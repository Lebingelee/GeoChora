"""Public-observation-only camera example helpers."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from .._bootstrap import (
    BACKEND_CHOICES,
    check_observation,
    get_logger,
    json_compatible,
    stage14_output,
    with_backend_fallback,
    write_json,
)


def camera_config(backend: str, *, bound: bool) -> dict[str, Any]:
    from task_env import CameraSpec
    from task_env.utils.rotation import look_at_quat_wxyz

    if bound:
        cameras = (
            CameraSpec(
                name="eef_camera",
                width=32,
                height=24,
                frame="site",
                parent="nutassembly_ee_site",
                position=(0.08, 0.0, -0.03),
                quaternion_wxyz=(0.70710678, 0.0, -0.70710678, 0.0),
            ),
        )
    else:
        position = np.asarray((0.8, 0.0, 0.8), dtype=np.float64)
        cameras = (
            CameraSpec(
                name="static_camera",
                width=32,
                height=24,
                frame="world",
                position=tuple(position),
                quaternion_wxyz=look_at_quat_wxyz(position, np.asarray((0.0, 0.0, -0.2))),
            ),
        )
    return {
        "runtime": {
            "backend": backend,
            "broadphase": "n2",
            "prewarm": False,
            "physics_dt": 1.0 / 600.0,
            "control_substeps": 1,
        },
        "robot": {
            "controller": {
                "kind": "absolute_pose",
                "reference": "world",
                "rotation_representation": "quaternion_wxyz",
            }
        },
        "render": {"camera_obs": True, "backend": "raytracer", "cameras": cameras},
        "episode": {"horizon": 2},
    }


def _image(observation: Mapping[str, Any], name: str) -> np.ndarray:
    try:
        if "rgb" in observation:
            image = np.asarray(observation["rgb"][name])
        else:
            image = np.asarray(observation["vision"]["rgb"][name])
    except (KeyError, TypeError) as exc:
        raise ValueError(f"public observation is missing vision.rgb.{name}") from exc
    if image.shape != (24, 32, 3) or image.dtype != np.float32 or not np.isfinite(image).all():
        raise ValueError(
            f"camera {name!r} must be finite float32 HWC (24, 32, 3), got "
            f"shape={image.shape}, dtype={image.dtype}"
        )
    return image


def run_camera(*, requested_backend: str, bound: bool) -> Path:
    from task_env import make_env

    name = "bound" if bound else "static"
    logger = get_logger(f"task-env-stage14-camera-{name}")

    def create(backend: str):
        return make_env("pick-cube-v1", config=camera_config(backend, bound=bound))

    backend, env = with_backend_fallback(
        requested_backend,
        create,
        logger=logger,
        operation=f"camera:{name}",
    )
    try:
        observation, info = env.reset(seed=31)
        check_observation(observation, env.observation_space)
        first = _image(observation, "eef_camera" if bound else "static_camera")
        images = {"first": first.copy()}
        bound_motion = None
        if bound:
            current_pose = np.asarray(observation["state"]["ee_pose"], dtype=np.float32).copy()
            target = current_pose.copy()
            target[2] += 0.01
            action = np.concatenate((target, np.asarray([1.0], dtype=np.float32)))
            observation, reward, terminated, truncated, info = env.step(action)
            check_observation(observation, env.observation_space)
            second = _image(observation, "eef_camera")
            images["after_step"] = second.copy()
            bound_motion = {
                "ee_pose_delta": float(
                    np.linalg.norm(
                        np.asarray(observation["state"]["ee_pose"], dtype=np.float32)[:3]
                        - current_pose[:3]
                    )
                ),
                "image_delta": float(np.mean(np.abs(second - first))),
                "terminated": bool(terminated),
                "truncated": bool(truncated),
            }
            if bound_motion["ee_pose_delta"] <= 0.0:
                raise ValueError("bound camera example did not observe parent motion")
        output = stage14_output("camera", f"{name}.npz")
        np.savez_compressed(output, **images)
        summary = {
            "camera_mode": name,
            "backend": backend,
            "observation_schema": json_compatible(info.get("observation_schema", {})),
            "images": {
                key: {"shape": list(value.shape), "dtype": str(value.dtype), "finite": bool(np.isfinite(value).all())}
                for key, value in images.items()
            },
            "bound_motion": bound_motion,
            "output": str(output),
        }
        write_json(stage14_output("camera", f"{name}.json"), summary)
        logger.success(
            "Stage 14 camera example completed",
            camera_mode=name,
            backend=backend,
            output=str(output),
        )
        return output
    finally:
        env.close()
