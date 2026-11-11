"""Source-traced PickCube MJCF physical-control candidate using the selected Env."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from contextlib import ExitStack

from ...registry import register_env
from ...environment.reference_env import SelectedReferenceEnv


PICKCUBE_PHYSICAL_PROFILES = {
    'panda-direct-effort-v1': 'direct',
    'panda-joint-effort-reference-v1': 'joint',
    'panda-r3-effort-reference-v1': 'r3-pose',
    'panda-joint-mass-effort-v1': 'joint-mass',
    'panda-r3-mass-effort-v1': 'r3-mass-pose',
}

# This normalized closure was derived only after the original pinned receipt
# and all of its referenced assets passed the historical source verification.
_PANDA_NORMALIZED_CLOSURE_SHA256 = 'cbb7c0a3a68a5e08161651933aef262d340659c04fefc5825f3b8a4ff319e23f'


def validate_physical_configuration(*, provider, backend, profile, robot_uid, native_drive,
                                    parameters, workspace, gravity_compensation, reset_profile,
                                    source_delivery_manifest, execution_spec, task_parameters, horizon):
    if profile not in PICKCUBE_PHYSICAL_PROFILES:
        if native_drive is not None or parameters or workspace is not None:
            raise ValueError('Robot/Controller/source options require a declared physical profile')
        return
    kind = PICKCUBE_PHYSICAL_PROFILES[profile]
    if execution_spec.deployment != 'in_process':
        raise ValueError('physical profile currently requires explicit in_process execution')
    if (provider, backend) not in {('mujoco', 'cpu'), ('geophys', 'cpu'), ('isaacsim', 'cuda')}:
        raise ValueError('physical control requires an admitted CPU or Isaac CUDA route')
    if robot_uid not in (None, 'panda-v1') or gravity_compensation or reset_profile is not None:
        raise ValueError('physical profile requires its declared Panda source without Position-only options')
    if provider == 'isaacsim':
        if source_delivery_manifest is None or parameters or workspace is not None or task_parameters:
            raise ValueError('Isaac physical control requires its USD delivery without MJCF-only options')
        if horizon > 1000:
            raise ValueError('Isaac physical source horizon must be in [1, 1000]')
    elif source_delivery_manifest is not None:
        raise ValueError('MJCF physical profile does not consume a USD source delivery')
    drive = native_drive or ('position' if kind == 'direct' else 'disabled')
    if kind != 'direct' and drive != 'disabled':
        raise ValueError('reference effort requires the isolated native drive fixture')
    switch = parameters.get('reset_selection', False)
    policy = parameters.get('action_space_policy', 'dynamic')
    if type(switch) is not bool or policy not in {'dynamic', 'fixed_semantic'}:
        raise ValueError('invalid physical reset selection or action-space policy')
    if switch and ((provider, backend) != ('mujoco', 'cpu') or drive != 'disabled'
                   or kind not in {'joint', 'r3-pose'}):
        raise ValueError('physical reset selection requires an isolated MuJoCo reference Controller')
    if not switch and policy != 'dynamic':
        raise ValueError('physical action-space policy requires reset selection')
    if set(task_parameters) - {'cube_force_z_N'}:
        raise ValueError('physical source retains its declared Task parameters; unsupported override')
    if 'cube_force_z_N' in task_parameters and (provider, drive, kind, switch) != (
            'mujoco', 'position', 'direct', False):
        raise ValueError('PickCube Task COM force requires MuJoCo direct coexist control')
    if workspace is not None:
        root = Path(workspace)
        if root.exists() and any(root.iterdir()):
            raise ValueError('physical source_workspace must be fresh or empty')


def physical_binding_from_config(config):
    import json
    options = json.loads(config.controller_parameters_json)
    kind = PICKCUBE_PHYSICAL_PROFILES[config.controller_profile]
    drive = config.native_drive or ('position' if kind == 'direct' else 'disabled')
    if config.physics_provider == 'isaacsim':
        from .physical_isaac_candidate import make_isaac_physical_binding
        return make_isaac_physical_binding(delivery_manifest=config.source_delivery_manifest,
            seed=config.environment.episode.seed if config.environment.episode.seed is not None else 31,
            horizon=config.environment.episode.horizon,
            drive_mode='effort-only' if drive == 'disabled' else 'coexist', control_kind=kind)
    force = dict(config.task_parameters).get('cube_force_z_N')
    return make_physical_binding(root=config.source_workspace, provider=config.physics_provider,
        horizon=config.environment.episode.horizon, seed=config.environment.episode.seed if config.environment.episode.seed is not None else 31,
        drive_mode='effort-only' if drive == 'disabled' else 'coexist', control_kind=kind,
        reset_switch=options.get('reset_selection', False), space_policy=options.get('action_space_policy', 'dynamic'),
        cube_force_z_N=force)


def _physical_pickcube_observation(env, state):
    """Keep the task's source EE site distinct from the Panda hand-origin frame."""
    import numpy as np
    from ...observations.selected_reference import build_selected_observation
    obs, info, _ = build_selected_observation(env, state)
    ee = state.pose_world['panda-v1/ee']
    obs['state']['ee_pose'] = np.asarray((*ee.position, *ee.quaternion_wxyz), dtype=np.float32)
    from ...environment.reference_binding import evaluate_task_definition
    evaluation = evaluate_task_definition(env, state)
    info.update(is_success=bool(evaluation.success), task_failure=bool(evaluation.failure),
                task_metrics=dict(evaluation.metrics))
    return obs, info, evaluation


