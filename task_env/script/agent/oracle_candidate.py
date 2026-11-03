"""Record a compiled candidate using Core's selected recorder; no new recorder."""
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time

if __package__:
    from .harness_spec_schema import CandidateSpec, CheckFinding, CheckReport, save_json
    from .catalog_query import core_context, validate_catalog
    from .harness_compiler import compile_candidate, CompilationRejected
    from .provider_routes import backend_for, device_for, requires_native_worker
else:
    from harness_spec_schema import CandidateSpec, CheckFinding, CheckReport, save_json
    from catalog_query import core_context, validate_catalog
    from harness_compiler import compile_candidate, CompilationRejected
    from provider_routes import backend_for, device_for, requires_native_worker

CANONICAL_SCHEMA_PREFIX = 'canonical'
GENERIC_V3_SCHEMA = 'task-env-h5/v3'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@contextmanager
def alarm(seconds):
    """Raise TimeoutError in this process when the wall-clock budget is exhausted."""
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    def timeout(*_):
        raise TimeoutError('Oracle wall-clock budget exhausted')
    signal.signal(signal.SIGALRM, timeout)
    signal.setitimer(signal.ITIMER_REAL, float(seconds))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)


def record_episode(compiled, spec, *, provider, seed, h5, deadline):
    """Construct, reset, record and drive the expert once; storage inspection stays with the caller."""
    facts = {'episode': None, 'identity': None, 'controller_identity': None, 'expert_identity': None,
             'verification': None, 'execution_fault': None, 'errors': [], 'recording_started': False,
             'close_attempted': False, 'close_succeeded': False, 'backend': compiled.backend,
             'device': compiled.device}
    env = None
    try:
        env = compiled.env_class()(provider=provider, backend=compiled.backend)
        _, reset_info = env.reset(seed=seed)
        if requires_native_worker(provider):
            # Bind expected H5 identities to the reset Core value; the public
            # get_record_metadata hook only serves mixed-control environments.
            runtime_input = env.value['f06_pickcube_isaac_input']
            reset_plan = env.value['reset_plan']
            source = env.value['source']
            execution = runtime_input.execution
            if reset_plan.reset_sample.task_seed != seed:
                raise ValueError('native Oracle reset seed differs from the requested seed')
            facts['recording_identity'] = {
                'seed': reset_plan.reset_sample.task_seed,
                'profile': {
                    'execution_identity_sha256': execution.identity_hash,
                    'reset_plan_identity_hash': reset_plan.identity_hash,
                    'reset_sample_id': reset_plan.reset_sample.sample_id,
                    'source_id': source.source_id,
                    'source_closure_digest': source.source_closure_digest,
                    'delivery_manifest_sha256': runtime_input.delivery_manifest_sha256,
                    'provider': execution.physics_provider,
                    'backend': execution.physics_backend,
                    'device': execution.physics_device,
                },
            }
        env.start_recording(h5)
        facts['recording_started'] = True
        from examples._common import run_expert, identity_summary
        facts['episode'] = run_expert(env, seed=seed, horizon=spec.horizon,
                                      already_reset=True, initial_info=reset_info)
        facts['identity'] = identity_summary(env, provider=provider, backend=compiled.backend)
        facts['controller_identity'] = env.controller.identity
        facts['expert_identity'] = env.solution.identity
        fault = getattr(env, 'execution_fault', None)
        facts['execution_fault'] = fault.to_mapping() if hasattr(fault, 'to_mapping') else (str(fault) if fault else None)
        if fault:
            raise RuntimeError('execution fault remains latched')
    except Exception as error:
        fault = getattr(error, 'execution_fault', None) or (getattr(env, 'execution_fault', None) if env is not None else None)
        if fault is not None:
            facts['execution_fault'] = fault.to_mapping() if hasattr(fault, 'to_mapping') else str(fault)
        facts['errors'].append({'phase': 'execute', 'type': type(error).__name__, 'message': str(error)})
    finally:
        if env is not None:
            if facts['recording_started']:
                try:
                    if deadline - time.perf_counter() <= 0:
                        raise TimeoutError('no budget remains for recording finalization')
                    reason = (facts['episode'] or {}).get('failure_reason') or ('pass' if not facts['errors'] else 'execution_error')
                    if getattr(env, 'position_profile', False):
                        reason = env.stop(reason).outcome.end_reason
                    facts['verification'] = env.finish_recording(reason)
                except Exception as error:
                    facts['errors'].append({'phase': 'finalize', 'type': type(error).__name__, 'message': str(error)})
            facts['close_attempted'] = True
            try:
                env.close()
                facts['close_succeeded'] = True
            except Exception as error:
                facts['errors'].append({'phase': 'close', 'type': type(error).__name__, 'message': str(error)})
    return facts


