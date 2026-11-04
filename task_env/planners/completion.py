"""Provider-neutral completion values for frozen public-action stage plans."""
from dataclasses import dataclass
from enum import Enum
from typing import Any
import math
import numpy as np
from ..artifacts.contracts import Contract
from ..controllers.canonical.readiness import CanonicalControlReadiness
from ..utils.rotation import quat_wxyz_to_matrix, rotation_vector_error


@dataclass(frozen=True)
class ExpertExecutionInfo(Contract):
    schema_version: str
    control_step: int
    simulation_time: float
    control_readiness: CanonicalControlReadiness

    def validate(self):
        if self.schema_version != 'expert-execution-info-v1':
            raise ValueError('unsupported expert execution metadata')
        if type(self.control_step) is not int or self.control_step < 0:
            raise ValueError('invalid expert execution control boundary')
        if not math.isfinite(self.simulation_time) or self.simulation_time < 0:
            raise ValueError('invalid expert execution simulation time')
        if not isinstance(self.control_readiness, CanonicalControlReadiness):
            raise TypeError('canonical control readiness is required')
        self.control_readiness.validate()
        self.control_readiness.require_boundary(self.control_step, self.simulation_time)


@dataclass(frozen=True)
class StageCompletionPolicy(Contract):
    schema_version: str
    kind: str
    hold_ticks: int
    position_deadband_m: float
    rotation_deadband_rad: float
    collection_endpoint_m: float
    gripper_semantic_id: str
    failure_reason: str

    def validate(self):
        if self.schema_version != 'stage-completion-v1' or self.kind not in ('pose_ready', 'gripper_ready', 'task_outcome'):
            raise ValueError('unsupported stage completion policy')
        if self.hold_ticks < 0 or min(self.position_deadband_m, self.rotation_deadband_rad, self.collection_endpoint_m) <= 0:
            raise ValueError('invalid completion limits')

    def evaluate(self, ee_pose, target_pose, task_info, execution_info):
        if self.kind == 'task_outcome':
            return bool(task_info.get('is_success', False)) and float(task_info.get('task_metrics', {}).get('cube_lift', 0.)) >= self.collection_endpoint_m
        if self.kind == 'gripper_ready':
            gripper = execution_info.control_readiness.gripper
            if gripper.semantic_id != self.gripper_semantic_id:
                raise ValueError('unexpected semantic gripper binding')
            return gripper.close_ready
        current, target = np.asarray(ee_pose), np.asarray(target_pose)
        if not np.isfinite(current).all() or not np.isfinite(target).all():
            raise ValueError('nonfinite public pose')
        position = np.linalg.norm(current[:3] - target[:3])
        rotation = np.linalg.norm(rotation_vector_error(quat_wxyz_to_matrix(current[3:7]), quat_wxyz_to_matrix(target[3:7])))
        return bool(position <= self.position_deadband_m and rotation <= self.rotation_deadband_rad)


def measured_interval_timing(time_s, duration_s, *, start_time_s, last_start_s, sample_period_s):
    """Validate a measured interval and report its end and sampling continuity.

    A gap breaks a dwell window; no missing sample is synthesized.
    """
    if not math.isfinite(time_s) or not math.isfinite(duration_s) or duration_s <= 0:
        raise ValueError("invalid guard observation")
    if time_s < start_time_s - 1e-10:
        raise ValueError("guard observation predates transition window")
    delta = None if last_start_s is None else time_s - last_start_s
    if delta is not None and delta <= 0:
        raise ValueError("guard observations must be strictly time ordered")
    tolerance = max(1e-12, sample_period_s * 1e-9)
    if abs(duration_s - sample_period_s) > tolerance:
        raise ValueError("guard observation duration differs from declared sample period")
    return time_s + duration_s, delta is not None and abs(delta - sample_period_s) > tolerance


class SolutionCompletionPolicy(str, Enum):
    """When a Canonical Solution may report successful expert completion."""

    ON_TASK_SUCCESS = "on_task_success"
    ON_EXPERT_TERMINAL_STAGE = "on_expert_terminal_stage"


