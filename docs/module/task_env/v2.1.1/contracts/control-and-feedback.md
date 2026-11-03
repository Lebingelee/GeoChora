# 控制、effort 与反馈协议草案

状态：`DRAFT_FOR_DISCUSSION`；1c 冻结物理命令、模型/feedback 和兼容边界，4a–4c 再实施 Controller 与迁移。下列协议是设计建议，不是新 public schema。

## 控制分层与命令阶段

```text
Action / task semantics
    → Core Controller + explicitly bound public feedback/model
    → named physical command (one writer per DOF/resource/interval)
    → RuntimeSession / adapter → provider control channel
    → completed physics interval → typed state / feedback
```

Core 绑定唯一 Controller、命令 writer、action spec 和控制 cadence；RuntimeSession/adapter 写 provider 通道和推进 scene；provider 执行 physics。Controller 不 reset、step 或读 provider private state。command lifecycle 必须区分：

| 阶段 | 意义 | receipt 能证明什么 |
| --- | --- | --- |
| submitted | Core 为准确 source/materialization/episode/boundary 提交请求 | 目标、writer、作用区间及输入 identity |
| accepted | Core/adapter 校验能力、名称、单位、限制及新鲜度 | 请求可按此映射执行；还没有物理推进 |
| applied / write acknowledged | adapter 按记录的 native mapping 写入并确认写操作 | 写入了哪些 native control 或 generalized command；不代表发生运动、力已测量或等价于另一引擎 |
| measured / estimated | 独立 typed sample 指明传感器或估算模型、量纲、样本时钟与 identity | 实际 measurement 或明确标为 model estimate；缺失必须说明，不得由 ack 推断 |

现有 `AppliedMixedActuatorCommandV1` 是 target-hash/provider/channel ACK；`AppliedCanonicalControl` 是目标确认并显式不作运动声明。保持该限制。若 adapter 无法把 native ctrl 可靠映射成 canonical generalized effort，只能返回 native-channel write receipt，不能宣称 canonical effort applied。

## 首批 Panda 通道建议

- **主路线：**七个 source-bound Panda arm revolute DOF，按语义名固定排序，单位 N·m、轴和正负按源定义；一个 `panda-v1/gripper-closure` 广义坐标，坐标单位 m、共轭广义力单位 N。夹爪 opening/closing 正方向、参考点、范围和实体 binding 写进版本化 Scene/Execution 表示。
- Adapter receipt 给出 `q_native = f(q_closure)`／其 Jacobian 和 `tau_native = J(q)^T F_closure` 的 source-bound actuator/transmission 对应；native tendon/gear/mimic 必须在有效范围内满足能量/功率关系，做不到就拒绝该 effort capability。不能把一个 tendon ctrl 直接重命名成 N，也不能把两 finger joints 的任意两路力压成一条标量。
- 位置参考、opening＋force limit、原生 mimic/implicit PD 保留为具名 **position compatibility** profile；必须独立列能力，永不充当 unified effort completion。现有 R3 输出 arm q_ref 与 gripper position；MixedActuatorPlan 当前的 arm-torque＋finger-position/source-specific route 也是 compatibility。
- `cube-v1` 的 free-body pose/velocity 是被动状态，不生成 cube action。外部 wrench 若日后需要，必须另有 typed body、frame、application point、unit 和叠加政策。
- 一个 control interval 内一个 DOF/resource 只允许一个 writer。位置 servo/implicit drive、显式 PD 和 direct effort 的冲突需在 build/query 拒绝。若 direct effort route 要求引擎 drive 留存，配置须明确其 inactive/passive-only/native-owned 状态、gains、limits、friction 和被动项，避免重复 PD。

转动 generalized effort 单位 N·m，平动 generalized effort 单位 N；body wrench 仍是作用点/坐标系绑定的 6D wrench，不得同 joint effort 混用。native actuator input 的 ctrl range/units、gear/transmission、saturation、delay、mimic/tendon 与关节轴需进入 compiled mapping；单位与符号沿 source oracle，不靠数值数组顺序推断。行动限幅要分别记录 Core clip、adapter map 和 solver/native clamp。

