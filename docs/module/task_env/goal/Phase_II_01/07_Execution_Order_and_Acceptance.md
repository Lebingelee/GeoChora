# Phase II-01 — Execution Order / P99 Required Envelope

当前入口（2026-10-29）：**R03c已接收；F00 attempt002及有限复核修正已获Sol有界接收；F01 attempt001安装/原生对照包已获维护者授权；camera分支R04b attempt002已获Sol接收ACCEPTED_BOUNDED_S2，R04c attempt001已获Sol接收ACCEPTED_BOUNDED_S3**。
当前复用集成分支 `develop-full`。attempt002保留attempt001的20条专家失败，在新版本合成box proxy上完成20/20有效solved、Oracle真实H5与独立读回、pending Judge prepare/verify。Sol已核实完整出口并接收两处消费者复核修正，状态`ACCEPTED_BOUNDED_F00`；Human decision仍pending，Qualification/D0/D1/D2均未评估。F01的安装/原生执行状态由主checkout与维护者安装记录管理；本camera分支不包含或覆盖该事实。此后顺序为F01→F02→F03→F04，再按ready cell推进F05/F06；R04b已接收S2、R04c attempt001已获Sol有界S3接收，F07不成为相机前置。
R03c attempt004的精确MuJoCo CPU S2/S3为`ACCEPTED_BOUNDED_S2_S3`，原receipt与attempt001–003失败原件保留。
各原 slice 的当前状态以下表/manifest 为准，不能使用早期“R02a等待复核”等签署时点摘要覆盖后续接收记录。
原 7父Goal/22切片建议 DAG 与 Required Envelope 保留，不继承 Phase II 的 PASS；总体最终批准与各 slice 已有明确授权分开。
新增后继方向见 [10](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md)，本文件更新不自动授权实现/native。

<a id="r03c-checkpoint-recovery"></a>

## R03c attempt004 结果与检查点恢复合同

1. **恢复位置**：复用 `codex/phase-ii-01-p00-20261023` 和现有阶段提交，不 reset 回旧 HEAD。
   attempt004 native与freeze绑定输入HEAD `4ac7284a4cf770f28a1c5d1f9c81337a6b39c66d`；本次结果文档提交只记录证据，实际后续包仍须从届时真实HEAD和保护bytes建立快照。历史attempt002/003 freeze、账本与raw保持不变。
