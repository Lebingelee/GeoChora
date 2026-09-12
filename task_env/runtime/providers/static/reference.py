"""Generic articulated static-template reference execution.

This module is deliberately task-agnostic.  It extracts one immutable scene
model and creates exact-B local solver/workspace owners from the current
``RigidSolver`` assembly.  The current implementation is a semantic reference
kernel (one local solver per world), not the final fused ``(B, local_*)``
Taichi kernel.  It is useful because it proves the public static-template
contract, contact isolation, control-substep ordering, and masked reset without
reintroducing a global body/geom key.  The resource report makes the mode
explicit so it cannot be mistaken for the fused-performance exit gate.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

import numpy as np

from .model import StaticTemplateModel
from .workspace import StaticTemplateContactWorkspace
from ...contracts import DeviceBatchState


def _solver_field_inventory(solver: object) -> dict[str, list[str]]:
    """Classify current RigidSolver Taichi fields for provenance only."""

    try:
        values = vars(solver)
    except TypeError:
        values = {}
    names = sorted(
        str(name)
        for name, value in values.items()
        if callable(getattr(value, "to_numpy", None))
        and callable(getattr(value, "from_numpy", None))
    )
    workspace_tokens = (
        "candidate", "manifold", "contact_row", "free_body_contact",
        "prev_manifold", "warm", "gjk", "broadphase", "constraint",
    )
    state_tokens = (
        "qpos", "qvel", "qacc", "ctrl", "act", "position", "orientation",
        "linear_velocity", "angular_velocity", "body_x", "geom_x", "site_",
    )
    workspace = [name for name in names if any(token in name.lower() for token in workspace_tokens)]
    persistent = [name for name in names if name not in workspace and any(token in name.lower() for token in state_tokens)]
    shared = [name for name in names if name not in workspace and name not in persistent]
    return {"template_shared": shared, "world_persistent": persistent, "substep_workspace": workspace}


class StaticTemplateRigidSolverReference:
    """Exact-B local RigidSolver reference with shared topology provenance."""

    def __init__(
        self,
        *,
        solvers: tuple[object, ...],
        simulators: tuple[object, ...],
        scene_model: object,
        num_envs: int,
        backend: str,
        control_substeps: int,
        enable_ground_contact: bool,
        enable_domain_boundary_contact: bool,
        template_model: StaticTemplateModel,
        workspace: StaticTemplateContactWorkspace,
    ) -> None:
        self._solvers = solvers
        self._simulators = simulators
        self._scene_model = scene_model
        self.num_envs = int(num_envs)
        self.backend = str(backend)
        self.control_substeps = int(control_substeps)
        self.enable_ground_contact = bool(enable_ground_contact)
        self.enable_domain_boundary_contact = bool(enable_domain_boundary_contact)
        self.template_model = template_model
        self.workspace = workspace
        self.field_inventory = _solver_field_inventory(self._solvers[0])
        if self.num_envs < 1:
            raise ValueError("num_envs must be positive")
        if len(self._solvers) != self.num_envs or len(self._simulators) != self.num_envs:
            raise ValueError("static reference solver/simulator count must equal num_envs")
        self._counts = {
            "qpos": int(getattr(self._solvers[0], "n_qpos", 0)),
            "qvel": int(getattr(self._solvers[0], "n_dof", 0)),
            "qacc": int(getattr(self._solvers[0], "n_dof", 0)),
            "ctrl": int(getattr(self._solvers[0], "n_actuators", 0)),
            "act": int(getattr(self._solvers[0], "n_actuators", 0)),
            "body": int(getattr(self._solvers[0], "n_bodies_actual", 0)),
            "geom": int(getattr(self._solvers[0], "n_geoms", 0)),
            "site": int(getattr(self._solvers[0], "n_sites", 0)),
        }

    @classmethod
    def from_compiled_scene(
        cls,
        *,
        compiled_scene: object,
        config: object,
        num_envs: int,
        backend: str,
    ) -> "StaticTemplateRigidSolverReference":
        from geophys.demo_runtime import assemble_mjcf_articulated_runtime
        from geophys.test_runtime import init_test_backend

        size = int(num_envs)
        if size < 1:
            raise ValueError("num_envs must be positive")
        init_test_backend(str(backend))
        base_model = getattr(compiled_scene, "scene_model", None)
        imported_scene = getattr(compiled_scene, "imported_scene", None)
        if base_model is None or imported_scene is None:
            raise ValueError("compiled_scene must expose scene_model and imported_scene")

        runtime = config.runtime
        ground = getattr(base_model, "ground", None)
        enable_ground = runtime.enable_ground_contact
        if enable_ground is None:
            enable_ground = ground is not None
        solver_kwargs: dict[str, object] = {
            "dt": runtime.physics_dt,
            "gravity": runtime.gravity,
            "integrator": runtime.integrator,
            "ground": ground,
            "enable_ground_contact": bool(enable_ground),
            "enable_domain_boundary_contact": bool(
                runtime.enable_domain_boundary_contact
            ),
            "broadphase": runtime.broadphase,
            "prewarm_kernels": False,
        }
        if runtime.rigid_solver_backend is not None:
            solver_kwargs["rigid_solver_backend"] = runtime.rigid_solver_backend
        if runtime.body_contact_solver_iterations is not None:
            solver_kwargs["body_contact_solver_iterations"] = int(
                runtime.body_contact_solver_iterations
            )

        solvers: list[object] = []
        simulators: list[object] = []
        for _ in range(size):
            # Each world owns local contact/manifold/row fields.  The copied
            # model is immutable after construction and has no B-offset IDs.
            world_model = copy.deepcopy(base_model)
            assembly = assemble_mjcf_articulated_runtime(
                imported_scene,
                scene_model=world_model,
                apply_mjcf_options=True,
                default_dt=runtime.physics_dt,
                default_gravity=runtime.gravity,
                default_integrator=runtime.integrator,
                solver_kwargs=solver_kwargs,
                create_simulator=True,
                create_render_source=False,
            )
            if assembly.simulator is None:
                raise RuntimeError("static reference assembly did not create a simulator")
            solvers.append(assembly.solver)
            simulators.append(assembly.simulator)
        local_geom_count = int(getattr(solvers[0], "n_geoms", 0))
        max_pairs = max(0, local_geom_count * max(local_geom_count - 1, 0) // 2)
        workspace = StaticTemplateContactWorkspace(
            num_envs=size,
            max_pairs_per_world=max_pairs,
            max_rows_per_world=max_pairs * 4,
        )
        return cls(
            solvers=tuple(solvers),
            simulators=tuple(simulators),
            scene_model=base_model,
            num_envs=size,
            backend=str(backend),
            control_substeps=int(runtime.control_substeps),
            enable_ground_contact=bool(enable_ground),
            enable_domain_boundary_contact=bool(
                runtime.enable_domain_boundary_contact
            ),
            template_model=StaticTemplateModel.from_compiled_scene(compiled_scene),
            workspace=workspace,
        )

    @property
    def counts(self) -> Mapping[str, int]:
        return self._counts

    def write_state(self, state: Mapping[str, np.ndarray]) -> None:
        for slot, solver in enumerate(self._solvers):
            self._write_solver_state(solver, state, slot)

    def write_ctrl(self, ctrl: np.ndarray) -> None:
        value = np.asarray(ctrl, dtype=np.float32)
        expected = (self.num_envs, self._counts["ctrl"])
        if value.shape != expected:
            raise ValueError(f"batch control action must have shape {expected}, got {value.shape}")
        for slot, solver in enumerate(self._solvers):
            solver.write_ctrl(value[slot])

    @staticmethod
    def _field_tensor(solver: object, names: tuple[str, ...], *, count: int, label: str, device: str) -> Any:
        field = None
        field_name = ""
        for name in names:
            candidate = getattr(solver, name, None)
            if callable(getattr(candidate, "to_torch", None)):
                field = candidate
                field_name = name
                break
        if field is None:
            raise RuntimeError(f"solver has no device field for {label!r}")
        value = field.to_torch(device=device)
        if value.ndim < 1:
            raise RuntimeError(f"solver device field {field_name!r} for {label!r} is scalar")
        return value[: int(count)]

    @staticmethod
    def _write_field_tensor(solver: object, names: tuple[str, ...], value: Any, *, label: str) -> None:
        for name in names:
            field = getattr(solver, name, None)
            if callable(getattr(field, "from_torch", None)):
                field.from_torch(value.contiguous())
                return
        raise RuntimeError(f"solver has no device field for {label!r}")

    def read_device_state(self, names: tuple[str, ...]) -> DeviceBatchState:
        """Read a named state view using each local solver's device fields."""

        import torch

        supported = {
            "qpos": (("qpos_field", "qpos"), "qpos"),
            "qvel": (("qvel_field", "qvel"), "qvel"),
            "qacc": (("qacc_field", "qacc"), "qacc"),
            "ctrl": (("ctrl_field", "ctrl"), "ctrl"),
            "act": (("act_state_field", "act_field", "act"), "act"),
            "body_xpos": (("positions", "body_xpos"), "body_xpos"),
            "body_xquat": (("orientations", "body_xquat"), "body_xquat"),
            "geom_xpos": (("geom_xpos", "geom_world_pos"), "geom_xpos"),
            "geom_xquat": (("geom_xquat", "geom_world_quat"), "geom_xquat"),
            "site_xpos": (("site_world_pos", "site_xpos"), "site_xpos"),
            "site_xquat": (("site_world_quat", "site_xquat"), "site_xquat"),
            "ground_contact_active": (("ground_contact_active",), "ground_contact_active"),
            "body_contact_active": (("body_contact_active",), "body_contact_active"),
            "ground_contact_count": (("ground_contact_count",), "ground_contact_count"),
            "body_contact_count": (("body_contact_count",), "body_contact_count"),
        }
        unknown = sorted(set(names) - set(supported))
        if unknown:
            raise KeyError(f"unknown static device state fields: {unknown}")
        arrays: dict[str, Any] = {}
        for name in names:
            field_names, label = supported[name]
            count = self._counts["body"] if name in {
                "body_xpos", "body_xquat", "ground_contact_active", "body_contact_active",
                "ground_contact_count", "body_contact_count",
            } else self._counts["geom"] if name in {"geom_xpos", "geom_xquat"} else self._counts["site"] if name in {"site_xpos", "site_xquat"} else self._counts[name]
            device = "cuda" if self.backend == "cuda" else "cpu"
            tensors = [
                self._field_tensor(
                    solver,
                    field_names,
                    count=count,
                    label=label,
                    device=device,
                )
                for solver in self._solvers
            ]
            arrays[name] = torch.stack(tensors, dim=0)
        if not arrays:
            raise ValueError("device state request cannot be empty")
        device = str(next(iter(arrays.values())).device)
        return DeviceBatchState(arrays=arrays, device=device, num_envs=self.num_envs)

    def write_ctrl_device(self, ctrl: Any) -> None:
        expected = (self.num_envs, self._counts["ctrl"])
        if tuple(getattr(ctrl, "shape", ())) != expected:
            raise ValueError(f"device control must have shape {expected}")
        for slot, solver in enumerate(self._solvers):
            self._write_field_tensor(solver, ("ctrl_field", "ctrl"), ctrl[slot], label="ctrl")

    def step_device(self, control: Any) -> DeviceBatchState:
        """Run one control tick with device fields and no state readback."""

        if str(getattr(control, "device", "")) != str(
            self.read_device_state(("qpos",)).device
        ):
            raise RuntimeError(
                "device control and static reference fields must share a device; "
                "select an explicit sim/rl transfer mode instead"
            )
        self.write_ctrl_device(control)
        for simulator in self._simulators:
            simulator.step(self.control_substeps)
        return self.read_device_state(
            (
                "qpos", "qvel", "qacc", "ctrl", "act", "body_xpos", "body_xquat", "geom_xpos", "geom_xquat",
                "site_xpos", "site_xquat", "ground_contact_active", "body_contact_active",
                "ground_contact_count", "body_contact_count",
            )
        )

    def reset_device(self, state: Mapping[str, Any], mask: Any) -> DeviceBatchState:
        import torch

        current = self.read_device_state(("qpos", "qvel", "qacc", "ctrl", "act"))
        selected = mask if hasattr(mask, "device") else torch.as_tensor(mask, dtype=torch.bool)
        if tuple(getattr(selected, "shape", ())) != (self.num_envs,):
            raise ValueError(f"device reset mask must have shape ({self.num_envs},)")
        selected = selected.to(device=current.device, dtype=torch.bool)
        for name, fields in (
            ("qpos", ("qpos_field", "qpos")),
            ("qvel", ("qvel_field", "qvel")),
            ("qacc", ("qacc_field", "qacc")),
            ("ctrl", ("ctrl_field", "ctrl")),
            ("act", ("act_state_field", "act_field", "act")),
        ):
            if name not in state:
                continue
            value = state[name]
            expected = tuple(current.arrays[name].shape)
            if tuple(getattr(value, "shape", ())) != expected:
                raise ValueError(f"device reset field {name!r} must have shape {expected}")
            if str(getattr(value, "device", "")) != str(current.device):
                raise RuntimeError(f"device reset field {name!r} is on a different device")
            merged = torch.where(
                selected.reshape(self.num_envs, *([1] * (len(expected) - 1))),
                value,
                current.arrays[name],
            )
            for slot, solver in enumerate(self._solvers):
                self._write_field_tensor(solver, fields, merged[slot], label=name)
        reset_mask = selected.detach().to("cpu").numpy()
        self.reset_workspace(reset_mask)
        self.refresh()
        return self.read_device_state(
            ("qpos", "qvel", "qacc", "ctrl", "act", "body_xpos", "body_xquat", "geom_xpos", "geom_xquat", "site_xpos", "site_xquat")
        )

    def refresh(self) -> None:
        for solver in self._solvers:
            solver.synchronize_kinematic_state(update_site_jacobians=False)

    def step(self, substeps: int) -> None:
        if int(substeps) != self.control_substeps:
            raise ValueError(
                "static-template control_substeps is fixed at construction; "
                f"expected {self.control_substeps}, got {int(substeps)}"
            )
        for simulator in self._simulators:
            simulator.step(self.control_substeps)

    def reset_workspace(self, mask: np.ndarray) -> None:
        value = np.asarray(mask, dtype=np.bool_)
        if value.shape != (self.num_envs,):
            raise ValueError("static reference reset mask must have shape (B,)")
        self.workspace.reset(value)
        for slot, selected in enumerate(value):
            if selected:
                self._clear_solver_workspace(self._solvers[slot])

    def execution_plan_facts(self) -> Mapping[str, Any]:
        """Publish local workspace facts owned by the reference provider."""

        return {
            "max_contact_pairs_per_world": int(
                self.workspace.max_pairs_per_world
            ),
            "max_constraint_rows_per_world": int(
                self.workspace.max_rows_per_world
            ),
            # The reference path publishes contact state through its solver
            # fields; it does not expose the fused fixed-slot contact port.
            "contact_workspace_slots_per_world": 0,
            "fused_kernel": False,
            "execution_route": "isolated_world_reference",
        }

    def render_state_source(self) -> tuple[object, str]:
        """Return local solver owners through the formal render port."""

        if self._solvers:
            return self._solvers, "local_solver_sequence"
        raise RuntimeError("static reference provider has no renderable state owner")

    def read_state(self) -> dict[str, np.ndarray]:
        result = {
            "qpos": np.zeros((self.num_envs, self._counts["qpos"]), dtype=np.float32),
            "qvel": np.zeros((self.num_envs, self._counts["qvel"]), dtype=np.float32),
            "qacc": np.zeros((self.num_envs, self._counts["qacc"]), dtype=np.float32),
            "ctrl": np.zeros((self.num_envs, self._counts["ctrl"]), dtype=np.float32),
            "act": np.zeros((self.num_envs, self._counts["act"]), dtype=np.float32),
            "body_xpos": np.zeros((self.num_envs, self._counts["body"], 3), dtype=np.float32),
            "body_xquat": np.zeros((self.num_envs, self._counts["body"], 4), dtype=np.float32),
            "geom_xpos": np.zeros((self.num_envs, self._counts["geom"], 3), dtype=np.float32),
            "geom_xquat": np.zeros((self.num_envs, self._counts["geom"], 4), dtype=np.float32),
            "site_xpos": np.zeros((self.num_envs, self._counts["site"], 3), dtype=np.float32),
            "site_xquat": np.zeros((self.num_envs, self._counts["site"], 4), dtype=np.float32),
            "ground_contact_active": np.zeros((self.num_envs, self._counts["body"]), dtype=np.bool_),
            "body_contact_active": np.zeros((self.num_envs, self._counts["body"]), dtype=np.bool_),
            "ground_contact_count": np.zeros((self.num_envs, self._counts["body"]), dtype=np.int32),
            "body_contact_count": np.zeros((self.num_envs, self._counts["body"]), dtype=np.int32),
        }
        for slot, solver in enumerate(self._solvers):
            result["qpos"][slot] = np.asarray(solver.read_qpos(), dtype=np.float32)[: self._counts["qpos"]]
            result["qvel"][slot] = np.asarray(solver.read_qvel(), dtype=np.float32)[: self._counts["qvel"]]
            result["qacc"][slot] = np.asarray(solver.read_qacc(), dtype=np.float32)[: self._counts["qacc"]]
            result["ctrl"][slot] = np.asarray(solver.read_ctrl(), dtype=np.float32)[: self._counts["ctrl"]]
            result["act"][slot] = np.asarray(solver.read_act(), dtype=np.float32)[: self._counts["act"]]
            result["body_xpos"][slot] = np.asarray(solver.read_positions(), dtype=np.float32).reshape(-1, 3)[: self._counts["body"]]
            result["body_xquat"][slot] = np.asarray(solver.read_orientations(), dtype=np.float32).reshape(-1, 4)[: self._counts["body"]]
            for name, reader, width in (
                ("geom_xpos", "read_geom_world_pos", 3),
                ("geom_xquat", "read_geom_world_quat", 4),
            ):
                method = getattr(solver, reader, None)
                if callable(method) and self._counts["geom"]:
                    result[name][slot] = np.asarray(method(), dtype=np.float32).reshape(-1, width)[: self._counts["geom"]]
            if self._counts["site"]:
                result["site_xpos"][slot] = np.asarray(solver.read_site_world_pos(), dtype=np.float32).reshape(-1, 3)[: self._counts["site"]]
                result["site_xquat"][slot] = np.asarray(solver.read_site_world_quat(), dtype=np.float32).reshape(-1, 4)[: self._counts["site"]]
            if hasattr(solver, "ground_contact_active"):
                result["ground_contact_active"][slot] = np.asarray(
                    solver.ground_contact_active.to_numpy(), dtype=np.bool_
                )[: self._counts["body"]]
                result["ground_contact_count"][slot] = np.asarray(
                    solver.ground_contact_count.to_numpy(), dtype=np.int32
                )[: self._counts["body"]]
            if hasattr(solver, "body_contact_active"):
                result["body_contact_active"][slot] = np.asarray(
                    solver.body_contact_active.to_numpy(), dtype=np.bool_
                )[: self._counts["body"]]
                result["body_contact_count"][slot] = np.asarray(
                    solver.body_contact_count.to_numpy(), dtype=np.int32
                )[: self._counts["body"]]
        return result

    def prewarm(self) -> None:
        for simulator in self._simulators:
            prewarm = getattr(simulator, "prewarm", None)
            if callable(prewarm):
                prewarm(profile="interactive")

    def resource_summary(self) -> dict[str, Any]:
        body = self._counts["body"]
        geom = self._counts["geom"]
        qpos = self._counts["qpos"]
        qvel = self._counts["qvel"]
        ctrl = self._counts["ctrl"]
        sites = self._counts["site"]
        per_world_state = 4 * (qpos + 2 * qvel + 2 * ctrl + 7 * body + 7 * geom + 7 * sites)
        shared = int(sum(np.asarray(getattr(self._scene_model, "joint_data", {}).get(key, ())).nbytes for key in ("jnt_type", "jnt_parent_body", "jnt_child_body", "geom_bodyid")))
        device_methods = all(
            callable(getattr(self, name, None))
            for name in ("read_device_state", "step_device", "reset_device")
        )
        field_device = None
        if device_methods:
            try:
                field_device = str(self.read_device_state(("qpos",)).device)
            except Exception:
                device_methods = False
        compatible = bool(
            device_methods
            and field_device is not None
            and (self.backend != "cuda" or field_device.startswith("cuda"))
        )
        solver = self._solvers[0] if self._solvers else None
        route_report_fn = getattr(solver, "execution_route_report", None)
        route_report = (
            dict(route_report_fn())
            if callable(route_report_fn)
            else {}
        )
        return {
            "execution": "isolated_world_reference",
            "implementation_status": "reference_kernel",
            "device_transition": {
                "available": compatible,
                "runtime_method": "step_device",
                "reason": None if compatible else (
                    "solver fields are not on the requested simulator device"
                    if device_methods else "reference device methods are incomplete"
                ),
                "field_device": field_device,
                "zero_copy_substeps": compatible,
            },
            "solver_count": self.num_envs,
            "num_envs": self.num_envs,
            "backend": self.backend,
            "exact_batch": True,
            "contact_workspace": "solver_local",
            "workspace_addressing": "(world_id, local_id)",
            "template_digest": self.template_model.template_digest,
            "compiled_template_fields": list(self.template_model.compiled_field_names),
            "solver_field_inventory": self.field_inventory,
            "workspace": self.workspace.resource_summary(),
            "enable_ground_contact": self.enable_ground_contact,
            "enable_domain_boundary_contact": self.enable_domain_boundary_contact,
            "shared_template_bytes_lower_bound": shared,
            "per_world_state_bytes_lower_bound": per_world_state,
            "local_body_count": body,
            "local_geom_count": geom,
            "capacity_policy": "exact_batch",
            "rigid_solver_backend": str(
                getattr(solver, "rigid_solver_backend_name", "unknown")
            ),
            "rigid_constraint_backend": str(
                getattr(solver, "rigid_constraint_backend_name", "unknown")
            ),
            "active_efc_solver": bool(
                getattr(solver, "rigid_contact_backend_uses_active_efc_solver", False)
            ),
            "execution_route_report": route_report,
        }

    def close(self) -> None:
        # Taichi owns process-wide resources; dropping references is sufficient.
        self._solvers = ()
        self._simulators = ()

    @staticmethod
    def _write_solver_state(solver: object, state: Mapping[str, np.ndarray], slot: int) -> None:
        solver.write_qpos(np.asarray(state["qpos"][slot], dtype=np.float32))
        solver.write_qvel(np.asarray(state["qvel"][slot], dtype=np.float32))
        solver.write_qacc(np.asarray(state["qacc"][slot], dtype=np.float32))
        solver.write_ctrl(np.asarray(state["ctrl"][slot], dtype=np.float32))
        solver.write_act(np.asarray(state["act"][slot], dtype=np.float32))

    @staticmethod
    def _clear_solver_workspace(solver: object) -> None:
        for name in (
            "_reset_ground_contact_rows",
            "_reset_generalized_contact_row_buffers_kernel",
            "_reset_body_contact_pipeline_buffers",
        ):
            method = getattr(solver, name, None)
            if callable(method):
                method()
        for name in ("prev_manifold_count", "manifold_count", "ground_contact_count"):
            field = getattr(solver, name, None)
            if field is not None:
                try:
                    field[None] = 0
                except Exception:
                    pass


__all__ = ["StaticTemplateRigidSolverReference"]
