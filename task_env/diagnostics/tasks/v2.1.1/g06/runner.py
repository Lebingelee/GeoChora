"""Bounded two-interpreter CUDA IPC check for a prospective batch transport.

Run via the repository supervisor: --run --worker-python PATH --output DIR.
The exchanged two float values are diagnostic data, not a TaskEnv transition.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys


def _send(stream, value):
    stream.write(json.dumps(value) + '\n')
    stream.flush()


def _receive(stream):
    line = stream.readline()
    if not line:
        raise RuntimeError('IPC peer exited before sending a message')
    return json.loads(line)


def _encode(value):
    return base64.b64encode(value).decode('ascii')


def _decode(value):
    return base64.b64decode(value, validate=True)


def _worker():
    with contextlib.redirect_stdout(sys.stderr):
        import numpy as np
        import warp as wp
        wp.init()
        device = wp.get_device('cuda:0')
        if not device.is_ipc_supported:
            raise RuntimeError('Warp reports that CUDA IPC is not supported')
        with wp.ScopedMempool(device, False):
            values = wp.array(np.array([1., 2.], dtype=np.float32), device=device)
        ready = wp.Event(device=device, interprocess=True)
        wp.record_event(ready)
        memory_handle, ready_handle = values.ipc_handle(), ready.ipc_handle()
    _send(sys.stdout, {'memory': _encode(memory_handle), 'ready': _encode(ready_handle),
                       'warp_version': wp.__version__, 'device': str(device)})
    request = _receive(sys.stdin)
    with contextlib.redirect_stdout(sys.stderr):
        written = wp.event_from_ipc_handle(_decode(request['written']), device=device)
        wp.wait_event(written)
        # Reading these two diagnostic scalars is an oracle, not a state transfer.
        observed = values.numpy().tolist()
        if observed != [4., 7.]:
            raise AssertionError(f'worker observed {observed!r}')
        values.assign(np.array([9., 13.], dtype=np.float32))
        wp.record_event(ready)
    _send(sys.stdout, {'observed': observed})
    _receive(sys.stdin)
    with contextlib.redirect_stdout(sys.stderr):
        wp.synchronize_device(device)
        del written, values, ready
    _send(sys.stdout, {'closed': True})


def _check(result):
    if int(result[0]) != 0:
        raise RuntimeError(f'CUDA driver call failed: {result[0]}')
    return result[1] if len(result) > 1 else None


def _ipc_handle(kind, payload):
    value = kind()
    if len(payload) != 64:
        raise ValueError('CUDA IPC handle must contain 64 bytes')
    ctypes.memmove(value.getPtr(), payload, len(payload))
    return value


def _parent(worker_python):
    import torch
    from task_env.runtime.transport.cuda_ipc import CudaIpcConnection
    process = subprocess.Popen([worker_python, '-u', __file__, '--worker'],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               text=True, bufsize=1)
    connection = None
    try:
        hello = _receive(process.stdout)
        connection = CudaIpcConnection({'device': 'cuda:0', 'ready': hello['ready'],
            'buffers': {'values': {'handle': hello['memory'], 'shape': [2], 'dtype': 'float32'}}})
        connection.wait_ready()
        result = connection.read('values')
        connection.synchronize()
        initial = result.cpu().tolist()
        if initial != [1., 2.]:
            raise AssertionError(f'parent observed {initial!r}')
        outgoing = torch.tensor([4., 7.], device='cuda', dtype=torch.float32)
        connection.write('values', outgoing)
        connection.record_written()
        _send(process.stdin, {'written': connection.written_handle})
        response = _receive(process.stdout)
        connection.wait_ready()
        result = connection.read('values')
        connection.synchronize()
        final = result.cpu().tolist()
        if final != [9., 13.]:
            raise AssertionError(f'parent final data {final!r}')
        connection.release_imports()
        _send(process.stdin, {'close': True})
        closed = _receive(process.stdout)
        if not closed['closed'] or process.wait(timeout=20) != 0:
            raise RuntimeError('worker did not close cleanly')
        return {'initial': initial, 'worker_observed': response['observed'],
                'final': final, 'worker_closed': True, 'worker_version': hello['warp_version'],
                'torch_version': torch.__version__, 'worker_python': worker_python,
                'parent_python': sys.executable, 'device': hello['device']}
    finally:
        if connection is not None:
            connection.release_imports()
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        if connection is not None:
            connection.close()


def _physics():
    """Exercise the real Pendulum MJCF as an isolated native B=3 diagnostic."""
    with contextlib.redirect_stdout(sys.stderr):
        import numpy as np
        import mujoco
        import mujoco_warp as mjw
        import warp as wp
        from task_env.environment.configuration import resolve_task_env_config
        from task_env.registry import ENV_REGISTRY
        from task_env.runtime.sessions.mujoco_physical import resolve_physical_joint, validate_direct_motor
        from task_env.tasks.pendulum import PENDULUM_TASK_SEMANTICS

        wp.init()
        environment = ENV_REGISTRY.get('pendulum-v1')
        config = resolve_task_env_config(environment, {'execution': {'physics_provider': 'mujoco',
            'deployment': 'in_process'}, 'episode': {'seed': 73}})
        binding = environment._build_selected_binding(config)
        built = binding.build_for_request('mujoco', 'cpu', 73, config.environment.episode.horizon)
        source, execution = built['source'], built['physical_execution']
        execution.validate_source(scene=source.scene_definition, artifact_sha256=built['artifact'].identity_hash,
            source_id=source.source_id, source_closure_sha256=source.source_closure_digest, source=source)
        model = mujoco.MjModel.from_xml_string(source.scene_source.xml)
        channels = execution.compiled.binding.channels
        if len(channels) != 1:
            raise ValueError('the bounded native diagnostic requires one declared channel')
        channel, = channels
        joint = execution.joint_bindings[f'{channel.entity_id}/{channel.joint_id}']
        joint_id, dof = resolve_physical_joint(model, mujoco, source.joints, joint, channel)
        actuator = int(model.actuator(channel.native_actuator).id)
        validate_direct_motor(model, mujoco, actuator, channel)
        if (int(model.actuator_trntype[actuator]) != int(mujoco.mjtTrn.mjTRN_JOINT)
                or int(model.actuator_trnid[actuator, 0]) != joint_id or dof != 0):
            raise ValueError('declared joint, actuator and DOF mapping disagree')
        model.opt.disableflags |= int(mujoco.mjtDisableBit.mjDSBL_ACTUATION)
        data = mujoco.MjData(model)
        device_model = mjw.put_model(model)
        device_data = mjw.put_data(model, data, nworld=3)
        samples = [PENDULUM_TASK_SEMANTICS.sample_reset(np.random.default_rng(seed))
                   for seed in (73, 74, 75)]
        q0 = np.array([[angle] for angle, _ in samples], dtype=np.float32)
        v0 = np.array([[speed] for _, speed in samples], dtype=np.float32)
        efforts = np.array([[-1.5], [0.5], [1.5]], dtype=np.float32)
        device_data.qpos.assign(q0)
        device_data.qvel.assign(v0)
        device_data.qfrc_applied.assign(efforts)
        # Frozen oracle: gravity acts as +m*g*l*sin(theta), damping opposes
        # angular velocity, and the declared moment about the hinge is
        # I_com + m*l**2 = 0.1125 kg m². First-step velocity tolerance is
        # 2e-3 rad/s, allowing implicit damping and f32 rounding.
        predicted_v = v0[:, 0] + 0.002 * (
            efforts[:, 0] + 9.81 * 0.25 * np.sin(q0[:, 0]) - 0.05 * v0[:, 0]
        ) / 0.1125
        mjw.step(device_model, device_data)
        first_v = device_data.qvel.numpy()[:, 0].copy()
        error = np.abs(first_v - predicted_v)
        if np.any(error > 0.002):
            raise AssertionError(f'first-step oracle error {error.tolist()}')
        for _ in range(499):
            mjw.step(device_model, device_data)
        wp.synchronize_device()
        final_q = device_data.qpos.numpy().reshape(3).tolist()
        final_v = device_data.qvel.numpy().reshape(3).tolist()
        if not (np.isfinite(final_q).all() and np.isfinite(final_v).all()):
            raise AssertionError('nonfinite final physics state')
    return {'provider': 'mujoco_warp', 'batch': 3, 'seeds': [73, 74, 75],
            'initial_q_rad': q0[:, 0].tolist(), 'initial_qd_rad_s': v0[:, 0].tolist(),
            'effort_nm': efforts[:, 0].tolist(), 'predicted_first_qd_rad_s': predicted_v.tolist(),
            'observed_first_qd_rad_s': first_v.tolist(), 'first_step_abs_error': error.tolist(),
            'first_step_tolerance_rad_s': 0.002, 'final_q_rad': final_q,
            'final_qd_rad_s': final_v, 'control_intervals': 20, 'substeps_per_interval': 25,
            'native_batch_steps': 500, 'world_steps': 1500,
            'physics_dt_s': float(model.opt.timestep), 'python': sys.executable,
            'joint': source.joints[f'{channel.entity_id}/{channel.joint_id}'],
            'actuator': channel.native_actuator, 'native_dof': dof,
            'source_id': source.source_id, 'drive_isolation': 'mjDSBL_ACTUATION',
            'mujoco': mujoco.__version__, 'mujoco_warp': mjw.__version__, 'warp': wp.__version__,
            'scope': 'native diagnostic only; not the formal TaskEnv device route'}


def _transport_physics(worker_python, *, frame_probe=False):
    """Exercise the actual worker/provider/IPC owners before public admission."""
    import torch
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.registry import ENV_REGISTRY
    from task_env.runtime.transport.cuda_ipc import CudaIpcConnection
    from task_env.runtime.transport.worker import RuntimeWorker

    environment = ENV_REGISTRY.get('pendulum-v1')
    config = resolve_task_env_config(environment, {'execution': {'physics_provider': 'mujoco'},
                                                   'episode': {'seed': 73}})
    binding = environment._build_selected_binding(config)
    built = binding.build_for_request('mujoco', 'cpu', 73, config.environment.episode.horizon)
    source, execution = built['source'], built['physical_execution']
    execution.validate_source(scene=source.scene_definition, artifact_sha256=built['artifact'].identity_hash,
        source_id=source.source_id, source_closure_sha256=source.source_closure_digest, source=source)
    channels = execution.compiled.binding.channels
    request = {'provider': 'mujoco_warp', 'device': 'cuda:0', 'source_xml': source.scene_source.xml,
               'source_joints': dict(source.joints), 'num_envs': 3,
               'physics_dt': built['artifact'].timebase.physics_dt,
               'control_substeps': built['artifact'].timebase.control_substeps,
               'channels': [{'channel': channel.to_mapping(),
                             'joint': execution.joint_bindings[
                                 f'{channel.entity_id}/{channel.joint_id}'].to_mapping()}
                            for channel in channels]}
    if frame_probe:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(request['source_xml'])
        body = root.find(".//body[@name='pendulum_link']")
        ET.SubElement(body, 'site', name='frame_probe', pos='.1 0 .3',
                      quat='.9238795325112867 0 0 .3826834323650898')
        request['source_xml'] = ET.tostring(root, encoding='unicode')
        request['source_frames'] = {'probe/frame': 'frame_probe'}
    worker = RuntimeWorker(worker_python, request, working_directory=os.getcwd())
    connection = None
    try:
        connection = CudaIpcConnection(worker.description)
        worker.call('bind_event', handle=connection.written_handle)
        q = torch.zeros((3, worker.description['nq']), dtype=torch.float32, device='cuda')
        v = torch.zeros((3, worker.description['nv']), dtype=torch.float32, device='cuda')
        mask = torch.ones(3, dtype=torch.bool, device='cuda')
        connection.write('reset_qpos', q)
        connection.write('reset_qvel', v)
        connection.write('reset_mask', mask)
        connection.record_written()
        worker.call('reset')
        connection.wait_ready()
        reset_q = connection.read('qpos')
        connection.synchronize()
        if not torch.equal(reset_q, q):
            raise AssertionError('native reset did not publish requested values')
        effort = torch.tensor([[-1.5], [0.5], [1.5]], dtype=torch.float32, device='cuda')
        first = None
        for _ in range(20):
            connection.write('effort', effort)
            connection.record_written()
            worker.call('step')
            connection.wait_ready()
            before_q = connection.read('qpos')
            before_v = connection.read('qvel')
            connection.synchronize()
            if first is None:
                first = before_v[:, 0].cpu().tolist()
        if not (first[0] < 0 < first[1] < first[2]):
            raise AssertionError(f'native rows do not follow effort signs: {first}')
        frame_error = None
        if frame_probe:
            import math
            frame_position = connection.read('frame_position')[:, 0]
            frame_orientation = connection.read('frame_orientation')[:, 0]
            connection.synchronize()
            angles = before_q[:, 0]
            cosine, sine = torch.cos(angles), torch.sin(angles)
            expected_position = torch.stack((.1 * cosine + .3 * sine,
                                              torch.zeros_like(angles),
                                              -.1 * sine + .3 * cosine), dim=1)
            cy, sy = torch.cos(angles / 2), torch.sin(angles / 2)
            cz, sz = math.cos(math.pi / 8), math.sin(math.pi / 8)
            expected_orientation = torch.stack((cy * cz, sy * sz, sy * cz, cy * sz), dim=1)
            # A quaternion and its negation represent the same rotation.
            alignment = torch.where((frame_orientation * expected_orientation).sum(dim=1, keepdim=True) < 0,
                                    -1., 1.)
            frame_error = max(float((frame_position - expected_position).abs().max().item()),
                              float((frame_orientation * alignment - expected_orientation).abs().max().item()))
            if frame_error > 2e-5:
                raise AssertionError(f'device site frame disagrees with independent FK: {frame_error}; '
                    f'position={frame_position.cpu().tolist()} expected={expected_position.cpu().tolist()}; '
                    f'orientation={frame_orientation.cpu().tolist()} expected={expected_orientation.cpu().tolist()}')
        mask = torch.tensor([False, True, False], dtype=torch.bool, device='cuda')
        connection.write('reset_qpos', q)
        connection.write('reset_qvel', v)
        connection.write('reset_mask', mask)
        connection.record_written()
        worker.call('reset')
        connection.wait_ready()
        after_q = connection.read('qpos')
        after_v = connection.read('qvel')
        connection.synchronize()
        if (not torch.equal(after_q[[0, 2]], before_q[[0, 2]])
                or not torch.equal(after_v[[0, 2]], before_v[[0, 2]])
                or float(after_q[1, 0]) != 0. or float(after_v[1, 0]) != 0.):
            raise AssertionError('masked reset altered another row or did not reset the selected row')
        connection.release_imports()
        worker.close()
        connection.close()
        connection = None
        return {'scope': 'worker/provider/IPC diagnostic, not formal TaskEnv', 'batch': 3,
                'first_qd_rad_s': first, 'masked_reset_rows': [1], 'nonselected_unchanged': True,
                'control_intervals': 20, 'native_batch_steps': 500, 'world_steps': 1500,
                'source_id': source.source_id, 'worker_closed': True,
                'site_frame_fk_max_error': frame_error}
    finally:
        if connection is not None:
            connection.release_imports()
        worker.close()
        if connection is not None:
            connection.close()


def _session_physics(worker_python):
    """Exercise the source-bound Controller and MJWarp session below the Env."""
    from dataclasses import replace
    import torch
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.registry import ENV_REGISTRY
    from task_env.runtime.providers.mujoco_warp.batch import MuJoCoWarpBatchSession

    environment = ENV_REGISTRY.get('pendulum-v1')
    config = resolve_task_env_config(environment, {'execution': {'physics_provider': 'mujoco'},
                                                   'episode': {'seed': 73}})
    binding = environment._build_selected_binding(config)
    built = binding.build_for_request('mujoco', 'cpu', 73, config.environment.episode.horizon)
    session = MuJoCoWarpBatchSession(built, num_envs=3, device='cuda:0',
                                    interpreter=worker_python, working_directory=os.getcwd())
    try:
        q = torch.zeros((3, 1), dtype=torch.float32, device='cuda')
        v = torch.zeros((3, 1), dtype=torch.float32, device='cuda')
        mask = torch.ones(3, dtype=torch.bool, device='cuda')
        state = session.reset_device({'qpos': q, 'qvel': v}, mask)
        controller = built['controller']
        action = {'torque': torch.tensor([[-1.5], [0.5], [1.5]], device='cuda')}
        first = None
        for tick in range(20):
            state = replace(state, episode_ids=torch.ones(3, dtype=torch.int64, device='cuda'),
                            episode_steps=torch.full((3,), tick, dtype=torch.int32, device='cuda'))
            command = controller.convert_device_batch(action, state)
            state = session.step_device(command)
            if tick == 0:
                first = state.arrays['qvel'][:, 0].cpu().tolist()
                try:
                    session.step_device(command)
                except ValueError as error:
                    if 'stale' not in str(error):
                        raise
                else:
                    raise AssertionError('session admitted the same command twice')
        if not (first[0] < 0 < first[1] < first[2]):
            raise AssertionError(f'Controller responses disagree with efforts: {first}')
        before = state
        mask = torch.tensor([False, True, False], dtype=torch.bool, device='cuda')
        state = session.reset_device({'qpos': q, 'qvel': v}, mask)
        if (not torch.equal(state.arrays['qpos'][[0, 2]], before.arrays['qpos'][[0, 2]])
                or not torch.equal(state.arrays['qvel'][[0, 2]], before.arrays['qvel'][[0, 2]])
                or float(state.arrays['qpos'][1, 0]) != 0. or float(state.arrays['qvel'][1, 0]) != 0.):
            raise AssertionError('session masked reset contaminated another row')
        state = replace(state, episode_ids=torch.tensor([1, 2, 1], dtype=torch.int64, device='cuda'),
                        episode_steps=torch.tensor([20, 0, 20], dtype=torch.int32, device='cuda'))
        old_command = controller.convert_device_batch(action, state)
        retained = state.arrays['qpos'].clone()
        old_identity = state.identity
        result = {'scope': 'typed Controller and session diagnostic; not formal TaskEnv', 'batch': 3,
                  'first_qd_rad_s': first, 'masked_reset_rows': [1], 'stale_command_rejected': True,
                  'nonselected_unchanged': True, 'control_intervals': 20,
                  'native_batch_steps': 500, 'world_steps': 1500,
                  'state_revision': state.identity.revision}
    finally:
        session.close()
    session.close()
    if not torch.equal(state.arrays['qpos'], retained):
        raise AssertionError('owned state snapshot did not survive close')
    replacement = MuJoCoWarpBatchSession(built, num_envs=3, device='cuda:0',
                                        interpreter=worker_python, working_directory=os.getcwd())
    try:
        new_state = replacement.reset_device({'qpos': q, 'qvel': v}, torch.ones(3, dtype=torch.bool, device='cuda'))
        if new_state.identity.materialization_id == old_identity.materialization_id:
            raise AssertionError('replacement session reused a materialization identity')
        try:
            replacement.step_device(old_command)
        except ValueError as error:
            if 'stale' not in str(error):
                raise
        else:
            raise AssertionError('replacement session accepted an old command')
    finally:
        replacement.close()
    result['replacement_rejects_old_command'] = True
    result['owned_snapshot_survives_close'] = True
    result['worker_closed'] = True
    return result


def _formal_device(worker_python):
    """Exercise the ordinary registered factory and same-step device lifecycle."""
    import numpy as np
    import torch
    from task_env import make_parallel_env

    config = {'execution': {'physics_provider': 'mujoco_warp', 'interpreter': worker_python},
              'episode': {'seed': 73, 'horizon': 20}}
    env = make_parallel_env('pendulum-v1', env_config=config, num_env=3, backend='cuda',
                            execution='device', worker_directory=os.getcwd())
    try:
        observation, info = env.reset(seed=73)
        leaf = observation['state']['proprioception']
        if tuple(leaf.shape) != (3, 3) or leaf.dtype != torch.float32 or str(leaf.device) != 'cuda:0':
            raise AssertionError('initial observation violates the device contract')
        initial = env.read_device_state(('qpos', 'qvel'))
        if (initial.lifetime != 'owned_snapshot' or initial.identity.native_step != 0
                or initial.episode_ids.tolist() != [1, 1, 1]
                or initial.episode_steps.tolist() != [0, 0, 0]):
            raise AssertionError('initial state ownership or native clock is incorrect')
        retained_initial_q = initial.arrays['qpos'].clone()
        for invalid in (torch.zeros(2, dtype=torch.bool, device='cuda'),
                        torch.zeros(3, dtype=torch.bool, device='cpu')):
            try:
                env.reset(mask=invalid)
            except ValueError:
                pass
            else:
                raise AssertionError('invalid reset mask was admitted')
        env.reset(mask=torch.zeros(3, dtype=torch.bool, device='cuda'))
        no_op = env.read_device_state(('qpos', 'qvel'))
        if no_op.identity != initial.identity or not torch.equal(no_op.arrays['qpos'], retained_initial_q):
            raise AssertionError('all-false reset mutated the state or native clock')
        invalid_actions = ({'other': torch.zeros((3, 1), device='cuda')},
                           {'torque': torch.zeros((3, 1), device='cpu')},
                           {'torque': torch.full((3, 1), 2.1, device='cuda')})
        for invalid_action in invalid_actions:
            try:
                env.step(invalid_action)
            except ValueError:
                pass
            else:
                raise AssertionError('invalid canonical action was admitted')
        if env.read_device_state(('qpos',)).identity.native_step != 0:
            raise AssertionError('invalid action advanced physics')
        q0 = initial.arrays['qpos'][:, 0].cpu().numpy().copy()
        v0 = initial.arrays['qvel'][:, 0].cpu().numpy().copy()
        # Frozen independent ODE oracle: semi-implicit integration of the
        # declared single-hinge inertia/gravity/damping over one 25-substep
        # control interval; tolerances are 0.01 rad and 0.05 rad/s.
        predicted_q, predicted_v = q0.astype(float).copy(), v0.astype(float).copy()
        efforts = np.asarray([-1.5, .5, 1.5], dtype=float)
        for _ in range(25):
            predicted_v += .002 * (efforts + 9.81 * .25 * np.sin(predicted_q) - .05 * predicted_v) / .1125
            predicted_q += .002 * predicted_v
        action = {'torque': torch.tensor([[-1.5], [.5], [1.5]], dtype=torch.float32, device='cuda')}
        first_q = first_v = None
        for tick in range(20):
            if tick == 19:
                before_terminal = env.read_device_state(('qpos', 'qvel'))
                terminal_q = before_terminal.arrays['qpos'][:, 0].cpu().numpy().astype(float)
                terminal_v = before_terminal.arrays['qvel'][:, 0].cpu().numpy().astype(float)
                terminal_q_before, terminal_v_before = terminal_q.copy(), terminal_v.copy()
                for _ in range(25):
                    terminal_v += .002 * (efforts + 9.81 * .25 * np.sin(terminal_q) - .05 * terminal_v) / .1125
                    terminal_q += .002 * terminal_v
            observation, reward, terminated, truncated, info = env.step(action)
            if any(str(value.device) != 'cuda:0' for value in (reward, terminated, truncated)):
                raise AssertionError('transition left the requested CUDA device')
            if tick == 0:
                current = env.read_device_state(('qpos', 'qvel'))
                first_q = current.arrays['qpos'][:, 0].cpu().numpy().copy()
                first_v = current.arrays['qvel'][:, 0].cpu().numpy().copy()
                if (current.identity.native_step != 25
                        or current.episode_steps.tolist() != [1, 1, 1]
                        or not torch.equal(initial.arrays['qpos'], retained_initial_q)):
                    raise AssertionError('native clock or retained state snapshot is incorrect')
                if (np.max(np.abs(first_q - predicted_q)) > .01
                        or np.max(np.abs(first_v - predicted_v)) > .05):
                    raise AssertionError('first interval disagrees with the independent hinge oracle')
                poses = env.read_device_state(('body_position', 'body_orientation'))
                body_names = env.metadata['runtime_resource_summary']['device_transition']['body_names']
                link = body_names.index('pendulum-v1/pendulum_link')
                measured_quat = poses.arrays['body_orientation'][:, link].cpu().numpy()
                expected_quat = np.stack((np.cos(first_q / 2), np.zeros(3),
                                          np.sin(first_q / 2), np.zeros(3)), axis=1)
                if (np.max(np.abs(measured_quat - expected_quat)) > 1e-5
                        or poses.identity != current.identity):
                    raise AssertionError('public body pose differs from same-boundary hinge FK')
            if tick == 4:
                before = env.read_device_state(('qpos', 'qvel'))
                mask = torch.tensor([False, True, False], dtype=torch.bool, device='cuda')
                env.reset(mask=mask)
                after = env.read_device_state(('qpos', 'qvel'))
                if after.identity.native_step != before.identity.native_step:
                    raise AssertionError('masked reset moved the global native clock')
                for name in ('qpos', 'qvel'):
                    if not torch.equal(before.arrays[name][[0, 2]], after.arrays[name][[0, 2]]):
                        raise AssertionError('manual reset contaminated an unselected row')
            if tick < 19 and (bool(terminated.any()) or bool(truncated.any())):
                raise AssertionError('unexpected early terminal transition')
        if terminated.tolist() != [False, False, False] or truncated.tolist() != [True, False, True]:
            raise AssertionError('staggered horizon did not terminate exactly the expected rows')
        final = info['final_observation']['state']['proprioception']
        preserved = final.clone()
        if tuple(final.shape) != (3, 3) or info['_final_observation'].tolist() != [True, False, True] or info['episode_id'].tolist() != [2, 2, 2]:
            raise AssertionError('same-step reset did not retain final rows and advance episodes')
        if info['episode_step'].tolist() != [0, 15, 0] or info['final_episode_step'].tolist() != [20, 15, 20]:
            raise AssertionError('per-row clocks do not match the staggered reset')
        expected_final = np.stack((np.cos(terminal_q), np.sin(terminal_q), terminal_v), axis=1)[[0, 2]]
        actual_final = final[[0, 2]].cpu().numpy().copy()
        if (np.max(np.abs(actual_final[:, :2] - expected_final[:, :2])) > .01
                or np.max(np.abs(actual_final[:, 2] - expected_final[:, 2])) > .05):
            raise AssertionError('saved terminal observations do not describe the old transition')
        if torch.equal(final[[0, 2]], observation['state']['proprioception'][[0, 2]]):
            raise AssertionError('done observations did not switch to the new episode')
        env.step(action)
        if not torch.equal(final, preserved):
            raise AssertionError('terminal observation changed on a later step')
        result = {'scope': 'ordinary make_parallel_env device route', 'batch': 3, 'seed': 73,
                  'initial_q_rad': q0.tolist(), 'initial_qd_rad_s': v0.tolist(),
                  'first_q_rad': first_q.tolist(), 'first_qd_rad_s': first_v.tolist(),
                  'predicted_q_rad': predicted_q.tolist(), 'predicted_qd_rad_s': predicted_v.tolist(),
                  'q_tolerance_rad': .01, 'qd_tolerance_rad_s': .05,
                  'truncated': truncated.tolist(), 'episode_id': info['episode_id'].tolist(),
                  'terminal_observation_shape': list(final.shape), 'terminal_snapshot_retained': True,
                  'body_pose_fk_max_error': float(np.max(np.abs(measured_quat - expected_quat))),
                  'terminal_observation': actual_final.tolist(), 'expected_terminal_observation': expected_final.tolist(),
                  'terminal_previous_q_rad': terminal_q_before.tolist(),
                  'terminal_previous_qd_rad_s': terminal_v_before.tolist(),
                  'post_reset_observation': observation['state']['proprioception'][[0, 2]].cpu().tolist(),
                  'manual_mask_nonselected_unchanged': True, 'render_mode': env.render_mode,
                  'control_intervals': 21, 'native_batch_steps': 525, 'world_steps': 1575}
    finally:
        env.close()
    env.close()
    result['worker_closed'] = True
    return result


def _formal_render(worker_python):
    """Exercise the public batch route, device poses, and shared Rasterizer."""
    import numpy as np
    import torch
    from task_env import make_parallel_env

    config = {'execution': {'physics_provider': 'mujoco_warp', 'interpreter': worker_python},
              'episode': {'seed': 73, 'horizon': 200}}
    env = make_parallel_env('pendulum-v1', env_config=config, num_env=3, backend='cuda',
                            execution='device', render_mode='rgb_array', worker_directory=os.getcwd())
    try:
        env.reset(seed=73)
        initial_state = env.read_device_state(('qpos', 'body_position', 'body_orientation'))
        nondefault_stream = torch.cuda.Stream()
        with torch.cuda.stream(nondefault_stream):
            first = env.render()
            repeat = env.render()
        after_render = env.read_device_state(('qpos', 'body_position', 'body_orientation'))
        if (str(first.device) != 'cuda:0' or first.dtype != torch.uint8 or
                tuple(first.shape) != (480, 640, 3) or not torch.equal(first, repeat)):
            raise AssertionError('device Rasterizer frame dtype, shape, or repeated capture differs')
        if initial_state.identity != after_render.identity:
            raise AssertionError('render advanced physics or changed its boundary')
        action = {'torque': torch.tensor([[-1.5], [.5], [1.5]], device='cuda', dtype=torch.float32)}
        for _ in range(20):
            env.step(action)
        final_state = env.read_device_state(('qpos', 'body_position', 'body_orientation'))
        final = env.render()
        if torch.equal(first, final) or final_state.identity.native_step != 500:
            raise AssertionError('nonzero physics did not change the device render at the correct clock')
        initial_image = first.cpu().numpy()
        final_image = final.cpu().numpy()
        def blue_centroids(image):
            rgb = image.astype(np.float32)
            mask = ((rgb[:, :, 2] > 1.18 * rgb[:, :, 0])
                    & (rgb[:, :, 2] > 1.1 * rgb[:, :, 1]) & (rgb[:, :, 0] < 180))
            result = []
            for left, right in ((160, 240), (280, 360), (400, 480)):
                y, x = np.where(mask[:, left:right])
                if len(x) < 5:
                    raise AssertionError('an expected world has no visible blue mesh')
                result.append([float(x.mean() + left), float(y.mean())])
            return result
        before_xy, after_xy = blue_centroids(initial_image), blue_centroids(final_image)
        if not (before_xy[0][0] < before_xy[1][0] < before_xy[2][0]
                and after_xy[0][0] > before_xy[0][0] + 2
                and after_xy[1][0] < before_xy[1][0] - 2):
            raise AssertionError('world layout or opposing hinge motion is inconsistent')
        np.savez_compressed('device_frames.npz', initial=initial_image, final=final_image)
        return {'scope': 'formal device route to shared Rasterizer', 'batch': 3,
                'device': str(first.device), 'dtype': str(first.dtype), 'shape': list(first.shape),
                'initial_native_step': initial_state.identity.native_step,
                'after_repeated_capture_step': after_render.identity.native_step,
                'final_native_step': final_state.identity.native_step,
                'initial_q': initial_state.arrays['qpos'][:, 0].cpu().tolist(),
                'final_q': final_state.arrays['qpos'][:, 0].cpu().tolist(),
                'initial_mesh_centroids': before_xy, 'final_mesh_centroids': after_xy,
                'changed_pixels': int(np.count_nonzero(initial_image != final_image)),
                'native_batch_steps': 500, 'world_steps': 1500, 'closed': True}
    finally:
        env.close()


def _formal_camera(worker_python):
    """Capture configured finite-clip cameras through the public device lifecycle."""
    import numpy as np
    import torch
    from task_env import make_parallel_env

    config = {'execution': {'physics_provider': 'mujoco_warp', 'interpreter': worker_python},
              'episode': {'seed': 73, 'horizon': 200},
              'render': {'backend': 'rasterizer', 'camera_obs': True,
                         'cameras': [{'name': 'base', 'width': 128, 'height': 128,
                                      'rgb_dtype': 'uint8', 'near': .01, 'far': 3.0}]}}
    env = make_parallel_env('pendulum-v1', env_config=config, num_env=3, backend='cuda',
                            execution='device', worker_directory=os.getcwd())
    try:
        if env.observation_space['cameras']['base']['rgb'].shape != (3, 128, 128, 3):
            raise AssertionError('camera observation space does not match batch shape')
        observation, _ = env.reset(seed=73)
        first = observation['cameras']['base']['rgb'].clone()
        if first.device.type != 'cuda' or first.dtype != torch.uint8 or tuple(first.shape) != (3, 128, 128, 3):
            raise AssertionError('camera image is not CUDA uint8 BHWC')
        action = {'torque': torch.tensor([[-1.5], [.5], [1.5]], device='cuda', dtype=torch.float32)}
        for _ in range(20):
            observation, _, _, _, _ = env.step(action)
        last = observation['cameras']['base']['rgb']
        state = env.read_device_state(('qpos',))
        if state.identity.native_step != 500:
            raise AssertionError('camera capture changed the physics clock')
        changed = int(torch.count_nonzero(first != last).item())
        if not changed:
            raise AssertionError('camera image did not respond to nonzero motion')
        np.savez_compressed('camera_frames.npz', initial=first.cpu().numpy(), final=last.cpu().numpy())
        return {'scope': 'public MJWarp device camera and shared finite-clip rasterizer',
                'shape': list(first.shape), 'dtype': str(first.dtype), 'device': str(first.device),
                'changed_channels': changed, 'control_intervals': 20,
                'native_batch_steps': 500, 'world_steps': 1500, 'closed': True}
    finally:
        env.close()


def _x11_geochora_windows():
    """Find client windows, excluding the window manager's decoration frames."""
    import re

    tree = subprocess.check_output(['xwininfo', '-root', '-tree'], text=True)
    lines = [line.strip() for line in tree.splitlines() if 'GeoChora' in line]
    clients = {match.group(1) for line in lines
               if (match := re.match(r'(0x[0-9a-f]+)\s+"GeoChora[^"]*":\s+\("GeoChora"\s+"GeoChora"\)', line))}
    return clients, lines


