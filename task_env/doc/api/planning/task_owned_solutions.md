# Task-owned solutions

**Import path**：`task_env.solutions`、`task_env.tasks.pick_cube`、`task_env.tasks.nut_assembly`  
**任务域**：Task Planning  
**稳定性**：Extension API / Public API  
**职责**：以公开 observation、info 和 metadata 实现任务相关策略。  
**调用者/消费者**：用户脚本。  
**源码**：`solutions/base.py`、`tasks/*/solution.py`

## `ExpertAction` and `TaskExpertSolver`

**Kind**：frozen dataclass / Protocol；**Stability**：Public API / Extension API；**Defined in**：`solutions/base.py`

`ExpertAction(action, stage, done=False, failed=False, diagnostics={})` 将 action 复制为 readonly float32 一维数组。`TaskExpertSolver` 要求 `stage`、`done`、`failed` 属性及 `reset(observation, info)`、`act(observation, info)`、`observe(observation, reward, terminated, truncated, info)`。它不拥有 env/runtime。

## `PickCubeSolution` / `NutAssemblySolution`

**Kind**：class；**Stability**：Public API；**Defined in**：`tasks/pick_cube/solution.py`、`tasks/nut_assembly/solution.py`

两者分别具有 task-owned config 和状态机，提出 `ExpertAction`，使用者必须将 `.action` 交给 `env.step()` 后以返回五元组调用 `observe()`。需要 action schema 的实现会在 `reset(observation, info, metadata)` 中验证 controller contract。
