# 控制、物理命令与反馈协议

状态：`APPROVED_IMPLEMENTATION_BASELINE`，2026-11-03 维护者确认；见[确认收据](../maintenance/20261103_protocol_baseline_confirmation.md)。本文是语义实施基线，不是已实现的 public schema；4a–4c 在既有 owner 内落地。

## 1. 控制主体、Controller 与提交边界

```text
Agent / task action
    → Robot / nested component 的控制声明与 Controller binding
    → Controller + Core public state / 可替换 model
    → typed named physical contributions
    → Core 校验 / 显式组合 → RuntimeSession / adapter
    → provider native command → 完整 physics interval → typed state / feedback
```

Robot 及其嵌套子 Robot／组件声明受控实体、关节／DOF、通道、轴／符号／单位／范围、耦合／传动、Controller 输入和输出 binding。Robot 的控制入口可委托可复用 Controller；声明不嵌入 provider SDK 或 live native object。逻辑组件树与 native articulation 不要求一一对应；复用现有 Scene robots、actuator resources、ControlGroup 与 binding owner，以有版本的语义引用解析嵌套路径，不引入第二套 Robot runtime／manager。

Core 拥有 binding、能力汇总、action spec、控制 cadence 和组合后的唯一 adapter 提交入口。多个 Controller 可控制互不重叠的部位，也可向显式 aggregator 提供贡献；不要求整个 Env 只有一个 Controller。Controller 通过 Core 的公共 state/model 接口计算，不调用 live provider SDK、不按 provider 分支运算、不 reset/step、不读取私有 solver state。Adapter 负责原生映射和施加，provider 负责场景物理。

### 2026-11-08 诊断中的有界实现候选

`ControlledSubjectV1` 在现有 physical control owner 中声明 Scene entity、source closure、来源拥有或引用、root Frame/要求、父主体、具名 logical channel 路径与 Controller writer。`PhysicalControlExecutionV1` 可将它与既有 `resolve_logical_assembly`、physical binding 和 Controller 匹配；在每次批次计算前重新校验，并拒绝主体外的 joint contribution。多个 Controller 仍经现有贡献组合规则形成一次逻辑提交，provider 可按其声明语义在多个物理子步保持或重施。声明的 root/父子关系不单独证明 native 约束或 provider 资产准入；这些仍须由来源、附件和 adapter 的既有检查证明。

诊断返工候选中，主体先声明逻辑通道，来源适配方提供具名传动及范围，`compile_declared_subject_binding` 从这些声明和同一个 logical assembly resolver 构造既有 physical binding；它不替代具体 source 与 native build 的传动核验。Panda 的已验证 source 限制保持在原 source 路径；Pendulum 和双轮声明仍不等于其真实运行路线已迁移。控制器有 Gymnasium `action_space` 时组合该声明，保留其边界、dtype 和动作树；仅有旧 `action_shape` 的既有调用保留无界 float32 Box 兼容语义，并非推断出真实有界能力。

Panda 的现有 PickCube physical 路径消费该声明；Pendulum 与双轮车新增的名称/通道声明尚未替换原 component bootstrap 和 native torque adapter。已存在的 `PhysicalControlExecutionV1` 无主体声明调用保留为兼容路径；这不意味着旧调用自动满足新声明。通用单层/嵌套扩展仍须在具体真实任务、附件、source 和 provider 交集验证，不能因合成声明通过就宣称真实四主体已统一。该候选及其证据等待独立主审，不改变已接收 G04 的范围。

PickCube MuJoCo CPU 的 direct effort 候选可将 physical execution 直接作为 selected 声明经同一 `RuntimeSession` 准入、reset、提交和读取；它不要求先构造 PositionServo profile。观察的 Panda 字段由该任务投影，公共物理状态使用 source-bound typed publication。现有 Position 和 reset-scoped 参考控制器仍是兼容路径；GeoPhys、Isaac、组件任务和其他控制器并未因这条纵切自动迁移或取得新的 native 验证。

