"""Small provider-free checks for the task renderer construction boundary."""
from types import SimpleNamespace

import pytest

from task_env.render.camera.task_rgb import create_task_rgb_consumer
from task_env.diagnostics.tasks.test_v211_task_rgb import _camera, _capture, _state, _Session


@pytest.mark.parametrize('provider,renderer', [('isaacsim', 'isaacsim'), ('geophys', 'geophys')])
def test_borrowed_camera_uses_runtime_without_mujoco_source(provider, renderer):
    camera = _camera()
    owner = SimpleNamespace()
    calls = []
    owner.bind_task_camera = lambda selected, state: calls.append(('bind', selected, state))
    artifact = SimpleNamespace(identity_hash=camera.task_artifact_hash)
    forbidden = lambda: pytest.fail('borrowed camera must not request a MuJoCo source')
    consumer = create_task_rgb_consumer(camera=camera, renderer=renderer, provider=provider,
        backend='cuda' if provider == 'isaacsim' else 'cpu', provider_seed=1,
        artifact=artifact, color_space='test', session_getter=lambda: owner,
        source_getter=forbidden, binding_getter=forbidden)
    owner.capture_task_camera = lambda selected, state: _capture(selected, consumer.renderer, state)
    image, receipt = consumer.capture(_state(0))
    assert calls[0][0] == 'bind' and image.flags.owndata
    assert receipt['capture_identity']['state_boundary'] == _state(0).boundary.to_mapping()
    consumer.close()


def test_cross_renderer_checks_source_identity_before_session(monkeypatch):
    from task_env.render.camera import api
    from task_env.render.camera.source import DynamicCameraRenderSourceV2

    source = object()
    artifact = SimpleNamespace(identity_hash='c' * 64)
    rendered = SimpleNamespace(identity_hash='render-a')
    binding = (source, artifact.identity_hash, object(), {}, {}, object(), rendered)
    monkeypatch.setattr(DynamicCameraRenderSourceV2, 'from_runtime_source',
        classmethod(lambda cls, *args, **kwargs: SimpleNamespace(identity_hash='render-b')))
    monkeypatch.setattr(api, 'create_dynamic_camera_session',
        lambda *args, **kwargs: pytest.fail('foreign visual source must not create a session'))
    consumer = create_task_rgb_consumer(camera=_camera(), renderer='mujoco', provider='geophys',
        backend='cpu', provider_seed=1, artifact=artifact, color_space='test',
        session_getter=lambda: None, source_getter=lambda: source, binding_getter=lambda: binding)
    with pytest.raises(ValueError, match='source changed'):
        consumer.capture(_state(0))
    consumer.close()


def test_cross_renderer_binds_current_public_state(monkeypatch):
    from task_env.render.camera import api
    from task_env.render.camera.source import DynamicCameraRenderSourceV2

    source = object()
    artifact = SimpleNamespace(identity_hash='c' * 64)
    rendered = SimpleNamespace(identity_hash='render-a')
    binding = (source, artifact.identity_hash, object(), {}, {}, object(), rendered)
    monkeypatch.setattr(DynamicCameraRenderSourceV2, 'from_runtime_source',
        classmethod(lambda cls, *args, **kwargs: rendered))
    calls = []
    def create(camera, execution, *, source, initial_state):
        calls.append((source, initial_state, execution))
        return _Session(camera, consumer.renderer)
    monkeypatch.setattr(api, 'create_dynamic_camera_session', create)
    consumer = create_task_rgb_consumer(camera=_camera(), renderer='mujoco', provider='geophys',
        backend='cpu', provider_seed=1, artifact=artifact, color_space='test',
        session_getter=lambda: None, source_getter=lambda: source, binding_getter=lambda: binding)
    state = _state(0)
    _, receipt = consumer.capture(state)
    assert calls[0][:2] == (rendered, state)
    assert receipt['capture_identity']['state_boundary'] == state.boundary.to_mapping()
    consumer.close()
