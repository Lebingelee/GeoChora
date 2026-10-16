"""Provider-free S4 retirement and retained-contract regression tests."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest


def test_static_template_configuration_fails_with_migration_guidance():
    from task_env.environment.config import RuntimeConfig

    assert RuntimeConfig().batch_physics_layout == "merged_scene"
    with pytest.raises(ValueError, match="static_template.*retired.*merged_scene"):
        RuntimeConfig(batch_physics_layout="static_template")
    with pytest.raises(ValueError, match="static_template.*retired"):
        RuntimeConfig(static_template={"profile": "rigid_batch_v1"})

    from task_env.environment.configuration import resolve_task_env_config
    from task_env.registry import ENV_REGISTRY

    importlib.import_module("task_env.tasks")
    pendulum = ENV_REGISTRY.get("pendulum-v1")
    with pytest.raises(ValueError, match="batch_physics_layout='static_template' is retired"):
        resolve_task_env_config(
            pendulum,
            {"runtime": {"batch_physics_layout": "static_template"}},
        )
    with pytest.raises(ValueError, match="runtime.static_template is retired"):
        resolve_task_env_config(
            pendulum,
            {"runtime": {"static_template": {"profile": "rigid_batch_v1"}}},
        )


def test_retired_layout_fails_before_runtime_provider_import():
    from task_env.runtime.factory import make_batch_runtime

    config = SimpleNamespace(
        runtime=SimpleNamespace(batch_physics_layout="static_template")
    )
    with pytest.raises(ValueError, match="static_template.*retired.*No runtime substitution"):
        make_batch_runtime(
            compiled_scene=object(),
            resolved_config=config,
            num_envs=2,
            backend="cpu",
        )


def test_merged_scene_remains_the_only_factory_route(monkeypatch):
    from task_env.environment.config import RuntimeConfig
    from task_env.runtime import factory
    from task_env.runtime.providers import merged_scene

    calls = {}
    sentinel = object()

    def build(cls, **kwargs):
        calls.update(kwargs)
        return sentinel

    monkeypatch.setattr(
        merged_scene.SceneBatchRuntime,
        "from_compiled_scene",
        classmethod(build),
    )
    config = SimpleNamespace(runtime=RuntimeConfig())
    result = factory.make_batch_runtime(
        compiled_scene="fixture-scene",
        resolved_config=config,
        num_envs=3,
        backend="cpu",
    )
    assert result is sentinel
    assert calls == {
        "compiled_scene": "fixture-scene",
        "config": config,
        "num_envs": 3,
        "backend": "cpu",
    }


def test_retired_static_modules_and_public_exports_are_absent():
    modules = (
        "task_env.runtime.providers.static",
        "task_env.runtime.static_capabilities",
        "task_env.runtime.static_execution",
        "task_env.runtime.static_provider",
        "task_env.runtime.static_template",
        "task_env.runtime.static_template_fused",
        "task_env.runtime.static_template_model",
        "task_env.runtime.static_template_physics",
        "task_env.runtime.static_template_reference",
        "task_env.runtime.static_template_rigid_batch",
        "task_env.runtime.static_template_taichi",
        "task_env.runtime.static_workspace",
        "task_env.diagnostics.runtime.stage_a_runtime_profile",
        "task_env.diagnostics.runtime.stage18_bridge_benchmark",
        "task_env.diagnostics.runtime.stage_g_contact_precision_gate",
    )
    for name in modules:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(name)

    import task_env.environment as environment
    import task_env.runtime as runtime

    assert not hasattr(environment, "StaticTemplateRuntimeConfig")
    assert not hasattr(environment, "StaticTemplateContactConfig")
    assert not hasattr(runtime, "StaticTemplateBatchRuntime")
    assert not hasattr(runtime, "StaticTemplateRigidBatch")


def test_static_cli_routes_fail_and_merged_scene_options_remain():
    from task_env.script.rl.pendulum_ppo import parse_args as parse_pendulum_args

    assert parse_pendulum_args([]).batch_physics_layout == "merged_scene"
    with pytest.raises(SystemExit):
        parse_pendulum_args(
            ["--batch-physics-layout", "static_template"]
        )
    with pytest.raises(SystemExit):
        parse_pendulum_args(
            ["--static-template-profile", "rigid_batch_v1"]
        )

    from task_env.diagnostics.runtime.stage17_performance_profile import main

    with pytest.raises(SystemExit):
        main(["--task-uid", "pendulum-v1", "--layout", "static_template"])


def test_selected_tasks_and_generic_batch_contracts_remain_importable():
    importlib.import_module("task_env.tasks")
    from task_env.registry import ENV_REGISTRY
    from task_env.runtime.contracts import BatchRuntimeProtocol
    from task_env.runtime.device_plan import DeviceFieldPlan
    from task_env.vectorization.contracts import BatchResetSample
    from task_env.vectorization.sb3 import TaskEnvSB3VecAdapter
    from task_env.alg.rsl_rl.adapter import TaskEnvRslVecAdapter

    assert "pick-cube-p16-reference-v1" in ENV_REGISTRY.uids()
    assert "nut-assembly-outcome-reference-v1" in ENV_REGISTRY.uids()
    assert BatchRuntimeProtocol is not None
    assert DeviceFieldPlan is not None
    assert BatchResetSample is not None
    assert TaskEnvSB3VecAdapter is not None
    assert TaskEnvRslVecAdapter is not None


def test_geophys_rigid_batch_adapter_and_unsupported_contact_gate_remain():
    from task_env.environment.types import StageUnavailableError
    from task_env.runtime.geophys_rigid_batch import GeoPhysRigidBatchRuntime as Alias
    from task_env.runtime.providers.geophys.rigid_batch import GeoPhysRigidBatchRuntime

    assert Alias is GeoPhysRigidBatchRuntime
    config = SimpleNamespace(
        runtime=SimpleNamespace(
            integrator="euler",
            enable_ground_contact=True,
            enable_domain_boundary_contact=False,
        )
    )
    scene = SimpleNamespace(scene_model=object())
    with pytest.raises(StageUnavailableError, match="does not support TaskEnv ground contact"):
        GeoPhysRigidBatchRuntime.from_compiled_scene(
            compiled_scene=scene,
            config=config,
            num_envs=1,
            backend="cpu",
        )
