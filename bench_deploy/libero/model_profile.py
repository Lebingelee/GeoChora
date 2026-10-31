"""Pinned robosuite MJCF defaults for the task-local LIBERO MuJoCo source."""
from __future__ import annotations

import hashlib
import math
import xml.etree.ElementTree as ET


ROBOT_MODEL_PROFILE_ID = "libero-robosuite-panda-layout-seed19-v2"
ROBOSUITE_REVISION = "fbee5844ff5632f5b5698e204ec5357ca50be0df"
LIBERO_REVISION = "8f1084e3132a39270c3a13ebe37270a43ece2a01"

_BASE_COMPILER_DEFAULTS = {"angle": "radian", "inertiagrouprange": "0 0"}
_BASE_OPTION_DEFAULTS = {
    "cone": "elliptic",
    "density": "1.2",
    "impratio": "20",
    "viscosity": "0.00002",
    "integrator": "Euler",
}
_BASE_SIZE_DEFAULTS = {"nconmax": "5000", "njmax": "5000"}
_FIXTURE_WORLD_POSES = {
    "wooden_cabinet_1_main": {
        "pos": (0.032160686061349086, -0.26769535926827864, 0.905),
        "quat": (0.21813924162729167, 0.0, 0.0, 0.9759176559844944),
    },
    "flat_stove_1_main": {
        "pos": (-0.4146303298573933, -0.13499687702793547, 0.905),
        "quat": (1.0, 0.0, 0.0, 0.0),
    },
}
_TABLE_REGION_SITES = {
    "main_table_between_plate_ramekin_region": ((-0.05, 0.20, 0.02), (0.01, 0.01, 0.007)),
    "main_table_box_region": ((0.07, 0.03, 0.02), (0.01, 0.01, 0.007)),
    "main_table_cabinet_region": ((0.03, -0.27, 0.02), (0.01, 0.01, 0.007)),
    "main_table_next_to_box_region": ((0.13, -0.07, 0.02), (0.01, 0.01, 0.007)),
    "main_table_next_to_plate_region": ((0.01, 0.31, 0.02), (0.01, 0.01, 0.007)),
    "main_table_next_to_ramekin_region": ((-0.18, 0.32, 0.02), (0.01, 0.01, 0.007)),
    "main_table_plate_region": ((0.06, 0.20, 0.02), (0.01, 0.01, 0.007)),
    "main_table_ramekin_region": ((-0.20, 0.20, 0.02), (0.01, 0.01, 0.007)),
    "main_table_stove_region": ((-0.41, -0.14, 0.02), (0.01, 0.01, 0.007)),
    "main_table_table_center": ((-0.075, 0.0, 0.02), (0.025, 0.01, 0.007)),
    "main_table_table_front": ((0.20, 0.0, 0.02), (0.01, 0.01, 0.007)),
}