def _direct_physical_observation_spaces(env):
    """PickCube's existing single-Panda state shape, declared by the task."""
    from collections import OrderedDict
    import numpy as np
    from ...environment.gym_compat import Box, Dict
    return OrderedDict((
        ('state', Dict({
            'ee_pose': Box(-np.inf, np.inf, (7,), dtype=np.float32),
            'joint_position': Box(-np.inf, np.inf, (9,), dtype=np.float32),
            'hand_pose': Box(-np.inf, np.inf, (7,), dtype=np.float32),
            'boundary_identity_sha256': Box(0, 255, (32,), dtype=np.uint8),
        })),
        ('privileged_state', Dict({'cube_v1_body_pose': Box(-np.inf, np.inf, (1, 7), dtype=np.float32)})),
    ))


def _direct_physical_observation(env, state):
    """Project the physical publication without requiring a Position controller."""
    import numpy as np
    from ...artifacts import CanonicalStateView
    view = env.typed_state.view
    joints = {v.joint_id: v for v in view.joints if v.entity_id == 'panda-v1'}
    names = tuple(f'joint{i}' for i in range(1, 8)) + ('finger_joint1', 'finger_joint2')
    if any(name not in joints for name in names):
        raise ValueError('PickCube observation requires its named Panda joints')
    hands = [v for v in view.frames if v.frame.entity_id == 'panda-v1' and v.frame.frame_id == 'hand']
    if len(hands) != 1:
        raise ValueError('PickCube observation requires one hand frame')
    hand = hands[0].pose_world
    adapted = CanonicalStateView(
        schema_version='canonical-state-v0', convention=state.convention,
        control_step=state.control_step, simulation_time=state.simulation_time,
        joint_position={**state.joint_position, **{f'panda-v1/{n}': float(joints[n].position[0]) for n in names}},
        joint_velocity={**state.joint_velocity, **{f'panda-v1/{n}': float(joints[n].velocity[0]) for n in names}},
        pose_world=dict(state.pose_world),
    )
    from ...environment.reference_binding import evaluate_task_definition
    evaluation = evaluate_task_definition(env, adapted)
    site = state.pose_world['panda-v1/ee']
    pose = np.asarray((*site.position, *site.quaternion_wxyz), dtype=np.float32)
    hand_pose = np.asarray((*hand.position, *hand.quaternion_wxyz), dtype=np.float32)
    cube = state.pose_world['cube-v1']
    boundary = view.boundary
    obs = {'state': {'ee_pose': pose.copy(),
                     'joint_position': np.asarray([joints[n].position[0] for n in names], dtype=np.float32),
                     'hand_pose': hand_pose,
                     'boundary_identity_sha256': np.frombuffer(bytes.fromhex(
                         boundary.boundary_id.removeprefix('state-boundary-')), dtype=np.uint8).copy()},
           'privileged_state': {'cube_v1_body_pose': np.asarray(
               [(*cube.position, *cube.quaternion_wxyz)], dtype=np.float32)}}
    info = {'is_success': bool(evaluation.success), 'task_failure': bool(evaluation.failure),
            'task_metrics': dict(evaluation.metrics), 'control_step': int(state.control_step),
            'simulation_time_s': float(state.simulation_time),
            'state_boundary_identity': boundary.to_mapping(), 'state_boundary_id': boundary.boundary_id,
            'state_sample_clock': view.sample_clock.to_mapping()}
    return obs, info, evaluation


