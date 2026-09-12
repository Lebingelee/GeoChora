"""Stage F: Torch/contact and Taichi/contact CUDA Graph lifecycle.

Both contact Graph routes are opt-in.  This diagnostic makes the lifecycle
contract explicit: fixed-shape capture, replay parity, reset
invalidation/recapture, and stable runtime boundary pointers.  Taichi FK stays
outside the Graph and is refreshed between complete Torch-core substep
replays.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import torch
import tensordict  # noqa: F401

from task_env.utils.runtime_support import get_task_env_logger
from task_env.diagnostics.runtime.stage19d_cuda_graph_contact import (
    _benchmark_case,
    _build as _build_torch_contact,
    _parity_case,
    _step,
)
from task_env.diagnostics.runtime.stage_b_torch_reference import _build as _build_reference


LOGGER = get_task_env_logger("simulation", module="task-env-stage-f-cuda-graph-lifecycle")
SCHEMA = "task-env-stage-f-cuda-graph-lifecycle-v2"


def _lifecycle_case(
    batch: int,
    steps: int,
    *,
    kinematics_backend: str = "torch",
) -> dict[str, Any]:
    backend = str(kinematics_backend)
    if backend == "torch":
        spec = _build_torch_contact(batch, graph=True)
        expected_scope = "contact_full_v4"
    elif backend == "taichi":
        spec = _build_reference(
            batch,
            backend="cuda",
            kinematics_backend="taichi",
            graph=True,
        )
        expected_scope = "contact_core_full_v5"
    else:
        raise ValueError(f"unsupported kinematics backend: {backend!r}")
    try:
        spec.reset(seed=73)
        physics = spec.runtime._physics
        after_reset = physics.resource_summary()["cuda_graph"]
        boundary_before = physics.runtime_boundary_snapshot()
        for _ in range(int(steps)):
            _step(spec)
        after_replay = physics.resource_summary()["cuda_graph"]
        boundary_after = physics.runtime_boundary_snapshot()
        pointer_stable = boundary_before["torch_tensor_pointers"] == boundary_after["torch_tensor_pointers"]
        device_stable = boundary_before["device"] == boundary_after["device"]
        stream_stable = boundary_before["stream_id"] == boundary_after["stream_id"]
        reset_status = after_replay["status"]
        spec.reset(seed=73)
        after_invalidation = physics.resource_summary()["cuda_graph"]
        _step(spec)
        after_recapture = physics.resource_summary()["cuda_graph"]
        passed = (
            after_reset["status"] == "armed"
            and reset_status == "ready"
            and after_invalidation["status"] == "armed"
            and after_recapture["status"] == "ready"
            and after_replay["scope"] == expected_scope
            and pointer_stable
            and device_stable
            and stream_stable
        )
        return {
            "batch": int(batch),
            "steps": int(steps),
            "kinematics_backend": backend,
            "status": "passed" if passed else "failed_lifecycle_gate",
            "after_reset": after_reset,
            "after_replay": after_replay,
            "after_invalidation": after_invalidation,
            "after_recapture": after_recapture,
            "runtime_boundary": {
                "pointer_stable": pointer_stable,
                "device_stable": device_stable,
                "stream_stable": stream_stable,
                "before": boundary_before,
                "after": boundary_after,
            },
        }
    finally:
        spec.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, nargs="+", default=(1024, 4096))
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path("temp_outputs/task_env/stage_f_cuda_graph_lifecycle.json"))
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if any(int(value) < 1 for value in args.batch):
        raise ValueError("--batch values must be positive")
    if int(args.steps) < 1 or int(args.samples) < 1 or int(args.warmup) < 0:
        raise ValueError("steps/samples must be positive and warmup must be non-negative")
    if not torch.cuda.is_available():
        raise RuntimeError("Stage F CUDA Graph experiment requires an available CUDA device")
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "passed",
        "manifest": {
            "batches": [int(value) for value in args.batch],
            "parity_steps": int(args.steps),
            "benchmark": bool(args.benchmark),
            "torch_contact_scope": "contact_full_v4",
            "taichi_contact_scope": "contact_core_full_v5",
            "taichi_contact_policy": (
                "one_complete_torch_core_substep_per_replay; eager_fk_between_replays"
            ),
            "taichi_contact_interop_ordering": "host_fenced_v1",
            "default_policy": "opt_in_only; no default PPO route change",
        },
        "lifecycle": [],
        "taichi_contact_lifecycle": [],
        "benchmark": [],
    }
    for batch in args.batch:
        lifecycle = _lifecycle_case(
            int(batch), int(args.steps), kinematics_backend="torch"
        )
        parity = _parity_case(int(batch), int(args.steps))
        report["lifecycle"].append({"lifecycle": lifecycle, "parity": parity})
        taichi_lifecycle = _lifecycle_case(
            int(batch), int(args.steps), kinematics_backend="taichi"
        )
        report["taichi_contact_lifecycle"].append(taichi_lifecycle)
        if (
            lifecycle["status"] != "passed"
            or parity["status"] != "passed"
            or taichi_lifecycle["status"] != "passed"
        ):
            report["status"] = "gated_failure"
    if args.benchmark:
        for batch in args.batch:
            benchmark = _benchmark_case(int(batch), int(args.warmup), int(args.samples))
            report["benchmark"].append(benchmark)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    LOGGER.success("Stage F CUDA Graph lifecycle report written", output=str(args.output), status=report["status"])


if __name__ == "__main__":
    main()
