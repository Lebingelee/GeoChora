"""Lazy SB3 runner integration."""

from importlib import import_module


_EXPORTS = {"build_ppo": (".runner", "build_ppo"), "train": (".runner", "train")}


def __getattr__(name: str):
    try:
        module_name, attr_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name, __name__), attr_name)
    globals()[name] = value
    return value


__all__ = sorted(_EXPORTS)
