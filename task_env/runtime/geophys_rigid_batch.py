"""Compatibility-only alias for the GeoPhys batch provider.

The canonical implementation is owned by
``task_env.runtime.providers.geophys.rigid_batch``.  Keep this exact-module
route for repository and downstream migration callers without duplicating
state, lifecycle, or solver logic.
"""

from importlib import import_module
import sys

_implementation = import_module("task_env.runtime.providers.geophys.rigid_batch")
sys.modules[__name__] = _implementation
