"""Pendulum's source-bound declaration for the shared physical RuntimeSession."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from ..artifacts import (ActionIntent, ActuatorResourceDefinition, ArticulationDefinition,
    AssetDefinition, ControlGroup, EntityDefinition, EntityInstance, FrameDefinition,
    FrameReference, InitializationContract, JointDefinition, JointReference, PoseWorld,
    RobotInstance, SceneDefinition, SemanticDefinition, Timebase)
from ..artifacts.logical_assembly import (LogicalAssemblyV1, LogicalAssemblyScenePinV1,
    LogicalAssemblyEntityMemberV1, LogicalAssemblySubcomponentReferenceV1)
from ..artifacts.state import StateFieldRequirement, StateRequirements
from ..artifacts.execution import ResetSampleV1, ResetPlanV1
from ..artifacts import ExecutionSpecV1, RendererSelectionV1
from ..assembly.assets import _source_closure_digest
from ..assembly.compiler import compile_reference_source
from ..assembly.source import TaskSceneSource
from ..environment.task_source import TaskSourceV1, TaskArtifactDeclarationV1
from ..environment.types import TaskCompositionSpec, RuntimeSnapshot
from ..environment.reference_binding import ReferenceTaskBinding
from ..environment.gym_compat import Box, Dict
from ..robots.pendulum import PendulumEntity, PENDULUM_ACTION_CONTRACT
from ..runtime.sessions.physical_control import PhysicalControlExecutionV1, compile_declared_subject_binding
from ..runtime.sessions.source import project_scene_definition_v3_to_mjcf, source_asset_bytes
from ..runtime.sessions.isaac_g05 import (
    G05_ISAAC_EFFORT_PROFILE, build_g05_isaac_runtime_source,
    ensure_g05_isaac_app_open, load_g05_isaac_delivery,
)
from .pendulum import (PENDULUM_MJCF_XML, PENDULUM_TASK_UID, PENDULUM_SCENE_UID,
                       PENDULUM_SUCCESS_DEFINITION, PendulumTaskDefinition,
                       PendulumObservationBuilder, PENDULUM_TASK_SEMANTICS)

ENTITY = 'pendulum-v1'
JOINT = f'{ENTITY}/pendulum_hinge'
WRITER = 'pendulum-direct-effort'


def _scene(*, source_revision=None):
    origin = PoseWorld((0., 0., 0.), (1., 0., 0., 0.))
    source_hash = hashlib.sha256(PENDULUM_MJCF_XML.encode()).hexdigest()
    asset = AssetDefinition('asset-definition-v1', 'pendulum-inline', 'v1',
                            'inline://task-env/pendulum', source_revision=source_revision,
                            source_content_sha256=source_hash)
    entity = EntityInstance('entity-instance-v1', ENTITY, asset.asset_id, asset.asset_version)
    frames = tuple(FrameDefinition('frame-definition-v1', ENTITY, name, 'runtime', None, None)
                   for name in ('pendulum_anchor', 'pendulum_link'))
    root, link = (FrameReference(ENTITY, name) for name in ('pendulum_anchor', 'pendulum_link'))
    joint = JointDefinition('joint-definition-v1', 'pendulum_hinge', root, link,
                            origin, origin, 'revolute', (0., 1., 0.),
                            'radian', 'radian_per_second', 1, 1)
    articulation = ArticulationDefinition('articulation-definition-v1', ENTITY, 'pendulum_anchor',
        ('pendulum_anchor', 'pendulum_link'), (joint,))
    actuator = ActuatorResourceDefinition('actuator-resource-v1', ENTITY, 'pendulum_torque')
    from ..artifacts import ActuatorReference
    group = ControlGroup('control-group-v1', ENTITY, 'hinge-drive',
                         (ActuatorReference(ENTITY, 'pendulum_torque'),))
    return SceneDefinition('scene-definition-v3', 'pendulum-inline-scene-v1', (asset,), (entity,),
        frames, (articulation,), (RobotInstance('robot-instance-v1', ENTITY, (root,)),),
        (actuator,), (group,))


def _declaration(scene):
    entity = EntityDefinition(ENTITY, 'embodiment', 'inline://task-env/pendulum',
        ('pendulum-v1/pendulum_anchor', 'pendulum-v1/pendulum_link'), (JOINT,),
        'source_owned', 'source_owned', {})
    init = InitializationContract('initialization-v0', {}, {JOINT: 0.}, (), 'clear', 'source', 0)
    semantics = SemanticDefinition('semantics-v0', 'pendulum-task-definition-v1', (), (JOINT,),
                                   {}, PENDULUM_SUCCESS_DEFINITION)
    decl = TaskArtifactDeclarationV1('pendulum-physical-v1', PENDULUM_TASK_UID, 'v1', (entity,),
        ActionIntent('direct_joint_effort', None, 'none', 'joint_effort'), ('joint_state',),
        init, semantics, Timebase(.002, 25, .05), ('articulated_robot', 'joint_state_query'))
    source = TaskSourceV1(PENDULUM_TASK_UID, 'v1', scene.scene_id, (), None)
    artifact = decl.compile_v1(source, scene)
    return source, artifact


def _reset_plan(artifact, source, seed, sampled=None):
    angle, speed = (PENDULUM_TASK_SEMANTICS.sample_reset(np.random.default_rng(seed))
                    if sampled is None else sampled)
    row = json.dumps([float(angle), float(speed)], separators=(',', ':')).encode()
    sample = ResetSampleV1.create(schema_version='reset-sample-v1',
        task_artifact_hash=artifact.identity_hash, source_id=source.source_id,
        source_closure_digest=source.source_closure_digest,
        sampler_id='pendulum-uniform-angle-velocity', sampler_version='v1', task_seed=seed,
        init_row_index=0, init_row_sha256=hashlib.sha256(row).hexdigest(),
        joint_position={JOINT: float(angle)}, joint_velocity={JOINT: float(speed)},
        sampled_poses_world={}, poses_world={}, free_joint_velocity={},
        free_joint_velocity_frame='mujoco_world_linear_local_angular_v1', fixture_pose_world={},
        simulation_time_s=0., velocity_policy='named_qvel_and_free_joint_qvel_v1',
        control_policy='named_physical_effort_by_source_v1', initialization_order=(
            'sample_source_properties', 'native_preprocess', 'sample_task_placements',
            'restore_source_bound_state', 'forward_derived_state'), settle_steps=0)
    return ResetPlanV1('reset-plan-v1', sample, 'task_episode')


def _build(config, seed, sampled=None, *, provider='geophys', source_delivery_manifest=None):
    import xml.etree.ElementTree as ET
    isaac_loaded = None
    if provider == 'isaacsim':
        if source_delivery_manifest is None:
            raise ValueError('Pendulum Isaac requires its explicit source_delivery_manifest')
        isaac_loaded = load_g05_isaac_delivery(source_delivery_manifest)
        source_revision = isaac_loaded.delivery.asset_definition.source_revision
    else:
        source_revision = None
    scene = _scene(source_revision=source_revision)
    task_source, artifact = _declaration(scene)
    # Validate exact task-owned motor semantics before creating any provider.
    root_xml = ET.fromstring(PENDULUM_MJCF_XML)
    motors = root_xml.findall('./actuator/motor')
    actuator_section = root_xml.find('./actuator')
    if (actuator_section is None or len(actuator_section) != 1 or len(motors) != 1
            or motors[0].get('name') != 'pendulum_torque'
            or motors[0].get('joint') != 'pendulum_hinge'
            or motors[0].get('gear') != '1' or motors[0].get('ctrllimited') != 'true'
            or motors[0].get('ctrlrange') != '-2 2'):
        raise ValueError('source does not declare the expected single unit-gear motor')
    base = Path(__file__).resolve().parent
    projected = project_scene_definition_v3_to_mjcf(PENDULUM_MJCF_XML, scene)
    closure = _source_closure_digest({'scene.xml': projected.encode(), **source_asset_bytes(base, projected)})
    composition = TaskCompositionSpec(PENDULUM_TASK_UID, PENDULUM_SCENE_UID,
                                      success_definition=PENDULUM_SUCCESS_DEFINITION)
    if provider == 'isaacsim':
        source = build_g05_isaac_runtime_source(
            manifest_path=source_delivery_manifest, artifact=artifact, scene=scene,
            task_source_identity_sha256=task_source.identity_hash,
            joints={JOINT: 'pendulum_hinge'},
            bodies={'pendulum-v1/pendulum_anchor': 'Geometry/pendulum_anchor',
                    'pendulum-v1/pendulum_link': 'Geometry/pendulum_anchor/pendulum_link'},
            frames={}, free_joints={}, joint_targets={JOINT: 'pendulum_hinge'},
        )
        closure = source.source_closure_digest
        execution_spec = ExecutionSpecV1(
            'execution-spec-v1', 'isaacsim', 'cuda', G05_ISAAC_EFFORT_PROFILE,
            seed, 'best_effort',
            RendererSelectionV1('renderer-selection-v1', 'none', 'cpu', 'none', None),
            physics_device='cuda:0', camera_overrides=(),
        )
    else:
        source = compile_reference_source(artifact=artifact,
            scene_source=TaskSceneSource(PENDULUM_MJCF_XML, base, f'scene-definition-v3:{scene.identity_hash}'),
            composition=composition, config=config, joints={JOINT: 'pendulum_hinge'},
            bodies={'pendulum-v1/pendulum_anchor': 'pendulum_anchor',
                    'pendulum-v1/pendulum_link': 'pendulum_link'}, frames={},
            free_joints={}, joint_targets={}, open_actuators=(), scene_definition=scene,
            source_closure_digest=closure, torque_actuators={JOINT: 'pendulum_torque'},
            actuator_units={'pendulum_torque': 'N*m'})
        execution_spec = None
    controlled_entity = PendulumEntity()
    subject, declarations = controlled_entity.physical_subject_declaration(source_id=source.source_id,
        source_closure_sha256=closure, entity_id=ENTITY, root_frame='pendulum_anchor',
        controller_writer=WRITER, component_path=('hinge',))
    pin = LogicalAssemblyScenePinV1('logical-assembly-scene-pin-v1', scene.scene_id,
                                    scene.schema_version, scene.identity_hash)
    assembly = LogicalAssemblyV1('logical-assembly-v1', 'pendulum-source-assembly', 'v1', pin, (
        LogicalAssemblyEntityMemberV1('entity_member', ('owner',), ENTITY, 'pendulum-inline', 'v1'),
        LogicalAssemblySubcomponentReferenceV1('existing_entity_subcomponent_ref', ('hinge',),
                                               'joint', JointReference(ENTITY, 'pendulum_hinge'))))
    compiled = compile_declared_subject_binding(scene, artifact.identity_hash, source.source_id,
                                                closure, assembly, {}, (subject,), declarations)
    selected_profile_id = config.control.profile_id or 'direct_joint_effort_v1'
    controller = subject.select_effort_controller(
        compiled.binding, profile_id=selected_profile_id, writer_id=WRITER,
        units=('N*m',), cadence_s=artifact.timebase.control_dt)
    requirements = StateRequirements('state-requirements-v1', 'controller', WRITER, tuple(
        StateFieldRequirement('state-field-requirement-v1', field, 'joint', ENTITY, 'pendulum_hinge',
            'required', 'evaluation_boundary', 'joint-definition', 'joint_state_query')
        for field in ('joint_position', 'joint_velocity')))
    physical = PhysicalControlExecutionV1(compiled, (controller,), scene,
        {JOINT: scene.articulations[0].joints[0]},
        {name: FrameReference(ENTITY, name.split('/', 1)[1]) for name in source.bodies},
        requirements, 1, (subject,))
    physical.validate_source(scene=scene, artifact_sha256=artifact.identity_hash,
        source_id=source.source_id, source_closure_sha256=closure, source=source)
    return {'artifact': artifact, 'task_source': task_source, 'source': source,
        'controller': controller, 'solution': None, 'physical_execution': physical,
        'reset_plan': _reset_plan(artifact, source, seed, sampled), 'construction_id': 'pendulum-shared-physical-v1',
        'source_revision': scene.assets[0].source_revision or 'pendulum-inline-v1',
        'execution_spec_v1': execution_spec,
        'selected_controller_profile_id': selected_profile_id,
        'source_sha256': {'original': hashlib.sha256(
            PENDULUM_MJCF_XML.encode()).hexdigest(), 'projected_closure': closure},
        'resolved_configuration': {'physics_dt': .002, 'control_substeps': 25}}


def _observation_spaces(_env):
    return {'state': Dict({'proprioception': Box(-np.inf, np.inf, (3,), dtype=np.float32)})}


def _observe(env, state):
    q = np.asarray([state.joint_position[JOINT]], dtype=np.float32)
    v = np.asarray([state.joint_velocity[JOINT]], dtype=np.float32)
    snapshot = RuntimeSnapshot(qpos=q, qvel=v, simulation_time=state.simulation_time)
    definition = env._pendulum_task_definition
    if state.control_step == 0:
        evaluation = definition.reset(snapshot)
    else:
        evaluation = definition.evaluate(state=snapshot, action=env.controller.last_action,
                                         elapsed_steps=state.control_step)
    observation = definition.build_observation(snapshot)
    info = {'is_success': evaluation.success, 'task_failure': evaluation.failure,
            'task_metrics': dict(evaluation.metrics), 'reward_terms': dict(evaluation.reward_terms),
            'task_reward': evaluation.reward, 'elapsed_steps': state.control_step,
            'simulation_time_s': state.simulation_time,
            'external_action': env.controller.last_action.copy(),
            'universal_action': env.controller.last_action.copy(),
            'success_definition': PENDULUM_SUCCESS_DEFINITION,
            'observation_schema': env._pendulum_observation_schema}
    return observation, info, evaluation


def build_pendulum_environment(environment_type, config, *, provider, backend, render_mode=None,
                               task_rgb_camera=None, task_renderer=None,
                               source_delivery_manifest=None):
    if (provider, backend) not in {('geophys', 'cpu'), ('mujoco', 'cpu'), ('isaacsim', 'cuda')}:
        raise ValueError('Pendulum physical route requires GeoPhys/MuJoCo CPU or the admitted Isaac CUDA route')
    if (config.control.profile_id == 'velocity_damped_joint_effort_v1'
            and (provider, backend) != ('mujoco', 'cpu')):
        raise ValueError('velocity-damped Controller is admitted only by the tested MuJoCo CPU source-state model')
    if provider == 'isaacsim' and render_mode is not None:
        raise ValueError('Pendulum G05 Isaac route is state-only and does not admit rendering')
    if render_mode not in (None, 'human', 'rgb_array') or (render_mode == 'rgb_array' and provider != 'geophys'):
        raise ValueError('Pendulum admits human construction or GeoPhys CPU rgb_array')
    if render_mode == 'rgb_array' and config.render.backend not in {'raytracer', 'rasterizer'}:
        raise ValueError('Pendulum shared observer requires a GeoPhys renderer')
    if config.render.camera_obs and provider != 'geophys':
        raise ValueError('legacy camera observations require GeoPhys CPU')
    if (config.runtime.physics_dt, config.runtime.control_substeps, config.runtime.backend) != (.002, 25, backend):
        raise ValueError('Pendulum requires its original 25 by 2 ms CPU timebase')
    if (task_rgb_camera is None) != (task_renderer is None):
        raise ValueError('task RGB camera and fixed renderer must be supplied together')
    if task_rgb_camera is not None:
        from ..environment.config import CameraSpec
        if (not isinstance(task_rgb_camera, CameraSpec) or task_rgb_camera.frame != 'world'
                or not np.isfinite((task_rgb_camera.fov_y, task_rgb_camera.near, task_rgb_camera.far)).all()):
            raise ValueError('Pendulum task RGB requires a finite world CameraSpec')
    if provider == 'isaacsim':
        if source_delivery_manifest is None:
            raise ValueError('Pendulum Isaac requires its explicit source_delivery_manifest')
        # Establish Kit's USD owner before the first _build() can enter the
        # complete Core/USD delivery inspection.  The native adapter later
        # reuses this process singleton; it must not create another App.
        ensure_g05_isaac_app_open()
    pending_reset = {}
    def build_seeded(_provider, _backend, seed, _horizon):
        return _build(config, seed, pending_reset.get('sampled'), provider=provider,
                      source_delivery_manifest=source_delivery_manifest)
    def reset_seed(seed):
        if type(seed) is not int or seed < 0:
            raise ValueError('Pendulum seed must be a nonnegative integer')
        return seed
    def space():
        return Dict({'torque': Box(-2., 2., (1,), dtype=np.float32)})
    binding = ReferenceTaskBinding(build=lambda _provider: _build(
        config, 31, provider=provider, source_delivery_manifest=source_delivery_manifest),
        build_seeded=build_seeded,
        reset_sample=lambda _artifact, _seed: None, evaluate=lambda _state, _semantics: None,
        object_poses=(), external_actions=True, interval_mode='grouped', recorder_mode='execution',
        reset_seed=reset_seed, action_schema={'schema_id': 'task-env.pendulum.torque.v1',
            'schema_version': 'task-env-action-v1', 'mode': 'direct_torque',
            'components': ['torque'], 'low': -2., 'high': 2., 'unit': 'N*m'},
        action_space_factory=space, prepare_action=lambda value: value,
        observation_space_factory=_observation_spaces, observation_projection=_observe,
        physical_control_profile=lambda env: env.value['physical_execution'],
        physical_direct_effort_feedback=(config.control.profile_id in (None, 'direct_joint_effort_v1')),
        physical_terminate_on_success=True,
        physical_ignore_done=config.episode.ignore_done)
    execution_spec = (_build(config, 31, provider=provider,
                             source_delivery_manifest=source_delivery_manifest).get('execution_spec_v1')
                      if provider == 'isaacsim' else None)
    env = environment_type(provider=provider, backend=backend, horizon=config.episode.horizon,
                           _binding=binding, _execution_spec_v1=execution_spec)
    env.config = config
    from ..environment.reference_env import build_stage0_metadata
    from dataclasses import replace
    env._env_metadata = replace(build_stage0_metadata(env.uid, config),
        external_action=PENDULUM_ACTION_CONTRACT,
        physics_engine=('GeoPhys' if provider == 'geophys'
                        else 'Isaac Sim PhysX' if provider == 'isaacsim' else 'MuJoCo'),
        camera_specs=((task_rgb_camera,) if task_rgb_camera is not None else config.render.cameras))
    env._pendulum_pending_reset = pending_reset
    env._pendulum_task_definition = PendulumTaskDefinition(qpos_id=0, qvel_id=0)
    env._pendulum_observation_schema = PendulumObservationBuilder(qpos_id=0, qvel_id=0).schema
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
            env._pendulum_camera_spec = c
        except BaseException:
            env.close()
            raise
    return env
