"""TaskEnv render contracts with lazy backend implementations.

Importing a render mode or a physics environment must not import Taichi or
any concrete renderer.  Backend modules remain available from their explicit
owner paths and are loaded when the caller requests that capability.
"""

from importlib import import_module

from .base.backend import (
    LegacyReferenceRenderBackend,
    RenderBackend,
    RenderBackendDescriptor,
    SceneSourceBackend,
)
from .base.contracts import (
    RenderBackendBuildError,
    RenderBackendCapabilities,
    RenderBackendName,
    RenderMode,
    RenderUnavailableError,
    UiRenderProvider,
    normalize_render_mode,
)


_LAZY_EXPORTS = {
    "available_render_backends": ("task_env.render.tools.backend_registry", "available_render_backends"),
    "create_render_backend": ("task_env.render.tools.backend_registry", "create_render_backend"),
    "normalize_render_backend": ("task_env.render.tools.backend_registry", "normalize_render_backend"),
    "RasterizerRenderBackend": ("task_env.render.rasterizer", "RasterizerRenderBackend"),
    "RaytracerRenderBackend": ("task_env.render.raytracer", "RaytracerRenderBackend"),
    "FloraRenderBackend": ("task_env.render.flora", "FloraRenderBackend"),
    "RenderBuildRequest": ("task_env.render.tools.processing", "RenderBuildRequest"),
    "RenderProcessor": ("task_env.render.tools.processing", "RenderProcessor"),
    "build_task_visualizer": ("task_env.render.tools.processing", "build_task_visualizer"),
    "TaskEnvRenderProvider": ("task_env.render.providers.single", "TaskEnvRenderProvider"),
    "ParallelRenderLayout": ("task_env.render.providers.parallel", "ParallelRenderLayout"),
    "ParallelRenderProvider": ("task_env.render.providers.parallel", "ParallelRenderProvider"),
    "ParallelRenderSourceProtocol": ("task_env.render.providers.parallel", "ParallelRenderSourceProtocol"),
    "BatchParallelRenderSource": ("task_env.render.providers.parallel_source", "BatchParallelRenderSource"),
    "TrainingRenderController": ("task_env.render.training.controller", "TrainingRenderController"),
    "TrainingRenderEvents": ("task_env.render.training.controller", "TrainingRenderEvents"),
    "TrainingRenderKeyMap": ("task_env.render.training.controller", "TrainingRenderKeyMap"),
    "TrainingRenderSettings": ("task_env.render.training.controller", "TrainingRenderSettings"),
    "TrainingRenderVecAdapter": ("task_env.render.training.controller", "TrainingRenderVecAdapter"),
    "resolve_training_render_settings": ("task_env.render.training.controller", "resolve_training_render_settings"),
}


def __getattr__(name: str):
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value


__all__ = [
    "RenderMode",
    "RenderBackendName",
    "RenderBackendCapabilities",
    "RenderBackendBuildError",
    "RenderUnavailableError",
    "UiRenderProvider",
    "normalize_render_mode",
    "RenderBackend",
    "RenderBackendDescriptor",
    "LegacyReferenceRenderBackend",
    "SceneSourceBackend",
    "available_render_backends",
    "create_render_backend",
    "normalize_render_backend",
    "RasterizerRenderBackend",
    "RaytracerRenderBackend",
    "FloraRenderBackend",
    "RenderBuildRequest",
    "RenderProcessor",
    "build_task_visualizer",
    "TaskEnvRenderProvider",
    "ParallelRenderLayout",
    "ParallelRenderProvider",
    "ParallelRenderSourceProtocol",
    "BatchParallelRenderSource",
    "TrainingRenderController",
    "TrainingRenderEvents",
    "TrainingRenderKeyMap",
    "TrainingRenderSettings",
    "TrainingRenderVecAdapter",
    "resolve_training_render_settings",
]
