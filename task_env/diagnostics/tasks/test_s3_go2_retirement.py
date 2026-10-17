"""S3 Go2 retirement boundaries; provider-free and non-qualifying."""

from __future__ import annotations

import importlib.util
import importlib

import gymnasium as gym
import numpy as np
import pytest


GO2_TASK_UIDS = (
    "go2-walk-v1",
    "go2-walk-deploy-v1",
    "go2-walk-deploy-height-v1",
    "go2-walk-codex",
)


def _generic_parallel_factory(**_kwargs):
    return object()


def _find_spec_or_none(module_name):
    """Treat an absent parent package as an unavailable dotted module."""
    try:
        return importlib.util.find_spec(module_name)
    except ModuleNotFoundError:
        return None


def test_selected_tasks_remain_registered_and_go2_uids_are_retired():
    import task_env
    from task_env.registry import AGENT_REGISTRY, ENV_REGISTRY, make_agent, make_env
    from task_env.vectorization.registry import PARALLEL_ENV_REGISTRY

    assert "pick-cube-p16-reference-v1" in ENV_REGISTRY.uids()
    assert "nut-assembly-outcome-reference-v1" in ENV_REGISTRY.uids()
    assert not any(uid.startswith("go2-") for uid in ENV_REGISTRY.uids())
    assert "go2-v1" not in AGENT_REGISTRY.uids()
    assert not any(uid.startswith("go2-") for uid in PARALLEL_ENV_REGISTRY.uids())
    assert "Go2WalkEnv" not in task_env.__all__

    for uid in GO2_TASK_UIDS:
        with pytest.raises(ValueError, match="Go2 task UID.*retired.*no task is substituted"):
            make_env(uid)
    with pytest.raises(ValueError, match="Go2 agent UID.*retired.*no agent is substituted"):
        make_agent("go2-v1")


@pytest.mark.parametrize(
    "module_name",
    (
    "task_env.tasks.go2_walk.task",
    "task_env.tasks.go2_walk_deploy.task",
    "task_env.tasks.go2_walk_codex.task",
    "task_env.robots.go2.go2",
    "task_env.diagnostics.go2.mujoco_oracle",
    "task_env.diagnostics.runtime.stage_f_cuda_graph_lifecycle",
    "task_env.script.rl.go2.go2_mujoco",
        "task_env.flora_go2_assets",
        "task_env.script.flora_go2_single_smoke",
    ),
)
def test_retired_go2_modules_are_not_importable(module_name):
    assert _find_spec_or_none(module_name) is None


def test_generic_rsl_cli_requires_an_explicit_registered_task():
    from task_env.script.rl.rsl_ppo import _parser

    parser = _parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    args = parser.parse_args(["--env-id", "pendulum-v1", "--render"])
    assert args.env_id == "pendulum-v1"
    assert args.render is True
    hard_render = parser.parse_args(["--env-id", "pendulum-v1", "--hard-render"])
    assert hard_render.hard_render is True


@pytest.mark.parametrize("env_id", (*GO2_TASK_UIDS, "go2_walk", "go2_walk_deploy", "go2_walk_deploy_height"))
def test_generic_rsl_runner_rejects_retired_go2_ids_without_substitution(env_id):
    from task_env.alg.runner import canonical_ppo_env_id

    with pytest.raises(ValueError, match="Go2 RSL environment.*retired.*no training task is substituted"):
        canonical_ppo_env_id(env_id)


def test_generic_runtime_diagnostics_require_explicit_task_uid():
    parser = importlib.import_module(
        "task_env.diagnostics.runtime.stage17_performance_profile"
    ).build_parser()
    action = next(item for item in parser._actions if item.dest == "task_uid")
    assert action.required is True


def test_static_only_runtime_diagnostics_are_retired():
    for module_name in (
        "task_env.diagnostics.runtime.stage_a_runtime_profile",
        "task_env.diagnostics.runtime.stage18_bridge_benchmark",
        "task_env.diagnostics.runtime.stage_g_contact_precision_gate",
    ):
        assert _find_spec_or_none(module_name) is None