def _formal_window(worker_python):
    """Exercise a real display and close its renderer independently of physics."""
    import torch
    from task_env import make_parallel_env

    config = {'execution': {'physics_provider': 'mujoco_warp', 'interpreter': worker_python},
              'episode': {'seed': 73, 'horizon': 200}}
    env = make_parallel_env('pendulum-v1', env_config=config, num_env=3, backend='cuda',
                            execution='device', render_mode='human', worker_directory=os.getcwd())
    try:
        env.reset(seed=73)
        initial = env.read_device_state(('qpos',)).identity
        existing_windows, _ = _x11_geochora_windows()
        if env.render() is not None:
            raise AssertionError('human presentation returned an image')
        windows, entries = _x11_geochora_windows()
        opened_windows = windows - existing_windows
        if len(opened_windows) != 1:
            raise AssertionError(f'expected one new Xorg client, got {opened_windows!r}; entries={entries!r}')
        presented = env.read_device_state(('qpos',)).identity
        if presented != initial:
            raise AssertionError('window presentation advanced physics')
        action = {'torque': torch.tensor([[-1.5], [.5], [1.5]], device='cuda', dtype=torch.float32)}
        for _ in range(20):
            env.step(action)
        env.render()
        before_close = env.read_device_state(('qpos',)).identity
        env.close_render()
        env.close_render()
        if opened_windows & _x11_geochora_windows()[0]:
            raise AssertionError('window client remained after renderer close')
        after_close = env.read_device_state(('qpos',)).identity
        if before_close != after_close:
            raise AssertionError('closing the window changed the physical boundary')
        env.step(action)
        after_step = env.read_device_state(('qpos',)).identity
        if after_step.native_step != before_close.native_step + 25:
            raise AssertionError('physics did not continue after the window closed')
        return {'display': os.environ.get('DISPLAY'), 'batch': 3, 'control_intervals': 21,
                'native_batch_steps': 525, 'world_steps': 1575,
                'initial_native_step': initial.native_step,
                'before_window_close': before_close.native_step,
                'after_window_close': after_close.native_step,
                'after_following_step': after_step.native_step, 'closed': True}
    finally:
        env.close()


