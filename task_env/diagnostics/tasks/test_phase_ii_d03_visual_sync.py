"""Defect-sensitive S1 coverage for the first D03 dynamic visual consumer."""

from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from task_env.artifacts import CapabilityAdmissionError, PoseWorld, TypedFrameStateValue
from task_env.controllers.canonical.position_profile import PandaPositionServoProfileV1
from task_env.diagnostics.tasks.c02b_position_candidate import build_position_candidate
from task_env.diagnostics.tasks.c02b_position_s2_probe import _request, _typed_hand_and_joints
from task_env.diagnostics.tasks.d03_visual_sync_s2_probe import _camera, _execution
from task_env.render.camera import (
    DynamicCameraRenderSourceV1,
    create_dynamic_camera_session,
    project_render_state_v1,
)
from task_env.runtime.sessions.source import lower_mujoco_scene_source


def _candidate(tmp_path: Path, *, horizon=3):
    candidate = build_position_candidate(tmp_path / 'position-source', provider='geophys', horizon=horizon)
    candidate.env.reset()
    return candidate


def _same_step_pose_publication(source, state, *, joint_key=('panda-main', 'joint1'), delta=0.1):
    """Build one valid synthetic Scene-v3 publication at the same outer step."""

    import mujoco

    xml, assets = lower_mujoco_scene_source(
        source.scene_source, source.scene_definition, source.source_closure_digest,
    )
    model = mujoco.MjModel.from_xml_string(xml, assets=assets)
    data = mujoco.MjData(model)
    bindings = {(item.entity_id, item.joint_id): item for item in source.joint_bindings}
    for value in state.joints:
        binding = bindings[(value.entity_id, value.joint_id)]
        joint_id = model.joint(binding.native_joint_name).id
        data.qpos[int(model.jnt_qposadr[joint_id])] = float(value.position[0])
    changed_binding = bindings[joint_key]
    changed_joint = model.joint(changed_binding.native_joint_name).id
    changed_address = int(model.jnt_qposadr[changed_joint])
    data.qpos[changed_address] += delta
    mujoco.mj_kinematics(model, data)
    changed_joints = tuple(
        replace(item, position=(float(item.position[0]) + delta,))
        if (item.entity_id, item.joint_id) == joint_key else item
        for item in state.joints
    )
    changed_frames = []
    frame_bindings = {(item.entity_id, item.frame_id): item for item in source.frame_bindings}
    for item in state.frames:
        key = (item.frame.entity_id, item.frame.frame_id)
        body_id = model.body(frame_bindings[key].native_body_name).id
        pose = PoseWorld(
            tuple(float(value) for value in data.xpos[body_id]),
            tuple(float(value) for value in data.xquat[body_id]),
        )
        changed_frames.append(TypedFrameStateValue('typed-frame-state-v1', item.frame, pose))
    return replace(
        state,
        boundary=replace(state.boundary, state_revision=state.boundary.state_revision + 1),
        joints=changed_joints,
        frames=tuple(changed_frames),
    )


def test_d03_admission_and_missing_mapping_reject_before_native_construction(tmp_path):
    candidate = _candidate(tmp_path)
    try:
        source = DynamicCameraRenderSourceV1.from_runtime_source(candidate.source)
        camera = _camera(candidate)
        execution = _execution()
        state = candidate.env.typed_state.view

        import task_env.render.camera.mujoco as mujoco_camera
        real_session = mujoco_camera.MuJoCoDynamicCameraSession
        constructed = []

        def forbidden_construction(*args, **kwargs):
            constructed.append(True)
            raise AssertionError('native camera construction happened before D03 preflight')

        with patch.object(mujoco_camera, 'MuJoCoDynamicCameraSession', forbidden_construction):
            with pytest.raises(ValueError, match='Frame identities'):
                create_dynamic_camera_session(
                    camera, execution, source=replace(source, frame_bindings=source.frame_bindings[:-1]),
                    initial_state=state,
                )
            with pytest.raises(CapabilityAdmissionError, match='TaskArtifact linkage'):
                create_dynamic_camera_session(
                    replace(camera, task_artifact_hash='f' * 64), execution,
                    source=source, initial_state=state,
                )
            bad_execution = replace(execution, physics_provider='mujoco')
            with pytest.raises(CapabilityAdmissionError, match='admits only GeoPhys CPU'):
                create_dynamic_camera_session(
                    camera, bad_execution, source=source, initial_state=state,
                )
            with pytest.raises(CapabilityAdmissionError, match='missing D03 dynamic render capability.*depth_camera'):
                create_dynamic_camera_session(
                    replace(camera, depth=True), execution, source=source, initial_state=state,
                )
        assert constructed == []
        assert real_session is mujoco_camera.MuJoCoDynamicCameraSession

        wrong_scene = replace(source, scene_identity_hash='0' * 64)
        with pytest.raises(ValueError, match='Scene identity mismatch'):
            project_render_state_v1(wrong_scene, state)
    finally:
        candidate.env.close()


