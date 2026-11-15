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
    # A native child can finish a partial log line just before the parent
    # prints its JSON receipt. Accept that prefix, but require a complete JSON
    # object through the end of the line rather than a substring match.
    line = lines[-1]
    for offset, char in enumerate(line):
        if char != '{':
            continue
        try:
            receipt = json.loads(line[offset:])
        except json.JSONDecodeError:
            continue
        if isinstance(receipt, dict):
            return path, receipt
    raise ValueError(f'supervised run has no complete JSON receipt: {path}')


def readback_pickcube_fk(directory, source_xml):
    """Independently compare recorded initial hand/EE poses to source MuJoCo FK."""
    import mujoco

    _, receipt = _receipt(directory)
    model = mujoco.MjModel.from_xml_path(str(Path(source_xml).resolve(strict=True)))
    data = mujoco.MjData(model)
    names = [f'joint{index}' for index in range(1, 8)] + ['finger_joint1', 'finger_joint2']
    observed_q = np.asarray(receipt['initial_joint_position'], dtype=float)
    actual_hand = np.asarray(receipt['initial_hand_pose'], dtype=float)
    actual_ee = np.asarray(receipt['initial_ee_pose'], dtype=float)
    if observed_q.shape != (3, 9) or actual_hand.shape != (3, 7) or actual_ee.shape != (3, 7):
        raise ValueError('PickCube FK evidence does not contain three complete Robot states')
    hand_id = model.body('hand').id
    errors = []
    for row in range(3):
        for name, value in zip(names, observed_q[row], strict=True):
            data.joint(name).qpos[:] = value
        mujoco.mj_forward(model, data)
        position, quat = data.xpos[hand_id].copy(), data.xquat[hand_id].copy()
        matrix = data.xmat[hand_id].reshape(3, 3)
        expected_ee = position + matrix @ np.array([0., 0., .0584])
        def quat_error(a, b):
            return min(np.max(np.abs(a - b)), np.max(np.abs(a + b)))
        errors.append({'hand_position_m': float(np.max(np.abs(actual_hand[row, :3] - position))),
                       'hand_quaternion': float(quat_error(actual_hand[row, 3:], quat)),
                       'ee_position_m': float(np.max(np.abs(actual_ee[row, :3] - expected_ee))),
                       'ee_quaternion': float(quat_error(actual_ee[row, 3:], quat))})
    if any(max(row.values()) > 1e-4 for row in errors):
        raise ValueError(f'PickCube USD body/frame poses differ from source FK: {errors}')
    return {'status': 'PASS', 'scope': 'three initial hand and EE poses against source MuJoCo FK',
            'position_tolerance_m': 1e-4, 'quaternion_component_tolerance': 1e-4, 'errors': errors}


def readback_pickcube_projection(directory, *, phase='initial'):
    """Compare observed row differences with independently projected cube bounds."""
    import itertools
    import math

    path, receipt = _receipt(directory)
    if receipt['batch'] != 3 or receipt['camera_names'] != ['base', 'hand']:
        raise ValueError('camera probe has an unexpected batch or camera declaration')

    def rotate(quat, vector):
        quat = np.asarray(quat, dtype=float)
        quat = quat / np.linalg.norm(quat)
        vector = np.asarray(vector, dtype=float)
        return vector + 2 * np.cross(quat[1:], np.cross(quat[1:], vector) + quat[0] * vector)

    def multiply(a, b):
        return np.r_[a[0] * b[0] - np.dot(a[1:], b[1:]),
                     a[0] * b[1:] + b[0] * a[1:] + np.cross(a[1:], b[1:])]

    cy, sy = math.cos(.45 / 2), math.sin(.45 / 2)
    cp, sp = math.cos(.25 / 2), math.sin(.25 / 2)
    cameras = {'base': ('panda-v1/link0', np.array([-.35, -.4, .8]),
                        np.array([cy * cp, -sy * sp, cy * sp, sy * cp])),
               'hand': ('panda-v1/hand', np.array([.075, 0., -.15]),
                        np.array([math.sqrt(.5), 0., -math.sqrt(.5), 0.]))}
    corners = np.array(list(itertools.product((-.025, .025), repeat=3)))
    results = {}
    with np.load(path / 'pickcube_camera_probe.npz') as evidence:
        names = list(evidence['body_names'])
        position = evidence[phase + '_body_position']
        orientation = evidence[phase + '_body_orientation']
        cube = names.index('cube-v1')
        for camera, (parent_name, local_p, local_q) in cameras.items():
            parent = names.index(parent_name)
            images = evidence[camera + '_' + phase].astype(np.int16)
            boxes = []
            for row in range(3):
                parent_q = orientation[row, parent].astype(float)
                camera_q = multiply(parent_q, local_q)
                camera_p = position[row, parent] + rotate(parent_q, local_p)
                forward, up = rotate(camera_q, [1., 0., 0.]), rotate(camera_q, [0., 0., 1.])
                right = np.cross(forward, up)
                world_corners = np.array([position[row, cube] + rotate(orientation[row, cube], p)
                                          for p in corners])
                delta = world_corners - camera_p
                depth = delta @ forward
                if np.any(depth <= .01):
                    raise ValueError(f'{camera} row {row} cube is not fully in front of the near plane')
                u, v = 64. + 64. * (delta @ right) / depth, 64. - 64. * (delta @ up) / depth
                x0, x1 = max(0, int(np.floor(u.min())) - 4), min(127, int(np.ceil(u.max())) + 4)
                y0, y1 = max(0, int(np.floor(v.min())) - 4), min(127, int(np.ceil(v.max())) + 4)
                if x0 > x1 or y0 > y1:
                    raise ValueError(f'{camera} row {row} projected cube does not intersect image')
                boxes.append((x0, y0, x1, y1))
            witnesses = []
            for first, second in ((0, 1), (1, 2), (2, 0)):
                difference = np.max(np.abs(images[first] - images[second]), axis=2) >= 8
                counts = []
                for row in (first, second):
                    x0, y0, x1, y1 = boxes[row]
                    counts.append(int(difference[y0:y1 + 1, x0:x1 + 1].sum()))
                if min(counts) < 3:
                    raise ValueError(f'{camera} rows {first},{second} lack projected cube pixels: '
                                     f'boxes={boxes}, counts={counts}')
                witnesses.append({'rows': [first, second], 'changed_pixels_in_projected_boxes': counts})
            results[camera] = {'projected_boxes_xyxy': boxes, 'row_pairs': witnesses}
    return {'status': 'PASS', 'scope': f'{phase} row-local cube projection in two RGB cameras',
            'margin_pixels': 4, 'rgb_difference_threshold': 8, 'results': results}


