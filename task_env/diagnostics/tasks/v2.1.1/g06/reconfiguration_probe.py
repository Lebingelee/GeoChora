"""Slim native probe for G06c partial reset and whole-batch reconfiguration.

The probe exercises only public batch APIs: ``make_parallel_env``,
``env.reset``/``env.step``/``env.render``, ``env.read_device_state``,
``env.robot`` and the existing ``VectorTransitionRecorder``.  It never reads
provider-private solver or renderer state.

Each invocation is one supervised native run; the shared G06 supervisor owns
the lock, per-run working directory and resource observation.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path

import numpy as np
import torch

import task_env.tasks  # noqa: F401  (replays the public task registrations)
from task_env import make_parallel_env
from task_env.recorders import VectorTransitionRecorder


TASK_UIDS = {
    'pendulum': 'pendulum-v1',
    'pick-cube': 'pick-cube-p16-reference-v1',
}


def _pickcube_cameras():
    yaw, pitch = .45, .30
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    return [
        {'name': 'base', 'frame': 'body', 'parent': 'panda-v1/link0',
         'width': 128, 'height': 128, 'rgb_dtype': 'uint8',
         'position': [-.35, -.4, .8],
         'quaternion_wxyz': [cy * cp, -sy * sp, cy * sp, sy * cp],
         'near': .01, 'far': 3.},
        {'name': 'hand', 'frame': 'body', 'parent': 'panda-v1/hand',
         'width': 128, 'height': 128, 'rgb_dtype': 'uint8',
         'position': [.075, 0., -.15],
         'quaternion_wxyz': [math.sqrt(.5), 0., -math.sqrt(.5), 0.],
         'near': .01, 'far': 3.},
    ]


def _config(task, provider, interpreter, *, seed, horizon, cameras):
    execution = {'physics_provider': provider}
    if interpreter:
        execution['interpreter'] = interpreter
    if provider == 'geophys':
        execution['geophys_contact_mode'] = 'discrete'
    config = {'execution': execution,
              'episode': {'seed': seed, 'horizon': horizon}}
    if task == 'pick-cube':
        config['controller'] = {'profile_id': 'panda-direct-effort-v1'}
        config['robot'] = {'native_drive': 'disabled'}
        if provider == 'geophys':
            config['runtime'] = {'body_contact_solver_iterations': 32}
        if cameras:
            config['render'] = {'backend': 'rasterizer', 'camera_obs': True,
                                'cameras': _pickcube_cameras()}
    return config


def _build(task, provider, interpreter, *, seed, horizon, cameras, render_mode,
           output):
    directory = None if output is None else str(Path(output).resolve().parent)
    return make_parallel_env(
        TASK_UIDS[task],
        env_config=_config(task, provider, interpreter, seed=seed,
                           horizon=horizon, cameras=cameras),
        num_env=3, backend='cuda', execution='device',
        render_mode=render_mode, worker_directory=directory)


def _action(env, task, tick, batch=3, sign=1.0, offset=0.0):
    if task == 'pendulum':
        values = torch.tensor(
            [[sign * (0.2 + 0.3 * ((row + tick) % 3)) + offset]
             for row in range(batch)],
            dtype=torch.float32, device='cuda')
        return {'torque': values}
    shape = tuple(env.single_action_space['effort'].shape)
    values = torch.zeros((batch, *shape), dtype=torch.float32, device='cuda')
    rows = torch.arange(batch, device='cuda')
    values[:, 0] = sign * (0.3 + 0.2 * ((rows + tick) % 3))
    values[:, -1] = sign * 0.1 * ((rows + tick) % 2)
    return {'effort': values}


def _read(env):
    names = tuple(env.resource_summary()['device_transition']['state_shapes'])
    state = env.read_device_state(names)
    result = {name: state.arrays[name].detach().clone() for name in names}
    result['identity'] = asdict(state.identity)
    return result


def _pixel_diff(left, right, row):
    difference = (left[row].to(torch.int16) - right[row].to(torch.int16)).abs()
    return {'max_abs': int(difference.max().item()),
            'changed': int((difference > 0).any(dim=-1).sum().item()),
            'pixels': int(difference.shape[0] * difference.shape[1])}


def _diff_rows(left, right, left_row, right_row):
    difference = (left[left_row].to(torch.int16)
                  - right[right_row].to(torch.int16)).abs()
    return {'max_abs': int(difference.max().item()),
            'changed': int((difference > 0).any(dim=-1).sum().item())}


def _cuda_mask(rows, batch=3):
    value = torch.zeros(batch, dtype=torch.bool, device='cuda')
    for row in rows:
        value[row] = True
    return value


def _rgb(observation):
    cameras = observation.get('cameras') or {}
    if 'base' not in cameras:
        return None
    return {name: cameras[name]['rgb'].detach().clone() for name in ('base', 'hand')}


def _same_rgb(left, right):
    return left.keys() == right.keys() and all(torch.equal(left[key], right[key]) for key in left)


def _jsonable(value):
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().tolist()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.generic,)):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _write(output, name, payload):
    if output is None:
        return
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.with_name(name).write_text(json.dumps(_jsonable(payload), indent=2) + '\n')


# --------------------------------------------------------------------------- C1


def _state_keys(state):
    return tuple(name for name in state if name != 'identity')


def _same_arrays(left, right):
    return all(torch.equal(left[name], right[name])
               for name in _state_keys(left))


def _same_rows(left, right, rows):
    return all(torch.equal(left[name][row], right[name][row])
               for name in _state_keys(left) for row in rows)


def run_partial(args):
    """All-false, single-row and non-adjacent partial reset with a fresh control.

    Each branch is a fresh batch with the same seed, so the no-reset control
    and the treatment share one native clock origin instead of comparing two
    positions in one cumulative provider counter.
    """

    seed, prefix, horizon = 31, 4, 64
    camera = args.task == 'pick-cube'
    checks, facts = [], {'pixels': []}

    def make_env():
        return _build(args.task, args.provider, args.interpreter, seed=seed,
                      horizon=horizon, cameras=camera, render_mode=None,
                      output=args.output)

    def replay(env):
        env.reset(seed=seed)
        observation, info = None, None
        for tick in range(prefix):
            observation, _, _, _, info = env.step(
                _action(env, args.task, tick))
        return _read(env), _rgb(observation), info

    def require(name, condition, detail=None):
        checks.append({'check': name, 'passed': bool(condition),
                       'detail': detail})

    control = make_env()
    try:
        control_boundary, control_rgb, control_info = replay(control)
        control_episode = control_info['episode_id'].detach().clone()
        obs_control, _, _, _, _ = control.step(
            _action(control, args.task, prefix))
        control_next = _read(control)
        control_next_rgb = _rgb(obs_control)
        # Control reset of row 1 gives the expected later sample for that row.
        control.reset(mask=_cuda_mask((1,)))
        control_row1 = _read(control)
    finally:
        control.close()

    # All-false branch.
    env = make_env()
    try:
        before, before_rgb, before_info = replay(env)
        before_episode = before_info['episode_id'].detach().clone()
        require('fresh batch replay matches control arrays',
                _same_arrays(before, control_boundary))
        if camera:
            require('fresh batch camera matches control',
                    _same_rgb(before_rgb, control_rgb))
        obs, info = env.reset(mask=_cuda_mask(()))
        applied = _read(env)
        require('all-false keeps all state fields',
                _same_arrays(applied, before))
        require('all-false keeps native step',
                applied['identity']['native_step']
                == before['identity']['native_step'])
        require('all-false keeps episode ids',
                torch.equal(info['episode_id'], before_episode))
        if camera:
            require('all-false keeps camera rows',
                    _same_rgb(_rgb(obs), before_rgb))
        obs_after, _, _, _, _ = env.step(_action(env, args.task, prefix))
        after = _read(env)
        require('all-false response matches no-reset control',
                _same_arrays(after, control_next))
        if camera:
            require('all-false next frame matches control',
                    _same_rgb(_rgb(obs_after), control_next_rgb))
    finally:
        env.close()

    cases = [('single', (1,)), ('non-adjacent', (0, 2))]
    for name, selected in cases:
        env = make_env()
        isolated = None
        try:
            before, before_rgb, before_info = replay(env)
            isolated_before = None
            isolated_row = 0 if name == 'single' else 1
            if args.camera_attribution:
                from task_env.render.rasterizer.device import DeviceBatchRasterSource
                adapter = env._task_spec
                provider = adapter.parallel_render_provider
                isolated = DeviceBatchRasterSource(
                    runtime=adapter.runtime, source=adapter._source_resources[0],
                    cameras=adapter._device_camera_specs)
                isolated_args = dict(world_ids=(isolated_row,),
                                     world_transforms=provider.world_transforms[isolated_row:isolated_row + 1],
                                     width=640, height=480)
                state = env.read_device_state(('body_position', 'body_orientation'))
                isolated_before = isolated.capture_cameras(state=state, **isolated_args)
            before_episode = before_info['episode_id'].detach().clone()
            obs, info = env.reset(mask=_cuda_mask(selected))
            applied = _read(env)
            if isolated_before is not None:
                state = env.read_device_state(('body_position', 'body_orientation'))
                isolated_after = isolated.capture_cameras(state=state, **isolated_args)
                isolated_equal = {camera: torch.equal(isolated_before[camera]['rgb'],
                                                       isolated_after[camera]['rgb'])
                                  for camera in ('base', 'hand')}
                full_diff = {camera: _pixel_diff(obs['cameras'][camera]['rgb'],
                                                before_rgb[camera], isolated_row)
                             for camera in ('base', 'hand')}
                facts.setdefault('camera_attribution', []).append({
                    'branch': name, 'isolated_row': isolated_row,
                    'isolated_equal': isolated_equal, 'full_scene_difference': full_diff})
                require(f'{name} isolated unselected cameras unchanged',
                        all(isolated_equal.values()))
            applied_episode = info['episode_id'].detach().clone()
            applied_step = info['episode_step'].detach().clone()
            unselected = tuple(row for row in range(3) if row not in selected)
            require(f'{name} unselected state fields unchanged',
                    _same_rows(applied, before, unselected))
            require(f'{name} selected qpos changed',
                    all((applied['qpos'][row] != before['qpos'][row]).any()
                        for row in selected))
            require(f'{name} episode ids advance only selected',
                    all(int(applied_episode[row]) == int(before_episode[row])
                        for row in unselected)
                    and all(int(applied_episode[row])
                            == int(before_episode[row]) + 1
                            for row in selected))
            require(f'{name} selected episode clock restarts',
                    all(int(applied_step[row]) == 0 for row in selected)
                    and all(int(applied_step[row]) == prefix
                            for row in unselected))
            if camera:
                frames = _rgb(obs)
                obs_ref, _ = env.reset(mask=_cuda_mask(()))
                frames_ref = _rgb(obs_ref)
                for camera_name, frame in frames.items():
                    previous = before_rgb[camera_name]
                    diffs = {row: _pixel_diff(frame, previous, row) for row in range(3)}
                    matrix = [[{'after_row': left_row, 'before_row': right_row,
                                **_diff_rows(frame, previous, left_row, right_row)}
                               for right_row in range(3)] for left_row in range(3)]
                    repeat_stable = torch.equal(frames_ref[camera_name], frame)
                    own_row_minimal = all(
                        matrix[row][row]['changed'] < min(
                            matrix[row][other]['changed'] for other in range(3) if other != row)
                        for row in unselected)
                    facts['pixels'].extend({'branch': name, 'camera': camera_name,
                                            'row': row, **diffs[row]} for row in unselected)
                    for row in unselected:
                        if diffs[row]['changed']:
                            np.savez_compressed(
                                Path(args.output).resolve().parent /
                                f'camera-{name}-{camera_name}-row{row}.npz',
                                before=previous[row].detach().cpu().numpy(),
                                after=frame[row].detach().cpu().numpy())
                    facts.setdefault('camera_matrix', []).append({
                        'branch': name, 'camera': camera_name,
                        'selected': list(selected), 'rows': matrix})
                    require(f'{name} {camera_name} unselected row keeps its identity', own_row_minimal)
                    require(f'{name} {camera_name} repeated same-state render is stable', repeat_stable)
                    require(f'{name} {camera_name} unselected pixels unchanged or explained by shared scene',
                            all(torch.equal(frame[row], previous[row]) or (
                                isolated_before is not None and row == isolated_row
                                and isolated_equal[camera_name] and repeat_stable)
                                for row in unselected))
            obs_next, _, _, _, _ = env.step(_action(env, args.task, prefix))
            stepped = _read(env)
            require(f'{name} unselected next response matches control',
                    _same_rows(stepped, control_next, unselected))
        finally:
            if isolated is not None:
                isolated.close()
            env.close()

    # The non-adjacent reset must not advance row 1's reset stream.
    env = make_env()
    try:
        replay(env)
        env.reset(mask=_cuda_mask((0, 2)))
        env.step(_action(env, args.task, prefix))
        env.reset(mask=_cuda_mask((1,)))
        later_row1 = _read(env)
        require('unselected row reset stream is unchanged',
                _same_rows(later_row1, control_row1, (1,)))
    finally:
        env.close()

    facts.update({'task': args.task, 'provider': args.provider,
                  'prefix_steps': prefix, 'checks': checks})
    _write(args.output, 'partial.json', facts)
    return facts


# --------------------------------------------------------------------------- C2


def run_rng_sequence(args):
    """Compare several later row samples with and without other-row resets."""
    samples = []
    for perturb in (False, True):
        env = _build(args.task, args.provider, args.interpreter, seed=31,
                     horizon=64, cameras=False, render_mode=None, output=args.output)
        try:
            env.reset(seed=31)
            for tick in range(4):
                env.step(_action(env, args.task, tick))
            if perturb:
                env.reset(mask=_cuda_mask((0, 2)))
            env.step(_action(env, args.task, 4))
            rows = []
            for _ in range(3):
                env.reset(mask=_cuda_mask((1,)))
                state = _read(env)
                rows.append({name: state[name][1].detach().clone()
                             for name in _state_keys(state)})
            samples.append(rows)
        finally:
            env.close()
    checks = [{'check': f'later reset sample {index + 1} matches control',
               'passed': all(torch.equal(left[key], right[key]) for key in left)}
              for index, (left, right) in enumerate(zip(*samples, strict=True))]
    facts = {'provider': args.provider, 'task': args.task, 'checks': checks}
    _write(args.output, 'rng-sequence.json', facts)
    return facts


def run_staggered(args):
    """Staggered horizon endings and same-step autoreset on PickCube."""

    seed, horizon = 31, 4
    env = _build('pick-cube', args.provider, args.interpreter, seed=seed,
                 horizon=horizon, cameras=True, render_mode=None,
                 output=args.output)
    out = Path(args.output).resolve().parent
    recorder = VectorTransitionRecorder(env, path=out, env_ids=(0, 1))
    checks, facts, endings = [], {}, []
    pending = {}
    traces, contexts, segment = {}, {}, [0, 0, 0]

    def boundary(slot, observation, info):
        name = f'trajectory_slot_{slot:03d}_episode_{segment[slot]:06d}'
        entry = traces.setdefault(name, {key: [] for key in (
            'ee_pose', 'joint_position', 'hand_pose', 'cube_v1_body_pose',
            'base_rgb', 'hand_rgb', 'action', 'reward', 'terminated', 'truncated')})
        for key in ('ee_pose', 'joint_position', 'hand_pose'):
            entry[key].append(observation['state'][key][slot].detach().cpu().numpy().copy())
        entry['cube_v1_body_pose'].append(
            observation['privileged_state']['cube_v1_body_pose'][slot].detach().cpu().numpy().copy())
        for camera in ('base', 'hand'):
            entry[camera + '_rgb'].append(
                observation['cameras'][camera]['rgb'][slot].detach().cpu().numpy().copy())
        context = {'schema_version': 'device-batch-boundary-v1',
                   'env_id': int(info['env_id'][slot]),
                   'episode_id': int(info['episode_id'][slot]),
                   'episode_step': int(info['episode_step'][slot]),
                   **asdict(info['boundary'])}
        if 'native_world_time' in info:
            context['native_world_time_s'] = float(info['native_world_time'][slot])
        contexts.setdefault(name, []).append(context)
        return entry

    def recorded_step(tick):
        action = _action(env, 'pick-cube', tick)
        observation, reward, terminated, truncated, info = recorder.step(action)
        for slot in (0, 1):
            ended = bool(terminated[slot] or truncated[slot])
            entry = boundary(slot, info['final_observation'] if ended else observation,
                             info['final_info'] if ended else info)
            entry['action'].append(action['effort'][slot].detach().cpu().numpy().copy())
            entry['reward'].append(float(reward[slot]))
            entry['terminated'].append(bool(terminated[slot]))
            entry['truncated'].append(bool(truncated[slot]))
            if ended:
                segment[slot] += 1
                boundary(slot, observation, info['reset_info'])
        return observation, reward, terminated, truncated, info

    def require(name, condition, detail=None):
        checks.append({'check': name, 'passed': bool(condition),
                       'detail': detail})

    try:
        observation, info = recorder.reset(seed=seed)
        for slot in (0, 1):
            boundary(slot, observation, info)
        native_steps = [_read(env)['identity']['native_step']]
        native_delta = None
        for tick in range(0, 9):
            if tick == 1:  # row 0 starts its horizon one tick late
                observation, info = recorder.reset(mask=_cuda_mask((0,)))
                segment[0] += 1
                boundary(0, observation, info)
            if tick == 3:  # row 1 starts its horizon after row 0
                observation, info = recorder.reset(mask=_cuda_mask((1,)))
                segment[1] += 1
                boundary(1, observation, info)
            old_episode = info['episode_id'].detach().clone()
            old_step = info['episode_step'].detach().clone()
            observation, reward, terminated, truncated, info = recorded_step(tick)
            native_steps.append(_read(env)['identity']['native_step'])
            done = torch.logical_or(terminated, truncated)
            delta = native_steps[-1] - native_steps[-2]
            require(f'tick {tick} shared native clock advances by one control '
                    'interval and no extra row step',
                    delta >= 1 and (native_delta is None or delta == native_delta))
            native_delta = delta if native_delta is None else native_delta
            # Frames saved at an earlier tick must survive the reused buffer.
            for row, saved in list(pending.items()):
                expected, reference = saved
                require(f'tick {tick} row {row} owned terminal frame survives',
                        torch.equal(reference, expected)
                        and not torch.equal(expected[row],
                                            observation['cameras']['base']['rgb'][row]))
                del pending[row]
            for row in range(3):
                if not bool(done[row]):
                    require(f'tick {tick} row {row} continues identity',
                            int(info['episode_id'][row]) == int(old_episode[row]))
                    continue
                final = info['final_observation']
                final_rgb = final['cameras']['base']['rgb']
                expected = final_rgb.clone()
                new_rgb = observation['cameras']['base']['rgb']
                require(f'tick {tick} row {row} same-step final mask',
                        bool(info['_final_observation'][row]))
                require(f'tick {tick} row {row} old/new episode identity',
                        int(info['final_episode_id'][row]) == int(old_episode[row])
                        and int(info['episode_id'][row]) == int(old_episode[row]) + 1
                        and int(info['reset_info']['episode_id'][row])
                        == int(old_episode[row]) + 1)
                require(f'tick {tick} row {row} old terminal clock retained',
                        int(info['final_episode_step'][row])
                        == int(old_step[row]) + 1)
                require(f'tick {tick} row {row} reset clock restarts',
                        int(info['episode_step'][row]) == 0)
                require(f'tick {tick} row {row} new first frame differs',
                        not torch.equal(expected[row], new_rgb[row]))
                require(f'tick {tick} row {row} terminal clock equals horizon',
                        int(old_step[row]) + 1 == horizon)
                endings.append({
                    'tick': tick, 'row': row,
                    'terminated': bool(terminated[row]),
                    'truncated': bool(truncated[row]),
                    'old_episode': int(old_episode[row]),
                    'old_step': int(old_step[row]),
                    'new_episode': int(info['episode_id'][row]),
                })
                pending[row] = (expected, final_rgb)
        # One later step proves the last owned terminal frame survives buffer reuse.
        if pending:
            observation, reward, terminated, truncated, info = recorded_step(9)
            for row, saved in list(pending.items()):
                expected, reference = saved
                require(f'post-loop row {row} owned terminal frame survives',
                        torch.equal(reference, expected)
                        and not torch.equal(expected[row],
                                            observation['cameras']['base']['rgb'][row]))
                del pending[row]
        require('staggered endings cover separate ticks',
                len({entry['tick'] for entry in endings}) >= 2)
        require('at least one row ended while others continued',
                any(entry['tick'] < 9 for entry in endings))
        require('owned terminal frames were checked after a later step',
                not pending)
        facts.update({'provider': args.provider, 'horizon': horizon,
                      'endings': endings, 'checks': checks})
    finally:
        recorder.close()
    recorded_names = {path.stem for path in recorder.saved_paths}
    traces = {name: value for name, value in traces.items() if name in recorded_names}
    contexts = {name: value for name, value in contexts.items() if name in recorded_names}
    np.savez_compressed(out / 'pickcube_public_traces.npz', **{
        name + '__' + key: np.asarray(value) for name, trace in traces.items()
        for key, value in trace.items() if value})
    (out / 'pickcube_public_contexts.json').write_text(json.dumps(contexts, indent=2) + '\n')
    facts.update({'recorded_env_ids': [0, 1], 'closed': True,
                  'files': [path.name for path in recorder.saved_paths],
                  'action_components': list(env.metadata['action_schema']['components']),
                  'cameras_recorded': ['base', 'hand']})
    _write(args.output, 'staggered.json', facts)
    return facts


# --------------------------------------------------------------------------- C3


def _metadata_facts(env):
    metadata = env.get_record_metadata()
    device = metadata.get('device_execution', {})
    return {'provider': device.get('provider'),
            'generation': device.get('generation'),
            'env_provider': metadata.get('env_metadata', {}).get('physics_provider')}


def _view_rejected(view, state):
    """Return whether a saved view/state pair is rejected by its owner."""

    try:
        view.joint_positions(state)
    except (ValueError, RuntimeError):
        return True
    return False


def run_switch(args):
    """Isaac -> MJWarp -> Isaac for one task with recorded H5 segments."""

    seed, steps = 31, 3
    out = Path(args.output).resolve().parent
    out.mkdir(parents=True, exist_ok=True)
    env = _build(args.task, 'isaacsim', args.interpreter, seed=seed, horizon=64,
                 cameras=args.task == 'pick-cube', render_mode='human',
                 output=args.output)
    recorder = VectorTransitionRecorder(
        env, path=out, env_ids=(0, 1, 2),
        name_prefix=f"{args.task.replace('-', '_')}_switch")
    facts = {'task': args.task, 'segments': [], 'h5': [], 'checks': []}
    witness = {}

    def save_tree(prefix, value):
        if isinstance(value, dict):
            for key, child in value.items():
                save_tree(f'{prefix}__{key}', child)
        elif isinstance(value, torch.Tensor):
            witness.setdefault(prefix, []).append(value.detach().cpu().numpy().copy())

    def require(name, condition, detail=None):
        facts['checks'].append({'check': name, 'passed': bool(condition),
                               'detail': detail})

    def display_does_not_advance(label):
        before = _read(env)['identity']['native_step']
        env.render()
        middle = _read(env)['identity']['native_step']
        env.render()
        after = _read(env)['identity']['native_step']
        require(f'{label} display does not advance physics',
                before == middle == after)

    def segment(label, action_sign):
        kwargs = {}
        if label == 'A1':
            kwargs['seed'] = seed
        else:
            target = 'mujoco_warp' if label == 'B' else 'isaacsim'
            kwargs['options'] = {'execution': {'physics_provider': target}}
        observation, info = recorder.reset(**kwargs)
        facts['segments'].append({
            'label': label, 'metadata': _metadata_facts(env),
            'episode_id': info['episode_id'].detach().cpu().tolist()})
        save_tree(f'{label}__obs', observation)
        for tick in range(steps):
            action = _action(env, args.task, tick, sign=action_sign,
                             offset=0.1 * action_sign)
            observation, reward, terminated, truncated, info = recorder.step(action)
            save_tree(f'{label}__obs', observation)
            save_tree(f'{label}__action', action)
            for key, value in (('reward', reward), ('terminated', terminated),
                               ('truncated', truncated)):
                save_tree(f'{label}__{key}', value)
        state = _read(env)
        require(f'{label} native state is finite',
                bool(torch.isfinite(state['qpos']).all())
                and bool(torch.isfinite(state['qvel']).all()))
        require(f'{label} generation is distinguishable',
                facts['segments'][-1]['metadata']['generation']
                == facts['segments'][0]['metadata']['generation']
                + len(facts['segments']) - 1)
        display_does_not_advance(label)
        if args.task == 'pick-cube':
            require(f'{label} privileged state is live',
                    bool(torch.isfinite(
                        observation['privileged_state']['cube_v1_body_pose']).all()))
        return observation, info

    try:
        first_view = env.robot
        first_observation, _ = segment('A1', 1.0)
        first_state = env.read_device_state(('qpos', 'qvel'))
        first_owned = {key: value.detach().clone() for key, value in first_state.arrays.items()}
        first_frame = (first_observation['cameras']['base']['rgb'] if args.task == 'pick-cube' else None)
        first_frame_copy = None if first_frame is None else first_frame.detach().clone()
        first_renderer = env._task_spec.parallel_render_provider
        first_command = env._task_spec.action_adapter.convert_device_batch(
            _action(env, args.task, 0), first_state)
        first_mask = _cuda_mask((0,))
        first_selection = env.prepare_device_reset_selection(first_mask)

        segment('B', -1.0)
        second_view = env.robot
        second_state = env.read_device_state(('qpos', 'qvel'))
        second_command = env._task_spec.action_adapter.convert_device_batch(
            _action(env, args.task, 1), second_state)
        second_mask = _cuda_mask((1,))
        second_selection = env.prepare_device_reset_selection(second_mask)
        require('A1 view/state rejected after switch',
                _view_rejected(first_view, first_state))
        require('old A1 state is not accepted by the new B view',
                _view_rejected(second_view, first_state))

        segment('A2', 0.5)
        require('B view/state rejected after returning to A',
                _view_rejected(second_view, second_state))
        require('A1 owned state remains readable after reconstruction',
                all(torch.equal(first_state.arrays[key], value)
                    for key, value in first_owned.items()))
        if first_frame is not None:
            require('A1 owned camera frame remains readable after reconstruction',
                    torch.equal(first_frame, first_frame_copy))
            for label, provider in (('A1', first_renderer),
                                    ('A2', env._task_spec.parallel_render_provider)):
                try:
                    provider.capture_cameras(state=first_state)
                except (ValueError, RuntimeError):
                    require(f'{label} renderer rejects A1 state after reconstruction', True)
                else:
                    require(f'{label} renderer rejects A1 state after reconstruction', False)
        for label, command in (('A1', first_command), ('B', second_command)):
            try:
                env._task_spec.runtime.step_device(command)
            except ValueError as error:
                require(f'{label} command rejected after returning to A',
                        'stale' in str(error))
            else:
                require(f'{label} command rejected after returning to A', False)
        for label, mask, selection in (('A1', first_mask, first_selection),
                                       ('B', second_mask, second_selection)):
            try:
                # The lifecycle adapter owns the existing selection consumer;
                # validate before a state payload could be applied.
                env._task_spec.reset_device({}, mask, selection=selection)
            except ValueError as error:
                require(f'{label} selection rejected after returning to A',
                        'selection is stale' in str(error))
            else:
                require(f'{label} selection rejected after returning to A', False)
        require('env identity is stable', id(env) == id(recorder.venv))
    finally:
        recorder.close()

    import h5py
    from task_env.trajectory.metadata import load_metadata

    by_key = {}
    for path in sorted(recorder.saved_paths):
        with h5py.File(path, 'r') as handle:
            raw = handle['meta/env_cfg'][()]
            text = raw.decode() if isinstance(raw, bytes) else str(raw)
            config = load_metadata(text)
            boundary_raw = handle['meta/boundary_context_v1_json'][()]
            boundary = json.loads(boundary_raw)
            transitions = int(handle.attrs['transition_count'])
        entry = {
            'file': path.name,
            'provider': config.get('physics_provider'),
            'generation': config.get('device_generation'),
            'episode_id': [int(item['episode_id']) for item in boundary],
            'transitions': transitions,
        }
        facts['h5'].append(entry)
        by_key.setdefault((entry['provider'], entry['generation']), []).append(entry)
    require('H5 contains three provider/generation segments',
            len(by_key) == 3)
    require('H5 segments are traceable A1/B/A2',
            all(len(items) == 3 for items in by_key.values()))
    np.savez_compressed(out / 'switch-public-witness.npz',
                        **{key: np.stack(values) for key, values in witness.items()})
    _write(args.output, 'switch.json', facts)
    return facts


# --------------------------------------------------------------------------- C4


def run_fault(args):
    """Real switch then a diagnostic-side controlled failure after target build."""

    import psutil
    import subprocess
    import task_env.vectorization.factory as factory_module

    seed = 31
    env = _build(args.task, 'isaacsim', args.interpreter, seed=seed, horizon=64,
                 cameras=False, render_mode=None, output=args.output)
    checks = []

    def require(name, condition, detail=None):
        checks.append({'check': name, 'passed': bool(condition),
                       'detail': detail})

    real_factory = factory_module.make_selected_device_spec
    try:
        env.reset(seed=seed)
        env.step(_action(env, args.task, 0))
        original_generation = _metadata_facts(env)['generation']
        old_view = env.robot
        old_state = env.read_device_state(('qpos', 'qvel'))
        # A real Isaac -> MJWarp rebuild proves the destructive path works.
        env.reset(mask=torch.ones(3, dtype=torch.bool, device='cuda'),
                  options={'execution': {'physics_provider': 'mujoco_warp'}})
        require('real rebuild advanced generation',
                _metadata_facts(env)['generation'] == original_generation + 1)
        require('old view/state invalid after real rebuild',
                _view_rejected(old_view, old_state))

        created = {}

        def failing_factory(**kwargs):
            spec = real_factory(**kwargs)
            created['runtime'] = spec.runtime
            created['ipc'] = spec.runtime._ipc
            created['worker_pids'] = [process.pid for process in
                                      psutil.Process().children(recursive=True)]

            def fail_first_reset(**_kwargs):
                raise RuntimeError('diagnostic injection after target construction')

            # Env's ordinary failure path, not the probe, must close spec.
            spec.reset_sampled_device = fail_first_reset
            return spec

        factory_module.make_selected_device_spec = failing_factory
        faulted = None
        try:
            env.reset(options={'execution': {'physics_provider': 'isaacsim'}})
        except RuntimeError as error:
            faulted = error
        require('failure after destruction raises', faulted is not None)
        pids = created.get('worker_pids', [])
        require('target worker was created', bool(pids), pids)
        require('target workers exited after failed reset',
                all(not psutil.pid_exists(pid) for pid in pids), pids)
        runtime, ipc = created['runtime'], created['ipc']
        require('target worker and IPC owners are detached',
                runtime._worker is None and runtime._ipc is None)
        require('target IPC handles were released',
                not ipc._buffers and ipc._ready is None and ipc._written is None)
        gpu_listing = subprocess.run(
            ['nvidia-smi', '--query-compute-apps=pid,used_gpu_memory',
             '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True)
        gpu_pids = {int(line.split(',')[0].strip()) for line in gpu_listing.stdout.splitlines()
                    if line.strip()}
        require('target workers no longer own GPU allocations',
                not gpu_pids.intersection(pids), gpu_listing.stdout.strip())
        for name, call in (
            ('reset', lambda: env.reset()),
            ('step', lambda: env.step(_action(env, args.task, 0))),
            ('render', lambda: env.render('rgb_array')),
            ('state', lambda: env.read_device_state(('qpos', 'qvel'))),
        ):
            try:
                call()
            except RuntimeError:
                require(f'faulted env blocks {name}', True)
            else:
                require(f'faulted env blocks {name}', False)
        require('close is repeatable after a fault', env.close() is None)
        require('second close is repeatable after a fault', env.close() is None)
    finally:
        factory_module.make_selected_device_spec = real_factory
        env.close()
    _write(args.output, 'fault.json', {'checks': checks})
    return {'checks': checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interpreter', required=True)
    parser.add_argument('--output')
    sub = parser.add_subparsers(dest='case', required=True)
    partial = sub.add_parser('partial')
    partial.add_argument('--task', choices=tuple(TASK_UIDS), required=True)
    partial.add_argument('--provider',
                         choices=('geophys', 'mujoco_warp', 'isaacsim'),
                         required=True)
    partial.add_argument('--camera-attribution', action='store_true')
    staggered = sub.add_parser('staggered')
    staggered.add_argument('--provider',
                           choices=('geophys', 'mujoco_warp', 'isaacsim'),
                           required=True)
    rng = sub.add_parser('rng')
    rng.add_argument('--task', choices=tuple(TASK_UIDS), required=True)
    rng.add_argument('--provider', choices=('geophys', 'mujoco_warp', 'isaacsim'),
                     required=True)
    switch = sub.add_parser('switch')
    switch.add_argument('--task', choices=tuple(TASK_UIDS), required=True)
    fault = sub.add_parser('fault')
    fault.add_argument('--task', choices=('pendulum',), default='pendulum')
    args = parser.parse_args()
    if args.case == 'partial':
        result = run_partial(args)
    elif args.case == 'staggered':
        result = run_staggered(args)
    elif args.case == 'rng':
        result = run_rng_sequence(args)
    elif args.case == 'switch':
        result = run_switch(args)
    else:
        result = run_fault(args)
    failed = [item for item in result.get('checks', ()) if not item['passed']]
    print(json.dumps(_jsonable(result)))
    if failed:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
