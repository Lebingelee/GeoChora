"""可复用 tabletop 背景描述。"""

import xml.etree.ElementTree as ET

from ...environment import AssetManifest, ReferenceSpec
from ...registry import register_scene
from .base import BaseSceneBuilder


_EMPTY_TABLETOP_XML = """
<mujoco model="task_env_empty_tabletop">
  <option timestep="0.002" gravity="0 0 -9.81"/>
  <worldbody>
    <body name="grasp_table" pos="0 0 0.45">
      <geom name="grasp_table_geom" type="box" size="0.28 0.20 0.01"
            rgba="0.34 0.39 0.42 1"/>
      <geom name="grasp_table_visual" type="box" size="0.28 0.20 0.0101"
            contype="0" conaffinity="0" rgba="0.34 0.39 0.42 1"/>
    </body>
  </worldbody>
</mujoco>
"""


def _add_tabletop_if_missing(root: ET.Element) -> None:
    worldbody = root.find("worldbody")
    if worldbody is None:
        raise KeyError("Panda MJCF does not contain worldbody")
    if worldbody.find("body[@name='grasp_table']") is not None:
        return
    table = ET.SubElement(
        worldbody,
        "body",
        {
            "name": "grasp_table",
            "pos": "0.5545 0 0.452",
        },
    )
    ET.SubElement(
        table,
        "geom",
        {
            "name": "grasp_table_geom",
            "type": "box",
            "size": "0.28 0.20 0.01",
            "condim": "4",
            "friction": "1.2 0.25 0.02",
            "rgba": "0.34 0.39 0.42 1",
        },
    )
    ET.SubElement(
        table,
        "geom",
        {
            "name": "grasp_table_visual",
            "type": "box",
            "size": "0.28 0.20 0.0101",
            "contype": "0",
            "conaffinity": "0",
            "group": "2",
            "mass": "0",
            "rgba": "0.34 0.39 0.42 1",
        },
    )


@register_scene("tabletop-v1")
class TabletopSceneBuilder(BaseSceneBuilder):
    uid = "tabletop-v1"

    def build_scene_source(self, composition, agents):
        """Compose this world with an explicitly declared component source."""
        from scene import SceneSource
        if tuple(agent.uid for agent in agents) != tuple(composition.agent_uids):
            raise ValueError("scene Robots differ from the task composition")
        if not agents:
            return SceneSource.mjcf_string(
                _EMPTY_TABLETOP_XML, label="task-env-empty-tabletop",
            ), "inline_empty_tabletop_v1"
        if len(agents) != 1:
            raise NotImplementedError("tabletop component source supports one Robot")
        robot = agents[0]
        declare = getattr(robot, "component_mjcf_frames", None)
        if not callable(declare):
            raise NotImplementedError("Robot has no component MJCF frame declaration")
        from ...runtime.sessions.mujoco_composition import lower_component_scene_source
        xml, base = lower_component_scene_source(
            robot.single_mjcf_source(), frames=declare(), add_world=_add_tabletop_if_missing,
        )
        label, adapter = robot.component_scene_identity()
        return SceneSource.mjcf_string(xml, base_dir=base, label=label), adapter

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
