"""Closure readiness permits an occupied gripper, without claiming a grasp."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from task_env.tasks.pick_cube.solution import (
    PickCubePositionExecutionInfoV1, PickCubePositionExecutionInfoV2, PickCubeReadinessSolution,
)


def _readback(step=1, *, opening=.053632, speed=.002025, target=0.):
    return PickCubePositionExecutionInfoV2('pickcube-position-execution-info-v2', step, step*.01,
        opening, speed, target, PickCubePositionExecutionInfoV2.closure_is_ready(target, opening, speed))


def test_recorded_occupied_width_is_settled_but_old_contract_stays_false():
    assert _readback().close_ready
    old = PickCubePositionExecutionInfoV1('pickcube-position-execution-info-v1', 1, .01,
                                         .053632, .002025, 0., False)
    old.validate()
    assert not old.close_ready
    assert _readback(opening=0., speed=0.).close_ready  # Readiness is not grasp detection.
    for kwargs in ({'target': .04}, {'opening': .08}, {'speed': .006}):
        assert not _readback(**kwargs).close_ready
    with pytest.raises(ValueError, match='readiness'):
        replace(_readback(), close_ready=False)
    with pytest.raises(ValueError, match='finite'):
        _readback(speed=float('nan'))


def test_solution_requires_consecutive_settling_and_resets_on_motion():
    solution = object.__new__(PickCubeReadinessSolution)
    solution.readiness_config = SimpleNamespace(control_dt=.01, physics_dt=.002, control_substeps=5,
        measured_tcp_clearance_gate=False,
        policies=[SimpleNamespace(kind='gripper_ready', hold_ticks=100, failure_reason='timeout')])
    solution._segments = [SimpleNamespace(name='close', plan=SimpleNamespace(actions=[0]))]
    solution._segment_index, solution._action_index = 0, 1
    solution._boundary_step, solution._boundary_time = 0, 0.
    solution._position_close_settled_ticks = 0
    solution.total_control_actions_emitted = solution.readiness_wait_actions_emitted = 0
    solution.planned_actions_emitted = solution._wait_count = 0
    solution.completion_events = []
    solution._refresh_current_segment = lambda observation, info: None
    for step in range(1, 11):
        solution._awaiting_observation = solution._last_wait = True
        solution._last_measured_tcp_gate_hold = False
        sample = _readback(step, speed=.01 if step == 5 else .002)
        solution.observe({}, 0., False, False, {'pickcube_position_execution_info_v2': sample.to_mapping()})
        assert solution._segment_index == (1 if step == 10 else 0)
    assert len(solution.completion_events) == 1
