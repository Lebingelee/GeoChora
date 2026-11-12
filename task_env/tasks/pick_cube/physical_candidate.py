"""Source-traced PickCube MJCF physical-control candidate using the selected Env."""
from __future__ import annotations

from dataclasses import replace
from contextlib import ExitStack
from pathlib import Path



from ...robots.panda import PandaAgent

def validate_physical_configuration(*, provider, backend, profile, robot_uid, native_drive,
                                    parameters, gravity_compensation, reset_profile,
                                    source_delivery_manifest, execution_spec, task_parameters, horizon):
    profiles = PandaAgent.effort_controller_profiles()
    if profile not in profiles:
        if native_drive is not None or parameters:
            raise ValueError('Robot/Controller/source options require a declared physical profile')
        return
    kind = profiles[profile]
    if execution_spec.deployment != 'in_process':
        raise ValueError('physical profile currently requires explicit in_process execution')
    if (provider, backend) not in {('mujoco', 'cpu'), ('geophys', 'cpu'), ('isaacsim', 'cuda')}:
        raise ValueError('physical control requires an admitted CPU or Isaac CUDA route')
    if robot_uid != 'panda-v1' or gravity_compensation or reset_profile is not None:
        raise ValueError('physical profile requires its declared Panda source without Position-only options')
    if provider == 'isaacsim':
        if source_delivery_manifest is None or parameters or set(task_parameters) - {'lift_height_m'}:
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
    if set(task_parameters) - {'cube_force_z_N', 'lift_height_m'}:
        raise ValueError('physical source retains its declared Task parameters; unsupported override')
    if 'cube_force_z_N' in task_parameters and (provider, drive, kind, switch) != (
            'mujoco', 'position', 'direct', False):
        raise ValueError('PickCube Task COM force requires MuJoCo direct coexist control')


def physical_binding_from_config(config, *, robot=None):
    import json
    options = json.loads(config.controller_parameters_json)
    task_config = json.loads(config.task_configuration_json)
    lift_height_m = dict(config.task_parameters).get('lift_height_m')
    kind = PandaAgent.effort_controller_profiles()[config.controller_profile]
    drive = config.native_drive or ('position' if kind == 'direct' else 'disabled')
    if config.physics_provider == 'isaacsim':
        from .physical_isaac_candidate import make_isaac_physical_binding
        return make_isaac_physical_binding(delivery_manifest=config.source_delivery_manifest,
            horizon=config.environment.episode.horizon,
            drive_mode='effort-only' if drive == 'disabled' else 'coexist', control_kind=kind,
            task_config=task_config, resolved_config=config.environment, lift_height_m=lift_height_m, robot=robot)
    force = dict(config.task_parameters).get('cube_force_z_N')
    return make_physical_binding(
        drive_mode='effort-only' if drive == 'disabled' else 'coexist', control_kind=kind,
        reset_switch=options.get('reset_selection', False), space_policy=options.get('action_space_policy', 'dynamic'),
        cube_force_z_N=force, task_config=task_config, resolved_config=config.environment,
        lift_height_m=lift_height_m, robot=robot)


