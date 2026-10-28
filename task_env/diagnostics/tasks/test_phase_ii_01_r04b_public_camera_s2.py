from __future__ import annotations

import json
import hashlib
import importlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import MappingProxyType, SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest

from task_env.diagnostics.tasks import r04b_native_supervisor as supervisor
from task_env.diagnostics.tasks import r04b_public_camera_offline_readback as reader
from task_env.diagnostics.tasks import r04b_public_camera_s2_probe as probe
from task_env.runtime.sessions.common import _SessionValues


class _SyntheticScheduler:
    def __init__(self):
        self.accepted_substeps = 0

    def step(self, substeps):
        if type(substeps) is not int or substeps <= 0:
            raise ValueError("synthetic runtime boundary requires a positive integer substep count")
        self.accepted_substeps += substeps


class _ProviderFreeRuntimeSession(_SessionValues):
    """Drive the real selected Env/controller/publisher over a fake bottom physics IO."""

    def __init__(self, artifact, source, binding, plan, controller):
        from task_env.runtime.boundary import GeoPhysRuntimeBoundary
        from task_env.runtime.sessions.common import _SessionValues
        from task_env.controllers.canonical.kinematics import (
            PANDA_HAND_ORIGIN_TCP_V1,
            PandaKinematics,
        )
        from task_env.artifacts import PoseWorld

        self._values_owner = _SessionValues
        self._initialize_values(artifact, source, "geophys")
        self._boundary = object.__new__(GeoPhysRuntimeBoundary)
        self._boundary._scheduler = _SyntheticScheduler()
        self._boundary._simulation_time = 0.0
        self._boundary._physics_dt = float(artifact.timebase.physics_dt)
        self._boundary._force_observation_reader = None
        self._plan = plan
        self._controller = controller
        self._control_binding = binding
        self._control_binding_plan = plan
        self._force_feedback_required = False
        self._position_profile_identity = controller.identity
        self._position_profile_id = controller.profile_id
        self._position_writer_id = controller.writer_id
        self._position_binding_identity_hash = plan.identity_hash
        self._position_source_closure_digest = source.source_closure_digest
        self._position_applied_boundary_ids = set()
        self._position_target_in_flight = None
        self._target_actuators = dict(source.joint_targets)
        self._pending_joints = None
        self._joint_positions = {}
        self._joint_velocities = {}
        peg_matrix = probe._pose_from_mjcf_body(
            __import__("xml.etree.ElementTree", fromlist=["fromstring"])
            .fromstring(source.scene_source.xml)
            .find("worldbody/body[@name='peg1']")
        )
        self._PoseWorld = PoseWorld
        from task_env.utils.rotation import matrix_to_quat_wxyz
        self._peg_pose = PoseWorld(
            tuple(float(value) for value in peg_matrix[:3, 3]),
            tuple(float(value) for value in matrix_to_quat_wxyz(peg_matrix[:3, :3])),
        )
        self._kinematics = PandaKinematics(
            source.scene_source.xml, tcp_profile=PANDA_HAND_ORIGIN_TCP_V1,
        )
        from task_env.controllers.canonical.contracts import AppliedCanonicalControl
        self._AppliedCanonicalControl = AppliedCanonicalControl

    def _initialize_values(self, artifact, source, provider):
        self._values_owner._initialize_values(self, artifact, source, provider)

    def reset(self, sample):
        self._begin_reset()
        self._validate_sample(sample)
        self._joint_positions = {key: float(value) for key, value in sample.joint_position.items()}
        self._joint_velocities = {key: 0.0 for key in self._joint_positions}
        self._boundary._simulation_time = 0.0
        self._pending_joints = None
        return self._realized(sample)

    def _poses(self):
        from task_env.utils.rotation import matrix_to_quat_wxyz

        q = np.asarray([
            self._joint_positions[f"panda-main/joint{index}"]
            for index in range(1, 8)
        ], dtype=np.float64)
        world_from_hand, _ = self._kinematics.fk_jacobian(q)
        hand = self._PoseWorld(
            tuple(float(value) for value in world_from_hand[:3, 3]),
            tuple(float(value) for value in matrix_to_quat_wxyz(world_from_hand[:3, :3])),
        )
        return {
            "panda-main/hand": hand,
            "square-peg-instance/peg1": self._peg_pose,
        }

    def _canonical_state(self):
        self._require_reset()
        return self._state(
            dict(self._joint_positions), dict(self._joint_velocities), self._poses(),
            float(self._boundary._simulation_time),
        )

    def snapshot(self):
        return self._canonical_state()

    def _snapshot_with_native_free_joints(self):
        return self._canonical_state(), {}

    def snapshot_v1(self, *, scene, joint_bindings, frame_bindings, requirements):
        selected_frames = {
            key: value for key, value in frame_bindings.items()
            if key in {"panda-main/hand", "square-peg-instance/peg1"}
        }
        return self._values_owner.snapshot_v1(
            self, scene=scene, joint_bindings=joint_bindings,
            frame_bindings=selected_frames, requirements=requirements,
        )

    def apply_control(self, target):
        from task_env.runtime.sessions.control import validate_target

        validate_target(self, target)
        self._pending_joints = {
            key: float(value) for key, value in target.arm_servo_position.items()
        }
        opening = float(target.gripper.servo_opening_m) * 0.5
        self._pending_joints["panda-main/finger_joint1"] = opening
        self._pending_joints["panda-main/finger_joint2"] = opening
        result = self._AppliedCanonicalControl(
            "applied-canonical-control-v0", target.identity_hash, "geophys",
            dict(target.arm_servo_position), float(target.gripper.servo_opening_m),
            float(target.gripper.force_limit_N), False,
            "provider-free-test-IO-only; no physical simulator was created",
        )
        result.validate()
        return result

    def step(self):
        self._require_reset()
        self._boundary.step(substeps=int(self._artifact.timebase.control_substeps))
        if self._pending_joints is not None:
            self._joint_positions.update(self._pending_joints)
            self._pending_joints = None
        self._control_step += 1
        self._state_revision += 1
        return self.snapshot()

    def close(self):
        self._closed = True


