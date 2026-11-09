"""Pure lifecycle/commit contract tests; no provider or asset parsing."""
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from task_env.runtime.sessions.control_submission import submit_control_command


@dataclass(frozen=True)
class _Boundary:
    episode_id: str = 'episode-1'
    provider_materialization_id: str = 'materialization-1'
    control_step: int = 0
    state_revision: int = 0
    boundary_id: str = 'boundary-1'
    scene_identity_hash: str = 'e' * 64


@dataclass(frozen=True)
class _Clock:
    sample_index: int = 0
    simulation_time_s: float = 0.0


class _Command:
    identity_hash = '1' * 64
    writer_id = 'writer-1'
    controller_identity = 'controller-1'
    source_boundary = _Boundary()
    sample_clock = _Clock()
    source_closure_digest = 'a' * 64
    binding_identity_hash = 'd' * 64
    target = SimpleNamespace(task_artifact_hash='b' * 64)

    def validate(self):
        if getattr(self, 'invalid', False):
            raise ValueError('nonfinite typed action')


class PhysicalCommandBatchV1:
    identity_hash = '2' * 64
    context = SimpleNamespace(source_id='task', source_closure_sha256='a' * 64,
        artifact_sha256='b' * 64, boundary=_Boundary(), clock=_Clock(), generation=0)
    joint_efforts = (SimpleNamespace(contribution=SimpleNamespace(owner_id='pendulum-torque')),)
    body_wrenches = ()
    extensions = ()

    def validate(self):
        pass


class _ResolvedPhysicalBatchV1:
    input_batch = PhysicalCommandBatchV1()
    joints = (SimpleNamespace(entity_id='pendulum', joint_id='hinge'),)
    body_wrenches = ()
    extensions = ()


class _Session:
    _provider = 'mujoco'
    provider_materialization_id = 'materialization-1'
    episode_id = 'episode-1'
    _source = SimpleNamespace(source_id='task', source_closure_digest='a' * 64)
    _artifact = SimpleNamespace(identity_hash='b' * 64)

    def __init__(self):
        self.boundary = _Boundary()
        self.calls = 0

    def state_boundary_identity(self):
        return self.boundary


def _submit(session, command=None, **overrides):
    command = _Command() if command is None else command
    kwargs = dict(command_kind='position-target', command_sha256='1' * 64,
        source_id='task', source_closure_sha256='a' * 64, artifact_sha256='b' * 64,
        boundary=session.boundary, sample_clock=_Clock(), controller_generation=0,
        controller_identities=('controller-1',), writer_ids=('writer-1',),
        resource_ids=('robot/joint-1',), units=('joint-position:rad', 'gripper-position:m'),
        lowering='fake-mujoco-position-write', lower=lambda: _ack())
    kwargs.update(overrides)
    return submit_control_command(session, command, **kwargs)


def _ack():
    return SimpleNamespace(identity_hash='c' * 64)


def test_position_and_effort_commands_share_the_commit_owner(monkeypatch):
    import task_env.controllers.canonical.contracts as contracts
    import task_env.runtime.sessions.physical_control as physical

    monkeypatch.setattr(contracts, 'PositionControlTargetV1', _Command)
    monkeypatch.setattr(physical, 'ResolvedPhysicalBatchV1', _ResolvedPhysicalBatchV1)
    position_session = _Session()
    receipt = _submit(position_session)
    assert receipt.identity_hash == 'c' * 64
    assert position_session._last_control_submission['command_kind'] == 'position-target'
    assert position_session._last_control_submission['schema_version'] == 'control-submission-receipt-v2'
    assert position_session._last_control_submission['units'] == (
        'joint-position:rad', 'gripper-position:m')

    effort_session = _Session()
    effort = _ResolvedPhysicalBatchV1()
    submit_control_command(effort_session, effort, command_kind='physical-effort-batch',
        command_sha256=effort.input_batch.identity_hash, source_id='task',
        source_closure_sha256='a' * 64, artifact_sha256='b' * 64,
        boundary=effort_session.boundary, sample_clock=_Clock(), controller_generation=0,
        controller_identities=('torque-controller',), writer_ids=('pendulum-torque',),
        resource_ids=('pendulum/hinge',), units=('N*m',),
        lowering='fake-mujoco-effort-batch-write', lower=lambda: _ack())
    assert effort_session._last_control_submission['command_kind'] == 'physical-effort-batch'
    assert effort_session._last_control_submission['units'] == ('N*m',)


