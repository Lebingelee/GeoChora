"""Compatibility-only alias for the static fused provider.

The canonical module is intentionally not imported by ``task_env.runtime``
package initialization.  Importing this historical route explicitly retains
the old exact-module ABI and resolves to the same implementation module.
"""

from importlib import import_module
import sys

_implementation = import_module("task_env.runtime.providers.static.fused")
sys.modules[__name__] = _implementation
