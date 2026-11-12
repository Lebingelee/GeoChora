"""Provider-free tests for the failed-probe diagnosis helper."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import diagnose_candidate
from feasibility_probe import initial_row
from harness_spec_schema import CandidateSpec, CheckFinding, CheckReport

CENTER = [0.5, 0.0]
SPEC = CandidateSpec.from_dict({
    'schema_version': 'harness-candidate-spec-v0',
    'task_id': 'mock/pick-lift-v0',
    'template': 'pick-lift-v0',
    'scene_config': {'table_top_z': 0.4, 'table_center_xy': CENTER, 'table_half_size': [0.5, 0.5, 0.05]},
    'object_config': {'object_uid': 'cube-v1', 'initial_pos_xy': CENTER,
                      'reset_half_extent_m': 0.1, 'reset_z_fixed': True},
    'success_config': {'lift_height_m': 0.08, 'reach_distance_m': 0.05, 'gripper_closed_opening_m': 0.04},
    'timebase_config': {'physics_dt': 0.002, 'control_substeps': 5},
    'required_capabilities': ['state_read'],
    'horizon': 100,
})


def row(seed, classification, offset, *, stage='lift', reason='r', pose=True):
    value = initial_row(seed, SPEC.horizon)
    value.update(classification=classification, phase='execution', stage=stage, reason=reason, steps=7)
    if pose:
        value['start_pose'] = {'cube-v1': {'position': [CENTER[0] + offset[0], CENTER[1] + offset[1], 0.43],
                                           'quaternion_wxyz': [1.0, 0.0, 0.0, 0.0]}}
    return value


def finding(seed, index, *, category='expert_failed', locality='unknown'):
    return CheckFinding('expert_completion', category, locality, 'object_config', 'r', 'done',
                        {'seed': seed, 'row_index': index})


class DiagnoseCandidateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.spec_path = self.root / 'candidate.spec.json'
        SPEC.save(self.spec_path)

    def report(self, rows, findings, *, spec=SPEC, tool='feasibility_probe', name='feasibility.json'):
        totals = {key: sum(r['classification'] == key for r in rows)
                  for key in ('solved', 'invalid', 'expert_failed', 'unknown')}
        path = self.root / name
        CheckReport(spec.spec_sha256(), 'b' * 64, 'c' * 40, False, tool, 'fail', findings,
                    details={'complete': True, 'provider': 'mujoco', 'horizon': spec.horizon,
                             'seeds': [r['seed'] for r in rows], 'rows': rows, 'totals': totals}).save(path)
        return path

    def mixed(self):
        rows = [row(0, 'solved', (0.0, 0.0)), row(1, 'solved', (0.02, -0.02)),
                row(2, 'expert_failed', (0.08, 0.0), stage='descend', reason='grasp_lost'),
                row(3, 'expert_failed', (0.09, 0.01), stage='descend', reason='grasp_lost'),
                row(4, 'invalid', (0.01, 0.0), stage='reach', reason='fault')]
        findings = [finding(2, 2), finding(3, 3), finding(4, 4, category='execution_fault')]
        return self.report(rows, findings)

    def test_groups_offsets_and_citable_findings(self):
        summary, specs = diagnose_candidate.diagnose(self.mixed(), self.spec_path)
        self.assertEqual(summary['totals'], {'solved': 2, 'invalid': 1, 'expert_failed': 2, 'unknown': 0})
        self.assertTrue(summary['declared_totals_match'])
        groups = summary['non_solved_groups']
        self.assertEqual([(g['stage'], g['seeds']) for g in groups], [('descend', [2, 3]), ('reach', [4])])
        seed2 = summary['seeds'][2]
        self.assertAlmostEqual(seed2['offset_from_reset_center_xy'][0], 0.08)
        self.assertAlmostEqual(seed2['offset_fraction_of_half_extent'][0], 0.8)
        self.assertEqual(seed2['finding_indices'], [0])
        # Seed 4 failed inside the solved offset box; only 2 and 3 lie beyond it.
        self.assertEqual(summary['offset_bounds']['non_solved_seeds_outside_solved_bounds'], [2, 3])
        flags = [(f['spec_revision_allowed'], f['diagnostics_required']) for f in summary['findings']]
        self.assertEqual(flags, [(True, True), (True, True), (False, False)])
        self.assertEqual(sorted(specs), [f'fixed-pose-seed{n}.spec.json' for n in (2, 3, 4)])

    def test_fixed_pose_spec_pins_recorded_pose_with_new_identity(self):
        _, specs = diagnose_candidate.diagnose(self.mixed(), self.spec_path, seeds=[3])
        self.assertEqual(list(specs), ['fixed-pose-seed3.spec.json'])
        fixed = specs['fixed-pose-seed3.spec.json']
        self.assertEqual(fixed.object_config['reset_half_extent_m'], 0.0)
        self.assertEqual(fixed.object_config['initial_pos_xy'], [CENTER[0] + 0.09, CENTER[1] + 0.01])
        self.assertNotEqual(fixed.spec_sha256(), SPEC.spec_sha256())
        changed = {k for k in SPEC.to_dict() if SPEC.to_dict()[k] != fixed.to_dict()[k]}
        self.assertEqual(changed, {'object_config'})

    def test_write_is_exclusive_and_records_absolute_spec_paths(self):
        out = self.root / 'diag'
        code = diagnose_candidate.main(['--report', str(self.mixed()), '--spec', str(self.spec_path),
                                        '--output-dir', str(out)])
        self.assertEqual(code, 0)
        summary = json.loads((out / 'summary.json').read_text())
        self.assertEqual(summary['source']['spec_sha256'], SPEC.spec_sha256())
        for entry in summary['fixed_pose_diagnostics']:
            self.assertEqual(CandidateSpec.load(entry['spec']).spec_sha256(), entry['spec_sha256'])
        again = diagnose_candidate.main(['--report', str(self.root / 'feasibility.json'),
                                         '--spec', str(self.spec_path), '--output-dir', str(out)])
        self.assertEqual(again, 2)

    def test_skips_missing_duplicate_and_already_fixed_poses(self):
        rows = [row(0, 'unknown', (0.05, 0.0), pose=False), row(1, 'expert_failed', (0.05, 0.0)),
                row(2, 'expert_failed', (0.05, 0.0))]
        summary, specs = diagnose_candidate.diagnose(self.report(rows, [finding(1, 1)]), self.spec_path)
        skipped = [e['skipped'] for e in summary['fixed_pose_diagnostics']]
        self.assertIn('not recorded', skipped[0])
        self.assertIsNone(skipped[1])
        self.assertEqual(skipped[2], 'same pose as seed 1')
        self.assertEqual(len(specs), 1)

        pinned = CandidateSpec.from_dict({**SPEC.to_dict(), 'object_config': {
            **SPEC.object_config, 'reset_half_extent_m': 0.0}})
        pinned_path = self.root / 'pinned.spec.json'
        pinned.save(pinned_path)
        # A provider may record the pinned pose rounded (Isaac float32 center):
        # the spec hash would change although the reset does not.
        report = self.report([row(9, 'expert_failed', (-1.62e-08, 0.0))], [finding(9, 0)], spec=pinned, name='pinned.json')
        summary, specs = diagnose_candidate.diagnose(report, pinned_path)
        self.assertEqual(specs, {})
        self.assertIn('not an independent diagnostic', summary['fixed_pose_diagnostics'][0]['skipped'])
        self.assertIsNone(summary['seeds'][0]['offset_fraction_of_half_extent'])

    def test_cited_hash_is_the_snapshot_that_was_parsed(self):
        path = self.mixed()
        first = path.read_bytes()
        later = self.report([row(0, 'expert_failed', (0.0, 0.0))], [finding(0, 0)], name='later.json').read_bytes()
        original = Path.read_bytes
        reads = []

        def advancing(target):
            # The probe checkpoints the same file; a second read sees newer bytes.
            if target == path.resolve():
                reads.append(target)
                return first if len(reads) == 1 else later
            return original(target)

        with mock.patch.object(Path, 'read_bytes', advancing), \
                mock.patch.object(Path, 'read_text', lambda target, *a, **k: advancing(target).decode()):
            summary, _ = diagnose_candidate.diagnose(path, self.spec_path)
        self.assertEqual(summary['source']['report_sha256'], hashlib.sha256(first).hexdigest())
        self.assertEqual(len(summary['seeds']), 5)

    def test_rejects_unbound_or_undiagnosable_inputs(self):
        other = CandidateSpec.from_dict({**SPEC.to_dict(), 'horizon': 50})
        cases = {
            'different spec': self.report([row(0, 'unknown', (0, 0))], [], spec=other, name='a.json'),
            'feasibility_probe report': self.report([row(0, 'unknown', (0, 0))], [], tool='semantic_check', name='b.json'),
            'no episode rows': self.report([], [], name='c.json'),
            'repeat a seed': self.report([row(0, 'unknown', (0, 0)), row(0, 'unknown', (0, 0))], [], name='d.json'),
        }
        for message, path in cases.items():
            with self.subTest(message), self.assertRaisesRegex(diagnose_candidate.DiagnosisInputError, message):
                diagnose_candidate.diagnose(path, self.spec_path)
        mixed = self.mixed()
        for seeds, message in (([0], 'solved'), ([99], 'not in the report'), ([2, 2], 'repeats')):
            with self.subTest(seeds), self.assertRaisesRegex(diagnose_candidate.DiagnosisInputError, message):
                diagnose_candidate.diagnose(mixed, self.spec_path, seeds=seeds)

    def test_ambiguous_entities_need_an_explicit_object_key(self):
        value = row(0, 'expert_failed', (0.03, 0.0))
        value['start_pose']['other'] = {'position': [0.0, 0.0, 0.0], 'quaternion_wxyz': [1.0, 0.0, 0.0, 0.0]}
        path = self.report([value], [finding(0, 0)])
        with self.assertRaisesRegex(diagnose_candidate.DiagnosisInputError, '--object-key'):
            diagnose_candidate.diagnose(path, self.spec_path)
        summary, _ = diagnose_candidate.diagnose(path, self.spec_path, object_key='cube-v1')
        self.assertAlmostEqual(summary['seeds'][0]['offset_from_reset_center_xy'][0], 0.03)
        with self.assertRaisesRegex(diagnose_candidate.DiagnosisInputError, 'absent'):
            diagnose_candidate.diagnose(path, self.spec_path, object_key='missing')


if __name__ == '__main__':
    unittest.main()
