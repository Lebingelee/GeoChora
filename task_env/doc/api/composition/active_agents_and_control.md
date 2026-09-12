# Active agents and control

**Import path**：`task_env.robots`、`task_env.controllers`  
**任务域**：Task Composition  
**稳定性**：Public API / Extension API  
**职责**：声明 active agent，并把 public action 转为 `ControlCommand`。  
**调用者/消费者**：`BaseTaskEnv.step()`、`RuntimeBoundary.apply_control()`。  
**源码**：`task_env/robots/`、`controllers/`

## `task_env.robots.BaseAgent` / `PandaAgent`

**Kind**：class；**Stability**：Extension API / Public API；**Defined in**：`robots/base.py`、`panda.py`

`BaseAgent` 实现 `AgentComponent`；子类必须提供 `asset_manifest()`、`reference_spec()`、`initial_state_spec()`、`supported_action_modes()`。`PandaAgent` 是内置实现，编译后的 ID 位于 `TaskReferences.agents`。`PANDA_ASSET_ROOT` 是资产根路径常量。

## `task_env.environment.ActionAdapter`

**Kind**：Protocol；**Stability**：Extension API；**Defined in**：`environment/protocols.py`

公开成员为 `action_space`、`reset(snapshot)` 和 `convert(action, snapshot) -> ControlCommand`。它是纯 CPU 边界；`DeltaPoseActionAdapter`、`CartesianPoseActionAdapter`、`AbsoluteJointPositionActionAdapter` 是 Panda 的公开 action-mode 实现。`JointPositionServoBackend`、`Controller`、`JointTarget`、`PoseTarget`、`ActuatorCommand` 是同一控制 contract。不可把输出 actuator `ctrl` 当成 public action。

## `task_env.robots.PandaGripperController`

**Kind**：class；**Stability**：Public API；**Defined in**：`robots/gripper.py`

构造签名：`PandaGripperController(*, references: AgentReferences, config: ActionConfig, force_limit_N=None)`。默认 TaskEnv 配置通过 `robot.gripper` 选择 `kind` 及参数；省略时使用 `experimental_rate_limited` 与默认参数。`force_limit_N` 是唯一的夹持力状态，同时约束位置控制与 runtime actuator `forcerange`；运行时可用 `set_force_limit_N()` 临时调整。`set_force()` 和 `force_N` 仅保留兼容别名。实验控制器还提供 `set_opening_step_m()`、`set_force_deadband_N()`、`set_force_adjust_step_m()`。`move_gripper_m(value=0.0, force=None)` 与 `normalized_target(command)` 返回 `GripperTarget`；传入兼容的 `force` 参数也会更新同一个 `force_limit_N`。`ctrl_for_target(target, ctrl)` 生成控制数组。它由 adapter 使用。
