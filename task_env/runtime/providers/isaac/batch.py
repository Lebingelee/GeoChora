"""Source-bound Isaac PhysX batch through the shared device worker contract."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import uuid
import xml.etree.ElementTree as ET

from ...transport.device_batch_session import DevicePhysicalBatchSession


def _declared_single_joint_damping(source):
    """Resolve explicit source damping without inventing a control profile."""
    root = ET.fromstring(source.scene_source.xml)
    if root.find('default') is not None:
        raise ValueError('Isaac single-joint device admission cannot infer MJCF default inheritance')
    native_name, = source.joints.values()
    joints = [joint for joint in root.iter('joint') if joint.get('name') == native_name]
    if len(joints) != 1:
        raise ValueError('Isaac source must contain exactly one named scalar joint')
    joint = joints[0]
    if any(float(joint.get(name, '0')) != 0 for name in ('frictionloss', 'stiffness', 'armature')):
        raise ValueError('Isaac single-joint device admission cannot realize other passive terms')
    damping = float(joint.get('damping', '0'))
    if not math.isfinite(damping) or damping < 0:
        raise ValueError('Isaac source joint damping must be finite and nonnegative')
    return damping


def _aggregate_pair_capacity(collider_count, current):
    """Reserve for any pair of cloned colliders, rounded up for PhysX buffers."""
    if collider_count < 0 or current < 0:
        raise ValueError('collision capacity inputs must be nonnegative')
    pairs = collider_count * (collider_count - 1) // 2
    required = max(1, current, 2 * pairs)
    capacity = 1 << (required - 1).bit_length()
    if capacity > 2**31 - 1:
        raise ValueError('Isaac collision pair capacity exceeds the supported integer range')
    return capacity


def _declared_articulation_dynamics(source):
    """Resolve passive scalar-DOF parameters and affine equalities from source MJCF."""
    import mujoco

    inputs = dict(source.scene_source.loaded_delivery.source_input_bytes)
    entry = source.scene_source.loaded_delivery.delivery.source_entry_file
    xml = inputs.pop(entry, None)
    if not isinstance(xml, bytes):
        raise ValueError('verified source delivery has no original MJCF entry')
    model = mujoco.MjModel.from_xml_string(xml.decode('utf-8'), assets=inputs)
    names = tuple(source.joints.values())
    if len(set(names)) != len(names):
        raise ValueError('source scalar joints must have unique native names')
    dynamics = {}
    joint_ids = {}
    for name in names:
        try:
            joint = model.joint(name).id
        except KeyError as error:
            raise ValueError(f'source MJCF omits joint {name!r}') from error
        if int(model.jnt_type[joint]) not in (int(mujoco.mjtJoint.mjJNT_HINGE), int(mujoco.mjtJoint.mjJNT_SLIDE)):
            raise ValueError('Isaac articulation requires scalar source joints')
        dof = int(model.jnt_dofadr[joint])
        if float(model.dof_frictionloss[dof]) != 0 or float(model.jnt_stiffness[joint]) != 0:
            raise ValueError('Isaac articulation cannot realize source friction loss or joint stiffness')
        damping, armature = float(model.dof_damping[dof]), float(model.dof_armature[dof])
        if not all(math.isfinite(value) and value >= 0 for value in (damping, armature)):
            raise ValueError('source damping and armature must be finite and nonnegative')
        dynamics[name] = {'damping': damping, 'armature': armature}
        joint_ids[joint] = name
    equalities = []
    for index in range(model.neq):
        first, second = int(model.eq_obj1id[index]), int(model.eq_obj2id[index])
        if (int(model.eq_type[index]) != int(mujoco.mjtEq.mjEQ_JOINT)
                or not bool(model.eq_active0[index]) or first not in joint_ids or second not in joint_ids
                or tuple(float(x) for x in model.eq_data[index][:5]) != (0., 1., 0., 0., 0.)):
            raise ValueError('Isaac articulation cannot realize the declared source equality')
        equalities.append((joint_ids[first], joint_ids[second]))
    return dynamics, equalities


class IsaacNativeBatch:
    """Own one App, one PhysX scene, and source-bound native batch tensor views."""

    def __init__(self, request):
        import numpy as np
        import torch
        import warp as wp
        from ...sessions.isaac_native_io import IsaacSimAppOwnerV1
        from ...transport.cuda_ipc import CudaIpcDuplexPublisher

        self._owner = IsaacSimAppOwnerV1()
        self._context = self._stage = self._manager = self._articulation = self._publisher = None
        self._body_views = {}
        self._closed = False
        self._torch, self._wp = torch, wp
        self._layout_adapter = None
        self._articulated_layout = bool(request.get('articulated_layout', False))
        self.num_envs = int(request['num_envs'])
        self._substeps = int(request['control_substeps'])
        self._physics_dt = float(request['physics_dt'])
        self._source_damping = float(request['source_joint_damping'])
        self._body_names = tuple(request['source_bodies'])
        if self.num_envs < 1 or self._substeps < 1 or not self._body_names:
            raise ValueError('Isaac batch requires positive size/substeps and source bodies')
        if not self._articulated_layout and (len(request['source_joints']) != 1
                or request['source_frames'] or request['source_free_joints']):
            raise ValueError('Isaac device batch currently admits a single scalar joint and rigid body frames')
        self._joint_mapping = {name: 0 for name in request['source_joints']}
        root = Path(request['snapshot_root']).resolve(strict=True)
        for relative, digest in request['snapshot_sha256'].items():
            path = Path(relative)
            target = (root / path).resolve(strict=True)
            if path.is_absolute() or not target.is_relative_to(root):
                raise ValueError('Isaac snapshot file escaped its verified closure')
            if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise ValueError('Isaac snapshot file differs from the admitted source closure')
        entry = (root / request['entry_file']).resolve(strict=True)
        if not entry.is_relative_to(root):
            raise ValueError('Isaac USD entry escaped its verified closure')
        try:
            self._owner.open()
            import omni.usd
            from pxr import Gf, PhysxSchema, Sdf, UsdGeom, UsdPhysics
            from isaacsim.core.cloner import Cloner
            from isaacsim.core.experimental.prims import Articulation
            from isaacsim.core.experimental.utils import app as app_utils
            from isaacsim.core.simulation_manager import SimulationManager

            self._app_utils, self._manager = app_utils, SimulationManager
            self._context = omni.usd.get_context()
            if self._context.get_stage() is not None:
                self._context.close_stage()
            self._context.new_stage()
            self._stage = self._context.get_stage()
            stage = self._stage
            UsdGeom.SetStageMetersPerUnit(stage, 1.0)
            UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
            paths = [f'/World/envs/env_{index}' for index in range(self.num_envs)]
            prim = UsdGeom.Xform.Define(stage, paths[0]).GetPrim()
            if not prim.GetReferences().AddReference(str(entry), Sdf.Path(request['entry_prim'])):
                raise ValueError('Isaac could not reference the verified source')
            for key, value in request['variant_selections'].items():
                path, name = key.rsplit('#', 1)
                if path != request['entry_prim']:
                    raise ValueError('Isaac batch requires entry-root source variants')
                if not prim.GetVariantSets().GetVariantSet(name).SetVariantSelection(value):
                    raise ValueError('Isaac source variant selection failed')
            source_scenes = [str(p.GetPath()) for p in stage.Traverse() if p.IsA(UsdPhysics.Scene)]
            if len(source_scenes) > 1:
                raise ValueError('Isaac source has multiple physics scenes')
            for path in source_scenes:
                source_scene = UsdPhysics.Scene(stage.GetPrimAtPath(path))
                direction = source_scene.GetGravityDirectionAttr().Get()
                magnitude = source_scene.GetGravityMagnitudeAttr().Get()
                if direction is not None and magnitude is not None and not np.allclose(
                        np.asarray(direction, dtype=float) * float(magnitude),
                        request['gravity'], rtol=0, atol=1e-5):
                    raise ValueError('Isaac source gravity differs from the Task runtime')
                source_scene.GetPrim().SetActive(False)
            cloner = Cloner()
            cloner.clone(paths[0], paths, positions=np.zeros((self.num_envs, 3)), copy_from_source=True)
            if self._articulated_layout:
                from .articulation_layout import prepare_articulation
                articulated_facts = prepare_articulation(stage, paths, request, UsdPhysics, PhysxSchema)
            SimulationManager.setup_simulation(dt=float(request['physics_dt']), device=request['device'])
            scenes = SimulationManager.get_physics_scenes()
            if len(scenes) != 1:
                raise ValueError('Isaac batch requires exactly one native physics scene')
            physics = scenes[0]
            physics.set_gravity(Gf.Vec3f(*request['gravity']))
            physics.set_enabled_gpu_dynamics(True)
            # All worlds share an origin; broadphase can see cross-world pairs
            # before group filtering. Reserve from actual cloned collision
            # topology rather than silently dropping found/lost aggregate pairs.
            collider_count = sum(
                1 for prim in stage.Traverse()
                if prim.HasAPI(UsdPhysics.CollisionAPI)
                and any(str(prim.GetPath()) == path or str(prim.GetPath()).startswith(path + '/')
                        for path in paths)
                and UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get() is not False
            )
            gpu_config = physics.get_gpu_configuration()
            existing = max(int(gpu_config.gpu_found_lost_aggregate_pairs_capacity or 0),
                           int(gpu_config.gpu_total_aggregate_pairs_capacity or 0))
            pair_capacity = _aggregate_pair_capacity(collider_count, existing)
            physics.set_gpu_configuration({'gpu_found_lost_aggregate_pairs_capacity': pair_capacity,
                                           'gpu_total_aggregate_pairs_capacity': pair_capacity})
            actual_gpu_config = physics.get_gpu_configuration()
            if (int(actual_gpu_config.gpu_found_lost_aggregate_pairs_capacity or 0) != pair_capacity
                    or int(actual_gpu_config.gpu_total_aggregate_pairs_capacity or 0) != pair_capacity):
                raise RuntimeError('Isaac collision aggregate capacity did not apply')
            if (not physics.get_enabled_gpu_dynamics()
                    or not math.isclose(float(physics.get_dt()), float(request['physics_dt']), abs_tol=1e-12)
                    or not np.allclose(physics.get_gravity(), request['gravity'], rtol=0, atol=1e-5)
                    or str(SimulationManager.get_device()) != request['device']):
                raise ValueError('Isaac native physics scene does not match its CUDA timebase')
            cloner.filter_collisions(str(physics.path), '/World/collisions', paths)
            if not PhysxSchema.PhysxSceneAPI(physics.prim).GetInvertCollisionGroupFilterAttr().Get():
                raise ValueError('Isaac cross-environment collision filtering is unavailable')
            groups = []
            for index, path in enumerate(paths):
                group_path = f'/World/collisions/group{index}'
                group = stage.GetPrimAtPath(group_path)
                includes = [str(p) for p in group.GetRelationship('collection:colliders:includes').GetTargets()]
                filters = [str(p) for p in group.GetRelationship('physics:filteredGroups').GetTargets()]
                if includes != [path] or filters != [group_path]:
                    raise ValueError('Isaac collision group does not match its source environment')
                groups.append({'env_id': index, 'includes': includes, 'filtered_groups': filters})
            roots = [str(p.GetPath()) for p in stage.Traverse() if p.HasAPI(UsdPhysics.ArticulationRootAPI)]
            row_roots = []
            for path in paths:
                matches = [value for value in roots if value.startswith(path + '/')]
                if len(matches) != 1:
                    raise ValueError('Isaac environment does not have one source articulation')
                row_roots.append(matches[0])
            self._articulation = Articulation(row_roots)
            app_utils.play()
            app_utils.update_app(steps=2)
            app_utils.pause()
            if app_utils.is_playing() or not self._articulation.is_physics_tensor_entity_valid():
                raise RuntimeError('Isaac batch tensor bootstrap failed')
            articulation = self._articulation
            if (len(articulation) != self.num_envs
                    or set(articulation.dof_names) != set(request['joint_targets'])
                    or len(articulation.dof_names) != len(request['joint_targets'])):
                raise ValueError('Isaac native articulation DOFs differ from the source binding')
            for row, path in enumerate(paths):
                if not articulation.link_paths[row] or any(
                        not str(link).startswith(path + '/') for link in articulation.link_paths[row]):
                    raise ValueError('Isaac articulation tensor row order differs from the environment mapping')
            articulation.set_dof_gains([0.] * len(articulation.dof_names),
                                       [0.] * len(articulation.dof_names), update_default_gains=False)
            stiffness, damping = articulation.get_dof_gains()
            if (bool((wp.to_torch(stiffness).abs() > 1e-8).any())
                    or bool((wp.to_torch(damping).abs() > 1e-8).any())):
                raise ValueError('Isaac drive isolation could not be verified')
            simulation = SimulationManager.get_physics_simulation_view()
            if simulation is None:
                raise RuntimeError('Isaac native simulation tensor view unavailable')
            self._simulation = simulation
            clock_origin = self._clock()
            if self._articulated_layout:
                from .articulation_layout import ArticulationLayout
                layout = ArticulationLayout(stage=stage, roots=paths, articulation_roots=row_roots, request=request,
                    articulation=articulation, simulation=simulation, torch=torch, wp=wp,
                    usd_geom=UsdGeom, usd_physics=UsdPhysics)
                self._layout_adapter = layout
                self._body_names = layout.body_names
                self._joint_mapping = layout.joint_qpos
                fields = {'qpos': ((self.num_envs, layout.nq), 'float32'),
                          'qvel': ((self.num_envs, layout.nv), 'float32'),
                          'body_position': ((self.num_envs, len(layout.body_names), 3), 'float32'),
                          'body_orientation': ((self.num_envs, len(layout.body_names), 4), 'float32'),
                          'reset_qpos': ((self.num_envs, layout.nq), 'float32'),
                          'reset_qvel': ((self.num_envs, layout.nv), 'float32'),
                          'reset_mask': ((self.num_envs,), 'bool'),
                          'effort': ((self.num_envs, len(request['channel_keys'])), 'float32')}
                if layout.frame_names:
                    fields.update(frame_position=((self.num_envs, len(layout.frame_names), 3), 'float32'),
                                  frame_orientation=((self.num_envs, len(layout.frame_names), 4), 'float32'))
                self._publisher = CudaIpcDuplexPublisher(fields)
                self._layout = {'articulation_roots': row_roots, 'dof_names': list(articulation.dof_names),
                    'collision_groups': groups, 'coincident_origins': True, 'drive_gains': 'zero',
                    'source_collision_shapes_all_worlds': collider_count,
                    'gpu_aggregate_pair_capacity': pair_capacity,
                    'source_joint_dynamics': request['joint_dynamics'], 'native_joint_facts': articulated_facts,
                    'passive_damping_mapping': 'device generalized force -damping * joint velocity',
                    'native_clock': 'SimulationManager physics step count and simulation time',
                    'native_clock_origin_step': clock_origin[0],
                    'native_clock_origin_time_s': clock_origin[1]}
                self._publish()
                return
            self._body_reorders = {}
            for semantic, native in request['source_bodies'].items():
                if native.startswith('/') or '..' in Path(native).parts:
                    raise ValueError('Isaac body source must be an entry-relative path')
                expected = [path + '/' + native for path in paths]
                view = simulation.create_rigid_body_view(expected)
                native_paths = [str(path) for path in view.prim_paths]
                if len(native_paths) != self.num_envs or set(native_paths) != set(expected):
                    raise ValueError('Isaac native body view does not cover exactly the declared environments')
                self._body_views[semantic] = view
                self._body_reorders[semantic] = torch.tensor(
                    [native_paths.index(path) for path in expected], dtype=torch.int64, device='cuda')
            fields = {'qpos': ((self.num_envs, 1), 'float32'), 'qvel': ((self.num_envs, 1), 'float32'),
                      'body_position': ((self.num_envs, len(self._body_names), 3), 'float32'),
                      'body_orientation': ((self.num_envs, len(self._body_names), 4), 'float32'),
                      'reset_qpos': ((self.num_envs, 1), 'float32'),
                      'reset_qvel': ((self.num_envs, 1), 'float32'),
                      'reset_mask': ((self.num_envs,), 'bool'), 'effort': ((self.num_envs, 1), 'float32')}
            self._publisher = CudaIpcDuplexPublisher(fields)
            self._layout = {'articulation_roots': row_roots, 'dof_names': list(articulation.dof_names),
                            'collision_groups': groups, 'coincident_origins': True,
                            'source_collision_shapes_all_worlds': collider_count,
                            'gpu_aggregate_pair_capacity': pair_capacity,
                            'source_scene_deactivated_in_memory': source_scenes,
                            'native_physics_scene': str(physics.path), 'drive_gains': 'zero',
                            'source_joint_passive_damping': self._source_damping,
                            'passive_damping_mapping': 'device generalized force -damping * joint velocity',
                            'native_clock': 'SimulationManager physics step count and simulation time',
                            'native_clock_origin_step': clock_origin[0],
                            'native_clock_origin_time_s': clock_origin[1]}
            self._publish()
        except BaseException as error:
            import gc
            import traceback
            traceback.print_exc()
            # The traceback can retain temporary Warp arrays from a failed
            # native view construction. Release those while the SDK is alive.
            error.__traceback__ = None
            gc.collect()
            try:
                self.close()
            except BaseException as cleanup_error:
                error.add_note(f'Isaac batch construction cleanup failed: {cleanup_error!r}')
            raise error.with_traceback(None)

    def description(self):
        result = self._publisher.description()
        if self._layout_adapter is not None:
            layout = self._layout_adapter
            result.update(nq=layout.nq, nv=layout.nv, body_names=list(layout.body_names),
                          frame_names=list(layout.frame_names), joint_qpos_indices=layout.joint_qpos,
                          free_joint_qpos_indices=layout.free_qpos, physical_layout_facts=self._layout)
            return result
        result.update(nq=1, nv=1, body_names=list(self._body_names), frame_names=[],
                      joint_qpos_indices=self._joint_qpos, free_joint_qpos_indices={},
                      physical_layout_facts=self._layout)
        return result

    @property
    def _joint_qpos(self):
        return self._joint_mapping

    def bind_written_event(self, handle):
        self._publisher.bind_written_event(handle)

    def _clock(self):
        return (int(self._manager.get_num_physics_steps()),
                float(self._manager.get_simulation_time()))

    def _publish(self):
        torch, wp = self._torch, self._wp
        before = self._clock()
        if self._layout_adapter is not None:
            self._publisher.publish(self._layout_adapter.read())
            if self._clock() != before:
                raise RuntimeError('Isaac publication advanced physics')
            return
        q_view = self._articulation.get_dof_positions()
        v_view = self._articulation.get_dof_velocities()
        body_views = {name: self._body_views[name].get_transforms() for name in self._body_names}
        # PhysX/Warp may publish on a different stream from the IPC copies.
        # Complete those reads before Torch consumes the shared tensors.
        torch.cuda.synchronize()
        q, v = wp.to_torch(q_view).clone(), wp.to_torch(v_view).clone()
        positions, orientations = [], []
        for name in self._body_names:
            value = body_views[name]
            pose = value if isinstance(value, torch.Tensor) else wp.to_torch(value)
            pose = pose.index_select(0, self._body_reorders[name])
            positions.append(pose[:, :3])
            orientations.append(pose[:, [6, 3, 4, 5]])
        self._publisher.publish({'qpos': q.contiguous(), 'qvel': v.contiguous(),
            'body_position': torch.stack(positions, dim=1).contiguous(),
            'body_orientation': torch.stack(orientations, dim=1).contiguous()})
        if self._clock() != before:
            raise RuntimeError('Isaac publication advanced physics')

    def reset(self):
        torch, wp = self._torch, self._wp
        inputs = self._publisher.read_inputs(('reset_qpos', 'reset_qvel', 'reset_mask'))
        if self._layout_adapter is not None:
            before = self._clock()
            self._layout_adapter.reset(inputs)
            self._publish()
            if self._clock() != before:
                raise RuntimeError('Isaac reset advanced physics')
            return
        selected = torch.nonzero(inputs['reset_mask'], as_tuple=False).flatten()
        if selected.numel():
            indices = selected.cpu().tolist()
            before = self._clock()
            reset_q = inputs['reset_qpos'].index_select(0, selected).contiguous()
            reset_v = inputs['reset_qvel'].index_select(0, selected).contiguous()
            reset_effort = torch.zeros((len(indices), 1), device='cuda')
            self._articulation.set_dof_positions(wp.from_torch(reset_q), indices=indices)
            self._articulation.set_dof_velocities(wp.from_torch(reset_v), indices=indices)
            self._articulation.set_dof_efforts(wp.from_torch(reset_effort), indices=indices)
            torch.cuda.synchronize()
            if self._simulation.update_articulations_kinematic() is False:
                raise RuntimeError('Isaac native articulation reset refresh failed')
            torch.cuda.synchronize()
            if self._clock() != before:
                raise RuntimeError('Isaac reset advanced physics')
        self._publish()

    def step(self):
        inputs = self._publisher.read_inputs(('effort',))
        before = self._clock()
        for _ in range(self._substeps):
            if self._layout_adapter is not None:
                self._layout_adapter.apply_effort(inputs['effort'])
                self._manager.step(steps=1, update_fabric=False)
                self._torch.cuda.synchronize()
                continue
            native_velocity = self._articulation.get_dof_velocities()
            self._torch.cuda.synchronize()
            velocity = self._wp.to_torch(native_velocity)
            # The verified MJCF source declares viscous joint damping, but the
            # current PhysX USD conversion does not realize it. Apply this
            # source-owned passive term independently of the bounded action.
            total_effort = (inputs['effort'] - self._source_damping * velocity).contiguous()
            self._torch.cuda.synchronize()
            self._articulation.set_dof_efforts(self._wp.from_torch(total_effort))
            self._torch.cuda.synchronize()
            self._manager.step(steps=1, update_fabric=False)
            self._torch.cuda.synchronize()
        self._torch.cuda.synchronize()
        after = self._clock()
        if after[0] - before[0] != self._substeps or not math.isclose(
                after[1] - before[1], self._substeps * self._physics_dt, rel_tol=1e-6, abs_tol=1e-7):
            raise RuntimeError('Isaac native physics clock differs from the Task timebase')
        self._publish()

    def close(self):
        if self._closed:
            return
        self._closed = True
        import gc
        error = None
        for action in (
            lambda: self._publisher.close() if self._publisher is not None else None,
            lambda: self._app_utils.stop() if getattr(self, '_app_utils', None) is not None else None,
        ):
            try:
                action()
            except BaseException as caught:
                if error is None:
                    error = caught
                else:
                    error.add_note(f'Isaac batch cleanup also failed: {caught!r}')
        self._layout_adapter = None
        self._publisher = self._articulation = self._simulation = None
        self._body_views.clear()
        gc.collect()
        try:
            if self._context is not None and self._context.get_stage() is not None:
                self._context.close_stage()
            self._stage = self._context = None
        except BaseException as caught:
            if error is None:
                error = caught
            else:
                error.add_note(f'Isaac stage cleanup also failed: {caught!r}')
        try:
            self._owner.close()
        except BaseException as caught:
            if error is None:
                error = caught
            else:
                error.add_note(f'Isaac App cleanup also failed: {caught!r}')
        if error is not None:
            raise error


class IsaacDeviceBatchSession(DevicePhysicalBatchSession):
    """Own one verified source lease and the shared source-bound IPC session."""
    _provider_label = 'Isaac'

    def __init__(self, built, *, num_envs, device, interpreter, runtime_config,
                 contact_mode='provider_default', working_directory=None):
        from ....controllers.canonical.physical_controller import DirectJointEffortControllerV1, LinearEffortControllerV1
        from ...sessions.physical_control import PhysicalControlExecutionV1
        from ...transport.cuda_ipc import CudaIpcConnection
        from ...transport.worker import RuntimeWorker

        if contact_mode != 'provider_default':
            raise ValueError('Isaac does not consume the GeoPhys contact mode')

        source, artifact, execution = built['source'], built['artifact'], built['physical_execution']
        if type(execution) is not PhysicalControlExecutionV1:
            raise TypeError('Isaac device batch requires source-bound physical execution')
        execution.validate_source(scene=source.scene_definition, artifact_sha256=artifact.identity_hash,
            source_id=source.source_id, source_closure_sha256=source.source_closure_digest, source=source)
        if len(execution.controllers) != 1 or type(execution.controllers[0]) not in (
                DirectJointEffortControllerV1, LinearEffortControllerV1):
            raise ValueError('Isaac device batch requires one source-bound joint-effort Controller')
        controller, binding = execution.controllers[0], execution.compiled.binding
        if (binding.bodies or controller.channel_keys != tuple(channel.target_key for channel in binding.channels)
                or any(c.owner_ids != (controller.writer_id,) or c.native_drive != 'disabled'
                       or c.sign != 1 for c in binding.channels)):
            raise ValueError('Isaac device batch requires exclusive declared joint-effort channels')
        simple = (len(binding.channels) == 1 and not source.frames and not source.free_joints
                  and type(controller) is DirectJointEffortControllerV1
                  and binding.channels[0].transmission_coefficient == 1.)
        channel_joints = [f'{channel.entity_id}/{channel.joint_id}' for channel in binding.channels]
        if not simple and (len(set(channel_joints)) != len(channel_joints)
                or set(channel_joints) != set(source.joints)
                or any(channel.dof_id != 'dof0' for channel in binding.channels)):
            raise ValueError('Isaac articulated device batch requires every source scalar joint to be controlled')
        if not simple and len(execution.subjects) != 1:
            raise ValueError('Isaac articulated device batch requires one declared articulation subject')
        count = int(num_envs)
        if isinstance(num_envs, bool) or count != num_envs or count < 1 or str(device) != 'cuda:0':
            raise ValueError('Isaac device batch requires positive B and cuda:0')
        timebase = artifact.timebase
        if not math.isclose(timebase.physics_dt * timebase.control_substeps, timebase.control_dt,
                            rel_tol=0, abs_tol=1e-12):
            raise ValueError('Task timebase has inconsistent control cadence')
        if simple:
            source_damping = _declared_single_joint_damping(source)
            joint_dynamics, joint_equalities = {}, []
        else:
            source_damping = 0.
            joint_dynamics, joint_equalities = _declared_articulation_dynamics(source)
        loaded = source.scene_source.loaded_delivery
        delivery = loaded.delivery
        self._source_lease = source.scene_source.acquire_snapshot()
        try:
            request = {'provider': 'isaacsim', 'device': str(device), 'num_envs': count,
                'snapshot_root': str(self._source_lease.root), 'entry_file': delivery.entry_file,
                'entry_prim': delivery.entry_prim, 'variant_selections': dict(delivery.variant_selections),
                'snapshot_sha256': {name: hashlib.sha256(value).hexdigest() for name, value in loaded.file_bytes.items()},
                'source_bodies': dict(source.bodies), 'source_frames': dict(source.frames),
                'source_joints': dict(source.joints), 'source_free_joints': dict(source.free_joints),
                'joint_targets': list(source.joint_targets.values()), 'physics_dt': timebase.physics_dt,
                'control_substeps': timebase.control_substeps, 'gravity': runtime_config.gravity,
                'source_joint_damping': source_damping, 'articulated_layout': not simple,
                'joint_dynamics': joint_dynamics, 'joint_equalities': joint_equalities,
                'channel_keys': channel_joints,
                'articulation_entity': execution.subjects[0].entity_id if not simple else None}
        except BaseException:
            self._source_lease.close()
            raise
        self.num_envs, self.device = count, str(device)
        self._source, self._artifact, self._execution = source, artifact, execution
        self._source_identity = (source.source_id, source.source_closure_digest, artifact.identity_hash)
        self._binding, self._controller, self._binding_hash = binding, controller, binding.identity_hash
        self._materialization_id = 'isaac-' + uuid.uuid4().hex
        self._generation, self._revision, self._native_steps = int(execution.generation), 0, 0
        self._physics_dt, self._control_substeps = float(timebase.physics_dt), int(timebase.control_substeps)
        self._control_dt = float(timebase.control_dt)
        self._last_state = self._device_limits = None
        self._closed = self._faulted = False
        self._worker = self._ipc = None
        try:
            self._worker = RuntimeWorker(interpreter, request, working_directory=working_directory)
            description = self._worker.description
            self._ipc = CudaIpcConnection(description)
            self._body_names, self._frame_names = tuple(description['body_names']), tuple(description['frame_names'])
            self._joint_qpos, self._free_qpos = dict(description['joint_qpos_indices']), dict(description['free_joint_qpos_indices'])
            self._layout_facts = dict(description['physical_layout_facts'])
            self._state_shapes = {'qpos': (description['nq'],), 'qvel': (description['nv'],),
                                  'body_position': (len(self._body_names), 3),
                                  'body_orientation': (len(self._body_names), 4)}
            if self._frame_names:
                self._state_shapes.update(frame_position=(len(self._frame_names), 3),
                                          frame_orientation=(len(self._frame_names), 4))
            self._worker.call('bind_event', handle=self._ipc.written_handle)
        except BaseException as error:
            try:
                self.close()
            except BaseException as cleanup_error:
                error.add_note(f'Isaac construction cleanup failed: {cleanup_error!r}')
            raise

    def resource_summary(self):
        return {'num_envs': self.num_envs, 'provider': 'isaacsim',
            'device_transition': {'available': True, 'field_device': self.device,
                'transport': 'cuda_ipc', 'state_readback_fields': list(self._state_shapes),
                'state_shapes': self._state_shapes, 'body_names': self._body_names,
                'frame_names': self._frame_names, 'joint_qpos_indices': dict(self._joint_qpos),
                'free_joint_qpos_indices': dict(self._free_qpos),
                'physical_layout_facts': dict(self._layout_facts),
                'pose_layout': 'world_body_xyz_wxyz_env_local'}}

    def close(self):
        error = None
        try:
            super().close()
        except BaseException as caught:
            error = caught
        if self._worker is None and self._source_lease is not None:
            try:
                self._source_lease.close()
                self._source_lease = None
            except BaseException as caught:
                if error is None:
                    error = caught
                else:
                    error.add_note(f'Isaac source lease cleanup also failed: {caught!r}')
        if error is not None:
            raise error
