"""Provider-free tests for ledger issue escalation export and cited resolution."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import construction_ledger
from harness_spec_schema import CandidateSpec, CheckFinding, CheckReport

CORE_COMMIT = 'c' * 40
SPEC = CandidateSpec.from_dict({
    'schema_version': 'harness-candidate-spec-v0',
    'task_id': 'mock/pick-lift-v0',
    'template': 'pick-lift-v0',
    'scene_config': {'table_top_z': 0.4, 'table_center_xy': [0.5, 0.0], 'table_half_size': [0.5, 0.5, 0.05]},
    'object_config': {'object_uid': 'cube-v1', 'initial_pos_xy': [0.5, 0.0],
                      'reset_half_extent_m': 0.0, 'reset_z_fixed': True},
    'success_config': {'lift_height_m': 0.08, 'reach_distance_m': 0.05, 'gripper_closed_opening_m': 0.04},
    'timebase_config': {'physics_dt': 0.002, 'control_substeps': 5},
    'required_capabilities': ['state_read'],
    'horizon': 1,
})


class LedgerIssueTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'task.json').write_text(json.dumps({'task_id': SPEC.task_id}))
        (self.root / 'catalog.json').write_text(json.dumps({
            'core_dirty': False, 'core_commit': CORE_COMMIT, 'providers': {'mujoco': {'available': True}}}))
        SPEC.save(self.root / 'spec.json')
        self.ledger = self.root / 'ledger.json'
        construction_ledger.initialize(ledger=self.ledger, task=self.root / 'task.json',
                                       catalog=self.root / 'catalog.json', provider='mujoco')
        construction_ledger.begin(ledger=self.ledger, spec=self.root / 'spec.json')
        assets = self.root / 'assets.json'
        CheckReport(SPEC.spec_sha256(), None, CORE_COMMIT, False, 'asset_check', 'pass').save(assets)
        self.compile = self.root / 'compile.json'
        CheckReport(SPEC.spec_sha256(), None, CORE_COMMIT, False, 'harness_compiler', 'fail', [
            CheckFinding('provider_admission', 'capability_unsupported', 'provider', 'required_capabilities',
                         'x', 'admitted', {}),
            CheckFinding('reset_supported_by_table', 'init_infeasible', 'task_local', 'object_config', 1, 2, {}),
            CheckFinding('template_supported', 'template_missing', 'harness', 'template', 'a', 'b', {}),
        ], details={'provider': 'mujoco'}).save(self.compile)
        value = construction_ledger.finish(ledger=self.ledger, reports=[assets, self.compile])
        # The task_local finding is not an owner issue; findings 0 and 2 are.
        self.assertEqual([i['finding_index'] for i in value['open_issues']], [0, 2])
        self.compile_sha = value['open_issues'][0]['report']['sha256']
        self.evidence = self.root / 'owner-fix.diff'
        self.evidence.write_text('diff --git a b\n')

    def resolution(self, name='resolution.json', **changes):
        value = {'schema_version': construction_ledger.ISSUE_RESOLUTION, 'report_sha256': self.compile_sha,
                 'finding_index': 0, 'disposition': 'owner_fixed', 'owner': 'provider',
                 'reason': 'Provider owner admitted the capability in commit abc.',
                 'evidence': [str(self.evidence)]}
        value.update(changes)
        path = self.root / name
        path.write_text(json.dumps(value))
        return path

    def test_resolution_is_appended_without_rewriting_history(self):
        before = construction_ledger.load(self.ledger)
        value = construction_ledger.resolve_issue(ledger=self.ledger, issue_index=0, resolution=self.resolution())
        self.assertEqual(value['open_issues'], before['open_issues'])
        self.assertEqual((value['state'], value.get('stop_reason'), len(value['rounds'])),
                         (before['state'], before.get('stop_reason'), len(before['rounds'])))
        event = value['issue_events'][0]
        self.assertEqual((event['issue_index'], event['disposition'], event['owner']), (0, 'owner_fixed', 'provider'))
        self.assertEqual(event['evidence'], [construction_ledger.file_ref(self.evidence)])
        self.assertEqual(construction_ledger.unresolved_issue_indices(value), [1])
        self.assertEqual(construction_ledger.load(self.ledger)['issue_events'], value['issue_events'])

    def test_rejected_resolutions_leave_the_ledger_unchanged(self):
        original = self.ledger.read_bytes()
        empty = self.root / 'empty.txt'
        empty.write_text('')
        cases = {
            'different report/finding': (0, dict(finding_index=2)),
            'different report/finding ': (0, dict(report_sha256='0' * 64)),
            'disposition': (0, dict(disposition='accepted_limitation')),
            'owner': (0, dict(owner='task_local')),
            'reason required': (0, dict(reason='  ')),
            'cited evidence': (0, dict(evidence=[])),
            'not independent': (0, dict(evidence=[str(self.compile)])),
            'repeats a file': (0, dict(evidence=[str(self.evidence), str(self.evidence)])),
            'schema required': (0, dict(schema_version='other')),
            'must be absolute': (0, dict(evidence=['owner-fix.diff'])),
            'cannot be its own resolution evidence': (0, dict(evidence=[str(self.ledger)])),
            'out of range': (5, {}),
        }
        for index, (message, (issue_index, changes)) in enumerate(cases.items()):
            with self.subTest(message), self.assertRaisesRegex(ValueError, message.strip()):
                construction_ledger.resolve_issue(ledger=self.ledger, issue_index=issue_index,
                                                  resolution=self.resolution(f'bad{index}.json', **changes))
        with self.assertRaises(OSError):
            construction_ledger.resolve_issue(ledger=self.ledger, issue_index=0, resolution=self.resolution(
                'missing.json', evidence=[str(self.root / 'absent')]))
        self.assertEqual(self.ledger.read_bytes(), original)

    def test_an_issue_resolves_once_and_stale_evidence_invalidates_the_ledger(self):
        construction_ledger.resolve_issue(ledger=self.ledger, issue_index=0, resolution=self.resolution())
        with self.assertRaisesRegex(ValueError, 'already has a recorded resolution'):
            construction_ledger.resolve_issue(ledger=self.ledger, issue_index=0,
                                              resolution=self.resolution('again.json'))
        self.evidence.write_text('edited after the fact\n')
        with self.assertRaisesRegex(ValueError, 'stale/missing evidence'):
            construction_ledger.load(self.ledger)

    def test_tampered_events_are_rejected_on_load(self):
        construction_ledger.resolve_issue(ledger=self.ledger, issue_index=0, resolution=self.resolution())
        pristine = json.loads(self.ledger.read_text())

        def tamper(change):
            value = json.loads(json.dumps(pristine))
            change(value)
            self.ledger.write_text(json.dumps(value))

        tamper(lambda v: v['issue_events'][0].update(disposition='not_reproduced'))
        with self.assertRaisesRegex(ValueError, 'does not match its hashed resolution input'):
            construction_ledger.load(self.ledger)
        tamper(lambda v: v['issue_events'][0].update(issue_index=1))
        with self.assertRaisesRegex(ValueError, 'different report/finding'):
            construction_ledger.load(self.ledger)
        tamper(lambda v: v['issue_events'].append(dict(v['issue_events'][0])))
        with self.assertRaisesRegex(ValueError, 'resolved twice'):
            construction_ledger.load(self.ledger)

    def test_export_writes_escalations_and_never_modifies_the_ledger(self):
        construction_ledger.resolve_issue(ledger=self.ledger, issue_index=1, resolution=self.resolution(
            finding_index=2, owner='harness', disposition='not_reproduced'))
        original = self.ledger.read_bytes()
        out = self.root / 'issues'
        construction_ledger.export_issues(ledger=self.ledger, output_dir=out)
        self.assertEqual(self.ledger.read_bytes(), original)
        index = json.loads((out / 'issues.json').read_text())
        self.assertEqual(index['unresolved'], [0])
        self.assertEqual([(i['owner_hint'], i['status']) for i in index['issues']],
                         [('provider', 'open'), ('harness', 'resolution_recorded')])
        first = json.loads((out / 'issue-00.escalation.json').read_text())
        self.assertEqual((first['round'], first['finding']['check'], first['resolution']),
                         (1, 'provider_admission', None))
        # The template is directly usable once the owner fills in the open fields.
        template = {**first['resolution_template'], 'disposition': 'owner_fixed', 'owner': 'provider',
                    'reason': 'fixed', 'evidence': [str(self.evidence)]}
        path = self.root / 'from-template.json'
        path.write_text(json.dumps(template))
        value = construction_ledger.resolve_issue(ledger=self.ledger, issue_index=0, resolution=path)
        self.assertEqual(construction_ledger.unresolved_issue_indices(value), [])
        with self.assertRaises(FileExistsError):
            construction_ledger.export_issues(ledger=self.ledger, output_dir=out)

    def test_refuses_to_overwrite_a_ledger_that_changed_after_it_was_read(self):
        resolution = self.resolution()
        real_load = construction_ledger.load

        def load_then_concurrent_write(path):
            value = real_load(path)
            self.ledger.write_text(self.ledger.read_text() + '\n')  # another writer lands in between
            return value

        construction_ledger.load = load_then_concurrent_write
        try:
            with self.assertRaisesRegex(ValueError, 'ledger changed'):
                construction_ledger.resolve_issue(ledger=self.ledger, issue_index=0, resolution=resolution)
        finally:
            construction_ledger.load = real_load
        self.assertNotIn('issue_events', json.loads(self.ledger.read_text()))

    def test_package_requires_every_resolution_file(self):
        import judge_package
        value = construction_ledger.resolve_issue(ledger=self.ledger, issue_index=0, resolution=self.resolution())
        event = value['issue_events'][0]
        refs = [event['input'], *event['evidence']]
        index = {'files': [{'path': f'validation/history/refs/{r["sha256"]}/x', 'sha256': r['sha256']} for r in refs],
                 'relocations': {r['path']: f'validation/history/refs/{r["sha256"]}/x' for r in refs}}
        judge_package.check_issue_event_files(value, index)
        judge_package.check_issue_event_files({}, {'files': []})
        for broken in ({**index, 'relocations': {refs[0]['path']: index['relocations'][refs[0]['path']]}},
                       {**index, 'files': [{**index['files'][0]}, {**index['files'][1], 'sha256': '0' * 64}]}):
            with self.assertRaisesRegex(ValueError, 'missing from package'):
                judge_package.check_issue_event_files(value, broken)

    def test_cli_reports_unresolved_count(self):
        import contextlib
        import io
        argv = ['construction_ledger.py', 'resolve-issue', '--ledger', str(self.ledger), '--issue-index', '0',
                '--resolution', str(self.resolution())]
        stream = io.StringIO()
        old = sys.argv
        sys.argv = argv
        try:
            with contextlib.redirect_stdout(stream):
                code = construction_ledger.main()
        finally:
            sys.argv = old
        result = json.loads(stream.getvalue())
        self.assertEqual((result['open_issues'], result['unresolved_issues'], result['state']), (2, 1, 'stopped'))
        self.assertEqual(code, 1)  # the ledger is still stopped; resolution does not reopen it


if __name__ == '__main__':
    unittest.main()
