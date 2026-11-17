"""Native MJWarp homogeneous data owned by the isolated provider worker."""
import base64

from ...transport.device_batch_session import DevicePhysicalBatchSession


def _encoded(value):
    return base64.b64encode(value).decode('ascii')


class MuJoCoWarpNativeBatch:
    """One model and one native multi-world data object, without Task semantics."""

    def __init__(self, request):
        import mujoco
        import mujoco_warp as mjw
        import numpy as np
        import warp as wp
        from ...sessions.mujoco_physical import validate_physical_joint_mapping
        from ....artifacts import JointDefinition
        from ....controllers.canonical.physical_commands import PhysicalControlBindingV1

        wp.init()
        device = wp.get_device(request['device'])
        if not device.is_cuda or not device.is_ipc_supported:
            raise RuntimeError('MJWarp device must support CUDA IPC')
        xml = request['source_xml']
        assets = {name: base64.b64decode(payload, validate=True)
                  for name, payload in request['source_assets'].items()}
        model = mujoco.MjModel.from_xml_string(xml, assets=assets)
        if float(model.opt.timestep) != float(request['physics_dt']):
            raise ValueError('MJWarp model timestep differs from the Task timebase')
        binding = PhysicalControlBindingV1.from_mapping(request['binding'])
        channels = binding.channels
        definitions = {(channel.entity_id, channel.joint_id): JointDefinition.from_mapping(value)
                       for channel, value in zip(channels, request['joint_definitions'], strict=True)}
        layout_facts = {}
        dof_by_key, _ = validate_physical_joint_mapping(
            model, mujoco, binding, definitions, source_joints=request['source_joints'],
            torque_actuators=request['torque_actuators'], position_actuators=request['position_actuators'],
            joint_targets=request['joint_targets'], open_actuators=request['open_actuators'],
            gripper_force_limit=request['gripper_force_limit'], fixed_roots=request['fixed_roots'],
            build_layout_facts=layout_facts)
        dofs = [dof_by_key[channel.target_key] for channel in channels]
        signs = [channel.sign for channel in channels]
        count = int(request['num_envs'])
        if count < 1:
            raise ValueError('MJWarp num_envs must be positive')
        self._wp, self._mjw, self._mujoco, self._device, self._model = wp, mjw, mujoco, device, model
        self._layout_facts = {**layout_facts, 'native_world_clock': 'MJWarp Data.time in seconds'}
        self.num_envs, self.substeps = count, int(request['control_substeps'])
        self._joint_qpos = {}
        for semantic, native in request['source_joints'].items():
            joint_id = int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, native))
            if joint_id < 0 or int(model.jnt_type[joint_id]) not in (
                    int(mujoco.mjtJoint.mjJNT_HINGE), int(mujoco.mjtJoint.mjJNT_SLIDE)):
                raise ValueError('MJWarp named joint mapping requires a native scalar joint')
            self._joint_qpos[semantic] = int(model.jnt_qposadr[joint_id])
        self._free_qpos = {}
        for semantic, native in request['source_free_joints'].items():
            joint_id = int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, native))
            if joint_id < 0 or int(model.jnt_type[joint_id]) != int(mujoco.mjtJoint.mjJNT_FREE):
                raise ValueError('MJWarp free-joint mapping requires a native free joint')
            self._free_qpos[semantic] = int(model.jnt_qposadr[joint_id])
        self._body_names = tuple(request.get('source_bodies', {}))
        body_ids = [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, native)
                    for native in request.get('source_bodies', {}).values()]
        if any(body_id < 0 for body_id in body_ids):
            raise ValueError('MJWarp source body mapping contains an unknown native body')
        load_ids = []
        for body in binding.bodies:
            semantic = f'{body.entity_id}/{body.body_id}'
            sources = request['source_bodies']
            if semantic not in sources and sources.get(body.entity_id) == body.native_body:
                semantic = body.entity_id
            if sources.get(semantic) != body.native_body:
                raise ValueError('MJWarp body load differs from its source mapping')
            body_id = int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body.native_body))
            if body_id <= 0 or int(model.body_jntnum[body_id]) != 1:
                raise ValueError('MJWarp body load requires one explicit FREE joint')
            joint_id = int(model.body_jntadr[body_id])
            if int(model.jnt_type[joint_id]) != int(mujoco.mjtJoint.mjJNT_FREE):
                raise ValueError('MJWarp body load requires one explicit FREE joint')
            if body_id in load_ids:
                raise ValueError('MJWarp body load bindings alias the same native body')
            load_ids.append(body_id)
        if load_ids and count != 1:
            raise ValueError('MJWarp body loads are currently admitted only for batch size one')
        self._load_body_native_ids = tuple(load_ids)
        self._frame_names = tuple(request.get('source_frames', {}))
        frame_ids = [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, native)
                     for native in request.get('source_frames', {}).values()]
        if any(frame_id < 0 for frame_id in frame_ids):
            raise ValueError('MJWarp source frame mapping contains an unknown native site')
        if self.substeps < 1:
            raise ValueError('control substeps must be positive')
        # MJWarp's generic default of 64 constraint rows is insufficient for
        # contact-rich articulated sources. Size from the source's collidable
        # geometry and retain the native overflow flags as a hard error.
        collidable = int(np.count_nonzero((model.geom_contype != 0) | (model.geom_conaffinity != 0)))
        nconmax = max(48, 4 * collidable)
        njmax = max(64, 8 * nconmax + 6 * model.neq + model.njnt + model.nv)
        self._capacities = {'contacts_per_world': nconmax, 'constraint_rows_per_world': njmax}
        with wp.ScopedMempool(device, False):
            self._model_device = mjw.put_model(model)
            self._data = mjw.put_data(model, mujoco.MjData(model), nworld=count,
                                     nconmax=nconmax, njmax=njmax)
            self._buffers = {
                'qpos': wp.zeros((count, model.nq), dtype=wp.float32, device=device),
                'qvel': wp.zeros((count, model.nv), dtype=wp.float32, device=device),
                'native_world_time': wp.zeros(count, dtype=wp.float32, device=device),
                'reset_qpos': wp.zeros((count, model.nq), dtype=wp.float32, device=device),
                'reset_qvel': wp.zeros((count, model.nv), dtype=wp.float32, device=device),
                'reset_mask': wp.zeros(count, dtype=wp.bool, device=device),
                'effort': wp.zeros((count, len(channels)), dtype=wp.float32, device=device),
            }
            if body_ids:
                self._buffers['body_position'] = wp.zeros((count, len(body_ids), 3), dtype=wp.float32, device=device)
                self._buffers['body_orientation'] = wp.zeros((count, len(body_ids), 4), dtype=wp.float32, device=device)
            if frame_ids:
                self._buffers['frame_position'] = wp.zeros((count, len(frame_ids), 3), dtype=wp.float32, device=device)
                self._buffers['frame_orientation'] = wp.zeros((count, len(frame_ids), 4), dtype=wp.float32, device=device)
            if load_ids:
                self._buffers['body_wrench'] = wp.zeros((count, len(load_ids), 6), dtype=wp.float32, device=device)
        self._dofs = wp.array(dofs, dtype=wp.int32, device=device)
        self._signs = wp.array(signs, dtype=wp.float32, device=device)
        self._body_ids = wp.array(body_ids, dtype=wp.int32, device=device) if body_ids else None
        self._frame_ids = wp.array(frame_ids, dtype=wp.int32, device=device) if frame_ids else None
        self._load_body_ids = wp.array(load_ids, dtype=wp.int32, device=device) if load_ids else None
        self._ready = wp.Event(device=device, interprocess=True)
        self._written = None
        self._closed = False
        @wp.kernel
        def apply_effort(values: wp.array2d(dtype=wp.float32), ids: wp.array(dtype=wp.int32),
                         direction: wp.array(dtype=wp.float32), force: wp.array2d(dtype=wp.float32)):
            row, column = wp.tid()
            force[row, ids[column]] = values[row, column] * direction[column]

        @wp.kernel
        def apply_body_wrench(values: wp.array3d(dtype=wp.float32), ids: wp.array(dtype=wp.int32),
                              native: wp.array2d(dtype=wp.spatial_vector)):
            row, column = wp.tid()
            native[row, ids[column]] = wp.spatial_vector(values[row, column, 0], values[row, column, 1],
                values[row, column, 2], values[row, column, 3], values[row, column, 4], values[row, column, 5])

        @wp.kernel
        def apply_reset(mask: wp.array(dtype=wp.bool), q: wp.array2d(dtype=wp.float32),
                        v: wp.array2d(dtype=wp.float32), native_q: wp.array2d(dtype=wp.float32),
                        native_v: wp.array2d(dtype=wp.float32)):
            row, column = wp.tid()
            if mask[row]:
                if column < native_q.shape[1]:
                    native_q[row, column] = q[row, column]
                if column < native_v.shape[1]:
                    native_v[row, column] = v[row, column]

        @wp.kernel
        def copy_body_pose(ids: wp.array(dtype=wp.int32), positions: wp.array2d(dtype=wp.vec3),
                           orientations: wp.array2d(dtype=wp.quat),
                           out_positions: wp.array3d(dtype=wp.float32),
                           out_orientations: wp.array3d(dtype=wp.float32)):
            row, body = wp.tid()
            position = positions[row, ids[body]]
            orientation = orientations[row, ids[body]]
            for component in range(3):
                out_positions[row, body, component] = position[component]
            for component in range(4):
                out_orientations[row, body, component] = orientation[component]

        @wp.kernel
        def copy_frame_pose(ids: wp.array(dtype=wp.int32), positions: wp.array2d(dtype=wp.vec3),
                            rotations: wp.array2d(dtype=wp.mat33),
                            out_positions: wp.array3d(dtype=wp.float32),
                            out_orientations: wp.array3d(dtype=wp.float32)):
            row, frame = wp.tid()
            position = positions[row, ids[frame]]
            quat = wp.quat_from_matrix(rotations[row, ids[frame]])
            for component in range(3):
                out_positions[row, frame, component] = position[component]
                out_orientations[row, frame, component + 1] = quat[component]
            out_orientations[row, frame, 0] = quat[3]

        self._apply_effort, self._apply_reset, self._copy_body_pose = apply_effort, apply_reset, copy_body_pose
        self._apply_body_wrench = apply_body_wrench
        self._copy_frame_pose = copy_frame_pose
        self._publish()

    def description(self):
        import sys
        return {'device': str(self._device), 'ready': _encoded(self._ready.ipc_handle()),
                'buffers': {name: {'handle': _encoded(value.ipc_handle()),
                                   'shape': list(value.shape),
                                   'dtype': 'bool' if name == 'reset_mask' else 'float32'}
                            for name, value in self._buffers.items()},
                'mujoco_version': self._mujoco.__version__, 'mujoco_warp_version': self._mjw.__version__,
                'warp_version': self._wp.__version__,
                'python': sys.executable, 'python_version': list(sys.version_info[:2]),
                'module_paths': {'mujoco': self._mujoco.__file__, 'mujoco_warp': self._mjw.__file__,
                                 'warp': self._wp.__file__},
                'nq': self._model.nq, 'nv': self._model.nv, 'body_names': list(self._body_names),
                'frame_names': list(self._frame_names), 'physical_layout_facts': self._layout_facts,
                'load_body_ids': list(self._load_body_native_ids),
                'native_capacities': self._capacities,
                'joint_qpos_indices': self._joint_qpos, 'free_joint_qpos_indices': self._free_qpos}

    def bind_written_event(self, encoded):
        if self._written is not None:
            raise RuntimeError('worker input event is already bound')
        handle = base64.b64decode(encoded, validate=True)
        if len(handle) != 64:
            raise ValueError('worker input event handle must have 64 bytes')
        self._written = self._wp.event_from_ipc_handle(handle, device=self._device)

    def _wait_input(self):
        if self._written is None or self._closed:
            raise RuntimeError('MJWarp input event is unavailable')
        self._wp.wait_event(self._written)

    def _publish(self):
        self._wp.copy(self._buffers['qpos'], self._data.qpos)
        self._wp.copy(self._buffers['qvel'], self._data.qvel)
        self._wp.copy(self._buffers['native_world_time'], self._data.time)
        if self._body_ids is not None:
            self._wp.launch(self._copy_body_pose, dim=(self.num_envs, len(self._body_names)),
                inputs=[self._body_ids, self._data.xpos, self._data.xquat,
                        self._buffers['body_position'], self._buffers['body_orientation']], device=self._device)
        if self._frame_ids is not None:
            self._wp.launch(self._copy_frame_pose, dim=(self.num_envs, len(self._frame_names)),
                inputs=[self._frame_ids, self._data.site_xpos, self._data.site_xmat,
                        self._buffers['frame_position'], self._buffers['frame_orientation']], device=self._device)
        self._wp.record_event(self._ready)

    def reset(self):
        self._wait_input()
        self._data.overflow.zero_()
        mask = self._buffers['reset_mask']
        self._mjw.reset_data(self._model_device, self._data, reset=mask)
        self._wp.launch(self._apply_reset, dim=(self.num_envs, max(self._model.nq, self._model.nv)),
            inputs=[mask, self._buffers['reset_qpos'], self._buffers['reset_qvel'],
                    self._data.qpos, self._data.qvel], device=self._device)
        self._mjw.forward(self._model_device, self._data)
        self._check_overflow()
        self._publish()

    def step(self):
        self._wait_input()
        self._data.overflow.zero_()
        self._data.qfrc_applied.zero_()
        self._data.xfrc_applied.zero_()
        self._wp.launch(self._apply_effort, dim=(self.num_envs, len(self._dofs)),
            inputs=[self._buffers['effort'], self._dofs, self._signs, self._data.qfrc_applied],
            device=self._device)
        if self._load_body_ids is not None:
            self._wp.launch(self._apply_body_wrench, dim=(self.num_envs, len(self._load_body_ids)),
                inputs=[self._buffers['body_wrench'], self._load_body_ids, self._data.xfrc_applied],
                device=self._device)
        for _ in range(self.substeps):
            self._mjw.step(self._model_device, self._data)
        self._data.qfrc_applied.zero_()
        self._data.xfrc_applied.zero_()
        # MJWarp's step integrates qpos after its derived-pose computation.
        # Refresh kinematics at the published boundary without advancing time.
        self._mjw.forward(self._model_device, self._data)
        self._check_overflow()
        self._publish()

    def _check_overflow(self):
        """Reject a corrupted native transition using only per-world status bits."""
        flags = self._data.overflow.numpy()
        if flags.any():
            raise RuntimeError(f'MJWarp native capacity overflow by world: {flags.tolist()}')

    def close(self):
        if self._closed:
            return
        self._wp.synchronize_device(self._device)
        self._written = None
        self._buffers.clear()
        self._ready = self._data = self._model_device = None
        self._dofs = self._signs = self._body_ids = self._frame_ids = self._load_body_ids = None
        self._closed = True


