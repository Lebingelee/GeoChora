"""Stage 12a Pendulum swing-up TaskEnv."""

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
from ..robots.pendulum import (
    PENDULUM_ACTION_CONTRACT,
    PendulumTorqueActionAdapter,
)
from .base import BaseTaskEnv


PENDULUM_ENV_ID = "pendulum-v1"
PENDULUM_TASK_UID = PENDULUM_ENV_ID
PENDULUM_SCENE_UID = PENDULUM_ENV_ID
PENDULUM_SUCCESS_DEFINITION = "pendulum_upright_hold_v1"
PENDULUM_STATE_SCHEMA_VERSION = "task-env-pendulum-state-v1"
PENDULUM_PHYSICS_DT = 0.002
PENDULUM_CONTROL_SUBSTEPS = 25
PENDULUM_HORIZON = 200
PENDULUM_UPRIGHT_ANGLE_RAD = 0.15
PENDULUM_UPRIGHT_ANGULAR_VELOCITY = 0.50
PENDULUM_SUCCESS_WINDOW_STEPS = 5

PENDULUM_REFERENCE_PROFILE_ID = "task-env-pendulum-reference-v1"


# The asset is intentionally inline for the first non-arm TaskEnv.  It keeps
# the exact reference scene local to the versioned task while still going
# through GeoPhys's normal MJCF import and rigid runtime boundary.
PENDULUM_MJCF_XML = """
<mujoco model="task_env_pendulum">
  <compiler angle="radian"/>
  <option timestep="0.002" gravity="0 0 -9.81" integrator="implicitfast"/>
  <worldbody>
    <body name="pendulum_anchor" pos="0 0 0">
      <geom name="pendulum_anchor_geom" type="cylinder" size="0.08 0.03"
            mass="0" rgba="0.30 0.30 0.34 1"/>
      <body name="pendulum_link" pos="0 0 0">
        <joint name="pendulum_hinge" type="hinge" axis="0 1 0"
               damping="0.05"/>
        <inertial pos="0 0 0.25" mass="1.0"
                  diaginertia="0.05 0.05 0.05"/>
        <geom name="pendulum_link_geom" type="capsule"
              fromto="0 0 0 0 0 0.50" size="0.04"
              density="1000" rgba="0.16 0.46 0.82 1"/>
      </body>
    </body>
  </worldbody>
  <contact>
    <exclude body1="pendulum_anchor" body2="pendulum_link"/>
  </contact>
  <actuator>
    <motor name="pendulum_torque" joint="pendulum_hinge"
           gear="1" ctrllimited="true" ctrlrange="-2 2"/>
  </actuator>
</mujoco>
""".strip()


def _wrap_angle(angle: float) -> float:
    return float((float(angle) + math.pi) % (2.0 * math.pi) - math.pi)


def _pendulum_state(snapshot: RuntimeSnapshot, *, qpos_id: int, qvel_id: int) -> tuple[float, float]:
    if snapshot.qpos.shape[0] <= qpos_id or snapshot.qvel.shape[0] <= qvel_id:
        raise ValueError("Pendulum snapshot does not contain the hinge state")
    return _wrap_angle(snapshot.qpos[qpos_id]), float(snapshot.qvel[qvel_id])


