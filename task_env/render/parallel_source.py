"""Compatibility exports for the parallel render source provider."""

from .providers.parallel_source import BatchParallelRenderSource
from .providers.parallel_source import _replicate_render_scene_for_parallel
from .providers.parallel_source import _tint_hard_render_scene

__all__ = ["BatchParallelRenderSource"]
