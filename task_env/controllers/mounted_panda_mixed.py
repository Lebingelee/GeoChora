"""Candidate controller contract for a source-bound mixed Panda interface.

This is an internal, provider-free controller implementation for the single
LIBERO MountedPanda source candidate. It is deliberately not exported from the
``task_env.controllers`` package root and does not admit a Provider route.
Seven arm slots are torque commands (N*m); two finger slots are independent
position commands (m). The public ``ControlCommand`` remains the existing
RuntimeBoundary value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from numbers import Real
import re
from typing import Any

import numpy as np
from gymnasium.spaces import Box

from ..environment.types import ActionModeSpec, ControlCommand, RuntimeSnapshot


_ARM_JOINTS = tuple(f"joint{i}" for i in range(1, 8))
_FINGER_JOINTS = ("finger_joint1", "finger_joint2")
_ARM_ACTUATORS = tuple(f"torq_j{i}" for i in range(1, 8))
_FINGER_ACTUATORS = (
    "gripper_finger_joint1",
    "gripper_finger_joint2",
)
_JOINT_LIMITS_RAD = np.asarray(
    [
        (-2.8973, 2.8973),
        (-1.7628, 1.7628),
        (-2.8973, 2.8973),
        (-3.0718, -0.0698),
        (-2.8973, 2.8973),
        (-0.0175, 3.7525),
        (-2.8973, 2.8973),
    ],
    dtype=np.float64,
)
_ACTUATOR_LIMITS = np.asarray(
    [(-80.0, 80.0)] * 5
    + [(-12.0, 12.0)] * 2
    + [(0.0, 0.04), (-0.04, 0.0)],
    dtype=np.float64,
)
_NAME_RE = re.compile(r"^[A-Za-z0-9_.:/-]+$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def _readonly_int_vector(value: Any, *, name: str, size: int) -> np.ndarray:
    raw = np.asarray(value)
    if raw.ndim != 1 or raw.shape != (size,) or raw.dtype.kind not in "iu":
        raise TypeError(f"{name} must be an integer vector of shape {(size,)}")
    result = raw.astype(np.int64, copy=True)
    if np.any(result < 0) or len(set(result.tolist())) != size:
        raise ValueError(f"{name} must contain unique non-negative indices")
    result.setflags(write=False)
    return result


def _readonly_float_matrix(value: Any, *, name: str, shape: tuple[int, int]) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64).copy()
    if result.shape != shape or not np.isfinite(result).all():
        raise ValueError(f"{name} must be finite with shape {shape}")
    if np.any(result[:, 0] > result[:, 1]):
        raise ValueError(f"{name} has an inverted range")
    result.setflags(write=False)
    return result


@dataclass(frozen=True)
class MountedPandaControlMapV1:
    """Name-resolved slot map derived from the existing TaskReferences owner."""

    source_id: str
    source_xml_sha256: str
    agent_uid: str
    joint_names: tuple[str, ...]
    actuator_names: tuple[str, ...]
    joint_qpos_ids: np.ndarray
    joint_dof_ids: np.ndarray
    actuator_ids: np.ndarray
    actuator_control_ranges: np.ndarray
    joint_position_ranges_rad: np.ndarray = field(
        default_factory=lambda: _JOINT_LIMITS_RAD.copy()
    )
    schema_version: str = "libero-mounted-panda-control-map-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "libero-mounted-panda-control-map-v1":
            raise ValueError("unsupported MountedPanda control map schema")
        if type(self.source_id) is not str or not self.source_id.strip():
            raise ValueError("control map requires a source identity")
        if type(self.source_xml_sha256) is not str or not _SHA_RE.fullmatch(self.source_xml_sha256):
            raise ValueError("control map source XML identity must be SHA-256")
        if type(self.agent_uid) is not str or not self.agent_uid.strip():
            raise ValueError("control map requires a resolved Agent identity")
        joints = tuple(str(value) for value in self.joint_names)
        actuators = tuple(str(value) for value in self.actuator_names)
        if len(joints) != 9 or len(actuators) != 9:
            raise ValueError("MountedPanda map requires seven arm and two finger names")
        if len(set(joints)) != 9 or len(set(actuators)) != 9:
            raise ValueError("MountedPanda map names must be unique")
        if any(not _NAME_RE.fullmatch(value) for value in (*joints, *actuators)):
            raise ValueError("MountedPanda map names contain invalid characters")
        joint_prefix = joints[0][: -len("joint1")]
        actuator_prefix = actuators[0][: -len("torq_j1")]
        expected_joints = tuple(joint_prefix + name for name in (*_ARM_JOINTS, *_FINGER_JOINTS))
        expected_actuators = tuple(
            actuator_prefix + name for name in (*_ARM_ACTUATORS, *_FINGER_ACTUATORS)
        )
        if joints != expected_joints or actuators != expected_actuators:
            raise ValueError("MountedPanda source joint/actuator ordering or common prefix is invalid")
        object.__setattr__(self, "joint_names", joints)
        object.__setattr__(self, "actuator_names", actuators)
        object.__setattr__(self, "joint_qpos_ids", _readonly_int_vector(
            self.joint_qpos_ids, name="joint_qpos_ids", size=9
        ))
        object.__setattr__(self, "joint_dof_ids", _readonly_int_vector(
            self.joint_dof_ids, name="joint_dof_ids", size=9
        ))
        actuator_ids = np.asarray(self.actuator_ids)
        if actuator_ids.ndim != 1 or actuator_ids.dtype.kind not in "iu":
            raise TypeError("actuator_ids must be a one-dimensional integer vector")
        actuator_ids = actuator_ids.astype(np.int64, copy=True)
        if actuator_ids.shape != (9,) or np.any(actuator_ids < 0) or len(set(actuator_ids.tolist())) != 9:
            raise ValueError("actuator_ids must map the nine source actuators uniquely")
        actuator_ids.setflags(write=False)
        object.__setattr__(self, "actuator_ids", actuator_ids)
        ranges = np.asarray(self.actuator_control_ranges, dtype=np.float64)
        if ranges.ndim != 2 or ranges.shape[1] != 2 or not np.isfinite(ranges).all():
            raise ValueError("actuator_control_ranges must have shape (nu, 2) and be finite")
        if np.any(ranges[:, 0] > ranges[:, 1]) or int(np.max(actuator_ids)) >= len(ranges):
            raise ValueError("actuator ranges do not cover the resolved source slots")
        for index, (slot, expected) in enumerate(
            zip(actuator_ids, _ACTUATOR_LIMITS, strict=True)
        ):
            if not np.allclose(ranges[slot], expected, rtol=0.0, atol=1.0e-7):
                raise ValueError(f"source actuator range differs from pinned XML: {actuators[index]}")
        ranges = ranges.copy()
        ranges.setflags(write=False)
        object.__setattr__(self, "actuator_control_ranges", ranges)
        joint_ranges = _readonly_float_matrix(
            self.joint_position_ranges_rad,
            name="joint_position_ranges_rad",
            shape=(7, 2),
        )
        if not np.allclose(joint_ranges, _JOINT_LIMITS_RAD, rtol=0.0, atol=1.0e-7):
            raise ValueError("joint position ranges differ from the pinned Panda XML")
        object.__setattr__(self, "joint_position_ranges_rad", joint_ranges)

    @classmethod
    def from_task_references(
        cls,
        references: Any,
        *,
        agent_uid: str,
        source_id: str,
        source_xml_sha256: str,
    ) -> "MountedPandaControlMapV1":
        """Resolve source names through ``resolve_task_references`` output.

        The generic reference owner remains responsible for all compiled IDs;
        this task-bound projection only verifies the exact ordered LIBERO slots.
        """

        agents = getattr(references, "agents", None)
        names = getattr(references, "names", None)
        if not isinstance(agents, dict) and not hasattr(agents, "get"):
            raise TypeError("MountedPanda mapping requires TaskReferences")
        if names is None:
            raise TypeError("MountedPanda mapping requires SceneNameTable")
        try:
            agent = agents[agent_uid]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"resolved Agent is missing: {agent_uid}") from exc
        expected_joint_suffixes = (*_ARM_JOINTS, *_FINGER_JOINTS)
        expected_actuator_suffixes = (*_ARM_ACTUATORS, *_FINGER_ACTUATORS)
        joint_names = tuple(agent.joint_names)
        actuator_names = tuple(agent.actuator_names)
        if len(joint_names) != 9 or len(actuator_names) != 9:
            raise ValueError("resolved Agent must expose all nine ordered MountedPanda resources")
        joint_prefix = joint_names[0][: -len("joint1")]
        actuator_prefix = actuator_names[0][: -len("torq_j1")]
        if joint_names != tuple(joint_prefix + value for value in expected_joint_suffixes):
            raise ValueError("resolved joint name order differs from the pinned MountedPanda source")
        if actuator_names != tuple(actuator_prefix + value for value in expected_actuator_suffixes):
            raise ValueError("resolved actuator name order differs from the pinned MountedPanda source")
        try:
            mapped_joint_ids = tuple(int(names.joints[name]) for name in joint_names)
            mapped_actuator_ids = tuple(int(names.actuators[name]) for name in actuator_names)
        except KeyError as exc:
            raise ValueError(f"compiled source reference is missing: {exc.args[0]}") from exc
        if tuple(int(value) for value in agent.arm_joint_ids) != mapped_joint_ids:
            raise ValueError("Agent joint IDs disagree with the compiled SceneNameTable")
        if tuple(int(value) for value in agent.arm_actuator_ids) != mapped_actuator_ids:
            raise ValueError("Agent actuator IDs disagree with the compiled SceneNameTable")
        return cls(
            source_id=source_id,
            source_xml_sha256=source_xml_sha256,
            agent_uid=agent_uid,
            joint_names=joint_names,
            actuator_names=actuator_names,
            joint_qpos_ids=agent.arm_qpos_ids,
            joint_dof_ids=agent.arm_dof_ids,
            actuator_ids=mapped_actuator_ids,
            actuator_control_ranges=agent.ctrl_range,
        )

    @property
    def identity_hash(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "source_xml_sha256": self.source_xml_sha256,
            "agent_uid": self.agent_uid,
            "joint_names": self.joint_names,
            "actuator_names": self.actuator_names,
            "joint_qpos_ids": self.joint_qpos_ids.tolist(),
            "joint_dof_ids": self.joint_dof_ids.tolist(),
            "actuator_ids": self.actuator_ids.tolist(),
            "actuator_control_ranges": self.actuator_control_ranges.tolist(),
            "joint_position_ranges_rad": self.joint_position_ranges_rad.tolist(),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()


@dataclass(frozen=True)
class MountedPandaServoConfigV1:
    """Explicit, unqualified candidate gains and source timebase."""

    kp_Nm_per_rad: tuple[float, ...]
    kd_Nm_s_per_rad: tuple[float, ...]
    control_period_s: float = 0.05
    physics_dt_s: float = 0.002
    gain_status: str = "synthetic_s1_fixture"
    schema_version: str = "libero-mounted-panda-servo-config-v1"

    def __post_init__(self) -> None:
        if self.schema_version != "libero-mounted-panda-servo-config-v1":
            raise ValueError("unsupported MountedPanda servo config")
        if self.gain_status not in {"synthetic_s1_fixture", "candidate_unqualified"}:
            raise ValueError("servo gains must remain explicitly unqualified")
        for name in ("kp_Nm_per_rad", "kd_Nm_s_per_rad"):
            raw_values = tuple(getattr(self, name))
            if any(isinstance(value, (bool, np.bool_)) or not isinstance(value, Real)
                   for value in raw_values):
                raise TypeError(f"{name} values must be real numbers, not bools or strings")
            values = tuple(float(value) for value in raw_values)
            if len(values) != 7 or any(not math.isfinite(value) or value < 0 for value in values):
                raise ValueError(f"{name} must contain seven finite non-negative values")
            object.__setattr__(self, name, values)
        for name in ("control_period_s", "physics_dt_s"):
            raw = getattr(self, name)
            if isinstance(raw, (bool, np.bool_)) or not isinstance(raw, Real):
                raise TypeError(f"{name} must be a real number")
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
            object.__setattr__(self, name, value)
        repeats = self.control_period_s / self.physics_dt_s
        if (not math.isclose(repeats, round(repeats), rel_tol=0.0, abs_tol=1.0e-10)
                or round(repeats) != 25 or not math.isclose(self.control_period_s, 0.05, abs_tol=1.0e-12)):
            raise ValueError("candidate preserves the pinned 20 Hz / 2 ms × 25 source timebase")


class MountedPandaMixedActuatorAdapter:
    """Source-bound seven-joint PD torque plus signed two-finger position map.

    Gains are mandatory; the adapter provides no physically qualified default.
    Torque beyond source limits fails before a RuntimeBoundary consumes a step.
    """

    def __init__(self, *, mapping: MountedPandaControlMapV1, config: MountedPandaServoConfigV1) -> None:
        if not isinstance(mapping, MountedPandaControlMapV1):
            raise TypeError("MountedPanda adapter requires MountedPandaControlMapV1")
        if not isinstance(config, MountedPandaServoConfigV1):
            raise TypeError("MountedPanda adapter requires explicit MountedPandaServoConfigV1")
        self.mapping = mapping
        self.config = config
        low = np.concatenate((mapping.joint_position_ranges_rad[:, 0], np.asarray([0.0])))
        high = np.concatenate((mapping.joint_position_ranges_rad[:, 1], np.asarray([0.08])))
        self._action_space = Box(low=low.astype(np.float32), high=high.astype(np.float32), dtype=np.float32)

    @property
    def action_space(self) -> Box:
        return self._action_space

    @property
    def action_contract(self) -> ActionModeSpec:
        """Return the typed Core action schema expected by ``BaseTaskEnv``."""
        low = tuple(float(value) for value in self.mapping.joint_position_ranges_rad[:, 0]) + (0.0,)
        high = tuple(float(value) for value in self.mapping.joint_position_ranges_rad[:, 1]) + (0.08,)
        return ActionModeSpec(
            schema_id="libero.mounted_panda_mixed_action.v1",
            schema_version="task-env-action-v2",
            controller_kind="absolute_joint",
            reference=None,
            rotation_representation=None,
            components=(*self.mapping.joint_names[:7], "opening_m"),
            low=low,
            high=high,
            joint_order=self.mapping.joint_names[:7],
            gripper_convention="physical_opening_m",
            backend_provenance="unqualified_mounted_panda_pd_torque_position_candidate",
        )

    @property
    def action_profile(self) -> dict[str, Any]:
        """Detailed candidate wiring separate from the Core action schema."""
        return {
            "schema_version": "libero-mounted-panda-mixed-control-profile-v1",
            "source_id": self.mapping.source_id,
            "composed_mjcf_sha256": self.mapping.source_xml_sha256,
            "mapping_identity_sha256": self.mapping.identity_hash,
            "arm_actuators": {"names": list(self.mapping.actuator_names[:7]), "unit": "N*m", "law": "explicit_pd_candidate"},
            "finger_actuators": {"names": list(self.mapping.actuator_names[7:]), "unit": "m", "mapping": ["opening_m/2", "-opening_m/2"]},
            "timebase": {"control_period_s": self.config.control_period_s, "physics_dt_s": self.config.physics_dt_s, "substeps": 25},
            "gain_status": self.config.gain_status,
            "provider_admission": "NOT_ADMITTED",
        }

    def reset(self, snapshot: RuntimeSnapshot) -> None:
        self._validate_snapshot(snapshot)

    def _validate_snapshot(self, snapshot: RuntimeSnapshot) -> None:
        if not isinstance(snapshot, RuntimeSnapshot):
            raise TypeError("MountedPanda controller requires RuntimeSnapshot")
        if snapshot.ctrl is None:
            raise ValueError("MountedPanda controller requires public ctrl state")
        if np.asarray(snapshot.ctrl).shape != (self.mapping.actuator_control_ranges.shape[0],):
            raise ValueError("RuntimeSnapshot ctrl width differs from the resolved source model")
        if np.asarray(snapshot.qpos).ndim != 1 or int(np.max(self.mapping.joint_qpos_ids)) >= len(snapshot.qpos):
            raise ValueError("RuntimeSnapshot qpos does not cover the resolved source joints")
        if snapshot.qvel is None or np.asarray(snapshot.qvel).ndim != 1 or int(np.max(self.mapping.joint_dof_ids)) >= len(snapshot.qvel):
            raise ValueError("RuntimeSnapshot qvel does not cover the resolved source DOFs")
        for name in ("ctrl", "qpos", "qvel"):
            value = getattr(snapshot, name)
            if not np.isfinite(np.asarray(value)).all():
                raise ValueError(f"RuntimeSnapshot {name} must be finite")

    def convert(self, action: np.ndarray, snapshot: RuntimeSnapshot) -> ControlCommand:
        self._validate_snapshot(snapshot)
        raw = np.asarray(action)
        if raw.dtype.kind not in "fiu" or raw.ndim != 1 or raw.shape != (8,):
            raise TypeError("MountedPanda action must be a numeric vector [7 joint targets, opening_m]")
        requested = raw.astype(np.float64, copy=True)
        if not np.isfinite(requested).all():
            raise ValueError("MountedPanda action must be finite")
        target = requested[:7]
        opening_m = float(requested[7])
        if np.any(target < self.mapping.joint_position_ranges_rad[:, 0]) or np.any(target > self.mapping.joint_position_ranges_rad[:, 1]):
            raise ValueError("joint target exceeds the pinned source joint range")
        if not 0.0 <= opening_m <= 0.08:
            raise ValueError("opening_m must be in [0, 0.08]")

        current_q = np.asarray(snapshot.qpos, dtype=np.float64)[self.mapping.joint_qpos_ids[:7]]
        current_dq = np.asarray(snapshot.qvel, dtype=np.float64)[self.mapping.joint_dof_ids[:7]]
        torque_requested = (
            np.asarray(self.config.kp_Nm_per_rad) * (target - current_q)
            - np.asarray(self.config.kd_Nm_s_per_rad) * current_dq
        )
        if not np.isfinite(torque_requested).all():
            raise ValueError("candidate torque calculation is non-finite")
        actuator_ids = self.mapping.actuator_ids
        arm_ranges = self.mapping.actuator_control_ranges[actuator_ids[:7]]
        torque = np.clip(torque_requested, arm_ranges[:, 0], arm_ranges[:, 1])
        torque_clipped = not np.array_equal(torque, torque_requested)
        finger_targets = np.asarray([opening_m / 2.0, -opening_m / 2.0], dtype=np.float64)
        finger_ranges = self.mapping.actuator_control_ranges[actuator_ids[7:]]
        if np.any(finger_targets < finger_ranges[:, 0]) or np.any(finger_targets > finger_ranges[:, 1]):
            raise ValueError("signed finger targets exceed the pinned source position ranges")

        ctrl = np.asarray(snapshot.ctrl, dtype=np.float64).copy()
        ctrl[actuator_ids[:7]] = torque
        ctrl[actuator_ids[7:]] = finger_targets
        if not np.isfinite(ctrl).all():
            raise ValueError("compiled mixed actuator command is not finite")
        interpreted = requested.copy()
        return ControlCommand(
            actuator_ctrl=ctrl,
            external_action=interpreted,
            requested_action=requested,
            controller_target=ctrl,
            universal_action=interpreted,
            mode="libero_mounted_panda_mixed_torque_position_v1",
            action_clipped=torque_clipped,
        )


__all__ = [
    "MountedPandaControlMapV1",
    "MountedPandaMixedActuatorAdapter",
    "MountedPandaServoConfigV1",
]
