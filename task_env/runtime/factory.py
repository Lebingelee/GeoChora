"""Construct the supported merged-scene batch physics runtime."""

from __future__ import annotations

from typing import Any

from ..environment import ResolvedEnvConfig


_DEVICE_PROVIDER_TYPES = {
    'mujoco_warp': ('task_env.runtime.providers.mujoco_warp.batch',
                    'MuJoCoWarpBatchSession', 'MuJoCoWarpNativeBatch'),
    'geophys': ('task_env.runtime.providers.geophys.device_batch',
                'GeoPhysDeviceBatchSession', 'GeoPhysNativeBatch'),
    'isaacsim': ('task_env.runtime.providers.isaac.batch',
                 'IsaacDeviceBatchSession', 'IsaacNativeBatch'),
}


def load_device_provider(provider: str, *, worker: bool = False):
    """Resolve one admitted provider implementation without importing its SDK."""
    from importlib import import_module

    try:
        module_name, session_name, worker_name = _DEVICE_PROVIDER_TYPES[provider]
    except KeyError as error:
        raise ValueError(f'no device batch implementation for provider {provider!r}') from error
    return getattr(import_module(module_name), worker_name if worker else session_name)


def make_batch_runtime(
    *,
    compiled_scene: object,
    resolved_config: ResolvedEnvConfig,
    num_envs: int,
    backend: str,
) -> Any:
    """Construct the configured homogeneous batch physics runtime.

    ``execution=local|remote`` is an IPC concern owned by
    ``vectorization.parallel``. A retired layout fails before provider import;
    it is never redirected to ``merged_scene``.
    """

    layout = str(resolved_config.runtime.batch_physics_layout).strip().lower()
    if layout == "static_template":
        raise ValueError(
            "batch_physics_layout='static_template' is retired; use 'merged_scene'. "
            "No runtime substitution is performed."
        )
    if layout != "merged_scene":
        raise ValueError(f"unsupported batch_physics_layout: {layout!r}")

    from .providers.merged_scene import SceneBatchRuntime

    return SceneBatchRuntime.from_compiled_scene(
        compiled_scene=compiled_scene,
        config=resolved_config,
        num_envs=int(num_envs),
        backend=str(backend),
    )


__all__ = ["make_batch_runtime"]
