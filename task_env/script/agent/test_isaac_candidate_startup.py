"""Exercise native startup ordering without importing or starting Kit."""
from pathlib import Path
import json
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import candidate_worker
import builtin_example_validation as validation
import task_env.runtime.sessions.isaac_native_io as native_io


@pytest.mark.parametrize('startup_fails', (False, True))
def test_candidate_opens_app_before_usd_compile_and_closes_on_failure(tmp_path, startup_fails):
    events = []

    class AppOwner:
        def open(self):
            events.append('app_open')
            if startup_fails:
                raise RuntimeError('startup sentinel')

        def launch_profile_receipt(self):
            return {'profile_id': 'f06-headless-no-render-v1'}

        def close(self):
            events.append('app_close')

        def close_receipt(self):
            return {'close_attempted': True, 'close_completed': True}

    def compile_candidate(*_args, **_kwargs):
        events.append('source_compile')
        assert events == ['app_open', 'source_compile']
        raise RuntimeError('compile sentinel')

    with patch.object(candidate_worker, 'core_context', return_value={
        'core_commit': 'commit', 'core_dirty': False,
    }), patch.object(native_io, '_process_app_owner', return_value=AppOwner()), \
         patch.object(candidate_worker, 'compile_candidate', side_effect=compile_candidate):
        receipt, code = candidate_worker.run_worker(
            mode='probe', spec=SimpleNamespace(horizon=5), catalog={'core_repo': '/core'},
            provider='isaacsim', seed=31, horizon=5, output=tmp_path,
        )

    expected = ['app_open', 'app_close'] if startup_fails else ['app_open', 'source_compile', 'app_close']
    assert events == expected
    assert code == 1
    assert receipt['errors'][0]['phase'] == ('app_open' if startup_fails else 'compile')
    assert receipt['app']['close_receipt']['close_completed'] is True
    assert not receipt['row_written']
    assert not (tmp_path / 'row.json').exists()


def test_runtime_configuration_honors_explicit_environment(monkeypatch, tmp_path):
    cpu = tmp_path / 'core-python'
    isaac = tmp_path / 'isaac-python'
    lock = tmp_path / 'shared' / 'native.lock'
    monkeypatch.setenv('GEOCHORA_CORE_PYTHON', str(cpu))
    monkeypatch.setenv('GEOCHORA_ISAAC_PYTHON', str(isaac))
    monkeypatch.setenv('GEOCHORA_NATIVE_LOCK', str(lock))
    assert validation.core_python() == cpu
    assert validation.isaac_python() == isaac
    assert validation.native_lock_path() == lock
    assert lock.parent.is_dir()


def test_candidate_and_builtin_share_runtime_configuration():
    import native_candidate_runner as runner
    assert runner.isaac_python is validation.isaac_python
    assert runner.native_lock_path is validation.native_lock_path


def test_checked_in_working_tree_scope_admits_a_clean_checkout():
    from builtin_example_schema import ExampleWorkingTreeScopeV1
    scope = ExampleWorkingTreeScopeV1.load(
        Path(__file__).resolve().parents[3] / 'examples/tasks/pick_cube_harness_working_tree_scope.json'
    )
    assert scope.expected_untracked == ()


def test_supervisor_preserves_worker_compilation_identity(tmp_path, monkeypatch):
    from builtin_example_schema import BuiltinPickCubeExampleV1, ExampleWorkingTreeScopeV1

    monkeypatch.setattr(validation, 'CORE', tmp_path)
    monkeypatch.setenv('GEOCHORA_NATIVE_LOCK', str(tmp_path / 'native.lock'))
    spec = BuiltinPickCubeExampleV1.load(
        Path(__file__).resolve().parents[3] / 'examples/tasks/pick_cube_harness.json'
    )
    spec_path, catalog_path, scope_path = (tmp_path / name for name in ('spec.json', 'catalog.json', 'scope.json'))
    spec_path.write_text(json.dumps(spec.to_dict()))
    catalog_path.write_text('{}')
    scope_path.write_text(json.dumps(ExampleWorkingTreeScopeV1(
        'harness-example-working-tree-scope-v1', (),
    ).to_dict()))
    output = tmp_path / 'seed_31'
    compiled = {'artifact_sha256': 'a' * 64, 'source_revision': 'commit'}

    def launch(*_args, **_kwargs):
        (output / 'run.json').write_text(json.dumps({
            'runtime_valid': True, 'compiled': compiled, 'task_outcome': 'TASK_OR_EXPERT_FAILURE_REPORTED',
        }))
        return SimpleNamespace(pid=99999999, poll=lambda: 0, wait=lambda: 0)

    with patch.object(validation, '_mem_available_bytes', return_value=10 * 1024**3), \
         patch.object(validation.subprocess, 'Popen', side_effect=launch), \
         patch.object(validation.os, 'killpg', side_effect=ProcessLookupError), \
         patch.object(validation, '_cold_read_h5', return_value={'status': 'PASS'}):
        row = validation._run_one(spec_path, catalog_path, scope_path, 31, output, provider='mujoco')
    assert row['compiled'] == compiled
    assert row['runtime_valid'] is True
    assert row['worker_process_group_ended'] is True