PickCube physical 候选的 `ee_pose` 与任务距离、reward 以 source 绑定的 `nutassembly_ee_site` 为准，`hand_pose` 单独表示 hand 原点。旧 default direct 的 Position 投影曾将 hand 代入任务 EE，历史记录按其原实现解释，不回写旧 evidence；这次修正会改变受影响旧路径的任务距离和 reward，shape 及物理控制语义不因此改变。

## 2. 三类底层物理命令

名称是语义类别，具体版本值／codec 在现有 canonical/control owner 内由 4a 冻结：

| 类别 | Core 提供 | Adapter 必须核对与回报 |
| --- | --- | --- |
| JointEffort | 具名 entity/Joint/DOF、轴向／符号、转动 N·m 或平动 N、目标值、区间／cadence、contribution ID、组合与限幅规则 | 原生 joint/actuator/transmission/gear/mimic/tendon 映射、可实现力域、实际写入和限制；不能将无量纲 ctrl 或 position drive 更名为 effort |
| BodyWrench | 具名 body（普通物体或 Robot body）、表达 Frame、作用点及其 Frame、力矩参考点、force N 与 torque N·m、duration／有效区间和贡献身份 | body/COM/origin、力和力矩的变换、原生施力入口、hold／clear/reapply 语义、完成边界和可读回范围；坐标／力矩参考点不明则拒绝 |
| TypedLoadExtension | namespace/schema、requiredness、目标区域／粒子／拓扑引用、数量及 shape、单位／Frame、有效区间、payload identity | 注册的扩展与精确 provider 能力交集；unknown required 拒绝，不能使用任意 Any/dict 绕过类型／准入 |

JointEffort 与 BodyWrench 是本版的一等协议类型；4a 落地 typed command／capability／拒绝与映射边界，4b 完成真实执行的有界验收。BodyWrench 的最小目标、路线、作用点／Frame、数值 oracle 和预算在 4a 包中明确，不能将其整体标为未来接口，也不自动增加所有配对矩阵。粒子力、面压力、分布载荷等只保留 TypedLoadExtension；本版不新增完整非刚体载荷语言。

能力逐项声明：joint effort、body force、body torque、offset application point、Frame、持续方式、叠加、传动限制、并行布局和测量范围分别查询，不能用一个 effort_supported 推出全部支持。被动 free cube 默认不接收控制；显式任务／调用方可以按已准入 BodyWrench 施力，不把其 7 维 qpos 当动作。

## 3. Panda profile：8 维输入与 9 路具名输出

- Panda 的一类 Controller 接受 **8 维 action**，经其参考生成／伺服和源约束映射，输出 **7 个 arm revolute joint torque（N·m）＋2 个 finger prismatic joint force（N）**。八个输入的具体含义由该 Controller 的 action spec 定义，不由 Core 根据维度猜测。九路输出是具名物理通道，不代表九个独立控制输入／自由度，不进入通用 Core 的固定数组结构。
- 夹爪 closure/opening 可作为 Controller 内部中间目标；不再强制一条 closure generalized force 作为 canonical 边界。两个 finger 的正负按各自关节轴定义，不能直接假设为两个世界坐标相反的力，也不自动等于接触测得夹持力。
- 既有源是七臂 actuator 加一条 tendon gripper route、两个 finger joints。Adapter 需验证所请求的两路力是否处于该 source transmission／约束可表达的子空间，记录原生分配、coupling、限幅、轴／符号和虚功关系；不得删除 mimic/tendon 来伪造支持。任意独立双指力是另一个能力；不支持时拒绝该请求，仍可支持已验证的成对力 profile。
- 若 Controller 用 `q_native=f(s)` 生成手指参考，则 `A=df/ds`、`F_s=A^T*tau_native` 只给出功率共轭关系，不能唯一反推两个原生力。力分配必须有显式 source-bound 策略；两路 canonical force 到 native actuator 的反向编译同样需要可实现性证明，不能直接求逆或把 tendon ctrl 标为 N。
- 当前 R3 实现输出 arm q_ref＋gripper position；现有 arm-torque＋finger-position mixed route、opening＋force limit、native mimic/implicit PD 都保留具名 **position compatibility** 身份，不能充当 7＋2 effort 已实现。阶段 2 先修复这一现有链路，阶段 4 再迁移并复核成功。

