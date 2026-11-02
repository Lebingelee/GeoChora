# Quickstart

This short scalar example constructs through the public factory, resets, steps once, and closes. It does not start a manipulation task or establish a provider qualification.

```python
from task_env import make_env

env = make_env("pendulum-v1", config={"runtime": {"backend": "cpu"}})
try:
    observation, info = env.reset(seed=73)
    action = env.action_space.sample()
    observation, reward, terminated, truncated, info = env.step(action)
finally:
    env.close()
```

Run from the repository root in an environment installed per [installation](installation.md), with `PYTHONPATH=GeoPhys/src:.`. Check the returned termination/truncation and task-specific outcome fields; do not assume one step is task completion.

## Record an explicit reference episode

For the current PickCube expert-recording path, use the repository CLI and a fresh output location:

```bash
PYTHONPATH=GeoPhys/src:. python examples/recording/record_expert.py \
  --env-id pick-cube-p16-reference-v1 --provider mujoco --seed 31 \
  --output workspace/examples/pickcube-mujoco.h5
PYTHONPATH=GeoPhys/src:. python examples/recording/inspect_h5.py \
  --input workspace/examples/pickcube-mujoco.h5
```

The recorder uses the selected task/provider route and preserves its resolved configuration and provenance. The independent reader checks H5 structure and T/T+1 boundaries. A storage/readback pass is not replay validity, Expert completion, task success, a Judge decision, or Qualification. If the output already exists, choose a new path rather than overwriting evidence.

Expert execution is explicit and task-specific. For guarded NutAssembly progression, use the task's `step_expert()` route and its documented horizon; do not infer a general expert API from the scalar `step()` example.
