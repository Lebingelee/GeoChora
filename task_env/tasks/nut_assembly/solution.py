"""Selected guarded NutAssembly expert and Outcome Completion V1.

This is the sole active task-specific expert. It uses only canonical public
observations, controller readiness, and the Core lifecycle/guard contracts.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, replace
import hashlib
import math
from numbers import Real
from pathlib import Path

import numpy as np

from ...controllers.canonical.contracts import digest
from ...controllers.canonical.execution import BoundaryWait, PoseStabilityWindow
from ...controllers.canonical.gripper_execution import EqualRateGripperServo
from ...planners import AbsolutePosePlanner, AbsolutePosePlannerConfig, ExpertAction
from ...utils.rotation import (
    normalize_quat_wxyz, quat_angle_wxyz, quat_multiply_wxyz,
    quat_wxyz_to_matrix, rotate_vector_wxyz,
)
from ..canonical_solution_lifecycle import (
    CanonicalSolutionLifecycle, SolutionCompletionPolicy,
)
from ..guarded_transition import GuardedTransitionEvaluator, TransitionGuardSpec
from ...objects.nut_assembly import (
    NUT_HALF_HEIGHT, NUT_HANDLE_LOCAL_X, PEG_HALF_HEIGHT,
)

OUTCOME_POLICY_ID = "nutassembly-outcome-oriented-completion-v1"


@dataclass(frozen=True)
class NutAssemblySolutionConfig:
    grasp_offset: tuple[float, float, float] = (0.0, 0.0, 0.045895)
    grasp_quaternion_wxyz: tuple[float, float, float, float] = (0.0038, 0.99993765, 0.0, 0.0105)
    grasp_opening_m: float = 0.0
    opening_range_m: float = 0.08
    table_top_z_m: float = 0.462
    nut_contact_margin_m: float = 0.001
    approach_height_m: float = 0.12
    translation_speed_m_s: float = 0.06
    translation_acceleration_m_s2: float = 0.45
    rotation_speed_rad_s: float = 3.0
    rotation_acceleration_rad_s2: float = 27.0
    settle_duration_s: float = 0.26666666666666666
    close_transition_s: float = 0.3333333333333333
    close_settle_s: float = 0.5
    release_transition_s: float = 0.3333333333333333
    release_settle_s: float = 0.6666666666666666
    pose_position_ready_m: float = 0.007
    pose_rotation_ready_rad: float = 0.06
    readiness_stable_s: float = 0.1
    gripper_stable_speed_m_s: float = 0.003
    opening_stable_range_m: float = 0.0005
    grasp_min_closing_force_N: float = 25.0
    max_pose_hold_s: float = 3.0
    max_close_hold_s: float = 8.0
    max_release_hold_s: float = 3.0
    capture_translation_slip_m: float = 0.008
    capture_rotation_slip_rad: float = 0.15
    verify_lift_m: float = 0.1
    max_stage_plan_s: float = 6.0
    action_budget_s: float = 60.0

    def __post_init__(self):
        if len(self.grasp_offset) != 3 or len(self.grasp_quaternion_wxyz) != 4:
            raise ValueError("selected grasp pose dimensions changed")
        values = (*self.grasp_offset, *self.grasp_quaternion_wxyz,
                  *(v for k, v in asdict(self).items()
                    if k not in {"grasp_offset", "grasp_quaternion_wxyz", "grasp_opening_m"}))
        if not all(math.isfinite(float(v)) for v in values):
            raise ValueError("selected solution configuration must be finite")
        if not 0.0 <= self.grasp_opening_m < self.opening_range_m:
            raise ValueError("selected grasp opening is outside range")
        normalize_quat_wxyz(self.grasp_quaternion_wxyz)


class NutAssemblyOutcomeSolutionV1:
    """One task-owned implementation of guarded V2/V5/R3 Outcome V1 behavior."""

    version = "nutassembly-r5-v5-guarded-outcome-solution-v3"
    STAGES = (
        "approach_nut", "descend_to_handle", "close_gripper", "verify_lift",
        "raise_for_transport", "move_above_square_peg", "align_nut_yaw",
        "descend_to_peg_top", "lower_nut_to_table", "open_gripper", "release_retreat",
    )
    capture_stages = frozenset({
        "verify_lift", "raise_for_transport", "move_above_square_peg",
        "align_nut_yaw", "descend_to_peg_top", "lower_nut_to_table",
    })
    height_warning_limit_m = 0.0003
    outward_handle_offset_m = 0.024
    servo_height_compensation_m = 0.0006514767471602623
    descend_endpoint_command_bias_m = servo_height_compensation_m
    minimum_pose_wait_s = 0.5
    pose_window_s = 0.2
    tracking_position_rmse_limit_m = 0.0001
    pose_span_m = 0.0001
    pose_speed_m_s = 0.002
    postclose_hold_s = 0.1
    stable_height_tolerance_m = 0.0001
    close_authorization_deadline_s = 1.5
    primary_guard_id = "primary_controller_close_ready"
    alternative_guard_id = "alternative_force_8n"
    alternative_force_threshold_N = 8.0
    authorization_dwell_s = 0.1
    authorization_deadline_s = 1.5
    early_alternative_authorization = True

    def __init__(self, *, config=None, control_dt, arm_hold, physics_dt_s):
        self.config = config or NutAssemblySolutionConfig()
        self.control_dt = float(control_dt)
        self.physics_dt_s = float(physics_dt_s)
        if abs(self.control_dt - 0.01) > 1e-12 or abs(self.physics_dt_s - 0.002) > 1e-12:
            raise ValueError("Outcome Completion V1 admits only the accepted 100 Hz / 2 ms recipe")
        if (self.config.capture_translation_slip_m != 0.008
                or self.config.capture_rotation_slip_rad != 0.15
                or self.config.pose_position_ready_m != 0.007
                or self.config.pose_rotation_ready_rad != 0.06
                or self.config.action_budget_s != 60.0):
            raise ValueError("selected outcome policy requires unchanged limits and budget")
        self.arm_hold = arm_hold
        self._planner = AbsolutePosePlanner(AbsolutePosePlannerConfig(
            max_translation_per_step=self.config.translation_speed_m_s * self.control_dt,
            max_translation_acceleration_per_step=self.config.translation_acceleration_m_s2 * self.control_dt**2,
            max_rotation_per_step=self.config.rotation_speed_rad_s * self.control_dt,
            max_rotation_acceleration_per_step=self.config.rotation_acceleration_rad_s2 * self.control_dt**2,
            settle_steps=self._ticks(self.config.settle_duration_s),
            max_steps=self._ticks(self.config.max_stage_plan_s),
        ))
        self._lifecycle = CanonicalSolutionLifecycle(
            SolutionCompletionPolicy.ON_EXPERT_TERMINAL_STAGE)
        self.policy_mapping = {
            "schema": "nutassembly-close-authorization-primary-alternative-v1",
            "primary_guard": {"guard_id": self.primary_guard_id,
                "conditions": ["controller_close_ready", "grasped_nut", "pose_ready"],
                "meaning": "historical canonical Controller Readiness"},
            "alternative_guard": {"guard_id": self.alternative_guard_id,
                "conditions": ["measured_force_at_least_threshold", "force_mode_active",
                    "force_mode_initialized", "grasped_nut", "pose_ready"],
                "threshold_N": self.alternative_force_threshold_N,
                "meaning": "task-facing alternative authorization; never relabeled as Controller Readiness"},
            "selection": {"allow_early_alternative": True,
                "same_sample_tie_break": "primary_controller_readiness_first"},
            "required_continuous_dwell_s": self.authorization_dwell_s,
            "deadline_from_close_stage_entry_s": self.authorization_deadline_s,
            "sampling": {"clock": "native-physics-state-and-canonical-controller-feedback",
                "sample_period_s": self.physics_dt_s,
                "sample_interval": "measured-left-closed-right-open",
                "missing_samples": "break-continuity; no interpolation",
                "decision_boundary": "next-outer-control-boundary"},
            "post_authorization_hold_s": self.postclose_hold_s,
            "physical_force_regulation": {"target_N": 10.0, "cap_N": 10.0,
                "controller_law": "unchanged R3"},
        }
        self.policy_identity = digest({"policy": self.policy_mapping,
            "evaluator": GuardedTransitionEvaluator.version,
            "evaluator_source_sha256": hashlib.sha256(
                Path(__import__(GuardedTransitionEvaluator.__module__, fromlist=["__file__"]).__file__).read_bytes()
            ).hexdigest()})
        self.outcome_policy_mapping = {
            "policy_id": OUTCOME_POLICY_ID, "rate_hz": 100,
            "grasp_control": {
                "target": "fixed_world_pose",
                "controller_update": "recompute_each_control_boundary",
                "joint_target_hold_during_close": False,
            },
            "endpoint_z_alignment": {
                "command_bias_m": self.descend_endpoint_command_bias_m,
                "acceptance_compensation_m": self.servo_height_compensation_m,
                "aligned": self.descend_endpoint_command_bias_m == self.servo_height_compensation_m,
            },
            "tracking_gate": {
                "metric": "rolling_rms_euclidean_tcp_position_error",
                "window_s": self.pose_window_s,
                "minimum_samples": self._ticks(self.pose_window_s),
                "strict_limit_m": self.tracking_position_rmse_limit_m,
            },
            "allowlist": [{"stage": "descend_to_handle", "reason": "stable_height_mismatch",
                "maximum_occurrences": 1, "maximum_height_residual_m": self.height_warning_limit_m,
                "pose_position_ready_m": self.config.pose_position_ready_m,
                "pose_rotation_ready_rad": self.config.pose_rotation_ready_rad,
                "minimum_pose_wait_s": self.minimum_pose_wait_s,
                "window_s": self.pose_window_s, "minimum_samples": self._ticks(self.pose_window_s),
                "axis_span_m": self.pose_span_m, "speed_m_s": self.pose_speed_m_s}],
            "strict_height_tolerance_m": self.stable_height_tolerance_m,
            "capture_translation_slip_m": self.config.capture_translation_slip_m,
            "capture_rotation_slip_rad": self.config.capture_rotation_slip_rad,
            "close_authorization_policy_identity": self.policy_identity,
            "force_target_and_cap_N": 10.0, "action_budget_s": self.config.action_budget_s,
            "ordered_stages": list(self.STAGES),
            "completion": "all authored actions and endpoint gates including retreat; final inserted_on_peg AND released_nut",
            "fail_closed": ["unlisted_or_repeated_failure", "invalid_state_or_clock",
                "capture_violation", "task_failure", "runtime_error", "terminated",
                "truncated", "action_budget_exhausted", "incomplete_plan_or_retreat"],
            "diagnostic_shadow_override": False,
        }
        self.outcome_policy_identity = digest(self.outcome_policy_mapping)
        self.identity = digest({"version": self.version,
            "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "solution_config": asdict(self.config),
            "close_authorization_policy_identity": self.policy_identity,
            "outcome_policy_identity": self.outcome_policy_identity,
            "lifecycle_policy": SolutionCompletionPolicy.ON_EXPERT_TERMINAL_STAGE.value})
        self._clear_rollout()

    def _ticks(self, seconds):
        return max(1, int(math.ceil(float(seconds) / self.control_dt - 1e-10)))

    def _clear_rollout(self):
        self._stage_index = 0
        self._emitted = 0
        self._index = 0
        self._hold_ticks = 0
        self._stable_ticks = 0
        self._actions = np.empty((0, 8), dtype=np.float32)
        self._goal = np.zeros(7, dtype=np.float64)
        self._grasp_pose = None
        self._captured_position = None
        self._captured_rotation = None
        self._last_opening = 0.0
        self._opening_history = []
        self._stability = PoseStabilityWindow()
        self._pose_wait_start = None
        self._tracking_rmse_passed = False
        self._postclose_hold_ticks = 0
        self._lift_released = False
        self._close_gate = None
        self._close_action_completed_at_s = None
        self._transition_guard_state = None
        self._close_authorization = None
        self._last_guard_decision = None
        self._readiness_warnings = []
        self._stage_receipts = []
        self._pending_action = None
        self._task_success = False
        self._runtime_error = None
        self.events = []
        self.arm_hold.locked = False
        self._lifecycle.reset()
        self._last_observed_step = 0
        self._last_observed_time_s = 0.0

    @property
    def stage(self):
        return self.STAGES[min(self._stage_index, len(self.STAGES) - 1)]

    @property
    def done(self):
        return self._runtime_error is None and self._lifecycle.expert_complete

    @property
    def failed(self):
        return self._runtime_error is not None or self._lifecycle.expert_failed

    @property
    def failure_reason(self):
        return self._runtime_error or self._lifecycle.failure_reason

    @property
    def lifecycle(self):
        return self._lifecycle

    @property
    def readiness_warnings(self):
        return deepcopy(self._readiness_warnings)

    @property
    def task_success(self):
        return self._task_success

    @property
    def planned_trajectory_completed(self):
        return (len(self._stage_receipts) == len(self.STAGES)
            and [r["stage"] for r in self._stage_receipts] == list(self.STAGES)
            and all(r["endpoint_pass"] and r["planned_actions"] > 0
                and r["planned_actions_executed"] == r["planned_actions"]
                for r in self._stage_receipts))

    @property
    def outcome_complete(self):
        return self.done and self.task_success and self.planned_trajectory_completed

    @property
    def original_expert_lifecycle_status(self):
        warning = next(iter(self._readiness_warnings), None)
        return {"policy": "original-guarded-v2-v5-strict-gates",
            "assessment": "strict gate evaluated on current execution; not historical qualification",
            "expert_complete": bool(not warning and self.done),
            "expert_failed": bool(warning or self.failed),
            "failure_reason": warning["reason"] if warning else self.failure_reason,
            "failure_step": warning["control_step"] if warning else None}

    def outcome_report(self):
        return {"completion_policy_id": OUTCOME_POLICY_ID,
            "completion_policy_identity": self.outcome_policy_identity,
            "task_success": self.task_success,
            "planned_trajectory_completed": self.planned_trajectory_completed,
            "outcome_complete": self.outcome_complete,
            "readiness_warnings": self.readiness_warnings,
            "original_expert_lifecycle_status": self.original_expert_lifecycle_status,
            "execution_lifecycle_status": self.lifecycle.to_mapping()["status"],
            "stage_execution_receipts": deepcopy(self._stage_receipts),
            "runtime_error": self._runtime_error, "unapproved_override_used": False}

    @staticmethod
    def _finite(value):
        if isinstance(value, dict):
            return all(NutAssemblyOutcomeSolutionV1._finite(v) for v in value.values())
        if isinstance(value, (list, tuple, np.ndarray)):
            return all(NutAssemblyOutcomeSolutionV1._finite(v) for v in value)
        if isinstance(value, (Real, np.bool_)):
            return math.isfinite(float(value))
        return value is None or isinstance(value, str)

    @staticmethod
    def _ee(obs):
        return np.asarray(obs["state"]["ee_pose"], dtype=np.float64).reshape(7)

    @staticmethod
    def _body(obs, name):
        return np.asarray(obs["privileged_state"][name + "_body_pose"][0], dtype=np.float64).reshape(7)

    def _clock(self, info):
        step = info.get("control_step", self._emitted)
        time_s = info.get("simulation_time_s", float(step) * self.control_dt)
        if isinstance(step, bool) or not isinstance(step, (int, np.integer)):
            raise ValueError("integer control_step required")
        return int(step), float(time_s)

    def _validate(self, obs, info, reward=0.0, readiness=None, samples=()):
        if not self._finite((obs, info, reward, samples)):
            raise ValueError("nonfinite state or evidence")
        for pose in (self._ee(obs), self._body(obs, "square_nut_v1"),
                     self._body(obs, "square_peg_v1")):
            if not np.isfinite(pose).all() or not 0.99 <= np.linalg.norm(pose[3:]) <= 1.01:
                raise ValueError("invalid pose quaternion")
        metrics = info["task_metrics"]
        if not all(isinstance(v, (bool, np.bool_)) for v in (
                metrics["inserted_on_peg"], metrics["released_nut"],
                metrics["task_success"], info["is_success"], info.get("task_failure", False))):
            raise ValueError("canonical outcome predicates must be boolean")
        success = bool(metrics["inserted_on_peg"] and metrics["released_nut"])
        if success != bool(info["is_success"]) or success != bool(metrics["task_success"]):
            raise ValueError("inconsistent canonical task success")
        if readiness is not None:
            if not self._finite(readiness.to_mapping()):
                raise ValueError("nonfinite readiness")
            if abs(readiness.gripper.force_limit_N - 10.0) > 1e-12:
                raise ValueError("selected controller force cap changed")
        return success

    def reset(self, obs, info, metadata):
        self._clear_rollout()
        try:
            self._validate(obs, info)
            if type(info.get("control_step")) is not int or info.get("control_step") != 0 or info.get("simulation_time_s") != 0.0:
                raise ValueError("reset clock must be zero")
            schema = metadata.get("action_schema", {})
            if (schema.get("controller_kind"), schema.get("reference"),
                    schema.get("rotation_representation")) != (
                    "absolute_pose", "world", "quaternion_wxyz"):
                raise ValueError("absolute_pose/world/wxyz required")
        except (ValueError, KeyError, TypeError):
            self._fail("invalid_state_or_clock")
            return
        self._lifecycle.observe_task_outcome(task_success=False, task_failure=False,
            control_step=0, simulation_time_s=0.0)
        self._last_opening = float(info["task_metrics"]["gripper_opening"])
        self._plan(obs)
        success = bool(info["is_success"])
        self._task_success = success
        if success:
            self._lifecycle.observe_task_outcome(task_success=True, task_failure=False,
                control_step=0, simulation_time_s=0.0)

    def _plan(self, obs):
        ee, nut, peg = self._ee(obs), self._body(obs, "square_nut_v1"), self._body(obs, "square_peg_v1")
        stage = self.stage
        config = self.config
        orientation = normalize_quat_wxyz(config.grasp_quaternion_wxyz)
        handle = nut[:3] + rotate_vector_wxyz(nut[3:],
            np.asarray([NUT_HANDLE_LOCAL_X + self.outward_handle_offset_m, 0.0, 0.0]))
        pose = ee.copy(); pose[3:] = orientation
        gripper = 2.0 * config.grasp_opening_m / config.opening_range_m - 1.0
        if stage == "approach_nut":
            pose[:3] = handle + np.asarray([0.0, 0.0, config.approach_height_m]); gripper = 1.0
        elif stage == "descend_to_handle":
            pose[:3] = handle + np.asarray(config.grasp_offset); gripper = 1.0
        elif stage == "close_gripper":
            pose = self._grasp_pose.copy()
        elif stage == "verify_lift":
            self._captured_position = quat_wxyz_to_matrix(ee[3:]).T @ (nut[:3] - ee[:3])
            inverse = ee[3:].copy(); inverse[1:] *= -1
            self._captured_rotation = quat_multiply_wxyz(inverse, nut[3:])
            pose[:3] = ee[:3] + np.asarray([0.0, 0.0, config.verify_lift_m])
        else:
            nut_to_ee = nut[:3] - ee[:3]
            hover_nut = peg[:3] + np.asarray([0.0, 0.0, PEG_HALF_HEIGHT + 0.08])
            if stage == "raise_for_transport":
                pose[2] = (hover_nut - nut_to_ee)[2]
            elif stage == "move_above_square_peg":
                pose[:3] = hover_nut - nut_to_ee
            elif stage == "align_nut_yaw":
                angle = self._square_yaw_correction(nut[3:])
                qz = np.asarray([np.cos(0.5 * angle), 0.0, 0.0, np.sin(0.5 * angle)])
                pose[3:] = quat_multiply_wxyz(qz, ee[3:])
            elif stage == "descend_to_peg_top":
                target = peg[:3] + np.asarray([0.0, 0.0,
                PEG_HALF_HEIGHT + NUT_HALF_HEIGHT + config.nut_contact_margin_m])
                pose[:3] = target - nut_to_ee
            elif stage == "lower_nut_to_table":
                target = np.asarray([peg[0], peg[1], config.table_top_z_m + NUT_HALF_HEIGHT + config.nut_contact_margin_m])
                pose[:3] = target - nut_to_ee
            elif stage == "open_gripper":
                pose = ee.copy(); gripper = 1.0
            elif stage == "release_retreat":
                pose[:3] = ee[:3] + np.asarray([0.0, 0.0, 0.1]); gripper = 1.0
        self._goal = pose.copy(); self._index = 0; self._hold_ticks = 0; self._stable_ticks = 0
        if stage == "close_gripper":
            self._actions = self._planner.plan_gripper_transition(pose=pose,
                start_gripper=1.0, goal_gripper=gripper,
                steps=self._ticks(config.close_transition_s), settle_steps=self._ticks(config.close_settle_s))
        elif stage == "open_gripper":
            self._actions = self._planner.plan_gripper_transition(pose=pose,
                start_gripper=2.0 * config.grasp_opening_m / config.opening_range_m - 1.0,
                goal_gripper=1.0, steps=self._ticks(config.release_transition_s),
                settle_steps=self._ticks(config.release_settle_s))
        else:
            self._actions = self._planner.plan_to_pose(current_pose=ee, goal_pose=pose, gripper=gripper)
        if stage in {"approach_nut", "descend_to_handle"}:
            nominal = self._goal.copy()
            if stage == "descend_to_handle":
                command = nominal.copy(); command[2] -= self.descend_endpoint_command_bias_m
            else:
                command = nominal
            self._actions = self._planner.plan_to_pose(current_pose=ee, goal_pose=command, gripper=1.0)
            self._goal = nominal
            if stage == "descend_to_handle":
                self._grasp_pose = nominal.copy()
        if stage == "close_gripper":
            hold_pose = ee.copy()
            self._goal = hold_pose
            self._actions[:, :7] = hold_pose.astype(np.float32)
            self._close_gate = BoundaryWait(self._emitted * self.control_dt,
                self.close_authorization_deadline_s)
            self.events.append({"event": "close_start", "t": self._emitted * self.control_dt,
                "stable_pose": hold_pose.tolist()})
            self._transition_guard_state = self._evaluator(self._close_gate.start_s).to_mapping()
            self._close_action_completed_at_s = None
            self._close_authorization = None
        if stage == "verify_lift":
            hold_pose = ee.copy()
            self._postclose_hold_ticks = self._ticks(self.postclose_hold_s)
            hold = np.tile(np.asarray([*hold_pose, -1.0], dtype=np.float32),
                (self._postclose_hold_ticks, 1))
            self._actions = np.concatenate((hold, self._actions))
            if len(self._actions) * self.control_dt > config.max_stage_plan_s:
                raise ValueError("hold + lift exceeds stage plan budget")
            self.events.append({"event": "authorized_hold_start", "t": self._emitted * self.control_dt,
                "duration_s": self._postclose_hold_ticks * self.control_dt})
        if len(self._actions) < 1 or self._actions.shape[1] != 8:
            raise ValueError("selected solution requires nonempty universal 8D action plan")
        if self._emitted + len(self._actions) > self._ticks(config.action_budget_s):
            self._fail("canonical_solution_action_budget")
        if len(self._stage_receipts) != self._stage_index:
            raise RuntimeError("outcome stage sequence mismatch")
        self._stage_receipts.append({"stage": stage, "planned_actions": len(self._actions),
            "planned_actions_executed": 0, "actions_executed": 0,
            "entry_step": self._emitted, "completed_step": None, "endpoint_pass": False})

    @staticmethod
    def _square_yaw_correction(quaternion):
        w, x, y, z = normalize_quat_wxyz(quaternion)
        yaw = float(math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z)))
        period = 0.5 * math.pi
        return -float((yaw + 0.5 * period) % period - 0.5 * period)

    def act(self):
        if self._pending_action is not None:
            self.abort("missing_execution_boundary")
        if self._emitted >= self._ticks(self.config.action_budget_s) and not self.failed:
            self._fail("canonical_solution_action_budget")
        if self.failed or self.done:
            raise RuntimeError("cannot act after outcome execution terminal")
        if self.stage == "verify_lift" and self._index >= self._postclose_hold_ticks and not self._lift_released:
            self.arm_hold.locked = False; self._lift_released = True
            self.events.append({"event": "verify_lift_motion_start", "t": self._emitted * self.control_dt})
        planned = self._index < len(self._actions)
        hold = not planned
        action = self._actions[self._index] if planned else self._actions[-1]
        proposal = ExpertAction(action=action.copy(), stage=self.stage,
            diagnostics={"version": self.version, "stage_index": self._stage_index,
                "stage_step": self._index, "readiness_hold": hold,
                "hold_seconds": self._hold_ticks * self.control_dt,
                "control_dt": self.control_dt,
                "completion_policy_id": OUTCOME_POLICY_ID,
                "readiness_warning_count": len(self._readiness_warnings)})
        if planned: self._index += 1
        else: self._hold_ticks += 1
        self._emitted += 1
        self._pending_action = {"stage": proposal.stage, "planned": planned}
        return proposal

    def _evaluator(self, start_time_s):
        guards = (
            TransitionGuardSpec(self.primary_guard_id, "close_gripper", "verify_lift",
                ("controller_close_ready", "grasped_nut", "pose_ready"), 0),
            TransitionGuardSpec(self.alternative_guard_id, "close_gripper", "verify_lift",
                ("measured_force_at_least_threshold", "force_mode_active", "force_mode_initialized",
                 "grasped_nut", "pose_ready"), 1),
        )
        evaluator = GuardedTransitionEvaluator(source_stage="close_gripper", guards=guards,
            required_duration_s=self.authorization_dwell_s, start_time_s=float(start_time_s),
            deadline_s=float(start_time_s) + self.authorization_deadline_s,
            sample_period_s=self.physics_dt_s, allow_early_alternative=True)
        if self._transition_guard_state is not None:
            evaluator.restore_state(self._transition_guard_state)
        return evaluator

    def make_native_guard_sample(self, state, info, diagnostics):
        if self.stage != "close_gripper":
            raise ValueError("guard samples only belong to close_gripper")
        ee_pose = state.pose_world["panda-v1/ee"]
        ee = np.asarray([*ee_pose.position, *ee_pose.quaternion_wxyz], dtype=float)
        pose_ready = (np.linalg.norm(ee[:3] - self._goal[:3]) <= self.config.pose_position_ready_m
            and quat_angle_wxyz(ee[3:], self._goal[3:]) <= self.config.pose_rotation_ready_rad)
        force = float(diagnostics["closing_force_N"])
        active, initialized = bool(diagnostics["force_mode_active"]), bool(diagnostics["force_mode_initialized"])
        controller_ready = bool(diagnostics["controller_close_ready"])
        grasped = bool(info["task_metrics"].get("grasped_nut", False))
        conditions = {"controller_close_ready": controller_ready,
            "measured_force_at_least_threshold": force >= self.alternative_force_threshold_N,
            "force_mode_active": active, "force_mode_initialized": initialized,
            "grasped_nut": grasped, "pose_ready": pose_ready}
        return {"sample_time_s": float(state.simulation_time), "sample_duration_s": self.physics_dt_s,
            "conditions": conditions, "values": {"control_step": int(state.control_step),
            "closing_force_N": force, "force_mode_active": active,
            "force_mode_initialized": initialized, "controller_close_ready": controller_ready,
            "grasped_nut": grasped, "pose_ready": pose_ready,
            "finger_opening_m": float(diagnostics["measured_opening_m"])}}

    def _authorize_close(self, obs, terminated, truncated, transition_samples):
        if terminated or truncated:
            self._fail("environment_terminated"); return
        if self._emitted > self._ticks(self.config.action_budget_s):
            self._fail("canonical_solution_action_budget"); return
        if self._index < len(self._actions):
            if self._close_gate.wait_until(self._last_observed_time_s, False) == "timeout":
                self._fail("close_gripper_authorization_deadline")
            return
        now = float(self._last_observed_time_s)
        if self._close_action_completed_at_s is None:
            self._close_action_completed_at_s = now
            self._transition_guard_state = self._evaluator(self._close_gate.start_s).to_mapping()
        evaluator = self._evaluator(self._close_gate.start_s)
        for sample in transition_samples or ():
            if float(sample["sample_time_s"]) < self._close_action_completed_at_s - 1e-10:
                continue
            decision = evaluator.observe(sample)
            self._last_guard_decision = decision.to_mapping()
            self._transition_guard_state = evaluator.to_mapping()
            if decision.outcome == "RECOVERY_REQUIRED":
                self.events.append({"event": "close_authorization_guard_recovery_required",
                    "t": decision.simulation_time_s, "evidence": decision.evidence})
            elif decision.outcome == "AUTHORIZED":
                self._close_authorization = {"authorization_guard_id": decision.selected_guard_id,
                    "authorization_time_s": decision.simulation_time_s,
                    "transition_consumed_at_outer_boundary_s": now,
                    "source_stage": decision.source_stage, "target_stage": decision.target_stage,
                    "required_stable_duration_s": self.authorization_dwell_s,
                    **decision.evidence, "policy_identity": self.policy_identity}
                self.events.append({"event": "close_transition_authorized",
                    "t": decision.simulation_time_s, **self._close_authorization,
                    "controller_close_ready": bool(decision.evidence["conditions"]["controller_close_ready"]),
                    "fallback_used": False})
                self._stage_index += 1; self._plan(obs); return
            elif decision.outcome == "FAILED":
                self._fail("close_gripper_authorization_deadline"); return
        if now >= self._close_gate.start_s + self.authorization_deadline_s - 1e-10:
            self._fail("close_gripper_authorization_deadline")

    def _stable_height_ready(self, achieved_z, expected_z):
        if abs(achieved_z - expected_z) <= self.stable_height_tolerance_m:
            return True
        if self.stage != "descend_to_handle" or self._readiness_warnings or self._stability.start is None:
            return False
        now = self._emitted * self.control_dt
        window = [x for x in self._stability.history if x[0] >= now - self.pose_window_s - 1e-8]
        if not window:
            return False
        poses = np.asarray([x[1][:3] for x in window])
        span = np.ptp(poses, axis=0)
        speeds = [np.linalg.norm(b[1][:3] - a[1][:3]) / (b[0] - a[0])
                  for a, b in zip(window, window[1:])]
        pose = window[-1][1]
        position = float(np.linalg.norm(pose[:3] - self._goal[:3]))
        rotation = float(quat_angle_wxyz(pose[3:], self._goal[3:]))
        measurements = {"control_step": self._emitted, "simulation_time_s": now,
            "stage": self.stage, "reason": "stable_height_mismatch",
            "achieved_z_m": float(achieved_z), "strict_expected_z_m": float(expected_z),
            "height_residual_m": float(achieved_z - expected_z),
            "strict_tolerance_m": self.stable_height_tolerance_m,
            "admission_limit_m": self.height_warning_limit_m, "sample_count": len(window),
            "wait_s": now - self._stability.start, "position_error_m": position,
            "rotation_error_rad": rotation, "axis_span_m": span.tolist(),
            "maximum_speed_m_s": float(max(speeds, default=math.inf))}
        allowed = (self._finite(measurements) and self._index == len(self._actions)
            and abs(achieved_z - expected_z) <= self.height_warning_limit_m
            and position <= self.config.pose_position_ready_m
            and rotation <= self.config.pose_rotation_ready_rad
            and measurements["wait_s"] >= self.minimum_pose_wait_s
            and len(window) >= self._ticks(self.pose_window_s)
            and max(span) <= self.pose_span_m
            and measurements["maximum_speed_m_s"] <= self.pose_speed_m_s)
        self.events.append({"event": "readiness_warning" if allowed else "readiness_warning_rejected",
            "t": now, **measurements})
        if allowed:
            self._readiness_warnings.append({**measurements, "policy_id": OUTCOME_POLICY_ID,
                "policy_identity": self.outcome_policy_identity})
        return bool(allowed)

    def _tracking_position_rmse(self, now, target_xyz):
        window = [x for x in self._stability.history
                  if x[0] >= now - self.pose_window_s - 1e-8]
        if len(window) < self._ticks(self.pose_window_s):
            return math.inf
        errors = np.asarray([pose[:3] - target_xyz for _, pose in window], dtype=np.float64)
        return float(np.sqrt(np.mean(np.einsum("ij,ij->i", errors, errors))))

    def _observe_stage(self, obs, info, readiness):
        receipt = self._stage_receipts[-1]
        if (self._index != receipt["planned_actions_executed"]
                or self.stage == "release_retreat" and not all(
                    item["endpoint_pass"] for item in self._stage_receipts[:-1])):
            self._fail("incomplete_planned_trajectory"); return
        if self._emitted > self._ticks(self.config.action_budget_s):
            self._fail("canonical_solution_action_budget"); return
        metrics = info["task_metrics"]
        opening = float(metrics["gripper_opening"])
        self._last_opening = opening
        self._opening_history.append(opening)
        self._opening_history = self._opening_history[-self._ticks(self.config.readiness_stable_s):]
        if self._index < len(self._actions):
            return
        ee, config, stage = self._ee(obs), self.config, self.stage
        pose_ready = (np.linalg.norm(ee[:3] - self._goal[:3]) <= config.pose_position_ready_m
            and quat_angle_wxyz(ee[3:], self._goal[3:]) <= config.pose_rotation_ready_rad)
        limit = config.max_pose_hold_s
        ready = pose_ready
        if stage == "close_gripper":
            force_ready = bool(readiness and readiness.gripper.close_ready)
            stable = (len(self._opening_history) == self._ticks(config.readiness_stable_s)
                and max(self._opening_history) - min(self._opening_history) <= config.opening_stable_range_m)
            contact = bool(readiness and readiness.gripper.closing_force_N >= config.grasp_min_closing_force_N)
            ready = bool(metrics["grasped_nut"]) and (force_ready or (stable and contact))
            limit = config.max_close_hold_s
        elif stage == "verify_lift":
            nut = self._body(obs, "square_nut_v1")
            relative = quat_wxyz_to_matrix(ee[3:]).T @ (nut[:3] - ee[:3])
            inverse = ee[3:].copy(); inverse[1:] *= -1
            rotation = quat_multiply_wxyz(inverse, nut[3:])
            capture_ready = (np.linalg.norm(relative - self._captured_position) <= config.capture_translation_slip_m
                and quat_angle_wxyz(rotation, self._captured_rotation) <= config.capture_rotation_slip_rad)
            ready = pose_ready and bool(metrics["lifted_nut"]) and capture_ready
        elif stage == "move_above_square_peg":
            ready = pose_ready and bool(metrics["hovered_over_peg"])
        elif stage == "lower_nut_to_table":
            ready = pose_ready and bool(metrics["inserted_on_peg"])
        elif stage == "open_gripper":
            ready = opening >= 0.065; limit = config.max_release_hold_s
        self._stable_ticks = self._stable_ticks + 1 if ready else 0
        if self._stable_ticks >= self._ticks(config.readiness_stable_s):
            if stage == "release_retreat":
                step, now = self._clock(info)
                self._lifecycle.complete_expert(terminal_stage_completed=True,
                    final_task_success=bool(info.get("is_success", False)),
                    control_step=step, simulation_time_s=now)
                return
            self._stage_index += 1
            self._plan(obs)
        elif self._hold_ticks >= self._ticks(limit):
            self._fail(stage + "_readiness_timeout")

    def observe(self, obs, reward, terminated, truncated, info, *, readiness=None,
                transition_samples=None):
        if self.done or self.failed:
            raise RuntimeError("cannot observe terminal outcome execution")
        try:
            success = self._validate(obs, info, reward, readiness, transition_samples or ())
            step, now = self._clock(info)
            if (self._pending_action is None or step != self._emitted
                    or step != self._last_observed_step + 1 or not math.isfinite(now)
                    or abs(now - step * self.control_dt) > 1e-7):
                raise ValueError("invalid execution clock or missing action")
            if readiness is not None:
                readiness.require_boundary(step, now)
        except (ValueError, KeyError, TypeError):
            self._task_success = False; self._fail("invalid_state_or_clock"); return
        self._task_success = success
        receipt = self._stage_receipts[-1]
        receipt["actions_executed"] += 1
        receipt["planned_actions_executed"] += int(self._pending_action["planned"])
        self._pending_action = None
        self._last_observed_step, self._last_observed_time_s = step, now
        if terminated and truncated:
            self._fail("invalid_runtime_terminal_flags"); return
        if self._emitted > self._ticks(self.config.action_budget_s):
            self._fail("canonical_solution_action_budget"); return
        if terminated or truncated or info.get("task_failure", False):
            self._lifecycle.observe_task_outcome(task_success=success,
                task_failure=bool(info.get("task_failure", False)), terminated=bool(terminated),
                truncated=bool(truncated), control_step=step, simulation_time_s=now)
            return
        if self.stage in self.capture_stages and not self._capture_valid(obs):
            self._fail("capture_constraint_violation"); return
        self._lifecycle.observe_task_outcome(task_success=success,
            task_failure=bool(info.get("task_failure", False)), control_step=step,
            simulation_time_s=now)
        if self._lifecycle.terminal:
            return
        if self.stage == "close_gripper":
            self._authorize_close(obs, terminated, truncated, transition_samples)
        elif self.stage == "descend_to_handle" and self._index >= len(self._actions):
            now = self._emitted * self.control_dt
            pose = self._ee(obs)
            if self._pose_wait_start is None:
                self._pose_wait_start = now
            stable, span, speeds = self._stability.is_stable(now, pose,
                minimum_wait_s=self.minimum_pose_wait_s, window_s=self.pose_window_s,
                minimum_samples=self._ticks(self.pose_window_s), axis_span_m=self.pose_span_m,
                speed_m_s=self.pose_speed_m_s)
            tracking_target = self._goal[:3].copy()
            tracking_target[2] -= self.descend_endpoint_command_bias_m
            tracking_rmse = self._tracking_position_rmse(now, tracking_target)
            if (tracking_rmse < self.tracking_position_rmse_limit_m
                    and not self._tracking_rmse_passed):
                self._tracking_rmse_passed = True
                self.events.append({"event": "tracking_rmse_satisfied", "t": now,
                    "target_xyz_m": tracking_target.tolist(),
                    "rolling_position_rmse_m": tracking_rmse,
                    "window_s": self.pose_window_s,
                    "sample_count": self._ticks(self.pose_window_s)})
            stable = stable and self._tracking_rmse_passed
            if stable:
                expected = self._goal[2] - self.servo_height_compensation_m
                if not self._stable_height_ready(pose[2], expected):
                    self._fail("stable_height_mismatch"); return
                self.events.append({"event": "pose_stable", "t": now, "pose": pose.tolist(),
                    "wait_s": now - self._pose_wait_start, "position_span_m": span.tolist(),
                    "maximum_speed_m_s": max(speeds, default=math.inf),
                    "tracking_position_rmse_m": tracking_rmse,
                    "stable_height_goal_m": expected})
                self._grasp_pose = pose.copy()
                self._stable_ticks = self._ticks(self.config.readiness_stable_s) - 1
                self._observe_stage(obs, info, readiness)
            elif now - self._pose_wait_start >= self.config.max_pose_hold_s:
                self._fail("preclose_motion_stability_timeout")
        else:
            self._observe_stage(obs, info, readiness)
        if self.stage != receipt["stage"] or self.done:
            receipt.update(endpoint_pass=True, completed_step=step)

    def _capture_valid(self, obs):
        ee, nut = self._ee(obs), self._body(obs, "square_nut_v1")
        relative = quat_wxyz_to_matrix(ee[3:]).T @ (nut[:3] - ee[:3])
        inverse = ee[3:].copy(); inverse[1:] *= -1
        rotation = quat_multiply_wxyz(inverse, nut[3:])
        return (np.linalg.norm(relative - self._captured_position) <= self.config.capture_translation_slip_m
            and quat_angle_wxyz(rotation, self._captured_rotation) <= self.config.capture_rotation_slip_rad)

    def abort(self, reason="runtime_error"):
        self._runtime_error = str(reason)
        if not self._lifecycle.terminal:
            self._fail(str(reason))

    def _fail(self, reason):
        if not self._lifecycle.terminal:
            self._lifecycle.fail(str(reason), control_step=self._last_observed_step,
                simulation_time_s=self._last_observed_time_s)


__all__ = ["NutAssemblyOutcomeSolutionV1", "NutAssemblySolutionConfig", "OUTCOME_POLICY_ID"]


class ArmRampMemory:
    """Per-episode acknowledgement memory for the selected arm schedule."""
    def __init__(self, last_applied_arm=None):
        self.last_applied_arm = last_applied_arm


class NativeRateGripperServo(EqualRateGripperServo):
    version = "native-gripper-500hz-v1"
    def inner_gripper_step(self, state, feedback):
        if abs(self.controller.inner_physics_dt_s - 0.002) > 1e-12:
            raise ValueError("Native-rate gripper requires the accepted 2 ms physics clock")
        target, diagnostics = self._update(state, feedback)
        self._last_control_step, self._last_target = state.control_step, target
        self._last_diagnostics = dict(diagnostics)
        self.update_count += 1
        return target, {**diagnostics, "inner_update_performed": True,
            "inner_update_period_s": 0.002, "configured_inner_rate_hz": 500}


class ReferenceExecutionController:
    """Selected R3 arm hold plus native-rate gripper feedback coordinator."""
    def __init__(self, hold, control_dt):
        self.hold = hold
        self.inner = NativeRateGripperServo(hold.controller, 500, control_dt)
    def __getattr__(self, name): return getattr(self.hold, name)
    def compute(self, *args): return self.hold.compute(*args)
    def inner_gripper_step(self, *args): return self.inner.inner_gripper_step(*args)


class ReferenceArmSchedule:
    """The selected after-lift ramp is coordinated from public applied acks."""
    version = "linear-native-ramp-after-lift-v2-public-ack-memory"
    def __init__(self, solution, memory): self.solution, self.memory = solution, memory
    def begin(self, target):
        self.active = bool(self.solution._lift_released)
        if self.active and self.memory.last_applied_arm is None:
            raise ValueError("arm ramp requires a preceding public applied acknowledgement")
        self.initial = dict(self.memory.last_applied_arm or target.arm_servo_position)
    def target(self, target, index, count):
        if not self.active: return target
        fraction = (index + 1) / count
        arm = {k: self.initial[k] + fraction * (v - self.initial[k])
               for k, v in target.arm_servo_position.items()}
        return replace(target, arm_position=arm, arm_servo_position=arm)
    def applied(self, acknowledgement):
        self.memory.last_applied_arm = dict(acknowledgement.arm_servo_position)


__all__ += ["ArmRampMemory", "NativeRateGripperServo", "ReferenceArmSchedule",
            "ReferenceExecutionController"]
