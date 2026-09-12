"""Batch physics runtime selection.

The selector is intentionally small: task semantics and vector lifecycle do
not inspect the concrete runtime.  ``merged_scene`` remains the compatibility
path; the static-template implementation is enabled only after its explicit
capability gate passes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..environment import ResolvedEnvConfig


@dataclass(frozen=True, slots=True)
class _ResolvedRuntimeRoute:
    """Internal normalized provider/layout/profile facts for one request."""

    provider: str
    layout: str
    profile: str | None


def _resolve_runtime_route(config: ResolvedEnvConfig) -> _ResolvedRuntimeRoute:
    """Separate provider family, materialization layout, and profile facts.

    ``batch_physics_layout`` remains the compatibility vocabulary accepted by
    existing YAML.  This value object prevents new provider branches from
    spreading that legacy name through construction code.
    """

    layout = str(config.runtime.batch_physics_layout).strip().lower()
    if layout == "merged_scene":
        return _ResolvedRuntimeRoute(
            provider="merged_scene",
            layout="merged_scene",
            profile=None,
        )
    if layout == "static_template":
        return _ResolvedRuntimeRoute(
            provider="static",
            layout="homogeneous_static",
            profile=str(config.runtime.static_template.profile),
        )
    raise ValueError(f"unsupported batch_physics_layout: {layout!r}")


def _build_merged_scene_runtime(**kwargs: Any) -> Any:
    from .providers.merged_scene import SceneBatchRuntime

    return SceneBatchRuntime.from_compiled_scene(**kwargs)


def _build_static_runtime(**kwargs: Any) -> Any:
    from .providers.static.runtime import StaticTemplateBatchRuntime

    return StaticTemplateBatchRuntime.from_compiled_scene(**kwargs)


_RUNTIME_BUILDERS: dict[str, Callable[..., Any]] = {
    "merged_scene": _build_merged_scene_runtime,
    "static": _build_static_runtime,
}


def make_batch_runtime(
    *,
    compiled_scene: object,
    resolved_config: ResolvedEnvConfig,
    num_envs: int,
    backend: str,
) -> Any:
    """Construct the configured homogeneous batch physics runtime.

    ``execution=local|remote`` is deliberately absent from this function; it
    is an IPC concern owned by ``vectorization.parallel``.  An explicitly
    requested but unavailable static layout must fail instead of silently
    changing the experiment back to ``merged_scene``.
    """

    route = _resolve_runtime_route(resolved_config)
    builder = _RUNTIME_BUILDERS.get(route.provider)
    if builder is None:  # pragma: no cover - defensive future-provider guard
        raise ValueError(f"unsupported runtime provider: {route.provider!r}")
    return builder(
        compiled_scene=compiled_scene,
        config=resolved_config,
        num_envs=int(num_envs),
        backend=str(backend),
    )


__all__ = ["make_batch_runtime"]
