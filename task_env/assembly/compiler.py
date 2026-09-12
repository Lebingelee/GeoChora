"""Stage 1 task-specific scene composition adapters."""

from __future__ import annotations

from dataclasses import dataclass
import xml.etree.ElementTree as ET

import numpy as np

from ..environment import EpisodePhysicsState, TaskCompositionSpec
from .references import TaskReferences, resolve_task_references


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


@dataclass(frozen=True)
class CompiledTaskScene:
    imported_scene: object
    loader_result: object
    scene_model: object
    references: TaskReferences
    initial_state: EpisodePhysicsState
    composition_adapter: str


def _find_body(root: ET.Element, name: str) -> ET.Element:
    for body in root.iter("body"):
        if body.get("name") == name:
            return body
    raise KeyError(f"body {name!r} is required by the task scene builder")


def _ensure_panda_ee_site(root: ET.Element) -> None:
    hand = _find_body(root, "hand")
    if hand.find("site[@name='nutassembly_ee_site']") is not None:
        return
    ET.SubElement(
        hand,
        "site",
        {
            "name": "nutassembly_ee_site",
            "pos": "0 0 0.0584",
            "size": "0.000001",
            "group": "6",
            "rgba": "0 0 0 0",
        },
    )


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


def _empty_tabletop_with_panda_xml(agents) -> tuple[str, object]:
    panda_agents = [agent for agent in agents if agent.uid == "panda-v1"]
    if len(panda_agents) != 1 or len(tuple(agents)) != 1:
        raise NotImplementedError("empty-v1 currently supports at most one panda-v1 agent")
    manifest = panda_agents[0].asset_manifest()
    if not manifest.mjcf_sources:
        raise ValueError("panda-v1 asset manifest must provide an MJCF source")
    panda_xml = manifest.mjcf_sources[0]
    root = ET.parse(panda_xml).getroot()
    compiler = root.find("compiler")
    if compiler is None:
        compiler = ET.SubElement(root, "compiler")
    compiler.set("meshdir", str((panda_xml.parent / "assets").resolve()).replace("\\", "/"))

    option = root.find("option")
    if option is None:
        option = ET.SubElement(root, "option")
    option.set("timestep", "0.002")
    option.set("gravity", "0 0 -9.81")

    _add_tabletop_if_missing(root)
    _ensure_panda_ee_site(root)
    return ET.tostring(root, encoding="unicode"), panda_xml.parent


def _source_for_task(composition: TaskCompositionSpec, agents, scene_composer=None):
    from scene import SceneSource

    build_scene_source = getattr(scene_composer, "build_scene_source", None)
    if build_scene_source is not None:
        return build_scene_source(composition, agents)
    if composition.task_uid == "empty-v1":
        if composition.agent_uids:
            xml, base_dir = _empty_tabletop_with_panda_xml(agents)
            return SceneSource.mjcf_string(
                xml,
                base_dir=base_dir,
                label="task-env-empty-tabletop-panda",
            ), "task_env_empty_tabletop_panda_v1"
        return SceneSource.mjcf_string(
            _EMPTY_TABLETOP_XML,
            label="task-env-empty-tabletop",
        ), "inline_empty_tabletop_v1"
    raise NotImplementedError(
        f"no Stage 1 scene composition adapter for {composition.task_uid}"
    )


def _build_scene_model(imported_scene, composition: TaskCompositionSpec, scene_composer=None):
    build_scene_model = getattr(scene_composer, "build_scene_model", None)
    if build_scene_model is not None:
        return build_scene_model(imported_scene, composition)
    return imported_scene.build_rigid_scene_model()


def _semantic_geom_names(source) -> tuple[str, ...]:
    """Return all authored MJCF geom names, including render-only geoms."""
    if getattr(source, "xml", None) is None:
        return ()
    root = ET.fromstring(source.xml)
    return tuple(
        name
        for geom in root.iter("geom")
        if (name := geom.get("name"))
    )


