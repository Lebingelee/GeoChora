"""One frozen R02c MuJoCo CPU probe; execute only under its package contract."""
from __future__ import annotations

import hashlib
import json
import math
import os
import argparse
from pathlib import Path
import shutil
import sys
import tempfile
import time
import traceback
import warnings

import numpy as np


REPO = Path(__file__).resolve().parents[3]
CURRENT_ATTEMPT = "004"
ATTEMPT_ROOT = None
OUTPUT = None
CONTRACT_PATH = None
SNAPSHOT_PATH = None
EVIDENCE_PATH = None
LOG_PATH = None


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _validate_mujoco_runtime_identity(observed: dict, expected: dict) -> None:
    # MuJoCo 3.8.1's public mujoco.h defines mjVERSION_HEADER as 3008001.
    if (observed.get("version") != "3.8.1"
            or observed.get("runtime_version") != "3.8.1"
            or type(observed.get("mj_version")) is not int
            or observed["mj_version"] != 3008001):
        raise RuntimeError(
            "BLOCKED_PROVIDER: expected MuJoCo package/runtime/API "
            f"3.8.1/3.8.1/3008001; observed {observed.get('version')!r}/"
            f"{observed.get('runtime_version')!r}/{observed.get('mj_version')!r}"
        )
    for observed_key, expected_key, hash_key in (
        ("package_path", "package_init_path", "package_sha256"),
        ("binding_path", "binding_path", "binding_sha256"),
    ):
        path = str(Path(expected[expected_key]).resolve())
        if (observed.get(observed_key) != path
                or observed.get(hash_key) != expected["static_files_sha256"][expected[expected_key]]):
            raise RuntimeError(f"BLOCKED_PROVIDER: loaded {observed_key}/hash differs from frozen package")
    library = str(Path(expected["native_library_path"]).resolve())
    if not any(item.get("path") == library
               and item.get("sha256") == expected["native_library_sha256"]
               for item in observed.get("mapped_native_libraries", ())):
        raise RuntimeError("BLOCKED_PROVIDER: loaded MuJoCo native library path/hash differs")


def _json_default(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _write_json(path: Path, value) -> None:
    encoded = json.dumps(value, indent=2, sort_keys=True, allow_nan=False, default=_json_default) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _leaf_failure_progress(envs) -> list[dict]:
    """Retain the public typed dispatch receipt before Env.close drops Session."""
    rows = []
    for env in envs:
        try:
            progress = getattr(getattr(env, "session", None), "leaf_control_fault", None)
            if progress is None:
                continue
            rows.append({
                "schema_version": progress.schema_version,
                "effective_plan_identity_sha256": progress.effective_plan_identity_sha256,
                "source_boundary_id": progress.source_boundary_id,
                "attempted_writers": progress.attempted_writers,
                "applied_writers": progress.applied_writers,
                "unknown_writers": progress.unknown_writers,
                "acknowledged_writers": progress.acknowledged_writers,
                "ack_identity_hashes": progress.ack_identity_hashes,
                "command_identity_hashes": progress.command_identity_hashes,
                "prepared_commands": [item.to_mapping() for item in progress.prepared_commands],
                "returned_apply_results": [{
                    "schema_version": item.schema_version, "writer_id": item.writer_id,
                    "command_identity_sha256": item.command_identity_sha256,
                    "materialization_identity_sha256": item.materialization_identity_sha256,
                    "applied_slots": item.applied_slots, "ack": item.ack.to_mapping(),
                } for item in progress.returned_apply_results],
                "failed_writer": progress.failed_writer,
                "failure_phase": progress.failure_phase,
                "fault": progress.fault.to_mapping(),
            })
        except BaseException as error:
            rows.append({"capture_error": f"{type(error).__name__}: {error}"})
    return rows


def _rss_bytes() -> int | None:
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _package_bytes() -> int:
    total = 0
    for path in ATTEMPT_ROOT.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
    return total


def _raw_evidence_bytes() -> int:
    excluded = ATTEMPT_ROOT / "source-workspace"
    total = 0
    for path in ATTEMPT_ROOT.rglob("*"):
        if path.is_file() and excluded not in path.parents:
            total += path.stat().st_size
    return total


def _verify_frozen_inputs(contract: dict, snapshot: dict) -> None:
    if contract.get("task_id") != "PHASE-II-01-R02C" or contract.get("attempt") != CURRENT_ATTEMPT:
        raise RuntimeError("frozen native contract task identity mismatch")
    reference = contract.get("authorization", {}).get("reference")
    if (type(reference) is not str or not reference.strip()
            or reference != contract.get("authorization", {}).get("user_instruction_reference")):
        raise RuntimeError("native authorization reference is missing")
    if contract.get("authorization", {}).get("approved_by") is not None:
        raise RuntimeError("probe contract must not invent a named approver")
    if _sha256_file(Path(__file__)) != contract["sha256"]["probe_script"]:
        raise RuntimeError("R02c probe script changed after native freeze")
    if _sha256_file(SNAPSHOT_PATH) != contract["sha256"]["input_snapshot"]:
        raise RuntimeError("R02c input snapshot changed after native freeze")
    for rel, expected in contract["sha256"]["core_sources"].items():
        if _sha256_file(REPO / rel) != expected:
            raise RuntimeError(f"R02c Core source changed after native freeze: {rel}")
    for raw, expected in contract["provider_identity"]["static_files_sha256"].items():
        if _sha256_file(Path(raw)) != expected:
            raise RuntimeError(f"MuJoCo static package file changed before import: {raw}")
    if contract["source"]["closure_bytes"] > 128 * 1024 * 1024:
        raise RuntimeError("R02c derived source closure exceeds 128 MiB")
    if contract["budget"]["native_process_timeout_s"] != 300:
        raise RuntimeError("R02c process timeout differs from fixed contract")
    if contract["budget"]["max_materializations_total"] != 8:
        raise RuntimeError("R02c materialization budget differs from fixed contract")
    if contract["budget"]["max_native_process_invocations"] != 1:
        raise RuntimeError("R02c continuation allows only one native process")
    expected_counters = {
        "process_starts": 0, "materialization_attempts": 0, "reset_attempts": 0,
        "mj_step_calls": 0, "mj_forward_calls": 0, "outer_intervals": 0,
    }
    if contract.get("current_window_baseline_native_budget_consumed") != expected_counters:
        raise RuntimeError("current continuation native budget baseline must begin at zero")
    if snapshot.get("task_id") != "PHASE-II-01-R02C" or snapshot.get("attempt") != CURRENT_ATTEMPT:
        raise RuntimeError("R02c continuation input snapshot identity mismatch")
    branch = __import__("subprocess").run(
        ["git", "branch", "--show-current"], cwd=REPO, check=True, capture_output=True, text=True,
    ).stdout.strip()
    head = __import__("subprocess").run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, check=True, capture_output=True, text=True,
    ).stdout.strip()
    if (branch, head) != (contract["git"]["branch"], contract["git"]["frozen_head"]):
        raise RuntimeError("R02c branch/HEAD changed after native freeze")
    if _package_bytes() > contract["budget"]["max_output_bytes"]:
        raise RuntimeError("R02c output directory exceeds its byte budget before run")
    if _raw_evidence_bytes() > contract["budget"]["raw_evidence_limit_bytes"]:
        raise RuntimeError("R02c raw evidence exceeds its byte budget before run")


def _warning_numbers(data) -> tuple[int, ...]:
    return tuple(int(item.number) for item in data.warning)