def _record_device(worker_python, *, camera=False):
    """Record selected rows from the ordinary five-tuple device environment."""
    from dataclasses import asdict
    import numpy as np
    import torch
    from task_env import make_parallel_env
    from task_env.recorders import VectorTransitionRecorder

    config = {'execution': {'physics_provider': 'mujoco_warp', 'interpreter': worker_python},
              'episode': {'seed': 73, 'horizon': 20}}
    if camera:
        config['render'] = {'backend': 'rasterizer', 'camera_obs': True,
                            'cameras': [{'name': 'base', 'width': 128, 'height': 128,
                                         'rgb_dtype': 'uint8', 'near': .01, 'far': 3.0}]}
    env = make_parallel_env('pendulum-v1', env_config=config, num_env=3, backend='cuda',
                            execution='device', worker_directory=os.getcwd())
    recorder = VectorTransitionRecorder(env, path=os.getcwd(), env_ids=(0, 1))
    action = {'torque': torch.tensor([[-1.5], [.5], [1.5]], device='cuda', dtype=torch.float32)}
    expected = {}
    witnesses = {}

    def capture(slot, observation, info, *, flags=None):
        episode = int(info['episode_id'][slot].item())
        name = f'trajectory_slot_{slot:03d}_episode_{episode - 1:06d}'
        trace = witnesses.setdefault(name, {'contexts': [], 'states': [], 'images': [],
                                            'terminated': [], 'truncated': []})
        trace['contexts'].append({'schema_version': 'device-batch-boundary-v1',
                                  'env_id': int(info['env_id'][slot].item()),
                                  'episode_id': episode,
                                  'episode_step': int(info['episode_step'][slot].item()),
                                  **asdict(info['boundary'])})
        trace['states'].append(observation['state']['proprioception'][slot].cpu().numpy().copy())
        if camera:
            trace['images'].append(observation['cameras']['base']['rgb'][slot].cpu().numpy().copy())
        if flags is not None:
            trace['terminated'].append(bool(flags[0]))
            trace['truncated'].append(bool(flags[1]))

    def capture_step(observation, terminated, truncated, info):
        for slot in (0, 1):
            flags = (terminated[slot].item(), truncated[slot].item())
            ended = any(flags)
            capture(slot, info['final_observation'] if ended else observation,
                    info['final_info'] if ended else info, flags=flags)
            if ended:
                capture(slot, observation, info['reset_info'])

    try:
        obs, info = recorder.reset(seed=73)
        for slot in (0, 1):
            capture(slot, obs, info)
        expected['initial_0'] = obs['state']['proprioception'][0].cpu().numpy().copy()
        expected['initial_1'] = obs['state']['proprioception'][1].cpu().numpy().copy()
        if camera:
            for slot in (0, 1):
                expected[f'initial_{slot}_rgb'] = obs['cameras']['base']['rgb'][slot].cpu().numpy().copy()
        for tick in range(20):
            if tick == 5:
                obs, info = recorder.reset(mask=torch.tensor([False, True, False], device='cuda'))
                capture(1, obs, info)
                expected['reset_1'] = obs['state']['proprioception'][1].cpu().numpy().copy()
                if camera:
                    expected['reset_1_rgb'] = obs['cameras']['base']['rgb'][1].cpu().numpy().copy()
            obs, reward, terminated, truncated, info = recorder.step(action)
            capture_step(obs, terminated, truncated, info)
            if tick == 4:
                expected['old_1'] = obs['state']['proprioception'][1].cpu().numpy().copy()
                if camera:
                    expected['old_1_rgb'] = obs['cameras']['base']['rgb'][1].cpu().numpy().copy()
            if tick == 19:
                if info['_final_observation'].tolist() != [True, False, True]:
                    raise AssertionError('staggered terminal mask differs')
                expected['final_0'] = info['final_observation']['state']['proprioception'][0].cpu().numpy().copy()
                expected['next_0'] = obs['state']['proprioception'][0].cpu().numpy().copy()
                expected['last_1'] = obs['state']['proprioception'][1].cpu().numpy().copy()
                if camera:
                    expected['final_0_rgb'] = info['final_observation']['cameras']['base']['rgb'][0].cpu().numpy().copy()
                    expected['next_0_rgb'] = obs['cameras']['base']['rgb'][0].cpu().numpy().copy()
                    expected['last_1_rgb'] = obs['cameras']['base']['rgb'][1].cpu().numpy().copy()
        if camera:
            obs, _, terminated, truncated, info = recorder.step(action)
            capture_step(obs, terminated, truncated, info)
            expected['after_0'] = obs['state']['proprioception'][0].cpu().numpy().copy()
            expected['after_0_rgb'] = obs['cameras']['base']['rgb'][0].cpu().numpy().copy()
            expected['last_1'] = obs['state']['proprioception'][1].cpu().numpy().copy()
            expected['last_1_rgb'] = obs['cameras']['base']['rgb'][1].cpu().numpy().copy()
        np.savez('expected_record_values.npz', **expected)
        traces = {}
        contexts = {}
        for name, trace in witnesses.items():
            traces[name + '__state'] = np.stack(trace['states'])
            if camera:
                traces[name + '__rgb'] = np.stack(trace['images'])
            contexts[name] = {key: trace[key] for key in ('contexts', 'terminated', 'truncated')}
        np.savez_compressed('public_record_traces.npz', **traces)
        Path('public_record_contexts.json').write_text(json.dumps(contexts, indent=2) + '\n')
    finally:
        recorder.close()
    files = [path.name for path in recorder.saved_paths]
    if len(files) != (4 if camera else 3):
        raise AssertionError(f'unexpected staggered episode files: {files!r}')
    return {'scope': 'public device state and camera recording' if camera else 'public device state recording, no camera',
            'camera': camera, 'batch': 3,
            'recorded_env_ids': [0, 1], 'files': files, 'public_boundary_witness': True,
            'control_intervals': 21 if camera else 20,
            'native_batch_steps': 525 if camera else 500, 'world_steps': 1575 if camera else 1500,
            'closed': True}


