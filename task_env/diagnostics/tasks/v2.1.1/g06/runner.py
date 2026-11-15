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


def _duplex_worker():
    import torch
    from task_env.runtime.transport.cuda_ipc import CudaIpcDuplexPublisher

    publisher = CudaIpcDuplexPublisher({'output': ((2,), 'float32'),
                                        'input': ((2,), 'float32'), 'mask': ((2,), 'bool')})
    try:
        publisher.publish({'output': torch.tensor([1., 2.], device='cuda')})
        _send(sys.stdout, publisher.description())
        publisher.bind_written_event(_receive(sys.stdin)['written'])
        inputs = publisher.read_inputs(('input', 'mask'))
        observed = inputs['input'].cpu().tolist()
        mask = inputs['mask'].cpu().tolist()
        if observed != [4., 7.] or mask != [True, False]:
            raise AssertionError('CUDA duplex worker inputs differ')
        publisher.publish({'output': torch.where(inputs['mask'], 2 * inputs['input'], inputs['input'])})
        _send(sys.stdout, {'observed': observed, 'mask': mask})
        _receive(sys.stdin)
    finally:
        publisher.close()
    _send(sys.stdout, {'closed': True})


def _duplex_parent():
    import torch
    from task_env.runtime.transport.cuda_ipc import CudaIpcConnection

    process = subprocess.Popen([sys.executable, '-u', __file__, '--duplex-worker'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    connection = None
    try:
        connection = CudaIpcConnection(_receive(process.stdout))
        connection.wait_ready()
        first = connection.read('output')
        connection.synchronize()
        if first.cpu().tolist() != [1., 2.]:
            raise AssertionError('CUDA duplex initial output differs')
        connection.write('input', torch.tensor([4., 7.], device='cuda'))
        connection.write('mask', torch.tensor([True, False], device='cuda'))
        connection.record_written()
        _send(process.stdin, {'written': connection.written_handle})
        result = _receive(process.stdout)
        connection.wait_ready()
        final = connection.read('output')
        connection.synchronize()
        if final.cpu().tolist() != [8., 7.]:
            raise AssertionError('CUDA duplex final output differs')
        connection.release_imports()
        _send(process.stdin, {'close': True})
        if not _receive(process.stdout)['closed'] or process.wait(timeout=20) != 0:
            raise AssertionError('CUDA duplex worker did not close')
        return {'scope': 'CUDA driver duplex IPC', 'initial': first.cpu().tolist(),
                'worker_observed': result['observed'], 'mask': result['mask'],
                'final': final.cpu().tolist(), 'closed': True}
    finally:
        if connection is not None:
            connection.release_imports()
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        if connection is not None:
            connection.close()


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


def _pickcube_execution(provider, interpreter):
    execution = {'physics_provider': provider, 'interpreter': interpreter}
    if provider == 'geophys':
        execution['geophys_contact_mode'] = 'discrete'
    return execution


def _pickcube_camera_configuration():
    import math
    cy, sy, cp, sp = (math.cos(.45 / 2), math.sin(.45 / 2),
                      math.cos(.25 / 2), math.sin(.25 / 2))
    return {'backend': 'rasterizer', 'camera_obs': True, 'cameras': [
                  {'name': 'base', 'frame': 'body', 'parent': 'panda-v1/link0',
                   'width': 128, 'height': 128, 'rgb_dtype': 'uint8', 'position': [-.35, -.4, .8],
                   'quaternion_wxyz': [cy * cp, -sy * sp, cy * sp, sy * cp], 'near': .01, 'far': 3.},
                  {'name': 'hand', 'frame': 'body', 'parent': 'panda-v1/hand',
                   'width': 128, 'height': 128, 'rgb_dtype': 'uint8', 'position': [.075, 0., -.15],
                   'quaternion_wxyz': [math.sqrt(.5), 0., -math.sqrt(.5), 0.], 'near': .01, 'far': 3.}]}


def _pickcube_camera_probe(worker_python, *, provider='mujoco_warp'):
    """Capture real source-mounted base and hand cameras for three worlds."""
    import numpy as np
    import torch
    from task_env import make_parallel_env

    config = {'execution': _pickcube_execution(provider, worker_python),
              'controller': {'profile_id': 'panda-direct-effort-v1'},
              'robot': {'native_drive': 'disabled'}, 'episode': {'seed': 31, 'horizon': 20},
              'render': _pickcube_camera_configuration()}
    env = make_parallel_env('pick-cube-p16-reference-v1', env_config=config, num_env=3,
                            backend='cuda', execution='device', worker_directory=os.getcwd())
    try:
        obs, _ = env.reset(seed=31)
        first = env.read_device_state(('body_position', 'body_orientation'))
        frames = {}
        for name in ('base', 'hand'):
            image = obs['cameras'][name]['rgb']
            if image.device.type != 'cuda' or image.dtype != torch.uint8 or tuple(image.shape) != (3, 128, 128, 3):
                raise AssertionError('camera image does not match declared device shape or dtype')
            frames[name + '_initial'] = image.clone().cpu().numpy()
        np.savez_compressed('pickcube_camera_initial.npz', **frames)
        action = torch.zeros((3, 8), device='cuda')
        action[:, 0] = torch.tensor([5., 0., -5.], device='cuda')
        for _ in range(10):
            obs, _, _, _, _ = env.step({'effort': action})
        last = env.read_device_state(('body_position', 'body_orientation'))
        if last.identity.native_step - first.identity.native_step != 50:
            raise AssertionError('camera capture advanced the native physics clock')
        for name in ('base', 'hand'):
            frames[name + '_final'] = obs['cameras'][name]['rgb'].cpu().numpy().copy()
            if any(len(np.unique(image.reshape(-1, 3), axis=0)) < 10
                   for image in frames[name + '_initial']):
                raise AssertionError(f'{name} camera image lacks visible scene detail')
        frames.update(initial_body_position=first.arrays['body_position'].cpu().numpy(),
                      initial_body_orientation=first.arrays['body_orientation'].cpu().numpy(),
                      final_body_position=last.arrays['body_position'].cpu().numpy(),
                      final_body_orientation=last.arrays['body_orientation'].cpu().numpy(),
                      body_names=np.asarray(env.robot.body_names))
        hand_index = env.robot.body_names.index('panda-v1/hand')
        movement = np.linalg.norm(frames['final_body_position'][:, hand_index] -
                                  frames['initial_body_position'][:, hand_index], axis=1)
        if float(movement.max()) < 1e-4:
            raise AssertionError('native hand did not move')
        np.savez_compressed('pickcube_camera_probe.npz', **frames)
        return {'scope': f'PickCube {provider} camera integration probe, not projection qualification',
                'batch': 3, 'hand_motion_m': movement.tolist(), 'native_steps': 50,
                'camera_names': ['base', 'hand'], 'image_shape': [3, 128, 128, 3]}
    finally:
        env.close()


def _pickcube_window_probe(worker_python, *, provider, sensor):
    """Check window lifetime independently from optional task cameras."""
    import torch
    from task_env import make_parallel_env

    config = {'execution': _pickcube_execution(provider, worker_python),
              'controller': {'profile_id': 'panda-direct-effort-v1'},
              'robot': {'native_drive': 'disabled'}, 'episode': {'seed': 31, 'horizon': 20}}
    if sensor:
        config['render'] = _pickcube_camera_configuration()
    env = make_parallel_env('pick-cube-p16-reference-v1', env_config=config, num_env=3,
                            backend='cuda', execution='device', render_mode='human',
                            worker_directory=os.getcwd())
    try:
        observation, _ = env.reset(seed=31)
        env.set_parallel_render_num(3)
        initial = env.read_device_state(('qpos',)).identity
        env.render()
        env.render()
        if env.read_device_state(('qpos',)).identity != initial:
            raise AssertionError('window presentation advanced physics')
        env.close_render()
        if env.read_device_state(('qpos',)).identity != initial:
            raise AssertionError('closing the window advanced physics')
        action = torch.zeros((3, *env.single_action_space['effort'].shape), device='cuda')
        action[:, 0] = torch.tensor([5., 0., -5.], device='cuda')
        observation, _, _, _, _ = env.step({'effort': action})
        after = env.read_device_state(('qpos',)).identity
        if after.native_step - initial.native_step != 5:
            raise AssertionError('physics did not continue after window close')
        if sensor:
            for camera in ('base', 'hand'):
                rgb = observation['cameras'][camera]['rgb']
                if tuple(rgb.shape) != (3, 128, 128, 3) or rgb.dtype != torch.uint8 or rgb.device.type != 'cuda':
                    raise AssertionError('task camera stopped after closing the window')
        elif 'cameras' in observation:
            raise AssertionError('window-only configuration added cameras to the observation')
        return {'scope': f'{provider} PickCube real window close and continued physics',
                'sensor_enabled': sensor, 'native_step_before': initial.native_step,
                'displayed_envs': 3,
                'native_step_after': after.native_step, 'sensor_continued_after_close': sensor,
                'window_presented_twice_without_step': True}
    finally:
        env.close()


def _geophys_pickcube_plan(*, contact_mode='provider_default', world_count=3):
    """Inspect real source-to-rigid-batch admission without starting physics."""
    from task_env.assembly import compile_task_scene
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.registry import ENV_REGISTRY
    from task_env.runtime.sessions.geophys_source import GeoPhysSourceComposer
    from task_env.runtime.sessions.source import close_source_and_task_resources
    from solvers.rigid.config import RigidSolverConfig
    from solvers.rigid.planning.batch_plan import build_rigid_batch_plan

    task = ENV_REGISTRY.get('pick-cube-p16-reference-v1')
    execution = {'physics_provider': 'geophys'}
    if contact_mode != 'provider_default':
        execution['geophys_contact_mode'] = contact_mode
    config = resolve_task_env_config(task, {'execution': execution,
        'controller': {'profile_id': 'panda-direct-effort-v1'},
        'robot': {'native_drive': 'disabled'}, 'episode': {'seed': 31, 'horizon': 20}},
        execution_scope='device_batch')
    binding = task._build_selected_binding(config)
    built = binding.build_for_request('geophys', 'cuda', 31, 20)
    source = built['source']
    composer = GeoPhysSourceComposer(source.scene_source, scene_definition=source.scene_definition,
        source_closure_digest=source.source_closure_digest, execution_source_receipt=source.execution_source_receipt)
    try:
        compiled = compile_task_scene(composition=source.composition, scene=source.scene,
            agents=source.agents, objects=source.objects, scene_composer=composer)
        options = {'dt': built['artifact'].timebase.physics_dt, 'gravity': config.environment.runtime.gravity,
                   'integrator': 'euler', 'enable_ground_contact': False,
                   'enable_domain_boundary_contact': False,
                   'broadphase': config.environment.runtime.broadphase}
        if contact_mode != 'provider_default':
            options['enable_ccd'] = contact_mode == 'continuous'
        plan = build_rigid_batch_plan(compiled.scene_model, world_count=world_count,
                                     config=RigidSolverConfig.from_legacy_kwargs(options))
        data = compiled.scene_model.joint_data
        return {'scope': 'GeoPhys registered PickCube source and batch planning; no physics',
                'contact_mode_requested': contact_mode,
                'source_id': source.source_id, 'source_closure': source.source_closure_digest,
                'joint_names': dict(compiled.references.names.joints),
                'body_names': dict(compiled.references.names.bodies),
                'qpos_addresses': data['jnt_qposadr'].tolist(),
                'dof_addresses': data['jnt_dofadr'].tolist(),
                'joint_types': data['jnt_type'].tolist(), 'plan': plan.describe()}
    finally:
        composer.close()
        close_source_and_task_resources(source, binding)


def _geophys_pendulum_source_probe():
    """Probe native BRS with the registered source, before factory admission."""
    from dataclasses import replace
    import numpy as np
    import torch
    from task_env.assembly import compile_task_scene
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.registry import ENV_REGISTRY
    from task_env.runtime.provider_bootstrap import init_task_env_backend
    from task_env.runtime.providers.geophys.rigid_batch import GeoPhysRigidBatchRuntime
    from task_env.runtime.sessions.geophys_source import GeoPhysSourceComposer
    from task_env.runtime.sessions.source import close_source_and_task_resources

    task = ENV_REGISTRY.get('pendulum-v1')
    config = resolve_task_env_config(task, {'execution': {'physics_provider': 'geophys'},
                                          'episode': {'seed': 73, 'horizon': 20}})
    binding = task._build_selected_binding(config)
    built = binding.build_for_request('geophys', 'cpu', 73, 20)
    source = built['source']
    composer = GeoPhysSourceComposer(source.scene_source, scene_definition=source.scene_definition,
        source_closure_digest=source.source_closure_digest, execution_source_receipt=source.execution_source_receipt)
    runtime = None
    try:
        init_task_env_backend('cuda')
        compiled = compile_task_scene(composition=source.composition, scene=source.scene,
            agents=source.agents, objects=source.objects, scene_composer=composer)
        euler_config = replace(source.config, runtime=replace(source.config.runtime,
            backend='cuda', integrator='euler', prewarm=False))
        runtime = GeoPhysRigidBatchRuntime.from_compiled_scene(compiled_scene=compiled,
            config=euler_config, num_envs=3, backend='cuda')
        initial = runtime.read_device_state(('qpos', 'qvel', 'body_position', 'body_orientation'))
        position = torch.tensor([[.2], [.5], [-.4]], dtype=torch.float32, device='cuda')
        velocity = torch.zeros_like(position)
        body_position, body_orientation = initial.arrays['body_position'], initial.arrays['body_orientation']
        runtime.reset_device_state(mask=torch.ones(3, dtype=torch.bool, device='cuda'),
            qpos=position, qvel=velocity, body_position=body_position, body_orientation=body_orientation,
            body_linear_velocity=torch.zeros_like(body_position), body_angular_velocity=torch.zeros_like(body_position))
        forces = torch.tensor([[1.], [0.], [-1.]], dtype=torch.float32, device='cuda')
        runtime.write_device_qfrc(forces)
        runtime.step_substeps()
        state = runtime.read_device_state(('qpos', 'qvel', 'body_position', 'body_orientation'))
        actual_q = state.arrays['qpos'][:, 0].cpu().numpy()
        actual_v = state.arrays['qvel'][:, 0].cpu().numpy()
        expected_q = np.array([.2, .5, -.4])
        expected_v = np.zeros(3)
        for _ in range(25):
            expected_v += .002 * (np.array([1., 0., -1.]) + 9.81 * .25 * np.sin(expected_q)
                                  - .05 * expected_v) / .1125
            expected_q += .002 * expected_v
        if np.max(np.abs(actual_q - expected_q)) > .01 or np.max(np.abs(actual_v - expected_v)) > .05:
            raise AssertionError(f'GeoPhys source diverges from frozen hinge oracle: q={actual_q}, v={actual_v}')
        return {'scope': 'GeoPhys registered Pendulum source, CUDA BRS diagnostic; not factory admission',
                'batch': 3, 'source_integrator': source.config.runtime.integrator,
                'native_integrator': 'euler', 'q': actual_q.tolist(), 'qdot': actual_v.tolist(),
                'expected_q': expected_q.tolist(), 'expected_qdot': expected_v.tolist()}
    finally:
        if runtime is not None:
            runtime.close()
        composer.close()
        close_source_and_task_resources(source, binding)


def _pickcube_record(worker_python, *, provider='mujoco_warp', sensor=False):
    """Save every public boundary independently of the vector recorder."""
    from dataclasses import asdict
    import numpy as np
    import torch
    from task_env import make_parallel_env
    from task_env.recorders import VectorTransitionRecorder

    config = {'execution': _pickcube_execution(provider, worker_python),
              'controller': {'profile_id': 'panda-direct-effort-v1'},
              'robot': {'native_drive': 'disabled'}, 'episode': {'seed': 31, 'horizon': 4}}
    if sensor:
        config['render'] = _pickcube_camera_configuration()
    env = make_parallel_env('pick-cube-p16-reference-v1', env_config=config, num_env=3,
                            backend='cuda', execution='device', worker_directory=os.getcwd())
    recorder = None
    traces = {}
    contexts = {}
    actions = torch.zeros((3, 8), device='cuda')

    def boundary(slot, observation, info):
        episode = int(info['episode_id'][slot].item())
        name = f'trajectory_slot_{slot:03d}_episode_{episode - 1:06d}'
        entry = traces.setdefault(name, {'ee_pose': [], 'joint_position': [], 'hand_pose': [],
                                         'cube_v1_body_pose': [], 'action': [], 'reward': [],
                                         'terminated': [], 'truncated': []})
        for key in ('ee_pose', 'joint_position', 'hand_pose'):
            entry[key].append(observation['state'][key][slot].cpu().numpy().copy())
        entry['cube_v1_body_pose'].append(
            observation['privileged_state']['cube_v1_body_pose'][slot].cpu().numpy().copy())
        if sensor:
            for camera in ('base', 'hand'):
                entry.setdefault(camera + '_rgb', []).append(
                    observation['cameras'][camera]['rgb'][slot].cpu().numpy().copy())
        context = {'schema_version': 'device-batch-boundary-v1',
            'env_id': int(info['env_id'][slot].item()), 'episode_id': episode,
            'episode_step': int(info['episode_step'][slot].item()), **asdict(info['boundary'])}
        if 'native_world_time' in info:
            context['native_world_time_s'] = float(info['native_world_time'][slot].item())
        contexts.setdefault(name, []).append(context)
        return entry

    try:
        recorder = VectorTransitionRecorder(env, path=os.getcwd(), env_ids=(0, 1))
        obs, info = recorder.reset(seed=31)
        for slot in (0, 1):
            boundary(slot, obs, info)
        for tick in range(5):
            if tick == 2:
                obs, info = recorder.reset(mask=torch.tensor([False, True, False], device='cuda'))
                boundary(1, obs, info)
            obs, reward, terminated, truncated, info = recorder.step({'effort': actions})
            for slot in (0, 1):
                ended = bool(terminated[slot] or truncated[slot])
                entry = boundary(slot, info['final_observation'] if ended else obs,
                                 info['final_info'] if ended else info)
                entry['action'].append(actions[slot].cpu().numpy().copy())
                entry['reward'].append(float(reward[slot].item()))
                entry['terminated'].append(bool(terminated[slot].item()))
                entry['truncated'].append(bool(truncated[slot].item()))
                if ended:
                    boundary(slot, obs, info['reset_info'])
        np.savez_compressed('pickcube_public_traces.npz', **{
            name + '__' + key: np.asarray(value) for name, trace in traces.items()
            for key, value in trace.items() if value})
        Path('pickcube_public_contexts.json').write_text(json.dumps(contexts, indent=2) + '\n')
    finally:
        if recorder is None:
            env.close()
        else:
            recorder.close()
    return {'scope': 'PickCube device state recorder probe', 'recorded_env_ids': [0, 1],
            'files': [path.name for path in recorder.saved_paths], 'closed': True,
            'action_components': list(env.metadata['action_schema']['components']),
            'cameras_recorded': ['base', 'hand'] if sensor else []}


def _pickcube_scalar_effort():
    """Compare the source's scalar physical response without a trajectory oracle."""
    import numpy as np
    from task_env import make_env

    env = make_env('pick-cube-p16-reference-v1', config={
        'execution': {'physics_provider': 'mujoco', 'deployment': 'in_process'},
        'controller': {'profile_id': 'panda-direct-effort-v1'},
        'robot': {'native_drive': 'disabled'}, 'episode': {'seed': 31, 'horizon': 20}})
    try:
        initial, info = env.reset(seed=31)
        if set(initial['state']) != {'ee_pose', 'joint_position', 'hand_pose'}:
            raise AssertionError('canonical scalar physical observation differs from device fields')
        if 'state_boundary_identity' not in info or 'state_sample_clock' not in info:
            raise AssertionError('scalar boundary metadata is missing')
        action = np.zeros(8, dtype=np.float32)
        env.step(action)
        action[0], action[-1] = 5., -4.
        for _ in range(10):
            observation, _, _, _, info = env.step(action)
        return {'scope': 'scalar PickCube motion comparison', 'seed': 31,
                'initial_cube': initial['privileged_state']['cube_v1_body_pose'][0].tolist(),
                'final_finger_positions': observation['state']['joint_position'][-2:].tolist(),
                'final_cube': observation['privileged_state']['cube_v1_body_pose'][0].tolist(),
                'control_step': info['control_step'], 'simulation_time_s': info['simulation_time_s'],
                'state_fields': sorted(observation['state'])}
    finally:
        env.close()


def _scale_correctness(worker_python, *, provider, pickcube, count=16):
    """Check a batch row permutation and the Pendulum's independent ODE."""
    import numpy as np
    import torch
    from task_env import make_parallel_env

    if count < 1:
        raise ValueError('scale correctness requires a positive batch')
    task = 'pick-cube-p16-reference-v1' if pickcube else 'pendulum-v1'
    seed = 31 if pickcube else 73
    config = {'execution': {'physics_provider': provider,
                            'interpreter': sys.executable if provider == 'geophys' else worker_python},
              'episode': {'seed': seed, 'horizon': 20}}
    if pickcube:
        config.update(controller={'profile_id': 'panda-direct-effort-v1'},
                      robot={'native_drive': 'disabled'})
        if provider == 'geophys':
            config['execution']['geophys_contact_mode'] = 'discrete'
    env = make_parallel_env(task, env_config=config, num_env=count, backend='cuda',
                            execution='device', worker_directory=os.getcwd())
    try:
        env.reset(seed=[seed] * count)
        initial = env.read_device_state(('qpos', 'qvel'))
        for name in ('qpos', 'qvel'):
            if not torch.allclose(initial.arrays[name], initial.arrays[name][:1].expand_as(initial.arrays[name]),
                                  atol=1e-6, rtol=0):
                raise AssertionError(f'B={count} initial {name} differs by row')
        key = 'effort' if pickcube else 'torque'
        action = torch.zeros((count, *env.single_action_space[key].shape), device='cuda')
        action[:, 0] = torch.linspace(-5., 5., count, device='cuda') if pickcube else torch.linspace(-1.5, 1.5, count, device='cuda')
        if pickcube:
            action[:, -1] = torch.linspace(-4., 4., count, device='cuda')
        env.step({key: action})
        first = env.read_device_state(('qpos', 'qvel'))
        if any(not bool(torch.isfinite(value).all()) for value in first.arrays.values()):
            raise AssertionError(f'B={count} physical state is nonfinite')
        ode_error = None
        if not pickcube:
            q = initial.arrays['qpos'][:, 0].cpu().numpy().astype(float)
            velocity = initial.arrays['qvel'][:, 0].cpu().numpy().astype(float)
            effort = action[:, 0].cpu().numpy().astype(float)
            for _ in range(25):
                velocity += .002 * (effort + 9.81 * .25 * np.sin(q) - .05 * velocity) / .1125
                q += .002 * velocity
            ode_error = {'qpos': float(np.max(np.abs(first.arrays['qpos'][:, 0].cpu().numpy() - q))),
                         'qvel': float(np.max(np.abs(first.arrays['qvel'][:, 0].cpu().numpy() - velocity)))}
            if ode_error['qpos'] > .01 or ode_error['qvel'] > .05:
                raise AssertionError(f'B={count} Pendulum disagrees with frozen source ODE: {ode_error}')
        env.reset(seed=[seed] * count)
        reset = env.read_device_state(('qpos', 'qvel'))
        if reset.identity.native_step != first.identity.native_step:
            raise AssertionError(f'B={count} reset advanced physics')
        for name in ('qpos', 'qvel'):
            if not torch.allclose(reset.arrays[name], initial.arrays[name], atol=1e-6, rtol=0):
                raise AssertionError(f'B={count} reset did not restore initial {name}')
        order = torch.arange(count - 1, -1, -1, device='cuda')
        env.step({key: action.index_select(0, order).contiguous()})
        second = env.read_device_state(('qpos', 'qvel'))
        expected = {name: first.arrays[name].index_select(0, order).cpu().numpy() for name in ('qpos', 'qvel')}
        actual = {name: second.arrays[name].cpu().numpy() for name in ('qpos', 'qvel')}
        np.savez_compressed('scale_states.npz', **{f'{prefix}_{name}': values[name]
            for prefix, values in (('expected', expected), ('actual', actual)) for name in values})
        errors = {name: float(np.max(np.abs(actual[name] - expected[name]))) for name in expected}
        if errors['qpos'] > 1e-4 or errors['qvel'] > 1e-3:
            raise AssertionError(f'B={count} row permutation differs after reset: {errors}')
        return {'scope': f'{provider} {task} B={count} state and reversed-action correctness',
                'batch': count, 'permutation_errors': errors, 'pendulum_ode_errors': ode_error,
                'native_step_reset_unchanged': True, 'source_states': 'scale_states.npz'}
    finally:
        env.close()


def _action_permutation(worker_python, *, provider, pickcube):
    """Reapply the same actions on permuted rows from identical source states."""
    import numpy as np
    import torch
    from task_env import make_parallel_env

    task = 'pick-cube-p16-reference-v1' if pickcube else 'pendulum-v1'
    seed = 31 if pickcube else 73
    config = {'execution': {'physics_provider': provider,
                            'interpreter': sys.executable if provider == 'geophys' else worker_python},
              'episode': {'seed': seed, 'horizon': 20}}
    if pickcube:
        config.update(controller={'profile_id': 'panda-direct-effort-v1'},
                      robot={'native_drive': 'disabled'})
        if provider == 'geophys':
            config['execution']['geophys_contact_mode'] = 'discrete'
    env = make_parallel_env(task, env_config=config, num_env=3, backend='cuda',
                            execution='device', worker_directory=os.getcwd())
    try:
        env.reset(seed=[seed] * 3)
        initial = env.read_device_state(('qpos', 'qvel'))
        for name in ('qpos', 'qvel'):
            if not torch.allclose(initial.arrays[name], initial.arrays[name][:1].expand_as(initial.arrays[name]),
                                  atol=1e-6, rtol=0):
                raise AssertionError(f'permutation rows did not start from the same {name}')
        key = 'effort' if pickcube else 'torque'
        action = torch.zeros((3, *env.single_action_space[key].shape), device='cuda')
        action[:, 0] = torch.tensor([-5., 0., 5.] if pickcube else [-1.5, 0., 1.5], device='cuda')
        if pickcube:
            action[:, -1] = torch.tensor([-4., 0., 4.], device='cuda')
        env.step({key: action})
        first = env.read_device_state(('qpos', 'qvel'))
        env.reset(seed=[seed] * 3)
        reset = env.read_device_state(('qpos', 'qvel'))
        if reset.identity.native_step != first.identity.native_step:
            raise AssertionError('permutation reset advanced native time')
        for name in ('qpos', 'qvel'):
            if not torch.allclose(reset.arrays[name], initial.arrays[name], atol=1e-6, rtol=0):
                raise AssertionError(f'permutation reset changed the frozen initial {name}')
        order = torch.tensor([2, 0, 1], dtype=torch.int64, device='cuda')
        env.step({key: action.index_select(0, order).contiguous()})
        second = env.read_device_state(('qpos', 'qvel'))
        expected = {name: first.arrays[name].index_select(0, order).cpu().numpy()
                    for name in ('qpos', 'qvel')}
        actual = {name: second.arrays[name].cpu().numpy() for name in ('qpos', 'qvel')}
        np.savez_compressed('permutation_states.npz', **{f'{prefix}_{name}': values[name]
            for prefix, values in (('expected', expected), ('actual', actual)) for name in values})
        errors = {name: float(np.max(np.abs(actual[name] - expected[name]))) for name in expected}
        if errors['qpos'] > 1e-4 or errors['qvel'] > 1e-3:
            raise AssertionError(f'permuted action response differs from same-state control: {errors}')
        return {'scope': f'{provider} {task} action permutation from identical reset states',
                'order': [2, 0, 1], 'qpos_max_error': errors['qpos'], 'qvel_max_error': errors['qvel'],
                'qpos_tolerance': 1e-4, 'qvel_tolerance': 1e-3,
                'reset_did_not_step': True, 'source_states': 'permutation_states.npz'}
    finally:
        env.close()


def _pickcube_finger_contact(worker_python, *, provider, hold_arm=False):
    """Compare a source-aligned cube against same-action empty-space controls."""
    import numpy as np
    import torch
    from task_env import make_parallel_env

    controlled_descent = hold_arm == 'source-bias-descend'
    source_bias = isinstance(hold_arm, str) and hold_arm.startswith('source-bias')
    config = {'execution': _pickcube_execution(provider, worker_python),
              'controller': {'profile_id': 'panda-direct-effort-v1'},
              'robot': {'native_drive': 'disabled'},
              'episode': {'seed': 31, 'horizon': 100 if controlled_descent else 40}}
    env = make_parallel_env('pick-cube-p16-reference-v1', env_config=config, num_env=3,
                            backend='cuda', execution='device', worker_directory=os.getcwd())
    traces = {'joint_position': [], 'hand_pose': [], 'ee_pose': [], 'cube_pose': []}

    def retain(observation):
        for key in ('joint_position', 'hand_pose', 'ee_pose'):
            traces[key].append(observation['state'][key].cpu().numpy().copy())
        traces['cube_pose'].append(observation['privileged_state']['cube_v1_body_pose'][:, 0].cpu().numpy().copy())

    try:
        observation, _ = env.reset(seed=[3706, 31, 3706])
        retain(observation)
        target = observation['state']['joint_position'][:, :7].clone()
        previous = target.clone()
        if controlled_descent:
            target[:, 3] -= .08
        actions = torch.zeros((3, *env.single_action_space['effort'].shape), device='cuda')
        finger_efforts = torch.tensor([-4., -4., 0.], device='cuda')
        limits = torch.tensor([87., 87., 87., 87., 12., 12., 12.], device='cuda')
        bias = (torch.tensor([0., -29.3559534, 0., 22.0492107, .6695478, 2.3063896, 0.], device='cuda')
                if source_bias else 0.)
        actions[:, -1] = finger_efforts
        steps = 60 if controlled_descent else 20
        for tick in range(steps):
            if hold_arm:
                current = observation['state']['joint_position'][:, :7]
                velocity = (current - previous) / .01
                previous = current.clone()
                actions[:, :7] = torch.clamp(bias + 200. * (target - current) - 20. * velocity,
                                             min=-limits, max=limits)
                if controlled_descent:
                    actions[:, -1] = finger_efforts if tick >= 35 else 0.
            observation, _, terminated, truncated, _ = env.step({'effort': actions})
            retain(observation)
            if bool(terminated.any() or truncated.any()):
                raise AssertionError('contact probe ended before its frozen horizon')
        arrays = {name: np.asarray(value) for name, value in traces.items()}
        np.savez_compressed('finger_contact_traces.npz', **arrays)
        initial_xy = arrays['cube_pose'][0, :, :2]
        initial_ee = arrays['ee_pose'][0, :, :2]
        offsets = np.linalg.norm(initial_xy - initial_ee, axis=1)
        openings = arrays['joint_position'][-1, :, -2:].sum(axis=1)
        finger_error = np.max(np.abs(arrays['joint_position'][:, :, -2] - arrays['joint_position'][:, :, -1]))
        displacement = np.linalg.norm(arrays['cube_pose'][-1, :, :2] - initial_xy, axis=1)
        if offsets[0] > .002 or offsets[1] < .05 or offsets[2] > .002:
            raise AssertionError(f'frozen cube/hand alignment differs: {offsets.tolist()}')
        if openings[1] >= .02 or openings[0] <= openings[1] + .01 or finger_error >= .003:
            raise AssertionError(f'finger contact response differs: openings={openings.tolist()}, '
                                 f'coupling_error={finger_error}')
        if displacement[0] < .0005:
            raise AssertionError(f'aligned cube did not move observably: {displacement.tolist()}')
        return {'scope': f'{provider} same-action aligned/offset cube contact witness',
                'initial_xy_distance_m': offsets.tolist(), 'final_finger_openings_m': openings.tolist(),
                'finger_coupling_max_error_m': float(finger_error),
                'cube_xy_displacement_m': displacement.tolist(), 'steps': steps,
                'arm_control': ('sampled position hold with independently compiled source bias' if source_bias
                                else 'sampled position hold' if hold_arm else 'zero effort'),
                'source_trajectory': 'finger_contact_traces.npz'}
    finally:
        env.close()


def _pickcube_device_probe(worker_python, *, motion=False, provider='mujoco_warp'):
    """Bounded first integration probe of the registered PickCube route."""
    import torch
    from task_env import make_parallel_env

    config = {'execution': _pickcube_execution(provider, worker_python),
              'controller': {'profile_id': 'panda-direct-effort-v1'},
              'robot': {'native_drive': 'disabled'},
              'episode': {'seed': 31, 'horizon': 20}}
    env = make_parallel_env('pick-cube-p16-reference-v1', env_config=config, num_env=3,
                            backend='cuda', execution='device', worker_directory=os.getcwd())
    try:
        observation, info = env.reset(seed=31)
        if set(observation['state']) != {'ee_pose', 'joint_position', 'hand_pose'}:
            raise AssertionError('unexpected PickCube Robot observation fields')
        if tuple(observation['privileged_state']['cube_v1_body_pose'].shape) != (3, 1, 7):
            raise AssertionError('invalid cube observation shape')
        cube = observation['privileged_state']['cube_v1_body_pose'][:, 0, :3].clone()
        if torch.unique(cube[:, :2], dim=0).shape[0] != 3:
            raise AssertionError('reset samples did not differ by row')
        action_space = env.single_action_space['effort']
        action = {'effort': torch.zeros((3, *action_space.shape), device='cuda')}
        next_observation, reward, terminated, truncated, next_info = env.step(action)
        if not bool(torch.isfinite(reward).all()) or bool(terminated.any() or truncated.any()):
            raise AssertionError('invalid first PickCube task transition')
        if not torch.equal(cube, observation['privileged_state']['cube_v1_body_pose'][:, 0, :3]):
            raise AssertionError('reset observation was not owned')
        result = {'scope': f'initial PickCube {provider} integration probe', 'batch': 3,
                'seed': 31, 'cube_initial': cube.cpu().tolist(),
                'reward': reward.cpu().tolist(), 'episode_step': next_info['episode_step'].cpu().tolist(),
                'action_shape': list(action['effort'].shape), 'observation_owned': True,
                'initial_joint_position': observation['state']['joint_position'].cpu().tolist(),
                'initial_ee_pose': observation['state']['ee_pose'].cpu().tolist(),
                'initial_hand_pose': observation['state']['hand_pose'].cpu().tolist(),
                'first_joint_position': next_observation['state']['joint_position'].cpu().tolist(),
                'first_cube_pose': next_observation['privileged_state']['cube_v1_body_pose'][:, 0].cpu().tolist()}
        if motion:
            action['effort'][:, 0] = torch.tensor([5., 0., -5.], device='cuda')
            action['effort'][:, -1] = torch.tensor([-4., 0., 4.], device='cuda')
            for _ in range(10):
                next_observation, _, _, _, _ = env.step(action)
                heights = next_observation['privileged_state']['cube_v1_body_pose'][:, 0, 2]
                if not bool(torch.all(torch.abs(heights - .488) < .02)):
                    raise AssertionError('cube did not remain near authored table rest height')
            fingers = next_observation['state']['joint_position'][:, -2:]
            openings = fingers.sum(dim=1)
            if not bool(openings[0] + .0001 < openings[2]):
                raise AssertionError('signed tendon effort did not produce distinct opening')
            if not bool(torch.all(torch.abs(fingers[:, 0] - fingers[:, 1]) < .003)):
                raise AssertionError('coupled fingers do not retain the declared constraint')
            before = env.read_device_state(('qpos', 'qvel'))
            before_values = {name: value.clone() for name, value in before.arrays.items()}
            env.reset(mask=torch.tensor([True, False, True], dtype=torch.bool, device='cuda'))
            after = env.read_device_state(('qpos', 'qvel'))
            if after.identity.native_step != before.identity.native_step:
                raise AssertionError('masked reset advanced the native physics clock')
            for name in ('qpos', 'qvel'):
                if not torch.equal(before_values[name][1], after.arrays[name][1]):
                    raise AssertionError('masked reset altered the unselected row')
            result.update(scope=f'PickCube {provider} motion and masked-reset probe',
                          finger_openings=openings.cpu().tolist(),
                          final_cube_heights=heights.cpu().tolist(),
                          unselected_state_unchanged=True, reset_did_not_step=True)
        return result
    finally:
        primary = sys.exception()
        try:
            env.close()
        except BaseException as cleanup_error:
            if primary is None:
                raise
            primary.add_note(f'PickCube probe cleanup also failed: {cleanup_error!r}')


def _formal_device(worker_python, *, provider='mujoco_warp', contact_mode='provider_default'):
    """Exercise the ordinary registered factory and same-step device lifecycle."""
    import numpy as np
    import torch
    from task_env import make_parallel_env

    config = {'execution': {'physics_provider': provider,
                            'interpreter': sys.executable if provider == 'geophys' else worker_python},
              'episode': {'seed': 73, 'horizon': 20}}
    if contact_mode != 'provider_default':
        config['execution']['geophys_contact_mode'] = contact_mode
    env = make_parallel_env('pendulum-v1', env_config=config, num_env=3, backend='cuda',
                            execution='device', worker_directory=os.getcwd())
    robot = env.robot
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
                joint_positions = robot.joint_positions(current)
                if (len(robot.subjects) != 1 or len(robot.controlled_joints) != 1
                        or not torch.equal(joint_positions[:, 0], current.arrays['qpos'][:, 0])):
                    raise AssertionError('Robot view does not resolve its declared joint on this runtime')
                try:
                    robot.joint_positions(initial)
                except ValueError:
                    pass
                else:
                    raise AssertionError('Robot view admitted a stale state boundary')
                if (np.max(np.abs(first_q - predicted_q)) > .01
                        or np.max(np.abs(first_v - predicted_v)) > .05):
                    raise AssertionError('first interval disagrees with the independent hinge oracle')
                poses = env.read_device_state(('body_position', 'body_orientation'))
                body_names = env.metadata['runtime_resource_summary']['device_transition']['body_names']
                link = body_names.index('pendulum-v1/pendulum_link')
                measured_quat = poses.arrays['body_orientation'][:, link].cpu().numpy()
                robot_pose = robot.frame_pose(poses, 'pendulum-v1/pendulum_link')
                if not torch.equal(robot_pose[:, 3:], poses.arrays['body_orientation'][:, link]):
                    raise AssertionError('Robot view frame mapping differs from the runtime publication')
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
        Path('formal_terminal_oracle.json').write_text(json.dumps({
            'actual': actual_final.tolist(), 'expected': expected_final.tolist(),
            'previous_q_rad': terminal_q_before.tolist(),
            'previous_qd_rad_s': terminal_v_before.tolist()}, indent=2) + '\n')
        if (np.max(np.abs(actual_final[:, :2] - expected_final[:, :2])) > .01
                or np.max(np.abs(actual_final[:, 2] - expected_final[:, 2])) > .05):
            raise AssertionError('saved terminal observations do not describe the old transition: '
                                 f'actual={actual_final.tolist()}, expected={expected_final.tolist()}')
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
                  'robot_controlled_joints': list(robot.controlled_joints),
                  'robot_subject_count': len(robot.subjects), 'robot_stale_state_rejected': True,
                  'control_intervals': 21, 'native_batch_steps': 525, 'world_steps': 1575}
        if provider == 'geophys':
            layout = env.resource_summary()['device_transition']['physical_layout_facts']
            result['contact_mode_requested'] = layout['contact_mode_requested']
            result['contact_mode_resolved'] = layout['contact_mode_resolved']
            if result['contact_mode_requested'] != contact_mode:
                raise AssertionError('GeoPhys did not retain the explicitly selected contact mode')
    finally:
        env.close()
    env.close()
    try:
        robot.read_device_state(('qpos',))
    except RuntimeError:
        pass
    else:
        raise AssertionError('Robot view remained live after runtime close')
    result['robot_closed_state_rejected'] = True
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


def _formal_window(worker_python, *, provider='mujoco_warp'):
    """Exercise a real display and close its renderer independently of physics."""
    import torch
    from task_env import make_parallel_env

    config = {'execution': {'physics_provider': provider,
                            'interpreter': sys.executable if provider == 'geophys' else worker_python},
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


def _record_device(worker_python, *, camera=False, provider='mujoco_warp'):
    """Record selected rows from the ordinary five-tuple device environment."""
    from dataclasses import asdict
    import numpy as np
    import torch
    from task_env import make_parallel_env
    from task_env.recorders import VectorTransitionRecorder

    config = {'execution': {'physics_provider': provider,
                            'interpreter': sys.executable if provider == 'geophys' else worker_python},
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
        context = {'schema_version': 'device-batch-boundary-v1',
                                  'env_id': int(info['env_id'][slot].item()),
                                  'episode_id': episode,
                                  'episode_step': int(info['episode_step'][slot].item()),
                                  **asdict(info['boundary'])}
        if 'native_world_time' in info:
            context['native_world_time_s'] = float(info['native_world_time'][slot].item())
        trace['contexts'].append(context)
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


def _mjwarp_world_clock_probe(worker_python):
    """Read native per-world time through masked reset and same-step reset."""
    import torch
    from task_env import make_parallel_env

    env = make_parallel_env('pendulum-v1', env_config={
        'execution': {'physics_provider': 'mujoco_warp', 'interpreter': worker_python},
        'episode': {'seed': 73, 'horizon': 3}}, num_env=3, backend='cuda',
        execution='device', worker_directory=os.getcwd())
    try:
        _, info = env.reset(seed=73)
        samples = [info['native_world_time'].cpu().tolist()]
        action = {'torque': torch.zeros((3, 1), device='cuda')}
        _, _, _, _, info = env.step(action)
        samples.append(info['native_world_time'].cpu().tolist())
        _, info = env.reset(mask=torch.tensor([False, True, False], dtype=torch.bool, device='cuda'))
        samples.append(info['native_world_time'].cpu().tolist())
        env.step(action)
        _, _, _, truncated, info = env.step(action)
        samples.append(info['final_info']['native_world_time'].cpu().tolist())
        samples.append(info['native_world_time'].cpu().tolist())
        expected = [[0., 0., 0.], [.05, .05, .05], [.05, 0., .05],
                    [.15, .10, .15], [0., .10, 0.]]
        if truncated.tolist() != [True, False, True] or not torch.allclose(
                torch.tensor(samples), torch.tensor(expected), atol=1e-6, rtol=0):
            raise AssertionError(f'native world clocks differ from the frozen boundaries: {samples}')
        direct = env.read_device_state(('native_world_time',)).arrays['native_world_time']
        if not torch.allclose(direct, info['native_world_time'], atol=0, rtol=0):
            raise AssertionError('public native world clock differs from returned info')
        return {'scope': 'MJWarp native per-world clocks across masked and same-step reset',
                'samples_s': samples, 'truncated': truncated.cpu().tolist(),
                'source': 'MJWarp Data.time', 'maximum_error_s': float(
                    torch.max(torch.abs(torch.tensor(samples) - torch.tensor(expected))))}
    finally:
        env.close()


def _device_sha_probe(worker_python, *, pickcube, sensor=False):
    """Count SHA-256 calls in a public step, including same-step autoreset."""
    import hashlib
    import traceback
    import torch
    from task_env import make_parallel_env

    task = 'pick-cube-p16-reference-v1' if pickcube else 'pendulum-v1'
    config = {'execution': {'physics_provider': 'mujoco_warp', 'interpreter': worker_python},
              'episode': {'seed': 31 if pickcube else 73, 'horizon': 1}}
    if pickcube:
        config.update(controller={'profile_id': 'panda-direct-effort-v1'},
                      robot={'native_drive': 'disabled'})
    if sensor:
        if not pickcube:
            raise ValueError('this SHA probe only declares PickCube cameras')
        config['render'] = _pickcube_camera_configuration()
    env = make_parallel_env(task, env_config=config, num_env=3, backend='cuda',
                            execution='device', worker_directory=os.getcwd())
    try:
        env.reset(seed=31 if pickcube else 73)
        key = 'effort' if pickcube else 'torque'
        shape = env.single_action_space[key].shape
        action = {key: torch.zeros((3, *shape), dtype=torch.float32, device='cuda')}
        real_sha256 = hashlib.sha256
        calls = []
        def capture(*args, **kwargs):
            calls.append(traceback.extract_stack(limit=5)[-2].name)
            return real_sha256(*args, **kwargs)
        try:
            hashlib.sha256 = capture
            _, _, _, truncated, _ = env.step(action)
        finally:
            hashlib.sha256 = real_sha256
        if not bool(truncated.all()):
            raise AssertionError('probe did not exercise same-step autoreset')
        return {'task': task, 'sensor_enabled': sensor, 'step_sha256_call_count': len(calls), 'callers': calls,
                'same_step_autoreset': True}
    finally:
        env.close()


def _pickcube_performance(worker_python, *, provider, sensor, window, count=16):
    """Measure complete public PickCube steps with all requested render rows."""
    import math
    import time
    import torch
    from task_env import make_parallel_env

    horizon = 1000 if provider == 'isaacsim' else 2000
    config = {'execution': _pickcube_execution(provider, worker_python),
              'controller': {'profile_id': 'panda-direct-effort-v1'},
              'robot': {'native_drive': 'disabled'}, 'episode': {'seed': 31, 'horizon': horizon}}
    if sensor:
        config['render'] = _pickcube_camera_configuration()
    else:
        config['render'] = {}
    config['render']['parallel'] = {'columns': math.ceil(math.sqrt(count))}
    started = time.monotonic()
    env = make_parallel_env('pick-cube-p16-reference-v1', env_config=config, num_env=count,
                            backend='cuda', execution='device', render_mode='human' if window else None,
                            worker_directory=os.getcwd())
    try:
        env.reset(seed=31)
        layout_facts = env.resource_summary()['device_transition']['physical_layout_facts']
        if window:
            env.set_parallel_render_num(count)
        values = torch.zeros((count, *env.single_action_space['effort'].shape), device='cuda')
        values[:, 0] = torch.linspace(-5., 5., count, device='cuda')
        values[:, -1] = torch.linspace(-4., 4., count, device='cuda')
        action = {'effort': values}
        torch.cuda.synchronize()
        init_seconds = time.monotonic() - started
        for _ in range(20):
            env.step(action)
            if window:
                env.render()
        torch.cuda.synchronize()
        if window:
            from PIL import Image
            before = env.read_device_state(('qpos',)).identity
            frame = env.render(mode='rgb_array')
            Image.fromarray(frame.cpu().numpy()).save('observer-warmup.png')
            env.render(mode='human')
            if env.read_device_state(('qpos',)).identity != before:
                raise AssertionError('observer witness capture advanced physics')
        started = time.monotonic()
        steps = 0
        step_seconds = presentation_seconds = 0.
        while steps < horizon - 20:
            step_started = time.monotonic()
            env.step(action)
            torch.cuda.synchronize()
            step_seconds += time.monotonic() - step_started
            if window:
                presentation_started = time.monotonic()
                env.render()
                torch.cuda.synchronize()
                presentation_seconds += time.monotonic() - presentation_started
            steps += 1
            elapsed = time.monotonic() - started
            if steps >= 100 and elapsed >= 10:
                break
        final = env.read_device_state(('qpos', 'qvel'))
        if any(not bool(torch.isfinite(value).all()) for value in final.arrays.values()):
            raise AssertionError('PickCube performance sample ended in a nonfinite physical state')
        return {'scope': 'full public PickCube transitions with configured cameras and observer',
                'provider': provider, 'batch': count, 'sensor': sensor, 'window': window,
                'selected_render_envs': count if window else 0,
                'visibly_distinguishable_envs': None if window else 0,
                'sensor_envs': count if sensor else 0,
                'render_grid_columns': math.ceil(math.sqrt(count)),
                'sensor_cameras': ['base', 'hand'] if sensor else [],
                'warmup_steps': 20, 'measured_steps': steps, 'measurement_seconds': elapsed,
                'initialization_seconds': init_seconds, 'sample_sufficient': steps >= 100 and elapsed >= 10,
                'public_step_seconds': step_seconds, 'public_step_hz': steps / step_seconds,
                'control_hz_including_present': steps / elapsed,
                'env_transitions_per_second': count * steps / elapsed,
                'presentation_seconds': presentation_seconds,
                'window_fps': steps / elapsed if window else None,
                'sensor_hz': steps / elapsed if sensor else None,
                'gpu_aggregate_pair_capacity': layout_facts.get('gpu_aggregate_pair_capacity'),
                'source_collision_shapes_all_worlds': layout_facts.get('source_collision_shapes_all_worlds'),
                'final_state_finite': True,
                'native_substeps_per_control': 5, 'physics_dt': .002}
    finally:
        env.close()


def _pendulum_performance(worker_python, *, window, provider='mujoco_warp', count=16):
    """Measure complete public transitions, with an optional observer."""
    import math
    import time
    import torch
    from task_env import make_parallel_env

    started = time.monotonic()
    env = make_parallel_env('pendulum-v1', env_config={
        'execution': {'physics_provider': provider,
                      'interpreter': sys.executable if provider == 'geophys' else worker_python},
        'render': {'parallel': {'columns': math.ceil(math.sqrt(count))}},
        'episode': {'seed': 73, 'horizon': 2000}}, num_env=count, backend='cuda',
        execution='device', render_mode='human' if window else None, worker_directory=os.getcwd())
    try:
        env.reset(seed=73)
        if window:
            env.set_parallel_render_num(count)
        action = {'torque': torch.linspace(-1.5, 1.5, count, device='cuda').reshape(count, 1)}
        torch.cuda.synchronize()
        init_seconds = time.monotonic() - started
        for _ in range(20):
            env.step(action)
            if window:
                env.render()
        torch.cuda.synchronize()
        if window:
            from PIL import Image
            before_capture = env.read_device_state(('qpos',)).identity
            frame = env.render(mode='rgb_array')
            Image.fromarray(frame.cpu().numpy()).save('observer-warmup.png')
            env.render(mode='human')
            if env.read_device_state(('qpos',)).identity != before_capture:
                raise AssertionError('observer witness capture advanced physics')
        started = time.monotonic()
        steps = 0
        presentation_seconds = 0.0
        step_seconds = 0.0
        while steps < 1980:
            step_started = time.monotonic()
            env.step(action)
            torch.cuda.synchronize()
            step_seconds += time.monotonic() - step_started
            if window:
                presentation_started = time.monotonic()
                env.render()
                torch.cuda.synchronize()
                presentation_seconds += time.monotonic() - presentation_started
            steps += 1
            elapsed = time.monotonic() - started
            if steps >= 100 and elapsed >= 10:
                break
        final = env.read_device_state(('qpos', 'qvel'))
        if any(not bool(torch.isfinite(value).all()) for value in final.arrays.values()):
            raise AssertionError('Pendulum performance sample ended in a nonfinite physical state')
        return {'scope': 'full public Pendulum transitions with optional window presentation',
                'provider': provider, 'batch': count, 'window': window,
                'selected_render_envs': count if window else 0,
                'visibly_distinguishable_envs': None if window else 0,
                'render_grid_columns': math.ceil(math.sqrt(count)),
                'sensor': False, 'warmup_steps': 20, 'measured_steps': steps,
                'measurement_seconds': elapsed, 'initialization_seconds': init_seconds,
                'sample_sufficient': steps >= 100 and elapsed >= 10,
                'public_step_seconds': step_seconds, 'public_step_hz': steps / step_seconds,
                'control_hz_including_present': steps / elapsed,
                'env_transitions_per_second': count * steps / elapsed,
                'presentation_seconds': presentation_seconds,
                'window_fps': steps / elapsed if window else None,
                'final_state_finite': True,
                'native_substeps_per_control': 25, 'physics_dt': .002}
    finally:
        env.close()


def _gpu_group_mib(group):
    processes = subprocess.check_output(['ps', '-eo', 'pid=,pgid='], text=True)
    members = {int(pid) for pid, pgid in (line.split() for line in processes.splitlines())
               if int(pgid) == group}
    apps = subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid,used_gpu_memory',
                                    '--format=csv,noheader,nounits'], text=True)
    return sum(int(memory.strip()) for line in apps.splitlines() if line.strip()
               for pid, memory in [line.split(',', 1)] if int(pid.strip()) in members)


def _gpu_used_mib():
    values = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used',
                                      '--format=csv,noheader,nounits'], text=True)
    return sum(int(line.strip()) for line in values.splitlines() if line.strip())


