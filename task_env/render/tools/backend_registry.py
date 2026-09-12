"""Lazy backend registry used by the common TaskEnv render tools."""

from __future__ import annotations

from ..base.backend import (
    LegacyReferenceRenderBackend,
    RenderBackend,
    RenderBackendDescriptor,
)
from ..base.contracts import RenderBackendName


def _backend_factories():
    """Import concrete backends only when the registry is queried."""

    from ..rasterizer.backend import RasterizerRenderBackend
    from ..raytracer.backend import RaytracerRenderBackend
    from ..flora.backend import FloraRenderBackend

    return {
        RenderBackendName.RAYTRACER.value: RaytracerRenderBackend,
        RenderBackendName.RASTERIZER.value: RasterizerRenderBackend,
        RenderBackendName.FLORA.value: FloraRenderBackend,
        "mujoco_reference": LegacyReferenceRenderBackend,
        "mujoco": LegacyReferenceRenderBackend,
        "external_mujoco": LegacyReferenceRenderBackend,
    }


def normalize_render_backend(value: str | RenderBackendName) -> str:
    """Normalize a TaskEnv backend name without loading native runtimes."""

    name = str(getattr(value, "value", value)).strip().lower()
    if name not in _backend_factories():
        expected = ", ".join(
            (
                RenderBackendName.RAYTRACER.value,
                RenderBackendName.RASTERIZER.value,
                RenderBackendName.FLORA.value,
            )
        )
        raise ValueError(
            f"unsupported task_env render backend {name!r}; expected one of: {expected}"
        )
    return name


def create_render_backend(value: str | RenderBackendName) -> RenderBackend:
    """Create a fresh backend instance."""

    name = normalize_render_backend(value)
    return _backend_factories()[name]()


def available_render_backends() -> tuple[RenderBackendDescriptor, ...]:
    """Return descriptors for the three supported TaskEnv backends."""

    factories = _backend_factories()
    return tuple(
        factories[name]().descriptor
        for name in (
            RenderBackendName.RAYTRACER.value,
            RenderBackendName.RASTERIZER.value,
            RenderBackendName.FLORA.value,
        )
    )


__all__ = [
    "normalize_render_backend",
    "create_render_backend",
    "available_render_backends",
]
