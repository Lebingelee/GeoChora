"""Stable TaskEnv runtime contracts and composition entry points.

Concrete providers live under ``task_env.runtime.providers`` and are loaded
only after the factory selects a route.  This package root therefore does not
initialize Taichi, Triton, Torch CUDA state, or provider workspaces during a
plain ``import task_env``.
"""

from importlib import import_module

from .boundary import RuntimeBoundary
from .admission import (
    RuntimePortAdmission,
    admit_runtime_port,
    resolve_device_transfer_mode,
)
from .bootstrap import TaskRuntimeBootstrap, bootstrap_task_runtime
from .contracts import (
    BatchDiagnostics,
    BatchResetResult,
    BatchRuntimeProtocol,
    BatchState,
    BatchStepResult,
    DeviceBatchRuntimeProtocol,
    DeviceBatchResetResult,
    DeviceBatchState,
    DeviceBatchTransition,
    DeviceResetSelection,
    WorldRandomizationBatch,
    WorldRandomizationRuntimeProtocol,
    build_world_randomization_batch,
    validate_device_reset_selection,
)
from .device_plan import (
    DEVICE_FIELD_PLAN_VERSION,
    DeviceFieldPlan,
    DeviceFieldSpec,
    build_device_field_plan,
)
from .factory import make_batch_runtime
from .state import (
    EpisodePhysicsState,
    PhysicsStateSnapshot,
    RuntimeSnapshot,
    SnapshotRequest,
)


# These names were exposed by the pre-Phase-7 root.  They remain available for
# in-repository migration callers, but loading one explicitly imports only its
# owner; they are not stable package-root API and are absent from __all__.
_COMPAT_EXPORTS = {
    "GeoPhysRuntimeBoundary": ("task_env.runtime.boundary", "GeoPhysRuntimeBoundary"),
    "SceneBatchRuntime": (
        "task_env.runtime.providers.merged_scene",
        "SceneBatchRuntime",
    ),
}


def __getattr__(name: str):
    target = _COMPAT_EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value


__all__ = [
    "BatchDiagnostics",
    "BatchResetResult",
    "BatchRuntimeProtocol",
    "BatchState",
    "BatchStepResult",
    "DeviceBatchRuntimeProtocol",
    "DeviceBatchResetResult",
    "DeviceBatchState",
    "DeviceBatchTransition",
    "DeviceResetSelection",
    "WorldRandomizationBatch",
    "WorldRandomizationRuntimeProtocol",
    "build_world_randomization_batch",
    "validate_device_reset_selection",
    "DEVICE_FIELD_PLAN_VERSION",
    "DeviceFieldPlan",
    "DeviceFieldSpec",
    "RuntimePortAdmission",
    "admit_runtime_port",
    "build_device_field_plan",
    "resolve_device_transfer_mode",
    "EpisodePhysicsState",
    "PhysicsStateSnapshot",
    "RuntimeBoundary",
    "RuntimeSnapshot",
    "SnapshotRequest",
    "make_batch_runtime",
    "TaskRuntimeBootstrap",
    "bootstrap_task_runtime",
]
