"""Relative public clock for a physical reset that preserves native time."""
from types import SimpleNamespace as NS
import pytest
from task_env.runtime.sessions.mujoco import _MuJoCoSession


def session(native_time, native_steps, control_step):
    value = object.__new__(_MuJoCoSession)
    value._require_reset = lambda: None
    value._data = NS(qpos=[], qvel=[], xpos=[], xquat=[], site_xmat=[], site_xpos=[], time=native_time)
    value._joint_addresses = value._free_addresses = value._bodies = value._frames = {}
    value._mixed_actuator_plan = None
    value._source_bound_reset_clock = True
    value._reset_time_origin = 4.25
    value._native_steps, value._control_step = native_steps, control_step
    value._inner_interval_active = False
    value._artifact = NS(timebase=NS(physics_dt=.002, control_substeps=25, control_dt=.05))
    value._state = lambda joints, velocities, poses, time: NS(simulation_time=time)
    return value


def test_physical_source_clock_preserves_native_origin_and_public_relative_time():
    before, _ = session(4.25, 0, 0)._snapshot_with_native_free_joints()
    after, _ = session(4.30, 25, 1)._snapshot_with_native_free_joints()
    assert before.simulation_time == 0.
    assert after.simulation_time == .05


def test_physical_source_clock_rejects_wrong_native_advance():
    with pytest.raises(ValueError, match='clock or integration count mismatch'):
        session(4.32, 25, 1)._snapshot_with_native_free_joints()
