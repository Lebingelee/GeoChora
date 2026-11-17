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

## 从规划到执行

公共运动原语根据给定目标和时间参数生成参考序列；task-owned Solution 将观测、阶段和反馈解释为下一次动作。caller 的常见时序为 `reset → solution.reset → act → env.step → observe`，并由调用者处理完成、失败和关闭；普通动作也可直接走受支持的 Controller 输入。planner 计算本身不推进物理，输出只有在相应 Task/Controller 准入后才进入共同提交。

参考序列是否遍历完、事件驱动策略是否 done、Task predicate 是否成功分别记录。带来源的 ExpertAction 必须匹配动作前边界，普通动作没有 Solution 身份；不要通过 planner 写原生 ctrl/qpos，也不要把某一个 Panda pose schema 推到所有 Robot。先读[原语](public_motion_primitives.md)，再读[任务 Solution](task_owned_solutions.md)。
