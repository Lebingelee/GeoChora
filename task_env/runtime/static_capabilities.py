"""Compatibility-only alias for static profile facts.

Use ``task_env.runtime.providers.static.profile`` for the canonical internal
owner.  This module has no independent capability state.
"""

from importlib import import_module
import sys

_implementation = import_module("task_env.runtime.providers.static.profile")
sys.modules[__name__] = _implementation