def _inspect(h5, directory, ctx, deadline):
    remaining = deadline - time.perf_counter()
    if remaining <= 0:
        raise TimeoutError('no budget remains for inspection')
    environment = os.environ.copy()
    core = Path(ctx['core_repo'])
    environment['PYTHONPATH'] = f"{core / 'GeoPhys/src'}:{core}"
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    process = subprocess.run([sys.executable, str(core / 'examples/recording/inspect_h5.py'), '--input', str(h5)],
                             capture_output=True, text=True, timeout=min(30, remaining), env=environment, cwd=core)
    (directory / 'inspect.stdout.txt').write_text(process.stdout)
    (directory / 'inspect.stderr.txt').write_text(process.stderr)
    summary = json.loads(process.stdout.strip().splitlines()[-1])
    save_json(summary, directory / 'inspect.json')
    return process, summary


def _snapshot_sources(ctx, directory, expected):
    """Pin every hashed source file that is a checkout path; identity-only digests are reported, not copied."""
    identity_only = {}
    for name, digest in expected.items():
        if name.startswith('task_env/') or name.startswith('examples/'):
            source = Path(ctx['core_repo']) / name
        elif (Path(__file__).parent / name).is_file() and '/' not in name:
            source = Path(__file__).parent / name
        else:
            identity_only[name] = digest
            continue
        if sha256(source) != digest:
            raise ValueError(f'source changed during run: {name}')
        target = directory / 'source_snapshot' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    return identity_only


