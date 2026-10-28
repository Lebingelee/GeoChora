from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import types

import numpy as np
import pytest

from task_env.diagnostics.tasks import (
    r04b_public_camera_s2_probe as camera_probe,
    r04c_camera_h5_s3_probe as r04c_worker,
    r04c_public_h5_semantic_reader as semantic_reader,
    r04c_raw_h5_comparator as raw_comparator,
)
from task_env.diagnostics.tasks.test_phase_ii_01_r04b_public_camera_s2 import (
    _ProviderFreeCameraSession,
    _ProviderFreeRuntimeSession,
)


MAINTENANCE = Path(
    "/home/lly/Program_Files/Geochora/workspace/maintenance/"
    "phase_ii_01_sol_luna_handoff_20261023_001"
)
CAMERA_IDS = camera_probe.CAMERA_IDS


def _patch_provider_free_route(monkeypatch, worker_output: Path):
    import mujoco

    seed_path = MAINTENANCE / "r04b_002" / "native" / "worker_001" / "raw_camera_arrays.npz"
    if not seed_path.is_file():
        seed_path = MAINTENANCE / "r04b_001" / "native_attempt002" / "worker" / "raw_camera_arrays.npz"
    seed_archive = np.load(seed_path, allow_pickle=False)
    seed_arrays = {key: seed_archive[key].copy() for key in seed_archive.files}
    created_envs = []
    sessions = []
    from task_env import make_env as actual_make_env
    reference_env_module = importlib.import_module("task_env.tasks.reference_env")
    camera_module = importlib.import_module("task_env.render.camera")

    def materialize(artifact, execution, *, source, binding,
                    controller_binding_plan, controller_profile, **_kwargs):
        if isinstance(controller_profile, (tuple, list)):
            assert len(controller_profile) == 1
            controller_profile = controller_profile[0]
        return _ProviderFreeRuntimeSession(
            artifact, source, binding, controller_binding_plan, controller_profile,
        )

    def camera_factory(camera, execution, *, source, initial_state, manifest):
        session = _ProviderFreeCameraSession(
            camera, execution, source=source, initial_state=initial_state,
            manifest=manifest, seed_arrays=seed_arrays,
        )
        sessions.append(session)
        return session

    def tracked_make_env(*args, **kwargs):
        env = actual_make_env(*args, **kwargs)
        created_envs.append(env)
        return env

    monkeypatch.setattr("task_env.make_env", tracked_make_env)
    monkeypatch.setattr(reference_env_module, "materialize_control", materialize)
    monkeypatch.setattr(camera_module, "create_dynamic_camera_session", camera_factory)
    monkeypatch.setattr(mujoco.Renderer, "render", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mujoco.Renderer, "close", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.setenv("MUJOCO_GL", "egl")
    monkeypatch.setenv("PYOPENGL_PLATFORM", "egl")
    worktree = Path(__file__).resolve().parents[3]
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join((str(worktree), str(worktree / "GeoPhys" / "src"))))
    monkeypatch.setattr(sys, "path", [str(worktree / "GeoPhys" / "src"), *sys.path])
    frozen = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=worktree, text=True).strip()
    monkeypatch.setenv("R04C_FROZEN_HEAD", frozen)
    real_check_output = subprocess.check_output

    def synthetic_clean_tree_check(args, *call_args, **call_kwargs):
        if list(args[:2]) == ["git", "status"]:
            return ""
        return real_check_output(args, *call_args, **call_kwargs)

    # The provider-free S1 calls the production CLI before its implementation
    # commit exists. Native execution keeps the runner's real clean-tree gate.
    monkeypatch.setattr(subprocess, "check_output", synthetic_clean_tree_check)
    return {"created_envs": created_envs, "sessions": sessions, "seed_path": seed_path}


