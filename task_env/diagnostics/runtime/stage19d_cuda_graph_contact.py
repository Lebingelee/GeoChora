"""Stage 19d Torch-FK ground-contact CUDA Graph parity and benchmark gate."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import gc
import json
import logging
from pathlib import Path
import time
from typing import Any

from task_env.utils._device_stack import preload_device_stack


# Triton must be imported before the factory dependency graph can initialize
# Taichi.  The accepted module identities are retained for artifact provenance.
DEVICE_STACK_PRELOAD = preload_device_stack()

import numpy as np
import torch
import tensordict  # noqa: F401  # import before Taichi initialization

from task_env.vectorization.factory import make_framework_parallel_spec


LOGGER = logging.getLogger(__name__)
REQUIRED_CONTACT_PGS_BACKEND = "triton_fused_axis_world_serial_v2"
CONTACT_PGS_BOOTSTRAP_POLICY = "triton_preloaded_before_taichi_required"


class ContactPgsBackendError(RuntimeError):
    """Raised when Stage 19d did not execute its required fused backend."""


def _validate_required_contact_pgs_backend(
    summary: Mapping[str, Any],
    *,
    point: str,
) -> dict[str, Any]:
    bootstrap = summary.get("contact_pgs_bootstrap")
    triton_version = summary.get("contact_pgs_triton_version")
    checks = {
        "bootstrap_schema": (
            isinstance(bootstrap, Mapping)
            and bootstrap.get("schema") == "task-env-device-stack-provenance-v1"
        ),
        "bootstrap_status": (
            isinstance(bootstrap, Mapping)
            and bootstrap.get("status") == "triton_preloaded_before_taichi"
        ),
        "triton_requested": (
            isinstance(bootstrap, Mapping)
            and bootstrap.get("triton_requested") is True
        ),
        "triton_loaded": (
            isinstance(bootstrap, Mapping)
            and bootstrap.get("triton_loaded") is True
        ),
        "taichi_not_loaded_first": (
            isinstance(bootstrap, Mapping)
            and bootstrap.get("taichi_loaded_before_triton") is False
        ),
        "bootstrap_error_absent": (
            isinstance(bootstrap, Mapping) and bootstrap.get("error") is None
        ),
        "triton_version": (
            isinstance(bootstrap, Mapping)
            and isinstance(triton_version, str)
            and bool(triton_version.strip())
            and bootstrap.get("triton_version") == triton_version
        ),
        "triton_module_id": (
            isinstance(bootstrap, Mapping)
            and isinstance(bootstrap.get("triton_module_id"), int)
            and int(bootstrap["triton_module_id"]) > 0
        ),
        "triton_language_module_id": (
            isinstance(bootstrap, Mapping)
            and isinstance(bootstrap.get("triton_language_module_id"), int)
            and int(bootstrap["triton_language_module_id"]) > 0
        ),
        "selected": (
            summary.get("contact_pgs_backend_selected")
            == REQUIRED_CONTACT_PGS_BACKEND
        ),
        "effective": (
            summary.get("contact_pgs_backend_effective")
            == REQUIRED_CONTACT_PGS_BACKEND
        ),
        "next": (
            summary.get("contact_pgs_backend_next") == REQUIRED_CONTACT_PGS_BACKEND
        ),
        "attempted": summary.get("contact_pgs_fused_attempted") is True,
        "qualified": summary.get("contact_pgs_fused_qualified") is True,
        "failed_closed": summary.get("contact_pgs_failed_closed") is False,
        "fallback_absent": summary.get("contact_pgs_fallback_reason") is None,
    }
    mismatches = [name for name, passed in checks.items() if not passed]
    validation = {
        "status": "passed" if not mismatches else "failed",
        "point": str(point),
        "required": REQUIRED_CONTACT_PGS_BACKEND,
        "checks": checks,
        "mismatches": mismatches,
    }
    if mismatches:
        raise ContactPgsBackendError(
            f"Stage 19d contact PGS backend validation failed at {point}: "
            f"{mismatches}"
        )
    return validation


def _build(
    batch: int,
    *,
    graph: bool,
    contact_precision: str = "f64",
):
    return make_framework_parallel_spec(
        uid="go2-walk-v1",
        num_env=int(batch),
        env_config={
            "base_seed": 73,
            "runtime": {
                "backend": "cuda",
                "prewarm": False,
                "batch_physics_layout": "static_template",
                "static_template": {
                    "profile": "articulated_fused_ground_contact_v1",
                    "kinematics_backend": "torch",
                    "contact_precision": str(contact_precision),
                    "cuda_graph": bool(graph),
                },
                "enable_ground_contact": True,
                "enable_domain_boundary_contact": False,
            },
        },
        backend="cuda",
    )


def _physics(spec):
    return spec.runtime._physics


def _step(spec) -> None:
    physics = _physics(spec)
    physics.step(physics.control_substeps)
    torch.cuda.synchronize()


def _step_capture_safe_eager(spec) -> None:
    """Advance the numerical oracle without entering Graph capture/replay."""

    physics = _physics(spec)
    physics._step_eager(physics.control_substeps)
    torch.cuda.synchronize()


def _max_abs(lhs, rhs) -> float:
    return float((lhs - rhs).abs().max().item())


def _parity_case(
    batch: int,
    steps: int,
    *,
    contact_precision: str = "f64",
) -> dict[str, object]:
    capture_safe_eager = _build(
        batch,
        graph=False,
        contact_precision=contact_precision,
    )
    graph = _build(batch, graph=True, contact_precision=contact_precision)
    try:
        capture_safe_eager.reset(seed=73)
        graph.reset(seed=73)
        # This is an internal numerical oracle: it selects the same fixed
        # Cholesky route as the Graph path, but executes the full tick eagerly.
        torch.cuda.synchronize()
        maxima = {
            name: 0.0
            for name in (
                "qpos",
                "qvel",
                "qacc",
                "contact_distance",
                "normal_lambda",
                "tangent_lambda",
            )
        }
        for _ in range(int(steps)):
            _step_capture_safe_eager(capture_safe_eager)
            _step(graph)
            eager_physics = _physics(capture_safe_eager)
            graph_physics = _physics(graph)
            fields = {
                "qpos": (eager_physics._qpos, graph_physics._qpos),
                "qvel": (eager_physics._qvel, graph_physics._qvel),
                "qacc": (eager_physics._qacc, graph_physics._qacc),
                "contact_distance": (
                    eager_physics._contact_distance,
                    graph_physics._contact_distance,
                ),
                "normal_lambda": (
                    eager_physics._contact_normal_lambda,
                    graph_physics._contact_normal_lambda,
                ),
                "tangent_lambda": (
                    eager_physics._contact_tangent_lambda,
                    graph_physics._contact_tangent_lambda,
                ),
            }
            for name, (lhs, rhs) in fields.items():
                maxima[name] = max(maxima[name], _max_abs(lhs, rhs))
        eager_summary = _physics(capture_safe_eager).resource_summary()
        eager_cuda_graph = eager_summary["cuda_graph"]
        if eager_cuda_graph["status"] != "armed":
            raise AssertionError(
                "capture-safe eager oracle did not remain armed without replay: "
                f"{eager_cuda_graph}"
            )
        summary = _physics(graph).resource_summary()
        backend_validation = {
            "initial_eager_oracle": _validate_required_contact_pgs_backend(
                eager_summary,
                point="initial_eager_oracle",
            ),
            "post_graph_replay": _validate_required_contact_pgs_backend(
                summary,
                point="post_graph_replay",
            ),
        }
        cuda_graph = summary["cuda_graph"]
        if cuda_graph["status"] != "ready" or cuda_graph["scope"] != "contact_full_v4":
            raise AssertionError(cuda_graph)
        graph.reset(seed=73)
        reset_summary = _physics(graph).resource_summary()["cuda_graph"]
        if reset_summary["status"] != "armed":
            raise AssertionError(f"contact Graph reset did not invalidate: {reset_summary}")
        _step(graph)
        recaptured_resource_summary = _physics(graph).resource_summary()
        recaptured_summary = recaptured_resource_summary["cuda_graph"]
        if recaptured_summary["status"] != "ready":
            raise AssertionError(f"contact Graph did not recapture: {recaptured_summary}")
        backend_validation["post_graph_recapture"] = (
            _validate_required_contact_pgs_backend(
                recaptured_resource_summary,
                point="post_graph_recapture",
            )
        )
        limits = {
            "qpos": 2.0e-7,
            "qvel": 2.0e-6,
            "qacc": 2.0e-5,
            "contact_distance": 2.0e-7,
            "normal_lambda": 2.0e-6,
            "tangent_lambda": 2.0e-6,
        }
        for name, limit in limits.items():
            if maxima[name] > limit:
                raise AssertionError(
                    f"Torch/contact CUDA Graph parity failed for B={batch}: {maxima}"
                )
        return {
            "batch": int(batch),
            "steps": int(steps),
            "static_template_contact_precision": str(contact_precision),
            "status": "passed",
            "max_abs": maxima,
            "eager_oracle": {
                "execution": "explicit_step_eager",
                "cuda_graph_status": eager_cuda_graph["status"],
                "control_substeps_per_tick": int(
                    _physics(capture_safe_eager).control_substeps
                ),
            },
            "contact_pgs_backend_validation": backend_validation,
            "reset_status": reset_summary["status"],
            "recapture_status": recaptured_summary["status"],
            "resource_summary": summary,
        }
    finally:
        capture_safe_eager.close()
        graph.close()


def _measure_runtime(
    batch: int,
    *,
    graph: bool,
    warmup: int,
    samples: int,
    contact_precision: str = "f64",
) -> dict[str, object]:
    spec = _build(batch, graph=graph, contact_precision=contact_precision)
    try:
        spec.reset(seed=73)
        for _ in range(int(warmup)):
            _step(spec)
        torch.cuda.synchronize()
        timings: list[float] = []
        for _ in range(int(samples)):
            start = time.perf_counter()
            _step(spec)
            timings.append((time.perf_counter() - start) * 1000.0)
        return {
            "static_template_contact_precision": str(contact_precision),
            "p50_ms": float(np.percentile(timings, 50)),
            "p95_ms": float(np.percentile(timings, 95)),
            "resource_summary": _physics(spec).resource_summary(),
        }
    finally:
        spec.close()
        del spec
        gc.collect()
        torch.cuda.synchronize()
        torch.cuda.empty_cache()


def _benchmark_case(
    batch: int,
    warmup: int,
    samples: int,
    *,
    contact_precision: str = "f64",
) -> dict[str, object]:
    # Measure the two modes in separate lifetimes.  A B=8192 parity pair would
    # retain two large state/workspace payloads and two CUDA Graph private pools,
    # which is not representative of the one-runtime PPO process.
    eager = _measure_runtime(
        batch,
        graph=False,
        warmup=warmup,
        samples=samples,
        contact_precision=contact_precision,
    )
    graph = _measure_runtime(
        batch,
        graph=True,
        warmup=warmup,
        samples=samples,
        contact_precision=contact_precision,
    )
    backend_validation = {
        "benchmark_eager": _validate_required_contact_pgs_backend(
            eager["resource_summary"],
            point="benchmark_eager",
        ),
        "benchmark_graph": _validate_required_contact_pgs_backend(
            graph["resource_summary"],
            point="benchmark_graph",
        ),
    }
    p50 = {
        "torch_contact_eager": eager["p50_ms"],
        "torch_contact_cuda_graph": graph["p50_ms"],
    }
    p95 = {
        "torch_contact_eager": eager["p95_ms"],
        "torch_contact_cuda_graph": graph["p95_ms"],
    }
    return {
        "batch": int(batch),
        "warmup": int(warmup),
        "samples": int(samples),
        "static_template_contact_precision": str(contact_precision),
        "status": "passed",
        "single_runtime_measurement": True,
        "contact_pgs_backend_validation": backend_validation,
        "p50_ms": p50,
        "p95_ms": p95,
        "ratio_graph_over_eager": {
            "p50_ms": p50["torch_contact_cuda_graph"] / p50["torch_contact_eager"],
            "p95_ms": p95["torch_contact_cuda_graph"] / p95["torch_contact_eager"],
        },
        "graph_resource_summary": graph["resource_summary"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, nargs="+", default=(1, 32))
    parser.add_argument("--steps", type=int, default=12)
    parser.add_argument(
        "--contact-precision",
        choices=("f64", "f32"),
        default="f64",
    )
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--skip-parity", action="store_true")
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--samples", type=int, default=8)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("temp_outputs/task_env/stage19d_cuda_graph_contact.json"),
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    if args.skip_parity and not args.benchmark:
        raise ValueError("--skip-parity requires --benchmark")
    report = {
        "schema": "task_env.stage19d_cuda_graph_contact.v1",
        "status": "passed",
        "manifest": {
            "batches": [int(batch) for batch in args.batch],
            "static_template_contact_precision": str(args.contact_precision),
            "parity_steps": int(args.steps),
            "skip_parity": bool(args.skip_parity),
            "benchmark": bool(args.benchmark),
            "warmup": int(args.warmup),
            "samples": int(args.samples),
            "single_runtime_measurement": True,
            "contact_pgs_bootstrap_policy": CONTACT_PGS_BOOTSTRAP_POLICY,
            "required_contact_pgs_backend": REQUIRED_CONTACT_PGS_BACKEND,
            "device_stack_preload": DEVICE_STACK_PRELOAD.to_dict(),
        },
        "parity": (
            []
            if args.skip_parity
            else [
                _parity_case(
                    int(batch),
                    int(args.steps),
                    contact_precision=str(args.contact_precision),
                )
                for batch in args.batch
            ]
        ),
        "benchmark": (
            [
                _benchmark_case(
                    int(batch),
                    int(args.warmup),
                    int(args.samples),
                    contact_precision=str(args.contact_precision),
                )
                for batch in args.batch
            ]
            if args.benchmark
            else []
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    LOGGER.info("Stage 19d Torch/contact CUDA Graph gate passed: %s", args.output)


if __name__ == "__main__":
    main()
