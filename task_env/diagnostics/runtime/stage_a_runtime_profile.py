"""Stage A: static-template runtime boundary and component profile.

The diagnostic keeps the normal TaskEnv path unchanged and attaches the
existing opt-in collector only for measured samples.  It records CUDA event
time and synchronized host wall time for the fixed local stages, plus the
Torch/Taichi storage boundary provenance.  ``runtime_handoff`` is an
overlapping envelope around Taichi external-ndarray calls; it is intentionally
excluded from the additive stage sum.  Diagnostic child stages may overlap
their named parent and are likewise excluded from that sum.

Example::

    PYTHONPATH=GeoPhys/src:. python -m task_env.diagnostics.runtime.stage_a_runtime_profile \
        --backend cuda --kinematics-backend torch --num-envs 1024 4096 8192
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
from uuid import uuid4

from task_env.utils._device_stack import get_device_stack_provenance
from task_env.utils._device_stack import preload_device_stack

from .stage17_performance_profile import (
    _device_memory_snapshot,
    _external_gpu_compute_processes,
    _fingerprint,
    _gpu_snapshot,
    _measure,
    _phase,
    _resolve_device,
    _synchronise,
)
from .stage17_performance_profile import _ProfileCollector


from ...utils._paths import MUJOCO_MENAGERIE_ROOT, REPO_ROOT
PROFILE_SCHEMA = "task-env-stage-a-runtime-profile-v1"
_ADDITIVE_STAGES = (
    "fk_geom_transform",
    "dense_dynamics",
    "contact_candidate",
    "contact_mass_response",
    "row_pgs",
    "integration",
)
_DIAGNOSTIC_CHILD_STAGES = (
    ("dense_inertia_crb", "dense_dynamics"),
    ("dense_mass_matrix", "dense_dynamics"),
    ("dense_rne_bias", "dense_dynamics"),
    ("dense_passive_actuation", "dense_dynamics"),
    ("dense_qacc_solve", "dense_dynamics"),
    ("dense_velocity_update", "dense_dynamics"),
    ("contact_motion_jacobian", "contact_mass_response"),
    ("contact_precision_rhs_pack", "contact_mass_response"),
    ("contact_factorization", "contact_mass_response"),
    ("contact_linear_solve", "contact_mass_response"),
    ("contact_response_finalize", "contact_mass_response"),
)
_OPTIONAL_STAGES = ("runtime_handoff",)
EVIDENCE_REVISION = "task-env-stage-a-performance-evidence-v2"


class RequiredContactPgsBackendError(RuntimeError):
    """Stage A warm-up did not prove the explicitly required PGS route."""

    def __init__(
        self,
        validation: dict[str, Any],
        mismatches: list[str],
        *,
        validation_field: str = "required_backend_validation",
    ) -> None:
        self.case: dict[str, Any] = {}
        self.validation = validation
        self.mismatches = tuple(mismatches)
        self.validation_field = validation_field
        super().__init__(
            "required contact PGS backend was not qualified after warm-up: "
            + ", ".join(mismatches)
        )


class StageAProfileCaseError(RuntimeError):
    """Carry one partially measured case without obscuring its root error."""

    def __init__(self, case: dict[str, Any], original: Exception) -> None:
        self.case = case
        self.original = original
        super().__init__(str(original))


def _write_report_atomic(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(
                report,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
                default=str,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _invocation(args: argparse.Namespace, argv: list[str] | None) -> dict[str, Any]:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    command_parts = [
        str(sys.executable),
        "-m",
        "task_env.diagnostics.runtime.stage_a_runtime_profile",
        *raw_argv,
    ]
    measurement = {
        "task_uid": str(args.task_uid),
        "backend": str(args.backend),
        "kinematics_backend": str(args.kinematics_backend),
        "profile": str(args.profile),
        "contact_precision": str(args.contact_precision),
        "num_envs": [int(value) for value in args.num_envs],
        "warmup_steps": int(args.warmup),
        "steady_state_steps": int(args.steps),
        "seed": int(args.seed),
        "load_label": str(args.load_label),
    }
    return {
        "command": subprocess.list2cmdline(command_parts),
        "argv": raw_argv,
        "cwd": str(Path.cwd().resolve()),
        "python_executable": str(Path(sys.executable).resolve()),
        "measurement_command": json.dumps(
            measurement, sort_keys=True, separators=(",", ":")
        ),
    }


def _scene_fingerprint(args: argparse.Namespace) -> dict[str, str]:
    payload: dict[str, Any] = {
        "task_uid": str(args.task_uid),
        "profile": str(args.profile),
    }
    if str(args.task_uid) == "go2-walk-v1":
        assets_path = REPO_ROOT / "task_env" / "tasks" / "go2_walk" / "assets.py"
        xml_path = MUJOCO_MENAGERIE_ROOT / "unitree_go2" / "go2.xml"
        payload["canonical_xml_sha256"] = sha256(xml_path.read_bytes()).hexdigest()
        payload["composition_source_sha256"] = sha256(
            assets_path.read_bytes()
        ).hexdigest()
    digest = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {"digest_algorithm": "sha256", "digest": digest}


def _gpu_driver_fingerprint() -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=driver_version,driver_model.current",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=False,
            timeout=3.0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "status": "unavailable",
            "driver_version": None,
            "driver_model_current": None,
            "error_type": type(exc).__name__,
        }
    devices = []
    stdout = (completed.stdout or b"").decode("utf-8", errors="replace")
    for line in stdout.splitlines():
        values = [value.strip() for value in line.split(",", 1)]
        if len(values) == 2 and values[0]:
            devices.append(
                {"driver_version": values[0], "driver_model_current": values[1]}
            )
    if not devices:
        return {
            "status": "unavailable",
            "driver_version": None,
            "driver_model_current": None,
            "error_type": "EmptyQueryResult",
        }
    versions = sorted({str(item["driver_version"]) for item in devices})
    models = sorted({str(item["driver_model_current"]) for item in devices})
    return {
        "status": "measured",
        "driver_version": versions[0] if len(versions) == 1 else versions,
        "driver_model_current": models[0] if len(models) == 1 else models,
        "devices": devices,
    }


def _process_accounting_snapshot() -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,process_name,used_memory",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=False,
            timeout=3.0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "complete": False,
            "processes": [],
            "external_processes": [],
            "error_type": type(exc).__name__,
        }
    processes: list[dict[str, Any]] = []
    stdout = (completed.stdout or b"").decode("utf-8", errors="replace")
    for line in stdout.splitlines():
        values = [value.strip() for value in line.split(",", 2)]
        if len(values) != 3:
            continue
        try:
            processes.append(
                {
                    "pid": int(values[0]),
                    "process_name": values[1],
                    "memory_used_mib": float(values[2]),
                }
            )
        except ValueError:
            return {
                "complete": False,
                "processes": processes,
                "external_processes": _external_gpu_compute_processes(processes),
                "error_type": "UnparseableQueryRow",
            }
    return {
        "complete": True,
        "processes": processes,
        "external_processes": _external_gpu_compute_processes(processes),
        "error_type": None,
    }


def _validate_required_contact_pgs_backend(
    *,
    required: str | None,
    summary: Mapping[str, Any],
    warmup_steps: int,
    validation_field: str = "required_backend_validation",
) -> dict[str, Any]:
    if required is None:
        return {
            "status": "not_requested",
            "point": "after_warmup_before_timed_samples",
            "required": None,
            "warmup_steps_completed": int(warmup_steps),
            "checks": None,
            "mismatches": [],
        }
    checks = {
        "selected": summary.get("contact_pgs_backend_selected") == required,
        "effective": summary.get("contact_pgs_backend_effective") == required,
        "next": summary.get("contact_pgs_backend_next") == required,
        "attempted": summary.get("contact_pgs_fused_attempted") is True,
        "qualified": summary.get("contact_pgs_fused_qualified") is True,
        "failed_closed": summary.get("contact_pgs_failed_closed") is False,
        "fallback": summary.get("contact_pgs_fallback_reason") is None,
    }
    mismatches = [name for name, passed in checks.items() if not passed]
    validation = {
        "status": "passed" if not mismatches else "failed",
        "point": "after_warmup_before_timed_samples",
        "required": required,
        "warmup_steps_completed": int(warmup_steps),
        "checks": checks,
        "mismatches": mismatches,
    }
    if mismatches:
        raise RequiredContactPgsBackendError(
            validation, mismatches, validation_field=validation_field
        )
    return validation


def _build_spec(args: argparse.Namespace, batch: int):
    import importlib

    importlib.import_module("task_env.tasks")
    from task_env.vectorization.factory import make_framework_parallel_spec

    return make_framework_parallel_spec(
        uid=str(args.task_uid),
        num_env=int(batch),
        env_config={
            "base_seed": int(args.seed),
            "runtime": {
                "backend": str(args.backend),
                "prewarm": False,
                "batch_physics_layout": "static_template",
                "static_template": {
                    "profile": str(args.profile),
                    "kinematics_backend": str(args.kinematics_backend),
                    "contact_precision": str(args.contact_precision),
                    "cuda_graph": False,
                    # Stage A is the general boundary profile; keep it on the
                    # f64/CPU-safe P0 route instead of inheriting Go2's P12
                    # production defaults from task YAML.
                    "contact": {
                        "fixed_topology_child_schur": False,
                        "root_factor_6x6": False,
                    },
                },
                "enable_ground_contact": str(args.profile)
                == "articulated_fused_ground_contact_v1",
                "enable_domain_boundary_contact": False,
            },
        },
        backend=str(args.backend),
        execution="local",
        transfer_mode="device",
    )


def _missing_stage(reason: str) -> dict[str, Any]:
    return {"status": "not_measured", "samples": 0, "reason": reason}


def _stage_map(subphases: Mapping[str, Any], *, kinematics_backend: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in _ADDITIVE_STAGES:
        result[name] = dict(subphases.get(name, _missing_stage("stage not emitted by this profile")))
    for name, parent in _DIAGNOSTIC_CHILD_STAGES:
        result[name] = dict(
            subphases.get(name, _missing_stage("diagnostic child stage not emitted by this profile"))
        )
        result[name]["additive"] = False
        result[name]["parent"] = parent
    if str(kinematics_backend) == "taichi":
        result["runtime_handoff"] = dict(
            subphases.get(
                "runtime_handoff",
                _missing_stage("Taichi external-ndarray boundary was not sampled"),
            )
        )
        result["runtime_handoff"]["additive"] = False
        result["runtime_handoff"]["meaning"] = (
            "overlapping host/device envelope around Taichi external-ndarray calls"
        )
    else:
        result["runtime_handoff"] = {
            "status": "not_applicable",
            "samples": 0,
            "reason": "Torch FK owns the state tensors without a Taichi handoff",
            "additive": False,
        }
    return result


def _pointer_delta(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    before_pointers = dict(before.get("torch_tensor_pointers", {}))
    after_pointers = dict(after.get("torch_tensor_pointers", {}))
    before_external = dict(before.get("taichi_external_ndarray_pointers", {}))
    after_external = dict(after.get("taichi_external_ndarray_pointers", {}))
    pointer_changes = {
        name: {"before": before_pointers.get(name), "after": after_pointers.get(name)}
        for name in sorted(set(before_pointers) | set(after_pointers))
        if before_pointers.get(name) != after_pointers.get(name)
    }
    external_changes = {
        name: {"before": before_external.get(name), "after": after_external.get(name)}
        for name in sorted(set(before_external) | set(after_external))
        if before_external.get(name) != after_external.get(name)
    }
    return {
        "torch_tensor_pointers_stable": not pointer_changes,
        "taichi_external_ndarray_pointers_stable": not external_changes,
        "pointer_changes": pointer_changes,
        "external_pointer_changes": external_changes,
        "device_stable": before.get("device") == after.get("device"),
        "stream_stable": before.get("stream_id") == after.get("stream_id"),
        "before": dict(before),
        "after": dict(after),
    }


def _profile_case(args: argparse.Namespace, batch: int) -> dict[str, Any]:
    construction_started = time.perf_counter()
    spec = _build_spec(args, batch)
    current_phase = "construction"
    case: dict[str, Any] = {
        "status": "in_progress",
        "num_envs": int(batch),
        "backend": str(args.backend),
        "kinematics_backend": str(args.kinematics_backend),
        "profile": str(args.profile),
        "static_template_contact_precision": str(args.contact_precision),
        "construction": {"status": "in_progress", "samples": 0},
        "resource_summary": None,
        "post_measurement_resource_summary": None,
        "required_backend_validation": {
            "status": "pending",
            "point": "after_warmup_before_timed_samples",
            "required": args.require_contact_pgs_backend,
            "warmup_steps_completed": 0,
            "checks": None,
            "mismatches": [],
        },
        "post_measurement_backend_validation": {
            "status": "pending",
            "point": "after_timed_samples",
            "required": args.require_contact_pgs_backend,
            "warmup_steps_completed": int(args.warmup),
            "checks": None,
            "mismatches": [],
        },
        "completed_phases": [],
        "failed_phase": None,
    }

    def complete(phase: str) -> None:
        case["completed_phases"].append(phase)

    try:
        construction_device = None
        if str(args.backend) == "cuda":
            import torch

            construction_device = torch.device("cuda:0")
        _synchronise(construction_device)
        construction_ms = (time.perf_counter() - construction_started) * 1000.0
        case["construction"] = {
            "status": "measured",
            "samples": 1,
            "wall_ms": {
                "mean": construction_ms,
                "p50": construction_ms,
                "p95": construction_ms,
            },
            "cuda_event_ms": None,
        }
        complete("construction")

        current_phase = "device_setup"
        plan = spec.device_field_plan.as_dict()
        device = _resolve_device(plan, str(args.backend))
        if device is None:
            raise RuntimeError("Stage A requires the TaskEnv device path")
        collector = _ProfileCollector(device)
        spec.set_profile_collector(collector)
        physics = spec.runtime._physics
        boundary_before = physics.runtime_boundary_snapshot()
        memory_before = _device_memory_snapshot(device, reset_peak=True)

        spec.reset(seed=int(args.seed))
        import torch

        action = torch.zeros(
            (int(batch), int(spec.single_action_space.shape[0])),
            dtype=torch.float32,
            device=device,
        )
        state_before = spec.runtime.read_device_state(tuple(plan["state_readback_fields"]))
        control = spec.action_adapter.convert_device_batch(action, state_before)
        complete("device_setup")

        # Exercise and synchronize the exact runtime route before admitting any
        # timed sample.  The required-backend check therefore cannot mistake a
        # selected-but-uncompiled Triton specialization for a qualified one.
        current_phase = "warmup"
        for _ in range(max(0, int(args.warmup))):
            spec.runtime.step_device(control)
        _synchronise(device)
        complete("warmup")

        current_phase = "post_warmup_resource_summary"
        summary = spec.resource_summary()
        case["resource_summary"] = summary
        if summary["contact_precision_requested"] != str(args.contact_precision):
            raise AssertionError("Stage A runtime precision does not match its manifest")
        complete("post_warmup_resource_summary")

        current_phase = "required_backend_validation"
        case["required_backend_validation"] = _validate_required_contact_pgs_backend(
            required=args.require_contact_pgs_backend,
            summary=summary,
            warmup_steps=int(args.warmup),
        )
        complete("required_backend_validation")

        # The direct runtime phase isolates the physics stages.  The public
        # transition below includes task evaluation and lifecycle boundaries.
        current_phase = "direct_runtime_physics"
        physics_phase = _phase(
            lambda: spec.runtime.step_device(control),
            device=device,
            warmup=0,
            samples=int(args.steps),
            collector=collector,
        )
        case["direct_runtime_physics"] = physics_phase
        complete("direct_runtime_physics")

        current_phase = "transition_reset"
        spec.reset(seed=int(args.seed))
        complete("transition_reset")

        current_phase = "full_device_transition"
        transition_phase = _phase(
            lambda: spec.step_device(action),
            device=device,
            warmup=int(args.warmup),
            samples=int(args.steps),
            collector=collector,
        )
        case["full_device_transition"] = transition_phase
        complete("full_device_transition")

        current_phase = "post_measurement_summary"
        post_measurement_summary = spec.resource_summary()
        case["post_measurement_resource_summary"] = post_measurement_summary
        case["post_measurement_backend_validation"] = (
            _validate_required_contact_pgs_backend(
                required=args.require_contact_pgs_backend,
                summary=post_measurement_summary,
                warmup_steps=int(args.warmup),
                validation_field="post_measurement_backend_validation",
            )
        )
        case["post_measurement_backend_validation"]["point"] = (
            "after_timed_samples"
        )
        boundary_after = physics.runtime_boundary_snapshot()
        memory_after = _device_memory_snapshot(device)
        subphases = transition_phase.get("subphases", {})
        stages = _stage_map(subphases, kinematics_backend=str(args.kinematics_backend))
        additive_sum = {
            "wall_ms": {
                "p50": sum(
                    float(stages[name].get("wall_ms", {}).get("p50", 0.0) or 0.0)
                    for name in _ADDITIVE_STAGES
                )
            },
            "cuda_event_ms": {
                "p50": sum(
                    float(stages[name].get("cuda_event_ms", {}).get("p50", 0.0) or 0.0)
                    for name in _ADDITIVE_STAGES
                    if stages[name].get("cuda_event_ms") is not None
                )
            },
            "excludes": [
                *(name for name, _ in _DIAGNOSTIC_CHILD_STAGES),
                "runtime_handoff",
                "task_evaluation",
                "task_observation",
                "bridge_input",
                "bridge_output",
            ],
        }
        case.update(
            {
                "stage_a_segments": stages,
                "additive_stage_sum": additive_sum,
                "runtime_boundary": _pointer_delta(boundary_before, boundary_after),
                "device_memory": {"before": memory_before, "after": memory_after},
                "measurement_policy": {
                    "host_wall_clock": "perf_counter with explicit device synchronization",
                    "cuda_clock": "torch.cuda.Event when backend=cuda",
                    "warmup_excluded": int(args.warmup),
                    "steady_state_samples": int(args.steps),
                    "runtime_handoff_additive": False,
                },
            }
        )
        complete("post_measurement_summary")
        case["status"] = "measured"
        return case
    except RequiredContactPgsBackendError as exc:
        case["status"] = "failed_required_contact_pgs_backend"
        case["failed_phase"] = current_phase
        case[exc.validation_field] = exc.validation
        case[exc.validation_field]["point"] = (
            "after_timed_samples"
            if exc.validation_field == "post_measurement_backend_validation"
            else "after_warmup_before_timed_samples"
        )
        case["error"] = {"type": type(exc).__name__, "message": str(exc)}
        exc.case = dict(case)
        raise
    except Exception as exc:
        case["status"] = "failed"
        case["failed_phase"] = current_phase
        case["error"] = {"type": type(exc).__name__, "message": str(exc)}
        raise StageAProfileCaseError(dict(case), exc) from exc
    finally:
        spec.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-uid", default="go2-walk-v1")
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--kinematics-backend", choices=("torch", "taichi"), default="torch")
    parser.add_argument(
        "--profile",
        choices=("articulated_fused_no_contact_v1", "articulated_fused_ground_contact_v1"),
        default="articulated_fused_ground_contact_v1",
    )
    parser.add_argument(
        "--contact-precision",
        choices=("f64", "f32"),
        default="f64",
    )
    parser.add_argument("--num-envs", type=int, nargs="+", default=(1024, 4096, 8192))
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--seed", type=int, default=73)
    parser.add_argument("--load-label", choices=("idle", "current_training_occupied"), default="idle")
    parser.add_argument(
        "--require-contact-pgs-backend",
        default=None,
        metavar="BACKEND",
        help=(
            "fail after warm-up and before timed samples unless the runtime "
            "proves this selected/effective/qualified contact PGS backend"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("temp_outputs/task_env/stage_a_runtime_profile.json"),
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    preload = get_device_stack_provenance()
    if preload is None:
        preload = preload_device_stack(request_triton=str(args.backend) == "cuda")
    fingerprint = _fingerprint(str(args.backend))
    triton_disabled = os.environ.get("GEOPHYS_DISABLE_TRITON", "").strip() == "1"
    if (
        args.require_contact_pgs_backend
        == "triton_fused_axis_world_serial_v2"
        and not triton_disabled
    ):
        route_role = "candidate"
    elif args.require_contact_pgs_backend is None and triton_disabled:
        route_role = "baseline"
    else:
        route_role = "uncontrolled"
    session_started = datetime.now(timezone.utc).isoformat()
    driver = _gpu_driver_fingerprint()
    driver_models = driver.get("driver_model_current")
    if not isinstance(driver_models, list):
        driver_models = [driver_models]
    is_wddm = any(
        "wddm" in str(model).lower() for model in driver_models if model is not None
    )
    report: dict[str, Any] = {
        "schema": PROFILE_SCHEMA,
        "status": "failed",
        "manifest": {
            "evidence_revision": EVIDENCE_REVISION,
            "task_uid": str(args.task_uid),
            "backend": str(args.backend),
            "kinematics_backend": str(args.kinematics_backend),
            "profile": str(args.profile),
            "static_template_contact_precision": str(args.contact_precision),
            "num_envs": [int(value) for value in args.num_envs],
            "seed": int(args.seed),
            "warmup_steps": int(args.warmup),
            "steady_state_steps": int(args.steps),
            "load_label": str(args.load_label),
            "required_contact_pgs_backend": args.require_contact_pgs_backend,
            "backend_route": {
                "role": route_role,
                "required_backend": args.require_contact_pgs_backend,
                "geophys_disable_triton": triton_disabled,
                "bootstrap_status": preload.status,
            },
            "device_stack_preload": preload.to_dict(),
            "session": {
                "id": str(uuid4()),
                "started_utc": session_started,
                "pid": os.getpid(),
            },
            "invocation": _invocation(args, argv),
            "environment": {
                "system": platform.system(),
                "release": platform.release(),
                "platform": platform.platform(),
                "python_version": platform.python_version(),
                "python_executable": fingerprint["python_executable"],
                "cwd": fingerprint["cwd"],
                "runtime_versions": fingerprint["runtime_versions"],
                "execution_mode": (
                    "WDDM"
                    if is_wddm
                    else "linux_compute"
                    if platform.system() == "Linux"
                    else "compute_or_unknown"
                ),
            },
            "gpu_driver": driver,
            "process_accounting": {
                "status": "unknown",
                "method": "nvidia_smi_compute_apps",
                "before_complete": False,
                "after_complete": False,
                "external_compute_processes_before": [],
                "external_compute_processes_after": [],
            },
            "scene": {"status": "pending"},
            "outcome": {
                "status": "pending",
                "completed": False,
                "oom_observed_by_profiler": None,
                "oom_evidence_scope": "not_asserted; aggregate gate scans an external log sidecar",
            },
            "gpu_snapshots": {
                "before": [],
                "compute_processes_before": [],
                "external_compute_processes_before": [],
                "benchmark_pid": os.getpid(),
            },
            "fingerprint": fingerprint,
            "equation": "T_tick = T_FK + T_boundary + T_dynamics + T_contact + T_PGS + T_integration",
            "handoff_note": "runtime_handoff is a non-additive envelope; pointer stability determines whether a copy boundary exists",
        },
        "cases": [],
        "errors": [],
    }
    accounting_before: dict[str, Any] = {
        "complete": False,
        "processes": [],
        "external_processes": [],
        "error_type": "NotAttempted",
    }
    try:
        if any(int(batch) < 1 for batch in args.num_envs):
            raise ValueError("--num-envs values must be positive")
        if int(args.warmup) < 0 or int(args.steps) < 1:
            raise ValueError("--warmup must be non-negative and --steps must be positive")
        if str(args.backend) == "cuda":
            import torch

            if not torch.cuda.is_available():
                raise RuntimeError("Stage A CUDA profile requires an available CUDA device")
        accounting_before = _process_accounting_snapshot()
        process_before = accounting_before["processes"]
        snapshots = report["manifest"]["gpu_snapshots"]
        snapshots["before"] = _gpu_snapshot()
        snapshots["compute_processes_before"] = process_before
        snapshots["external_compute_processes_before"] = (
            _external_gpu_compute_processes(process_before)
        )
        for batch in args.num_envs:
            report["cases"].append(_profile_case(args, int(batch)))
        template_digests = {
            case["post_measurement_resource_summary"].get("template_digest")
            for case in report["cases"]
        }
        traversal_digests = {
            case["post_measurement_resource_summary"].get(
                "compiled_traversal_digest"
            )
            for case in report["cases"]
        }
        if (
            len(template_digests) != 1
            or len(traversal_digests) != 1
            or not isinstance(next(iter(template_digests), None), str)
            or not isinstance(next(iter(traversal_digests), None), str)
            or not next(iter(template_digests), "")
            or not next(iter(traversal_digests), "")
        ):
            raise RuntimeError(
                "Stage A cases did not preserve one compiled scene identity"
            )
        scene = _scene_fingerprint(args)
        scene.update(
            {
                "template_digest": next(iter(template_digests)),
                "compiled_traversal_digest": next(iter(traversal_digests)),
            }
        )
        report["manifest"]["scene"] = scene
        report["status"] = f"measured_{args.load_label}_profile"
    except RequiredContactPgsBackendError as exc:
        report["status"] = "failed_required_contact_pgs_backend"
        report["cases"].append(exc.case)
        report["errors"].append(
            {"type": type(exc).__name__, "message": str(exc)}
        )
    except StageAProfileCaseError as exc:
        report["status"] = "failed"
        report["cases"].append(exc.case)
        report["errors"].append(
            {
                "type": type(exc.original).__name__,
                "message": str(exc.original),
            }
        )
    except Exception as exc:
        report["status"] = "failed"
        report["errors"].append(
            {"type": type(exc).__name__, "message": str(exc)}
        )
    finally:
        accounting_after = _process_accounting_snapshot()
        process_after = accounting_after["processes"]
        snapshots = report["manifest"]["gpu_snapshots"]
        snapshots["after"] = _gpu_snapshot()
        snapshots["compute_processes_after"] = process_after
        snapshots["external_compute_processes_after"] = (
            _external_gpu_compute_processes(process_after)
        )
        process_accounting = report["manifest"]["process_accounting"]
        process_accounting.update(
            {
                "status": (
                    "complete"
                    if accounting_before["complete"]
                    and accounting_after["complete"]
                    else "incomplete"
                ),
                "before_complete": bool(accounting_before["complete"]),
                "after_complete": bool(accounting_after["complete"]),
                "external_compute_processes_before": accounting_before[
                    "external_processes"
                ],
                "external_compute_processes_after": accounting_after[
                    "external_processes"
                ],
                "before_error_type": accounting_before["error_type"],
                "after_error_type": accounting_after["error_type"],
            }
        )
        report["manifest"]["outcome"].update(
            {
                "status": report["status"],
                "completed": str(report["status"]).startswith("measured_"),
            }
        )
        _write_report_atomic(args.output, report)
    if report["status"].startswith("failed"):
        raise SystemExit(1)
    try:
        from task_env.utils.runtime_support import get_task_env_logger

        get_task_env_logger("simulation", module="task-env-stage-a-runtime-profile").success(
            "Stage A runtime profile written",
            output=str(args.output),
            cases=len(report["cases"]),
            kinematics_backend=str(args.kinematics_backend),
        )
    except Exception:
        pass


if __name__ == "__main__":
    main()
