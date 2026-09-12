"""Stage 12b single-environment two-wheel balance task."""

from __future__ import annotations

from dataclasses import dataclass
import math
from collections.abc import Mapping
from typing import Any

import numpy as np
from gymnasium.spaces import Box, Dict

from ..environment import (
    EpisodePhysicsState,
    ObservationFieldSpec,
    ObservationSchema,
    RuntimeSnapshot,
    TaskBatchEvaluation,
    TaskStateView,
    TaskEvaluation,
    as_task_state_view,
    freeze_observation,
)
from ..environment.configuration import resolve_env_config
from ..environment.task_definition import TaskDefinitionBase
from ..registry import register_env
from ..vectorization.registry import register_parallel_env
from ..robots.two_wheel_balance import (
    TWO_WHEEL_ACTION_CONTRACT,
    TWO_WHEEL_TORQUE_LIMIT_NM,
    TwoWheelTorqueActionAdapter,
)
from .base import BaseTaskEnv


TWO_WHEEL_BALANCE_ENV_ID = "two-wheel-balance-v1"
TWO_WHEEL_BALANCE_TASK_UID = TWO_WHEEL_BALANCE_ENV_ID
TWO_WHEEL_BALANCE_SCENE_UID = TWO_WHEEL_BALANCE_ENV_ID
TWO_WHEEL_BALANCE_SUCCESS_DEFINITION = "two_wheel_upright_hold_v1"
TWO_WHEEL_BALANCE_STATE_SCHEMA_VERSION = "task-env-two-wheel-balance-state-v1"
TWO_WHEEL_BALANCE_PHYSICS_DT = 0.002
TWO_WHEEL_BALANCE_CONTROL_SUBSTEPS = 25
TWO_WHEEL_BALANCE_HORIZON = 400
TWO_WHEEL_UPRIGHT_PITCH_RAD = 0.12
TWO_WHEEL_UPRIGHT_PITCH_RATE_RAD_S = 1.0
TWO_WHEEL_UPRIGHT_WHEEL_RATE_RAD_S = 8.0
TWO_WHEEL_UPRIGHT_WINDOW_STEPS = 10
TWO_WHEEL_FALL_PITCH_RAD = 0.75
TWO_WHEEL_REFERENCE_PROFILE_ID = "task-env-two-wheel-balance-reference-v1"


TWO_WHEEL_BALANCE_MJCF_XML = """
<mujoco model="task_env_two_wheel_balance">
  <compiler angle="radian"/>
  <option timestep="0.002" gravity="0 0 -9.81" integrator="implicitfast"/>
  <worldbody>
    <body name="balance_anchor" pos="0 0 0">
      <geom name="balance_anchor_geom" type="cylinder" size="0.06 0.02"
            mass="0" rgba="0.28 0.28 0.32 1"/>
      <body name="balance_chassis" pos="0 0 0">
        <joint name="chassis_pitch" type="hinge" axis="0 1 0"
               damping="0.04"/>
        <inertial pos="0 0 0.45" mass="2.0"
                  diaginertia="0.20 0.20 0.20"/>
        <geom name="balance_chassis_geom" type="box" pos="0 0 0.45"
              size="0.18 0.10 0.45" mass="0"
              rgba="0.20 0.48 0.78 1"/>
        <body name="left_wheel" pos="-0.22 0 0">
          <joint name="left_wheel_hinge" type="hinge" axis="0 1 0"
                 damping="0.01"/>
          <inertial pos="0 0 0" mass="0.25"
                    diaginertia="0.01 0.01 0.01"/>
          <geom name="left_wheel_geom" type="cylinder" size="0.12 0.045"
                mass="0" rgba="0.08 0.08 0.10 1"/>
        </body>
        <body name="right_wheel" pos="0.22 0 0">
          <joint name="right_wheel_hinge" type="hinge" axis="0 1 0"
                 damping="0.01"/>
          <inertial pos="0 0 0" mass="0.25"
                    diaginertia="0.01 0.01 0.01"/>
          <geom name="right_wheel_geom" type="cylinder" size="0.12 0.045"
                mass="0" rgba="0.08 0.08 0.10 1"/>
        </body>
      </body>
    </body>
  </worldbody>
  <contact>
    <exclude body1="balance_anchor" body2="balance_chassis"/>
    <exclude body1="balance_chassis" body2="left_wheel"/>
    <exclude body1="balance_chassis" body2="right_wheel"/>
    <exclude body1="left_wheel" body2="right_wheel"/>
  </contact>
  <actuator>
    <motor name="left_wheel_torque" joint="left_wheel_hinge"
           gear="1" ctrllimited="true" ctrlrange="-1.5 1.5"/>
    <motor name="right_wheel_torque" joint="right_wheel_hinge"
           gear="1" ctrllimited="true" ctrlrange="-1.5 1.5"/>
  </actuator>
</mujoco>
""".strip()


