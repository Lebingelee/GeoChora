"""NutAssembly 的纯描述物体组件。"""

from __future__ import annotations

from pathlib import Path

from ..utils._paths import REPO_ROOT
from ..environment import AssetManifest, ReferenceSpec
from ..registry import register_object
from .base import BaseTaskObject


NUT_ASSET_ROOT = REPO_ROOT / "task_env" / "objects" / "default_asset"

# Reusable Nut/Peg asset geometry and inertial properties. Task placement and
# reset semantics live in the owning Task Artifact instead.
NUT_HALF_HEIGHT = 0.01
NUT_CONTACT_MARGIN = 1.0e-3
NUT_HANDLE_LOCAL_X = 0.054
NUT_MASS = 1.0
NUT_DIAG_INERTIA = (7.5e-4, 7.5e-4, 1.25e-3)
NUTASSEMBLY_NOMINAL_V1_ID = "nutassembly-nominal-v1"
NUTASSEMBLY_NOMINAL_V1_MASS = 0.1
NUTASSEMBLY_NOMINAL_V1_DIAG_INERTIA = (7.5e-5, 7.5e-5, 1.25e-4)
NUT_FREEJOINT_DAMPING = 2.0
NUT_FREEJOINT_ARMATURE = 0.03
PEG_HALF_HEIGHT = 0.06
SQUARE_PEG_HALF_WIDTH = 0.016
ROUND_PEG_RADIUS = 0.02


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
    "NUTASSEMBLY_NOMINAL_V1_DIAG_INERTIA",
    "NUTASSEMBLY_NOMINAL_V1_ID",
    "NUTASSEMBLY_NOMINAL_V1_MASS",
    "NUT_ASSET_ROOT",
    "NUT_CONTACT_MARGIN",
    "NUT_DIAG_INERTIA",
    "NUT_FREEJOINT_ARMATURE",
    "NUT_FREEJOINT_DAMPING",
    "NUT_HALF_HEIGHT",
    "NUT_HANDLE_LOCAL_X",
    "NUT_MASS",
    "PEG_HALF_HEIGHT",
    "ROUND_PEG_RADIUS",
    "RoundPegObject",
    "SQUARE_PEG_HALF_WIDTH",
    "SquareNutObject",
    "SquarePegObject",
]
