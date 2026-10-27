# R02 — Composite Control Profiles

状态：REVISED_DRAFT；R02a 已获Sol接收（ACCEPTED_S1_BOUNDED；Required State拒绝门修正后37 passed）；R02b 已获Sol接收（ACCEPTED_S1_BOUNDED；4项局部修正后18 passed）；R02c仍 PLANNED / NOT_STARTED。
复用算法，新增 leaf binding 契约不等于已有叶级执行支持，也不修改最终 Goal/DAG/Required Envelope。

## 真实复用边界

[Position Profile](../../../../../task_env/controllers/canonical/position_profile.py) 当前要求同 Entity 内 7 arm + 2 finger joints，并以单 writer 绑定 arm/gripper 两组。[ControlBindingPlan](../../../../../task_env/runtime/sessions/control.py) 检查全部资源唯一覆盖，并拒绝一个 writer 跨 Entity。[JointPositionServoBackend](../../../../../task_env/controllers/joint_position.py) 提供既有 position 算法复用点；它不是现成的 advanced Arm-only/Hand-only profile。

EXTEND_EXISTING / COMPOSE_EXISTING：在现有 canonical profile/target/feedback/admission owners 内形成 leaf adapter，保留现有 RuntimeSession 和 Controller 算法。两个完整 Panda Controller 的历史 S2 只做兼容基线，不能满足新 leaf 的充分证明。Asset 不嵌入 Controller 实例、任意 Python callable 或未注册可执行代码。

## Leaf 版本化合同（R02a静态S1出口已接收；runtime仍NOT_ADMITTED）

| Leaf | Action | Target / Applied Ack | Required State / Identity |
| --- | --- | --- | --- |
| Arm-only Position | `ArmPositionActionV1`；有序七关节 `position_rad`，rad，Panda joint1…joint7 与绑定限位；Cartesian/IK 不包括 | `ArmPositionTargetV1` 固定 profile/action schema/writer、七个有序 Joint 与 Actuator、binding/source/Scene hash、typed boundary/clock；`LeafApplicationAckV1` 引用精确 Target 和应用 boundary，不代表到位 | `LeafRequiredStateV1` 复用 `StateRequirements`，含 Arm Entity 每关节 q/qvel 和 Entity-qualified TCP parent Frame pose；额外锁定 reset/episode/boundary/clock/source identities；不借用另一 Entity Hand frame |
| Hand-only Position | `HandPositionActionV1` 单一 aggregate `opening_m`，m，[0,0.08]；旧 signed scalar 只能经显式 `opening_m=0.04*(u+1)` adapter 转换 | `HandPositionTargetV1` 固定两个有序 finger Joint、单一 `actuator8`、writer/identity/boundary/clock；candidate mapping `ctrl=3187.5*opening_m`，source ctrlrange `[0,255]`、gainprm `(0.01568627451,0,0)`、biasprm `(0,-100,-10)` | q1/q2、qvel、opening=`q1+q2`、Hand TCP parent Frame 和 typed clock；finger range 各 `[0,0.04] m`；`hand.xml/tendon/split` 系数 0.5/0.5 + `hand.xml/equality/finger_joint1=finger_joint2`；不要求 measured force |
| Hand-only Force-aware | `hand-force-aware-action-v1` 仅作独立 profile/action identity；R02a 不提供可执行 Action/Target/Ack | `HandForceAwareDependencyV1` 固定依赖/拒绝描述且 `NOT_ADMITTED`；不能借用 Position identity | 独立 Force-aware Required State；要求 raw signed N 与 canonical closing N 分开、source/transmission、单位/符号、validity、phase/native index、sequence、state/config revisions、episode/reset/boundary、Provider/build/backend/cadence。符号与phase映射标为未审计 |

每一 leaf 的 Action/Target/Ack/Required State 都以独立版本 discriminator/identity 绑定 ordered canonical refs、算法/配置、TCP、source closure、Provider/build/backend 和 cadence。只对实际测试的模式开放；现有 ActionModeSpec、CanonicalControlTarget 与 AppliedCanonicalControl 能复用的字段复用，若 frozen payload 不足则另版 extension，不改旧 bytes。首个 R03 required 路线只要求两种 Position leaf；Force-aware 新 leaf 仅定义依赖和拒绝边界，未纳入装配必需出口，不因此扩大 R1 支持。

当前实现 owner 是 `task_env/controllers/canonical/leaf_profiles.py`，仅将高级值 re-export 于同目录 `canonical` 包，未扩充 `task_env` root facade。`LeafProfileBindingV1` 区分 `declared` 与 `synthetic_fixture`，锁定 Scene identity、Assembly ID/revision/content hash、leaf path/member selector、Entity/Asset、source closure、profile/action schema、algorithm/config、Provider/build/backend/timebase、ordered resources、ControlGroup、TCP parent Frame、`T_parent_from_tcp` transform direction 与 Required State。Arm 还逐项配对 joint1…joint7→actuator1…actuator7；Hand 只由固定 tendon 与单 actuator 表示，不给两个 finger 各自分配 writer。静态 validator 对 Scene v3 的 Joint kind/unit/axis、Actuator group 和 TCP Frame 做核验；有 `ResolvedLogicalAssemblyV1` 时核对确切 selector。Whole-Panda 的 arm/hand group 是 reference-only selector，不能据此创建 owner/writer；独立 Entity fixture 使用已有 Entity owners。

