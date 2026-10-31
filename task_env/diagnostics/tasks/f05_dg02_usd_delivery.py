"""Build the DG02 source-bound USD delivery from the frozen Panda inputs.

This is an offline asset task. It reads the protected Menagerie closure and the
accepted local composed USD, authors a versioned GeoChora semantic block, and
does not import a physics engine or start a solver.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

from task_env.assembly.assets import _source_closure_digest, _source_closure_manifest
from task_env.artifacts import AssetDefinition
from task_env.assembly.usd_delivery import load_usd_asset_delivery, variant_selection_hash


SCHEMA_V1 = "geochora.f05-source-semantics.v1"
SCHEMA_V2 = "geochora.f05-source-semantics.v2"
R009_STAGE_SHA256 = "f1c7a1a62deba337ce2f50100e53b1ebf1d677004b4fff3ecb5bf51d55692608"
SOURCE_CLOSURE_SHA256 = "a59a66d0b176cb6b2634d54cd20744752742b425e5524db1b865dda0eb3adf2a"
SOURCE_XML_SHA256 = "96ad67da03710f17f798c9478fd9e9efdf24a3bf8359f05e456dd9fb158ea273"
SOURCE_REVISION = "b846dd12bc459d776cccb3dee0b1d02acbf7a9c7"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return _sha(raw)


def _numbers(value: str, *, width: int, label: str) -> list[float]:
    items = [float(part) for part in value.split()]
    if len(items) != width or not all(math.isfinite(item) for item in items):
        raise ValueError(f"{label} must contain {width} finite values")
    return items


def _mjcf_parameters(value: str, *, width: int, label: str) -> list[float]:
    """Apply MuJoCo's scalar-to-parameter-vector rule for source actuator arrays."""
    items = [float(part) for part in value.split()]
    if not 1 <= len(items) <= width or not all(math.isfinite(item) for item in items):
        raise ValueError(f"{label} must contain one to {width} finite values")
    return items + [0.0] * (width - len(items))


