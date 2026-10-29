#!/usr/bin/env python3
"""Independent stdlib-only reader for R07 cost-lineage continuation v2.2."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


HEX64 = re.compile(r"^[0-9a-f]{64}$")


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
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant, object_pairs_hook=_unique_object)


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _resolve(root: Path, value: str) -> Path:
    rel = PurePosixPath(value)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise ValueError(f"unsafe package-relative path: {value!r}")
    path = (root / Path(*rel.parts)).resolve()
    if root.resolve() not in path.parents and path != root.resolve():
        raise ValueError(f"path escapes package root: {value!r}")
    return path


def _tree_hashes(root: Path) -> dict[str, str]:
    if not root.is_dir():
        raise ValueError(f"source snapshot is missing: {root}")
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"source snapshot symlink is forbidden: {path}")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = _sha_file(path)
    return result


def read_result(root: Path, result_path: Path) -> dict:
    result = _load(result_path)
    if not isinstance(result, dict) or result.get("schema_version") != "r07-cost-continuation-result-v2_2":
        raise ValueError("unsupported continuation result schema")
    claimed = result.get("result_sha256")
    unsigned = dict(result)
    unsigned.pop("result_sha256", None)
    if not isinstance(claimed, str) or not HEX64.fullmatch(claimed) or _sha(_canonical(unsigned)) != claimed:
        raise ValueError("continuation result self-hash mismatch")
    if result.get("deployment_ready") is not False or result.get("cumulative_r07_cost_claim_allowed") is not False:
        raise ValueError("continuation result cannot grant deployment or cumulative-cost approval")
    if result.get("structural_status") not in {"STRUCTURALLY_VALID_PARTIAL", "STRUCTURALLY_VALID_MEASURED"}:
        raise ValueError("unsupported structural status")
    if result.get("measurement_status") not in {"INCOMPLETE", "STRUCTURALLY_VALID_MEASURED"}:
        raise ValueError("unsupported measurement status")
    prior = result.get("prior_v2_1")
    if not isinstance(prior, dict) or prior.get("status") != "INVALID" or prior.get("upgraded") is not False:
        raise ValueError("historical v2.1 result was upgraded or lost")
    if "BASELINE_NOT_ANCESTOR_OF_EXECUTION" not in prior.get("issue_codes", []):
        raise ValueError("original v2.1 failure attribution is missing")
    if result.get("structural_status") == "STRUCTURALLY_VALID_PARTIAL" and result.get("measurement_status") != "INCOMPLETE":
        raise ValueError("partial lineage cannot claim a complete measurement")
    protocol = result.get("protocol")
    if not isinstance(protocol, dict) or protocol.get("version") != "2.2.0":
        raise ValueError("result does not bind protocol v2.2")
    protocol_path = _resolve(root, protocol.get("path"))
    protocol_bytes = protocol_path.read_bytes()
    if _sha(protocol_bytes) != protocol.get("sha256"):
        raise ValueError("protocol bytes changed after the result was created")
    protocol_value = _load(protocol_path)
    if protocol_value.get("status") != "CANDIDATE_CONTINUATION_PENDING_SOL_TECHNICAL_REVIEW":
        raise ValueError("protocol review gate is not pending Sol")

    evidence = result.get("source_evidence")
    if not isinstance(evidence, dict) or set(evidence) != {"prior_protocol", "prior_result", "prior_tool", "prior_reader"}:
        raise ValueError("prior evidence references are incomplete")
    prior_paths = {}
    for role in ("prior_protocol", "prior_result", "prior_tool", "prior_reader"):
        ref = evidence[role]
        if (not isinstance(ref, dict) or not isinstance(ref.get("path"), str)
                or not isinstance(ref.get("sha256"), str) or not HEX64.fullmatch(ref["sha256"])):
            raise ValueError(f"{role} path/hash reference is malformed")
        prior_path = _resolve(root, ref["path"])
        if _sha_file(prior_path) != ref["sha256"]:
            raise ValueError(f"{role} evidence bytes changed")
        prior_paths[role] = prior_path

    prior_protocol = _load(prior_paths["prior_protocol"])
    if (prior_protocol.get("protocol_id") != "geochora-r07-agent-cost"
            or prior_protocol.get("version") != "2.1.0"
            or prior_protocol.get("schema") != "r07-agent-cost-protocol-v2.1"):
        raise ValueError("bound prior protocol identity is not v2.1")
    if protocol_value.get("extends", {}).get("prior_protocol_sha256") != evidence["prior_protocol"]["sha256"]:
        raise ValueError("continuation protocol does not bind the exact prior v2.1 protocol")

    prior_result_path = prior_paths["prior_result"]
    prior_result_bytes = prior_result_path.read_bytes()
    legacy = _load(prior_result_path)
    if legacy.get("status") != "INVALID" or legacy.get("result_sha256") != prior["result_sha256"]:
        raise ValueError("prior result was not preserved with its original INVALID status")
    if not any(isinstance(row, dict) and row.get("code") == "BASELINE_NOT_ANCESTOR_OF_EXECUTION" for row in legacy.get("issues", [])):
        raise ValueError("prior result issue attribution changed")

    snapshots = result.get("source_snapshot_root")
    if not isinstance(snapshots, str):
        raise ValueError("source snapshot root is missing")
    snapshot_root = _resolve(root, snapshots)
    for side, key in (("session_start", "baseline_files_sha256"), ("final", "final_files_sha256")):
        expected = result.get("loc_delta", {}).get(key)
        actual = _tree_hashes(snapshot_root / side)
        if not isinstance(expected, dict) or actual != expected:
            raise ValueError(f"{side} source snapshot bytes differ from the LOC ledger")
    if result.get("loc_delta", {}).get("path_class_policy") != "r07-cost-path-v2_2-asset-benchmark-python-before-data":
        raise ValueError("LOC classification policy is not the reviewed v2.2 ordering")

    lineage = result.get("lineage")
    if not isinstance(lineage, dict) or lineage.get("branch_rewrite_performed") is not False:
        raise ValueError("lineage rewrite status is missing or unsafe")
    return {
        "schema_version": "r07-cost-lineage-reader-result-v1",
        "reader_status": "VERIFIED_STRUCTURAL_PARTIAL" if result["structural_status"] == "STRUCTURALLY_VALID_PARTIAL" else "VERIFIED_STRUCTURAL_ONLY",
        "measurement_status": result["measurement_status"],
        "prior_v2_1_status": "INVALID_PRESERVED",
        "result_sha256": claimed,
        "source_files_checked": sum(len(result["loc_delta"][key]) for key in ("baseline_files_sha256", "final_files_sha256")),
        "cumulative_r07_cost_claim_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        value = read_result(root, _resolve(root, args.result))
        print(json.dumps(value, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema_version": "r07-cost-lineage-reader-result-v1", "reader_status": "REJECTED", "reason": f"{type(exc).__name__}: {exc}"}, sort_keys=True))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
