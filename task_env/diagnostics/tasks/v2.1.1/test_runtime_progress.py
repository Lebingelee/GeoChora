"""Provider-free checks for source-bound mixed progress projections."""
from types import SimpleNamespace

import pytest

from task_env.runtime.sessions.geophys import _GeoPhysSession
from task_env.runtime.sessions.mujoco import _MuJoCoSession


def _session(cls):
    session = object.__new__(cls)
    session._mixed_actuator_plan = SimpleNamespace(identity_hash='plan')
    session._provider_materialization_id = 'materialization'
    session._episode_id = 'episode'
    session._reset_sample_id = 'reset'
    session._reset_count = 2
    session._control_step = 3
    session._state_revision = 4
    session._native_steps = 15
    session._source = SimpleNamespace(scene_source=SimpleNamespace(source_id='source'),
                                      source_closure_digest='closure')
    return session


def test_mixed_progress_keeps_provider_clocks_and_adapter_facts_distinct():
    mujoco = _session(_MuJoCoSession)
    mujoco._data = SimpleNamespace(time=.137)
    mujoco._reset_time_origin = .017
    mujoco._preprocess_calls, mujoco._forward_calls = 4, 5
    mujoco._physical_monitor = {'status': 'passed', 'samples': [1]}
    geophys = _session(_GeoPhysSession)
    snapshots = []
    geophys.snapshot = lambda: snapshots.append(True) or SimpleNamespace(simulation_time=.119)
    left, right = mujoco.runtime_progress_receipt, geophys.runtime_progress_receipt
    common = {'schema_version': 'runtime-progress-v1', 'provider_materialization_id': 'materialization',
              'episode_id': 'episode', 'reset_sample_id': 'reset', 'reset_count': 2,
              'control_step': 3, 'state_revision': 4, 'native_step_count': 15,
              'source_id': 'source', 'source_closure_digest': 'closure', 'plan_identity_hash': 'plan'}
    assert all(left[key] == right[key] == value for key, value in common.items())
    assert left['simulation_time_native_s'] == .137
    assert left['simulation_time_episode_s'] == .137 - .017
    assert right['simulation_time_native_s'] == right['simulation_time_episode_s'] == .119
    assert (left['preprocess_call_count'], left['forward_call_count']) == (4, 5)
    assert 'preprocess_call_count' not in right and 'physical_state_monitor' not in right
    left['physical_state_monitor']['samples'].append(2)
    assert mujoco._physical_monitor['samples'] == [1]
    geophys._control_step, geophys._state_revision = 4, 5
    assert geophys.runtime_progress_receipt['control_step'] == 4
    assert len(snapshots) == 2


@pytest.mark.parametrize('cls', [_MuJoCoSession, _GeoPhysSession])
def test_mixed_progress_rejects_unadmitted_route_before_readback(cls):
    session = _session(cls)
    session._mixed_actuator_plan = None
    session.snapshot = lambda: pytest.fail('unadmitted route read the native state')
    with pytest.raises(RuntimeError, match='mixed runtime progress is unavailable'):
        session.runtime_progress_receipt
