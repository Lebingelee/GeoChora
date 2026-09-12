"""启动真实 PickCube TaskEnv 的显式 remote-gym-env v2 TCP endpoint。"""

from __future__ import annotations

import argparse

from task_env import CameraSpec, make_env
from task_env.reporter.v2 import TaskEnvV2Reporter
from task_env.tasks.pick_cube.task import PICK_CUBE_TASK_UID
from task_env.utils.runtime_support import get_task_env_logger


logger = get_task_env_logger("simulation", module="task-env-real-reporter-v2-tcp-fixture")


def _config() -> dict:
    return {
        "runtime": {"backend": "cpu", "broadphase": "n2", "prewarm": False, "control_substeps": 1},
        "robot": {"controller": {"kind": "absolute_joint"}},
        "observation": {"schema_version": "task-env-state-v2"},
        "render": {
            "camera_obs": True,
            "backend": "raytracer",
            "cameras": (
                CameraSpec("front_hwc", width=16, height=12, rgb_layout="HWC", rgb_dtype="float32", position=(0.7, 0.0, 0.8)),
                CameraSpec("wrist_chw", width=16, height=12, rgb_layout="CHW", rgb_dtype="uint8", position=(0.6, 0.2, 0.7)),
            ),
        },
        "episode": {"horizon": 8},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--accept-timeout-s", type=float, default=60.0)
    args = parser.parse_args()
    env = make_env(PICK_CUBE_TASK_UID, config=_config())
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
