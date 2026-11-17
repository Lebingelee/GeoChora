"""NutAssembly reset, feedback observations, and task evaluation semantics."""
from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np

from ...artifacts import CanonicalStateView, SemanticDefinition, TaskArtifact, TaskArtifactV1
from ...artifacts.execution import ResetSample
from ...environment.task_definition import CanonicalTaskStateView, TaskDefinitionBase, as_task_state_view
from ...objects.nut_assembly import NUT_HALF_HEIGHT, NUT_HANDLE_LOCAL_X
from ...utils.rotation import quat_wxyz_to_matrix

EEF = "panda-v1/ee"
NUT = "square-nut-v1"
PEG = "square-peg-v1"
FINGERS = ("panda-v1/finger_joint1", "panda-v1/finger_joint2")
SUCCESS = "nut_on_square_peg_canonical_state_v0"

def semantic_definition(*, lift_height_m=None, task_config=None) -> SemanticDefinition:
    recipe = _recipe() if task_config is None else task_config["recipe"]
    p = recipe["semantic_parameters"]
    scene = recipe["scene"]
    return SemanticDefinition("semantics-v0", "nut_assembly_state_v0",
        (NUT, PEG, EEF), FINGERS,
        {**{key: float(value) for key, value in p.items()},
         "lift_height": float(p["lift_height"] if lift_height_m is None else lift_height_m),
         "table_top_z": float(scene["table_top_z"]),
         "nut_half_height": float(NUT_HALF_HEIGHT),
         "nut_contact_margin": float(recipe["asset"]["nut_contact_margin_m"]),
         "nut_handle_local_x": float(NUT_HANDLE_LOCAL_X),
         "peg_half_height": float(scene["peg_half_height"])}, SUCCESS)


def evaluate(state: CanonicalStateView, semantics: SemanticDefinition | None = None, *, lift_height_m=None, task_config=None):
    from ...environment import TaskEvaluation
    expected = semantic_definition(lift_height_m=lift_height_m, task_config=task_config)
    semantics = expected if semantics is None else semantics
    if not isinstance(state, CanonicalStateView) or semantics != expected:
        raise ValueError("unsupported canonical NutAssembly state/semantics")
    return _evaluate_bound(state, semantics)


def _evaluate_bound(state: CanonicalStateView, semantics: SemanticDefinition):
    from ...environment import TaskEvaluation
    semantics.require_state(state)
    p = semantics.parameters_si
    nut, peg = state.pose_world[NUT], state.pose_world[PEG]
    position = np.asarray(nut.position)
    ee = np.asarray(state.pose_world[EEF].position)
    rotation = quat_wxyz_to_matrix(nut.quaternion_wxyz)
    handle = position + rotation @ np.array([p["nut_handle_local_x"], 0.0, 0.0])
    yaw = float(np.arctan2(rotation[1, 0], rotation[0, 0]))
    period = 0.5 * np.pi
    yaw_error = abs((yaw + 0.5 * period) % period - 0.5 * period)
    xy_error = float(np.linalg.norm(position[:2] - np.asarray(peg.position[:2])))
    z_error = float(position[2] - (p["table_top_z"] + p["nut_half_height"] + p["nut_contact_margin"]))
    ee_distance = float(np.linalg.norm(ee - position))
    handle_distance = float(np.linalg.norm(ee - handle))
    opening = float(sum(state.joint_position[name] for name in FINGERS))
    reached = handle_distance <= p["grasp_distance"]
    grasped = bool(reached and opening <= p["gripper_closed_opening"])
    lifted = bool(position[2] >= p["table_top_z"] + p["nut_half_height"] + p["lift_height"])
    hover = bool(lifted and xy_error <= p["hover_xy_tolerance"])
    aligned = bool(xy_error <= p["insert_xy_tolerance"] and yaw_error <= p["insert_yaw_tolerance"])
    passed = bool(position[2] <= peg.position[2] + p["peg_half_height"] - p["nut_contact_margin"])
    returned = bool(position[2] <= p["table_top_z"] + 3 * p["nut_half_height"])
    inserted = bool(aligned and passed and returned)
    gripper_released = bool(opening >= p["gripper_release_opening"])
    released = bool(inserted and gripper_released and ee_distance >= p["release_distance"])
    success = bool(inserted and released)
    metrics = {
        "reached_nut": bool(reached), "grasped_nut": bool(grasped),
        "lifted_nut": bool(lifted), "hovered_over_peg": bool(hover),
        "aligned_with_peg": bool(aligned), "peg_passed_through_nut_center": bool(passed),
        "nut_returned_to_table": bool(returned), "inserted_on_peg": bool(inserted),
        "gripper_released": bool(gripper_released), "released_nut": bool(released),
        "task_success": bool(success), "nut_x": float(position[0]),
        "nut_y": float(position[1]), "nut_z": float(position[2]), "nut_yaw": yaw,
        "table_seated_nut_max_z": p["table_top_z"] + 3 * p["nut_half_height"],
        "peg_xy_error": xy_error, "peg_z_error": z_error, "yaw_error": yaw_error,
        "eef_to_nut_dist": ee_distance, "eef_to_handle_dist": handle_distance,
        "gripper_opening": opening, "success_definition": True,
    }
    terms = {"reach": 0.10 * (1.0 - math.tanh(10.0 * handle_distance)),
             "grasp": 0.25 if grasped else 0.0, "lift": 0.25 if lifted else 0.0,
             "hover": 0.15 if hover else 0.0, "insert": 0.15 if inserted else 0.0,
             "release": 0.10 if released else 0.0, "success": 1.0 if success else 0.0}
    return TaskEvaluation(reward=float(sum(terms.values())), success=success,
        failure=False, metrics=metrics, reward_terms=terms)


