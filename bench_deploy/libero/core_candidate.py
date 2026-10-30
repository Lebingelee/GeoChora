"""Internal constructor for the fixed R07c LIBERO SelectedReferenceEnv route."""
from __future__ import annotations

from pathlib import Path


def build_libero_pilot_env(
    *, xml: str, composed_mjcf_sha256: str, install_root: Path,
    build_runtime: bool = True,
):
    """Build the fixed candidate through SelectedReferenceEnv and RuntimeSession.

    ``build_runtime`` remains accepted for source compatibility with the prior
    internal recipe. Construction itself never imports or compiles MuJoCo;
    the selected environment materializes only when reset is requested.
    """
    del build_runtime
    from .selected_candidate import build_libero_selected_candidate

    return build_libero_selected_candidate(
        xml=xml, composed_mjcf_sha256=composed_mjcf_sha256,
        install_root=Path(install_root),
    )


def build_libero_solution_env(
    *, xml: str, composed_mjcf_sha256: str, install_root: Path,
    composition_plan_path: Path, horizon: int = 1000,
):
    """Build the task #1 caller-owned Solution profile on the same Core route."""
    from .selected_candidate import build_libero_solution_candidate

    return build_libero_solution_candidate(
        xml=xml, composed_mjcf_sha256=composed_mjcf_sha256,
        install_root=Path(install_root), composition_plan_path=Path(composition_plan_path),
        horizon=horizon,
    )


__all__ = ['build_libero_pilot_env', 'build_libero_solution_env']
