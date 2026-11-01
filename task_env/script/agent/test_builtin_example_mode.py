"""Focused contract tests for the versioned built-in PickCube Harness mode."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

AGENT_DIR = Path(__file__).resolve().parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from builtin_example_schema import BuiltinPickCubeExampleV1, ExampleWorkingTreeScopeV1


def _spec(**changes):
    value = {
        'schema_version': 'harness-builtin-pickcube-example-v1',
        'example_id': 'pickcube-harness-example-v1',
        'task_uid': 'pick-cube-p16-reference-v1',
        'provider': 'mujoco', 'backend': 'cpu', 'device': 'cpu',
        'controller_profile': 'r3_continuous_v1', 'seeds': [31, 32, 33],
        'horizon_control_ticks': 1000, 'physics_dt_s': 0.002, 'control_substeps': 5,
    }
    value.update(changes)
    return BuiltinPickCubeExampleV1.from_dict(value)


def test_builtin_example_schema_pins_uid_profile_seed_set_and_timebase():
    spec = _spec()
    assert spec.identity_sha256
    assert spec.seeds == (31, 32, 33)
    for changes in (
        {'task_uid': 'other/task-v1'},
        {'provider': 'mujoco', 'backend': 'cuda', 'device': 'cuda:0'},
        {'controller_profile': 'r1'},
        {'seeds': [31, 32]},
        {'horizon_control_ticks': 1001},
        {'control_substeps': 4},
    ):
        with pytest.raises(ValueError):
            _spec(**changes)


def test_working_tree_scope_requires_exact_sorted_byte_pins():
    scope = ExampleWorkingTreeScopeV1.from_dict({
        'schema_version': 'harness-example-working-tree-scope-v1',
        'expected_untracked': [
            {'path': 'docs/maintenance/a.md', 'sha256': 'a' * 64},
        ],
    })
    assert scope.to_dict()['expected_untracked'][0]['path'] == 'docs/maintenance/a.md'
    with pytest.raises(ValueError):
        ExampleWorkingTreeScopeV1.from_dict({
            'schema_version': 'harness-example-working-tree-scope-v1',
            'expected_untracked': [
                {'path': 'b', 'sha256': 'b' * 64}, {'path': 'a', 'sha256': 'a' * 64},
            ],
        })


def test_compiler_uses_builtin_catalog_but_preserves_candidate_spec():
    import harness_compiler
    from harness_spec_schema import CandidateSpec

    spec = _spec()
    scope = ExampleWorkingTreeScopeV1('harness-example-working-tree-scope-v1', ())
    artifact = type('Artifact', (), {
        'identity_hash': 'f' * 64, 'task_id': 'pick-cube-v1',
        'timebase': type('Timebase', (), {'physics_dt': 0.002, 'control_substeps': 5})(),
    })()
    source = type('Source', (), {
        'scene_source': type('SceneSource', (), {'source_id': 'test-source', 'xml': '<mujoco/>'})(),
    })()
    controller = type('Controller', (), {'identity': 'controller-v1'})()
    solution = type('Solution', (), {'identity': 'solution-v1'})()
    value = {
        'artifact': artifact, 'construction_id': 'pickcube-core-v2',
        'recipe_identity': 'e' * 64, 'source_revision': 'commit',
        'source_sha256': {'task_env/tasks/pick_cube/task.py': '1' * 64},
        'source': source, 'controller': controller, 'solution_identity': solution.identity,
    }
    catalog = {
        'schema_version': 'harness-catalog-v0', 'core_repo': '/tmp/core',
        'core_commit': 'commit', 'core_dirty': False,
        'builtin_examples': {'pickcube-harness-example-v1': {'task_uid': spec.task_uid}},
        'env_uids': [spec.task_uid], 'providers': {'mujoco': {'available': True}},
    }
    with patch.object(harness_compiler, '_example_working_tree_context', return_value={
        'schema_version': scope.schema_version, 'tracked_clean': True,
        'repo_dirty': False, 'expected_untracked': [],
    }), patch('catalog_query.core_context', return_value={'core_repo': '/tmp/core', 'core_commit': 'commit', 'core_dirty': False}), \
         patch.object(subprocess, 'check_output', return_value=''), \
         patch('task_env.tasks.pick_cube.task.build_reference', return_value=value):
        compiled = harness_compiler.compile_builtin_pickcube_example(spec, catalog, working_tree_scope=scope)

    assert compiled.artifact_hash == 'f' * 64
    assert compiled.runtime_source_id == 'test-source'
    with pytest.raises((ValueError, TypeError)):
        CandidateSpec.from_dict(spec.to_dict())


def test_compiler_does_not_claim_isaac_before_exact_core_route_exists():
    import harness_compiler

    spec = _spec(provider='isaacsim', backend='cuda', device='cuda:0')
    scope = ExampleWorkingTreeScopeV1('harness-example-working-tree-scope-v1', ())
    catalog = {
        'schema_version': 'harness-catalog-v0', 'core_repo': '/tmp/core',
        'core_commit': 'commit', 'core_dirty': False,
        'builtin_examples': {'pickcube-harness-example-v1': {'task_uid': spec.task_uid}},
        'env_uids': [spec.task_uid], 'providers': {},
    }
    with patch.object(harness_compiler, '_example_working_tree_context', return_value={
        'schema_version': scope.schema_version, 'tracked_clean': True,
        'repo_dirty': False, 'expected_untracked': [],
    }), patch('catalog_query.core_context', return_value={'core_repo': '/tmp/core', 'core_commit': 'commit', 'core_dirty': False}), \
         patch.object(subprocess, 'check_output', return_value=''):
        with pytest.raises(ValueError, match='not yet admitted'):
            harness_compiler.compile_builtin_pickcube_example(spec, catalog, working_tree_scope=scope)
