"""Simulator-free consistency check: mock upstream sample -> catalog -> spec -> compile.

Uses the checked-in synthetic upstream delivery under ``examples/harness/mock_upstream``.
No physics is stepped; the test only proves that the current Core still exposes
what the Harness construction path needs (registries, provider manifest,
PickCube construction entry and Robot source composer). A Core change that
breaks candidate construction fails here instead of in a 20-seed run.

Catalog provenance is pinned to a clean context for the duration of the test,
as the other Harness unit tests do: the CLIs still refuse a dirty Core, but this
test is about construction and must also run in a working checkout.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
CORE = HERE.parents[2]
UPSTREAM = CORE / 'examples/harness/mock_upstream'
sys.path.insert(0, str(HERE))

import catalog_query  # noqa: E402
from asset_check import check_assets  # noqa: E402
from catalog_query import build_catalog  # noqa: E402
from harness_compiler import MJCF_CONTROLLER_PROFILE, compile_candidate  # noqa: E402
from harness_spec_schema import CandidateSpec  # noqa: E402
from semantic_check import check_semantics  # noqa: E402


def spec_from_upstream(catalog, task):
    """Fill the catalog's pick-lift-v0 template from the upstream task (same steps as the Skill)."""
    data = copy.deepcopy(catalog['template_details']['pick-lift-v0']['spec_template'])
    data['task_id'] = task['task_id']
    data['scene_config'] = task['scene']
    data['object_config'].update(object_uid=task['requested_asset_uid'], asset_sha256=task['asset_sha256'],
                                 initial_pos_xy=task['initial_pos_xy'], reset_half_extent_m=0.035)
    data['success_config']['lift_height_m'] = task['goal']['height_m']
    return CandidateSpec.from_dict(data)


class MockUpstreamConsistencyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        real = catalog_query.core_context(CORE)
        patcher = patch.object(catalog_query, 'core_context', return_value={**real, 'core_dirty': False})
        patcher.start()
        cls.addClassCleanup(patcher.stop)
        cls.task = json.loads((UPSTREAM / 'task.json').read_text(encoding='utf-8'))
        cls.catalog = build_catalog(CORE, asset_bundle=UPSTREAM / cls.task['asset_bundle'], providers=('mujoco',))
        cls.spec = spec_from_upstream(cls.catalog, cls.task)

    def test_catalog_exposes_template_and_upstream_asset(self):
        self.assertIn('pick-lift-v0', self.catalog['template_details'])
        self.assertIn(self.task['requested_asset_uid'], self.catalog['external_assets'])
        self.assertTrue(self.catalog['providers']['mujoco']['manifest_available'])

    def test_asset_and_semantic_checks_pass(self):
        self.assertEqual(check_assets(self.spec, self.catalog).status, 'pass')
        semantic = check_semantics(self.spec, self.catalog, UPSTREAM / self.task['semantic_examples'])
        self.assertEqual(semantic.status, 'pass', semantic.findings)

    def test_compile_is_deterministic_and_bound_to_spec(self):
        first = compile_candidate(self.spec, self.catalog, provider='mujoco')
        second = compile_candidate(self.spec, self.catalog, provider='mujoco')
        self.assertEqual(first.spec_sha256, self.spec.spec_sha256())
        self.assertEqual(first.artifact_hash, second.artifact_hash)
        self.assertEqual(first.source_xml_sha256, second.source_xml_sha256)
        self.assertEqual(first.route['controller_profile'], MJCF_CONTROLLER_PROFILE)
        self.assertEqual(first.artifact_hash, first.artifact.identity_hash)
        self.assertIn(first.spec_sha256, json.dumps(first.artifact.to_mapping(), default=str))

    def test_tampered_upstream_asset_is_reported_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            copy_dir = Path(directory) / 'mock_upstream'
            shutil.copytree(UPSTREAM, copy_dir)
            catalog = build_catalog(CORE, asset_bundle=copy_dir / self.task['asset_bundle'], providers=('mujoco',))
            asset = catalog['external_assets'][self.task['requested_asset_uid']]
            Path(asset['path']).write_text('<body/>', encoding='utf-8')
            findings = check_assets(self.spec, catalog).findings
            self.assertEqual([finding.category for finding in findings][:1], ['asset_missing'])


if __name__ == '__main__':
    unittest.main()
