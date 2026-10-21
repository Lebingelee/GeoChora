"""Defect-sensitive S1 contracts for the bounded D04 RGB/Depth camera slice."""

from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from task_env.artifacts import (
    CapabilityAdmissionError,
    ExecutionSpecV1,
    RendererSelectionV1,
)
from task_env.diagnostics.tasks.c02b_position_candidate import build_position_candidate
from task_env.diagnostics.tasks.c02b_position_s2_probe import _request, _typed_hand_and_joints
from task_env.diagnostics.tasks.d04_rgbd_camera_s2_probe import (
    CAMERA_HEIGHT,
    CAMERA_WIDTH,
    _frame_pose,
    _ray_box_hit,
    d03_execution,
    d04_execution,
    fixed_calibration_camera,
    mounted_hand_camera,
)
from task_env.observations.canonical_camera import (
    CanonicalCameraObservation,
    CanonicalEntityInstanceSegmentationV1,
    CanonicalEntityLabelV1,
    back_project_world,
    intrinsics,
    project_world,
    resolve_camera,
)
from task_env.observations.canonical_camera.geometry import optical_depth
from task_env.render.camera import (
    D04_ENTITY_SEGMENTATION_PROFILE,
    D03_PHYSICS_PROFILE,
    DynamicCameraRenderSourceV1,
    admit_dynamic_camera,
    create_dynamic_camera_session,
    dynamic_render_manifest,
    dynamic_rgbd_render_manifest,
    dynamic_entity_instance_segmentation_manifest,
)
from task_env.render.camera.mujoco import _resolve_canonical_entity_geometry_labels


def _candidate(tmp_path: Path, *, horizon=4):
    candidate = build_position_candidate(tmp_path / 'position-candidate', provider='geophys', horizon=horizon)
    candidate.env.reset()
    return candidate


def test_d04_profile_geometry_and_depth_invalid_contract_are_versioned_and_legacy_safe(tmp_path):
    candidate = _candidate(tmp_path)
    try:
        source = DynamicCameraRenderSourceV1.from_runtime_source(candidate.source)
        state = candidate.env.typed_state.view
        camera = fixed_calibration_camera(candidate, state)
        d03_claims = {claim.name for claim in dynamic_render_manifest().capabilities}
        d04_claims = {claim.name for claim in dynamic_rgbd_render_manifest().capabilities}
        assert d03_claims == {'rgb_camera'}
        assert d04_claims == {'rgb_camera', 'depth_camera'}
        admit_dynamic_camera(
            camera, d04_execution(camera.camera_id), source=source,
            manifest=dynamic_rgbd_render_manifest(),
        )

        # The same RGBD request remains rejected by the original D03 RGB profile.
        with pytest.raises(CapabilityAdmissionError, match='depth_camera'):
            admit_dynamic_camera(
                camera, d03_execution(camera.camera_id), source=source,
                manifest=dynamic_render_manifest(),
            )
        missing_parent = replace(camera, camera_id='d04-missing-parent-v1', parent_frame='not-a-frame')
        execution = d04_execution(missing_parent.camera_id)
        import task_env.render.camera.mujoco as mujoco_camera
        with patch.object(
            mujoco_camera, 'MuJoCoDynamicCameraSession',
            side_effect=AssertionError('missing camera Frame reached native construction'),
        ):
            with pytest.raises(CapabilityAdmissionError, match='parent Frame'):
                create_dynamic_camera_session(
                    missing_parent, execution, source=source,
                    initial_state=state, manifest=dynamic_rgbd_render_manifest(),
                )

        # Provider-free pinhole projection/back-projection is checked against
        # the fixture's known box, without consulting the native Renderer.
        metadata = resolve_camera(camera, state)
        peg = _frame_pose(state, 'square-peg-instance', 'peg1')
        center_pixel = project_world(metadata, np.asarray((peg.position,), dtype=np.float64))[0]
        assert np.allclose(center_pixel, (camera.width / 2, camera.height / 2), atol=1e-8, rtol=0)
        row, col = camera.height // 2, camera.width // 2
        expected_depth, expected_hit = _ray_box_hit(metadata, peg, row, col)
        backprojected = back_project_world(
            metadata,
            np.asarray(((col + 0.5, row + 0.5),)),
            np.asarray((expected_depth,)),
        )[0]
        assert np.linalg.norm(backprojected - expected_hit) <= 1e-9
        assert np.allclose(
            np.asarray(metadata.T_world_from_camera),
            np.asarray(metadata.T_world_from_mount) @ np.asarray(camera.T_mount_from_camera),
            atol=1e-12, rtol=0,
        )
        assert np.array_equal(metadata.K, intrinsics(camera))

        # D04 maps far/background and near/far clipped samples to 0. Existing
        # optical_z_m keeps its old inclusive far-plane rule.
        values = np.asarray((camera.near * 0.5, camera.near, camera.far - 1e-3, camera.far, camera.far + 1), dtype=np.float64)
        native = np.full((camera.height, camera.width), camera.far, dtype=np.float64)
        native[0, :len(values)] = values
        d04 = optical_depth(
            native, metadata, native_convention='optical_z_m_far_invalid_v1',
        )
        legacy = optical_depth(native, metadata, native_convention='optical_z_m')
        assert d04.dtype == np.float32
        assert np.array_equal(
            d04[0, :len(values)],
            np.asarray((0.0, camera.near, camera.far - 1e-3, 0.0, 0.0), dtype=np.float32),
        )
        assert legacy[0, 3] == np.float32(camera.far)
        assert camera.identity_hash == replace(camera).identity_hash
        assert set(camera.to_mapping()) == {
            'schema_version', 'task_artifact_hash', 'camera_id', 'parent_frame',
            'T_parent_from_mount', 'T_mount_from_camera', 'width', 'height', 'fov_y',
            'near', 'far', 'rgb', 'depth', 'rgb_layout', 'rgb_dtype',
            'pixel_convention', 'depth_convention', 'capture_phase',
        }
    finally:
        candidate.env.close()


