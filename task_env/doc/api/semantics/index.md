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

## 从声明到结果

TaskArtifact 固定实体、语义、初态与时基，TaskDefinition/sampler 定义如何从公开状态计算 reward、success、failure 和 metrics；环境统一执行 reset、action、step、observation 和 close，runtime 拥有真实物理推进。Task 不直接改 provider 的 native state。阅读顺序为环境生命周期 → 任务声明/评价 → reset 身份 → 内置任务。

同一 transition 的动作来源、Task success、Solution done/failed、计划轨迹完成及记录有效性是独立事实。普通 action 可以得到 task success，也不因此成为 Solution 完成；已声明 Solution identity 不证明本次动作来自该 Solution。source、episode 或 reset 改变后旧 proposal 失效，错误的来源不应降级为普通数组。
