"""NutAssembly 的纯描述物体组件。"""

from __future__ import annotations

from pathlib import Path

from ..utils._paths import REPO_ROOT
from ..environment import AssetManifest, ReferenceSpec
from ..registry import register_object
from .base import BaseTaskObject


NUT_ASSET_ROOT = REPO_ROOT / "task_env" / "objects" / "default_asset"


@register_object("square-nut-v1")
class SquareNutObject(BaseTaskObject):
    uid = "square-nut-v1"

    def asset_manifest(self) -> AssetManifest:
        return AssetManifest(
            owner_uid=self.uid,
            asset_kind="task_object_mjcf",
            mjcf_sources=(NUT_ASSET_ROOT / "square-nut.xml",),
            asset_roots=(NUT_ASSET_ROOT,),
            asset_version="robosuite-square-nut-local-copy",
        )

    def reference_spec(self) -> ReferenceSpec:
        return ReferenceSpec(
            body_names=("SquareNut",),
            joint_names=("SquareNut_joint",),
            site_names=(
                "handle_site",
                "center_site",
                "bottom_site",
                "top_site",
            ),
        )


@register_object("square-peg-v1")
class SquarePegObject(BaseTaskObject):
    uid = "square-peg-v1"

    def asset_manifest(self) -> AssetManifest:
        return AssetManifest(
            owner_uid=self.uid,
            asset_kind="procedural_task_object",
            asset_version="nut-assembly-peg-v1",
        )

    def reference_spec(self) -> ReferenceSpec:
        return ReferenceSpec(
            body_names=("peg1",),
            geom_names=("square_peg_collision", "square_peg_visual"),
        )


@register_object("round-peg-v1")
class RoundPegObject(BaseTaskObject):
    uid = "round-peg-v1"

    def asset_manifest(self) -> AssetManifest:
        return AssetManifest(
            owner_uid=self.uid,
            asset_kind="procedural_task_object",
            asset_version="nut-assembly-peg-v1",
        )

    def reference_spec(self) -> ReferenceSpec:
        return ReferenceSpec(
            body_names=("peg2",),
            geom_names=("round_peg_collision", "round_peg_visual"),
        )


@register_object("cube-v1")
class CubeObject(BaseTaskObject):
    uid = "cube-v1"

    def asset_manifest(self) -> AssetManifest:
        return AssetManifest(
            owner_uid=self.uid,
            asset_kind="procedural_task_object",
            asset_version="pick-cube-box-v1",
        )

    def reference_spec(self) -> ReferenceSpec:
        return ReferenceSpec(
            body_names=("PickCube",),
            joint_names=("PickCube_joint",),
            site_names=("PickCube_center_site",),
            geom_names=("PickCube_collision", "PickCube_visual"),
        )


__all__ = [
    "CubeObject",
    "NUT_ASSET_ROOT",
    "RoundPegObject",
    "SquareNutObject",
    "SquarePegObject",
]