def _source_semantics(xml_bytes: bytes, source_closure: str, *, version: int = 1) -> dict:
    """Resolve the Panda MJCF actuator defaults without loading MuJoCo."""
    root = ET.fromstring(xml_bytes)
    compiler = root.find("compiler")
    if compiler is None or compiler.get("angle") != "radian" or compiler.get("autolimits") != "true":
        raise ValueError("the frozen Panda MJCF compiler convention changed")
    defaults = root.find("default")
    panda_class = next((item for item in defaults.iter("default") if item.get("class") == "panda"), None) if defaults is not None else None
    general_defaults = panda_class.find("general") if panda_class is not None else None
    if general_defaults is None:
        raise ValueError("the frozen Panda actuator default class is missing")

    actuators = []
    actuator_section = root.find("actuator")
    if actuator_section is None:
        raise ValueError("the frozen Panda MJCF actuator section is missing")
    for node in actuator_section.findall("general"):
        effective = dict(general_defaults.attrib)
        effective.update(node.attrib)
        name = effective["name"]
        target_kind = "joint" if "joint" in effective else "tendon" if "tendon" in effective else None
        if target_kind is None:
            raise ValueError(f"unsupported source actuator target for {name}")
        target = effective[target_kind]
        ctrl_range = _numbers(effective["ctrlrange"], width=2, label=f"{name}.ctrlrange")
        force_range = _numbers(effective["forcerange"], width=2, label=f"{name}.forcerange")
        actuators.append({
            "name": name,
            "target_kind": target_kind,
            "target": target,
            "gear": _mjcf_parameters(effective.get("gear", "1"), width=6, label=f"{name}.gear"),
            "dyn_type": effective.get("dyntype", "none"),
            "gain_type": effective.get("gaintype", "fixed"),
            "bias_type": effective.get("biastype", "none"),
            "dyn_prm": _numbers(effective.get("dynprm", "1 0 0"), width=3, label=f"{name}.dynprm"),
            "gain_prm": _mjcf_parameters(effective.get("gainprm", "1"), width=3, label=f"{name}.gainprm"),
            "bias_prm": _mjcf_parameters(effective.get("biasprm", "0"), width=3, label=f"{name}.biasprm"),
            "ctrl_limited": "ctrlrange" in effective,
            "ctrl_range": ctrl_range,
            "force_limited": "forcerange" in effective,
            "force_range": force_range,
            "act_limited": "actrange" in effective,
            "act_range": _numbers(effective.get("actrange", "0 0"), width=2, label=f"{name}.actrange"),
        })
    if len(actuators) != 8 or [row["name"] for row in actuators] != [f"actuator{i}" for i in range(1, 9)]:
        raise ValueError("the frozen Panda actuator inventory must remain actuator1 through actuator8")

    tendon_section = root.find("tendon")
    fixed = tendon_section.find("fixed") if tendon_section is not None else None
    if fixed is None or fixed.get("name") != "split":
        raise ValueError("the frozen Panda split fixed tendon changed")
    wraps = []
    for node in fixed.findall("joint"):
        wraps.append({
            "type": "joint",
            "target": node.attrib["joint"],
            "coefficient": float(node.attrib["coef"]),
        })
    if len(wraps) != 2 or [row["coefficient"] for row in wraps] != [0.5, 0.5]:
        raise ValueError("the frozen Panda split tendon wraps changed")
    tendons = [{
        "name": "split",
        "wraps": wraps,
        "limited": False,
        "range": [0.0, 0.0],
        "stiffness": 0.0,
        "damping": 0.0,
        "friction_loss": 0.0,
        "margin": 0.0,
        "solref_limit": [],
        "solimp_limit": [],
        "solref_friction": [],
        "solimp_friction": [],
    }]

    equality_section = root.find("equality")
    equality = equality_section.find("joint") if equality_section is not None else None
    if equality is None or (equality.get("joint1"), equality.get("joint2")) != ("finger_joint1", "finger_joint2"):
        raise ValueError("the frozen Panda joint equality targets changed")
    equalities = [{
        "name": "finger_joint1_finger_joint2",
        "kind": "joint",
        "target1": equality.attrib["joint1"],
        "target2": equality.attrib["joint2"],
        "poly_coef": _numbers(equality.get("polycoef", "0 1 0 0 0"), width=5, label="equality.polycoef"),
        "solref": _numbers(equality.attrib["solref"], width=2, label="equality.solref"),
        "solimp": _numbers(equality.attrib["solimp"], width=3, label="equality.solimp"),
        "active": equality.get("active", "true") == "true",
    }]
    semantics = {
        "schema_version": SCHEMA_V2 if version == 2 else SCHEMA_V1,
        "source_identity": {
            "family": "menagerie-panda",
            "revision": SOURCE_REVISION,
            "source_closure_sha256": source_closure,
            "original_mjcf_sha256": _sha(xml_bytes),
        },
        "units": "SI_m_kg_s_rad",
        "actuators": actuators,
        "tendons": tendons,
        "equalities": equalities,
    }
    if version == 2:
        geom_nodes = [node for body in root.findall("worldbody") for node in body.iter("geom")]
        authored_friction = [node.attrib.get("friction") for node in geom_nodes if "friction" in node.attrib]
        collision_defaults = [node.attrib.get("friction") for node in root.findall(".//default/geom")
                              if "friction" in node.attrib]
        if authored_friction or collision_defaults:
            raise ValueError("DG02 v2 source friction defaults changed; do not substitute an unreviewed value")
        source_materials = {
            node.attrib["name"]: _numbers(node.attrib["rgba"], width=4, label=f"{node.attrib['name']}.rgba")
            for node in root.findall("asset/material") if node.get("name") and node.get("rgba")
        }
        if not source_materials:
            raise ValueError("DG02 v2 source visual materials are missing")
        semantics["visual_materials"] = source_materials
        semantics["collision_material"] = {
            "source_effective_mjcf_geom_friction": [1.0, 0.005, 0.0001],
            "source_mjcf_restitution_parameter": None,
            "usd_physics_material_api": {
                "static_friction": 1.0,
                "dynamic_friction": 1.0,
                "restitution": 0.0,
            },
            "geophys_geom_config_friction_expected": [1.0, 0.005, 0.0001],
            "mapping": "USD dynamic_friction supplies GeoPhys sliding component 0; GeoPhys public USD lowering retains tail defaults 0.005 and 0.0001, matching the source MJCF effective defaults for this build identity. MJCF has no scalar geom restitution parameter; USD restitution 0 is target configuration only and not a source-equivalence claim.",
            "cross_solver_friction_law_equivalence_claim": False,
            "cross_solver_contact_law_equivalence_claim": False,
        }
    return semantics


