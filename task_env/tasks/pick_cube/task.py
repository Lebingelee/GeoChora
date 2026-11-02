"""PickCube reset, observations, and task evaluation semantics."""
from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np

from ...artifacts import CanonicalStateView, PoseWorld, SemanticDefinition, TaskArtifact
from ...artifacts.execution import ResetSample
from ...assembly import TaskReferences
from ...environment import (RuntimeSnapshot, TaskEvaluation, TaskEvaluationContextV1,
                            TaskPredicateEvaluationV1, TaskPredicateResultV1)
from ...environment.task_definition import TaskDefinitionBase, as_task_state_view
from ...objects.pick_cube import CUBE_HALF_SIZE

EEF = "panda-v1/ee"
FINGERS = ("panda-v1/finger_joint1", "panda-v1/finger_joint2")

def semantic_definition(*, lift_height_m=None) -> SemanticDefinition:
    recipe = _recipe()
    scene, task = recipe["scene"], recipe["success"]
    return SemanticDefinition(
        schema_version="semantics-v0", evaluator="pick_cube_lift_v0",
        required_poses=("cube-v1", EEF), required_joints=FINGERS,
        parameters_si={
            "rest_height": float(scene["table_top_z"]) + CUBE_HALF_SIZE,
            "lift_height": float(task["lift_height_m"] if lift_height_m is None else lift_height_m),
            "reach_distance": float(task["reach_distance_m"]),
            "gripper_closed_opening": float(task["gripper_closed_opening_m"]),
        },
        success_definition=recipe["success_definition"],
    )


def _evaluate_values(cube_pos, eef_pos, gripper_opening, semantics=None) -> TaskEvaluation:
    semantics = semantic_definition() if semantics is None else semantics
    p = semantics.parameters_si
    # Keep the historical tuple-scalar evaluation order. Coercing these
    # coordinates to NumPy scalars changes a few distance/reward values by one
    # ULP even when every recorded physical state and action is identical.
    cube_lift = float(cube_pos[2] - p["rest_height"])
    distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(eef_pos, cube_pos, strict=True)))
    reached = distance <= p["reach_distance"]
    grasped = bool(reached and gripper_opening <= p["gripper_closed_opening"])
    lifted = bool(cube_lift >= p["lift_height"])
    terms = {
        "reach": .10 * (1.0 - math.tanh(10.0 * distance)),
        "grasp": .25 if grasped else 0.0,
        "lift": min(.40, max(0.0, cube_lift / p["lift_height"]) * .40),
        "success": 1.0 if lifted else 0.0,
    }
    metrics = {
        "reached_cube": bool(reached), "grasped_cube": grasped,
        "lifted_cube": lifted, "task_success": lifted,
        "cube_x": float(cube_pos[0]), "cube_y": float(cube_pos[1]),
        "cube_z": float(cube_pos[2]), "cube_lift": cube_lift,
        "eef_to_cube_dist": distance, "gripper_opening": float(gripper_opening),
        "success_definition": True,
    }
    return TaskEvaluation(float(sum(terms.values())), lifted, False, metrics, terms)


def evaluate(state: CanonicalStateView, semantics: SemanticDefinition | None = None, *, lift_height_m=None) -> TaskEvaluation:
    """Lift is the sole success gate; grasp remains a reward diagnostic."""
    if not isinstance(state, CanonicalStateView):
        raise TypeError("PickCube evaluation requires CanonicalStateView")
    expected = semantic_definition(lift_height_m=lift_height_m)
    semantics = expected if semantics is None else semantics
    if semantics != expected:
        raise ValueError("unsupported PickCube semantic definition")
    semantics.require_state(state)
    gripper_opening = sum(state.joint_position[name] for name in FINGERS)
    return _evaluate_values(state.pose_world["cube-v1"].position,
                            state.pose_world[EEF].position, gripper_opening, semantics)