2. **attempt003失败历史保留**：attempt003在HEAD `3b71683`的唯一native窗口完成四份H5和同run文件读取，但runner以`UnboundLocalError`退出1、缺正式`native_result.json`，S2/S3为INCOMPLETE。post-run收尾修正及33项provider-free S1经Sol复核；该修正不追溯改变attempt003状态。原freeze/hash和失败raw保持。
3. **attempt004 bounded结果**：S0与launcher `--check`通过且均provider-free、native starts为0；随后消耗一个native start，实际MuJoCo package/runtime/API为3.8.1/3.8.1/3008001，CPU且renderer未初始化，runner exit 0，发布正式receipt并将progress置为complete，无failure/cleanup error。总计4 materialization、4 reset、260 forward、1280 step、256 outer、2.56 simulated seconds。E1–E4各自64 transitions/65 observations；活动Arm/Hand门、reset/mount/warning门、E3/E4 Arm增益隔离均通过。独立provider-free reader对同run四个闭合H5读回256 transitions/260 observations，并拒绝48/48 tamper。Sol复核后总体状态`ACCEPTED_BOUNDED_S2_S3`，只覆盖本包冻结的Panda Arm+Hand source、seed31、2ms×5、四配置和两个Position writer；不是task success、通用Attachment/Provider admission或Qualification。完整Evidence在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r03c_004/`。Sol已复核实际差异、正式receipt、H5和独立reader Evidence；额度已用完。
4. **S1 入口**：现有 candidate/已选 public 构造入口→真实 Core admission→public reset→runner bindings/requirements→真实 snapshot_v1/check-reset→
   首个 public step→snapshot/check-outer→Recorder/reader→close；仅替换 native IO，
   不以 helper 类型断言或 hash/账本 preflight 代替出错链覆盖。完整通用门见 [10 第6节](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md#6-防止字段与接线错误进入-native)。
5. **出口不变**：同一 public 路线完成原四 episode，各 T=64/T+1=65；四个真实 closed H5 独立读回及原 tamper 门；
   保留 source/plan/Attachment/materialization/config/command/Target/Ack/state/clock 身份。
   不降低原 motion/mount/range/clock/oracle、不以 R03b S2、synthetic H5 或诊断拼接替代。
6. **失败与后继**：保留原失败与新 partial progress；同包普通接线修正只用该包允许的运行额度。
   原表在 R03c 后默认进入 R04b；维护者后续选择的F00/F01优先顺序见本页当前入口。选择独立 ready 行须在工作包中记明原因，
   不自动换 provider、放宽 required 或延长预算。
7. **新增补丁线**：F00–F07 由 [10](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md#5-分阶段顺序与出口) 维护。
   它们不继承 R03c 的 native 授权，也不要求完整 P99 先完成；F01 安装准备等独立行可在明确选择后提前。
   原 R05a、R06 compatibility blockers 与 P99 不关闭；单 Panda USD 不追加 split Attachment/500Hz 全局依赖。

2026-10-28 顺序记录：维护者明确在 R03c 后、默认 R04b 前先推进独立 F00 attempt001，理由是优先处理 Isaac、USD 与 Task Harness，并修复已有 Harness 生命周期误判。该工作包沿 `develop-full` 独立执行，不改原 7/22 DAG、P99 Required Envelope 或 R04b/c 出口，不启动其他 slice；当前实现/S1及native结果见 [10 F00记录](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md#f00-attempt001-实施快照-native-result)。

2026-10-28 F00 attempt001 native 结果：20 个 synthetic MuJoCo 3.8.1 CPU seed 均以 `expert_failed / gripper_readiness_timeout` 结束，Oracle/H5 与 Judge 未运行；Harness 修复及 provider-free S1 通过，但该 mock campaign 未通过，不能记为 Harness candidate acceptance。逐行原始事实见 ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f00_001/`；不启动 retry 或其他 slice，交 Sol 复核。


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
| 10 | R02c | R02b,R01c | 真实独立leaf Position隔离与H5 | S2/S3 | 只测两个完整Panda或无真实hand驱动→失败 | ACCEPTED_BOUNDED_S2_S3；005 Hand50 case四episode/四H5通过；2500默认/旧FAIL保留，下一项R03b |
| 11 | R03b | R03a,R01c | 固定树lowering/root/collision/mapping | S1/S2 | wrong mount/root/顺序/约束失败→停止 | ACCEPTED_BOUNDED_S1_S2；Sol补齐source声明拒绝门并通过99项S1，原两trial S2离线复核通过；仅限该Panda source/seed31/2ms×5候选 |
| 12 | R03c | R03b,R02c | 装配态public Env控制/记录 | S2/S3 | 不同diagnostic路径拼接或不完整H5→失败 | attempt004 ACCEPTED_BOUNDED_S2_S3：正式receipt/progress complete；四份同run 64/65 H5由独立reader读取，256 transitions/260 observations、48/48 tamper拒绝。只限冻结Panda Arm+Hand/MuJoCo 3.8.1 CPU/seed31/timebase/config；其他provider、Attachment和Qualification未准入 |
| 13 | R04b | R04a | 同Env真实capture/observation | S2 | stale/ghost step/teardown失败→停止 | ACCEPTED_BOUNDED_S2；GeoPhys a53 CPU × MuJoCo3.8.1 EGL、两轮24step/53capture；见 [R04b attempt002](04_R04_Dynamic_Camera_Consumer.md#r04b-attempt002-bounded-s2-execution-2026-10-28) |
| 14 | R04c | R04b | 同H5图像/metadata/控制读回 | S3 | 错T/T+1或无semantic reader→失败 | `ACCEPTED_BOUNDED_S3`；GeoPhys a53 CPU × MuJoCo 3.8.1 EGL，双同Env H5各12/13、双reader与22项native派生篡改拒绝；见 [R04c attempt001](04_R04_Dynamic_Camera_Consumer.md#r04c-attempt001-camera-h5-s3) |
| 15 | R05b | R05a | Provider public sample→Core admission | S1/S2 | 错phase/validity或private bypass→停止 | PLANNED / NOT_STARTED |
| 16 | R05c | R05b | CPU/CUDA×100/500Hz正式对照/H5 | S2/S3 | 任一required cell失败/未运行→P99 blocked | PLANNED / NOT_STARTED |
| 17 | R06b | R06a,R01c,R02c,R03b | 版本/顺序/coupling保护汇总 | S1/S2 | 旧支持退化/新token混淆→停止 | attempt001 `PARTIAL_BLOCKED_PHYSICAL_ORDER_PERMUTATION_PENDING_SOL_REVIEW`：定向provider-free S1通过，精确source S2/S3复用；物理重排变体只证明pre-native拒绝，没有成功执行证据；历史missing raw处置gate仍BLOCKED。 |
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

2026-10-28，授权R03c attempt001完成既有Owner上的双Entity Position-leaf candidate/Env/Recorder/reader实现，所选provider-free S1为83 passed。第一次MuJoCo 3.8.1 CPU启动核实runtime identity后，在public reset admission因Attachment receipt的`panda-hand/split`与Hand leaf逻辑tendon identity不匹配而失败，0次forward/step；一次Core映射修正后，第二次（最后授权）native进程在MuJoCo import前因retry runner错误要求append-only ledger仍只有首行而退出。保留两次启动原件；累计materialization1、reset1、forward0、step0、outer0、模拟0，未产生完整episode/H5。之后retry counter修复通过最终provider-free S1，未再启动native。R03c真实S2/S3未完成，等待Sol核对diff与证据；不授予Provider admission、Attachment通用支持或Qualification。R06 gate、R05a blocker、DAG、Required Envelope、P99与冻结refs不变。未启动其他slice；报告/ledger见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r03c_001/`。

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

2026-10-27，R02c attempt004执行一项有界静态预检与唯一MuJoCo 3.8.1 CPU native进程。静态source closure、67 assets与runtime identity通过。E1 arm-only完成64 intervals/320 step，Arm运动/home门、真实H5 T64/T+1 65、独立reader与9类tamper拒绝通过。E2 hand-only完成64 intervals/320 step，但opening最小0.0687899 m、excursion0.00721014 m未达到固定≤0.02 m/≥0.04 m门；其closed H5离线独立reader通过。native进程累计materialize2/reset2/step640，forward计数未保存，未知；E3/E4未运行。失败后JSON证据写入遇numpy.float32 TypeError，raw `native_evidence.json`错误显示FAIL_PRE_STEP/零计数；immutable JSONL failure event保留真实E2 oracle assertion与计数。诊断写入器的序列化修正及回归后测模块21 passed，无native retry，source/physics/oracle/阈值/预算不变。状态`FAIL_PHYSICAL_ORACLE / S2_S3_INCOMPLETE_PENDING_SOL_REVIEW`，无Provider admission/Qualification，R03b未启动。完整attempt004报告与raw保存于ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02c_004/`；attempt001–003原件保留。

2026-10-28，Sol复核R02c004：640实际step事实由原JSONL及两个64/65 H5交叉确认，原零计数raw误分类保留；E1有界通过、E2物理失败。默认5/2500策略限制servo距当前开度2mm，拟用source坐标推导50N/m的Task-owned完整Hand override新case；默认/旧FAIL与原物理门不改，需维护者明确选择后才实施/授权native。当前BLOCKED_HAND_CONFIGURATION_DECISION，未启动R03b。

2026-10-28，Sol完成R02c005 Task-owned Hand50配置修复：56项S1、实际static、唯一MuJoCo3.8.1 CPU进程四episode S2/S3通过，1280step/260forward/4reset/4materialize；E2 min11.01mm、final68.02mm、excursion64.99mm，四H5各64/65且新进程独立回读通过。原算法/source/oracle/预算、2500默认和旧FAIL保持。出口ACCEPTED_BOUNDED_S2_S3，限定新case，未授Qualification或独立Attachment支持；下一项R03b准备工作包，未实现。

2026-10-28，R03b attempt001在固定输入HEAD `48bc7e023929df7aa843a2097014481cd6c3c806` 实现精确双source Panda Arm+Hand fixed-tree计划、closure/lowering、现有Core `materialize()` opt-in和compiled-model receipt。Provider-free S1 19项拒绝门及受影响旧owner 80项回归通过。首个MuJoCo进程在任何native import/reset/forward/step前因源XML省略显式2ms timestep而失败；保留raw后，授权的一次pre-step普通接线修正只对显式Attachment plan允许该省略属性，compiled model仍核对`opt.timestep=0.002`，修复后S1与80项回归重过。第二且最后一次3.8.1 CPU native进程的两个独立trial各完成128 intervals/640 step/129 forward；reset、9/9/8维度、单一`link0`物理root、source映射/碰撞、Arm/Hand motion、mount≤1e-8m/2e-7rad、range、clock、warning与resource-close门全部通过。跨进程预算计数为materialize3（含失败前置尝试）/reset2/forward258/outer256/step1280/2.56s，峰值RSS 336,027,648 bytes。当前仅为`BOUNDED_FIXED_ATTACHMENT_S1_S2_PASS_PENDING_SOL_REVIEW`，没有public Env/Recorder/H5 S3或Qualification；R03c NOT_RUN、未启动，R06/R05a/DAG/Required Envelope/P99与冻结refs不变。报告、S1/S2原件、合同与ledger位于ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r03b_001/`。

2026-10-28，Sol复核R03c001并直接补齐真实Core准入/public reset-step S1、reader Ack/slot/冻结门拒绝与共享runner preflight；当前90项provider-free S1通过，状态`S1_REVIEWED_NATIVE_PENDING`。原窗口2/2已耗尽，未新增native；R03c S2/S3仍不接收。后继仅准备attempt002新的一次启动窗口，须维护者实际转交授权，不推进其他slice。

2026-10-28，R03c attempt002在HEAD `b39bba45c1d39685bc1bd4869a61a2ca3c360208` 通过S0与启动器 `--check` 后使用唯一授权native start。实际MuJoCo package/runtime/API为3.8.1/3.8.1/3008001；E1 public reset/materialization完成，计数为materialization1/reset1/forward1/step0/outer0/0.0 simulated seconds。随后 `RuntimeSession.snapshot_v1()` 因runner传入 `JointReference` 而非Scene `JointDefinition` 抛TypeError。无完整episode/H5，独立reader未运行，S2失败/不完整、S3 NOT_RUN；RSS无采样。保留startup ledger、identity、failure/trace和`native_progress`原件。失败后仅修正runner从canonical Scene选择JointDefinition并新增provider-free定向回归（1 passed）；这不重启native，修正仍未native验证。结果报告及raw在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r03c_002/`。待Sol复核，不推进其他slice；R06/R05a/DAG/Required Envelope/P99与冻结refs保持。


2026-10-28，R03c attempt003基于HEAD `3b71683d5890c4ca1701037d59bce7b17de50a30`通过S0及launcher check后启动唯一MuJoCo 3.8.1 CPU进程。E1–E4各64 outer/320 step/65 forward且各自H5闭合；合计4 materialization、4 reset、260 forward、1280 step、256 outer、2.56 simulated seconds。E4 close后runner在resource summary引用未赋值的`native_log_bytes`并退出1，缺正式`native_result.json`。同run独立reader完成四文件语义回读、48/48 tamper拒绝（256 transitions/260 observations），但整体状态`OFFLINE_READBACK_INCOMPLETE_OR_FAILED`。峰值RSS采样440,950,784 bytes。post-run仅修复runner资源计数顺序和合成fresh-window测试fixture，20项provider-free回归通过，未重启native且不代表修正获native验证。该attempt S2/S3均INCOMPLETE、待Sol复核；原attempt001/002、R06/R05a/DAG/Required Envelope/P99与frozen refs保留，未启动其他slice。详情见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r03c_003/`。

2026-10-28，Sol已复核R03c attempt003的两笔提交和53项签署hash：四份真实H5各64/65、1280次step trace、260 forward、四reset与四materialization、48/48离线tamper拒绝事实接收；native最终receipt缺失且exit 1，S2/S3仍INCOMPLETE。post-run计数修正保留。Sol在现有runner提取可独立检查的收尾方法，并在预算/进度写入完成后才发布正式receipt；新增13项成功出口、计数/缺episode、预算与写入/非有限值失败检查，模块33项provider-free S1通过。没有新native，下一包为同source/oracle/预算的attempt004一次启动收口；其结果仍待实际执行和Sol复核，不推进其他slice。复核见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r03c_003/sol_review.md`。

2026-10-28，R03c attempt004以输入HEAD `4ac7284a4cf770f28a1c5d1f9c81337a6b39c66d`完成一次新的MuJoCo 3.8.1 CPU启动。S0和launcher `--check`通过；actual package/runtime/API为3.8.1/3.8.1/3008001，正式native receipt存在、progress complete、无failure/cleanup error，native exit 0。四episode共4 materialization/reset、260 forward、1280 step、256 outer；H5各64/65，活动Arm/Hand与reset/mount/warning/config-isolation门通过。新provider-free进程同run读取四份H5，provider imports 0，累计256 transitions/260 observations和48/48 tamper拒绝；reader状态`BOUNDED_ATTACHED_LEAF_PUBLIC_ENV_S2_S3_PASS_PENDING_SOL_REVIEW`。RSS最大采样459,276,288 bytes（outer boundary sampling，不代表interval内硬峰值）；完整package最终大小见ignored attempt004 `sha256.manifest`/report。S1复用33项Sol复核结果，没有重跑；attempt001–003失败原件不变。当前只待Sol复核，不启动其他slice，且不授予通用Provider/Attachment支持或Qualification。

2026-10-28，Sol复核R03c attempt004，接收 `ACCEPTED_BOUNDED_S2_S3`。实际启动exit 0、正式receipt及complete progress存在；50项原始文件hash、16项冻结源码hash、1280 step trace、四份H5与独立readback的hash及冻结门一致，48/48 tamper拒绝。接收仅限Panda Arm+Hand 双source、两个Position writer、MuJoCo 3.8.1 CPU、seed31、2ms×5、E1–E4四配置；RSS为边界采样，非interval内硬峰值。复用33项provider-free S1，没有新增native或软件测试。复核报告：ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r03c_004/sol_review.md`。

2026-10-28 Sol复核F00 attempt001：接收 `develop-full` 两线整合与完成事实修复/S1；33项manifest（25文件、8个Git blob）匹配，13项provider-free tests复核通过，20条原始campaign行经report validator再核一致。candidate仍为20/20 `expert_failed / gripper_readiness_timeout`，ledger round1 fail/state ready、Oracle/H5/Judge未运行；F00整体保持PARTIAL。该专家可行性缺口不作为独立F01安装/官方原生Panda+刚体对照的前置。维护者要求下一子阶段工作包，当前明确选择F01，之后按F02/F03/F04逐包推进；R04b/c可独立安排，原DAG/P99门保持。复核见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_f00_001/sol_review.md`。

2026-10-28 维护者最新纠正顺序：先成功验收F00完整闭环，再准备/执行F01。F00 attempt001仅整合/修复/S1接收，20seed候选失败，下一包为F00 attempt002集中诊断、必要owner修复、20seed/Oracle/H5/pending Judge收口；F01草稿保留待用、未派发、未安装或启动。该选择覆盖此前独立提前F01的计划，R04b/c及原7/22/P99门仍保留。

2026-10-28 Luna执行F00 attempt002：在同一 `develop-full` 上保留round1失败并新增round2 owner-repair复验；公开A/B显示builtin seed0在427 steps完成，旧mock在854 steps以`gripper_readiness_timeout`失败，controller/expert/readiness身份相同且target/Ack哈希一致，实际编译source body不同。v002仅将已有builtin PickCube物理属性复制到新UID/version/hash的synthetic box输入，没有更改R1、reset、goal、horizon或solver。MuJoCo 3.8.1 CPU campaign seeds0–19全部valid solved（8612 outer steps）；ledger `candidate_ready`，round1 fail仍保留。Oracle seed0完成427 transitions/428 boundaries，H5 T+1、逻辑映射与独立Core inspector通过；Judge pending包prepare/verify均通过、86 files verified。实现提交`0d75d7646d45f96cc22c567aa61e070dbab5dd94`；完整receipt见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f00_002/`。状态为`F00_FULL_PASS_PENDING_SOL_REVIEW`，不表示已被Sol/Human接收或获得Qualification；F01未启动。

2026-10-28 Sol接收F00 attempt002及有限复核修正为`ACCEPTED_BOUNDED_F00`：338项原件及历史保护hash、20seed原始完成事实、真实Oracle427/428和86项pending包独立复核通过；Luna2独立审阅同意本次native结果未被其条件性缺陷推翻。新增非空portable diagnostics字符串误作文件ref、新owner/fault issue追加后账本无法load两项缺陷已在`1045fd9c65daaa56fdb7eab06779d946bf4b8cd6`修正，Sol复核actual diff并独立重跑29项provider-free tests通过。原生证据继续仅绑定`0d75d76`，复核修正零native；原338项保持不变。Judge metadata既有校验缺口另记后续，不扩大本次标准；原7/22、P99及其他slice不变。下一步F01工作包准备，尚未安装/启动。复核详见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_f00_002/sol_review.md`。

2026-10-28 维护者在F00接收后要求准备F01并安装Isaac。Sol重新核实官方stable6.2.0.0、Python3.12/torch2.11.0 cu128配方及主机资源，准备新HEAD工作包：Luna1持有代码/安装单写入并执行隔离安装及官方Panda+刚体有界native；Luna2独立只读复核配方/API/资源与收尾门禁，不并行安装或启动App。原F01草稿保持历史不执行。本次Sol零安装、零native；Core Isaac adapter仍为F04，安装不等于provider接通。

2026-10-28 camera分支R04b attempt001经Sol复核仅S1/partial capture接收，完整S2未通过；attempt002已在同分支修复worker/reader字段接线，完整provider-free S1文件10 passed，之后一个native worker exit 0且独立offline reader通过。S2结果仅绑定attempt002冻结的GeoPhys/MuJoCo3.8.1 EGL、单Panda Position source、seed31、双相机、24 steps和120个接受substeps；当时状态为`R04B_BOUNDED_PUBLIC_CAMERA_S2_PASS_PENDING_SOL_REVIEW`，不表示Sol接收或Qualification。**截至该attempt报告**R04c/H5未运行且未授权。详见[04 R04b attempt002](04_R04_Dynamic_Camera_Consumer.md#r04b-attempt002-bounded-s2-execution-2026-10-28)及ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r04b_002/`。本camera分支不包含或更新main checkout的F01/Isaac安装进展；不改变原7/22 DAG、P99或其他slice状态，等待Sol复核并协调后续集成。

2026-10-28 Sol接收camera分支R04b attempt002为`ACCEPTED_BOUNDED_S2`：105项原始输出、9项输入源码、3项native源码和5项保护hash匹配；隔离provider-free进程独立重读同run 26 boundary/53 capture/24 control，通过原reset/几何/变化/cache/close门。一次native exit0、2reset、24public step、120 accepted substeps和独立clock推导120/.24s事实接收；不称逐kernel trace。10项S1/11项拒绝例复用，Sol零新native/测试。仅限GeoPhys a53 CPU × MuJoCo3.8.1 EGL × 单Panda Position/seed31/2ms×5/D04双相机。原件与既有失败保留；未合入develop-full，主分支R07a/维护者Isaac窗口不变。**截至该次接收**R04c仍未运行/未授权；P99及Qualification不由此关闭。复核入口ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r04b_002/sol_review.md`。

2026-10-28 Luna执行camera分支R04c attempt001，冻结HEAD为`72f136c6c089eb0bfc6c4389b3d81441b605c28f`。provider-free S1 8 passed，R04b回归10 passed；单一native worker exit0，2 reset/24 public step/120 accepted substeps/0.24 s，生成两份同Env Generic H5 v3（各12 transitions/13 observations）。两个episode实际以`external_stop`结束且`terminated=false`、`truncated=true`、`task_success=false`；这不是horizon耗尽或task success。public semantic reader与raw prewrite-witness reader均通过，native派生22项H5篡改全部拒绝；Env/renderer关闭与Evidence预算门通过。最大process-group RSS为2,121,879,552 bytes，属于采样最大值而不是硬峰值。worker记录并删除source workspace后，收尾从哈希匹配的R04b attempt002保留原件恢复68文件/34,307,151 bytes；单独恢复receipt留存，原R04c删除disposition和native记录不改。Sol并行只读复核进一步核对24项输入源码、19项native冻结源码、8项保护证据，并在两个新进程独立重读原H5：semantic与raw均PASS；两次错误`.venv`路径尝试exit127，未启动Python/native，随后用receipt指定Python完成读回。当前状态`R04C_BOUNDED_CAMERA_H5_S3_PASS_PENDING_SOL_REVIEW`，最终Sol接收仍待收尾审阅；未获Qualification或task success。范围仅限冻结的GeoPhys a53 CPU × MuJoCo3.8.1 EGL × 单Panda Position/seed31/2ms×5/D04双相机。报告和Evidence见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r04c_001/`；camera分支未合入develop-full，主checkout F01/Isaac状态仍以维护者记录为准。

2026-10-29 R04c attempt001 Sol最终接收：162项清单及68项恢复source匹配，复用原两份H5的独立semantic/raw读回和8+10项S1/22项拒绝，状态为ACCEPTED_BOUNDED_S3。仅camera分支收口，无新native/测试重跑、未merge。下一原表行R05b仍受R05a正式Provider合同阻塞；R06b直接前置已有有界接收，可作为独立后继准备，但历史missing raw/本阶段处置决定保持BLOCKED，R06c/P99不得提前关闭。主develop-full正冻结于604da2c供Luna1执行R07a004，本次不写主checkout、不追加在途prompt、不派发R06b或其他实现包。

2026-10-29维护者在两位Luna完整返回后重新分工：Luna1仅做F00–F07，Isaac已安装但F01 native待验；Luna2复用camera工作树开展R06b attempt001。选择R06b的理由、owner/方法/探测矩阵见[06实施定位](06_R06_Compatibility_and_Regression.md#r06b-attempt001-实施定位2026-10-29)。沿用两个阶段checkout，native共享排他锁；原R05和历史compatibility blocker不变。LIBERO仅先选无TurboSquid依赖的一项pilot，后续沿R07独立实施；本R06b包不展开benchmark适配，不改变旧五任务P99记录。主checkout后续摘要由其owner维护，本camera分支不覆盖F线安装/运行证据。

2026-10-29 R06b attempt001在camera输入HEAD `2ed1ed5218b397d80bf062fc305fe166ebf9f410` 完成owner定位、兼容性矩阵、映射/source-order detector与定向S1。Focused新detector 3 passed；legacy/Scene/public候选集合41 passed、1 warning；R02b/R02c集合44 passed；R03b/R03c集合53 passed；静态source gate拒绝19项。修复限诊断测试/夹具，无生产owner/API/source/pin变化。复用已接收R02c005 Hand50、R03b固定Panda Arm+Hand和R03c004 public attached-leaf精确source证据；相关生产owner相对R03c native freeze HEAD `4ac7284a4cf770f28a1c5d1f9c81337a6b39c66d`无差异，没有当前HEAD重跑。新的Hand source-order变体在lowering admission前按精确canonical order拒绝，没有有效物理变体获准执行；因此R06b物理重排门 `BLOCKED_PHYSICAL_ORDER_PERMUTATION`、总体交付为partial待Sol复核。没有启动native、没有取得共享锁。四类历史原件/Phase II-01处置仍 `BLOCKED_MISSING_RAW_OR_PHASE_DECISION`；R05a blocker、DAG、P99与Required Envelope不变。报告和原始日志在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r06b_001/`。
