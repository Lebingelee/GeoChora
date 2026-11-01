"""Generate and locally validate the versioned F06 desktop PickCube USD.

Run the script directly with Isaac Sim 6.2 Python, outside a SimulationApp
process. Pass the matching Core interpreter so its dependencies can be exposed
without replacing Isaac's OpenUSD package:
``isaacsim-6.2.0/bin/python task_env/diagnostics/tasks/pickcube_isaac_usd_delivery.py --core-python /path/to/geochora/bin/python --source-package ... --output ...``
This generator consumes the frozen DG03/V4 Menagerie robot package as source
evidence and writes its derived F06 composition under the requested workspace
output directory. It does not start Isaac Sim or a physics worker.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile

CORE_ROOT = Path(__file__).resolve().parents[3]
CORE_AGENT_TOOLS = CORE_ROOT / "task_env/script/agent"
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))
if str(CORE_ROOT / "GeoPhys/src") not in sys.path:
    sys.path.insert(0, str(CORE_ROOT / "GeoPhys/src"))
if str(CORE_AGENT_TOOLS) not in sys.path:
    sys.path.insert(0, str(CORE_AGENT_TOOLS))

from isaac_core_site_overlay import populate_isaac_core_site_overlay


LOCAL_CHECKS = (
    "source-bytes", "derived-output-bytes", "usd-composition", "dependency-closure",
    "selected-scene-structure", "panda-dof-units-limits", "physx-drive-profile",
    "free-body-and-support", "source-losses-recorded",
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != raw:
        raise FileExistsError(f"refusing to overwrite different F06 USD package byte: {path}")
    if not path.exists():
        path.write_bytes(raw)


def _json_bytes(value) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _read_stage(output: Path, entry_rel: str):
    from pxr import Gf, Usd, UsdGeom, UsdPhysics

    stage = Usd.Stage.CreateNew(str(output / entry_rel))
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    root = UsdGeom.Xform.Define(stage, "/F06Scene")
    stage.SetDefaultPrim(root.GetPrim())
    scene = UsdPhysics.Scene.Define(stage, "/F06Scene/physicsScene")
    scene.CreateGravityDirectionAttr(Gf.Vec3f(0.0, 0.0, -1.0))
    scene.CreateGravityMagnitudeAttr(9.81)

    # USD path components are Sdf identifiers; canonical semantic IDs with
    # hyphens stay in Core, while the source prim names use valid USD tokens.
    panda = UsdGeom.Xform.Define(stage, "/F06Scene/panda").GetPrim()
    panda.GetReferences().AddReference("derived_v4/panda.usda", "/panda")
    ee_path = (
        "/F06Scene/panda/Geometry/link0/link1/link2/link3/link4/"
        "link5/link6/link7/hand/ee"
    )
    ee = UsdGeom.Xform.Define(stage, ee_path)
    ee.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.0584))

    table_center = (0.5545, 0.0, 0.452)
    table = UsdGeom.Xform.Define(stage, "/F06Scene/tabletop_v1")
    table.AddTranslateOp().Set(Gf.Vec3d(*table_center))
    support = UsdGeom.Cube.Define(stage, "/F06Scene/tabletop_v1/collision")
    support.CreateSizeAttr(2.0)
    UsdGeom.Xformable(support.GetPrim()).AddScaleOp().Set(Gf.Vec3f(0.28, 0.20, 0.01))
    UsdPhysics.CollisionAPI.Apply(support.GetPrim())
    table_top = UsdGeom.Xform.Define(stage, "/F06Scene/tabletop_v1/top")
    table_top.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.01))

    cube = UsdGeom.Xform.Define(stage, "/F06Scene/cube_v1")
    cube.AddTranslateOp().Set(Gf.Vec3d(0.50, 0.0, 0.488))
    UsdPhysics.RigidBodyAPI.Apply(cube.GetPrim()).CreateRigidBodyEnabledAttr(True)
    mass = UsdPhysics.MassAPI.Apply(cube.GetPrim())
    mass.CreateMassAttr(0.08)
    cube_inertia = 0.08 * 0.05**2 / 6.0
    mass.CreateDiagonalInertiaAttr(Gf.Vec3f(cube_inertia, cube_inertia, cube_inertia))
    collision = UsdGeom.Cube.Define(stage, "/F06Scene/cube_v1/collision")
    collision.CreateSizeAttr(2.0)
    UsdGeom.Xformable(collision.GetPrim()).AddScaleOp().Set(Gf.Vec3f(0.025, 0.025, 0.025))
    UsdPhysics.CollisionAPI.Apply(collision.GetPrim())

    arm_joint_paths = {
        "joint1": "/F06Scene/panda/Geometry/link0/link1/joint1",
        "joint2": "/F06Scene/panda/Geometry/link0/link1/link2/joint2",
        "joint3": "/F06Scene/panda/Geometry/link0/link1/link2/link3/joint3",
        "joint4": "/F06Scene/panda/Geometry/link0/link1/link2/link3/link4/joint4",
        "joint5": "/F06Scene/panda/Geometry/link0/link1/link2/link3/link4/link5/joint5",
        "joint6": "/F06Scene/panda/Geometry/link0/link1/link2/link3/link4/link5/link6/joint6",
        "joint7": "/F06Scene/panda/Geometry/link0/link1/link2/link3/link4/link5/link6/link7/joint7",
    }
    for path in arm_joint_paths.values():
        joint = stage.GetPrimAtPath(path)
        if not joint or not joint.IsValid():
            raise ValueError(f"F06 source Panda arm Joint is absent: {path}")
        drive = UsdPhysics.DriveAPI(joint, "angular")
        if not drive:
            drive = UsdPhysics.DriveAPI.Apply(joint, "angular")
        drive.CreateMaxForceAttr(250.0)

    leader_path = (
        "/F06Scene/panda/Geometry/link0/link1/link2/link3/link4/"
        "link5/link6/link7/hand/left_finger/finger_joint1"
    )
    leader = stage.GetPrimAtPath(leader_path)
    if not leader or not leader.IsValid():
        raise ValueError("F06 source Panda leader finger Joint is absent")
    drive = UsdPhysics.DriveAPI(leader, "linear")
    if not drive:
        drive = UsdPhysics.DriveAPI.Apply(leader, "linear")
    drive.CreateStiffnessAttr(5000.0)
    drive.CreateDampingAttr(120.0)
    drive.CreateMaxForceAttr(5.0)
    stage.GetRootLayer().Save()
    return stage, arm_joint_paths, leader_path, ee_path


def _validate_stage(output: Path, entry_rel: str) -> dict[str, object]:
    from pxr import Usd, UsdGeom, UsdPhysics

    stage = Usd.Stage.Open(str(output / entry_rel), load=Usd.Stage.LoadAll)
    if stage is None:
        raise ValueError("F06 PickCube USD did not reopen")
    if (float(UsdGeom.GetStageMetersPerUnit(stage)), str(UsdGeom.GetStageUpAxis(stage))) != (1.0, "Z"):
        raise ValueError("F06 PickCube USD must use SI meters and Z-up")
    scenes = [prim for prim in stage.Traverse() if prim.IsA(UsdPhysics.Scene)]
    articulation_roots = [
        prim for prim in stage.Traverse() if prim.HasAPI(UsdPhysics.ArticulationRootAPI)
    ]
    joints = [prim for prim in stage.Traverse() if prim.IsA(UsdPhysics.Joint)]
    if len(scenes) != 1 or len(articulation_roots) != 1:
        raise ValueError("F06 USD requires one physics scene and the referenced Panda articulation root")
    if not stage.GetPrimAtPath("/F06Scene/cube_v1").HasAPI(UsdPhysics.RigidBodyAPI):
        raise ValueError("F06 cube body lacks public RigidBodyAPI")
    if not stage.GetPrimAtPath("/F06Scene/cube_v1/collision").HasAPI(UsdPhysics.CollisionAPI):
        raise ValueError("F06 cube is missing its collision geometry")
    if not stage.GetPrimAtPath("/F06Scene/tabletop_v1/collision").HasAPI(UsdPhysics.CollisionAPI):
        raise ValueError("F06 tabletop is missing its collision geometry")
    top_path = "/F06Scene/tabletop_v1/top"
    if not stage.GetPrimAtPath(top_path).IsValid():
        raise ValueError("F06 tabletop task-frame prim is absent")
    top_offset = tuple(float(v) for v in UsdGeom.Xformable(
        stage.GetPrimAtPath(top_path)).GetOrderedXformOps()[0].Get())
    if top_offset != (0.0, 0.0, 0.01):
        raise ValueError("F06 tabletop task frame must bind the physical support surface")
    cube_mass = float(UsdPhysics.MassAPI(stage.GetPrimAtPath("/F06Scene/cube_v1")).GetMassAttr().Get())
    if not __import__("math").isclose(cube_mass, 0.08, rel_tol=0.0, abs_tol=1e-8):
        raise ValueError("F06 cube mass differs from the PickCube 0.08 kg contract")
    cube_scale = tuple(float(v) for v in UsdGeom.Xformable(
        stage.GetPrimAtPath("/F06Scene/cube_v1/collision")).GetOrderedXformOps()[0].Get())
    if any(not __import__("math").isclose(v, 0.025, rel_tol=0.0, abs_tol=1e-8)
           for v in cube_scale):
        raise ValueError("F06 cube half-size differs from the PickCube 50 mm contract")
    mimic_rows = [
        prim for prim in stage.Traverse()
        if prim.GetName() == "finger_joint2" and prim.IsA(UsdPhysics.PrismaticJoint)
    ]
    mimic_schemas = (
        [] if len(mimic_rows) != 1
        else list(mimic_rows[0].GetMetadata("apiSchemas").GetAppliedItems())
    )
    if len(mimic_rows) != 1 or "PhysxMimicJointAPI:transX" not in mimic_schemas:
        raise ValueError("F06 follower finger lacks its source-derived PhysX mimic API")
    leader_rows = [
        prim for prim in stage.Traverse()
        if prim.GetName() == "finger_joint1" and prim.IsA(UsdPhysics.PrismaticJoint)
    ]
    arm_rows = [
        prim for prim in stage.Traverse()
        if prim.GetName() in {f"joint{i}" for i in range(1, 8)}
        and prim.IsA(UsdPhysics.RevoluteJoint)
    ]
    if len(leader_rows) != 1 or len(arm_rows) != 7:
        raise ValueError("F06 Panda mapping must expose seven angular Arm and two linear Hand DOFs")
    leader_drive = UsdPhysics.DriveAPI(leader_rows[0], "linear")
    if any(float(leader_drive.GetStiffnessAttr().Get()) != expected
           for expected in (5000.0,)):
        raise ValueError("F06 gripper stiffness differs from the task source profile")
    if (float(leader_drive.GetDampingAttr().Get()) != 120.0
            or float(leader_drive.GetMaxForceAttr().Get()) != 5.0):
        raise ValueError("F06 gripper damping/force cap differs from the PickCube source adapter")
    if any(float(UsdPhysics.DriveAPI(row, "angular").GetMaxForceAttr().Get()) != 250.0
           for row in arm_rows):
        raise ValueError("F06 Arm max effort differs from PickCube's 250 N source force range")
    ee_path = (
        "/F06Scene/panda/Geometry/link0/link1/link2/link3/link4/"
        "link5/link6/link7/hand/ee"
    )
    if not stage.GetPrimAtPath(ee_path).IsValid():
        raise ValueError("F06 hand TCP frame prim is absent")
    ee_offset = tuple(float(v) for v in UsdGeom.Xformable(
        stage.GetPrimAtPath(ee_path)).GetOrderedXformOps()[0].Get())
    if ee_offset != (0.0, 0.0, 0.0584):
        raise ValueError("F06 TCP offset differs from the PickCube hand-frame contract")
    return {
        "physics_scene_count": len(scenes),
        "articulation_root_count": len(articulation_roots),
        "joint_count": len(joints),
        "arm_dofs": 7, "hand_dofs": 2,
        "cube_half_size_m": [0.025, 0.025, 0.025],
        "cube_mass_kg": cube_mass,
        "table_top_z_m": 0.462,
        "table_top_frame_local_offset_m": list(top_offset),
        "tcp_hand_offset_m": list(ee_offset),
        "arm_effort_limit_N": 250.0,
        "hand_effort_limit_N": 5.0,
        "gripper_drive_stiffness_N_m": 5000.0,
        "gripper_drive_damping_N_s_m": 120.0,
        "mimic_mapping": "source-affine-finger-equality-to-public-PhysxMimicJointAPI-v1",
        "surface_material": "provider-default-no-cross-engine-equivalence-claim",
    }


@contextmanager
def _core_dependency_path(core_python: Path | None):
    """Expose matching Core dependencies after Isaac's native packages."""
    configured_site = os.environ.get("GEOCHORA_CORE_SITE")
    if configured_site:
        site = Path(configured_site).expanduser().resolve(strict=True)
        sys.path.append(str(site))
        try:
            yield
        finally:
            sys.path.remove(str(site))
        return
    if core_python is None:
        yield
        return

    interpreter = core_python.expanduser().resolve(strict=True)
    details = json.loads(subprocess.check_output(
        [str(interpreter), "-c",
         "import json,sys,sysconfig; print(json.dumps({'version': list(sys.version_info[:2]), 'purelib': sysconfig.get_paths()['purelib']}))"],
        cwd=CORE_ROOT, text=True, timeout=10,
    ))
    if details["version"] != list(sys.version_info[:2]):
        raise ValueError(
            f"Core Python {details['version']} does not match running Isaac Python "
            f"{list(sys.version_info[:2])}; native dependency ABI must match"
        )
    with tempfile.TemporaryDirectory(prefix="geochora-isaac-core-site-") as temporary:
        overlay = Path(temporary)
        populate_isaac_core_site_overlay(details["purelib"], overlay)
        sys.path.append(str(overlay))
        try:
            yield
        finally:
            sys.path.remove(str(overlay))