def _run_reader(script: Path, args: list[str], cwd: Path):
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-I", "-B", str(script), *args], cwd=cwd, env=environment,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def test_r04c_complete_provider_free_s3_worker_and_two_independent_readers(tmp_path, monkeypatch):
    """Run real Env/Controller/Recorder/H5 owners with synthetic bottom IO only."""
    worker_output = tmp_path / "synthetic_worker"
    provenance = _patch_provider_free_route(monkeypatch, worker_output)
    assert r04c_worker.main(["--output", str(worker_output)]) == 0
    receipt = json.loads((worker_output / "r04c_worker_receipt.json").read_text())
    assert receipt["status"] == "R04C_NATIVE_RECORDING_COMPLETE_PENDING_OFFLINE_READBACK"
    assert receipt["native_counters"]["reset_attempts"] == 2
    assert receipt["native_counters"]["outer_steps"] == 24
    assert receipt["native_counters"]["accepted_physics_substeps"] == 120
    assert receipt["native_counters"]["clock_inferred_substeps"] == 120
    assert receipt["env_close_calls"] == 1
    assert receipt["env_close_successes"] == 1
    assert receipt["closed_before_receipt"] is True
    assert len(receipt["episode_recordings"]) == 2
    assert all(item["status"] == "FINALIZED" for item in receipt["episode_recordings"])
    assert len(provenance["created_envs"]) == 1
    assert len(provenance["sessions"]) == 4
    assert not (worker_output / "source_workspace_public").exists()
    assert (worker_output / "source_workspace_manifest.json").is_file()

    semantic_path = Path(semantic_reader.__file__).resolve()
    semantic_receipt = worker_output / "semantic_readback.json"
    process = _run_reader(
        semantic_path,
        ["--worker-output", str(worker_output), "--receipt-out", str(semantic_receipt)],
        tmp_path,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    semantic = json.loads(semantic_receipt.read_text())
    assert semantic["status"] == "R04C_PUBLIC_H5_SEMANTIC_READBACK_PASS"
    assert len(semantic["episodes"]) == 2
    assert semantic["engine_modules_imported"] == []

    comparator_path = Path(raw_comparator.__file__).resolve()
    raw_receipt = worker_output / "raw_readback.json"
    process = _run_reader(
        comparator_path,
        ["--worker-output", str(worker_output), "--receipt-out", str(raw_receipt)],
        tmp_path,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    raw = json.loads(raw_receipt.read_text())
    assert raw["status"] == "R04C_RAW_H5_PREWRITE_WITNESS_PASS"
    assert len(raw["episodes"]) == 2
    assert raw["forbidden_imports"] == []
    assert all(item["checked_public_boundary_camera_values"] > 1_000_000 for item in raw["episodes"])

    import h5py

    original_h5 = Path(receipt["episode_recordings"][0]["path"])
    working_h5 = tmp_path / "tamper_working.h5"
    semantic_negative = tmp_path / "semantic_negative.json"
    raw_negative = tmp_path / "raw_negative.json"

    def rewrite_metadata(root, name, value):
        path = f"meta/{name}"
        del root[path]
        root["meta"].create_dataset(
            name,
            data=np.asarray(json.dumps(value, sort_keys=True), dtype=h5py.string_dtype("utf-8")),
        )

    def edit_sidecar(name, edit):
        def mutate(root):
            value = json.loads(root[f"meta/{name}"][()].decode("utf-8"))
            edit(value)
            rewrite_metadata(root, name, value)
        return mutate

    def mutate_rgb(root):
        path = f"obs/rgb/{CAMERA_IDS[0]}"
        dataset = root[path]
        value = int(dataset[0, 0, 0, 0])
        dataset[0, 0, 0, 0] = np.uint8((value + 1) % 256)

    def mutate_depth(root):
        path = f"obs/depth/{CAMERA_IDS[0]}"
        dataset = root[path]
        dataset[0, 0, 0] = np.float32(dataset[0, 0, 0]) + np.float32(1.0)

    def mutate_state_digest(root):
        root["obs/state/boundary_identity_sha256"][0, 0] ^= np.uint8(1)

    def mutate_schema(root):
        root.attrs["schema_version"] = "v2"

    def mutate_count(root):
        root.attrs["transition_count"] = 11

    def remove_contract(root):
        del root["meta/camera_observation_contract_v1_json"]

    def bad_rgb_shape(root):
        del root[f"obs/rgb/{CAMERA_IDS[0]}"]
        root.create_dataset(f"obs/rgb/{CAMERA_IDS[0]}", data=np.zeros((13, 3, 240, 321), dtype=np.uint8))

    def bad_rgb_dtype(root):
        del root[f"obs/rgb/{CAMERA_IDS[0]}"]
        root.create_dataset(f"obs/rgb/{CAMERA_IDS[0]}", data=np.zeros((13, 3, 241, 321), dtype=np.uint16))

    def bad_mask_label(root):
        root[f"obs/entity_mask/{CAMERA_IDS[0]}"][0, 0, 0] = np.uint32(999)

    def bad_mask_digest(value):
        value[0]["captures"][0]["mask_sha256"] = "0" * 64

    def bad_clock(value):
        value["boundaries"][0]["state_sample_clock"]["simulation_time_s"] += 0.001

    def bad_materialization(value):
        value[0]["captures"][0]["capture_identity"]["state_boundary"][
            "provider_materialization_id"
        ] = "wrong-materialization"

    def bad_episode(value):
        value[0]["captures"][0]["capture_identity"]["state_boundary"]["episode_id"] = "wrong-episode"

    def bad_reset(value):
        value[0]["captures"][0]["capture_identity"]["state_boundary"]["reset_sample_id"] = "reset-" + "0" * 64

    def bad_calibration(value):
        value[0]["captures"][0]["calibration"]["camera"]["width"] = 320

    def bad_label_map(value):
        value[0]["captures"][0]["label_map"]["labels"][0]["label"] = 99

    def bad_target_ack(value):
        value[0]["writer_controls"][0]["applied_control"]["target_hash"] = "0" * 64

    def reverse_control_order(value):
        value[0], value[1] = value[1], value[0]

    def change_outcome(root):
        outcome = json.loads(root["meta/episode_outcome_v1_json"][()].decode("utf-8"))
        outcome["end_reason"] = "internal_stop"
        rewrite_metadata(root, "episode_outcome_v1_json", outcome)
        root.attrs["stop_reason"] = "internal_stop"

    def unfinalized(root):
        root.attrs["episode_complete"] = False

    cases = [
        ("missing-camera-sidecar", remove_contract, "semantic"),
        ("unknown-version", mutate_schema, "semantic"),
        ("transition-count", mutate_count, "semantic"),
        ("rgb-shape", bad_rgb_shape, "semantic"),
        ("rgb-dtype", bad_rgb_dtype, "semantic"),
        ("mask-unknown-label", bad_mask_label, "semantic"),
        ("mask-digest", edit_sidecar("camera_observations_v1_json", bad_mask_digest), "semantic"),
        ("rgb-pixel-change", mutate_rgb, "raw"),
        ("finite-depth-pixel-change", mutate_depth, "raw"),
        ("state-boundary-digest", mutate_state_digest, "semantic"),
        ("sample-clock", edit_sidecar("camera_recording_binding_v1_json", bad_clock), "semantic"),
        ("provider-materialization", edit_sidecar("camera_observations_v1_json", bad_materialization), "semantic"),
        ("episode-identity", edit_sidecar("camera_observations_v1_json", bad_episode), "semantic"),
        ("reset-identity", edit_sidecar("camera_observations_v1_json", bad_reset), "semantic"),
        ("camera-calibration", edit_sidecar("camera_observations_v1_json", bad_calibration), "semantic"),
        ("canonical-label-map", edit_sidecar("camera_observations_v1_json", bad_label_map), "semantic"),
        ("target-ack", edit_sidecar("structured_controls_v1_json", bad_target_ack), "semantic"),
        ("control-order", edit_sidecar("structured_controls_v1_json", reverse_control_order), "semantic"),
        ("end-reason", change_outcome, "semantic"),
        ("unfinalized", unfinalized, "semantic"),
    ]
    negative_rows = []
    for case_id, mutator, reader_kind in cases:
        shutil.copyfile(original_h5, working_h5)
        with h5py.File(working_h5, "r+") as root:
            mutator(root)
        if reader_kind == "semantic":
            process = _run_reader(
                semantic_path,
                ["--h5", str(working_h5), "--receipt-out", str(semantic_negative)],
                tmp_path,
            )
            result = json.loads(semantic_negative.read_text())
            assert process.returncode == 1, (case_id, process.stdout, process.stderr)
            assert result["status"] == "R04C_PUBLIC_H5_SEMANTIC_READBACK_FAIL", case_id
        else:
            process = _run_reader(
                comparator_path,
                ["--worker-output", str(worker_output), "--h5-override", str(working_h5),
                 "--episode-index", "1", "--receipt-out", str(raw_negative)],
                tmp_path,
            )
            result = json.loads(raw_negative.read_text())
            assert process.returncode == 1, (case_id, process.stdout, process.stderr)
            assert result["status"] == "R04C_RAW_H5_PREWRITE_WITNESS_FAIL", case_id
        negative_rows.append({
            "case_id": case_id, "target_reader": reader_kind,
            "return_code": process.returncode, "rejected": True,
            "error": result.get("error", {}).get("message"),
        })

    partial_receipt = tmp_path / "partial_worker_receipt.json"
    partial = json.loads((worker_output / "r04c_worker_receipt.json").read_text())
    partial["episode_recordings"][0]["status"] = "RECORDING"
    partial["episode_recordings"][0]["finalizer_result"] = None
    partial_receipt.write_text(json.dumps(partial, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    process = _run_reader(
        comparator_path,
        ["--worker-output", str(worker_output), "--worker-receipt", str(partial_receipt),
         "--receipt-out", str(raw_negative)],
        tmp_path,
    )
    partial_result = json.loads(raw_negative.read_text())
    assert process.returncode == 1
    assert partial_result["status"] == "R04C_RAW_H5_PREWRITE_WITNESS_FAIL"
    negative_rows.append({
        "case_id": "partial-receipt-masquerading-complete", "target_reader": "raw",
        "return_code": process.returncode, "rejected": True,
        "error": partial_result.get("error", {}).get("message"),
    })
    (tmp_path / "negative_matrix.json").write_text(
        json.dumps({"schema_version": "r04c-h5-negative-matrix-v1", "cases": negative_rows},
                   indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    native_matrix_path = Path(__file__).with_name("r04c_h5_negative_matrix.py").resolve()
    native_matrix_receipt = worker_output / "native_h5_negative_matrix.json"
    process = _run_reader(
        native_matrix_path,
        ["--worker-output", str(worker_output), "--receipt-out", str(native_matrix_receipt)],
        tmp_path,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    native_matrix = json.loads(native_matrix_receipt.read_text())
    assert native_matrix["status"] == "R04C_NATIVE_H5_TAMPER_MATRIX_PASS"
    assert native_matrix["case_count"] >= 21


def test_r04c_reader_cli_argument_contracts_are_available():
    for module in (r04c_worker, semantic_reader, raw_comparator,
                   importlib.import_module("task_env.diagnostics.tasks.r04c_h5_negative_matrix")):
        worktree = Path(module.__file__).resolve().parents[3]
        help_result = subprocess.run(
            [sys.executable, "-B", str(Path(module.__file__).resolve()), "--help"],
            cwd=worktree,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={
                **os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": os.pathsep.join((str(worktree), str(worktree / "GeoPhys" / "src"))),
            },
        )
        assert help_result.returncode == 0, help_result.stdout + help_result.stderr


@pytest.mark.parametrize(
    "failure_kind",
    ("post-step-capture", "recorder-append", "h5-metadata", "h5-dataset", "h5-replace", "env-close"),
)
def test_r04c_provider_free_failure_chain_fails_closed_and_preserves_evidence(
    tmp_path, monkeypatch, failure_kind,
):
    output = tmp_path / f"failure_{failure_kind}"
    _patch_provider_free_route(monkeypatch, output)
    recorder_module = importlib.import_module("task_env.recorders.recorder")
    h5_module = importlib.import_module("task_env.recorders.h5")
    original_session_capture = _ProviderFreeCameraSession.capture
    original_runtime_close = _ProviderFreeRuntimeSession.close

    if failure_kind == "post-step-capture":
        def capture_failure(session, state):
            if state.boundary.control_step == 1:
                raise RuntimeError("injected post-step camera capture failure")
            return original_session_capture(session, state)
        monkeypatch.setattr(_ProviderFreeCameraSession, "capture", capture_failure)
    elif failure_kind == "recorder-append":
        def append_failure(*_args, **_kwargs):
            raise RuntimeError("injected TransitionRecorder append failure")
        monkeypatch.setattr(recorder_module.TransitionRecorder, "append_transition", append_failure)
    elif failure_kind == "h5-metadata":
        original_json_dataset = h5_module._json_dataset
        def metadata_failure(group, name, value):
            if name == "camera_observation_contract_v1_json":
                raise RuntimeError("injected H5 camera metadata write failure")
            return original_json_dataset(group, name, value)
        monkeypatch.setattr(h5_module, "_json_dataset", metadata_failure)
    elif failure_kind == "h5-dataset":
        import h5py
        original_create_dataset = h5py.Group.create_dataset
        fired = {"value": False}
        def dataset_failure(group, name, *args, **kwargs):
            if not fired["value"] and str(name).startswith("obs/rgb/"):
                fired["value"] = True
                raise RuntimeError("injected H5 RGB dataset write failure")
            return original_create_dataset(group, name, *args, **kwargs)
        monkeypatch.setattr(h5py.Group, "create_dataset", dataset_failure)
    elif failure_kind == "h5-replace":
        def replace_failure(_temporary, _target):
            raise OSError("injected atomic H5 os.replace failure")
        monkeypatch.setattr(h5_module, "os", types.SimpleNamespace(replace=replace_failure))
    elif failure_kind == "env-close":
        close_calls = {"count": 0}
        def runtime_close_failure(session):
            original_runtime_close(session)
            close_calls["count"] += 1
            if close_calls["count"] == 2:
                raise RuntimeError("injected final runtime close acknowledgement failure")
        monkeypatch.setattr(_ProviderFreeRuntimeSession, "close", runtime_close_failure)

    assert r04c_worker.main(["--output", str(output)]) == 1
    receipt = json.loads((output / "r04c_worker_receipt.json").read_text())
    assert receipt["status"] == "R04C_NATIVE_RECORDING_FAIL"
    assert receipt["primary_error"] is not None or receipt["cleanup_errors"]
    assert receipt["qualification_granted"] is False
    if failure_kind in ("post-step-capture", "recorder-append"):
        counters = receipt["native_counters"]
        assert counters["accepted_physics_substeps"] >= 5
        assert counters["outer_steps"] < 24
        assert receipt["episode_recordings"][0]["status"] in {"STARTING", "RECORDING"}
        fault_path = Path(receipt["episode_recordings"][0]["path"])
        assert fault_path.is_file()
        import h5py
        with h5py.File(fault_path, "r") as fault_h5:
            assert int(fault_h5.attrs["transition_count"]) == 0
            assert int(fault_h5.attrs["observation_count"]) == 1
            assert fault_h5.attrs["stop_reason"] == "execution_fault"
    elif failure_kind in ("h5-metadata", "h5-dataset", "h5-replace"):
        first_path = Path(receipt["episode_recordings"][0]["path"])
        assert not first_path.exists(), "failed finalization must not publish a final H5"
        assert not first_path.with_name(f".{first_path.name}.tmp").exists(), "failed writer must remove its temporary H5"
        assert receipt["primary_error"] is not None
    else:
        assert receipt["primary_error"] is not None
        assert "cleanup_error" in receipt
        assert receipt["env_close_successes"] == 0
        for entry in receipt["episode_recordings"]:
            path = Path(entry["path"])
            assert path.is_file()
            assert camera_probe._sha256(path) == entry["file_sha256"], "close failure changed an already finalized episode"

    (tmp_path / f"{failure_kind}_receipt_summary.json").write_text(
        json.dumps({
            "failure_kind": failure_kind,
            "status": receipt["status"],
            "primary_error": receipt["primary_error"],
            "cleanup_errors": receipt["cleanup_errors"],
            "counters": receipt["native_counters"],
            "episode_recordings": receipt["episode_recordings"],
        }, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
