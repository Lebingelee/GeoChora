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
