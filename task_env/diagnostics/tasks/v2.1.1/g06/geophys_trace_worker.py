#!/home/lly/miniconda3/envs/geochora/bin/python
"""Diagnostic interpreter shim; worker protocol and product entry stay unchanged."""
import importlib.util
import os
from pathlib import Path

protocol_fd = os.dup(1)
os.dup2(2, 1)
root = Path(__file__).resolve().parents[5]
spec = importlib.util.spec_from_file_location(
    'g06b_contact_trace', root / 'GeoPhys/test/development/rigid/g06b_contact_trace.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

from task_env.runtime.providers.geophys.device_batch import GeoPhysNativeBatch
from task_env.runtime.providers.geophys.rigid_batch import GeoPhysRigidBatchRuntime
os.dup2(protocol_fd, 1)
os.close(protocol_fd)

original_init = GeoPhysNativeBatch.__init__
original_close = GeoPhysNativeBatch.close


def construct(self, request):
    original_init(self, request)
    try:
        self._g06b_trace = module.ContactTrace(self, os.environ['G06B_TRACE_OUTPUT'])
        self._runtime._g06b_trace = self._g06b_trace
    except BaseException:
        original_close(self)
        raise


def step_substeps(self, substeps=None):
    count = self.control_substeps if substeps is None else int(substeps)
    if count < 1:
        raise ValueError('substeps must be positive')
    for _ in range(count):
        self.solver.step()
        self._g06b_trace.state_after_substep()


def close(self):
    trace = getattr(self, '_g06b_trace', None)
    if trace is not None:
        trace.save()
        self._g06b_trace = None
    original_close(self)


GeoPhysNativeBatch.__init__ = construct
GeoPhysNativeBatch.close = close
GeoPhysRigidBatchRuntime.step_substeps = step_substeps

from task_env.runtime.transport.worker import main
main()
