"""PickCube reset, observations, and task evaluation semantics."""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import math
import numpy as np

from ...artifacts import (CanonicalStateView, PoseWorld, SemanticDefinition, TaskArtifact,
    AssetDefinition, ArticulationDefinition, EntityInstance, FrameDefinition, FrameReference,
    JointDefinition, SceneDefinition)
from ...artifacts.execution import ResetSample
from ...environment import (adapt_legacy_recipe_task_source, compile_task_artifact_v1,
                            TaskEvaluation, TaskEvaluationContextV1,
                            TaskPredicateEvaluationV1, TaskPredicateResultV1)
from ...environment.task_definition import CanonicalTaskStateView, TaskDefinitionBase, as_task_state_view
from ...objects.pick_cube import CUBE_HALF_SIZE

EEF = "panda-v1/ee"
FINGERS = ("panda-v1/finger_joint1", "panda-v1/finger_joint2")


def physical_execution_info(env):
    """Project the task's measured gripper readiness at the current boundary."""
    from .solution import PickCubePositionExecutionInfoV1

    state = env.state
    opening = sum(float(state.joint_position[name]) for name in FINGERS)
    if -1e-6 <= opening < 0.:
        opening = 0.
    speed = sum(abs(float(state.joint_velocity[name])) for name in FINGERS)
    target = getattr(env, '_last_physical_opening_target', None)
    target = min(.08, max(0., opening)) if target is None else target
    return PickCubePositionExecutionInfoV1('pickcube-position-execution-info-v1',
        int(state.control_step), float(state.simulation_time), opening, speed, target,
        bool(target <= .045 and opening <= .045 and speed <= .005))


def observe_physical_action(env, action, spec):
    """Retain the opening target needed by PickCube's readiness semantics."""
    if action is None:
        env._last_physical_opening_target = None
    elif spec['kind'] == 'r3-pose':
        env._last_physical_opening_target = .04 * (float(np.clip(action[-1], -1., 1.)) + 1.)
    else:
        env._last_physical_opening_target = float(action[-1])


def semantic_definition(*, lift_height_m=None, task_config=None) -> SemanticDefinition:
    recipe = _recipe() if task_config is None else task_config["recipe"]
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


def evaluate(state: CanonicalStateView, semantics: SemanticDefinition | None = None, *, lift_height_m=None, task_config=None) -> TaskEvaluation:
    """Lift is the sole success gate; grasp remains a reward diagnostic."""
    if not isinstance(state, CanonicalStateView):
        raise TypeError("PickCube evaluation requires CanonicalStateView")
    expected = semantic_definition(lift_height_m=lift_height_m, task_config=task_config)
    semantics = expected if semantics is None else semantics
    if semantics != expected:
        raise ValueError("unsupported PickCube semantic definition")
    return _evaluate_bound(state, semantics)


def _evaluate_bound(state, semantics):
    """Evaluate canonical task inputs in their historical scalar order."""
    semantics.require_state(state)
    gripper_opening = sum(state.joint_position[name] for name in FINGERS)
    return _evaluate_values(state.pose_world["cube-v1"].position,
                            state.pose_world[EEF].position, gripper_opening, semantics)