def test_d04_same_publication_identity_reset_and_failure_are_consumer_local(tmp_path):
    candidate = _candidate(tmp_path)
    env = candidate.env
    sessions = []
    try:
        source = DynamicCameraRenderSourceV1.from_runtime_source(candidate.source)
        initial_state = env.typed_state.view
        fixed_camera = fixed_calibration_camera(candidate, initial_state)
        mounted_camera = mounted_hand_camera(candidate, initial_state)
        fixed = create_dynamic_camera_session(
            fixed_camera, d04_execution(fixed_camera.camera_id), source=source,
            initial_state=initial_state, manifest=dynamic_rgbd_render_manifest(),
        )
        sibling = create_dynamic_camera_session(
            mounted_camera, d04_execution(mounted_camera.camera_id), source=source,
            initial_state=initial_state, manifest=dynamic_rgbd_render_manifest(),
        )
        sessions.extend((fixed, sibling))

        fixed_initial = fixed.capture(initial_state)
        mounted_initial = sibling.capture(initial_state)
        for observation in (fixed_initial, mounted_initial):
            assert observation.rgb.shape == (CAMERA_HEIGHT, CAMERA_WIDTH, 3)
            assert observation.rgb.dtype == np.float32
            assert observation.depth.shape == (CAMERA_HEIGHT, CAMERA_WIDTH)
            assert observation.depth.dtype == np.float32
            assert np.isfinite(observation.depth).all()
            assert np.all(observation.depth >= 0)
            assert np.any(observation.depth == 0)
            assert observation.capture_identity.state_boundary.boundary_id == initial_state.boundary.boundary_id
            assert observation.segmentation is None
            assert set(observation.capture_identity.modalities) == {'rgb', 'depth'}
            assert observation.metadata.capture_control_step == initial_state.boundary.control_step
            assert observation.metadata.capture_simulation_time == initial_state.sample_clock.simulation_time_s
        assert fixed.consumer_id != sibling.consumer_id
        assert fixed.last_sync.state_boundary.boundary_id == sibling.last_sync.state_boundary.boundary_id

        joints, hand_pose = _typed_hand_and_joints(env)
        target = type(hand_pose)(
            (hand_pose.position[0] + 0.02, *hand_pose.position[1:]), hand_pose.quaternion_wxyz,
        )
        env.step(_request(candidate.controller_binding_plan, target, 1.0))
        moved_state = env.typed_state.view
        with patch.object(fixed._renderer, 'render', side_effect=RuntimeError('injected renderer failure')):
            with pytest.raises(RuntimeError, match='injected renderer failure'):
                fixed.capture(moved_state)
        # A failed capture returned no stale observation; the sibling remains usable.
        mounted_moved = sibling.capture(moved_state)
        fixed_moved = fixed.capture(moved_state)
        assert fixed_moved.capture_identity.state_boundary.boundary_id == moved_state.boundary.boundary_id
        assert mounted_moved.capture_identity.state_boundary.boundary_id == moved_state.boundary.boundary_id

        env.reset()
        reset_state = env.typed_state.view
        fixed_reset = fixed.capture(reset_state)
        sibling_reset = sibling.capture(reset_state)
        assert fixed_reset.capture_identity.identity_hash != fixed_moved.capture_identity.identity_hash
        assert sibling_reset.capture_identity.identity_hash != mounted_moved.capture_identity.identity_hash
        assert fixed_reset.capture_identity.state_boundary.boundary_id == reset_state.boundary.boundary_id
        assert sibling_reset.capture_identity.state_boundary.boundary_id == reset_state.boundary.boundary_id
        for session in (fixed, sibling):
            with pytest.raises(ValueError, match='previous episode'):
                session.capture(moved_state)

        fixed.close()
        fixed.close()
        with pytest.raises(RuntimeError, match='closed'):
            fixed.capture(reset_state)
        assert sibling.capture(reset_state).rgb.shape == (CAMERA_HEIGHT, CAMERA_WIDTH, 3)
    finally:
        for session in sessions:
            session.close()
        env.close()


