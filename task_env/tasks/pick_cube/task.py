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


def _gripper_execution_info(state, target, *, clamp_default):
    """Project one measured boundary into the Task's readiness contract."""
    from .solution import PickCubePositionExecutionInfoV2

    opening = sum(float(state.joint_position[name]) for name in FINGERS)
    if -1e-6 <= opening < 0.:
        opening = 0.
    speed = sum(abs(float(state.joint_velocity[name])) for name in FINGERS)
    if target is None:
        target = min(.08, max(0., opening)) if clamp_default else opening
    return PickCubePositionExecutionInfoV2('pickcube-position-execution-info-v2',
        int(state.control_step), float(state.simulation_time), opening, speed, target,
        PickCubePositionExecutionInfoV2.closure_is_ready(target, opening, speed))


def physical_execution_info(env):
    """Project physical feedback, preserving its bounded fallback target."""
    return _gripper_execution_info(env.state,
        getattr(env, '_last_physical_opening_target', None), clamp_default=True)


def position_execution_info(state, last_position_transition):
    """Project the exact Position boundary and validate its target/readback."""
    target = (None if last_position_transition is None
              else float(last_position_transition[1].target.gripper.opening_m))
    result = _gripper_execution_info(state, target, clamp_default=False)
    result.validate()
    return result


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
class _DeviceTaskBinding:
    robot_view: object
    joint_initial: tuple[tuple[int, float], ...]
    cube_qpos_start: int
    cube_body_index: int
    cube_pose: tuple[float, ...]
    random_bounds: tuple[tuple[float, float], ...]
    terminate_on_success: bool


