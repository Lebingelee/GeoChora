"""D05a S1 static execution selection and capture-identity contracts."""

from dataclasses import replace

import pytest

from task_env.artifacts import (
    CameraRendererOverrideV1,
    CapabilityClaim,
    CapabilityAdmissionError,
    ExecutionSpec,
    ExecutionSpecV1,
    ProviderCapabilityManifest,
    RendererSelectionV1,
    StateBoundaryIdentity,
    StateSampleClock,
    CanonicalStateViewV1,
    decode_execution_spec,
)
from task_env.observations.canonical_camera import CameraGeometry
from task_env.render.camera import CameraRenderSource, TriangleMesh, admit_render, create_camera_session


def _renderer(provider="mujoco", *, backend="cpu", profile="camera-profile-v1", device=None):
    return RendererSelectionV1(
        "renderer-selection-v1", provider, backend, profile, device
    )


def _execution(*, overrides=(), default=None):
    return ExecutionSpecV1(
        schema_version="execution-spec-v1",
        physics_provider="geophys",
        physics_backend="cpu",
        physics_profile="geophys-profile-v1",
        provider_seed=7,
        determinism_mode="strict",
        render_default=default or _renderer(),
        physics_device="cpu:0",
        camera_overrides=tuple(overrides),
    )


def _camera(*, camera_id="wrist-cam", width=32, rgb=True, depth=True):
    identity = ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0))
    return CameraGeometry(
        "camera-observation-v0", "a" * 64, camera_id, "world", identity, identity,
        width, 24, 1.0, 0.01, 10.0, rgb, depth,
    )


def _manifest(*, capability_status="tested", profile="camera-profile-v1"):
    return ProviderCapabilityManifest(
        "provider-capability-v0", "mujoco", "mujoco-build-v1", "camera-adapter-v1",
        "cpu", "native-pairing", profile, "strict",
        (CapabilityClaim("rgb_camera", capability_status, "d05a-fixture"),),
        (), "implementation_only_no_qualification",
    )


def _legacy_camera_manifest():
    return ProviderCapabilityManifest(
        "provider-capability-v0", "mujoco", "mujoco-build-v1", "camera-adapter-v1",
        "cpu", "legacy-physics-profile", "p1_4_native_camera_cpu_v0", "strict",
        (
            CapabilityClaim("rgb_camera", "tested", "legacy-camera-fixture"),
            CapabilityClaim("depth_camera", "tested", "legacy-camera-fixture"),
        ),
        (), "implementation_only_no_qualification",
    )


def _state(*, revision=0, simulation_time=0.0):
    boundary = StateBoundaryIdentity(
        "state-boundary-identity-v1", "episode-v1", "reset-" + "b" * 64,
        "c" * 64, "scene-instance-v1", "materialization-v1", 0, revision,
    )
    clock = StateSampleClock(
        "state-sample-clock-v1", "evaluation_boundary", 0, simulation_time
    )
    return CanonicalStateViewV1(
        "canonical-state-v1", "SI_right_handed_z_up_wxyz", boundary, clock, (), (),
    )


def _source():
    vertices = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    mesh = TriangleMesh("table", vertices, ((0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)),
                        (0.5, 0.5, 0.5))
    return CameraRenderSource("camera-static-triangles-v0", "a" * 64, (mesh,))


def test_execution_spec_dispatch_preserves_legacy_v0_mapping_exactly():
    legacy = ExecutionSpec("mujoco", "cpu", "mujoco", "cpu", 11, "best_effort")
    mapping = legacy.to_mapping()

    assert "schema_version" not in mapping
    assert decode_execution_spec(mapping) == legacy
    assert decode_execution_spec(mapping).to_mapping() == mapping
    with pytest.raises(ValueError, match="unknown ExecutionSpec fields"):
        ExecutionSpec.from_mapping({**mapping, "schema_version": "execution-spec-v1"})
    with pytest.raises(ValueError, match="unsupported execution spec schema"):
        decode_execution_spec({**mapping, "schema_version": "execution-spec-v9"})


