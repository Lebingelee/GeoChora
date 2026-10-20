"""B03a read-only predicate, action-context and legacy reward oracles."""

from types import SimpleNamespace

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
    TaskEvaluationContextV1,
    TaskLifecycleAdapter,
    TaskPredicateEvaluationV1,
    TaskPredicateResultV1,
)
from task_env.environment.task_definition import TaskDefinitionBase
from task_env.robots.pendulum import PENDULUM_ACTION_SCHEMA_ID
from task_env.runtime.contracts import BatchState
from task_env.tasks.pendulum import (
    PENDULUM_CONTROL_SUBSTEPS,
    PENDULUM_PHYSICS_DT,
    PendulumTaskDefinition,
)
from task_env.tasks.pick_cube.task import (
    PickCubeTaskDefinition,
    semantic_definition,
)


class _FalseAndUnavailablePredicates(TaskDefinitionBase):
    def evaluate_predicates(self, context):
        assert context.requested_action["command"].flags.writeable is False
        return TaskPredicateEvaluationV1.available(
            {
                "gate_open": TaskPredicateResultV1.available(False),
                "contact": TaskPredicateResultV1.unavailable(
                    "required_contact_summary_unavailable"
                ),
            }
        )


def _pendulum_snapshot(theta=0.0, theta_dot=0.0):
    return RuntimeSnapshot(
        qpos=np.asarray([theta], dtype=np.float32),
        qvel=np.asarray([theta_dot], dtype=np.float32),
    )


def _pendulum_context(
    state, *, action=1.0, applied_action=None, elapsed_steps=1
):
    applied = action if applied_action is None else applied_action
    return TaskEvaluationContextV1(
        state=state,
        requested_action=np.asarray([action], dtype=np.float32),
        action_schema_id=PENDULUM_ACTION_SCHEMA_ID,
        applied_control=AppliedControl(
            requested_ctrl=np.asarray([action], dtype=np.float32),
            applied_ctrl=np.asarray([applied], dtype=np.float32),
            clipped=applied != action,
        ),
        elapsed_steps=elapsed_steps,
        timebase=Timebase(
            physics_dt=PENDULUM_PHYSICS_DT,
            control_substeps=PENDULUM_CONTROL_SUBSTEPS,
            control_dt=PENDULUM_PHYSICS_DT * PENDULUM_CONTROL_SUBSTEPS,
        ),
    )


def _native_interval_evidence(*, physics_dt=0.01, control_substeps=1):
    scene_hash = "a" * 64
    before = StateBoundaryIdentity(
        schema_version="state-boundary-identity-v1",
        episode_id="episode-test",
        reset_sample_id="reset-" + "b" * 64,
        scene_identity_hash=scene_hash,
        scene_instance_id="scene-test",
        provider_materialization_id="materialization-test",
        control_step=0,
        state_revision=0,
    )
    after = StateBoundaryIdentity(
        schema_version="state-boundary-identity-v1",
        episode_id="episode-test",
        reset_sample_id=before.reset_sample_id,
        scene_identity_hash=scene_hash,
        scene_instance_id="scene-test",
        provider_materialization_id="materialization-test",
        control_step=1,
        state_revision=1,
    )
    start_time = 0.0
    end_time = start_time + physics_dt * control_substeps
    return NativeIntervalEvidence(
        schema_version="native-interval-evidence-v1",
        interval_id="interval-test",
        boundary_before=before,
        boundary_after=after,
        evaluation_start=StateSampleClock(
            "state-sample-clock-v1", "evaluation_boundary", 0, start_time
        ),
        evaluation_end=StateSampleClock(
            "state-sample-clock-v1", "evaluation_boundary", 1, end_time
        ),
        physics_dt=physics_dt,
        control_substeps=control_substeps,
        native_step_start=0,
        samples=tuple(
            NativeIntervalSample(
                schema_version="native-interval-sample-v1",
                native_step_index=index,
                interval_start_s=start_time + index * physics_dt,
                interval_end_s=start_time + (index + 1) * physics_dt,
                signals=(),
                unavailable=(
                    UnavailableStateValue(
                        schema_version="unavailable-state-value-v1",
                        field_name="actuator_force",
                        subject_kind="actuator",
                        entity_id="arm",
                        subject_id="joint1",
                        sample_domain="native_step_interval",
                        reason="not measured by this test fixture",
                    ),
                ),
            )
            for index in range(control_substeps)
        ),
        evidence_reference="test://native-interval-evidence",
    )


