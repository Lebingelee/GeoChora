"""Bounded Isaac 6.2 native-mimic N1 probe for the DG04 adaptation profile.

This probe exercises the real DG04 native I/O owner in one Isaac App. It is
diagnostic evidence for passive follower synchronization and blocked contact;
it does not constitute Core N2, source-dynamics equivalence, or qualification.
"""
from __future__ import annotations

import argparse
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
ISAAC_ROOT = CORE / "workspace/environments/isaacsim-6.2.0"
ISAAC_SITE = ISAAC_ROOT / "lib/python3.12/site-packages"
CORE_SITE = Path("/home/lly/miniconda3/envs/geochora/lib/python3.12/site-packages")
SYNC_STEPS = 100
CONTACT_LOCAL_Z_M = 0.085
CONTACT_TARGET_M = 0.005
CONTACT_MIN_BLOCKED_GAP_M = 0.010
CONTACT_MIN_NORMAL_FORCE_N = 0.001
MIN_APPLIED_LEADER_EFFORT_N = 0.1
RELATION_LIMIT_M = 0.002
EFFORT_CAP_N = 100.0


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _terminate_worker(exit_code: int) -> None:
    """Use the established Kit worker terminal boundary after durable receipts."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except (OSError, ValueError):
            pass
    os._exit(int(exit_code))


def _checkpoint(path: Path, mode: str, stage: str, *, bootstrap_steps: int,
                native_steps: int, exact: bool) -> None:
    _atomic_json(path, {
        "schema_version": "f05-dg04-native-mimic-n1-progress-v1",
        "mode": mode,
        "stage": stage,
        "bootstrap_steps": int(bootstrap_steps),
        "nonbootstrap_attempted_steps": int(native_steps),
        "attempted_steps_exact": bool(exact),
        "updated_at_monotonic_s": time.monotonic(),
    })


def _python_dependency_setup() -> None:
    if Path(sys.executable).resolve() != (ISAAC_ROOT / "bin/python").resolve():
        raise RuntimeError("DG04 native mimic N1 must use the frozen Isaac Sim 6.2 interpreter")
    if os.environ.get("PYTHONPATH"):
        raise RuntimeError("DG04 native mimic N1 requires inherited PYTHONPATH to be unset")
    if str(CORE) not in sys.path:
        sys.path.insert(0, str(CORE))
    if str(CORE_SITE) not in sys.path:
        sys.path.append(str(CORE_SITE))


def _validate_loaded_pxr_paths() -> dict[str, object]:
    import pxr
    from pxr import Gf, PhysxSchema, Sdf, Tf, Usd, UsdGeom, UsdPhysics

    expected = ISAAC_SITE.resolve()
    search_paths = [Path(item).resolve() for item in pxr.__path__]
    if not search_paths or not any(expected in item.parents for item in search_paths):
        raise RuntimeError(f"OpenUSD namespace is not extended by the matching Isaac install: {search_paths!r}")
    modules = {
        "Gf": Gf, "PhysxSchema": PhysxSchema, "Sdf": Sdf, "Tf": Tf,
        "Usd": Usd, "UsdGeom": UsdGeom, "UsdPhysics": UsdPhysics,
    }
    loaded = {}
    for name, module in modules.items():
        origin = getattr(module, "__file__", None)
        if not origin:
            spec = getattr(module, "__spec__", None)
            origin = getattr(spec, "origin", None)
        if not isinstance(origin, str) or not origin:
            raise RuntimeError(f"OpenUSD module {name} has no concrete loaded origin")
        resolved = Path(origin).resolve()
        if expected not in resolved.parents:
            raise RuntimeError(f"OpenUSD module {name} loaded outside the matching Isaac install: {resolved}")
        loaded[name] = str(resolved)
    return {
        "isaac_site": str(expected),
        "namespace_search_paths": [str(path) for path in search_paths],
        "loaded_module_origins": loaded,
        "verification": "all adapter-consumed OpenUSD modules originate inside Isaac 6.2; additional namespace search roots are allowed",
    }


def _open_app_with_progress(app_owner, progress_path: Path, mode: str) -> None:
    _checkpoint(progress_path, mode, "isaac_app_open_start",
                bootstrap_steps=0, native_steps=0, exact=False)
    app_owner.open()
    _checkpoint(progress_path, mode, "isaac_app_opened",
                bootstrap_steps=0, native_steps=0, exact=False)


def _bootstrap_steps(receipt: dict) -> int:
    if receipt.get("schema_version") != "isaac-public-physics-bootstrap-v1":
        raise ValueError("unsupported Isaac public bootstrap receipt")
    before, after, steps = (receipt.get(key) for key in (
        "step_index_before", "step_index_after", "physics_steps",
    ))
    if any(type(item) is not int or item < 0 for item in (before, after, steps)):
        raise ValueError("Isaac bootstrap counters must be nonnegative exact integers")
    if after - before != steps:
        raise ValueError("Isaac bootstrap step count differs from its public counter delta")
    dt = float(receipt["physics_dt_s"])
    elapsed = float(receipt["physics_time_s"])
    if not math.isfinite(dt) or dt <= 0 or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError("Isaac bootstrap timing facts are invalid")
    return steps


def _rotation_matrix_wxyz(quaternion):
    w, x, y, z = (float(item) for item in quaternion)
    return (
        (1 - 2 * (y*y + z*z), 2 * (x*y - z*w), 2 * (x*z + y*w)),
        (2 * (x*y + z*w), 1 - 2 * (x*x + z*z), 2 * (y*z - x*w)),
        (2 * (x*z - y*w), 2 * (y*z + x*w), 1 - 2 * (x*x + y*y)),
    )


def _hand_local_offset_world(hand_pose, local_offset):
    matrix = _rotation_matrix_wxyz(hand_pose.quaternion_wxyz)
    rotated = tuple(sum(matrix[row][col] * local_offset[col] for col in range(3))
                    for row in range(3))
    return tuple(float(hand_pose.position[i]) + rotated[i] for i in range(3))


def _clone_reset(sample, *, tag: str, finger_q: tuple[float, float], cube_pose=None):
    from task_env.artifacts.execution import ResetSample

    joints = dict(sample.joint_position)
    joints["panda-main/finger_joint1"] = float(finger_q[0])
    joints["panda-main/finger_joint2"] = float(finger_q[1])
    poses = dict(sample.poses_world)
    if cube_pose is not None:
        poses["free-cube/free_cube"] = cube_pose
    result = ResetSample.create(
        schema_version=sample.schema_version,
        task_artifact_hash=sample.task_artifact_hash,
        sampler_id=f"f05-dg04-window004-native-mimic-{tag}",
        sampler_version="window004-n1-v1",
        task_seed=sample.task_seed,
        joint_position=joints,
        poses_world=poses,
        velocity_policy=sample.velocity_policy,
        control_policy=sample.control_policy,
        settle_steps=sample.settle_steps,
    )
    result.validate()
    return result


def _active_targets(input_v1, metadata, sample, *, leader_m: float):
    arm = tuple(
        (metadata.native_dof_names.index(native), native, float(sample.joint_position[semantic]))
        for semantic, native in input_v1.runtime_source.joints.items()
        if native in {f"joint{index}" for index in range(1, 8)}
    )
    leader = (metadata.native_dof_names.index("finger_joint1"), "finger_joint1", float(leader_m))
    targets = tuple(sorted((*arm, leader)))
    names = {name for _index, name, _value in targets}
    expected = {f"joint{index}" for index in range(1, 8)} | {"finger_joint1"}
    if len(targets) != 8 or names != expected or "finger_joint2" in names:
        raise ValueError("N1 target must drive the seven Arm joints and leader only")
    return targets


def _write_reset(input_v1, native_io, sample, targets):
    from isaacsim.core.simulation_manager import SimulationManager

    physics_before = int(SimulationManager.get_num_physics_steps())
    receipt = native_io.write_reset(sample, targets)
    physics_after = int(SimulationManager.get_num_physics_steps())
    from task_env.runtime.sessions.native_io import NativeResetWriteReceiptV1

    if type(receipt) is not NativeResetWriteReceiptV1:
        raise TypeError("DG04 native reset did not return its exact typed receipt")
    receipt.validate(sample, input_v1.runtime_source, tuple(row[1] for row in targets))
    if physics_after != physics_before:
        raise ValueError("DG04 diagnostic reset unexpectedly advanced physics")
    return receipt


def _set_target(native_io, targets, phase: str):
    target_identity = hashlib.sha256(
        json.dumps({"phase": phase, "targets": targets}, sort_keys=True).encode(),
    ).hexdigest()
    ack = native_io.write_position_targets(target_identity, targets)
    from task_env.runtime.sessions.native_io import NativePositionWriteAckV1

    if type(ack) is not NativePositionWriteAckV1:
        raise TypeError("DG04 target write did not return its exact typed acknowledgement")
    ack.validate(target_identity, targets)
    return ack


def _read_finger_state(native_io):
    state = native_io.read_state()
    q = (float(state.joint_position["panda-main/finger_joint1"]),
         float(state.joint_position["panda-main/finger_joint2"]))
    qd = (float(state.joint_velocity["panda-main/finger_joint1"]),
          float(state.joint_velocity["panda-main/finger_joint2"]))
    return state, q, qd


def _advance(native_io, *, step_index: int, target_identity: str,
             receipt_identity: str, progress_path: Path, mode: str,
             bootstrap_steps: int, native_steps: int) -> tuple[dict, object]:
    _checkpoint(progress_path, mode, f"native_step_{native_steps + 1}",
                bootstrap_steps=bootstrap_steps, native_steps=native_steps + 1, exact=True)
    from task_env.runtime.sessions.native_io import NativeAdvanceReceiptV1

    receipt = native_io.advance()
    if type(receipt) is not NativeAdvanceReceiptV1:
        raise TypeError("DG04 native advance did not return its exact typed receipt")
    if receipt.native_step_index != step_index:
        raise ValueError(f"DG04 native step index differs: {receipt.native_step_index} vs {step_index}")
    application = receipt.native_adaptation_application
    if (not isinstance(application, dict)
            or application.get("schema_version") != "native-physx-mimic-substep-application-v1"
            or application.get("provenance_kind") != "native_runtime"
            or application.get("native_step_index") != step_index
            or application.get("target_identity_sha256") != target_identity
            or application.get("drive_receipt_identity_sha256") != receipt_identity
            or application.get("reference_joint") != "finger_joint1"
            or application.get("follower_joint") != "finger_joint2"
            or application.get("public_effort_api")
                != "Articulation.get_dof_projected_joint_forces"
            or application.get("effort_measurement_semantics")
                != "projected_active_joint_force"):
        raise ValueError("DG04 native physical step is not bound to the current target/receipt")
    effort = float(application["reference_effort_N"])
    cap = float(application["maximum_effort_N"])
    relation = float(application["relation_error_m"])
    if (not all(math.isfinite(value) for value in (effort, cap, relation))
            or cap != EFFORT_CAP_N or abs(effort) > EFFORT_CAP_N + 1e-6):
        raise ValueError("DG04 actual leader effort violated the declared public 100 N cap")
    witness = application["public_contact_witness"]
    count = witness.get("raw_contact_count")
    paths = witness.get("raw_contact_actor_paths")
    forces = witness.get("raw_contact_normal_forces_N")
    signed_forces = witness.get("raw_contact_signed_normal_force_scalars_N")
    normals = witness.get("raw_contact_normals_world")
    separations = witness.get("raw_contact_separations_m")
    if (type(count) is not int or count < 0 or count > 32
            or type(paths) is not list or len(paths) != count
            or type(forces) is not list or len(forces) != count
            or type(signed_forces) is not list or len(signed_forces) != count
            or type(normals) is not list or len(normals) != count
            or type(separations) is not list or len(separations) != count
            or any(not isinstance(path, str) for path in paths)
            or witness.get("schema_version") != "f05-dg04-native-contact-witness-v1"
            or witness.get("force_magnitude_mapping") != "abs(raw_signed_normal_force_scalar_N)"
            or any(not math.isfinite(float(force)) or float(force) < 0 for force in forces)
            or any(not math.isfinite(float(force)) for force in signed_forces)
            or any(not math.isclose(float(magnitude), abs(float(signed)), rel_tol=0.0, abs_tol=1e-7)
                   for magnitude, signed in zip(forces, signed_forces, strict=True))
            or any(type(normal) is not list or len(normal) != 3
                   or any(not math.isfinite(float(value)) for value in normal) for normal in normals)
            or any(not math.isfinite(float(value)) for value in separations)):
        raise ValueError("DG04 raw contact actor/normal-force evidence is incomplete")
    return dict(application), receipt


def run(*, mode: str, contact_steps: int, output: Path, progress_path: Path,
        max_attempted_steps: int, max_bootstrap_steps: int) -> dict:
    if mode != "native_mimic_sync_contact":
        raise ValueError(f"unsupported DG04 native mimic mode {mode!r}")
    if type(contact_steps) is not int or contact_steps != 150:
        raise ValueError("the frozen DG04 blocked-contact horizon is exactly 150 steps")
    if type(max_attempted_steps) is not int or not 1 <= max_attempted_steps <= 500:
        raise ValueError("DG04 native mimic N1 total attempted-step cap must be in 1..500")
    if type(max_bootstrap_steps) is not int or not 0 <= max_bootstrap_steps <= 200:
        raise ValueError("DG04 native mimic N1 bootstrap cap must be in 0..200")

    _checkpoint(progress_path, mode, "python_bootstrap", bootstrap_steps=0,
                native_steps=0, exact=False)
    _python_dependency_setup()
    from task_env.runtime.sessions.isaac_native_io import (
        _process_app_owner, create_isaac_native_runtime_io,
    )

    app_owner = _process_app_owner()
    native_io = None
    bootstrap_steps = None
    native_steps = 0
    app_opened = False
    began = time.monotonic()
    native_attempts = 0
    try:
        _open_app_with_progress(app_owner, progress_path, mode)
        app_opened = True
        pxr_runtime_identity = _validate_loaded_pxr_paths()
        from task_env.tasks.position_candidate.builder import build_f05_dg04_isaac_native_candidate

        input_v1, _candidate = build_f05_dg04_isaac_native_candidate(
            str(DELIVERY_MANIFEST), horizon=8,
        )
        input_v1.validate()
        native_io = create_isaac_native_runtime_io(
            input_v1.artifact, input_v1.execution, input_v1.runtime_source,
            dg04_native_input=input_v1,
        )
        receipt = native_io.drive_receipt
        metadata = native_io.metadata()
        if (receipt is None or receipt.provenance_kind != "native_runtime"
                or receipt.physics_profile != "isaac-gpu-physx-f05-dg04-native-mimic-v1"
                or receipt.gripper_force_limit_N != EFFORT_CAP_N):
            raise ValueError("DG04 did not bind its exact native mimic profile and 100 N limit")
        bootstrap = dict(native_io.bootstrap_receipt())
        bootstrap_steps = _bootstrap_steps(bootstrap)
        _checkpoint(progress_path, mode, "native_adapter_open",
                    bootstrap_steps=bootstrap_steps, native_steps=0, exact=True)
        if bootstrap_steps > max_bootstrap_steps:
            raise ValueError("DG04 bootstrap exceeded the frozen N1 budget")
        if bootstrap_steps + SYNC_STEPS + contact_steps > max_attempted_steps:
            raise ValueError("DG04 sync/contact schedule exceeds the frozen total attempted-step budget")

        from isaacsim.core.simulation_manager import SimulationManager
        physics_before = int(SimulationManager.get_num_physics_steps())
        base = input_v1.reset_plan.reset_sample
        dt = float(input_v1.artifact.timebase.physics_dt)
        sync_sample = _clone_reset(base, tag="sync", finger_q=(0.028, 0.012))
        sync_targets = _active_targets(input_v1, metadata, sync_sample, leader_m=0.028)
        sync_reset = _write_reset(input_v1, native_io, sync_sample, sync_targets)
        sync_before_state, sync_initial_q, sync_initial_qd = _read_finger_state(native_io)
        if (abs(sync_initial_q[0] - 0.028) > 1e-6 or abs(sync_initial_q[1] - 0.012) > 1e-6
                or max(abs(value) for value in sync_initial_qd) > 1e-6):
            raise ValueError(f"DG04 asymmetric sync initial state did not read back: {sync_initial_q!r}, {sync_initial_qd!r}")
        sync_ack = _set_target(native_io, sync_targets, "sync_only_leader_0.028m")
        if "finger_joint2" in sync_ack.native_names:
            raise ValueError("DG04 synchronization detector unexpectedly commanded the passive follower")
        sync_trace = []
        for index in range(1, SYNC_STEPS + 1):
            native_attempts = native_steps + 1
            application, native_receipt = _advance(
                native_io, step_index=index,
                target_identity=sync_ack.target_identity_sha256,
                receipt_identity=receipt.identity_sha256,
                progress_path=progress_path, mode=mode,
                bootstrap_steps=bootstrap_steps, native_steps=native_steps,
            )
            native_steps += 1
            if abs(float(native_receipt.simulation_time_s) - index * dt) > 1e-12:
                raise ValueError("DG04 synchronization receipt has an unexpected native time")
            contact_witness = application["public_contact_witness"]
            sync_finger_contact_force = math.fsum(
                float(force)
                for path, force in zip(
                    contact_witness["raw_contact_actor_paths"],
                    contact_witness["raw_contact_normal_forces_N"], strict=True,
                )
                if any(token in path for token in ("/left_finger", "/right_finger"))
            )
            sync_trace.append({
                "step_index": index,
                "reference_position_m": application["reference_position_m"],
                "follower_position_m": application["follower_position_m"],
                "relation_error_m": application["relation_error_m"],
                "reference_effort_N": application["reference_effort_N"],
                "target_m": application["reference_target_m"],
                "unobstructed_finger_contact_force_sum_N": sync_finger_contact_force,
                "raw_contact_actor_paths": contact_witness["raw_contact_actor_paths"],
                "raw_contact_normal_forces_N": contact_witness["raw_contact_normal_forces_N"],
                "raw_contact_signed_normal_force_scalars_N": contact_witness[
                    "raw_contact_signed_normal_force_scalars_N"
                ],
            })
        sync_final_q = (float(sync_trace[-1]["reference_position_m"]),
                        float(sync_trace[-1]["follower_position_m"]))
        sync_final_relation = sync_final_q[1] - sync_final_q[0]
        sync_follower_motion = sync_final_q[1] - sync_initial_q[1]
        if (abs(sync_final_relation) > RELATION_LIMIT_M
                or sync_follower_motion < 0.010
                or abs(sync_final_q[0] - 0.028) > 0.003):
            raise ValueError(
                "DG04 physical passive-mimic synchronization failed: "
                f"initial={sync_initial_q!r}, final={sync_final_q!r}, "
                f"follower_motion={sync_follower_motion!r}, limit={RELATION_LIMIT_M}"
            )
        _atomic_json(output.with_name(output.stem + ".sync.partial.json"), {
            "schema_version": "f05-dg04-native-mimic-n1-sync-partial-v1",
            "status": "SYNC_ORACLE_PASS_CONTACT_GATE_PENDING",
            "mode": mode,
            "input_head": subprocess.check_output(
                ["git", "-C", str(CORE), "rev-parse", "HEAD"], text=True,
            ).strip(),
            "source_id": input_v1.runtime_source.source_id,
            "source_closure_sha256": input_v1.runtime_source.source_closure_digest,
            "artifact_identity_sha256": input_v1.artifact.identity_hash,
            "execution_identity_sha256": input_v1.execution.identity_hash,
            "drive_receipt_identity_sha256": receipt.identity_sha256,
            "backend": metadata.backend,
            "device": metadata.device,
            "physics_dt_s": dt,
            "sync_steps": len(sync_trace),
            "initial_q_m": list(sync_initial_q),
            "final_q_m": list(sync_final_q),
            "final_relation_error_m": sync_final_relation,
            "follower_motion_m": sync_follower_motion,
            "leader_target_m": 0.028,
            "leader_target_error_m": abs(sync_final_q[0] - 0.028),
            "max_unobstructed_finger_contact_force_N": max(
                float(sample["unobstructed_finger_contact_force_sum_N"])
                for sample in sync_trace
            ),
            "oracle": {
                "relation_abs_max_m": RELATION_LIMIT_M,
                "follower_motion_min_m": 0.010,
                "leader_target_error_max_m": 0.003,
            },
            "trace": sync_trace,
            "claim_limit": "N1 synchronization segment only; blocked contact/effort gate pending; no source-softness equivalence or qualification",
        })

        open_sample = _clone_reset(base, tag="contact-open", finger_q=(0.04, 0.04))
        open_targets = _active_targets(input_v1, metadata, open_sample, leader_m=0.04)
        _write_reset(input_v1, native_io, open_sample, open_targets)
        hand_state, _open_q, _open_qd = _read_finger_state(native_io)
        hand_pose = hand_state.frame_pose_world.get("panda-main/hand")
        if hand_pose is None:
            raise ValueError("DG04 typed public state omits the source-bound panda-main/hand pose")
        cube_center = _hand_local_offset_world(hand_pose, (0.0, 0.0, CONTACT_LOCAL_Z_M))
        from task_env.artifacts.contracts import PoseWorld

        cube_pose = PoseWorld(cube_center, hand_pose.quaternion_wxyz)
        contact_sample = _clone_reset(
            base, tag="blocked-contact", finger_q=(0.04, 0.04), cube_pose=cube_pose,
        )
        contact_reset = _write_reset(
            input_v1, native_io, contact_sample,
            _active_targets(input_v1, metadata, contact_sample, leader_m=0.04),
        )
        contact_targets = _active_targets(
            input_v1, metadata, contact_sample, leader_m=CONTACT_TARGET_M,
        )
        contact_ack = _set_target(native_io, contact_targets, "blocked_contact_leader_0.005m")
        if "finger_joint2" in contact_ack.native_names:
            raise ValueError("DG04 blocked-contact detector unexpectedly commanded the passive follower")
        contact_trace = []
        finger_contact_steps = []
        max_finger_normal_force = 0.0
        max_applied_effort = 0.0
        min_contact_leader_q = math.inf
        contact_partial_path = output.with_name(output.stem + ".contact.partial.json")

        def persist_contact_partial(status: str) -> None:
            final_relation = None
            if contact_trace:
                final_relation = float(contact_trace[-1]["follower_q_m"]) - float(
                    contact_trace[-1]["leader_q_m"]
                )
            _atomic_json(contact_partial_path, {
                "schema_version": "f05-dg04-native-mimic-n1-contact-partial-v1",
                "status": status,
                "mode": mode,
                "input_head": subprocess.check_output(
                    ["git", "-C", str(CORE), "rev-parse", "HEAD"], text=True,
                ).strip(),
                "source_id": input_v1.runtime_source.source_id,
                "artifact_identity_sha256": input_v1.artifact.identity_hash,
                "execution_identity_sha256": input_v1.execution.identity_hash,
                "drive_receipt_identity_sha256": receipt.identity_sha256,
                "target_identity_sha256": contact_ack.target_identity_sha256,
                "bootstrap_steps": bootstrap_steps,
                "sync_steps": SYNC_STEPS,
                "contact_steps_requested": contact_steps,
                "contact_steps_completed": len(contact_trace),
                "effort_measurement_api": "Articulation.get_dof_projected_joint_forces",
                "effort_measurement_semantics": "projected_active_joint_force",
                "max_finger_contact_normal_force_N": max_finger_normal_force,
                "max_projected_leader_effort_abs_N": max_applied_effort,
                "min_blocked_leader_q_m": min_contact_leader_q,
                "final_mimic_relation_error_m": final_relation,
                "finger_contact_step_indices": list(finger_contact_steps),
                "contact_trace": contact_trace,
                "oracle": {
                    "blocked_leader_q_min_m": CONTACT_TARGET_M + CONTACT_MIN_BLOCKED_GAP_M,
                    "mimic_relation_abs_max_m": RELATION_LIMIT_M,
                    "minimum_finger_contact_force_N": CONTACT_MIN_NORMAL_FORCE_N,
                    "projected_leader_effort_min_N": MIN_APPLIED_LEADER_EFFORT_N,
                    "projected_leader_effort_max_N": EFFORT_CAP_N,
                },
                "claim_limit": "N1 blocked-contact/effort diagnostic only; no source-softness equivalence or qualification",
            })

        for index in range(1, contact_steps + 1):
            native_attempts = native_steps + 1
            application, native_receipt = _advance(
                native_io, step_index=index,
                target_identity=contact_ack.target_identity_sha256,
                receipt_identity=receipt.identity_sha256,
                progress_path=progress_path, mode=mode,
                bootstrap_steps=bootstrap_steps, native_steps=native_steps,
            )
            native_steps += 1
            if abs(float(native_receipt.simulation_time_s) - index * dt) > 1e-12:
                raise ValueError("DG04 blocked-contact receipt has an unexpected native time")
            witness = application["public_contact_witness"]
            path_force = tuple(zip(
                witness["raw_contact_actor_paths"],
                witness["raw_contact_normal_forces_N"], strict=True,
            ))
            finger_force = math.fsum(
                float(force) for path, force in path_force
                if any(token in path for token in ("/left_finger", "/right_finger", "finger_joint1", "finger_joint2"))
            )
            q = float(application["reference_position_m"])
            effort = abs(float(application["reference_effort_N"]))
            max_finger_normal_force = max(max_finger_normal_force, finger_force)
            max_applied_effort = max(max_applied_effort, effort)
            min_contact_leader_q = min(min_contact_leader_q, q)
            if finger_force >= CONTACT_MIN_NORMAL_FORCE_N:
                finger_contact_steps.append(index)
            contact_trace.append({
                "step_index": index,
                "leader_q_m": q,
                "follower_q_m": float(application["follower_position_m"]),
                "relation_error_m": float(application["relation_error_m"]),
                "leader_applied_effort_N": float(application["reference_effort_N"]),
                "declared_effort_cap_N": float(application["maximum_effort_N"]),
                "finger_contact_normal_force_sum_N": finger_force,
                "raw_contact_actor_paths": witness["raw_contact_actor_paths"],
                "raw_contact_normal_force_magnitudes_N": witness["raw_contact_normal_forces_N"],
                "raw_contact_signed_normal_force_scalars_N": witness[
                    "raw_contact_signed_normal_force_scalars_N"
                ],
                "raw_contact_normals_world": witness["raw_contact_normals_world"],
                "raw_contact_separations_m": witness["raw_contact_separations_m"],
            })
            if index % 10 == 0 or index == contact_steps:
                persist_contact_partial("CONTACT_PROBE_COMPLETE_PENDING_ORACLE")
        final_contact = contact_trace[-1]
        contact_relation = float(final_contact["follower_q_m"]) - float(final_contact["leader_q_m"])
        if (not finger_contact_steps
                or max_finger_normal_force < CONTACT_MIN_NORMAL_FORCE_N
                or min_contact_leader_q <= CONTACT_TARGET_M + CONTACT_MIN_BLOCKED_GAP_M
                or abs(contact_relation) > RELATION_LIMIT_M
                or max_applied_effort < MIN_APPLIED_LEADER_EFFORT_N
                or max_applied_effort > EFFORT_CAP_N + 1e-6):
            raise ValueError(
                "DG04 blocked-contact/effort-cap gate failed: "
                f"finger_contact_steps={len(finger_contact_steps)}, "
                f"max_measured_finger_contact_force_N={max_finger_normal_force!r}, "
                f"min_leader_q_m={min_contact_leader_q!r}, target_m={CONTACT_TARGET_M}, "
                f"max_actual_leader_effort_N={max_applied_effort!r}, cap_N={EFFORT_CAP_N}, "
                f"final_relation_m={contact_relation!r}"
            )

        from isaacsim.core.simulation_manager import SimulationManager

        physics_after = int(SimulationManager.get_num_physics_steps())
        expected_delta = native_steps
        if physics_after - physics_before != expected_delta:
            raise ValueError(
                f"DG04 native probe counter mismatch: before={physics_before}, after={physics_after}, "
                f"expected_delta={expected_delta}"
            )
        _checkpoint(progress_path, mode, "native_mimic_sync_contact_pass",
                    bootstrap_steps=bootstrap_steps, native_steps=native_steps, exact=True)
        return {
            "schema_version": "f05-dg04-native-mimic-n1-receipt-v1",
            "status": "PASS_DIAGNOSTIC_ONLY",
            "package_id": "F05_DG04_WINDOW004_NATIVE_ADAPTATION_CORE_CLOSURE",
            "mode": mode,
            "core_branch": subprocess.check_output(["git", "-C", str(CORE), "branch", "--show-current"], text=True).strip(),
            "input_head": subprocess.check_output(["git", "-C", str(CORE), "rev-parse", "HEAD"], text=True).strip(),
            "source_id": input_v1.runtime_source.source_id,
            "source_closure_sha256": input_v1.runtime_source.source_closure_digest,
            "delivery_sha256": input_v1.runtime_source.scene_source.loaded_delivery.delivery_sha256,
            "artifact_identity_sha256": input_v1.artifact.identity_hash,
            "execution_identity_sha256": input_v1.execution.identity_hash,
            "drive_receipt_identity_sha256": receipt.identity_sha256,
            "provider_build_identity": metadata.provider_build_identity,
            "physics_backend": metadata.backend,
            "physics_device": metadata.device,
            "pxr_runtime_identity": pxr_runtime_identity,
            "native_dof_names": list(metadata.native_dof_names),
            "bootstrap_receipt": bootstrap,
            "bootstrap_attempted_steps": bootstrap_steps,
            "budget": {
                "sync_steps": SYNC_STEPS,
                "blocked_contact_steps": contact_steps,
                "native_steps_excluding_bootstrap": native_steps,
                "total_native_attempted_steps": bootstrap_steps + native_steps,
                "max_attempted_steps": max_attempted_steps,
            },
            "oracle": {
                "sync_initial_q_m": list(sync_initial_q),
                "sync_initial_qd_m_s": list(sync_initial_qd),
                "sync_leader_only_target_m": 0.028,
                "sync_final_q_m": list(sync_final_q),
                "sync_final_relation_error_m": sync_final_relation,
                "sync_follower_motion_m": sync_follower_motion,
                "sync_relation_abs_max_m": RELATION_LIMIT_M,
                "sync_follower_motion_min_m": 0.010,
                "sync_trace": sync_trace,
                "blocked_contact_geometry": {
                    "cube_edge_m": 0.06,
                    "hand_local_cube_center_m": [0.0, 0.0, CONTACT_LOCAL_Z_M],
                    "basis": "frozen source finger mesh local-z extent 0.0584..0.1123 m; cube 60 mm",
                    "cube_center_world_m": list(cube_center),
                    "cube_orientation_wxyz": list(hand_pose.quaternion_wxyz),
                    "reset_step_count": 0,
                },
                "blocked_contact_leader_target_m": CONTACT_TARGET_M,
                "blocked_contact_min_q_minus_target_m": CONTACT_MIN_BLOCKED_GAP_M,
                "blocked_contact_final_q_m": final_contact["leader_q_m"],
                "blocked_contact_contact_steps": finger_contact_steps,
                "blocked_contact_max_measured_normal_force_N": max_finger_normal_force,
                "blocked_contact_min_measured_normal_force_N": CONTACT_MIN_NORMAL_FORCE_N,
                "max_public_applied_leader_effort_N": max_applied_effort,
                "effort_measurement_api": "Articulation.get_dof_projected_joint_forces",
                "effort_measurement_semantics": "projected_active_joint_force",
                "declared_drive_effort_cap_N": EFFORT_CAP_N,
                "minimum_observed_applied_leader_effort_N": MIN_APPLIED_LEADER_EFFORT_N,
                "contact_trace": contact_trace,
                "reset_receipts": {
                    "sync": sync_reset.to_mapping(),
                    "blocked_contact": contact_reset.to_mapping(),
                },
                "physical_response_claim": "native mimic sync and blocked finger contact only; source solimp/solref and tendon force-law equivalence are deferred",
            },
            "physics_step_counter": {
                "before": physics_before,
                "after": physics_after,
                "expected_delta": expected_delta,
            },
            "wall_seconds_worker": time.monotonic() - began,
        }
    except BaseException:
        if bootstrap_steps is None and native_io is not None:
            try:
                bootstrap_steps = _bootstrap_steps(dict(native_io.bootstrap_receipt()))
                _checkpoint(progress_path, mode, "native_mimic_probe_failed",
                            bootstrap_steps=bootstrap_steps, native_steps=native_steps, exact=True)
            except BaseException:
                _checkpoint(progress_path, mode, "native_mimic_failure_step_count_unavailable",
                            bootstrap_steps=0, native_steps=native_steps, exact=False)
        elif bootstrap_steps is not None:
            _checkpoint(progress_path, mode, "native_mimic_probe_failed",
                        bootstrap_steps=bootstrap_steps, native_steps=native_attempts, exact=True)
        raise
    finally:
        if native_io is not None:
            try:
                native_io.close()
            finally:
                native_io.close_runtime_owner()
        elif app_opened:
            app_owner.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("native_mimic_sync_contact",))
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument("--max-attempted-steps", type=int, required=True)
    parser.add_argument("--max-bootstrap-steps", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    began = time.monotonic()
    progress_path = args.output.with_name(args.output.stem + ".progress.json")
    try:
        receipt = run(
            mode=args.mode,
            contact_steps=args.steps,
            output=args.output,
            progress_path=progress_path,
            max_attempted_steps=args.max_attempted_steps,
            max_bootstrap_steps=args.max_bootstrap_steps,
        )
        receipt["wall_seconds_worker"] = time.monotonic() - began
        _atomic_json(args.output, receipt)
        print(json.dumps({key: value for key, value in receipt.items() if key != "oracle"},
                         sort_keys=True, indent=2, allow_nan=False))
        _terminate_worker(0)
    except BaseException:
        _atomic_json(args.output.with_name(args.output.stem + ".failure.json"), {
            "schema_version": "f05-dg04-native-mimic-n1-failure-v1",
            "mode": args.mode,
            "wall_seconds_worker": time.monotonic() - began,
            "traceback": traceback.format_exc(),
            "contact_partial_path": (
                str(args.output.with_name(args.output.stem + ".contact.partial.json"))
                if args.output.with_name(args.output.stem + ".contact.partial.json").is_file()
                else None
            ),
        })
        traceback.print_exc()
        _terminate_worker(1)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
