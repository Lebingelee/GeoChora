"""Freeze the bounded DG02 same-GeoPhys MJCF/USD public-source comparison."""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import argparse
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


CORE = Path("/home/lly/Program_Files/Geochora")
BASE = CORE / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f05_diagnostic_goal02/window_002"
PREVIOUS_PLAN = CORE / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f05_diagnostic_goal02/window_001/host_g2_001/n1_public_consumer_004.plan.json"
USD_REFERENCE = CORE / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f05_diagnostic_goal02/window_001/host_g2_001/n1_public_consumer_004/worker_receipt.json"
PROVIDER = CORE / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f05_geophys_provider/GeoPhys"
LOCK = CORE / "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/shared_native_execution.lock"
WORKER = CORE / "task_env/diagnostics/tasks/f05_dg02_mjcf_usd_source_probe.py"
SUPERVISOR = CORE / "task_env/diagnostics/tasks/f05_dg02_n1_supervisor.py"
BUILDER = Path(__file__).resolve()
ORIGINAL_MJCF = CORE / "asset/external/mujoco_menagerie/franka_emika_panda/panda.xml"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str, cwd: Path = CORE) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def tracked(path: Path) -> dict[str, str]:
    path = path.resolve(strict=True)
    return {"path": str(path), "sha256": sha(path)}


def _mem_available() -> int:
    return next(int(row.split()[1]) * 1024 for row in Path("/proc/meminfo").read_text().splitlines()
                if row.startswith("MemAvailable:"))


def _compose_task_scene_xml(source_path: Path, usd_stage_path: Path) -> str:
    """Compose the two literal F04Scene cube prims into a diagnostic MJCF copy."""
    stage = usd_stage_path.read_text(encoding="utf-8")
    expected_stage_facts = (
        'def Cube "support"', 'double size = 1',
        'float3 xformOp:scale = (0.35, 0.35, 0.05)',
        'double3 xformOp:translate = (1, 0.5, 0.45)',
        'def Cube "free_cube"', 'float physics:mass = 0.1',
        'double size = 0.06', 'double3 xformOp:translate = (1, 0.5, 0.9)',
    )
    missing = [fact for fact in expected_stage_facts if fact not in stage]
    if missing:
        raise ValueError(f"frozen USD task-scene values differ from the approved MJCF composition: {missing}")
    root = ET.fromstring(source_path.read_text(encoding="utf-8"))
    world = root.find("worldbody")
    if world is None:
        raise ValueError("Menagerie MJCF has no worldbody for the DG02 task-scene composition")
    names = {item.get("name") for item in root.iter() if item.get("name")}
    if {"support", "free_cube", "rootJoint"} & names:
        raise ValueError("protected source unexpectedly already contains one of the DG02 scene names")
    ET.SubElement(world, "geom", {
        "name": "support",
        "type": "box",
        "size": "0.175 0.175 0.025",
        "pos": "1 0.5 0.45",
    })
    free_cube = ET.SubElement(world, "body", {
        "name": "free_cube",
        "pos": "1 0.5 0.9",
    })
    ET.SubElement(free_cube, "freejoint", {"name": "rootJoint"})
    ET.SubElement(free_cube, "geom", {
        "name": "free_cube",
        "type": "box",
        "size": "0.03 0.03 0.03",
        "mass": "0.1",
    })
    return ET.tostring(root, encoding="unicode") + "\n"


