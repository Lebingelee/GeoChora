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
    args = parser.parse_args()

    contract_path = args.contract.resolve()
    probe_path = args.probe.resolve()
    repo = args.repo.resolve()
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    ast.parse(probe_path.read_text(encoding="utf-8"), filename=str(probe_path))
    module, newly_loaded = load_probe_module(probe_path)

    basis = module.candidate_basis_sha256(contract)
    if basis != "7c639ca471642fd0e044c9ee7e3632aafb7fa80722a3074676bc78abebac8102":
        raise AssertionError(f"candidate basis changed: {basis}")
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
        "over_budget_candidate_rejected": True,
        "unsupported_runtime_rejected": True,
        "static_source_preflight": static,
    }
    print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
