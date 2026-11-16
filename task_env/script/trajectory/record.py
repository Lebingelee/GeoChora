"""Record the selected 100Hz task-owned route; canonical execution H5, no D0 claim."""
from pathlib import Path
import argparse
import json


def _completion_result(env, info, *, solution=None, terminated=False, truncated=False):
    """Report success only after the selected task policy and outcome complete."""
    from task_env.script.trajectory.completion import completion_facts

    solution = env.solution if solution is None else solution
    facts = completion_facts(solution, info, terminated=terminated, truncated=truncated)
    return {**facts, 'status': 'PASS' if facts['policy_complete'] else 'FAIL'}


def main(argv=None):
    from task_env import make_env
    selected_env_ids = ('pick-cube-p16-reference-v1', 'nut-assembly-outcome-reference-v1')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-id', choices=selected_env_ids, default=selected_env_ids[1])
    parser.add_argument('--provider', choices=('geophys', 'mujoco'), required=True)
    parser.add_argument('--horizon', type=int, default=6000)
    parser.add_argument('--seed', type=int, default=19)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    env = None
    info = {}
    completion = verification = error = close_error = None
    close_attempted = close_succeeded = False
    try:
        env = make_env(args.env_id, config={'execution': {'physics_provider': args.provider, 'physics_backend': 'cpu'}, 'episode': {'horizon': args.horizon}})
        observation, info = env.reset(seed=args.seed)
        solution = None
        if args.env_id == selected_env_ids[1]:
            from task_env.tasks.nut_assembly.task import build_outcome_solution
            solution = build_outcome_solution(provider=args.provider)
            solution.reset(observation, info, env.metadata)
        else:
            from task_env.tasks.pick_cube import build_readiness_solution
            solution = build_readiness_solution(backend='cpu', controller_profile='r3_continuous_v1')
            solution.reset(observation, info, env.metadata)
        env.start_recording(args.output)
        terminated = truncated = False
        while not solution.done and not solution.failed:
            action = solution.act(observation, info)
            observation, reward, terminated, truncated, info = env.step(action)
            solution.observe(observation, reward, terminated, truncated, info)
            if terminated or truncated:
                break
        completion = _completion_result(env, info, solution=solution, terminated=terminated, truncated=truncated)
        stop_reason = completion['failure_reason'] or 'selected_policy_completed'
        verification = env.finish_recording(stop_reason)
    except Exception as exc:
        error = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        if env is not None:
            close_attempted = True
            try:
                env.close()
                close_succeeded = True
            except Exception as exc:
                close_error = {'type': type(exc).__name__, 'message': str(exc)}
    status = ('INVALID' if error is not None or close_error is not None or completion is None
              else completion['status'])
    print(json.dumps({'status': status, 'completion': completion,
                      'verification': verification, 'info': info, 'error': error,
                      'close_attempted': close_attempted, 'close_succeeded': close_succeeded,
                      'close_error': close_error}, default=str))
    return 0 if status == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
