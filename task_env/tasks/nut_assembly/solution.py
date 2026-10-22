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
from collections.abc import Mapping

import numpy as np

from ...controllers.canonical.contracts import digest
from ...controllers.canonical.execution import (
    ArmTargetExecutionRequestV1, BoundaryWait, PoseStabilityWindow,
)
from ...controllers.canonical.feedback import (
    CanonicalControlFeedback, CanonicalGripperFeedback,
    NativeControlFeedbackSampleV1,
)
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
class NutAssemblyNativeFeedbackSampleV1:
    """One measured pre-step feedback sample from the selected native interval."""

    schema_version: str
    provider: str
    provider_materialization_id: str
    task_artifact_hash: str
    source_id: str
    source_xml_sha256: str
    controller_identity: str
    solution_identity: str
    episode_id: str
    reset_sample_id: str
    evaluation_boundary_id: str
    evaluation_time_s: float
    control_step: int
    substep_index: int
    sample_sequence: int
    sample_time_s: float
    sample_duration_s: float
    sample_phase: str
    validity: str
    end_effector_pose: tuple[float, ...]
    feedback: CanonicalControlFeedback
    controller_diagnostics: Mapping[str, object]
    provider_feedback_sample: NativeControlFeedbackSampleV1
    target_hash: str
    applied_acknowledgement: Mapping[str, object]
    grasped_nut: bool | None = None

    def __post_init__(self):
        object.__setattr__(self, "end_effector_pose", tuple(float(v) for v in self.end_effector_pose))
        object.__setattr__(self, "controller_diagnostics", deepcopy(dict(self.controller_diagnostics)))
        object.__setattr__(self, "applied_acknowledgement", deepcopy(dict(self.applied_acknowledgement)))
        self.validate()

    def validate(self):
        if self.schema_version != "nutassembly-native-feedback-sample-v1":
            raise ValueError("unsupported NutAssembly native feedback sample")
        for name in ("provider", "provider_materialization_id", "source_id", "controller_identity", "solution_identity",
                     "episode_id", "reset_sample_id", "evaluation_boundary_id", "target_hash"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"native feedback sample requires {name}")
        for name in ("task_artifact_hash", "source_xml_sha256"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError(f"native feedback sample requires a SHA-256 {name}")
        if (type(self.control_step) is not int or self.control_step < 0
                or type(self.substep_index) is not int or not 0 <= self.substep_index < 5
                or type(self.sample_sequence) is not int or self.sample_sequence < 1):
            raise ValueError("native feedback sample position/sequence is invalid")
        if self.sample_phase not in {"reset_forward", "native_step_pre_integration"}:
            raise ValueError("native feedback sample phase is unsupported")
        if self.validity != "valid":
            raise ValueError("invalid native feedback cannot satisfy the required Guard sample contract")
        if (not all(math.isfinite(float(v)) for v in (
                self.evaluation_time_s, self.sample_time_s, self.sample_duration_s))
                or self.sample_duration_s != 0.002):
            raise ValueError("native feedback sample clock is non-finite or has the wrong period")
        if len(self.end_effector_pose) != 7 or not all(math.isfinite(v) for v in self.end_effector_pose):
            raise ValueError("native feedback sample requires a finite end-effector pose")
        if not 0.99 <= float(np.linalg.norm(self.end_effector_pose[3:])) <= 1.01:
            raise ValueError("native feedback sample quaternion is invalid")
        if not isinstance(self.feedback, CanonicalControlFeedback):
            raise TypeError("native feedback sample requires CanonicalControlFeedback")
        self.feedback.validate()
        if not isinstance(self.provider_feedback_sample, NativeControlFeedbackSampleV1):
            raise TypeError("native Guard sample requires the RuntimeSession force-sample receipt")
        self.provider_feedback_sample.validate()
        measurement = self.provider_feedback_sample.actuator_force_measurement
        mismatches = []
        for name, matches in (
            ("feedback_control_step", self.feedback.control_step == self.control_step),
            ("feedback_time", self.feedback.simulation_time == self.evaluation_time_s),
            ("canonical_feedback", self.provider_feedback_sample.feedback == self.feedback),
            ("provider", self.provider_feedback_sample.provider_name == self.provider),
            ("materialization", self.provider_feedback_sample.provider_materialization_id == self.provider_materialization_id),
            ("source", self.provider_feedback_sample.source_id == self.source_id),
            ("episode", self.provider_feedback_sample.episode_id == self.episode_id),
            ("reset", self.provider_feedback_sample.reset_sample_id == self.reset_sample_id),
            ("native_index", measurement.native_step_index == self.control_step * 5 + self.substep_index),
            ("sample_sequence", measurement.sample_sequence == self.sample_sequence),
            ("sample_time", measurement.native_sample_time_s == self.sample_time_s),
            ("evaluation_time", measurement.evaluation_simulation_time_s == self.evaluation_time_s),
            ("phase", measurement.phase == self.sample_phase),
            ("measurement_valid", measurement.valid),
            ("sample_validity", self.validity == "valid"),
        ):
            if not matches:
                mismatches.append(name)
        if mismatches:
            raise ValueError("native feedback sample is stale/mismatched: " + ", ".join(mismatches))
        expected_time = 0.0 if measurement.phase == "reset_forward" else (
            self.evaluation_time_s - self.sample_duration_s)
        if (measurement.phase == "reset_forward"
                and (self.control_step != 0 or self.substep_index != 0)):
            raise ValueError("reset-forward sample is only valid at the episode's initial native state")
        if abs(self.sample_time_s - expected_time) > 1e-10:
            raise ValueError("native force sample is stale beyond its documented pre-integration phase")
        diagnostics = self.controller_diagnostics
        rate_hz = diagnostics.get("configured_inner_rate_hz")
        update_performed = diagnostics.get("inner_update_performed")
        update_period_s = diagnostics.get("inner_update_period_s")
        expected_update = True if rate_hz == 500 else self.substep_index == 0
        expected_period_s = 0.002 if rate_hz == 500 else 0.01
        if (rate_hz not in (100, 500)
                or type(update_performed) is not bool
                or update_performed is not expected_update
                or update_period_s != expected_period_s):
            raise ValueError("native feedback sample does not match the declared 100/500 Hz gripper update cadence")
        measured_force = float(self.feedback.gripper.closing_force_N)
        if (not math.isfinite(measured_force)
                or diagnostics.get("closing_force_N") != measured_force
                or not math.isfinite(float(diagnostics.get("measured_opening_m", math.nan)))):
            raise ValueError("native feedback sample measurement and Controller input disagree")
        ack = self.applied_acknowledgement
        if ack.get("target_hash") != self.target_hash or ack.get("provider_name") != self.provider:
            raise ValueError("native feedback sample lacks a matching applied target acknowledgement")
        if self.grasped_nut is not None and type(self.grasped_nut) is not bool:
            raise ValueError("native guard task metric must be boolean when present")

    def to_mapping(self):
        self.validate()
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "provider_materialization_id": self.provider_materialization_id,
            "task_artifact_hash": self.task_artifact_hash,
            "source_id": self.source_id,
            "source_xml_sha256": self.source_xml_sha256,
            "controller_identity": self.controller_identity,
            "solution_identity": self.solution_identity,
            "episode_id": self.episode_id,
            "reset_sample_id": self.reset_sample_id,
            "evaluation_boundary_id": self.evaluation_boundary_id,
            "evaluation_time_s": self.evaluation_time_s,
            "control_step": self.control_step,
            "substep_index": self.substep_index,
            "sample_sequence": self.sample_sequence,
            "sample_time_s": self.sample_time_s,
            "sample_duration_s": self.sample_duration_s,
            "sample_phase": self.sample_phase,
            "validity": self.validity,
            "end_effector_pose": list(self.end_effector_pose),
            "feedback": self.feedback.to_mapping(),
            "controller_diagnostics": deepcopy(dict(self.controller_diagnostics)),
            "provider_feedback_sample": self.provider_feedback_sample.to_mapping(),
            "target_hash": self.target_hash,
            "applied_acknowledgement": deepcopy(dict(self.applied_acknowledgement)),
            "grasped_nut": self.grasped_nut,
        }

    @classmethod
    def from_mapping(cls, value):
        feedback_value = value["feedback"]
        gripper_value = feedback_value["gripper"]
        feedback = CanonicalControlFeedback(
            feedback_value["schema_version"], feedback_value["control_step"],
            feedback_value["simulation_time"], CanonicalGripperFeedback(
                gripper_value["semantic_id"], gripper_value["opening_m"],
                gripper_value["closing_force_N"],
            ),
        )
        return cls(
            value["schema_version"], value["provider"], value["provider_materialization_id"],
            value["task_artifact_hash"],
            value["source_id"], value["source_xml_sha256"], value["controller_identity"],
            value["solution_identity"], value["episode_id"], value["reset_sample_id"],
            value["evaluation_boundary_id"], value["evaluation_time_s"],
            value["control_step"], value["substep_index"], value["sample_sequence"],
            value["sample_time_s"], value["sample_duration_s"],
            value["sample_phase"], value["validity"],
            tuple(value["end_effector_pose"]), feedback, value["controller_diagnostics"],
            NativeControlFeedbackSampleV1.from_mapping(value["provider_feedback_sample"]),
            value["target_hash"], value["applied_acknowledgement"], value.get("grasped_nut"),
        )


