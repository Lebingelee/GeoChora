"""Source-derived articulated and free-body tensor layout for one Isaac scene.

The owner remains ``IsaacNativeBatch``. This helper only resolves the batch's
joint, rigid-body and frame coordinates and lowers state/control tensors.
"""
from __future__ import annotations

import math


def _relative_path(entry, path):
    if path.startswith('/'):
        prefix = entry.rstrip('/') + '/'
        if not path.startswith(prefix):
            raise ValueError('USD binding lies outside the admitted source entry')
        path = path[len(prefix):]
    if not path or '..' in path.split('/'):
        raise ValueError('USD binding must resolve below the source entry')
    return path


def _rotate(quaternion, vectors):
    """Rotate vectors by wxyz unit quaternions, broadcasting over rows."""
    import torch
    xyz = quaternion[..., 1:]
    twice_cross = 2 * torch.linalg.cross(xyz, vectors)
    return vectors + quaternion[..., :1] * twice_cross + torch.linalg.cross(xyz, twice_cross)


def prepare_articulation(stage, roots, request, usd_physics, physx_schema):
    """Apply the source-declared armature and verify joint equality lowering."""
    dynamics = request['joint_dynamics']
    equalities = {frozenset(pair) for pair in request['joint_equalities']}
    facts = []
    for root in roots:
        prims = [prim for prim in stage.Traverse() if str(prim.GetPath()).startswith(root + '/')]
        joints = {}
        for prim in prims:
            if prim.IsA(usd_physics.RevoluteJoint) or prim.IsA(usd_physics.PrismaticJoint):
                name = prim.GetName()
                if name in joints:
                    raise ValueError(f'USD articulation has duplicate joint name {name!r}')
                joints[name] = prim
        if set(joints) != set(dynamics):
            raise ValueError('USD articulation joints differ from source-declared scalar joints')
        for name, values in dynamics.items():
            armature = float(values['armature'])
            if not math.isfinite(armature) or armature < 0:
                raise ValueError('source armature must be finite and nonnegative')
            api = physx_schema.PhysxJointAPI.Apply(joints[name])
            if not api or api.CreateArmatureAttr().Set(armature) is False:
                raise ValueError('PhysX could not receive the source joint armature')
            if not math.isclose(float(api.GetArmatureAttr().Get()), armature, abs_tol=1e-6):
                raise ValueError('PhysX joint armature readback differs from source')
        observed = set()
        for name, joint in joints.items():
            for axis in ('transX', 'rotX'):
                if not joint.HasAPI(physx_schema.PhysxMimicJointAPI, axis):
                    continue
                relationship = joint.GetRelationship(f'physxMimicJoint:{axis}:referenceJoint')
                targets = relationship.GetTargets() if relationship else []
                if len(targets) != 1:
                    raise ValueError('PhysX mimic must reference one source joint')
                reference = stage.GetPrimAtPath(targets[0])
                if not reference or not str(reference.GetPath()).startswith(root + '/'):
                    raise ValueError('PhysX mimic references a different environment')
                pair = frozenset((name, reference.GetName()))
                if len(pair) != 2 or pair not in equalities or pair in observed:
                    raise ValueError('PhysX mimic differs from source joint equalities')
                for field, expected in (('gearing', 1.), ('offset', 0.)):
                    attr = joint.GetAttribute(f'physxMimicJoint:{axis}:{field}')
                    if not attr or not math.isclose(float(attr.Get()), expected, abs_tol=1e-6):
                        raise ValueError('PhysX mimic coefficients differ from source equality')
                observed.add(pair)
        if observed != equalities:
            raise ValueError('USD does not realize every source joint equality')
        facts.append({'root': root, 'joint_names': sorted(joints),
                      'source_equalities': [sorted(pair) for pair in observed]})
    return facts


