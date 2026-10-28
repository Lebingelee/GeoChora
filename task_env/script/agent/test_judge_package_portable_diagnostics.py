"""Real pending-package verify regressions for portable diagnostic bindings.

The immutable F00 attempt002 pending package is used as a valid non-native
fixture. Each test hard-links that package into a fresh temporary directory and
replaces only its copied index/history files; the protected package is read-only.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import judge_package


ROOT = Path(__file__).resolve().parents[3]
SOURCE_PACKAGE = ROOT / 'workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f00_002/stage1_pending_candidate'
CORE_COMMIT = '0d75d7646d45f96cc22c567aa61e070dbab5dd94'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _link_or_copy(source, destination):
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)
    return destination


class PortableDiagnosticVerifyTests(unittest.TestCase):
    def setUp(self):
        if not SOURCE_PACKAGE.is_dir():
            self.skipTest('requires the immutable F00 attempt002 pending-package fixture')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.package = Path(self.temp.name) / 'pending'
        shutil.copytree(SOURCE_PACKAGE, self.package, copy_function=_link_or_copy)
        self.package_file_count = len(json.loads(
            (self.package / 'validation/evidence.json').read_text())['files'])
        self._append_diagnostic()

    @staticmethod
    def _write_json(path, value):
        path = Path(path)
        path.unlink(missing_ok=True)
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')

    def _append_diagnostic(self):
        history_path = self.package / 'validation/history/construction_log.json'
        history = json.loads(history_path.read_text())
        round_ = history['rounds'][-1]
        revision = round_.setdefault('revision', {})
        revision.setdefault('diagnostics', []).append({
            'report': {
                'path': 'validation/current/feasibility.json',
                'sha256': sha(self.package / 'validation/current/feasibility.json'),
            },
            'spec': {
                'path': 'candidate.spec.json',
                'sha256': sha(self.package / 'candidate.spec.json'),
            },
        })
        self._write_json(history_path, history)
        context = round_.get('context') or {'core_commit': history['core_commit']}
        self._write_json(self.package / 'validation/history/diagnostics.json', [{
            'report': {
                'path': 'validation/current/feasibility.json',
                'sha256': sha(self.package / 'validation/current/feasibility.json'),
            },
            'spec': {
                'path': 'candidate.spec.json',
                'sha256': sha(self.package / 'candidate.spec.json'),
            },
            'core_commit': context['core_commit'],
        }])
        self._refresh_package_indexes()

    def _refresh_package_indexes(self):
        index_path = self.package / 'validation/evidence.json'
        index = json.loads(index_path.read_text())
        by_path = {item['path']: item for item in index['files']}
        for relative in (
            'validation/history/construction_log.json',
            'validation/history/diagnostics.json',
        ):
            path = self.package / relative
            by_path[relative] = {
                'path': relative,
                'sha256': sha(path),
                'bytes': path.stat().st_size,
            }
        index['files'] = [by_path[key] for key in sorted(by_path)]
        self._write_json(index_path, index)

        decision_path = self.package / 'judge_decision.yaml'
        decision = yaml.safe_load(decision_path.read_text())
        decision['basis']['evidence_manifest_sha256'] = sha(index_path)
        decision_path.unlink()
        decision_path.write_text(yaml.safe_dump(decision, sort_keys=False))

    def _mutate_diagnostic(self, mutate):
        path = self.package / 'validation/history/diagnostics.json'
        rows = json.loads(path.read_text())
        mutate(rows[0])
        self._write_json(path, rows)
        self._refresh_package_indexes()

    def _verify(self):
        # Substitute only the checkout identity boundary; execute the complete
        # production verify function and all report/H5/index checks.
        with patch.object(judge_package, 'core_context', return_value={
            'core_repo': str(ROOT), 'core_commit': CORE_COMMIT, 'core_dirty': False,
        }):
            return judge_package.verify(self.package, core_repo=ROOT)

    def test_real_verify_accepts_nonempty_portable_diagnostic(self):
        result = self._verify()
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['decision'], 'pending')
        self.assertEqual(result['files_verified'], self.package_file_count)

    def test_real_verify_rejects_diagnostic_hash_mismatch(self):
        self._mutate_diagnostic(lambda row: row['report'].update(sha256='0' * 64))
        with self.assertRaisesRegex(ValueError, 'portable diagnostic evidence ref mismatch'):
            self._verify()

    def test_real_verify_rejects_wrong_diagnostic_core(self):
        self._mutate_diagnostic(lambda row: row.update(core_commit='f' * 40))
        with self.assertRaisesRegex(ValueError, 'diagnostic Core identity'):
            self._verify()

    def test_real_verify_rejects_wrongly_typed_diagnostic_core(self):
        self._mutate_diagnostic(lambda row: row.update(core_commit={'commit': CORE_COMMIT}))
        with self.assertRaisesRegex(ValueError, 'diagnostic Core commit'):
            self._verify()


if __name__ == '__main__':
    unittest.main()