def readback_isaac_filter(directory):
    _, receipt = _receipt(directory)
    trials = receipt['trials']
    if len(trials) != 2 or [trial['filter_enabled'] for trial in trials] != [True, False]:
        raise ValueError('collision control does not contain both filter conditions')
    if 'initial_q' in trials[0]:
        names = [f'joint{index}' for index in range(1, 8)] + ['finger_joint1', 'finger_joint2']
        initial = np.array([-.17, 0., 0., -np.pi / 2, 0., np.pi / 2, -np.pi / 4, .04, .04])
        cross_type = 'cube_initial_pose' in trials[0]
        rows = 1 if cross_type else 3
        origins = (np.zeros((3, 3)) if cross_type
                   else np.array([[0., 0., 0.], [.01, 0., 0.], [-.01, 0., 0.]]))
        finals = []
        for trial in trials:
            value = np.asarray(trial['final_q'], dtype=float)
            if (trial['dof_names'] != names or trial['native_steps'] != 25
                    or value.shape != (rows, 9) or not np.isfinite(value).all()
                    or not np.allclose(trial['initial_q'], np.tile(initial, (rows, 1)), atol=1e-6, rtol=0)
                    or not np.allclose(trial['origins_m'], origins, atol=1e-9, rtol=0)):
                raise ValueError('source robot filter control differs from frozen inputs')
            if cross_type:
                cube = np.asarray(trial['cube_initial_pose'], dtype=float)
                if (cube.shape != (1, 7) or not np.allclose(
                        cube[0], [.5465, -.0938, .6245, 0., 0., 0., 1.], atol=1e-6, rtol=0)
                        or not np.isfinite(trial['cube_final_pose']).all()):
                    raise ValueError('cross-type filter control lacks its frozen cube placement')
            finals.append(value)
        row_error = float(np.max(np.abs(finals[0] - finals[0][:1])))
        control_effect = float(np.max(np.abs(finals[1] - finals[0])))
        if row_error > .001 or control_effect < .01:
            raise ValueError(f'robot filtering control thresholds failed: {row_error}, {control_effect}')
        scope = ('source robot/cube cross-environment filter on/off; other bodies inactive' if cross_type
                 else 'source robot cross-environment filter on/off; other bodies inactive')
        return {'status': 'PASS', 'scope': scope,
                'filter_on_max_row_error_rad_or_m': row_error,
                'filter_off_max_difference_rad_or_m': control_effect}
    frozen = np.array([[.90, .40, .80], [.91, .40, .80], [.89, .40, .80]])
    shifts = []
    for trial in trials:
        initial, final = np.asarray(trial['initial_xyz']), np.asarray(trial['final_xyz'])
        if (initial.shape != (3, 3) or final.shape != (3, 3) or trial['native_steps'] != 25
                or not np.allclose(initial, frozen, atol=1e-6, rtol=0)
                or not np.all(final[:, 2] < initial[:, 2])):
            raise ValueError('collision control lacks its frozen initial state, steps, or gravity')
        shifts.append(np.linalg.norm(final[:, :2] - initial[:, :2], axis=1))
    if max(shifts[0]) > 1e-4 or max(shifts[1]) < .005:
        raise ValueError(f'filter on/off control does not meet frozen thresholds: {shifts}')
    return {'status': 'PASS', 'scope': 'same-source cube cross-environment filter on/off; Panda inactive',
            'filter_on_horizontal_m': shifts[0].tolist(), 'filter_off_horizontal_m': shifts[1].tolist()}


def readback_finger_geometry(directory, source_xml):
    """Check public trajectory against an independently compiled source geometry."""
    import mujoco
    import xml.etree.ElementTree as ET

    path, receipt = _receipt(directory)
    source_path = Path(source_xml).resolve(strict=True)
    root = ET.fromstring(source_path.read_bytes())
    keyframes = root.find('keyframe')
    if keyframes is not None:
        root.remove(keyframes)
    world = root.find('worldbody')
    if world is None:
        raise ValueError('source Panda MJCF has no world body')
    cube = ET.SubElement(world, 'body', {'name': 'independent_cube'})
    ET.SubElement(cube, 'freejoint', {'name': 'independent_cube_joint'})
    ET.SubElement(cube, 'geom', {'name': 'independent_cube_geom', 'type': 'box',
                                'size': '.025 .025 .025', 'mass': '.08'})
    compiler = root.find('compiler')
    meshdir = compiler.get('meshdir', '') if compiler is not None else ''
    asset_dir = source_path.parent / meshdir
    assets = {f'{meshdir}/{item.name}': item.read_bytes() for item in asset_dir.iterdir() if item.is_file()}
    model = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding='unicode'), assets=assets)
    data = mujoco.MjData(model)
    names = [f'joint{index}' for index in range(1, 8)] + ['finger_joint1', 'finger_joint2']
    bodies = {model.body('left_finger').id, model.body('right_finger').id}
    fingers = [index for index in range(model.ngeom)
               if int(model.geom_bodyid[index]) in bodies
               and int(model.geom_type[index]) == int(mujoco.mjtGeom.mjGEOM_BOX)
               and (int(model.geom_contype[index]) or int(model.geom_conaffinity[index]))]
    cube_geom = model.geom('independent_cube_geom').id
    table_geom = int(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, 'grasp_table_geom'))
    if not fingers:
        raise ValueError('source contains no finger collision geometry')
    with np.load(path / receipt['source_trajectory']) as trace:
        joints, cube_pose = trace['joint_position'], trace['cube_pose']
    if (joints.ndim != 3 or joints.shape[1:] != (3, 9)
            or cube_pose.shape != (joints.shape[0], 3, 7)):
        raise ValueError('contact trajectory has unexpected shape')
    minimum = []
    table_minimum = []
    for row in range(3):
        best = float('inf')
        table_best = float('inf')
        for tick in range(joints.shape[0]):
            for name, value in zip(names, joints[tick, row], strict=True):
                data.joint(name).qpos[:] = float(value)
            data.joint('independent_cube_joint').qpos[:] = cube_pose[tick, row]
            mujoco.mj_forward(model, data)
            if table_geom >= 0:
                table_best = min(table_best, float(mujoco.mj_geomDistance(model, data, table_geom, cube_geom, .2, None)))
            for geom in fingers:
                distance = float(mujoco.mj_geomDistance(model, data, geom, cube_geom, .2, None))
                best = min(best, distance)
        minimum.append(best)
        table_minimum.append(table_best if table_geom >= 0 else None)
    if minimum[0] > .001:
        raise ValueError(f'aligned finger/cube source geometry never came within 1 mm: {minimum}')
    table_limit = .002
    table_status = ('NOT_AVAILABLE' if any(value is None for value in table_minimum)
                    else 'PASS' if all(value >= -table_limit for value in table_minimum) else 'FAIL')
    return {'status': 'PASS', 'scope': 'source finger/cube geometry over public device trajectory',
            'minimum_distance_m_by_row': minimum, 'contact_distance_tolerance_m': .001,
            'cube_table_minimum_distance_m_by_row': table_minimum,
            'table_stability_status': table_status,
            'table_stability_max_penetration_m': table_limit,
            'table_distance_scope': 'task-scale witness over retained trajectory; not a general CCD guarantee'}


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


