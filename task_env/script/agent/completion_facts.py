"""Raw completion facts shared by the Harness probe and its consumers."""
from __future__ import annotations

from collections.abc import Mapping
import re


COMPLETION_CONTRACT = 'harness-feasibility-completion-v1'
CLASSIFICATIONS = ('solved', 'invalid', 'expert_failed', 'unknown')
COMPLETION_BASES = {
    'selected_expert_completion',
    'outcome_policy_and_full_planned_route',
}
_SHA256 = re.compile(r'[0-9a-f]{64}')
_GIT_SHA = re.compile(r'[0-9a-f]{40}')
_PHASES = {'construction', 'reset', 'execution', 'close'}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _bool(value, name: str) -> bool:
    _require(type(value) is bool, f'{name} must be a boolean')
    return value


def _optional_bool(value, name: str) -> bool | None:
    _require(value is None or type(value) is bool, f'{name} must be a boolean or null')
    return value


def _capture_bool(value, name: str) -> bool:
    return _bool(value, name)


def capture_episode_facts(env, info, *, terminated, truncated, transitions):
    """Snapshot Core task/expert facts before cleanup can mutate the environment."""
    _require(isinstance(info, Mapping), 'step/reset info must be a mapping')
    metrics = info.get('task_metrics', {})
    _require(isinstance(metrics, Mapping), 'task_metrics must be a mapping')
    solution = env.solution
    outcome_method = getattr(solution, 'outcome_report', None)
    outcome = outcome_method() if callable(outcome_method) else {}
    _require(isinstance(outcome, Mapping), 'solution outcome_report must return a mapping')

    task_success = _capture_bool(
        metrics.get('task_success', info.get('is_success', False)), 'task_success'
    )
    task_failure = _capture_bool(info.get('task_failure', False), 'task_failure')
    solution_done = _capture_bool(solution.done, 'solution.done')
    solution_failed = _capture_bool(solution.failed, 'solution.failed')
    terminated = _capture_bool(terminated, 'terminated')
    truncated = _capture_bool(truncated, 'truncated')
    _require(type(transitions) is int and transitions >= 0, 'transitions must be a nonnegative int')

    planned = outcome.get('planned_trajectory_completed', info.get('planned_trajectory_completed'))
    outcome_complete = outcome.get('outcome_complete', info.get('outcome_complete'))
    override = outcome.get('unapproved_override_used', info.get('unapproved_override_used'))
    lifecycle = outcome.get(
        'original_expert_lifecycle_status', info.get('original_expert_lifecycle_status')
    )
    expert_complete = outcome.get('expert_complete', info.get('expert_complete'))
    if lifecycle is not None:
        _require(isinstance(lifecycle, Mapping), 'original expert lifecycle status must be a mapping or null')
        lifecycle = dict(lifecycle)
        for name in ('expert_complete', 'expert_failed'):
            if name in lifecycle:
                _optional_bool(lifecycle[name], f'lifecycle.{name}')
    if expert_complete is None and isinstance(lifecycle, Mapping):
        expert_complete = lifecycle.get('expert_complete')
    if expert_complete is None:
        expert_complete = solution_done and not solution_failed
    expert_complete = _capture_bool(expert_complete, 'expert_complete')
    planned = _optional_bool(planned, 'planned_trajectory_completed')
    outcome_complete = _optional_bool(outcome_complete, 'outcome_complete')
    override = _optional_bool(override, 'unapproved_override_used')

    if outcome_complete is None:
        completion_basis = 'selected_expert_completion'
        completion_eligible = (
            task_success and not task_failure and solution_done and not solution_failed
            and expert_complete
            and not (isinstance(lifecycle, Mapping) and lifecycle.get('expert_failed') is True)
            and outcome.get('execution_lifecycle_status') != 'failed'
        )
    else:
        completion_basis = 'outcome_policy_and_full_planned_route'
        completion_eligible = (
            task_success and not task_failure and solution_done and not solution_failed
            and expert_complete and planned is True and outcome_complete is True
            and override is False
            and not (isinstance(lifecycle, Mapping) and lifecycle.get('expert_failed') is True)
            and outcome.get('execution_lifecycle_status') != 'failed'
        )
    if terminated or truncated:
        completion_eligible = False

    warnings = outcome.get('readiness_warnings', info.get('readiness_warnings', []))
    _require(isinstance(warnings, (list, tuple)), 'readiness_warnings must be a list')
    execution_status = outcome.get('execution_lifecycle_status')
    _require(execution_status is None or isinstance(execution_status, str),
             'execution_lifecycle_status must be a string or null')

    return {
        'task_success': task_success,
        'task_failure': task_failure,
        'solution_done': solution_done,
        'solution_failed': solution_failed,
        'expert_complete': expert_complete,
        'planned_trajectory_completed': planned,
        'outcome_complete': outcome_complete,
        'unapproved_override_used': override,
        'original_expert_lifecycle_status': lifecycle,
        'readiness_warnings': list(warnings),
        'execution_lifecycle_status': execution_status,
        'terminated': terminated,
        'truncated': truncated,
        'transitions': transitions,
        'completion_basis': completion_basis,
        'completion_eligible': completion_eligible,
    }