def test_execution_spec_v1_roundtrip_and_per_camera_override_precedence():
    override = CameraRendererOverrideV1(
        "camera-renderer-override-v1", "wrist-cam",
        _renderer("geophys", backend="cpu", profile="geophys-camera-v1", device="cuda:1"),
    )
    execution = _execution(overrides=(override,))
    decoded = decode_execution_spec(execution.to_mapping())

    assert decoded == execution
    assert decoded.identity_hash == execution.identity_hash
    assert decoded.renderer_for_camera("wrist-cam") == override.renderer
    assert decoded.renderer_for_camera("overhead-cam") == execution.render_default
    assert decoded.resolve_camera_renderers(("overhead-cam", "wrist-cam")) == (
        ("overhead-cam", execution.render_default), ("wrist-cam", override.renderer)
    )
    assert decoded.identity_hash != replace(
        decoded, physics_device="cpu:1"
    ).identity_hash


def test_camera_override_sets_are_strict_and_cannot_dangle():
    override = CameraRendererOverrideV1(
        "camera-renderer-override-v1", "wrist-cam", _renderer("geophys")
    )
    with pytest.raises(ValueError, match="duplicate per-camera"):
        _execution(overrides=(override, override))
    with pytest.raises(ValueError, match="unknown camera IDs"):
        _execution(overrides=(override,)).resolve_camera_renderers(("overhead-cam",))
    with pytest.raises(ValueError, match="duplicate declared camera ID"):
        _execution().resolve_camera_renderers(("wrist-cam", "wrist-cam"))


def test_manifest_identity_is_exact_and_does_not_change_existing_mapping():
    first = _manifest()
    same = ProviderCapabilityManifest.from_mapping(first.to_mapping())
    changed = _manifest(capability_status="implemented")

    assert first.identity_hash == same.identity_hash
    assert first.to_mapping() == same.to_mapping()
    assert first.identity_hash != changed.identity_hash


def test_capture_identity_binds_camera_source_selection_manifest_and_state_boundary():
    source = _source()
    camera = _camera()
    execution = _execution()
    manifest = _manifest()
    state = _state(revision=4, simulation_time=0.12)

    identity = source.capture_identity(camera, execution, manifest, state)
    assert identity.identity_hash == source.capture_identity(camera, execution, manifest, state).identity_hash
    assert identity.task_artifact_hash == camera.task_artifact_hash
    assert identity.render_source_identity_hash == source.identity_hash
    assert identity.provider_manifest_identity_hash == manifest.identity_hash
    assert identity.state_boundary == state.boundary
    assert identity.modalities == ("depth", "rgb")

    changed_state = _state(revision=5, simulation_time=0.12)
    assert identity.identity_hash != source.capture_identity(
        camera, execution, manifest, changed_state
    ).identity_hash
    assert identity.identity_hash != source.capture_identity(
        _camera(width=64), execution, manifest, state
    ).identity_hash
    assert identity.identity_hash != source.capture_identity(
        camera, _execution(default=_renderer(device="cuda:0")), manifest, state
    ).identity_hash


def test_capture_identity_refuses_mismatched_manifest_or_unlinked_source():
    source, camera, execution, state = _source(), _camera(), _execution(), _state()
    with pytest.raises(ValueError, match="manifest identity"):
        source.capture_identity(camera, execution, _manifest(profile="other-profile-v1"), state)
    with pytest.raises(ValueError, match="TaskArtifact linkage"):
        source.capture_identity(_camera().__class__(
            "camera-observation-v0", "d" * 64, "wrist-cam", "world",
            _camera().T_parent_from_mount, _camera().T_mount_from_camera,
            32, 24, 1.0, 0.01, 10.0,
        ), execution, _manifest(), state)


def test_current_camera_admission_stays_legacy_and_same_provider_only():
    camera = _camera()
    manifest = _legacy_camera_manifest()
    same_provider = ExecutionSpec("mujoco", "legacy-physics-profile", "mujoco", "cpu", 0, "strict")
    admit_render(camera, same_provider, manifest)

    cross_provider = ExecutionSpec("geophys", "legacy-physics-profile", "mujoco", "cpu", 0, "strict")
    with pytest.raises(CapabilityAdmissionError, match="provider/pairing"):
        admit_render(camera, cross_provider, manifest)
    with pytest.raises(TypeError, match="legacy ExecutionSpec"):
        admit_render(camera, _execution(), manifest)
    with pytest.raises(TypeError, match="legacy ExecutionSpec"):
        create_camera_session(camera, _execution(), source=_source())