def test_legacy_v1_submission_receipt_keeps_its_original_mapping_contract():
    from task_env.runtime.sessions.control_submission import ControlSubmissionReceiptV1

    receipt = ControlSubmissionReceiptV1(
        'control-submission-receipt-v1', 'd' * 64, 'position-target', '1' * 64,
        'mujoco', 'materialization-1', 'task', 'a' * 64, 'b' * 64,
        'episode-1', 'boundary-1', 0, 0, 0, 0,
        ('controller-1',), ('writer-1',), ('robot/joint-1',),
        ('joint-position:rad',), 'fake-lowering', 'acknowledged',
        'SimpleNamespace', 'c' * 64,
    )
    receipt.validate()
    assert receipt.to_mapping()['schema_version'] == 'control-submission-receipt-v1'


def test_legacy_canonical_position_target_uses_same_lifecycle_dispatch():
    from task_env.controllers.canonical.contracts import (
        CanonicalControlTarget, GripperControlTarget,
    )
    from task_env.runtime.sessions.control_lifecycle import ControlLifecycleDispatchV1

    session = _Session()
    joint_order = tuple(f'robot/joint-{index}' for index in range(1, 8))
    positions = {joint: 0.0 for joint in joint_order}
    target = CanonicalControlTarget(
        'canonical-control-v0', 'b' * 64, 'controller-1', joint_order,
        positions, positions,
        GripperControlTarget('robot/gripper', 0.02, 30.0, 0.02),
    )
    session._control_lifecycle_dispatch = ControlLifecycleDispatchV1(
        'control-lifecycle-dispatch-v1', 'position-target', 'task', 'a' * 64,
        'b' * 64, 'episode-1', 'boundary-1', 0, 0, ('controller-1',), 'preparing')
    receipt = _submit(
        session, target, command_sha256=target.identity_hash,
        controller_identities=('controller-1',), units=('arm-position:rad', 'gripper-position:m'),
    )
    assert receipt.identity_hash == 'c' * 64
    assert session._control_lifecycle_dispatch.stage == 'committed'
    assert session._last_control_submission['acknowledgement_type'] == 'SimpleNamespace'


def test_shared_commit_rejects_replay_stale_identity_generation_and_resource_conflict(monkeypatch):
    import task_env.controllers.canonical.contracts as contracts
    monkeypatch.setattr(contracts, 'PositionControlTargetV1', _Command)
    session = _Session()
    _submit(session)
    with pytest.raises(ValueError, match='already has a logical submission'):
        _submit(session)

    stale = _Session()
    old_boundary = stale.boundary
    stale.boundary = _Boundary(state_revision=1, boundary_id='boundary-next')
    writes = []
    with pytest.raises(ValueError, match='boundary is stale'):
        _submit(stale, lower=lambda: writes.append('write'), boundary=old_boundary)
    assert writes == []

    generation = _Session()
    generation.physical_control_generation = 4
    with pytest.raises(ValueError, match='generation is stale'):
        _submit(generation, controller_generation=3)

    conflict = _Session()
    with pytest.raises(ValueError, match='resource identities must be unique'):
        _submit(conflict, resource_ids=('robot/joint-1', 'robot/joint-1'))
    assert not hasattr(conflict, '_control_submission_consumed')


def test_shared_commit_validation_failure_never_writes_and_lowering_failure_cannot_replay(monkeypatch):
    import task_env.controllers.canonical.contracts as contracts
    monkeypatch.setattr(contracts, 'PositionControlTargetV1', _Command)
    session = _Session()
    command = _Command()
    command.invalid = True
    writes = []
    with pytest.raises(ValueError, match='nonfinite'):
        _submit(session, command, lower=lambda: writes.append('write'))
    assert writes == [] and not hasattr(session, '_control_submission_consumed')

    failed = _Session()
    def fail():
        writes.append('attempt')
        raise RuntimeError('provider write failed')
    with pytest.raises(RuntimeError, match='provider write failed'):
        _submit(failed, lower=fail)
    with pytest.raises(ValueError, match='already has a logical submission'):
        _submit(failed)
    assert writes == ['attempt']