@dataclass(frozen=True)
class NutAssemblyNativeIntervalReceiptV1:
    """Completed five-sample native interval and its source-bound boundary pair."""

    schema_version: str
    provider: str
    provider_materialization_id: str
    task_artifact_hash: str
    source_id: str
    source_xml_sha256: str
    controller_identity: str
    solution_identity: str
    episode_id: str
    reset_sample_id: str
    request_boundary: Mapping[str, object]
    evaluation_boundary: Mapping[str, object]
    physics_dt_s: float
    requested_substeps: int
    completed_substeps: int
    samples: tuple[NutAssemblyNativeFeedbackSampleV1, ...]

    def __post_init__(self):
        object.__setattr__(self, "request_boundary", deepcopy(dict(self.request_boundary)))
        object.__setattr__(self, "evaluation_boundary", deepcopy(dict(self.evaluation_boundary)))
        object.__setattr__(self, "samples", tuple(self.samples))
        self.validate()

    def validate(self):
        if self.schema_version != "nutassembly-native-interval-receipt-v1":
            raise ValueError("unsupported NutAssembly native interval receipt")
        if self.requested_substeps != 5 or self.completed_substeps != 5 or len(self.samples) != 5:
            raise ValueError("native interval is incomplete; five actual samples are required")
        if self.physics_dt_s != 0.002:
            raise ValueError("NutAssembly Guard requires the accepted 2 ms native clock")
        before, after = self.request_boundary, self.evaluation_boundary
        if (before.get("control_step", -2) + 1 != after.get("control_step", -1)
                or before.get("episode_id") != self.episode_id
                or after.get("episode_id") != self.episode_id
                or before.get("reset_sample_id") != self.reset_sample_id
                or after.get("reset_sample_id") != self.reset_sample_id
                or before.get("provider_materialization_id") != self.provider_materialization_id
                or after.get("provider_materialization_id") != self.provider_materialization_id
                or not before.get("identity_hash") or not after.get("identity_hash")):
            raise ValueError("native interval boundary identity or reset lineage changed")
        start_time = float(before["simulation_time_s"])
        end_time = float(after["simulation_time_s"])
        if abs((end_time - start_time) - 0.01) > 1e-10:
            raise ValueError("native interval did not complete one 10 ms control interval")
        identities = (self.provider, self.task_artifact_hash, self.source_id,
                      self.source_xml_sha256, self.controller_identity, self.solution_identity,
                      self.provider_materialization_id)
        configured_rates = {
            sample.controller_diagnostics.get("configured_inner_rate_hz")
            for sample in self.samples
        }
        if len(configured_rates) != 1 or next(iter(configured_rates)) not in (100, 500):
            raise ValueError("native interval gripper cadence is missing or changes within the interval")
        gripper_rate_hz = next(iter(configured_rates))
        if gripper_rate_hz == 100:
            first = self.samples[0]
            first_opening = first.controller_diagnostics.get("commanded_opening_m")
            first_applied_opening = float(
                first.applied_acknowledgement.get("gripper_servo_opening_m", math.nan)
            )
            if (not math.isfinite(float(first_opening))
                    or not math.isfinite(first_applied_opening)
                    or any(
                        abs(float(sample.controller_diagnostics.get(
                            "commanded_opening_m", math.nan)) - float(first_opening)) > 1e-12
                        or abs(float(sample.applied_acknowledgement.get(
                            "gripper_servo_opening_m", math.nan)) - first_applied_opening) > 1e-8
                        for sample in self.samples[1:]
                    )):
                raise ValueError("100 Hz gripper target was not held across the remaining four native substeps")
        last_sequence = None
        for index, sample in enumerate(self.samples):
            sample.validate()
            if (sample.substep_index != index
                    or sample.provider_feedback_sample.provider_materialization_id
                       != self.samples[0].provider_feedback_sample.provider_materialization_id
                    or abs(sample.evaluation_time_s - (start_time + index * self.physics_dt_s)) > 1e-10
                    or sample.evaluation_boundary_id != before["identity_hash"]
                    or sample.control_step != before["control_step"]
                    or sample.episode_id != self.episode_id
                    or sample.reset_sample_id != self.reset_sample_id
                    or (sample.provider, sample.task_artifact_hash, sample.source_id,
                        sample.source_xml_sha256, sample.controller_identity,
                        sample.solution_identity,
                        sample.provider_materialization_id) != identities):
                raise ValueError("native interval contains stale, unordered, or mismatched samples")
            if last_sequence is not None and sample.sample_sequence != last_sequence + 1:
                raise ValueError("native force sample sequence did not advance once per 2 ms substep")
            expected_sample_time = (start_time + index * self.physics_dt_s
                                    if sample.sample_phase == "reset_forward"
                                    else start_time + index * self.physics_dt_s - self.physics_dt_s)
            if abs(sample.sample_time_s - expected_sample_time) > 1e-10:
                raise ValueError("native force sample timestamp does not match its pre-integration phase")
            last_sequence = sample.sample_sequence

    def to_mapping(self):
        self.validate()
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "provider_materialization_id": self.provider_materialization_id,
            "task_artifact_hash": self.task_artifact_hash,
            "source_id": self.source_id,
            "source_xml_sha256": self.source_xml_sha256,
            "controller_identity": self.controller_identity,
            "solution_identity": self.solution_identity,
            "episode_id": self.episode_id,
            "reset_sample_id": self.reset_sample_id,
            "request_boundary": deepcopy(dict(self.request_boundary)),
            "evaluation_boundary": deepcopy(dict(self.evaluation_boundary)),
            "physics_dt_s": self.physics_dt_s,
            "requested_substeps": self.requested_substeps,
            "completed_substeps": self.completed_substeps,
            "samples": [sample.to_mapping() for sample in self.samples],
        }

    @classmethod
    def from_mapping(cls, value):
        return cls(
            value["schema_version"], value["provider"], value["provider_materialization_id"],
            value["task_artifact_hash"],
            value["source_id"], value["source_xml_sha256"], value["controller_identity"],
            value["solution_identity"], value["episode_id"], value["reset_sample_id"],
            value["request_boundary"], value["evaluation_boundary"], value["physics_dt_s"],
            value["requested_substeps"], value["completed_substeps"],
            tuple(NutAssemblyNativeFeedbackSampleV1.from_mapping(item) for item in value["samples"]),
        )


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

    def __init__(self, *, config=None, control_dt, physics_dt_s,
                 provider=None, task_artifact_hash=None, source_id=None,
                 source_closure_digest=None, source_xml_sha256=None,
                 base_controller_identity=None,
                 require_native_feedback_contract=False):
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
        self.provider = None if provider is None else str(provider)
        self.task_artifact_hash = task_artifact_hash
        self.source_id = source_id
        self.source_closure_digest = source_closure_digest
        self.source_xml_sha256 = source_xml_sha256
        self.base_controller_identity = base_controller_identity
        self.require_native_feedback_contract = bool(require_native_feedback_contract)
        if self.require_native_feedback_contract and not all((
                self.provider, self.task_artifact_hash, self.source_id,
                self.source_xml_sha256, self.base_controller_identity)):
            raise ValueError("native Solution requires actual provider/source/controller identity bindings")
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
                "postclose_hold": "controller_owned_last_applied_arm_target",
                "lift_release": "native_linear_ramp_from_last_applied_ack",
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
            "execution_binding": {
                "provider": self.provider,
                "task_artifact_hash": self.task_artifact_hash,
                "source_id": self.source_id,
                "source_closure_digest": self.source_closure_digest,
                "source_xml_sha256": self.source_xml_sha256,
                "base_controller_identity": self.base_controller_identity,
                "native_feedback_contract": self.require_native_feedback_contract,
            },
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
        self._pending_boundary = None
        self._episode_id = None
        self._reset_sample_id = None
        self._controller_identity = None
        self._provider_materialization_id = None
        self._task_success = False
        self._runtime_error = None
        self.events = []
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
            "close_authorization": deepcopy(self._close_authorization),
            "last_close_guard_decision": deepcopy(self._last_guard_decision),
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
            boundary = info.get("expert_execution_boundary_v1")
            if self.require_native_feedback_contract:
                if not isinstance(boundary, Mapping):
                    raise ValueError("native Solution reset requires the published execution boundary")
                if not boundary.get("provider_materialization_id"):
                    raise ValueError("native Solution reset requires the concrete RuntimeSession identity")
                expected = {
                    "task_artifact_hash": self.task_artifact_hash,
                    "source_id": self.source_id,
                    "source_closure_digest": self.source_closure_digest,
                    "source_xml_sha256": self.source_xml_sha256,
                    "provider_materialization_id": boundary.get("provider_materialization_id"),
                    "solution_identity": self.identity,
                }
                if any(boundary.get(key) != value for key, value in expected.items()):
                    raise ValueError("native Solution reset identity does not match the selected execution")
                self.provider = str(info.get("provider", self.provider))
                self._episode_id = str(boundary["episode_id"])
                self._reset_sample_id = str(boundary["reset_sample_id"])
                self._controller_identity = str(boundary["controller_identity"])
                self._provider_materialization_id = str(boundary["provider_materialization_id"])
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

    def act(self, obs=None, info=None):
        if self._pending_action is not None:
            self.abort("missing_execution_boundary")
        if self._emitted >= self._ticks(self.config.action_budget_s) and not self.failed:
            self._fail("canonical_solution_action_budget")
        if self.failed or self.done:
            raise RuntimeError("cannot act after outcome execution terminal")
        if self.stage == "verify_lift" and self._index >= self._postclose_hold_ticks and not self._lift_released:
            self._lift_released = True
            self.events.append({"event": "verify_lift_motion_start", "t": self._emitted * self.control_dt})
        planned = self._index < len(self._actions)
        hold = not planned
        action = self._actions[self._index] if planned else self._actions[-1]
        if self.stage == "verify_lift" and not self._lift_released:
            mode = "hold_last_applied"
        elif self._lift_released:
            mode = "ramp_from_last_applied"
        else:
            mode = "track"
        control_request = ArmTargetExecutionRequestV1(
            "arm-target-execution-request-v1", "nutassembly-r3-hold-ramp-v1", mode,
        )
        control_request.validate()
        if self.require_native_feedback_contract:
            boundary = None if info is None else info.get("expert_execution_boundary_v1")
            if not isinstance(boundary, Mapping):
                raise ValueError("native Solution action requires a current published execution boundary")
            if (boundary.get("episode_id") != self._episode_id
                    or boundary.get("reset_sample_id") != self._reset_sample_id
                    or boundary.get("controller_identity") != self._controller_identity
                    or boundary.get("control_step") != self._emitted):
                raise ValueError("native Solution action boundary is stale or belongs to another episode")
            self._pending_boundary = deepcopy(dict(boundary))
        proposal = ExpertAction(action=action.copy(), stage=self.stage,
            diagnostics={"version": self.version, "stage_index": self._stage_index,
                "stage_step": self._index, "readiness_hold": hold,
                "hold_seconds": self._hold_ticks * self.control_dt,
                "control_dt": self.control_dt,
                "completion_policy_id": OUTCOME_POLICY_ID,
                "readiness_warning_count": len(self._readiness_warnings)},
            control_request=control_request)
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
        """Compatibility helper for existing diagnostic workers.

        Selected Env execution uses ``_guard_mapping_from_native_sample`` on
        immutable, source-bound samples and never calls back into Solution from
        the RuntimeSession substep observer.
        """
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

    def _guard_mapping_from_native_sample(self, sample):
        sample.validate()
        if sample.grasped_nut is None:
            raise ValueError("close Guard requires the native sample's measured task predicate")
        ee = np.asarray(sample.end_effector_pose, dtype=float)
        pose_ready = (np.linalg.norm(ee[:3] - self._goal[:3]) <= self.config.pose_position_ready_m
            and quat_angle_wxyz(ee[3:], self._goal[3:]) <= self.config.pose_rotation_ready_rad)
        diagnostics = sample.controller_diagnostics
        force = float(sample.feedback.gripper.closing_force_N)
        active = bool(diagnostics["force_mode_active"])
        initialized = bool(diagnostics["force_mode_initialized"])
        controller_ready = bool(diagnostics["controller_close_ready"])
        grasped = sample.grasped_nut
        return {
            "sample_time_s": sample.sample_time_s,
            "sample_duration_s": sample.sample_duration_s,
            "conditions": {
                "controller_close_ready": controller_ready,
                "measured_force_at_least_threshold": force >= self.alternative_force_threshold_N,
                "force_mode_active": active,
                "force_mode_initialized": initialized,
                "grasped_nut": grasped,
                "pose_ready": pose_ready,
            },
            "values": {
                "control_step": sample.control_step,
                "native_sample_sequence": sample.sample_sequence,
                "native_substep_index": sample.substep_index,
                "provider_native_step_index": sample.provider_feedback_sample.actuator_force_measurement.native_step_index,
                "signed_actuator_force_N": sample.provider_feedback_sample.actuator_force_measurement.signed_force_N,
                "actuator_control_value": sample.provider_feedback_sample.actuator_force_measurement.actuator_ctrl,
                "force_unit": sample.provider_feedback_sample.actuator_force_measurement.force_unit,
                "sample_time_s": sample.sample_time_s,
                "evaluation_time_s": sample.evaluation_time_s,
                "sample_phase": sample.sample_phase,
                "episode_id": sample.episode_id,
                "reset_sample_id": sample.reset_sample_id,
                "provider_materialization_id": sample.provider_materialization_id,
                "evaluation_boundary_id": sample.evaluation_boundary_id,
                "closing_force_N": force,
                "force_mode_active": active,
                "force_mode_initialized": initialized,
                "controller_close_ready": controller_ready,
                "grasped_nut": grasped,
                "pose_ready": pose_ready,
                "finger_opening_m": float(sample.feedback.gripper.opening_m),
                "applied_target_hash": sample.applied_acknowledgement["target_hash"],
            },
        }

    def _validated_native_guard_samples(self, receipt, native_samples):
        if not isinstance(receipt, NutAssemblyNativeIntervalReceiptV1):
            raise ValueError("selected NutAssembly step requires a typed native interval receipt")
        receipt.validate()
        if self._pending_boundary is None:
            raise ValueError("native interval receipt has no matching pending action boundary")
        before = receipt.request_boundary
        if (before.get("identity_hash") != self._pending_boundary.get("identity_hash")
                or before != self._pending_boundary
                or receipt.episode_id != self._episode_id
                or receipt.reset_sample_id != self._reset_sample_id
                or receipt.provider != self.provider
                or receipt.task_artifact_hash != self.task_artifact_hash
                or receipt.source_id != self.source_id
                or receipt.source_xml_sha256 != self.source_xml_sha256
                or receipt.provider_materialization_id != self._provider_materialization_id
                or receipt.solution_identity != self.identity
                or receipt.controller_identity != self._controller_identity):
            raise ValueError("native feedback receipt is stale or belongs to another execution identity")
        if native_samples is None or tuple(native_samples) != receipt.samples:
            raise ValueError("native Solution observe requires every measured sample from the receipt")
        if self.stage == "close_gripper":
            return tuple(self._guard_mapping_from_native_sample(sample) for sample in receipt.samples)
        return ()

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
                transition_samples=None, native_interval_receipt=None,
                native_samples=None):
        if self.done or self.failed:
            raise RuntimeError("cannot observe terminal outcome execution")
        if self.require_native_feedback_contract:
            try:
                transition_samples = self._validated_native_guard_samples(
                    native_interval_receipt, native_samples,
                )
            except (ValueError, KeyError, TypeError):
                self._task_success = False
                self._fail("native_feedback_invalid")
                raise
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
        self._pending_boundary = None
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


