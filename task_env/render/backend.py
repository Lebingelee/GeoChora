"""Compatibility exports for the split render base and tool layers."""

from .base.backend import *
from .base.backend import __all__ as _base_all
from .tools.backend_registry import (
    available_render_backends,
    create_render_backend,
    normalize_render_backend,
)

__all__ = [
    *_base_all,
    "available_render_backends",
    "create_render_backend",
    "normalize_render_backend",
]
