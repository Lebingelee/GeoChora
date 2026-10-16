"""Reusable Panda/NutAssembly MJCF asset preparation and assembly owner.

Task composition and placement are supplied by the selected task definition;
this module only materializes the declared scene into a provider-neutral source.
"""
from __future__ import annotations
from copy import deepcopy
from math import isfinite
from pathlib import Path
import xml.etree.ElementTree as ET
from ..robots.panda import PANDA_ASSET_ROOT
from ..objects.nut_assembly import NUT_ASSET_ROOT
ARM_DOF = 7
ARM_FORCE_RANGE = 250.0
GRIPPER_FORCE_RANGE = 400.0
GRIPPER_OPEN_TENDON_LENGTH = 0.04
GRIPPER_SERVO_STIFFNESS = 5000.0
GRIPPER_CLOSE_DAMPING = 120.0

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


def _ensure_option(root: ET.Element, physics_dt: float) -> None:
    option = root.find("option")
    if option is None:
        option = ET.SubElement(root, "option")
    option.set("timestep", str(physics_dt))
    option.set("gravity", "0 0 -9.81")


def _ensure_panda_ee_site(root: ET.Element, ee_site_name: str) -> None:
    hand = _find_body(root, "hand")
    if hand.find(f"site[@name='{ee_site_name}']") is not None:
        return
    ET.SubElement(
        hand,
        "site",
        {
            "name": ee_site_name,
            "pos": "0 0 0.0584",
            "size": "0.000001",
            "group": "6",
            "rgba": "0 0 0 0",
        },
    )


def _ensure_panda_hand_collision_proxies(root: ET.Element, friction: str) -> None:
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
                "friction": friction,
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


def _add_tabletop(root: ET.Element, scene: dict) -> None:
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
            "pos": "{} {} {}".format(*scene["table_body_position"]),
        },
    )
    ET.SubElement(
        table,
        "geom",
        {
            "name": "grasp_table_geom",
            "type": "box",
            "size": "{} {} {}".format(*scene["table_half_size"]),
            "condim": "4",
            "friction": scene["table_friction"],
            "rgba": "0.34 0.39 0.42 1",
        },
    )
    ET.SubElement(
        table,
        "geom",
        {
            "name": "grasp_table_visual",
            "type": "box",
            "size": "{} {} {}".format(*scene["table_half_size"]),
            "contype": "0",
            "conaffinity": "0",
            "group": "2",
            "mass": "0",
            "rgba": "0.34 0.39 0.42 1",
        },
    )


def _make_square_nut_body(
    square_nut: ET.Element,
    scene: dict,
    *,
    mass_kg: float,
    diagonal_inertia_kg_m2: tuple[float, float, float],
) -> ET.Element:
    source_container = square_nut.find("worldbody/body")
    if source_container is None:
        raise KeyError("square-nut.xml must contain worldbody/body")
    source_body = source_container.find("body")
    if source_body is None:
        raise KeyError("square-nut.xml must contain nested collision body")

    body = ET.Element(
        "body",
        name="SquareNut",
        pos="{} {} {}".format(*scene["nut_pose"]["position"]),
        quat="{} {} {} {}".format(*scene["nut_pose"]["quaternion_wxyz"]),
    )
    body.append(
        ET.Element(
            "inertial",
            mass=format(float(mass_kg), ".12g"),
            pos="0 0 0",
            diaginertia=" ".join(format(float(v), ".12g") for v in diagonal_inertia_kg_m2),
        )
    )
    body.append(
        ET.Element(
            "freejoint",
            name="SquareNut_joint",
            damping=f"{scene['freejoint_damping']}",
            armature=f"{scene['freejoint_armature']}",
        )
    )
    source_children = list(source_body)
    for collision_id, child in enumerate(source_children):
        if child.tag == "geom":
            child.set("name", f"SquareNut_collision_{collision_id}")
            child.attrib.pop("material", None)
            child.attrib.pop("density", None)
            child.attrib.pop("mass", None)
            child.set("margin", f"{scene['nut_contact_margin_m']}")
            child.set("friction", scene["nut_friction"])
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


