"""Exercise named dynamic sites through the existing source-bound batch session.

The runner calls this diagnostic with a synthetic inline Scene. The real
MJWarp session, Controller, worker and IPC path are used without changing a
registered Robot or its frozen assets.
"""
from __future__ import annotations

import math
import os
import json
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path


def _build_source():
    from task_env.artifacts import FrameDefinition, FrameReference
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.registry import ENV_REGISTRY
    from task_env.robots.pendulum import PendulumEntity
    from task_env.runtime.sessions.source import project_mjcf_scene_source

    xml = ET.fromstring(PendulumEntity.source_xml)
    link = xml.find(".//body[@name='pendulum_link']")
    ET.SubElement(link, 'site', name='frame_probe', pos='.1 0 .3',
                  quat='.9238795325112867 0 0 .3826834323650898')
    inline_xml = ET.tostring(xml, encoding='unicode')

    class FrameRobot(PendulumEntity):
        source_xml = inline_xml

        def scene_definition(self, *, source_revision=None):
            scene = super().scene_definition(source_revision=source_revision)
            frame = FrameDefinition('frame-definition-v1', self.uid, 'frame_probe', 'runtime', None, None)
            return replace(scene, frames=(*scene.frames, frame))

    environment = ENV_REGISTRY.get('pendulum-v1')
    config = resolve_task_env_config(environment, {'execution': {'physics_provider': 'mujoco'},
                                                  'episode': {'seed': 73, 'horizon': 200}})
    binding = environment._build_selected_binding(config, robot=FrameRobot())
    built = binding.build_for_request('mujoco', 'cpu', 73, 200)
    source = replace(built['source'], frames={'pendulum-v1/frame_probe': 'frame_probe'})
    physical = built['physical_execution']
    physical = replace(physical, frame_bindings={**physical.frame_bindings,
        'pendulum-v1/frame_probe': FrameReference('pendulum-v1', 'frame_probe')})
    physical.validate_source(scene=source.scene_definition, artifact_sha256=built['artifact'].identity_hash,
        source_id=source.source_id, source_closure_sha256=source.source_closure_digest, source=source)
    projected, _, closure = project_mjcf_scene_source(source.scene_source, source.scene_definition)
    if closure != source.source_closure_digest or 'frame_probe' not in projected:
        raise AssertionError('fixture site and source closure are inconsistent')
    Path('frame-source-input.xml').write_text(source.scene_source.xml)
    Path('frame-source-projected.xml').write_text(projected)
    Path('frame-scene.json').write_text(json.dumps(source.scene_definition.to_mapping(), sort_keys=True) + '\n')
    return binding, {**built, 'source': source, 'physical_execution': physical}


def _oracle(state):
    import torch

    angle = state.arrays['qpos'][:, 0]
    cosine, sine = torch.cos(angle), torch.sin(angle)
    expected_position = torch.stack((.1 * cosine + .3 * sine, torch.zeros_like(angle),
                                     -.1 * sine + .3 * cosine), dim=1)
    cy, sy = torch.cos(angle / 2), torch.sin(angle / 2)
    cz, sz = math.cos(math.pi / 8), math.sin(math.pi / 8)
    expected_quat = torch.stack((cy * cz, sy * sz, sy * cz, cy * sz), dim=1)
    actual_position = state.arrays['frame_position'][:, 0]
    actual_quat = state.arrays['frame_orientation'][:, 0]
    sign = torch.where((actual_quat * expected_quat).sum(dim=1, keepdim=True) < 0, -1., 1.)
    error = max(float((actual_position - expected_position).abs().max().item()),
                float((actual_quat * sign - expected_quat).abs().max().item()))
    if error > 2e-5:
        raise AssertionError(f'published source frame differs from independent FK: {error}')
    return error


