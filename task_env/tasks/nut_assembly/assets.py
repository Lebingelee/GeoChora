"""Task-owned NutAssemblySquare MJCF composition."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET

from ...robots.panda import PANDA_ASSET_ROOT
from ...objects.nut_assembly import NUT_ASSET_ROOT


TABLE_HALF_SIZE = (0.28, 0.20, 0.01)
TABLE_TOP_Z = 0.462
PEG_HALF_HEIGHT = 0.06
PEG_Z = TABLE_TOP_Z + PEG_HALF_HEIGHT
PEG_X = 0.58
PEG_Y_OFFSET = 0.045
NUT_CONTACT_MARGIN = 1.0e-3
NUT_HALF_HEIGHT = 0.01
FRANKA_GRASP_TARGET_X = 0.4545
FRANKA_GRASP_TARGET_Y = -0.075
NUT_HANDLE_LOCAL_X = 0.054
NUT_HANDLE_WORLD_X_SIGN = -1.0
NUT_WORLD_QUAT = (0.0, 0.0, 0.0, 1.0)
NUT_WORLD_POS = (
    FRANKA_GRASP_TARGET_X - NUT_HANDLE_WORLD_X_SIGN * NUT_HANDLE_LOCAL_X,
    FRANKA_GRASP_TARGET_Y,
    TABLE_TOP_Z + NUT_HALF_HEIGHT + NUT_CONTACT_MARGIN,
)
NUT_MASS = 1.0
NUT_DIAG_INERTIA = (7.5e-4, 7.5e-4, 1.25e-3)
NUT_FREEJOINT_DAMPING = 2.0
NUT_FREEJOINT_ARMATURE = 0.03
NUT_CONTACT_FRICTION = "1.6 0.08 0.001"
GRIPPER_CONTACT_FRICTION = "4.0 0.20 0.01"
ARM_DOF = 7
ARM_FORCE_RANGE = 250.0
GRIPPER_FORCE_RANGE = 400.0
GRIPPER_OPEN_TENDON_LENGTH = 0.04
GRIPPER_SERVO_STIFFNESS = 5000.0
GRIPPER_CLOSE_DAMPING = 120.0
EE_SITE_NAME = "nutassembly_ee_site"


def _find_body(root: ET.Element, name: str) -> ET.Element:
    for body in root.iter("body"):
        if body.get("name") == name:
            return body
    raise KeyError(f"body {name!r} is required by NutAssembly builder")


def _load_xml(path: Path) -> ET.Element:
    if not path.is_file():
        raise FileNotFoundError(str(path))
    return ET.parse(path).getroot()


def _ensure_panda_compiler(root: ET.Element, panda_xml: Path) -> None:
    compiler = root.find("compiler")
    if compiler is None:
        compiler = ET.SubElement(root, "compiler")
    compiler.set("meshdir", str((panda_xml.parent / "assets").resolve()).replace("\\", "/"))


def _ensure_option(root: ET.Element) -> None:
    option = root.find("option")
    if option is None:
        option = ET.SubElement(root, "option")
    option.set("timestep", "0.002")
    option.set("gravity", "0 0 -9.81")


def _ensure_panda_ee_site(root: ET.Element) -> None:
    hand = _find_body(root, "hand")
    if hand.find(f"site[@name='{EE_SITE_NAME}']") is not None:
        return
    ET.SubElement(
        hand,
        "site",
        {
            "name": EE_SITE_NAME,
            "pos": "0 0 0.0584",
            "size": "0.000001",
            "group": "6",
            "rgba": "0 0 0 0",
        },
    )


def _ensure_panda_hand_collision_proxies(root: ET.Element) -> None:
    hand = _find_body(root, "hand")
    proxy_specs = (
        ("nutassembly_hand_palm_collision_proxy", "0.042 0.030 0.024", "0.000 0.000 0.030"),
        ("nutassembly_hand_wrist_collision_proxy", "0.030 0.026 0.030", "-0.032 0.000 0.016"),
        ("nutassembly_hand_knuckle_collision_proxy", "0.032 0.048 0.018", "0.030 0.000 0.058"),
    )
    existing = {geom.get("name") for geom in hand.findall("geom")}
    for name, size, pos in proxy_specs:
        if name in existing:
            continue
        ET.SubElement(
            hand,
            "geom",
            {
                "name": name,
                "type": "box",
                "size": size,
                "pos": pos,
                "group": "3",
                "contype": "1",
                "conaffinity": "1",
                "condim": "4",
                "friction": GRIPPER_CONTACT_FRICTION,
                "rgba": "0.23 0.27 0.30 0.35",
            },
        )


def _strengthen_panda_arm_actuators(root: ET.Element) -> None:
    actuator = root.find("actuator")
    if actuator is None:
        return
    for actuator_id in range(1, ARM_DOF + 1):
        arm_actuator = actuator.find(f"general[@name='actuator{actuator_id}']")
        if arm_actuator is not None:
            arm_actuator.set("forcerange", f"{-ARM_FORCE_RANGE:g} {ARM_FORCE_RANGE:g}")


def _strengthen_panda_gripper_actuator(root: ET.Element) -> None:
    actuator = root.find("actuator")
    if actuator is None:
        return
    gripper = actuator.find("general[@name='actuator8']")
    if gripper is None:
        return
    gripper_gain = GRIPPER_SERVO_STIFFNESS * GRIPPER_OPEN_TENDON_LENGTH / 255.0
    gripper.set("gainprm", f"{gripper_gain:.12g} 0 0")
    gripper.set("forcerange", f"{-GRIPPER_FORCE_RANGE:g} {GRIPPER_FORCE_RANGE:g}")
    gripper.set("biasprm", f"0 {-GRIPPER_SERVO_STIFFNESS:g} {-GRIPPER_CLOSE_DAMPING:g}")


def _add_tabletop(root: ET.Element) -> None:
    worldbody = root.find("worldbody")
    if worldbody is None:
        raise KeyError("Panda MJCF does not contain worldbody")
    existing = worldbody.find("body[@name='grasp_table']")
    if existing is not None:
        worldbody.remove(existing)
    table = ET.SubElement(
        worldbody,
        "body",
        {
            "name": "grasp_table",
            "pos": f"0.5545 0 {TABLE_TOP_Z - TABLE_HALF_SIZE[2]}",
        },
    )
    ET.SubElement(
        table,
        "geom",
        {
            "name": "grasp_table_geom",
            "type": "box",
            "size": "{} {} {}".format(*TABLE_HALF_SIZE),
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
            "size": "{} {} {}".format(*TABLE_HALF_SIZE),
            "contype": "0",
            "conaffinity": "0",
            "group": "2",
            "mass": "0",
            "rgba": "0.34 0.39 0.42 1",
        },
    )


def _make_square_nut_body(square_nut: ET.Element) -> ET.Element:
    source_container = square_nut.find("worldbody/body")
    if source_container is None:
        raise KeyError("square-nut.xml must contain worldbody/body")
    source_body = source_container.find("body")
    if source_body is None:
        raise KeyError("square-nut.xml must contain nested collision body")

    body = ET.Element(
        "body",
        name="SquareNut",
        pos="{} {} {}".format(*NUT_WORLD_POS),
        quat="{} {} {} {}".format(*NUT_WORLD_QUAT),
    )
    body.append(
        ET.Element(
            "inertial",
            mass=f"{NUT_MASS}",
            pos="0 0 0",
            diaginertia="{} {} {}".format(*NUT_DIAG_INERTIA),
        )
    )
    body.append(
        ET.Element(
            "freejoint",
            name="SquareNut_joint",
            damping=f"{NUT_FREEJOINT_DAMPING}",
            armature=f"{NUT_FREEJOINT_ARMATURE}",
        )
    )
    source_children = list(source_body)
    for collision_id, child in enumerate(source_children):
        if child.tag == "geom":
            child.set("name", f"SquareNut_collision_{collision_id}")
            child.attrib.pop("material", None)
            child.attrib.pop("density", None)
            child.attrib.pop("mass", None)
            child.set("margin", f"{NUT_CONTACT_MARGIN}")
            child.set("friction", NUT_CONTACT_FRICTION)
        body.append(child)
    for visual_id, child in enumerate(source_children):
        if child.tag != "geom":
            continue
        visual = deepcopy(child)
        visual.set("name", f"SquareNut_visual_{visual_id}")
        visual.set("group", "2")
        visual.set("contype", "0")
        visual.set("conaffinity", "0")
        visual.set("mass", "0")
        visual.attrib.pop("material", None)
        visual.set("rgba", "0.95 0.60 0.18 1")
        body.append(visual)
    for child in list(source_container):
        if child.tag == "site":
            body.append(child)
    return body


def _add_pegs_and_nut(root: ET.Element) -> None:
    worldbody = root.find("worldbody")
    if worldbody is None:
        raise KeyError("Panda MJCF does not contain worldbody")
    for body in list(worldbody):
        if body.tag == "body" and body.get("name") in {"peg1", "peg2", "SquareNut"}:
            worldbody.remove(body)
    peg1 = ET.SubElement(worldbody, "body", name="peg1", pos=f"{PEG_X} {PEG_Y_OFFSET} {PEG_Z}")
    ET.SubElement(
        peg1,
        "geom",
        name="square_peg_collision",
        type="box",
        size=f"0.016 0.016 {PEG_HALF_HEIGHT}",
        group="0",
        friction="1 0.005 0.0001",
        rgba="0.93 0.54 0.18 1",
    )
    ET.SubElement(
        peg1,
        "geom",
        name="square_peg_visual",
        type="box",
        size=f"0.016 0.016 {PEG_HALF_HEIGHT}",
        group="2",
        contype="0",
        conaffinity="0",
        mass="0",
        rgba="0.93 0.54 0.18 1",
    )
    peg2 = ET.SubElement(worldbody, "body", name="peg2", pos=f"{PEG_X} {-PEG_Y_OFFSET} {PEG_Z}")
    ET.SubElement(
        peg2,
        "geom",
        name="round_peg_collision",
        type="cylinder",
        size=f"0.02 {PEG_HALF_HEIGHT}",
        group="0",
        friction="1 0.005 0.0001",
        rgba="0.18 0.48 0.66 1",
    )
    ET.SubElement(
        peg2,
        "geom",
        name="round_peg_visual",
        type="cylinder",
        size=f"0.02 {PEG_HALF_HEIGHT}",
        group="2",
        contype="0",
        conaffinity="0",
        mass="0",
        rgba="0.18 0.48 0.66 1",
    )
    square_nut = _load_xml(NUT_ASSET_ROOT / "square-nut.xml")
    worldbody.append(_make_square_nut_body(square_nut))


def _ensure_positive_auxiliary_body_inertials(root: ET.Element) -> None:
    for body in root.iter("body"):
        if body.findall("geom"):
            continue
        inertial = body.find("inertial")
        if inertial is None:
            inertial = ET.Element("inertial", pos="0 0 0")
            body.insert(0, inertial)
        try:
            mass = float(inertial.get("mass", "0"))
        except ValueError:
            mass = 0.0
        if mass > 0.0:
            continue
        inertial.set("mass", "1e-4")
        inertial.set("diaginertia", "1e-6 1e-6 1e-6")
        inertial.set("pos", inertial.get("pos") or "0 0 0")


def _enable_scene_collision_geoms(root: ET.Element) -> None:
    for geom in root.iter("geom"):
        name = (geom.get("name") or "").lower()
        class_name = (geom.get("class") or "").lower()
        group = geom.get("group")
        contype = geom.get("contype")
        conaffinity = geom.get("conaffinity")
        is_visual = class_name == "visual" or group in ("1", "2") or "visual" in name
        is_visual = is_visual or (contype == "0" and conaffinity == "0")
        if is_visual:
            geom.set("contype", "0")
            geom.set("conaffinity", "0")
            continue
        geom.set("contype", "1")
        geom.set("conaffinity", "1")
        if group is None:
            geom.set("group", "0")


def _increase_panda_gripper_collision_friction(root: ET.Element) -> None:
    def _visit_body(body: ET.Element) -> None:
        body_name = (body.get("name") or "").lower()
        for geom in body.findall("geom"):
            geom_name = (geom.get("name") or "").lower()
            class_name = (geom.get("class") or "").lower()
            group = geom.get("group")
            contype = geom.get("contype")
            conaffinity = geom.get("conaffinity")
            is_visual = class_name == "visual" or group in ("1", "2") or "visual" in geom_name
            is_visual = is_visual or (contype == "0" and conaffinity == "0")
            if is_visual:
                continue
            is_gripper_geom = (
                "finger" in body_name
                or "finger" in geom_name
                or "fingertip" in geom_name
                or "pad" in geom_name
                or "hand" in body_name
                or "hand" in geom_name
                or "gripper" in body_name
                or "gripper" in geom_name
            )
            if is_gripper_geom:
                geom.set("friction", GRIPPER_CONTACT_FRICTION)
                geom.set("condim", "4")
        for child in body.findall("body"):
            _visit_body(child)

    worldbody = root.find("worldbody")
    if worldbody is None:
        return
    for body in worldbody.findall("body"):
        _visit_body(body)


def _apply_render_colors(root: ET.Element) -> None:
    def _color_for_geom(body_name: str, geom: ET.Element) -> str | None:
        geom_name = geom.get("name") or ""
        if body_name == "SquareNut":
            return "0.95 0.60 0.18 1"
        if body_name == "peg1":
            return "0.93 0.54 0.18 1"
        if body_name == "peg2":
            return "0.18 0.48 0.66 1"
        if body_name == "grasp_table" or "table_" in geom_name:
            return "0.34 0.39 0.42 1"
        if "finger" in geom_name or "hand" in geom_name:
            return "0.23 0.27 0.30 1"
        return None

    def _visit_body(body: ET.Element) -> None:
        body_name = body.get("name") or ""
        for geom in body.findall("geom"):
            rgba = _color_for_geom(body_name, geom)
            if rgba is not None:
                geom.set("rgba", rgba)
        for child in body.findall("body"):
            _visit_body(child)

    worldbody = root.find("worldbody")
    if worldbody is not None:
        for body in worldbody.findall("body"):
            _visit_body(body)


class NutAssemblySceneComposer:
    """Build the task-owned NutAssembly source and solver scene model."""

    adapter_name = "task_env_nutassembly_owned_builder_v1"
    source_label = "task-env-nut-assembly-square"

    def build_scene_source(self, composition, agents):
        del composition, agents
        from scene import SceneSource

        xml, base_dir = build_nut_assembly_model_xml()
        return (
            SceneSource.mjcf_string(
                xml,
                base_dir=base_dir,
                label=self.source_label,
            ),
            self.adapter_name,
        )

    def build_scene_model(self, imported_scene, composition):
        del composition
        # Match the stable NutAssembly demo physics path: keep imported meshes
        # for rendering, but use primitive/proxy collision geometry in solver.
        return imported_scene.build_rigid_scene_model(use_imported_meshes=False)


def build_nut_assembly_model_xml() -> tuple[str, Path]:
    """Build the task-owned NutAssemblySquare MJCF string."""

    panda_xml = PANDA_ASSET_ROOT / "panda.xml"
    root = _load_xml(panda_xml)
    _ensure_panda_compiler(root, panda_xml)
    _ensure_option(root)
    _ensure_panda_ee_site(root)
    _ensure_panda_hand_collision_proxies(root)
    _strengthen_panda_arm_actuators(root)
    _strengthen_panda_gripper_actuator(root)
    _add_tabletop(root)
    _add_pegs_and_nut(root)
    _ensure_positive_auxiliary_body_inertials(root)
    _enable_scene_collision_geoms(root)
    _increase_panda_gripper_collision_friction(root)
    _apply_render_colors(root)
    return ET.tostring(root, encoding="unicode"), panda_xml.parent


__all__ = [
    "EE_SITE_NAME",
    "FRANKA_GRASP_TARGET_X",
    "FRANKA_GRASP_TARGET_Y",
    "NUT_CONTACT_MARGIN",
    "NUT_HALF_HEIGHT",
    "NUT_HANDLE_LOCAL_X",
    "NUT_WORLD_POS",
    "NUT_WORLD_QUAT",
    "PEG_HALF_HEIGHT",
    "PEG_X",
    "PEG_Y_OFFSET",
    "PEG_Z",
    "TABLE_TOP_Z",
    "NutAssemblySceneComposer",
    "build_nut_assembly_model_xml",
]
