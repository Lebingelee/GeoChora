"""Bounded real D04 RGB/optical-Z fixed and hand-mounted camera probe."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from task_env.artifacts import ExecutionSpecV1, RendererSelectionV1
from task_env.diagnostics.tasks.c02b_position_candidate import build_position_candidate
from task_env.diagnostics.tasks.c02b_position_s2_probe import _request, _typed_hand_and_joints
from task_env.objects.nut_assembly import PEG_HALF_HEIGHT, SQUARE_PEG_HALF_WIDTH
from task_env.observations.canonical_camera import (
    CameraGeometry,
    MOUNT_FROM_CAMERA,
    back_project_world,
    project_world,
)
from task_env.render.camera import (
    D03_DYNAMIC_PROFILE,
    D03_PHYSICS_PROFILE,
    D04_DYNAMIC_PROFILE,
    DynamicCameraRenderSourceV1,
    create_dynamic_camera_session,
    dynamic_render_manifest,
    dynamic_rgbd_render_manifest,
)
from task_env.utils.rotation import quat_wxyz_to_matrix


CONTROL_INTERVALS = 12
HAND_TARGET_DELTA_M = 0.08
CAMERA_WIDTH = 321
CAMERA_HEIGHT = 241
CAMERA_FOV_Y = math.radians(90.0)
CAMERA_NEAR_M = 0.01
CAMERA_FAR_M = 3.0
PIXEL_DELTA_THRESHOLD = 1.0 / 255.0
MIN_CHANGED_PIXELS = 8
FRAME_POSITION_ATOL_M = 5.0e-4
FRAME_QUATERNION_SIGN_INVARIANT_L2_ATOL = 1.0e-3
LANDMARK_DEPTH_ATOL_M = 2.0e-3
BACKPROJECTION_ATOL_M = 3.0e-3
NATIVE_CLOCK_ATOL_S = 1.0e-9


def _tuple_matrix(value):
    return tuple(tuple(float(entry) for entry in row) for row in np.asarray(value))


def _pose_matrix(pose):
    result = np.eye(4, dtype=np.float64)
    result[:3, :3] = quat_wxyz_to_matrix(pose.quaternion_wxyz)
    result[:3, 3] = pose.position
    return result


def _frame_pose(state, entity_id, frame_id):
    matches = [
        item.pose_world for item in state.frames
        if (item.frame.entity_id, item.frame.frame_id) == (entity_id, frame_id)
    ]
    if len(matches) != 1:
        raise ValueError(f'expected exactly one Canonical Frame {entity_id}/{frame_id}')
    return matches[0]


def _world_from_optical_camera(position, target):
    position = np.asarray(position, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    forward = target - position
    norm = float(np.linalg.norm(forward))
    if not math.isfinite(norm) or norm <= 1.0e-9:
        raise ValueError('camera target must differ from camera position')
    forward /= norm
    world_up = np.asarray((0.0, 0.0, 1.0), dtype=np.float64)
    if abs(float(np.dot(forward, world_up))) > 0.98:
        world_up = np.asarray((0.0, 1.0, 0.0), dtype=np.float64)
    right = np.cross(forward, world_up)
    right /= np.linalg.norm(right)
    down = np.cross(forward, right)
    transform = np.eye(4, dtype=np.float64)
    # Canonical optical coordinates: +X right, +Y down, +Z forward.
    transform[:3, :3] = np.column_stack((right, down, forward))
    transform[:3, 3] = position
    return transform


def _camera_geometry(candidate, camera_id, parent_frame, T_parent_from_mount):
    return CameraGeometry(
        schema_version='camera-observation-v0',
        task_artifact_hash=candidate.artifact.identity_hash,
        camera_id=camera_id,
        parent_frame=parent_frame,
        T_parent_from_mount=_tuple_matrix(T_parent_from_mount),
        T_mount_from_camera=MOUNT_FROM_CAMERA,
        width=CAMERA_WIDTH,
        height=CAMERA_HEIGHT,
        fov_y=CAMERA_FOV_Y,
        near=CAMERA_NEAR_M,
        far=CAMERA_FAR_M,
        rgb=True,
        depth=True,
        rgb_layout='HWC',
        rgb_dtype='float32',
        pixel_convention='image_edges_pixel_centers_half',
        depth_convention='optical_z_m_float32',
        capture_phase='post_control_step',
    )


def fixed_calibration_camera(candidate, state):
    """Aim a version-identified diagnostic camera at the known square peg."""

    peg = _frame_pose(state, 'square-peg-instance', 'peg1')
    center = np.asarray(peg.position, dtype=np.float64)
    # This view includes the robot and the known peg while keeping the
    # calibration landmark on the principal ray.
    optical = _world_from_optical_camera(center + (0.0, -1.5, 0.0), center)
    world_from_mount = optical @ np.linalg.inv(np.asarray(MOUNT_FROM_CAMERA, dtype=np.float64))
    return _camera_geometry(
        candidate, 'd04-fixed-square-peg-calibration-v1', 'world', world_from_mount,
    )


def mounted_hand_camera(candidate, state):
    """Place an optical camera on a calibrated hand mount and aim at the peg."""

    hand = _frame_pose(state, 'panda-main', 'hand')
    peg = _frame_pose(state, 'square-peg-instance', 'peg1')
    world_from_hand = _pose_matrix(hand)
    optical_position = world_from_hand[:3, 3] + world_from_hand[:3, :3] @ np.asarray((0.0, 0.0, 0.035))
    optical = _world_from_optical_camera(optical_position, peg.position)
    world_from_mount = optical @ np.linalg.inv(np.asarray(MOUNT_FROM_CAMERA, dtype=np.float64))
    parent_from_mount = np.linalg.inv(world_from_hand) @ world_from_mount
    return _camera_geometry(
        candidate, 'd04-panda-hand-mounted-camera-v1', 'hand', parent_from_mount,
    )


def d04_execution(camera_id='d04-fixed-square-peg-calibration-v1'):
    renderer = RendererSelectionV1(
        'renderer-selection-v1', 'mujoco', 'native-opengl', D04_DYNAMIC_PROFILE, None,
    )
    return ExecutionSpecV1(
        'execution-spec-v1', 'geophys', 'cpu', D03_PHYSICS_PROFILE,
        32, 'best_effort', renderer, physics_device='cpu:0',
    )


def d03_execution(camera_id='d04-fixed-square-peg-calibration-v1'):
    renderer = RendererSelectionV1(
        'renderer-selection-v1', 'mujoco', 'native-opengl', D03_DYNAMIC_PROFILE, None,
    )
    return ExecutionSpecV1(
        'execution-spec-v1', 'geophys', 'cpu', D03_PHYSICS_PROFILE,
        31, 'best_effort', renderer, physics_device='cpu:0',
    )


def _save_rgb(path: Path, image: np.ndarray) -> None:
    Image.fromarray((np.clip(image, 0.0, 1.0) * 255.0).astype(np.uint8)).save(path)


def _ray_box_hit(metadata, peg_pose, row, col):
    """Independent pinhole ray/AABB oracle for the known square-peg box."""

    K = np.asarray(metadata.K, dtype=np.float64)
    pixel = np.asarray(((col + 0.5, row + 0.5, 1.0),), dtype=np.float64)
    ray_camera = pixel @ np.linalg.inv(K).T
    world_from_camera = np.asarray(metadata.T_world_from_camera, dtype=np.float64)
    ray_world = ray_camera[0] @ world_from_camera[:3, :3].T
    origin_world = world_from_camera[:3, 3]
    box_from_world = quat_wxyz_to_matrix(peg_pose.quaternion_wxyz).T
    ray_box = box_from_world @ ray_world
    origin_box = box_from_world @ (origin_world - np.asarray(peg_pose.position, dtype=np.float64))
    half_extent = np.asarray((SQUARE_PEG_HALF_WIDTH, SQUARE_PEG_HALF_WIDTH, PEG_HALF_HEIGHT))
    near, far = -math.inf, math.inf
    for axis in range(3):
        if abs(float(ray_box[axis])) <= 1.0e-12:
            if abs(float(origin_box[axis])) > half_extent[axis]:
                raise ValueError('projected peg landmark ray misses the known box')
            continue
        first = (-half_extent[axis] - origin_box[axis]) / ray_box[axis]
        second = (half_extent[axis] - origin_box[axis]) / ray_box[axis]
        near = max(near, min(float(first), float(second)))
        far = min(far, max(float(first), float(second)))
    if near < 0 or far < near:
        raise ValueError('known box is not in front of the calibration camera ray')
    hit_box = origin_box + near * ray_box
    hit_world = np.asarray(peg_pose.position, dtype=np.float64) + quat_wxyz_to_matrix(peg_pose.quaternion_wxyz) @ hit_box
    # ray_camera.z is one, so the ray parameter is optical-Z in metres.
    return float(near), hit_world


def _verify_peg_depth(camera_observation, peg_pose):
    metadata = camera_observation.metadata
    center_pixel = project_world(metadata, np.asarray((peg_pose.position,), dtype=np.float64))[0]
    col = int(round(float(center_pixel[0]) - 0.5))
    row = int(round(float(center_pixel[1]) - 0.5))
    if not (0 <= row < metadata.camera.height and 0 <= col < metadata.camera.width):
        raise AssertionError('known square-peg landmark projects outside the camera image')
    expected_depth, expected_hit = _ray_box_hit(metadata, peg_pose, row, col)
    observed_depth = float(camera_observation.depth[row, col])
    if observed_depth <= 0 or abs(observed_depth - expected_depth) > LANDMARK_DEPTH_ATOL_M:
        raise AssertionError(
            f'known square-peg optical-Z mismatch at {(row, col)}: '
            f'observed={observed_depth:g} m expected={expected_depth:g} m'
        )
    observed_hit = back_project_world(metadata, np.asarray(((col + 0.5, row + 0.5),)), np.asarray((observed_depth,)))[0]
    error = float(np.linalg.norm(observed_hit - expected_hit))
    if error > BACKPROJECTION_ATOL_M:
        raise AssertionError(f'camera depth back-projection misses known peg face by {error:g} m')
    return {
        'landmark_world_m': tuple(float(value) for value in peg_pose.position),
        'projected_pixel_edge_coordinates': tuple(float(value) for value in center_pixel),
        'sample_pixel_row_col': (row, col),
        'known_box_half_extents_m': (SQUARE_PEG_HALF_WIDTH, SQUARE_PEG_HALF_WIDTH, PEG_HALF_HEIGHT),
        'analytic_front_surface_optical_z_m': expected_depth,
        'measured_optical_z_m': observed_depth,
        'expected_surface_world_m': tuple(float(value) for value in expected_hit),
        'backprojected_surface_world_m': tuple(float(value) for value in observed_hit),
        'backprojection_error_m': error,
    }


def _camera_pose_error(camera, state, metadata):
    if camera.parent_frame == 'world':
        parent = np.eye(4, dtype=np.float64)
    else:
        parent_frame = _frame_pose(state, 'panda-main', camera.parent_frame)
        parent = _pose_matrix(parent_frame)
    expected = (
        parent
        @ np.asarray(camera.T_parent_from_mount, dtype=np.float64)
        @ np.asarray(camera.T_mount_from_camera, dtype=np.float64)
    )
    return float(np.max(np.abs(expected - np.asarray(metadata.T_world_from_camera))))


def _assert_observation(camera, state, observation, expected_manifest_profile):
    if observation.rgb.shape != (camera.height, camera.width, 3) or observation.rgb.dtype != np.float32:
        raise AssertionError('D04 RGB output did not preserve the declared HWC float32[0,1] contract')
    if observation.depth.shape != (camera.height, camera.width) or observation.depth.dtype != np.float32:
        raise AssertionError('D04 depth output did not preserve the H×W float32 contract')
    if not (np.isfinite(observation.rgb).all() and np.isfinite(observation.depth).all()):
        raise AssertionError('D04 capture returned non-finite image values')
    if np.any(observation.depth < 0) or not np.any(observation.depth == 0):
        raise AssertionError('D04 depth must use finite nonnegative metres and zero for invalid/background')
    identity = observation.capture_identity
    if identity is None:
        raise AssertionError('D04 observation lacks its completed capture identity')
    if identity.state_boundary.boundary_id != state.boundary.boundary_id or identity.sample_clock != state.sample_clock:
        raise AssertionError('camera observation/capture identity came from another publication')
    if set(identity.modalities) != {'depth', 'rgb'}:
        raise AssertionError('RGB/Depth capture identity modality list is incomplete')
    if identity.renderer_selection.profile != expected_manifest_profile:
        raise AssertionError('camera observation capture identity names another renderer profile')
    if observation.metadata.capture_control_step != state.boundary.control_step:
        raise AssertionError('camera metadata control step differs from the sampled state')
    if observation.metadata.capture_simulation_time != state.sample_clock.simulation_time_s:
        raise AssertionError('camera metadata simulation time differs from the sampled state')
    pose_error = _camera_pose_error(camera, state, observation.metadata)
    if pose_error > 1.0e-9:
        raise AssertionError(f'camera metadata pose differs from the declared Frame/mount transform by {pose_error:g}')
    return pose_error


def run_s2(output: Path | str) -> dict[str, object]:
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    candidate = build_position_candidate(output / 'source-closure', provider='geophys', horizon=CONTROL_INTERVALS)
    env = candidate.env
    sessions = []
    try:
        env.reset()
        source = DynamicCameraRenderSourceV1.from_runtime_source(candidate.source)
        initial_state = env.typed_state.view
        fixed_camera = fixed_calibration_camera(candidate, initial_state)
        mounted_camera = mounted_hand_camera(candidate, initial_state)
        fixed_session = create_dynamic_camera_session(
            fixed_camera, d04_execution(fixed_camera.camera_id), source=source,
            initial_state=initial_state, manifest=dynamic_rgbd_render_manifest(),
        )
        mounted_session = create_dynamic_camera_session(
            mounted_camera, d04_execution(mounted_camera.camera_id), source=source,
            initial_state=initial_state, manifest=dynamic_rgbd_render_manifest(),
        )
        sessions.extend((fixed_session, mounted_session))

        counters = {
            'controller_compute_during_capture': 0,
            'provider_step_during_capture': 0,
            'mujoco_mj_step_during_capture': 0,
            'mujoco_mj_forward_during_capture': 0,
            'provider_outer_step_calls': 0,
        }
        capture_phase = {'active': False}
        controller_type, session_type = type(env.controller), type(env.session)
        original_compute, original_step = controller_type.compute, session_type.step

        def counted_compute(controller, *args, **kwargs):
            if controller is env.controller and capture_phase['active']:
                counters['controller_compute_during_capture'] += 1
            return original_compute(controller, *args, **kwargs)

        def counted_step(session, *args, **kwargs):
            if session is env.session:
                if capture_phase['active']:
                    counters['provider_step_during_capture'] += 1
                else:
                    counters['provider_outer_step_calls'] += 1
            return original_step(session, *args, **kwargs)

        import mujoco
        original_mj_step, original_mj_forward = mujoco.mj_step, mujoco.mj_forward

        def counted_mj_step(*args, **kwargs):
            if capture_phase['active']:
                counters['mujoco_mj_step_during_capture'] += 1
            return original_mj_step(*args, **kwargs)

        def counted_mj_forward(*args, **kwargs):
            if capture_phase['active']:
                counters['mujoco_mj_forward_during_capture'] += 1
            return original_mj_forward(*args, **kwargs)

        patchers = (
            patch.object(controller_type, 'compute', counted_compute),
            patch.object(session_type, 'step', counted_step),
            patch.object(mujoco, 'mj_step', counted_mj_step),
            patch.object(mujoco, 'mj_forward', counted_mj_forward),
        )
        with patchers[0], patchers[1], patchers[2], patchers[3]:
            capture_phase['active'] = True
            clock_before = (int(env.state.control_step), float(env.state.simulation_time))
            fixed_initial = fixed_session.capture(initial_state)
            fixed_device = fixed_session.graphics_device_info()
            mounted_initial = mounted_session.capture(initial_state)
            mounted_device = mounted_session.graphics_device_info()
            clock_after_initial_capture = (int(env.state.control_step), float(env.state.simulation_time))
            capture_phase['active'] = False
            if clock_before != clock_after_initial_capture:
                raise AssertionError('initial camera capture advanced the GeoPhys public clock')

        fixed_initial_pose_error = _assert_observation(
            fixed_camera, initial_state, fixed_initial, D04_DYNAMIC_PROFILE,
        )
        mounted_initial_pose_error = _assert_observation(
            mounted_camera, initial_state, mounted_initial, D04_DYNAMIC_PROFILE,
        )
        initial_peg = _frame_pose(initial_state, 'square-peg-instance', 'peg1')
        fixed_calibration = _verify_peg_depth(fixed_initial, initial_peg)
        mounted_calibration = _verify_peg_depth(mounted_initial, initial_peg)
        # The odd-sized image puts the principal point on one pixel center.
        fixed_projected = np.asarray(fixed_calibration['projected_pixel_edge_coordinates'])
        if not np.allclose(fixed_projected, (CAMERA_WIDTH / 2, CAMERA_HEIGHT / 2), atol=1.0e-8, rtol=0):
            raise AssertionError('fixed calibration landmark is not at the analytic principal point')

        for name, value in (
            ('fixed_initial', fixed_initial.rgb), ('mounted_initial', mounted_initial.rgb),
        ):
            _save_rgb(output / f'{name}.png', value)
        np.save(output / 'fixed_initial_depth.npy', fixed_initial.depth)
        np.save(output / 'mounted_initial_depth.npy', mounted_initial.depth)

        initial_hand = _frame_pose(initial_state, 'panda-main', 'hand')
        hand_target = type(initial_hand)(
            (initial_hand.position[0] + HAND_TARGET_DELTA_M, *initial_hand.position[1:]),
            initial_hand.quaternion_wxyz,
        )
        action = _request(candidate.controller_binding_plan, hand_target, 1.0)
        physics_dt = float(candidate.artifact.timebase.physics_dt)
        control_dt = float(candidate.artifact.timebase.control_dt)
        requested_native_steps = int(candidate.artifact.timebase.control_substeps)
        completed_rows = []
        with patch.object(session_type, 'step', counted_step):
            for _ in range(CONTROL_INTERVALS):
                before = env.state
                env.step(action)
                after = env.state
                elapsed = float(after.simulation_time - before.simulation_time)
                completed = int(round(elapsed / physics_dt))
                if (
                    after.control_step != before.control_step + 1
                    or completed != requested_native_steps
                    or abs(elapsed - control_dt) > NATIVE_CLOCK_ATOL_S
                ):
                    raise AssertionError('Position candidate did not complete five native 2 ms steps per 10 ms interval')
                completed_rows.append({
                    'control_step': int(after.control_step),
                    'simulation_time_s': float(after.simulation_time),
                    'native_step_delta_inferred_from_public_clock': completed,
                    'elapsed_s': elapsed,
                })

        moved_state = env.typed_state.view
        moved_hand = _frame_pose(moved_state, 'panda-main', 'hand')
        hand_displacement = float(np.linalg.norm(
            np.asarray(moved_hand.position) - np.asarray(initial_hand.position),
        ))
        capture_clock_before = (int(env.state.control_step), float(env.state.simulation_time))
        with patchers[0], patchers[1], patchers[2], patchers[3]:
            capture_phase['active'] = True
            fixed_moved = fixed_session.capture(moved_state)
            fixed_moved_device = fixed_session.graphics_device_info()
            mounted_moved = mounted_session.capture(moved_state)
            mounted_moved_device = mounted_session.graphics_device_info()
            capture_phase['active'] = False
        capture_clock_after = (int(env.state.control_step), float(env.state.simulation_time))
        if capture_clock_before != capture_clock_after:
            raise AssertionError('post-motion camera capture advanced the GeoPhys public clock')
        fixed_moved_pose_error = _assert_observation(
            fixed_camera, moved_state, fixed_moved, D04_DYNAMIC_PROFILE,
        )
        mounted_moved_pose_error = _assert_observation(
            mounted_camera, moved_state, mounted_moved, D04_DYNAMIC_PROFILE,
        )

        fixed_changed_pixels = int(np.count_nonzero(
            np.max(np.abs(fixed_moved.rgb - fixed_initial.rgb), axis=2) > PIXEL_DELTA_THRESHOLD,
        ))
        mounted_changed_pixels = int(np.count_nonzero(
            np.max(np.abs(mounted_moved.rgb - mounted_initial.rgb), axis=2) > PIXEL_DELTA_THRESHOLD,
        ))
        fixed_changed_depth = int(np.count_nonzero(fixed_moved.depth != fixed_initial.depth))
        mounted_changed_depth = int(np.count_nonzero(mounted_moved.depth != mounted_initial.depth))
        if hand_displacement < 0.02 or fixed_changed_pixels < MIN_CHANGED_PIXELS or mounted_changed_pixels < MIN_CHANGED_PIXELS:
            raise AssertionError(
                'real Position motion was not visible in both D04 cameras: '
                f'hand={hand_displacement:g} m fixed_pixels={fixed_changed_pixels} '
                f'mounted_pixels={mounted_changed_pixels}'
            )
        if fixed_changed_depth < MIN_CHANGED_PIXELS or mounted_changed_depth < MIN_CHANGED_PIXELS:
            raise AssertionError(
                f'depth did not reflect the same real motion: fixed={fixed_changed_depth} mounted={mounted_changed_depth}'
            )

        moved_peg = _frame_pose(moved_state, 'square-peg-instance', 'peg1')
        fixed_moved_calibration = _verify_peg_depth(fixed_moved, moved_peg)
        mounted_moved_calibration = _verify_peg_depth(mounted_moved, moved_peg)
        initial_mounted_pose = np.asarray(mounted_initial.metadata.T_world_from_camera)
        moved_mounted_pose = np.asarray(mounted_moved.metadata.T_world_from_camera)
        initial_fixed_pose = np.asarray(fixed_initial.metadata.T_world_from_camera)
        moved_fixed_pose = np.asarray(fixed_moved.metadata.T_world_from_camera)
        if np.max(np.abs(initial_fixed_pose - moved_fixed_pose)) > 1.0e-9:
            raise AssertionError('fixed world camera extrinsic changed across Position motion')
        mounted_camera_translation = float(np.linalg.norm(
            moved_mounted_pose[:3, 3] - initial_mounted_pose[:3, 3],
        ))
        if mounted_camera_translation < 0.02:
            raise AssertionError('hand-mounted camera extrinsic did not follow its parent Frame motion')
        if (
            fixed_moved.capture_identity.state_boundary.boundary_id
            != mounted_moved.capture_identity.state_boundary.boundary_id
        ):
            raise AssertionError('fixed and mounted captures did not consume the same physical publication')

        _save_rgb(output / 'fixed_moved.png', fixed_moved.rgb)
        _save_rgb(output / 'mounted_moved.png', mounted_moved.rgb)
        np.save(output / 'fixed_moved_depth.npy', fixed_moved.depth)
        np.save(output / 'mounted_moved_depth.npy', mounted_moved.depth)

        moved_boundary_id = moved_state.boundary.boundary_id
        env.reset()
        reset_state = env.typed_state.view
        capture_clock_before_reset_capture = (int(env.state.control_step), float(env.state.simulation_time))
        with patchers[0], patchers[1], patchers[2], patchers[3]:
            capture_phase['active'] = True
            fixed_reset = fixed_session.capture(reset_state)
            fixed_reset_device = fixed_session.graphics_device_info()
            mounted_reset = mounted_session.capture(reset_state)
            mounted_reset_device = mounted_session.graphics_device_info()
            capture_phase['active'] = False
        capture_clock_after_reset_capture = (int(env.state.control_step), float(env.state.simulation_time))
        if capture_clock_before_reset_capture != capture_clock_after_reset_capture:
            raise AssertionError('reset camera capture advanced the GeoPhys public clock')
        if fixed_reset.capture_identity.state_boundary.boundary_id == moved_boundary_id:
            raise AssertionError('fixed camera returned a previous-episode capture identity after reset')
        if mounted_reset.capture_identity.state_boundary.boundary_id == moved_boundary_id:
            raise AssertionError('mounted camera returned a previous-episode capture identity after reset')
        if not np.array_equal(fixed_reset.rgb, fixed_initial.rgb) or not np.array_equal(mounted_reset.rgb, mounted_initial.rgb):
            raise AssertionError('same fixed reset sample did not reproduce its reset camera images')
        if not np.array_equal(fixed_reset.depth, fixed_initial.depth) or not np.array_equal(mounted_reset.depth, mounted_initial.depth):
            raise AssertionError('same fixed reset sample did not reproduce its reset camera depth')
        if not np.allclose(
            np.asarray(fixed_reset.metadata.T_world_from_camera), initial_fixed_pose, atol=1.0e-9, rtol=0,
        ):
            raise AssertionError('fixed camera pose retained an old episode transform after reset')
        if not np.allclose(
            np.asarray(mounted_reset.metadata.T_world_from_camera), initial_mounted_pose, atol=1.0e-9, rtol=0,
        ):
            raise AssertionError('mounted camera pose retained an old episode transform after reset')
        for session, old_state in ((fixed_session, moved_state), (mounted_session, moved_state)):
            try:
                session.capture(old_state)
            except ValueError as exc:
                if 'previous episode' not in str(exc):
                    raise
            else:
                raise AssertionError('camera session accepted an older episode publication after reset')

        all_devices = (fixed_device, mounted_device, fixed_moved_device, mounted_moved_device, fixed_reset_device, mounted_reset_device)
        if not all(device['renderer'] and device['vendor'] and device['version'] for device in all_devices):
            raise AssertionError('native OpenGL current-context query did not return actual device strings')
        if counters['provider_outer_step_calls'] != CONTROL_INTERVALS:
            raise AssertionError('outer Provider step API call count differs from requested intervals')
        if any(counters[name] for name in (
            'controller_compute_during_capture', 'provider_step_during_capture',
            'mujoco_mj_step_during_capture', 'mujoco_mj_forward_during_capture',
        )):
            raise AssertionError(f'capture advanced physics or Controller: {counters}')

        for name, value in (
            ('fixed_reset', fixed_reset.rgb), ('mounted_reset', mounted_reset.rgb),
        ):
            _save_rgb(output / f'{name}.png', value)
        np.save(output / 'fixed_reset_depth.npy', fixed_reset.depth)
        np.save(output / 'mounted_reset_depth.npy', mounted_reset.depth)

        return {
            'status': 'D04_RGBD_FIXED_MOUNTED_S2_BOUNDED_PASS',
            'scope': {
                'physics_provider': 'GeoPhys',
                'physics_backend': 'Taichi x64 CPU runtime',
                'render_provider': 'MuJoCo native OpenGL Renderer',
                'render_backend_selection': 'native-opengl',
                'render_device_observed_after_capture': fixed_moved_device,
                'device_info_limitation': 'MuJoCo exposes no public context handle; device strings were queried from the current GL context immediately after each successful capture and were not used for admission/device pinning.',
                'task_candidate': candidate.artifact.artifact_id,
                'task_artifact_hash': candidate.artifact.identity_hash,
                'controller_profile': env.controller.profile_id,
                'controller_identity': env.controller.identity,
                'scene_identity_hash': source.scene_identity_hash,
                'source_identity': source.source_identity,
                'source_closure_digest': source.source_closure_digest,
                'render_source_identity_hash': source.identity_hash,
                'fixed_camera_id': fixed_camera.camera_id,
                'fixed_camera_identity_hash': fixed_camera.identity_hash,
                'mounted_camera_id': mounted_camera.camera_id,
                'mounted_camera_identity_hash': mounted_camera.identity_hash,
                'mounted_parent_frame_resolved': 'panda-main/hand (unique Entity-qualified state Frame)',
            },
            'camera_contract': {
                'optical_frame': '+X right, +Y down, +Z forward; MuJoCo camera axes mapped from +X right, +Y up, -Z forward',
                'T_world_from_camera': 'T_world_from_parent @ T_parent_from_mount @ T_mount_from_camera',
                'pixel_convention': 'image edge coordinates; pixel centers at (column+0.5,row+0.5)',
                'projection': 'centered pinhole; K derived from width, height and vertical FOV',
                'image_size': (CAMERA_WIDTH, CAMERA_HEIGHT),
                'fov_y_rad': CAMERA_FOV_Y,
                'near_far_m': (CAMERA_NEAR_M, CAMERA_FAR_M),
                'rgb_layout_dtype_range': 'HWC float32 [0,1]',
                'depth_shape_dtype_unit': 'H×W float32 metres',
                'depth_convention': 'optical-Z along camera +Z; native MuJoCo metric view-Z is already metres',
                'depth_invalid_value': 0.0,
                'depth_invalid_rule': 'near-clipped and far/background samples map to zero; far plane is exclusive for this D04 profile',
                'native_renderer_metric_clipping_m': (
                    float(fixed_session._model.vis.map.znear * fixed_session._model.stat.extent),
                    float(fixed_session._model.vis.map.zfar * fixed_session._model.stat.extent),
                ),
                'legacy_depth_boundary': 'legacy optical_z_m and ray_distance_m normalization keeps inclusive far-plane behavior',
            },
            'known_geometry_oracle': {
                'source': 'existing A05 square-peg geometry; fixture bytes unchanged',
                'analytic_camera_projection': 'peg center projects to the fixed camera principal point',
                'depth_tolerance_m': LANDMARK_DEPTH_ATOL_M,
                'backprojection_tolerance_m': BACKPROJECTION_ATOL_M,
                'fixed_initial': fixed_calibration,
                'fixed_moved': fixed_moved_calibration,
                'mounted_initial': mounted_calibration,
                'mounted_moved': mounted_moved_calibration,
            },
            'synchronization': {
                'same_initial_boundary_id': fixed_initial.capture_identity.state_boundary.boundary_id,
                'same_moved_boundary_id': fixed_moved.capture_identity.state_boundary.boundary_id,
                'fixed_initial_capture_identity': fixed_initial.capture_identity.identity_hash,
                'fixed_moved_capture_identity': fixed_moved.capture_identity.identity_hash,
                'mounted_initial_capture_identity': mounted_initial.capture_identity.identity_hash,
                'mounted_moved_capture_identity': mounted_moved.capture_identity.identity_hash,
                'fixed_pose_error_initial_max_abs': fixed_initial_pose_error,
                'fixed_pose_error_moved_max_abs': fixed_moved_pose_error,
                'mounted_pose_error_initial_max_abs': mounted_initial_pose_error,
                'mounted_pose_error_moved_max_abs': mounted_moved_pose_error,
                'fixed_extrinsic_change_max_abs': float(np.max(np.abs(initial_fixed_pose - moved_fixed_pose))),
                'mounted_extrinsic_translation_m': mounted_camera_translation,
                'hand_displacement_m': hand_displacement,
                'fixed_rgb_changed_pixels': fixed_changed_pixels,
                'mounted_rgb_changed_pixels': mounted_changed_pixels,
                'fixed_depth_changed_pixels': fixed_changed_depth,
                'mounted_depth_changed_pixels': mounted_changed_depth,
                'fixed_reset_identity_changed': fixed_reset.capture_identity.identity_hash != fixed_moved.capture_identity.identity_hash,
                'mounted_reset_identity_changed': mounted_reset.capture_identity.identity_hash != mounted_moved.capture_identity.identity_hash,
                'reset_rgb_exactly_reproduced': bool(
                    np.array_equal(fixed_reset.rgb, fixed_initial.rgb)
                    and np.array_equal(mounted_reset.rgb, mounted_initial.rgb)
                ),
                'reset_depth_exactly_reproduced': bool(
                    np.array_equal(fixed_reset.depth, fixed_initial.depth)
                    and np.array_equal(mounted_reset.depth, mounted_initial.depth)
                ),
            },
            'timing': {
                'physics_dt_s': physics_dt,
                'outer_control_dt_s': control_dt,
                'native_steps_requested_per_interval': requested_native_steps,
                'completed_outer_intervals': len(completed_rows),
                'completed_native_steps_inferred_from_public_clock': sum(
                    row['native_step_delta_inferred_from_public_clock'] for row in completed_rows
                ),
                'provider_outer_step_api_calls': counters['provider_outer_step_calls'],
                'interval_rows': completed_rows,
                'capture_clock_before': capture_clock_before,
                'capture_clock_after': capture_clock_after,
                'capture_clock_before_reset': capture_clock_before_reset_capture,
                'capture_clock_after_reset': capture_clock_after_reset_capture,
                'capture_controller_compute_calls': counters['controller_compute_during_capture'],
                'capture_provider_step_calls': counters['provider_step_during_capture'],
                'capture_mujoco_mj_step_calls': counters['mujoco_mj_step_during_capture'],
                'capture_mujoco_mj_forward_calls': counters['mujoco_mj_forward_during_capture'],
            },
            'tolerances': {
                'frame_position_atol_m': FRAME_POSITION_ATOL_M,
                'frame_quaternion_sign_invariant_l2_atol': FRAME_QUATERNION_SIGN_INVARIANT_L2_ATOL,
                'pixel_delta_threshold': PIXEL_DELTA_THRESHOLD,
                'minimum_changed_pixels_per_camera': MIN_CHANGED_PIXELS,
                'landmark_depth_atol_m': LANDMARK_DEPTH_ATOL_M,
                'backprojection_atol_m': BACKPROJECTION_ATOL_M,
                'native_clock_atol_s': NATIVE_CLOCK_ATOL_S,
            },
            'artifacts': {
                'rgb_pngs': [
                    str(output / f'{name}.png') for name in (
                        'fixed_initial', 'mounted_initial', 'fixed_moved',
                        'mounted_moved', 'fixed_reset', 'mounted_reset',
                    )
                ],
                'depth_arrays': [
                    str(output / f'{name}.npy') for name in (
                        'fixed_initial_depth', 'mounted_initial_depth',
                        'fixed_moved_depth', 'mounted_moved_depth',
                        'fixed_reset_depth', 'mounted_reset_depth',
                    )
                ],
            },
        }
    finally:
        for session in sessions:
            session.close()
        env.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    receipt = run_s2(args.output)
    (args.output / 'd04_rgbd_s2_receipt.json').write_text(
        json.dumps(receipt, indent=2, sort_keys=True), encoding='utf-8',
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
