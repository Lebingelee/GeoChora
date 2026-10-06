"""Lazy compatibility exports; optional algorithms load only on request."""
from importlib import import_module

_EXPORTS = {'ExpertDataset': '.expert_dataset', 'ClassicReplayBuffer': '.replaybuffer', 'FileReplayBuffer': '.replaybuffer', 'CPIQLExpertDataset': '.cpiql', 'CPIQLFileReplayBuffer': '.cpiql'}
__all__ = list(_EXPORTS)

def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    value = getattr(import_module(_EXPORTS[name], __name__), name)
    globals()[name] = value
    return value
