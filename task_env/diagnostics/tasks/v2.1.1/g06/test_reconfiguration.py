"""Pure and fake-owner checks for G06c whole-batch device reconfiguration."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import sys

import gymnasium as gym
import numpy as np
import pytest

import task_env.tasks  # noqa: F401  (replays selected task registrations)
from task_env.environment.configuration import resolve_task_env_config
from task_env.registry import ENV_REGISTRY
from task_env.vectorization.homogeneous import HomogeneousVectorTaskEnv
from task_env.vectorization.reconfiguration import (
    DeviceBatchBuildInput,
    PreparedReconfiguration,
    _assert_fixed_contract,
    parse_switch_options,
    prepare_reconfiguration,
    render_config_signature,
)


TASK_UID = "pendulum-v1"


def _resolved(provider: str = "mujoco_warp", *, render=None):
    values = {
        "execution": {"physics_provider": provider},
        "episode": {"seed": 73, "horizon": 4},
    }
    if render is not None:
        values["render"] = render
    return resolve_task_env_config(
        ENV_REGISTRY.get(TASK_UID), values, execution_scope="device_batch"
    )


@pytest.fixture(autouse=True)
def _isolated_interpreter(monkeypatch):
    # Configuration resolution only needs a declared isolated route; these
    # checks never construct a native provider.
    monkeypatch.setenv("GEOCHORA_MJWARP_PYTHON", sys.executable)
    monkeypatch.setenv("ISAAC_SIM_PYTHON", sys.executable)
    monkeypatch.setenv("GEOCHORA_GEOPHYS_PYTHON", sys.executable)


def _build_input(config=None, *, provider="mujoco_warp"):
    config = _resolved(provider) if config is None else config
    return DeviceBatchBuildInput(
        uid=TASK_UID,
        num_env=3,
        backend="cuda",
        env_config={
            "execution": {"physics_provider": provider},
            "episode": {"seed": 73, "horizon": 4},
        },
        worker_directory=None,
        render_mode=None,
        resolved_config=config,
        provider=provider,
        generation=0,
        render_signature=render_config_signature(config.environment.render),
    )


class _FakeSpec:
    def __init__(self, build_input, *, generation=0, fail_reset=False, fail_close=False):
        self.uid = build_input.uid
        self.num_envs = 3
        self.single_action_space = gym.spaces.Dict(
            {"effort": gym.spaces.Box(-1.0, 1.0, (2,), np.float32)}
        )
        self.single_observation_space = gym.spaces.Dict(
            {"state": gym.spaces.Box(-1e6, 1e6, (4,), np.float32)}
        )
        self.metadata = {
            "execution": "device_worker",
            "backend": "cuda",
            "physics_provider": build_input.provider,
            "device_generation": generation,
        }
        self.parallel_render_provider = None
        # The real factory attaches a fresh build input carrying the new
        # generation; the fake mirrors that so metadata reflects the rebuild.
        self.device_build_input = replace(build_input, generation=generation)
        self.generation = generation
        self.closed = False
        self.fail_reset = fail_reset
        self.fail_close = fail_close
        self.carried = None
        self.reset_calls = []
        self._device_fault = None

    def export_reconfiguration_state(self):
        return {
            "host_rng": {"state": "captured"},
            "device_rng": None,
            "device_pcg": None,
            "device": "cuda:0",
        }

    def import_reconfiguration_state(self, state):
        self.carried = state

    def reset_sampled_device(self, *, seed=None, mask=None):
        self.reset_calls.append((seed, mask))
        if self.fail_reset:
            raise RuntimeError("first target reset failed")
        return SimpleNamespace(
            observation={"state": np.zeros((3, 4), dtype=np.float32)},
            infos={"episode_id": np.zeros(3, dtype=np.int64)},
        )

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.fail_close:
            raise RuntimeError("close failed")


def _fake_env():
    build_input = _build_input()
    spec = _FakeSpec(build_input, generation=0)
    return HomogeneousVectorTaskEnv(spec, execution_mode="device"), spec, build_input


def _patch_preparation(monkeypatch, *, generation=1):
    def prepare(build_input, execution, *, generation):
        return PreparedReconfiguration(
            target_config=object(),
            target_provider=str(execution.get("physics_provider", "isaacsim")),
            generation=generation,
            execution=dict(execution),
        )

    monkeypatch.setattr(
        "task_env.vectorization.reconfiguration.prepare_reconfiguration", prepare
    )


def test_parse_switch_options_accepts_only_the_documented_execution_target():
    assert parse_switch_options(None, num_envs=3) is None
    assert parse_switch_options({}, num_envs=3) is None
    assert parse_switch_options({"execution": {}}, num_envs=3) is None
    assert parse_switch_options(
        {"execution": {"physics_provider": "isaacsim"}}, num_envs=3
    ) == {"physics_provider": "isaacsim"}
    with pytest.raises(ValueError, match="only 'execution'"):
        parse_switch_options({"mask": None}, num_envs=3)
    with pytest.raises(ValueError, match="unsupported fields"):
        parse_switch_options({"execution": {"task": "other"}}, num_envs=3)
    with pytest.raises(TypeError, match="must be a mapping"):
        parse_switch_options({"execution": "isaacsim"}, num_envs=3)


def test_prepare_reconfiguration_rejects_an_unadmitted_edge_before_touch():
    build_input = _build_input(provider="mujoco_warp")
    with pytest.raises(ValueError, match="not admitted"):
        prepare_reconfiguration(
            build_input, {"physics_provider": "geophys"}, generation=1
        )
    # The same provider remains rebuildable without claiming a new edge.
    prepared = prepare_reconfiguration(
        build_input, {"physics_provider": "mujoco_warp"}, generation=1
    )
    assert prepared.target_provider == "mujoco_warp"
    assert prepared.generation == 1


def test_prepare_reconfiguration_advances_generation_only():
    build_input = _build_input(provider="mujoco_warp")
    prepared = prepare_reconfiguration(
        build_input, {"physics_provider": "isaacsim"}, generation=1
    )
    assert prepared.target_config.physics_provider == "isaacsim"
    assert prepared.target_config.environment.render == (
        build_input.resolved_config.environment.render
    )
    with pytest.raises(ValueError, match="monotonically"):
        prepare_reconfiguration(
            build_input, {"physics_provider": "isaacsim"}, generation=0
        )


def test_switch_does_not_carry_a_foreign_provider_manifest(monkeypatch):
    original = _build_input(provider='mujoco_warp')
    original = replace(original, env_config={'execution': {
        'physics_provider': 'mujoco_warp', 'interpreter': '/old/python',
        'source_delivery_manifest': '/old/provider-manifest.json'}})
    target = _resolved(provider='isaacsim')
    requests = []

    def resolve(_environment_type, request, **_kwargs):
        requests.append(request)
        return target

    monkeypatch.setattr('task_env.environment.configuration.resolve_task_env_config', resolve)
    prepare_reconfiguration(original, {'physics_provider': 'isaacsim'}, generation=1)
    assert requests[0]['execution'] == {'physics_provider': 'isaacsim'}


def test_later_same_provider_rebuild_uses_the_committed_target_request():
    original = _build_input(provider='mujoco_warp')
    prepared = prepare_reconfiguration(original, {
        'physics_provider': 'isaacsim', 'interpreter': '/target/isaac-python'}, generation=1)
    committed = replace(original, env_config=prepared.target_request,
                        resolved_config=prepared.target_config, provider='isaacsim', generation=1)
    again = prepare_reconfiguration(committed, {'physics_provider': 'isaacsim'}, generation=2)
    assert again.target_config.execution_spec_v2.interpreter == '/target/isaac-python'


def test_fixed_contract_rejects_a_changed_renderer_or_task_recipe():
    original = _resolved(provider="mujoco_warp")
    with pytest.raises(ValueError, match="environment.render"):
        _assert_fixed_contract(original, replace(original, environment=replace(
            original.environment,
            render=replace(original.environment.render, width=321),
        )))
    with pytest.raises(ValueError, match="task parameters"):
        _assert_fixed_contract(original, replace(original, task_parameters=(("x", 1.0),)))


def test_rebuild_swaps_generation_and_preserves_env_identity(monkeypatch):
    env, old_spec, build_input = _fake_env()
    env_id = id(env)
    replacement = _FakeSpec(build_input, generation=1)
    calls = []

    def factory(**kwargs):
        calls.append(kwargs)
        return replacement

    monkeypatch.setattr(
        "task_env.vectorization.factory.make_selected_device_spec", factory
    )
    _patch_preparation(monkeypatch)

    observation, infos = env.reset(
        seed=7, options={"execution": {"physics_provider": "isaacsim"}}
    )
    assert id(env) == env_id
    assert old_spec.closed is True
    assert env._task_spec is replacement
    assert calls[0]["generation"] == 1
    assert calls[0]["resolved_config"] is not None
    assert replacement.reset_calls == [(7, None)]
    assert replacement.carried is None
    assert env.get_record_metadata()["device_execution"]["generation"] == 1
    assert observation["state"].shape == (3, 4)


def test_rebuild_without_seed_continues_the_reset_stream(monkeypatch):
    env, _old_spec, build_input = _fake_env()
    replacement = _FakeSpec(build_input, generation=1)
    monkeypatch.setattr(
        "task_env.vectorization.factory.make_selected_device_spec",
        lambda **kwargs: replacement,
    )
    _patch_preparation(monkeypatch)

    env.reset(options={"execution": {"physics_provider": "isaacsim"}})
    assert replacement.carried == {
        "host_rng": {"state": "captured"},
        "device_rng": None,
        "device_pcg": None,
        "device": "cuda:0",
    }
    assert replacement.reset_calls == [(None, None)]


def test_rejected_target_keeps_the_old_batch_usable():
    env, old_spec, _build_input = _fake_env()
    with pytest.raises(ValueError, match="not admitted"):
        env.reset(options={"execution": {"physics_provider": "geophys"}})
    assert old_spec.closed is False
    assert env._task_spec is old_spec
    observation, _infos = env.reset(seed=1)
    assert observation["state"].shape == (3, 4)


def test_partial_mask_with_switch_is_rejected_before_destruction():
    env, old_spec, _build_input = _fake_env()
    with pytest.raises(ValueError, match="all-true mask"):
        env.reset(
            mask=np.array([True, False, True]),
            options={"execution": {"physics_provider": "isaacsim"}},
        )
    assert old_spec.closed is False


def test_tensor_mask_with_switch_is_checked_before_destruction(monkeypatch):
    import torch

    env, old_spec, build_input = _fake_env()
    with pytest.raises(ValueError, match='all-true mask'):
        env.reset(mask=torch.tensor([True, False, True]),
                  options={'execution': {'physics_provider': 'isaacsim'}})
    assert old_spec.closed is False
    replacement = _FakeSpec(build_input, generation=1)
    monkeypatch.setattr('task_env.vectorization.factory.make_selected_device_spec',
                        lambda **kwargs: replacement)
    _patch_preparation(monkeypatch)
    env.reset(mask=torch.ones(3, dtype=torch.bool),
              options={'execution': {'physics_provider': 'isaacsim'}})
    assert old_spec.closed is True
    assert env._task_spec is replacement


def test_prepared_reset_selection_is_bound_to_its_batch_owner():
    import torch
    from weakref import WeakValueDictionary
    from task_env.vectorization.task_definition import BatchTaskLifecycleAdapter

    def adapter():
        value = object.__new__(BatchTaskLifecycleAdapter)
        value.num_envs = 3
        value.device_field_plan = SimpleNamespace(device='cpu')
        value._device_reset_selections = WeakValueDictionary()
        return value

    old, new = adapter(), adapter()
    mask = torch.tensor([True, False, True])
    selection = old.prepare_device_reset_selection(mask)
    old._require_owned_device_reset_selection(selection)
    with pytest.raises(ValueError, match='stale or belongs to another batch'):
        new.reset_device({}, mask, selection=selection)


def test_pendulum_partial_reset_preserves_unselected_task_dwell_counter():
    import torch
    from task_env.tasks.pendulum import PendulumTaskDefinition

    task = PendulumTaskDefinition(qpos_id=0, qvel_id=0)
    task._device_upright_steps = torch.tensor([3, 5, 7], dtype=torch.int32)
    task.reset_device(state=SimpleNamespace(num_envs=3, device='cpu'),
                      reset_mask=torch.tensor([True, False, True]))
    assert task._device_upright_steps.tolist() == [0, 5, 0]


def test_changed_native_space_faults_and_closes_replacement(monkeypatch):
    env, old, build_input = _fake_env()
    replacement = _FakeSpec(build_input, generation=1)
    replacement.single_action_space = gym.spaces.Box(-1, 1, shape=(7,), dtype=np.float32)
    monkeypatch.setattr('task_env.vectorization.factory.make_selected_device_spec',
                        lambda **kwargs: replacement)
    _patch_preparation(monkeypatch)
    with pytest.raises(ValueError, match='changes the action or observation contract'):
        env.reset(options={'execution': {'physics_provider': 'isaacsim'}})
    assert old.closed and replacement.closed
    with pytest.raises(RuntimeError, match='faulted'):
        env.reset()
    env.close()


def test_first_reset_preserves_error_when_replacement_cleanup_fails(monkeypatch):
    env, _old, build_input = _fake_env()
    replacement = _FakeSpec(build_input, generation=1, fail_reset=True, fail_close=True)
    monkeypatch.setattr('task_env.vectorization.factory.make_selected_device_spec',
                        lambda **kwargs: replacement)
    _patch_preparation(monkeypatch)
    with pytest.raises(RuntimeError, match='first target reset failed') as caught:
        env.reset(options={'execution': {'physics_provider': 'isaacsim'}})
    assert any('cleanup also failed' in note for note in caught.value.__notes__)
    assert replacement.closed
    env.close()
    env.close()


def test_renderer_binding_failure_retires_orphan_and_adapter_even_on_cleanup_error():
    from task_env.vectorization.factory import _cleanup_failed_device_build

    calls = []

    class Owner:
        def __init__(self, name, fail=False):
            self.name, self.fail = name, fail
            self.parallel_render_provider = None

        def close(self):
            calls.append(self.name)
            if self.fail:
                raise RuntimeError(self.name + ' failed')

    error = RuntimeError('renderer binding failed')
    _cleanup_failed_device_build(Owner('adapter', fail=True), Owner('source', fail=True),
                                 None, None, None, error)
    assert calls == ['source', 'adapter']
    assert len(error.__notes__) == 2


def test_failure_after_worker_creation_closes_runtime_and_source(monkeypatch):
    from task_env.vectorization.factory import _cleanup_failed_device_build

    calls = []
    runtime = SimpleNamespace(close=lambda: calls.append('runtime'))
    controller = SimpleNamespace(close_device=lambda: calls.append('controller'))
    definition = SimpleNamespace(close_device=lambda: calls.append('definition'))
    monkeypatch.setattr('task_env.runtime.sessions.source.close_source_and_task_resources',
                        lambda source, binding, error: calls.append((source, binding)))
    _cleanup_failed_device_build(None, None, runtime, {'source': 'scene'}, 'binding',
                                 RuntimeError('build failed'), controller, definition)
    assert calls == ['runtime', 'controller', 'definition', ('scene', 'binding')]


def test_build_failure_after_teardown_faults_the_same_env(monkeypatch):
    env, old_spec, _build_input = _fake_env()
    env_id = id(env)

    def factory(**kwargs):
        raise RuntimeError("construction failed")

    monkeypatch.setattr(
        "task_env.vectorization.factory.make_selected_device_spec", factory
    )
    _patch_preparation(monkeypatch)

    with pytest.raises(RuntimeError, match="construction failed"):
        env.reset(options={"execution": {"physics_provider": "isaacsim"}})
    assert id(env) == env_id
    assert old_spec.closed is True
    assert env._task_spec is None
    with pytest.raises(RuntimeError, match="faulted"):
        env.step({})
    with pytest.raises(RuntimeError, match="faulted"):
        env.read_device_state(("qpos",))
    with pytest.raises(RuntimeError, match="faulted"):
        env.render(mode="rgb_array")
    env.close()
    env.close()


def test_first_target_reset_failure_cleans_and_faults(monkeypatch):
    env, old_spec, build_input = _fake_env()
    replacement = _FakeSpec(build_input, generation=1, fail_reset=True)
    monkeypatch.setattr(
        "task_env.vectorization.factory.make_selected_device_spec",
        lambda **kwargs: replacement,
    )
    _patch_preparation(monkeypatch)

    with pytest.raises(RuntimeError, match="first target reset failed"):
        env.reset(options={"execution": {"physics_provider": "isaacsim"}})
    assert old_spec.closed is True
    assert replacement.closed is True
    assert env._task_spec is None
    env.close()
    env.close()


def test_teardown_failure_faults_without_constructing_a_target(monkeypatch):
    env, old_spec, build_input = _fake_env()
    old_spec.fail_close = True
    called = []
    monkeypatch.setattr(
        "task_env.vectorization.factory.make_selected_device_spec",
        lambda **kwargs: called.append(kwargs),
    )
    _patch_preparation(monkeypatch)

    with pytest.raises(RuntimeError, match="teardown failed"):
        env.reset(options={"execution": {"physics_provider": "isaacsim"}})
    assert called == []
    assert env._task_spec is old_spec
    assert env._device_fault is not None
    with pytest.raises(RuntimeError, match='faulted'):
        env.read_device_state(('qpos',))
    env.close()
    env.close()
