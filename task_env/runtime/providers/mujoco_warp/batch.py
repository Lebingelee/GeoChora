"""Native MJWarp homogeneous data owned by the isolated provider worker."""
import base64
import xml.etree.ElementTree as ET


def _encoded(value):
    return base64.b64encode(value).decode('ascii')


class MuJoCoWarpNativeBatch:
    """One model and one native multi-world data object, without Task semantics."""

    def __init__(self, request):
        import mujoco
        import mujoco_warp as mjw
        import warp as wp
        from ...sessions.mujoco_physical import resolve_physical_joint, validate_direct_motor
        from ....artifacts import JointDefinition
        from ....controllers.canonical.physical_commands import PhysicalJointChannelV1

        wp.init()
        device = wp.get_device(request['device'])
        if not device.is_cuda or not device.is_ipc_supported:
            raise RuntimeError('MJWarp device must support CUDA IPC')
        xml = request['source_xml']
        root = ET.fromstring(xml)
        if any(node.get('file') for node in root.findall('./asset/*')):
            raise ValueError('MJWarp profile does not yet support external source files')
        model = mujoco.MjModel.from_xml_string(xml)
        if float(model.opt.timestep) != float(request['physics_dt']):
            raise ValueError('MJWarp model timestep differs from the Task timebase')
        channels = [PhysicalJointChannelV1.from_mapping(value['channel'])
                    for value in request['channels']]
        definitions = [JointDefinition.from_mapping(value['joint']) for value in request['channels']]
        if not channels or len(channels) != int(model.nu):
            raise ValueError('MJWarp direct effort requires every actuator to be declared')
        dofs, qpos_indices, actuators, signs = [], [], set(), []
        for channel, definition in zip(channels, definitions, strict=True):
            if (channel.native_drive != 'disabled' or channel.transmission_coefficient != 1.0
                    or len(channel.owner_ids) != 1):
                raise ValueError('MJWarp direct effort requires exclusive unit joint transmissions')
            joint_id, dof = resolve_physical_joint(model, mujoco, request['source_joints'],
                                                   definition, channel)
            actuator = int(model.actuator(channel.native_actuator).id)
            validate_direct_motor(model, mujoco, actuator, channel)
            if (dof in dofs or actuator in actuators
                    or int(model.actuator_trntype[actuator]) != int(mujoco.mjtTrn.mjTRN_JOINT)
                    or int(model.actuator_trnid[actuator, 0]) != joint_id):
                raise ValueError('MJWarp named joints, DOFs or actuator transmissions conflict')
            dofs.append(dof)
            qpos_indices.append(int(model.jnt_qposadr[joint_id]))
            actuators.add(actuator)
            signs.append(channel.sign)
        if actuators != set(range(model.nu)):
            raise ValueError('MJWarp must isolate every source actuator')
        if (model.nq != len(channels) or model.nv != len(channels)
                or dofs != list(range(model.nv)) or qpos_indices != list(range(model.nq))):
            raise ValueError('MJWarp profile requires source-ordered scalar joint coordinates')
        model.opt.disableflags |= int(mujoco.mjtDisableBit.mjDSBL_ACTUATION)
        count = int(request['num_envs'])
        if count < 1:
            raise ValueError('MJWarp num_envs must be positive')
        self._wp, self._mjw, self._mujoco, self._device, self._model = wp, mjw, mujoco, device, model
        self.num_envs, self.substeps = count, int(request['control_substeps'])
        self._body_names = tuple(request.get('source_bodies', {}))
        body_ids = [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, native)
                    for native in request.get('source_bodies', {}).values()]
        if any(body_id < 0 for body_id in body_ids):
            raise ValueError('MJWarp source body mapping contains an unknown native body')
        self._frame_names = tuple(request.get('source_frames', {}))
        frame_ids = [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, native)
                     for native in request.get('source_frames', {}).values()]
        if any(frame_id < 0 for frame_id in frame_ids):
            raise ValueError('MJWarp source frame mapping contains an unknown native site')
        if self.substeps < 1:
            raise ValueError('control substeps must be positive')
        with wp.ScopedMempool(device, False):
            self._model_device = mjw.put_model(model)
            self._data = mjw.put_data(model, mujoco.MjData(model), nworld=count)
            self._buffers = {
                'qpos': wp.zeros((count, model.nq), dtype=wp.float32, device=device),
                'qvel': wp.zeros((count, model.nv), dtype=wp.float32, device=device),
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
        self._dofs = wp.array(dofs, dtype=wp.int32, device=device)
        self._signs = wp.array(signs, dtype=wp.float32, device=device)
        self._body_ids = wp.array(body_ids, dtype=wp.int32, device=device) if body_ids else None
        self._frame_ids = wp.array(frame_ids, dtype=wp.int32, device=device) if frame_ids else None
        self._ready = wp.Event(device=device, interprocess=True)
        self._written = None
        self._closed = False
        @wp.kernel
        def apply_effort(values: wp.array2d(dtype=wp.float32), ids: wp.array(dtype=wp.int32),
                         direction: wp.array(dtype=wp.float32), force: wp.array2d(dtype=wp.float32)):
            row, column = wp.tid()
            force[row, ids[column]] = values[row, column] * direction[column]

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
                'frame_names': list(self._frame_names)}

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
        mask = self._buffers['reset_mask']
        self._mjw.reset_data(self._model_device, self._data, reset=mask)
        self._wp.launch(self._apply_reset, dim=(self.num_envs, max(self._model.nq, self._model.nv)),
            inputs=[mask, self._buffers['reset_qpos'], self._buffers['reset_qvel'],
                    self._data.qpos, self._data.qvel], device=self._device)
        self._mjw.forward(self._model_device, self._data)
        self._publish()

    def step(self):
        self._wait_input()
        self._data.qfrc_applied.zero_()
        self._wp.launch(self._apply_effort, dim=(self.num_envs, len(self._dofs)),
            inputs=[self._buffers['effort'], self._dofs, self._signs, self._data.qfrc_applied],
            device=self._device)
        for _ in range(self.substeps):
            self._mjw.step(self._model_device, self._data)
        self._data.qfrc_applied.zero_()
        # MJWarp's step integrates qpos after its derived-pose computation.
        # Refresh kinematics at the published boundary without advancing time.
        self._mjw.forward(self._model_device, self._data)
        self._publish()

    def close(self):
        if self._closed and self._ipc is None and self._worker is None:
            return
        self._wp.synchronize_device(self._device)
        self._written = None
        self._buffers.clear()
        self._ready = self._data = self._model_device = None
        self._dofs = self._signs = self._body_ids = self._frame_ids = None
        self._closed = True