class _ProviderFreeCameraSession:
    """Synthetic camera IO carrying real public identities/calibration and seed arrays."""

    def __init__(self, camera, execution, *, source, initial_state, manifest, seed_arrays):
        from task_env.observations.canonical_camera.geometry import resolve_camera

        self._geometry = camera
        self._execution = execution
        self._source = source
        self._manifest = manifest
        self._resolve_camera = resolve_camera
        self._seed_arrays = seed_arrays
        self.consumer_id = f"preflight-consumer-{camera.camera_id}-{uuid4().hex}"
        self._renderer = SimpleNamespace(preflight_renderer_token=uuid4().hex)
        self._closed = False
        self.last_sync = None
        self._captures = 0
        self.close_invocations = 0

    def capture(self, state):
        from task_env.observations.canonical_camera.images import (
            CanonicalCameraObservation,
            CanonicalEntityInstanceSegmentationV1,
            CanonicalEntityLabelMapV1,
            CanonicalEntityLabelV1,
        )

        if self._closed:
            raise RuntimeError("synthetic camera session was closed")
        camera_id = self._geometry.camera_id
        seed_index = probe.CAMERA_IDS.index(camera_id)
        rgb = self._seed_arrays[f"rgb_{seed_index:03d}"].copy()
        depth = self._seed_arrays[f"depth_{seed_index:03d}"].copy()
        mask = self._seed_arrays[f"mask_{seed_index:03d}"].copy()
        step = state.boundary.control_step
        if step:
            delta = np.float32(min(0.20, 0.02 + 0.015 * step))
            rgb[4:7, 4:7, 0] = np.clip(rgb[4:7, 4:7, 0] + delta, 0.0, 1.0)

        metadata = self._resolve_camera(self._geometry, state)
        identity = self._source.capture_identity(
            self._geometry, self._execution, self._manifest, state,
            additional_modalities=("entity_instance_segmentation",),
        )
        entities = sorted(entity.entity_id for entity in self._source.scene_definition.entities)
        label_map = CanonicalEntityLabelMapV1(
            "canonical-entity-label-map-v1", identity.task_artifact_hash,
            state.boundary.scene_identity_hash, identity.render_source_identity_hash,
            camera_id, state.boundary.scene_instance_id,
            state.boundary.provider_materialization_id, state.boundary.episode_id,
            state.boundary.reset_sample_id, state.boundary.boundary_id,
            state.boundary.state_revision, state.boundary.control_step,
            state.sample_clock.simulation_time_s, identity.identity_hash,
            tuple(CanonicalEntityLabelV1(index, entity) for index, entity in enumerate(entities, 1)),
        )
        segmentation = CanonicalEntityInstanceSegmentationV1(
            "canonical-entity-instance-segmentation-v1", mask, 0, label_map,
        )
        peg_pose = next(
            item.pose_world for item in state.frames
            if item.frame.entity_id == "square-peg-instance" and item.frame.frame_id == "peg1"
        )
        transform = np.asarray(metadata.T_camera_from_world, dtype=np.float64)
        camera_point = transform[:3, :3] @ np.asarray(peg_pose.position) + transform[:3, 3]
        # The worker requires a geometry sample at reset and at the target
        # boundary. During intermediate controller states, the hand camera can
        # legitimately point away from the static peg; do not synthesize an
        # impossible in-view landmark sample for those boundaries.
        if camera_point[2] > 0:
            pixel = np.asarray(metadata.K, dtype=np.float64) @ camera_point
            col = int(round(float(pixel[0] / pixel[2]) - 0.5))
            row = int(round(float(pixel[1] / pixel[2]) - 0.5))
            if 0 <= row < probe.HEIGHT and 0 <= col < probe.WIDTH:
                try:
                    expected_depth, _ = probe._ray_box_hit(metadata, peg_pose, row, col)
                except ValueError as exc:
                    if camera_id == probe.FIXED_CAMERA_ID or step in (0, 12):
                        raise ValueError(
                            f"{exc}; synthetic capture camera={camera_id} "
                            f"control_step={step} peg_position={tuple(peg_pose.position)} "
                            f"camera_point={camera_point.tolist()} pixel={pixel.tolist()} row={row} col={col} "
                            f"T_world_from_camera={np.asarray(metadata.T_world_from_camera).tolist()}"
                        ) from exc
                else:
                    depth[row, col] = np.float32(expected_depth)
            elif camera_id == probe.FIXED_CAMERA_ID or step in (0, 12):
                raise ValueError(
                    f"synthetic calibration landmark is outside view: camera={camera_id} "
                    f"control_step={step} camera_point={camera_point.tolist()} pixel={pixel.tolist()}"
                )
        elif camera_id == probe.FIXED_CAMERA_ID or step in (0, 12):
            raise ValueError(
                f"synthetic calibration landmark is behind camera: camera={camera_id} "
                f"control_step={step} camera_point={camera_point.tolist()}"
            )

        self.last_sync = SimpleNamespace(to_mapping=lambda: {
            "schema_version": "render-state-sync-receipt-v1",
            "consumer_id": self.consumer_id,
            "state_boundary": state.boundary.to_mapping(),
            "sample_clock": state.sample_clock.to_mapping(),
            "max_frame_position_error_m": 0.0,
            "max_frame_quaternion_sign_invariant_l2_error": 0.0,
        })
        self._captures += 1
        import mujoco

        # Three calls represent RGB, depth, and Entity-mask renderer passes.
        for _ in range(3):
            mujoco.Renderer.render(self._renderer)
        return CanonicalCameraObservation(rgb, depth, metadata, identity, segmentation)

    def graphics_device_info(self):
        return {
            "render_api": "provider-free synthetic camera IO",
            "observation_scope": "S1 fixture; no GL context or physical evidence",
        }

    def close(self):
        self.close_invocations += 1
        if not self._closed:
            import mujoco

            mujoco.Renderer.close(self._renderer)
            self._closed = True


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


