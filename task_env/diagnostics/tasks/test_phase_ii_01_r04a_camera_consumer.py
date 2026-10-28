"""Provider-free S1 for the opt-in Position camera observation consumer."""

import json
import os
import shutil
import sys
from dataclasses import replace
from pathlib import Path

import h5py
import numpy as np
import pytest

from task_env.artifacts.contracts import FrameReference, PoseWorld
from task_env.controllers.canonical.contracts import (
    CanonicalControlTarget,
    ControlGroupActionV1,
    GripperControlTarget,
    PositionControlTargetV1,
    StructuredActionRequestV1,
)
from task_env.artifacts.state import (
    CanonicalStateViewV1,
    StateBoundaryIdentity,
    StateSampleClock,
    TypedFrameStateValue,
)
from task_env.diagnostics.tasks.c02b_position_candidate import build_position_candidate
from task_env.observations.canonical_camera import (
    CanonicalCameraObservation,
    CanonicalEntityInstanceSegmentationV1,
    CanonicalEntityLabelMapV1,
    CanonicalEntityLabelV1,
    CameraMountRequestV1,
    CameraObservationConfigV1,
    FIXED_CAMERA_ID,
    HAND_CAMERA_ID,
    resolve_camera,
)
from task_env.observations.capture import DynamicCameraObservationConsumerV1
from task_env.recorders import (
    RecorderConfig,
    TransitionRecorder,
    load_camera_observations_h5,
    load_structured_control_records_h5,
    load_structured_training_actions_h5,
)
from task_env.trajectory.canonical.episode import StructuredControlTransitionV1
from task_env.trajectory.canonical.episode import make_episode_end_v1


IDENTITY = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)


def _config(*, width=2, height=3):
    return CameraObservationConfigV1(
        "camera-observation-consumer-v1",
        (
            CameraMountRequestV1("camera-mount-request-v1", FIXED_CAMERA_ID, "world", IDENTITY),
            CameraMountRequestV1("camera-mount-request-v1", HAND_CAMERA_ID, "hand", IDENTITY),
        ),
        width=width,
        height=height,
    )


def _state(candidate, step=0, *, state_revision=None):
    revision = step if state_revision is None else state_revision
    boundary = StateBoundaryIdentity(
        "state-boundary-identity-v1", "episode-r04a", "reset-" + "a" * 64,
        candidate.scene.identity_hash, "scene-instance-r04a", "materialization-r04a",
        step, revision,
    )
    clock = StateSampleClock("state-sample-clock-v1", "evaluation_boundary", step, step * 0.01)
    frame = TypedFrameStateValue(
        "typed-frame-state-v1", FrameReference("panda-main", "hand"),
        PoseWorld((0.0, 0.0, 0.5), (1.0, 0.0, 0.0, 0.0)),
    )
    return CanonicalStateViewV1(
        "canonical-state-v1", "SI_right_handed_z_up_wxyz", boundary, clock, (), (frame,),
    )


def _capture(camera, execution, source, state, manifest, config):
    identity = source.capture_identity(
        camera, execution, manifest, state,
        additional_modalities=("entity_instance_segmentation",),
    )
    calibration = resolve_camera(camera, state)
    boundary = state.boundary
    label_map = CanonicalEntityLabelMapV1(
        "canonical-entity-label-map-v1",
        identity.task_artifact_hash,
        boundary.scene_identity_hash,
        identity.render_source_identity_hash,
        camera.camera_id,
        boundary.scene_instance_id,
        boundary.provider_materialization_id,
        boundary.episode_id,
        boundary.reset_sample_id,
        boundary.boundary_id,
        boundary.state_revision,
        boundary.control_step,
        identity.sample_clock.simulation_time_s,
        identity.identity_hash,
        (CanonicalEntityLabelV1(1, "panda-main"),),
    )
    mask = np.zeros((config.height, config.width), dtype=np.uint32)
    segmentation = CanonicalEntityInstanceSegmentationV1(
        "canonical-entity-instance-segmentation-v1", mask, 0, label_map,
    )
    return CanonicalCameraObservation(
        np.full((config.height, config.width, 3), 0.5, dtype=np.float32),
        np.full((config.height, config.width), 0.75, dtype=np.float32),
        calibration, identity, segmentation,
    )


