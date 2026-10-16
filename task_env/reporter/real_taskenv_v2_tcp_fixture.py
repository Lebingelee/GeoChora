"""启动真实 PickCube TaskEnv 的显式 remote-gym-env v2 TCP endpoint。"""

from __future__ import annotations

import argparse

from task_env import make_env
from task_env.reporter.v2 import TaskEnvV2Reporter
from task_env.tasks.pick_cube.reference_env import REFERENCE_ENV_ID
from task_env.utils.runtime_support import get_task_env_logger




def _config() -> dict:
    """Selected state-only reference; historical camera fixture is not requalified."""
    return {'provider': 'geophys', 'backend': 'cpu', 'horizon': 8}


def main() -> None:
    logger = get_task_env_logger("simulation", module="task-env-real-reporter-v2-tcp-fixture")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--accept-timeout-s", type=float, default=60.0)
    args = parser.parse_args()
    env = make_env(REFERENCE_ENV_ID, config=_config())
    reporter = TaskEnvV2Reporter(env, args.host, args.port)
    try:
        logger.info("Real TaskEnv v2 reporter fixture is listening", host=args.host, port=args.port)
        while True:
            reporter.serve_once(timeout_s=args.accept_timeout_s)
            if reporter._closed:
                break
    finally:
        reporter.close()


if __name__ == "__main__":
    main()