@dataclass(frozen=True)
class PickCubeTaskDefinition(TaskDefinitionBase):
    """Core Task Definition using the same measured lift predicate as the Artifact."""

    references: TaskReferences
    success_definition: str = "cube_lifted_v1"

    def __post_init__(self):
        if self.success_definition != _recipe()["success_definition"]:
            raise ValueError("unsupported PickCube success definition")
        if "panda-v1" not in self.references.agents or "cube-v1" not in self.references.objects:
            raise KeyError("PickCube Task Definition requires panda-v1 and cube-v1 references")

    def reset(self, snapshot: RuntimeSnapshot) -> TaskEvaluation:
        return self._evaluate_snapshot(snapshot)

    def evaluate(self, previous_snapshot, action, current_snapshot) -> TaskEvaluation:
        del previous_snapshot, action
        return self._evaluate_snapshot(current_snapshot)

    def _evaluate_snapshot(self, snapshot):
        return self._evaluate_state_view(as_task_state_view(snapshot))

    def _evaluate_state_view(self, state, *, batch_index=None):
        panda = self.references.agents["panda-v1"]
        cube_ref = self.references.objects["cube-v1"]
        if state.site_xpos is None or state.body_xpos is None:
            raise ValueError("PickCube evaluation requires site_xpos and body_xpos")
        if state.is_batch:
            if batch_index is None:
                raise ValueError("batch PickCube state requires an explicit row")
            cube_pos = state.body_xpos[batch_index, int(cube_ref.body_ids[0])]
            eef_pos = state.site_xpos[batch_index, int(panda.eef_site_id)]
            opening = float(np.sum(state.qpos[batch_index, panda.gripper_qpos_ids]))
        else:
            cube_pos = state.body_xpos[int(cube_ref.body_ids[0])]
            eef_pos = state.site_xpos[int(panda.eef_site_id)]
            opening = float(np.sum(state.qpos[panda.gripper_qpos_ids]))
        return _evaluate_values(cube_pos, eef_pos, opening)

    def evaluate_predicates(
        self, context: TaskEvaluationContextV1
    ) -> TaskPredicateEvaluationV1:
        """Expose the existing lift oracle as a read-only typed predicate."""

        if not isinstance(context, TaskEvaluationContextV1):
            raise TypeError("PickCube predicates require TaskEvaluationContextV1")
        state = context.state
        if state.body_xpos is None or state.site_xpos is None:
            return TaskPredicateEvaluationV1.available(
                {
                    "cube_lifted": TaskPredicateResultV1.unavailable(
                        "required_pickcube_state_unavailable"
                    )
                }
            )
        try:
            if state.is_batch:
                evaluations = [
                    self._evaluate_state_view(state, batch_index=index)
                    for index in range(state.batch_size)
                ]
                values = np.asarray(
                    [
                        evaluation.success for evaluation in evaluations
                    ],
                    dtype=np.bool_,
                )
            else:
                evaluation = self._evaluate_state_view(state)
                evaluations = [evaluation]
                values = evaluation.success
        except IndexError:
            return TaskPredicateEvaluationV1.available(
                {
                    "cube_lifted": TaskPredicateResultV1.unavailable(
                        "required_pickcube_state_unavailable"
                    )
                }
            )
        if any(
            not np.isfinite(
                [
                    evaluation.metrics["cube_lift"],
                    evaluation.metrics["eef_to_cube_dist"],
                ]
            ).all()
            for evaluation in evaluations
        ):
            return TaskPredicateEvaluationV1.available(
                {
                    "cube_lifted": TaskPredicateResultV1.unavailable(
                        "required_pickcube_state_nonfinite"
                    )
                }
            )
        return TaskPredicateEvaluationV1.available(
            {"cube_lifted": TaskPredicateResultV1.available(values)}
        )


def sample_reset(artifact: TaskArtifact, task_seed: int, *, lift_height_m=None) -> ResetSample:
    """Sample the selected PCG64-v0 reset distribution at the task boundary."""
    if not isinstance(artifact, TaskArtifact) or artifact.identity_hash != build_artifact(lift_height_m=lift_height_m).identity_hash:
        raise ValueError("selected P1.6 experimental_100hz TaskArtifact required")
    if type(task_seed) is not int or task_seed < 0:
        raise ValueError("task_seed must be a nonnegative integer")
    rng = np.random.Generator(np.random.PCG64(task_seed))
    initial = artifact.initialization
    position = list(initial.poses_world["cube-v1"].position)
    for index, dimension in enumerate(initial.randomization):
        position[index] = float(rng.uniform(*dimension.training_bounds))
    poses = {"cube-v1": PoseWorld(tuple(position), initial.poses_world["cube-v1"].quaternion_wxyz)}
    return ResetSample.create(
        schema_version="reset-sample-v0", task_artifact_hash=artifact.identity_hash,
        sampler_id="pick-cube-v1/uniform_xy", sampler_version="pcg64-v0",
        task_seed=task_seed, joint_position=dict(initial.joint_position), poses_world=poses,
        velocity_policy="zero_named_joint_and_entity_velocities",
        control_policy="arm_targets_at_initial_joints_gripper_open", settle_steps=initial.settle_steps,
    )


# Existing imports remain a thin bridge while repository callers migrate.
from .specialization import (
    REFERENCE_ENV_ID, PickCubeReferenceEnv, _configuration, _recipe, build_artifact,
    build_runtime_source, build_reference, build_isaac_reference,
    build_readiness_solution, make_reference_binding,
)

__all__ = ["PickCubeReferenceEnv", "PickCubeTaskDefinition", "REFERENCE_ENV_ID",
           "build_artifact", "build_readiness_solution", "build_reference",
           "build_runtime_source", "evaluate", "make_reference_binding", "sample_reset",
           "semantic_definition", "build_isaac_reference"]
