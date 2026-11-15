"""Independently check retained G06 transport, physics and raster diagnostics."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np


def _receipt(directory):
    path = Path(directory)
    supervisor = json.loads((path / 'supervisor.json').read_text())
    if supervisor['exit_code'] != 0 or supervisor['violation'] or supervisor['forced_retirement']:
        raise ValueError(f'unsuccessful supervised run: {path}')
    lines = (path / 'stdout.log').read_text().splitlines()
    return path, json.loads(lines[-1])


def readback(ipc, physics, raster, formal, example):
    _, transfer = _receipt(ipc)
    if (transfer['initial'], transfer['worker_observed'], transfer['final'], transfer['worker_closed']) != (
            [1., 2.], [4., 7.], [9., 13.], True):
        raise ValueError('CUDA IPC diagnostic values or close differ')
    _, state = _receipt(physics)
    q = np.asarray(state['initial_q_rad'])
    v = np.asarray(state['initial_qd_rad_s'])
    u = np.asarray(state['effort_nm'])
    measured = np.asarray(state['observed_first_qd_rad_s'])
    expected = v + .002 * (u + 9.81 * .25 * np.sin(q) - .05 * v) / .1125
    if (state['batch'] != 3 or state['seeds'] != [73, 74, 75]
            or state['native_batch_steps'] != 500 or state['world_steps'] != 1500
            or not np.all(np.abs(measured - expected) < .002)):
        raise ValueError('MJWarp diagnostic does not satisfy the frozen physical oracle')
    raster_dir, rendered = _receipt(raster)
    with np.load(raster_dir / rendered['image']['file']) as frames:
        first, repeat, final = (frames[key] for key in ('initial', 'repeated', 'final'))
    if (first.shape != (128, 128, 3) or first.dtype != np.float32
            or not np.array_equal(first, repeat) or np.array_equal(first, final)
            or rendered['initial'] != rendered['after_repeated_render']):
        raise ValueError('Rasterizer frame or clock evidence differs')

    def centroid(frame):
        mask = ((frame[:, :, 2] > frame[:, :, 0] * 1.3)
                & (frame[:, :, 2] > frame[:, :, 1] * 1.2))
        y, x = np.where(mask)
        if len(x) < 20:
            raise ValueError('Pendulum pixels are unavailable')
        return np.array([x.mean(), y.mean()])

    first_xy, final_xy = centroid(first), centroid(final)
    if (np.sin(rendered['final']['q_rad']) <= .5
            or final_xy[0] <= first_xy[0] + 5 or final_xy[1] <= first_xy[1] + 3):
        raise ValueError('rendered centroid disagrees with the hinge axis')
    _, public = _receipt(formal)
    q, v = np.asarray(public['initial_q_rad'], dtype=float), np.asarray(public['initial_qd_rad_s'], dtype=float)
    for _ in range(25):
        v += .002 * (np.asarray([-1.5, .5, 1.5]) + 9.81 * .25 * np.sin(q) - .05 * v) / .1125
        q += .002 * v
    if (np.max(np.abs(q - public['first_q_rad'])) > .01
            or np.max(np.abs(v - public['first_qd_rad_s'])) > .05
            or public['truncated'] != [True, False, True]
            or not public['terminal_snapshot_retained'] or not public['worker_closed']):
        raise ValueError('public device run failed the independent physical/lifecycle readback')
    terminal_q = np.asarray(public['terminal_previous_q_rad'], dtype=float)
    terminal_v = np.asarray(public['terminal_previous_qd_rad_s'], dtype=float)
    for _ in range(25):
        terminal_v += .002 * (np.asarray([-1.5, .5, 1.5])
                              + 9.81 * .25 * np.sin(terminal_q) - .05 * terminal_v) / .1125
        terminal_q += .002 * terminal_v
    expected_final = np.stack((np.cos(terminal_q), np.sin(terminal_q), terminal_v), axis=1)[[0, 2]]
    saved_final = np.asarray(public['terminal_observation'])
    if (np.max(np.abs(expected_final[:, :2] - saved_final[:, :2])) > .01
            or np.max(np.abs(expected_final[:, 2] - saved_final[:, 2])) > .05
            or np.array_equal(saved_final, public['post_reset_observation'])):
        raise ValueError('saved terminal observations do not match the old transition')
    example_dir, example_stdout = _receipt(example)
    example_file = json.loads((example_dir / 'result.json').read_text())
    if (example_file != example_stdout or example_file['task'] != 'pendulum-v1'
            or example_file['device'] != 'cuda:0' or example_file['num_envs'] != 3
            or example_file['native_step'] != 500 or example_file['truncated'] != [True] * 3
            or not example_file['closed']):
        raise ValueError('ordinary example result or close readback differs')
    return {'status': 'PASS', 'scope': 'formal Pendulum device, diagnostic IPC and host RGB; not qualification',
            'max_first_step_error_rad_s': float(np.max(np.abs(measured - expected))),
            'initial_centroid_xy': first_xy.tolist(), 'final_centroid_xy': final_xy.tolist(),
            'raster_image_dtype': str(first.dtype), 'raster_image_device': 'host',
            'public_q_error_rad': float(np.max(np.abs(q - public['first_q_rad']))),
            'public_qd_error_rad_s': float(np.max(np.abs(v - public['first_qd_rad_s']))),
            'example_steps': example_file['steps']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ipc', required=True)
    parser.add_argument('--physics', required=True)
    parser.add_argument('--raster', required=True)
    parser.add_argument('--formal', required=True)
    parser.add_argument('--example', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = readback(args.ipc, args.physics, args.raster, args.formal, args.example)
    Path(args.output).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
