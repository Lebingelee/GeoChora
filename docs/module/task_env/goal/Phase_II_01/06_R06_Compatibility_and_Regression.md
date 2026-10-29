# R06 — Compatibility / Mapping / Regression Governance

状态：REVISED_DRAFT；R06a Audit/S1交付已获Sol接收（ACCEPTED_AUDIT_S1_BOUNDED）；R06b attempt003已完成有界双case S1/S2交付，待Sol复核；历史原件/处置决定缺失使compatibility decision gate仍BLOCKED，R06c未启动。本 Goal 管理新支持交集与历史局限，不改 Phase II 接受决定。

## 映射与机械语义保护

| 检查对象 | 必需验证与失败边界 |
| --- | --- |
| Body/Joint/Actuator order | canonical typed name→native name/index/coordinate slice→逆映射，绑定 closure/Provider build/materialization；声明顺序、import order 与 native slot 不能假设一致 |
| Permutation detector | 刻意打乱 body/joint/actuator 列表，以可区分单资源输入验证目标、真实响应、state readback 与 H5 路径；错映射/alias/遗漏/重复在 apply 前拒绝 |
| Coordinate layout | qpos/qvel 各自 width/单位/offset；不把 nq=nv 作为通用合同，fixed relation 不伪造 DOF |
| Hand coupling | 两 finger 与一个 tendon actuator、Equality/mimic 的符号/比例、约束误差/限位、真实 driven resource；每个 finger joint 不一定有独立 actuator；禁止重复 writer |
| Inertia/contact/root | source 有声明≠solver消费；固定 child/root 处置、mass/inertia frame、collision filtering、接触/负载行为与 warning 要单列 receipt |
| Policy interface compatibility | 有序 action/observation、scale/offset/clipping/units/frames、clock/hold、reset/termination/语义保持；shape 相同不证明机制或 policy transfer 等价 |

复用 existing Scene/artifacts、source/import、ControlBindingPlan、typed state、Recorder/readers 和其测试 owners；不建立跨 Provider storage ABI，不访问 Provider 私有数组补 mapping。

## 版本、原件与 source-bound Evidence

保持 Scene v1/v2/v3 strict decode/mapping/hash、旧 Artifact/Entity identities、ResetSample/timebase、Position/R1 source-bound targets/acks、Recorder fault/T/T+1、旧 Provider capability manifest 与 UID/defaults。新 Assembly/Profile/Camera metadata 采用明确版本，未知字段/版本拒绝，不能用 global skip/删断言获得兼容 PASS。

