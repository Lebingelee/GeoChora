"""Provider-free regressions for selected construction config and identity facts."""

import pytest

from task_env.artifacts.contracts import RendererSelectionV1
from task_env.environment.config import ResolvedEnvConfig
from task_env.environment.configuration import resolve_task_env_config


def _resolver_target(*, class_defaults=None, task_defaults=None):
    class Target:
        uid = "resolver-target-v1"
        uses_selected_public_config = True
        selected_controller_profiles = frozenset()
        selected_parameter_limits = {}
        selected_supports_isaac = False

        @staticmethod
        def selected_default_config(task_config=None):
            return ResolvedEnvConfig()

        @staticmethod
        def selected_default_controller_profile(task_config=None):
            return None

    if class_defaults is not None:
        Target.selected_execution_defaults = class_defaults
    if task_defaults is not None:
        Target.selected_task_configuration = staticmethod(
            lambda: {"execution": task_defaults}
        )
    return Target


def test_selected_execution_defaults_follow_core_class_yaml_and_caller_order():
    core = resolve_task_env_config(_resolver_target(), None)
    assert (core.physics_provider, core.environment.runtime.backend, core.physics_device) == (
        "geophys", "cpu", "cpu",
    )

    task_class = resolve_task_env_config(
        _resolver_target(class_defaults={"physics_provider": "mujoco"}), None,
    )
    assert task_class.physics_provider == "mujoco"

    yaml_default = resolve_task_env_config(
        _resolver_target(
            class_defaults={"physics_provider": "mujoco"},
            task_defaults={"physics_provider": "geophys"},
        ),
        None,
    )
    assert yaml_default.physics_provider == "geophys"

    caller = resolve_task_env_config(
        _resolver_target(
            class_defaults={"physics_provider": "mujoco"},
            task_defaults={"physics_provider": "geophys"},
        ),
        {"execution": {"physics_provider": "mujoco"}},
    )
    assert caller.physics_provider == "mujoco"


def test_selected_execution_is_strict_and_rejects_inherited_device_conflicts():
    target = _resolver_target()
    with pytest.raises(ValueError, match="provider.*conflicts"):
        resolve_task_env_config(
            target,
            {"provider": "mujoco", "execution": {"physics_provider": "geophys"}},
        )
    with pytest.raises(KeyError, match="unsupported selected execution fields"):
        resolve_task_env_config(target, {"execution": {"surprise": True}})
    with pytest.raises(ValueError, match="'geophys'/'cuda'/'cpu'"):
        resolve_task_env_config(target, {"execution": {"physics_backend": "cuda"}})


def test_state_only_renderer_is_resolved_recorded_and_roundtrips():
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    resolved = resolve_task_env_config(PickCubeReferenceEnv, None)
    assert type(resolved.render_default) is RendererSelectionV1
    state_only = {
        "schema_version": "renderer-selection-v1",
        "provider": "none",
        "backend": "cpu",
        "profile": "none",
        "device": None,
    }
    assert resolved.render_default.to_mapping() == state_only
    assert resolve_task_env_config(PickCubeReferenceEnv, resolved) == resolved

    env = PickCubeReferenceEnv.from_resolved_config(resolved)
    assert env.session is None
    assert env._recorded_execution_configuration()["execution"]["render_default"] == state_only


def test_selected_config_rejects_unsupported_renderer_selections():
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    unsupported = RendererSelectionV1(
        "renderer-selection-v1", "mujoco", "cpu", "offscreen", "cpu",
    ).to_mapping()
    with pytest.raises(ValueError, match="state-only renderer|physics-renderer"):
        resolve_task_env_config(
            PickCubeReferenceEnv,
            {"execution": {"physics_provider": "mujoco", "render_default": unsupported}},
        )


@pytest.mark.parametrize("task_module", [
    "task_env.tasks.pick_cube.specialization",
    "task_env.tasks.nut_assembly.specialization",
])
def test_selected_task_yaml_uses_duplicate_key_rejecting_loader(
    task_module, tmp_path, monkeypatch,
):
    import importlib
    from yaml.constructor import ConstructorError

    module = importlib.import_module(task_module)
    path = tmp_path / "duplicate.yaml"
    path.write_text("recipe: {}\nrecipe: {}\nenvironment: {}\n")
    monkeypatch.setattr(module, "CONFIG_PATH", path)
    with pytest.raises(ConstructorError, match="found duplicate key 'recipe'"):
        module._configuration()


def test_two_section_task_yaml_remains_compatible(tmp_path, monkeypatch):
    import yaml

    from task_env.tasks.pick_cube import specialization
    from task_env.tasks.pick_cube.specialization import PickCubeReferenceEnv

    legacy = specialization._configuration()
    legacy.pop("execution")
    path = tmp_path / "legacy.yaml"
    path.write_text(yaml.safe_dump(legacy, sort_keys=False))
    monkeypatch.setattr(specialization, "CONFIG_PATH", path)
    resolved = resolve_task_env_config(PickCubeReferenceEnv, None)
    assert resolved.physics_provider == "geophys"
    assert resolved.render_default.provider == "none"


def test_optional_controller_identity_is_explicit_and_bound_identity_is_preserved():
    from types import SimpleNamespace

    from task_env.assembly.compiler import CompiledReferenceTaskV1
    from task_env.assembly.panda_box import compile_panda_box_task
    from task_env.tasks.pick_cube.specialization import _declaration, _environment_config

    compiled = compile_panda_box_task(_declaration(), config=_environment_config())
    assert compiled.controller is None
    assert compiled.identity_fields()["controller_identity"] is None

    bound = CompiledReferenceTaskV1(
        compiled.artifact, compiled.source, SimpleNamespace(identity="controller-v1"),
    )
    assert bound.identity_fields()["controller_identity"] == "controller-v1"
