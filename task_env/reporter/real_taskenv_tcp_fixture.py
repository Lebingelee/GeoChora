"""为跨工作区 socket 验收启动真实 TaskEnv 的短生命周期 TCP producer。"""

from __future__ import annotations

import argparse

from task_env import CameraSpec, make_env
from task_env.reporter import ReporterDisconnected, ReporterSession, TcpReporterTransport
from task_env.tasks.pick_cube.task import PICK_CUBE_TASK_UID
from task_env.utils.runtime_support import get_task_env_logger


logger = get_task_env_logger("simulation", module="task-env-real-reporter-tcp-fixture")


def _config() -> dict:
    return {
        "runtime": {
            "backend": "cpu",
            "broadphase": "n2",
            "prewarm": False,
            "control_substeps": 1,
        },
        "robot": {"controller": {"kind": "absolute_joint"}},
        "observation": {"schema_version": "task-env-state-v2"},
        "render": {
            "camera_obs": True,
            "backend": "raytracer",
            "cameras": (
                CameraSpec(
                    "front_hwc",
                    width=16,
                    height=12,
                    rgb_layout="HWC",
                    rgb_dtype="float32",
                    position=(0.7, 0.0, 0.8),
                ),
                CameraSpec(
                    "wrist_chw",
                    width=16,
                    height=12,
                    rgb_layout="CHW",
                    rgb_dtype="uint8",
                    position=(0.6, 0.2, 0.7),
                ),
            ),
        },
        "episode": {"horizon": 8},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-steps", type=int, default=1)
    parser.add_argument("--accept-timeout-s", type=float, default=60.0)
    args = parser.parse_args()
    if args.max_steps < 1:
        raise ValueError("--max-steps must be positive")

    env = make_env(PICK_CUBE_TASK_UID, config=_config())
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
