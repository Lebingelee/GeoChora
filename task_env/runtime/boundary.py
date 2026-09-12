"""GeoPhys physics runtime 的唯一 TaskEnv 持有边界。"""

from __future__ import annotations

import numpy as np

from ..environment import (
    AppliedControl,
    ContactSummary,
    ControlCommand,
    EpisodePhysicsState,
    PhysicsStateSnapshot,
    RuntimeBoundary,
    RuntimeSnapshot,
    SnapshotRequest,
)


class GeoPhysRuntimeBoundary:
    """拥有 PhysicsSolver/Simulator，并只暴露 CPU 值对象。"""

    def __init__(
        self,
        *,
        physics,
        scheduler,
        physics_dt: float,
        ctrl_range,
        initial_state: EpisodePhysicsState,
    ) -> None:
        self._physics = physics
        self._scheduler = scheduler
        self._physics_dt = float(physics_dt)
        self._ctrl_range = np.asarray(ctrl_range, dtype=np.float32).copy()
        self._actuator_force_limit_overrides: dict[int, float] = {}
        self._simulation_time = 0.0
        self._baseline = {
            name: np.asarray(value).copy()
            for name, value in self._physics.snapshot().items()
        }
        self._initial_state = initial_state
        self.apply_reset_state(initial_state)
        self._baseline = {
            name: np.asarray(value).copy()
            for name, value in self._physics.snapshot().items()
        }

    @property
    def initial_state(self) -> EpisodePhysicsState:
        return self._initial_state

    def apply_reset_state(self, state: EpisodePhysicsState) -> None:
        self._physics.restore(self._baseline)
        self._apply_actuator_force_limit_overrides()
        if state.qpos.size:
            self._physics.write_qpos(state.qpos)
        if state.qvel.size:
            self._physics.write_qvel(state.qvel)
            self._physics.write_qacc(state.qacc)
        if state.ctrl.size:
            self._physics.write_ctrl(state.ctrl)
            self._physics.write_act(state.act)
        self._physics.synchronize_kinematic_state(update_site_jacobians=False)
        self._simulation_time = 0.0

    def set_actuator_force_limits(self, actuator_ids, limit_N: float) -> None:
        """Set persistent symmetric actuator force caps through TaskEnv's public boundary.

        This is an explicitly low-frequency control/configuration operation.
        Runtime action conversion never reads or writes solver fields directly;
        the boundary reapplies selected caps after every reset.
        """

        limit = float(limit_N)
        if not np.isfinite(limit) or limit < 0.0:
            raise ValueError("actuator force limit must be finite and non-negative")
        ids = np.asarray(actuator_ids, dtype=np.int32).reshape(-1)
        actuator_count = int(getattr(self._physics, "n_actuators", 0))
        if ids.size and (int(ids.min()) < 0 or int(ids.max()) >= actuator_count):
            raise ValueError("actuator force-limit ids exceed the compiled actuator range")
        for actuator_id in ids:
            self._actuator_force_limit_overrides[int(actuator_id)] = limit
        self._apply_actuator_force_limit_overrides()

    def _apply_actuator_force_limit_overrides(self) -> None:
        if not self._actuator_force_limit_overrides:
            return
        if not hasattr(self._physics, "act_forcerange_field"):
            raise StageUnavailableError("runtime physics has no actuator force-limit field")
        ranges = np.asarray(self._physics.act_forcerange_field.to_numpy(), dtype=np.float32)
        limited = np.asarray(self._physics.act_forcelimited_field.to_numpy(), dtype=np.int32)
        for actuator_id, limit in self._actuator_force_limit_overrides.items():
            ranges[actuator_id] = (-limit, limit)
            limited[actuator_id] = 1
        self._physics.act_forcerange_field.from_numpy(ranges)
        self._physics.act_forcelimited_field.from_numpy(limited)

    def apply_control(self, command: ControlCommand) -> AppliedControl:
        requested = np.asarray(command.actuator_ctrl, dtype=np.float32)
        n_actuators = int(getattr(self._physics, "n_actuators", 0))
        if requested.shape != (n_actuators,):
            raise ValueError(
                f"actuator ctrl shape must be {(n_actuators,)}, "
                f"got {requested.shape}"
            )
        applied = requested.copy()
        if self._ctrl_range.shape == (applied.size, 2):
            limited = self._ctrl_range[:, 1] > self._ctrl_range[:, 0] + 1.0e-8
            applied[limited] = np.clip(
                applied[limited],
                self._ctrl_range[limited, 0],
                self._ctrl_range[limited, 1],
            )
        if n_actuators:
            self._physics.write_ctrl(applied)
        return AppliedControl(
            requested_ctrl=requested,
            applied_ctrl=applied,
            clipped=not np.array_equal(requested, applied),
        )

    def step(self, *, substeps: int) -> None:
        if substeps < 1:
            raise ValueError("substeps must be at least 1")
        self._scheduler.step(substeps)
        self._simulation_time += self._physics_dt * int(substeps)

    def read_snapshot(self, request: SnapshotRequest) -> RuntimeSnapshot:
        n_qpos = int(getattr(self._physics, "n_qpos", 0))
        n_dof = int(getattr(self._physics, "n_dof", 0))
        n_act = int(getattr(self._physics, "n_actuators", 0))
        n_sites = int(getattr(self._physics, "n_sites", 0))
        site_jacp = None
        site_jacr = None
        if request.site_jacobians and n_sites:
            site_jacp = self._physics.read_site_jacp()
            site_jacr = self._physics.read_site_jacr()
        return RuntimeSnapshot(
            qpos=(
                self._physics.read_qpos()
                if n_qpos
                else np.zeros(0, dtype=np.float32)
            ),
            qvel=(
                self._physics.read_qvel()
                if n_dof
                else np.zeros(0, dtype=np.float32)
            ),
            qacc=(
                self._physics.read_qacc()
                if request.qacc and n_dof
                else (np.zeros(0, dtype=np.float32) if request.qacc else None)
            ),
            ctrl=(
                self._physics.read_ctrl()
                if request.ctrl and n_act
                else (np.zeros(0, dtype=np.float32) if request.ctrl else None)
            ),
            actuator_force=(
                self._physics.read_actuator_force()
                if request.actuator_force and n_act
                else (
                    np.zeros(0, dtype=np.float32)
                    if request.actuator_force
                    else None
                )
            ),
            body_xpos=self._physics.read_positions() if request.body_pose else None,
            body_xquat=(
                self._physics.read_orientations() if request.body_pose else None
            ),
            site_xpos=(
                self._physics.read_site_world_pos()
                if request.site_pose and n_sites
                else (
                    np.zeros((0, 3), dtype=np.float32)
                    if request.site_pose
                    else None
                )
            ),
            site_xquat=(
                self._physics.read_site_world_quat()
                if request.site_pose and n_sites
                else (
                    np.zeros((0, 4), dtype=np.float32)
                    if request.site_pose
                    else None
                )
            ),
            site_jacp=site_jacp,
            site_jacr=site_jacr,
            contact_summary=ContactSummary() if request.contact_summary else None,
            simulation_time=(
                self._simulation_time if request.simulation_time else None
            ),
        )

    def snapshot_state(self) -> PhysicsStateSnapshot:
        arrays = {
            name: np.asarray(value).copy()
            for name, value in self._physics.snapshot().items()
        }
        arrays["task_env_simulation_time"] = np.asarray(
            [self._simulation_time],
            dtype=np.float64,
        )
        return PhysicsStateSnapshot(arrays=arrays)

    def restore_state(self, state: PhysicsStateSnapshot) -> None:
        arrays = dict(state.arrays)
        time_array = np.asarray(
            arrays.pop("task_env_simulation_time", np.zeros(1)),
            dtype=np.float64,
        )
        self._physics.restore(arrays)
        self._simulation_time = float(time_array.reshape(-1)[0])

    def prewarm(self, profile: str = "interactive") -> None:
        self._scheduler.prewarm(profile=profile)

    def close(self) -> None:
        """Runtime resources are owned by Taichi's process-wide runtime."""


__all__ = ["GeoPhysRuntimeBoundary", "RuntimeBoundary"]
