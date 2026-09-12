"""Compatibility-only alias for the static provider protocol."""

from importlib import import_module
import sys

_implementation = import_module("task_env.runtime.providers.static.provider")
sys.modules[__name__] = _implementation