@pytest.mark.parametrize('field,value', (
    ('source_boundary', _Boundary(state_revision=1, boundary_id='foreign')),
    ('sample_clock', _Clock(simulation_time_s=1.0)),
    ('source_closure_digest', 'f' * 64),
    ('controller_identity', 'foreign-controller'),
    ('writer_id', 'foreign-writer'),
    ('target', SimpleNamespace(task_artifact_hash='f' * 64)),
))
def test_position_inner_identity_must_match_outer_submission(monkeypatch, field, value):
    import task_env.controllers.canonical.contracts as contracts
    monkeypatch.setattr(contracts, 'PositionControlTargetV1', _Command)
    session, command, writes = _Session(), _Command(), []
    setattr(command, field, value)
    with pytest.raises(ValueError, match='position target identity'):
        _submit(session, command, lower=lambda: writes.append('write'))
    assert not writes and not hasattr(session, '_control_submission_consumed')


def test_physical_inner_context_must_match_outer_submission(monkeypatch):
    import task_env.runtime.sessions.physical_control as physical
    monkeypatch.setattr(physical, 'ResolvedPhysicalBatchV1', _ResolvedPhysicalBatchV1)
    session = _Session()
    command = _ResolvedPhysicalBatchV1()
    command.input_batch = PhysicalCommandBatchV1()
    command.input_batch.context = SimpleNamespace(source_id='foreign',
        source_closure_sha256='a' * 64, artifact_sha256='b' * 64,
        boundary=session.boundary, clock=_Clock(), generation=0)
    with pytest.raises(ValueError, match='physical batch context'):
        _submit(session, command, command_kind='physical-effort-batch',
                command_sha256='2' * 64)
    assert not hasattr(session, '_control_submission_consumed')


def test_preflight_does_not_consume_boundary_or_call_lowerer(monkeypatch):
    import task_env.controllers.canonical.contracts as contracts
    from task_env.runtime.sessions.control_submission import _preflight_control_command
    monkeypatch.setattr(contracts, 'PositionControlTargetV1', _Command)
    session, writes = _Session(), []
    payload, identity, _ = _preflight_control_command(
        session, _Command(), command_kind='position-target', command_sha256='1' * 64,
        source_id='task', source_closure_sha256='a' * 64, artifact_sha256='b' * 64,
        boundary=session.boundary, sample_clock=_Clock(), controller_generation=0,
        controller_identities=('controller-1',), writer_ids=('writer-1',),
        resource_ids=('robot/joint-1',), units=('joint-position:rad',),
        lowering='fake-lowerer', lower=lambda: writes.append('write'))
    assert len(identity) == 64 and payload['command_sha256'] == '1' * 64
    assert not writes and not hasattr(session, '_control_submission_consumed')
    # The unchanged entry point can still commit the same boundary exactly once.
    _submit(session)
    with pytest.raises(ValueError, match='already has a logical submission'):
        _submit(session)


def test_position_resources_are_checked_against_materialized_plan(monkeypatch):
    import task_env.controllers.canonical.contracts as contracts
    import task_env.runtime.sessions.control as control
    monkeypatch.setattr(contracts, 'PositionControlTargetV1', _Command)
    class Plan:
        identity_hash = 'd' * 64
        _compiled = True
        scene_identity_hash = 'e' * 64
        artifact_identity_hash = 'b' * 64
        source_closure_digest = 'a' * 64
        resource_writers = (('robot', 'joint-1', 'writer-1'),)
    monkeypatch.setattr(control, 'ControlBindingPlanV1', Plan)
    session = _Session()
    session._control_binding_plan = Plan()
    session._position_writer_id = 'writer-1'
    session._position_profile_identity = 'controller-1'
    session._artifact = SimpleNamespace(identity_hash='b' * 64,
        timebase=SimpleNamespace(control_substeps=5, physics_dt=.002, control_dt=.01))
    writes = []
    with pytest.raises(ValueError, match='resources differ from the materialized binding'):
        _submit(session, resource_ids=('robot/forged',),
                resource_owners=(('writer-1', ('robot/forged',)),),
                lower=lambda: writes.append('write'))
    assert not writes and not hasattr(session, '_control_submission_consumed')
    session._position_profile_identity = 'stale-controller'
    with pytest.raises(ValueError, match='not the admitted writer'):
        _submit(session, lower=lambda: writes.append('write'))
    assert not writes and not hasattr(session, '_control_submission_consumed')
    session._position_profile_identity = 'controller-1'
    _submit(session)
    outer = session._last_scene_control_submission
    assert outer['inner_submission_id'] == session._last_control_submission['submission_id']
    assert outer['inner_command_sha256'] == '1' * 64
    assert outer['interval']['contributions'][0]['controller_generation'] is None

    bad_timebase = _Session()
    bad_timebase._control_binding_plan = Plan()
    bad_timebase._position_writer_id = 'writer-1'
    bad_timebase._position_profile_identity = 'controller-1'
    bad_timebase._artifact = SimpleNamespace(identity_hash='b' * 64,
        timebase=SimpleNamespace(control_substeps=5, physics_dt=.002, control_dt=.011))
    with pytest.raises(ValueError, match='not aligned'):
        _submit(bad_timebase)
    assert not hasattr(bad_timebase, '_control_submission_consumed')


