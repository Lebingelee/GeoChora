"""Linear absolute-world-pose solution for the PickCube task.

This module deliberately owns no environment internals.  It consumes only the
observations and info mappings returned by ``TaskEnv.reset`` / ``TaskEnv.step``
and emits one public absolute-world-pose action at a time.  It is a small, non-replanning
baseline for validating the planner-to-rollout boundary before Stage 9 records
transitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from decimal import Decimal, ROUND_CEILING
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Callable, Mapping

import numpy as np

from ...planners import AbsolutePosePlanner, AbsolutePosePlannerConfig, ExpertAction
from ...planners.completion import StageCompletionPolicy, ExpertExecutionInfo
from ...artifacts.contracts import Contract
from ...controllers.canonical.contracts import digest
from ...objects.pick_cube import CUBE_HALF_SIZE


_ABOVE_CLEARANCE = 0.12
# Keep the approach above the existing hover pose while traversing laterally.
# The final hover/grasp poses and task geometry remain unchanged.
_APPROACH_CLEARANCE = 0.10
# Clearance is confirmed from the public measured EE pose before the preplanned
# path is allowed to traverse over the cube or descend toward it.
_MEASURED_CLEARANCE_TOLERANCE = 0.005
_OVER_CUBE_HORIZONTAL_TOLERANCE = 0.010
# Nominal EE-site clearance above the cube top for this PickCube expert.
# The current hand/knuckle proxy needs about 17.6 mm in a downward grasp;
# 20 mm leaves a small geometry margin, not contact-precision qualification.
_GRASP_CLEARANCE_ABOVE_CUBE_TOP = 0.020
_LIFT_DISTANCE = 0.16
_COLLECTION_LIFT_MARGIN = 0.105
_POSITION_TOLERANCE = 0.150
_CLOSE_TRANSITION_MIN_STEPS = 10
_MIN_CLOSE_TRANSITION_STEPS = 20


class SegmentStatus(str, Enum):
    """Result of evaluating one fully linear semantic segment."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class MeasuredTcpGate:
    """A public-pose interlock inside a precomputed PickCube action sequence."""

    name: str
    after_actions: int
    minimum_height_above_cube_top_m: float
    max_horizontal_error_m: float | None = None

    def __post_init__(self) -> None:
        if not self.name or type(self.after_actions) is not int or self.after_actions < 0:
            raise ValueError("measured TCP gate requires a name and nonnegative action boundary")
        if (not np.isfinite(self.minimum_height_above_cube_top_m)
                or self.minimum_height_above_cube_top_m <= 0.0):
            raise ValueError("measured TCP gate clearance must be finite and positive")
        if (self.max_horizontal_error_m is not None
                and (not np.isfinite(self.max_horizontal_error_m)
                     or self.max_horizontal_error_m <= 0.0)):
            raise ValueError("measured TCP gate horizontal error must be finite and positive")


@dataclass(frozen=True)
class SegmentPlan:
    """One segment's immutable public-action sequence and diagnostic target."""

    actions: np.ndarray
    target_pose: np.ndarray
    measured_tcp_gates: tuple[MeasuredTcpGate, ...] = ()

    def __post_init__(self) -> None:
        actions = np.asarray(self.actions, dtype=np.float32).copy()
        target_pose = np.asarray(self.target_pose, dtype=np.float32).reshape(7).copy()
        if actions.ndim != 2 or actions.shape[0] < 1:
            raise ValueError("segment actions must have shape [N, action_dim] with N >= 1")
        if not np.isfinite(actions).all() or not np.isfinite(target_pose).all():
            raise ValueError("segment plan must contain only finite values")
        gates = tuple(self.measured_tcp_gates)
        if any(not isinstance(gate, MeasuredTcpGate) for gate in gates):
            raise TypeError("segment measured TCP gates must be MeasuredTcpGate values")
        if any(gate.after_actions > len(actions) for gate in gates):
            raise ValueError("measured TCP gate lies beyond the segment action sequence")
        if tuple(gate.after_actions for gate in gates) != tuple(
            sorted(gate.after_actions for gate in gates)
        ):
            raise ValueError("measured TCP gates must follow action order")
        actions.setflags(write=False)
        target_pose.setflags(write=False)
        object.__setattr__(self, "actions", actions)
        object.__setattr__(self, "target_pose", target_pose)
        object.__setattr__(self, "measured_tcp_gates", gates)


