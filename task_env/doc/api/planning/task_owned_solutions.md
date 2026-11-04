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

对内置 selected Expert，使用公共 `make_env` 构造任务，`env.reset(seed=...)` 后调用 `env.step_expert()`；该路径负责 proposal、执行和 observe，返回 observation、reward、terminated、truncated、info。NutAssembly 不接受未受保护的外部 action，因此不能把其 proposal 简化为直接 `env.step(action)`。调用方拥有的 Solution 仅在任务支持并验证时使用 `reset_for_solution(solution, ...)` 和 `step_with_solution(solution)`；不能在同一 episode 混用外部 action 与 Solution。完整循环和关闭方式见 [Expert 录制示例](../../../../examples/recording/record_expert.py) 与[当前环境接口](../semantics/task_environment.md)。
