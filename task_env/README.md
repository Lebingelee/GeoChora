# TaskEnv Core

当前模块使用与能力治理入口：[TaskEnv canonical docs](../docs/module/task_env/README.md)。符号级细节继续在 API reference 维护。

`task_env/` owns GeoChora's public task/environment lifecycle, task-owned
reference implementations, controller and observation contracts, generic
parallel execution adapters, recording, learning boundaries, and renderer
contracts. Provider-private solver state remains behind provider adapters.

The repository has no root packaging metadata. From the repository root, use
the GeoChora dependency environment and set `PYTHONPATH`:

```bash
PYTHONPATH=GeoPhys/src:. python examples/tasks/pick_cube.py \
  --provider mujoco --seed 31

PYTHONPATH=GeoPhys/src:. python examples/tasks/nut_assembly.py \
  --provider geophys --seed 19
```

The current selected manipulation UIDs are
`pick-cube-p16-reference-v1` and `nut-assembly-outcome-reference-v1`.
Construct them through `from task_env import make_env`; NutAssembly advances
only through its guarded `step_expert()` route. Task success and expert
lifecycle completion remain separate.

## Current developer workflows

| Workflow | Entry point | Boundary |
| --- | --- | --- |
| Scalar environment | Public `task_env.make_env` | Pendulum reset/step; `single_inline` currently fails with `env.binding` AttributeError. See canonical troubleshooting. |
| Generic batch environment | `task_env.script.env.parallel_inline` | Public `make_parallel_env`, explicit CPU supported smoke on Pendulum/`merged_scene`. |
| Selected task expert | `examples/tasks/pick_cube.py`, `examples/tasks/nut_assembly.py` | Selected task-owned experts, explicit provider, bounded CPU run. |
| Canonical recording | `examples/recording/record_expert.py` | Existing recorder/H5 schema, selected expert, nonzero on incomplete result. |
| Offline H5 inspection | `examples/recording/inspect_h5.py` | Canonical reader integrity and T+1 check; not replay or D0. |
| SB3 smoke | `examples/learning/pendulum_sb3.py` | One update through the existing Pendulum runner; not convergence evidence. |
| Native renderer smoke | `examples/rendering/pendulum_single_rgb.py`, `examples/rendering/pendulum_parallel_rgb.py` | Scalar and `merged_scene` batch Pendulum frames, GeoPhys CPU, rasterizer RGB. |
| Advanced parallel renderer | `task_env.script.render_parallel` | Same narrow route; other providers, Flora, and headed UI are not established. |
| Window input probe | `task_env.script.render_input_probe` | Taichi Forge keyboard/window probe without a TaskEnv. |

See [root examples](../examples/README.md) for exact commands, output paths,
resource notes, and evidence limits. Linux examples use per-process
`RLIMIT_AS` virtual-address-space limits; these are not RSS or aggregate
process-tree memory caps.

## Parallel and learner boundaries

`make_parallel_env` is optional and only admits tasks with explicit
homogeneous registrations. The current TaskEnv batch physics layout is
`merged_scene`. The retired `static_template` layout fails closed; it is not
redirected. `GeoPhysRigidBatchRuntime` remains a GeoPhys-owned adapter with its
existing capability limits and is not a registered TaskEnv batch factory
route.

SB3 flattening remains at `SB3FlattenVecWrapper`; RSL-RL remains generic and
requires an explicit `--env-id` plus active batch and learner-contract
admission. PickCube and NutAssembly are not implicit PPO targets. Go2-specific
task, robot, profile, and training routes are retired from current develop;
historical recovery is through immutable `v1.0.0`.

## Rendering and Camera boundaries

Camera observations and UI frame presentation are separate contracts.
`CameraSpec`, the Camera APIs, Renderer Registry, Flora, and rasterizer
implementations remain available within their declared support. Current
bounded native rendering evidence covers Pendulum × GeoPhys CPU × scalar
TaskEnv × rasterizer RGB and Pendulum × GeoPhys CPU × `merged_scene` batch ×
rasterizer RGB. No selected manipulation task × Flora route or Physics ×
Renderer interoperability is claimed.

`task_env.script.render_single` returns an explicit retired-route error because
it used a historical task factory; current scalar Pendulum rendering is shown
in `examples/rendering/pendulum_single_rgb.py`. `task_env.script.camera.static`,
`task_env.script.camera.bound`, and `task_env.script.camera_lighting_probe`
also fail explicitly because they depended on historical PickCube construction
or renderer internals. Their original source identities and caller dispositions
are recorded in the S4.5-B recovery manifest.

## Trajectory utilities

Use `task_env.script.trajectory.record` or the root `record_expert.py` example
for selected expert recording. `convert` remains an offline Panda/controller
action conversion route. `replay` requires explicit `--historical` for legacy
H5 replay; selected-source reexecution and offline H5 inspection are separate
operations. H5 roundtrip does not establish D0 reconstruction.

The [API example index](doc/api/examples/index.md) and
[migration notes](doc/api/appendix/migration.md) describe current routes and
retired APIs. Historical release documentation and Evidence remain unchanged.
