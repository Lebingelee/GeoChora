"""Package and cold-validate the bounded DG03 source-preserving Isaac USD.

The report is a local representation check. It records unresolved public
PhysX consumers explicitly and does not qualify the model or a runtime route.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
from typing import Mapping
import xml.etree.ElementTree as ET

from task_env.assembly.assets import _source_closure_digest, _source_closure_manifest
from task_env.assembly.usd_delivery import (
    _inspect_snapshot,
    load_usd_asset_delivery,
    variant_selection_hash,
)
from task_env.artifacts import AssetDefinition, UsdLocalValidationReportV1


SOURCE_REVISION = "b846dd12bc459d776cccb3dee0b1d02acbf7a9c7"
SOURCE_XML_SHA256 = "96ad67da03710f17f798c9478fd9e9efdf24a3bf8359f05e456dd9fb158ea273"
SOURCE_CLOSURE_SHA256 = "a59a66d0b176cb6b2634d54cd20744752742b425e5524db1b865dda0eb3adf2a"
TASK_RECIPE_SHA256 = "6a705816e619681e948a1b243e0588dd1db2f667ecfb085bd2e55b1c3fd8b89d"
LOCAL_CHECKS = (
    "source-bytes", "derived-output-bytes", "usd-composition", "dependency-closure",
    "selected-scene-structure", "panda-dof-units-limits", "physx-drive-profile",
    "free-body-and-support", "source-losses-recorded",
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_sha(value: object) -> str:
    return _sha(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def _write_exact(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise FileExistsError(f"refusing to overwrite different DG03 delivery bytes: {path}")
        return
    path.write_bytes(raw)


def _copy_exact(source: Path, destination: Path) -> bytes:
    raw = source.read_bytes()
    _write_exact(destination, raw)
    return raw


def package_delivery(*, repo: Path, window: Path, output: Path) -> dict[str, object]:
    repo = repo.resolve(strict=True)
    window = window.resolve(strict=True)
    output = output.absolute()
    source_root = repo / "asset/external/mujoco_menagerie/franka_emika_panda"
    source_inventory_path = (
        repo / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001"
        / "f05_diagnostic_goal02/window_001/usd_source_v2_004/metadata/source_inventory.json"
    )
    inventory_raw = source_inventory_path.read_bytes()
    frozen_inventory = json.loads(inventory_raw)
    if (frozen_inventory.get("schema_version") != "f04-local-source-inventory-v1"
            or frozen_inventory.get("source_closure_sha256") != SOURCE_CLOSURE_SHA256
            or len(frozen_inventory.get("files", ())) != 68):
        raise ValueError("DG03 source-file selection differs from the frozen accepted Menagerie inventory")
    source_files: dict[str, bytes] = {}
    if not source_root.is_dir():
        raise FileNotFoundError(f"frozen Menagerie Panda source is missing: {source_root}")
    for binding in frozen_inventory["files"]:
        relative = binding["path"]
        source_path = source_root.joinpath(*PurePosixPath(relative).parts)
        raw = source_path.read_bytes()
        if (len(raw) != binding["size_bytes"] or _sha(raw) != binding["sha256"]):
            raise ValueError(f"DG03 source input differs from frozen inventory bytes: {relative}")
        source_files[relative] = raw
        _write_exact(output / relative, raw)
    if len(source_files) != 68 or _source_closure_digest(source_files) != SOURCE_CLOSURE_SHA256:
        raise ValueError("DG03 packaged source closure differs from the frozen 68-file Menagerie input")
    if _sha(source_files["panda.xml"]) != SOURCE_XML_SHA256:
        raise ValueError("DG03 packaged Panda MJCF differs from frozen source identity")

    source_recipe_path = repo / "task_env/tasks/position_candidate/assets/f05_dg01_task_scene_recipe.json"
    source_recipe = source_recipe_path.read_bytes()
    if _sha(source_recipe) != TASK_RECIPE_SHA256:
        raise ValueError("DG03 scene recipe differs from frozen DG01 recipe identity")
    recipe_rel = "metadata/f05_dg03_isaac_usd_recipe.json"
    checker_rel = "metadata/f05_dg03_isaac_usd_checker.py"
    inventory_rel = "metadata/source_inventory.json"
    report_rel = "metadata/f05_dg03_local_validation_report.json"
    manifest_rel = "delivery_manifest.json"

    overlay_receipt_path = window / "isaac_usd_v1/derived_v1/overlay_receipt.json"
    overlay_receipt_raw = overlay_receipt_path.read_bytes()
    overlay_receipt = json.loads(overlay_receipt_raw)
    entry_rel = "derived_v1/panda.usda"
    entry_raw = _copy_exact(
        window / "isaac_usd_v1/derived_v1/panda.usda", output / entry_rel,
    )
    converter_root = window / "isaac_usd_v1/converter_output"
    if not converter_root.is_dir():
        raise FileNotFoundError("DG03 converter output is missing")
    for source_path in sorted(path for path in converter_root.rglob("*") if path.is_file()):
        relative = source_path.relative_to(window / "isaac_usd_v1").as_posix()
        _copy_exact(source_path, output / relative)

    source_manifest_rows = list(_source_closure_manifest(source_files))
    source_manifest = {
        "schema_version": "f04-local-source-inventory-v1",
        "files": source_manifest_rows,
        "source_closure_sha256": SOURCE_CLOSURE_SHA256,
    }
    source_manifest_raw = (json.dumps(source_manifest, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    _write_exact(output / inventory_rel, source_manifest_raw)

    from pxr import Usd, UsdGeom, UsdPhysics

    required, inspection = _inspect_snapshot(
        output, output / entry_rel, "/panda", {},
    )
    required_paths = sorted(required)
    expected_existing = {entry_rel, *(path.relative_to(output).as_posix()
                                      for path in (output / "converter_output").rglob("*") if path.is_file())}
    if not set(required_paths).issubset(expected_existing):
        raise ValueError("DG03 USD composed dependencies escape the recorded converter closure")
    output_files = {relative: (output / relative).read_bytes() for relative in required_paths}
    if entry_rel not in output_files:
        raise ValueError("DG03 USD dependency closure omitted its entry layer")
    output_closure_sha = _source_closure_digest(output_files)

    stage = Usd.Stage.Open(str(output / entry_rel), load=Usd.Stage.LoadAll)
    if stage is None:
        raise ValueError("DG03 USD stage failed independent OpenUSD reopen")
    if (float(UsdGeom.GetStageMetersPerUnit(stage)), str(UsdGeom.GetStageUpAxis(stage))) != (1.0, "Z"):
        raise ValueError("DG03 stage must remain SI meter and Z-up")
    if not stage.GetPrimAtPath("/panda").IsValid():
        raise ValueError("DG03 selected Panda prim is missing")
    scenes = [prim for prim in stage.Traverse() if prim.IsA(UsdPhysics.Scene)]
    joints = [prim for prim in stage.Traverse()
              if prim.IsA(UsdPhysics.RevoluteJoint) or prim.IsA(UsdPhysics.PrismaticJoint)]
    articulation_roots = [prim for prim in stage.Traverse()
                          if prim.HasAPI(UsdPhysics.ArticulationRootAPI)]
    drives = [prim for prim in joints if prim.HasAPI(UsdPhysics.DriveAPI)]
    if len(scenes) != 1 or len(joints) != 9 or len(articulation_roots) != 1 or len(drives) != 7:
        raise ValueError("DG03 public USD structure differs from the frozen 1-scene/9-DOF/7-arm-drive profile")
    if not stage.GetPrimAtPath("/F05Scene/free_cube").HasAPI(UsdPhysics.RigidBodyAPI):
        raise ValueError("DG03 reset cube lacks the declared public RigidBodyAPI")
    if not stage.GetPrimAtPath("/F05Scene/free_cube/collision").HasAPI(UsdPhysics.CollisionAPI):
        raise ValueError("DG03 reset cube lacks collision geometry")
    if not stage.GetPrimAtPath("/F05Scene/support/collision").HasAPI(UsdPhysics.CollisionAPI):
        raise ValueError("DG03 support lacks collision geometry")
    if not any(prim.GetTypeName() == "MjcTendon" for prim in stage.Traverse()):
        raise ValueError("DG03 source tendon declaration is absent from composed USD")
    source_root_xml = ET.fromstring(source_files["panda.xml"])
    equality = source_root_xml.find("./equality")
    if equality is None or not list(equality):
        raise ValueError("DG03 frozen source entry does not include its equality declaration")
    mjc_type_counts: dict[str, int] = {}
    for prim in stage.Traverse():
        if prim.GetTypeName().startswith("Mjc"):
            mjc_type_counts[prim.GetTypeName()] = mjc_type_counts.get(prim.GetTypeName(), 0) + 1
    if mjc_type_counts.get("MjcTendon", 0) != 1 or mjc_type_counts.get("MjcEquality", 0) != 0:
        raise ValueError(f"DG03 converter's Mjc source-schema inventory changed: {mjc_type_counts!r}")
    correction = {
        "schema_version": "f05-dg03-usd-overlay-audit-correction-v1",
        "supersedes_overlay_receipt_sha256": _sha(overlay_receipt_raw),
        "superseded_claim": overlay_receipt.get("source_equality_and_tendon_metadata_preserved_in_sublayer"),
        "source_xml_sha256": SOURCE_XML_SHA256,
        "derived_entry_sha256": _sha(entry_raw),
        "converter_base_sha256": _sha((output / "converter_output/panda.usda").read_bytes()),
        "source_equality": [
            {"tag": node.tag, "attributes": dict(sorted(node.attrib.items()))}
            for node in list(equality)
        ],
        "composed_mjc_schema_counts": dict(sorted(mjc_type_counts.items())),
        "source_tendon_preserved_as_mjc_metadata": True,
        "source_equality_preserved_as_mjc_metadata": False,
        "equality_loss": "MuJoCo USD Converter 0.6.1 output contains no MjcEquality prim; source XML bytes remain bound separately.",
        "consumer_claim": "No PhysX equality consumer is established by this local USD audit.",
    }
    correction_rel = "metadata/overlay_audit_correction.json"
    correction_raw = (json.dumps(correction, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    _write_exact(output / correction_rel, correction_raw)
    overlay_receipt = {
        **overlay_receipt,
        "source_equality_and_tendon_metadata_preserved_in_sublayer": False,
        "audit_correction": correction,
    }

    source_asset = AssetDefinition(
        schema_version="asset-definition-v1",
        asset_id="f05-dg03-menagerie-panda-source-preserving-isaac-usd",
        asset_version="f05-dg03-isaac-usd-v1",
        source_reference="mujoco-menagerie://franka_emika_panda/panda.xml",
        source_revision=SOURCE_REVISION,
        source_content_sha256=SOURCE_CLOSURE_SHA256,
        license_id="bsd-3-clause",
    )
    source_variant = {}
    source_variant_sha = variant_selection_hash(source_variant)
    options = {
        "entry_prim": "/panda",
        "source_closure_sha256": SOURCE_CLOSURE_SHA256,
        "base_converter_output_sha256": _sha((window / "isaac_usd_v1/converter_output/panda.usda").read_bytes()),
        "overlay_source_sha256": overlay_receipt["derived_entry_sha256"],
        "actuator_policy": "seven-source-derived-arm-UsdPhysics-DriveAPI-plus-Core-tendon-effort",
        "equality_policy": "MJCF joint equality is not emitted by converter 0.6.1; public PhysX mapping remains unresolved",
        "task_scene_recipe_sha256": TASK_RECIPE_SHA256,
    }
    options_sha = _canonical_sha(options)
    representation_id = "isaacsim-6.2.0.0-f05-dg03-source-preserving-usd-v1"
    recipe = {
        "schema_version": "f05-dg03-isaac-usd-recipe-v1",
        "recipe_id": "f05-dg03-menagerie-panda-source-preserving-isaac-usd",
        "recipe_version": "1",
        "source": {
            "family": "menagerie-panda", "revision": SOURCE_REVISION,
            "entry_file": "panda.xml", "entry_sha256": SOURCE_XML_SHA256,
            "closure_sha256": SOURCE_CLOSURE_SHA256,
            "task_scene_recipe_sha256": TASK_RECIPE_SHA256,
        },
        "derivation": {
            "converter": "mujoco-usd-converter 0.6.1 from installed Isaac Sim 6.2.0.0",
            "overlay": "DG03 separate source-preserving layer, not DG02 USD or r009 source",
            "overlay_receipt": overlay_receipt,
            "overlay_audit_correction": correction,
            "options": options,
            "validation": "local OpenUSD byte/structure/dependency audit",
        },
        "known_limits": [
            "local validation does not prove PhysX consumption of MJCF equality/tendon",
            "arm DriveAPI settings are derived source representation; native force/limit behavior requires a public consumer probe",
            "free cube/support have no authored surface material, collision filters, COM or inertia",
            "USD contact law is not claimed equivalent to MuJoCo or GeoPhys",
        ],
    }
    recipe_raw = (json.dumps(recipe, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    checker_raw = Path(__file__).read_bytes()
    _write_exact(output / recipe_rel, recipe_raw)
    _write_exact(output / checker_rel, checker_raw)

    output_bindings = list(_source_closure_manifest(output_files))
    source_bindings = list(_source_closure_manifest(source_files))
    delivery = {
        "schema_version": "usd-local-derived-delivery-v1",
        "asset_definition": source_asset.to_mapping(),
        "source_revision": SOURCE_REVISION,
        "provenance_kind": "local-validated",
        "source_closure_sha256": SOURCE_CLOSURE_SHA256,
        "source_manifest_path": inventory_rel,
        "source_manifest_sha256": _sha(source_manifest_raw),
        "source_files": source_bindings,
        "source_entry_file": "panda.xml",
        "source_entry_sha256": SOURCE_XML_SHA256,
        "source_variant_selections": source_variant,
        "source_variant_selection_sha256": source_variant_sha,
        "entry_file": entry_rel,
        "entry_prim": "/panda",
        "variant_selections": {},
        "representation_format": "usd",
        "representation_id": representation_id,
        "closure_policy": "f04-selected-derived-scene-v1",
        "files": output_bindings,
        "closure_sha256": output_closure_sha,
        "recipe_path": recipe_rel,
        "recipe_sha256": _sha(recipe_raw),
        "checker_path": checker_rel,
        "checker_sha256": _sha(checker_raw),
        "support_files": list(_source_closure_manifest({correction_rel: correction_raw})),
        "validation_report_path": report_rel,
        "validation_report_sha256": "0" * 64,
        "options_sha256": options_sha,
    }
    report = UsdLocalValidationReportV1(
        "usd-local-validation-report-v1", "f05-dg03-isaac-usd-local-report-v1",
        "local-validated", source_asset.identity_hash, SOURCE_REVISION,
        SOURCE_CLOSURE_SHA256, _sha(source_manifest_raw), SOURCE_XML_SHA256,
        source_variant_sha, _sha(entry_raw), output_closure_sha, "/panda", "usd",
        representation_id, recipe["recipe_id"], "1", _sha(recipe_raw), options_sha,
        "f05-dg03-local-usd-checker-v1", _sha(checker_raw), "Luna1",
        LOCAL_CHECKS,
        (
            "source MJCF equality is not emitted by converter 0.6.1; the original source bytes remain separately bound and a PhysX mapping is unresolved",
            "native arm drive force/limit behavior is not established by schema authoring",
            "free cube/support contact material, COM, inertia and collision filtering are not source-bound",
        ),
        (
            "PhysX equality/mimic representation and consumer",
            "PhysX fixed tendon consumer",
            "cross-provider contact-material equivalence",
        ),
        True,
    )
    report.validate()
    report_raw = (json.dumps(report.to_mapping(), sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    delivery["validation_report_sha256"] = _sha(report_raw)
    _write_exact(output / report_rel, report_raw)
    _write_exact(output / manifest_rel,
                 (json.dumps(delivery, sort_keys=True, indent=2, allow_nan=False) + "\n").encode())
    loaded = load_usd_asset_delivery(output / manifest_rel)
    if (not loaded.locally_validated or loaded.source_verified
            or loaded.delivery.source_closure_sha256 != SOURCE_CLOSURE_SHA256):
        raise ValueError("DG03 Core loader did not return the exact local, non-upstream source package")
    return {
        "schema_version": "f05-dg03-isaac-usd-delivery-receipt-v1",
        "manifest_path": str(output / manifest_rel),
        "manifest_sha256": _sha((output / manifest_rel).read_bytes()),
        "delivery_sha256": loaded.delivery_sha256,
        "source_closure_sha256": SOURCE_CLOSURE_SHA256,
        "output_closure_sha256": output_closure_sha,
        "required_usd_dependencies": required_paths,
        "inspection": dict(inspection),
        "locally_validated": loaded.locally_validated,
        "source_verified": loaded.source_verified,
        "unconsumed": list(report.unconsumed),
        "passed": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--window", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = package_delivery(repo=args.repo, window=args.window, output=args.output)
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
