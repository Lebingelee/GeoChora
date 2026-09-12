"""编译场景的一次性稳定名称解析。"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Sequence

import numpy as np

from ..environment import ReferenceSpec


def _freeze_map(values: Mapping[str, int]) -> Mapping[str, int]:
    return MappingProxyType({str(name): int(index) for name, index in values.items()})


def _readonly_ids(values: Sequence[int]) -> np.ndarray:
    array = np.asarray(values, dtype=np.int32).copy()
    array.setflags(write=False)
    return array


@dataclass(frozen=True)
class SceneNameTable:
    bodies: Mapping[str, int]
    joints: Mapping[str, int]
    sites: Mapping[str, int]
    geoms: Mapping[str, int]
    actuators: Mapping[str, int]

    def __post_init__(self) -> None:
        for field_name in ("bodies", "joints", "sites", "geoms", "actuators"):
            object.__setattr__(self, field_name, _freeze_map(getattr(self, field_name)))


@dataclass(frozen=True)
class AgentReferences:
    uid: str
    arm_joint_ids: np.ndarray
    arm_qpos_ids: np.ndarray
    arm_dof_ids: np.ndarray
    arm_actuator_ids: np.ndarray
    gripper_joint_ids: np.ndarray
    gripper_qpos_ids: np.ndarray
    gripper_actuator_ids: np.ndarray
    eef_site_id: int
    hand_body_id: int
    ctrl_range: np.ndarray
    arm_joint_names: tuple[str, ...] = ()
    base_body_id: int = -1
    base_body_name: str = ""
    eef_site_name: str = ""
    # Generic articulated-agent projection.  The historical arm/gripper
    # fields remain for Panda controllers; these additive fields let a
    # non-arm agent expose its complete local joint/actuator layout without
    # making the public reference resolver robot-specific.
    joint_names: tuple[str, ...] = ()
    actuator_names: tuple[str, ...] = ()
    body_ids: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.int32))
    site_ids: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.int32))

    def __post_init__(self) -> None:
        for name in (
            "arm_joint_ids",
            "arm_qpos_ids",
            "arm_dof_ids",
            "arm_actuator_ids",
            "gripper_joint_ids",
            "gripper_qpos_ids",
            "gripper_actuator_ids",
            "body_ids",
            "site_ids",
        ):
            object.__setattr__(self, name, _readonly_ids(getattr(self, name)))
        ctrl_range = np.asarray(self.ctrl_range, dtype=np.float32).copy()
        ctrl_range.setflags(write=False)
        object.__setattr__(self, "ctrl_range", ctrl_range)
        arm_joint_names = tuple(str(name).strip() for name in self.arm_joint_names)
        if arm_joint_names and len(arm_joint_names) != len(self.arm_joint_ids):
            raise ValueError("arm_joint_names must match arm_joint_ids")
        if any(not name for name in arm_joint_names):
            raise ValueError("arm_joint_names cannot contain empty names")
        object.__setattr__(self, "arm_joint_names", arm_joint_names)
        joint_names = tuple(str(name).strip() for name in self.joint_names)
        actuator_names = tuple(str(name).strip() for name in self.actuator_names)
        if any(not name for name in (*joint_names, *actuator_names)):
            raise ValueError("generic agent reference names cannot be empty")
        object.__setattr__(self, "joint_names", joint_names)
        object.__setattr__(self, "actuator_names", actuator_names)


@dataclass(frozen=True)
class ObjectReferences:
    uid: str
    body_ids: np.ndarray
    joint_ids: np.ndarray
    site_ids: np.ndarray
    geom_ids: np.ndarray
    qpos_ids: np.ndarray

    def __post_init__(self) -> None:
        for name in ("body_ids", "joint_ids", "site_ids", "geom_ids", "qpos_ids"):
            object.__setattr__(self, name, _readonly_ids(getattr(self, name)))


@dataclass(frozen=True)
class TaskReferences:
    names: SceneNameTable
    agents: Mapping[str, AgentReferences]
    objects: Mapping[str, ObjectReferences]

    def __post_init__(self) -> None:
        object.__setattr__(self, "agents", MappingProxyType(dict(self.agents)))
        object.__setattr__(self, "objects", MappingProxyType(dict(self.objects)))


def _name_map(values: Sequence[str], kind: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for index, value in enumerate(values):
        name = str(value)
        if not name:
            continue
        if name in result:
            raise ValueError(f"duplicate compiled {kind} name: {name}")
        result[name] = index
    return result


def _flatten_names(loader_result) -> tuple[list[str], list[str], list[str], list[str]]:
    """Read name-bearing articulation data from legacy or G4 scene imports."""
    articulation = getattr(loader_result, "articulation", loader_result)
    body_names: list[str] = []
    joint_names: list[str] = []
    site_names: list[str] = []
    for link in articulation.links:
        body_names.append(str(link.name))
        joint_names.extend(str(joint.name) for joint in link.joints)
        site_names.extend(str(site.name) for site in link.sites)
    actuator_names = [
        str(actuator.name) for actuator in articulation.actuators
    ]
    return body_names, joint_names, site_names, actuator_names


def _require_spec(names: SceneNameTable, spec: ReferenceSpec, owner_uid: str) -> None:
    for field_name, table_name in (
        ("body_names", "bodies"),
        ("joint_names", "joints"),
        ("site_names", "sites"),
        ("geom_names", "geoms"),
        ("actuator_names", "actuators"),
    ):
        table = getattr(names, table_name)
        missing = [name for name in getattr(spec, field_name) if name not in table]
        if missing:
            raise KeyError(
                f"{owner_uid} has unresolved {table_name}: {', '.join(missing)}"
            )


def resolve_task_references(
    *,
    loader_result,
    scene_model,
    scene,
    agents,
    objects,
    semantic_geom_names: Sequence[str] = (),
) -> TaskReferences:
    body_names, joint_names, site_names, actuator_names = _flatten_names(loader_result)
    geom_names = list(scene_model.joint_data.get("geom_names", ()))
    geom_names.extend(name for name in semantic_geom_names if name not in geom_names)
    names = SceneNameTable(
        bodies=_name_map(body_names, "body"),
        joints=_name_map(joint_names, "joint"),
        sites=_name_map(site_names, "site"),
        geoms=_name_map(geom_names, "geom"),
        actuators=_name_map(actuator_names, "actuator"),
    )
    _require_spec(names, scene.reference_spec(), scene.uid)
    for component in (*agents, *objects):
        _require_spec(names, component.reference_spec(), component.uid)

    joint_data = scene_model.joint_data
    qpos_adr = np.asarray(joint_data["jnt_qposadr"], dtype=np.int32)
    dof_adr = np.asarray(joint_data["jnt_dofadr"], dtype=np.int32)
    ctrl_range = np.asarray(joint_data["actuator_ctrlrange"], dtype=np.float32)

    agent_refs: dict[str, AgentReferences] = {}
    for agent in agents:
        spec = agent.reference_spec()
        if agent.uid == "panda-v1":
            # Preserve the Stage 1 Panda controller layout exactly.
            arm_joint_names = tuple(f"joint{i}" for i in range(1, 8))
            gripper_joint_names = ("finger_joint1", "finger_joint2")
            arm_joint_ids = [names.joints[name] for name in arm_joint_names]
            gripper_joint_ids = [names.joints[name] for name in gripper_joint_names]
            arm_actuator_ids = [names.actuators[f"actuator{i}"] for i in range(1, 8)]
            gripper_actuator_ids = [names.actuators["actuator8"]]
            agent_refs[agent.uid] = AgentReferences(
                uid=agent.uid,
                arm_joint_ids=arm_joint_ids,
                arm_qpos_ids=qpos_adr[arm_joint_ids],
                arm_dof_ids=dof_adr[arm_joint_ids],
                arm_actuator_ids=arm_actuator_ids,
                gripper_joint_ids=gripper_joint_ids,
                gripper_qpos_ids=qpos_adr[gripper_joint_ids],
                gripper_actuator_ids=gripper_actuator_ids,
                eef_site_id=names.sites["nutassembly_ee_site"],
                hand_body_id=names.bodies["hand"],
                ctrl_range=ctrl_range,
                arm_joint_names=arm_joint_names,
                base_body_id=names.bodies["link0"],
                base_body_name="link0",
                eef_site_name="nutassembly_ee_site",
                joint_names=tuple(spec.joint_names),
                actuator_names=tuple(spec.actuator_names),
                body_ids=[names.bodies[name] for name in spec.body_names],
                site_ids=[names.sites[name] for name in spec.site_names],
            )
            continue

        # Generic articulated-agent projection.  Agent-specific semantics
        # (observation/reward/action ordering) stay in the private task; the
        # compiler only resolves stable names and qpos/dof addresses.
        joint_ids = [names.joints[name] for name in spec.joint_names]
        actuator_ids = [names.actuators[name] for name in spec.actuator_names]
        layout_factory = getattr(agent, "reference_layout", None)
        layout = layout_factory() if callable(layout_factory) else {}
        layout = dict(layout or {})
        body_names_for_layout = tuple(spec.body_names)
        site_names_for_layout = tuple(spec.site_names)
        base_body_name = str(
            layout.get(
                "base_body_name",
                body_names_for_layout[0] if body_names_for_layout else "",
            )
        )
        eef_site_name = str(
            layout.get(
                "eef_site_name",
                site_names_for_layout[0] if site_names_for_layout else "",
            )
        )
        agent_refs[agent.uid] = AgentReferences(
            uid=agent.uid,
            arm_joint_ids=joint_ids,
            arm_qpos_ids=qpos_adr[joint_ids],
            arm_dof_ids=dof_adr[joint_ids],
            arm_actuator_ids=actuator_ids,
            gripper_joint_ids=(),
            gripper_qpos_ids=(),
            gripper_actuator_ids=(),
            eef_site_id=names.sites[eef_site_name] if eef_site_name else -1,
            hand_body_id=names.bodies[base_body_name] if base_body_name else -1,
            ctrl_range=ctrl_range,
            arm_joint_names=tuple(spec.joint_names),
            base_body_id=names.bodies[base_body_name] if base_body_name else -1,
            base_body_name=base_body_name,
            eef_site_name=eef_site_name,
            joint_names=tuple(spec.joint_names),
            actuator_names=tuple(spec.actuator_names),
            body_ids=[names.bodies[name] for name in spec.body_names],
            site_ids=[names.sites[name] for name in spec.site_names],
        )

    object_refs: dict[str, ObjectReferences] = {}
    for component in objects:
        spec = component.reference_spec()
        joint_ids = [names.joints[name] for name in spec.joint_names]
        object_refs[component.uid] = ObjectReferences(
            uid=component.uid,
            body_ids=[names.bodies[name] for name in spec.body_names],
            joint_ids=joint_ids,
            site_ids=[names.sites[name] for name in spec.site_names],
            geom_ids=[names.geoms[name] for name in spec.geom_names],
            qpos_ids=[qpos_adr[index] for index in joint_ids],
        )
    return TaskReferences(names=names, agents=agent_refs, objects=object_refs)


__all__ = [
    "AgentReferences",
    "ObjectReferences",
    "ReferenceSpec",
    "SceneNameTable",
    "TaskReferences",
    "resolve_task_references",
]
