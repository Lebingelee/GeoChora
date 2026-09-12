"""Real-asset Unitree Go2 description and policy-action adapter.

This module preserves the robot binding used for the real-asset variant.  It
is intentionally not imported by the public ``go2-v1`` registry entry; the
canonical menagerie XML binding lives in the sibling :mod:`go2` module.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from gymnasium.spaces import Box

from ...utils._paths import MUJOCO_MENAGERIE_ROOT
from ...environment import (
    AssetManifest,
    ControlCommand,
    EpisodePhysicsState,
    ExternalActionContract,
    InitialStateSpec,
    ReferenceSpec,
    RuntimeSnapshot,
    StageUnavailableError,
)
from ..base import BaseAgent


GO2_ASSET_ROOT = MUJOCO_MENAGERIE_ROOT / "unitree_go2"
GO2_MJCF_PATH = GO2_ASSET_ROOT / "go2.xml"
GO2_BASE_BODY_NAME = "base_link"

GO2_JOINT_NAMES = (
    "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint",
    "FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
    "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint",
    "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint",
)
GO2_ACTUATOR_NAMES = (
    "FL_hip", "FL_thigh", "FL_calf",
    "FR_hip", "FR_thigh", "FR_calf",
    "RL_hip", "RL_thigh", "RL_calf",
    "RR_hip", "RR_thigh", "RR_calf",
)
GO2_BODY_NAMES = (
    GO2_BASE_BODY_NAME,
    "FL_hip", "FL_thigh", "FL_calf",
    "FR_hip", "FR_thigh", "FR_calf",
    "RL_hip", "RL_thigh", "RL_calf",
    "RR_hip", "RR_thigh", "RR_calf",
)
GO2_SITE_NAMES = ("imu",)
GO2_FOOT_GEOM_NAMES = ("FL", "FR", "RL", "RR")

GO2_DEFAULT_JOINT_ANGLES = np.asarray(
    # Genesis' Go2 reference reset pose: zero hips, front thighs at .8,
    # rear thighs at 1.0, and all calves at -1.5 rad.
    (0.0, 0.8, -1.5, 0.0, 0.8, -1.5,
     0.0, 1.0, -1.5, 0.0, 1.0, -1.5),
    dtype=np.float32,
)
GO2_ACTION_SCALE = 0.25
GO2_ACTION_CLIP = 100.0
GO2_KP = 20.0
GO2_KD = 0.5

GO2_ACTION_CONTRACT = ExternalActionContract(
    mode="go2_position_target",
    dimension=12,
    components=GO2_ACTUATOR_NAMES,
    # unitree_rl_gym's normalization.clip_actions is 100.  The public Go2
    # task action therefore uses the native position-target command range;
    # other tasks retain their own action spaces and contracts.
    low=-GO2_ACTION_CLIP,
    high=GO2_ACTION_CLIP,
    controller_backend="go2_pd_position_target",
    actuator_control_mode="torque",
    schema_id="task-env.go2.position-target.v2",
    schema_version="task-env-action-v1",
    unit="native_position_target_delta",
    actuator_interpretation=(
        "clip(action,[-100,100]); apply one-policy-tick delayed target="
        "default_joint_angle+0.25*action; kp=20,kd=0.5"
    ),
    task_family="go2_walk",
)


@dataclass(frozen=True)
class Go2Entity:
    uid: str = "go2-v1"
    base_body_name: str = GO2_BASE_BODY_NAME
    imu_site_name: str = "imu"


class Go2Agent(BaseAgent):
    uid = "go2-v1"

    def asset_manifest(self) -> AssetManifest:
        return AssetManifest(
            owner_uid=self.uid,
            asset_kind="agent_mjcf",
            mjcf_sources=(GO2_MJCF_PATH,),
            asset_roots=(GO2_ASSET_ROOT,),
            asset_version="mujoco-menagerie-unitree-go2",
        )

    def reference_spec(self) -> ReferenceSpec:
        return ReferenceSpec(
            body_names=GO2_BODY_NAMES,
            joint_names=GO2_JOINT_NAMES,
            site_names=GO2_SITE_NAMES,
            geom_names=GO2_FOOT_GEOM_NAMES,
            actuator_names=GO2_ACTUATOR_NAMES,
        )

    def reference_layout(self) -> Mapping[str, str]:
        return {"base_body_name": GO2_BASE_BODY_NAME, "eef_site_name": "imu"}

    def initial_state_spec(self) -> InitialStateSpec:
        return InitialStateSpec(
            joint_positions=tuple(
                (name, float(value))
                for name, value in zip(GO2_JOINT_NAMES, GO2_DEFAULT_JOINT_ANGLES, strict=True)
            ),
            notes=(
                "Go2 policy uses Genesis' unitree_rl_gym 12-DOF ordering and zero action target.",
                "Go2WalkResetSampler applies the fixed Genesis pose and zero generalized velocity.",
            ),
        )

    def supported_controller_kinds(self) -> tuple[str, ...]:
        # Go2 is a task-native policy actuator, not a Panda-style public robot
        # controller.  The task binds GO2ActionAdapter after compilation.
        return ()


class Go2ActionAdapter:
    """Apply the delayed native 12-DOF position-target PD law."""

    action_contract = GO2_ACTION_CONTRACT

    def __init__(
        self,
        *,
        joint_qpos_ids: np.ndarray,
        joint_dof_ids: np.ndarray,
        actuator_ids: np.ndarray,
        ctrl_range: np.ndarray,
    ) -> None:
        self._qpos_ids = np.asarray(joint_qpos_ids, dtype=np.int32).reshape(-1)
        self._dof_ids = np.asarray(joint_dof_ids, dtype=np.int32).reshape(-1)
        self._actuator_ids = np.asarray(actuator_ids, dtype=np.int32).reshape(-1)
        if not (
            self._qpos_ids.size == self._dof_ids.size == self._actuator_ids.size == 12
        ):
            raise ValueError("Go2 action adapter requires exactly 12 joints and actuators")
        self._ctrl_range = np.asarray(ctrl_range, dtype=np.float32)
        if self._ctrl_range.ndim != 2 or self._ctrl_range.shape[1] != 2:
            raise ValueError("Go2 ctrl_range must have shape (n_actuators, 2)")
        self._device_constant_cache: dict[tuple[str, object], tuple[object, ...]] = {}
        self._delayed_action: np.ndarray | None = None
        self._delayed_action_batch: np.ndarray | None = None
        self._delayed_action_device: dict[tuple[str, object], object] = {}
        self.action_space = Box(
            low=np.full(12, -GO2_ACTION_CLIP, dtype=np.float32),
            high=np.full(12, GO2_ACTION_CLIP, dtype=np.float32),
            dtype=np.float32,
        )

    def reset(self, snapshot: RuntimeSnapshot) -> None:
        self._delayed_action = self._hold_action(np.asarray(snapshot.qpos, dtype=np.float32))

    def reset_batch(self, state, reset_mask=None) -> None:
        """Seed selected delay rows with zero-error hold targets after reset."""

        qpos = np.asarray(state.qpos, dtype=np.float32)
        if qpos.ndim != 2 or qpos.shape[0] != int(state.batch_size):
            raise ValueError("Go2 batch reset state must expose qpos with shape (B, nq)")
        hold = self._hold_action(qpos)
        if self._delayed_action_batch is None or self._delayed_action_batch.shape != hold.shape:
            self._delayed_action_batch = hold
            return
        if reset_mask is None:
            self._delayed_action_batch[...] = hold
            return
        mask = np.asarray(reset_mask, dtype=np.bool_)
        if mask.shape != (int(state.batch_size),):
            raise ValueError("Go2 batch reset mask must have shape (B,)")
        self._delayed_action_batch[mask] = hold[mask]

    def reset_device_batch(self, state, reset_mask) -> None:
        """Reset selected device delay rows to their current joint pose."""

        import torch

        qpos = state.arrays["qpos"]
        mask = reset_mask if torch.is_tensor(reset_mask) else torch.as_tensor(
            reset_mask, dtype=torch.bool, device=qpos.device
        )
        mask = mask.to(device=qpos.device, dtype=torch.bool)
        key = (str(qpos.device), qpos.dtype)
        hold = self._hold_action_device(qpos)
        delayed = self._delayed_action_device.get(key)
        if delayed is None or tuple(delayed.shape) != tuple(hold.shape):
            delayed = hold.clone()
            self._delayed_action_device[key] = delayed
        else:
            delayed[mask] = hold[mask]

    def _hold_action(self, qpos: np.ndarray) -> np.ndarray:
        dof_pos = np.asarray(qpos, dtype=np.float32)[..., self._qpos_ids]
        return np.clip(
            (dof_pos - GO2_DEFAULT_JOINT_ANGLES) / np.float32(GO2_ACTION_SCALE),
            -GO2_ACTION_CLIP,
            GO2_ACTION_CLIP,
        ).astype(np.float32, copy=False)

    def _hold_action_device(self, qpos):
        import torch

        key = (str(qpos.device), qpos.dtype)
        constants = self._device_constant_cache.get(key)
        if constants is None:
            default = torch.as_tensor(GO2_DEFAULT_JOINT_ANGLES, dtype=qpos.dtype, device=qpos.device)
            scale = torch.as_tensor(GO2_ACTION_SCALE, dtype=qpos.dtype, device=qpos.device)
        else:
            default, scale = constants[3], constants[6]
        qpos_ids = torch.tensor(self._qpos_ids, dtype=torch.long, device=qpos.device)
        return torch.clamp(
            (qpos.index_select(-1, qpos_ids) - default) / scale,
            -GO2_ACTION_CLIP,
            GO2_ACTION_CLIP,
        )

    def _validate(self, action: np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
        value = np.asarray(action, dtype=np.float32)
        if value.shape != shape:
            raise ValueError(f"Go2 action must have shape {shape}, got {value.shape}")
        if not np.isfinite(value).all() or np.any(value < -GO2_ACTION_CLIP) or np.any(value > GO2_ACTION_CLIP):
            raise ValueError("Go2 native action must be finite and lie in [-100, 100]")
        return value

    def _torque(self, action: np.ndarray, qpos: np.ndarray, qvel: np.ndarray) -> np.ndarray:
        dof_pos = np.asarray(qpos, dtype=np.float32)[..., self._qpos_ids]
        dof_vel = np.asarray(qvel, dtype=np.float32)[..., self._dof_ids]
        target = GO2_DEFAULT_JOINT_ANGLES + GO2_ACTION_SCALE * action
        torque = GO2_KP * (target - dof_pos) - GO2_KD * dof_vel
        low = self._ctrl_range[self._actuator_ids, 0]
        high = self._ctrl_range[self._actuator_ids, 1]
        return np.clip(torque, low, high).astype(np.float32, copy=False)

    def convert(self, action: np.ndarray, snapshot: RuntimeSnapshot) -> ControlCommand:
        value = self._validate(action, (12,))
        if self._delayed_action is None:
            self._delayed_action = self._hold_action(snapshot.qpos)
        delayed = self._delayed_action.copy()
        torque = self._torque(delayed, snapshot.qpos, snapshot.qvel)
        self._delayed_action = value.copy()
        ctrl = (
            np.zeros(self._ctrl_range.shape[0], dtype=np.float32)
            if snapshot.ctrl is None
            else np.asarray(snapshot.ctrl, dtype=np.float32).copy()
        )
        ctrl[self._actuator_ids] = torque
        return ControlCommand(
            actuator_ctrl=ctrl,
            external_action=value.copy(),
            requested_action=value.copy(),
            controller_target=GO2_DEFAULT_JOINT_ANGLES + GO2_ACTION_SCALE * delayed,
            universal_action=torque.copy(),
            mode="go2_position_target_pd",
        )

    def convert_batch(self, action: np.ndarray, state) -> np.ndarray:
        value = self._validate(action, (int(state.batch_size), 12))
        expected = (int(state.batch_size), 12)
        if self._delayed_action_batch is None or self._delayed_action_batch.shape != expected:
            self._delayed_action_batch = self._hold_action(state.qpos)
        delayed = self._delayed_action_batch.copy()
        torque = self._torque(delayed, state.qpos, state.qvel)
        self._delayed_action_batch = value.copy()
        control = np.zeros((int(state.batch_size), self._ctrl_range.shape[0]), dtype=np.float32)
        control[:, self._actuator_ids] = torque
        return control

    def convert_device_batch(self, action, state):
        """Device-native counterpart of :meth:`convert_batch`.

        The public device bridge passes a ``DeviceBatchState`` rather than a
        NumPy ``TaskStateView``.  This method deliberately performs no host
        conversion; index/limit constants are materialized on the action's
        device and the returned actuator control retains that device.
        """

        import torch

        if not hasattr(action, "shape") or tuple(action.shape) != (int(state.num_envs), 12):
            raise ValueError(
                f"Go2 device action must have shape ({int(state.num_envs)}, 12)"
            )
        if not torch.isfinite(action).all() or torch.any(action < -GO2_ACTION_CLIP) or torch.any(action > GO2_ACTION_CLIP):
            raise ValueError("Go2 native device action must be finite and lie in [-100, 100]")
        qpos = state.arrays["qpos"]
        qvel = state.arrays["qvel"]
        device = action.device
        if str(getattr(qpos, "device", "")) != str(device) or str(getattr(qvel, "device", "")) != str(device):
            raise StageUnavailableError(
                "Go2 device action/state tensors must share a device; "
                "use an explicit sim/rl transfer mode instead of an implicit copy"
            )
        cache_key = (str(device), action.dtype)
        constants = self._device_constant_cache.get(cache_key)
        if constants is None:
            constants = (
                torch.tensor(self._qpos_ids, dtype=torch.long, device=device),
                torch.tensor(self._dof_ids, dtype=torch.long, device=device),
                torch.tensor(self._actuator_ids, dtype=torch.long, device=device),
                torch.as_tensor(
                    GO2_DEFAULT_JOINT_ANGLES,
                    dtype=action.dtype,
                    device=device,
                ),
                torch.as_tensor(GO2_KP, dtype=action.dtype, device=device),
                torch.as_tensor(GO2_KD, dtype=action.dtype, device=device),
                torch.as_tensor(GO2_ACTION_SCALE, dtype=action.dtype, device=device),
                torch.as_tensor(
                    self._ctrl_range[self._actuator_ids],
                    dtype=action.dtype,
                    device=device,
                ),
            )
            self._device_constant_cache[cache_key] = constants
        qpos_ids, dof_ids, actuator_ids, default, kp, kd, scale, limits = constants
        key = (str(device), action.dtype)
        delayed = self._delayed_action_device.get(key)
        if delayed is None or tuple(delayed.shape) != tuple(action.shape):
            delayed = self._hold_action_device(qpos)
            self._delayed_action_device[key] = delayed.clone()
        target = default + scale * delayed
        torque = kp * (target - qpos.index_select(-1, qpos_ids)) - kd * qvel.index_select(-1, dof_ids)
        torque = torch.clamp(torque, limits[:, 0], limits[:, 1])
        control = state.arrays["ctrl"].clone()
        control[:, actuator_ids] = torque
        self._delayed_action_device[key].copy_(action.detach())
        return control


__all__ = [
    "GO2_ACTION_CONTRACT",
    "GO2_ACTION_CLIP",
    "GO2_ACTION_SCALE",
    "GO2_ACTUATOR_NAMES",
    "GO2_ASSET_ROOT",
    "GO2_BASE_BODY_NAME",
    "GO2_BODY_NAMES",
    "GO2_DEFAULT_JOINT_ANGLES",
    "GO2_FOOT_GEOM_NAMES",
    "GO2_JOINT_NAMES",
    "GO2_KD",
    "GO2_KP",
    "GO2_MJCF_PATH",
    "Go2ActionAdapter",
    "Go2Agent",
    "Go2Entity",
]
