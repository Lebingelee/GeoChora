"""Compatibility-only alias for the static contact workspace."""

from importlib import import_module
import sys

_implementation = import_module("task_env.runtime.providers.static.workspace")
sys.modules[__name__] = _implementation
