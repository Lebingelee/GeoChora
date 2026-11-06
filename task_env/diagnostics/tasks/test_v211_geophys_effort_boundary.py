"""Provider-free tests for the public GeoPhys generalized-effort boundary."""
import numpy as np
import pytest
from task_env.runtime.boundary import GeoPhysRuntimeBoundary


class FakePhysics:
    n_dof = 3
    def __init__(self):
        self.writes = []
        self.fail = False
    def set_qfrc_applied(self, values):
        if self.fail:
            raise RuntimeError('setter failed')
        self.writes.append(np.asarray(values).copy())


def boundary():
    value = GeoPhysRuntimeBoundary.__new__(GeoPhysRuntimeBoundary)
    value._physics = FakePhysics()
    value._generalized_effort_pending = False
    value._generalized_effort_fault = False
    return value


def test_effort_boundary_replace_clear_and_reject_duplicate():
    value = boundary()
    value.write_generalized_effort([1., -2., 0.5])
    assert value._physics.writes[0].dtype == np.float32
    np.testing.assert_array_equal(value._physics.writes[0], [1., -2., .5])
    with pytest.raises(RuntimeError, match='occupied'):
        value.write_generalized_effort([0., 0., 0.])
    value.clear_generalized_effort()
    np.testing.assert_array_equal(value._physics.writes[-1], [0., 0., 0.])
    value.write_generalized_effort([-1., 2., 0.])
    value.clear_generalized_effort()
    assert len(value._physics.writes) == 4


@pytest.mark.parametrize('bad', [[1., 2.], [1., float('nan'), 2.], [True, False, True], [1e100, 0., 0.]])
def test_effort_boundary_rejects_invalid_before_write(bad):
    value = boundary()
    with pytest.raises(ValueError):
        value.write_generalized_effort(bad)
    assert not value._physics.writes and not value._generalized_effort_pending


def test_effort_boundary_fault_requires_rebuild_after_setter_failure():
    value = boundary(); value._physics.fail = True
    with pytest.raises(RuntimeError, match='setter failed'):
        value.write_generalized_effort([1., 0., 0.])
    value._physics.fail = False
    value.clear_generalized_effort()
    with pytest.raises(RuntimeError, match='faulted'):
        value.write_generalized_effort([0., 0., 0.])


def test_port_rechecks_mapping_and_clears_owned_interval():
    from dataclasses import replace
    from types import SimpleNamespace
    from task_env.controllers.canonical.physical_commands import PhysicalCommandBatchV1
    from task_env.runtime.sessions.geophys_physical import GeoPhysPhysicalPort
    from task_env.runtime.sessions.physical_control import prepare_physical_command_batch
    from task_env.diagnostics.tasks.test_v211_physical_control_contract import _case

    plan, context, effort, _ = _case()
    batch = PhysicalCommandBatchV1('physical-command-batch-v1', context, (effort('force-a', 1.),), (), ())
    host = boundary()
    session = SimpleNamespace(_require_open=lambda: None, _require_reset=lambda: None,
        state_boundary_identity=lambda: context.boundary,
        snapshot_v2=lambda **kwargs: SimpleNamespace(view=SimpleNamespace(boundary=context.boundary, sample_clock=context.clock)),
        _artifact=SimpleNamespace(timebase=SimpleNamespace(control_dt=.01)),
        _initial=SimpleNamespace(qvel=np.zeros(3)), _boundary=host, provider_materialization_id='material-a')
    port = object.__new__(GeoPhysPhysicalPort)
    port.session, port.binding = session, plan.binding
    port.execution = SimpleNamespace(compiled=plan, scene=plan.scene, generation=1,
                                     joint_bindings={}, frame_bindings={}, requirements=None)
    port.dofs = {plan.binding.channels[0].target_key: 1}
    port.pending, port.consumed = None, set()
    admitted = prepare_physical_command_batch(plan, batch, expected_context=context,
        assessment=port.assessment(plan.binding), joint_build_receipt=port.joints(plan.binding))
    forged = replace(admitted, joints=(replace(admitted.joints[0], value=2.),))
    with pytest.raises(ValueError, match='admitted GeoPhys'):
        port.write(forged)
    assert not host._physics.writes
    assert port.write(admitted).stage == 'native_write_ack'
    np.testing.assert_array_equal(host._physics.writes[-1], [0., 1., 0.])
    with pytest.raises(ValueError, match='duplicated'):
        port.write(admitted)
    port.finish_interval()
    np.testing.assert_array_equal(host._physics.writes[-1], [0., 0., 0.])
    with pytest.raises(ValueError, match='duplicated'):
        port.write(admitted)


def test_public_actuator_isolation_and_failure_restore():
    class Physics:
        def __init__(self):
            self.enabled = {0: True, 1: True}
            self.fail_once = False
        def read_actuator_enabled(self, index):
            return self.enabled[index]
        def set_actuator_enabled(self, index, enabled):
            self.enabled[index] = enabled
            if index == 1 and not enabled and self.fail_once:
                self.fail_once = False
                raise RuntimeError('partial setter failure')
    boundary = object.__new__(GeoPhysRuntimeBoundary)
    boundary._physics = Physics()
    result = boundary.isolate_actuator_outputs_for_physical_fixture((0, 1))
    assert result['before_enabled'] == [True, True]
    assert result['after_enabled'] == [False, False]
    assert boundary._physics.enabled == {0: False, 1: False}
    boundary._physics = Physics()
    boundary._physics.fail_once = True
    with pytest.raises(RuntimeError, match='partial setter failure'):
        boundary.isolate_actuator_outputs_for_physical_fixture((0, 1))
    assert boundary._physics.enabled == {0: True, 1: True}
