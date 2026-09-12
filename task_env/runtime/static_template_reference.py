"""Compatibility-only alias for the exact-B static reference provider."""

from importlib import import_module
import sys

_implementation = import_module("task_env.runtime.providers.static.reference")
sys.modules[__name__] = _implementation
