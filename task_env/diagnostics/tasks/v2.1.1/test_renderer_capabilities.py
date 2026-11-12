"""Renderer route registration and independent task camera failures."""
import builtins
import importlib
import sys
from types import SimpleNamespace

import pytest


def test_capability_query_and_camera_math_do_not_import_native_sdk(monkeypatch):
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.split('.')[0] in {'taichi', 'isaacsim', 'omni', 'carb'}:
            raise AssertionError('unexpected SDK import: ' + name)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    from task_env.render.base.contracts import TASK_RGB_PAIRINGS, task_rgb_capability
    assert len(TASK_RGB_PAIRINGS) == 4
    for provider, backend, renderer in TASK_RGB_PAIRINGS:
        cap = task_rgb_capability(provider, backend, renderer)
        assert cap.renderer == renderer and cap.profile and cap.color_space
    with pytest.raises(ValueError, match='unsupported'):
        task_rgb_capability('mujoco', 'cuda', 'isaacsim')
    sys.modules.pop('task_env.render.tools.camera', None)
    camera = importlib.import_module('task_env.render.tools.camera')
    control = camera.InteractiveCameraController(position=(1, 0, 0), look_at=(0, 0, 0),
                                                   pose_sink=lambda *_: None)
    assert control.position == (1.0, 0.0, 0.0)


@pytest.mark.parametrize(('robot', 'profile', 'provider', 'backend', 'mode', 'parameters'), [
    ('pendulum-v1', 'direct_joint_effort_v1', 'geophys', 'cpu', 'rgb_array', '{}'),
    ('two-wheel-balance-v1', 'direct_joint_effort_v1', 'mujoco', 'cpu', 'human', '{}'),
    ('panda-v1', 'panda-joint-effort-reference-v1', 'geophys', 'cpu', 'rgb_array', '{}'),
    ('panda-v1', 'panda-joint-effort-reference-v1', 'mujoco', 'cpu', 'rgb_array', '{"reset_selection":true}'),
    ('panda-v1', 'panda-joint-effort-reference-v1', 'isaacsim', 'cuda', 'rgb_array', '{}'),
])
def test_observer_route_is_consumed_by_camera_factory(robot, profile, provider, backend, mode, parameters):
    import task_env.tasks  # registers Robot declarations without starting a provider
    from task_env.environment.config import CameraSpec
    from task_env.observations.canonical_camera import CameraGeometry
    from task_env.render.base.contracts import TASK_RGB_CAPABILITIES
    from task_env.render.camera.task_rgb import prepare_observer_adapter, selected_observer_route

    config = SimpleNamespace(robot_uid=robot, controller_profile=profile,
        controller_parameters_json=parameters, physics_provider=provider,
        environment=SimpleNamespace(runtime=SimpleNamespace(backend=backend)))
    route = selected_observer_route(config, mode)
    artifact = SimpleNamespace(identity_hash='a' * 64)
    camera = CameraGeometry.from_camera_spec(CameraSpec('observer', width=4, height=3, depth=False),
                                            task_artifact_hash=artifact.identity_hash)
    capability, request = prepare_observer_adapter(camera=camera, render_mode=mode,
        provider=provider, backend=backend, artifact=artifact, task_rgb=None, observer_route=route)
    assert capability is route.camera is TASK_RGB_CAPABILITIES[(provider, backend, provider)]
    assert (request is not None) == (capability.ownership == 'borrowed Runtime camera')


def test_observer_route_rejects_unadmitted_control_and_foreign_descriptor():
    from dataclasses import replace
    import task_env.tasks
    from task_env.environment.config import CameraSpec
    from task_env.observations.canonical_camera import CameraGeometry
    from task_env.render.camera.task_rgb import prepare_observer_adapter, selected_observer_route

    config = SimpleNamespace(robot_uid='panda-v1', controller_profile='r3_continuous_v1',
        controller_parameters_json='{}', physics_provider='isaacsim',
        environment=SimpleNamespace(runtime=SimpleNamespace(backend='cuda')))
    with pytest.raises(ValueError, match='state-only'):
        selected_observer_route(config, 'rgb_array')
    config.controller_profile = 'panda-direct-effort-v1'
    route = selected_observer_route(config, 'rgb_array')
    artifact = SimpleNamespace(identity_hash='a' * 64)
    camera = CameraGeometry.from_camera_spec(CameraSpec('observer', width=4, height=3, depth=False),
                                            task_artifact_hash=artifact.identity_hash)
    with pytest.raises(ValueError, match='differs from its renderer capability'):
        prepare_observer_adapter(camera=camera, render_mode='rgb_array', provider='isaacsim',
            backend='cuda', artifact=artifact, task_rgb=None, observer_route=replace(route))


