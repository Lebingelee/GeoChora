"""Reusable S0/S1 detector for P1.1, with machine-readable provenance.

No simulator is constructed. Provider manifests are synthetic fixtures only.
Run from the repository root with the configured TaskEnv Python environment.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

from ...artifacts import (
    ActionIntent, CanonicalStateView, CapabilityClaim, CapabilityAdmissionError, ExecutionSpec,
    PoseWorld, ProviderCapabilityManifest, RequiredCapabilitySet, TaskArtifact, Timebase,
    admit_capabilities,
)
from ...tasks.pick_cube.candidate import build_candidate
from ...tasks.pick_cube.canonical_semantics import CUBE, EEF, FINGERS, evaluate

FORBIDDEN = {'geophys', 'mujoco', 'sapien', 'genesis', 'torch', 'taichi'}
ROOT = Path(__file__).resolve().parents[3]


def _git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()


def _assert(condition, message='invariant failed'):
    if not condition:
        raise AssertionError(message)


def _reject(fn, error=(TypeError, ValueError), contains=None):
    try:
        fn()
    except error as exc:
        if contains is not None:
            _assert(contains in str(exc), f'wrong rejection: {exc}')
    else:
        raise AssertionError('invalid input accepted')


def _fixture(lift=.0, distance=.02, opening=.04):
    from ...tasks.pick_cube.assets import TABLE_TOP_Z, CUBE_HALF_SIZE
    z = TABLE_TOP_Z + CUBE_HALF_SIZE + lift
    return CanonicalStateView(
        'canonical-state-v0', 'SI_right_handed_z_up_wxyz', 1, .002,
        {n: opening / 2 for n in FINGERS}, {n: 0. for n in FINGERS},
        {CUBE: PoseWorld((.5, 0., z), (1., 0., 0., 0.)),
         EEF: PoseWorld((.5 + distance, 0., z), (1., 0., 0., 0.))},
    )


def _provider_free(module):
    # A fresh subprocess verifies both loaded modules and attempted imports.
    code = f'''
import importlib.abc, json, sys
forbidden = {sorted(FORBIDDEN)!r}
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in forbidden:
            raise AssertionError('attempted provider import: ' + fullname)
sys.meta_path.insert(0, Guard())
import {module}
if {module!r}.endswith('candidate'):
    from task_env.tasks.pick_cube.candidate import build_candidate
    from task_env.artifacts import TaskArtifact
    c = build_candidate()
    assert TaskArtifact.from_mapping(c.to_mapping()).identity_hash == c.identity_hash
loaded = sorted(n for n in sys.modules if n.split('.')[0] in forbidden)
assert not loaded, loaded
print(json.dumps({{'loaded_forbidden': loaded}}))
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, text=True,
                            capture_output=True, timeout=30)
    _assert(result.returncode == 0, result.stderr)
    return json.loads(result.stdout)


def _legacy_compatibility():
    """Independent authoritative evaluator on synthetic arrays, no runtime."""
    import numpy as np
    from ...tasks.pick_cube.task import PickCubeTaskDefinition, _LIFT_HEIGHT
    _assert(_LIFT_HEIGHT == .10)
    refs = SimpleNamespace(
        agents={'panda-v1': SimpleNamespace(eef_site_id=0, gripper_qpos_ids=np.array([0, 1]))},
        objects={'cube-v1': SimpleNamespace(body_ids=np.array([0]))},
    )
    legacy = PickCubeTaskDefinition(refs)
    count = 0
    # Boundary values remain unchanged; grasp-open successful fixtures protect
    # success from accidentally acquiring a grasp gate.
    for lift in (-.01, 0., .099, .10, .100001, .12):
        for distance in (0., .089, .09, .091, .3):
            for opening in (.02, .045, .046, .08):
                state = _fixture(lift, distance, opening)
                snapshot = SimpleNamespace(
                    qpos=np.asarray([state.joint_position[n] for n in FINGERS]),
                    body_xpos=np.asarray([state.pose_world[CUBE].position]),
                    site_xpos=np.asarray([state.pose_world[EEF].position]),
                )
                expected, actual = legacy.reset(snapshot), evaluate(state)
                _assert(actual.success == expected.success and actual.failure == expected.failure)
                _assert(actual.metrics.keys() == expected.metrics.keys())
                for mapping in ('metrics', 'reward_terms'):
                    for key, value in getattr(expected, mapping).items():
                        observed = getattr(actual, mapping)[key]
                        if isinstance(value, bool):
                            _assert(observed is value, key)
                        else:
                            # Fixed stdlib-vs-NumPy expression representation bound.
                            _assert(math.isclose(observed, value, rel_tol=0., abs_tol=1e-14), key)
                _assert(math.isclose(actual.reward, expected.reward, rel_tol=0., abs_tol=1e-14))
                count += 1
    return {'synthetic_fixtures': count, 'success_threshold_m': _LIFT_HEIGHT,
            'float_expression_abs_tolerance': 1e-14}


def run():
    started = datetime.now(timezone.utc).isoformat()
    timer = time.monotonic()
    checks = []
    def check(name, category, fn):
        try:
            details = fn()
            checks.append({'name': name, 'result': 'pass', 'failure_category': None, 'details': details})
        except Exception as exc:
            checks.append({'name': name, 'result': 'fail', 'failure_category': category,
                           'error': f'{type(exc).__name__}: {exc}'})
    candidate = build_candidate()
    mapping = candidate.to_mapping()
    manifest = ProviderCapabilityManifest(
        'provider-capability-v0', 'synthetic', 'fixture-v0', 'fixture-v0',
        'cpu', 'fixture', 'none', 'strict',
        tuple(CapabilityClaim(n, 'tested', 'synthetic-fixture-only') for n in candidate.required_capabilities.names),
        (), 'synthetic-fixture-only',
    )
    check('valid_artifact_load', 'schema', lambda: _assert(TaskArtifact.from_mapping(mapping) == candidate))
    check('mapping_roundtrip', 'schema', lambda: _assert(TaskArtifact.from_mapping(mapping).to_mapping() == mapping))
    check('json_roundtrip', 'schema', lambda: _assert(TaskArtifact.from_mapping(json.loads(json.dumps(mapping))) == candidate))
    def yaml_roundtrip():
        import yaml
        _assert(TaskArtifact.from_mapping(yaml.safe_load(yaml.safe_dump(mapping))) == candidate)
    check('yaml_roundtrip', 'schema', yaml_roundtrip)
    def action_references(mode, references, valid):
        import yaml
        from ...environment import ActionModeSpec
        # Build valid Core schemas through its factory, then replace only the
        # reference: the authoritative validator independently judges each case.
        from ...environment.config import RobotControllerConfig
        core = ActionModeSpec.from_controller_config(RobotControllerConfig(
            kind=mode, reference=None if mode == 'absolute_joint' else 'world'))
        rotation = 'none' if mode == 'absolute_joint' else 'quaternion_wxyz'
        for reference in references:
            construct = lambda: ActionIntent(mode, reference, rotation, 'arm_joint_position_and_gripper')
            if valid:
                _assert(replace(core, reference=reference).reference == reference)
                intent = construct()
                _assert(ActionIntent.from_mapping(json.loads(json.dumps(intent.to_mapping()))) == intent)
                _assert(ActionIntent.from_mapping(yaml.safe_load(yaml.safe_dump(intent.to_mapping()))) == intent)
            else:
                _reject(construct)
                _reject(lambda: replace(core, reference=reference))
    check('absolute_joint_none_reference_pass', 'action', lambda: action_references('absolute_joint', (None,), True))
    check('absolute_joint_world_base_reference_rejected', 'action', lambda: action_references('absolute_joint', ('world', 'base'), False))
    check('absolute_pose_world_base_reference_pass', 'action', lambda: action_references('absolute_pose', ('world', 'base'), True))
    check('absolute_pose_ee_none_reference_rejected', 'action', lambda: action_references('absolute_pose', ('ee', None), False))
    check('delta_pose_world_base_ee_reference_pass', 'action', lambda: action_references('delta_pose', ('world', 'base', 'ee'), True))
    check('delta_pose_none_reference_rejected', 'action', lambda: action_references('delta_pose', (None,), False))
    check('nullable_reference_wrong_type_rejected', 'schema', lambda: _reject(
        lambda: ActionIntent('absolute_pose', 7, 'quaternion_wxyz', 'arm_joint_position_and_gripper')))
    check('unknown_top_level_rejected', 'schema', lambda: _reject(lambda: TaskArtifact.from_mapping({**mapping, 'typo': 1})))
    def nested_rejections():
        paths = [('world',), ('world', 'entities', 0), ('world', 'action'), ('initialization',),
                 ('initialization', 'randomization', 0), ('initialization', 'poses_world', CUBE),
                 ('semantics',), ('timebase',), ('required_capabilities',)]
        for path in paths:
            mutated = deepcopy(mapping)
            node = mutated
            for part in path:
                node = node[part]
            node['typo'] = True
            _reject(lambda: TaskArtifact.from_mapping(mutated))
        for section in ('world', 'initialization', 'semantics'):
            mutated = deepcopy(mapping)
            mutated[section]['schema_version'] = 'future-schema'
            _reject(lambda: TaskArtifact.from_mapping(mutated))
        _reject(lambda: TaskArtifact.from_mapping({**mapping, 'schema_version': 'task-artifact-v999'}))
        _reject(lambda: TaskArtifact.from_mapping({**mapping, 'world': None}))
    check('invalid_nested_and_schema_rejected', 'schema', nested_rejections)
    def timebase_rejections():
        for values in ((0., 1, 0.), (-.002, 1, -.002), (.002, 0, 0.),
                       (.002, True, .002), (.002, 1, .02), (float('nan'), 1, .002),
                       (.002, 1, float('inf')), (.002, 1.0, .002)):
            _reject(lambda: Timebase(*values))
        _reject(lambda: replace(candidate.timebase, action_hold='linear'))
    check('invalid_timebase_rejected', 'timebase', timebase_rejections)
    check('capability_positive_admission', 'capability', lambda: admit_capabilities(candidate.required_capabilities, manifest))
    check('missing_capability_fail_closed', 'capability', lambda: _reject(
        lambda: admit_capabilities(candidate.required_capabilities, replace(manifest, capabilities=manifest.capabilities[1:])),
        CapabilityAdmissionError, manifest.capabilities[0].name))
    def status_rejections():
        for status in ('planned', 'unknown', 'unsupported'):
            claims = (replace(manifest.capabilities[0], status=status), *manifest.capabilities[1:])
            _reject(lambda: admit_capabilities(candidate.required_capabilities, replace(manifest, capabilities=claims)), CapabilityAdmissionError)
        _reject(lambda: RequiredCapabilitySet(('imaginary_capability',)))
        _reject(lambda: replace(manifest, known_unsupported=(manifest.capabilities[0].name,)))
        _reject(lambda: replace(manifest, capabilities=(*manifest.capabilities, manifest.capabilities[0])))
    check('unknown_status_and_contradictory_capability_rejected', 'capability', status_rejections)
    def execution_separation():
        a = ExecutionSpec('synthetic', 'fixture', 'none', 'cpu', 1007, 'strict')
        b = ExecutionSpec('other', 'other_profile', 'other_renderer', 'cuda', 12, 'best_effort')
        for execution in (a, b):
            _assert(ExecutionSpec.from_mapping(execution.to_mapping()) == execution)
            _reject(lambda: TaskArtifact.from_mapping({**mapping, 'execution': execution.to_mapping()}))
        admit_capabilities(candidate.required_capabilities, manifest, a)
        _reject(lambda: admit_capabilities(candidate.required_capabilities, manifest, b), CapabilityAdmissionError)
        _assert(TaskArtifact.from_mapping(mapping).identity_hash == candidate.identity_hash)
        _assert(replace(candidate, artifact_version='changed').identity_hash != candidate.identity_hash)
    check('execution_excluded_from_identity', 'identity', execution_separation)
    def state_validation():
        state = _fixture()
        _assert(CanonicalStateView.from_mapping(state.to_mapping()) == state)
        for changes in ({'control_step': True}, {'simulation_time': -1.}, {'convention': 'xyzw'},
                        {'joint_position': {0: .0}}, {'joint_position': {'123': .0}},
                        {'joint_position': {'bad name': .0}}, {'joint_position': {FINGERS[0]: float('inf')}},
                        {'pose_world': {CUBE: {'position': [0., 0.], 'quaternion_wxyz': [1., 0., 0., 0.]}}}):
            _reject(lambda: replace(state, **changes))
        _reject(lambda: PoseWorld((0., 0., 0.), (0., 0., 0., 0.)))
        _reject(lambda: evaluate(replace(state, pose_world={})), contains='missing semantic state')
        _reject(lambda: evaluate(object()))
    check('canonical_state_name_finite_convention_validation', 'canonical_state', state_validation)
    def quaternion_float32_representation():
        import numpy as np
        q = np.asarray((.35, -.2, .3, .8), dtype=np.float32)
        q /= np.linalg.norm(q)
        values = tuple(float(v) for v in q)
        norm_error = abs(sum(v * v for v in values) - 1.)
        _assert(norm_error > 1e-12, 'fixture must exercise float32 rounding')
        pose = PoseWorld((0., 0., 0.), values)
        state = replace(_fixture(), pose_world={CUBE: pose, EEF: pose})
        _assert(CanonicalStateView.from_mapping(state.to_mapping()) == state)
        _assert(PoseWorld.from_mapping(json.loads(json.dumps(pose.to_mapping()))) == pose)
        return {'normalization_dtype': 'float32', 'norm_squared_error': norm_error}
    check('float32_normalized_quaternion_pass', 'representation', quaternion_float32_representation)
    def nonunit_quaternions():
        for q in ((0., 0., 0., 0.), (2., 0., 0., 0.), (1.001, 0., 0., 0.),
                  (float('nan'), 0., 0., 0.)):
            _reject(lambda: PoseWorld((0., 0., 0.), q))
    check('nonunit_quaternion_fail_closed', 'representation', nonunit_quaternions)
    check('provider_free_contract_import', 'import_boundary', lambda: _provider_free('task_env.artifacts'))
    check('provider_free_candidate_import_load', 'import_boundary', lambda: _provider_free('task_env.tasks.pick_cube.candidate'))
    check('fresh_task_env_import', 'import_boundary', lambda: _provider_free('task_env'))
    check('pick_cube_non_success_fixture', 'semantics', lambda: _assert(not evaluate(_fixture(.099)).success))
    check('pick_cube_success_fixture_without_grasp', 'semantics', lambda: _assert(evaluate(_fixture(.12, .3, .08)).success and not evaluate(_fixture(.12, .3, .08)).metrics['grasped_cube']))
    check('authoritative_pick_cube_semantic_compatibility', 'semantics', _legacy_compatibility)
    def reset_default_facts():
        from ...tasks.pick_cube.task import PickCubeEnv, PickCubeResetSampler
        from ...environment.configuration import load_yaml_mapping, overlay_public_env_config
        resolved = overlay_public_env_config(PickCubeEnv.default_config(), load_yaml_mapping(PickCubeEnv.default_config_path()))
        _assert(candidate.timebase == Timebase(resolved.runtime.physics_dt, resolved.runtime.control_substeps,
                                               resolved.runtime.physics_dt * resolved.runtime.control_substeps))
        _assert(resolved.robot.controller.kind == candidate.world.action.mode)
        _assert(resolved.observation.include_privileged_state)
        _assert(PickCubeResetSampler.half_extent_m == .10)
        for d in candidate.initialization.randomization:
            _assert(d.training_bounds == d.feasibility_bounds == d.evaluation_bounds == d.hard_bounds)
    check('reset_and_resolved_default_facts', 'candidate', reset_default_facts)
    def canonical_panda_initialization():
        from ...robots.panda import PandaAgent
        expected = {f'panda-v1/{name}': value for name, value in PandaAgent().initial_state_spec().joint_positions}
        _assert(len(expected) == 9)
        _assert(dict(candidate.initialization.joint_position) == expected)
        _assert(set(expected) == candidate.world.joint_names)
        _assert(candidate.initialization.inherited_state_policy ==
                'zero_named_joint_and_entity_velocities_arm_targets_at_initial_joints_gripper_open')
        # Token scan, not substring scan: e.g. 'actuation' is legitimate intent.
        import re
        tokens = set(re.findall(r'[A-Za-z]+', json.dumps(candidate.initialization.to_mapping())))
        _assert(not tokens & {'qpos', 'qvel', 'qacc', 'ctrl', 'act'})
        return {'named_joint_count': len(expected), 'joint_positions': expected,
                'initial_velocity_policy': 'zero_named_joint_and_entity_velocities'}
    check('canonical_panda_initialization', 'initialization', canonical_panda_initialization)
    check('loaded_module_boundary', 'import_boundary', lambda: _assert(not FORBIDDEN & {n.split('.')[0] for n in sys.modules}))
    return {
        'schema': 'geochora.p1_1_contract_smoke.v1',
        'result': 'pass' if all(c['result'] == 'pass' for c in checks) else 'fail',
        'checks': checks, 'failure_category': sorted({c['failure_category'] for c in checks if c['failure_category']}),
        'repository_commit': _git('rev-parse', 'HEAD'), 'branch': _git('branch', '--show-current'),
        'changed_tree': _git('status', '--short'), 'candidate_identity': candidate.identity_hash,
        'artifact_id': candidate.artifact_id, 'artifact_version': candidate.artifact_version,
        'provider': 'none; synthetic manifests only', 'backend': 'none',
        'level': 'S0/S1', 'qualification': False, 'python': sys.executable,
        'start_time': started, 'end_time': datetime.now(timezone.utc).isoformat(),
        'wall_time_s': time.monotonic() - timer,
        'command': [sys.executable, '-m', 'task_env.diagnostics.phase1.p1_1_contracts', *sys.argv[1:]],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run()
    except Exception as exc:
        report = {'result': 'error', 'checks': [], 'failure_category': 'diagnostic_setup',
                  'error': f'{type(exc).__name__}: {exc}', 'repository_commit': _git('rev-parse', 'HEAD')}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'result': report['result'], 'checks': len(report['checks']), 'output': str(args.output)}))
    return 0 if report['result'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
