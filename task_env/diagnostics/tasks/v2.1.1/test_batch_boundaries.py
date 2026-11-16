"""Pure capability admission and SB3 lifecycle checks; no native worker."""
from dataclasses import dataclass
import multiprocessing
import subprocess
import sys
from types import SimpleNamespace

import gymnasium as gym
import numpy as np
import pytest

FORMAL_UIDS = ('pick-cube-p16-reference-v1', 'nut-assembly-outcome-reference-v1',
               'pendulum-v1', 'two-wheel-balance-v1')


@pytest.mark.parametrize('uid', FORMAL_UIDS)
@pytest.mark.parametrize('execution', ['local', 'remote'])
def test_formal_batch_rejected_before_worker_or_runtime(uid, execution, monkeypatch):
    from task_env import make_parallel_env
    from task_env.environment.types import StageUnavailableError
    monkeypatch.setattr(multiprocessing, 'get_context', lambda *_: pytest.fail('worker requested'))
    with pytest.raises(StageUnavailableError, match='no formal batch adapter'):
        make_parallel_env(uid, num_env=2, backend='cpu', execution=execution)


def test_parallel_entry_does_not_require_sb3_until_bridge_is_used():
    code = '''
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.startswith("stable_baselines3"):
        raise AssertionError("SB3 imported before its bridge was requested")
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
import task_env.vectorization.parallel
'''
    subprocess.run([sys.executable, '-c', code], check=True)


@pytest.mark.parametrize('uid', FORMAL_UIDS)
def test_framework_factory_rejects_formal_config_before_resolution(uid, monkeypatch):
    from task_env.environment.types import StageUnavailableError
    from task_env.vectorization import factory

    monkeypatch.setattr(factory, 'resolve_task_env_config', lambda *_: pytest.fail('resolved formal batch'))
    monkeypatch.setattr(factory, 'make_batch_runtime', lambda **_: pytest.fail('runtime created'))
    with pytest.raises(StageUnavailableError, match='no formal batch adapter'):
        factory.make_framework_parallel_spec(uid=uid, num_env=2, env_config=None, backend='cpu')


def test_component_factory_still_builds_without_runtime_until_after_definition(monkeypatch):
    from task_env.vectorization import factory

    @dataclass(frozen=True)
    class Runtime:
        backend: str = 'cpu'

    @dataclass(frozen=True)
    class Config:
        runtime: Runtime = Runtime()

    seen = []

    class Component:
        def __init__(self, *, config, build_runtime):
            seen.append((config.runtime.backend, build_runtime))
            self.composition_spec = self.scene = self.agents = self.objects = None

        def create_scene_composer(self):
            return None

        def create_task_definition(self, compiled):
            raise LookupError('definition boundary reached')

    monkeypatch.setattr(factory.ENV_REGISTRY, 'get', lambda uid: Component)
    monkeypatch.setattr(factory, 'resolve_task_env_config', lambda cls, values: Config())
    monkeypatch.setattr(factory, 'compile_task_scene', lambda **kwargs: object())
    monkeypatch.setattr(factory, 'make_batch_runtime', lambda **kwargs: pytest.fail('early runtime'))
    with pytest.raises(LookupError, match='definition boundary reached'):
        factory.make_framework_parallel_spec(uid='component', num_env=2, env_config=None, backend='cuda')
    assert seen == [('cuda', False)]


@pytest.mark.parametrize('remote', [False, True])
def test_sb3_autoreset_preserves_terminal_observation_and_owner(remote):
    from task_env.vectorization.parallel import _step_and_autoreset
    from task_env.vectorization.sb3 import TaskEnvSB3VecAdapter

    class Batch:
        num_envs = 2
        metadata = {}
        render_mode = None
        single_observation_space = gym.spaces.Box(-10, 10, shape=(1,), dtype=np.float32)
        single_action_space = gym.spaces.Box(-1, 1, shape=(1,), dtype=np.float32)

        def step(self, actions):
            return (np.array([[1.], [2.]], dtype=np.float32), np.array([0., 1.]),
                    np.array([False, False]), np.array([False, True]), [{}, {}])

        def reset(self, *, seed=None, options=None, mask=None):
            assert mask.tolist() == [False, True]
            return np.array([[8.], [9.]], dtype=np.float32), [{}, {'reset': True}]

        def close(self):
            self.closed = True

    batch = Batch()
    actions = np.zeros((2, 1), dtype=np.float32)
    if remote:
        observation, _, done, infos = _step_and_autoreset(batch, actions)
    else:
        adapter = TaskEnvSB3VecAdapter(batch)
        adapter.step_async(actions)
        observation, _, done, infos = adapter.step_wait()
        adapter.close()
        assert batch.closed
    assert done.tolist() == [False, True]
    assert observation[:, 0].tolist() == [1., 9.]
    assert infos[1]['terminal_observation'].tolist() == [2.]
    assert infos[1]['reset_info'] == {'reset': True}
    assert infos[1]['TimeLimit.truncated'] is True


def test_renderer_close_failure_still_closes_task_and_runtime():
    from task_env.vectorization.homogeneous import HomogeneousVectorTaskEnv
    from task_env.vectorization.task_definition import BatchTaskLifecycleAdapter

    calls = []
    render_error = RuntimeError('renderer close failed')

    class Renderer:
        def close_render(self):
            calls.append('close_render')
            raise render_error

        def close(self):
            calls.append('provider_close')
            raise LookupError('provider close failed')

    class Runtime:
        def close(self):
            calls.append('runtime_close')

    renderer = Renderer()
    spec = SimpleNamespace(num_envs=1, metadata={}, parallel_render_provider=renderer, _source_resources=None,
        single_action_space=gym.spaces.Box(-1, 1, shape=(1,), dtype=np.float32),
        single_observation_space=gym.spaces.Box(-1, 1, shape=(1,), dtype=np.float32),
        runtime=Runtime())
    spec.close = lambda: BatchTaskLifecycleAdapter.close(spec)
    env = HomogeneousVectorTaskEnv(spec)
    with pytest.raises(RuntimeError) as caught:
        env.close()
    assert caught.value is render_error
    assert calls == ['close_render', 'provider_close', 'runtime_close']
    assert any('provider close failed' in note for note in caught.value.__notes__)