@dataclass(frozen=True)
class PickCubeTaskDefinition(TaskDefinitionBase):
    """Core Task Definition using the same measured lift predicate as the Artifact."""

    semantics: SemanticDefinition
    device_binding: _DeviceTaskBinding | None = None
    uses_unified_state_view = True
    device_state_required_fields = ('qpos', 'qvel', 'body_position', 'body_orientation',
                                    'frame_position', 'frame_orientation')
    device_random_algorithm = 'pcg64-v0'

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

    def bind_device(self, *, artifact, robot_view, source, runtime, terminate_on_success=False):
        """Bind the shared Task declaration to one source-resolved device layout."""
        if artifact.semantics != self.semantics:
            raise ValueError('PickCube device semantics differ from the selected Artifact')
        layout = runtime.resource_summary()['device_transition']
        joints = layout['joint_qpos_indices']
        free = layout['free_joint_qpos_indices']
        bodies = tuple(layout['body_names'])
        if ('cube-v1' not in free or 'cube-v1' not in bodies
                or EEF not in layout['frame_names']
                or not set(artifact.initialization.joint_position) <= set(joints)
                or not set(FINGERS) <= set(joints)):
            raise ValueError('PickCube device source lacks declared joints, cube, or end frame')
        dimensions = artifact.initialization.randomization
        if tuple(item.name for item in dimensions) != (
                'cube-v1.position_world.x', 'cube-v1.position_world.y'):
            raise ValueError('PickCube device reset requires its declared XY randomization')
        pose = artifact.initialization.poses_world['cube-v1']
        binding = _DeviceTaskBinding(robot_view,
            tuple((int(joints[name]), float(value))
                  for name, value in artifact.initialization.joint_position.items()),
            int(free['cube-v1']), bodies.index('cube-v1'),
            (*pose.position, *pose.quaternion_wxyz),
            tuple(tuple(item.training_bounds) for item in dimensions), bool(terminate_on_success))
        return replace(self, device_binding=binding)

    def _device_binding(self):
        if self.device_binding is None:
            raise RuntimeError('PickCube device task is not bound to a source')
        return self.device_binding

    def device_reset_spec(self):
        return {'random': {'cube_x': (), 'cube_y': ()}, 'state_fields': ('qpos', 'qvel')}

    def sample_device_reset(self, uniforms, template):
        import torch

        binding = self._device_binding()
        qpos, qvel = torch.zeros_like(template['qpos']), torch.zeros_like(template['qvel'])
        for index, value in binding.joint_initial:
            qpos[:, index] = value
        start = binding.cube_qpos_start
        qpos[:, start:start + 7] = torch.tensor(binding.cube_pose, dtype=qpos.dtype, device=qpos.device)
        for offset, name in enumerate(('cube_x', 'cube_y')):
            low, high = binding.random_bounds[offset]
            qpos[:, start + offset] = low + uniforms[name] * (high - low)
        return {'qpos': qpos, 'qvel': qvel}

    def reset_device(self, *, state, reset_mask, selection=None):
        """PickCube has no extra per-episode Task state to reset."""
        del state, reset_mask, selection
        self._device_binding()

    def device_observation_space(self):
        from ...environment.gym_compat import Box, Dict
        robot = self._device_binding().robot_view.robot
        return Dict({'state': robot.device_reference_observation_space(),
                     'privileged_state': Dict({'cube_v1_body_pose':
                         Box(-np.inf, np.inf, (1, 7), dtype=np.float32)})})

    def device_observation_schema(self):
        from ...environment.types import ObservationFieldSpec, ObservationSchema
        robot = self._device_binding().robot_view.robot
        robot_fields = robot.reference_observation_field_metadata(None)
        fields = []
        for name, space in self.device_observation_space()['state'].spaces.items():
            semantic, unit, frame = robot_fields[f'state.{name}']
            fields.append(ObservationFieldSpec(f'state.{name}', tuple(space.shape), str(space.dtype),
                                               semantic, unit, frame))
        fields.append(ObservationFieldSpec('privileged_state.cube_v1_body_pose', (1, 7), 'float32',
            'task object pose [x,y,z,qw,qx,qy,qz]', 'm + unit quaternion', 'world'))
        return ObservationSchema('selected-reference-observation-v1', tuple(fields),
                                 groups=('state', 'privileged_state'))

    def build_device_observation(self, state):
        import torch

        binding = self._device_binding()
        index = binding.cube_body_index
        cube = torch.cat((state.arrays['body_position'][:, index],
                          state.arrays['body_orientation'][:, index]), dim=1).unsqueeze(1)
        robot = binding.robot_view.robot
        return {'state': robot.device_reference_observation(binding.robot_view, state),
                'privileged_state': {'cube_v1_body_pose': cube}}

    def evaluate_device(self, *, state, action, elapsed_steps, previous_state=None):
        """Evaluate the existing PickCube lift, reach and grasp formula on device."""
        import torch

        del action, elapsed_steps, previous_state
        binding = self._device_binding()
        cube = state.arrays['body_position'][:, binding.cube_body_index]
        eef = binding.robot_view.frame_pose(state, EEF)[:, :3]
        opening = binding.robot_view.joint_positions(state, FINGERS).sum(dim=1)
        p = self.semantics.parameters_si
        lift = cube[:, 2] - p['rest_height']
        distance = torch.linalg.vector_norm(eef - cube, dim=1)
        reached = distance <= p['reach_distance']
        grasped = reached & (opening <= p['gripper_closed_opening'])
        lifted = lift >= p['lift_height']
        terms = {'reach': .10 * (1. - torch.tanh(10. * distance)),
                 'grasp': grasped.float() * .25,
                 'lift': torch.clamp(lift / p['lift_height'], 0., 1.) * .40,
                 'success': lifted.float()}
        metrics = {'reached_cube': reached, 'grasped_cube': grasped, 'lifted_cube': lifted,
                   'task_success': lifted, 'cube_x': cube[:, 0], 'cube_y': cube[:, 1],
                   'cube_z': cube[:, 2], 'cube_lift': lift, 'eef_to_cube_dist': distance,
                   'gripper_opening': opening, 'success_definition': torch.ones_like(lifted)}
        return {'reward': sum(terms.values()),
                'terminated': lifted if binding.terminate_on_success else torch.zeros_like(lifted),
                'truncated': torch.zeros_like(lifted), 'metrics': metrics, 'reward_terms': terms}

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


def physical_observation(env, state):
    """Project the physical publication without requiring a Position controller."""
    adapted, subject, subject_info = env.binding.robot.physical_reference_observation(env, state)
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


def physical_task_binding_fields(*, task_config, lift_height_m,
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
        'observation_projection': physical_observation,
        'physical_sequence_v2_observation': True,
    }


def physical_task_binding(*, build, task_config, lift_height_m,
                          validate_solution, reset_capability=None,
                          cube_force_z_N=None, runtime_input=False):
    """Bind PickCube semantics to a source-bound physical Controller."""
    from ...environment.reference_binding import ReferenceTaskBinding
    fields = physical_task_binding_fields(task_config=task_config, lift_height_m=lift_height_m,
        cube_force_z_N=cube_force_z_N)
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
        position_execution_info_key='pickcube_position_execution_info_v2' if reset_switch else None,
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


# Existing imports remain a thin bridge while repository callers migrate.
from .specialization import (
    REFERENCE_ENV_ID, PickCubeReferenceEnv, _configuration, _recipe, build_artifact,
    build_readiness_solution, make_reference_binding,
)

__all__ = ["PickCubeReferenceEnv", "PickCubeTaskDefinition", "REFERENCE_ENV_ID",
           "build_artifact", "build_readiness_solution", "evaluate", "make_reference_binding",
           "sample_reset", "semantic_definition"]