@dataclass(frozen=True)
class PendulumTaskSemantics:
    """Scalar/batch shared source of Pendulum task meaning."""

    upright_angle_rad: float = PENDULUM_UPRIGHT_ANGLE_RAD
    upright_angular_velocity: float = PENDULUM_UPRIGHT_ANGULAR_VELOCITY
    success_window_steps: int = PENDULUM_SUCCESS_WINDOW_STEPS
    horizon: int = PENDULUM_HORIZON
    torque_limit: float = float(PENDULUM_ACTION_CONTRACT.high)

    def __post_init__(self) -> None:
        if self.upright_angle_rad <= 0.0 or self.upright_angular_velocity <= 0.0:
            raise ValueError("Pendulum upright thresholds must be positive")
        if self.success_window_steps < 1 or self.horizon < 1:
            raise ValueError("Pendulum success window and horizon must be positive")

    @staticmethod
    def observation_one(theta: float, theta_dot: float) -> np.ndarray:
        return np.asarray(
            (math.cos(float(theta)), math.sin(float(theta)), float(theta_dot)),
            dtype=np.float32,
        )

    def observation(self, theta: np.ndarray, theta_dot: np.ndarray) -> np.ndarray:
        theta_value = np.asarray(theta, dtype=np.float32)
        theta_dot_value = np.asarray(theta_dot, dtype=np.float32)
        if theta_value.shape != theta_dot_value.shape or theta_value.ndim != 1:
            raise ValueError("Pendulum batch state arrays must both have shape (B,)")
        return np.stack(
            (
                np.cos(theta_value),
                np.sin(theta_value),
                theta_dot_value,
            ),
            axis=1,
        ).astype(np.float32, copy=False)

    def sample_reset(
        self,
        rng: np.random.Generator,
        *,
        size: int | None = None,
    ) -> tuple[np.ndarray | np.float32, np.ndarray | np.float32]:
        if size is None:
            return (
                np.float32(rng.uniform(-math.pi, math.pi)),
                np.float32(rng.uniform(-1.0, 1.0)),
            )
        return (
            rng.uniform(-math.pi, math.pi, size=int(size)).astype(np.float32),
            rng.uniform(-1.0, 1.0, size=int(size)).astype(np.float32),
        )

    def validate_torque(self, torque: np.ndarray) -> None:
        value = np.asarray(torque, dtype=np.float32)
        if not np.isfinite(value).all() or np.any(np.abs(value) > self.torque_limit):
            raise ValueError(
                f"Pendulum torque must be finite and within "
                f"[-{self.torque_limit:g}, {self.torque_limit:g}]"
            )

    def _is_upright(self, theta: float, theta_dot: float) -> bool:
        return (
            abs(float(theta)) <= self.upright_angle_rad
            and abs(float(theta_dot)) <= self.upright_angular_velocity
        )

    def evaluate_one(
        self,
        *,
        theta: float,
        theta_dot: float,
        torque: float,
        upright_steps: int,
        elapsed_steps: int | None = None,
        update_window: bool,
    ) -> tuple[TaskEvaluation, int]:
        upright = self._is_upright(theta, theta_dot)
        next_upright_steps = (
            (int(upright_steps) + 1) if upright else 0
        ) if update_window else 0
        success = next_upright_steps >= self.success_window_steps
        reward_terms = {
            "upright": math.cos(float(theta)),
            "angular_velocity_cost": -0.10 * float(theta_dot) ** 2,
            "torque_cost": -0.001 * float(torque) ** 2,
            "success": 1.0 if success else 0.0,
        }
        metrics = {
            "theta_rad": float(theta),
            "theta_dot_rad_s": float(theta_dot),
            "upright": upright,
            "upright_steps": next_upright_steps,
            "task_success": success,
        }
        if elapsed_steps is not None:
            metrics["elapsed_steps"] = int(elapsed_steps)
        return (
            TaskEvaluation(
                reward=sum(reward_terms.values()),
                success=success,
                failure=False,
                metrics=metrics,
                reward_terms=reward_terms,
            ),
            next_upright_steps,
        )

    def evaluate_arrays(
        self,
        *,
        theta: np.ndarray,
        theta_dot: np.ndarray,
        torque: np.ndarray,
        upright_steps: np.ndarray,
        elapsed_steps: np.ndarray,
        update_window: bool = True,
    ) -> tuple[
        np.ndarray,
        np.ndarray,
        np.ndarray,
        np.ndarray,
        dict[str, np.ndarray],
        dict[str, np.ndarray],
    ]:
        theta_value = np.asarray(theta, dtype=np.float32)
        theta_dot_value = np.asarray(theta_dot, dtype=np.float32)
        torque_value = np.asarray(torque, dtype=np.float32).reshape(-1)
        old_upright = np.asarray(upright_steps, dtype=np.int32)
        elapsed = np.asarray(elapsed_steps, dtype=np.int32)
        if not (
            theta_value.shape == theta_dot_value.shape == torque_value.shape == old_upright.shape == elapsed.shape
        ):
            raise ValueError("Pendulum batch semantic arrays must share shape (B,)")
        upright = (
            np.abs(theta_value) <= self.upright_angle_rad
        ) & (np.abs(theta_dot_value) <= self.upright_angular_velocity)
        next_upright = (
            np.where(upright, old_upright + 1, 0).astype(np.int32)
            if update_window
            else np.zeros_like(old_upright)
        )
        success = next_upright >= self.success_window_steps
        truncated = elapsed >= self.horizon
        reward_terms = {
            "upright": np.cos(theta_value).astype(np.float32),
            "angular_velocity_cost": (-0.10 * theta_dot_value * theta_dot_value).astype(np.float32),
            "torque_cost": (-0.001 * torque_value * torque_value).astype(np.float32),
            "success": success.astype(np.float32),
        }
        reward = np.sum(np.stack(tuple(reward_terms.values()), axis=0), axis=0).astype(np.float32)
        metrics = {
            "theta_rad": theta_value.copy(),
            "theta_dot_rad_s": theta_dot_value.copy(),
            "upright": upright.copy(),
            "upright_steps": next_upright.copy(),
            "task_success": success.copy(),
            "elapsed_steps": elapsed.copy(),
        }
        return reward, success.astype(np.bool_), truncated.astype(np.bool_), next_upright, metrics, reward_terms


