"""Source-bound two-wheel declarations for the shared physical RuntimeSession."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import numpy as np

from ..artifacts import (ActionIntent, ActuatorReference, ActuatorResourceDefinition,
    ArticulationDefinition, AssetDefinition, ControlGroup, EntityDefinition,
    EntityInstance, FrameDefinition, FrameReference, InitializationContract,
    JointDefinition, JointReference, PoseWorld, RobotInstance, SceneDefinition,
    SemanticDefinition, Timebase)
from ..artifacts.logical_assembly import (LogicalAssemblyV1, LogicalAssemblyScenePinV1,
    LogicalAssemblyEntityMemberV1, LogicalAssemblySubcomponentReferenceV1)
from ..artifacts.state import StateFieldRequirement, StateRequirements
from ..artifacts.execution import ResetSampleV1, ResetPlanV1
from ..assembly.assets import _source_closure_digest
from ..assembly.compiler import compile_reference_source
from ..assembly.source import TaskSceneSource
from ..environment.task_source import TaskSourceV1, TaskArtifactDeclarationV1
from ..environment.types import TaskCompositionSpec, RuntimeSnapshot
from ..environment.reference_binding import ReferenceTaskBinding
from ..environment.gym_compat import Box, Dict
from ..robots.two_wheel_balance import TwoWheelBalanceEntity, TWO_WHEEL_ACTION_CONTRACT
from ..runtime.sessions.physical_control import PhysicalControlExecutionV1, compile_declared_subject_binding
from ..runtime.sessions.source import project_scene_definition_v3_to_mjcf, source_asset_bytes
from .two_wheel_balance import (TWO_WHEEL_BALANCE_MJCF_XML, TWO_WHEEL_BALANCE_TASK_UID,
    TWO_WHEEL_BALANCE_SCENE_UID, TWO_WHEEL_BALANCE_SUCCESS_DEFINITION,
    TwoWheelBalanceTaskDefinition, TwoWheelBalanceObservationBuilder)

ENTITY = 'two-wheel-balance-v1'
NAMES = ('chassis_pitch', 'left_wheel_hinge', 'right_wheel_hinge')
JOINTS = tuple(f'{ENTITY}/{name}' for name in NAMES)
WRITER = 'two-wheel-direct-effort'
FRAMES = ('balance_anchor', 'balance_chassis', 'left_wheel', 'right_wheel')
ACTUATORS = ('left_wheel_torque', 'right_wheel_torque')


def _scene():
    identity = PoseWorld((0., 0., 0.), (1., 0., 0., 0.))
    asset = AssetDefinition('asset-definition-v1', 'two-wheel-inline', 'v1',
        'inline://task-env/two-wheel-balance', source_content_sha256=hashlib.sha256(
            TWO_WHEEL_BALANCE_MJCF_XML.encode()).hexdigest())
    entity = EntityInstance('entity-instance-v1', ENTITY, asset.asset_id, asset.asset_version)
    frames = tuple(FrameDefinition('frame-definition-v1', ENTITY, name, 'runtime', None, None)
                   for name in FRAMES)
    refs = tuple(FrameReference(ENTITY, name) for name in FRAMES)
    offsets = (identity, PoseWorld((-.22, 0., 0.), (1., 0., 0., 0.)),
               PoseWorld((.22, 0., 0.), (1., 0., 0., 0.)))
    joints = tuple(JointDefinition('joint-definition-v1', name, refs[parent], refs[child],
        offset, identity, 'revolute', (0., 1., 0.), 'radian', 'radian_per_second', 1, 1)
        for name, parent, child, offset in zip(NAMES, (0, 1, 1), (1, 2, 3), offsets, strict=True))
    articulation = ArticulationDefinition('articulation-definition-v1', ENTITY, FRAMES[0], FRAMES, joints)
    actuators = tuple(ActuatorResourceDefinition('actuator-resource-v1', ENTITY, a) for a in ACTUATORS)
    group = ControlGroup('control-group-v1', ENTITY, 'wheel-drive',
        tuple(ActuatorReference(ENTITY, a) for a in ACTUATORS))
    return SceneDefinition('scene-definition-v3', 'two-wheel-inline-scene-v1', (asset,),
        (entity,), frames, (articulation,), (RobotInstance('robot-instance-v1', ENTITY, (refs[0],)),), actuators, (group,))


def _declaration(scene):
    entity = EntityDefinition(ENTITY, 'embodiment', 'inline://task-env/two-wheel-balance',
        tuple(f'{ENTITY}/{f}' for f in FRAMES), JOINTS, 'source_owned', 'source_owned', {})
    init = InitializationContract('initialization-v0', {}, {j: 0. for j in JOINTS}, (), 'clear', 'source', 0)
    semantics = SemanticDefinition('semantics-v0', 'two-wheel-task-definition-v1', (), JOINTS,
                                   {}, TWO_WHEEL_BALANCE_SUCCESS_DEFINITION)
    decl = TaskArtifactDeclarationV1('two-wheel-physical-v1', TWO_WHEEL_BALANCE_TASK_UID, 'v1', (entity,),
        ActionIntent('direct_joint_effort', None, 'none', 'joint_effort'), ('joint_state',), init, semantics,
        Timebase(.002, 25, .05), ('articulated_robot', 'joint_state_query'))
    task_source = TaskSourceV1(TWO_WHEEL_BALANCE_TASK_UID, 'v1', scene.scene_id, (), None)
    return task_source, decl.compile_v1(task_source, scene)


def sample_reset(rng):
    return (float(rng.uniform(-.08, .08)), float(rng.uniform(-.20, .20)),
            float(rng.uniform(-.02, .02)), float(rng.uniform(-.02, .02)),
            float(rng.uniform(-.30, .30)), float(rng.uniform(-.30, .30)))


def _reset_plan(artifact, source, seed, sampled):
    pitch, pitch_rate, left, right, left_rate, right_rate = sampled
    row = json.dumps([float(x) for x in sampled], separators=(',', ':')).encode()
    sample = ResetSampleV1.create(schema_version='reset-sample-v1', task_artifact_hash=artifact.identity_hash,
        source_id=source.source_id, source_closure_digest=source.source_closure_digest,
        sampler_id='two-wheel-uniform-perturbation', sampler_version='v1', task_seed=seed,
        init_row_index=0, init_row_sha256=hashlib.sha256(row).hexdigest(),
        joint_position=dict(zip(JOINTS, (pitch, left, right), strict=True)),
        joint_velocity=dict(zip(JOINTS, (pitch_rate, left_rate, right_rate), strict=True)),
        sampled_poses_world={}, poses_world={}, free_joint_velocity={},
        free_joint_velocity_frame='mujoco_world_linear_local_angular_v1', fixture_pose_world={},
        simulation_time_s=0., velocity_policy='named_qvel_and_free_joint_qvel_v1',
        control_policy='named_physical_effort_by_source_v1', initialization_order=(
            'sample_source_properties', 'native_preprocess', 'sample_task_placements',
            'restore_source_bound_state', 'forward_derived_state'), settle_steps=0)
    return ResetPlanV1('reset-plan-v1', sample, 'task_episode')


def _build(config, seed, sampled=None):
    import xml.etree.ElementTree as ET
    scene = _scene(); task_source, artifact = _declaration(scene)
    xml = ET.fromstring(TWO_WHEEL_BALANCE_MJCF_XML); section = xml.find('./actuator')
    motors = xml.findall('./actuator/motor')
    if section is None or len(section) != 2 or len(motors) != 2:
        raise ValueError('two-wheel source requires exactly two motors')
    for motor, actuator, joint in zip(motors, ACTUATORS, NAMES[1:], strict=True):
        if (motor.get('name'), motor.get('joint'), motor.get('gear'), motor.get('ctrllimited'), motor.get('ctrlrange')) != (actuator, joint, '1', 'true', '-1.5 1.5'):
            raise ValueError('two-wheel source motor transmission differs from declaration')
    base = Path(__file__).resolve().parent
    projected = project_scene_definition_v3_to_mjcf(TWO_WHEEL_BALANCE_MJCF_XML, scene)
    closure = _source_closure_digest({'scene.xml': projected.encode(), **source_asset_bytes(base, projected)})
    composition = TaskCompositionSpec(TWO_WHEEL_BALANCE_TASK_UID, TWO_WHEEL_BALANCE_SCENE_UID,
                                      success_definition=TWO_WHEEL_BALANCE_SUCCESS_DEFINITION)
    source = compile_reference_source(artifact=artifact,
        scene_source=TaskSceneSource(TWO_WHEEL_BALANCE_MJCF_XML, base, f'scene-definition-v3:{scene.identity_hash}'),
        composition=composition, config=config, joints=dict(zip(JOINTS, NAMES, strict=True)),
        bodies={f'{ENTITY}/{name}': name for name in FRAMES}, frames={}, free_joints={},
        joint_targets={}, open_actuators=(), scene_definition=scene, source_closure_digest=closure,
        torque_actuators=dict(zip(JOINTS[1:], ACTUATORS, strict=True)),
        actuator_units={a: 'N*m' for a in ACTUATORS})
    controlled_entity = TwoWheelBalanceEntity()
    subject, declarations = controlled_entity.physical_subject_declaration(source_id=source.source_id,
        source_closure_sha256=closure, entity_id=ENTITY, root_frame=FRAMES[0],
        controller_writer=WRITER, component_paths=(('left',), ('right',)))
    pin = LogicalAssemblyScenePinV1('logical-assembly-scene-pin-v1', scene.scene_id, scene.schema_version, scene.identity_hash)
    assembly = LogicalAssemblyV1('logical-assembly-v1', 'two-wheel-source-assembly', 'v1', pin, (
        LogicalAssemblyEntityMemberV1('entity_member', ('owner',), ENTITY, 'two-wheel-inline', 'v1'),
        *(LogicalAssemblySubcomponentReferenceV1('existing_entity_subcomponent_ref', path, 'joint', JointReference(ENTITY, name))
          for path, name in zip((('left',), ('right',)), NAMES[1:], strict=True))))
    compiled = compile_declared_subject_binding(scene, artifact.identity_hash, source.source_id, closure,
                                                assembly, {}, (subject,), declarations)
    controller = controlled_entity.default_controller.bind(subject, compiled.binding,
                                                           writer_id=WRITER, units=('N*m', 'N*m'))
    requirements = StateRequirements('state-requirements-v1', 'controller', WRITER, tuple(
        StateFieldRequirement('state-field-requirement-v1', field, 'joint', ENTITY, name,
            'required', 'evaluation_boundary', 'joint-definition', 'joint_state_query')
        for name in NAMES for field in ('joint_position', 'joint_velocity')))
    physical = PhysicalControlExecutionV1(compiled, (controller,), scene,
        dict(zip(JOINTS, scene.articulations[0].joints, strict=True)),
        {name: FrameReference(ENTITY, name.split('/', 1)[1]) for name in source.bodies},
        requirements, 1, (subject,))
    physical.validate_source(scene=scene, artifact_sha256=artifact.identity_hash, source_id=source.source_id,
                             source_closure_sha256=closure, source=source)
    return {'artifact': artifact, 'task_source': task_source, 'source': source, 'controller': controller,
        'solution': None, 'physical_execution': physical,
        'reset_plan': _reset_plan(artifact, source, seed, sampled if sampled is not None else sample_reset(np.random.default_rng(seed))),
        'construction_id': 'two-wheel-shared-physical-v1', 'source_revision': 'two-wheel-inline-v1',
        'source_sha256': {'original': hashlib.sha256(TWO_WHEEL_BALANCE_MJCF_XML.encode()).hexdigest(), 'projected_closure': closure},
        'resolved_configuration': {'physics_dt': .002, 'control_substeps': 25}}


def _observation_spaces(_env):
    return {'state': Dict({'proprioception': Box(-np.inf, np.inf, (7,), dtype=np.float32)})}


def _observe(env, state):
    snapshot = RuntimeSnapshot(qpos=np.asarray([state.joint_position[j] for j in JOINTS], dtype=np.float32),
        qvel=np.asarray([state.joint_velocity[j] for j in JOINTS], dtype=np.float32), simulation_time=state.simulation_time)
    definition = env._two_wheel_task_definition
    evaluation = definition.reset(snapshot) if state.control_step == 0 else definition.evaluate(
        state=snapshot, action=env.controller.last_action, elapsed_steps=state.control_step)
    observation = definition.build_observation(snapshot)
    info = {'is_success': evaluation.success, 'task_failure': evaluation.failure,
        'task_metrics': dict(evaluation.metrics), 'reward_terms': dict(evaluation.reward_terms),
        'task_reward': evaluation.reward, 'elapsed_steps': state.control_step,
        'simulation_time_s': state.simulation_time, 'external_action': env.controller.last_action.copy(),
        'universal_action': env.controller.last_action.copy(), 'success_definition': TWO_WHEEL_BALANCE_SUCCESS_DEFINITION,
        'observation_schema': env._two_wheel_observation_schema}
    return observation, info, evaluation


def build_two_wheel_environment(environment_type, config, *, provider, backend, render_mode=None,
                                task_rgb_camera=None, task_renderer=None):
    if (provider, backend) not in {('geophys', 'cpu'), ('mujoco', 'cpu')}:
        raise ValueError('two-wheel physical route requires a CPU physics provider')
    if render_mode not in (None, 'human', 'rgb_array') or (render_mode == 'rgb_array' and provider != 'geophys'):
        raise ValueError('two-wheel admits human construction or GeoPhys CPU rgb_array')
    if render_mode == 'rgb_array' and config.render.backend not in {'raytracer', 'rasterizer'}:
        raise ValueError('two-wheel observer requires a GeoPhys renderer')
    if config.render.camera_obs and provider != 'geophys':
        raise ValueError('legacy camera observations require GeoPhys CPU')
    if (config.runtime.physics_dt, config.runtime.control_substeps, config.runtime.backend) != (.002, 25, backend):
        raise ValueError('two-wheel requires its original 25 by 2 ms CPU timebase')
    if (task_rgb_camera is None) != (task_renderer is None):
        raise ValueError('task RGB camera and fixed renderer must be supplied together')
    if task_rgb_camera is not None:
        from ..environment.config import CameraSpec
        if (not isinstance(task_rgb_camera, CameraSpec) or task_rgb_camera.frame != 'world'
                or not np.isfinite((task_rgb_camera.fov_y, task_rgb_camera.near, task_rgb_camera.far)).all()):
            raise ValueError('two-wheel task RGB requires a finite world CameraSpec')
    pending = {}
    def build_seeded(_provider, _backend, seed, _horizon):
        return _build(config, seed, pending.get('sampled'))
    def reset_seed(seed):
        if type(seed) is not int or seed < 0: raise ValueError('seed must be a nonnegative integer')
        return seed
    binding = ReferenceTaskBinding(build=lambda _provider: _build(config, 31), build_seeded=build_seeded,
        reset_sample=lambda _artifact, _seed: None, evaluate=lambda _state, _semantics: None,
        object_poses=(), external_actions=True, interval_mode='grouped', recorder_mode='execution',
        reset_seed=reset_seed, action_schema={'schema_id': 'task-env.two-wheel-balance.wheel-torque.v1',
            'schema_version': 'task-env-action-v1', 'mode': 'direct_wheel_torque',
            'components': ['left_wheel_torque', 'right_wheel_torque'], 'low': -1.5, 'high': 1.5, 'unit': 'N*m'},
        action_space_factory=lambda: Dict({'torque': Box(-1.5, 1.5, (2,), dtype=np.float32)}),
        prepare_action=lambda value: value, observation_space_factory=_observation_spaces, observation_projection=_observe,
        physical_control_profile=lambda env: env.value['physical_execution'], physical_direct_effort_feedback=True,
        physical_terminate_on_success=True,
        physical_ignore_done=config.episode.ignore_done)
    env = environment_type(provider=provider, backend=backend, horizon=config.episode.horizon, _binding=binding)
    env.config = config
    from ..environment.reference_env import build_stage0_metadata
    from dataclasses import replace
    env._env_metadata = replace(build_stage0_metadata(env.uid, config), external_action=TWO_WHEEL_ACTION_CONTRACT,
                                physics_engine='GeoPhys' if provider == 'geophys' else 'MuJoCo',
                                camera_specs=((task_rgb_camera,) if task_rgb_camera is not None else config.render.cameras))
    env._two_wheel_pending_reset = pending
    ids = {'pitch': (0, 0), 'left': (1, 1), 'right': (2, 2)}
    env._two_wheel_task_definition = TwoWheelBalanceTaskDefinition(0, 0, 1, 1, 2, 2)
    env._two_wheel_observation_schema = TwoWheelBalanceObservationBuilder(joint_ids=ids).schema
    env.metadata['reference_profile'] = env.reference_profile()
    env._legacy_camera_observations = bool(config.render.camera_obs)
    if render_mode == 'human':
        env.render_mode = render_mode
        env._human_display_unavailable = True
        env.metadata.update(render_modes=['human', 'rgb_array'] if provider == 'geophys' else ['human'],
                            render_mode=render_mode, human_display_available=False)
    elif render_mode == 'rgb_array':
        env.render_mode = render_mode
        env._legacy_observer_requested = True
        env.metadata.update(render_modes=['human', 'rgb_array'], render_mode=render_mode,
                            human_display_available=False, render_backend=config.render.backend,
                            render_resolution=(config.render.width, config.render.height))
    if task_rgb_camera is not None:
        from ..observations.canonical_camera.contracts import CameraGeometry, MOUNT_FROM_CAMERA
        c = task_rgb_camera
        w, x, y, z = c.quaternion_wxyz
        norm = (w*w+x*x+y*y+z*z)**.5
        if not np.isfinite(norm) or norm < 1e-12:
            env.close()
            raise ValueError('camera quaternion must be finite and nonzero')
        w, x, y, z = (v/norm for v in (w, x, y, z))
        transform = ((1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w), c.position[0]),
                     (2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w), c.position[1]),
                     (2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y), c.position[2]),
                     (0., 0., 0., 1.))
        camera = CameraGeometry('camera-observation-v0', env.artifact.identity_hash, c.name, 'world',
            transform, MOUNT_FROM_CAMERA, c.width, c.height, c.fov_y, c.near, c.far,
            c.rgb, c.depth, c.rgb_layout, c.rgb_dtype)
        try:
            env._configure_task_rgb(camera, task_renderer)
            env._two_wheel_camera_spec = c
        except BaseException:
            env.close()
            raise
    return env
