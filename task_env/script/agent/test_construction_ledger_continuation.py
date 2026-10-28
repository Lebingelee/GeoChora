"""Defect-sensitive tests for owner-repair continuation and immutable history."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import construction_ledger as ledger_api
from harness_spec_schema import CandidateSpec, CheckFinding, CheckReport, save_json


ROOT = Path(__file__).resolve().parents[3]
AGENT = Path(__file__).resolve().parent
OLD_CORE = 'a' * 40
NEW_CORE = 'b' * 40
ARTIFACT = 'c' * 64


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_spec(uid, asset_hash):
    return CandidateSpec.from_dict({
        'schema_version': 'harness-candidate-spec-v0',
        'task_id': 'mock/pick-lift-v0',
        'template': 'pick-lift-v0',
        'scene_config': {'table_top_z': 0.4, 'table_center_xy': [0.5, 0.0],
                         'table_half_size': [0.5, 0.5, 0.05]},
        'object_config': {'object_uid': uid, 'initial_pos_xy': [0.5, 0.0],
                          'reset_half_extent_m': 0.06, 'reset_z_fixed': True,
                          'asset_sha256': asset_hash},
        'success_config': {'lift_height_m': 0.1, 'reach_distance_m': 0.05,
                           'gripper_closed_opening_m': 0.04},
        'timebase_config': {'physics_dt': 0.002, 'control_substeps': 5},
        'required_capabilities': ['state_read'], 'horizon': 6000,
    })


class OwnerRepairContinuationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.old = self.base / 'old'
        self.old.mkdir()
        (self.old / 'assets').mkdir()
        (self.old / 'assets/old.xml').write_text('<body name="old"/>\n')
        old_asset = sha(self.old / 'assets/old.xml')
        (self.old / 'asset_bundle.json').write_text(json.dumps({
            'synthetic': True, 'assets': [{'uid': 'mock-box-v1', 'path': 'assets/old.xml',
                'sha256': old_asset, 'version': 'v1'}]}, indent=2) + '\n')
        (self.old / 'semantic_examples.json').write_text('{"cases":[]}\n')
        (self.old / 'task.json').write_text(json.dumps({'task_id': 'mock/pick-lift-v0',
            'asset_bundle': 'asset_bundle.json', 'semantic_examples': 'semantic_examples.json'}, indent=2) + '\n')
        self.old_spec = make_spec('mock-box-v1', old_asset)
        self.old_spec_path = self.old / 'round1.spec.json'
        self.old_spec.save(self.old_spec_path)
        self.old_catalog = self.old / 'catalog.json'
        save_json(self.catalog(OLD_CORE), self.old_catalog)
        self.old_ledger_path = self.old / 'construction.json'
        ledger_api.initialize(ledger=self.old_ledger_path, task=self.old / 'task.json',
            catalog=self.old_catalog, provider='mujoco')
        ledger_api.begin(ledger=self.old_ledger_path, spec=self.old_spec_path)
        failed = CheckReport(self.old_spec.spec_sha256(), None, OLD_CORE, False,
            'asset_check', 'fail', [CheckFinding('asset_check', 'asset_missing', 'task_local',
                'object_config.asset_sha256', None, old_asset, {'asset_uid': 'mock-box-v1'})],
            {'provider': 'mujoco'})
        self.old_report = self.old / 'round1.asset_check.json'
        failed.save(self.old_report)
        ledger_api.finish(ledger=self.old_ledger_path, reports=[self.old_report])
        # Keep a historical issue to prove continuation cannot silently clear it.
        data = json.loads(self.old_ledger_path.read_text())
        data['open_issues'] = [{'report': ledger_api.file_ref(self.old_report),
            'finding_index': 0, 'status': 'open', 'sent': False}]
        self.old_ledger_path.write_text(json.dumps(data, indent=2) + '\n')
        self.archive_path = self.make_archive(data)
        self.new = self.base / 'new'
        self.new.mkdir()
        (self.new / 'assets').mkdir()
        (self.new / 'assets/new.xml').write_text('<body name="new" damping="0.8"/>\n')
        new_asset = sha(self.new / 'assets/new.xml')
        (self.new / 'asset_bundle.json').write_text(json.dumps({
            'synthetic': True, 'assets': [{'uid': 'mock-box-v2', 'path': 'assets/new.xml',
                'sha256': new_asset, 'version': 'v2'}]}, indent=2) + '\n')
        (self.new / 'semantic_examples.json').write_text('{"cases":[]}\n')
        (self.new / 'task.json').write_text(json.dumps({'task_id': 'mock/pick-lift-v0',
            'asset_bundle': 'asset_bundle.json', 'semantic_examples': 'semantic_examples.json'}, indent=2) + '\n')
        self.new_spec = make_spec('mock-box-v2', new_asset)
        self.new_spec_path = self.new / 'round2.spec.json'
        self.new_spec.save(self.new_spec_path)
        self.new_catalog = self.new / 'catalog.json'
        save_json(self.catalog(NEW_CORE), self.new_catalog)
        self.receipt_path = self.new / 'owner_repair.json'
        self.write_receipt()
        self.continued_path = self.new / 'continued.json'

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def catalog(commit):
        return {'schema_version':'harness-catalog-v0','core_repo':str(ROOT.resolve()),
            'core_commit': commit, 'core_dirty': False,
            'providers': {'mujoco': {'available': True}}}

    def make_archive(self, old_ledger):
        archive_dir = self.base / 'runtime_archive'
        archive_dir.mkdir(exist_ok=True)
        rows = []
        for name, ref in old_ledger['runtime_refs'].items():
            source = Path(ref['path'])
            target = archive_dir / name
            shutil.copyfile(source, target)
            rows.append({'name': name, 'original_path': str(source),
                'archive_path': str(target), 'sha256': sha(target), 'bytes': target.stat().st_size})
        indexed = {}
        def visit(value):
            if isinstance(value, dict):
                if set(value) == {'path', 'sha256'} and value['path'] not in {x['path'] for x in old_ledger['runtime_refs'].values()}:
                    source = Path(value['path'])
                    indexed[str(source)] = {'path': str(source), 'sha256': value['sha256'],
                        'bytes': source.stat().st_size}
                else:
                    for child in value.values(): visit(child)
            elif isinstance(value, list):
                for child in value: visit(child)
        visit(old_ledger)
        path = self.base / 'archive_manifest.json'
        path.unlink(missing_ok=True)
        save_json({'schema_version': 'f00-attempt001-history-archive-v1',
            'ledger_sha256': sha(self.old_ledger_path), 'indexed_files': list(indexed.values()),
            'runtime_snapshot': rows}, path)
        return path

    def write_receipt(self):
        diagnostics=[]
        for label in ('ab_diagnosis_summary', 'builtin_seed0_trace', 'old_mock_seed0_trace'):
            path=self.new / f'{label}.jsonl'
            path.write_text(label + '\n')
            diagnostics.append({'label': label, 'ref': ledger_api.file_ref(path)})
        diff=self.new/'source.patch';diff.write_text('diff --git a/example b/example\n')
        old_bundle=json.loads((self.old/'asset_bundle.json').read_text())
        new_bundle=json.loads((self.new/'asset_bundle.json').read_text())
        old_ref=ledger_api.file_ref(self.old/'catalog.json')
        after={
            'spec_sha256': self.new_spec.spec_sha256(),
            'catalog_sha256': ledger_api.file_ref(self.new_catalog)['sha256'],
            'task_sha256': ledger_api.file_ref(self.new/'task.json')['sha256'],
            'asset_bundle_sha256': ledger_api.file_ref(self.new/'asset_bundle.json')['sha256'],
        }
        receipt={'schema_version':'harness-owner-repair-receipt-v1',
            'legacy_ledger_sha256':sha(self.old_ledger_path),'repair_commit':NEW_CORE,
            'spec_sha256':self.new_spec.spec_sha256(),'reason':'Replace physically non-equivalent synthetic proxy after public A/B diagnosis.',
            'diagnostic_refs':diagnostics,'source_diff_ref':ledger_api.file_ref(diff),
            'input_before':{'spec_sha256':self.old_spec.spec_sha256(),
                'catalog_sha256':old_ref['sha256'],
                'task_sha256':ledger_api.file_ref(self.old/'task.json')['sha256'],
                'asset_bundle_sha256':ledger_api.file_ref(self.old/'asset_bundle.json')['sha256']},
            'input_after':after,
            'asset_change':{'old_uid':old_bundle['assets'][0]['uid'],'new_uid':new_bundle['assets'][0]['uid'],
                'old_sha256':old_bundle['assets'][0]['sha256'],'new_sha256':new_bundle['assets'][0]['sha256']}}
        self.receipt_path.unlink(missing_ok=True)
        save_json(receipt,self.receipt_path)

    def continue_owner_repair(self):
        with patch.object(ledger_api,'core_context',return_value={
            'core_repo':str(ROOT.resolve()),'core_commit':NEW_CORE,'core_dirty':False}):
            return ledger_api.continue_owner_repair(legacy_ledger=self.old_ledger_path,
                history_archive=self.archive_path,repair_receipt=self.receipt_path,
                task=self.new/'task.json',catalog=self.new_catalog,spec=self.new_spec_path,
                provider='mujoco',ledger=self.continued_path)

    def test_continuation_reserves_round_two_and_preserves_failed_round_and_issue(self):
        data=self.continue_owner_repair()
        self.assertEqual(data['schema_version'], 'harness-attempt-ledger-v1')
        self.assertEqual(data['state'], 'running')
        self.assertEqual(len(data['rounds']), 2)
        self.assertEqual(data['rounds'][0]['status'], 'fail')
        self.assertEqual(data['rounds'][0]['context']['core_commit'], OLD_CORE)
        self.assertEqual(data['rounds'][1]['number'], 2)
        self.assertEqual(data['rounds'][1]['context']['core_commit'], NEW_CORE)
        self.assertEqual(data['open_issues'], json.loads(self.old_ledger_path.read_text())['open_issues'])
        self.assertEqual(ledger_api.load(self.continued_path)['state'], 'running')

    def test_cross_commit_report_cannot_finish_reserved_round(self):
        self.continue_owner_repair()
        report=CheckReport(self.new_spec.spec_sha256(), ARTIFACT, OLD_CORE, False,
            'harness_compiler', 'pass', [], {'provider':'mujoco'})
        path=self.new/'cross_commit.json';report.save(path)
        with self.assertRaisesRegex(ValueError, 'Core identity mismatch'):
            ledger_api.finish(ledger=self.continued_path,reports=[path])

    def test_tampered_diagnostic_and_catalog_are_rejected(self):
        self.continue_owner_repair()
        diagnostic=self.new/'builtin_seed0_trace.jsonl'
        diagnostic.write_text('tampered\n')
        with self.assertRaisesRegex(ValueError, 'stale owner-repair diagnostic'):
            ledger_api.load(self.continued_path)
        diagnostic.write_text('builtin_seed0_trace\n')
        self.new_catalog.write_text('{"core_commit":"' + NEW_CORE + '","core_dirty":false,"providers":{}}\n')
        with self.assertRaisesRegex(ValueError, 'stale/missing evidence'):
            ledger_api.load(self.continued_path)

    def test_forged_catalog_commit_is_rejected_against_live_clean_checkout(self):
        with patch.object(ledger_api,'core_context',return_value={
                'core_repo':str(ROOT.resolve()),'core_commit':OLD_CORE,'core_dirty':False}):
            with self.assertRaisesRegex(ValueError, 'catalog does not describe'):
                ledger_api.continue_owner_repair(legacy_ledger=self.old_ledger_path,
                    history_archive=self.archive_path,repair_receipt=self.receipt_path,
                    task=self.new/'task.json',catalog=self.new_catalog,spec=self.new_spec_path,
                    provider='mujoco',ledger=self.continued_path)

    def test_owner_repair_requires_diagnostic_and_exact_before_inputs(self):
        receipt=json.loads(self.receipt_path.read_text())
        receipt['diagnostic_refs']=receipt['diagnostic_refs'][:2]
        self.receipt_path.unlink()
        save_json(receipt,self.receipt_path)
        with self.assertRaisesRegex(ValueError, 'owner-repair diagnostics missing'):
            self.continue_owner_repair()
        self.receipt_path.unlink()
        self.write_receipt()
        receipt=json.loads(self.receipt_path.read_text())
        receipt['input_before']['asset_bundle_sha256']='0'*64
        self.receipt_path.unlink()
        save_json(receipt,self.receipt_path)
        with self.assertRaisesRegex(ValueError, 'before asset_bundle identity mismatch'):
            self.continue_owner_repair()

    def test_dropped_history_or_cleared_issue_is_rejected(self):
        data=self.continue_owner_repair()
        data['rounds'][0]['finding_keys']=[]
        self.continued_path.write_text(json.dumps(data,indent=2)+'\n')
        with self.assertRaisesRegex(ValueError, 'altered historical round'):
            ledger_api.load(self.continued_path)
        self.continued_path.unlink()
        data=self.continue_owner_repair()
        data['open_issues']=[]
        self.continued_path.write_text(json.dumps(data,indent=2)+'\n')
        with self.assertRaisesRegex(ValueError, 'cleared or altered historical open issues'):
            ledger_api.load(self.continued_path)

    def test_historical_context_and_repair_anchor_are_immutable(self):
        data=self.continue_owner_repair()
        data['rounds'][0]['context']['artifact_hash']='d'*64
        self.continued_path.write_text(json.dumps(data,indent=2)+'\n')
        with self.assertRaisesRegex(ValueError, 'changed historical round 1 execution context'):
            ledger_api.load(self.continued_path)
        self.continued_path.unlink()
        data=self.continue_owner_repair()
        data['owner_repair_ref']=ledger_api.file_ref(self.new_spec_path)
        self.continued_path.write_text(json.dumps(data,indent=2)+'\n')
        with self.assertRaisesRegex(ValueError, 'owner-repair continuation anchor'):
            ledger_api.load(self.continued_path)

    def test_attempt_budget_exhaustion_blocks_continuation(self):
        data=json.loads(self.old_ledger_path.read_text())
        one=data['rounds'][0]
        data['rounds']=[{**one,'number':i} for i in range(1,ledger_api.MAX_ROUNDS+1)]
        data['open_issues']=[]
        self.old_ledger_path.write_text(json.dumps(data,indent=2)+'\n')
        self.archive_path=self.make_archive(data)
        self.write_receipt()
        with self.assertRaisesRegex(ValueError, 'attempt budget exhausted'):
            self.continue_owner_repair()

    def test_v1_keeps_ordinary_task_local_spec_revision(self):
        self.continue_owner_repair()
        failed=CheckReport(self.new_spec.spec_sha256(), None, NEW_CORE, False,
            'asset_check', 'fail', [CheckFinding('asset_check', 'spec_invalid', 'task_local',
                'success_config.reach_distance_m', 0.05, 0.06, {'reason':'bounded task-local revision'})],
            {'provider':'mujoco'})
        report_path=self.new/'round2.failure.json';failed.save(report_path)
        data=ledger_api.finish(ledger=self.continued_path,reports=[report_path])
        self.assertEqual(data['state'],'ready')
        revised=self.new_spec.to_dict();revised['success_config']['reach_distance_m']=0.06
        revised_spec=CandidateSpec.from_dict(revised);revised_path=self.new/'round3.spec.json'
        revised_spec.save(revised_path)
        revision={'reason':'Correct one task-local reach setting after its cited finding.',
            'report_sha256':sha(report_path),'finding_index':0}
        revision_path=self.new/'revision.json';save_json(revision,revision_path)
        begun=ledger_api.begin(ledger=self.continued_path,spec=revised_path,revision=revision_path)
        self.assertEqual(begun['state'],'running')
        self.assertEqual(len(begun['rounds']),3)
        self.assertEqual(begun['rounds'][2]['revision']['kind'],'spec_revision')

    def finish_owner_and_fault_findings(self):
        self.continue_owner_repair()
        findings=[
            CheckFinding('asset_check','asset_missing','asset','object_config.asset_sha256',
                'missing','expected',{'case':'new asset issue'}),
            CheckFinding('asset_check','capability_unsupported','core','scene_config.table_top_z',
                'unsupported','supported',{'case':'new core issue'}),
            CheckFinding('asset_check','capability_unsupported','provider','provider.mujoco',
                'unavailable','available',{'case':'new provider issue'}),
            CheckFinding('asset_check','capability_unsupported','harness','candidate.binding',
                'invalid','valid',{'case':'new harness issue'}),
            CheckFinding('asset_check','execution_fault','task_local','execution.close',
                'fault','none',{'case':'new execution fault'}),
        ]
        report=CheckReport(self.new_spec.spec_sha256(),None,NEW_CORE,False,
            'asset_check','fail',findings,{'provider':'mujoco'})
        self.issue_report_path=self.new/'round2.issues.json'
        report.save(self.issue_report_path)
        ledger_api.finish(ledger=self.continued_path,reports=[self.issue_report_path])
        return ledger_api.file_ref(self.issue_report_path)

    def test_finish_appended_owner_and_fault_issues_load_in_report_order(self):
        report_ref=self.finish_owner_and_fault_findings()
        value=ledger_api.load(self.continued_path)
        self.assertEqual(value['state'],'stopped')
        historical=json.loads(self.old_ledger_path.read_text())['open_issues']
        self.assertEqual(value['open_issues'][:len(historical)],historical)
        self.assertEqual(value['open_issues'][len(historical):],[
            {'report':report_ref,'finding_index':i,'status':'open','sent':False}
            for i in range(5)])

    def test_load_rejects_forged_new_issue_and_deleted_historical_issue(self):
        self.finish_owner_and_fault_findings()
        value=json.loads(self.continued_path.read_text())
        value['open_issues'].append({**value['open_issues'][-1],'finding_index':999})
        self.continued_path.write_text(json.dumps(value,indent=2)+'\n')
        with self.assertRaisesRegex(ValueError,'new open issues do not match round findings'):
            ledger_api.load(self.continued_path)

        value=json.loads(self.continued_path.read_text())
        value['open_issues'].pop()
        value['open_issues'].pop(0)
        self.continued_path.write_text(json.dumps(value,indent=2)+'\n')
        with self.assertRaisesRegex(ValueError,'cleared or altered historical open issues'):
            ledger_api.load(self.continued_path)


if __name__ == '__main__':
    unittest.main()
