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


def test_task_rgb_clock_mapping_records_epoch_without_rewriting_timeline():
    from task_env.runtime.sessions.isaac_native_io import _task_render_clock_mapping

    receipt = _task_render_clock_mapping(provider_time_s=0.036, episode_time_s=0.0)

    assert receipt['schema_version'] == 'isaac-task-render-clock-observation-v1'
    assert receipt['episode_time_s'] == 0.0
    assert receipt['provider_time_s'] == pytest.approx(0.036)
    assert receipt['provider_epoch_offset_s'] == pytest.approx(0.036)
    assert receipt['timeline_mutated'] is False
    assert receipt['physics_step_requested'] is False
    with pytest.raises(ValueError, match='finite'):
        _task_render_clock_mapping(provider_time_s=float('nan'), episode_time_s=0.0)


def test_isaac_task_rgb_uses_historical_bound_sensor_and_sync_capture_route():
    import inspect
    from task_env.runtime.sessions.isaac_native_io import IsaacSimNativeRuntimeIOV1

    capture = inspect.getsource(IsaacSimNativeRuntimeIOV1.capture_task_camera)
    admitted = inspect.getsource(IsaacSimNativeRuntimeIOV1._capture_observer_admitted)
    bind = inspect.getsource(IsaacSimNativeRuntimeIOV1.bind_task_camera)
    stage_prep = inspect.getsource(IsaacSimNativeRuntimeIOV1._prepare_task_rgb_render_stage)

    assert 'use_observer_sensor' not in capture + admitted
    assert 'RtxCamera(path, tick_rate=0.0, reset_xform_op_properties=False)' in admitted
    assert 'sensor = self._task_camera_sensor' in admitted
    assert "'/GeoChoraObserver_'" in admitted
    assert 'rep.orchestrator.step(rt_subframes=1, pause_timeline=True' in admitted
    assert 'delta_time=0.0, wait_for_render=True' in admitted
    assert 'self._prepare_task_rgb_render_stage()' in bind
    assert 'SetEndTimeCode(end_time_code)' in stage_prep
    assert 'UsdLux.DomeLight.Define' in stage_prep
    assert "'source_bytes_modified': False" in stage_prep
    assert "'stage_saved': False" in stage_prep
    assert "render_once('task sensor warmup', allow_unready=True)" in admitted
    assert "operation='task sensor initialization'" in admitted
    assert "'task_renderer_stage_preparation'" in admitted
    assert 'frame_is_fresh' in admitted
    assert 'and timeline_matches_provider' not in admitted
    assert '_align_task_render_timeline' not in admitted
    assert '_prepare_task_rgb_viewport' not in admitted
    assert 'RenderingManager' not in admitted


def test_task_rgb_request_selects_camera_capable_existing_isaac_app_owner():
    from task_env.runtime.sessions.isaac_native_io import (
        F06_ISAAC_APP_LAUNCH_PROFILE_V1,
        V211_ISAAC_RENDER_APP_LAUNCH_PROFILE_V1,
        _isaac_app_launch_profile_id,
    )

    assert _isaac_app_launch_profile_id(
        f06_pickcube=True, observer_render_request=None,
        task_render_requested=False,
    ) == F06_ISAAC_APP_LAUNCH_PROFILE_V1
    assert _isaac_app_launch_profile_id(
        f06_pickcube=True, observer_render_request=None,
        task_render_requested=True,
    ) == V211_ISAAC_RENDER_APP_LAUNCH_PROFILE_V1
    assert _isaac_app_launch_profile_id(
        f06_pickcube=True, observer_render_request=object(),
        task_render_requested=False,
    ) == V211_ISAAC_RENDER_APP_LAUNCH_PROFILE_V1

    import inspect
    from task_env.runtime.sessions import selected_materialization
    source = inspect.getsource(selected_materialization)
    assert "_component_task_rgb" in source
    assert "task_render_requested=bool(" in source


