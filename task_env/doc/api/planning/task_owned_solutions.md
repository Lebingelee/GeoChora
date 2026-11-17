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
               config={"execution": {"physics_provider": "mujoco", "physics_backend": "cpu"},
                       "episode": {"horizon": 6000}})
try:
    solution = build_outcome_solution(provider="mujoco")
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

`ExpertAction` 携带绝对位姿、版本化 arm 执行请求和动作前来源边界；Env 校验边界后执行并在 `info` 发布包含五个 native 样本的 interval receipt。`observe()` 从公开 `info` 解析并校验完整 receipt、readiness、控制应用及其请求动作／阶段／模式与本次待执行计划的一致性；若调用方在 `act()` 后替换动作，该检查在物理推进后失败，调用方须将该次执行视为失败。旧显式反馈参数仍兼容。合法普通 pose 数组通过独立准入；过期边界、缺失控制请求和错误或缺失 Solution 身份的 proposal 在推进前拒绝，不能将此路线推广为任意外部动作。调用方负责 Solution 完成/失败和异常处理；不同模式不能混用。

上述示例是普通 MuJoCo scalar CPU 路线。历史 R05b 专属构造和 Solution 入口已退休；其原有证据保留为历史记录。当前任务通过正式配置构造，并按所选路线的实际证据判断支持范围。

PickCube Solution 也返回 `ExpertAction`，调用方可将其直接交给 `env.step(action)`；阶段和 readiness 记录随动作保留。Solution 从公开 `info` 读取并校验执行反馈，旧的显式 `execution_info` 参数仍兼容。Nut 的控制请求／来源边界仍为必需；PickCube 不接受控制请求字段；调用方驱动动作携带声明的 Solution 身份和动作前来源边界，Env 在推进前与任务配置和当前边界核对。该身份是完整性校验，不是调用者身份认证。在 `5a04140a` 的历史 CPU 代表回归见[验证记录](../../../../docs/module/task_env/v2.1.1/maintenance/reviews/20261105_pre_stage3_resumed_physical_checks.md)。

当前接收口径（2026-11-14）：[U3 原运行](../../../../docs/module/task_env/v2.1.1/maintenance/reviews/20261113_e11_e16_u3_solution_evidence.md)中的 Isaac 失败保留；后续 `solution-002` 已在自己的冻结身份下完成任务和 Solution。四条 CPU 及这条 Isaac 完整单seed运行通过[同次联合证据](../../../../docs/module/task_env/v2.1.1/maintenance/reviews/20261113_e11_e16_u4_joint_completion.md)有界接收；CPU canonical H5 没有 completion 字段，Isaac v3为null，由同次caller、监督和独立读回联合证明，不能称H5单文件自含。各路线不是同一最新HEAD重跑，也不构成G07三seed矩阵。通用candidate oracle及feasibility入口同样由调用方驱动；旧 `step_expert()` 不作为回退。示例：[PickCube](../../../../examples/tasks/pick_cube.py)、[NutAssembly](../../../../examples/tasks/nut_assembly.py)、[录制](../../../../examples/recording/record_expert.py)。
