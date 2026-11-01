#!/usr/bin/env python3
"""Independent reader for R07 cost-lineage continuation v2.2.

The result self-hash detects accidental corruption only. Acceptance also needs
the caller's frozen input digest and a read-only Git repository so lineage and
the source snapshots can be checked against immutable commit/blob objects.
This module intentionally does not import the producer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any


HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ARCHIVE_PATHS = (
    "task_env",
    "bench_deploy/libero",
    "asset/benchmarks/libero",
    "docs/module/task_env/goal/Phase_II_01/07_Execution_Order_and_Acceptance.md",
    "docs/module/task_env/goal/Phase_II_01/09_R07_Benchmark_Deployment_and_Agent_Cost.md",
    "docs/module/task_env/goal/Phase_II_01/README.md",
    "docs/module/task_env/public-api.md",
    "docs/module/task_env/goal/Phase_II_01/planning_manifest.json",
    ".agents/skills/geochora-task-env/SKILL.md",
)
TIME_FIELDS = (
    "session_wall_seconds", "active_development_seconds", "install_seconds",
    "test_seconds", "debug_seconds", "waiting_seconds", "human_assistance_seconds",
)
USAGE_FIELDS = (
    "input_tokens", "output_tokens", "cached_input_tokens", "input_includes_cached",
)
MONEY_FIELDS = (
    "amount", "currency", "billing_source_path", "billing_source_sha256",
)
INHERITED_FIELDS = frozenset({"active_seconds", "tokens", "amount"})
INHERITED_ROW_FIELDS = frozenset({
    "aggregation_id", "source_status", "upgraded", "cost_fields", "unknown_reasons",
})


def _reject_constant(value: str):
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load(path: Path):
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=_reject_constant,
        object_pairs_hook=_unique_object,
    )


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve(root: Path, value: str) -> Path:
    if type(value) is not str:
        raise ValueError("package path must be text")
    rel = PurePosixPath(value)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts or "\\" in value:
        raise ValueError(f"unsafe package-relative path: {value!r}")
    resolved_root = root.resolve()
    path = (resolved_root / Path(*rel.parts)).resolve()
    if resolved_root not in path.parents and path != resolved_root:
        raise ValueError(f"path escapes package root: {value!r}")
    return path


def _git(repo: Path, *args: str, timeout: float = 30.0) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if proc.returncode:
        detail = proc.stderr.decode("utf-8", "replace")[:500]
        raise ValueError(f"git {' '.join(args)} failed ({proc.returncode}): {detail}")
    return proc.stdout


def _commit(repo: Path, value: Any, label: str) -> str:
    if type(value) is not str or not HEX40.fullmatch(value):
        raise ValueError(f"{label} must be a full lowercase Git SHA-1")
    resolved = _git(repo, "rev-parse", "--verify", f"{value}^{{commit}}").decode().strip()
    if resolved != value:
        raise ValueError(f"{label} does not resolve to the exact commit")
    return value


def _is_ancestor(repo: Path, older: str, newer: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", older, newer],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30.0,
    )
    if proc.returncode not in (0, 1):
        raise ValueError("Git could not determine commit ancestry")
    return proc.returncode == 0


def _merge_base(repo: Path, left: str, right: str) -> str:
    return _git(repo, "merge-base", left, right).decode("ascii").strip()


def _tree_hashes(root: Path) -> dict[str, str]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"source snapshot is missing or unsafe: {root}")
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"source snapshot symlink is forbidden: {path}")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = _sha_file(path)
    return result


def _git_snapshot_hashes(repo: Path, commit: str) -> dict[str, str]:
    """Read exact blobs with Git plumbing; no producer archive is trusted."""
    raw = _git(repo, "ls-tree", "-r", "-z", "--full-tree", commit, "--", *ARCHIVE_PATHS)
    result: dict[str, str] = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            header, name_bytes = record.split(b"\t", 1)
            mode, kind, oid = header.decode("ascii").split(" ")
            name = name_bytes.decode("utf-8", "strict")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("Git tree entry is malformed") from exc
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ValueError(f"source snapshot contains a non-regular Git entry: {name}")
        if name in result:
            raise ValueError(f"Git source snapshot contains duplicate path: {name}")
        body = _git(repo, "cat-file", "blob", oid, timeout=45.0)
        result[name] = _sha(body)
    return result


def _validate_fact_group(group: Any, fields: tuple[str, ...], label: str) -> bool:
    if type(group) is not dict:
        raise ValueError(f"{label} must be an object")
    missing = [field for field in fields if field not in group]
    if missing:
        raise ValueError(f"{label} is missing required fields: {', '.join(missing)}")
    unknown_fields = set(group) - set(fields) - {field + "_reason" for field in fields}
    if unknown_fields:
        raise ValueError(f"{label} contains unknown fields: {', '.join(sorted(unknown_fields))}")
    incomplete = False
    for field in fields:
        value = group[field]
        reason_field = field + "_reason"
        if value is None:
            reason = group.get(reason_field)
            if type(reason) is not str or not reason.strip():
                raise ValueError(f"{label}.{field}=null requires a specific reason")
            incomplete = True
        else:
            if reason_field in group:
                raise ValueError(f"{label}.{reason_field} is only valid for a null value")
            if label.endswith(".time"):
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise ValueError(f"{label}.{field} must be a finite nonnegative number or null")
            elif label.endswith(".usage"):
                if field == "input_includes_cached":
                    if type(value) is not bool:
                        raise ValueError(f"{label}.{field} must be boolean or null")
                elif type(value) is not int or value < 0:
                    raise ValueError(f"{label}.{field} must be a nonnegative integer or null")
            elif field == "amount":
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise ValueError(f"{label}.{field} must be a finite nonnegative number or null")
            elif field == "currency":
                if type(value) is not str or not value.strip():
                    raise ValueError(f"{label}.{field} must be a nonempty string or null")
            elif field == "billing_source_path":
                if type(value) is not str or not value.strip():
                    raise ValueError(f"{label}.{field} must be a nonempty string or null")
            elif field == "billing_source_sha256":
                if type(value) is not str or not HEX64.fullmatch(value):
                    raise ValueError(f"{label}.{field} must be a lowercase SHA-256 or null")
    return incomplete


def _validate_inherited(rows: Any, root: Path, repo: Path) -> bool:
    if type(rows) is not list or not rows:
        raise ValueError("inherited cost ledger requires explicit rows")
    seen: set[str] = set()
    incomplete = False
    for index, row in enumerate(rows):
        label = f"inherited_costs[{index}]"
        if type(row) is not dict:
            raise ValueError(f"{label} must be an object")
        if set(row) not in (INHERITED_ROW_FIELDS, INHERITED_ROW_FIELDS | {"source_evidence"}):
            raise ValueError(f"{label} field set is invalid")
        aggregation_id = row.get("aggregation_id")
        if type(aggregation_id) is not str or not aggregation_id.strip() or aggregation_id in seen:
            raise ValueError("inherited aggregation IDs must be unique nonempty tokens")
        seen.add(aggregation_id)
        status = row.get("source_status")
        if status not in {"verified", "unverified", "INVALID"}:
            raise ValueError(f"{label}.source_status is invalid")
        if type(row.get("upgraded")) is not bool:
            raise ValueError(f"{label}.upgraded must be boolean")
        if status == "INVALID" and row["upgraded"] is not False:
            raise ValueError("historical INVALID evidence cannot be upgraded")
        fields, reasons = row.get("cost_fields"), row.get("unknown_reasons")
        if type(fields) is not dict or set(fields) != INHERITED_FIELDS:
            raise ValueError(f"{label}.cost_fields must contain exactly {sorted(INHERITED_FIELDS)}")
        if type(reasons) is not dict:
            raise ValueError(f"{label}.unknown_reasons must be an object")
        unknown_values = {key for key, value in fields.items() if value is None}
        missing_reasons = unknown_values - set(reasons)
        if missing_reasons:
            field = sorted(missing_reasons)[0]
            raise ValueError(f"inherited {aggregation_id}.{field}=null requires a reason")
        if set(reasons) != unknown_values:
            raise ValueError(f"{label}.unknown_reasons contains reasons for non-null cost fields")
        for field, value in fields.items():
            if value is None:
                if type(reasons.get(field)) is not str or not reasons[field].strip():
                    raise ValueError(f"inherited {aggregation_id}.{field}=null requires a reason")
                incomplete = True
            elif field == "tokens":
                if type(value) is not int or value < 0:
                    raise ValueError(f"inherited {aggregation_id}.tokens must be a nonnegative integer")
            elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"inherited {aggregation_id}.{field} must be a finite nonnegative number")
        evidence = row.get("source_evidence")
        if status == "verified":
            if type(evidence) is not dict or set(evidence) != {"commit", "path", "sha256"}:
                raise ValueError(f"verified inherited ledger {aggregation_id} requires source evidence")
            if type(evidence["sha256"]) is not str or not HEX64.fullmatch(evidence["sha256"]):
                raise ValueError(f"verified inherited ledger {aggregation_id} has an invalid source digest")
            source_commit = _commit(repo, evidence.get("commit"), f"{label}.source_evidence.commit")
            source_rel = PurePosixPath(evidence.get("path", ""))
            if source_rel.is_absolute() or ".." in source_rel.parts or not source_rel.parts or "\\" in str(source_rel):
                raise ValueError(f"verified inherited ledger {aggregation_id} has an unsafe Git path")
            source_bytes = _git(repo, "cat-file", "blob", f"{source_commit}:{source_rel.as_posix()}")
            if _sha(source_bytes) != evidence["sha256"]:
                raise ValueError(f"verified inherited ledger {aggregation_id} does not match its Git blob")
            ledger = json.loads(source_bytes.decode("utf-8"), parse_constant=_reject_constant, object_pairs_hook=_unique_object)
            if (type(ledger) is not dict
                    or set(ledger) != {"schema_version", "aggregation_id", "source_status", "cost_fields", "unknown_reasons"}
                    or ledger.get("schema_version") != "r07-inherited-cost-ledger-v1"
                    or ledger.get("aggregation_id") != aggregation_id
                    or ledger.get("source_status") != "verified"
                    or ledger.get("cost_fields") != fields
                    or ledger.get("unknown_reasons") != reasons):
                raise ValueError(f"verified inherited ledger {aggregation_id} content differs from its bound Git blob")
        elif evidence is not None:
            raise ValueError(f"unverified inherited ledger {aggregation_id} cannot carry verified source evidence")
        if status in {"unverified", "INVALID"} and any(value is not None for value in fields.values()):
            raise ValueError(f"{status} inherited ledger {aggregation_id} cannot contribute measured values")
    return incomplete


def _validate_protocol_and_prior(root: Path, result: dict, input_data: dict) -> tuple[int, bool]:
    protocol = result.get("protocol")
    if type(protocol) is not dict or protocol.get("version") != "2.2.0":
        raise ValueError("result does not bind protocol v2.2")
    input_protocol = input_data.get("protocol")
    if type(input_protocol) is not dict or protocol != {
        "path": input_protocol.get("path"),
        "sha256": input_protocol.get("sha256"),
        "version": "2.2.0",
    }:
        raise ValueError("result protocol identity differs from the frozen input")
    protocol_path = _resolve(root, protocol.get("path"))
    protocol_bytes = protocol_path.read_bytes()
    if _sha(protocol_bytes) != protocol.get("sha256"):
        raise ValueError("protocol bytes changed after the result was created")
    protocol_value = _load(protocol_path)
    if (protocol_value.get("protocol_id") != "geochora-r07-agent-cost"
            or protocol_value.get("version") != "2.2.0"
            or protocol_value.get("status") != "CANDIDATE_CONTINUATION_PENDING_SOL_TECHNICAL_REVIEW"):
        raise ValueError("protocol identity/review gate is not pending Sol")

    evidence = input_data.get("evidence")
    if type(evidence) is not dict or set(evidence) != {"prior_protocol", "prior_result", "prior_tool", "prior_reader"}:
        raise ValueError("frozen input prior evidence references are incomplete")
    if result.get("source_evidence") != evidence:
        raise ValueError("result prior evidence references differ from the frozen input")
    prior_paths = {}
    for role, ref in evidence.items():
        if type(ref) is not dict or set(ref) != {"path", "sha256"} or type(ref.get("sha256")) is not str or not HEX64.fullmatch(ref["sha256"]):
            raise ValueError(f"{role} evidence path/hash reference is malformed")
        prior_path = _resolve(root, ref["path"])
        if not prior_path.is_file() or _sha_file(prior_path) != ref["sha256"]:
            raise ValueError(f"{role} evidence bytes changed")
        prior_paths[role] = prior_path
    prior_protocol = _load(prior_paths["prior_protocol"])
    if (prior_protocol.get("protocol_id") != "geochora-r07-agent-cost"
            or prior_protocol.get("version") != "2.1.0"
            or prior_protocol.get("schema") != "r07-agent-cost-protocol-v2.1"):
        raise ValueError("bound prior protocol identity is not v2.1")
    if protocol_value.get("extends", {}).get("prior_protocol_sha256") != evidence["prior_protocol"]["sha256"]:
        raise ValueError("continuation protocol does not bind exact prior v2.1 protocol bytes")
    legacy = _load(prior_paths["prior_result"])
    prior_result = result.get("prior_v2_1")
    if (type(prior_result) is not dict or prior_result.get("status") != "INVALID"
            or prior_result.get("upgraded") is not False
            or prior_result.get("result_sha256") != legacy.get("result_sha256")
            or legacy.get("status") != "INVALID"
            or input_data.get("prior_result_sha256") != legacy.get("result_sha256")):
        raise ValueError("prior INVALID result identity/status is not bound and preserved")
    codes = [row.get("code") for row in legacy.get("issues", []) if type(row) is dict]
    if "BASELINE_NOT_ANCESTOR_OF_EXECUTION" not in codes or prior_result.get("issue_codes") != codes:
        raise ValueError("original prior INVALID issue attribution changed")
    if any(row.get("source_status") == "INVALID" and row.get("upgraded") is not False for row in result.get("inherited_costs", []) if type(row) is dict):
        raise ValueError("historical INVALID inheritance was upgraded")
    return sum(1 for role in prior_paths), True


def read_result(
    root: Path,
    result_path: Path,
    *,
    repo: Path,
    input_path: Path,
    expected_input_sha256: str,
) -> dict:
    """Verify a result against frozen input bytes and immutable Git objects.

    ``expected_input_sha256`` is supplied by the independent caller from the
    package freeze; it must not be read from the result or producer output.
    """
    root, repo, result_path, input_path = (
        Path(root).resolve(), Path(repo).resolve(), Path(result_path).resolve(), Path(input_path).resolve()
    )
    if type(expected_input_sha256) is not str or not HEX64.fullmatch(expected_input_sha256):
        raise ValueError("independent frozen input SHA-256 is required")
    input_bytes = input_path.read_bytes()
    input_sha = _sha(input_bytes)
    if input_sha != expected_input_sha256:
        raise ValueError("frozen input bytes differ from the caller-supplied SHA-256")
    input_data = json.loads(input_bytes.decode("utf-8"), parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    if type(input_data) is not dict or input_data.get("schema_version") != "r07-cost-continuation-input-v2_2":
        raise ValueError("unsupported frozen cost continuation input schema")

    result = _load(result_path)
    if type(result) is not dict or result.get("schema_version") != "r07-cost-continuation-result-v2_2":
        raise ValueError("unsupported continuation result schema")
    claimed = result.get("result_sha256")
    unsigned = dict(result)
    unsigned.pop("result_sha256", None)
    if type(claimed) is not str or not HEX64.fullmatch(claimed) or _sha(_canonical(unsigned)) != claimed:
        raise ValueError("continuation result self-hash mismatch")
    if result.get("input_sha256") != expected_input_sha256:
        raise ValueError("result does not bind the caller-frozen input identity")
    if result.get("deployment_ready") is not False or result.get("cumulative_r07_cost_claim_allowed") is not False:
        raise ValueError("continuation result cannot grant deployment or cumulative-cost approval")

    identity = input_data.get("identity")
    lineage = input_data.get("lineage")
    if type(identity) is not dict or type(lineage) is not dict or result.get("identity") != identity:
        raise ValueError("result identity differs from the frozen input")
    start = _commit(repo, lineage.get("session_start_commit"), "lineage.session_start_commit")
    final = _commit(repo, lineage.get("final_commit"), "lineage.final_commit")
    historical = _commit(repo, lineage.get("historical_measurement_reference_commit"), "lineage.historical_measurement_reference_commit")
    expected_base = _commit(repo, lineage.get("expected_common_ancestor"), "lineage.expected_common_ancestor")
    if identity.get("input_head") != start or identity.get("historical_reference_commit") != historical:
        raise ValueError("frozen input identity is not bound to the Git lineage")
    if not _is_ancestor(repo, start, final):
        raise ValueError("session start is not an ancestor of final commit")
    actual_base = _merge_base(repo, historical, start)
    final_base = _merge_base(repo, historical, final)
    if actual_base != expected_base or final_base != expected_base:
        raise ValueError("recorded common ancestor differs from Git merge-base")
    expected_lineage = {
        "session_start_commit": start,
        "final_commit": final,
        "historical_measurement_reference_commit": historical,
        "actual_common_ancestor": actual_base,
        "historical_reference_is_current_session_ancestor": _is_ancestor(repo, historical, start),
        "branch_rewrite_performed": False,
    }
    if result.get("lineage") != expected_lineage:
        raise ValueError("result lineage identity/facts differ from the verified Git graph")

    if result.get("source_snapshot_root") != input_data.get("source_snapshot_root"):
        raise ValueError("source snapshot path differs from the frozen input")
    loc = result.get("loc_delta")
    if type(loc) is not dict or loc.get("path_class_policy") != "r07-cost-path-v2_2-asset-benchmark-python-before-data":
        raise ValueError("LOC classification policy is not the reviewed v2.2 ordering")
    if loc.get("snapshot_source_commits") != {"session_start": start, "final": final}:
        raise ValueError("LOC source snapshot commits differ from verified lineage")
    snapshot_root = _resolve(root, input_data.get("source_snapshot_root"))
    expected_files = {}
    for side, commit, key in (("session_start", start, "baseline_files_sha256"), ("final", final, "final_files_sha256")):
        actual_snapshot = _tree_hashes(snapshot_root / side)
        git_hashes = _git_snapshot_hashes(repo, commit)
        if actual_snapshot != git_hashes:
            raise ValueError(f"{side} snapshot path/bytes differ from the specified Git commit/blob tree")
        claimed_snapshot = loc.get(key)
        if type(claimed_snapshot) is not dict or claimed_snapshot != git_hashes:
            raise ValueError(f"{side} source snapshot differs from independently read Git blobs")
        expected_files[side] = git_hashes

    prior_count, _ = _validate_protocol_and_prior(root, result, input_data)
    if result.get("inherited_costs") != input_data.get("inherited_costs"):
        raise ValueError("inherited ledger differs from the frozen input")
    if result.get("session_facts") != input_data.get("session_facts"):
        raise ValueError("session facts differ from the frozen input")
    inherited_incomplete = _validate_inherited(input_data.get("inherited_costs"), root, repo)
    facts = input_data.get("session_facts")
    if type(facts) is not dict:
        raise ValueError("session_facts are required")
    time_incomplete = _validate_fact_group(facts.get("time"), TIME_FIELDS, "session_facts.time")
    usage_incomplete = _validate_fact_group(facts.get("usage"), USAGE_FIELDS, "session_facts.usage")
    money_incomplete = _validate_fact_group(facts.get("money"), MONEY_FIELDS, "session_facts.money")
    for field in ("start_timestamp_utc", "end_timestamp_utc"):
        if type(facts.get(field)) is not str or not facts[field].endswith("Z"):
            raise ValueError(f"session_facts.{field} must be an explicit UTC timestamp ending Z")
    expected_incomplete = inherited_incomplete or time_incomplete or usage_incomplete or money_incomplete
    expected_status = "INCOMPLETE" if expected_incomplete else "STRUCTURALLY_VALID_MEASURED"
    expected_structure = "STRUCTURALLY_VALID_PARTIAL" if expected_incomplete else "STRUCTURALLY_VALID_MEASURED"
    if result.get("measurement_status") != expected_status or result.get("structural_status") != expected_structure:
        raise ValueError("declared status differs from independently recomputed cost completeness")

    return {
        "schema_version": "r07-cost-lineage-reader-result-v1",
        "reader_status": "VERIFIED_STRUCTURAL_PARTIAL" if expected_incomplete else "VERIFIED_STRUCTURAL_ONLY",
        "measurement_status": expected_status,
        "prior_v2_1_status": "INVALID_PRESERVED",
        "result_sha256": claimed,
        "input_sha256": input_sha,
        "source_files_checked": sum(len(value) for value in expected_files.values()),
        "prior_evidence_files_checked": prior_count,
        "cumulative_r07_cost_claim_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--expected-input-sha256", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        value = read_result(
            root,
            _resolve(root, args.result),
            repo=args.repo,
            input_path=_resolve(root, args.input),
            expected_input_sha256=args.expected_input_sha256,
        )
        print(json.dumps(value, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"schema_version": "r07-cost-lineage-reader-result-v1", "reader_status": "REJECTED", "reason": f"{type(exc).__name__}: {exc}"}, sort_keys=True))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
