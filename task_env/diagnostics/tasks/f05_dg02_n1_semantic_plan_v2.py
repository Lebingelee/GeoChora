"""Freeze the v2 public-consumer tendon/equality probe and its source variants."""

from __future__ import annotations

import fcntl
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from pxr import Sdf, Usd, Vt


CORE = Path("/home/lly/Program_Files/Geochora")
WINDOW = CORE / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f05_diagnostic_goal02/window_001"
PROVIDER = CORE / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f05_geophys_provider/GeoPhys"
PREVIOUS = WINDOW / "host_g2_001/n0_model_compile_008/plan.json"
PARENT_RECEIPT = WINDOW / "host_g2_001/n0_model_compile_008/supervisor_receipt.json"
PARENT_WORKER_RECEIPT = WINDOW / "host_g2_001/n0_model_compile_008/process/worker_receipt.json"
LOCK = CORE / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/shared_native_execution.lock"
RUNS_DIR = WINDOW / "host_g2_001"
ORIGINAL_PHYSICAL_ORACLE = CORE / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_f05_dg02_001/original_physical_oracle.json"
WORKER = CORE / "task_env/diagnostics/tasks/f05_dg02_n1_semantic_probe.py"
SUPERVISOR = CORE / "task_env/diagnostics/tasks/f05_dg02_n1_supervisor.py"
BUILDER = Path(__file__).resolve()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str, cwd: Path = CORE) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def tracked_input(path: Path) -> dict[str, str]:
    path = path.resolve(strict=True)
    return {"path": str(path), "sha256": sha(path)}


def mem_available() -> int:
    return next(
        int(line.split()[1]) * 1024
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith("MemAvailable:")
    )


