"""Provider-free tests for the read-only provider comparison and ledger summary."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import compare_providers
import construction_ledger
from feasibility_probe import initial_row
import ledger_summary
from harness_spec_schema import CandidateSpec, CheckFinding, CheckReport

CORE_COMMIT = 'c' * 40
SPEC = CandidateSpec.from_dict({
    'schema_version': 'harness-candidate-spec-v0',
    'task_id': 'mock/pick-lift-v0',
    'template': 'pick-lift-v0',
    'scene_config': {'table_top_z': 0.4, 'table_center_xy': [0.5, 0.0], 'table_half_size': [0.5, 0.5, 0.05]},
    'object_config': {'object_uid': 'cube-v1', 'initial_pos_xy': [0.5, 0.0],
                      'reset_half_extent_m': 0.1, 'reset_z_fixed': True},
    'success_config': {'lift_height_m': 0.08, 'reach_distance_m': 0.05, 'gripper_closed_opening_m': 0.04},
    'timebase_config': {'physics_dt': 0.002, 'control_substeps': 5},
    'required_capabilities': ['state_read'],
    'horizon': 100,
})


class Workspace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)


class CompareProvidersTest(Workspace):
    def probe(self, provider, outcomes, *, spec=SPEC, x=0.5, tool='feasibility_probe'):
        rows = []
        for seed, (classification, steps) in outcomes.items():
            row = initial_row(seed, spec.horizon)
            row.update(classification=classification, steps=steps, phase='execution', stage='lift', reason='r',
                       start_pose={'cube-v1': {'position': [x, 0.0, 0.43], 'quaternion_wxyz': [1.0, 0.0, 0.0, 0.0]}})
            rows.append(row)
        path = self.root / f'{provider}-{len(list(self.root.iterdir()))}.json'
        CheckReport(spec.spec_sha256(), 'b' * 64, CORE_COMMIT, False, tool, 'fail', [],
                    details={'complete': True, 'provider': provider, 'horizon': spec.horizon,
                             'seeds': list(outcomes), 'rows': rows}).save(path)
        return path

    def test_per_seed_agreement_and_pose_spread(self):
        a = self.probe('mujoco', {0: ('solved', 380), 1: ('solved', 390), 2: ('expert_failed', 100)})
        b = self.probe('isaacsim', {0: ('solved', 387), 1: ('expert_failed', 50), 3: ('solved', 379)}, x=0.5000001)
        result = compare_providers.compare([a, b])
        self.assertEqual(result['summary'], {'seeds_compared': 2, 'agree': 1, 'disagree': 1,
                                             'disagreeing_seeds': [1], 'seeds_not_in_all_reports': [2, 3]})
        self.assertTrue(result['same_spec'] and result['same_core_commit'] and result['same_horizon'])
        seed0, seed1, seed2 = result['seeds'][:3]
        self.assertEqual(seed0['outcomes']['isaacsim']['steps'], 387)
        self.assertAlmostEqual(seed0['start_position_max_difference_m']['cube-v1'], 1e-7)
        self.assertEqual((seed1['comparison'], seed2['comparison']), ('disagree', 'not_in_all_reports'))
        self.assertIsNone(seed2['outcomes']['isaacsim'])
        self.assertIsNone(seed2['start_position_max_difference_m'])
        # A third provider without a usable pose removes the spread instead of narrowing it.
        c = self.probe('geophys', {0: ('solved', 381)})
        value = json.loads(c.read_text())
        value['details']['rows'][0]['start_pose'] = {'cube-v1': None}
        c.write_text(json.dumps(value))
        three = compare_providers.compare([a, b, c])
        self.assertIsNone(three['seeds'][0]['start_position_max_difference_m'])
        self.assertEqual(result['providers']['mujoco']['totals']['solved'], 2)
        # Synthetic rows lack the completion facts, so they are shown but never marked verified.
        self.assertFalse(result['all_reports_contract_verified'])
        self.assertIsInstance(result['providers']['mujoco']['completion_contract_error'], str)

    def test_reports_meeting_the_completion_contract_are_marked_verified(self):
        from dataclasses import replace
        from test_completion_facts import make_report
        paths = []
        for provider in ('mujoco', 'geophys'):
            report = make_report()
            path = self.root / f'valid-{provider}.json'
            replace(report, details={**report.details, 'provider': provider}).save(path)
            paths.append(path)
        result = compare_providers.compare(paths)
        self.assertTrue(result['all_reports_contract_verified'])
        self.assertEqual((result['summary']['agree'], result['summary']['disagree']), (20, 0))

    def test_failed_reports_without_the_current_contract_marker_stay_unverified(self):
        from dataclasses import replace
        from test_completion_facts import make_report, make_row
        paths = []
        for provider in ('mujoco', 'geophys'):
            rows = [make_row(0)]
            report = make_report(rows)
            details = {**report.details, 'provider': provider, 'seeds': [0, 1], 'complete': False,
                       'completion_contract': 'harness-feasibility-completion-v0'}
            path = self.root / f'legacy-{provider}.json'
            replace(report, status='error', details=details).save(path)
            paths.append(path)
        result = compare_providers.compare(paths)
        self.assertFalse(result['all_reports_contract_verified'])
        self.assertIn('current completion contract', result['providers']['mujoco']['completion_contract_error'])

    def test_unidentified_specs_are_not_a_match(self):
        paths = []
        for provider in ('mujoco', 'geophys'):
            path = self.probe(provider, {0: ('solved', 1)})
            value = json.loads(path.read_text())
            value['spec_sha256'] = None
            path.write_text(json.dumps(value))
            paths.append(path)
        with self.assertRaisesRegex(compare_providers.ComparisonInputError, 'one identified spec'):
            compare_providers.compare(paths)
        self.assertFalse(compare_providers.compare(paths, allow_spec_mismatch=True)['same_spec'])

    def test_rejects_incomparable_inputs(self):
        a = self.probe('mujoco', {0: ('solved', 1)})
        other = CandidateSpec.from_dict({**SPEC.to_dict(), 'horizon': 50})
        cases = {
            'at least two': [a],
            'each provider may appear once': [a, self.probe('mujoco', {0: ('solved', 1)})],
            'one identified spec': [a, self.probe('geophys', {0: ('solved', 1)}, spec=other)],
            'expected a feasibility_probe report': [a, self.probe('geophys', {0: ('solved', 1)}, tool='semantic_check')],
            'no episode rows': [a, self.probe('geophys', {})],
        }
        for message, paths in cases.items():
            with self.subTest(message), self.assertRaisesRegex(compare_providers.ComparisonInputError, message):
                compare_providers.compare(paths)

    def test_spec_mismatch_is_opt_in_and_recorded(self):
        other = CandidateSpec.from_dict({**SPEC.to_dict(), 'horizon': 50})
        paths = [self.probe('mujoco', {0: ('solved', 1)}), self.probe('isaacsim', {0: ('solved', 1)}, spec=other)]
        out = self.root / 'comparison.json'
        argv = ['--reports', *map(str, paths), '--output', str(out)]
        self.assertEqual(compare_providers.main(argv), 2)
        self.assertFalse(out.exists())
        self.assertEqual(compare_providers.main([*argv, '--allow-spec-mismatch']), 0)
        result = json.loads(out.read_text())
        self.assertEqual((result['same_spec'], result['same_horizon']), (False, False))
        self.assertEqual(compare_providers.main([*argv, '--allow-spec-mismatch']), 2)  # never overwrites


class LedgerSummaryTest(Workspace):
    def test_summary_shows_rounds_revision_and_issues(self):
        root = self.root
        (root / 'task.json').write_text(json.dumps({'task_id': SPEC.task_id}))
        (root / 'catalog.json').write_text(json.dumps({
            'core_dirty': False, 'core_commit': CORE_COMMIT, 'providers': {'mujoco': {'available': True}}}))
        ledger = root / 'ledger.json'
        construction_ledger.initialize(ledger=ledger, task=root / 'task.json', catalog=root / 'catalog.json',
                                       provider='mujoco')
        self.assertIn('Rounds used: 0 of 5', ledger_summary.render(ledger))

        def run_round(name, spec, findings, revision=None):
            (root / name).mkdir()
            spec.save(root / name / 'spec.json')
            construction_ledger.begin(ledger=ledger, spec=root / name / 'spec.json', revision=revision)
            assets = root / name / 'assets.json'
            CheckReport(spec.spec_sha256(), None, CORE_COMMIT, False, 'asset_check', 'pass').save(assets)
            compiled = root / name / 'compile.json'
            CheckReport(spec.spec_sha256(), None, CORE_COMMIT, False, 'harness_compiler', 'fail', findings,
                        details={'provider': 'mujoco'}).save(compiled)
            construction_ledger.finish(ledger=ledger, reports=[assets, compiled])
            return compiled

        first = run_round('round1', SPEC, [CheckFinding(
            'reset_supported_by_table', 'init_infeasible', 'task_local', 'object_config.initial_pos_xy[0]', 1, 2, {})])
        revision = root / 'revision.json'
        revision.write_text(json.dumps({'report_sha256': construction_ledger.file_ref(first)['sha256'],
                                        'finding_index': 0,
                                        'reason': 'Narrow the reset | to fit the table. <b>\n# Round 9: pass'}))
        narrowed = CandidateSpec.from_dict({**SPEC.to_dict(), 'object_config': {
            **SPEC.object_config, 'reset_half_extent_m': 0.05}})
        second = run_round('round2', narrowed, [CheckFinding(
            'provider_admission', 'capability_unsupported', 'provider', '', 'x', 'y', {})], revision)

        text = ledger_summary.render(ledger)
        self.assertIn('State: **stopped** (stop reason: `owner_escalation`)', text)
        self.assertIn('Rounds used: 2 of 5', text)
        self.assertIn('Issues: 1 recorded, 1 without a recorded resolution', text)
        self.assertIn('## Round 1: fail', text)
        self.assertIn('Initial candidate.', text)
        self.assertIn('`reset_supported_by_table` (init_infeasible, task_local)', text)
        self.assertIn('Reason: Narrow the reset \\| to fit the table. &lt;b&gt; \\# Round 9: pass', text)
        self.assertNotIn('\n# Round 9', text)
        self.assertIn('| `object_config.reset_half_extent_m` | 0.1 | 0.05 |', text)
        self.assertIn('| 0 | 2 | `provider_admission` | capability_unsupported | provider | none recorded |', text)

        evidence = root / 'fix.diff'
        evidence.write_text('diff\n')
        resolution = root / 'resolution.json'
        resolution.write_text(json.dumps({
            'schema_version': construction_ledger.ISSUE_RESOLUTION,
            'report_sha256': construction_ledger.file_ref(second)['sha256'], 'finding_index': 0,
            'disposition': 'owner_fixed', 'owner': 'provider', 'reason': 'fixed', 'evidence': [str(evidence)]}))
        construction_ledger.resolve_issue(ledger=ledger, issue_index=0, resolution=resolution)
        before = ledger.read_bytes()
        out = root / 'summary.md'
        self.assertEqual(ledger_summary.main(['--ledger', str(ledger), '--output', str(out)]), 0)
        self.assertIn('owner_fixed by provider (owner claim)', out.read_text())
        self.assertIn('1 recorded, 0 without a recorded resolution', out.read_text())
        self.assertEqual(ledger.read_bytes(), before)
        self.assertEqual(ledger_summary.main(['--ledger', str(ledger), '--output', str(out)]), 2)

        evidence.write_text('tampered\n')  # stale evidence must fail, not render
        self.assertEqual(ledger_summary.main(['--ledger', str(ledger)]), 2)


if __name__ == '__main__':
    unittest.main()
