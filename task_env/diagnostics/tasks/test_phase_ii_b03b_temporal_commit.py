"""B03b bounded temporal rules and exactly-once outer-boundary commits."""

import math
from dataclasses import replace

import numpy as np
import pytest

from task_env.artifacts.contracts import Timebase
from task_env.artifacts.state import (
    NativeIntervalEvidence,
    NativeIntervalSample,
    StateBoundaryIdentity,
    StateSampleClock,
    UnavailableStateValue,
)
from task_env.environment import (
    AppliedControl,
    RuntimeSnapshot,
    TaskEvaluation,
    TaskEvaluationContextV1,
    TaskLifecycleAdapter,
    TaskPredicateEvaluationV1,
    TaskPredicateResultV1,
    TemporalPredicateRuleV1,
    StageUnavailableError,
)
from task_env.environment.types import ContactSummary
from task_env.environment.task_definition import TaskDefinitionBase
from task_env.runtime.contracts import BatchState
from task_env.tasks.pendulum import PendulumTaskDefinition


_SCENE_HASH = "a" * 64


class _TemporalProbeDefinition(TaskDefinitionBase):
    def temporal_predicate_rules(self):
        return (
            TemporalPredicateRuleV1("ready_edge", "rising_edge", ("ready",)),
            TemporalPredicateRuleV1("ready_dwell", "dwell", ("ready",), 2),
            TemporalPredicateRuleV1(
                "ordered_ab", "sequence", ("first", "second")
            ),
        )

    def reset(self, snapshot):
        del snapshot
        return TaskEvaluation(0.0, False)

    def evaluate_predicates(self, context):
        values = np.asarray(context.state.qpos, dtype=np.float64).reshape(-1)
        predicates = {}
        for name, index in (("ready", 0), ("first", 1), ("second", 2)):
            value = values[index]
            if math.isnan(float(value)):
                predicates[name] = TaskPredicateResultV1.unavailable(
                    f"{name}_measurement_missing"
                )
            else:
                predicates[name] = TaskPredicateResultV1.available(bool(value))
        return TaskPredicateEvaluationV1.available(predicates)


class _MutablePredicateDefinition(_TemporalProbeDefinition):
    def __init__(self):
        self.ready_override = False

    def evaluate_predicates(self, context):
        evaluation = super().evaluate_predicates(context)
        predicates = dict(evaluation.predicates)
        predicates["ready"] = TaskPredicateResultV1.available(self.ready_override)
        return TaskPredicateEvaluationV1.available(predicates)


class _ToggleNoEvaluatorDefinition(_TemporalProbeDefinition):
    def __init__(self):
        self.has_evaluator = True

    def evaluate_predicates(self, context):
        if not self.has_evaluator:
            return TaskPredicateEvaluationV1.no_evaluator()
        return super().evaluate_predicates(context)


def _boundary(
    control_step,
    *,
    episode_id="episode-b03b",
    reset_suffix="1",
    state_revision=None,
):
    return StateBoundaryIdentity(
        schema_version="state-boundary-identity-v1",
        episode_id=episode_id,
        reset_sample_id="reset-" + reset_suffix * 64,
        scene_identity_hash=_SCENE_HASH,
        scene_instance_id="scene-b03b",
        provider_materialization_id="materialization-b03b",
        control_step=control_step,
        state_revision=(control_step if state_revision is None else state_revision),
    )


def _native_interval(control_step, *, control_substeps=25, physics_dt=0.001):
    if control_step < 1:
        raise ValueError("native interval needs a preceding evaluation boundary")
    before = _boundary(control_step - 1)
    after = _boundary(control_step)
    control_dt = control_substeps * physics_dt
    start = (control_step - 1) * control_dt
    end = start + control_dt
    samples = tuple(
        NativeIntervalSample(
            schema_version="native-interval-sample-v1",
            native_step_index=(control_step - 1) * control_substeps + index,
            interval_start_s=start + index * physics_dt,
            interval_end_s=start + (index + 1) * physics_dt,
            signals=(),
            unavailable=(
                UnavailableStateValue(
                    schema_version="unavailable-state-value-v1",
                    field_name="actuator_force",
                    subject_kind="actuator",
                    entity_id="robot",
                    subject_id="motor",
                    sample_domain="native_step_interval",
                    reason="not measured by deterministic temporal fixture",
                ),
            ),
        )
        for index in range(control_substeps)
    )
    return NativeIntervalEvidence(
        schema_version="native-interval-evidence-v1",
        interval_id=f"interval-{control_step}",
        boundary_before=before,
        boundary_after=after,
        evaluation_start=StateSampleClock(
            "state-sample-clock-v1",
            "evaluation_boundary",
            control_step - 1,
            start,
        ),
        evaluation_end=StateSampleClock(
            "state-sample-clock-v1", "evaluation_boundary", control_step, end
        ),
        physics_dt=physics_dt,
        control_substeps=control_substeps,
        native_step_start=(control_step - 1) * control_substeps,
        samples=samples,
        evidence_reference="test://b03b-native-interval",
    )


