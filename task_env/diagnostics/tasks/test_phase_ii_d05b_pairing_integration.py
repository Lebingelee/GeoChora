"""Defect-sensitive S1 checks for the bounded D05b camera pairing route."""

from dataclasses import replace
import sys
from unittest.mock import patch

import pytest

from task_env.artifacts import (
    CameraRendererOverrideV1,
    CapabilityAdmissionError,
    ExecutionSpecV1,
    RendererSelectionV1,
)
from task_env.diagnostics.tasks.c02b_position_candidate import build_position_candidate
from task_env.diagnostics.tasks.d04_rgbd_camera_s2_probe import (
    fixed_calibration_camera,
    mounted_hand_camera,
)
from task_env.render.camera import (
    D03_PHYSICS_PROFILE,
    D04_ENTITY_SEGMENTATION_PROFILE,
    DynamicCameraRenderSourceV1,
    admit_dynamic_camera,
    create_dynamic_camera_session,
    dynamic_entity_instance_segmentation_manifest,
)
from task_env.render.camera.source import project_render_state_v1


def _selection(*, provider="mujoco", backend="native-opengl", profile=D04_ENTITY_SEGMENTATION_PROFILE, device=None):
    return RendererSelectionV1("renderer-selection-v1", provider, backend, profile, device)


def _execution(*, default=None, overrides=(), physics_provider="geophys"):
    return ExecutionSpecV1(
        "execution-spec-v1", physics_provider, "cpu", D03_PHYSICS_PROFILE,
        32, "best_effort", default or _selection(), physics_device="cpu:0",
        camera_overrides=tuple(overrides),
    )


def _candidate(tmp_path, *, horizon=8):
    candidate = build_position_candidate(
        tmp_path / "position-source", provider="geophys", horizon=horizon,
    )
    candidate.env.reset()
    return candidate


def _guard_physics_calls(env):
    counts = {"controller_compute": 0, "provider_step": 0}
    controller_type = type(env.controller)
    provider_type = type(env.session)
    original_compute = controller_type.compute
    original_step = provider_type.step

    def count_compute(controller, *args, **kwargs):
        if controller is env.controller:
            counts["controller_compute"] += 1
        return original_compute(controller, *args, **kwargs)

    def count_step(session, *args, **kwargs):
        if session is env.session:
            counts["provider_step"] += 1
        return original_step(session, *args, **kwargs)

    return counts, patch.object(controller_type, "compute", count_compute), patch.object(provider_type, "step", count_step)


def test_d05b_exact_default_override_admission_and_invalid_requests_fail_before_native_or_physics(tmp_path):
    candidate = _candidate(tmp_path)
    env = candidate.env
    try:
        source = DynamicCameraRenderSourceV1.from_runtime_source(candidate.source)
        state = env.typed_state.view
        fixed = fixed_calibration_camera(candidate, state)
        mounted = mounted_hand_camera(candidate, state)
        selection = _selection()
        execution = _execution(overrides=(
            CameraRendererOverrideV1(
                "camera-renderer-override-v1", mounted.camera_id, selection,
            ),
        ))
        manifest = dynamic_entity_instance_segmentation_manifest()

        assert execution.resolve_camera_renderers((fixed.camera_id, mounted.camera_id)) == (
            (fixed.camera_id, selection), (mounted.camera_id, selection),
        )
        for camera in (fixed, mounted):
            admit_dynamic_camera(camera, execution, source=source, manifest=manifest)

        bad_renderer = _execution(default=_selection(backend="cpu"))
        wrong_physics = _execution(physics_provider="mujoco")
        missing_device = _execution(default=_selection(device="gpu:0"))
        bad_override = _execution(overrides=(
            CameraRendererOverrideV1(
                "camera-renderer-override-v1", mounted.camera_id,
                _selection(provider="geophys"),
            ),
        ))
        missing_source = replace(source, task_artifact_hash="f" * 64)
        missing_parent = replace(mounted, parent_frame="panda-main/not-a-frame")
        missing_artifact = replace(fixed, task_artifact_hash="e" * 64)
        missing_rgb = replace(fixed, rgb=False)
        bad_scene_boundary = replace(
            state.boundary, scene_identity_hash="d" * 64,
        )
        wrong_publication = replace(state, boundary=bad_scene_boundary)

        import task_env.render.camera.mujoco as mujoco_camera

        native_calls = []
        construction_guard = patch.object(
            mujoco_camera, "MuJoCoDynamicCameraSession",
            side_effect=lambda *args, **kwargs: native_calls.append((args, kwargs)),
        )
        counts, compute_guard, step_guard = _guard_physics_calls(env)
        with construction_guard, compute_guard, step_guard:
            with pytest.raises(CapabilityAdmissionError, match="bounded MuJoCo native OpenGL"):
                admit_dynamic_camera(fixed, bad_renderer, source=source, manifest=manifest)
            with pytest.raises(CapabilityAdmissionError, match="bounded MuJoCo native OpenGL"):
                admit_dynamic_camera(fixed, wrong_physics, source=source, manifest=manifest)
            with pytest.raises(CapabilityAdmissionError, match="bounded MuJoCo native OpenGL"):
                admit_dynamic_camera(fixed, missing_device, source=source, manifest=manifest)
            with pytest.raises(CapabilityAdmissionError, match="bounded MuJoCo native OpenGL"):
                admit_dynamic_camera(mounted, bad_override, source=source, manifest=manifest)
            with pytest.raises(CapabilityAdmissionError, match="TaskArtifact linkage"):
                create_dynamic_camera_session(
                    fixed, execution, source=missing_source, initial_state=state, manifest=manifest,
                )
            with pytest.raises(CapabilityAdmissionError, match="TaskArtifact linkage"):
                create_dynamic_camera_session(
                    missing_artifact, execution, source=source, initial_state=state, manifest=manifest,
                )
            with pytest.raises(CapabilityAdmissionError, match="parent Frame"):
                create_dynamic_camera_session(
                    missing_parent, execution, source=source, initial_state=state, manifest=manifest,
                )
            with pytest.raises(CapabilityAdmissionError, match="requires RGB and Depth"):
                admit_dynamic_camera(missing_rgb, execution, source=source, manifest=manifest)
            with pytest.raises(ValueError, match="Scene identity"):
                create_dynamic_camera_session(
                    fixed, execution, source=source, initial_state=wrong_publication, manifest=manifest,
                )

        assert native_calls == []
        assert counts == {"controller_compute": 0, "provider_step": 0}
        assert env.typed_state.view.boundary == state.boundary
        assert env.state.simulation_time == 0.0
    finally:
        env.close()


