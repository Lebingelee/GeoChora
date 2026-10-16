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
| `stage_a_runtime_profile`、`stage17_performance_profile`、`stage18_bridge_benchmark` 不传 `--task-uid` | 三个通用 runtime diagnostics 现在要求明确 task UID；旧 Go2 默认调用已退休。 |
| `stage_b_torch_reference`、`stage_g_contact_precision`、`stage19d_cuda_graph_*`、`stage_p_topology_candidate_benchmark`、`stage_f_cuda_graph_lifecycle` | 这些历史诊断依赖 Go2/static profile fixture，已在核对实际调用后移除；其历史 Evidence 保持不变，S4 不得依赖这些入口充当当前通用 Static Physics 回归 fixture。 |

Selected active task UIDs remain `pick-cube-p16-reference-v1` and `nut-assembly-outcome-reference-v1`. They are single-environment task routes and are not substituted as PPO targets by this retirement.