def _isaac_camera_io():
    from task_env.runtime.sessions.isaac_native_io import IsaacSimNativeRuntimeIOV1
    io = object.__new__(IsaacSimNativeRuntimeIOV1)
    camera = object()
    io._closed = False
    io._observer_faulted = False
    io._task_camera_faulted = False
    io._task_render_requested = True
    io._observer_render_request = None
    io._task_camera_geometry = camera
    io._task_camera_path = '/task'
    io.task_camera_binding = lambda state: {'boundary': state}
    return io, camera


def test_headless_isaac_task_capture_does_not_need_observer():
    io, camera = _isaac_camera_io()
    io._observer_faulted = True
    io._capture_observer_admitted = lambda *args, **kwargs: ('frame', kwargs['task'])
    assert io.capture_task_camera(camera, 'boundary') == ('frame', True)


def test_isaac_camera_fault_is_local_and_shared_clock_fault_blocks_both():
    io, camera = _isaac_camera_io()
    calls = []
    def fail(*args, **kwargs):
        raise RuntimeError('sensor failed')
    io._capture_observer_admitted = fail
    io._close_task_camera_sensor = lambda: calls.append('task')
    io._close_observer = lambda: calls.append('observer')
    with pytest.raises(RuntimeError, match='sensor failed'):
        io.capture_task_camera(camera, 'boundary')
    assert io._task_camera_faulted and not io._observer_faulted and calls == ['task']
    io._task_camera_faulted = False
    io._observer_runtime_invalid = True
    with pytest.raises(RuntimeError, match='unavailable or faulted'):
        io.capture_task_camera(camera, 'boundary')
    io._observer_render_request = SimpleNamespace()
    with pytest.raises(RuntimeError, match='unavailable or faulted'):
        io.capture_observer(camera, 'boundary')


def test_task_rgb_schema_preserves_simple_task_semantics():
    import numpy as np
    from collections import OrderedDict
    from task_env.environment.gym_compat import Box, Dict
    from task_env.environment.types import ObservationFieldSpec, ObservationSchema
    from task_env.observations.selected_reference import selected_reference_observation_schema

    base = ObservationSchema('simple-v1', (ObservationFieldSpec(
        'state.angle', (1,), 'float32', 'measured angle', 'rad', 'joint'),), groups=('state',))
    env = SimpleNamespace(observation_space=Dict(OrderedDict((
        ('state', Dict(OrderedDict((('angle', Box(-1, 1, (1,), dtype=np.float32)),)))),
        ('task_rgb', Box(0, 1, (2, 3, 3), dtype=np.float32)),
    ))), _task_rgb_config=(object(), 'isaacsim'))
    obs = {'state': {'angle': np.zeros(1, dtype=np.float32)}}
    combined = selected_reference_observation_schema(env, obs, base_schema=base)
    assert combined.fields[0] == base.fields[0]
    assert combined.fields[1].name == 'task_rgb'
    combined.validate({**obs, 'task_rgb': np.zeros((2, 3, 3), dtype=np.float32)})
    bad = ObservationSchema('bad-v1', (ObservationFieldSpec('state.angle', (2,), 'float32'),),
                            groups=('state',))
    with pytest.raises(ValueError, match='differs from declared space'):
        selected_reference_observation_schema(env, obs, base_schema=bad)


@pytest.mark.parametrize(('provider', 'backend', 'renderer'), [
    ('mujoco', 'cpu', 'mujoco'), ('geophys', 'cpu', 'mujoco'),
    ('geophys', 'cpu', 'geophys'), ('isaacsim', 'cuda', 'isaacsim'),
])
def test_task_consumer_uses_the_registered_capability(provider, backend, renderer):
    from task_env.render.base.contracts import task_rgb_capability
    from task_env.render.camera.task_rgb import create_task_rgb_consumer

    from task_env.environment.config import CameraSpec
    from task_env.observations.canonical_camera import CameraGeometry
    camera = CameraGeometry.from_camera_spec(CameraSpec('task', width=4, height=3, depth=False),
                                            task_artifact_hash='a' * 64)
    cap = task_rgb_capability(provider, backend, renderer)
    consumer = create_task_rgb_consumer(camera=camera, renderer=renderer, provider=provider,
        backend=backend, provider_seed_getter=lambda: 1, artifact=object(),
        color_space=cap.color_space, session_getter=lambda: None,
        source_getter=lambda: None, binding_getter=lambda: None)
    assert consumer.renderer.provider == cap.renderer
    assert consumer.renderer.backend == cap.backend and consumer.renderer.profile == cap.profile
    with pytest.raises(ValueError, match='output description'):
        create_task_rgb_consumer(camera=object(), renderer=renderer, provider=provider,
            backend=backend, provider_seed_getter=lambda: 1, artifact=object(),
            color_space='incorrect', session_getter=lambda: None,
            source_getter=lambda: None, binding_getter=lambda: None)


