"""Core reset regression for the legacy zero-velocity ResetSample v0 route."""

from types import SimpleNamespace

import numpy as np
import pytest

from task_env.artifacts import PoseWorld
from task_env.artifacts.execution import ResetSample, ResetSampleV1
from task_env.environment.types import EpisodePhysicsState
from task_env.runtime.sessions.geophys import _GeoPhysSession


class _CaptureBoundary:
    def __init__(self):
        self.state = None
        self.static_world_child_poses = None
        self.reset_calls = 0

    def apply_reset_state(
        self, state, *, refresh_actuator_force, static_world_child_poses,
    ):
        self.reset_calls += 1
        self.state = state
        self.static_world_child_poses = static_world_child_poses
        return None


def test_geophys_reset_v0_uses_zero_velocities_and_omits_fixture_poses():
    artifact_hash = "a" * 64
    cube_pose = PoseWorld((0.2, 0.1, 0.3), (1.0, 0.0, 0.0, 0.0))
    sample = ResetSample.create(
        schema_version="reset-sample-v0",
        task_artifact_hash=artifact_hash,
        sampler_id="a123-legacy-reset",
        sampler_version="v0",
        task_seed=19,
        joint_position={"hinge": 0.25},
        poses_world={"cube": cube_pose},
        velocity_policy="zero_named_joint_and_entity_velocities",
        control_policy="arm_targets_at_initial_joints_gripper_open",
        settle_steps=0,
    )

    session = object.__new__(_GeoPhysSession)
    session._provider = "geophys"
    session._closed = False
    session._artifact = SimpleNamespace(identity_hash=artifact_hash)
    session._source = SimpleNamespace(
        joints={"hinge": "hinge"},
        free_joints={"cube": "cube_free"},
        fixture_bodies={"fixture": "fixture"},
        mixed_actuator_plan=None,
    )
    session._mixed_actuator_plan = None
    session._initial = EpisodePhysicsState(
        np.zeros(8), np.full(7, 3.0), np.zeros(7), np.zeros(1), np.zeros(0),
    )
    session._joint_addresses = {"hinge": (0, 0)}
    session._free_addresses = {"cube": (1, 1)}
    session._target_actuators = {"hinge": 0}
    session._position_actuators = {}
    session._open_actuators = ()
    session._ctrl_range = np.zeros((1, 2))
    session._fixture_bodies = {"fixture": 2}
    session._boundary = _CaptureBoundary()
    session._realized = lambda _sample: "realized"
    session._reset_force_measurement = None
    session._last_actuator_force_measurement = None
    session._last_typed_force_publication = None
    session._last_reset_readback_v1 = None

    assert session.reset(sample) == "realized"
    assert session._boundary.state.qpos[0] == 0.25
    assert np.allclose(
        session._boundary.state.qpos[1:8],
        (*cube_pose.position, *cube_pose.quaternion_wxyz),
        rtol=0.0, atol=1.0e-7,
    )
    assert np.array_equal(session._boundary.state.qvel, np.zeros(7))
    assert session._boundary.static_world_child_poses == {}


