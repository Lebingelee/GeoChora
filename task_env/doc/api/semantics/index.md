# Task Semantics

**Import path**：`task_env.tasks`、`task_env.environment`  
**任务域**：Task Semantics  
**稳定性**：Public API / Extension API  
**职责**：把同一组物理元素定义为明确任务并运行 Gym lifecycle。  
**调用者/消费者**：Gym 用户、task implementer、recorder。  
**源码**：`task_env/environment/env.py`、`tasks/`

- [Task environment](task_environment.md)
- [Task definition](task_definition.md)
- [Episode reset](episode_reset.md)
- [Built-in tasks](built_in_tasks.md)

`reward`、`success`、`failure` 由任务语义决定；终止、截断还取决于任务路线、episode 策略和 horizon，不能把 success 一律等同于 `terminated`。普通动作通过 `env.step()`，受支持的 task-owned Solution 通过 `step_expert()` 或 `step_with_solution()`；任务和调用者不直接推进 runtime。
