"""Homogeneous device-batched TaskEnv adapters.

The exports are lazy on purpose.  Importing the learner-side parallel factory
must not import a concrete Taichi runtime before the simulator worker starts.
"""

from importlib import import_module


_LAZY_EXPORTS = {
    "BatchTaskDefinitionBase": (".task_definition", "BatchTaskDefinitionBase"),
    "BatchTaskLifecycleAdapter": (".task_definition", "BatchTaskLifecycleAdapter"),
    "TaskLifecycleAdapter": (".task_definition", "TaskLifecycleAdapter"),
    "PARALLEL_ENV_REGISTRY": (".registry", "PARALLEL_ENV_REGISTRY"),
    "HomogeneousVectorTaskEnv": (".homogeneous", "HomogeneousVectorTaskEnv"),
    "GenericHomogeneousVectorTaskEnv": (".homogeneous", "HomogeneousVectorTaskEnv"),
    "LocalBatchVecEnv": (".sb3", "LocalBatchVecEnv"),
    "RemoteBatchVecEnv": (".parallel", "RemoteBatchVecEnv"),
    "TaskEnvSB3VecAdapter": (".sb3", "TaskEnvSB3VecAdapter"),
    "make_homogeneous_env": (".parallel", "make_homogeneous_env"),
    "make_parallel_env": (".parallel", "make_parallel_env"),
    "register_vector_env": (".parallel", "register_vector_env"),
    "register_parallel_env": (".registry", "register_parallel_env"),
}


def __getattr__(name: str):
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


__all__ = sorted(_LAZY_EXPORTS)
