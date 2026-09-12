"""Compatibility exports for the canonical Go2 Flora asset pipeline.

The implementation lives in :mod:`task_env.render.flora.assets`; Go2 paths
and task-specific defaults live in :mod:`task_env.tasks.go2_walk.flora_assets`.
New diagnostics should use ``task_env.diagnostics.flora`` instead of this
legacy module.
"""

from __future__ import annotations

from pathlib import Path

from .render.flora.assets import FloraSceneBundle, build_scene_file_from_mjcf


# Preserve the old symbol name for checkout-local callers while ensuring that
# there is only one MJCF/OBJ -> GLB/SceneFile implementation.
Go2FloraBundle = FloraSceneBundle


def build_go2_flora_bundle(
    *,
    output_dir: str | Path,
    mjcf_path: str | Path,
    asset_root: str | Path,
    force: bool = False,
) -> FloraSceneBundle:
    """Compatibility wrapper for the former explicit-path converter."""

    return build_scene_file_from_mjcf(
        output_dir=output_dir,
        mjcf_path=mjcf_path,
        asset_root=asset_root,
        instance_count=1,
        scene_name="go2_single",
        force=force,
    )


__all__ = ["Go2FloraBundle", "build_go2_flora_bundle"]
