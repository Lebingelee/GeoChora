# Task Planning

**Import path**：`task_env.planners`、`task_env.solutions`  
**任务域**：Task Planning  
**稳定性**：Public API / Extension API  
**职责**：通过公开 observation/info 生成 public action。  
**调用者/消费者**：用户脚本、`env.step()`。  
**源码**：`task_env/planners/`、`solutions/`、`tasks/*/solution.py`

planners 是 task-agnostic action-sequence 生成器；task-owned solution 可以理解任务语义。二者均不可写 `ctrl`、`qpos`，不可访问 private runtime。

- [Public motion primitives](public_motion_primitives.md)
- [Task-owned solutions](task_owned_solutions.md)
