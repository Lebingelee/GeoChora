"""External Stage-1 reset/expert probe. Expert failure is not infeasibility.

Candidate mode (--spec) returns 0 only when all requested seeds solve.
Legacy environment mode (--env) returns 0 for a complete report, not qualification.
Output files are exclusively created and never overwritten.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import subprocess
import time
import traceback

from completion_facts import COMPLETION_CONTRACT, capture_episode_facts

CLASSES = ('solved', 'invalid', 'expert_failed', 'unknown')


def run_seed(env_class, provider, seed, horizon):
    started = time.perf_counter()
    env = None
    info = {}
    phase = 'construction'
    row = dict(seed=seed, horizon=horizon, start_pose=None, sample_seed=None,
        artifact_hash=None, classification='unknown', steps=0, step_attempts=0,
        phase=phase, reason='probe did not reach an outcome', stage=None,
        construction_succeeded=False, reset_attempted=False, reset_succeeded=False,
        terminated=False, truncated=False, task_success=False, task_failure=False,
        solution_done=False, solution_failed=False, expert_complete=False,
        planned_trajectory_completed=None, outcome_complete=None,
        unapproved_override_used=None, original_expert_lifecycle_status=None,
        readiness_warnings=[], execution_lifecycle_status=None,
        completion_basis=None, completion_eligible=False, execution_fault=None,
        close_attempted=False, close_succeeded=False, cleanup_error=None,
        cleanup_traceback=None, error_phase=None, error_type=None,
        error_message=None, error_traceback=None, failure_reason=None,
        wall_time_s=0.0)

    def remember_error(error, error_phase):
        if row['error_type'] is not None:
            return
        row.update(phase=error_phase, error_phase=error_phase,
            error_type=type(error).__name__, error_message=str(error),
            error_traceback=''.join(traceback.format_exception(type(error), error, error.__traceback__)),
            reason=f'{type(error).__name__}: {error}')

    def record_fault(fault):
        if fault is None:
            return
        mapping = fault.to_mapping()
        row['execution_fault'] = mapping
        if row['error_type'] is None:
            row['reason'] = fault.message

    try:
        env = env_class(provider=provider, backend='cpu', horizon=horizon)
        row['construction_succeeded'] = True
        row['artifact_hash'] = env.artifact.identity_hash
        phase = 'reset'
        row['phase'] = phase
        row['reset_attempted'] = True
        _, info = env.reset(seed=seed)
        row['reset_succeeded'] = True
        phase = 'execution'
        row['phase'] = phase
        while True:
            fault = env.execution_fault
            solution = env.solution
            row.update(capture_episode_facts(env, info, terminated=row['terminated'],
                                             truncated=row['truncated'], transitions=row['steps']))
            row.update(stage=solution.stage, failure_reason=solution.failure_reason)
            if fault is not None:
                record_fault(fault)
                break
            if row['terminated'] and row['truncated']:
                row.update(reason='terminated_and_truncated', classification='invalid')
                break
            if row['completion_eligible']:
                row.update(reason='task_and_expert_completion_confirmed')
                break
            if row['solution_failed']:
                row.update(reason=solution.failure_reason or 'expert_failed')
                break
            if row['terminated'] or row['truncated'] or row['task_failure']:
                reason = ('terminated' if row['terminated'] else 'truncated' if row['truncated']
                          else 'task_failure')
                row.update(reason=reason)
                break
            if row['steps'] >= horizon or row['solution_done']:
                reason = 'expert_done_without_confirmed_completion' if row['solution_done'] else 'horizon_exhausted'
                row.update(reason=reason)
                break
            row['step_attempts'] += 1
            _, _, terminated, truncated, info = env.step_expert()
            row.update(terminated=terminated, truncated=truncated)
            row['steps'] += 1
    except Exception as error:
        remember_error(error, phase)
        fault = getattr(error, 'execution_fault', None)
        if fault is None and env is not None:
            try:
                fault = env.execution_fault
            except Exception:
                pass
        if fault is not None:
            try:
                record_fault(fault)
            except Exception as fault_error:
                row['fault_mapping_error'] = f'{type(fault_error).__name__}: {fault_error}'
    finally:
        if env is not None:
            try:
                sample = getattr(env, 'sample', None)
                if sample is not None:
                    row['start_pose'] = {key: {'position': list(pose.position),
                        'quaternion_wxyz': list(pose.quaternion_wxyz)} for key, pose in sample.poses_world.items()}
                    row['sample_seed'] = sample.task_seed
            except Exception as error:
                row['evidence_capture_error'] = f'{type(error).__name__}: {error}'
            row['close_attempted'] = True
            try:
                env.close()
                row['close_succeeded'] = True
            except Exception as error:
                row['cleanup_error'] = f'{type(error).__name__}: {error}'
                row['cleanup_traceback'] = ''.join(
                    traceback.format_exception(type(error), error, error.__traceback__)
                )
                if row['error_type'] is None:
                    remember_error(error, 'close')
        if row['execution_fault'] is not None or row['error_type'] is not None \
                or row['cleanup_error'] is not None or not row['construction_succeeded'] \
                or not row['reset_succeeded'] or (row['terminated'] and row['truncated']):
            row['classification'] = 'invalid'
        elif row['solution_failed'] \
                or (isinstance(row['original_expert_lifecycle_status'], dict)
                    and row['original_expert_lifecycle_status'].get('expert_failed') is True) \
                or row['execution_lifecycle_status'] == 'failed':
            row['classification'] = 'expert_failed'
        elif row['completion_eligible'] and not row['terminated'] and not row['truncated'] \
                and row['close_succeeded']:
            row['classification'] = 'solved'
        else:
            row['classification'] = 'unknown'
        if row['classification'] == 'invalid' and row['reason'] == 'probe did not reach an outcome':
            row['reason'] = 'execution or cleanup invalidated completion'
        elif row['classification'] == 'expert_failed' and row['reason'] == 'probe did not reach an outcome':
            row['reason'] = row['failure_reason'] or 'expert_failed'
        elif row['classification'] == 'unknown' and row['reason'] == 'probe did not reach an outcome':
            row['reason'] = 'completion was not confirmed'
        row['wall_time_s'] = time.perf_counter() - started
    return row


def run_candidate_probe(spec, catalog, provider, seeds, *, output=None):
    """Shared report mode for declarative candidates; retain all four raw classes."""
    if not seeds or any(type(seed) is not int or seed < 0 for seed in seeds) or len(set(seeds)) != len(seeds):
        raise ValueError('seeds must be nonempty, unique nonnegative integers')
    from dataclasses import asdict, replace
    from harness_spec_schema import CheckFinding, CheckReport
    from harness_compiler import compile_candidate, CompilationRejected
    try:
        compiled = compile_candidate(spec, catalog, provider=provider)
    except CompilationRejected as error:
        report = replace(error.report,tool='feasibility_probe',details={'origin_tool':'harness_compiler', 'complete':False})
        if output is not None:
            report.save(output)
        return report
    except Exception as error:
        from catalog_query import core_context
        ctx = core_context(catalog['core_repo'])
        report = CheckReport(spec.spec_sha256(), None, ctx['core_commit'], ctx['core_dirty'],
            'feasibility_probe', 'error', [CheckFinding('candidate_compile', 'execution_fault', 'harness', '',
            f'{type(error).__name__}: {error}', 'successful compilation', {'phase': 'compile'})],
            details={'complete': False})
        if output is not None:
            report.save(output)
        return report
    stream = None
    if output is not None:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        stream = output.open('x', encoding='utf-8')
    rows, findings = [], []
    def report_for(complete):
        totals = {key: sum(row['classification'] == key for row in rows) for key in CLASSES}
        # Unknown remains inconclusive, never relabelled as expert failure.
        status = 'pass' if complete and totals['solved'] == len(seeds) and not findings else 'fail' if complete else 'error'
        return CheckReport(compiled.spec_sha256, compiled.artifact_hash,
            catalog['core_commit'], catalog['core_dirty'], 'feasibility_probe', status, list(findings),
            details={'complete': complete, 'provider': provider, 'horizon': spec.horizon,
                'seeds': list(seeds), 'rows': list(rows), 'totals': totals,
                'completion_contract': COMPLETION_CONTRACT,
                'classification_policy': 'invalid first; solved requires task success, confirmed expert completion, no failure/flags, and successful close; then expert_failed; otherwise unknown',
                'scope': 'Candidate reset/expert evidence only; not task infeasibility, full validation, or qualification.'})
    def checkpoint(report):
        if stream is not None:
            stream.seek(0)
            json.dump(asdict(report), stream, indent=2, allow_nan=False)
            stream.write('\n')
            stream.truncate()
            stream.flush()
    try:
        checkpoint(report_for(False))
        for seed in seeds:
            row = run_seed(compiled.env_class(), provider, seed, spec.horizon)
            rows.append(row)
            evidence = {'seed': seed, 'row_index': len(rows)-1, 'phase': row['phase'],
                        'stage': row['stage'], 'start_pose': row['start_pose']}
            if row['classification'] == 'invalid':
                findings.append(CheckFinding('episode_execution', 'execution_fault', 'unknown', '',
                    row['reason'], 'valid reset and execution', evidence,
                    'Escalate for diagnosis; do not narrow reset merely to hide an execution fault.'))
            elif row['classification'] == 'expert_failed':
                findings.append(CheckFinding('expert_completion', 'expert_failed', 'unknown',
                    'object_config', row['reason'], 'expert done AND current task success', evidence,
                    'Establish task-local evidence before revising reset; expert failure alone is not infeasibility.'))
            if row.get('cleanup_error'):
                findings.append(CheckFinding('episode_cleanup', 'execution_fault', 'harness', '',
                    row['cleanup_error'], 'successful close', evidence))
            checkpoint(report_for(False))
            print(json.dumps({'seed': seed, 'classification': row['classification'], 'reason': row['reason']}), flush=True)
        report = report_for(True)
        if findings and report.status == 'pass':
            from dataclasses import replace
            report = replace(report, status='fail')
        checkpoint(report)
        return report
    finally:
        if stream is not None:
            stream.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--env', help='legacy module:SelectedReferenceEnvSubclass receipt mode')
    target.add_argument('--spec', type=Path, help='declarative candidate; unified CheckReport mode')
    parser.add_argument('--catalog', type=Path)
    parser.add_argument('--provider', required=True)
    seeds_group = parser.add_mutually_exclusive_group(required=True)
    seeds_group.add_argument('--seeds', type=int, nargs='+')
    seeds_group.add_argument('--count', type=int)
    parser.add_argument('--base-seed', type=int, default=0)
    parser.add_argument('--horizon', type=int)
    parser.add_argument('--core-repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.horizon is not None and not 1 <= args.horizon <= 6000:
        parser.error('horizon must be in [1, 6000]')
    if args.count is not None and args.count <= 0:
        parser.error('count must be positive')
    seeds = args.seeds if args.seeds is not None else list(range(args.base_seed, args.base_seed + args.count))
    if any(seed < 0 for seed in seeds) or len(set(seeds)) != len(seeds):
        parser.error('seeds must be nonnegative and unique')
    if args.spec:
        from catalog_query import core_context, build_catalog, validate_catalog, CatalogProvenanceError
        from harness_spec_schema import CandidateSpec, CheckReport, CheckFinding
        ctx = core_context(args.core_repo)
        try:
            spec = CandidateSpec.load(args.spec)
            if args.horizon is not None and args.horizon != spec.horizon:
                raise ValueError('candidate horizon must be revised in the spec, not overridden')
            catalog = json.loads(args.catalog.read_text()) if args.catalog else build_catalog(args.core_repo)
            if catalog['core_commit'] != ctx['core_commit'] or catalog['core_repo'] != ctx['core_repo']:
                raise CatalogProvenanceError('catalog provenance mismatch')
            validate_catalog(catalog)
        except CatalogProvenanceError as error:
            report = CheckReport(None, None, ctx['core_commit'], ctx['core_dirty'], 'feasibility_probe', 'error',
                [CheckFinding('catalog_provenance', 'execution_fault', 'harness', '', str(error), 'matching clean Core snapshot', {})])
            report.save(args.output)
            return 2
        except (ValueError, TypeError, KeyError, OSError) as error:
            report = CheckReport(None, None, ctx['core_commit'], ctx['core_dirty'], 'feasibility_probe', 'error',
                [CheckFinding('probe_input', 'spec_invalid', 'task_local', '', str(error), 'valid spec and catalog', {})])
            report.save(args.output)
            return 2
        report = run_candidate_probe(spec, catalog, args.provider, seeds, output=args.output)
        print(json.dumps({'status': report.status, 'output': str(args.output), 'totals': report.details.get('totals')}))
        return {'pass': 0, 'fail': 1, 'error': 2}[report.status]
    args.horizon = args.horizon or 6000
    from task_env.tasks.reference_env import SelectedReferenceEnv
    import task_env
    repo = args.core_repo.resolve()
    if Path(task_env.__file__).resolve().parent.parent != repo:
        parser.error('--core-repo does not match imported task_env')
    module, name = args.env.split(':', 1)
    env_class = getattr(importlib.import_module(module), name)
    if not isinstance(env_class, type) or not issubclass(env_class, SelectedReferenceEnv):
        parser.error('--env must name a SelectedReferenceEnv subclass')
    commit = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain'], text=True)
    report = dict(schema_version='harness-feasibility-probe-v1', env=args.env,
                  provider=args.provider, core_commit=commit, core_dirty=bool(dirty),
                  core_repo=str(repo), horizon=args.horizon, seeds=seeds,
                  created_at=datetime.now(timezone.utc).isoformat(),
                  completion_contract=COMPLETION_CONTRACT,
                  classification_policy='invalid first; solved requires task success, confirmed expert completion, no failure/flags, and successful close; then expert_failed; otherwise unknown.',
                  scope='Randomized reset/expert probe; expert failure is not task infeasibility; no qualification.',
                  status='running', artifact_hash=None, rows=[], totals={key: 0 for key in CLASSES})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as output:
        def checkpoint():
            output.seek(0)
            json.dump(report, output, indent=2, allow_nan=False)
            output.write('\n')
            output.truncate()
            output.flush()
        checkpoint()
        for seed in seeds:
            row = run_seed(env_class, args.provider, seed, args.horizon)
            report['rows'].append(row)
            hashes = {r['artifact_hash'] for r in report['rows'] if r['artifact_hash'] is not None}
            report['artifact_hash'] = next(iter(hashes)) if len(hashes) == 1 else None
            report['artifact_hashes'] = sorted(hashes)
            counts = Counter(r['classification'] for r in report['rows'])
            report['totals'] = {key: counts[key] for key in CLASSES}
            checkpoint()
            print(json.dumps(row), flush=True)
        report['status'] = 'complete'
        checkpoint()
    print(json.dumps({'output': str(args.output), 'totals': report['totals']}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