PENDULUM_TASK_SEMANTICS = PendulumTaskSemantics()


class PendulumObservationBuilder:
    """State-only Box observation with a versioned metadata schema."""

    def __init__(self, *, qpos_id: int, qvel_id: int) -> None:
        self._qpos_id = int(qpos_id)
        self._qvel_id = int(qvel_id)
        self.observation_space = Dict(
            {
                "state": Dict(
                    {
                        "proprioception": Box(
                            low=-np.inf,
                            high=np.inf,
                            shape=(3,),
                            dtype=np.float32,
                        )
                    }
                )
            }
        )
        self._schema = ObservationSchema(
            version=PENDULUM_STATE_SCHEMA_VERSION,
            fields=(
                ObservationFieldSpec(
                    name="state.proprioception",
                    shape=(3,),
                    dtype="float32",
                    semantic="cos(theta), sin(theta), theta_dot; theta=0 is upright",
                ),
            ),
            groups=("state",),
        )

    @property
    def schema(self) -> ObservationSchema:
        return self._schema

    def build(self, snapshot: RuntimeSnapshot, sensor_observation=None) -> np.ndarray:
        del sensor_observation
        theta, theta_dot = _pendulum_state(
            snapshot,
            qpos_id=self._qpos_id,
            qvel_id=self._qvel_id,
        )
        return freeze_observation(
            (
                (
                    "state",
                    {
                        "proprioception": PENDULUM_TASK_SEMANTICS.observation_one(
                            theta, theta_dot
                        ),
                    },
                ),
            )
        )