@pytest.mark.parametrize('writers,resources', (
    (('foreign-writer',), ('pendulum/hinge',)),
    (('pendulum-torque',), ('pendulum/forged',)),
))
def test_physical_resources_and_writers_match_batch(monkeypatch, writers, resources):
    import task_env.runtime.sessions.physical_control as physical
    monkeypatch.setattr(physical, 'ResolvedPhysicalBatchV1', _ResolvedPhysicalBatchV1)
    session, writes = _Session(), []
    with pytest.raises(ValueError, match='physical batch writers or resources'):
        _submit(session, _ResolvedPhysicalBatchV1(), command_kind='physical-effort-batch',
                command_sha256='2' * 64, writer_ids=writers, resource_ids=resources,
                lower=lambda: writes.append('write'))
    assert not writes and not hasattr(session, '_control_submission_consumed')


def test_scene_resource_admission_allows_disjoint_fragments_for_same_writer():
    from task_env.runtime.sessions.control_submission import _validate_resource_intervals
    authority = (('writer-1', ('robot/joint-1',)),)
    _validate_resource_intervals((('writer-1', 'robot/joint-1', 0, 2),
                                  ('writer-1', 'robot/joint-1', 2, 5)),
                                 writer_resources=authority, substeps=5)
    with pytest.raises(ValueError, match='claims overlap'):
        _validate_resource_intervals((('writer-1', 'robot/joint-1', 0, 3),
                                      ('writer-1', 'robot/joint-1', 2, 5)),
                                     writer_resources=authority, substeps=5)
    with pytest.raises(ValueError, match='not authorized'):
        _validate_resource_intervals((('writer-1', 'robot/other', 0, 1),),
                                     writer_resources=authority, substeps=5)
    with pytest.raises(ValueError, match='half-open'):
        _validate_resource_intervals((('writer-1', 'robot/joint-1', 0, 5.0),),
                                     writer_resources=authority, substeps=5)


def test_position_scene_interval_retains_each_admitted_controller_generation(monkeypatch):
    import task_env.controllers.canonical.contracts as contracts
    import task_env.runtime.sessions.control as control
    from task_env.runtime.sessions.control_submission import (
        PositionControlBatchV1, prepare_position_scene_interval,
    )
    monkeypatch.setattr(contracts, 'PositionControlTargetV1', _Command)
    class Plan:
        identity_hash = 'd' * 64
        _compiled = True
        scene_identity_hash = 'e' * 64
        artifact_identity_hash = 'b' * 64
        source_closure_digest = 'a' * 64
        resource_writers = (('robot', 'joint-1', 'writer-1'),
                            ('robot', 'joint-2', 'writer-2'))
    monkeypatch.setattr(control, 'ControlBindingPlanV1', Plan)
    session = _Session()
    session._artifact = SimpleNamespace(identity_hash='b' * 64,
        timebase=SimpleNamespace(control_substeps=5, physics_dt=.002, control_dt=.01))
    session._position_profiles_by_writer = {
        'writer-1': SimpleNamespace(identity='controller-1', generation=1),
        'writer-2': SimpleNamespace(identity='controller-2', generation=7),
    }
    session._position_profile_generations = {'writer-1': 1, 'writer-2': 7}
    first, second = _Command(), _Command()
    second.writer_id, second.controller_identity = 'writer-2', 'controller-2'
    interval = prepare_position_scene_interval(session=session, plan=Plan(),
        command=PositionControlBatchV1((first, second)), source_id='task',
        source_closure_sha256='a' * 64, artifact_sha256='b' * 64,
        boundary=session.boundary, sample_clock=_Clock(),
        resource_owners=(('writer-1', ('robot/joint-1',)), ('writer-2', ('robot/joint-2',))))
    assert [(item.writer_id, item.controller_generation) for item in interval.contributions] == [
        ('writer-1', 1), ('writer-2', 7)]
    assert not hasattr(session, '_control_submission_consumed')
    session._position_profiles_by_writer['writer-2'].generation = 8
    with pytest.raises(ValueError, match='generation differs from materialization'):
        prepare_position_scene_interval(session=session, plan=Plan(),
            command=PositionControlBatchV1((first, second)), source_id='task',
            source_closure_sha256='a' * 64, artifact_sha256='b' * 64,
            boundary=session.boundary, sample_clock=_Clock(),
            resource_owners=(('writer-1', ('robot/joint-1',)), ('writer-2', ('robot/joint-2',))))


