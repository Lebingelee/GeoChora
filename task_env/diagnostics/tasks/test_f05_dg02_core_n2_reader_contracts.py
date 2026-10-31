import json

import h5py
import numpy as np

from task_env.diagnostics.tasks.f05_dg02_core_n2_cold_reader import (
    _load_episode,
    _mutate_negative,
    _novel_errors,
    _stored_cube_pose_matches,
)


def _minimal_episode_h5(path, pose):
    with h5py.File(path, "w") as file:
        state = file.create_group("obs/state")
        state.create_dataset("joint_position", data=np.zeros((301, 9), dtype=np.float32))
        state.create_dataset("ee_pose", data=np.zeros((301, 7), dtype=np.float32))
        state.create_dataset("hand_pose", data=np.zeros((301, 7), dtype=np.float32))
        state.create_dataset("boundary_identity_sha256", data=np.zeros((301, 32), dtype=np.uint8))
        privileged = file.create_group("obs/privileged_state")
        privileged.create_dataset("target_body_pose", data=np.broadcast_to(
            np.asarray(pose, dtype=np.float32), (301, 1, 7),
        ).copy())
        for name in ("terminated", "truncated", "success"):
            file.create_dataset(name, data=np.zeros((300,), dtype=np.bool_))
        file.create_dataset("reward", data=np.zeros((300,), dtype=np.float64))
        metrics = file.create_group("info/task_metrics")
        for name in ("free_cube_center_z_m", "lift_threshold_z_m"):
            metrics.create_dataset(name, data=np.zeros((300,), dtype=np.float64))
        for name in ("raw_lift_height_predicate", "lifecycle_terminated"):
            metrics.create_dataset(name, data=np.zeros((300,), dtype=np.bool_))
        file.create_dataset(
            "info/task_metrics/reset_initial_height_already_satisfies_raw_predicate",
            data=np.asarray(False, dtype=np.bool_),
        )
        meta = file.create_group("meta")
        string = h5py.string_dtype(encoding="utf-8")
        for name, value in (
            ("f05_public_typed_state_witness_v1_json", {}),
            ("structured_controls_v1_json", {}),
            ("boundary_events_v1_json", []),
            ("episode_outcome_v1_json", {}),
        ):
            meta.create_dataset(name, data=json.dumps(value), dtype=string)
        meta.create_dataset("env_meta", data="{}", dtype=string)
        meta.create_dataset("env_cfg", data="{}", dtype=string)
        file.create_group("action")
        file.create_group("universal_action")


def test_cold_episode_reader_loads_actual_privileged_cube_pose_leaf(tmp_path):
    expected = np.asarray((0.1, -0.2, 0.3, 1.0, 0.0, 0.0, 0.0), dtype=np.float32)
    path = tmp_path / "episode.h5"
    _minimal_episode_h5(path, expected)

    loaded = _load_episode(path)
    stored = loaded["arrays"]["target_body_pose"]
    cube = {"position": expected[:3], "quaternion_wxyz": expected[3:]}

    assert stored.shape == (301, 1, 7)
    assert stored.dtype == np.dtype("float32")
    assert np.array_equal(stored[100, 0], expected)
    assert _stored_cube_pose_matches(stored[100, 0], cube)

    bundle = {
        "episodes": [{
            "arrays": {"target_body_pose": stored.copy()},
            "identity": {"sha256": loaded["identity"]["sha256"]},
            "worker_h5_sha256": loaded["identity"]["sha256"],
        }],
    }
    _mutate_negative(bundle, "obs_cube_pose")
    mutated = bundle["episodes"][0]
    assert not _stored_cube_pose_matches(mutated["arrays"]["target_body_pose"][100, 0], cube)
    assert mutated["identity"]["sha256"] == "f" * 64
    assert mutated["worker_h5_sha256"] == "f" * 64


def test_negative_attribution_requires_a_finding_beyond_formal_baseline():
    baseline = [
        {"code": "task_predicate", "detail": f"preexisting tracking finding {index}"}
        for index in range(22)
    ]
    unchanged = _novel_errors(list(baseline), baseline)
    mutated = _novel_errors(
        [*baseline, {"code": "obs_cube_pose", "detail": "actual H5 cube leaf differs"}],
        baseline,
    )

    assert unchanged == []
    assert mutated == [{"code": "obs_cube_pose", "detail": "actual H5 cube leaf differs"}]