class MuJoCoWarpBatchSession:
    """Source-bound session proxy for one isolated native MJWarp batch."""

    def __init__(self, built, *, num_envs, device, interpreter, working_directory=None):
        import math
        import uuid
        from ....controllers.canonical.physical_controller import DirectJointEffortControllerV1
        from ...sessions.physical_control import PhysicalControlExecutionV1
        from ...transport.cuda_ipc import CudaIpcConnection
        from ...transport.worker import RuntimeWorker

        source, artifact, execution = built['source'], built['artifact'], built['physical_execution']
        if type(execution) is not PhysicalControlExecutionV1:
            raise TypeError('MJWarp requires a source-bound physical execution')
        execution.validate_source(scene=source.scene_definition, artifact_sha256=artifact.identity_hash,
            source_id=source.source_id, source_closure_sha256=source.source_closure_digest, source=source)
        if (len(execution.controllers) != 1
                or type(execution.controllers[0]) is not DirectJointEffortControllerV1):
            raise ValueError('MJWarp currently requires one direct joint-effort Controller')
        controller = execution.controllers[0]
        binding = execution.compiled.binding
        channels = binding.channels
        if (binding.bodies or controller.channel_keys != tuple(channel.target_key for channel in channels)
                or any(channel.owner_ids != (controller.writer_id,) for channel in channels)
                or {f'{c.entity_id}/{c.joint_id}': c.native_actuator for c in channels}
                != dict(source.torque_actuators) or source.joint_targets or source.open_actuators):
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
        request = {'provider': 'mujoco_warp', 'device': str(device), 'source_xml': source.scene_source.xml,
                   'source_bodies': dict(source.bodies), 'source_frames': dict(source.frames),
                   'source_joints': dict(source.joints), 'num_envs': count,
                   'physics_dt': timebase.physics_dt, 'control_substeps': timebase.control_substeps,
                   'channels': [{'channel': channel.to_mapping(),
                                 'joint': execution.joint_bindings[
                                     f'{channel.entity_id}/{channel.joint_id}'].to_mapping()}
                                for channel in channels]}
        self.num_envs, self.device = count, str(device)
        self._source, self._artifact, self._execution = source, artifact, execution
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
            self._state_shapes = {'qpos': (int(description['nq']),), 'qvel': (int(description['nv']),)}
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

    def _require_live(self):
        if self._closed:
            raise RuntimeError('MJWarp batch session is closed')
        if self._faulted:
            raise RuntimeError('MJWarp batch session is faulted')

    def _identity(self):
        from ...contracts import DeviceStateIdentity
        return DeviceStateIdentity(self._source.source_id, self._source.source_closure_digest,
            self._artifact.identity_hash, self._materialization_id, self._generation,
            self._revision, self._native_steps, self._native_steps * self._physics_dt, self._control_dt)

    def _read_publication(self):
        from ...contracts import DeviceBatchState
        self._ipc.wait_ready()
        arrays = {name: self._ipc.read(name) for name in self._state_shapes}
        self._ipc.synchronize()
        self._last_state = DeviceBatchState(arrays, self.device, self.num_envs,
                                            self._identity(), 'owned_snapshot')
        return self._last_state

    def read_device_state(self, names):
        from ...contracts import DeviceBatchState
        self._require_live()
        if self._last_state is None:
            raise RuntimeError('MJWarp batch must be reset before state is read')
        requested = tuple(names)
        if not requested or len(requested) != len(set(requested)):
            raise ValueError('device state requires unique named fields')
        unknown = set(requested) - set(self._last_state.arrays)
        if unknown:
            raise KeyError(f'unsupported MJWarp state fields: {sorted(unknown)}')
        return DeviceBatchState({name: self._last_state.arrays[name].clone() for name in requested},
                                self.device, self.num_envs, self._last_state.identity, 'owned_snapshot')

    def reset_device(self, state, mask, *, selection=None):
        import torch
        from ...contracts import validate_device_reset_selection
        self._require_live()
        if selection is not None:
            validate_device_reset_selection(selection, mask=mask, num_envs=self.num_envs,
                                            device=self.device, require_data_pointer=True)
        if (not isinstance(mask, torch.Tensor) or str(mask.device) != self.device
                or mask.dtype != torch.bool or tuple(mask.shape) != (self.num_envs,)):
            raise ValueError('MJWarp reset mask must be CUDA bool with shape (B,)')
        if set(state) != {'qpos', 'qvel'}:
            raise ValueError('MJWarp reset requires named qpos and qvel')
        for name in ('qpos', 'qvel'):
            value = state[name]
            expected = (self.num_envs, *self._state_shapes[name])
            if (not isinstance(value, torch.Tensor) or str(value.device) != self.device
                    or value.dtype != torch.float32 or tuple(value.shape) != expected
                    or not bool(torch.isfinite(value).all())):
                raise ValueError(f'MJWarp reset {name} must be finite CUDA float32 with shape {expected}')
        if not bool(mask.any()):
            if self._last_state is None:
                raise ValueError('initial MJWarp reset must select at least one row')
            return self.read_device_state(tuple(self._state_shapes))
        if self._last_state is None and not bool(mask.all()):
            raise ValueError('initial MJWarp reset must select every row')
        try:
            for name in ('qpos', 'qvel'):
                value = state[name]
                self._ipc.write('reset_' + name, value.contiguous())
            self._ipc.write('reset_mask', mask.contiguous())
            self._ipc.record_written()
            self._worker.call('reset')
            self._revision += 1
            return self._read_publication()
        except BaseException:
            self._faulted = True
            raise

    def step_device(self, command):
        import torch
        from ....controllers.canonical.physical_commands import DeviceJointEffortCommand
        self._require_live()
        if self._last_state is None:
            raise RuntimeError('MJWarp batch must be reset before step')
        if (type(command) is not DeviceJointEffortCommand or command.boundary != self._identity()
                or command.binding_sha256 != self._binding_hash
                or command.writer_id != self._controller.writer_id
                or command.channel_keys != self._controller.channel_keys):
            raise ValueError('MJWarp effort command is stale or differs from its source binding')
        values = command.values
        if (not isinstance(values, torch.Tensor) or str(values.device) != self.device
                or values.dtype != torch.float32
                or tuple(values.shape) != (self.num_envs, len(self._binding.channels))
                or str(command.episode_ids.device) != self.device
                or command.episode_ids.dtype != torch.int64
                or str(command.episode_steps.device) != self.device
                or command.episode_steps.dtype != torch.int32
                or not bool(torch.isfinite(values).all())):
            raise ValueError('MJWarp effort command has an invalid device, shape, dtype or value')
        if self._device_limits is None:
            self._device_limits = (
                torch.tensor([channel.effort_range[0] for channel in self._binding.channels], device=values.device),
                torch.tensor([channel.effort_range[1] for channel in self._binding.channels], device=values.device))
        low, high = self._device_limits
        if bool(((values < low) | (values > high)).any()):
            raise ValueError('MJWarp effort command exceeds its admitted range')
        try:
            self._ipc.write('effort', values.contiguous())
            self._ipc.record_written()
            self._worker.call('step')
            self._native_steps += self._control_substeps
            self._revision += 1
            return self._read_publication()
        except BaseException:
            self._faulted = True
            raise

    def resource_summary(self):
        return {'num_envs': self.num_envs, 'provider': 'mujoco_warp',
                'dependency_profile': dict(self._profile),
                'device_transition': {'available': True, 'field_device': self.device,
                    'transport': 'cuda_ipc', 'state_readback_fields': list(self._state_shapes),
                    'state_shapes': self._state_shapes,
                    'body_names': self._body_names, 'frame_names': self._frame_names,
                    'pose_layout': 'world_body_xyz_wxyz_env_local'}}

    def close(self):
        if self._closed:
            return
        self._closed = True
        error = None
        if self._ipc is not None:
            try:
                self._ipc.release_imports()
            except BaseException as caught:
                error = caught
        if self._worker is not None:
            try:
                self._worker.close()
            except BaseException as caught:
                if error is None:
                    error = caught
                else:
                    error.add_note(f'worker close also failed: {caught!r}')
            if self._worker.closed:
                self._worker = None
        if self._ipc is not None and self._worker is None:
            try:
                self._ipc.close()
                self._ipc = None
            except BaseException as caught:
                if error is None:
                    error = caught
                else:
                    error.add_note(f'IPC close also failed: {caught!r}')
        self._last_state = None
        self._device_limits = None
        if error is not None:
            raise error
