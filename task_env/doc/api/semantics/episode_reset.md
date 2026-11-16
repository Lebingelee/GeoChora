# Episode reset

**Import path**：`task_env.environment`  
**任务域**：Task Semantics  
**稳定性**：Public API / Extension API  
**职责**：描述 reset seed、初态及一次 episode 的公开状态。  
**调用者/消费者**：classic 和 selected 的 `reset()`、runtime boundary、task definition。
**源码**：`environment/env.py`、`environment/reference_env.py`、`environment/lifecycle.py`、任务 sampler。

classic `reset(*, seed=None, options=None)` 将 seed 交给 Gym 基类并由任务 sampler 使用；当前 scalar lifecycle 丢弃 options，`reset_parameters` 是 sampler 返回的 mapping，不保证为空。显式相同 seed 可用于任务定义的可复现 reset；省略或传 `None` 使用 Gym RNG 语义。每次新 episode 首次 `step()` 前应 reset。

普通 selected `reset(*, seed=<省略>, options=None)` 省略 seed 时使用 19，显式 `None` 不等于省略；普通路线拒绝非空 options。Position 候选 seed 须匹配其固定 ResetPlan，mixed-control 的 `reset_plan_v1` 经单独验证。记录实际采样信息和 resolved config，而不应手工捏造 reset 身份。相关代码路径见 [Task environment](task_environment.md)。

`InitialStateSpec(joint_positions=(), notes=())` 是命名初态描述，不含 solver 地址。`EpisodePhysicsState(qpos, qvel, qacc, ctrl, act)` 是 classic runtime 初态 contract；具体 task 的 sampler 和 selected ResetSample 属于各自 owner，不是用户需要直接操作的 solver API。
