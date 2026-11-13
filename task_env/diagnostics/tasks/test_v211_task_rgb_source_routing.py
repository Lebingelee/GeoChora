"""Provider-free checks for task RGB state vs renderer source ownership."""
from types import SimpleNamespace

import pytest



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