def _capture_reset_state(model, data, episode: str) -> dict:
    return {
        "episode": episode,
        "model_dimensions": {
            "nq": int(model.nq), "nv": int(model.nv), "nu": int(model.nu),
            "njnt": int(model.njnt), "nbody": int(model.nbody),
            "neq": int(model.neq), "ntendon": int(model.ntendon),
        },
        "qpos": np.asarray(data.qpos, dtype=np.float64).tolist(),
        "qvel": np.asarray(data.qvel, dtype=np.float64).tolist(),
        "ctrl": np.asarray(data.ctrl, dtype=np.float64).tolist(),
        "time_s": float(data.time),
        "warnings": _warning_numbers(data),
    }


def _array_digest_rows(rows: list[dict]) -> None:
    for row in rows:
        for field in ("qpos", "qvel", "ctrl"):
            values = np.asarray(row[field], dtype=np.float64)
            if not np.isfinite(values).all():
                raise AssertionError(f"reset {row['episode']} {field} contains non-finite values")


def _typed_reset_values(env, scene) -> dict:
    state = env.state
    joints = {key: float(value) for key, value in state.joint_position.items()}
    velocities = {key: float(value) for key, value in state.joint_velocity.items()}
    frame_values = {
        f"{item.frame.entity_id}/{item.frame.frame_id}": item.pose_world
        for item in env.typed_state.view.frames
    }
    frames = {
        key: [*value.position, *value.quaternion_wxyz]
        for key, value in frame_values.items()
    }
    if not all(math.isfinite(value) for value in (*joints.values(), *velocities.values())):
        raise AssertionError("reset typed Joint state is non-finite")
    if any(not np.isfinite(np.asarray(value, dtype=np.float64)).all() for value in frames.values()):
        raise AssertionError("reset typed Frame state is non-finite")
    return {
        "control_step": int(state.control_step), "simulation_time_s": float(state.simulation_time),
        "joints": joints, "joint_velocities": velocities, "frames": frames,
        "boundary": env.typed_state.view.boundary.to_mapping(),
        "clock": env.typed_state.view.sample_clock.to_mapping(),
        "scene_identity_sha256": scene.identity_hash,
    }


def _reset_bytes_equal(first: dict, current: dict) -> bool:
    for key in ("qpos", "qvel", "ctrl"):
        if not np.array_equal(np.asarray(first[key]), np.asarray(current[key])):
            return False
    return first["time_s"] == current["time_s"] == 0.0


def _public_receipt_summary(receipt) -> dict:
    return {
        "schema_version": receipt.schema_version,
        "provenance_kind": receipt.provenance_kind,
        "identity_sha256": receipt.identity_sha256,
        "provider": receipt.provider_name,
        "provider_version": receipt.provider_version,
        "provider_build_sha256": receipt.provider_build_sha256,
        "backend": receipt.backend,
        "dimensions": {name: int(getattr(receipt, name))
                       for name in ("nq", "nv", "nu", "njnt", "nbody", "neq", "ntendon")},
        "joints": [{
            "canonical": f"{item.canonical_joint.entity_id}/{item.canonical_joint.joint_id}",
            "native_name": item.native_name, "native_id": item.native_joint_id,
            "qpos_address": item.qpos_address, "dof_address": item.dof_address,
            "position_unit": item.position_unit,
        } for item in receipt.joints],
        "actuators": [{
            "canonical": f"{item.canonical_actuator.entity_id}/{item.canonical_actuator.actuator_id}",
            "native_name": item.native_name, "native_id": item.native_actuator_id,
            "ctrl_slot": item.ctrl_slot, "ctrlrange": item.ctrlrange,
            "command_unit": item.command_unit,
            "transmission_target_kind": item.transmission_target_kind,
            "transmission_target_id": item.transmission_target_id,
        } for item in receipt.actuators],
        "frames": [{
            "canonical": f"{item.canonical_frame.entity_id}/{item.canonical_frame.frame_id}",
            "native_name": item.native_name, "native_body_id": item.native_body_id,
        } for item in receipt.frames],
        "tendons": [{"identity": item.tendon_identity, "native_name": item.native_name}
                    for item in receipt.tendons],
        "equality_identities": receipt.equality_identities,
    }


def _validate_materialization_receipt(receipt) -> None:
    dimensions = {name: int(getattr(receipt, name)) for name in
                  ("nq", "nv", "nu", "njnt", "neq", "ntendon")}
    if dimensions != {"nq": 9, "nv": 9, "nu": 8, "njnt": 9, "neq": 1, "ntendon": 1}:
        raise AssertionError(f"compiled Panda model dimensions differ from the frozen leaf contract: {dimensions}")
    expected_joints = {
        *(f"panda-main/joint{index}" for index in range(1, 8)),
        "panda-main/finger_joint1", "panda-main/finger_joint2",
    }
    actual_joints = {
        f"{item.canonical_joint.entity_id}/{item.canonical_joint.joint_id}"
        for item in receipt.joints
    }
    if actual_joints != expected_joints or len(receipt.joints) != 9:
        raise AssertionError("compiled native Joint receipt differs from the nine canonical Panda joints")
    expected_actuators = {f"panda-main/actuator{index}" for index in range(1, 9)}
    actual_actuators = {
        f"{item.canonical_actuator.entity_id}/{item.canonical_actuator.actuator_id}"
        for item in receipt.actuators
    }
    if actual_actuators != expected_actuators or len(receipt.actuators) != 8:
        raise AssertionError("compiled native Actuator receipt differs from the eight canonical actuators")
    if {item.ctrl_slot for item in receipt.actuators} != set(range(8)):
        raise AssertionError("compiled native actuator mapping does not cover slots 0..7 exactly")
    by_name = {item.native_name: item for item in receipt.actuators}
    for index in range(1, 8):
        item = by_name[f"actuator{index}"]
        if (item.ctrl_slot != index - 1 or item.command_unit != "radian"
                or item.transmission_target_kind != "joint"
                or item.transmission_target_id != f"joint{index}"):
            raise AssertionError(f"compiled Arm actuator{index} mapping differs from its canonical Joint")
    hand = by_name["actuator8"]
    if (hand.ctrl_slot != 7 or hand.ctrlrange != (0.0, 255.0)
            or hand.command_unit != "native_ctrl"
            or hand.transmission_target_kind != "tendon"
            or hand.transmission_target_id != "split"):
        raise AssertionError("compiled Hand actuator8 mapping differs from the split-tendon ctrl contract")
    if len(receipt.tendons) != 1 or len(receipt.equality_identities) != 1:
        raise AssertionError("compiled native receipt omitted the single split tendon or finger equality")


def _preview_commands(candidate, *, interval: int = 1) -> dict[str, dict]:
    from task_env.controllers.canonical.leaf_profiles import ArmPositionActionV1, HandPositionActionV1
    from task_env.runtime.sessions.leaf_control import prepare_leaf_command
    from task_env.tasks.position_candidate.leaf_candidate import (
        ARM_WRITER_ID, HAND_WRITER_ID, action_for_interval,
    )

    action_set = action_for_interval(
        candidate.scene, candidate.plan, interval, arm_active=True, hand_active=True,
    )
    env = candidate.env
    receipt = env.session.leaf_materialization_receipt
    commands = {}
    for writer_id, action in (
        (ARM_WRITER_ID, action_set.arm), (HAND_WRITER_ID, action_set.hand),
    ):
        if not isinstance(action, (ArmPositionActionV1, HandPositionActionV1)):
            raise TypeError("R02c preview expected typed Arm/Hand leaf Actions")
        command = prepare_leaf_command(
            env.leaf_plan, writer_id, action, env.typed_state, receipt,
            env.session.leaf_configuration_revision, scene=candidate.scene,
        )
        commands[writer_id] = {
            "command_identity_sha256": command.command_identity_sha256,
            "target_identity_sha256": command.target.identity_hash,
            "configuration_identity_sha256": command.effective_configuration_identity_sha256,
            "slot_values": [{"ctrl_slot": item.ctrl_slot, "value": float(item.value)}
                            for item in command.slot_values],
            "requested_opening_m": command.requested_opening_m,
            "servo_opening_m": command.servo_opening_m,
            "native_ctrl": command.native_ctrl,
        }
    return commands