@dataclass
class PendulumTaskDefinition(TaskDefinitionBase):
    uses_unified_state_view = True

    qpos_id: int
    qvel_id: int
    upright_angle_rad: float = PENDULUM_UPRIGHT_ANGLE_RAD
    upright_angular_velocity: float = PENDULUM_UPRIGHT_ANGULAR_VELOCITY
    success_window_steps: int = PENDULUM_SUCCESS_WINDOW_STEPS

    def __post_init__(self) -> None:
        self._semantics = PendulumTaskSemantics(
            upright_angle_rad=self.upright_angle_rad,
            upright_angular_velocity=self.upright_angular_velocity,
            success_window_steps=self.success_window_steps,
            horizon=PENDULUM_HORIZON,
        )
        self._upright_steps = 0

    def create_action_adapter(self, compiled_scene):
        names = compiled_scene.references.names
        actuator_id = names.actuators["pendulum_torque"]
        actuator_count = int(compiled_scene.scene_model.joint_data["n_actuators"])
        return PendulumTorqueActionAdapter(
            actuator_id=actuator_id,
            actuator_count=actuator_count,
        )

    def create_observation_builder(self, compiled_scene, **_kwargs):
        del compiled_scene
        return PendulumObservationBuilder(
            qpos_id=self.qpos_id,
            qvel_id=self.qvel_id,
        )

    def _coerce_action(
        self,
        action: Mapping[str, np.ndarray] | np.ndarray,
        *,
        batch_size: int | None,
    ) -> np.ndarray:
        if isinstance(action, Mapping):
            if tuple(action.keys()) != ("torque",):
                raise ValueError("Pendulum action tree must contain only torque")
            action = action["torque"]
        value = np.asarray(action, dtype=np.float32)
        expected = (1,) if batch_size is None else (batch_size, 1)
        if value.shape != expected:
            raise ValueError(f"Pendulum action must have shape {expected}, got {value.shape}")
        self._semantics.validate_torque(value)
        return value

    def build_observation(
        self,
        state: TaskStateView,
        *,
        sensor_observation: Any | None = None,
    ) -> Any:
        del sensor_observation
        view = as_task_state_view(state)
        qpos = np.asarray(view.qpos)
        qvel = np.asarray(view.qvel)
        if view.is_batch:
            theta = np.asarray(
                (qpos[:, self.qpos_id] + math.pi) % (2.0 * math.pi) - math.pi,
                dtype=np.float32,
            )
            theta_dot = np.asarray(qvel[:, self.qvel_id], dtype=np.float32)
            return {
                "state": {
                    "proprioception": self._semantics.observation(theta, theta_dot)
                }
            }
        theta = _wrap_angle(qpos[self.qpos_id])
        theta_dot = float(qvel[self.qvel_id])
        return freeze_observation(
            (
                (
                    "state",
                    {
                        "proprioception": self._semantics.observation_one(
                            theta, theta_dot
                        )
                    },
                ),
            )
        )

    def reset(
        self,
        snapshot: RuntimeSnapshot | TaskStateView | None = None,
        *,
        state: TaskStateView | None = None,
        reset_mask: np.ndarray | None = None,
    ) -> TaskEvaluation | TaskBatchEvaluation:
        if state is None:
            if snapshot is None:
                raise TypeError("Pendulum reset requires state")
            state = as_task_state_view(snapshot)
        view = as_task_state_view(state)
        if view.is_batch:
            mask = np.ones(view.batch_size, dtype=np.bool_) if reset_mask is None else np.asarray(reset_mask, dtype=np.bool_)
            if mask.shape != (view.batch_size,):
                raise ValueError("Pendulum reset_mask must have shape (B,)")
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
            torque=0.0,
            update_window=False,
        )

    def evaluate(
        self,
        *legacy_args,
        state: TaskStateView | None = None,
        action: Mapping[str, np.ndarray] | np.ndarray | None = None,
        elapsed_steps: int | np.ndarray | None = None,
        previous_state: TaskStateView | None = None,
    ) -> TaskEvaluation | TaskBatchEvaluation:
        if state is None:
            if len(legacy_args) != 3:
                raise TypeError(
                    "Pendulum evaluate requires state/action/elapsed_steps or "
                    "(previous_snapshot, action, current_snapshot)"
                )
            del previous_state
            _previous_snapshot, action, current_snapshot = legacy_args
            state = as_task_state_view(current_snapshot)
            elapsed_steps = 0 if elapsed_steps is None else elapsed_steps
        elif legacy_args:
            raise TypeError("Pendulum evaluate cannot mix legacy and unified arguments")
        view = as_task_state_view(state)
        if view.is_batch:
            if elapsed_steps is None:
                raise TypeError("batch Pendulum evaluate requires elapsed_steps")
            return self._evaluate_batch_semantics(
                state=view,
                action=action,
                elapsed_steps=np.asarray(elapsed_steps, dtype=np.int32),
                update_window=True,
            )
        torque = float(self._coerce_action(action, batch_size=None)[0])
        return self._evaluate_scalar_view(view, torque=torque, update_window=True)

    def _evaluate_scalar_view(
        self,
        state: TaskStateView,
        *,
        torque: float,
        update_window: bool,
    ) -> TaskEvaluation:
        qpos = np.asarray(state.qpos, dtype=np.float32).reshape(-1)
        qvel = np.asarray(state.qvel, dtype=np.float32).reshape(-1)
        if qpos.size <= self.qpos_id or qvel.size <= self.qvel_id:
            raise ValueError("Pendulum state does not contain the hinge state")
        theta = _wrap_angle(qpos[self.qpos_id])
        theta_dot = float(qvel[self.qvel_id])
        evaluation, next_upright_steps = self._semantics.evaluate_one(
            theta=theta,
            theta_dot=theta_dot,
            torque=torque,
            upright_steps=self._upright_steps,
            update_window=update_window,
        )
        self._upright_steps = next_upright_steps
        return evaluation

    def _ensure_batch_private_state(self, batch_size: int) -> None:
        if np.isscalar(self._upright_steps):
            self._upright_steps = np.zeros(batch_size, dtype=np.int32)
        elif np.asarray(self._upright_steps).shape != (batch_size,):
            raise ValueError("Pendulum private batch state has the wrong batch size")

    def _evaluate_batch_semantics(
        self,
        *,
        state: TaskStateView,
        action: Mapping[str, np.ndarray] | np.ndarray | None,
        elapsed_steps: np.ndarray,
        update_window: bool,
    ) -> TaskBatchEvaluation:
        qpos = np.asarray(state.qpos, dtype=np.float32)
        qvel = np.asarray(state.qvel, dtype=np.float32)
        if qpos.ndim != 2 or qvel.ndim != 2:
            raise ValueError("Pendulum batch state arrays must have leading batch dimensions")
        torque = self._coerce_action(action, batch_size=state.batch_size)[:, 0]
        self._ensure_batch_private_state(state.batch_size)
        old_upright = np.asarray(self._upright_steps, dtype=np.int32)
        elapsed = np.asarray(elapsed_steps, dtype=np.int32)
        reward, success, truncated, next_upright, metrics, reward_terms = (
            self._semantics.evaluate_arrays(
                theta=(qpos[:, self.qpos_id] + math.pi) % (2.0 * math.pi) - math.pi,
                theta_dot=qvel[:, self.qvel_id],
                torque=torque,
                upright_steps=old_upright,
                elapsed_steps=elapsed,
                update_window=update_window,
            )
        )
        self._upright_steps = next_upright
        return TaskBatchEvaluation(
            reward=reward,
            success=success,
            failure=np.zeros(state.batch_size, dtype=np.bool_),
            truncated=truncated,
            metrics=metrics,
            reward_terms=reward_terms,
        )