@register_env()
class PickCubePhysicalCandidateEnv(SelectedReferenceEnv):
    """Position compatibility plus typed physical control for PickCube MJCF."""
    uid = 'pickcube-physical-candidate-v1'
    task_rgb_factory_prepares_runtime = True

    @classmethod
    def from_reference_config(cls, config=None, *, render_mode=None, **kwargs):
        """Translate the historical UID/input; only the formal factory builds Env."""
        from .specialization import PickCubeReferenceEnv
        from ...render.base.contracts import validate_camera_declarations
        validate_camera_declarations(render_mode=render_mode, **{
            name: kwargs.get(name) for name in ('observer_camera', 'task_camera', 'task_rgb_camera', 'task_renderer')})
        values = {} if config is None else dict(config)
        allowed = {'provider', 'backend', 'horizon', 'source_workspace', 'seed', 'drive_mode',
                   'control_kind', 'reset_switch', 'action_space_policy', 'cube_force_z_N'}
        if set(values) - allowed:
            raise ValueError('PickCube physical candidate rejects unsupported configuration')
        workspace = values.get('source_workspace')
        if not isinstance(workspace, (str, Path)) or not str(workspace):
            raise ValueError('legacy physical candidate requires a fresh source_workspace')
        drive = values.get('drive_mode', 'coexist')
        profiles = {kind: profile for profile, kind in PICKCUBE_PHYSICAL_PROFILES.items()}
        if drive not in {'coexist', 'effort-only'} or values.get('control_kind', 'direct') not in profiles:
            raise ValueError('unsupported physical drive or controller mode')
        import sys
        provider, backend = values.get('provider', 'mujoco'), values.get('backend', 'cpu')
        task = {} if 'cube_force_z_N' not in values else {'cube_force_z_N': values['cube_force_z_N']}
        public = {'execution': {'physics_provider': provider, 'physics_backend': backend,
                               'physics_device': 'cpu', 'source_workspace': str(workspace),
                               'deployment': 'in_process', 'interpreter': sys.executable},
                  'episode': {'horizon': values.get('horizon', 8), 'seed': values.get('seed', 31)},
                  'controller': {'profile_id': profiles[values.get('control_kind', 'direct')],
                      'parameters': {'reset_selection': values.get('reset_switch', False),
                                     'action_space_policy': values.get('action_space_policy', 'dynamic')}},
                  'robot': {'native_drive': 'position' if drive == 'coexist' else 'disabled'}, 'task': task}
        return PickCubeReferenceEnv.from_reference_config(public, render_mode=render_mode, **kwargs)


def _pickcube_mjcf_scene(task_config):
    """Bind the authored MJCF names to the existing PickCube/Panda Scene owner."""
    from ...artifacts import SceneDefinition
    from ...registry import AGENT_REGISTRY
    from ...runtime.sessions.mujoco_composition import declare_panda_scene
    from .specialization import build_pickcube_isaac_scene
    scene = build_pickcube_isaac_scene(task_config)
    mapping = scene.to_mapping()
    panda = declare_panda_scene(AGENT_REGISTRY.create('panda-v1'),
                                entity_id='panda-v1', scene_id=scene.scene_id)
    mapping['assets'] = [panda.assets[0].to_mapping()
        if asset['asset_id'] == 'f05-dg03-menagerie-panda-source-preserving-isaac-usd' else asset
        for asset in mapping['assets']]
    for entity in mapping['entities']:
        if entity['entity_id'] == 'panda-v1':
            entity['asset_id'], entity['asset_version'] = panda.entities[0].asset_id, panda.entities[0].asset_version
    for frame in mapping['frames']:
        key = (frame['entity_id'], frame['frame_id'])
        frame['frame_id'] = {('cube-v1', 'cube'): 'PickCube', ('tabletop-v1', 'top'): 'grasp_table',
                             ('panda-v1', 'ee'): 'nutassembly_ee_site'}.get(key, frame['frame_id'])
    for articulation in mapping['articulations']:
        if articulation['entity_id'] == 'cube-v1':
            articulation['link_frame_ids'] = ['world', 'PickCube']
            joint = articulation['joints'][0]
            joint['joint_id'], joint['child_frame']['frame_id'] = 'PickCube_joint', 'PickCube'
    return SceneDefinition.from_mapping(mapping)


