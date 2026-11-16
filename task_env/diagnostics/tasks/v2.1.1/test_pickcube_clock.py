"""PickCube readiness accepts native rounding but rejects stale boundaries."""
from types import SimpleNamespace

import pytest

from task_env.tasks.pick_cube.solution import PickCubePositionExecutionInfoV1, PickCubeReadinessSolution


def _info(step, clock):
    return PickCubePositionExecutionInfoV1('pickcube-position-execution-info-v1', step, clock,
                                            0.08, 0., 0.08, False)


def test_native_five_substep_rounding_and_stale_clock_rejection():
    solution = object.__new__(PickCubeReadinessSolution)
    solution.readiness_config = SimpleNamespace(control_dt=0.01, physics_dt=0.002, control_substeps=5)
    solution._execution(_info(0, 0.), reset=True)
    clock = 0.
    for step in range(1, 1001):
        for _ in range(5):
            clock += 0.002
        solution._execution(_info(step, clock))
    with pytest.raises(ValueError, match='stale execution time'):
        solution._execution(_info(1001, clock + 0.009))
    with pytest.raises(ValueError, match='stale/skipped execution boundary'):
        solution._execution(_info(1002, clock + 0.01))