def readback_device_recording(directory):
    """Compare existing H5 reader output with values returned by the same run."""
    import h5py
    from task_env.recorders import inspect_trajectory_h5

    path, receipt = _receipt(directory)
    if receipt['recorded_env_ids'] != [0, 1] or not receipt['closed']:
        raise ValueError('selected device recording did not close')
    camera = receipt.get('camera', False)
    witness = None
    if receipt.get('public_boundary_witness'):
        witness = json.loads((path / 'public_record_contexts.json').read_text())
    with np.load(path / 'expected_record_values.npz') as expected:
        checks = [
            ('trajectory_slot_000_episode_000000.h5', 0, 1, 20, 'initial_0', 'final_0'),
            ('trajectory_slot_001_episode_000000.h5', 1, 1, 5, 'initial_1', 'old_1'),
            ('trajectory_slot_001_episode_000001.h5', 1, 2, 16 if camera else 15, 'reset_1', 'last_1'),
        ]
        if camera:
            checks.append(('trajectory_slot_000_episode_000001.h5', 0, 2, 1, 'next_0', 'after_0'))
        for filename, slot, episode, count, first_key, last_key in checks:
            summary = inspect_trajectory_h5(path / filename)
            contexts = summary['boundary_contexts']
            key = Path(filename).stem
            if witness is not None and contexts != witness[key]['contexts']:
                raise ValueError(f'public boundary identity or native clock differs in {filename}')
            if (summary['transition_count'] != count or len(contexts) != count + 1
                    or any(c['env_id'] != slot or c['episode_id'] != episode for c in contexts)
                    or contexts[0]['episode_step'] != 0 or contexts[-1]['episode_step'] != count
                    or len({c['generation'] for c in contexts}) != 1):
                raise ValueError(f'identity or clock mismatch in {filename}')
            with h5py.File(path / filename) as h5:
                values = np.asarray(h5['obs/state/proprioception'])
                if witness is not None:
                    with np.load(path / 'public_record_traces.npz') as public:
                        if not np.array_equal(values, public[key + '__state']):
                            raise ValueError(f'public state trace differs from {filename}')
                        if camera and not np.array_equal(
                                np.asarray(h5['obs/cameras/base/rgb']).transpose(0, 2, 3, 1),
                                public[key + '__rgb']):
                            raise ValueError(f'public camera trace differs from {filename}')
                    for flag in ('terminated', 'truncated'):
                        if np.asarray(h5[flag]).tolist() != witness[key][flag]:
                            raise ValueError(f'public {flag} trace differs from {filename}')
                if not np.array_equal(values[0], expected[first_key]) or not np.array_equal(values[-1], expected[last_key]):
                    raise ValueError(f'public state values differ from {filename}')
                if camera:
                    rgb_chw = np.asarray(h5['obs/cameras/base/rgb'])
                    if rgb_chw.dtype != np.uint8 or rgb_chw.shape[1:] != (3, 128, 128):
                        raise ValueError(f'recorded camera layout differs in {filename}')
                    rgb = rgb_chw.transpose(0, 2, 3, 1)
                    if (rgb.dtype != np.uint8
                            or not np.array_equal(rgb[0], expected[first_key + '_rgb'])
                            or not np.array_equal(rgb[-1], expected[last_key + '_rgb'])):
                        raise ValueError(f'public camera pixels differ from {filename}')
                    if slot == 0 and episode == 1:
                        if (np.asarray(h5['terminated'])[-1] or not np.asarray(h5['truncated'])[-1]):
                            raise ValueError('recorded terminal flags differ from the public transition')
        if np.array_equal(expected['final_0'], expected['next_0']):
            raise ValueError('terminal and new episode observations were not distinguished')
        if camera and np.array_equal(expected['final_0_rgb'], expected['next_0_rgb']):
            raise ValueError('terminal and new episode camera frames were not distinguished')
    return {'status': 'PASS', 'scope': ('two device rows, staggered episodes and CUDA camera pixels'
                                        if camera else 'two selected device state rows and staggered episodes; no RGB'),
            'files': len(checks), 'control_intervals': receipt['control_intervals'],
            'all_public_boundaries_checked': witness is not None}


