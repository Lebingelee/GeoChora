# 从现有 Controller 抽象实现自己的控制器

本页是**独立章**。它只描述仓库现有两条真实合同，不发明 `BaseController`、`register_controller`、全局 manager，也不建议通过未声明的 config 字段把 Controller 对象塞进 Env。

> **验证口径（2026-11-17）**：以下签名/类型按 `task_env/controllers/contracts.py`、`task_env/controllers/canonical/*`、`task_env/runtime/sessions/physical_control.py` 静态核对；本页的算法示例是**普通扩展代码**，本轮没有运行 native。

## C1 先选择当前存在的扩展合同

### 合同 A：旧 one-tick Protocol

`task_env.controllers.contracts.Controller` 是 **`typing.Protocol`**，不是需要继承的 ABC：

```python
class Controller(Protocol):
    @property
    def action_space(self) -> Any: ...
    def reset(self, snapshot: RuntimeSnapshot) -> None: ...
    def convert(self, action: np.ndarray, snapshot: RuntimeSnapshot) -> ControlCommand: ...
```

- 消费者：旧 component/legacy adapter 路径（例如 `RobotControllerHandle` 包装的 `convert`）。
- 它返回 `ControlCommand`，是冻结的旧 `env.step(action)` 边界类型。
- 它**不能直接接**当前 selected 的 typed physical 路线；不要因为名字叫 `Controller` 就把它塞进 selected Task。

### 合同 B：当前 selected typed physical Controller

当前 selected 的 typed 路线不使用上面的 `convert`。真实实例采用：

```text
controller.compute(action, state, context) -> PhysicalCommandBatchV1
controller.reset_from_realized_state(state)
controller.action_space            # 可选：Gymnasium Dict/Box
controller.identity                # profile+binding(+model) 的摘要
```

真实消费者/实现：

| 实现 | 文件 | 用途 |
| --- | --- | --- |
| `DirectJointEffortControllerV1` | `task_env/controllers/canonical/physical_controller.py` | 具名关节 bounded torque 的一对一映射 |
| `LinearEffortControllerV1` | 同上 | 线性 action→effort + 纯模型 bias；`zero_bias` 是零偏置起点 |
| `WrenchControllerV1` | 同上 | 6 维 body wrench（力+矩） |
| `OperationalSpaceEffortControllerV1` | `task_env/controllers/canonical/operational_space_effort.py` | world TCP pose → 7 维 effort；需要模型 |
| `DefaultCanonicalController` | `task_env/controllers/canonical/default_identity.py` | 初始 unbound 的默认恒等绑定 |

共同限制：

- source 身份、binding、writer、单位、channel 顺序、effort 范围、context/boundary/clock 必须匹配；
- Controller 只做**纯计算**；不推进物理、不直接写 native 数组、不读 provider 私有状态；
- ACK 不是力测量；真实响应必须从公共 state/feedback 读。

推荐顺序：**先复用已有 Controller/profile；确实不够时再做小扩展**。扩展代码放在你自己的 Task/Asset 包里，只有可复用 Core 行为才进 `task_env`。

## C2 先复用：默认恒等与已有 profile

`DefaultCanonicalController` 的构造/绑定：

```python
from task_env.controllers.canonical.default_identity import DefaultCanonicalController

default = DefaultCanonicalController()
default.bind(
    subject,                 # ControlledSubjectV1（真实声明的 subject）
    binding,                 # PhysicalControlBindingV1（同 source/Scene/Artifact）
    writer_id="my-writer",   # subject.controller_writers 中真实声明的 writer
    units=("N*m",) * len(subject.channel_paths),
    action_key="torque",
)
```

`bind` 的真实行为（源码）：

- 拒绝已经 bound 的实例；
- subject 必须是 `ControlledSubjectV1`；
- 委托 `bind_subject_direct_effort_controller(subject, binding, writer_id, units, action_key)`；
- 该函数按 subject 的 `channel_paths` 找到唯一 channel，并检查 writer owner 与 unit；
- **不会**承诺 coupled transmission 的 provider 准入。

嵌套 subject 用 `bind_many(binding, declarations)`：

