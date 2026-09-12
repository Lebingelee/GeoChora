"""Stage 17 分层 TaskEnv 性能 profile。

该诊断固定记录可复现的 construction/reset/physics/transition profile，不改变
solver 或 task 语义。CUDA 模式同时记录显式同步后的 wall-clock 与 CUDA event
样本。真实 learner update 属于外部阶段：除非 manifest 另行提供 PPO 命令，本工具
明确记录该阶段未测量。

Example::

    PYTHONPATH=GeoPhys/src:. python -m task_env.diagnostics.runtime.stage17_performance_profile \
        --backend cuda --num-envs 1024 4096 8192 \
        --output-dir temp_outputs/task_env/stage17_empty
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from importlib import metadata as importlib_metadata
import json
import locale
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
from typing import Any

import numpy as np

from task_env.utils._device_stack import get_device_stack_provenance, preload_device_stack

from ...utils._paths import REPO_ROOT
PROFILE_SCHEMA = "task-env-stage17-performance-profile-v1"


def _subprocess_text_encoding() -> str:
    if hasattr(locale, "getencoding"):
        return locale.getencoding()
    if os.name == "nt":
        return "mbcs"
    return locale.getpreferredencoding(False)


def _git_value(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value or None


def _git_dirty() -> bool | None:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return bool(result.stdout.strip())


def _distribution_version(*names: str) -> str | None:
    for name in names:
        try:
            return str(importlib_metadata.version(name))
        except importlib_metadata.PackageNotFoundError:
            continue
    return None


def _runtime_versions() -> dict[str, str | None]:
    return {
        "python": platform.python_version(),
        "torch": _distribution_version("torch"),
        "taichi": _distribution_version("taichi", "taichi-forge"),
        "tensordict": _distribution_version("tensordict"),
        "numpy": _distribution_version("numpy"),
        "triton": _distribution_version("triton", "triton-windows"),
    }


def _gpu_snapshot() -> list[dict[str, Any]]:
    """低频读取外部利用率快照，不进入 simulation hot path。"""

    query = "index,utilization.gpu,memory.used,memory.total"
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                f"--query-gpu={query}",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding=_subprocess_text_encoding(),
            errors="replace",
            timeout=3.0,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    rows: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        values = [item.strip() for item in line.split(",")]
        if len(values) != 4:
            continue
        try:
            rows.append(
                {
                    "index": int(values[0]),
                    "utilization_gpu_percent": float(values[1]),
                    "memory_used_mib": float(values[2]),
                    "memory_total_mib": float(values[3]),
                }
            )
        except ValueError:
            continue
    return rows


def _gpu_compute_processes() -> list[dict[str, Any]]:
    """低频记录 GPU compute process，用于 occupied manifest 的可审计证据。"""

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,process_name,used_memory",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding=_subprocess_text_encoding(),
            errors="replace",
            timeout=3.0,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    rows: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        values = [item.strip() for item in line.split(",", 2)]
        if len(values) != 3:
            continue
        try:
            rows.append(
                {
                    "pid": int(values[0]),
                    "process_name": values[1],
                    "memory_used_mib": float(values[2]),
                }
            )
        except ValueError:
            continue
    return rows


def _external_gpu_compute_processes(
    processes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """排除本次 profiler，保留可归因于外部训练/服务的 compute process。"""

    current_pid = os.getpid()
    return [row for row in processes if int(row.get("pid", -1)) != current_pid]


def _torch_fingerprint(backend: str) -> dict[str, Any]:
    try:
        import torch
    except ModuleNotFoundError:
        return {"available": False}
    payload: dict[str, Any] = {
        "available": True,
        "version": str(torch.__version__),
        "cuda_build": getattr(torch.version, "cuda", None),
        "cuda_available": bool(torch.cuda.is_available()),
    }
    if backend == "cuda" and torch.cuda.is_available():
        payload["device_count"] = int(torch.cuda.device_count())
        payload["device_names"] = [
            str(torch.cuda.get_device_name(index)) for index in range(torch.cuda.device_count())
        ]
    return payload


def _fingerprint(backend: str) -> dict[str, Any]:
    git_commit = _git_value("rev-parse", "HEAD")
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "pid": os.getpid(),
        "git_commit": git_commit,
        "git_branch": _git_value("branch", "--show-current"),
        "source_identity": {
            "git_commit": git_commit,
            "git_tree": _git_value("rev-parse", "HEAD^{tree}"),
            "git_dirty": _git_dirty(),
        },
        "python_executable": str(Path(sys.executable).resolve()),
        "cwd": str(Path.cwd().resolve()),
        "runtime_versions": _runtime_versions(),
        "torch": _torch_fingerprint(backend),
    }


def _synchronise(device: Any) -> None:
    if device is None:
        return
    try:
        import torch

        if getattr(device, "type", None) == "cuda":
            torch.cuda.synchronize(device)
    except (ModuleNotFoundError, RuntimeError):
        return


def _device_memory_snapshot(device: Any, *, reset_peak: bool = False) -> dict[str, Any]:
    """读取可用的 CUDA 分配/保留/峰值显存；CPU 模式返回未测量。"""

    if device is None or getattr(device, "type", None) != "cuda":
        return {"status": "not_measured", "reason": "CUDA device unavailable"}
    try:
        import torch

        if reset_peak:
            torch.cuda.reset_peak_memory_stats(device)
        return {
            "status": "measured",
            "allocated_bytes": int(torch.cuda.memory_allocated(device)),
            "reserved_bytes": int(torch.cuda.memory_reserved(device)),
            "peak_allocated_bytes": int(torch.cuda.max_memory_allocated(device)),
            "peak_reserved_bytes": int(torch.cuda.max_memory_reserved(device)),
        }
    except (ModuleNotFoundError, RuntimeError) as exc:
        return {"status": "not_measured", "reason": type(exc).__name__}


def _measure(fn: Callable[[], Any], device: Any) -> dict[str, float | None]:
    """测量一个显式同步的样本。

    这里的同步是有意的，因为这是诊断边界，不会进入正常 TaskEnv transition 路径。
    """

    _synchronise(device)
    cuda_start = cuda_end = None
    try:
        import torch

        if device is not None and getattr(device, "type", None) == "cuda":
            cuda_start = torch.cuda.Event(enable_timing=True)
            cuda_end = torch.cuda.Event(enable_timing=True)
            cuda_start.record(torch.cuda.current_stream(device))
    except (ModuleNotFoundError, RuntimeError):
        cuda_start = cuda_end = None
    started = time.perf_counter()
    fn()
    if cuda_end is not None:
        cuda_end.record(torch.cuda.current_stream(device))
    _synchronise(device)
    wall_ms = (time.perf_counter() - started) * 1000.0
    cuda_ms = None if cuda_start is None or cuda_end is None else float(cuda_start.elapsed_time(cuda_end))
    return {"wall_ms": wall_ms, "cuda_event_ms": cuda_ms}


class _ProfileCollector:
    """仅在 Stage 17 诊断挂载的非侵入式分段计时器。"""

    def __init__(self, device: Any) -> None:
        self.device = device
        self._active: dict[str, dict[str, Any]] = {}
        self._completed: dict[str, list[dict[str, Any]]] = {}
        self._samples: list[dict[str, list[dict[str, Any]]]] = []
        self._sampling = False

    def clear(self) -> None:
        self._active.clear()
        self._completed.clear()
        self._samples.clear()
        self._sampling = False

    def begin_sample(self) -> None:
        if self._active or self._completed:
            raise RuntimeError("profile sample started while another sample is active")
        self._active.clear()
        self._completed.clear()
        self._sampling = True

    def finish_sample(self) -> None:
        if self._active:
            self._completed.update(
                {
                    name: [*self._completed.get(name, []), span]
                    for name, span in self._active.items()
                }
            )
        if self._completed:
            self._samples.append(
                {name: list(spans) for name, spans in self._completed.items()}
            )
        self._active.clear()
        self._completed.clear()
        self._sampling = False

    def begin(self, name: str) -> None:
        if not self._sampling:
            return
        key = str(name)
        if key in self._active:
            raise RuntimeError(f"profile span {key!r} is already active")
        cuda_start = None
        try:
            import torch

            if self.device is not None and getattr(self.device, "type", None) == "cuda":
                cuda_start = torch.cuda.Event(enable_timing=True)
                cuda_start.record(torch.cuda.current_stream(self.device))
        except (ModuleNotFoundError, RuntimeError):
            cuda_start = None
        self._active[key] = {
            "wall_started": time.perf_counter(),
            "cuda_start": cuda_start,
            "cuda_end": None,
        }

    def end(self, name: str) -> None:
        if not self._sampling:
            return
        key = str(name)
        span = self._active.pop(key, None)
        if span is None:
            return
        cuda_start = span.get("cuda_start")
        if cuda_start is not None:
            try:
                import torch

                cuda_end = torch.cuda.Event(enable_timing=True)
                cuda_end.record(torch.cuda.current_stream(self.device))
                span["cuda_end"] = cuda_end
            except (ModuleNotFoundError, RuntimeError):
                span["cuda_end"] = None
        span["wall_finished"] = time.perf_counter()
        self._completed.setdefault(key, []).append(span)

    def summaries(self) -> dict[str, dict[str, Any]]:
        by_name: dict[str, list[dict[str, float | None]]] = {}
        for sample in self._samples:
            for name, spans in sample.items():
                wall_ms = sum(
                    (float(span["wall_finished"]) - float(span["wall_started"])) * 1000.0
                    for span in spans
                )
                cuda_events = [
                    span["cuda_start"].elapsed_time(span["cuda_end"])
                    for span in spans
                    if span.get("cuda_start") is not None and span.get("cuda_end") is not None
                ]
                by_name.setdefault(name, []).append(
                    {
                        "wall_ms": wall_ms,
                        "cuda_event_ms": float(sum(cuda_events)) if cuda_events else None,
                    }
                )
        return {name: _summary(samples) for name, samples in sorted(by_name.items())}


def _summary(samples: list[dict[str, float | None]], *, derived: bool = False) -> dict[str, Any]:
    if not samples:
        return {"status": "not_measured", "samples": 0, "derived": bool(derived)}

    def values(name: str) -> list[float]:
        return [float(sample[name]) for sample in samples if sample.get(name) is not None]

    result: dict[str, Any] = {
        "status": "measured",
        "samples": len(samples),
        "derived": bool(derived),
    }
    for name in ("wall_ms", "cuda_event_ms"):
        selected = values(name)
        if not selected:
            result[name] = None
            continue
        result[name] = {
            "mean": float(statistics.fmean(selected)),
            "p50": float(np.percentile(selected, 50)),
            "p95": float(np.percentile(selected, 95)),
            "min": float(min(selected)),
            "max": float(max(selected)),
        }
    result["raw_samples"] = samples
    return result


def _phase(
    fn: Callable[[], Any],
    *,
    device: Any,
    warmup: int,
    samples: int,
    collector: _ProfileCollector | None = None,
) -> dict[str, Any]:
    if collector is not None:
        collector.clear()
    for _ in range(max(0, int(warmup))):
        fn()

    def measured_fn() -> Any:
        if collector is not None:
            collector.begin_sample()
        try:
            return fn()
        finally:
            if collector is not None:
                collector.finish_sample()

    measured = [_measure(measured_fn, device) for _ in range(max(1, int(samples)))]
    result = _summary(measured)
    if collector is not None:
        result["subphases"] = collector.summaries()
    return result


def _derived_bridge(total: Mapping[str, Any], physics: Mapping[str, Any]) -> dict[str, Any]:
    total_samples = list(total.get("raw_samples", ()))
    physics_samples = list(physics.get("raw_samples", ()))
    count = min(len(total_samples), len(physics_samples))
    samples = [
        {
            "wall_ms": max(
                0.0,
                float(total_samples[index].get("wall_ms", 0.0))
                - float(physics_samples[index].get("wall_ms", 0.0)),
            ),
            "cuda_event_ms": (
                None
                if total_samples[index].get("cuda_event_ms") is None
                or physics_samples[index].get("cuda_event_ms") is None
                else max(
                    0.0,
                    float(total_samples[index]["cuda_event_ms"])
                    - float(physics_samples[index]["cuda_event_ms"]),
                )
            ),
        }
        for index in range(count)
    ]
    result = _summary(samples, derived=True)
    result["method"] = "paired total device transition minus direct runtime physics"
    return result


_SOLVER_SUBPHASES = (
    "dynamics",
    "geom_fk",
    "contact_candidate",
    "row_pgs_response",
    "integration",
)
_TASK_SUBPHASES = ("task_observation", "task_evaluation")
_BRIDGE_SUBPHASES = ("bridge_input", "bridge_output")


def _raw_subphase_values(
    subphases: Mapping[str, Any],
    names: tuple[str, ...],
    *,
    count: int,
) -> list[dict[str, float | None]]:
    """按 public tick 对齐并求和分段样本；缺失子项按零计入。"""

    values: list[dict[str, float | None]] = []
    for index in range(count):
        wall = 0.0
        cuda = 0.0
        has_cuda = True
        for name in names:
            raw = list(subphases.get(name, {}).get("raw_samples", ()))
            if index >= len(raw):
                continue
            wall += float(raw[index].get("wall_ms", 0.0) or 0.0)
            event = raw[index].get("cuda_event_ms")
            if event is None:
                has_cuda = False
            else:
                cuda += float(event)
        values.append(
            {
                "wall_ms": wall,
                "cuda_event_ms": cuda if has_cuda else None,
            }
        )
    return values


def _component_attribution(
    device_transition: Mapping[str, Any],
) -> dict[str, Any]:
    """将完整 public device tick 归因到 solver/task/bridge 三个边界。"""

    subphases = device_transition.get("subphases")
    tick_samples = list(device_transition.get("raw_samples", ()))
    if not isinstance(subphases, Mapping) or not tick_samples:
        return {
            "status": "not_measured",
            "reason": "runtime/task segment collector is unavailable for this layout",
            "equation": "T_tick = T_solver + T_task + T_bridge",
        }

    count = len(tick_samples)
    solver_samples = _raw_subphase_values(subphases, _SOLVER_SUBPHASES, count=count)
    task_samples = _raw_subphase_values(subphases, _TASK_SUBPHASES, count=count)
    bridge_only_samples = _raw_subphase_values(subphases, _BRIDGE_SUBPHASES, count=count)
    bridge_samples: list[dict[str, float | None]] = []
    for index, tick in enumerate(tick_samples):
        tick_wall = float(tick.get("wall_ms", 0.0) or 0.0)
        known_wall = (
            float(solver_samples[index]["wall_ms"] or 0.0)
            + float(task_samples[index]["wall_ms"] or 0.0)
            + float(bridge_only_samples[index]["wall_ms"] or 0.0)
        )
        wall_residual = max(0.0, tick_wall - known_wall)
        tick_cuda = tick.get("cuda_event_ms")
        cuda_residual = None
        if tick_cuda is not None:
            known_cuda = sum(
                float(sample["cuda_event_ms"] or 0.0)
                for sample in (solver_samples[index], task_samples[index], bridge_only_samples[index])
                if sample.get("cuda_event_ms") is not None
            )
            cuda_residual = max(0.0, float(tick_cuda) - known_cuda)
        bridge_samples.append(
            {
                "wall_ms": float(bridge_only_samples[index]["wall_ms"] or 0.0) + wall_residual,
                "cuda_event_ms": (
                    None
                    if cuda_residual is None or bridge_only_samples[index].get("cuda_event_ms") is None
                    else float(bridge_only_samples[index]["cuda_event_ms"] or 0.0) + cuda_residual
                ),
            }
        )

    components = {
        "T_solver": _summary(solver_samples, derived=True),
        "T_task": _summary(task_samples, derived=True),
        "T_bridge": _summary(bridge_samples, derived=True),
    }
    tick_p50 = float(device_transition.get("wall_ms", {}).get("p50", 0.0) or 0.0)
    for component in components.values():
        p50 = component.get("wall_ms", {}).get("p50")
        component["share_of_tick_p50"] = None if not tick_p50 else float(p50) / tick_p50
    return {
        "status": "measured",
        "equation": "T_tick = T_solver + T_task + T_bridge",
        "method": "paired public device transition spans; residual lifecycle time assigned to T_bridge",
        "components": components,
        "solver_subphases": {
            name: dict(subphases.get(name, {"status": "not_measured", "reason": "phase not present"}))
            for name in _SOLVER_SUBPHASES
        },
        "task_subphases": {
            name: dict(subphases.get(name, {"status": "not_measured", "reason": "phase not present"}))
            for name in _TASK_SUBPHASES
        },
        "bridge_subphases": {
            name: dict(subphases.get(name, {"status": "not_measured", "reason": "phase not present"}))
            for name in _BRIDGE_SUBPHASES
        },
    }


def _resolve_device(plan: Mapping[str, Any], backend: str) -> Any:
    if not bool(plan.get("available")):
        return None
    try:
        import torch
    except ModuleNotFoundError:
        return None
    value = plan.get("device") or ("cuda:0" if backend == "cuda" else "cpu")
    try:
        return torch.device(str(value))
    except RuntimeError:
        return None


def _env_config(args: argparse.Namespace) -> dict[str, Any]:
    candidate = str(args.contact_candidate)
    runtime: dict[str, Any] = {
        "backend": str(args.backend),
        "prewarm": False,
        "batch_physics_layout": str(args.layout),
    }
    if args.layout == "static_template":
        runtime["static_template"] = {
            "profile": str(args.profile),
            "kinematics_backend": str(args.kinematics_backend),
            "contact_precision": str(args.contact_precision),
            "cuda_graph": str(args.backend) == "cuda",
            "contact": {
                "response_backend": "active_slot_cholesky_f32_v1",
                "fixed_topology_child_schur": candidate in {"p1", "p12"},
                "root_factor_6x6": candidate == "p12",
            },
        }
        runtime["enable_ground_contact"] = args.profile == "articulated_fused_ground_contact_v1"
        runtime["enable_domain_boundary_contact"] = False
    return {"base_seed": int(args.seed), "runtime": runtime}


def _build_spec(args: argparse.Namespace, batch: int):
    import importlib

    importlib.import_module("task_env.tasks")
    from task_env.vectorization.factory import make_framework_parallel_spec

    return make_framework_parallel_spec(
        uid=str(args.task_uid),
        num_env=int(batch),
        env_config=_env_config(args),
        backend=str(args.backend),
    )


def _profile_case(args: argparse.Namespace, batch: int) -> dict[str, Any]:
    construction_started = time.perf_counter()
    spec = _build_spec(args, batch)
    construction_device = None
    if str(args.backend) == "cuda":
        try:
            import torch

            construction_device = torch.device("cuda:0")
        except (ModuleNotFoundError, RuntimeError):
            construction_device = None
    _synchronise(construction_device)
    construction_ms = (time.perf_counter() - construction_started) * 1000.0
    try:
        plan = spec.device_field_plan.as_dict()
        device = _resolve_device(plan, args.backend)
        collector = _ProfileCollector(device)
        set_collector = getattr(spec, "set_profile_collector", None)
        if callable(set_collector):
            set_collector(collector)
        memory_before = _device_memory_snapshot(device, reset_peak=True)
        action_space = spec.single_action_space
        if not hasattr(action_space, "shape"):
            raise RuntimeError("Stage 17 currently requires a flat Box action space")
        action = np.zeros((batch, *tuple(action_space.shape)), dtype=np.float32)
        action_device = None
        if device is not None:
            import torch

            action_device = torch.as_tensor(action, dtype=torch.float32, device=device)

        phases: dict[str, Any] = {
            "construction": {
                "status": "measured",
                "samples": 1,
                "derived": False,
                "wall_ms": {
                    "mean": construction_ms,
                    "p50": construction_ms,
                    "p95": construction_ms,
                    "min": construction_ms,
                    "max": construction_ms,
                },
                "cuda_event_ms": None,
                "raw_samples": [{"wall_ms": construction_ms, "cuda_event_ms": None}],
            }
        }
        prewarm = getattr(spec.runtime, "prewarm", None)
        if callable(prewarm):
            phases["prewarm"] = _phase(
                lambda: prewarm(profile="benchmark_full"),
                device=device,
                warmup=0,
                samples=1,
            )
        else:
            phases["prewarm"] = {"status": "not_available", "reason": "runtime.prewarm is unavailable"}

        phases["reset"] = _phase(
            lambda: spec.reset(seed=int(args.seed)),
            device=device,
            warmup=0,
            samples=max(1, min(3, int(args.steps))),
        )

        if bool(plan.get("available")) and action_device is not None:
            runtime = spec.runtime
            state_before = spec.read_device_state(tuple(plan["state_readback_fields"]))
            converter = getattr(spec.action_adapter, "convert_device_batch", None)
            if not callable(converter):
                raise RuntimeError("device field plan claimed availability without a device action converter")
            control = converter(action_device, state_before)
            phases["physics"] = _phase(
                lambda: runtime.step_device(control),
                device=device,
                warmup=args.warmup,
                samples=args.steps,
                collector=collector,
            )
            # 测量完整公共 device transition 前恢复 task/runtime 状态；direct physics
            # probe 会绕过 task bookkeeping，不与该阶段混合。
            spec.reset(seed=int(args.seed))
            phases["device_transition"] = _phase(
                lambda: spec.step_device(action_device),
                device=device,
                warmup=args.warmup,
                samples=args.steps,
                collector=collector,
            )
            phases["task_device_bridge"] = _derived_bridge(
                phases["device_transition"], phases["physics"]
            )
            phases["attribution"] = _component_attribution(
                phases["device_transition"]
            )
        else:
            phases["physics"] = {
                "status": "not_measured",
                "reason": "device capability unavailable",
            }
            phases["device_transition"] = {
                "status": "not_measured",
                "reason": "device capability unavailable",
            }
            phases["task_device_bridge"] = {
                "status": "not_measured",
                "reason": "device capability unavailable",
            }
            phases["attribution"] = {
                "status": "not_measured",
                "reason": "device capability unavailable",
                "equation": "T_tick = T_solver + T_task + T_bridge",
            }

        if bool(args.include_host):
            spec.reset(seed=int(args.seed))
            phases["host_transition"] = _phase(
                lambda: spec.step(action),
                device=None,
                warmup=args.warmup,
                samples=args.steps,
            )
        else:
            phases["host_transition"] = {
                "status": "not_measured",
                "reason": "pass --include-host to include the compatibility path",
            }

        phases["learner_update"] = {
            "status": "not_measured",
            "reason": "real PPO learner timing is supplied by the Stage 21 training artifact",
            "external_command": "task_env.script.rl.rsl_ppo",
        }
        phases["ppo_iteration"] = {
            "status": "not_measured",
            "reason": "Stage 17 does not launch a learner from the physics profile process",
        }
        phases["artifact_logging"] = {
            "status": "not_measured",
            "reason": "H5/TensorBoard logging is intentionally outside the physics profile process",
        }
        summary = spec.resource_summary()
        memory_after = _device_memory_snapshot(device)
        return {
            "num_envs": int(batch),
            "backend": str(args.backend),
            "layout": str(args.layout),
            "profile": str(args.profile),
            "kinematics_backend": (
                str(args.kinematics_backend)
                if args.layout == "static_template"
                else "not_applicable"
            ),
            "contact_precision": (
                str(args.contact_precision)
                if args.layout == "static_template"
                else "not_applicable"
            ),
            "contact_candidate": str(args.contact_candidate),
            "device_field_plan": plan,
            "resource_summary": summary,
            "benchmark_facts": {
                "template_digest": summary.get("template_digest"),
                "control_substeps": summary.get("control_substeps"),
                "physics_intermediate_dtype": summary.get("contact_solve_intermediate_dtype"),
                "synchronization": "explicit only at diagnostic phase boundaries",
                "kernel_trace": "not enabled; use Nsight separately for launch-level attribution",
            },
            "device_memory": {"before": memory_before, "after": memory_after},
            "phases": phases,
        }
    finally:
        spec.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-uid", default="go2-walk-v1")
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--layout", choices=("merged_scene", "static_template"), default="static_template")
    parser.add_argument(
        "--profile",
        choices=(
            "articulated_fused_no_contact_v1",
            "articulated_fused_ground_contact_v1",
            "articulated_ground_contact_v1",
        ),
        default="articulated_fused_ground_contact_v1",
    )
    parser.add_argument(
        "--contact-precision",
        choices=("f64", "f32"),
        default="f64",
    )
    parser.add_argument(
        "--kinematics-backend",
        choices=("torch", "taichi"),
        default="torch",
        help="FK/geom backend for the static fused runtime; Taichi is an explicit A/B path",
    )
    parser.add_argument(
        "--contact-candidate",
        choices=("p0", "p1", "p12"),
        default="p12",
        help="diagnostic candidate selected before environment construction",
    )
    parser.add_argument("--num-envs", type=int, nargs="+", default=(1,))
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--seed", type=int, default=73)
    parser.add_argument(
        "--load-label",
        choices=("idle", "current_training_occupied"),
        default="idle",
        help="标记本次 profile 的系统负载；occupied 需在真实训练进程运行时执行",
    )
    parser.add_argument("--include-host", action="store_true")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("temp_outputs/task_env/stage17_profile"),
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if any(int(batch) < 1 for batch in args.num_envs):
        raise ValueError("--num-envs values must be positive")
    if int(args.warmup) < 0 or int(args.steps) < 1:
        raise ValueError("--warmup must be non-negative and --steps must be positive")
    if args.layout != "static_template" and args.profile != "articulated_fused_ground_contact_v1":
        # merged_scene 不消费该 profile；保留稳定的 manifest 值，但不暗示它选择了
        # 某个具体 runtime。
        args.profile = "articulated_fused_ground_contact_v1"
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    # Importing the public TaskEnv contract currently loads the runtime
    # package, which may already have completed the process-level bootstrap.
    # Reuse that immutable record instead of issuing a conflicting CPU/CUDA
    # request from the diagnostic itself.
    preload = get_device_stack_provenance()
    if preload is None:
        # Static TaskEnv construction calls the public preload contract with
        # Triton requested even on CPU.  Match that process-level fingerprint
        # so the diagnostic does not reject its own construction request.
        request_triton = (
            str(args.backend) == "cuda"
            or str(args.layout) == "static_template"
        )
        preload = preload_device_stack(request_triton=request_triton)
    process_before = _gpu_compute_processes()
    report = {
        "schema": PROFILE_SCHEMA,
        "status": f"measured_{args.load_label}_profile",
        "manifest": {
            "task_uid": str(args.task_uid),
            "backend": str(args.backend),
            "layout": str(args.layout),
            "profile": str(args.profile),
            "kinematics_backend": (
                str(args.kinematics_backend)
                if args.layout == "static_template"
                else "not_applicable"
            ),
            "contact_precision": (
                str(args.contact_precision)
                if args.layout == "static_template"
                else "not_applicable"
            ),
            "contact_candidate": str(args.contact_candidate),
            "num_envs": [int(value) for value in args.num_envs],
            "seed": int(args.seed),
            "warmup_steps": int(args.warmup),
            "steady_state_steps": int(args.steps),
            "include_host": bool(args.include_host),
            "load_label": str(args.load_label),
            "load_label_policy": (
                "caller must run this exact command while the current training process is active"
                if args.load_label == "current_training_occupied"
                else "nvidia-smi snapshots must show no training process"
            ),
            "construction_samples": 1,
            "learner_update": "not_measured_in_physics_profile",
            "artifact_logging": "not_measured_in_physics_profile",
            "wall_clock": "time.perf_counter with explicit device synchronization",
            "cuda_clock": "torch.cuda.Event when backend=cuda and available",
            "kernel_trace": "not enabled; synchronize boundaries and CUDA events are recorded",
            "gpu_snapshots": {
                "before": _gpu_snapshot(),
                "compute_processes_before": process_before,
                "external_compute_processes_before": _external_gpu_compute_processes(process_before),
                "benchmark_pid": os.getpid(),
            },
            "fingerprint": _fingerprint(str(args.backend)),
            "device_stack_preload": preload.to_dict(),
        },
        "cases": [],
    }
    for batch in args.num_envs:
        report["cases"].append(_profile_case(args, int(batch)))
    process_after = _gpu_compute_processes()
    report["manifest"]["gpu_snapshots"]["after"] = _gpu_snapshot()
    report["manifest"]["gpu_snapshots"]["compute_processes_after"] = process_after
    report["manifest"]["gpu_snapshots"]["external_compute_processes_after"] = (
        _external_gpu_compute_processes(process_after)
    )
    report_path = output_dir / "stage17_profile.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    try:
        from task_env.utils.runtime_support import get_task_env_logger

        logger = get_task_env_logger("simulation", module="task-env-stage17-profile")
        logger.success(
            "Stage 17 layered performance profile written",
            output=str(report_path),
            cases=len(report["cases"]),
            status=report["status"],
        )
    except Exception:
        # 即使独立运行时没有可选 test logger，诊断仍必须保留 artifact。
        pass


if __name__ == "__main__":
    main()
