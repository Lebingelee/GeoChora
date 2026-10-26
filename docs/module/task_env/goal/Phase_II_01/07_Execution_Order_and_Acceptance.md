# Phase II-01 — Execution Order / P99 Required Envelope

状态：REVISED_DRAFT / AWAITING_MAINTAINER_GOAL_DAG_APPROVAL。以下是7父Goal/22切片**建议表**，不继承Phase II的PASS。P00核查已完成；维护者已单独授权R03a attempt001及有界的attempt002 INTERIOR_HAND_COMMANDS native case，attempt002结果已记录并待Sol复核。其他实施slice仍按表中状态执行；DAG与Required Envelope未获最终批准。

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
| 01 | R03a | P00 | MuJoCo独立资产可行性；GeoPhys拒绝 | attempt001 ENDPOINT_HAND_COMMANDS FAIL保留；attempt002 INTERIOR_HAND_COMMANDS的S1及独立native source/dynamics冻结oracle通过，详见ignored R03a attempt002报告；不构成Core S2/S3 | 仅当前内缩操作case通过，不证明0/255端点或全行程；Sol复核前不扩展结论；R03b/c仍须满足原DAG依赖 | EXECUTED / BOUNDED CASE PASS; SOL REVIEW PENDING |
| 02 | R01a | P00 | 两类成员与非自指身份/codec | S1 | 旧identity变动或引用契约不明→停止 | PLANNED / NOT_STARTED |
| 03 | R05a | P00 | Provider正式cadence/设备/成本合同 | Audit/S1/probe | 无owner合同→BLOCKED_PROVIDER_CONTRACT | PLANNED / NOT_STARTED |
| 04 | R04a | P00 | public Camera消费/reader/预算 | S1 | 身份/metadata reader/资源合同缺失→停止 | PLANNED / NOT_STARTED |
| 05 | R06a | P00 | 历史原件与决议ledger | Audit/S1 | 缺原件且无独立处置→compatibility gate blocked | PLANNED / NOT_STARTED |
| 06 | R01b | R01a | 递归owning/reference解析 | S1 | 环/重复/悬空/预算失败→停止 | PLANNED / NOT_STARTED |
| 07 | R02a | R01a | Arm-only/Hand-only版本化leaf合同 | S1 | required state/TCP/资源不明→停止 | PLANNED / NOT_STARTED |
| 08 | R01c | R01b | 静态source投影与leaf refs | S1 | 隐式物理构造/旧hash变动→停止 | PLANNED / NOT_STARTED |
| 09 | R02b | R02a,R01b | effective plan与leaf adapter/preflight | S1 | 重叠native writer/部分apply假回滚→停止 | PLANNED / NOT_STARTED |
| 10 | R02c | R02b,R01c | 真实独立leaf Position隔离与H5 | S2/S3 | 只测两个完整Panda或无真实hand驱动→失败 | PLANNED / NOT_STARTED |
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

## P99 Required Envelope（待批准）

| Gate | 必需交集/证据 | 当前已知与未获得资格 |
| --- | --- | --- |
| R01 logical composition | 两类typed member、稳定路径、无环/唯一owning、source/hash、旧Scene/Artifact不变 | 全部 PLANNED；不构成动力学 |
| R02 leaf control | Arm-only + Hand-only Position，preset/override→唯一资源writer；真实分开/同时施控、target/ack/state/H5 | 双完整 Panda 历史证据仅作对照；force-aware新leaf不在装配required范围 |
| R03 first Provider | **MuJoCo 3.8.1 CPU**、Menagerie独立Arm+Hand、新固定连接source；reset/连续运动/开合/接触或负载/constraint误差与资源关闭 | 仅先前compile成功；Native S2/S3 NOT_RUN，未获Assembly Qualification |
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

后续维护者明确授权P00核查/准入准备先行；最终Goal/DAG及相关合同未批准前，不进入R01–R07实施。此表仍是候选执行合同；原 [规划校验](validation_receipt.json)不是新P00实验或阶段验收报告，新审计状态由manifest的P00条目引用。

## R07条件前置与测量范围

[R07](09_R07_Benchmark_Deployment_and_Agent_Cost.md)五Task各锁native文件/BDDL/init/hash，首版均authentic预集成MountedPanda + state-only；各自R02/R03/R04 conditional prerequisites为none，而不是假设任意source已可构造。若选择split leaf /独立Attachment/dynamic public Camera，则仅该Task分别加入R02c/R03c/R04c，并在运行前校验expanded DAG。不得让required task有隐含或未解析dependency；不得添加R04/R05全局前置。任一通用能力缺口交原Core/Provider owner review，不以bench私有补丁过关。

R07a成本protocol须在任何R07b部署前冻结。R07d的native-reference Agent成本对照属于可选研究；R07c native semantic evaluation仍required，两者不能混淆。没有controlled baseline/design/budget与实际数据，不宣称统计成本下降。P99 required集合保留R01–R06，并新增五LIBERO部署、可审计Agent成本/独立质量review、RoboCasa早期feasibility。当前所有implementation NOT_STARTED；本轮仅source/document检查，不是P00/R07a执行通过。

2026-10-23 复核基线为已推送的 `535ce251…`；此前 `234da21b…` 是首版 R07 修订的输入，不再表述为本轮远端 HEAD。本轮保持上述 22 切片、逐 Task 条件前置与全部 Required Envelope 原值；[收据](validation_receipt.json)区分前轮 63 文件审计、本轮 16 文件重新抓取及本地静态复核。未启动任何 slice，也不以文档校验代替其 Evidence。