def _record_state_info(state, captures, *, reset=False, clock_override=None):
    from task_env.observations.canonical_camera.consumer import camera_observation_boundary_from_captures

    info = {
        "state_boundary_identity": state.boundary.to_mapping(),
        "state_boundary_id": state.boundary.boundary_id,
        "state_sample_clock": (clock_override or state.sample_clock).to_mapping(),
        "source_closure_digest": "d" * 64,
    }
    if not reset:
        info.update({
            "control_step": state.boundary.control_step,
            "simulation_time_s": state.sample_clock.simulation_time_s,
        })
    info["camera_observation_v1"] = camera_observation_boundary_from_captures(captures).to_mapping()
    return info


def _camera_h5_observation(state, captures, *, corrupt_state_digest=False):
    digest = bytes.fromhex(state.boundary.boundary_id.removeprefix("state-boundary-"))
    if corrupt_state_digest:
        digest = bytes((digest[0] ^ 1,)) + digest[1:]
    return {
        "state": {
            "value": np.asarray((state.boundary.control_step,), dtype=np.float32),
            "boundary_identity_sha256": np.frombuffer(digest, dtype=np.uint8).copy(),
        },
        "privileged_state": {},
        "rgb": {camera_id: capture.rgb for camera_id, capture in zip((FIXED_CAMERA_ID, HAND_CAMERA_ID), captures)},
        "depth": {camera_id: capture.depth for camera_id, capture in zip((FIXED_CAMERA_ID, HAND_CAMERA_ID), captures)},
        "entity_mask": {
            camera_id: capture.segmentation.mask
            for camera_id, capture in zip((FIXED_CAMERA_ID, HAND_CAMERA_ID), captures)
        },
    }


def _position_control(candidate, state, values, *, writer_id, controller_identity, plan_hash, source_closure_digest):
    components = ("x", "y", "z", "qw", "qx", "qy", "qz", "gripper")
    action_schema_id = "r04a-position-action-v1"
    arm_joint_order = tuple(f"joint{index}" for index in range(1, 8))
    arm_positions = {name: float(index) * 0.01 for index, name in enumerate(arm_joint_order)}
    target = PositionControlTargetV1(
        "position-control-target-v1", writer_id, controller_identity, plan_hash,
        source_closure_digest, state.boundary, state.sample_clock,
        CanonicalControlTarget(
            "canonical-control-v0", candidate.artifact.identity_hash, controller_identity,
            arm_joint_order, arm_positions, dict(arm_positions),
            GripperControlTarget("panda-main/gripper", 0.04, 10.0, 0.04),
        ),
    )
    groups = (
        ControlGroupActionV1(
            "control-group-action-v1", "panda-main", "arm", action_schema_id,
            tuple(float(value) for value in values[:7]),
        ),
        ControlGroupActionV1(
            "control-group-action-v1", "panda-main", "gripper", action_schema_id,
            (float(values[7]),),
        ),
    )
    request = StructuredActionRequestV1(
        "structured-action-request-v1", candidate.scene.identity_hash, plan_hash, groups,
    )
    target_mapping = target.to_mapping()
    canonical_control = target.target.to_mapping()
    return StructuredControlTransitionV1(
        "structured-control-transition-v1", request, ({
            "writer_id": writer_id,
            "action_schema_id": action_schema_id,
            "components": components,
            "groups": (
                {"entity_id": "panda-main", "group_id": "arm", "action_components": components[:7]},
                {"entity_id": "panda-main", "group_id": "gripper", "action_components": (components[7],)},
            ),
            "requested_action": {"mode": "absolute_pose", "reference": "world",
                                 "rotation_representation": "quaternion_wxyz", "values": tuple(values)},
            "canonical_action": {
                "schema_version": "canonical-action-v0",
                "interpreted_values": tuple(values),
                "position_target_v1": target_mapping,
                "position_target_identity_hash": target.identity_hash,
            },
            "controller_target": {
                "schema_version": canonical_control["schema_version"],
                "payload": canonical_control,
                "identity_hash": target.target.identity_hash,
            },
            "applied_control": {
                "schema_version": "applied-canonical-control-v0",
                "payload": {"acknowledged": True},
                "target_hash": target.target.identity_hash,
            },
        },),
    )


