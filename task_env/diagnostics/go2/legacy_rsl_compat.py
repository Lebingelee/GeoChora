"""Read-only compatibility probe for the legacy RSL-RL runner.

The supplied adamanip environment is Python 3.8 while its installed
``rsl_rl 1.0.2`` source contains one eagerly evaluated PEP 604 annotation in
``algorithms/distillation.py``.  This module can load that one module from
its existing file with postponed annotations in memory; it never edits the
external environment and remains lazy with respect to RSL-RL.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import Any


def _install_python38_annotation_shim() -> None:
    package = importlib.import_module("rsl_rl")
    root = Path(next(iter(getattr(package, "__path__", ())))).resolve()
    source_path = root / "algorithms" / "distillation.py"
    if not source_path.is_file():
        raise ImportError(f"legacy distillation module not found: {source_path}")

    # Drop only partially imported package children from the failed attempt.
    for name in tuple(sys.modules):
        if name == "rsl_rl.runners" or name.startswith("rsl_rl.runners."):
            sys.modules.pop(name, None)
        if name == "rsl_rl.algorithms" or name.startswith("rsl_rl.algorithms."):
            sys.modules.pop(name, None)

    module_name = "rsl_rl.algorithms.distillation"
    module = types.ModuleType(module_name)
    module.__file__ = str(source_path)
    module.__package__ = "rsl_rl.algorithms"
    source = source_path.read_text(encoding="utf-8")
    source = "from __future__ import annotations\n" + source
    exec(compile(source, str(source_path), "exec"), module.__dict__)
    sys.modules[module_name] = module


def import_legacy_on_policy_runner() -> tuple[Any, dict[str, Any]]:
    """Return ``(OnPolicyRunner, probe_metadata)`` for legacy RSL-RL.

    The normal import is attempted first.  The in-memory shim is used only
    for the known Python 3.8 PEP604 failure; all other import errors are
    returned to callers unchanged so a missing/incompatible installation is
    never hidden.
    """

    try:
        from rsl_rl.runners import OnPolicyRunner
    except TypeError as exc:
        if "unsupported operand type(s) for |" not in str(exc):
            raise
        _install_python38_annotation_shim()
        from rsl_rl.runners import OnPolicyRunner

        return OnPolicyRunner, {
            "legacy_runner_import": "ok",
            "python38_annotation_shim": True,
            "shim_scope": "in_memory_distillation_module_only",
        }
    return OnPolicyRunner, {
        "legacy_runner_import": "ok",
        "python38_annotation_shim": False,
    }


__all__ = ["import_legacy_on_policy_runner"]