def readback_observer_fixture(directory, *, mounted=False):
    """Compare H5 pixels, state, flags and clocks against the same fixture returns."""
    import h5py
    from task_env.recorders import inspect_trajectory_h5

    path, receipt = _receipt(directory)
    if mounted:
        receipt = receipt['recording_fixture']
    if (receipt['recorded_env_ids'] != [0, 1] or receipt['control_intervals'] != 20
            or receipt['fixture_transitions'] != 3 or not receipt['closed']):
        raise ValueError('observer fixture receipt differs from its declared scope')
    checks = (
        (0, 0, 1, ('initial', 'next1', 'final2'), (0, 2, 3), (False, True), (False, True)),
        (1, 0, 1, ('initial', 'final1'), (0, 1), (True,), (False,)),
        (1, 1, 2, ('next1', 'next2', 'final3'), (2, 4, 5), (False, False), (False, True)),
        (0, 1, 2, ('next2', 'next3'), (4, 6), (False,), (False,)),
    )
    values_file = 'expected_mounted_values.npz' if mounted else 'expected_observer_values.npz'
    with np.load(path / values_file) as expected:
        for slot, file_episode, episode, names, boundaries, terminated, truncated in checks:
            filename = f'trajectory_slot_{slot:03d}_episode_{file_episode:06d}.h5'
            summary = inspect_trajectory_h5(path / filename)
            contexts = summary['boundary_contexts']
            if (summary['transition_count'] != len(names) - 1 or len(contexts) != len(names)
                    or [entry['env_id'] for entry in contexts] != [slot] * len(names)
                    or [entry['episode_id'] for entry in contexts] != [episode] * len(names)
                    or [entry['episode_step'] for entry in contexts] != list(range(len(names)))
                    or [entry['native_step'] for entry in contexts] != expected['native_steps'][list(boundaries)].tolist()
                    or any(entry['generation'] != int(expected['generation']) for entry in contexts)
                    or not np.allclose([entry['native_time_s'] for entry in contexts],
                                       expected['native_times'][list(boundaries)], rtol=0., atol=1e-12)):
                raise ValueError(f'fixture identity or clock differs in {filename}')
            with h5py.File(path / filename) as h5:
                rgb_path = 'obs/cameras/hand/rgb' if mounted else 'obs/frames/observer_crop/rgb'
                state_path = 'obs/state/hand_position' if mounted else 'obs/state/proprioception'
                rgb = np.asarray(h5[rgb_path]).transpose(0, 2, 3, 1)
                state = np.asarray(h5[state_path])
                if (rgb.dtype != np.uint8
                        or not np.array_equal(rgb, np.stack([expected[f'{name}_rgb'][slot] for name in names]))
                        or not np.array_equal(state, np.stack([expected[f'{name}_state'][slot] for name in names]))
                        or np.asarray(h5['terminated']).tolist() != list(terminated)
                        or np.asarray(h5['truncated']).tolist() != list(truncated)):
                    raise ValueError(f'fixture pixels, state or done flags differ in {filename}')
        for slot, index in ((1, 1), (0, 2), (1, 3)):
            if np.array_equal(expected[f'final{index}_rgb'][slot], expected[f'next{index}_rgb'][slot]):
                raise ValueError('terminal and next-episode frames are identical')
    return {'status': 'PASS', 'scope': ('real Isaac hand-camera pixels and controlled lifecycle; scalar physics'
                                        if mounted else 'real CUDA observer pixels plus controlled lifecycle; not sensor cameras'),
            'files': len(checks), 'recorded_env_ids': [0, 1], 'fixture_transitions': 3}