def _camera_h5_recorder(
    tmp_path, *, transition_count=0, bad_state_digest_at=None,
    reset_clock_seconds=None, transition_clock_seconds=None,
):
    """Build a provider-free T/T+1 Generic H5 v3 trajectory from real typed anchors."""
    from task_env.artifacts import ExecutionSpecV1, RendererSelectionV1
    from task_env.render.camera import (
        D03_PHYSICS_PROFILE,
        D04_ENTITY_SEGMENTATION_PROFILE,
        DynamicCameraRenderSourceV1,
        dynamic_entity_instance_segmentation_manifest,
    )

    config = _config(width=3, height=2)
    candidate = _candidate(tmp_path / "candidate", horizon=2)
    render_source = DynamicCameraRenderSourceV1.from_runtime_source(candidate.source)
    renderer = RendererSelectionV1(
        "renderer-selection-v1", "mujoco", "native-opengl", D04_ENTITY_SEGMENTATION_PROFILE, None,
    )
    execution = ExecutionSpecV1(
        "execution-spec-v1", "geophys", "cpu", D03_PHYSICS_PROFILE,
        31, "best_effort", renderer, physics_device="cpu:0",
    )
    manifest = dynamic_entity_instance_segmentation_manifest()
    states = tuple(_state(candidate, index) for index in range(transition_count + 1))
    captures_by_boundary = tuple(
        tuple(_capture(camera, execution, render_source, state, manifest, config)
              for camera in config.geometries(candidate.artifact.identity_hash))
        for state in states
    )
    observations = tuple(
        _camera_h5_observation(state, captures,
                               corrupt_state_digest=(index == bad_state_digest_at))
        for index, (state, captures) in enumerate(zip(states, captures_by_boundary, strict=True))
    )
    episode_id = states[0].boundary.episode_id
    writer_id = "panda-main-position-writer-v1"
    controller_identity = "c" * 64
    plan_hash = "b" * 64
    source_closure_digest = candidate.source.source_closure_digest
    components = ("x", "y", "z", "qw", "qx", "qy", "qz", "gripper")
    metadata = {
        "env_metadata": {
            "env_name": "SelectedReferenceEnv.PositionServoV1",
            "task_name": "r04a-synthetic-position",
            "task_version": "1",
            "scene_uid": candidate.scene.scene_id,
            "agent_uids": ("panda-main",),
            "action_schema": {
                "schema_id": "r04a-position-action-v1",
                "schema_version": "structured-action-schema-v1",
                "controller_kind": "delta_pose",
                "reference": "world",
                "components": components,
            },
            "observation_schema": {"leaf_specs": [
                {"path": "state.boundary_identity_sha256", "semantic": "state_boundary_identity_sha256"},
            ]},
            "reference_profile": {
                "writer_id": writer_id,
                "controller_identity": controller_identity,
                "control_binding_plan_identity_hash": plan_hash,
                "task_artifact_identity_hash": candidate.artifact.identity_hash,
                "scene_identity_hash": candidate.scene.identity_hash,
                "reset_sample_id": states[0].boundary.reset_sample_id,
                "source_closure_digest": source_closure_digest,
            },
        },
        "universal_action_schema": {
            "version": "r04a-position-universal-action-v1",
            "dimension": len(components),
            "components": components,
        },
        "camera_observation_contract_v1": config.to_mapping(),
    }
    reset_clock = states[0].sample_clock
    if reset_clock_seconds is not None:
        reset_clock = StateSampleClock(
            "state-sample-clock-v1", "evaluation_boundary", 0, reset_clock_seconds,
        )
    reset_info = _record_state_info(states[0], captures_by_boundary[0], reset=True, clock_override=reset_clock)
    recorder = TransitionRecorder(RecorderConfig(schema_version="v3", max_transitions=max(1, transition_count)))
    recorder.begin_episode(observations[0], reset_info, metadata)
    for index in range(transition_count):
        state = states[index + 1]
        clock = state.sample_clock
        if transition_clock_seconds is not None and index == 0:
            clock = StateSampleClock(
                "state-sample-clock-v1", "evaluation_boundary", index + 1, transition_clock_seconds,
            )
        info = _record_state_info(state, captures_by_boundary[index + 1], clock_override=clock)
        values = (0.1 + index * 0.01, 0.2, 0.3, 1.0, 0.0, 0.0, 0.0, 0.5)
        control = _position_control(
            candidate, states[index], values,
            writer_id=writer_id, controller_identity=controller_identity,
            plan_hash=plan_hash, source_closure_digest=source_closure_digest,
        )
        action = np.asarray(values, dtype=np.float32)
        recorder.append_transition(
            action, action, observations[index + 1], 0.0, False, False, False, info,
            structured_control=control,
        )
    end = make_episode_end_v1(
        episode_id=episode_id, final_boundary=transition_count, end_reason="external_stop",
        terminated=False, truncated=True, bootstrap_allowed=True, source="r04a-s1-test",
    )
    recorder.end_episode("external_stop", outcome=end.outcome)
    return recorder, candidate