class NativeRateGripperServo(EqualRateGripperServo):
    version = "native-gripper-500hz-v1"
    def reset(self):
        self.update_count = 0
        self._last_control_step = None
        self._last_target = None
        self._last_diagnostics = None

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
    """Existing Controller owner for the selected R3 arm and gripper execution."""
    def __init__(self, hold, control_dt, *, gripper_rate_hz=500):
        self.hold = hold
        if gripper_rate_hz == 500:
            self.inner = NativeRateGripperServo(hold.controller, 500, control_dt)
        elif gripper_rate_hz == 100:
            self.inner = EqualRateGripperServo(hold.controller, 100, control_dt)
        else:
            raise ValueError('NutAssembly R3 diagnostic gripper cadence must be 100 or 500 Hz')
        self.gripper_rate_hz = int(gripper_rate_hz)
    def __getattr__(self, name): return getattr(self.hold, name)
    def reset(self, state, feedback):
        self.inner.reset()
        return self.hold.reset(state, feedback)
    def compute(self, *args): return self.hold.compute(*args)
    def inner_gripper_step(self, *args): return self.inner.inner_gripper_step(*args)
    def validate_arm_execution_request(self, request): return self.hold.validate_execution_request(request)
    def request_arm_execution(self, request): self.hold.request_execution(request)
    def begin(self, target): self.hold.begin(target)
    def target(self, target, index, count): return self.hold.target(target, index, count)
    def applied(self, acknowledgement): self.hold.applied(acknowledgement)


__all__ += ["NativeRateGripperServo", "ReferenceExecutionController",
            "NutAssemblyNativeFeedbackSampleV1", "NutAssemblyNativeIntervalReceiptV1"]
