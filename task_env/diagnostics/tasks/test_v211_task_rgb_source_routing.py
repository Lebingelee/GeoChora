"""Provider-free checks for task RGB state vs renderer source ownership."""
from types import SimpleNamespace

import pytest

from task_env.diagnostics.tasks.test_v211_physical_control_contract import _case
from task_env.environment.reference_env import SelectedReferenceEnv
from task_env.render.camera.source import DynamicCameraRenderSourceV2


def _env(renderer):
    compiled, _, _, _ = _case()
    artifact = SimpleNamespace(identity_hash='a' * 64, legacy_frame_bindings={})
    source = SimpleNamespace(
        scene_definition=compiled.scene, source_id='source-a',
        source_closure_digest='b' * 64, task_artifact_hash=artifact.identity_hash,
        joints={'arm/drive': 'drive'}, bodies={}, frames={}, free_joints={},
    )
    env = object.__new__(SelectedReferenceEnv)
    env.artifact = artifact
    env.value = {'source': source}
    env._task_rgb_config = (object(), renderer)
    return env, source


@pytest.mark.parametrize('renderer', ('isaacsim', 'geophys'))
def test_borrowed_camera_state_does_not_require_mujoco_source(monkeypatch, renderer):
    env, source = _env(renderer)
    def unexpected(*args, **kwargs):
        raise AssertionError('borrowed camera must not construct a MuJoCo visual source')
    monkeypatch.setattr(DynamicCameraRenderSourceV2, 'from_runtime_source', unexpected)
    binding = env._prepare_task_rgb_state_binding()
    assert binding[0] is source
    assert 'arm/drive' in binding[3]
    assert binding[-1] is None


def test_mujoco_renderer_still_requires_its_source_adapter(monkeypatch):
    env, source = _env('mujoco')
    calls = []
    projection = SimpleNamespace(
        validate_binding_provenance=lambda: calls.append('validated'),
    )
    def construct(actual_source, **kwargs):
        calls.append(actual_source)
        return projection
    monkeypatch.setattr(DynamicCameraRenderSourceV2, 'from_runtime_source', construct)
    assert env._prepare_task_rgb_state_binding()[-1] is projection
    assert calls == [source, 'validated']


def test_task_rgb_rejects_foreign_artifact_before_renderer_selection():
    env, source = _env('isaacsim')
    source.task_artifact_hash = 'f' * 64
    with pytest.raises(ValueError, match='Artifact'):
        env._prepare_task_rgb_state_binding()