class _FakeSession:
    def __init__(self, capture_fn):
        self.capture_fn = capture_fn
        self.capture_count = 0
        self.close_count = 0

    def capture(self, state):
        self.capture_count += 1
        return self.capture_fn(state)

    def close(self):
        self.close_count += 1


def _candidate(tmp_path, *, camera_config=None, horizon=2):
    return build_position_candidate(
        tmp_path / "position-source", provider="geophys", horizon=horizon,
        camera_observation_config=camera_config,
    )


def test_camera_contract_is_opt_in_and_capacity_is_arithmetic_only(tmp_path):
    config = _config()
    assert CameraObservationConfigV1.from_mapping(config.to_mapping()) == config
    production = _config(width=321, height=241)
    assert production.capacity(16) == {
        "boundary_count": 17,
        "public_bytes_per_boundary": 3_094_440,
        "recorded_bytes_per_boundary": 1_701_942,
        "public_total_bytes": 52_605_480,
        "recorded_total_bytes": 28_933_014,
        "public_budget_bytes": 64 * 1024 * 1024,
        "recording_budget_bytes": 128 * 1024 * 1024,
        "combined_payload_bytes": 81_538_494,
    }
    with pytest.raises(ValueError, match="horizon"):
        production.capacity(17)
    with pytest.raises(ValueError, match="canonical order"):
        CameraObservationConfigV1(
            "camera-observation-consumer-v1", tuple(reversed(config.cameras)), width=2, height=3,
        )
    from task_env.tasks.position_candidate import PositionCandidateEnv

    refused_workspace = tmp_path / "must-not-be-created"
    with pytest.raises(ValueError, match="horizon"):
        PositionCandidateEnv.from_reference_config({
            "horizon": 17,
            "source_workspace": refused_workspace,
            "camera_observation": production.to_mapping(),
        })
    assert not refused_workspace.exists()

    camera_candidate = _candidate(tmp_path / "camera", camera_config=production, horizon=16)
    try:
        env = camera_candidate.env
        assert tuple(env.observation_space.spaces) == (
            "state", "privileged_state", "rgb", "depth", "entity_mask",
        )
        assert env.observation_space.spaces["rgb"].spaces[FIXED_CAMERA_ID].shape == (241, 321, 3)
        assert env.observation_space.spaces["depth"].spaces[HAND_CAMERA_ID].dtype == np.dtype(np.float32)
        assert env.observation_space.spaces["entity_mask"].spaces[HAND_CAMERA_ID].dtype == np.dtype(np.uint32)
        declared = {item["path"] for item in env.metadata["observation_schema"]["leaf_specs"]}
        assert {f"rgb.{camera_id}" for camera_id in (FIXED_CAMERA_ID, HAND_CAMERA_ID)} <= declared
        assert {f"depth.{camera_id}" for camera_id in (FIXED_CAMERA_ID, HAND_CAMERA_ID)} <= declared
        assert {f"entity_mask.{camera_id}" for camera_id in (FIXED_CAMERA_ID, HAND_CAMERA_ID)} <= declared
        assert env.metadata["info_schema"]["camera_observation_v1"]["required"] is True
        assert env._camera_consumer is None
    finally:
        camera_candidate.env.close()

    state_only = _candidate(tmp_path / "state-only")
    try:
        assert tuple(state_only.env.observation_space.spaces) == ("state", "privileged_state")
        assert state_only.env.metadata.get("camera_observation_schema") is None
    finally:
        state_only.env.close()
    forbidden = [
        name for name in sys.modules
        if name == "mujoco" or name == "taichi" or name.startswith("taichi.")
        or name.startswith("GeoPhys.solvers") or name.startswith("GeoPhys.src.solvers")
    ]
    assert forbidden == []


