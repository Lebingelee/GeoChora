"""Small process-bound and reporting helpers for the public examples."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import signal
import sys
from typing import Mapping


class RunTimeout(TimeoutError):
    """The example exceeded its wall-clock or CPU budget."""


def bootstrap_imports() -> None:
    """Make direct ``python examples/...`` execution use the checkout APIs."""

    root = Path(__file__).resolve().parents[1]
    for path in (root / "GeoPhys" / "src", root):
        value = str(path)
        if path.is_dir() and value not in sys.path:
            sys.path.insert(0, value)
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"


def _raise_timeout(signum, frame) -> None:
    reason = "CPU time limit reached" if signum == getattr(signal, "SIGXCPU", None) else "wall-clock limit reached"
    raise RunTimeout(reason)


def _virtual_bytes() -> int:
    try:
        pages = int(Path("/proc/self/statm").read_text().split()[0])
        return pages * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError):
        return 0


@contextmanager
def bounded_process(memory_limit_mb: int, time_limit_s: int):
    """Apply Linux-oriented per-process limits for example runs.

    ``RLIMIT_AS`` caps this process's virtual address space. It is neither an
    RSS limit nor an aggregate process-tree memory limit. CPU time is also a
    per-process limit; the real-time alarm bounds the coordinating process.
    """

    if not sys.platform.startswith("linux") or os.name != "posix" or not hasattr(signal, "setitimer"):
        raise RuntimeError("these example limits are supported on Linux with POSIX resource and timer APIs")
    if not 1024 <= memory_limit_mb <= 8192:
        raise ValueError("--memory-limit-mb must be between 1024 and 8192")
    if not 1 <= time_limit_s <= 420:
        raise ValueError("--time-limit-s must be between 1 and 420")

    import resource

    as_soft, as_hard = resource.getrlimit(resource.RLIMIT_AS)
    requested = memory_limit_mb * 1024 * 1024
    as_limit = min(requested, as_soft) if as_soft != resource.RLIM_INFINITY else requested
    if as_hard != resource.RLIM_INFINITY:
        as_limit = min(as_limit, as_hard)
    if _virtual_bytes() >= as_limit:
        raise RuntimeError("current process virtual memory already exceeds the requested address-space limit")

    cpu_soft, cpu_hard = resource.getrlimit(resource.RLIMIT_CPU)
    cpu_limit = min(time_limit_s, cpu_soft) if cpu_soft != resource.RLIM_INFINITY else time_limit_s
    if cpu_hard != resource.RLIM_INFINITY:
        cpu_limit = min(cpu_limit, cpu_hard)
    old_alarm = signal.getsignal(signal.SIGALRM)
    old_xcpu = signal.getsignal(signal.SIGXCPU) if hasattr(signal, "SIGXCPU") else None
    old_timer = signal.getitimer(signal.ITIMER_REAL)
    resource.setrlimit(resource.RLIMIT_AS, (as_limit, as_hard))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_hard))
    signal.signal(signal.SIGALRM, _raise_timeout)
    if hasattr(signal, "SIGXCPU"):
        signal.signal(signal.SIGXCPU, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, float(time_limit_s))
    try:
        yield {"address_space_limit_bytes": as_limit, "address_space_limit_scope": "single_process_rlimit_as",
               "cpu_limit_s": cpu_limit, "cpu_limit_scope": "single_process_rlimit_cpu",
               "wall_limit_s": time_limit_s, "wall_limit_scope": "coordinating_process_alarm",
               "native_threads": 1}
    finally:
        signal.setitimer(signal.ITIMER_REAL, *old_timer)
        signal.signal(signal.SIGALRM, old_alarm)
        if old_xcpu is not None:
            signal.signal(signal.SIGXCPU, old_xcpu)
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_soft, cpu_hard))
        resource.setrlimit(resource.RLIMIT_AS, (as_soft, as_hard))


def run_expert(env, *, seed: int, horizon: int, already_reset: bool = False,
               initial_info: Mapping | None = None) -> dict:
    """Reset and drive only the selected task-owned expert entry point."""

    if not already_reset:
        _, info = env.reset(seed=seed)
    else:
        info = dict(initial_info or {})
    terminated = truncated = False
    transitions = 0
    while transitions < horizon and not env.solution.done and not env.solution.failed:
        _, _, terminated, truncated, info = env.step_expert()
        transitions += 1
        if terminated or truncated:
            break
    if transitions >= horizon and not env.solution.done and not env.solution.failed:
        truncated = True
    return episode_result(env, info=info, transitions=transitions,
                          terminated=terminated, truncated=truncated)


def episode_result(env, *, info: Mapping | None = None, transitions: int,
                   terminated: bool = False,
                   truncated: bool = False) -> dict:
    """Keep physical task outcome and expert lifecycle as separate fields."""

    info = dict(info or {})
    metrics = dict(info.get("task_metrics", {}))
    solution = env.solution
    outcome = solution.outcome_report() if callable(getattr(solution, "outcome_report", None)) else {}
    task_success = bool(metrics.get("task_success", info.get("is_success", False)))
    solution_done = bool(solution.done)
    solution_failed = bool(solution.failed)
    planned = outcome.get("planned_trajectory_completed", info.get("planned_trajectory_completed"))
    outcome_complete = outcome.get("outcome_complete", info.get("outcome_complete"))
    override = outcome.get("unapproved_override_used", info.get("unapproved_override_used"))
    strict_lifecycle = outcome.get(
        "original_expert_lifecycle_status", info.get("original_expert_lifecycle_status")
    )
    expert_complete = outcome.get("expert_complete", info.get("expert_complete"))
    if expert_complete is None and isinstance(strict_lifecycle, dict):
        expert_complete = strict_lifecycle.get("expert_complete")
    if expert_complete is None:
        expert_complete = solution_done and not solution_failed
    physical_complete = task_success and not bool(info.get("task_failure", False))
    if outcome_complete is None:
        complete = physical_complete and solution_done and not solution_failed
        completion_basis = "selected_expert_completion"
    else:
        complete = bool(physical_complete and solution_done and not solution_failed
                        and planned is True and outcome_complete is True and override is False)
        completion_basis = "outcome_policy_and_full_planned_route"
    if terminated or truncated:
        complete = False
    return {
        "status": "PASS" if complete else "FAIL",
        "completion_basis": completion_basis,
        "task_success": task_success,
        "expert_complete": bool(expert_complete),
        "solution_done": solution_done,
        "solution_failed": solution_failed,
        "planned_trajectory_completed": planned,
        "outcome_complete": outcome_complete,
        "unapproved_override_used": override,
        "original_expert_lifecycle_status": strict_lifecycle,
        "readiness_warnings": info.get("readiness_warnings", outcome.get("readiness_warnings", [])),
        "task_failure": bool(info.get("task_failure", False)),
        "terminated": bool(terminated),
        "truncated": bool(truncated),
        "transitions": int(transitions),
        "failure_reason": solution.failure_reason or (None if complete else "task_or_expert_incomplete"),
        "task_metrics": metrics,
    }


def identity_summary(env, *, provider: str) -> dict:
    metadata = dict(getattr(env, "metadata", {}) or {})
    return {
        "env_id": metadata.get("env_id"),
        "provider": provider,
        "backend": "cpu",
        "task_artifact_sha256": metadata.get("task_artifact_hash"),
        "construction_id": metadata.get("construction_id"),
        "control_dt": metadata.get("control_dt"),
    }


def load_recording_summary(path: Path) -> dict:
    """Load and validate the current recorder schema, then check T/T+1."""

    import h5py

    with h5py.File(path, "r") as handle:
        canonical_outer = "numeric" in handle and "logical_json" in handle
    if canonical_outer:
        from task_env.trajectory.canonical.h5 import load

        trajectory = load(path)
        transitions = len(trajectory.transitions)
        boundaries = len(trajectory.boundaries)
        metadata = trajectory.metadata.to_mapping()
        schema = trajectory.schema_version
    else:
        from task_env.trajectory.canonical.execution import load

        trajectory = load(path)
        transitions = len(trajectory["transitions"])
        boundaries = len(trajectory["boundaries"])
        metadata = trajectory["metadata"]
        schema = trajectory["schema"]
    provenance = metadata.get("source_provenance", {})
    valid_counts = boundaries == transitions + 1
    source_hash_count = sum(str(key).startswith("source_sha256:") for key in provenance)
    return {
        "schema": schema,
        "transitions": transitions,
        "boundaries": boundaries,
        "t_plus_one_valid": valid_counts,
        "task_artifact_sha256": metadata.get("task_artifact_hash"),
        "controller_identity": metadata.get("controller_identity"),
        "expert_identity": metadata.get("expert_identity"),
        "provider_provenance_present": bool(metadata.get("provider_provenance")),
        "source_provenance_present": bool(provenance),
        "source_revision": provenance.get("geochora_revision"),
        "resolved_configuration_identity": provenance.get("construction"),
        "source_file_sha256_count": source_hash_count,
        "storage_roundtrip": "PASS" if valid_counts else "FAIL",
        "qualification": "NOT_ASSESSED",
        "D0": "NOT_ASSESSED",
    }
