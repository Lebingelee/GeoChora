"""Bounded R04b S2 through the public Position Candidate Env camera route."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import replace
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import traceback
import xml.etree.ElementTree as ET

import numpy as np


FIXED_CAMERA_ID = "d04-fixed-square-peg-calibration-v1"
HAND_CAMERA_ID = "d04-panda-hand-mounted-camera-v1"
CAMERA_IDS = (FIXED_CAMERA_ID, HAND_CAMERA_ID)
WIDTH, HEIGHT = 321, 241
HAND_TARGET_DELTA_M = 0.08
PIXEL_DELTA_THRESHOLD = 1.0 / 255.0
MIN_CHANGED_PIXELS = 8
FRAME_POSITION_ATOL_M = 5.0e-4
FRAME_QUATERNION_ATOL = 1.0e-3
LANDMARK_DEPTH_ATOL_M = 2.0e-3
BACKPROJECTION_ATOL_M = 3.0e-3
CLOCK_ATOL_S = 1.0e-9
MAX_OUTER_STEPS = 32
MAX_SUBSTEPS = 160
PHYSICS_DT_S = 0.002
CONTROL_SUBSTEPS = 5


def _json_safe(value):
    """Convert contract values to JSON without silently stringifying arrays."""

    if hasattr(value, "to_mapping") and callable(value.to_mapping):
        return _json_safe(value.to_mapping())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return {"encoding": "hex", "value": value.hex()}
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported JSON evidence value: {type(value).__name__}")


def _write_json(path: Path, value) -> None:
    payload = json.dumps(_json_safe(value), indent=2, sort_keys=True, allow_nan=False) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def _append_jsonl(path: Path, value) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(_json_safe(value), sort_keys=True, allow_nan=False) + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pose_matrix(pose) -> np.ndarray:
    from task_env.utils.rotation import quat_wxyz_to_matrix

    result = np.eye(4, dtype=np.float64)
    result[:3, :3] = quat_wxyz_to_matrix(np.asarray(pose.quaternion_wxyz, dtype=np.float64))
    result[:3, 3] = np.asarray(pose.position, dtype=np.float64)
    return result


def _look_at_world_from_optical(position, target) -> np.ndarray:
    position = np.asarray(position, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    forward = target - position
    norm = float(np.linalg.norm(forward))
    if not math.isfinite(norm) or norm <= 1.0e-9:
        raise ValueError("camera target must differ from camera position")
    forward /= norm
    world_up = np.asarray((0.0, 0.0, 1.0), dtype=np.float64)
    if abs(float(np.dot(forward, world_up))) > 0.98:
        world_up = np.asarray((0.0, 1.0, 0.0), dtype=np.float64)
    right = np.cross(forward, world_up)
    right /= np.linalg.norm(right)
    down = np.cross(forward, right)
    result = np.eye(4, dtype=np.float64)
    result[:3, :3] = np.column_stack((right, down, forward))
    result[:3, 3] = position
    return result


def _pose_from_mjcf_body(body) -> np.ndarray:
    from task_env.utils.rotation import quat_wxyz_to_matrix

    position = np.fromstring(body.get("pos", "0 0 0"), sep=" ", dtype=np.float64)
    quaternion = np.fromstring(body.get("quat", "1 0 0 0"), sep=" ", dtype=np.float64)
    if position.shape != (3,) or quaternion.shape != (4,):
        raise ValueError("R04b peg body has unsupported source pose fields")
    result = np.eye(4, dtype=np.float64)
    result[:3, :3] = quat_wxyz_to_matrix(quaternion)
    result[:3, 3] = position
    return result


def derive_camera_config() -> tuple[object, dict[str, object]]:
    """Freeze the two D04 mount transforms from the candidate ResetPlan and FK."""

    from task_env.artifacts import Timebase
    from task_env.controllers.canonical.kinematics import (
        PANDA_HAND_ORIGIN_TCP_V1,
        PandaKinematics,
    )
    from task_env.environment import compile_task_artifact_v1, sample_episode_reset_plan
    from task_env.observations.canonical_camera.consumer import (
        CameraMountRequestV1,
        CameraObservationConfigV1,
    )
    from task_env.observations.canonical_camera.contracts import MOUNT_FROM_CAMERA, rigid_transform
    from task_env.robots.panda import PandaAgent
    from task_env.runtime.sessions.geophys_source import project_scene_definition_v3_to_mjcf
    from task_env.tasks.position_candidate.builder import (
        POSITION_CANDIDATE_SEED,
        POSITION_CANDIDATE_TASK_ID,
    )
    from task_env.tasks.position_candidate.source import (
        FIXTURE_ROOT,
        _a05_scene,
        _artifact_and_sample,
        _compose_scene_source,
        _task_source,
    )
    from task_env.utils.rotation import matrix_to_quat_wxyz

    scene = _a05_scene()
    legacy, _ = _artifact_and_sample(scene)
    legacy = replace(
        legacy,
        artifact_id="phase-ii-c02b-position-servo-v1",
        task_id=POSITION_CANDIDATE_TASK_ID,
        artifact_version="candidate-v1",
        timebase=Timebase(PHYSICS_DT_S, CONTROL_SUBSTEPS, PHYSICS_DT_S * CONTROL_SUBSTEPS),
    )
    task_source = replace(
        _task_source(scene), task_id=legacy.task_id, version=legacy.artifact_version,
    )
    artifact = compile_task_artifact_v1(task_source, scene, legacy)
    reset_plan = sample_episode_reset_plan(
        task_source, scene, artifact, task_seed=POSITION_CANDIDATE_SEED,
    )
    if reset_plan.reset_sample.task_seed != 31:
        raise ValueError("R04b camera geometry requires the fixed Position ResetPlan seed 31")

    panda_source = Path(PandaAgent().asset_manifest().mjcf_sources[0]).resolve()
    source_xml = _compose_scene_source(scene, panda_source.parent, physics_dt=PHYSICS_DT_S)
    projected_xml = project_scene_definition_v3_to_mjcf(source_xml, scene)
    model = PandaKinematics(projected_xml, tcp_profile=PANDA_HAND_ORIGIN_TCP_V1)
    joint_positions = reset_plan.reset_sample.joint_position
    q = np.asarray([joint_positions[f"panda-main/joint{index}"] for index in range(1, 8)], dtype=np.float64)
    world_from_hand, _ = model.fk_jacobian(q)
    reset_hand_quaternion = matrix_to_quat_wxyz(world_from_hand[:3, :3])
    requested_hand_target = {
        "position": [
            float(world_from_hand[0, 3] + HAND_TARGET_DELTA_M),
            float(world_from_hand[1, 3]),
            float(world_from_hand[2, 3]),
        ],
        "quaternion_wxyz": [float(value) for value in reset_hand_quaternion],
    }

    xml_root = ET.fromstring(source_xml)
    world = xml_root.find("worldbody")
    peg_body = None if world is None else world.find("body[@name='peg1']")
    if peg_body is None:
        raise ValueError("fixed candidate source must place peg1 directly in the worldbody")
    world_from_peg = _pose_from_mjcf_body(peg_body)
    world_from_camera_mount = np.asarray(MOUNT_FROM_CAMERA, dtype=np.float64)
    if world_from_camera_mount.shape != (4, 4):
        raise ValueError("canonical camera mount transform is malformed")
    camera_from_mount = np.linalg.inv(world_from_camera_mount)

    peg_position = world_from_peg[:3, 3]
    fixed_optical = _look_at_world_from_optical(
        peg_position + np.asarray((0.0, -1.5, 0.0)), peg_position,
    )
    world_from_fixed_mount = fixed_optical @ camera_from_mount
    fixed_parent_from_mount = world_from_fixed_mount

    hand_optical_position = (
        world_from_hand[:3, 3]
        + world_from_hand[:3, :3] @ np.asarray((0.0, 0.0, 0.035), dtype=np.float64)
    )
    hand_optical = _look_at_world_from_optical(hand_optical_position, peg_position)
    world_from_hand_mount = hand_optical @ camera_from_mount
    hand_from_mount = np.linalg.inv(world_from_hand) @ world_from_hand_mount

    fixed_parent_from_mount = rigid_transform(fixed_parent_from_mount)
    hand_from_mount = rigid_transform(hand_from_mount)
    config = CameraObservationConfigV1(
        schema_version="camera-observation-consumer-v1",
        cameras=(
            CameraMountRequestV1(
                "camera-mount-request-v1", FIXED_CAMERA_ID, "world",
                tuple(tuple(float(v) for v in row) for row in fixed_parent_from_mount),
            ),
            CameraMountRequestV1(
                "camera-mount-request-v1", HAND_CAMERA_ID, "hand",
                tuple(tuple(float(v) for v in row) for row in hand_from_mount),
            ),
        ),
    )
    config.validate_production_envelope()
    config.capacity(16)
    evidence = {
        "recipe": "D04 optical camera look-at; fixed world calibration view and hand-local mount from fixed ResetPlan FK",
        "task_artifact_hash": artifact.identity_hash,
        "scene_identity_hash": scene.identity_hash,
        "reset_plan_identity_hash": reset_plan.identity_hash,
        "reset_sample_id": reset_plan.reset_sample.sample_id,
        "task_seed": reset_plan.reset_sample.task_seed,
        "joint_positions_rad": {f"joint{i}": float(q[i - 1]) for i in range(1, 8)},
        "panda_source_path": str(panda_source),
        "panda_source_sha256": hashlib.sha256(panda_source.read_bytes()).hexdigest(),
        "projected_panda_scene_source_sha256": hashlib.sha256(projected_xml.encode()).hexdigest(),
        "peg_source_sha256": hashlib.sha256((FIXTURE_ROOT / "square_peg.xml").read_bytes()).hexdigest(),
        "world_from_hand_reset_fk": world_from_hand.tolist(),
        "requested_hand_target_pose_world": requested_hand_target,
        "world_from_peg_source_pose": world_from_peg.tolist(),
        "camera_observation_config": config.to_mapping(),
        "camera_observation_config_sha256": hashlib.sha256(
            json.dumps(config.to_mapping(), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest(),
    }
    return config, evidence


def _frame_pose(view, entity_id: str, frame_id: str):
    matches = [
        item.pose_world for item in view.frames
        if item.frame.entity_id == entity_id and item.frame.frame_id == frame_id
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one typed Canonical Frame {entity_id}/{frame_id}, got {len(matches)}")
    return matches[0]


def _quat_error(first, second) -> float:
    a = np.asarray(first, dtype=np.float64)
    b = np.asarray(second, dtype=np.float64)
    return min(float(np.linalg.norm(a - b)), float(np.linalg.norm(a + b)))


def _ray_box_hit(metadata, peg_pose, row: int, col: int):
    from task_env.objects.nut_assembly import PEG_HALF_HEIGHT, SQUARE_PEG_HALF_WIDTH
    from task_env.utils.rotation import quat_wxyz_to_matrix

    K = np.asarray(metadata.K, dtype=np.float64)
    pixel = np.asarray((col + 0.5, row + 0.5, 1.0), dtype=np.float64)
    ray_camera = np.linalg.inv(K) @ pixel
    world_from_camera = np.asarray(metadata.T_world_from_camera, dtype=np.float64)
    ray_world = world_from_camera[:3, :3] @ ray_camera
    origin_world = world_from_camera[:3, 3]
    box_from_world = quat_wxyz_to_matrix(np.asarray(peg_pose.quaternion_wxyz, dtype=np.float64)).T
    ray_box = box_from_world @ ray_world
    origin_box = box_from_world @ (origin_world - np.asarray(peg_pose.position, dtype=np.float64))
    half_extent = np.asarray((SQUARE_PEG_HALF_WIDTH, SQUARE_PEG_HALF_WIDTH, PEG_HALF_HEIGHT))
    near, far = -math.inf, math.inf
    for axis in range(3):
        if abs(float(ray_box[axis])) <= 1.0e-12:
            if abs(float(origin_box[axis])) > half_extent[axis]:
                raise ValueError("projected calibration ray misses the square peg")
            continue
        first = (-half_extent[axis] - origin_box[axis]) / ray_box[axis]
        second = (half_extent[axis] - origin_box[axis]) / ray_box[axis]
        near = max(near, min(float(first), float(second)))
        far = min(far, max(float(first), float(second)))
    if near < 0 or far < near:
        raise ValueError("square peg is not in front of the calibration ray")
    hit_box = origin_box + near * ray_box
    hit_world = np.asarray(peg_pose.position) + quat_wxyz_to_matrix(peg_pose.quaternion_wxyz) @ hit_box
    return float(near), hit_world


def _verify_depth_sample(metadata, depth: np.ndarray, peg_pose) -> dict[str, object]:
    K = np.asarray(metadata.K, dtype=np.float64)
    T_camera_from_world = np.asarray(metadata.T_camera_from_world, dtype=np.float64)
    peg_position = np.asarray(peg_pose.position, dtype=np.float64)
    camera_point = T_camera_from_world[:3, :3] @ peg_position + T_camera_from_world[:3, 3]
    if camera_point[2] <= 0:
        raise ValueError("square peg calibration landmark is behind the camera")
    pixel = K @ camera_point
    pixel = pixel[:2] / pixel[2]
    col = int(round(float(pixel[0]) - 0.5))
    row = int(round(float(pixel[1]) - 0.5))
    if not (0 <= row < depth.shape[0] and 0 <= col < depth.shape[1]):
        raise ValueError("square peg calibration landmark is outside the image")
    expected_depth, expected_hit = _ray_box_hit(metadata, peg_pose, row, col)
    observed_depth = float(depth[row, col])
    if observed_depth <= 0 or abs(observed_depth - expected_depth) > LANDMARK_DEPTH_ATOL_M:
        raise AssertionError(
            f"optical-Z at pixel {(row, col)} is {observed_depth:g} m; expected {expected_depth:g} m"
        )
    pixel_ray = np.linalg.inv(K) @ np.asarray((col + 0.5, row + 0.5, 1.0))
    world_from_camera = np.asarray(metadata.T_world_from_camera, dtype=np.float64)
    backprojected = world_from_camera[:3, :3] @ (pixel_ray * observed_depth) + world_from_camera[:3, 3]
    error = float(np.linalg.norm(backprojected - expected_hit))
    if error > BACKPROJECTION_ATOL_M:
        raise AssertionError(f"optical-Z back-projection error is {error:g} m")
    return {
        "row": row,
        "column": col,
        "landmark_world_m": peg_position.tolist(),
        "expected_optical_z_m": expected_depth,
        "observed_optical_z_m": observed_depth,
        "backprojection_error_m": error,
        "expected_surface_world_m": expected_hit.tolist(),
        "backprojected_surface_world_m": backprojected.tolist(),
    }


def _public_label_map_matches(capture_metadata, raw_label_map) -> bool:
    """Compare the canonical JSON mapping across Contract decode boundaries."""

    return capture_metadata.canonical_label_map.to_mapping() == raw_label_map


def _validate_public_boundary(env, observation, info, round_index, rows, counters, *, repeat_probe=True):
    from task_env.observations.canonical_camera.consumer import CameraObservationBoundaryV1

    if "camera_observation_v1" not in info:
        raise ValueError("public Env info omitted required camera_observation_v1 metadata")
    boundary_value = CameraObservationBoundaryV1.from_mapping(info["camera_observation_v1"])
    boundary_value.validate()
    view = env.typed_state.view
    boundary = view.boundary
    clock = view.sample_clock
    if (boundary_value.boundary_index != boundary.control_step
            or boundary_value.state_boundary_id != boundary.boundary_id
            or boundary_value.simulation_time_s != clock.simulation_time_s
            or clock.sample_index != boundary.control_step
            or clock.clock_domain != "evaluation_boundary"):
        raise ValueError("public camera metadata disagrees with its typed state publication")
    if tuple(observation) != ("state", "privileged_state", "rgb", "depth", "entity_mask"):
        raise ValueError("camera observation groups differ from the public Position schema")
    if not env.observation_space.contains(observation):
        raise ValueError("public Position observation_space rejected an actual camera observation")
    env.camera_observation_schema.validate(observation)

    start_index = len(rows) - len(CAMERA_IDS)
    current_rows = rows[start_index:]
    if tuple(row["camera_id"] for row in current_rows) != CAMERA_IDS:
        raise ValueError("actual public boundary did not perform one capture per canonical camera")
    frames = {item.frame.entity_id: item.frame for item in view.frames}
    frame_entity_ids = {frame.entity_id for frame in frames.values()}
    hand_pose = _frame_pose(view, "panda-main", "hand")
    peg_pose = _frame_pose(view, "square-peg-instance", "peg1")

    for capture_meta, row in zip(boundary_value.captures, current_rows):
        camera_id = capture_meta.camera_id
        if row["camera_id"] != camera_id:
            raise ValueError("renderer capture order differs from public metadata order")
        capture_identity = capture_meta.capture_identity
        if (capture_identity.state_boundary != boundary
                or capture_identity.sample_clock != clock
                or tuple(capture_identity.modalities) != ("depth", "entity_instance_segmentation", "rgb")):
            raise ValueError("capture identity lost the typed boundary, clock, or required modalities")
        if capture_meta.mask_sha256 != row["mask_sha256"]:
            raise ValueError("public capture metadata mask digest differs from the raw Entity mask")
        if not _public_label_map_matches(capture_meta, row["label_map"]):
            raise ValueError("public canonical label map differs from the raw renderer capture")
        if row["capture_identity"]["identity_hash"] != capture_identity.identity_hash:
            raise ValueError("session capture identity differs from the public metadata identity")

        rgb, depth, mask = row["rgb"], row["depth"], row["mask"]
        if (rgb.shape != (HEIGHT, WIDTH, 3) or rgb.dtype != np.float32
                or not np.isfinite(rgb).all() or np.any(rgb < 0) or np.any(rgb > 1)):
            raise ValueError(f"{camera_id} RGB violates HWC float32 [0,1]")
        if (depth.shape != (HEIGHT, WIDTH) or depth.dtype != np.float32
                or not np.isfinite(depth).all() or np.any(depth < 0)
                or not np.any(depth > 0) or not np.any(depth == 0)):
            raise ValueError(f"{camera_id} depth violates finite metric optical-Z with invalid=0")
        if mask.shape != (HEIGHT, WIDTH) or mask.dtype != np.uint32:
            raise ValueError(f"{camera_id} Entity mask violates HxW uint32")
        label_map = capture_meta.canonical_label_map
        label_map.validate()
        labels = {item.label for item in label_map.labels}
        entity_ids = {item.entity_id for item in label_map.labels}
        if not entity_ids.issubset(frame_entity_ids):
            raise ValueError("Entity label map refers to IDs outside the typed canonical state")
        mask_values = {int(value) for value in np.unique(mask)}
        if 0 not in mask_values or not mask_values.issubset({0, *labels}):
            raise ValueError("Entity mask includes a non-canonical label or lacks background label zero")

        calibration = capture_meta.calibration
        expected_parent = np.eye(4, dtype=np.float64)
        if camera_id == HAND_CAMERA_ID:
            expected_parent = _pose_matrix(hand_pose)
        expected_world_from_camera = (
            expected_parent
            @ np.asarray(calibration.camera.T_parent_from_mount, dtype=np.float64)
            @ np.asarray(calibration.camera.T_mount_from_camera, dtype=np.float64)
        )
        camera_error = float(np.max(np.abs(
            expected_world_from_camera - np.asarray(calibration.T_world_from_camera, dtype=np.float64),
        )))
        if camera_error > 1.0e-9:
            raise AssertionError(f"{camera_id} camera calibration disagrees with the typed parent frame")
        sync = row["sync"]
        if (sync["state_boundary"]["boundary_id"] != boundary.boundary_id
                or sync["sample_clock"] != clock.to_mapping()
                or sync["consumer_id"] != row["consumer_id"]):
            raise ValueError("renderer sync receipt is not bound to the public capture boundary")
        if (float(sync["max_frame_position_error_m"]) > FRAME_POSITION_ATOL_M
                or float(sync["max_frame_quaternion_sign_invariant_l2_error"]) > FRAME_QUATERNION_ATOL):
            raise AssertionError("renderer Frame sync exceeds the frozen D04 pose tolerances")
        row["public_capture_metadata"] = capture_meta.to_mapping()
        row["typed_frame_hand"] = {
            "position": list(hand_pose.position), "quaternion_wxyz": list(hand_pose.quaternion_wxyz),
        }
        row["typed_frame_peg"] = {
            "position": list(peg_pose.position), "quaternion_wxyz": list(peg_pose.quaternion_wxyz),
        }
        row["camera_transform_error_max_abs"] = camera_error

    cache_result = None
    if repeat_probe:
        before = {
            "control_step": int(env.state.control_step),
            "simulation_time_s": float(env.state.simulation_time),
            "boundary_id": boundary.boundary_id,
            "sample_clock": clock.to_mapping(),
            "physics_substeps": counters["physics_substeps"],
            "controller_compute_calls": counters["controller_compute_calls"],
            "provider_interval_step_calls": counters["provider_interval_step_calls"],
            "renderer_capture_calls": counters["renderer_capture_calls"],
            "renderer_render_calls": counters["renderer_render_calls"],
            "mj_step_during_capture": counters["mj_step_during_capture"],
            "mj_forward_during_capture": counters["mj_forward_during_capture"],
        }
        repeated, repeated_info, _ = env.observation(env.state)
        after_view = env.typed_state.view
        after = {
            "control_step": int(env.state.control_step),
            "simulation_time_s": float(env.state.simulation_time),
            "boundary_id": after_view.boundary.boundary_id,
            "sample_clock": after_view.sample_clock.to_mapping(),
            "physics_substeps": counters["physics_substeps"],
            "controller_compute_calls": counters["controller_compute_calls"],
            "provider_interval_step_calls": counters["provider_interval_step_calls"],
            "renderer_capture_calls": counters["renderer_capture_calls"],
            "renderer_render_calls": counters["renderer_render_calls"],
            "mj_step_during_capture": counters["mj_step_during_capture"],
            "mj_forward_during_capture": counters["mj_forward_during_capture"],
        }
        if before != after:
            raise AssertionError("same-boundary public observation advanced state, controller, physics, or renderer")
        for group in ("rgb", "depth", "entity_mask"):
            for camera_id in CAMERA_IDS:
                if not np.array_equal(observation[group][camera_id], repeated[group][camera_id]):
                    raise AssertionError("same-boundary cache read changed a public camera array")
        if repeated_info.get("camera_observation_v1") != info.get("camera_observation_v1"):
            raise AssertionError("same-boundary cache read returned another camera metadata boundary")
        cache_result = {"before": before, "after": after, "zero_progress": True}

    boundary_index = boundary.control_step
    return {
        "round_index": round_index,
        "boundary_index": boundary_index,
        "state_boundary": boundary.to_mapping(),
        "sample_clock": clock.to_mapping(),
        "hand_frame": {"position": list(hand_pose.position), "quaternion_wxyz": list(hand_pose.quaternion_wxyz)},
        "peg_frame": {"position": list(peg_pose.position), "quaternion_wxyz": list(peg_pose.quaternion_wxyz)},
        "canonical_entity_ids": sorted(frame_entity_ids),
        "capture_rows": [row["index"] for row in current_rows],
        "cache_probe": cache_result,
        "observation_ee_pose": np.asarray(observation["state"]["ee_pose"]).tolist(),
        "source_closure_digest": env.value["source"].source_closure_digest,
        "controller_identity": env.controller.identity,
        "controller_plan_identity_hash": env.position_plan.identity_hash,
        "task_artifact_hash": env.artifact.identity_hash,
        "scene_identity_hash": view.scene_identity_hash,
    }


def _camera_render_json(camera_capture, camera_id, index, round_index, capture_kind, session, arrays):
    capture_identity = camera_capture.capture_identity
    if capture_identity is None or camera_capture.segmentation is None:
        raise ValueError("R04b capture requires a public capture identity and canonical Entity mask")
    rgb = np.ascontiguousarray(camera_capture.rgb)
    depth = np.ascontiguousarray(camera_capture.depth)
    mask = np.ascontiguousarray(camera_capture.segmentation.mask)
    if (rgb.dtype != np.float32 or depth.dtype != np.float32 or mask.dtype != np.uint32):
        raise TypeError("camera capture dtypes differ from the public R04b contract")
    keys = {"rgb": f"rgb_{index:03d}", "depth": f"depth_{index:03d}", "mask": f"mask_{index:03d}"}
    arrays[keys["rgb"]] = rgb.copy()
    arrays[keys["depth"]] = depth.copy()
    arrays[keys["mask"]] = mask.copy()
    label_map = camera_capture.segmentation.label_map
    mask_sha256 = hashlib.sha256(mask.tobytes(order="C")).hexdigest()
    sync = session.last_sync
    if sync is None:
        raise ValueError("dynamic camera capture did not publish its Renderer sync receipt")
    return {
        "index": index,
        "round_index": round_index,
        "capture_kind": capture_kind,
        "camera_id": camera_id,
        "consumer_id": session.consumer_id,
        "capture_identity": capture_identity.to_mapping(),
        "capture_identity_identity_hash": capture_identity.identity_hash,
        "calibration": camera_capture.metadata.to_mapping(),
        "label_map": label_map.to_mapping(),
        "mask_sha256": mask_sha256,
        "sync": sync.to_mapping(),
        "array_keys": keys,
        "rgb": rgb,
        "depth": depth,
        "mask": mask,
        "public_capture_metadata": None,
    }


def run_s2(output: str | Path) -> dict[str, object]:
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("R04b native output must be fresh; existing evidence is preserved")
    output.mkdir(parents=True, exist_ok=True)
    counters = {
        "reset_attempts": 0,
        "materialization_ids": [],
        "outer_steps": 0,
        "physics_substeps": 0,
        "simulation_seconds": 0.0,
        "provider_interval_step_calls": 0,
        "controller_compute_calls": 0,
        "renderer_capture_calls": 0,
        "renderer_capture_successes": 0,
        "renderer_render_calls": 0,
        "mj_step_during_capture": 0,
        "mj_forward_during_capture": 0,
        "session_close_calls": 0,
        "native_renderer_close_calls": 0,
        "native_renderer_ids_closed": [],
        "public_boundary_captures": 0,
        "isolation_capture_calls": 0,
    }
    arrays = {}
    capture_rows = []
    boundary_rows = []
    cache_rows = []
    control_rows = []
    action_trajectories = []
    sessions = []
    renderer_ids = set()
    renderer_camera_by_id = {}
    active_capture = {"value": False, "session": None}
    context = {"round_index": -1, "capture_kind": "public"}
    env = None
    primary_error = None
    cleanup_error = None
    phase = "preflight"
    start_time = __import__("time").monotonic()
    runtime = {}
    config_evidence = {}
    geometry_results = []
    round_initial = {}
    round_moved = {}
    graphics = []
    graphics_seen = set()
    env_close_calls = 0

    try:
        if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
            raise RuntimeError("PYTHONDONTWRITEBYTECODE must be set before the native worker starts")
        if os.environ.get("MUJOCO_GL") != "egl" or os.environ.get("PYOPENGL_PLATFORM") != "egl":
            raise RuntimeError("R04b requires the frozen MuJoCo/PyOpenGL EGL selection before imports")
        worktree = Path(__file__).resolve().parents[3]
        if Path.cwd().resolve() != worktree:
            raise RuntimeError(f"native worker cwd must be the camera worktree: {worktree}")
        if os.environ.get("PYTHONPATH", "").split(os.pathsep)[0] != str(worktree):
            raise RuntimeError("native worker PYTHONPATH must begin with the camera worktree")

        config, config_evidence = derive_camera_config()
        config_evidence["camera_mount_request_sha256"] = config_evidence["camera_observation_config_sha256"]
        from task_env import make_env

        task_env_module = importlib.import_module("task_env")
        registry_module = importlib.import_module("task_env.tasks.position_candidate")
        camera_package = importlib.import_module("task_env.render.camera")
        from task_env.controllers.canonical.position_profile import PandaPositionServoProfileV1
        from task_env.diagnostics.tasks.c02b_position_s2_probe import _request
        from task_env.observations.canonical_camera.consumer import CAMERA_IDS as PUBLIC_CAMERA_IDS
        from task_env.observations.canonical_camera.consumer import CameraObservationBoundaryV1
        from task_env.utils.rotation import quat_wxyz_to_matrix
        import mujoco

        if tuple(PUBLIC_CAMERA_IDS) != CAMERA_IDS:
            raise AssertionError("public camera IDs changed from the frozen R04b route")
        if (not Path(task_env_module.__file__).resolve().is_relative_to(worktree)
                or not Path(registry_module.__file__).resolve().is_relative_to(worktree)):
            raise RuntimeError("TaskEnv modules were not imported from the camera worktree")
        source_workspace = output / "source_workspace_public"
        if source_workspace.exists():
            raise ValueError("public source_workspace path is not fresh")
        env = make_env("panda-position-servo-candidate-v1", config={
            "provider": "geophys",
            "backend": "cpu",
            "horizon": 16,
            "source_workspace": str(source_workspace),
            "camera_observation": config,
        })
        runtime = {
            "python": platform.python_version(),
            "python_executable": sys.executable,
            "core_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=worktree, text=True).strip(),
            "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=worktree, text=True).strip(),
            "geophys_revision": subprocess.check_output(["git", "-C", str(worktree / "GeoPhys"), "rev-parse", "HEAD"], text=True).strip(),
            "menagerie_revision": subprocess.check_output(["git", "-C", str(worktree / "asset/external/mujoco_menagerie"), "rev-parse", "HEAD"], text=True).strip(),
            "numpy": np.__version__,
            "mujoco": str(mujoco.__version__),
            "task_env_module": str(Path(task_env_module.__file__).resolve()),
            "position_candidate_module": str(Path(registry_module.__file__).resolve()),
            "provider": "geophys",
            "backend": "cpu",
            "physics_dt_s": PHYSICS_DT_S,
            "control_substeps": CONTROL_SUBSTEPS,
            "horizon": 16,
            "source_closure_digest": env.value["source"].source_closure_digest,
            "artifact_identity_hash": env.artifact.identity_hash,
            "controller_identity": env.controller.identity,
            "controller_plan_identity_hash": env.value["controller_binding_plan"].identity_hash,
            "scene_identity_hash": env.value["source"].scene_definition.identity_hash,
            "reset_plan_identity_hash": env.value["reset_plan"].identity_hash,
            "reset_sample_id": env.value["reset_plan"].reset_sample.sample_id,
            "reset_seed": env.value["reset_plan"].reset_sample.task_seed,
        }
        frozen_head = os.environ.get("R04B_FROZEN_HEAD")
        runtime["frozen_head"] = frozen_head
        tracked_status = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all"], cwd=worktree, text=True,
        )
        if not frozen_head or runtime["core_revision"] != frozen_head or tracked_status.strip():
            raise RuntimeError("camera worker HEAD or clean tree differs from its native freeze")
        if subprocess.run(
            ["git", "merge-base", "--is-ancestor", "b0b26e95ddfd7b5128401261f05541bb19586372", "HEAD"],
            cwd=worktree, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode != 0:
            raise RuntimeError("camera worker HEAD is not a descendant of the frozen input")
        if runtime["geophys_revision"] != "a53a8cfed7c9d6464274b5c96fca601271dc4ee4":
            raise RuntimeError("camera worker GeoPhys pin drifted from the frozen input")
        if runtime["menagerie_revision"] != "b846dd12bc459d776cccb3dee0b1d02acbf7a9c7":
            raise RuntimeError("camera worker Menagerie pin drifted from the frozen input")
        if not isinstance(env.controller, PandaPositionServoProfileV1):
            raise TypeError("public Position Candidate did not bind its existing Position Controller")

        original_factory = camera_package.create_dynamic_camera_session
        original_compute = PandaPositionServoProfileV1.compute
        original_render = mujoco.Renderer.render
        original_renderer_close = mujoco.Renderer.close
        original_mj_step = mujoco.mj_step
        original_mj_forward = mujoco.mj_forward
        runtime_session_type = None

        def wrapped_factory(camera, execution, **kwargs):
            session = original_factory(camera, execution, **kwargs)
            sessions.append(session)
            renderer = getattr(session, "_renderer", None)
            if renderer is not None:
                renderer_id = id(renderer)
                renderer_ids.add(renderer_id)
                renderer_camera_by_id[renderer_id] = camera.camera_id
            old_capture = session.capture
            old_close = session.close

            def wrapped_capture(state):
                counters["renderer_capture_calls"] += 1
                if context["capture_kind"] == "isolation":
                    counters["isolation_capture_calls"] += 1
                active_capture.update(value=True, session=session)
                try:
                    captured = old_capture(state)
                    counters["renderer_capture_successes"] += 1
                    if camera.camera_id not in graphics_seen:
                        graphics.append({
                            "round_index": context["round_index"],
                            "camera_id": camera.camera_id,
                            **session.graphics_device_info(),
                        })
                        graphics_seen.add(camera.camera_id)
                    row = _camera_render_json(
                        captured, camera.camera_id, len(capture_rows), context["round_index"],
                        context["capture_kind"], session, arrays,
                    )
                    capture_rows.append(row)
                    return captured
                finally:
                    active_capture.update(value=False, session=None)

            def wrapped_close():
                counters["session_close_calls"] += 1
                return old_close()

            session.capture = wrapped_capture
            session.close = wrapped_close
            return session

        def wrapped_compute(controller, *args, **kwargs):
            counters["controller_compute_calls"] += 1
            return original_compute(controller, *args, **kwargs)

        def wrapped_render(renderer, *args, **kwargs):
            if id(renderer) in renderer_ids:
                counters["renderer_render_calls"] += 1
            return original_render(renderer, *args, **kwargs)

        def wrapped_renderer_close(renderer, *args, **kwargs):
            if id(renderer) in renderer_ids:
                counters["native_renderer_close_calls"] += 1
                counters["native_renderer_ids_closed"].append(renderer_camera_by_id[id(renderer)])
            return original_renderer_close(renderer, *args, **kwargs)

        def wrapped_mj_step(*args, **kwargs):
            if active_capture["value"]:
                counters["mj_step_during_capture"] += 1
            return original_mj_step(*args, **kwargs)

        def wrapped_mj_forward(*args, **kwargs):
            if active_capture["value"]:
                counters["mj_forward_during_capture"] += 1
            return original_mj_forward(*args, **kwargs)

        phase = "native_instrumentation"
        with ExitStack() as stack:
            stack.enter_context(importlib.import_module("unittest.mock").patch.object(
                camera_package, "create_dynamic_camera_session", wrapped_factory,
            ))
            stack.enter_context(importlib.import_module("unittest.mock").patch.object(
                PandaPositionServoProfileV1, "compute", wrapped_compute,
            ))
            stack.enter_context(importlib.import_module("unittest.mock").patch.object(
                mujoco.Renderer, "render", wrapped_render,
            ))
            stack.enter_context(importlib.import_module("unittest.mock").patch.object(
                mujoco.Renderer, "close", wrapped_renderer_close,
            ))
            stack.enter_context(importlib.import_module("unittest.mock").patch.object(
                mujoco, "mj_step", wrapped_mj_step,
            ))
            stack.enter_context(importlib.import_module("unittest.mock").patch.object(
                mujoco, "mj_forward", wrapped_mj_forward,
            ))
            try:
                for round_index in (0, 1):
                    context["round_index"] = round_index
                    context["capture_kind"] = "public"
                    phase = f"reset_round_{round_index + 1}"
                    counters["reset_attempts"] += 1
                    if counters["reset_attempts"] > 2:
                        raise RuntimeError("native reset attempt budget exceeded")
                    observation, info = env.reset(seed=31)
                    if runtime_session_type is None:
                        runtime_session_type = type(env.session)
                        original_runtime_step = runtime_session_type.step

                        def wrapped_runtime_step(session, *args, **kwargs):
                            counters["provider_interval_step_calls"] += 1
                            return original_runtime_step(session, *args, **kwargs)

                        stack.enter_context(importlib.import_module("unittest.mock").patch.object(
                            runtime_session_type, "step", wrapped_runtime_step,
                        ))
                    typed = env.typed_state.view
                    materialization_id = typed.boundary.provider_materialization_id
                    counters["materialization_ids"].append(materialization_id)
                    if (env.value["reset_plan"].identity_hash != runtime["reset_plan_identity_hash"]
                            or env.sample.sample_id != runtime["reset_sample_id"]):
                        raise AssertionError("reset did not reuse the fixed TaskArtifact ResetPlan")
                    initial_hand = _frame_pose(typed, "panda-main", "hand")
                    initial_peg = _frame_pose(typed, "square-peg-instance", "peg1")
                    if round_index == 0:
                        expected_hand = np.asarray(config_evidence["world_from_hand_reset_fk"])
                        observed_hand = _pose_matrix(initial_hand)
                        position_error = float(np.linalg.norm(expected_hand[:3, 3] - observed_hand[:3, 3]))
                        quaternion_error = _quat_error(
                            __import__("task_env.utils.rotation", fromlist=["matrix_to_quat_wxyz"]).matrix_to_quat_wxyz(expected_hand[:3, :3]),
                            initial_hand.quaternion_wxyz,
                        )
                        expected_peg = np.asarray(config_evidence["world_from_peg_source_pose"])
                        peg_error = float(np.linalg.norm(expected_peg[:3, 3] - np.asarray(initial_peg.position)))
                        if position_error > FRAME_POSITION_ATOL_M or quaternion_error > FRAME_QUATERNION_ATOL:
                            raise AssertionError("fixed ResetPlan FK disagrees with the public reset hand Frame")
                        if peg_error > FRAME_POSITION_ATOL_M:
                            raise AssertionError("square-peg source pose disagrees with its public reset Frame")
                        config_evidence["reset_frame_oracle"] = {
                            "hand_position_error_m": position_error,
                            "hand_quaternion_sign_invariant_l2_error": quaternion_error,
                            "peg_position_error_m": peg_error,
                        }
                    boundary_rows.append(_validate_public_boundary(
                        env, observation, info, round_index, capture_rows, counters,
                    ))
                    cache_rows.append({
                        "round_index": round_index, "boundary_index": 0,
                        **boundary_rows[-1]["cache_probe"],
                    })
                    counters["public_boundary_captures"] += len(CAMERA_IDS)
                    round_initial[round_index] = {
                        "hand": initial_hand,
                        "peg": initial_peg,
                        "observation": observation,
                        "boundary": boundary_rows[-1],
                        "capture_indices": list(boundary_rows[-1]["capture_rows"]),
                    }

                    from task_env.diagnostics.tasks.c02b_position_s2_probe import _request
                    frozen_target = config_evidence["requested_hand_target_pose_world"]
                    hand_target = type(initial_hand)(
                        tuple(frozen_target["position"]), tuple(frozen_target["quaternion_wxyz"]),
                    )
                    request = _request(env.value["controller_binding_plan"], hand_target, 1.0)
                    request_mapping = request.to_mapping()
                    request_hash = hashlib.sha256(json.dumps(
                        request_mapping, sort_keys=True, separators=(",", ":"), allow_nan=False,
                    ).encode()).hexdigest()
                    action_trajectories.append({
                        "round_index": round_index,
                        "initial_hand_pose": {
                            "position": list(initial_hand.position),
                            "quaternion_wxyz": list(initial_hand.quaternion_wxyz),
                        },
                        "target_hand_pose": {
                            "position": list(hand_target.position),
                            "quaternion_wxyz": list(hand_target.quaternion_wxyz),
                        },
                        "world_position_delta_m": HAND_TARGET_DELTA_M,
                        "gripper_target": 1.0,
                        "request_identity_sha256": request_hash,
                        "structured_action_request": request_mapping,
                        "controller_identity": env.controller.identity,
                        "controller_plan_identity_hash": env.position_plan.identity_hash,
                    })
                    for _ in range(12):
                        if counters["outer_steps"] >= MAX_OUTER_STEPS:
                            raise RuntimeError("native outer-step budget exceeded")
                        before_state = env.state
                        before_clock = env.typed_state.view.sample_clock
                        phase = f"step_round_{round_index + 1}_{before_state.control_step + 1}"
                        result = env.step(request)
                        if not isinstance(result, tuple) or len(result) != 5:
                            raise TypeError("public Position Env step must return the existing five-value transition")
                        observation, _reward, terminated, truncated, info = result
                        after_state = env.state
                        after_view = env.typed_state.view
                        elapsed = float(after_view.sample_clock.simulation_time_s - before_clock.simulation_time_s)
                        substeps = int(round(elapsed / PHYSICS_DT_S))
                        tolerance = CLOCK_ATOL_S
                        if (after_view.boundary.control_step != before_state.control_step + 1
                                or substeps != CONTROL_SUBSTEPS
                                or abs(elapsed - CONTROL_SUBSTEPS * PHYSICS_DT_S) > tolerance
                                or terminated or truncated):
                            raise AssertionError("public Position step did not complete one 5×2 ms interval")
                        counters["outer_steps"] += 1
                        counters["physics_substeps"] += substeps
                        counters["simulation_seconds"] += elapsed
                        if counters["physics_substeps"] > MAX_SUBSTEPS:
                            raise RuntimeError("native physical-substep budget exceeded")
                        boundary_rows.append(_validate_public_boundary(
                            env, observation, info, round_index, capture_rows, counters,
                        ))
                        transition = env.last_position_transition
                        if not isinstance(transition, tuple) or len(transition) != 3:
                            raise TypeError("Position Env did not expose the existing Controller target/application receipt")
                        canonical_action, target, applied = transition
                        control_row = {
                            "round_index": round_index,
                            "control_step": after_view.boundary.control_step,
                            "request_identity_sha256": request_hash,
                            "controller_identity": env.controller.identity,
                            "controller_plan_identity_hash": env.position_plan.identity_hash,
                            "canonical_action": canonical_action.to_mapping(),
                            "target": target.to_mapping(),
                            "target_identity_hash": target.identity_hash,
                            "applied": applied.to_mapping(),
                            "applied_target_hash": applied.target_hash,
                        }
                        if control_row["target_identity_hash"] != control_row["applied_target_hash"]:
                            raise AssertionError("Position Controller acknowledgement does not bind its actual target")
                        control_rows.append(control_row)
                        boundary_rows[-1]["control_transition"] = control_row
                        cache_rows.append({
                            "round_index": round_index,
                            "boundary_index": after_view.boundary.control_step,
                            **boundary_rows[-1]["cache_probe"],
                        })
                        counters["public_boundary_captures"] += len(CAMERA_IDS)

                    moved = env.typed_state.view
                    moved_hand = _frame_pose(moved, "panda-main", "hand")
                    displacement = float(np.linalg.norm(
                        np.asarray(moved_hand.position) - np.asarray(initial_hand.position),
                    ))
                    if displacement < 0.02:
                        raise AssertionError(f"Position target produced only {displacement:g} m hand motion")
                    round_moved[round_index] = {
                        "hand": moved_hand,
                        "observation": env.obs,
                        "boundary": boundary_rows[-1],
                        "capture_indices": list(boundary_rows[-1]["capture_rows"]),
                        "displacement_m": displacement,
                    }

                    if round_index == 0:
                        for camera_id in CAMERA_IDS:
                            first_idx = round_initial[0]["capture_indices"][CAMERA_IDS.index(camera_id)]
                            moved_idx = round_moved[0]["capture_indices"][CAMERA_IDS.index(camera_id)]
                            first_row, moved_row = capture_rows[first_idx], capture_rows[moved_idx]
                            changed = int(np.count_nonzero(
                                np.max(np.abs(moved_row["rgb"] - first_row["rgb"]), axis=2)
                                > PIXEL_DELTA_THRESHOLD,
                            ))
                            depth_changed = int(np.count_nonzero(moved_row["depth"] != first_row["depth"]))
                            mask_changed = int(np.count_nonzero(moved_row["mask"] != first_row["mask"]))
                            if changed < MIN_CHANGED_PIXELS:
                                raise AssertionError(f"{camera_id} RGB changed only {changed} pixels")
                            fixed_meta = first_row["calibration"]
                            moved_meta = moved_row["calibration"]
                            if camera_id == FIXED_CAMERA_ID:
                                extrinsic_motion = float(np.max(np.abs(
                                    np.asarray(fixed_meta["T_world_from_camera"])
                                    - np.asarray(moved_meta["T_world_from_camera"]),
                                )))
                                if extrinsic_motion > 1.0e-9:
                                    raise AssertionError("fixed world camera extrinsics changed after hand motion")
                            else:
                                extrinsic_motion = float(np.linalg.norm(
                                    np.asarray(fixed_meta["T_world_from_camera"])[:3, 3]
                                    - np.asarray(moved_meta["T_world_from_camera"])[:3, 3],
                                ))
                                if extrinsic_motion < 0.02:
                                    raise AssertionError("hand-mounted camera extrinsics did not follow the hand Frame")
                            geometry_results.append({
                                "round_index": 0,
                                "camera_id": camera_id,
                                "rgb_changed_pixels_gt_1_over_255": changed,
                                "depth_changed_pixels": depth_changed,
                                "mask_changed_pixels": mask_changed,
                                "extrinsic_change_metric": extrinsic_motion,
                            })

                if counters["reset_attempts"] != 2 or counters["outer_steps"] != 24:
                    raise AssertionError("R04b successful native route must use two resets and 24 outer steps")
                if counters["physics_substeps"] != 120 or abs(counters["simulation_seconds"] - 0.24) > 2e-9:
                    raise AssertionError("R04b successful native route must integrate exactly 120×2 ms")
                if len(set(counters["materialization_ids"])) != 2:
                    raise AssertionError("the two reset rounds did not create distinct provider materializations")
                if counters["controller_compute_calls"] != 24:
                    raise AssertionError("the existing Position Controller must compute once per public interval")
                if counters["renderer_capture_calls"] != 52 or counters["public_boundary_captures"] != 52:
                    raise AssertionError("normal public camera capture count must be 52")

                # Independently validate the D04 RGB-D geometry samples for both cameras.
                for round_index, step_index in ((0, 0), (0, 12), (1, 0)):
                    boundary = next(
                        row for row in boundary_rows
                        if row["round_index"] == round_index and row["boundary_index"] == step_index
                    )
                    state_pose = boundary["peg_frame"]
                    from task_env.artifacts import PoseWorld
                    typed_peg = PoseWorld(tuple(state_pose["position"]), tuple(state_pose["quaternion_wxyz"]))
                    for row_index in boundary["capture_rows"]:
                        row = capture_rows[row_index]
                        from task_env.observations.canonical_camera.contracts import ResolvedCameraMetadata
                        metadata = ResolvedCameraMetadata.from_mapping(row["calibration"])
                        geometry_results.append({
                            "round_index": round_index,
                            "boundary_index": step_index,
                            "camera_id": row["camera_id"],
                            "depth_oracle": _verify_depth_sample(metadata, row["depth"], typed_peg),
                        })

                # Fresh reset identities, repeatable state and images.
                first_reset = round_initial[0]
                second_reset = round_initial[1]
                first_boundary = first_reset["boundary"]["state_boundary"]
                second_boundary = second_reset["boundary"]["state_boundary"]
                for key in ("episode_id", "scene_instance_id", "provider_materialization_id", "boundary_id"):
                    if first_boundary[key] == second_boundary[key]:
                        raise AssertionError(f"reset did not refresh state identity field {key}")
                if first_boundary["reset_sample_id"] != second_boundary["reset_sample_id"]:
                    raise AssertionError("second reset did not reuse the same fixed ResetPlan sample")
                for camera_id in CAMERA_IDS:
                    index = CAMERA_IDS.index(camera_id)
                    left = capture_rows[first_reset["capture_indices"][index]]
                    right = capture_rows[second_reset["capture_indices"][index]]
                    if not np.array_equal(left["rgb"], right["rgb"]):
                        raise AssertionError(f"same ResetPlan {camera_id} RGB did not repeat exactly")
                    if not np.array_equal(left["depth"], right["depth"]):
                        raise AssertionError(f"same ResetPlan {camera_id} depth did not repeat exactly")
                    if not np.array_equal(left["mask"], right["mask"]):
                        raise AssertionError(f"same ResetPlan {camera_id} Entity mask did not repeat exactly")

                # Closing the fixed session leaves the independent mounted session readable at that boundary.
                phase = "camera_consumer_isolation"
                context["capture_kind"] = "isolation"
                fixed_session, hand_session = env._camera_consumer._sessions
                isolation_state = env.typed_state.view
                fixed_session.close()
                isolation_capture = hand_session.capture(isolation_state)
                if (isolation_capture.capture_identity.state_boundary != isolation_state.boundary
                        or isolation_capture.capture_identity.sample_clock != isolation_state.sample_clock):
                    raise AssertionError("remaining mounted consumer could not read the same typed publication")
                context["capture_kind"] = "public"
                if counters["renderer_capture_calls"] != 53 or counters["isolation_capture_calls"] != 1:
                    raise AssertionError("isolation capture was not separately counted exactly once")
                if counters["mj_step_during_capture"] or counters["mj_forward_during_capture"]:
                    raise AssertionError("dynamic camera capture advanced MuJoCo physics or called mj_forward")

                env.close()
                env_close_calls += 1
                if not env._closed:
                    raise AssertionError("Environment did not report closed after its sole close call")
                if counters["native_renderer_close_calls"] != 4:
                    raise AssertionError(
                        f"expected one native Renderer close per created session, got {counters['native_renderer_close_calls']}"
                    )
                if counters["renderer_render_calls"] != 159:
                    raise AssertionError(f"expected 159 real RGB/depth/mask renderer calls, got {counters['renderer_render_calls']}")
                if counters["provider_interval_step_calls"] != 24:
                    raise AssertionError("RuntimeSession.step was not called exactly once per public interval")
                phase = "closed_success"
            except BaseException:
                raise

    except BaseException as error:
        primary_error = {
            "type": type(error).__name__,
            "message": str(error),
            "phase": phase,
            "traceback": traceback.format_exc(),
        }
    finally:
        if env is not None and not getattr(env, "_closed", False):
            try:
                close_wrapper = locals().get("wrapped_renderer_close")
                mujoco_module = locals().get("mujoco")
                if close_wrapper is not None and mujoco_module is not None:
                    patch_object = importlib.import_module("unittest.mock").patch.object
                    with patch_object(mujoco_module.Renderer, "close", close_wrapper):
                        env.close()
                else:
                    env.close()
                env_close_calls += 1
            except BaseException as error:
                cleanup_error = {
                    "type": type(error).__name__, "message": str(error),
                    "traceback": traceback.format_exc(),
                }
        if env is not None and getattr(env, "_closed", False) and env_close_calls == 0:
            # The successful path closed inside the try block.
            env_close_calls = 1
        if env is not None and getattr(env, "_closed", False):
            expected_session_closes = len(sessions)
            expected_renderer_closes = len(renderer_ids)
            sessions_closed = all(getattr(session, "_closed", False) for session in sessions)
            if (not sessions_closed
                    or counters["session_close_calls"] < expected_session_closes
                    or counters["native_renderer_close_calls"] != expected_renderer_closes):
                cleanup_error = cleanup_error or {
                    "type": "AssertionError",
                    "message": (
                        "Environment closed without one DynamicCameraSession and native Renderer close "
                        f"per created session (sessions={expected_session_closes}, "
                        f"session_closes={counters['session_close_calls']}, "
                        f"renderers={expected_renderer_closes}, "
                        f"renderer_closes={counters['native_renderer_close_calls']})"
                    ),
                    "traceback": "",
                }

        arrays_path = output / "raw_camera_arrays.npz"
        try:
            temporary = arrays_path.with_name(arrays_path.name + ".tmp")
            with temporary.open("wb") as stream:
                np.savez(stream, **arrays)
            os.replace(temporary, arrays_path)
        except BaseException as error:
            if cleanup_error is None:
                cleanup_error = {"type": type(error).__name__, "message": f"array finalization: {error}",
                                 "traceback": traceback.format_exc()}
        try:
            for row in capture_rows:
                _append_jsonl(output / "capture_rows.jsonl", {
                    key: value for key, value in row.items() if key not in {"rgb", "depth", "mask"}
                })
            for row in boundary_rows:
                _append_jsonl(output / "boundary_rows.jsonl", row)
            for row in cache_rows:
                _append_jsonl(output / "cache_probes.jsonl", row)
            for row in control_rows:
                _append_jsonl(output / "control_rows.jsonl", row)
        except BaseException as error:
            if cleanup_error is None:
                cleanup_error = {"type": type(error).__name__, "message": f"JSONL finalization: {error}",
                                 "traceback": traceback.format_exc()}

    passed = primary_error is None and cleanup_error is None and env is not None and getattr(env, "_closed", False)
    receipt = {
        "schema_version": "r04b-public-camera-s2-worker-v1",
        "status": "R04B_PUBLIC_ENV_TWO_CAMERA_S2_PASS" if passed else "R04B_PUBLIC_ENV_TWO_CAMERA_S2_FAIL",
        "scope": "one make_env panda-position-servo-candidate-v1 Env; two reset(seed=31) rounds; 12 public Position steps each; fixed and hand D04 RGB/depth/Entity mask",
        "input_head": "b0b26e95ddfd7b5128401261f05541bb19586372",
        "runtime": runtime,
        "camera_config_preflight": config_evidence,
        "counters": counters,
        "env_close_calls": env_close_calls,
        "closed_before_receipt": bool(env is not None and getattr(env, "_closed", False)),
        "normal_capture_calls_expected": 52,
        "isolation_capture_calls": counters["isolation_capture_calls"],
        "geometry_oracles": geometry_results,
        "action_trajectories": action_trajectories,
        "graphics_contexts": graphics,
        "native_worker_elapsed_s": __import__("time").monotonic() - start_time,
        "primary_error": primary_error,
        "cleanup_error": cleanup_error,
        "evidence": {
            "arrays": str(output / "raw_camera_arrays.npz"),
            "capture_rows": str(output / "capture_rows.jsonl"),
            "boundary_rows": str(output / "boundary_rows.jsonl"),
            "cache_probes": str(output / "cache_probes.jsonl"),
            "control_rows": str(output / "control_rows.jsonl"),
        },
    }
    if (output / "raw_camera_arrays.npz").exists():
        receipt["evidence"]["raw_camera_arrays_sha256"] = _sha256(output / "raw_camera_arrays.npz")
    for key in ("capture_rows", "boundary_rows", "cache_probes", "control_rows"):
        path = Path(receipt["evidence"][key])
        if path.exists():
            receipt["evidence"][key + "_sha256"] = _sha256(path)
    _write_json(output / "worker_receipt.json", receipt)
    if not passed:
        raise RuntimeError(f"R04b native worker failed in phase {phase}: {primary_error or cleanup_error}")
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = run_s2(args.output)
    except BaseException as error:
        print(json.dumps({"status": "FAIL", "error": f"{type(error).__name__}: {error}"}, sort_keys=True))
        return 1
    print(json.dumps({"status": receipt["status"], "worker_receipt": str(args.output / "worker_receipt.json")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