def test_dynamic_consumer_caches_boundaries_and_closes_each_session_once(tmp_path):
    config = _config()
    candidate = _candidate(tmp_path)
    sessions = []
    try:
        def factory(camera, execution, *, source, initial_state, manifest):
            session = _FakeSession(
                lambda state: _capture(camera, execution, source, state, manifest, config)
            )
            sessions.append(session)
            return session

        consumer = DynamicCameraObservationConsumerV1(
            config=config, task_artifact_hash=candidate.artifact.identity_hash,
            runtime_source=candidate.source, horizon=2, session_factory=factory,
        )
        first_state = _state(candidate, 0)
        leaves, boundary = consumer.capture(first_state)
        repeated_leaves, repeated_boundary = consumer.capture(first_state)
        assert boundary == repeated_boundary
        assert leaves["rgb"][FIXED_CAMERA_ID] is repeated_leaves["rgb"][FIXED_CAMERA_ID]
        assert [item.capture_count for item in sessions] == [1, 1]
        assert tuple(leaves) == ("rgb", "depth", "entity_mask")
        assert leaves["rgb"][HAND_CAMERA_ID].dtype == np.dtype(np.float32)
        assert leaves["depth"][FIXED_CAMERA_ID].shape == (3, 2)
        assert leaves["entity_mask"][HAND_CAMERA_ID].dtype == np.dtype(np.uint32)

        next_leaves, next_boundary = consumer.capture(_state(candidate, 1))
        assert next_boundary.boundary_index == 1
        assert next_boundary.state_boundary_id != boundary.state_boundary_id
        assert [item.capture_count for item in sessions] == [2, 2]
        with pytest.raises(ValueError, match="contiguous"):
            consumer.capture(_state(candidate, 0, state_revision=9))
        consumer.close()
        consumer.close()
        assert [item.close_count for item in sessions] == [1, 1]
        assert next_leaves["rgb"][FIXED_CAMERA_ID].shape == (3, 2, 3)
    finally:
        candidate.env.close()


@pytest.mark.parametrize("drift", ("mount", "artifact", "render_source", "execution"))
def test_dynamic_consumer_rejects_capture_that_disagrees_with_actual_request(tmp_path, drift):
    config = _config()
    candidate = _candidate(tmp_path)
    sessions = []
    forged_context = {}
    try:
        def factory(camera, execution, *, source, initial_state, manifest):
            forged_camera, forged_source, forged_execution = camera, source, execution
            if drift == "mount":
                mount = [list(row) for row in camera.T_parent_from_mount]
                mount[0][3] += 0.2
                forged_camera = replace(camera, T_parent_from_mount=tuple(tuple(row) for row in mount))
            elif drift == "artifact":
                forged_source = replace(source, task_artifact_hash="a" * 64)
                forged_camera = replace(camera, task_artifact_hash="a" * 64)
            elif drift == "render_source":
                forged_source = replace(source, source_closure_digest="c" * 64)
            elif drift == "execution":
                forged_execution = replace(execution, provider_seed=32)
            else:
                raise AssertionError(drift)
            forged_context[drift] = (forged_camera, forged_source, forged_execution)
            session = _FakeSession(
                lambda state: _capture(
                    forged_camera, forged_execution, forged_source, state, manifest, config,
                )
            )
            sessions.append(session)
            return session

        consumer = DynamicCameraObservationConsumerV1(
            config=config,
            task_artifact_hash=candidate.artifact.identity_hash,
            runtime_source=candidate.source,
            horizon=2,
            session_factory=factory,
        )
        with pytest.raises(ValueError, match="request"):
            consumer.capture(_state(candidate, 0))
        assert len(sessions) == 2
        assert consumer._last_key is None
        assert consumer._last_leaves is None
        consumer.close()
        consumer.close()
        assert [item.close_count for item in sessions] == [1, 1]
    finally:
        candidate.env.close()


def test_dynamic_consumer_rejects_calibration_from_another_parent_frame_pose(tmp_path):
    config = _config()
    candidate = _candidate(tmp_path)
    sessions = []
    state = _state(candidate, 0)
    moved_hand = replace(
        state.frames[0],
        pose_world=PoseWorld((0.2, 0.0, 0.5), (1.0, 0.0, 0.0, 0.0)),
    )
    other_state = replace(state, frames=(moved_hand,))
    try:
        def factory(camera, execution, *, source, initial_state, manifest):
            def produce(current_state):
                capture = _capture(camera, execution, source, current_state, manifest, config)
                if camera.camera_id == HAND_CAMERA_ID:
                    return replace(capture, metadata=resolve_camera(camera, other_state))
                return capture
            session = _FakeSession(produce)
            sessions.append(session)
            return session

        consumer = DynamicCameraObservationConsumerV1(
            config=config,
            task_artifact_hash=candidate.artifact.identity_hash,
            runtime_source=candidate.source,
            horizon=2,
            session_factory=factory,
        )
        with pytest.raises(ValueError, match="calibration"):
            consumer.capture(state)
        assert consumer._last_key is None
        assert consumer._last_leaves is None
        consumer.close()
        assert [item.close_count for item in sessions] == [1, 1]
    finally:
        candidate.env.close()


