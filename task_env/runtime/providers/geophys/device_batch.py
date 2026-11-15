"""Source-bound CUDA IPC adapter for GeoPhys homogeneous rigid batches.

Native model admission remains governed by the rigid batch solver; published
state and direct effort use the compiled source layout.
"""
from __future__ import annotations

import base64
import math
from pathlib import Path
from types import SimpleNamespace
import uuid
import xml.etree.ElementTree as ET

from ...transport.device_batch_session import DevicePhysicalBatchSession


def _compose_site_poses(body_position, body_quaternion, local_position, local_quaternion):
    """Compose source site transforms with device body poses, using wxyz quaternions."""
    import torch

    vector = body_quaternion[..., 1:]
    local_position = local_position.expand_as(vector)
    twice_cross = 2 * torch.cross(vector, local_position, dim=-1)
    position = (body_position + local_position + body_quaternion[..., :1] * twice_cross
                + torch.cross(vector, twice_cross, dim=-1))
    local_quaternion = local_quaternion.expand_as(body_quaternion)
    local_vector = local_quaternion[..., 1:]
    scalar = body_quaternion[..., :1] * local_quaternion[..., :1] - (vector * local_vector).sum(-1, keepdim=True)
    rotation = (body_quaternion[..., :1] * local_vector + local_quaternion[..., :1] * vector
                + torch.cross(vector, local_vector, dim=-1))
    return position.contiguous(), torch.cat((scalar, rotation), dim=-1).contiguous()


def _validate_implicitfast_smooth_equivalence(model, option):
    """Admit only sources whose implicit velocity derivative is joint damping.

    Native actuators are isolated separately. A standalone isotropic free
    body at its COM has no gyroscopic derivative; arbitrary free bodies and
    other velocity-dependent forces require their own integrator support.
    This does not assert equality of different constraint/contact solvers.
    """
    import numpy as np

    data = model.joint_data
    if option is not None:
        if any(float(option.get(name, '0')) != 0 for name in ('density', 'viscosity')):
            raise ValueError('GeoPhys implicitfast equivalence excludes fluid forces')
        if option.find('flag') is not None:
            raise ValueError('GeoPhys implicitfast equivalence requires default source option flags')
    for key in ('jnt_frictionloss', 'jnt_stiffness', 'tendon_damping',
                'body_linear_damping', 'body_angular_damping'):
        values = np.asarray(data.get(key, ()), dtype=np.float64)
        if not np.isfinite(values).all() or np.any(values != 0):
            raise ValueError(f'GeoPhys implicitfast equivalence excludes {key}')
    parents = np.asarray(data['body_parentid'], dtype=np.int64)
    offsets = np.asarray(data['body_ipos'], dtype=np.float64)
    for joint, kind in enumerate(data['jnt_type']):
        if int(kind) != 0:
            continue
        body = int(data['jnt_child_body'][joint])
        if body < 0 or body >= len(model.objects) or np.any(parents == body):
            raise ValueError('GeoPhys implicitfast equivalence requires standalone free bodies')
        inertia = np.asarray(model.objects[body].body_inertia, dtype=np.float64)
        if (inertia.shape != (3,) or not np.isfinite(inertia).all() or np.any(inertia <= 0)
                or not np.array_equal(inertia, np.repeat(inertia[:1], 3))
                or np.any(offsets[body] != 0)):
            raise ValueError('GeoPhys implicitfast equivalence requires isotropic free-body inertia at its COM')


