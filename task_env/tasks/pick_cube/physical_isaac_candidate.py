"""Task binding for the existing Isaac physical source."""
def make_isaac_physical_binding(*, delivery_manifest, horizon, drive_mode, control_kind,
                                task_config, resolved_config, lift_height_m=None, robot=None):
    """Declare source and Controller bindings; Env and Runtime own lifecycle."""
    from .specialization import build_isaac_reference, _validate_external_readiness_solution
    from .task import physical_task_binding_fields
    from ...environment.reference_binding import ReferenceTaskBinding
    from ...runtime.sessions.source_composition_adapters import build_panda_effort_execution
    if type(horizon) is not int or not 1 <= horizon <= 1000:
        raise ValueError('Isaac physical source horizon must be in [1, 1000]')
    manifest = delivery_manifest
    def build_controller(robot, runtime_input, panda_xml, action_config):
        from .physical_reference_profile import build_pickcube_effort_profile
        source, artifact = runtime_input.runtime_source, runtime_input.artifact
        physical = build_panda_effort_execution(robot, source.scene_definition, artifact, source,
            native_drive='disabled' if drive_mode == 'effort-only' else 'position')
        return build_pickcube_effort_profile(physical, artifact, kind=control_kind,
            config=action_config, source_xml=panda_xml, end_frame_id='ee')
    def build(provider, backend, actual_seed, actual_horizon, sampled):
        if sampled is not None:
            raise ValueError('PickCube does not accept an externally sampled reset')
        if (provider, backend) != ('isaacsim', 'cuda'):
            raise ValueError('Isaac physical control requires Isaac CUDA')
        if type(actual_horizon) is not int or not 1 <= actual_horizon <= 1000:
            raise ValueError('Isaac physical source horizon must be in [1, 1000]')
        return build_isaac_reference(delivery_manifest=manifest, task_seed=actual_seed, horizon=actual_horizon,
                                     include_solution=False, physical_fixture=drive_mode,
                                     controller_builder=build_controller, task_config=task_config,
                                     resolved_config=resolved_config, lift_height_m=lift_height_m, robot=robot)
    return ReferenceTaskBinding(build=build,
        **physical_task_binding_fields(task_config=task_config, lift_height_m=lift_height_m,
                                       hand_frame_id='ee'),
        action_schema=None, action_space_factory=None,
        reset_runtime_input=lambda value: value.get('session_admission_input'),
        validate_external_solution=_validate_external_readiness_solution,
        external_solution_actions=True,
        reset_expert_kwargs=lambda env: {'execution_info': env.expert_execution_info()},
        observe_expert_kwargs=lambda env, _samples: {'execution_info': env.expert_execution_info()})