def _alter_controls(path: Path, mutate) -> None:
    import h5py

    with h5py.File(path, "r") as source:
        raw = source["meta/structured_controls_v1_json"][()]
        raw = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    controls = json.loads(raw)
    mutate(controls)
    encoded = json.dumps(controls, sort_keys=True)
    with h5py.File(path, "r+") as target:
        del target["meta/structured_controls_v1_json"]
        target.create_dataset(
            "meta/structured_controls_v1_json", data=encoded,
            dtype=h5py.string_dtype(encoding="utf-8"),
        )


def _tamper_checks(source_h5: Path, reader) -> list[dict]:
    import h5py

    cases = {}
    cases["target_identity"] = lambda rows: rows[0]["writer_controls"][0]["controller_target"].__setitem__("identity_hash", "0" * 64)
    cases["ack_writer"] = lambda rows: rows[0]["writer_controls"][0]["canonical_action"]["application_ack"].__setitem__("writer_id", "tampered-writer")
    cases["prepared_command"] = lambda rows: rows[0]["writer_controls"][0]["canonical_action"]["prepared_command"]["slot_values"][0].__setitem__("value", 999.0)
    cases["source_digest"] = lambda rows: rows[0]["writer_controls"][0]["canonical_action"].__setitem__("source_closure_sha256", "0" * 64)
    cases["configuration_identity"] = lambda rows: rows[0]["writer_controls"][0]["canonical_action"].__setitem__("configuration_identity_sha256", "0" * 64)
    cases["missing_writer"] = lambda rows: rows[0]["writer_controls"].pop()

    results = []
    with tempfile.TemporaryDirectory(prefix="r02c-h5-tamper-") as directory:
        temp = Path(directory)
        for label, mutation in cases.items():
            destination = temp / f"{label}.h5"
            shutil.copy2(source_h5, destination)
            _alter_controls(destination, mutation)
            try:
                reader(destination)
            except Exception as error:
                results.append({"case": label, "rejected": True,
                                "error_type": type(error).__name__, "error": str(error)})
            else:
                raise AssertionError(f"leaf H5 reader accepted tampered {label}")

        destination = temp / "boundary-observation.h5"
        shutil.copy2(source_h5, destination)
        with h5py.File(destination, "r+") as root:
            values = root["obs/state/boundary_identity_sha256"]
            values[1, 0] = (int(values[1, 0]) + 1) % 256
        try:
            reader(destination)
        except Exception as error:
            results.append({"case": "boundary_observation", "rejected": True,
                            "error_type": type(error).__name__, "error": str(error)})
        else:
            raise AssertionError("leaf H5 reader accepted boundary-observation tampering")

        def duplicate_slot(rows):
            writer_rows = rows[0]["writer_controls"]
            arm_slot = writer_rows[0]["canonical_action"]["prepared_command"]["slot_values"][0]["ctrl_slot"]
            writer_rows[1]["applied_control"]["payload"]["applied_slots"] = [arm_slot]

        destination = temp / "duplicate-slot.h5"
        shutil.copy2(source_h5, destination)
        _alter_controls(destination, duplicate_slot)
        try:
            reader(destination)
        except Exception as error:
            results.append({"case": "duplicate_slot", "rejected": True,
                            "error_type": type(error).__name__, "error": str(error)})
        else:
            raise AssertionError("leaf H5 reader accepted duplicate native slot evidence")

        destination = temp / "t-plus-one.h5"
        shutil.copy2(source_h5, destination)
        with h5py.File(destination, "r+") as root:
            root.attrs["observation_count"] = 64
        try:
            reader(destination)
        except Exception as error:
            results.append({"case": "t_plus_one", "rejected": True,
                            "error_type": type(error).__name__, "error": str(error)})
        else:
            raise AssertionError("Generic H5 reader accepted a T/T+1 count mismatch")
    if len(results) != len(cases) + 3 or not all(row["rejected"] for row in results):
        raise AssertionError("R02c H5 tamper matrix is incomplete")
    return results


def _validate_h5_commands(independently_loaded, ctrl_by_episode_interval, episode, *, arm_active, hand_active):
    """Compare closed-H5 commands with separately observed per-interval ctrl."""
    from task_env.tasks.position_candidate.leaf_candidate import ARM_WRITER_ID, HAND_WRITER_ID
    from task_env.runtime.sessions.leaf_control import LeafPreparedCommandV1
    for interval, control in enumerate(independently_loaded["structured_controls"], start=1):
        rows = {item["writer_id"]: item for item in control.writer_controls}
        if set(rows) != {ARM_WRITER_ID, HAND_WRITER_ID} or len(control.writer_controls) != 2:
            raise AssertionError(f"{episode} H5 transition {interval} omitted/duplicated a leaf writer")
        seen_slots = set()
        actual_ctrl = ctrl_by_episode_interval[(episode, interval)]
        for writer_id, row in rows.items():
            command = LeafPreparedCommandV1.from_mapping(
                row["canonical_action"]["prepared_command"]
            )
            expected_slots = tuple(item.ctrl_slot for item in command.slot_values)
            applied_slots = tuple(row["applied_control"]["payload"]["applied_slots"])
            if applied_slots != expected_slots or seen_slots.intersection(expected_slots):
                raise AssertionError(f"{episode}/{writer_id} applied slots are not exact/disjoint")
            seen_slots.update(expected_slots)
            for slot_value in command.slot_values:
                if actual_ctrl[slot_value.ctrl_slot] != float(slot_value.value):
                    raise AssertionError(f"{episode}/{writer_id} native ctrl differs from stored command")
            if writer_id == ARM_WRITER_ID and not arm_active:
                if tuple(command.target.action.position_rad) != (
                    0.0, 0.0, 0.0, -1.57079, 0.0, 1.57079, -0.7853,
                ):
                    raise AssertionError(f"{episode} inactive Arm leaf did not retain its Position hold")
            if writer_id == HAND_WRITER_ID and not hand_active:
                if float(command.target.action.opening_m) != 0.076:
                    raise AssertionError(f"{episode} inactive Hand leaf did not retain its Position hold")
        if seen_slots != set(range(8)):
            raise AssertionError(f"{episode} leaf H5 does not cover all native actuator slots")


