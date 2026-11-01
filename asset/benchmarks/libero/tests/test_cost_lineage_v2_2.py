"""Synthetic S1 for branch-aware, fail-closed R07 cost continuation."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import copy
import os
from pathlib import Path
import subprocess

import pytest


TOOL_PATH = Path(__file__).parents[1] / "tools" / "cost_lineage_v2_2.py"
READER_PATH = Path(__file__).parents[1] / "tools" / "cost_lineage_v2_2_reader.py"
PROTOCOL_PATH = Path(__file__).parents[1] / "protocols" / "r07_agent_cost_protocol_v2_2.json"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TOOL = _load_module("r07_cost_lineage_v2_2_s1", TOOL_PATH)
READER = _load_module("r07_cost_lineage_v2_2_reader_s1", READER_PATH)


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ).stdout.strip()


def _commit(repo, message):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _seal_result(result_path, result):
    unsigned = dict(result)
    unsigned.pop("result_sha256", None)
    result["result_sha256"] = TOOL.sha256_bytes(TOOL.canonical(unsigned))
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")


def _reader(root, repo, input_path, result_path, expected_sha=None):
    frozen = input_path.read_bytes()
    return READER.read_result(
        root,
        result_path,
        repo=repo,
        input_path=input_path,
        expected_input_sha256=expected_sha or hashlib.sha256(frozen).hexdigest(),
    )


def _fixture(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "R07 S1")
    _git(repo, "config", "user.email", "r07-s1@example.invalid")
    (repo / "README.md").write_text("common\n")
    common = _commit(repo, "common ancestry")

    _git(repo, "checkout", "-b", "historical")
    (repo / "historical.txt").write_text("historical measurement reference\n")
    historical = _commit(repo, "historical reference")

    _git(repo, "checkout", "-b", "session", common)
    for rel, text in {
        "task_env/owner.py": "def owner():\n    return 1\n",
        "bench_deploy/libero/recipe.py": "def recipe():\n    return 1\n",
        "asset/benchmarks/libero/tools/asset_tool.py": "def asset_tool():\n    return 1\n",
        "asset/benchmarks/libero/source_manifest.json": "{}\n",
        "docs/module/task_env/goal/Phase_II_01/README.md": "pilot\n",
        "docs/module/task_env/goal/Phase_II_01/07_Execution_Order_and_Acceptance.md": "order\n",
        "docs/module/task_env/goal/Phase_II_01/09_R07_Benchmark_Deployment_and_Agent_Cost.md": "cost\n",
        "docs/module/task_env/public-api.md": "public api\n",
        "docs/module/task_env/goal/Phase_II_01/planning_manifest.json": "{}\n",
        ".agents/skills/geochora-task-env/SKILL.md": "task env\n",
    }.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    start = _commit(repo, "session start")
    (repo / "task_env/owner.py").write_text("def owner():\n    return 2\n")
    (repo / "asset/benchmarks/libero/tools/new_tool.py").write_text("def new_tool():\n    return 2\n")
    final = _commit(repo, "session final")

    root = tmp_path / "package"
    (root / "cost/protocol").mkdir(parents=True)
    (root / "cost/prior").mkdir(parents=True)
    (root / "cost/protocol/r07_agent_cost_protocol_v2_2.json").write_bytes(PROTOCOL_PATH.read_bytes())
    prior_protocol = root / "cost/prior/prior_protocol.json"
    prior_protocol.write_text(json.dumps({
        "protocol_id": "geochora-r07-agent-cost",
        "version": "2.1.0",
        "schema": "r07-agent-cost-protocol-v2.1",
    }) + "\n")
    protocol_record = json.loads((root / "cost/protocol/r07_agent_cost_protocol_v2_2.json").read_text())
    protocol_record["extends"]["prior_protocol_sha256"] = hashlib.sha256(prior_protocol.read_bytes()).hexdigest()
    (root / "cost/protocol/r07_agent_cost_protocol_v2_2.json").write_text(
        json.dumps(protocol_record, sort_keys=True, indent=2) + "\n"
    )
    prior_result = root / "cost/prior/prior_result.json"
    prior_result.write_text(json.dumps({
        "status": "INVALID",
        "result_sha256": "d" * 64,
        "issues": [{"severity": "invalid", "code": "BASELINE_NOT_ANCESTOR_OF_EXECUTION"}],
    }) + "\n")
    prior_reader = root / "cost/prior/reader.py"
    prior_reader.write_text("# frozen v2 reader fixture\n")
    prior_tool = root / "cost/prior/prior_tool.py"
    prior_tool.write_text(
        "from pathlib import Path\n"
        "import hashlib\n"
        "def _hashes(root):\n"
        " return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file() and not p.is_symlink()}\n"
        "def compute_loc_delta(base_root, final_root):\n"
        " return {'baseline_files_sha256': _hashes(base_root), 'final_files_sha256': _hashes(final_root), 'effective_added_loc': 1, 'raw_added_lines': 1}\n"
    )
    evidence = {}
    for role, path in (("prior_protocol", prior_protocol), ("prior_result", prior_result), ("prior_tool", prior_tool), ("prior_reader", prior_reader)):
        evidence[role] = {"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    start = start
    record = {
        "schema_version": "r07-cost-continuation-input-v2_2",
        "protocol": {
            "path": "cost/protocol/r07_agent_cost_protocol_v2_2.json",
            "sha256": hashlib.sha256((root / "cost/protocol/r07_agent_cost_protocol_v2_2.json").read_bytes()).hexdigest(),
        },
        "identity": {
            "agent_id": "Luna2",
            "agent_thread_id": "01a186a5-7ac7-7c63-88f8-036b1f36d210",
            "input_head": start,
            "historical_reference_commit": historical,
        },
        "lineage": {
            "session_start_commit": start,
            "final_commit": final,
            "historical_measurement_reference_commit": historical,
            "expected_common_ancestor": common,
        },
        "prior_result_sha256": "d" * 64,
        "evidence": evidence,
        "inherited_costs": [{
            "aggregation_id": "R07a-history",
            "source_status": "unverified",
            "upgraded": False,
            "cost_fields": {"active_seconds": None, "tokens": None, "amount": None},
            "unknown_reasons": {
                "active_seconds": "no compatible monotonic activity ledger is available",
                "tokens": "historical token telemetry is not recorded",
                "amount": "no billing source bytes were preserved",
            },
        }, {
            "aggregation_id": "R07b-prior-invalid",
            "source_status": "INVALID",
            "upgraded": False,
            "cost_fields": {"active_seconds": None, "tokens": None, "amount": None},
            "unknown_reasons": {
                "active_seconds": "prior run status is INVALID and no independent cumulative ledger was accepted",
                "tokens": "prior token telemetry is unavailable",
                "amount": "prior billing record is unavailable",
            },
        }],
        "session_facts": {
            "start_timestamp_utc": "2026-10-29T12:00:00Z",
            "end_timestamp_utc": "2026-10-29T12:01:00Z",
            "time": {field: None for field in TOOL.REQUIRED_TIME_FIELDS},
            "usage": {field: None for field in TOOL.REQUIRED_USAGE_FIELDS},
            "money": {field: None for field in TOOL.REQUIRED_MONEY_FIELDS},
        },
        "source_snapshot_root": "cost/source_snapshots/s1_case",
    }
    for group, fields in (("time", TOOL.REQUIRED_TIME_FIELDS), ("usage", TOOL.REQUIRED_USAGE_FIELDS), ("money", TOOL.REQUIRED_MONEY_FIELDS)):
        for field in fields:
            record["session_facts"][group][field + "_reason"] = "synthetic fixture deliberately has no measurement telemetry"
    input_path = root / "cost/input.json"
    input_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    return root, repo, input_path, prior_tool, record, common, historical, start, final


def test_path_classification_counts_asset_benchmark_python_as_benchmark_code():
    assert TOOL.classify_path("asset/benchmarks/libero/tools/script.py") == "benchmark"
    assert TOOL.classify_path("bench_deploy/libero/recipe.py") == "benchmark"
    assert TOOL.classify_path("asset/benchmarks/libero/source_manifest.json") == "data"
    assert TOOL.classify_path("asset/benchmarks/libero/tests/test_source.py") == "tests"


def test_diverged_reference_structurally_validates_but_keeps_unknowns_partial(tmp_path):
    root, repo, input_path, prior_tool, *_ = _fixture(tmp_path)
    result = TOOL.validate_record(root, repo, input_path, prior_tool)
    assert result["lineage"]["historical_reference_is_current_session_ancestor"] is False
    assert result["lineage"]["branch_rewrite_performed"] is False
    assert result["prior_v2_1"]["status"] == "INVALID"
    assert result["prior_v2_1"]["upgraded"] is False
    assert result["structural_status"] == "STRUCTURALLY_VALID_PARTIAL"
    assert result["measurement_status"] == "INCOMPLETE"
    result_path = root / "cost/result.json"
    _seal_result(result_path, result)
    independent = _reader(root, repo, input_path, result_path)
    assert independent["reader_status"] == "VERIFIED_STRUCTURAL_PARTIAL"
    assert independent["prior_v2_1_status"] == "INVALID_PRESERVED"
    assert independent["input_sha256"] == hashlib.sha256(input_path.read_bytes()).hexdigest()


def test_reader_rejects_sol_reproduced_self_hashed_fake_git_identity(tmp_path):
    root, repo, input_path, prior_tool, *_ = _fixture(tmp_path)
    result = TOOL.validate_record(root, repo, input_path, prior_tool)
    result_path = root / "cost/result.json"
    # Reproduce the original attack: plausible-looking full SHA fields and a
    # recomputed producer self-hash cannot replace the frozen input/Git graph.
    result["identity"]["input_head"] = "0" * 40
    result["lineage"]["session_start_commit"] = "0" * 40
    result["lineage"]["final_commit"] = "1" * 40
    _seal_result(result_path, result)
    with pytest.raises(ValueError, match="identity differs from the frozen input"):
        _reader(root, repo, input_path, result_path)


def test_reader_recomputes_partial_status_instead_of_trusting_resigned_claim(tmp_path):
    root, repo, input_path, prior_tool, *_ = _fixture(tmp_path)
    result = TOOL.validate_record(root, repo, input_path, prior_tool)
    result_path = root / "cost/result.json"
    result["structural_status"] = "STRUCTURALLY_VALID_MEASURED"
    result["measurement_status"] = "STRUCTURALLY_VALID_MEASURED"
    _seal_result(result_path, result)
    with pytest.raises(ValueError, match="independently recomputed"):
        _reader(root, repo, input_path, result_path)


def test_reader_requires_caller_frozen_input_hash(tmp_path):
    root, repo, input_path, prior_tool, *_ = _fixture(tmp_path)
    result = TOOL.validate_record(root, repo, input_path, prior_tool)
    result_path = root / "cost/result.json"
    _seal_result(result_path, result)
    frozen_sha = hashlib.sha256(input_path.read_bytes()).hexdigest()
    record = json.loads(input_path.read_text())
    record["identity"]["agent_id"] = "Luna-Other"
    input_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    with pytest.raises(ValueError, match="caller-supplied SHA-256"):
        _reader(root, repo, input_path, result_path, frozen_sha)


def test_reader_rejects_snapshot_changed_even_when_loc_and_self_hash_are_resigned(tmp_path):
    root, repo, input_path, prior_tool, *_ = _fixture(tmp_path)
    result = TOOL.validate_record(root, repo, input_path, prior_tool)
    result_path = root / "cost/result.json"
    side = root / result["source_snapshot_root"] / "session_start" / "task_env/owner.py"
    side.write_text("def forged():\n    return 99\n")
    result["loc_delta"]["baseline_files_sha256"]["task_env/owner.py"] = hashlib.sha256(side.read_bytes()).hexdigest()
    _seal_result(result_path, result)
    with pytest.raises(ValueError, match="Git commit/blob tree"):
        _reader(root, repo, input_path, result_path)


def test_verified_inherited_values_need_exact_committed_source_ledger(tmp_path):
    root, repo, input_path, prior_tool, record, common, historical, start, final = _fixture(tmp_path)
    row = record["inherited_costs"][0]
    row["source_status"] = "verified"
    row["cost_fields"] = {"active_seconds": 12.0, "tokens": 120, "amount": 0.25}
    row["unknown_reasons"] = {}
    input_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    with pytest.raises(ValueError, match="requires source evidence"):
        TOOL.validate_record(root, repo, input_path, prior_tool)


def test_reader_accepts_partial_result_with_byte_bound_cross_branch_ledger(tmp_path):
    root, repo, input_path, prior_tool, record, common, historical, start, final = _fixture(tmp_path)
    _git(repo, "checkout", "historical")
    ledger = {
        "schema_version": "r07-inherited-cost-ledger-v1",
        "aggregation_id": "R07a-history",
        "source_status": "verified",
        "cost_fields": {"active_seconds": 12.0, "tokens": 120, "amount": 0.25},
        "unknown_reasons": {},
    }
    ledger_path = repo / "cost-ledgers/r07a.json"
    ledger_path.parent.mkdir(parents=True)
    ledger_bytes = json.dumps(ledger, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    ledger_path.write_bytes(ledger_bytes)
    source_commit = _commit(repo, "add byte-bound cost ledger")
    _git(repo, "checkout", "session")
    record["identity"]["historical_reference_commit"] = source_commit
    record["lineage"]["historical_measurement_reference_commit"] = source_commit
    row = record["inherited_costs"][0]
    row["source_status"] = "verified"
    row["cost_fields"] = ledger["cost_fields"]
    row["unknown_reasons"] = {}
    row["source_evidence"] = {
        "commit": source_commit,
        "path": "cost-ledgers/r07a.json",
        "sha256": hashlib.sha256(ledger_bytes).hexdigest(),
    }
    input_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    result = TOOL.validate_record(root, repo, input_path, prior_tool)
    result_path = root / "cost/result.json"
    _seal_result(result_path, result)
    independent = _reader(root, repo, input_path, result_path)
    assert independent["reader_status"] == "VERIFIED_STRUCTURAL_PARTIAL"
    assert independent["measurement_status"] == "INCOMPLETE"


def test_reader_rejects_wrong_merge_base_after_self_hash_recalculation(tmp_path):
    root, repo, input_path, prior_tool, *_ = _fixture(tmp_path)
    result = TOOL.validate_record(root, repo, input_path, prior_tool)
    result_path = root / "cost/result.json"
    result["lineage"]["actual_common_ancestor"] = result["lineage"]["historical_measurement_reference_commit"]
    _seal_result(result_path, result)
    with pytest.raises(ValueError, match="Git graph"):
        _reader(root, repo, input_path, result_path)


def test_wrong_common_ancestor_is_rejected(tmp_path):
    root, repo, input_path, prior_tool, record, _, historical, _, _ = _fixture(tmp_path)
    record["lineage"]["expected_common_ancestor"] = historical
    input_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    with pytest.raises(ValueError, match="common ancestor"):
        TOOL.validate_record(root, repo, input_path, prior_tool)


def test_final_on_another_run_or_non_descendant_is_rejected(tmp_path):
    root, repo, input_path, prior_tool, record, _, _, _, _ = _fixture(tmp_path)
    record["lineage"]["final_commit"] = record["lineage"]["historical_measurement_reference_commit"]
    input_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    with pytest.raises(ValueError, match="not an ancestor"):
        TOOL.validate_record(root, repo, input_path, prior_tool)


def test_missing_inherited_cost_reason_and_duplicate_aggregation_are_rejected(tmp_path):
    root, repo, input_path, prior_tool, record, *_ = _fixture(tmp_path)
    del record["inherited_costs"][0]["unknown_reasons"]["tokens"]
    input_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    with pytest.raises(ValueError, match="requires a reason"):
        TOOL.validate_record(root, repo, input_path, prior_tool)

    root, repo, input_path, prior_tool, record, *_ = _fixture(tmp_path / "duplicate")
    record["inherited_costs"][1]["aggregation_id"] = record["inherited_costs"][0]["aggregation_id"]
    input_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    with pytest.raises(ValueError, match="unique"):
        TOOL.validate_record(root, repo, input_path, prior_tool)


def test_missing_token_field_is_not_accepted_as_null_with_reason(tmp_path):
    root, repo, input_path, prior_tool, record, *_ = _fixture(tmp_path)
    del record["session_facts"]["usage"]["input_tokens"]
    input_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    with pytest.raises(ValueError, match="missing required fields"):
        TOOL.validate_record(root, repo, input_path, prior_tool)


def test_prior_evidence_byte_and_session_source_identity_mismatches_are_rejected(tmp_path):
    root, repo, input_path, prior_tool, record, *_ = _fixture(tmp_path)
    prior_tool.write_text(prior_tool.read_text() + "# mutated after reference\n")
    with pytest.raises(ValueError, match="prior_tool evidence changed"):
        TOOL.validate_record(root, repo, input_path, prior_tool)

    root, repo, input_path, prior_tool, record, *_ = _fixture(tmp_path / "bad_blob")
    record["identity"]["input_head"] = "1" * 40
    input_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    with pytest.raises(ValueError, match="input HEAD"):
        TOOL.validate_record(root, repo, input_path, prior_tool)


def test_prior_invalid_cannot_be_implicitly_upgraded(tmp_path):
    root, repo, input_path, prior_tool, record, *_ = _fixture(tmp_path)
    record["inherited_costs"][1]["upgraded"] = True
    input_path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    with pytest.raises(ValueError, match="cannot be upgraded"):
        TOOL.validate_record(root, repo, input_path, prior_tool)
