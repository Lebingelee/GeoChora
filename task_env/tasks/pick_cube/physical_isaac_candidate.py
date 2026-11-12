"""Task binding for the existing Isaac physical source."""
from dataclasses import replace
from functools import partial


def make_isaac_physical_binding(*, delivery_manifest, seed, horizon, drive_mode, control_kind,
                                task_config, resolved_config, lift_height_m=None):
    """Declare source and Controller bindings; Env and Runtime own lifecycle."""
    from .specialization import build_isaac_reference, make_reference_binding
    from ...runtime.sessions.isaac_physical import build_isaac_panda_effort_execution
    if type(horizon) is not int or not 1 <= horizon <= 1000:
        raise ValueError('Isaac physical source horizon must be in [1, 1000]')
    manifest = delivery_manifest
    def build_controller(robot, runtime_input, panda_xml, action_config):
        from ...controllers.canonical.kinematics import PandaKinematics, PANDA_PICKCUBE_EE_TCP_V1
        from .physical_reference_profile import build_pickcube_effort_profile
        source, artifact = runtime_input.runtime_source, runtime_input.artifact
        physical = build_isaac_panda_effort_execution(robot, source.scene_definition, artifact, source,
            native_drive='disabled' if drive_mode == 'effort-only' else 'position')
        model = (PandaKinematics(panda_xml, tcp_profile=PANDA_PICKCUBE_EE_TCP_V1)
                 if control_kind in {'r3-pose', 'r3-mass-pose'} else None)
        return build_pickcube_effort_profile(physical, artifact, source, kind=control_kind,
            config=action_config, model=model, end_frame_id='ee')
    base = make_reference_binding(controller_profile='r3_continuous_v1', source_delivery_manifest=manifest,
                                  task_config=task_config, resolved_config=resolved_config,
                                  lift_height_m=lift_height_m)
    def build(provider):
        if provider != 'isaacsim':
            raise ValueError('F06 physical candidate requires Isaac')
        return build_seeded(provider, 'cuda', seed, horizon)
    def build_seeded(provider, backend, actual_seed, actual_horizon):
        if (provider, backend) != ('isaacsim', 'cuda'):
            raise ValueError('Isaac physical control requires Isaac CUDA')
        return build_isaac_reference(delivery_manifest=manifest, task_seed=actual_seed, horizon=actual_horizon,
                                     include_solution=False, physical_fixture=drive_mode,
                                     controller_builder=build_controller, task_config=task_config,
                                     resolved_config=resolved_config, lift_height_m=lift_height_m)
    from .physical_candidate import _direct_physical_observation, _direct_physical_observation_spaces
    return replace(base, build=build, build_seeded=build_seeded,
        scalar_control_binding=None, action_space_factory=None,
        observation_space_factory=_direct_physical_observation_spaces,
        observation_projection=partial(_direct_physical_observation, hand_frame_id='ee'),
        physical_sequence_v2_observation=True,
        action_schema=None,
        recorder_mode='execution', interval_mode='grouped')