def _wrap_angle(angle: float) -> float:
    return float((float(angle) + math.pi) % (2.0 * math.pi) - math.pi)


def _balance_state(
    snapshot: RuntimeSnapshot,
    *,
    pitch_qpos_id: int,
    pitch_qvel_id: int,
    left_qpos_id: int,
    left_qvel_id: int,
    right_qpos_id: int,
    right_qvel_id: int,
) -> tuple[float, float, float, float, float, float]:
    if (
        snapshot.qpos.shape[0] <= max(pitch_qpos_id, left_qpos_id, right_qpos_id)
        or snapshot.qvel.shape[0] <= max(pitch_qvel_id, left_qvel_id, right_qvel_id)
    ):
        raise ValueError("Two-wheel snapshot does not contain the declared joint state")
    return (
        _wrap_angle(snapshot.qpos[pitch_qpos_id]),
        float(snapshot.qvel[pitch_qvel_id]),
        float(snapshot.qpos[left_qpos_id]),
        float(snapshot.qvel[left_qvel_id]),
        float(snapshot.qpos[right_qpos_id]),
        float(snapshot.qvel[right_qvel_id]),
    )


class TwoWheelBalanceObservationBuilder:
    """Versioned flat state: pitch, pitch rate, and both wheel states."""

    def __init__(self, *, joint_ids: dict[str, tuple[int, int]]) -> None:
        self._ids = dict(joint_ids)
        self.observation_space = Dict(
            {
                "state": Dict(
                    {
                        "proprioception": Box(
                            low=-np.inf,
                            high=np.inf,
                            shape=(7,),
                            dtype=np.float32,
                        )
                    }
                )
            }
        )
        self._schema = ObservationSchema(
            version=TWO_WHEEL_BALANCE_STATE_SCHEMA_VERSION,
            fields=(
                ObservationFieldSpec(
                    name="state.proprioception",
                    shape=(7,),
                    dtype="float32",
                    semantic=(
                        "sin(pitch), cos(pitch), pitch_rate, left_wheel_position, "
                        "right_wheel_position, left_wheel_rate, right_wheel_rate"
                    ),
                ),
            ),
            groups=("state",),
        )

    @property
    def schema(self) -> ObservationSchema:
        return self._schema

    def build(self, snapshot: RuntimeSnapshot, sensor_observation=None) -> np.ndarray:
        del sensor_observation
        pitch, pitch_rate, left_pos, left_rate, right_pos, right_rate = _balance_state(
            snapshot,
            pitch_qpos_id=self._ids["pitch"][0],
            pitch_qvel_id=self._ids["pitch"][1],
            left_qpos_id=self._ids["left"][0],
            left_qvel_id=self._ids["left"][1],
            right_qpos_id=self._ids["right"][0],
            right_qvel_id=self._ids["right"][1],
        )
        return freeze_observation(
            (
                (
                    "state",
                    {
                        "proprioception": np.asarray(
                            (
                                math.sin(pitch),
                                math.cos(pitch),
                                pitch_rate,
                                left_pos,
                                right_pos,
                                left_rate,
                                right_rate,
                            ),
                            dtype=np.float32,
                        ),
                    },
                ),
            )
        )