def test_partial_camera_construction_closes_created_session_once(tmp_path):
    config = _config()
    candidate = _candidate(tmp_path)
    sessions = []
    calls = 0
    try:
        def factory(camera, execution, *, source, initial_state, manifest):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("injected second-camera construction failure")

            class _CloseFailureSession(_FakeSession):
                def close(self):
                    self.close_count += 1
                    raise OSError("injected renderer close failure")

            session = _CloseFailureSession(
                lambda state: _capture(camera, execution, source, state, manifest, config)
            )
            sessions.append(session)
            return session

        consumer = DynamicCameraObservationConsumerV1(
            config=config, task_artifact_hash=candidate.artifact.identity_hash,
            runtime_source=candidate.source, horizon=2, session_factory=factory,
        )
        with pytest.raises(RuntimeError, match="second-camera") as caught:
            consumer.capture(_state(candidate, 0))
        assert any("renderer close failure" in note for note in caught.value.__notes__)
        consumer.close()
        assert [item.close_count for item in sessions] == [1]
    finally:
        candidate.env.close()


def test_post_step_camera_observation_failure_keeps_progress_fault_and_closes_once(monkeypatch):
    from types import MethodType, SimpleNamespace
    from task_env.runtime.sessions import control as control_sessions
    from task_env.tasks.reference_env import SelectedReferenceEnv

    before = SimpleNamespace(control_step=0, simulation_time=0.0)
    after = SimpleNamespace(control_step=1, simulation_time=0.01)

    class _CloseOnce:
        close_count = 0

        def close(self):
            self.close_count += 1

    camera_consumer = _CloseOnce()
    selected = SimpleNamespace(
        _execution_fault=None, _stopped=False, _closed=False, horizon=4,
        position_profile=True, dual_entity_position=False,
        session=SimpleNamespace(snapshot=lambda: after), controller=object(),
        position_profiles=(SimpleNamespace(requirements=object()),),
        position_plan=object(), typed_state=object(), position_scene=object(),
        position_joint_bindings={}, position_frame_bindings={}, state=before,
        artifact=SimpleNamespace(timebase=SimpleNamespace(control_substeps=5, control_dt=0.01)),
        recorder=None, _camera_consumer=camera_consumer,
    )
    selected._latch_fault = MethodType(SelectedReferenceEnv._latch_fault, selected)
    selected._position_requirements = MethodType(
        SelectedReferenceEnv._position_requirements, selected,
    )
    selected._recording_counts = SelectedReferenceEnv._recording_counts
    selected._fault_transition_status = MethodType(
        SelectedReferenceEnv._fault_transition_status.__func__, selected,
    )
    selected._close_camera_consumer = MethodType(
        SelectedReferenceEnv._close_camera_consumer, selected,
    )

    def fail_observation(_state):
        raise RuntimeError("injected camera observation failure")

    selected.observation = fail_observation
    monkeypatch.setattr(
        control_sessions,
        "execute_position_control_interval",
        lambda *_args, **_kwargs: (object(), object(), object(), after, object()),
    )
    with pytest.raises(RuntimeError, match="camera observation failure"):
        SelectedReferenceEnv._step_position_profile(selected, object())
    assert selected.state is after
    assert selected._execution_fault.phase == "position_observation"
    assert selected._execution_fault.physical_progress == "advanced"
    assert selected._stopped is True
    assert selected._camera_consumer is None
    assert camera_consumer.close_count == 1