PlanBuilder = Callable[[object, Mapping[str, object]], SegmentPlan]
AcceptanceCheck = Callable[[object, Mapping[str, object], SegmentPlan], bool]


@dataclass
class Segment:
    """A linear semantic stage planned once at stage entry.

    ``refresh`` is intentionally called only once per stage in this version.
    Future replanning can reuse this boundary without changing the rollout
    contract, but is explicitly out of scope here.
    """

    name: str
    build_plan: PlanBuilder
    accept: AcceptanceCheck
    plan: SegmentPlan | None = field(default=None, init=False)

    def refresh(
        self,
        observation,
        info: Mapping[str, object],
        metadata: Mapping[str, object],
    ) -> SegmentPlan:
        """Freeze this stage's target and public action sequence from public state."""
        action_schema = metadata.get("action_schema", {})
        if (
            action_schema.get("controller_kind") != "absolute_pose"
            or action_schema.get("reference") != "world"
            or action_schema.get("rotation_representation") != "quaternion_wxyz"
        ):
            raise ValueError(
                "PickCubeSolution requires absolute_pose(reference='world') "
                "with quaternion_wxyz rotation"
            )
        plan = self.build_plan(observation, info)
        expected_dim = int(action_schema.get("dimension", 0))
        if plan.actions.shape[1] != expected_dim:
            raise ValueError(
                f"segment {self.name!r} emits action_dim={plan.actions.shape[1]}, "
                f"expected {expected_dim}"
            )
        self.plan = plan
        return plan

    def check(
        self,
        observation,
        info: Mapping[str, object],
        *,
        actions_exhausted: bool,
    ) -> SegmentStatus:
        """Accept only after the precomputed sequence is consumed."""
        if self.plan is None:
            raise RuntimeError(f"segment {self.name!r} was not refreshed")
        if not actions_exhausted:
            return SegmentStatus.RUNNING
        return SegmentStatus.SUCCEEDED if self.accept(observation, info, self.plan) else SegmentStatus.FAILED


@dataclass(frozen=True)
class PickCubeSolutionConfig:
    """Validated Stage 8E timing and Cartesian limits for the linear baseline."""

    action_budget: int = 120
    position_tolerance: float = _POSITION_TOLERANCE
    close_transition_steps: int = _MIN_CLOSE_TRANSITION_STEPS
    planner: AbsolutePosePlannerConfig = field(
        default_factory=lambda: AbsolutePosePlannerConfig(
            max_translation_per_step=0.012,
            max_translation_acceleration_per_step=0.004,
            max_rotation_per_step=0.10,
            max_rotation_acceleration_per_step=0.03,
            settle_steps=0,
            max_steps=200,
        )
    )

    def __post_init__(self) -> None:
        if self.action_budget < 1:
            raise ValueError("action_budget must be at least one")
        if self.position_tolerance <= 0.0:
            raise ValueError("position_tolerance must be positive")
        if not _CLOSE_TRANSITION_MIN_STEPS <= self.close_transition_steps <= _MIN_CLOSE_TRANSITION_STEPS:
            raise ValueError(
                "close_transition_steps must be in the stable-close range [10, 20]"
            )


