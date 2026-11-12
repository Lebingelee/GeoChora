"""TaskEnv runtime bootstrap; constructs runtime only on environment setup."""

from __future__ import annotations

from dataclasses import dataclass

from ..environment import ResolvedEnvConfig
from ..assembly import CompiledTaskScene, compile_task_scene
from .boundary import GeoPhysRuntimeBoundary


@dataclass(frozen=True)
class TaskRuntimeBootstrap:
    compiled_scene: CompiledTaskScene
    boundary: GeoPhysRuntimeBoundary
    render_source: object | None = None
    render_options: object | None = None


def bootstrap_task_runtime(
    *,
    config: ResolvedEnvConfig,
    composition,
    scene,
    agents,
    objects,
    scene_composer=None,
    reset_sampler=None,
    create_render_source: bool = False,
) -> TaskRuntimeBootstrap:
    from .provider_bootstrap import init_task_env_backend, materialize_task_scene

    init_task_env_backend(config.runtime.backend)
    compiled = compile_task_scene(
        composition=composition,
        scene=scene,
        agents=agents,
        objects=objects,
        scene_composer=scene_composer,
    )
    runtime = materialize_task_scene(
        compiled, config.runtime,
        create_render_source=bool(create_render_source or config.render.camera_obs),
    )
    resolve_initial_state = getattr(reset_sampler, "resolve_initial_state", None)
    initial_state = (
        resolve_initial_state(
            solver=runtime.solver,
            compiled_scene=compiled,
        )
        if resolve_initial_state is not None
        else compiled.initial_state
    )
    boundary = GeoPhysRuntimeBoundary(
        physics=runtime.solver,
        scheduler=runtime.simulator,
        physics_dt=config.runtime.physics_dt,
        ctrl_range=compiled.scene_model.joint_data.get("actuator_ctrlrange"),
        initial_state=initial_state,
        # A zero-DOF static scene has no task reset sampler or writable
        # articulated placement. Its baseline is the public snapshot; the
        # provider's articulated body-pose reader is unavailable there.
        capture_static_world_children=(
            compiled.scene_model.joint_data.get("n_dof") != 0
            or reset_sampler is not None
        ),
    )
    if config.runtime.prewarm:
        boundary.prewarm()
    return TaskRuntimeBootstrap(
        compiled_scene=compiled,
        boundary=boundary,
        render_source=runtime.render_source,
        render_options=runtime.render_options,
    )


__all__ = ["TaskRuntimeBootstrap", "bootstrap_task_runtime"]
