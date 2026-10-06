"""R4 locked production readiness smoke; never final P1.5 qualification."""
import argparse, hashlib, json, os, subprocess, sys, traceback
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import yaml
from .control.spec import context
from .control.worker import observation
from .p1_2_runtime import execution, write_json
from ...artifacts.execution import ResetSample
from ...controllers.canonical import ProductionCanonicalPandaController, RequestedAction
from ...planners.completion import ExpertExecutionInfo
from ...tasks.pick_cube.readiness_solution import PickCubeReadinessConfig, PickCubeReadinessSolution
from ...runtime.sessions.control import materialize_control, ControlBinding


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inputs():
    artifact, source, _, _ = context()
    cfg = PickCubeReadinessConfig.from_source(artifact, source)
    expert = PickCubeReadinessSolution(config=cfg)
    r2 = Path('workspace/qualification/phase1/p1_5_expert/recovery/r2/control_oracle_r2.yaml')
    old = yaml.safe_load(r2.read_text())
    paths = ['task_env/tasks/pick_cube/solution.py', 'task_env/tasks/pick_cube/readiness_solution.py',
        'task_env/controllers/canonical/production.py', 'task_env/controllers/canonical/readiness.py',
        'task_env/planners/completion.py', __file__]
    return {'schema': 'p1_5-r4-production-readiness-smoke-v1', 'expert_identity': expert.identity,
        'expert_config_identity': cfg.identity, 'config': asdict(cfg),
        'controller_identity': ProductionCanonicalPandaController.from_source(artifact, source).identity,
        'artifact_hash': artifact.identity_hash, 'source_sha256': sha_bytes(source.scene_source.xml.encode()),
        'samples': old['samples'], 'r2_oracle_sha256': sha(r2),
        'r1_oracle_sha256': sha('workspace/qualification/phase1/p1_5_expert/recovery_r1/control_oracle_r1.yaml'),
        'timebase': artifact.timebase.to_mapping(), 'resolved_action': asdict(source.config.action),
        'resolved_gripper': asdict(source.config.robot.gripper), 'global_safety_cap': cfg.global_safety_cap,
        'task_success': 'cube_lift>=0.10m', 'collection_endpoint': 'cube_lift>=0.105m',
        'source_hashes': {str(Path(p).relative_to(Path.cwd())) if Path(p).is_absolute() else p: sha(p) for p in paths},
        'claim': 'production_readiness_smoke; not P1.5 C2 qualified'}


def sha_bytes(value): return hashlib.sha256(value).hexdigest()


def verify(path):
    lock = json.loads((path.parent / 'readiness_oracle_lock.json').read_text())
    spec = yaml.safe_load(path.read_text())
    if sha(path) != lock['sha256'] or spec != json.loads(json.dumps(inputs())):
        raise ValueError('locked R4 inputs changed')
    return spec, lock


def execution_info(controller, state, feedback):
    return ExpertExecutionInfo('expert-execution-info-v1', state.control_step,
        state.simulation_time, controller.readiness(state, feedback))


