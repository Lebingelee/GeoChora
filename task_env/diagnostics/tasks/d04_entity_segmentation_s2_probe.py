"""Bounded real D04 Entity Instance Segmentation S2 probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from task_env.artifacts import ExecutionSpecV1, RendererSelectionV1
from task_env.diagnostics.tasks.c02b_position_candidate import build_position_candidate
from task_env.diagnostics.tasks.c02b_position_s2_probe import _request
from task_env.diagnostics.tasks.d04_rgbd_camera_s2_probe import (
    BACKPROJECTION_ATOL_M,
    CAMERA_FAR_M,
    CAMERA_FOV_Y,
    CAMERA_HEIGHT,
    CAMERA_NEAR_M,
    CAMERA_WIDTH,
    CONTROL_INTERVALS,
    FRAME_POSITION_ATOL_M,
    FRAME_QUATERNION_SIGN_INVARIANT_L2_ATOL,
    MIN_CHANGED_PIXELS,
    NATIVE_CLOCK_ATOL_S,
    PIXEL_DELTA_THRESHOLD,
    _camera_geometry,
    _frame_pose,
    _pose_matrix,
    _world_from_optical_camera,
    mounted_hand_camera,
)
from task_env.objects.nut_assembly import PEG_HALF_HEIGHT, SQUARE_PEG_HALF_WIDTH
from task_env.observations.canonical_camera import MOUNT_FROM_CAMERA
from task_env.observations.canonical_camera.images import CanonicalEntityLabelMapV1
from task_env.render.camera import (
    D03_PHYSICS_PROFILE,
    D04_ENTITY_SEGMENTATION_PROFILE,
    CameraCaptureIdentityV1,
    DynamicCameraRenderSourceV1,
    create_dynamic_camera_session,
    dynamic_entity_instance_segmentation_manifest,
)
SEGMENTATION_CONTROL_INTERVALS = CONTROL_INTERVALS


def _fixed_occlusion_camera(candidate, state, hand_target):
    """Aim a fixed, versioned diagnostic view through the planned hand pose."""

    peg = _frame_pose(state, 'square-peg-instance', 'peg1')
    direction = np.asarray(hand_target.position) - np.asarray(peg.position)
    norm = float(np.linalg.norm(direction))
    if not math.isfinite(norm) or norm <= 1.0e-8:
        raise ValueError('occlusion calibration needs a distinct hand target and peg')
    camera_position = np.asarray(peg.position) + direction / norm * 1.5
    optical = _world_from_optical_camera(camera_position, peg.position)
    world_from_mount = optical @ np.linalg.inv(np.asarray(MOUNT_FROM_CAMERA, dtype=np.float64))
    return _camera_geometry(
        candidate,
        'd04-entity-seg-fixed-occlusion-v1',
        'world',
        world_from_mount,
    )


def _segmentation_execution():
    selection = RendererSelectionV1(
        'renderer-selection-v1', 'mujoco', 'native-opengl',
        D04_ENTITY_SEGMENTATION_PROFILE, None,
    )
    return ExecutionSpecV1(
        'execution-spec-v1', 'geophys', 'cpu', D03_PHYSICS_PROFILE,
        32, 'best_effort', selection, physics_device='cpu:0',
    )


def _save_capture(output: Path, name: str, observation):
    segmentation = observation.segmentation
    if segmentation is None:
        raise AssertionError('Entity segmentation profile returned no canonical mask')
    mask_path = output / f'{name}_mask.npy'
    bundle_path = output / f'{name}_labels.json'
    np.save(mask_path, segmentation.mask, allow_pickle=False)
    Image.fromarray(
        np.asarray(observation.rgb * 255.0, dtype=np.uint8), mode='RGB',
    ).save(output / f'{name}_rgb.png')
    np.save(output / f'{name}_depth.npy', observation.depth, allow_pickle=False)
    bundle = {
        'segmentation': segmentation.to_mapping(),
        'label_map': segmentation.label_map.to_mapping(),
        'capture_identity': observation.capture_identity.to_mapping(),
    }
    bundle_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + '\n', encoding='utf-8')

    # Read the actual files back; compare both pixel values and the complete
    # canonical label/capture contract rather than trusting the write buffers.
    loaded_mask = np.load(mask_path, allow_pickle=False)
    loaded = json.loads(bundle_path.read_text(encoding='utf-8'))
    label_map = CanonicalEntityLabelMapV1.from_mapping(loaded['label_map'])
    capture_identity = CameraCaptureIdentityV1.from_mapping(loaded['capture_identity'])
    if loaded_mask.dtype != np.uint32 or not np.array_equal(loaded_mask, segmentation.mask):
        raise AssertionError(f'{name} on-disk mask changed dtype or numeric values')
    if hashlib.sha256(loaded_mask.tobytes(order='C')).hexdigest() != loaded['segmentation']['mask_sha256']:
        raise AssertionError(f'{name} mask checksum does not match the saved segmentation contract')
    if label_map.identity_hash != segmentation.label_map.identity_hash:
        raise AssertionError(f'{name} on-disk label map identity differs from the captured map')
    if capture_identity.identity_hash != observation.capture_identity.identity_hash:
        raise AssertionError(f'{name} on-disk capture identity differs from the observation')
    if label_map.capture_identity_hash != capture_identity.identity_hash:
        raise AssertionError(f'{name} mask label map and capture identity have different publications')
    allowed = {0, *(entry.label for entry in label_map.labels)}
    if not set(np.unique(loaded_mask).tolist()).issubset(allowed):
        raise AssertionError(f'{name} on-disk mask contains a label absent from its label map')
    return {
        'mask_path': str(mask_path),
        'label_map_path': str(bundle_path),
        'mask_sha256': hashlib.sha256(loaded_mask.tobytes(order='C')).hexdigest(),
        'label_map_identity_hash': label_map.identity_hash,
        'capture_identity_hash': capture_identity.identity_hash,
        'state_boundary_id': capture_identity.state_boundary.boundary_id,
        'scene_instance_id': capture_identity.state_boundary.scene_instance_id,
    }


def _analytic_box_depth_map(observation, peg_pose):
    """Independent ray/OBB optical-Z oracle for the existing square-peg box."""

    metadata = observation.metadata
    height, width = observation.depth.shape
    yy, xx = np.indices((height, width), dtype=np.float64)
    K = np.asarray(metadata.K, dtype=np.float64)
    rays_camera = np.stack((
        (xx + 0.5 - K[0, 2]) / K[0, 0],
        (yy + 0.5 - K[1, 2]) / K[1, 1],
        np.ones((height, width), dtype=np.float64),
    ), axis=0).reshape(3, -1)
    world_from_camera = np.asarray(metadata.T_world_from_camera, dtype=np.float64)
    world_from_peg = _pose_matrix(peg_pose)
    origin_local = world_from_peg[:3, :3].T @ (
        world_from_camera[:3, 3] - world_from_peg[:3, 3]
    )
    directions_local = world_from_peg[:3, :3].T @ world_from_camera[:3, :3] @ rays_camera
    half = np.asarray((SQUARE_PEG_HALF_WIDTH, SQUARE_PEG_HALF_WIDTH, PEG_HALF_HEIGHT), dtype=np.float64)
    with np.errstate(divide='ignore', invalid='ignore'):
        a = (-half[:, None] - origin_local[:, None]) / directions_local
        b = (half[:, None] - origin_local[:, None]) / directions_local
    entry = np.max(np.minimum(a, b), axis=0)
    exit_ = np.min(np.maximum(a, b), axis=0)
    hit = np.isfinite(entry) & np.isfinite(exit_) & (exit_ >= np.maximum(entry, 0.0))
    depth = np.zeros(height * width, dtype=np.float64)
    depth[hit] = np.maximum(entry[hit], 0.0)
    return depth.reshape(height, width), hit.reshape(height, width)


def _capture_all(env, sessions, state, counters, active):
    import mujoco

    controller_type, provider_type = type(env.controller), type(env.session)
    original_compute, original_step = controller_type.compute, provider_type.step
    original_mj_step, original_mj_forward = mujoco.mj_step, mujoco.mj_forward

    def count_compute(controller, *args, **kwargs):
        if controller is env.controller and active['capture']:
            counters['controller_compute'] += 1
        return original_compute(controller, *args, **kwargs)

    def count_provider_step(session, *args, **kwargs):
        if session is env.session and active['capture']:
            counters['provider_step'] += 1
        return original_step(session, *args, **kwargs)

    def count_mj_step(*args, **kwargs):
        if active['capture']:
            counters['mj_step'] += 1
        return original_mj_step(*args, **kwargs)

    def count_mj_forward(*args, **kwargs):
        if active['capture']:
            counters['mj_forward'] += 1
        return original_mj_forward(*args, **kwargs)

    active['capture'] = True
    try:
        with (
            patch.object(controller_type, 'compute', count_compute),
            patch.object(provider_type, 'step', count_provider_step),
            patch.object(mujoco, 'mj_step', count_mj_step),
            patch.object(mujoco, 'mj_forward', count_mj_forward),
        ):
            observations = tuple(session.capture(state) for session in sessions)
            devices = tuple(session.graphics_device_info() for session in sessions)
    finally:
        active['capture'] = False
    if any(counters.values()):
        raise AssertionError(f'camera capture called Controller or advanced physics: {counters}')
    return observations, devices


def run_s2(output: Path | str) -> dict[str, object]:
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    candidate = build_position_candidate(
        output / 'source-closure', provider='geophys', horizon=SEGMENTATION_CONTROL_INTERVALS,
    )
    env = candidate.env
    sessions = []
    try:
        env.reset()
        source = DynamicCameraRenderSourceV1.from_runtime_source(candidate.source)
        initial_state = env.typed_state.view
        initial_hand = _frame_pose(initial_state, 'panda-main', 'hand')
        peg = _frame_pose(initial_state, 'square-peg-instance', 'peg1')
        target_position = np.asarray(initial_hand.position, dtype=np.float64)
        target_position[1] += 0.12
        hand_target = type(initial_hand)(
            tuple(float(value) for value in target_position),
            initial_hand.quaternion_wxyz,
        )
        fixed_camera = _fixed_occlusion_camera(candidate, initial_state, hand_target)
        mounted_camera = mounted_hand_camera(candidate, initial_state)
        manifest = dynamic_entity_instance_segmentation_manifest()
        fixed = create_dynamic_camera_session(
            fixed_camera, _segmentation_execution(),
            source=source, initial_state=initial_state, manifest=manifest,
        )
        mounted = create_dynamic_camera_session(
            mounted_camera, _segmentation_execution(),
            source=source, initial_state=initial_state, manifest=manifest,
        )
        sessions.extend((fixed, mounted))
        counters = {'controller_compute': 0, 'provider_step': 0, 'mj_step': 0, 'mj_forward': 0}
        active = {'capture': False}

        initial_clock = (int(env.state.control_step), float(env.state.simulation_time))
        (fixed_initial, mounted_initial), initial_devices = _capture_all(
            env, sessions, initial_state, counters, active,
        )
        if (int(env.state.control_step), float(env.state.simulation_time)) != initial_clock:
            raise AssertionError('initial fixed/mounted RGBD-mask capture advanced physical time')

        expected_entities = {'panda-main', 'square-peg-instance'}
        for observation in (fixed_initial, mounted_initial):
            segmentation = observation.segmentation
            if segmentation is None:
                raise AssertionError('segmentation profile returned no Entity mask')
            if segmentation.mask.dtype != np.uint32 or segmentation.mask.shape != (CAMERA_HEIGHT, CAMERA_WIDTH):
                raise AssertionError('Entity mask violates H×W uint32 output contract')
            if not observation.rgb.flags.c_contiguous or observation.depth.dtype != np.float32:
                raise AssertionError('RGB/Depth contract changed under Entity segmentation profile')
            if set(observation.capture_identity.modalities) != {
                'rgb', 'depth', 'entity_instance_segmentation',
            }:
                raise AssertionError('capture identity omitted a co-captured RGBD or Entity mask modality')
            if observation.capture_identity.state_boundary.boundary_id != initial_state.boundary.boundary_id:
                raise AssertionError('initial RGBD-mask buffers do not share the initial state publication')
            if observation.capture_identity.state_boundary.scene_instance_id != segmentation.label_map.scene_instance_id:
                raise AssertionError('initial label map SceneInstance differs from the image capture')
            if not expected_entities.issubset({entry.entity_id for entry in segmentation.label_map.labels}):
                raise AssertionError('label map omitted a required visible canonical Entity')

        fixed_entities = {entry.entity_id: entry.label for entry in fixed_initial.segmentation.label_map.labels}
        peg_label = fixed_entities['square-peg-instance']
        panda_label = fixed_entities['panda-main']
        if fixed_entities != {'panda-main': 1, 'square-peg-instance': 2}:
            raise AssertionError('fixed label map is not deterministic by canonical Entity ID')

        initial_artifacts = {
            'fixed_initial': _save_capture(output, 'fixed_initial', fixed_initial),
            'mounted_initial': _save_capture(output, 'mounted_initial', mounted_initial),
        }

        action = _request(candidate.controller_binding_plan, hand_target, 1.0)
        physics_dt = float(candidate.artifact.timebase.physics_dt)
        control_dt = float(candidate.artifact.timebase.control_dt)
        native_steps = int(candidate.artifact.timebase.control_substeps)
        completed_rows = []
        for _ in range(SEGMENTATION_CONTROL_INTERVALS):
            before = env.state
            env.step(action)
            after = env.state
            elapsed = float(after.simulation_time - before.simulation_time)
            completed = int(round(elapsed / physics_dt))
            if (
                after.control_step != before.control_step + 1
                or completed != native_steps
                or abs(elapsed - control_dt) > NATIVE_CLOCK_ATOL_S
            ):
                raise AssertionError('Position candidate did not complete five native 2 ms steps per 10 ms interval')
            completed_rows.append({
                'control_step': int(after.control_step),
                'simulation_time_s': float(after.simulation_time),
                'native_step_delta_inferred_from_public_clock': completed,
            })

        moved_state = env.typed_state.view
        moved_hand = _frame_pose(moved_state, 'panda-main', 'hand')
        hand_displacement = float(np.linalg.norm(
            np.asarray(moved_hand.position) - np.asarray(initial_hand.position),
        ))
        if hand_displacement < 0.02:
            raise AssertionError(f'Position action did not move the Panda hand enough: {hand_displacement:g} m')
        moved_clock = (int(env.state.control_step), float(env.state.simulation_time))
        (fixed_moved, mounted_moved), moved_devices = _capture_all(
            env, sessions, moved_state, counters, active,
        )
        if (int(env.state.control_step), float(env.state.simulation_time)) != moved_clock:
            raise AssertionError('moving fixed/mounted RGBD-mask capture advanced physical time')
        if fixed_moved.capture_identity.state_boundary.boundary_id != mounted_moved.capture_identity.state_boundary.boundary_id:
            raise AssertionError('fixed and mounted captures consumed different moved-state publications')
        fixed_mask_delta = int(np.count_nonzero(fixed_moved.segmentation.mask != fixed_initial.segmentation.mask))
        mounted_mask_delta = int(np.count_nonzero(mounted_moved.segmentation.mask != mounted_initial.segmentation.mask))
        fixed_rgb_delta = int(np.count_nonzero(
            np.max(np.abs(fixed_moved.rgb - fixed_initial.rgb), axis=2) > PIXEL_DELTA_THRESHOLD,
        ))
        mounted_rgb_delta = int(np.count_nonzero(
            np.max(np.abs(mounted_moved.rgb - mounted_initial.rgb), axis=2) > PIXEL_DELTA_THRESHOLD,
        ))
        fixed_depth_delta = int(np.count_nonzero(fixed_moved.depth != fixed_initial.depth))
        mounted_depth_delta = int(np.count_nonzero(mounted_moved.depth != mounted_initial.depth))
        if min(fixed_mask_delta, mounted_mask_delta, fixed_rgb_delta, mounted_rgb_delta,
               fixed_depth_delta, mounted_depth_delta) < MIN_CHANGED_PIXELS:
            raise AssertionError('real Position motion did not change RGB, Depth, and Entity mask in both cameras')

        moved_artifacts = {
            'fixed_moved': _save_capture(output, 'fixed_moved', fixed_moved),
            'mounted_moved': _save_capture(output, 'mounted_moved', mounted_moved),
        }

        # Prove a real occlusion transition against an independent ray/box
        # surface oracle: a pixel on the peg face changes from the peg Entity
        # to the nearer Panda Entity as the planned hand reaches that ray.
        peg_pose = _frame_pose(moved_state, 'square-peg-instance', 'peg1')
        peg_surface_z, peg_hits = _analytic_box_depth_map(fixed_moved, peg_pose)
        initial_mask = fixed_initial.segmentation.mask
        moved_mask = fixed_moved.segmentation.mask
        occluded = (
            peg_hits
            & (initial_mask == peg_label)
            & (moved_mask == panda_label)
            & (fixed_moved.depth > 0)
            & (fixed_moved.depth < peg_surface_z - 2.0e-3)
        )
        occluded_pixels = int(np.count_nonzero(occluded))
        if occluded_pixels < 1:
            raise AssertionError(
                'the moving Panda did not visibly occlude the known peg surface in the fixed camera '
                f'(initial peg pixels={int(np.count_nonzero(initial_mask == peg_label))}, '
                f'moved Panda pixels={int(np.count_nonzero(moved_mask == panda_label))}, '
                f'analytic peg-hit pixels={int(np.count_nonzero(peg_hits))}, '
                f'peg-to-Panda candidate pixels={int(np.count_nonzero(peg_hits & (initial_mask == peg_label) & (moved_mask == panda_label)))})'
            )
        occlusion_row, occlusion_col = tuple(int(value) for value in np.argwhere(occluded)[0])
        occlusion_receipt = {
            'row': occlusion_row,
            'column': occlusion_col,
            'expected_peg_surface_optical_z_m': float(peg_surface_z[occlusion_row, occlusion_col]),
            'measured_nearer_optical_z_m': float(fixed_moved.depth[occlusion_row, occlusion_col]),
            'initial_entity_id': 'square-peg-instance',
            'moved_entity_id': 'panda-main',
            'occluded_pixel_count': occluded_pixels,
        }

        fixed_pose_delta = float(np.max(np.abs(
            np.asarray(fixed_moved.metadata.T_world_from_camera)
            - np.asarray(fixed_initial.metadata.T_world_from_camera),
        )))
        mounted_pose_delta = float(np.linalg.norm(
            np.asarray(mounted_moved.metadata.T_world_from_camera)[:3, 3]
            - np.asarray(mounted_initial.metadata.T_world_from_camera)[:3, 3],
        ))
        if fixed_pose_delta > 1.0e-9 or mounted_pose_delta < 0.02:
            raise AssertionError('fixed/mounted camera pose did not preserve its declared parent Frame behavior')
        if fixed_moved.segmentation.label_map.state_boundary_id != fixed_moved.capture_identity.state_boundary.boundary_id:
            raise AssertionError('moved mask or label map lost its capture publication identity')

        old_boundary_id = moved_state.boundary.boundary_id
        env.reset()
        reset_state = env.typed_state.view
        reset_clock = (int(env.state.control_step), float(env.state.simulation_time))
        (fixed_reset, mounted_reset), reset_devices = _capture_all(
            env, sessions, reset_state, counters, active,
        )
        if (int(env.state.control_step), float(env.state.simulation_time)) != reset_clock:
            raise AssertionError('reset fixed/mounted RGBD-mask capture advanced physical time')
        for name, reset_observation, initial_observation in (
            ('fixed', fixed_reset, fixed_initial), ('mounted', mounted_reset, mounted_initial),
        ):
            if reset_observation.capture_identity.state_boundary.boundary_id == old_boundary_id:
                raise AssertionError(f'{name} reset capture reused a previous-episode boundary')
            if reset_observation.segmentation.label_map.capture_identity_hash != reset_observation.capture_identity.identity_hash:
                raise AssertionError(f'{name} reset label map is bound to the wrong capture identity')
            if reset_observation.segmentation.label_map.labels != initial_observation.segmentation.label_map.labels:
                raise AssertionError(f'{name} reset label numbering changed for the same source closure')
            if not np.array_equal(reset_observation.segmentation.mask, initial_observation.segmentation.mask):
                raise AssertionError(f'{name} reset mask did not reproduce the same reset publication')
            if not np.array_equal(reset_observation.rgb, initial_observation.rgb):
                raise AssertionError(f'{name} reset RGB did not reproduce the same reset publication')
            if not np.array_equal(reset_observation.depth, initial_observation.depth):
                raise AssertionError(f'{name} reset Depth did not reproduce the same reset publication')
        for session in sessions:
            try:
                session.capture(moved_state)
            except ValueError as exc:
                if 'previous episode' not in str(exc):
                    raise
            else:
                raise AssertionError('D04 segmentation session accepted a previous-episode publication')
        reset_artifacts = {
            'fixed_reset': _save_capture(output, 'fixed_reset', fixed_reset),
            'mounted_reset': _save_capture(output, 'mounted_reset', mounted_reset),
        }

        all_devices = (*initial_devices, *moved_devices, *reset_devices)
        if not all(device.get('renderer') and device.get('vendor') and device.get('version') for device in all_devices):
            raise AssertionError('native OpenGL current-context query did not return actual device strings')
        device = all_devices[0]
        result = {
            'status': 'D04_ENTITY_INSTANCE_SEGMENTATION_FIXED_MOUNTED_S2_BOUNDED_PASS',
            'scope': {
                'task_candidate': candidate.artifact.artifact_id,
                'task_artifact_hash': candidate.artifact.identity_hash,
                'scene_identity_hash': source.scene_identity_hash,
                'source_closure_digest': source.source_closure_digest,
                'source_identity_hash': source.identity_hash,
                'controller_identity': env.controller.identity,
                'controller_profile': 'panda-main/position-servo-v1',
                'physics_provider': 'GeoPhys',
                'physics_backend': 'Taichi x64 CPU runtime',
                'render_provider': 'MuJoCo native OpenGL Renderer',
                'render_profile': D04_ENTITY_SEGMENTATION_PROFILE,
                'render_device_observed_after_capture': device,
                'device_is_diagnostic_only': True,
                'fixed_camera_id': fixed_camera.camera_id,
                'mounted_camera_id': mounted_camera.camera_id,
                'mounted_parent_frame': mounted_camera.parent_frame,
                'unsupported': ['free-joint', 'Assembly', 'Segmentation categories', 'other provider/backend pairs', 'D05b qualification'],
            },
            'mask_contract': {
                'schema_version': 'canonical-entity-instance-segmentation-v1',
                'label_map_schema_version': 'canonical-entity-label-map-v1',
                'shape': [CAMERA_HEIGHT, CAMERA_WIDTH],
                'dtype': 'uint32',
                'background_label': 0,
                'positive_labels': 'dense, deterministic, sorted canonical Entity IDs',
                'world_body_geometry': 'background label 0; no synthetic Entity identity',
                'native_geom_ids_public': False,
                'capture_binding': 'capture identity hash + exact state boundary and SceneInstance',
                'rgb_dtype': str(fixed_initial.rgb.dtype),
                'depth_dtype': str(fixed_initial.depth.dtype),
                'depth_unit': 'metres optical-Z along camera +Z',
            },
            'timebase': {
                'outer_control_dt_s': control_dt,
                'physics_dt_s': physics_dt,
                'native_steps_requested_per_outer_interval': native_steps,
                'completed_outer_intervals': len(completed_rows),
                'completed_native_steps_inferred_from_public_clock': sum(
                    row['native_step_delta_inferred_from_public_clock'] for row in completed_rows
                ),
                'intervals': completed_rows,
            },
            'capture_side_effects': counters,
            'motion': {
                'hand_displacement_m': hand_displacement,
                'fixed_pose_max_abs_delta': fixed_pose_delta,
                'mounted_pose_translation_delta_m': mounted_pose_delta,
                'fixed_mask_changed_pixels': fixed_mask_delta,
                'mounted_mask_changed_pixels': mounted_mask_delta,
                'fixed_rgb_changed_pixels': fixed_rgb_delta,
                'mounted_rgb_changed_pixels': mounted_rgb_delta,
                'fixed_depth_changed_pixels': fixed_depth_delta,
                'mounted_depth_changed_pixels': mounted_depth_delta,
                'known_geometry_occlusion': occlusion_receipt,
                'frame_position_atol_m': FRAME_POSITION_ATOL_M,
                'frame_quaternion_sign_invariant_l2_atol': FRAME_QUATERNION_SIGN_INVARIANT_L2_ATOL,
                'known_geometry_backprojection_atol_m': BACKPROJECTION_ATOL_M,
            },
            'disk_readback': {
                **initial_artifacts,
                **moved_artifacts,
                **reset_artifacts,
            },
        }
        (output / 'd04_entity_segmentation_s2_receipt.json').write_text(
            json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8',
        )
        return result
    finally:
        for session in sessions:
            session.close()
        env.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--output',
        default='workspace/maintenance/d04_entity_segmentation_20261022/s2_geophys_mujoco',
    )
    args = parser.parse_args()
    print(json.dumps(run_s2(args.output), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
