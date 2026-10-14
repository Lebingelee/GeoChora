"""Read-only recorder integrity/profile audit; never runs physics or qualification."""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import resource
from time import perf_counter

from ....controllers.canonical.contracts import digest
from ....trajectory.canonical.execution import expand_snapshot
from ....trajectory.canonical.streaming import (
    _json_bytes, load_streaming, snapshot_digest, verify_payload_integrity,
)


def snapshot_benchmark(*, repeats=100, plan_rows=4000):
    """Bounded synthetic stress pattern; not a physical trajectory comparison."""
    fixture = Path(__file__).parent / "fixtures/execution_prefix_fixture.json.gz"
    episode = json.loads(gzip.decompress(fixture.read_bytes()))
    snapshot = copy.deepcopy(episode["boundaries"][0]["owners"])
    entry = snapshot["owners"]["coordinator"]["fields"]["_actions"]
    blob = copy.deepcopy(episode["blobs"][entry["value"]["sha256"]])
    row = blob["values"][0]
    blob["values"] = [list(row) for _ in range(plan_rows)]
    blob["shape"][0] = plan_rows
    key = digest(blob)
    entry["value"] = {"kind": "content-ref", "sha256": key}
    blobs = {key: blob}
    expanded = expand_snapshot(snapshot, blobs)
    expanded.pop("integrity_hash")
    expected = digest(expanded)
    started = perf_counter()
    for _ in range(repeats):
        expanded = expand_snapshot(snapshot, blobs)
        expanded.pop("integrity_hash")
        if digest(expanded) != expected:
            raise AssertionError("historical snapshot hash")
    historical_s = perf_counter() - started
    started = perf_counter()
    encoded = {key: _json_bytes(blob)}
    for _ in range(repeats):
        if snapshot_digest(snapshot, encoded) != expected:
            raise AssertionError("optimized snapshot hash")
    optimized_s = perf_counter() - started
    return {"scope": "synthetic repeated snapshot expansion/hash only",
            "repeats": repeats, "plan_rows": plan_rows, "hash_exact": True,
            "historical_s": historical_s, "optimized_s": optimized_s,
            "speedup": historical_s / optimized_s}


def audit(path, *, semantic=False, benchmark=False):
    result = {"schema": "p18-recording-io-audit-v1", "source_h5": str(path),
              "qualification": "NOT_RUN", "replay": "NOT_RUN"}
    result["integrity"] = verify_payload_integrity(path)
    if semantic:
        profile = {}
        episode = load_streaming(path, profile=profile)
        boundary = episode["boundaries"][-1]
        owners = expand_snapshot(boundary["owners"], episode["blobs"])
        result["semantic"] = {
            "status": "PASS", "profile": profile,
            "transitions": len(episode["transitions"]),
            "boundaries": len(episode["boundaries"]),
            "last_task_success": boundary["record"]["is_success"],
            "last_lifecycle_state": owners["owners"]["coordinator"]["fields"].get("lifecycle_state"),
            "full_expert_status": "NOT_ADJUDICATED"}
    if benchmark:
        result["snapshot_benchmark"] = snapshot_benchmark()
    result["peak_rss_KiB"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    hashed = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hashed.update(chunk)
    result["source_h5_sha256"] = hashed.hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--semantic", action="store_true")
    parser.add_argument("--snapshot-benchmark", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("no overwrite")
    result = audit(args.input, semantic=args.semantic, benchmark=args.snapshot_benchmark)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({key: result.get(key) for key in ("integrity", "snapshot_benchmark", "peak_rss_KiB")}, indent=2))


if __name__ == "__main__":
    main()
