# Task-owned solutions

**Import path**：`task_env.planners`、`task_env.tasks.pick_cube.solution`、`task_env.tasks.nut_assembly.solution`
**任务域**：Task Planning  
**稳定性**：planner 公共契约；Solution 为任务专属扩展
**职责**：以公开 observation、info 和 metadata 实现任务相关策略。  
**调用者/消费者**：selected 环境、使用对应任务契约的调用者。
**源码**：`planners/contracts.py`、`tasks/*/solution.py`

## `ExpertAction` and `TaskExpertSolver`

**Kind**：frozen dataclass / Protocol；**Stability**：Public API / Extension API；**Defined in**：`planners/contracts.py`

`from task_env.planners import ExpertAction, TaskExpertSolver`。`ExpertAction(action, stage, done=False, failed=False, diagnostics=<空映射>, control_request=None, request_boundary=None)` 将 action 复制为只读 float32 一维数组；提供 `control_request` 时须符合 `ArmTargetExecutionRequestV1`。`TaskExpertSolver` 声明 `stage`、`done`、`failed` 属性及 `reset(observation, info)`、`act(observation, info)`、`observe(observation, reward, terminated, truncated, info)`。具体任务可要求额外的 readiness 或 metadata；该 Protocol 不拥有 env/runtime。

## Selected 任务的 Solution

PickCube 的 `PickCubeReadinessSolution` 和 NutAssembly 的 `NutAssemblyOutcomeSolutionV1` 属于各自任务模块；它们的配置、readiness 与完成条件并不通用。

外部 Solution 根据 observation/privileged state 推理动作，调用方执行 `env.step(action)`。`step_expert()` **不是标准 Env API**；`step_with_solution()` 仍由 Env 调用 Solution，只保留为受限兼容。

NutAssembly 的普通 scalar CPU 路线现在可由调用方驱动：

```python
from task_env import make_env
from task_env.tasks.nut_assembly import build_outcome_solution

env = make_env("nut-assembly-outcome-reference-v1",
               config={"provider": "mujoco", "backend": "cpu", "horizon": 6000})
solution = build_outcome_solution(provider="mujoco")
try:
    obs, info = env.reset(seed=19)
    solution.reset(obs, info, env.metadata)
    while not solution.done and not solution.failed:
        action = solution.act(obs, info)  # ExpertAction：动作、控制请求及来源边界
        obs, reward, terminated, truncated, info = env.step(action)
        solution.observe(obs, reward, terminated, truncated, info)
        if terminated or truncated:
            break
finally:
    env.close()
```

`ExpertAction` 携带绝对位姿、版本化 arm 执行请求和动作前来源边界；Env 校验边界后执行并在 `info` 发布包含五个 native 样本的 interval receipt。`observe()` 从公开 `info` 解析并校验完整 receipt 和 readiness，旧显式参数仍兼容。普通裸数组仍拒绝，过期边界和缺失控制请求在推进前拒绝，不能将此路线推广为任意外部动作。调用方负责 Solution 完成/失败和异常处理；不同模式不能混用。

PickCube scalar CPU 的 Solution 当前返回同一 `ExpertAction`，但 `env.step(proposal.action)` 接收其中的数组，`reset`/`observe` 另需 `env.expert_execution_info()`。这两个调用方驱动路径有禁止 native import 的合成测试；新 Nut 路径的完整真实物理成功及新源码记录仍待验证，旧成功参考不能代替该证据。Position 候选及其他任务不由这些结果推及。示例：[NutAssembly](../../../../examples/tasks/nut_assembly.py)、[录制](../../../../examples/recording/record_expert.py)。
