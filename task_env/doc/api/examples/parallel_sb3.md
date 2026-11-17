# Parallel environment and SB3 boundary

G06 subsequently accepted bounded Pendulum/PickCube device routes. The older host SB3 wrapper retains its own fixed-space, masked autoreset and terminal-observation contract; it explicitly rejects coordinated device same-step rather than resetting a second time. Neither registration nor device stepping alone proves CUDA training support. See the [current state](../../../../docs/module/task_env/v2.1.1/maintenance/current-state.md).

The following retained historical example targets the older `merged_scene` batch route and requires a fresh output directory. Its own current source reports the formal Pendulum adapter unavailable; it is not a current passing training claim:

```bash
PYTHONPATH=GeoPhys/src:. python examples/learning/pendulum_sb3.py \
  --output-dir workspace/maintenance/pendulum-sb3-smoke-01
```

Its historical intended configuration uses two environments, one PPO update, two rollout steps per environment,
CPU simulation, and the `implicitfast` integrator. It writes the existing
runner's checkpoint, `return_curve.h5`, `summary.json`, and a small
`example_result.json` receipt. The example applies Linux-oriented per-process
time and `RLIMIT_AS` limits. `RLIMIT_AS` is a virtual address-space cap, not an
RSS or process-tree memory limit. Do not treat the historical command as a current successful run or a training qualification.

The following raw vector example documents a historical host contract; it is not evidence that this specific current formal Task admits that configuration:

```python
from task_env import make_parallel_env

raw_env = make_parallel_env(
    "pendulum-v1", {"base_seed": 73}, num_env=2, backend="cpu", execution="remote"
)
try:
    raw_observation = raw_env.reset()
    # raw_observation remains a structured batch tree.
finally:
    raw_env.close()
```

`SB3FlattenVecWrapper` remains the learner boundary and owns structured-to-flat
conversion. TaskEnv owns neither PPO's optimizer nor the algorithm. The current
selected PickCube and NutAssembly manipulation UIDs do not become default PPO
targets through the existence of these adapters.

For the separately admitted G06 device path, the public caller follows this
contract (requires CUDA and the selected provider's installed runtime):

```python
import torch
from task_env import make_parallel_env

env = make_parallel_env('pendulum-v1', env_config={
    'execution': {'physics_provider': 'mujoco_warp'},
    'episode': {'seed': 73, 'horizon': 20},
}, num_env=3, backend='cuda', execution='device')
try:
    observation, info = env.reset(seed=73)
    action = {'torque': torch.zeros((3, 1), dtype=torch.float32, device='cuda')}
    observation, reward, terminated, truncated, info = env.step(action)
    print(info['episode_id'], info['_final_observation'])
finally:
    env.close()
```

This is the shape used by the existing device example, statically checked here;
the current attempt did not run CUDA training or this new block. Its same-step
terminal and reset information belongs to the device lifecycle; passing this
environment to the legacy SB3/RSL adapter is rejected rather than performing a
second reset. On the old host path `terminal_observation` belongs to its own
wrapper. Do not conflate these two contracts.

The RSL-RL command remains generic and fail-closed. It requires an explicit
`--env-id`; admission requires an active homogeneous registration and
compatible action/observation contracts. No new RSL training run is claimed,
and no replacement for the retired Go2 target is selected.
