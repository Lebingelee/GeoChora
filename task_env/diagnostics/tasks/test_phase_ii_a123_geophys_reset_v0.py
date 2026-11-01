"""Core reset regression for the legacy zero-velocity ResetSample v0 route."""

from types import SimpleNamespace

import numpy as np

from task_env.artifacts import PoseWorld
from task_env.artifacts.execution import ResetSample
from task_env.environment.types import EpisodePhysicsState
from task_env.runtime.sessions.geophys import _GeoPhysSession


class _CaptureBoundary:
    def __init__(self):
        self.state = None
        self.static_world_child_poses = None

    def apply_reset_state(
        self, state, *, refresh_actuator_force, static_world_child_poses,
    ):
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
