# Task definition

**Import path**：`task_env.environment.TaskDefinition`、`task_env.TaskEvaluation`  
**任务域**：Task Semantics  
**稳定性**：Extension API / Public API  
**职责**：基于 snapshot 给出奖励、成功、失败和指标。  
**调用者/消费者**：`BaseTaskEnv.reset()`、`step()`、info、recorder。  
**源码**：`environment/protocols.py`、`types.py`

## `TaskDefinition`

**Kind**：Protocol；**Stability**：Extension API；**Defined in**：`environment/protocols.py`

旧协议支持 `reset(snapshot)` 与 `evaluate(previous_snapshot, action, current_snapshot)`。`TaskDefinitionBase` 的 unified 调用使用 `reset(state=..., reset_mask=...)` 和 `evaluate(state=..., action=..., elapsed_steps=..., previous_state=...)`；由 `TaskLifecycleAdapter` 调用，任务只拥有语义。具体签名见 [`task_definition.py`](../../../environment/task_definition.py)。

`as_task_state_view` 保留两种公开表示：`RuntimeSnapshot`／旧 batch arrays 使用原 `TaskStateView`；`CanonicalStateView` 使用 `CanonicalTaskStateView`，其 `canonical_state` 引用同一具名状态，`batch_size=1`、`is_batch=False`，不制造 qpos、body/site 索引或另一个物理状态 owner。Task 仍须声明所消费的格式，具名 scalar 支持不授予 batch 能力。

正式 PickCube（含物理配置）、NutAssembly、Pendulum、双轮车均在共同 Env 中以本次 Artifact 构造 TaskDefinition，并在 reset 重建后重新绑定；正式 observation 调用同一语义 lifecycle。PickCube 组件模式继续消费原 compiled references 和数组，保留其旧 scalar/batch admission；Panda 的 canonical evaluator 保留 Python tuple／scalar 计算顺序。高级中性 Position 与 mixed 诊断仍可显式使用其既有 binding evaluator，不能据此声称所有 diagnostic caller 已迁移。任务消费公开状态，不访问 solver/runtime 私有布局。

## `TaskEvaluation`

**Kind**：frozen dataclass；**Stability**：Public API；**Defined in**：`environment/types.py`

签名：`TaskEvaluation(reward: float, success: bool, failure: bool = False, metrics: Mapping[str, float | bool] = {}, reward_terms: Mapping[str, float] = {})`。构造时数值/布尔值规范化，两个 mapping 变为只读。classic 的终止还受 task termination policy 与 `ignore_done` 控制；selected 的任务和 Solution 可能分开报告物理成功、失败、Expert 完成与 horizon 截断，不能用单一布尔值替代。

公共 Gym info 继续保留 `ObservationSchema` 与只读 TaskEvaluation mappings。框架在 Solution 的 reset／act／observe callback 边界通过 metadata owner 投影为值 payload；不删除字段，不改变数值或 Solution 的 finite／identity／clock 检查。需要施加 Solution action 时使用正式 `reset_for_solution`／`step_with_solution` 链。