def test_subject_scene_submission_checks_bound_writer_and_live_target(monkeypatch):
    from task_env.controllers.canonical.contracts import CanonicalControlTarget, GripperControlTarget
    import task_env.assembly.source_composition as composition

    class SubjectBinding:
        pass

    monkeypatch.setattr(composition, 'PositionSubjectControlBindingV1', SubjectBinding)
    binding = SubjectBinding()
    binding.identity_hash = 'f' * 64
    binding.plan = SimpleNamespace(_compiled=True, scene_identity_hash='e' * 64,
        artifact_identity_hash='b' * 64, source_closure_digest='a' * 64,
        controller_bindings=(SimpleNamespace(controller_identity='controller-1'),),
        resource_writers=(('robot', 'joint-1', 'writer-1'),))
    joints = tuple(f'robot/joint-{i}' for i in range(1, 8))
    positions = dict.fromkeys(joints, 0.0)
    target = CanonicalControlTarget('canonical-control-v0', 'b' * 64, 'controller-1',
        joints, positions, positions, GripperControlTarget('robot/gripper', .02, 30., .02))

    def session():
        value = _Session()
        value._source = SimpleNamespace(source_id='task', source_closure_digest='a' * 64,
            position_subject_binding=binding, composition_runtime_input=None)
        value._artifact = SimpleNamespace(identity_hash='b' * 64,
            timebase=SimpleNamespace(control_substeps=5, physics_dt=.002, control_dt=.01))
        value._subject_position_inflight = (('materialization-1', 'episode-1', 0, 0),
                                             target.identity_hash, 'controller-1')
        return value

    for mode, kind, policy in (('boundary-hold', 'position-target', 'exclusive'),
                                ('native-feedback', 'position-reference-native-feedback', 'controller-managed')):
        current = session()
        _submit(current, target, command_sha256=target.identity_hash, subject_execution_mode=mode)
        outer = current._last_scene_control_submission
        assert outer['status'] == 'acknowledged'
        assert outer['inner_command_sha256'] == target.identity_hash
        contribution, = outer['interval']['contributions']
        assert (contribution['command_kind'], contribution['composition']) == (kind, policy)
        assert contribution['controller_generation'] is None
        assert (contribution['start_substep'], contribution['end_substep']) == (0, 5)

    for field in ('inflight', 'resource'):
        current = session()
        writes = []
        kwargs = {}
        if field == 'inflight':
            current._subject_position_inflight = None
        else:
            kwargs.update(resource_ids=('robot/other',), resource_owners=(('writer-1', ('robot/other',)),))
        with pytest.raises(ValueError):
            _submit(current, target, command_sha256=target.identity_hash,
                    subject_execution_mode='boundary-hold', lower=lambda: writes.append(1), **kwargs)
        assert not writes and not getattr(current, '_control_submission_consumed', set())