@pytest.mark.parametrize('actual_seed', (31, 32))
def test_oracle_binds_position_recording_without_mixed_control_metadata(tmp_path, actual_seed):
    import oracle_candidate as oracle

    events = []
    execution = SimpleNamespace(identity_hash='execution', physics_provider='isaacsim',
                                physics_backend='cuda', physics_device='cuda:0')
    sample = SimpleNamespace(task_seed=actual_seed, sample_id='sample')
    source = SimpleNamespace(source_id='source', source_closure_digest='closure')

    class Env:
        def __init__(self, **_kwargs):
            self.value = {'f06_pickcube_isaac_input': SimpleNamespace(
                execution=execution, delivery_manifest_sha256='manifest'),
                'reset_plan': SimpleNamespace(identity_hash='reset', reset_sample=sample),
                'source': source}
            self.controller = SimpleNamespace(identity='controller')
            self.solution = SimpleNamespace(identity='solution')
            self.execution_fault = None

        def reset(self, **_kwargs):
            events.append('reset')
            return {}, {}

        def get_record_metadata(self):
            raise AssertionError('mixed-control metadata called on a Position route')

        def start_recording(self, _path):
            events.append('record')

        def finish_recording(self, _reason):
            return {'transition_count': 1}

        def close(self):
            events.append('close')

    compiled = SimpleNamespace(env_class=lambda: Env, backend='cuda', device='cuda:0')
    with patch('examples._common.run_expert', return_value={'status': 'FAIL', 'transitions': 1}), \
         patch('examples._common.identity_summary', return_value={}):
        facts = oracle.record_episode(compiled, SimpleNamespace(horizon=5), provider='isaacsim',
                                      seed=31, h5=tmp_path / 'episode.h5', deadline=time.perf_counter() + 10)
    assert facts['close_succeeded'] is True
    if actual_seed == 31:
        assert facts['errors'] == []
        assert events == ['reset', 'record', 'close']
        assert facts['recording_identity']['seed'] == 31
        assert facts['recording_identity']['profile'] == {
            'execution_identity_sha256': 'execution', 'reset_plan_identity_hash': 'reset',
            'reset_sample_id': 'sample', 'source_id': 'source', 'source_closure_digest': 'closure',
            'delivery_manifest_sha256': 'manifest', 'provider': 'isaacsim', 'backend': 'cuda', 'device': 'cuda:0',
        }
    else:
        assert facts['recording_started'] is False
        assert events == ['reset', 'close']
        assert 'seed' in facts['errors'][0]['message'].lower()


@pytest.mark.parametrize('outcome_reason', ['horizon_reached', 'task_terminal', 'external_stop'])
def test_oracle_finalizes_position_with_the_public_lifecycle_reason(tmp_path, outcome_reason):
    import oracle_candidate as oracle

    requested = []
    summary = {'status': 'FAIL', 'failure_reason': 'episode_truncated', 'transitions': 1}

    class Env:
        position_profile = True
        controller = SimpleNamespace(identity='controller')
        solution = SimpleNamespace(identity='solution')
        execution_fault = None

        def __init__(self, **_kwargs):
            pass

        def reset(self, **_kwargs):
            return {}, {}

        def start_recording(self, _path):
            pass

        def stop(self, reason):
            requested.append(reason)
            return SimpleNamespace(outcome=SimpleNamespace(end_reason=outcome_reason))

        def finish_recording(self, reason):
            if reason != outcome_reason:
                raise ValueError('recording finalization reason disagrees with EpisodeOutcome')
            return {'outcome': {'end_reason': outcome_reason}, 'transition_count': 1}

        def close(self):
            pass

    compiled = SimpleNamespace(env_class=lambda: Env, backend='cpu', device='cpu')
    with patch('examples._common.run_expert', return_value=summary), \
         patch('examples._common.identity_summary', return_value={}):
        facts = oracle.record_episode(compiled, SimpleNamespace(horizon=1), provider='mujoco',
                                      seed=0, h5=tmp_path / 'episode.h5', deadline=time.perf_counter() + 10)
    assert facts['errors'] == []
    assert requested == ['episode_truncated']
    assert facts['episode'] == summary
    assert facts['verification']['outcome']['end_reason'] == outcome_reason
    assert facts['close_succeeded'] is True