def test_d05b_missing_native_dependency_fails_before_physics_or_successful_capture(tmp_path):
    candidate = _candidate(tmp_path)
    env = candidate.env
    try:
        source = DynamicCameraRenderSourceV1.from_runtime_source(candidate.source)
        state = env.typed_state.view
        camera = fixed_calibration_camera(candidate, state)
        execution = _execution()
        manifest = dynamic_entity_instance_segmentation_manifest()
        counts, compute_guard, step_guard = _guard_physics_calls(env)
        with compute_guard, step_guard, patch.dict(sys.modules, {"mujoco": None}):
            # Admission computes the selected Renderer manifest first, whose
            # existing provider provenance gate rejects a missing package.
            with pytest.raises(ValueError, match="mujoco import source unavailable"):
                create_dynamic_camera_session(
                    camera, execution, source=source, initial_state=state, manifest=manifest,
                )
        assert counts == {"controller_compute": 0, "provider_step": 0}
        assert env.typed_state.view.boundary == state.boundary
        assert env.state.simulation_time == 0.0
    finally:
        env.close()


def test_d05b_partial_construction_cleanup_sync_capture_failure_and_consumer_close_isolation(tmp_path):
    candidate = _candidate(tmp_path)
    env = candidate.env
    sessions = []
    try:
        source = DynamicCameraRenderSourceV1.from_runtime_source(candidate.source)
        state = env.typed_state.view
        fixed_camera = fixed_calibration_camera(candidate, state)
        mounted_camera = mounted_hand_camera(candidate, state)
        execution = _execution(overrides=(
            CameraRendererOverrideV1(
                "camera-renderer-override-v1", mounted_camera.camera_id, _selection(),
            ),
        ))
        manifest = dynamic_entity_instance_segmentation_manifest()
        import mujoco
        import task_env.render.camera.api as camera_api

        projection = project_render_state_v1(source, state)
        invalid_projection = replace(projection, geometry_version="wrong-geometry-version")
        close_calls = []
        original_close = mujoco.Renderer.close

        def counted_close(renderer):
            # Keep the object alive through the assertion so its destructor
            # cannot be mistaken for a second explicit close by the session.
            close_calls.append(renderer)
            return original_close(renderer)

        with (
            patch.object(camera_api, "project_render_state_v1", return_value=invalid_projection),
            patch.object(mujoco.Renderer, "close", counted_close),
        ):
            with pytest.raises(ValueError, match="another geometry version"):
                create_dynamic_camera_session(
                    fixed_camera, execution, source=source, initial_state=state, manifest=manifest,
                )
        assert len(close_calls) == 1, "post-allocation constructor failure leaked its native Renderer"

        counts, compute_guard, step_guard = _guard_physics_calls(env)
        with patch.object(mujoco.Renderer, "close", counted_close), compute_guard, step_guard:
            fixed = create_dynamic_camera_session(
                fixed_camera, execution, source=source, initial_state=state, manifest=manifest,
            )
            mounted = create_dynamic_camera_session(
                mounted_camera, execution, source=source, initial_state=state, manifest=manifest,
            )
            sessions.extend((fixed, mounted))

            wrong_state = replace(
                state,
                boundary=replace(state.boundary, scene_identity_hash="c" * 64),
            )
            with pytest.raises(ValueError, match="Scene identity"):
                fixed.capture(wrong_state)
            assert fixed.last_sync.state_boundary == state.boundary

            def fail_native_render(_renderer, *args, **kwargs):
                raise RuntimeError("injected D05b capture failure")

            with patch.object(mujoco.Renderer, "render", fail_native_render):
                with pytest.raises(RuntimeError, match="injected D05b capture failure"):
                    fixed.capture(state)
            # A failed capture yields no CanonicalCameraObservation; the sibling
            # renderer remains independently usable at the same publication.
            sibling_capture = mounted.capture(state)
            assert sibling_capture.capture_identity.state_boundary == state.boundary

            fixed.close()
            fixed.close()
            with pytest.raises(RuntimeError, match="closed"):
                fixed.capture(state)
            assert mounted.capture(state).capture_identity.state_boundary == state.boundary
            mounted.close()
            mounted.close()

        assert counts == {"controller_compute": 0, "provider_step": 0}
        assert len(close_calls) == 3
        assert len({id(renderer) for renderer in close_calls}) == 3
        assert env.typed_state.view.boundary == state.boundary
        assert env.state.simulation_time == 0.0
    finally:
        for session in sessions:
            session.close()
        env.close()
