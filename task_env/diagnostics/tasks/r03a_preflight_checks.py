"""Minimal stdlib-only S1 checks for the authorized R03a candidate.

This validates the frozen candidate's static contract gates and source closure.
It deliberately never imports MuJoCo, Taichi, GeoChora Core, or GeoPhys and
never calls the native probe's main/execute functions.
"""
from __future__ import annotations

import argparse
import ast
import copy
import importlib.util
import json
import sys
from pathlib import Path


FORBIDDEN_MODULES = ("mujoco", "taichi", "task_env", "geophys")


def forbidden_loaded(modules: set[str]) -> list[str]:
    return sorted(
        name for name in modules
        if any(name == prefix or name.startswith(prefix + ".") for prefix in FORBIDDEN_MODULES)
    )


def load_probe_module(path: Path):
    before = set(sys.modules)
    spec = importlib.util.spec_from_file_location("r03a_probe_s1_subject", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot create import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    loaded = forbidden_loaded(set(sys.modules))
    if loaded:
        raise AssertionError(f"probe module import loaded forbidden modules: {loaded}")
    return module, sorted(set(sys.modules) - before)


def expect_candidate_block(module, candidate: dict, label: str) -> None:
    try:
        module.validate_supported_candidate(candidate)
    except module.CandidateBlocked:
        return
    raise AssertionError(f"unsupported candidate was not rejected: {label}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--expected-basis", required=True)
    parser.add_argument("--attempt001-evidence", required=True, type=Path)
    args = parser.parse_args()

    contract_path = args.contract.resolve()
    probe_path = args.probe.resolve()
    repo = args.repo.resolve()
    attempt001_evidence_path = args.attempt001_evidence.resolve()
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    ast.parse(probe_path.read_text(encoding="utf-8"), filename=str(probe_path))
    module, newly_loaded = load_probe_module(probe_path)

    basis = module.candidate_basis_sha256(contract)
    if basis != args.expected_basis:
        raise AssertionError(f"calculated candidate basis differs from explicit expected basis: {basis}")
    if basis != contract["artifacts"]["candidate_basis_sha256"]:
        raise AssertionError("stored candidate basis does not match calculated basis")
    if module.approval_gate(contract, basis):
        raise AssertionError(f"approved candidate has missing approvals: {module.approval_gate(contract, basis)}")
    module.validate_supported_candidate(contract)
    input_identity = module.repo_and_artifact_preflight(repo, contract_path, contract)
    if input_identity["candidate_basis_sha256"] != basis:
        raise AssertionError("production input preflight returned a different candidate basis")

    missing_approval = copy.deepcopy(contract)
    missing_approval["approvals"]["native_execution_authorization"] = None
    missing_rejected = "native_execution_authorization" in module.approval_gate(missing_approval, basis)
    if not missing_rejected:
        raise AssertionError("missing native authorization was not rejected")

    wrong_basis = copy.deepcopy(contract)
    wrong_basis["approvals"]["numerical_thresholds"]["candidate_basis_sha256"] = "0" * 64
    wrong_basis_rejected = "numerical_thresholds" in module.approval_gate(wrong_basis, basis)
    if not wrong_basis_rejected:
        raise AssertionError("wrong-basis approval was not rejected")
    wrong_stored_basis = copy.deepcopy(contract)
    wrong_stored_basis["artifacts"]["candidate_basis_sha256"] = "0" * 64
    try:
        module.repo_and_artifact_preflight(repo, contract_path, wrong_stored_basis)
    except module.CandidateBlocked:
        wrong_stored_basis_rejected = True
    else:
        raise AssertionError("wrong stored candidate basis was not rejected by production preflight")

    wrong_operating_target = copy.deepcopy(contract)
    wrong_operating_target["actuation"]["hand"]["operating_targets"]["close_ctrl"] = 0.0
    expect_candidate_block(module, wrong_operating_target, "wrong interior Hand close command")

    wrong_reset = copy.deepcopy(contract)
    wrong_reset["reset"]["hand_finger_qpos_m"] = [0.04, 0.04]
    expect_candidate_block(module, wrong_reset, "reset outside the approved interior target")

    hand = contract["actuation"]["hand"]
    targets = hand["operating_targets"]
    close_mapped = module.hand_ctrl_for_finger_qpos(
        targets["close_each_finger_qpos_m"], hand["finger_joint_range_each_m"], hand["ctrlrange"]
    )
    open_mapped = module.hand_ctrl_for_finger_qpos(
        targets["open_each_finger_qpos_m"], hand["finger_joint_range_each_m"], hand["ctrlrange"]
    )
    if abs(close_mapped - targets["close_ctrl"]) > 1e-12 or abs(open_mapped - targets["open_ctrl"]) > 1e-12:
        raise AssertionError("interior Hand qpos-to-control mapping differs")
    if contract["reset"]["hand_finger_qpos_m"] != [targets["open_each_finger_qpos_m"]] * 2:
        raise AssertionError("reset finger qpos differs from the approved open target")
    if contract["reset"]["hand_ctrl"] != targets["open_ctrl"]:
        raise AssertionError("reset control differs from the approved open target")

    prior_reference = contract["prior_attempt001"]
    prior_sha256 = module.sha256_file(attempt001_evidence_path)
    if prior_sha256 != prior_reference["probe_evidence_sha256"]:
        raise AssertionError("preserved attempt001 evidence hash differs from the new contract provenance")
    prior = json.loads(attempt001_evidence_path.read_text(encoding="utf-8"))
    if prior.get("result") != "FAIL":
        raise AssertionError("attempt001 raw failure is not preserved as FAIL")
    prior_rows = [row for trial in prior.get("trials", []) for row in trial.get("samples", [])]
    old_sample = next((row for row in prior_rows
                       if row.get("joint_positions_by_native_name", {}).get("probe_hand_finger_joint1") == 0.040001041818975604), None)
    if old_sample is None:
        raise AssertionError("attempt001 public range-failure sample was not found")
    old_qpos = old_sample["joint_positions_by_native_name"]["probe_hand_finger_joint1"]
    old_gate_rejected = False
    try:
        module.enforce_joint_range("probe_hand_finger_joint1", old_qpos, 0.0, 0.04,
                                   contract["oracles"]["state_limits_clock"]["joint_range_overrun_max_rad_or_m"])
    except module.CandidateCheckFailed:
        old_gate_rejected = True
    if not old_gate_rejected:
        raise AssertionError("attempt001 0.040001041818975604 m sample no longer fails the 1e-6 m gate")

    over_budget = copy.deepcopy(contract)
    over_budget["budgets"]["trials"] = 3
    expect_candidate_block(module, over_budget, "trials=3")

    unsupported_runtime = copy.deepcopy(contract)
    unsupported_runtime["source"]["candidate_provider"]["runtime"] = "MuJoCo EGL"
    expect_candidate_block(module, unsupported_runtime, "non-CPU runtime")

    static = module.static_source_preflight(repo, contract, contract_path)
    if not static.get("files") or not static.get("mount"):
        raise AssertionError("static source preflight omitted source or mount evidence")

    forbidden = forbidden_loaded(set(sys.modules))
    if forbidden:
        raise AssertionError(f"S1 loaded forbidden modules: {forbidden}")
    result = {
        "result": "S1_STATIC_PREPARATION_CHECKS_PASS",
        "r03a_core_s1": "NOT_CLAIMED",
        "native_execution": "NOT_RUN_BY_THIS_CHECKER",
        "candidate_basis_sha256": basis,
        "production_input_preflight": input_identity,
        "probe_ast_parse": "PASS",
        "probe_module_import": "PASS_STDLIB_ONLY",
        "new_modules_count": len(newly_loaded),
        "forbidden_modules_loaded": [],
        "approved_candidate_validation": "PASS",
        "missing_approval_rejected": missing_rejected,
        "wrong_basis_approval_rejected": wrong_basis_rejected,
        "wrong_stored_basis_rejected": wrong_stored_basis_rejected,
        "wrong_operating_target_rejected": True,
        "wrong_interior_reset_rejected": True,
        "interior_qpos_ctrl_mapping": {
            "close_qpos_m": targets["close_each_finger_qpos_m"],
            "close_ctrl": close_mapped,
            "open_qpos_m": targets["open_each_finger_qpos_m"],
            "open_ctrl": open_mapped,
            "native_joint_range_m": hand["finger_joint_range_each_m"],
            "native_ctrlrange": hand["ctrlrange"],
        },
        "attempt001_range_regression": {
            "evidence_sha256": prior_sha256,
            "sample_qpos_m": old_qpos,
            "overrun_m": module.joint_range_overrun(old_qpos, 0.0, 0.04),
            "tolerance_m": contract["oracles"]["state_limits_clock"]["joint_range_overrun_max_rad_or_m"],
            "rejected": old_gate_rejected,
        },
        "over_budget_candidate_rejected": True,
        "unsupported_runtime_rejected": True,
        "static_source_preflight": static,
    }
    print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