def _patch_stage(stage_path: Path, semantics: dict, *, version: int = 1, source_root: Path | None = None) -> list[str]:
    try:
        from pxr import Sdf, Usd
    except Exception as exc:  # pragma: no cover - runtime supplied by the frozen package
        raise RuntimeError("the frozen OpenUSD Python runtime is unavailable") from exc
    stage = Usd.Stage.Open(str(stage_path), load=Usd.Stage.LoadAll)
    if stage is None:
        raise ValueError("OpenUSD cannot compose the base stage")
    root = stage.GetDefaultPrim()
    if not root or str(root.GetPath()) != "/panda":
        raise ValueError("base stage default prim is not the accepted Panda articulation")
    removed = []
    for prim in stage.Traverse():
        for schema in tuple(prim.GetAppliedSchemas()):
            if schema.startswith("PhysicsDriveAPI:"):
                prim.RemoveAppliedSchema(schema)
                removed.append(f"{prim.GetPath()}:{schema}")
    attr = root.GetAttribute("geochora:f05SourceSemantics")
    if attr and attr.HasAuthoredValueOpinion():
        raise ValueError("base stage already has F05 source semantics; refusing to overwrite")
    attr = root.CreateAttribute("geochora:f05SourceSemantics", Sdf.ValueTypeNames.String, custom=True)
    attr.Set(json.dumps(semantics, sort_keys=True, separators=(",", ":"), allow_nan=False))
    if version == 2:
        from pxr import Gf, UsdGeom, UsdPhysics, UsdShade

        if source_root is None:
            raise ValueError("DG02 v2 stage authoring requires its frozen source root")
        xml_root = ET.parse(source_root / "panda.xml").getroot()
        body_paths = {}

        def visit(parent, parent_path="/panda/Geometry"):
            for body in parent.findall("body"):
                path = f"{parent_path}/{body.attrib['name']}"
                body_paths[body.attrib["name"]] = path
                visit(body, path)

        worldbody = xml_root.find("worldbody")
        if worldbody is None:
            raise ValueError("source MJCF has no worldbody")
        visit(worldbody)
        source_visual_materials = semantics["visual_materials"]
        visual_count = collision_count = 0
        for body in xml_root.iter("body"):
            body_name = body.attrib["name"]
            body_path = body_paths[body_name]
            for geom in body.findall("geom"):
                mesh_name = geom.get("mesh")
                role = geom.get("class", "")
                if not mesh_name:
                    continue
                collision = role == "collision"
                candidates = [
                    prim for prim in stage.GetPrimAtPath(body_path).GetChildren()
                    if prim.IsA(UsdGeom.Mesh)
                    and (str(prim.GetName()) == mesh_name or str(prim.GetName()).startswith(mesh_name + "_"))
                    and prim.HasAPI(UsdPhysics.CollisionAPI) == collision
                ]
                if len(candidates) != 1:
                    raise ValueError(f"cannot map v2 Panda source mesh {body_name}/{mesh_name}")
                prim = candidates[0]
                if collision:
                    collision_count += 1
                    continue
                material_name = geom.get("material")
                if material_name not in source_visual_materials:
                    raise ValueError(f"visual mesh {body_name}/{mesh_name} has no source RGBA material")
                rgba = source_visual_materials[material_name]
                mesh = UsdGeom.Mesh(prim)
                mesh.CreateDisplayColorAttr().Set([Gf.Vec3f(*rgba[:3])])
                mesh.CreateDisplayOpacityAttr().Set([float(rgba[3])])
                visual_count += 1
        material = UsdShade.Material.Define(stage, "/panda/Materials/F05SourceCollision")
        physics = UsdPhysics.MaterialAPI.Apply(material.GetPrim())
        physics.CreateStaticFrictionAttr().Set(1.0)
        physics.CreateDynamicFrictionAttr().Set(1.0)
        physics.CreateRestitutionAttr().Set(0.0)
        panda_shapes = [
            prim for prim in stage.Traverse()
            if str(prim.GetPath()).startswith("/panda/Geometry/")
            and prim.HasAPI(UsdPhysics.CollisionAPI)
        ]
        for prim in panda_shapes:
            UsdShade.MaterialBindingAPI.Apply(prim).Bind(
                material, materialPurpose="physics",
            )
        semantics["authored_shape_counts"] = {
            "visual_meshes_with_source_color": visual_count,
            "source_collision_meshes": collision_count,
            "panda_collision_shapes_with_source_material": len(panda_shapes),
        }
        attr.Set(json.dumps(semantics, sort_keys=True, separators=(",", ":"), allow_nan=False))
    stage.GetRootLayer().Save()
    return sorted(removed)


