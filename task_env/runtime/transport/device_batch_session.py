"""Shared source-bound CUDA IPC session lifecycle for physical batches."""


def _coupled_effort_groups(channels):
    """Compile source transmission groups once, retaining canonical signs."""
    groups = {}
    for index, channel in enumerate(channels):
        groups.setdefault((channel.entity_id, channel.transmission_id), []).append(
            (index, channel.sign, channel.transmission_coefficient))
    return tuple(tuple(group) for group in groups.values() if len(group) > 1)


def _validate_coupled_efforts(values, groups):
    """Reject device efforts that cannot come from a single tendon input."""
    import torch

    invalid = torch.zeros((), dtype=torch.bool, device=values.device)
    for group in groups:
        first_index, first_sign, first_coefficient = group[0]
        reference = values[:, first_index] * first_sign / first_coefficient
        for index, sign, coefficient in group[1:]:
            native = values[:, index] * sign / coefficient
            invalid = invalid | (~torch.isclose(native, reference, rtol=2e-6, atol=2e-6)).any()
    if bool(invalid):
        raise ValueError('device effort is not representable by the declared coupled transmission')


class DevicePhysicalBatchSession:
    """Own identity, IPC synchronization, fault latching and batch operations."""

    def _require_live(self):
        if self._closed:
            raise RuntimeError(f'{self._provider_label} batch session is closed')
        if self._faulted:
            raise RuntimeError(f'{self._provider_label} batch session is faulted')

    def _identity(self):
        from ..contracts import DeviceStateIdentity
        return DeviceStateIdentity(*self._source_identity, self._materialization_id, self._generation,
            self._revision, self._native_steps, self._native_steps * self._physics_dt, self._control_dt)

    def device_state_identity(self):
        """Return the live device boundary without reading any physics values."""
        self._require_live()
        if self._last_state is None:
            raise RuntimeError(f'{self._provider_label} batch must be reset before state is read')
        return self._identity()

    def _read_publication(self):
        from ..contracts import DeviceBatchState
        self._ipc.wait_ready()
        arrays = {name: self._ipc.read(name) for name in self._state_shapes}
        self._ipc.synchronize()
        self._last_state = DeviceBatchState(arrays, self.device, self.num_envs,
                                            self._identity(), 'owned_snapshot')
        return self._last_state

    def read_device_state(self, names):
        from ..contracts import DeviceBatchState
        self._require_live()
        if self._last_state is None:
            raise RuntimeError(f'{self._provider_label} batch must be reset before state is read')
        requested = tuple(names)
        if not requested or len(requested) != len(set(requested)):
            raise ValueError('device state requires unique named fields')
        unknown = set(requested) - set(self._last_state.arrays)
        if unknown:
            raise KeyError(f'unsupported {self._provider_label} state fields: {sorted(unknown)}')
        return DeviceBatchState({name: self._last_state.arrays[name].clone() for name in requested},
                                self.device, self.num_envs, self._last_state.identity, 'owned_snapshot')

    def reset_device(self, state, mask, *, selection=None):
        import torch
        from ..contracts import validate_device_reset_selection
        self._require_live()
        if selection is not None:
            validate_device_reset_selection(selection, mask=mask, num_envs=self.num_envs,
                                            device=self.device, require_data_pointer=True)
        if (not isinstance(mask, torch.Tensor) or str(mask.device) != self.device
                or mask.dtype != torch.bool or tuple(mask.shape) != (self.num_envs,)):
            raise ValueError(f'{self._provider_label} reset mask must be CUDA bool with shape (B,)')
        if set(state) != {'qpos', 'qvel'}:
            raise ValueError(f'{self._provider_label} reset requires named qpos and qvel')
        for name in ('qpos', 'qvel'):
            value = state[name]
            expected = (self.num_envs, *self._state_shapes[name])
            if (not isinstance(value, torch.Tensor) or str(value.device) != self.device
                    or value.dtype != torch.float32 or tuple(value.shape) != expected
                    or not bool(torch.isfinite(value).all())):
                raise ValueError(f'{self._provider_label} reset {name} must be finite CUDA float32 with shape {expected}')
        if not bool(mask.any()):
            if self._last_state is None:
                raise ValueError(f'initial {self._provider_label} reset must select at least one row')
            return self.read_device_state(tuple(self._state_shapes))
        if self._last_state is None and not bool(mask.all()):
            raise ValueError(f'initial {self._provider_label} reset must select every row')
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
        from ...controllers.canonical.physical_commands import DeviceJointEffortCommand
        self._require_live()
        if self._last_state is None:
            raise RuntimeError(f'{self._provider_label} batch must be reset before step')
        if (type(command) is not DeviceJointEffortCommand or command.boundary != self._identity()
                or command.binding_sha256 != self._binding_hash
                or command.writer_id != self._controller.writer_id
                or command.channel_keys != self._controller.channel_keys):
            raise ValueError(f'{self._provider_label} effort command is stale or differs from its source binding')
        values = command.values
        if (not isinstance(values, torch.Tensor) or str(values.device) != self.device
                or values.dtype != torch.float32
                or tuple(values.shape) != (self.num_envs, len(self._binding.channels))
                or str(command.episode_ids.device) != self.device
                or command.episode_ids.dtype != torch.int64
                or str(command.episode_steps.device) != self.device
                or command.episode_steps.dtype != torch.int32
                or not bool(torch.isfinite(values).all())):
            raise ValueError(f'{self._provider_label} effort command has an invalid device, shape, dtype or value')
        if self._device_limits is None:
            self._device_limits = (
                torch.tensor([channel.effort_range[0] for channel in self._binding.channels], device=values.device),
                torch.tensor([channel.effort_range[1] for channel in self._binding.channels], device=values.device))
        low, high = self._device_limits
        if bool(((values < low) | (values > high)).any()):
            raise ValueError(f'{self._provider_label} effort command exceeds its admitted range')
        groups = getattr(self, '_device_coupled_effort_groups', None)
        if groups is None:
            groups = self._device_coupled_effort_groups = _coupled_effort_groups(self._binding.channels)
        if groups:
            _validate_coupled_efforts(values, groups)
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

    def close(self):
        if self._closed and self._worker is None and self._ipc is None:
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
