# Migration

**Import path**：不适用  
**任务域**：Appendix  
**稳定性**：Public API migration note  
**职责**：集中说明已移除旧路径。  
**调用者/消费者**：从旧 TaskEnv 导入迁移的用户。  
**源码**：`task_env/__init__.py` 与各 package `__init__.py`

| 旧路径 | canonical import |
| --- | --- |
| `task_env.action` | `task_env.controllers` |
| `task_env.agents` | `task_env.robots` |
| `task_env.core` | `task_env.environment` / `task_env.assembly` |
| `task_env.scene`、`task_env.scenes` | `task_env.worlds`、`task_env.assembly` |
| `task_env.observation` | `task_env.observations` |
| `task_env.planning` | `task_env.planners` |
| `task_env.recording` | `task_env.recorders` |
| `task_env.rendering` | `task_env.renderers` |
| `task_env.experts` | `task_env.solutions` |
| `task_env.utils` | 按实际公开子包替换 |

以上旧路径不保留 compatibility shim。迁移时使用顶层 `task_env.__all__` 或目标子包 `__all__` 核验导入名。

## P2.0-B S3：Go2 retirement

Go2 专用 task/robot/RSL 与诊断入口已从当前 develop 移除。v1.0.0 是其历史源代码与冻结 Evidence 的恢复点；当前 Core 不把旧名称静默重定向到其他任务。

| 旧 UID、模块或调用 | 当前行为与迁移 |
| --- | --- |
| `go2-walk-v1`、`go2-walk-deploy-v1`、`go2-walk-deploy-height-v1`、`go2-walk-codex` | `make_env` 显式报 retired UID；无替代任务。历史运行需恢复 `v1.0.0`。 |
| `go2-v1` | `make_agent` 显式报 retired UID；无机器人替代。 |
| `task_env.tasks.go2_walk*`、`task_env.robots.go2`、`task_env.diagnostics.go2`、`task_env.script.rl.go2` | 当前模块已移除且无兼容导入。历史代码和诊断可从 `v1.0.0` 恢复。 |
| `task_env.flora_go2_assets`、`task_env.tasks.go2_walk.flora_assets`、Go2 Flora diagnostic/smoke imports | Go2 资产适配与诊断已移除；通用 `task_env.render.flora` renderer 和 public render-description lowering 保留。 |
| `unitree_go2_reference`、`unitree_go2_debug` learner profile | 当前 profile 已移除；RSL 默认 action transform 仍使用任务公开 action space，不提供 Go2 的 ±100 native action 语义。 |
| `task_env.script.rl.rsl_ppo` 无 `--env-id` | 现在 CLI 要求显式 `--env-id`。Go2 UID 及旧 `go2_walk*` aliases 显式报 retired；其他 task 仍须有 parallel registration 与兼容的 learner contracts。 |
| `stage17_performance_profile` 不传 `--task-uid` | Stage 17 要求显式 task UID；S4 已集成并仅保留 `merged_scene`，`--layout static_template` 会明确报错。 |
| `stage_a_runtime_profile`、`stage18_bridge_benchmark`、`stage_g_contact_precision_gate` | S4 中这些静态模板专用诊断模块已移除；历史 Evidence 与资格结论不变。 |
| `stage_b_torch_reference`、`stage_g_contact_precision`、`stage19d_cuda_graph_*`、`stage_p_topology_candidate_benchmark`、`stage_f_cuda_graph_lifecycle` | 这些历史诊断依赖 Go2/static profile fixture，已在核对实际调用后移除；其历史 Evidence 保持不变。 |

Selected active task UIDs remain `pick-cube-p16-reference-v1` and `nut-assembly-outcome-reference-v1`. They are single-environment task routes and are not substituted as PPO targets by this retirement.

## P2.0-B S4.5-A: selected task workflows (local review candidate)

The S4.5-A candidate adds runnable root examples under `examples/` using
`from task_env import make_env`. Selected current commands use only
`pick-cube-p16-reference-v1` or `nut-assembly-outcome-reference-v1`, explicit
GeoPhys/MuJoCo providers, and CPU. NutAssembly must advance through guarded
`step_expert()`; no external gripper action route is added. Recording continues
to use the task-owned canonical recorder and existing H5 schema. The storage
reader checks H5 validity and `T+1` boundaries, but does not reconstruct D0.