def readback_formal_frame(directory):
    """Recompute synthetic source-site FK independently from saved qpos."""
    import hashlib
    import xml.etree.ElementTree as ET
    from task_env.artifacts import SceneDefinition

    path, receipt = _receipt(directory)
    if (receipt['frame_names'] != ['pendulum-v1/frame_probe'] or receipt['device'] != 'cuda:0'
            or receipt['native_batch_steps'] != 500 or receipt['world_steps'] != 1500
            or receipt['control_intervals'] != 20 or receipt['seed'] != 73
            or receipt['reset_sampler'] != 'device task lifecycle' or not receipt['closed']
            or receipt['renderer'] != 'geophys-rasterizer' or receipt['repeated_render_advanced_physics']
            or not receipt['all_false_reset_keeps_fields']
            or not receipt['masked_reset_keeps_unselected_frames']):
        raise ValueError('formal frame receipt differs from the bounded source session')
    original = (path / 'frame-source-input.xml').read_bytes()
    projected = (path / 'frame-source-projected.xml').read_bytes()
    scene = SceneDefinition.from_mapping(json.loads((path / 'frame-scene.json').read_text()))
    root = ET.fromstring(original)
    site = root.find(".//body[@name='pendulum_link']/site[@name='frame_probe']")
    if (site is None or site.get('pos') != '.1 0 .3'
            or root.findall('./asset/*[@file]')
            or scene.assets[0].source_content_sha256 != hashlib.sha256(original).hexdigest()
            or receipt['source_id'] != f'scene-definition-v3:{scene.identity_hash}'):
        raise ValueError('saved source XML or declared Scene identity differs')
    manifest = {'schema_version': 'source-closure-v1', 'files': [
        {'path': 'scene.xml', 'size_bytes': len(projected), 'sha256': hashlib.sha256(projected).hexdigest()}]}
    closure = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':'),
                                        allow_nan=False).encode()).hexdigest()
    if closure != receipt['source_closure_sha256']:
        raise ValueError('saved projected XML differs from the source closure identity')
    errors = []
    with np.load(path / 'formal_frame_values.npz') as values:
        for prefix in ('initial', 'final', 'masked'):
            angle = values[f'{prefix}_q'][:, 0].astype(np.float64)
            xyz = values[f'{prefix}_position'][:, 0].astype(np.float64)
            wxyz = values[f'{prefix}_quaternion'][:, 0].astype(np.float64)
            if angle.shape != (3,) or xyz.shape != (3, 3) or wxyz.shape != (3, 4):
                raise ValueError('formal frame publication has an invalid B or pose shape')
            expected_xyz = np.column_stack((.1 * np.cos(angle) + .3 * np.sin(angle),
                                            np.zeros(3), .3 * np.cos(angle) - .1 * np.sin(angle)))
            cy, sy = np.cos(angle / 2), np.sin(angle / 2)
            cz, sz = np.cos(np.pi / 8), np.sin(np.pi / 8)
            expected_wxyz = np.column_stack((cy * cz, sy * sz, sy * cz, cy * sz))
            error = np.minimum(np.max(np.abs(wxyz - expected_wxyz), axis=1),
                               np.max(np.abs(wxyz + expected_wxyz), axis=1)).max()
            errors.extend((float(np.abs(xyz - expected_xyz).max()), float(error)))
        old = values['previous_q'][:, 0].astype(np.float64)
        previous_xyz = np.column_stack((.1 * np.cos(old) + .3 * np.sin(old),
                                        np.zeros(3), .3 * np.cos(old) - .1 * np.sin(old)))
        stale_error = float(np.abs(values['final_position'][:, 0] - previous_xyz).max())
        for field in ('q', 'position', 'quaternion'):
            if (not np.array_equal(values[f'noop_{field}'], values[f'final_{field}'])
                    or not np.array_equal(values[f'masked_{field}'][[0, 2]],
                                          values[f'final_{field}'][[0, 2]])):
                raise ValueError(f'no-op or masked reset changed unselected {field}')
        if not np.array_equal(values['masked_q'][1], values['initial_q'][1]):
            raise ValueError('masked reset did not restore the selected joint state')
        images = (values['initial_image'], values['final_image'])
        if any(image.shape != (480, 640, 3) or image.dtype != np.uint8 for image in images):
            raise ValueError('formal source image contract differs')
        if int(np.count_nonzero(images[0] != images[1])) != receipt['changed_pixel_components']:
            raise ValueError('formal source changed-pixel count differs')
        centers = []
        for image in images:
            rgb = image.astype(np.float32)
            blue = ((rgb[:, :, 2] > 1.18 * rgb[:, :, 0])
                    & (rgb[:, :, 2] > 1.1 * rgb[:, :, 1]) & (rgb[:, :, 0] < 180))
            row = []
            for left, right in ((160, 240), (280, 360), (400, 480)):
                y, x = np.where(blue[:, left:right])
                if len(x) < 5:
                    raise ValueError('a declared world is missing its visible source mesh')
                row.append(float(x.mean() + left))
            centers.append(row)
        if (not centers[0][0] < centers[0][1] < centers[0][2]
                or centers[1][0] <= centers[0][0] + 2
                or centers[1][1] >= centers[0][1] - 2):
            raise ValueError('world placement or independent motion differs')
    if max(errors) > 2e-5 or stale_error < 1e-4:
        raise ValueError(f'formal frame FK or previous-boundary negative control differs: {errors}, {stale_error}')
    return {'status': 'PASS', 'scope': 'source-bound batch session with a synthetic declared site',
            'max_fk_error': max(errors), 'previous_boundary_position_error': stale_error,
            'initial_mesh_centroids_x': centers[0], 'final_mesh_centroids_x': centers[1]}


def _readback_isaac_pose_values(path, receipt):
    """Compare public CUDA pose snapshots to scalar observations from the same run."""
    names = receipt['body_names']
    with np.load(path / 'isaac_pose_values.npz') as values:
        hand, cube = names.index('panda-v1/hand'), names.index('cube-v1/cube')
        movement = float(np.linalg.norm(values['final'][0, hand] - values['initial'][0, hand]))
        errors = []
        for prefix in ('initial', 'final'):
            pos = values[prefix][0, cube]
            quat = values[f'{prefix}_orientation'][0, cube]
            observed = values[f'{prefix}_cube_observation']
            errors.extend((float(np.abs(pos - observed[:3]).max()),
                min(float(np.abs(quat - observed[3:]).max()), float(np.abs(quat + observed[3:]).max()))))
    if (movement < 1e-4 or abs(movement - receipt['hand_displacement_m']) > 1e-6
            or max(errors) > 1e-4 or abs(max(errors) - receipt['cube_public_observation_max_error']) > 1e-6):
        raise ValueError('Isaac device pose differs from the public observation or hand movement')
    return movement, max(errors)


def readback_isaac_window(directory):
    """Check the scalar Isaac, real window and device-pose evidence independently."""
    path, receipt = _receipt(directory)
    window = receipt['window']
    if (receipt['seed'] != 31 or receipt['device'] != 'cuda:0' or not receipt['closed']
            or receipt['renderer'] != 'geophys-rasterizer' or receipt['control_intervals'] != 21
            or receipt['repeated_native_step'] != receipt['initial_native_step']
            or receipt['final_native_step'] - receipt['initial_native_step'] != 100
            or not window['display'] or len(window['xorg_window_ids']) != 1
            or window['sensor_enabled'] or not window['renderer_closed']
            or window['before_close_step'] != receipt['final_native_step']
            or window['after_close_step'] != window['before_close_step']
            or window['after_following_step'] != window['after_close_step'] + 5):
        raise ValueError('Isaac window or physical clock receipt differs')
    movement, cube_error = _readback_isaac_pose_values(path, receipt)
    with np.load(path / 'isaac_device_frames.npz') as values:
        initial, final = values['initial'], values['final']
        if (initial.shape != (480, 640, 3) or initial.dtype != np.uint8
                or final.shape != initial.shape or final.dtype != np.uint8
                or int(np.count_nonzero(initial != final)) != receipt['changed_pixels']
                or receipt['changed_pixels'] == 0):
            raise ValueError('Isaac source device frames differ from the public capture')
    return {'status': 'PASS', 'scope': 'scalar Isaac with sensor off and a real Xorg window',
            'hand_displacement_m': movement, 'cube_public_observation_max_error': cube_error,
            'native_batch_steps': window['after_following_step'] - receipt['initial_native_step'],
            'world_steps': window['after_following_step'] - receipt['initial_native_step'],
            'window_closed_without_physics_change': True}