def test_v3_camera_metadata_extension_roundtrip_and_mask_guard(tmp_path):
    # Avoid a height-three synthetic image: the legacy RGB quantizer accepts
    # either HWC or CHW arrays and that single-axis size is intentionally
    # ambiguous without production camera dimensions.
    recorder, candidate = _camera_h5_recorder(tmp_path, transition_count=0)
    try:
        config = _config(width=3, height=2)
        path = recorder.save_h5(tmp_path, "synthetic-camera-v3")
        camera = load_camera_observations_h5(path)
        boundary = camera["boundaries"][0]
        from task_env.observations.canonical_camera.consumer import CameraObservationBoundaryV1

        missing_modality = boundary.to_mapping()
        missing_modality["captures"][0]["capture_identity"]["modalities"] = ["rgb", "depth"]
        with pytest.raises(ValueError, match="must include RGB, depth, and Entity segmentation"):
            CameraObservationBoundaryV1.from_mapping(missing_modality)
        stale_label = boundary.to_mapping()
        stale_label["captures"][0]["label_map"]["scene_instance_id"] = "another-scene-instance"
        with pytest.raises(ValueError, match="stale or belongs to another capture"):
            CameraObservationBoundaryV1.from_mapping(stale_label)
        wrong_calibration = boundary.to_mapping()
        wrong_calibration["captures"][0]["calibration"]["capture_control_step"] = 1
        with pytest.raises(ValueError, match="boundary disagree"):
            CameraObservationBoundaryV1.from_mapping(wrong_calibration)
        assert camera["schema_version"] == "camera-observation-boundary-v1"
        assert camera["recording_binding_schema_version"] == "camera-recording-binding-v1"
        assert camera["observation_count"] == 1 and camera["transition_count"] == 0
        assert boundary.state_boundary_id == camera["recording_binding"]["boundaries"][0]["state_boundary_id"]
        assert load_structured_control_records_h5(path)["observation_count"] == 1
        assert load_structured_training_actions_h5(path) == ()
        evidence_dir = os.environ.get("R04A_EVIDENCE_DIR")
        if evidence_dir:
            Path(evidence_dir).mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, Path(evidence_dir) / "valid-zero-transition.h5")
        with h5py.File(path, "r+") as h5:
            assert h5["obs/rgb/" + FIXED_CAMERA_ID].shape == (1, 3, 2, 3)
            assert h5["obs/rgb/" + FIXED_CAMERA_ID].dtype == np.dtype(np.uint8)
            assert h5["obs/depth/" + HAND_CAMERA_ID].dtype == np.dtype(np.float32)
            assert h5["obs/entity_mask/" + HAND_CAMERA_ID].dtype == np.dtype(np.uint32)
            h5["obs/entity_mask/" + HAND_CAMERA_ID][0, 0, 0] = 7
        with pytest.raises(ValueError, match="mask|LabelMap"):
            load_camera_observations_h5(path)
    finally:
        candidate.env.close()


@pytest.mark.parametrize(
    ("case", "kwargs", "message"),
    (
        ("wrong_state_digest", {"bad_state_digest_at": 0}, "state observation digest"),
        ("wrong_reset_clock", {"reset_clock_seconds": 0.125}, "independent reset/transition identity and clock"),
        ("wrong_transition_clock", {"transition_count": 1, "transition_clock_seconds": 0.125},
         "recorded info simulation clock"),
    ),
)
def test_camera_h5_writer_rejects_independent_state_clock_mismatches_and_cleans_temp(
    tmp_path, case, kwargs, message,
):
    recorder, candidate = _camera_h5_recorder(tmp_path / case, **kwargs)
    directory = tmp_path / (case + "-out")
    try:
        with pytest.raises(ValueError, match=message):
            recorder.save_h5(directory, "rejected-camera-recording")
        assert not (directory / "rejected-camera-recording.h5").exists()
        assert not (directory / ".rejected-camera-recording.h5.tmp").exists()
    finally:
        candidate.env.close()


def _replace_json_dataset(h5, dataset_path, value):
    del h5[dataset_path]
    h5.create_dataset(
        dataset_path,
        data=np.asarray(json.dumps(value, sort_keys=True), dtype=h5py.string_dtype(encoding="utf-8")),
    )