def test_geophys_reset_v1_validates_source_and_applies_explicit_fixture_pose():
    artifact_hash = "a" * 64
    source_hash = "b" * 64
    closure_hash = "c" * 64
    scene_source_id = f"scene-definition-v3:{source_hash}"
    cube_pose = PoseWorld((0.2, 0.1, 0.3), (1.0, 0.0, 0.0, 0.0))
    fixture_pose = PoseWorld((0.7, -0.2, 0.4), (0.9238795325, 0.0, 0.0, 0.3826834324))
    sample = ResetSampleV1.create(
        schema_version="reset-sample-v1",
        task_artifact_hash=artifact_hash,
        source_id=scene_source_id,
        source_closure_digest=closure_hash,
        sampler_id="a123-source-bound-reset",
        sampler_version="v1",
        task_seed=19,
        init_row_index=0,
        init_row_sha256="d" * 64,
        joint_position={"hinge": 0.25},
        joint_velocity={"hinge": 0.0},
        sampled_poses_world={"cube": cube_pose},
        poses_world={"cube": cube_pose},
        free_joint_velocity={"cube": (0.0,) * 6},
        free_joint_velocity_frame="mujoco_world_linear_local_angular_v1",
        fixture_pose_world={"fixture": fixture_pose},
        simulation_time_s=0.0,
        velocity_policy="named_qvel_and_free_joint_qvel_v1",
        control_policy="named_mixed_actuator_channels_by_source_v1",
        initialization_order=(
            "sample_source_properties", "native_preprocess", "sample_task_placements",
            "restore_source_bound_state", "forward_derived_state",
        ),
        settle_steps=0,
    )

    session = object.__new__(_GeoPhysSession)
    session._provider = "geophys"
    session._closed = False
    session._artifact = SimpleNamespace(identity_hash=artifact_hash)
    session._source = SimpleNamespace(
        joints={"hinge": "hinge"},
        free_joints={"cube": "cube_free"},
        fixture_bodies={"fixture": "fixture"},
        scene_source=SimpleNamespace(source_id=scene_source_id),
        source_closure_digest=closure_hash,
        mixed_actuator_plan=object(),
    )
    session._mixed_actuator_plan = session._source.mixed_actuator_plan
    session._initial = EpisodePhysicsState(
        np.zeros(8), np.full(7, 3.0), np.zeros(7), np.zeros(1), np.zeros(0),
    )
    session._joint_addresses = {"hinge": (0, 0)}
    session._free_addresses = {"cube": (1, 1)}
    session._target_actuators = {"hinge": 0}
    session._position_actuators = {}
    session._open_actuators = ()
    session._ctrl_range = np.zeros((1, 2))
    session._fixture_bodies = {"fixture": 0}
    session._body_parentid = np.asarray([-1])
    session._body_jntnum = np.asarray([0])
    session._boundary = _CaptureBoundary()
    session._provider_materialization_id = "provider-materialization-v1"
    session._episode_id = "episode-v1"
    session._reset_sample_id = sample.sample_id
    session._reset_plan_gate_required = False
    session._reset_plan_gate_open = False
    session._reset_plan_evidence = None
    session._mixed_consumed_boundaries = set()
    session._native_steps = 0
    session._mixed_pending_target = None
    session._mixed_fault = None
    session._last_reset_readback_v1 = None
    session._reset_force_measurement = None
    session._last_actuator_force_measurement = None
    session._last_typed_force_publication = None
    session._realized = lambda _sample: "realized"
    state = SimpleNamespace(
        simulation_time=0.0,
        joint_position={"hinge": 0.25},
        joint_velocity={"hinge": 0.0},
        pose_world={"cube": cube_pose},
    )
    session._snapshot_with_native_free_joints = lambda: (
        state,
        {"cube": (
            (*cube_pose.position, *cube_pose.quaternion_wxyz),
            (0.0,) * 6,
        )},
    )
    session._fixture_pose_readback = lambda _name: fixture_pose

    assert session.reset(sample) == "realized"
    assert session._boundary.reset_calls == 1
    assert session._boundary.state.qpos[0] == 0.25
    assert np.array_equal(session._boundary.state.qvel, np.zeros(7))
    assert set(session._boundary.static_world_child_poses) == {0}
    realized_position, realized_quaternion = session._boundary.static_world_child_poses[0]
    assert np.array_equal(realized_position, np.asarray(fixture_pose.position, dtype=np.float32))
    assert np.array_equal(
        realized_quaternion,
        np.asarray(fixture_pose.quaternion_wxyz, dtype=np.float32),
    )
    assert session.reset_readback_v1["fixture_pose_world"]["fixture"] == {
        "position_m": list(fixture_pose.position),
        "quaternion_wxyz": list(fixture_pose.quaternion_wxyz),
    }

    wrong_source_values = sample.to_mapping()
    wrong_source_values["source_id"] = f"scene-definition-v3:{'e' * 64}"
    wrong_source = ResetSampleV1.create(**wrong_source_values)
    with pytest.raises(ValueError, match="ResetSampleV1 source/closure identity mismatch"):
        session.reset(wrong_source)
    assert session._boundary.reset_calls == 1