@dataclass
class TwoWheelBalanceTaskDefinition(TaskDefinitionBase):
    uses_unified_state_view = True

    pitch_qpos_id: int
    pitch_qvel_id: int
    left_qpos_id: int
    left_qvel_id: int
    right_qpos_id: int
    right_qvel_id: int
    upright_pitch_rad: float = TWO_WHEEL_UPRIGHT_PITCH_RAD
    upright_pitch_rate_rad_s: float = TWO_WHEEL_UPRIGHT_PITCH_RATE_RAD_S
    upright_wheel_rate_rad_s: float = TWO_WHEEL_UPRIGHT_WHEEL_RATE_RAD_S
    fall_pitch_rad: float = TWO_WHEEL_FALL_PITCH_RAD
    success_window_steps: int = TWO_WHEEL_UPRIGHT_WINDOW_STEPS

    def __post_init__(self) -> None:
        if self.upright_pitch_rad <= 0.0 or self.fall_pitch_rad <= self.upright_pitch_rad:
            raise ValueError("Two-wheel pitch thresholds must be positive and ordered")
        if self.success_window_steps < 1:
            raise ValueError("Two-wheel success window must be positive")
        self._upright_steps = 0

    def create_action_adapter(self, compiled_scene):
        names = compiled_scene.references.names.actuators
        joint_data = compiled_scene.scene_model.joint_data
        return TwoWheelTorqueActionAdapter(
            actuator_ids=(names["left_wheel_torque"], names["right_wheel_torque"]),
            actuator_count=int(joint_data["n_actuators"]),
        )

    def create_observation_builder(self, compiled_scene, **_kwargs):
        del compiled_scene
        return TwoWheelBalanceObservationBuilder(
            joint_ids={
                "pitch": (self.pitch_qpos_id, self.pitch_qvel_id),
                "left": (self.left_qpos_id, self.left_qvel_id),
                "right": (self.right_qpos_id, self.right_qvel_id),
            }
        )

    def build_observation(
        self,
        state: TaskStateView,
        *,
        sensor_observation: Any | None = None,
    ) -> Any:
        del sensor_observation
        view = as_task_state_view(state)
        qpos = np.asarray(view.qpos, dtype=np.float32)
        qvel = np.asarray(view.qvel, dtype=np.float32)
        pitch = (
            (qpos[:, self.pitch_qpos_id] + math.pi) % (2.0 * math.pi) - math.pi
            if view.is_batch
            else _wrap_angle(qpos[self.pitch_qpos_id])
        )
        pitch_rate = qvel[:, self.pitch_qvel_id] if view.is_batch else float(qvel[self.pitch_qvel_id])
        left_pos = qpos[:, self.left_qpos_id] if view.is_batch else float(qpos[self.left_qpos_id])
        right_pos = qpos[:, self.right_qpos_id] if view.is_batch else float(qpos[self.right_qpos_id])
        left_rate = qvel[:, self.left_qvel_id] if view.is_batch else float(qvel[self.left_qvel_id])
        right_rate = qvel[:, self.right_qvel_id] if view.is_batch else float(qvel[self.right_qvel_id])
        if view.is_batch:
            proprioception = np.stack(
                (
                    np.sin(pitch),
                    np.cos(pitch),
                    pitch_rate,
                    left_pos,
                    right_pos,
                    left_rate,
                    right_rate,
                ),
                axis=1,
            ).astype(np.float32, copy=False)
            return {"state": {"proprioception": proprioception}}
        return freeze_observation(
            (
                (
                    "state",
                    {
                        "proprioception": np.asarray(
                            (
                                math.sin(pitch),
                                math.cos(pitch),
                                pitch_rate,
                                left_pos,
                                right_pos,
                                left_rate,
                                right_rate,
                            ),
                            dtype=np.float32,
                        )
                    },
                ),
            )
        )

    def _ensure_batch_private_state(self, batch_size: int) -> None:
        if np.isscalar(self._upright_steps):
            self._upright_steps = np.zeros(batch_size, dtype=np.int32)
        elif np.asarray(self._upright_steps).shape != (batch_size,):
            raise ValueError("Two-wheel private batch state has the wrong batch size")

    def _coerce_action(self, action, *, batch_size: int | None) -> np.ndarray:
        if isinstance(action, Mapping):
            if tuple(action.keys()) != ("torque",):
                raise ValueError("Two-wheel action tree must contain only torque")
            action = action["torque"]
        value = np.asarray(action, dtype=np.float32)
        expected = (2,) if batch_size is None else (batch_size, 2)
        if value.shape != expected:
            raise ValueError(f"Two-wheel action must have shape {expected}, got {value.shape}")
        if not np.isfinite(value).all() or np.any(
            value < -TWO_WHEEL_TORQUE_LIMIT_NM
        ) or np.any(value > TWO_WHEEL_TORQUE_LIMIT_NM):
            raise ValueError("Two-wheel torque action is outside the declared bounds")
        return value

    def reset(
        self,
        snapshot: RuntimeSnapshot | TaskStateView | None = None,
        *,
        state: TaskStateView | None = None,
        reset_mask: np.ndarray | None = None,
    ) -> TaskEvaluation | TaskBatchEvaluation:
        if state is None:
            if snapshot is None:
                raise TypeError("Two-wheel reset requires state")
            state = as_task_state_view(snapshot)
        view = as_task_state_view(state)
        if view.is_batch:
            mask = (
                np.ones(view.batch_size, dtype=np.bool_)
                if reset_mask is None
                else np.asarray(reset_mask, dtype=np.bool_)
            )
            if mask.shape != (view.batch_size,):
                raise ValueError("Two-wheel reset_mask must have shape (B,)")
            self._ensure_batch_private_state(view.batch_size)
            self._upright_steps[mask] = 0
            return TaskBatchEvaluation(
                reward=np.zeros(view.batch_size, dtype=np.float32),
                success=np.zeros(view.batch_size, dtype=np.bool_),
                failure=np.zeros(view.batch_size, dtype=np.bool_),
                truncated=np.zeros(view.batch_size, dtype=np.bool_),
            )
        self._upright_steps = 0
        return self._evaluate_scalar_view(
            view,
            torque=np.zeros(2, dtype=np.float32),
            update_window=False,
        )

    def evaluate(
        self,
        *legacy_args,
        state: TaskStateView | None = None,
        action=None,
        elapsed_steps: int | np.ndarray | None = None,
        previous_state: TaskStateView | None = None,
    ) -> TaskEvaluation | TaskBatchEvaluation:
        if state is None:
            if len(legacy_args) != 3:
                raise TypeError(
                    "Two-wheel evaluate requires state/action/elapsed_steps or "
                    "(previous_snapshot, action, current_snapshot)"
                )
            del previous_state
            _previous_snapshot, action, current_snapshot = legacy_args
            state = as_task_state_view(current_snapshot)
            elapsed_steps = 0 if elapsed_steps is None else elapsed_steps
        elif legacy_args:
            raise TypeError("Two-wheel evaluate cannot mix legacy and unified arguments")
        view = as_task_state_view(state)
        if view.is_batch:
            if elapsed_steps is None:
                raise TypeError("batch Two-wheel evaluate requires elapsed_steps")
            return self._evaluate_batch(
                view,
                action=action,
                elapsed_steps=np.asarray(elapsed_steps, dtype=np.int32),
            )
        torque = self._coerce_action(action, batch_size=None)
        return self._evaluate_scalar_view(view, torque=torque, update_window=True)

    def _evaluate_scalar_view(
        self,
        state: TaskStateView,
        *,
        torque: np.ndarray,
        update_window: bool,
    ) -> TaskEvaluation:
        qpos = np.asarray(state.qpos, dtype=np.float32).reshape(-1)
        qvel = np.asarray(state.qvel, dtype=np.float32).reshape(-1)
        ids = (self.pitch_qpos_id, self.left_qpos_id, self.right_qpos_id)
        dofs = (self.pitch_qvel_id, self.left_qvel_id, self.right_qvel_id)
        if qpos.size <= max(ids) or qvel.size <= max(dofs):
            raise ValueError("Two-wheel state does not contain the declared joint state")
        pitch = _wrap_angle(qpos[self.pitch_qpos_id])
        pitch_rate = float(qvel[self.pitch_qvel_id])
        left_rate = float(qvel[self.left_qvel_id])
        right_rate = float(qvel[self.right_qvel_id])
        wheel_rate = max(abs(left_rate), abs(right_rate))
        upright = (
            abs(pitch) <= self.upright_pitch_rad
            and abs(pitch_rate) <= self.upright_pitch_rate_rad_s
            and wheel_rate <= self.upright_wheel_rate_rad_s
        )
        failure = abs(pitch) >= self.fall_pitch_rad
        if update_window:
            self._upright_steps = self._upright_steps + 1 if upright else 0
        success = self._upright_steps >= self.success_window_steps
        reward_terms = {
            "upright": math.cos(pitch),
            "pitch_rate_cost": -0.02 * pitch_rate * pitch_rate,
            "wheel_rate_cost": -0.002 * (left_rate * left_rate + right_rate * right_rate),
            "torque_cost": -0.0005 * float(np.dot(torque, torque)),
            "success": 1.0 if success else 0.0,
        }
        return TaskEvaluation(
            reward=sum(reward_terms.values()),
            success=success,
            failure=failure,
            metrics={
                "pitch_rad": pitch,
                "pitch_rate_rad_s": pitch_rate,
                "left_wheel_rate_rad_s": left_rate,
                "right_wheel_rate_rad_s": right_rate,
                "upright": upright,
                "upright_steps": self._upright_steps,
                "task_success": success,
                "task_failure": failure,
            },
            reward_terms=reward_terms,
        )

    def _evaluate_batch(
        self,
        state: TaskStateView,
        *,
        action,
        elapsed_steps: np.ndarray,
    ) -> TaskBatchEvaluation:
        qpos = np.asarray(state.qpos, dtype=np.float32)
        qvel = np.asarray(state.qvel, dtype=np.float32)
        if qpos.ndim != 2 or qvel.ndim != 2:
            raise ValueError("Two-wheel batch state arrays must have leading batch dimensions")
        torque = self._coerce_action(action, batch_size=state.batch_size)
        self._ensure_batch_private_state(state.batch_size)
        pitch = (qpos[:, self.pitch_qpos_id] + math.pi) % (2.0 * math.pi) - math.pi
        pitch_rate = qvel[:, self.pitch_qvel_id]
        left_rate = qvel[:, self.left_qvel_id]
        right_rate = qvel[:, self.right_qvel_id]
        wheel_rate = np.maximum(np.abs(left_rate), np.abs(right_rate))
        upright = (
            (np.abs(pitch) <= self.upright_pitch_rad)
            & (np.abs(pitch_rate) <= self.upright_pitch_rate_rad_s)
            & (wheel_rate <= self.upright_wheel_rate_rad_s)
        )
        failure = np.abs(pitch) >= self.fall_pitch_rad
        self._upright_steps = np.where(
            upright,
            self._upright_steps + 1,
            0,
        ).astype(np.int32)
        success = self._upright_steps >= self.success_window_steps
        reward_terms = {
            "upright": np.cos(pitch).astype(np.float32),
            "pitch_rate_cost": (-0.02 * pitch_rate * pitch_rate).astype(np.float32),
            "wheel_rate_cost": (-0.002 * (left_rate * left_rate + right_rate * right_rate)).astype(np.float32),
            "torque_cost": (-0.0005 * np.sum(torque * torque, axis=1)).astype(np.float32),
            "success": success.astype(np.float32),
        }
        reward = np.sum(np.stack(tuple(reward_terms.values()), axis=0), axis=0).astype(np.float32)
        return TaskBatchEvaluation(
            reward=reward,
            success=success.astype(np.bool_),
            failure=failure.astype(np.bool_),
            truncated=np.zeros(state.batch_size, dtype=np.bool_),
            metrics={
                "pitch_rad": pitch.astype(np.float32),
                "pitch_rate_rad_s": pitch_rate.astype(np.float32),
                "left_wheel_rate_rad_s": left_rate.astype(np.float32),
                "right_wheel_rate_rad_s": right_rate.astype(np.float32),
                "upright": upright.astype(np.bool_),
                "upright_steps": self._upright_steps.copy(),
                "task_success": success.astype(np.bool_),
                "task_failure": failure.astype(np.bool_),
                "elapsed_steps": np.asarray(elapsed_steps, dtype=np.int32),
            },
            reward_terms=reward_terms,
        )