def _validate_output(root: Path, delivery: dict, semantics: dict, source_files: dict[str, bytes], *, version: int = 1) -> dict:
    try:
        from pxr import Usd, UsdGeom, UsdPhysics
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("the frozen OpenUSD Python runtime is unavailable") from exc
    stage_path = root / delivery["entry_file"]
    stage = Usd.Stage.Open(str(stage_path), load=Usd.Stage.LoadAll)
    if stage is None or not stage.GetDefaultPrim():
        raise ValueError("F05 derived USD stage does not compose")
    root_prim = stage.GetDefaultPrim()
    if str(root_prim.GetPath()) != delivery["entry_prim"]:
        raise ValueError("F05 derived USD default prim differs from its delivery")
    if not math.isclose(UsdGeom.GetStageMetersPerUnit(stage), 1.0) or UsdGeom.GetStageUpAxis(stage) != UsdGeom.Tokens.z:
        raise ValueError("F05 derived USD must preserve meters and Z-up")
    prims = tuple(stage.Traverse())
    joints = [prim for prim in prims if prim.IsA(UsdPhysics.Joint)]
    drive_schemas = [
        (str(prim.GetPath()), schema)
        for prim in prims for schema in prim.GetAppliedSchemas()
        if schema.startswith("PhysicsDriveAPI:")
    ]
    if drive_schemas:
        raise ValueError(f"F05 derived USD retains duplicate standard drive channels: {drive_schemas}")
    panda_scalar_joints = [
        prim for prim in joints
        if str(prim.GetPath()).startswith("/panda/")
        and prim.GetTypeName() in {"PhysicsRevoluteJoint", "PhysicsPrismaticJoint"}
    ]
    if len(semantics["actuators"]) != 8 or len(panda_scalar_joints) != 9:
        raise ValueError(
            f"F05 Panda shape differs: {len(panda_scalar_joints)} scalar joints / "
            f"{len(semantics['actuators'])} source actuators"
        )
    if not stage.GetPrimAtPath("/F04Scene/free_cube") or not stage.GetPrimAtPath("/F04Scene/support"):
        raise ValueError("F05 task cube/support prims are missing from the derived USD")
    if _source_closure_digest(source_files) != SOURCE_CLOSURE_SHA256:
        raise ValueError("source closure identity differs from the frozen Menagerie input")
    raw = stage.GetDefaultPrim().GetAttribute("geochora:f05SourceSemantics").Get()
    if json.loads(raw) != semantics:
        raise ValueError("authored USD semantic block differs from the source-derived payload")
    return {
        "source_closure_sha256": SOURCE_CLOSURE_SHA256,
        "source_entry_sha256": SOURCE_XML_SHA256,
        "usd_stage_sha256": _sha(stage_path.read_bytes()),
        "entry_prim": str(root_prim.GetPath()),
        "meters_per_unit": UsdGeom.GetStageMetersPerUnit(stage),
        "up_axis": str(UsdGeom.GetStageUpAxis(stage)),
        "joint_prim_count": len(joints),
        "panda_scalar_joint_count": len(panda_scalar_joints),
        "actuator_count": len(semantics["actuators"]),
        "tendon_count": len(semantics["tendons"]),
        "equality_count": len(semantics["equalities"]),
        "removed_standard_drive_schemas": drive_schemas,
        "features": {
            "source_actuators": "authored in geochora:f05SourceSemantics and lowered by the public GeoPhys USD importer into ActuatorDesc/TransmissionDesc",
            "fixed_tendon": "source joint wraps and coefficients retained in the versioned semantic block",
            "compliant_joint_equality": "source solref(2) and solimp(3) retained with source-authored arity",
            "task_cube_support": "retained from accepted source-derived local stage and checked by prim path",
            "visual_collision_geometry": (
                "source mesh surfaces, local frames, Panda body frames, boxes, joints and full body inertias are checked by the bound source audit"
                if version == 2 else
                "byte-identical to accepted stage base; geometric vertex/frame comparison remains a separate G1 audit item"
            ),
            "visual_colors": (
                "source MJCF RGBA values are authored as USD displayColor/displayOpacity on all visual Panda meshes"
                if version == 2 else "not source-bound in v1"
            ),
            "contact_material": (
                "the source-effective friction vector is represented on all Panda collision shapes; MJCF/GeoPhys contact-law equivalence and USD restitution equivalence are not claimed"
                if version == 2 else "not source-bound in v1"
            ),
        },
    }