def _run_native(contract: dict, snapshot: dict, started: float, log_stream, results) -> int:
    if "mujoco" in sys.modules:
        raise RuntimeError("BLOCKED_PROVIDER: MuJoCo was imported before the frozen runtime identity check")

    from task_env.tasks.position_candidate.leaf_candidate import (
        ARM_WRITER_ID, HAND_WRITER_ID, action_for_interval, build_leaf_position_candidate,
    )
    from task_env.tasks.reference_env import SelectedReferenceEnv
    import task_env.tasks.reference_env as reference_env_module

    results.update({
        "status": "RUNNING", "provider": "mujoco", "version": "3.8.1",
        "backend": "cpu", "episodes": [], "tamper_checks": [],
        "native_calls": {"mj_step": 0, "mj_forward": 0, "mj_resetData": 0,
                         "materialize_control": 0},
        "resource_samples": [], "failure": None,
        "historical_attempt001_activity": contract.get("historical_attempt001_activity"),
        "historical_attempt002_activity": contract.get("historical_attempt002_activity"),
        "historical_attempt003_activity": contract.get("historical_attempt003_activity"),
        "current_window_baseline_native_budget_consumed": contract[
            "current_window_baseline_native_budget_consumed"],
        "started_monotonic_s": started,
    })
    active_episode = {"name": "preflight"}
    native_step_by_episode: dict[str, int] = {}
    warning_max_by_data: dict[int, tuple[int, ...]] = {}
    reset_pending: set[int] = set()
    reset_snapshots: list[dict] = []
    ctrl_by_episode_interval: dict[tuple[str, int], list[float]] = {}
    originals = {}
    envs = []
    session_models: dict[int, dict] = {}
    materialize_by_episode: dict[str, int] = {}

    def note(message, **fields):
        record = {"time_monotonic_s": time.monotonic(), "message": message, **fields}
        log_stream.write(json.dumps(record, sort_keys=True, allow_nan=False, default=_json_default) + "\n")
        log_stream.flush()

    try:
        import mujoco
        import mujoco._functions as native_functions
        loaded_path = Path(mujoco.__file__).resolve()
        native_path = Path(native_functions.__file__).resolve()
        maps = []
        for line in Path("/proc/self/maps").read_text().splitlines():
            fields = line.split()
            if fields and fields[-1].startswith("/") and "libmujoco" in fields[-1]:
                mapped = Path(fields[-1]).resolve()
                if mapped not in maps:
                    maps.append(mapped)
        # Save the actual values before deciding admission, including failures.
        observed = results["loaded_provider"] = {
            "version": str(mujoco.__version__),
            "package_path": str(loaded_path), "package_sha256": _sha256_file(loaded_path),
            "binding_path": str(native_path), "binding_sha256": _sha256_file(native_path),
            "mapped_native_libraries": [{"path": str(path), "sha256": _sha256_file(path)} for path in maps],
            "renderer_initialized": False,
        }
        observed["mj_version"] = int(mujoco.mj_version())
        observed["runtime_version"] = str(mujoco.mj_versionString())
        note("provider_runtime_observed", provider=observed)
        _write_json(EVIDENCE_PATH, results)
        _validate_mujoco_runtime_identity(observed, contract["provider_identity"])
        note("provider_runtime_verified", provider=observed)

        originals["mj_step"] = mujoco.mj_step
        originals["mj_forward"] = mujoco.mj_forward
        originals["mj_resetData"] = mujoco.mj_resetData

        def sample_warnings(data):
            values = _warning_numbers(data)
            ident = id(data)
            previous = warning_max_by_data.get(ident, tuple(0 for _ in values))
            warning_max_by_data[ident] = tuple(max(a, b) for a, b in zip(previous, values, strict=True))
            return values

        def wrapped_reset(model, data, *args, **kwargs):
            value = originals["mj_resetData"](model, data, *args, **kwargs)
            results["native_calls"]["mj_resetData"] += 1
            reset_pending.add(id(data))
            warning_max_by_data[id(data)] = _warning_numbers(data)
            session_models[id(model)] = {
                "episode": active_episode["name"],
                "dimensions": {name: int(getattr(model, name))
                               for name in ("nq", "nv", "nu", "njnt", "nbody", "neq", "ntendon")},
            }
            return value

        def wrapped_forward(model, data, *args, **kwargs):
            if id(data) in reset_pending:
                reset_snapshots.append(_capture_reset_state(model, data, active_episode["name"]))
                reset_pending.remove(id(data))
            value = originals["mj_forward"](model, data, *args, **kwargs)
            results["native_calls"]["mj_forward"] += 1
            sample_warnings(data)
            return value

        def wrapped_step(model, data, *args, **kwargs):
            episode = active_episode["name"]
            native_index = native_step_by_episode.get(episode, 0)
            substep = native_index % 5
            interval = native_index // 5 + 1
            if substep == 0:
                ctrl_by_episode_interval[(episode, interval)] = [float(v) for v in data.ctrl]
            before_time = float(data.time)
            value = originals["mj_step"](model, data, *args, **kwargs)
            after_time = float(data.time)
            if abs((after_time - before_time) - 0.002) > 1.0e-12:
                raise AssertionError(f"{episode} native step clock delta is {after_time-before_time!r}")
            native_step_by_episode[episode] = native_index + 1
            results["native_calls"]["mj_step"] += 1
            sample_warnings(data)
            return value

        mujoco.mj_resetData = wrapped_reset
        mujoco.mj_forward = wrapped_forward
        mujoco.mj_step = wrapped_step

        original_materialize = reference_env_module.materialize_control

        def counted_materialize(*args, **kwargs):
            episode = active_episode["name"]
            results["native_calls"]["materialize_control"] += 1
            materialize_by_episode[episode] = materialize_by_episode.get(episode, 0) + 1
            return original_materialize(*args, **kwargs)

        reference_env_module.materialize_control = counted_materialize

        workspace = ATTEMPT_ROOT / "source-workspace"
        default_candidate = build_leaf_position_candidate(
            workspace, environment_type=SelectedReferenceEnv, arm_gain=2.5,
        )
        override_candidate = build_leaf_position_candidate(
            workspace, environment_type=SelectedReferenceEnv, arm_gain=3.0,
        )
        envs.extend((default_candidate.env, override_candidate.env))
        if default_candidate.source.source_closure_digest != contract["source"]["closure_sha256"]:
            raise RuntimeError("R02c candidate source closure changed after native freeze")
        if override_candidate.source.source_closure_digest != default_candidate.source.source_closure_digest:
            raise RuntimeError("R02c Arm override changed the frozen physical source closure")
        if (default_candidate.plan.identity_sha256 != contract["plans"]["default_identity_sha256"]
                or override_candidate.plan.identity_sha256 != contract["plans"]["override_identity_sha256"]):
            raise RuntimeError("R02c effective leaf plan changed after native freeze")
        from task_env.runtime.sessions.source import lower_mujoco_scene_source
        lowered_xml, assets = lower_mujoco_scene_source(
            default_candidate.source.scene_source, default_candidate.scene,
            default_candidate.source.source_closure_digest,
        )
        if _sha256_bytes(lowered_xml.encode("utf-8")) != contract["source"]["lowered_xml_sha256"]:
            raise RuntimeError("R02c lowered MuJoCo XML changed after native freeze")
        if {name: _sha256_bytes(value) for name, value in assets.items()} != contract["source"]["assets_sha256"]:
            raise RuntimeError("R02c MuJoCo asset closure changed after native freeze")
        note("candidate_source_verified", closure=default_candidate.source.source_closure_digest,
             plan_default=default_candidate.plan.identity_sha256,
             plan_override=override_candidate.plan.identity_sha256,
             closure_asset_count=len(assets))

        reset_reference = None
        all_metrics = {}
        e3_preview = None
        e4_preview = None
        scenarios = (
            ("E1-arm-only", default_candidate, default_candidate.env, True, False),
            ("E2-hand-only", default_candidate, default_candidate.env, False, True),
            ("E3-simultaneous-default", default_candidate, default_candidate.env, True, True),
            ("E4-simultaneous-arm-gain-3", override_candidate, override_candidate.env, True, True),
        )

        for episode, candidate, env, arm_active, hand_active in scenarios:
            active_episode["name"] = episode
            native_step_by_episode[episode] = 0
            result_row = {
                "episode": episode, "status": "RUNNING", "arm_active": arm_active,
                "hand_active": hand_active, "seed": 31, "requested_outer_intervals": 64,
                "materialize_calls": 0, "reset_data_calls_before": results["native_calls"]["mj_resetData"],
                "outer_intervals": 0, "mj_step_calls": 0, "mj_forward_calls": 0,
            }
            results["episodes"].append(result_row)
            before_materialize = results["native_calls"]["materialize_control"]
            before_reset_data = results["native_calls"]["mj_resetData"]
            before_step = results["native_calls"]["mj_step"]
            before_forward = results["native_calls"]["mj_forward"]
            obs, info = env.reset(seed=31)
            result_row["materialize_calls"] = results["native_calls"]["materialize_control"] - before_materialize
            result_row["reset_data_calls"] = results["native_calls"]["mj_resetData"] - before_reset_data
            if result_row["materialize_calls"] != 1 or result_row["reset_data_calls"] != 1:
                raise AssertionError(f"{episode} did not perform exactly one materialization/reset")
            if env.state.control_step != 0 or env.state.simulation_time != 0.0:
                raise AssertionError(f"{episode} ResetPlan did not produce a zero-time boundary")
            if not env.observation_space.contains(obs):
                raise AssertionError(f"{episode} reset observation is outside its declared space")
            snapshot = next((row for row in reversed(reset_snapshots) if row["episode"] == episode), None)
            if snapshot is None:
                raise AssertionError(f"{episode} native reset state was not observed at public mj_forward")
            if reset_reference is None:
                reset_reference = snapshot
            elif not _reset_bytes_equal(reset_reference, snapshot):
                raise AssertionError(f"{episode} qpos/qvel/ctrl/time differs from the first deterministic reset")
            _array_digest_rows([snapshot])
            reset_public = _typed_reset_values(env, candidate.scene)
            if reset_public["control_step"] != 0 or reset_public["simulation_time_s"] != 0.0:
                raise AssertionError(f"{episode} typed ResetPlan boundary is not step/time zero")
            required_start = {
                "panda-main/joint1": 0.0, "panda-main/joint2": 0.0,
                "panda-main/joint3": 0.0, "panda-main/joint4": -1.57079,
                "panda-main/joint5": 0.0, "panda-main/joint6": 1.57079,
                "panda-main/joint7": -0.7853,
                "panda-main/finger_joint1": 0.038,
                "panda-main/finger_joint2": 0.038,
            }
            if any(abs(reset_public["joints"][key] - value) > 1.0e-12
                   for key, value in required_start.items()):
                raise AssertionError(f"{episode} reset Joint state differs from the fixed authored ResetPlan")
            receipt = env.session.leaf_materialization_receipt
            _validate_materialization_receipt(receipt)
            result_row["materialization"] = _public_receipt_summary(receipt)
            result_row["reset_public"] = reset_public
            result_row["reset_native"] = snapshot
            native_joint_addresses = {
                f"{item.canonical_joint.entity_id}/{item.canonical_joint.joint_id}": item.qpos_address
                for item in receipt.joints
            }
            for canonical_name, expected_value in required_start.items():
                address = native_joint_addresses[canonical_name]
                if abs(float(snapshot["qpos"][address]) - expected_value) > 1.0e-12:
                    raise AssertionError(
                        f"{episode} native qpos for {canonical_name} differs from the fixed ResetPlan"
                    )
            if any(value != 0.0 for value in snapshot["qvel"]):
                raise AssertionError(f"{episode} native qvel reset is not exactly zero")
            expected_ctrl = {
                **{f"actuator{index}": required_start[f"panda-main/joint{index}"]
                   for index in range(1, 8)},
                "actuator8": 242.25,
            }
            for actuator in receipt.actuators:
                if abs(float(snapshot["ctrl"][actuator.ctrl_slot])
                       - expected_ctrl[actuator.native_name]) > 1.0e-12:
                    raise AssertionError(
                        f"{episode} native reset ctrl for {actuator.native_name} differs from the fixed ResetPlan"
                    )
            result_row["provider_materialization_id"] = env.session.provider_materialization_id
            result_row["reset_episode_id"] = env.session.episode_id
            result_row["reset_sample_id"] = reset_public["boundary"]["reset_sample_id"]
            results["resource_samples"].append({"episode": episode, "phase": "reset",
                                                 "rss_bytes": _rss_bytes(),
                                                 "package_bytes": _package_bytes()})

            if episode == "E3-simultaneous-default":
                counts_before = (results["native_calls"]["mj_step"], results["native_calls"]["mj_forward"])
                e3_preview = _preview_commands(candidate)
                if counts_before != (results["native_calls"]["mj_step"], results["native_calls"]["mj_forward"]):
                    raise AssertionError("E3 stateless prepare comparison touched native integration/forward")
            if episode == "E4-simultaneous-arm-gain-3":
                counts_before = (results["native_calls"]["mj_step"], results["native_calls"]["mj_forward"])
                e4_preview = _preview_commands(candidate)
                if counts_before != (results["native_calls"]["mj_step"], results["native_calls"]["mj_forward"]):
                    raise AssertionError("E4 stateless prepare comparison touched native integration/forward")
                arm_default = e3_preview[ARM_WRITER_ID]
                arm_override = e4_preview[ARM_WRITER_ID]
                hand_default = e3_preview[HAND_WRITER_ID]
                hand_override = e4_preview[HAND_WRITER_ID]
                if (arm_default["configuration_identity_sha256"] == arm_override["configuration_identity_sha256"]
                        or arm_default["slot_values"] == arm_override["slot_values"]):
                    raise AssertionError("E3/E4 Arm config/command did not change under the fixed override")
                if (hand_default["configuration_identity_sha256"] != hand_override["configuration_identity_sha256"]
                        or hand_default["slot_values"] != hand_override["slot_values"]
                        or hand_default["native_ctrl"] != hand_override["native_ctrl"]):
                    raise AssertionError("E3/E4 Hand config/command changed under Arm-only override")
                result_row["e3_e4_preview_comparison"] = {
                    "arm_configuration_changed": True, "arm_command_changed": True,
                    "hand_configuration_equal": True, "hand_command_equal": True,
                    "e3": {ARM_WRITER_ID: arm_default, HAND_WRITER_ID: hand_default},
                    "e4": {ARM_WRITER_ID: arm_override, HAND_WRITER_ID: hand_override},
                }

            h5_path = OUTPUT / f"{episode}.h5"
            env.start_recording(h5_path)
            q1_trace = [float(env.state.joint_position["panda-main/joint1"])]
            opening_trace = [sum(float(env.state.joint_position[f"panda-main/finger_joint{i}"]) for i in (1, 2))]
            finger_difference_trace = [abs(
                float(env.state.joint_position["panda-main/finger_joint1"])
                - float(env.state.joint_position["panda-main/finger_joint2"])
            )]
            tcp_trace = [list(obs["state"]["ee_pose"])]
            hand_pose_trace = [list(obs["state"]["hand_pose"])]
            clock_trace = [float(env.state.simulation_time)]
            last_terminated = False
            last_truncated = False
            ctrl_slots_by_writer = {
                entry.binding.writer_id: tuple(
                    item.ctrl_slot for item in receipt.actuators
                    if item.canonical_actuator in entry.binding.actuator_order
                ) for entry in env.leaf_plan.leaves
            }
            if set(ctrl_slots_by_writer[ARM_WRITER_ID]).intersection(ctrl_slots_by_writer[HAND_WRITER_ID]):
                raise AssertionError(f"{episode} writers do not own disjoint native ctrl slots")
            for interval in range(1, 65):
                action = action_for_interval(
                    candidate.scene, candidate.plan, interval,
                    arm_active=arm_active, hand_active=hand_active,
                )
                obs, reward, terminated, truncated, info = env.step(action)
                last_terminated, last_truncated = bool(terminated), bool(truncated)
                if terminated or (truncated and interval != 64):
                    raise AssertionError(f"{episode} stopped before its fixed 64-interval horizon")
                if (env.state.control_step != interval
                        or abs(float(env.state.simulation_time) - interval * 0.01) > 1.0e-12):
                    raise AssertionError(f"{episode} public clock/control-step mismatch at {interval}")
                if not math.isfinite(float(reward)):
                    raise AssertionError(f"{episode} returned a non-finite reward")
                state_joints = env.state.joint_position
                state_velocities = env.state.joint_velocity
                if not all(math.isfinite(float(value)) for value in (*state_joints.values(), *state_velocities.values())):
                    raise AssertionError(f"{episode} typed/canonical Joint state is non-finite")
                if not np.isfinite(np.asarray(obs["state"]["ee_pose"], dtype=np.float64)).all():
                    raise AssertionError(f"{episode} Arm TCP pose is non-finite")
                if not np.isfinite(np.asarray(obs["state"]["hand_pose"], dtype=np.float64)).all():
                    raise AssertionError(f"{episode} Hand frame pose is non-finite")
                q1_trace.append(float(state_joints["panda-main/joint1"]))
                opening_trace.append(sum(float(state_joints[f"panda-main/finger_joint{i}"]) for i in (1, 2)))
                finger_difference_trace.append(abs(
                    float(state_joints["panda-main/finger_joint1"])
                    - float(state_joints["panda-main/finger_joint2"])
                ))
                tcp_trace.append([float(v) for v in obs["state"]["ee_pose"]])
                hand_pose_trace.append([float(v) for v in obs["state"]["hand_pose"]])
                clock_trace.append(float(env.state.simulation_time))
                if interval > 64 or (episode, interval) not in ctrl_by_episode_interval:
                    raise AssertionError(f"{episode} actual public mj_step control snapshot missing interval {interval}")
                actual_ctrl = ctrl_by_episode_interval[(episode, interval)]
                if len(actual_ctrl) != 8 or not np.isfinite(np.asarray(actual_ctrl)).all():
                    raise AssertionError(f"{episode} actual native ctrl vector is malformed/non-finite")
                result_row["outer_intervals"] += 1
                if interval % 8 == 0 or interval == 64:
                    results["resource_samples"].append({"episode": episode, "phase": f"interval-{interval}",
                                                         "rss_bytes": _rss_bytes(),
                                                         "package_bytes": _package_bytes()})
                    if results["native_calls"]["mj_step"] > contract["budget"]["max_mj_step_calls"]:
                        raise AssertionError("R02c fixed mj_step budget exceeded")
                    if _package_bytes() > contract["budget"]["max_output_bytes"]:
                        raise AssertionError("R02c package byte budget exceeded")
                    if _raw_evidence_bytes() > contract["budget"]["raw_evidence_limit_bytes"]:
                        raise AssertionError("R02c raw Evidence/H5/log byte budget exceeded")

            if env.state.control_step != 64 or last_terminated or not last_truncated:
                raise AssertionError(f"{episode} did not complete exactly its 64-interval horizon")
            if len(clock_trace) != 65 or any(
                abs(value - index * 0.01) > 1.0e-12 for index, value in enumerate(clock_trace)
            ):
                raise AssertionError(f"{episode} evaluation-boundary clock trace violates fixed 100Hz oracle")
            for warning_vector in warning_max_by_data.values():
                if any(warning_vector):
                    raise AssertionError(f"{episode} native MuJoCo warning count increased: {warning_vector}")
            if native_step_by_episode[episode] != 320:
                raise AssertionError(f"{episode} must perform exactly 320 native mj_step calls")
            result_row["mj_step_calls"] = results["native_calls"]["mj_step"] - before_step
            result_row["mj_forward_calls"] = results["native_calls"]["mj_forward"] - before_forward
            result_row["warning_max_by_data"] = {
                str(data_id): values for data_id, values in warning_max_by_data.items()
            }
            result_row["q1_rad"] = q1_trace
            result_row["opening_m"] = opening_trace
            result_row["tcp_pose_wxyz_m"] = tcp_trace
            result_row["hand_pose_wxyz_m"] = hand_pose_trace
            result_row["clock_s"] = clock_trace
            result_row["motion_metrics"] = {
                "q1_peak_delta_rad": max(q1_trace) - q1_trace[0],
                "q1_final_home_error_rad": abs(q1_trace[-1] - 0.0),
                "opening_min_m": min(opening_trace),
                "opening_final_m": opening_trace[-1],
                "opening_excursion_m": max(opening_trace) - min(opening_trace),
                "max_finger_difference_m": max(finger_difference_trace),
                "tcp_position_peak_excursion_m": max(
                    float(np.linalg.norm(np.asarray(row[:3]) - np.asarray(tcp_trace[0][:3])))
                    for row in tcp_trace
                ),
                "hand_position_peak_excursion_m": max(
                    float(np.linalg.norm(np.asarray(row[:3]) - np.asarray(hand_pose_trace[0][:3])))
                    for row in hand_pose_trace
                ),
            }
            for array in (q1_trace, opening_trace, clock_trace):
                if not np.isfinite(np.asarray(array, dtype=np.float64)).all():
                    raise AssertionError(f"{episode} trace contains non-finite numeric values")
            if episode in {"E1-arm-only", "E3-simultaneous-default", "E4-simultaneous-arm-gain-3"}:
                metrics = result_row["motion_metrics"]
                if metrics["q1_peak_delta_rad"] < 0.08 or metrics["q1_final_home_error_rad"] > 0.02:
                    raise AssertionError(f"{episode} Arm motion oracle failed: {metrics}")
            if episode in {"E2-hand-only", "E3-simultaneous-default", "E4-simultaneous-arm-gain-3"}:
                metrics = result_row["motion_metrics"]
                if (metrics["opening_min_m"] > 0.02 or metrics["opening_final_m"] < 0.06
                        or metrics["opening_excursion_m"] < 0.04
                        or metrics["max_finger_difference_m"] > 1.0e-4):
                    raise AssertionError(f"{episode} Hand opening/tendon/equality motion oracle failed: {metrics}")

            finish = env.finish_recording("horizon_reached")
            h5_file = Path(finish["path"]).resolve()
            from task_env.recorders import load_leaf_control_records_h5
            independently_loaded = load_leaf_control_records_h5(h5_file)
            if (independently_loaded["transition_count"], independently_loaded["observation_count"]) != (64, 65):
                raise AssertionError(f"{episode} independent H5 readback violated T/T+1")
            if independently_loaded["leaf_writer_ids"] != tuple(sorted((ARM_WRITER_ID, HAND_WRITER_ID))):
                raise AssertionError(f"{episode} independent H5 readback has wrong leaf writers")
            if independently_loaded["leaf_profile"]["source_closure_digest"] != candidate.source.source_closure_digest:
                raise AssertionError(f"{episode} H5 source closure metadata mismatch")
            _validate_h5_commands(
                independently_loaded, ctrl_by_episode_interval, episode,
                arm_active=arm_active, hand_active=hand_active,
            )
            result_row["h5"] = {
                "path": str(h5_file.relative_to(REPO)), "sha256": _sha256_file(h5_file),
                "bytes": h5_file.stat().st_size,
                "transition_count": independently_loaded["transition_count"],
                "observation_count": independently_loaded["observation_count"],
                "outcome": independently_loaded["outcome"].to_mapping(),
                "independent_reader": "PASS",
            }
            all_metrics[episode] = result_row["motion_metrics"]
            result_row["status"] = "PASS"
            note("episode_complete", episode=episode, motion=result_row["motion_metrics"],
                 h5=result_row["h5"], step_calls=result_row["mj_step_calls"])
            if episode == "E1-arm-only":
                tamper_results = _tamper_checks(h5_file, load_leaf_control_records_h5)
                results["tamper_checks"] = tamper_results
                note("h5_tamper_matrix_complete", results=tamper_results)

        results["episodes_by_name"] = all_metrics
        results["reset_comparison"] = {
            "native_qpos_qvel_ctrl_time_identical": all(
                _reset_bytes_equal(reset_reference, row)
                for row in reset_snapshots if row["episode"] in {item["episode"] for item in results["episodes"]}
            ),
            "reset_count": results["native_calls"]["mj_resetData"],
            "episode_ids_are_distinct": len({row["reset_episode_id"] for row in results["episodes"]}) == 4,
        }
        if (results["native_calls"]["mj_step"] != 1280
                or results["native_calls"]["mj_resetData"] != 4
                or results["native_calls"]["mj_forward"] > contract["budget"]["max_mj_forward_calls"]
                or results["native_calls"]["materialize_control"] != 4):
            raise AssertionError(f"R02c aggregate native budget/accounting failed: {results['native_calls']}")
        if len(results["tamper_checks"]) != 9:
            raise AssertionError("R02c independent H5 tamper checks are incomplete")
        if any(sample["rss_bytes"] is not None and sample["rss_bytes"] > 4 * 1024**3
               for sample in results["resource_samples"]):
            raise AssertionError("observed RSS exceeded 4 GiB")
        results["status"] = "PASS"
        results["budget_total"] = {
            "process_starts": 1,
            "materialization_attempts_in_probe": results["native_calls"]["materialize_control"],
            "reset_attempts_in_probe": results["native_calls"]["mj_resetData"],
            "outer_intervals": sum(item["outer_intervals"] for item in results["episodes"]),
            "mj_step_calls": results["native_calls"]["mj_step"],
            "mj_forward_calls": results["native_calls"]["mj_forward"],
            "simulated_time_s": results["native_calls"]["mj_step"] * 0.002,
            "max_rss_sampled_bytes": max(
                (sample["rss_bytes"] for sample in results["resource_samples"] if sample["rss_bytes"] is not None),
                default=None,
            ),
            "output_bytes": _package_bytes(),
            "raw_evidence_bytes": _raw_evidence_bytes(),
        }
        note("probe_complete", status=results["status"], budget=results["budget_total"])
    except BaseException as error:
        results["status"] = "FAIL" if results["native_calls"]["mj_step"] else "FAIL_PRE_STEP"
        results["failure"] = {
            "type": type(error).__name__, "message": str(error),
            "traceback": traceback.format_exc(),
            "mj_step_calls": results["native_calls"]["mj_step"],
            "materialize_calls": results["native_calls"]["materialize_control"],
            "reset_data_calls": results["native_calls"]["mj_resetData"],
            "leaf_dispatch_progress": _leaf_failure_progress(envs),
        }
        note("probe_failure", failure=results["failure"])
        raise
    finally:
        close_errors = []
        for env in reversed(envs):
            try:
                env.close()
            except BaseException as error:
                close_errors.append({"type": type(error).__name__, "message": str(error)})
        results["resource_close_errors"] = close_errors
        results["finished_monotonic_s"] = time.monotonic()
        results["wall_seconds"] = results["finished_monotonic_s"] - started
        results["package_bytes_at_exit"] = _package_bytes()
        _write_json(EVIDENCE_PATH, results)
        log_stream.close()
        if close_errors:
            raise RuntimeError(f"one or more selected environment close calls failed: {close_errors}")
    return 0


