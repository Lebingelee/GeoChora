"""Task binding for the existing Isaac physical source."""
from dataclasses import replace


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
            from ...controllers.canonical.r3_effort import build_panda_effort_profile
            r3_profile = velocity_limit = mass_model = None
            if control_kind in {'r3-pose', 'r3-mass-pose'}:
                from .specialization import _r3_dynamic_profile, PICKCUBE_R3_CONTINUOUS_PROFILE_V1
                r3_profile, _ = _r3_dynamic_profile()
                velocity_limit = PICKCUBE_R3_CONTINUOUS_PROFILE_V1['joint_velocity_limit_rad_s']
            if control_kind in {'joint-mass', 'r3-mass-pose'}:
                from .physical_mass_profile import load_pickcube_mass_effort_model
                mass_model = load_pickcube_mass_effort_model(value['artifact'], value['source'], kind=control_kind)
            position = value['controller']
            physical = build_panda_effort_profile(physical, kind=control_kind,
                cadence_s=value['artifact'].timebase.control_dt, end_frame_id='ee',
                model=position.model, config=position.config, artifact_hash=value['artifact'].identity_hash,
                r3_profile=r3_profile, joint_velocity_limit_rad_s=velocity_limit, mass_model=mass_model)
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
        action_space_factory=None,
        physical_observation_binding=legacy_position_physical_observation_binding,
        action_schema=None,
        recorder_mode='execution', interval_mode='grouped')
