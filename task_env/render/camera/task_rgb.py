"""Construct task RGB consumers at the renderer adapter boundary."""


def selected_observer_route(config, render_mode):
    """Select a source/renderer route independently of the control algorithm."""
    from ...registry import AGENT_REGISTRY
    from ..base.contracts import (OBSERVER_CAPABILITIES, SCALAR_OBSERVER_BACKENDS,
                                  normalize_render_mode)

    mode = normalize_render_mode(render_mode).value
    try:
        robot = AGENT_REGISTRY.get(config.robot_uid)
    except KeyError as error:
        raise ValueError('selected configuration admits state-only execution without observer rendering') from error
    family = getattr(robot, 'observer_source_family', None)
    route = OBSERVER_CAPABILITIES.get((family, config.physics_provider, config.environment.runtime.backend))
    if route is None or mode not in route.modes:
        raise ValueError('no observer renderer for the selected source family and physics route')
    expected = SCALAR_OBSERVER_BACKENDS[config.physics_provider]
    if config.environment.render.backend != expected:
        raise ValueError(f'scalar observer on {config.physics_provider} requires '
                         f'render.backend={expected!r}')
    return route


def create_task_rgb_consumer(*, camera, renderer, provider, backend, provider_seed_getter,
                             artifact, color_space, session_getter,
                             source_getter, binding_getter):
    """Bind the selected renderer without owning the physics RuntimeSession."""
    from ...artifacts import ExecutionSpecV1, RendererSelectionV1
    from ..base.contracts import task_rgb_capability
    from ...observations.capture import BorrowedTaskCameraSessionV1, TaskRgbObservationConsumerV1
    from .api import create_dynamic_camera_session
    from .source import DynamicCameraRenderSourceV2

    capability = task_rgb_capability(provider, backend, renderer)
    if color_space != capability.color_space:
        raise ValueError('task RGB output description differs from its registered renderer')
    selection = RendererSelectionV1('renderer-selection-v1', capability.renderer,
                                    capability.backend, capability.profile, capability.device)
    if capability.ownership == 'borrowed Runtime camera':
        return TaskRgbObservationConsumerV1(
            camera, selection,
            lambda state: BorrowedTaskCameraSessionV1(session_getter(), camera, state),
            color_space=capability.color_space,
        )
    physics_profile = capability.physics_profile

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
                                    provider_seed_getter(), 'best_effort', selection, physics_device='cpu')
        return create_dynamic_camera_session(camera, execution, source=current_source, initial_state=state)

    return TaskRgbObservationConsumerV1(camera, selection, factory, color_space=color_space)


def prepare_task_rgb_adapter(*, camera, renderer, provider, backend, artifact, observer):
    """Admit a registered task-camera route and prepare its native prerequisites."""
    from ..base.contracts import ObserverRenderRequestV1, task_rgb_capability

    capability = task_rgb_capability(provider, backend, renderer)
    if camera.parent_frame != 'world' and not capability.frame_mounts:
        raise ValueError('selected task RGB renderer does not admit frame-mounted cameras')
    if (observer is not None and capability.shared_framebuffer
            and (observer.width, observer.height) != (camera.width, camera.height)):
        raise ValueError('GeoPhys task and observer cameras require the same framebuffer extent')
    color_setup = None
    if renderer == 'isaacsim':
        from ...runtime.sessions.isaac_native_io import configure_isaac_task_rgb_color_defaults
        color_setup = configure_isaac_task_rgb_color_defaults()
    native_request = None
    if renderer == 'geophys':
        native_request = ObserverRenderRequestV1(camera, 'rgb_array', provider, capability.backend)
        native_request.validate(artifact=artifact, physics_provider=provider, physics_backend=backend)
    return capability, color_setup, native_request


def prepare_observer_adapter(*, camera, render_mode, provider, backend, artifact, task_rgb,
                             observer_route=None):
    """Admit observer geometry and return the native renderer's output contract."""
    from ..base.contracts import (OBSERVER_CAPABILITIES, ObserverRenderRequestV1,
                                  normalize_render_mode, task_rgb_capability)

    if camera.task_artifact_hash != artifact.identity_hash:
        raise ValueError('observer camera TaskArtifact linkage mismatch')
    if observer_route is None:
        capability = task_rgb_capability(provider, backend, provider)
    else:
        key = (observer_route.source_family, provider, backend)
        if (OBSERVER_CAPABILITIES.get(key) is not observer_route
                or normalize_render_mode(render_mode).value not in observer_route.modes):
            raise ValueError('observer route differs from its renderer capability')
        capability = observer_route.camera
    if task_rgb is not None:
        task_camera, task_capability = task_rgb
        if camera.camera_id == task_camera.camera_id:
            raise ValueError('task and observer cameras require distinct identities')
        if (task_capability.shared_framebuffer
                and (camera.width, camera.height) != (task_camera.width, task_camera.height)):
            raise ValueError('GeoPhys task and observer cameras require the same framebuffer extent')
    request = None
    if capability.ownership == 'borrowed Runtime camera':
        request = ObserverRenderRequestV1(camera, render_mode, provider, capability.backend)
        request.validate(artifact=artifact, physics_provider=provider, physics_backend=backend)
    return capability, request
