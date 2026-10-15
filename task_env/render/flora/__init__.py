"""TaskEnv-owned, robot-agnostic Flora backend namespace."""

from .backend import FloraRenderBackend


_LAZY_EXPORTS = {
    "FloraSceneBundle": ".assets",
    "build_scene_file_from_assemblies": ".assets",
    "build_scene_file_from_mjcf": ".assets",
    "build_scene_file_from_render_scene": ".assets",
    "FloraRuntimeConfig": ".runtime",
    "FloraRuntimeProbe": ".runtime",
    "load_flora_backend": ".runtime",
    "probe_flora_runtime": ".runtime",
    "FloraScene": ".scene",
    "build_flora_scene_from_source": ".scene",
    "FloraParallelVisualizer": ".parallel",
}


def __getattr__(name: str):
    from importlib import import_module

    module = _LAZY_EXPORTS.get(name)
    if module is None:
        raise AttributeError(name)
    value = getattr(import_module(module, __name__), name)
    globals()[name] = value
    return value

__all__ = [
    "FloraRenderBackend",
    "FloraRuntimeConfig",
    "FloraRuntimeProbe",
    "FloraScene",
    "FloraParallelVisualizer",
    "FloraSceneBundle",
    "build_flora_scene_from_source",
    "build_scene_file_from_assemblies",
    "build_scene_file_from_mjcf",
    "build_scene_file_from_render_scene",
    "load_flora_backend",
    "probe_flora_runtime",
]