class CanonicalSolutionLifecycle:
    """One rollout's immutable-policy, replayable completion state."""

    version = "canonical-solution-lifecycle-v1"

    def __init__(self, completion_policy: SolutionCompletionPolicy | str) -> None:
        self._completion_policy = SolutionCompletionPolicy(completion_policy)
        self.reset()

    @property
    def completion_policy(self) -> SolutionCompletionPolicy:
        return self._completion_policy

    @property
    def expert_complete(self) -> bool:
        return self._status == "completed"

    @property
    def expert_failed(self) -> bool:
        return self._status == "failed"

    @property
    def terminal(self) -> bool:
        return self._status != "active"

    def reset(self) -> None:
        """Clear all rollout history without changing the declared policy."""
        self._status = "active"
        self.task_success_seen = False
        self.first_task_success_step: int | None = None
        self.first_task_success_time_s: float | None = None
        self.last_task_success = False
        self.environment_terminated = False
        self.environment_truncated = False
        self.failure_reason: str | None = None
        self.outcome_code: str | None = None
        self.completion_reason: str | None = None
        self.completion_step: int | None = None
        self.completion_time_s: float | None = None
        self.events: list[dict[str, Any]] = []

    @staticmethod
    def _clock(control_step: int, simulation_time_s: float) -> tuple[int, float]:
        if isinstance(control_step, bool) or not isinstance(control_step, int) or control_step < 0:
            raise ValueError("control_step must be a nonnegative integer")
        value = float(simulation_time_s)
        if not math.isfinite(value) or value < 0.0:
            raise ValueError("simulation_time_s must be finite and nonnegative")
        return control_step, value

    def _event(self, name: str, control_step: int, simulation_time_s: float, **details: Any) -> None:
        step, time_s = self._clock(control_step, simulation_time_s)
        self.events.append({"event": name, "control_step": step,
                            "simulation_time_s": time_s, **details})

    def observe_task_outcome(
        self,
        *,
        task_success: bool,
        task_failure: bool = False,
        terminated: bool = False,
        truncated: bool = False,
        control_step: int,
        simulation_time_s: float,
    ) -> bool:
        """Record an observed task/runtime boundary and apply immediate policy.

        Returns whether the lifecycle reached a terminal state.  The current
        task-success value is kept separately from its first historical event.
        """
        if self.terminal:
            raise RuntimeError("cannot observe a terminal solution lifecycle")
        if terminated and truncated:
            raise ValueError("an episode boundary cannot be both terminated and truncated")
        step, time_s = self._clock(control_step, simulation_time_s)
        success = bool(task_success)
        self.environment_terminated = bool(terminated)
        self.environment_truncated = bool(truncated)
        if success and not self.task_success_seen:
            self.task_success_seen = True
            self.first_task_success_step = step
            self.first_task_success_time_s = time_s
            self._event("task_success_first_observed", step, time_s)
        elif self.task_success_seen and self.last_task_success and not success:
            self._event("task_success_lost", step, time_s)
        self.last_task_success = success

        if task_failure:
            self.fail("task_failure", control_step=step, simulation_time_s=time_s)
        elif success and self.completion_policy is SolutionCompletionPolicy.ON_TASK_SUCCESS:
            self._complete("canonical_task_success_observed", step, time_s)
        elif terminated:
            reason = ("TASK_SUCCESS_EXPERT_INCOMPLETE" if self.task_success_seen
                      else "environment_terminated_before_expert_completion")
            self.fail(reason, control_step=step, simulation_time_s=time_s)
        elif truncated:
            reason = ("TASK_SUCCESS_EXPERT_INCOMPLETE" if self.task_success_seen
                      else "environment_truncated_before_expert_completion")
            self.fail(reason, control_step=step, simulation_time_s=time_s)
        return self.terminal

    def fail(self, reason: str, *, control_step: int, simulation_time_s: float) -> None:
        """Record an expert failure without rewriting task-success history."""
        if self.terminal:
            raise RuntimeError("cannot change a terminal solution lifecycle")
        if not isinstance(reason, str) or not reason:
            raise ValueError("failure reason is required")
        step, time_s = self._clock(control_step, simulation_time_s)
        self._status = "failed"
        self.failure_reason = reason
        self.outcome_code = ("TASK_SUCCESS_EXPERT_INCOMPLETE"
                             if self.task_success_seen and reason.startswith(("environment_", "TASK_SUCCESS_"))
                             else "EXPERT_EXECUTION_FAILED")
        self._event("expert_sequence_failed", step, time_s,
                    reason=reason, outcome_code=self.outcome_code)

    def _complete(self, reason: str, control_step: int, simulation_time_s: float) -> None:
        if self.terminal:
            raise RuntimeError("cannot change a terminal solution lifecycle")
        self._status = "completed"
        self.completion_reason = reason
        self.completion_step = control_step
        self.completion_time_s = simulation_time_s
        self.outcome_code = "EXPERT_COMPLETED"
        self._event("expert_sequence_completed", control_step, simulation_time_s,
                    reason=reason, final_task_success=self.last_task_success)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "completion_policy": self.completion_policy.value,
            "status": self._status,
            "task_success_seen": self.task_success_seen,
            "first_task_success_step": self.first_task_success_step,
            "first_task_success_time_s": self.first_task_success_time_s,
            "last_task_success": self.last_task_success,
            "environment_terminated": self.environment_terminated,
            "environment_truncated": self.environment_truncated,
            "failure_reason": self.failure_reason,
            "outcome_code": self.outcome_code,
            "completion_reason": self.completion_reason,
            "completion_step": self.completion_step,
            "completion_time_s": self.completion_time_s,
            "events": [dict(event) for event in self.events],
        }

    def restore_state(self, value: dict[str, Any]) -> None:
        """Restore rollout state, rejecting policy or lifecycle mismatches."""
        expected_keys = set(self.to_mapping())
        if not isinstance(value, dict) or set(value) != expected_keys:
            raise ValueError("incomplete solution lifecycle snapshot")
        if value["version"] != self.version:
            raise ValueError("solution lifecycle version mismatch")
        if value["completion_policy"] != self.completion_policy.value:
            raise ValueError("solution lifecycle policy mismatch")
        status = value["status"]
        if status not in {"active", "completed", "failed"}:
            raise ValueError("invalid solution lifecycle status")
        if type(value["task_success_seen"]) is not bool or type(value["last_task_success"]) is not bool:
            raise ValueError("invalid task outcome state")
        if type(value["environment_terminated"]) is not bool or type(value["environment_truncated"]) is not bool:
            raise ValueError("invalid environment outcome state")
        if value["environment_terminated"] and value["environment_truncated"]:
            raise ValueError("terminated and truncated cannot both be true")
        first_step, first_time = value["first_task_success_step"], value["first_task_success_time_s"]
        if value["task_success_seen"]:
            if first_step is None or first_time is None:
                raise ValueError("first task success clock is missing")
            self._clock(first_step, first_time)
        elif first_step is not None or first_time is not None:
            raise ValueError("unexpected first task success clock")
        complete_fields = (value["completion_reason"], value["completion_step"], value["completion_time_s"])
        if status == "completed":
            if value["failure_reason"] is not None or any(x is None for x in complete_fields):
                raise ValueError("inconsistent completed lifecycle snapshot")
            self._clock(value["completion_step"], value["completion_time_s"])
        elif any(x is not None for x in complete_fields):
            raise ValueError("inconsistent non-completed lifecycle snapshot")
        if status == "failed":
            if not value["failure_reason"] or value["outcome_code"] not in {
                "TASK_SUCCESS_EXPERT_INCOMPLETE", "EXPERT_EXECUTION_FAILED"
            }:
                raise ValueError("inconsistent failed lifecycle snapshot")
        elif value["failure_reason"] is not None:
            raise ValueError("failure reason on non-failed lifecycle")
        if status == "active" and value["outcome_code"] is not None:
            raise ValueError("active lifecycle cannot have terminal outcome")
        events = value["events"]
        if not isinstance(events, list):
            raise ValueError("invalid lifecycle event history")
        for event in events:
            if not isinstance(event, dict) or not isinstance(event.get("event"), str):
                raise ValueError("invalid lifecycle event")
            self._clock(event.get("control_step"), event.get("simulation_time_s"))

        self._status = status
        for name in (
            "task_success_seen", "first_task_success_step", "first_task_success_time_s",
            "last_task_success", "environment_terminated", "environment_truncated",
            "failure_reason", "outcome_code", "completion_reason", "completion_step",
            "completion_time_s",
        ):
            setattr(self, name, value[name])
        self.events = [dict(event) for event in events]