def run(worker_python):
    """Publish a declared site through a real session for twenty control intervals."""
    import numpy as np
    import torch
    from dataclasses import asdict
    from task_env.runtime.providers.mujoco_warp.batch import MuJoCoWarpBatchSession
    from task_env.runtime.sessions.source import close_source_and_task_resources
    from task_env.render.providers.parallel import ParallelRenderProvider
    from task_env.render.rasterizer.device import DeviceBatchRasterSource
    from task_env.vectorization.task_definition import BatchTaskLifecycleAdapter

    binding, built = _build_source()
    session = adapter = renderer = None
    primary = None
    try:
        session = MuJoCoWarpBatchSession(built, num_envs=3, device='cuda:0',
            interpreter=worker_python, working_directory=os.getcwd())
        summary = session.resource_summary()['device_transition']
        if summary['frame_names'] != ('pendulum-v1/frame_probe',):
            raise AssertionError('session frame names differ from the source declaration')
        published_fields = tuple(summary['state_shapes'])
        binding = binding.bind_compiled_control(built)
        definition = binding.task_definition_factory(built['artifact'])
        metadata = {'task_uid': 'pendulum-v1', 'num_envs': 3, 'backend': 'cuda',
                    'execution': 'device_worker', 'transfer_mode': 'device',
                    'runtime_resource_summary': session.resource_summary(),
                    'action_schema': dict(binding.action_schema),
                    'observation_schema': asdict(binding.task_observation_schema)}
        adapter = BatchTaskLifecycleAdapter(uid='pendulum-v1', num_envs=3, backend='cuda', base_seed=73,
            runtime=session, reset_sampler=binding.task_reset_sampler, compiled_scene=None, initial_state=None,
            task_definition=definition, action_adapter=built['controller'],
            single_action_space=binding.action_space_factory(),
            single_observation_space=definition.device_observation_space(), metadata=metadata,
            horizon=200, ignore_done=False)
        state = adapter.reset_sampled_device(seed=73).state
        q, v = state.arrays['qpos'].clone(), state.arrays['qvel'].clone()
        initial = session.read_device_state(('qpos', 'frame_position', 'frame_orientation'))
        retained = initial.arrays['frame_position'].clone()
        errors = [_oracle(initial)]
        renderer = ParallelRenderProvider(num_envs=3,
            render_source=DeviceBatchRasterSource(runtime=session, source=built['source']),
            width=640, height=480)
        renderer.set_parallel_render_num(3)
        render_stream = torch.cuda.Stream()
        with torch.cuda.stream(render_stream):
            first_image = renderer.render(mode='rgb_array')
            repeated_image = renderer.render(mode='rgb_array')
        render_stream.synchronize()
        if (first_image.device.type != 'cuda' or first_image.dtype != torch.uint8
                or tuple(first_image.shape) != (480, 640, 3)
                or not torch.equal(first_image, repeated_image)
                or session.read_device_state(('qpos',)).identity != initial.identity):
            raise AssertionError('repeated device rendering changed the source boundary or frame')
        action = {'torque': torch.tensor([[-1.5], [.5], [1.5]], dtype=torch.float32, device='cuda')}
        previous = None
        for tick in range(20):
            previous = state.arrays['qpos'].clone()
            transition = adapter.step_device(action)
            if bool((transition.terminated | transition.truncated).any()):
                raise AssertionError(f'source task ended at controlled interval {tick + 1}')
            state = session.read_device_state(published_fields)
            errors.append(_oracle(state))
        stream = torch.cuda.Stream()
        with torch.cuda.stream(stream):
            last = session.read_device_state(('qpos', 'frame_position', 'frame_orientation'))
        stream.synchronize()
        if (last.identity.native_step != 500 or last.identity.native_time_s != 1.0
                or last.identity != state.identity or not torch.equal(initial.arrays['frame_position'], retained)):
            raise AssertionError('source frame boundary, stream completion or snapshot lifetime differs')
        last_image = renderer.render(mode='rgb_array')
        if torch.equal(first_image, last_image) or session.read_device_state(('qpos',)).identity != last.identity:
            raise AssertionError('source motion did not reach the shared renderer at the same boundary')
        noop = session.reset_device({'qpos': q, 'qvel': v}, torch.zeros(3, dtype=torch.bool, device='cuda'))
        if (noop.identity != state.identity or set(noop.arrays) != set(state.arrays)
                or any(not torch.equal(noop.arrays[name], state.arrays[name]) for name in state.arrays)):
            raise AssertionError('all-false reset changed the frame schema, data or physics boundary')
        masked = session.reset_device({'qpos': q, 'qvel': v},
                                      torch.tensor([False, True, False], dtype=torch.bool, device='cuda'))
        if (masked.identity.native_step != 500 or _oracle(masked) > 2e-5
                or not torch.equal(masked.arrays['frame_position'][[0, 2]], last.arrays['frame_position'][[0, 2]])
                or not torch.equal(masked.arrays['frame_orientation'][[0, 2]], last.arrays['frame_orientation'][[0, 2]])):
            raise AssertionError('masked reset changed another row or its published source frame')
        stale = torch.stack((.1 * torch.cos(previous[:, 0]) + .3 * torch.sin(previous[:, 0]),
                             torch.zeros(3, device='cuda'),
                             -.1 * torch.sin(previous[:, 0]) + .3 * torch.cos(previous[:, 0])), dim=1)
        stale_error = float((last.arrays['frame_position'][:, 0] - stale).abs().max().item())
        if stale_error < 1e-4:
            raise AssertionError('previous-boundary negative control is not distinguishable')
        np.savez('formal_frame_values.npz', initial_q=initial.arrays['qpos'].cpu().numpy(),
            initial_position=initial.arrays['frame_position'].cpu().numpy(),
            initial_quaternion=initial.arrays['frame_orientation'].cpu().numpy(),
            final_q=last.arrays['qpos'].cpu().numpy(),
            final_position=last.arrays['frame_position'].cpu().numpy(),
            final_quaternion=last.arrays['frame_orientation'].cpu().numpy(),
            noop_q=noop.arrays['qpos'].cpu().numpy(),
            noop_position=noop.arrays['frame_position'].cpu().numpy(),
            noop_quaternion=noop.arrays['frame_orientation'].cpu().numpy(),
            masked_q=masked.arrays['qpos'].cpu().numpy(),
            masked_position=masked.arrays['frame_position'].cpu().numpy(),
            masked_quaternion=masked.arrays['frame_orientation'].cpu().numpy(),
            initial_image=first_image.cpu().numpy(), final_image=last_image.cpu().numpy(),
            previous_q=previous.cpu().numpy())
        result = {'scope': 'formal source-bound batch session with synthetic declared site; not task camera',
                  'source_id': built['source'].source_id,
                  'source_closure_sha256': built['source'].source_closure_digest,
                  'frame_names': list(summary['frame_names']), 'device': last.device,
                  'max_fk_error': max(errors), 'previous_boundary_position_error': stale_error,
                  'native_batch_steps': 500, 'world_steps': 1500, 'control_intervals': 20,
                  'seed': 73, 'reset_sampler': 'device task lifecycle',
                  'renderer': 'geophys-rasterizer', 'repeated_render_advanced_physics': False,
                  'changed_pixel_components': int(torch.count_nonzero(first_image != last_image).item()),
                  'all_false_reset_keeps_fields': True, 'masked_reset_keeps_unselected_frames': True}
    except BaseException as error:
        primary = error
    finally:
        if renderer is not None:
            try:
                renderer.close()
            except BaseException as error:
                if primary is None:
                    primary = error
                else:
                    primary.add_note(f'renderer cleanup also failed: {error!r}')
        if session is not None:
            try:
                (adapter.close if adapter is not None else session.close)()
            except BaseException as error:
                if primary is None:
                    primary = error
                else:
                    primary.add_note(f'session cleanup also failed: {error!r}')
        primary = close_source_and_task_resources(built['source'], binding, error=primary)
    if primary is not None:
        raise primary
    if not torch.equal(initial.arrays['frame_position'], retained):
        raise AssertionError('owned frame snapshot changed after session close')
    result['closed'] = True
    return result