def _isaac_device(worker_python, *, render=False, window=False, mount=False, sensor=False, record=False):
    """Use the existing scalar Isaac session as a second device-pose source."""
    import numpy as np
    import torch
    from task_env import make_env
    from task_env.tasks.pick_cube import build_readiness_solution

    if window and not render:
        raise ValueError('a window requires the shared renderer')
    if record and not sensor:
        raise ValueError('mounted recording requires the sensor')

    initial_window_ids = _x11_geochora_windows()[0] if os.environ.get('DISPLAY') else None
    config = {'execution': {'physics_provider': 'isaacsim', 'physics_backend': 'cuda',
                            'physics_device': 'cuda:0', 'interpreter': worker_python},
              'episode': {'seed': 31, 'horizon': 200}}
    env = make_env('pick-cube-p16-reference-v1', config=config)
    render_owner = visual_binding = visual_source = None
    primary = None
    try:
        obs, info = env.reset(seed=31)
        if 'cameras' in obs:
            raise AssertionError('sensor-off probe unexpectedly enabled task cameras')
        solution = build_readiness_solution(backend='cuda')
        solution.reset(obs, info, env.metadata)
        first = env.session.read_device_state(('body_position', 'body_orientation'))
        names = env.session.device_pose_names
        if 'panda-v1/hand' not in names or 'panda-v1/link0' not in names:
            raise AssertionError(f'Isaac source did not publish base and hand: {names!r}')
        if first.device != 'cuda:0' or first.arrays['body_position'].shape != (1, len(names), 3):
            raise AssertionError('Isaac public body poses have wrong device or shape')
        cube_index = names.index('cube-v1/cube')
        initial_cube_observation = np.asarray(obs['privileged_state']['cube_v1_body_pose'][0]).copy()
        if mount or sensor:
            from mount_fixture import capture, prepare, save
            specs, sensors, offset, grid_offsets = prepare(names)
            initial_mount = capture(sensors, offset, grid_offsets, first)
        if render or sensor:
            from task_env.environment.configuration import resolve_task_env_config
            from task_env.registry import ENV_REGISTRY
            from task_env.render.providers.parallel import ParallelRenderProvider
            from task_env.render.rasterizer.device import DeviceBatchRasterSource

            cls = ENV_REGISTRY.get('pick-cube-p16-reference-v1')
            visual_config = resolve_task_env_config(cls, {'execution': {'physics_provider': 'mujoco',
                'physics_backend': 'cpu', 'physics_device': 'cpu'}, 'episode': {'horizon': 200}})
            visual_binding = cls._build_selected_binding(visual_config)
            built = visual_binding.build_for_request('mujoco', 'cpu', 31, 200)
            visual_source = built['source']
            def robot_articulation(scene):
                entities = {robot.entity_id for robot in scene.robots}
                matches = [item.to_mapping() for item in scene.articulations if item.entity_id in entities]
                if len(matches) != 1:
                    raise ValueError('expected one declared visual robot articulation')
                return matches[0]
            if robot_articulation(visual_source.scene_definition) != robot_articulation(env.value['source'].scene_definition):
                raise ValueError('visual and physical Robot declarations differ')
            runtime = env.session
            if sensor:
                from task_env.runtime.contracts import DeviceBatchState
                class RepeatedScalarPose:
                    """Present one real scalar Isaac snapshot in three visual layout cells."""
                    def read_device_state(self, fields):
                        state = env.session.read_device_state(fields)
                        return DeviceBatchState(
                            {name: value.expand(3, *value.shape[1:]).clone()
                             for name, value in state.arrays.items()},
                            state.device, 3, state.identity, 'owned_snapshot')
                runtime = RepeatedScalarPose()
            render_source = DeviceBatchRasterSource(runtime=runtime, source=visual_source,
                                                     body_names=names, cameras=specs if sensor else ())
            render_owner = ParallelRenderProvider(num_envs=3 if sensor else 1, render_source=render_source,
                                                  width=640, height=480)
            if sensor:
                render_owner.enable_device_cameras()
                initial_sensor = render_owner.capture_cameras(state=first)
                for camera in specs:
                    frame = initial_sensor[camera.name]['rgb']
                    if (frame.dtype != torch.uint8 or str(frame.device) != 'cuda:0'
                            or tuple(frame.shape) != (3, 128, 128, 3)):
                        raise AssertionError('mounted camera returned an invalid device image')
                if torch.equal(initial_sensor['base']['rgb'], initial_sensor['hand']['rgb']):
                    raise AssertionError('base and hand cameras returned identical views')
                if record:
                    hand_index = names.index('panda-v1/hand')
                    record_frames = [initial_sensor['hand']['rgb'].clone()]
                    record_states = [first.arrays['body_position'][:, hand_index].expand(3, 3).clone()]
                    record_identities = [first.identity]
            if render:
                initial_frame = render_owner.render(mode='rgb_array')
                if (initial_frame.dtype != torch.uint8 or str(initial_frame.device) != 'cuda:0'
                        or tuple(initial_frame.shape) != (480, 640, 3)):
                    raise AssertionError('Isaac Rasterizer output has the wrong device frame contract')
            if window:
                import time
                existing_windows, _ = _x11_geochora_windows()
                if render_owner.render(mode='human') is not None:
                    raise AssertionError('human renderer unexpectedly returned an image')
                deadline = time.monotonic() + 3.0
                while True:
                    windows, entries = _x11_geochora_windows()
                    opened_windows = windows - existing_windows
                    if opened_windows or time.monotonic() >= deadline:
                        break
                    time.sleep(.1)
                if len(opened_windows) != 1:
                    raise AssertionError(f'expected one new Xorg client, got {opened_windows!r}; entries={entries!r}')
                if env.session.read_device_state(('body_position',)).identity != first.identity:
                    raise AssertionError('opening the window advanced Isaac physics')
        retained = first.arrays['body_position'].clone()
        repeat = env.session.read_device_state(('body_position', 'body_orientation'))
        if repeat.identity.native_step != first.identity.native_step:
            raise AssertionError('reading Isaac device poses advanced physics')
        completed = 0
        for _ in range(20):
            action = solution.act(obs, info)
            obs, reward, terminated, truncated, info = env.step(action)
            solution.observe(obs, reward, terminated, truncated, info)
            completed += 1
            if record and completed in (3, 6, 9, 12, 16, 20):
                boundary = env.session.read_device_state(('body_position', 'body_orientation'))
                camera_frame = render_owner.capture_cameras(state=boundary)['hand']['rgb']
                record_frames.append(camera_frame.clone())
                record_states.append(boundary.arrays['body_position'][:, hand_index].expand(3, 3).clone())
                record_identities.append(boundary.identity)
            if terminated or truncated or solution.done or solution.failed:
                break
        last = env.session.read_device_state(('body_position', 'body_orientation'))
        final_cube_observation = np.asarray(obs['privileged_state']['cube_v1_body_pose'][0]).copy()
        hand = names.index('panda-v1/hand')
        movement = float(torch.linalg.vector_norm(
            last.arrays['body_position'][0, hand] - first.arrays['body_position'][0, hand]).item())
        if completed != 20 or movement < 1e-4 or not torch.equal(first.arrays['body_position'], retained):
            raise AssertionError(f'Isaac hand motion, step count or owned snapshot differs: {movement}, {completed}')
        def cube_error(public_state, observed):
            position = public_state.arrays['body_position'][0, cube_index].cpu().numpy()
            quaternion = public_state.arrays['body_orientation'][0, cube_index].cpu().numpy()
            return max(float(np.abs(position - observed[:3]).max()),
                       min(float(np.abs(quaternion - observed[3:]).max()),
                           float(np.abs(quaternion + observed[3:]).max())))
        cube_pose_error = max(cube_error(first, initial_cube_observation),
                              cube_error(last, final_cube_observation))
        if cube_pose_error > 1e-4:
            raise AssertionError(f'Isaac device cube pose differs from public observation: {cube_pose_error}')
        mount_result = None
        if mount or sensor:
            final_mount = capture(sensors, offset, grid_offsets, last)
            if env.session.read_device_state(('body_position',)).identity != last.identity:
                raise AssertionError('camera mount resolution advanced Isaac physics')
            mount_result = save(specs, offset, grid_offsets, first, last, initial_mount, final_mount)
        sensor_result = None
        if sensor:
            final_sensor = render_owner.capture_cameras(state=last)
            arrays = {}
            for camera in specs:
                before = initial_sensor[camera.name]['rgb']
                after = final_sensor[camera.name]['rgb']
                change = int(torch.count_nonzero(before != after).item())
                if change == 0:
                    raise AssertionError(f'{camera.name} mounted camera did not reflect motion')
                arrays[f'{camera.name}_initial'] = before.cpu().numpy()
                arrays[f'{camera.name}_final'] = after.cpu().numpy()
            np.savez_compressed('isaac_sensor_frames.npz', **arrays)
            if env.session.read_device_state(('body_position',)).identity != last.identity:
                raise AssertionError('sensor capture advanced Isaac physics')
            sensor_result = {'cameras': [camera.name for camera in specs], 'shape': [3, 128, 128, 3],
                             'device': 'cuda:0', 'layout': 'one real scalar pose repeated into three visual cells'}
            mount_result['frame_capture'] = 'CUDA sensor frames saved in isaac_sensor_frames.npz'
        recording_result = None
        if record:
            from recording_fixture import record_frames as record_mounted_frames
            recording_result = record_mounted_frames(record_frames, record_states, record_identities, mounted=True)
        changed_pixels = None
        window_result = None
        if render:
            final_frame = render_owner.render(mode='rgb_array')
            initial_image, final_image = initial_frame.cpu().numpy(), final_frame.cpu().numpy()
            changed_pixels = int(np.count_nonzero(initial_image != final_image))
            if changed_pixels == 0:
                raise AssertionError('Isaac nonzero motion did not change the Rasterizer frame')
            np.savez_compressed('isaac_device_frames.npz', initial=initial_image, final=final_image)
            if window:
                render_owner.render(mode='human')
                after_present = env.session.read_device_state(('body_position',)).identity
                if after_present != last.identity:
                    raise AssertionError('window presentation advanced Isaac physics')
                render_owner.close_render()
                render_owner.close_render()
                if opened_windows & _x11_geochora_windows()[0]:
                    raise AssertionError('the Xorg window remained after renderer close')
                after_close = env.session.read_device_state(('body_position',)).identity
                if after_close != last.identity:
                    raise AssertionError('closing the renderer changed the Isaac boundary')
                if sensor:
                    after_window = render_owner.capture_cameras(state=last)
                    if any(not torch.equal(after_window[camera.name]['rgb'], final_sensor[camera.name]['rgb'])
                           for camera in specs):
                        raise AssertionError('closing window changed the sensor frame at the same boundary')
                action = solution.act(obs, info)
                obs, reward, terminated, truncated, info = env.step(action)
                solution.observe(obs, reward, terminated, truncated, info)
                continued = env.session.read_device_state(('body_position',)).identity
                substeps = env.value['artifact'].timebase.control_substeps
                if continued.native_step != last.identity.native_step + substeps:
                    raise AssertionError('Isaac physics did not continue after renderer close')
                window_result = {'display': os.environ.get('DISPLAY'), 'xorg_window_ids': sorted(opened_windows),
                    'sensor_enabled': sensor, 'before_close_step': last.identity.native_step,
                    'after_close_step': after_close.native_step,
                    'after_following_step': continued.native_step, 'renderer_closed': True}
        np.savez('isaac_pose_values.npz', initial=first.arrays['body_position'].cpu().numpy(),
                 final=last.arrays['body_position'].cpu().numpy(),
                 initial_orientation=first.arrays['body_orientation'].cpu().numpy(),
                 final_orientation=last.arrays['body_orientation'].cpu().numpy(),
                 initial_cube_observation=initial_cube_observation,
                 final_cube_observation=final_cube_observation)
        if (not window and initial_window_ids is not None
                and _x11_geochora_windows()[0] - initial_window_ids):
            raise AssertionError('window-off probe created a GeoChora window')
        return {'scope': 'existing scalar Isaac source and public CUDA pose; not parallel task qualification',
                'seed': 31, 'device': first.device, 'body_names': list(names),
                'initial_native_step': first.identity.native_step,
                'repeated_native_step': repeat.identity.native_step,
                'final_native_step': last.identity.native_step, 'hand_displacement_m': movement,
                'cube_public_observation_max_error': cube_pose_error,
                'renderer': 'geophys-rasterizer' if render or sensor else None, 'changed_pixels': changed_pixels,
                'sensor_enabled': sensor, 'window_enabled': window, 'sensor': sensor_result,
                'recording_fixture': recording_result,
                'window_absence_checked': not window and initial_window_ids is not None,
                'mount_pose_probe': mount_result,
                'control_intervals': completed + int(window), 'window': window_result, 'closed': True}
    except BaseException as error:
        primary = error
        raise
    finally:
        cleanup = None
        for owner in (render_owner, env):
            if owner is None:
                continue
            try:
                owner.close()
            except BaseException as error:
                if cleanup is None:
                    cleanup = error
                else:
                    cleanup.add_note(f'additional owner cleanup failed: {error!r}')
        if visual_binding is not None:
            from task_env.runtime.sessions.source import close_source_and_task_resources
            cleanup = close_source_and_task_resources(visual_source, visual_binding, error=cleanup)
        if cleanup is not None:
            if primary is not None:
                primary.add_note(f'Isaac diagnostic cleanup failed: {cleanup!r}')
            else:
                raise cleanup