class TwoWheelBalanceResetSampler:
    """Replayable initial pitch and wheel-rate perturbation."""

    def sample_episode_state(
        self,
        *,
        compiled_scene: object,
        initial_state: EpisodePhysicsState,
        rng: np.random.Generator,
        seed: int | None,
    ) -> tuple[EpisodePhysicsState, dict[str, Any]]:
        del seed
        joint_data = compiled_scene.scene_model.joint_data
        names = compiled_scene.references.names.joints
        pitch_joint = names["chassis_pitch"]
        left_joint = names["left_wheel_hinge"]
        right_joint = names["right_wheel_hinge"]
        qpos_adr = np.asarray(joint_data["jnt_qposadr"], dtype=np.int32)
        dof_adr = np.asarray(joint_data["jnt_dofadr"], dtype=np.int32)
        qpos = np.asarray(initial_state.qpos, dtype=np.float32).copy()
        qvel = np.asarray(initial_state.qvel, dtype=np.float32).copy()
        ctrl = np.asarray(initial_state.ctrl, dtype=np.float32).copy()
        act = np.asarray(initial_state.act, dtype=np.float32).copy()
        pitch = float(rng.uniform(-0.08, 0.08))
        pitch_rate = float(rng.uniform(-0.20, 0.20))
        left_position = float(rng.uniform(-0.02, 0.02))
        right_position = float(rng.uniform(-0.02, 0.02))
        left_rate = float(rng.uniform(-0.30, 0.30))
        right_rate = float(rng.uniform(-0.30, 0.30))
        qpos[qpos_adr[pitch_joint]] = np.float32(pitch)
        qpos[qpos_adr[left_joint]] = np.float32(left_position)
        qpos[qpos_adr[right_joint]] = np.float32(right_position)
        qvel[dof_adr[pitch_joint]] = np.float32(pitch_rate)
        qvel[dof_adr[left_joint]] = np.float32(left_rate)
        qvel[dof_adr[right_joint]] = np.float32(right_rate)
        ctrl.fill(0.0)
        act.fill(0.0)
        return (
            EpisodePhysicsState(
                qpos=qpos,
                qvel=qvel,
                qacc=np.zeros_like(qvel),
                ctrl=ctrl,
                act=act,
            ),
            {
                "profile": "two_wheel_balance_uniform_perturbation_v1",
                "pitch_range_rad": [-0.08, 0.08],
                "pitch_rate_range_rad_s": [-0.20, 0.20],
                "wheel_position_range_rad": [-0.02, 0.02],
                "wheel_rate_range_rad_s": [-0.30, 0.30],
                "pitch_rad": pitch,
                "pitch_rate_rad_s": pitch_rate,
                "left_wheel_position_rad": left_position,
                "right_wheel_position_rad": right_position,
                "left_wheel_rate_rad_s": left_rate,
                "right_wheel_rate_rad_s": right_rate,
            },
        )


