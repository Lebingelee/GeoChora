"""Freeze the source-bound 0.5 s equality coupling positive/negative probe."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from pxr import Usd


CORE = Path("/home/lly/Program_Files/Geochora").resolve()
WINDOW = CORE / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f05_diagnostic_goal02/window_001"
PROVIDER = CORE / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f05_geophys_provider/GeoPhys"
BASE_PLAN = WINDOW / "host_g2_001/n1_public_consumer_003.plan.json"
BASE_RECEIPT = WINDOW / "host_g2_001/n1_public_consumer_003/supervisor_receipt.json"
BASE_WORKER_RECEIPT = WINDOW / "host_g2_001/n1_public_consumer_003/worker_receipt.json"
LOCK = CORE / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/shared_native_execution.lock"
RUNS_DIR = WINDOW / "host_g4_001"
WORKER = CORE / "task_env/diagnostics/tasks/f05_dg02_equality_coupling_probe.py"
SUPERVISOR = CORE / "task_env/diagnostics/tasks/f05_dg02_n1_supervisor.py"
BUILDER = Path(__file__).resolve()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def mem_available() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable unavailable")


def tracked(path: Path) -> dict[str, str]:
    path = path.resolve(strict=True)
    return {"path": str(path), "sha256": sha(path)}


def make_inactive_variant(source_path: Path, variant_dir: Path) -> dict:
    source = source_path.read_bytes()
    token = b'"equalities":[{"active":true,"kind":"joint","name":"finger_joint1_finger_joint2"'
    replacement = b'"equalities":[{"active":false,"kind":"joint","name":"finger_joint1_finger_joint2"'
    if source.count(token) != 1:
        raise ValueError("source USD must contain one canonical active finger equality block")
    variant_dir.mkdir(parents=True, exist_ok=True)
    variant = variant_dir / "panda_equality_inactive_only.usda"
    expected = source.replace(token, replacement, 1)
    if variant.exists():
        if variant.read_bytes() != expected:
            raise ValueError(f"existing coupling variant differs; preserve it and select another suffix: {variant}")
    else:
        variant.write_bytes(expected)
    cold = variant.read_bytes()
    if cold != expected or cold.replace(replacement, token, 1) != source:
        raise ValueError("inactive equality variant changes bytes beyond its active flag")
    stage = Usd.Stage.Open(str(variant))
    if stage is None:
        raise ValueError("public OpenUSD cold-read failed for inactive equality variant")
    root = stage.GetDefaultPrim()
    attr = root.GetAttribute("geochora:f05SourceSemantics")
    semantics = json.loads(attr.Get())
    if len(semantics.get("equalities", [])) != 1 or semantics["equalities"][0].get("active") is not False:
        raise ValueError("cold-read inactive variant did not change only the equality active state")
    base_stage = Usd.Stage.Open(str(source_path))
    base_semantics = json.loads(base_stage.GetDefaultPrim().GetAttribute("geochora:f05SourceSemantics").Get())
    expected_semantics = json.loads(json.dumps(base_semantics))
    expected_semantics["equalities"][0]["active"] = False
    if semantics != expected_semantics:
        raise ValueError("inactive equality semantic object has unintended changes")
    return {
        "path": str(variant.resolve()),
        "sha256": sha(variant),
        "source_stage_sha256": sha(source_path),
        "replacement_delta_bytes": 1,
        "only_changed_semantic_field": "equalities[0].active: true -> false",
        "source_actuators_and_parameters_preserved": True,
        "source_tendon_preserved": True,
        "source_solref_solimp_preserved": True,
    }


def _resource_and_lock_check() -> int:
    available = mem_available()
    if available < 6 * 1024**3:
        raise RuntimeError(f"native start gate failed before planning: MemAvailable={available}")
    with LOCK.open("a+") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("shared native lock is already owned") from exc
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    return available


def build(suffix: str) -> Path:
    if not re.fullmatch(r"[0-9]{3}", suffix):
        raise ValueError("coupling run suffix must be exactly three digits")
    run_id = f"DG02_G4_SOURCE_USD_EQUALITY_COUPLING_{suffix}"
    run_dir = RUNS_DIR / f"coupling_{suffix}"
    variant_dir = RUNS_DIR / f"coupling_{suffix}_variants"
    plan_path = RUNS_DIR / f"coupling_{suffix}.plan.json"
    if run_dir.exists() or plan_path.exists() or variant_dir.exists():
        raise FileExistsError("coupling output identity already exists; choose a new suffix")
    base = json.loads(BASE_PLAN.read_text())
    parent = json.loads(BASE_RECEIPT.read_text())
    parent_worker = json.loads(BASE_WORKER_RECEIPT.read_text())
    if parent.get("exit_code") != 0 or parent.get("physics_steps") != 4 or not parent.get("lock_released_after_process_group_exit"):
        raise ValueError("successful source-consumer N1 run is required before coupling probe")
    if parent_worker.get("result") != "PASS_V2_PUBLIC_CONSUMERS" or parent_worker.get("physics_steps_completed") != 4:
        raise ValueError("N1 source consumer receipt is not a complete pass")
    core_branch, core_head = git(CORE, "branch", "--show-current"), git(CORE, "rev-parse", "HEAD")
    provider_branch, provider_head = git(PROVIDER, "branch", "--show-current"), git(PROVIDER, "rev-parse", "HEAD")
    if core_branch != "develop-full" or provider_branch != "codex/phase-ii-01-f05-geophys":
        raise ValueError("DG02 Core/provider branch identity changed")
    progress_path = WINDOW / "goal_progress.json"
    progress = json.loads(progress_path.read_text())
    if progress.get("protected_bad") != 0 or not progress.get("provider_clean"):
        raise RuntimeError("protected inputs or provider checkout are not clean before coupling plan freeze")
    if progress.get("core_current_head") != core_head or progress.get("provider_current_head") != provider_head:
        raise ValueError("goal progress HEAD differs from actual Core/provider checkout")
    available = _resource_and_lock_check()

    source = dict(base["source"])
    for old_key in (
        "diagnostic_variants_manifest",
        "equality_positive_variant_stage",
        "equality_negative_variant_stage",
        "equality_removed_variant_stage",
    ):
        source.pop(old_key, None)
    source["parent_n1_plan"] = tracked(BASE_PLAN)
    source["parent_n1_supervisor_receipt"] = tracked(BASE_RECEIPT)
    source["parent_n1_worker_receipt"] = tracked(BASE_WORKER_RECEIPT)
    stage_path = Path(source["usd_stage"]["path"]).resolve(strict=True)
    inactive = make_inactive_variant(stage_path, variant_dir)
    source["coupling_active_variant_stage"] = {
        "path": str(stage_path),
        "sha256": sha(stage_path),
        "active": True,
        "variant_transform": "none; exact source stage",
    }
    source["coupling_inactive_variant_stage"] = {**inactive, "active": False}
    source["coupling_variants_manifest"] = {
        "path": str((variant_dir / "variants_manifest.json").resolve()),
        "sha256": "",
    }
    manifest = {
        "schema_version": "f05-dg02-equality-coupling-variants-v1",
        "run_id": run_id,
        "source_stage": {"path": str(stage_path), "sha256": sha(stage_path)},
        "active_positive": source["coupling_active_variant_stage"],
        "inactive_counterfactual": source["coupling_inactive_variant_stage"],
        "scope": "source stage is immutable; counterfactual changes only equality active=true to false; source actuators remain authored and one output is disabled at runtime through the public provider API",
    }
    manifest_path = Path(source["coupling_variants_manifest"]["path"])
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    source["coupling_variants_manifest"]["sha256"] = sha(manifest_path)

    # Public, zero-step import/IR/articulation preflight for both identities.
    from scene import SceneSource, import_scene_source
    from scene.solver_scene import solver_scene_to_articulation_config

    preflight = {}
    for key, row, expected_active in (
        ("active", source["coupling_active_variant_stage"], True),
        ("inactive", source["coupling_inactive_variant_stage"], False),
    ):
        imported = import_scene_source(SceneSource.usd_path(Path(row["path"]), label=f"DG02_COUPLING_{key.upper()}_PREFLIGHT"), cache=False)
        if imported.format != "usd":
            raise ValueError(f"{key} source preflight did not use public USD importer")
        desc = imported.build_solver_scene_desc(mesh_collision_policy="strict")
        art = solver_scene_to_articulation_config(desc, usd_joint_anchor_tolerance=0.0)
        errors = art.validate()
        if errors:
            raise ValueError(f"{key} source coupling ArticulationConfig validation failed: {errors}")
        if len(art.actuators) != 8 or len(art.tendons) != 1 or len(art.equalities) != 1:
            raise ValueError(f"{key} source preflight lost required actuators/tendon/equality")
        equality = art.equalities[0]
        oracle = base["oracle"]["equality"]
        if bool(equality.active) is not expected_active or list(equality.solref) != oracle["solref"] or list(equality.solimp) != oracle["solimp"]:
            raise ValueError(f"{key} source preflight changed equality activity/compliance")
        if [str(a.name) for a in art.actuators] != base["oracle"]["source_actuator_names"]:
            raise ValueError(f"{key} source preflight changed actuator names/order")
        actuator8 = next(a for a in art.actuators if str(a.name) == "actuator8")
        expected8 = next(a for a in base["oracle"]["source_actuator_values"] if a["name"] == "actuator8")
        if list(actuator8.gain_prm) != expected8["gain_prm"] or list(actuator8.bias_prm) != expected8["bias_prm"] or list(actuator8.ctrl_range) != expected8["ctrl_range"] or list(actuator8.force_range) != expected8["force_range"]:
            raise ValueError(f"{key} source preflight changed actuator8 gain/bias/control/force limits")
        preflight[key] = {
            "format": imported.format,
            "semantic_hash": imported.ir_semantic_hash,
            "source_graph_hash": imported.source_graph_hash,
            "actuator_count": len(art.actuators),
            "tendon_count": len(art.tendons),
            "equality_count": len(art.equalities),
            "equality_active": bool(equality.active),
            "source_solref": list(equality.solref),
            "source_solimp": list(equality.solimp),
            "actuator8_gain_prm": list(actuator8.gain_prm),
            "actuator8_bias_prm": list(actuator8.bias_prm),
            "actuator8_ctrl_range": list(actuator8.ctrl_range),
            "actuator8_force_range": list(actuator8.force_range),
        }
        del imported, desc, art
    base["schema_version"] = "f05-dg02-equality-coupling-plan-v1"
    base["run_id"] = run_id
    base["classification"] = "source-bound GeoPhys/USD public model runtime equality coupling positive and inactive-relation counterfactual; diagnostic, not qualification"
    base["hypothesis"] = "On exact source USD with unchanged tendon/equality/actuator parameters, public runtime isolation of only actuator8 (with ctrl=255 and predicted enabled force >1 N) leaves arm holds active. Over 250 steps/0.5s, active source equality reduces the initial 0.016 m finger gap to <=0.002 m; changing only equality active=true to false makes the same relation gate fail. No poststep projection or equal finger targets are used."
    base["created_utc"] = datetime.now(timezone.utc).isoformat()
    base["input_identity"] = {
        "core_branch": core_branch,
        "core_input_head": core_head,
        "core_worktree": str(CORE),
        "provider_branch": provider_branch,
        "provider_input_head": provider_head,
        "provider_worktree": str(PROVIDER.resolve()),
    }
    base["source"] = source
    base["oracle"] = {
        **base["oracle"],
        "variant_preflight": preflight,
        "coupling_variants": {
            "reset_each_finger_q_m": [0.028, 0.012],
            "initial_finger_gap_m": 0.016,
            "source_actuator_ctrl8": 255.0,
            "only_disabled_actuator": "actuator8",
            "arm_control": "original physical oracle exact seven-joint home; all seven source arm actuators remain enabled",
            "steps_per_variant": 250,
            "dt_s": 0.002,
            "duration_s": 0.5,
            "relation_abs_error_max_m": 0.002,
            "inactive_gap_drift_max_m": 0.0001,
            "disabled_actuator_force_max_abs_N": 1.0e-6,
            "arm_home_error_max_rad": 0.01,
            "no_contact_impulse_abs_max_Ns": 1.0e-8,
            "source_compliance": {"solref": base["oracle"]["equality"]["solref"], "solimp": base["oracle"]["equality"]["solimp"]},
            "preflight": preflight,
        },
    }
    base["limits"].update({
        "native_starts_before": int(progress["native"]["geophys_starts"]),
        "physics_steps_before": int(progress["native"]["geophys_steps"]),
        "probe_physics_steps_before": int(progress["native"]["probe_steps"]),
        "cumulative_geophys_wall_s_before": float(progress["native"]["geophys_wall_s"]),
        "physics_steps_reserved": 500,
        "per_probe_steps_max": 500,
        "probe_physics_steps_max": 18000,
        "geophys_physics_steps_max": 66000,
        "global_physics_steps_max": 72000,
        "per_probe_worker_wall_s_max": 900,
        "worker_wall_s_max": 900,
        "start_native_mem_available_bytes_min": 6 * 1024**3,
        "preflight_mem_available_bytes": available,
        "native_process_group_sampled_rss_bytes_max": 4 * 1024**3,
        "abort_mem_available_bytes_below": 1 * 1024**3,
        "sample_interval_s": 0.25,
        "term_grace_s": 5,
        "cpu_threads_max": 4,
        "native_log_bytes_max": 128 * 1024**2,
        "shared_native_lock_path": str(LOCK),
        "shared_native_lock_available_at_freeze": True,
    })
    base["runtime"]["environment"] = {
        "CUDA_VISIBLE_DEVICES": "",
        "GEOPHYS_TAICHI_ARCH": "cpu",
        "GEOPHYS_TAICHI_BACKEND": "taichi-forge",
        "MKL_NUM_THREADS": "4",
        "NUMEXPR_NUM_THREADS": "4",
        "OMP_NUM_THREADS": "4",
        "OPENBLAS_NUM_THREADS": "4",
    }
    base["runtime_environment_sha256"] = hashlib.sha256(json.dumps(base["runtime"], sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    base["exit_policy"] = "Any failed gate remains in its own run record. The active and inactive cases each get exactly 250 steps; steps are counted before and after each solver.step. No cleanup or retry can erase prior native counters. A repaired rerun requires a new suffix, plan hash and complete resource/lock preflight."
    base["output"] = {
        "run_dir": str(run_dir.resolve()),
        "native_receipt": str((run_dir / "supervisor_receipt.json").resolve()),
        "worker_receipt": str((run_dir / "worker_receipt.json").resolve()),
        "worker_script": str(WORKER.resolve()),
    }

    # Preserve the known N1 import closure, refresh its exact current hashes,
    # and bind this planner/worker/supervisor plus the newly changed provider.
    code_paths = {Path(row["path"]).resolve() for row in base["code"]["tracked_inputs"]}
    provider_changes = git(PROVIDER, "diff", "--name-only", "524a08ca1744d9ea3140bc598147f4d82bb0a1b8", provider_head).splitlines()
    code_paths.update((PROVIDER / item).resolve() for item in provider_changes)
    code_paths.update(path.resolve() for path in (
        BUILDER,
        WORKER,
        SUPERVISOR,
        PROVIDER / "src/solvers/rigid/state/host_io.py",
        PROVIDER / "src/solvers/rigid/articulation/field_allocation.py",
        PROVIDER / "src/solvers/rigid/articulation/generalized_dynamics.py",
        PROVIDER / "src/solvers/rigid/row/constraint_rows_mixin.py",
    ))
    base["code"]["tracked_inputs"] = [tracked(path) for path in sorted(code_paths, key=str)]
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(base, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    plan_path.write_bytes(raw)
    sidecar = plan_path.with_suffix(plan_path.suffix + ".sha256")
    sidecar.write_text(hashlib.sha256(raw).hexdigest() + "  " + plan_path.name + "\n")
    return plan_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suffix", required=True)
    args = parser.parse_args()
    print(build(args.suffix))


if __name__ == "__main__":
    main()