def test_camera_h5_reader_rejects_independent_state_episode_and_clock_mismatches(tmp_path):
    recorder, candidate = _camera_h5_recorder(tmp_path / "base", transition_count=0)
    try:
        source = recorder.save_h5(tmp_path, "camera-reader-negative-base")
        evidence_dir = os.environ.get("R04A_EVIDENCE_DIR")
        if evidence_dir:
            root = Path(evidence_dir)
            root.mkdir(parents=True, exist_ok=True)
        cases = (
            ("wrong-state-boundary.h5", "stored state digest", "state"),
            ("wrong-episode-outcome.h5", "finalized typed EpisodeOutcome", "episode"),
            ("wrong-clock-anchor.h5", "stored state digest and record clock", "clock"),
        )
        for filename, message, kind in cases:
            case_path = tmp_path / filename
            shutil.copy2(source, case_path)
            with h5py.File(case_path, "r+") as h5:
                if kind == "state":
                    row = np.asarray(h5["obs/state/boundary_identity_sha256"][0])
                    row[0] ^= np.uint8(1)
                    h5["obs/state/boundary_identity_sha256"][0] = row
                elif kind == "episode":
                    outcome = json.loads(h5["meta/episode_outcome_v1_json"][()].decode("utf-8"))
                    outcome["episode_id"] = "another-finalized-episode"
                    _replace_json_dataset(h5, "meta/episode_outcome_v1_json", outcome)
                else:
                    binding = json.loads(h5["meta/camera_recording_binding_v1_json"][()].decode("utf-8"))
                    binding["boundaries"][0]["state_sample_clock"]["simulation_time_s"] = 0.125
                    _replace_json_dataset(h5, "meta/camera_recording_binding_v1_json", binding)
            with pytest.raises(ValueError, match=message):
                load_camera_observations_h5(case_path)
            if evidence_dir:
                shutil.copy2(case_path, root / filename)
        missing_path = tmp_path / "missing-recording-binding.h5"
        shutil.copy2(source, missing_path)
        with h5py.File(missing_path, "r+") as h5:
            del h5["meta/camera_recording_binding_v1_json"]
        with pytest.raises(ValueError, match="extension is incomplete"):
            load_camera_observations_h5(missing_path)

        geometry_path = tmp_path / "wrong-authored-geometry.h5"
        shutil.copy2(source, geometry_path)
        with h5py.File(geometry_path, "r+") as h5:
            contract = json.loads(h5["meta/camera_observation_contract_v1_json"][()].decode("utf-8"))
            contract["cameras"][0]["T_parent_from_mount"][0][3] += 0.2
            _replace_json_dataset(h5, "meta/camera_observation_contract_v1_json", contract)
        with pytest.raises(ValueError, match="another CameraGeometry"):
            load_camera_observations_h5(geometry_path)

        shape_path = tmp_path / "wrong-modality-shape.h5"
        shutil.copy2(source, shape_path)
        with h5py.File(shape_path, "r+") as h5:
            depth_path = "obs/depth/" + HAND_CAMERA_ID
            del h5[depth_path]
            h5.create_dataset(depth_path, data=np.zeros((1, 1, 1), dtype=np.float32))
        with pytest.raises(ValueError, match="schema mismatch"):
            load_camera_observations_h5(shape_path)
        if evidence_dir:
            shutil.copy2(geometry_path, Path(evidence_dir) / "wrong-authored-geometry.h5")
            shutil.copy2(shape_path, Path(evidence_dir) / "wrong-modality-shape.h5")
    finally:
        candidate.env.close()


def test_camera_h5_reader_accepts_ordered_multitransition_controls_and_rejects_control_boundary_drift(tmp_path):
    recorder, candidate = _camera_h5_recorder(tmp_path / "base", transition_count=2)
    try:
        source = recorder.save_h5(tmp_path, "camera-control-reader-base")
        loaded = load_camera_observations_h5(source)
        assert loaded["observation_count"] == 3 and loaded["transition_count"] == 2
        assert len(load_structured_control_records_h5(source)["structured_controls"]) == 2
        assert len(load_structured_training_actions_h5(source)) == 2
        evidence_dir = os.environ.get("R04A_EVIDENCE_DIR")
        if evidence_dir:
            root = Path(evidence_dir)
            root.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, root / "valid-two-transition.h5")

        broken = tmp_path / "wrong-control-boundary.h5"
        shutil.copy2(source, broken)
        with h5py.File(broken, "r+") as h5:
            controls = json.loads(h5["meta/structured_controls_v1_json"][()].decode("utf-8"))
            action = controls[0]["writer_controls"][0]["canonical_action"]
            target_value = action["position_target_v1"]
            target_value["source_boundary"]["state_revision"] += 1
            target = PositionControlTargetV1.from_mapping(target_value)
            action["position_target_identity_hash"] = target.identity_hash
            _replace_json_dataset(h5, "meta/structured_controls_v1_json", controls)
        with pytest.raises(ValueError, match="structured control is not aligned"):
            load_camera_observations_h5(broken)
        if evidence_dir:
            shutil.copy2(broken, Path(evidence_dir) / "wrong-control-boundary.h5")
    finally:
        candidate.env.close()