@dataclass(frozen=True)
class PickCubeTaskDefinition(TaskDefinitionBase):
    """Core Task Definition using the same measured lift predicate as the Artifact."""

    semantics: SemanticDefinition
    uses_unified_state_view = True

    @property
    def success_definition(self):
        return self.semantics.success_definition

    @classmethod
    def from_artifact(cls, artifact):
        if artifact.semantics.evaluator != 'pick_cube_lift_v0':
            raise ValueError('PickCube TaskDefinition requires its semantic Artifact')
        return cls(semantics=artifact.semantics)

    def __post_init__(self):
        if not isinstance(self.semantics, SemanticDefinition) or self.semantics.evaluator != 'pick_cube_lift_v0':
            raise ValueError('PickCube TaskDefinition requires its Artifact semantics')
        if self.semantics.success_definition != 'cube_lifted_v1':
            raise ValueError('unsupported PickCube success definition')

    def reset(self, state, reset_mask=None) -> TaskEvaluation:
        return self._evaluate_snapshot(state)

    def evaluate(self, previous_snapshot=None, action=None, current_snapshot=None, *,
                 state=None, elapsed_steps=None, previous_state=None) -> TaskEvaluation:
        return self._evaluate_snapshot(current_snapshot if state is None else state)

    def _evaluate_snapshot(self, snapshot):
        return self._evaluate_state_view(as_task_state_view(snapshot))

    def _evaluate_state_view(self, state):
        if not isinstance(state, CanonicalTaskStateView):
            raise TypeError('PickCube requires a named canonical task state')
        return _evaluate_bound(state.canonical_state, self.semantics)

    def evaluate_predicates(
        self, context: TaskEvaluationContextV1
    ) -> TaskPredicateEvaluationV1:
        """Expose the existing lift oracle as a read-only typed predicate."""

        if not isinstance(context, TaskEvaluationContextV1):
            raise TypeError("PickCube predicates require TaskEvaluationContextV1")
        state = context.state
        canonical = state.canonical_state if isinstance(state, CanonicalTaskStateView) else None
        unavailable = (canonical is None
            or not set(self.semantics.required_poses) <= set(canonical.pose_world)
            or not set(self.semantics.required_joints) <= set(canonical.joint_position))
        if unavailable:
            return TaskPredicateEvaluationV1.available(
                {
                    "cube_lifted": TaskPredicateResultV1.unavailable(
                        "required_pickcube_state_unavailable"
                    )
                }
            )
        evaluation = self._evaluate_state_view(state)
        if not np.isfinite([evaluation.metrics["cube_lift"],
                            evaluation.metrics["eef_to_cube_dist"]]).all():
            return TaskPredicateEvaluationV1.available(
                {
                    "cube_lifted": TaskPredicateResultV1.unavailable(
                        "required_pickcube_state_nonfinite"
                    )
                }
            )
        return TaskPredicateEvaluationV1.available(
            {"cube_lifted": TaskPredicateResultV1.available(evaluation.success)}
        )


def physical_observation(env, state, *, hand_frame_id="hand"):
    """Project the physical publication without requiring a Position controller."""
    adapted, subject, subject_info = env.binding.robot.physical_reference_observation(
        env, state, hand_frame_id=hand_frame_id)
    from ...environment.reference_binding import evaluate_task_definition
    evaluation = evaluate_task_definition(env, adapted)
    cube = state.pose_world['cube-v1']
    obs = {'state': subject, 'privileged_state': {'cube_v1_body_pose': np.asarray(
        [(*cube.position, *cube.quaternion_wxyz)], dtype=np.float32)}}
    info = {'is_success': bool(evaluation.success), 'task_failure': bool(evaluation.failure),
            'task_metrics': dict(evaluation.metrics), 'control_step': int(state.control_step),
            'simulation_time_s': float(state.simulation_time), **subject_info}
    return obs, info, evaluation


def task_binding_fields(*, task_config=None, lift_height_m=None, reset_sampler=None,
                        cube_force_z_N=None):
    """Provide the task semantics shared by each admitted control execution."""
    if reset_sampler is None:
        reset_sampler = lambda artifact, seed: sample_reset(
            artifact, seed, lift_height_m=lift_height_m, task_config=task_config)
    return {
        'reset_sample': reset_sampler,
        'evaluate': lambda state, semantics: evaluate(
            state, semantics, lift_height_m=lift_height_m, task_config=task_config),
        'task_definition_factory': PickCubeTaskDefinition.from_artifact,
        'task_state_projection': as_task_state_view,
        'object_poses': (('cube-v1', 'cube_v1'),),
        'task_com_wrench_factory': task_com_wrench_factory(cube_force_z_N),
    }


