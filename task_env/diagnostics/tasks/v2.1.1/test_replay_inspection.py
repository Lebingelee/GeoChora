"""Replay format inspection is offline and does not grant replay eligibility."""
import h5py
import pytest

from task_env.trajectory.reference_replay import inspect_selected_replay, reexecute_selected


@pytest.mark.parametrize('schema,supported', [
    ('task-env-canonical-trajectory-v0', True),
    ('task-env-canonical-execution-v1', True),
    ('task-env-canonical-execution-v2', True),
    ('task-env-canonical-trajectory-v1', False),
    ('task-env-canonical-execution-v3', False),
    ('unknown', False),
])
def test_offline_format_inspection_does_not_claim_identity(tmp_path, schema, supported):
    path = tmp_path / 'record.h5'
    with h5py.File(path, 'w') as handle:
        handle.attrs['schema'] = schema
    result = inspect_selected_replay(path)
    assert result['format_supported_for_reexecution'] is supported
    assert result['source_identity_checked'] is False
    if not supported:
        with pytest.raises(ValueError, match=result['reason']):
            reexecute_selected(path, output=tmp_path / 'replay.h5')


def test_foreign_runtime_source_is_rejected_before_environment_construction(tmp_path, monkeypatch):
    import task_env
    from task_env.trajectory import reference_replay
    from task_env.tasks.pick_cube.task import REFERENCE_ENV_ID

    path = tmp_path / 'record.h5'
    with h5py.File(path, 'w') as handle:
        handle.attrs['schema'] = 'task-env-canonical-execution-v2'
    monkeypatch.setattr(reference_replay, 'load_streaming', lambda _path: {
        'metadata': {'source_provenance': {'interval_source': '0' * 64}},
        'recipe': {'execution_configuration': {'env_id': REFERENCE_ENV_ID}},
        'transitions': [],
    })
    def unexpected_make_env(*args, **kwargs):
        pytest.fail('foreign-source replay attempted to construct an environment')
    monkeypatch.setattr(task_env, 'make_env', unexpected_make_env)
    with pytest.raises(ValueError, match='runtime interval source identity mismatch'):
        reexecute_selected(path, output=tmp_path / 'out.h5')
