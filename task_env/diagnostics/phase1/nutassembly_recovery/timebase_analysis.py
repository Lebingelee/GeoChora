"""Provider-free planner/gripper rate audit using preserved failure Evidence.

This measures authored commands, not native tracking or grasp qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from ....environment.config import GripperConfig
from ....planners.cartesian import CartesianPosePlanner, CartesianPosePlannerConfig


def audit(existing_analysis):
    path = Path(existing_analysis)
    old = json.loads(path.read_text())
    gripper = GripperConfig()
    fixtures = []
    for hz in (50, 100, 500):
        dt = 1 / hz
        planner = CartesianPosePlanner(CartesianPosePlannerConfig(
            max_translation_per_step=.04 * dt,
            max_translation_acceleration_per_step=.15 * dt * dt,
            max_rotation_per_step=3 * dt,
            max_rotation_acceleration_per_step=27 * dt * dt,
            settle_steps=0, max_steps=int(6 / dt)))
        start = np.array([0., 0., 0., 1., 0., 0., 0.])
        end = start.copy()
        end[0] = .1
        actions = planner.plan_to_pose(current_pose=start, goal_pose=end)
        positions = np.vstack([start[:3], actions[:, :3], end[:3]])
        velocity = np.diff(positions, axis=0) / dt
        acceleration = np.diff(velocity, axis=0) / dt
        vmax = float(np.linalg.norm(velocity, axis=1).max())
        amax = float(np.linalg.norm(acceleration, axis=1).max())
        fixtures.append({
            'control_frequency_Hz': hz, 'control_dt_s': dt,
            'physics_dt_s': .002, 'control_substeps': round(dt / .002),
            'planned_ticks': len(actions), 'planned_duration_s': len(actions) * dt,
            'planned_max_speed_m_s': vmax, 'planned_max_acceleration_m_s2': amax,
            'float32_command_bounds_pass': vmax <= .04001 and amax <= .1501,
            'opening_command_rate_ceiling_m_s': gripper.opening_step_m / dt,
            'force_servo_correction_rate_m_s': gripper.force_adjust_step_m / dt,
            'legacy_25_tick_close_duration_s': 25 * dt,
        })
    episodes = []
    for episode in old['episodes']:
        descend, close = episode['end_descend'], episode['end_close']
        episodes.append({
            'profile': episode['profile'], 'provider': episode['provider'],
            'source_h5': episode['path'], 'source_h5_sha256': episode['h5_sha256'],
            'end_descend_request_residual_m': descend['EE_request_residual_m'],
            'end_close_request_residual_m': close['EE_request_residual_m'],
            'close_physical_duration_s': close['simulation_time_s'] - descend['simulation_time_s'],
            'end_close_measured_opening_m': close['physical_opening_m'],
            'end_close_desired_opening_m': close['target']['opening_m'],
            'end_close_servo_opening_m': close['target']['servo_opening_m'],
            'end_close_closing_force_N': close['feedback']['closing_force_N'],
            'end_close_reached_nut': close['reached_nut'],
            'end_close_grasped_nut': close['grasped_nut'],
        })
    return {
        'schema': 'nutassembly-planner-gripper-rate-audit-v0',
        'physics_executed': False, 'production_modified': False,
        'existing_analysis_path': str(path),
        'existing_analysis_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'planned_fixture': '0.1m straight translation, identity orientation, v=.04m/s, a=.15m/s2',
        'planner_sampling': fixtures, 'preserved_failed_runs': episodes,
        'interpretation': 'Command rate invariance is necessary but does not establish achieved tracking or grasp stability. Gripper rate ceilings are command updates, not measured speeds. Per-boundary arm DLS is not a continuous-time gain contract.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--existing-analysis', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = audit(args.existing_analysis)
    assert all(row['float32_command_bounds_pass'] for row in result['planner_sampling'])
    Path(args.output).write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(args.output)


if __name__ == '__main__':
    main()
