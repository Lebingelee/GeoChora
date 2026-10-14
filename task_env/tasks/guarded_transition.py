"""Provider-neutral, physical-time guarded stage transitions.

The evaluator consumes explicitly timestamped observations.  Each observation
describes one measured interval ``[time_s, time_s + duration_s)``; it never
interpolates missing samples or treats a count of outer actions as elapsed time.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import hashlib
import json
from typing import Mapping


@dataclass(frozen=True)
class TransitionGuardSpec:
    guard_id: str
    source_stage: str
    target_stage: str
    required_conditions: tuple[str, ...]
    priority: int

    def __post_init__(self):
        if not self.guard_id or not self.source_stage or not self.target_stage:
            raise ValueError("guard identity and stages are required")
        if not self.required_conditions or len(set(self.required_conditions)) != len(self.required_conditions):
            raise ValueError("guard conditions must be nonempty and unique")
        if type(self.priority) is not int or self.priority < 0:
            raise ValueError("guard priority must be a nonnegative integer")

    def to_mapping(self):
        return {
            "guard_id": self.guard_id,
            "source_stage": self.source_stage,
            "target_stage": self.target_stage,
            "required_conditions": list(self.required_conditions),
            "priority": self.priority,
        }


@dataclass(frozen=True)
class TransitionDecision:
    outcome: str
    selected_guard_id: str | None
    source_stage: str
    target_stage: str | None
    simulation_time_s: float
    evidence: dict

    def __post_init__(self):
        if self.outcome not in {"WAIT", "AUTHORIZED", "RECOVERY_REQUIRED", "FAILED"}:
            raise ValueError("unsupported guarded-transition outcome")
        if not math.isfinite(float(self.simulation_time_s)) or self.simulation_time_s < 0:
            raise ValueError("invalid transition decision time")

    def to_mapping(self):
        return {
            "outcome": self.outcome,
            "selected_guard_id": self.selected_guard_id,
            "source_stage": self.source_stage,
            "target_stage": self.target_stage,
            "simulation_time_s": float(self.simulation_time_s),
            "evidence": self.evidence,
        }


class GuardedTransitionEvaluator:
    """Deterministically evaluate multiple continuous-time authorization edges."""

    version = "canonical-guarded-transition-evaluator-v1"

    def __init__(self, *, source_stage: str, guards: tuple[TransitionGuardSpec, ...],
                 required_duration_s: float, start_time_s: float,
                 deadline_s: float, sample_period_s: float,
                 allow_early_alternative: bool):
        if not guards or len({x.guard_id for x in guards}) != len(guards):
            raise ValueError("transition guards must be nonempty and uniquely named")
        if any(x.source_stage != source_stage for x in guards):
            raise ValueError("guard source stage mismatch")
        values = (required_duration_s, start_time_s, deadline_s, sample_period_s)
        if not all(math.isfinite(float(x)) for x in values):
            raise ValueError("finite physical-time guard parameters required")
        if required_duration_s <= 0 or sample_period_s <= 0 or deadline_s <= start_time_s:
            raise ValueError("positive dwell/sample period and later deadline required")
        self.source_stage = source_stage
        self.guards = tuple(sorted(guards, key=lambda item: (item.priority, item.guard_id)))
        self.required_duration_s = float(required_duration_s)
        self.start_time_s = float(start_time_s)
        self.deadline_s = float(deadline_s)
        self.sample_period_s = float(sample_period_s)
        self.allow_early_alternative = bool(allow_early_alternative)
        self.last_sample_start_s = None
        self.guard_progress = {
            spec.guard_id: {
                "window_start_s": None,
                "continuous_duration_s": 0.0,
                "sample_count": 0,
                "sample_history": [],
                "last_sample_start_s": None,
                "last_conditions": None,
            }
            for spec in self.guards
        }
        self.selected_guard_id = None
        self.selected_evidence = None
        self.outcome = "WAIT"
        self.recovery_required = False

    @property
    def identity_mapping(self):
        return {
            "version": self.version,
            "source_stage": self.source_stage,
            "guards": [guard.to_mapping() for guard in self.guards],
            "required_duration_s": self.required_duration_s,
            "start_time_s": self.start_time_s,
            "deadline_s": self.deadline_s,
            "sample_period_s": self.sample_period_s,
            "sample_interval_semantics": "measured-left-closed-right-open",
            "allow_early_alternative": self.allow_early_alternative,
            "tie_break": "lowest-priority-number-then-guard-id",
        }

    def _decision(self, outcome, time_s, selected=None, evidence=None):
        target = None
        if selected is not None:
            target = next(x.target_stage for x in self.guards if x.guard_id == selected)
        return TransitionDecision(outcome, selected, self.source_stage, target,
                                  float(time_s), evidence or {})

    def observe(self, sample: Mapping):
        """Consume one measured interval and return its current decision."""
        if self.outcome in {"AUTHORIZED", "FAILED"}:
            return self._decision(self.outcome, self.deadline_s,
                                  self.selected_guard_id, self.selected_evidence)
        if set(sample) != {"sample_time_s", "sample_duration_s", "conditions", "values"}:
            raise ValueError("guard observation schema")
        time_s = float(sample["sample_time_s"])
        duration_s = float(sample["sample_duration_s"])
        end_s = time_s + duration_s
        conditions = sample["conditions"]
        if (not math.isfinite(time_s) or not math.isfinite(duration_s)
                or duration_s <= 0 or not isinstance(conditions, Mapping)
                or not isinstance(sample["values"], Mapping)):
            raise ValueError("invalid guard observation")
        if time_s < self.start_time_s - 1e-10:
            raise ValueError("guard observation predates transition window")
        if self.last_sample_start_s is not None:
            delta = time_s - self.last_sample_start_s
            if delta <= 0:
                raise ValueError("guard observations must be strictly time ordered")
        else:
            delta = None
        if abs(duration_s - self.sample_period_s) > max(1e-12, self.sample_period_s * 1e-9):
            raise ValueError("guard observation duration differs from declared sample period")

        had_progress = any(v["sample_count"] > 0 for v in self.guard_progress.values())
        continuity_lost = False
        if delta is not None and abs(delta - self.sample_period_s) > max(1e-12, self.sample_period_s * 1e-9):
            for progress in self.guard_progress.values():
                continuity_lost |= progress["sample_count"] > 0
                progress.update(window_start_s=None, continuous_duration_s=0.0,
                                sample_count=0, sample_history=[], last_sample_start_s=None)

        eligible = []
        within_deadline = end_s <= self.deadline_s + 1e-10
        for spec in self.guards:
            progress = self.guard_progress[spec.guard_id]
            if not within_deadline:
                progress.update(window_start_s=None, continuous_duration_s=0.0,
                                sample_count=0, last_sample_start_s=None,
                                last_conditions=dict(conditions))
                continue
            missing = set(spec.required_conditions) - set(conditions)
            if missing:
                raise ValueError(f"guard observation missing conditions: {sorted(missing)}")
            satisfied = all(type(conditions[key]) is bool and conditions[key]
                            for key in spec.required_conditions)
            if not satisfied:
                continuity_lost |= progress["sample_count"] > 0
                progress.update(window_start_s=None, continuous_duration_s=0.0,
                                sample_count=0, sample_history=[], last_sample_start_s=time_s,
                                last_conditions=dict(conditions))
                continue
            if progress["sample_count"] == 0:
                progress["window_start_s"] = time_s
            progress["continuous_duration_s"] = round(
                float(progress["continuous_duration_s"]) + duration_s, 12)
            progress["sample_count"] += 1
            progress["sample_history"].append({
                "sample_time_s": time_s,
                "sample_duration_s": duration_s,
                "conditions": dict(conditions),
                "values": dict(sample["values"]),
            })
            progress["last_sample_start_s"] = time_s
            progress["last_conditions"] = dict(conditions)
            if progress["continuous_duration_s"] + 1e-10 >= self.required_duration_s:
                eligible.append(spec)

        self.last_sample_start_s = time_s
        if eligible:
            # A declared early alternative may be selected as soon as its own
            # complete dwell is observed. Priority resolves only same-sample ties.
            chosen = min(eligible, key=lambda item: (item.priority, item.guard_id))
            if (not self.allow_early_alternative
                    and chosen.guard_id != self.guards[0].guard_id
                    and self.guards[0].guard_id not in {item.guard_id for item in eligible}):
                self.recovery_required = False
                if end_s >= self.deadline_s - 1e-10:
                    self.outcome = "FAILED"
                    outcome = "FAILED"
                else:
                    outcome = "WAIT"
                return self._decision(outcome, end_s, evidence={
                    "deadline_s": self.deadline_s,
                    "guard_progress": self.guard_progress,
                    "alternative_waiting_for_primary": chosen.guard_id,
                })
            progress = self.guard_progress[chosen.guard_id]
            self.selected_guard_id = chosen.guard_id
            self.selected_evidence = {
                "window_start_s": progress["window_start_s"],
                "authorization_sample_start_s": time_s,
                "authorization_time_s": end_s,
                "observed_stable_duration_s": progress["continuous_duration_s"],
                "native_sample_count": progress["sample_count"],
                "sample_history_sha256": hashlib.sha256(json.dumps(
                    progress["sample_history"], sort_keys=True,
                    separators=(",", ":"), allow_nan=False,
                ).encode()).hexdigest(),
                "conditions": dict(conditions),
                "values": dict(sample["values"]),
            }
            self.outcome = "AUTHORIZED"
            return self._decision("AUTHORIZED", end_s, chosen.guard_id, self.selected_evidence)

        if end_s >= self.deadline_s - 1e-10:
            self.outcome = "FAILED"
            return self._decision("FAILED", end_s, evidence={
                "deadline_s": self.deadline_s,
                "guard_progress": self.guard_progress,
                "last_conditions": dict(conditions),
            })
        self.recovery_required = bool(continuity_lost)
        outcome = "RECOVERY_REQUIRED" if continuity_lost and had_progress else "WAIT"
        return self._decision(outcome, end_s, evidence={
            "deadline_s": self.deadline_s,
            "guard_progress": self.guard_progress,
            "conditions": dict(conditions),
        })

    def to_mapping(self):
        return {
            "version": self.version,
            "identity": self.identity_mapping,
            "last_sample_start_s": self.last_sample_start_s,
            "guard_progress": self.guard_progress,
            "selected_guard_id": self.selected_guard_id,
            "selected_evidence": self.selected_evidence,
            "outcome": self.outcome,
            "recovery_required": self.recovery_required,
        }

    def restore_state(self, state):
        if not isinstance(state, Mapping) or set(state) != {
            "version", "identity", "last_sample_start_s", "guard_progress",
            "selected_guard_id", "selected_evidence", "outcome", "recovery_required",
        }:
            raise ValueError("guard evaluator snapshot schema")
        if state["version"] != self.version or state["identity"] != self.identity_mapping:
            raise ValueError("guard evaluator snapshot identity mismatch")
        if set(state["guard_progress"]) != set(self.guard_progress):
            raise ValueError("guard evaluator snapshot progress mismatch")
        if state["outcome"] not in {"WAIT", "AUTHORIZED", "FAILED"}:
            raise ValueError("invalid restored guard evaluator outcome")
        self.last_sample_start_s = state["last_sample_start_s"]
        self.guard_progress = state["guard_progress"]
        self.selected_guard_id = state["selected_guard_id"]
        self.selected_evidence = state["selected_evidence"]
        self.outcome = state["outcome"]
        self.recovery_required = bool(state["recovery_required"])