class PickCubeSolution:
    """Execute the validated PickCube stages once, without replanning.

    The solution is an external TaskEnv client: callers drive it by forwarding
    only public reset/step values.  It never receives an environment object,
    solver, controller, or runtime snapshot.
    """

    def __init__(self, *, config: PickCubeSolutionConfig | None = None) -> None:
        self.config = config or PickCubeSolutionConfig()
        self._planner = AbsolutePosePlanner(self.config.planner)
        self._segments = self._make_segments()
        self._segment_index = 0
        self._action_index = 0
        self._actions_emitted = 0
        self._done = False
        self._failed = False
        self._failure_reason: str | None = None
        self._metadata: Mapping[str, object] | None = None
        self._awaiting_observation = False

    @property
    def stage(self) -> str:
        return self._segments[min(self._segment_index, len(self._segments) - 1)].name

    @property
    def done(self) -> bool:
        return self._done

    @property
    def failed(self) -> bool:
        return self._failed

    @property
    def failure_reason(self) -> str | None:
        return self._failure_reason

    def reset(self, observation, info: Mapping[str, object], metadata: Mapping[str, object]) -> None:
        """Initialize the first segment from the public reset transition."""
        self._segments = self._make_segments()
        self._segment_index = 0
        self._action_index = 0
        self._actions_emitted = 0
        self._done = bool(info.get("is_success", False))
        self._failed = False
        self._failure_reason = None
        self._metadata = metadata
        self._awaiting_observation = False
        if not self._done:
            self._refresh_current_segment(observation, info)

    def act(self, observation=None, info: Mapping[str, object] | None = None) -> ExpertAction:
        """Return exactly one public action for the current precomputed segment."""
        del observation, info
        if self._done or self._failed:
            raise RuntimeError("cannot request an action after solution completion")
        if self._awaiting_observation:
            raise RuntimeError("observe() must follow each act() before requesting another action")
        segment = self._segments[self._segment_index]
        if segment.plan is None:
            raise RuntimeError(f"segment {segment.name!r} has no plan")
        if self._action_index >= len(segment.plan.actions):
            raise RuntimeError("segment actions are exhausted before observe() advanced the solution")
        action = segment.plan.actions[self._action_index]
        diagnostics = {
            "segment_index": self._segment_index,
            "segment_step": self._action_index,
            "planned_segment_steps": len(segment.plan.actions),
            "actions_emitted": self._actions_emitted,
            "target_x": float(segment.plan.target_pose[0]),
            "target_y": float(segment.plan.target_pose[1]),
            "target_z": float(segment.plan.target_pose[2]),
        }
        self._awaiting_observation = True
        return ExpertAction(action=action, stage=segment.name, diagnostics=diagnostics)

    next_action = act

    def observe(
        self,
        observation,
        reward: float,
        terminated: bool,
        truncated: bool,
        info: Mapping[str, object],
    ) -> None:
        """Consume one public step result and advance only on stage acceptance."""
        del reward
        if not self._awaiting_observation:
            raise RuntimeError("observe() requires a preceding act()")
        self._awaiting_observation = False
        self._action_index += 1
        self._actions_emitted += 1

        task_metrics = info.get("task_metrics", {})
        collection_margin_reached = (
            self.stage != "lift"
            or (
                isinstance(task_metrics, Mapping)
                and float(task_metrics.get("cube_lift", 0.0)) >= _COLLECTION_LIFT_MARGIN
            )
        )
        # ``is_success`` remains the task's 10 cm predicate.  The extra lift
        # margin is only an expert-collection endpoint invariant.
        if bool(info.get("is_success", False)) and collection_margin_reached:
            self._done = True
            return
        if truncated:
            self._fail("episode_truncated")
            return
        if terminated or bool(info.get("task_failure", False)):
            self._fail("environment_terminated")
            return

        segment = self._segments[self._segment_index]
        status = segment.check(
            observation,
            info,
            actions_exhausted=self._action_index >= len(segment.plan.actions),
        )
        if status is SegmentStatus.RUNNING:
            return
        if status is SegmentStatus.FAILED:
            self._fail(f"segment_acceptance_failed:{segment.name}")
            return
        if self._segment_index == len(self._segments) - 1:
            self._fail("final_segment_completed_without_task_success")
            return
        self._segment_index += 1
        self._action_index = 0
        self._refresh_current_segment(observation, info)

    def _refresh_current_segment(self, observation, info: Mapping[str, object]) -> None:
        if self._metadata is None:
            raise RuntimeError("solution metadata is unavailable before reset()")
        segment = self._segments[self._segment_index]
        plan = segment.refresh(observation, info, self._metadata)
        if self._actions_emitted + len(plan.actions) > self.config.action_budget:
            self._fail("solution_action_budget_exceeded")

    def _fail(self, reason: str) -> None:
        self._failed = True
        self._failure_reason = reason

    def _make_segments(self) -> list[Segment]:
        return [
            Segment("move_above_cube", self._plan_move_above, self._accept_position),
            Segment("descend_vertical", self._plan_descend, self._accept_position),
            # Closing is a fixed 10--20 tick public action primitive.  The
            # task success contract is the measured 10 cm cube lift, so an
            # opening-based grasp heuristic must not prevent the lift phase.
            Segment("close_gripper", self._plan_close, self._accept_sequence_complete),
            Segment("lift", self._plan_lift, self._accept_task_success),
        ]

    @staticmethod
    def _ee_pose(observation) -> np.ndarray:
        return np.asarray(observation["state"]["ee_pose"], dtype=np.float32).reshape(7)

    @staticmethod
    def _cube_position(observation) -> np.ndarray:
        return np.asarray(
            observation["privileged_state"]["cube_v1_body_pose"][0, :3],
            dtype=np.float32,
        ).reshape(3)

    def _plan_move_above(self, observation, info: Mapping[str, object]) -> SegmentPlan:
        del info
        start = self._ee_pose(observation)
        cube = self._cube_position(observation)
        target = start.copy()
        target[:3] = cube + np.array(
            [0.0, 0.0, CUBE_HALF_SIZE + _ABOVE_CLEARANCE], dtype=np.float32
        )
        clear = start.copy()
        clear[2] = max(
            float(start[2]), float(target[2]) + _APPROACH_CLEARANCE,
        )
        transit = clear.copy()
        transit[:2] = target[:2]
        vertical_actions = self._planner.plan_translation_only(
            current_pose=start,
            target_position=clear[:3],
            gripper=1.0,
            settle_steps=0,
        )
        lateral_actions = self._planner.plan_translation_only(
            current_pose=clear,
            target_position=transit[:3],
            gripper=1.0,
            settle_steps=0,
        )
        descend_actions = self._planner.plan_translation_only(
            current_pose=transit,
            target_position=target[:3],
            gripper=1.0,
            settle_steps=0,
        )
        action_segments = (vertical_actions, lateral_actions, descend_actions)
        actions = np.concatenate([segment for segment in action_segments if len(segment)], axis=0)
        minimum_height = _ABOVE_CLEARANCE + _APPROACH_CLEARANCE - _MEASURED_CLEARANCE_TOLERANCE
        vertical_end = len(vertical_actions)
        lateral_end = vertical_end + len(lateral_actions)
        return SegmentPlan(
            actions=actions,
            target_pose=target,
            measured_tcp_gates=(
                MeasuredTcpGate(
                    "vertical_clearance",
                    vertical_end,
                    minimum_height_above_cube_top_m=minimum_height,
                ),
                MeasuredTcpGate(
                    "over_cube_before_descent",
                    lateral_end,
                    minimum_height_above_cube_top_m=minimum_height,
                    max_horizontal_error_m=_OVER_CUBE_HORIZONTAL_TOLERANCE,
                ),
            ),
        )

    def _plan_descend(self, observation, info: Mapping[str, object]) -> SegmentPlan:
        del info
        start = self._ee_pose(observation)
        target = start.copy()
        target[:3] = self._cube_position(observation) + np.array(
            [
                0.0,
                0.0,
                CUBE_HALF_SIZE + _GRASP_CLEARANCE_ABOVE_CUBE_TOP,
            ],
            dtype=np.float32,
        )
        return SegmentPlan(
            actions=self._planner.plan_translation_only(
                current_pose=start, target_position=target[:3], gripper=1.0, settle_steps=0
            ),
            target_pose=target,
        )

    def _plan_close(self, observation, info: Mapping[str, object]) -> SegmentPlan:
        del info
        target = self._ee_pose(observation)
        return SegmentPlan(
            actions=self._planner.plan_gripper_transition(
                pose=target,
                start_gripper=1.0,
                goal_gripper=-1.0,
                steps=self.config.close_transition_steps,
                settle_steps=0,
            ),
            target_pose=target,
        )

    def _plan_lift(self, observation, info: Mapping[str, object]) -> SegmentPlan:
        del info
        start = self._ee_pose(observation)
        target = start.copy()
        target[2] += _LIFT_DISTANCE
        remaining_budget = self.config.action_budget - self._actions_emitted
        return SegmentPlan(
            actions=self._planner.plan_translation_only(
                current_pose=start,
                target_position=target[:3],
                steps=remaining_budget,
                gripper=-1.0,
                settle_steps=0,
            ),
            target_pose=target,
        )

    def _accept_position(self, observation, info: Mapping[str, object], plan: SegmentPlan) -> bool:
        del info
        error = float(np.linalg.norm(self._ee_pose(observation)[:3] - plan.target_pose[:3]))
        return error <= self.config.position_tolerance

    @staticmethod
    def _accept_sequence_complete(observation, info: Mapping[str, object], plan: SegmentPlan) -> bool:
        del observation, info, plan
        return True

    @staticmethod
    def _accept_task_success(observation, info: Mapping[str, object], plan: SegmentPlan) -> bool:
        del observation, plan
        return bool(info.get("is_success", False))