def package_delivery(*, source_package: Path, output: Path) -> dict[str, object]:
    from task_env.assembly.assets import _source_closure_digest, _source_closure_manifest
    from task_env.assembly.usd_delivery import (
        _canonical_hash, _inspect_snapshot, load_usd_asset_delivery,
        variant_selection_hash,
    )
    from task_env.artifacts import UsdLocalValidationReportV1

    source_package = source_package.resolve(strict=True)
    output = output.absolute()
    source_loaded = load_usd_asset_delivery(source_package / "delivery_manifest.json")
    if not source_loaded.locally_validated or source_loaded.source_verified:
        raise ValueError("F06 source input must remain the existing local Menagerie sample, not upstream verification")
    source_delivery = source_loaded.delivery
    source_files = {}
    for binding in source_delivery.source_files:
        raw = source_package.joinpath(*PurePosixPath(binding.path).parts).read_bytes()
        if len(raw) != binding.size_bytes or _sha(raw) != binding.sha256:
            raise ValueError(f"F06 frozen original Panda input changed: {binding.path}")
        source_files[binding.path] = raw
        _write(output.joinpath(*PurePosixPath(binding.path).parts), raw)
    if _source_closure_digest(source_files) != source_delivery.source_closure_sha256:
        raise ValueError("F06 original Panda input closure differs from its loaded F05 manifest")
    for binding in source_delivery.files:
        raw = source_package.joinpath(*PurePosixPath(binding.path).parts).read_bytes()
        if len(raw) != binding.size_bytes or _sha(raw) != binding.sha256:
            raise ValueError(f"F06 reusable Panda representation changed: {binding.path}")
        _write(output.joinpath(*PurePosixPath(binding.path).parts), raw)

    entry_rel = "pickcube_scene.usda"
    stage, _arm_paths, _leader_path, _ee_path = _read_stage(output, entry_rel)
    validation = _validate_stage(output, entry_rel)
    required, inspection = _inspect_snapshot(output, output / entry_rel, "/F06Scene", {})
    output_files = {relative: output.joinpath(*PurePosixPath(relative).parts).read_bytes()
                    for relative in sorted(required)}
    output_closure_sha = _source_closure_digest(output_files)
    source_inventory = {
        "schema_version": "f04-local-source-inventory-v1",
        "files": list(_source_closure_manifest(source_files)),
        "source_closure_sha256": source_delivery.source_closure_sha256,
    }
    inventory_raw = _json_bytes(source_inventory)
    inventory_rel = "metadata/source_inventory_v1.json"
    _write(output / inventory_rel, inventory_raw)

    recipe_rel = "metadata/pickcube_isaac_recipe_v1.json"
    checker_rel = "metadata/pickcube_isaac_checker_v1.py"
    report_rel = "metadata/pickcube_local_validation_v1.json"
    recipe = {
        "schema_version": "pick-cube-isaac-usd-recipe-v1",
        "recipe_id": "pick-cube-isaac-desktop-scene-v1",
        "recipe_version": "1",
        "source_delivery_sha256": source_delivery.delivery_sha256,
        "source_closure_sha256": source_delivery.source_closure_sha256,
        "source_entry_sha256": source_delivery.source_entry_sha256,
        "entry_file": entry_rel,
        "entry_prim": "/F06Scene",
        "task_recipe": {
            "cube_half_size_m": 0.025,
            "cube_mass_kg": 0.08,
            "cube_diagonal_inertia_kg_m2": [0.08 * 0.05**2 / 6.0] * 3,
            "table_half_size_m": [0.28, 0.20, 0.01],
            "table_center_world_m": [0.5545, 0.0, 0.452],
            "table_top_z_m": 0.462,
            "initial_cube_pose_world_m_wxyz": [0.50, 0.0, 0.488, 1.0, 0.0, 0.0, 0.0],
            "tcp_hand_offset_local_m": [0.0, 0.0, 0.0584],
        },
        "native_adaptation": {
            "arm_dof_units": "radian/radian_per_second",
            "hand_dof_units": "meter/meter_per_second",
            "arm_effort_limit_N": 250.0,
            "gripper_drive_stiffness_N_m": 5000.0,
            "gripper_drive_damping_N_s_m": 120.0,
            "gripper_native_force_limit_N": 5.0,
            "r3_requested_force_limit_N": 30.0,
            "force_mapping": "native source cap remains 5 N; requested R3 force limit is bounded to that source cap",
            "follower_mimic": "source-affine-finger-equality-to-public-PhysxMimicJointAPI-v1",
            "surface_material": "provider-default-no-cross-engine-equivalence-claim",
        },
        "validation": validation,
        "known_losses": [
            "USD default surface friction/restitution is not claimed equivalent to the MJCF contact law.",
            "The native PhysX mimic constraint does not carry MuJoCo solimp impedance shaping.",
            "R3 requests up to 30 N while the task source gripper actuator is limited to 5 N; the native drive preserves the 5 N source cap.",
        ],
    }
    recipe_raw = _json_bytes(recipe)
    checker_raw = Path(__file__).read_bytes()
    _write(output / recipe_rel, recipe_raw)
    _write(output / checker_rel, checker_raw)
    options = {
        "scene_recipe_sha256": _sha(recipe_raw),
        "source_delivery_sha256": source_delivery.delivery_sha256,
        "task_profile": "pick-cube-v1/p1_6_experimental_100hz",
        "representation": "local-isaacsim-6.2-desktop-pickcube-v1",
    }
    options_sha = _canonical_hash(options)
    report_id = "pickcube-isaac-local-validation-v1"
    report = UsdLocalValidationReportV1(
        "usd-local-validation-report-v1", report_id, "local-validated",
        source_delivery.asset_identity_hash, source_delivery.source_revision,
        source_delivery.source_closure_sha256, _sha(inventory_raw),
        source_delivery.source_entry_sha256, variant_selection_hash({}),
        _sha(output_files[entry_rel]), output_closure_sha, "/F06Scene", "usd",
        "isaacsim-6.2.0.0-pickcube-desktop-v1", recipe["recipe_id"], "1",
        _sha(recipe_raw), options_sha, "pickcube-isaac-scene-checker-v1",
        _sha(checker_raw), "Geochora F06 task owner", LOCAL_CHECKS,
        tuple(recipe["known_losses"]),
        (
            "native GPU PhysX consumption is established only by the separate F06 runtime campaign",
            "cross-provider surface-material equivalence is not established",
        ),
        True,
    )
    report_raw = _json_bytes(report.to_mapping())
    _write(output / report_rel, report_raw)
    manifest = {
        "schema_version": "usd-local-derived-delivery-v1",
        "asset_definition": source_delivery.asset_definition.to_mapping(),
        "source_revision": source_delivery.source_revision,
        "provenance_kind": "local-validated",
        "source_closure_sha256": source_delivery.source_closure_sha256,
        "source_manifest_path": inventory_rel,
        "source_manifest_sha256": _sha(inventory_raw),
        "source_files": list(_source_closure_manifest(source_files)),
        "source_entry_file": source_delivery.source_entry_file,
        "source_entry_sha256": source_delivery.source_entry_sha256,
        "source_variant_selections": {},
        "source_variant_selection_sha256": variant_selection_hash({}),
        "entry_file": entry_rel,
        "entry_prim": "/F06Scene",
        "variant_selections": {},
        "representation_format": "usd",
        "representation_id": "isaacsim-6.2.0.0-pickcube-desktop-v1",
        "closure_policy": "f04-selected-derived-scene-v1",
        "files": list(_source_closure_manifest(output_files)),
        "closure_sha256": output_closure_sha,
        "recipe_path": recipe_rel,
        "recipe_sha256": _sha(recipe_raw),
        "checker_path": checker_rel,
        "checker_sha256": _sha(checker_raw),
        "support_files": [],
        "validation_report_path": report_rel,
        "validation_report_sha256": _sha(report_raw),
        "options_sha256": options_sha,
    }
    manifest_rel = "delivery_manifest.json"
    manifest_raw = _json_bytes(manifest)
    _write(output / manifest_rel, manifest_raw)
    loaded = load_usd_asset_delivery(output / manifest_rel)
    if (not loaded.locally_validated or loaded.source_verified
            or loaded.delivery.closure_sha256 != output_closure_sha):
        raise ValueError("F06 source loader did not return exact local validation/provenance")
    return {
        "manifest_path": str(output / manifest_rel),
        "manifest_sha256": _sha(manifest_raw),
        "delivery_sha256": loaded.delivery_sha256,
        "source_closure_sha256": source_delivery.source_closure_sha256,
        "output_closure_sha256": output_closure_sha,
        "inspection": dict(inspection),
        "validation": validation,
        "locally_validated": loaded.locally_validated,
        "source_verified": loaded.source_verified,
        "passed": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--core-python", type=Path,
        default=Path(os.environ["GEOCHORA_CORE_PYTHON"]) if os.environ.get("GEOCHORA_CORE_PYTHON") else None,
        help="matching Core Python 3.12 interpreter used to expose dependencies to Isaac",
    )
    parser.add_argument("--source-package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        with _core_dependency_path(args.core_python):
            result = package_delivery(source_package=args.source_package, output=args.output)
    except ModuleNotFoundError as error:
        raise SystemExit(
            f"required Core/Isaac Python module {error.name!r} is unavailable; "
            "pass --core-python pointing to the matching Geochora Python environment"
        ) from error
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