def _context(
    values,
    control_step,
    *,
    episode_id="episode-b03b",
    reset_suffix="1",
    native_substeps=None,
    state_revision=None,
):
    state = RuntimeSnapshot(
        qpos=np.asarray(values, dtype=np.float32),
        qvel=np.zeros(0, dtype=np.float32),
    )
    boundary = _boundary(
        control_step,
        episode_id=episode_id,
        reset_suffix=reset_suffix,
        state_revision=state_revision,
    )
    interval = (
        None
        if native_substeps is None
        else _native_interval(control_step, control_substeps=native_substeps)
    )
    clock = StateSampleClock(
        "state-sample-clock-v1",
        "evaluation_boundary",
        control_step,
        float(control_step) * 0.025,
    )
    if interval is not None:
        boundary = interval.boundary_after
        clock = interval.evaluation_end
    return TaskEvaluationContextV1(
        state=state,
        elapsed_steps=control_step,
        boundary_identity=boundary,
        sample_clock=clock,
        native_interval=interval,
    )


def _adapter():
    return TaskLifecycleAdapter(
        task_definition=_TemporalProbeDefinition(), horizon=20, ignore_done=False
    )


def test_temporal_commit_is_explicit_idempotent_ordered_and_one_per_outer_boundary():
    lifecycle = _adapter()
    unbound = TaskEvaluationContextV1(
        state=RuntimeSnapshot(
            qpos=np.zeros(3, dtype=np.float32), qvel=np.zeros(0, dtype=np.float32)
        )
    )
    with pytest.raises(ValueError, match="typed state boundary and sample clock"):
        lifecycle.commit_temporal_predicates(unbound)

    first = _context([0.0, 0.0, 0.0], 0)
    initial = lifecycle.commit_temporal_predicates(first)
    assert initial.resolve("ready_edge").value is False
    assert initial.resolve("ready_dwell").value is False

    native_step = _context([1.0, 1.0, 0.0], 1, native_substeps=25)
    for _ in range(25):
        read = lifecycle.evaluate_predicates(native_step)
        assert read.resolve("ready_dwell").status == "unavailable"
    committed = lifecycle.commit_temporal_predicates(native_step)
    assert committed.resolve("ready_edge").value is True
    assert committed.resolve("ready_dwell").value is False
    assert committed.resolve("ordered_ab").value is False
    assert lifecycle.commit_temporal_predicates(native_step) is committed

    conflicting = _context(
        [0.0, 1.0, 0.0], 1, native_substeps=25
    )
    with pytest.raises(ValueError, match="already committed with different input"):
        lifecycle.commit_temporal_predicates(conflicting)

    next_step = _context([1.0, 0.0, 0.0], 2, native_substeps=25)
    completed = lifecycle.commit_temporal_predicates(next_step)
    assert completed.resolve("ready_edge").value is False
    assert completed.resolve("ready_dwell").value is True
    with pytest.raises(ValueError, match="committed in order"):
        lifecycle.commit_temporal_predicates(native_step)


@pytest.mark.parametrize(
    "changed_field",
    (
        {"site_jacp": np.asarray([[0.0, 0.0, 0.0]], dtype=np.float32)},
        {"site_jacr": np.asarray([[0.0, 0.0, 0.0]], dtype=np.float32)},
        {"contact_summary": ContactSummary({"robot/object": 1})},
        {"simulation_time": 0.025},
    ),
)
def test_duplicate_boundary_rejects_changes_to_any_runtime_snapshot_field(changed_field):
    lifecycle = _adapter()
    original = _context([0.0, 0.0, 0.0], 0)
    committed = lifecycle.commit_temporal_predicates(original)
    changed_state = RuntimeSnapshot(
        qpos=np.asarray(original.state.qpos),
        qvel=np.asarray(original.state.qvel),
        **changed_field,
    )
    changed = TaskEvaluationContextV1(
        state=changed_state,
        elapsed_steps=original.elapsed_steps,
        boundary_identity=original.boundary_identity,
        sample_clock=original.sample_clock,
    )
    assert lifecycle.evaluate_predicates(changed) == lifecycle.evaluate_predicates(original)
    with pytest.raises(ValueError, match="already committed with different input"):
        lifecycle.commit_temporal_predicates(changed)
    assert lifecycle.commit_temporal_predicates(original) is committed