__all__ = [
    "PickCubeSolution",
    "PickCubeSolutionConfig",
    "Segment",
    "SegmentPlan",
    "SegmentStatus",
]


@dataclass(frozen=True)
class PickCubeReadinessConfig:
    """Selected P1.6 stage-readiness policy resolved from task/controller config."""

    base: PickCubeSolutionConfig
    control_dt: float
    policies: tuple[StageCompletionPolicy, ...]
    profile_identity: str
    timeout_derivation: str
    version: str = "pick-cube-readiness-v1"
    measured_tcp_clearance_gate: bool = False

    def __post_init__(self):
        if self.version != "pick-cube-readiness-v1" or self.control_dt <= 0:
            raise ValueError("invalid readiness configuration")
        if type(self.measured_tcp_clearance_gate) is not bool:
            raise TypeError("measured_tcp_clearance_gate must be an explicit boolean")
        if len(self.policies) != 4 or tuple(p.kind for p in self.policies) != (
            "pose_ready", "pose_ready", "gripper_ready", "task_outcome"
        ):
            raise ValueError("invalid stage policy order")
        if self.base.close_transition_steps != 20:
            raise ValueError("readiness-v1 requires the existing 20-step close primitive")

    @classmethod
    def from_source(cls, artifact, source, *, measured_tcp_clearance_gate=False):
        if source.task_artifact_hash != artifact.identity_hash:
            raise ValueError("source/Artifact mismatch")
        if type(measured_tcp_clearance_gate) is not bool:
            raise TypeError("measured_tcp_clearance_gate must be an explicit boolean")
        action, gripper = source.config.action, source.config.robot.gripper
        if gripper.kind != "experimental_rate_limited":
            raise ValueError("readiness-v1 requires resolved experimental gripper profile")
        base = PickCubeSolutionConfig()
        dt = Decimal(str(artifact.timebase.control_dt))
        ceil = lambda value: int(value.to_integral_value(rounding=ROUND_CEILING))
        pose = Decimal("1.0") / dt
        if pose != pose.to_integral_value():
            raise ValueError("pose timeout must resolve to whole control boundaries")
        opening = Decimal(str(action.gripper_opening_range_m))
        rate = ceil(opening / Decimal(str(gripper.opening_step_m)))
        force = ceil(opening / Decimal(str(gripper.force_adjust_step_m)))
        margin = ceil(Decimal("0.2") / dt)
        total_close = max(rate, force) + margin
        holds = total_close - base.close_transition_steps
        if holds < 0:
            raise ValueError("gripper horizon shorter than transition")

        def policy(kind, ticks, reason):
            return StageCompletionPolicy(
                "stage-completion-v1", kind, ticks, action.ik_position_deadband,
                action.ik_rotation_deadband, _COLLECTION_LIFT_MARGIN,
                "panda-v1/gripper", reason,
            )

        profile = {
            "gripper": asdict(gripper), "opening_range_m": action.gripper_opening_range_m,
            "position_stiffness_N_per_m": action.gripper_position_stiffness_N_per_m,
            "pose_threshold_authority": "resolved ActionConfig",
            "position_deadband": action.ik_position_deadband,
            "rotation_deadband": action.ik_rotation_deadband,
            "measured_tcp_clearance_gate": measured_tcp_clearance_gate,
        }
        derivation = {
            "rate_ticks": rate, "force_adjust_ticks": force,
            "common_dynamics_margin_s": .2, "margin_ticks": margin,
            "total_close_ticks": total_close,
            "transition_ticks": base.close_transition_steps, "pose_timeout_s": 1.,
            "formula": "max(ceil(range/opening_step),ceil(range/force_adjust_step))+ceil(margin/control_dt)",
            "measured_tcp_clearance_gate": measured_tcp_clearance_gate,
            "measured_tcp_clearance_gate_hold_ticks": 2 * int(pose) if measured_tcp_clearance_gate else 0,
        }
        return cls(
            base, float(dt),
            (policy("pose_ready", int(pose), "above_pose_readiness_timeout"),
             policy("pose_ready", int(pose), "descend_pose_readiness_timeout"),
             policy("gripper_ready", holds, "gripper_readiness_timeout"),
             policy("task_outcome", int(pose), "lift_outcome_timeout")),
            digest(profile), json.dumps(derivation, sort_keys=True),
            measured_tcp_clearance_gate=measured_tcp_clearance_gate,
        )

    @property
    def global_safety_cap(self):
        gate_holds = (
            2 * self.policies[0].hold_ticks if self.measured_tcp_clearance_gate else 0
        )
        return self.base.action_budget + sum(policy.hold_ticks for policy in self.policies) + gate_holds

    @property
    def identity(self):
        return digest({
            "version": self.version, "base": asdict(self.base),
            "control_dt": self.control_dt,
            "policies": [policy.to_mapping() for policy in self.policies],
            "profile_identity": self.profile_identity,
            "timeout_derivation": self.timeout_derivation,
            "measured_tcp_clearance_gate": self.measured_tcp_clearance_gate,
            "global_safety_cap": self.global_safety_cap,
        })


