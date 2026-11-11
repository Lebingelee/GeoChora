"""Task binding for the existing Isaac physical source."""
from dataclasses import replace
from functools import partial


def make_isaac_physical_binding(*, delivery_manifest, seed, horizon, drive_mode, control_kind):
    """Declare source and Controller bindings; Env and Runtime own lifecycle."""
    from .specialization import build_isaac_reference, make_reference_binding
    from .physical_usd_profile import build_f06_direct_effort_execution
    if type(horizon) is not int or not 1 <= horizon <= 1000:
        raise ValueError('Isaac physical source horizon must be in [1, 1000]')
    manifest = delivery_manifest
    def with_physical(value):
        physical = build_f06_direct_effort_execution(value['robot'], value['source'].scene_definition,
                                                      value['artifact'], value['source'])
        from .physical_reference_profile import build_pickcube_effort_profile
        position = value['controller']
        physical = build_pickcube_effort_profile(physical, value['artifact'], value['source'],
            kind=control_kind, config=position.config, model=position.model, end_frame_id='ee')
        from ...controllers.canonical.contracts import digest
        resolved = {**value['resolved_configuration'], 'controller_identity': physical.controllers[0].identity}
        return {**value, 'controller': physical.controllers[0], 'physical_execution': physical,
                'resolved_configuration': resolved, 'recipe_identity': digest(resolved)}
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
    from .physical_candidate import _direct_physical_observation, _direct_physical_observation_spaces
    return replace(base, build=build, build_seeded=build_seeded, reset_seed=reset_seed,
        scalar_control_binding=None, action_space_factory=None,
        observation_space_factory=_direct_physical_observation_spaces,
        observation_projection=partial(_direct_physical_observation, hand_frame_id='ee'),
        physical_sequence_v2_observation=True,
        action_schema=None,
        recorder_mode='execution', interval_mode='grouped')
