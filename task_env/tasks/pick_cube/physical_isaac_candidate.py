"""Compatibility input and task binding for the existing Isaac physical source."""
from dataclasses import replace
from pathlib import Path

from ...registry import register_env
from ...environment.reference_env import SelectedReferenceEnv


@register_env()
class PickCubeIsaacPhysicalCandidateEnv(SelectedReferenceEnv):
    """Legacy input translated to the formal PickCube construction."""
    uid = 'pickcube-isaac-physical-candidate-v1'
    task_rgb_factory_prepares_runtime = True

    @classmethod
    def from_reference_config(cls, config=None, *, render_mode=None, **kwargs):
        from .specialization import PickCubeReferenceEnv
        from .physical_candidate import PICKCUBE_PHYSICAL_PROFILES
        from ...render.base.contracts import validate_camera_declarations
        validate_camera_declarations(render_mode=render_mode, **kwargs)
        values = {} if config is None else dict(config)
        if set(values) - {'delivery_manifest', 'seed', 'horizon', 'drive_mode', 'control_kind'}:
            raise ValueError('Isaac physical compatibility input rejects unsupported configuration')
        profiles = {kind: profile for profile, kind in PICKCUBE_PHYSICAL_PROFILES.items()}
        drive, kind = values.get('drive_mode', 'coexist'), values.get('control_kind', 'direct')
        if drive not in {'coexist', 'effort-only'} or kind not in profiles:
            raise ValueError('unsupported physical drive or controller mode')
        manifest = values.get('delivery_manifest')
        if not isinstance(manifest, (str, Path)) or not str(manifest):
            raise ValueError('Isaac physical source requires its delivery manifest')
        seed, horizon = values.get('seed', 31), values.get('horizon', 8)
        if type(seed) is not int or seed < 0 or type(horizon) is not int or not 1 <= horizon <= 1000:
            raise ValueError('Isaac physical compatibility input requires a valid frozen seed and horizon')
        import sys
        public = {'execution': {'physics_provider': 'isaacsim', 'physics_backend': 'cuda',
                    'physics_device': 'cuda:0', 'source_delivery_manifest': str(manifest),
                    'deployment': 'in_process', 'interpreter': sys.executable},
                  'episode': {'seed': seed, 'horizon': horizon},
                  'robot': {'native_drive': 'position' if drive == 'coexist' else 'disabled'},
                  'controller': {'profile_id': profiles[kind]}}
        return PickCubeReferenceEnv.from_reference_config(public, render_mode=render_mode, **kwargs)


def make_isaac_physical_binding(*, delivery_manifest, seed, horizon, drive_mode, control_kind):
    """Declare source and Controller bindings; Env and Runtime own lifecycle."""
    from .specialization import build_isaac_reference, make_reference_binding
    from .physical_usd_profile import build_f06_direct_effort_execution
    if type(horizon) is not int or not 1 <= horizon <= 1000:
        raise ValueError('Isaac physical source horizon must be in [1, 1000]')
    manifest = delivery_manifest
    def with_physical(value):
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
        return {**value, 'physical_execution': physical}
    base = make_reference_binding(controller_profile='r3_continuous_v1', source_delivery_manifest=manifest)
    def build(provider):
        if provider != 'isaacsim':
            raise ValueError('F06 physical candidate requires Isaac')
        return build_seeded(provider, 'cuda', seed, horizon)
    def build_seeded(provider, backend, actual_seed, actual_horizon):
        if (provider, backend, actual_seed, actual_horizon) != ('isaacsim', 'cuda', seed, horizon):
            raise ValueError('F06 physical candidate requires its frozen execution')
        return with_physical(build_isaac_reference(delivery_manifest=manifest, task_seed=seed, horizon=horizon,
                                     include_solution=False, physical_fixture=drive_mode))
    def reset_seed(actual):
        if type(actual) is not int or actual != seed:
            raise ValueError('F06 physical candidate requires its frozen seed')
        return actual
    from ...environment.reference_binding import legacy_position_physical_observation_binding
    return replace(base, build=build, build_seeded=build_seeded, reset_seed=reset_seed,
        physical_control_profile=lambda env: env.value['physical_execution'],
        action_space_factory=None,
        physical_observation_binding=legacy_position_physical_observation_binding,
        action_schema=None,
        recorder_mode='execution', interval_mode='grouped')
