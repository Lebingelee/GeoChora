import pytest

from task_env.artifacts import ExecutionSpec
from task_env.runtime.sessions.api import _diagnostic_manifest, provider_manifest
from task_env.tasks.nut_assembly.task import (
    NutAssemblyReferenceEnv,
    build_gripper_cadence_diagnostic_reference,
)


def test_equal_rate_gripper_updates_once_and_holds_for_four_native_steps():
    from task_env.controllers.canonical.gripper_execution import EqualRateGripperServo

    class Controller:
        inner_physics_dt_s = 0.002
        _force_mode = False
        _force_initialized = False

        def __init__(self):
            self.elapsed = []

        def inner_gripper_step(self, _state, _feedback):
            self.elapsed.append(self.inner_physics_dt_s)
            return 'target-100hz', {'commanded_opening_m': 0.04,
                                    'desired_opening_m': 0.04,
                                    'controller_close_ready': False,
                                    'command_saturated_at_zero': False}

    controller = Controller()
    servo = EqualRateGripperServo(controller, 100, 0.01)
    state = type('State', (), {'control_step': 7})()
    feedback = type('Feedback', (), {'gripper': type('Grip', (), {
        'opening_m': 0.08, 'closing_force_N': 0.0,
    })()})()
    outputs = [servo.inner_gripper_step(state, feedback) for _ in range(5)]

    assert outputs[0][1]['inner_update_performed'] is True
    assert all(output[1]['inner_update_performed'] is False for output in outputs[1:])
    assert all(output[0] == 'target-100hz' for output in outputs)
    assert controller.elapsed == [0.01]
    assert servo.update_count == 1 and servo.held_count == 4
    servo.reset()
    assert servo.update_count == 0 and servo.held_count == 0


def test_cadence_experiment_is_explicit_and_does_not_widen_selected_manifest():
    assert provider_manifest('geophys').backend == 'cpu'
    with pytest.raises(ValueError, match='scalar CPU only'):
        NutAssemblyReferenceEnv(provider='geophys', backend='cuda')
    with pytest.raises(ValueError, match='100/500 Hz'):
        NutAssemblyReferenceEnv.for_gripper_cadence_diagnostic(backend='cpu', gripper_control_hz=250)

    cpu_100 = build_gripper_cadence_diagnostic_reference(backend='cpu', gripper_control_hz=100)
    cpu_500 = build_gripper_cadence_diagnostic_reference(backend='cpu', gripper_control_hz=500)
    cuda_100 = build_gripper_cadence_diagnostic_reference(backend='cuda', gripper_control_hz=100)
    assert cpu_100['artifact'].identity_hash == cpu_500['artifact'].identity_hash == cuda_100['artifact'].identity_hash
    assert cpu_100['source'].scene_source.xml == cpu_500['source'].scene_source.xml == cuda_100['source'].scene_source.xml
    assert cpu_100['source'].config.runtime.backend == 'cpu'
    assert cpu_500['source'].config.runtime.backend == 'cpu'
    assert cuda_100['source'].config.runtime.backend == 'cuda'
    assert type(cpu_100['controller'].inner).__name__ == 'EqualRateGripperServo'
    assert type(cpu_500['controller'].inner).__name__ == 'NativeRateGripperServo'
    assert cpu_100['controller_identity'] != cpu_500['controller_identity']


def test_cuda_diagnostic_manifest_is_source_pinned_and_not_global_capability():
    reference = build_gripper_cadence_diagnostic_reference(backend='cuda', gripper_control_hz=500)
    execution = ExecutionSpec('geophys', 'p1_2_scalar_cpu_v0', 'none', 'cuda', 0, 'strict')
    manifest = _diagnostic_manifest(
        reference['artifact'], execution, reference['source'], 'nutassembly-gripper-cadence-v1',
    )
    assert manifest.provider_name == 'geophys' and manifest.backend == 'cuda'
    assert manifest.evidence_reference == 'diagnostic-only-no-capability-or-qualification'
    assert provider_manifest('geophys').backend == 'cpu'
    assert provider_manifest('geophys').identity_hash != manifest.identity_hash

    wrong = build_gripper_cadence_diagnostic_reference(backend='cpu', gripper_control_hz=500)
    with pytest.raises(ValueError, match='diagnostic admission source'):
        _diagnostic_manifest(wrong['artifact'], execution, wrong['source'], 'nutassembly-gripper-cadence-v1')


def test_native_clock_ack_allows_only_accumulated_float_roundoff():
    from task_env.tasks.reference_env import _boundary_interval_clock_tolerance

    start, end, expected = 0.020000000000000004, 0.030000000000000013, 0.01
    tolerance = _boundary_interval_clock_tolerance(start, end, expected, 0.002, 5)
    assert abs((end - start) - expected) <= tolerance
    assert 1e-12 > tolerance
