# Episode reset

**Import path**：`task_env.environment`  
**任务域**：Task Semantics  
**稳定性**：Public API / Extension API  
**职责**：描述 reset seed、初态及一次 episode 的公开状态。  
**调用者/消费者**：classic 和 selected 的 `reset()`、runtime boundary、task definition。
**源码**：`environment/env.py`、`environment/reference_env.py`、`environment/lifecycle.py`、任务 sampler。

classic `reset(*, seed=None, options=None)` 将 seed 交给 Gym 基类并由任务 sampler 使用；当前 scalar lifecycle 丢弃 options，`reset_parameters` 是 sampler 返回的 mapping，不保证为空。显式相同 seed 可用于任务定义的可复现 reset；省略或传 `None` 使用 Gym RNG 语义。每次新 episode 首次 `step()` 前应 reset。

selected `reset(*, seed=<省略>, options=None)` 优先使用配置的 episode seed；省略和显式 `None` 的含义不同。Nut 的有界路线使用固定 seed 19，不能由此推断其他任务的随机初态。Task 的 sampler 按自己的合同生成 ResetSample，记录实际采样信息和 resolved config，不手工捏造 reset 身份。普通路线拒绝不支持的 options；声明 reset-scoped Controller selection 的 physical 路线可在 `options['controller']` 选择受支持候选，其他路线不能据此推断支持切换。Position 候选 seed 须匹配其固定 ResetPlan，mixed-control 的 `reset_plan_v1` 经单独验证。

## 什么时候失效

reset 建立新 episode 和采样身份，可能重新物化 provider session；状态视图、动作绑定、Solution proposal 和场景载荷 context 必须按各自合同重新取得。普通 reset 恢复当前声明的 Controller、参数与绑定；显式选择是另一个经过准入的 reset 操作，不表示任意 Controller 切换矩阵已通过。故障后的 step 会拒绝，直到允许的 reset 成功完成；reset 失败本身不能当成恢复。调用者持有 Solution 时，`reset_for_solution(solution, seed=...)` 校验其 source／配置后绑定该实例，随后使用 `step_with_solution(solution)`；普通 action 和该 Solution 不能在同 episode 混用。

```python
import numpy as np
from task_env import make_env

env = make_env('pick-cube-p16-reference-v1', config={
    'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu', 'deployment': 'in_process'},
    'episode': {'horizon': 10},
})
try:
    obs, info = env.reset(seed=31)
    pose = env.state.pose_world['panda-v1/ee']
    action = np.asarray([*pose.position, *pose.quaternion_wxyz, 1.], dtype=np.float64)
    obs, reward, terminated, truncated, info = env.step(action)
    obs, info = env.reset(seed=31)  # discard the preceding episode's identities
finally:
    env.close()
```

本例说明 scalar 生命周期，本轮尚未单独运行；受测路线及默认 Controller 以[版本 API](../../../../docs/module/task_env/v2.1.1/api/README.md)为准。device batch 的 `reset(..., mask=...)` 和 same-step autoreset 是单独的批量合同：部分 reset 只重置选中行，终止帧与 reset 帧不能混为同一观测。旧 SB3 adapter 对 coordinated device same-step 明确拒绝，不应再执行一次手动重置。相关代码路径见 [Task environment](task_environment.md) 和 [learner integrations](../appendix/learner_integrations.md)。

`InitialStateSpec(joint_positions=(), notes=())` 是命名初态描述，不含 solver 地址。`EpisodePhysicsState(qpos, qvel, qacc, ctrl, act)` 是 classic runtime 初态 contract；具体 task 的 sampler 和 selected ResetSample 属于各自 owner，不是用户需要直接操作的 solver API。
