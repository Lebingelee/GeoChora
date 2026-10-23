# R02 — Composite Control Profiles

状态：REVISED_DRAFT；R02a/b/c 均 PLANNED / NOT_STARTED。复用算法，新增 leaf binding 契约不等于已有叶级执行支持。

## 真实复用边界

[Position Profile](../../../../../task_env/controllers/canonical/position_profile.py) 当前要求同 Entity 内 7 arm + 2 finger joints，并以单 writer 绑定 arm/gripper 两组。[ControlBindingPlan](../../../../../task_env/runtime/sessions/control.py) 检查全部资源唯一覆盖，并拒绝一个 writer 跨 Entity。[JointPositionServoBackend](../../../../../task_env/controllers/joint_position.py) 提供既有 position 算法复用点；它不是现成的 advanced Arm-only/Hand-only profile。

EXTEND_EXISTING / COMPOSE_EXISTING：在现有 canonical profile/target/feedback/admission owners 内形成 leaf adapter，保留现有 RuntimeSession 和 Controller 算法。两个完整 Panda Controller 的历史 S2 只做兼容基线，不能满足新 leaf 的充分证明。Asset 不嵌入 Controller 实例、任意 Python callable 或未注册可执行代码。

## Leaf 版本化合同（拟议，R02a 才冻结字段名）

| Leaf | Action | Target / Applied Ack | Required State / Identity |
| --- | --- | --- | --- |
| Arm-only Position | 首版 ordered joint-position vector，rad、exact joint list、width=7、限位；Cartesian 为另行精确准入变体 | 带 version/profile/plan/source/boundary 的关节目标；Ack 引用同 target、writer、实际资源/应用边界，不混同真实到位 | Arm Entity 的 q/qvel、joint/actuator refs、reset/clock；独立 flange/TCP profile，明确 world/local frame、SE(3)/wxyz；不得硬取另一 Entity 的 hand frame |
| Hand-only Position | 独立 schema；Panda tendon 手首版 opening_m（m）、有界 [0,0.08]，明确与旧 normalized [-1,1] adapter 的变换 | 一个真实驱动 tendon actuator 的目标与限幅；Ack 对应该驱动资源，不把两个被联动 finger 当两个 writer | Hand Entity 的 finger joints/opening 与 clock；独立 Hand/TCP 与 actuator/transmission identity；不要求 measured force，也不能填 0N 冒充 force feedback |
| Hand-only Force-aware | 单独 schema/profile/required-state，raw signed force 与 canonical closing force 分开 | 带 force mode/threshold/hold 状态语义与具体 source phase 的 Target/Ack；不得借用 Position identity | source/transmission 审计、force unit/sign、phase/sequence/revision/freshness；未准入时 NOT_ADMITTED |

每一 leaf 的 Action/Target/Ack/Required State 都以独立版本 discriminator/identity 绑定 ordered canonical refs、算法/配置、TCP、source closure、Provider/build/backend 和 cadence。只对实际测试的模式开放；现有 ActionModeSpec、CanonicalControlTarget 与 AppliedCanonicalControl 能复用的字段复用，若 frozen payload 不足则另版 extension，不改旧 bytes。首个 R03 required 路线只要求两种 Position leaf；Force-aware 新 leaf 仅定义依赖和拒绝边界，未纳入装配必需出口，不因此扩大 R1 支持。

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

R02c 首先在既有完整 Panda 的两个 Existing-Entity Subcomponent References 上运行两个真正分离的 Arm-only / Hand-only writer，验证 leaf 算法/资源隔离与 H5；这与运行两个完整 Panda Controller 不同。若选择未装配的两个独立资产作附加样例，R02b 必须先交付其有界 source mapping/admission，不能假定已有支持。跨两个真实 Entity 的最终 split-leaf 执行、装配后载荷/耦合/状态与公开 env S3 由 R03c 必须验证；该选择不新增 R03b→R02c 的隐藏依赖。R04/R05 不是 Position-only 前置；Force-aware required-state 未准入只拒绝该 profile，不给 Position 强加力读取。