def test_task_rgb_state_projection_preserves_controller_publication(monkeypatch):
    from task_env import artifacts

    class Publication:
        def __init__(self, boundary):
            self.view = SimpleNamespace(
                boundary=boundary,
                sample_clock=SimpleNamespace(simulation_time_s=0.0),
                validate_against_scene=lambda _scene: None,
                validate_requirements=lambda _requirements: None,
            )
            self.lifetime = SimpleNamespace(may_be_retained=True)

    monkeypatch.setattr(artifacts, 'CanonicalStatePublicationV1', Publication)
    env, source = _env('isaacsim')
    scene = source.scene_definition
    boundary = SimpleNamespace(control_step=0)
    publication = Publication(boundary)
    env.artifact.timebase = SimpleNamespace(
        control_dt=0.01, physics_dt=0.002, control_substeps=5,
    )
    env.session = SimpleNamespace(
        state_boundary_identity=lambda: boundary,
        snapshot_v1=lambda **_kwargs: publication,
    )
    env.state = SimpleNamespace(control_step=0, simulation_time=0.0)
    env._task_rgb_state_binding = (
        source, env.artifact.identity_hash, scene, {}, {}, object(), None,
    )
    controller_publication = object()
    env.typed_state = controller_publication

    assert env._publish_task_rgb_typed_state(env.state) is publication
    assert env._task_rgb_typed_state is publication
    assert env.typed_state is controller_publication

    with pytest.raises(ValueError, match='stale or differs from Runtime readback'):
        env._publish_task_rgb_typed_state(
            SimpleNamespace(control_step=1, simulation_time=0.0),
        )
    assert env.typed_state is controller_publication
    assert env._task_rgb_typed_state is None


def test_observation_captures_the_camera_projection_not_controller_state():
    import numpy as np

    env = object.__new__(SelectedReferenceEnv)
    env.mixed_control_profile = False
    env.binding = SimpleNamespace(
        observation_projection=lambda _env, state: ({'state': state}, {}, 'evaluation'),
    )
    env._task_rgb_config = (object(), 'isaacsim')
    camera_view = object()
    camera_publication = SimpleNamespace(view=camera_view)
    env._publish_task_rgb_typed_state = lambda _state: camera_publication
    env.typed_state = object()
    frame = np.zeros((2, 2, 3), dtype=np.float32)
    captured = []
    env._task_rgb_consumer = SimpleNamespace(
        capture=lambda state: captured.append(state) or (frame, {'capture': 'receipt'}),
    )
    env._selected_execution_context = lambda: (None, None)

    observation, info, evaluation = env.observation(object())

    assert captured == [camera_view]
    assert observation['task_rgb'] is frame
    assert info['task_rgb_v1'] == {'capture': 'receipt'}
    assert evaluation == 'evaluation'


def test_selected_reference_schema_describes_declared_nested_space_and_task_rgb():
    from collections import OrderedDict
    import numpy as np
    from task_env.environment.gym_compat import Box, Dict
    from task_env.observations.selected_reference import selected_reference_observation_schema

    spaces = Dict(OrderedDict((
        ('state', Dict(OrderedDict((
            ('ee_pose', Box(-np.inf, np.inf, (7,), dtype=np.float32)),
            ('boundary_identity_sha256', Box(0, 255, (32,), dtype=np.uint8)),
        )))),
        ('privileged_state', Dict({'cube_v1_body_pose': Box(-np.inf, np.inf, (1, 7), dtype=np.float32)})),
        ('task_rgb', Box(0., 1., (240, 320, 3), dtype=np.float32)),
    )))
    observation = {
        'state': {'ee_pose': np.zeros(7, np.float32),
                  'boundary_identity_sha256': np.zeros(32, np.uint8)},
        'privileged_state': {'cube_v1_body_pose': np.zeros((1, 7), np.float32)},
    }
    schema = selected_reference_observation_schema(
        SimpleNamespace(observation_space=spaces, _task_rgb_config=(object(), 'mujoco')),
        observation,
    )

    assert schema.groups == ('state', 'privileged_state', 'task_rgb')
    assert schema.leaf_field_names == (
        'state.ee_pose', 'state.boundary_identity_sha256',
        'privileged_state.cube_v1_body_pose', 'task_rgb',
    )
    schema.validate({**observation, 'task_rgb': np.zeros((240, 320, 3), np.float32)})