def test_d03_versions_are_independent_per_consumer_and_reset_is_resynchronized(tmp_path):
    candidate = _candidate(tmp_path)
    env = candidate.env
    consumers = []
    try:
        source = DynamicCameraRenderSourceV1.from_runtime_source(candidate.source)
        camera = _camera(candidate)
        execution = _execution()
        reset_state = env.typed_state.view
        first = create_dynamic_camera_session(camera, execution, source=source, initial_state=reset_state)
        second = create_dynamic_camera_session(camera, execution, source=source, initial_state=reset_state)
        consumers.extend((first, second))

        assert first.consumer_id != second.consumer_id
        assert first.static_geometry_build_count == second.static_geometry_build_count == 1
        assert first.last_consumed_publication_version == second.last_consumed_publication_version
        assert first.last_consumed_transform_version == second.last_consumed_transform_version
        hand_binding = next(
            item for item in first.visual_instance_bindings
            if (item.entity_id, item.frame_id) == ('panda-main', 'hand')
        )
        assert hand_binding.native_body_name == 'hand'
        assert hand_binding.render_geometry_names

        # A valid same-step publication changes a canonical scalar joint and
        # its linked Frame poses while retaining the evaluation control step.
        reset_rgb = first.capture(reset_state).rgb
        same_step = _same_step_pose_publication(source, reset_state)
        old_second_publication = second.last_consumed_publication_version
        first_same_step = first.sync_state(same_step)
        assert first_same_step.publication_updated is True
        assert first_same_step.transforms_updated is True
        assert first_same_step.state_boundary.control_step == reset_state.boundary.control_step
        assert second.last_consumed_publication_version == old_second_publication
        same_step_rgb = first.capture(same_step).rgb
        assert (reset_rgb != same_step_rgb).any()
        second_same_step = second.sync_state(same_step)
        assert second_same_step.publication_updated is True
        assert second_same_step.transforms_updated is True
        assert second_same_step.publication_version == first_same_step.publication_version

        stale_value_change = replace(
            same_step,
            joints=tuple(
                replace(item, position=(item.position[0] + 0.01,))
                if (item.entity_id, item.joint_id) == ('panda-main', 'joint1') else item
                for item in same_step.joints
            ),
        )
        with pytest.raises(ValueError, match='without a new publication version'):
            first.sync_state(stale_value_change)

        joints, hand_pose = _typed_hand_and_joints(env)
        target = type(hand_pose)(
            (hand_pose.position[0] + 0.02, *hand_pose.position[1:]), hand_pose.quaternion_wxyz,
        )
        action = _request(candidate.controller_binding_plan, target, 1.0)
        env.step(action)
        moved_state = env.typed_state.view
        first_moved = first.sync_state(moved_state)
        old_second_transform = second.last_consumed_transform_version
        assert first_moved.transforms_updated is True
        assert second.last_consumed_transform_version == old_second_transform
        second_moved = second.sync_state(moved_state)
        assert second_moved.transforms_updated is True
        assert first_moved.transform_version == second_moved.transform_version
        assert first_moved.geometry_version == second_moved.geometry_version
        assert first.static_geometry_build_count == second.static_geometry_build_count == 1

        before_capture = (env.state.control_step, env.state.simulation_time)
        counters = {'compute': 0, 'provider_step': 0}
        controller_type, session_type = type(env.controller), type(env.session)
        original_compute, original_step = controller_type.compute, session_type.step

        def counted_compute(controller, *args, **kwargs):
            if controller is env.controller:
                counters['compute'] += 1
            return original_compute(controller, *args, **kwargs)

        def counted_step(session, *args, **kwargs):
            if session is env.session:
                counters['provider_step'] += 1
            return original_step(session, *args, **kwargs)

        with patch.object(controller_type, 'compute', counted_compute), patch.object(session_type, 'step', counted_step):
            first.capture(moved_state)
            first.sync_state(moved_state)
        assert before_capture == (env.state.control_step, env.state.simulation_time)
        assert counters == {'compute': 0, 'provider_step': 0}

        # Reset creates a new boundary identity even with the same fixed sample.
        env.reset()
        after_reset = env.typed_state.view
        first_reset = first.sync_state(after_reset)
        second_reset = second.sync_state(after_reset)
        assert first_reset.publication_updated is True
        assert second_reset.publication_updated is True
        assert first_reset.state_boundary.episode_id != first_moved.state_boundary.episode_id
        assert first_reset.geometry_version == second_reset.geometry_version
        assert first.static_geometry_build_count == second.static_geometry_build_count == 1

        first.close()
        first.close()
        with pytest.raises(RuntimeError, match='closed'):
            first.capture(after_reset)
        # Closing one consumer does not invalidate its sibling.
        assert second.capture(after_reset).rgb.shape == (120, 160, 3)
    finally:
        for consumer in consumers:
            consumer.close()
        env.close()