Position Target/Ack 的静态交叉检查需要调用者另给 source/application boundary 和 clock context；Ack 的 source 与 application boundary 限定为同一 evaluation control step。Ack 只证明合同字段自洽，不记录真实 apply。Position state 不包含 actuator force。Force-aware 目录为有限只读值，所有三项都标为 `CONTRACT_ONLY / NOT_ADMITTED / NOT_RUN`；它没有注册、Provider manifest 或执行能力。严格 decoder 拒绝未知字段/版本和跨 kind payload。旧 `RequestedAction`、`CanonicalControlTarget`、`AppliedCanonicalControl`、TaskArtifact/Scene/Reset/H5 identities 均未改。

R02a provider-free S1 仅验证合同与静态selector，不算 Core admission、native S2/S3 或 Qualification。R02b实现状态见下文；R02c 负责真实 leaf writer/既有 H5，R01c source projection 仍独立；本文不更改它们的 DAG 边。

## Sol复核与Required State修正（2026-10-27）

Sol审阅提交 `8d2c46524e9dc8cce282335cd5fecb04c603d622` 的10文件差异与30项S1，发现Required State可被降为optional或混入别的leaf资源。已直接要求所有v1字段保持required，并将具体binding的requirements与profile/Entity/resources/TCP模板完整匹配；不修改旧generic StateRequirements、Profile/Target/Ack或有效payload/hash。7项定向负例通过，原集合加回归37 passed，接收为 **ACCEPTED_S1_BOUNDED**。下一行R01c；source/plan/adapter/native仍由原后续Gate负责。复核入口为ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r02a_001/`。

## Preset 编译与执行所有权

1. 校验 Scene/Assembly/member/profile/source 的精确版本；parent preset 是不可变模板，不是 writer。
2. 按叶 canonical path 展开 preset；Local Override 必须显式选 leaf 并替换完整 profile section，禁止把两个 profile 的字段隐式深合并。重复/未知 override、跨 owned resources 的覆盖拒绝；允许的标量 override 由该 profile schema 列出并重新校验。
3. 编译 effective plan，记录 base preset ID/hash、排序 overrides、resolved leaf profile IDs/required state、source/TCP/clock 与唯一 actuator writers。`preset/partially_overridden/custom` 从差分推导，不再存独立可漂移状态。
4. 复用完整 ControlBindingPlan 预检；所有 Group/action shape/unit/schema/identity/feedback 必须在任何 Controller memory、apply 或 physics step 前通过。Canonical 顺序→native actuator slot 的映射由 materialization receipt 提供，不能依 tuple 恰好同序。
5. 只有 leaf writer 发 Target；parent、只读 subcomponent ref 与 alias 都不写。重叠资源、遗漏 actuator、同一个 native actuator 的不同 canonical alias 必须拒绝。

## 切换、故障与录制

reset 时选择 preset 与 episode 内切换分开。现有 C02c 仅单 Panda Position、相同 schema/source/TCP/resources/feedback/clock 的受限切换；不能因此允许 split leaf/dual/force-aware 切换。首版 split leaf 采用静态 plan，运行中不支持的改变明确 NOT_ADMITTED。继承范围内的 switch 只在完整边界记事件，不计算/施控/step；下一真实 transition 带新 identity Target/Ack。新 leaf switch 若未来需要，须追加该 slice 内独立 S1/S2，不能拿旧 C02c 充证。

整体预检失败零写入；部分 native apply 后失败沿用 C03a fault latch 与 partial-applied receipt，不宣称回滚。禁止追加伪 transition、freeze incomplete H5 或带 fault 继续执行。事件/Recorder 写入失败也闭锁；reset/close 行为由既有 Env/Recorder lifecycle 所有者负责。

## 切片与证据

| ID | 前置 | 工作与交付 | 必需 Evidence / Stop Condition |
| --- | --- | --- | --- |
| R02a | R01a | Arm-only/Hand-only Position 和 Force-aware 依赖/拒绝合同；capability catalog | S1：版本/顺序/TCP/单位/资源/缺反馈负例；不得把 catalog 当支持 |
| R02b | R02a,R01b | preset/override→effective leaf plan，复用现有算法与 target/ack owners | S1：整体预检、重复 native writer/alias/错 source/phase、hash 确定性、部分 apply fault；拆叶有真实 adapter，而非改名字 |
| R02c | R02b,R01c | 独立 Arm-only 与 Hand-only writer 的真实 Position 执行及既有 Recorder；保留双完整 Panda 兼容对照 | S2/S3：arm-only/hand-only/同时运动，override 只影响所属资源，target/ack/state/identity 同 H5；无适配或错误映射即停止 |

## R02b 实现与provider-free S1（2026-10-27，等待Sol复核）

本包在 `task_env.controllers.canonical.leaf_plan` 与既有 `task_env.runtime.sessions` control owner 中完成 additive R02b
合同。`LeafProfileSectionV1` 固定完整注册的 Arm/Hand Position 配置；`LeafControlPresetV1` 按规范路径保存 parent
template；`LeafProfileOverrideV1` 替换一个已存在leaf的完整profile section。`compile_effective_leaf_plan()` 从当前
root/Scene/child inputs 重跑R01b resolver和R01c source projection，然后重校验R02a binding、Scene Group/Actuator资源
覆盖、source identity、Provider/build/backend/timebase、profile/action/config/TCP/Required State。`EffectiveLeafPlanV1`
记录base preset hash、effective配置实值/hash、排序override和唯一writer资源表；状态 `preset`、
`partially_overridden`、`custom` 从实际生效配置差异推导。无效果override不改变状态或effective identity。

Arm/Hand真实stateless adapters 位于 `task_env.runtime.sessions.leaf_control`，共享已抽取的旧Arm绝对Position限幅/误差
修正与既有Hand opening servo/ctrl换算；完整Panda旧Controller仍调用同一算法。Hand Prepared Command 分开保留请求
开度(m)、servo开度(m)与native ctrl。显式 `LeafMaterializationReceiptV1` 固定canonical/native Joint/Actuator/Frame mapping、
logical Tendon→native name mapping、名称/ID/地址/slot、native维度、ctrl范围、source transmission、Hand单tendon actuator/equality与plan/provider/source identity；
乱序mapping按明确ref消费，slot/native名称/ID与地址alias拒绝。当前receipt全部标作 `synthetic_fixture`，不表示Provider产物。

`dispatch_leaf_control_interval()` 对完整请求、全部leaf action、typed Required State、clock/episode/reset/materialization/
config identity和writer可用性先做preflight；然后无副作用prepare全部command，才consume边界、apply独立patch、校验实际返回Ack、
执行单次外层step并核验下一份typed publication。Preflight失败不compute/apply/step。边界consume或apply之后失败时，
`ExecutionFaultV1`与 `LeafDispatchProgressV1`记录attempted/applied/unknown/acknowledged writers、已准备的Target/command patch
及失败前返回的每个typed apply result；可能先写后抛的writer标为unknown，
不宣称回滚、不重试、不发布transition，fault latch要求新episode/reset/materialization context后再继续。未创建native handle，
无资源需关闭；synthetic lifecycle 的close为幂等假IO检查。真实RuntimeSession Provider接线、SelectedReferenceEnv与Recorder/H5仍
未实现。

新增R02b provider-free S1为13 passed；选定受影响既有contracts/resolver/projection/C02a/C03a owner集合101 passed、3个真实
native selector deselected；另有C02b pure legacy-action guard 1 passed。新增测试还验证分离Arm/Hand Entity synthetic dispatch。
R02b总体状态为 `IMPLEMENTED_S1_PASS_PENDING_SOL_REVIEW`。未运行真实 Provider/native、R02c、R03b、S2/S3/S4/H5或Qualification；
split leaf仍 `NOT_ADMITTED`。Force-aware仍拒绝，旧完整Panda及双独立Position既有路线未宣称退化。

R02c 首先在既有完整 Panda 的两个 Existing-Entity Subcomponent References 上运行两个真正分离的 Arm-only / Hand-only writer，验证 leaf 算法/资源隔离与 H5；这与运行两个完整 Panda Controller 不同。若选择未装配的两个独立资产作附加样例，R02b 必须先交付其有界 source mapping/admission，不能假定已有支持。跨两个真实 Entity 的最终 split-leaf 执行、装配后载荷/耦合/状态与公开 env S3 由 R03c 必须验证；该选择不新增 R03b→R02c 的隐藏依赖。R04/R05 不是 Position-only 前置；Force-aware required-state 未准入只拒绝该 profile，不给 Position 强加力读取。

## R02b Sol复核与局部兼容修正（2026-10-27）

Sol审阅提交 `0527b1aa9261aad199b8afe62cf66c15f2f20ccb`，通过5项定向失败复现，直接关闭4项缺口：共享gripper helper恢复旧零力Target的hold语义；canonical Controller保留原末端opening限幅与无deadband运算；native actuator/ctrl slots必须完整覆盖nu，不接受隐藏的未分配actuator；writer沿用R02a semantic name规则，允许Entity-qualified名称。leaf配置仍按原schema校验，不新增Force-aware或物理force-cap支持。

最终R02b provider-free S1为18 passed（原13项加5项回归），既有owner集合101 passed/3个native selector未运行，C02b pure guard 1 passed。另从输入提交实际旧源码执行18个canonical与36个gripper数值对照，payload/Target identity或ctrl逐项完全一致。47项原始交付哈希、14项保护输入、11份Phase Markdown及R06/DAG/Required Envelope/P99语义匹配；原始Luna报告与失败日志保留。接收为 **ACCEPTED_S1_BOUNDED**；下一包按表进入R02c同完整Panda内两个真正Position leaf writer的MuJoCo CPU/既有Env与H5实现和有界验证。Sol本次未运行native/S2/S3/S4，未授予Provider admission或Qualification。复核见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r02b_001/`。
