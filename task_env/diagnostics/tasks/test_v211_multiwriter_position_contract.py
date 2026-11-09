"""Provider-free regression coverage for one logical multi-writer Position interval."""
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from task_env.controllers.canonical.contracts import (
    CanonicalControlTarget, GripperControlTarget,
)
from task_env.diagnostics.tasks.test_v211_control_submission_contract import _Clock, _Session
from task_env.runtime.sessions import control
from task_env.runtime.sessions.control_lifecycle import ControlLifecycleDispatchV1


@dataclass(frozen=True)
class _PositionTarget:
    writer_id: str
    controller_identity: str
    binding_identity_hash: str
    source_closure_digest: str
    source_boundary: object
    sample_clock: object
    target: object
    identity_hash: str

    def validate(self):
        pass


class _Profile:
    def __init__(self, writer_id, boundary, clock, binding_identity_hash):
        self.writer_id = writer_id
        self.identity = f'controller-{writer_id}'
        self.source = SimpleNamespace(source_id='task', source_closure_digest='a' * 64)
        self.artifact = SimpleNamespace(identity_hash='b' * 64)
        self.gripper_semantic_id = 'robot/gripper'
        self.generation = 0
        self.requirements = object()
        self._boundary = boundary
        self._clock = clock
        self._binding_identity_hash = binding_identity_hash

    def controller_binding(self):
        return SimpleNamespace(writer_id=self.writer_id)

    def compute(self, _publication, _action, _plan):
        order = tuple(f'robot/joint-{index}' for index in range(1, 8))
        positions = {name: 0.0 for name in order}
        canonical = CanonicalControlTarget(
            'canonical-control-v0', 'b' * 64, self.identity, order,
            positions, positions,
            GripperControlTarget('robot/gripper', .02, 30., .02),
        )
        target = _PositionTarget(
            self.writer_id, self.identity, self._binding_identity_hash, 'a' * 64,
            self._boundary, self._clock, canonical,
            ('1' if self.writer_id == 'a' else '2') * 64,
        )
        return canonical, target


def _run_two_writer_interval(monkeypatch, *, resource_writers=None, fail_writer=None):
    import task_env.controllers.canonical.contracts as contracts

    monkeypatch.setattr(contracts, 'PositionControlTargetV1', _PositionTarget)
    boundary = _Session().boundary
    clock = _Clock()
    publication = SimpleNamespace(view=SimpleNamespace(boundary=boundary, sample_clock=clock))
    plan = SimpleNamespace(
        identity_hash='d' * 64,
        controller_bindings=(SimpleNamespace(writer_id='a'), SimpleNamespace(writer_id='b')),
        resource_writers=(resource_writers or (
            ('arm', 'actuator-a', 'a'), ('hand', 'actuator-b', 'b'),
        )),
    )
    profiles = (_Profile('a', boundary, clock, plan.identity_hash),
                _Profile('b', boundary, clock, plan.identity_hash))
    session = _Session()
    session.boundary = boundary
    writes = []
    steps = []

    def apply(target):
        writes.append(target.controller_identity)
        if target.controller_identity == f'controller-{fail_writer}':
            raise RuntimeError('synthetic provider write failed')
        return SimpleNamespace(target_hash=target.identity_hash)

    session.apply_control = apply
    session.step = lambda: (steps.append('step') or SimpleNamespace(control_step=1))
    next_boundary = SimpleNamespace(control_step=1)
    session.snapshot_v1 = lambda **_kwargs: SimpleNamespace(
        view=SimpleNamespace(boundary=next_boundary, sample_clock=SimpleNamespace(sample_index=1)),
    )
    session._control_lifecycle_dispatch = ControlLifecycleDispatchV1(
        'control-lifecycle-dispatch-v1', 'position-target', 'task', 'a' * 64,
        'b' * 64, session.episode_id, boundary.boundary_id, 0, 0,
        ('controller-a', 'controller-b'), 'prepared',
    )
    monkeypatch.setattr(control, 'prepare_structured_action',
                        lambda *_args: (('a', object()), ('b', object())))
    monkeypatch.setattr(control, '_validate_position_source_boundary',
                        lambda *_args, **_kwargs: plan.identity_hash)
    try:
        result = control.execute_position_control_interval(
            session, profiles, plan, object(), publication,
            scene=None, joint_bindings=None, frame_bindings=None,
        )
    except BaseException as error:
        return session, writes, steps, None, error
    return session, writes, steps, result, None


def test_dual_position_writers_share_one_receipt_and_exact_resource_ownership(monkeypatch):
    session, writes, steps, result, error = _run_two_writer_interval(monkeypatch)
    assert error is None
    assert result is not None
    assert writes == ['controller-a', 'controller-b']
    assert steps == ['step']
    assert session._last_control_submission['status'] == 'acknowledged'
    assert session._last_control_submission['writer_ids'] == ('a', 'b')
    assert session._last_control_submission['resource_owners'] == (
        ('a', ('arm/actuator-a',)), ('b', ('hand/actuator-b',)),
    )
    target_hashes = tuple(row[2].target_hash for row in result[0])
    assert len(target_hashes) == 2 and target_hashes[0] != target_hashes[1]


def test_conflicting_position_resources_fail_before_any_provider_write_or_step(monkeypatch):
    session, writes, steps, result, error = _run_two_writer_interval(
        monkeypatch,
        resource_writers=(('arm', 'same-actuator', 'a'),
                          ('arm', 'same-actuator', 'b')),
    )
    assert isinstance(error, ValueError) and 'conflicting' in str(error)
    assert result is None
    assert writes == [] and steps == []
    assert not hasattr(session, '_control_submission_consumed')
    assert not hasattr(session, '_last_control_submission')


def test_partial_position_write_is_latched_and_interval_cannot_step_or_replay(monkeypatch):
    session, writes, steps, result, error = _run_two_writer_interval(
        monkeypatch, fail_writer='b',
    )
    assert isinstance(error, RuntimeError) and 'provider write failed' in str(error)
    assert result is None
    assert writes == ['controller-a', 'controller-b']
    assert steps == []
    receipt = session._last_control_submission
    assert receipt['status'] == 'failed_partial'
    assert receipt['attempted_writer_ids'] == ('a', 'b')
    assert receipt['completed_writer_ids'] == ('a',)
    assert session._control_lifecycle_dispatch.stage == 'failed'
    assert ('episode-1', session.boundary.boundary_id) in session._control_submission_consumed
