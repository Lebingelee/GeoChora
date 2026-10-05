"""Task-owned PickCube MJCF composition."""

from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from ...robots.panda import PANDA_ASSET_ROOT


TABLE_HALF_SIZE = (0.28, 0.20, 0.01)
TABLE_TOP_Z = 0.462
CUBE_HALF_SIZE = 0.025
CUBE_CONTACT_MARGIN = 1.0e-3
CUBE_WORLD_POS = (0.50, 0.0, TABLE_TOP_Z + CUBE_HALF_SIZE + CUBE_CONTACT_MARGIN)
CUBE_WORLD_QUAT = (1.0, 0.0, 0.0, 0.0)
CUBE_MASS = 0.08
CUBE_DIAG_INERTIA = (3.5e-5, 3.5e-5, 3.5e-5)
CUBE_FREEJOINT_DAMPING = 0.8
CUBE_FREEJOINT_ARMATURE = 0.01
CUBE_CONTACT_FRICTION = "1.8 0.10 0.002"
GRIPPER_CONTACT_FRICTION = "4.0 0.20 0.01"
ARM_DOF = 7
ARM_FORCE_RANGE = 250.0
GRIPPER_FORCE_RANGE = 5.0
GRIPPER_OPEN_TENDON_LENGTH = 0.04
GRIPPER_SERVO_STIFFNESS = 5000.0
GRIPPER_CLOSE_DAMPING = 120.0
EE_SITE_NAME = "nutassembly_ee_site"


def _find_body(root: ET.Element, name: str) -> ET.Element:
    for body in root.iter("body"):
        if body.get("name") == name:
            return body
    raise KeyError(f"body {name!r} is required by PickCube builder")


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
        ("pickcube_hand_palm_collision_proxy", "0.042 0.030 0.024", "0.000 0.000 0.030"),
        ("pickcube_hand_wrist_collision_proxy", "0.030 0.026 0.030", "-0.032 0.000 0.016"),
        ("pickcube_hand_knuckle_collision_proxy", "0.032 0.048 0.018", "0.030 0.000 0.058"),
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


def _add_cube(root: ET.Element) -> None:
    worldbody = root.find("worldbody")
    if worldbody is None:
        raise KeyError("Panda MJCF does not contain worldbody")
    existing = worldbody.find("body[@name='PickCube']")
    if existing is not None:
        worldbody.remove(existing)
    cube = ET.SubElement(
        worldbody,
        "body",
        {
            "name": "PickCube",
            "pos": "{} {} {}".format(*CUBE_WORLD_POS),
            "quat": "{} {} {} {}".format(*CUBE_WORLD_QUAT),
        },
    )
    ET.SubElement(
        cube,
        "inertial",
        {
            "mass": f"{CUBE_MASS}",
            "pos": "0 0 0",
            "diaginertia": "{} {} {}".format(*CUBE_DIAG_INERTIA),
        },
    )
    ET.SubElement(
        cube,
        "freejoint",
        {
            "name": "PickCube_joint",
            "damping": f"{CUBE_FREEJOINT_DAMPING}",
            "armature": f"{CUBE_FREEJOINT_ARMATURE}",
        },
    )
    ET.SubElement(
        cube,
        "geom",
        {
            "name": "PickCube_collision",
            "type": "box",
            "size": f"{CUBE_HALF_SIZE} {CUBE_HALF_SIZE} {CUBE_HALF_SIZE}",
            "group": "3",
            "margin": f"{CUBE_CONTACT_MARGIN}",
            "condim": "4",
            "friction": CUBE_CONTACT_FRICTION,
            "rgba": "0.15 0.55 0.82 1",
        },
    )
    ET.SubElement(
        cube,
        "geom",
        {
            "name": "PickCube_visual",
            "type": "box",
            "size": f"{CUBE_HALF_SIZE} {CUBE_HALF_SIZE} {CUBE_HALF_SIZE}",
            "group": "2",
            "contype": "0",
            "conaffinity": "0",
            "mass": "0",
            "rgba": "0.15 0.55 0.82 1",
        },
    )
    ET.SubElement(cube, "site", {"name": "PickCube_center_site", "pos": "0 0 0", "size": "0.004"})


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


class PickCubeSceneComposer:
    """Build the task-owned PickCube source and solver scene model."""

    adapter_name = "task_env_pickcube_owned_builder_v1"
    source_label = "task-env-pick-cube"

    def build_source_description(self):
        from ...assembly.source import TaskSceneSource

        xml, base_dir = build_pick_cube_model_xml()
        return TaskSceneSource(xml, base_dir, self.source_label)

    def build_scene_source(self, composition, agents):
        # Compatibility for existing scalar compiler; conversion belongs to provider.
        from ...runtime.sessions.geophys_source import native_scene_source

        return native_scene_source(self.build_source_description()), self.adapter_name

    def build_scene_model(self, imported_scene, composition):
        del composition
        return imported_scene.build_rigid_scene_model(use_imported_meshes=False)


def build_pick_cube_model_xml() -> tuple[str, Path]:
    """Build the task-owned PickCube MJCF string."""

    panda_xml = PANDA_ASSET_ROOT / "panda.xml"
    root = _load_xml(panda_xml)
    _ensure_panda_compiler(root, panda_xml)
    _ensure_option(root)
    _ensure_panda_ee_site(root)
    _ensure_panda_hand_collision_proxies(root)
    _strengthen_panda_arm_actuators(root)
    _strengthen_panda_gripper_actuator(root)
    _add_tabletop(root)
    _add_cube(root)
    _ensure_positive_auxiliary_body_inertials(root)
    _enable_scene_collision_geoms(root)
    _increase_panda_gripper_collision_friction(root)
    return ET.tostring(root, encoding="unicode"), panda_xml.parent


__all__ = [
    "CUBE_CONTACT_MARGIN",
    "CUBE_HALF_SIZE",
    "CUBE_WORLD_POS",
    "CUBE_WORLD_QUAT",
    "EE_SITE_NAME",
    "PickCubeSceneComposer",
    "TABLE_TOP_Z",
    "build_pick_cube_model_xml",
]
