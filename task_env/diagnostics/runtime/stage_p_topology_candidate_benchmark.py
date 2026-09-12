"""Measure fixed-runtime P0/P1/P12 full-physics control ticks.

This diagnostic owns no production runtime settings.  The candidate selector is
translated into the public task YAML overlay before construction, then the
same device-native TaskEnv lifecycle is timed for every case.
"""

from __future__ import annotations

import argparse
from importlib import metadata as importlib_metadata
import json
import platform
from pathlib import Path
import subprocess
import time
from typing import Any

from task_env.utils._device_stack import preload_device_stack


_BACKENDS = {
    "p0": "triton_active_slot_cholesky_f32_v1",
    "p1": "triton_active_slot_topology_child_schur_f32_v1",
    "p12": "triton_active_slot_topology_child_schur_root6x6_f32_v1",
}


def _package_version(*names: str) -> str | None:
    for name in names:
        try:
            return str(importlib_metadata.version(name))
        except importlib_metadata.PackageNotFoundError:
            continue
    return None


def _git_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def _gpu_info() -> dict[str, str | None]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
    except (OSError, subprocess.SubprocessError):
        return {"name": None, "driver": None, "memory_total": None}
    fields = [item.strip() for item in result.stdout.splitlines()[0].split(",")]
    fields.extend([None] * (3 - len(fields)))
    return {"name": fields[0], "driver": fields[1], "memory_total": fields[2]}


def _candidate_config(candidate: str) -> dict[str, Any]:
    return {
        "base_seed": 73,
        "runtime": {
            "backend": "cuda",
            "prewarm": False,
            "batch_physics_layout": "static_template",
            "static_template": {
                "profile": "articulated_fused_ground_contact_v1",
                "kinematics_backend": "taichi",
                "contact_precision": "f32",
                "cuda_graph": True,
                "contact": {
                    "response_backend": "active_slot_cholesky_f32_v1",
                    "fixed_topology_child_schur": candidate in {"p1", "p12"},
                    "root_factor_6x6": candidate == "p12",
                },
            },
        },
    }


def _measure_case(
    *, candidate: str, batch: int, seed: int, warmup: int, steps: int
) -> dict[str, Any]:
    import torch

    from task_env.vectorization.factory import make_framework_parallel_spec

    torch.manual_seed(int(seed))
    spec = make_framework_parallel_spec(
        uid="go2-walk-v1",
        num_env=int(batch),
        env_config=_candidate_config(candidate),
        backend="cuda",
        execution="local",
    )
    try:
        spec.reset(seed=int(seed))
        device = torch.device("cuda:0")
        action = torch.zeros((int(batch), 12), dtype=torch.float32, device=device)
        for _ in range(int(warmup)):
            spec.step_device(action)
        torch.cuda.synchronize(device)
        samples_ms: list[float] = []
        finite = True
        for _ in range(int(steps)):
            started = time.perf_counter()
            transition = spec.step_device(action)
            torch.cuda.synchronize(device)
            samples_ms.append((time.perf_counter() - started) * 1000.0)
            finite = finite and bool(
                torch.isfinite(transition.reward).all().item()
                and torch.isfinite(transition.observation).all().item()
            )
        ordered = sorted(samples_ms)
        p50 = ordered[(len(ordered) - 1) * 50 // 100]
        p95 = ordered[(len(ordered) - 1) * 95 // 100]
        summary = spec.resource_summary()
        expected = _BACKENDS[candidate]
        return {
            "candidate": candidate,
            "batch": int(batch),
            "seed": int(seed),
            "warmup_steps": int(warmup),
            "steady_state_steps": int(steps),
            "finite": bool(finite),
            "control_tick_ms": {
                "p50": float(p50),
                "p95": float(p95),
                "mean": float(sum(samples_ms) / len(samples_ms)),
            },
            "control_hz_p50": float(1000.0 / p50),
            "backend_expected": expected,
            "backend_selected": summary.get("contact_response_backend_selected"),
            "backend_effective": summary.get("contact_response_backend_effective"),
            "topology_child_schur": summary.get("topology_child_schur"),
            "cuda_graph": summary.get("cuda_graph"),
            "resource_summary_digest": summary.get("template_digest"),
        }
    finally:
        spec.close()
        torch.cuda.empty_cache()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", choices=tuple(_BACKENDS), required=True)
    parser.add_argument("--num-envs", type=int, nargs="+", required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=(1954,))
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--steps", type=int, default=180)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="JSON report path under temp_outputs or another ignored directory",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if any(int(value) < 1 for value in args.num_envs + args.seeds):
        raise SystemExit("num-envs and seeds must be positive")
    if int(args.warmup) < 0 or int(args.steps) < 1:
        raise SystemExit("warmup must be non-negative and steps must be positive")
    preload_device_stack(request_triton=True)
    import torch

    report = {
        "schema": "task-env-stage-p-topology-candidate-benchmark-v1",
        "commit": _git_sha(),
        "candidate": args.candidate,
        "yaml_summary": _candidate_config(args.candidate),
        "environment": {
            "python": platform.python_version(),
            "torch": str(torch.__version__),
            "torch_cuda": str(torch.version.cuda),
            "triton": _package_version("triton", "triton-windows"),
            "rsl_rl": _package_version("rsl-rl-lib"),
            "gpu": _gpu_info(),
        },
        "measurement_policy": {
            "warmup_steps": int(args.warmup),
            "steady_state_steps": int(args.steps),
            "timing": "synchronized_cuda_wall_clock_per_device_native_control_tick",
            "render": False,
        },
        "cases": [],
    }
    for batch in args.num_envs:
        for seed in args.seeds:
            report["cases"].append(
                _measure_case(
                    candidate=args.candidate,
                    batch=int(batch),
                    seed=int(seed),
                    warmup=int(args.warmup),
                    steps=int(args.steps),
                )
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
