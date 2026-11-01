# F05–F07 后继执行指南与 Codex 工作包合同（规划方向已采纳；F05 successor attempt001 S0已执行）

> **当前执行范围（2026-11-01）**：遵循维护者批准的[原生适配裁定与最小验证集](13_F05_Early_Diagnostic_Three_Goals.md#f05-native-adaptation-scope-decision)。DG04 window004 续包准备供人工转述；Luna 仍暂停，未派发或执行。历史完整源柔顺/传力等价门不作为新路线前置条件；历史运行、失败及接收范围保持。压缩恢复只读取新包、当前一页状态和必要证据，不完整重读历史快照/账本。

> **Status: PLANNING_DIRECTION_ADOPTED / ATTEMPT001_REVIEWED_PARTIAL_REWORK_REQUIRED / ATTEMPT002_PREPARED_NOT_DISPATCHED.** 本文的阶段设计规格保留原规划含义；2026-10-30冻结首包已完成静态S0、诊断实现与定向验证。该结果不启动S1/F06/F07，也不改写旧F05结果。后续002仅按第9节新完整包，在前置门满足且维护者转述后有条件允许native。
>
> 原网页稿SHA-256：`6107b5a70a09b16aa7b06da7617bef0dae44fff1cbdf93139c2b6ad03ac78b5f`。本文与[11的仓库约束澄清](11_F05_F07_Multi_Asset_Solver_Recovery_Plan.md#repository-adoption)共同使用；`develop-full`是F线规划owner。

## 1. 适用输入和不会改变的事实

- 本提案审阅基线 `develop-full@b24a1ac84bbfb32f91864ddc8121ea8af23a6c31`。先读取 `AGENTS.md`、GeoChora/TaskEnv 模块 Skills、[07](07_Execution_Order_and_Acceptance.md)、[10](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md)、[11](11_F05_F07_Multi_Asset_Solver_Recovery_Plan.md)、当前 `planning_manifest.json`；实际 dispatch 重新检查 HEAD/dirty/submodule/active writer。
- 不改冻结 F00–F05 接收事实、不覆盖 ignored raw、不隐含新 attempt04；只对新输入单元重新取得证据。
- 项目唯一 Core Runtime/Recorder/Controller/factory；不允许读取 solver-private 数据补齐缺失 public 属性。实验 Oracle 独立于生产状态。

## 2. 后继stage及前置门（实际工作包可按已知owner组合）

### F05 successor stage S0 — Menagerie Source-family / Feature Inventory（默认先行；仅静态）

**目的**：查清现有 `franka_emika_panda` MJCF 与 F04/F05 `local_menagerie_panda_r009` USD 的真实对应关系，识别与旧官方 Panda 不同的完整物理特性。

**允许**：只读源、Py/文本级 parser、现有 delivery/report/manifest 校验、provider-free tests、报告与定向文档/Skill更新（待授权）。**不允许**：Kit、MuJoCo/GeoPhys/Isaac/Newton solver 初始化与 physics step、自动下载替换原资产、实际转换覆盖旧 r009 文件。

**冻结输入**：`develop-full` HEAD、Menagerie gitlink SHA、source `panda.xml` 与依赖 SHA、F04/F05 现有 r009 交付原始 byte closure、recipe/checker/report SHA、Provider Build/Device Profile、历史 evidence locator；不可用时报告 `SOURCE_UNAVAILABLE` 而非猜测路径。注意 F04 local validated delivery ≠ upstream verified。

**Source Inventory**（machine-readable + review.md）：

| Feature | Original MJCF | r009 USD | GeoChora Canonical | Isaac native | GeoPhys native | MuJoCo native | Disposition |
|---|---|---|---|---|---|---|---|
| Bodies/joints/frames | exact count/names | exact count/names | entity-qualified | readback | readback | readback | verified/missing |
| Joint axis, limit, sign | source values | translated values | SI/frame | measured | measured | measured | same semantics? |
| Hand equality/tendon/mimic | source semantics | retained/derived/lost | typed relation? | consumed? | consumed? | consumed? | no synthetic equivalence |
| Actuator/drive | source formula | generated gain/mode | control target | target/ack | target/ack | target/ack | effective vs authored |
| Mass/COM/inertia/collision | source fields | transformed fields | physical values | independent check | independent check | independent check | losses |

**S0 gate**：不能用旧r009的9驱动native结果推定原MJCF的8-actuator/equality/tendon已等价；机器人和cube/support一起盘点。完整来源闭包；每个本任务关键 feature 有明确分类 `preserved / converted_verified / unconsumed / unsupported / unknown`；不存在隐性丢弃；原始与派生来源的 revision/recipe/bytes 绑定；5–10 个显式负例：缺 mesh、错 SHA、坏 frame、颠倒 joint order、不支持 mimic、错误 source revision、伪造 upstream verified、下游未消费字段。无 reader/native 的结果一律不报 runtime supported。

**输出建议**：`source_family_manifest.json`、`feature_coverage.json`、`equivalence_checks.json`、`report.md`、`input_sha256.manifest`、`output_sha256.manifest`，实际检查的 commands/results，未知保留。

### F05 successor stage S1 — Shared Panda Cross-Representation Core Cell（仅在 Scope Decision 后）

**目标**：同源 Menagerie Panda 在有证据的 MJCF/MuJoCo、USD/Isaac 和 USD/GeoPhys 执行路径上证明相同的 Canonical 对象/Joint/Frame、动作含义及可读取 State/Task；**不是 same USD three-provider closure**。

**实施原则**：优先 COMPOSE 现有 `UsdAssetDeliveryLocalV1`、`UsdRuntimeSourceV1`、`resolve_provider_representation`、`SceneDefinition v3`、`NativeRuntimeIO`、Position leaf/controller、CanonicalStateView、H5 Reader。必要版本化 extension 仅在 S0 发现不能由既有 owner 表达真实 feature 时允许；不绕过 required checks。

**前置**：S0 Source Family PASS、Scope Decision、真实 native 准入与每个 Provider 独立预算、完整 frozen input/r009 输出、对应 production caller 和原始 Reader 当前可用。F04/F05 已接受 cell 可用**原证据复核**代替无关 native 重跑，但不能据此自动完成新的 source-family 特性验收。

**验收顺序**：环境构造/reset/public state/close → 空载hold与点位追踪稳定性 → gripper/free-body → Task；不能以FK自洽或Ack代替追踪精度。目标误差、漂移、稳定时间和physics/close阈值先冻结。

**最小可观测验收**：同一 Env 的 public construct/reset/step/close；一致且有显式对应的 Task/Joint/Frame/Action 逻辑身份（representation/Artifact精确hash各自保留）；相同 SI/unit/quaternion/COM contract；关节位置写入与独立读取；gripper 两指/fanout/equality/tendon 关系按实际来源准确说明；position target→native ctrl→Ack→native state 的链；1 个自由刚体/contact oracle；H5 T+1 rows、Reader tamper、worker/plan/source/producer/hash 和 exit/lock，负例拒绝。允许数值轨迹不同，但物理单位/引用和请求意义不能不同。Task 成功必须独立于接口 ACK，且需要 Task Predicate 实测。

**判断结果**：`CELL_PASS_BOUNDED`、`PARTIAL`、`BLOCKED_BY_FORMAT`、`BLOCKED_BY_FEATURE`、`SOURCE_UNAVAILABLE`；每个 provider+build+source+representation 独立登记，不概括为通用支持。

### F05 successor stage S2 — USD Decoder / 官方 Panda 兼容（可独立排期）

分离为两个**独立审查单元**，不能为通过另一单元默默改变来源或降低门：

**S2a MuJoCo USD build**：先做只读/无 solver 的 Decoder Build Capability check；固定精确 3.8.1 lib SHA、USD-enabled build recipe、plugin registry、content type 与依赖闭包。只有获得独立执行批准后，才进行 same r009 USD 的 Core/native 读写、H5/物理验证；现有 wheel decoder 不可用仍报 BLOCKED_BUILD。可保留 source MJCF native 作为 A 路线，不可替代 B 路线。

**S2b 官方 Panda GeoPhys**：从原 `maxDepenetrationVelocity=+inf`、`maxLinearVelocity=+inf` 与 `PhysxMimicJointAPI` authored 来源建立 Schema/Consumer 对照；先解决无限上限是否具有正式含义以及目标 host 是否有等价约束，再检查 mimic gearing/ref/offset 的有效消费。没有等价物时 fail closed，不将 `+inf` 无依据截断、不通过双指同时写命令假冒物理耦合，也不修改原输入哈希。

**S2 gate**：每个特性必须有源→规范语义→目标 public host model→native consumption→验证证据的链；缺一则保持该 cell 不通过；只做 parser 修复不能报告 solver supported。

### F06 — 真实 Task Harness（按原门，不以 smoke 代替）

在维护者显式选择的 ready cell 上构造真实资产+Task，而非 mock-only。沿用 F00 的任务生命周期修复、四报告/Oracle、20 seeds、独立 Expert/Task/Lifecycle/Storage/H5、pending Judge。明确排除 invalid/fault/expert_failed 伪成功；Task On/In/region 不替换为 lift。可以先一个 Menagerie Panda+cube 的 Pick/Lift task，与具体 Task 成功定义精确绑定；状态/控制一致性仅是必要条件，不是 Harness 通过充分条件。

### F07 — 混合资产与 Provider 覆盖（候选扩展）

先资产源闭包不同但具有共同 SceneDefinition/Task 语义的两个实体（例如 Menagerie robot + USD rigid fixture）；验证组合、独立来源和依赖闭包、几何、Frame、collision、reset、state/control/Task，再增加可动 Drawer/Attachment。最终针对 Newton 的具体 host/build/solver profile 单独增加一个新 column/cell；不因 Isaac Lab 的 upstream Newton 支持自动宣称 GeoChora 通过，也不把 F07 变成完整 v3 HPG 项目。

## 3. 工作包模板（每次 Sol 必须填写真实值）

```yaml
package_id: TO_BE_APPROVED
scope_decision: EXACT_SUCCESSOR_CONTRACT_TO_FREEZE
branch: develop-full
input_head: TO_FETCH
writer_window: TO_CONFIRM
source_family: menagerie/franka_emika_panda
source_revision_sha: TO_MEASURE
source_closure_sha256: TO_MEASURE
representation_sha256: TO_MEASURE
recipe_sha256: TO_MEASURE
provider_build_identity: TO_MEASURE
solver_backend: TO_DECLARE
device: TO_DECLARE
required_features: TO_FREEZE
expected_public_call_chain: [make_env, admission, reset, apply_control, step, canonical_snapshot, recording, independent_reader, close]
allowed_owner_changes: TO_REVIEW
negative_tests: TO_FREEZE
native_allowed: false
native_budget: NOT_AUTHORIZED
resource_budget: NOT_AUTHORIZED
source_protected_paths: TO_LIST
output_dir: TO_FREEZE
report_status: NOT_RUN
```

这个模板仅帮助冻结输入，不自动允许 `native_allowed=true`。资源/运行时间必须来自对应新包的维护者授权，而不是继承旧 F04/F05。所有异常/partial evidence 保留，不清除旧报告。

## 4. 验收分层和否决规则

`G0` source/revision/closure/license/recipe 原始 byte 可验证；`G1` 结构语义与依赖特性完整，丢失有审计；`G2` Provider build/solver/asset 匹配与 capability admission；`G3` public actual model and state/control/physics；`G4` Task success/Expert/Oracle/Recorder/H5/Reader；`G5` independent Sol/Judge 复核。早期门通过不得升级为后期 PASS。

明确拒绝：fake pose/FK、native target 数组顺序猜测、未计步 physics、读旧 timestamp、mock 伪装真实、reader 缺记录、H5 输入与 native producer 不绑定、原始 USD 或 MJCF byte 被不明转换覆盖、忽略终止与 timeout、用包含参数的文件替代 solver 真实消费证明、用 source family identity 替代 exact representation SHA。

## 5. 接收与文档同步

Luna 仅执行一个已授权包，提交包内 local commits 和原始路径/命令/ledger；Sol 在 writer 释放后独立复核证据与 diff，再给出精确 `ACCEPTED_BOUNDED` 或 `PARTIAL/BLOCKED`。历史原件保留不可追溯改写。本轮已按维护者要求同步规划入口、README、manifest与Skill；原F05冻结gate和历史结果保持未通过事实。首包以新Scope Decision明确A路线的新required/deferred表与F06 ready-cell依赖，才可授权执行；不得从本轮文档提交推断已派包。

## 6. 本轮接入与后续派包检查

- 原F05三次普通attempt不重置，successor范围与计数另记；本轮successor窗口数为0。
- S0/S1/S2是路线stage，实际一个完整窗口可包含已知owner的调查、实现、定向验证与收口；避免仅为填表分出准备attempt。
- 一个包冻结累计资源及修复重跑权限，每run记录真实代码/来源；不默认单次launch或沿用旧F04/F05启动预算。
- 旧native证据必须按[11第9节](11_F05_F07_Multi_Asset_Solver_Recovery_Plan.md#repository-adoption)确认覆盖范围；关键语义差异未解决则BLOCKED_BY_FEATURE，不只比较关节名称或hash。
- F06不以状态/控制smoke代替真实任务20-seed/Expert/Oracle/四报告/pending Judge；F07与原R07路线分开。
- 三条分支的规划文档分别同步；camera已在维护者确认writer释放及实际HEAD/补丁检查后落地，实际提交见manifest同步记录和收口回执。文档同步不等于实现合入，也不授权执行工作包。

## 7. 维护者后续指令与首包

维护者于2026-10-30要求重新按新F05路线设置三个attempt并构建首包。执行以[11首包合同](11_F05_F07_Multi_Asset_Solver_Recovery_Plan.md#successor-attempt001-contract)和冻结包为准：三个窗口跨successor S0/S1共享；001是静态审计工具、负例验证与下一实施方案，原三次F05不重命名。转述本完整包后仅授权001范围，native仍为0。准确INPUT_HEAD、保护路径、allowed owners、机器输出、否决门和预算见`sol_f05_successor_001/input_snapshot.json`与`luna1_prompt.md`。后续scope变更须由维护者明确裁定；不用缺失的旧ignored fixture或共同名称推断等价。

## 8. attempt001 Sol复核后的返工入口

完整S0 inventory PASS尚未接收，复核状态`F05_SUCCESSOR_ATTEMPT001_REVIEWED_PARTIAL_REWORK_REQUIRED`。来源/原始字段采集与零native证据保留；下个窗口针对[11所列原包缺口](11_F05_F07_Multi_Asset_Solver_Recovery_Plan.md#successor-attempt001-sol-review)补齐真实诊断路径、authored apiSchemas、有效默认及单位/惯性/传动静态核验和具体owner决策。S0 inventory可在真实物理差异未解时PASS，但须完成盘点与缺陷检测；不以所有特性unknown代替可执行静态调查。尚未批准S1 native，F06/F07未启动，窗口计数1/3。


## 9. attempt002：返工与实施合并、按cell条件native

当前冻结方案以[11第12节](11_F05_F07_Multi_Asset_Solver_Recovery_Plan.md#successor-attempt002-contract)及sol_f05_successor_002完整包为准；attempt002现已完成且2026-11-01续行已经Sol复核为`F05_SUCCESSOR_PARTIAL_REVIEWED_DG03_CONTINUE_REQUIRED`。R1–R4真实S0修复及DG03 current-HEAD synthetic Core S1已完成；DG01/DG02各自有界结果保留其独立profile范围。DG03 mimic positive/完整关系ablation仅为N1诊断，source `solimp`、fixed tendon consumer及drive/contact语义仍阻止正式Isaac N2。required物理语义与旧门保持，不把源8actuator误作8DOF，也不把合法joint遍历排列当身份错误。详见[attempt002 continuation](11_F05_F07_Multi_Asset_Solver_Recovery_Plan.md#successor-attempt002-continuation-20261101)。

正式cell必须先闭合关键source→public model→consumer语义。2026-10-30初次检查时三个formal cell均未启动；随后DG01/DG02分别完成独立有界cell，DG03完成synthetic S1及一对N1诊断。DG03正式N2仍因source-compliance、fixed-tendon与drive/contact consumer gap阻断。静态inventory PASS不提升为cross-representation readiness。Sol于2026-11-01复核接受本轮partial证据，不接收DG03 Goal或新F05整体。完整Gate和阻断证据见[11 attempt002 continuation](11_F05_F07_Multi_Asset_Solver_Recovery_Plan.md#successor-attempt002-continuation-20261101)及[Sol review](../../../../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_f05_successor002_continuation_20261101/sol_review.md)。旧F05 PARTIAL不改，F06/F07不启动。


<a id="f05-early-diagnostic-three-goals"></a>

### 2026-10-30维护者指定提前诊断：三个长期Goal

当前执行入口改为[13提前诊断Goal编排](13_F05_Early_Diagnostic_Three_Goals.md)：DG01共同基线＋MuJoCo/MJCF、DG02 GeoPhys/USD、DG03 Isaac/USD＋三路线收口。普通successor001/002与2/3历史保留，普通003不派发；明确指定的诊断窗口另记，无固定attempt上限，资源预算仍严格。每Goal必须持续实现和取得真实Core/native/reader证据；缺profile/receipt是工作项，不自行结束为BLOCKED。允许完整route未就绪前的有界N0/N1模型/特性探针，最终N2生产门不降低。DG01与DG02均有其精确有界Sol接收；DG03为partial且仍active，后续窗口须依据Sol复核后的HEAD/证据和预算重新冻结。F06/F07未启动，旧F05partial及required物理语义不变。

### DG01 Goal01 执行结果（2026-10-30；候选通过，待Sol复核）

DG01以单独的长期诊断Goal执行，不是普通successor attempt004。原Menagerie MJCF、派生cube/support scene与当前Core/MuJoCo CPU路线已完成S1、N0公开模型编译、N1 tendon/equality/限力探针及N2同Env双episode正式cell。N2接受3,000 physics steps；worker exit=0，两个H5分别为301 observations/300 transitions；独立reader通过全部14类负例。精确范围、物理门、plan/source/code hash、失败attempt、资源与过程收据见[13第7节](13_F05_Early_Diagnostic_Three_Goals.md)及ignored输出`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f05_diagnostic_goal01/window_001/`。

候选标签为`F05_DG01_MUJOCO_CORE_CELL_PASS_PENDING_SOL_REVIEW`。普通F05仍`F05_OVERALL_PARTIAL`；GeoPhys/USD与Isaac/USD路线尚未执行，不能由MuJoCo结果推断等价。DG02只有在Sol独立接收DG01后，按真实HEAD和语义变化重新冻结包；F06/F07、Qualification均未启动/授予。
