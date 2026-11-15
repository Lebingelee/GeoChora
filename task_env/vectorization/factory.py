"""Framework parallel assembly from the three TaskEnv extension points."""

from __future__ import annotations

from dataclasses import replace
from collections.abc import Mapping
from typing import Any

import gymnasium as gym
import numpy as np

from ..assembly import compile_task_scene
from ..environment.configuration import resolve_task_env_config
from ..environment.metadata import gym_metadata_dict
from ..environment.task_definition import TaskDefinitionBase
from ..environment.types import StageUnavailableError
from ..registry import ENV_REGISTRY
from ..runtime import make_batch_runtime
from ..runtime.device_plan import admit_runtime_port
from .task_definition import BatchTaskLifecycleAdapter


def make_framework_parallel_spec(
    *,
    uid: str,
    num_env: int,
    env_config: Mapping[str, Any] | None,
    backend: str,
    execution: str = "local",
    transfer_mode: str = "device",
    **env_kwargs: Any,
) -> BatchTaskLifecycleAdapter:
    """Assemble a parallel task through the same three env factories as single."""

    environment_type = ENV_REGISTRY.get(uid)
    if getattr(environment_type, 'uses_selected_public_config', False):
        raise StageUnavailableError(
            f"task {uid!r} has no formal batch adapter; use scalar make_env"
        )
    values = dict(env_config or {})
    base_seed = values.pop("base_seed", env_kwargs.pop("base_seed", 73))
    if env_kwargs:
        unknown = ", ".join(sorted(str(key) for key in env_kwargs))
        raise TypeError(f"unknown parallel TaskEnv kwargs: {unknown}")
    config = resolve_task_env_config(environment_type, values or None)
    config = replace(
        config,
        runtime=replace(config.runtime, backend=str(backend)),
    )
    env = environment_type(config=config, build_runtime=False)

    scene_composer = env.create_scene_composer()
    compiled_scene = compile_task_scene(
        composition=env.composition_spec,
        scene=env.scene,
        agents=env.agents,
        objects=env.objects,
        scene_composer=scene_composer,
    )
    task_definition = env.create_task_definition(compiled_scene)
    if not getattr(task_definition, "uses_unified_state_view", False):
        raise StageUnavailableError(
            f"task {uid!r} task definition does not implement the unified scalar/batch state contract"
        )
    if not callable(getattr(task_definition, "reset", None)):
        raise StageUnavailableError(
            f"task {uid!r} task definition has no unified reset semantic"
        )
    if not callable(getattr(task_definition, "evaluate", None)):
        raise StageUnavailableError(
            f"task {uid!r} task definition has no unified step semantic"
        )
    if (
        not callable(getattr(task_definition, "build_observation", None))
        or type(task_definition).build_observation is TaskDefinitionBase.build_observation
    ):
        raise StageUnavailableError(
            f"task {uid!r} has no unified scalar/batch observation definition"
        )
    action_adapter_factory = getattr(task_definition, "create_action_adapter", None)
    action_adapter = (
        action_adapter_factory(compiled_scene)
        if callable(action_adapter_factory)
        else env.create_action_adapter(compiled_scene)
    )
    if compiled_scene.references.agents and action_adapter is None:
        raise StageUnavailableError(
            f"task {uid!r} declares agent references but provides no native "
            "batch action adapter capability"
        )
    if action_adapter is None:
        single_action_space = gym.spaces.Box(
            low=-1.0,
            high=1.0,
            shape=(0,),
            dtype=np.float32,
        )
    else:
        single_action_space = action_adapter.action_space
        if not callable(getattr(action_adapter, "convert_batch", None)):
            raise StageUnavailableError(
                f"action adapter {type(action_adapter).__name__!r} has no batch-native conversion"
            )

    observation_builder_factory = getattr(
        task_definition,
        "create_observation_builder",
        None,
    )
    observation_builder = (
        observation_builder_factory(
            compiled_scene,
            observation_config=config.observation,
            render_config=config.render,
        )
        if callable(observation_builder_factory)
        else env.create_observation_builder(compiled_scene)
    )
    single_observation_space = observation_builder.observation_space
    external_action = getattr(action_adapter, "action_contract", None)
    if external_action is not None:
        env._env_metadata = replace(env._env_metadata, external_action=external_action)
    metadata = gym_metadata_dict(
        env._env_metadata,
        observation_schema=getattr(observation_builder, "schema", None),
        stage="stage4_gym_contract",
    )
    metadata.update(
        {
            "batch_schema_version": "task-env-homogeneous-vector-v2",
            "num_envs": int(num_env),
            "backend": str(backend),
            "execution": str(execution),
            "transfer_mode": str(transfer_mode),
            "horizon": int(config.episode.horizon),
        }
    )

    runtime = make_batch_runtime(
        compiled_scene=compiled_scene,
        resolved_config=config,
        num_envs=int(num_env),
        backend=str(backend),
    )
    runtime_summary = runtime.resource_summary()
    admission = admit_runtime_port(
        runtime=runtime,
        summary=runtime_summary,
        execution=str(execution),
        requested_transfer_mode=str(transfer_mode),
    )
    if not admission.host_available:
        raise StageUnavailableError(
            "batch runtime does not satisfy the host Runtime Port: "
            + ", ".join(admission.host_reasons)
        )
    effective_transfer_mode = admission.transfer_mode
    metadata.update(
        {
            "batch_physics_layout": config.runtime.batch_physics_layout,
            "static_template": {
                "profile": config.runtime.static_template.profile,
                "kinematics_backend": config.runtime.static_template.kinematics_backend,
                "contact_precision": config.runtime.static_template.contact_precision,
                "cuda_graph": config.runtime.static_template.cuda_graph,
                "contact": {
                    "response_backend": config.runtime.static_template.contact.response_backend,
                    "fixed_topology_child_schur": config.runtime.static_template.contact.fixed_topology_child_schur,
                    "root_factor_6x6": config.runtime.static_template.contact.root_factor_6x6,
                },
            },
            "runtime_resource_summary": runtime_summary,
            "transfer_mode": effective_transfer_mode,
        }
    )
    reset_sampler = env.create_reset_sampler()
    configure_reset_sampler = getattr(reset_sampler, "configure", None)
    if callable(configure_reset_sampler):
        configure_reset_sampler(
            runtime_config=config.runtime,
            num_envs=int(num_env),
            horizon=int(config.episode.horizon),
        )
    adapter = BatchTaskLifecycleAdapter(
        uid=str(uid),
        num_envs=int(num_env),
        backend=str(backend),
        base_seed=int(base_seed),
        runtime=runtime,
        reset_sampler=reset_sampler,
        compiled_scene=compiled_scene,
        initial_state=compiled_scene.initial_state,
        task_definition=task_definition,
        action_adapter=action_adapter,
        single_action_space=single_action_space,
        single_observation_space=single_observation_space,
        metadata=metadata,
        horizon=int(config.episode.horizon),
        ignore_done=bool(config.episode.ignore_done),
    )
    adapter.resolved_config.update(
        {
            "runtime": {
                "batch_physics_layout": config.runtime.batch_physics_layout,
                "static_template": {
                    "profile": config.runtime.static_template.profile,
                    "kinematics_backend": config.runtime.static_template.kinematics_backend,
                    "contact_precision": config.runtime.static_template.contact_precision,
                    "cuda_graph": config.runtime.static_template.cuda_graph,
                    "contact": {
                        "response_backend": config.runtime.static_template.contact.response_backend,
                        "fixed_topology_child_schur": config.runtime.static_template.contact.fixed_topology_child_schur,
                        "root_factor_6x6": config.runtime.static_template.contact.root_factor_6x6,
                    },
                },
                "physics_dt": config.runtime.physics_dt,
                "control_substeps": config.runtime.control_substeps,
                "enable_ground_contact": config.runtime.enable_ground_contact,
                "enable_domain_boundary_contact": config.runtime.enable_domain_boundary_contact,
                "world_randomization": dict(config.runtime.world_randomization),
                "backend": str(backend),
            },
            "render": {
                "backend": config.render.backend,
                "width": int(config.render.width),
                "height": int(config.render.height),
                "parallel": {
                    "num": config.render.parallel.num,
                    "columns": int(config.render.parallel.columns),
                    "cell_width": float(config.render.parallel.cell_width),
                    "cell_depth": float(config.render.parallel.cell_depth),
                    "padding": float(config.render.parallel.padding),
                },
                "training": {
                    "every": int(config.render.training.every),
                },
            },
            "resource_summary": runtime.resource_summary(),
        }
    )
    # Renderer implementations are loaded only after physics provider
    # construction.  In particular, parallel render sources import Taichi;
    # static runtime construction must first complete its audited Triton
    # preload.
    from ..render.providers.parallel import ParallelRenderProvider
    from ..render.providers.parallel_source import BatchParallelRenderSource

    # P2-S18b: the provider owns one renderer proxy plus a bounded snapshot
    # ring.  It never becomes a physics owner and its selected-world copies
    # stay on device for CUDA runtimes.
    adapter.parallel_render_provider = ParallelRenderProvider(
        num_envs=int(num_env),
        render_source=BatchParallelRenderSource(
            runtime=runtime,
            compiled_scene=compiled_scene,
            layout_kind=config.runtime.batch_physics_layout,
            render_config=config.render,
        ),
        width=int(config.render.width),
        height=int(config.render.height),
    )
    return adapter