class MuJoCoWarpBatchSession(DevicePhysicalBatchSession):
    """Source-bound session proxy for one isolated native MJWarp batch."""

    _provider_label = "MJWarp"

    def __init__(self, built, *, num_envs, device, interpreter, runtime_config=None,
                 contact_mode='provider_default', working_directory=None):
        import math
        import uuid
        from ....controllers.canonical.physical_controller import DirectJointEffortControllerV1, LinearEffortControllerV1
        from ...sessions.physical_control import PhysicalControlExecutionV1
        from ...sessions.source import lower_mujoco_scene_source
        from ...transport.cuda_ipc import CudaIpcConnection
        from ...transport.worker import RuntimeWorker

        if contact_mode != 'provider_default':
            raise ValueError('MJWarp does not consume the GeoPhys contact mode')

        source, artifact, execution = built['source'], built['artifact'], built['physical_execution']
        if type(execution) is not PhysicalControlExecutionV1:
            raise TypeError('MJWarp requires a source-bound physical execution')
        execution.validate_source(scene=source.scene_definition, artifact_sha256=artifact.identity_hash,
            source_id=source.source_id, source_closure_sha256=source.source_closure_digest, source=source)
        if (len(execution.controllers) != 1
                or type(execution.controllers[0]) not in (DirectJointEffortControllerV1, LinearEffortControllerV1)):
            raise ValueError('MJWarp currently requires one direct joint-effort Controller')
        controller = execution.controllers[0]
        binding = execution.compiled.binding
        channels = binding.channels
        if (controller.channel_keys != tuple(channel.target_key for channel in channels)
                or any(channel.owner_ids != (controller.writer_id,) or channel.native_drive != 'disabled'
                       for channel in channels)):
            raise ValueError('MJWarp requires exclusive declared source joint-effort channels')
        count = int(num_envs)
        if isinstance(num_envs, bool) or count != num_envs or count < 1:
            raise ValueError('MJWarp batch size must be a positive integer')
        timebase = artifact.timebase
        if not math.isclose(timebase.physics_dt * timebase.control_substeps, timebase.control_dt,
                            rel_tol=0, abs_tol=1e-12):
            raise ValueError('Task timebase has inconsistent control cadence')
        if str(device) != 'cuda:0':
            raise ValueError('MJWarp profile currently admits cuda:0 only')
        source_xml, source_assets = lower_mujoco_scene_source(
            source.scene_source, source.scene_definition, source.source_closure_digest)
        gripper = getattr(getattr(source.config, 'robot', None), 'gripper', None)
        request = {'provider': 'mujoco_warp', 'device': str(device), 'source_xml': source_xml,
                   'source_assets': {name: _encoded(content) for name, content in source_assets.items()},
                   'source_bodies': dict(source.bodies), 'source_frames': dict(source.frames),
                   'source_joints': dict(source.joints), 'source_free_joints': dict(source.free_joints),
                   'num_envs': count,
                   'physics_dt': timebase.physics_dt, 'control_substeps': timebase.control_substeps,
                   'binding': binding.to_mapping(),
                   'joint_definitions': [execution.joint_bindings[
                       f'{channel.entity_id}/{channel.joint_id}'].to_mapping() for channel in channels],
                   'torque_actuators': dict(source.torque_actuators),
                   'position_actuators': dict(source.position_actuators),
                   'joint_targets': dict(source.joint_targets), 'open_actuators': list(source.open_actuators),
                   'gripper_force_limit': getattr(gripper, 'force_limit_N', None),
                   'fixed_roots': [subject.root_frame.frame_id for subject in execution.subjects
                                   if subject.root_mode == 'fixed']}
        self.num_envs, self.device = count, str(device)
        self._source, self._artifact, self._execution = source, artifact, execution
        self._source_identity = (source.source_id, source.source_closure_digest, artifact.identity_hash)
        self._binding, self._controller = binding, controller
        self._binding_hash = binding.identity_hash
        self._materialization_id = 'mjwarp-' + uuid.uuid4().hex
        self._generation, self._revision = int(execution.generation), 0
        self._native_steps = 0
        self._physics_dt = float(timebase.physics_dt)
        self._control_substeps = int(timebase.control_substeps)
        self._control_dt = float(timebase.control_dt)
        self._last_state = None
        self._device_limits = None
        self._closed = self._faulted = False
        self._worker = self._ipc = None
        try:
            self._worker = RuntimeWorker(interpreter, request, working_directory=working_directory)
            description = self._worker.description
            if (description['mujoco_version'], description['mujoco_warp_version'],
                    description['warp_version'], description['python_version']) != (
                        '4.0.1', '4.0.1', '1.18.0', [3, 12]):
                raise ValueError('MJWarp worker does not match the resolved dependency profile')
            self._profile = {name: description[name] for name in ('python', 'python_version',
                'mujoco_version', 'mujoco_warp_version', 'warp_version', 'module_paths')}
            self._ipc = CudaIpcConnection(description)
            self._body_names = tuple(description['body_names'])
            self._frame_names = tuple(description['frame_names'])
            self._joint_qpos = dict(description['joint_qpos_indices'])
            self._free_qpos = dict(description['free_joint_qpos_indices'])
            self._layout_facts = dict(description['physical_layout_facts'])
            native_body_ids = description['load_body_ids']
            if (len(native_body_ids) != len(binding.bodies)
                    or any(type(value) is not int or value <= 0 for value in native_body_ids)
                    or len(set(native_body_ids)) != len(native_body_ids)):
                raise ValueError('MJWarp native body build facts differ from the declared binding')
            if binding.bodies:
                self._layout_facts['scene_body_build_v1'] = {
                    'binding_sha256': binding.identity_hash,
                    'source_closure_sha256': source.source_closure_digest,
                    'materialization_id': self._materialization_id,
                    'bodies': [{'entity_id': body.entity_id, 'body_id': body.body_id,
                                'native_body': body.native_body, 'native_id': native_id}
                               for body, native_id in zip(binding.bodies, native_body_ids, strict=True)],
                    'provenance': 'native_build',
                }
            self._capacities = dict(description['native_capacities'])
            self._state_shapes = {'qpos': (int(description['nq']),), 'qvel': (int(description['nv']),)}
            self._state_shapes['native_world_time'] = ()
            if self._body_names:
                self._state_shapes.update(body_position=(len(self._body_names), 3),
                                          body_orientation=(len(self._body_names), 4))
            if self._frame_names:
                self._state_shapes.update(frame_position=(len(self._frame_names), 3),
                                          frame_orientation=(len(self._frame_names), 4))
            self._worker.call('bind_event', handle=self._ipc.written_handle)
        except BaseException as error:
            try:
                self.close()
            except BaseException as cleanup_error:
                error.add_note(f'MJWarp construction cleanup failed: {cleanup_error!r}')
            raise

    def resource_summary(self):
        return {'num_envs': self.num_envs, 'provider': 'mujoco_warp',
                'dependency_profile': dict(self._profile),
                'device_transition': {'available': True, 'field_device': self.device,
                    'transport': 'cuda_ipc', 'state_readback_fields': list(self._state_shapes),
                    'state_shapes': self._state_shapes,
                    'body_names': self._body_names, 'frame_names': self._frame_names,
                    'joint_qpos_indices': dict(self._joint_qpos),
                    'free_joint_qpos_indices': dict(self._free_qpos),
                    'physical_layout_facts': dict(self._layout_facts),
                    'native_capacities': dict(self._capacities),
                    'pose_layout': 'world_body_xyz_wxyz_env_local'}}
