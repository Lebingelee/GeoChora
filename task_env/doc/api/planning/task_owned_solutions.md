# Task-owned solutions

**Import path**：`task_env.planners`、`task_env.tasks.pick_cube.solution`、`task_env.tasks.nut_assembly.solution`
**任务域**：Task Planning  
**稳定性**：planner 公共契约；Solution 为任务专属扩展
**职责**：以公开 observation、info 和 metadata 实现任务相关策略。  
**调用者/消费者**：selected 环境、使用对应任务契约的调用者。
**源码**：`planners/contracts.py`、`tasks/*/solution.py`

## `ExpertAction` and `TaskExpertSolver`

**Kind**：frozen dataclass / Protocol；**Stability**：Public API / Extension API；**Defined in**：`planners/contracts.py`

`from task_env.planners import ExpertAction, TaskExpertSolver`。`ExpertAction(action, stage, done=False, failed=False, diagnostics=<空映射>, control_request=None)` 将 action 复制为只读 float32 一维数组；提供 `control_request` 时须符合 `ArmTargetExecutionRequestV1`。`TaskExpertSolver` 声明 `stage`、`done`、`failed` 属性及 `reset(observation, info)`、`act(observation, info)`、`observe(observation, reward, terminated, truncated, info)`。具体任务可要求额外的 readiness 或 metadata；该 Protocol 不拥有 env/runtime。

## Selected 任务的 Solution

PickCube 的 `PickCubeReadinessSolution` 和 NutAssembly 的 `NutAssemblyOutcomeSolutionV1` 属于各自任务模块；它们的配置、readiness 与完成条件并不通用。

规范方向是外部 Solution 从 observation/privileged state 推理动作，再由调用方交给 `env.step(action)`；`step_expert()` **不是标准 Env API**。当前 PickCube/NutAssembly 的旧 Expert 路线尚未完成这种迁移：为保留已验证行为，现有 [Expert 录制示例](../../../../examples/recording/record_expert.py) 仍使用受限兼容方法 `step_expert()`。

当前还有部分任务和配置支持调用方持有 Solution，经 `reset_for_solution(solution, ...)` 和 `step_with_solution(solution)` 执行；后者由 Env 调用该 Solution 的 `act`/`observe`，所以也是受限的过渡接线，并不等于外部独立 `act → env.step(action)` 已对所有任务实现。NutAssembly 当前拒绝未受保护的普通外部 action，不能删去其 guard、readiness 或 native feedback 来强行迁移；不同执行模式不能在同一 episode 混用。具体状态见[当前环境接口](../semantics/task_environment.md)与 [Phase C 契约](../../../../docs/module/task_env/v2.0.0/goals/phase_ii/03_Phase_C_Execution_Lifecycle.md)。

PickCube 当前的普通 scalar CPU absolute-pose 路线也允许调用方独立持有 `build_readiness_solution()` 产生的 Solution，用 `env.reset()` 后的 observation、info、metadata 和 `env.expert_execution_info()` 初始化；调用方再依次执行 `solution.act(...)`、`env.step(proposal.action)`、`solution.observe(..., execution_info=env.expert_execution_info())`。这条直接 action 路线已有禁止 native import 的单 transition 合成检查；本次未完成真实物理全程外部循环或其录制验收，不能据此推广到 Position 候选或 NutAssembly。当前兼容示例和冻结成功记录仍使用旧 Expert 路线。