@pytest.mark.parametrize(
    "updates",
    (
        {
            "requested_action": np.asarray([1.0], dtype=np.float32),
            "action_schema_id": "test-action-v1",
        },
        {
            "applied_control": AppliedControl(
                requested_ctrl=np.asarray([1.0], dtype=np.float32),
                applied_ctrl=np.asarray([0.5], dtype=np.float32),
                clipped=True,
            )
        },
        {"timebase": Timebase(physics_dt=0.001, control_substeps=25, control_dt=0.025)},
        {"native_interval": _native_interval(1, control_substeps=25)},
    ),
)
def test_duplicate_boundary_rejects_changed_action_and_interval_inputs(updates):
    lifecycle = _adapter()
    original = _context([0.0, 0.0, 0.0], 1)
    lifecycle.commit_temporal_predicates(original)
    changed = replace(original, **updates)
    assert lifecycle.evaluate_predicates(changed) == lifecycle.evaluate_predicates(original)
    with pytest.raises(ValueError, match="already committed with different input"):
        lifecycle.commit_temporal_predicates(changed)


def test_duplicate_boundary_rejects_changed_predicate_result():
    definition = _MutablePredicateDefinition()
    lifecycle = TaskLifecycleAdapter(
        task_definition=definition, horizon=20, ignore_done=False
    )
    context = _context([0.0, 0.0, 0.0], 0)
    lifecycle.commit_temporal_predicates(context)
    definition.ready_override = True
    with pytest.raises(ValueError, match="already committed with different input"):
        lifecycle.commit_temporal_predicates(context)


def test_temporal_gap_missing_sample_and_reset_have_explicit_memory_behavior():
    lifecycle = _adapter()
    lifecycle.commit_temporal_predicates(_context([0.0, 0.0, 0.0], 0))
    with pytest.raises(ValueError, match="identity changed without lifecycle reset"):
        lifecycle.commit_temporal_predicates(
            _context(
                [1.0, 0.0, 0.0],
                1,
                episode_id="unreset-new-episode",
                reset_suffix="2",
            )
        )
    lifecycle.commit_temporal_predicates(_context([1.0, 0.0, 0.0], 1))

    after_gap = lifecycle.commit_temporal_predicates(
        _context([1.0, 0.0, 0.0], 3)
    )
    assert after_gap.resolve("ready_dwell").value is False
    assert after_gap.resolve("ready_edge").status == "unavailable"
    assert after_gap.resolve("ready_edge").reason == "edge_baseline_unavailable"
    after_gap_dwell = lifecycle.commit_temporal_predicates(
        _context([1.0, 0.0, 0.0], 4)
    )
    assert after_gap_dwell.resolve("ready_dwell").value is True

    missing = lifecycle.commit_temporal_predicates(
        _context([np.nan, 0.0, 0.0], 5)
    )
    assert missing.resolve("ready_dwell").status == "unavailable"
    assert missing.resolve("ready_dwell").reason == "ready_measurement_missing"
    after_missing = lifecycle.commit_temporal_predicates(
        _context([1.0, 0.0, 0.0], 6)
    )
    assert after_missing.resolve("ready_dwell").value is False

    reset_state = RuntimeSnapshot(
        qpos=np.zeros(3, dtype=np.float32), qvel=np.zeros(0, dtype=np.float32)
    )
    lifecycle.reset_task(state=reset_state, legacy_snapshot=reset_state)
    fresh_episode = lifecycle.commit_temporal_predicates(
        _context(
            [1.0, 0.0, 0.0],
            0,
            episode_id="episode-after-reset",
            reset_suffix="2",
        )
    )
    assert fresh_episode.resolve("ready_dwell").value is False


