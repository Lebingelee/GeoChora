"""为跨工作区 socket 验收启动真实 TaskEnv 的短生命周期 TCP producer。"""

from __future__ import annotations

import argparse

from task_env import make_env
from task_env.reporter import ReporterDisconnected, ReporterSession, TcpReporterTransport
from task_env.tasks.pick_cube.reference_env import REFERENCE_ENV_ID
from task_env.utils.runtime_support import get_task_env_logger




def _config() -> dict:
    """Selected state-only reference; historical camera fixture is not requalified."""
    return {'provider': 'geophys', 'backend': 'cpu', 'horizon': 8}


def main() -> None:
    logger = get_task_env_logger("simulation", module="task-env-real-reporter-tcp-fixture")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-steps", type=int, default=1)
    parser.add_argument("--accept-timeout-s", type=float, default=60.0)
    args = parser.parse_args()
    if args.max_steps < 1:
        raise ValueError("--max-steps must be positive")

    env = make_env(REFERENCE_ENV_ID, config=_config())
    transport = TcpReporterTransport(args.host, args.port)
    session = ReporterSession(env, transport)
    completed_steps = 0
    try:
        logger.info(
            "Real TaskEnv reporter fixture is listening",
            host=args.host,
            port=args.port,
            max_steps=args.max_steps,
        )
        while completed_steps < args.max_steps:
            transport.accept(timeout_s=args.accept_timeout_s)
            if session.latest_packet is None:
                session.reset(seed=args.seed)
            else:
                session.republish_latest()
            while completed_steps < args.max_steps:
                try:
                    result = session.step_if_action(timeout_s=None)
                except ReporterDisconnected:
                    logger.info("TCP client disconnected; waiting for explicit reconnect")
                    break
                if result is not None:
                    completed_steps += 1
        logger.success("Real TaskEnv reporter fixture completed requested steps")
    finally:
        session.close()
        env.close()


if __name__ == "__main__":
    main()
