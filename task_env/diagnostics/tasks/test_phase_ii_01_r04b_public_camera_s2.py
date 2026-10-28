from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from types import MappingProxyType, SimpleNamespace

import numpy as np
import pytest

from task_env.diagnostics.tasks import r04b_native_supervisor as supervisor
from task_env.diagnostics.tasks import r04b_public_camera_offline_readback as reader
from task_env.diagnostics.tasks import r04b_public_camera_s2_probe as probe


def _proper_transform(value):
    matrix = np.asarray(value, dtype=np.float64)
    return (
        matrix.shape == (4, 4)
        and np.isfinite(matrix).all()
        and np.array_equal(matrix[3], (0.0, 0.0, 0.0, 1.0))
        and np.allclose(matrix[:3, :3].T @ matrix[:3, :3], np.eye(3), atol=1e-6, rtol=0)
        and abs(float(np.linalg.det(matrix[:3, :3])) - 1.0) <= 1e-6
    )


def test_r04b_mounts_come_from_fixed_reset_plan_fk_and_are_proper():
    config, evidence = probe.derive_camera_config()
    assert tuple(item.camera_id for item in config.cameras) == probe.CAMERA_IDS
    assert tuple(item.parent_frame for item in config.cameras) == ("world", "hand")
    assert all(_proper_transform(item.T_parent_from_mount) for item in config.cameras)
    assert evidence["task_seed"] == 31
    assert evidence["joint_positions_rad"]["joint1"] == pytest.approx(0.35)
    assert config.capacity(16)["boundary_count"] == 17


def test_worker_preflight_imports_when_loaded_from_its_direct_file_path():
    worktree = Path(__file__).resolve().parents[3]
    worker_path = Path(probe.__file__).resolve()
    environment = dict(os.environ)
    environment.update({
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join((str(worktree), str(worktree / "GeoPhys" / "src"))),
    })
    code = (
        "import runpy; "
        "m=runpy.run_path(__import__('sys').argv[1], run_name='r04b_worker_preflight_test'); "
        "config,evidence=m['derive_camera_config'](); "
        "print(config.cameras[0].camera_id, evidence['task_seed'])"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(worker_path)], env=environment,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("31")


def test_contract_decoded_label_map_compares_through_canonical_json_mapping():
    from task_env.observations.canonical_camera.images import CanonicalEntityLabelMapV1, CanonicalEntityLabelV1

    canonical = CanonicalEntityLabelMapV1(
        "canonical-entity-label-map-v1", "a" * 64, "b" * 64, "c" * 64,
        probe.FIXED_CAMERA_ID, "scene-instance", "materialization", "episode",
        "reset-sample", "boundary", 0, 0, 0.0, "d" * 64,
        (CanonicalEntityLabelV1(1, "panda-main"),),
    )
    raw = canonical.to_mapping()
    decoded = MappingProxyType({
        **raw,
        "labels": tuple(MappingProxyType(dict(item)) for item in raw["labels"]),
    })
    metadata = SimpleNamespace(label_map=decoded, canonical_label_map=canonical)

    assert metadata.label_map != raw
    assert probe._public_label_map_matches(metadata, raw)


def test_public_factory_admits_r04b_config_without_eager_camera_sessions(tmp_path):
    from task_env import make_env

    config, _ = probe.derive_camera_config()
    env = make_env("panda-position-servo-candidate-v1", config={
        "provider": "geophys", "backend": "cpu", "horizon": 16,
        "source_workspace": str(tmp_path / "source"),
        "camera_observation": config,
    })
    try:
        assert env.session is None
        assert env._camera_consumer is None
        assert tuple(env.observation_space.spaces) == (
            "state", "privileged_state", "rgb", "depth", "entity_mask",
        )
        assert env.metadata["info_schema"]["camera_observation_v1"]["required"] is True
    finally:
        env.close()


def test_runner_failure_receipt_preserves_primary_error_and_partial_counts(tmp_path, monkeypatch):
    output = tmp_path / "native"
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.setenv("MUJOCO_GL", "egl")
    monkeypatch.setenv("PYOPENGL_PLATFORM", "egl")
    worktree = Path(__file__).resolve().parents[3]
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join((str(worktree), str(worktree / "GeoPhys" / "src"))))

    def fail_preflight():
        raise ValueError("injected R04b preflight failure")

    monkeypatch.setattr(probe, "derive_camera_config", fail_preflight)
    with pytest.raises(RuntimeError, match="R04b native worker failed"):
        probe.run_s2(output)
    receipt = json.loads((output / "worker_receipt.json").read_text())
    assert receipt["status"] == "R04B_PUBLIC_ENV_TWO_CAMERA_S2_FAIL"
    assert receipt["primary_error"]["message"] == "injected R04b preflight failure"
    assert receipt["counters"]["reset_attempts"] == 0
    assert receipt["counters"]["outer_steps"] == 0
    assert receipt["cleanup_error"] is None
    assert (output / "raw_camera_arrays.npz").is_file()


def test_runner_rejects_nonfresh_output_without_touching_existing_bytes(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "protected.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="fresh"):
        probe.run_s2(output)
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_supervisor_lock_timeout_launches_no_native_worker(tmp_path):
    receipt = supervisor.supervise(
        lock_path=tmp_path / "shared.lock",
        output=tmp_path / "supervisor",
        worker_output=tmp_path / "worker",
        worktree=Path(__file__).resolve().parents[3],
        python=Path("/bin/false"),
        worker_script=Path("/does/not/run.py"),
        wait_lock_s=0,
    )
    assert receipt["status"] == "NOT_RUN_RESOURCE_PENDING"
    assert receipt["lock_acquired"] is False
    assert receipt["native_processes_launched"] == 0
    stored = json.loads((tmp_path / "supervisor" / "launch_receipt.json").read_text())
    assert stored["native_processes_launched"] == 0


def test_offline_reader_failure_path_is_explicit_and_provider_free(tmp_path):
    output = tmp_path / "incomplete"
    output.mkdir()
    (output / "worker_receipt.json").write_text(json.dumps({"status": "FAIL"}), encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        reader.verify(output)
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    process = subprocess.run(
        [sys.executable, str(Path(reader.__file__).resolve()), "--output", str(output)],
        env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert process.returncode == 1
    result = json.loads((output / "offline_readback_receipt.json").read_text())
    assert result["status"] == "R04B_PUBLIC_ENV_TWO_CAMERA_OFFLINE_READBACK_FAIL"
    assert "required R04b evidence file missing" in result["error"]["message"]


def test_runner_json_serializer_handles_arrays_paths_and_bytes_and_rejects_unknown():
    value = probe._json_safe({
        "array": np.asarray([[1, 2]], dtype=np.uint8),
        "path": Path("evidence.bin"),
        "bytes": b"\x00\xff",
    })
    assert value == {"array": [[1, 2]], "path": "evidence.bin", "bytes": {"encoding": "hex", "value": "00ff"}}
    with pytest.raises(TypeError, match="unsupported JSON evidence value"):
        probe._json_safe(object())
