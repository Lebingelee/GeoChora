"""Compatibility-only alias for static execution-plan facts."""

from importlib import import_module
import sys

_implementation = import_module("task_env.runtime.providers.static.execution")
sys.modules[__name__] = _implementation
