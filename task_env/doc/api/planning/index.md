# Task Planning

**Import path**：`task_env.planners` 与各任务自己的 Solution 模块
**任务域**：Task Planning  
**稳定性**：planner 公共契约和任务专属扩展；具体路线以任务声明为准
**职责**：通过公开 observation/info 生成 public action。  
**调用者/消费者**：用户脚本、selected 环境的 Solution/Expert 路线。
**源码**：`task_env/planners/`、`task_env/tasks/*/solution.py`

planners 是 task-agnostic action-sequence 生成器；task-owned solution 可以理解任务语义。二者均不可写 `ctrl`、`qpos`，不可访问 private runtime。

- [Public motion primitives](public_motion_primitives.md)
- [Task-owned solutions](task_owned_solutions.md)
