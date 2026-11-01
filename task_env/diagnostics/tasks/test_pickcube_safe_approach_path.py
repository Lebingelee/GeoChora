from __future__ import annotations

import numpy as np

from task_env.objects.pick_cube import CUBE_HALF_SIZE
from task_env.tasks.pick_cube.solution import (
    _ABOVE_CLEARANCE,
    _APPROACH_CLEARANCE,
    PickCubeSolution,
)


def test_move_above_cube_clears_vertically_before_lateral_transit():
    start = np.asarray(
        [0.5465, -0.0938, 0.5661, 0.0, 0.7646, 0.6445, 0.0],
        dtype=np.float32,
    )
    cube = np.asarray([0.6351, -0.0865, 0.488], dtype=np.float32)
    observation = {
        "state": {"ee_pose": start},
        "privileged_state": {"cube_v1_body_pose": np.asarray([[*cube, 1, 0, 0, 0]])},
    }

    plan = PickCubeSolution()._plan_move_above(observation, {})
    positions = plan.actions[:, :3]
    target = cube + np.asarray(
        [0.0, 0.0, CUBE_HALF_SIZE + _ABOVE_CLEARANCE], dtype=np.float32,
    )
    clear_z = float(target[2]) + _APPROACH_CLEARANCE
    deltas = np.diff(np.vstack((start[:3], positions)), axis=0)
    lateral = np.flatnonzero(np.linalg.norm(deltas[:, :2], axis=1) > 1e-7)

    assert lateral.size > 0
    first_lateral, last_lateral = int(lateral[0]), int(lateral[-1])
    before_lateral = start[:3] if first_lateral == 0 else positions[first_lateral - 1]
    assert before_lateral[2] >= clear_z - 1e-5
    assert positions[first_lateral, 2] >= clear_z - 1e-5
    assert positions[last_lateral, 2] >= clear_z - 1e-5
    assert np.all(np.abs(deltas[last_lateral + 1 :, :2]) <= 1e-7)
    assert np.allclose(plan.target_pose[:3], target, atol=1e-6)
    assert np.allclose(positions[-1], target, atol=1e-5)
    assert np.isfinite(plan.actions).all()
