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
    configured_geophys = os.environ.get("GEOCHORA_GEOPHYS_SRC")
    geophys_src = (Path(configured_geophys).expanduser().resolve()
                   if configured_geophys else root / "GeoPhys" / "src")
    if configured_geophys and not (geophys_src / "scene" / "__init__.py").is_file():
        raise ValueError(f"GEOCHORA_GEOPHYS_SRC must point to a GeoPhys src directory: {geophys_src}")
    loaded_scene = sys.modules.get("scene")
    if configured_geophys and loaded_scene is not None:
        origin = getattr(loaded_scene, "__file__", None)
        if origin is None or not Path(origin).resolve().is_relative_to(geophys_src):
            raise RuntimeError("scene was already imported outside GEOCHORA_GEOPHYS_SRC; start a fresh interpreter")
    for path in (geophys_src, root):
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
def bounded_process(memory_limit_mb: int, time_limit_s: int, *, limit_address_space: bool = True):
    """Apply Linux-oriented per-process limits for example runs.

    When enabled, ``RLIMIT_AS`` caps virtual address space and is inherited by
    child processes. It is neither an RSS nor an aggregate process-tree cap.
    CPU time is per process; the real-time alarm bounds the coordinator.
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
    if limit_address_space and _virtual_bytes() >= as_limit:
        raise RuntimeError("current process virtual memory already exceeds the requested address-space limit")

    cpu_soft, cpu_hard = resource.getrlimit(resource.RLIMIT_CPU)
    cpu_limit = min(time_limit_s, cpu_soft) if cpu_soft != resource.RLIM_INFINITY else time_limit_s
    if cpu_hard != resource.RLIM_INFINITY:
        cpu_limit = min(cpu_limit, cpu_hard)
    old_alarm = signal.getsignal(signal.SIGALRM)
    old_xcpu = signal.getsignal(signal.SIGXCPU) if hasattr(signal, "SIGXCPU") else None
    old_timer = signal.getitimer(signal.ITIMER_REAL)
    if limit_address_space:
        resource.setrlimit(resource.RLIMIT_AS, (as_limit, as_hard))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_hard))
    signal.signal(signal.SIGALRM, _raise_timeout)
    if hasattr(signal, "SIGXCPU"):
        signal.signal(signal.SIGXCPU, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, float(time_limit_s))
    try:
        yield {"address_space_limit_bytes": as_limit if limit_address_space else None,
               "address_space_limit_scope": "single_process_rlimit_as" if limit_address_space else "not_set",
               "cpu_limit_s": cpu_limit, "cpu_limit_scope": "single_process_rlimit_cpu",
               "wall_limit_s": time_limit_s, "wall_limit_scope": "coordinating_process_alarm",
               "native_threads": 1}
    finally:
        signal.setitimer(signal.ITIMER_REAL, *old_timer)
        signal.signal(signal.SIGALRM, old_alarm)
        if old_xcpu is not None:
            signal.signal(signal.SIGXCPU, old_xcpu)
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_soft, cpu_hard))
        if limit_address_space:
            resource.setrlimit(resource.RLIMIT_AS, (as_soft, as_hard))


def run_caller_solution(env, solution, obs, info, *, horizon: int) -> dict:
    """Drive a caller-owned Solution using the public action/observation boundary."""
    terminated = truncated = False
    transitions = 0
    while transitions < horizon and not solution.done and not solution.failed:
        action = solution.act(obs, info)
        obs, reward, terminated, truncated, info = env.step(action)
        solution.observe(obs, reward, terminated, truncated, info)
        transitions += 1
        if terminated or truncated:
            break
    if transitions >= horizon and not solution.done and not solution.failed:
        truncated = True
    return episode_result(env, solution=solution, info=info, transitions=transitions,
                          terminated=terminated, truncated=truncated)


def episode_result(env, *, solution=None, info: Mapping | None = None, transitions: int,
                   terminated: bool = False,
                   truncated: bool = False) -> dict:
    """Keep physical task outcome and expert lifecycle as separate fields."""

    from task_env.script.trajectory.completion import completion_facts

    solution = env.solution if solution is None else solution
    facts = completion_facts(solution, info, terminated=terminated, truncated=truncated)
    return {
        **facts,
        "status": "PASS" if facts["policy_complete"] else "FAIL",
        "transitions": int(transitions),
        "task_metrics": dict((info or {}).get("task_metrics", {})),
    }



def identity_summary(env, *, provider: str) -> dict:
    metadata = dict(getattr(env, "metadata", {}) or {})
    return {
        "env_id": metadata.get("env_id"),
        "provider": provider,
        "backend": getattr(getattr(getattr(env, "config", None), "runtime", None), "backend", None),
        "task_artifact_sha256": metadata.get("task_artifact_hash"),
        "construction_id": metadata.get("construction_id"),
        "control_dt": metadata.get("control_dt"),
    }


def load_recording_summary(path: Path) -> dict:
    """Load and validate the current recorder schema, then check T/T+1."""

    import h5py

    with h5py.File(path, "r") as handle:
        canonical_outer = "numeric" in handle and "logical_json" in handle
        generic_v3 = (
            str(handle.attrs.get("schema_id", "")) == "task-env-h5"
            and str(handle.attrs.get("schema_version", "")) == "v3"
        )
    if canonical_outer:
        from task_env.trajectory.canonical.h5 import load

        trajectory = load(path)
        transitions = len(trajectory.transitions)
        boundaries = len(trajectory.boundaries)
        metadata = trajectory.metadata.to_mapping()
        schema = trajectory.schema_version
    elif generic_v3:
        from task_env.recorders import load_structured_control_records_h5

        trajectory = load_structured_control_records_h5(path)
        transitions = trajectory["transition_count"]
        boundaries = trajectory["observation_count"]
        profile = trajectory["env_meta"].get("reference_profile", {})
        valid_counts = boundaries == transitions + 1
        source_present = bool(
            isinstance(profile, dict) and profile.get("source_id")
            and profile.get("source_closure_digest")
        )
        provider_present = bool(
            isinstance(profile, dict) and profile.get("provider")
            and profile.get("provider_build_identity")
        )
        return {
            "schema": "task-env-h5/v3",
            "transitions": transitions,
            "boundaries": boundaries,
            "t_plus_one_valid": valid_counts,
            "task_artifact_sha256": profile.get("task_artifact_identity_hash"),
            "controller_identity": profile.get("controller_identity"),
            "expert_identity": profile.get("solution_identity"),
            "provider_provenance_present": provider_present,
            "source_provenance_present": source_present,
            "source_revision": None,
            "resolved_configuration_identity": profile.get("execution_identity_sha256"),
            "source_file_sha256_count": 0,
            "storage_roundtrip": "PASS" if valid_counts else "FAIL",
            "qualification": "NOT_ASSESSED",
            "D0": "NOT_ASSESSED",
        }
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
