"""Optional Taichi FK backend for the static-template articulated runtime.

The backend owns only immutable local topology/constants.  Per-world state and
outputs remain Torch tensors and are passed to Taichi as external CUDA/CPU
ndarrays, so the public device-field contract does not change.  The Torch FK
path remains the default and is the fallback for unsupported Taichi runtimes.
"""

from collections.abc import Mapping

import numpy as np
import taichi as ti


NdarrayF32_1 = ti.types.ndarray(dtype=ti.f32, ndim=1)
NdarrayF32_2 = ti.types.ndarray(dtype=ti.f32, ndim=2)
NdarrayF32_3 = ti.types.ndarray(dtype=ti.f32, ndim=3)
NdarrayF32_4 = ti.types.ndarray(dtype=ti.f32, ndim=4)
NdarrayI32_1 = ti.types.ndarray(dtype=ti.i32, ndim=1)


@ti.data_oriented
class StaticTemplateTaichiFK:
    """Fixed-topology FK and geom transform kernels.

    The topology is copied into Taichi fields once during construction.  The
    hot path receives only persistent Torch state/output arrays.  Runtime
    scalar counts are fields rather than Python-side early-exit reads, keeping
    CUDA execution asynchronous.
    """

    JOINT_FREE = 0
    JOINT_BALL = 1
    JOINT_HINGE = 2
    JOINT_SLIDE = 3
    JOINT_UNIVERSAL = 4

    def __init__(self, *, model: Mapping[str, np.ndarray], body_routes: tuple, geom_bodies: tuple, site_bodies: tuple):
        self.n_bodies = int(model["n_bodies"])
        self.n_joints = int(model["n_joints"])
        self.n_geoms = int(model["n_geoms"])
        self.n_sites = int(model["n_sites"])
        self.max_joints_per_body = max(
            1,
            max((len(route[2]) for route in body_routes), default=1),
        )

        self.body_count = ti.field(ti.i32, shape=())
        self.joint_count = ti.field(ti.i32, shape=())
        self.geom_count = ti.field(ti.i32, shape=())
        self.site_count = ti.field(ti.i32, shape=())
        self.body_count[None] = self.n_bodies
        self.joint_count[None] = self.n_joints
        self.geom_count[None] = self.n_geoms
        self.site_count[None] = self.n_sites

        self.body_parent = ti.field(ti.i32, shape=self.n_bodies)
        self.body_joint_start = ti.field(ti.i32, shape=self.n_bodies)
        self.body_joint_count = ti.field(ti.i32, shape=self.n_bodies)
        self.joint_type = ti.field(ti.i32, shape=self.n_joints)
        self.joint_qpos_adr = ti.field(ti.i32, shape=self.n_joints)
        self.joint_dof_adr = ti.field(ti.i32, shape=self.n_joints)
        self.joint_parent_body = ti.field(ti.i32, shape=self.n_joints)
        self.joint_child_body = ti.field(ti.i32, shape=self.n_joints)
        self.geom_body = ti.field(ti.i32, shape=max(1, self.n_geoms))
        self.site_body = ti.field(ti.i32, shape=max(1, self.n_sites))

        self.body_local_pos = ti.Vector.field(3, ti.f32, shape=self.n_bodies)
        self.body_local_quat = ti.Vector.field(4, ti.f32, shape=self.n_bodies)
        self.body_local_rot = ti.Matrix.field(3, 3, ti.f32, shape=self.n_bodies)
        self.joint_axis_parent = ti.Vector.field(3, ti.f32, shape=self.n_joints)
        self.joint_axis_child = ti.Vector.field(3, ti.f32, shape=self.n_joints)
        self.joint_anchor_child = ti.Vector.field(3, ti.f32, shape=self.n_joints)
        self.geom_local_pos = ti.Vector.field(3, ti.f32, shape=max(1, self.n_geoms))
        self.geom_local_quat = ti.Vector.field(4, ti.f32, shape=max(1, self.n_geoms))
        self.geom_local_rot = ti.Matrix.field(3, 3, ti.f32, shape=max(1, self.n_geoms))
        self.site_local_pos = ti.Vector.field(3, ti.f32, shape=max(1, self.n_sites))
        self.site_local_quat = ti.Vector.field(4, ti.f32, shape=max(1, self.n_sites))
        self.root_pos = ti.Vector.field(3, ti.f32, shape=())
        self.root_quat = ti.Vector.field(4, ti.f32, shape=())
        self.root_rot = ti.Matrix.field(3, 3, ti.f32, shape=())

        self._load_static_fields(model, body_routes, geom_bodies, site_bodies)

    @staticmethod
    def _array(model: Mapping[str, np.ndarray], name: str, shape: tuple[int, ...], dtype) -> np.ndarray:
        value = np.asarray(model.get(name, np.zeros(shape, dtype=dtype)), dtype=dtype)
        if value.shape != shape:
            raise ValueError(f"Taichi FK model field {name!r} has shape {value.shape}, expected {shape}")
        return np.ascontiguousarray(value)

    def _load_static_fields(self, model, body_routes, geom_bodies, site_bodies) -> None:
        body_parent = np.asarray([int(route[1]) for route in body_routes], dtype=np.int32)
        body_joint_start = np.asarray(
            [int(route[2][0][0]) if route[2] else 0 for route in body_routes],
            dtype=np.int32,
        )
        body_joint_count = np.asarray([len(route[2]) for route in body_routes], dtype=np.int32)
        self.body_parent.from_numpy(body_parent)
        self.body_joint_start.from_numpy(body_joint_start)
        self.body_joint_count.from_numpy(body_joint_count)

        self.joint_type.from_numpy(self._array(model, "jnt_type", (self.n_joints,), np.int32))
        self.joint_qpos_adr.from_numpy(self._array(model, "jnt_qposadr", (self.n_joints,), np.int32))
        self.joint_dof_adr.from_numpy(self._array(model, "jnt_dofadr", (self.n_joints,), np.int32))
        self.joint_parent_body.from_numpy(self._array(model, "jnt_parent_body", (self.n_joints,), np.int32))
        self.joint_child_body.from_numpy(self._array(model, "jnt_child_body", (self.n_joints,), np.int32))

        self.body_local_pos.from_numpy(self._array(model, "body_pos_local", (self.n_bodies, 3), np.float32))
        self.body_local_quat.from_numpy(self._array(model, "body_quat_local", (self.n_bodies, 4), np.float32))
        self.body_local_rot.from_numpy(self._array(model, "body_rot_local", (self.n_bodies, 3, 3), np.float32))
        self.joint_axis_parent.from_numpy(self._array(model, "jnt_axis_parent", (self.n_joints, 3), np.float32))
        self.joint_axis_child.from_numpy(self._array(model, "jnt_axis_child", (self.n_joints, 3), np.float32))
        self.joint_anchor_child.from_numpy(self._array(model, "jnt_anchor_child", (self.n_joints, 3), np.float32))

        geom_body_values = np.asarray(geom_bodies, dtype=np.int32)
        if self.n_geoms:
            self.geom_body.from_numpy(geom_body_values)
        else:
            self.geom_body.from_numpy(np.zeros((1,), dtype=np.int32))
        site_body_values = np.asarray(site_bodies, dtype=np.int32)
        if self.n_sites:
            self.site_body.from_numpy(site_body_values)
        else:
            self.site_body.from_numpy(np.zeros((1,), dtype=np.int32))

        geom_pos = self._array(model, "geom_pos", (self.n_geoms, 3), np.float32)
        geom_quat = self._array(model, "geom_quat", (self.n_geoms, 4), np.float32)
        geom_rot = self._array(model, "geom_rot_local", (self.n_geoms, 3, 3), np.float32)
        if self.n_geoms:
            self.geom_local_pos.from_numpy(geom_pos)
            self.geom_local_quat.from_numpy(geom_quat)
            self.geom_local_rot.from_numpy(geom_rot)
        else:
            self.geom_local_pos.from_numpy(np.zeros((1, 3), dtype=np.float32))
            self.geom_local_quat.from_numpy(np.asarray([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32))
            self.geom_local_rot.from_numpy(np.eye(3, dtype=np.float32)[None])

        site_pos = self._array(model, "site_pos", (self.n_sites, 3), np.float32)
        site_quat = self._array(model, "site_quat", (self.n_sites, 4), np.float32)
        if self.n_sites:
            self.site_local_pos.from_numpy(site_pos)
            self.site_local_quat.from_numpy(site_quat)
        else:
            self.site_local_pos.from_numpy(np.zeros((1, 3), dtype=np.float32))
            self.site_local_quat.from_numpy(np.asarray([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32))

        self.root_pos.from_numpy(self._array(model, "root_pos", (3,), np.float32))
        self.root_quat.from_numpy(self._normalize_numpy(self._array(model, "root_quat", (4,), np.float32)))
        self.root_rot.from_numpy(self._quat_to_matrix_numpy(self.root_quat.to_numpy()))

    @staticmethod
    def _normalize_numpy(value: np.ndarray) -> np.ndarray:
        norm = float(np.linalg.norm(value))
        if norm < 1.0e-8:
            return np.asarray((1.0, 0.0, 0.0, 0.0), dtype=np.float32)
        return np.asarray(value / norm, dtype=np.float32)

    @staticmethod
    def _quat_to_matrix_numpy(value: np.ndarray) -> np.ndarray:
        w, x, y, z = [float(item) for item in value]
        return np.asarray(
            (
                (1.0 - 2.0 * y * y - 2.0 * z * z, 2.0 * x * y - 2.0 * z * w, 2.0 * x * z + 2.0 * y * w),
                (2.0 * x * y + 2.0 * z * w, 1.0 - 2.0 * x * x - 2.0 * z * z, 2.0 * y * z - 2.0 * x * w),
                (2.0 * x * z - 2.0 * y * w, 2.0 * y * z + 2.0 * x * w, 1.0 - 2.0 * x * x - 2.0 * y * y),
            ),
            dtype=np.float32,
        )

    @ti.func
    def _quat_normalize(self, q):
        norm = ti.sqrt(q.dot(q))
        result = ti.Vector([1.0, 0.0, 0.0, 0.0])
        if norm >= 1.0e-8:
            result = q / norm
        return result

    @ti.func
    def _quat_mul(self, a, b):
        aw, ax, ay, az = a[0], a[1], a[2], a[3]
        bw, bx, by, bz = b[0], b[1], b[2], b[3]
        return ti.Vector(
            [
                aw * bw - ax * bx - ay * by - az * bz,
                aw * bx + ax * bw + ay * bz - az * by,
                aw * by - ax * bz + ay * bw + az * bx,
                aw * bz + ax * by - ay * bx + az * bw,
            ]
        )

    @ti.func
    def _quat_to_matrix(self, q):
        qn = self._quat_normalize(q)
        w, x, y, z = qn[0], qn[1], qn[2], qn[3]
        return ti.Matrix(
            [
                [1.0 - 2.0 * y * y - 2.0 * z * z, 2.0 * x * y - 2.0 * z * w, 2.0 * x * z + 2.0 * y * w],
                [2.0 * x * y + 2.0 * z * w, 1.0 - 2.0 * x * x - 2.0 * z * z, 2.0 * y * z - 2.0 * x * w],
                [2.0 * x * z - 2.0 * y * w, 2.0 * y * z + 2.0 * x * w, 1.0 - 2.0 * x * x - 2.0 * y * y],
            ]
        )

    @ti.func
    def _axis_angle(self, axis, angle):
        half = angle * 0.5
        return ti.Vector([ti.cos(half), axis[0] * ti.sin(half), axis[1] * ti.sin(half), axis[2] * ti.sin(half)])

    @ti.func
    def _load_vec3(self, array: ti.template(), world, index):
        return ti.Vector([array[world, index, 0], array[world, index, 1], array[world, index, 2]])

    @ti.func
    def _load_vec4(self, array: ti.template(), world, index):
        return ti.Vector([array[world, index, 0], array[world, index, 1], array[world, index, 2], array[world, index, 3]])

    @ti.func
    def _load_mat3(self, array: ti.template(), world, index):
        return ti.Matrix(
            [
                [array[world, index, 0, 0], array[world, index, 0, 1], array[world, index, 0, 2]],
                [array[world, index, 1, 0], array[world, index, 1, 1], array[world, index, 1, 2]],
                [array[world, index, 2, 0], array[world, index, 2, 1], array[world, index, 2, 2]],
            ]
        )

    @ti.func
    def _store_vec3(self, array: ti.template(), world, index, value):
        array[world, index, 0] = value[0]
        array[world, index, 1] = value[1]
        array[world, index, 2] = value[2]

    @ti.func
    def _store_vec4(self, array: ti.template(), world, index, value):
        array[world, index, 0] = value[0]
        array[world, index, 1] = value[1]
        array[world, index, 2] = value[2]
        array[world, index, 3] = value[3]

    @ti.func
    def _store_mat3(self, array: ti.template(), world, index, value):
        for i in ti.static(range(3)):
            for j in ti.static(range(3)):
                array[world, index, i, j] = value[i, j]

    @ti.kernel
    def refresh_pose(
        self,
        qpos: NdarrayF32_2,
        body_xpos: NdarrayF32_3,
        body_xquat: NdarrayF32_3,
        body_xmat: NdarrayF32_4,
        geom_xpos: NdarrayF32_3,
        geom_xquat: NdarrayF32_3,
        geom_xmat: NdarrayF32_4,
        site_xpos: NdarrayF32_3,
        site_xquat: NdarrayF32_3,
        xanchor: NdarrayF32_3,
        xaxis: NdarrayF32_3,
        univ_axis0: NdarrayF32_3,
        univ_axis1: NdarrayF32_3,
    ):
        for world in range(qpos.shape[0]):
            self._refresh_pose_world(
                world,
                qpos,
                body_xpos,
                body_xquat,
                body_xmat,
                geom_xpos,
                geom_xquat,
                geom_xmat,
                site_xpos,
                site_xquat,
                xanchor,
                xaxis,
                univ_axis0,
                univ_axis1,
            )

    @ti.kernel
    def refresh_pose_selected(
        self,
        world_ids: NdarrayI32_1,
        world_count: ti.i32,
        qpos: NdarrayF32_2,
        body_xpos: NdarrayF32_3,
        body_xquat: NdarrayF32_3,
        body_xmat: NdarrayF32_4,
        geom_xpos: NdarrayF32_3,
        geom_xquat: NdarrayF32_3,
        geom_xmat: NdarrayF32_4,
        site_xpos: NdarrayF32_3,
        site_xquat: NdarrayF32_3,
        xanchor: NdarrayF32_3,
        xaxis: NdarrayF32_3,
        univ_axis0: NdarrayF32_3,
        univ_axis1: NdarrayF32_3,
    ):
        for local_id in range(world_ids.shape[0]):
            if local_id < world_count:
                self._refresh_pose_world(
                    world_ids[local_id],
                    qpos,
                    body_xpos,
                    body_xquat,
                    body_xmat,
                    geom_xpos,
                    geom_xquat,
                    geom_xmat,
                    site_xpos,
                    site_xquat,
                    xanchor,
                    xaxis,
                    univ_axis0,
                    univ_axis1,
                )

    @ti.func
    def _refresh_pose_world(
        self,
        world,
        qpos: ti.template(),
        body_xpos: ti.template(),
        body_xquat: ti.template(),
        body_xmat: ti.template(),
        geom_xpos: ti.template(),
        geom_xquat: ti.template(),
        geom_xmat: ti.template(),
        site_xpos: ti.template(),
        site_xquat: ti.template(),
        xanchor: ti.template(),
        xaxis: ti.template(),
        univ_axis0: ti.template(),
        univ_axis1: ti.template(),
    ):
        for body in range(self.body_count[None]):
            start = self.body_joint_start[body]
            count = self.body_joint_count[body]
            first_type = -1
            if count > 0:
                first_type = self.joint_type[start]
            free = first_type == self.JOINT_FREE
            pos = ti.Vector([0.0, 0.0, 0.0])
            quat = ti.Vector([1.0, 0.0, 0.0, 0.0])
            if free:
                qp = self.joint_qpos_adr[start]
                pos = ti.Vector([qpos[world, qp], qpos[world, qp + 1], qpos[world, qp + 2]])
                quat = ti.Vector([qpos[world, qp + 3], qpos[world, qp + 4], qpos[world, qp + 5], qpos[world, qp + 6]])
                quat = self._quat_normalize(quat)
            else:
                pos = self.body_local_pos[body]
                quat = self.body_local_quat[body]
                rest_pos = pos
                rest_rot = self.body_local_rot[body]
                for offset in range(self.max_joints_per_body):
                    if offset < count:
                        joint = start + offset
                        typ = self.joint_type[joint]
                        qa = self.joint_qpos_adr[joint]
                        if typ == self.JOINT_HINGE:
                            quat = self._quat_mul(quat, self._axis_angle(self.joint_axis_child[joint], qpos[world, qa]))
                            anchor_parent = rest_pos + rest_rot @ self.joint_anchor_child[joint]
                            pos = anchor_parent - self._quat_to_matrix(quat) @ self.joint_anchor_child[joint]
                        elif typ == self.JOINT_SLIDE:
                            pos = pos + self.joint_axis_parent[joint] * qpos[world, qa]
                        elif typ == self.JOINT_BALL:
                            quat = self._quat_mul(
                                quat,
                                self._quat_normalize(ti.Vector([qpos[world, qa], qpos[world, qa + 1], qpos[world, qa + 2], qpos[world, qa + 3]])),
                            )
                            anchor_parent = rest_pos + rest_rot @ self.joint_anchor_child[joint]
                            pos = anchor_parent - self._quat_to_matrix(quat) @ self.joint_anchor_child[joint]
                        elif typ == self.JOINT_UNIVERSAL:
                            qx = self._axis_angle(ti.Vector([1.0, 0.0, 0.0]), qpos[world, qa])
                            qy = self._axis_angle(ti.Vector([0.0, 1.0, 0.0]), qpos[world, qa + 1])
                            quat = self._quat_mul(quat, self._quat_mul(qx, qy))
                            anchor_parent = rest_pos + rest_rot @ self.joint_anchor_child[joint]
                            pos = anchor_parent - self._quat_to_matrix(quat) @ self.joint_anchor_child[joint]

            parent = self.body_parent[body]
            if parent >= 0:
                parent_quat = self._load_vec4(body_xquat, world, parent)
                parent_mat = self._load_mat3(body_xmat, world, parent)
                pos = self._load_vec3(body_xpos, world, parent) + parent_mat @ pos
                quat = self._quat_normalize(self._quat_mul(parent_quat, quat))
            elif not free:
                pos = self.root_pos[None] + self.root_rot[None] @ pos
                quat = self._quat_normalize(self._quat_mul(self.root_quat[None], quat))

            body_xpos[world, body, 0] = pos[0]
            body_xpos[world, body, 1] = pos[1]
            body_xpos[world, body, 2] = pos[2]
            self._store_vec4(body_xquat, world, body, quat)
            self._store_mat3(body_xmat, world, body, self._quat_to_matrix(quat))

        for geom in range(self.geom_count[None]):
            body = self.geom_body[geom]
            body_pos = self._load_vec3(body_xpos, world, body)
            body_mat = self._load_mat3(body_xmat, world, body)
            body_quat = self._load_vec4(body_xquat, world, body)
            self._store_vec3(geom_xpos, world, geom, body_pos + body_mat @ self.geom_local_pos[geom])
            self._store_vec4(geom_xquat, world, geom, self._quat_normalize(self._quat_mul(body_quat, self.geom_local_quat[geom])))
            self._store_mat3(geom_xmat, world, geom, body_mat @ self.geom_local_rot[geom])

        for site in range(self.site_count[None]):
            body = self.site_body[site]
            body_pos = self._load_vec3(body_xpos, world, body)
            body_mat = self._load_mat3(body_xmat, world, body)
            body_quat = self._load_vec4(body_xquat, world, body)
            self._store_vec3(site_xpos, world, site, body_pos + body_mat @ self.site_local_pos[site])
            self._store_vec4(site_xquat, world, site, self._quat_normalize(self._quat_mul(body_quat, self.site_local_quat[site])))

        for joint in range(self.joint_count[None]):
            child = self.joint_child_body[joint]
            child_pos = self._load_vec3(body_xpos, world, child)
            child_mat = self._load_mat3(body_xmat, world, child)
            self._store_vec3(xanchor, world, joint, child_pos + child_mat @ self.joint_anchor_child[joint])
            parent = self.joint_parent_body[joint]
            parent_mat = self.root_rot[None]
            if parent >= 0:
                parent_mat = self._load_mat3(body_xmat, world, parent)
            self._store_vec3(xaxis, world, joint, parent_mat @ self.joint_axis_parent[joint])
            self._store_vec3(univ_axis0, world, joint, ti.Vector([parent_mat[0, 0], parent_mat[1, 0], parent_mat[2, 0]]))
            self._store_vec3(univ_axis1, world, joint, ti.Vector([parent_mat[0, 1], parent_mat[1, 1], parent_mat[2, 1]]))

    @ti.kernel
    def refresh_velocity(
        self,
        qvel: NdarrayF32_2,
        body_xpos: NdarrayF32_3,
        body_xmat: NdarrayF32_4,
        body_linear_vel: NdarrayF32_3,
        body_angular_vel: NdarrayF32_3,
    ):
        for world in range(qvel.shape[0]):
            self._refresh_velocity_world(
                world,
                qvel,
                body_xpos,
                body_xmat,
                body_linear_vel,
                body_angular_vel,
            )

    @ti.kernel
    def refresh_velocity_selected(
        self,
        world_ids: NdarrayI32_1,
        world_count: ti.i32,
        qvel: NdarrayF32_2,
        body_xpos: NdarrayF32_3,
        body_xmat: NdarrayF32_4,
        body_linear_vel: NdarrayF32_3,
        body_angular_vel: NdarrayF32_3,
    ):
        for local_id in range(world_ids.shape[0]):
            if local_id < world_count:
                self._refresh_velocity_world(
                    world_ids[local_id],
                    qvel,
                    body_xpos,
                    body_xmat,
                    body_linear_vel,
                    body_angular_vel,
                )

    @ti.func
    def _refresh_velocity_world(
        self,
        world,
        qvel: ti.template(),
        body_xpos: ti.template(),
        body_xmat: ti.template(),
        body_linear_vel: ti.template(),
        body_angular_vel: ti.template(),
    ):
        for body in range(self.body_count[None]):
            start = self.body_joint_start[body]
            count = self.body_joint_count[body]
            first_type = -1
            if count > 0:
                first_type = self.joint_type[start]
            if first_type == self.JOINT_FREE:
                dof = self.joint_dof_adr[start]
                self._store_vec3(body_linear_vel, world, body, ti.Vector([qvel[world, dof], qvel[world, dof + 1], qvel[world, dof + 2]]))
                self._store_vec3(body_angular_vel, world, body, ti.Vector([qvel[world, dof + 3], qvel[world, dof + 4], qvel[world, dof + 5]]))
            else:
                parent = self.body_parent[body]
                position = self._load_vec3(body_xpos, world, body)
                linear = ti.Vector([0.0, 0.0, 0.0])
                angular = ti.Vector([0.0, 0.0, 0.0])
                if parent >= 0:
                    parent_pos = self._load_vec3(body_xpos, world, parent)
                    parent_linear = self._load_vec3(body_linear_vel, world, parent)
                    parent_angular = self._load_vec3(body_angular_vel, world, parent)
                    linear = parent_linear + parent_angular.cross(position - parent_pos)
                    angular = parent_angular
                else:
                    parent_pos = self.root_pos[None]
                parent_rot = self.root_rot[None]
                if parent >= 0:
                    parent_rot = self._load_mat3(body_xmat, world, parent)
                body_rot = self._load_mat3(body_xmat, world, body)
                for offset in range(self.max_joints_per_body):
                    if offset < count:
                        joint = start + offset
                        typ = self.joint_type[joint]
                        dof = self.joint_dof_adr[joint]
                        if typ == self.JOINT_HINGE:
                            axis = parent_rot @ self.joint_axis_parent[joint]
                            relative = qvel[world, dof] * axis
                            pivot = position + body_rot @ self.joint_anchor_child[joint]
                            linear = linear + relative.cross(position - pivot)
                            angular = angular + relative
                        elif typ == self.JOINT_SLIDE:
                            axis = parent_rot @ self.joint_axis_parent[joint]
                            linear = linear + qvel[world, dof] * axis
                        elif typ == self.JOINT_BALL:
                            relative = ti.Vector([qvel[world, dof], qvel[world, dof + 1], qvel[world, dof + 2]])
                            pivot = position + body_rot @ self.joint_anchor_child[joint]
                            linear = linear + relative.cross(position - pivot)
                            angular = angular + relative
                        elif typ == self.JOINT_UNIVERSAL:
                            axis0 = ti.Vector([parent_rot[0, 0], parent_rot[1, 0], parent_rot[2, 0]])
                            axis1 = ti.Vector([parent_rot[0, 1], parent_rot[1, 1], parent_rot[2, 1]])
                            relative = qvel[world, dof] * axis0 + qvel[world, dof + 1] * axis1
                            pivot = position + body_rot @ self.joint_anchor_child[joint]
                            linear = linear + relative.cross(position - pivot)
                            angular = angular + relative
                self._store_vec3(body_linear_vel, world, body, linear)
                self._store_vec3(body_angular_vel, world, body, angular)


__all__ = ["StaticTemplateTaichiFK"]