def test_caller_com_contribution_is_in_the_single_committed_scene(monkeypatch):
    from task_env.controllers.canonical.physical_commands import ExternalComWrenchV1
    import task_env.controllers.canonical.contracts as contracts
    import task_env.runtime.sessions.control_submission as submission

    monkeypatch.setattr(contracts, 'CanonicalControlTarget', _Command)
    session = _Session()
    session._source = SimpleNamespace(source_id='task', source_closure_digest='a' * 64,
                                      position_subject_binding=object())
    command = _Command()
    command.task_artifact_hash = 'b' * 64
    base = submission.SceneCommandIntervalV1('scene-command-interval-v1', 'task', 'a' * 64,
        'b' * 64, session.boundary, _Clock(), 'd' * 64, None, None, None, .002, 5,
        (submission.SceneCommandContributionV1('robot-controller', 'position-target', ('rad',),
             'exclusive', None, 'writer-1', 'controller-1', None, command.identity_hash,
             ('robot/joint-1',), 0, 5),))
    monkeypatch.setattr(submission, 'prepare_subject_position_scene_interval', lambda **_: base)
    request = ExternalComWrenchV1('external-com-wrench-v1', 'push', 'cube', (0., 0., 1.), (0., 0., 0.))
    external = SimpleNamespace(rows=((request, 1),), authorized=False, verify=lambda value: None)
    session._external_com_port = external
    writes = []
    _submit(session, command, subject_execution_mode='boundary-hold',
            lower=lambda: (writes.append(external.authorized), _ack())[1])
    assert writes == [True]
    scene = session._last_scene_control_submission
    assert scene['status'] == 'acknowledged'
    assert scene['inner_submission_id'] == session._last_control_submission['submission_id']
    first, second = scene['interval']['contributions']
    assert first['command_sha256'] == command.identity_hash
    assert (second['producer_kind'], second['physical_effect_id'], second['resources']) == (
        'caller', 'push', ('body:cube',))
    assert second['command_sha256'] == request.identity_hash


def test_split_subject_commit_rejects_forged_component_before_consuming_boundary(monkeypatch):
    from dataclasses import replace
    from task_env.controllers.canonical.contracts import CanonicalControlTarget, GripperControlTarget
    from task_env.controllers.canonical.kinematics import ARM
    from task_env.controllers.canonical.split_panda_position import (
        ARM_WRITER, HAND_WRITER, SplitPositionBundleV1, split_identity,
    )
    import task_env.assembly.source_composition as composition
    class SubjectBinding:
        pass
    monkeypatch.setattr(composition, 'PositionSubjectControlBindingV1', SubjectBinding)
    arm_id, hand_id = 'a' * 64, 'c' * 64
    positions = dict.fromkeys(ARM, 0.)
    hand = GripperControlTarget('panda-v1/gripper', .02, 10., .02)
    target = CanonicalControlTarget('canonical-control-v0', 'b' * 64, split_identity(arm_id, hand_id),
                                    ARM, positions, positions, hand)
    bundle = SplitPositionBundleV1(arm_id, hand_id, (0.,) * 7, (0.,) * 7, hand, target.identity_hash)
    binding = SubjectBinding(); binding.identity_hash = 'f' * 64
    binding.plan = SimpleNamespace(_compiled=True, scene_identity_hash='e' * 64,
        artifact_identity_hash='b' * 64, source_closure_digest='a' * 64,
        controller_bindings=(SimpleNamespace(writer_id=ARM_WRITER, controller_identity=arm_id),
                             SimpleNamespace(writer_id=HAND_WRITER, controller_identity=hand_id)),
        resource_writers=(('arm', 'motor', ARM_WRITER), ('hand', 'motor', HAND_WRITER)))
    owners = ((ARM_WRITER, ('arm/motor',)), (HAND_WRITER, ('hand/motor',)))
    def fresh(component):
        value = _Session()
        value._source = SimpleNamespace(source_id='task', source_closure_digest='a' * 64,
            position_subject_binding=binding, composition_runtime_input=None)
        value._artifact = SimpleNamespace(identity_hash='b' * 64,
            timebase=SimpleNamespace(control_substeps=5, physics_dt=.002, control_dt=.01))
        value._subject_position_inflight = (('materialization-1', 'episode-1', 0, 0),
                                             target.identity_hash, target.controller_identity)
        value._subject_position_split_bundle = component
        return value
    kwargs = dict(command_sha256=target.identity_hash, controller_identities=(target.controller_identity,),
                  writer_ids=(ARM_WRITER, HAND_WRITER), resource_ids=('arm/motor', 'hand/motor'),
                  resource_owners=owners, subject_execution_mode='boundary-hold')
    bad = fresh(replace(bundle, hand_identity='d' * 64)); writes=[]
    with pytest.raises(ValueError, match='source-bound plan'):
        _submit(bad, target, lower=lambda: writes.append(1), **kwargs)
    assert not writes and not getattr(bad, '_control_submission_consumed', set())
    good = fresh(bundle); _submit(good, target, **kwargs)
    first, second = good._last_scene_control_submission['interval']['contributions']
    assert (first['writer_id'], first['command_sha256']) == (ARM_WRITER, bundle.arm_hash)
    assert (second['writer_id'], second['command_sha256']) == (HAND_WRITER, bundle.hand_hash)
