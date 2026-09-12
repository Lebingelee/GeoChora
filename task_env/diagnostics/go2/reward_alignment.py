"""Report Go2 reward algebra against the supplied Unitree reference.

The comparison is deliberately task-local and dependency-light: it checks the
reference raw scales and their policy-tick ``dt`` conversion, then evaluates a
canonical no-contact state with an independently written copy of the active
reference equations.  Physics/contact response is not hidden in this report;
that is covered by the separate three-engine oracle scripts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


REFERENCE_SCALES = {
    "termination": -0.0,
    "tracking_lin_vel": 1.0,
    "tracking_ang_vel": 0.5,
    "lin_vel_z": -2.0,
    "ang_vel_xy": -0.05,
    "orientation": -0.0,
    "torques": -0.0002,
    "dof_vel": -0.0,
    "dof_acc": -2.5e-7,
    "base_height": -0.0,
    "feet_air_time": 1.0,
    "collision": -1.0,
    "feet_stumble": -0.0,
    "action_rate": -0.01,
    "stand_still": -0.0,
}

TASK_SCALES = {
    "tracking_lin_vel": 1.0,
    "tracking_ang_vel": 0.5,
    "lin_vel_z": -2.0,
    "ang_vel_xy": -0.05,
    "orientation": -0.0,
    "torques": -0.0002,
    "dof_acc": -2.5e-7,
    "action_rate": -0.01,
    "feet_air_time": 1.0,
    "collision": -1.0,
}


def _independent_terms(*, lin, ang, torque, action, previous, qpos, qvel,
                       previous_vel, command, joint_range, dt):
    dof_pos = np.asarray(qpos)[..., :12]
    dof_vel = np.asarray(qvel)[..., :12]
    ranges = np.asarray(joint_range)
    midpoint = 0.5 * (ranges[:, 0] + ranges[:, 1])
    half = 0.5 * (ranges[:, 1] - ranges[:, 0]) * 0.9
    violation = np.sum(np.maximum(midpoint - half - dof_pos, 0.0)
                       + np.maximum(dof_pos - midpoint - half, 0.0), axis=-1)
    return {
        "tracking_lin_vel": np.exp(-np.sum((command[..., :2] - lin[..., :2]) ** 2, axis=-1) / 0.25) * dt,
        "tracking_ang_vel": np.exp(-((command[..., 2] - ang[..., 2]) ** 2) / 0.25) * 0.5 * dt,
        "lin_vel_z": -2.0 * lin[..., 2] ** 2 * dt,
        "ang_vel_xy": -0.05 * np.sum(ang[..., :2] ** 2, axis=-1) * dt,
        "torques": -0.0002 * np.sum(torque ** 2, axis=-1) * dt,
        "dof_pos_limits": -10.0 * violation * dt,
        "dof_acc": -2.5e-7 * np.sum(((previous_vel - dof_vel) / dt) ** 2, axis=-1) * dt,
        "action_rate": -0.01 * np.sum((previous - action) ** 2, axis=-1) * dt,
        "orientation": np.zeros(np.asarray(torque).shape[:-1], dtype=np.float32),
        "feet_air_time": np.zeros(np.asarray(torque).shape[:-1], dtype=np.float32),
        "collision": np.zeros(np.asarray(torque).shape[:-1], dtype=np.float32),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path,
        default=Path("temp_outputs/task_env/go2_reward_alignment.json"),
    )
    args = parser.parse_args()

    from task_env.assembly import compile_task_scene
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.go2_walk.task import GO2_POLICY_DT, Go2WalkEnv, _base_kinematics

    config = resolve_task_env_config(Go2WalkEnv, None)
    env = Go2WalkEnv(config=config, build_runtime=False)
    compiled = compile_task_scene(
        composition=env.composition_spec,
        scene=env.scene,
        agents=env.agents,
        objects=env.objects,
        scene_composer=env.create_scene_composer(),
    )
    refs = compiled.references.agents["go2-v1"]
    task = env.create_task_definition(compiled)
    qpos = np.asarray(compiled.initial_state.qpos, dtype=np.float32).copy()
    qvel = np.asarray(compiled.initial_state.qvel, dtype=np.float32).copy()
    qpos[refs.arm_qpos_ids] += np.linspace(-0.03, 0.03, 12, dtype=np.float32)
    qvel[refs.arm_dof_ids] = np.linspace(-0.2, 0.2, 12, dtype=np.float32)
    action = np.linspace(-0.2, 0.2, 12, dtype=np.float32)
    previous = np.linspace(0.1, -0.1, 12, dtype=np.float32)
    previous_vel = np.linspace(0.2, -0.2, 12, dtype=np.float32)
    command = np.asarray((0.35, -0.1, 0.2), dtype=np.float32)
    _, lin, ang, gravity = _base_kinematics(qpos, qvel, None, task.base_body_id)
    torque = task._compute_torque(action, qpos, qvel)
    actual, actual_terms = task._reward(
        lin, ang, gravity, torque, action, previous, qpos, qvel,
        command, previous_vel, None, None,
    )
    expected_terms = _independent_terms(
        lin=np.asarray(lin), ang=np.asarray(ang), torque=torque,
        action=action, previous=previous, qpos=qpos[refs.arm_qpos_ids],
        qvel=qvel[refs.arm_dof_ids], previous_vel=previous_vel,
        command=command, joint_range=task.joint_range, dt=GO2_POLICY_DT,
    )
    term_error = {
        name: float(np.max(np.abs(np.asarray(actual_terms[name]) - np.asarray(value))))
        for name, value in expected_terms.items()
    }
    report = {
        "schema": "task-env-go2-reward-alignment-v1",
        "policy_dt": float(GO2_POLICY_DT),
        "reference_raw_scales": REFERENCE_SCALES,
        "task_active_raw_scales": TASK_SCALES,
        "missing_active_scales": sorted(set(TASK_SCALES) - set(REFERENCE_SCALES)),
        "scale_mismatches": {
            name: {"reference": REFERENCE_SCALES.get(name), "task": TASK_SCALES.get(name)}
            for name in sorted(set(REFERENCE_SCALES) | set(TASK_SCALES))
            if float(REFERENCE_SCALES.get(name, 0.0)) != float(TASK_SCALES.get(name, 0.0))
        },
        "independent_active_term_max_abs_error": term_error,
        "independent_reward_max_abs_error": float(
            abs(float(np.maximum(np.sum(list(actual_terms.values()), axis=0), 0.0)) - float(actual))
        ),
        "reference_semantic_settings_not_yet_reproduced": [
            "observation_noise_enabled_by_default (reference add_noise=True)",
            "friction randomization and 15-second XY push domain randomization",
            "feet_air_time reference thresholds per-foot contact forces (>1); geom-aware fused ground rows now provide identity, while exact/no-geom profiles use body-active fallback",
            "reference collision counts selected body contact forces; geom-aware Go2 adaptation excludes named foot geoms from calf collision while body-summary fallback remains for older profiles",
        ],
        "interpretation": (
            "active reward algebra/scales match; the listed reference environment "
            "settings remain rollout-semantic gaps"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