def _storage_checks(h5, directory, *, ctx, spec, artifact_hash, details, deadline, worker=None):
    process, summary = _inspect(h5, directory, ctx, deadline)
    details['recording'] = summary
    details['h5'] = {'path': 'oracle.h5', 'sha256': sha256(h5), 'bytes': h5.stat().st_size}
    episode = details['episode'] or {}
    schema = str(summary.get('schema', ''))
    common = {
        'inspector_pass': process.returncode == 0 and summary.get('status') == 'PASS',
        't_plus_one': summary.get('t_plus_one_valid') is True,
        'artifact_identity': summary.get('task_artifact_sha256') == artifact_hash,
        'controller_identity': summary.get('controller_identity') == details.get('controller_identity'),
        'expert_identity': summary.get('expert_identity') == details.get('expert_identity'),
        'episode_transition_count': summary.get('transitions') == episode.get('transitions'),
    }
    if schema == GENERIC_V3_SCHEMA:
        # The versioned Position recorder stores a source profile, not the
        # canonical-v0 resolved-configuration JSON; Core/spec identity therefore
        # binds to the worker receipt and the parent compilation, not to H5 bytes.
        worker = worker or {}
        compiled = worker.get('compiled') or {}
        from task_env.recorders import load_structured_control_records_h5
        actual_profile = load_structured_control_records_h5(h5)['env_meta']['reference_profile']
        identity = (worker.get('facts') or {}).get('recording_identity') or {}
        expected_profile = identity.get('profile') or {}
        checks = {**common,
                  'requested_seed': worker.get('seed') == details['seed'] == identity.get('seed'),
                  **{'recorded_' + key: bool(expected_profile.get(key))
                     and actual_profile.get(key) == expected_profile[key]
                     for key in ('execution_identity_sha256', 'reset_plan_identity_hash',
                                 'reset_sample_id', 'source_id', 'source_closure_digest',
                                 'delivery_manifest_sha256', 'provider', 'backend', 'device')},
                  'provider_provenance': summary.get('provider_provenance_present') is True,
                  'source_provenance': summary.get('source_provenance_present') is True,
                  'core_identity': worker.get('core_commit') == ctx['core_commit'] and worker.get('core_dirty') is False,
                  'spec_identity': compiled.get('spec_sha256') == spec.spec_sha256(),
                  'worker_artifact_identity': compiled.get('artifact_hash') == artifact_hash,
                  'roundtrip_readback': summary.get('storage_roundtrip') == 'PASS'}
        details['storage_contract'] = ('task-env-h5/v3 structured-control readback; not the canonical-v0 '
                                       'exact logical save/load comparison')
        details['storage_not_checked'] = ['task_success_at_last_boundary', 'logical_mapping_exact']
        details['source_identity_only'] = _snapshot_sources(ctx, directory, {**compiled.get('source_sha256', {}),
                                                                             **details['tool_sha256']})
    else:
        from task_env.trajectory.canonical.h5 import load
        trajectory = load(h5)
        metadata = trajectory.metadata.to_mapping()
        config = json.loads(metadata['source_provenance']['resolved_configuration_json'])
        details['source_identity_only'] = _snapshot_sources(ctx, directory, {**config['source_sha256'], **details['tool_sha256']})
        checks = {**common,
                  'roundtrip_exact': bool((details['verification'] or {}).get('logical_mapping_exact')),
                  'core_identity': summary.get('source_revision') == ctx['core_commit'],
                  'spec_identity': config['spec_sha256'] == spec.spec_sha256(),
                  'task_success_at_last_boundary': trajectory.boundaries[-1].is_success == bool(episode.get('task_success'))}
        details['storage_contract'] = 'canonical-v0 exact logical save/load comparison plus independent inspector'
    details['storage_identity_checks'] = checks
    if not all(checks.values()):
        raise ValueError(f'Oracle storage/identity checks failed: {checks}')


