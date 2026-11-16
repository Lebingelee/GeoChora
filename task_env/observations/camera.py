"""Camera sensor pose resolver for observation acquisition."""

from __future__ import annotations

import math

import numpy as np

from ..environment import (
    CameraMetadata,
    CameraPose,
    CameraSpec,
    RuntimeSnapshot,
)
from ..assembly import TaskReferences
from .camera_geometry import (
    normalize_quat_wxyz,
    quat_multiply_wxyz,
    rotate_vector_wxyz,
    transform_matrix,
)


_FORWARD_LOCAL = np.array((1.0, 0.0, 0.0), dtype=np.float32)
_UP_LOCAL = np.array((0.0, 0.0, 1.0), dtype=np.float32)


class CameraSensor:
    """Resolve a CameraSpec against compiled task references and runtime snapshots."""

    def __init__(self, *, spec: CameraSpec, references: TaskReferences) -> None:
        self.spec = spec
        self.references = references
        self._parent_id = self._resolve_parent_id()

    @property
    def name(self) -> str:
        return self.spec.name

    def resolve_pose(self, snapshot: RuntimeSnapshot) -> CameraPose:
        parent_position, parent_quat = self._parent_pose(snapshot)
        local_position = np.asarray(self.spec.position, dtype=np.float32)
        local_quat = normalize_quat_wxyz(self.spec.quaternion_wxyz)
        world_quat = quat_multiply_wxyz(parent_quat, local_quat)
        world_position = parent_position + rotate_vector_wxyz(
            parent_quat,
            local_position,
        )
        forward = rotate_vector_wxyz(world_quat, _FORWARD_LOCAL)
        up = rotate_vector_wxyz(world_quat, _UP_LOCAL)
        return CameraPose(
            position=world_position,
            quaternion_wxyz=world_quat,
            look_at=world_position + forward,
            up=up,
        )

    def resolve_device_pose(self, state, *, world_offsets=None):
        """Resolve batched camera position/look-at/up from named device poses.

        Positions are environment-local until optional renderer layout offsets
        are applied here. Quaternions use WXYZ; local forward is +X and up +Z.
        """
        import torch

        count, device = state.num_envs, state.device
        if self.spec.frame == 'world':
            parent_position = torch.zeros((count, 3), dtype=torch.float32, device=device)
            parent_quaternion = torch.zeros((count, 4), dtype=torch.float32, device=device)
            parent_quaternion[:, 0] = 1.
        else:
            prefix = 'body' if self.spec.frame == 'body' else 'frame'
            parent_position = state.arrays[f'{prefix}_position'][:, self._parent_id]
            parent_quaternion = state.arrays[f'{prefix}_orientation'][:, self._parent_id]
        norms = torch.linalg.vector_norm(parent_quaternion, dim=-1, keepdim=True)
        if (not bool(torch.isfinite(parent_position).all())
                or not bool(torch.isfinite(parent_quaternion).all()) or bool((norms < 1e-12).any())):
            raise ValueError('camera parent device pose must be finite with a nonzero quaternion')
        parent_quaternion = parent_quaternion / norms
        local_q = torch.as_tensor(normalize_quat_wxyz(self.spec.quaternion_wxyz),
                                  dtype=torch.float32, device=device)
        local_p = torch.as_tensor(self.spec.position, dtype=torch.float32, device=device).expand(count, -1)

        def rotate(quaternion, vector):
            xyz = quaternion[..., 1:]
            return vector + 2. * torch.linalg.cross(xyz, torch.linalg.cross(xyz, vector, dim=-1)
                                                   + quaternion[..., :1] * vector, dim=-1)

        parent_xyz = parent_quaternion[:, 1:]
        world_q = torch.cat((parent_quaternion[:, :1] * local_q[0]
                             - (parent_xyz * local_q[1:]).sum(dim=1, keepdim=True),
                             parent_quaternion[:, :1] * local_q[1:]
                             + local_q[0] * parent_xyz
                             + torch.linalg.cross(parent_xyz, local_q[1:].expand(count, -1), dim=-1)), dim=1)
        position = parent_position + rotate(parent_quaternion, local_p)
        if world_offsets is not None:
            if tuple(world_offsets.shape) != (count, 3) or str(world_offsets.device) != device:
                raise ValueError('camera world offsets must be device-resident (B, 3)')
            position = position + world_offsets
        forward = torch.tensor((1., 0., 0.), dtype=torch.float32, device=device).expand(count, -1)
        up = torch.tensor((0., 0., 1.), dtype=torch.float32, device=device).expand(count, -1)
        return torch.stack((position, position + rotate(world_q, forward), rotate(world_q, up)), dim=1)

    def metadata(self, snapshot: RuntimeSnapshot) -> CameraMetadata:
        pose = self.resolve_pose(snapshot)
        return CameraMetadata(
            name=self.spec.name,
            width=self.spec.width,
            height=self.spec.height,
            rgb=self.spec.rgb,
            depth=self.spec.depth,
            frame=self.spec.frame,
            parent=self.spec.parent,
            fov_y=self.spec.fov_y,
            near=self.spec.near,
            far=self.spec.far,
            pose=pose,
            intrinsic=self._intrinsic_matrix(),
            extrinsic=transform_matrix(pose.position, pose.quaternion_wxyz),
        )

    def _resolve_parent_id(self) -> int | None:
        parent = self.spec.parent
        if self.spec.frame == "world":
            return None
        if parent is None:
            raise ValueError(f"camera {self.spec.name} requires a parent")
        table = (
            self.references.names.bodies
            if self.spec.frame == "body"
            else self.references.names.sites
        )
        if parent not in table:
            raise KeyError(
                f"camera {self.spec.name} cannot resolve {self.spec.frame} parent {parent!r}"
            )
        return int(table[parent])

    def _parent_pose(self, snapshot: RuntimeSnapshot) -> tuple[np.ndarray, np.ndarray]:
        if self.spec.frame == "world":
            return (
                np.zeros(3, dtype=np.float32),
                np.array((1.0, 0.0, 0.0, 0.0), dtype=np.float32),
            )
        if self.spec.frame == "body":
            if snapshot.body_xpos is None or snapshot.body_xquat is None:
                raise ValueError("body camera requires body pose in RuntimeSnapshot")
            return (
                np.asarray(snapshot.body_xpos[self._parent_id], dtype=np.float32),
                normalize_quat_wxyz(snapshot.body_xquat[self._parent_id]),
            )
        if snapshot.site_xpos is None or snapshot.site_xquat is None:
            raise ValueError("site camera requires site pose in RuntimeSnapshot")
        return (
            np.asarray(snapshot.site_xpos[self._parent_id], dtype=np.float32),
            normalize_quat_wxyz(snapshot.site_xquat[self._parent_id]),
        )

    def _intrinsic_matrix(self) -> np.ndarray:
        fy = 0.5 * float(self.spec.height) / math.tan(0.5 * float(self.spec.fov_y))
        fx = fy
        return np.array(
            (
                (fx, 0.0, 0.5 * float(self.spec.width)),
                (0.0, fy, 0.5 * float(self.spec.height)),
                (0.0, 0.0, 1.0),
            ),
            dtype=np.float32,
        )
