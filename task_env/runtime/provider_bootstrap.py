"""GeoPhys provider bootstrap owned by the TaskEnv runtime boundary."""

from __future__ import annotations

from typing import Any


def init_task_env_backend(arch: str = "cpu", **kwargs: Any) -> None:
    """Initialize GeoPhys through its documented process-wide public facade."""
    import os
    from geophys import init_taichi

    # Preserve the TaskEnv backend selection and environment contract that was
    # previously supplied by GeoPhys's test/demo convenience wrapper.
    normalized = str("cuda" if arch is None else arch).strip().lower()
    if normalized not in {"cpu", "cuda", "vulkan", "gpu"}:
        raise ValueError(f"unsupported runtime arch: {arch}")
    os.environ["GEOPHYS_TAICHI_ARCH"] = normalized
    if normalized == "vulkan":
        os.environ.setdefault("GEOPHYS_VULKAN_SPARSE_EXPERIMENTAL", "0")
    init_taichi(arch=normalized, **kwargs)


def materialize_task_scene(compiled, runtime_config, *, create_render_source: bool):
    """Use GeoPhys' public assembly entry with the selected Runtime settings."""
    from simulation import assemble_mjcf_articulated_runtime
    from solvers.rigid import RigidGroundConfig

    solver_kwargs = {
        "dt": runtime_config.physics_dt,
        "gravity": runtime_config.gravity,
        "integrator": runtime_config.integrator,
        "ground": RigidGroundConfig(height=-1.0, visible=False, contact_margin=0.0),
        "enable_ground_contact": False,
        "enable_domain_boundary_contact": False,
        "broadphase": runtime_config.broadphase,
        "prewarm_kernels": False,
    }
    if runtime_config.rigid_solver_backend is not None:
        solver_kwargs["rigid_solver_backend"] = runtime_config.rigid_solver_backend
    if runtime_config.body_contact_solver_iterations is not None:
        solver_kwargs["body_contact_solver_iterations"] = runtime_config.body_contact_solver_iterations
    return assemble_mjcf_articulated_runtime(
        compiled.imported_scene, scene_model=compiled.scene_model,
        apply_mjcf_options=True, default_dt=runtime_config.physics_dt,
        default_gravity=runtime_config.gravity, default_integrator=runtime_config.integrator,
        solver_kwargs=solver_kwargs, create_simulator=True,
        create_render_source=create_render_source,
    )


__all__ = ["init_task_env_backend", "materialize_task_scene"]
