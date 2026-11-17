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
        compiled=plan,controllers=(SimpleNamespace(writer_id='controller-a'),), scene_body_producers=())))
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


def test_scene_load_is_recorded_separately_from_controller_target():
    from task_env.artifacts import FrameReference
    from task_env.controllers.canonical.physical_commands import BodyWrenchV1, ContributionPolicyV1
    from task_env.runtime.sessions.physical_control import SceneBodyProducerV1
    plan, context, effort, _ = _case()
    frame = FrameReference('arm', 'base')
    policy = ContributionPolicyV1('physical-contribution-policy-v1', 'load-a', 'load-effect',
                                  'caller-a', 'exclusive', 'reject_outside', 'one_interval')
    wrench = BodyWrenchV1('body-wrench-v1', context, policy, 'arm', 'body-a', frame,
        (0., 0., 0.), frame, (0., 0., 0.), frame, (1., 0., 0.), (0., 0., 0.))
    batch = PhysicalCommandBatchV1('physical-command-batch-v1', context, (effort('effort-a', 1.),), (wrench,), ())
    ack = PhysicalControlReceiptV1('physical-control-receipt-v1', context, batch.identity_hash,
        'native_write_ack', ('effort-a', 'load-a'), 'fake-terminal', 'per-channel')
    accepted = PhysicalControlReceiptV1('physical-control-receipt-v1', context, batch.identity_hash,
        'accepted', ('effort-a', 'load-a'), 'core', 'per-channel')
    calls = []
    class Recorder:
        def append_transition(self, *args, **kwargs): calls.append(kwargs)
    execution = SimpleNamespace(compiled=plan, controllers=(SimpleNamespace(writer_id='controller-a'),),
        scene_body_producers=(SceneBodyProducerV1('caller-a', 'caller', (('arm', 'body-a'),)),))
    spec = {'kind': 'joint', 'spec_id': '0'*64, 'generation': 1, 'controller_identity': 'b'*64, 'shape': [8]}
    env = SimpleNamespace(physical_action_spec=lambda: spec, _physical_reset_selection=object(),
        _physical_execution=lambda: execution, session=SimpleNamespace(_last_scene_control_submission={'status':'ack'}),
        typed_state=SimpleNamespace(view=SimpleNamespace(boundary=context.boundary, sample_clock=context.clock)),
        recorder=Recorder(), obs={'position':np.array([1.])}, evaluation=SimpleNamespace(reward=.2,success=False), info={})
    resolved = SimpleNamespace(accepted_receipt=accepted, joints=(), body_wrenches=(),
                               binding_sha256=plan.binding.identity_hash)
    record_physical_transition(env, np.arange(8.), batch, resolved, ack, terminated=False, truncated=False)
    writer = calls[0]['structured_control'].writer_controls[0]
    assert not writer['controller_target']['payload']['body_wrenches']
    scene = writer['applied_control']['payload']['scene_physical_batch_v1']
    assert scene['batch_sha256'] == batch.identity_hash
    assert scene['batch']['body_wrenches'][0]['contribution']['owner_id'] == 'caller-a'
    assert writer['controller_target']['identity_hash'] != scene['batch_sha256']


def test_device_record_reader_rejects_foreign_writer_binding_and_clock():
    """A device H5 load must match its recorded source binding and previous boundary."""
    from copy import deepcopy
    from dataclasses import replace
    import pytest
    from task_env.artifacts import FrameReference
    from task_env.controllers.canonical.physical_commands import PhysicalBodyBindingV1
    from task_env.recorders.h5 import _validate_device_scene_record

    compiled, _context, _effort, _ = _case()
    body = PhysicalBodyBindingV1('physical-body-binding-v1', 'arm', 'body-a',
                                 FrameReference('arm', 'base'), 'native-body', ('caller-a',))
    binding = replace(compiled.binding, bodies=(body,))
    declaration = {'binding': binding.to_mapping(), 'binding_sha256': binding.identity_hash,
                   'controller_writer_id': 'controller-a',
                   'native_build': {'binding_sha256': binding.identity_hash,
                                    'source_closure_sha256': binding.source_closure_sha256,
                                    'materialization_id': 'materialization-a', 'provenance': 'native_build',
                                    'bodies': [{'entity_id': 'arm', 'body_id': 'body-a',
                                                'native_body': 'native-body', 'native_id': 1}]},
                   'producers': [{'writer_id': 'caller-a', 'producer_kind': 'caller',
                                  'body_keys': [['arm', 'body-a']]}]}
    identity = {'source_id': binding.source_id, 'source_closure_sha256': binding.source_closure_sha256,
                'artifact_sha256': binding.artifact_sha256, 'materialization_id': 'materialization-a',
                'generation': 1, 'revision': 1, 'native_step': 0, 'native_time_s': 0., 'control_dt_s': .01}
    before = {**identity, 'episode_id': 4, 'episode_step': 0}
    load = {'binding_sha256': binding.identity_hash, 'body_key': ['arm', 'body-a'],
            'boundary': identity, 'composition': 'exclusive', 'controller_writer_id': 'controller-a',
            'episode_ids': 4, 'episode_steps': 0, 'frame': 'world', 'moment_reference': 'body_com',
            'native_ack': 'worker_step_completed', 'physical_effect_id': 'effect-a',
            'producer_kind': 'caller', 'scene_admission': 'common_resource_conflict_rules',
            'units': ['N', 'N*m'], 'values': [1., 0., 0., 0., 0., 0.], 'writer_id': 'caller-a'}
    after = {**identity, 'revision': 2, 'native_step': 5, 'native_time_s': .01,
             'episode_id': 4, 'episode_step': 1, 'scene_physical_v1': [load]}
    _validate_device_scene_record([before, after], declaration)
    for field, value in [('writer_id', 'intruder'), ('binding_sha256', '0' * 64),
                         ('episode_steps', 9), ('native_ack', 'unknown')]:
        tampered = deepcopy([before, after])
        tampered[1]['scene_physical_v1'][0][field] = value
        with pytest.raises(ValueError):
            _validate_device_scene_record(tampered, declaration)
    forged = deepcopy(declaration)
    forged['native_build']['bodies'][0]['native_body'] = 'foreign-body'
    with pytest.raises(ValueError, match='native body build'):
        _validate_device_scene_record([before, after], forged)
