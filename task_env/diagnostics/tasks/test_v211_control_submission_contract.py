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


@dataclass(frozen=True)
class _Clock:
    sample_index: int = 0
    simulation_time_s: float = 0.0


class _Command:
    identity_hash = '1' * 64

    def validate(self):
        if getattr(self, 'invalid', False):
            raise ValueError('nonfinite typed action')


class PhysicalCommandBatchV1:
    identity_hash = '2' * 64

    def validate(self):
        pass


class _ResolvedPhysicalBatchV1:
    input_batch = PhysicalCommandBatchV1()


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
