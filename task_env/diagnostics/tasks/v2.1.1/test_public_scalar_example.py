"""Formal example callers without opening a source, Runtime or renderer."""
import ast
from contextlib import contextmanager
import json
from pathlib import Path
import re
from types import SimpleNamespace

import numpy as np


def test_pendulum_rgb_example_uses_formal_config_and_camera(monkeypatch, capsys):
    import task_env
    from examples.rendering import pendulum_single_rgb as example
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.environment.gym_compat import Box
    from task_env.render.base.contracts import validate_camera_declarations
    from task_env.render.camera.task_rgb import selected_observer_route
    from task_env.tasks.pendulum import PendulumEnv

    events = []
    observation = np.zeros(3, dtype=np.float32)
    space = Box(-1, 1, shape=(3,), dtype=np.float32)

    @contextmanager
    def budget(*_args):
        yield {'fake': True}

    def make_env(uid, *, config, render_mode, observer_camera):
        assert uid == 'pendulum-v1'
        resolved = resolve_task_env_config(PendulumEnv, config)
        assert resolved.physics_provider == 'geophys'
        assert resolved.environment.runtime.backend == 'cpu'
        validate_camera_declarations(render_mode=render_mode, observer_camera=observer_camera)
        assert 'rgb_array' in selected_observer_route(resolved, render_mode).modes

        def reset(*, seed):
            events.append(('reset', seed))
            return observation, {}

        def step(action):
            np.testing.assert_array_equal(action['torque'], np.zeros(1, dtype=np.float32))
            events.append(('step',))
            return observation, 1.0, False, False, {'is_success': True}

        return SimpleNamespace(
            observation_space=space, reset=reset, step=step,
            render=lambda: np.zeros((observer_camera.height, observer_camera.width, 3), dtype=np.float32),
            close=lambda: events.append(('close',)),
        )

    monkeypatch.setattr(example, 'bounded_process', budget)
    monkeypatch.setattr(example, 'bootstrap_imports', lambda: None)
    monkeypatch.setattr(task_env, 'make_env', make_env)
    assert example.main(['--width', '32', '--height', '24', '--seed', '73']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['frame_shape'] == [24, 32, 3]
    assert report['task_success'] is True
    assert report['reset_observation_valid'] and report['step_observation_valid']
    assert events == [('reset', 73), ('step',), ('close',)]


def test_documented_nut_solution_configuration_resolves_without_assets():
    from task_env.environment.configuration import resolve_task_env_config
    from task_env.tasks.nut_assembly.specialization import NutAssemblyReferenceEnv

    root = Path(__file__).resolve().parents[4]
    text = (root/'task_env/doc/api/planning/task_owned_solutions.md').read_text()
    snippet = re.search(r'```python\n(.*?)```', text, re.S).group(1)
    tree = ast.parse(snippet)
    call = next(node for node in ast.walk(tree) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name) and node.func.id == 'make_env')
    config = ast.literal_eval(next(item.value for item in call.keywords if item.arg == 'config'))
    resolved = resolve_task_env_config(NutAssemblyReferenceEnv, config)
    assert resolved.physics_provider == 'mujoco'
    assert resolved.environment.runtime.backend == 'cpu'
    assert resolved.environment.episode.horizon == 6000
