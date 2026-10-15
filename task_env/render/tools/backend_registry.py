"""Lazy backend registry used by the common TaskEnv render tools."""

from __future__ import annotations

from importlib import import_module

from ..base.backend import (
    RenderBackend,
    RenderBackendDescriptor,
    _BACKEND_REGISTRATIONS,
    _backend_registration,
)
from ..base.contracts import RenderBackendName


def normalize_render_backend(value: str | RenderBackendName) -> str:
    """Normalize a TaskEnv backend name without loading native runtimes."""

    name = str(getattr(value, "value", value)).strip().lower()
    try:
        _backend_registration(name)
    except KeyError:
        expected = ", ".join(
            registration.descriptor.name
            for registration in _BACKEND_REGISTRATIONS
            if registration.listed
        )
        raise ValueError(
            f"unsupported task_env render backend {name!r}; expected one of: {expected}"
        ) from None
    return name


def create_render_backend(value: str | RenderBackendName) -> RenderBackend:
    """Create a fresh backend instance."""

    name = normalize_render_backend(value)
    implementation = _backend_registration(name).descriptor.implementation
    module_name, _, class_name = implementation.rpartition(".")
    return getattr(import_module(module_name), class_name)()


def available_render_backends() -> tuple[RenderBackendDescriptor, ...]:
    """Return descriptors for the three supported TaskEnv backends."""

    return tuple(
        registration.descriptor
        for registration in _BACKEND_REGISTRATIONS
        if registration.listed
    )


__all__ = [
    "normalize_render_backend",
    "create_render_backend",
    "available_render_backends",
]
