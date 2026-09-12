"""Aggregate three Stage A f64/f32 sessions into a performance decision."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any


SCHEMA = "task-env-stage-g-contact-precision-gate-v1"
STAGE_A_SCHEMA = "task-env-stage-a-runtime-profile-v1"
EXPECTED_BATCHES = {32, 1024, 4096}

MEAN_LIMIT_MS = 100.0
P95_LIMIT_MS = 110.0
MEAN_REGRESSION_LIMIT = 1.05
P95_REGRESSION_LIMIT = 1.10


def _validate(
    report: dict[str, object],
    path: Path,
    *,
    expected_precision: str,
) -> dict[int, dict[str, float]]:
    if report.get("schema") != STAGE_A_SCHEMA:
        raise ValueError(f"{path}: unsupported Stage A schema")
    if report.get("status") != "measured_idle_profile":
        raise ValueError(f"{path}: gate requires an idle Stage A profile")

    manifest = report["manifest"]
    if (
        manifest["backend"] != "cuda"
        or manifest["static_template_contact_precision"] != expected_precision
    ):
        raise ValueError(f"{path}: gate requires CUDA {expected_precision}")
    if manifest["warmup_steps"] < 20 or manifest["steady_state_steps"] < 180:
        raise ValueError(f"{path}: insufficient warmup or samples")
    snapshots = manifest["gpu_snapshots"]
    if (
        snapshots["external_compute_processes_before"]
        or snapshots["external_compute_processes_after"]
    ):
        raise ValueError(f"{path}: GPU was not idle")

    case_items = report["cases"]
    batches = [int(item["num_envs"]) for item in case_items]
    if len(batches) != 3 or len(set(batches)) != 3 or set(batches) != EXPECTED_BATCHES:
        raise ValueError(f"{path}: expected exactly B=32/1024/4096")
    cases = {int(item["num_envs"]): item for item in case_items}

    result: dict[int, dict[str, float]] = {}
    for batch, case in cases.items():
        summary = case["resource_summary"]
        expected_intermediate_dtype = (
            "float32" if expected_precision == "f32" else "float64"
        )
        if (
            summary["contact_precision_requested"] != expected_precision
            or summary["contact_precision_effective"] != expected_precision
        ):
            raise ValueError(f"{path}: B={batch} did not execute {expected_precision}")
        if (
            summary.get("contact_solve_intermediate_dtype")
            != expected_intermediate_dtype
        ):
            raise ValueError(
                f"{path}: B={batch} did not execute {expected_precision} with "
                f"{expected_intermediate_dtype} intermediate"
            )
        timing = case["full_device_transition"]
        if timing.get("status") != "measured":
            raise ValueError(f"{path}: B={batch} was not measured")
        if int(timing["samples"]) < 180:
            raise ValueError(f"{path}: B={batch} has insufficient samples")
        mean_ms = float(timing["wall_ms"]["mean"])
        p95_ms = float(timing["wall_ms"]["p95"])
        if (
            not math.isfinite(mean_ms)
            or not math.isfinite(p95_ms)
            or mean_ms <= 0.0
            or p95_ms <= 0.0
        ):
            raise ValueError(f"{path}: B={batch} has invalid timing")
        result[batch] = {"mean_ms": mean_ms, "p95_ms": p95_ms}
    return result


def _input(
    path: Path, metadata: dict[str, Any]
) -> dict[str, object]:
    payload = path.read_bytes()
    metadata["available"] = True
    metadata["sha256"] = sha256(payload).hexdigest()
    report = json.loads(payload)
    if not isinstance(report, dict):
        raise ValueError(f"{path}: Stage A report must be a JSON object")
    return report


def _limits() -> dict[str, float]:
    return {
        "b4096_mean_ms": MEAN_LIMIT_MS,
        "b4096_p95_ms": P95_LIMIT_MS,
        "mean_regression_ratio": MEAN_REGRESSION_LIMIT,
        "p95_regression_ratio": P95_REGRESSION_LIMIT,
    }


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggregate three Stage A contact-precision performance sessions."
    )
    parser.add_argument(
        "--baseline-inputs", type=Path, nargs=3, required=True
    )
    parser.add_argument(
        "--candidate-inputs", type=Path, nargs=3, required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _base_report(
    baseline_inputs: list[dict[str, Any]],
    candidate_inputs: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": "pending",
        "limits": _limits(),
        "inputs": {
            "baseline": baseline_inputs,
            "candidate": candidate_inputs,
        },
        "sessions": [],
        "errors": [],
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    baseline_metadata = [
        {"path": str(path), "available": False, "sha256": None}
        for path in args.baseline_inputs
    ]
    candidate_metadata = [
        {"path": str(path), "available": False, "sha256": None}
        for path in args.candidate_inputs
    ]
    report = _base_report(baseline_metadata, candidate_metadata)

    try:
        baseline_loaded = [
            _input(path, metadata)
            for path, metadata in zip(args.baseline_inputs, baseline_metadata)
        ]
        candidate_loaded = [
            _input(path, metadata)
            for path, metadata in zip(args.candidate_inputs, candidate_metadata)
        ]

        baseline_timings = [
            _validate(stage_a, path, expected_precision="f64")
            for path, stage_a in zip(args.baseline_inputs, baseline_loaded)
        ]
        candidate_timings = [
            _validate(stage_a, path, expected_precision="f32")
            for path, stage_a in zip(args.candidate_inputs, candidate_loaded)
        ]

        sessions: list[dict[str, Any]] = []
        for index in range(3):
            batches: dict[str, Any] = {}
            for batch in sorted(EXPECTED_BATCHES):
                baseline = baseline_timings[index][batch]
                candidate = candidate_timings[index][batch]
                mean_ratio = candidate["mean_ms"] / baseline["mean_ms"]
                p95_ratio = candidate["p95_ms"] / baseline["p95_ms"]
                if not math.isfinite(mean_ratio) or not math.isfinite(p95_ratio):
                    raise ValueError(
                        f"paired session {index + 1}: B={batch} has non-finite ratio"
                    )
                ratio_passed = (
                    mean_ratio <= MEAN_REGRESSION_LIMIT
                    and p95_ratio <= P95_REGRESSION_LIMIT
                )
                absolute_passed = (
                    batch != 4096
                    or (
                        candidate["mean_ms"] <= MEAN_LIMIT_MS
                        and candidate["p95_ms"] <= P95_LIMIT_MS
                    )
                )
                batches[str(batch)] = {
                    "baseline": baseline,
                    "candidate": candidate,
                    "ratios": {"mean": mean_ratio, "p95": p95_ratio},
                    "passed": ratio_passed and absolute_passed,
                }
            sessions.append(
                {
                    "session": index + 1,
                    "baseline_input": baseline_metadata[index],
                    "candidate_input": candidate_metadata[index],
                    "batches": batches,
                    "passed": all(item["passed"] for item in batches.values()),
                }
            )

        report["sessions"] = sessions
        passed = all(session["passed"] for session in sessions)
        report["status"] = "passed" if passed else "failed_performance_gate"
        _write_report(args.output, report)
        return 0 if passed else 1
    except Exception as exc:
        report["status"] = "failed_validation"
        report["sessions"] = []
        report["errors"] = [
            {"type": type(exc).__name__, "message": str(exc)}
        ]
        _write_report(args.output, report)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
