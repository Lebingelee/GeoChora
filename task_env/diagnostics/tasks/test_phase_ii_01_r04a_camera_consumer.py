"""Provider-free S1 for the opt-in Position camera observation consumer."""

import sys

import h5py
import numpy as np
import pytest

from task_env.artifacts.contracts import FrameReference, PoseWorld
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
)
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
    config = _config(width=3, height=2)
    candidate = _candidate(tmp_path)
    try:
        from task_env.artifacts import ExecutionSpecV1, RendererSelectionV1
        from task_env.render.camera import (
            D03_PHYSICS_PROFILE,
            D04_ENTITY_SEGMENTATION_PROFILE,
            DynamicCameraRenderSourceV1,
            dynamic_entity_instance_segmentation_manifest,
        )

        state = _state(candidate, 0)
        source = DynamicCameraRenderSourceV1.from_runtime_source(candidate.source)
        renderer = RendererSelectionV1(
            "renderer-selection-v1", "mujoco", "native-opengl",
            D04_ENTITY_SEGMENTATION_PROFILE, None,
        )
        execution = ExecutionSpecV1(
            "execution-spec-v1", "geophys", "cpu", D03_PHYSICS_PROFILE,
            31, "best_effort", renderer, physics_device="cpu:0",
        )
        manifest = dynamic_entity_instance_segmentation_manifest()
        captures = tuple(
            _capture(camera, execution, source, state, manifest, config)
            for camera in config.geometries(candidate.artifact.identity_hash)
        )
        from task_env.observations.canonical_camera.consumer import camera_observation_boundary_from_captures

        boundary = camera_observation_boundary_from_captures(captures)
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
        leaves = {
            "state": {"value": np.asarray((0.0,), dtype=np.float32)},
            "privileged_state": {},
            "rgb": {camera: capture.rgb for camera, capture in zip((FIXED_CAMERA_ID, HAND_CAMERA_ID), captures)},
            "depth": {camera: capture.depth for camera, capture in zip((FIXED_CAMERA_ID, HAND_CAMERA_ID), captures)},
            "entity_mask": {camera: capture.segmentation.mask for camera, capture in zip((FIXED_CAMERA_ID, HAND_CAMERA_ID), captures)},
        }
        metadata = {
            "env_metadata": {
                "env_name": "r04a-synthetic-camera-v3",
                "action_schema": {"schema_id": "synthetic-action-v1", "components": ("action",),
                                  "controller_kind": "absolute_joint", "reference": "world"},
                "observation_schema": {"leaf_specs": []},
            },
            "universal_action_schema": {"version": "synthetic-v1", "dimension": 1,
                                        "components": ("action",)},
            "camera_observation_contract_v1": config.to_mapping(),
        }
        recorder = TransitionRecorder(RecorderConfig(schema_version="v3", max_transitions=1))
        recorder.begin_episode(
            leaves, {"camera_observation_v1": boundary.to_mapping()}, metadata,
        )
        end = make_episode_end_v1(
            episode_id=state.boundary.episode_id, final_boundary=0,
            end_reason="external_stop", terminated=False, truncated=True,
            bootstrap_allowed=True, source="r04a-s1-test",
        )
        recorder.end_episode(
            "external_stop", outcome=end.outcome, end_event=end.boundary_event,
        )
        path = recorder.save_h5(tmp_path, "synthetic-camera-v3")
        camera = load_camera_observations_h5(path)
        assert camera["schema_version"] == "camera-observation-boundary-v1"
        assert camera["observation_count"] == 1 and camera["transition_count"] == 0
        assert camera["boundaries"][0].state_boundary_id == state.boundary.boundary_id
        assert load_structured_control_records_h5(path)["observation_count"] == 1
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
