"""Record one public task solution as a TaskEnv H5 v2 trajectory."""

from __future__ import annotations

import argparse
from pathlib import Path

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from task_env.script._bootstrap import BACKEND_CHOICES, get_logger, stage14_output, with_backend_fallback
    from task_env.script.trajectory._task_plans import _build_plan
else:
    from .._bootstrap import BACKEND_CHOICES, get_logger, stage14_output, with_backend_fallback
    from ._task_plans import _build_plan


def main() -> None:
    from task_env import make_env
    from task_env.recorders import RecorderConfig, TransitionRecordWrapper

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-id",
        "--env_id",
        dest="env_id",
        choices=("pick-cube-v1", "nut-assembly-square-v1"),
        default="nut-assembly-square-v1",
    )
    parser.add_argument("--output", "--h5_path", dest="output", type=Path)
    parser.add_argument("--backend", choices=BACKEND_CHOICES, default="auto")
    parser.add_argument("--horizon", type=int, default=600)
    parser.add_argument("--seed", type=int, default=19)
    parser.add_argument("--gripper-force", "--gripper_force", dest="gripper_force", type=float, default=30.0)
    parser.add_argument("--camera-size", type=int, default=64)
    parser.add_argument("--no-render", action="store_true")
    args = parser.parse_args()
    if args.horizon < 1 or args.gripper_force <= 0.0 or args.camera_size < 1:
        parser.error("horizon, gripper force, and camera size must be positive")
    output = args.output or stage14_output(
        "trajectories", args.env_id, f"trajectory_seed{args.seed}.h5"
    )
    logger = get_logger("task-env-stage14-trajectory-record")

    def create(backend: str):
        config, solution = _build_plan(
            args.env_id,
            backend,
            args.horizon,
            camera_obs=not args.no_render,
            force_limit_N=args.gripper_force,
            camera_size=args.camera_size,
        )
        wrapper = TransitionRecordWrapper(
            make_env(args.env_id, config=config),
            RecorderConfig(max_transitions=args.horizon, meta_only=True),
        )
        return wrapper, solution

    backend, pair = with_backend_fallback(
        args.backend,
        create,
        logger=logger,
        operation=f"trajectory-record:{args.env_id}",
    )
    env, solution = pair
    try:
        observation, info = env.reset(seed=args.seed)
        env.start_record()
        solution.reset(observation, info, env.metadata)
        while not solution.done and not solution.failed:
            proposal = solution.act(observation, info)
            observation, reward, terminated, truncated, info = env.step(proposal.action)
            solution.observe(observation, reward, terminated, truncated, info)
        if env.recorder.active:
            env.end_record()
        logger.check_or_raise(
            solution.done and not solution.failed and bool(info.get("is_success", False)),
            "trajectory recording requires a successful public solution",
            env_id=args.env_id,
            failure_reason=solution.failure_reason,
            metrics=info.get("task_metrics", {}),
        )
        saved = env.save_h5(output.parent, output.name)
        logger.success(
            "Stage 14 trajectory recorded",
            env_id=args.env_id,
            backend=backend,
            output=str(saved),
            transition_count=env.recorder.frozen.transition_count,
        )
    finally:
        env.close()


if __name__ == "__main__":
    main()
