# Task definition

**Import path**：`task_env.environment.TaskDefinition`、`task_env.TaskEvaluation`  
**任务域**：Task Semantics  
**稳定性**：Extension API / Public API  
**职责**：基于 snapshot 给出奖励、成功、失败和指标。  
**调用者/消费者**：`BaseTaskEnv.reset()`、`step()`、info、recorder。  
**源码**：`environment/protocols.py`、`types.py`

## `TaskDefinition`

**Kind**：Protocol；**Stability**：Extension API；**Defined in**：`environment/protocols.py`

旧协议支持 `reset(snapshot)` 与 `evaluate(previous_snapshot, action, current_snapshot)`；当前 `TaskDefinitionBase` 也支持声明 `uses_unified_state_view=True`，使用 `TaskStateView`、reset mask 与当前／先前 state 执行 scalar 或旧 batch 语义。具体方法签名以 [`task_definition.py`](../../../environment/task_definition.py) 和 Pendulum/TwoWheel 实现为准。selected binding 使用 task-owned evaluator，不应假定所有 task 已通过同一扩展点。任务消费公开状态，不访问 solver/runtime 私有布局。

## `TaskEvaluation`

**Kind**：frozen dataclass；**Stability**：Public API；**Defined in**：`environment/types.py`

签名：`TaskEvaluation(reward: float, success: bool, failure: bool = False, metrics: Mapping[str, float | bool] = {}, reward_terms: Mapping[str, float] = {})`。构造时数值/布尔值规范化，两个 mapping 变为只读。classic 的终止还受 task termination policy 与 `ignore_done` 控制；selected 的任务和 Solution 可能分开报告物理成功、失败、Expert 完成与 horizon 截断，不能用单一布尔值替代。
