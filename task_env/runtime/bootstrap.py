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
    from geophys.demo_runtime import assemble_mjcf_articulated_runtime
    from geophys.test_runtime import init_test_backend
    from solvers.rigid import RigidGroundConfig

    init_test_backend(config.runtime.backend)
    compiled = compile_task_scene(
        composition=composition,
        scene=scene,
        agents=agents,
        objects=objects,
        scene_composer=scene_composer,
    )
    solver_kwargs = {
        "dt": config.runtime.physics_dt,
        "gravity": config.runtime.gravity,
        "integrator": config.runtime.integrator,
        "ground": RigidGroundConfig(
            height=-1.0,
            visible=False,
            contact_margin=0.0,
        ),
        "enable_ground_contact": False,
        "enable_domain_boundary_contact": False,
        "broadphase": config.runtime.broadphase,
        "prewarm_kernels": False,
    }
    if config.runtime.rigid_solver_backend is not None:
        solver_kwargs["rigid_solver_backend"] = config.runtime.rigid_solver_backend
    if config.runtime.body_contact_solver_iterations is not None:
        solver_kwargs["body_contact_solver_iterations"] = (
            config.runtime.body_contact_solver_iterations
        )

    runtime = assemble_mjcf_articulated_runtime(
        compiled.imported_scene,
        scene_model=compiled.scene_model,
        apply_mjcf_options=True,
        default_dt=config.runtime.physics_dt,
        default_gravity=config.runtime.gravity,
        default_integrator=config.runtime.integrator,
        solver_kwargs=solver_kwargs,
        create_simulator=True,
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
