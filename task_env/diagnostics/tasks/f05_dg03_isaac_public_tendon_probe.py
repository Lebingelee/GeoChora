"""N1 bounded public Isaac/PhysX probe for Panda prismatic coupling and tendon effort.

This is a diagnostic harness, not the source-bound Core RuntimeSession route.
It opens one exact locally validated DG03 USD delivery, reads the source-derived
PhysX mimic from that composed USD without authoring it, uses public Isaac
Articulation/SimulationManager APIs, and records whether PhysX consumes it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback


SOURCE_CLOSURE_SHA256 = "a59a66d0b176cb6b2634d54cd20744752742b425e5524db1b865dda0eb3adf2a"
SOURCE_XML_SHA256 = "96ad67da03710f17f798c9478fd9e9efdf24a3bf8359f05e456dd9fb158ea273"
TENDON_GAIN = 0.01568627451
TENDON_CTRL_RANGE = (0.0, 255.0)
TENDON_FORCE_RANGE = (-100.0, 100.0)
TENDON_COEFFICIENTS = (0.5, 0.5)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_receipt(path: Path, value: dict[str, object]) -> None:
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()


def _verify_frozen_delivery(manifest_path: Path, expected_manifest_sha256: str) -> dict[str, object]:
    """Recheck byte bindings with stdlib only, before Isaac loads its USD runtime."""
    manifest_raw = manifest_path.read_bytes()
    if hashlib.sha256(manifest_raw).hexdigest() != expected_manifest_sha256:
        raise ValueError("N1 delivery manifest SHA differs from the frozen probe input")
    mapping = json.loads(manifest_raw)
    if mapping.get("schema_version") != "usd-local-derived-delivery-v1":
        raise ValueError("N1 source package is not the exact local derived USD delivery")
    root = manifest_path.parent

    def check_bindings(rows, expected_digest, label):
        checked = []
        for row in rows:
            path = row["path"]
            raw = root.joinpath(*Path(path).parts).read_bytes()
            actual = hashlib.sha256(raw).hexdigest()
            if len(raw) != row["size_bytes"] or actual != row["sha256"]:
                raise ValueError(f"N1 {label} bytes differ from frozen binding: {path}")
            checked.append({"path": path, "size_bytes": len(raw), "sha256": actual})
        digest = _canonical_digest({
            "schema_version": "source-closure-v1",
            "files": sorted(checked, key=lambda item: item["path"]),
        })
        if digest != expected_digest:
            raise ValueError(f"N1 {label} closure digest mismatch")
        return digest

    if mapping.get("source_closure_sha256") != SOURCE_CLOSURE_SHA256:
        raise ValueError("N1 source package closure differs from exact Menagerie source")
    source_inventory_raw = root.joinpath(*Path(mapping["source_manifest_path"]).parts).read_bytes()
    if hashlib.sha256(source_inventory_raw).hexdigest() != mapping["source_manifest_sha256"]:
        raise ValueError("N1 source inventory manifest hash mismatch")
    source_inventory = json.loads(source_inventory_raw)
    if source_inventory.get("source_closure_sha256") != SOURCE_CLOSURE_SHA256:
        raise ValueError("N1 source inventory differs from the frozen Menagerie closure")
    check_bindings(mapping["source_files"], SOURCE_CLOSURE_SHA256, "source")
    check_bindings(mapping["files"], mapping["closure_sha256"], "USD output")
    source_entry = root.joinpath(*Path(mapping["source_entry_file"]).parts).read_bytes()
    entry = root.joinpath(*Path(mapping["entry_file"]).parts).read_bytes()
    if (hashlib.sha256(source_entry).hexdigest() != SOURCE_XML_SHA256
            or hashlib.sha256(source_entry).hexdigest() != mapping["source_entry_sha256"]):
        raise ValueError("N1 exact source MJCF entry hash mismatch")
    entry_binding = next((row for row in mapping["files"] if row["path"] == mapping["entry_file"]), None)
    if entry_binding is None or hashlib.sha256(entry).hexdigest() != entry_binding["sha256"]:
        raise ValueError("N1 exact derived USD entry hash mismatch")
    for path_key, sha_key in (("recipe_path", "recipe_sha256"),
                              ("checker_path", "checker_sha256"),
                              ("validation_report_path", "validation_report_sha256")):
        raw = root.joinpath(*Path(mapping[path_key]).parts).read_bytes()
        if hashlib.sha256(raw).hexdigest() != mapping[sha_key]:
            raise ValueError(f"N1 bound local metadata hash mismatch: {path_key}")
        if path_key == "recipe_path":
            recipe = json.loads(raw)
    for row in mapping.get("support_files", ()):
        raw = root.joinpath(*Path(row["path"]).parts).read_bytes()
        if len(raw) != row["size_bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError(f"N1 local support file hash mismatch: {row['path']}")
    return {
        "delivery_sha256": _canonical_digest(mapping),
        "derived_closure_sha256": mapping["closure_sha256"],
        "entry_file": str(root / mapping["entry_file"]),
        "entry_sha256": hashlib.sha256(entry).hexdigest(),
        "source_verified": False,
        "locally_validated": True,
        "source_equality_mapping": recipe["derivation"]["overlay_receipt"]["source_equality_mapping"],
    }


def _terminate_worker(exit_code: int) -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except (OSError, ValueError):
            pass
    os._exit(int(exit_code))


def _remove_source_mimic_for_ablation(follower) -> tuple[str, ...]:
    """Remove only the composed source mimic relation from this in-memory stage."""
    schema_token = "PhysxMimicJointAPI:transX"
    properties = (
        "physxMimicJoint:transX:referenceJoint",
        "physxMimicJoint:transX:gearing",
        "physxMimicJoint:transX:offset",
        "physxMimicJoint:transX:naturalFrequency",
        "physxMimicJoint:transX:dampingRatio",
    )
    if not follower.RemoveAppliedSchema(schema_token):
        raise ValueError("mimic ablation could not remove the exact applied API token")
    for property_name in properties:
        prop = follower.GetProperty(property_name)
        if not prop or not prop.IsValid() or not follower.RemoveProperty(property_name):
            raise ValueError(f"mimic ablation could not remove the exact relation property: {property_name}")
    api_schemas = follower.GetMetadata("apiSchemas")
    if api_schemas and schema_token in api_schemas.GetAppliedItems():
        raise ValueError("mimic ablation left the PhysX API token on the runtime stage")
    return properties


def run_probe(
    manifest_path: Path, expected_manifest_sha256: str, receipt_path: Path,
    *, ablate_source_mimic: bool = False,
) -> int:
    started = time.monotonic()
    result: dict[str, object] = {
        "schema_version": "f05-dg03-n1-source-mimic-probe-v2",
        "probe_mode": "source_mimic_ablation" if ablate_source_mimic else "source_mimic_positive",
        "manifest_path": str(manifest_path),
        "manifest_sha256_expected": expected_manifest_sha256,
        "source_closure_sha256_expected": SOURCE_CLOSURE_SHA256,
        "source_xml_sha256_expected": SOURCE_XML_SHA256,
        "eula_acceptance_env": os.environ.get("OMNI_KIT_ACCEPT_EULA"),
        "app_started": False,
        "public_apis_used": [],
        "mimic_schema_authored": False,
        "mimic_relation_active_in_runtime_stage": False,
        "mimic_api_removed_for_ablation": False,
        "runtime_stage_mutated": False,
        "counterfactual_identity_sha256": None,
        "mimic_leader_motion_m": None,
        "ablation_no_coupling_detected": False,
        "mimic_schema_supported": False,
        "mimic_reference_joint": None,
        "mimic_q_difference_max_m": None,
        "mimic_follower_motion_m": None,
        "tendon_effort_write_succeeded": False,
        "tendon_ctrl_samples": [],
        "tendon_force_samples_N": [],
        "tendon_finger_efforts_N": [],
        "tendon_joint_motion_m": None,
        "physics_steps": 0,
        "passed": False,
    }
    app = None
    status = 1
    try:
        if os.environ.get("OMNI_KIT_ACCEPT_EULA") != "YES":
            raise RuntimeError("user-authorized NVIDIA EULA setting is absent")
        if _sha(manifest_path) != expected_manifest_sha256:
            raise ValueError("N1 delivery manifest SHA differs from the frozen probe input")
        delivery_facts = _verify_frozen_delivery(manifest_path, expected_manifest_sha256)
        result.update(delivery_facts)
        report_mapping = json.loads((manifest_path.parent / "metadata/f05_dg03_local_validation_report.json").read_text())
        result["local_unconsumed"] = list(report_mapping["unconsumed"])

        from isaacsim.simulation_app import SimulationApp

        app = SimulationApp({
            "headless": True,
            "enable_cameras": False,
            "limit_cpu_threads": 4,
            "fast_shutdown": False,
        })
        result["app_started"] = True
        import carb
        import omni.usd
        import torch
        from isaacsim.core.experimental.prims import Articulation
        from isaacsim.core.experimental.utils import app as app_utils
        from isaacsim.core.simulation_manager import SimulationManager
        from pxr import PhysxSchema, UsdGeom, UsdPhysics

        result["public_apis_used"] = [
            "SimulationManager.setup_simulation/step/get_num_physics_steps/get_simulation_time",
            "Articulation.dof_names/get_dof_positions/get_dof_velocities/set_dof_positions/set_dof_velocities/set_dof_efforts",
            "composed PhysxMimicJointAPI HasAPI/referenceJoint/attributes (read-only)",
        ]
        task_threads = int(carb.settings.get_settings().get_as_int("/plugins/carb.tasking.plugin/threadCount"))
        result["kit_task_threads"] = task_threads
        if not 1 <= task_threads <= 4:
            raise RuntimeError(f"Kit tasking pool exceeds the frozen four-thread cap: {task_threads}")
        if not torch.cuda.is_available() or torch.cuda.current_device() != 0:
            raise RuntimeError("N1 requires CUDA device 0 and does not admit CPU fallback")
        result["gpu_device"] = torch.cuda.get_device_name(0)
        if SimulationManager.get_active_physics_engine() != "physx":
            raise RuntimeError("N1 requires the public PhysX engine")

        context = omni.usd.get_context()
        if context.get_stage() is not None:
            context.close_stage()
        entry = result["entry_file"]
        if context.open_stage(entry) is False:
            raise RuntimeError("public USD context rejected exact DG03 delivery entry")
        stage = context.get_stage()
        if stage is None:
            raise RuntimeError("public USD context did not publish the DG03 stage")
        if (float(UsdGeom.GetStageMetersPerUnit(stage)), str(UsdGeom.GetStageUpAxis(stage))) != (1.0, "Z"):
            raise ValueError("N1 stage units/up-axis differ from exact local delivery validation")

        joints = {}
        for prim in stage.Traverse():
            if prim.GetName() in {"finger_joint1", "finger_joint2"}:
                if not prim.IsA(UsdPhysics.PrismaticJoint):
                    raise ValueError(f"source finger Joint is not prismatic: {prim.GetPath()}")
                joints[prim.GetName()] = prim
        if set(joints) != {"finger_joint1", "finger_joint2"}:
            raise ValueError("N1 did not locate exactly the source pair of prismatic finger joints")
        result["finger_joint_paths"] = {name: str(prim.GetPath()) for name, prim in joints.items()}

        source_mimic = delivery_facts["source_equality_mapping"]
        if not joints["finger_joint2"].HasAPI(PhysxSchema.PhysxMimicJointAPI, "transX"):
            raise ValueError("source-derived PhysxMimicJointAPI is absent from the composed delivery")
        mimic_relationship = joints["finger_joint2"].GetRelationship(
            "physxMimicJoint:transX:referenceJoint"
        )
        if (not mimic_relationship
                or mimic_relationship.GetTargets() != [joints["finger_joint1"].GetPath()]):
            raise ValueError("composed source-derived mimic reference differs from exact MJCF equality")
        source_to_physx_attributes = {
            "gearing": "physx_gearing",
            "offset": "physx_offset_m",
            "naturalFrequency": "physx_natural_frequency_hz",
            "dampingRatio": "physx_damping_ratio",
        }
        result["mimic_physx_attributes"] = {}
        for attr_name, source_key in source_to_physx_attributes.items():
            attr = joints["finger_joint2"].GetAttribute(f"physxMimicJoint:transX:{attr_name}")
            expected = float(source_mimic[source_key])
            if (not attr or not attr.IsValid()
                    or not math.isclose(float(attr.Get()), expected, rel_tol=0.0, abs_tol=1e-6)):
                raise ValueError(f"composed source-derived mimic field differs from source: {attr_name}")
            result["mimic_physx_attributes"][attr_name] = float(attr.Get())
        result["mimic_schema_authored"] = False
        result["mimic_schema_from_source_delivery"] = True
        result["source_mimic_mapping"] = source_mimic
        result["mimic_reference_joint"] = str(joints["finger_joint1"].GetPath())
        result["mimic_applied_schema"] = list(joints["finger_joint2"].GetAppliedSchemas())
        if ablate_source_mimic:
            removed_properties = _remove_source_mimic_for_ablation(joints["finger_joint2"])
            result["mimic_api_removed_for_ablation"] = True
            result["runtime_stage_mutated"] = True
            result["ablation_removed_properties"] = list(removed_properties)
            counterfactual = {
                "base_delivery_sha256": delivery_facts["delivery_sha256"],
                "base_entry_sha256": delivery_facts["entry_sha256"],
                "removed_schema": "PhysxMimicJointAPI:transX",
                "removed_properties": list(removed_properties),
            }
            result["counterfactual_identity_sha256"] = hashlib.sha256(
                json.dumps(counterfactual, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            ).hexdigest()
            if joints["finger_joint2"].HasAPI(PhysxSchema.PhysxMimicJointAPI, "transX"):
                raise ValueError("mimic ablation left the API applied to the runtime prim")
            result["mimic_relation_active_in_runtime_stage"] = False
        else:
            result["mimic_relation_active_in_runtime_stage"] = True

        SimulationManager.setup_simulation(dt=0.002, device="cuda:0")
        scenes = SimulationManager.get_physics_scenes()
        if len(scenes) != 1:
            raise RuntimeError(f"public PhysX compiled {len(scenes)} scenes instead of one")
        scenes[0].set_enabled_gpu_dynamics(True)
        if scenes[0].get_enabled_gpu_dynamics() is not True:
            raise RuntimeError("GPU dynamics did not remain enabled")
        if str(SimulationManager.get_device()) != "cuda:0":
            raise RuntimeError("SimulationManager changed away from cuda:0")
        roots = [prim for prim in stage.Traverse() if prim.HasAPI(UsdPhysics.ArticulationRootAPI)]
        if len(roots) != 1:
            raise RuntimeError("exact USD must contain one public articulation root")
        articulation = Articulation(str(roots[0].GetPath()))
        names = tuple(str(name) for name in articulation.dof_names)
        expected_names = tuple(f"joint{index}" for index in range(1, 8)) + ("finger_joint1", "finger_joint2")
        if names != expected_names:
            raise ValueError(f"N1 public DOF order differs from expected exact source mapping: {names!r}")
        index = {name: pos for pos, name in enumerate(names)}
        before = (int(SimulationManager.get_num_physics_steps()), float(SimulationManager.get_simulation_time()))
        app_utils.play()
        app_utils.update_app(steps=2)
        after = (int(SimulationManager.get_num_physics_steps()), float(SimulationManager.get_simulation_time()))
        bootstrap_steps = after[0] - before[0]
        result["bootstrap_physics_steps"] = bootstrap_steps
        result["physics_steps"] = bootstrap_steps
        physics_counter_origin = before[0]

        zero = [0.0] * len(names)
        positions = list(zero)
        positions[index["joint4"]] = -1.57
        articulation.set_dof_positions(positions)
        articulation.set_dof_velocities(zero)
        torch.cuda.synchronize(0)
        baseline_readback = articulation.get_dof_positions()
        result["position_readback_type"] = (
            f"{type(baseline_readback).__module__}.{type(baseline_readback).__name__}"
        )
        result["position_readback_conversion"] = (
            "Warp array.numpy()" if callable(getattr(baseline_readback, "numpy", None))
            else "tensor/list/sequence scalar flatten"
        )
        baseline = _rows(baseline_readback, len(names))
        q1_initial = baseline[index["finger_joint1"]]
        q2_initial = baseline[index["finger_joint2"]]
        mimic_diffs = []
        follower_deltas = []
        attempted = 0
        for _ in range(30):
            q1, _q2, _qd1, _qd2 = _finger_state(articulation, index, len(names))
            articulation.set_dof_efforts([4.0], dof_indices=[index["finger_joint1"]])
            attempted += 1
            result["physics_steps"] += 1
            SimulationManager.step(steps=1, update_fabric=False)
            torch.cuda.synchronize(0)
            q1, q2, _qd1, _qd2 = _finger_state(articulation, index, len(names))
            mimic_diffs.append(abs(q1 - q2))
            follower_deltas.append(abs(q2 - q2_initial))
            result["mimic_q_difference_max_m"] = max(mimic_diffs)
            result["mimic_follower_motion_m"] = max(follower_deltas)

        result["mimic_q_difference_max_m"] = max(mimic_diffs, default=math.inf)
        result["mimic_follower_motion_m"] = max(follower_deltas, default=0.0)
        result["mimic_leader_motion_m"] = abs(q1 - q1_initial)
        result["mimic_schema_supported"] = bool(
            result["mimic_relation_active_in_runtime_stage"]
            and result["mimic_follower_motion_m"] >= 1e-4
            and result["mimic_q_difference_max_m"] <= 2e-3
        )

        if ablate_source_mimic:
            result["ablation_no_coupling_detected"] = bool(
                result["mimic_leader_motion_m"] >= 1e-4
                and result["mimic_follower_motion_m"] < 1e-4
                and result["mimic_q_difference_max_m"] > 2e-3
                and not result["mimic_schema_supported"]
            )
        else:
            source_efforts = []
            source_forces = []
            source_ctrls = []
            target_opening_m = 0.04
            for _ in range(30):
                q1, q2, qd1, qd2 = _finger_state(articulation, index, len(names))
                ctrl = min(TENDON_CTRL_RANGE[1], max(TENDON_CTRL_RANGE[0], 255.0 * target_opening_m / 0.08))
                tendon_length = TENDON_COEFFICIENTS[0] * q1 + TENDON_COEFFICIENTS[1] * q2
                tendon_rate = TENDON_COEFFICIENTS[0] * qd1 + TENDON_COEFFICIENTS[1] * qd2
                force = min(TENDON_FORCE_RANGE[1], max(
                    TENDON_FORCE_RANGE[0], TENDON_GAIN * ctrl - 100.0 * tendon_length - 10.0 * tendon_rate,
                ))
                dof_efforts = [
                    TENDON_COEFFICIENTS[0] * force,
                    TENDON_COEFFICIENTS[1] * force,
                ]
                articulation.set_dof_efforts(
                    dof_efforts,
                    dof_indices=[index["finger_joint1"], index["finger_joint2"]],
                )
                attempted += 1
                result["physics_steps"] += 1
                source_ctrls.append(ctrl)
                source_forces.append(force)
                source_efforts.append(dof_efforts)
                result["tendon_ctrl_samples"] = [float(source_ctrls[0]), float(source_ctrls[-1])]
                result["tendon_force_samples_N"] = [float(source_forces[0]), float(source_forces[-1])]
                result["tendon_finger_efforts_N"] = [float(x) for x in source_efforts[-1]]
                SimulationManager.step(steps=1, update_fabric=False)
                torch.cuda.synchronize(0)
                attempted += 1
            final = _rows(articulation.get_dof_positions(), len(names))
            result["tendon_effort_write_succeeded"] = True
            result["tendon_ctrl_samples"] = [float(source_ctrls[0]), float(source_ctrls[-1])]
            result["tendon_force_samples_N"] = [float(source_forces[0]), float(source_forces[-1])]
            result["tendon_finger_efforts_N"] = [float(x) for x in source_efforts[-1]]
            result["tendon_joint_motion_m"] = [
                float(final[index["finger_joint1"]] - q1_initial),
                float(final[index["finger_joint2"]] - q2_initial),
            ]
            result["tendon_source_law"] = {
                "ctrl_formula": "clip(255 * opening_m / 0.08, 0, 255)",
                "force_formula": "clip(0.01568627451 * ctrl - 100 * tendon_length - 10 * tendon_rate, -100, 100)",
                "tendon_length_formula": "0.5*q_finger1 + 0.5*q_finger2",
                "tendon_rate_formula": "0.5*qd_finger1 + 0.5*qd_finger2",
                "effort_mapping": "J^T force = [0.5*force, 0.5*force]",
            }
            result["force_clamp_extreme_oracle_N"] = min(
                TENDON_FORCE_RANGE[1], max(
                    TENDON_FORCE_RANGE[0], TENDON_GAIN * 255.0 - 100.0 * (-2.0) - 10.0 * (-10.0),
                ),
            )
        final_counter = int(SimulationManager.get_num_physics_steps())
        result["public_step_counter_delta"] = final_counter - physics_counter_origin
        result["delivery_entry_sha256_after_runtime"] = _sha(Path(entry))
        if result["delivery_entry_sha256_after_runtime"] != delivery_facts["entry_sha256"]:
            raise ValueError("N1 runtime stage mutation changed the frozen delivery file on disk")
        if result["physics_steps"] > 500:
            raise RuntimeError("N1 exceeded the 500-physics-step probe cap")
        result["physics_dt_s"] = 0.002
        result["physics_device"] = str(SimulationManager.get_device())
        result["gpu_dynamics"] = scenes[0].get_enabled_gpu_dynamics()
        if ablate_source_mimic:
            result["passed"] = bool(
                result["mimic_api_removed_for_ablation"]
                and result["ablation_no_coupling_detected"]
                and result["physics_device"] == "cuda:0"
                and result["gpu_dynamics"] is True
            )
        else:
            result["passed"] = bool(
                result["mimic_schema_supported"]
                and result["tendon_effort_write_succeeded"]
                and result["force_clamp_extreme_oracle_N"] == 100.0
                and all(math.isfinite(float(value)) for value in result["tendon_joint_motion_m"])
                and result["physics_device"] == "cuda:0"
                and result["gpu_dynamics"] is True
            )
        status = 0 if result["passed"] else 2
    except BaseException as error:
        result["error"] = f"{type(error).__name__}: {error}"
        result["error_traceback"] = traceback.format_exc()
        result["passed"] = False
        status = 1
    finally:
        result["elapsed_s"] = time.monotonic() - started
        if app is not None:
            try:
                app.close()
                result["app_close_completed"] = True
            except BaseException as error:
                result["app_close_completed"] = False
                result["app_close_error"] = f"{type(error).__name__}: {error}"
                status = 1
        _write_receipt(receipt_path, result)
    _terminate_worker(status)
    return status


def _rows(value, width: int) -> list[float]:
    values: list[float] = []

    def flatten(item):
        if hasattr(item, "detach"):
            item = item.detach()
        if hasattr(item, "cpu"):
            item = item.cpu()
        if callable(getattr(item, "numpy", None)):
            converted = item.numpy()
            if converted is not item:
                flatten(converted)
                return
        if hasattr(item, "tolist") and not isinstance(item, (list, tuple)):
            converted = item.tolist()
            if converted is not item:
                flatten(converted)
                return
        if not isinstance(item, (str, bytes, bytearray, dict)):
            try:
                iterator = iter(item)
            except TypeError:
                iterator = None
            if iterator is not None:
                for child in iterator:
                    flatten(child)
                return
        values.append(float(item))

    flatten(value)
    if len(values) != width or any(not math.isfinite(item) for item in values):
        raise ValueError("public DOF tensor row has an invalid width or nonfinite values")
    return values


def _finger_state(articulation, index, width):
    q = _rows(articulation.get_dof_positions(), width)
    qd = _rows(articulation.get_dof_velocities(), width)
    return q[index["finger_joint1"]], q[index["finger_joint2"]], qd[index["finger_joint1"]], qd[index["finger_joint2"]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--ablate-source-mimic", action="store_true")
    args = parser.parse_args()
    run_probe(args.manifest, args.manifest_sha256, args.receipt,
              ablate_source_mimic=args.ablate_source_mimic)


if __name__ == "__main__":
    main()