| Retired path or command | Current behavior and migration |
| --- | --- |
| `task_env.script.stage11` and `task_env.script.stage11_socket` | Entry points return an explicit retirement error. Restore their recorded source commit or immutable `v1.0.0` in a separate historical checkout. |
| `task_env.diagnostics.phase1.nutassembly_recovery.historical` | Legacy TaskEnv/provider-private recovery route is explicitly retired. Restore its exact source recovery ref for historical diagnostics; current execution uses the selected NutAssembly UID through `make_env`. |
| `task_env.script.trajectory._task_plans` and its `_build_plan`, `_historical_build_plan`, `_pick_cube_config`, `_nut_assembly_config` helpers | Retired. Use the selected public UID with `make_env`; no old task ID is redirected. |
| `task_env.script.trajectory.commands collect` and `--historical-grouped` | Grouped Stage 14/Phase I collection is retired. Use `task_env.script.trajectory.record` or `examples/recording/record_expert.py` for one current selected route. |
| `task_env.script.recorder._pick_cube_config`, `_nut_assembly_config`, `_build_plan`, `_look_at_quat` | Removed from the compatibility command module. `task_env.script.recorder` now delegates only to selected expert recording. |
| `task_env.script.trajectory._nut_assembly_config` and `_pick_cube_config` package exports | Removed; task-owned configuration is selected by its Task Artifact and not reconstructed by a script helper. |
| `task_env.script.trajectory.planning.*` selected routes | Kept and now construct through `make_env`; NutAssembly calls only `step_expert()`. |
| `task_env.script.env.single_*` and `parallel_*` | Kept. The single examples use public `make_env`; parallel examples remain generic registered batch workflows. |
| `task_env.script.trajectory.convert` and `replay` | Kept as offline utilities. Historical H5 replay still requires explicit `--historical`; selected same-source reexecution remains a separate path. |

Exact pre-change source blobs, SHA-256 values, and recovery refs are recorded in
[`p2_0_s4_5_a_source_recovery.json`](../../../../docs/module/task_env/p2_0_s4_5_a_source_recovery.json).
The S4.5-A code and examples remain local review candidates; they do not alter
frozen release documents or qualification labels. The S4 implementation was
subsequently integrated into public `develop` at
`0ff2d846a36c7014d2b40a530f52d99e64266ff9` by normal fast-forward.

## P2.0-B S4.5-B: learning and rendering workflow consolidation (local candidate)

The S4.5-B candidate adds a one-update Pendulum SB3 wrapper over the existing
`task_env.script.rl.pendulum_ppo` runner, an offline canonical H5 inspector,
and bounded scalar and batch Pendulum/GeoPhys CPU/rasterizer RGB examples. The
learning smoke checks runner wiring only. The rendering smokes do not test
Flora or Physics × Renderer interoperability. RSL-RL stays generic and
requires an explicit `--env-id`; no Go2 replacement or manipulation PPO target
is added.

| Retired or retained entry point | Current behavior and migration |
| --- | --- |
| `task_env.script.render_single` | Explicit retired-route error; it depended on historical task construction. Use `examples/rendering/pendulum_single_rgb.py` for the bounded current scalar Pendulum route or `examples/rendering/pendulum_parallel_rgb.py` for the bounded batch route; selected manipulation renderer support is not claimed. |
| `task_env.script.camera.static`, `task_env.script.camera.bound`, and `task_env.script.camera_lighting_probe` | Explicit retired-route errors; these used the historical PickCube task, and the lighting probe read provider-private renderer state. `CameraSpec` and Camera contracts remain. |
| `task_env.script.camera._common` | Removed; only the retired camera scripts called it. Exact source is recoverable from the S4.5-B base commit in the recovery manifest. |
| `task_env.script.render_parallel` | Retained as an advanced Pendulum-only batch rendering entry point. The bounded smoke covers GeoPhys CPU, `merged_scene`, rasterizer, RGB-array mode, one world and one step. Other renderers/providers and headed UI are unverified. |
| `task_env.script.render_input_probe` | Retained as a standalone Taichi Forge window-input probe. It does not construct a TaskEnv or establish a rendering capability. |
| `task_env.script.trajectory.convert`, `replay`, and `merge` | Retained as generic offline utilities; historical replay remains explicit and separate from canonical H5 inspection and selected-source reexecution. |

The S4.5-B source-recovery manifest records each retired script path,
pre-change SHA-256, Git blob, invocation identity, caller disposition, and
replacement boundary. Use the repository-root
[`examples/README.md`](../../../../examples/README.md) for current commands.
This local candidate does not alter frozen release documents or qualification
labels.

## P2.0-B S4: static-template retirement (integrated)

S4 was integrated into public `develop` at
`0ff2d846a36c7014d2b40a530f52d99e64266ff9` by normal fast-forward from
`5b8c901135e624a248cf73d29be9a6fea70feb2b`. It removes
`task_env.runtime.providers.static`, the `task_env.runtime.static_*`
compatibility modules, and the public `StaticTemplate*` configuration/runtime
exports. `runtime.batch_physics_layout=static_template` and explicit public
`runtime.static_template.*` configuration now fail with migration guidance.
`RuntimeConfig` retains the default-only static config value to preserve
unrelated scalar Task config identities; non-default direct values are rejected.
No request is redirected to `merged_scene`.

The `pendulum_ppo` `--batch-physics-layout static_template` and
`--static-template-profile` options, and Stage 17's `--layout static_template`,
fail explicitly. The Stage A profile, Stage G precision gate, and Stage 18
static bridge module paths are retired. Use `merged_scene` for the supported
TaskEnv batch factory. `GeoPhysRigidBatchRuntime` remains an adapter with its
prior capability limits and is not a `make_parallel_env` route. Release-level
compatibility policy remains subject to v1.0.1 review.
