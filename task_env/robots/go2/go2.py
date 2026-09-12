"""Canonical Unitree Go2 binding for the menagerie ``go2.xml`` asset.

The checked-in menagerie XML names the free-root body ``base``.  The real
robot binding is kept separately in :mod:`go2_real` because its asset uses
``base_link``.  This module owns the public ``go2-v1`` registration and
reuses the common action implementation from the real-asset snapshot.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ...environment import AssetManifest, ReferenceSpec
from ...registry import register_agent
from .go2_real import (
    GO2_ACTION_CONTRACT,
    GO2_ACTION_CLIP,
    GO2_ACTION_SCALE,
    GO2_ACTUATOR_NAMES,
    GO2_ASSET_ROOT,
    GO2_DEFAULT_JOINT_ANGLES,
    GO2_FOOT_GEOM_NAMES,
    GO2_JOINT_NAMES,
    GO2_KD,
    GO2_KP,
    GO2_MJCF_PATH,
    GO2_SITE_NAMES,
    Go2ActionAdapter,
    Go2Agent as _RealAssetGo2Agent,
)


GO2_BASE_BODY_NAME = "base"
GO2_BODY_NAMES = (
    GO2_BASE_BODY_NAME,
    "FL_hip", "FL_thigh", "FL_calf",
    "FR_hip", "FR_thigh", "FR_calf",
    "RL_hip", "RL_thigh", "RL_calf",
    "RR_hip", "RR_thigh", "RR_calf",
)


@dataclass(frozen=True)
class Go2Entity:
    uid: str = "go2-v1"
    base_body_name: str = GO2_BASE_BODY_NAME
    imu_site_name: str = "imu"


@register_agent("go2-v1")
class Go2Agent(_RealAssetGo2Agent):
    """Agent descriptor bound to the canonical menagerie XML topology."""

    uid = "go2-v1"

    def asset_manifest(self) -> AssetManifest:
        return AssetManifest(
            owner_uid=self.uid,
            asset_kind="agent_mjcf",
            mjcf_sources=(GO2_MJCF_PATH,),
            asset_roots=(GO2_ASSET_ROOT,),
            asset_version="mujoco-menagerie-unitree-go2",
        )

    def reference_spec(self) -> ReferenceSpec:
        return ReferenceSpec(
            body_names=GO2_BODY_NAMES,
            joint_names=GO2_JOINT_NAMES,
            site_names=GO2_SITE_NAMES,
            geom_names=GO2_FOOT_GEOM_NAMES,
            actuator_names=GO2_ACTUATOR_NAMES,
        )

    def reference_layout(self) -> Mapping[str, str]:
        return {"base_body_name": GO2_BASE_BODY_NAME, "eef_site_name": "imu"}


__all__ = [
    "GO2_ACTION_CONTRACT",
    "GO2_ACTION_CLIP",
    "GO2_ACTION_SCALE",
    "GO2_ACTUATOR_NAMES",
    "GO2_ASSET_ROOT",
    "GO2_BASE_BODY_NAME",
    "GO2_BODY_NAMES",
    "GO2_DEFAULT_JOINT_ANGLES",
    "GO2_FOOT_GEOM_NAMES",
    "GO2_JOINT_NAMES",
    "GO2_KD",
    "GO2_KP",
    "GO2_MJCF_PATH",
    "GO2_SITE_NAMES",
    "Go2ActionAdapter",
    "Go2Agent",
    "Go2Entity",
]
