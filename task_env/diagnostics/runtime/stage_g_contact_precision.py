"""Stage G: long-window f64/f32 contact precision and lifecycle gate.

This developer diagnostic leaves the production TaskEnv path unchanged.  It
compares fixed-seed f64-request and f32-request runtimes, validates batch-slot
isolation, and exercises masked reset/replay through existing public device
boundaries.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any

import torch
import tensordict  # noqa: F401  # import before Taichi initialization

from task_env.utils.runtime_support import get_task_env_logger
from task_env.diagnostics.runtime.stage17_performance_profile import (
    _fingerprint,
)


LOGGER = get_task_env_logger("simulation", module="task-env-stage-g-contact-precision")
SCHEMA = "task-env-stage-g-contact-precision-v1"

CHECKPOINT_LIMITS = {
    10: {
        "qpos": 2.0e-4,
        "qvel": 2.0e-3,
        "qacc": 2.0e-1,
        "contact_distance": 2.0e-4,
        "contact_normal": 2.0e-4,
        "normal_lambda": 2.0e-3,
        "tangent_lambda": 2.0e-3,
        "observation": 2.0e-3,
        "reward": 2.0e-3,
    },
    100: {
        "qpos": 2.0e-3,
        "qvel": 2.0e-2,
        "qacc": 2.0,
        "contact_distance": 2.0e-3,
        "contact_normal": 2.0e-3,
        "normal_lambda": 2.0e-2,
        "tangent_lambda": 2.0e-2,
        "observation": 2.0e-2,
        "reward": 2.0e-2,
    },
    1000: {
        "qpos": 2.0e-2,
        "qvel": 2.0e-1,
        "qacc": 20.0,
        "contact_distance": 2.0e-2,
        "contact_normal": 2.0e-2,
        "normal_lambda": 2.0e-1,
        "tangent_lambda": 2.0e-1,
        "observation": 2.0e-1,
        "reward": 2.0e-1,
    },
}

STABILITY_LIMITS = {
    "max_penetration_m": 5.0e-2,
    "max_abs_qvel": 100.0,
    "max_abs_qacc": 1.0e5,
    "batch_isolation_qpos": 1.0e-5,
    "batch_isolation_qvel": 1.0e-5,
}

PHYSICS_FIELDS = (
    "qpos",
    "qvel",
    "qacc",
    "contact_distance",
    "contact_normal",
    "normal_lambda",
    "tangent_lambda",
)


def _build(batch: int, *, backend: str, precision: str):
    from task_env.vectorization.factory import make_framework_parallel_spec

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
                    "kinematics_backend": "taichi" if backend == "cuda" else "torch",
                    "contact_precision": str(precision),
                    "cuda_graph": False,
                },
                "enable_ground_contact": True,
                "enable_domain_boundary_contact": False,
            },
        },
        backend=str(backend),
        execution="local",
        transfer_mode="device",
    )


def _physics_values(spec: object) -> dict[str, torch.Tensor]:
    physics = spec.runtime._physics
    return {
        "qpos": physics._qpos,
        "qvel": physics._qvel,
        "qacc": physics._qacc,
        "contact_distance": physics._contact_distance,
        "contact_normal": physics._contact_normal,
        "normal_lambda": physics._contact_normal_lambda,
        "tangent_lambda": physics._contact_tangent_lambda,
    }


def _leaves(value: object, prefix: str = "") -> dict[str, torch.Tensor]:
    if isinstance(value, Mapping):
        result: dict[str, torch.Tensor] = {}
        for name, child in value.items():
            result.update(_leaves(child, f"{prefix}/{name}"))
        return result
    if isinstance(value, torch.Tensor):
        return {prefix or "value": value}
    return {}


def _device(spec: object) -> torch.device:
    return spec.runtime._physics._qpos.device


def _synchronise(device: Any) -> None:
    """Synchronize a diagnostic CUDA read boundary without hiding failures."""

    if device is not None and getattr(device, "type", None) == "cuda":
        torch.cuda.synchronize(device)


def _action(spec: object) -> torch.Tensor:
    return torch.zeros(
        (int(spec.num_envs), int(spec.single_action_space.shape[0])),
        dtype=torch.float32,
        device=_device(spec),
    )


def _max_abs(lhs: torch.Tensor, rhs: torch.Tensor) -> float:
    if lhs.numel() == 0:
        return 0.0
    return float((lhs - rhs).abs().max().item())


def _finite(tensors: Any) -> bool:
    for tensor in tensors:
        if tensor.dtype.is_floating_point or tensor.dtype.is_complex:
            if not bool(torch.isfinite(tensor).all().item()):
                return False
    return True


def _precision_summary(spec: object) -> dict[str, Any]:
    summary = spec.runtime.resource_summary()
    return {
        "requested": summary.get("contact_precision_requested"),
        "effective": summary.get("contact_precision_effective"),
        "solve_intermediate_dtype": summary.get(
            "contact_solve_intermediate_dtype"
        ),
        "policy": summary.get("contact_precision_policy"),
    }


def _checkpoint_passed(result: Mapping[str, Any]) -> bool:
    limits = result["limits"]
    return (
        all(
            float(result["max_abs"][name]) <= float(limits[name])
            for name in PHYSICS_FIELDS
        )
        and float(result["observation_max_abs"]) <= float(limits["observation"])
        and float(result["reward_max_abs"]) <= float(limits["reward"])
        and all(
            float(value) <= float(limits["reward"])
            for value in result["reward_term_max_abs"].values()
        )
        and not result["observation_leaf_name_mismatch"]
        and not result["reward_term_name_mismatch"]
        and bool(result["terminated_equal_every_tick"])
        and bool(result["truncated_equal_every_tick"])
        and bool(result["contact_active_equal_every_tick"])
        and bool(result["finite"])
        and float(result["max_penetration_m"])
        <= STABILITY_LIMITS["max_penetration_m"]
        and float(result["max_abs_qvel"]) <= STABILITY_LIMITS["max_abs_qvel"]
        and float(result["max_abs_qacc"]) <= STABILITY_LIMITS["max_abs_qacc"]
    )


def _parity_case(
    batch: int,
    *,
    backend: str,
    checkpoints: tuple[int, ...],
) -> dict[str, Any]:
    reference = _build(batch, backend=backend, precision="f64")
    candidate = None
    try:
        candidate = _build(batch, backend=backend, precision="f32")
        reference.reset(seed=73)
        candidate.reset(seed=73)
        device = _device(reference)
        _synchronise(device)
        action = _action(reference)
        maxima = {name: 0.0 for name in PHYSICS_FIELDS}
        observation_maximum = 0.0
        reward_maximum = 0.0
        reward_term_maxima: dict[str, float] = {}
        observation_leaf_name_mismatch: set[str] = set()
        reward_term_name_mismatch: set[str] = set()
        terminated_equal = True
        truncated_equal = True
        contact_active_equal = True
        finite = True
        max_penetration = 0.0
        max_abs_qvel = 0.0
        max_abs_qacc = 0.0
        episode_index = 0
        first_lifecycle_mismatch_tick: int | None = None
        checkpoint_set = set(checkpoints)
        checkpoint_results: list[dict[str, Any]] = []

        for tick in range(1, max(checkpoints) + 1):
            reference_transition = reference.step_device(action)
            candidate_transition = candidate.step_device(action)
            # Diagnostic reads are ordered at this explicit boundary.  No
            # synchronization is added to the production transition path.
            _synchronise(device)
            reference_values = _physics_values(reference)
            candidate_values = _physics_values(candidate)
            for name in PHYSICS_FIELDS:
                maxima[name] = max(
                    maxima[name],
                    _max_abs(reference_values[name], candidate_values[name]),
                )

            reference_observation = _leaves(
                reference_transition.observation, "observation"
            )
            candidate_observation = _leaves(
                candidate_transition.observation, "observation"
            )
            observation_leaf_name_mismatch.update(
                set(reference_observation) ^ set(candidate_observation)
            )
            for name in sorted(
                set(reference_observation) & set(candidate_observation)
            ):
                if reference_observation[name].dtype.is_floating_point:
                    observation_maximum = max(
                        observation_maximum,
                        _max_abs(
                            reference_observation[name],
                            candidate_observation[name],
                        ),
                    )

            reward_maximum = max(
                reward_maximum,
                _max_abs(reference_transition.reward, candidate_transition.reward),
            )
            reference_terms = _leaves(
                reference_transition.infos["reward_terms"], "reward_terms"
            )
            candidate_terms = _leaves(
                candidate_transition.infos["reward_terms"], "reward_terms"
            )
            reward_term_name_mismatch.update(
                set(reference_terms) ^ set(candidate_terms)
            )
            for name in sorted(set(reference_terms) & set(candidate_terms)):
                reward_term_maxima[name] = max(
                    reward_term_maxima.get(name, 0.0),
                    _max_abs(reference_terms[name], candidate_terms[name]),
                )

            terminated_this_tick = torch.equal(
                reference_transition.terminated, candidate_transition.terminated
            )
            truncated_this_tick = torch.equal(
                reference_transition.truncated, candidate_transition.truncated
            )
            contact_active_this_tick = torch.equal(
                reference.runtime._physics._contact_active,
                candidate.runtime._physics._contact_active,
            )
            terminated_equal = terminated_equal and terminated_this_tick
            truncated_equal = truncated_equal and truncated_this_tick
            contact_active_equal = (
                contact_active_equal and contact_active_this_tick
            )

            finite = finite and _finite(
                list(reference_values.values())
                + list(candidate_values.values())
                + list(reference_observation.values())
                + list(candidate_observation.values())
                + [reference_transition.reward, candidate_transition.reward]
                + list(reference_terms.values())
                + list(candidate_terms.values())
            )
            for values in (reference_values, candidate_values):
                if values["contact_distance"].numel():
                    max_penetration = max(
                        max_penetration,
                        float(
                            torch.clamp(
                                -values["contact_distance"], min=0.0
                            ).max().item()
                        ),
                    )
                max_abs_qvel = max(
                    max_abs_qvel, float(values["qvel"].abs().max().item())
                )
                max_abs_qacc = max(
                    max_abs_qacc, float(values["qacc"].abs().max().item())
                )

            if tick in checkpoint_set:
                checkpoint_result = {
                    "tick": tick,
                    "max_abs": dict(maxima),
                    "observation_max_abs": observation_maximum,
                    "reward_max_abs": reward_maximum,
                    "reward_term_max_abs": dict(reward_term_maxima),
                    "observation_leaf_name_mismatch": sorted(
                        observation_leaf_name_mismatch
                    ),
                    "reward_term_name_mismatch": sorted(
                        reward_term_name_mismatch
                    ),
                    "terminated_equal_every_tick": terminated_equal,
                    "truncated_equal_every_tick": truncated_equal,
                    "contact_active_equal_every_tick": contact_active_equal,
                    "finite": finite,
                    "max_penetration_m": max_penetration,
                    "max_abs_qvel": max_abs_qvel,
                    "max_abs_qacc": max_abs_qacc,
                    "limits": CHECKPOINT_LIMITS[tick],
                }
                checkpoint_result["status"] = (
                    "passed"
                    if _checkpoint_passed(checkpoint_result)
                    else "failed_checkpoint_gate"
                )
                checkpoint_results.append(checkpoint_result)

            if not terminated_this_tick or not truncated_this_tick:
                first_lifecycle_mismatch_tick = tick
                break

            reference_done = torch.logical_or(
                reference_transition.terminated, reference_transition.truncated
            )
            if bool(reference_done.any().item()):
                episode_index += 1
                reset_seed = 73 + episode_index
                reference.reset(seed=reset_seed)
                candidate.reset(seed=reset_seed)
                _synchronise(device)

        passed = (
            first_lifecycle_mismatch_tick is None
            and len(checkpoint_results) == len(checkpoint_set)
            and all(result["status"] == "passed" for result in checkpoint_results)
        )
        return {
            "batch": int(batch),
            "backend": str(backend),
            "status": "passed" if passed else "failed_precision_gate",
            "checkpoints": checkpoint_results,
            "first_lifecycle_mismatch_tick": first_lifecycle_mismatch_tick,
            "episodes_reset": int(episode_index),
            "precision": {
                "reference": _precision_summary(reference),
                "candidate": _precision_summary(candidate),
            },
        }
    finally:
        try:
            reference.close()
        finally:
            if candidate is not None:
                candidate.close()


def _batch_isolation(*, backend: str, steps: int) -> dict[str, Any]:
    spec1 = _build(1, backend=backend, precision="f32")
    spec2 = None
    try:
        spec2 = _build(2, backend=backend, precision="f32")
        spec1.reset(seed=73)
        spec2.reset(seed=73)
        device = _device(spec1)
        _synchronise(device)
        names = ("qpos", "qvel", "qacc", "ctrl", "act")
        state1 = spec1.runtime.read_device_state(names).arrays
        state2 = spec2.runtime.read_device_state(names).arrays
        payload2 = {name: value.clone() for name, value in state2.items()}
        for name in names:
            payload2[name][0].copy_(state1[name][0])
        mask2 = torch.tensor((True, False), dtype=torch.bool, device=device)
        spec2.runtime.reset_device(payload2, mask2)
        control1 = torch.zeros_like(state1["ctrl"])
        control2 = torch.zeros_like(state2["ctrl"])
        qpos_maximum = 0.0
        qvel_maximum = 0.0
        finite = True
        for _ in range(int(steps)):
            result1 = spec1.runtime.step_device(control1)
            result2 = spec2.runtime.step_device(control2)
            _synchronise(device)
            qpos1 = result1.arrays["qpos"][0]
            qpos2 = result2.arrays["qpos"][0]
            qvel1 = result1.arrays["qvel"][0]
            qvel2 = result2.arrays["qvel"][0]
            qpos_maximum = max(qpos_maximum, _max_abs(qpos1, qpos2))
            qvel_maximum = max(qvel_maximum, _max_abs(qvel1, qvel2))
            finite = finite and _finite((qpos1, qpos2, qvel1, qvel2))
        passed = (
            finite
            and qpos_maximum <= STABILITY_LIMITS["batch_isolation_qpos"]
            and qvel_maximum <= STABILITY_LIMITS["batch_isolation_qvel"]
        )
        return {
            "status": "passed" if passed else "failed_batch_isolation_gate",
            "backend": str(backend),
            "precision": "f32",
            "steps": int(steps),
            "qpos_max_abs": qpos_maximum,
            "qvel_max_abs": qvel_maximum,
            "finite": finite,
            "limits": {
                "qpos": STABILITY_LIMITS["batch_isolation_qpos"],
                "qvel": STABILITY_LIMITS["batch_isolation_qvel"],
            },
            "batch_1_precision": _precision_summary(spec1),
            "batch_2_precision": _precision_summary(spec2),
        }
    finally:
        try:
            spec1.close()
        finally:
            if spec2 is not None:
                spec2.close()


def _replay_trace(spec: object, *, steps: int) -> dict[str, torch.Tensor]:
    action = _action(spec)
    qpos: list[torch.Tensor] = []
    qvel: list[torch.Tensor] = []
    reward: list[torch.Tensor] = []
    terminated: list[torch.Tensor] = []
    truncated: list[torch.Tensor] = []
    for _ in range(int(steps)):
        transition = spec.step_device(action)
        _synchronise(_device(spec))
        values = _physics_values(spec)
        qpos.append(values["qpos"].clone())
        qvel.append(values["qvel"].clone())
        reward.append(transition.reward.clone())
        terminated.append(transition.terminated.clone())
        truncated.append(transition.truncated.clone())
    return {
        "qpos": torch.stack(qpos),
        "qvel": torch.stack(qvel),
        "reward": torch.stack(reward),
        "terminated": torch.stack(terminated),
        "truncated": torch.stack(truncated),
    }


def _masked_reset_and_replay(backend: str, precision: str) -> dict[str, Any]:
    spec = _build(17, backend=backend, precision=precision)
    try:
        spec.reset(seed=73)
        device = _device(spec)
        _synchronise(device)
        names = ("qpos", "qvel", "qacc", "ctrl", "act")
        before = spec.runtime.read_device_state(names)
        before_qpos = before.arrays["qpos"].clone()
        before_qvel = before.arrays["qvel"].clone()
        payload = {name: value.clone() for name, value in before.arrays.items()}
        payload["qpos"][1, 2].add_(0.10)
        mask = torch.zeros(17, dtype=torch.bool, device=device)
        mask[1] = True
        after = spec.runtime.reset_device(payload, mask)
        _synchronise(device)
        unselected = torch.logical_not(mask)
        physics = spec.runtime._physics
        reset_checks = {
            "unselected_qpos_bitwise_unchanged": torch.equal(
                after.arrays["qpos"][unselected], before_qpos[unselected]
            ),
            "unselected_qvel_bitwise_unchanged": torch.equal(
                after.arrays["qvel"][unselected], before_qvel[unselected]
            ),
            "selected_qpos_matches_payload": torch.equal(
                after.arrays["qpos"][1], payload["qpos"][1]
            ),
            "selected_contact_count_cleared": bool(
                torch.all(physics._contact_count[1] == 0).item()
            ),
            "selected_contact_active_cleared": bool(
                torch.all(torch.logical_not(physics._contact_active[1])).item()
            ),
            "selected_normal_lambda_cleared": bool(
                torch.all(physics._contact_normal_lambda[1] == 0).item()
            ),
            "selected_tangent_lambda_cleared": bool(
                torch.all(physics._contact_tangent_lambda[1] == 0).item()
            ),
            "selected_contact_geom_workspace_cleared": bool(
                torch.all(physics._contact_geom[1] == -1).item()
            ),
        }

        spec.reset(seed=73)
        first = _replay_trace(spec, steps=10)
        spec.reset(seed=73)
        second = _replay_trace(spec, steps=10)
        qpos_error = _max_abs(first["qpos"], second["qpos"])
        qvel_error = _max_abs(first["qvel"], second["qvel"])
        reward_error = _max_abs(first["reward"], second["reward"])
        terminated_equal = torch.equal(
            first["terminated"], second["terminated"]
        )
        truncated_equal = torch.equal(first["truncated"], second["truncated"])
        done_equal = torch.equal(
            torch.logical_or(first["terminated"], first["truncated"]),
            torch.logical_or(second["terminated"], second["truncated"]),
        )
        finite = _finite(
            (
                first["qpos"],
                second["qpos"],
                first["qvel"],
                second["qvel"],
                first["reward"],
                second["reward"],
            )
        )
        replay_limit = 1.0e-7
        passed = (
            all(reset_checks.values())
            and terminated_equal
            and truncated_equal
            and done_equal
            and finite
            and qpos_error <= replay_limit
            and qvel_error <= replay_limit
            and reward_error <= replay_limit
        )
        return {
            "status": "passed" if passed else "failed_masked_reset_replay_gate",
            "backend": str(backend),
            "precision": _precision_summary(spec),
            "masked_reset": reset_checks,
            "replay": {
                "steps": 10,
                "qpos_max_abs": qpos_error,
                "qvel_max_abs": qvel_error,
                "reward_max_abs": reward_error,
                "terminated_bitwise_equal": terminated_equal,
                "truncated_bitwise_equal": truncated_equal,
                "done_bitwise_equal": done_equal,
                "finite": finite,
                "limit": replay_limit,
            },
        }
    finally:
        spec.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--batches", type=int, nargs="+", default=(1, 2, 17, 32))
    parser.add_argument(
        "--checkpoints", type=int, nargs="+", default=(10, 100, 1000)
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("temp_outputs/task_env/stage_g_contact_precision.json"),
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    checkpoints = tuple(int(value) for value in args.checkpoints)
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "failed",
        "manifest": {
            "backend": str(args.backend),
            "batches": [int(value) for value in args.batches],
            "checkpoints": list(checkpoints),
            "seed": 73,
            "reference_precision": "f64",
            "candidate_precision": "f32",
            "kinematics_backend": (
                "taichi" if str(args.backend) == "cuda" else "torch"
            ),
            "fingerprint": None,
        },
        "fixed_limits": {
            "checkpoints": CHECKPOINT_LIMITS,
            "stability": STABILITY_LIMITS,
        },
        "precision_summaries": [],
        "cases": [],
        "batch_isolation": None,
        "masked_reset_and_replay": {},
        "errors": [],
    }
    try:
        if any(int(batch) < 1 for batch in args.batches):
            raise ValueError("--batches values must be positive")
        unsupported = sorted(set(checkpoints) - set(CHECKPOINT_LIMITS))
        if unsupported:
            raise ValueError(
                "--checkpoints values must be selected from "
                f"{sorted(CHECKPOINT_LIMITS)}; unsupported: {unsupported}"
            )
        report["manifest"]["fingerprint"] = _fingerprint(str(args.backend))
        if str(args.backend) == "cuda" and not torch.cuda.is_available():
            raise RuntimeError(
                "Stage G CUDA gate requires an available CUDA device"
            )
        for batch in args.batches:
            case = _parity_case(
                int(batch), backend=str(args.backend), checkpoints=checkpoints
            )
            report["cases"].append(case)
            report["precision_summaries"].append(
                {"batch": int(batch), **case["precision"]}
            )
        report["batch_isolation"] = _batch_isolation(
            backend=str(args.backend), steps=10
        )
        for precision in ("f64", "f32"):
            report["masked_reset_and_replay"][precision] = (
                _masked_reset_and_replay(str(args.backend), precision)
            )
        statuses = [case["status"] for case in report["cases"]]
        statuses.append(report["batch_isolation"]["status"])
        statuses.extend(
            result["status"]
            for result in report["masked_reset_and_replay"].values()
        )
        if all(status == "passed" for status in statuses):
            report["status"] = "passed"
    except Exception as exc:
        report["status"] = "failed"
        report["errors"].append(
            {"type": type(exc).__name__, "message": str(exc)}
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    if report["status"] == "passed":
        LOGGER.success(
            "Stage G contact precision report passed",
            output=str(args.output),
            cases=len(report["cases"]),
        )
        return
    LOGGER.warning(
        "Stage G contact precision gate failed",
        output=str(args.output),
        errors=report["errors"],
    )
    raise SystemExit(1)


if __name__ == "__main__":
    main()