class GeoPhysNativeBatch:
    """One isolated GeoPhys BRS materialization and its CUDA IPC buffers."""

    def __init__(self, request):
        import numpy as np
        import torch
        from scene import SceneSource, import_scene_source
        from ....artifacts import SceneDefinition
        from ....controllers.canonical.physical_commands import PhysicalControlBindingV1
        from ...provider_bootstrap import init_task_env_backend
        from ...sessions.geophys_source import validate_canonical_scene_import
        from ...transport.cuda_ipc import CudaIpcDuplexPublisher
        from .rigid_batch import GeoPhysRigidBatchRuntime

        self._publisher = self._runtime = None
        self._closed = False
        root = Path.cwd().resolve()
        for logical, encoded in request['source_assets'].items():
            path = Path(logical)
            if path.is_absolute() or any(part in ('', '.', '..') for part in path.parts):
                raise ValueError('GeoPhys source asset must be a safe relative path')
            target = (root / path).resolve()
            if not target.is_relative_to(root):
                raise ValueError('GeoPhys source asset escaped the worker directory')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(base64.b64decode(encoded, validate=True))
        init_task_env_backend('cuda')
        option = ET.fromstring(request['source_xml']).find('option')
        source_integrator = 'euler' if option is None else option.get('integrator', 'euler').lower()
        if source_integrator not in {'euler', 'implicitfast'}:
            raise ValueError('GeoPhys device batch does not admit the source integrator')
        if option is not None and option.get('timestep') is not None and not math.isclose(
                float(option.get('timestep')), float(request['physics_dt']), rel_tol=0, abs_tol=1e-12):
            raise ValueError('GeoPhys native timestep differs from the source')
        if option is not None and option.get('gravity') is not None:
            gravity = tuple(float(value) for value in option.get('gravity').split())
            if gravity != tuple(float(value) for value in request['gravity']):
                raise ValueError('GeoPhys gravity differs from the source')
        scene_definition = SceneDefinition.from_mapping(request['scene_definition'])
        imported = import_scene_source(SceneSource.mjcf_string(
            request['source_xml'], base_dir=root, label=request['source_id']), cache=False)
        validate_canonical_scene_import(scene_definition, imported)
        model = imported.build_rigid_scene_model(use_imported_meshes=True)
        data = model.joint_data
        binding = PhysicalControlBindingV1.from_mapping(request['binding'])
        channels = binding.channels
        if source_integrator == 'implicitfast':
            _validate_implicitfast_smooth_equivalence(model, option)
        if any(channel.native_drive != 'disabled' for channel in channels) or binding.bodies:
            raise ValueError('GeoPhys device batch requires isolated named joint effort')
        name_to_joint = data['name_to_joint']
        self._joint_qpos = {}
        for key, native in request['source_joints'].items():
            joint = int(name_to_joint[native])
            if int(data['jnt_type'][joint]) not in (2, 3):
                raise ValueError('GeoPhys named joint mapping requires a scalar joint')
            self._joint_qpos[key] = int(data['jnt_qposadr'][joint])
        self._free_qpos = {}
        for key, native in request['source_free_joints'].items():
            joint = int(name_to_joint[native])
            if int(data['jnt_type'][joint]) != 0:
                raise ValueError('GeoPhys free-joint mapping requires a native free joint')
            self._free_qpos[key] = int(data['jnt_qposadr'][joint])
        dofs, signs = [], []
        for channel, declared in zip(channels, request['joint_definitions'], strict=True):
            key = f'{channel.entity_id}/{channel.joint_id}'
            joint = int(name_to_joint[request['source_joints'][key]])
            if (int(data['jnt_type'][joint]) != (2 if channel.kind == 'revolute' else 3)
                    or channel.dof_id != 'dof0'
                    or not np.allclose(data['jnt_axis_child'][joint], declared['axis'], rtol=0, atol=1e-6)):
                raise ValueError('GeoPhys native joint type or axis differs from the source declaration')
            dofs.append(int(data['jnt_dofadr'][joint]))
            signs.append(float(channel.sign))
        if len(set(dofs)) != len(dofs) or any(index < 0 or index >= int(data['n_dof']) for index in dofs):
            raise ValueError('GeoPhys native DOF mapping is invalid or aliased')
        actuator_map = data['name_to_actuator']
        groups = {}
        for channel, dof in zip(channels, dofs, strict=True):
            groups.setdefault((channel.entity_id, channel.transmission_id), []).append((channel, dof))
        named = [group[0][0].native_actuator for group in groups.values()]
        if len(named) != len(set(named)) or set(named) != set(actuator_map):
            raise ValueError('GeoPhys isolated effort requires every native actuator exactly once')
        for group in groups.values():
            first = group[0][0]
            index = int(actuator_map[first.native_actuator])
            start, count = int(data['actuator_moment_adr'][index]), int(data['actuator_moment_num'][index])
            total = int(data['n_actuator_moments'])
            if start < 0 or count < 1 or start + count > total:
                raise ValueError('GeoPhys native actuator moment layout is invalid')
            actual = sorted((int(data['actuator_moment_dofadr'][i]),
                             int(data['actuator_moment_qposadr'][i]),
                             float(data['actuator_moment_coef'][i])) for i in range(start, start + count))
            expected = sorted((dof, self._joint_qpos[f'{channel.entity_id}/{channel.joint_id}'],
                               float(channel.transmission_coefficient)) for channel, dof in group)
            if (len(actual) != len(expected) or any(
                    a[:2] != b[:2] or not math.isclose(a[2], b[2], rel_tol=0, abs_tol=1e-6)
                    for a, b in zip(actual, expected, strict=True))):
                raise ValueError('GeoPhys native actuator moments differ from the declared transmission')
            for channel, _ in group:
                bounds = sorted(channel.transmission_coefficient * value for value in channel.native_range)
                if not np.allclose(bounds, channel.effort_range, rtol=0, atol=1e-9):
                    raise ValueError('GeoPhys declared effort range differs from its transmission')
        bodies = {obj.object_key: int(obj.object_id) for obj in model.objects}
        for root in request['fixed_roots']:
            root_id = bodies[root]
            if int(data['body_parentid'][root_id]) >= 0 or int(data['body_jntnum'][root_id]) != 0:
                raise ValueError('GeoPhys source subject root is not fixed to the world')
        self._source_integrator = source_integrator
        self._contact_mode = request.get('contact_mode', 'provider_default')
        if self._contact_mode not in ('provider_default', 'discrete', 'continuous'):
            raise ValueError('unsupported GeoPhys contact mode')
        self._nq, self._nv = int(data['n_qpos']), int(data['n_dof'])
        self._body_names = tuple(request['source_bodies'])
        self._body_indices = tuple(bodies[request['source_bodies'][name]] for name in self._body_names)
        self._frame_names = tuple(request['source_frames'])
        site_ids = [int(data['name_to_site'][name]) for name in request['source_frames'].values()]
        site_bodies = [int(data['site_bodyid'][index]) for index in site_ids]
        if any(index < 0 or index >= len(model.objects) for index in site_bodies):
            raise ValueError('GeoPhys source frame must belong to a native body')
        if site_ids:
            self._site_body_tensor = torch.tensor(site_bodies, dtype=torch.int64, device='cuda')
            self._site_pos_tensor = torch.tensor(np.asarray(data['site_pos'])[site_ids], dtype=torch.float32, device='cuda')
            self._site_quat_tensor = torch.tensor(np.asarray(data['site_quat'])[site_ids], dtype=torch.float32, device='cuda')
        self._dofs, self._signs = tuple(dofs), tuple(signs)
        self.num_envs = int(request['num_envs'])
        self._num_bodies = len(model.objects)
        self._substeps = int(request['control_substeps'])
        self._physics_dt = float(request['physics_dt'])
        if self.num_envs < 1 or self._substeps < 1:
            raise ValueError('GeoPhys batch size and substeps must be positive')
        runtime_config = SimpleNamespace(integrator='euler', enable_ground_contact=False,
            enable_domain_boundary_contact=False, physics_dt=self._physics_dt,
            gravity=tuple(request['gravity']), broadphase=request['broadphase'],
            rigid_solver_backend=None, body_contact_solver_iterations=None,
            control_substeps=self._substeps, backend='cuda', contact_mode=self._contact_mode)
        try:
            self._runtime = GeoPhysRigidBatchRuntime.from_compiled_scene(
                compiled_scene=SimpleNamespace(scene_model=model), config=SimpleNamespace(runtime=runtime_config),
                num_envs=self.num_envs, backend='cuda')
            self._runtime.solver.set_actuator_enabled(tuple(range(len(actuator_map))), False)
            count, nbody = self.num_envs, len(self._body_names)
            fields = {'qpos': ((count, self._nq), 'float32'), 'qvel': ((count, self._nv), 'float32'),
                      'body_position': ((count, nbody, 3), 'float32'),
                      'body_orientation': ((count, nbody, 4), 'float32'),
                      'reset_qpos': ((count, self._nq), 'float32'), 'reset_qvel': ((count, self._nv), 'float32'),
                      'reset_mask': ((count,), 'bool'), 'effort': ((count, len(channels)), 'float32')}
            if self._frame_names:
                fields.update(frame_position=((count, len(self._frame_names), 3), 'float32'),
                              frame_orientation=((count, len(self._frame_names), 4), 'float32'))
            self._publisher = CudaIpcDuplexPublisher(fields)
            self._body_index_tensor = torch.tensor(self._body_indices, dtype=torch.int64, device='cuda')
            self._publish()
        except BaseException as error:
            try:
                self.close()
            except BaseException as cleanup_error:
                error.add_note(f'GeoPhys construction cleanup failed: {cleanup_error!r}')
                for note in getattr(cleanup_error, '__notes__', ()):
                    error.add_note(note)
            raise

    def description(self):
        description = self._publisher.description()
        description.update(nq=self._nq, nv=self._nv, body_names=list(self._body_names), frame_names=list(self._frame_names),
            joint_qpos_indices=self._joint_qpos, free_joint_qpos_indices=self._free_qpos,
            physical_layout_facts={'source_dofs': list(self._dofs), 'source_signs': list(self._signs),
                                   'native_integrator': 'euler', 'source_integrator': self._source_integrator,
                                   'scope': 'source-layout isolated effort; solver-admitted dynamics',
                                   'contact_mode_requested': self._contact_mode,
                                   'contact_mode_resolved': self._runtime.contact_mode_resolved,
                                   'native_clock': 'BatchedRigidSolver direct step count and dt'})
        return description

    def bind_written_event(self, handle):
        self._publisher.bind_written_event(handle)

    def _publish(self):
        state = self._runtime.read_device_state(('qpos', 'qvel', 'body_position', 'body_orientation'))
        arrays = dict(state.arrays)
        if self._frame_names:
            arrays['frame_position'], arrays['frame_orientation'] = _compose_site_poses(
                arrays['body_position'].index_select(1, self._site_body_tensor),
                arrays['body_orientation'].index_select(1, self._site_body_tensor),
                self._site_pos_tensor, self._site_quat_tensor)
        for name in ('body_position', 'body_orientation'):
            arrays[name] = arrays[name].index_select(1, self._body_index_tensor).contiguous()
        self._publisher.publish(arrays)

    def reset(self):
        import torch
        before = self._runtime.solver.read_direct_step_clock()
        inputs = self._publisher.read_inputs(('reset_qpos', 'reset_qvel', 'reset_mask'))
        state = self._runtime.read_device_state(('body_position', 'body_orientation'))
        positions, orientations = state.arrays['body_position'], state.arrays['body_orientation']
        self._runtime.reset_device_state(mask=inputs['reset_mask'], qpos=inputs['reset_qpos'],
            qvel=inputs['reset_qvel'], body_position=positions, body_orientation=orientations,
            body_linear_velocity=torch.zeros_like(positions), body_angular_velocity=torch.zeros_like(positions))
        self._publish()
        if self._runtime.solver.read_direct_step_clock() != before:
            raise RuntimeError('GeoPhys reset or publication advanced the native direct-step clock')

    def step(self):
        import torch
        before = self._runtime.solver.read_direct_step_clock()
        inputs = self._publisher.read_inputs(('effort',))
        forces = torch.zeros((self.num_envs, self._nv), dtype=torch.float32, device='cuda')
        for channel, (dof, sign) in enumerate(zip(self._dofs, self._signs, strict=True)):
            forces[:, dof] = inputs['effort'][:, channel] * sign
        self._runtime.write_device_qfrc(forces)
        self._runtime.step_substeps()
        self._publish()
        after = self._runtime.solver.read_direct_step_clock()
        if after[0] - before[0] != self._substeps or not math.isclose(
                after[1] - before[1], self._substeps * self._physics_dt, rel_tol=1e-9, abs_tol=1e-12):
            raise RuntimeError('GeoPhys native direct-step clock differs from the Task timebase')

    def close(self):
        if self._closed:
            return
        first_error = None
        for name in ('_publisher', '_runtime'):
            resource = getattr(self, name)
            if resource is None:
                continue
            try:
                resource.close()
            except BaseException as error:
                if first_error is None:
                    first_error = error
                else:
                    first_error.add_note(f'Additional {name} cleanup failure: {error!r}')
            else:
                setattr(self, name, None)
        self._closed = self._publisher is None and self._runtime is None
        if first_error is not None:
            raise first_error


