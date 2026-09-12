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
    "StaticTemplateBatchRuntime": (
        "task_env.runtime.providers.static.runtime",
        "StaticTemplateBatchRuntime",
    ),
    "StaticTemplateDescriptor": (
        "task_env.runtime.providers.static.runtime",
        "StaticTemplateDescriptor",
    ),
    "STATIC_TEMPLATE_CAPABILITIES": (
        "task_env.runtime.providers.static.profile",
        "STATIC_TEMPLATE_CAPABILITIES",
    ),
    "StaticTemplateCapability": (
        "task_env.runtime.providers.static.profile",
        "StaticTemplateCapability",
    ),
    "get_static_template_capability": (
        "task_env.runtime.providers.static.profile",
        "get_static_template_capability",
    ),
    "resolve_static_template_profile": (
        "task_env.runtime.providers.static.profile",
        "resolve_static_template_profile",
    ),
    "static_template_compatibility_issues": (
        "task_env.runtime.providers.static.profile",
        "static_template_compatibility_issues",
    ),
    "LocalPairKey": (
        "task_env.runtime.providers.static.workspace",
        "LocalPairKey",
    ),
    "StaticTemplateContactWorkspace": (
        "task_env.runtime.providers.static.workspace",
        "StaticTemplateContactWorkspace",
    ),
    "StaticTemplateModel": (
        "task_env.runtime.providers.static.model",
        "StaticTemplateModel",
    ),
    "StaticTemplateExecutionPlan": (
        "task_env.runtime.providers.static.execution",
        "StaticTemplateExecutionPlan",
    ),
    "StaticTemplateRigidSolverReference": (
        "task_env.runtime.providers.static.reference",
        "StaticTemplateRigidSolverReference",
    ),
    "StaticTemplateFusedArticulated": (
        "task_env.runtime.providers.static.fused",
        "StaticTemplateFusedArticulated",
    ),
    "StaticTemplateRigidBatch": (
        "task_env.runtime.static_template_rigid_batch",
        "StaticTemplateRigidBatch",
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
