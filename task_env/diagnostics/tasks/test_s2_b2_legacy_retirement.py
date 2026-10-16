"""Provider-free regression for the bounded S2-B2 retirement slice."""
import ast
import hashlib
import json
import math
from pathlib import Path
import sys

import pytest

from task_env.diagnostics.phase1.integration.route_receipt_contracts import (
    validate_native_step_counts,
    validate_transition_boundaries,
)

ROOT = Path(__file__).resolve().parents[3]
IDENTITY_PATH = ROOT / 'docs/module/task_env/p2_0_s2_b1_source_identity.json'
MANIFEST_PATH = ROOT / 'docs/module/task_env/p2_0_s2_b_deletion_manifest.json'
RETIRED_MODULES = {
    'task_env.tasks.nut_assembly.clearance_candidate_v4',
    'task_env.tasks.nut_assembly.stable_grasp_reference',
}
RETIRED_PATHS = {module.replace('.', '/') + '.py' for module in RETIRED_MODULES}


def test_selected_active_source_fingerprints_and_outcome_mro_are_unchanged():
    identity = json.loads(IDENTITY_PATH.read_text())
    for relative_path, record in identity['source_files'].items():
        # S2-B1's PickCube files are frozen migration inputs; S2-C1 replaces
        # that active closure. Keep the NutAssembly identity comparison exact.
        if relative_path.startswith('task_env/tasks/pick_cube/'):
            continue
        path = ROOT / relative_path
        assert path.is_file(), relative_path
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record['new_source_sha256']
    assert not RETIRED_PATHS.intersection(identity['source_files'])

    from task_env.tasks.nut_assembly.outcome_solution import NutAssemblyOutcomeSolutionV1
    from task_env.tasks.nut_assembly.reference import build_reference
    active = build_reference(provider='mujoco')
    assert active['construction_id'] == 'nutassembly-r5-v5-outcome-reference-construction-v2'
    assert active['solution'].__class__ is NutAssemblyOutcomeSolutionV1
    mro = [f'{item.__module__}.{item.__name__}' for item in NutAssemblyOutcomeSolutionV1.__mro__]
    assert mro[:5] == [
        'task_env.tasks.nut_assembly.outcome_solution.NutAssemblyOutcomeSolutionV1',
        'task_env.tasks.nut_assembly.guarded_authorization_candidate_v2.NutAssemblyGuardedAuthorizationCandidateV2',
        'task_env.tasks.nut_assembly.guarded_authorization_candidate.NutAssemblyGuardedAuthorizationCandidateV1',
        'task_env.tasks.nut_assembly.clearance_candidate_v5.NutAssemblyHandClearanceCandidateV5',
        'task_env.tasks.nut_assembly.clearance_candidate_v3.NutAssemblyHandClearanceCandidateV3',
    ]
    assert not any('clearance_candidate_v4' in item or 'stable_grasp_reference' in item for item in mro)
    assert not (RETIRED_MODULES & set(sys.modules))


def test_no_current_python_entrypoint_imports_the_retired_modules():
    direct_imports = []
    for path in (ROOT / 'task_env').rglob('*.py'):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in RETIRED_MODULES:
                direct_imports.append((str(path.relative_to(ROOT)), node.lineno, node.module))
            elif isinstance(node, ast.Import):
                direct_imports.extend(
                    (str(path.relative_to(ROOT)), node.lineno, alias.name)
                    for alias in node.names if alias.name in RETIRED_MODULES
                )
    assert direct_imports == []


def test_retirement_manifest_records_exact_v1_recovery_identities():
    manifest = json.loads(MANIFEST_PATH.read_text())
    entries = {item['path']: item for item in manifest['files']}
    expected = {
        'task_env/tasks/nut_assembly/clearance_candidate_v4.py': (
            '10067cbdea578c17c9a1659667e8dbb5edd081ab362b2ad16b1fcdd8a53b3f83',
            '6251ac1d861ab41c14379b3fd9af7cd9e82034e3',
        ),
        'task_env/tasks/nut_assembly/stable_grasp_reference.py': (
            'b51c054bb997e294d9e3605a28d86eec1dfc253589f3da1578078a64a6908324',
            'e8cc8880ddf2e5342c74d8ef63a8acd6696f5bb9',
        ),
    }
    for relative_path, (source_hash, release_blob) in expected.items():
        entry = entries[relative_path]
        assert entry['sha256'] == source_hash
        assert entry['v1_0_0_blob'] == release_blob
        assert entry['recovery'] == {'canonical': 'v1.0.0', 'blob': release_blob}


@pytest.mark.parametrize('case', [
    ('pickcube', 'geophys', {'grouped_control_interval_calls': 3,
                             'grouped_native_substeps_requested': 15}, True),
    ('pickcube', 'mujoco', {'native_physics_step_calls': 15,
                             'grouped_control_interval_calls': 0}, True),
    ('nutassembly', 'geophys', {'native_physics_step_calls': 15,
                                 'grouped_control_interval_calls': 0}, True),
    ('nutassembly', 'mujoco', {'native_physics_step_calls': 15,
                                'grouped_control_interval_calls': 0}, True),
    ('pickcube', 'mujoco', {'native_physics_step_calls': 14,
                             'grouped_control_interval_calls': 0}, False),
])
def test_provider_specific_native_step_receipt_contract(case):
    task, provider, counts, valid = case
    if valid:
        assert validate_native_step_counts(task, provider, 3, counts, substeps=5) == 15
    else:
        with pytest.raises(ValueError, match='native-step count mismatch'):
            validate_native_step_counts(task, provider, 3, counts, substeps=5)


def test_t_plus_one_boundary_and_100hz_clock_receipt_contract():
    transitions = [{'index': index} for index in range(2)]
    boundaries = [
        {'control_step': 0, 'simulation_time': 0.0, 'native_step_index': 0},
        {'control_step': 1, 'simulation_time': 0.01, 'native_step_index': 5},
        {'control_step': 2, 'simulation_time': 0.02, 'native_step_index': 10},
    ]
    boundaries[1]['simulation_time'] = math.nextafter(0.01, math.inf)
    assert validate_transition_boundaries(transitions, boundaries, control_dt=0.01, substeps=5) == 2
    with pytest.raises(ValueError, match=r'T transitions and T\+1 boundaries'):
        validate_transition_boundaries(transitions, boundaries[:-1], control_dt=0.01, substeps=5)
    boundaries[2]['native_step_index'] = 9
    with pytest.raises(ValueError, match='native-step boundary mismatch'):
        validate_transition_boundaries(transitions, boundaries, control_dt=0.01, substeps=5)
    boundaries[2]['native_step_index'] = 10
    boundaries[2]['simulation_time'] = float('nan')
    with pytest.raises(ValueError, match='control-clock mismatch'):
        validate_transition_boundaries(transitions, boundaries, control_dt=0.01, substeps=5)
    boundaries[2]['simulation_time'] = 0.020001
    with pytest.raises(ValueError, match='control-clock mismatch'):
        validate_transition_boundaries(transitions, boundaries, control_dt=0.01, substeps=5)


def test_b2_retired_candidates_remain_unimportable_after_pickcube_consolidation():
    from importlib.util import find_spec
    for module in RETIRED_MODULES:
        assert find_spec(module) is None
