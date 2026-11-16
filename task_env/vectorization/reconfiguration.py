"""Declarative whole-batch device reconfiguration.

This module owns only pure preparation for the public
``env.reset(options={'execution': target_execution})`` request.  It never
constructs, closes or mutates a native provider.  The homogeneous lifecycle
performs the destructive commit after these checks have accepted the target.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any


# Only the documented public option is accepted.  An execution target uses the
# existing selected execution fields rather than a provider alias.
_ALLOWED_OPTION_KEYS = frozenset({"execution"})
_ALLOWED_EXECUTION_FIELDS = frozenset(
    {
        "physics_provider",
        "physics_backend",
        "physics_device",
        "source_delivery_manifest",
        "render_default",
        "host",
        "engine",
        "solver_family",
        "solver_algorithm",
        "coupler",
        "batch_layout",
        "deployment",
        "interpreter",
        "native_dt",
        "reset_profile",
        "geophys_contact_mode",
    }
)

# Provider-router fields must be re-derived from the target provider's legal
# defaults.  Reusing the old provider's private route would either be rejected
# by the shared resolver or silently describe the wrong native owner.
_PROVIDER_PRIVATE_ROUTE_FIELDS = frozenset(
    {
        "host",
        "engine",
        "solver_family",
        "solver_algorithm",
        "coupler",
        "batch_layout",
        "deployment",
        "native_dt",
        "interpreter",
        "source_delivery_manifest",
        "geophys_contact_mode",
    }
)

# The G06c representative edge is Isaac <-> MJWarp with CUDA B3.  GeoPhys
# cross-backend switching has no admitted evidence and is rejected explicitly.
_ADMITTED_PROVIDER_EDGES = frozenset(
    {frozenset(("isaacsim", "mujoco_warp"))}
)
_ADMITTED_PROVIDERS = frozenset(("isaacsim", "mujoco_warp", "geophys"))


@dataclass(frozen=True)
class DeviceBatchBuildInput:
    """Declarative input retained on a device adapter for whole-batch rebuilds.

    It deliberately stores configuration and identity integers, never a live
    provider, runtime or renderer object.
    """

    uid: str
    num_env: int
    backend: str
    env_config: Any
    worker_directory: str | None
    render_mode: str | None
    resolved_config: Any
    provider: str
    generation: int
    render_signature: tuple

    def __post_init__(self) -> None:
        if type(self.uid) is not str or not self.uid:
            raise ValueError("device build input requires a task uid")
        if type(self.num_env) is not int or self.num_env < 1:
            raise ValueError("device build input requires a positive batch size")
        if type(self.generation) is not int or self.generation < 0:
            raise ValueError("device build input requires a nonnegative generation")
        if self.provider not in _ADMITTED_PROVIDERS:
            raise ValueError(f"device build input has an unadmitted provider: {self.provider!r}")


@dataclass(frozen=True)
class PreparedReconfiguration:
    """A preflighted target that can safely replace the old batch."""

    target_config: Any
    target_provider: str
    generation: int
    execution: Mapping[str, Any]
    target_request: Mapping[str, Any] | None = None


def _render_signature(render_config: Any) -> tuple:
    """Freeze renderer implementation, camera layout and resolution."""

    return tuple(
        sorted(
            (name, repr(value))
            for name, value in asdict(render_config).items()
        )
    )


def render_config_signature(render_config: Any) -> tuple:
    """Public helper used when the factory records its build input."""

    return _render_signature(render_config)


def parse_switch_options(options: Mapping[str, Any] | None, *, num_envs: int) -> dict[str, Any] | None:
    """Parse ``options={"execution": ...}`` without touching the old batch.

    Returns ``None`` when the request is not a reconfiguration.  Unknown
    options, malformed execution targets and empty targets are rejected before
    any provider teardown.
    """

    if options is None:
        return None
    if not isinstance(options, Mapping):
        raise TypeError("device reset options must be a mapping")
    unknown = set(options) - _ALLOWED_OPTION_KEYS
    if unknown:
        raise ValueError(
            "device reset options support only 'execution': "
            + ", ".join(sorted(str(name) for name in unknown))
        )
    if "execution" not in options:
        return None
    execution = options["execution"]
    if not isinstance(execution, Mapping):
        raise TypeError("options['execution'] must be a mapping")
    if set(execution) - _ALLOWED_EXECUTION_FIELDS:
        raise ValueError(
            "options['execution'] contains unsupported fields: "
            + ", ".join(sorted(str(name) for name in set(execution) - _ALLOWED_EXECUTION_FIELDS))
        )
    if not execution:
        return None
    if int(num_envs) < 1:
        raise ValueError("device reset requires a positive batch size")
    return dict(execution)


def _request_mapping(build_input: DeviceBatchBuildInput) -> dict[str, Any]:
    source = build_input.env_config
    if source is None:
        return {}
    if isinstance(source, Mapping):
        return copy.deepcopy(dict(source))
    if isinstance(source, (str, Path)):
        from ..environment.configuration import load_yaml_mapping

        return dict(load_yaml_mapping(source))
    raise ValueError(
        "whole-batch execution switching requires the original mapping or YAML "
        "request; a pre-resolved selected configuration cannot be overlaid"
    )


def _assert_fixed_contract(original: Any, target: Any) -> None:
    """Reject target changes outside the execution route."""

    if target.task_uid != original.task_uid:
        raise ValueError("whole-batch execution switch cannot change the task")
    for name in (
        "asset",
        "scene",
        "agents",
        "objects",
        "robot",
        "control",
        "action",
        "observation",
        "render",
        "task",
        "episode",
    ):
        if getattr(target.environment, name) != getattr(original.environment, name):
            raise ValueError(
                f"whole-batch execution switch cannot change environment.{name}"
            )
    # Execution backend may change, but the task-owned timebase and physics
    # options must remain the same physics contract.
    original_runtime = original.environment.runtime
    target_runtime = replace(
        target.environment.runtime, backend=original_runtime.backend
    )
    if target_runtime != original_runtime:
        raise ValueError(
            "whole-batch execution switch cannot change the task runtime configuration"
        )
    if target.robot_uid != original.robot_uid:
        raise ValueError("whole-batch execution switch cannot change the Robot")
    if target.controller_parameters_json != original.controller_parameters_json:
        raise ValueError(
            "whole-batch execution switch cannot change Controller parameters"
        )
    if target.controller_profile != original.controller_profile:
        raise ValueError(
            "whole-batch execution switch cannot change the Controller profile"
        )
    if target.task_parameters != original.task_parameters:
        raise ValueError("whole-batch execution switch cannot change task parameters")
    if target.task_configuration_json != original.task_configuration_json:
        raise ValueError(
            "whole-batch execution switch cannot change task configuration"
        )
    if target.gravity_compensation != original.gravity_compensation:
        raise ValueError(
            "whole-batch execution switch cannot change gravity compensation"
        )
    if target.native_drive != original.native_drive:
        raise ValueError("whole-batch execution switch cannot change the Robot drive")
    if target.reset_profile != original.reset_profile:
        raise ValueError("whole-batch execution switch cannot change the reset profile")
    original_selection = original.execution_spec_v2
    target_selection = target.execution_spec_v2
    if target_selection.render_default != original_selection.render_default:
        raise ValueError("whole-batch execution switch cannot change the renderer")
    if target_selection.batch_layout != original_selection.batch_layout:
        raise ValueError("whole-batch execution switch cannot change the batch layout")


def prepare_reconfiguration(
    build_input: DeviceBatchBuildInput,
    execution: Mapping[str, Any],
    *,
    generation: int,
    environment_type: Any | None = None,
) -> PreparedReconfiguration:
    """Resolve and validate one target entirely before destroying the old batch."""

    if not isinstance(build_input, DeviceBatchBuildInput):
        raise TypeError("reconfiguration requires a DeviceBatchBuildInput")
    if not isinstance(execution, Mapping):
        raise TypeError("execution target must be a mapping")
    if set(execution) - _ALLOWED_EXECUTION_FIELDS:
        raise ValueError("execution target contains unsupported fields")
    if type(generation) is not int or generation <= int(build_input.generation):
        raise ValueError("reconfiguration generation must advance monotonically")

    from ..environment.configuration import resolve_task_env_config
    from ..registry import ENV_REGISTRY

    environment_type = ENV_REGISTRY.get(build_input.uid) if environment_type is None else environment_type
    request = _request_mapping(build_input)
    old_execution = request.get("execution", {})
    if old_execution is None:
        old_execution = {}
    if not isinstance(old_execution, Mapping):
        raise TypeError("original env_config.execution must be a mapping")
    old_execution = dict(old_execution)
    unknown = set(old_execution) - _ALLOWED_EXECUTION_FIELDS
    if unknown:
        raise ValueError(
            "original env_config.execution contains unsupported fields: "
            + ", ".join(sorted(str(name) for name in unknown))
        )

    target_provider = str(execution.get("physics_provider", build_input.provider))
    if target_provider not in _ADMITTED_PROVIDERS:
        raise ValueError(f"unsupported target physics provider: {target_provider!r}")
    provider_changed = target_provider != str(build_input.provider)
    if provider_changed:
        if frozenset((str(build_input.provider), target_provider)) not in _ADMITTED_PROVIDER_EDGES:
            raise ValueError(
                "whole-batch provider switch is not admitted for "
                f"{build_input.provider!r} -> {target_provider!r}; the validated "
                "G06c edge is isaacsim <-> mujoco_warp"
            )
        for name in _PROVIDER_PRIVATE_ROUTE_FIELDS:
            old_execution.pop(name, None)
        runtime = request.get("runtime")
        if isinstance(runtime, Mapping):
            runtime = dict(runtime)
            if target_provider != "geophys":
                runtime.pop("body_contact_solver_iterations", None)
            if runtime:
                request["runtime"] = runtime
            else:
                request.pop("runtime", None)

    merged = dict(old_execution)
    merged.update(dict(execution))
    merged["physics_provider"] = target_provider
    request["execution"] = merged

    target_config = resolve_task_env_config(
        environment_type, request, execution_scope="device_batch"
    )
    _assert_fixed_contract(build_input.resolved_config, target_config)
    target_provider = str(target_config.physics_provider)
    return PreparedReconfiguration(
        target_config=target_config,
        target_provider=target_provider,
        generation=int(generation),
        execution=dict(merged),
        target_request=request,
    )


__all__ = [
    "DeviceBatchBuildInput",
    "PreparedReconfiguration",
    "parse_switch_options",
    "prepare_reconfiguration",
    "render_config_signature",
]
