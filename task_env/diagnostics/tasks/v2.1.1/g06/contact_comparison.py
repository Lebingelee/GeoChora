"""Frozen-action PickCube comparison, using only the public device API."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import torch


def freeze_actions(previous, output):
    """Derive a new replay file from retained observations, never old deleted actions."""
    previous, output = Path(previous), Path(output)
    cases = {
        'zero': ('geophys-pickcube-finger-contact-001', False, False),
        'hold': ('geophys-pickcube-hold-contact-001', True, False),
        'descent': ('geophys-pickcube-controlled-contact-final-001', True, True),
    }
    frozen = {}
    provenance = {}
    for name, (directory, hold, descent) in cases.items():
        path = previous / directory / 'finger_contact_traces.npz'
        with np.load(path) as data:
            joints = torch.from_numpy(data['joint_position'].copy())
        steps = len(joints) - 1
        if steps != (60 if descent else 20) or tuple(joints.shape[1:]) != (3, 9):
            raise ValueError(f'{name}: unexpected retained trajectory')
        target = joints[0, :, :7].clone()
        if descent:
            target[:, 3] -= .08
        limits = torch.tensor([87., 87., 87., 87., 12., 12., 12.])
        bias = torch.tensor([0., -29.3559534, 0., 22.0492107, .6695478, 2.3063896, 0.]) if descent else 0.
        actions = torch.zeros((steps, 3, 8))
        for tick in range(steps):
            actions[tick, :, -1] = (torch.tensor([-4., -4., 0.])
                                     if not descent or tick >= 35 else 0.)
            if hold:
                velocity = (joints[tick, :, :7] - joints[max(0, tick - 1), :, :7]) / .01
                actions[tick, :, :7] = torch.clamp(
                    bias + 200. * (target - joints[tick, :, :7]) - 20. * velocity,
                    min=-limits, max=limits)
        frozen[name] = actions.numpy()
        provenance[name] = {'retained_observation': str(path.resolve()),
                            'observation_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                            'steps': steps, 'shape': list(actions.shape)}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        np.savez_compressed(stream, **frozen)
    return {'file': str(output.resolve()), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'kind': 'new reconstructed replay, not the deleted four-path comparison',
            'seeds': [3706, 31, 3706], 'source_observations': provenance}


def freeze_source(output, worker_python):
    """Freeze the same task's source closure before independent geometry readback."""
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.registry import ENV_REGISTRY
    from task_env.runtime.sessions.source import close_source_and_task_resources, lower_mujoco_scene_source

    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    request = {'execution': {'physics_provider': 'geophys', 'interpreter': worker_python,
                             'geophys_contact_mode': 'discrete'},
               'controller': {'profile_id': 'panda-direct-effort-v1'},
               'robot': {'native_drive': 'disabled'}, 'episode': {'seed': 31, 'horizon': 100}}
    task = ENV_REGISTRY.get('pick-cube-p16-reference-v1')
    config = resolve_task_env_config(task, request, execution_scope='device_batch')
    binding = task._build_selected_binding(config)
    built = binding.build_for_request('geophys', 'cuda', 31, 100)
    try:
        source = built['source']
        xml, assets = lower_mujoco_scene_source(source.scene_source, source.scene_definition,
                                                 source.source_closure_digest)
        (output / 'scene.xml').write_text(xml)
        for name, payload in assets.items():
            path = (output / name).resolve()
            if not path.is_relative_to(output.resolve()):
                raise ValueError('source asset escaped snapshot')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        return {'request': request, 'source_id': source.source_id,
                'source_closure_sha256': source.source_closure_digest,
                'artifact_sha256': built['artifact'].identity_hash,
                'scene_xml_sha256': hashlib.sha256(xml.encode()).hexdigest(),
                'asset_sha256': {name: hashlib.sha256(data).hexdigest() for name, data in assets.items()}}
    finally:
        error = close_source_and_task_resources(built['source'], binding)
        if error is not None:
            raise error


def replay(worker_python, action_file, *, batch, iterations, source_row=0):
    from task_env import make_parallel_env

    if batch not in (1, 3, 16):
        raise ValueError('comparison accepts B=1, B=3 or B=16')
    if source_row not in (0, 1, 2) or (batch != 1 and source_row != 0):
        raise ValueError('source row selection requires B=1')
    path = Path(action_file).resolve(strict=True)
    with np.load(path) as data:
        actions = {key: data[key].copy() for key in ('zero', 'hold', 'descent')}
    config = {'execution': {'physics_provider': 'geophys', 'interpreter': worker_python,
                            'geophys_contact_mode': 'discrete'},
              'controller': {'profile_id': 'panda-direct-effort-v1'},
              'robot': {'native_drive': 'disabled'},
              'episode': {'seed': 31, 'horizon': 100}}
    if iterations is not None:
        config['runtime'] = {'body_contact_solver_iterations': iterations}
    env = make_parallel_env('pick-cube-p16-reference-v1', env_config=config, num_env=batch,
                            backend='cuda', execution='device', worker_directory=os.getcwd())
    indices = [source_row] if batch == 1 else [row % 3 for row in range(batch)]
    result = {'configuration': config, 'action_file': str(path),
              'action_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'batch': batch,
              'seeds': [[3706, 31, 3706][row] for row in indices], 'source_rows': indices, 'cases': {}}
    try:
        result['layout'] = env.resource_summary()['device_transition']['physical_layout_facts']
        for name, sequence in actions.items():
            observation, _ = env.reset(seed=result['seeds'])
            arrays = {'qpos': [], 'qvel': [], 'joint_position': [], 'cube_pose': []}

            def capture():
                state = env.read_device_state(('qpos', 'qvel'))
                for key in ('qpos', 'qvel'):
                    arrays[key].append(state.arrays[key].cpu().numpy().copy())
                arrays['joint_position'].append(observation['state']['joint_position'].cpu().numpy().copy())
                arrays['cube_pose'].append(observation['privileged_state']['cube_v1_body_pose'][:, 0].cpu().numpy().copy())

            capture()
            for tick, action in enumerate(sequence):
                observation, _, terminated, truncated, _ = env.step(
                    {'effort': torch.from_numpy(action[indices].copy()).to('cuda')})
                capture()
                if bool(terminated.any() or truncated.any()):
                    raise AssertionError(f'{name}: task ended at tick {tick}')
                print(f'completed {name} {tick + 1}/{len(sequence)}', flush=True)
            output = f'{name}-trajectory.npz'
            np.savez_compressed(output, **{key: np.asarray(value) for key, value in arrays.items()})
            result['cases'][name] = {'steps': len(sequence), 'trajectory': output,
                                     'native_substeps_per_interval': 5}
    finally:
        env.close()
    return result


