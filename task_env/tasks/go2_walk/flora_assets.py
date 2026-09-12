"""Go2-specific Flora asset adapter for the Go2 walk task family.

The Flora backend remains robot-agnostic.  This task-owned adapter supplies
the canonical Go2 MJCF/asset roots and, when needed by offline diagnostics,
the public compiled body order.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ...robots.go2 import GO2_ASSET_ROOT, GO2_MJCF_PATH
from ...render.flora.assets import FloraSceneBundle, build_scene_file_from_mjcf


def build_go2_flora_bundle(
    *,
    output_dir: str | Path,
    instance_count: int = 1,
    body_order: Sequence[str] = (),
    force: bool = False,
) -> FloraSceneBundle:
    """Prepare the Go2 SceneFile for explicit task/diagnostic use."""

    return build_scene_file_from_mjcf(
        output_dir=output_dir,
        mjcf_path=GO2_MJCF_PATH,
        asset_root=GO2_ASSET_ROOT / "assets",
        instance_count=int(instance_count),
        body_order=body_order,
        scene_name="go2_single",
        force=force,
    )


__all__ = ["build_go2_flora_bundle"]