def test_no_evaluator_is_distinct_and_clears_temporal_progress():
    definition = _ToggleNoEvaluatorDefinition()
    lifecycle = TaskLifecycleAdapter(
        task_definition=definition, horizon=20, ignore_done=False
    )
    first = lifecycle.commit_temporal_predicates(_context([1.0, 0.0, 0.0], 0))
    assert first.resolve("ready_dwell").value is False

    definition.has_evaluator = False
    unavailable = lifecycle.commit_temporal_predicates(
        _context([1.0, 0.0, 0.0], 1)
    )
    assert unavailable.resolve("ready").status == "no_evaluator"
    assert unavailable.resolve("ready_dwell").status == "no_evaluator"

    definition.has_evaluator = True
    after_unavailable = lifecycle.commit_temporal_predicates(
        _context([1.0, 0.0, 0.0], 2)
    )
    assert after_unavailable.resolve("ready_dwell").value is False


def test_sequence_advances_on_ordered_rising_edges_and_restarts_after_interruption():
    lifecycle = _adapter()
    trace = (
        ([0.0, 0.0, 0.0], False),
        ([0.0, 1.0, 0.0], False),
        ([0.0, 1.0, 1.0], True),
        ([0.0, 0.0, 0.0], False),
        ([0.0, 0.0, 1.0], False),
    )
    for step, (values, expected) in enumerate(trace):
        result = lifecycle.commit_temporal_predicates(_context(values, step))
        assert result.resolve("ordered_ab").value is expected

    missing = lifecycle.commit_temporal_predicates(
        _context([0.0, np.nan, 0.0], len(trace))
    )
    assert missing.resolve("ordered_ab").status == "unavailable"
    assert missing.resolve("ordered_ab").reason == "first_measurement_missing"


def test_pendulum_temporal_commit_matches_existing_reward_window_and_reset():
    definition = PendulumTaskDefinition(qpos_id=0, qvel_id=0)
    lifecycle = TaskLifecycleAdapter(
        task_definition=definition, horizon=20, ignore_done=False
    )
    state = RuntimeSnapshot(
        qpos=np.asarray([0.0], dtype=np.float32),
        qvel=np.asarray([0.0], dtype=np.float32),
    )
    lifecycle.reset_task(state=state, legacy_snapshot=state)

    for step in range(1, 6):
        context = _context(
            [0.0, 0.0, 0.0],
            step,
            episode_id="pendulum-temporal",
            reset_suffix="3",
        )
        context = TaskEvaluationContextV1(
            state=state,
            requested_action=np.asarray([1.0], dtype=np.float32),
            action_schema_id="task-env.pendulum.torque.v1",
            elapsed_steps=step,
            boundary_identity=context.boundary_identity,
            sample_clock=context.sample_clock,
        )
        for _ in range(2):
            assert lifecycle.evaluate_predicates(context).resolve("task_success").status == "unavailable"
        temporal = lifecycle.commit_temporal_predicates(context)
        reward = definition.evaluate(
            state=context.state,
            action=np.asarray([1.0], dtype=np.float32),
            elapsed_steps=step,
        )
        assert temporal.resolve("task_success").value is (step == 5)
        assert reward.success is (step == 5)
        assert reward.reward_terms["torque_cost"] == -0.001

    lifecycle.reset_task(state=state, legacy_snapshot=state)
    reset_context = TaskEvaluationContextV1(
        state=state,
        elapsed_steps=1,
        boundary_identity=_boundary(
            1, episode_id="pendulum-reset", reset_suffix="4"
        ),
        sample_clock=StateSampleClock(
            "state-sample-clock-v1", "evaluation_boundary", 1, 0.025
        ),
    )
    reset_result = lifecycle.commit_temporal_predicates(reset_context)
    assert reset_result.resolve("task_success").value is False
    assert definition._upright_steps == 0


def test_batch_predicate_reads_remain_available_but_temporal_commit_fails_closed():
    lifecycle = TaskLifecycleAdapter(
        task_definition=PendulumTaskDefinition(qpos_id=0, qvel_id=0),
        horizon=20,
        ignore_done=False,
    )
    state = BatchState(
        {
            "qpos": np.asarray([[0.0]], dtype=np.float32),
            "qvel": np.asarray([[0.0]], dtype=np.float32),
        }
    )
    context = TaskEvaluationContextV1(
        state=state,
        elapsed_steps=np.asarray([0], dtype=np.int64),
        boundary_identity=_boundary(0),
        sample_clock=StateSampleClock(
            "state-sample-clock-v1", "evaluation_boundary", 0, 0.0
        ),
    )
    assert lifecycle.evaluate_predicates(context).resolve("upright").value.tolist() == [True]
    with pytest.raises(StageUnavailableError, match="scalar evaluation boundary"):
        lifecycle.commit_temporal_predicates(context)
