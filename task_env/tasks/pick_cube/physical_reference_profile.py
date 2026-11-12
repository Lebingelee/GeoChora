"""Task-declared inputs for Panda reference effort Controllers."""
def build_pickcube_effort_profile(direct_execution, artifact, source, *, kind, config,
                                 model, end_frame_id, dynamic_parameters=None):
    """Supply the task's admitted reference inputs to the common Controller owner."""
    from ...controllers.canonical.r3_effort import build_panda_effort_profile

    if kind == 'direct':
        return direct_execution
    r3_profile = velocity_limit = mass_model = None
    if kind in {'r3-pose', 'r3-mass-pose'}:
        from .specialization import _r3_dynamic_profile, PICKCUBE_R3_CONTINUOUS_PROFILE_V1
        r3_profile, _ = _r3_dynamic_profile()
        velocity_limit = PICKCUBE_R3_CONTINUOUS_PROFILE_V1['joint_velocity_limit_rad_s']
    return build_panda_effort_profile(direct_execution, kind=kind,
        cadence_s=artifact.timebase.control_dt, end_frame_id=end_frame_id,
        model=model, config=config, artifact_hash=artifact.identity_hash,
        r3_profile=r3_profile, joint_velocity_limit_rad_s=velocity_limit,
        mass_model=mass_model, dynamic_parameters=dynamic_parameters)