def make_variant(source_path: Path, destination: Path, *, label: str, relation_active: bool, remove_equality: bool = False) -> dict:
    source_hash = sha(source_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copy2(source_path, destination)
        stage = Usd.Stage.Open(str(destination))
        if stage is None:
            raise RuntimeError(f"cannot open diagnostic USD variant {destination}")
        root = stage.GetDefaultPrim()
        semantic_attr = root.GetAttribute("geochora:f05SourceSemantics")
        if not root or not semantic_attr or not semantic_attr.IsValid():
            raise ValueError("v2 source semantics attribute missing from USD default prim")
        semantics = json.loads(semantic_attr.Get())
        if semantics.get("schema_version") != "geochora.f05-source-semantics.v2":
            raise ValueError("diagnostic variant requires exact v2 source semantics")
        if len(semantics.get("actuators", ())) != 8:
            raise ValueError("diagnostic variant requires eight source actuators")
        for actuator in semantics["actuators"]:
            actuator["gain_prm"] = [0.0] * len(actuator["gain_prm"])
            actuator["bias_prm"] = [0.0] * len(actuator["bias_prm"])
            prim = stage.GetPrimAtPath(f"/panda/Physics/{actuator['name']}")
            if not prim or not prim.IsValid():
                raise ValueError(f"USD actuator prim missing: {actuator['name']}")
            for attribute_name in ("mjc:gainPrm", "mjc:biasPrm"):
                attribute = prim.GetAttribute(attribute_name)
                if not attribute or not attribute.IsValid():
                    raise ValueError(f"USD actuator attribute missing: {actuator['name']}.{attribute_name}")
                attribute.Set(Vt.DoubleArray([0.0] * len(attribute.Get())))
        if remove_equality:
            semantics["equalities"] = []
        else:
            if len(semantics.get("equalities", ())) != 1:
                raise ValueError("equality variant requires exactly one source relation")
            semantics["equalities"][0]["active"] = bool(relation_active)
        semantic_attr.Set(json.dumps(semantics, sort_keys=True, separators=(",", ":")))
        marker = root.CreateAttribute("geochora:f05DG02ProbeVariant", Sdf.ValueTypeNames.String, custom=True)
        marker.Set(label)
        stage.GetRootLayer().Save()

    # Cold-read the exact bytes before they are frozen into the plan. Existing
    # variants are accepted only if their semantics still match this transform.
    stage = Usd.Stage.Open(str(destination))
    if stage is None:
        raise RuntimeError(f"cannot cold-read diagnostic USD variant {destination}")
    root = stage.GetDefaultPrim()
    semantic_attr = root.GetAttribute("geochora:f05SourceSemantics")
    semantics = json.loads(semantic_attr.Get())
    if root.GetAttribute("geochora:f05DG02ProbeVariant").Get() != label:
        raise ValueError(f"diagnostic USD variant marker mismatch: {label}")
    if len(semantics.get("actuators", ())) != 8:
        raise ValueError("diagnostic variant changed the actuator count")
    if any(any(float(x) != 0.0 for x in a["gain_prm"] + a["bias_prm"]) for a in semantics["actuators"]):
        raise ValueError("diagnostic variant actuator disable transform is incomplete")
    if remove_equality and semantics.get("equalities") != []:
        raise ValueError("negative equality variant still contains a source equality")
    if not remove_equality and (len(semantics.get("equalities", ())) != 1 or semantics["equalities"][0].get("active") is not bool(relation_active)):
        raise ValueError("equality variant lost its requested source relation active state")
    for actuator in semantics["actuators"]:
        prim = stage.GetPrimAtPath(f"/panda/Physics/{actuator['name']}")
        for name in ("mjc:gainPrm", "mjc:biasPrm"):
            if any(float(x) != 0.0 for x in prim.GetAttribute(name).Get()):
                raise ValueError(f"diagnostic variant left authored drive force active: {actuator['name']}.{name}")
    return {
        "path": str(destination.resolve()),
        "sha256": sha(destination),
        "source_stage_sha256": source_hash,
        "variant": label,
        "transform": {
            "all_eight_actuator_gain_and_bias_parameters_zeroed": True,
            "equality_removed": remove_equality,
            "equality_active": None if remove_equality else bool(relation_active),
            "retained_actuator_count": len(semantics["actuators"]),
            "retained_equality_count": len(semantics.get("equalities", ())),
        },
    }


def build(*, suffix: str, expected_starts: int, expected_steps: int) -> Path:
    if not suffix.isdigit() or len(suffix) != 3:
        raise ValueError("N1 run suffix must be exactly three digits")
    run_name = f"n1_public_consumer_{suffix}"
    run_dir = RUNS_DIR / run_name
    variants_dir = RUNS_DIR / f"{run_name}_variants_v2c"
    if run_dir.exists():
        raise FileExistsError(f"N1 output already exists: {run_dir}")
    previous = json.loads(PREVIOUS.read_text())
    parent = json.loads(PARENT_RECEIPT.read_text())
    parent_worker = json.loads(PARENT_WORKER_RECEIPT.read_text())
    if previous.get("run_id") != "DG02_N0_PUBLIC_MODEL_COMPILE_008_V2_CONTACT_MATERIAL_F32_ORACLE":
        raise ValueError("N1 v2 plan must bind the successful N0_008 source-model compile")
    if parent.get("exit_code") != 0 or parent.get("physics_steps") != 0 or not parent.get("lock_released_after_process_group_exit"):
        raise ValueError("N0_008 supervisor evidence is incomplete or not a zero-step pass")
    if parent_worker.get("backend_initialized") is not False or parent_worker.get("tripwire_counts", {}).get("solver_construct") != 0:
        raise ValueError("N0_008 unexpectedly initialized or constructed a solver")
    identity = previous["input_identity"]
    if git("rev-parse", "HEAD") != identity["core_input_head"] or git("branch", "--show-current") != identity["core_branch"]:
        raise RuntimeError("Core branch/HEAD differs from the N0_008 frozen identity")
    if git("-C", str(PROVIDER), "rev-parse", "HEAD") != identity["provider_input_head"] or git("-C", str(PROVIDER), "branch", "--show-current") != identity["provider_branch"]:
        raise RuntimeError("provider branch/HEAD differs from the N0_008 frozen identity")
    progress = json.loads((WINDOW / "goal_progress.json").read_text())
    native = progress["native"]
    if native["geophys_starts"] != expected_starts or native["geophys_steps"] != expected_steps or native["probe_steps"] != expected_steps:
        raise RuntimeError(f"cumulative N1 counters changed since the planned freeze: {native}")
    lock_stream = LOCK.open("a+")
    try:
        try:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("shared native lock is occupied") from exc
        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)
    finally:
        lock_stream.close()
    available = mem_available()
    if available < 6 * 1024**3:
        raise RuntimeError(f"native resource gate failed: MemAvailable={available}")

    source = dict(previous["source"])
    source["parent_model_compile_plan"] = {"path": str(PREVIOUS.resolve()), "sha256": sha(PREVIOUS)}
    source["parent_model_compile_receipt"] = {"path": str(PARENT_RECEIPT.resolve()), "sha256": sha(PARENT_RECEIPT)}
    source["parent_model_compile_worker_receipt"] = {"path": str(PARENT_WORKER_RECEIPT.resolve()), "sha256": sha(PARENT_WORKER_RECEIPT)}
    stage_path = Path(source["usd_stage"]["path"]).resolve(strict=True)
    positive = make_variant(stage_path, variants_dir / "panda_equal_active_actuators_disabled.usda", label="equality-positive-actuators-zeroed", relation_active=True)
    negative = make_variant(stage_path, variants_dir / "panda_equal_inactive_actuators_disabled.usda", label="equality-inactive-actuators-zeroed", relation_active=False)
    removed = make_variant(stage_path, variants_dir / "panda_equality_removed_actuators_disabled.usda", label="equality-removed-actuators-zeroed", relation_active=False, remove_equality=True)
    source["equality_positive_variant_stage"] = {"path": positive["path"], "sha256": positive["sha256"]}
    source["equality_negative_variant_stage"] = {"path": negative["path"], "sha256": negative["sha256"]}
    source["equality_removed_variant_stage"] = {"path": removed["path"], "sha256": removed["sha256"]}
    variants_manifest = {
        "schema_version": "f05-dg02-n1-diagnostic-usd-variants-v1",
        "source_stage_path": str(stage_path),
        "source_stage_sha256": sha(stage_path),
        "source_delivery_identity_sha256": source["delivery_identity_sha256"],
        "positive": positive,
        "negative": negative,
        "removed_relation_negative": removed,
        "scope": "diagnostic-only; all eight actuators zeroed to isolate the source equality; source v2 stage remains unchanged",
    }
    variants_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = variants_dir / "variants_manifest.json"
    manifest_raw = (json.dumps(variants_manifest, sort_keys=True, indent=2) + "\n").encode()
    if manifest_path.exists() and manifest_path.read_bytes() != manifest_raw:
        raise ValueError("existing diagnostic-variant manifest differs; preserve and allocate a new unique run")
    if not manifest_path.exists():
        manifest_path.write_bytes(manifest_raw)
    source["diagnostic_variants_manifest"] = {"path": str(manifest_path.resolve()), "sha256": sha(manifest_path)}
    source["mjcf_source"] = {
        "path": str(CORE / "asset/external/mujoco_menagerie/franka_emika_panda/panda.xml"),
        "sha256": previous["source"]["source_mjcf_sha256"],
    }
    source["original_physical_oracle"] = tracked_input(ORIGINAL_PHYSICAL_ORACLE)
    physical_oracle = json.loads(ORIGINAL_PHYSICAL_ORACLE.read_text())
    arm_home_qpos = {
        f"joint{i}": float(physical_oracle["physical_acceptance"]["home_joint_position_rad"][f"joint{i}"])
        for i in range(1, 8)
    }

    # Public importer/IR preflight for both dynamic identities and the required-
    # relation removal negative; no rigid-model compile, backend init or physics.
    from scene import SceneSource, import_scene_source
    from scene.solver_scene import solver_scene_to_articulation_config

    variant_preflight = {}
    for key, row, expected_equalities, expected_active in (
        ("positive", positive, 1, True),
        ("negative", negative, 1, False),
    ):
        imported = import_scene_source(SceneSource.usd_path(Path(row["path"]), label=f"N1_{key}_preflight"), cache=False)
        solver_scene = imported.build_solver_scene_desc(mesh_collision_policy="strict")
        articulation = solver_scene_to_articulation_config(solver_scene, usd_joint_anchor_tolerance=0.0)
        errors = articulation.validate()
        if errors:
            raise ValueError(f"{key} equality variant public articulation validation failed: {errors}")
        if len(articulation.actuators) != 8 or len(articulation.equalities) != expected_equalities:
            raise ValueError(f"{key} equality variant public counts mismatch")
        if any(any(float(x) != 0.0 for x in tuple(a.gain_prm) + tuple(a.bias_prm)) for a in articulation.actuators):
            raise ValueError(f"{key} equality variant public source actuator force is not fully disabled")
        if bool(articulation.equalities[0].active) is not expected_active:
            raise ValueError(f"{key} equality variant active state mismatch")
        if key == "positive" and tuple(articulation.equalities[0].solref) != (0.005, 1.0):
            raise ValueError("positive equality variant lost exact source compliance")
        variant_preflight[key] = {
            "format": imported.format,
            "ir_semantic_hash": imported.ir_semantic_hash,
            "source_graph_hash": imported.source_graph_hash,
            "actuators": len(articulation.actuators),
            "equalities": len(articulation.equalities),
            "equality_active": bool(articulation.equalities[0].active),
            "all_actuator_gain_bias_zero": True,
        }
    try:
        removed_import = import_scene_source(SceneSource.usd_path(Path(removed["path"]), label="N1_removed_equality_preflight"), cache=False)
    except ValueError as exc:
        expected_message = "F05 source semantics equalities must be a nonempty array of objects"
        if expected_message not in str(exc):
            raise
        variant_preflight["removed_relation_negative"] = {
            "status": "EXPECTED_IMPORT_REJECTION",
            "error": str(exc),
            "rejection_layer": "public USD source-semantics importer",
            "reason": "required equality relation was removed from the explicit diagnostic variant",
        }
    else:
        raise ValueError(f"removed-equality negative unexpectedly imported: {removed_import.ir_semantic_hash}")

    code_paths = {row["path"] for row in previous["code"]["tracked_inputs"]}
    code_paths.update(str(path.resolve()) for path in (
        BUILDER,
        WORKER,
        SUPERVISOR,
        PROVIDER / "src/solvers/rigid/state/host_io.py",
        PROVIDER / "src/solvers/rigid/equality/row_law.py",
        PROVIDER / "src/solvers/rigid/batch/equalities.py",
        PROVIDER / "src/solvers/rigid/batch/tendons.py",
        PROVIDER / "src/solvers/rigid/articulation/generalized_dynamics.py",
        PROVIDER / "test/verification/rigid/test_rigid_state_host_io.py",
    ))
    code = [tracked_input(Path(path)) for path in sorted(code_paths)]
    limits = {
        "native_starts_before": native["geophys_starts"],
        "physics_steps_before": native["geophys_steps"],
        "probe_physics_steps_before": native["probe_steps"],
        "physics_steps_reserved": 4,
        "per_probe_steps_max": 500,
        "worker_wall_s_max": 900,
        "sample_interval_s": 0.25,
        "start_native_mem_available_bytes_min": 6442450944,
        "abort_mem_available_bytes_below": 1073741824,
        "native_process_group_sampled_rss_bytes_max": 4294967296,
        "native_log_bytes_max": 134217728,
        "cpu_threads_max": 4,
        "term_grace_s": 5,
        "shared_native_lock_path": str(LOCK),
        "preflight_mem_available_bytes": available,
        "shared_native_lock_available_at_freeze": True,
        "global_physics_steps_max": 72000,
        "geophys_physics_steps_max": 66000,
        "probe_physics_steps_max": 18000,
        "cumulative_geophys_wall_s_before": native["geophys_wall_s"],
    }
    plan = {
        "schema_version": "f05-dg02-n1-public-consumer-plan-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "classification": "source-bound GeoPhys/USD public-consumer diagnostic; not qualification",
        "run_id": f"DG02_N1_V2_PRESTEP_TENDON_AND_EQUALITY_POSITIVE_NEGATIVE_{suffix}",
        "hypothesis": "The v2 source USD reaches public tendon state and actuator consumers. Public state synchronization exposes L=0.02 m and Ldot=0.05 m/s before integration; the source scalar actuator law clips ctrl=300 to 255, gives 1.5 N, and maps through J=(0.5,0.5) to (0.75,0.75) N. A separate saturated state gives -100 N scalar and (-50,-50) N generalized. The exact source equality is tested with all actuator gains/biases zeroed, zero gravity and no ground/domain/self-contact: measured constraint qfrc must match an independently calculated solref/solimp row response. The diagnostic arm joints use the exact original physical-oracle home pose to avoid unrelated joint-limit/self-contact forces. An authored-but-inactive equality variant must produce no response, while removing the required equality record must be rejected by the public source importer.",
        "method": [
            "Import the exact v2 delivery by SceneSource.usd_path through the public importer, semantic IR, SolverSceneDesc, ArticulationConfig, RigidSceneModel and materialize_rigid CPU route.",
            "For both tendon actuator scenarios, write state through public qpos/qvel/ctrl writers, call public synchronize_kinematic_state, directly read tendon length/velocity before any solver.step, then execute one counted step.",
            "Import the separately hashed active/inactive equality-only derived USD variants. The transform zeros gain and bias for all eight actuators; the active variant retains exact source equality parameters, while the inactive variant keeps the relationship with active=false. A missing-relation negative is preflighted separately and must be rejected by the public source importer.",
            "For each dynamic equality variant, set the seven arm joints to the frozen original physical-oracle home pose, write q1=.021 m, q2=.020 m and zero velocity/control through public APIs, synchronize, execute exactly one counted step, and record qfrc_constraint, qM, qpos/qvel, contact readbacks and actuator force.",
            "Independently reproduce the frozen equality row law in Python from the source solref/solimp, source residual, pre-step velocity and public dense mass matrix; compare the active source row force and gap response to that oracle. The inactive variant must produce no response; the removed-relation variant must fail importer preflight."
        ],
        "source": source,
        "input_identity": identity,
        "runtime": previous["runtime"],
        "code": {"tracked_inputs": code},
        "oracle": {
            "source_revision": "b846dd12bc459d776cccb3dee0b1d02acbf7a9c7",
            "source_actuator_names": [str(row["name"]) for row in parent_worker["actuators"]],
            "source_actuator_values": parent_worker["actuators"],
            "source_tendon": "split",
            "source_equality": "finger_joint1_finger_joint2",
            "source_frictionless_diagnostic_variant": {
                "gain_prm": [0.0, 0.0, 0.0],
                "bias_prm": [0.0, 0.0, 0.0],
                "gravity": [0.0, 0.0, 0.0],
                "ground_contact": False,
                "domain_boundary_contact": False,
                "equality_variant_source_hashes": [positive["sha256"], negative["sha256"], removed["sha256"]],
            },
            "test_state_1": {"finger_joint1_q": 0.01, "finger_joint2_q": 0.03, "finger_joint1_dq": 0.02, "finger_joint2_dq": 0.08, "actuator8_requested_ctrl": 300.0, "ctrl_clips_to": 255.0, "expected_pre_step_tendon_length": 0.02, "expected_pre_step_tendon_velocity": 0.05, "expected_actuator_force": 1.50000000005, "expected_each_finger_generalized_force": 0.750000000025},
            "test_state_2": {"finger_joint1_q": 1.05, "finger_joint2_q": 1.05, "finger_joint1_dq": 0.0, "finger_joint2_dq": 0.0, "actuator8_requested_ctrl": 255.0, "raw_expected_actuator_force": -101.0, "expected_clipped_actuator_force": -100.0, "expected_each_finger_generalized_force": -50.0},
            "equality": {"finger_joint1_q": 0.021, "finger_joint2_q": 0.020, "finger_joint1_dq": 0.0, "finger_joint2_dq": 0.0, "arm_home_qpos": arm_home_qpos, "solref": [0.005, 1.0], "solimp": [0.95, 0.99, 0.001], "dt": 0.002, "positive_minimum_gap_reduction_m": 0.00001, "negative_maximum_gap_change_m": 0.000001, "negative_maximum_constraint_force_N": 0.0001},
            "epsilon": {"length_m": 0.00005, "velocity_m_s": 0.0001, "force_n": 0.05, "generalized_force_n": 0.08, "equality_force_n_abs_floor": 0.25, "equality_force_relative": 0.05},
            "model_counts": {"actuators": 8, "tendons": 1, "equalities": 1, "scalar_dof": 15},
            "variant_preflight": variant_preflight,
        },
        "limits": limits,
        "exit_policy": "Preserve the exact step counter and receipts on every failure; no implicit retry. A repaired retry must receive a unique plan/output identity and repeat all hash, resource and lock gates. This probe is diagnostic only.",
        "output": {
            "run_dir": str(run_dir.resolve()),
            "native_receipt": str((run_dir / "supervisor_receipt.json").resolve()),
            "worker_receipt": str((run_dir / "worker_receipt.json").resolve()),
            "worker_script": str(WORKER.resolve()),
        },
    }
    plan_path = run_dir.with_suffix(".plan.json")
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(plan, sort_keys=True, indent=2) + "\n").encode()
    plan_path.write_bytes(raw)
    plan_path.with_suffix(plan_path.suffix + ".sha256").write_text(hashlib.sha256(raw).hexdigest() + "  " + plan_path.name + "\n")
    return plan_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Freeze a uniquely named DG02 N1 public consumer probe plan.")
    parser.add_argument("--suffix", default="004")
    parser.add_argument("--expected-starts", type=int, default=12)
    parser.add_argument("--expected-steps", type=int, default=6)
    args = parser.parse_args()
    print(build(suffix=args.suffix, expected_starts=args.expected_starts, expected_steps=args.expected_steps))
