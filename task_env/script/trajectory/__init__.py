"""TaskEnv trajectory examples and compatibility command exports.

The package is intentionally lazy: offline conversion/replay imports do not
load the task solution builders, while the historical Stage 11 imports keep
working when their symbols are requested.
"""

from importlib import import_module


_LAZY_EXPORTS = {
    "_build_plan": ("._task_plans", "_build_plan"),
    "_collect": (".commands", "_collect"),
    "_nut_assembly_config": ("._task_plans", "_nut_assembly_config"),
    "_pick_cube_config": ("._task_plans", "_pick_cube_config"),
    "main": (".commands", "main"),
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
