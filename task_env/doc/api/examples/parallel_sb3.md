# Parallel environment and SB3 boundary

The current generic learning example is Pendulum on the registered
`merged_scene` batch route. The root example delegates the training loop to
the existing runner; it fixes a small CPU configuration and requires a fresh
output directory:

```bash
PYTHONPATH=GeoPhys/src:. python examples/learning/pendulum_sb3.py \
  --output-dir workspace/maintenance/pendulum-sb3-smoke-01
```

This runs two environments, one PPO update, two rollout steps per environment,
CPU simulation, and the `implicitfast` integrator. It writes the existing
runner's checkpoint, `return_curve.h5`, `summary.json`, and a small
`example_result.json` receipt. The example applies Linux-oriented per-process
time and `RLIMIT_AS` limits. `RLIMIT_AS` is a virtual address-space cap, not an
RSS or process-tree memory limit. This short smoke checks wiring and cleanup;
it does not measure convergence or qualify a training capability.

The raw vector contract remains available directly:

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

The RSL-RL command remains generic and fail-closed. It requires an explicit
`--env-id`; admission requires an active homogeneous registration and
compatible action/observation contracts. No new RSL training run is claimed,
and no replacement for the retired Go2 target is selected.