class GeoPhysDeviceBatchSession(DevicePhysicalBatchSession):
    """Use the common source-bound device session with one GeoPhys worker."""
    _provider_label = 'GeoPhys'

    def __init__(self, built, *, num_envs, device, interpreter, runtime_config=None,
                 contact_mode='provider_default', working_directory=None):
        import math
        from ....controllers.canonical.physical_controller import DirectJointEffortControllerV1, LinearEffortControllerV1
        from ...sessions.physical_control import PhysicalControlExecutionV1
        from ...sessions.source import lower_mujoco_scene_source
        from ...transport.cuda_ipc import CudaIpcConnection
        from ...transport.worker import RuntimeWorker

        if contact_mode not in ('provider_default', 'discrete', 'continuous'):
            raise ValueError('unsupported GeoPhys contact mode')

        source, artifact, execution = built['source'], built['artifact'], built['physical_execution']
        if type(execution) is not PhysicalControlExecutionV1:
            raise TypeError('GeoPhys device batch requires source-bound physical execution')
        execution.validate_source(scene=source.scene_definition, artifact_sha256=artifact.identity_hash,
            source_id=source.source_id, source_closure_sha256=source.source_closure_digest, source=source)
        if (len(execution.controllers) != 1 or type(execution.controllers[0]) not in
                (DirectJointEffortControllerV1, LinearEffortControllerV1)):
            raise ValueError('GeoPhys device batch requires one source-bound effort Controller')
        controller, binding = execution.controllers[0], execution.compiled.binding
        if (binding.bodies or controller.channel_keys != tuple(channel.target_key for channel in binding.channels)
                or any(channel.owner_ids != (controller.writer_id,) or channel.native_drive != 'disabled'
                       for channel in binding.channels)):
            raise ValueError('GeoPhys device batch requires exclusive source joint-effort channels')
        count = int(num_envs)
        if isinstance(num_envs, bool) or count != num_envs or count < 1 or str(device) != 'cuda:0':
            raise ValueError('GeoPhys device batch requires positive B and cuda:0')
        timebase = artifact.timebase
        if not math.isclose(timebase.physics_dt * timebase.control_substeps, timebase.control_dt,
                            rel_tol=0, abs_tol=1e-12):
            raise ValueError('Task timebase has inconsistent control cadence')
        xml, assets = lower_mujoco_scene_source(source.scene_source, source.scene_definition,
                                                source.source_closure_digest)
        request = {'provider': 'geophys', 'device': str(device), 'source_id': source.source_id,
            'source_xml': xml, 'source_assets': {name: base64.b64encode(value).decode('ascii')
                                                 for name, value in assets.items()},
            'scene_definition': source.scene_definition.to_mapping(), 'binding': binding.to_mapping(),
            'source_bodies': dict(source.bodies), 'source_frames': dict(source.frames),
            'source_joints': dict(source.joints), 'source_free_joints': dict(source.free_joints),
            'joint_definitions': [execution.joint_bindings[f'{c.entity_id}/{c.joint_id}'].to_mapping()
                                  for c in binding.channels],
            'fixed_roots': [subject.root_frame.frame_id for subject in execution.subjects
                            if subject.root_mode == 'fixed'],
            'num_envs': count, 'physics_dt': timebase.physics_dt,
            'control_substeps': timebase.control_substeps,
            'gravity': source.config.runtime.gravity, 'broadphase': source.config.runtime.broadphase,
            'contact_mode': contact_mode}
        self.num_envs, self.device = count, str(device)
        self._source, self._artifact, self._execution = source, artifact, execution
        self._source_identity = (source.source_id, source.source_closure_digest, artifact.identity_hash)
        self._binding, self._controller, self._binding_hash = binding, controller, binding.identity_hash
        mode_prefix = '' if contact_mode == 'provider_default' else contact_mode + '-'
        self._materialization_id = 'geophys-' + mode_prefix + uuid.uuid4().hex
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
                error.add_note(f'GeoPhys construction cleanup failed: {cleanup_error!r}')
            raise

    def resource_summary(self):
        return {'num_envs': self.num_envs, 'provider': 'geophys',
            'device_transition': {'available': True, 'field_device': self.device,
                'transport': 'cuda_ipc', 'state_readback_fields': list(self._state_shapes),
                'state_shapes': self._state_shapes, 'body_names': self._body_names,
                'frame_names': self._frame_names, 'joint_qpos_indices': dict(self._joint_qpos),
                'free_joint_qpos_indices': dict(self._free_qpos),
                'physical_layout_facts': dict(self._layout_facts),
                'pose_layout': 'world_body_xyz_wxyz_env_local'}}