def readback_isaac_no_window(directory):
    """Verify the sensor-off, renderer-off scalar Isaac resource path."""
    path, receipt = _receipt(directory)
    if (receipt['seed'] != 31 or receipt['device'] != 'cuda:0' or not receipt['closed']
            or receipt['sensor_enabled'] or receipt['window_enabled']
            or not receipt['window_absence_checked'] or receipt['renderer'] is not None
            or receipt['window'] is not None or receipt['control_intervals'] != 20
            or receipt['repeated_native_step'] != receipt['initial_native_step']
            or receipt['final_native_step'] - receipt['initial_native_step'] != 100):
        raise ValueError('Isaac sensor-off, window-off receipt differs')
    movement, cube_error = _readback_isaac_pose_values(path, receipt)
    return {'status': 'PASS', 'scope': 'scalar Isaac with sensor and window off',
            'hand_displacement_m': movement, 'cube_public_observation_max_error': cube_error,
            'native_batch_steps': 100, 'world_steps': 100}


def readback_isaac_mount(directory, *, sensor=False, window=False):
    """Check real device mount composition against an independent rotation library."""
    from scipy.spatial.transform import Rotation

    path, receipt = _receipt(directory)
    mount = receipt['mount_pose_probe']
    if (receipt['seed'] != 31 or receipt['device'] != 'cuda:0' or not receipt['closed']
            or receipt['control_intervals'] != 20 + int(window)
            or receipt['sensor_enabled'] != sensor or receipt['window_enabled'] != window
            or receipt['final_native_step'] - receipt['initial_native_step'] != 100
            or mount['parents'] != ['panda-v1/link0', 'panda-v1/hand']
            or mount['camera_names'] != ['base', 'hand'] or mount['shape'] != [2, 1, 3, 3]
            or mount['grid_shape'] != [2, 3, 3, 3]
            or mount['grid_scope'] != 'one scalar pose repeated for layout; not batch physics'
            or mount['device'] != 'cuda:0'
            or (not sensor and not mount['frame_capture'].startswith('NOT_RUN'))):
        raise ValueError('Isaac mount probe differs from its declared scope')
    _readback_isaac_pose_values(path, receipt)
    errors = []
    names = receipt['body_names']
    with np.load(path / 'camera_mount_values.npz') as values, np.load(path / 'isaac_pose_values.npz') as published:
        offset = values['offset'][0].astype(np.float64)
        if not np.allclose(offset, mount['layout_offset_m'], rtol=0., atol=1e-7):
            raise ValueError('mount layout offset differs from its receipt')
        grid_offsets = values['grid_offsets'].astype(np.float64)
        if not np.array_equal(grid_offsets, [[-.625, -.625, 0.], [.625, -.625, 0.], [-.625, .625, 0.]]):
            raise ValueError('B=3 grid layout differs from its declared row order')
        for boundary in ('initial', 'final'):
            body_positions = values[f'{boundary}_parent_position']
            body_quaternions = values[f'{boundary}_parent_quaternion']
            if (not np.array_equal(body_positions, published[boundary])
                    or not np.array_equal(body_quaternions, published[f'{boundary}_orientation'])):
                raise ValueError('camera mount parents differ from published device poses')
            for index, parent in enumerate(mount['parents']):
                body_index = names.index(parent)
                q = body_quaternions[0, body_index].astype(np.float64)
                local_q = values['spec_quaternion'][index].astype(np.float64)
                parent_rotation = Rotation.from_quat(q[[1, 2, 3, 0]])
                local_rotation = Rotation.from_quat(local_q[[1, 2, 3, 0]])
                position = body_positions[0, body_index] + parent_rotation.apply(values['spec_position'][index])
                rotation = parent_rotation * local_rotation
                expected = np.stack((position, position + rotation.apply([1., 0., 0.]),
                                     rotation.apply([0., 0., 1.])))
                placed = expected.copy()
                placed[:2] += offset
                actual = values[f'{boundary}_local'][index, 0]
                actual_placed = values[f'{boundary}_placed'][index, 0]
                errors.extend((float(np.abs(actual - expected).max()),
                               float(np.abs(actual_placed - placed).max())))
                grid = values[f'{boundary}_grid'][index]
                for row in range(3):
                    expected_row = expected.copy()
                    expected_row[:2] += grid_offsets[row]
                    errors.append(float(np.abs(grid[row] - expected_row).max()))
        base_change = float(np.abs(values['final_local'][0] - values['initial_local'][0]).max())
        hand_change = float(np.linalg.norm(values['final_local'][1, 0, 0] - values['initial_local'][1, 0, 0]))
    if (max(errors) > 2e-5 or base_change > 1e-5 or hand_change < 1e-4
            or abs(base_change - mount['base_max_change']) > 1e-6
            or abs(hand_change - mount['hand_position_change_m']) > 1e-6):
        raise ValueError(f'camera mount FK, offset, or motion differs: {errors}, {base_change}, {hand_change}')
    if sensor:
        if mount['frame_capture'] != 'CUDA sensor frames saved in isaac_sensor_frames.npz':
            raise ValueError('sensor frame receipt is missing')
        with np.load(path / 'isaac_sensor_frames.npz') as frames:
            for name in ('base', 'hand'):
                first, last = frames[f'{name}_initial'], frames[f'{name}_final']
                if (first.shape != (3, 128, 128, 3) or first.dtype != np.uint8
                        or last.shape != first.shape or last.dtype != np.uint8
                        or np.count_nonzero(first != last) == 0
                        or any(len(np.unique(row.reshape(-1, 3), axis=0)) < 10 for row in first)):
                    raise ValueError(f'{name} camera frames lack shape, color or motion')
            if np.array_equal(frames['base_initial'], frames['hand_initial']):
                raise ValueError('base and hand views are identical')
    if window:
        event = receipt['window']
        if (not event['display'] or len(event['xorg_window_ids']) != 1 or not event['sensor_enabled']
                or not event['renderer_closed'] or event['before_close_step'] != event['after_close_step']
                or event['after_following_step'] != event['after_close_step'] + 5):
            raise ValueError('sensor-on window lifecycle or physics clock differs')
    return {'status': 'PASS', 'scope': ('real Isaac poses and mounted CUDA camera frames; scalar physics'
                                        if sensor else 'real Isaac device poses and CameraSpec mounts; no camera frames'),
            'max_pose_error': max(errors), 'base_max_change': base_change,
            'hand_position_change_m': hand_change, 'native_batch_steps': 100 + 5 * int(window),
            'world_steps': 100 + 5 * int(window), 'window': window}


