"""CUDA driver IPC mappings and event ordering for device-resident tensors.

The exporting worker retains allocation ownership. Imported mappings are closed
before the worker is asked to release its allocations. Tensor results are
owned GPU copies and never alias a mapping after it is closed.
"""
from __future__ import annotations

import base64
import ctypes


def _check(result):
    if int(result[0]) != 0:
        raise RuntimeError(f'CUDA driver IPC operation failed: {result[0]}')
    return result[1] if len(result) > 1 else None


def _decode_handle(kind, encoded):
    value = base64.b64decode(encoded, validate=True)
    if len(value) != 64:
        raise ValueError('CUDA IPC handles must have exactly 64 bytes')
    handle = kind()
    ctypes.memmove(handle.getPtr(), value, len(value))
    return handle


class CudaIpcConnection:
    """Import one worker's buffers and synchronize copies on a Torch stream."""

    def __init__(self, description):
        import torch
        from cuda.bindings import driver as cu

        torch.cuda.init()
        self._torch, self._cu = torch, cu
        self._device = torch.device(description['device'])
        if self._device.type != 'cuda' or self._device.index is None:
            raise ValueError('IPC requires an explicitly indexed CUDA device')
        if self._device.index != torch.cuda.current_device():
            raise ValueError('IPC device must be the current CUDA device')
        # PyTorch lazily establishes the primary context when a stream is
        # requested; driver IPC opens require that context to be current.
        torch.cuda.current_stream(self._device)
        self._buffers = {}
        self._ready = self._written = None
        try:
            for name, spec in description['buffers'].items():
                pointer = _check(cu.cuIpcOpenMemHandle(
                    _decode_handle(cu.CUipcMemHandle, spec['handle']), 1))
                self._buffers[name] = (pointer, tuple(spec['shape']), spec['dtype'])
            self._ready = _check(cu.cuIpcOpenEventHandle(
                _decode_handle(cu.CUipcEventHandle, description['ready'])))
            self._written = _check(cu.cuEventCreate(6))
        except BaseException:
            self.close()
            raise

    @property
    def written_handle(self):
        handle = _check(self._cu.cuIpcGetEventHandle(self._written))
        return base64.b64encode(ctypes.string_at(handle.getPtr(), 64)).decode('ascii')

    def _stream(self):
        return self._cu.CUstream(self._torch.cuda.current_stream(self._device).cuda_stream)

    def wait_ready(self):
        _check(self._cu.cuStreamWaitEvent(self._stream(), self._ready, 0))

    def record_written(self):
        _check(self._cu.cuEventRecord(self._written, self._stream()))

    def write(self, name, value):
        pointer, shape, dtype = self._buffers[name]
        expected = {'float32': self._torch.float32, 'bool': self._torch.bool}[dtype]
        if (not isinstance(value, self._torch.Tensor) or value.device != self._device
                or tuple(value.shape) != shape or value.dtype != expected or not value.is_contiguous()):
            raise ValueError(f'IPC buffer {name!r} requires a contiguous CUDA {dtype} tensor of shape {shape}')
        _check(self._cu.cuMemcpyDtoDAsync(pointer, value.data_ptr(), value.numel() * value.element_size(),
                                          self._stream()))

    def read(self, name):
        pointer, shape, dtype = self._buffers[name]
        tensor_dtype = {'float32': self._torch.float32, 'bool': self._torch.bool}[dtype]
        result = self._torch.empty(shape, dtype=tensor_dtype, device=self._device)
        _check(self._cu.cuMemcpyDtoDAsync(result.data_ptr(), pointer,
                                          result.numel() * result.element_size(), self._stream()))
        return result

    def synchronize(self):
        self._torch.cuda.current_stream(self._device).synchronize()

    def release_imports(self):
        """Unmap worker-owned resources while leaving our exported event alive."""
        if self._buffers or self._ready is not None:
            self.synchronize()
        for pointer, _, _ in self._buffers.values():
            _check(self._cu.cuIpcCloseMemHandle(pointer))
        self._buffers.clear()
        if self._ready is not None:
            _check(self._cu.cuEventDestroy(self._ready))
            self._ready = None

    def close(self):
        """Close after the worker has released its import of the written event."""
        self.release_imports()
        if self._written is not None:
            _check(self._cu.cuEventDestroy(self._written))
            self._written = None
