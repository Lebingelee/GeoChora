"""Stage 18 public device bridge baseline/after benchmark.

The outer process runs the same short benchmark in two source trees while
keeping backend, batch, seed and warmup/steady-state settings identical.
"""

from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
from typing import Any

import numpy as np


_BRIDGE_STATE_FIELDS = (
    "qpos",
    "qvel",
    "qacc",
    "ctrl",
    "act",
    "body_xpos",
    "body_xquat",
    "site_xpos",
    "site_xquat",
)


def _single_run(args: argparse.Namespace) -> None:
    import torch

    import task_env.tasks  # noqa: F401
    from task_env.vectorization.factory import make_framework_parallel_spec

    factory_kwargs = {
        "uid": str(args.task_uid),
        "num_env": int(args.num_envs),
        "backend": str(args.backend),
        "env_config": {
                "base_seed": int(args.seed),
                "runtime": {
                    "backend": str(args.backend),
                    "prewarm": False,
                    "batch_physics_layout": "static_template",
                    "static_template": {
                        "profile": "articulated_fused_ground_contact_v1",
                        "kinematics_backend": "torch",
                        "contact_precision": "f64",
                        "cuda_graph": False,
                    },
                    "enable_ground_contact": True,
                    "enable_domain_boundary_contact": False,
                },
            },
    }
    if "execution" in inspect.signature(make_framework_parallel_spec).parameters:
        factory_kwargs.update({"execution": "local", "transfer_mode": "device"})
    spec = make_framework_parallel_spec(**factory_kwargs)
    try:
        plan_object = getattr(spec, "device_field_plan", None)
        plan = (
            plan_object.as_dict()
            if hasattr(plan_object, "as_dict")
            else {"available": True, "execution": "baseline_unknown", "transfer_mode": "device"}
        )
        if not bool(plan.get("available", False)):
            raise RuntimeError(f"device benchmark capability unavailable: {plan}")
        spec.reset(seed=int(args.seed))
        action = torch.zeros(
            (int(args.num_envs), int(spec.single_action_space.shape[0])),
            dtype=torch.float32,
            device=torch.device("cuda:0" if args.backend == "cuda" else "cpu"),
        )
        for _ in range(max(0, int(args.warmup))):
            spec.step_device(action)
        if args.backend == "cuda":
            torch.cuda.synchronize(action.device)
        samples: list[float] = []
        for _ in range(max(1, int(args.steps))):
            started = time.perf_counter()
            spec.step_device(action)
            if args.backend == "cuda":
                torch.cuda.synchronize(action.device)
            samples.append((time.perf_counter() - started) * 1000.0)

        runtime_reader = getattr(spec.runtime, "read_device_state", None)
        runtime_stepper = getattr(spec.runtime, "step_device", None)
        action_converter = getattr(spec.action_adapter, "convert_device_batch", None)
        if not all(callable(value) for value in (runtime_reader, runtime_stepper, action_converter)):
            raise RuntimeError("paired bridge benchmark requires explicit runtime read/step and action converter")

        def _control_after_reset():
            spec.reset(seed=int(args.seed))
            state = runtime_reader(_BRIDGE_STATE_FIELDS)
            return action_converter(action, state)

        for _ in range(max(0, int(args.warmup))):
            runtime_stepper(_control_after_reset())
        if args.backend == "cuda":
            torch.cuda.synchronize(action.device)
        physics_samples: list[float] = []
        bridge_samples: list[float] = []
        for _ in range(max(1, int(args.steps))):
            control = _control_after_reset()
            started = time.perf_counter()
            runtime_stepper(control)
            if args.backend == "cuda":
                torch.cuda.synchronize(action.device)
            physics_ms = (time.perf_counter() - started) * 1000.0
            control = _control_after_reset()
            started = time.perf_counter()
            spec.step_device(action)
            if args.backend == "cuda":
                torch.cuda.synchronize(action.device)
            public_ms = (time.perf_counter() - started) * 1000.0
            physics_samples.append(physics_ms)
            bridge_samples.append(max(0.0, public_ms - physics_ms))

        def _stats(values: list[float]) -> dict[str, Any]:
            return {
                "p50_ms": float(np.percentile(values, 50)),
                "p95_ms": float(np.percentile(values, 95)),
                "mean_ms": float(statistics.fmean(values)),
                "raw_ms": values,
            }

        result = {
            "git_commit": _git_value("rev-parse", "HEAD"),
            "num_envs": int(args.num_envs),
            "backend": str(args.backend),
            "warmup": int(args.warmup),
            "steps": int(args.steps),
            "p50_ms": float(np.percentile(samples, 50)),
            "p95_ms": float(np.percentile(samples, 95)),
            "mean_ms": float(statistics.fmean(samples)),
            "raw_ms": samples,
            "device_field_plan": plan,
            "paired": {
                "physics": _stats(physics_samples),
                "bridge": _stats(bridge_samples),
                "method": "public device transition minus paired direct runtime step; reset and control conversion outside timed spans",
            },
        }
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    finally:
        spec.close()