def _static_candidate_checks(contract: dict) -> dict:
    if "mujoco" in sys.modules or "taichi" in sys.modules:
        raise RuntimeError("static preflight must not import MuJoCo or Taichi")
    from task_env.tasks.position_candidate.leaf_candidate import build_leaf_position_candidate
    from task_env.tasks.reference_env import SelectedReferenceEnv
    from task_env.runtime.sessions.source import lower_mujoco_scene_source

    workspace = ATTEMPT_ROOT / "source-workspace"
    candidate = build_leaf_position_candidate(
        workspace, environment_type=SelectedReferenceEnv, arm_gain=2.5,
    )
    try:
        if candidate.source.source_closure_digest != contract["source"]["closure_sha256"]:
            raise RuntimeError("static candidate source closure differs from the frozen contract")
        if candidate.plan.identity_sha256 != contract["plans"]["default_identity_sha256"]:
            raise RuntimeError("static default effective leaf plan differs from the frozen contract")
        xml, assets = lower_mujoco_scene_source(
            candidate.source.scene_source, candidate.scene, candidate.source.source_closure_digest,
        )
        xml_hash = _sha256_bytes(xml.encode("utf-8"))
        assets_hashes = {name: _sha256_bytes(value) for name, value in assets.items()}
        if xml_hash != contract["source"]["lowered_xml_sha256"]:
            raise RuntimeError("static lowered MuJoCo source hash differs from the frozen contract")
        if assets_hashes != contract["source"]["assets_sha256"]:
            raise RuntimeError("static lowered asset closure differs from the frozen contract")
        if "mujoco" in sys.modules or "taichi" in sys.modules:
            raise RuntimeError("static source verification imported a native Provider")
        return {
            "source_closure_sha256": candidate.source.source_closure_digest,
            "lowered_xml_sha256": xml_hash,
            "asset_count": len(assets_hashes),
            "assets_sha256": assets_hashes,
            "default_plan_identity_sha256": candidate.plan.identity_sha256,
            "native_provider_imported": False,
        }
    finally:
        candidate.env.close()


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_output_path(raw_path: str, mode: str) -> Path:
    global ATTEMPT_ROOT
    expected_root = (REPO / f"workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02c_{CURRENT_ATTEMPT}").resolve()
    root = Path(raw_path).expanduser().resolve(strict=False)
    if root.parent != expected_root:
        raise ValueError("output-dir must be a direct child of the current R02c continuation package")
    allowed_native = mode == "native" and root.name == "native_run_001"
    allowed_static_preflight = mode == "static" and (
        root.name.startswith("preflight_reject_")
        or (root.name.startswith("preflight_") and root.name.removeprefix("preflight_").isdigit())
    )
    if not allowed_native and not allowed_static_preflight:
        raise ValueError("output-dir names an unauthorized R02c attempt directory")
    if root.exists() or root.is_symlink():
        raise FileExistsError(f"output-dir must be fresh and exclusive: {root}")
    ATTEMPT_ROOT = expected_root
    ATTEMPT_ROOT.mkdir(parents=True, exist_ok=True)
    root.mkdir(exist_ok=False)
    return root


