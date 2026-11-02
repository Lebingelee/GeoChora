"""Stage 1 task-specific scene composition adapters."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
import hashlib
import json
from types import MappingProxyType
import xml.etree.ElementTree as ET

import numpy as np

from ..environment import EpisodePhysicsState, TaskCompositionSpec
from ..environment.task_source import TaskArtifactDeclarationV1
from .references import TaskReferences, resolve_task_references
from .logical_source import LogicalAssemblySourceProjectionV1, project_logical_assembly_source


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


@dataclass(frozen=True)
class CompiledReferenceTaskV1:
    """Provider-free Artifact/source facts produced from one task declaration."""

    artifact: object
    source: object
    controller: object | None = None

    def identity_fields(self, *, include_runtime_config_sha256: bool = True) -> dict[str, object]:
        return reference_task_identity_fields(
            self.artifact, self.source, self.controller,
            include_runtime_config_sha256=include_runtime_config_sha256,
        )


def reference_task_identity_fields(artifact, source, controller, *,
                                   include_runtime_config_sha256: bool = True) -> dict[str, object]:
    """Return the shared resolved identity facts for a compiled task route."""
    runtime_config = asdict(source.config)
    xml = source.scene_source.xml
    if not isinstance(xml, (str, bytes)):
        raise TypeError("reference source identity requires immutable XML bytes or text")
    xml_bytes = xml.encode("utf-8") if isinstance(xml, str) else xml
    result = {
        "artifact_sha256": artifact.identity_hash,
        "runtime_config": runtime_config,
        "source_xml_sha256": hashlib.sha256(xml_bytes).hexdigest(),
        "controller_identity": None if controller is None else controller.identity,
        "runtime_source_bindings": {
            name: dict(getattr(source, name))
            for name in ("joints", "bodies", "frames", "free_joints", "joint_targets")
        },
        "runtime_open_actuators": list(source.open_actuators),
    }
    if include_runtime_config_sha256:
        result["runtime_config_sha256"] = hashlib.sha256(json.dumps(
            runtime_config, sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
    return result


@dataclass(frozen=True)
class ReferenceTaskDeclarationV1:
    """Task data plus Core source bindings for a selected reference construction.

    The task owns scene bytes and semantic names; this declaration makes Core
    the single owner of Artifact validation and RuntimeSource binding.
    """

    artifact: TaskArtifactDeclarationV1
    composition: TaskCompositionSpec
    bodies: Mapping[str, str]
    frames: Mapping[str, str]
    free_joints: Mapping[str, str]
    joint_targets: Mapping[str, str]
    open_actuators: tuple[str, ...]
    joints: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if type(self.artifact) is not TaskArtifactDeclarationV1:
            raise TypeError("artifact must be a TaskArtifactDeclarationV1")
        if type(self.composition) is not TaskCompositionSpec:
            raise TypeError("composition must be a TaskCompositionSpec")
        if self.composition.task_uid != self.artifact.task_id:
            raise ValueError("task composition identity differs from Artifact declaration")
        for name in ("bodies", "frames", "free_joints", "joint_targets"):
            value = getattr(self, name)
            if not isinstance(value, Mapping):
                raise TypeError(f"{name} must be a mapping")
            if any(not isinstance(key, str) or not key or not isinstance(item, str) or not item
                   for key, item in value.items()):
                raise ValueError(f"{name} must map nonempty names to nonempty names")
            object.__setattr__(self, name, MappingProxyType(dict(value)))
        if self.joints is not None:
            if not isinstance(self.joints, Mapping):
                raise TypeError("joints must be a mapping when supplied")
            object.__setattr__(self, "joints", MappingProxyType(dict(self.joints)))
        actuators = tuple(self.open_actuators)
        if any(not isinstance(value, str) or not value for value in actuators):
            raise ValueError("open_actuators must contain nonempty names")
        object.__setattr__(self, "open_actuators", actuators)

    def compile_source(self, artifact, *, scene_source, config, **source_options):
        """Bind one declared Artifact to its source without native materialization."""
        expected = self.artifact.compile()
        if type(artifact) is not type(expected) or artifact.identity_hash != expected.identity_hash:
            raise ValueError("source Artifact does not match the task declaration")
        return compile_reference_source(
            artifact=artifact,
            scene_source=scene_source,
            composition=self.composition,
            config=config,
            bodies=self.bodies,
            frames=self.frames,
            free_joints=self.free_joints,
            joint_targets=self.joint_targets,
            open_actuators=self.open_actuators,
            **({"joints": self.joints} if self.joints is not None else {}),
            **source_options,
        )

    def compile(self, *, scene_source, config, controller_factory: Callable | None = None,
                **source_options) -> CompiledReferenceTaskV1:
        """Compile Artifact, source bindings and an optional pure controller."""
        artifact = self.artifact.compile()
        source = self.compile_source(
            artifact, scene_source=scene_source, config=config, **source_options,
        )
        controller = None
        if controller_factory is not None:
            if not callable(controller_factory):
                raise TypeError("controller_factory must be callable")
            controller = controller_factory(artifact, source)
        return CompiledReferenceTaskV1(artifact, source, controller)


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


def panda_entity_declaration():
    """Return the shared pinned Panda embodiment declaration."""
    from ..artifacts import EntityDefinition
    return EntityDefinition(
        'panda-v1', 'embodiment',
        'mujoco_menagerie/b846dd12bc459d776cccb3dee0b1d02acbf7a9c7/franka_emika_panda/panda.xml',
        ('panda-v1/base', 'panda-v1/ee'),
        (*tuple(f'panda-v1/joint{i}' for i in range(1, 8)),
         'panda-v1/finger_joint1', 'panda-v1/finger_joint2'),
        'referenced_articulation', 'arm_hand_finger_collision', {},
    )


_UNSET_COMPONENT = object()


def compile_reference_source(*, artifact, scene_source, composition, config,
                             bodies, frames, free_joints, joint_targets,
                             open_actuators, joints=None, scene=_UNSET_COMPONENT,
                             agents=_UNSET_COMPONENT, objects=_UNSET_COMPONENT, **source_options):
    """Bind semantic names and declared components to a provider-free source.

    Registered components are resolved from a TaskCompositionSpec by default.
    A benchmark with already compiled components can supply those values and a
    source-specific composition receipt explicitly.
    """
    from ..registry import make_agent, make_object, make_scene
    from ..runtime.sessions.source import RuntimeSource

    if joints is None:
        joints = {name: name.split("/", 1)[1] for name in artifact.initialization.joint_position}
    supplied = tuple(value is not _UNSET_COMPONENT for value in (scene, agents, objects))
    if any(supplied) and not all(supplied):
        raise ValueError("explicit source components must be supplied together")
    if not any(supplied):
        scene = make_scene(composition.scene_uid)
        agents = tuple(make_agent(uid) for uid in composition.agent_uids)
        objects = tuple(make_object(uid) for uid in composition.object_uids)
    return RuntimeSource(
        task_artifact_hash=artifact.identity_hash, scene_source=scene_source,
        joints=joints, bodies=bodies, frames=frames, free_joints=free_joints,
        joint_targets=joint_targets, open_actuators=tuple(open_actuators),
        composition=composition, config=config, scene=scene,
        agents=tuple(agents), objects=tuple(objects), **source_options,
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


__all__ = [
    "CompiledReferenceTaskV1",
    "CompiledTaskScene",
    "ReferenceTaskDeclarationV1",
    "compile_task_scene",
    "reference_task_identity_fields",
]