def sample_reset(artifact: TaskArtifact, task_seed: int = 19, *, lift_height_m=None, task_config=None) -> ResetSample:
    expected = build_artifact(lift_height_m=lift_height_m, task_config=task_config)
    if not isinstance(artifact, TaskArtifact) or artifact.to_mapping() != expected.to_mapping():
        raise ValueError("selected NA-S0 TaskArtifact required")
    artifact.validate()
    if type(task_seed) is not int or task_seed != 19:
        raise ValueError("selected NA-S0 uses fixed provenance seed19")
    initialization = artifact.initialization
    reset = (_recipe() if task_config is None else task_config["recipe"])["reset"]
    return ResetSample.create(schema_version="reset-sample-v0",
        task_artifact_hash=artifact.identity_hash, sampler_id=reset["sampler_id"],
        sampler_version=reset["sampler_version"], task_seed=task_seed,
        joint_position=dict(initialization.joint_position), poses_world=dict(initialization.poses_world),
        velocity_policy=reset["inherited_state_policy"],
        control_policy=reset["control_policy"],
        settle_steps=int(reset["settle_steps"]))


@dataclass(frozen=True)
class NutAssemblyTaskDefinition(TaskDefinitionBase):
    """Immutable selected reset and evaluation contract bound to an Artifact."""

    artifact_hash: str
    semantics: SemanticDefinition
    sampler_id: str
    sampler_version: str
    velocity_policy: str
    control_policy: str
    settle_steps: int
    uses_unified_state_view = True

    @classmethod
    def from_artifact(cls, artifact: TaskArtifact, reset: dict):
        if not isinstance(artifact, (TaskArtifact, TaskArtifactV1)) or artifact.semantics.evaluator != 'nut_assembly_state_v0':
            raise ValueError('NutAssembly task definition requires its semantic Artifact')
        artifact.validate()
        return cls(artifact.identity_hash, artifact.semantics, reset['sampler_id'],
                   reset['sampler_version'], reset['inherited_state_policy'],
                   reset['control_policy'], int(reset['settle_steps']))

    def reset(self, state, reset_mask=None):
        return self.evaluate(state)

    def evaluate(self, state, semantics=None, *, action=None, elapsed_steps=None, previous_state=None):
        view = as_task_state_view(state)
        if not isinstance(view, CanonicalTaskStateView):
            raise ValueError('NutAssembly semantics require named canonical state')
        semantics = self.semantics if semantics is None else semantics
        if semantics != self.semantics:
            raise ValueError('unsupported canonical NutAssembly state/semantics')
        return _evaluate_bound(view.canonical_state, semantics)

    def sample_reset(self, artifact, task_seed):
        if not (isinstance(artifact, (TaskArtifact, TaskArtifactV1))
                and artifact.identity_hash == self.artifact_hash):
            raise ValueError('selected NA-S0 TaskArtifact required')
        artifact.validate()
        if artifact.semantics != self.semantics:
            raise ValueError('NutAssembly Artifact semantics differ from its task definition')
        if type(task_seed) is not int or task_seed != 19:
            raise ValueError('selected NA-S0 uses fixed provenance seed19')
        initial = artifact.initialization
        return ResetSample.create(
            schema_version='reset-sample-v0', task_artifact_hash=artifact.identity_hash,
            sampler_id=self.sampler_id, sampler_version=self.sampler_version, task_seed=task_seed,
            joint_position=dict(initial.joint_position), poses_world=dict(initial.poses_world),
            velocity_policy=self.velocity_policy, control_policy=self.control_policy,
            settle_steps=self.settle_steps,
        )


def _reset_seed(seed):
    if seed not in (19, None):
        raise ValueError("selected NutAssembly NA-S0 has fixed provenance seed19")
    return 19 if seed is None else seed


from .specialization import (
    NutAssemblyReferenceEnv, REFERENCE_ENV_ID, _configuration, _recipe,
    build_artifact, build_reference, build_outcome_solution,
)

__all__ = ["NutAssemblyTaskDefinition", "NutAssemblyReferenceEnv", "REFERENCE_ENV_ID", "build_artifact",
           "build_reference", "build_outcome_solution", "evaluate",
           "sample_reset", "semantic_definition"]