def physical_task_binding_fields(*, task_config, lift_height_m, hand_frame_id,
                                 reset_sampler=None, cube_force_z_N=None):
    """Declare task semantics shared by the admitted physical source formats."""
    from functools import partial
    from ...controllers.canonical.contracts import reference_pose_action
    from ...observations.selected_reference import selected_reference_observation_spaces

    return {
        **task_binding_fields(task_config=task_config, lift_height_m=lift_height_m,
                              reset_sampler=reset_sampler, cube_force_z_N=cube_force_z_N),
        'external_actions': True, 'interval_mode': 'grouped', 'recorder_mode': 'execution',
        'prepare_action': reference_pose_action,
        'observation_space_factory': partial(selected_reference_observation_spaces, include_robot_state=True),
        'observation_projection': partial(physical_observation, hand_frame_id=hand_frame_id),
        'physical_sequence_v2_observation': True,
    }


def physical_task_binding(*, build, task_config, lift_height_m, hand_frame_id,
                          validate_solution, reset_capability=None,
                          cube_force_z_N=None, runtime_input=False):
    """Bind PickCube semantics to a source-bound physical Controller."""
    from ...environment.reference_binding import ReferenceTaskBinding
    fields = physical_task_binding_fields(task_config=task_config, lift_height_m=lift_height_m,
        hand_frame_id=hand_frame_id, cube_force_z_N=cube_force_z_N)
    if runtime_input:
        return ReferenceTaskBinding(build=build, **fields,
            reset_runtime_input=lambda value: value.get('session_admission_input'),
            validate_external_solution=validate_solution, external_solution_actions=True,
            reset_expert_kwargs=lambda env: {'execution_info': env.expert_execution_info()},
            observe_expert_kwargs=lambda env, _samples: {'execution_info': env.expert_execution_info()})
    reset_switch = reset_capability is not None
    return ReferenceTaskBinding(build=build, **fields, action_schema=None, action_space_factory=None,
        external_solution_actions=reset_switch,
        validate_external_solution=validate_solution if reset_switch else None,
        position_execution_info=physical_execution_info if reset_switch else None,
        position_execution_info_key='pickcube_position_execution_info_v1' if reset_switch else None,
        physical_reset_capability=reset_capability,
        physical_action_observer=observe_physical_action if reset_switch else None)


def task_com_wrench_factory(cube_force_z_N):
    """Declare the Task's optional vertical force for the common control interval."""
    if cube_force_z_N is None:
        return None

    def contributions(env):
        from ...controllers.canonical.physical_commands import ExternalComWrenchSumSegmentV1
        return (ExternalComWrenchSumSegmentV1('external-com-wrench-sum-segment-v1',
            'pickcube-task-writer-v1', 'pickcube-task-cube-force-v1', 'cube-v1',
            0, env.artifact.timebase.control_substeps,
            (0., 0., cube_force_z_N), (0., 0., 0.)),)

    return contributions


def sample_reset(artifact: TaskArtifact, task_seed: int, *, lift_height_m=None, task_config=None) -> ResetSample:
    """Sample the selected PCG64-v0 reset distribution at the task boundary."""
    if not isinstance(artifact, TaskArtifact) or artifact.identity_hash != build_artifact(lift_height_m=lift_height_m, task_config=task_config).identity_hash:
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


SCHEMA_VERSION = "pick-cube-isaac-scene-v1"
SCENE_RECIPE_ID = "pick-cube-isaac-desktop-scene-v1"


def build_pickcube_isaac_scene(task_config: dict, *, robot=None) -> SceneDefinition:
    """Compose the Task scene with the admitted provider's Robot asset identity."""
    if robot is None:
        from ...registry import AGENT_REGISTRY
        robot = AGENT_REGISTRY.create('panda-v1')
    from ...runtime.sessions.isaac_usd_admission import build_f06_task_scene
    return build_f06_task_scene(task_config, robot=robot, build_task_scene=build_pickcube_scene)