三类历史 H5 原件：`geophys-transition-h5/v1`、canonical trajectory outer-v0、canonical-execution-v1，继续 **ACCEPTED-DEFERRED / MISSING_RAW_EVIDENCE / bytes compatibility NOT_PROVEN**。早期 GeoPhys eb870f6f typed-force JSON 被覆盖的原 bytes 仍 MISSING_RAW_EVIDENCE；同路径现存文件不是丢失原件，a53 新收据不能恢复它。历史 [B04a](../Phase_II/B_Development_Record.md#b04a) 与 [C02b](../Phase_II/C_Development_Record.md#c02b) 不回写。

只可从批准备份恢复原 bytes 并核 hash；synthetic、新格式 H5、摘要 hash 或相同任务重跑都不是恢复。Reader retirement/支持范围缩减必须另获维护者批准，并列精确 reader/格式/迁移影响，不自动执行。若不能恢复又没有 retirement/继续延期的本阶段独立决定，R06 compatibility decision gate 保持 BLOCKED；不能把 Phase II 旧延期当作 Phase II-01 自动豁免。

Evidence 分三栏：① 原 Phase II 固定 source/pin 收据；② 本轮仅文档/静态校验；③ 未来新 source/profile/Provider 交集的 S1/S2/S3。GeoPhys dual Position `4436787e` 不能改写为 a53 重跑；当前 a53 单 Panda/Camera pairing 不转移为 split-leaf Assembly 支持。未来 Provider pin 变化必须独立准入与新证据，旧 pin/原日志/原 hash 不移动。

## 分层回归与 Stop Conditions

每个 R01–R05 slice 在自己的提交前运行受影响旧路/negative detectors；R06b 是汇总 gate，不允许把兼容问题拖到 R06c。现有静态回归定位包括 [Scene composition](../../../../../task_env/diagnostics/tasks/test_phase_ii_scene_composition.py)、[legacy matrix](../../../../../task_env/diagnostics/tasks/test_phase_ii_b04a_legacy_matrix.py)、[Position profile](../../../../../task_env/diagnostics/tasks/test_phase_ii_c02b_position_profile.py)、[public candidate](../../../../../task_env/diagnostics/tasks/test_p99_public_position_candidate.py)、[pairing](../../../../../task_env/diagnostics/tasks/test_phase_ii_d05b_pairing_integration.py)。测试存在不等于本轮运行或新交集通过。

| ID | 前置 | 工作与交付 | 必需 Evidence / Stop Condition |
| --- | --- | --- | --- |
| R06a | P00 | 原件/备份可恢复性、版本/缺口 ledger、恢复/退休/继续延期待审批方案 | Audit/S1：缺失不改 PASS；没有本阶段精确决定则 compatibility gate 未关闭 |
| R06b | R06a,R01c,R02c,R03b | 新/旧 Schema、source、profile、native 顺序/coupling、UID/default/admission 正负回归 | S1/S2：错顺序、联动/资源/identity、版本误派发会失败；旧范围不退化 |
| R06c | R06b,R03c,R04c,R05c | 汇总所有 required 源码/Provider/backend/camera/reader交集，交付 P99 包 | S1/S2/S3 原始 receipts+checksums，FAIL/NOT_RUN/BLOCKED 分列；缺 required gate 不产生阶段 PASS |

P99 包应有 `acceptance_report.md`、`acceptance.json`、独立 `phase_decision.yaml`；记录 Core/tree、gitlinks/native build、source/closure/Scene/Assembly/profile/mapping identities、seed/reset/horizon、commands/预算、oracle/tolerance、T/T+1/H5/hash、failed/NOT_RUN/unsupported。事实由 evaluator 记录，维护者/Judge 独立决定；本轮不生成该未来 decision。

<a id="r06a-legacy-original-audit"></a>

## R06a 历史原件审计（2026-10-26）

审计边界仅复用 `evidence_index.json`、P00 `missing_originals.json`、所列 v1.1 备份/恢复索引和已知工作目录；未全盘扫描、未访问云端或其他机器。v1.1 L2 本地归档含22项有界证据副本，无一命中这四项历史域/路径，且不是完整工作区备份。source-recovery索引列出的7个manifest路径中，2个可读且未含目标域，5个在当前checkout中不存在。恢复清单没有列出以下四项原件。前三项的原件路径与原始文件 SHA-256 均为 `UNKNOWN`，索引无逐文件 bytes identity。B04a source-bound reconstruction 的 Core `f9543b8725d2990966743f49cebf9d68493b6b06` / GeoPhys `4436787e` 是重建来源事实，不能绑定为每个丢失文件的原始身份。

| 缺失原件 | 当前严格格式/读取路径与真实影响 | 原件/现存候选及历史身份 | 本阶段决定 |
| --- | --- | --- | --- |
| `geophys-transition-h5/v1` H5 | `RecorderConfig` 仍接受该 id/version；`TransitionRecorder.save_h5()` 可按 v1 写入。`inspect_trajectory_h5()` 可读容器摘要及 `meta/layout_json`，不重建完整语义轨迹；未找到独立完整 v1 loader 或 Core production replay caller。移除会影响旧格式写入/检查与兼容 fixture。 | 原路径/hash `UNKNOWN`；没有可信候选。历史 B04a 仅记录该 golden 缺失。 | 历史 `ACCEPTED-DEFERRED`；本阶段恢复/退休/延期均 `PENDING`。 |
| canonical trajectory outer-v0 H5 | `task_env.trajectory.canonical.h5.load()` 严格解析 v0 mapping、identity hash 与 numeric projection；`reference_replay.reexecute_selected()` 对 v0 调用该 loader 并走当前选定重执行。退休会移除该读取/selected replay 入口及对应 legacy matrix。 | 原路径/hash `UNKNOWN`；没有可信候选。B04a 重建 pin 仅作上下文，不是该 H5 的逐文件 source binding。 | 历史 `ACCEPTED-DEFERRED`；本阶段恢复/退休/延期均 `PENDING`。 |
| canonical-execution-v1 H5 | `execution.load()` 与 `streaming.load_streaming()` 接受 legacy v1 外层/逻辑 schema并校验hash/projection；`reference_replay.reexecute_selected()` 将非 outer-v0 路由至 streaming reader。`ExecutionRecorder` 构造器只创建 v2/v3，但模块级 `validate/save/load` 仍接受 v1 mapping。退休会影响读取、selected replay、legacy serialization及历史回归。 | 原路径/hash `UNKNOWN`；没有可信候选。历史 B04a 重建 pin 不等同于该 H5 的 bytes identity。 | 历史 `ACCEPTED-DEFERRED`；本阶段恢复/退休/延期均 `PENDING`。 |
| 早期 GeoPhys `eb870f6f` typed-force `s2_probe.json` 原 bytes | `test_phase_ii_c02b_r1_typed_force.py` 的诊断 probe writer 输出 JSON；未发现生产 codec/reader 或需要迁移的 production caller，因此不适用机械 reader retirement。 | 丢失原路径 `workspace/maintenance/c02b_r1_typed_force_20261022/s2_probe.json`；原 hash/Core pin `UNKNOWN`，GeoPhys 早期 pin 仅知短值 `eb870f6f`。同路径现有文件是后续 `c02b-r1-typed-force-probe-v1` 内容（7,664 bytes，SHA-256 `3c23764e877c067cd26d6af75f45127bbe5234c575dea5d69eb5118a0ac3bec7`），不是原件。 | `MISSING_RAW_EVIDENCE`；本阶段保留/排除该历史证据项的决定 `PENDING`。 |

当前没有批准归档成员或原始 hash 可供恢复；旧日志、mapping/identity hash、摘要、当前同路径 JSON 或新 a53 收据均不能代替文件 bytes。恢复选项需提供已批准来源、原件及可核验 SHA-256/来源链。若无法恢复，维护者可逐格式批准准确的 reader retirement/支持收缩（须接受上述调用者影响），或明确批准本阶段继续延期并规定该缺口对 R06c/P99 的后果；诊断 JSON 应按历史 Evidence 保留边界单独决定，不套用 reader retirement。所有选项的 `decision`、`approved_by`、`reference` 当前均为 `null`/未批准，Phase II 旧延期不自动沿用。

R06a 本轮定向 `test_phase_ii_b04a_legacy_matrix.py` 为 6 passed；它覆盖当前 codec/version route 与负例，不读取缺失历史 bytes，不证明 byte compatibility。Audit/S1 可交付但 compatibility decision gate 仍为 `BLOCKED_MISSING_RAW_OR_PHASE_DECISION`；R06b/c 与 P99 不得把它记作关闭。本轮没有改 reader、格式、source pin、DAG、Required Envelope 或 Skill。

## Sol复核（2026-10-26）

Sol审阅提交 `56f689570a0fbaf29aea4ea26a073d38b5e6afd6` 的四份文档差异、四项ledger及当前reader/caller边界，接收R06a为 **ACCEPTED_AUDIT_S1_BOUNDED**，无必需返工。20项输出、9项owner源码、13项审计输入、8项保护输入与11份phase文档摘要核验通过，复用6 passed日志；22项L2成员和7项恢复清单路径核对支持本包限定检索结论。四项原件仍未恢复，处置批准均为空，compatibility gate保持 `BLOCKED_MISSING_RAW_OR_PHASE_DECISION`。下一行R01b不增加原件恢复前置；R06b/c/P99 gate不因此关闭。复核入口为ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r06a_001/`。

## 与独立R07的分界

R06b新增R03b前置，以便对真实lowering/root与native顺序映射做回归；原R01–R06目的/required gates保持。Benchmark部署/Agent成本由独立[R07](09_R07_Benchmark_Deployment_and_Agent_Cost.md)所有，不并入R06c。R06仍保护旧Scene/Artifact/Recorder/Provider合同；P99同时依赖R06c和R07d，R07不是回写PhaseII兼容结论的理由。

## 与 USD / Harness 后继计划的分界（2026-10-28）

[10 补丁计划](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md) 规定新增 source/receipt/recording profile
版本化并保留现有 R02c/R03c exact reader；不能为接 Isaac 删除 MuJoCo3.8.1/64/65 的旧交集校验。
Harness 的 canonical H5 与 leaf Generic H5 各沿现有 owner 扩展，storage roundtrip 不代正式 replay。
新三 provider 运行保留精确 execution/source/build 身份，不回写旧 pin 的证据。
本页四项 missing raw/处置决定与 R06c/P99 阻塞保持，不以新资产验证报告或新 H5 自动填补历史 bytes。

## R06b attempt001 实施定位（2026-10-29）

维护者明确要求Luna2继续R04c之后工作。R04c已在camera提交`4d27651`有界接收；原表下一行R05b仍被R05a正式Provider合同阻塞，因此明确选择直接前置R06a/R01c/R02c/R03b已接收的独立R06b。复用`codex/phase-ii-01-camera`及既有工作树，范围从camera收口扩展到兼容性回归，不新增checkout；Luna1同时在develop-full仅做F00–F07，两边native共用同一排他锁，不并发运行。此顺序选择不关闭R05或历史证据处置gate。

| 既有owner/方法 | 本包实施与缺陷探测 |
| --- | --- |
| artifacts strict codecs、registry、既有legacy matrix/Scene composition | 固定旧mapping/hash、UID/default/action-observation顺序；未知版本/字段拒绝，不把缺失历史文件替换为新synthetic |
| `assembly/fixed_attachment.py::lower_fixed_attachment_sources`；source declaration gate | canonical/native名称和逆映射、声明顺序变化、alias/遗漏/重复、错误root/mount；不支持的物理变换在apply前拒绝 |
| `sessions/leaf_control.py::LeafMaterializationReceiptV1/preflight_leaf_control_interval/dispatch_leaf_control_interval` | 原子preflight、qpos/dof/ctrl独立映射、Writer ownership与不可区分目标的反例；有效重排不依赖tuple索引，错映射在写入前拒绝 |
| `sessions/mujoco.py::_make_fixed_attachment_receipt/admit_leaf_control_plan/apply_leaf_actuator_patch/publish_leaf_state` | 模型绑定显式mapping与真实响应；Hand tendon/equality/两个finger/单actuator保持原source语义，禁止用私有状态补公共能力 |
| 现有attached candidate、`load_leaf_control_records_h5`、`r03c_offline_readback` | 复用原S2/S3，按受影响输入补最小有界native；同文件state/Action/Target/Ack/clock/H5顺序与close一致，不修改旧exact reader门 |

Attempt001于2026-10-29完成源码调查、覆盖矩阵、detector/相邻fixture修复、provider-free S1、未受影响S2证据复用、报告与camera分支本地提交。新增native前置门要求完整worker链和冻结source/case/oracle/预算；本次无新增native，因为支持外的物理source顺序变体被既有精确source admission拒绝，现有accepted native source/profile未变。不能因同shape、构造成功或synthetic receipt断言声称物理重排支持。原缺件的compatibility decision仍BLOCKED；完成的新旧合同回归与未完成物理/历史范围分栏。交Sol复核后停止，不自动R06c、R05、R07或Isaac。

## R06b attempt001 实施结果（2026-10-29）

结果：`PARTIAL_BLOCKED_PHYSICAL_ORDER_PERMUTATION_PENDING_SOL_REVIEW`。实施提交 `0e8f09f` 只改既有诊断测试与测试夹具；没有生产API、Provider实现、source/asset、依赖或submodule pin变化。代码提交输入HEAD为 `2ed1ed5218b397d80bf062fc305fe166ebf9f410`。覆盖矩阵和逐项证据位于ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r06b_001/`。

| 栏目 | 实际结果与边界 |
| --- | --- |
| 旧版本/UID/default/Scene 与 public Position 路径 | 选定legacy、Scene composition、Position、pairing与candidate检查：`41 passed, 1 warning`；旧严格reader/identity路径未放宽。 |
| semantic mapping / preflight | R02b/R02c owner集合 `44 passed`；非对称Arm值在receipt tuple反序时仍按语义Joint/Actuator绑定到预期ctrl slot。另以明确synthetic `nq=9, nv=10` fixture 验证qpos/dof分别按`nq`/`nv`做边界检查，不外推到Panda。 |
| source order / Attachment / public leaf integration | R03b/R03c provider-free集合 `53 passed`；source-order static gate报告19项拒绝。更改Hand源XML兄弟顺序并同步source/closure/asset/Scene/plan identity后，现有`lower_fixed_attachment_sources()`因source joint order不符合canonical order而拒绝；这是拒绝门证据，不是重排source的物理成功证据。 |
| 精确source的S2/S3 | 复用Sol已接收的R02c005 Hand50、R03b exact Panda Arm+Hand固定树及R03c004 public attached-leaf证据。R03c004冻结source closure为70文件/34,318,679 bytes/SHA-256 `b97f7c4f9b585ef175e986b9fb59f3054de74184666373443d6d166a45609b63`，native freeze HEAD `4ac7284a4cf770f28a1c5d1f9c81337a6b39c66d`；相关生产owner文件在该freeze至本包输入HEAD间无差异。复用不是本HEAD重跑。 |
| 新物理顺序变体 | 未启动native worker；精确source合同没有准入改变顺序的source/asset profile。当前S1只证明此变体会在provider materialization前被拒绝。需要的物理重排成功/映射门仍 `BLOCKED_PHYSICAL_ORDER_PERMUTATION`，所以R06b不是完整compatibility regression PASS。 |
| 历史原件 | `geophys-transition-h5/v1`、canonical trajectory outer-v0、canonical-execution-v1及早期typed-force JSON原bytes仍缺失；byte compatibility未证明，处置未批准，compatibility decision gate保持 `BLOCKED_MISSING_RAW_OR_PHASE_DECISION`。 |

最终定向S1进程均在包预算内，最长墙钟54.10秒，十个provider-free/static进程累计墙钟152.54秒，最大RSS 1,760,472 KiB；`r03b_fixed_attachment_probe.py --static-only`未导入Provider/编译/step。native额度未使用，共享flock未取得。保留的早期失败日志记录了初始断言和夹具不完整；修复后各最终集合通过。完整命令、RSS、输出hash、输入保护hash、原始日志及复用矩阵见ignored报告。


<a id="r06b-attempt002-repair-plan"></a>

## R06b attempt001 Sol复核与attempt002实施定位（2026-10-29）

Sol复核camera `4d032f8`：33项输出hash、24项输入冻结校验及相关生产文件未变均匹配；接收 `ACCEPT_PARTIAL_S1_AND_EXACT_SOURCE_REUSE`，**R06b未完成**。本次未重跑测试/native。复核记录在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r06b_001/`。

需修正上文拒绝原因的解释：attempt001虽然同步了source/closure/Asset/Scene/plan身份，但没有改变Hand `Articulation.joints`的原tuple顺序；因此该负例证明XML声明与Scene关节顺序不一致会被拒绝，不能证明一致重排的Scene/source也无法lower。除此之外，Core admission仍钉死原source hash/Asset provenance，adapter仍钉死三类native顺序；这两处是新增物理变体的独立准入缺口。

| owner / 方法 | attempt002有界修复与验收 |
| --- | --- |
| `position_candidate/fixed_attachment_candidate.py::_entity_scene/_scene_and_bindings/_plan_and_source/build_fixed_attachment_candidate`；`attached_leaf_candidate.py::build_attached_leaf_candidate` | 在原构造链增加显式、内部使用的一种derived order recipe；Hand两个finger sibling子树反序，Arm七actuator声明反序。派生bytes与Scene Joint顺序一致；重建Asset/Assembly/plan/Artifact/reset/leaf/source identities并保留原默认bytes/hash。资产版本/来源明确派生，追踪原revision/hash和recipe，不能冒充原Menagerie文件。 |
| `assembly/fixed_attachment.py::_validate_source_declarations/lower_fixed_attachment_sources` | 复用严格声明检查；一份确定性recipe校验归此既有owner，确认只改变指定元素顺序。原始与新派生source配对均精确校验；任意属性/缺失/重复/别名/错Scene顺序仍拒绝。 |
| `runtime/sessions/api.py::_validate_fixed_attachment_materialization_source` | 在原exact pair之外，只准入上述可重建派生pair及其Asset provenance；不以caller boolean、仅自报hash或通用skip开放任意source。未知变体仍在native import前拒绝。 |
| `runtime/sessions/mujoco.py::_validate_fixed_attachment_scene_model/_make_fixed_attachment_receipt/_admit_attached_leaf_control_plan` | 原exact order oracle保留；为派生pair核验明确的body/joint/actuator顺序，semantic name→实际ID/qpos/dof/ctrl→逆映射由现有adapter生成。保留维度/root/mount/transmission/tendon/equality/limits/collision门。 |
| 既有leaf/Env/Recorder；`load_leaf_control_records_h5`；R06b诊断worker/reader | 先provider-free通过真实worker到final receipt及异常close链，再冻结实现commit、两case、source闭包和预算。一worker分别运行原始及派生recipe，各64步/65观测；同run public state/Target/Ack/clock/H5与独立reader对应。旧reader/profile严格合同不放松；若现有语义profile可原样容纳新source identity则复用，否则显式新分派复用Recorder。 |

预计90–180分钟，最多一次MuJoCo3.8.1 CPU worker、无重试、两次materialize/reset、128 outer/640实际mj_step、无render；与Luna1 F01共享排他锁。详细RAM/wall/output/等待及oracle限制由冻结工作包确定。未通过所有适用门只报告partial，不把S1拒绝或receipt tuple反序替代物理重排成功。历史原件处置保持独立BLOCKED；R05/R06c/P99未获解锁。attempt002争取收口；若核心门仍失败，第三次前须按项目Skill重新评估并调研，不自动续跑。


<a id="r06b-attempt002-execution-result-2026-10-29"></a>

## R06b attempt002执行结果（2026-10-29）

结果：`PARTIAL_NATIVE_COUNTER_INSTRUMENTATION_FAILURE_PENDING_SOL_REVIEW`。实现冻结HEAD为 `baa544dad4a024ec235f9209420de734ec59f797`，camera代码实现提交为 `baa544d`；同包文档/receipt提交另列manifest。native contract SHA-256为 `b65c2018c731ae91dc56022aa90a94164c6e3a172e1a6085a59ecbdbb00ea4f6`，只绑定上述HEAD、当前实现文件、两个source closure、case顺序/IDs、预算/oracle与保护输入。

| 门 | 实际结果 |
| --- | --- |
| provider-free S1 | 最终定向集合 **202 passed**；pytest 78.06s、采样墙钟78.51s、进程组RSS最大采样586,563,584 bytes，低于2GiB门。attempt001的未受影响exact-source S2只按原Sol接收范围复用，不冒称本HEAD重跑。 |
| native worker/锁 | 仅启动1次；共享排他锁等待约0.00002s并覆盖worker，worker退出码1、墙钟8.24s。监督器随后写 `lock_released_after_group=true`；失败收尾未保留RSS样本，峰值RSS未知。无重试。 |
| E1 pinned baseline | 一次materialization/reset，64 transitions/65 observations、320 `mj_step`/65 forward、0.64s；reset/mount、Arm运动/回home、Hand开合/equality、warning、Env close均通过。production H5 reader及worker严格tamper门通过；H5 SHA-256 `91624a7e930bfdb841bb4c0f28a13bcde5497a9cf7a83f2468d729d94e4034c1`。worker失败后另起零Core/provider-import raw reader读取此单份H5，T/T+1、named slots与same-run joins通过；该读回发生在锁释放后，只属于E1，不是完整同窗口reader出口。 |
| E2 derived order | candidate/source closure与冻结identity匹配，但在 public reset 的 materialize call 前，worker抛出 `R06b per-worker materialization budget of two attempts exceeded`。根因是 `_run_case` 每episode再次包裹已被上一case替换的 `control_module.materialize_control`，使E2单次包装调用嵌套增加同一全局计数；底层E2 materializer未调用，没有E2 native receipt、H5或物理顺序证据。 |
| 独立raw reader | E1单文件读取PASS；E2无H5。完整两case `raw_readback.json` 未生成，R06b S3/同run双case门不通过。 |
| 其余gate | E1的物理运动不代表派生顺序native通过；R06b总体状态保持partial，不能报 `R06B_BOUNDED_ORDER_REGRESSION_PASS_PENDING_SOL_REVIEW`。历史 `BLOCKED_MISSING_RAW_OR_PHASE_DECISION`、R05 provider合同阻塞、R06c/P99/Qualification均不变。不得在本attempt重试native；是否安排attempt003由Sol重新评估。 |

执行包与原始收据：`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r06b_002/`；完整worker失败trace在 `native/native_failure.json`，E1成功case在 `native/E1_result.json`，E1 raw读回在 `E1_raw_readback.json`，共享锁最终状态在 `native_window.json`。本次曾在provider-free目标集合之外误运行一个R04b pytest入口：该测试自身因冻结HEAD/clean-tree preflight在R06b dirty状态下拒绝，未到其worker/compile/step，但pytest进程导入了MuJoCo；此协议偏离已如实记录在 `report.md`/`commands.json`，不计入R06b S1且不抹除。


<a id="r06b-attempt003-reassessment"></a>

## R06b attempt002 Sol复核与attempt003前重评（2026-10-29）

Sol核对camera `4b74276`：178项输出hash（71,228,096 bytes）、native冻结640项代码及165项保护路径均匹配。接收部分S1/E1实际执行事实，决定 `ACCEPT_PARTIAL_E1_FACTS_WITH_REWORK_REQUIRED`；R06b未完成。无Sol新native或测试套件重跑。完整复核和开源调研/可行性记录在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r06b_002/`。

除了已报告的materialize wrapper跨case重复嵌套，还需修复：worker把空dict而非共享active传给case，导致trace归因不完整；S1未跑真正worker双case/finalizer；supervisor失败路径未保存RSS采样。不能通过提高两次materialization上限修复这些问题。

**修正上一包设计：canonical Joint order无需等于source traversal。** attempt002改变通用`ArticulationDefinition.joints`规范化，在同一v1 schema下使未排序旧输入的canonical mapping/identity变化，未获兼容接收。003必须恢复原joint_id排序，将特定source遍历顺序留在严格source recipe和native receipt中，通过显式name mapping衔接；不是新建schema或放宽任意XML。

| owner / 方法 | attempt003最后一次有界修复及门 |
| --- | --- |
| `artifacts/contracts.py::ArticulationDefinition.validate`；Scene strict codecs；既有Scene/identity测试 | 恢复旧排序；逆序输入构造/解码/serialization/hash与旧规范化一致。原始默认Task/Scene身份不变。 |
| `assembly/fixed_attachment.py::_validate_source_declarations/lower_fixed_attachment_sources`；既有recipe/helper与candidate | canonical覆盖和named拓扑/type/axis/pose校验不变；在独立校验原exact或唯一derived recipe之后，按该recipe校验XML traversal而非要求canonical tuple等于native顺序。保留unknown/bytes/provenance/alias/missing拒绝；不得仅改set去掉source顺序门。 |
| `r06b_order_worker.py::_run_case/run_worker` | 一个scope owner安装/恢复materialize查找别名及step/forward hooks；不累计wrapper。共享active传给case；总计和case计数分开。真实双case worker/finalizer provider-free成功/失败与原hook恢复通过再native。 |
| `r06b_order_supervisor.py::run_supervisor`；原raw reader | 所有成功/失败路径保存已观测RSS、primary/cleanup和锁收据；未知不能报0。真实engine import须限制于唯一worker；S1显式清单/guard，完整argv可审计。 |
| 原Env/leaf/Recorder/production reader与raw witness | 一worker两case仍各64/65、320step，累计128/130、640step、1.28s；原物理/identity/reader门保留。新closure/Scene等变更后重新freeze，旧E1/失败原件不改。 |

前置重评结论 `FEASIBLE_WITH_BOUNDED_REWORK`：Python标准库contextmanager/ExitStack、unittest.mock的scope恢复、pytest monkeypatch.context可借鉴，无需新库/框架；MuJoCo官方named resource映射与已有adapter适配。引用与取舍见重评。E2从未真实编译/步进，物理结果仍未知，不能保证第三次通过。预计90–180分钟，仅第三次完整实施/验证/收尾包，最多1worker，无重试，仍与Luna1共享native锁。003若失败即报告未完成交回维护者，不自动第四次、不改变原required门。

R04b误导入MuJoCo与argv未保留的偏离保持记录。历史missing raw/Phase处置、R05、R06c/P99与Qualification均不改变；本包不进入R07或F线。主checkout由Luna1持有，不触碰其dirty文件。

独立reader补充复核：`run_readback`还需重算contract digest并将worker result的exact两case、H5 hash/size、receipt/materialization/counters逐项与实际文件绑定；单纯H5内部self-hash不足以排除错run。003补这些原same-run门的反例，整理tamper清单名与实际执行结果的对应，不新增物理范围。


<a id="r06b-attempt003-maintainer-window-correction"></a>

## R06b attempt003维护者执行窗口纠正（2026-10-29）

维护者明确：一次attempt允许预定时间内多轮代码修复、测试和native验证；不能因Sol默认设置的“一次native启动”用尽就结束。未解决时，预定时间耗尽或确需Sol外部指导才结束attempt。此前报告、运行失败与attempt编号保留，不重写历史。

在途003已按维护者改向停稳，camera HEAD `d3ea90c`、clean；约22分56秒主动窗口已用，7次S1累计约219秒，native启动0次。现有代码/全部检查输出保留，不另开attempt。主项目Skill与AGENTS已明确该语义；恢复包修订同一003的运行合同，保留已用时间和run ledger。剩余主动时间9424秒（180分钟减原窗口1376秒），控制暂停与外部锁等待另记，不能恢复成全新180分钟。

新规则：每次native run仍限一个worker、原2case/128 outer/640 step/1.28sim秒、300秒wall、4GiB RSS与共享排他锁；这些是每run上限。允许在剩余窗口内定位普通故障、修复、重新S1并另起新run目录/合同，逐run保全失败和累计成本。不再默认将一次失败视为attempt结束。单run输出256MiB、整个003累计1GiB；不能删除失败证据或拼接多run为一次PASS，遇资源/外部阻塞安全暂停并说明。最终成功run仍须独立满足baseline+derived同worker全部原门。

本次是003合同修订，不是004，也不恢复001/002或触碰F线。旧003冻结包只读保留；替换包与新hash由Sol冻结后派发。完整暂停/替换收据在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_attempt_semantics_correction_20261029/`。

<a id="r06b-attempt003-execution-result-2026-10-29"></a>

## R06b attempt003恢复窗口执行结果（2026-10-29）

结果：`R06B_BOUNDED_ORDER_REGRESSION_PASS_PENDING_SOL_REVIEW`。这是一个完整的同worker E1 baseline + E2 derived order recipe bounded S2/native结果，尚待Sol复核。它不关闭通用compatibility、R06c/P99、R05 Provider合同、历史原件处置或Qualification。

| 项目 | 实际结果 |
| --- | --- |
| 冻结与实现 | attempt编号仍为003；从合同修订后的resume input HEAD `a6831128e9494cca682943cad410ecacd58d74d7`继续。native实现冻结HEAD为 `03fba40873e651b0831ed040fec93ea12655642c`，分支 `codex/phase-ii-01-camera`。恢复后实现提交 `f6668e2c711d06bea783844ed485379fa9a9f4b2`、`03fba40873e651b0831ed040fec93ea12655642c`；此前attempt003实现提交保留在report/evidence。GeoPhys/Menagerie pins未变。 |
| S1 | 同一11文件provider-free集合在两个clean implementation HEAD分别通过 **249 passed**；最终运行墙钟128.78s、最大采样进程组RSS 201,252,864 bytes。测试真实调用双case `run_worker`/`_run_case`/finalizer/strict loader/raw reader/supervisor控制流，并以明确synthetic model/data IO隔离物理engine；import tripwire在collection前后及测试后均未加载MuJoCo、Isaac、GeoPhys、Taichi。 |
| 首轮native `run_001` | 单MuJoCo 3.8.1 CPU worker在共享flock内完成E1/E2各自64 outer、65 observations、320 `mj_step`、65 forward及H5，但独立reader因worker `native_counts`缺少case `episode_id`退出1。监督器记为 `NATIVE_SUPERVISOR_FAILED`，未计作PASS；worker与reader完成后释放锁，采样RSS峰值395,603,968 bytes。保留原结果、H5与失败日志。 |
| 修复与重验 | 在已有worker owner补齐per-case `episode_id`并加回归断言，提交 `03fba40`。重新运行完整S1和静态native preflight，再以全新contract与 `run_002` 复测；未复用或覆盖 `run_001`。 |
| 成功native `run_002` | 合同SHA-256 `758742668720d00ee2f5c6727d282fdd856fbfe942db76dbe756aa1d81706c40`；单worker同进程顺序运行E1 exact baseline、E2唯一derived recipe。每case一次materialize/reset、64 outer、65 observations、320 step、65 forward、0.64 simulated seconds；总计2/2、128、640、130、1.28秒。worker与独立reader均exit 0；状态为 `R06B_BOUNDED_ORDER_REGRESSION_PASS_PENDING_SOL_REVIEW`。 |
| 顺序、H5与锁 | E2完整交换Hand finger sibling subtree并反转七个Arm actuator声明；raw receipt/native model的body、joint、actuator order和按名字映射到真实ID/ctrl slot符合合同，Hand资源与控制语义保持冻结oracle。两个H5各为64 transitions/65 observations，production reader和独立raw reader通过；reader重算合同digest并逐case join worker H5 hash/size、receipt、materialization ID、计数与named order/slot。共享锁覆盖worker、reader及cleanup后释放。 |
| 资源/成本 | run002 worker墙钟13.38s；采样进程组RSS峰值413,986,816 bytes；开始时可用内存11,087,433,728 bytes；输出73,104,010 bytes，低于每run 256MiB。两个物理启动累计materialize/reset各4、outer256、step1280、forward260、模拟2.56秒；累计run输出146,210,149 bytes，低于attempt 1GiB。 |
| 局限 | E1/E2结束均为 `horizon_reached` 且 `task_success=false`。证据只覆盖冻结Panda Arm+Hand source、r06b-order-v1 recipe、MuJoCo 3.8.1 CPU及该有界配置；不代表任意source/provider兼容。四类历史原件及Phase II-01处置仍 `BLOCKED_MISSING_RAW_OR_PHASE_DECISION`；R05 Provider合同阻塞、R06c/P99未关闭、无Qualification。 |

完整报告、command/resource收据及sha256清单位于ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r06b_003/`；其中 `resume001/runs/run_001/`保留reader失败现场，`resume001/runs/run_002/`是独立完整成功run。该结果待Sol检查actual diff、manifest和available Evidence后决定是否接收。