```python
children = DefaultCanonicalController().bind_many(binding, (
    (arm_subject, "arm-writer", ("N*m",) * 7),
    (hand_subject, "hand-writer", ("N*m",) * 2),
))
```

每个 declaration 是 `(subject, writer_id, units)`，必须不可变 tuple；subject/writer 不能重复；所有子绑定成功后才发布，避免部分绑定。之后由现有 `PhysicalControlExecutionV1` 在一个 interval 组合，不要另造 compositor。

逐项解释：

| 概念 | 真实含义 |
| --- | --- |
| channel 声明 | source/Scene 编译出的具名关节；不是 Panda 7 维硬编码 |
| writer | 该 channel 的所有者；默认绑定要求 writer 在 `subject.controller_writers` 内 |
| 单位 | 每个 channel 显式 `N*m`（revolute）或 `N`（prismatic）；不按名字猜 |
| transmission/native drive | source 的 actuator/tendon/equality 与 drive 选择；默认 Controller 不改变它 |
| action_space | 由 `DirectJointEffortControllerV1` 按 channel effort 范围生成 `Dict({action_key: Box(...)})` |
| source identity | binding 与 state/context 的 source/closure/artifact 必须一致 |

默认 Controller **不表示**“任意夹爪 position actuator 可以把旧 pose 数组当 effort 透传”。position drive 与 direct effort 是不同语义；是否共存由 source/声明决定。

已有 profile 的参数修改示例（不新增 config 字段）：

```python
config = {
    "execution": {"physics_provider": "mujoco", "physics_backend": "cpu"},
    "controller": {"profile_id": "r3_continuous_v1"},
    # 只有 Task 声明 selected_controller_parameters 才允许 parameters
}
```

如果要改的是 Controller **参数**（如 reset selection），必须使用该 Task 真正声明的 `controller.parameters` 键；如果只是换 solution 的轨迹，不要改 Controller 对象。`reset` 是否重新绑定由 Controller 的 reset capability 和 Task 选择决定；普通 reset 不应被教程用来偷偷替换 Controller。

## C3 第一个自定义算法：命名关节 PD／线性 effort

最短起点是 `LinearEffortControllerV1.zero_bias`：它从真实 `PhysicalControlBindingV1` 和 writer 生成有界 named action、零偏置纯模型、逐通道 `JointEffortV1` 输出。

```python
from task_env.controllers.canonical.physical_controller import LinearEffortControllerV1

controller = LinearEffortControllerV1.zero_bias(
    binding,                                  # 当前 subject/source 的真实 binding
    writer_id="my-writer",
    channel_keys=channel_keys,                # 例如 ("panda-v1/joint1", ..., "panda-v1/joint7")
    action_names=tuple(f"effort-{i}" for i in range(len(channel_keys))),
    action_to_effort=tuple(
        tuple(1.0 if row == column else 0.0 for column in range(len(channel_keys)))
        for row in range(len(channel_keys))
    ),
    cadence_s=0.01,
    model_id="my-zero-bias-model-v1",
)
```

这已经是“线性 effort”，但还不是 PD：它把输入当 effort 直通。要实现**命名关节 PD**，在同一个 typed 合同上包一层纯算法：