def test_predicate_states_distinguish_false_missing_input_and_no_evaluator():
    state = _pendulum_snapshot()
    raw_action = np.asarray([1.0], dtype=np.float32)
    context = TaskEvaluationContextV1(
        state=state,
        requested_action={"command": raw_action},
        action_schema_id="test-action-v1",
    )
    raw_action[0] = 7.0
    assert context.requested_action["command"].tolist() == [1.0]
    assert context.requested_action["command"].flags.writeable is False
    assert context.declared_control_interval_s is None
    assert context.measured_control_interval_s is None

    no_evaluator = TaskLifecycleAdapter(
        task_definition=TaskDefinitionBase(), horizon=10, ignore_done=False
    ).evaluate_predicates(context)
    assert no_evaluator.resolve("gate_open").status == "no_evaluator"

    evaluation = TaskLifecycleAdapter(
        task_definition=_FalseAndUnavailablePredicates(),
        horizon=10,
        ignore_done=False,
    ).evaluate_predicates(context)
    false = evaluation.resolve("gate_open")
    unavailable = evaluation.resolve("contact")
    missing = evaluation.resolve("not_declared")
    assert (false.status, false.value) == ("available", False)
    assert (unavailable.status, unavailable.value) == (
        "unavailable",
        None,
    )
    assert unavailable.reason == "required_contact_summary_unavailable"
    assert (missing.status, missing.reason) == (
        "unavailable",
        "predicate_not_produced",
    )


def test_evaluation_context_distinguishes_declared_cadence_from_measured_interval():
    timebase = Timebase(physics_dt=0.01, control_substeps=1, control_dt=0.01)
    interval = _native_interval_evidence()
    context = TaskEvaluationContextV1(
        state=_pendulum_snapshot(),
        timebase=timebase,
        native_interval=interval,
    )
    assert context.declared_control_interval_s == 0.01
    assert context.measured_control_interval_s == 0.01

    mismatched = Timebase(physics_dt=0.005, control_substeps=2, control_dt=0.01)
    with pytest.raises(ValueError, match="disagrees with the declared Timebase"):
        TaskEvaluationContextV1(
            state=_pendulum_snapshot(),
            timebase=mismatched,
            native_interval=interval,
        )


def test_pendulum_predicate_reads_do_not_commit_or_change_torque_reward_window():
    definition = PendulumTaskDefinition(qpos_id=0, qvel_id=0)
    state = _pendulum_snapshot()
    definition.reset(state)
    lifecycle = TaskLifecycleAdapter(
        task_definition=definition, horizon=100, ignore_done=False
    )
    context = _pendulum_context(state, applied_action=0.5)
    assert context.requested_action.tolist() == [1.0]
    assert context.applied_control.applied_ctrl.tolist() == [0.5]

    for _ in range(3):
        predicates = lifecycle.evaluate_predicates(context)
        assert predicates.resolve("upright").value is True
        assert predicates.resolve("task_success").status == "unavailable"
        assert predicates.resolve("task_success").reason == "predicate_not_produced"
        assert definition._upright_steps == 0

    for step in range(1, 6):
        evaluation = definition.evaluate(
            state=context.state,
            action=np.asarray([1.0], dtype=np.float32),
            elapsed_steps=step,
        )
        assert evaluation.reward_terms["torque_cost"] == -0.001
        assert evaluation.success is (step == 5)
        lifecycle.evaluate_predicates(context)
        assert definition._upright_steps == step


