"""Framework-owned batched runtime for compiled articulated scenes."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

import numpy as np

from ...environment import ResolvedEnvConfig
from ..contracts import (
    BatchDiagnostics,
    BatchResetResult,
    BatchState,
    BatchStepResult,
)


class SceneBatchRuntime:
    """One device solver containing ``num_envs`` independent scene replicas.

    Replication happens once during construction.  The runtime then advances
    the merged rigid scene with one simulator/solver dispatch per substep; it
    never constructs or steps ``B`` scalar TaskEnvs.
    """

    def __init__(
        self,
        *,
        solver: object,
        simulator: object,
        num_envs: int,
        backend: str,
        control_substeps: int,
        single_counts: Mapping[str, int],
        initial_state: Mapping[str, np.ndarray],
    ) -> None:
        self._solver = solver
        self._simulator = simulator
        self.num_envs = int(num_envs)
        self.backend = str(backend)
        self.control_substeps = int(control_substeps)
        if self.num_envs < 1:
            raise ValueError("num_envs must be positive")
        if self.control_substeps < 1:
            raise ValueError("control_substeps must be positive")
        self._counts = {
            "qpos": int(single_counts.get("qpos", 0)),
            "qvel": int(single_counts.get("qvel", 0)),
            "qacc": int(single_counts.get("qacc", 0)),
            "ctrl": int(single_counts.get("ctrl", 0)),
            "act": int(single_counts.get("act", 0)),
            "body": int(single_counts.get("body", 0)),
            "site": int(single_counts.get("site", 0)),
        }
        self._initial_state = self._normalize_write_state(initial_state)

    @classmethod
    def from_compiled_scene(
        cls,
        *,
        compiled_scene: object,
        config: ResolvedEnvConfig,
        num_envs: int,
        backend: str,
    ) -> "SceneBatchRuntime":
        """Construct a batch runtime from the same compiled scene as single env."""

        size = int(num_envs)
        if size < 1:
            raise ValueError("num_envs must be positive")

        from geophys.demo_runtime import assemble_mjcf_articulated_runtime
        from geophys.test_runtime import init_test_backend
        from solvers.rigid import RigidGroundConfig
        from solvers.rigid.model import merge_rigid_scene_models

        init_test_backend(str(backend))
        base_model = compiled_scene.scene_model
        scene_models = [copy.deepcopy(base_model) for _ in range(size)]
        merged_model = merge_rigid_scene_models(scene_models)
        base_joint_data = base_model.joint_data or {}
        merged_joint_data = merged_model.joint_data or {}
        counts = {
            "qpos": int(base_joint_data.get("n_qpos", 0)),
            "qvel": int(base_joint_data.get("n_dof", 0)),
            "qacc": int(base_joint_data.get("n_dof", 0)),
            "ctrl": int(base_joint_data.get("n_actuators", 0)),
            "act": int(base_joint_data.get("n_actuators", 0)),
            "body": len(base_model.objects),
            "site": int(base_joint_data.get("n_sites", 0)),
        }
        # Replicas are independent environments, not one physical scene.  The
        # merged solver therefore needs explicit cross-slot body exclusions;
        # intra-slot contacts and authored contact excludes remain intact.
        body_count = counts["body"]
        authored_excludes = [
            tuple(int(value) for value in pair)
            for pair in merged_joint_data.get("contact_exclude_pairs", [])
        ]
        cross_slot_excludes = list(authored_excludes)
        for left_slot in range(size):
            left_start = left_slot * body_count
            for right_slot in range(left_slot + 1, size):
                right_start = right_slot * body_count
                cross_slot_excludes.extend(
                    (left_start + left_body, right_start + right_body)
                    for left_body in range(body_count)
                    for right_body in range(body_count)
                )
        merged_joint_data["contact_exclude_pairs"] = cross_slot_excludes
        for name, total_name in (
            ("qpos", "n_qpos"),
            ("qvel", "n_dof"),
            ("ctrl", "n_actuators"),
        ):
            if int(merged_joint_data.get(total_name, 0)) != size * counts[name]:
                raise RuntimeError(f"merged scene {name} layout is not homogeneous")

        solver_kwargs: dict[str, object] = {
            "dt": config.runtime.physics_dt,
            "gravity": config.runtime.gravity,
            "integrator": config.runtime.integrator,
            "ground": RigidGroundConfig(
                height=-1.0,
                visible=False,
                contact_margin=0.0,
            ),
            "enable_ground_contact": False,
            "enable_domain_boundary_contact": False,
            "broadphase": config.runtime.broadphase,
            "prewarm_kernels": False,
        }
        if config.runtime.rigid_solver_backend is not None:
            solver_kwargs["rigid_solver_backend"] = config.runtime.rigid_solver_backend
        if config.runtime.body_contact_solver_iterations is not None:
            solver_kwargs["body_contact_solver_iterations"] = (
                config.runtime.body_contact_solver_iterations
            )
        assembly = assemble_mjcf_articulated_runtime(
            compiled_scene.imported_scene,
            scene_model=merged_model,
            apply_mjcf_options=True,
            default_dt=config.runtime.physics_dt,
            default_gravity=config.runtime.gravity,
            default_integrator=config.runtime.integrator,
            solver_kwargs=solver_kwargs,
            create_simulator=True,
            create_render_source=False,
        )

        source_initial = compiled_scene.initial_state
        initial_state = {
            name: np.repeat(
                np.asarray(getattr(source_initial, name), dtype=np.float32)[None, :],
                size,
                axis=0,
            )
            for name in ("qpos", "qvel", "qacc", "ctrl", "act")
        }
        runtime = cls(
            solver=assembly.solver,
            simulator=assembly.simulator,
            num_envs=size,
            backend=str(backend),
            control_substeps=int(config.runtime.control_substeps),
            single_counts=counts,
            initial_state=initial_state,
        )
        runtime._write_state(initial_state, np.ones(size, dtype=np.bool_))
        if config.runtime.prewarm:
            runtime.prewarm()
        return runtime

    def reset(
        self,
        *,
        state: Mapping[str, np.ndarray],
        mask: np.ndarray,
    ) -> BatchResetResult:
        reset_mask = np.asarray(mask, dtype=np.bool_)
        if reset_mask.shape != (self.num_envs,):
            raise ValueError("batch reset mask must have shape (B,)")
        current = self._read_state()
        self._write_state(state, reset_mask, current=current)
        return BatchResetResult(
            state=BatchState(self._read_state()),
            diagnostics=BatchDiagnostics(
                {"reset_mask": reset_mask.astype(np.bool_, copy=True)}
            ),
        )

    def step(self, action: np.ndarray) -> BatchStepResult:
        value = np.asarray(action, dtype=np.float32)
        expected = (self.num_envs, self._counts["ctrl"])
        if value.shape != expected:
            raise ValueError(
                f"batch control action must have shape {expected}, got {value.shape}"
            )
        if not np.isfinite(value).all():
            raise ValueError("batch control action must be finite")
        if self._counts["ctrl"]:
            self._solver.write_ctrl(value.reshape(-1))
        self._simulator.step(self.control_substeps)
        return BatchStepResult(state=BatchState(self._read_state()))

    def resource_summary(self) -> dict[str, Any]:
        return {
            "kind": "scene_device_batch",
            "backend": self.backend,
            "num_envs": self.num_envs,
            "solver_count": 1,
            "control_substeps": self.control_substeps,
            "single_topology": {
                "qpos": self._counts["qpos"],
                "qvel": self._counts["qvel"],
                "actuators": self._counts["ctrl"],
                "bodies": self._counts["body"],
                "sites": self._counts["site"],
            },
            # 与 static-template runtime 保持相同 summary 形状。merged-scene 实现
            # 明确为 host-only；wrapper 上偶然发现的 callable 不得制造 device 能力。
            "device_transition": {
                "available": False,
                "runtime_method": "step_device",
                "zero_copy_substeps": False,
                "field_device": None,
                "reason": "merged scene runtime has no device transition",
            },
        }

    def parallel_render_state_source(self) -> tuple[object, str]:
        """向 parallel renderer 提供独立的渲染状态 port。"""

        return self._solver, "flat"

    def prewarm(self, profile: str = "interactive") -> None:
        prewarm = getattr(self._simulator, "prewarm", None)
        if callable(prewarm):
            prewarm(profile=profile)

    def close(self) -> None:
        """Taichi owns process-wide resources; no per-runtime teardown is needed."""

    def _normalize_write_state(
        self,
        state: Mapping[str, np.ndarray],
        *,
        current: Mapping[str, np.ndarray] | None = None,
    ) -> dict[str, np.ndarray]:
        allowed = ("qpos", "qvel", "qacc", "ctrl", "act")
        unknown = set(state) - set(allowed)
        if unknown:
            raise ValueError(
                f"scene batch reset contains unknown state fields: {sorted(unknown)}"
            )
        result: dict[str, np.ndarray] = {}
        for name in allowed:
            width = self._counts[name]
            if name in state:
                value = np.asarray(state[name], dtype=np.float32)
                expected = (self.num_envs, width)
                if value.shape != expected:
                    raise ValueError(
                        f"batch state {name} must have shape {expected}, got {value.shape}"
                    )
                if not np.isfinite(value).all():
                    raise ValueError(f"batch state {name} must be finite")
                result[name] = value.copy()
            elif current is not None:
                result[name] = np.asarray(current[name], dtype=np.float32).copy()
            else:
                result[name] = np.asarray(self._initial_state[name], dtype=np.float32).copy()
        return result

    def _write_state(
        self,
        state: Mapping[str, np.ndarray],
        mask: np.ndarray,
        *,
        current: Mapping[str, np.ndarray] | None = None,
    ) -> None:
        values = self._normalize_write_state(state, current=current)
        reset_mask = np.asarray(mask, dtype=np.bool_)
        if reset_mask.shape != (self.num_envs,):
            raise ValueError("batch reset mask must have shape (B,)")
        if current is not None:
            merged = {
                name: np.asarray(current[name], dtype=np.float32).copy()
                for name in values
            }
            for name in values:
                merged[name][reset_mask] = values[name][reset_mask]
            values = merged
        if self._counts["qpos"]:
            self._solver.write_qpos(values["qpos"].reshape(-1))
        if self._counts["qvel"]:
            self._solver.write_qvel(values["qvel"].reshape(-1))
            self._solver.write_qacc(values["qacc"].reshape(-1))
        if self._counts["ctrl"]:
            self._solver.write_ctrl(values["ctrl"].reshape(-1))
            self._solver.write_act(values["act"].reshape(-1))
        self._solver.synchronize_kinematic_state(update_site_jacobians=False)

    def _read_state(self) -> dict[str, np.ndarray]:
        result = {
            "qpos": self._read_vector("qpos", self._solver.read_qpos),
            "qvel": self._read_vector("qvel", self._solver.read_qvel),
            "qacc": self._read_vector("qacc", self._solver.read_qacc),
            "ctrl": self._read_vector("ctrl", self._solver.read_ctrl),
            "act": self._read_vector("act", self._solver.read_act),
            "body_xpos": self._reshape_spatial(
                self._solver.read_positions(), "body", 3
            ),
            "body_xquat": self._reshape_spatial(
                self._solver.read_orientations(), "body", 4
            ),
            "site_xpos": (
                self._reshape_spatial(self._solver.read_site_world_pos(), "site", 3)
                if self._counts["site"]
                else np.zeros((self.num_envs, 0, 3), dtype=np.float32)
            ),
            "site_xquat": (
                self._reshape_spatial(self._solver.read_site_world_quat(), "site", 4)
                if self._counts["site"]
                else np.zeros((self.num_envs, 0, 4), dtype=np.float32)
            ),
        }
        # Contact readback is optional and remains a named diagnostic view;
        # task definitions can consume it without depending on solver fields.
        for name in ("ground_contact_active", "body_contact_active"):
            field = getattr(self._solver, name, None)
            if field is not None:
                result[name] = self._reshape_spatial_scalar(
                    field.to_numpy(), "body"
                ).astype(np.bool_, copy=False)
        for name in ("ground_contact_count", "body_contact_count"):
            field = getattr(self._solver, name, None)
            if field is not None:
                result[name] = self._reshape_spatial_scalar(field.to_numpy(), "body")
        return result

    def _reshape_spatial_scalar(self, value: np.ndarray, name: str) -> np.ndarray:
        width = self._counts[name]
        array = np.asarray(value).reshape(-1)
        expected = self.num_envs * width
        if array.size < expected:
            raise RuntimeError(
                f"solver {name} contact readback has {array.size} values, expected {expected}"
            )
        return array[:expected].reshape(self.num_envs, width).copy()

    def _read_vector(self, name: str, reader) -> np.ndarray:
        if self._counts[name] == 0:
            return np.zeros((self.num_envs, 0), dtype=np.float32)
        return self._reshape_read(name, reader())

    def _reshape_read(self, name: str, value: np.ndarray) -> np.ndarray:
        width = self._counts[name]
        if width == 0:
            return np.zeros((self.num_envs, 0), dtype=np.float32)
        array = np.asarray(value, dtype=np.float32).reshape(-1)
        expected = self.num_envs * width
        if array.size < expected:
            raise RuntimeError(
                f"solver {name} readback has {array.size} values, expected {expected}"
            )
        return array[:expected].reshape(self.num_envs, width).copy()

    def _reshape_spatial(
        self,
        value: np.ndarray,
        name: str,
        tail: int,
    ) -> np.ndarray:
        width = self._counts[name]
        if width == 0:
            return np.zeros((self.num_envs, 0, tail), dtype=np.float32)
        array = np.asarray(value, dtype=np.float32).reshape(-1, tail)
        expected = self.num_envs * width
        if array.shape[0] < expected:
            raise RuntimeError(
                f"solver {name} readback has {array.shape[0]} rows, expected {expected}"
            )
        return array[:expected].reshape(self.num_envs, width, tail).copy()


__all__ = ["SceneBatchRuntime"]
