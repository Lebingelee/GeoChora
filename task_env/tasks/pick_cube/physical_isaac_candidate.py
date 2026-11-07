"""Versioned F06 selected-environment direct-effort candidate."""
from dataclasses import replace
from pathlib import Path

from ...registry import register_env
from ...environment.reference_env import SelectedReferenceEnv


@register_env()
class PickCubeIsaacPhysicalCandidateEnv(SelectedReferenceEnv):
    """F06 USD, native PhysX mimic and a separate typed direct-effort input."""
    uid = 'pickcube-isaac-physical-candidate-v1'
    task_rgb_factory_prepares_runtime = True

    @classmethod
    def from_reference_config(cls, config=None, *, render_mode=None, **kwargs):
        from .specialization import build_isaac_reference, make_reference_binding
        from .physical_usd_profile import build_f06_direct_effort_execution
        values = {} if config is None else dict(config)
        observer_camera = kwargs.pop('observer_camera', None)
        task_camera = kwargs.pop('task_camera', None)
        task_rgb_camera = kwargs.pop('task_rgb_camera', None)
        task_renderer = kwargs.pop('task_renderer', None)
        if (task_rgb_camera is None) != (task_renderer is None):
            raise ValueError('task RGB camera and fixed renderer must be declared together')
        if task_rgb_camera is not None:
            from ...observations.canonical_camera import CameraGeometry
            if type(task_rgb_camera) is not CameraGeometry:
                raise TypeError('task RGB camera must be CameraGeometry')
            task_rgb_camera.validate()
            if task_renderer != 'isaacsim':
                raise ValueError('Isaac task RGB requires the Isaac RTX renderer')
        if task_rgb_camera is not None and task_camera is not None:
            raise ValueError('declare either a task RGB camera or a legacy task camera binding')
        if kwargs or set(values) - {'delivery_manifest', 'seed', 'horizon', 'drive_mode', 'control_kind'}:
            raise ValueError('F06 physical candidate rejects unsupported configuration')
        if task_camera is not None:
            from ...observations.canonical_camera import CameraGeometry
            if type(task_camera) is not CameraGeometry:
                raise TypeError('task camera must be CameraGeometry')
            task_camera.validate()
            if task_camera.parent_frame != 'world':
                raise ValueError('F06 task camera currently admits world mounts only')
            if render_mode is None:
                raise ValueError('F06 task camera requires an observer-enabled scene')
            if task_camera.camera_id == getattr(observer_camera, 'camera_id', None):
                raise ValueError('task and observer cameras require distinct identities')
        if render_mode is not None:
            from ...render.base.contracts import normalize_render_mode
            from ...observations.canonical_camera import CameraGeometry
            render_mode = normalize_render_mode(render_mode).value
            if type(observer_camera) is not CameraGeometry:
                raise ValueError('F06 rendering requires an explicit observer CameraGeometry')
            observer_camera.validate()
            if not observer_camera.rgb or observer_camera.depth or observer_camera.rgb_layout != 'HWC' or observer_camera.rgb_dtype != 'float32':
                raise ValueError('F06 observer requires HWC float32 RGB without depth')
        elif observer_camera is not None:
            raise ValueError('observer camera requires a configured render mode')
        manifest = values.get('delivery_manifest')
        seed, horizon = values.get('seed', 31), values.get('horizon', 8)
        drive_mode = values.get('drive_mode', 'coexist')
        if drive_mode not in {'coexist', 'effort-only'}:
            raise ValueError('F06 physical drive_mode must be coexist or effort-only')
        control_kind = values.get('control_kind', 'direct')
        if control_kind not in {'direct', 'joint', 'r3-pose', 'joint-mass', 'r3-mass-pose'}:
            raise ValueError('unsupported F06 physical controller mode')
        if control_kind != 'direct' and drive_mode != 'effort-only':
            raise ValueError('F06 reference effort requires the isolated drive fixture')
        if not isinstance(manifest, (str, Path)) or not str(manifest):
            raise ValueError('F06 physical candidate requires its delivery manifest')
        if type(seed) is not int or seed < 0 or type(horizon) is not int or not 1 <= horizon <= 1000:
            raise ValueError('F06 physical candidate requires a valid frozen seed and horizon')
        app_owner = None
        opened_here = False
        try:
            if render_mode is not None or task_rgb_camera is not None:
                from ...runtime.sessions.isaac_native_io import (
                    _process_app_owner, V211_ISAAC_RENDER_APP_LAUNCH_PROFILE_V1,
                )
                app_owner = _process_app_owner(launch_profile_id=V211_ISAAC_RENDER_APP_LAUNCH_PROFILE_V1)
                opened_here = app_owner.app is None
                app_owner.open(f06_compatibility=True)
            value = build_isaac_reference(delivery_manifest=manifest, task_seed=seed, horizon=horizon,
                                          include_solution=False, physical_fixture=drive_mode)
            execution = value['execution_spec_v1']
            physical = build_f06_direct_effort_execution(value['source'].scene_definition,
                                                          value['artifact'], value['source'])
            if control_kind != 'direct':
                from ...controllers.canonical.r3_effort import build_reference_effort_execution
                reference = None
                if control_kind in {'r3-pose', 'r3-mass-pose'}:
                    from ...controllers.canonical.production_r3 import ProductionCanonicalPandaControllerR3
                    from .specialization import _r3_dynamic_profile, PICKCUBE_R3_CONTINUOUS_PROFILE_V1
                    r3_profile, _ = _r3_dynamic_profile()
                    position = value['controller']
                    reference = ProductionCanonicalPandaControllerR3.create_arm_reference(
                        position.model, artifact_hash=value['artifact'].identity_hash, config=position.config,
                        control_dt=value['artifact'].timebase.control_dt, profile=r3_profile,
                        joint_velocity_limit_rad_s=PICKCUBE_R3_CONTINUOUS_PROFILE_V1['joint_velocity_limit_rad_s'])
                if control_kind in {'joint-mass', 'r3-mass-pose'}:
                    from .physical_mass_profile import build_pickcube_mass_effort_execution
                    physical = build_pickcube_mass_effort_execution(physical, value['artifact'], value['source'],
                        kind=control_kind, r3_reference=reference, end_frame_id='ee')
                else:
                    physical = build_reference_effort_execution(physical, reference_kind=control_kind,
                                                                 r3_reference=reference, end_frame_id='ee')
            base = make_reference_binding(controller_profile='r3_continuous_v1', source_delivery_manifest=manifest)
            def build(provider):
                if provider != 'isaacsim':
                    raise ValueError('F06 physical candidate requires Isaac')
                return value
            def build_seeded(provider, backend, actual_seed, actual_horizon):
                if (provider, backend, actual_seed, actual_horizon) != ('isaacsim', 'cuda', seed, horizon):
                    raise ValueError('F06 physical candidate requires its frozen execution')
                return build_isaac_reference(delivery_manifest=manifest, task_seed=seed, horizon=horizon,
                                             include_solution=False, physical_fixture=drive_mode)
            def reset_seed(actual):
                if type(actual) is not int or actual != seed:
                    raise ValueError('F06 physical candidate requires its frozen seed')
                return actual
            binding = replace(base, build=build, build_seeded=build_seeded, reset_seed=reset_seed,
                reset_sample=lambda _artifact, _seed: value['reset_plan'].reset_sample,
                physical_control_profile=lambda _env: physical, action_space_factory=physical.action_space,
                action_schema={'schema_version': 'physical-control-actions-v1',
                               'controllers': [{'identity': c.identity, 'shape': list(c.action_shape)}
                                               for c in physical.controllers]},
                recorder_mode='execution', interval_mode='grouped')
            env = cls.from_position_candidate(binding, provider='isaacsim', backend='cuda',
                                              horizon=horizon, execution_spec=execution)
            if task_rgb_camera is not None:
                try:
                    env._configure_task_rgb(task_rgb_camera, task_renderer)
                except BaseException as error:
                    try:
                        env.close()
                    except BaseException as cleanup_error:
                        error.add_note(f'F06 task RGB construction cleanup failed: {cleanup_error!r}')
                    raise
            if render_mode is not None:
                try:
                    if task_camera is not None:
                        import copy
                        if task_camera.task_artifact_hash != env.artifact.identity_hash:
                            raise ValueError('task camera TaskArtifact linkage mismatch')
                        env._declared_task_camera = copy.deepcopy(task_camera)
                    env._configure_selected_observer(render_mode, observer_camera)
                except BaseException as error:
                    try:
                        env.close()
                    except BaseException as cleanup_error:
                        error.add_note(f'F06 observer construction cleanup failed: {cleanup_error!r}')
                    raise
            return env
        except BaseException as error:
            if opened_here and app_owner is not None:
                try:
                    app_owner.close()
                except BaseException as cleanup_error:
                    error.add_note(f'F06 App construction cleanup failed: {cleanup_error!r}')
            raise
