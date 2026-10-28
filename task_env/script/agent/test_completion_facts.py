"""Defect-sensitive provider-free tests for Harness completion and consumers."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import construction_ledger
from completion_facts import COMPLETION_CONTRACT, validate_completion_row
from feasibility_probe import run_seed
from harness_spec_schema import CandidateSpec, CheckReport
import judge_package


ROOT = Path(__file__).resolve().parents[3]
CORE_COMMIT = 'c' * 40
SPEC = CandidateSpec.from_dict({
    'schema_version': 'harness-candidate-spec-v0',
    'task_id': 'mock/pick-lift-v0',
    'template': 'pick-lift-v0',
    'scene_config': {'table_top_z': 0.4, 'table_center_xy': [0.5, 0.0],
                     'table_half_size': [0.5, 0.5, 0.05]},
    'object_config': {'object_uid': 'mock-box', 'initial_pos_xy': [0.5, 0.0],
                      'reset_half_extent_m': 0.0, 'reset_z_fixed': True,
                      'asset_sha256': 'a' * 64},
    'success_config': {'lift_height_m': 0.08, 'reach_distance_m': 0.05,
                       'gripper_closed_opening_m': 0.04},
    'timebase_config': {'physics_dt': 0.002, 'control_substeps': 5},
    'required_capabilities': ['state_read'],
    'horizon': 1,
})
ARTIFACT_HASH = 'b' * 64


class ExecutionFault:
    phase = 'control_step'
    message = 'latched execution fault'

    def to_mapping(self):
        return {'phase': self.phase, 'message': self.message}


class FakeSolution:
    def __init__(self, outcome=None):
        self.done = False
        self.failed = False
        self.failure_reason = None
        self.stage = 'lift'
        self._outcome = outcome

    def outcome_report(self):
        return {} if self._outcome is None else self._outcome


class FakeEnv:
    def __init__(self, scenario):
        self.artifact = type('Artifact', (), {'identity_hash': ARTIFACT_HASH})()
        self.solution = FakeSolution(scenario.get('outcome'))
        self.execution_fault = None
        self.sample = None
        self.scenario = scenario
        self.closed = False

    def reset(self, *, seed):
        if self.scenario.get('reset_error'):
            raise RuntimeError('reset broke')
        self.info = {'is_success': False, 'task_metrics': {'task_success': False}}
        return {}, self.info

    def step_expert(self):
        scenario = self.scenario
        if scenario.get('step_error'):
            error = LookupError('step broke')
            if scenario.get('step_error_fault'):
                error.execution_fault = ExecutionFault()
            raise error
        if scenario.get('fault'):
            self.execution_fault = ExecutionFault()
        self.solution.done = scenario.get('done', True)
        self.solution.failed = scenario.get('failed', False)
        self.solution.failure_reason = 'expert route failed' if self.solution.failed else None
        self.info = {
            'is_success': scenario.get('success', True),
            'task_failure': scenario.get('task_failure', False),
            'task_metrics': {'task_success': scenario.get('success', True)},
        }
        return {}, 1.0, scenario.get('terminated', False), scenario.get('truncated', False), self.info

    def close(self):
        self.closed = True
        if self.scenario.get('mutate_on_close'):
            # Cleanup may invalidate live object access; facts were already snapshotted.
            self.solution = None
        if self.scenario.get('close_error'):
            raise OSError('close broke')


def make_row(seed):
    return {
        'seed': seed, 'artifact_hash': ARTIFACT_HASH, 'horizon': 1,
        'classification': 'solved', 'reason': 'task_and_expert_completion_confirmed',
        'phase': 'execution', 'construction_succeeded': True,
        'reset_attempted': True, 'reset_succeeded': True, 'steps': 1,
        'step_attempts': 1, 'terminated': False, 'truncated': False,
        'task_success': True, 'task_failure': False, 'solution_done': True,
        'solution_failed': False, 'expert_complete': True,
        'planned_trajectory_completed': None, 'outcome_complete': None,
        'unapproved_override_used': None, 'original_expert_lifecycle_status': None,
        'readiness_warnings': [], 'execution_lifecycle_status': None,
        'completion_basis': 'selected_expert_completion', 'completion_eligible': True,
        'execution_fault': None, 'close_attempted': True, 'close_succeeded': True,
        'cleanup_error': None, 'cleanup_traceback': None, 'error_phase': None,
        'error_type': None, 'error_message': None, 'error_traceback': None,
        'stage': 'lift', 'failure_reason': None,
    }


def make_report(rows=None):
    seeds = list(range(20))
    rows = rows if rows is not None else [make_row(seed) for seed in seeds]
    totals = {key: sum(row.get('classification') == key for row in rows)
              for key in ('solved', 'invalid', 'expert_failed', 'unknown')}
    return CheckReport(SPEC.spec_sha256(), ARTIFACT_HASH, CORE_COMMIT, False,
        'feasibility_probe', 'pass', details={
            'complete': True, 'provider': 'mujoco', 'horizon': SPEC.horizon,
            'seeds': seeds, 'rows': rows, 'totals': totals,
            'completion_contract': COMPLETION_CONTRACT,
        })


class RunSeedCompletionTests(unittest.TestCase):
    def run_scenario(self, scenario, *, horizon=1):
        env = FakeEnv(scenario)
        row = run_seed(lambda **kwargs: env, 'mujoco', 7, horizon)
        self.assertTrue(env.closed)
        return row

    def test_final_legal_step_can_complete_at_horizon(self):
        row = self.run_scenario({'done': True, 'success': True}, horizon=1)
        self.assertEqual(row['classification'], 'solved')
        self.assertEqual(row['steps'], 1)
        self.assertFalse(row['truncated'])
        self.assertTrue(row['close_succeeded'])
        validate_completion_row(row, expected_seed=7, expected_horizon=1,
                                 expected_artifact_hash=ARTIFACT_HASH)

    def test_done_with_terminated_or_truncated_is_not_solved(self):
        for flags in ({'terminated': True}, {'truncated': True}):
            with self.subTest(flags=flags):
                row = self.run_scenario({'done': True, 'success': True, **flags})
                self.assertEqual(row['classification'], 'unknown')
                self.assertFalse(row['completion_eligible'])
                validate_completion_row(row)

    def test_both_episode_flags_are_invalid(self):
        row = self.run_scenario({'done': True, 'success': True,
                                 'terminated': True, 'truncated': True})
        self.assertEqual(row['classification'], 'invalid')
        validate_completion_row(row)

    def test_task_failure_and_expert_failure_remain_distinct(self):
        failed_task = self.run_scenario({'done': True, 'success': True, 'task_failure': True})
        expert_failed = self.run_scenario({'done': False, 'success': False, 'failed': True})
        self.assertEqual(failed_task['classification'], 'unknown')
        self.assertEqual(expert_failed['classification'], 'expert_failed')
        self.assertTrue(failed_task['task_failure'])
        self.assertTrue(expert_failed['solution_failed'])
        validate_completion_row(failed_task)
        validate_completion_row(expert_failed)

    def test_execution_fault_is_invalid_even_with_success_facts(self):
        row = self.run_scenario({'done': True, 'success': True, 'fault': True})
        self.assertEqual(row['classification'], 'invalid')
        self.assertEqual(row['execution_fault']['phase'], 'control_step')
        validate_completion_row(row)

    def test_construction_reset_and_step_errors_are_captured_and_closed(self):
        def broken_constructor(**kwargs):
            raise ArithmeticError('construction broke')
        row = run_seed(broken_constructor, 'mujoco', 7, 1)
        self.assertEqual(row['classification'], 'invalid')
        self.assertEqual(row['error_phase'], 'construction')
        self.assertFalse(row['close_attempted'])
        validate_completion_row(row)

        reset = self.run_scenario({'reset_error': True})
        self.assertEqual(reset['classification'], 'invalid')
        self.assertEqual(reset['error_phase'], 'reset')
        self.assertTrue(reset['close_succeeded'])
        validate_completion_row(reset)

        step = self.run_scenario({'step_error': True})
        self.assertEqual(step['classification'], 'invalid')
        self.assertEqual(step['error_phase'], 'execution')
        self.assertEqual((step['step_attempts'], step['steps']), (1, 0))
        validate_completion_row(step)

    def test_close_failure_downgrades_success_and_preserves_both_errors(self):
        close_only = self.run_scenario({'done': True, 'success': True, 'close_error': True})
        self.assertEqual(close_only['classification'], 'invalid')
        self.assertEqual(close_only['error_phase'], 'close')
        self.assertIn('close broke', close_only['cleanup_error'])
        validate_completion_row(close_only)

        primary = self.run_scenario({'step_error': True, 'close_error': True})
        self.assertEqual(primary['error_type'], 'LookupError')
        self.assertEqual(primary['error_phase'], 'execution')
        self.assertIn('close broke', primary['cleanup_error'])
        validate_completion_row(primary)

        primary_fault = self.run_scenario({'step_error': True, 'step_error_fault': True,
                                           'close_error': True})
        self.assertEqual(primary_fault['error_type'], 'LookupError')
        self.assertEqual(primary_fault['reason'], 'LookupError: step broke')
        self.assertEqual(primary_fault['execution_fault']['message'], 'latched execution fault')
        self.assertIn('close broke', primary_fault['cleanup_error'])
        validate_completion_row(primary_fault)

    def test_close_state_change_does_not_rewrite_preclose_facts(self):
        row = self.run_scenario({'done': True, 'success': True, 'mutate_on_close': True})
        self.assertEqual(row['classification'], 'solved')
        self.assertTrue(row['solution_done'])
        validate_completion_row(row)

    def test_strict_outcome_requires_route_and_override_facts(self):
        outcome = {'expert_complete': True, 'planned_trajectory_completed': False,
                   'outcome_complete': True, 'unapproved_override_used': False,
                   'original_expert_lifecycle_status': {'expert_complete': True}}
        row = self.run_scenario({'done': True, 'success': True, 'outcome': outcome})
        self.assertEqual(row['classification'], 'unknown')
        self.assertEqual(row['completion_basis'], 'outcome_policy_and_full_planned_route')
        validate_completion_row(row)

    def test_lifecycle_failure_cannot_be_overridden_by_done(self):
        for outcome in (
            {'original_expert_lifecycle_status': {'expert_failed': True}},
            {'execution_lifecycle_status': 'failed'},
        ):
            with self.subTest(outcome=outcome):
                row = self.run_scenario({'done': True, 'success': True, 'outcome': outcome})
                self.assertEqual(row['classification'], 'expert_failed')
                self.assertFalse(row['completion_eligible'])
                validate_completion_row(row)


class ReportConsumerTests(unittest.TestCase):
    def test_valid_twenty_rows_pass_judge_and_ledger(self):
        report = make_report()
        checked = judge_package.check_probe(report,
            expected_spec_sha256=SPEC.spec_sha256(), expected_artifact_hash=ARTIFACT_HASH,
            expected_core_commit=CORE_COMMIT, expected_provider='mujoco',
            expected_horizon=SPEC.horizon)
        self.assertEqual(checked['totals']['solved'], 20)
        self.assertEqual(self.finish_with(report)['state'], 'candidate_ready')

    def mutate(self, name):
        report = make_report()
        details = deepcopy(report.details)
        row = details['rows'][5]
        if name == 'terminated':
            row.update(terminated=True, completion_eligible=False)
        elif name == 'truncated':
            row.update(truncated=True, completion_eligible=False)
        elif name == 'task_failure':
            row.update(task_failure=True, completion_eligible=False)
        elif name == 'expert_failed':
            row.update(solution_failed=True, expert_complete=False, completion_eligible=False)
        elif name == 'execution_fault':
            row['execution_fault'] = {'phase': 'control_step', 'message': 'fault'}
        elif name == 'cleanup_error':
            row.update(close_succeeded=False, cleanup_error='OSError: close broke',
                cleanup_traceback='traceback', error_phase='close', error_type='OSError',
                error_message='close broke', error_traceback='traceback', phase='close')
        elif name == 'close_not_confirmed':
            row['close_succeeded'] = False
        elif name == 'missing_fact':
            del row['expert_complete']
        elif name == 'wrong_type':
            row['terminated'] = 1
        elif name == 'strict_outcome_forgery':
            row.update(completion_basis='outcome_policy_and_full_planned_route',
                outcome_complete=True, completion_eligible=True)
        elif name == 'lifecycle_conflict':
            row['original_expert_lifecycle_status'] = {'expert_complete': False}
        elif name == 'lifecycle_expert_failed':
            row['original_expert_lifecycle_status'] = {'expert_failed': True}
        elif name == 'both_flags':
            row.update(terminated=True, truncated=True, completion_eligible=False)
        elif name == 'wrong_seed_order':
            details['rows'][0], details['rows'][1] = details['rows'][1], details['rows'][0]
        elif name == 'duplicate_seed':
            details['seeds'][1] = details['seeds'][0]
        elif name == 'bad_totals':
            details['totals']['unknown'] = 1
        elif name == 'old_report_no_contract':
            details.pop('completion_contract')
        elif name == 'incomplete':
            details['complete'] = False
        return replace(report, details=details)

    def finish_with(self, probe_report):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = root / 'task.json'
            task.write_text(json.dumps({'task_id': SPEC.task_id}))
            catalog = root / 'catalog.json'
            catalog.write_text(json.dumps({'core_dirty': False, 'core_commit': CORE_COMMIT,
                'providers': {'mujoco': {'available': True}}}))
            spec_path = root / 'spec.json'
            SPEC.save(spec_path)
            ledger = root / 'ledger.json'
            construction_ledger.initialize(ledger=ledger, task=task, catalog=catalog, provider='mujoco')
            construction_ledger.begin(ledger=ledger, spec=spec_path)
            reports = []
            for tool in ('asset_check', 'harness_compiler', 'semantic_check', 'feasibility_probe'):
                if tool == 'feasibility_probe':
                    report = probe_report
                else:
                    artifact_hash = None if tool == 'asset_check' else ARTIFACT_HASH
                    details = {} if tool == 'asset_check' else {'provider': 'mujoco'}
                    report = CheckReport(SPEC.spec_sha256(), artifact_hash, CORE_COMMIT, False,
                        tool, 'pass', details=details)
                path = root / f'{tool}.json'
                report.save(path)
                reports.append(path)
            return construction_ledger.finish(ledger=ledger, reports=reports)

    def test_forged_twenty_solved_reports_rejected_at_both_consumers(self):
        for name in ('terminated', 'truncated', 'task_failure', 'expert_failed',
                     'execution_fault', 'cleanup_error', 'close_not_confirmed',
                     'missing_fact', 'wrong_type', 'strict_outcome_forgery',
                     'lifecycle_conflict', 'lifecycle_expert_failed', 'both_flags', 'wrong_seed_order',
                     'duplicate_seed', 'bad_totals', 'old_report_no_contract', 'incomplete'):
            with self.subTest(tamper=name):
                report = self.mutate(name)
                with self.assertRaises((ValueError, TypeError)):
                    judge_package.check_probe(report,
                        expected_spec_sha256=SPEC.spec_sha256(), expected_artifact_hash=ARTIFACT_HASH,
                        expected_core_commit=CORE_COMMIT, expected_provider='mujoco',
                        expected_horizon=SPEC.horizon)
                with self.assertRaises((ValueError, TypeError)):
                    self.finish_with(report)

    def test_judge_rechecks_report_identity_and_context(self):
        report = make_report()
        for altered, expected in (
            (replace(report, spec_sha256='d' * 64), SPEC.spec_sha256()),
            (replace(report, artifact_hash='e' * 64), ARTIFACT_HASH),
            (replace(report, core_commit='d' * 40), CORE_COMMIT),
            (replace(report, core_dirty=True), None),
            (replace(report, details={**report.details, 'provider': 'other'}), None),
        ):
            with self.subTest(report=altered):
                with self.assertRaises((ValueError, TypeError)):
                    judge_package.check_probe(altered,
                        expected_spec_sha256=expected or SPEC.spec_sha256(),
                        expected_artifact_hash=ARTIFACT_HASH,
                        expected_core_commit=CORE_COMMIT, expected_provider='mujoco',
                        expected_horizon=SPEC.horizon)


if __name__ == '__main__':
    unittest.main()
