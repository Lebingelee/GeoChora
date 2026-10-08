"""Gated Phase A then Phase B campaign for P1.8-E-R3; never tunes behavior."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import yaml

from ....runtime.sessions.provenance import provider_build_identity
from ....objects.nut_assembly import NUT_ASSET_ROOT
from ....tasks.nut_assembly.canonical_reset import sample_reset
from .common import PROFILE_PATH, PROVIDERS, RATE_NAMES, context, read_profile, sha256_file


ROOT = Path("workspace/qualification/phase1/p1_8_nutassembly_nominal")
MODULE = "task_env.diagnostics.phase1.nutassembly_nominal.worker"
RESET_BOUND = 1.0e-5
SOURCE_PATHS = (
    "task_env/artifacts/contracts.py",
    "task_env/artifacts/execution.py",
    "task_env/tasks/nut_assembly/assets.py",
    "task_env/tasks/nut_assembly/canonical_artifact.py",
    "task_env/tasks/nut_assembly/canonical_initialization.json",
    "task_env/tasks/nut_assembly/canonical_source.py",
    "task_env/tasks/nut_assembly/canonical_reset.py",
    "task_env/tasks/nut_assembly/canonical_semantics.py",
    "task_env/tasks/nut_assembly/canonical_solution.py",
    "task_env/tasks/nut_assembly/default.yaml",
    "task_env/tasks/nut_assembly/profiles/nutassembly-nominal-v1.json",
    "task_env/tasks/nut_assembly/solution.py",
    "task_env/tasks/nut_assembly/task.py",
    "task_env/objects/nut_assembly.py",
    "task_env/objects/default_asset/square-nut.xml",
    "task_env/robots/panda.py",
    "task_env/robots/gripper.py",
    "task_env/controllers/canonical/production.py",
    "task_env/controllers/canonical/controller.py",
    "task_env/controllers/canonical/readiness.py",
    "task_env/controllers/canonical/feedback.py",
    "task_env/controllers/canonical/contracts.py",
    "task_env/controllers/canonical/kinematics.py",
    "task_env/controllers/canonical/__init__.py",
    "task_env/environment/config.py",
    "task_env/environment/configuration.py",
    "task_env/planners/__init__.py",
    "task_env/planners/cartesian.py",
    "task_env/planners/contracts.py",
    "task_env/planners/joint.py",
    "task_env/utils/rotation/__init__.py",
    "task_env/utils/rotation/core.py",
    "task_env/utils/_paths.py",
    "task_env/runtime/sessions/control.py",
    "task_env/runtime/sessions/geophys.py",
    "task_env/runtime/sessions/geophys_source.py",
    "task_env/runtime/sessions/mujoco.py",
    "task_env/runtime/sessions/sapien.py",
    "task_env/runtime/sessions/genesis.py",
    "task_env/runtime/sessions/api.py",
    "task_env/runtime/sessions/common.py",
    "task_env/runtime/sessions/representation.py",
    "task_env/runtime/sessions/source.py",
    "task_env/runtime/sessions/provenance.py",
    "task_env/diagnostics/phase1/nutassembly/common.py",
    "task_env/diagnostics/phase1/nutassembly/native.py",
    "task_env/diagnostics/phase1/multirate/common.py",
    "task_env/diagnostics/phase1/p1_2_runtime.py",
    "task_env/diagnostics/phase1/nutassembly_nominal/__init__.py",
    "task_env/diagnostics/phase1/nutassembly_nominal/common.py",
    "task_env/diagnostics/phase1/nutassembly_nominal/worker.py",
    "task_env/diagnostics/phase1/nutassembly_nominal/campaign.py",
)


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def provider_presence(name):
    module = importlib.util.find_spec(name)
    distribution = "genesis-world" if name == "genesis" else name
    try:
        version = importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        version = None
    return {"provider": name, "distribution": distribution, "import_available": module is not None,
            "import_origin": module.origin if module is not None else None, "package_version": version}


def spec_mapping():
    profile = read_profile()
    rate_specs = {}
    reset_physical_fingerprints = []
    for rate in RATE_NAMES:
        value = context(rate)
        artifact = value["artifact"]
        sample = sample_reset(artifact, int(profile["reset"]["seed"]))
        physical = sample.to_mapping()
        physical.pop("sample_id", None)
        physical.pop("task_artifact_hash", None)
        reset_physical_fingerprints.append(sha(json.dumps(physical, sort_keys=True, separators=(",", ":")).encode()))
        rate_specs[rate] = {
            "task_artifact_hash": artifact.identity_hash,
            "reset_sample_hash": sample.identity_hash,
            "reset_sample_mapping": sample.to_mapping(),
            "reset_physical_fingerprint_without_rate_identity": reset_physical_fingerprints[-1],
            "timebase": artifact.timebase.to_mapping(),
            "source_xml_sha256": hashlib.sha256(value["source"].scene_source.xml.encode()).hexdigest(),
            "normalized_source_xml_sha256": value["recipe"]["normalized_source_xml_sha256"],
            "source_recipe_hash": value["recipe_identity"],
            "controller_identity": value["controller_identity"],
            "controller_action_config": value["recipe"]["source_config_action"],
            "controller_gripper_config": value["recipe"]["source_config_gripper"],
            "solution_identity": value["solution_identity"],
            "solution_config": asdict(value["solution_config"]),
            "readiness_identity": value["readiness_identity"],
            "fallback_window_ticks": max(1, int(math.ceil(profile["solution"]["fallback_window_s"]
                / artifact.timebase.control_dt - 1e-10))),
        }
    if len(set(reset_physical_fingerprints)) != 1:
        raise ValueError("NA-S0 physical reset differs across timebase Artifact variants")
    return {
        "schema_version": "p1_8_e_r3_nominal_spec_v1",
        "qualification_base_commit": git("rev-parse", "HEAD"),
        "qualification_branch": git("branch", "--show-current"),
        "human_authority": {
            "prior_followup_spec_lock_sha256": "eb533e675c0f05e0a85f9e52e2d011c5237ad306cec65ef4af87aacb027b4585",
            "prior_followup_source_binding": "workspace/qualification/phase1/p1_8_nutassembly_nominal/provenance/source_worktree_audit.json",
            "phase_a_before_phase_b": True,
            "no_behavior_tuning_after_lock": True,
        },
        "frozen_nominal_profile": profile,
        "rate_artifact_family": rate_specs,
        "source_hashes": {path: sha256_file(path) for path in SOURCE_PATHS},
        "pinned_assets": {
            "geophys_gitlink": git("rev-parse", "HEAD:GeoPhys"),
            "panda_asset_gitlink": git("rev-parse", "HEAD:asset/external/mujoco_menagerie"),
            "panda_xml_sha256": sha256_file("asset/external/mujoco_menagerie/franka_emika_panda/panda.xml"),
            "nut_xml_sha256": sha256_file(NUT_ASSET_ROOT / "square-nut.xml"),
        },
        "providers": {
            "geophys": provider_build_identity("geophys"),
            "mujoco": provider_build_identity("mujoco"),
            "sapien": provider_presence("sapien"),
            "genesis": provider_presence("genesis"),
        },
        "acceptance": {
            "reset_representation_max_abs": RESET_BOUND,
            "close_authorization": ["controller_close_ready", "stable_grasp_fallback"],
            "controller_force_limit_N": 30.0,
            "controller_force_deadband_N": 1.0,
            "fallback_min_closing_force_N": 25.0,
            "fallback_physical_window_s": 0.1,
            "fallback_max_opening_span_m": 0.0005,
            "fallback_requires_grasped_nut_every_boundary": True,
            "verify_lift_mandatory": True,
            "canonical_task_success": ["inserted_on_peg", "gripper_released", "released_nut", "task_success"],
            "expert_required_rate_providers": [[rate, provider] for rate in RATE_NAMES for provider in ("geophys", "mujoco")],
            "phase_a_d1_d2_source_replay_providers": ["geophys", "mujoco"],
            "phase_b_only_if_phase_a_all_pass": True,
            "phase_b_d1_d2_source_replay_providers": ["sapien", "genesis"],
            "phase_b_primary_to_boundary_source": "geophys",
        },
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }


def create_lock(root):
    root.mkdir(parents=True, exist_ok=True)
    spec_path = root / "nominal_spec.yaml"
    lock_path = root / "nominal_spec_lock.json"
    if spec_path.exists() or lock_path.exists():
        raise FileExistsError("nominal spec already exists; refusing to overwrite Evidence")
    spec_path.write_text(yaml.safe_dump(spec_mapping(), sort_keys=False, allow_unicode=True))
    lock = {"schema_version": "p1_8_e_r3_nominal_spec_lock_v1", "path": str(spec_path),
            "sha256": sha(spec_path.read_bytes()), "locked_before_first_provider_run": True}
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    return lock


def verify_lock(root):
    spec_path, lock_path = root / "nominal_spec.yaml", root / "nominal_spec_lock.json"
    lock = json.loads(lock_path.read_text())
    if sha(spec_path.read_bytes()) != lock["sha256"]:
        raise ValueError("nominal spec lock mismatch")
    spec = yaml.safe_load(spec_path.read_text())
    for path, expected in spec["source_hashes"].items():
        if sha256_file(path) != expected:
            raise ValueError("source changed after nominal lock: " + path)
    return spec, lock


def _folder_for(root, phase, route, rate, provider, source_provider=None):
    label = rate.lower().replace("na-", "")
    base = root / phase
    if route == "precheck":
        return base / "precheck" / label / provider
    if route == "expert":
        return base / "expert" / label / provider
    if route == "D0":
        return base / "d0" / label / (source_provider or provider)
    return base / route.lower() / label / (source_provider or provider) / provider


def run_cell(root, phase, route, rate, provider, *, source_provider=None, source_phase=None, route_name=None):
    verify_lock(root)
    folder = _folder_for(root, phase, route_name or route, rate, provider, source_provider)
    if (folder / "report.json").exists():
        raise FileExistsError(f"refusing to overwrite {folder}")
    folder.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", MODULE, "--root", str(root), "--route", route,
               "--rate", rate, "--provider", provider, "--phase", phase]
    if source_provider:
        command += ["--source-provider", source_provider]
    if source_phase:
        command += ["--source-phase", source_phase]
    if route_name:
        command += ["--route-name", route_name]
    command_text = "PYTHONPATH=GeoPhys/src:. PYTHONDONTWRITEBYTECODE=1 GEOPHYS_HEADLESS=1 " + shlex.join(command)
    (folder / "command.txt").write_text(command_text + "\n")
    env = os.environ.copy()
    env["PYTHONPATH"] = "GeoPhys/src:."
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["GEOPHYS_HEADLESS"] = "1"
    with (folder / "stdout.log").open("w") as stdout, (folder / "stderr.log").open("w") as stderr:
        completed = subprocess.run(command, cwd=Path.cwd(), env=env, stdout=stdout, stderr=stderr, check=False)
    report_path = folder / "report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text())
    else:
        report = {"pass": False, "success": False, "execution_valid": False, "task_valid": False,
                  "failure_boundary": "diagnostic_worker_exit", "returncode": completed.returncode}
        report_path.write_text(json.dumps(report, indent=2) + "\n")
    report["worker_returncode"] = completed.returncode
    report["command"] = command_text
    report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    verify_lock(root)
    return report


def _copy_golden(root, phase, rate, provider):
    label = rate.lower().replace("na-", "")
    source = root / phase / "expert" / label / provider
    report = json.loads((source / "report.json").read_text())
    if not report.get("success"):
        raise ValueError("cannot freeze unsuccessful expert trajectory")
    destination = root / phase / "golden" / label / provider
    destination.mkdir(parents=True, exist_ok=True)
    for filename in ("trajectory.h5",):
        source_path = Path(report["trajectory_path"])
        dest_path = destination / filename
        if dest_path.exists():
            raise FileExistsError("golden Evidence collision")
        shutil.copy2(source_path, dest_path)
        if sha256_file(dest_path) != report["h5_sha256"]:
            raise ValueError("golden H5 changed during freeze")
    (destination / "reference.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return report


def _phase_matrix(root, phase, providers, source_providers):
    result = {"precheck": {}, "expert": {}, "D0": {}, "D1": {}, "D2": {}}
    for rate in RATE_NAMES:
        for provider in providers:
            report = run_cell(root, phase, "precheck", rate, provider)
            result["precheck"][f"{rate}/{provider}"] = report
    failed_precheck = [key for key, value in result["precheck"].items() if not value.get("pass")]
    if failed_precheck:
        return result, "precheck", failed_precheck
    for rate in RATE_NAMES:
        for provider in providers:
            report = run_cell(root, phase, "expert", rate, provider)
            result["expert"][f"{rate}/{provider}"] = report
            if not report.get("success"):
                return result, f"expert/{rate}/{provider}", [report.get("failure_boundary") or report.get("failure_reason") or "expert_failed"]
    for rate in RATE_NAMES:
        for provider in providers:
            _copy_golden(root, phase, rate, provider)
            report = run_cell(root, phase, "D0", rate, provider, source_provider=provider)
            result["D0"][f"{rate}/{provider}"] = report
    if any(not report.get("pass") for report in result["D0"].values()):
        return result, "D0", [key for key, report in result["D0"].items() if not report.get("pass")]
    for route in ("D1", "D2"):
        for rate in RATE_NAMES:
            for source_provider in source_providers:
                for provider in providers:
                    report = run_cell(root, phase, route, rate, provider,
                                      source_provider=source_provider, route_name=route)
                    result[route][f"{rate}/{source_provider}->{provider}"] = report
    failures = []
    for route in ("D1", "D2"):
        for key, report in result[route].items():
            if not report.get("execution_valid") or not report.get("task_valid"):
                failures.append(f"{route}/{key}")
    return result, "complete" if not failures else "replay", failures


def _write_primary_lock(root, spec, lock):
    production = {path: sha256_file(path) for path in SOURCE_PATHS
                  if not path.startswith("task_env/diagnostics/phase1/nutassembly_nominal/")}
    goldens = {}
    actions = {}
    for rate in RATE_NAMES:
        label = rate.lower().replace("na-", "")
        for provider in ("geophys", "mujoco"):
            ref_path = root / "phase_a" / "golden" / label / provider / "reference.json"
            ref = json.loads(ref_path.read_text())
            goldens[f"{rate}/{provider}"] = {"logical_hash": ref["logical_hash"], "h5_sha256": ref["h5_sha256"],
                                              "task_artifact_hash": ref["task_artifact_hash"],
                                              "reset_sample_hash": ref["reset_sample_hash"], "T": ref["T"]}
            d0 = json.loads((root / "phase_a" / "d0" / label / provider / "report.json").read_text())
            actions[f"{rate}/{provider}"] = d0["action_sequence_identity"]
    payload = {"schema_version": "p1_8_e_r3_primary_acceptance_lock_v1",
               "qualification_base_commit": spec["qualification_base_commit"],
               "nominal_spec_sha256": lock["sha256"], "production_source_hashes": production,
               "goldens": goldens, "d0_action_sequence_hashes": actions,
               "frozen_thresholds": spec["acceptance"], "phase_a_completed_before_phase_b": True}
    path = root / "phase_a" / "primary_acceptance_lock.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return {"path": str(path), "sha256": sha256_file(path), **payload}


def _phase_a_report(matrix, outcome, failures):
    return {"decision": outcome == "complete", "matrix": matrix, "first_failure_boundary": outcome,
            "failures": failures, "phase_b_permitted": outcome == "complete"}


def _write_acceptance(root, status, phase_a, phase_b, first_failure):
    payload = {
        "phase": "p1_8_nutassembly_nominal",
        "decision": "ready_for_human_review" if status == "ready_for_human_review" else "partial_with_localized_failure",
        "nominal_profile": "nutassembly-nominal-v1",
        "phase_a": {"decision": "pass" if phase_a.get("decision") else "fail", "evidence": "phase_a"},
        "phase_b": {"decision": "pass" if phase_b and phase_b.get("decision") else "not_run" if phase_b is None else "fail",
                    "evidence": "phase_b" if phase_b else None},
        "first_failing_boundary": first_failure,
        "heavy_load_1kg_is_separate_stress_profile": True,
        "p1_6_p1_7_waived": False,
        "phase_i_closed": False,
    }
    (root / "acceptance.json").write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")


def _write_handoff(root, status, phase_a, phase_b, first_failure):
    a_experts = phase_a["matrix"].get("expert", {})
    b_experts = phase_b["matrix"].get("expert", {}) if phase_b else {}
    lines = [
        "# P1.8-E-R3 Nominal NutAssembly Handoff",
        "",
        f"Operational status: `{status}`",
        f"Qualification base commit: `{phase_a.get('qualification_base_commit', 'see nominal_spec.yaml')}`",
        f"Nominal profile: `nutassembly-nominal-v1` (0.1 kg, 30 N / 1 N controller, 25 N solution fallback)",
        f"Phase A: `{'PASS' if phase_a.get('decision') else 'FAIL'}`",
        f"Phase B: `{'PASS' if phase_b and phase_b.get('decision') else 'NOT RUN' if phase_b is None else 'FAIL'}`",
        f"First failing boundary: `{first_failure or 'none'}`",
        "",
        "## Phase A prechecks",
        "",
        "| Rate | GeoPhys | MuJoCo |",
        "|---|---|---|",
    ]
    for rate in RATE_NAMES:
        vals = [phase_a["matrix"].get("precheck", {}).get(f"{rate}/{provider}", {}).get("pass", "NOT RUN")
                for provider in ("geophys", "mujoco")]
        lines.append(f"| {rate} | {vals[0]} | {vals[1]} |")
    lines += ["", "## Phase A expert runs", "", "| Rate | GeoPhys | MuJoCo |", "|---|---|---|"]
    for rate in RATE_NAMES:
        vals = [a_experts.get(f"{rate}/{provider}", {}).get("success", "NOT RUN") for provider in ("geophys", "mujoco")]
        lines.append(f"| {rate} | {vals[0]} | {vals[1]} |")
    lines += ["", "## Gate disposition", "",
              "Phase B was entered only after the Phase-A expert, D0, D1, D2, and timebase gates passed.",
              "The 1.0 kg results remain an unchanged heavy-load stress reference and do not gate this nominal profile.",
              "P1.6 and P1.7 were not waived; Phase I is not closed.", ""]
    (root / "handoff.md").write_text("\n".join(lines))


def run(root=ROOT):
    root = Path(root)
    lock = create_lock(root)
    spec, lock = verify_lock(root)
    matrix_a, outcome_a, failures_a = _phase_matrix(root, "phase_a", ("geophys", "mujoco"), ("geophys", "mujoco"))
    phase_a = _phase_a_report(matrix_a, outcome_a, failures_a)
    phase_a["qualification_base_commit"] = spec["qualification_base_commit"]
    (root / "phase_a" / "report.json").write_text(json.dumps(phase_a, indent=2, sort_keys=True, allow_nan=False) + "\n")
    phase_b = None
    first_failure = None if phase_a["decision"] else (failures_a[0] if failures_a else outcome_a)
    if phase_a["decision"]:
        phase_a["primary_acceptance_lock"] = _write_primary_lock(root, spec, lock)
        (root / "phase_a" / "report.json").write_text(json.dumps(phase_a, indent=2, sort_keys=True, allow_nan=False) + "\n")
        matrix_b, outcome_b, failures_b = _phase_matrix(root, "phase_b", ("sapien", "genesis"), ("sapien", "genesis"))
        phase_b = _phase_a_report(matrix_b, outcome_b, failures_b)
        if phase_b["decision"]:
            bridge = {"D1": {}, "D2": {}}
            for route in ("D1", "D2"):
                for rate in RATE_NAMES:
                    for provider in ("sapien", "genesis"):
                        bridge[route][f"{rate}/geophys->{provider}"] = run_cell(
                            root, "phase_b/primary_to_boundary", route, rate, provider,
                            source_provider="geophys", source_phase="phase_a", route_name=route)
            phase_b["primary_to_boundary"] = bridge
            bridge_fail = [f"{route}/{key}" for route in ("D1", "D2") for key, report in bridge[route].items()
                           if not report.get("execution_valid") or not report.get("task_valid")]
            phase_b["decision"] = not bridge_fail
            phase_b["primary_to_boundary_failures"] = bridge_fail
            if bridge_fail:
                first_failure = bridge_fail[0]
        else:
            first_failure = failures_b[0] if failures_b else outcome_b
        (root / "phase_b" / "report.json").parent.mkdir(parents=True, exist_ok=True)
        (root / "phase_b" / "report.json").write_text(json.dumps(phase_b, indent=2, sort_keys=True, allow_nan=False) + "\n")
    status = "ready_for_human_review" if phase_a["decision"] and phase_b and phase_b["decision"] else "partial_with_localized_failure"
    _write_acceptance(root, status, phase_a, phase_b, first_failure)
    _write_handoff(root, status, phase_a, phase_b, first_failure)
    result = {"status": status, "phase_a": phase_a, "phase_b": phase_b, "first_failing_boundary": first_failure}
    (root / "campaign_report.json").write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = run(args.root)
    print(json.dumps({"status": result["status"], "first_failing_boundary": result["first_failing_boundary"],
                      "phase_a": result["phase_a"]["decision"], "phase_b": None if result["phase_b"] is None else result["phase_b"]["decision"]}, indent=2))
    return 0 if result["status"] == "ready_for_human_review" else 1


if __name__ == "__main__":
    raise SystemExit(main())
