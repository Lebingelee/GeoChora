# Phase II-01 — Execution Order / P99 Required Envelope

状态：REVISED_DRAFT / AWAITING_MAINTAINER_GOAL_DAG_APPROVAL。以下是7父Goal/22切片**建议表**，不继承Phase II的PASS。P00核查已完成；R03a两个有界native case经Sol复核接收为`ACCEPTED_BOUNDED`，R01a静态合同/S1与R01b resolver/S1已获接收。R02a attempt001已交付实现与 provider-free S1，等待Sol复核；本表不自动授权后继slice。DAG与Required Envelope未获最终批准。

## 基线、P00 与证据记账

以 [00 基线](00_Phase_II_01_Blueprint.md) 的develop/gitlinks为规划输入；该次远端readback属于规划复核时点。新P00从Core `259f27f…`重新核查refs/source/build/env，保全工作区与Evidence，并在现有 [manifest](planning_manifest.json) 的P00审计条目及ignored事实收据记账。P00核查不等于实施准入；R03a attempt001/002只按各自维护者指令及精确source/case记账，不扩展其授权范围。

R03a直接依赖 **P00**，与R01a同属早期可启动项，不等待R01 codec。R05a同样是独立Provider gate；R04/R05对R01/R02/R03 Position执行**无前置边**。下面编号是一个合法拓扑序；依维护者2026-10-25要求，默认按此顺序逐包推进，不因DAG允许独立执行就自动并行或逐Goal开新分支。

<a id="sol-luna-workflow"></a>

## 阶段分支、逐包提交与Sol/Luna闭环（2026-10-25）