def normalize_libero_robosuite_model_xml_v2(source_xml: bytes) -> tuple[bytes, dict[str, object]]:
    """Apply pinned robosuite defaults and the seed-19 LIBERO scene layout.

    The pinned source MJCF remains the transform input. Values already authored
    in that MJCF are retained when they agree with robosuite's ``force=False``
    defaults; conflicting explicit values fail closed.
    """
    if type(source_xml) is not bytes:
        raise TypeError("LIBERO model-profile input must be immutable XML bytes")
    try:
        root = ET.fromstring(source_xml)
    except ET.ParseError as exc:
        raise ValueError("LIBERO model-profile input is not valid MJCF XML") from exc
    if root.tag != "mujoco":
        raise ValueError("LIBERO model-profile input must have a mujoco root")

    option = root.find("option")
    if option is None:
        raise ValueError("LIBERO composed MJCF omitted the root option element")
    compiler = root.find("compiler")
    if compiler is None:
        raise ValueError("LIBERO composed MJCF omitted the root compiler element")
    size = root.find("size")
    if size is None:
        size = ET.Element("size")
        children = list(root)
        insertion = next((i for i, child in enumerate(children)
                          if child.tag in {"visual", "statistic", "default", "asset", "worldbody"}),
                         len(children))
        root.insert(insertion, size)

    applied: dict[str, object] = {
        "compiler": {}, "option": {}, "size": {}, "panda_arm_joints": {},
        "fixture_world_poses": {},
    }

    def set_default(element: ET.Element, name: str, expected: str, *, numeric: bool = False) -> None:
        actual = element.get(name)
        if actual is None:
            element.set(name, expected)
            bucket = "compiler" if element is compiler else "option" if element is option else "size"
            applied[bucket][name] = expected
            return
        if numeric:
            try:
                equal = math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=1.0e-12)
            except ValueError:
                equal = False
        else:
            equal = actual.strip().casefold() == expected.casefold()
        if not equal:
            raise ValueError(
                f"explicit MJCF {element.tag}.{name}={actual!r} conflicts with pinned robosuite default {expected!r}"
            )

    for name, expected in _BASE_COMPILER_DEFAULTS.items():
        set_default(compiler, name, expected)
    for name, expected in _BASE_OPTION_DEFAULTS.items():
        set_default(option, name, expected, numeric=name in {"density", "impratio", "viscosity"})
    for name, expected in _BASE_SIZE_DEFAULTS.items():
        set_default(size, name, expected, numeric=True)

    all_joints = [element for element in root.iter("joint")]
    arm_joint_rows = []
    for index in range(1, 8):
        name = f"robot0_joint{index}"
        matches = [joint for joint in all_joints if joint.get("name") == name]
        if len(matches) != 1:
            raise ValueError(f"pinned Panda model requires exactly one {name}; found {len(matches)}")
        joint = matches[0]
        if joint.get("type", "hinge") != "hinge":
            raise ValueError(f"pinned Panda arm joint is not a hinge: {name}")
        defaults = {
            "frictionloss": "0.1",
            "damping": "0.1",
            "armature": format(5.0 / index, ".17g"),
        }
        fields = {}
        for field_name, expected in defaults.items():
            actual = joint.get(field_name)
            if actual is None:
                joint.set(field_name, expected)
                fields[field_name] = {"applied": expected}
            else:
                fields[field_name] = {"preserved": actual}
        arm_joint_rows.append({"joint": name, "fields": fields})
    applied["panda_arm_joints"] = {row["joint"]: row["fields"] for row in arm_joint_rows}

    worldbody = root.find("worldbody")
    if worldbody is None:
        raise ValueError("LIBERO composed MJCF omitted the root worldbody")
    fixture_rows = {}
    for body_name, pose in _FIXTURE_WORLD_POSES.items():
        matches = [body for body in worldbody.iter("body") if body.get("name") == body_name]
        if len(matches) != 1:
            raise ValueError(f"pinned LIBERO scene requires exactly one {body_name}; found {len(matches)}")
        body = matches[0]
        values = {}
        for field_name, expected_values in pose.items():
            expected = " ".join(format(value, ".17g") for value in expected_values)
            actual = body.get(field_name)
            if actual is None:
                body.set(field_name, expected)
                values[field_name] = {"applied": expected}
                continue
            try:
                actual_values = tuple(float(item) for item in actual.split())
            except ValueError as exc:
                raise ValueError(f"fixture {body_name}.{field_name} is not a numeric vector") from exc
            if (len(actual_values) != len(expected_values)
                    or any(not math.isclose(a, b, rel_tol=0.0, abs_tol=1.0e-12)
                           for a, b in zip(actual_values, expected_values, strict=True))):
                raise ValueError(f"fixture {body_name}.{field_name} conflicts with pinned LIBERO world pose")
            values[field_name] = {"preserved": actual}
        fixture_rows[body_name] = values
    applied["fixture_world_poses"] = fixture_rows

    table_matches = [body for body in worldbody.iter("body") if body.get("name") == "main_table"]
    if len(table_matches) != 1:
        raise ValueError(f"pinned candidate scene requires exactly one main_table; found {len(table_matches)}")
    table_body = table_matches[0]
    region_sites = {}
    for site_name, (position, size) in _TABLE_REGION_SITES.items():
        matches = [site for site in root.iter("site") if site.get("name") == site_name]
        pos_text = " ".join(format(value, ".17g") for value in position)
        size_text = " ".join(format(value, ".17g") for value in size)
        if not matches:
            ET.SubElement(table_body, "site", {
                "name": site_name, "type": "box", "pos": pos_text, "size": size_text,
            })
            region_sites[site_name] = {"action": "added", "body": "main_table", "type": "box",
                                       "pos": pos_text, "size": size_text}
            continue
        if len(matches) != 1:
            raise ValueError(f"pinned task region site is duplicated: {site_name}")
        site = matches[0]
        if site not in list(table_body.iter("site")):
            raise ValueError(f"pinned task region site is attached to the wrong body: {site_name}")
        if site.get("type", "ellipsoid") != "box":
            raise ValueError(f"pinned task region site has the wrong shape: {site_name}")
        for field_name, expected_values in (("pos", position), ("size", size)):
            actual_values = tuple(float(item) for item in site.get(field_name, "").split())
            if (len(actual_values) != len(expected_values)
                    or any(not math.isclose(a, b, rel_tol=0.0, abs_tol=1.0e-12)
                           for a, b in zip(actual_values, expected_values, strict=True))):
                raise ValueError(f"pinned task region site {site_name}.{field_name} differs")
        region_sites[site_name] = {"action": "preserved", "body": "main_table", "type": "box",
                                   "pos": site.get("pos"), "size": site.get("size")}
    applied["task_region_sites"] = region_sites

    contact_geoms = [geom for geom in root.iter("geom")
                     if geom.get("name", "").startswith("libero_contact_")]
    contact_names = [geom.get("name") for geom in contact_geoms]
    if len(set(contact_names)) != len(contact_names):
        raise ValueError("LIBERO contact decomposition contains duplicate geom names")
    contact_geom_authored_flags = {
        "count": len(contact_geoms),
        "explicitly_disabled_count": sum(
            geom.get("contype") == "0" and geom.get("conaffinity") == "0"
            for geom in contact_geoms
        ),
        "missing_contype_count": sum(geom.get("contype") is None for geom in contact_geoms),
        "missing_conaffinity_count": sum(geom.get("conaffinity") is None for geom in contact_geoms),
    }

    normalized = ET.tostring(root, encoding="utf-8", short_empty_elements=True)
    receipt: dict[str, object] = {
        "schema_version": "libero-robosuite-model-transform-v2",
        "profile_id": ROBOT_MODEL_PROFILE_ID,
        "libero_revision": LIBERO_REVISION,
        "robosuite_revision": ROBOSUITE_REVISION,
        "raw_source_xml_sha256": hashlib.sha256(source_xml).hexdigest(),
        "runtime_model_xml_sha256": hashlib.sha256(normalized).hexdigest(),
        "applied_defaults": applied,
        "world_defaults_source": "robosuite/models/assets/base.xml",
        "robot_defaults_source": "robosuite/models/robots/robot_model.py::RobotModel.__init__",
        "joint_default_policy": "force_false_preserve_authored_values_v1",
        "mjcf_option_integrator": "Euler",
        "fixture_pose_source": "pinned LIBERO task model compiled twice with Python/NumPy seed 19",
        "official_task_construction_seed": 19,
        "task_region_site_source": "pinned LIBERO task model compiled with seed 19",
        "contact_decomposition_authored_flags": contact_geom_authored_flags,
    }
    return normalized, receipt


__all__ = [
    "LIBERO_REVISION", "ROBOSUITE_REVISION", "ROBOT_MODEL_PROFILE_ID",
    "normalize_libero_robosuite_model_xml_v2",
]
