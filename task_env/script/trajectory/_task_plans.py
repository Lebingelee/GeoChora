"""Task-owned configuration builders shared by trajectory examples."""

from __future__ import annotations

from typing import Any

from task_env import CameraSpec
from task_env.tasks.nut_assembly.solution import NutAssemblySolution
from task_env.tasks.nut_assembly.task import NUT_ASSEMBLY_TASK_UID
from task_env.tasks.pick_cube import PickCubeSolution
from task_env.tasks.pick_cube.task import PICK_CUBE_TASK_UID
from task_env.utils.rotation import look_at_quat_wxyz


def _nut_assembly_config(
    backend: str,
    horizon: int,
    *,
    camera_obs: bool,
    force_limit_N: float,
    camera_size: int = 64,
) -> dict[str, Any]:
    base_position = (0.8, 0.0, 0.8)
    cameras = (
        CameraSpec(
            "base_camera",
            camera_size,
            camera_size,
            frame="world",
            position=base_position,
            quaternion_wxyz=look_at_quat_wxyz(base_position, (0.0, 0.0, -0.2)),
        ),
        CameraSpec(
            "hand_camera",
            camera_size,
            camera_size,
            frame="site",
            parent="nutassembly_ee_site",
            position=(0.04, 0.0, -0.03),
            quaternion_wxyz=(0.707, 0.0, -0.707, 0.0),
        ),
    )
    return {
        "runtime": {
            "backend": backend,
            "broadphase": "n2",
            "prewarm": False,
            "physics_dt": 1.0 / 600.0,
            "control_substeps": 20,
            "body_contact_solver_iterations": 64,
        },
        "robot": {
            "controller": {
                "kind": "absolute_pose",
                "reference": "world",
                "rotation_representation": "quaternion_wxyz",
            },
            "gripper": {
                "kind": "experimental_rate_limited",
                "force_limit_N": force_limit_N,
                "opening_step_m": 0.002,
                "force_deadband_N": 1.0,
                "force_adjust_step_m": 1.0e-4,
            },
        },
        "render": {
            "camera_obs": camera_obs,
            "backend": "raytracer",
            "cameras": cameras if camera_obs else (),
        },
        "episode": {"horizon": horizon},
    }


def _pick_cube_config(
    backend: str,
    horizon: int,
    *,
    camera_obs: bool,
    force_limit_N: float = 30.0,
    camera_size: int = 64,
) -> dict[str, Any]:
    base_position = (0.8, 0.0, 0.8)
    cameras = (
        CameraSpec(
            "base_camera",
            camera_size,
            camera_size,
            frame="world",
            position=base_position,
            quaternion_wxyz=look_at_quat_wxyz(base_position, (0.0, 0.0, -0.2)),
        ),
        CameraSpec(
            "hand_camera",
            camera_size,
            camera_size,
            frame="site",
            parent="nutassembly_ee_site",
            position=(0.04, 0.0, -0.035),
            quaternion_wxyz=(0.707, 0.0, -0.707, 0.0),
        ),
    )
    return {
        "runtime": {
            "backend": backend,
            "broadphase": "n2",
            "prewarm": False,
            "physics_dt": 1.0 / 600.0,
            "control_substeps": 20,
            "body_contact_solver_iterations": 64,
        },
        "robot": {
            "controller": {
                "kind": "absolute_pose",
                "reference": "world",
                "rotation_representation": "quaternion_wxyz",
                "max_translation_delta_m": 0.25,
                "max_rotation_delta_rad": 0.50,
            },
            "gripper": {
                "kind": "experimental_rate_limited",
                "force_limit_N": force_limit_N,
                "opening_step_m": 0.002,
                "force_deadband_N": 1.0,
                "force_adjust_step_m": 1.0e-4,
            },
        },
        "render": {
            "camera_obs": camera_obs,
            "backend": "raytracer",
            "cameras": cameras if camera_obs else (),
        },
        "episode": {"horizon": horizon, "ignore_done": True},
    }


def _build_plan(
    env_id: str,
    backend: str,
    horizon: int,
    *,
    camera_obs: bool,
    force_limit_N: float,
    camera_size: int = 64,
) -> tuple[dict[str, Any], Any]:
    if env_id == NUT_ASSEMBLY_TASK_UID:
        return (
            _nut_assembly_config(
                backend,
                horizon,
                camera_obs=camera_obs,
                force_limit_N=force_limit_N,
                camera_size=camera_size,
            ),
            NutAssemblySolution(),
        )
    if env_id == PICK_CUBE_TASK_UID:
        return (
            _pick_cube_config(
                backend,
                horizon,
                camera_obs=camera_obs,
                force_limit_N=force_limit_N,
                camera_size=camera_size,
            ),
            PickCubeSolution(),
        )
    raise ValueError(f"unsupported env_id {env_id!r}; no public solution is registered")


__all__ = ["_build_plan", "_nut_assembly_config", "_pick_cube_config"]