## Controller 输入、公共模型与反馈

Controller binding 应声明必须与可选的字段、实体和关节名/order、单位、frame/reference point、频率/cadence、时钟域、新鲜度上限、action spec 与 reset 行为。至少可表达 q/qdot/pose/FK/Jacobian/M/gravity/bias/contact/actuator-force；每种 Controller 只要求实际需要的子集。缺 required field 或 freshness 不满足时拒绝/返回 typed operation failure；optional 未测量字段以 `UnavailableStateValue(reason)` 公开，绝不置为 0。

建议在现有 `ControlBindingPlanV1`/Controller binding 增加 `ControllerModelRequirementV1`，不另建通用服务管理器。建议字段：
- model profile、library/provider、精确 dependency/build identity 与模型 source/closure；
- 输入 state names/order/units、sample boundary 与 model-to-live mapping；
- 输出 quantity、单位、frame/reference point、解析版本；
- cadence（每外部 control interval 或每 physics substep）、最大 sample age 与同步要求；
- `pure_model_computation=true` 之类的行为承诺（不可推进执行 physics），以及 reset/integrator/filter state 和 close owner。

LIBERO 的 `MujocoSourceGravityBiasV1` 以 `ExecutionSourceReceiptV1` 绑定已验证 MJCF/closure，接受七个具名 q/qdot，使用 `mj_forward` 得 world TCP FK、Jacobian、arm mass matrix 与 `qfrc_bias`，并记 `mj_step_call_count=0`。它是可借鉴的 source-bound reference model，但属 bench_deploy，依赖 MuJoCo，也不是通用 Core Service。R3 使用 source XML 的 PandaKinematics 生成 q_ref，并非 effort model。任何参考模型须通过同一 Core boundary 的 q/qdot identity 校验；模型计算不推进 provider，也不得读 live solver field。

测量、估算和控制反馈分开：
- named q/qdot/state 的 sample clock 说明是 evaluation boundary 还是 native-step；
- `CanonicalControlFeedback.gripper.closing_force_N` 当前可从 named finger position 推导，是 position-derived value；不能写成传感器测得夹持力；
- `NativeControlFeedbackSampleV1` 必须绑定 provider materialization/source/episode/reset/sequence/revision/native step/phase；该能力 unavailable 时报告原因，不返回伪造零力；
- R3 外层按 control interval 更新 q_ref；mixed physics-rate profile 可明确选择每 native substep 重算。zero-order hold 与 recalculate 不得从 route 名字猜测；
- reset 或 action/Controller input schema 变化时清空 q_ref、积分器、滤波、force latch 与 sample history；更新 Controller/action-spec identity。已构建 observation schema 固定，不随 Controller 切换而暗改。

## Reset 时 action spec 切换

Controller、参数和输入规格只在 reset 边界改变；Core 先验证 Env/Batch 的 action-space policy，并发布新 binding/action spec identity。固定空间 wrapper/Agent 必须明确拒绝或由调用方重建匹配 wrapper；旧 action 不能跨 action-spec generation。

同一 native batch 的 action dimension 与布局保持共同。需要切换 provider/backend/solver 或 command mapping 时整批重建；只对明确支持的 profile 允许 same-config reset mask。新 episode 从 reset 实际 readback 初始化 Controller，不迁移旧积分器、力 latch 或 trajectory。完整 Gym/RL wrapper 兼容留后续 4c。

## 边界与验证

1c 定义语义、命令值和必要回执；不选一套通用 PD 增益、不实现新 Controller、不重新研究 F05 严格传力等价。4a–4b 核对 R3 reference、joint reference 与 direct effort profile 的真实映射、唯一 writer、drive ownership、饱和、sample freshness 和闭环；4c 验证 reset/spec 变化和旧 wrapper 的明确拒绝/重建。协议 PASS 不表示现有 R3/PickCube 问题已修复，也不提升 native evidence。
