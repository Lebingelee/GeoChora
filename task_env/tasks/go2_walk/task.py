"""Unitree Go2 walking task (private Stage 16 binding).

The observation/action ordering mirrors ``unitree_rl_gym``'s blind Go2
policy: 48 state values and 12 native position-target actions clipped at 100.
Physics
capability selection remains owned by the public runtime factory; this task
does not special-case either ``merged_scene`` or ``static_template``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np
from gymnasium.spaces import Box, Dict

from ...environment import (
    EpisodePhysicsState,
    ObservationFieldSpec,
    ObservationSchema,
    RuntimeSnapshot,
    TaskBatchEvaluation,
    TaskEvaluation,
    TaskStateView,
    as_task_state_view,
    freeze_observation,
)
from ...environment.configuration import resolve_env_config
from ...environment.task_definition import TaskDefinitionBase
from ...registry import register_env
from ...runtime.contracts import DeviceResetSelection
from ...robots.go2 import (
    GO2_ACTION_CONTRACT,
    GO2_DEFAULT_JOINT_ANGLES,
    GO2_KD,
    GO2_KP,
    Go2ActionAdapter,
)
from ...vectorization.registry import register_parallel_env
from ..base import BaseTaskEnv
from .assets import GO2_SCENE_UID, Go2WalkSceneComposer, canonical_xml_digest
from .domain_randomization import Go2DomainRandomizationConfig


GO2_ENV_ID = "go2-walk-v1"
GO2_HORIZON = 1000
GO2_PHYSICS_DT = 0.005
GO2_CONTROL_SUBSTEPS = 4
GO2_POLICY_DT = GO2_PHYSICS_DT * GO2_CONTROL_SUBSTEPS
GO2_COMMAND_RESAMPLE_STEPS = 4 * int(round(1.0 / GO2_POLICY_DT))
GO2_TERMINATION_ANGLE = np.deg2rad(10.0)
# Task subclasses may use a short reset grace window for intentionally
# randomized initial states.  The default Go2 walk contract remains strict.
GO2_TERMINATION_GRACE_STEPS = 0
GO2_HEIGHT_COMMAND_MIN = 0.34
GO2_HEIGHT_COMMAND_MAX = 0.34
GO2_OBS_SCHEMA_VERSION = "task-env-go2-walk-observation-v1"
# Unitree's actor command channels are already in [-1, 1].  Keep linear
# command observations at unit scale and apply the reference yaw scale only.
GO2_COMMAND_OBS_SCALE = np.asarray((1.0, 1.0, 0.25), dtype=np.float32)


def _quat_rotate_inverse(quat: np.ndarray, vector: np.ndarray) -> np.ndarray:
    """Rotate world-frame vectors into a wxyz quaternion's body frame."""

    q = np.asarray(quat, dtype=np.float32)
    v = np.asarray(vector, dtype=np.float32)
    q_xyz = q[..., 1:]
    q_w = q[..., :1]
    t = 2.0 * np.cross(q_xyz, v)
    return (v - q_w * t + np.cross(q_xyz, t)).astype(np.float32, copy=False)


