"""Stage B: unified Torch reference versus the Taichi-FK hybrid route.

This is an opt-in experiment.  Both routes keep the current dense dynamics,
ground contact row order, ERP/bias, integration step and task semantics.  The
only requested difference is the FK/geometry owner: Torch or Taichi.  The
report contains short-run parity and, when requested, steady-state direct
physics/public device timing for each fixed batch.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
import torch
import tensordict  # noqa: F401  # import before Taichi initialization

from task_env.utils.runtime_support import get_task_env_logger
from task_env.diagnostics.runtime.stage17_performance_profile import _measure, _synchronise
from task_env.vectorization.factory import make_framework_parallel_spec


LOGGER = get_task_env_logger("simulation", module="task-env-stage-b-torch-reference")
SCHEMA = "task-env-stage-b-torch-reference-v1"
_PHYSICS_FIELDS = (
    "qpos",
    "qvel",
    "qacc",
    "contact_distance",
    "contact_normal",
    "normal_lambda",
    "tangent_lambda",
)


def _build(batch: int, *, backend: str, kinematics_backend: str, graph: bool = False):
    return make_framework_parallel_spec(
        uid="go2-walk-v1",
        num_env=int(batch),
        env_config={
            "base_seed": 73,
            "runtime": {
                "backend": str(backend),
                "prewarm": False,
                "batch_physics_layout": "static_template",
                "static_template": {
                    "profile": "articulated_fused_ground_contact_v1",
                    "kinematics_backend": str(kinematics_backend),
                    "contact_precision": "f64",
                    "cuda_graph": bool(graph),
                },
                "enable_ground_contact": True,
                "enable_domain_boundary_contact": False,
            },
        },
        backend=str(backend),
        execution="local",
        transfer_mode="device",
    )


def _physics(spec: object) -> object:
    return spec.runtime._physics


def _device(spec: object, backend: str) -> torch.device:
    return torch.device("cuda:0" if str(backend) == "cuda" else "cpu")


def _action(spec: object, backend: str) -> torch.Tensor:
    return torch.zeros(
        (int(spec.num_envs), int(spec.single_action_space.shape[0])),
        dtype=torch.float32,
        device=_device(spec, backend),
    )


def _private_physics_values(physics: object) -> dict[str, torch.Tensor]:
    values = {
        "qpos": physics._qpos,
        "qvel": physics._qvel,
        "qacc": physics._qacc,
        "contact_distance": physics._contact_distance,
        "contact_normal": physics._contact_normal,
        "normal_lambda": physics._contact_normal_lambda,
        "tangent_lambda": physics._contact_tangent_lambda,
    }
    return values


def _max_abs(lhs: torch.Tensor, rhs: torch.Tensor) -> float:
    return float((lhs - rhs).abs().max().item())


def _leaves(value: Any, prefix: str = "") -> dict[str, torch.Tensor]:
    if isinstance(value, Mapping):
        result: dict[str, torch.Tensor] = {}
        for name, child in value.items():
            result.update(_leaves(child, f"{prefix}/{name}"))
        return result
    if isinstance(value, torch.Tensor):
        return {prefix or "value": value}
    return {}


def _task_errors(torch_transition: object, taichi_transition: object) -> dict[str, Any]:
    torch_obs = _leaves(torch_transition.observation, "observation")
    taichi_obs = _leaves(taichi_transition.observation, "observation")
    observation_errors = {
        name: _max_abs(torch_obs[name], taichi_obs[name])
        for name in sorted(set(torch_obs) & set(taichi_obs))
        if torch_obs[name].dtype.is_floating_point
    }
    missing = sorted(set(torch_obs) ^ set(taichi_obs))
    reward_error = _max_abs(torch_transition.reward, taichi_transition.reward)
    terminated_equal = bool(torch.equal(torch_transition.terminated, taichi_transition.terminated))
    truncated_equal = bool(torch.equal(torch_transition.truncated, taichi_transition.truncated))
    return {
        "observation_max_abs": max(observation_errors.values(), default=0.0),
        "observation_by_field": observation_errors,
        "observation_leaf_mismatch": missing,
        "reward_max_abs": reward_error,
        "terminated_equal": terminated_equal,
        "truncated_equal": truncated_equal,
    }


def _parity_case(batch: int, *, backend: str, steps: int) -> dict[str, Any]:
    torch_spec = _build(batch, backend=backend, kinematics_backend="torch")
    taichi_spec = _build(batch, backend=backend, kinematics_backend="taichi")
    try:
        torch_spec.reset(seed=73)
        taichi_spec.reset(seed=73)
        _synchronise(_device(torch_spec, backend))
        torch_action = _action(torch_spec, backend)
        taichi_action = _action(taichi_spec, backend)
        torch_physics = _physics(torch_spec)
        taichi_physics = _physics(taichi_spec)
        maxima = {name: 0.0 for name in _PHYSICS_FIELDS}
        task_maxima = {
            "observation_max_abs": 0.0,
            "reward_max_abs": 0.0,
            "terminated_equal": True,
            "truncated_equal": True,
            "observation_leaf_mismatch": [],
        }
        per_step: list[dict[str, Any]] = []
        for step in range(int(steps)):
            torch_transition = torch_spec.step_device(torch_action)
            taichi_transition = taichi_spec.step_device(taichi_action)
            # Taichi external-ndarray launches and Torch launches share
            # storage but not necessarily the same runtime stream.  Pointer
            # equality alone is insufficient ordering evidence; this
            # diagnostic boundary must wait before reading either route.
            _synchronise(_device(torch_spec, backend))
            torch_values = _private_physics_values(torch_physics)
            taichi_values = _private_physics_values(taichi_physics)
            for name in _PHYSICS_FIELDS:
                maxima[name] = max(maxima[name], _max_abs(torch_values[name], taichi_values[name]))
            task_errors = _task_errors(torch_transition, taichi_transition)
            task_maxima["observation_max_abs"] = max(
                float(task_maxima["observation_max_abs"]),
                float(task_errors["observation_max_abs"]),
            )
            task_maxima["reward_max_abs"] = max(
                float(task_maxima["reward_max_abs"]),
                float(task_errors["reward_max_abs"]),
            )
            task_maxima["terminated_equal"] = bool(task_maxima["terminated_equal"] and task_errors["terminated_equal"])
            task_maxima["truncated_equal"] = bool(task_maxima["truncated_equal"] and task_errors["truncated_equal"])
            if task_errors["observation_leaf_mismatch"]:
                task_maxima["observation_leaf_mismatch"] = task_errors["observation_leaf_mismatch"]
            per_step.append({"step": int(step), "max_abs": dict(maxima), "task_max_abs": dict(task_maxima)})
        limits = {
            "qpos": 2.0e-5,
            "qvel": 2.0e-4,
            # CUDA f32 Taichi-FK/Torch-solver parity follows the existing
            # Stage 19d core envelope; qacc is more sensitive than qpos/qvel
            # even when the public state and contact impulses stay aligned.
            "qacc": 2.0e-2,
            "contact_distance": 2.0e-5,
            "contact_normal": 2.0e-5,
            "normal_lambda": 2.0e-4,
            "tangent_lambda": 2.0e-4,
        }
        status = all(maxima[name] <= limits[name] for name in _PHYSICS_FIELDS) and (
            float(task_maxima["observation_max_abs"]) <= 2.0e-4
            and float(task_maxima["reward_max_abs"]) <= 2.0e-4
            and bool(task_maxima["terminated_equal"])
            and bool(task_maxima["truncated_equal"])
            and not task_maxima["observation_leaf_mismatch"]
        )
        if not status:
            LOGGER.warning(
                "Stage B Torch reference parity gate blocked",
                batch=batch,
                backend=backend,
                maxima=maxima,
                task=task_maxima,
            )
        return {
            "batch": int(batch),
            "steps": int(steps),
            "status": "passed" if status else "failed_parity_gate",
            "max_abs": maxima,
            "limits": limits,
            "task_max_abs": task_maxima,
            "per_step": per_step,
            "torch_resource_summary": torch_spec.runtime.resource_summary(),
            "taichi_resource_summary": taichi_spec.runtime.resource_summary(),
        }
    finally:
        torch_spec.close()
        taichi_spec.close()


def _measure_route(batch: int, *, backend: str, kinematics_backend: str, graph: bool, warmup: int, samples: int) -> dict[str, Any]:
    spec = _build(batch, backend=backend, kinematics_backend=kinematics_backend, graph=graph)
    device = _device(spec, backend)
    try:
        spec.reset(seed=73)
        action = _action(spec, backend)
        plan = spec.device_field_plan.as_dict()
        state = spec.read_device_state(tuple(plan["state_readback_fields"]))
        control = spec.action_adapter.convert_device_batch(action, state)
        for _ in range(max(0, int(warmup))):
            spec.runtime.step_device(control)
        _synchronise(device)
        direct = [_measure(lambda: spec.runtime.step_device(control), device) for _ in range(max(1, int(samples)))]
        spec.reset(seed=73)
        for _ in range(max(0, int(warmup))):
            spec.step_device(action)
        _synchronise(device)
        public = [_measure(lambda: spec.step_device(action), device) for _ in range(max(1, int(samples)))]

        def stats(values: list[dict[str, float | None]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for name in ("wall_ms", "cuda_event_ms"):
                selected = [float(value[name]) for value in values if value.get(name) is not None]
                result[name] = {
                    "mean": float(np.mean(selected)),
                    "p50": float(np.percentile(selected, 50)),
                    "p95": float(np.percentile(selected, 95)),
                    "raw": selected,
                } if selected else None
            return result

        return {
            "batch": int(batch),
            "backend": str(backend),
            "kinematics_backend": str(kinematics_backend),
            "graph": bool(graph),
            "warmup": int(warmup),
            "samples": int(samples),
            "direct_runtime_physics": stats(direct),
            "full_device_transition": stats(public),
            "resource_summary": spec.runtime.resource_summary(),
        }
    finally:
        spec.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--batch", type=int, nargs="+", default=(1, 17, 32))
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--include-graph", action="store_true", help="also measure the opt-in Torch contact Graph route")
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("temp_outputs/task_env/stage_b_torch_reference.json"),
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if any(int(batch) < 1 for batch in args.batch):
        raise ValueError("--batch values must be positive")
    if int(args.steps) < 1 or int(args.warmup) < 0 or int(args.samples) < 1:
        raise ValueError("steps/samples must be positive and warmup must be non-negative")
    if str(args.backend) == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("Stage B CUDA reference requires an available CUDA device")
    if args.include_graph and str(args.backend) != "cuda":
        raise ValueError("--include-graph requires --backend cuda")

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "passed",
        "manifest": {
            "backend": str(args.backend),
            "batches": [int(batch) for batch in args.batch],
            "parity_steps": int(args.steps),
            "warmup": int(args.warmup),
            "samples": int(args.samples),
            "semantics": {
                "contact_row_order": "ascending_local_slot_gauss_seidel",
                "solver": "dense_linalg_v1_plus_row_pgs",
                "integrator": "current_static_template_integrator",
                "task_contract": "Go2 reward/observation/terminated/truncated unchanged",
            },
            "default_policy": "opt_in_only_until_parity_and_idle/PPO gates pass",
        },
        "parity": [],
        "benchmark": [],
    }
    for batch in args.batch:
        report["parity"].append(_parity_case(int(batch), backend=str(args.backend), steps=int(args.steps)))
    if any(case.get("status") != "passed" for case in report["parity"]):
        report["status"] = "gated_parity_failure"
    if args.benchmark:
        for batch in args.batch:
            report["benchmark"].append(
                _measure_route(
                    int(batch),
                    backend=str(args.backend),
                    kinematics_backend="torch",
                    graph=False,
                    warmup=int(args.warmup),
                    samples=int(args.samples),
                )
            )
            report["benchmark"].append(
                _measure_route(
                    int(batch),
                    backend=str(args.backend),
                    kinematics_backend="taichi",
                    graph=False,
                    warmup=int(args.warmup),
                    samples=int(args.samples),
                )
            )
            if args.include_graph:
                report["benchmark"].append(
                    _measure_route(
                        int(batch),
                        backend=str(args.backend),
                        kinematics_backend="torch",
                        graph=True,
                        warmup=int(args.warmup),
                        samples=int(args.samples),
                    )
                )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    LOGGER.success("Stage B Torch reference report written", output=str(args.output), cases=len(report["parity"]))


if __name__ == "__main__":
    main()