def replay_scalar(worker_python, action_file, *, iterations, contact_mode, source_row=0):
    from task_env import make_env

    path = Path(action_file).resolve(strict=True)
    with np.load(path) as data:
        actions = {key: data[key].copy() for key in ('zero', 'hold', 'descent')}
    if source_row not in (0, 1, 2):
        raise ValueError('source row must be 0, 1 or 2')
    seed = [3706, 31, 3706][source_row]
    config = {'execution': {'physics_provider': 'geophys', 'physics_backend': 'cpu',
                            'physics_device': 'cpu', 'deployment': 'in_process',
                            'interpreter': worker_python},
              'controller': {'profile_id': 'panda-direct-effort-v1'},
              'robot': {'native_drive': 'disabled'}, 'episode': {'seed': seed, 'horizon': 100}}
    if iterations is not None:
        config['runtime'] = {'body_contact_solver_iterations': iterations}
    if contact_mode != 'provider_default':
        config['execution']['geophys_contact_mode'] = contact_mode
    env = make_env('pick-cube-p16-reference-v1', config=config)
    trace = None
    result = {'configuration': config, 'action_file': str(path),
              'action_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'seed': seed, 'source_row': source_row, 'cases': {}, 'contact_mode_requested': contact_mode}
    try:
        for name, sequence in actions.items():
            if trace is not None:
                trace.close()
                trace = None
            observation, _ = env.reset(seed=seed)
            if os.environ.get('G06B_SCALAR_TRACE_OUTPUT'):
                import importlib.util
                trace_file = (Path(__file__).resolve().parents[5] / 'GeoPhys/test/development/rigid'
                              / 'g06b_scalar_contact_trace.py')
                spec = importlib.util.spec_from_file_location('g06b_scalar_contact_trace', trace_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                trace = module.ScalarContactTrace(
                    env.session, Path(os.environ['G06B_SCALAR_TRACE_OUTPUT']) / name)
            if 'effective_model' not in result:
                facts = env.session.build_layout_facts
                Path('scalar-build-layout-facts.json').write_text(json.dumps(facts, indent=2) + '\n')
                result['effective_model'] = 'scalar-build-layout-facts.json'
            if contact_mode != 'provider_default':
                facts = env.session.build_layout_facts
                result['contact_mode_resolved'] = facts['contact_mode_resolved']
                if facts['contact_mode_requested'] != contact_mode or facts['contact_mode_resolved'] != contact_mode:
                    raise AssertionError('scalar GeoPhys actual contact mode differs')
            arrays = {'joint_position': [], 'joint_velocity': [], 'cube_pose': [],
                      'cube_velocity': [], 'simulation_time': []}

            def capture():
                arrays['joint_position'].append(np.asarray(observation['state']['joint_position']).copy())
                arrays['cube_pose'].append(np.asarray(observation['privileged_state']['cube_v1_body_pose'])[0].copy())
                public_state = env.session.snapshot()
                free = env.session.snapshot_free_joint_native_v1()
                names = sorted(public_state.joint_velocity)
                if 'joint_velocity_names' not in result:
                    result['joint_velocity_names'] = names
                elif result['joint_velocity_names'] != names:
                    raise AssertionError('scalar joint state names changed')
                arrays['joint_velocity'].append(np.asarray([public_state.joint_velocity[name] for name in names]))
                arrays['cube_velocity'].append(np.asarray(free['joints']['cube-v1']['velocity']))
                arrays['simulation_time'].append(np.asarray(public_state.simulation_time))

            capture()
            for tick, action in enumerate(sequence):
                observation, _, terminated, truncated, _ = env.step(action[source_row].copy())
                capture()
                if bool(terminated or truncated):
                    raise AssertionError(f'{name}: task ended at tick {tick}')
                print(f'completed {name} {tick + 1}/{len(sequence)}', flush=True)
            output = f'{name}-trajectory.npz'
            np.savez_compressed(output, **{key: np.asarray(value)[:, None] for key, value in arrays.items()})
            result['cases'][name] = {'steps': len(sequence), 'trajectory': output}
    finally:
        try:
            if trace is not None:
                trace.close()
        finally:
            env.close()
    return result
