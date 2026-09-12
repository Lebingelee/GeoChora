"""First-class TaskEnv host runtime adapter for GeoPhys BatchedRigidSolver.

This module owns only the ABI translation between the TaskEnv batch runtime
contract and one homogeneous ``BatchedRigidSolver`` block.  The solver remains
the sole owner of mutable physics state, storage, contact workspaces, and
numerical kernels.  Device state, TaskEnv randomization, and CUDA Graph
management are intentionally not implemented by this first host-only adapter.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from ....environment.types import StageUnavailableError
from ...contracts import BatchResetResult, BatchState, BatchStepResult


class GeoPhysRigidBatchRuntime:
    """TaskEnv ``BatchRuntimeProtocol`` adapter over one BRS world block."""

    # These class attributes let the legacy static-template route retain its
    # historical provenance while sharing the BRS-specific ABI implementation.
    runtime_kind = "geophys_rigid_batch"
    runtime_layout = "homogeneous_batch"
    storage_owner_key = "task_env:geophys:rigid_batch"
    render_enabled = False
    fused_world_local = True

    @classmethod
    def from_compiled_scene(
        cls,
        *,
        compiled_scene: object,
        config: object,
        num_envs: int,
        backend: str | None = None,
    ) -> "GeoPhysRigidBatchRuntime":
        """Materialize the current GeoPhys homogeneous rigid solver path."""

        from runtime import SimulationExecutionLayout
        try:
            # Keep the historical source-tree construction seam available to
            # existing callers/tests while using the canonical module export
            # in a normal GeoPhys runtime.
            from runtime import StorageOwnerRegistry
        except ImportError:
            from runtime.storage_lifecycle import StorageOwnerRegistry
        from solvers.materialization import materialize_rigid
        from solvers.rigid.config import RigidSolverConfig

        scene = getattr(compiled_scene, "scene_model", None)
        if scene is None:
            raise StageUnavailableError(
                "geophys_rigid_batch requires compiled_scene.scene_model"
            )

        runtime_config = config.runtime
        integrator = str(runtime_config.integrator).strip().lower()
        if integrator != "euler":
            raise StageUnavailableError(
                "geophys_rigid_batch requires runtime.integrator='euler'; "
                f"got {runtime_config.integrator!r}"
            )

        # The current BRS admission is deliberately narrower than the
        # articulated static-template runtime: its TaskEnv bridge does not
        # expose ground or domain-boundary rows.
        if runtime_config.enable_ground_contact is True:
            raise StageUnavailableError(
                "geophys_rigid_batch does not support TaskEnv ground contact yet"
            )
        if runtime_config.enable_domain_boundary_contact:
            raise StageUnavailableError(
                "geophys_rigid_batch does not support domain-boundary contact yet"
            )

        options: dict[str, object] = {
            "dt": float(runtime_config.physics_dt),
            "gravity": tuple(float(value) for value in runtime_config.gravity),
            "integrator": "euler",
            "enable_ground_contact": False,
            "enable_domain_boundary_contact": False,
            "broadphase": str(runtime_config.broadphase),
        }
        if runtime_config.rigid_solver_backend is not None:
            options["rigid_solver_backend"] = runtime_config.rigid_solver_backend
        if runtime_config.body_contact_solver_iterations is not None:
            options["body_contact_solver_iterations"] = (
                runtime_config.body_contact_solver_iterations
            )
        solver_config = RigidSolverConfig.from_legacy_kwargs(options)

        # The registry is owned by this runtime instance.  The source
        # materializer requires it before fields are allocated, and freezing
        # preserves the existing storage lifecycle invariant.
        registry = StorageOwnerRegistry(program_epoch=0)
        layout = SimulationExecutionLayout(
            mode="homogeneous_batch",
            world_count=int(num_envs),
        )
        solver = materialize_rigid(
            scene,
            execution_layout=layout,
            config=solver_config,
            storage_registry=registry,
            storage_owner_key=cls.storage_owner_key,
        )
        registry.binding_for(solver)
        registry.freeze()
        return cls(
            solver=solver,
            registry=registry,
            num_envs=int(num_envs),
            control_substeps=int(runtime_config.control_substeps),
            scene_model=scene if cls.render_enabled else None,
            backend=(
                str(backend)
                if backend is not None
                else str(getattr(runtime_config, "backend", "cpu"))
            ),
        )

    def __init__(
        self,
        *,
        solver: object,
        registry: object,
        num_envs: int,
        control_substeps: int,
        scene_model: object | None = None,
        backend: str = "cpu",
    ) -> None:
        if int(num_envs) < 1:
            raise ValueError("num_envs must be positive")
        if int(control_substeps) < 1:
            raise ValueError("control_substeps must be positive")
        self.solver = solver
        self.registry = registry
        self.num_envs = int(num_envs)
        self.control_substeps = int(control_substeps)
        self.backend = str(backend)
        self.positions = getattr(
            getattr(solver, "storage", None), "body_positions", None
        )
        self.orientations = getattr(
            getattr(solver, "storage", None), "body_orientations", None
        )
        self.geom_world_pos = None
        self.geom_world_quat = None
        self._geom_bodyid = np.empty(0, dtype=np.int32)
        self._geom_pos = np.empty((0, 3), dtype=np.float32)
        self._geom_quat = np.empty((0, 4), dtype=np.float32)
        if scene_model is not None:
            self._init_render_fields(scene_model)

    def reset(
        self,
        *,
        state: Mapping[str, np.ndarray],
        mask: np.ndarray,
    ) -> BatchResetResult:
        """Apply a selected batch reset and publish a host snapshot.

        The input mapping is batch-major.  Missing channels are merged from
        the current solver state, matching the existing TaskEnv host reset
        semantics; they are never silently replaced by zeros.
        """

        reset_mask = np.asarray(mask)
        if reset_mask.dtype != np.bool_:
            raise ValueError("rigid batch reset mask must have boolean dtype")
        if reset_mask.shape != (self.num_envs,):
            raise ValueError("rigid batch reset mask must have shape (B,)")
        current = self.read_state()
        values = self._normalize_state(state, current=current)
        world_ids = tuple(int(index) for index in np.flatnonzero(reset_mask))
        if world_ids:
            resetter = getattr(self.solver, "reset", None)
            if not callable(resetter):
                raise StageUnavailableError(
                    "geophys_rigid_batch solver has no public reset capability"
                )
            resetter(world_ids)
            rows = [
                {
                    "qpos": values["qpos"][world],
                    "qvel": values["qvel"][world],
                    "qacc": values["qacc"][world],
                    "ctrl": values["ctrl"][world],
                    "act_state": values["act"][world],
                }
                for world in world_ids
            ]
            self.solver.write_state(world_ids, rows)
            self.refresh()
        return BatchResetResult(state=BatchState(self.read_state()))

    def step(self, action: np.ndarray) -> BatchStepResult:
        """Validate one control batch, advance BRS substeps, and read back."""

        value = np.asarray(action, dtype=np.float32)
        expected = (self.num_envs, self._actuator_count())
        if value.shape != expected:
            raise ValueError(
                f"batch control action must have shape {expected}, got {value.shape}"
            )
        if not np.isfinite(value).all():
            raise ValueError("batch control action must be finite")
        self.write_ctrl(value)
        self.step_substeps()
        return BatchStepResult(state=BatchState(self.read_state()))

    def write_state(self, state: Mapping[str, np.ndarray]) -> None:
        """Retain the established complete-state helper for legacy callers."""

        values = self._normalize_state(state)
        rows = [
            {
                "qpos": values["qpos"][world],
                "qvel": values["qvel"][world],
                "qacc": values["qacc"][world],
                "ctrl": values["ctrl"][world],
                "act_state": values["act"][world],
            }
            for world in range(self.num_envs)
        ]
        self.solver.write_state(tuple(range(self.num_envs)), rows)

    def write_ctrl(self, control: np.ndarray) -> None:
        """Validate and forward the complete batch control field."""

        value = np.asarray(control, dtype=np.float32)
        expected = (self.num_envs, self._actuator_count())
        if value.shape != expected:
            raise ValueError(
                f"batch control action must have shape {expected}, got {value.shape}"
            )
        if not np.isfinite(value).all():
            raise ValueError("batch control action must be finite")
        if expected[1] == 0:
            return
        write_ctrl = getattr(self.solver, "write_ctrl", None)
        if not callable(write_ctrl):
            raise StageUnavailableError(
                "geophys_rigid_batch solver has no public write_ctrl capability"
            )
        write_ctrl(value)

    def step_substeps(self, substeps: int | None = None) -> None:
        """Advance the BRS by the configured number of simulation substeps."""

        count = self.control_substeps if substeps is None else int(substeps)
        if count < 1:
            raise ValueError("substeps must be positive")
        for _ in range(count):
            self.solver.step()

    def read_state(self) -> dict[str, np.ndarray]:
        """Publish a copied named host state, never solver-owned storage."""

        rows = self.solver.read_state()
        if len(rows) != self.num_envs:
            raise RuntimeError("rigid batch solver returned an unexpected world count")
        body_positions = self._stack(rows, "body_positions")
        body_orientations = self._stack(rows, "body_orientations")
        self._sync_render_geom_fields(body_positions, body_orientations)
        return {
            "qpos": self._stack(rows, "qpos"),
            "qvel": self._stack(rows, "qvel"),
            "qacc": self._stack(rows, "qacc"),
            "ctrl": self._stack(rows, "ctrl"),
            "act": self._stack(rows, "act_state"),
        }

    def refresh(self) -> None:
        """Keep the existing BRS write-state refresh boundary explicit."""

        return None

    def execution_plan_facts(self) -> Mapping[str, Any]:
        """Publish the compatibility route's immutable plan facts."""

        return {
            "max_contact_pairs_per_world": 0,
            "max_constraint_rows_per_world": 0,
            "contact_workspace_slots_per_world": 0,
            # The legacy static profile historically reported this adapter as
            # a fused world-local route; preserve that metadata while the
            # numerical owner remains GeoPhys BatchedRigidSolver.
            "fused_kernel": True,
            "execution_route": "fused_world_local",
        }

    def render_state_source(self) -> tuple[object, str]:
        """Return the provider-owned batched render state port."""

        if self.positions is not None:
            return self, "batched"
        raise RuntimeError("GeoPhys rigid batch has no renderable state owner")

    def resource_summary(self) -> dict[str, Any]:
        """Return truthful GeoPhys provenance and the host-only capability."""

        solver_name = type(self.solver).__name__
        summary = dict(self.solver.resource_summary())
        summary.update(
            {
                "kind": self.runtime_kind,
                "layout": self.runtime_layout,
                "backend": self.backend,
                "num_envs": self.num_envs,
                "runtime_adapter": type(self).__name__,
                "provider": "GeoPhys",
                "provider_identity": "GeoPhys",
                "physics_provider": "GeoPhys",
                "solver": solver_name,
                "solver_family": str(getattr(self.solver, "solver_family", "rigid")),
                "implementation": solver_name,
                "implementation_status": "src_rigid_batch_host_boundary",
                "state_exchange": "host_numpy_boundary",
                "world_randomization": {
                    "configured": False,
                    "enabled": False,
                    "schema_id": None,
                    "reference_profile": None,
                    "lifetime": None,
                    "inertia_policy": None,
                    "capabilities": {
                        "friction": False,
                        "push_schedule": False,
                        "base_mass": False,
                        "inertia_policy": [],
                    },
                    "reason": (
                        "GeoPhys BatchedRigidSolver has no exact TaskEnv "
                        "WorldRandomizationBatch realization path"
                    ),
                },
                "device_transition": {
                    "available": False,
                    "runtime_method": "step_device",
                    "zero_copy_substeps": False,
                    "field_device": None,
                    "reason": "GeoPhys BatchedRigidSolver exposes host state exchange only",
                },
                "capabilities": {
                    "reset": {
                        "host": True,
                        "masked": True,
                        "partial_state": True,
                        "post_reset_readable": True,
                    },
                    "randomization": {
                        "available": False,
                        "friction": False,
                        "base_mass": False,
                        "inertia_policy": [],
                        "push_schedule": False,
                        "selected_worlds": False,
                        "episode_lifetime": False,
                    },
                    "device": {
                        "read": False,
                        "step": False,
                        "reset": False,
                        "selection_validation": False,
                    },
                    "contact": {
                        "ground": False,
                        "contact_state": False,
                    },
                    "graph": {
                        "cuda_graph": False,
                        "enabled": False,
                    },
                    "render": {
                        "source": bool(self.render_enabled),
                        "mode": "batched" if self.render_enabled else None,
                    },
                },
            }
        )
        summary["storage_registry"] = self.registry.describe()
        return summary

    def prewarm(self) -> None:
        self.solver.prewarm()

    def close(self) -> None:
        # Taichi fields are owned by the current program and have no per-owner
        # destruction path.  The registry remains alive with the solver until
        # the runtime is released.
        return None

    def _actuator_count(self) -> int:
        return int(getattr(self.solver.storage, "n_actuators", 0))

    def _normalize_state(
        self,
        state: Mapping[str, np.ndarray],
        *,
        current: Mapping[str, np.ndarray] | None = None,
    ) -> dict[str, np.ndarray]:
        if not isinstance(state, Mapping):
            raise TypeError("rigid batch state must be a mapping")
        allowed = {"qpos", "qvel", "qacc", "ctrl", "act"}
        unknown = set(state).difference(allowed)
        if unknown:
            raise ValueError(
                f"rigid batch state contains unknown fields: {sorted(unknown)}"
            )
        counts = {
            "qpos": int(getattr(self.solver.storage, "n_qpos", 0)),
            "qvel": int(getattr(self.solver.storage, "n_dof", 0)),
            "qacc": int(getattr(self.solver.storage, "n_dof", 0)),
            "ctrl": self._actuator_count(),
            "act": self._actuator_count(),
        }
        result: dict[str, np.ndarray] = {}
        for name, width in counts.items():
            if name not in state:
                if current is None:
                    raise ValueError(
                        f"rigid batch state is missing required field {name!r}"
                    )
                value = current[name]
            else:
                value = state[name]
            array = np.asarray(value, dtype=np.float32)
            expected = (self.num_envs, width)
            if array.shape != expected:
                raise ValueError(
                    f"rigid batch state {name!r} must have shape {expected}, "
                    f"got {array.shape}"
                )
            if not np.isfinite(array).all():
                raise ValueError(f"rigid batch state {name!r} must be finite")
            result[name] = np.ascontiguousarray(array)
        return result

    def _init_render_fields(self, scene_model: object) -> None:
        """Expose legacy render fields only for the compatibility subclass."""

        import taichi as ti

        joint_data = dict(getattr(scene_model, "joint_data", None) or {})
        geom_count = int(joint_data.get("n_geoms", 0) or 0)
        if geom_count <= 0:
            return
        self.geom_world_pos = ti.Vector.field(
            3,
            dtype=ti.f32,
            shape=(self.num_envs, geom_count),
        )
        self.geom_world_quat = ti.Vector.field(
            4,
            dtype=ti.f32,
            shape=(self.num_envs, geom_count),
        )
        self._geom_bodyid = np.asarray(
            joint_data.get("geom_bodyid", np.zeros(geom_count, dtype=np.int32)),
            dtype=np.int32,
        ).reshape(-1)[:geom_count]
        self._geom_pos = self._normalize_geom_array(
            joint_data.get("geom_pos"), geom_count, width=3
        )
        self._geom_quat = self._normalize_geom_array(
            joint_data.get("geom_quat"),
            geom_count,
            width=4,
            default=np.asarray((1.0, 0.0, 0.0, 0.0), dtype=np.float32),
        )
        initial_positions = np.repeat(
            np.asarray(getattr(scene_model, "positions"), dtype=np.float32)[None, ...],
            self.num_envs,
            axis=0,
        )
        initial_orientations = np.repeat(
            np.asarray(getattr(scene_model, "orientations"), dtype=np.float32)[None, ...],
            self.num_envs,
            axis=0,
        )
        self._sync_render_geom_fields(initial_positions, initial_orientations)

    @staticmethod
    def _normalize_geom_array(
        value: object | None,
        count: int,
        *,
        width: int,
        default: np.ndarray | None = None,
    ) -> np.ndarray:
        fallback = (
            np.zeros(width, dtype=np.float32)
            if default is None
            else np.asarray(default, dtype=np.float32)
        )
        result = np.repeat(fallback[None, :], count, axis=0)
        if value is not None:
            incoming = np.asarray(value, dtype=np.float32).reshape(-1, width)
            result[: min(count, len(incoming))] = incoming[:count]
        return np.ascontiguousarray(result)

    def _sync_render_geom_fields(
        self,
        body_positions: np.ndarray,
        body_orientations: np.ndarray,
    ) -> None:
        if self.geom_world_pos is None or self.geom_world_quat is None:
            return
        body_ids = np.clip(self._geom_bodyid, 0, body_positions.shape[1] - 1)
        parent_positions = body_positions[:, body_ids]
        parent_quats = body_orientations[:, body_ids]
        parent_rotation = self._quat_to_matrix(parent_quats)
        geom_positions = parent_positions + np.einsum(
            "bgij,gj->bgi", parent_rotation, self._geom_pos
        )
        geom_quats = self._quat_multiply(
            parent_quats,
            np.broadcast_to(self._geom_quat[None, ...], parent_quats.shape),
        )
        self.geom_world_pos.from_numpy(np.ascontiguousarray(geom_positions))
        self.geom_world_quat.from_numpy(np.ascontiguousarray(geom_quats))

    @staticmethod
    def _quat_to_matrix(quat: np.ndarray) -> np.ndarray:
        w, x, y, z = np.moveaxis(quat, -1, 0)
        return np.stack(
            (
                1 - 2 * (y * y + z * z),
                2 * (x * y - z * w),
                2 * (x * z + y * w),
                2 * (x * y + z * w),
                1 - 2 * (x * x + z * z),
                2 * (y * z - x * w),
                2 * (x * z + y * w),
                2 * (y * z + x * w),
                1 - 2 * (x * x + y * y),
            ),
            axis=-1,
        ).reshape(*quat.shape[:-1], 3, 3)

    @staticmethod
    def _quat_multiply(first: np.ndarray, second: np.ndarray) -> np.ndarray:
        w1, x1, y1, z1 = np.moveaxis(first, -1, 0)
        w2, x2, y2, z2 = np.moveaxis(second, -1, 0)
        return np.stack(
            (
                w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
                w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            ),
            axis=-1,
        )

    @staticmethod
    def _stack(rows: list[Mapping[str, Any]], name: str) -> np.ndarray:
        return np.ascontiguousarray(
            np.stack(
                [np.asarray(row[name], dtype=np.float32) for row in rows],
                axis=0,
            )
        )


def make_geophys_rigid_batch_runtime(
    *,
    compiled_scene: object,
    config: object,
    num_envs: int,
    backend: str,
) -> GeoPhysRigidBatchRuntime:
    """Internal construction seam without changing the public layout schema."""

    return GeoPhysRigidBatchRuntime.from_compiled_scene(
        compiled_scene=compiled_scene,
        config=config,
        num_envs=num_envs,
        backend=backend,
    )


__all__ = ["GeoPhysRigidBatchRuntime", "make_geophys_rigid_batch_runtime"]
