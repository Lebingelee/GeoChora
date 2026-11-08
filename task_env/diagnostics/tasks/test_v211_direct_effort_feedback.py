"""Source-independent tests of the explicit compatibility projection."""
from types import SimpleNamespace as NS
import numpy as np
import pytest
from task_env.controllers.canonical.physical_controller import DirectJointEffortControllerV1


def _case():
    c = DirectJointEffortControllerV1.__new__(DirectJointEffortControllerV1)
    c.last_action = np.array([.9, -.4], dtype=np.float32)
    c._channels = tuple(NS(sign=1, transmission_coefficient=1., native_drive='disabled', unit='N*m',
                           target_key=('vehicle', name, 'dof0')) for name in ('left', 'right'))
    batch = NS(identity_hash='batch', context='context')
    joints = tuple(NS(entity_id='vehicle', joint_id=name, dof_id='dof0', unit='N*m', value=float(value),
                      contribution_ids=(name,), clipped_before_sum=False, clipped_after_sum=False)
                   for name, value in zip(('left', 'right'), c.last_action, strict=True))
    resolved = NS(input_batch=batch, joints=joints, body_wrenches=(), extensions=(),
                  accepted_receipt=NS(contribution_ids=('left', 'right')))
    ack = NS(batch_sha256='batch', stage='native_write_ack', context='context', contribution_ids=('left', 'right'))
    return c, resolved, ack


def test_feedback_preserves_action_tree_order_dtype_and_diagnostics():
    c, resolved, ack = _case()
    result = c.compatibility_feedback(resolved, ack, mode='direct_wheel_torque', include_diagnostics=True)
    for name in ('requested_action', 'external_action', 'controller_target', 'requested_ctrl', 'applied_ctrl', 'universal_action'):
        assert result[name].dtype == np.float32
        np.testing.assert_array_equal(result[name], c.last_action)
    assert result['action']['mode'] == 'direct_wheel_torque'
    assert result['action']['clipped'] is False and result['ctrl_clipped'] is False
    assert 'not a force measurement' in result['control_application']
    result = c.compatibility_feedback(resolved, ack, mode='direct_wheel_torque', include_diagnostics=False)
    assert 'ctrl_clipped' not in result and 'clipped' not in result['action']


def test_feedback_rejects_foreign_ack_or_mismatched_admission():
    c, resolved, ack = _case()
    ack.batch_sha256 = 'foreign'
    with pytest.raises(ValueError, match='matching accepted'):
        c.compatibility_feedback(resolved, ack, mode='direct_wheel_torque', include_diagnostics=True)
    c, resolved, ack = _case()
    resolved.joints[0].value = -.4
    with pytest.raises(ValueError, match='admitted effort'):
        c.compatibility_feedback(resolved, ack, mode='direct_wheel_torque', include_diagnostics=True)
    c, resolved, ack = _case()
    c._channels[0].transmission_coefficient = 2.
    with pytest.raises(ValueError, match='unit-gear'):
        c.compatibility_feedback(resolved, ack, mode='direct_wheel_torque', include_diagnostics=True)


def test_projection_covers_declared_required_action_feedback():
    from task_env.environment.metadata import task_info_schema_metadata
    c, resolved, ack = _case()
    info = c.compatibility_feedback(resolved, ack, mode='direct_wheel_torque', include_diagnostics=False)
    fields = [f for f in task_info_schema_metadata()['fields']
              if f['category'] == 'required_feedback' and f['required'] and 'step' in f['phases']]
    assert fields
    for field in fields:
        value = info
        for part in field['path'].split('.'):
            assert part in value, field['path']
            value = value[part]