def build(source_root: Path, base_delivery_path: Path, output_root: Path, *, version: int = 1) -> dict:
    if version not in (1, 2):
        raise ValueError("DG02 local delivery version must be 1 or 2")
    source_root = source_root.resolve(strict=True)
    base_root = base_delivery_path.resolve(strict=True).parent
    output_root = output_root.resolve()
    base_delivery = json.loads(base_delivery_path.read_text(encoding="utf-8"))
    if base_delivery.get("closure_sha256") != "e806772efcbc685cd36ad24dd69910fd970d3504cb7329472122956c8648e89d":
        raise ValueError("base local USD delivery is not the frozen accepted r009 input")
    base_stage = base_root / base_delivery["entry_file"]
    if _sha(base_stage.read_bytes()) != R009_STAGE_SHA256:
        raise ValueError("base composed stage bytes differ from frozen r009")

    existing_paths: set[str] = set()
    if output_root.exists():
        if not output_root.is_dir() or output_root.is_symlink():
            raise ValueError("DG02 output root must be a real directory")
        existing_paths = {path.relative_to(output_root).as_posix() for path in output_root.rglob("*") if path.is_file()}
        if "usd_delivery.json" in existing_paths or any(
            not (
                PurePosixPath(path).parts[0] == "assets"
                or path in {
                    "panda.xml", "derived/panda.usda",
                    "metadata/f05_dg02_usd_delivery_checker.py",
                    "metadata/f05_dg02_usd_recipe.json",
                    "metadata/source_inventory.json",
                    "metadata/f05_dg02_local_validation_report.json",
                }
            )
            for path in existing_paths
        ):
            raise FileExistsError(f"refusing to overwrite an existing DG02 delivery: {output_root}")
    else:
        output_root.mkdir(parents=True)

    files: dict[str, bytes] = {}
    for item in base_delivery["source_files"]:
        source_path = source_root / item["path"]
        raw = source_path.read_bytes()
        if len(raw) != item["size_bytes"] or _sha(raw) != item["sha256"]:
            raise ValueError(f"protected source bytes changed: {item['path']}")
        destination = output_root / item["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.read_bytes() != raw:
                raise ValueError(f"partial DG02 source copy differs from protected input: {item['path']}")
        else:
            shutil.copyfile(source_path, destination)
        files[item["path"]] = raw
    if _source_closure_digest(files) != SOURCE_CLOSURE_SHA256:
        raise ValueError("Menagerie source byte closure differs from the accepted DG01 source")
    xml_bytes = files["panda.xml"]
    if _sha(xml_bytes) != SOURCE_XML_SHA256:
        raise ValueError("original Panda MJCF source identity changed")
    semantics = _source_semantics(xml_bytes, SOURCE_CLOSURE_SHA256, version=version)

    entry_file = "derived/panda.usda"
    stage_path = output_root / entry_file
    stage_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(base_stage, stage_path)
    removed = _patch_stage(stage_path, semantics, version=version, source_root=source_root)

    checker_path = "metadata/f05_dg02_usd_delivery_checker.py"
    recipe_path = "metadata/f05_dg02_usd_recipe.json"
    source_manifest_path = "metadata/source_inventory.json"
    report_path = "metadata/f05_dg02_local_validation_report.json"
    for name in ("metadata",):
        (output_root / name).mkdir(parents=True, exist_ok=True)
    checker_bytes = Path(__file__).read_bytes()
    (output_root / checker_path).write_bytes(checker_bytes)

    source_bindings = list(_source_closure_manifest(files))
    source_manifest = {
        "schema_version": "f04-local-source-inventory-v1",
        "files": source_bindings,
        "source_closure_sha256": SOURCE_CLOSURE_SHA256,
    }
    source_manifest_bytes = (json.dumps(source_manifest, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    (output_root / source_manifest_path).write_bytes(source_manifest_bytes)

    recipe = {
        "schema_version": f"f05-dg02-usd-recipe-v{version}",
        "recipe_id": "f05-dg02-menagerie-panda-source-preserving-usd",
        "recipe_version": str(version),
        "source": {
            "family": "menagerie-panda",
            "revision": SOURCE_REVISION,
            "entry_file": "panda.xml",
            "entry_sha256": SOURCE_XML_SHA256,
            "closure_sha256": SOURCE_CLOSURE_SHA256,
            "base_representation": "f04 local r009 selected stage, frozen as a geometry/task-scene input only",
            "base_stage_sha256": R009_STAGE_SHA256,
            "base_delivery_sha256": _sha(base_delivery_path.read_bytes()),
        },
        "derivation": {
            "operation": "copy accepted composed stage; remove standard DriveAPI overlays; author source-derived versioned F05 semantics on /panda; DG02 v2 also preserves source visual RGBA and binds Panda collision defaults",
            "semantics_schema": SCHEMA_V2 if version == 2 else SCHEMA_V1,
            "removed_standard_drive_schemas": removed,
            "units": "SI meters-kilograms-seconds-radians; stage metersPerUnit=1 and upAxis=Z",
            "controller_values": "parsed from original MJCF actuator class defaults plus per-actuator overrides",
            "tendon_values": "parsed from original MJCF fixed tendon wraps; default passive terms explicitly represented",
            "equality_values": "parsed from original MJCF joint equality; authored 3-value solimp arity retained",
        },
        "feature_semantics": semantics,
        "known_audit_limits": (
            [
                "The source MJCF and GeoPhys contact laws are distinct; identical resolved friction coefficients do not claim cross-solver contact-law equivalence. USD restitution 0 is target configuration because MJCF has no scalar geom restitution parameter.",
                "The free cube and support retain the accepted DG01 recipe's unbound material values.",
                "Local delivery validation is not provider admission or native physics evidence.",
            ] if version == 2 else [
                "The base stage bytes are retained for meshes and task-scene geometry; vertex-level source-to-USD frame comparison is still required for G1.",
                "The source recipe has no authored contact material or collision filter and makes no friction-equivalence claim.",
                "Local delivery validation is not provider admission or native physics evidence.",
            ]
        ),
    }
    recipe_bytes = (json.dumps(recipe, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    (output_root / recipe_path).write_bytes(recipe_bytes)

    output_bindings = list(_source_closure_manifest({"derived/panda.usda": stage_path.read_bytes()}))
    options = {
        "base_stage_sha256": R009_STAGE_SHA256,
        "source_closure_sha256": SOURCE_CLOSURE_SHA256,
        "semantic_schema": SCHEMA_V2 if version == 2 else SCHEMA_V1,
        "drive_api_policy": "remove_standard_usd_drives_and_use_source_actuator_bundle",
        "source_visual_color_policy": "preserve_mjcf_material_rgba_as_usd_displayColor" if version == 2 else "base_stage",
        "source_contact_material_policy": "bind_MuJoCo_effective_default_coefficients_to_Panda_collision_shapes" if version == 2 else "base_stage_unbound",
    }
    options_sha = _canonical_hash(options)
    source_variant_sha = variant_selection_hash({})
    asset_definition = {
        "schema_version": "asset-definition-v1",
        "asset_id": "f05-dg02-menagerie-panda-source-preserving-usd",
        "asset_version": f"f05-dg02-usd-v{version}",
        "license_id": "bsd-3-clause",
        "source_content_sha256": SOURCE_CLOSURE_SHA256,
        "source_reference": "mujoco-menagerie://franka_emika_panda/panda.xml",
        "source_revision": SOURCE_REVISION,
    }
    asset_identity_hash = AssetDefinition.from_mapping(asset_definition).identity_hash
    delivery = {
        "schema_version": "usd-local-derived-delivery-v1",
        "asset_definition": asset_definition,
        "source_revision": SOURCE_REVISION,
        "provenance_kind": "local-validated",
        "source_closure_sha256": SOURCE_CLOSURE_SHA256,
        "source_manifest_path": source_manifest_path,
        "source_manifest_sha256": _sha(source_manifest_bytes),
        "source_entry_file": "panda.xml",
        "source_entry_sha256": SOURCE_XML_SHA256,
        "source_variant_selections": {},
        "source_variant_selection_sha256": source_variant_sha,
        "representation_format": "usd",
        "representation_id": f"geophys-0.6.3-source-preserving-f05-dg02-v{version}",
        "closure_policy": "f04-selected-derived-scene-v1",
        "entry_file": entry_file,
        "entry_prim": "/panda",
        "files": output_bindings,
        "closure_sha256": _source_closure_digest({"derived/panda.usda": stage_path.read_bytes()}),
        "recipe_path": recipe_path,
        "recipe_sha256": _sha(recipe_bytes),
        "checker_path": checker_path,
        "checker_sha256": _sha(checker_bytes),
        "support_files": [],
        "validation_report_path": report_path,
        "validation_report_sha256": "0" * 64,
        "options_sha256": options_sha,
        "source_files": [{**item} for item in source_bindings],
        "variant_selections": {},
    }
    validation = _validate_output(output_root, delivery, semantics, files, version=version)
    validation["removed_standard_drive_schemas"] = removed
    audit_receipt = None
    audit_code_sha256 = None
    if version == 2:
        from task_env.diagnostics.tasks.f05_dg02_usd_source_audit import audit

        audit_receipt = audit(source_root, stage_path, require_v2=True)
        audit_path = output_root / "metadata" / "source_audit.json"
        audit_path.write_text(json.dumps(audit_receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        audit_code_path = output_root / "metadata" / "f05_dg02_usd_source_audit.py"
        audit_code_path.write_bytes(Path(__file__).with_name("f05_dg02_usd_source_audit.py").read_bytes())
        validation["source_audit_sha256"] = _sha(audit_path.read_bytes())
        validation["source_audit_code_sha256"] = _sha(audit_code_path.read_bytes())
        validation["source_audit_summary"] = {
            key: audit_receipt["panda"][key] for key in (
                "source_mesh_geometry_count", "matched_mesh_geometry_count", "source_box_geometry_count",
                "matched_box_geometry_count", "body_frame_count", "inertial_body_count",
                "source_scalar_joint_count", "panda_joint_count", "collision_shape_count",
                "collision_shapes_with_physics_material_binding", "panda_joint_count",
            )
        }
    required_checks = [
        "source-bytes", "derived-output-bytes", "usd-composition", "dependency-closure",
        "selected-scene-structure", "panda-dof-units-limits", "physx-drive-profile",
        "free-body-and-support", "source-losses-recorded",
    ]
    if version == 2:
        required_checks.extend((
            "source-bound-triangle-geometry", "body-frames-and-full-inertia",
            "visual-color-source-values", "Panda-collision-material-binding",
            "source-contact-filter",
        ))
    report = {
        "schema_version": "usd-local-validation-report-v1",
        "report_id": f"f05-dg02-local-usd-report-v{version}",
        "provenance_kind": "local-validated",
        "source_asset_identity_hash": asset_identity_hash,
        "source_revision": SOURCE_REVISION,
        "source_closure_sha256": SOURCE_CLOSURE_SHA256,
        "source_manifest_sha256": delivery["source_manifest_sha256"],
        "source_entry_sha256": SOURCE_XML_SHA256,
        "source_variant_selection_sha256": source_variant_sha,
        "entry_file_sha256": output_bindings[0]["sha256"],
        "output_closure_sha256": delivery["closure_sha256"],
        "entry_prim": "/panda",
        "representation_format": "usd",
        "representation_id": delivery["representation_id"],
        "recipe_id": recipe["recipe_id"],
        "recipe_version": recipe["recipe_version"],
        "recipe_sha256": delivery["recipe_sha256"],
        "options_sha256": options_sha,
        "checker_id": f"geochora-f05-dg02-usd-delivery-checker-v{version}",
        "checker_sha256": delivery["checker_sha256"],
        "author": "GeoChora DG02 local source-preserving USD delivery",
        "checks": required_checks,
        "losses": [
            "r009 standard USD drive channels are removed from this derived representation and replaced by source-authored eight-actuator IR data.",
            "r009 representation did not expose the source tendon/equality to the GeoPhys importer; the versioned F05 semantic block records them for existing consumers.",
        ],
        "unconsumed": (
            ["the source contact law and GeoPhys contact law are not asserted equivalent beyond the mapped friction-parameter intersection; MJCF has no scalar geom restitution parameter"]
            if version == 2 else [
                "vertex-level source-to-USD mesh transform comparison remains a G1 audit item",
                "contact material and collision-filter semantics are absent from the accepted task recipe; no cross-engine friction equivalence is claimed",
            ]
        ),
        "passed": True,
    }
    report_bytes = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    delivery["validation_report_sha256"] = _sha(report_bytes)
    (output_root / report_path).write_bytes(report_bytes)
    manifest_bytes = (json.dumps(delivery, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    (output_root / "usd_delivery.json").write_bytes(manifest_bytes)
    loaded = load_usd_asset_delivery(output_root / "usd_delivery.json")
    loaded.assert_fresh()
    validation["loader_delivery_sha256"] = loaded.delivery.delivery_sha256
    validation["loader_source_verified"] = loaded.source_verified
    validation["loader_locally_validated"] = loaded.locally_validated
    validation["manifest_sha256"] = _sha(manifest_bytes)
    (output_root / "delivery_build_receipt.json").write_text(
        json.dumps(validation, sort_keys=True, indent=2) + "\n", encoding="utf-8",
    )
    return validation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--base-delivery", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--version", type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    result = build(args.source_root, args.base_delivery, args.output_root, version=args.version)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
