"""Gymnasium 导入边界。"""

from __future__ import annotations

try:
    from gymnasium import Env as GymEnvBase
except ModuleNotFoundError as error:
    if error.name != 'gymnasium':
        raise
    GYMNASIUM_AVAILABLE = False

    class GymEnvBase:
        """Definition-only base; creating an Env still requires Gymnasium."""
        def __new__(cls, *args, **kwargs):
            raise ModuleNotFoundError('Gymnasium is required to create a TaskEnv', name='gymnasium')
else:
    GYMNASIUM_AVAILABLE = True


def Box(*args, **kwargs):
    """Construct the real Gymnasium Box at the host space boundary."""
    from gymnasium.spaces import Box as GymBox
    return GymBox(*args, **kwargs)


def Dict(*args, **kwargs):
    """Construct the real Gymnasium Dict at the host space boundary."""
    from gymnasium.spaces import Dict as GymDict
    return GymDict(*args, **kwargs)


__all__ = ["GYMNASIUM_AVAILABLE", "GymEnvBase", "Box", "Dict"]