def readback_scalar_camera(directory):
    """Verify the scalar camera's saved images and supervised lifecycle receipt."""
    path, receipt = _receipt(directory)
    if (receipt['shape'] != [128, 128, 3] or receipt['dtype'] != 'torch.uint8'
            or receipt['device'] != 'cuda:0' or receipt['control_intervals'] != 21
            or receipt['native_batch_steps'] != 525 or receipt['world_steps'] != 525
            or not receipt['terminal_snapshot_retained'] or not receipt['closed']):
        raise ValueError('scalar camera lifecycle receipt differs')
    with np.load(path / 'scalar_camera_frames.npz') as frames:
        initial, final, reset = (frames[name] for name in ('initial', 'final', 'reset'))
        if any(frame.shape != (128, 128, 3) or frame.dtype != np.uint8
               or np.unique(frame.reshape(-1, 3), axis=0).shape[0] < 10
               for frame in (initial, final, reset)):
            raise ValueError('scalar camera output does not contain valid color frames')
        if np.array_equal(initial, final) or np.array_equal(final, reset):
            raise ValueError('scalar camera motion or episode boundary is missing')
    return {'status': 'PASS', 'scope': 'scalar CUDA camera images and owned terminal boundary',
            'control_intervals': 21, 'native_batch_steps': 525, 'world_steps': 525}