def build_pickcube_scene(task_config, *, robot_scene, robot_asset, ee_frame, cube_frame, cube_joint, table_frame):
    """Compose Task entities with an already declared Robot and source frame names."""
    scene_id = robot_scene.scene_id
    robot_entity = replace(robot_scene.entities[0], asset_id=robot_asset.asset_id,
                           asset_version=robot_asset.asset_version)
    recipe_digest = hashlib.sha256(_canonical_task_recipe(task_config)).hexdigest()
    cube_asset = AssetDefinition(
        "asset-definition-v1", "pick-cube-cube-v1", "pick-cube-recipe-v1",
        "geochora-task-scene://pick-cube-v1/cube", SCENE_RECIPE_ID, recipe_digest,
    )
    tabletop_asset = AssetDefinition(
        "asset-definition-v1", "pick-cube-tabletop-v1", "pick-cube-recipe-v1",
        "geochora-task-scene://pick-cube-v1/tabletop", SCENE_RECIPE_ID, recipe_digest,
    )
    cube = EntityInstance(
        "entity-instance-v1", "cube-v1", cube_asset.asset_id, cube_asset.asset_version,
    )
    tabletop = EntityInstance(
        "entity-instance-v1", "tabletop-v1", tabletop_asset.asset_id,
        tabletop_asset.asset_version,
    )
    identity_pose = PoseWorld((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
    cube_articulation = ArticulationDefinition(
        "articulation-definition-v1",
        "cube-v1",
        "world",
        ("world", cube_frame),
        (JointDefinition(
            "joint-definition-v1",
            cube_joint,
            FrameReference("cube-v1", "world"),
            FrameReference("cube-v1", cube_frame),
            identity_pose,
            identity_pose,
            "floating",
            None,
            "xyz_meter_quaternion_wxyz",
            "linear_xyz_meter_per_second_angular_xyz_radian_per_second",
            7,
            6,
        ),),
    )
    return SceneDefinition(
        schema_version="scene-definition-v3",
        scene_id=scene_id,
        assets=(robot_asset, cube_asset, tabletop_asset),
        entities=(robot_entity, cube, tabletop),
        frames=(
            *robot_scene.frames,
            FrameDefinition("frame-definition-v1", robot_entity.entity_id, ee_frame, "runtime", None, None),
            FrameDefinition("frame-definition-v1", "cube-v1", "world", "runtime", None, None),
            FrameDefinition("frame-definition-v1", "cube-v1", cube_frame, "runtime", None, None),
            FrameDefinition("frame-definition-v1", "tabletop-v1", table_frame, "runtime", None, None),
        ),
        articulations=(*robot_scene.articulations, cube_articulation),
        robots=robot_scene.robots,
        actuator_resources=robot_scene.actuator_resources,
        control_groups=robot_scene.control_groups,
    )


def _canonical_task_recipe(task_config: dict) -> bytes:
    return json.dumps(
        {"schema_version": SCHEMA_VERSION, "recipe": task_config["recipe"]},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def compile_pickcube_task_artifact(task_config, scene, legacy_artifact, *, frame_bindings, cube_frame,
                                   additional_frames=None):
    """Compile the same Task semantics against a declared source Scene."""
    if set(task_config) - {'recipe', 'environment', 'execution'}:
        raise ValueError('unsupported PickCube task config fields')
    task_source = adapt_legacy_recipe_task_source({
        'recipe': task_config['recipe'], 'environment': task_config['environment'],
    })
    artifact = compile_task_artifact_v1(task_source, scene, legacy_artifact,
                                        frame_bindings=frame_bindings)
    bindings = dict(artifact.legacy_frame_bindings)
    bindings['cube-v1'] = FrameReference('cube-v1', cube_frame)
    for name, reference in (additional_frames or {}).items():
        bindings.setdefault(name, reference)
    artifact = replace(artifact, legacy_frame_bindings=bindings)
    artifact.validate_scene(scene)
    return task_source, artifact


def compile_pickcube_isaac_task_artifact(task_config: dict, legacy_artifact, *, robot=None):
    """Compile the existing PickCube v0 semantics against its USD Scene."""
    scene = build_pickcube_isaac_scene(task_config, robot=robot)
    task_source, artifact = compile_pickcube_task_artifact(task_config, scene, legacy_artifact,
        frame_bindings={
            'panda-v1/base': FrameReference('panda-v1', 'link0'),
            'panda-v1/ee': FrameReference('panda-v1', 'ee'),
        }, cube_frame='cube')
    return task_source, scene, artifact




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
