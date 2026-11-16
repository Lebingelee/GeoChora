"""Provider-free checks of the physical-control v3 recording projection."""
from types import SimpleNamespace
import numpy as np
from task_env.controllers.canonical.physical_commands import PhysicalCommandBatchV1, PhysicalControlReceiptV1
from task_env.diagnostics.tasks.test_v211_physical_control_contract import _case
from task_env.recorders.physical_metadata import record_physical_transition
from task_env.runtime.sessions.physical_control import ResolvedJointEffortV1


def test_recording_selects_only_the_group_covering_physical_channels():
    from task_env.artifacts import ActuatorReference, ControlGroup
    from task_env.recorders.physical_metadata import physical_action_group
    arm = ControlGroup('control-group-v1', 'arm', 'arm', (ActuatorReference('arm', 'motor'),))
    hand = ControlGroup('control-group-v1', 'arm', 'hand', (ActuatorReference('arm', 'finger'),))
    binding = SimpleNamespace(channels=(SimpleNamespace(entity_id='arm', native_actuator='motor'),))
    execution = SimpleNamespace(scene=SimpleNamespace(control_groups=(arm, hand)),
                                compiled=SimpleNamespace(binding=binding))
    assert physical_action_group(execution) == arm
    execution.scene.control_groups = (hand,)
    import pytest
    with pytest.raises(ValueError, match='matching the selected channels'):
        physical_action_group(execution)


def test_physical_record_keeps_spec_batch_ack_and_no_measured_force():
    plan, context, effort, _ = _case()
    batch = PhysicalCommandBatchV1('physical-command-batch-v1', context, (effort('effort-a',1.),), (), ())
    ack = PhysicalControlReceiptV1('physical-control-receipt-v1', context, batch.identity_hash,
        'native_write_ack', ('effort-a',), 'fake-terminal', 'per-channel')
    accepted = PhysicalControlReceiptV1('physical-control-receipt-v1', context, batch.identity_hash,
        'accepted', ('effort-a',), 'core', 'per-channel')
    calls=[]
    class Recorder:
        def append_transition(self,*args,**kwargs): calls.append((args,kwargs))
    selection=SimpleNamespace(current=SimpleNamespace(execution=SimpleNamespace(
        compiled=plan,controllers=(SimpleNamespace(writer_id='controller-a'),))))
    spec={'kind':'joint','spec_id':'0'*64,'generation':1,'controller_identity':'b'*64,'shape':[8]}
    env=SimpleNamespace(physical_action_spec=lambda:spec, _physical_reset_selection=selection,
        _physical_execution=lambda: selection.current.execution,
        typed_state=SimpleNamespace(view=SimpleNamespace(boundary=context.boundary, sample_clock=context.clock)),
        recorder=Recorder(), obs={'position':np.array([1.])},evaluation=SimpleNamespace(reward=.2,success=False),info={})
    resolved = SimpleNamespace(accepted_receipt=accepted, joints=(ResolvedJointEffortV1(
        'arm','drive','dof0','N*m',1.,('effort-a',),False,False),))
    record_physical_transition(env, np.arange(8.), batch, resolved, ack, terminated=False, truncated=False)
    args,kwargs=calls[0]
    control=kwargs['structured_control'];control.validate();writer=control.writer_controls[0]
    assert tuple(args[0]) == tuple(range(8))
    recorded_spec = writer['requested_action']['physical_action_spec_v1']
    assert recorded_spec['spec_id'] == spec['spec_id'] and recorded_spec['generation'] == 1
    assert tuple(recorded_spec['shape']) == (8,)
    assert writer['controller_target']['identity_hash'] == batch.identity_hash
    assert writer['applied_control']['payload']['native_write_ack']['stage'] == 'native_write_ack'
    assert writer['applied_control']['payload']['independent_measurement'] == 'unavailable'
    assert writer['applied_control']['payload']['admitted_joint_efforts'][0]['value'] == 1.
    assert args[7]['boundary_context_v1']['state_boundary_identity'] == context.boundary.to_mapping()
    assert args[7]['boundary_context_v1']['state_sample_clock'] == context.clock.to_mapping()