def _clip_cuda():
    """Run the existing independent mesh clipping oracle directly on CUDA."""
    import importlib.util
    import io
    import taichi as ti

    path = Path(__file__).resolve().parents[5] / 'GeoPhys/test/verification/rendering/raster_clip_interval_cpu_smoke.py'
    spec = importlib.util.spec_from_file_location('raster_clip_interval_oracle', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    initialize = ti.init
    def initialize_cuda(*args, **kwargs):
        return initialize(arch=ti.cuda, device_memory_GB=.5, offline_cache=False)
    ti.init = initialize_cuda
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            module.main()
    finally:
        ti.init = initialize
        ti.reset()
    result = json.loads(output.getvalue().splitlines()[-1])
    result.update(scope='direct CUDA clipping oracle only; separate from engine admission',
                  oracle_path=str(path))
    return result


def _scalar_camera_schema(worker_python):
    """Check scalar CUDA camera observations through the public task lifecycle."""
    import numpy as np
    import torch
    from task_env import make_env

    config = {'execution': {'physics_provider': 'mujoco_warp', 'interpreter': worker_python},
              'episode': {'seed': 73, 'horizon': 20},
              'render': {'backend': 'rasterizer', 'camera_obs': True,
                         'cameras': [{'name': 'base', 'width': 128, 'height': 128,
                                      'rgb_dtype': 'uint8', 'near': .01, 'far': 3.0}]}}
    env = make_env('pendulum-v1', config=config, execution='device', worker_directory=os.getcwd())
    try:
        spaces = env.observation_space.spaces
        if 'cameras' not in spaces:
            raise AssertionError('configured scalar observation space has no cameras group')
        image = spaces['cameras']['base']['rgb']
        if tuple(image.shape) != (128, 128, 3) or str(image.dtype) != 'uint8':
            raise AssertionError('configured scalar camera has an incorrect RGB space')
        observation, _ = env.reset(seed=73)
        initial = observation['cameras']['base']['rgb'].clone()
        if initial.device.type != 'cuda' or initial.dtype != torch.uint8 or tuple(initial.shape) != (128, 128, 3):
            raise AssertionError('scalar camera is not CUDA uint8 HWC')
        action = {'torque': torch.tensor([.5], device='cuda', dtype=torch.float32)}
        for _ in range(20):
            observation, reward, terminated, truncated, info = env.step(action)
        if (reward.shape != () or terminated.shape != () or truncated.shape != ()
                or reward.dtype != torch.float32 or terminated.dtype != torch.bool or truncated.dtype != torch.bool
                or any(value.device.type != 'cuda' for value in (reward, terminated, truncated))
                or info['_final_observation'].shape != () or info['_final_observation'].dtype != torch.bool
                or not bool(truncated) or not bool(info['_final_observation'])):
            raise AssertionError('scalar reward, flags or terminal mask differs')
        final = info['final_observation']['cameras']['base']['rgb']
        reset = observation['cameras']['base']['rgb']
        if torch.equal(final, reset):
            raise AssertionError('scalar final image and new episode image are identical')
        retained = final.clone()
        env.step(action)
        if not torch.equal(final, retained) or env.read_device_state(('qpos',)).identity.native_step != 525:
            raise AssertionError('scalar terminal image ownership or native clock differs')
        np.savez_compressed('scalar_camera_frames.npz', initial=initial.cpu().numpy(),
                            final=final.cpu().numpy(), reset=reset.cpu().numpy())
        return {'scope': 'public scalar device task camera; same one-world lifecycle',
                'shape': list(initial.shape), 'dtype': str(initial.dtype), 'device': str(initial.device),
                'control_intervals': 21, 'native_batch_steps': 525, 'world_steps': 525,
                'terminal_snapshot_retained': True, 'closed': True}
    finally:
        env.close()


def _scalar_compat():
    """Check the existing public MuJoCo CPU Pendulum route after shared changes."""
    import mujoco
    import numpy as np
    from task_env import make_env

    original_step = mujoco.mj_step
    counts = {'calls': 0, 'substeps': 0}

    def counted_step(*args, **kwargs):
        counts['calls'] += 1
        counts['substeps'] += int(kwargs.get('nstep', args[2] if len(args) > 2 else 1))
        return original_step(*args, **kwargs)

    mujoco.mj_step = counted_step
    env = None
    try:
        env = make_env('pendulum-v1', config={'execution': {'physics_provider': 'mujoco',
                                                             'deployment': 'in_process'}})
        observation, _ = env.reset(seed=73)
        if not env.observation_space.contains(observation):
            raise ValueError('scalar reset observation is outside its space')
        action = {'torque': np.array([.5], dtype=np.float32)}
        completed_episodes = 0
        for _ in range(20):
            observation, reward, terminated, truncated, _ = env.step(action)
            if not env.observation_space.contains(observation) or not np.isfinite(reward):
                raise ValueError('scalar transition violates the existing observation contract')
            if terminated or truncated:
                completed_episodes += 1
                env.reset(seed=73 + completed_episodes)
        if counts['substeps'] != 500:
            raise ValueError(f'scalar physics count differs from the Task timebase: {counts}')
        result = {'scope': 'existing scalar public Pendulum route', 'provider': 'mujoco',
                  'mujoco': mujoco.__version__, 'seed': 73, 'control_intervals': 20,
                  'native_substeps': counts['substeps'], 'native_calls': counts['calls'],
                  'completed_episodes': completed_episodes,
                  'last_reward': float(reward)}
    finally:
        if env is not None:
            env.close()
        mujoco.mj_step = original_step
    result['closed'] = True
    return result


def _mount_intent():
    """Resolve real PickCube/Panda visual assets and two declared camera parents."""
    import hashlib
    import xml.etree.ElementTree as ET
    from task_env import make_env
    from task_env.environment.config import CameraSpec
    from task_env.observations.canonical_camera import CameraGeometry

    env = make_env('pick-cube-p16-reference-v1', config={
        'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process'},
        'episode': {'seed': 31}})
    try:
        manifest = env.binding.robot.asset_manifest()
        source_path, = manifest.mjcf_sources
        before = source_path.read_bytes()
        root = ET.fromstring(before)
        compiler = root.find('compiler')
        mesh_root = source_path.parent / compiler.get('meshdir', '')
        mesh_files = [mesh_root / item.get('file') for item in root.findall('./asset/mesh')
                      if item.get('file')]
        missing = [str(path) for path in mesh_files if not path.is_file()]
        if not mesh_files or missing:
            raise ValueError(f'Panda mesh files missing: {missing}')
        mappings = env.value['source'].bodies
        cameras = []
        for name, parent in (('base', 'panda-v1/link0'), ('hand', 'panda-v1/hand')):
            camera = CameraGeometry.from_camera_spec(CameraSpec(name, frame='body', parent=parent,
                width=128, height=128), task_artifact_hash=env.artifact.identity_hash)
            if camera.parent_frame not in mappings:
                raise ValueError(f'camera parent is absent from source: {parent}')
            cameras.append({'name': name, 'parent': camera.parent_frame,
                            'native_body': mappings[camera.parent_frame]})
        if source_path.read_bytes() != before:
            raise RuntimeError('Panda asset changed during camera declaration')
        return {'scope': 'offline source and camera intent only', 'seed': 31,
                'robot_source': manifest.source_reference, 'source_revision': manifest.source_revision,
                'panda_xml_sha256': hashlib.sha256(before).hexdigest(),
                'mesh_file_count': len(mesh_files), 'missing_meshes': missing,
                'cameras': cameras, 'physics_asset_modified': False}
    finally:
        env.close()