def _home_equality_scenario(source_path: Path) -> dict:
    """Derive a low-contact equality-offset stimulus from Menagerie's home key."""
    root = ET.fromstring(source_path.read_text(encoding="utf-8"))
    home = root.find("./keyframe/key[@name='home']")
    if home is None:
        raise ValueError("protected Menagerie MJCF lacks the expected home keyframe")
    joint_names = [item.get("name") for item in root.findall("./worldbody//joint")]
    qpos = [float(value) for value in home.get("qpos", "").split()]
    if len(joint_names) != 9 or len(qpos) != len(joint_names):
        raise ValueError("home keyframe qpos no longer matches the nine named Panda scalar joints")
    state = {name: {"q": value, "dq": 0.0} for name, value in zip(joint_names, qpos)}
    if not {"finger_joint1", "finger_joint2", *[f"joint{i}" for i in range(1, 8)]}.issubset(state):
        raise ValueError("home keyframe is missing one or more source Panda joints")
    state["finger_joint1"]["q"] = 0.021
    state["finger_joint2"]["q"] = 0.020

    actuator_nodes = list(root.findall("./actuator/*"))
    actuator_names = [item.get("name", "") for item in actuator_nodes]
    controls = [float(value) for value in home.get("ctrl", "").split()]
    if len(actuator_names) != 8 or len(controls) != len(actuator_names):
        raise ValueError("home keyframe controls no longer match the eight source actuators")
    ctrl_by_name = dict(zip(actuator_names, controls))
    tendon = root.find("./tendon/fixed[@name='split']")
    if tendon is None:
        raise ValueError("protected source MJCF lacks the fixed split tendon")
    tendon_length = sum(
        float(joint.get("coef", "1")) * state[joint.get("joint")]["q"]
        for joint in tendon.findall("joint")
    )
    actuator8 = next((item for item in actuator_nodes if item.get("name") == "actuator8"), None)
    if actuator8 is None:
        raise ValueError("protected source MJCF lacks source actuator8")
    gain = [float(value) for value in actuator8.get("gainprm", "").split()]
    bias = [float(value) for value in actuator8.get("biasprm", "").split()]
    if not gain or len(bias) < 3 or gain[0] == 0.0:
        raise ValueError("source actuator8 gain/bias law is not the expected affine law")
    # Choose ctrl8 so the authored affine source law is zero at d(length)/dt=0.
    ctrl_by_name["actuator8"] = -bias[1] * tendon_length / gain[0]
    expected_force = gain[0] * ctrl_by_name["actuator8"] + bias[1] * tendon_length
    if not math.isclose(expected_force, 0.0, abs_tol=1e-12):
        raise ValueError("derived source actuator8 control does not neutralize its frozen law")
    return {
        "scenario": "home_arm_equality_offset",
        "pre_state_by_joint": state,
        "ctrl_by_actuator": ctrl_by_name,
        "source_derivation": {
            "source_keyframe": "home",
            "source_mjcf_sha256": sha(source_path),
            "finger_qpos_override_rad": {"finger_joint1": 0.021, "finger_joint2": 0.020},
            "tendon_length_m": tendon_length,
            "actuator8_force_target_N": 0.0,
            "actuator8_force_from_source_gain_bias_N": expected_force,
            "actuator8_ctrl_derived_from_original_gain_bias": True,
        },
    }


