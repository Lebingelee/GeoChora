"""Offline trajectory APIs; serialization dependencies load only when requested."""

from importlib import import_module

_PROCESSING_EXPORTS = frozenset({
    'ActionTransformError', 'TrajectoryCollectionError', 'TrajectoryMergeError',
    'TrajectoryValidationError', 'inspect_trajectory', 'merge_trajectories',
    'merge_trajectory_collections', 'transcode_actions', 'transcode_trajectory_collection',
    'validate_trajectory', 'validate_trajectory_collection',
})
_REPLAY_EXPORTS = frozenset({
    'ReplayVerificationError', 'replay_and_verify_collection', 'replay_and_verify_universal_action',
})
__all__ = sorted(_PROCESSING_EXPORTS | _REPLAY_EXPORTS)


def __getattr__(name):
    if name in _PROCESSING_EXPORTS:
        module = import_module('.processing', __name__)
    elif name in _REPLAY_EXPORTS:
        module = import_module('.replay', __name__)
    else:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    value = getattr(module, name)
    globals()[name] = value
    return value
