# Task definition

**Import path**：`task_env.environment.TaskDefinition`、`task_env.TaskEvaluation`  
**任务域**：Task Semantics  
**稳定性**：Extension API / Public API  
**职责**：基于 snapshot 给出奖励、成功、失败和指标。  
**调用者/消费者**：`BaseTaskEnv.reset()`、`step()`、info、recorder。  
**源码**：`environment/protocols.py`、`types.py`

## `TaskDefinition`

**Kind**：Protocol；**Stability**：Extension API；**Defined in**：`environment/protocols.py`

必须实现 `reset(snapshot: RuntimeSnapshot) -> TaskEvaluation` 与 `evaluate(previous_snapshot, action, current_snapshot) -> TaskEvaluation`。仅消费 `RuntimeSnapshot`，不可访问 solver/runtime。

## `TaskEvaluation`

**Kind**：frozen dataclass；**Stability**：Public API；**Defined in**：`environment/types.py`

签名：`TaskEvaluation(reward: float, success: bool, failure: bool = False, metrics: Mapping[str, float | bool] = {}, reward_terms: Mapping[str, float] = {})`。构造时数值/布尔值规范化，两个 mapping 变为只读。`success` 或 `failure` 在 `ignore_done=False` 时令 `terminated=True`；horizon 只影响 `truncated`。