def _git_value(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], check=True, capture_output=True, text=True, timeout=5.0
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value or None


def _run_tree(script: Path, root: Path, args: argparse.Namespace) -> dict[str, Any]:
    env = dict(__import__("os").environ)
    env["PYTHONPATH"] = f"{root / 'GeoPhys' / 'src'}:{root}"
    env["GEOPHYS_DISABLE_TRITON"] = "1"
    command = [
        sys.executable,
        str(script),
        "--single-run",
        "--task-uid",
        str(args.task_uid),
        "--backend",
        str(args.backend),
        "--num-envs",
        str(args.num_envs),
        "--warmup",
        str(args.warmup),
        "--steps",
        str(args.steps),
        "--seed",
        str(args.seed),
    ]
    completed = subprocess.run(
        command,
        cwd=root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"bridge benchmark failed in {root}:\n{completed.stdout}\n{completed.stderr}"
        )
    lines = [line for line in completed.stdout.splitlines() if line.strip().startswith("{")]
    if not lines:
        raise RuntimeError(f"bridge benchmark produced no JSON for {root}: {completed.stdout}")
    return json.loads(lines[-1])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--single-run", action="store_true")
    parser.add_argument("--task-uid", default="go2-walk-v1")
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--num-envs", type=int, default=1)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--seed", type=int, default=1818)
    parser.add_argument("--baseline-root", type=Path)
    parser.add_argument("--output", type=Path, default=Path("temp_outputs/task_env/stage18_bridge_benchmark.json"))
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.single_run:
        _single_run(args)
        return
    if args.baseline_root is None:
        raise ValueError("outer benchmark requires --baseline-root")
    root = Path.cwd().resolve()
    script = Path(__file__).resolve()
    baseline = _run_tree(script, Path(args.baseline_root).resolve(), args)
    after = _run_tree(script, root, args)
    full_ratio = float(after["p50_ms"]) / max(float(baseline["p50_ms"]), 1.0e-9)
    baseline_bridge_p50 = float(baseline["paired"]["bridge"]["p50_ms"])
    baseline_bridge_p95 = float(baseline["paired"]["bridge"]["p95_ms"])
    bridge_ratio = (
        None
        if baseline_bridge_p50 <= 1.0e-6
        else float(after["paired"]["bridge"]["p50_ms"]) / baseline_bridge_p50
    )
    bridge_p95_ratio = (
        None
        if baseline_bridge_p95 <= 1.0e-6
        else float(after["paired"]["bridge"]["p95_ms"]) / baseline_bridge_p95
    )
    bridge_budget_p50_ratio = float(after["paired"]["bridge"]["p50_ms"]) / max(
        float(baseline["p50_ms"]), 1.0e-9
    )
    bridge_budget_p95_ratio = float(after["paired"]["bridge"]["p95_ms"]) / max(
        float(baseline["p95_ms"]), 1.0e-9
    )
    report = {
        "schema": "task-env-stage18-bridge-benchmark-v1",
        "status": (
            "passed"
            if bridge_budget_p50_ratio <= 0.05 and bridge_budget_p95_ratio <= 0.10
            else "failed_bridge_budget_gate"
        ),
        "method": "same shell session; paired direct runtime physics and public device transition; bridge budget is checked against baseline full-tick p50/p95 so solver implementation differences remain separate",
        "manifest": {
            "task_uid": str(args.task_uid),
            "backend": str(args.backend),
            "num_envs": int(args.num_envs),
            "warmup": int(args.warmup),
            "steps": int(args.steps),
            "seed": int(args.seed),
            "regression_limit": 1.05,
        },
        "baseline": baseline,
        "after": after,
        "full_tick_p50_ratio_after_over_baseline": full_ratio,
        "bridge_p50_ratio_after_over_baseline": bridge_ratio,
        "bridge_p95_ratio_after_over_baseline": bridge_p95_ratio,
        "bridge_budget_p50_ratio_of_baseline_full_tick": bridge_budget_p50_ratio,
        "bridge_budget_p95_ratio_of_baseline_full_tick": bridge_budget_p95_ratio,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    from task_env.utils.runtime_support import get_task_env_logger

    get_task_env_logger("simulation", module="task-env-stage18-bridge-benchmark").success(
        "Stage 18 bridge benchmark written",
        output=str(args.output),
        status=report["status"],
        p50_ratio=bridge_ratio,
    )


if __name__ == "__main__":
    main()