class PickCubeReadinessSolution(PickCubeSolution):
    """Selected four-stage P1.6 expert with strict readiness and clock checks."""

    version = "pick-cube-p16-readiness-expert-v2"

    def __init__(self, *, config: PickCubeReadinessConfig):
        self.readiness_config = config
        self.version = (
            "pick-cube-p16-readiness-expert-v3-measured-tcp-clearance"
            if config.measured_tcp_clearance_gate else type(self).version
        )
        self._measured_tcp_gate_index = 0
        self._measured_tcp_gate_wait_ticks = 0
        self._last_measured_tcp_gate_hold = False
        self._last_public_observation = None
        super().__init__(config=config.base)
        implementation_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.identity = digest({
            "version": self.version, "config": config.identity,
            "implementation_sha256": implementation_hash,
        })

    def _execution(self, execution_info, *, reset=False):
        if not isinstance(execution_info, (ExpertExecutionInfo, PickCubePositionExecutionInfoV1)):
            raise TypeError("a validated task execution-boundary value is required separately from task metrics")
        execution_info.validate()
        if not reset:
            if execution_info.control_step != self._boundary_step + 1:
                raise ValueError("stale/skipped execution boundary")
            expected = self._boundary_time + self.readiness_config.control_dt
            import math
            if abs(execution_info.simulation_time - expected) > max(
                math.ulp(expected), math.ulp(execution_info.simulation_time)
            ):
                raise ValueError("stale execution time")
        self._boundary_step = execution_info.control_step
        self._boundary_time = execution_info.simulation_time

    def reset(self, observation, info, metadata, *, execution_info):
        self._execution(execution_info, reset=True)
        self.planned_actions_emitted = 0
        self.readiness_wait_actions_emitted = 0
        self.total_control_actions_emitted = 0
        self._wait_count = 0
        self.completion_events = []
        self._measured_tcp_gate_index = 0
        self._measured_tcp_gate_wait_ticks = 0
        self._last_measured_tcp_gate_hold = False
        self._last_public_observation = observation
        super().reset(observation, info, metadata)
        if self._done:
            self._done = bool(info.get("is_success")) and float(
                info.get("task_metrics", {}).get("cube_lift", 0.)
            ) >= _COLLECTION_LIFT_MARGIN
            if not self._done:
                self._refresh_current_segment(observation, info)
        if (self.readiness_config.measured_tcp_clearance_gate
                and not self.done and not self.failed and self.stage == "move_above_cube"):
            self._advance_measured_tcp_gates(observation)

    def act(self, observation=None, info=None):
        if self.done or self.failed or self._awaiting_observation:
            raise RuntimeError("invalid expert act lifecycle")
        if self.total_control_actions_emitted >= self.readiness_config.global_safety_cap:
            self._fail("global_control_safety_cap")
            raise RuntimeError("global control safety cap reached")
        segment = self._segments[self._segment_index]
        gate = self._pending_measured_tcp_gate(segment)
        self._last_measured_tcp_gate_hold = gate is not None
        self._last_wait = gate is not None or self._action_index >= len(segment.plan.actions)
        if gate is not None:
            if gate.after_actions == 0:
                self._fail(f"measured_tcp_gate_has_no_prior_action:{gate.name}")
                raise RuntimeError(self.failure_reason)
            action = segment.plan.actions[gate.after_actions - 1]
        else:
            action = segment.plan.actions[-1] if self._last_wait else segment.plan.actions[self._action_index]
        diagnostics = {
            "expert_version": self.version, "readiness_hold": self._last_wait,
            "planned_actions_emitted": self.planned_actions_emitted,
            "readiness_wait_actions_emitted": self.readiness_wait_actions_emitted,
            "total_control_actions_emitted": self.total_control_actions_emitted,
            "planned_segment_steps": len(segment.plan.actions), "stage_wait_ticks": self._wait_count,
            "measured_tcp_clearance_gate_hold": self._last_measured_tcp_gate_hold,
            "measured_tcp_clearance_gate": gate.name if gate is not None else None,
            "measured_tcp_clearance_gate_wait_ticks": self._measured_tcp_gate_wait_ticks,
        }
        if gate is not None and self._last_public_observation is not None:
            metrics = self._measured_tcp_gate_metrics(gate, self._last_public_observation)
            diagnostics.update({
                "measured_tcp_height_above_cube_top_m": metrics["height_above_cube_top_m"],
                "required_tcp_height_above_cube_top_m": gate.minimum_height_above_cube_top_m,
                "measured_tcp_horizontal_error_m": metrics["horizontal_error_m"],
            })
        self._awaiting_observation = True
        return ExpertAction(action=action, stage=segment.name, diagnostics=diagnostics)

    next_action = act

    def observe(self, observation, reward, terminated, truncated, info, *, execution_info):
        if not self._awaiting_observation:
            raise RuntimeError("observe requires preceding act")
        self._execution(execution_info)
        self._awaiting_observation = False
        self.total_control_actions_emitted += 1
        self._last_public_observation = observation
        if self._last_wait:
            self.readiness_wait_actions_emitted += 1
            if self._last_measured_tcp_gate_hold:
                self._measured_tcp_gate_wait_ticks += 1
            else:
                self._wait_count += 1
        else:
            self._action_index += 1
            self.planned_actions_emitted += 1
        self._actions_emitted = self.planned_actions_emitted
        policy = self.readiness_config.policies[self._segment_index]
        plan = self._segments[self._segment_index].plan
        exhausted = self._action_index >= len(plan.actions)
        if (policy.kind == "gripper_ready"
                and isinstance(execution_info, PickCubePositionExecutionInfoV1)):
            ready = execution_info.close_ready
        else:
            ready = policy.evaluate(self._ee_pose(observation), plan.target_pose, info, execution_info)
        if policy.kind == "task_outcome" and ready:
            self.completion_events.append({
                "stage": self.stage, "control_step": self._boundary_step,
                "wait_ticks": self._wait_count, "kind": policy.kind,
            })
            self._done = True
            return
        if truncated or terminated or info.get("task_failure", False):
            self._fail("episode_truncated" if truncated else "environment_terminated")
            return
        if self.readiness_config.measured_tcp_clearance_gate and self._segment_index == 0:
            self._advance_measured_tcp_gates(observation)
            gate = self._pending_measured_tcp_gate(self._segments[self._segment_index])
            if gate is not None and self._action_index >= gate.after_actions:
                if self._measured_tcp_gate_wait_ticks >= self.readiness_config.policies[0].hold_ticks:
                    self._fail(f"measured_tcp_clearance_timeout:{gate.name}")
                return
        if not exhausted:
            return
        if ready:
            self.completion_events.append({
                "stage": self.stage, "control_step": self._boundary_step,
                "wait_ticks": self._wait_count, "kind": policy.kind,
            })
            self._segment_index += 1
            self._action_index = 0
            self._wait_count = 0
            self._refresh_current_segment(observation, info)
        elif self._wait_count >= policy.hold_ticks:
            self._fail(policy.failure_reason)

    def _pending_measured_tcp_gate(self, segment):
        if (not self.readiness_config.measured_tcp_clearance_gate
                or self._segment_index != 0
                or self._measured_tcp_gate_index >= len(segment.plan.measured_tcp_gates)):
            return None
        gate = segment.plan.measured_tcp_gates[self._measured_tcp_gate_index]
        return gate if self._action_index >= gate.after_actions else None

    @classmethod
    def _measured_tcp_gate_metrics(cls, gate, observation):
        ee_pose = cls._ee_pose(observation)
        cube_position = cls._cube_position(observation)
        if not np.isfinite(ee_pose).all() or not np.isfinite(cube_position).all():
            raise ValueError("measured TCP clearance gate received a nonfinite public pose")
        height = float(ee_pose[2] - cube_position[2] - CUBE_HALF_SIZE)
        horizontal_error = float(np.linalg.norm(ee_pose[:2] - cube_position[:2]))
        ready = height >= gate.minimum_height_above_cube_top_m
        if gate.max_horizontal_error_m is not None:
            ready = ready and horizontal_error <= gate.max_horizontal_error_m
        return {
            "ready": bool(ready),
            "height_above_cube_top_m": height,
            "horizontal_error_m": horizontal_error,
            "tcp_pose": ee_pose,
            "cube_position": cube_position,
        }

    def _advance_measured_tcp_gates(self, observation):
        segment = self._segments[self._segment_index]
        while self._measured_tcp_gate_index < len(segment.plan.measured_tcp_gates):
            gate = segment.plan.measured_tcp_gates[self._measured_tcp_gate_index]
            if self._action_index < gate.after_actions:
                return
            metrics = self._measured_tcp_gate_metrics(gate, observation)
            if not metrics["ready"]:
                return
            self.completion_events.append({
                "stage": segment.name,
                "kind": "measured_tcp_clearance",
                "gate": gate.name,
                "control_step": self._boundary_step,
                "height_above_cube_top_m": metrics["height_above_cube_top_m"],
                "required_height_above_cube_top_m": gate.minimum_height_above_cube_top_m,
                "horizontal_error_m": metrics["horizontal_error_m"],
                "max_horizontal_error_m": gate.max_horizontal_error_m,
                "tcp_pose": metrics["tcp_pose"].tolist(),
                "cube_position": metrics["cube_position"].tolist(),
                "wait_ticks": self._measured_tcp_gate_wait_ticks,
            })
            self._measured_tcp_gate_index += 1
            self._measured_tcp_gate_wait_ticks = 0


