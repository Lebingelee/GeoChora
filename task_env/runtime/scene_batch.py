"""Compatibility-only alias for the merged-scene provider."""

from importlib import import_module
import sys

_implementation = import_module("task_env.runtime.providers.merged_scene")
sys.modules[__name__] = _implementation