class PendulumResetSampler:
    """Replayable random initial state for the fixed Pendulum profile."""

    def sample_episode_state(
        self,
        *,
        compiled_scene: object,
        initial_state: EpisodePhysicsState,
        rng: np.random.Generator,
        seed: int | None,
    ) -> tuple[EpisodePhysicsState, dict[str, Any]]:
        del seed
        joint_id = compiled_scene.references.names.joints["pendulum_hinge"]
        qpos_id = int(compiled_scene.scene_model.joint_data["jnt_qposadr"][joint_id])
        dof_id = int(compiled_scene.scene_model.joint_data["jnt_dofadr"][joint_id])
        qpos = np.asarray(initial_state.qpos, dtype=np.float32).copy()
        qvel = np.asarray(initial_state.qvel, dtype=np.float32).copy()
        ctrl = np.asarray(initial_state.ctrl, dtype=np.float32).copy()
        act = np.asarray(initial_state.act, dtype=np.float32).copy()
        theta_value, theta_dot_value = PENDULUM_TASK_SEMANTICS.sample_reset(rng)
        theta = float(theta_value)
        theta_dot = float(theta_dot_value)
        qpos[qpos_id] = np.float32(theta)
        qvel[dof_id] = np.float32(theta_dot)
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
                "profile": "pendulum_uniform_angle_velocity_v1",
                "angle_range_rad": [-math.pi, math.pi],
                "angular_velocity_range_rad_s": [-1.0, 1.0],
                "theta_rad": theta,
                "theta_dot_rad_s": theta_dot,
            },
        )


class _PendulumSceneComposer:
    def build_scene_source(self, composition, agents):
        del composition
        if tuple(agents):
            raise ValueError("Pendulum scene must not receive robot agents")
        from scene import SceneSource

        return (
            SceneSource.mjcf_string(
                PENDULUM_MJCF_XML,
                label="task-env-pendulum-inline-v1",
            ),
            "pendulum_inline_v1",
        )


