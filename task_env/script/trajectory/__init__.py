"""Selected-route recording and provider-independent trajectory utilities."""

from importlib import import_module


_LAZY_EXPORTS = {
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