def _add_pegs_and_nut(
    root: ET.Element,
    scene: dict,
    *,
    nut_mass_kg: float,
    nut_diagonal_inertia_kg_m2: tuple[float, float, float],
) -> None:
    worldbody = root.find("worldbody")
    if worldbody is None:
        raise KeyError("Panda MJCF does not contain worldbody")
    for body in list(worldbody):
        if body.tag == "body" and body.get("name") in {"peg1", "peg2", "SquareNut"}:
            worldbody.remove(body)
    peg1 = ET.SubElement(worldbody, "body", name="peg1", pos="{} {} {}".format(*scene["square_peg_position"]))
    ET.SubElement(
        peg1,
        "geom",
        name="square_peg_collision",
        type="box",
        size=f"{scene['square_peg_half_width']} {scene['square_peg_half_width']} {scene['peg_half_height']}",
        group="0",
        friction=scene["peg_friction"],
        rgba="0.93 0.54 0.18 1",
    )
    ET.SubElement(
        peg1,
        "geom",
        name="square_peg_visual",
        type="box",
        size=f"{scene['square_peg_half_width']} {scene['square_peg_half_width']} {scene['peg_half_height']}",
        group="2",
        contype="0",
        conaffinity="0",
        mass="0",
        rgba="0.93 0.54 0.18 1",
    )
    peg2 = ET.SubElement(worldbody, "body", name="peg2", pos="{} {} {}".format(*scene["round_peg_position"]))
    ET.SubElement(
        peg2,
        "geom",
        name="round_peg_collision",
        type="cylinder",
        size=f"{scene['round_peg_radius']} {scene['peg_half_height']}",
        group="0",
        friction=scene["peg_friction"],
        rgba="0.18 0.48 0.66 1",
    )
    ET.SubElement(
        peg2,
        "geom",
        name="round_peg_visual",
        type="cylinder",
        size=f"{scene['round_peg_radius']} {scene['peg_half_height']}",
        group="2",
        contype="0",
        conaffinity="0",
        mass="0",
        rgba="0.18 0.48 0.66 1",
    )
    square_nut = _load_xml(NUT_ASSET_ROOT / "square-nut.xml")
    worldbody.append(_make_square_nut_body(
        square_nut, scene,
        mass_kg=nut_mass_kg,
        diagonal_inertia_kg_m2=nut_diagonal_inertia_kg_m2,
    ))


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


def _increase_panda_gripper_collision_friction(root: ET.Element, friction: str) -> None:
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
                geom.set("friction", friction)
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


def build_nut_assembly_model_xml(
    scene: dict,
    *,
    nut_mass_kg: float,
    nut_diagonal_inertia_kg_m2: tuple[float, float, float],
) -> tuple[str, Path]:
    """Build task-owned NutAssemblySquare MJCF for a declared asset profile."""

    values = (float(nut_mass_kg), *(float(v) for v in nut_diagonal_inertia_kg_m2))
    if len(values) != 4 or not all(isfinite(value) and value > 0.0 for value in values):
        raise ValueError("nut mass and diagonal inertia must be positive")

    panda_xml = PANDA_ASSET_ROOT / "panda.xml"
    root = _load_xml(panda_xml)
    _ensure_panda_compiler(root, panda_xml)
    _ensure_option(root, scene["physics_dt"])
    _ensure_panda_ee_site(root, scene["ee_site_name"])
    _ensure_panda_hand_collision_proxies(root, scene["gripper_friction"])
    _strengthen_panda_arm_actuators(root)
    _strengthen_panda_gripper_actuator(root)
    _add_tabletop(root, scene)
    _add_pegs_and_nut(
        root, scene,
        nut_mass_kg=values[0],
        nut_diagonal_inertia_kg_m2=tuple(values[1:]),
    )
    _ensure_positive_auxiliary_body_inertials(root)
    _enable_scene_collision_geoms(root)
    _increase_panda_gripper_collision_friction(root, scene["gripper_friction"])
    _apply_render_colors(root)
    return ET.tostring(root, encoding="unicode"), panda_xml.parent


__all__ = ["build_nut_assembly_model_xml"]