def record_candidate(spec, catalog, *, provider, seed, directory, time_limit_s=120):
    """Return the independent completion, storage and provenance checks for one run."""
    if type(seed) is not int or seed < 0:
        raise ValueError('nonnegative seed required')
    if not 1 <= time_limit_s <= 420:
        raise ValueError('time_limit_s must be 1..420')
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    ctx = validate_catalog(catalog)
    spec.save(directory / 'candidate.spec.json')
    save_json(catalog, directory / 'catalog.json')
    started = time.perf_counter()
    deadline = started + time_limit_s
    native = requires_native_worker(provider)
    details = {'created_at': datetime.now(timezone.utc).isoformat(), 'provider': provider,
        'backend': backend_for(provider), 'device': device_for(provider), 'seed': seed, 'horizon': spec.horizon,
        'execution_mode': 'native_worker' if native else 'in_process',
        'synthetic_upstream': spec.object_config['object_uid'] in catalog.get('external_assets', {}),
        'physics_execution': 'real', 'time_limit_s': time_limit_s,
        'qualification': 'NOT_ASSESSED', 'D0': 'NOT_ASSESSED', 'D1': 'NOT_ASSESSED', 'D2': 'NOT_ASSESSED',
        'video': {'status': 'NOT_RECORDED', 'reason': 'selected reference route has no supported render configuration'},
        'episode': None, 'recording': None, 'verification': None, 'errors': [],
        'tool_sha256': {n: sha256(Path(__file__).parent / n) for n in
            ('oracle_candidate.py', 'harness_compiler.py', 'harness_spec_schema.py')}}
    artifact_hash = None
    findings = []
    worker = None
    h5 = directory / 'oracle.h5'
    try:
        with alarm(time_limit_s):
            compiled = compile_candidate(spec, catalog, provider=provider)
            artifact_hash = compiled.artifact_hash
            save_json(compiled.artifact.to_mapping(), directory / 'candidate.artifact.json')
            if native:
                if __package__:
                    from .native_candidate_runner import run_oracle_native
                else:
                    from native_candidate_runner import run_oracle_native
                worker, receipt = run_oracle_native(spec=spec, catalog=catalog, provider=provider, seed=seed,
                                                    directory=directory, time_limit_s=time_limit_s)
                details['native_run'] = receipt
                if worker is None:
                    raise RuntimeError(f"native worker produced no receipt: {receipt.get('status')}: {receipt.get('reason')}")
                details['worker'] = {key: worker.get(key) for key in ('core_commit', 'core_dirty', 'compiled', 'app', 'errors')}
                facts = worker.get('facts') or {}
                for error in worker.get('errors', []):
                    details['errors'].append({'phase': f"worker_{error.get('phase')}", 'type': error.get('type'),
                                              'message': error.get('message')})
            else:
                facts = record_episode(compiled, spec, provider=provider, seed=seed, h5=h5, deadline=deadline)
        for key in ('episode', 'identity', 'controller_identity', 'expert_identity', 'verification', 'execution_fault'):
            details[key] = facts.get(key)
        details['errors'].extend(facts.get('errors', []))
        if details['episode'] is not None and details['episode'].get('status') != 'PASS':
            findings.append(CheckFinding('oracle_completion', 'expert_failed', 'unknown', '',
                details['episode'], 'task success AND complete expert without truncation', {'seed': seed}))
    except CompilationRejected as error:
        findings.extend(error.report.findings)
    except Exception as error:
        details['errors'].append({'phase': 'execute', 'type': type(error).__name__, 'message': str(error)})
    if h5.is_file():
        try:
            _storage_checks(h5, directory, ctx=ctx, spec=spec, artifact_hash=artifact_hash, details=details,
                            deadline=deadline, worker=worker)
        except Exception as error:
            details['errors'].append({'phase': 'inspect', 'type': type(error).__name__, 'message': str(error)})
    elif not findings:
        details['errors'].append({'phase': 'inspect', 'type': 'MissingRecording', 'message': 'no H5 was finalized'})
    for error in details['errors']:
        findings.append(CheckFinding('oracle_' + str(error['phase']), 'execution_fault', 'unknown', '', error,
            'successful recorded execution and storage checks', {'seed': seed}))
    passed = not findings and (details['episode'] or {}).get('status') == 'PASS'
    status = 'pass' if passed else ('error' if details['errors'] else 'fail')
    details['wall_time_s'] = time.perf_counter() - started
    report = CheckReport(spec.spec_sha256(), artifact_hash, ctx['core_commit'], ctx['core_dirty'],
        'oracle_candidate', status, findings, details)
    report.save(directory / 'oracle.check.json')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('core-repo', 'spec', 'catalog', 'output-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--provider', default='mujoco')
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--time-limit-s', type=int, default=120)
    args = parser.parse_args()
    core_context(args.core_repo)
    report = record_candidate(CandidateSpec.load(args.spec), json.loads(args.catalog.read_text()),
        provider=args.provider, seed=args.seed, directory=args.output_dir, time_limit_s=args.time_limit_s)
    print(json.dumps({'status': report.status, 'output': str(args.output_dir), 'episode': report.details['episode'],
        'recording': report.details['recording'], 'errors': report.details['errors']}, default=str))
    return {'pass': 0, 'fail': 1, 'error': 2}[report.status]


if __name__ == '__main__':
    raise SystemExit(main())
