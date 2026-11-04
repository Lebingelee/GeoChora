"""Path helpers shared by TaskEnv descriptors and developer diagnostics.

TaskEnv can be imported from a Geochora source checkout or from an installed
wheel. A wheel intentionally does not contain the repository's external MJCF
assets, so repository discovery has a non-raising fallback; the later asset
compiler is responsible for reporting a missing deployment prerequisite.
"""

from __future__ import annotations

from pathlib import Path
from functools import partial
import inspect


def callable_source_path(callback) -> Path:
    """Find the implementation file of a callable, including partial applications.

    This identifies the callable's code owner only; it does not claim to trace
    arbitrary captured arguments, closure values, or indirect dependencies.
    """
    if not callable(callback):
        raise TypeError('source owner must be callable')
    while isinstance(callback, partial):
        callback = callback.func
    owner = callback if inspect.isroutine(callback) or inspect.isclass(callback) else type(callback)
    try:
        source = inspect.getsourcefile(owner)
    except (OSError, TypeError) as error:
        raise ValueError('callable has no traceable source file') from error
    if source is None or not Path(source).is_file():
        raise ValueError('callable has no traceable source file')
    return Path(source).resolve()


def repository_root(start: str | Path | None = None) -> Path:
    """Find a Geochora checkout, with a GeoPhys checkout fallback."""

    source = Path(start or __file__).resolve()
    anchor = source if source.is_dir() else source.parent
    for candidate in (anchor, *anchor.parents):
        if (
            (candidate / "task_env").is_dir()
            and (candidate / "asset").is_dir()
        ):
            return candidate
        if (candidate / "pyproject.toml").is_file() and (candidate / "src").is_dir():
            return candidate
    # Installed wheels have no repository marker. Keep imports usable and let
    # the runtime asset validator report the missing external prerequisite.
    return anchor.parent if anchor.name == "task_env" else anchor


GEOCHORA_ROOT = repository_root()
REPO_ROOT = GEOCHORA_ROOT
GEOPHYS_PROVIDER_ROOT = GEOCHORA_ROOT / "GeoPhys"
ASSET_ROOT = GEOCHORA_ROOT / "asset"
MUJOCO_MENAGERIE_ROOT = ASSET_ROOT / "external" / "mujoco_menagerie"
WORKSPACE_ROOT = GEOCHORA_ROOT / "workspace"


__all__ = [
    "ASSET_ROOT",
    "GEOCHORA_ROOT",
    "GEOPHYS_PROVIDER_ROOT",
    "MUJOCO_MENAGERIE_ROOT",
    "REPO_ROOT",
    "WORKSPACE_ROOT",
    "repository_root",
    "callable_source_path",
]