## 4. 力贡献、驱动与重复提交

“唯一 writer”指组合完成后的单一提交 authority，不排斥物理上有意的力叠加：

1. 每项贡献有 controller/caller 来源、目标、contribution ID、区间、generation、组合政策和限幅政策。互斥目标冲突必须拒绝；声明为 sum 的同坐标贡献先变换到共同 Frame／参考点再相加。组合前／后 clip 和 native clamp 分别记录，不依赖写入顺序。
2. Robot joint effort 与施加在其 body 上的外力可以并存。BodyWrench 与它的 `J^T*wrench` 投影若代表同一贡献只能施加一次；不能重复走两条入口。
3. 一个 native interval 的重复 contribution／提交必须拒绝或按明示幂等语义处理，不能累计两次。持续载荷在各 substep 依原生 buffer 的 clear/add/replace 规则重施，不能每子步额外累加；reset 清空旧 episode 的 pending contribution、force latch 和已消费记录。
4. 显式完整 PD 与未协调的 position/implicit-PD drive 不能重复控制同一目标。若显式声明的复合控制确需某项驱动力，必须独立声明贡献及 owner；不得把未知 native servo 当成可加外力。引擎必须保留的 passive/inactive drive、gains、friction、限幅和被动项进入 receipt。
5. 一次批量命令的每行仍需 env/row/boundary identity；同名通道不能导致跨 Robot／跨环境施力。

## 5. 命令接受、写入与反馈

| 阶段 | 意义 | receipt 能证明什么 |
| --- | --- | --- |
| submitted | Core 提交 source/materialization/episode/boundary-bound 命令及贡献清单 | 来源、目标、组合、作用区间及输入 identity |
| accepted | Core/adapter 校验能力、名称、单位、Frame、传动限制与新鲜度 | 请求可按此映射执行；尚未推进物理 |
| applied / write acknowledged | Adapter 写入并确认 native command | 哪些原生写入发生；有证据才称 canonical effort applied，不证明运动或实测力 |
| measured / estimated | 独立 typed sample 记录传感器或估算模型、单位、时钟及 identity | 实际 measurement 或明确标为 model estimate；不能从 ack 推断 |

现有 `AppliedMixedActuatorCommandV1` 是 target-hash/provider/channel ACK；`AppliedCanonicalControl` 是目标确认。保持其限制。分别记录 Core clip、组合、adapter map、solver/native clamp；原生 ctrl 的单位、gear/transmission、saturation、delay、mimic/tendon 必须 source-bound。

## 6. Controller 输入、可替换公共模型与反馈

Binding 声明 required/optional state、实体与关节名/order、单位／Frame／参考点、action spec、cadence、clock、新鲜度、reset/close owner。FK/Jacobian/M/gravity/bias/contact/actuator-force 均按 Controller 实际需求求交，不强制所有任务具有这些字段。缺 required 或 freshness 不满足时拒绝／fault；optional 用 `UnavailableStateValue(reason)`，不能填零。

在现有 `ControlBindingPlanV1`／Controller binding 中增补 typed model requirement，至少含 model profile、实现库／版本和依赖环境、source/closure、model-to-live names/order、输入 state boundary、输出量纲／Frame、cadence/max-age、pure computation/no physics advance、内部积分器及资源 owner。Controller 只面向公共 model 接口；FK/J/M/bias 的库实现可替换，使用 MuJoCo 计算模型可以作为显式模型实现，不成为 Controller 硬编码 live-provider 依赖。不得创建第二个运行中的物理 step。

