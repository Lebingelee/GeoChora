"""Full-length deterministic canonical reconstruction for a frozen FULL H5."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .checkpoint_validation import initialized, one
from .replay_preparation import snapshot
from ....artifacts.contracts import CanonicalStateView
from ....trajectory.canonical.execution import expand_snapshot
from ....trajectory.canonical.streaming import load_streaming as load


def validate_full(path: Path, output: Path) -> dict:
    path, output = Path(path), Path(output)
    source_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    recorded = load(path)
    hz = round(1.0 / recorded["metadata"]["timebase"]["control_dt"])
    provider = recorded["metadata"]["execution"]["physics_provider"]
    source = recorded["recipe"].get("solution_version")
    if source != (
        "nutassembly-r5-v5-clearance-primary-readiness-"
        "alternative-8n-guarded-v2"
    ):
        raise ValueError("full guarded-authorization source required")
    value = initialized(recorded, hz)
    first_divergence = None
    checked = 0
    previous = CanonicalStateView.from_mapping(recorded["boundaries"][0]["record"]["state"])
    initial_expected = expand_snapshot(recorded["boundaries"][0]["owners"], recorded["blobs"])
    if snapshot(value, previous, provider) != initial_expected:
        first_divergence = {"boundary": 0, "phase": "initial_owner_state"}
    for index in range(len(recorded["transitions"])):
        if first_divergence is not None:
            break
        start = CanonicalStateView.from_mapping(recorded["boundaries"][index]["record"]["state"])
        if previous.to_mapping() != start.to_mapping():
            first_divergence = {"boundary": index, "phase": "recorded_start_state"}
            break
        try:
            previous, _feedback = one(value, recorded, index, provider)
            checked += 1
        except Exception as exc:
            first_divergence = {
                "boundary": index,
                "phase": "canonical_action_controller_or_owner_state",
                "error": f"{type(exc).__name__}: {exc}",
            }
            break
    final_owner = expand_snapshot(
        recorded["boundaries"][-1]["owners"], recorded["blobs"]
    )
    lifecycle = final_owner["owners"]["coordinator"]["fields"]["lifecycle_state"]["value"]
    expected_success = bool(recorded["boundaries"][-1]["record"]["is_success"])
    all_steps = checked == len(recorded["transitions"])
    final_owner_exact = snapshot(value, previous, provider) == final_owner if all_steps else False
    passed = bool(all_steps and first_divergence is None and final_owner_exact
                  and lifecycle.get("status") == "completed" and expected_success)
    result = {
        "schema": "p1.8-full-d0-canonical-reconstruction-v1",
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "provider": provider,
        "outer_rate_hz": hz,
        "source_execution_h5": str(path),
        "source_execution_h5_sha256": source_sha,
        "source_logical_hash": recorded["metadata"].get("logical_hash"),
        "transitions_expected": len(recorded["transitions"]),
        "transitions_reconstructed": checked,
        "boundaries_expected": len(recorded["boundaries"]),
        "full_solution_owner_state_exact": final_owner_exact,
        "final_lifecycle_status": lifecycle.get("status"),
        "final_task_success": expected_success,
        "first_divergence": first_divergence,
        "scope": "all boundaries and native control samples; no physics re-execution",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = validate_full(args.input, args.output)
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
