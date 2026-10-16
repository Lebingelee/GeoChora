"""Record the selected 100Hz task-owned route; canonical execution H5, no D0 claim."""
from pathlib import Path
import argparse
import json


def _completion_result(env, *, terminated=False, truncated=False):
    """Report success only after the selected task policy and outcome complete."""
    solution = env.solution
    result = {
        'solution_done': bool(solution.done),
        'solution_failed': bool(solution.failed),
        'task_success': bool(env.info.get('task_metrics', {}).get('task_success', env.info.get('is_success', False))),
        'planned_trajectory_completed': None,
        'outcome_complete': None,
        'unapproved_override_used': None,
        'terminated': bool(terminated),
        'truncated': bool(truncated),
    }
    reason = None
    if terminated:
        reason = 'environment_terminated'
    elif truncated:
        reason = 'environment_truncated_or_horizon_reached'
    elif solution.failed:
        reason = solution.failure_reason or 'selected_policy_failed'
    elif not solution.done:
        reason = 'selected_policy_incomplete'
    elif not result['task_success']:
        reason = 'task_success_false'
    elif env.task_kind == 'nut_assembly':
        outcome = solution.outcome_report()
        result['planned_trajectory_completed'] = bool(outcome.get('planned_trajectory_completed'))
        result['outcome_complete'] = bool(outcome.get('outcome_complete'))
        result['unapproved_override_used'] = outcome.get('unapproved_override_used')
        if not result['planned_trajectory_completed']:
            reason = 'planned_trajectory_incomplete'
        elif not result['outcome_complete']:
            reason = 'outcome_incomplete'
        elif result['unapproved_override_used'] is not False:
            reason = 'unapproved_override_used_or_unreported'
    result['status'] = 'PASS' if reason is None else 'FAIL'
    result['failure_reason'] = reason
    return result


def main(argv=None):
    from task_env import make_env
    from task_env.script.trajectory._task_plans import SELECTED_ENV_IDS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-id', choices=SELECTED_ENV_IDS, default=SELECTED_ENV_IDS[1])
    parser.add_argument('--provider', choices=('geophys', 'mujoco'), required=True)
    parser.add_argument('--horizon', type=int, default=6000)
    parser.add_argument('--seed', type=int, default=19)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    env = make_env(args.env_id, config={'provider': args.provider, 'horizon': args.horizon})
    try:
        env.reset(seed=args.seed)
        env.start_recording(args.output)
        terminated = truncated = False
        while not env._stopped:
            _, _, terminated, truncated, _ = env.step_expert()
        completion = _completion_result(env, terminated=terminated, truncated=truncated)
        stop_reason = completion['failure_reason'] or 'selected_policy_completed'
        verification = env.finish_recording(stop_reason)
        print(json.dumps({'status': completion['status'], 'completion': completion,
                          'verification': verification, 'info': env.info}, default=str))
        return 0 if completion['status'] == 'PASS' else 1
    finally:
        env.close()


if __name__ == '__main__':
    raise SystemExit(main())
