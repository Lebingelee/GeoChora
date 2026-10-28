"""Independent provider-free reader for an R04b public camera S2 capture bundle.

This module intentionally imports only Python's standard library and NumPy. It
does not import TaskEnv, GeoPhys, MuJoCo, OpenGL, or the worker's assertions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import time
import traceback

import numpy as np


FIXED_CAMERA_ID = "d04-fixed-square-peg-calibration-v1"
HAND_CAMERA_ID = "d04-panda-hand-mounted-camera-v1"
CAMERA_IDS = (FIXED_CAMERA_ID, HAND_CAMERA_ID)
WIDTH, HEIGHT = 321, 241
FRAME_POSITION_ATOL_M = 5.0e-4
FRAME_QUATERNION_ATOL = 1.0e-3
LANDMARK_DEPTH_ATOL_M = 2.0e-3
BACKPROJECTION_ATOL_M = 3.0e-3
PIXEL_DELTA_THRESHOLD = 1.0 / 255.0
MIN_CHANGED_PIXELS = 8


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path):
    rows = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError(f"{path.name}:{index} is invalid JSON") from error
    return rows


def _rotation_wxyz(quaternion) -> np.ndarray:
    w, x, y, z = np.asarray(quaternion, dtype=np.float64)
    norm = math.sqrt(w * w + x * x + y * y + z * z)
    if not math.isfinite(norm) or norm <= 1.0e-12:
        raise ValueError("invalid quaternion in offline camera evidence")
    w, x, y, z = w / norm, x / norm, y / norm, z / norm
    return np.asarray((
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    ), dtype=np.float64)


def _pose_matrix(pose) -> np.ndarray:
    result = np.eye(4, dtype=np.float64)
    result[:3, :3] = _rotation_wxyz(pose["quaternion_wxyz"])
    result[:3, 3] = np.asarray(pose["position"], dtype=np.float64)
    return result


def _matrix_quaternion_wxyz(matrix) -> np.ndarray:
    rotation = np.asarray(matrix, dtype=np.float64)[:3, :3]
    trace = float(np.trace(rotation))
    if trace > 0:
        scale = math.sqrt(trace + 1.0) * 2.0
        quat = np.asarray((
            0.25 * scale,
            (rotation[2, 1] - rotation[1, 2]) / scale,
            (rotation[0, 2] - rotation[2, 0]) / scale,
            (rotation[1, 0] - rotation[0, 1]) / scale,
        ))
    elif rotation[0, 0] > rotation[1, 1] and rotation[0, 0] > rotation[2, 2]:
        scale = math.sqrt(1.0 + rotation[0, 0] - rotation[1, 1] - rotation[2, 2]) * 2.0
        quat = np.asarray((
            (rotation[2, 1] - rotation[1, 2]) / scale,
            0.25 * scale,
            (rotation[0, 1] + rotation[1, 0]) / scale,
            (rotation[0, 2] + rotation[2, 0]) / scale,
        ))
    elif rotation[1, 1] > rotation[2, 2]:
        scale = math.sqrt(1.0 + rotation[1, 1] - rotation[0, 0] - rotation[2, 2]) * 2.0
        quat = np.asarray((
            (rotation[0, 2] - rotation[2, 0]) / scale,
            (rotation[0, 1] + rotation[1, 0]) / scale,
            0.25 * scale,
            (rotation[1, 2] + rotation[2, 1]) / scale,
        ))
    else:
        scale = math.sqrt(1.0 + rotation[2, 2] - rotation[0, 0] - rotation[1, 1]) * 2.0
        quat = np.asarray((
            (rotation[1, 0] - rotation[0, 1]) / scale,
            (rotation[0, 2] + rotation[2, 0]) / scale,
            (rotation[1, 2] + rotation[2, 1]) / scale,
            0.25 * scale,
        ))
    return quat / np.linalg.norm(quat)


def _rigid(matrix, label: str) -> np.ndarray:
    value = np.asarray(matrix, dtype=np.float64)
    if (value.shape != (4, 4) or not np.isfinite(value).all()
            or not np.array_equal(value[3], (0.0, 0.0, 0.0, 1.0))
            or not np.allclose(value[:3, :3].T @ value[:3, :3], np.eye(3), atol=1e-6, rtol=0)
            or abs(float(np.linalg.det(value[:3, :3])) - 1.0) > 1e-6):
        raise ValueError(f"{label} is not a finite proper rigid transform")
    return value


def _ray_box_depth(metadata, peg_pose, row: int, col: int):
    K = np.asarray(metadata["K"], dtype=np.float64)
    world_from_camera = _rigid(metadata["T_world_from_camera"], "T_world_from_camera")
    ray_camera = np.linalg.inv(K) @ np.asarray((col + 0.5, row + 0.5, 1.0))
    ray_world = world_from_camera[:3, :3] @ ray_camera
    origin_world = world_from_camera[:3, 3]
    world_from_box = _pose_matrix(peg_pose)
    box_from_world = world_from_box[:3, :3].T
    ray_box = box_from_world @ ray_world
    origin_box = box_from_world @ (origin_world - world_from_box[:3, 3])
    half = np.asarray((0.016, 0.016, 0.06), dtype=np.float64)
    near, far = -math.inf, math.inf
    for axis in range(3):
        if abs(float(ray_box[axis])) <= 1.0e-12:
            if abs(float(origin_box[axis])) > half[axis]:
                raise ValueError("landmark ray misses the canonical square peg")
            continue
        t0 = (-half[axis] - origin_box[axis]) / ray_box[axis]
        t1 = (half[axis] - origin_box[axis]) / ray_box[axis]
        near = max(near, min(float(t0), float(t1)))
        far = min(far, max(float(t0), float(t1)))
    if near < 0 or far < near:
        raise ValueError("canonical square peg is behind the camera ray")
    hit_box = origin_box + near * ray_box
    hit_world = world_from_box[:3, 3] + world_from_box[:3, :3] @ hit_box
    return float(near), hit_world


def _check_depth_sample(capture, arrays, peg_pose):
    calibration = capture["calibration"]
    depth = arrays[capture["array_keys"]["depth"]]
    K = np.asarray(calibration["K"], dtype=np.float64)
    camera_from_world = _rigid(calibration["T_camera_from_world"], "T_camera_from_world")
    landmark = np.asarray(peg_pose["position"], dtype=np.float64)
    camera_point = camera_from_world[:3, :3] @ landmark + camera_from_world[:3, 3]
    if camera_point[2] <= 0:
        raise ValueError("calibration landmark is behind the camera")
    homogeneous_pixel = K @ camera_point
    pixel = homogeneous_pixel[:2] / homogeneous_pixel[2]
    col = int(round(float(pixel[0]) - 0.5))
    row = int(round(float(pixel[1]) - 0.5))
    if row < 0 or row >= depth.shape[0] or col < 0 or col >= depth.shape[1]:
        raise ValueError("calibration landmark projects outside the camera image")
    expected, hit_world = _ray_box_depth(calibration, peg_pose, row, col)
    observed = float(depth[row, col])
    if observed <= 0 or abs(observed - expected) > LANDMARK_DEPTH_ATOL_M:
        raise AssertionError(f"{capture['camera_id']} optical-Z mismatch {observed:g} vs {expected:g} m")
    ray_camera = np.linalg.inv(K) @ np.asarray((col + 0.5, row + 0.5, 1.0))
    world_from_camera = np.asarray(calibration["T_world_from_camera"], dtype=np.float64)
    backprojected = world_from_camera[:3, :3] @ (ray_camera * observed) + world_from_camera[:3, 3]
    error = float(np.linalg.norm(backprojected - hit_world))
    if error > BACKPROJECTION_ATOL_M:
        raise AssertionError(f"{capture['camera_id']} back-projection error is {error:g} m")
    return {
        "row": row,
        "column": col,
        "expected_optical_z_m": expected,
        "observed_optical_z_m": observed,
        "backprojection_error_m": error,
    }


def _capture_identity_digest(identity) -> str:
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _state_boundary_id(boundary) -> str:
    payload = json.dumps(boundary, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return "state-boundary-" + hashlib.sha256(payload).hexdigest()


def verify(output: str | Path, evidence_root: str | Path | None = None) -> dict[str, object]:
    started = time.monotonic()
    output = Path(output).resolve()
    worker_path = output / "worker_receipt.json"
    arrays_path = output / "raw_camera_arrays.npz"
    captures_path = output / "capture_rows.jsonl"
    boundaries_path = output / "boundary_rows.jsonl"
    cache_path = output / "cache_probes.jsonl"
    controls_path = output / "control_rows.jsonl"
    for path in (worker_path, arrays_path, captures_path, boundaries_path, cache_path, controls_path):
        if not path.is_file():
            raise FileNotFoundError(f"required R04b evidence file missing: {path.name}")
    worker = _read_json(worker_path)
    if worker.get("status") != "R04B_PUBLIC_ENV_TWO_CAMERA_S2_PASS":
        raise ValueError("worker did not publish a closed successful public Env run")
    if (not worker.get("closed_before_receipt") or worker.get("env_close_calls") != 1
            or worker.get("env_close_successes") != 1):
        raise ValueError("worker receipt was not written after the sole Environment close")
    if worker.get("primary_error") is not None or worker.get("cleanup_error") is not None:
        raise ValueError("worker receipt contains an execution or cleanup error")

    raw = np.load(arrays_path, allow_pickle=False)
    capture_rows = _read_jsonl(captures_path)
    boundary_rows = _read_jsonl(boundaries_path)
    cache_rows = _read_jsonl(cache_path)
    control_rows = _read_jsonl(controls_path)
    if _sha256(arrays_path) != worker["evidence"]["raw_camera_arrays_sha256"]:
        raise ValueError("raw array digest differs from the worker receipt")
    for path, key in ((captures_path, "capture_rows_sha256"),
                      (boundaries_path, "boundary_rows_sha256"),
                      (cache_path, "cache_probes_sha256"),
                      (controls_path, "control_rows_sha256")):
        if _sha256(path) != worker["evidence"][key]:
            raise ValueError(f"{path.name} digest differs from the worker receipt")

    by_index = {row["index"]: row for row in capture_rows}
    if len(by_index) != len(capture_rows) or sorted(by_index) != list(range(len(capture_rows))):
        raise ValueError("capture row indices are missing, duplicated, or reordered")
    if len(capture_rows) != 53:
        raise ValueError(f"expected 52 public captures plus one isolation capture, got {len(capture_rows)}")
    if len(boundary_rows) != 26 or len(cache_rows) != 26:
        raise ValueError("expected two 13-boundary episodes and one cache probe per public boundary")
    if len(control_rows) != 24:
        raise ValueError("expected one actual Position Controller target/application receipt per outer interval")
    if sum(row["capture_kind"] == "public" for row in capture_rows) != 52:
        raise ValueError("public camera capture row count is not 52")
    if sum(row["capture_kind"] == "isolation" for row in capture_rows) != 1:
        raise ValueError("camera isolation capture row count is not one")
    if set(raw.files) != {
        key for row in capture_rows for key in row["array_keys"].values()
    }:
        raise ValueError("NPZ array keys do not match capture rows exactly")

    counters = worker["counters"]
    expected_counts = {
        "reset_attempts": 2,
        "outer_steps": 24,
        "clock_inferred_substeps": 120,
        "accepted_physics_substeps": 120,
        "renderer_capture_calls": 53,
        "renderer_capture_successes": 53,
        "public_boundary_captures": 52,
        "isolation_capture_calls": 1,
        "renderer_render_calls": 159,
        "renderer_render_successes": 159,
        "provider_interval_step_calls": 24,
        "provider_interval_step_successes": 24,
        "runtime_boundary_step_calls": 24,
        "runtime_boundary_step_successes": 24,
        "runtime_boundary_step_calls_during_capture": 0,
        "mj_step_during_capture": 0,
        "mj_forward_during_capture": 0,
        "native_renderer_close_calls": 4,
        "native_renderer_close_successes": 4,
        "session_close_calls": 5,
        "session_close_successes": 5,
        "session_close_failures": 0,
    }
    for key, value in expected_counts.items():
        if counters.get(key) != value:
            raise ValueError(f"worker counted {key}={counters.get(key)!r}; expected {value}")
    if len(set(counters.get("materialization_ids", ()))) != 2:
        raise ValueError("worker did not observe two fresh provider materializations")
    if (len(counters.get("native_renderer_close_counts", {})) != 4
            or set(counters["native_renderer_close_counts"].values()) != {1}
            or len(counters.get("native_renderer_tokens_closed", ())) != 4):
        raise ValueError("worker did not close each stable renderer lifecycle token exactly once")
    session_closes = counters.get("camera_session_close_counts", {})
    if (len(session_closes) != 4 or sorted(session_closes.values()) != [1, 1, 1, 2]
            or session_closes != counters.get("camera_session_close_successes", {})):
        raise ValueError("worker did not record the explicit duplicate camera-session close while closing each renderer once")
    if abs(float(counters.get("simulation_seconds", -1.0)) - 0.24) > 2e-9:
        raise ValueError("worker integrated simulation time other than 0.24 seconds")

    capture_by_boundary_camera = {}
    consumers_by_round_camera = {}
    reset_rows = {}
    moved_rows = {}
    expected_source = worker["runtime"]["source_closure_digest"]
    expected_artifact = worker["runtime"]["artifact_identity_hash"]
    expected_scene = worker["runtime"]["scene_identity_hash"]
    expected_reset_sample = worker["runtime"]["reset_sample_id"]
    expected_config = worker["camera_config_preflight"]["camera_observation_config"]
    expected_cameras = {item["camera_id"]: item for item in expected_config["cameras"]}
    if tuple(expected_cameras) != CAMERA_IDS:
        raise ValueError("worker camera config is not in canonical D04 order")

    boundaries_by_key = {}
    for boundary in boundary_rows:
        round_index = boundary["round_index"]
        step = boundary["boundary_index"]
        key = (round_index, step)
        if key in boundaries_by_key:
            raise ValueError("duplicate public episode boundary")
        boundaries_by_key[key] = boundary
        state = boundary["state_boundary"]
        clock = boundary["sample_clock"]
        if (state["control_step"] != step or state["reset_sample_id"] != expected_reset_sample
                or state["scene_identity_hash"] != expected_scene
                or abs(float(clock["simulation_time_s"]) - step * 0.01) > 1e-9
                or clock["sample_index"] != step or clock["clock_domain"] != "evaluation_boundary"):
            raise ValueError("typed boundary/clock/reset identity is inconsistent")
        if len(boundary["capture_rows"]) != 2:
            raise ValueError("public boundary does not bind exactly two camera captures")
        if step == 0 and boundary.get("control_transition") is not None:
            raise ValueError("reset boundary must not invent a Position action transition")
        if step > 0 and not isinstance(boundary.get("control_transition"), dict):
            raise ValueError("public Position step lacks its actual Controller transition receipt")
        for row_index in boundary["capture_rows"]:
            capture = by_index[row_index]
            capture_key = (round_index, step, capture["camera_id"])
            if capture_key in capture_by_boundary_camera:
                raise ValueError("multiple captures for one public camera boundary")
            if capture["capture_kind"] != "public":
                raise ValueError("boundary includes a non-public isolation capture")
            if capture["round_index"] != round_index or capture["camera_id"] not in CAMERA_IDS:
                raise ValueError("capture row round/camera differs from its boundary")
            if (capture["capture_identity"]["state_boundary"] != state
                    or capture["capture_identity"]["sample_clock"] != clock):
                raise ValueError("capture identity boundary/clock differs from its typed public boundary")
            capture_by_boundary_camera[capture_key] = capture

    if set(boundaries_by_key) != {(episode, step) for episode in (0, 1) for step in range(13)}:
        raise ValueError("public boundary sequence is not two complete 0..12 episodes")
    control_by_key = {(row["round_index"], row["control_step"]): row for row in control_rows}
    if len(control_by_key) != 24 or set(control_by_key) != {
        (episode, step) for episode in (0, 1) for step in range(1, 13)
    }:
        raise ValueError("Position control receipt sequence is missing, duplicated, or reordered")
    request_hashes = set()
    for key, row in control_by_key.items():
        boundary_control = boundaries_by_key[key].get("control_transition")
        if boundary_control != row:
            raise ValueError("boundary control transition differs from the independent control JSONL")
        if row["canonical_target_identity_hash"] != row["applied_target_hash"]:
            raise ValueError("Position applied acknowledgement targets a different canonical Controller target")
        if (row["target"].get("schema_version") != "position-control-target-v1"
                or row["target"]["target"].get("schema_version") != "canonical-control-v0"
                or row["applied"].get("schema_version") != "applied-canonical-control-v0"
                or row["applied"].get("target_hash") != row["canonical_target_identity_hash"]
                or row["applied"].get("provider_name") != "geophys"):
            raise ValueError("Position Target/Ack public schema or provider binding is invalid")
        if _capture_identity_digest(row["target"]) != row["target_identity_hash"]:
            raise ValueError("Position Target identity digest is invalid")
        if (_capture_identity_digest(row["target"]["target"])
                != row["canonical_target_identity_hash"]):
            raise ValueError("Position canonical Target identity digest is invalid")
        if row["target"]["target"]["task_artifact_hash"] != expected_artifact:
            raise ValueError("Position target is not bound to the admitted TaskArtifact")
        if row["controller_identity"] != boundaries_by_key[key]["controller_identity"]:
            raise ValueError("Position target was computed by another Controller identity")
        source_boundary = row["target"]["source_boundary"]
        previous_boundary = boundaries_by_key[(key[0], key[1] - 1)]["state_boundary"]
        if (source_boundary != previous_boundary
                or source_boundary["control_step"] != key[1] - 1
                or row["target"]["sample_clock"] != boundaries_by_key[(key[0], key[1] - 1)]["sample_clock"]):
            raise ValueError("Position target is not bound to the exact preceding typed boundary")
        request_hashes.add(row["request_identity_sha256"])
    trajectories = worker.get("action_trajectories", [])
    if len(trajectories) != 2 or {row["round_index"] for row in trajectories} != {0, 1}:
        raise ValueError("worker did not freeze one identical public Position request per reset round")
    for trajectory in trajectories:
        digest = hashlib.sha256(json.dumps(
            trajectory["structured_action_request"], sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest()
        if digest != trajectory["request_identity_sha256"]:
            raise ValueError("public Position action request identity digest is invalid")
        if trajectory["world_position_delta_m"] != 0.08 or trajectory["gripper_target"] != 1.0:
            raise ValueError("Position action trajectory differs from the frozen D04 small-motion request")
        groups = {(item["entity_id"], item["group_id"]): item for item in trajectory["structured_action_request"]["groups"]}
        arm_values = groups[("panda-main", "arm")]["values"]
        gripper_values = groups[("panda-main", "gripper")]["values"]
        expected_arm = [*trajectory["target_hand_pose"]["position"],
                        *trajectory["target_hand_pose"]["quaternion_wxyz"]]
        if (not np.allclose(arm_values, expected_arm, atol=1e-12, rtol=0)
                or list(gripper_values) != [trajectory["gripper_target"]]):
            raise ValueError("structured Position request differs from its frozen world target")
        frozen_initial = np.asarray(worker["camera_config_preflight"]["world_from_hand_reset_fk"], dtype=np.float64)
        target_pose = worker["camera_config_preflight"]["requested_hand_target_pose_world"]
        expected_initial_position = frozen_initial[:3, 3]
        actual_initial_position = np.asarray(trajectory["initial_hand_pose"]["position"], dtype=np.float64)
        actual_target_position = np.asarray(trajectory["target_hand_pose"]["position"], dtype=np.float64)
        if (not np.allclose(actual_initial_position, expected_initial_position, atol=FRAME_POSITION_ATOL_M, rtol=0)
                or not np.allclose(actual_target_position, target_pose["position"], atol=1e-12, rtol=0)
                or not np.allclose(trajectory["target_hand_pose"]["quaternion_wxyz"],
                                   target_pose["quaternion_wxyz"], atol=1e-12, rtol=0)):
            raise ValueError("action request was not frozen from the fixed ResetPlan FK before native execution")
    if len(request_hashes) != 1 or request_hashes != {row["request_identity_sha256"] for row in trajectories}:
        raise ValueError("one fixed action request identity was not used across both 12-step rounds")

    all_capture_hashes = []
    all_materializations = set()
    all_episodes = set()
    render_sources = set()
    execution_specs = set()
    fixed_world_transforms = []
    hand_world_transforms = []
    hand_local_transforms = []
    changed_pixel_counts = {}
    geometry_samples = []
    rgb_digest_inputs = {}

    for capture in capture_rows:
        index = capture["index"]
        camera_id = capture["camera_id"]
        if camera_id not in CAMERA_IDS:
            raise ValueError("capture row contains an unrequested camera ID")
        keys = capture["array_keys"]
        rgb, depth, mask = (raw[keys["rgb"]], raw[keys["depth"]], raw[keys["mask"]])
        if rgb.dtype != np.float32 or rgb.shape != (HEIGHT, WIDTH, 3):
            raise ValueError(f"capture {index} RGB shape/dtype mismatch")
        if not np.isfinite(rgb).all() or np.any(rgb < 0) or np.any(rgb > 1):
            raise ValueError(f"capture {index} RGB has invalid values")
        if depth.dtype != np.float32 or depth.shape != (HEIGHT, WIDTH):
            raise ValueError(f"capture {index} depth shape/dtype mismatch")
        if not np.isfinite(depth).all() or np.any(depth < 0) or not np.any(depth > 0) or not np.any(depth == 0):
            raise ValueError(f"capture {index} depth is not finite metric optical-Z with zero invalids")
        if mask.dtype != np.uint32 or mask.shape != (HEIGHT, WIDTH):
            raise ValueError(f"capture {index} mask shape/dtype mismatch")
        if hashlib.sha256(np.ascontiguousarray(mask).tobytes(order="C")).hexdigest() != capture["mask_sha256"]:
            raise ValueError(f"capture {index} mask digest mismatch")

        identity = capture["capture_identity"]
        actual_identity_hash = _capture_identity_digest(identity)
        if actual_identity_hash != capture["capture_identity_identity_hash"]:
            raise ValueError(f"capture {index} identity digest mismatch")
        all_capture_hashes.append(actual_identity_hash)
        state = identity["state_boundary"]
        clock = identity["sample_clock"]
        if (identity["camera_id"] != camera_id or identity["task_artifact_hash"] != expected_artifact
                or not identity["render_source_identity_hash"]
                or state["scene_identity_hash"] != expected_scene
                or state["reset_sample_id"] != expected_reset_sample
                or clock["clock_domain"] != "evaluation_boundary"
                or clock["sample_index"] != state["control_step"]
                or set(identity["modalities"]) != {"rgb", "depth", "entity_instance_segmentation"}):
            raise ValueError(f"capture {index} identity is not bound to the public candidate route")
        render_sources.add(identity["render_source_identity_hash"])
        execution_specs.add(identity["execution_spec_identity_hash"])
        selection = identity["renderer_selection"]
        if (selection["provider"] != "mujoco" or selection["backend"] != "native-opengl"
                or selection["profile"] != "d04_mujoco_native_dynamic_opengl_entity_instance_segmentation_v1"):
            raise ValueError(f"capture {index} renderer selection differs from the required D04 profile")
        all_materializations.add(state["provider_materialization_id"])
        all_episodes.add(state["episode_id"])
        calibration = capture["calibration"]
        camera = calibration["camera"]
        if (camera["camera_id"] != camera_id or camera["width"] != WIDTH or camera["height"] != HEIGHT
                or abs(float(camera["fov_y"]) - math.pi / 2) > 1e-12
                or abs(float(camera["near"]) - 0.01) > 1e-12
                or abs(float(camera["far"]) - 3.0) > 1e-12):
            raise ValueError(f"capture {index} calibration does not match the frozen camera envelope")
        world_from_mount = _rigid(calibration["T_world_from_mount"], "T_world_from_mount")
        world_from_camera = _rigid(calibration["T_world_from_camera"], "T_world_from_camera")
        camera_from_world = _rigid(calibration["T_camera_from_world"], "T_camera_from_world")
        if not np.allclose(world_from_camera @ camera_from_world, np.eye(4), atol=1e-6, rtol=0):
            raise ValueError(f"capture {index} camera transforms are not inverses")
        if not np.allclose(world_from_mount @ np.asarray(camera["T_mount_from_camera"]),
                           world_from_camera, atol=1e-6, rtol=0):
            raise ValueError(f"capture {index} camera/mount composition is inconsistent")
        expected_mount = expected_cameras[camera_id]["T_parent_from_mount"]
        if not np.allclose(expected_mount, camera["T_parent_from_mount"], atol=1e-12, rtol=0):
            raise ValueError(f"capture {index} mount differs from the frozen input request")

        label_map = capture["label_map"]
        if (label_map["capture_identity_hash"] != actual_identity_hash
                or label_map["camera_id"] != camera_id
                or label_map["state_boundary_id"] != _state_boundary_id(state)
                or label_map["episode_id"] != state["episode_id"]
                or label_map["reset_sample_id"] != state["reset_sample_id"]
                or label_map["provider_materialization_id"] != state["provider_materialization_id"]
                or label_map["control_step"] != state["control_step"]):
            raise ValueError(f"capture {index} canonical Entity label map is stale")
        labels = {entry["label"] for entry in label_map["labels"]}
        entities = {entry["entity_id"] for entry in label_map["labels"]}
        if labels != set(range(1, len(labels) + 1)):
            raise ValueError(f"capture {index} Entity labels are not dense positive canonical labels")
        boundary = boundaries_by_key.get((capture["round_index"], state["control_step"]))
        if boundary is None:
            raise ValueError(f"capture {index} has no matching public typed boundary")
        if not entities.issubset(set(boundary["canonical_entity_ids"])):
            raise ValueError(f"capture {index} label map includes a non-canonical Entity ID")
        mask_values = {int(value) for value in np.unique(mask)}
        if 0 not in mask_values or not mask_values.issubset({0, *labels}):
            raise ValueError(f"capture {index} mask leaks a native geometry ID or omits background")

        sync = capture["sync"]
        if (sync["consumer_id"] != capture["consumer_id"]
                or sync["state_boundary"] != state
                or sync["sample_clock"] != clock
                or float(sync["max_frame_position_error_m"]) > FRAME_POSITION_ATOL_M
                or float(sync["max_frame_quaternion_sign_invariant_l2_error"]) > FRAME_QUATERNION_ATOL):
            raise ValueError(f"capture {index} renderer sync evidence exceeds or disagrees with typed Frame pose limits")
        consumers_by_round_camera.setdefault((capture["round_index"], camera_id), set()).add(capture["consumer_id"])

        typed_hand = boundary["hand_frame"]
        hand_world = _pose_matrix(typed_hand)
        expected_parent = np.eye(4) if camera["parent_frame"] == "world" else hand_world
        recomputed_camera = expected_parent @ np.asarray(camera["T_parent_from_mount"]) @ np.asarray(camera["T_mount_from_camera"])
        if not np.allclose(recomputed_camera, world_from_camera, atol=1e-9, rtol=0):
            raise ValueError(f"capture {index} world extrinsic disagrees with its typed parent Frame")
        if camera_id == FIXED_CAMERA_ID:
            fixed_world_transforms.append(world_from_camera)
        else:
            hand_world_transforms.append(world_from_camera)
            hand_local_transforms.append(np.linalg.inv(hand_world) @ world_from_camera)

        public_meta = capture.get("public_capture_metadata")
        if capture["capture_kind"] == "public":
            if not isinstance(public_meta, dict):
                raise ValueError(f"public capture {index} has no Environment metadata cross-check")
            if (public_meta["camera_id"] != camera_id
                    or public_meta["capture_identity"] != identity
                    or public_meta["calibration"] != calibration
                    or public_meta["mask_sha256"] != capture["mask_sha256"]
                    or public_meta["label_map"] != label_map):
                raise ValueError(f"public observation metadata differs from raw camera capture {index}")
            capture_by_boundary_camera[(capture["round_index"], state["control_step"], camera_id)] = capture
            if state["control_step"] == 0:
                reset_rows[(capture["round_index"], camera_id)] = capture
            if state["control_step"] == 12:
                moved_rows[(capture["round_index"], camera_id)] = capture
        else:
            if public_meta is not None:
                raise ValueError("isolation-only capture must not be counted as a public observation boundary")

    if len(all_materializations) != 2 or len(all_episodes) != 2:
        raise ValueError("camera identities do not bind exactly two fresh episodes/materializations")
    if len(render_sources) != 1 or len(execution_specs) != 1:
        raise ValueError("camera captures changed source or execution identity within the frozen run")
    if any(row["source_closure_digest"] != expected_source for row in boundary_rows):
        raise ValueError("public typed boundary rows disagree with the runtime source closure")
    for round_index in (0, 1):
        for camera_id in CAMERA_IDS:
            if consumers_by_round_camera.get((round_index, camera_id), set()).__len__() != 1:
                raise ValueError("camera consumer identity changed within an episode")
        if (consumers_by_round_camera[(round_index, FIXED_CAMERA_ID)]
                == consumers_by_round_camera[(round_index, HAND_CAMERA_ID)]):
            raise ValueError("fixed and hand cameras share one renderer consumer")

    public_boundary_keys = set(capture_by_boundary_camera)
    expected_boundary_keys = {(episode, step, camera) for episode in (0, 1) for step in range(13) for camera in CAMERA_IDS}
    if public_boundary_keys != expected_boundary_keys:
        raise ValueError("public captures do not cover every camera at every boundary")
    for camera_id in CAMERA_IDS:
        for transform in fixed_world_transforms if camera_id == FIXED_CAMERA_ID else hand_world_transforms:
            if not np.isfinite(transform).all():
                raise ValueError("camera world transform contains non-finite values")
    fixed_reference = fixed_world_transforms[0]
    if any(not np.allclose(fixed_reference, value, atol=1e-9, rtol=0) for value in fixed_world_transforms[1:]):
        raise ValueError("fixed world camera extrinsics changed between boundaries")
    hand_reference = hand_local_transforms[0]
    if any(not np.allclose(hand_reference, value, atol=1e-8, rtol=0) for value in hand_local_transforms[1:]):
        raise ValueError("hand camera mount did not remain fixed relative to the typed hand Frame")
    initial_hand = _pose_matrix(boundaries_by_key[(0, 0)]["hand_frame"])
    moved_hand = _pose_matrix(boundaries_by_key[(0, 12)]["hand_frame"])
    hand_displacement = float(np.linalg.norm(moved_hand[:3, 3] - initial_hand[:3, 3]))
    mounted_camera_displacement = float(np.linalg.norm(
        hand_world_transforms[0][:3, 3]
        - np.asarray(capture_by_boundary_camera[(0, 12, HAND_CAMERA_ID)]["calibration"]["T_world_from_camera"])[:3, 3],
    ))
    if hand_displacement < 0.02 or mounted_camera_displacement < 0.02:
        raise ValueError("hand Frame and mounted camera extrinsics did not move together")

    for camera_id in CAMERA_IDS:
        initial = capture_by_boundary_camera[(0, 0, camera_id)]
        moved = capture_by_boundary_camera[(0, 12, camera_id)]
        rgb0 = raw[initial["array_keys"]["rgb"]]
        rgb1 = raw[moved["array_keys"]["rgb"]]
        changed = int(np.count_nonzero(np.max(np.abs(rgb1 - rgb0), axis=2) > PIXEL_DELTA_THRESHOLD))
        if changed < MIN_CHANGED_PIXELS:
            raise AssertionError(f"{camera_id} initial→moved image changed only {changed} pixels")
        changed_pixel_counts[camera_id] = changed
        initial_boundary = boundaries_by_key[(0, 0)]
        moved_boundary = boundaries_by_key[(0, 12)]
        initial_depth = _check_depth_sample(initial, raw, initial_boundary["peg_frame"])
        moved_depth = _check_depth_sample(moved, raw, moved_boundary["peg_frame"])
        geometry_samples.extend((
            {"round_index": 0, "boundary_index": 0, "camera_id": camera_id, **initial_depth},
            {"round_index": 0, "boundary_index": 12, "camera_id": camera_id, **moved_depth},
        ))
        repeat = reset_rows[(1, camera_id)]
        repeat_depth = _check_depth_sample(repeat, raw, boundaries_by_key[(1, 0)]["peg_frame"])
        geometry_samples.append({"round_index": 1, "boundary_index": 0, "camera_id": camera_id, **repeat_depth})
        repeat_rgb = raw[repeat["array_keys"]["rgb"]]
        repeat_depth_array = raw[repeat["array_keys"]["depth"]]
        repeat_mask = raw[repeat["array_keys"]["mask"]]
        if (not np.array_equal(rgb0, repeat_rgb)
                or not np.array_equal(raw[initial["array_keys"]["depth"]], repeat_depth_array)
                or not np.array_equal(raw[initial["array_keys"]["mask"]], repeat_mask)):
            raise ValueError(f"same fixed ResetPlan {camera_id} image/state did not repeat")

    first_boundary = boundaries_by_key[(0, 0)]["state_boundary"]
    second_boundary = boundaries_by_key[(1, 0)]["state_boundary"]
    for key in ("episode_id", "scene_instance_id", "provider_materialization_id", "boundary_id"):
        if first_boundary[key] == second_boundary[key]:
            raise ValueError(f"second reset did not refresh {key}")
    if first_boundary["reset_sample_id"] != second_boundary["reset_sample_id"]:
        raise ValueError("second reset did not reuse the fixed ResetPlan sample")
    if abs(float(counters["simulation_seconds"]) - 24 * 0.01) > 2e-9:
        raise ValueError("total public clock does not equal the 24 requested intervals")
    cache_probes = {(row["round_index"], row["boundary_index"]): row for row in cache_rows}
    if len(cache_probes) != 26:
        raise ValueError("cache JSONL contains duplicated or missing episode boundaries")
    for boundary in boundary_rows:
        probe = boundary["cache_probe"]
        key = (boundary["round_index"], boundary["boundary_index"])
        if cache_probes.get(key) != {"round_index": key[0], "boundary_index": key[1], **probe}:
            raise ValueError("cache JSONL entry differs from the public boundary receipt")
        if not probe or probe["before"] != probe["after"]:
            raise ValueError("same-boundary public observation read advanced a tracked counter")
        if (probe["before"]["boundary_id"] != _state_boundary_id(boundary["state_boundary"])
                or probe["before"]["sample_clock"] != boundary["sample_clock"]):
            raise ValueError("cache read receipt is not bound to its typed boundary")
    if len({_state_boundary_id(row["state_boundary"]) for row in boundary_rows}) != 26:
        raise ValueError("cache readback did not cover all 26 distinct public boundaries")

    preflight = worker["camera_config_preflight"]
    expected_fk = np.asarray(preflight["world_from_hand_reset_fk"], dtype=np.float64)
    first_hand = _pose_matrix(boundaries_by_key[(0, 0)]["hand_frame"])
    initial_position_error = float(np.linalg.norm(expected_fk[:3, 3] - first_hand[:3, 3]))
    expected_quaternion = _matrix_quaternion_wxyz(expected_fk)
    observed_quaternion = np.asarray(boundaries_by_key[(0, 0)]["hand_frame"]["quaternion_wxyz"], dtype=np.float64)
    rotation_error = min(float(np.linalg.norm(expected_quaternion - observed_quaternion)),
                         float(np.linalg.norm(expected_quaternion + observed_quaternion)))
    second_hand = _pose_matrix(boundaries_by_key[(1, 0)]["hand_frame"])
    reset_state_delta = float(np.max(np.abs(first_hand - second_hand)))
    if (initial_position_error > FRAME_POSITION_ATOL_M or rotation_error > FRAME_QUATERNION_ATOL
            or reset_state_delta > 1e-7):
        raise ValueError("fixed ResetPlan FK does not agree with the independently read public hand Frame")

    byte_root = output if evidence_root is None else Path(evidence_root).resolve()
    total_bytes = sum(path.stat().st_size for path in byte_root.rglob("*") if path.is_file())
    if total_bytes > 256 * 1024 * 1024:
        raise ValueError(f"R04b incremental Evidence exceeds 256 MiB: {total_bytes}")
    return {
        "schema_version": "r04b-public-camera-offline-readback-v1",
        "status": "R04B_PUBLIC_ENV_TWO_CAMERA_OFFLINE_READBACK_PASS",
        "provider_modules_imported": False,
        "taskenv_modules_imported": False,
        "raw_capture_rows": len(capture_rows),
        "public_boundaries": len(boundary_rows),
        "cache_probes": len(cache_rows),
        "camera_ids": CAMERA_IDS,
        "image_changed_pixels": changed_pixel_counts,
        "depth_geometry_samples": geometry_samples,
        "reset_initial_hand_position_error_m": initial_position_error,
        "reset_initial_hand_rotation_matrix_error_fro": rotation_error,
        "reset_rounds_hand_matrix_max_abs_delta": reset_state_delta,
        "hand_displacement_m": hand_displacement,
        "mounted_camera_displacement_m": mounted_camera_displacement,
        "fresh_episode_count": len(all_episodes),
        "fresh_materialization_count": len(all_materializations),
        "raw_camera_arrays_sha256": _sha256(arrays_path),
        "capture_rows_sha256": _sha256(captures_path),
        "boundary_rows_sha256": _sha256(boundaries_path),
        "cache_probes_sha256": _sha256(cache_path),
        "control_rows_sha256": _sha256(controls_path),
        "evidence_bytes": total_bytes,
        "evidence_root": str(byte_root),
        "offline_readback_elapsed_s": time.monotonic() - started,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path)
    args = parser.parse_args(argv)
    started = time.monotonic()
    try:
        receipt = verify(args.output, args.evidence_root)
        receipt["offline_readback_elapsed_s"] = time.monotonic() - started
        path = args.output / "offline_readback_receipt.json"
        path.write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps({"status": receipt["status"], "receipt": str(path)}, sort_keys=True))
        return 0
    except BaseException as error:
        receipt = {
            "schema_version": "r04b-public-camera-offline-readback-v1",
            "status": "R04B_PUBLIC_ENV_TWO_CAMERA_OFFLINE_READBACK_FAIL",
            "error": {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()},
            "offline_readback_elapsed_s": time.monotonic() - started,
        }
        path = args.output / "offline_readback_receipt.json"
        if args.output.exists():
            path.write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps({"status": receipt["status"], "error": receipt["error"]["message"]}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
