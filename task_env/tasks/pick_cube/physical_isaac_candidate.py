"""Versioned F06 selected-environment direct-effort candidate."""
from dataclasses import replace
from pathlib import Path

from ...registry import register_env
from ...environment.reference_env import SelectedReferenceEnv


@register_env()
class PickCubeIsaacPhysicalCandidateEnv(SelectedReferenceEnv):
    """F06 USD, native PhysX mimic and a separate typed direct-effort input."""
    uid = 'pickcube-isaac-physical-candidate-v1'

    @classmethod
    def from_reference_config(cls, config=None, *, render_mode=None, **kwargs):
        from .specialization import build_isaac_reference, make_reference_binding
        from .physical_usd_profile import build_f06_direct_effort_execution
        values = {} if config is None else dict(config)
        if kwargs or render_mode is not None or set(values) - {'delivery_manifest', 'seed', 'horizon', 'drive_mode', 'control_kind'}:
            raise ValueError('F06 physical candidate rejects unsupported configuration')
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
        return cls.from_position_candidate(binding, provider='isaacsim', backend='cuda',
                                           horizon=horizon, execution_spec=execution)
