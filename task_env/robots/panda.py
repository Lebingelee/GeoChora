"""Franka Panda 的纯描述组件。"""

from __future__ import annotations

from pathlib import Path

from ..utils._paths import MUJOCO_MENAGERIE_ROOT
from ..environment import AssetManifest, InitialStateSpec, ReferenceSpec
from ..registry import register_agent
from .base import BaseAgent
from .gripper import ExperimentalPandaGripperController, PandaGripperController


PANDA_ASSET_ROOT = MUJOCO_MENAGERIE_ROOT / "franka_emika_panda"


@register_agent("panda-v1")
class PandaAgent(BaseAgent):
    uid = "panda-v1"

    def asset_manifest(self) -> AssetManifest:
        return AssetManifest(
            owner_uid=self.uid,
            asset_kind="agent_mjcf",
            mjcf_sources=(PANDA_ASSET_ROOT / "panda.xml",),
            asset_roots=(PANDA_ASSET_ROOT,),
            asset_version="mujoco-menagerie-panda",
        )

    def reference_spec(self) -> ReferenceSpec:
        return ReferenceSpec(
            body_names=("link0", "hand", "left_finger", "right_finger"),
            joint_names=(
                "joint1",
                "joint2",
                "joint3",
                "joint4",
                "joint5",
                "joint6",
                "joint7",
                "finger_joint1",
                "finger_joint2",
            ),
            site_names=("nutassembly_ee_site",),
            actuator_names=(
                "actuator1",
                "actuator2",
                "actuator3",
                "actuator4",
                "actuator5",
                "actuator6",
                "actuator7",
                "actuator8",
            ),
        )

    def initial_state_spec(self) -> InitialStateSpec:
        return InitialStateSpec(
            joint_positions=(
                ("joint1", -0.17),
                ("joint2", 0.0),
                ("joint3", 0.0),
                ("joint4", -1.57079),
                ("joint5", 0.0),
                ("joint6", 1.57079),
                ("joint7", -0.7853),
                ("finger_joint1", 0.04),
                ("finger_joint2", 0.04),
            ),
            notes=("Stage 1 must resolve these names to qpos addresses.",),
        )

    def supported_controller_kinds(self) -> tuple[str, ...]:
        return (
            "absolute_joint",
            "absolute_pose",
            "delta_pose",
        )

    def create_gripper_controller(
        self,
        *,
        references,
        config,
        kind: str = "experimental_rate_limited",
        force_limit_N: float = 30.0,
        opening_step_m: float = 0.002,
        force_deadband_N: float = 1.0,
        force_adjust_step_m: float = 1.0e-4,
    ) -> PandaGripperController:
        """Create the selected Panda gripper controller after references resolve."""

        if kind == "experimental_rate_limited":
            return ExperimentalPandaGripperController(
                references=references,
                config=config,
                force_limit_N=force_limit_N,
                max_opening_step_m=opening_step_m,
                force_deadband_N=force_deadband_N,
                force_adjust_step_m=force_adjust_step_m,
            )
        if kind != "legacy":
            raise ValueError(f"unsupported Panda gripper controller kind {kind!r}")
        return PandaGripperController(
            references=references,
            config=config,
            force_limit_N=force_limit_N,
        )


__all__ = ["PANDA_ASSET_ROOT", "PandaAgent"]
