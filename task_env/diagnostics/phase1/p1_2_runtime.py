"""Bounded CPU reset/semantic/timebase smoke; no physics qualification claim.

Run providers in separate subprocesses: GeoPhys owns process-global Taichi state.
The parent samples once and persists the exact JSON consumed by both workers.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import traceback
from unittest.mock import patch

from ...artifacts import CanonicalStateView, CapabilityAdmissionError, ExecutionSpec, TaskArtifact
from ...artifacts.execution import RealizedInitialState, ResetSample, canonical_json
from ...runtime.sessions import materialize, provider_manifest
from ...runtime.sessions.api import PROFILE
from ...tasks.pick_cube.candidate import build_candidate
from ...tasks.pick_cube.canonical_semantics import evaluate as evaluate_canonical
from ...tasks.pick_cube.reset import sample_reset
from ...tasks.pick_cube.runtime_source import build_runtime_source

# Frozen before execution. Representation/reset bounds, never physics tolerances.
BOUNDS = {'joint_max_abs': 1e-5, 'position_max_abs_m': 1e-5, 'quaternion_max_abs': 1e-5}
APPROVED = '1fde9dcb235bf7ea4f4d31268864b2507efb7003'
GEOPHYS = 'c665ce5028a12bb4d2afe49f05e015fa9b684a39'
APPROVED_ARTIFACT = '461d2f08fc08685583d4e7a9ff0cf8401a223e6b719c9ecc32e4f32476f3c25e'


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2, allow_nan=False) + '\n')


def execution(provider):
    return ExecutionSpec(provider, PROFILE, 'none', 'cpu', 0, 'strict')


def errors(sample, state):
    joints = max(abs(state.joint_position[k] - v) for k, v in sample.joint_position.items())
    position = max(abs(a-b) for k, p in sample.poses_world.items()
                   for a, b in zip(state.pose_world[k].position, p.position, strict=True))
    quaternion = max(abs(a-b) for k, p in sample.poses_world.items()
                     for a, b in zip(state.pose_world[k].quaternion_wxyz, p.quaternion_wxyz, strict=True))
    return {'joint_max_abs': joints, 'position_max_abs_m': position, 'quaternion_max_abs': quaternion}


def repeat_errors(a, b, sample):
    # Only fields requested by reset, not contact/controller/EE equivalence.
    values = {
        'joint_max_abs': max(abs(a.joint_position[k]-b.joint_position[k]) for k in sample.joint_position),
        'position_max_abs_m': max(abs(x-y) for k in sample.poses_world
                                  for x, y in zip(a.pose_world[k].position, b.pose_world[k].position, strict=True)),
        'quaternion_max_abs': max(abs(x-y) for k in sample.poses_world
                                 for x, y in zip(a.pose_world[k].quaternion_wxyz, b.pose_world[k].quaternion_wxyz, strict=True)),
    }
    return values


def within(values):
    return all(values[k] <= BOUNDS[k] for k in BOUNDS)


def canonical_checks(state, artifact):
    mapping = state.to_mapping()
    roundtrip = CanonicalStateView.from_mapping(json.loads(canonical_json(mapping))).to_mapping() == mapping
    return {
        'strict_roundtrip': roundtrip,
        'semantic_names': set(state.joint_position) == set(artifact.initialization.joint_position)
                          and set(state.pose_world) == {'cube-v1', 'panda-v1/ee'},
        'finite_normalized_wxyz': all(abs(sum(v*v for v in pose.quaternion_wxyz)-1) < 1e-12
                                      for pose in state.pose_world.values()),
        'no_native_ids': set(mapping) == {'schema_version', 'convention', 'control_step', 'simulation_time',
                                         'joint_position', 'joint_velocity', 'pose_world'}
                         and all(type(k) is str and '/' in k for k in state.joint_position)
                         and not any(token in canonical_json(mapping) for token in
                                     ('body_id', 'site_id', 'qpos', 'qvel', 'native_id', 'address', 'solver')),
    }


def worker(provider, input_path, output):
    report = {'provider': provider, 'status': 'partial_with_localized_failure', 'rows': [],
              'first_failing_boundary': None, 'closed': False,
              'clock_source': ('MuJoCo data.time' if provider == 'mujoco' else
                               'GeoPhysRuntimeBoundary completed-scheduler-step clock; no native clock API')}
    session = None
    stage = 'input_decode'
    try:
        request = json.loads(input_path.read_text())
        artifact = TaskArtifact.from_mapping(request['artifact'])
        samples = [ResetSample.from_mapping(value) for value in request['samples']]
        report['input_file_sha256'] = hashlib.sha256(input_path.read_bytes()).hexdigest()
        report['manifest'] = provider_manifest(provider).to_mapping()
        report['source_xml_sha256'] = hashlib.sha256(build_runtime_source(artifact).scene_source.xml.encode()).hexdigest()
        stage = 'materialization'
        session = materialize(artifact, execution(provider), source=build_runtime_source(artifact))
        report['materialized'] = True
        for sample in samples:
            stage = f'reset/{sample.task_seed}'
            before, digest = canonical_json(sample.to_mapping()), sample.identity_hash
            realized = session.reset(sample)
            a = session.snapshot()
            stage = f'repeat_reset/{sample.task_seed}'
            realized_b = session.reset(sample)
            b = session.snapshot()
            stage = f'canonical_semantics/{sample.task_seed}'
            evaluation = evaluate_canonical(b, artifact.semantics)
            stage = f'step/{sample.task_seed}'
            c = session.step()
            measured = errors(sample, a)
            repeated = repeat_errors(a, b, sample)
            row = {
                'seed': sample.task_seed, 'sample_id': sample.sample_id, 'sample_hash': digest,
                'requested_vs_realized': measured, 'repeat_reset_errors': repeated,
                'realized_initial_state': realized.to_mapping(),
                'repeat_realized_initial_state': realized_b.to_mapping(),
                'reset_state_a': a.to_mapping(), 'reset_state_b': b.to_mapping(), 'one_step_state': c.to_mapping(),
                'semantic_evaluation': {'reward': evaluation.reward, 'success': evaluation.success,
                                        'metrics': dict(evaluation.metrics), 'reward_terms': dict(evaluation.reward_terms)},
                'checks': {
                    'requested_reset_within_bound': within(measured),
                    'repeat_reset_within_bound': within(repeated),
                    'reset_time': a.control_step == b.control_step == 0 and a.simulation_time == b.simulation_time == 0.,
                    'one_step_time': c.control_step == 1 and abs(c.simulation_time-artifact.timebase.control_dt) <= math.ulp(artifact.timebase.control_dt),
                    'request_unchanged': canonical_json(sample.to_mapping()) == before and sample.identity_hash == digest,
                    'realized_is_measured': realized.measured_state.to_mapping() == a.to_mapping()
                                           and realized_b.measured_state.to_mapping() == b.to_mapping(),
                    'canonical_semantics_wired': True,
                    'realized_json_yaml_roundtrip': realized_roundtrip(realized) and realized_roundtrip(realized_b),
                    'zero_reset_velocities': all(abs(v) <= 1e-5 for v in b.joint_velocity.values()),
                    **{f'reset_{k}': v for k, v in canonical_checks(b, artifact).items()},
                    **{f'step_{k}': v for k, v in canonical_checks(c, artifact).items()},
                },
            }
            report['rows'].append(row)
        report['status'] = ('ready_for_human_review' if all(all(r['checks'].values()) for r in report['rows'])
                            else 'partial_with_localized_failure')
        for row in report['rows']:
            failures = [name for name, passed in row['checks'].items() if not passed]
            if failures and report['first_failing_boundary'] is None:
                report['first_failing_boundary'] = {'seed': row['seed'], 'checks': failures}
    except Exception as exc:
        report['first_failing_boundary'] = {'stage': stage, 'error': f'{type(exc).__name__}: {exc}'}
        traceback.print_exc()
    finally:
        if session is not None:
            try:
                session.close()
                try:
                    session.snapshot()
                except RuntimeError:
                    report['closed'] = True
                if not report['closed']:
                    raise AssertionError('closed session still readable')
            except Exception as exc:
                report['status'] = 'partial_with_localized_failure'
                report['close_error'] = str(exc)
        write_json(output, report)
    return 0 if report['status'] == 'ready_for_human_review' and report['closed'] else 1


def realized_roundtrip(value):
    import yaml
    mapping = value.to_mapping()
    return (RealizedInitialState.from_mapping(json.loads(canonical_json(mapping))).to_mapping() == mapping
            and RealizedInitialState.from_mapping(yaml.safe_load(yaml.safe_dump(mapping))).to_mapping() == mapping)


def contract_rejection_checks(sample):
    checks = {}
    for name, mutation in (
        ('unknown_field', lambda v: {**v, 'native_id': 7}),
        ('changed_request_hash', lambda v: {**v, 'task_seed': v['task_seed'] + 1}),
        ('nonunit_rotation', lambda v: {**v, 'poses_world': {'cube-v1': {'position': [0., 0., .488], 'quaternion_wxyz': [2., 0., 0., 0.]}}}),
    ):
        try:
            ResetSample.from_mapping(mutation(sample.to_mapping()))
            checks[name] = False
        except (ValueError, TypeError):
            checks[name] = True
    try:
        sample.joint_position['panda-v1/joint1'] = 5.
        checks['immutable_request'] = False
    except TypeError:
        checks['immutable_request'] = True
    return checks


def provenance():
    import yaml
    def git(*args):
        return subprocess.check_output(['git', *args], text=True).strip()
    decision_path = Path('workspace/qualification/phase1/p1_1_contracts/phase_decision.yaml')
    decision = yaml.safe_load(decision_path.read_text())
    gp_tree = git('ls-tree', 'HEAD', 'GeoPhys').split()[2]
    data = {'branch': git('branch', '--show-current'), 'head': git('rev-parse', 'HEAD'),
            'approved_commit': APPROVED, 'geophys_gitlink': gp_tree,
            'geophys_head': git('-C', 'GeoPhys', 'rev-parse', 'HEAD'),
            'geophys_status': git('-C', 'GeoPhys', 'status', '--porcelain'),
            'decision_sha256': hashlib.sha256(decision_path.read_bytes()).hexdigest(),
            'public_main': git('rev-parse', 'refs/remotes/public/main'),
            'public_main_contains_approved': subprocess.run(['git', 'merge-base', '--is-ancestor', APPROVED, 'refs/remotes/public/main']).returncode == 0}
    if (decision.get('decision') != 'approve' or decision.get('judge', {}).get('type') != 'human'
        or decision.get('implementation_commit', {}).get('geochora') != APPROVED
        or decision.get('provider_baseline', {}).get('geophys') != GEOPHYS
        or gp_tree != GEOPHYS or data['geophys_head'] != GEOPHYS or data['geophys_status']
        or subprocess.run(['git', 'merge-base', '--is-ancestor', APPROVED, 'HEAD']).returncode != 0):
        raise ValueError('approved P1.1 provenance mismatch')
    return data


def provider_free_guard():
    code = '''
import importlib.abc, sys
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'geophys', 'mujoco', 'sapien', 'genesis', 'taichi', 'torch', 'scene', 'solvers'}:
            raise AssertionError('provider import: '+fullname)
sys.meta_path.insert(0, Guard())
from task_env.tasks.pick_cube.candidate import build_candidate
from task_env.tasks.pick_cube.reset import sample_reset
from task_env.tasks.pick_cube.runtime_source import build_runtime_source
from task_env.runtime.sessions import materialize
x=build_candidate()
sample_reset(x,31)
build_runtime_source(x)
print('PASS')
'''
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=30)
    return {'passed': result.returncode == 0, 'stdout': result.stdout, 'stderr': result.stderr}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', choices=('geophys', 'mujoco'))
    parser.add_argument('--input', type=Path)
    args = parser.parse_args()
    if args.worker:
        return worker(args.worker, args.input, args.output)
    import yaml
    started = datetime.now(timezone.utc).isoformat()
    timer = time.monotonic()
    try:
        identity = provenance()
    except Exception as exc:
        write_json(args.output, {'status': 'blocked', 'first_failing_boundary': 'provenance', 'error': str(exc)})
        return 1
    root = args.output.parent
    artifacts = root / 'artifacts'
    artifacts.mkdir(parents=True, exist_ok=True)
    artifact = build_candidate()
    if artifact.identity_hash != APPROVED_ARTIFACT:
        raise ValueError('approved Artifact identity changed')
    source = build_runtime_source(artifact)
    (artifacts / 'source.mjcf.xml').write_text(source.scene_source.xml)
    write_json(artifacts / 'source_bindings.json', {
        'source_id': source.scene_source.source_id, 'base_dir': str(source.scene_source.base_dir),
        'artifact_hash': source.task_artifact_hash,
        **{key: dict(getattr(source, key)) for key in ('joints', 'bodies', 'frames', 'free_joints', 'joint_targets')},
        'open_actuators': source.open_actuators,
    })
    samples = [sample_reset(artifact, seed) for seed in (31, 73)]
    payload = {'artifact': artifact.to_mapping(), 'samples': [s.to_mapping() for s in samples]}
    input_path = artifacts / 'shared_request.json'
    write_json(input_path, payload)
    deterministic = all(s.to_mapping() == sample_reset(artifact, s.task_seed).to_mapping() for s in samples)
    roundtrip = all(ResetSample.from_mapping(json.loads(canonical_json(s.to_mapping()))).to_mapping() == s.to_mapping()
                    and ResetSample.from_mapping(yaml.safe_load(yaml.safe_dump(s.to_mapping()))).to_mapping() == s.to_mapping()
                    for s in samples)
    admission = {}
    for provider in ('geophys', 'mujoco'):
        manifest = provider_manifest(provider)
        missing = replace(manifest, capabilities=manifest.capabilities[1:])
        with patch('task_env.runtime.sessions.api._materialize_admitted') as entered:
            try:
                materialize(artifact, execution(provider), source=build_runtime_source(artifact), manifest=missing)
                failed_closed = False
            except CapabilityAdmissionError:
                failed_closed = True
            admission[provider] = {'rejected': failed_closed, 'materialization_calls': entered.call_count,
                                   'passed': failed_closed and entered.call_count == 0,
                                   'removed_capability': manifest.capabilities[0].name}
    report = {'schema_version': 'p1_2-runtime-smoke-v0', 'bounds_frozen': BOUNDS,
              'approved_implementation': APPROVED, 'geophys_baseline': GEOPHYS,
              'artifact_hash': artifact.identity_hash, 'deterministic_sampling': deterministic,
              'provenance': identity, 'started_at': started,
              'contract_rejection_checks': contract_rejection_checks(samples[0]),
              'reset_json_yaml_roundtrip': roundtrip, 'negative_capability_admission': admission,
              'provider_free_guard': provider_free_guard(), 'providers': {},
              'claim': 'bounded reset/canonical/one-step runtime wiring only; no qualification or physics equivalence'}
    for provider in ('geophys', 'mujoco'):
        path = artifacts / f'{provider}_report.json'
        command = [sys.executable, '-m', __name__, '--worker', provider, '--input', str(input_path), '--output', str(path)]
        # __name__ is __main__ when invoked with -m; use the stable reusable module.
        command[2] = 'task_env.diagnostics.phase1.p1_2_runtime'
        (artifacts / f'{provider}_command.json').write_text(json.dumps(command) + '\n')
        with (artifacts / f'{provider}_stdout.log').open('w') as stdout, (artifacts / f'{provider}_stderr.log').open('w') as stderr:
            try:
                worker_env = dict(os.environ)
                worker_env['GEOPHYS_LOG_AGENT_DIR'] = str((artifacts / f'{provider}_logs').resolve())
                worker_env['GEOPHYS_LOG_AGENT_DETAIL'] = 'detail'
                result = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=600, env=worker_env)
                report['providers'][provider] = json.loads(path.read_text()) if path.exists() else {'status': 'partial_with_localized_failure', 'error': 'worker did not write report'}
                report['providers'][provider]['exit_code'] = result.returncode
            except subprocess.TimeoutExpired:
                report['providers'][provider] = {'status': 'partial_with_localized_failure', 'first_failing_boundary': 'worker timeout'}
        print(provider, report['providers'][provider]['status'], flush=True)
    input_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()
    report['same_source_representation'] = all(p.get('source_xml_sha256') == hashlib.sha256(source.scene_source.xml.encode()).hexdigest() for p in report['providers'].values())
    report['same_serialized_input'] = all(p.get('input_file_sha256') == input_hash for p in report['providers'].values())
    passed = all(report['contract_rejection_checks'].values()) and deterministic and roundtrip and report['provider_free_guard']['passed'] and report['same_serialized_input'] and report['same_source_representation']
    passed = passed and all(v['passed'] for v in admission.values()) and all(p['status'] == 'ready_for_human_review' and p['closed'] for p in report['providers'].values())
    report['status'] = 'ready_for_human_review' if passed else 'partial_with_localized_failure'
    report['ended_at'] = datetime.now(timezone.utc).isoformat()
    report['wall_time_s'] = time.monotonic() - timer
    write_json(args.output, report)
    print(report['status'], flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