def test_d04_entity_segmentation_mapping_contract_and_publication_binding(tmp_path):
    candidate = _candidate(tmp_path, horizon=8)
    env = candidate.env
    session = None
    try:
        source = DynamicCameraRenderSourceV1.from_runtime_source(candidate.source)
        state = env.typed_state.view
        camera = fixed_calibration_camera(candidate, state)
        renderer = RendererSelectionV1(
            'renderer-selection-v1', 'mujoco', 'native-opengl',
            D04_ENTITY_SEGMENTATION_PROFILE, None,
        )
        execution = ExecutionSpecV1(
            'execution-spec-v1', 'geophys', 'cpu', D03_PHYSICS_PROFILE,
            32, 'best_effort', renderer, physics_device='cpu:0',
        )
        manifest = dynamic_entity_instance_segmentation_manifest()
        claims = {claim.name for claim in manifest.capabilities}
        assert claims == {'rgb_camera', 'depth_camera', 'entity_instance_segmentation'}
        admit_dynamic_camera(camera, execution, source=source, manifest=manifest)

        rgb_only = replace(camera, camera_id='d04-segmentation-rgb-only-v1', depth=False)
        rgb_only_execution = replace(
            execution,
            render_default=replace(renderer),
            camera_overrides=(),
        )
        # The selection profile makes the extra modality mandatory; the old
        # CameraGeometry v0 remains an RGB/Depth-only value.
        with pytest.raises(CapabilityAdmissionError, match='requires RGB and Depth'):
            admit_dynamic_camera(rgb_only, rgb_only_execution, source=source, manifest=manifest)

        geom_labels, label_entries = _resolve_canonical_entity_geometry_labels(
            (0, 1, 1),
            (('panda-main', 1),),
            ('panda-main',),
        )
        assert geom_labels == {0: 0, 1: 1, 2: 1}
        assert tuple((item.label, item.entity_id) for item in label_entries) == ((1, 'panda-main'),)
        with pytest.raises(ValueError, match='no Canonical Frame mapping'):
            _resolve_canonical_entity_geometry_labels((7,), (), ('panda-main',))
        with pytest.raises(ValueError, match='only the canonical world Frame'):
            _resolve_canonical_entity_geometry_labels((0,), (('panda-main', 0),), ('panda-main',))
        with pytest.raises(ValueError, match='ambiguous Canonical Entity mapping'):
            _resolve_canonical_entity_geometry_labels(
                (1,), (('panda-main', 1), ('square-peg-instance', 1)),
                ('panda-main', 'square-peg-instance'),
            )
        with pytest.raises(ValueError, match='positive uint32'):
            CanonicalEntityLabelV1(0, 'panda-main').validate()

        session = create_dynamic_camera_session(
            camera, execution, source=source, initial_state=state, manifest=manifest,
        )
        import mujoco
        with (
            patch.object(type(env.controller), 'compute', side_effect=AssertionError('capture called Controller')) as compute,
            patch.object(type(env.session), 'step', side_effect=AssertionError('capture stepped Provider')) as step,
            patch.object(mujoco, 'mj_step', side_effect=AssertionError('capture advanced MuJoCo')) as mj_step,
            patch.object(mujoco, 'mj_forward', side_effect=AssertionError('capture forwarded MuJoCo')) as mj_forward,
        ):
            observation = session.capture(state)
        compute.assert_not_called()
        step.assert_not_called()
        mj_step.assert_not_called()
        mj_forward.assert_not_called()

        segmentation = observation.segmentation
        assert isinstance(segmentation, CanonicalEntityInstanceSegmentationV1)
        assert segmentation.mask.shape == (CAMERA_HEIGHT, CAMERA_WIDTH)
        assert segmentation.mask.dtype == np.uint32
        assert not segmentation.mask.flags.writeable
        assert segmentation.background_label == 0
        assert segmentation.mask.flags.c_contiguous
        assert np.any(segmentation.mask == 0)
        assert set(np.unique(segmentation.mask).tolist()).issubset(
            {0, *(item.label for item in segmentation.label_map.labels)}
        )
        mapped_entities = {item.entity_id for item in segmentation.label_map.labels}
        assert {'panda-main', 'square-peg-instance'}.issubset(mapped_entities)
        identity = observation.capture_identity
        label_map = segmentation.label_map
        assert set(identity.modalities) == {'rgb', 'depth', 'entity_instance_segmentation'}
        assert label_map.capture_identity_hash == identity.identity_hash
        assert label_map.scene_instance_id == identity.state_boundary.scene_instance_id
        assert label_map.state_boundary_id == state.boundary.boundary_id
        assert label_map.state_revision == state.boundary.state_revision
        assert label_map.control_step == state.boundary.control_step
        assert label_map.simulation_time_s == state.sample_clock.simulation_time_s
        assert label_map.render_source_identity_hash == source.identity_hash

        invalid_label = max(item.label for item in label_map.labels) + 1
        invalid_mask = np.full(segmentation.mask.shape, invalid_label, dtype=np.uint32)
        with pytest.raises(ValueError, match='absent from its label map'):
            CanonicalEntityInstanceSegmentationV1(
                'canonical-entity-instance-segmentation-v1', invalid_mask, 0, label_map,
            )
        stale_map = replace(label_map, scene_instance_id='stale-scene-instance')
        stale_segmentation = replace(segmentation, label_map=stale_map)
        with pytest.raises(ValueError, match='different state publications'):
            CanonicalCameraObservation(
                observation.rgb, observation.depth, observation.metadata,
                observation.capture_identity, stale_segmentation,
            )

        env.reset()
        reset_state = env.typed_state.view
        reset_observation = session.capture(reset_state)
        assert reset_observation.capture_identity.state_boundary.boundary_id == reset_state.boundary.boundary_id
        assert reset_observation.capture_identity.identity_hash != observation.capture_identity.identity_hash
        with pytest.raises(ValueError, match='previous episode'):
            session.capture(state)
    finally:
        if session is not None:
            session.close()
        env.close()
