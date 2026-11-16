"""Compatibility export for the canonical scalar task environment."""

from .reference_env import SelectedReferenceEnv

BaseTaskEnv = SelectedReferenceEnv

__all__ = ["BaseTaskEnv"]