def _run(worker_python, output, case, *, batch_size=16):
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
    elif case in ('pickcube-example', 'pickcube-example-sensor', 'geophys-pickcube-example'):
        example = Path(__file__).resolve().parents[5] / 'examples/parallel/pick_cube_device.py'
        command = [sys.executable, '-u', str(example), '--interpreter', worker_python,
                   '--steps', '2', '--output', str(output / 'result.json')]
        if case == 'pickcube-example-sensor':
            command.append('--sensor')
        if case == 'geophys-pickcube-example':
            command.extend(['--provider', 'geophys', '--geophys-contact-mode', 'discrete'])
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
    elif case == 'scalar-effort-regression':
        root = Path(__file__).resolve().parents[5] / 'task_env/diagnostics/tasks/v2.1.1'
        command = [sys.executable, '-m', 'pytest', '-q',
                   str(root / 'test_panda_effort_source.py') + '::test_formal_env_releases_its_source_once',
                   str(root / 'test_panda_effort_profiles.py') + '::test_effort_reset_rebuilds_plan_for_requested_seed[False]']
    elif case == 'geophys-batch-cuda':
        root = Path(__file__).resolve().parents[5] / 'GeoPhys/test/verification/rigid'
        command = [sys.executable, '-m', 'pytest', '-q',
                   str(root / 'test_rigid_batch_no_contact.py') + '::test_public_three_world_construction_and_selected_reset',
                   str(root / 'test_rigid_batch_contact.py') + '::test_contact_worlds_are_isolated_and_selected_reset_clears_cache']
    elif case == 'geophys-batch-plan-regression':
        test = Path(__file__).resolve().parents[5] / 'GeoPhys/test/verification/rigid/test_rigid_batch_plan.py'
        command = [sys.executable, '-m', 'pytest', '-q', str(test)]
    elif case == 'geophys-actuator-isolation':
        test = Path(__file__).resolve().parents[5] / 'GeoPhys/test/verification/rigid/test_rigid_batch_tendons.py'
        command = [sys.executable, '-m', 'pytest', '-q',
                   str(test) + '::test_native_actuator_isolation_includes_affine_bias_and_survives_reset']
    elif case == 'geophys-device-layout':
        test = Path(__file__).resolve().parent / 'test_geophys_device_layout.py'
        command = [sys.executable, '-m', 'pytest', '-q', str(test)]
    elif case == 'geophys-contact-mode-comparison':
        test = Path(__file__).resolve().parents[5] / 'GeoPhys/test/verification/rigid/test_rigid_batch_ccd.py'
        command = [sys.executable, '-m', 'pytest', '-q',
                   str(test) + '::test_public_discrete_and_continuous_modes_expose_tunneling_limit']
    elif case == 'geophys-mesh-contact':
        test = Path(__file__).resolve().parents[5] / 'GeoPhys/test/verification/rigid/test_rigid_batch_mesh_contact.py'
        command = [sys.executable, '-m', 'pytest', '-q', str(test)]
    elif case == 'geophys-table-stability':
        test = Path(__file__).resolve().parents[5] / 'GeoPhys/test/verification/rigid/test_rigid_batch_table_stability.py'
        command = [sys.executable, '-m', 'pytest', '-q', '-s', str(test)]
    elif case == 'geophys-efc-regression':
        test = Path(__file__).resolve().parents[5] / 'GeoPhys/test/verification/rigid/test_efc_batch_preparation.py'
        command = [sys.executable, '-m', 'pytest', '-q',
                   str(test) + '::test_public_coupled_step_with_damping_and_current_control[off]']
    elif case == 'geophys-torsion-constraints':
        test = Path(__file__).resolve().parents[5] / 'GeoPhys/test/verification/rigid/test_rigid_batch_equalities.py'
        command = [sys.executable, '-m', 'pytest', '-q',
                   str(test) + '::test_contact_limit_equality_share_one_world_iteration']
    elif case == 'geophys-torsion-direct':
        test = Path(__file__).resolve().parents[5] / 'GeoPhys/test/verification/rigid/test_rigid_batch_mixed.py'
        command = [sys.executable, '-m', 'pytest', '-q',
                   str(test) + '::test_condim4_torsion_applies_to_direct_body_endpoint']
    elif case == 'geophys-torsion':
        test = Path(__file__).resolve().parents[5] / 'GeoPhys/test/verification/rigid/test_rigid_batch_contact.py'
        command = [sys.executable, '-m', 'pytest', '-q',
                   str(test) + '::test_condim4_torsion_changes_spin_and_respects_normal_impulse',
                   str(test) + '::test_condim4_combined_sliding_and_spin_stay_inside_friction_cone',
                   str(test) + '::test_condim3_and_condim4_contacts_are_world_local_in_one_batch',
                   str(test) + '::test_condim4_box_contact_has_bounded_torsional_impulse']
    elif case == 'geophys-static-contact-filter':
        test = Path(__file__).resolve().parents[5] / 'GeoPhys/test/verification/rigid/test_rigid_batch_plan.py'
        command = [sys.executable, '-m', 'pytest', '-q',
                   str(test) + '::test_contact_pairs_exclude_distinct_fixed_roots_but_keep_kinematic_roots',
                   str(test) + '::test_pair_material_priority_margin_and_mask_are_frozen_host_facts',
                   str(test) + '::test_source_offsets_are_pair_facts_and_explicit_pair_remains_authoritative',
                   str(test) + '::test_condim4_material_priority_and_unqualified_routes_fail_closed',
                   str(test) + '::test_mixed_partition_identity_and_split_workspace_budget',
                   str(test) + '::test_joint_limit_preflight_frozen_facts_and_resource_contract']
    elif case == 'geophys-free-damping':
        test = Path(__file__).resolve().parents[5] / 'GeoPhys/test/verification/rigid/test_rigid_batch_no_contact.py'
        command = [sys.executable, '-m', 'pytest', '-q',
                   str(test) + '::test_free_joint_damping_and_armature_match_mujoco_per_world']
    elif case == 'geophys-device-state':
        test = Path(__file__).resolve().parents[5] / 'GeoPhys/test/verification/rigid/test_rigid_batch_no_contact.py'
        command = [sys.executable, '-m', 'pytest', '-q',
                   str(test) + '::test_cuda_device_state_is_owned_and_matches_public_readback',
                   str(test) + '::test_cuda_device_state_supports_zero_dof_worlds']
    elif case == 'geophys-device-effort':
        test = Path(__file__).resolve().parents[5] / 'GeoPhys/test/verification/rigid/test_rigid_batch_no_contact.py'
        command = [sys.executable, '-m', 'pytest', '-q',
                   str(test) + '::test_cuda_device_qfrc_has_independent_world_response']
    elif case == 'geophys-device-reset':
        test = Path(__file__).resolve().parents[5] / 'GeoPhys/test/verification/rigid/test_rigid_batch_no_contact.py'
        contact_test = test.with_name('test_rigid_batch_contact.py')
        command = [sys.executable, '-m', 'pytest', '-q',
                   str(test) + '::test_cuda_device_partial_reset_refreshes_selected_kinematics',
                   str(test) + '::test_cuda_device_reset_free_body_and_velocity_are_row_local',
                   str(contact_test) + '::test_cuda_device_reset_clears_only_selected_contact_cache']
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
    elif case == 'isaac-batch-probe':
        command = [worker_python, '-u', __file__, '--isaac-batch-probe']
    elif case == 'isaac-filter-probe':
        command = [worker_python, '-u', __file__, '--isaac-filter-probe']
    elif case == 'isaac-robot-filter-probe':
        command = [worker_python, '-u', __file__, '--isaac-robot-filter-probe']
    elif case == 'isaac-cross-filter-probe':
        command = [worker_python, '-u', __file__, '--isaac-cross-filter-probe']
    elif case == 'isaac-cross-filter-weak':
        command = [worker_python, '-u', __file__, '--isaac-cross-filter-weak']
    elif case == 'isaac-filter-cleanup-error':
        command = [worker_python, '-u', __file__, '--isaac-filter-cleanup-error']
    elif case.startswith('performance-pickcube-'):
        combinations = {
            f'performance-pickcube-{provider}-{mode}': (provider, mode)
            for provider in ('mujoco_warp', 'geophys', 'isaacsim')
            for mode in ('off', 'window', 'sensor', 'sensor-window')
        }
        provider, mode = combinations[case]
        command = [sys.executable, '-u', __file__, '--performance-pickcube',
                   '--worker-python', worker_python, '--performance-provider', provider]
        if 'sensor' in mode:
            command.append('--performance-sensor')
        if 'window' in mode:
            command.append('--performance-window')
    elif case.startswith('scale-check-'):
        combinations = {f'scale-check-{provider}-{task}': (provider, task)
                        for provider in ('mujoco_warp', 'geophys', 'isaacsim')
                        for task in ('pendulum', 'pickcube')}
        provider, task = combinations[case]
        command = [sys.executable, '-u', __file__, '--scale-check', '--worker-python', worker_python,
                   '--scale-provider', provider]
        if task == 'pickcube':
            command.append('--scale-pickcube')
    elif case == 'physics':
        command = [worker_python, '-u', __file__, '--physics']
    else:
        role = {'ipc': '--parent', 'raster': '--raster', 'transport-physics': '--transport-physics',
                'session-physics': '--session-physics', 'formal-device': '--formal-device',
                'pickcube-device-probe': '--pickcube-device-probe',
                'geophys-pickcube-device-probe': '--geophys-pickcube-device-probe',
                'geophys-pickcube-motion-probe': '--geophys-pickcube-motion-probe',
                'isaac-pickcube-device-probe': '--isaac-pickcube-device-probe',
                'isaac-pickcube-motion-probe': '--isaac-pickcube-motion-probe',
                'pickcube-motion-probe': '--pickcube-motion-probe',
                'pickcube-scalar-effort': '--pickcube-scalar-effort',
                'pickcube-record': '--pickcube-record',
                'pickcube-camera-record': '--pickcube-camera-record',
                'isaac-pickcube-record': '--isaac-pickcube-record',
                'isaac-pickcube-camera-record': '--isaac-pickcube-camera-record',
                'geophys-pickcube-camera-record': '--geophys-pickcube-camera-record',
                'pickcube-finger-contact': '--pickcube-finger-contact',
                'isaac-pickcube-finger-contact': '--isaac-pickcube-finger-contact',
                'geophys-pickcube-finger-contact': '--geophys-pickcube-finger-contact',
                'geophys-pickcube-hold-contact': '--geophys-pickcube-hold-contact',
                'geophys-pickcube-source-bias-contact': '--geophys-pickcube-source-bias-contact',
                'geophys-pickcube-controlled-contact': '--geophys-pickcube-controlled-contact',
                'permutation-mjwarp-pickcube': '--permutation-mjwarp-pickcube',
                'permutation-isaac-pickcube': '--permutation-isaac-pickcube',
                'permutation-geophys-pickcube': '--permutation-geophys-pickcube',
                'permutation-mjwarp-pendulum': '--permutation-mjwarp-pendulum',
                'permutation-geophys-pendulum': '--permutation-geophys-pendulum',
                'permutation-isaac-pendulum': '--permutation-isaac-pendulum',
                'pickcube-window': '--pickcube-window',
                'pickcube-sensor-window': '--pickcube-sensor-window',
                'isaac-pickcube-window': '--isaac-pickcube-window',
                'isaac-pickcube-sensor-window': '--isaac-pickcube-sensor-window',
                'geophys-pickcube-window': '--geophys-pickcube-window',
                'geophys-pickcube-sensor-window': '--geophys-pickcube-sensor-window',
                'geophys-pendulum-source': '--geophys-pendulum-source',
                'pickcube-camera-probe': '--pickcube-camera-probe',
                'isaac-pickcube-camera-probe': '--isaac-pickcube-camera-probe',
                'geophys-pickcube-camera-probe': '--geophys-pickcube-camera-probe',
                'duplex-ipc': '--duplex-parent',
                'geophys-pendulum-formal': '--geophys-pendulum-formal',
                'geophys-pendulum-formal-discrete': '--geophys-pendulum-formal-discrete',
                'geophys-pendulum-window': '--geophys-pendulum-window',
                'geophys-pendulum-record': '--geophys-pendulum-record',
                'isaac-pendulum-formal': '--isaac-pendulum-formal',
                'isaac-pendulum-window': '--isaac-pendulum-window',
                'isaac-pendulum-record': '--isaac-pendulum-record',
                'geophys-pickcube-plan': '--geophys-pickcube-plan',
                'geophys-pickcube-plan-discrete': '--geophys-pickcube-plan-discrete',
                'performance-pendulum-off': '--performance-pendulum-off',
                'performance-pendulum-window': '--performance-pendulum-window',
                'performance-geophys-off': '--performance-geophys-off',
                'performance-geophys-window': '--performance-geophys-window',
                'performance-isaac-off': '--performance-isaac-off',
                'performance-isaac-window': '--performance-isaac-window',
                'device-sha-pendulum': '--device-sha-pendulum',
                'device-sha-pickcube': '--device-sha-pickcube',
                'device-sha-pickcube-camera': '--device-sha-pickcube-camera',
                'mjwarp-world-clock': '--mjwarp-world-clock',
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
    if case.startswith(('performance-', 'scale-check-')):
        command.extend(['--batch-size', str(batch_size)])
    start = time.monotonic()
    baseline_gpu_mib = _gpu_used_mib()
    environment = os.environ.copy()
    if case in ('isaac-batch-probe', 'isaac-filter-probe', 'isaac-robot-filter-probe',
                'isaac-cross-filter-probe', 'isaac-cross-filter-weak', 'isaac-filter-cleanup-error'):
        import sysconfig
        environment['GEOCHORA_DIAGNOSTIC_CORE_SITE'] = sysconfig.get_path('purelib')
    with harness._open_shared_native_lock() as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        legacy = harness.LEGACY_LOCK.exists()
        if not harness._lock_matches_legacy(lock, require_legacy=legacy):
            raise RuntimeError('native lock alias differs')
        with (output / 'stdout.log').open('wb') as out, (output / 'stderr.log').open('wb') as err:
            with harness._supervised_worker(command, environment=environment, stdout=out, stderr=err,
                    cwd=output, lock_fd=lock.fileno()) as (proc, state):
                violation = None
                peak_rss = peak_gpu_mib = 0
                peak_card_mib = baseline_gpu_mib
                while proc.poll() is None:
                    rss = harness._proc_rss_tree(proc.pid)
                    gpu_mib = _gpu_group_mib(proc.pid)
                    peak_card_mib = max(peak_card_mib, _gpu_used_mib())
                    peak_rss, peak_gpu_mib = max(peak_rss, rss), max(peak_gpu_mib, gpu_mib)
                    if not harness._lock_matches_legacy(lock, require_legacy=legacy):
                        violation = 'shared lock changed'
                    elif time.monotonic() - start > 900:
                        violation = '900 second wall timeout'
                    elif harness._mem_available_bytes() < 1024**3:
                        violation = 'less than 1 GiB host memory available'
                    elif rss > 10 * 1024**3:
                        violation = 'process tree exceeds 10 GiB RSS'
                    elif harness._gpu_free_mib() < 512:
                        violation = 'less than 512 MiB GPU memory available'
                    elif gpu_mib > 6144:
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
                       'wall_seconds': time.monotonic() - start,
                       'sampled_peak_process_tree_rss_bytes': peak_rss,
                       'sampled_peak_process_group_gpu_mib': peak_gpu_mib,
                       'baseline_card_gpu_mib': baseline_gpu_mib,
                       'sampled_peak_card_gpu_mib': peak_card_mib}
    # PhysX can return zero while reporting that a fixed GPU buffer overflow
    # caused missed interactions. Such a run cannot qualify as physics evidence.
    with (output / 'stderr.log').open('rb') as native_log:
        if any(b'simulation will miss interactions' in line for line in native_log):
            violation = violation or 'PhysX reported missed interactions'
            receipt['violation'] = violation
    if case in ('isaac-filter-probe', 'isaac-robot-filter-probe',
                'isaac-cross-filter-probe', 'isaac-cross-filter-weak', 'isaac-filter-cleanup-error') and code == 0:
        lines = (output / 'stdout.log').read_text(errors='replace').splitlines()
        try:
            outcome = json.loads(lines[-1])
        except (IndexError, json.JSONDecodeError):
            outcome = {}
        if outcome.get('status') != 'PASS':
            violation = violation or 'Isaac collision control did not pass'
            receipt['violation'] = violation
    (output / 'supervisor.json').write_text(json.dumps(receipt, indent=2) + '\n')
    if code != 0 or violation or state['forced_retirement']:
        raise RuntimeError(f'IPC probe failed: {receipt}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--duplex-worker', action='store_true')
    parser.add_argument('--duplex-parent', action='store_true')
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
    parser.add_argument('--pickcube-device-probe', action='store_true')
    parser.add_argument('--geophys-pickcube-device-probe', action='store_true')
    parser.add_argument('--geophys-pickcube-motion-probe', action='store_true')
    parser.add_argument('--isaac-pickcube-device-probe', action='store_true')
    parser.add_argument('--isaac-pickcube-motion-probe', action='store_true')
    parser.add_argument('--pickcube-motion-probe', action='store_true')
    parser.add_argument('--pickcube-scalar-effort', action='store_true')
    parser.add_argument('--pickcube-record', action='store_true')
    parser.add_argument('--pickcube-camera-record', action='store_true')
    parser.add_argument('--isaac-pickcube-record', action='store_true')
    parser.add_argument('--isaac-pickcube-camera-record', action='store_true')
    parser.add_argument('--geophys-pickcube-camera-record', action='store_true')
    parser.add_argument('--pickcube-finger-contact', action='store_true')
    parser.add_argument('--isaac-pickcube-finger-contact', action='store_true')
    parser.add_argument('--geophys-pickcube-finger-contact', action='store_true')
    parser.add_argument('--geophys-pickcube-hold-contact', action='store_true')
    parser.add_argument('--geophys-pickcube-source-bias-contact', action='store_true')
    parser.add_argument('--geophys-pickcube-controlled-contact', action='store_true')
    parser.add_argument('--permutation-mjwarp-pickcube', action='store_true')
    parser.add_argument('--permutation-isaac-pickcube', action='store_true')
    parser.add_argument('--permutation-geophys-pickcube', action='store_true')
    parser.add_argument('--permutation-mjwarp-pendulum', action='store_true')
    parser.add_argument('--permutation-geophys-pendulum', action='store_true')
    parser.add_argument('--permutation-isaac-pendulum', action='store_true')
    parser.add_argument('--pickcube-window', action='store_true')
    parser.add_argument('--pickcube-sensor-window', action='store_true')
    parser.add_argument('--isaac-pickcube-window', action='store_true')
    parser.add_argument('--isaac-pickcube-sensor-window', action='store_true')
    parser.add_argument('--geophys-pickcube-window', action='store_true')
    parser.add_argument('--geophys-pickcube-sensor-window', action='store_true')
    parser.add_argument('--geophys-pendulum-source', action='store_true')
    parser.add_argument('--geophys-pendulum-formal', action='store_true')
    parser.add_argument('--geophys-pendulum-formal-discrete', action='store_true')
    parser.add_argument('--geophys-pendulum-window', action='store_true')
    parser.add_argument('--geophys-pendulum-record', action='store_true')
    parser.add_argument('--geophys-pickcube-plan', action='store_true')
    parser.add_argument('--geophys-pickcube-plan-discrete', action='store_true')
    parser.add_argument('--geophys-pickcube-camera-probe', action='store_true')
    parser.add_argument('--performance-pendulum-off', action='store_true')
    parser.add_argument('--performance-pendulum-window', action='store_true')
    parser.add_argument('--performance-geophys-off', action='store_true')
    parser.add_argument('--performance-geophys-window', action='store_true')
    parser.add_argument('--performance-isaac-off', action='store_true')
    parser.add_argument('--performance-isaac-window', action='store_true')
    parser.add_argument('--performance-pickcube', action='store_true')
    parser.add_argument('--performance-provider', choices=('mujoco_warp', 'geophys', 'isaacsim'), default='mujoco_warp')
    parser.add_argument('--performance-sensor', action='store_true')
    parser.add_argument('--performance-window', action='store_true')
    parser.add_argument('--scale-check', action='store_true')
    parser.add_argument('--scale-provider', choices=('mujoco_warp', 'geophys', 'isaacsim'))
    parser.add_argument('--scale-pickcube', action='store_true')
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--device-sha-pendulum', action='store_true')
    parser.add_argument('--device-sha-pickcube', action='store_true')
    parser.add_argument('--device-sha-pickcube-camera', action='store_true')
    parser.add_argument('--mjwarp-world-clock', action='store_true')
    parser.add_argument('--isaac-batch-probe', action='store_true')
    parser.add_argument('--isaac-filter-probe', action='store_true')
    parser.add_argument('--isaac-robot-filter-probe', action='store_true')
    parser.add_argument('--isaac-cross-filter-probe', action='store_true')
    parser.add_argument('--isaac-cross-filter-weak', action='store_true')
    parser.add_argument('--isaac-filter-cleanup-error', action='store_true')
    parser.add_argument('--isaac-pendulum-formal', action='store_true')
    parser.add_argument('--isaac-pendulum-window', action='store_true')
    parser.add_argument('--isaac-pendulum-record', action='store_true')
    parser.add_argument('--pickcube-camera-probe', action='store_true')
    parser.add_argument('--isaac-pickcube-camera-probe', action='store_true')
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
    parser.add_argument(
        '--case',
        choices=(
            'ipc', 'physics', 'raster', 'transport-physics', 'geophys-pickcube-device-probe', 'geophys-pickcube-motion-probe',
            'geophys-pickcube-camera-probe', 'geophys-pickcube-camera-record', 'geophys-pickcube-finger-contact', 'geophys-pickcube-hold-contact', 'geophys-pickcube-source-bias-contact', 'geophys-pickcube-controlled-contact', 'permutation-geophys-pickcube', 'geophys-table-stability',
            'transport-frames', 'session-physics', 'formal-device', 'pickcube-device-probe',
            'pickcube-motion-probe', 'pickcube-scalar-effort', 'pickcube-record', 'geophys-pendulum-source',
            'geophys-pendulum-formal', 'geophys-pendulum-formal-discrete', 'geophys-pendulum-window', 'geophys-pendulum-record', 'geophys-pickcube-plan', 'geophys-pickcube-plan-discrete',
            'pickcube-camera-probe', 'duplex-ipc', 'isaac-batch-probe', 'isaac-pendulum-formal',
            'isaac-pendulum-window', 'isaac-pendulum-record', 'formal-render', 'formal-camera',
            'formal-frames', 'formal-window', 'record-device', 'record-camera',
            'record-render-fixture', 'clip-cuda', 'isaac-device', 'isaac-render',
            'isaac-window', 'isaac-mount', 'isaac-sensor', 'isaac-sensor-window',
            'isaac-sensor-record', 'example', 'scalar', 'scalar-camera-schema',
            'framebuffer-device', 'geophys-camera', 'geophys-aot-core', 'geophys-merge-regression',
            'geophys-merge-clip', 'geophys-merge-focused', 'geophys-merge-lighting', 'geophys-merge-mjcf-light',
            'geophys-merge-rigid', 'geophys-merge-robot', 'geophys-batch-cuda', 'geophys-device-state',
            'geophys-device-effort', 'geophys-device-reset', 'geophys-free-damping', 'geophys-static-contact-filter', 'geophys-torsion', 'geophys-torsion-direct', 'geophys-torsion-constraints', 'geophys-efc-regression', 'geophys-batch-plan-regression', 'geophys-actuator-isolation', 'geophys-device-layout', 'geophys-contact-mode-comparison', 'geophys-mesh-contact', 'transport-regression', 'core-semantics',
            'scalar-effort-regression', 'core-regression', 'performance-pendulum-off', 'performance-pendulum-window',
            'performance-geophys-off', 'performance-geophys-window', 'performance-isaac-off', 'performance-isaac-window',
            'device-sha-pendulum', 'device-sha-pickcube', 'device-sha-pickcube-camera', 'mjwarp-world-clock',
            'isaac-pickcube-device-probe', 'isaac-pickcube-motion-probe', 'isaac-pickcube-record', 'isaac-pickcube-camera-probe',
            'isaac-pickcube-camera-record', 'isaac-filter-probe', 'isaac-robot-filter-probe', 'isaac-cross-filter-probe', 'isaac-cross-filter-weak', 'isaac-filter-cleanup-error', 'pickcube-camera-record', 'pickcube-finger-contact',
            'isaac-pickcube-finger-contact', 'pickcube-example', 'pickcube-example-sensor', 'geophys-pickcube-example', 'permutation-mjwarp-pickcube',
            'permutation-isaac-pickcube', 'permutation-mjwarp-pendulum', 'permutation-geophys-pendulum', 'permutation-isaac-pendulum',
            'pickcube-window', 'pickcube-sensor-window', 'isaac-pickcube-window', 'isaac-pickcube-sensor-window', 'geophys-pickcube-window', 'geophys-pickcube-sensor-window',
            *(f'performance-pickcube-{provider}-{mode}'
              for provider in ('mujoco_warp', 'geophys', 'isaacsim')
              for mode in ('off', 'window', 'sensor', 'sensor-window')),
            *(f'scale-check-{provider}-{task}'
              for provider in ('mujoco_warp', 'geophys', 'isaacsim')
              for task in ('pendulum', 'pickcube')),
        ),
        default='ipc',
    )
    parser.add_argument('--worker-python')
    parser.add_argument('--output')
    args = parser.parse_args()
    if args.worker:
        _worker()
    elif args.duplex_worker:
        _duplex_worker()
    elif args.duplex_parent:
        print(json.dumps(_duplex_parent()))
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
    elif args.pickcube_device_probe:
        print(json.dumps(_pickcube_device_probe(args.worker_python)))
    elif args.isaac_pickcube_device_probe:
        print(json.dumps(_pickcube_device_probe(args.worker_python, provider='isaacsim')))
    elif args.isaac_pickcube_motion_probe:
        print(json.dumps(_pickcube_device_probe(args.worker_python, motion=True, provider='isaacsim')))
    elif args.pickcube_motion_probe:
        print(json.dumps(_pickcube_device_probe(args.worker_python, motion=True)))
    elif args.pickcube_scalar_effort:
        print(json.dumps(_pickcube_scalar_effort()))
    elif args.pickcube_record:
        print(json.dumps(_pickcube_record(args.worker_python)))
    elif args.pickcube_camera_record:
        print(json.dumps(_pickcube_record(args.worker_python, sensor=True)))
    elif args.isaac_pickcube_record:
        print(json.dumps(_pickcube_record(args.worker_python, provider='isaacsim')))
    elif args.isaac_pickcube_camera_record:
        print(json.dumps(_pickcube_record(args.worker_python, provider='isaacsim', sensor=True)))
    elif args.geophys_pickcube_camera_record:
        print(json.dumps(_pickcube_record(args.worker_python, provider='geophys', sensor=True)))
    elif args.pickcube_finger_contact:
        print(json.dumps(_pickcube_finger_contact(args.worker_python, provider='mujoco_warp')))
    elif args.isaac_pickcube_finger_contact:
        print(json.dumps(_pickcube_finger_contact(args.worker_python, provider='isaacsim')))
    elif args.geophys_pickcube_finger_contact:
        print(json.dumps(_pickcube_finger_contact(args.worker_python, provider='geophys')))
    elif args.geophys_pickcube_hold_contact:
        print(json.dumps(_pickcube_finger_contact(args.worker_python, provider='geophys', hold_arm=True)))
    elif args.geophys_pickcube_source_bias_contact:
        print(json.dumps(_pickcube_finger_contact(args.worker_python, provider='geophys', hold_arm='source-bias')))
    elif args.geophys_pickcube_controlled_contact:
        print(json.dumps(_pickcube_finger_contact(args.worker_python, provider='geophys', hold_arm='source-bias-descend')))
    elif args.permutation_mjwarp_pickcube:
        print(json.dumps(_action_permutation(args.worker_python, provider='mujoco_warp', pickcube=True)))
    elif args.permutation_isaac_pickcube:
        print(json.dumps(_action_permutation(args.worker_python, provider='isaacsim', pickcube=True)))
    elif args.permutation_geophys_pickcube:
        print(json.dumps(_action_permutation(args.worker_python, provider='geophys', pickcube=True)))
    elif args.permutation_mjwarp_pendulum:
        print(json.dumps(_action_permutation(args.worker_python, provider='mujoco_warp', pickcube=False)))
    elif args.permutation_geophys_pendulum:
        print(json.dumps(_action_permutation(args.worker_python, provider='geophys', pickcube=False)))
    elif args.permutation_isaac_pendulum:
        print(json.dumps(_action_permutation(args.worker_python, provider='isaacsim', pickcube=False)))
    elif args.pickcube_window:
        print(json.dumps(_pickcube_window_probe(args.worker_python, provider='mujoco_warp', sensor=False)))
    elif args.pickcube_sensor_window:
        print(json.dumps(_pickcube_window_probe(args.worker_python, provider='mujoco_warp', sensor=True)))
    elif args.isaac_pickcube_window:
        print(json.dumps(_pickcube_window_probe(args.worker_python, provider='isaacsim', sensor=False)))
    elif args.isaac_pickcube_sensor_window:
        print(json.dumps(_pickcube_window_probe(args.worker_python, provider='isaacsim', sensor=True)))
    elif args.geophys_pickcube_window:
        print(json.dumps(_pickcube_window_probe(args.worker_python, provider='geophys', sensor=False)))
    elif args.geophys_pickcube_sensor_window:
        print(json.dumps(_pickcube_window_probe(args.worker_python, provider='geophys', sensor=True)))
    elif args.geophys_pendulum_source:
        print(json.dumps(_geophys_pendulum_source_probe()))
    elif args.geophys_pendulum_formal:
        print(json.dumps(_formal_device(args.worker_python, provider='geophys')))
    elif args.geophys_pendulum_formal_discrete:
        print(json.dumps(_formal_device(args.worker_python, provider='geophys', contact_mode='discrete')))
    elif args.geophys_pendulum_window:
        print(json.dumps(_formal_window(args.worker_python, provider='geophys')))
    elif args.geophys_pendulum_record:
        print(json.dumps(_record_device(args.worker_python, provider='geophys')))
    elif args.geophys_pickcube_plan:
        print(json.dumps(_geophys_pickcube_plan()))
    elif args.geophys_pickcube_device_probe:
        print(json.dumps(_pickcube_device_probe(args.worker_python, provider='geophys')))
    elif args.geophys_pickcube_motion_probe:
        print(json.dumps(_pickcube_device_probe(args.worker_python, provider='geophys', motion=True)))
    elif args.geophys_pickcube_plan_discrete:
        print(json.dumps(_geophys_pickcube_plan(contact_mode='discrete')))
    elif args.geophys_pickcube_camera_probe:
        print(json.dumps(_pickcube_camera_probe(args.worker_python, provider='geophys')))
    elif args.performance_pendulum_off:
        print(json.dumps(_pendulum_performance(args.worker_python, window=False, count=args.batch_size)))
    elif args.performance_pendulum_window:
        print(json.dumps(_pendulum_performance(args.worker_python, window=True, count=args.batch_size)))
    elif args.performance_geophys_off:
        print(json.dumps(_pendulum_performance(args.worker_python, window=False, provider='geophys', count=args.batch_size)))
    elif args.performance_geophys_window:
        print(json.dumps(_pendulum_performance(args.worker_python, window=True, provider='geophys', count=args.batch_size)))
    elif args.performance_isaac_off:
        print(json.dumps(_pendulum_performance(args.worker_python, window=False, provider='isaacsim', count=args.batch_size)))
    elif args.performance_isaac_window:
        print(json.dumps(_pendulum_performance(args.worker_python, window=True, provider='isaacsim', count=args.batch_size)))
    elif args.performance_pickcube:
        print(json.dumps(_pickcube_performance(args.worker_python, provider=args.performance_provider,
                                               sensor=args.performance_sensor, window=args.performance_window,
                                               count=args.batch_size)))
    elif args.scale_check:
        print(json.dumps(_scale_correctness(args.worker_python, provider=args.scale_provider,
                                            pickcube=args.scale_pickcube, count=args.batch_size)))
    elif args.device_sha_pendulum:
        print(json.dumps(_device_sha_probe(args.worker_python, pickcube=False)))
    elif args.device_sha_pickcube:
        print(json.dumps(_device_sha_probe(args.worker_python, pickcube=True)))
    elif args.device_sha_pickcube_camera:
        print(json.dumps(_device_sha_probe(args.worker_python, pickcube=True, sensor=True)))
    elif args.mjwarp_world_clock:
        print(json.dumps(_mjwarp_world_clock_probe(args.worker_python)))
    elif args.isaac_batch_probe:
        from isaac_batch_probe import run
        print(json.dumps(run()), flush=True)
        # Match the existing isolated Isaac worker's terminal boundary after
        # successful App, stage and source cleanup; Kit's later CPython
        # finalization is unsafe in this profile.
        from task_env.runtime.sessions.worker import _exit_after_isaac_cleanup
        _exit_after_isaac_cleanup(0)
    elif args.isaac_filter_probe:
        from isaac_batch_probe import run_pickcube_collision_filter
        print(json.dumps(run_pickcube_collision_filter()), flush=True)
    elif args.isaac_robot_filter_probe:
        from isaac_batch_probe import run_pickcube_collision_filter
        print(json.dumps(run_pickcube_collision_filter(participant='robot')), flush=True)
    elif args.isaac_cross_filter_probe:
        from isaac_batch_probe import run_pickcube_collision_filter
        print(json.dumps(run_pickcube_collision_filter(participant='cross')), flush=True)
    elif args.isaac_cross_filter_weak:
        from isaac_batch_probe import run_pickcube_collision_filter
        print(json.dumps(run_pickcube_collision_filter(participant='cross', cross_cube_height=.5661)), flush=True)
    elif args.isaac_filter_cleanup_error:
        from isaac_batch_probe import run_pickcube_collision_filter
        print(json.dumps(run_pickcube_collision_filter(participant='cross', inject_failure=True)), flush=True)
        from task_env.runtime.sessions.worker import _exit_after_isaac_cleanup
        _exit_after_isaac_cleanup(0)
    elif args.isaac_pendulum_formal:
        print(json.dumps(_formal_device(args.worker_python, provider='isaacsim')))
    elif args.isaac_pendulum_window:
        print(json.dumps(_formal_window(args.worker_python, provider='isaacsim')))
    elif args.isaac_pendulum_record:
        print(json.dumps(_record_device(args.worker_python, provider='isaacsim')))
    elif args.pickcube_camera_probe:
        print(json.dumps(_pickcube_camera_probe(args.worker_python)))
    elif args.isaac_pickcube_camera_probe:
        print(json.dumps(_pickcube_camera_probe(args.worker_python, provider='isaacsim')))
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
        _run(args.worker_python, args.output, args.case, batch_size=args.batch_size)
    else:
        parser.error('choose --run, --parent or --worker')


if __name__ == '__main__':
    main()
