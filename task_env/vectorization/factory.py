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


__all__ = ["make_framework_parallel_spec"]
