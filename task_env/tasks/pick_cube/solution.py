"""Linear absolute-world-pose solution for the PickCube task.

This module deliberately owns no environment internals.  It consumes only the
observations and info mappings returned by ``TaskEnv.reset`` / ``TaskEnv.step``
and emits one public absolute-world-pose action at a time.  It is a small, non-replanning
baseline for validating the planner-to-rollout boundary before Stage 9 records
transitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Mapping

import numpy as np

from ...planners import AbsolutePosePlanner, AbsolutePosePlannerConfig, ExpertAction
from .assets import CUBE_HALF_SIZE


_ABOVE_CLEARANCE = 0.12
_DESCEND_DISTANCE = 0.13
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
class SegmentPlan:
    """One segment's immutable public-action sequence and diagnostic target."""

    actions: np.ndarray
    target_pose: np.ndarray

    def __post_init__(self) -> None:
        actions = np.asarray(self.actions, dtype=np.float32).copy()
        target_pose = np.asarray(self.target_pose, dtype=np.float32).reshape(7).copy()
        if actions.ndim != 2 or actions.shape[0] < 1:
            raise ValueError("segment actions must have shape [N, action_dim] with N >= 1")
        if not np.isfinite(actions).all() or not np.isfinite(target_pose).all():
            raise ValueError("segment plan must contain only finite values")
        actions.setflags(write=False)
        target_pose.setflags(write=False)
        object.__setattr__(self, "actions", actions)
        object.__setattr__(self, "target_pose", target_pose)


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
        target = start.copy()
        target[:3] = self._cube_position(observation) + np.array(
            [0.0, 0.0, CUBE_HALF_SIZE + _ABOVE_CLEARANCE], dtype=np.float32
        )
        return SegmentPlan(
            actions=self._planner.plan_to_pose(
                current_pose=start, goal_pose=target, gripper=1.0, settle_steps=0
            ),
            target_pose=target,
        )

    def _plan_descend(self, observation, info: Mapping[str, object]) -> SegmentPlan:
        del info
        start = self._ee_pose(observation)
        target = start.copy()
        target[:3] = self._cube_position(observation) + np.array(
            [0.0, 0.0, CUBE_HALF_SIZE + _ABOVE_CLEARANCE - _DESCEND_DISTANCE],
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
