# TaskEnv API examples

The repository-root [developer workflow guide](../../../../examples/README.md)
is the command index for current scalar tasks, expert recording, H5
inspection, batch smoke, learning smoke, and the bounded rendering route.
Examples call existing public APIs; they do not define another TaskEnv,
TaskArtifact, recorder, or renderer contract.

Run from the repository root in the GeoChora dependency environment:

```bash
PYTHONPATH=GeoPhys/src:. python -m task_env.script.env.single_inline --env-id pendulum-v1 --backend cpu --steps 1
PYTHONPATH=GeoPhys/src:. python -m task_env.script.env.parallel_inline --env-id pendulum-v1 --backend cpu --num-env 2 --steps 1
PYTHONPATH=GeoPhys/src:. python examples/tasks/pick_cube.py --provider mujoco --seed 31
PYTHONPATH=GeoPhys/src:. python examples/tasks/nut_assembly.py --provider geophys --seed 19
```

## Current commands

| Goal | Command | Boundary |
| --- | --- | --- |
| Scalar task construction | `examples/tasks/pick_cube.py` or `examples/tasks/nut_assembly.py` | Public `task_env.make_env`; explicit provider; selected task-owned expert. |
| Canonical recording | `examples/recording/record_expert.py --env-id <selected-uid> --provider <geophys\|mujoco> --output <fresh.h5>` | Existing task-owned recorder and canonical H5. |
| Offline H5 inspection | `examples/recording/inspect_h5.py --input <recording.h5>` | Canonical schema/hash/projection and T+1 validation; not D0 replay. |
| Batch environment | `task_env.script.env.parallel_inline` | Generic Pendulum `make_parallel_env` route; current bounded CPU smoke only. |
| SB3 example | `examples/learning/pendulum_sb3.py --output-dir <fresh-dir>` | One update through the existing Pendulum PPO runner; no convergence claim. |
| Rendering examples | `examples/rendering/pendulum_single_rgb.py`, `examples/rendering/pendulum_parallel_rgb.py` | Bounded Pendulum × GeoPhys CPU × rasterizer RGB smokes through scalar `make_env` and merged-scene batch routes. |
| Offline trajectory conversion | `task_env.script.trajectory.convert` | Existing Panda/controller action conversion contract. |
| Historical H5 replay | `task_env.script.trajectory.replay --historical ...` | Recovery-only route; not selected-source acceptance or D0 by default. |

The selected public manipulation UIDs are `pick-cube-p16-reference-v1` and
`nut-assembly-outcome-reference-v1`. Historical `pick-cube-v1` and
`nut-assembly-square-v1` identifiers are not redirected.

## Public construction API

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

Selected PickCube and NutAssembly routes use task-owned `step_expert()` and
their current public provider configuration. NutAssembly does not admit
arbitrary external actions. A successful physical task outcome, a completed
expert lifecycle, and a finalized recording are reported separately.

## Batch and learning boundary

```python
from task_env import make_parallel_env

env = make_parallel_env(
    "pendulum-v1", {"base_seed": 73}, num_env=2, backend="cpu", execution="remote"
)
try:
    observation = env.reset()
    # Raw batch observations retain their structured tree and batch-first shape.
finally:
    env.close()
```

The SB3 adapter owns flattening at the learner boundary. RSL-RL remains a
generic, fail-closed CLI and requires an explicit `--env-id`; neither selected
manipulation UID is made a default PPO target. Importability and a one-update
smoke do not qualify training.

## Rendering and Camera limits

`CameraSpec`, camera observation, UI rendering, the Renderer Registry, Flora,
and rasterizer contracts remain distinct APIs. The bounded native rendering
examples cover Pendulum × GeoPhys CPU × scalar TaskEnv × rasterizer RGB and
Pendulum × GeoPhys CPU × merged-scene batch × rasterizer RGB. They do not test
Flora or any Physics × Renderer interoperation. The old single-task CLI and
PickCube camera scripts are retired; the current scalar example uses public
`make_env`, while selected reference tasks have no camera acceptance claim.
See [trajectory and camera notes](trajectory_and_camera.md)
and the [migration table](../appendix/migration.md).