def validate_completion_row(row, *, expected_seed=None, expected_horizon=None,
                            expected_artifact_hash=None):
    """Recompute a row's class from its raw facts; never trust its label alone."""
    _require(isinstance(row, dict), 'probe row must be an object')
    required = {
        'seed', 'artifact_hash', 'horizon', 'classification', 'reason', 'phase',
        'construction_succeeded', 'reset_attempted', 'reset_succeeded',
        'step_attempts', 'steps', 'terminated', 'truncated', 'task_success',
        'task_failure', 'solution_done', 'solution_failed', 'expert_complete',
        'planned_trajectory_completed', 'outcome_complete', 'unapproved_override_used',
        'original_expert_lifecycle_status', 'readiness_warnings',
        'execution_lifecycle_status', 'execution_fault', 'completion_basis',
        'completion_eligible', 'close_attempted', 'close_succeeded', 'cleanup_error',
        'cleanup_traceback', 'error_phase', 'error_type', 'error_message',
        'error_traceback', 'stage', 'failure_reason',
    }
    _require(required <= row.keys(), f'probe row missing facts: {sorted(required - row.keys())}')

    seed = row['seed']
    _require(type(seed) is int and seed >= 0, 'seed must be a nonnegative int')
    if expected_seed is not None:
        _require(seed == expected_seed, 'probe row seed/order mismatch')
    _require(type(row['horizon']) is int and 1 <= row['horizon'] <= 6000,
             'horizon must be an int in [1,6000]')
    if expected_horizon is not None:
        _require(row['horizon'] == expected_horizon, 'probe row horizon mismatch')
    artifact_hash = row['artifact_hash']
    _require(artifact_hash is None or (isinstance(artifact_hash, str) and _SHA256.fullmatch(artifact_hash)),
             'artifact_hash must be a SHA-256 or null')
    if row['construction_succeeded']:
        _require(artifact_hash is not None, 'constructed candidate row requires artifact identity')
        if expected_artifact_hash is not None:
            _require(artifact_hash == expected_artifact_hash, 'row artifact identity mismatch')
    else:
        _require(artifact_hash is None, 'failed construction cannot claim artifact identity')

    for name in ('construction_succeeded', 'reset_attempted', 'reset_succeeded',
                 'terminated', 'truncated', 'task_success', 'task_failure',
                 'solution_done', 'solution_failed', 'expert_complete',
                 'completion_eligible', 'close_attempted', 'close_succeeded'):
        _bool(row[name], name)
    _optional_bool(row['planned_trajectory_completed'], 'planned_trajectory_completed')
    _optional_bool(row['outcome_complete'], 'outcome_complete')
    _optional_bool(row['unapproved_override_used'], 'unapproved_override_used')
    _require(type(row['steps']) is int and row['steps'] >= 0, 'steps must be a nonnegative int')
    _require(type(row['step_attempts']) is int and row['step_attempts'] >= row['steps'],
             'step_attempts must be an int >= steps')
    _require(row['step_attempts'] <= row['steps'] + 1, 'only one incomplete step attempt is allowed')
    _require(row['reset_succeeded'] <= row['reset_attempted'], 'reset succeeded without an attempt')
    _require(not row['reset_attempted'] or row['construction_succeeded'],
             'reset attempted before construction completed')
    _require(not row['reset_succeeded'] or row['reset_attempted'], 'reset success without attempt')
    _require(row['close_attempted'] == row['construction_succeeded'],
             'constructed environments must receive exactly one close attempt')
    _require(not row['close_succeeded'] or row['close_attempted'], 'close success without attempt')

    for name in ('phase',):
        _require(row[name] in _PHASES, f'{name} is not a valid execution phase')
    for name in ('reason',):
        _require(isinstance(row[name], str) and bool(row[name]), f'{name} must be a nonempty string')
    for name in ('stage', 'failure_reason', 'execution_lifecycle_status'):
        _require(row[name] is None or isinstance(row[name], str), f'{name} must be a string or null')
    _require(isinstance(row['readiness_warnings'], list), 'readiness_warnings must be a list')
    lifecycle = row['original_expert_lifecycle_status']
    _require(lifecycle is None or isinstance(lifecycle, dict),
             'original_expert_lifecycle_status must be an object or null')
    if lifecycle is not None:
        for name in ('expert_complete', 'expert_failed'):
            if name in lifecycle:
                _optional_bool(lifecycle[name], f'lifecycle.{name}')
        if lifecycle.get('expert_complete') is not None:
            _require(lifecycle['expert_complete'] == row['expert_complete'],
                     'lifecycle expert completion conflicts with row fact')
        if lifecycle.get('expert_failed') is True:
            _require(not row['completion_eligible'],
                     'failed expert lifecycle cannot assert completion')

    fault = row['execution_fault']
    _require(fault is None or isinstance(fault, dict), 'execution_fault must be an object or null')
    if fault is not None:
        _require(isinstance(fault.get('phase'), str) and isinstance(fault.get('message'), str),
                 'execution_fault requires phase and message')
    cleanup_error = row['cleanup_error']
    _require(cleanup_error is None or isinstance(cleanup_error, str), 'cleanup_error must be string or null')
    _require(row['cleanup_traceback'] is None or isinstance(row['cleanup_traceback'], str),
             'cleanup_traceback must be string or null')
    if cleanup_error is not None:
        _require(row['close_attempted'] and not row['close_succeeded'],
                 'cleanup error conflicts with close result')
        _require(bool(row['cleanup_traceback']), 'cleanup error traceback is required')
    else:
        _require(row['close_succeeded'] or not row['close_attempted'],
                 'unsuccessful close requires cleanup error evidence')

    error_values = (row['error_phase'], row['error_type'], row['error_message'], row['error_traceback'])
    _require(all(value is None or isinstance(value, str) for value in error_values),
             'primary error facts must be strings or null')
    if any(value is not None for value in error_values):
        _require(all(isinstance(value, str) and value for value in error_values),
                 'primary error requires phase, type, message and traceback')
        _require(row['error_phase'] in _PHASES, 'primary error phase is invalid')
    _require(row['error_phase'] is None or row['phase'] == row['error_phase'],
             'primary error phase does not match row phase')
    if row['error_phase'] == 'reset':
        _require(row['reset_attempted'] and not row['reset_succeeded'],
                 'reset error facts conflict with reset result')
    if row['error_phase'] == 'execution':
        _require(row['reset_succeeded'], 'execution error without a completed reset')

    basis = row['completion_basis']
    invalid_cause_present = (
        fault is not None or row['error_type'] is not None or cleanup_error is not None
        or not row['construction_succeeded'] or not row['reset_succeeded']
        or (row['terminated'] and row['truncated'])
    )
    if row['reset_succeeded'] and basis is None and invalid_cause_present:
        # An execution can fail while facts are being read. Preserve the invalid row
        # without promoting its initialized false defaults to a completion claim.
        _require(row['completion_eligible'] is False,
                 'uncaptured completion facts cannot assert completion')
    elif row['reset_succeeded']:
        _require(basis in COMPLETION_BASES, 'reset episode requires a recognized completion basis')
        if row['outcome_complete'] is None:
            _require(basis == 'selected_expert_completion', 'fallback outcome basis mismatch')
            computed_eligible = (
                row['task_success'] and not row['task_failure'] and row['solution_done']
                and not row['solution_failed'] and row['expert_complete']
                and not (isinstance(lifecycle, dict) and lifecycle.get('expert_failed') is True)
                and row['execution_lifecycle_status'] != 'failed'
            )
        else:
            _require(basis == 'outcome_policy_and_full_planned_route', 'strict outcome basis mismatch')
            computed_eligible = (
                row['task_success'] and not row['task_failure'] and row['solution_done']
                and not row['solution_failed'] and row['expert_complete']
                and row['planned_trajectory_completed'] is True
                and row['outcome_complete'] is True
                and row['unapproved_override_used'] is False
                and not (isinstance(lifecycle, dict) and lifecycle.get('expert_failed') is True)
                and row['execution_lifecycle_status'] != 'failed'
            )
        if row['terminated'] or row['truncated']:
            computed_eligible = False
        _require(row['completion_eligible'] == computed_eligible,
                 'completion eligibility does not match raw outcome facts')
    else:
        _require(basis is None and row['completion_eligible'] is False,
                 'unreset row cannot assert completion')

    if row['terminated'] and row['truncated']:
        _require(row['classification'] == 'invalid', 'both terminal flags indicate invalid execution')
    if invalid_cause_present:
        expected_classification = 'invalid'
    elif row['solution_failed'] or (isinstance(lifecycle, dict) and lifecycle.get('expert_failed') is True) \
            or row['execution_lifecycle_status'] == 'failed':
        expected_classification = 'expert_failed'
    elif row['completion_eligible'] and not row['terminated'] and not row['truncated'] and row['close_succeeded']:
        expected_classification = 'solved'
    else:
        expected_classification = 'unknown'
    _require(row['classification'] in CLASSIFICATIONS, 'unknown probe classification')
    _require(row['classification'] == expected_classification,
             'probe classification does not follow raw completion/cleanup facts')
    return expected_classification


