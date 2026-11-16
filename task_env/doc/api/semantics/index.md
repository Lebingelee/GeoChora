# Task Semantics

**Import path**：`task_env.tasks`、`task_env.environment`  
**任务域**：Task Semantics  
**稳定性**：Public API / Extension API  
**职责**：把同一组物理元素定义为明确任务并运行 Gym lifecycle。  
**调用者/消费者**：Gym 用户、task implementer、recorder。  
**源码**：`task_env/environment/env.py`、`task_env/environment/reference_env.py`、`tasks/`

- [Task environment](task_environment.md)
- [Task definition](task_definition.md)
- [Episode reset](episode_reset.md)
- [Built-in tasks](built_in_tasks.md)

`reward`、`success`、`failure` 由任务语义决定；终止、截断还取决于任务路线、episode 策略和 horizon，不能把 success 一律等同于 `terminated`。标准方向是外部 Solution 产生 action 并交给 `env.step(action)`；当前部分 selected 任务还保留 `step_expert()` 和 `step_with_solution()` 受限过渡路线，不能将其当成标准 API。任务和调用者不直接推进 runtime。
