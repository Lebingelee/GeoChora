"""Shared, side-effect-light bootstrap for the TaskEnv example scripts.

This module only prepares import paths and ordinary Python helpers at import
time.  Taichi, Gym environments, and SB3 are imported inside the example
entry points so learner-side imports remain free of simulator initialization.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, is_dataclass
import json
import math
import sys
from pathlib import Path
from typing import Any, TypeVar

import numpy as np

from task_env.utils._paths import GEOPHYS_PROVIDER_ROOT, REPO_ROOT


T = TypeVar("T")
STAGE14_OUTPUT_ROOT = REPO_ROOT / "workspace" / "diagnostics" / "stage14"
BACKEND_CHOICES = ("auto", "cuda", "cpu", "vulkan")


def configure_imports() -> None:
    """Expose Geochora and its GeoPhys provider for direct script runs."""

    # Insert in reverse so the effective order is provider ``src`` before the
    # Geochora root.  A legacy test checkout is supported when present, but is
    # not required by the migrated project.
    for entry in (
        REPO_ROOT / "test",
        REPO_ROOT,
        GEOPHYS_PROVIDER_ROOT / "src",
    ):
        value = str(entry)
        if entry.is_dir() and value not in sys.path:
            sys.path.insert(0, value)


def get_logger(module: str):
    """Load the repository logger lazily for a script entry point."""

    configure_imports()
    from utils.logger import get_component_logger

    return get_component_logger("simulation", module=module)


def load_yaml_mapping(path: str | Path | None) -> dict[str, Any]:
    """Load a public YAML mapping and reject scalar/list roots."""

    if path is None:
        return {}
    import yaml

    source = Path(path)
    with source.open("r", encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"configuration root must be a mapping: {source}")
    return dict(value)


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Deep-merge user-owned config sections without mutating either input."""

    result = dict(base)
    for key, value in override.items():
        previous = result.get(key)
        if isinstance(previous, Mapping) and isinstance(value, Mapping):
            result[key] = deep_merge(previous, value)
        else:
            result[key] = value
    return result


def resolve_config(
    *,
    inline: Mapping[str, Any] | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Resolve inline values followed by a YAML override."""

    return deep_merge(dict(inline or {}), load_yaml_mapping(config_path))


def json_compatible(value: Any) -> Any:
    """Project dataclasses/arrays/tuples to strict JSON-compatible values."""

    if is_dataclass(value):
        return json_compatible(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): json_compatible(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_compatible(item) for item in value]
    if isinstance(value, np.ndarray):
        return json_compatible(value.tolist())
    if isinstance(value, np.generic):
        return json_compatible(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if value is None or isinstance(value, (str, int, bool)):
        return value
    return str(value)


def resolved_config_summary(env: Any) -> dict[str, Any]:
    """Return the public resolved config and metadata projection of an env."""

    return {
        "config": json_compatible(getattr(env, "config", {})),
        "metadata": json_compatible(dict(getattr(env, "metadata", {}))),
    }


def stage14_output(*parts: str | Path) -> Path:
    """Return and create a path under the documented Stage 14 output root."""

    output = STAGE14_OUTPUT_ROOT.joinpath(*(str(part) for part in parts))
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def write_json(path: str | Path, value: Any) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(json_compatible(value), indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return output


def backend_candidates(requested: str) -> tuple[str, ...]:
    normalized = str(requested).strip().lower()
    if normalized not in BACKEND_CHOICES:
        raise ValueError(f"backend must be one of {BACKEND_CHOICES}, got {requested!r}")
    if normalized in {"auto", "cuda"}:
        return ("cuda", "cpu")
    return (normalized,)


def with_backend_fallback(
    requested: str,
    factory: Callable[[str], T],
    *,
    logger: Any,
    operation: str,
) -> tuple[str, T]:
    """Run an environment factory CUDA-first and log an explicit CPU fallback."""

    candidates = backend_candidates(requested)
    last_error: Exception | None = None
    for index, backend in enumerate(candidates):
        try:
            result = factory(backend)
            logger.info(
                "TaskEnv script backend selected",
                event="runtime.backend_selected",
                operation=operation,
                requested_backend=requested,
                backend=backend,
            )
            return backend, result
        except Exception as exc:
            last_error = exc
            if index + 1 >= len(candidates):
                raise
            logger.warning(
                "TaskEnv script backend failed; switching to CPU",
                event="runtime.backend_fallback",
                operation=operation,
                requested_backend=requested,
                failed_backend=backend,
                fallback_backend=candidates[index + 1],
                error_type=type(exc).__name__,
                error=str(exc),
            )
    if last_error is None:
        raise RuntimeError("backend factory did not produce a result")
    raise last_error


def _walk_arrays(value: Any, path: str = ""):
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield from _walk_arrays(child, f"{path}.{key}" if path else str(key))
    elif isinstance(value, (tuple, list)):
        for index, child in enumerate(value):
            yield from _walk_arrays(child, f"{path}[{index}]")
    elif isinstance(value, np.ndarray):
        yield path, value


def _first_batch(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _first_batch(child) for key, child in value.items()}
    if isinstance(value, (tuple, list)):
        return type(value)(_first_batch(child) for child in value)
    if isinstance(value, np.ndarray):
        return value[0]
    return value


def check_observation(observation: Any, observation_space: Any, *, batch: int | None = None) -> None:
    """Check public observation containment, finite numeric leaves, and batch shape."""

    candidate = _first_batch(observation) if batch is not None else observation
    if not observation_space.contains(candidate):
        raise ValueError("observation is outside the advertised observation_space")
    for path, value in _walk_arrays(observation):
        if np.issubdtype(value.dtype, np.number) and not np.isfinite(value).all():
            raise ValueError(f"observation leaf {path!r} contains non-finite values")
        if batch is not None and (value.ndim < 1 or value.shape[0] != batch):
            raise ValueError(f"observation leaf {path!r} must have leading batch {batch}")


def pick_cube_config(*, backend: str, horizon: int):
    """Return the documented public configuration used by all examples."""
    return {
        "runtime": {
            "backend": backend,
            "broadphase": "n2",
            "prewarm": False,
            "control_substeps": 25,
        },
        "robot": {"controller": {"kind": "absolute_pose", "reference": "world"}},
        "episode": {"horizon": horizon},
    }