def test_generic_rl_vectorization_and_renderer_contracts_remain_importable():
    from task_env.alg.contracts import LearnerTensorContract
    from task_env.alg.rsl_rl.action_transform import RslActionTransformSpec
    from task_env.alg.rsl_rl.adapter import TaskEnvRslVecAdapter
    from task_env.runtime.device_plan import DeviceFieldPlan
    from task_env.vectorization.contracts import BatchResetSample
    from task_env.vectorization.contracts import ParallelTaskSpecProtocol
    from task_env.vectorization.homogeneous import HomogeneousVectorTaskEnv
    from task_env.vectorization.registry import ParallelEnvRegistry
    from task_env.vectorization.sb3 import TaskEnvSB3VecAdapter
    from task_env.render import available_render_backends

    action = RslActionTransformSpec(
        policy_low=-1.0,
        policy_high=1.0,
        native_low=-0.8,
        native_high=0.8,
        scale=2.0,
    )
    assert action.apply_numpy([-2.0, 0.5, 3.0]).tolist() == [-0.8, 0.8, 0.8]
    assert TaskEnvRslVecAdapter is not None
    assert TaskEnvSB3VecAdapter is not None
    assert HomogeneousVectorTaskEnv is not None
    assert ParallelTaskSpecProtocol is not None
    assert "flora" in {descriptor.name for descriptor in available_render_backends()}

    observation_space = gym.spaces.Box(-1.0, 1.0, shape=(2,), dtype=np.float32)
    action_space = gym.spaces.Box(-1.0, 1.0, shape=(1,), dtype=np.float32)
    contract = LearnerTensorContract.from_spaces(observation_space, action_space)
    assert contract.flatten_observation(np.zeros((2, 2), dtype=np.float32), 2).shape == (2, 2)
    assert contract.validate_flat_action(np.zeros((2, 1), dtype=np.float32), 2).shape == (2, 1)
    reset_sample = BatchResetSample(
        state={"qpos": np.zeros((2, 1), dtype=np.float32)},
        seeds=(1, 2),
        parameters=({}, {}),
    )
    assert len(reset_sample.seeds) == 2
    device_plan = DeviceFieldPlan(
        available=False,
        num_envs=2,
        backend="cpu",
        execution="local",
        device=None,
        transfer_mode="host_numpy",
        state_readback_fields=(),
        fields=(),
        reasons=("no device transition requested",),
    )
    assert not device_plan.available and device_plan.num_envs == 2

    registry = ParallelEnvRegistry()

    registry.register("example-batch-v1", _generic_parallel_factory)
    assert registry.contains("example-batch-v1")
    assert registry.get("example-batch-v1") is _generic_parallel_factory


def test_generic_sb3_adapter_preserves_five_to_four_tuple_lifecycle():
    from task_env.vectorization.sb3 import TaskEnvSB3VecAdapter

    class FakeBatch:
        num_envs = 2
        horizon = 5
        metadata = {"execution": "local"}
        render_mode = None
        single_observation_space = gym.spaces.Box(-10.0, 10.0, shape=(2,), dtype=np.float32)
        single_action_space = gym.spaces.Box(-1.0, 1.0, shape=(1,), dtype=np.float32)

        def __init__(self):
            self.reset_masks = []

        def reset(self, *, seed=None, options=None, mask=None):
            self.reset_masks.append(None if mask is None else np.asarray(mask).copy())
            return np.zeros((2, 2), dtype=np.float32), [{}, {}]

        def step(self, actions):
            self.actions = np.asarray(actions).copy()
            return (
                np.ones((2, 2), dtype=np.float32),
                np.array([1.0, 2.0], dtype=np.float32),
                np.array([False, False]),
                np.array([False, True]),
                [{}, {}],
            )

        def close(self):
            self.closed = True

    raw = FakeBatch()
    env = TaskEnvSB3VecAdapter(raw)
    observation = env.reset()
    assert observation.shape == (2, 2)
    env.step_async(np.zeros((2, 1), dtype=np.float32))
    observation, rewards, dones, infos = env.step_wait()
    assert observation.shape == (2, 2)
    assert rewards.tolist() == [1.0, 2.0]
    assert dones.tolist() == [False, True]
    assert infos[1]["TimeLimit.truncated"] is True
    assert "terminal_observation" in infos[1]
    assert raw.reset_masks[-1].tolist() == [False, True]
    env.close()
    assert raw.closed


def test_generic_rsl_adapter_preserves_action_and_timeout_contract():
    from task_env.alg.rsl_rl.adapter import TaskEnvRslVecAdapter

    class FakeBatch:
        num_envs = 2
        horizon = 5
        backend = "cpu"
        metadata = {"execution": "local"}
        single_observation_space = gym.spaces.Box(-10.0, 10.0, shape=(2,), dtype=np.float32)
        single_action_space = gym.spaces.Box(-1.0, 1.0, shape=(1,), dtype=np.float32)

        def __init__(self):
            self.reset_masks = []

        def reset(self, *, seed=None, mask=None):
            self.reset_masks.append(None if mask is None else np.asarray(mask).copy())
            return np.zeros((2, 2), dtype=np.float32), [{}, {}]

        def step(self, actions):
            self.actions = np.asarray(actions).copy()
            return (
                np.ones((2, 2), dtype=np.float32),
                np.array([1.0, 2.0], dtype=np.float32),
                np.array([False, False]),
                np.array([False, True]),
                [{}, {}],
            )

    raw = FakeBatch()
    env = TaskEnvRslVecAdapter(raw, device="cpu", transfer_mode="host_numpy")
    assert tuple(env.get_observations().batch_size) == (2,)
    _, rewards, dones, extras = env.step(np.array([[2.0], [-2.0]], dtype=np.float32))
    assert raw.actions.tolist() == [[1.0], [-1.0]]
    assert rewards.tolist() == [1.0, 2.0]
    assert dones.tolist() == [False, True]
    assert extras["time_outs"].tolist() == [False, True]
    assert raw.reset_masks[-1].tolist() == [False, True]
    assert "terminal_observation" in extras["infos"][1]
