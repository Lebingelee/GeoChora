"""Record real CUDA frames through a controlled batch lifecycle.

The g06 runner supplies either Pendulum observer crops or real Isaac hand
camera images. The subsequent episode boundaries are a controlled fixture.
"""
from __future__ import annotations

import os


def _capture_frames(worker_python):
    import torch
    from task_env import make_parallel_env

    config = {'execution': {'physics_provider': 'mujoco_warp', 'interpreter': worker_python},
              'episode': {'seed': 73, 'horizon': 200}}
    env = make_parallel_env('pendulum-v1', env_config=config, num_env=3, backend='cuda',
                            execution='device', render_mode='rgb_array', worker_directory=os.getcwd())
    frames, states, identities = [], [], []
    initial_snapshot = None
    try:
        obs, _ = env.reset(seed=73)
        action = {'torque': torch.tensor([[-1.5], [.5], [1.5]], dtype=torch.float32, device='cuda')}
        for tick in range(21):
            if tick:
                obs, _, terminated, truncated, _ = env.step(action)
                if bool((terminated | truncated).any()):
                    raise AssertionError('frame source ended before fixture capture completed')
            if tick not in (0, 3, 6, 9, 12, 16, 20):
                continue
            image = env.render()
            if image.device.type != 'cuda' or image.dtype != torch.uint8:
                raise AssertionError('observer frame is not a CUDA uint8 image')
            # Each crop is taken directly from one visible world in the real
            # B=3 observer frame. It is not a mounted-camera observation.
            crops = torch.stack([image[175:303, x:x + 128, :] for x in (150, 263, 370)])
            frames.append(crops.clone())
            if initial_snapshot is None:
                initial_snapshot = frames[0].clone()
            states.append(obs['state']['proprioception'].clone())
            identities.append(env.read_device_state(('qpos',)).identity)
        if torch.equal(frames[0], frames[-1]) or not torch.equal(frames[0], initial_snapshot):
            raise AssertionError('source frames do not show motion or retain their device data')
    finally:
        env.close()
    return frames, states, identities


def _fixture(frames, states, identities, *, mounted=False):
    import gymnasium as gym
    import numpy as np
    import torch

    image_group, image_name = ('cameras', 'hand') if mounted else ('frames', 'observer_crop')
    state_name = 'hand_position' if mounted else 'proprioception'

    class ControlledLifecycle:
        num_envs = 3
        metadata = {'execution': 'device_worker', 'action_schema': {'components': ['torque']}}
        single_action_space = gym.spaces.Dict({'torque': gym.spaces.Box(-2., 2., (1,), dtype=np.float32)})
        action_space = gym.vector.utils.batch_space(single_action_space, 3)
        single_observation_space = gym.spaces.Dict({
            'state': gym.spaces.Dict({state_name: gym.spaces.Box(-np.inf, np.inf, (3,), dtype=np.float32)}),
            image_group: gym.spaces.Dict({image_name: gym.spaces.Dict({
                'rgb': gym.spaces.Box(0, 255, (128, 128, 3), dtype=np.uint8)})})})
        observation_space = gym.vector.utils.batch_space(single_observation_space, 3)
        render_mode = None

        def __init__(self):
            self.episode = torch.ones(3, dtype=torch.int64, device='cuda')
            self.clock = torch.zeros(3, dtype=torch.int32, device='cuda')
            self.tick = 0

        def get_record_metadata(self):
            return {'env_metadata': self.metadata, 'resolved_config': {}, 'universal_action_schema': {}}

        def observation(self, index):
            return {'state': {state_name: states[index]}, image_group: {image_name: {'rgb': frames[index]}}}

        def info(self, index):
            return {'env_id': torch.arange(3, device='cuda'), 'episode_id': self.episode.clone(),
                    'episode_step': self.clock.clone(), 'boundary': identities[index]}

        def reset(self):
            return self.observation(0), self.info(0)

        def step(self, actions):
            del actions
            self.tick += 1
            self.clock += 1
            terminated = torch.tensor(([False, True, False], [True, False, False],
                                       [False, False, False])[self.tick - 1], device='cuda')
            truncated = torch.tensor(([False, False, False], [True, False, False],
                                      [False, True, False])[self.tick - 1], device='cuda')
            done = terminated | truncated
            old_index, new_index = 2 * self.tick - 1, 2 * self.tick
            old = self.info(old_index)
            final = self.observation(old_index)
            self.episode[done] += 1
            self.clock[done] = 0
            reset = self.info(new_index)
            info = dict(reset, final_info=old, reset_info=reset,
                        final_observation=final, _final_observation=done,
                        metrics={}, reward_terms={})
            return (self.observation(new_index), torch.zeros(3, device='cuda'),
                    terminated, truncated, info)

        def close(self):
            pass

    return ControlledLifecycle()


def run(worker_python):
    """Capture 20 real intervals and record three synthetic lifecycle transitions."""
    frames, states, identities = _capture_frames(worker_python)
    return record_frames(frames, states, identities)


def record_frames(frames, states, identities, *, mounted=False):
    """Record device frames against controlled old/new episode boundaries."""
    import numpy as np
    import torch
    from task_env.recorders import VectorTransitionRecorder

    image_group, image_name = ('cameras', 'hand') if mounted else ('frames', 'observer_crop')
    state_name = 'hand_position' if mounted else 'proprioception'
    recorder = VectorTransitionRecorder(_fixture(frames, states, identities, mounted=mounted),
                                        path=os.getcwd(), env_ids=(0, 1))
    expected = {}

    def remember(name, observation):
        expected[f'{name}_rgb'] = observation[image_group][image_name]['rgb'].cpu().numpy().copy()
        expected[f'{name}_state'] = observation['state'][state_name].cpu().numpy().copy()

    try:
        observation, _ = recorder.reset()
        remember('initial', observation)
        action = {'torque': torch.zeros((3, 1), device='cuda')}
        for index in range(1, 4):
            observation, _, _, _, info = recorder.step(action)
            done = info['_final_observation']
            if torch.equal(info['final_observation'][image_group][image_name]['rgb'][done],
                           observation[image_group][image_name]['rgb'][done]):
                raise AssertionError('controlled terminal and reset real frames are indistinguishable')
            remember(f'final{index}', info['final_observation'])
            remember(f'next{index}', observation)
        expected['native_steps'] = np.array([item.native_step for item in identities], dtype=np.int64)
        expected['native_times'] = np.array([item.native_time_s for item in identities], dtype=np.float64)
        expected['generation'] = np.array(identities[0].generation, dtype=np.int64)
        np.savez_compressed('expected_mounted_values.npz' if mounted else 'expected_observer_values.npz', **expected)
    finally:
        recorder.close()
    return {'scope': ('real Isaac hand camera, controlled episode fixture; scalar physics' if mounted else
                      'real CUDA observer crops, controlled episode fixture; not task-camera qualification'),
            'batch': 3, 'recorded_env_ids': [0, 1], 'native_batch_steps': 100 if mounted else 500,
            'world_steps': 100 if mounted else 1500, 'control_intervals': 20, 'fixture_transitions': 3,
            'files': [path.name for path in recorder.saved_paths], 'closed': True}
