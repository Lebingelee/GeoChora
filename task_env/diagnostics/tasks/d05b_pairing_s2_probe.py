"""Real bounded D05b Physics × Renderer pairing probe for Position/Scene-v3."""

from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path
import subprocess
from unittest.mock import patch

from task_env.artifacts import (
    CameraRendererOverrideV1,
    ExecutionSpecV1,
    RendererSelectionV1,
)
from task_env.render.camera import D03_PHYSICS_PROFILE, D04_ENTITY_SEGMENTATION_PROFILE

FIXED_CAMERA_ID = "d04-entity-seg-fixed-occlusion-v1"
MOUNTED_CAMERA_ID = "d04-panda-hand-mounted-camera-v1"


def _execution_spec() -> ExecutionSpecV1:
    selection = RendererSelectionV1(
        "renderer-selection-v1", "mujoco", "native-opengl",
        D04_ENTITY_SEGMENTATION_PROFILE, None,
    )
    return ExecutionSpecV1(
        "execution-spec-v1", "geophys", "cpu", D03_PHYSICS_PROFILE,
        32, "best_effort", selection, physics_device="cpu:0",
        camera_overrides=(CameraRendererOverrideV1(
            "camera-renderer-override-v1", MOUNTED_CAMERA_ID, selection,
        ),),
    )


