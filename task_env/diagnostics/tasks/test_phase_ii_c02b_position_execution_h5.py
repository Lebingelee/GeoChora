"""Targeted Position candidate construction, guards, and recorder integrity."""

from types import SimpleNamespace

import numpy as np
import pytest

from task_env.diagnostics.tasks.c02b_position_candidate import build_position_candidate
from task_env.recorders import RecorderConfig, TransitionRecorder
from task_env.tasks.reference_env import SelectedReferenceEnv


def test_explicit_candidate_uses_selected_binding_and_rejects_fixed_seed_before_materialization(tmp_path):
    pytest.importorskip('scene', reason='GeoPhys public Scene importer is required')
    candidate = build_position_candidate(tmp_path / 'candidate', provider='mujoco', horizon=2)
    try:
        env = candidate.env
        assert isinstance(env, SelectedReferenceEnv)
        assert env.binding is not None
        assert env.position_profile is True
        assert env.controller.profile_id == 'panda-main/position-servo-v1'
        with pytest.raises(ValueError, match='fixed ResetPlan'):
            env.reset(seed=candidate.reset_plan.reset_sample.task_seed + 1)
        assert env.session is None
        assert env._closed is False
    finally:
        candidate.env.close()


@pytest.mark.parametrize(
    ('state', 'fault', 'closed', 'stopped', 'session', 'horizon', 'error'),
    [
        (None, None, False, True, None, 10, 'reset required'),
        (SimpleNamespace(control_step=3), None, False, False, object(), 3, 'horizon'),
            (SimpleNamespace(control_step=0), SimpleNamespace(phase='injected', physical_progress='not_advanced'), False, True, object(), 10, 'faulted'),
        (None, None, True, True, None, 10, 'closed'),
    ],
)
def test_position_lifecycle_guards_reject_before_preflight_or_recording(
    monkeypatch, state, fault, closed, stopped, session, horizon, error,
):
    from task_env.runtime.sessions import control as control_sessions

    selected = SimpleNamespace(
        _closed=closed,
        _execution_fault=fault,
        _episode_mode=None,
        _stopped=stopped,
        session=session,
        position_profile=True,
        position_plan=object(),
        horizon=horizon,
        state=state,
        binding=SimpleNamespace(external_actions=True),
        recorder=SimpleNamespace(transition_count=0, observation_count=1),
    )
    selected.recorder_before = (0, 1)
    prepared = []
    monkeypatch.setattr(
        control_sessions, 'prepare_structured_action',
        lambda *_args, **_kwargs: prepared.append(True),
    )
    with pytest.raises(RuntimeError, match=error):
        SelectedReferenceEnv.step(selected, object())
    assert prepared == []
    assert selected.recorder.transition_count == 0
    assert selected.recorder.observation_count == 1


def test_generic_v3_transition_append_capacity_failure_is_atomic():
    recorder = TransitionRecorder(RecorderConfig(schema_version='v3', max_buffer_bytes=64))
    metadata = {
        'env_metadata': {},
        'universal_action_schema': {'dimension': 8},
    }
    recorder.begin_episode(np.zeros(1, dtype=np.float32), {'seed': 31}, metadata)
    before = (recorder.transition_count, recorder.observation_count)
    with pytest.raises(MemoryError, match='max_buffer_bytes'):
        recorder.append_transition(
            np.zeros(8, dtype=np.float32), np.zeros(8, dtype=np.float32),
            np.ones(1, dtype=np.float32), 0.0, False, False, False, {},
        )
    assert (recorder.transition_count, recorder.observation_count) == before == (0, 1)