def validate_probe_report(report, *, expected_spec_sha256=None, expected_artifact_hash=None,
                          expected_core_commit=None, expected_provider=None,
                          expected_horizon=None, require_passing=False):
    """Validate report context, ordered seed rows, derived totals and completion facts."""
    _require(getattr(report, 'schema_version', None) == 'harness-check-report-v0',
             'unsupported feasibility report schema')
    _require(getattr(report, 'tool', None) == 'feasibility_probe', 'wrong feasibility report tool')
    _require(getattr(report, 'status', None) in {'pass', 'fail', 'error'}, 'invalid feasibility report status')
    spec_hash = getattr(report, 'spec_sha256', None)
    _require(isinstance(spec_hash, str) and _SHA256.fullmatch(spec_hash), 'feasibility report spec identity missing')
    if expected_spec_sha256 is not None:
        _require(spec_hash == expected_spec_sha256, 'feasibility report spec identity mismatch')
    artifact_hash = getattr(report, 'artifact_hash', None)
    _require(artifact_hash is None or (isinstance(artifact_hash, str) and _SHA256.fullmatch(artifact_hash)),
             'feasibility report artifact identity malformed')
    if expected_artifact_hash is not None:
        _require(artifact_hash == expected_artifact_hash, 'feasibility report artifact identity mismatch')
    core_commit = getattr(report, 'core_commit', None)
    _require(isinstance(core_commit, str) and _GIT_SHA.fullmatch(core_commit),
             'feasibility report Core identity missing')
    if expected_core_commit is not None:
        _require(core_commit == expected_core_commit, 'feasibility report Core identity mismatch')
    _require(getattr(report, 'core_dirty', None) is False, 'feasibility report must bind a clean Core')
    details = getattr(report, 'details', None)
    _require(isinstance(details, dict), 'feasibility report details must be an object')
    provider = details.get('provider')
    _require(isinstance(provider, str) and provider, 'feasibility report provider missing')
    if expected_provider is not None:
        _require(provider == expected_provider, 'feasibility report provider mismatch')
    horizon = details.get('horizon')
    if horizon is not None:
        _require(type(horizon) is int and 1 <= horizon <= 6000, 'feasibility report horizon invalid')
    if expected_horizon is not None:
        _require(horizon == expected_horizon, 'feasibility report horizon mismatch')
    if require_passing:
        _require(report.status == 'pass' and not report.findings, 'feasibility report is not a clean pass')
    if report.status == 'pass':
        _require(not report.findings, 'passing feasibility report contains findings')
        _require(artifact_hash is not None, 'passing feasibility report lacks artifact identity')

    complete = details.get('complete')
    _require(type(complete) is bool, 'feasibility report complete flag must be boolean')
    seeds = details.get('seeds')
    rows = details.get('rows')
    if seeds is None and rows is None:
        _require(not complete and report.status != 'pass',
                 'passing feasibility report cannot omit seed rows')
        return {'complete': False, 'row_count': 0, 'totals': {key: 0 for key in CLASSIFICATIONS}}
    _require(isinstance(seeds, list) and isinstance(rows, list), 'probe seeds and rows must both be lists')
    _require(bool(seeds), 'probe must declare at least one seed')
    _require(all(type(seed) is int and seed >= 0 for seed in seeds), 'probe seeds must be nonnegative ints')
    _require(len(seeds) == len(set(seeds)), 'probe seeds must be unique')
    _require(len(rows) <= len(seeds), 'probe has more rows than declared seeds')
    if complete:
        _require(len(rows) == len(seeds), 'complete probe is missing seed rows')
    else:
        _require(report.status != 'pass', 'passing probe cannot be incomplete')
    totals = {key: 0 for key in CLASSIFICATIONS}
    for index, row in enumerate(rows):
        classification = validate_completion_row(
            row, expected_seed=seeds[index], expected_horizon=horizon,
            expected_artifact_hash=artifact_hash,
        )
        totals[classification] += 1
    declared_totals = details.get('totals')
    _require(isinstance(declared_totals, dict) and set(declared_totals) == set(CLASSIFICATIONS),
             'probe totals must contain exactly the four classifications')
    _require(all(type(value) is int and value >= 0 for value in declared_totals.values()),
             'probe totals must be nonnegative ints')
    _require(declared_totals == totals, 'probe totals do not match independently classified rows')
    if report.status == 'pass':
        _require(complete and len(seeds) >= 20, 'passing probe requires 20 complete distinct seeds')
        _require(totals == {'solved': len(seeds), 'invalid': 0, 'expert_failed': 0, 'unknown': 0},
                 'passing probe requires every declared seed solved')
        _require(details.get('completion_contract') == COMPLETION_CONTRACT,
                 'passing report lacks current raw-completion contract; legacy report is unverifiable')
    return {'complete': complete, 'row_count': len(rows), 'totals': totals}