def _write_jsonl(path, rows):
    path.write_text("".join(
        json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in rows
    ), encoding="utf-8")


def _refresh_worker_hashes(output):
    worker_path = output / "worker_receipt.json"
    worker = json.loads(worker_path.read_text(encoding="utf-8"))
    evidence = worker["evidence"]
    evidence["raw_camera_arrays_sha256"] = probe._sha256(output / "raw_camera_arrays.npz")
    for name in ("capture_rows", "boundary_rows", "cache_probes", "control_rows"):
        evidence[name + "_sha256"] = probe._sha256(output / f"{name}.jsonl")
    worker_path.write_text(json.dumps(worker, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _identity_sha256(identity):
    return hashlib.sha256(json.dumps(
        identity, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()


def test_provider_free_complete_worker_success_and_independent_reader_negative_matrix(
    tmp_path, monkeypatch,
):
    """Exercise the real public Env path with fake bottom physics/GL IO only."""
    import mujoco

    maintenance = Path(
        "/home/lly/Program_Files/Geochora/workspace/maintenance/"
        "phase_ii_01_sol_luna_handoff_20261023_001"
    )
    old_root = maintenance / "r04b_001"
    old_manifest = old_root / "evidence_sha256.manifest"
    old_worker = old_root / "native_attempt002" / "worker"
    seed_path = old_worker / "raw_camera_arrays.npz"
    assert probe._sha256(old_manifest) == "4892cfdfcb2fb7a3a58f53c62ebc101cf272756c8461effecc5a06007d178f95"
    old_hashes = {}
    for line in old_manifest.read_text(encoding="utf-8").splitlines():
        digest, relative = line.split("  ", 1)
        old_hashes[relative] = digest
    assert old_hashes["native_attempt002/worker/raw_camera_arrays.npz"] == probe._sha256(seed_path)
    assert old_hashes["native_attempt002/worker/capture_rows.jsonl"] == probe._sha256(
        old_worker / "capture_rows.jsonl"
    )
    seed_npz = np.load(seed_path, allow_pickle=False)
    seed_arrays = {key: seed_npz[key].copy() for key in seed_npz.files}

    preflight = tmp_path
    worker_output = preflight / "worker_success"
    created_envs = []
    synthetic_sessions = []
    factory_calls = {"camera": 0, "fail_on_camera_call": None}

    from task_env import make_env as actual_make_env
    reference_env_module = importlib.import_module("task_env.tasks.reference_env")
    camera_module = importlib.import_module("task_env.render.camera")
    from task_env.runtime.boundary import GeoPhysRuntimeBoundary
    from task_env.controllers.canonical.position_profile import PandaPositionServoProfileV1

    def fake_materialize(artifact, execution, *, source, binding,
                         controller_binding_plan, controller_profile, **_kwargs):
        if isinstance(controller_profile, (tuple, list)):
            if len(controller_profile) != 1:
                raise AssertionError("provider-free fixture only admits the single existing Panda profile")
            controller_profile = controller_profile[0]
        session = _ProviderFreeRuntimeSession(
            artifact, source, binding, controller_binding_plan, controller_profile,
        )
        return session

    def fake_camera_factory(camera, execution, *, source, initial_state, manifest):
        factory_calls["camera"] += 1
        if factory_calls["fail_on_camera_call"] == factory_calls["camera"]:
            raise RuntimeError("injected partial dynamic-camera construction failure")
        session = _ProviderFreeCameraSession(
            camera, execution, source=source, initial_state=initial_state,
            manifest=manifest, seed_arrays=seed_arrays,
        )
        synthetic_sessions.append(session)
        return session

    def tracked_make_env(*args, **kwargs):
        env = actual_make_env(*args, **kwargs)
        created_envs.append(env)
        return env

    def synthetic_renderer_render(_renderer, *_args, **_kwargs):
        return None

    def synthetic_renderer_close(_renderer, *_args, **_kwargs):
        return None

    monkeypatch.setattr("task_env.make_env", tracked_make_env)
    monkeypatch.setattr(reference_env_module, "materialize_control", fake_materialize)
    monkeypatch.setattr(camera_module, "create_dynamic_camera_session", fake_camera_factory)
    monkeypatch.setattr(mujoco.Renderer, "render", synthetic_renderer_render)
    monkeypatch.setattr(mujoco.Renderer, "close", synthetic_renderer_close)
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.setenv("MUJOCO_GL", "egl")
    monkeypatch.setenv("PYOPENGL_PLATFORM", "egl")
    worktree = Path(__file__).resolve().parents[3]
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join((str(worktree), str(worktree / "GeoPhys" / "src"))))
    frozen_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=worktree, text=True).strip()
    monkeypatch.setenv("R04B_FROZEN_HEAD", frozen_head)

    provenance = {
        "schema_version": "r04b-provider-free-synthetic-preflight-v1",
        "status": "SYNTHETIC_ONLY_NOT_PHYSICAL_EVIDENCE",
        "real_reset_capture_source": str(seed_path),
        "old_manifest_sha256": probe._sha256(old_manifest),
        "seed_npz_sha256": probe._sha256(seed_path),
        "synthetic_routes": [
            "all post-reset camera arrays after the two actual reset seeds",
            "provider-free scheduler accepts the real TaskEnv runtime-boundary step call",
            "no GeoPhys materialization, MuJoCo Renderer, OpenGL context, or physical simulation",
        ],
    }
    (preflight / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    assert probe.main(["--output", str(worker_output)]) == 0
    success = json.loads((worker_output / "worker_receipt.json").read_text(encoding="utf-8"))
    assert success["status"] == "R04B_PUBLIC_ENV_TWO_CAMERA_S2_PASS"
    assert success["counters"]["clock_inferred_substeps"] == 120
    assert success["counters"]["accepted_physics_substeps"] == 120
    assert success["counters"]["native_renderer_close_counts"]
    assert all(value == 1 for value in success["counters"]["native_renderer_close_counts"].values())
    assert sorted(success["counters"]["camera_session_close_counts"].values()) == [1, 1, 1, 2]
    assert all((worker_output / f"{name}.jsonl").is_file() for name in (
        "capture_rows", "boundary_rows", "cache_probes", "control_rows",
    ))
    assert len(synthetic_sessions) == 4
    before_already_closed_env_call = [session.close_invocations for session in synthetic_sessions]
    created_envs[0].close()
    assert [session.close_invocations for session in synthetic_sessions] == before_already_closed_env_call

    reader_path = Path(reader.__file__).resolve()
    provider_free_environment = dict(os.environ)
    provider_free_environment.pop("PYTHONPATH", None)
    provider_free_environment["PYTHONDONTWRITEBYTECODE"] = "1"
    positive_process = subprocess.run(
        [sys.executable, "-I", "-B", str(reader_path), "--output", str(worker_output),
         "--evidence-root", str(preflight)],
        cwd=preflight, env=provider_free_environment,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert positive_process.returncode == 0, positive_process.stdout + positive_process.stderr
    positive_receipt = json.loads((worker_output / "offline_readback_receipt.json").read_text())
    assert positive_receipt["provider_modules_imported"] is False
    assert positive_receipt["taskenv_modules_imported"] is False
    assert positive_receipt["raw_capture_rows"] == 53
    assert positive_receipt["public_boundaries"] == 26
    assert positive_receipt["cache_probes"] == 26

    negative_output = preflight / "negative_reader_working"
    shutil.copytree(worker_output, negative_output)
    baseline_files = {
        name: (negative_output / name).read_bytes()
        for name in (
            "worker_receipt.json", "raw_camera_arrays.npz", "capture_rows.jsonl",
            "boundary_rows.jsonl", "cache_probes.jsonl", "control_rows.jsonl",
        )
    }

    def restore_negative_bundle():
        for name, payload in baseline_files.items():
            (negative_output / name).write_bytes(payload)

    def mutate_mask(rows, boundaries, controls, worker):
        archive = np.load(negative_output / "raw_camera_arrays.npz", allow_pickle=False)
        arrays = {key: archive[key].copy() for key in archive.files}
        mask_key = rows[0]["array_keys"]["mask"]
        arrays[mask_key][0, 0] = np.uint32(999)
        with (negative_output / "raw_camera_arrays.npz").open("wb") as stream:
            np.savez(stream, **arrays)
        digest = hashlib.sha256(np.ascontiguousarray(arrays[mask_key]).tobytes(order="C")).hexdigest()
        rows[0]["mask_sha256"] = digest
        rows[0]["public_capture_metadata"]["mask_sha256"] = digest

    def mutate_capture_identity(rows, boundaries, controls, worker):
        identity = rows[0]["capture_identity"]
        identity["camera_id"] = "d04-unrequested-camera"
        identity_hash = _identity_sha256(identity)
        rows[0]["capture_identity_identity_hash"] = identity_hash
        rows[0]["label_map"]["capture_identity_hash"] = identity_hash
        rows[0]["public_capture_metadata"]["capture_identity"] = identity
        rows[0]["public_capture_metadata"]["label_map"] = rows[0]["label_map"]

    def mutate_typed_clock(rows, boundaries, controls, worker):
        boundaries[0]["sample_clock"]["simulation_time_s"] = 0.001

    def mutate_state_boundary(rows, boundaries, controls, worker):
        boundaries[0]["state_boundary"]["boundary_id"] = "corrupted-boundary"

    def mutate_parent_frame(rows, boundaries, controls, worker):
        calibration = rows[0]["calibration"]
        camera = calibration["camera"]
        world_from_camera = np.asarray(calibration["T_world_from_camera"], dtype=np.float64)
        world_from_camera[0, 3] += 0.01
        calibration["T_world_from_camera"] = world_from_camera.tolist()
        calibration["T_camera_from_world"] = np.linalg.inv(world_from_camera).tolist()
        calibration["T_world_from_mount"] = (
            world_from_camera @ np.linalg.inv(np.asarray(camera["T_mount_from_camera"], dtype=np.float64))
        ).tolist()
        rows[0]["public_capture_metadata"]["calibration"] = calibration

    def mutate_label_map(rows, boundaries, controls, worker):
        rows[0]["label_map"]["labels"][0]["entity_id"] = "noncanonical-entity"
        rows[0]["public_capture_metadata"]["label_map"] = rows[0]["label_map"]

    def remove_boundary(rows, boundaries, controls, worker):
        boundaries.pop()

    def duplicate_boundary(rows, boundaries, controls, worker):
        boundaries.append(dict(boundaries[0]))

    def mutate_target_ack(rows, boundaries, controls, worker):
        key = (controls[0]["round_index"], controls[0]["control_step"])
        controls[0]["applied"]["target_hash"] = "0" * 64
        controls[0]["applied_target_hash"] = "0" * 64
        for boundary in boundaries:
            if (boundary["round_index"], boundary["boundary_index"]) == key:
                boundary["control_transition"] = controls[0]
                break

    def mutate_close_count(rows, boundaries, controls, worker):
        token = next(iter(worker["counters"]["native_renderer_close_counts"]))
        worker["counters"]["native_renderer_close_counts"][token] = 2

    def failure_receipt_claims_pass(rows, boundaries, controls, worker):
        worker["primary_error"] = {"type": "InjectedFailure", "message": "must not pass readback"}

    mutations = (
        ("bad-mask-with-recomputed-hash", mutate_mask, "mask leaks a native geometry ID"),
        ("bad-capture-identity-with-recomputed-digest", mutate_capture_identity, "identity is not bound to the public candidate route"),
        ("bad-typed-clock", mutate_typed_clock, "typed boundary/clock/reset identity is inconsistent"),
        ("bad-state-boundary", mutate_state_boundary, "capture identity boundary/clock differs"),
        ("bad-parent-frame", mutate_parent_frame, "world extrinsic disagrees with its typed parent Frame"),
        ("bad-label-map", mutate_label_map, "label map includes a non-canonical Entity ID"),
        ("missing-boundary", remove_boundary, "expected two 13-boundary episodes and one cache probe per public boundary"),
        ("duplicate-boundary", duplicate_boundary, "expected two 13-boundary episodes and one cache probe per public boundary"),
        ("bad-target-ack", mutate_target_ack, "Position applied acknowledgement targets a different canonical Controller target"),
        ("bad-close-count", mutate_close_count, "stable renderer lifecycle token exactly once"),
        ("failure-receipt-claims-pass", failure_receipt_claims_pass, "execution or cleanup error"),
    )
    matrix = []
    for case_id, mutation, expected_message in mutations:
        restore_negative_bundle()
        capture_rows = [json.loads(line) for line in (negative_output / "capture_rows.jsonl").read_text().splitlines()]
        boundary_rows = [json.loads(line) for line in (negative_output / "boundary_rows.jsonl").read_text().splitlines()]
        control_rows = [json.loads(line) for line in (negative_output / "control_rows.jsonl").read_text().splitlines()]
        worker = json.loads((negative_output / "worker_receipt.json").read_text())
        mutation(capture_rows, boundary_rows, control_rows, worker)
        _write_jsonl(negative_output / "capture_rows.jsonl", capture_rows)
        _write_jsonl(negative_output / "boundary_rows.jsonl", boundary_rows)
        _write_jsonl(negative_output / "control_rows.jsonl", control_rows)
        (negative_output / "worker_receipt.json").write_text(
            json.dumps(worker, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        _refresh_worker_hashes(negative_output)
        process = subprocess.run(
            [sys.executable, "-I", "-B", str(reader_path), "--output", str(negative_output),
             "--evidence-root", str(preflight)],
            cwd=preflight, env=provider_free_environment,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        rejected = json.loads((negative_output / "offline_readback_receipt.json").read_text())
        message = rejected["error"]["message"]
        assert process.returncode == 1, (case_id, process.stdout, process.stderr)
        assert expected_message in message, (case_id, expected_message, message)
        matrix.append({"case_id": case_id, "return_code": process.returncode, "rejected": True,
                       "error_message": message, "reader_sha256": probe._sha256(reader_path)})

    (preflight / "negative_reader_matrix.json").write_text(
        json.dumps({"schema_version": "r04b-reader-negative-matrix-v1", "cases": matrix},
                   indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    restore_negative_bundle()
    assert len(matrix) >= 10

    # The second Env.close() call is already-closed and must not close any
    # consumer or Renderer again; the receipt records the one worker call.
    assert json.loads((worker_output / "worker_receipt.json").read_text())["env_close_calls"] == 1

    # ExitStack restored all monkeypatches even after the complete positive run.
    assert mujoco.Renderer.render is synthetic_renderer_render
    assert mujoco.Renderer.close is synthetic_renderer_close
    assert GeoPhysRuntimeBoundary.step.__name__ == "step"
    assert PandaPositionServoProfileV1.compute.__name__ == "compute"

    # A failure during construction of the second real consumer preserves its
    # partial close and writes all empty/partial JSONL files plus a FAIL receipt.
    factory_calls.update(camera=0, fail_on_camera_call=2)
    partial_output = preflight / "partial_construction_worker"
    assert probe.main(["--output", str(partial_output)]) == 1
    partial = json.loads((partial_output / "worker_receipt.json").read_text())
    assert partial["status"] == "R04B_PUBLIC_ENV_TWO_CAMERA_S2_FAIL"
    assert partial["counters"]["reset_attempts"] == 1
    assert partial["counters"]["renderer_capture_calls"] == 0
    assert partial["counters"]["native_renderer_close_calls"] == 1
    assert partial["counters"]["native_renderer_close_counts"] == {"renderer-01": 1}
    assert all((partial_output / f"{name}.jsonl").is_file() for name in (
        "capture_rows", "boundary_rows", "cache_probes", "control_rows",
    ))
    assert all((partial_output / f"{name}.jsonl").stat().st_size == 0 for name in (
        "capture_rows", "boundary_rows", "cache_probes", "control_rows",
    ))
    assert GeoPhysRuntimeBoundary.step.__name__ == "step"
