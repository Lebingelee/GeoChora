"""Compatibility-only alias for the static runtime facade."""

from importlib import import_module
import sys

_implementation = import_module("task_env.runtime.providers.static.runtime")
sys.modules[__name__] = _implementation