def _render_worker():
    """Publish the MJWarp model's live world poses through CUDA IPC."""
    with contextlib.redirect_stdout(sys.stderr):
        import numpy as np
        import mujoco
        import mujoco_warp as mjw
        import warp as wp
        from task_env.robots.pendulum import PENDULUM_MJCF_XML
        from task_env.tasks.pendulum import PENDULUM_TASK_SEMANTICS

        wp.init()
        device = wp.get_device('cuda:0')
        model = mujoco.MjModel.from_xml_string(PENDULUM_MJCF_XML)
        body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, 'pendulum_link')
        geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, 'pendulum_link_geom')
        with wp.ScopedMempool(device, False):
            batch_model = mjw.put_model(model)
            batch = mjw.put_data(model, mujoco.MjData(model), nworld=3)
        angles, speeds = zip(*(PENDULUM_TASK_SEMANTICS.sample_reset(np.random.default_rng(seed))
                               for seed in (73, 74, 75)))
        batch.qpos.assign(np.asarray(angles, dtype=np.float32).reshape(3, 1))
        batch.qvel.assign(np.asarray(speeds, dtype=np.float32).reshape(3, 1))
        batch.ctrl.assign(np.asarray([[1.5], [0.5], [-1.5]], dtype=np.float32))
        mjw.forward(batch_model, batch)
        ready = wp.Event(device=device, interprocess=True)
        wp.record_event(ready)
        payload = {'positions': _encode(batch.xpos.ipc_handle()),
                   'orientations': _encode(batch.xquat.ipc_handle()),
                   'ready': _encode(ready.ipc_handle()), 'body_count': model.nbody,
                   'body_id': body_id, 'radius': float(model.geom_size[geom_id, 0]),
                   'half_length': float(model.geom_size[geom_id, 1]),
                   'local_position': model.geom_pos[geom_id].tolist(),
                   'rgba': model.geom_rgba[geom_id].tolist()}
    _send(sys.stdout, payload)
    for _ in range(3):
        request = _receive(sys.stdin)
        with contextlib.redirect_stdout(sys.stderr):
            if request['step']:
                for _ in range(500):
                    mjw.step(batch_model, batch)
                mjw.forward(batch_model, batch)
                wp.record_event(ready)
            wp.synchronize_device(device)
            values = {'q_rad': float(batch.qpos.numpy()[0, 0]),
                      'time_s': float(batch.time.numpy()[0])}
        _send(sys.stdout, values)
    _receive(sys.stdin)
    with contextlib.redirect_stdout(sys.stderr):
        wp.synchronize_device(device)
        del ready, batch, batch_model
    _send(sys.stdout, {'closed': True})


