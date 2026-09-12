# Parallel raw tree and SB3 boundary

并行入口有两层，不要把 raw tree 和 SB3 learner boundary 混成一个 API：

```text
task_env.make_parallel_env
    -> raw tree, Gymnasium-style task lifecycle, per-slot batch state
    -> optional SB3FlattenVecWrapper
    -> SB3 VecEnv four-tuple
```

## Raw vector contract

```python
import numpy as np
from task_env import make_parallel_env

env = make_parallel_env(
    "pendulum-v1",
    {"base_seed": 800},
    num_env=8,
    backend="cpu",
    execution="remote",
)
try:
    observation = env.reset()
    assert observation["state"]["proprioception"].shape == (8, 3)

    action = {"torque": np.zeros((8, 1), dtype=np.float32)}
    env.step_async(action)
    observation, reward, done, infos = env.step_wait()
    assert observation["state"]["proprioception"].shape == (8, 3)
    assert reward.shape == (8,)
    assert done.shape == (8,)
    assert len(infos) == 8
finally:
    env.close()
```

The raw vector runtime validates every action leaf, requires the batch size as the leading dimension, and keeps task
metadata shared. A completed raw slot is not silently reset by the task runtime; masked reset is a lifecycle operation.
The remote SB3 bridge may perform controlled autoreset only to satisfy the SB3 protocol, preserving
`terminal_observation` and `reset_info` in `infos`.

## SB3 learner boundary

```python
from stable_baselines3 import PPO
from task_env import make_parallel_env
from task_env.utils import SB3FlattenVecWrapper

raw_env = make_parallel_env(
    "pendulum-v1", {"base_seed": 800}, num_env=8, backend="cpu", execution="remote"
)
env = SB3FlattenVecWrapper(raw_env)
try:
    model = PPO(
        "MlpPolicy",
        env,
        n_steps=5,
        batch_size=5 * 8,
        n_epochs=1,
        device="cpu",
        verbose=0,
    )
    model.learn(total_timesteps=3 * 5 * 8)
finally:
    env.close()
```

`SB3FlattenVecWrapper` is the only example-layer flattening boundary. The simulator child never constructs PPO or its
optimizer, and the recorder must be placed below this wrapper when raw H5 tree output is required.

## Long run and return curve

```bash
PYTHONPATH=GeoPhys/src:. python -m task_env.script.rl.pendulum_ppo \
  --num-env 8 --rollout-steps 5 --updates 3000 --save-log \
  --output-dir temp_outputs/task_env/rl/pendulum_ppo_long
```

`--updates` counts PPO rollout/update cycles. `--save-log` writes `return_curve.h5` (or a supplied path)
incrementally and once more at shutdown. The H5 file contains `episodes/`, `rollouts/`, and `active/` groups:
episode returns indexed by learner timesteps, episode lengths and slot indices, a 100-episode rolling mean,
per-rollout timesteps/mean returns, new and cumulative episode counts, a `rollouts/mean_return_valid` mask, active
partial returns, and run metadata as root attributes. `rollouts/mean_return` is intentionally NaN when that rollout
completed no new episode; use the validity mask before plotting it. Logger progress is throttled by
`--log-every-updates` (default 100); curve flushes use `--save-every-updates` (default 10).