def _validate_external_assets(components) -> None:
    """Fail clearly when a repository/deployment asset prerequisite is absent."""

    missing: list[str] = []
    for component in components:
        manifest = component.asset_manifest()
        for path in manifest.mjcf_sources:
            if not path.is_file():
                missing.append(f"{manifest.owner_uid}: MJCF {path}")
        for path in manifest.asset_roots:
            if not path.is_dir():
                missing.append(f"{manifest.owner_uid}: asset root {path}")
    if missing:
        details = "; ".join(missing)
        raise FileNotFoundError(
            "TaskEnv external asset prerequisite missing; install or mount the "
            f"repository assets before building this environment: {details}"
        )


def _initial_state(scene_model, agents, references: TaskReferences) -> EpisodePhysicsState:
    joint_data = scene_model.joint_data
    n_qpos = int(joint_data.get("n_qpos", 0))
    n_dof = int(joint_data.get("n_dof", 0))
    n_act = int(joint_data.get("n_actuators", 0))
    qpos = np.asarray(
        joint_data.get("initial_qpos", np.zeros(max(n_qpos, 1))),
        dtype=np.float32,
    )[:n_qpos].copy()
    qvel = np.asarray(
        joint_data.get("initial_qvel", np.zeros(max(n_dof, 1))),
        dtype=np.float32,
    )[:n_dof].copy()
    ctrl = np.asarray(
        joint_data.get("initial_ctrl", np.zeros(max(n_act, 1))),
        dtype=np.float32,
    )[:n_act].copy()
    act = np.asarray(
        joint_data.get("initial_act", np.zeros(max(n_act, 1))),
        dtype=np.float32,
    )[:n_act].copy()

    for agent in agents:
        agent_ref = references.agents[agent.uid]
        named_positions = dict(agent.initial_state_spec().joint_positions)
        for joint_name, value in named_positions.items():
            joint_id = references.names.joints[joint_name]
            qpos_adr = int(scene_model.joint_data["jnt_qposadr"][joint_id])
            qpos[qpos_adr] = np.float32(value)
        if agent.uid == "panda-v1":
            ctrl[agent_ref.arm_actuator_ids] = qpos[agent_ref.arm_qpos_ids]
            gripper_ids = agent_ref.gripper_actuator_ids
            if gripper_ids.size:
                ctrl[gripper_ids] = agent_ref.ctrl_range[gripper_ids, 1]

    return EpisodePhysicsState(
        qpos=qpos,
        qvel=qvel,
        qacc=np.zeros(n_dof, dtype=np.float32),
        ctrl=ctrl,
        act=act,
    )


def compile_task_scene(
    *,
    composition: TaskCompositionSpec,
    scene,
    agents,
    objects,
    scene_composer=None,
) -> CompiledTaskScene:
    from scene import import_scene_source

    _validate_external_assets((*agents, *objects))
    source, adapter_name = _source_for_task(composition, agents, scene_composer)
    imported_scene = import_scene_source(source)
    scene_model = _build_scene_model(imported_scene, composition, scene_composer)
    # G4 场景导入不再暴露旧 loader_result；其 articulation 视图保留了
    # TaskEnv 编译期名称解析所需的 links/actuators 契约。
    loader_result = imported_scene.articulation
    references = resolve_task_references(
        loader_result=loader_result,
        scene_model=scene_model,
        semantic_geom_names=_semantic_geom_names(source),
        scene=scene,
        agents=agents,
        objects=objects,
    )
    initial_state = _initial_state(scene_model, agents, references)
    return CompiledTaskScene(
        imported_scene=imported_scene,
        loader_result=loader_result,
        scene_model=scene_model,
        references=references,
        initial_state=initial_state,
        composition_adapter=adapter_name,
    )


__all__ = ["CompiledTaskScene", "compile_task_scene"]