def make_physical_binding(*, drive_mode, control_kind,
                          task_config, resolved_config, reset_switch=False,
                          space_policy='dynamic', cube_force_z_N=None, lift_height_m=None, robot=None):
    """Declare task/source/control bindings; the shared factory constructs Env."""
    from ...controllers.canonical.contracts import reference_pose_action
    from ...environment import sample_episode_reset_plan
    from ...environment.reference_binding import ReferenceTaskBinding
    from functools import partial
    from ...observations.selected_reference import selected_reference_observation_spaces
    from .specialization import _prepare_reference_source, compile_pickcube_mjcf_task
    from .task import physical_observation, task_binding_fields

    prepared = _prepare_reference_source(
        backend='cpu', controller_profile='r3_continuous_v1', task_config=task_config,
        resolved_config=resolved_config, lift_height_m=lift_height_m, include_readiness=reset_switch, robot=robot)
    legacy_artifact, original, readiness = prepared.artifact, prepared.source, prepared.readiness
    from ...runtime.sessions.source import close_execution_source_on_failure
    with close_execution_source_on_failure(original):
        import subprocess
        revision = subprocess.check_output(['git', '-C', str(Path(__file__).resolve().parents[3]),
                                            'rev-parse', 'HEAD'], text=True).strip()
        if reset_switch:
            from .solution import PickCubeReadinessSolution
            solution_identity = PickCubeReadinessSolution.identity_for_config(readiness)
        receipt = original.execution_source_receipt
    with ExitStack() as resources:
        resources.callback(receipt.close)
        robot = original.agents[0]
        task_source, scene, artifact, bodies, frames = compile_pickcube_mjcf_task(
            task_config, robot, legacy_artifact)
        from ...runtime.sessions.source import bind_reference_scene_source
        source, projected, closure = bind_reference_scene_source(original, artifact=artifact,
            scene=scene, bodies=bodies, frames=frames)
        def build_physical(kind, **parameters):
            if (set(parameters) - {'kp', 'kd', 'finger_kp', 'finger_kd'}
                    or any(type(value) not in (int, float) or not 0. < value <= 5000.
                           for value in parameters.values())):
                raise ValueError('unsupported or invalid physical controller parameters')
            if parameters and not reset_switch:
                raise ValueError('controller parameters require physical reset selection')
            from ...runtime.sessions.source_composition_adapters import build_panda_effort_execution
            native_drive = 'disabled' if drive_mode == 'effort-only' else 'position'
            physical = build_panda_effort_execution(
                robot, scene, artifact, source, native_drive=native_drive, gripper_force_limit_N=(
                    source.config.robot.gripper.force_limit_N if reset_switch else None))
            from .physical_reference_profile import build_pickcube_effort_profile
            return build_pickcube_effort_profile(physical, artifact, kind=kind,
                config=source.config.action, source_xml=projected, end_frame_id='nutassembly_ee_site',
                dynamic_parameters=parameters if reset_switch else None)

        physical = build_physical(control_kind)
        def build(provider, backend, actual_seed, _horizon, sampled):
            if backend != source.config.runtime.backend:
                raise ValueError('requested backend differs from the declared Robot source')
            if sampled is not None:
                raise ValueError('PickCube does not accept an externally sampled reset')
            reset_plan = sample_episode_reset_plan(task_source, scene, artifact, task_seed=actual_seed)
            return {'artifact': artifact, 'task_source': task_source, 'source': source,
                'controller': physical.controllers[0],
                'solution': None, 'reset_plan': reset_plan,
                **({'solution_factory': lambda: PickCubeReadinessSolution(config=readiness),
                    'solution_identity': solution_identity, 'readiness': readiness} if reset_switch else {}),
                'physical_execution': physical,
                'construction_id': 'pickcube-mjcf-physical-candidate-v1',
                'source_revision': revision, 'source_sha256': {
                    'original_closure': original.source_closure_digest,
                    'projected_closure': closure},
                'resolved_configuration': {'provider': provider, 'backend': backend,
                    'finger_initial_position_m': float(legacy_artifact.initialization.joint_position['panda-v1/finger_joint1']),
                    'drive_mode': drive_mode, 'control_kind': control_kind,
                    **({'task_com_force_v1': {'cube_force_z_N': cube_force_z_N}}
                       if cube_force_z_N is not None else {}),
                    'original_closure': original.source_closure_digest,
                    'projected_closure': closure, 'physical_binding': physical.compiled.binding.identity_hash}}
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
        from .specialization import _validate_external_readiness_solution
        from ...controllers.canonical.reset_selection import PhysicalResetSelection
        owned_resources = ExitStack()
        binding = ReferenceTaskBinding(build=build,
            **task_binding_fields(task_config=task_config, lift_height_m=lift_height_m,
                cube_force_z_N=cube_force_z_N, reset_sampler=lambda _artifact, actual_seed:
                    sample_episode_reset_plan(task_source, scene, artifact, task_seed=actual_seed).reset_sample),
            external_actions=True, interval_mode='grouped',
            recorder_mode='execution', close_task_resources=owned_resources.close,
            action_schema=physical.action_schema(),
            action_space_factory=physical.action_space, prepare_action=reference_pose_action,
            observation_space_factory=partial(selected_reference_observation_spaces, include_robot_state=True),
            observation_projection=physical_observation,
            validate_external_solution=_validate_external_readiness_solution if reset_switch else None,
            position_execution_info=physical_execution_info if reset_switch else None,
            position_execution_info_key='pickcube_position_execution_info_v1' if reset_switch else None,
            physical_reset_action_schema=physical_action_schema if reset_switch else None,
            physical_reset_selection_factory=(lambda: PhysicalResetSelection(build_physical,
                initial_kind=control_kind, allowed_kinds=('joint', 'r3-pose'), space_policy=space_policy,
                declaration=physical))
                if reset_switch else None,
            physical_action_observer=observe_physical_action if reset_switch else None,
            physical_sequence_v2_observation=True)
        owned_resources.callback(resources.pop_all().close)
        return binding