def worker(args):
    spec, lock = verify(args.oracle)
    artifact, source, _, _ = context()
    sample = ResetSample.from_mapping(next(s for s in spec['samples'] if s['task_seed'] == args.seed))
    original = sample.to_mapping()
    dest = args.output.parent
    result = {'provider': args.provider, 'seed': args.seed, 'evaluation': 'production_readiness_smoke',
        'qualification_claim': False, 'started_at': datetime.now(timezone.utc).isoformat(),
        'oracle_sha256': lock['sha256'], 'sample_hash': sample.identity_hash, 'pass': False}
    session = None
    trace, native_rows = [], []
    try:
        session = materialize_control(artifact, execution(args.provider), source=source,
            binding=ControlBinding('panda-v1/gripper', source.config.action.gripper_opening_range_m))
        session.reset(sample)
        state = session.snapshot()
        feedback = session.control_feedback(state)
        controller = ProductionCanonicalPandaController.from_source(artifact, source)
        controller.reset(state, feedback)
        cfg = PickCubeReadinessConfig.from_source(artifact, source)
        expert = PickCubeReadinessSolution(config=cfg)
        obs, info, _ = observation(state, artifact)
        metadata = {'action_schema': {'controller_kind': 'absolute_pose', 'reference': 'world',
            'rotation_representation': 'quaternion_wxyz', 'dimension': 8}}
        expert.reset(obs, info, metadata, execution_info=execution_info(controller, state, feedback))
        max_lift = float(info['task_metrics']['cube_lift'])
        while not expert.done and not expert.failed:
            public = expert.act()
            request = RequestedAction('absolute_pose', 'world', 'quaternion_wxyz', tuple(map(float, public.action)))
            canonical, target = controller.compute(state, feedback, request)
            applied = session.apply_control(target)
            before = state
            state = session.step()
            if args.provider == 'mujoco':
                # Diagnostic-private native readback, never passed to expert/controller.
                data = session._data
                raw = {'time': float(data.time), 'qpos': data.qpos.tolist(), 'qvel': data.qvel.tolist(),
                    'warning_counts': np.array(data.warning.number).tolist()}
                native_rows.append(raw)
                if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all() or any(raw['warning_counts']):
                    raise ValueError('provider_instability: nonfinite native state or native warning')
            if state.simulation_time <= before.simulation_time:
                raise ValueError('provider_instability: native time not monotonic')
            feedback = session.control_feedback(state)
            ei = execution_info(controller, state, feedback)
            obs, info, _ = observation(state, artifact)
            expert.observe(obs, 0., False, False, info, execution_info=ei)
            max_lift = max(max_lift, float(info['task_metrics']['cube_lift']))
            trace.append({'control_step': state.control_step, 'simulation_time': state.simulation_time,
                'expert_stage': public.stage, 'expert_diagnostics': dict(public.diagnostics),
                'requested_action': request.to_mapping(), 'canonical_action': canonical.to_mapping(),
                'controller_target': target.to_mapping(), 'applied_control': applied.to_mapping(),
                'canonical_state': state.to_mapping(), 'canonical_control_feedback': feedback.to_mapping(),
                'execution_info': ei.to_mapping(), 'task_info': info,
                'planned': expert.planned_actions_emitted, 'waits': expert.readiness_wait_actions_emitted,
                'total': expert.total_control_actions_emitted})
        ready = {e['stage']: True for e in expert.completion_events}
        result.update(expert_identity=expert.identity, controller_identity=controller.identity,
            completion_events=expert.completion_events, above_ready=ready.get('move_above_cube', False),
            descend_ready=ready.get('descend_vertical', False), gripper_ready=ready.get('close_gripper', False),
            max_cube_lift=max_lift, endpoint_reached=expert.done, task_success=bool(info['is_success']),
            planned=expert.planned_actions_emitted, waits=expert.readiness_wait_actions_emitted,
            total=expert.total_control_actions_emitted, failure_reason=expert.failure_reason,
            stable=True, sample_unchanged=sample.to_mapping() == original)
        result['pass'] = expert.done and all(result[k] for k in ('above_ready', 'descend_ready', 'gripper_ready', 'task_success', 'stable', 'sample_unchanged'))
    except Exception as error:
        result.update(error=str(error), traceback=traceback.format_exc(), stable=False)
    finally:
        if session is not None: session.close()
        write_json(dest / 'trace.json', trace)
        write_json(dest / 'native_raw.json', native_rows)
        write_json(args.output, result)
    return 0 if result['pass'] else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--oracle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--provider', choices=['geophys', 'mujoco'])
    parser.add_argument('--seed', type=int, choices=[31, 73])
    args = parser.parse_args()
    if args.prepare:
        lockpath = args.oracle.parent / 'readiness_oracle_lock.json'
        if args.oracle.exists() or lockpath.exists(): raise ValueError('Evidence collision')
        args.oracle.parent.mkdir(parents=True, exist_ok=True)
        args.oracle.write_text(yaml.safe_dump(json.loads(json.dumps(inputs())), sort_keys=False))
        write_json(lockpath, {'sha256': sha(args.oracle), 'timestamp': datetime.now(timezone.utc).isoformat()})
        return 0
    if args.provider: return worker(args)
    verify(args.oracle)
    results = []
    for provider in ('geophys', 'mujoco'):
        for seed in (31, 73):
            dest = args.output.parent / provider / f'seed{seed}'
            dest.mkdir(parents=True, exist_ok=True)
            output = dest / 'report.json'
            if output.exists(): raise ValueError('preserve first smoke Evidence')
            command = [sys.executable, '-m', 'task_env.diagnostics.phase1.p1_5_readiness', '--oracle', str(args.oracle),
                '--output', str(output), '--provider', provider, '--seed', str(seed)]
            (dest / 'command.txt').write_text('PYTHONPATH=GeoPhys/src:. PYTHONDONTWRITEBYTECODE=1 ' + ' '.join(command) + '\n')
            with (dest / 'stdout.log').open('w') as out, (dest / 'stderr.log').open('w') as err:
                subprocess.run(command, stdout=out, stderr=err, timeout=900, env=os.environ.copy())
            native_log = Path('MUJOCO_LOG.TXT')
            if native_log.exists(): native_log.rename(dest / 'native_warning_log.txt')
            result = json.loads(output.read_text()) if output.exists() else {'pass': False, 'error': 'worker_process'}
            results.append(result)
            write_json(args.output, {'evaluation': 'production_readiness_smoke', 'qualification_claim': False, 'results': results, 'pass': all(r['pass'] for r in results)})
            print(provider, seed, result.get('pass'), result.get('error', result.get('failure_reason')), flush=True)
    verify(args.oracle)
    return 0 if all(r['pass'] for r in results) else 1


if __name__ == '__main__': raise SystemExit(main())