class _TwoWheelBalanceSceneComposer:
    def build_scene_source(self, composition, agents):
        del composition
        if tuple(agents):
            raise ValueError("Two-wheel balance scene must not receive robot agents")
        from scene import SceneSource

        return (
            SceneSource.mjcf_string(
                TWO_WHEEL_BALANCE_MJCF_XML,
                label="task-env-two-wheel-balance-inline-v1",
            ),
            "two_wheel_balance_inline_v1",
        )


@register_parallel_env()
@register_env()
class TwoWheelBalanceEnv(BaseTaskEnv):
    """GeoPhys-native articulated two-wheel balance environment."""

    uid = TWO_WHEEL_BALANCE_ENV_ID
    task_uid = TWO_WHEEL_BALANCE_TASK_UID
    scene_uid = TWO_WHEEL_BALANCE_SCENE_UID
    agent_uids: tuple[str, ...] = ()
    object_uids: tuple[str, ...] = ()
    success_definition = TWO_WHEEL_BALANCE_SUCCESS_DEFINITION

    @classmethod
    def default_config(cls):
        return resolve_env_config(
            task_uid=cls.task_uid,
            scene_uid=cls.scene_uid,
            success_definition=cls.success_definition,
            runtime={
                "physics_dt": TWO_WHEEL_BALANCE_PHYSICS_DT,
                "control_substeps": TWO_WHEEL_BALANCE_CONTROL_SUBSTEPS,
            },
            observation={
                "schema_version": TWO_WHEEL_BALANCE_STATE_SCHEMA_VERSION,
                "include_privileged_state": False,
            },
            episode={"horizon": TWO_WHEEL_BALANCE_HORIZON},
        )

    def placement_notes(self) -> tuple[str, ...]:
        return (
            "Two-wheel balance is a fixed-anchor articulated chassis with two independent wheel hinges.",
            "Native action is left/right direct wheel torque; no robot controller is bound.",
        )

    def reference_profile(self) -> dict[str, Any]:
        return {
            "profile_id": TWO_WHEEL_REFERENCE_PROFILE_ID,
            "asset": {
                "source": "inline_mjcf",
                "label": "task-env-two-wheel-balance-inline-v1",
                "topology": "fixed_anchor_chassis_with_two_wheel_hinges",
            },
            "frame": {
                "pitch_zero": "upright",
                "positive_direction": "right_hand_about_+y",
                "wrap": "[-pi, pi)",
            },
            "physics": {
                "gravity": [0.0, 0.0, -9.81],
                "integrator": "implicitfast",
                "physics_dt": TWO_WHEEL_BALANCE_PHYSICS_DT,
                "control_substeps": TWO_WHEEL_BALANCE_CONTROL_SUBSTEPS,
            },
            "action": {
                "schema_id": "task-env.two-wheel-balance.wheel-torque.v1",
                "order": ["left_wheel_torque", "right_wheel_torque"],
                "unit": "N*m",
                "bounds": [-1.5, 1.5],
            },
            "observation": {
                "schema_id": TWO_WHEEL_BALANCE_STATE_SCHEMA_VERSION,
                "order": [
                    "sin(pitch)",
                    "cos(pitch)",
                    "pitch_rate",
                    "left_wheel_position",
                    "right_wheel_position",
                    "left_wheel_rate",
                    "right_wheel_rate",
                ],
                "dtype": "float32",
            },
            "reset": {
                "sampler": "uniform",
                "pitch_rad": [-0.08, 0.08],
                "pitch_rate_rad_s": [-0.20, 0.20],
                "wheel_position_rad": [-0.02, 0.02],
                "wheel_rate_rad_s": [-0.30, 0.30],
            },
            "termination": {
                "success_definition": TWO_WHEEL_BALANCE_SUCCESS_DEFINITION,
                "success_window_steps": TWO_WHEEL_UPRIGHT_WINDOW_STEPS,
                "upright_pitch_rad": TWO_WHEEL_UPRIGHT_PITCH_RAD,
                "fall_pitch_rad": TWO_WHEEL_FALL_PITCH_RAD,
                "success_terminates": True,
                "failure_terminates": True,
                "horizon": TWO_WHEEL_BALANCE_HORIZON,
                "horizon_is_truncated": True,
            },
        }

    def create_scene_composer(self):
        return _TwoWheelBalanceSceneComposer()

    def create_reset_sampler(self):
        return TwoWheelBalanceResetSampler()

    def create_task_definition(self, compiled_scene):
        names = compiled_scene.references.names.joints
        joint_data = compiled_scene.scene_model.joint_data
        qpos_adr = np.asarray(joint_data["jnt_qposadr"], dtype=np.int32)
        dof_adr = np.asarray(joint_data["jnt_dofadr"], dtype=np.int32)
        return TwoWheelBalanceTaskDefinition(
            pitch_qpos_id=int(qpos_adr[names["chassis_pitch"]]),
            pitch_qvel_id=int(dof_adr[names["chassis_pitch"]]),
            left_qpos_id=int(qpos_adr[names["left_wheel_hinge"]]),
            left_qvel_id=int(dof_adr[names["left_wheel_hinge"]]),
            right_qpos_id=int(qpos_adr[names["right_wheel_hinge"]]),
            right_qvel_id=int(dof_adr[names["right_wheel_hinge"]]),
        )


__all__ = [
    "TWO_WHEEL_BALANCE_ENV_ID",
    "TWO_WHEEL_BALANCE_MJCF_XML",
    "TWO_WHEEL_REFERENCE_PROFILE_ID",
    "TWO_WHEEL_BALANCE_STATE_SCHEMA_VERSION",
    "TWO_WHEEL_BALANCE_TASK_UID",
    "TwoWheelBalanceEnv",
]