```python
# workspace/tutorial/named_joint_pd.py  （扩展代码；不在生产 Core 注册）
from __future__ import annotations
import math
import numpy as np
from gymnasium.spaces import Box, Dict

from task_env.controllers.canonical.physical_commands import (
    ContributionPolicyV1, JointEffortV1, PhysicalCommandBatchV1,
    PhysicalCommandContextV1, PhysicalControlBindingV1,
)
from task_env.controllers.canonical.contracts import digest


class NamedJointPDController:
    """Joint target -> bounded effort; pure compute, no physics step."""

    profile_id = "tutorial_named_joint_pd_v1"

    def __init__(self, binding: PhysicalControlBindingV1, *, channel_keys, writer_id,
                 kp=40.0, kd=2.0, action_low=-1.5, action_high=1.5, action_key="target"):
        if type(binding) is not PhysicalControlBindingV1:
            raise TypeError("PD controller requires a typed physical binding")
        by_key = {f"{c.entity_id}/{c.joint_id}": c for c in binding.channels}
        keys = tuple(channel_keys)
        if not keys or len(set(keys)) != len(keys):
            raise ValueError("PD controller requires unique ordered channels")
        if any(key not in by_key or writer_id not in by_key[key].owner_ids for key in keys):
            raise ValueError("PD channels differ from the declared writer binding")
        if not (math.isfinite(kp) and math.isfinite(kd) and kp > 0 and kd >= 0):
            raise ValueError("PD gains must be finite, kp>0, kd>=0")
        if not (math.isfinite(action_low) and math.isfinite(action_high)
                and action_low < action_high):
            raise ValueError("PD target bounds must be finite and ordered")

        self.binding = binding
        self.writer_id = writer_id
        self._channels = tuple(by_key[key] for key in keys)
        self.kp, self.kd = float(kp), float(kd)
        self.action_key = action_key
        self.action_space = Dict({action_key: Box(
            low=np.full(len(keys), action_low, dtype=np.float32),
            high=np.full(len(keys), action_high, dtype=np.float32),
            dtype=np.float32,
        )})
        self.identity = digest({
            "profile": self.profile_id,
            "binding": binding.identity_hash,
            "channels": keys,
            "kp": self.kp,
            "kd": self.kd,
            "action_low": action_low,
            "action_high": action_high,
        })
        self._episode_id = None
        self.last_action = None

    def reset_from_realized_state(self, state):
        # state 是当前 episode 的公开 state publication
        if state.boundary.scene_identity_hash != self.binding.scene_sha256:
            raise ValueError("PD reset state differs from bound Scene")
        self._episode_id = state.boundary.episode_id
        self.last_action = None

    def validate_action(self, action):
        if isinstance(action, dict):
            if set(action) != {self.action_key}:
                raise ValueError("PD action tree differs from its declaration")
            action = action[self.action_key]
        values = np.asarray(action)
        if (values.shape != (len(self._channels),)
                or values.dtype.kind not in {"i", "u", "f"}
                or not np.isfinite(values).all()):
            raise ValueError("PD action shape or finite values are invalid")
        space = self.action_space.spaces[self.action_key]
        if not space.contains(values.astype(np.float32)):
            raise ValueError("PD target exceeds its declared bounds")
        return np.asarray(values, dtype=np.float64)

    def compute(self, action, state, context):
        if type(context) is not PhysicalCommandContextV1:
            raise TypeError("PD controller requires a typed interval context")
        target = self.validate_action(action)

        # 1) 来源/边界/时钟：state 必须是本 interval 的公开同边界状态
        if (context.source_id, context.source_closure_sha256, context.artifact_sha256) != (
                self.binding.source_id, self.binding.source_closure_sha256,
                self.binding.artifact_sha256):
            raise ValueError("PD context source differs from binding")
        if state.boundary != context.boundary or state.sample_clock != context.clock:
            raise ValueError("PD state is stale or foreign")
        if self._episode_id is None or context.boundary.episode_id != self._episode_id:
            raise ValueError("PD must be reset for the current episode")

        # 2) q/qd 来自公开 state，不读私有 solver 数组
        joints = {(j.entity_id, j.joint_id): j for j in state.joints}
        q, qd = [], []
        for channel in self._channels:
            joint = joints.get((channel.entity_id, channel.joint_id))
            if joint is None:
                raise ValueError("PD state lacks a declared joint")
            q.append(float(joint.position[0]))
            qd.append(float(joint.velocity[0]))
        q = np.asarray(q)
        qd = np.asarray(qd)
        if not np.isfinite(q).all() or not np.isfinite(qd).all():
            raise ValueError("PD joint state is not finite")

        # 3) pure PD；饱和按 channel 的 effort_range
        efforts = self.kp * (target - q) - self.kd * qd
        efforts = np.clip(
            efforts,
            [c.effort_range[0] for c in self._channels],
            [c.effort_range[1] for c in self._channels],
        )

        # 4) 逐通道 typed contribution；由现有 execution owner 组合/提交
        contributions = []
        for index, (channel, value) in enumerate(zip(self._channels, efforts, strict=True)):
            policy = ContributionPolicyV1(
                "physical-contribution-policy-v1",
                f"{self.writer_id}/channel-{index}",
                f"{self.writer_id}/effect-{index}",
                self.writer_id,
                "exclusive",
                "clip_after_sum",
                "one_interval",
            )
            contributions.append(JointEffortV1(
                "joint-effort-v1", context, policy,
                channel.entity_id, channel.joint_id, channel.dof_id,
                channel.kind, channel.axis, channel.axis_frame,
                channel.sign, channel.unit, float(value),
                channel.effort_range, "explicit_full_pd",
            ))
        self.last_action = target.copy()
        return PhysicalCommandBatchV1(
            "physical-command-batch-v1", context,
            tuple(contributions), (), (),
        )
```

