"""C01a static execution planning, normalization and ownership regressions."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


def _config(*, agent_uids=(), runtime=None):
    from task_env.environment.configuration import resolve_env_config

    return resolve_env_config(
        task_uid="c01a-fixture-v1",
        scene_uid="tabletop-v1",
        agent_uids=tuple(agent_uids),
        runtime=runtime,
    )


def test_task_config_precedence_and_pre_resolved_compatibility(tmp_path):
    from task_env.environment.configuration import resolve_task_env_config

    default_path = tmp_path / "default.yaml"
    default_path.write_text(
        "runtime:\n  physics_dt: 0.01\n  control_substeps: 2\nepisode:\n  horizon: 30\n",
        encoding="utf-8",
    )
    override_path = tmp_path / "override.yaml"
    override_path.write_text(
        "runtime:\n  control_substeps: 4\nepisode:\n  horizon: 7\n",
        encoding="utf-8",
    )
    base = _config()

    class FixtureEnv:
        @classmethod
        def default_config(cls):
            return base

        @classmethod
        def default_config_path(cls):
            return default_path

    resolved = resolve_task_env_config(
        FixtureEnv,
        {"runtime": {"control_substeps": 4}, "episode": {"horizon": 7}},
    )
    assert resolved.runtime.physics_dt == pytest.approx(0.01)
    assert resolved.runtime.control_substeps == 4
    assert resolved.episode.horizon == 7
    assert resolve_task_env_config(FixtureEnv, override_path) == resolved

    authoritative = _config(runtime={"physics_dt": 0.03})
    assert resolve_task_env_config(FixtureEnv, authoritative) is authoritative
    with pytest.raises(KeyError, match="cannot override task topology/semantics"):
        resolve_task_env_config(FixtureEnv, {"scene": {"scene_uid": "other-v1"}})


def test_custom_base_task_subclass_uses_component_configuration_without_marker(monkeypatch):
    from task_env import BaseTaskEnv, make_env
    from task_env.registry import ENV_REGISTRY, Registration

    class CustomTask(BaseTaskEnv):
        uid = 'custom-component-fixture-v1'
        task_uid = 'custom-component-fixture-v1'

    monkeypatch.setitem(ENV_REGISTRY._entries, CustomTask.uid,
                        Registration(CustomTask.uid, CustomTask))
    env = make_env(CustomTask.uid, config={'episode': {'horizon': 7}}, build_runtime=False)
    try:
        assert isinstance(env, BaseTaskEnv)
        assert env.config.episode.horizon == 7
        assert env._runtime is None
    finally:
        env.close()


def test_static_execution_plan_is_stable_and_marks_its_evidence_boundary():
    from task_env.environment.configuration import resolve_execution_plan

    class FixtureEnv:
        uid = "fixture-env-v1"

    config = _config(runtime={"physics_dt": 0.004, "control_substeps": 5})
    first = resolve_execution_plan(FixtureEnv, config, render_mode="rgb_array")
    second = resolve_execution_plan(FixtureEnv, config, render_mode="rgb_array")
    changed = resolve_execution_plan(
        FixtureEnv,
        _config(runtime={"physics_dt": 0.004, "control_substeps": 4}),
        render_mode="rgb_array",
    )

    assert first.identity_hash == second.identity_hash
    assert first.configuration_identity == second.configuration_identity
    assert first.identity_hash != changed.identity_hash
    mapping = first.to_mapping()
    assert mapping["admission_stage"] == "static_config"
    assert mapping["physics_provider"] == "geophys"
    assert mapping["timebase"] == {
        "physics_dt": 0.004,
        "control_substeps": 5,
        "control_dt": 0.02,
    }
    assert mapping["resource_owner_identities"]["physics_boundary"] == (
        "task_env.runtime.GeoPhysRuntimeBoundary"
    )
    assert "manifest" not in mapping
    assert "realization" not in mapping


def test_typed_state_requirements_are_bound_without_manifest_claims():
    from task_env.artifacts import StateRequirements
    from task_env.environment.configuration import resolve_execution_plan

    class FixtureEnv:
        uid = "fixture-env-v1"

    requirements = StateRequirements(
        schema_version="state-requirements-v1",
        consumer_kind="task",
        consumer_id="fixture-task",
        requirements=(),
    )
    plan = resolve_execution_plan(
        FixtureEnv, _config(), state_requirements=requirements
    )
    assert plan.state_requirements is requirements
    assert plan.to_mapping()["state_requirements"] == requirements.to_mapping()


def test_multi_agent_route_is_rejected_before_provider_bootstrap(monkeypatch):
    import task_env.tasks  # noqa: F401 - load the public component registrations
    import task_env.runtime as runtime_module
    from task_env.environment.env import BaseTaskEnv
    from task_env.environment.types import StageUnavailableError
    from task_env.registry import AGENT_REGISTRY

    def unexpected_bootstrap(**kwargs):
        raise AssertionError("static admission must precede provider bootstrap")

    monkeypatch.setattr(runtime_module, "bootstrap_task_runtime", unexpected_bootstrap)
    monkeypatch.setattr(
        AGENT_REGISTRY,
        "create",
        lambda uid: SimpleNamespace(uid=uid),
    )
    config = _config(agent_uids=("panda-v1", "other-robot-v1"))
    with pytest.raises(StageUnavailableError, match="at most one agent"):
        BaseTaskEnv(config=config, build_runtime=True)


def test_component_controller_selection_follows_robot_capability():
    from task_env.environment.configuration import resolve_env_config, resolve_execution_plan
    from task_env.environment.types import StageUnavailableError

    class FixtureEnv:
        uid = 'fixture-env-v1'

    robot = SimpleNamespace(uid='another-robot-v1', component_controller_kinds=('absolute_pose',))
    config = resolve_env_config(task_uid='fixture-v1', scene_uid='tabletop-v1',
        agent_uids=(robot.uid,), robot={'controller': {'kind': 'absolute_pose', 'reference': 'base'}})
    plan = resolve_execution_plan(FixtureEnv, config, agents=iter((robot,)))
    assert plan.controller_selections == ((robot.uid, 'absolute_pose', 'base'),)

    wrong = resolve_env_config(task_uid='fixture-v1', scene_uid='tabletop-v1',
        agent_uids=(robot.uid,), robot={'controller': {'kind': 'absolute_joint'}})
    with pytest.raises(StageUnavailableError, match='unsupported robot controller'):
        resolve_execution_plan(FixtureEnv, wrong, agents=(robot,))

    panda = resolve_env_config(task_uid='fixture-v1', scene_uid='tabletop-v1',
        agent_uids=('panda-v1',), robot={'controller': {'kind': 'absolute_joint'}})
    assert resolve_execution_plan(FixtureEnv, panda).controller_selections == (
        ('panda-v1', 'absolute_joint', None),)
    assert resolve_execution_plan(FixtureEnv, panda, agents=None).controller_selections == (
        ('panda-v1', 'absolute_joint', None),)


def test_missing_panda_controller_is_rejected_before_provider_bootstrap(monkeypatch):
    import task_env.tasks  # noqa: F401 - load the public component registrations
    import task_env.runtime as runtime_module
    from task_env.environment.env import BaseTaskEnv
    from task_env.environment.types import StageUnavailableError

    def unexpected_bootstrap(**kwargs):
        raise AssertionError("static admission must precede provider bootstrap")

    monkeypatch.setattr(runtime_module, "bootstrap_task_runtime", unexpected_bootstrap)
    with pytest.raises(StageUnavailableError, match="explicit robot.controller"):
        BaseTaskEnv(config=_config(agent_uids=("panda-v1",)), build_runtime=True)


def test_panda_binds_its_controller_and_frame_references_without_engine(monkeypatch):
    from task_env import controllers
    from task_env.environment.configuration import resolve_env_config
    from task_env.robots.panda import PandaAgent

    config = resolve_env_config(
        task_uid='fixture-v1', scene_uid='tabletop-v1', agent_uids=('panda-v1',),
        robot={'controller': {'kind': 'absolute_pose', 'reference': 'base'}},
    )
    refs = SimpleNamespace(base_body_name='base_link', base_body_id=3,
                           eef_site_name='tool_site', eef_site_id=7)
    boundary = object()
    bound = []
    gripper = SimpleNamespace(bind_force_limit=lambda value: bound.append(value))
    monkeypatch.setattr(PandaAgent, 'create_gripper_controller', lambda *_args, **_kwargs: gripper)

    class Adapter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.action_space = object()

    monkeypatch.setattr(controllers, 'AbsolutePoseActionAdapter', Adapter)
    runtime, action_spec = PandaAgent().bind_runtime(
        references=refs, config=config, boundary=boundary,
    )
    assert bound == [boundary]
    assert runtime.uid == 'panda-v1'
    assert runtime.base.source_name == 'base_link' and runtime.ee.source_name == 'tool_site'
    assert runtime.controller.action_spec is action_spec
    assert action_spec.reference_identity == 'body:base_link'
    assert runtime.controller._adapter.kwargs['gripper'] is gripper


def test_failed_environment_construction_rolls_back_the_runtime(monkeypatch):
    import task_env.tasks  # noqa: F401 - load the public component registrations
    import task_env.runtime as runtime_module
    from task_env.environment.env import BaseTaskEnv

    class CloseProbe:
        def __init__(self):
            self.close_calls = 0

        def close(self):
            self.close_calls += 1

    runtime = CloseProbe()
    monkeypatch.setattr(
        runtime_module,
        "bootstrap_task_runtime",
        lambda **kwargs: SimpleNamespace(boundary=runtime, compiled_scene=object()),
    )

    class FailingEnv(BaseTaskEnv):
        uid = "c01a-construction-failure-v1"

        def create_task_definition(self, compiled_scene):
            raise RuntimeError("injected post-bootstrap failure")

    with pytest.raises(RuntimeError, match="injected post-bootstrap failure"):
        FailingEnv(config=_config(), build_runtime=True)
    assert runtime.close_calls == 1


def test_close_has_one_runtime_owner_and_attempts_all_auxiliary_owners():
    import task_env.tasks  # noqa: F401 - load the public component registrations
    from task_env.environment.env import BaseTaskEnv

    class CloseProbe:
        def __init__(self, *, fail=False):
            self.close_calls = 0
            self.fail = fail

        def close(self):
            self.close_calls += 1
            if self.fail:
                raise RuntimeError("injected close failure")

    runtime = CloseProbe()
    lifecycle = CloseProbe()
    # Model SingleTaskLifecycleAdapter's current ownership of RuntimeBoundary.
    lifecycle.close = lambda: runtime.close()
    ui = CloseProbe(fail=True)
    sensor = CloseProbe()
    env = BaseTaskEnv(config=_config(), build_runtime=False)
    env._runtime = runtime
    env._task_lifecycle = lifecycle
    env._ui_render_provider = ui
    env._sensor_provider = sensor

    with pytest.raises(RuntimeError, match="injected close failure"):
        env.close()
    assert (ui.close_calls, sensor.close_calls, runtime.close_calls) == (1, 1, 1)
    env.close()
    assert (ui.close_calls, sensor.close_calls, runtime.close_calls) == (1, 1, 1)


@pytest.mark.parametrize('value', [False, 0, '', [], 1])
def test_component_overlay_rejects_non_mapping_even_when_empty(value):
    from task_env.environment.configuration import overlay_public_env_config
    from task_env.environment.config import ResolvedEnvConfig
    with pytest.raises(TypeError, match='overlay must be a mapping'):
        overlay_public_env_config(ResolvedEnvConfig(), {'runtime': value})
