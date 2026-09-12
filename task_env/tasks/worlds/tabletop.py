"""可复用 tabletop 背景描述。"""

from ...environment import AssetManifest, ReferenceSpec
from ...registry import register_scene
from .base import BaseSceneBuilder


@register_scene("tabletop-v1")
class TabletopSceneBuilder(BaseSceneBuilder):
    uid = "tabletop-v1"

    def asset_manifest(self) -> AssetManifest:
        return AssetManifest(
            owner_uid=self.uid,
            asset_kind="procedural_scene_description",
            asset_version="nut-assembly-tabletop-v1",
        )

    def reference_spec(self) -> ReferenceSpec:
        return ReferenceSpec(
            body_names=("grasp_table",),
            geom_names=("grasp_table_geom", "grasp_table_visual"),
        )


__all__ = ["TabletopSceneBuilder"]