逐条解释（对应蓝图 C3 的七步）：

1. **取得真实 binding/ordered channels**：上面从 `binding.channels` 按 `entity_id/joint_id` 取；`channel_keys` 由 Task/Robot 的真实声明给，不能硬填 Panda 7 维到公共代码。
2. **有界 action_space**：这里显式声明每个关节的目标范围；真实产品应使用 source 的关节限位/安全范围，而不是猜。action 是**目标 q**（rad），不是 delta q 或 effort。
3. **reset 清理**：`reset_from_realized_state` 检查 Scene 与 episode，清掉 `last_action`；本算法无积分器/历史目标，若你有积分项，也必须在这里清零，并在 source/episode 变更后拒绝旧 context。
4. **同边界计算**：`state.boundary == context.boundary` 且 `sample_clock == context.clock`；纯模型只做 evaluate，不推进 scratch/真实物理。
5. **声明 writer/policy/unit/range**：`ContributionPolicyV1` 的 owner/effect 必须来自声明；饱和顺序由公共 owner 决定（这里标 `clip_after_sum`，与你的算法语义一致）。
6. **接入方式**：当前 selected Task 没有通用“用户注入 Controller”入口。扩展作者需要在**自己的 Task/Robot binding** 里构造它（例如替换 `controller_factory`/`build_effort_execution` 的声明），并让 admission 识别该 profile；不要把类对象塞进 `controller` mapping，也不要新增一个全局 registry 绕过检查。若只是实验，放在你的包/诊断外部，不改生产 Core。
7. **caller 只调用 `env.step`**：Controller 不写 native 数组、不 step；调用方检查 ACK、实际 state 响应与 `close()`。

## C4 带模型、TCP 和重力补偿的进阶控制器

参考实现：`OperationalSpaceEffortControllerV1`；公开模型合同：`ControllerModelRequirementV1`、`ModelOutputV1`；当前 scalar worker 的模型能力限 **MuJoCo CPU 既有 source dynamics 的 mass_matrix/bias、纯查询、physics_steps=0**。

### 模型绑定/释放

```python
osc = OperationalSpaceEffortControllerV1(
    binding, tcp_frame=tcp_frame, cadence_s=0.01,
    kp=150.0, damping_ratio=0.9, nullspace_kp=10.0,
)
osc.bind_model(model)     # model.source_id/source_closure/tcp_frame 必须与 binding/TCP 一致
try:
    ...
finally:
    osc.release_model()   # 释放模型引用并清 episode/reference
```

`bind_model` 拒绝：不可调用 `evaluate`、source/closure 不同、TCP 不同、重复绑定。`release_model` 清 `_model/_episode/_reference`。

### 公式与数据来源

在 world frame，target pose `(p_d, R_d)`，当前 TCP `(p, R)`、关节 `q,qd`：

```text
e_p = p_d - p
e_R = 0.5 * Σ_i (R[:,i] × R_d[:,i])
v   = J(q) @ qd
F   = [ pinv(J_p M⁻¹ J_pᵀ) (kp e_p - kd v_p)
        pinv(J_R M⁻¹ J_Rᵀ) (kp e_R - kd v_R) ]
τ   = Jᵀ F + Nᵀ M (kp_null (q_ref - q) - kd_null qd) + bias(q,qd)
```

数据来自公开 model/state：

