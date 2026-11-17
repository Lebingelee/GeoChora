# Built-in tasks

**Import path**：`task_env.tasks`  
**任务域**：Task Semantics  
**稳定性**：Public API（env）/ Extension API（definition）  
**职责**：注册当前选定的 PickCube/NutAssembly reference routes，以及
Pendulum、双轮平衡车等通用任务环境。
**调用者/消费者**：`make_env`、Gym 使用者。  
**源码**：`tasks/pick_cube/`、`tasks/nut_assembly/`、`tasks/pendulum.py`、`tasks/two_wheel_balance.py`

## 从 UID 查询实际输入与结果

下例只构造一个 Nut scalar 环境；metadata 和 spaces 描述该实例，不能用它们代替其他任务的合同。`is_success` 是 Task 判断，`terminated`/`truncated` 是生命周期结果，普通动作不隐含 Solution 完成。

```python
import numpy as np
from task_env import make_env

env = make_env('nut-assembly-outcome-reference-v1', config={
    'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu', 'deployment': 'in_process'},
    'episode': {'horizon': 10},
})
try:
    obs, info = env.reset(seed=19)
    print(env.metadata['action_schema'], env.action_space, env.observation_space)
    pose = env.state.pose_world['panda-v1/ee']
    action = np.asarray([*pose.position, *pose.quaternion_wxyz, 1.], dtype=np.float64)
    obs, reward, terminated, truncated, info = env.step(action)
    print(info['is_success'], terminated, truncated)
finally:
    env.close()
```

7c002 已对该路线的相同动作合同做 MuJoCo CPU 有界运行和关闭；本代码块未单独执行。非法 UID、provider/profile 或 reset seed 按配置与 Task 合同拒绝，不自动替换其他任务。Pendulum/TwoWheel 是不同 action schema，不能套用八维 pose。

## Selected PickCube reference route

Public construction uses `make_env("pick-cube-p16-reference-v1", config=...)`.
The task-owned route is `PickCubeReferenceEnv` in `pick_cube/task.py` and uses
the canonical `TaskArtifact` identity
`pick-cube-v1/p1_6_experimental_100hz` (`fd5bc968…`). The task authoring package
also contains its artifact/reset/evaluation builder functions, but these are
not a second public environment factory.

This is the selected P1.6 `experimental_100hz` reference: 100 Hz control,
five 2 ms physics steps per control interval, absolute-pose expert actions,
and the measured 0.100 m lift predicate. The scalar route and separately declared device batches have bounded evidence; no policy-checkpoint inference or new P1.6 qualification is implied.

## Selected NutAssembly outcome reference route

Public construction uses `make_env("nut-assembly-outcome-reference-v1",
config=...)`. The registered class is `NutAssemblyReferenceEnv` in
`nut_assembly/task.py`; the task owns one selected guarded expert and
Outcome Completion V1. The ordinary example uses a caller-owned Solution and
`act → step(action) → observe`, with a source-bound action and five native
feedback samples. A legal ordinary world-pose action is admitted by the 7c002 implementation without an ExpertAction; its current evidence remains subject to independent review. Full MuJoCo Solution results for original and assembled Panda are recorded separately from ordinary actions; see the [7a acceptance](../../../../docs/module/task_env/v2.1.1/maintenance/reviews/20261117_g07a_attempt002_acceptance.md). Arbitrary inputs and untested provider combinations remain unsupported.

Its canonical artifact remains
`nut-assembly-square-v1/p1_8_e/nominal-v1` with identity
`99e374bd…`; the public environment UID and serialized TaskArtifact identity
are intentionally distinct. Task success is measured insertion AND release.
Outcome completion, readiness warnings, and the original strict Expert
lifecycle status remain separate. The bounded GeoPhys/MuJoCo route receipts do
not rewrite historical P1.8 FULL or D0-D2 results.

The selected task authoring API is task-owned. The public environment entry is
`make_env`; package-level construction helper exports are not uniform across
the two task packages and should be treated as an API compatibility decision,
not as interchangeable environment constructors.

## Generic Pendulum and TwoWheel tasks

`EmptyTaskEnv`, `PendulumEnv` and `TwoWheelBalanceEnv` have their own task
semantics. Empty has no task action dimensions; Pendulum and TwoWheel use one
and two torque inputs respectively. Pendulum and TwoWheel use their declared
Robot and Controller in the formal scalar environment. Their obsolete parallel
registrations have been retired; unified batch construction is deferred to G06.

## `PendulumEnv` and `PendulumTaskDefinition`

**Kind**：class / dataclass；**Defined in**：`tasks/pendulum.py`

Pendulum 是具有单铰链 Robot 的 TaskEnv。raw native action 为
`Dict({"torque": Box(shape=(1,), dtype=float32, low=-2.0, high=2.0)})`，对应树路径 `action/torque`，直接对应
`pendulum_torque` actuator。raw observation 为 `Dict({"state": Dict({"proprioception": Box(3)})})`，对应
`obs/state/proprioception`。它通过声明的 Robot、Controller 和共同控制提交链施加力矩；native action 的数值
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

### Batch capability

Pendulum 与 TwoWheel 的旧 parallel 注册及 component 工厂已退出；这两项目前不通过旧
`make_parallel_env` 路线创建。G06 将基于正式 Task／Robot／Controller 构建合同实现并验证并行能力。

## `TwoWheelBalanceEnv` and `TwoWheelBalanceTaskDefinition`

**Kind**：class / dataclass；**Defined in**：`tasks/two_wheel_balance.py`

双轮平衡车具有声明式 Robot，用于验证多 actuator native action。raw action 为
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

TwoWheel 的旧 `@register_parallel_env()` component 路线已退出；这里的 scalar 合同不证明当前
TwoWheel device batch 支持。G06 的有界 Pendulum/PickCube 证据也不能外推到 TwoWheel。

车体在 upright pitch/rate 与 wheel-rate 窗口内连续保持 10 个 control step 后 success；pitch 达到
`0.75 rad` 时产生 failure 并 `terminated`。horizon 只产生 `truncated`，不会被 generic action adapter 隐式
改变。两类 non-arm task 的 recorder 使用版本化 `universal_action/<component>`，组件由各自
`universal_action_schema` 声明，不写 Panda 专用的 `arm_joint_position/gripper` 布局。

[PickCube task](../../../tasks/pick_cube), [NutAssembly task](../../../tasks/nut_assembly), [Pendulum](../../../tasks/pendulum.py), and [TwoWheel](../../../tasks/two_wheel_balance.py) own their distinct task contracts.
