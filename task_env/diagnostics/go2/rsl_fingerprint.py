"""Read-only fingerprinting for installed RSL-RL API variants."""

from __future__ import annotations

import importlib
import importlib.metadata
import inspect
from typing import Any


def _version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def installed_fingerprint() -> dict[str, Any]:
    """Return a JSON-friendly API fingerprint without constructing a runner."""

    result: dict[str, Any] = {
        "rsl_rl_version": _version("rsl-rl"),
        "rsl_rl_lib_version": _version("rsl-rl-lib"),
        "python": __import__("platform").python_version(),
    }
    try:
        rsl = importlib.import_module("rsl_rl")
    except Exception as exc:
        result["available"] = False
        result["import_error"] = f"{type(exc).__name__}: {exc}"
    else:
        result["available"] = True
        result["source"] = str(getattr(rsl, "__file__", ""))
        try:
            vec = importlib.import_module("rsl_rl.env").VecEnv
            runner = importlib.import_module("rsl_rl.runners").OnPolicyRunner
            result["vec_env"] = {
                name: str(inspect.signature(getattr(vec, name)))
                for name in ("get_observations", "step", "reset")
                if hasattr(vec, name)
            }
            result["runner"] = {"init": str(inspect.signature(runner.__init__))}
        except Exception as exc:
            result["api_error"] = f"{type(exc).__name__}: {exc}"
    try:
        torch = importlib.import_module("torch")
        result["torch_version"] = str(getattr(torch, "__version__", ""))
        result["cuda_available"] = bool(torch.cuda.is_available())
        result["cuda_device_count"] = int(torch.cuda.device_count())
    except (ImportError, ModuleNotFoundError):
        result["torch_version"] = None
    try:
        td = importlib.import_module("tensordict")
        result["tensordict_version"] = str(getattr(td, "__version__", ""))
    except (ImportError, ModuleNotFoundError):
        result["tensordict_version"] = None
    return result


__all__ = ["installed_fingerprint"]
