# Built-in tasks

**Import path**：`task_env.tasks`  
**任务域**：Task Semantics  
**稳定性**：Public API（env）/ Extension API（definition）  
**职责**：提供内置 PickCube、NutAssembly、Pendulum 与双轮平衡车环境。
**调用者/消费者**：`make_env`、Gym 使用者。  
**源码**：`tasks/pick_cube/`、`tasks/nut_assembly/`、`tasks/pendulum.py`、`tasks/two_wheel_balance.py`

## `PickCubeEnv` and `PickCubeTaskDefinition`

**Kind**：class / dataclass；**Defined in**：`pick_cube/task.py`

`PickCubeEnv` 是 `BaseTaskEnv` 子类。`PickCubeTaskDefinition(references, success_definition=...)` 需要 `panda-v1` 与 `cube-v1` 引用；其 evaluate 使用 end-effector/cube snapshot、gripper opening 计算 reward、lift success。缺少所需 `site_xpos` 或 `body_xpos` 会抛 `ValueError`。

## `NutAssemblyEnv` and `NutAssemblyTaskDefinition`

**Kind**：class / dataclass；**Defined in**：`nut_assembly/task.py`

definition 需要 `panda-v1` 与 `square-nut-v1` 引用，并验证传入 `success_definition` 等于其版本常量；不匹配抛 `ValueError`，缺引用抛 `KeyError`。奖励、success/failure 只能通过 `TaskEvaluation` 进入 env lifecycle。

## `PendulumEnv` and `PendulumTaskDefinition`

**Kind**：class / dataclass；**Defined in**：`tasks/pendulum.py`

Pendulum 是无 robot agent 的单铰链 TaskEnv。raw native action 为
`Dict({"torque": Box(shape=(1,), dtype=float32, low=-2.0, high=2.0)})`，对应树路径 `action/torque`，直接对应
`pendulum_torque` actuator。raw observation 为 `Dict({"state": Dict({"proprioception": Box(3)})})`，对应
`obs/state/proprioception`。它通过 `PendulumTorqueActionAdapter` 接入中性 action seam；native action 的数值
同时作为该 task family 的 generic `universal_action`，不伪装成 Panda 八维 schema。

state-only observation 的 leaf schema 是 `task-env-pendulum-state-v1`，leaf shape 为 `(3,)`，严格顺序为
`[cos(theta), sin(theta), theta_dot]`，dtype 为 `float32`，其中 `theta=0` 表示 upright。reset 使用
`pendulum_uniform_angle_velocity_v1`，固定 seed 会重现 angle 与 angular velocity。

其 `action_schema` 显式声明 `kind=direct_torque`、`shape=(1,)`、`dtype=float32`、逐分量 bounds、单位、
actuator interpretation、task family 和 schema version；对应 reference profile 会随 Gym metadata 与 H5
`meta/env_meta` 保存。

`PendulumTaskDefinition` 在 upright angle/rate 窗口连续保持 5 个 control step 后 success；Pendulum 不定义
fall failure，未成功 episode 由 horizon 产生 `truncated`。reward 由 upright、angular-velocity cost、torque
cost 和 success term 组成。固定 action sequence 的物理语义由同一 inline MJCF 的 MuJoCo reference smoke 对照。

### Pendulum optional batch capability

Pendulum 与 TwoWheel 都同时注册在 `ENV_REGISTRY` 与 `PARALLEL_ENV_REGISTRY`。Pendulum 的 single 路径仍为
`make_env("pendulum-v1") -> BaseTaskEnv -> PendulumTaskDefinition`；parallel 路径为
`make_parallel_env("pendulum-v1") -> HomogeneousVectorTaskEnv -> BatchTaskLifecycleAdapter ->
environment.TaskLifecycleAdapter`。
两条路径共享 `PendulumTaskSemantics` 的 observation leaf 顺序、reward terms、success window、horizon、reset
采样和 action bounds。当前 Pendulum batch 由 `SceneBatchRuntime` 提供 `BatchState`、`BatchDiagnostics`、
`BatchResetResult` 和 `BatchStepResult`；`PendulumBatchRuntime` 仅保留旧导入兼容名，上层不解释 kernel 或
positional readback。当前在同一个 `BatchRuntimeProtocol` 下提供可配置的
`StaticTemplateBatchRuntime` 首个 `hinge_or_slide_no_contact_v1` profile；它只对满足该能力的拓扑启用，
不引入 Pendulum-specific factory 分支，unsupported topology 会由公共 factory 明确拒绝。

batch task 的公共任务语义由 `environment.TaskLifecycleAdapter` 与其 batch runtime 子适配器共同处理；task
definition 只提供统一 `TaskStateView` 上的 reset/evaluate、observation projection 与 action semantics。
controller 选择仍属于公共 configuration、`BaseTaskEnv` 与
robot/controller 层，不成为 task-specific batch hook。

PickCube、NutAssembly、Tabletop scene 以及尚无 batch backend 的其他 task 不会通过 parallel factory 创建；它们继续
使用 single `make_env`/scene composition contract。

## `TwoWheelBalanceEnv` and `TwoWheelBalanceTaskDefinition`

**Kind**：class / dataclass；**Defined in**：`tasks/two_wheel_balance.py`

双轮平衡车同样不拥有 robot agent，但用于验证多 actuator native action。raw action 为
`Dict({"torque": Box(shape=(2,), dtype=float32, low=-1.5, high=1.5)})`，对应树路径 `action/torque`，组件顺序
固定为 `left_wheel_torque, right_wheel_torque`，单位为 `N*m`；adapter 只写入对应的左右 wheel actuator，并
把完整两维 native vector 作为该 task family 的 generic `universal_action`。

其 `action_schema` 显式声明 `kind=direct_wheel_torque`、`shape=(2,)`、`dtype=float32`、左右轮逐分量 bounds、
单位、actuator interpretation、task family 和 schema version；对应 reference profile 同样随 Gym metadata
与 H5 `meta/env_meta` 保存。

state-only observation 的 leaf schema 是 `task-env-two-wheel-balance-state-v1`，leaf shape 为 `(7,)`，对应
`obs/state/proprioception`，顺序为
`[sin(pitch), cos(pitch), pitch_rate, left_wheel_position, right_wheel_position,
left_wheel_rate, right_wheel_rate]`，dtype 为 `float32`。reset 使用
`two_wheel_balance_uniform_perturbation_v1`，固定 seed 会重现车体姿态、轮位置和速度扰动。

TwoWheel 也通过 `@register_parallel_env()` 获得 generic `SceneBatchRuntime` 并行路径；single/B=1 共享同一
TaskDefinition 语义，B=2/4 的 slot isolation 与 masked reset 由框架 lifecycle 负责。

车体在 upright pitch/rate 与 wheel-rate 窗口内连续保持 10 个 control step 后 success；pitch 达到
`0.75 rad` 时产生 failure 并 `terminated`。horizon 只产生 `truncated`，不会被 generic action adapter 隐式
改变。两类 non-arm task 的 recorder 使用版本化 `universal_action/<component>`，组件由各自
`universal_action_schema` 声明，不写 Panda 专用的 `arm_joint_position/gripper` 布局。