- `mass`：`(7,7)` 质量矩阵；
- `jacobian`：`(6,7)` TCP Jacobian；
- `bias`：`(7,)` 关节 bias；
- `rotation`/`position`：模型给出的当前 TCP；
- `q/qd`：公开 `state.joints`；
- `tcp_frame`：必须是已声明的 subject frame，且在 `state.frames` 中唯一。

实现中的一致性检查：`model.evaluate(q,qd,boundary)` 返回的 `boundary` 必须等于 state boundary、`physics_steps==0`；模型 TCP 与公开 state 的 TCP 位置差 >3 mm 或旋转差 >0.05 时拒绝。`reset_from_realized_state` 要求已绑定模型与同 Scene，记录当前 `q` 作为 nullspace reference。

时序：

- **普通 reset**：重新从实际状态设置 reference；清 `last_action`。
- **参数重建**：改 `kp/damping_ratio/nullspace_kp` 需要重新构造 Controller（identity 变化），不要在运行中热改。
- **same-source 质量/偏置读取**：每个边界重新 evaluate；不缓存跨边界模型输出。

R3 位置路线与 effort 路线不要混成一套算法：R3 是 pose action → 参考/伺服 → 原生 position drive；OSC 是 pose → 模型动力学 → typed effort，且要求 7 个隔离的 `native_drive='disabled'` 臂通道。

**effect ownership**：补偿贡献（`bias`）必须只由该 Controller 的 effect 声明一次；不要与另一个重力补偿/position drive 重复施加。原/装配本体模型不能用相同维度推定同源；模型必须来自同一 source 组合与具名本体。

本 7c 不实现新的 OSC、数值模型或任意 provider 模型代理。适用 provider/部署范围以现有证据为准：MuJoCo CPU 的 source dynamics 纯查询是已接入的模型能力；GeoPhys/Isaac 的 source-model 能力不由此扩张。

## C5 一份能揭露错误的验收示例

下面只做**静态/纯算法 + 小 native 时序**的验收脚本骨架；本轮没有执行。

```python
import numpy as np
from task_env import make_env

env = make_env(
    "pick-cube-p16-reference-v1",
    config={
        "execution": {"physics_provider": "mujoco", "physics_backend": "cpu"},
        "controller": {"profile_id": "r3_continuous_v1"},
        "episode": {"horizon": 5},
    },
)
try:
    obs, info = env.reset(seed=31)
    spec = env.action_space
    bad = np.zeros(7, dtype=np.float64)          # 少一维
    try:
        env.step(bad)
    except (ValueError, TypeError) as error:
        print("EXPECTED shape rejection:", error)

    # 合法非零输入：在 reset 的 ee pose 上做小位移
    pose = np.asarray(obs["state"]["ee_pose"], dtype=np.float64).copy()
    pose[0] += 0.002
    action = np.concatenate([pose, [1.0]])
    obs2, reward, terminated, truncated, info2 = env.step(action)
    print("pose changed:", np.asarray(obs2["state"]["ee_pose"])[:3] - pose[:3])
    print("task_success:", info2.get("task_metrics", {}).get("task_success"))
finally:
    env.close()
```

验收应至少覆盖：

| 检查 | 期望 |
| --- | --- |
| 非零输入后实际状态响应 | 公开 `state` 有可解释变化；ACK 不等于跟踪精度 |
| reset 后目标/积分清零 | 新 episode 不接受旧 generation/context；自定义积分器归零 |
| 错误 shape/单位/过期 context | 在计算或 admission 处明确拒绝，不是静默修值 |
| 受支持的普通 profile 重置 | `reset` 重新绑定/重建，action_space 与 identity 可核对 |
| `close` | 释放资源；失败时保留原异常/可重试语义 |
| 空载 TCP 跟踪 | 需要**同输入可比 oracle** 与误差单位（m/rad）；没有 oracle 不能声称精度 |
| worker/device/夹爪未支持组合 | 明确列为未验证；不把“跨后端控制器”写成已支持 |

静态/纯算法验证不是 native 成功；native 成功也不是任意 source/provider/载荷的资格。新 profile 若未在 worker/device/夹爪路线验证，必须在你的交付里单列未支持项。
