"""Compatibility-only alias for the static Taichi provider."""

from importlib import import_module
import sys

_implementation = import_module("task_env.runtime.providers.static.physics")
sys.modules[__name__] = _implementation
