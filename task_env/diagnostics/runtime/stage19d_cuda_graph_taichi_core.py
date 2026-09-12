"""Stage 19d Taichi-FK/Torch-core CUDA Graph parity and benchmark gate.

The ground-contact case captures one complete Torch physics substep and keeps
Taichi FK outside the Graph between substep replays.  The historical
no-contact ``core_v2`` case remains selectable for regression coverage.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import time

from task_env.utils._device_stack import preload_device_stack


# Preserve the Triton-before-Taichi ordering before importing the runtime
# factory or any dependency that can initialize Taichi.
DEVICE_STACK_PRELOAD = preload_device_stack()

import numpy as np
import torch
import tensordict  # noqa: F401  # import before Taichi initialization

from task_env.diagnostics.runtime.stage19d_cuda_graph_contact import (
    CONTACT_PGS_BOOTSTRAP_POLICY,
    REQUIRED_CONTACT_PGS_BACKEND,
    _validate_required_contact_pgs_backend,
)
from task_env.vectorization.factory import make_framework_parallel_spec


LOGGER = logging.getLogger(__name__)


def _masked_reset_immediate_replay_lifecycle(
    *, physics: object, reset, replay, mode: str
) -> dict[str, object]:
    """Check that a fixed-pointer masked reset preserves the captured graph."""

    before_graph = physics._cuda_graph
    before_key = physics._cuda_graph_key
    before_summary = physics.resource_summary()["cuda_graph"]
    before_boundary = physics.runtime_boundary_snapshot()
    before_pointers = before_boundary.get(
        "masked_device_reset_tensor_pointers", before_boundary["torch_tensor_pointers"]
    )
    reset()
    after_reset = physics.resource_summary()["cuda_graph"]
    after_boundary = physics.runtime_boundary_snapshot()
    after_pointers = after_boundary.get(
        "masked_device_reset_tensor_pointers", after_boundary["torch_tensor_pointers"]
    )
    values = {
        "mode": str(mode),
        "ready_before_reset": before_summary["status"] == "ready",
        "ready_after_reset": after_reset["status"] == "ready",
        "same_graph_identity": physics._cuda_graph is before_graph,
        "same_capture_key": physics._cuda_graph_key == before_key,
        "pointers_stable": after_pointers == before_pointers,
    }
    if not all(values.values()):
        raise AssertionError(values)
    replay()
    after_replay = physics.resource_summary()["cuda_graph"]
    values["ready_after_immediate_replay"] = (
        after_replay["status"] == "ready"
        and physics._cuda_graph is before_graph
        and physics._cuda_graph_key == before_key
    )
    if not values["ready_after_immediate_replay"]:
        raise AssertionError(values)
    return values


def _contact_cases(mode: str) -> tuple[bool, ...]:
    return {
        "ground": (True,),
        "no-contact": (False,),
        "both": (False, True),
    }[str(mode)]


def _parity_limits(*, contact: bool) -> dict[str, float]:
    limits = {"qpos": 2.0e-4, "qvel": 2.0e-3, "qacc": 2.0e-2}
    if contact:
        limits.update(
            {
                "contact_distance": 2.0e-4,
                "normal_lambda": 2.0e-3,
                "tangent_lambda": 2.0e-3,
            }
        )
    return limits


def _distinct_masked_reset_payload(
    physics: object,
    mask: torch.Tensor,
    *,
    sequence: int,
) -> dict[str, torch.Tensor]:
    """Build a physically valid reset that cannot pass as a live-state no-op."""

    payload = {
        name: getattr(physics, f"_{name}").clone()
        for name in ("qpos", "qvel", "qacc", "ctrl", "act")
    }
    selected = mask.to(device=payload["qpos"].device, dtype=torch.bool)
    delta = float(int(sequence) + 1)
    if payload["qpos"].shape[1] > 2:
        # Move only root height; leave the root quaternion untouched/normalized.
        payload["qpos"][selected, 2] += 0.0025 * delta
    elif payload["qpos"].shape[1]:
        payload["qpos"][selected, 0] += 0.0025 * delta
    if payload["qvel"].shape[1]:
        payload["qvel"][selected, 0] += 0.01 * delta
    payload["qacc"][selected] = 0.0
    payload["ctrl"][selected] = 0.0
    payload["act"][selected] = 0.0
    return payload


def _tensor_leaves(value: object, prefix: str = "observation") -> dict[str, torch.Tensor]:
    if isinstance(value, torch.Tensor):
        return {prefix: value}
    items = getattr(value, "items", None)
    if callable(items):
        leaves: dict[str, torch.Tensor] = {}
        for key, child in items():
            leaves.update(_tensor_leaves(child, f"{prefix}.{key}"))
        return leaves
    raise TypeError(f"unsupported observation leaf container: {type(value).__name__}")


def _observation_max_abs(left: object, right: object) -> float:
    left_leaves = _tensor_leaves(left)
    right_leaves = _tensor_leaves(right)
    if set(left_leaves) != set(right_leaves):
        raise AssertionError(
            f"reset observation schema mismatch: {sorted(left_leaves)} != "
            f"{sorted(right_leaves)}"
        )
    maxima = []
    for name in left_leaves:
        lhs = left_leaves[name]
        rhs = right_leaves[name]
        if tuple(lhs.shape) != tuple(rhs.shape):
            raise AssertionError(
                f"reset observation shape mismatch for {name}: "
                f"{tuple(lhs.shape)} != {tuple(rhs.shape)}"
            )
        maxima.append(float((lhs - rhs).abs().max().item()) if lhs.numel() else 0.0)
    return max(maxima, default=0.0)


def _reset_comparison_fields(*, contact: bool) -> dict[str, tuple[str, float]]:
    fields = {
        "qpos": ("_qpos", 2.0e-4),
        "qvel": ("_qvel", 2.0e-3),
        "qacc": ("_qacc", 2.0e-2),
        "body_xpos": ("_body_xpos", 2.0e-4),
        "body_xquat": ("_body_xquat", 2.0e-4),
        "body_linear_vel": ("_body_linear_vel", 2.0e-3),
        "body_angular_vel": ("_body_angular_vel", 2.0e-3),
        "geom_xpos": ("_geom_xpos", 2.0e-4),
    }
    if contact:
        fields.update(
            {
                "contact_distance": ("_contact_distance", 2.0e-4),
                "normal_lambda": ("_contact_normal_lambda", 2.0e-3),
                "tangent_lambda": ("_contact_tangent_lambda", 2.0e-3),
            }
        )
    return fields


def _field_max_abs(left: object, right: object, attribute: str) -> float:
    lhs = getattr(left, attribute)
    rhs = getattr(right, attribute)
    if tuple(lhs.shape) != tuple(rhs.shape):
        raise AssertionError(
            f"reset parity shape mismatch for {attribute}: "
            f"{tuple(lhs.shape)} != {tuple(rhs.shape)}"
        )
    return float((lhs - rhs).abs().max().item()) if lhs.numel() else 0.0


def _checked_field_maxima(
    left: object,
    right: object,
    fields: dict[str, tuple[str, float]],
    *,
    phase: str,
    left_state: object | None = None,
    right_state: object | None = None,
) -> dict[str, float]:
    """Compare every qualified field and fail at the phase that produced it."""

    maxima: dict[str, float] = {}
    for name, (attribute, limit) in fields.items():
        if (
            name in {"qpos", "qvel", "qacc"}
            and left_state is not None
            and right_state is not None
        ):
            lhs = left_state.arrays[name]
            rhs = right_state.arrays[name]
            value = float((lhs - rhs).abs().max().item()) if lhs.numel() else 0.0
        else:
            value = _field_max_abs(left, right, attribute)
        maxima[name] = value
        if value > limit:
            raise AssertionError(
                f"Taichi {phase} parity failed for field={name}: {value} > {limit}"
            )
    return maxima


def _assert_reset_applied_and_isolated(
    *,
    physics: object,
    before: dict[str, torch.Tensor],
    payload: dict[str, torch.Tensor],
    mask: torch.Tensor,
) -> dict[str, bool]:
    selected = mask.to(device=physics._qpos.device, dtype=torch.bool)
    if torch.equal(physics._qpos[selected], before["_qpos"][selected]):
        raise AssertionError("masked reset did not change selected qpos")
    if torch.equal(physics._qvel[selected], before["_qvel"][selected]):
        raise AssertionError("masked reset did not change selected qvel")
    for name in ("qpos", "qvel", "qacc", "ctrl", "act"):
        actual = getattr(physics, f"_{name}")
        if not torch.equal(actual[selected], payload[name][selected]):
            raise AssertionError(f"masked reset did not apply selected {name}")
    unselected = torch.logical_not(selected)
    if bool(unselected.any().item()):
        for attribute, old_value in before.items():
            current = getattr(physics, attribute)
            if not torch.equal(current[unselected], old_value[unselected]):
                raise AssertionError(
                    f"masked reset changed unselected {attribute}"
                )
    return {
        "selected_qpos_changed": True,
        "selected_qvel_changed": True,
        "unselected_isolated": True,
    }


def _reset_and_build_observation(
    adapter: object,
    payload: dict[str, torch.Tensor],
    mask: torch.Tensor,
) -> tuple[object, object]:
    """Cross the semantic task-reset boundary before building observation."""

    state = adapter.reset_device(payload, mask)
    return state, adapter._device_observation_builder(state)


def _build(
    batch: int,
    *,
    graph: bool,
    contact: bool = False,
    contact_precision: str = "f64",
):
    contact_enabled = bool(contact)
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
                    "profile": (
                        "articulated_fused_ground_contact_v1"
                        if contact_enabled
                        else "articulated_fused_no_contact_v1"
                    ),
                    "kinematics_backend": "taichi",
                    "cuda_graph": bool(graph),
                    "contact_precision": str(contact_precision),
                    "contact": {
                        "response_backend": "active_slot_cholesky_f32_v1",
                        "fixed_topology_child_schur": False,
                        "root_factor_6x6": False,
                    },
                },
                "enable_ground_contact": contact_enabled,
                "enable_domain_boundary_contact": False,
            },
        },
        backend="cuda",
    )


def _parity_case(
    batch: int,
    steps: int,
    *,
    contact: bool = False,
    contact_precision: str = "f64",
) -> dict[str, object]:
    contact_enabled = bool(contact)
    eager = _build(
        batch,
        graph=False,
        contact=contact_enabled,
        contact_precision=contact_precision,
    )
    graph = _build(
        batch,
        graph=True,
        contact=contact_enabled,
        contact_precision=contact_precision,
    )
    try:
        eager.reset(seed=73)
        graph.reset(seed=73)
        torch.cuda.synchronize()
        fields = {
            "qpos": "_qpos",
            "qvel": "_qvel",
            "qacc": "_qacc",
        }
        if contact_enabled:
            fields.update(
                {
                    "contact_distance": "_contact_distance",
                    "normal_lambda": "_contact_normal_lambda",
                    "tangent_lambda": "_contact_tangent_lambda",
                }
            )
        maxima = {name: 0.0 for name in fields}
        for _ in range(int(steps)):
            eager.runtime._physics.step(eager.runtime._physics.control_substeps)
            graph.runtime._physics.step(graph.runtime._physics.control_substeps)
            torch.cuda.synchronize()
            for name, attribute in fields.items():
                eager_value = getattr(eager.runtime._physics, attribute)
                graph_value = getattr(graph.runtime._physics, attribute)
                maxima[name] = max(
                    maxima[name],
                    float((eager_value - graph_value).abs().max().item()),
                )
        eager_summary = eager.runtime.resource_summary()
        summary = graph.runtime.resource_summary()
        cuda_graph = summary["cuda_graph"]
        expected_scope = "contact_core_full_v5" if contact_enabled else "core_v2"
        if cuda_graph["status"] != "ready" or cuda_graph["scope"] != expected_scope:
            raise AssertionError(cuda_graph)
        backend_validation = None
        if contact_enabled:
            backend_validation = {
                "initial_eager_runtime": _validate_required_contact_pgs_backend(
                    eager_summary,
                    point="taichi_initial_eager_runtime",
                ),
                "post_graph_replay": _validate_required_contact_pgs_backend(
                    summary,
                    point="taichi_post_graph_replay",
                ),
            }
        limits = _parity_limits(contact=contact_enabled)
        for name, limit in limits.items():
            if maxima[name] > limit:
                raise AssertionError(
                    f"Taichi CUDA Graph core parity failed for B={batch}: {maxima}"
                )
        reset_lifecycle = []
        eager_physics = eager.runtime._physics
        graph_physics = graph.runtime._physics
        reset_fields = _reset_comparison_fields(contact=contact_enabled)
        isolation_attributes = tuple(
            dict.fromkeys(
                [f"_{name}" for name in ("qpos", "qvel", "qacc", "ctrl", "act")]
                + [attribute for attribute, _limit in reset_fields.values()]
            )
        )
        for sequence, mode in enumerate(("sparse", "all")):
            mask = torch.ones(int(batch), dtype=torch.bool, device=graph_physics.device)
            if mode == "sparse" and int(batch) > 1:
                mask[1:] = False
            payload = _distinct_masked_reset_payload(
                graph_physics,
                mask,
                sequence=sequence,
            )
            graph_before = {
                attribute: getattr(graph_physics, attribute).clone()
                for attribute in isolation_attributes
            }
            eager_reset_state, eager_reset_observation = (
                _reset_and_build_observation(eager, payload, mask)
            )
            graph_reset_evidence: dict[str, object] = {}

            def reset_graph_runtime() -> None:
                graph_reset_state, graph_reset_observation = (
                    _reset_and_build_observation(graph, payload, mask)
                )
                graph_reset_evidence["isolation"] = _assert_reset_applied_and_isolated(
                    physics=graph_physics,
                    before=graph_before,
                    payload=payload,
                    mask=mask,
                )
                graph_reset_evidence["reset_max_abs"] = _checked_field_maxima(
                    eager_physics,
                    graph_physics,
                    reset_fields,
                    phase=f"reset_{mode}",
                    left_state=eager_reset_state,
                    right_state=graph_reset_state,
                )
                graph_reset_evidence["observation"] = graph_reset_observation

            lifecycle = _masked_reset_immediate_replay_lifecycle(
                physics=graph_physics,
                reset=reset_graph_runtime,
                replay=lambda: graph_physics.step(graph_physics.control_substeps),
                mode=mode,
            )
            eager_physics.step(eager_physics.control_substeps)
            torch.cuda.synchronize()
            post_replay_max_abs = _checked_field_maxima(
                eager_physics,
                graph_physics,
                reset_fields,
                phase=f"masked_reset_replay_B{batch}_{mode}",
            )
            reset_observation_max_abs = _observation_max_abs(
                eager_reset_observation,
                graph_reset_evidence["observation"],
            )
            eager_post_state = eager_physics.read_device_state(
                eager_physics._device_state_field_names
            )
            graph_post_state = graph_physics.read_device_state(
                graph_physics._device_state_field_names
            )
            post_observation_max_abs = _observation_max_abs(
                eager._device_observation_builder(eager_post_state),
                graph._device_observation_builder(graph_post_state),
            )
            observation_limit = 2.0e-2
            if max(reset_observation_max_abs, post_observation_max_abs) > observation_limit:
                raise AssertionError(
                    f"Taichi masked-reset observation parity failed for B={batch}, "
                    f"mode={mode}: reset={reset_observation_max_abs}, "
                    f"post_replay={post_observation_max_abs}"
                )
            reset_lifecycle.append(
                lifecycle
                | {
                    "applied_and_isolated": graph_reset_evidence["isolation"],
                    "reset_max_abs": graph_reset_evidence["reset_max_abs"],
                    "reset_observation_max_abs": reset_observation_max_abs,
                    "post_replay_max_abs": post_replay_max_abs,
                    "post_replay_observation_max_abs": post_observation_max_abs,
                }
            )
        return {
            "batch": int(batch),
            "steps": int(steps),
            "contact_enabled": contact_enabled,
            "static_template_contact_precision": str(contact_precision),
            "status": "passed",
            "max_abs": maxima,
            "contact_pgs_backend_validation": backend_validation,
            "masked_device_reset_lifecycle": reset_lifecycle,
            "resource_summary": summary,
        }
    finally:
        eager.close()
        graph.close()


def _benchmark_case(
    batch: int,
    warmup: int,
    samples: int,
    *,
    contact: bool = False,
    contact_precision: str = "f64",
) -> dict[str, object]:
    contact_enabled = bool(contact)
    eager = _build(
        batch,
        graph=False,
        contact=contact_enabled,
        contact_precision=contact_precision,
    )
    graph = _build(
        batch,
        graph=True,
        contact=contact_enabled,
        contact_precision=contact_precision,
    )
    try:
        eager.reset(seed=73)
        graph.reset(seed=73)
        for _ in range(int(warmup)):
            eager.runtime._physics.step(eager.runtime._physics.control_substeps)
            graph.runtime._physics.step(graph.runtime._physics.control_substeps)
        torch.cuda.synchronize()
        label = "taichi_contact_core" if contact_enabled else "taichi_core"
        eager_label = f"{label}_eager"
        graph_label = f"{label}_cuda_graph"
        timings: dict[str, list[float]] = {eager_label: [], graph_label: []}
        for _ in range(int(samples)):
            start = time.perf_counter()
            eager.runtime._physics.step(eager.runtime._physics.control_substeps)
            torch.cuda.synchronize()
            timings[eager_label].append((time.perf_counter() - start) * 1000.0)
        for _ in range(int(samples)):
            start = time.perf_counter()
            graph.runtime._physics.step(graph.runtime._physics.control_substeps)
            torch.cuda.synchronize()
            timings[graph_label].append((time.perf_counter() - start) * 1000.0)
        p50 = {name: float(np.percentile(values, 50)) for name, values in timings.items()}
        p95 = {name: float(np.percentile(values, 95)) for name, values in timings.items()}
        eager_summary = eager.runtime.resource_summary()
        graph_summary = graph.runtime.resource_summary()
        backend_validation = None
        if contact_enabled:
            backend_validation = {
                "benchmark_eager": _validate_required_contact_pgs_backend(
                    eager_summary,
                    point="taichi_benchmark_eager",
                ),
                "benchmark_graph": _validate_required_contact_pgs_backend(
                    graph_summary,
                    point="taichi_benchmark_graph",
                ),
            }
        return {
            "batch": int(batch),
            "contact_enabled": contact_enabled,
            "static_template_contact_precision": str(contact_precision),
            "warmup": int(warmup),
            "samples": int(samples),
            "status": "passed",
            "contact_pgs_backend_validation": backend_validation,
            "p50_ms": p50,
            "p95_ms": p95,
            "ratio_graph_over_eager": {
                "p50_ms": p50[graph_label] / p50[eager_label],
                "p95_ms": p95[graph_label] / p95[eager_label],
            },
        }
    finally:
        eager.close()
        graph.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, nargs="+", default=(1, 2, 17))
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--samples", type=int, default=8)
    parser.add_argument(
        "--contact-mode",
        choices=("ground", "no-contact", "both"),
        default="ground",
        help="run the new ground-contact scope, the historical no-contact scope, or both",
    )
    parser.add_argument(
        "--contact-precision",
        choices=("f64", "f32"),
        default="f64",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("temp_outputs/task_env/stage19d_cuda_graph_taichi_core.json"),
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    contact_cases = _contact_cases(args.contact_mode)
    contact_backend_required = True in contact_cases
    report = {
        "schema": "task_env.stage19d_cuda_graph_taichi_core.v2",
        "status": "passed",
        "manifest": {
            "batches": [int(batch) for batch in args.batch],
            "contact_mode": str(args.contact_mode),
            "static_template_contact_precision": str(args.contact_precision),
            "contact_pgs_bootstrap_policy": (
                CONTACT_PGS_BOOTSTRAP_POLICY
                if contact_backend_required
                else "preloaded_not_required_no_contact"
            ),
            "required_contact_pgs_backend": (
                REQUIRED_CONTACT_PGS_BACKEND if contact_backend_required else None
            ),
            "device_stack_preload": DEVICE_STACK_PRELOAD.to_dict(),
        },
        "policy": {
            "ground_contact_scope": "contact_core_full_v5",
            "ground_contact_capture_unit": "one_complete_torch_core_substep",
            "inter_substep_fk": "eager_taichi_refresh",
            "interop_ordering": "host_fenced_v1",
            "no_contact_scope": "core_v2",
            "masked_device_reset": {
                "modes": ["sparse", "all"],
                "oracle": "same_payload_eager_then_immediate_graph_replay",
                "selected_state": "distinct_root_height_and_velocity",
                "unselected_state": "exact_isolation_required",
                "storage": "all_state_fk_contact_compaction_pointers_v1",
            },
        },
        "parity": [
            _parity_case(
                int(batch),
                int(args.steps),
                contact=contact,
                contact_precision=str(args.contact_precision),
            )
            for contact in contact_cases
            for batch in args.batch
        ],
        "benchmark": (
            [
                _benchmark_case(
                    int(batch),
                    int(args.warmup),
                    int(args.samples),
                    contact=contact,
                    contact_precision=str(args.contact_precision),
                )
                for contact in contact_cases
                for batch in args.batch
            ]
            if args.benchmark
            else []
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    LOGGER.info("Stage 19d Taichi core CUDA Graph gate passed: %s", args.output)


if __name__ == "__main__":
    main()
