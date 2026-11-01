"""Pinned robosuite MJCF defaults for the task-local LIBERO MuJoCo source."""
from __future__ import annotations

import hashlib
import json
import math
import xml.etree.ElementTree as ET

from bench_deploy.libero.objects.layout import FIXTURE_WORLD_POSES, TABLE_REGION_SITES


ROBOSUITE_REVISION = "fbee5844ff5632f5b5698e204ec5357ca50be0df"
LIBERO_REVISION = "8f1084e3132a39270c3a13ebe37270a43ece2a01"
ROBOT_MODEL_PROFILE_V3_ID = "libero-robosuite-panda-layout-seed19-compile-first-v3"
LIBERO_OFFICIAL_SOURCE_PLAN_SHA256 = "d01e83b8418636bccaa350ba99cab2c069439433577ec37921d517ac1cef0da7"
LIBERO_OFFICIAL_AUTHORED_MODEL_SHA256 = "bade99c39178af234cc0dd44d4f7c2facd3cbeb3b9a07d6a08d712a3b1dd842a"
LIBERO_OFFICIAL_REBASED_MODEL_SHA256 = "9faeed9185d08b2b3d26d45e950ef7eebeec7866b76edf8e8c390fc19ed8cd12"
LIBERO_OFFICIAL_TASK_UID = (
    "libero_spatial/pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate"
)

_BASE_COMPILER_DEFAULTS = {"angle": "radian", "inertiagrouprange": "0 0"}
_BASE_OPTION_DEFAULTS = {
    "cone": "elliptic",
    "density": "1.2",
    "impratio": "20",
    "viscosity": "0.00002",
    "integrator": "Euler",
}
_BASE_SIZE_DEFAULTS = {"nconmax": "5000", "njmax": "5000"}

def validate_libero_official_source_plan_v1(
    plan_bytes: bytes, raw_source_xml_bytes: bytes,
) -> dict[str, object]:
    """Validate the exact pinned LIBERO/robosuite compile-first model plan."""
    if type(plan_bytes) is not bytes or type(raw_source_xml_bytes) is not bytes:
        raise TypeError("official LIBERO source plan validation requires byte inputs")
    if hashlib.sha256(plan_bytes).hexdigest() != LIBERO_OFFICIAL_SOURCE_PLAN_SHA256:
        raise ValueError("official LIBERO source composition plan differs from its pinned bytes")
    if hashlib.sha256(raw_source_xml_bytes).hexdigest() != LIBERO_OFFICIAL_REBASED_MODEL_SHA256:
        raise ValueError("official LIBERO rebased model differs from its pinned source bytes")
    try:
        plan = json.loads(plan_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("official LIBERO source composition plan is not valid UTF-8 JSON") from exc
    expected_identity = {
        "authored_model_sha256": LIBERO_OFFICIAL_AUTHORED_MODEL_SHA256,
        "libero_revision": LIBERO_REVISION,
        "rebased_model_sha256": LIBERO_OFFICIAL_REBASED_MODEL_SHA256,
        "robosuite_revision": ROBOSUITE_REVISION,
        "seed": 19,
        "source_model_id": "libero-official-model-builder-v1",
        "task_uid": LIBERO_OFFICIAL_TASK_UID,
    }
    expected_output = {
        "composed_mjcf_bytes": len(raw_source_xml_bytes),
        "composed_mjcf_sha256": LIBERO_OFFICIAL_REBASED_MODEL_SHA256,
        "status": "SOURCE_MJCF_COMPOSED_NOT_NATIVE_COMPILED",
    }
    if (plan.get("schema_version") != "libero-official-source-composition-plan-v1"
            or plan.get("identity") != expected_identity
            or plan.get("output") != expected_output):
        raise ValueError("official LIBERO source plan identity/output differs from the pinned model")
    return plan


def _normalize_libero_robosuite_model_xml_v3(source_xml: bytes) -> tuple[bytes, dict[str, object]]:
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
    for body_name, pose in FIXTURE_WORLD_POSES.items():
        matches = [body for body in worldbody.iter("body") if body.get("name") == body_name]
        if len(matches) != 1:
            raise ValueError(f"pinned LIBERO scene requires exactly one {body_name}; found {len(matches)}")
        body = matches[0]
        values = {}
        for field_name, expected_values in pose.items():
            actual = body.get(field_name)
            origin = (1.0, 0.0, 0.0, 0.0) if field_name == "quat" else (0.0, 0.0, 0.0)
            actual_values = origin if actual is None else tuple(float(item) for item in actual.split())
            if (len(actual_values) != len(origin)
                    or any(not math.isclose(a, b, rel_tol=0.0, abs_tol=1.0e-12)
                           for a, b in zip(actual_values, origin, strict=True))):
                raise ValueError(
                    f"LIBERO compile-first profile requires {body_name}.{field_name} at its authored origin"
                )
            values[field_name] = {
                "action": "preserved_at_compile_origin",
                "xml_value": actual,
                "post_compile_world_value": [float(value) for value in expected_values],
            }
            expected = " ".join(format(value, ".17g") for value in expected_values)
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

    table_matches = [
        body for body in worldbody.iter("body")
        if body.get("name") in {"main_table", "table"}
    ]
    if len(table_matches) != 1:
        raise ValueError(
            "pinned LIBERO scene requires exactly one main_table/table body; "
            f"found {len(table_matches)}"
        )
    table_body = table_matches[0]
    table_body_name = table_body.get("name")
    region_sites = {}
    for site_name, (position, size) in TABLE_REGION_SITES.items():
        matches = [site for site in root.iter("site") if site.get("name") == site_name]
        pos_text = " ".join(format(value, ".17g") for value in position)
        size_text = " ".join(format(value, ".17g") for value in size)
        if not matches:
            ET.SubElement(table_body, "site", {
                "name": site_name, "type": "box", "pos": pos_text, "size": size_text,
            })
            region_sites[site_name] = {"action": "added", "body": table_body_name, "type": "box",
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
        region_sites[site_name] = {"action": "preserved", "body": table_body_name, "type": "box",
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
        "schema_version": "libero-robosuite-model-transform-v3",
        "profile_id": ROBOT_MODEL_PROFILE_V3_ID,
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
        "fixture_pose_timing": "post_compile_reset_sample_v1",
        "official_task_construction_seed": 19,
        "task_region_site_source": "pinned LIBERO task model compiled with seed 19",
        "contact_decomposition_authored_flags": contact_geom_authored_flags,
    }
    return normalized, receipt


def normalize_libero_robosuite_model_xml_v3(source_xml: bytes) -> tuple[bytes, dict[str, object]]:
    """Normalize only the pinned compile-first LIBERO/robosuite model bytes."""
    if type(source_xml) is not bytes or hashlib.sha256(source_xml).hexdigest() != (
            LIBERO_OFFICIAL_REBASED_MODEL_SHA256):
        raise ValueError("LIBERO compile-first profile requires its pinned rebased model bytes")
    return _normalize_libero_robosuite_model_xml_v3(source_xml)


__all__ = [
    "LIBERO_REVISION", "ROBOSUITE_REVISION",
    "ROBOT_MODEL_PROFILE_V3_ID", "LIBERO_OFFICIAL_SOURCE_PLAN_SHA256",
    "LIBERO_OFFICIAL_AUTHORED_MODEL_SHA256", "LIBERO_OFFICIAL_REBASED_MODEL_SHA256",
    "LIBERO_OFFICIAL_TASK_UID", "validate_libero_official_source_plan_v1",
    "normalize_libero_robosuite_model_xml_v3",
]