class ArticulationLayout:
    """Map source semantics to env-local CUDA state.

    Scalar joints lead ``qpos`` and ``qvel``. Each free body appends xyz/wxyz
    to qpos and world linear velocity at the body origin / local angular
    velocity to qvel, matching the source MJCF generalized coordinates.
    """

    def __init__(self, *, stage, roots, articulation_roots, request, articulation, simulation, torch, wp, usd_geom, usd_physics):
        self.torch, self.wp = torch, wp
        self._quaternion_conjugate = torch.tensor([1., -1., -1., -1.], device='cuda')
        self.articulation, self.simulation = articulation, simulation
        self.roots = tuple(roots)
        self.count = len(roots)
        self.joint_names = tuple(articulation.dof_names)
        self.nj = len(self.joint_names)
        source_joints = request['source_joints']
        if len(set(source_joints.values())) != len(source_joints) or set(source_joints.values()) != set(self.joint_names):
            raise ValueError('native articulation DOF names differ from source binding')
        self.joint_qpos = {key: self.joint_names.index(native) for key, native in source_joints.items()}
        self.free_names = tuple(request['source_free_joints'])
        self.free_qpos = {key: self.nj + 7 * index for index, key in enumerate(self.free_names)}
        self.nq, self.nv = self.nj + 7 * len(self.free_names), self.nj + 6 * len(self.free_names)
        self.frame_names = tuple(request['source_frames'])
        self.views, self.reorders = {}, {}
        entry = request['entry_prim']

        def view_for(relative):
            if relative not in self.views:
                expected = [root + '/' + relative for root in self.roots]
                view = simulation.create_rigid_body_view(expected)
                actual = [str(value) for value in view.prim_paths]
                if len(actual) != self.count or set(actual) != set(expected):
                    raise ValueError('native rigid-body view does not cover every declared row')
                self.views[relative] = view
                self.reorders[relative] = torch.tensor([actual.index(path) for path in expected],
                                                       dtype=torch.int64, device='cuda')
            return relative

        self.body_keys = {name: view_for(_relative_path(entry, path))
                          for name, path in request['source_bodies'].items()}
        entity = request['articulation_entity']
        articulation_root = articulation_roots[0]
        for prim in stage.Traverse():
            path = str(prim.GetPath())
            if ((path == articulation_root or path.startswith(articulation_root + '/'))
                    and prim.HasAPI(usd_physics.RigidBodyAPI)):
                semantic = f'{entity}/{prim.GetName()}'
                key = view_for(path[len(self.roots[0]) + 1:])
                if semantic in self.body_keys and self.body_keys[semantic] != key:
                    raise ValueError('source articulation contains ambiguous body leaf names')
                self.body_keys[semantic] = key
        self.body_names = tuple(self.body_keys)
        self.free_keys = {name: view_for(_relative_path(entry, path))
                          for name, path in request['source_free_joints'].items()}
        self.free_com = {}
        for name, key in self.free_keys.items():
            native = self.views[key].get_coms()
            torch.cuda.synchronize()
            # PhysX may expose immutable mass properties on CPU even when its
            # dynamic rigid-body views are on CUDA. Transfer once at build.
            com = self._tensor(native).to(device='cuda')
            self.free_com[name] = com.index_select(0, self.reorders[key])[:, :3].clone()
        self.frame_specs = {}
        cache = usd_geom.XformCache()
        for name, path in request['source_frames'].items():
            relative = _relative_path(entry, path)
            frame = stage.GetPrimAtPath(self.roots[0] + '/' + relative)
            if not frame or not frame.IsValid():
                raise ValueError(f'USD source frame is absent: {name}')
            ancestor = frame.GetParent()
            while ancestor and ancestor.IsValid() and not ancestor.HasAPI(usd_physics.RigidBodyAPI):
                ancestor = ancestor.GetParent()
            if ancestor and ancestor.IsValid() and str(ancestor.GetPath()).startswith(self.roots[0] + '/'):
                parent = str(ancestor.GetPath())[len(self.roots[0]) + 1:]
                key = view_for(parent)
                transform = cache.GetLocalToWorldTransform(frame) * cache.GetLocalToWorldTransform(ancestor).GetInverse()
            else:
                key = None
                transform = cache.GetLocalToWorldTransform(frame)
            translate, quaternion = transform.ExtractTranslation(), transform.ExtractRotationQuat()
            imaginary = quaternion.GetImaginary()
            position = torch.tensor(tuple(float(x) for x in translate), dtype=torch.float32, device='cuda')
            rotation = torch.tensor((float(quaternion.GetReal()), *(float(x) for x in imaginary)),
                                    dtype=torch.float32, device='cuda')
            self.frame_specs[name] = (key, position, rotation)
        self.channel_indices = tuple(self.joint_qpos[key] for key in request['channel_keys'])
        self.damping = torch.tensor([request['joint_dynamics'][name]['damping'] for name in self.joint_names],
                                    dtype=torch.float32, device='cuda').reshape(1, -1)

    def _tensor(self, value):
        return value if isinstance(value, self.torch.Tensor) else self.wp.to_torch(value)

    def _poses(self):
        native = {key: view.get_transforms() for key, view in self.views.items()}
        self.torch.cuda.synchronize()
        return {key: self._tensor(pose).index_select(0, self.reorders[key]).clone()
                for key, pose in native.items()}

    def read(self):
        torch = self.torch
        native_q = self.articulation.get_dof_positions()
        native_v = self.articulation.get_dof_velocities()
        poses = self._poses()
        q, v = self._tensor(native_q).clone(), self._tensor(native_v).clone()
        q_parts, v_parts = [q], [v]
        for name in self.free_names:
            key = self.free_keys[name]
            pose = poses[key]
            native_velocity = self.views[key].get_velocities()
            torch.cuda.synchronize()
            velocity = self._tensor(native_velocity).index_select(0, self.reorders[key]).clone()
            orientation = pose[:, [6, 3, 4, 5]]
            angular_world = velocity[:, 3:]
            offset_world = _rotate(orientation, self.free_com[name])
            linear_origin = velocity[:, :3] - torch.linalg.cross(angular_world, offset_world)
            inverse = orientation * self._quaternion_conjugate
            angular_local = _rotate(inverse, angular_world)
            q_parts.append(pose[:, [0, 1, 2, 6, 3, 4, 5]])
            v_parts.append(torch.cat((linear_origin, angular_local), dim=1))
        body = [poses[self.body_keys[name]] for name in self.body_names]
        result = {'qpos': torch.cat(q_parts, dim=1).contiguous(),
                  'qvel': torch.cat(v_parts, dim=1).contiguous(),
                  'body_position': torch.stack([pose[:, :3] for pose in body], dim=1).contiguous(),
                  'body_orientation': torch.stack([pose[:, [6, 3, 4, 5]] for pose in body], dim=1).contiguous()}
        frame_positions, frame_orientations = [], []
        for name in self.frame_names:
            parent, offset, rotation = self.frame_specs[name]
            if parent is None:
                position = offset.expand(self.count, -1)
                orientation = rotation.expand(self.count, -1)
            else:
                pose = poses[parent]
                quat = pose[:, [6, 3, 4, 5]]
                xyz = quat[:, 1:]
                local = offset.expand(self.count, -1)
                position = pose[:, :3] + _rotate(quat, local)
                rw, rv = rotation[:1], rotation[1:].expand(self.count, -1)
                orientation = torch.cat((quat[:, :1] * rw - (xyz * rv).sum(dim=1, keepdim=True),
                    quat[:, :1] * rv + rw * xyz + torch.linalg.cross(xyz, rv)), dim=1)
            frame_positions.append(position)
            frame_orientations.append(orientation)
        if self.frame_names:
            result.update(frame_position=torch.stack(frame_positions, dim=1).contiguous(),
                          frame_orientation=torch.stack(frame_orientations, dim=1).contiguous())
        torch.cuda.synchronize()
        return result

    def reset(self, inputs):
        torch, wp = self.torch, self.wp
        selected = torch.nonzero(inputs['reset_mask'], as_tuple=False).flatten()
        if not selected.numel():
            return
        rows = selected.cpu().tolist()
        q = inputs['reset_qpos'].index_select(0, selected)[:, :self.nj].contiguous()
        v = inputs['reset_qvel'].index_select(0, selected)[:, :self.nj].contiguous()
        self.articulation.set_dof_positions(wp.from_torch(q), indices=rows)
        self.articulation.set_dof_velocities(wp.from_torch(v), indices=rows)
        self.articulation.set_dof_efforts(wp.from_torch(torch.zeros_like(v)), indices=rows)
        for i, name in enumerate(self.free_names):
            key, start = self.free_keys[name], self.free_qpos[name]
            view, reorder = self.views[key], self.reorders[key]
            indices = reorder.index_select(0, selected)
            native_transforms, native_velocities = view.get_transforms(), view.get_velocities()
            torch.cuda.synchronize()
            transforms = self._tensor(native_transforms).clone()
            velocities = self._tensor(native_velocities).clone()
            source_q = inputs['reset_qpos'].index_select(0, selected)[:, start:start + 7]
            transforms[indices] = source_q[:, [0, 1, 2, 4, 5, 6, 3]]
            source_v = inputs['reset_qvel'].index_select(0, selected)[:, self.nj + 6*i:self.nj + 6*(i+1)]
            orientation = source_q[:, 3:7]
            angular_world = _rotate(orientation, source_v[:, 3:])
            offset_world = _rotate(orientation, self.free_com[name].index_select(0, selected))
            linear_com = source_v[:, :3] + torch.linalg.cross(angular_world, offset_world)
            velocities[indices] = torch.cat((linear_com, angular_world), dim=1)
            torch.cuda.synchronize()
            indices = indices.to(dtype=torch.int32).contiguous()
            if isinstance(native_transforms, torch.Tensor):
                view.set_transforms(transforms.contiguous(), indices)
                view.set_velocities(velocities.contiguous(), indices)
            else:
                native_indices = wp.from_torch(indices, dtype=wp.uint32)
                view.set_transforms(wp.from_torch(transforms.contiguous()), native_indices)
                view.set_velocities(wp.from_torch(velocities.contiguous()), native_indices)
        torch.cuda.synchronize()
        if self.simulation.update_articulations_kinematic() is False:
            raise RuntimeError('Isaac native articulation reset refresh failed')
        torch.cuda.synchronize()

    def apply_effort(self, effort):
        torch, wp = self.torch, self.wp
        velocity = self._tensor(self.articulation.get_dof_velocities())
        torch.cuda.synchronize()
        total = -self.damping * velocity
        for channel, native_index in enumerate(self.channel_indices):
            total[:, native_index] += effort[:, channel]
        torch.cuda.synchronize()
        self.articulation.set_dof_efforts(wp.from_torch(total.contiguous()))
        torch.cuda.synchronize()