def make_physical_binding(*, root=None, provider, horizon, seed, drive_mode, control_kind,
                          reset_switch=False, space_policy='dynamic', cube_force_z_N=None):
    """Declare task/source/control bindings; the shared factory constructs Env."""
    from ...artifacts import FrameReference
    from ...controllers.canonical.position_profile import PandaPositionServoProfileV1
    from ...controllers.canonical.contracts import reference_pose_action
    from ...environment import adapt_legacy_recipe_task_source, compile_task_artifact_v1, sample_episode_reset_plan
    from ...environment.task_definition import as_task_state_view
    from ...environment.reference_binding import ReferenceTaskBinding, legacy_position_physical_observation_binding
    from ...observations.selected_reference import selected_reference_observation_spaces
    from ...runtime.sessions.control import ControlBinding, compile_control_binding_plan
    from ...robots.panda import build_panda_direct_effort_execution
    from .specialization import _configuration, build_reference, evaluate
    from .task import PickCubeTaskDefinition

    task_config = _configuration()
    base = build_reference(backend='cpu', include_solution=False, controller_profile='r3_continuous_v1')
    original, legacy_artifact = base['source'], base['artifact']
    # The force-observation fixture starts inside the paired finger limits;
    # it retains PickCube semantics and is a distinct Artifact identity.
    if not reset_switch:
        joint_initial = dict(legacy_artifact.initialization.joint_position)
        joint_initial.update({'panda-v1/finger_joint1': 0.02, 'panda-v1/finger_joint2': 0.02})
        legacy_artifact = replace(legacy_artifact,
            initialization=replace(legacy_artifact.initialization, joint_position=joint_initial))
    if drive_mode == 'effort-only':
        legacy_artifact = replace(legacy_artifact,
            artifact_id=('pickcube-mjcf-physical-effort-task-v1' if reset_switch
                         else 'pickcube-mjcf-physical-effort-no-drive-v1'),
            initialization=replace(legacy_artifact.initialization,
                                   reset_validity=('mjcf-physical-effort-task-v1' if reset_switch
                                                   else 'mjcf-physical-effort-no-drive-v1')))
    receipt = original.execution_source_receipt
    with ExitStack() as resources:
        resources.callback(receipt.close)
        from ...runtime.sessions.source import matches_relocated_source_closure
        from ...utils._paths import MUJOCO_MENAGERIE_ROOT
        if not matches_relocated_source_closure(
                receipt, original.source_closure_digest,
                asset_root=MUJOCO_MENAGERIE_ROOT / 'franka_emika_panda' / 'assets',
                normalized_digest=_PANDA_NORMALIZED_CLOSURE_SHA256):
            raise ValueError('PickCube physical candidate requires the exact original MJCF closure')
        scene = _pickcube_mjcf_scene(task_config)
        task_source = adapt_legacy_recipe_task_source({'recipe': task_config['recipe'], 'environment': task_config['environment']})
        artifact = compile_task_artifact_v1(task_source, scene, legacy_artifact, frame_bindings={
            'panda-v1/base': FrameReference('panda-v1', 'link0'),
            'panda-v1/ee': FrameReference('panda-v1', 'nutassembly_ee_site'),
            'tabletop-v1/top': FrameReference('tabletop-v1', 'grasp_table'),
        })
        frame_aliases = dict(artifact.legacy_frame_bindings)
        frame_aliases['cube-v1'] = FrameReference('cube-v1', 'PickCube')
        for frame in scene.frames or ():
            if frame.entity_id == 'panda-v1' and frame.frame_id != 'nutassembly_ee_site':
                frame_aliases.setdefault(f'panda-v1/{frame.frame_id}', FrameReference('panda-v1', frame.frame_id))
        artifact = replace(artifact, legacy_frame_bindings=frame_aliases)
        artifact.validate_scene(scene)
        bodies = {f'panda-v1/{frame.frame_id}': frame.frame_id for frame in scene.frames or ()
                  if frame.entity_id == 'panda-v1' and frame.frame_id != 'nutassembly_ee_site'}
        bodies.update({'cube-v1': 'PickCube', 'tabletop-v1/top': 'grasp_table'})
        from ...runtime.sessions.mujoco_composition import bind_reference_scene_source
        source, projected, closure = bind_reference_scene_source(original, artifact=artifact,
            scene=scene, bodies=bodies, frames={'panda-v1/ee': 'nutassembly_ee_site'}, workspace=root)
        if root is not None:
            resources.close()
        reset_plan = sample_episode_reset_plan(task_source, scene, artifact, task_seed=seed)
        # GeoPhys and reset-scoped reference controllers retain their existing
        # bounded compatibility route until separately migrated and verified.
        direct_physical = provider == 'mujoco' and control_kind == 'direct' and not reset_switch
        position = (None if direct_physical else
                    PandaPositionServoProfileV1.from_source(artifact, source, entity_id='panda-v1'))
        plan = (None if direct_physical else
                compile_control_binding_plan(scene, (position.controller_binding(),)))
        def build_physical(kind, **parameters):
            if (set(parameters) - {'kp', 'kd', 'finger_kp', 'finger_kd'}
                    or any(type(value) not in (int, float) or not 0. < value <= 5000.
                           for value in parameters.values())):
                raise ValueError('unsupported or invalid physical controller parameters')
            if parameters and not reset_switch:
                raise ValueError('controller parameters require physical reset selection')
            from ...runtime.sessions.mujoco_composition import checked_panda_effort_source_limits
            native_drive = 'disabled' if drive_mode == 'effort-only' else 'position'
            limits = checked_panda_effort_source_limits(source, scene)
            if reset_switch:
                if (artifact.artifact_id != 'pickcube-mjcf-physical-effort-task-v1'
                        or native_drive != 'disabled' or limits[7] != (-5., 5.)):
                    raise ValueError('task gripper force override requires its exact source and isolated fixture')
                limits[7] = (-10., 10.)
            physical = build_panda_direct_effort_execution(
                scene, artifact, source, entity_id='panda-v1', native_drive=native_drive,
                native_ranges=tuple(limits))
            if kind != 'direct':
                from ...controllers.canonical.r3_effort import build_reference_effort_execution
                reference = None
                if kind in {'r3-pose', 'r3-mass-pose'}:
                    from ...controllers.canonical.kinematics import PandaKinematics, PANDA_PICKCUBE_EE_TCP_V1
                    from ...controllers.canonical.production_r3 import ProductionCanonicalPandaControllerR3
                    from .specialization import _r3_dynamic_profile, PICKCUBE_R3_CONTINUOUS_PROFILE_V1
                    model = PandaKinematics(projected, tcp_profile=PANDA_PICKCUBE_EE_TCP_V1)
                    r3_profile, _ = _r3_dynamic_profile()
                    reference = ProductionCanonicalPandaControllerR3.create_arm_reference(
                        model, artifact_hash=artifact.identity_hash, config=position.config,
                        control_dt=artifact.timebase.control_dt, profile=r3_profile,
                        joint_velocity_limit_rad_s=PICKCUBE_R3_CONTINUOUS_PROFILE_V1['joint_velocity_limit_rad_s'])
                if reset_switch:
                    from ...controllers.canonical.r3_effort import build_dynamic_reference_effort_execution
                    physical = build_dynamic_reference_effort_execution(physical, reference_kind=kind,
                        cadence_s=artifact.timebase.control_dt, r3_reference=reference,
                        end_frame_id='nutassembly_ee_site', **parameters)
                elif kind in {'joint-mass', 'r3-mass-pose'}:
                    from .physical_mass_profile import build_pickcube_mass_effort_execution
                    physical = build_pickcube_mass_effort_execution(physical, artifact, source, kind=kind,
                        r3_reference=reference, end_frame_id='nutassembly_ee_site')
                else:
                    physical = build_reference_effort_execution(physical, reference_kind=kind,
                        r3_reference=reference, end_frame_id='nutassembly_ee_site')
            return physical

        physical = build_physical(control_kind)
        def build(_provider):
            return {'artifact': artifact, 'task_source': task_source, 'source': source,
                'controller': physical.controllers[0] if direct_physical else position,
                'solution': None, 'reset_plan': reset_plan,
                **({'solution_factory': base['solution_factory'], 'solution_identity': base['solution_identity'],
                    'readiness': base['readiness']} if reset_switch else {}),
                **({} if reset_switch else {'physical_execution': physical}),
                **({} if direct_physical else {'controller_binding_plan': plan}),
                'construction_id': 'pickcube-mjcf-physical-candidate-v1',
                'source_revision': base['source_revision'], 'source_sha256': {
                    'original_closure': '02f12b11e8215af606d9eed7f22c411dc5bbd74f7d956331b74400b5a1e6963d',
                    'projected_closure': closure},
                'resolved_configuration': {'provider': _provider, 'backend': 'cpu',
                    'finger_initial_position_m': float(legacy_artifact.initialization.joint_position['panda-v1/finger_joint1']),
                    'drive_mode': drive_mode, 'control_kind': control_kind,
                    **({'task_com_force_v1': {'cube_force_z_N': cube_force_z_N}}
                       if cube_force_z_N is not None else {}),
                    'original_closure': '02f12b11e8215af606d9eed7f22c411dc5bbd74f7d956331b74400b5a1e6963d',
                    'projected_closure': closure, 'physical_binding': physical.compiled.binding.identity_hash}}
        def fixed_seed(value):
            if type(value) is not int or value != seed:
                raise ValueError('PickCube physical candidate requires its frozen seed')
            return value
        def physical_execution_info(env):
            from .solution import PickCubePositionExecutionInfoV1
            state = env.state
            opening = sum(float(state.joint_position[f'panda-v1/finger_joint{i}']) for i in (1, 2))
            if -1e-6 <= opening < 0.:
                opening = 0.
            speed = sum(abs(float(state.joint_velocity[f'panda-v1/finger_joint{i}'])) for i in (1, 2))
            target = getattr(env, '_last_physical_opening_target', None)
            target = min(.08, max(0., opening)) if target is None else target
            return PickCubePositionExecutionInfoV1('pickcube-position-execution-info-v1',
                int(state.control_step), float(state.simulation_time), opening, speed, target,
                bool(target <= .045 and opening <= .045 and speed <= .005))
        def physical_action_schema(kind):
            if kind == 'r3-pose':
                from ...controllers.canonical.contracts import REFERENCE_POSE_ACTION_SCHEMA
                return dict(REFERENCE_POSE_ACTION_SCHEMA)
            return {'schema_id': 'physical-joint-reference-v1',
                    'controller_kind': 'absolute_joint', 'dimension': 8}
        def observe_physical_action(env, action, spec):
            if action is None:
                env._last_physical_opening_target = None
            elif spec['kind'] == 'r3-pose':
                import numpy as np
                env._last_physical_opening_target = .04 * (float(np.clip(action[-1], -1., 1.)) + 1.)
            else:
                env._last_physical_opening_target = float(action[-1])
        from .specialization import _validate_external_readiness_solution, make_reference_binding
        task_com_factory = (make_reference_binding(cube_force_z_N=cube_force_z_N).task_com_wrench_factory
                            if cube_force_z_N is not None else None)
        from ...controllers.canonical.reset_selection import PhysicalResetSelection
        owned_resources = ExitStack()
        binding = ReferenceTaskBinding(build=build, reset_sample=lambda _artifact, _seed: reset_plan.reset_sample,
            evaluate=lambda state, semantics: evaluate(state, semantics),
            task_definition_factory=PickCubeTaskDefinition.from_artifact,
            task_state_projection=as_task_state_view,
            object_poses=(('cube-v1', 'cube_v1'),), external_actions=True, interval_mode='grouped',
            task_com_wrench_factory=task_com_factory,
            recorder_mode='execution', reset_seed=fixed_seed, close_task_resources=owned_resources.close,
            position_control_binding=lambda _value: ControlBinding('panda-v1/gripper', 0.08),
            action_schema=physical.action_schema(),
            action_space_factory=physical.action_space, prepare_action=reference_pose_action,
            observation_space_factory=(_direct_physical_observation_spaces if direct_physical
                                       else selected_reference_observation_spaces),
            observation_projection=(_direct_physical_observation if direct_physical else
                                    _physical_pickcube_observation),
            build_external=build if reset_switch else None,
            validate_external_solution=_validate_external_readiness_solution if reset_switch else None,
            position_execution_info=physical_execution_info if reset_switch else None,
            position_execution_info_key='pickcube_position_execution_info_v1' if reset_switch else None,
            physical_reset_action_schema=physical_action_schema if reset_switch else None,
            physical_reset_selection_factory=(lambda: PhysicalResetSelection(build_physical,
                initial_kind=control_kind, allowed_kinds=('joint', 'r3-pose'), space_policy=space_policy,
                declaration=physical))
                if reset_switch else None,
            physical_action_observer=observe_physical_action if reset_switch else None,
            physical_observation_binding=None if direct_physical else legacy_position_physical_observation_binding,
            physical_sequence_v2_observation=direct_physical,
            physical_control_profile=(lambda env: env._physical_reset_selection.current.execution)
                                     if reset_switch else (lambda _env: physical))
        owned_resources.callback(resources.pop_all().close)
        return binding
