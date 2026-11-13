# TaskEnv API examples

The repository-root [developer workflow guide](../../../../examples/README.md)
is the command index for current scalar tasks, expert recording, H5
inspection, batch smoke, learning smoke, and the bounded rendering route.
Examples call existing public APIs; they do not define another TaskEnv,
TaskArtifact, recorder, or renderer contract.

The following commands are examples, not validation of the latest source in
this maintenance attempt. Run from the repository root in a prepared GeoChora
dependency environment; the [installation and startup guide](../../../../docs/module/task_env/v2.1.1/guides/installation-and-start.md)
states checked paths and remaining installation gaps:

```bash
PYTHONPATH=GeoPhys/src:. python examples/tasks/pick_cube.py --provider mujoco --seed 31
PYTHONPATH=GeoPhys/src:. python examples/tasks/nut_assembly.py --provider geophys --seed 19
```

The historical v1.1.0 `single_inline` Pendulum route was reported to fail during stepping because its helper reads
`env.binding`, which generic Pendulum does not expose. This maintenance attempt has not rerun that historical command. Use the public construction example below;
[canonical troubleshooting](../../../../docs/module/task_env/v2.0.0/guides/troubleshooting.md#已复现的-cli-缺陷) records the reproducer.

## Current commands

| Goal | Command | Boundary |
| --- | --- | --- |
| Scalar task construction | `examples/tasks/pick_cube.py` or `examples/tasks/nut_assembly.py` | Public `task_env.make_env`; explicit provider; selected task-owned expert. |
| Canonical recording | `examples/recording/record_expert.py --env-id <selected-uid> --provider <geophys\|mujoco> --output <fresh.h5>` | Existing task-owned recorder and canonical H5. |
| Offline H5 inspection | `examples/recording/inspect_h5.py --input <recording.h5>` | Canonical schema/hash/projection and T+1 validation; not D0 replay. |
| Batch environment | `task_env.script.env.parallel_inline` | Four formal task UIDs reject formal batch before resource allocation; component batch retains its own scope. G06 remains open. |
| SB3 example | `examples/learning/pendulum_sb3.py --output-dir <fresh-dir>` | Depends on a supported batch route; the formal Pendulum adapter remains unavailable. No training claim. |
| Rendering examples | `examples/rendering/pendulum_single_rgb.py`, `examples/rendering/pendulum_parallel_rgb.py` | Scalar Pendulum rendering is the current route; the historical parallel example awaits G06 integration. |
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

The NutAssembly and PickCube examples use caller-owned
`act → step(action) → observe`. This public pattern has been run on PickCube Isaac CUDA; runtime and recording were valid while task and Solution failed, as recorded in the [U3 evidence](../../../../docs/module/task_env/v2.1.1/maintenance/reviews/20261113_e11_e16_u3_solution_evidence.md). The generic candidate Harness also requires a caller-driven Solution action
route; unsupported legacy routes fail explicitly. NutAssembly does not admit arbitrary ordinary external actions. A successful physical task outcome, a completed
expert lifecycle, and a finalized recording are reported separately.

## Batch and learning boundary

`make_parallel_env` retains supported component paths. The formal `pendulum-v1`,
`two-wheel-balance-v1`, PickCube and NutAssembly UIDs do not yet have formal
batch adapters and are rejected before workers or native resources are created.
The SB3 adapter owns flattening at the learner boundary. RSL-RL remains a
generic, fail-closed CLI and requires an explicit `--env-id`; neither selected
manipulation UID is made a default PPO target. Importability does not qualify training.

## Rendering and Camera limits

`CameraSpec`, camera observation, UI rendering, the Renderer Registry, Flora,
and rasterizer contracts remain distinct APIs. Historical bounded native rendering
examples covered Pendulum × GeoPhys CPU × scalar TaskEnv × rasterizer RGB and
Pendulum × GeoPhys CPU × merged-scene batch × rasterizer RGB; they were not rerun in this attempt. These historical routes do not establish arbitrary
Flora or Physics × Renderer interoperation. The old PickCube camera scripts are
retired; the current scalar example uses public `make_env`. Selected task RGB
and the GeoPhys physics × MuJoCo renderer-only pairing have separately bounded
evidence in the [current state](../../../../docs/module/task_env/v2.1.1/maintenance/current-state.md).
See [trajectory and camera notes](trajectory_and_camera.md)
and the [migration table](../appendix/migration.md).
