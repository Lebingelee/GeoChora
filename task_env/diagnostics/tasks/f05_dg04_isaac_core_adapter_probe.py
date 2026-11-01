"""Bounded DG04 native probe through the real Isaac Core Runtime-I/O owner.

This worker is diagnostic evidence only. It does not call ``materialize`` and
cannot grant a Core admission, F05 acceptance, or provider qualification.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback


CORE = Path(__file__).resolve().parents[3]
DELIVERY_MANIFEST = CORE / (
    "workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/"
    "f05_diagnostic04/window_002/isaac_usd_v4/delivery_manifest.json"
)
ISAAC_SITE = CORE / "workspace/environments/isaacsim-6.2.0/lib/python3.12/site-packages"
CORE_SITE = Path("/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _jsonable(value):
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "item") and callable(value.item):
        return _jsonable(value.item())
    if isinstance(value, Path):
        return str(value)
    return value


def _bootstrap_attempted_steps(bootstrap: Mapping[str, object]) -> int:
    """Validate the adapter's public bootstrap receipt before charging steps."""
    if not isinstance(bootstrap, Mapping):
        raise TypeError("Isaac bootstrap receipt must be a mapping")
    if bootstrap.get("schema_version") != "isaac-public-physics-bootstrap-v1":
        raise ValueError("unsupported Isaac public bootstrap receipt schema")
    counters = tuple(bootstrap.get(key) for key in (
        "step_index_before", "step_index_after", "physics_steps",
    ))
    if any(type(value) is not int or value < 0 for value in counters):
        raise ValueError("Isaac bootstrap step counters must be nonnegative exact integers")
    before, after, steps = counters
    if after < before or after - before != steps:
        raise ValueError("Isaac bootstrap physics_steps differs from the public counter delta")

    times = tuple(bootstrap.get(key) for key in (
        "simulation_time_before_s", "simulation_time_after_s", "physics_time_s", "physics_dt_s",
    ))
    if any(type(value) not in (int, float) or isinstance(value, bool)
           or not math.isfinite(float(value)) for value in times):
        raise ValueError("Isaac bootstrap time facts must be finite non-boolean numbers")
    time_before, time_after, physics_time, physics_dt = map(float, times)
    if physics_dt <= 0.0 or time_after < time_before or physics_time < 0.0:
        raise ValueError("Isaac bootstrap time facts must be nonnegative with a positive physics dt")
    delta_time = time_after - time_before
    if (not math.isclose(physics_time, delta_time, rel_tol=0.0, abs_tol=1e-8)
            or not math.isclose(delta_time, steps * physics_dt, rel_tol=0.0, abs_tol=1e-8)):
        raise ValueError("Isaac bootstrap physics time differs from its public counter/dt")
    return steps


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    encoded = (json.dumps(_jsonable(payload), sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _python_dependency_setup() -> None:
    if Path(sys.executable).resolve() != (CORE / "workspace/environments/isaacsim-6.2.0/bin/python").resolve():
        raise RuntimeError("DG04 native probe must use the frozen Isaac Sim 6.2 interpreter")
    if os.environ.get("PYTHONPATH"):
        raise RuntimeError("DG04 native probe requires inherited PYTHONPATH to be unset")
    if str(CORE) not in sys.path:
        sys.path.insert(0, str(CORE))
    if str(CORE_SITE) not in sys.path:
        # Isaac's own site-packages remains first. This supplies the existing
        # Core environment's pure-Python Gymnasium/HDF5 dependencies only.
        sys.path.append(str(CORE_SITE))


def _validate_loaded_pxr_paths() -> None:
    # Importing pxr before SimulationApp starts preloads OpenUSD libraries in
    # the wrong order for Kit's plugins, even when pxr comes from Isaac itself.
    # Call this only after the existing Core App owner has opened SimulationApp.
    import pxr

    pxr_paths = [Path(item).resolve() for item in pxr.__path__]
    isaac_site = ISAAC_SITE.resolve()
    if not pxr_paths or any(isaac_site not in item.parents for item in pxr_paths):
        raise RuntimeError(f"OpenUSD resolved outside the matching Isaac installation: {pxr_paths!r}")


def _open_app_with_progress(app_owner, checkpoint) -> None:
    """Expose the synchronous Kit-open interval to the external watchdog."""
    checkpoint("isaac_app_open_start", attempted_steps_exact=False)
    app_owner.open()
    checkpoint("isaac_app_opened", attempted_steps_exact=False)


def _public_view_state(input_v1, native_io, sample, *, finger_positions, finger_velocities):
    import omni.usd
    import torch
    from isaacsim.core.experimental.prims import Articulation
    from isaacsim.core.simulation_manager import SimulationManager
    from pxr import UsdPhysics

    metadata = native_io.metadata()
    stage = omni.usd.get_context().get_stage()
    roots = [prim for prim in stage.Traverse() if prim.HasAPI(UsdPhysics.ArticulationRootAPI)]
    if len(roots) != 1:
        raise ValueError(f"DG04 expected one composed public articulation root, got {len(roots)}")
    articulation = Articulation(str(roots[0].GetPath()))
    # Isaac Sim 6.2 experimental Articulation exposes the public DOF inventory
    # as ``dof_names`` (the Core adapter uses the same public property).
    names = tuple(str(name) for name in articulation.dof_names)
    if names != tuple(metadata.native_dof_names):
        raise ValueError("independent public Articulation DOF names differ from Core Runtime-I/O metadata")
    semantic_by_native = {native: semantic for semantic, native in input_v1.runtime_source.joints.items()}
    positions = [float(sample.joint_position[semantic_by_native[name]]) for name in names]
    velocities = [0.0] * len(names)
    for native, value in finger_positions.items():
        positions[names.index(native)] = float(value)
    for native, value in finger_velocities.items():
        velocities[names.index(native)] = float(value)
    articulation.set_dof_positions(positions)
    articulation.set_dof_velocities(velocities)
    simulation_view = SimulationManager.get_physics_simulation_view()
    if simulation_view is None:
        raise RuntimeError("DG04 public physics simulation view is unavailable")
    refresh = getattr(simulation_view, "update_articulations_kinematic", None)
    if not callable(refresh) or refresh() is False:
        raise RuntimeError("DG04 public articulation kinematic refresh failed")
    torch.cuda.synchronize(0)
    readback = native_io.read_state()
    observed_q = tuple(float(readback.joint_position[f"panda-main/{name}"]) for name in (
        "finger_joint1", "finger_joint2",
    ))
    observed_qd = tuple(float(readback.joint_velocity[f"panda-main/{name}"]) for name in (
        "finger_joint1", "finger_joint2",
    ))
    expected_q = tuple(float(finger_positions[name]) for name in ("finger_joint1", "finger_joint2"))
    expected_qd = tuple(float(finger_velocities[name]) for name in ("finger_joint1", "finger_joint2"))
    if any(abs(actual - expected) > 1e-6 for actual, expected in zip(observed_q, expected_q, strict=True)):
        raise ValueError(f"DG04 public asymmetric position write did not read back: {observed_q!r}")
    if any(abs(actual - expected) > 1e-6 for actual, expected in zip(observed_qd, expected_qd, strict=True)):
        raise ValueError(f"DG04 public asymmetric velocity write did not read back: {observed_qd!r}")
    return articulation, readback


def _arm_position_targets(input_v1, metadata, sample):
    return tuple(sorted(
        (
            metadata.native_dof_names.index(input_v1.runtime_source.joints[semantic]),
            input_v1.runtime_source.joints[semantic],
            float(sample.joint_position[semantic]),
        )
        for semantic in input_v1.runtime_source.joints
        if input_v1.runtime_source.joints[semantic] in {f"joint{index}" for index in range(1, 8)}
    ))


def _reset(input_v1, native_io, sample, targets):
    receipt = native_io.write_reset(sample, targets)
    receipt.validate(sample, input_v1.runtime_source, tuple(row[1] for row in targets))
    return receipt


def _diagnostic_contact_reset_sample(sample):
    """Clone the frozen task reset with a clearly labeled cube/support probe pose.

    F05 support top is z=0.475 m and the source cube half-height is 0.03 m;
    z=0.504 m gives a 1 mm overlap for a bounded raw-contact witness. The
    source task reset remains untouched and is still used for force probes and
    the later formal episodes.
    """
    from task_env.artifacts.contracts import PoseWorld
    from task_env.artifacts.execution import ResetSample

    cube_key = "free-cube/free_cube"
    if set(sample.poses_world) != {cube_key}:
        raise ValueError("DG04 contact diagnostic requires the exact single free-cube reset pose")
    poses = dict(sample.poses_world)
    source_pose = poses[cube_key]
    poses[cube_key] = PoseWorld((1.0, 0.5, 0.504), source_pose.quaternion_wxyz)
    probe = ResetSample.create(
        schema_version=sample.schema_version,
        task_artifact_hash=sample.task_artifact_hash,
        sampler_id="f05-dg04-diagnostic-support-contact-probe",
        sampler_version="window002-v1",
        task_seed=sample.task_seed,
        joint_position=dict(sample.joint_position),
        poses_world=poses,
        velocity_policy=sample.velocity_policy,
        control_policy=sample.control_policy,
        settle_steps=sample.settle_steps,
    )
    probe.validate()
    return probe


def _target(native_io, receipt, *, mode: str, case: str, control: float):
    from task_env.runtime.sessions.native_io import NativeSourceTendonWriteAckV1

    identity = _sha256(f"{mode}:{case}:{control:.17g}".encode("utf-8"))
    ack = native_io.write_source_tendon_target(
        identity, receipt.identity_sha256, receipt.actuator_name, float(control), 100.0,
    )
    if type(ack) is not NativeSourceTendonWriteAckV1:
        raise TypeError("DG04 source-tendon target did not return the exact typed Core acknowledgement")
    ack.validate(
        target_identity_sha256=identity,
        receipt_identity_sha256=receipt.identity_sha256,
        actuator_name=receipt.actuator_name,
        control_value=float(control),
        scalar_force_limit_N=100.0,
    )
    return ack


def _advance_checked(native_io, validator, ack, expected_index: int):
    application_receipt = native_io.advance()
    from task_env.runtime.sessions.native_io import NativeAdvanceReceiptV1, UsdCoreRuntimeSession

    if type(application_receipt) is not NativeAdvanceReceiptV1:
        raise TypeError("DG04 adapter advance did not return the exact Core receipt")
    application_receipt.validate(expected_index, expected_index * float(validator._artifact.timebase.physics_dt))
    application = application_receipt.source_tendon_application
    if application is None:
        raise ValueError("DG04 native adapter omitted its source tendon/mimic/contact consumer receipt")
    UsdCoreRuntimeSession._validate_source_tendon_application(
        validator, application, ack, expected_index,
    )
    return application_receipt, application


def _verify_paired_physics_response(mode_receipts: Mapping[str, Mapping[str, object]]) -> dict:
    """Require source-dependent USD updates to change actual public state evolution.

    Both runs use one composed model and consumer with matching public initial q/qd,
    reset sample, source-tendon control, and 40-step horizon. Residual and relative
    velocity are compared so common articulation motion cancels. The response
    thresholds are 5e-6 m and 1e-4 m/s. For a 0.5 mm initial residual and 80 ms,
    the independent unit-mass homogeneous oscillator predicts about 7e-6 m
    residual separation and 1e-3 m/s relative-velocity separation. The position
    threshold is 5x the public 1e-6 m readback tolerance; velocity is 100x its
    readback tolerance. This is a diagnostic detector, not solver equivalence.
    """
    required = {"source_dynamic", "fixed_endpoint_ablation"}
    if set(mode_receipts) != required:
        raise ValueError("DG04 physical-response detector requires exactly both compliance modes")
    dynamic = mode_receipts["source_dynamic"]
    fixed = mode_receipts["fixed_endpoint_ablation"]
    if (dynamic.get("rollout_steps") != 40 or fixed.get("rollout_steps") != 40
            or dynamic.get("rollout_reset_sample_id") != fixed.get("rollout_reset_sample_id")
            or dynamic.get("rollout_control_value") != fixed.get("rollout_control_value")):
        raise ValueError("DG04 response pair differs in reset identity, control, or required 40-step horizon")

    initial_position_delta = max(
        abs(float(a) - float(b))
        for a, b in zip(
            dynamic["rollout_initial_positions_m"], fixed["rollout_initial_positions_m"], strict=True,
        )
    )
    initial_velocity_delta = max(
        abs(float(a) - float(b))
        for a, b in zip(
            dynamic["rollout_initial_velocities_m_s"],
            fixed["rollout_initial_velocities_m_s"], strict=True,
        )
    )
    if initial_position_delta > 1e-6 or initial_velocity_delta > 1e-6:
        raise ValueError("DG04 response pair does not share the same public initial q/qd")

    dynamic_trace, fixed_trace = dynamic.get("trace"), fixed.get("trace")
    if (not isinstance(dynamic_trace, list) or not isinstance(fixed_trace, list)
            or len(dynamic_trace) != 40 or len(fixed_trace) != 40):
        raise ValueError("DG04 response pair lacks complete 40-step physical traces")
    parameter_delta_hz = 0.0
    position_delta_m = 0.0
    relative_velocity_delta_m_s = 0.0
    for left, right in zip(dynamic_trace, fixed_trace, strict=True):
        if left.get("step_index") != right.get("step_index"):
            raise ValueError("DG04 response pair step identities are not aligned")
        if left.get("rollout_control_value") != right.get("rollout_control_value"):
            raise ValueError("DG04 response pair source-tendon commands differ")
        parameter_delta_hz = max(
            parameter_delta_hz,
            abs(float(left["public_frequency_readback_hz"])
                - float(right["public_frequency_readback_hz"])),
        )
        left_q, right_q = left["post_step_finger_positions_m"], right["post_step_finger_positions_m"]
        left_qd = left["post_step_finger_velocities_m_s"]
        right_qd = right["post_step_finger_velocities_m_s"]
        if any(len(values) != 2 for values in (left_q, right_q, left_qd, right_qd)):
            raise ValueError("DG04 response pair must expose both public finger q/qd values")
        position_delta_m = max(
            position_delta_m,
            abs((float(left_q[1]) - float(left_q[0]))
                - (float(right_q[1]) - float(right_q[0]))),
        )
        relative_velocity_delta_m_s = max(
            relative_velocity_delta_m_s,
            abs((float(left_qd[1]) - float(left_qd[0]))
                - (float(right_qd[1]) - float(right_qd[0]))),
        )
    if parameter_delta_hz < 0.1:
        raise ValueError("DG04 source and endpoint USD frequency values did not materially separate")
    if position_delta_m <= 5e-6 or relative_velocity_delta_m_s <= 1e-4:
        raise ValueError(
            "DG04 USD mimic properties changed but the actual public physics response did not pass "
            "the frozen residual/velocity separation thresholds; observed "
            f"max_public_frequency_delta_hz={parameter_delta_hz!r}, "
            f"max_post_step_equality_residual_delta_m={position_delta_m!r}, "
            f"max_post_step_relative_velocity_delta_m_s={relative_velocity_delta_m_s!r}; "
            "required residual >5e-6 m and relative velocity >1e-4 m/s"
        )
    return {
        "status": "PASS_PUBLIC_PHYSICS_RESPONSE_CHANGES_WITH_SOURCE_MAPPING",
        "same_reset_and_control": True,
        "same_initial_public_q_qd": True,
        "steps_per_mode": 40,
        "max_public_frequency_delta_hz": parameter_delta_hz,
        "max_post_step_equality_residual_delta_m": position_delta_m,
        "max_post_step_relative_velocity_delta_m_s": relative_velocity_delta_m_s,
        "min_physical_position_delta_m": 5e-6,
        "min_physical_relative_velocity_delta_m_s": 1e-4,
        "public_state_readback_abs_tolerance": 1e-6,
        "threshold_basis": "5x position and 100x velocity public readback tolerance; below independent 0.5 mm/80 ms homogeneous oscillator estimate",
        "counterfactual": "changed public mimic frequency with fixed endpoint, same model/consumer/input",
    }


def run(mode: str, steps: int, output: Path, progress_path: Path,
        max_attempted_steps: int, max_bootstrap_steps: int) -> dict:
    native_steps = 0
    bootstrap_steps = None

    def checkpoint(stage: str, *, bootstrap_steps: int = 0,
                   attempted_steps_exact: bool = False) -> None:
        _atomic_json(progress_path, {
            "schema_version": "f05-dg04-native-core-adapter-progress-v1",
            "mode": mode,
            "stage": stage,
            "bootstrap_steps": int(bootstrap_steps),
            "nonbootstrap_attempted_steps": native_steps,
            "attempted_steps_exact": bool(attempted_steps_exact),
            "updated_at_monotonic_s": time.monotonic(),
        })

    checkpoint("python_bootstrap", attempted_steps_exact=False)
    _python_dependency_setup()
    if mode not in {"source_dynamic", "fixed_endpoint_ablation", "paired_dynamic_and_ablation"}:
        raise ValueError(f"unknown DG04 compliance mode {mode!r}")
    max_steps = 40 if mode == "paired_dynamic_and_ablation" else 300
    if type(steps) is not int or not 1 <= steps <= max_steps:
        raise ValueError(f"DG04 {mode} rollout is bounded to 1..{max_steps} steps")
    if type(max_attempted_steps) is not int or not 1 <= max_attempted_steps <= 500:
        raise ValueError("DG04 N1 per-run attempted-step bound must be in 1..500")
    if type(max_bootstrap_steps) is not int or not 0 <= max_bootstrap_steps <= 200:
        raise ValueError("DG04 N1 per-run bootstrap bound must be in 0..200")

    from task_env.runtime.sessions.isaac_native_io import (
        _process_app_owner, create_isaac_native_runtime_io,
    )
    from task_env.runtime.sessions.leaf_control import IsaacSourceEqualityComplianceV1
    from task_env.runtime.sessions.native_io import UsdCoreRuntimeSession

    app_owner = _process_app_owner()
    _open_app_with_progress(app_owner, checkpoint)
    native_io = None
    original_frequency = IsaacSourceEqualityComplianceV1.natural_frequency_hz
    original_damping = IsaacSourceEqualityComplianceV1.damping_ratio_for_residual

    def fixed_frequency_method(self, _residual_m):
        return original_frequency(self, self.source_solimp_effective[2])

    def fixed_damping_method(self, _residual_m):
        return original_damping(self, self.source_solimp_effective[2])

    try:
        _validate_loaded_pxr_paths()
        # The source-bound candidate loader uses OpenUSD only after Kit starts.
        from task_env.tasks.position_candidate.builder import build_f05_dg03_isaac_usd_candidate

        input_v1, _candidate = build_f05_dg03_isaac_usd_candidate(
            str(DELIVERY_MANIFEST), horizon=8,
        )
        input_v1.validate()
        from isaacsim.core.simulation_manager import SimulationManager

        adapter_steps_before = int(SimulationManager.get_num_physics_steps())
        try:
            native_io = create_isaac_native_runtime_io(
                input_v1.artifact, input_v1.execution, input_v1.runtime_source,
                dg03_input=input_v1,
            )
        except BaseException:
            # Count public physics updates performed before a source validator
            # rejects the stage, instead of charging an unrelated full cap.
            try:
                adapter_steps_after = int(SimulationManager.get_num_physics_steps())
                checkpoint(
                    "native_adapter_construction_failed",
                    bootstrap_steps=max(0, adapter_steps_after - adapter_steps_before),
                    attempted_steps_exact=True,
                )
            except BaseException:
                checkpoint(
                    "native_adapter_construction_step_count_unavailable",
                    attempted_steps_exact=False,
                )
            raise
    except BaseException as primary:
        IsaacSourceEqualityComplianceV1.natural_frequency_hz = original_frequency
        IsaacSourceEqualityComplianceV1.damping_ratio_for_residual = original_damping
        try:
            app_owner.close()
        except BaseException as cleanup_error:
            primary.add_note(
                f"Isaac App owner close after DG04 initialization failure also failed: "
                f"{type(cleanup_error).__name__}: {cleanup_error}"
            )
        raise

    if mode == "fixed_endpoint_ablation":
        # A controlled ablation of source-dependent compliance only. The real
        # stage, public effort path, contact queries and validator stay active.
        IsaacSourceEqualityComplianceV1.natural_frequency_hz = fixed_frequency_method
        IsaacSourceEqualityComplianceV1.damping_ratio_for_residual = fixed_damping_method

    try:
        import torch
        from task_env.runtime.sessions.leaf_control import IsaacSourceEqualityComplianceV1

        if not torch.cuda.is_available() or torch.cuda.current_device() != 0:
            raise RuntimeError("DG04 N1 requires the frozen CUDA device 0 route")
        sample = input_v1.reset_plan.reset_sample
        receipt = native_io.drive_receipt
        metadata = native_io.metadata()
        if receipt is None or receipt.provenance_kind != "native_runtime":
            raise ValueError("DG04 N1 did not compile a native model-bound source receipt")
        targets = _arm_position_targets(input_v1, metadata, sample)
        if len(targets) != 7:
            raise ValueError("DG04 reset must contain the seven source Arm drives")
        validator = type("NativeReceiptValidationContext", (), {})()
        validator._drive_receipt = receipt
        validator._native_io_metadata = metadata
        validator._artifact = input_v1.artifact

        bootstrap = dict(native_io.bootstrap_receipt())
        bootstrap_steps = _bootstrap_attempted_steps(bootstrap)
        checkpoint(
            "native_adapter_open", bootstrap_steps=bootstrap_steps,
            attempted_steps_exact=True,
        )
        if bootstrap_steps > max_bootstrap_steps:
            raise ValueError(
                f"DG04 N1 bootstrap exceeded its frozen {max_bootstrap_steps}-step bound: "
                f"{bootstrap_steps}"
            )
        from isaacsim.core.simulation_manager import SimulationManager

        planned_rollout_modes = 2 if mode == "paired_dynamic_and_ablation" else 1
        planned_native_steps = 2 + planned_rollout_modes * steps
        if bootstrap_steps + planned_native_steps > max_attempted_steps:
            raise ValueError(
                f"DG04 planned N1 work exceeds its frozen {max_attempted_steps}-step cap: "
                f"bootstrap={bootstrap_steps}, planned={planned_native_steps}"
            )

        def advance_attempted(ack, expected_index: int, stage: str):
            nonlocal native_steps
            if bootstrap_steps + native_steps + 1 > max_attempted_steps:
                raise RuntimeError("DG04 N1 per-run attempted-step cap would be exceeded")
            native_steps += 1
            checkpoint(stage, bootstrap_steps=bootstrap_steps, attempted_steps_exact=True)
            return _advance_checked(native_io, validator, ack, expected_index)

        global_before_probe = int(SimulationManager.get_num_physics_steps())
        compliance = receipt.equality_compliance
        if type(compliance) is not IsaacSourceEqualityComplianceV1:
            raise TypeError("DG04 model-bound source receipt lacks the source equality mapping")
        fixed_endpoint = float(compliance.source_solimp_effective[1])
        fixed_frequency = float(original_frequency(compliance, fixed_endpoint))
        fixed_damping = float(original_damping(compliance, fixed_endpoint))

        force_cases = []
        force_mode = "source_dynamic" if mode == "paired_dynamic_and_ablation" else mode
        for case, control, velocities, expected_force in (
            ("positive_scalar_clamp", 255.0, (-20.0, -10.0), 100.0),
            ("negative_scalar_clamp", 0.0, (20.0, 10.0), -100.0),
        ):
            _reset(input_v1, native_io, sample, targets)
            _articulation, _initial = _public_view_state(
                input_v1, native_io, sample,
                finger_positions={"finger_joint1": 0.024, "finger_joint2": 0.040},
                finger_velocities={
                    "finger_joint1": velocities[0], "finger_joint2": velocities[1],
                },
            )
            ack = _target(native_io, receipt, mode=force_mode, case=case, control=control)
            _advance_receipt, application = advance_attempted(
                ack, 1, f"force_case_{case}_step_1",
            )
            if (abs(float(application["scalar_force_N"]) - expected_force) > 1e-8
                    or tuple(application["public_applied_efforts_N"]) != (expected_force / 2.0,) * 2):
                raise ValueError(f"DG04 source force-law saturation/J^T application failed in {case}")
            force_cases.append({"case": case, "application": dict(application)})

        paired = mode == "paired_dynamic_and_ablation"
        if paired and steps != 40:
            raise ValueError("DG04 source-consumer response gate requires the frozen 40 steps per mode")
        compliance_modes = ("source_dynamic", "fixed_endpoint_ablation") if paired else (mode,)
        rollout_sample = _diagnostic_contact_reset_sample(sample) if paired else sample
        mode_receipts = {}
        combined_trace = []
        for active_mode in compliance_modes:
            if paired and active_mode == "fixed_endpoint_ablation":
                # Hold only the source-dependent compliance mapping at the exact
                # endpoint, in this same App, model, public consumer and rollout.
                IsaacSourceEqualityComplianceV1.natural_frequency_hz = fixed_frequency_method
                IsaacSourceEqualityComplianceV1.damping_ratio_for_residual = fixed_damping_method
            _reset(input_v1, native_io, rollout_sample, targets)
            rollout_fingers = (
                {"finger_joint1": 0.024, "finger_joint2": 0.0245}
                if paired
                else {"finger_joint1": 0.024, "finger_joint2": 0.040}
            )
            _articulation, initial_readback = _public_view_state(
                input_v1, native_io, rollout_sample,
                finger_positions=rollout_fingers,
                finger_velocities={"finger_joint1": 0.0, "finger_joint2": 0.0},
            )
            rollout_ack = _target(
                native_io, receipt, mode=active_mode, case="paired_solimp_rollout", control=127.5,
            )
            trace = []
            contact_positive_steps = []
            for index in range(1, steps + 1):
                step_receipt, application = advance_attempted(
                    rollout_ack, index, f"{active_mode}_rollout_step_{index}",
                )
                residual = float(application["source_equality_residual_m"])
                dynamic_frequency = float(original_frequency(compliance, residual))
                dynamic_damping = float(original_damping(compliance, residual))
                state = native_io.read_state()
                post_q = (
                    float(state.joint_position["panda-main/finger_joint1"]),
                    float(state.joint_position["panda-main/finger_joint2"]),
                )
                post_qd = (
                    float(state.joint_velocity["panda-main/finger_joint1"]),
                    float(state.joint_velocity["panda-main/finger_joint2"]),
                )
                post_residual = post_q[1] - post_q[0]
                witness = application["public_contact_witness"]
                if witness["contact_present"]:
                    contact_positive_steps.append(index)
                trace.append({
                    "compliance_mode": active_mode,
                    "step_index": index,
                    "simulation_time_s": float(step_receipt.simulation_time_s),
                    "rollout_control_value": 127.5,
                    "pre_step_finger_positions_m": application["finger_positions_m"],
                    "pre_step_finger_velocities_m_s": application["finger_velocities_m_s"],
                    "source_equality_residual_m": residual,
                    "source_equality_impedance": float(application["source_equality_impedance"]),
                    "dynamic_source_frequency_hz": dynamic_frequency,
                    "dynamic_source_damping_ratio": dynamic_damping,
                    "public_frequency_readback_hz": float(application["public_mimic_frequency_readback_hz"]),
                    "public_damping_ratio_readback": float(application["public_mimic_damping_ratio_readback"]),
                    "post_step_finger_positions_m": post_q,
                    "post_step_finger_velocities_m_s": post_qd,
                    "post_step_equality_residual_m": post_residual,
                    "tendon_length_m": float(application["tendon_length_m"]),
                    "tendon_rate_m_s": float(application["tendon_rate_m_s"]),
                    "unclipped_scalar_force_N": float(application["unclipped_scalar_force_N"]),
                    "scalar_force_N": float(application["scalar_force_N"]),
                    "dof_efforts_N": application["dof_efforts_N"],
                    "public_applied_efforts_N": application["public_applied_efforts_N"],
                    "contact_witness": dict(witness),
                })

            expected_start_residual = rollout_fingers["finger_joint2"] - rollout_fingers["finger_joint1"]
            if (abs(float(initial_readback.joint_position["panda-main/finger_joint2"])
                    - float(initial_readback.joint_position["panda-main/finger_joint1"])
                    - expected_start_residual) > 1e-6):
                raise ValueError(f"DG04 {active_mode} rollout did not start at the frozen residual")
            if min(abs(row["source_equality_residual_m"]) for row in trace) >= 0.001:
                raise ValueError(f"DG04 {active_mode} rollout did not exercise the solimp width")
            if not contact_positive_steps:
                raise ValueError(f"DG04 {active_mode} rollout missed public cube/support contact")
            expected_frequency = (
                [row["dynamic_source_frequency_hz"] for row in trace]
                if active_mode == "source_dynamic" else [fixed_frequency] * len(trace)
            )
            expected_damping = (
                [row["dynamic_source_damping_ratio"] for row in trace]
                if active_mode == "source_dynamic" else [fixed_damping] * len(trace)
            )
            for row, frequency, damping in zip(trace, expected_frequency, expected_damping, strict=True):
                if (abs(row["public_frequency_readback_hz"] - frequency) > 1e-6
                        or abs(row["public_damping_ratio_readback"] - damping) > 1e-6):
                    raise ValueError(f"DG04 {active_mode} public compliance readback differs from its assigned mapping")
            if active_mode == "fixed_endpoint_ablation" and not any(
                    abs(row["public_frequency_readback_hz"] - row["dynamic_source_frequency_hz"]) > 1e-5
                    or abs(row["public_damping_ratio_readback"] - row["dynamic_source_damping_ratio"]) > 1e-5
                    for row in trace):
                raise ValueError("DG04 fixed endpoint ablation did not diverge from the source solimp curve")
            mode_receipts[active_mode] = {
                "rollout_steps": len(trace),
                "rollout_reset_sample_id": rollout_sample.sample_id,
                "rollout_control_value": 127.5,
                "rollout_initial_positions_m": [
                    float(initial_readback.joint_position["panda-main/finger_joint1"]),
                    float(initial_readback.joint_position["panda-main/finger_joint2"]),
                ],
                "rollout_initial_velocities_m_s": [
                    float(initial_readback.joint_velocity["panda-main/finger_joint1"]),
                    float(initial_readback.joint_velocity["panda-main/finger_joint2"]),
                ],
                "rollout_initial_residual_m": expected_start_residual,
                "rollout_final_residual_m": trace[-1]["post_step_equality_residual_m"],
                "contact_positive_step_indices": contact_positive_steps,
                "contact_positive_step_count": len(contact_positive_steps),
                "trace": trace,
            }
            combined_trace.extend(trace)

        physical_response = _verify_paired_physics_response(mode_receipts) if paired else None

        # Do not leave process-global methods patched during ordinary teardown.
        IsaacSourceEqualityComplianceV1.natural_frequency_hz = original_frequency
        IsaacSourceEqualityComplianceV1.damping_ratio_for_residual = original_damping
        final = native_io.read_state()
        final_q = (
            float(final.joint_position["panda-main/finger_joint1"]),
            float(final.joint_position["panda-main/finger_joint2"]),
        )
        final_cube = final.free_joint_readback["free-cube/free_cube"]
        cube_position = tuple(float(value) for value in final_cube.position_world_m)

        return {
            "schema_version": "f05-dg04-native-core-adapter-probe-v1",
            "status": "PASS_DIAGNOSTIC_ONLY",
            "package_id": "F05_DIAGNOSTIC04_WINDOW002_REPAIR_SOURCE_ORACLE_AND_LIVE_CONSUMER",
            "input_head": subprocess.check_output(
                ["git", "-C", str(CORE), "rev-parse", "HEAD"], text=True,
            ).strip(),
            "compliance_mode": mode,
            "compliance_modes": mode_receipts,
            "physical_response_detection": physical_response,
            "artifact_identity_sha256": input_v1.artifact.identity_hash,
            "source_closure_sha256": input_v1.runtime_source.source_closure_digest,
            "delivery_sha256": input_v1.runtime_source.scene_source.loaded_delivery.delivery_sha256,
            "delivery_manifest_sha256": input_v1.runtime_source.scene_source.loaded_delivery.manifest_bytes_sha256,
            "scene_identity_sha256": input_v1.runtime_source.scene_definition.identity_hash,
            "execution_identity_sha256": input_v1.execution.identity_hash,
            "drive_receipt_identity_sha256": receipt.identity_sha256,
            "source_verified": False,
            "locally_validated": True,
            "production_materialize_admission_changed": False,
            "provider_build_identity": metadata.provider_build_identity,
            "physics_backend": metadata.backend,
            "physics_device": metadata.device,
            "native_dof_names": metadata.native_dof_names,
            "bootstrap_receipt": bootstrap,
            "bootstrap_attempted_steps": bootstrap_steps,
            "mode_fixed_endpoint": {"frequency_hz": fixed_frequency, "damping_ratio": fixed_damping},
            "force_clamp_cases": force_cases,
            "rollout_steps": len(combined_trace),
            "rollout_steps_per_compliance_mode": steps,
            "rollout_initial_positions_m": [
                rollout_fingers["finger_joint1"], rollout_fingers["finger_joint2"],
            ],
            "rollout_initial_residual_m": expected_start_residual,
            "contact_probe_reset_kind": (
                "diagnostic ResetSample clone; task/joints preserved; source cube moved to exact 1 mm support overlap"
                if paired else "frozen candidate reset sample"
            ),
            "contact_probe_reset_sample_id": rollout_sample.sample_id,
            "contact_probe_cube_position_m": list(rollout_sample.poses_world[
                "free-cube/free_cube"
            ].position),
            "rollout_final_positions_m": final_q,
            "rollout_final_residual_m": final_q[1] - final_q[0],
            "cube_final_position_world_m": cube_position,
            "contact_positive_step_indices_by_mode": {
                key: row["contact_positive_step_indices"] for key, row in mode_receipts.items()
            },
            "trace": combined_trace,
            "global_physics_steps_before_probe": global_before_probe,
            "global_physics_steps_after_probe": int(SimulationManager.get_num_physics_steps()),
            "native_physics_steps_excluding_bootstrap": native_steps,
            "total_native_attempted_steps": bootstrap_steps + native_steps,
            "wall_seconds_worker": time.monotonic(),
        }
    except BaseException:
        if bootstrap_steps is None and native_io is not None:
            try:
                bootstrap = dict(native_io.bootstrap_receipt())
                bootstrap_steps = _bootstrap_attempted_steps(bootstrap)
                checkpoint(
                    "native_probe_failed", bootstrap_steps=bootstrap_steps,
                    attempted_steps_exact=True,
                )
            except BaseException:
                checkpoint(
                    "native_probe_failure_step_count_unavailable",
                    attempted_steps_exact=False,
                )
        elif bootstrap_steps is not None:
            checkpoint(
                "native_probe_failed", bootstrap_steps=bootstrap_steps,
                attempted_steps_exact=True,
            )
        raise
    finally:
        try:
            native_io.close()
        finally:
            native_io.close_runtime_owner()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=(
        "source_dynamic", "fixed_endpoint_ablation", "paired_dynamic_and_ablation",
    ))
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument("--max-attempted-steps", type=int, required=True)
    parser.add_argument("--max-bootstrap-steps", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    began = time.monotonic()
    progress_path = args.output.with_name(args.output.stem + ".progress.json")
    try:
        receipt = run(
            args.mode, args.steps, args.output, progress_path,
            args.max_attempted_steps, args.max_bootstrap_steps,
        )
        receipt["wall_seconds_worker"] = time.monotonic() - began
        _atomic_json(args.output, receipt)
        print(json.dumps({key: value for key, value in receipt.items() if key != "trace"},
                         sort_keys=True, indent=2, allow_nan=False))
        return 0
    except BaseException:
        _atomic_json(args.output.with_name(args.output.stem + ".failure.json"), {
            "schema_version": "f05-dg04-native-core-adapter-probe-failure-v1",
            "mode": args.mode,
            "wall_seconds_worker": time.monotonic() - began,
            "traceback": traceback.format_exc(),
        })
        raise


if __name__ == "__main__":
    raise SystemExit(main())
