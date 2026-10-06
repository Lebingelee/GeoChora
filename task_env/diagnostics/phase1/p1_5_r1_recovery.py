"""Reusable independently locked R1 prerequisite detector; never runs C2."""
import argparse, json, os, subprocess, sys
from pathlib import Path
import numpy as np
from .p1_2_runtime import write_json
from .control_recovery.spec import verify
from .control_recovery.pure import checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--oracle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', choices=['geophys', 'mujoco'])
    parser.add_argument('--route', choices=['gripper', 'C1_A', 'C1_B'])
    args = parser.parse_args()
    if args.worker:
        from .control_recovery.worker import run
        run(args.worker, args.route, args.oracle, args.output)
        return
    spec, lock = verify(args.oracle)
    root = args.output.parent
    if args.output.exists():
        raise ValueError('preserve previous recovery run; choose a new output root')
    root.mkdir(parents=True, exist_ok=True)
    pure = checks()
    report = {'oracle_sha256': lock['sha256'], 'provider_free': pure,
        'providers': {}, 'pairwise': {}, 'C2': 'not_run', 'qualification_claim': False}
    if not pure['pass']:
        write_json(args.output, report)
        raise ValueError('provider-free prerequisite failed')
    for route in ('gripper', 'C1_A', 'C1_B'):
        for provider in ('geophys', 'mujoco'):
            output = root / route / provider / 'report.json'
            output.parent.mkdir(parents=True, exist_ok=True)
            command = [sys.executable, '-m', 'task_env.diagnostics.phase1.p1_5_r1_recovery',
                '--oracle', str(args.oracle), '--output', str(output), '--worker', provider, '--route', route]
            (output.parent / 'command.txt').write_text('PYTHONPATH=GeoPhys/src:. PYTHONDONTWRITEBYTECODE=1 ' + ' '.join(command) + '\n')
            with (output.parent / 'stdout.log').open('w') as out, (output.parent / 'stderr.log').open('w') as err:
                try:
                    process = subprocess.run(command, stdout=out, stderr=err, timeout=600, env=os.environ.copy())
                    rc = process.returncode
                except subprocess.TimeoutExpired:
                    rc = 124
            value = json.loads(output.read_text()) if output.exists() else {'pass': False, 'returncode': rc, 'first_boundary': 'worker_process'}
            report['providers'].setdefault(provider, {})[route] = value
            write_json(args.output, report)
        if route in ('C1_A', 'C1_B'):
            a = report['providers']['geophys'][route].get('metrics')
            b = report['providers']['mujoco'][route].get('metrics')
            if a and b:
                joint = float(np.max(np.abs(np.array(a['final_joint']) - b['final_joint'])))
                ee = float(np.linalg.norm(np.array(a['final_EE']) - b['final_EE']))
                report['pairwise'][route] = {'joint_max_abs': joint, 'EE_distance_m': ee,
                    'pass': joint <= spec['bounds'][route + '_pairwise_joint'] and (route == 'C1_A' or ee <= spec['bounds']['C1_B_pairwise_EE_m'])}
            else:
                report['pairwise'][route] = {'pass': False, 'not_comparable': True}
    verify(args.oracle)
    report['pass'] = all(v.get('pass', False) for routes in report['providers'].values() for v in routes.values()) and all(v['pass'] for v in report['pairwise'].values())
    report['status'] = 'prerequisites_pass_ready_for_human_review' if report['pass'] else 'partial_with_localized_failure'
    write_json(args.output, report)
    print(json.dumps({'status': report['status'], 'providers': {p: {r: v['pass'] for r,v in routes.items()} for p,routes in report['providers'].items()}, 'pairwise': report['pairwise']}, indent=2))
    sys.exit(0 if report['pass'] else 1)


if __name__ == '__main__':
    main()
