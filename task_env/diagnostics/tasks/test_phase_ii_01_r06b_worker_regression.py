"""Real R06b worker/supervisor control flow with explicitly synthetic model IO."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest

from task_env.tasks.position_candidate.attached_leaf_candidate import build_attached_leaf_candidate
from task_env.tasks.reference_env import SelectedReferenceEnv


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_synthetic_case(episode_id: str, order_variant: bool):
    from test_phase_ii_01_r03c_attached_leaf import _session_with_synthetic_native_io
    from task_env.diagnostics.tasks.r06b_order_worker import _candidate_identity

    candidate = build_attached_leaf_candidate(
        environment_type=SelectedReferenceEnv, arm_gain=2.5,
        hand_stiffness_N_per_m=50.0, provider='mujoco', horizon=64,
        episode_id=episode_id, arm_active=True, hand_active=True,
        order_variant=order_variant,
    )
    session = _session_with_synthetic_native_io(candidate)
    receipt = session.fixed_attachment_receipt
    return candidate, session, {
        'episode_id': episode_id,
        'candidate': _candidate_identity(candidate),
        'native_expected': {
            'native_body_order': receipt['native_body_order'],
            'native_joint_order': receipt['native_joint_order'],
            'native_actuator_order': receipt['native_actuator_order'],
            'dimensions': receipt['dimensions'],
            'actuator_slots': {
                key: row['ctrl_slot']
                for key, row in receipt['native_actuator_mappings'].items()
            },
        },
    }


def _engine_module(current_io: dict):
    """Fake only the MuJoCo module boundary; every Core owner remains real."""
    module = ModuleType('mujoco')
    module.__version__ = '3.8.1'
    module.mj_versionString = lambda: '3.8.1'
    module.mj_version = lambda: 3008001
    module.mjtJoint = SimpleNamespace(mjJNT_FREE=0, mjJNT_HINGE=3, mjJNT_SLIDE=2)
    module.mjtObj = SimpleNamespace(
        mjOBJ_JOINT='joint', mjOBJ_ACTUATOR='actuator', mjOBJ_BODY='body', mjOBJ_TENDON='tendon',
    )
    module.mjtTrn = SimpleNamespace(mjTRN_JOINT=0, mjTRN_TENDON=3)
    module.mjtEq = SimpleNamespace(mjEQ_JOINT=2)

    def io(name):
        target = current_io.get('value')
        if target is None:
            raise RuntimeError('synthetic MuJoCo IO was not selected by materialization')
        return getattr(target, name)

    module.mj_resetData = lambda *args, **kwargs: io('mj_resetData')(*args, **kwargs)
    module.mj_name2id = lambda *args, **kwargs: io('mj_name2id')(*args, **kwargs)
    module.mj_id2name = lambda *args, **kwargs: io('mj_id2name')(*args, **kwargs)
    module.mj_step = lambda *args, **kwargs: io('mj_step')(*args, **kwargs)
    module.mj_forward = lambda *args, **kwargs: io('mj_forward')(*args, **kwargs)
    module.mju_mat2Quat = lambda *args, **kwargs: io('mju_mat2Quat')(*args, **kwargs)
    return module


def _prepare_worker(monkeypatch, tmp_path: Path, *, failure: str | None = None):
    from task_env.diagnostics.tasks import r03c_attached_leaf_probe, r06b_order_worker as worker
    from task_env.runtime.sessions import api, control

    root = worker.ROOT
    cases = [
        _build_synthetic_case('E1', False),
        _build_synthetic_case('E2', True),
    ]
    contract_cases = [item[2] for item in cases]
    output = tmp_path / f'worker-{failure or "success"}'
    output.mkdir()
    (output / 'native_start_ledger.json').write_text(json.dumps({
        'schema': 'r06b-native-start-ledger-v1', 'native_start_count': 1,
        'native_worker': 'r06b_order_worker.py',
    }) + '\n')
    freeze = Path('/home/lly/Program_Files/Geochora/workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r06b_003/package_input/input_snapshot.json')
    snapshot = json.loads(freeze.read_text())
    relevant_code = [
        'task_env/artifacts/contracts.py', 'task_env/assembly/fixed_attachment.py',
        'task_env/runtime/sessions/api.py', 'task_env/runtime/sessions/mujoco.py',
        'task_env/tasks/position_candidate/fixed_attachment_candidate.py',
        'task_env/tasks/position_candidate/attached_leaf_candidate.py',
        'task_env/diagnostics/tasks/r06b_order_worker.py',
        'task_env/diagnostics/tasks/r06b_order_supervisor.py',
        'task_env/diagnostics/tasks/r06b_order_readback.py',
    ]
    contract = {
        'schema': 'r06b-order-native-contract-synthetic-test-v1',
        'input_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        'branch': subprocess.check_output(['git', 'branch', '--show-current'], cwd=root, text=True).strip(),
        'output_dir': str(output), 'cases': contract_cases,
        'limits': worker.FROZEN_LIMITS, 'oracles': worker.FROZEN_ORACLES,
        'reader_tamper_matrix': worker.FROZEN_TAMPER_MATRIX,
        'submodule_pins': snapshot['pins'],
        'code_sha256': {name: worker._sha(root / name) for name in relevant_code},
        'protected_sha256': snapshot['protected_evidence'],
        'mujoco_static': {'files_sha256': {}},
    }
    contract['contract_sha256'] = worker._contract_digest(contract)
    contract_path = output / 'native_contract.json'
    contract_path.write_text(json.dumps(contract, sort_keys=True, indent=2) + '\n')

    current_io = {'value': None, 'materializations': 0, 'steps_in_case': 0}
    engine = _engine_module(current_io)
    monkeypatch.setitem(sys.modules, 'mujoco', engine)
    runtime_identity = {'package_version': '3.8.1', 'runtime_version': '3.8.1', 'api_version': 3008001}
    monkeypatch.setattr(r03c_attached_leaf_probe, '_native_identity', lambda _mj, _static: runtime_identity)
    originals = {
        'control_materialize': control.materialize_control,
        'reference_materialize': sys.modules['task_env.tasks.reference_env'].materialize_control,
        'step': engine.mj_step, 'forward': engine.mj_forward,
    }
    materialization_count = {'value': 0}

    def materialize(artifact, execution, source):
        materialization_count['value'] += 1
        current_io['materializations'] += 1
        order_variant = source.fixed_attachment_plan.parent_asset_version.endswith('r06b-order-v1')
        episode_id = 'E1' if materialization_count['value'] == 1 else 'E2'
        if failure in {'e2_materialize_before', 'e2_materialize_during', 'primary_and_cleanup'} and episode_id == 'E2':
            if failure == 'e2_materialize_during':
                _candidate, partial, _case = _build_synthetic_case(episode_id, order_variant)
                partial.close()
            raise RuntimeError('synthetic E2 materialize failure')
        candidate, session, _case = _build_synthetic_case(episode_id, order_variant)
        if candidate.artifact.identity_hash != artifact.identity_hash or candidate.source != source:
            raise AssertionError('synthetic session owner received a mismatched production candidate')
        session._fixed_attachment_receipt['runtime_identity'] = runtime_identity
        payload = dict(session._fixed_attachment_receipt)
        payload.pop('receipt_identity_sha256', None)
        session._fixed_attachment_receipt['receipt_identity_sha256'] = hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False,
        ).encode()).hexdigest()
        current_io['value'] = session._mj
        session._mj = engine
        current_io['steps_in_case'] = 0
        return session

    monkeypatch.setattr(api, '_materialize_admitted', materialize)
    original_step = engine.mj_step

    def partial_step(*args, **kwargs):
        if failure == 'partial_physics' and materialization_count['value'] == 2:
            if current_io['steps_in_case'] >= 2:
                raise RuntimeError('synthetic partial physics failure')
            current_io['steps_in_case'] += 1
        return original_step(*args, **kwargs)

    engine.mj_step = partial_step
    if failure == 'primary_and_cleanup':
        original_close = SelectedReferenceEnv.close
        close_count = {'value': 0}

        def close_with_failure(env):
            close_count['value'] += 1
            original_close(env)
            if close_count['value'] == 2:
                raise RuntimeError('synthetic cleanup failure')

        monkeypatch.setattr(SelectedReferenceEnv, 'close', close_with_failure)
    if failure == 'third_materialization':
        original_reset = SelectedReferenceEnv.reset
        reset_count = {'value': 0}

        def reset_then_third_call(env, *args, **kwargs):
            value = original_reset(env, *args, **kwargs)
            reset_count['value'] += 1
            if reset_count['value'] == 2:
                control.materialize_control(None, None)
            return value

        monkeypatch.setattr(SelectedReferenceEnv, 'reset', reset_then_third_call)
    if failure == 'final_json_error':
        original_write = worker._write_json

        def fail_pending(path, value):
            if Path(path).name == 'native_result.pending.json':
                raise OSError('synthetic final JSON write failure')
            return original_write(path, value)

        monkeypatch.setattr(worker, '_write_json', fail_pending)
    return worker, contract_path, output, engine, originals, materialization_count


def test_real_run_worker_two_cases_with_synthetic_model_io_and_restored_hooks(monkeypatch, tmp_path):
    worker, contract_path, output, engine, originals, materializations = _prepare_worker(monkeypatch, tmp_path)
    result = worker.run_worker(contract_path)
    assert result['status'] == 'R06B_NATIVE_WORKER_PASS_PENDING_READBACK'
    assert [case['episode_id'] for case in result['cases']] == ['E1', 'E2']
    assert [case['h5']['transition_count'] for case in result['cases']] == [64, 64]
    assert [case['h5']['observation_count'] for case in result['cases']] == [65, 65]
    assert [case['episode_outcome']['end_reason'] for case in result['cases']] == [
        'horizon_reached', 'horizon_reached',
    ]
    assert [case['episode_outcome']['task_success'] for case in result['cases']] == [False, False]
    assert result['counters']['materialization_attempts'] == 2
    assert result['counters']['materializations_completed'] == 2
    assert result['counters']['resets'] == result['counters']['resets_completed'] == 2
    assert result['counters']['outer_intervals'] == 128
    assert result['counters']['attempted_mj_step_calls'] == result['counters']['mj_step_calls'] == 640
    assert result['counters']['mj_forward_calls'] == 130
    assert materializations['value'] == 2
    assert engine.mj_step is originals['step']
    assert engine.mj_forward is originals['forward']
    assert sys.modules['task_env.runtime.sessions.control'].materialize_control is originals['control_materialize']
    assert sys.modules['task_env.tasks.reference_env'].materialize_control is originals['reference_materialize']
    trace = [json.loads(line) for line in (output / 'native/native_step_trace.jsonl').read_text().splitlines()]
    assert len(trace) == 640
    assert {row['episode_id'] for row in trace} == {'E1', 'E2'}
    assert all(row['phase'] == 'public_typed_dispatch' for row in trace)
    assert {row['episode_id']: len([item for item in trace if item['episode_id'] == row['episode_id']])
            for row in trace} == {'E1': 320, 'E2': 320}


@pytest.mark.parametrize('failure', [
    'e2_materialize_before', 'e2_materialize_during', 'partial_physics',
    'primary_and_cleanup', 'third_materialization', 'final_json_error',
])
def test_real_run_worker_failure_finalizes_and_restores_hooks(monkeypatch, tmp_path, failure):
    worker, contract_path, output, engine, originals, materializations = _prepare_worker(
        monkeypatch, tmp_path, failure=failure,
    )
    with pytest.raises((RuntimeError, OSError)):
        worker.run_worker(contract_path)
    failure_receipt = json.loads((output / 'native/native_failure.json').read_text())
    assert failure_receipt['status'] == 'NATIVE_WORKER_FAILED'
    assert engine.mj_step is originals['step']
    assert engine.mj_forward is originals['forward']
    assert sys.modules['task_env.runtime.sessions.control'].materialize_control is originals['control_materialize']
    assert sys.modules['task_env.tasks.reference_env'].materialize_control is originals['reference_materialize']
    assert not (output / 'native/native_result.json').exists()
    if failure == 'e2_materialize_before':
        assert failure_receipt['counters']['materialization_attempts'] == 2
        assert failure_receipt['counters']['materializations_completed'] == 1
    if failure == 'third_materialization':
        assert failure_receipt['counters']['materialization_attempts'] == 3
        assert failure_receipt['counters']['materializations_completed'] == 2
        assert materializations['value'] == 2
    if failure == 'partial_physics':
        assert failure_receipt['counters']['cases']['E2']['attempted_mj_step_calls'] > failure_receipt['counters']['cases']['E2']['mj_step_calls']
    if failure == 'primary_and_cleanup':
        e2 = json.loads((output / 'native/E2_failure.json').read_text())
        assert e2['primary_error']['message'] == 'synthetic E2 materialize failure'
        assert e2['cleanup_error']['message'] == 'synthetic cleanup failure'
    if failure == 'final_json_error':
        assert failure_receipt['error'] == 'synthetic final JSON write failure'


def test_real_worker_rejects_existing_native_output_before_import(monkeypatch, tmp_path):
    from task_env.diagnostics.tasks.r06b_order_worker import run_worker

    output = tmp_path / 'existing-output'
    (output / 'native').mkdir(parents=True)
    contract_path = output / 'contract.json'
    contract_path.write_text(json.dumps({'output_dir': str(output)}) + '\n')
    with pytest.raises(FileExistsError):
        run_worker(contract_path)


def test_supervisor_persists_failure_resources_and_releases_fake_lock(monkeypatch, tmp_path):
    """Exercise supervisor's actual lock, orchestration and finally path with fake child IO."""
    from task_env.diagnostics.tasks import r06b_order_supervisor as supervisor
    from task_env.diagnostics.tasks import r06b_order_worker as worker

    outcomes = ('success', 'worker_failure', 'reader_failure', 'resource', 'popen_failure', 'cleanup_exception')
    for mode in outcomes:
        output = tmp_path / f'supervisor-{mode}'
        output.mkdir()
        lock = tmp_path / f'{mode}.lock'
        lock.touch()
        monkeypatch.setattr(supervisor, 'LOCK_PATH', lock)
        monkeypatch.setattr(supervisor, '_available_bytes', lambda: 4 * 1024**3)
        group_pid_calls = {'value': 0}

        def group_pids(_pgid):
            if mode == 'cleanup_exception' and group_pid_calls['value'] == 0:
                group_pid_calls['value'] += 1
                return [999999]
            return []

        monkeypatch.setattr(supervisor, '_process_group_pids', group_pids)
        if mode == 'cleanup_exception':
            monkeypatch.setattr(supervisor, '_process_group_rss', lambda _pgid: (_ for _ in ()).throw(
                RuntimeError('synthetic RSS sampling failure'),
            ))
        else:
            monkeypatch.setattr(supervisor, '_process_group_rss', lambda _pgid: [
                {'pid': 999999, 'rss_bytes': 5 * 1024**3 if mode == 'resource' else 1024},
            ])
        real_time = supervisor.time
        monkeypatch.setattr(supervisor, 'time', SimpleNamespace(
            monotonic=real_time.monotonic, time=real_time.time, sleep=lambda _seconds: None,
        ))
        contract = {
            'output_dir': str(output), 'contract_sha256': 'a' * 64,
            'input_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=worker.ROOT, text=True).strip(),
            'branch': subprocess.check_output(['git', 'branch', '--show-current'], cwd=worker.ROOT, text=True).strip(),
            'limits': worker.FROZEN_LIMITS, 'oracles': worker.FROZEN_ORACLES,
            'reader_tamper_matrix': worker.FROZEN_TAMPER_MATRIX,
            'submodule_pins': {
                'GeoPhys': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=worker.ROOT / 'GeoPhys', text=True).strip(),
                'asset/external/mujoco_menagerie': subprocess.check_output(
                    ['git', 'rev-parse', 'HEAD'], cwd=worker.ROOT / 'asset/external/mujoco_menagerie', text=True,
                ).strip(),
            },
            'code_sha256': {
                name: worker._sha(worker.ROOT / name) for name in (
                    'task_env/diagnostics/tasks/r06b_order_worker.py',
                    'task_env/diagnostics/tasks/r06b_order_supervisor.py',
                )
            },
            'protected_sha256': {},
        }
        contract['contract_sha256'] = worker._contract_digest(contract)
        contract_path = output / 'contract.json'
        contract_path.write_text(json.dumps(contract) + '\n')

        class FakeProcess:
            pid = 999999

            def __init__(self, *_args, **_kwargs):
                self.returncode = None
                self.polls = 0
                (output / 'native').mkdir(exist_ok=True)
                if mode in {'success', 'reader_failure'}:
                    (output / 'native/native_result.json').write_text(json.dumps({
                        'status': 'R06B_NATIVE_WORKER_PASS_PENDING_READBACK',
                    }))

            def poll(self):
                self.polls += 1
                if mode == 'cleanup_exception':
                    return None
                if self.polls > 1:
                    self.returncode = 1 if mode == 'worker_failure' else 0
                return self.returncode

            def wait(self, timeout=None):
                self.returncode = 0 if self.returncode is None else self.returncode
                return self.returncode

        class FakeRunResult:
            returncode = 1 if mode == 'reader_failure' else 0

        class FakeRun:
            def __call__(self, *_args, **_kwargs):
                import fcntl
                probe_fd = os.open(lock, os.O_RDWR)
                try:
                    with pytest.raises(BlockingIOError):
                        fcntl.flock(probe_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    os.close(probe_fd)
                if mode == 'success':
                    (output / 'raw_readback.json').write_text(json.dumps({'status': 'synthetic-pass'}))
                return FakeRunResult()

        def popen(*args, **kwargs):
            if mode == 'popen_failure':
                raise OSError('synthetic Popen failure')
            return FakeProcess(*args, **kwargs)

        fake_subprocess = SimpleNamespace(Popen=popen, run=FakeRun(), STDOUT=subprocess.STDOUT)
        monkeypatch.setattr(supervisor, 'subprocess', fake_subprocess)
        if mode == 'cleanup_exception':
            def cleanup_failure(_pgid, _proc):
                raise RuntimeError('synthetic cleanup failure')
            monkeypatch.setattr(supervisor, '_terminate_group', cleanup_failure)
        else:
            monkeypatch.setattr(supervisor, '_terminate_group', lambda _pgid, proc: {
                'term_sent': True, 'kill_sent': False, 'term_wait_seconds': 0.0,
            })
        receipt = supervisor.run_supervisor(contract_path)
        assert receipt['rss_sample_count'] in (0, 1)
        if mode == 'success':
            assert receipt['status'] == 'R06B_BOUNDED_ORDER_REGRESSION_PASS_PENDING_SOL_REVIEW'
            assert receipt['lock_held_until_raw_reader_exit'] is True
        elif mode == 'worker_failure':
            assert receipt['status'] == 'NATIVE_WORKER_FAILED'
        elif mode == 'reader_failure':
            assert receipt['status'] == 'NATIVE_SUPERVISOR_FAILED'
            assert receipt['primary_error']['message'].startswith('independent raw H5 witness exited')
            assert receipt['rss_sample_count'] == 1
            assert receipt['rss_peak_sampled_group_bytes'] == 1024
        elif mode == 'resource':
            assert receipt['status'] == 'NATIVE_TERMINATED_RESOURCE_LIMIT'
            assert receipt['rss_peak_sampled_group_bytes'] == 5 * 1024**3
        else:
            assert receipt['status'] == 'NATIVE_SUPERVISOR_FAILED'
            if mode == 'popen_failure':
                assert receipt['primary_error']['message'] == 'synthetic Popen failure'
                assert receipt['rss_peak_sampled_group_bytes'] is None
            else:
                assert receipt['primary_error']['message'] == 'synthetic RSS sampling failure'
                assert receipt['cleanup_error']['message'] == 'synthetic cleanup failure'
        assert receipt['lock_released_after_group'] is True
        assert receipt['worker_start_ledger_sha256'] is not None