__all__ += ["PickCubeReadinessConfig", "PickCubeReadinessSolution"]


@dataclass(frozen=True)
class PickCubePositionExecutionInfoV1(Contract):
    """Force-free gripper readiness from measured joint position and velocity."""

    schema_version: str
    control_step: int
    simulation_time: float
    measured_opening_m: float
    measured_opening_velocity_m_s: float
    target_opening_m: float
    close_ready: bool

    def validate(self):
        if self.schema_version != "pickcube-position-execution-info-v1":
            raise ValueError("unsupported PickCube Position execution info")
        values = (self.simulation_time, self.measured_opening_m,
                  self.measured_opening_velocity_m_s, self.target_opening_m)
        if (type(self.control_step) is not int or self.control_step < 0
                or any(not np.isfinite(float(value)) for value in values)
                or self.simulation_time < 0 or self.measured_opening_m < 0
                or not 0 <= self.target_opening_m <= 0.08):
            raise ValueError(
                "invalid PickCube Position execution boundary or gripper readback "
                f"(control_step={self.control_step!r}, "
                f"simulation_time={self.simulation_time!r}, "
                f"measured_opening_m={self.measured_opening_m!r}, "
                f"measured_opening_velocity_m_s={self.measured_opening_velocity_m_s!r}, "
                f"target_opening_m={self.target_opening_m!r})"
            )
        expected = bool(
            self.target_opening_m <= 0.045
            and self.measured_opening_m <= 0.045
            and abs(self.measured_opening_velocity_m_s) <= 0.005
        )
        if type(self.close_ready) is not bool or self.close_ready != expected:
            raise ValueError("PickCube close readiness must follow measured position/velocity only")


__all__ += ["PickCubePositionExecutionInfoV1"]
