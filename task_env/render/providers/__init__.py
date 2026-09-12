"""TaskEnv render providers with lazy concrete implementations."""

from importlib import import_module


_LAZY_EXPORTS = {
    "TaskEnvRenderProvider": ("task_env.render.providers.single", "TaskEnvRenderProvider"),
    "ParallelRenderLayout": ("task_env.render.providers.parallel", "ParallelRenderLayout"),
    "ParallelRenderProvider": ("task_env.render.providers.parallel", "ParallelRenderProvider"),
    "ParallelRenderSourceProtocol": (
        "task_env.render.providers.parallel",
        "ParallelRenderSourceProtocol",
    ),
    "BatchParallelRenderSource": (
        "task_env.render.providers.parallel_source",
        "BatchParallelRenderSource",
    ),
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
    "TaskEnvRenderProvider",
    "ParallelRenderLayout",
    "ParallelRenderProvider",
    "ParallelRenderSourceProtocol",
    "BatchParallelRenderSource",
]