现有 LIBERO `MujocoSourceGravityBiasV1` 以 `ExecutionSourceReceiptV1` 绑定 source MJCF，接受具名 q/qdot，用 `mj_forward` 计算 FK/J/M/bias 且 `mj_step_call_count=0`；是 bench_deploy owner 的有界参考，不是现成通用 Core ModelService。R3 的 PandaKinematics 生成 q_ref，亦不表示已有公共 effort model。

反馈保持以下区别：

- `opening_m` 来自 finger positions；受限 force-admitted MuJoCo/GeoPhys profile 经 `control.py::feedback_value` 读取并按符号投影 native actuator force 为 `closing_force_N`，不是位置推导的力，也不自动等于接触夹持力。
- `NativeControlFeedbackSampleV1` 绑定 provider/materialization/source/episode/reset/sequence/revision/native step/phase。其他 position-only route 没有该测量则明确 unavailable；不抹去已有有界能力。
- outer interval hold 与每 physics substep 重算分别配置和准入；命令、模型与测量的 clock/cadence 不由 route 名推定。

## 7. Reset 切换与检查

Controller、参数及输入 spec 在 reset 更改；episode 内组合固定。Core 在破坏旧 session 前核对新 binding、能力和 Env/Batch action-space policy，发布新 action spec/generation。Fixed-space wrapper／Agent 不兼容时明确拒绝或由调用方匹配 wrapper；旧 action 不跨 generation。同一 native batch 布局共同；更换执行方案／映射整批重建。

按 realized reset state 初始化 Controller，清 q_ref、积分器、滤波、贡献、force latch、sample history；不迁移旧 Controller 历史。Observation 结构／shape／dtype／单位／Frame／语义保持构建契约。上层输入切换不保证两 Controller 产生相同数值力，只保证输出服从同一物理命令协议。

[结构化案例](../planning/control-command-cases.json)覆盖嵌套主体、8→9、直接 joint effort／BodyWrench、声明叠加及拒绝。4a 落地协议／映射／公开模型边界，4b 真实验证三后端共同 effort 与有界 BodyWrench，4c 验证 reset 切换和 Solution 复核。设计确认不替代运行证据，也不重开 F05 严格传力等价研究。

## Pendulum 有界迁移候选

5c 人工诊断单元 2 的候选将 Pendulum 原 source 中的固定根、单个 hinge 和 unit-gear motor 交给受控主体声明与共享 binding 编译；`DirectJointEffortControllerV1` 将 `torque` 动作树转换为具名 typed effort，Env 的物理控制调度拥有唯一逻辑提交，provider adapter 在 native build 时独立核对关节、轴、传动、范围和 drive 隔离。原并行 component 入口仍是独立待迁移路线。此候选仅覆盖标量 CPU；其他主体、并行及 Isaac 不因此获得支持声明，最终状态以独立主审为准。

原任务的 reset 需要非零角速度。源绑定物理 reset 将采样位置及速度作为同一身份的 reset 输入，先校验来源和具名布局，再由 session 执行并对位置、速度及时钟读回；不以旧零速度 reset 合同隐式替代。共享 `ResetSampleV1` 的该有界策略只接收 time-zero 标量 joint 状态，不声称覆盖 free-body 或任意模型初始化。Pendulum 的 HWC task RGB 使用构造时固定的 CameraSpec／renderer，renderer 消费同一物理边界；渲染能力和闭环验证仍按各自交集审查。

该候选的 GeoPhys CPU `rgb_array` observer 由同一 RuntimeSession 的 render source 提供，使用公开的 visualizer 构造与同步帧读回；observer capture 不提交物理 step。task RGB 与 observer 是不同入口。可见窗口、observer/task RGB 同时使用及其他 renderer 组合不属于本单元验证范围。

原 component 的 `render.camera_obs` 在 GeoPhys CPU 单 world camera 的受测交集由同一 session 的已有 camera provider 继续采集并发布相机元数据；一般多相机、depth 和其他 renderer 仍不由该证据推断。可见 human observer 未在本窗口准入或验证。