def test_pendulum_batch_predicate_is_read_only_and_batch_reward_oracle_is_unchanged():
    definition = PendulumTaskDefinition(qpos_id=0, qvel_id=0)
    state = BatchState(
        {
            "qpos": np.asarray([[0.0], [0.4]], dtype=np.float32),
            "qvel": np.asarray([[0.0], [0.0]], dtype=np.float32),
        }
    )
    context = _pendulum_context(
        state,
        action=1.0,
        elapsed_steps=np.asarray([1, 1], dtype=np.int64),
    )
    lifecycle = TaskLifecycleAdapter(
        task_definition=definition, horizon=100, ignore_done=False
    )
    predicates = lifecycle.evaluate_predicates(context)
    assert predicates.resolve("upright").value.tolist() == [True, False]
    assert definition._upright_steps == 0

    for step in range(1, 6):
        result = definition.evaluate(
            state=context.state,
            action=np.asarray([[1.0], [-2.0]], dtype=np.float32),
            elapsed_steps=np.asarray([step, step], dtype=np.int32),
        )
        np.testing.assert_allclose(
            result.reward_terms["torque_cost"],
            np.asarray([-0.001, -0.004], dtype=np.float32),
            rtol=1e-7,
            atol=0.0,
        )
        assert result.success.tolist() == [step == 5, False]
        lifecycle.evaluate_predicates(context)
        assert definition._upright_steps.tolist() == [step, 0]


def test_pickcube_typed_lift_predicate_reuses_lift_only_reward_oracle():
    references = SimpleNamespace(
        agents={
            "panda-v1": SimpleNamespace(
                eef_site_id=0, gripper_qpos_ids=np.asarray([0, 1])
            )
        },
        objects={"cube-v1": SimpleNamespace(body_ids=(0,))},
    )
    definition = PickCubeTaskDefinition(references=references)
    params = semantic_definition().parameters_si
    threshold = params["rest_height"] + params["lift_height"]

    for z_value, expected in ((threshold - 1e-5, False), (threshold + 1e-5, True)):
        state = RuntimeSnapshot(
            qpos=np.asarray([0.2, 0.2], dtype=np.float32),
            qvel=np.zeros(0, dtype=np.float32),
            body_xpos=np.asarray([[0.0, 0.0, z_value]], dtype=np.float32),
            site_xpos=np.asarray([[2.0, 2.0, 2.0]], dtype=np.float32),
        )
        context = TaskEvaluationContextV1(state=state)
        predicate = TaskLifecycleAdapter(
            task_definition=definition, horizon=10, ignore_done=False
        ).evaluate_predicates(context).resolve("cube_lifted")
        legacy = definition.evaluate(state, np.asarray([0.0]), state)
        assert predicate.status == "available"
        assert predicate.value is expected
        assert legacy.success is expected
        # The raised but distant cube still succeeds under the frozen lift-only oracle.
        if expected:
            assert legacy.metrics["grasped_cube"] is False

    missing = RuntimeSnapshot(
        qpos=np.zeros(2, dtype=np.float32),
        qvel=np.zeros(0, dtype=np.float32),
    )
    unavailable = TaskLifecycleAdapter(
        task_definition=definition, horizon=10, ignore_done=False
    ).evaluate_predicates(TaskEvaluationContextV1(state=missing)).resolve("cube_lifted")
    assert unavailable.status == "unavailable"
    assert unavailable.reason == "required_pickcube_state_unavailable"

    nonfinite = RuntimeSnapshot(
        qpos=np.zeros(2, dtype=np.float32),
        qvel=np.zeros(0, dtype=np.float32),
        body_xpos=np.asarray([[0.0, 0.0, np.nan]], dtype=np.float32),
        site_xpos=np.asarray([[2.0, 2.0, 2.0]], dtype=np.float32),
    )
    invalid = TaskLifecycleAdapter(
        task_definition=definition, horizon=10, ignore_done=False
    ).evaluate_predicates(TaskEvaluationContextV1(state=nonfinite)).resolve("cube_lifted")
    assert invalid.status == "unavailable"
    assert invalid.reason == "required_pickcube_state_nonfinite"
