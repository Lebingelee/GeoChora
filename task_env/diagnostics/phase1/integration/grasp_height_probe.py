"""Opt-in shared +1 mm grasp diagnostic; no default profile migration."""
import argparse
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from .stable_grasp import context as base_context, worker


def context(rate):
    value = base_context(rate, skip_absolute_height_gate=True)
    config = replace(value['solution_config'], grasp_offset=(0., 0., .045895))
    value['solution_config'] = config
    value['solution'] = type(value['solution'])(config=config,
        control_dt=value['artifact'].timebase.control_dt, arm_hold=value['controller'].hold)
    value['solution_identity'] = value['solution'].identity
    value['recipe_identity'] = hashlib.sha256(json.dumps({
        'base': value['recipe_identity'], 'grasp_offset': config.grasp_offset,
        'diagnostic_raise_m': .001}, sort_keys=True).encode()).hexdigest()
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rate', type=int, choices=(500, 100, 50), required=True)
    parser.add_argument('--provider', choices=('geophys', 'mujoco'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    value = context(args.rate)
    worker.CLOSE_TIME_LIMIT_S = 1.5
    report = worker.run_loaded(value, args.provider, args.output, 'G0')
    report.update(solution_events=value['solution'].events, grasp_offset_z_m=.045895,
        raise_m=.001, force_limit_N=10., fallback_enabled=False, forced_lift=False,
        absolute_height_gate_enabled=False, outer_rate_hz=args.rate,
        gripper_rate_hz=args.rate, development_only=True)
    worker._write(args.output / 'report.json', report)
    print(json.dumps({key:report.get(key) for key in ('pass', 'failure_boundary',
        'close_authorization', 'verify_lift_pass')}), flush=True)
    if not report['pass']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