def _base_kinematics(
    qpos: np.ndarray,
    qvel: np.ndarray,
    body_xpos: np.ndarray | None,
    base_body_id: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    value_qpos = np.asarray(qpos, dtype=np.float32)
    value_qvel = np.asarray(qvel, dtype=np.float32)
    batch = value_qpos.ndim == 2
    if batch:
        root_quat = value_qpos[:, 3:7]
        world_lin = value_qvel[:, :3]
        world_ang = value_qvel[:, 3:6]
        base_pos = (
            np.asarray(body_xpos, dtype=np.float32)[:, base_body_id]
            if body_xpos is not None
            else value_qpos[:, :3]
        )
    else:
        root_quat = value_qpos[3:7]
        world_lin = value_qvel[:3]
        world_ang = value_qvel[3:6]
        base_pos = (
            np.asarray(body_xpos, dtype=np.float32)[base_body_id]
            if body_xpos is not None
            else value_qpos[:3]
        )
    gravity = np.zeros_like(world_lin, dtype=np.float32)
    gravity[..., 2] = -1.0
    base_lin = _quat_rotate_inverse(root_quat, world_lin)
    base_ang = _quat_rotate_inverse(root_quat, world_ang)
    projected = _quat_rotate_inverse(root_quat, gravity)
    return base_pos, base_lin, base_ang, projected


def _base_roll_pitch(
    qpos: np.ndarray,
    body_xquat: np.ndarray | None,
    base_body_id: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return Unitree's roll/pitch termination angles from wxyz quaternions."""

    value_qpos = np.asarray(qpos, dtype=np.float32)
    if body_xquat is not None:
        value = np.asarray(body_xquat, dtype=np.float32)
        quat = value[..., base_body_id, :] if value.ndim == 3 else value[base_body_id]
    else:
        quat = value_qpos[..., 3:7]
    w, x, y, z = [quat[..., index] for index in range(4)]
    roll = np.arctan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
    pitch_arg = np.clip(2.0 * (w * y - z * x), -1.0, 1.0)
    pitch = np.arcsin(pitch_arg)
    return roll.astype(np.float32), pitch.astype(np.float32)


def _torch_quat_rotate_inverse(quat, vector):
    """Torch equivalent of ``_quat_rotate_inverse`` for device transitions."""

    import torch

    q_xyz = quat[..., 1:]
    q_w = quat[..., :1]
    t = 2.0 * torch.linalg.cross(q_xyz, vector, dim=-1)
    return vector - q_w * t + torch.linalg.cross(q_xyz, t, dim=-1)


class Go2ObservationBuilder:
    def __init__(self, *, joint_qpos_ids: np.ndarray, joint_dof_ids: np.ndarray, base_body_id: int):
        self._qpos_ids = np.asarray(joint_qpos_ids, dtype=np.int32)
        self._dof_ids = np.asarray(joint_dof_ids, dtype=np.int32)
        self._base_body_id = int(base_body_id)
        self.observation_space = Dict(
            {"state": Dict({"proprioception": Box(low=-100.0, high=100.0, shape=(48,), dtype=np.float32)})}
        )
        self._schema = ObservationSchema(
            version=GO2_OBS_SCHEMA_VERSION,
            fields=(ObservationFieldSpec(
                name="state.proprioception", shape=(48,), dtype="float32",
                semantic=("base_lin_vel(3), base_ang_vel(3), projected_gravity(3), commands(3), "
                          "dof_pos_error(12), dof_vel(12), actions(12); unitree_rl_gym Go2 ordering"),
            ),),
            groups=("state",),
        )

    @property
    def schema(self) -> ObservationSchema:
        return self._schema

    def build(self, snapshot: RuntimeSnapshot, sensor_observation=None) -> Any:
        del sensor_observation
        return self._build(as_task_state_view(snapshot), np.zeros(3, dtype=np.float32), np.zeros(12, dtype=np.float32))

    def _build(self, view: TaskStateView, command: np.ndarray, actions: np.ndarray) -> Any:
        qpos = np.asarray(view.qpos, dtype=np.float32)
        qvel = np.asarray(view.qvel, dtype=np.float32)
        _, base_lin, base_ang, projected = _base_kinematics(qpos, qvel, view.body_xpos, self._base_body_id)
        dof_pos = qpos[..., self._qpos_ids] - GO2_DEFAULT_JOINT_ANGLES
        dof_vel = qvel[..., self._dof_ids]
        command_value = np.asarray(command, dtype=np.float32)
        scaled_command = command_value * GO2_COMMAND_OBS_SCALE
        if qpos.ndim == 1:
            values = np.concatenate((base_lin * 2.0, base_ang * 0.25, projected, scaled_command, dof_pos, dof_vel * 0.05, np.asarray(actions, dtype=np.float32)))
            if values.shape != (48,):
                raise ValueError("Go2 scalar observation must have shape (48,)")
            return freeze_observation((("state", {"proprioception": values.astype(np.float32)}),))
        values = np.concatenate((base_lin * 2.0, base_ang * 0.25, projected, scaled_command, dof_pos, dof_vel * 0.05, np.asarray(actions, dtype=np.float32)), axis=1)
        return {"state": {"proprioception": values.astype(np.float32, copy=False)}}


@dataclass
class Go2WalkTaskDefinition(TaskDefinitionBase):
    uses_unified_state_view = True
    joint_qpos_ids: np.ndarray
    joint_dof_ids: np.ndarray
    actuator_ids: np.ndarray
    ctrl_range: np.ndarray
    base_body_id: int
    joint_range: np.ndarray
    foot_body_ids: np.ndarray
    penalized_body_ids: np.ndarray
    # The canonical MuJoCo Go2 asset attaches the named foot geoms to the
    # calf bodies, while the Isaac URDF has separate foot links.  Keep the
    # reward identity at geom granularity when the static runtime exposes
    # its optional local contact slots; body summaries remain the fallback
    # for older/exact runtimes.
    foot_geom_ids: np.ndarray
    penalized_geom_ids: np.ndarray
    # Private deployment registrations extend the command contract without
    # introducing task-id branches into the common vector/runtime factory.
    command_dim: ClassVar[int] = 3
    # Legacy go2-walk keeps Unitree's hidden target-heading behavior.  Deploy
    # tasks override this so the visible third command is an explicit wz rate.
    heading_command_enabled: ClassVar[bool] = True
    height_command_enabled: ClassVar[bool] = False
    height_target_default: ClassVar[float | None] = None
    height_reward_scale: ClassVar[float] = 0.0
    height_error_tolerance: ClassVar[float] = 0.1
    roll_orientation_weight: ClassVar[float] = 0.0
    pitch_orientation_weight: ClassVar[float] = 0.0
    termination_grace_steps: ClassVar[int] = GO2_TERMINATION_GRACE_STEPS

    def __post_init__(self) -> None:
        self._last_actions: np.ndarray | None = None
        self._last_dof_vel: np.ndarray | None = None
        self._commands: np.ndarray | None = None
        self._feet_air_time: np.ndarray | None = None
        self._last_contacts: np.ndarray | None = None
        # Unitree's heading-command mode keeps a fourth internal target while
        # exposing only the first three command values to the policy.  The
        # optional array is task-owned; legacy/manual oracle fixtures that
        # provide only a three-value command retain their fixed-yaw behavior.
        self._headings: np.ndarray | None = None
        self._heading_enabled: np.ndarray | None = None
        self._command_rng = np.random.default_rng(0)
        self._device_last_actions = None
        self._device_last_dof_vel = None
        self._device_commands = None
        self._device_headings = None
        self._device_heading_enabled = None
        self._device_feet_air_time = None
        self._device_last_contacts = None
        self._device_elapsed = None
        # Device transitions keep command-resampling bookkeeping on the host
        # side.  This is not a physics readback: the counters are advanced by
        # the lifecycle tick and reset only for masked episode boundaries.
        # Keeping them separate from ``_device_elapsed`` lets the latter stay
        # a device tensor used for truncation while the reset sampler remains
        # the owner of command RNG state.
        self._device_command_steps: np.ndarray | None = None
        # Stage 20：每个 device/dtype 组合只创建一次索引和常量 tensor，正常
        # policy tick 不再反复从 NumPy 包装同一组 task 常量。
        self._device_static_constants: dict[tuple[str, str], dict[str, Any]] = {}

    def create_action_adapter(self, compiled_scene):
        del compiled_scene
        return Go2ActionAdapter(
            joint_qpos_ids=self.joint_qpos_ids, joint_dof_ids=self.joint_dof_ids,
            actuator_ids=self.actuator_ids, ctrl_range=self.ctrl_range,
        )

    def create_observation_builder(self, compiled_scene, **_kwargs):
        del compiled_scene
        return Go2ObservationBuilder(
            joint_qpos_ids=self.joint_qpos_ids, joint_dof_ids=self.joint_dof_ids,
            base_body_id=self.base_body_id,
        )

    def build_observation(self, state: TaskStateView, *, sensor_observation=None) -> Any:
        del sensor_observation
        view = as_task_state_view(state)
        if view.is_batch:
            actions = self._last_actions
            if actions is None or actions.shape != (view.batch_size, 12):
                actions = np.zeros((view.batch_size, 12), dtype=np.float32)
            commands = self._commands
            if commands is None or commands.shape != (view.batch_size, self.command_dim):
                commands = np.zeros((view.batch_size, self.command_dim), dtype=np.float32)
        else:
            actions = np.zeros(12, dtype=np.float32) if self._last_actions is None else self._last_actions
            commands = np.zeros(self.command_dim, dtype=np.float32) if self._commands is None else self._commands
        return self.create_observation_builder_from_state(view, actions, commands)

    def _device_command_tensor(self, *, batch_size: int, device, dtype):
        import torch

        if self._device_commands is None or tuple(self._device_commands.shape) != (batch_size, self.command_dim):
            source = np.zeros((batch_size, self.command_dim), dtype=np.float32)
            if self._commands is not None and np.asarray(self._commands).shape == (batch_size, self.command_dim):
                source = np.asarray(self._commands, dtype=np.float32)
            self._device_commands = torch.as_tensor(source, dtype=dtype, device=device)
        elif self._device_commands.device != device or self._device_commands.dtype != dtype:
            self._device_commands = self._device_commands.to(device=device, dtype=dtype)
        return self._device_commands

    def _device_heading_tensor(self, *, batch_size: int, device, dtype):
        import torch

        if self._device_headings is None or tuple(self._device_headings.shape) != (batch_size,):
            source = np.zeros(batch_size, dtype=np.float32)
            if self._headings is not None and np.asarray(self._headings).shape == (batch_size,):
                source = np.asarray(self._headings, dtype=np.float32)
            self._device_headings = torch.as_tensor(source, dtype=dtype, device=device)
        elif self._device_headings.device != device or self._device_headings.dtype != dtype:
            self._device_headings = self._device_headings.to(device=device, dtype=dtype)
        return self._device_headings

    def _device_heading_enabled_tensor(self, *, batch_size: int, device):
        import torch

        if self._device_heading_enabled is None or tuple(self._device_heading_enabled.shape) != (batch_size,):
            source = np.zeros(batch_size, dtype=np.bool_) if self._heading_enabled is None else self._heading_enabled
            self._device_heading_enabled = torch.as_tensor(source, dtype=torch.bool, device=device)
        elif self._device_heading_enabled.device != device:
            self._device_heading_enabled = self._device_heading_enabled.to(device=device)
        return self._device_heading_enabled

    @staticmethod
    def _heading_yaw_command(root_quat, target_heading):
        """Match legged_gym's heading-command callback in body/world frames."""

        import torch

        w, x, y, z = [root_quat[..., index] for index in range(4)]
        forward_x = 1.0 - 2.0 * (y * y + z * z)
        forward_y = 2.0 * (x * y + w * z)
        heading = torch.atan2(forward_y, forward_x)
        wrapped = torch.atan2(
            torch.sin(target_heading - heading),
            torch.cos(target_heading - heading),
        )
        return torch.clamp(0.5 * wrapped, -1.0, 1.0)

    def _device_update_heading_command(self, *, qpos, root_quat, batch_size: int):
        import torch

        if self._headings is None or self._heading_enabled is None or not np.any(self._heading_enabled):
            return self._device_command_tensor(
                batch_size=batch_size, device=qpos.device, dtype=qpos.dtype
            )
        commands = self._device_command_tensor(
            batch_size=batch_size, device=qpos.device, dtype=qpos.dtype
        )
        headings = self._device_heading_tensor(
            batch_size=batch_size, device=qpos.device, dtype=qpos.dtype
        )
        enabled = self._device_heading_enabled_tensor(batch_size=batch_size, device=qpos.device)
        yaw_command = self._heading_yaw_command(root_quat, headings)
        # The command tensor is task-owned persistent state.  Update only the
        # derived yaw component in place so a normal policy tick does not
        # allocate a second command tensor.
        commands[..., 2].copy_(torch.where(enabled, yaw_command, commands[..., 2]))
        return commands

    def _device_action_tensor(self, *, batch_size: int, device, dtype):
        import torch

        if self._device_last_actions is None or tuple(self._device_last_actions.shape) != (batch_size, 12):
            self._device_last_actions = torch.zeros((batch_size, 12), dtype=dtype, device=device)
        elif self._device_last_actions.device != device or self._device_last_actions.dtype != dtype:
            self._device_last_actions = self._device_last_actions.to(device=device, dtype=dtype)
        return self._device_last_actions

    def _device_constants(self, *, qpos):
        """返回与当前 runtime device/dtype 对齐且可复用的 Go2 常量。"""

        import torch

        key = (str(qpos.device), str(qpos.dtype))
        cached = self._device_static_constants.get(key)
        if cached is not None:
            return cached
        cached = {
            "qpos_ids": torch.tensor(self.joint_qpos_ids, dtype=torch.long, device=qpos.device),
            "dof_ids": torch.tensor(self.joint_dof_ids, dtype=torch.long, device=qpos.device),
            "default_angles": torch.tensor(GO2_DEFAULT_JOINT_ANGLES, dtype=qpos.dtype, device=qpos.device),
            "kp": torch.tensor(GO2_KP, dtype=qpos.dtype, device=qpos.device),
            "kd": torch.tensor(GO2_KD, dtype=qpos.dtype, device=qpos.device),
            "ctrl_limits": torch.tensor(
                self.ctrl_range[self.actuator_ids], dtype=qpos.dtype, device=qpos.device
            ),
            "command_scale": torch.as_tensor(GO2_COMMAND_OBS_SCALE, dtype=qpos.dtype, device=qpos.device),
            "foot_body_ids": torch.tensor(self.foot_body_ids, dtype=torch.long, device=qpos.device),
            "penalized_body_ids": torch.tensor(self.penalized_body_ids, dtype=torch.long, device=qpos.device),
            "foot_geom_ids": torch.tensor(self.foot_geom_ids, dtype=torch.long, device=qpos.device),
            "penalized_geom_ids": torch.tensor(self.penalized_geom_ids, dtype=torch.long, device=qpos.device),
            "base_body_ids": torch.tensor((self.base_body_id,), dtype=torch.long, device=qpos.device),
        }
        joint_ranges = torch.tensor(self.joint_range, dtype=qpos.dtype, device=qpos.device)
        midpoint = 0.5 * (joint_ranges[:, 0] + joint_ranges[:, 1])
        half = 0.5 * (joint_ranges[:, 1] - joint_ranges[:, 0]) * 0.9
        cached["joint_limit_low"] = midpoint - half
        cached["joint_limit_high"] = midpoint + half
        self._device_static_constants[key] = cached
        return cached

    def build_device_observation(self, state):
        """Build the 48-value Go2 policy tensor without NumPy readback."""

        import torch

        qpos = state.arrays["qpos"]
        qvel = state.arrays["qvel"]
        batch_size = int(state.num_envs)
        if qpos.ndim != 2 or qvel.ndim != 2:
            raise ValueError("Go2 device state qpos/qvel must be batched tensors")
        constants = self._device_constants(qpos=qpos)
        if "body_xquat" in state.arrays and state.arrays["body_xquat"].shape[1] > self.base_body_id:
            root_quat = state.arrays["body_xquat"][:, self.base_body_id]
        else:
            root_quat = qpos[:, 3:7]
        world_lin = qvel[:, :3]
        world_ang = qvel[:, 3:6]
        gravity = torch.zeros_like(world_lin)
        gravity[:, 2] = -1.0
        base_lin = _torch_quat_rotate_inverse(root_quat, world_lin)
        base_ang = _torch_quat_rotate_inverse(root_quat, world_ang)
        projected = _torch_quat_rotate_inverse(root_quat, gravity)
        qpos_ids = constants["qpos_ids"]
        dof_ids = constants["dof_ids"]
        default = constants["default_angles"]
        commands = self._device_command_tensor(batch_size=batch_size, device=qpos.device, dtype=qpos.dtype)
        actions = self._device_action_tensor(batch_size=batch_size, device=qpos.device, dtype=qpos.dtype)
        scaled_command = commands * constants["command_scale"]
        values = torch.cat(
            (
                base_lin * 2.0,
                base_ang * 0.25,
                projected,
                scaled_command,
                qpos.index_select(-1, qpos_ids) - default,
                qvel.index_select(-1, dof_ids) * 0.05,
                actions,
            ),
            dim=1,
        )
        if tuple(values.shape) != (batch_size, 48):
            raise ValueError(f"Go2 device observation must have shape ({batch_size}, 48)")
        return values

    def _device_body_contact(self, state, body_ids, *, batch_size: int):
        import torch

        ids = body_ids if hasattr(body_ids, "device") else torch.as_tensor(body_ids, dtype=torch.long, device=state.device)
        matrix = self._device_contact_matrix(state, batch_size=batch_size)
        if ids.numel() == 0 or matrix.shape[-1] == 0:
            return torch.zeros((batch_size,), dtype=torch.bool, device=state.device)
        valid = ids[ids < matrix.shape[-1]]
        if valid.numel() == 0:
            return torch.zeros((batch_size,), dtype=torch.bool, device=state.device)
        return matrix[..., valid].any(dim=-1)

    def _device_contact_matrix(self, state, *, batch_size: int):
        """Return body-local contact activity without collapsing selected bodies."""

        import torch

        values = []
        for name in ("ground_contact_active", "body_contact_active"):
            value = state.arrays.get(name)
            if value is not None and value.ndim == 2:
                values.append(value.to(torch.bool))
        if not values:
            return torch.zeros((batch_size, 0), dtype=torch.bool, device=state.device)
        width = max(int(value.shape[-1]) for value in values)
        result = torch.zeros((batch_size, width), dtype=torch.bool, device=state.device)
        for value in values:
            result[..., : value.shape[-1]] = torch.logical_or(
                result[..., : value.shape[-1]], value
            )
        return result

    def _device_geom_contact(self, state, geom_ids, *, batch_size: int):
        """Return selected local contact-geometries, or ``None`` if absent."""

        import torch

        slots = state.arrays.get("ground_contact_geom")
        if slots is None or slots.ndim != 2:
            return None
        ids = geom_ids if hasattr(geom_ids, "device") else torch.as_tensor(geom_ids, dtype=torch.long, device=slots.device)
        if ids.numel() == 0:
            return torch.zeros((batch_size, 0), dtype=torch.bool, device=slots.device)
        return torch.any(slots[..., None] == ids[None, None, :], dim=1)

    def _device_dof_limit_penalty(self, dof_pos, *, constants=None):
        import torch

        if constants is None:
            constants = self._device_constants(qpos=dof_pos)
        # Keep the violation non-negative; the Unitree reward scale applies
        # the ``-10`` sign at the call site, matching the host implementation.
        return torch.sum(
            torch.relu(constants["joint_limit_low"] - dof_pos)
            + torch.relu(dof_pos - constants["joint_limit_high"]),
            dim=-1,
        )

    def evaluate_device(self, *, state, action, elapsed_steps=None, previous_state=None):
        """Evaluate the Go2 transition using device tensors only.

        This mirrors the public reward/termination algebra for the fixed
        contract.  Command resampling remains task-local and is initialized
        from the host reset sampler.  The small host-side tick counter below
        only schedules the RNG update; it does not read a physics tensor back
        from the device.
        """

        import torch

        del elapsed_steps, previous_state
        qpos = state.arrays["qpos"]
        qvel = state.arrays["qvel"]
        action = action if hasattr(action, "device") else torch.as_tensor(action, device=state.device)
        batch_size = int(state.num_envs)
        constants = self._device_constants(qpos=qpos)
        if (
            self._device_command_steps is None
            or self._device_command_steps.shape != (batch_size,)
        ):
            self._device_command_steps = np.zeros(batch_size, dtype=np.int32)
        self._device_command_steps += 1
        self._maybe_resample_commands(self._device_command_steps, batch_size)
        qpos_ids = constants["qpos_ids"]
        dof_ids = constants["dof_ids"]
        default = constants["default_angles"]
        kp = constants["kp"]
        kd = constants["kd"]
        target = default + 0.25 * action
        torque = kp * (target - qpos.index_select(-1, qpos_ids)) - kd * qvel.index_select(-1, dof_ids)
        limits = constants["ctrl_limits"]
        torque = torch.clamp(torque, limits[:, 0], limits[:, 1])

        root_quat = state.arrays.get("body_xquat", qpos[:, None, 3:7])[:, self.base_body_id]
        gravity = torch.zeros_like(qvel[:, :3])
        gravity[:, 2] = -1.0
        lin = _torch_quat_rotate_inverse(root_quat, qvel[:, :3])
        ang = _torch_quat_rotate_inverse(root_quat, qvel[:, 3:6])
        projected = _torch_quat_rotate_inverse(root_quat, gravity)
        commands = self._device_update_heading_command(
            qpos=qpos, root_quat=root_quat, batch_size=batch_size
        )
        w, x, y, z = [root_quat[..., index] for index in range(4)]
        roll = torch.atan2(
            2.0 * (w * x + y * z),
            1.0 - 2.0 * (x * x + y * y),
        )
        pitch = torch.asin(
            torch.clamp(2.0 * (w * y - z * x), -1.0, 1.0)
        )
        previous = self._device_action_tensor(batch_size=batch_size, device=qpos.device, dtype=qpos.dtype)
        if self._device_last_dof_vel is None or tuple(self._device_last_dof_vel.shape) != (batch_size, 12):
            # The public NumPy reset path records the reset-time velocity as
            # the first reward baseline.  Rehydrate that snapshot once on the
            # task device instead of using the post-physics velocity from the
            # current tick; this keeps ``dof_acc`` algebraically identical.
            host_previous = np.asarray(self._last_dof_vel, dtype=np.float32)
            if host_previous.shape == (batch_size, 12):
                previous_vel = torch.as_tensor(
                    host_previous, dtype=qpos.dtype, device=qpos.device
                )
            else:
                previous_vel = qvel.index_select(-1, dof_ids).detach().clone()
        else:
            previous_vel = self._device_last_dof_vel
        dt = GO2_POLICY_DT
        shape = (batch_size,)
        terms = {
            "tracking_lin_vel": torch.exp(-torch.sum((commands[..., :2] - lin[..., :2]) ** 2, dim=-1) / 0.25) * dt,
            "tracking_ang_vel": torch.exp(-((commands[..., 2] - ang[..., 2]) ** 2) / 0.25) * 0.5 * dt,
            "lin_vel_z": -2.0 * lin[..., 2] ** 2 * dt,
            "ang_vel_xy": -0.05 * torch.sum(ang[..., :2] ** 2, dim=-1) * dt,
            "torques": -0.0002 * torch.sum(torque ** 2, dim=-1) * dt,
            # unitree_rl_gym uses a -10 scale with a 0.9 soft limit.  Keep
            # the violation helper positive so host/device reward algebra is
            # explicit and matches the reference implementation.
            "dof_pos_limits": -10.0 * self._device_dof_limit_penalty(
                qpos.index_select(-1, qpos_ids), constants=constants
            ) * dt,
            "dof_acc": -2.5e-7 * torch.sum(((previous_vel - qvel.index_select(-1, dof_ids)) / dt) ** 2, dim=-1) * dt,
            "action_rate": -0.01 * torch.sum((previous - action) ** 2, dim=-1) * dt,
            "orientation": -(
                float(self.roll_orientation_weight) * roll.square()
                + float(self.pitch_orientation_weight) * pitch.square()
            ) * dt,
        }
        if self.height_command_enabled:
            body_xpos = state.arrays.get("body_xpos")
            if body_xpos is not None and body_xpos.shape[1] > self.base_body_id:
                base_height = body_xpos[:, self.base_body_id, 2]
            else:
                base_height = qpos[:, 2]
            if commands.shape[-1] >= 4:
                height_target = commands[..., 3]
            else:
                height_target = torch.full_like(
                    base_height, float(self.height_target_default)
                )
            height_error = torch.clamp(
                torch.abs(base_height - height_target),
                min=0.0,
                max=float(self.height_error_tolerance),
            )
            terms["base_height_command"] = float(self.height_reward_scale) * (
                1.0 - height_error / float(self.height_error_tolerance)
            )
        contact_matrix = self._device_contact_matrix(state, batch_size=batch_size)
        geom_contact = self._device_geom_contact(
            state, constants["foot_geom_ids"], batch_size=batch_size
        )
        if geom_contact is not None:
            feet_contact = geom_contact
        else:
            foot_ids = constants["foot_body_ids"]
            valid_foot_ids = foot_ids[foot_ids < contact_matrix.shape[-1]]
            if valid_foot_ids.numel() == len(self.foot_body_ids):
                feet_contact = contact_matrix.index_select(-1, valid_foot_ids)
            else:
                feet_contact = torch.zeros(
                    (batch_size, len(self.foot_body_ids)), dtype=torch.bool, device=qpos.device
                )
                if valid_foot_ids.numel():
                    feet_contact[..., :valid_foot_ids.numel()] = contact_matrix.index_select(-1, valid_foot_ids)
        if (
            self._device_feet_air_time is None
            or tuple(self._device_feet_air_time.shape) != (batch_size, len(self.foot_body_ids))
            or self._device_feet_air_time.device != qpos.device
            or self._device_feet_air_time.dtype != qpos.dtype
        ):
            self._device_feet_air_time = torch.zeros((batch_size, len(self.foot_body_ids)), dtype=qpos.dtype, device=qpos.device)
            self._device_last_contacts = torch.zeros_like(self._device_feet_air_time, dtype=torch.bool)
        previous_contacts = self._device_last_contacts
        contact_filt = torch.logical_or(feet_contact, previous_contacts)
        first_contact = torch.logical_and(self._device_feet_air_time > 0.0, contact_filt)
        self._device_feet_air_time.add_(dt)
        air_reward = torch.sum((self._device_feet_air_time - 0.5) * first_contact, dim=-1)
        air_reward = air_reward * (torch.linalg.vector_norm(commands[..., :2], dim=-1) > 0.1)
        self._device_feet_air_time.mul_(~contact_filt)
        self._device_last_contacts.copy_(feet_contact)
        terms["feet_air_time"] = air_reward * dt
        if geom_contact is not None:
            penalized_geom_contact = self._device_geom_contact(
                state, constants["penalized_geom_ids"], batch_size=batch_size
            )
            collision = (
                penalized_geom_contact.to(qpos.dtype).sum(dim=-1)
                if penalized_geom_contact is not None and penalized_geom_contact.shape[-1]
                else torch.zeros(batch_size, dtype=qpos.dtype, device=qpos.device)
            )
        else:
            penalized_ids = constants["penalized_body_ids"]
            valid_penalized = penalized_ids[penalized_ids < contact_matrix.shape[-1]]
            collision = (
                contact_matrix.index_select(-1, valid_penalized).to(qpos.dtype).sum(dim=-1)
                if valid_penalized.numel() else torch.zeros(batch_size, dtype=qpos.dtype, device=qpos.device)
            )
        terms["collision"] = -collision * dt
        reward = torch.clamp(torch.stack(tuple(terms.values()), dim=0).sum(dim=0), min=0.0)

        raw_fall = (torch.abs(roll) > GO2_TERMINATION_ANGLE) | (
            torch.abs(pitch) > GO2_TERMINATION_ANGLE
        )
        if self.termination_grace_steps > 0:
            if self._device_elapsed is None:
                episode_age = torch.ones(batch_size, dtype=torch.int32, device=qpos.device)
            else:
                episode_age = self._device_elapsed + 1
            fall = raw_fall & (episode_age >= self.termination_grace_steps)
        else:
            fall = raw_fall
        base_contact = self._device_body_contact(
            state, constants["base_body_ids"], batch_size=batch_size
        )
        # Keep task-owned previous-action/velocity storage stable across the
        # rollout.  Allocation is reserved for the first tick or a shape,
        # device, or dtype change.
        if (
            self._device_last_actions is None
            or tuple(self._device_last_actions.shape) != tuple(action.shape)
            or self._device_last_actions.device != action.device
            or self._device_last_actions.dtype != action.dtype
        ):
            self._device_last_actions = torch.empty_like(action)
        self._device_last_actions.copy_(action.detach())
        current_dof_vel = qvel.index_select(-1, dof_ids).detach()
        if (
            self._device_last_dof_vel is None
            or tuple(self._device_last_dof_vel.shape) != tuple(current_dof_vel.shape)
            or self._device_last_dof_vel.device != current_dof_vel.device
            or self._device_last_dof_vel.dtype != current_dof_vel.dtype
        ):
            self._device_last_dof_vel = torch.empty_like(current_dof_vel)
        self._device_last_dof_vel.copy_(current_dof_vel)
        if self._device_elapsed is None or tuple(self._device_elapsed.shape) != (batch_size,):
            self._device_elapsed = torch.zeros((batch_size,), dtype=torch.int32, device=qpos.device)
        elif self._device_elapsed.device != qpos.device:
            self._device_elapsed = torch.zeros((batch_size,), dtype=torch.int32, device=qpos.device)
        self._device_elapsed.add_(1)
        return {
            "reward": reward,
            "terminated": fall | base_contact,
            "truncated": self._device_elapsed >= GO2_HORIZON,
            "infos": None,
            "metrics": {
                "base_height": state.arrays.get("body_xpos", qpos[:, None, :3])[:, self.base_body_id, 2],
                "roll": roll,
                "pitch": pitch,
                "fall": fall,
                "base_contact": base_contact,
            },
            "reward_terms": terms,
        }

    def create_observation_builder_from_state(self, view, actions, commands):
        qpos = np.asarray(view.qpos, dtype=np.float32)
        qvel = np.asarray(view.qvel, dtype=np.float32)
        _, base_lin, base_ang, projected = _base_kinematics(qpos, qvel, view.body_xpos, self.base_body_id)
        dof_pos = qpos[..., self.joint_qpos_ids] - GO2_DEFAULT_JOINT_ANGLES
        dof_vel = qvel[..., self.joint_dof_ids]
        scaled_command = np.asarray(commands, dtype=np.float32) * GO2_COMMAND_OBS_SCALE
        if qpos.ndim == 1:
            values = np.concatenate((base_lin * 2.0, base_ang * 0.25, projected, scaled_command, dof_pos, dof_vel * 0.05, actions))
            return freeze_observation((("state", {"proprioception": values.astype(np.float32)}),))
        values = np.concatenate((base_lin * 2.0, base_ang * 0.25, projected, scaled_command, dof_pos, dof_vel * 0.05, actions), axis=1)
        return {"state": {"proprioception": values.astype(np.float32, copy=False)}}

    def on_reset_sample(self, *, parameters, seeds, reset_mask: np.ndarray) -> None:
        """Consume named command samples without changing the common reset API."""

        mask = np.asarray(reset_mask, dtype=np.bool_)
        if isinstance(parameters, dict):
            entries = [parameters]
        else:
            entries = list(parameters)
        selected_slots = np.flatnonzero(mask).astype(np.int64, copy=False)
        if mask.ndim != 1 or len(entries) not in {mask.size, selected_slots.size}:
            raise ValueError("Go2 reset parameters must contain either one entry per world or selected slot")
        sparse = len(entries) == selected_slots.size and len(entries) != mask.size
        command_dim = int(
            getattr(
                self,
                "command_dim",
                self._commands.shape[-1] if self._commands is not None else 3,
            )
        )
        if self._commands is None or self._commands.shape != (mask.size, command_dim):
            self._commands = np.zeros((mask.size, command_dim), dtype=np.float32)
        if self._headings is None or self._headings.shape != (mask.size,):
            self._headings = np.zeros(mask.size, dtype=np.float32)
        if self._heading_enabled is None or self._heading_enabled.shape != (mask.size,):
            self._heading_enabled = np.zeros(mask.size, dtype=np.bool_)
        for local_slot, slot in enumerate(selected_slots):
            entry = entries[local_slot] if sparse else entries[int(slot)]
            command = np.asarray(
                entry.get("command", np.zeros(command_dim)), dtype=np.float32
            )
            if command.shape != (command_dim,):
                raise ValueError(
                    f"Go2 reset command must have shape ({command_dim},)"
                )
            self._commands[slot] = command
            if (
                getattr(self, "heading_command_enabled", True)
                and "heading" in entry
            ):
                self._headings[slot] = np.float32(entry["heading"])
                self._heading_enabled[slot] = True
            else:
                # Manual oracle fixtures and deploy tasks use an explicit yaw
                # command and intentionally do not opt into heading mode.
                self._headings[slot] = 0.0
                self._heading_enabled[slot] = False
        # Keep the persistent B-sized command tensors live across sparse
        # autoresets.  Re-uploading all worlds after every terminal tick is
        # unnecessary because the sampler changed only ``selected_slots``.
        # Pack task-width commands, heading, and enabled bit into one
        # compact transfer, then update those rows in place.
        device_commands = self._device_commands
        device_headings = self._device_headings
        device_heading_enabled = self._device_heading_enabled
        device_cache_valid = (
            device_commands is not None
            and device_headings is not None
            and device_heading_enabled is not None
            and tuple(device_commands.shape) == (mask.size, command_dim)
            and tuple(device_headings.shape) == (mask.size,)
            and tuple(device_heading_enabled.shape) == (mask.size,)
            and device_headings.device == device_commands.device
            and device_heading_enabled.device == device_commands.device
        )
        if device_cache_valid and selected_slots.size:
            import torch

            packed_host = np.concatenate(
                (
                    self._commands[selected_slots],
                    self._headings[selected_slots, None],
                    self._heading_enabled[selected_slots, None].astype(
                        np.float32,
                        copy=False,
                    ),
                ),
                axis=1,
            )
            slot_ids = torch.as_tensor(
                selected_slots,
                dtype=torch.long,
                device=device_commands.device,
            )
            packed = torch.as_tensor(
                packed_host,
                dtype=device_commands.dtype,
                device=device_commands.device,
            )
            device_commands.index_copy_(
                0, slot_ids, packed[:, : command_dim]
            )
            device_headings.index_copy_(
                0,
                slot_ids,
                packed[:, command_dim].to(dtype=device_headings.dtype),
            )
            device_heading_enabled.index_copy_(
                0,
                slot_ids,
                packed[:, command_dim + 1].to(dtype=torch.bool),
            )
        elif not device_cache_valid:
            # A mismatched/partial cache cannot be updated atomically.  Retain
            # the established full reconstruction fallback for that rare path.
            self._device_commands = None
            self._device_headings = None
            self._device_heading_enabled = None
        if seeds:
            seed_values = [int(value) for value in seeds if value is not None]
            if seed_values:
                self._command_rng = np.random.default_rng(seed_values[0] + 7919)

    def reset_device(
        self,
        *,
        state,
        reset_mask,
        selection: DeviceResetSelection | None = None,
    ) -> None:
        """Reset Go2 semantic device state for selected worlds in place."""

        import torch

        qvel = state.arrays["qvel"]
        mask = reset_mask.to(device=qvel.device, dtype=torch.bool)
        batch_size = int(state.num_envs)
        if tuple(mask.shape) != (batch_size,):
            raise ValueError(f"Go2 device reset mask must have shape ({batch_size},)")
        dof_ids = self._device_constants(qpos=qvel)["dof_ids"]
        reset_dof_vel = qvel.index_select(-1, dof_ids)

        if self._device_last_actions is not None:
            if (
                tuple(self._device_last_actions.shape) == (batch_size, 12)
                and self._device_last_actions.device == qvel.device
            ):
                self._device_last_actions.masked_fill_(mask[:, None], 0.0)
            else:
                self._device_last_actions = None
        if self._device_last_dof_vel is not None:
            if (
                tuple(self._device_last_dof_vel.shape) == tuple(reset_dof_vel.shape)
                and self._device_last_dof_vel.device == qvel.device
                and self._device_last_dof_vel.dtype == reset_dof_vel.dtype
            ):
                self._device_last_dof_vel[mask] = reset_dof_vel[mask]
            else:
                self._device_last_dof_vel = None
        if self._device_feet_air_time is not None:
            expected = (batch_size, len(self.foot_body_ids))
            if (
                tuple(self._device_feet_air_time.shape) == expected
                and self._device_feet_air_time.device == qvel.device
            ):
                self._device_feet_air_time.masked_fill_(mask[:, None], 0.0)
            else:
                self._device_feet_air_time = None
        if self._device_last_contacts is not None:
            expected = (batch_size, len(self.foot_body_ids))
            if (
                tuple(self._device_last_contacts.shape) == expected
                and self._device_last_contacts.device == qvel.device
            ):
                self._device_last_contacts.masked_fill_(mask[:, None], False)
            else:
                self._device_last_contacts = None
        if self._device_elapsed is not None:
            if (
                tuple(self._device_elapsed.shape) == (batch_size,)
                and self._device_elapsed.device == qvel.device
            ):
                self._device_elapsed.masked_fill_(mask, 0)
            else:
                self._device_elapsed = None
        if self._device_command_steps is None or self._device_command_steps.shape != (batch_size,):
            self._device_command_steps = np.zeros(batch_size, dtype=np.int32)
        host_mask = (
            selection.host_mask
            if selection is not None
            else np.asarray(mask.detach().to("cpu"), dtype=np.bool_)
        )
        self._device_command_steps[host_mask] = 0
        # Host command metadata and the matching selected device rows were
        # updated by ``on_reset_sample()`` immediately before this hook.

    def reset(self, snapshot: RuntimeSnapshot | None = None, *, state: TaskStateView | None = None, reset_mask: np.ndarray | None = None):
        del snapshot
        if state is not None and as_task_state_view(state).is_batch:
            view = as_task_state_view(state)
            mask = np.ones(view.batch_size, dtype=np.bool_) if reset_mask is None else np.asarray(reset_mask, dtype=np.bool_)
            if mask.shape != (view.batch_size,):
                raise ValueError("Go2 reset_mask must have shape (B,)")
            if self._last_actions is None or self._last_actions.shape != (view.batch_size, 12):
                self._last_actions = np.zeros((view.batch_size, 12), dtype=np.float32)
            if self._last_dof_vel is None or self._last_dof_vel.shape != (view.batch_size, 12):
                self._last_dof_vel = np.zeros((view.batch_size, 12), dtype=np.float32)
            if self._commands is None or self._commands.shape != (
                view.batch_size,
                self.command_dim,
            ):
                self._commands = np.zeros(
                    (view.batch_size, self.command_dim), dtype=np.float32
                )
            if self._headings is None or self._headings.shape != (view.batch_size,):
                self._headings = np.zeros(view.batch_size, dtype=np.float32)
            if self._heading_enabled is None or self._heading_enabled.shape != (view.batch_size,):
                self._heading_enabled = np.zeros(view.batch_size, dtype=np.bool_)
            if self._feet_air_time is None or self._feet_air_time.shape != (view.batch_size, len(self.foot_body_ids)):
                self._feet_air_time = np.zeros((view.batch_size, len(self.foot_body_ids)), dtype=np.float32)
            if self._last_contacts is None or self._last_contacts.shape != (view.batch_size, len(self.foot_body_ids)):
                self._last_contacts = np.zeros((view.batch_size, len(self.foot_body_ids)), dtype=np.bool_)
            self._last_actions[mask] = 0.0
            self._last_dof_vel[mask] = np.asarray(view.qvel)[mask][:, self.joint_dof_ids]
            self._feet_air_time[mask] = 0.0
            self._last_contacts[mask] = False
            # Keep device semantic state for untouched worlds.  A masked
            # autoreset is allowed to cross the host reset-sampler boundary,
            # but it must not erase another slot's previous-action, contact,
            # or horizon history.
            device_cache_present = any(
                value is not None
                for value in (
                    self._device_last_actions,
                    self._device_last_dof_vel,
                    self._device_feet_air_time,
                    self._device_last_contacts,
                    self._device_elapsed,
                )
            )
            torch = None
            if device_cache_present:
                import torch as torch_module

                torch = torch_module
            if torch is not None and self._device_last_actions is not None and tuple(self._device_last_actions.shape) == (view.batch_size, 12):
                selected_device = torch.as_tensor(mask, device=self._device_last_actions.device)
                self._device_last_actions[selected_device] = 0.0
            else:
                self._device_last_actions = None
            if torch is not None and self._device_last_dof_vel is not None and tuple(self._device_last_dof_vel.shape) == (view.batch_size, 12):
                selected_device = torch.as_tensor(mask, device=self._device_last_dof_vel.device)
                reset_vel = torch.as_tensor(
                    np.asarray(view.qvel)[..., self.joint_dof_ids],
                    dtype=self._device_last_dof_vel.dtype,
                    device=self._device_last_dof_vel.device,
                )
                self._device_last_dof_vel[selected_device] = reset_vel[selected_device]
            else:
                self._device_last_dof_vel = None
            if torch is not None and self._device_feet_air_time is not None and tuple(self._device_feet_air_time.shape) == (view.batch_size, len(self.foot_body_ids)):
                selected_device = torch.as_tensor(mask, device=self._device_feet_air_time.device)
                self._device_feet_air_time[selected_device] = 0.0
            else:
                self._device_feet_air_time = None
            if torch is not None and self._device_last_contacts is not None and tuple(self._device_last_contacts.shape) == (view.batch_size, len(self.foot_body_ids)):
                selected_device = torch.as_tensor(mask, device=self._device_last_contacts.device)
                self._device_last_contacts[selected_device] = False
            else:
                self._device_last_contacts = None
            if torch is not None and self._device_elapsed is not None and tuple(self._device_elapsed.shape) == (view.batch_size,):
                selected_device = torch.as_tensor(mask, device=self._device_elapsed.device)
                self._device_elapsed[selected_device] = 0
            else:
                self._device_elapsed = None
            if self._device_command_steps is None or self._device_command_steps.shape != (view.batch_size,):
                self._device_command_steps = np.zeros(view.batch_size, dtype=np.int32)
            self._device_command_steps[mask] = 0
            # Commands are rebuilt from the complete host command array, so
            # selected slots receive the new sampler values while untouched
            # slots retain their existing commands.
            self._device_commands = None
            self._device_headings = None
            return TaskBatchEvaluation(reward=np.zeros(view.batch_size, dtype=np.float32), success=np.zeros(view.batch_size, dtype=np.bool_), failure=np.zeros(view.batch_size, dtype=np.bool_), truncated=np.zeros(view.batch_size, dtype=np.bool_))
        self._last_actions = np.zeros(12, dtype=np.float32)
        self._last_dof_vel = np.asarray(as_task_state_view(state).qvel, dtype=np.float32)[self.joint_dof_ids] if state is not None else np.zeros(12, dtype=np.float32)
        if self._commands is None or np.asarray(self._commands).shape != (
            self.command_dim,
        ):
            self._commands = np.zeros(self.command_dim, dtype=np.float32)
        self._headings = None
        self._heading_enabled = None
        self._feet_air_time = np.zeros(len(self.foot_body_ids), dtype=np.float32)
        self._last_contacts = np.zeros(len(self.foot_body_ids), dtype=np.bool_)
        self._device_last_actions = None
        self._device_last_dof_vel = None
        self._device_commands = None
        self._device_headings = None
        self._device_heading_enabled = None
        self._device_feet_air_time = None
        self._device_last_contacts = None
        self._device_elapsed = None
        self._device_command_steps = None
        return TaskEvaluation(reward=0.0, success=False)

    def evaluate(self, *, state: TaskStateView, action: np.ndarray, elapsed_steps: int | np.ndarray, previous_state: TaskStateView | None = None):
        del previous_state
        view = as_task_state_view(state)
        value = np.asarray(action, dtype=np.float32)
        qpos = np.asarray(view.qpos, dtype=np.float32)
        qvel = np.asarray(view.qvel, dtype=np.float32)
        _, lin, ang, gravity = _base_kinematics(qpos, qvel, view.body_xpos, self.base_body_id)
        roll, pitch = _base_roll_pitch(qpos, view.body_xquat, self.base_body_id)
        contact_ground = self._contact_field(view, "ground_contact_active")
        contact_body = self._contact_field(view, "body_contact_active")
        contact_geom = self._contact_field(view, "ground_contact_geom")
        if view.is_batch:
            if value.shape != (view.batch_size, 12):
                raise ValueError("Go2 batch action must have shape (B, 12)")
            self._maybe_resample_commands(elapsed_steps, view.batch_size)
            self._update_heading_commands(qpos, view.body_xquat)
            commands = self._commands
            if commands is None or commands.shape != (view.batch_size, self.command_dim):
                commands = np.zeros((view.batch_size, self.command_dim), dtype=np.float32)
            previous = np.zeros_like(value) if self._last_actions is None else self._last_actions
            previous_vel = np.zeros((view.batch_size, 12), dtype=np.float32) if self._last_dof_vel is None else self._last_dof_vel
            torque = self._compute_torque(value, qpos, qvel)
            reward, terms = self._reward(
                lin, ang, gravity, torque, value, previous, qpos, qvel,
                commands, previous_vel, contact_ground, contact_body, contact_geom,
                base_height=self._base_height(view), roll=roll, pitch=pitch,
                foot_positions=self._reward_foot_positions(view),
            )
            self._last_actions = value.copy()
            self._last_dof_vel = qvel[:, self.joint_dof_ids].copy()
            base_contact = self._body_contact(contact_ground, contact_body, self.base_body_id, (view.batch_size,))
            elapsed = np.asarray(elapsed_steps, dtype=np.int32)
            raw_fall = (np.abs(roll) > GO2_TERMINATION_ANGLE) | (
                np.abs(pitch) > GO2_TERMINATION_ANGLE
            )
            fall = raw_fall & (
                elapsed >= int(self.termination_grace_steps)
            )
            failure = np.logical_or(fall, base_contact)
            return TaskBatchEvaluation(
                reward=reward,
                success=np.zeros(view.batch_size, dtype=np.bool_),
                failure=failure,
                truncated=elapsed >= GO2_HORIZON,
                metrics={
                    "base_height": self._base_height(view),
                    "roll": roll,
                    "pitch": pitch,
                    "fall": fall,
                    "base_contact": base_contact,
                },
                reward_terms=terms,
            )
        if value.shape != (12,):
            raise ValueError("Go2 action must have shape (12,)")
        commands = np.zeros(self.command_dim, dtype=np.float32) if self._commands is None else self._commands
        self._update_heading_commands(qpos, view.body_xquat)
        commands = np.zeros(self.command_dim, dtype=np.float32) if self._commands is None else self._commands
        previous = np.zeros(12, dtype=np.float32) if self._last_actions is None else self._last_actions
        previous_vel = np.zeros(12, dtype=np.float32) if self._last_dof_vel is None else self._last_dof_vel
        torque = self._compute_torque(value, qpos, qvel)
        reward, terms = self._reward(
            lin, ang, gravity, torque, value, previous, qpos, qvel,
            commands, previous_vel, contact_ground, contact_body, contact_geom,
            base_height=self._base_height(view), roll=roll, pitch=pitch,
            foot_positions=self._reward_foot_positions(view),
        )
        self._last_actions = value.copy()
        self._last_dof_vel = qvel[self.joint_dof_ids].copy()
        raw_fall = bool(
            abs(float(roll)) > GO2_TERMINATION_ANGLE
            or abs(float(pitch)) > GO2_TERMINATION_ANGLE
        )
        elapsed_value = int(np.asarray(elapsed_steps).reshape(-1)[0])
        fall = raw_fall and elapsed_value >= int(self.termination_grace_steps)
        base_contact = bool(self._body_contact(contact_ground, contact_body, self.base_body_id, ())[()])
        return TaskEvaluation(
            reward=float(reward),
            success=False,
            failure=fall or base_contact,
            metrics={
                "base_height": float(self._base_height(view)),
                "roll": float(roll),
                "pitch": float(pitch),
                "fall": fall,
                "base_contact": base_contact,
            },
            reward_terms={name: float(item) for name, item in terms.items()},
        )

    def _compute_torque(self, action, qpos, qvel):
        target = GO2_DEFAULT_JOINT_ANGLES + 0.25 * np.asarray(action, dtype=np.float32)
        torque = GO2_KP * (target - np.asarray(qpos)[..., self.joint_qpos_ids]) - GO2_KD * np.asarray(qvel)[..., self.joint_dof_ids]
        low = self.ctrl_range[self.actuator_ids, 0]
        high = self.ctrl_range[self.actuator_ids, 1]
        return np.clip(torque, low, high).astype(np.float32)

    def _base_height(self, view):
        if view.body_xpos is not None:
            return np.asarray(view.body_xpos)[..., self.base_body_id, 2]
        return np.asarray(view.qpos)[..., 2]

    def _reward(
        self,
        lin,
        ang,
        gravity,
        torque,
        action,
        previous,
        qpos,
        qvel,
        commands,
        previous_vel,
        contact_ground,
        contact_body,
        contact_geom=None,
        *,
        base_height=None,
        roll=None,
        pitch=None,
        foot_positions=None,
    ):
        del foot_positions
        lin = np.asarray(lin, dtype=np.float32)
        ang = np.asarray(ang, dtype=np.float32)
        torque = np.asarray(torque, dtype=np.float32)
        shape = torque.shape[:-1]
        if roll is None or pitch is None:
            derived_roll, derived_pitch = _base_roll_pitch(
                np.asarray(qpos, dtype=np.float32), None, self.base_body_id
            )
            if roll is None:
                roll = derived_roll
            if pitch is None:
                pitch = derived_pitch
        roll = np.asarray(roll, dtype=np.float32)
        pitch = np.asarray(pitch, dtype=np.float32)
        dof_pos = np.asarray(qpos, dtype=np.float32)[..., self.joint_qpos_ids]
        dof_vel = np.asarray(qvel, dtype=np.float32)[..., self.joint_dof_ids]
        commands = np.asarray(commands, dtype=np.float32)
        terms = {
            "tracking_lin_vel": np.exp(-np.sum((commands[..., :2] - lin[..., :2]) ** 2, axis=-1) / 0.25) * GO2_POLICY_DT,
            "tracking_ang_vel": np.exp(-((commands[..., 2] - ang[..., 2]) ** 2) / 0.25) * 0.5 * GO2_POLICY_DT,
            "lin_vel_z": -2.0 * lin[..., 2] ** 2 * GO2_POLICY_DT,
            "ang_vel_xy": -0.05 * np.sum(ang[..., :2] ** 2, axis=-1) * GO2_POLICY_DT,
            "torques": -0.0002 * np.sum(torque ** 2, axis=-1) * GO2_POLICY_DT,
            "dof_pos_limits": -10.0 * self._dof_pos_limit_penalty(dof_pos) * GO2_POLICY_DT,
            "dof_acc": -2.5e-7 * np.sum(((np.asarray(previous_vel) - dof_vel) / GO2_POLICY_DT) ** 2, axis=-1) * GO2_POLICY_DT,
            "action_rate": -0.01 * np.sum((np.asarray(previous) - action) ** 2, axis=-1) * GO2_POLICY_DT,
            "orientation": -(
                np.float32(self.roll_orientation_weight) * np.square(roll)
                + np.float32(self.pitch_orientation_weight) * np.square(pitch)
            ) * np.float32(GO2_POLICY_DT),
        }
        if self.height_command_enabled:
            if base_height is None:
                raise ValueError("height-enabled Go2 reward requires base_height")
            target = (
                commands[..., 3]
                if commands.shape[-1] >= 4
                else np.full(
                    np.asarray(base_height).shape,
                    self.height_target_default,
                    dtype=np.float32,
                )
            )
            height_error = np.clip(
                np.abs(np.asarray(base_height, dtype=np.float32) - target),
                0.0,
                float(self.height_error_tolerance),
            ).astype(np.float32)
            terms["base_height_command"] = np.float32(
                self.height_reward_scale
            ) * (1.0 - height_error / np.float32(self.height_error_tolerance))
        contact_matrix = self._contact_matrix(
            contact_ground, contact_body,
            body_ids=np.concatenate((self.foot_body_ids, self.penalized_body_ids)),
            shape=shape,
        )
        geom_matrix = self._geom_contact_matrix(
            contact_geom, geom_ids=self.foot_geom_ids, shape=shape
        )
        feet_contact = geom_matrix if geom_matrix is not None else contact_matrix[..., self.foot_body_ids]
        if self._feet_air_time is None or self._feet_air_time.shape != feet_contact.shape:
            self._feet_air_time = np.zeros_like(feet_contact, dtype=np.float32)
            self._last_contacts = np.zeros_like(feet_contact, dtype=np.bool_)
        previous_contacts = np.zeros_like(feet_contact, dtype=np.bool_) if self._last_contacts is None else self._last_contacts
        contact_filt = np.logical_or(feet_contact, previous_contacts)
        first_contact = np.logical_and(self._feet_air_time > 0.0, contact_filt)
        self._feet_air_time += GO2_POLICY_DT
        air_reward = np.sum((self._feet_air_time - 0.5) * first_contact, axis=-1)
        air_reward *= np.linalg.norm(commands[..., :2], axis=-1) > 0.1
        self._feet_air_time *= np.logical_not(contact_filt)
        self._last_contacts = feet_contact.copy()
        terms["feet_air_time"] = air_reward.astype(np.float32) * GO2_POLICY_DT
        penalized_geom_matrix = self._geom_contact_matrix(
            contact_geom, geom_ids=self.penalized_geom_ids, shape=shape
        )
        collision_source = (
            penalized_geom_matrix
            if penalized_geom_matrix is not None
            else contact_matrix[..., self.penalized_body_ids]
        )
        collision = np.sum(collision_source.astype(np.float32), axis=-1)
        terms["collision"] = -collision.astype(np.float32) * GO2_POLICY_DT
        total = np.maximum(np.sum(np.stack(tuple(terms.values()), axis=0), axis=0), 0.0).astype(np.float32)
        return total, terms

    def _reward_foot_positions(self, view: TaskStateView):
        """Optional task-owned foot position view for specialized rewards."""

        del view
        return None

    @staticmethod
    def _contact_field(view: TaskStateView, name: str) -> np.ndarray | None:
        try:
            return np.asarray(view.get(name))
        except KeyError:
            return None

    @staticmethod
    def _body_contact(ground: np.ndarray | None, body: np.ndarray | None, body_ids, shape) -> np.ndarray:
        matrix = Go2WalkTaskDefinition._contact_matrix(
            ground, body, body_ids=body_ids, shape=shape
        )
        ids = np.asarray(body_ids, dtype=np.int32).reshape(-1)
        if ids.size == 0 or matrix.shape[-1] == 0:
            return np.zeros(tuple(shape), dtype=np.bool_)
        valid = ids[ids < matrix.shape[-1]]
        if valid.size == 0:
            return np.zeros(tuple(shape), dtype=np.bool_)
        return np.any(matrix[..., valid], axis=-1)

    @staticmethod
    def _contact_matrix(
        ground: np.ndarray | None,
        body: np.ndarray | None,
        *,
        body_ids,
        shape,
    ) -> np.ndarray:
        """Preserve body-local contact identity for per-foot rewards."""

        ids = np.asarray(body_ids, dtype=np.int32).reshape(-1)
        width = int(ids.max()) + 1 if ids.size else 0
        values: list[np.ndarray] = []
        for field in (ground, body):
            if field is None:
                continue
            value = np.asarray(field, dtype=np.bool_)
            if value.ndim not in (1, 2):
                raise ValueError("Go2 contact fields must be one- or two-dimensional")
            width = max(width, int(value.shape[-1]))
            values.append(value)
        if len(tuple(shape)) == 0:
            result = np.zeros(width, dtype=np.bool_)
        else:
            result = np.zeros(tuple(shape) + (width,), dtype=np.bool_)
        for value in values:
            if value.ndim == 1:
                result = np.logical_or(result, value[:width])
            else:
                result = np.logical_or(result, value[..., :width])
        return result

    @staticmethod
    def _geom_contact_matrix(contact_geom, *, geom_ids, shape):
        """Map optional local contact slots to selected geometry identities."""

        if contact_geom is None:
            return None
        values = np.asarray(contact_geom)
        ids = np.asarray(geom_ids, dtype=np.int32).reshape(-1)
        if values.ndim == 0 or ids.size == 0:
            return np.zeros(tuple(shape) + (ids.size,), dtype=np.bool_)
        if values.ndim == 1:
            values = values[None, :]
        result = np.stack(
            [np.any(values == int(geom_id), axis=-1) for geom_id in ids], axis=-1
        )
        if tuple(shape) == ():
            return result[0]
        if result.shape[:-1] != tuple(shape):
            raise ValueError(
                f"contact geometry slots must have leading shape {tuple(shape)}, got {result.shape[:-1]}"
            )
        return result

    def _dof_pos_limit_penalty(self, dof_pos: np.ndarray) -> np.ndarray:
        ranges = np.asarray(self.joint_range, dtype=np.float32)
        midpoint = 0.5 * (ranges[:, 0] + ranges[:, 1])
        half = 0.5 * (ranges[:, 1] - ranges[:, 0]) * 0.9
        low = midpoint - half
        high = midpoint + half
        return np.sum(np.maximum(low - dof_pos, 0.0) + np.maximum(dof_pos - high, 0.0), axis=-1)

    def _maybe_resample_commands(self, elapsed_steps, batch_size: int) -> None:
        elapsed = np.asarray(elapsed_steps, dtype=np.int32).reshape(-1)
        if elapsed.size == 0 or not np.any(elapsed % GO2_COMMAND_RESAMPLE_STEPS == 0):
            return
        if self._commands is None or self._commands.shape != (batch_size, self.command_dim):
            self._commands = np.zeros((batch_size, self.command_dim), dtype=np.float32)
        if self._headings is None or self._headings.shape != (batch_size,):
            self._headings = np.zeros(batch_size, dtype=np.float32)
        if self._heading_enabled is None or self._heading_enabled.shape != (batch_size,):
            self._heading_enabled = np.zeros(batch_size, dtype=np.bool_)
        for slot in np.flatnonzero(elapsed % GO2_COMMAND_RESAMPLE_STEPS == 0):
            self._commands[int(slot)] = self._sample_task_command(self._command_rng)
            if self.heading_command_enabled:
                self._commands[int(slot), 2] = 0.0
                self._headings[int(slot)] = np.float32(self._command_rng.uniform(-np.pi, np.pi))
                self._heading_enabled[int(slot)] = True
            else:
                # Keep the sampled third channel as the direct yaw-rate (wz)
                # command; no hidden target heading is maintained.
                self._headings[int(slot)] = 0.0
                self._heading_enabled[int(slot)] = False
        self._device_commands = None
        self._device_headings = None
        self._device_heading_enabled = None

    def _update_heading_commands(self, qpos: np.ndarray, body_xquat: np.ndarray | None) -> None:
        if self._heading_enabled is None or not np.any(self._heading_enabled):
            return
        values = np.asarray(body_xquat, dtype=np.float32) if body_xquat is not None else np.asarray(qpos, dtype=np.float32)[..., 3:7]
        if values.ndim == 3:
            quat = values[..., self.base_body_id, :]
        elif values.ndim == 2 and values.shape[-1] == 4:
            quat = values
        else:
            quat = values[3:7]
        w, x, y, z = [quat[..., index] for index in range(4)]
        current_heading = np.arctan2(2.0 * (x * y + w * z), 1.0 - 2.0 * (y * y + z * z))
        target = np.asarray(self._headings, dtype=np.float32)
        wrapped = np.arctan2(np.sin(target - current_heading), np.cos(target - current_heading))
        command = np.clip(0.5 * wrapped, -1.0, 1.0).astype(np.float32)
        if np.asarray(self._commands).ndim == 2:
            self._commands[self._heading_enabled, 2] = command[self._heading_enabled]
        else:
            if bool(np.asarray(self._heading_enabled).reshape(-1)[0]):
                self._commands[2] = command

    @staticmethod
    def _sample_command(rng: np.random.Generator) -> np.ndarray:
        command = np.asarray([rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0)], dtype=np.float32)
        if float(np.linalg.norm(command[:2])) <= 0.2:
            command[:2] = 0.0
        return command

    def _sample_task_command(self, rng: np.random.Generator) -> np.ndarray:
        command = self._sample_command(rng)
        if self.command_dim == 3:
            return command
        if self.command_dim == 4:
            return np.concatenate(
                (
                    command,
                    np.asarray(
                        (rng.uniform(GO2_HEIGHT_COMMAND_MIN, GO2_HEIGHT_COMMAND_MAX),),
                        dtype=np.float32,
                    ),
                )
            )
        raise ValueError(f"unsupported Go2 command width: {self.command_dim}")


class Go2WalkResetSampler:
    heading_command_enabled = True

    def __init__(self) -> None:
        self._domain_randomization = Go2DomainRandomizationConfig()
        self._domain_horizon = GO2_HORIZON
        self._domain_policy_dt = GO2_POLICY_DT
        self._domain_randomization_progress = 0.0

    def configure(self, *, runtime_config, num_envs: int, horizon: int) -> None:
        del num_envs
        self._domain_randomization = Go2DomainRandomizationConfig.from_runtime_config(
            runtime_config
        )
        self._domain_horizon = int(horizon)
        self._domain_policy_dt = GO2_POLICY_DT
        self._domain_randomization_progress = 0.0

    def set_domain_randomization_progress(self, progress: float) -> None:
        """Set the normalized policy-tick progress used at the next reset."""

        value = float(progress)
        if not np.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("domain randomization progress must be a finite fraction in [0, 1]")
        self._domain_randomization_progress = value

    def sample_episode_state(self, *, compiled_scene, initial_state, rng, seed):
        del seed
        qpos = np.asarray(initial_state.qpos, dtype=np.float32).copy()
        qvel = np.asarray(initial_state.qvel, dtype=np.float32).copy()
        ctrl = np.asarray(initial_state.ctrl, dtype=np.float32).copy()
        act = np.asarray(initial_state.act, dtype=np.float32).copy()
        refs = compiled_scene.references.agents["go2-v1"]
        qpos[:7] = np.asarray((0.0, 0.0, 0.42, 1.0, 0.0, 0.0, 0.0), dtype=np.float32)
        # Genesis zeroes the full generalized velocity on reset.  Keep the
        # domain-randomized friction/mass schedule, but do not randomize the
        # reset root velocity distribution.
        qvel[:] = 0.0
        for qpos_id, default in zip(refs.arm_qpos_ids, GO2_DEFAULT_JOINT_ANGLES, strict=True):
            qpos[int(qpos_id)] = np.float32(default)
        qvel[6:] = 0.0
        ctrl.fill(0.0)
        act.fill(0.0)
        # Legacy go2-walk uses a hidden target heading.  Deploy samplers
        # override this flag and expose the third channel as direct wz.
        command = Go2WalkTaskDefinition._sample_command(rng)
        parameters = {
            "profile": "unitree_rl_gym_go2_reset_v1",
            "root_position": [0.0, 0.0, 0.42],
            "root_velocity_range": [0.0, 0.0],
            "joint_random_scale": [1.0, 1.0],
            "command": command.tolist(),
        }
        if self.heading_command_enabled:
            command[2] = 0.0
            parameters["command"] = command.tolist()
            parameters["heading"] = float(rng.uniform(-np.pi, np.pi))
        if self._domain_randomization.enabled:
            parameters["world_randomization"] = (
                self._domain_randomization.sample_payload(
                    rng=rng,
                    horizon=self._domain_horizon,
                    policy_dt=self._domain_policy_dt,
                    progress=self._domain_randomization_progress,
                )
            )
        return (
            EpisodePhysicsState(
                qpos=qpos,
                qvel=qvel,
                qacc=np.zeros_like(qvel),
                ctrl=ctrl,
                act=act,
            ),
            parameters,
        )


@register_parallel_env()
@register_env()
class Go2WalkEnv(BaseTaskEnv):
    uid = GO2_ENV_ID
    task_uid = GO2_ENV_ID
    scene_uid = GO2_SCENE_UID
    agent_uids = ("go2-v1",)
    object_uids: tuple[str, ...] = ()
    success_definition = "go2_walk_no_terminal_success_v1"

    @classmethod
    def default_config(cls):
        return resolve_env_config(
            task_uid=cls.task_uid,
            scene_uid=cls.scene_uid,
            agent_uids=cls.agent_uids,
            runtime={
                "physics_dt": GO2_PHYSICS_DT,
                "control_substeps": GO2_CONTROL_SUBSTEPS,
                "batch_physics_layout": "static_template",
                "static_template": {
                    "profile": "articulated_fused_ground_contact_v1",
                    "kinematics_backend": "taichi",
                    "contact_precision": "f32",
                    "cuda_graph": True,
                    "contact": {
                        "response_backend": "active_slot_cholesky_f32_v1",
                    },
                },
                "enable_ground_contact": True,
                "enable_domain_boundary_contact": False,
                "world_randomization": {"profile": "disabled"},
            },
            action={"rsl_action_profile": "unitree_go2_reference"},
            observation={
                "schema_version": GO2_OBS_SCHEMA_VERSION,
                "include_privileged_state": False,
            },
            episode={"horizon": GO2_HORIZON},
            success_definition=cls.success_definition,
        )

    def placement_notes(self) -> tuple[str, ...]:
        return ("Go2 uses the unitree_rl_gym 12-joint order and 48-value blind policy observation.", "Ground contact is part of the compiled scene; static-template support is capability-gated.")

    def reference_profile(self) -> dict[str, Any]:
        return {"profile_id": "task-env-go2-walk-reference-v1", "source": "asset/external/mujoco_menagerie/unitree_go2/go2.xml", "canonical_xml_sha256": canonical_xml_digest(), "observation_schema": GO2_OBS_SCHEMA_VERSION, "observation_dim": 48, "action_schema": GO2_ACTION_CONTRACT.schema_id, "action_dim": 12, "physics": {"physics_dt": GO2_PHYSICS_DT, "control_substeps": GO2_CONTROL_SUBSTEPS, "policy_dt": GO2_POLICY_DT}}

    def create_scene_composer(self):
        return Go2WalkSceneComposer()

    def create_reset_sampler(self):
        return Go2WalkResetSampler()

    def create_task_definition(self, compiled_scene):
        refs = compiled_scene.references.agents["go2-v1"]
        joint_data = compiled_scene.scene_model.joint_data
        joint_range = np.asarray(joint_data.get("jnt_range"), dtype=np.float32)[refs.arm_joint_ids]
        body_names = compiled_scene.references.names.bodies
        foot_body_ids = np.asarray(
            [body_names[name] for name in ("FL_calf", "FR_calf", "RL_calf", "RR_calf")],
            dtype=np.int32,
        )
        penalized_body_ids = np.asarray(
            [
                body_names[name]
                for name in (
                    "FL_thigh", "FR_thigh", "RL_thigh", "RR_thigh",
                    "FL_calf", "FR_calf", "RL_calf", "RR_calf",
                )
            ],
            dtype=np.int32,
        )
        geom_names = dict(compiled_scene.references.names.geoms)
        foot_geom_ids = np.asarray(
            [geom_names[name] for name in ("FL", "FR", "RL", "RR")],
            dtype=np.int32,
        )
        geom_bodyid = np.asarray(joint_data.get("geom_bodyid"), dtype=np.int32)
        foot_geom_set = set(int(value) for value in foot_geom_ids)
        penalized_body_set = set(int(value) for value in penalized_body_ids)
        penalized_geom_ids = np.asarray(
            [
                geom_id
                for geom_id, body_id in enumerate(geom_bodyid)
                if int(body_id) in penalized_body_set and geom_id not in foot_geom_set
            ],
            dtype=np.int32,
        )
        return Go2WalkTaskDefinition(
            joint_qpos_ids=refs.arm_qpos_ids,
            joint_dof_ids=refs.arm_dof_ids,
            actuator_ids=refs.arm_actuator_ids,
            ctrl_range=refs.ctrl_range,
            base_body_id=refs.base_body_id,
            joint_range=joint_range,
            foot_body_ids=foot_body_ids,
            penalized_body_ids=penalized_body_ids,
            foot_geom_ids=foot_geom_ids,
            penalized_geom_ids=penalized_geom_ids,
        )


__all__ = ["Go2WalkEnv", "Go2WalkResetSampler", "Go2WalkTaskDefinition"]
