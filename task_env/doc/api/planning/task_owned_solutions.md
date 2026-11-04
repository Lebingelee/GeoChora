# Task-owned solutions

**Import path**：`task_env.planners`、`task_env.tasks.pick_cube.solution`、`task_env.tasks.nut_assembly.solution`
**任务域**：Task Planning  
**稳定性**：planner 公共契约；Solution 为任务专属扩展
**职责**：以公开 observation、info 和 metadata 实现任务相关策略。  
**调用者/消费者**：selected 环境、使用对应任务契约的调用者。
**源码**：`planners/contracts.py`、`tasks/*/solution.py`

## `ExpertAction` and `TaskExpertSolver`

**Kind**：frozen dataclass / Protocol；**Stability**：Public API / Extension API；**Defined in**：`planners/contracts.py`

`from task_env.planners import ExpertAction, TaskExpertSolver`。`ExpertAction(action, stage, done=False, failed=False, diagnostics=<空映射>, control_request=None, request_boundary=None, solution_identity=None)` 将 action 复制为只读 float32 一维数组；提供 `control_request` 时须符合 `ArmTargetExecutionRequestV1`，提供 `solution_identity` 时须为非空字符串。`TaskExpertSolver` 声明 `stage`、`done`、`failed` 属性及 `reset(observation, info)`、`act(observation, info)`、`observe(observation, reward, terminated, truncated, info)`。具体任务可要求额外的 readiness 或 metadata；该 Protocol 不拥有 env/runtime。

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
        action = solution.act(obs, info)  # ExpertAction：动作、控制请求、Solution身份及来源边界
        obs, reward, terminated, truncated, info = env.step(action)
        solution.observe(obs, reward, terminated, truncated, info)
        if terminated or truncated:
            break
finally:
    env.close()
```

`ExpertAction` 携带绝对位姿、版本化 arm 执行请求和动作前来源边界；Env 校验边界后执行并在 `info` 发布包含五个 native 样本的 interval receipt。`observe()` 从公开 `info` 解析并校验完整 receipt、readiness、控制应用及其请求动作／阶段／模式与本次待执行计划的一致性；若调用方在 `act()` 后替换动作，该检查在物理推进后失败，调用方须将该次执行视为失败。旧显式反馈参数仍兼容。普通裸数组仍拒绝，过期边界、缺失控制请求和错误或缺失Solution身份在推进前拒绝，不能将此路线推广为任意外部动作。调用方负责 Solution 完成/失败和异常处理；不同模式不能混用。

PickCube scalar CPU 的 Solution 也返回 `ExpertAction`，调用方可将其直接交给 `env.step(action)`；阶段和readiness记录随动作保留。Solution 从公开 `info` 读取并校验执行反馈，旧的显式 `execution_info` 参数仍兼容。Nut 的控制请求／来源边界仍为必需；PickCube 不接受控制请求字段；调用方驱动动作携带声明的Solution身份和动作前来源边界，Env在推进前与任务配置和当前边界核对。该身份是完整性校验，不是调用者身份认证。两条调用方驱动路径有禁止引擎导入的合成测试，当前源码完整物理回归仍待验证。PickCube Position/F06 的调用方动作也会转换为既有结构化控制请求，并校验当前状态边界与Solution身份；该接线仅有合成验证，真实Isaac未运行。通用candidate oracle及feasibility入口也改为调用方驱动；旧 `step_expert()` 方法仍是受限兼容，不作为这些入口的回退。示例：[PickCube](../../../../examples/tasks/pick_cube.py)、[NutAssembly](../../../../examples/tasks/nut_assembly.py)、[录制](../../../../examples/recording/record_expert.py)。