def run_s2(output: Path | str) -> dict[str, object]:
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('pairing output must be fresh; prior Evidence is preserved')
    output.mkdir(parents=True, exist_ok=True)
    raw_dir = output / "paired-camera-s2"
    execution = _execution_spec()
    resolved = dict(execution.resolve_camera_renderers((FIXED_CAMERA_ID, MOUNTED_CAMERA_ID)))
    if resolved != {
        FIXED_CAMERA_ID: execution.render_default,
        MOUNTED_CAMERA_ID: execution.camera_overrides[0].renderer,
    }:
        raise AssertionError("D05b default/per-camera renderer resolution changed")

    from task_env.diagnostics.tasks import d04_entity_segmentation_s2_probe as d04_probe

    original_create = d04_probe.create_dynamic_camera_session
    sessions = []
    context_provenance = []
    captures = []
    native_renderer_closes = []
    import mujoco
    import taichi_forge
    original_renderer_close = mujoco.Renderer.close

    def close_renderer(renderer):
        native_renderer_closes.append(renderer)
        return original_renderer_close(renderer)

    def create_selected_session(camera, _execution, **kwargs):
        if camera.camera_id not in resolved:
            raise AssertionError(f"unexpected D05b CameraGeometry {camera.camera_id!r}")
        selected = execution.renderer_for_camera(camera.camera_id)
        expected_origin = "camera_override" if camera.camera_id == MOUNTED_CAMERA_ID else "default"
        if expected_origin == "default" and selected != execution.render_default:
            raise AssertionError("fixed camera did not resolve the default renderer selection")
        if expected_origin == "camera_override" and selected != execution.camera_overrides[0].renderer:
            raise AssertionError("mounted camera did not resolve its per-camera override")

        session = original_create(camera, execution, **kwargs)
        sessions.append(session)
        from OpenGL import GL
        import os
        context_provenance.append({
            'camera_id': camera.camera_id,
            'MUJOCO_GL': os.environ.get('MUJOCO_GL'),
            'PYOPENGL_PLATFORM': os.environ.get('PYOPENGL_PLATFORM'),
            'EGL_PLATFORM': os.environ.get('EGL_PLATFORM'),
            'gl_vendor': GL.glGetString(GL.GL_VENDOR).decode(),
            'gl_renderer': GL.glGetString(GL.GL_RENDERER).decode(),
            'gl_version': GL.glGetString(GL.GL_VERSION).decode(),
            'device_selection': selected.device,
        })
        capture = session.capture

        def tracked_capture(state):
            observation = capture(state)
            sync = session.last_sync
            identity = observation.capture_identity
            if sync is None or sync.state_boundary != identity.state_boundary:
                raise AssertionError("Renderer sync and successful Camera capture used different boundaries")
            if sync.sample_clock != identity.sample_clock:
                raise AssertionError("Renderer sync and Camera capture used different clocks")
            if sync.consumer_id != session.consumer_id:
                raise AssertionError("sync receipt belongs to another renderer consumer")
            if identity.renderer_selection != selected:
                raise AssertionError("capture identity does not report the effective renderer selection")
            if identity.execution_spec_identity_hash != execution.identity_hash:
                raise AssertionError("capture identity does not bind the D05b ExecutionSpec")
            if identity.camera_id != camera.camera_id:
                raise AssertionError("capture identity does not bind its CameraGeometry")
            captures.append({
                "camera_id": camera.camera_id,
                "selection_origin": expected_origin,
                "effective_renderer_selection": selected.to_mapping(),
                "execution_spec_identity_hash": identity.execution_spec_identity_hash,
                "capture_identity_hash": identity.identity_hash,
                "state_boundary_id": identity.state_boundary.boundary_id,
                "scene_instance_id": identity.state_boundary.scene_instance_id,
                "provider_materialization_id": identity.state_boundary.provider_materialization_id,
                "publication_version": sync.publication_version,
                "transform_version": sync.transform_version,
                "consumer_id": sync.consumer_id,
                "static_geometry_build_count": sync.static_geometry_build_count,
                "modalities": identity.modalities,
            })
            return observation

        session.capture = tracked_capture
        return session

    with (
        patch.object(d04_probe, "create_dynamic_camera_session", create_selected_session),
        patch.object(mujoco.Renderer, "close", close_renderer),
    ):
        d04_receipt = d04_probe.run_s2(raw_dir)

    expected_capture_count = 6
    if len(captures) != expected_capture_count:
        raise AssertionError(f"expected {expected_capture_count} successful paired captures, got {len(captures)}")
    if len(native_renderer_closes) != 2 or len({id(renderer) for renderer in native_renderer_closes}) != 2:
        raise AssertionError("each independent dynamic camera session must close its native Renderer exactly once")
    if len({row["consumer_id"] for row in captures if row["camera_id"] == FIXED_CAMERA_ID}) != 1:
        raise AssertionError("fixed Camera consumer identity changed during one Episode")
    if len({row["consumer_id"] for row in captures if row["camera_id"] == MOUNTED_CAMERA_ID}) != 1:
        raise AssertionError("mounted Camera consumer identity changed during one Episode")
    if captures[0]["consumer_id"] == captures[1]["consumer_id"]:
        raise AssertionError("fixed and mounted Cameras shared one consumer identity")

    disk_readback = {}
    for camera_name in ("fixed_initial", "mounted_initial", "fixed_moved", "mounted_moved", "fixed_reset", "mounted_reset"):
        item = d04_receipt["disk_readback"][camera_name]
        bundle_path = Path(item["label_map_path"])
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        identity = bundle["capture_identity"]
        camera_id = identity["camera_id"]
        if identity["execution_spec_identity_hash"] != execution.identity_hash:
            raise AssertionError(f"{camera_name} disk capture identity lost the D05b ExecutionSpec")
        if identity["renderer_selection"] != resolved[camera_id].to_mapping():
            raise AssertionError(f"{camera_name} disk capture identity differs from effective renderer selection")
        disk_readback[camera_name] = {
            "capture_identity_hash": item["capture_identity_hash"],
            "label_map_identity_hash": item["label_map_identity_hash"],
            "mask_path": item["mask_path"],
            "bundle_path": str(bundle_path),
            "renderer_selection": identity["renderer_selection"],
        }

    result = {
        "status": "D05B_POSITION_SCENE_V3_GEOPHYS_CPU_MUJOCO_OPENGL_BOUNDED_S2_PASS",
        "runtime_provenance": {
            "python": platform.python_version(),
            "mujoco": str(mujoco.__version__),
            "taichi_forge": ".".join(str(part) for part in taichi_forge.__version__),
            "core_revision": subprocess.check_output(
                ["git", "-C", str(Path(__file__).resolve().parents[3]), "rev-parse", "HEAD"],
                text=True,
            ).strip(),
            "geophys_revision": subprocess.check_output(
                ["git", "-C", str(Path(__file__).resolve().parents[3] / "GeoPhys"), "rev-parse", "HEAD"],
                text=True,
            ).strip(),
        },
        "scope": d04_receipt["scope"],
        "actual_graphics_context": context_provenance,
        "execution_spec": execution.to_mapping(),
        "execution_spec_identity_hash": execution.identity_hash,
        "renderer_selection_resolution": {
            "render_default": execution.render_default.to_mapping(),
            "camera_overrides": [item.to_mapping() for item in execution.camera_overrides],
            "effective_by_camera": {
                camera_id: {
                    "origin": "camera_override" if camera_id in {item.camera_id for item in execution.camera_overrides} else "default",
                    "selection": selection.to_mapping(),
                    "selection_identity_hash": selection.identity_hash,
                }
                for camera_id, selection in resolved.items()
            },
        },
        "state_sync_and_capture": captures,
        "camera_frame_resolution": {
            "fixed_camera_parent_frame": "world",
            "mounted_camera_parent_frame_selector": "hand",
            "mounted_camera_canonical_frame_binding": {
                "entity_id": "panda-main",
                "frame_id": "hand",
                "native_body_name": "hand",
            },
            "mounted_camera_frame_binding_count": 1,
        },
        "resource_teardown": {
            "independent_camera_sessions": len(sessions),
            "native_renderer_close_calls": len(native_renderer_closes),
            "distinct_native_renderers_closed": len({id(renderer) for renderer in native_renderer_closes}),
            "session_scoped_close_observed": True,
            "process_allocator_memory_zero_required": False,
            "note": "Acceptance uses each session's public close path and native Renderer close call; process-level GL allocator/cache retention is not a session leak oracle.",
        },
        "disk_readback": disk_readback,
        "consumer_boundary": {
            "camera_observation_session_connected_to_environment_policy_observation": False,
            "camera_capture_connected_to_transition_recorder": False,
            "diagnostic_files_are_policy_observations_or_recorder_evidence": False,
            "description": "This receipt validates the existing dynamic CameraSession owner directly. BaseTaskEnv's current CameraObservationProvider is a separate configured RenderSource path; no dynamic D05b CameraSession is attached to that policy observation or transition recording path.",
        },
        "qualification_boundary": "bounded first Physics x Renderer integration intersection only; not complete D04/D05b, formal Qualification, or Phase II",
        "evidence": {
            "raw_d04_probe_directory": str(raw_dir),
            "d04_receipt": str(raw_dir / "d04_entity_segmentation_s2_receipt.json"),
        },
    }
    receipt_path = output / "d05b_pairing_s2_receipt.json"
    result["receipt_path"] = str(receipt_path)
    receipt_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", default="workspace/maintenance/d05b_pairing_20261022/s2_geophys_mujoco",
    )
    args = parser.parse_args()
    print(json.dumps(run_s2(args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
