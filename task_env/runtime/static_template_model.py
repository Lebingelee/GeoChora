"""Compatibility-only alias for the static model inventory."""

from importlib import import_module
import sys

_implementation = import_module("task_env.runtime.providers.static.model")
sys.modules[__name__] = _implementation
