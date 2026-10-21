"""Real D03 GeoPhys CPU physics × MuJoCo native renderer S2 probe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from task_env.artifacts import ExecutionSpecV1, RendererSelectionV1
from task_env.controllers.canonical.position_profile import PandaPositionServoProfileV1
from task_env.diagnostics.tasks.c02b_position_candidate import build_position_candidate
from task_env.diagnostics.tasks.c02b_position_s2_probe import _request, _typed_hand_and_joints
from task_env.observations.canonical_camera import CameraGeometry
from task_env.render.camera import (
    D03_DYNAMIC_PROFILE,
    D03_PHYSICS_PROFILE,
    DynamicCameraRenderSourceV1,
    create_dynamic_camera_session,
    dynamic_render_manifest,
)


PIXEL_DELTA_THRESHOLD = 1.0 / 255.0
MIN_CHANGED_PIXELS = 8
FRAME_POSITION_ATOL_M = 5.0e-4
FRAME_QUATERNION_SIGN_INVARIANT_L2_ATOL = 1.0e-3
NATIVE_CLOCK_ATOL_S = 1.0e-9
CONTROL_INTERVALS = 12
HAND_TARGET_DELTA_M = 0.08


def _camera(candidate) -> CameraGeometry:
    position = np.asarray((1.4, -2.0, 1.3), dtype=np.float64)
    target = np.asarray((0.15, 0.0, 0.65), dtype=np.float64)
    forward = target - position
    forward /= np.linalg.norm(forward)
    world_up = np.asarray((0.0, 0.0, 1.0), dtype=np.float64)
    right = np.cross(forward, world_up)
    right /= np.linalg.norm(right)
    down = np.cross(forward, right)
    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = np.column_stack((right, down, forward))
    transform[:3, 3] = position
    identity = ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0))
    return CameraGeometry(
        'camera-observation-v0', candidate.artifact.identity_hash,
        'd03-position-fixed-world-camera', 'world',
        tuple(tuple(float(value) for value in row) for row in transform),
        identity, 160, 120, 1.0, 0.01, 10.0, True, False,
    )


def _execution() -> ExecutionSpecV1:
    renderer = RendererSelectionV1(
        'renderer-selection-v1', 'mujoco', 'native-opengl', D03_DYNAMIC_PROFILE, None,
    )
    return ExecutionSpecV1(
        'execution-spec-v1', 'geophys', 'cpu', D03_PHYSICS_PROFILE,
        31, 'best_effort', renderer, physics_device='cpu:0',
    )


def _save_rgb(path: Path, image: np.ndarray) -> None:
    Image.fromarray((np.clip(image, 0.0, 1.0) * 255.0).astype(np.uint8)).save(path)


def run_s2(output: Path | str) -> dict[str, object]:
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    candidate = build_position_candidate(
        output / 'source-closure', provider='geophys', horizon=CONTROL_INTERVALS,
    )
    env = candidate.env
    renderer = None
    try:
        env.reset()
        source = DynamicCameraRenderSourceV1.from_runtime_source(candidate.source)
        camera = _camera(candidate)
        execution = _execution()
        renderer = create_dynamic_camera_session(
            camera, execution, source=source, initial_state=env.typed_state.view,
            manifest=dynamic_render_manifest(),
        )

        controller_counts = {'compute_during_capture': 0}
        provider_counts = {'step_calls': 0}
        mujoco_counts = {'mj_step_during_capture': 0, 'mj_forward_during_capture': 0}
        capture_phase = {'active': False}
        controller_type = type(env.controller)
        session_type = type(env.session)
        controller_compute = controller_type.compute
        provider_step = session_type.step

        def counted_compute(controller, *args, **kwargs):
            if controller is env.controller and capture_phase['active']:
                controller_counts['compute_during_capture'] += 1
            return controller_compute(controller, *args, **kwargs)

        def counted_step(session, *args, **kwargs):
            if session is env.session:
                provider_counts['step_calls'] += 1
            return provider_step(session, *args, **kwargs)

        import mujoco
        mj_step = mujoco.mj_step
        mj_forward = mujoco.mj_forward

        def counted_mj_step(*args, **kwargs):
            if capture_phase['active']:
                mujoco_counts['mj_step_during_capture'] += 1
            return mj_step(*args, **kwargs)

        def counted_mj_forward(*args, **kwargs):
            if capture_phase['active']:
                mujoco_counts['mj_forward_during_capture'] += 1
            return mj_forward(*args, **kwargs)

        state_before_capture = (int(env.state.control_step), float(env.state.simulation_time))
        with (
            patch.object(controller_type, 'compute', counted_compute),
            patch.object(session_type, 'step', counted_step),
            patch.object(mujoco, 'mj_step', counted_mj_step),
            patch.object(mujoco, 'mj_forward', counted_mj_forward),
        ):
            capture_phase['active'] = True
            initial = renderer.capture(env.typed_state.view).rgb.copy()
            capture_phase['active'] = False
        if state_before_capture != (int(env.state.control_step), float(env.state.simulation_time)):
            raise AssertionError('initial dynamic capture changed the public physics clock')
        _save_rgb(output / 'initial.png', initial)
        initial_receipt = renderer.last_sync

        hand_pose = _typed_hand_and_joints(env)[1]
        target_pose = type(hand_pose)(
            (hand_pose.position[0] + HAND_TARGET_DELTA_M, *hand_pose.position[1:]),
            hand_pose.quaternion_wxyz,
        )
        action = _request(candidate.controller_binding_plan, target_pose, 1.0)
        physics_dt = float(candidate.artifact.timebase.physics_dt)
        control_dt = float(candidate.artifact.timebase.control_dt)
        native_steps_requested = int(candidate.artifact.timebase.control_substeps)
        completed_intervals = 0
        interval_clock_rows = []
        with patch.object(session_type, 'step', counted_step):
            for _ in range(CONTROL_INTERVALS):
                before = env.state
                env.step(action)
                after = env.state
                elapsed = float(after.simulation_time - before.simulation_time)
                inferred = int(round(elapsed / physics_dt))
                if (after.control_step != before.control_step + 1
                        or inferred != native_steps_requested
                        or abs(elapsed - control_dt) > NATIVE_CLOCK_ATOL_S):
                    raise AssertionError('Position candidate did not complete five native 2 ms steps per 10 ms interval')
                completed_intervals += 1
                interval_clock_rows.append({
                    'control_step': int(after.control_step),
                    'simulation_time_s': float(after.simulation_time),
                    'native_step_delta_inferred': inferred,
                    'elapsed_s': elapsed,
                })

        moved_state = env.typed_state.view
        moved_pose = next(
            item.pose_world for item in moved_state.frames
            if (item.frame.entity_id, item.frame.frame_id) == ('panda-main', 'hand')
        )
        hand_displacement = float(np.linalg.norm(
            np.asarray(moved_pose.position) - np.asarray(hand_pose.position),
        ))
        before_capture = (int(env.state.control_step), float(env.state.simulation_time))
        with (
            patch.object(controller_type, 'compute', counted_compute),
            patch.object(session_type, 'step', counted_step),
            patch.object(mujoco, 'mj_step', counted_mj_step),
            patch.object(mujoco, 'mj_forward', counted_mj_forward),
        ):
            capture_phase['active'] = True
            moved = renderer.capture(moved_state).rgb.copy()
            capture_phase['active'] = False
        after_capture = (int(env.state.control_step), float(env.state.simulation_time))
        if before_capture != after_capture:
            raise AssertionError('dynamic capture after motion changed the public physics clock')
        _save_rgb(output / 'moved.png', moved)

        changed_pixels = int(np.count_nonzero(np.max(np.abs(moved - initial), axis=2) > PIXEL_DELTA_THRESHOLD))
        if hand_displacement < 0.02:
            raise AssertionError(f'Position candidate hand motion was too small: {hand_displacement:g} m')
        if changed_pixels < MIN_CHANGED_PIXELS:
            raise AssertionError(
                f'dynamic RGB did not reflect real arm motion: {changed_pixels} pixels changed '
                f'(required {MIN_CHANGED_PIXELS} at threshold {PIXEL_DELTA_THRESHOLD:g})'
            )
        if controller_counts['compute_during_capture'] or provider_counts['step_calls'] != CONTROL_INTERVALS:
            raise AssertionError(
                'capture called Controller or changed the expected Provider step count: '
                f'controller={controller_counts}, provider={provider_counts}, '
                f'expected_outer_interval_calls={CONTROL_INTERVALS}'
            )
        if mujoco_counts != {'mj_step_during_capture': 0, 'mj_forward_during_capture': 0}:
            raise AssertionError(f'render path called MuJoCo dynamics: {mujoco_counts}')

        receipt = renderer.last_sync
        graphics = renderer.graphics_device_info()
        if 'NVIDIA GeForce RTX 5060' not in str(graphics.get('renderer')):
            raise AssertionError(f'native MuJoCo GL device differs from this recorded intersection: {graphics}')
        if receipt.static_geometry_build_count != 1:
            raise AssertionError('static Scene geometry was rebuilt after a state transform update')
        if receipt.geometry_version != initial_receipt.geometry_version:
            raise AssertionError('geometry version changed during transform-only Position execution')

        report = {
            'status': 'D03_S2_BOUNDED_PASS',
            'scope': {
                'physics_provider': 'GeoPhys',
                'physics_backend': 'CPU / Taichi x64 CPU runtime',
                'render_provider': 'MuJoCo native OpenGL Renderer',
                'render_backend_selection': 'native-opengl',
                'render_device': graphics,
                'task_candidate': candidate.artifact.artifact_id,
                'task_artifact_hash': candidate.artifact.identity_hash,
                'controller_profile': env.controller.profile_id,
                'controller_identity': env.controller.identity,
                'scene_identity_hash': source.scene_identity_hash,
                'source_identity': source.source_identity,
                'source_closure_digest': source.source_closure_digest,
                'render_source_identity_hash': source.identity_hash,
                'camera_id': camera.camera_id,
                'camera_identity_hash': camera.identity_hash,
            },
            'mapping': {
                'canonical_joint_bindings': tuple(item.to_mapping() for item in source.joint_bindings),
                'canonical_frame_to_native_body': tuple(item.to_mapping() for item in source.frame_bindings),
                'canonical_frame_to_renderer_instances': tuple(
                    item.to_mapping() for item in receipt.visual_instance_bindings
                ),
            },
            'tolerances': {
                'frame_position_atol_m': FRAME_POSITION_ATOL_M,
                'frame_quaternion_sign_invariant_l2_atol': FRAME_QUATERNION_SIGN_INVARIANT_L2_ATOL,
                'pixel_delta_threshold': PIXEL_DELTA_THRESHOLD,
                'minimum_changed_pixels': MIN_CHANGED_PIXELS,
                'native_clock_atol_s': NATIVE_CLOCK_ATOL_S,
            },
            'versions': {
                'initial': initial_receipt.to_mapping(),
                'moved': receipt.to_mapping(),
                'geometry_version_unchanged': initial_receipt.geometry_version == receipt.geometry_version,
                'publication_version_changed': initial_receipt.publication_version != receipt.publication_version,
                'transform_version_changed': initial_receipt.transform_version != receipt.transform_version,
                'static_geometry_build_count': renderer.static_geometry_build_count,
            },
            'motion_pixels': {
                'hand_origin_before_m': tuple(float(value) for value in hand_pose.position),
                'hand_origin_after_m': tuple(float(value) for value in moved_pose.position),
                'hand_displacement_m': hand_displacement,
                'changed_pixel_count': changed_pixels,
                'mean_absolute_rgb_delta': float(np.mean(np.abs(moved - initial))),
                'initial_png': str(output / 'initial.png'),
                'moved_png': str(output / 'moved.png'),
            },
            'timing': {
                'physics_dt_s': physics_dt,
                'outer_control_dt_s': control_dt,
                'native_steps_requested_per_interval': native_steps_requested,
                'completed_intervals': completed_intervals,
                'completed_native_steps_inferred': sum(row['native_step_delta_inferred'] for row in interval_clock_rows),
                'provider_step_calls_observed': provider_counts['step_calls'],
                'interval_clock_rows': interval_clock_rows,
                'capture_clock_before': before_capture,
                'capture_clock_after': after_capture,
                'capture_controller_compute_calls': controller_counts['compute_during_capture'],
                'capture_provider_step_calls': 0,
                'capture_mujoco_mj_step_calls': mujoco_counts['mj_step_during_capture'],
                'capture_mujoco_mj_forward_calls': mujoco_counts['mj_forward_during_capture'],
            },
        }
        (output / 'd03_s2_receipt.json').write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding='utf-8',
        )
        return report
    finally:
        if renderer is not None:
            renderer.close()
        env.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run_s2(args.output)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