本节记录维护者已明确的开发流程，复用[仓库规则](../../../../../AGENTS.md#phase-branch-workflow)；不批准尚未获准的slice、Required Envelope、Provider合同或Qualification。

| 计划项 | Phase II-01安排 |
| --- | --- |
| 计划内开发topic分支总数 | **1**，P00及后续R01–R07/P99在本阶段共用 |
| 复用分支 | `codex/phase-ii-01-p00-20261023`；保留既有名称，职责扩展为本阶段集成分支 |
| 新增worktree | **0**，复用当前checkout；已有历史/冻结worktree原样保留 |
| 追加分支/worktree的适用情形 | 恢复、需独立保留的方案、网页/独立审阅后确需隔离比较或整合；先记原因、base、范围、总数变化与回归/整合去向，讨论本身不要求新建 |
| 默认任务粒度 | 一个明确授权、前置齐全的slice/子阶段工作包；多个工作包共用上述分支 |
| 产出与提交 | 每个有界产出关联本地commit(s)；报告列slice/attempt、输入/输出HEAD、commit及Evidence hash/入口；不将多个未完成Goal混为一次提交 |

默认闭环：

1. Sol按下表顺序选择下一slice，核前置/授权/readiness，交付一个完整代码框Prompt及可选同内容文件；给出owner、真实HEAD/branch、保护路径、允许修改/本地提交范围、验收/oracle/预算、失败/关闭规则和报告格式。不惯例为每个Prompt重新要求已获批准的范围，不将流程补充扩大为功能授权。
2. Luna作为该包唯一写入者，完成实现和相应文档/Skill同步，执行必要检查；有界stage并创建该包允许的本地提交。报告PASS/FAIL/BLOCKED/NOT_RUN、实际commit、raw Evidence、未执行项及限制，然后交回，不自行开始下一slice。
3. Sol转为复核写入者前，先只读核对Luna实际HEAD/diff、关键代码、原始Evidence及最小缺陷敏感复核。Luna自报PASS不自动接受；范围内验收和提交可核对后，Sol在现有状态入口/manifest/history记录结论，必要的复核摘要形成有界本地提交，再发送下一slice包。
4. 失败时Sol给一个明确返工包，复用同一分支；不放宽oracle或跳required gate。若下一行被阻塞，可继续其准备工作；要先推进独立ready行，Sol须记录原因、未变DAG和范围依据，不静默改顺序/新增依赖。

AUDIT_ONLY包若仅允许ignored目录写入，原始日志/草稿仍不提交。Luna交回facts，由Sol这一指定owner将可维护摘要/索引写入既有文档并提交，建立audit→review→commit对应；不要求空提交或为了提交把raw workspace追踪进Git。Sol/Luna不同时改同一文件；各包允许的tracked写入清单及提交owner必须明确。

2026-10-26维护者补充：按复杂度组织工作，不固定套用准备轮次。已知owner的基础改动由一个授权包完成实现、定向验证、范围内修复和提交；只有影响实现决策的未知项才另做准备。普通代码缺陷在同一包内修正，保留失败证据；需改变范围、已冻结oracle/预算或真实外部阻塞时再交Sol决策。复用未受影响的既有证据，不重复全仓hash、历史审计或已通过实验。Sol直接修正小问题或带入实施包，不能为报告格式、未准入扩展或未知native结果反复增设准备前置。

P00-L02 attempt002由Sol收口后，下一包进入R03a具体实施/执行授权决定；不默认第三轮准备。未知compile/动力学结果由R03a有界probe回答，准备审阅通过不保证native PASS，也不授予R03b/c或Qualification。具体source/oracle/预算/执行可由同一次维护者指令覆盖；机器记录引用该真实指令，不要求四轮签字。

每个Luna执行窗口冻结HEAD和保护输入bytes，包含仅写ignored输出的AUDIT_ONLY包；Sol在Luna交回后完成复核/摘要/文档提交，再基于真实提交后HEAD发下一包。维护者在途补充先记待处理项；若必须立即改变基线，显式中断或amend该包，列精确commit/diff/hash并经readback后再恢复。旧Prompt/收据及其HEAD/hash保留签署时点；不能默默忽略漂移，也不把Sol文档提交归因于Luna。

该工作流允许有界本地提交；push、合并develop/main、Tag和Release仍按单独授权处理。

## 22 切片 DAG 与停止条件

| 序号 | Slice | 直接依赖 | 主交付 | 最低 Evidence | Stop Condition | 当前状态 |
| ---: | --- | --- | --- | --- | --- | --- |
| 01 | R03a | P00 | MuJoCo独立资产可行性；GeoPhys拒绝 | attempt001 ENDPOINT_HAND_COMMANDS FAIL保留；attempt002 INTERIOR_HAND_COMMANDS的S1及独立native source/dynamics冻结oracle通过，详见ignored R03a attempt002报告；不构成Core S2/S3 | 仅当前内缩操作case通过，不证明0/255端点或全行程；Sol已接收该有界工程出口；R03b/c仍须满足原DAG依赖 | ACCEPTED_BOUNDED / R03a EXIT MET FOR CASE |
| 02 | R01a | P00 | `logical-assembly-v1` 两类成员、Scene pin 与非自指身份/strict codec | provider-free S1 | 旧identity变动或引用契约不明→停止 | ACCEPTED_S1_BOUNDED；见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r01a_001/report.md` |
| 03 | R05a | P00 | Provider正式cadence/设备/成本合同 | Audit/S1/probe | 无owner合同→BLOCKED_PROVIDER_CONTRACT | BLOCKED_PROVIDER_CONTRACT（Sol preflight；无新cadence probe） |
| 04 | R04a | P00 | public Camera消费/reader/预算 | S1 | 身份/metadata reader/资源合同缺失→停止 | ACCEPTED_S1_BOUNDED：attempt002的33项provider-free S1与Sol定向复核通过 |
| 05 | R06a | P00 | 历史原件与决议ledger | Audit/S1 | 缺原件且无独立处置→compatibility gate blocked | ACCEPTED_AUDIT_S1_BOUNDED；compatibility decision gate仍BLOCKED |
| 06 | R01b | R01a | 递归owning/reference解析 | S1 | 环/重复/悬空/预算失败→停止 | ACCEPTED_S1_BOUNDED；Sol修正早期深度门后82项provider-free S1通过 |
| 07 | R02a | R01a | Arm-only/Hand-only版本化leaf合同；Force-aware依赖拒绝目录 | provider-free S1 | required state/TCP/资源不明→停止 | ACCEPTED_S1_BOUNDED；Sol修正Required State拒绝门后37项S1通过 |
| 08 | R01c | R01b | 静态source投影与leaf refs | S1 | 隐式物理构造/旧hash变动→停止 | ACCEPTED_S1_BOUNDED；Sol已复核声明级投影与18项provider-free S1 |
| 09 | R02b | R02a,R01b | effective plan与leaf adapter/preflight | S1 | 重叠native writer/部分apply假回滚→停止 | ACCEPTED_S1_BOUNDED；Sol修正兼容/覆盖/name拒绝门后18项S1通过；native/provider NOT_ADMITTED |
| 10 | R02c | R02b,R01c | 真实独立leaf Position隔离与H5 | S2/S3 | 只测两个完整Panda或无真实hand驱动→失败 | S1_REVIEWED_NATIVE_PENDING；003构造/reset与5步事实已复核，publication修复与38项S1通过；004新单进程补真实S2/S3 |
| 11 | R03b | R03a,R01c | 固定树lowering/root/collision/mapping | S1/S2 | wrong mount/root/顺序/约束失败→停止 | PLANNED / NOT_STARTED |
| 12 | R03c | R03b,R02c | 装配态public Env控制/记录 | S2/S3 | 不同diagnostic路径拼接或不完整H5→失败 | PLANNED / NOT_STARTED |
| 13 | R04b | R04a | 同Env真实capture/observation | S2 | stale/ghost step/teardown失败→停止 | PLANNED / NOT_STARTED |
| 14 | R04c | R04b | 同H5图像/metadata/控制读回 | S3 | 错T/T+1或无semantic reader→失败 | PLANNED / NOT_STARTED |
| 15 | R05b | R05a | Provider public sample→Core admission | S1/S2 | 错phase/validity或private bypass→停止 | PLANNED / NOT_STARTED |
| 16 | R05c | R05b | CPU/CUDA×100/500Hz正式对照/H5 | S2/S3 | 任一required cell失败/未运行→P99 blocked | PLANNED / NOT_STARTED |
| 17 | R06b | R06a,R01c,R02c,R03b | 版本/顺序/coupling保护汇总 | S1/S2 | 旧支持退化/新token混淆→停止 | PLANNED / NOT_STARTED |
| 18 | R06c | R06b,R03c,R04c,R05c | 全部required交集/证据/决议包 | S1/S2/S3 | 缺required出口/历史处置→P99 blocked | PLANNED / NOT_STARTED |
| 19 | R07a | P00 | LIBERO5任务/原生语义/init/资产审计、RoboCasafeasibility、成本协议 | Audit/S1 | 协议或required来源/语义缺口未决→阻塞部署 | PLANNED / NOT_STARTED |
| 20 | R07b | R07a | asset/benchmarks与bench_deploy责任/verified manifests/最小配方 | S1 | 许可/闭包/一般Core能力缺失→BLOCKED | PLANNED / NOT_STARTED |
| 21 | R07c | R07b | 五Task真实构造/reset/motion/Controller/Planner/语义/H5 | S1/S2/S3 | 任一required Task阻塞/不可表示/失败/未测→P99 blocked | PLANNED / NOT_STARTED |
| 22 | R07d | R07c | session成本报告与独立human代码质量审阅 | Audit/independent review | 无来源/无独立review或虚构usage→阻塞 | PLANNED / NOT_STARTED |

P99 直接依赖 **R06c, R07d**，且复核所有 22 slices 的 required contract、运行与独立范围决定。R06a 记录缺口可以形成自己的 ledger，但不代表 compatibility decision gate 已接受；R06c/P99 不能把未决决定忽略。各 slice 自带受影响兼容检查，R06b/c 不取代局部回归。

2026-10-26，Sol已接收R01a的静态codec/S1出口；R01b/c仍未启动。R05a受当前GeoPhys正式native-rate合同缺口阻塞：公开Reader限制逐substep host snapshot，旧C05c仅为诊断例外。此为preflight阻塞，不是R05a Audit/S1/probe完成，也不改为DEFERRED。维护者选择在R05a阻塞期间先推进独立R04a；R04a原23项S1通过但Sol复核发现identity绑定缺口，下一包为R04a attempt002定向返工，不改变DAG、R05a blocker或P99 required Camera gate。R04b/c仍按原依赖未执行。

2026-10-26，R04a attempt002已完成capture对实际请求身份/typed Frame calibration的交叉核验，以及H5 camera sidecar对真实state digest、clock、typed control与EpisodeOutcome的独立核验；provider-free定向S1 33 passed，当前出口等待Sol复核。真实 renderer/Env S2与camera H5 S3未运行；R04b/c仍未启动。R05a blocker、R04原DAG依赖、P99 required Camera gate和R06a后继顺序不变。

2026-10-26，R06a attempt001复核四类历史缺失原件的已知索引/归档边界，并完成定向 legacy matrix S1（6 passed）。三类B04a H5无可核验原路径/hash；eb870f6f JSON原路径的现存7,664-byte文件为后续内容，不能恢复原bytes。具体codec/reader调用者、影响与恢复/退休/继续延期选项见[R06 ledger](06_R06_Compatibility_and_Regression.md#r06a-legacy-original-audit)及manifest。Audit/S1交付待Sol复核；本阶段处置未批准，compatibility decision gate保持`BLOCKED_MISSING_RAW_OR_PHASE_DECISION`。不改变DAG、R05a blocker、R04b/c或P99 required；正常表后继R01b本包未启动。

2026-10-27，R01b attempt001在同一artifacts owner实现bounded `resolve_logical_assembly()` 与 immutable resolved-leaf values；最终required provider-free四文件定向集合81 passed，包含新resolver、R01a strict codec/固定identity hash、Scene composition与legacy matrix。覆盖精确Scene与child closure、typed refs、owning/reference-only分离、cycle/path/alias拒绝、32层/1024 leaf边界和调用内memo；未连接R01c/source/compiler，未运行native/S2/S3/S4。当前状态是Luna报告`IMPLEMENTED_S1_PASS_PENDING_SOL_REVIEW`，Sol尚未接受R01b。R06 compatibility gate仍`BLOCKED_MISSING_RAW_OR_PHASE_DECISION`，四项处置未批准，R05a blocker、DAG、Required Envelope与P99保持；原表下一行为R02a，R01c未启动。

## P99 Required Envelope（待批准）

| Gate | 必需交集/证据 | 当前已知与未获得资格 |
| --- | --- | --- |
| R01 logical composition | 两类typed member、稳定路径、无环/唯一owning、source/hash、旧Scene/Artifact不变 | R01a静态codec已获Sol接收；R01b bounded resolver/S1已获Sol接收（深度门修正后82 passed）；source projection与动力学仍未实现 |
| R02 leaf control | Arm-only + Hand-only Position，preset/override→唯一资源writer；真实分开/同时施控、target/ack/state/H5 | 双完整 Panda 历史证据仅作对照；force-aware新leaf不在装配required范围 |
| R03 first Provider | **MuJoCo 3.8.1 CPU**、Menagerie独立Arm+Hand、新固定连接source；reset/连续运动/开合/接触或负载/constraint误差与资源关闭 | 独立MuJoCo 3.8.1 CPU的INTERIOR_HAND_COMMANDS source/dynamics probe经Sol接收：重复reset、连续Arm/Hand motion、1 N外载与mount/限位门通过；端点FAIL保留，Core public Env/H5及后继lowering未实现，未获Assembly Qualification |
| R03 public S3 | 同一公开candidate make_env（或另经明确批准的公共入口）→reset→真实steps→observation→既有Recorder→同文件T/T+1读回→close | 扩展现有factory/RuntimeSession/Recorder；不导入test helpers、不拼接diagnostics |
| R03 second Provider disposition | GeoPhys a53同导出source拒绝、原因/策略/owner与未测项清楚列出；新S1 negative admission保护 | **NOT_ADMITTED/BLOCKED**，无新装配S2/S3/Qualification；第二Provider执行不为首版required，不自动DEFERRED |
| R04 Camera | GeoPhys a53 CPU × MuJoCo3.8.1 Native OpenGL/EGL、原单Panda source，双fixed/mounted RGB/Depth/Entity mask→同Env→同H5 semantic reader | 旧直接capture不代消费连通；需实际context/device、identity/calibration/label-map、T/T+1/故障/close |
| R05 formal feedback | GeoPhys CPU/CUDA physics × host Controller，各100/500Hz law对照、native sample/Guard/hold-ramp/H5；Provider正式公开cadence合同先批准 | 原C05c每子步host Reader仅诊断例外；a53未建立正常500Hz合同；device-resident/实时不要求 |
| R06 compatibility | canonical/native顺序与逆映射、Hand equality/tendon/真实驱动资源、旧版本/admission保护；缺失历史原件独立处置 | B04a/eb870限制保留；恢复/退休/继续延期须新阶段精确决定，缺决定则blocked |
| R07 LIBERO required deployments | 固定LIBERO 8f1084e…的指定五Task，各有可审计构造/重复reset/真实公开Controller-Planner运动/语义对照/状态与既有记录Evidence | 不要求Expert/训练/完整任务完成；任何Task BLOCKED_CORE/BLOCKED_PROVIDER/NOT_REPRESENTABLE/FAIL/NOT_RUN保留阻塞，不能换任务/降predicate/自动延期 |
| R07 Agent cost / quality | 真实Agent Session-bound代码/复用/time/tokens/tools/失败/人工干预，固定静态分析+独立human readability review | 缺值null+reason，不估算；描述性报告required，native成本baseline与因果统计为额外研究、须设计/预算批准 |
| R07 RoboCasa | 固定2ce1aecd…源码/资产许可/robot-base/fixtures/controller-planner可行性与范围建议 | 不要求首版五任务或真实部署；非自动新执行承诺 |
| scope/Release separation | Source Manifest、真实receipts、独立maintainer phase decision、失败/NOT_RUN明细 | S0-S3不授予Qualification；main/tag/v2.0.1Release另行Gate |

R04/R05 的失败或 NOT_RUN：仅阻塞其依赖后继与整阶段 P99，不阻塞无边的 Position 子链；不得自动记为 DEFERRED、跳过required cell或将diagnostic改为PASS。维护者范围变更必须记录 affected gate/source/provider/backend、理由、证据、风险、替代required出口、DAG影响及新的明确批准；在批准前保留原BLOCKED/FAIL/NOT_RUN。

R03 第二Provider若加入required，也须上述scope变更；若GeoPhys修复要求新pin，必须另审其Source/Provider变更与受影响回归，原Evidence不改。R05 CPU-only替代双backend同理；本轮没有批准这些变更。

## 每次实施的通用 Gate

每 slice 开始前冻结 owner/caller、Artifact/Scene/Assembly/Profile/Source/Provider/build/backend identity、seed/reset/horizon、Oracle/tolerance（单位/物理依据/生命周期片段）、timeout/内存/磁盘预算、正/负例与失败/close行为。Source存在、import/compile、S1、真实S2、public集成S3分开记账；不根据phase名称猜通过。

只有受影响明确问题才拓宽实验，不重跑完整 A–D/NutAssembly矩阵/485 interval R1 作为日常文档校验。禁止更换Provider求绿、提升阈值、删断言/全局skip、隐式fallback、私有状态穿透、重复Runtime、ghost transition、假物理回滚。

后续维护者已按具体slice明确授权P00与R03a。总体Goal/DAG未最终批准不覆盖已有具体授权，也不替代后继slice的范围指令；可按本表逐包批准并实施已明确owner/合同/验收的有界slice，不把单包授权扩大为R01–R07整体授权。此表仍是候选执行合同；原 [规划校验](validation_receipt.json)不是新P00实验或阶段验收报告，新审计状态由manifest的P00条目引用。

## R07条件前置与测量范围

[R07](09_R07_Benchmark_Deployment_and_Agent_Cost.md)五Task各锁native文件/BDDL/init/hash，首版均authentic预集成MountedPanda + state-only；各自R02/R03/R04 conditional prerequisites为none，而不是假设任意source已可构造。若选择split leaf /独立Attachment/dynamic public Camera，则仅该Task分别加入R02c/R03c/R04c，并在运行前校验expanded DAG。不得让required task有隐含或未解析dependency；不得添加R04/R05全局前置。任一通用能力缺口交原Core/Provider owner review，不以bench私有补丁过关。

R07a成本protocol须在任何R07b部署前冻结。R07d的native-reference Agent成本对照属于可选研究；R07c native semantic evaluation仍required，两者不能混淆。没有controlled baseline/design/budget与实际数据，不宣称统计成本下降。P99 required集合保留R01–R06，并新增五LIBERO部署、可审计Agent成本/独立质量review、RoboCasa早期feasibility。当前所有implementation NOT_STARTED；本轮仅source/document检查，不是P00/R07a执行通过。

2026-10-23 复核基线为已推送的 `535ce251…`；此前 `234da21b…` 是首版 R07 修订的输入，不再表述为本轮远端 HEAD。本轮保持上述 22 切片、逐 Task 条件前置与全部 Required Envelope 原值；[收据](validation_receipt.json)区分前轮 63 文件审计、本轮 16 文件重新抓取及本地静态复核。未启动任何 slice，也不以文档校验代替其 Evidence。

2026-10-26，Sol复核R04a attempt002实施提交 `72b5274e2adc438d2df165bd0190963909705630`，F01/F02关闭，接收其 `ACCEPTED_S1_BOUNDED` 出口；2个H5正例与11个拒绝反例独立读回通过，未新增native。下一工作包按表进入R06a，一次完成原件/备份审计、版本/缺口与待审批处置ledger、静态校验和本地提交。若原件仍缺失，审计交付可完成而compatibility decision gate保留BLOCKED；本条不批准reader retirement或本阶段继续延期。R04b/c、R05a blocker、DAG及P99 required保持原约束。

2026-10-26，Sol接收R06a attempt001的Audit/S1与ledger出口为 `ACCEPTED_AUDIT_S1_BOUNDED`，四项原件缺失及未批准处置保留，compatibility decision gate仍为 `BLOCKED_MISSING_RAW_OR_PHASE_DECISION`。按表进入只依赖R01a的R01b静态解析实施包；不增加raw恢复依赖，不启动R01c/native，不关闭R06b/c/P99 required。复核入口为ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r06a_001/`。

2026-10-27，Sol复核R01b attempt001并直接修正一个递归入口深度门缺陷：原1100层输入触发RecursionError，修正后按32层合同及时拒绝。原四文件provider-free S1集合82 passed，接收为 `ACCEPTED_S1_BOUNDED`。下一包按表进入R02a的leaf静态合同/capability catalog及Force-aware依赖拒绝，不启动R01c/R02b/native；R06 gate、R05a blocker、DAG/required/P99均保持。

2026-10-27，R02a attempt001在现有 `task_env.controllers.canonical` owner 增加版本化 Arm-only/Hand-only Position 静态合同、Scene/Assembly selector 校验及 Hand Force-aware 依赖/拒绝目录；Target/Ack 只通过显式上下文静态交叉校验。定向 provider-free S1、受影响旧 Controller binding 项和文档示例检查已完成；本包不编译 leaf plan、不运行 Provider/native、不接 Recorder。报告状态为 `IMPLEMENTED_S1_PASS_PENDING_SOL_REVIEW`，等待Sol复核，不构成 runtime/admission/Qualification。R01c、R02b/c仍未启动；R06 gate、R05a blocker、原DAG/Required Envelope/P99均不变。详见 ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02a_001/report.md`。

2026-10-27，Sol接收R02a为 `ACCEPTED_S1_BOUNDED`：直接修正Required State的optional降级/跨leaf字段缺口，7项定向与完整37项provider-free S1通过。新catalog和Force-aware仍NOT_ADMITTED，未实现plan/adapter或native。下一包按表进入R01c静态source/compiler投影；R06 gate、R05a、DAG/required/P99及R02b/c仍按原状态。

2026-10-27，R01c attempt001在既有assembly source/compiler owner中实现 `project_logical_assembly_source()`：每次从当前输入重跑R01b resolver，再投影唯一Scene Entity与Asset来源声明、精确typed leaf definitions、root/Scene/Assembly/path provenance及非自指projection identity。provider-free S1覆盖完整Panda内arm/gripper视图与独立Menagerie Arm/Hand Entity声明、四类typed target、receipt匹配/错配、同Asset不同Entity、reference-only、输入快照隔离及Provider/native未加载。结果等待Sol复核；未lower/attach XML、未创建物理/native mapping、未运行Runtime/S2/S3/S4、未授予Attachment admission或Qualification。R06 gate仍`BLOCKED_MISSING_RAW_OR_PHASE_DECISION`，R05a仍`BLOCKED_PROVIDER_CONTRACT`，DAG/Required Envelope/P99不变。R02b是表中后续切片，但本记录不启动它；报告及Evidence在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r01c_001/`。

2026-10-27，Sol接收R01c attempt001为 `ACCEPTED_S1_BOUNDED`：源码/typed refs/source provenance边界与不可变快照符合本slice，原18项provider-free S1可复用，无需返工或新增准备轮。下一工作包按表进入R02b preset/override→effective leaf plan、真实leaf adapter与整体preflight/partial-apply fault的provider-free实现/S1及本地提交；不启动R02c/native。R06 compatibility gate、R05a blocker、原DAG/Required Envelope/P99和冻结refs不变；复核见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r01c_001/`。

2026-10-27，R02b attempt001在既有canonical/controller与RuntimeSession control owners内实现版本化preset/whole-section override/effective Position leaf plan、独立Arm/Hand算法adapter、显式native mapping receipt、完整请求preflight/typed dispatch及C03a fault progress/latch。新增provider-free S1 13 passed；R02a/R01b/R01c/C02a/C03a受影响既有静态owner集合101 passed，另有C02b pure guard 1 passed；真实native selector未运行。新测试含分离Arm/Hand Entity synthetic dispatch、旧完整Panda算法数值parity、乱序mapping、no-op override identity、最后writer拒绝及partial apply/readback/step故障。当前为 `IMPLEMENTED_S1_PASS_PENDING_SOL_REVIEW`，Sol尚未接受；synthetic receipt不构成materialization，真实Provider/SelectedReferenceEnv/Recorder/H5尚未接线，R02c、R03b、S2/S3/S4与Qualification未运行。R06 gate仍`BLOCKED_MISSING_RAW_OR_PHASE_DECISION`、R05a仍`BLOCKED_PROVIDER_CONTRACT`；R06决议、DAG、Required Envelope、P99和冻结refs不变。完整报告与原始日志保存在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02b_001/`。

2026-10-27，Sol接收R02b attempt001为 `ACCEPTED_S1_BOUNDED`：直接修正4项局部问题，5项新增回归与原集合18 passed，既有owner101 passed/3个native selector未运行，C02b pure guard 1 passed；旧源码数值/身份54个对照完全一致。下一工作包按表进入R02c真实leaf Position执行与既有Env/Recorder/H5；R02b静态出口不等于native admission。当前未运行native/S2/S3/S4，R03b未启动；R06/R05a/DAG/Required Envelope/P99保持不变。复核见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r02b_001/`。

2026-10-27，R02c attempt002合并修复、provider-free S1与有界native执行。S1 28 passed；生产H5 T=64/T+1=65与9类tamper、adapter pre-write拒绝和cleanup通过；静态预检通过，四类合同负例均零native调用拒绝。唯一获授权进程在MuJoCo运行时版本/API检查处于compile前退出为`BLOCKED_PROVIDER`，compile/materialize/reset/forward/step均0，S2/S3未运行。未重试或换Provider，出口待Sol复核；R02c没有accepted/admission/Qualification结论，R03b未启动。实际Evidence在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02c_002/`；R06/R05a/DAG/Required Envelope/P99及冻结refs保持。

2026-10-27，Sol复核R02c attempt002为S1_REVIEWED_NATIVE_PENDING：原修复/S1保留，probe版本整数误写30801已按MuJoCo3.8.1官方及安装header修正为3008001，并补失败前身份记录与拒绝回归。原始loaded值未留存，Provider身份仍未核验；Sol未运行native。下一包attempt003直接单进程完成同source S2/S3与提交，不另开准备轮；S2/S3仍required，不能用synthetic H5替代。

2026-10-27，R02c attempt003静态预检通过；唯一MuJoCo进程核验到3.8.1/3.8.1/3008001与固定文件身份，编译完整source、materialize 9/9/8并reset E1。首个interval五次`mj_step`后，Core typed-state publication因leaf dispatch传tuple而违反`StateRequirements`合同。H5 event保留task-level ExecutionFault（control step 1、0.01s、transition incomplete）；probe未序列化逐writer LeafDispatchProgress/Ack详情。close生成的Generic H5 v3失败artifact为T=0/T+1=1，R02c strict reader拒绝64/65，不能作为S3。S2/S3均未通过。native后在现有dispatch owner将聚合要求改为typed `StateRequirements`，定向provider-free rework S1 19 passed；修正未native复验。一次native原始失败、日志与Evidence完整保存在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02c_003/`。当前 `FAIL_CORE / S2_S3_INCOMPLETE_PENDING_SOL_REVIEW`；不构成Provider admission/Qualification，不启动R03b；R06/R05a、DAG/Required Envelope/P99及source/oracle/冻结refs保持。

2026-10-27，Sol复核R02c003：native5步后的Core typed publication失败保持，S2/S3未完成。类型修复已预先校验，实际publisher/projection/H5/probe checker与R02b共38项S1通过；不以合成H5或Generic episode_complete属性替代64/65实际episode。下一包004为新授权单进程执行，不续旧账本、不另交准备报告，R03b未启动。
