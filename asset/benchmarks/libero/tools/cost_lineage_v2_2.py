#!/usr/bin/env python3
"""R07 cost-lineage continuation validator (v2.2, stdlib except prior LOC module).

This tool validates lineage and evidence structure. It never upgrades legacy
results, estimates missing cost, installs dependencies, imports a simulator,
or claims that structural validity is a complete cost measurement.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
from typing import Any


PROTOCOL_REL = "cost/protocol/r07_agent_cost_protocol_v2_2.json"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_SNAPSHOT_BYTES = 32 * 1024 * 1024
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
REQUIRED_TIME_FIELDS = (
    "session_wall_seconds", "active_development_seconds", "install_seconds",
    "test_seconds", "debug_seconds", "waiting_seconds", "human_assistance_seconds",
)
REQUIRED_USAGE_FIELDS = (
    "input_tokens", "output_tokens", "cached_input_tokens", "input_includes_cached",
)
REQUIRED_MONEY_FIELDS = (
    "amount", "currency", "billing_source_path", "billing_source_sha256",
)


def reject_constant(value: str):
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_load(path: Path):
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=reject_constant,
        object_pairs_hook=unique_object,
    )


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def safe_path(root: Path, value: str) -> Path:
    rel = PurePosixPath(value)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise ValueError(f"unsafe package-relative path: {value!r}")
    target = (root / Path(*rel.parts)).resolve()
    if target != root.resolve() and root.resolve() not in target.parents:
        raise ValueError(f"path escapes package root: {value!r}")
    return target


def classify_path(path: str) -> str:
    """Classify benchmark Python before the broad ``asset/`` data rule."""
    normalized = path.replace("\\", "/")
    low = normalized.lower()
    name = PurePosixPath(normalized).name
    if (normalized.startswith(("tests/", "test/"))
            or name.startswith("test_") and name.endswith(".py")
            or name.endswith("_test.py")):
        return "tests"
    if (normalized.startswith(("docs/", "doc/"))
            or low.endswith((".md", ".rst", ".adoc"))):
        return "docs"
    if normalized.startswith("generated/") or "/generated/" in normalized:
        return "generated"
    if normalized.startswith(("vendor/", "third_party/")) or "/vendor/" in normalized:
        return "vendor"
    if normalized.startswith(("bench_deploy/", "asset/benchmarks/")) and low.endswith(".py"):
        return "benchmark"
    if normalized.startswith("task_env/") and low.endswith(".py"):
        return "Core"
    if normalized.startswith(("geophys/", "provider/")) and low.endswith(".py"):
        return "provider"
    if (normalized.startswith(("data/", "assets/", "asset/"))
            or low.endswith((".json", ".yaml", ".yml", ".csv", ".h5", ".png",
                             ".jpg", ".jpeg", ".stl", ".obj", ".msh", ".usd",
                             ".usda", ".xml", ".bddl"))):
        return "data"
    return "other"


def _git(repo: Path, *args: str, timeout: float = 20.0) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if proc.returncode:
        raise ValueError(
            f"git {' '.join(args)} failed ({proc.returncode}): "
            f"{proc.stderr.decode('utf-8', 'replace')[:500]}"
        )
    return proc.stdout.decode("utf-8", "strict").strip()


def _git_blob(repo: Path, revision_path: str) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "blob", revision_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30.0,
        check=False,
    )
    if proc.returncode:
        raise ValueError("verified inherited ledger Git blob is unavailable")
    return proc.stdout


def _validate_commit(repo: Path, value: Any, field: str) -> str:
    if not isinstance(value, str) or not HEX40.fullmatch(value):
        raise ValueError(f"{field} must be a full lowercase Git SHA-1")
    resolved = _git(repo, "rev-parse", "--verify", f"{value}^{{commit}}")
    if resolved != value:
        raise ValueError(f"{field} does not resolve to the exact commit")
    return value


def _extract_archive(repo: Path, commit: str, destination: Path) -> int:
    proc = subprocess.run(
        ["git", "-C", str(repo), "archive", "--format=tar", commit, *ARCHIVE_PATHS],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=45.0,
        check=False,
    )
    if proc.returncode:
        raise ValueError(f"git archive failed: {proc.stderr.decode('utf-8', 'replace')[:500]}")
    destination.mkdir(parents=True, exist_ok=False)
    total = 0
    archive = tarfile.open(fileobj=io.BytesIO(proc.stdout), mode="r:")
    for member in archive.getmembers():
        rel = PurePosixPath(member.name)
        if rel.is_absolute() or ".." in rel.parts or member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
            raise ValueError(f"unsafe Git archive member: {member.name!r}")
        target = destination.joinpath(*rel.parts)
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        total += member.size
        if total > MAX_SNAPSHOT_BYTES:
            raise ValueError("paired cost source snapshots exceed the 32 MiB derived-source cap")
        target.parent.mkdir(parents=True, exist_ok=True)
        body = archive.extractfile(member)
        if body is None:
            raise ValueError(f"Git archive file has no payload: {member.name}")
        data = body.read(member.size + 1)
        if len(data) != member.size:
            raise ValueError(f"Git archive size mismatch: {member.name}")
        target.write_bytes(data)
    return total


def _unknown_field(record: dict, field: str) -> bool:
    value = record.get(field)
    if value is not None:
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)) and value < 0:
            raise ValueError(f"{field} cannot be negative")
        return False
    reason = record.get(field + "_reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError(f"{field}=null requires a specific reason")
    return True


def _validate_field_type(group: str, field: str, value: Any) -> None:
    """Reject malformed present values instead of treating them as evidence."""
    if value is None:
        return
    if group == "time" or group == "usage":
        if field == "input_includes_cached":
            if type(value) is not bool:
                raise ValueError(f"{group}.{field} must be boolean or null")
        elif type(value) is not int or value < 0:
            raise ValueError(f"{group}.{field} must be a nonnegative integer or null")
        return
    if group == "money":
        if field == "amount":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ValueError("money.amount must be a nonnegative number or null")
        elif field == "currency":
            if type(value) is not str or not value.strip():
                raise ValueError("money.currency must be a nonempty string or null")
        elif field == "billing_source_path":
            if type(value) is not str or not value.strip():
                raise ValueError("money.billing_source_path must be a nonempty string or null")
        elif field == "billing_source_sha256":
            if type(value) is not str or not HEX64.fullmatch(value):
                raise ValueError("money.billing_source_sha256 must be a lowercase SHA-256 or null")


def _validate_unknown_fields(record: dict, fields: tuple[str, ...], label: str) -> bool:
    if not isinstance(record, dict):
        raise ValueError(f"{label} must be an object")
    missing = [field for field in fields if field not in record]
    if missing:
        raise ValueError(f"{label} is missing required fields: {', '.join(missing)}")
    return any(_unknown_field(record, field) for field in fields)


_INHERITED_COST_FIELDS = frozenset({"active_seconds", "tokens", "amount"})
_INHERITED_ROW_FIELDS = frozenset({
    "aggregation_id", "source_status", "upgraded", "cost_fields", "unknown_reasons",
})


def _validate_inherited_costs(root: Path, repo: Path, rows: Any) -> bool:
    """Validate only the fixed v2.2 inherited ledger fields and provenance."""
    if not isinstance(rows, list) or not rows:
        raise ValueError("inherited cost ledger requires explicit rows")
    unknown = False
    aggregation_ids = set()
    for index, row in enumerate(rows):
        label = f"inherited_costs[{index}]"
        if not isinstance(row, dict):
            raise ValueError(f"{label} must be an object")
        if set(row) not in (_INHERITED_ROW_FIELDS, _INHERITED_ROW_FIELDS | {"source_evidence"}):
            raise ValueError(f"{label} field set is invalid")
        aggregation_id = row.get("aggregation_id")
        if type(aggregation_id) is not str or not aggregation_id.strip() or aggregation_id in aggregation_ids:
            raise ValueError("inherited aggregation IDs must be unique nonempty tokens")
        aggregation_ids.add(aggregation_id)
        status = row.get("source_status")
        if status not in {"verified", "unverified", "INVALID"}:
            raise ValueError(f"{label}.source_status is invalid")
        if type(row.get("upgraded")) is not bool:
            raise ValueError(f"{label}.upgraded must be boolean")
        if status == "INVALID" and row["upgraded"] is not False:
            raise ValueError("historical INVALID evidence cannot be upgraded")
        values, reasons = row.get("cost_fields"), row.get("unknown_reasons")
        if not isinstance(values, dict) or set(values) != _INHERITED_COST_FIELDS:
            raise ValueError(f"{label}.cost_fields must contain exactly {sorted(_INHERITED_COST_FIELDS)}")
        if not isinstance(reasons, dict):
            raise ValueError(f"{label}.unknown_reasons must be an object")
        null_fields = {field for field, value in values.items() if value is None}
        missing_reasons = null_fields - set(reasons)
        if missing_reasons:
            field = sorted(missing_reasons)[0]
            raise ValueError(f"inherited {aggregation_id}.{field}=null requires a reason")
        if set(reasons) != null_fields:
            raise ValueError(f"{label}.unknown_reasons contains reasons for non-null cost fields")
        for field, value in values.items():
            if value is None:
                reason = reasons.get(field)
                if type(reason) is not str or not reason.strip():
                    raise ValueError(f"inherited {aggregation_id}.{field}=null requires a reason")
                unknown = True
            elif field == "tokens":
                if type(value) is not int or value < 0:
                    raise ValueError(f"inherited {aggregation_id}.tokens must be a nonnegative integer")
            elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"inherited {aggregation_id}.{field} must be a finite nonnegative number")
        source_evidence = row.get("source_evidence")
        if status == "verified":
            if not isinstance(source_evidence, dict) or set(source_evidence) != {"commit", "path", "sha256"}:
                raise ValueError(f"verified inherited ledger {aggregation_id} requires source evidence")
            digest = source_evidence.get("sha256")
            if type(digest) is not str or not HEX64.fullmatch(digest):
                raise ValueError(f"verified inherited ledger {aggregation_id} has an invalid source digest")
            commit = _validate_commit(repo, source_evidence.get("commit"), f"{label}.source_evidence.commit")
            rel = PurePosixPath(source_evidence.get("path", ""))
            if rel.is_absolute() or ".." in rel.parts or not rel.parts or "\\" in str(rel):
                raise ValueError(f"verified inherited ledger {aggregation_id} has an unsafe Git path")
            source_bytes = _git_blob(repo, f"{commit}:{rel.as_posix()}")
            if sha256_bytes(source_bytes) != digest:
                raise ValueError(f"verified inherited ledger {aggregation_id} does not match its Git blob")
            ledger = json.loads(source_bytes.decode("utf-8"), parse_constant=reject_constant, object_pairs_hook=unique_object)
            if (not isinstance(ledger, dict)
                    or set(ledger) != {"schema_version", "aggregation_id", "source_status", "cost_fields", "unknown_reasons"}
                    or ledger.get("schema_version") != "r07-inherited-cost-ledger-v1"
                    or ledger.get("aggregation_id") != aggregation_id
                    or ledger.get("source_status") != "verified"
                    or ledger.get("cost_fields") != values
                    or ledger.get("unknown_reasons") != reasons):
                raise ValueError(f"verified inherited ledger {aggregation_id} content differs from its bound Git blob")
        elif source_evidence is not None:
            raise ValueError(f"unverified inherited ledger {aggregation_id} cannot claim verified source evidence")
        if status in {"unverified", "INVALID"} and any(value is not None for value in values.values()):
            raise ValueError(f"{status} inherited ledger {aggregation_id} cannot contribute measured values")
    return unknown


def _load_prior_loc(prior_tool: Path, expected_sha256: str):
    if sha256_file(prior_tool) != expected_sha256:
        raise ValueError("prior cost LOC tool bytes differ from the session-bound SHA-256")
    spec = importlib.util.spec_from_file_location("r07_prior_cost_v2", prior_tool)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load the pinned prior cost LOC implementation")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "compute_loc_delta", None)):
        raise ValueError("prior tool does not expose compute_loc_delta")
    # The v2.2 protocol corrects only path classification; tokenize/AST
    # fingerprints, move/copy accounting and conservative ambiguity rules are
    # reused from the exact hash-bound prior implementation.
    module.path_class = classify_path
    return module.compute_loc_delta


def validate_record(root: Path, repo: Path, input_path: Path, prior_tool: Path) -> dict:
    input_bytes = input_path.read_bytes()
    input_sha = sha256_bytes(input_bytes)
    input_data = json.loads(
        input_bytes.decode("utf-8"),
        parse_constant=reject_constant,
        object_pairs_hook=unique_object,
    )
    if not isinstance(input_data, dict) or input_data.get("schema_version") != "r07-cost-continuation-input-v2_2":
        raise ValueError("unsupported cost continuation input schema")
    protocol_ref = input_data.get("protocol")
    if not isinstance(protocol_ref, dict):
        raise ValueError("protocol reference is required")
    protocol_path = safe_path(root, protocol_ref.get("path"))
    protocol_bytes = protocol_path.read_bytes()
    protocol_hash = sha256_bytes(protocol_bytes)
    if protocol_hash != protocol_ref.get("sha256"):
        raise ValueError("protocol bytes do not match the session-bound hash")
    protocol = strict_load(protocol_path)
    if (protocol.get("schema_version") != "r07-agent-cost-protocol-continuation-v1"
            or protocol.get("protocol_id") != "geochora-r07-agent-cost"
            or protocol.get("version") != "2.2.0"
            or protocol.get("status") != "CANDIDATE_CONTINUATION_PENDING_SOL_TECHNICAL_REVIEW"):
        raise ValueError("protocol identity/review status is invalid")

    identity = input_data.get("identity")
    lineage = input_data.get("lineage")
    if not isinstance(identity, dict) or not isinstance(lineage, dict):
        raise ValueError("identity and lineage are required")
    start = _validate_commit(repo, lineage.get("session_start_commit"), "lineage.session_start_commit")
    final = _validate_commit(repo, lineage.get("final_commit"), "lineage.final_commit")
    historical = _validate_commit(repo, lineage.get("historical_measurement_reference_commit"), "lineage.historical_measurement_reference_commit")
    base = _validate_commit(repo, lineage.get("expected_common_ancestor"), "lineage.expected_common_ancestor")
    if _git(repo, "merge-base", start, final) != start:
        raise ValueError("current session start is not an ancestor of final commit")
    actual_common = _git(repo, "merge-base", historical, start)
    if actual_common != base:
        raise ValueError("historical reference common ancestor differs from recorded lineage")
    if _git(repo, "merge-base", historical, final) != base:
        raise ValueError("final tree changed the recorded historical branch ancestry")
    if identity.get("input_head") != start:
        raise ValueError("session input HEAD differs from lineage start commit")
    if identity.get("historical_reference_commit") != historical:
        raise ValueError("historical reference identity is not bound to lineage")
    if identity.get("agent_id") != "Luna2" or identity.get("agent_thread_id") != "01a186a5-7ac7-7c63-88f8-036b1f36d210":
        raise ValueError("agent session identity differs from the authorized R07c window")

    evidence = input_data.get("evidence")
    if not isinstance(evidence, dict):
        raise ValueError("evidence references are required")
    prior_values = {}
    for role in ("prior_protocol", "prior_result", "prior_tool", "prior_reader"):
        ref = evidence.get(role)
        if (not isinstance(ref, dict) or not isinstance(ref.get("path"), str)
                or not isinstance(ref.get("sha256"), str) or not HEX64.fullmatch(ref["sha256"])):
            raise ValueError(f"{role} evidence path/hash is required")
        file_path = safe_path(root, ref["path"])
        if sha256_file(file_path) != ref["sha256"]:
            raise ValueError(f"{role} evidence changed after it was recorded")
        prior_values[role] = strict_load(file_path) if role in {"prior_protocol", "prior_result"} else file_path
    prior_protocol = prior_values["prior_protocol"]
    if (not isinstance(prior_protocol, dict)
            or prior_protocol.get("schema") != "r07-agent-cost-protocol-v2.1"
            or prior_protocol.get("version") != "2.1.0"
            or prior_protocol.get("protocol_id") != "geochora-r07-agent-cost"):
        raise ValueError("prior v2 protocol identity is invalid")
    if protocol.get("extends", {}).get("prior_protocol_sha256") != evidence["prior_protocol"]["sha256"]:
        raise ValueError("continuation protocol does not bind the exact prior v2 protocol bytes")
    prior_result = prior_values["prior_result"]
    if not isinstance(prior_result, dict) or prior_result.get("status") != "INVALID":
        raise ValueError("prior v2.1 result must retain its original INVALID status")
    if prior_result.get("result_sha256") != input_data.get("prior_result_sha256"):
        raise ValueError("prior v2.1 result identity is not bound")
    if not any(issue.get("code") == "BASELINE_NOT_ANCESTOR_OF_EXECUTION"
               for issue in prior_result.get("issues", []) if isinstance(issue, dict)):
        raise ValueError("prior INVALID issue semantics are not preserved")

    inherited_rows = input_data.get("inherited_costs")
    inherited_unknown = _validate_inherited_costs(root, repo, inherited_rows)

    session_facts = input_data.get("session_facts")
    if not isinstance(session_facts, dict):
        raise ValueError("session_facts are required")
    unknown = inherited_unknown
    unknown |= _validate_unknown_fields(session_facts.get("time"), REQUIRED_TIME_FIELDS, "session_facts.time")
    unknown |= _validate_unknown_fields(session_facts.get("usage"), REQUIRED_USAGE_FIELDS, "session_facts.usage")
    unknown |= _validate_unknown_fields(session_facts.get("money"), REQUIRED_MONEY_FIELDS, "session_facts.money")
    for group, fields in (("time", REQUIRED_TIME_FIELDS), ("usage", REQUIRED_USAGE_FIELDS), ("money", REQUIRED_MONEY_FIELDS)):
        values = session_facts.get(group)
        if not isinstance(values, dict):
            raise ValueError(f"session_facts.{group} must be an object")
        for field in fields:
            _validate_field_type(group, field, values.get(field))
    for field in ("start_timestamp_utc", "end_timestamp_utc"):
        if not isinstance(session_facts.get(field), str) or not session_facts[field].endswith("Z"):
            raise ValueError(f"session_facts.{field} must be an explicit UTC timestamp ending Z")

    snapshot_root = safe_path(root, input_data.get("source_snapshot_root"))
    if snapshot_root.exists() and any(snapshot_root.iterdir()):
        raise ValueError("source snapshot destination already contains files")
    snapshot_root.mkdir(parents=True, exist_ok=True)
    start_root = snapshot_root / "session_start"
    final_root = snapshot_root / "final"
    start_bytes = _extract_archive(repo, start, start_root)
    final_bytes = _extract_archive(repo, final, final_root)
    if start_bytes + final_bytes > MAX_SNAPSHOT_BYTES:
        raise ValueError("paired cost source snapshots exceed the 32 MiB derived-source cap")
    compute_loc_delta = _load_prior_loc(
        prior_values["prior_tool"], evidence["prior_tool"]["sha256"]
    )
    loc_delta = compute_loc_delta(start_root, final_root)
    loc_delta["path_class_policy"] = "r07-cost-path-v2_2-asset-benchmark-python-before-data"
    loc_delta["snapshot_source_commits"] = {"session_start": start, "final": final}
    loc_delta["snapshot_bytes"] = {"session_start": start_bytes, "final": final_bytes}

    result = {
        "schema_version": "r07-cost-continuation-result-v2_2",
        "input_sha256": input_sha,
        "protocol": {"path": protocol_ref["path"], "sha256": protocol_hash, "version": "2.2.0"},
        "source_snapshot_root": input_data["source_snapshot_root"],
        "source_evidence": {
            role: {"path": evidence[role]["path"], "sha256": evidence[role]["sha256"]}
            for role in ("prior_protocol", "prior_result", "prior_tool", "prior_reader")
        },
        "identity": identity,
        "lineage": {
            "session_start_commit": start,
            "final_commit": final,
            "historical_measurement_reference_commit": historical,
            "actual_common_ancestor": actual_common,
            "historical_reference_is_current_session_ancestor": actual_common == historical,
            "branch_rewrite_performed": False,
        },
        "prior_v2_1": {
            "status": "INVALID",
            "result_sha256": prior_result["result_sha256"],
            "issue_codes": [row.get("code") for row in prior_result.get("issues", []) if isinstance(row, dict)],
            "upgraded": False,
        },
        "inherited_costs": inherited_rows,
        "session_facts": session_facts,
        "loc_delta": loc_delta,
        "measurement_status": "INCOMPLETE" if unknown else "STRUCTURALLY_VALID_MEASURED",
        "structural_status": "STRUCTURALLY_VALID_PARTIAL" if unknown else "STRUCTURALLY_VALID_MEASURED",
        "deployment_ready": False,
        "cumulative_r07_cost_claim_allowed": False,
        "reason": "Lineage and structure are checked; unknown inherited usage/time/billing remain null and prevent a complete cumulative measurement.",
        "tool": {"name": "cost_lineage_v2_2.py", "sha256": sha256_file(Path(__file__).resolve())},
    }
    unsigned = copy.deepcopy(result)
    result["result_sha256"] = sha256_bytes(canonical(unsigned))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("measure", choices=("measure",))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--prior-tool", required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        result = validate_record(
            root,
            args.repo.resolve(),
            safe_path(root, args.input),
            safe_path(root, args.prior_tool),
        )
        output = safe_path(root, args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps({"structural_status": result["structural_status"], "measurement_status": result["measurement_status"], "result_sha256": result["result_sha256"], "effective_added_loc": result["loc_delta"]["effective_added_loc"]}, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired, tarfile.TarError) as exc:
        print(json.dumps({"status": "INVALID", "reason": f"{type(exc).__name__}: {exc}"}, sort_keys=True))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
