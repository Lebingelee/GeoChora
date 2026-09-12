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

`reward`、`success`、`failure` 属于 task definition。success/failure 决定 `terminated`；episode horizon 决定 `truncated`。任务实现或 solution 不得绕过 `env.step()` 推进 runtime。
