"""TaskEnv RayTracer backend and asset-instance lowering."""

from .backend import RaytracerRenderBackend


def __getattr__(name: str):
    from importlib import import_module

    if name == "build_raytracer_visualizer":
        module = ".scene"
    elif name == "RaytracerSceneVisualizer":
        module = ".visualizer"
    else:
        raise AttributeError(name)
    value = getattr(import_module(module, __name__), name)
    globals()[name] = value
    return value

__all__ = [
    "RaytracerRenderBackend",
    "RaytracerSceneVisualizer",
    "build_raytracer_visualizer",
]