def make_selected_device_spec(*, uid, num_env, env_config, backend, worker_directory=None,
                              render_mode=None):
    """Use the selected task's shared source and Controller to construct a device batch."""
    from dataclasses import asdict
    from ..runtime.sessions.source import close_source_and_task_resources
    from ..runtime.factory import load_device_provider

    if backend != 'cuda':
        raise ValueError('device batch requires backend=cuda')
    if render_mode not in (None, 'human', 'rgb_array'):
        raise ValueError('device batch render_mode must be human, rgb_array or None')
    environment_type = ENV_REGISTRY.get(uid)
    config = resolve_task_env_config(environment_type, env_config, execution_scope='device_batch')
    binding = environment_type._build_selected_binding(config)
    built = None
    runtime = None
    try:
        seed = config.environment.episode.seed
        seed = 73 if seed is None else seed
        built = binding.build_for_request(config.physics_provider, config.environment.runtime.backend,
                                          seed, config.environment.episode.horizon)
        binding = binding.bind_compiled_control(built)
        if not callable(binding.task_definition_factory):
            raise StageUnavailableError('task does not declare a device TaskDefinition')
        definition = binding.task_definition_factory(built['artifact'])
        required = ('device_reset_spec', 'sample_device_reset', 'reset_device', 'build_device_observation',
                    'evaluate_device', 'device_observation_space')
        if any(not callable(getattr(definition, name, None)) for name in required):
            raise StageUnavailableError('task does not declare the required device semantics')
        controller = built['controller']
        if not callable(getattr(controller, 'convert_device_batch', None)):
            raise StageUnavailableError('compiled Controller has no device action capability')
        device_action_space = getattr(controller, 'device_action_space', None)
        action_space = (device_action_space() if callable(device_action_space)
                        else binding.action_space_factory())
        session_type = load_device_provider(config.physics_provider)
        runtime = session_type(built, num_envs=num_env, device=config.physics_device,
            interpreter=config.execution_spec_v2.interpreter, runtime_config=config.environment.runtime,
            contact_mode=config.geophys_contact_mode,
            working_directory=worker_directory)
        from ..robots.batch_view import RobotBatchView

        robot_view = RobotBatchView(robot=binding.robot, execution=built['physical_execution'], runtime=runtime)
        bind_device = getattr(definition, 'bind_device', None)
        if callable(bind_device):
            definition = bind_device(artifact=built['artifact'], robot_view=robot_view,
                                     source=built['source'], runtime=runtime,
                                     terminate_on_success=binding.physical_terminate_on_success)
        schema_builder = getattr(definition, 'device_observation_schema', None)
        schema = schema_builder() if callable(schema_builder) else binding.task_observation_schema
        action_schema = dict(binding.action_schema)
        if not action_schema.get('components'):
            component_declaration = getattr(binding.robot, 'device_effort_action_components', None)
            names = (tuple(component_declaration(controller)) if callable(component_declaration)
                     else tuple(getattr(getattr(controller, 'profile', None), 'action_names', ())))
            if names:
                action_schema['components'] = list(names)
        metadata = {'task_uid': uid, 'num_envs': int(num_env), 'backend': backend,
                    'execution': 'device_worker', 'transfer_mode': 'device',
                    'runtime_resource_summary': runtime.resource_summary(),
                    'action_schema': action_schema,
                    'observation_schema': asdict(schema)}
        adapter = BatchTaskLifecycleAdapter(uid=uid, num_envs=num_env, backend=backend,
            base_seed=seed, runtime=runtime, reset_sampler=binding.task_reset_sampler,
            compiled_scene=None, initial_state=None, task_definition=definition,
            action_adapter=controller, single_action_space=action_space,
            single_observation_space=definition.device_observation_space(), metadata=metadata,
            horizon=config.environment.episode.horizon, ignore_done=config.environment.episode.ignore_done,
            source_resources=(built['source'], binding))
        adapter.robot = robot_view
        render_config = config.environment.render
        if render_config.camera_obs or render_mode is not None:
            from ..render.providers.parallel import ParallelRenderLayout, ParallelRenderProvider
            from ..render.rasterizer.device import DeviceBatchRasterSource

            if render_config.camera_obs and render_config.backend != 'rasterizer':
                raise StageUnavailableError('device camera observations require the shared rasterizer')
            cameras = render_config.cameras if render_config.camera_obs else ()
            render_source = DeviceBatchRasterSource(runtime=runtime, source=built['source'], cameras=cameras)
            grid = render_config.parallel
            layout = ParallelRenderLayout(cell_width=grid.cell_width, cell_depth=grid.cell_depth,
                                          columns=grid.columns, padding=grid.padding)
            adapter.parallel_render_provider = ParallelRenderProvider(
                num_envs=num_env, render_source=render_source,
                width=render_config.width, height=render_config.height, layout=layout)
            adapter.parallel_render_provider.set_parallel_render_num(num_env)
            adapter.metadata['render_mode'] = render_mode
            adapter.resolved_config['render'] = asdict(render_config)
            if cameras:
                from ..environment.types import ObservationFieldSpec

                adapter.configure_device_cameras(cameras)
                camera_fields = tuple(ObservationFieldSpec(
                    name=f'cameras.{camera.name}.rgb', shape=(camera.height, camera.width, 3),
                    dtype='uint8', semantic=f'{camera.name} RGB', unit='uint8[0,255]',
                    frame=f'camera:{camera.name}/pixel_grid') for camera in cameras)
                adapter.metadata['observation_schema'] = asdict(replace(
                    schema, fields=(*schema.fields, *camera_fields),
                    groups=(*schema.groups, 'cameras')))
        return adapter
    except BaseException as error:
        if runtime is not None:
            try:
                runtime.close()
            except BaseException as cleanup_error:
                error.add_note(f'device runtime cleanup also failed: {cleanup_error!r}')
        close_source_and_task_resources(None if built is None else built.get('source'), binding, error=error)
        raise


__all__ = ["make_framework_parallel_spec", "make_selected_device_spec"]