@register_parallel_env()
@register_env()
class PendulumEnv(BaseTaskEnv):
    """GeoPhys-native single Pendulum environment."""

    uid = PENDULUM_ENV_ID
    task_uid = PENDULUM_TASK_UID
    scene_uid = PENDULUM_SCENE_UID
    agent_uids: tuple[str, ...] = ()
    object_uids: tuple[str, ...] = ()
    success_definition = PENDULUM_SUCCESS_DEFINITION

    @classmethod
    def default_config(cls):
        return resolve_env_config(
            task_uid=cls.task_uid,
            scene_uid=cls.scene_uid,
            success_definition=cls.success_definition,
            runtime={
                "physics_dt": PENDULUM_PHYSICS_DT,
                "control_substeps": PENDULUM_CONTROL_SUBSTEPS,
            },
            observation={
                "schema_version": PENDULUM_STATE_SCHEMA_VERSION,
                "include_privileged_state": False,
            },
            episode={"horizon": PENDULUM_HORIZON},
        )

    def placement_notes(self) -> tuple[str, ...]:
        return (
            "Pendulum is an inline single-hinge MJCF topology with theta=0 upright.",
            "Native action is direct hinge torque; no robot controller is bound.",
        )

    def reference_profile(self) -> dict[str, Any]:
        return {
            "profile_id": PENDULUM_REFERENCE_PROFILE_ID,
            "asset": {
                "source": "inline_mjcf",
                "label": "task-env-pendulum-inline-v1",
                "topology": "single_hinge_pendulum",
            },
            "frame": {
                "angle_zero": "upright",
                "positive_direction": "right_hand_about_+y",
                "wrap": "[-pi, pi)",
            },
            "physics": {
                "gravity": [0.0, 0.0, -9.81],
                "integrator": "implicitfast",
                "physics_dt": PENDULUM_PHYSICS_DT,
                "control_substeps": PENDULUM_CONTROL_SUBSTEPS,
                "damping": 0.05,
                "mass": 1.0,
                "length_m": 0.50,
            },
            "action": {
                "schema_id": "task-env.pendulum.torque.v1",
                "components": ["torque"],
                "unit": "N*m",
                "bounds": [-2.0, 2.0],
            },
            "observation": {
                "schema_id": PENDULUM_STATE_SCHEMA_VERSION,
                "order": ["cos(theta)", "sin(theta)", "theta_dot"],
                "dtype": "float32",
            },
            "reset": {
                "sampler": "uniform",
                "theta_rad": [-math.pi, math.pi],
                "theta_dot_rad_s": [-1.0, 1.0],
            },
            "reward": {
                "upright": "cos(theta)",
                "angular_velocity_cost": "-0.10 * theta_dot**2",
                "torque_cost": "-0.001 * torque**2",
            },
            "termination": {
                "success_definition": PENDULUM_SUCCESS_DEFINITION,
                "success_window_steps": PENDULUM_SUCCESS_WINDOW_STEPS,
                "success_terminates": True,
                "failure": False,
                "horizon": PENDULUM_HORIZON,
                "horizon_is_truncated": True,
            },
        }

    def create_scene_composer(self):
        return _PendulumSceneComposer()

    def create_reset_sampler(self):
        return PendulumResetSampler()

    def create_task_definition(self, compiled_scene):
        joint_id = compiled_scene.references.names.joints["pendulum_hinge"]
        return PendulumTaskDefinition(
            qpos_id=int(compiled_scene.scene_model.joint_data["jnt_qposadr"][joint_id]),
            qvel_id=int(compiled_scene.scene_model.joint_data["jnt_dofadr"][joint_id]),
        )


__all__ = [
    "PENDULUM_ACTION_CONTRACT",
    "PENDULUM_CONTROL_SUBSTEPS",
    "PENDULUM_ENV_ID",
    "PENDULUM_HORIZON",
    "PENDULUM_MJCF_XML",
    "PENDULUM_REFERENCE_PROFILE_ID",
    "PENDULUM_SCENE_UID",
    "PENDULUM_STATE_SCHEMA_VERSION",
    "PENDULUM_SUCCESS_DEFINITION",
    "PENDULUM_TASK_UID",
    "PENDULUM_TASK_SEMANTICS",
    "PendulumEnv",
    "PendulumObservationBuilder",
    "PendulumTaskSemantics",
    "PendulumResetSampler",
    "PendulumTaskDefinition",
]
