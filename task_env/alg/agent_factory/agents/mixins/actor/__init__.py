"""Lazy compatibility exports; optional algorithms load only on request."""
from importlib import import_module

_EXPORTS = {'DiffusionActorMixin': '.diffusion', 'ConditionalDiffusionActorMixin': '.conditional_diffusion', 'CPIQLDACActorMixin': '.cpiql_dac', 'FlowMatchingActorMixin': '.flow_matching', 'Pi0ActorMixin': '.pi0'}
__all__ = list(_EXPORTS)

def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    value = getattr(import_module(_EXPORTS[name], __name__), name)
    globals()[name] = value
    return value
