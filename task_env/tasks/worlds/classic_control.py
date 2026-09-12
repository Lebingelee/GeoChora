"""经典控制任务使用的最小 scene 描述组件。"""

from __future__ import annotations

from ...environment import AssetManifest, ReferenceSpec
from ...registry import register_scene
from .base import BaseSceneBuilder


@register_scene("pendulum-v1")
class PendulumSceneBuilder(BaseSceneBuilder):
    """Declare the stable names required by the inline Pendulum MJCF scene."""

    uid = "pendulum-v1"

    def asset_manifest(self) -> AssetManifest:
        return AssetManifest(
            owner_uid=self.uid,
            asset_kind="inline_mjcf_scene",
            asset_version="task-env-pendulum-inline-v1",
        )

    def reference_spec(self) -> ReferenceSpec:
        return ReferenceSpec(
            body_names=("pendulum_anchor", "pendulum_link"),
            joint_names=("pendulum_hinge",),
            geom_names=("pendulum_anchor_geom", "pendulum_link_geom"),
            actuator_names=("pendulum_torque",),
        )


@register_scene("two-wheel-balance-v1")
class TwoWheelBalanceSceneBuilder(BaseSceneBuilder):
    """Declare stable names for the articulated two-wheel balance scene."""

    uid = "two-wheel-balance-v1"

    def asset_manifest(self) -> AssetManifest:
        return AssetManifest(
            owner_uid=self.uid,
            asset_kind="inline_mjcf_scene",
            asset_version="task-env-two-wheel-balance-inline-v1",
        )

    def reference_spec(self) -> ReferenceSpec:
        return ReferenceSpec(
            body_names=("balance_anchor", "balance_chassis", "left_wheel", "right_wheel"),
            joint_names=("chassis_pitch", "left_wheel_hinge", "right_wheel_hinge"),
            geom_names=(
                "balance_anchor_geom",
                "balance_chassis_geom",
                "left_wheel_geom",
                "right_wheel_geom",
            ),
            actuator_names=("left_wheel_torque", "right_wheel_torque"),
        )


__all__ = ["PendulumSceneBuilder", "TwoWheelBalanceSceneBuilder"]
