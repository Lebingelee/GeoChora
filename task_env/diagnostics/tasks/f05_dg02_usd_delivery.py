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


SCHEMA = "geochora.f05-source-semantics.v1"
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


def _source_semantics(xml_bytes: bytes, source_closure: str) -> dict:
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
    return {
        "schema_version": SCHEMA,
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


def _patch_stage(stage_path: Path, semantics: dict) -> list[str]:
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
    stage.GetRootLayer().Save()
    return sorted(removed)


def _validate_output(root: Path, delivery: dict, semantics: dict, source_files: dict[str, bytes]) -> dict:
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
            "visual_collision_geometry": "byte-identical to accepted stage base; geometric vertex/frame comparison remains a separate G1 audit item",
            "contact_material_equivalence": "not claimed; no source material binding exists in the frozen recipe",
        },
    }


def build(source_root: Path, base_delivery_path: Path, output_root: Path) -> dict:
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
    semantics = _source_semantics(xml_bytes, SOURCE_CLOSURE_SHA256)

    entry_file = "derived/panda.usda"
    stage_path = output_root / entry_file
    stage_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(base_stage, stage_path)
    removed = _patch_stage(stage_path, semantics)

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
        "schema_version": "f05-dg02-usd-recipe-v1",
        "recipe_id": "f05-dg02-menagerie-panda-source-preserving-usd",
        "recipe_version": "1",
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
            "operation": "copy accepted composed stage; remove standard DriveAPI overlays; author source-derived versioned F05 semantics on /panda",
            "semantics_schema": SCHEMA,
            "removed_standard_drive_schemas": removed,
            "units": "SI meters-kilograms-seconds-radians; stage metersPerUnit=1 and upAxis=Z",
            "controller_values": "parsed from original MJCF actuator class defaults plus per-actuator overrides",
            "tendon_values": "parsed from original MJCF fixed tendon wraps; default passive terms explicitly represented",
            "equality_values": "parsed from original MJCF joint equality; authored 3-value solimp arity retained",
        },
        "feature_semantics": semantics,
        "known_audit_limits": [
            "The base stage bytes are retained for meshes and task-scene geometry; vertex-level source-to-USD frame comparison is still required for G1.",
            "The source recipe has no authored contact material or collision filter and makes no friction-equivalence claim.",
            "Local delivery validation is not provider admission or native physics evidence.",
        ],
    }
    recipe_bytes = (json.dumps(recipe, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    (output_root / recipe_path).write_bytes(recipe_bytes)

    output_bindings = list(_source_closure_manifest({"derived/panda.usda": stage_path.read_bytes()}))
    options = {
        "base_stage_sha256": R009_STAGE_SHA256,
        "source_closure_sha256": SOURCE_CLOSURE_SHA256,
        "semantic_schema": SCHEMA,
        "drive_api_policy": "remove_standard_usd_drives_and_use_source_actuator_bundle",
    }
    options_sha = _canonical_hash(options)
    source_variant_sha = variant_selection_hash({})
    asset_definition = {
        "schema_version": "asset-definition-v1",
        "asset_id": "f05-dg02-menagerie-panda-source-preserving-usd",
        "asset_version": "f05-dg02-usd-v1",
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
        "representation_id": "geophys-0.6.3-source-preserving-f05-dg02-v1",
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
    validation = _validate_output(output_root, delivery, semantics, files)
    validation["removed_standard_drive_schemas"] = removed
    required_checks = [
        "source-bytes", "derived-output-bytes", "usd-composition", "dependency-closure",
        "selected-scene-structure", "panda-dof-units-limits", "physx-drive-profile",
        "free-body-and-support", "source-losses-recorded",
    ]
    report = {
        "schema_version": "usd-local-validation-report-v1",
        "report_id": "f05-dg02-local-usd-report-v1",
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
        "checker_id": "geochora-f05-dg02-usd-delivery-checker-v1",
        "checker_sha256": delivery["checker_sha256"],
        "author": "GeoChora DG02 local source-preserving USD delivery",
        "checks": required_checks,
        "losses": [
            "r009 standard USD drive channels are removed from this derived representation and replaced by source-authored eight-actuator IR data.",
            "r009 representation did not expose the source tendon/equality to the GeoPhys importer; the versioned F05 semantic block records them for existing consumers.",
        ],
        "unconsumed": [
            "vertex-level source-to-USD mesh transform comparison remains a G1 audit item",
            "contact material and collision-filter semantics are absent from the accepted task recipe; no cross-engine friction equivalence is claimed",
        ],
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
    args = parser.parse_args()
    result = build(args.source_root, args.base_delivery, args.output_root)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
