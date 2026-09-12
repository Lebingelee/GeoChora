"""Taichi device implementation for the first static-template capability profile."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import taichi as ti

from geometry.ti_math import (
    ti_axis_angle_to_quat,
    ti_quat_multiply,
    ti_quat_normalize,
    ti_quat_to_matrix,
)
from .workspace import StaticTemplateContactWorkspace
from ...contracts import DeviceBatchState


def _field_shape(count: int) -> int:
    return max(1, int(count))


@ti.data_oriented
class StaticTemplatePhysics:
    """Shared local model plus ``(world, local)`` mutable state fields."""

    JOINT_HINGE = 2
    JOINT_SLIDE = 3

    def __init__(
        self,
        *,
        model: Mapping[str, Any],
        num_envs: int,
        control_substeps: int,
        qpos_count: int,
        qvel_count: int,
        actuator_count: int,
        body_count: int,
        geom_count: int,
        site_count: int,
        max_contact_pairs_per_world: int = 0,
        max_constraint_rows_per_world: int = 0,
        backend: str = "cpu",
    ) -> None:
        self.num_envs = int(num_envs)
        self.control_substeps = int(control_substeps)
        self.qpos_count = int(qpos_count)
        self.qvel_count = int(qvel_count)
        self.actuator_count = int(actuator_count)
        self.body_count = int(body_count)
        self.geom_count = int(geom_count)
        self.site_count = int(site_count)
        self.backend = str(backend)
        self._contact_workspace = StaticTemplateContactWorkspace(
            num_envs=self.num_envs,
            max_pairs_per_world=int(max_contact_pairs_per_world),
            max_rows_per_world=int(max_constraint_rows_per_world),
        )
        self.physics_dt = float(model["physics_dt"])
        self.integrator = str(model["integrator"])
        self.joint_type = int(np.asarray(model["jnt_type"]).reshape(-1)[0])

        # Shared immutable topology/model arrays.
        self._body_pos = ti.Vector.field(3, ti.f32, shape=_field_shape(self.body_count))
        self._body_quat = ti.Vector.field(4, ti.f32, shape=_field_shape(self.body_count))
        self._body_ipos = ti.Vector.field(3, ti.f32, shape=_field_shape(self.body_count))
        self._body_iquat = ti.Vector.field(4, ti.f32, shape=_field_shape(self.body_count))
        self._body_mass = ti.field(ti.f32, shape=_field_shape(self.body_count))
        self._body_inertia = ti.Vector.field(3, ti.f32, shape=_field_shape(self.body_count))
        self._body_gravcomp = ti.field(ti.f32, shape=_field_shape(self.body_count))
        self._body_parent = ti.field(ti.i32, shape=_field_shape(self.body_count))
        self._jnt_parent = ti.field(ti.i32, shape=1)
        self._jnt_child = ti.field(ti.i32, shape=1)
        self._jnt_qposadr = ti.field(ti.i32, shape=1)
        self._jnt_dofadr = ti.field(ti.i32, shape=1)
        self._jnt_axis_parent = ti.Vector.field(3, ti.f32, shape=1)
        self._jnt_axis_child = ti.Vector.field(3, ti.f32, shape=1)
        self._jnt_anchor_child = ti.Vector.field(3, ti.f32, shape=1)
        self._jnt_damping = ti.field(ti.f32, shape=1)
        self._jnt_stiffness = ti.field(ti.f32, shape=1)
        self._jnt_ref = ti.field(ti.f32, shape=1)
        self._jnt_ref_pos = ti.field(ti.f32, shape=1)
        self._jnt_armature = ti.field(ti.f32, shape=1)
        self._geom_bodyid = ti.field(ti.i32, shape=_field_shape(self.geom_count))
        self._geom_pos = ti.Vector.field(3, ti.f32, shape=_field_shape(self.geom_count))
        self._geom_quat = ti.Vector.field(4, ti.f32, shape=_field_shape(self.geom_count))
        self._site_bodyid = ti.field(ti.i32, shape=_field_shape(self.site_count))
        self._site_pos = ti.Vector.field(3, ti.f32, shape=_field_shape(self.site_count))
        self._site_quat = ti.Vector.field(4, ti.f32, shape=_field_shape(self.site_count))
        self._actuator_gear = ti.Vector.field(6, ti.f32, shape=_field_shape(self.actuator_count))
        self._root_pos = ti.Vector.field(3, ti.f32, shape=())
        self._root_quat = ti.Vector.field(4, ti.f32, shape=())
        self._gravity = ti.Vector.field(3, ti.f32, shape=())

        self._upload_model(model)

        # Per-world mutable state.  No field below contains a global B*local ID.
        self._qpos = ti.Vector.field(self.qpos_count, ti.f32, shape=self.num_envs)
        self._qvel = ti.Vector.field(self.qvel_count, ti.f32, shape=self.num_envs)
        self._qacc = ti.Vector.field(self.qvel_count, ti.f32, shape=self.num_envs)
        self._ctrl = ti.Vector.field(self.actuator_count, ti.f32, shape=self.num_envs)
        self._act = ti.Vector.field(self.actuator_count, ti.f32, shape=self.num_envs)
        self._body_xpos = ti.Vector.field(3, ti.f32, shape=(self.num_envs, _field_shape(self.body_count)))
        self._body_xquat = ti.Vector.field(4, ti.f32, shape=(self.num_envs, _field_shape(self.body_count)))
        self._body_linear_vel = ti.Vector.field(3, ti.f32, shape=(self.num_envs, _field_shape(self.body_count)))
        self._body_angular_vel = ti.Vector.field(3, ti.f32, shape=(self.num_envs, _field_shape(self.body_count)))
        self._geom_xpos = ti.Vector.field(3, ti.f32, shape=(self.num_envs, _field_shape(self.geom_count)))
        self._geom_xquat = ti.Vector.field(4, ti.f32, shape=(self.num_envs, _field_shape(self.geom_count)))
        self._site_xpos = ti.Vector.field(3, ti.f32, shape=(self.num_envs, _field_shape(self.site_count)))
        self._site_xquat = ti.Vector.field(4, ti.f32, shape=(self.num_envs, _field_shape(self.site_count)))

    def _upload_model(self, model: Mapping[str, Any]) -> None:
        def vector(field: Any, key: str, width: int, count: int) -> None:
            array = np.zeros((_field_shape(count), width), dtype=np.float32)
            source = np.asarray(model[key], dtype=np.float32).reshape(-1, width)
            array[: min(source.shape[0], array.shape[0])] = source[: array.shape[0]]
            field.from_numpy(array)

        def scalar(field: Any, key: str, count: int, dtype: np.dtype | type = np.float32) -> None:
            array = np.zeros((_field_shape(count),), dtype=dtype)
            source = np.asarray(model[key], dtype=dtype).reshape(-1)
            array[: min(source.size, array.size)] = source[: array.size]
            field.from_numpy(array)

        vector(self._body_pos, "body_pos", 3, self.body_count)
        vector(self._body_quat, "body_quat", 4, self.body_count)
        vector(self._body_ipos, "body_ipos", 3, self.body_count)
        vector(self._body_iquat, "body_iquat", 4, self.body_count)
        vector(self._body_inertia, "body_inertia", 3, self.body_count)
        scalar(self._body_mass, "body_mass", self.body_count)
        scalar(self._body_gravcomp, "body_gravcomp", self.body_count)
        scalar(self._body_parent, "body_parent", self.body_count, np.int32)
        scalar(self._jnt_parent, "jnt_parent_body", 1, np.int32)
        scalar(self._jnt_child, "jnt_child_body", 1, np.int32)
        scalar(self._jnt_qposadr, "jnt_qposadr", 1, np.int32)
        scalar(self._jnt_dofadr, "jnt_dofadr", 1, np.int32)
        vector(self._jnt_axis_parent, "jnt_axis_parent", 3, 1)
        vector(self._jnt_axis_child, "jnt_axis_child", 3, 1)
        vector(self._jnt_anchor_child, "jnt_anchor_child", 3, 1)
        scalar(self._jnt_damping, "jnt_damping", 1)
        scalar(self._jnt_stiffness, "jnt_stiffness", 1)
        scalar(self._jnt_ref, "jnt_ref", 1)
        scalar(self._jnt_ref_pos, "jnt_ref_pos", 1)
        scalar(self._jnt_armature, "jnt_armature", 1)
        scalar(self._geom_bodyid, "geom_bodyid", self.geom_count, np.int32)
        vector(self._geom_pos, "geom_pos", 3, self.geom_count)
        vector(self._geom_quat, "geom_quat", 4, self.geom_count)
        scalar(self._site_bodyid, "site_bodyid", self.site_count, np.int32)
        vector(self._site_pos, "site_pos", 3, self.site_count)
        vector(self._site_quat, "site_quat", 4, self.site_count)
        vector(self._actuator_gear, "actuator_gear", 6, self.actuator_count)
        self._root_pos[None] = np.asarray(model["root_pos"], dtype=np.float32)
        self._root_quat[None] = np.asarray(model["root_quat"], dtype=np.float32)
        self._gravity[None] = np.asarray(model["gravity"], dtype=np.float32)

    def write_state(self, state: Mapping[str, np.ndarray]) -> None:
        self._qpos.from_numpy(np.ascontiguousarray(state["qpos"], dtype=np.float32))
        self._qvel.from_numpy(np.ascontiguousarray(state["qvel"], dtype=np.float32))
        self._qacc.from_numpy(np.ascontiguousarray(state["qacc"], dtype=np.float32))
        self._ctrl.from_numpy(np.ascontiguousarray(state["ctrl"], dtype=np.float32))
        self._act.from_numpy(np.ascontiguousarray(state["act"], dtype=np.float32))

    def write_ctrl(self, ctrl: np.ndarray) -> None:
        self._ctrl.from_numpy(np.ascontiguousarray(ctrl, dtype=np.float32))

    @staticmethod
    def _torch_field(field: Any, *, name: str, device: str) -> Any:
        if not callable(getattr(field, "to_torch", None)):
            raise RuntimeError(f"static field {name!r} does not expose to_torch()")
        return field.to_torch(device=device)

    def read_device_state(self, names: tuple[str, ...]) -> DeviceBatchState:
        """Return named tensors from the fused narrow-profile fields."""

        fields = {
            "qpos": self._qpos,
            "qvel": self._qvel,
            "qacc": self._qacc,
            "ctrl": self._ctrl,
            "act": self._act,
            "body_xpos": self._body_xpos,
            "body_xquat": self._body_xquat,
            "geom_xpos": self._geom_xpos,
            "geom_xquat": self._geom_xquat,
            "site_xpos": self._site_xpos,
            "site_xquat": self._site_xquat,
        }
        unknown = sorted(set(names) - set(fields))
        if unknown:
            raise KeyError(f"unknown static device state fields: {unknown}")
        device = "cuda" if self.backend == "cuda" else "cpu"
        arrays = {
            name: self._torch_field(fields[name], name=name, device=device)
            for name in names
        }
        if "body_xpos" in arrays:
            arrays["body_xpos"] = arrays["body_xpos"][:, : self.body_count]
        if "body_xquat" in arrays:
            arrays["body_xquat"] = arrays["body_xquat"][:, : self.body_count]
        if "geom_xpos" in arrays:
            arrays["geom_xpos"] = arrays["geom_xpos"][:, : self.geom_count]
        if "geom_xquat" in arrays:
            arrays["geom_xquat"] = arrays["geom_xquat"][:, : self.geom_count]
        if "site_xpos" in arrays:
            arrays["site_xpos"] = arrays["site_xpos"][:, : self.site_count]
        if "site_xquat" in arrays:
            arrays["site_xquat"] = arrays["site_xquat"][:, : self.site_count]
        device = str(next(iter(arrays.values())).device)
        return DeviceBatchState(arrays=arrays, device=device, num_envs=self.num_envs)

    def _write_device_field(self, field: Any, value: Any, *, name: str) -> None:
        if not callable(getattr(field, "from_torch", None)):
            raise RuntimeError(f"static field {name!r} does not expose from_torch()")
        field.from_torch(value.contiguous())

    def step_device(self, control: Any) -> DeviceBatchState:
        expected = (self.num_envs, self.actuator_count)
        if tuple(getattr(control, "shape", ())) != expected:
            raise ValueError(f"device control must have shape {expected}")
        expected_device = "cuda" if self.backend == "cuda" else "cpu"
        if str(getattr(control, "device", "")) != expected_device and not (
            expected_device == "cuda" and str(getattr(control, "device", "")) == "cuda:0"
        ):
            raise RuntimeError(
                "device control and static physics fields must share a device; "
                "select an explicit sim/rl transfer mode instead"
            )
        self._write_device_field(self._ctrl, control, name="ctrl")
        self._step_kernel()
        return self.read_device_state(("qpos", "qvel", "qacc", "ctrl", "act", "body_xpos", "body_xquat", "geom_xpos", "geom_xquat", "site_xpos", "site_xquat"))

    def reset_device(self, state: Mapping[str, Any], mask: Any) -> DeviceBatchState:
        import torch

        selected = mask if hasattr(mask, "device") else torch.as_tensor(mask, dtype=torch.bool)
        current = self.read_device_state(("qpos", "qvel", "qacc", "ctrl", "act"))
        if tuple(selected.shape) != (self.num_envs,):
            raise ValueError(f"device reset mask must have shape ({self.num_envs},)")
        selected = selected.to(device=current.device, dtype=torch.bool)
        for name, field in (("qpos", self._qpos), ("qvel", self._qvel), ("qacc", self._qacc), ("ctrl", self._ctrl), ("act", self._act)):
            if name in state:
                value = state[name]
                expected = tuple(current.arrays[name].shape)
                if tuple(getattr(value, "shape", ())) != expected:
                    raise ValueError(f"device reset field {name!r} must have shape {expected}")
                merged = torch.where(selected.reshape(self.num_envs, *([1] * (len(expected) - 1))), value, current.arrays[name])
                self._write_device_field(field, merged, name=name)
        self._refresh_kernel()
        self._contact_workspace.reset(selected.detach().to("cpu").numpy())
        return self.read_device_state(("qpos", "qvel", "qacc", "ctrl", "act", "body_xpos", "body_xquat", "geom_xpos", "geom_xquat", "site_xpos", "site_xquat"))

    def read_state(self) -> dict[str, np.ndarray]:
        return {
            "qpos": self._qpos.to_numpy(),
            "qvel": self._qvel.to_numpy(),
            "qacc": self._qacc.to_numpy(),
            "ctrl": self._ctrl.to_numpy(),
            "act": self._act.to_numpy(),
            "body_xpos": self._body_xpos.to_numpy()[:, : self.body_count],
            "body_xquat": self._body_xquat.to_numpy()[:, : self.body_count],
            "geom_xpos": self._geom_xpos.to_numpy()[:, : self.geom_count],
            "geom_xquat": self._geom_xquat.to_numpy()[:, : self.geom_count],
            "site_xpos": self._site_xpos.to_numpy()[:, : self.site_count],
            "site_xquat": self._site_xquat.to_numpy()[:, : self.site_count],
        }

    def prewarm(self) -> None:
        self._refresh_kernel()

    def refresh(self) -> None:
        self._refresh_kernel()

    def step(self, substeps: int) -> None:
        if int(substeps) != self.control_substeps:
            raise ValueError(
                "static-template control_substeps is fixed at construction; "
                f"expected {self.control_substeps}, got {int(substeps)}"
            )
        self._step_kernel()

    def execution_plan_facts(self) -> Mapping[str, Any]:
        """Publish immutable layout facts without exposing private fields."""

        workspace = self._contact_workspace.resource_summary()
        return {
            "max_contact_pairs_per_world": int(
                workspace["max_contact_pairs_per_world"]
            ),
            "max_constraint_rows_per_world": int(
                workspace["max_constraint_rows_per_world"]
            ),
            "contact_workspace_slots_per_world": 0,
            "fused_kernel": True,
            "execution_route": "fused_world_local",
        }

    def render_state_source(self) -> tuple[object, str]:
        """Return the provider-owned batched render state port."""

        return self, "batched"

    def resource_summary(self) -> dict[str, int | str]:
        per_world_state = (
            self.qpos_count + 2 * self.qvel_count + 2 * self.actuator_count
        ) * 4
        per_world_state += self.body_count * (3 + 4 + 3 + 3) * 4
        per_world_state += self.geom_count * (3 + 4) * 4
        per_world_state += self.site_count * (3 + 4) * 4
        shared = (
            self.body_count * (3 + 4 + 3 + 4 + 3 + 1 + 1 + 1) * 4
            + self.geom_count * (1 + 3 + 4) * 4
            + self.site_count * (1 + 3 + 4) * 4
            + self.actuator_count * 6 * 4
        )
        # The first capability explicitly proves that every inter-body pair is
        # excluded.  No contact/broadphase/constraint rows are therefore
        # allocated, but the zero-capacity boundary is part of the diagnostic
        # contract so a later contact profile cannot silently reuse it.
        workspace_summary = self._contact_workspace.resource_summary()
        per_world_workspace = int(workspace_summary["contact_workspace_bytes"] // self.num_envs)
        per_world_reset_staging = (
            self.qpos_count + 2 * self.qvel_count + 2 * self.actuator_count
        ) * 4 * 2
        total_state = int(per_world_state * self.num_envs)
        total_workspace = int(per_world_workspace * self.num_envs)
        reset_staging = int(per_world_reset_staging * self.num_envs)
        return {
            "shared_template_bytes": int(shared),
            "per_world_state_bytes": int(per_world_state),
            "per_world_workspace_bytes": int(per_world_workspace),
            "per_world_reset_staging_bytes": int(per_world_reset_staging),
            "contact_workspace_bytes": int(workspace_summary["contact_workspace_bytes"]),
            "broadphase_workspace_bytes": int(workspace_summary["contact_workspace_bytes"]),
            "constraint_workspace_bytes": int(workspace_summary["contact_workspace_bytes"]),
            "contact_profile": "world_local_workspace_boundary",
            "workspace_addressing": workspace_summary["addressing"],
            "total_state_bytes": total_state,
            "total_workspace_bytes": total_workspace,
            "reset_staging_bytes": reset_staging,
            "total_payload_bytes": int(shared + total_state + total_workspace),
            "total_allocated_bytes_including_reset_staging": int(
                shared + total_state + total_workspace + reset_staging
            ),
            "solver_count": 1,
            "local_body_count": self.body_count,
            "local_geom_count": self.geom_count,
            "capacity_policy": "exact_batch",
        }

    def close(self) -> None:
        return None

    def reset_workspace(self, mask: np.ndarray) -> None:
        """Clear contact/row/warmstart storage for selected worlds."""

        self._contact_workspace.reset(mask)

    @ti.func
    def _world_transform(self, world, body, q):
        parent = self._body_parent[body]
        local_pos = self._body_pos[body]
        local_quat = self._body_quat[body]
        if body == self._jnt_child[0]:
            axis_child = self._jnt_axis_child[0]
            if ti.static(self.joint_type == self.JOINT_HINGE):
                local_quat = ti_quat_multiply(
                    local_quat,
                    ti_axis_angle_to_quat(axis_child, q),
                )
                rest_rot = ti_quat_to_matrix(self._body_quat[body])
                anchor_in_parent = self._body_pos[body] + rest_rot @ self._jnt_anchor_child[0]
                local_pos = anchor_in_parent - ti_quat_to_matrix(local_quat) @ self._jnt_anchor_child[0]
            elif ti.static(self.joint_type == self.JOINT_SLIDE):
                local_pos = local_pos + self._jnt_axis_parent[0] * q
        result_pos = ti.Vector.zero(ti.f32, 3)
        result_quat = ti.Vector([1.0, 0.0, 0.0, 0.0])
        if parent < 0:
            root_quat = self._root_quat[None]
            result_pos = self._root_pos[None] + ti_quat_to_matrix(root_quat) @ local_pos
            result_quat = ti_quat_normalize(ti_quat_multiply(root_quat, local_quat))
        else:
            parent_pos = self._body_xpos[world, parent]
            parent_quat = self._body_xquat[world, parent]
            result_pos = parent_pos + ti_quat_to_matrix(parent_quat) @ local_pos
            result_quat = ti_quat_normalize(ti_quat_multiply(parent_quat, local_quat))
        return result_pos, result_quat

    @ti.func
    def _refresh_world(self, world):
        q = self._qpos[world][0]
        for body in range(self.body_count):
            pos, quat = self._world_transform(world, body, q)
            self._body_xpos[world, body] = pos
            self._body_xquat[world, body] = quat
            self._body_linear_vel[world, body] = ti.Vector.zero(ti.f32, 3)
            self._body_angular_vel[world, body] = ti.Vector.zero(ti.f32, 3)

        child = self._jnt_child[0]
        parent = self._jnt_parent[0]
        parent_pos = self._root_pos[None]
        parent_quat = self._root_quat[None]
        parent_linear = ti.Vector.zero(ti.f32, 3)
        parent_angular = ti.Vector.zero(ti.f32, 3)
        if parent >= 0:
            parent_pos = self._body_xpos[world, parent]
            parent_quat = self._body_xquat[world, parent]
            parent_linear = self._body_linear_vel[world, parent]
            parent_angular = self._body_angular_vel[world, parent]
        child_pos = self._body_xpos[world, child]
        child_quat = self._body_xquat[world, child]
        axis = ti_quat_to_matrix(parent_quat) @ self._jnt_axis_parent[0]
        qdot = self._qvel[world][0]
        omega = parent_angular
        velocity = parent_linear + parent_angular.cross(child_pos - parent_pos)
        if ti.static(self.joint_type == self.JOINT_HINGE):
            omega = parent_angular + qdot * axis
            pivot = child_pos + ti_quat_to_matrix(child_quat) @ self._jnt_anchor_child[0]
            velocity = velocity + (qdot * axis).cross(child_pos - pivot)
        else:
            omega = parent_angular
            velocity = velocity + qdot * axis
        self._body_linear_vel[world, child] = velocity
        self._body_angular_vel[world, child] = omega

        for geom in range(self.geom_count):
            body = self._geom_bodyid[geom]
            body_quat = self._body_xquat[world, body]
            self._geom_xpos[world, geom] = self._body_xpos[world, body] + ti_quat_to_matrix(body_quat) @ self._geom_pos[geom]
            self._geom_xquat[world, geom] = ti_quat_normalize(
                ti_quat_multiply(body_quat, self._geom_quat[geom])
            )
        for site in range(self.site_count):
            body = self._site_bodyid[site]
            body_quat = self._body_xquat[world, body]
            self._site_xpos[world, site] = self._body_xpos[world, body] + ti_quat_to_matrix(body_quat) @ self._site_pos[site]
            self._site_xquat[world, site] = ti_quat_normalize(
                ti_quat_multiply(body_quat, self._site_quat[site])
            )

    @ti.kernel
    def _refresh_kernel(self):
        for world in range(self.num_envs):
            self._refresh_world(world)

    @ti.kernel
    def _step_kernel(self):
        for world in range(self.num_envs):
            for _ in range(self.control_substeps):
                q = self._qpos[world][0]
                qvel = self._qvel[world][0]
                parent = self._jnt_parent[0]
                parent_quat = self._root_quat[None]
                if parent >= 0:
                    parent_quat = self._body_xquat[world, parent]
                parent_rot = ti_quat_to_matrix(parent_quat)
                axis = parent_rot @ self._jnt_axis_parent[0]
                child = self._jnt_child[0]
                child_pos, child_quat = self._world_transform(world, child, q)
                child_rot = ti_quat_to_matrix(child_quat)
                pivot = child_pos + child_rot @ self._jnt_anchor_child[0]
                com = child_pos + child_rot @ self._body_ipos[child]
                force = self._gravity[None] * self._body_mass[child] * (1.0 - self._body_gravcomp[child])
                torque = (com - pivot).cross(force).dot(axis)
                inertia_rot = child_rot @ ti_quat_to_matrix(self._body_iquat[child])
                inertia_diag = self._body_inertia[child]
                inertia_world = inertia_rot @ ti.Matrix([[inertia_diag[0], 0.0, 0.0], [0.0, inertia_diag[1], 0.0], [0.0, 0.0, inertia_diag[2]]]) @ inertia_rot.transpose()
                mass_eff = self._body_mass[child] + self._jnt_armature[0]
                if ti.static(self.joint_type == self.JOINT_HINGE):
                    lever = (com - pivot).cross(axis)
                    mass_eff = axis.dot(inertia_world @ axis) + self._body_mass[child] * lever.dot(lever) + self._jnt_armature[0]
                else:
                    torque = force.dot(axis)
                motor = 0.0
                for actuator in range(self.actuator_count):
                    motor += self._ctrl[world][actuator] * self._actuator_gear[actuator][0]
                damping = self._jnt_damping[0]
                stiffness = self._jnt_stiffness[0]
                passive = -damping * qvel - stiffness * (q - self._jnt_ref[0])
                denominator = mass_eff
                if ti.static(self.integrator == "implicitfast"):
                    denominator = denominator + self.physics_dt * damping + self.physics_dt * self.physics_dt * stiffness
                qacc = (motor + torque + passive) / ti.max(denominator, 1.0e-8)
                qvel = qvel + self.physics_dt * qacc
                q = q + self.physics_dt * qvel
                self._qacc[world][0] = qacc
                self._qvel[world][0] = qvel
                self._qpos[world][0] = q
            self._refresh_world(world)
