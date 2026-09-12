"""TaskEnv utilities that are safe to import in learner processes."""

from importlib import import_module

# ``_paths`` and ``_device_stack`` are private cross-cutting helpers. They
# remain importable by explicit module path but are intentionally not
# re-exported from the public utility namespace.


_LAZY_EXPORTS = {
    "SB3FlattenVecWrapper": (".sb3", "SB3FlattenVecWrapper"),
    "tree_copy": (".tree", "tree_copy"),
    "tree_index": (".tree", "tree_index"),
    "tree_set_index": (".tree", "tree_set_index"),
    "tree_stack": (".tree", "tree_stack"),
    "validate_batched_tree": (".tree", "validate_batched_tree"),
    "get_task_env_logger": (".runtime_support", "get_task_env_logger"),
    "init_task_env_backend": (".runtime_support", "init_task_env_backend"),
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
