# Active agents and control

**Import path**：`task_env.robots`、`task_env.controllers`
**任务域**：Task Composition
**稳定性**：Robot 声明与公共构造入口为公开或扩展接口；具体 Controller/provider 组合按版本矩阵限定。
**职责**：Robot 声明组件、frame、joint、传动和能力；Controller 将被准入的动作解释为可提交的控制目标。
**调用者/消费者**：Task builder、source composer、环境控制生命周期、runtime 和 recorder。
**源码**：`task_env/robots/`、`controllers/`

## 当前 selected 路线

Task 的正式配置经 `make_env` 选择 Robot 和 Controller。Robot 提供 source recipe、具名资源与默认 Controller 声明；默认对象在绑定前不能被当成可执行的 native 转发器。共同 builder 将 Task source 与 Robot recipe 组合，公共绑定核对 Controller 输入／输出、资源、单位和传动，再将它绑定到实际 source；`RobotRuntime` 反映这个已绑定主体。显式选定的受支持 Controller 不应被默认值替换。普通 reset 按声明重建或恢复；显式切换仅限已声明并受测的路线。

下例通过公开入口提交一个世界坐标 pose：前三项为米，后四项为 `wxyz` 四元数，最后为夹爪标量；具体合法范围与行为以 Task 的 action schema 及 Controller 为准。采样当前 TCP 后改变 1 mm 是小的非零命令，不保证任务成功。

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
    action[0] += .001
    obs, reward, terminated, truncated, info = env.step(action)
finally:
    env.close()
```

本页示例形式对应本轮 PickCube MuJoCo 单步验证，具体配置、R1／R1_split／R3 约束、模型需求和可切换范围以[版本 API](../../../../docs/module/task_env/v2.1.1/api/README.md)及[Controller 指南](../../../../docs/module/task_env/v2.1.1/guides/custom-controllers.md)为准；不把一个受测 profile 推广到任意 Robot。错误 shape、非有限值和无效姿态应在提交前拒绝。action、Controller 目标、实际 ACK 与物理响应是不同证据；每次 reset 后重新取得受代次限制的绑定。

下面的 classic adapter 与 gripper 类型保留其各自兼容范围，不等价于 selected 的唯一控制入口。

## `task_env.robots.BaseAgent` / `PandaAgent`

**Kind**：class；**Stability**：Extension API / Public API；**Defined in**：`robots/base.py`、`panda.py`

`BaseAgent` 是 `AgentComponent` 的兼容别名；组件须提供 `asset_manifest()`、`reference_spec()`、`initial_state_spec()`、`supported_action_modes()`。`PandaAgent` 是内置实现，编译后的 ID 位于 `TaskReferences.agents`。`PANDA_ASSET_ROOT` 是资产根路径常量。

## `task_env.environment.ActionAdapter`

**Kind**：Protocol；**Stability**：Extension API；**Defined in**：`environment/protocols.py`

公开成员为 `action_space`、`reset(snapshot)` 和 `convert(action, snapshot) -> ControlCommand`。它是纯 CPU 边界；`DeltaPoseActionAdapter`、`CartesianPoseActionAdapter`、`AbsoluteJointPositionActionAdapter` 是 Panda 的公开 action-mode 实现。`JointPositionServoBackend`、`Controller`、`JointTarget`、`PoseTarget`、`ActuatorCommand` 是同一控制 contract。不可把输出 actuator `ctrl` 当成 public action。

## `task_env.robots.PandaGripperController`

**Kind**：class；**Stability**：Public API；**Defined in**：`robots/gripper.py`

构造签名：`PandaGripperController(*, references: AgentReferences, config: ActionConfig, force_limit_N=None)`。默认 TaskEnv 配置通过 `robot.gripper` 选择 `kind` 及参数；省略时使用 `experimental_rate_limited` 与默认参数。`force_limit_N` 是唯一的夹持力状态，同时约束位置控制与 runtime actuator `forcerange`；运行时可用 `set_force_limit_N()` 临时调整。`set_force()` 和 `force_N` 仅保留兼容别名。实验控制器还提供 `set_opening_step_m()`、`set_force_deadband_N()`、`set_force_adjust_step_m()`。`move_gripper_m(value=0.0, force=None)` 与 `normalized_target(command)` 返回 `GripperTarget`；传入兼容的 `force` 参数也会更新同一个 `force_limit_N`。`ctrl_for_target(target, ctrl)` 生成控制数组。它由 adapter 使用。