def _raster(worker_python):
    """Exercise the public Taichi-field pose port and host Rasterizer frame."""
    import numpy as np
    import torch
    from cuda.bindings import driver as cu
    import taichi as ti
    from visualization.scene_source import SceneVisualizationSource
    from visualization.render_source import SurfaceMeshGeometry, RenderUpdateClass
    from visualization.rigid_transform_provider import build_rigid_render_transform_provider
    from visualization.mesh_builders import build_capsule_mesh

    ti.init(arch=ti.cuda, device_memory_GB=1, offline_cache=False)
    torch.cuda.init()
    stream = cu.CUstream(torch.cuda.current_stream().cuda_stream)
    process = subprocess.Popen([worker_python, '-u', __file__, '--render-worker'],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    pointers, ready, visualizer = [], None, None
    try:
        payload = _receive(process.stdout)
        for name in ('positions', 'orientations'):
            pointers.append(_check(cu.cuIpcOpenMemHandle(
                _ipc_handle(cu.CUipcMemHandle, _decode(payload[name])), 1)))
        ready = _check(cu.cuIpcOpenEventHandle(
            _ipc_handle(cu.CUipcEventHandle, _decode(payload['ready']))))
        count = payload['body_count']
        positions = ti.Vector.field(3, ti.f32, shape=count)
        orientations = ti.Vector.field(4, ti.f32, shape=count)
        position_tensor = torch.empty((count, 3), dtype=torch.float32, device='cuda')
        orientation_tensor = torch.empty((count, 4), dtype=torch.float32, device='cuda')

        def transfer_pose():
            _check(cu.cuStreamWaitEvent(stream, ready, 0))
            _check(cu.cuMemcpyDtoDAsync(position_tensor.data_ptr(), pointers[0], count * 12, stream))
            _check(cu.cuMemcpyDtoDAsync(orientation_tensor.data_ptr(), pointers[1], count * 16, stream))
            torch.cuda.current_stream().synchronize()
            positions.from_torch(position_tensor)
            orientations.from_torch(orientation_tensor)
            ti.sync()

        provider = build_rigid_render_transform_provider(provider_id='mjwarp-foreign-pose',
            body_count=count, positions=positions, orientations=orientations, live=True)
        vertices, indices, normals = build_capsule_mesh(payload['radius'], payload['half_length'])
        vertices += np.asarray(payload['local_position'], dtype=np.float32)
        surface = SurfaceMeshGeometry(body_id=payload['body_id'], vertices=vertices,
            indices=indices, normals=normals, color=tuple(payload['rgba'][:3]),
            update_class=RenderUpdateClass.TRANSFORM_ONLY)

        class ForeignPoseSource:
            domain_min_vec = np.array([-1., -1., -1.], dtype=np.float32)
            domain_max_vec = np.array([1., 1., 1.], dtype=np.float32)
            ground = None
            def read_surface_geometries(self): return (surface,)
            def read_external_render_geometries(self): return (surface,)
            def read_static_geometries(self): return ()
            def read_debug_geometries(self): return ()
            def read_rigid_render_transform_provider(self): return provider

        source = SceneVisualizationSource(geometry_sources=(ForeignPoseSource(),))
        transfer_pose()
        visualizer = source.build_visualizer(backend='rasterizer', use_render_snapshot=False,
            width=128, height=128, max_framebuffer_resolution=(128, 128),
            enable_shadow=False, enable_ssao=False, enable_fxaa=False,
            enable_taa=False, raster_acceleration='compute')
        visualizer.set_camera_pose((0., -2., .25), (0., 0., .25), (0., 0., 1.))
        _send(process.stdin, {'step': False})
        initial_state = _receive(process.stdout)
        first = visualizer.read_frame(synchronized=True)
        repeated = visualizer.read_frame(synchronized=True)
        _send(process.stdin, {'step': False})
        after_repeated_render = _receive(process.stdout)
        _send(process.stdin, {'step': True})
        final_state = _receive(process.stdout)
        transfer_pose()
        last = visualizer.read_frame(synchronized=True)
        if first.shape != (128, 128, 3) or not np.isfinite(first).all():
            raise ValueError('invalid Rasterizer host RGB frame')
        np.savez_compressed('frames.npz', initial=first, repeated=repeated, final=last)
        difference = float(np.max(np.abs(last - first)))
        if difference <= 0 or final_state['time_s'] <= initial_state['time_s']:
            raise AssertionError('nonzero physics step did not produce a new frame')
        if after_repeated_render != initial_state:
            raise AssertionError('render changed the physics state or clock')
        def blue_centroid(frame):
            mask = ((frame[:, :, 2] > 1.3 * frame[:, :, 0])
                    & (frame[:, :, 2] > 1.2 * frame[:, :, 1]))
            y, x = np.where(mask)
            if len(x) < 20:
                raise AssertionError('Pendulum mesh was not visible')
            return [float(x.mean()), float(y.mean())]
        first_centroid = blue_centroid(first)
        last_centroid = blue_centroid(last)
        # Camera looks along +Y; the declared +Y hinge moves the +Z link
        # toward screen right for a positive sine.  This bounded spatial
        # oracle is independent of the renderer's transform fields.
        if not (np.sin(final_state['q_rad']) > 0.5
                and last_centroid[0] > first_centroid[0] + 5
                and last_centroid[1] > first_centroid[1] + 3):
            raise AssertionError('image centroid disagrees with hinge-axis geometry')
        visualizer.close(); visualizer = None
        for pointer in pointers:
            _check(cu.cuIpcCloseMemHandle(pointer))
        pointers.clear()
        _check(cu.cuEventDestroy(ready)); ready = None
        _send(process.stdin, {'close': True})
        closed = _receive(process.stdout)
        if not closed['closed'] or process.wait(timeout=20) != 0:
            raise RuntimeError('render physics worker did not close')
        return {'source': 'MJWarp Pendulum B=3 world 0', 'initial': initial_state,
                'after_repeated_render': after_repeated_render, 'final': final_state,
                'pose_transfer': 'CUDA IPC + device copy to Taichi fields',
                'image': {'shape': first.shape, 'dtype': str(first.dtype), 'device': 'host',
                          'max_change': difference, 'file': 'frames.npz',
                          'initial_blue_centroid_xy': first_centroid,
                          'final_blue_centroid_xy': last_centroid},
                'repeated_render_max_change': float(np.max(np.abs(repeated - first))),
                'control_intervals': 20, 'native_batch_steps': 500, 'worker_closed': True}
    finally:
        if visualizer is not None:
            visualizer.close()
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        for pointer in pointers:
            _check(cu.cuIpcCloseMemHandle(pointer))
        if ready is not None:
            _check(cu.cuEventDestroy(ready))
        ti.reset()


def _gpu_group_mib(group):
    processes = subprocess.check_output(['ps', '-eo', 'pid=,pgid='], text=True)
    members = {int(pid) for pid, pgid in (line.split() for line in processes.splitlines())
               if int(pgid) == group}
    apps = subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid,used_gpu_memory',
                                    '--format=csv,noheader,nounits'], text=True)
    return sum(int(memory.strip()) for line in apps.splitlines() if line.strip()
               for pid, memory in [line.split(',', 1)] if int(pid.strip()) in members)