def test_isaac_headless_admission_never_forges_observer_request(monkeypatch):
    from task_env.runtime.sessions import isaac_native_io
    from task_env.render.camera.task_rgb import prepare_task_rgb_adapter
    monkeypatch.setattr(isaac_native_io, 'configure_isaac_task_rgb_color_defaults', lambda: {'ok': True})
    cap, setup, request = prepare_task_rgb_adapter(camera=object(), renderer='isaacsim',
        provider='isaacsim', backend='cuda', artifact=object(), observer=None)
    assert cap.backend == 'rtx' and setup == {'ok': True} and request is None


def test_failed_task_sensor_detach_keeps_owner_and_receipt_incomplete():
    io, _ = _isaac_camera_io()
    class Sensor:
        def detach_annotators(self, _name):
            raise RuntimeError('detach failed')
    sensor = io._task_camera_sensor = Sensor()
    with pytest.raises(RuntimeError, match='detach failed'):
        io._close_task_camera_sensor()
    assert io._task_camera_sensor is sensor
    io._closed = True
    io._runtime_owner_closed = False
    io._lease = SimpleNamespace(closed=False)
    io._app_owner = SimpleNamespace(close_receipt=lambda: {'close_completed': False})
    receipt = io.close_receipt()
    assert receipt['native_io_close_requested'] and not receipt['native_io_closed']


def test_observer_receives_own_renderer_view_for_physical_v2(monkeypatch):
    from task_env.environment.reference_env import SelectedReferenceEnv
    env = object.__new__(SelectedReferenceEnv)
    env._published_position_typed_state = SimpleNamespace(view=object())
    env._execution_fault = None
    env._task_rgb_state_binding = object()
    env.state = object()
    expected = SimpleNamespace(view=object())
    env._publish_task_rgb_typed_state = lambda state: expected
    env.provider = 'geophys'
    env._selected_observer_camera = object()
    captured = []
    env.session = SimpleNamespace(capture_observer=lambda camera, view: captured.append(view))
    env._capture_selected_observer()
    assert captured == [expected.view]


def test_ui_provider_consumes_only_public_source_and_frame_methods(monkeypatch):
    import numpy as np
    from task_env.render.providers.single import TaskEnvRenderProvider

    frame = np.arange(18, dtype=np.float32).reshape(2, 3, 3) / 18
    pose = ((1., 2., 3.), (0., 0., 0.), (0., 0., 1.))
    camera = SimpleNamespace(position=pose[0], look_at=pose[1], up=pose[2])
    class Source:
        def read_render_scene(self, *, backend):
            assert backend == 'rasterizer'
            return SimpleNamespace(camera=camera)
    class Visualizer:
        def set_camera_pose(self, *value):
            self.pose = value
        def read_frame(self, *, width, height, synchronized):
            assert (width, height, synchronized) == (3, 2, True)
            return frame
    class Canvas:
        def set_image(self, pixels):
            self.pixels = pixels.copy()
    class Window:
        running = True
        def poll_events(self): pass
        def is_pressed(self, _key): return False
        def show(self): self.shown = True
    visualizer, canvas, window = Visualizer(), Canvas(), Window()
    provider = TaskEnvRenderProvider(render_source=Source(),
        config=SimpleNamespace(width=3, height=2, backend='rasterizer'))
    provider._render_processor = SimpleNamespace(request=SimpleNamespace(backend='rasterizer'),
                                                  build_visualizer=lambda _: visualizer)
    provider._window, provider._canvas = window, canvas
    monkeypatch.setitem(sys.modules, 'taichi', SimpleNamespace(ui=SimpleNamespace(
        RMB='RMB', LMB='LMB', MMB='MMB', CTRL='Control', SHIFT='Shift', ALT='Alt')))
    np.testing.assert_array_equal(provider._render_rgb(), frame)
    assert visualizer.pose == pose
    provider._render_human()
    np.testing.assert_array_equal(canvas.pixels, frame[::-1].transpose(1, 0, 2))
    assert window.shown


def test_public_camera_controller_retains_keyboard_and_middle_drag():
    import numpy as np
    from task_env.render.tools.camera import InteractiveCameraController
    poses = []
    controller = InteractiveCameraController(position=(0., 0., 0.), look_at=(1., 0., 0.),
                                              pose_sink=lambda *pose: poses.append(pose))
    class Window:
        keys = {'w'}
        cursor = (.5, .5)
        def is_pressed(self, key): return key in self.keys
        def get_cursor_pos(self): return self.cursor
        def get_window_shape(self): return (640, 480)
    window = Window()
    assert controller.update(window, extended=True, delta_seconds=.1, move_speed_per_second=1.)
    assert controller.position[0] == pytest.approx(.1)
    window.keys = {'MMB'}
    assert not controller.update(window, extended=True, delta_seconds=.1)
    before = np.asarray(controller.position)
    window.cursor = (.6, .55)
    assert controller.update(window, extended=True, delta_seconds=.1)
    assert not np.allclose(controller.position, before)
    assert len(poses) == 2