def main(argv=None) -> int:
    global OUTPUT, CONTRACT_PATH, SNAPSHOT_PATH, EVIDENCE_PATH, LOG_PATH
    parser = argparse.ArgumentParser(description=f"Bounded R02c attempt{CURRENT_ATTEMPT} MuJoCo CPU verification")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--static-only", action="store_true")
    mode.add_argument("--execute-native", action="store_true")
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    run_mode = "static" if args.static_only else "native"
    try:
        OUTPUT = _safe_output_path(args.output_dir, run_mode)
    except BaseException as error:
        print(json.dumps({"status": "BLOCKED_PRECHECK", "error_type": type(error).__name__, "error": str(error)}), file=sys.stderr)
        return 2
    ATTEMPT_ROOT = OUTPUT.parent
    globals()["ATTEMPT_ROOT"] = ATTEMPT_ROOT
    CONTRACT_PATH = args.contract.resolve()
    SNAPSHOT_PATH = args.snapshot.resolve()
    EVIDENCE_PATH = OUTPUT / ("preflight_result.json" if args.static_only else "native_evidence.json")
    log_dir = ATTEMPT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    LOG_PATH = log_dir / f"{OUTPUT.name}.jsonl"
    started = time.monotonic()
    result = {
        "task_id": "PHASE-II-01-R02C", "attempt": CURRENT_ATTEMPT, "mode": run_mode,
        "status": "RUNNING", "native_calls": {"mj_step": 0, "mj_forward": 0,
                          "mj_resetData": 0, "materialize_control": 0},
        "failure": None, "started_monotonic_s": started,
    }
    _write_json(EVIDENCE_PATH, result)
    log_stream = LOG_PATH.open("x", encoding="utf-8")
    ledger = None
    ledger_path = None
    ledger_run = None
    try:
        contract = _load_json(CONTRACT_PATH)
        snapshot = _load_json(SNAPSHOT_PATH)
        _verify_frozen_inputs(contract, snapshot)
        if args.static_only:
            result["source_static"] = _static_candidate_checks(contract)
            result["native_imported"] = False
            result["status"] = "PASS_STATIC_PREFLIGHT"
            result["finished_monotonic_s"] = time.monotonic()
            _write_json(EVIDENCE_PATH, result)
            log_stream.write(json.dumps({"status": result["status"], "source_static": result["source_static"]}, sort_keys=True) + "\n")
            return 0

        preflight_paths = sorted(ATTEMPT_ROOT.glob("preflight_[0-9][0-9][0-9]/preflight_result.json"))
        valid_preflight = next((path for path in reversed(preflight_paths)
                                if _load_json(path).get("status") == "PASS_STATIC_PREFLIGHT"), None)
        if valid_preflight is None:
            raise RuntimeError("native mode requires a successful current-attempt static preflight")
        preflight_path = valid_preflight
        preflight = _load_json(preflight_path)
        result["successful_static_preflight"] = str(preflight_path)
        if (preflight.get("source_static", {}).get("source_closure_sha256")
                != contract["source"]["closure_sha256"]):
            raise RuntimeError("static preflight and native contract source closure disagree")
        ledger_path = ATTEMPT_ROOT / "native_process_ledger.json"
        ledger = _load_json(ledger_path) if ledger_path.exists() else {
            "attempt": CURRENT_ATTEMPT, "process_starts": 0, "runs": [],
        }
        if ledger["process_starts"] >= contract["budget"]["max_native_process_invocations"]:
            raise RuntimeError("R02c continuation native process invocation budget exhausted")
        if ledger["process_starts"]:
            previous = ledger["runs"][-1]
            if (previous.get("status") != "FAIL_PRE_STEP" or previous.get("mj_step_calls") != 0
                    or previous.get("failure_class") != "PROGRAMMING_ERROR"):
                raise RuntimeError("second native process is allowed only after an ordinary pre-step programming failure")
        process_number = ledger["process_starts"] + 1
        if OUTPUT.name != f"native_run_{process_number:03d}":
            raise RuntimeError("native output directory does not match the next process ledger slot")
        ledger["process_starts"] = process_number
        ledger["runs"].append({"run": OUTPUT.name, "status": "RUNNING", "mj_step_calls": 0})
        ledger_run = ledger["runs"][-1]
        _write_json(ledger_path, ledger)
        exit_code = _run_native(contract, snapshot, started, log_stream, result)
        evidence = _load_json(EVIDENCE_PATH)
        ledger_run.update({
            "status": evidence.get("status"),
            "mj_step_calls": evidence.get("native_calls", {}).get("mj_step", 0),
            "failure_class": "NONE" if evidence.get("status") == "PASS" else "OTHER",
        })
        _write_json(ledger_path, ledger)
        return exit_code
    except BaseException as error:
        # The worker mutates this owned object in place. A disk checkpoint may
        # predate hundreds of successful steps if final serialization failed.
        existing = result
        if existing.get("status") in {"RUNNING", "PASS_STATIC_PREFLIGHT"}:
            existing["status"] = (
                ("FAIL" if existing.get("native_calls", {}).get("mj_step", 0) else "FAIL_PRE_STEP")
                if run_mode == "native" else "FAIL_STATIC_PREFLIGHT"
            )
            existing["failure"] = {
                "type": type(error).__name__, "message": str(error),
                "traceback": traceback.format_exc(),
            }
        elif existing.get("status") == "PASS" and run_mode == "native":
            existing["status"] = "FAIL_RESOURCE_CLOSE"
            existing["failure"] = {
                "type": type(error).__name__, "message": str(error),
                "traceback": traceback.format_exc(),
                "note": "Native evidence was already written; the wrapper failure occurred during closeout.",
            }
        elif ((existing.get("failure") or {}).get("type"), (existing.get("failure") or {}).get("message")) != (
            type(error).__name__, str(error),
        ):
            existing.setdefault("secondary_failures", []).append({
                "type": type(error).__name__, "message": str(error),
                "traceback": traceback.format_exc(),
            })
        result = existing
        result["finished_monotonic_s"] = time.monotonic()
        _write_json(EVIDENCE_PATH, result)
        if not log_stream.closed:
            log_stream.write(json.dumps({"status": result["status"], "failure": result.get("failure")},
                                        sort_keys=True, allow_nan=False, default=_json_default) + "\n")
        if ledger is not None and ledger_run is not None and ledger_path is not None:
            failure_message = str(result.get("failure", {}).get("message", ""))
            if result.get("native_calls", {}).get("mj_step", 0):
                failure_class = "POST_STEP_FAILURE"
            elif result.get("status") == "FAIL_PRE_STEP" and failure_message.startswith("BLOCKED_PROVIDER:"):
                failure_class = "BLOCKED_PROVIDER"
            elif result.get("status") == "FAIL_PRE_STEP" and type(error).__name__ in {
                "TypeError", "AttributeError", "NameError", "KeyError", "IndexError",
            }:
                failure_class = "PROGRAMMING_ERROR"
            else:
                failure_class = "OTHER"
            ledger_run.update({
                "status": result.get("status"),
                "mj_step_calls": result.get("native_calls", {}).get("mj_step", 0),
                "failure_class": failure_class,
            })
            _write_json(ledger_path, ledger)
        return 1
    finally:
        if not log_stream.closed:
            log_stream.close()


if __name__ == "__main__":
    raise SystemExit(main())