def build(suffix: str = "001") -> Path:
    if not suffix.isdigit() or len(suffix) != 3:
        raise ValueError("source-comparison suffix must be a three-digit number")
    run_id = f"DG02_P3_GEOPHYS_MJCF_USD_PUBLIC_SOURCE_PAIR_{suffix}"
    run_dir = BASE / f"geophys_mjcf_usd_source_compare_{suffix}"
    plan_path = BASE / f"geophys_mjcf_usd_source_compare_{suffix}.plan.json"
    task_mjcf = BASE / f"geophys_mjcf_usd_source_compare_{suffix}_mjcf_scene.xml"
    additional_scenarios = [_home_equality_scenario(ORIGINAL_MJCF)] if suffix in ("003", "004", "005", "006", "007", "008") else []
    if suffix in ("004", "005"):
        additional_scenarios[0]["scenario"] = "home_arm_equality_offset_contacts_disabled_counterfactual"
    if suffix == "006":
        additional_scenarios[0]["scenario"] = "home_arm_equality_offset_contacts_and_joint_passive_alignment_counterfactual"
    if suffix in ("007", "008"):
        additional_scenarios[0]["scenario"] = "home_arm_equality_offset_after_usd_joint_passive_import_fix"
    include_reference_scenarios = suffix not in ("004", "005", "006", "007", "008")
    source_body_contacts_enabled = suffix not in ("004", "005", "006", "007", "008")
    step_reservation = (
        2 if suffix == "004"
        else 4 + (2 * len(additional_scenarios)) if include_reference_scenarios
        else 2 * len(additional_scenarios)
    )
    if run_dir.exists() or plan_path.exists() or task_mjcf.exists():
        raise FileExistsError("DG02 source-comparison output already exists; allocate a new frozen suffix")
    previous = json.loads(PREVIOUS_PLAN.read_text(encoding="utf-8"))
    usd_receipt = json.loads(USD_REFERENCE.read_text(encoding="utf-8"))
    if previous.get("schema_version") != "f05-dg02-n1-public-consumer-plan-v1":
        raise ValueError("expected the source-bound DG02 N1 USD plan")
    if usd_receipt.get("result") != "PASS_V2_PUBLIC_CONSUMERS" or usd_receipt.get("physics_steps_completed") != 4:
        raise ValueError("frozen USD source-consumer reference must be a complete four-step pass")
    if git("branch", "--show-current") != "develop-full":
        raise RuntimeError("Core writer branch is not develop-full")
    provider_branch = git("-C", str(PROVIDER), "branch", "--show-current")
    if provider_branch != "codex/phase-ii-01-f05-geophys":
        raise RuntimeError("GeoPhys is not on the isolated F05 provider branch")
    lock_stream = LOCK.open("a+")
    try:
        try:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("shared native execution lock is occupied") from exc
        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)
    finally:
        lock_stream.close()
    available = _mem_available()
    if available < 6 * 1024**3:
        raise RuntimeError(f"native start memory gate failed: MemAvailable={available}")

    original = Path(previous["source"]["mjcf_source"]["path"]).resolve(strict=True)
    if sha(original) != previous["source"]["mjcf_source"]["sha256"]:
        raise ValueError("original Menagerie MJCF differs from the frozen source reference")
    stage = Path(previous["source"]["usd_stage"]["path"]).resolve(strict=True)
    task_xml = _compose_task_scene_xml(original, stage)
    task_mjcf.write_text(task_xml, encoding="utf-8")

    source = dict(previous["source"])
    source["mjcf_source"] = tracked(original)
    source["mjcf_task_scene_variant"] = tracked(task_mjcf)
    source["usd_reference_probe_receipt"] = tracked(USD_REFERENCE)
    source["mjcf_task_scene_composition"] = {
        "source_mjcf_sha256": sha(original),
        "usd_stage_sha256": sha(stage),
        "method": "append two static/free MJCF primitives derived from the literal /F04Scene USD prim facts; no edits to protected source input",
        "support": {"shape": "box", "full_size_m": [0.35, 0.35, 0.05], "center_m": [1.0, 0.5, 0.45], "material_binding": None},
        "free_cube": {"shape": "box", "edge_m": 0.06, "mass_kg": 0.1, "center_m": [1.0, 0.5, 0.9], "material_binding": None},
    }

    identity = dict(previous["input_identity"])
    identity["core_input_head"] = git("rev-parse", "HEAD")
    identity["core_branch"] = git("branch", "--show-current")
    identity["provider_input_head"] = git("-C", str(PROVIDER), "rev-parse", "HEAD")
    identity["provider_branch"] = provider_branch

    paths = {row["path"] for row in previous["code"]["tracked_inputs"]}
    paths.update(str(path.resolve(strict=True)) for path in (BUILDER, WORKER, SUPERVISOR))
    paths.update(str(path.resolve(strict=True)) for path in (
        PROVIDER / "src/scene/_rigid_usd_joint.py",
        PROVIDER / "src/scene/usd_scene_ir.py",
        PROVIDER / "test/verification/scene/test_usd_joint_lowering.py",
    ))
    code = [tracked(Path(path)) for path in sorted(paths)]

    ledger = json.loads((BASE / "run_ledger.json").read_text(encoding="utf-8"))
    totals = ledger["new_window_totals"]
    carry = ledger["carry_in"]
    probe_steps_before = int(carry["nonformal_probe_attempted_steps_upper_bound"]) + int(totals["geophys_nonformal_attempted_steps"])
    if probe_steps_before + step_reservation > int(ledger["cumulative_caps_unchanged"]["probe_steps"]):
        raise RuntimeError("DG02 cumulative probe budget would be exceeded")
    if int(totals["geophys_nonformal_attempted_steps"]) + step_reservation > int(ledger["window_budget"]["geophys_nonformal_steps_max"]):
        raise RuntimeError("DG02 per-window nonformal GeoPhys budget would be exceeded")

    limits = dict(previous["limits"])
    limits.update({
        "native_starts_before": 48 + int(suffix),
        "physics_steps_before": probe_steps_before,
        "probe_physics_steps_before": probe_steps_before,
        "physics_steps_reserved": step_reservation,
        "per_probe_steps_max": 500,
        "worker_wall_s_max": 900,
        "start_native_mem_available_bytes_min": 6442450944,
        "abort_mem_available_bytes_below": 1073741824,
        "native_process_group_sampled_rss_bytes_max": 4294967296,
        "native_log_bytes_max": 134217728,
        "cpu_threads_max": 4,
        "shared_native_lock_path": str(LOCK),
        "preflight_mem_available_bytes": available,
        "shared_native_lock_available_at_freeze": True,
        "probe_physics_steps_max": 18000,
        "geophys_physics_steps_max": 66000,
        "global_physics_steps_max": 72000,
        "cumulative_geophys_wall_s_before": float(carry["geophys_wall_s_conservative"] + totals["native_wall_s"]),
    })
    runtime = previous["runtime"]
    code_paths = {row["path"] for row in code}
    plan = {
        "schema_version": "f05-dg02-n1-public-consumer-plan-v1",
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "classification": "same-provider source-bound GeoPhys MJCF/USD fixed-state/fixed-control diagnostic; not online R3, Core formal, or qualification",
        "hypothesis": "GeoPhys' public importer/lowering and CPU rigid solver preserve the original Menagerie Panda source actuator, split-tendon and finger-equality semantics in both the exact source-bound USD and a hash-bound MJCF composition that includes the same DG02 support/free-cube primitives. Identical named joint q/dq and actuator ctrl vectors will be replayed in both formats under the same dt, integrator, gravity and explicit body-contact mode.",
        "method": [
            "Load the exact source-bound USD through SceneSource.usd_path and the exact original Menagerie panda.xml through SceneSource.mjcf_string after appending only the two F04Scene primitive facts from the frozen USD stage.",
            "Build both public ImportedScene -> SolverSceneDesc -> ArticulationConfig -> RigidSceneModel paths; compare counts, actuator descriptors, tendon/equality descriptors and source joint mappings before solver initialization.",
            "Use exact named Panda q/dq and actuator ctrl stimuli from the passing frozen DG02 USD source-consumer receipt; materialize both public host models with identical 2 ms implicitfast CPU config and take exactly two public steps per representation.",
            "Read public actuator force, generalized actuator/constraint force, tendon length/rate, named joint state and contact counts; compare paired values without inferring equivalence from schema retention alone.",
        ],
        "source": source,
        "additional_scenarios": additional_scenarios,
        "include_usd_reference_scenarios": include_reference_scenarios,
        "source_body_contacts_enabled": source_body_contacts_enabled,
        "align_mjcf_joint_passives_to_usd_counterfactual": suffix == "006",
        "diagnostic_variant": (
            "source_contact_disabled_joint_passives_aligned_counterfactual"
            if suffix == "006" else (
                "source_contact_disabled_after_usd_joint_passive_import_fix"
                if suffix in ("007", "008") else (
                "source_contact_disabled_equality_isolation_counterfactual"
                if not source_body_contacts_enabled else "source_contact_enabled_public_source_pair"
                )
            )
        ),
        "input_identity": identity,
        "runtime": runtime,
        "runtime_environment_sha256": hashlib.sha256(json.dumps(runtime, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
        "code": {"tracked_inputs": code},
        "oracle": {
            "required_actuator_names": [f"actuator{i}" for i in range(1, 9)],
            "required_tendon": {"name": "split", "transmission": "fixed", "joint_names": ["finger_joint1", "finger_joint2"], "coefficients": [0.5, 0.5]},
            "required_equality": {"name": "finger_joint1_finger_joint2", "target1": "finger_joint1", "target2": "finger_joint2", "solref": [0.005, 1.0], "solimp": [0.95, 0.99, 0.001]},
            "stimulus_receipt": str(USD_REFERENCE),
            "stimulus_receipt_sha256": sha(USD_REFERENCE),
            "expected_step_count": step_reservation,
            "comparison": "source-law and matched-input diagnostic; exact microprobe deltas are reported, no post-hoc tolerance grants equivalence",
        },
        "limits": limits,
        "exit_policy": "Keep every failed invocation and attempted step charged; retry only with a new source/code-bound plan. Do not use a passing source consumer probe as DG02 qualification.",
        "output": {
            "run_dir": str(run_dir.resolve()),
            "native_receipt": str((run_dir / "supervisor_receipt.json").resolve()),
            "worker_receipt": str((run_dir / "worker_receipt.json").resolve()),
            "worker_script": str(WORKER.resolve()),
            "step_counter": str((run_dir / "step_counter.json").resolve()),
        },
    }
    plan_raw = (json.dumps(plan, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    plan_path.write_bytes(plan_raw)
    plan_path.with_suffix(plan_path.suffix + ".sha256").write_text(
        hashlib.sha256(plan_raw).hexdigest() + "  " + plan_path.name + "\n",
        encoding="ascii",
    )
    return plan_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--suffix", default="001")
    print(build(parser.parse_args().suffix))
