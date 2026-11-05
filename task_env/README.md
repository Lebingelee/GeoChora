# TaskEnv Core

当前模块使用与能力治理入口：[TaskEnv canonical docs](../docs/module/task_env/README.md)。符号级细节继续在 API reference 维护。

开发中 v2.1.1 的[安装与启动指南](../docs/module/task_env/v2.1.1/guides/installation-and-start.md)说明新克隆、复用已有路径与轻量入口；[自定义任务指南](doc/自定义任务构建指南.md)对应可运行示例和 Solution 接口，并标明尚未验证的组合。[阶段3前维护](../docs/module/task_env/v2.1.1/planning/pre-stage3-environment-refactor.md)仍未完成；统一Env的并行适配待阶段6，本次Pendulum以单环境迁移和验证为范围。旧batch入口及历史证据不代表新路线已完成适配。

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
Construct them through `from task_env import make_env`. The NutAssembly and
PickCube examples use a caller-owned Solution and `act → step(action) → observe`.
The separate advanced R05b profile below uses a bounded caller-owned Solution
route, which still invokes that Solution through the Env and is transitional.
Task success and Expert lifecycle completion remain separate.

An advanced bounded GeoPhys native-feedback profile is available through
`NutAssemblyReferenceEnv.for_native_feedback_profile(backend="cpu"|"cuda",
gripper_control_hz=100|500)`; it uses the selected NutAssembly source and
normal Core admission with a versioned source-closure receipt. R05b attempt001
completed focused provider-free S1 plus two-outer CPU and CUDA native S2 with
independent H5 readback, pending Sol review. This does not qualify the full
100/500 Hz campaign, task/Expert completion, other sources or Providers, or
Formal Qualification. See the [R05 execution record](../docs/module/task_env/v2.1.0/history/phase_ii_01/05_R05_Native_Rate_Feedback.md#r05b-attempt001-execution-result-2026-10-29) and [public API contract](../docs/module/task_env/v2.1.0/api/public-api.md).

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