def readback_pickcube_recording(directory):
    """Compare every saved PickCube state boundary with public-return witnesses."""
    import h5py
    from task_env.recorders import inspect_trajectory_h5

    path, receipt = _receipt(directory)
    if receipt['recorded_env_ids'] != [0, 1] or not receipt['closed']:
        raise ValueError('PickCube recorder did not close the selected rows')
    contexts = json.loads((path / 'pickcube_public_contexts.json').read_text())
    components = receipt.get('action_components')
    checked = 0
    camera_boundaries = {}
    with np.load(path / 'pickcube_public_traces.npz') as traces:
        for filename in receipt['files']:
            name = Path(filename).stem
            summary = inspect_trajectory_h5(path / filename)
            if summary['boundary_contexts'] != contexts[name]:
                raise ValueError(f'boundary identity or clock differs in {filename}')
            for context in contexts[name]:
                if 'native_world_time_s' in context:
                    expected_time = context['episode_step'] * context['control_dt_s']
                    if abs(context['native_world_time_s'] - expected_time) > 1e-5:
                        raise ValueError(f'native world clock differs from its episode boundary in {filename}')
            with h5py.File(path / filename) as h5:
                if components is None:
                    legacy = [name for name in ('finger-tendon-effort', 'finger-pair-effort')
                              if name in h5['action']]
                    if len(legacy) != 1:
                        raise ValueError('legacy PickCube recording has ambiguous finger action metadata')
                    components = [f'arm-effort-{index}' for index in range(1, 8)] + legacy
                if set(components) != set(h5['action']):
                    raise ValueError(f'action metadata differs in {filename}')
                for key in ('ee_pose', 'joint_position', 'hand_pose', 'cube_v1_body_pose'):
                    group = 'privileged_state' if key == 'cube_v1_body_pose' else 'state'
                    if not np.array_equal(h5[f'obs/{group}/{key}'][...], traces[name + '__' + key]):
                        raise ValueError(f'public {key} differs in {filename}')
                for camera in receipt.get('cameras_recorded', []):
                    recorded_rgb = h5[f'obs/cameras/{camera}/rgb'][...].transpose(0, 2, 3, 1)
                    if not np.array_equal(recorded_rgb,
                                          traces[name + '__' + camera + '_rgb']):
                        raise ValueError(f'public {camera} RGB differs in {filename}')
                    camera_boundaries[(name, camera)] = (recorded_rgb[0].copy(), recorded_rgb[-1].copy())
                if 'boundary_identity_sha256' in h5['obs/state']:
                    raise ValueError('canonical recording unexpectedly contains the legacy digest leaf')
                expected_action = traces[name + '__action']
                actual_action = np.concatenate([h5[f'action/{key}'][...] for key in components], axis=1)
                if not np.array_equal(actual_action, expected_action):
                    raise ValueError(f'public actions differ in {filename}')
                for key in ('reward', 'terminated', 'truncated'):
                    actual = h5[key][...]
                    expected = traces[name + '__' + key].astype(actual.dtype)
                    if not np.array_equal(actual, expected):
                        raise ValueError(f'public {key} differs in {filename}')
                checked += len(contexts[name])
    transitions_checked = 0
    for name, rows in contexts.items():
        if not rows:
            continue
        current = rows[-1]
        successor = next((other for other, values in contexts.items()
                          if values and values[0]['env_id'] == current['env_id']
                          and values[0]['episode_id'] == current['episode_id'] + 1), None)
        if successor is None:
            continue
        for camera in receipt.get('cameras_recorded', []):
            if np.array_equal(camera_boundaries[(name, camera)][1], camera_boundaries[(successor, camera)][0]):
                raise ValueError(f'{camera} image did not change across episode boundary for {name}')
            transitions_checked += 1
    return {'status': 'PASS', 'scope': 'PickCube device H5 independent readback',
            'cameras_checked': receipt.get('cameras_recorded', []),
            'terminal_or_reset_camera_pairs_checked': transitions_checked,
            'files': len(receipt['files']), 'checked_boundaries': checked}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ipc')
    parser.add_argument('--physics')
    parser.add_argument('--raster')
    parser.add_argument('--formal')
    parser.add_argument('--example')
    parser.add_argument('--record')
    parser.add_argument('--pickcube-record')
    parser.add_argument('--pickcube-fk')
    parser.add_argument('--pickcube-projection')
    parser.add_argument('--projection-phase', choices=('initial', 'final'), default='initial')
    parser.add_argument('--isaac-filter')
    parser.add_argument('--finger-geometry')
    parser.add_argument('--source-xml')
    parser.add_argument('--observer-fixture')
    parser.add_argument('--mounted-fixture')
    parser.add_argument('--frame-session')
    parser.add_argument('--isaac-window')
    parser.add_argument('--isaac-no-window')
    parser.add_argument('--isaac-mount')
    parser.add_argument('--isaac-sensor')
    parser.add_argument('--sensor-window', action='store_true')
    parser.add_argument('--scalar-camera')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.finger_geometry:
        if not args.source_xml or any((args.isaac_filter, args.pickcube_projection, args.pickcube_fk,
                args.pickcube_record, args.scalar_camera, args.mounted_fixture, args.isaac_sensor,
                args.isaac_mount, args.isaac_no_window, args.isaac_window, args.frame_session,
                args.observer_fixture, args.record, args.ipc, args.physics, args.raster,
                args.formal, args.example, args.sensor_window)):
            parser.error('--finger-geometry requires --source-xml and cannot be mixed with other readbacks')
        result = readback_finger_geometry(args.finger_geometry, args.source_xml)
    elif args.isaac_filter:
        if any((args.pickcube_projection, args.pickcube_fk, args.source_xml, args.pickcube_record,
                args.scalar_camera, args.mounted_fixture, args.isaac_sensor, args.isaac_mount,
                args.isaac_no_window, args.isaac_window, args.frame_session, args.observer_fixture,
                args.record, args.ipc, args.physics, args.raster, args.formal, args.example, args.sensor_window)):
            parser.error('--isaac-filter cannot be mixed with other readbacks')
        result = readback_isaac_filter(args.isaac_filter)
    elif args.pickcube_projection:
        if any((args.pickcube_fk, args.source_xml, args.pickcube_record, args.scalar_camera,
                args.mounted_fixture, args.isaac_sensor, args.isaac_mount, args.isaac_no_window,
                args.isaac_window, args.frame_session, args.observer_fixture, args.record,
                args.ipc, args.physics, args.raster, args.formal, args.example, args.sensor_window)):
            parser.error('--pickcube-projection cannot be mixed with other readbacks')
        result = readback_pickcube_projection(args.pickcube_projection, phase=args.projection_phase)
    elif args.pickcube_fk:
        if not args.source_xml or any((args.pickcube_record, args.scalar_camera, args.mounted_fixture,
                args.isaac_sensor, args.isaac_mount, args.isaac_no_window, args.isaac_window,
                args.frame_session, args.observer_fixture, args.record, args.ipc, args.physics,
                args.raster, args.formal, args.example, args.sensor_window)):
            parser.error('--pickcube-fk requires --source-xml and cannot be mixed with other readbacks')
        result = readback_pickcube_fk(args.pickcube_fk, args.source_xml)
    elif args.pickcube_record:
        if any((args.scalar_camera, args.mounted_fixture, args.isaac_sensor, args.isaac_mount,
                args.isaac_no_window, args.isaac_window, args.frame_session,
                args.observer_fixture, args.record, args.ipc, args.physics, args.raster,
                args.formal, args.example, args.sensor_window)):
            parser.error('--pickcube-record cannot be mixed with other readbacks')
        result = readback_pickcube_recording(args.pickcube_record)
    elif args.scalar_camera:
        if any((args.mounted_fixture, args.isaac_sensor, args.isaac_mount, args.isaac_no_window,
                args.isaac_window, args.frame_session, args.observer_fixture, args.record,
                args.ipc, args.physics, args.raster, args.formal, args.example, args.sensor_window)):
            parser.error('--scalar-camera cannot be mixed with other readbacks')
        result = readback_scalar_camera(args.scalar_camera)
    elif args.mounted_fixture:
        if any((args.isaac_sensor, args.isaac_mount, args.isaac_no_window, args.isaac_window,
                args.frame_session, args.observer_fixture, args.record, args.ipc, args.physics,
                args.raster, args.formal, args.example)):
            parser.error('--mounted-fixture cannot be mixed with other readbacks')
        result = readback_observer_fixture(args.mounted_fixture, mounted=True)
    elif args.isaac_sensor:
        if any((args.isaac_mount, args.isaac_no_window, args.isaac_window, args.frame_session,
                args.observer_fixture, args.record, args.ipc, args.physics, args.raster, args.formal, args.example)):
            parser.error('--isaac-sensor cannot be mixed with other readbacks')
        result = readback_isaac_mount(args.isaac_sensor, sensor=True, window=args.sensor_window)
    elif args.isaac_mount:
        if any((args.isaac_no_window, args.isaac_window, args.frame_session, args.observer_fixture,
                args.record, args.ipc, args.physics, args.raster, args.formal, args.example)):
            parser.error('--isaac-mount cannot be mixed with other readbacks')
        result = readback_isaac_mount(args.isaac_mount)
    elif args.isaac_no_window:
        if any((args.isaac_window, args.frame_session, args.observer_fixture, args.record, args.ipc,
                args.physics, args.raster, args.formal, args.example)):
            parser.error('--isaac-no-window cannot be mixed with other readbacks')
        result = readback_isaac_no_window(args.isaac_no_window)
    elif args.isaac_window:
        if any((args.frame_session, args.observer_fixture, args.record, args.ipc, args.physics,
                args.raster, args.formal, args.example)):
            parser.error('--isaac-window cannot be mixed with other readbacks')
        result = readback_isaac_window(args.isaac_window)
    elif args.frame_session:
        if any((args.observer_fixture, args.record, args.ipc, args.physics, args.raster, args.formal, args.example)):
            parser.error('--frame-session cannot be mixed with other readbacks')
        result = readback_formal_frame(args.frame_session)
    elif args.observer_fixture:
        if any((args.record, args.ipc, args.physics, args.raster, args.formal, args.example)):
            parser.error('--observer-fixture cannot be mixed with other readbacks')
        result = readback_observer_fixture(args.observer_fixture)
    elif args.record:
        if any((args.ipc, args.physics, args.raster, args.formal, args.example)):
            parser.error('--record cannot be mixed with the original combined readback')
        result = readback_device_recording(args.record)
    else:
        if not all((args.ipc, args.physics, args.raster, args.formal, args.example)):
            parser.error('provide all original run directories or --record')
        result = readback(args.ipc, args.physics, args.raster, args.formal, args.example)
    Path(args.output).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