def _run(worker_python, output, case):
    import fcntl
    import signal
    import time
    from task_env.script.agent import builtin_example_validation as harness
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    if case == 'example':
        example = Path(__file__).resolve().parents[5] / 'examples/parallel/pendulum_device.py'
        command = [sys.executable, '-u', str(example), '--interpreter', worker_python,
                   '--output', str(output / 'result.json')]
    elif case in ('framebuffer-device', 'geophys-camera'):
        filename = ('test_framebuffer_device_rgb.py' if case == 'framebuffer-device'
                    else 'test_raster_task_camera_binding.py')
        test = Path(__file__).resolve().parents[5] / 'GeoPhys/test/verification/rendering' / filename
        command = [sys.executable, '-m', 'pytest', '-q', str(test)]
    elif case == 'transport-regression':
        test = Path(__file__).resolve().parents[5] / 'task_env/diagnostics/tasks/test_v211_g03_3a_transport.py'
        command = [sys.executable, '-m', 'pytest', '-q', str(test)]
    elif case == 'core-semantics':
        test = Path(__file__).resolve().parent / 'test_device_semantics.py'
        command = [sys.executable, '-m', 'pytest', '-q', str(test)]
    elif case == 'geophys-aot-core':
        test = Path(__file__).resolve().parents[5] / 'GeoPhys/test/verification/rendering/test_raster_lighting_component.py'
        command = [sys.executable, '-m', 'pytest', '-q', str(test) + '::test_raster_lighting_component[constant]']
    elif case == 'geophys-merge-regression':
        root = Path(__file__).resolve().parents[5] / 'GeoPhys'
        tests = ['test/verification/rigid/test_rigid_state_host_io.py',
                 'test/verification/agent/test_agent_contracts.py',
                 'test/verification/rendering/test_raster_task_camera_binding.py']
        command = [sys.executable, '-m', 'pytest', '-q', *(str(root / name) for name in tests)]
    elif case == 'geophys-merge-clip':
        test = Path(__file__).resolve().parents[5] / 'GeoPhys/test/verification/rendering/raster_clip_interval_cpu_smoke.py'
        command = [sys.executable, str(test)]
    elif case == 'geophys-merge-focused':
        root = Path(__file__).resolve().parents[5] / 'GeoPhys'
        tests = ['test/verification/rigid/test_rigid_state_host_io.py',
                 'test/verification/rendering/test_raster_task_camera_binding.py',
                 'test/verification/agent/test_agent_contracts.py::test_control_exports_robot_arm_owner_and_keeps_driver_abi_exact']
        command = [sys.executable, '-m', 'pytest', '-q', *(str(root / name) for name in tests)]
    elif case == 'geophys-merge-lighting':
        root = Path(__file__).resolve().parents[5] / 'GeoPhys/test/verification/rendering'
        command = [sys.executable, '-m', 'pytest', '-q', str(root / 'test_raster_lighting_component.py'),
                   str(root / 'test_punctual_shadow_batches.py'), str(root / 'test_builtin_area_lights.py')]
    elif case == 'geophys-merge-mjcf-light':
        test = Path(__file__).resolve().parents[5] / 'GeoPhys/test/verification/rendering/mjcf_light_cpu_smoke.py'
        command = [sys.executable, str(test)]
    elif case == 'geophys-merge-rigid':
        root = Path(__file__).resolve().parents[5] / 'GeoPhys/test/verification/rigid'
        command = [sys.executable, '-m', 'pytest', '-q', str(root / 'test_rigid_actuator_force_limits.py'),
                   str(root / 'test_rigid_state_snapshot_restore.py')]
    elif case == 'geophys-merge-robot':
        test = Path(__file__).resolve().parents[5] / 'GeoPhys/test/verification/rigid/robot_arm_control_runtime_smoke.py'
        command = [sys.executable, str(test)]
    elif case == 'core-regression':
        root = Path(__file__).resolve().parents[5]
        tests = [
            'task_env/diagnostics/tasks/v2.1.1/g06/test_device_semantics.py',
            'task_env/diagnostics/tasks/v2.1.1/test_component_source_declarations.py',
            'task_env/diagnostics/tasks/v2.1.1/test_renderer_capabilities.py',
            'task_env/diagnostics/tasks/v2.1.1/test_recording_observation_metadata.py',
            'task_env/diagnostics/tasks/v2.1.1/test_recording_preflight.py',
            'task_env/diagnostics/tasks/v2.1.1/test_physical_recording_readback.py',
            'task_env/diagnostics/tasks/test_v211_render_fault_cleanup.py',
            'task_env/diagnostics/tasks/test_v211_render_binding.py',
            'task_env/diagnostics/tasks/test_v211_g03_3a_transport.py',
            'task_env/diagnostics/tasks/test_v211_physical_recording.py',
            'task_env/diagnostics/tasks/test_phase_ii_c05a_structured_recording.py',
        ]
        command = [sys.executable, '-m', 'pytest', '-q', *(str(root / name) for name in tests)]
    elif case == 'physics':
        command = [worker_python, '-u', __file__, '--physics']
    else:
        role = {'ipc': '--parent', 'raster': '--raster', 'transport-physics': '--transport-physics',
                'session-physics': '--session-physics', 'formal-device': '--formal-device',
                'transport-frames': '--transport-frames',
                'formal-render': '--formal-render',
                'formal-camera': '--formal-camera',
                'formal-frames': '--formal-frames',
                'formal-window': '--formal-window',
                'record-device': '--record-device',
                'record-camera': '--record-camera',
                'record-render-fixture': '--record-render-fixture',
                'clip-cuda': '--clip-cuda',
                'isaac-device': '--isaac-device',
                'isaac-render': '--isaac-render',
                'isaac-window': '--isaac-window',
                'isaac-mount': '--isaac-mount',
                'isaac-sensor': '--isaac-sensor',
                'isaac-sensor-window': '--isaac-sensor-window',
                'isaac-sensor-record': '--isaac-sensor-record',
                'scalar': '--scalar', 'scalar-camera-schema': '--scalar-camera-schema'}[case]
        command = [sys.executable, '-u', __file__, role,
                   '--worker-python', worker_python]
    start = time.monotonic()
    with harness._open_shared_native_lock() as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        legacy = harness.LEGACY_LOCK.exists()
        if not harness._lock_matches_legacy(lock, require_legacy=legacy):
            raise RuntimeError('native lock alias differs')
        with (output / 'stdout.log').open('wb') as out, (output / 'stderr.log').open('wb') as err:
            with harness._supervised_worker(command, environment=os.environ, stdout=out, stderr=err,
                    cwd=output, lock_fd=lock.fileno()) as (proc, state):
                violation = None
                while proc.poll() is None:
                    if not harness._lock_matches_legacy(lock, require_legacy=legacy):
                        violation = 'shared lock changed'
                    elif time.monotonic() - start > 900:
                        violation = '900 second wall timeout'
                    elif harness._mem_available_bytes() < 1024**3:
                        violation = 'less than 1 GiB host memory available'
                    elif harness._proc_rss_tree(proc.pid) > 10 * 1024**3:
                        violation = 'process tree exceeds 10 GiB RSS'
                    elif harness._gpu_free_mib() < 512:
                        violation = 'less than 512 MiB GPU memory available'
                    elif _gpu_group_mib(proc.pid) > 6144:
                        violation = 'process group exceeds 6144 MiB GPU memory'
                    elif harness._directory_bytes(output) > 256 * 1024**2:
                        violation = 'evidence exceeds 256 MiB'
                    if violation:
                        harness._kill_process_group(proc, signal.SIGTERM)
                        break
                    time.sleep(1)
                code = proc.wait(timeout=10)
            receipt = {'exit_code': code, 'violation': violation,
                       'forced_retirement': state['forced_retirement'],
                       'wall_seconds': time.monotonic() - start}
    (output / 'supervisor.json').write_text(json.dumps(receipt, indent=2) + '\n')
    if code != 0 or violation or state['forced_retirement']:
        raise RuntimeError(f'IPC probe failed: {receipt}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--parent', action='store_true')
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--physics', action='store_true')
    parser.add_argument('--render-worker', action='store_true')
    parser.add_argument('--raster', action='store_true')
    parser.add_argument('--mount-intent', action='store_true')
    parser.add_argument('--transport-physics', action='store_true')
    parser.add_argument('--transport-frames', action='store_true')
    parser.add_argument('--session-physics', action='store_true')
    parser.add_argument('--formal-device', action='store_true')
    parser.add_argument('--formal-render', action='store_true')
    parser.add_argument('--formal-camera', action='store_true')
    parser.add_argument('--formal-frames', action='store_true')
    parser.add_argument('--formal-window', action='store_true')
    parser.add_argument('--record-device', action='store_true')
    parser.add_argument('--record-camera', action='store_true')
    parser.add_argument('--record-render-fixture', action='store_true')
    parser.add_argument('--clip-cuda', action='store_true')
    parser.add_argument('--isaac-device', action='store_true')
    parser.add_argument('--isaac-render', action='store_true')
    parser.add_argument('--isaac-window', action='store_true')
    parser.add_argument('--isaac-mount', action='store_true')
    parser.add_argument('--isaac-sensor', action='store_true')
    parser.add_argument('--isaac-sensor-window', action='store_true')
    parser.add_argument('--isaac-sensor-record', action='store_true')
    parser.add_argument('--scalar', action='store_true')
    parser.add_argument('--scalar-camera-schema', action='store_true')
    parser.add_argument('--case', choices=('ipc', 'physics', 'raster', 'transport-physics', 'transport-frames', 'session-physics',
                                           'formal-device', 'formal-render', 'formal-camera', 'formal-frames', 'formal-window', 'record-device', 'record-camera', 'record-render-fixture', 'clip-cuda', 'isaac-device', 'isaac-render', 'isaac-window', 'isaac-mount', 'isaac-sensor', 'isaac-sensor-window', 'isaac-sensor-record', 'example', 'scalar', 'scalar-camera-schema', 'framebuffer-device',
                                           'geophys-camera', 'geophys-aot-core', 'geophys-merge-regression', 'geophys-merge-clip', 'geophys-merge-focused', 'geophys-merge-lighting', 'geophys-merge-mjcf-light', 'geophys-merge-rigid', 'geophys-merge-robot', 'transport-regression', 'core-semantics', 'core-regression'),
                        default='ipc')
    parser.add_argument('--worker-python')
    parser.add_argument('--output')
    args = parser.parse_args()
    if args.worker:
        _worker()
    elif args.render_worker:
        _render_worker()
    elif args.parent:
        print(json.dumps(_parent(args.worker_python)))
    elif args.raster:
        print(json.dumps(_raster(args.worker_python)))
    elif args.mount_intent:
        print(json.dumps(_mount_intent()))
    elif args.transport_physics:
        print(json.dumps(_transport_physics(args.worker_python)))
    elif args.transport_frames:
        print(json.dumps(_transport_physics(args.worker_python, frame_probe=True)))
    elif args.session_physics:
        print(json.dumps(_session_physics(args.worker_python)))
    elif args.formal_device:
        print(json.dumps(_formal_device(args.worker_python)))
    elif args.formal_render:
        print(json.dumps(_formal_render(args.worker_python)))
    elif args.formal_camera:
        print(json.dumps(_formal_camera(args.worker_python)))
    elif args.formal_frames:
        from frame_fixture import run
        print(json.dumps(run(args.worker_python)))
    elif args.formal_window:
        print(json.dumps(_formal_window(args.worker_python)))
    elif args.record_device:
        print(json.dumps(_record_device(args.worker_python)))
    elif args.record_camera:
        print(json.dumps(_record_device(args.worker_python, camera=True)))
    elif args.record_render_fixture:
        from recording_fixture import run
        print(json.dumps(run(args.worker_python)))
    elif args.clip_cuda:
        print(json.dumps(_clip_cuda()))
    elif args.isaac_device:
        print(json.dumps(_isaac_device(args.worker_python)))
    elif args.isaac_render:
        print(json.dumps(_isaac_device(args.worker_python, render=True)))
    elif args.isaac_window:
        print(json.dumps(_isaac_device(args.worker_python, render=True, window=True)))
    elif args.isaac_mount:
        print(json.dumps(_isaac_device(args.worker_python, mount=True)))
    elif args.isaac_sensor:
        print(json.dumps(_isaac_device(args.worker_python, sensor=True)))
    elif args.isaac_sensor_window:
        print(json.dumps(_isaac_device(args.worker_python, render=True, window=True, sensor=True)))
    elif args.isaac_sensor_record:
        print(json.dumps(_isaac_device(args.worker_python, sensor=True, record=True)))
    elif args.scalar:
        print(json.dumps(_scalar_compat()))
    elif args.scalar_camera_schema:
        print(json.dumps(_scalar_camera_schema(args.worker_python)))
    elif args.physics:
        print(json.dumps(_physics()))
    elif args.run:
        _run(args.worker_python, args.output, args.case)
    else:
        parser.error('choose --run, --parent or --worker')


if __name__ == '__main__':
    main()
