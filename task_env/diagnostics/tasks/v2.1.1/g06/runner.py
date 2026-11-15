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


def _transport_physics(worker_python):
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
    request = {'device': 'cuda:0', 'source_xml': source.scene_source.xml,
               'source_joints': dict(source.joints), 'num_envs': 3,
               'physics_dt': built['artifact'].timebase.physics_dt,
               'control_substeps': built['artifact'].timebase.control_substeps,
               'channels': [{'channel': channel.to_mapping(),
                             'joint': execution.joint_bindings[
                                 f'{channel.entity_id}/{channel.joint_id}'].to_mapping()}
                            for channel in channels]}
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
                'source_id': source.source_id, 'worker_closed': True}
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
        if tuple(final.shape) != (2, 3) or info['episode_id'].tolist() != [2, 2, 2]:
            raise AssertionError('same-step reset did not retain final rows and advance episodes')
        if info['episode_step'].tolist() != [0, 15, 0] or info['final_episode_step'].tolist() != [20, 20]:
            raise AssertionError('per-row clocks do not match the staggered reset')
        expected_final = np.stack((np.cos(terminal_q), np.sin(terminal_q), terminal_v), axis=1)[[0, 2]]
        actual_final = final.cpu().numpy().copy()
        if (np.max(np.abs(actual_final[:, :2] - expected_final[:, :2])) > .01
                or np.max(np.abs(actual_final[:, 2] - expected_final[:, 2])) > .05):
            raise AssertionError('saved terminal observations do not describe the old transition')
        if torch.equal(final, observation['state']['proprioception'][[0, 2]]):
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
    elif case == 'physics':
        command = [worker_python, '-u', __file__, '--physics']
    else:
        role = {'ipc': '--parent', 'raster': '--raster', 'transport-physics': '--transport-physics',
                'session-physics': '--session-physics', 'formal-device': '--formal-device',
                'scalar': '--scalar'}[case]
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
    parser.add_argument('--session-physics', action='store_true')
    parser.add_argument('--formal-device', action='store_true')
    parser.add_argument('--scalar', action='store_true')
    parser.add_argument('--case', choices=('ipc', 'physics', 'raster', 'transport-physics', 'session-physics',
                                           'formal-device', 'example', 'scalar'),
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
    elif args.session_physics:
        print(json.dumps(_session_physics(args.worker_python)))
    elif args.formal_device:
        print(json.dumps(_formal_device(args.worker_python)))
    elif args.scalar:
        print(json.dumps(_scalar_compat()))
    elif args.physics:
        print(json.dumps(_physics()))
    elif args.run:
        _run(args.worker_python, args.output, args.case)
    else:
        parser.error('choose --run, --parent or --worker')


if __name__ == '__main__':
    main()
