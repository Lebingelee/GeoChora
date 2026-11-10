"""Construct task RGB consumers at the renderer adapter boundary."""


def create_task_rgb_consumer(*, camera, renderer, provider, backend, provider_seed,
                             artifact, color_space, session_getter,
                             source_getter, binding_getter):
    """Bind the selected renderer without owning the physics RuntimeSession."""
    from ...artifacts import ExecutionSpecV1, RendererSelectionV1
    from ...observations.capture import BorrowedTaskCameraSessionV1, TaskRgbObservationConsumerV1
    from .api import (D03_PHYSICS_PROFILE, V211_GEOPHYS_MUJOCO_RGB_PROFILE,
                      V211_PHYSICS_PROFILE, V211_RGB_PROFILE,
                      create_dynamic_camera_session)
    from .source import DynamicCameraRenderSourceV2

    if renderer in {'geophys', 'isaacsim'}:
        selection = (RendererSelectionV1('renderer-selection-v1', 'geophys', 'rasterizer',
                                          'v211_geophys_cpu_task_rgb_v1', 'cpu')
                     if renderer == 'geophys' else
                     RendererSelectionV1('renderer-selection-v1', 'isaacsim', 'rtx',
                                         'v211_isaac_rtx_task_rgb_v1', 'cuda:0'))
        return TaskRgbObservationConsumerV1(
            camera, selection,
            lambda state: BorrowedTaskCameraSessionV1(session_getter(), camera, state),
            color_space=color_space,
        )
    if renderer != 'mujoco':
        raise ValueError(f'unsupported task RGB renderer: {renderer!r}')

    is_cross = provider == 'geophys'
    profile = V211_GEOPHYS_MUJOCO_RGB_PROFILE if is_cross else V211_RGB_PROFILE
    physics_profile = D03_PHYSICS_PROFILE if is_cross else V211_PHYSICS_PROFILE
    selection = RendererSelectionV1('renderer-selection-v1', 'mujoco', 'native-opengl', profile, None)

    def factory(state):
        binding = binding_getter()
        source = source_getter()
        if binding[0] is not source or binding[1] != artifact.identity_hash:
            raise ValueError('selected task RGB render source is stale or foreign')
        render_source = binding[-1]
        current_source = DynamicCameraRenderSourceV2.from_runtime_source(
            source, artifact=artifact,
            joint_bindings=binding[3], frame_bindings=binding[4])
        if current_source.identity_hash != render_source.identity_hash:
            raise ValueError('selected task RGB render source changed after reset binding')
        execution = ExecutionSpecV1('execution-spec-v1', provider, backend, physics_profile,
                                    provider_seed, 'best_effort', selection, physics_device='cpu')
        return create_dynamic_camera_session(camera, execution, source=current_source, initial_state=state)

    return TaskRgbObservationConsumerV1(camera, selection, factory, color_space=color_space)
