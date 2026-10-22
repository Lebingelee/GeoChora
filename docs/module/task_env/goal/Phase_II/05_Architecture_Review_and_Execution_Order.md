# Phase II Architecture Review — 决策、切片顺序与验收

> 状态：规划于 2026-10-20 提交二审；2026-10-21 已开始有界实施记录，未形成全 Phase II approval。
> 历史规划修订记录：维护者曾授权当时的规划修订、两次提交并推送 develop，随后由网页 GPT 二审；该记录描述 2026-10-20 的规划工作，不代表本轮 D03 实施的发布授权。
> 源码审阅基准：develop@f292df149f41520b484ff27cf2ff78a584903013。
> 原始五份草案由提交 [a299d8b](https://github.com/Lebingelee/GeoChora/commit/a299d8b) 按原字节保存。
> 本文是本组规划的决策/执行顺序入口；`01–04` 是各父 Goal 的详细契约。都不是新的能力矩阵或 Qualification Decision。

> **当前规划与实现状态（2026-10-22）**：C02b-P/E 的单 Panda Position 交集和 P00/P99 最小双 Entity Position-only 子项已有 GeoPhys/MuJoCo CPU S2、Generic H5 v3 真写读及定向检查的 bounded evidence，等待维护者复核；C02b-R1 的 PickCube reset-force freshness 前置已在 GeoPhys CPU legacy route 有界通过，但 plan-bound typed raw-force admission 和完整 C02b 仍 BLOCKED。
> 下方当前表已采用 P00 的 **20 父 Goal / 33 实施切片 + P00/P99**；历史 receipts 保留当时编号与结论。
> C02b 恢复分为内部 P/E 检查点，C02b 仍 BLOCKED；单/双 Entity Position-only S2/H5 不关闭 R1 force freshness、其他任务 Guard 或完整 qualification。S2 与 H5 v3 是 E 的后层退出标准，不是启动前置。
> 见 [恢复审阅报告](C02b_Recovery_Architecture_Review.md)、[C02b-P Review](C02b_P_Position_Based_Profile_Review.md)、[C02b-E S1](C02b_E_Position_Profile_S1_Acceptance.md)、[C02b-E S2/H5](C02b_E_Position_Profile_S2_Acceptance.md)、[双 Entity Position Acceptance](C02b_Dual_Entity_Position_Acceptance.md)与 [Phase C 当前契约](03_Phase_C_Execution_Lifecycle.md#c02--controller-binding--atomic-execution--safe-switchabc)。
> **D03 current bounded result**：序号 31 已通过 GeoPhys CPU × MuJoCo native OpenGL 的 Position candidate RGB transform-sync S1/S2；仅覆盖 Scene-v3 scalar joints、Position arm movement 和单路 camera，不覆盖 D04 或完整 D05b。见 [Phase D D03 receipt](04_Phase_D_Physics_Rendering.md#d03-first-bounded-intersection-receipt-2026-10-21)。
> **D04 current bounded result**：序号 32 已通过同交集的 RGB/optical-Z Depth 与 Entity-instance segmentation；fixed/hand-mounted camera、遮挡、reset freshness、mask/label-map 磁盘回读均有 S1/S2。只准入 Scene-v3 scalar-joint Position source → GeoPhys CPU × MuJoCo native OpenGL。Semantic segmentation、free-joint、完整 D04/D05b 与 Qualification 仍未覆盖。见 [Phase D D04 receipt](04_Phase_D_Physics_Rendering.md#d04-bounded-entity-instance-segmentation-receipt-2026-10-22)。
> **D05b current bounded result**：序号 33 已通过指定 Position/Scene-v3 scalar-joint 交集的 default + per-camera override、exact admission、双相机 materialization/sync/capture/close S1/S2；Physics 是 GeoPhys CPU，Renderer 是 MuJoCo native OpenGL，输出为 RGB/optical-Z Depth/Entity-instance mask。仅首个 pairing bounded gate 通过；Environment policy observation、TransitionRecorder、完整 D05b 矩阵及 Qualification 未覆盖。见 [Phase D D05b receipt](04_Phase_D_Physics_Rendering.md#d05b-bounded-cross-provider-pairing-receipt-2026-10-22)。

## 1. 审阅结论与事实边界

结论为 **REVISE**：保留 A–D 分工及 20 个父编号，先定跨阶段契约、先跑最小真实闭环，
再迁移高耦合执行路径。原先 A→B→C→D 的主干没有形式上的必然依赖环，但真实 materialization
太晚，容易让多个阶段只通过静态检查后才发现基础模型不匹配。

本次规划修订与 runtime 复验分开：下述运行事实来自前一轮对 f292df1 的审阅；
本次第二提交只检查规划内容/链接/依赖/范围，未据此重新授予任何运行结论。
发布基线仍由 [v1.1.0](../../../../releases/v1.1/README.md)、
[唯一矩阵](../../capability_matrix_v1_1_0_candidate.json) 和
[qualification](../../qualification.md) 定义。

| 范围 | 当前源码事实 | 既有规范或本轮提案 |
| --- | --- | --- |
| Core/Provider | task_env 为 Core，GeoPhys 是 Gitlink；Core 使用其 public/runtime-facing API | 保留依赖方向，不复制 Runtime/Provider |
| Scalar | BaseTaskEnv 与 SelectedReferenceEnv 两条路径、不同 state/control 协议 | 本轮提议统一行为、允许薄 facade 过渡 |
| Scene | 已有 EntityDefinition/WorldDefinition、AssetManifest/TaskCompositionSpec/TaskReferences | vNext 明确唯一结构权威和实例身份 |
| Semantics | selected 几何谓词；Pendulum 有 action cost 和时序窗口 | 扩展现有 TaskDefinition，不另造任务执行 owner |
| Reset | v0 ResetSample/RealizedInitialState 可记录请求/实测 | 容器存在不证明通用 tolerance gate 已执行 |
| Provider lowering | ImportedScene 已有 ir/capability_report/solver/render descriptions | 优先组合，不复制 importer 或公开 native storage |
| Recording | generic H5 v2、canonical outer、execution stream 是不同格式 | structured action/events/outcome 需版本化扩展 |
| Camera | v0 RGB/Depth 与 static triangles 保留；D03 dynamic RGB、D04 dynamic RGB/optical-Z Depth 与 Entity-instance mask 在同一 GeoPhys CPU → MuJoCo native OpenGL Position-source 交集有 bounded S1/S2 | 仅同步 pinhole、Scene-v3 scalar-joint Position source 与已测 fixed/唯一绑定 Frame 相机；Semantic segmentation、free-joint 与完整 D05b pairing 不准入 |
| Freeze | TaskArtifact 是 immutable data/hash，不自动成为 approved frozen task | Stage-1 validation/feasibility/Human Judge 继续适用 |

基准 GeoPhys checkout/Gitlink 为 `c665ce5028a12bb4d2afe49f05e015fa9b684a39`，
Menagerie 为 `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。它们不能用当前上游 HEAD 替换。
更换源码后须重新 audit；本次结论不推广到任意 Provider/backend/task。

## 2. 本轮选择的保守决策

这些选择收敛规划歧义，仍需二审和后续切片实施授权；不是未经实现的 public API 承诺。

| 决策 | 本轮选择 | 影响与边界 |
| --- | --- | --- |
| 优先级 | A–D 候选工程优先；E 延后 | canonical Roadmap 的 LIBERO/Oracle 研究记录不在本次改写；未来工程立项同步取舍 |
| Scene 权威 | Core artifacts owner 的 immutable Scene/Entity contract；v0 保留 projection/codec | AssetManifest 只描述来源，TaskReferences 只映射编译结果；不建立第二个世界 owner |
| Registry | 类型 UID 与实例 Entity ID 分开；复用现有 registry | make_agent 保留，make_robot 改名不作为交付前提 |
| Import/visual | 先评估公开 ImportedScene/SceneSource/render lowering | Core 不复制 parser，也不要求其他 Provider 使用 GeoPhys IR ABI |
| Timebase | 首个 vNext 保留 exact physics_dt/substeps/control_dt/sampling | 同 control_dt 不证明跨 native dt 等价；进一步拆分独立评估 |
| Task freeze | E 延后只延后编排工具 | 新 frozen task 仍须 validation、randomized feasibility、Human Judge；不达标为 candidate |
| Variant | 首个基线固定拓扑，仅 Role/pose randomization | 拓扑改变明确拒绝；未来重建 Env/wrapper 或另设计有界 mask |
| Multi-robot | 双 Robot 静态命名/引用必测；真实主线先单 Robot/arm+hand | 两个独立 Panda Position Entity 的 exact Scene-v3/GeoPhys-or-MuJoCo CPU 交集已有 D01/C02 S2；任意 N、Assembly、其他配置/provider/backend 仍 unsupported/deferred |
| Scalar | 先统一公共行为，经已有 ports/adapter 适配 | 不要求立即同一具体 Env 类，不新造 UniversalRuntime |
| Semantics | TaskDefinition 适配 evaluation context，一 sample 一次提交 | native Guard 只读判据、observation、render/diagnostics 不改 Task memory |
| Action/record | structured request 与 target/applied 分层；C05a 前移 | 不把 NumPy vector writer 当 tree writer，不合并三类旧格式 |
| Stop | 独立 Boundary Event/EpisodeOutcome；不追加伪 transition、不回写已返回 flags | loader 以显式 final outcome/policy 决定 end/bootstrap；T=0/重复/terminal 后行为必须测试 |
| Controller switch | 同 schema/资源/单位/时序才允许 safepoint 替换 | schema 改变需要新 Env/wrapper/learner；默认拒绝 multi-writer，不建设通用 arbitration |
| NutAssembly | measured interval feedback + Controller-owned hold/ramp 受限请求 | Solution 不共享可变 hold，不跨边界读私有 stage；保留 500 Hz 和 strict failure/warning |
| Camera | pinhole、同步、RGB/optical-Z Depth；受限 segmentation 单独准入 | 任意 K、fisheye、真实 async/deformable 不因字段存在而支持 |
| Pairing 目标 | GeoPhys CPU physics × MuJoCo native renderer 已有 D03 RGB、D04 RGB/Depth 和 bounded Entity-instance mask 的真实 Position-source 交集 | 仅这些 exact synchronous profiles 有证据；任意 source、provider/backend、geometry 或 modality 不自动准入；完整 D05b 仍需独立 pairing/资源验收 |
| 未达 gate | 必需切片缺证据不标 implemented；deferred 明示范围缩减 | 不以接口就绪/同名 capture 通过声称完整 independence 或完整 A–D |

## 3. 切片依赖与推荐执行顺序

下表按一种拓扑顺序排列；“直接前置”是切片开始前必须满足的依赖，不将整阶段父 Goal 当黑箱前置。
a/b/c 后缀属于原 20 个父目标，不另增同义 subsystem。每个切片只修改一个可审查的所有权/契约边界；
有多个必要变更时再细分 receipt，不能将所有切片打包成一次跨系统重写。

| 序号 | 切片 | 直接前置 | 最小交付/退出 Gate |
| ---: | --- | --- | --- |
| 00 | P00 | 无 | 当前源码/dirty/gitlinks、真实 caller、有效 detector、旧格式/UID/失败/timeout 清单；批准保护范围 |
| 01 | A01 | P00 | 唯一 Scene/Asset/Entity 身份 owner；严格 value codec、legacy projection 策略 |
| 02 | A02 | A01 | Frame/Joint/Actuation 静态契约；transform oracle、非法引用/循环拒绝 |
| 03 | B04a | A02 | 嵌套 schema/read-write/migration 矩阵；v0 bytes/identity fixtures 与新版本识别策略 |
| 04 | D02a | A02 | typed state/requirements、evaluation/native sample clocks、validity/lifetime 契约 |
| 05 | C01a | B04a、D02a | normalize precedence、静态 Execution Plan/admission 和资源 owner |
| 06 | D05a | C01a、A02 | provider/backend/profile/device 分层；per-camera/capture identity 和版本契约 |
| 07 | A03 | A02 | 单/双 Robot 静态 Scene、实例命名空间及实际 reference resolution |
| 08 | A04 | A03 | 现有 Registry/public importer 组合；源语义/资源 hash/信息损失报告 |
| 09 | A05 | A04 | A 静态一致性 gate、legacy identity/UID/reference 不丢失 |
| 10 | D01a | A05、B04a、C01a | v0 schema 新 candidate 或等价 projection 的真实 microprobe；保护 frozen hash，改新输入会改 realization |
| 11 | D02b | D02a、D01a | typed projection、真实 free/spherical probe、只读 lifetime；为 B/C 提供输入 |
| 12 | B01 | A05、B04a、D01a、D02b | 最小 strict YAML Source/Hook declaration，不启动 native runtime |
| 13 | B02 | B01、D01a、D02b | 固定拓扑 Role/sample、RNG/version、rollout 前 realization gate |
| 14 | B03a | B02、D02b | 只读 predicates + action/interval evaluation context；现有 reward Oracle |
| 15 | B03b | B03a | dwell/sequence/edge memory；一次提交、重复/乱序/reset/缺测行为 |
| 16 | B04b | B04a、B03b、D05a | Source→vNext Artifact compiler/codec/hash；嵌套读写/拒绝矩阵 |
| 17 | B05 | B04b | 旧 samples/traces 语义差分与 legacy route；新版本无 freeze 自动继承 |
| 18 | C01b | B05、D02b | 实际 Task requirements/actual manifests、动态 admission；兼容配置分支 |
| 19 | D01b | D01a、B04b、C01b | vNext 与两 provider 固定拓扑 materialization/reset/realization；本分支有界 S2 receipt 见 §11 与 Phase D D01b |
| 20 | C02a | A03、C01b、D02b | **bounded implemented**：Scene-v3 Entity×Group binding 与完整 action preflight；单 writer；87 项交叉回归，未开放 group dispatch |
| 21 | C05a1 | C02a、C01b、D05a | **bounded evidence mapped**：既有值契约加 C03b lifecycle finalizer/调用次数与 End Event 验收；不撤销原 C05a 收据，也不代表全 consumer 迁移 |
| 22 | C05a2 | C05a1 | **bounded evidence mapped**：generic H5 v3、T/T+1、单 writer 投影及 `load_structured_training_episode_h5()` 的 end/bootstrap 消费已定向验证；未声明结构化 action 的 wrapper/env 明确拒绝 |
| 23 | C05a3 | C05a1、C05a2 | **C05b-scope supplement passed；overall bounded**：未知 execution H5 版本、Profile/ack/request/boundary/Event/Outcome 错配负例已补；实际 PickCube R1 仍只依赖 canonical-v0，见 §3.2–3.3 和 [Phase C audit](03_Phase_C_Execution_Lifecycle.md) |
| 24 | C03a | C02a、D01b、C05a2 | **bounded implemented**：scalar lifecycle、fault receipt、Recorder interval 完整性；历史证据见原文收据 |
| 25 | C04 | C03a、D02b | **bounded implemented**：observation/info schemas、feedback 与 diagnostics 分离；历史收据有效 |
| 26 | C02b | C02a、C03a、C04、C05a2、D01b | **BLOCKED**：单 Panda Position 与 P00/P99 最小双 Entity Position-only 子项的 S1、GeoPhys/MuJoCo CPU S2、Generic H5 v3 state readback bounded 通过；PickCube R1 reset-force freshness 前置另有 GeoPhys CPU S1/S2 bounded 通过。Plan-bound raw-force typed publication/manifest admission、完整 structured C02b、其他必需交集与 Qualification 仍未完成；见 [双 Entity receipt](C02b_Dual_Entity_Position_Acceptance.md) 和 [R1 freshness receipt](C02b_R1_Reset_Force_Freshness_Acceptance.md) |
| 27 | C03b | C03a、C04、C05a2 | **bounded implemented**：现有 generic/Position scalar lifecycle、EpisodeEnd、v3 reader consumer；Pendulum GeoPhys S2 与双 Provider Position Stop/H5 通过；selected R1、vector、全部算法和 MuJoCo generic Pendulum 未支持。详见 [C03b receipt](C03b_Stop_Outcome_Receipt_2026-10-21.md) |
| 28 | C02c | C02b、C03b、C05a2 | **bounded slice passed only**：单 `panda-main` Position Profile、GeoPhys CPU/MuJoCo CPU 的同 schema 实例切换与 H5 v3 evidence；dual Entity/R1/Guard/Assembly/Camera/general arbitration 和完整 C02b/C02c 仍 open。见 Phase C C02c receipt |
| 29 | C05b | C02b、C03b、C04、C05a3 | **实施前审计完成；未启动**：PickCube R1 reset freshness 前置已有 C02b-R1 bounded receipt；plan-bound typed raw-force admission仍未闭合，公开 info 缺 readiness/执行回执。不得以 Position S2 或 legacy freshness 证据替代 C05b 的 Expert/recording 验收，见 §3.3 |
| 30 | C05c | C05b、D02b | NutAssembly native Guard/hold/ramp/500 Hz/force freshness 与严格 Outcome 回归；不能靠 position-only Profile 替代 |
| 31 | D03 | D01b、D02b、D05a | **bounded implemented — first intersection**：Position scalar Scene-v3、canonical Frame→renderer mapping、独立 consumer versions、reset/same-step RGB S1/S2；详见 [D03 receipt](04_Phase_D_Physics_Rendering.md#d03-first-bounded-intersection-receipt-2026-10-21)。D04/full D05b remain open |
| 32 | D04 | D03、C04、C05a2 | **bounded implemented — RGB/Depth + Entity-instance segmentation slices**：GeoPhys CPU × MuJoCo native OpenGL fixed/hand-mounted capture、canonical Entity labels、运动/遮挡/reset 与 mask/map 磁盘回读有 S1/S2；semantic segmentation/full D04/D05b remain open。详见 [D04 receipt](04_Phase_D_Physics_Rendering.md#d04-bounded-entity-instance-segmentation-receipt-2026-10-22) |
| 33 | D05b | D05a、D04、C01b | **bounded exit passed — first cross-provider pairing**：GeoPhys CPU × MuJoCo native OpenGL、Position/Scene-v3、fixed + hand-mounted Camera、RGB/Depth/Entity-instance mask；default/override、admission、失败隔离与资源 close 有 S1/S2。动态输出尚未接入 Environment policy observation/TransitionRecorder；完整 D05b matrix/Qualification remains open。详见 [D05b receipt](04_Phase_D_Physics_Rendering.md#d05b-bounded-cross-provider-pairing-receipt-2026-10-22) |
| 34 | P99 | A05、B05、C02c、C05c、D05b | 20 父 Goal 的必需切片、真实新主线、最小双 Entity 隔离施控、D05b pairing；缺证据为 partial，不暗授 Assembly/force-profile 资格 |

D03 不以 C05c 为硬依赖；表中排在其后是建议主干，不要求 Renderer 等待全部 expert campaign。
相反，C05c 不等待高保真 Renderer。C05a 提前定义 events/outcome 存储，C03b 实现相应生命周期，
避免用后写的存储格式补救已开放的新 action/stop API。

B05 可以完成 legacy semantics 适配，但 vNext 全链执行要到 D01b/P99 验证；
D01a 只证明有限新 Scene bridge，不冒充完整 D01。父目标 implemented 必须覆盖其全部必需切片。
P00/P99 是 gate，不增设新的 Framework/Harness。2026-10-20 的规划提交本身没有执行代码；其后授权的 C02b/C03b/D03 变更分别在对应 receipts 记录，不改变 P99/Phase II 的整体退出条件。

截至本次文档修订，当前序号 24／C03a 与 25／C04 保持已有 bounded acceptance；26／C02b 仍 **BLOCKED**，其中 Position Profile 已通过 E-S1/S2/H5 的单 Panda bounded 交集。
force-aware R1 的 fail-closed gate 和 GeoPhys CPU reset stale-force Probe 已验证；公开 Reader route 存在，
但 reset 后仍可能读到上一 episode 的 −30 N，raw force 尚未闭合 admission/typed publication。
该缺陷继续阻塞 R1；位置 Profile 候选若在完整消费链不查询力，可独立验证，无须先修 GeoPhys force API。
C02b-P 已确定实际 writer/identity/required state 和 force-free reset/step/record 路线；E-S1/S2/H5 已实跑同一 candidate/sample、两 Provider 位置控制与 H5 v3 磁盘读回。结果只关闭该声明交集，不打开 production capability、不关闭 required-force R1 或其他场景。C03b 后续已在有界 scalar lifecycle 内完成，仍不改变 C02b/R1 阻塞或完整 Phase II 状态。
既有 C03a/C04 验收不会因序号同步失效，本地冻结 `codex/phase-ii-b` 保持 `0068010`。

**旧/新序号对照**（Goal ID 为主键，历史记录不改号）：

| 旧 31 切片表 | 当前 33 切片表 | 处理 |
| --- | --- | --- |
| 00–20（至 C02a） | 00–20 | 序号不变；B04b 补记已有 P00 的 D05a 直接前置 |
| 21／C05a | 21／C05a1、22／C05a2、23／C05a3 | 仅细化退出条件，已有实现/证据见 §3.2 |
| 22／C03a、23／C04 | 24／C03a、25／C04 | 保留既有 bounded receipts |
| 24／C02b、25／C03b | 26／C02b、27／C03b | 编表时实施未完成；P/E 不额外计数。C03b 后续 bounded receipt 见序号 27；C02b 仍 BLOCKED |
| 28／C02c | 28／C02c | 前置改为 C02b/C03b/C05a2，不等待完整 C05c |
| 26／C05b、27／C05c | 29／C05b、30／C05c | task-specific force/readiness/Guard 仍独立验收 |
| 29／D03、30／D04、31／D05b、32／P99 | 31／D03、32／D04、33／D05b、34／P99 | Renderer 不等待 C05c；保留最小双 Entity 施控 gate |

### 3.1 粒度与工作量

主要分类为 EXTEND_EXISTING / COMPOSE_EXISTING。新增轻量 Scene、typed state、events value contracts
须解释旧 owner 无法表达之处；不新增第二个 Runtime、TaskEnv、Recorder、Provider 或 Manager stack。
A05/B05/D05b 是集成 gate，不能再借机重构。make_robot 命名迁移可独立延期。

| 父目标范围 | 初步有效工程人日 | 主要不确定性 |
| --- | ---: | --- |
| A01–A05 | 18–32 | source semantics 保留、实例命名贯穿旧 compiler |
| B01–B05 | 21–35 | 嵌套 codec、action context、时序提交与 Hook recovery |
| C01–C05 | 31–55 | Recorder 版本、partial failure、NutAssembly hold/ramp/native coupling |
| D01–D05 | 30–53 | dynamic visual public API、native resources、segmentation/pairing |
| 合计 | 100–175 | 在 P00/各切片 audit 后重新估计，不构成排期承诺 |

估计包含定向测试、兼容和文档同步；不含新增 solver/native renderer 功能、全格式 parser、
真实双 Robot 全任务动力学承诺、大规模 qualification、E 或 Phase III。
无法证明的能力单列 deferred；不能为了符合人日估计降低验收。

### 3.2 C05a 既有证据与三切片映射

P00 已定义 a1/a2/a3，但后续工程按旧表将实现合并在一个 C05a 收据中；这里进行 evidence crosswalk，
不撤销历史验收、不复制代码、不把未测试的完整退出条件自动标 DONE。旧收据见
[Phase C C05a](03_Phase_C_Execution_Lifecycle.md#c05a-bounded-storage-receipt2026-10-21)及本文 §5.5。

| 当前切片 | 可直接复用的现有实现/证据 | 尚需明确的退出证据 |
| --- | --- | --- |
| C05a1 | 既有 BoundaryEventV1/EpisodeOutcomeV1/StructuredControlTransitionV1、版本拒绝、T=0、boundary sequence、terminal bootstrap 值约束；C03b 复用同一 Event/Outcome owner 并验证 lifecycle exactly-once finalizer | 非受限生产 consumer 的 Stop 适配；storage/finalizer 证据仍不等于完整算法迁移 |
| C05a2 | generic H5 v3、T/T+1、显式单 writer schema/order/value projection、finalized-episode reader；C03b 的 `load_structured_training_episode_h5()` 返回原 step flags 加 final outcome/bootstrap | 仅显式声明 typed structured controls 的 wrapper 可走 v3；当前无真实 generic TaskEnv 声明该能力，普通 Pendulum v3/v2-active-Stop 组合明确拒绝 |
| C05a3 | canonical outer v1、execution stream v3、structured reader/projection、旧 layout 拒绝及 pending interval 不可 freeze；本轮补充未知 execution H5 文件版本、request/ack/profile/boundary/Event/Outcome 错配负例 | C05b 实际 PickCube R1 只走 canonical-v0 外层格式；真实物理采集与回读须由 C05b S2/S3 完成。generic H5 v3 属于 Position candidate，execution stream v3 属于 native-substep consumer，不强制 R1 改格式。历史 retired import/campaign 缺口单列，不恢复 alias 或删除断言求绿 |

`test_phase_ii_c05a_structured_recording.py` 的旧 7 项及旧组合 41 项通过是当时有界结果，本次未重跑。
不能将它们重新计数为三个切片全部完成。对现有明确覆盖的条目直接继承 evidence；缺口只在相应真实 consumer
首次依赖前定向补证，不重新执行 A–D、重新审 SHA 或重造存储系统。已有 C03a/C04 的受限行为与证据保持成立。
generic H5 v3 是 C02b 位置路线的首选受限存储候选；canonical BoundaryRecord 目前强制 force/readiness，
若未来承载该 Profile 须另审原 owner 的版本扩展，不能填零或把 force-aware 记录解释为位置记录。

### 3.3 C05a3 targeted supplement 与 29／C05b PickCube consumer audit（2026-10-22）

本轮沿当前 `pick-cube-p16-reference-v1` 的真实构造与调用者审计，结论是：**C05b 不能用 Position candidate 的 S2
替代冻结 PickCube 当前 R1 consumer；GeoPhys CPU 的 required measured-force reset freshness 是进入真实双 Provider
S2 的硬阻塞。** 一步真实 smoke 已在 GeoPhys CPU 与 MuJoCo CPU 分别 reset→step，确认 Artifact、Controller、Solution
identity 和 10 ms 时钟一致；它没有完成 Expert、不含接触/readiness 行为、没有真实录制或 H5 回读，不能关闭此阻塞。

实际 consumer 的闭环如下，所有对象都沿现有 owner：

| 环节 | 当前事实与源码 owner |
| --- | --- |
| Source / Artifact | `task_env/tasks/pick_cube/task.py` 的 `build_artifact()` 固定 `pick-cube-v1/p1_6_experimental_100hz` 与 Menagerie `b846dd12…` Panda source identity；`build_runtime_source()` 委托 `PickCubeSceneComposer` 生成 Panda + 桌面 + cube 的 task-local MJCF，并建立 joints/bodies/frames/free-joint/actuator maps。Artifact hash 为 `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4`。见 [task.py](../../../../../task_env/tasks/pick_cube/task.py#L238)、[composer](../../../../../task_env/objects/pick_cube.py#L307)。 |
| Factory / identity | `build_reference()` 以同一 Artifact/RuntimeSource 创建 `ProductionCanonicalPandaController` 与 `PickCubeReadinessSolution`，持有 resolved config/source revision/source file hashes；`make_reference_binding()` 选择 grouped interval、canonical Recorder、`external_actions=True`，但 reset/observe kwargs 调用私有 `_execution_info()`。Provider 仅从 CPU selected route 进入，当前真实 Smoke 的 R1 identity 为 `76108c78b8159391e448ad9f49050bed42fd7a86e0e00a0520083b4e5efb02e9`，Solution version 为 `pick-cube-p16-readiness-expert-v2`、identity `514a5ed3bc0d289761ef88a00b1e7c11df2795133506ab148db9ab8e98e55241`。见 [task factory](../../../../../task_env/tasks/pick_cube/task.py#L371)。 |
| Action / TCP / time | 输入仍是 `selected-reference-absolute-pose-v1` v1：world absolute pose、quaternion wxyz、dimension 8（7D Panda pose + normalized gripper）。实际 TCP 是 `panda-v1/ee`。Artifact timebase 为 0.002 s × 5 native steps = 0.010 s control boundary（100 Hz）；reset 必须 step 0/time 0，Solution 每次 observe 要求连续 step 与 10 ms clock。不可更换为 `panda-main` Position `StructuredActionRequestV1` 或改 Action/Artifact identity。见 [SelectedReferenceEnv action/reset](../../../../../task_env/tasks/reference_env.py#L264)。 |
| Required feedback / readiness | R1 identity 是 `panda-production-control-r1`，gripper `experimental_rate_limited`；它要求边界对齐的 `CanonicalControlFeedback`，其中 opening 来自测量 finger joint state，closing force 来自已测 actuator-force 投影。R1 在 closing 时用 force 激活/初始化/调节 gripper target；`PickCubeReadinessSolution` 的 `gripper_ready` policy 消费 `ExpertExecutionInfo.control_readiness.gripper.close_ready`。这是 required feedback，不是 optional diagnostics。见 [R1](../../../../../task_env/controllers/canonical/production.py#L15)、[feedback](../../../../../task_env/controllers/canonical/feedback.py#L7)、[readiness](../../../../../task_env/controllers/canonical/readiness.py#L6)、[completion](../../../../../task_env/planners/completion.py#L9)。 |
| Provider force route | GeoPhys 的现有 Core adapter 可通过公开 `RobotArmObservationReader` / Boundary snapshot 组合外层 readback，MuJoCo 适配器复用 completed actuator-force cache；Core Controller 不读 provider-private solver。可是已记录真实 GeoPhys Probe 证明 reset 不推进 physics 时可能遗留上一 episode 的 `-30 N` force，而公开 Reader 没有 reset/sample identity、freshness、native index/phase。no-plan legacy route 继续要求 force（`_force_feedback_required=True`），但这不构成 freshness/typed manifest admission。故**现有公开接口能读到值，不等于能证明首个 R1 compute 的 required reset sample 有效**。见 [GeoPhys gap receipt](C02b_Feedback_Source_and_Sampling_Audit.md) 与 [control materialization](../../../../../task_env/runtime/sessions/control.py#L350)。 |
| Solution lifecycle / ownership | `PickCubeReadinessSolution` 持有 stage/index/wait/counters/completion memory；R1 Controller 持有 commanded/desired opening、force mode/init 和 expected step；RuntimeSession 持有实际 runtime state 并给 boundary feedback。当前 Environment 从 `self.value['solution']` 持有并驱动 Solution，`step_expert()` 调 `solution.act()`，`_step()` 施控、更新 feedback/obs、再调用 `solution.observe()`，最后 append Recorder。`env.step(action)` 不会调用 `Solution.observe()`，info 目前仅有 task success/failure/metrics 与 step/time；readiness 只由私有 `_execution_info()` 生成，target/applied acknowledgement 也不在 public info。若外部 loop 在 `env.step()` 返回后才 observe，observer failure 会发生在 transition 已 append 之后，与现有 expert 路线“observe 成功后才 append”不同。见 [Solution](../../../../../task_env/tasks/pick_cube/solution.py#L501)、[reset info](../../../../../task_env/tasks/reference_env.py#L426)、[step/expert](../../../../../task_env/tasks/reference_env.py#L820)。 |
| Success / ending / recording | frozen task predicate `cube_lifted_v1` 以 lift >= 0.10 m 给 `is_success`；Expert 最后一阶段仍要求 `is_success` 且 collection endpoint >= 0.105 m 才报告完成，不能混为一项。Task failure 导致 terminated，horizon 导致 truncated；R1 Solution 观察 flags 并维护 Expert 自身完成。C03b 明确 Selected legacy `production-r1` 不支持 `stop()`；它仍由 `finish_recording(reason)` freeze canonical-trajectory-v0，记录 T+1、request/canonical/target/applied/boundary，但无 Event/Outcome。C05b 不得悄悄给 R1 补 Stop、改 stop semantics 或将其升级到 outer-v1；若 Stop Event/Outcome 是必需项，先单独明确扩展 C03b-R1 和 truthful v1 identity/binding。见 [task semantics](../../../../../task_env/tasks/pick_cube/task.py#L123)、[step](../../../../../task_env/tasks/reference_env.py#L909)、[stop](../../../../../task_env/tasks/reference_env.py#L1140)、[recording](../../../../../task_env/tasks/reference_env.py#L1201)。 |

**C05a3 consumer-specific result.** C05b 当前 R1 绑定的实际格式是 canonical outer v0（不带 Events/Outcome/native substep stream）。本轮 C05a 真正格式证据覆盖 generic H5 v3、canonical outer v1、execution stream v3 的真写读；并复用 canonical-v0 PickCube factory/selected-consumer 文件回读及 execution legacy v1/v2 fixtures。补充测试覆盖 execution H5 真未知版本、request 与 structured request 错配、applied ack 与 target 错配、Controller/Profile identity 错配、state boundary 错配及 Event/Outcome episode/boundary 错配；pending native interval 仍拒绝 freeze。canonical/execution 的 Event 只与 `episode_id + boundary_index` 关联，旧 BoundaryRecord 没有唯一 episode-local UUID，本轮不伪造这种身份能力。没有发现已证明的 C05a storage production defect；真实 PickCube R1 的 provider freshness 与外部 Solution lifecycle 仍是 C05b 前置。

**最小施工方案与分类。**

- **COMPOSE_EXISTING**：继续由 `PickCubeReferenceEnv`/`SelectedReferenceEnv` 拥有 RuntimeSession、R1 Controller、Task evaluation 与 Recorder；直接复用 `PickCubeReadinessConfig.from_source()`、`PickCubeReadinessSolution`、`ExpertExecutionInfo`、`CanonicalControlReadiness`、`CanonicalControlFeedback`、`CanonicalRecorder`。创建外部 Solution 时复用 `build_artifact()`、`build_runtime_source()` 与 task-owned readiness config 构造，避免读取 `env.value`、`env.solution` 或建立第二个 Runtime/Controller。
- **EXTEND_EXISTING**：在 Task 的现有 factory/binding 与 `SelectedReferenceEnv` public boundary 上增加外部 Solution lifecycle 接线：reset/step 的 `info` 明确发布所需 `ExpertExecutionInfo`/readiness 与真实 control application acknowledgement；同一处提供 pre-record `observe` 完成点，保证 observer failure 仍按 C03a fault/transition 规则处理。必要反馈为必需数据，不能随 diagnostics 关闭；不新建 Solution registry、TaskEnv、Runtime、Recorder。
- **FIX_EXISTING prerequisite**：先由 GeoPhys 现有 reset/state/observation owners 修复 R1 reset 样本的 freshness/identity，或发布可验证的 reset-forward raw-force sample；Core 保持 raw force required，未验证时明确拒绝首个 compute。此项与 C05b 的 info wiring 不同，不能被 generic H5/Position profile 或单步 smoke 替代。按 `C02b_Feedback_Source_and_Sampling_Audit.md` 现有具体 Probe 结论，本轮不能进入声称双 Provider R1 S2 已可执行的完整 C05b。

推荐未来 C05b 切片顺序及验收：

1. **S1 public lifecycle contract**：冻结外部 driver 的具体调用顺序；同时比较 legacy `step_expert()` 与外部 `act → selected step → observe` 的 Task success、Expert 0.105 m completion、stage event、10 ms boundary、target/applied identity。注入 missing/stale readiness、`observe` 抛错、Recorder append 失败；在任何 observer/recording 失败后不得续步，也不得把 incomplete transition 留作有效记录。S1 需要真正对外公开已有 typed values，不能用私有 `_execution_info()` 或 synthetic force 冒充 public capability。
2. **解除 R1 provider 前置后做 S2**：GeoPhys CPU 与 MuJoCo CPU 分进程、同 Artifact/sample/config/seed 31，真实跑完 external Expert；证明 first reset/closing feedback fresh 且 boundary 对齐，实际使用 R1 identity/force mode/readiness，Task success 与 Expert completion 分开核对， clock/T/T+1/target/applied 相符。GeoPhys 必须先通过 reset freshness Probe；MuJoCo 一步成功不能替代。
3. **S3 recording consumer**：两 Provider 分别真实采集 canonical-v0 并用 canonical reader 回读，核对 Artifact/source/controller/solution identities、request→canonical action→target→applied ack、state boundary、T+1、flags、stop reason 与 S2 原始采集相同；对 incomplete/faulted run 拒绝 freeze。没有 C03b-R1 Stop/Outcome 的单独授权时，不要求或伪造 Stop Event/Outcome；不宣称 D0 replay、完整 Qualification 或 C05c Guard/native 500 Hz。

**当前放行结论：** storage 侧 C05a3 C05b-scope supplement 通过；C05b S1 的 public lifecycle 设计可以在既有 owner 内施工，但完整 R1 双 Provider S2/S3 被 GeoPhys reset required-force freshness 阻塞。下一条施工 Goal 建议先解开 C02b R1 freshness + typed/public admission；之后才做 C05b external Solution 接线。C02b Position S2 只证明 position-only candidate，不改变此结论。

## 4. 风险、源码依据与修订落点

P0 表示进入相关实施/集成前必须闭合的契约；P1 表示相应切片 gate 必须关闭。

| 优先级 | 原设计缺口、源码依据 | 原因/影响 | 修订落点 |
| --- | --- | --- | --- |
| P0 | 新 frozen task 的 feasibility/Judge 被原 B.8 推迟 | 与 [Stage-1](../../task-artifact.md#任务-contract-与冻结) 冲突，candidate 被误升 frozen | B04/B05/P99 保留既有冻结 gate，E 仅延后编排 |
| P0 | [selected observation/native callbacks](../../../../../task_env/tasks/reference_env.py#L157-L225) 都 evaluate | Stateful 替换会在一个 outer step 多次累计 memory，诊断可能改结果 | B03a/b 只读谓词与唯一 commit 分离，native samples 单独 clock |
| P0 | [NutAssembly hold/ramp](../../../../../task_env/tasks/nut_assembly/solution.py#L465-L489)、[schedule](../../../../../task_env/tasks/nut_assembly/solution.py#L771-L797) | act/observe 外置仍遗漏共享控制状态、500 Hz 与施控时间 | C05c 的 control directive/feedback contract，Controller 保有执行状态 |
| P0 | [Recorder vector cast](../../../../../task_env/recorders/recorder.py#L104-L145)、[H5 action](../../../../../task_env/recorders/h5.py#L150-L157) | proposed action tree 不可存；Stop 无 transition 时旧 flags 不表达 episode end | C05a 前移，C03b outcome/loader bootstrap 显式一致 |
| P0 | [Artifact/ExecutionSpec](../../../../../task_env/artifacts/contracts.py#L306-L352)、[ResetSample](../../../../../task_env/artifacts/execution.py#L19-L62) | 改外层 version 不足，nested state/sample/metadata 仍固定 v0 | B04a/b 全链矩阵；精确 Timebase；旧 bytes/hash 保护 |
| P1 | [重复 UID 拒绝](../../../../../task_env/environment/types.py#L103-L127)、[按 UID 引用](../../../../../task_env/assembly/references.py#L190-L273) | 添加 entity_id 未必到达 compiler/controller，重复 Asset 实例会冲突 | A01/A03/A04 贯穿命名与映射，不另建 registry |
| P1 | [ImportedScene public lowering](https://github.com/SCAILab-USTC/GeoPhys/blob/c665ce5028a12bb4d2afe49f05e015fa9b684a39/src/scene/scene_import.py#L296-L363) 已存在 | 从零写 parser/visual lowering 会重复 Provider 能力、扩大维护面 | A04/D01/D03 public API 复用评估 |
| P1 | [Env bootstrap/单 Robot 限制](../../../../../task_env/environment/env.py#L113-L159) | 强迫继承会混合两类 runtime/state/controller 协议 | C03a 用 existing ports 适配；不统一 native ABI |
| P1 | [scalar step](../../../../../task_env/environment/lifecycle.py#L468-L501) 施控后还执行 evaluation/capture | 局部失败可能已推进物理，下一动作不能假设原状态 | C03a faulted、partial receipts、reset/close 规则 |
| P1 | [TreeCodec](../../../../../task_env/recorders/flatten.py#L18-L33) 构造缓存 spaces | 拓扑 variant/非兼容 switch 会破坏 wrapper/learner | B02 固定拓扑，C02c 非兼容 schema 新 Env |
| P1 | [camera provider](../../../../../task_env/render/camera/api.py#L17-L45) 与 [UI backend](../../../../../task_env/render/base/contracts.py#L19-L25) 是不同维度 | rasterizer 不能直接当 provider；移除同名 gate 不证明 independence | D05a 分层、D03/D04 动态 Oracle、D05b 实际 pairing |
| P1 | [Pendulum torque/window](../../../../../task_env/tasks/pendulum.py#L160-L195) 已有语义 | 只接受瞬时 state 的 evaluator 遗漏 action cost、重复已有窗口 | B03 evaluation context；共享 scalar/batch 非回归 |
| P1 | [CanonicalStateView](../../../../../task_env/artifacts/contracts.py#L418-L436) 为 scalar map | free/spherical 类型构造不验证 native lowering；alias 可能改写历史 | D02b 真实运动多 DOF、Twist/frame/存储 lifetime |

已有 controller hash 受 absolute meshdir 影响是[发布限制](../../../../releases/v1.1/known-limitations.md)，
本轮不能改历史 hash。新逻辑内容身份与 materialized path/provenance 分开，增加跨 checkout Oracle。
Hook 恢复绑定源码/资源/依赖版本，单文件 hash 不能冒充完整闭包。

## 5. 验收设计与 Evidence

复用 [Layer A/B/C 与 S0–S4](../../qualification.md#验证层级与成本)。
每条 meaningful test 明确 production path、Oracle、单位/tolerance、provider/backend/assets/representation、
sample/config/source identities、command/budget、pass/fail/error/timeout、unsupported 与 raw refs。
不将同一个旧 recipe 的运行结果计到未被消费的新声明；不将 fake tests 或 metadata 正确升级为实际能力。

| 风险/切片 | 最低 Oracle 与负例 | 证据级别 |
| --- | --- | --- |
| A01–A04 身份/导入 | 同 Asset 多实例；重名/循环/悬挂 refs；必要 source semantics；跨 checkout 内容 hash | S1，A05/D01a 真实编译/S2 |
| B01/B04a/b codec | strict unknown/type/duplicate-key、nested legacy/new read-write/reject 矩阵；保留原文件 bytes | S0/S1；不冒称任务 freeze |
| B02 reset | frozen sample、候选排序/RNG domain/version、requested-realized tolerance、拓扑拒绝 | S1 + rollout 前 S2 |
| B03a/b semantics | analytical boundary traces、action cost、once-per-sample、重复读取/乱序/gap/reset/missing | S1；现有 sample route 定向 S2/S3 |
| C02a/b/c control | 全 action 先校验、缺 Group/extra/NaN、multi-writer 拒绝、switch memory/ack/失败 | S1 + 真实 arm+hand/switch S2 |
| C03a/b lifecycle | reset/terminal/fault、partial interval、T=0/重复 Stop、outcome/bootstrap、构造失败/close | S1 + 适用 S3 |
| C04 obs | space.contains、非 Panda、private/privileged 原义、只读不改语义、诊断开关不改施控 | S1 + 真实 feedback S2 |
| C05a/b/c storage/solution | 三类 legacy fixtures；action tree/events；T/T+1；两 provider 同 frozen sample，native 500 Hz/hold/ramp | S1 + 真实采集/读取/S3；适用 replay 单报 |
| D01a/b materialize | 改声明会改实测；属性映射报告；缺必要 Frame/geometry；无 resampling/hidden settle | S1/S2，两 provider 指定交集 |
| D02a/b state | moving free/spherical、不同 position/velocity 维数、Twist/frame、consumer 同时钟、alias 失效 | 数学 S1 + native S2 |
| D03/D04 visual/camera | 运动像素、same-step、双 consumer、projection/backprojection、seg ID/SceneInstance、reset freshness | S1 + 真实动态 S2 |
| D05a/b pairing | actual manifest 不扩权、缺 deps/modalities、共享 session/refcount、first realization、capture 不推进物理 | S1/S2，真实 task route 适用 S3 |
| P99 | 新 Scene/Task 确实进入 make_env→reset→step→obs→record；legacy/public/batch 相应非回归 | 有界 S3；新 freeze 另需 Stage-1/Judge，S4 独立授权 |

Stop 不改写最后 transition flags，也不添加伪物理步；final outcome/loader 的 end/bootstrap 解释必须
一致并有 schema identity。Partial native interval 作为 error receipts 记录，不能 finalize 为完整有效 transition。
Camera buffers 与 capture metadata 原子关联，Recorder 持有的数据不能随零拷贝 native view 跨步失效。

P00 需逐条识别现有更强/邻近 detector；退休 import 失效时先判定保护义务应迁移还是归 frozen source，
修复或替代测试须在受批准切片内完成。不能删断言/吞异常/跳过失败 Provider 来获得全绿。
Shared TaskLifecycleAdapter/config 改动即使不做 Phase III，仍需 Pendulum scalar/batch/learner 的相关最小回归。

### 5.1 2026-10-20 源码审阅的运行事实

环境为既有 Python 3.12.14、PYTHONPATH=GeoPhys/src:.，没有 fresh dependency installation。
以下为审阅实测摘要，非完整持久化 acceptance package；临时 H5/日志未纳入本次文档提交。
不声称这些结果适用于随后提交的新 source identity，实施前须按风险复验。

| 执行 | 实际结果与解释 |
| --- | --- |
| 五个定向 pytest 文件（下列命令） | 93 passed、6 subtests passed、1 failed；156.14 s |
| 同批曾加入 test_solution_lifecycle.py | collection error：退休 nut_assembly.canonical_solution 缺失；该文件未执行 |
| Guard 唯一失败项 | test_full_candidate_composes_guard_policy_with_v5_clearance_path 引用退休 clearance_candidate_v5 |
| P1.1 contracts detector | 启动失败：退休 pick_cube.candidate 缺失；没有生成可用 report |
| P1.4 fresh import guard | 失败：同样依赖 pick_cube.candidate；不能把 --help 成功算 detector 通过 |
| PickCube × MuJoCo CPU，seed31/horizon6000/60 s budget | PASS；470 transitions，expert 完成 |
| NutAssembly × MuJoCo CPU，seed19/horizon6000/60 s budget | PASS；2373 transitions，Outcome/planned route/strict completion；无 readiness warning |
| NutAssembly × GeoPhys CPU，seed19/horizon3/30 s budget | 正常 truncated；CLI FAIL 表示 expert incomplete，不是新架构回归 |
| NutAssembly × GeoPhys CPU，seed19/horizon6000/60 s budget | TIMEOUT：CPU 限额；不能判完整成功或物理行为失败 |
| Pendulum public GeoPhys CPU reset/step | 一步通过，observation_space.contains 为 True |
| Camera ad-hoc pure/admission probes | pure 26/26；缺能力/非法/cross pairing 在 native construction 前拒绝 |
| MuJoCo native Camera ad-hoc microprobe | 80×64 RGB/Depth capture 通过；depth 中心 2 m；输入 canonical fixture state，未证明 physics-camera 新闭环 |
| PickCube MuJoCo real recording | PASS；canonical-v0，470 transitions/471 boundaries；storage roundtrip/T+1/provenance；不是 D0 |
| Structured dict action → 现有 TransitionRecorder ad-hoc probe | TypeError：vector cast 不支持 dict；支持 C05a 前移的 limitation |

可复现的五文件测试命令（使用已配置的 TaskEnv Python，不使用系统默认缺依赖环境）：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=GeoPhys/src:. python -m pytest -q -p no:cacheprovider \
  task_env/diagnostics/tasks/test_reference_construction.py \
  task_env/diagnostics/tasks/test_selected_consumers.py \
  task_env/diagnostics/tasks/test_nutassembly_outcome.py \
  task_env/diagnostics/phase1/integration/test_guarded_transition.py \
  task_env/diagnostics/render/test_backend_registry.py
```

未执行全仓测试、完整 GeoPhys 两任务回归、native Flora、真实双 Robot、独立 cross-provider
Camera pairing、学习收敛或正式 qualification。已有 MuJoCo 成功不能替代 GeoPhys timeout 缺口；
P00 需声明未来重跑预算/条件，不把 timeout 变 PASS。
更完整的历史限制继续由 [known limitations](../../../../releases/v1.1/known-limitations.md) 保留。

### 5.2 依赖 gate 复核与 D01a 实际执行顺序（2026-10-20）

表 3 仍是实施依赖的权威顺序。实际开工时，GeoPhys Gitlink 从原 D01a 规划审阅所绑定的开发同步点切换到
pure `main` `4436787e9cb85ce519506a2a9af86d1eeec9de2d`；因此在满足 A05/B04a/C01a 依赖后、D01a 之前增加了
一次 provider-baseline revalidation gate。该 gate 复跑 A03–A05/B04a/D02a/C01a/D05a 关联的十个定向测试文件，
结果为 **91 passed**。这一步是基线改变后的证据重建，不调整父 Goal，也不把旧 GeoPhys SHA 的结果转移到 main。

随后按表 3 进入 D01a。维护者已批准将 A05 `scene-definition-v3` mapping 原样作为 D01a microprobe 输入；真实
GeoPhys main CPU probe 与负例结果见 [D01a bounded execution receipt](04_Phase_D_Physics_Rendering.md#d01a-bounded-execution-receipt-2026-10-20)。
D01a 的 4 项定向测试全部通过，receipt 明确限定为一个 provider/backend 的静态 Scene materialization/reset probe，
不构成 MuJoCo、contact、controller/task success、D01b 或 Qualification 证据。接下来按依赖图可进入 D02b；B01/B02
须等待 D02b，不能仅凭 D01a 提前越过其直接前置。

### 5.3 D02b 实际切片与后续顺序（2026-10-20）

D02b 在 D01a 后按表 3 完成有界实现。真实 GeoPhys/MuJoCo CPU free-body probe 和现有 Recorder 内存副本
边界测试通过；本轮只证明 consumer/Recorder in-memory ownership，不触及 H5 schema。为保持职责与依赖清晰，
不将 C05a 整体前移，也不让 D02b 依赖未来的 typed-state persistence：C05a 仍在 C02a、C01b、D05a 后扩展
三种既有存储格式；若将来需要将 typed state 作为持久化字段，应在该切片内版本化并单独验收。

因此后续实际顺序按依赖图而非 Goal 编号推进：**B01 → B02 → B03a → B03b → B04b → B05**。
B04a 已在早期切片完成，D02b 是 B01/B02 的真实 provider 前置；B02 必须等待 B01 和 D02b，B03b 必须等待
B03a，B04b 必须等待 B03b，B05 必须等待 B04b。B 完成后再回到表 3 的 C01b，而不是提前启动 C05a。

截至 2026-10-20，B01 和 B02 已按此调整顺序完成 bounded implementation。B02 保留 `ResetSample` v0，扩展
现有 `RuntimeSession.reset_plan()` 做 Scene identity 与 rollout 前 realization gate；GeoPhys/MuJoCo CPU 三刚体
probe、PickCube PCG64-v0/NutAssembly NA-S0 sample 相等检查，以及 A05 `scene-definition-v3`/source-closure
GeoPhys fixed-reset integration 均通过。自由刚体随机化 probe 本身不代表通用 A04 importer lowering。
详细范围与限制见
[B02 bounded slice](02_Phase_B_Task_Semantics.md#b02-bounded-rolereset-plan-slice-2026-10-20)。
B03a 现已通过显式只读 predicate/action-context contract 与现有 Reward Oracle 定向回归：它复用
`TaskDefinitionBase` / `TaskLifecycleAdapter`，让 false、unavailable 与 no-evaluator 可区分；Pendulum 的
windowed success 仍留给一次性 temporal commit，不在 predicate read 中累计。新增 B03a 与 PickCube/NutAssembly
selected consumer/reference construction 回归合计 **50 passed**；B01/B02/D01a/D02b 与 B03a 组合回归另 **25 passed**，
只有一条 Taichi 上游 deprecation warning。详细实现范围与测试记录见
[B03a slice](02_Phase_B_Task_Semantics.md#b03a-read-only-predicate-action-interval-context)。
B03b 现已完成：TemporalRule 仅声明 rising-edge、样本计数 dwell 和有序 edge sequence，mutable progress 留在
现有 lifecycle owner；reset、gap、missing、duplicate/conflicting boundary 与乱序均有明确处置；重复提交 fingerprint
覆盖公开 RuntimeSnapshot 字段和 action/applied/interval/predicate 输入。B03a/B03b 与 reference/selected consumers
回归 **65 passed**；B01/B02/D01a/D02b 与两切片合计 **40 passed**，仍只有一条 Taichi
上游 deprecation warning。临时 sample-count dwell 不冒充物理连续时间；边界身份/clock来自 D02b 契约，真实 Provider
NativeIntervalEvidence 与 batch temporal commit 保持未支持。详细范围见
[B03b slice](02_Phase_B_Task_Semantics.md#b03b-bounded-temporal-memory-boundary-commit)。
B04b 已按依赖完成 bounded Source→TaskArtifact v1 compiler/codec/hash；冻结 TaskArtifact v0 和未证明的历史轨迹
reader 均保持原样。新编译器只产 candidate，不接现有 Runtime/Recorder 主链。随后完成 B05 reference task 语义差分与
旧路线保护；B 阶段收尾后按依赖返回表 3 的 C01b。

B04b 在原定依赖上完成：`TaskArtifactV1` 与 exact-schema `decode_task_artifact()` 留在现有 artifact owner；
编译器复用 strict B01 Source、A Scene identity、B02 role-candidate validation 与旧 v0 semantic bridge。旧 Entity
identity 必须精确存在；非同名 Frame/Joint 只接受显式类型化绑定，绑定进入 v1 identity。它用逐字段
`source_retained_v0_fields` 和 source Artifact identity 指针显式保留尚不能由 Canonical Scene 精确表达的旧 World
数据，不复制 Scene、Entity topology 或 Provider Runtime。B04b+B04a codec fixture/roundtrip/reject 合计 **12 passed**；
另拒绝 v0 `scene` Entity 作为 `rigid_body` Role、source-retained pointer 形状/字段不完整和嵌套未知字段。与
B01/B02/B03a/B03b、D01a/D02b、reference construction、selected consumers 定向回归合计 **97 passed**，包含一条 Taichi 上游
弃用警告。没有改 Timebase 精确 gate、ResetSample/State/Camera/
Trajectory/H5 reader，也没有真实旧 H5 golden bytes，因此这些 reader compatibility 继续 deferred。详细边界见
[B04b slice](02_Phase_B_Task_Semantics.md#b04b-taskartifact-v1)。

B05 已按上述顺序完成 bounded semantic gate：NutAssembly 使用 A05 source-backed Scene projection，PickCube 使用 A04 实际
Panda imported structure，并把任务局部 table/cube 几何留在源 TaskArtifact identity 下；两个 v1 candidate 均在固定
`CanonicalStateView` fixture 上保持 legacy evaluator 的 success/reward/metrics。`test_phase_ii_b05_reference_semantics.py`
**2 passed**；NutAssembly outcome、reference construction、selected consumer 定向回归 **80 passed**。此证据不接通 v1
Runtime/Recorder 路线，也不代表实际 trajectory replay、Stage-1、Provider qualification。B 阶段后按依赖返回 **C01b**；
C05a 不提前于 C01b、D05a 和 C02a。

B01 的实际源契约只收显式 Entity-ID 候选；当前 A `EntityInstance` 没有 tags owner，因此 tags 选择不能作为 B02
前置假设，也不能临时新增第二套 registry。B02 负责把候选解析到 A03 Robot/Entity 声明并证明 reset-time
selection；若 region/type selector 在现有 Scene 中无法解析，应保留为 unsupported/deferred，而非静默按名称猜测。

### 5.4 C02a bounded implementation evidence（2026-10-21）

C02a 在 `codex/phase-ii-c` 基于 D01b/A03/C01b/D02b 完成了静态 Controller binding 编译及 structured action
全量预检，详细契约和边界见 [Phase C C02a receipt](03_Phase_C_Execution_Lifecycle.md#c02a-bounded-implementation-receipt2026-10-21)。
专项测试 **11 passed**；与 C01a/C01b、D01a/D01b、D02b、D05a、A04/A05、B04b 和 selected consumers 的定向交叉
回归 **87 passed**，`git diff --check` 通过。A05 Panda arm+gripper group 映射到一个现有生产 writer，两个受测
provider 的 legacy action/output 各执行一步；这保护既有路径，不代表 structured group action 已进入 Runtime dispatch。

因此本证据仅关闭序号 20 的静态 mapping/schema/preflight 部分。C02b 的多组施控、双机器人执行和 actuator-force
provider capability 均未由此获得支持；当前 CAPABILITIES 对 `actuator_force_query` 的缺口仍按 admission limitation
处理。下一项可并行前置工作为 C05a 的三类旧格式版本化存储与 reader/loader 验收，执行写入须仍等待 C03a/C04/C02b。

### 5.5 C05a bounded storage evidence（2026-10-21）

C05a 在原三个格式 owner 内添加 generic H5 v3、canonical outer v1、execution stream v3，并复用共用的版本化
BoundaryEvent、EpisodeOutcome、StructuredControlTransition 值。新 reader 精确按 version dispatch；旧通用 v1/v2、
canonical outer v0、execution v1/v2 的格式和历史 fixtures 保持原状。Training projection 必须是一条完整单 writer
schema/component order 映射，并与 generic H5 已存 action 数值逐项一致；multi-writer 与任意树 flatten 明确拒绝。
T=0 outcome/event 不产生 pseudo transition，execution incomplete interval 仍拒绝 finalize。详细规则见
[recording-and-learning](../../recording-and-learning.md#复用现有录制-owner)。

新增 C05a 专项 **7 passed**；C05a、record CLI、selected consumers 与 execution streaming 的最终定向组合为
**82 passed、2 deselected**。两项 deselected runner 依赖已经退休的 `task_env.tasks.nut_assembly.assets`；此前较小的
未排除组合为 **52 passed、2 failed**，失败均是该 historical import error。现有两类实测 selected route 仍沿用旧
canonical/execution schema；C05a 新存储 roundtrip 不声称新 structured Runtime dispatch、物理 D0 replay 或
Qualification。有关旧格式 fixture 的完整命令结果和失败边界见
[Phase C C05a receipt](03_Phase_C_Execution_Lifecycle.md#c05a-bounded-storage-receipt2026-10-21)。

## 6. 原稿保存、文档验证与二审交接

> 本节保留 2026-10-20 规划提交时的检查结果（当时 31 切片），不是当前 33 切片表的验证收据。
> 2026-10-21 的恢复修订与当前校验见 §12 及恢复审阅报告；历史检查数字不回写。

原稿只通过第一次提交保存，不在活动目录创建第二份 canonical 副本。第一次提交五个文件的 SHA-256：

| 文件 | 原稿 SHA-256 |
| --- | --- |
| 00_Phase_II_AD_Implementation_Blueprint.md | `05134fc479f2e03be00b7a247b4eae3e0e2a587533bec105bb45fc9aa93fb37a` |
| 01_Phase_A_Core_Object_Model.md | `418403f99c7f1a34154b2277ece3805fb0ea5d7a5f66840587843d8164633e5d` |
| 02_Phase_B_Task_Semantics.md | `e764dc8133bf95116f2d187b426294863d832b9dbadc72106d8d85a54b620fd7` |
| 03_Phase_C_Execution_Lifecycle.md | `ab655accbbfe1c536c5fc2867a229d4750bf62058347005843d284f86717f825` |
| 04_Phase_D_Physics_Rendering.md | `736fb007148c93d7a1495b00a8bf52c7645f23d8dc242351f8e5e33817b1e99e` |

第一次 staged 文件与审阅原稿已逐一核对字节/hash，包括原有 Markdown 行末两个空格；第二次修订规范化行末空白。
恢复/比较可用 `git show a299d8b:docs/module/task_env/goal/Phase_II/<filename>`，不改 frozen release refs。
Core 源码链接使用仓库相对路径，便于在 develop 二审；GeoPhys 内部路径使用其 Gitlink SHA 的上游链接，
避免把子模块当作主仓库普通目录。行为结论仍绑定本文声明的 f292df1 基准。

**已知静态治理限制**：consolidation inventory 的 docs limit 为 58；原稿加入后为 63，
本次六份规划加入后为 64。现有 validate_docs.py 会报告 `count limit exceeded`。
维护者本次明确要求新增规划文档，本修改未更改 inventory、上限或 validator，也不声称全仓治理脚本全绿。
须另行审定该历史整合数量政策如何适用于后续文档增长；本次只对文档内容/链接/依赖/原稿身份作有界验证。

本次规划修订的静态验证 receipt：

- 六份文件覆盖 20 个唯一父 Goal；31 个实施切片加 P00/P99 的依赖均指向表中更早的已定义条目，无环。
- 仓库链接/Markdown anchors 和 Gitlink-pinned GeoPhys source references 已检查，Python 引用行号均在文件范围内。
- 原稿提交的五个 SHA-256 与首次审阅逐字节一致；当时该规划修订提交的最终范围仅含本目录六份 Markdown，源码/Gitlinks 不变。
- 当时修订后的 staged `git diff --check` 通过；全仓 validate_docs.py 的唯一错误为上述数量上限，
  其链接、JSON、冻结 refs/保留 bytes/source-doc checks 未报告其他错误。
- 原规划修订轮次没有重跑 runtime/qualification；`5.1` 保留先前 f292df1 审阅结果，后续 GeoPhys main 基线复核与 D01a
  bounded microprobe 已追加记录在 `5.2` 和 [Phase D D01a receipt](04_Phase_D_Physics_Rendering.md#d01a-bounded-execution-receipt-2026-10-20)。

二审建议依次确认：

1. 对比第一次提交与第二次提交，判断这些决策和范围缩减是否合适，而非将规划合入当作实现批准。
2. 对照风险表的真实源码/callers，重点复核 semantic commit、NutAssembly hidden control coupling、
   三类 storage schemas、Provider public lowering 和版本矩阵。
3. 核对执行依赖表与各阶段切片一致；优先审 P00/A01/A02 和提前的 contract slices，
   不要求一次批准全部 100–175 人日。
4. 指定下一次 audit/implementation 的切片和 Evidence 范围后再启动；Task Harness/Agent Workflow 保持后续阶段。

本轮 D01a 增加了内部 RuntimeSource→GeoPhys public importer 的有界桥接与定向测试，并更新了 Phase II 计划记录；
没有修改 canonical contracts、module Skills、capability matrix、历史 Decisions 或 Provider 实现。若后续改变 public
API/ownership/capability，须按仓库治理同步 canonical docs/module Skills 并重新取得相应 review。

## 7. 后续协作、进度记录与阶段分支（2026-10-20维护者约定）

后续总审查Agent与施工Agent使用仓库本地ignored `workspace/phase_ii_coordination/` 交接命令、报告和审查决定。
本节只记录维护者批准的协作规则，不表示两个Agent/定时任务已启动，也不改变前文切片依赖或验收级别。
总Agent每15分钟审查进展；施工Agent为唯一源码和阶段文档写入者，每次实施命令最多包含两个已具备前置条件的序号，默认一个。

公共目录中的完整report不能替代本目录的进度记录。每个实施/返工切片仍按仓库既有documentation/test/module
Skills，在对应01–04阶段文档的既有Goal下追加适当说明：日期、分支和受测实现身份、owner/实际范围、测试命令及
真实结果、证据等级和相对Evidence引用、未跑/失败/timeout、风险及下一步。05记录跨阶段里程碑和阻塞，00仅在
蓝图事实变化时更新。原始日志/图像/H5留在workspace，不复制进规划文档；自检待审、工程接受、Human Judge与
Qualification保持区分。总Agent只写交接目录；阶段文档的后续review状态由施工Agent在获派命令或受限DOC_SYNC中同步。

B阶段收口需逐项核对B01、B02、B03a、B03b、B04a、B04b、B05的既定gate和验收记录。B闭合是有界工程出口，
不代替D01b/P99完整执行链或新Task Artifact的Stage-1/Human Judge。已到序号17/B05后，应在序号18/C01b开始前，
先完成B收口审查及阶段文档提交；如发现B必要缺口则先在B修正。

总Agent接受B收口提交后，向施工Agent发出明确的本地分支交接命令：从该精确提交创建并切换到
`codex/phase-ii-c`。施工Agent报告B/C ref、tree、Provider pin和验收引用；交接瞬间两分支必须指向同一收口SHA。
该最终冻结SHA记录在公共目录的不可改写handoff receipt，避免在提交自身文档中嵌入本提交SHA的循环依赖。
后续序号18–32及必要返工在C进行；`codex/phase-ii-b`固定在该验收提交，不继续写入、移动或删除，保留供后续
回退比对和维护者授权的Phase II分支合并。后续B功能修正也先在C，解冻/回填/合并另待维护者明确指令。
此为分支工作流冻结，不声称设置远端保护、发布新tag或授予任务资格；不自动push/merge，也不修改已有release冻结refs。

本次仅补充上述规则；B尚未因本节而自动冻结，C分支也未由本轮创建。正式进度以对应阶段验收记录和实际source/evidence为准。

## 8. B04a source-bound Evidence 重建里程碑（2026-10-20，cmd-0001）

B04a 已在受测实现 `f9543b8725d2990966743f49cebf9d68493b6b06` 上重建单项 provider-free S1 Evidence：现有
`test_phase_ii_b04a_legacy_matrix.py` 检测 **6 passed**，原始命令、环境、owner/fixture hashes 与日志见
[02 阶段文档](02_Phase_B_Task_Semantics.md)的 B04a 记录及本地报告。此状态是
`SELF_CHECKED_PENDING_REVIEW`，只覆盖该 detector，不声称 provider/runtime 或旧 H5 兼容已验证。

本命令没有补跑其他 B/D02b 检测；bootstrap review 中其余 B 切片与 D02b 的 `REWORK_REQUIRED` 状态仍待分别处理。
B 阶段尚未闭合，`codex/phase-ii-c` 尚未交接创建，18/C01b 不开放。旧 H5 golden-byte 缺口保持 DEFERRED；本里程碑不
改变 Task Artifact Stage-1、Human Judge 或 Qualification gate。

## 9. B 工程出口与 C01b 开放（2026-10-20）

在上述 B04a 单项里程碑之后，针对当前 `codex/phase-ii-b` 基线
`b3f8dc4381708b76c5003dde5da138d90518aefa`（tree `58340bab90620d417692342f6dc7e5cc1c92039b`）复跑 B01–B05、
D02b 与 C01a 的必要定向集合，结果 **56 passed, 0 failed, 0 errors**。完整命令、environment、Provider pins、
日志和 stdout digest 见 [B 阶段收口记录](02_Phase_B_Task_Semantics.md#b11-b-阶段有界工程收口2026-10-20)。因此 B 的有界工程
出口和 18/C01b 的直接前置已满足；这里不把工程出口等同于 B04a 历史 H5 缺口解决、TaskArtifact freeze、Stage-1、
Human Judge、Qualification 或 D01b 完整执行链。

分支交接按既定规则执行：先把本节与 B 阶段收口记录提交在 `codex/phase-ii-b`，再从该精确提交创建本地
`codex/phase-ii-c`；交接后 B 指针固定在收口 SHA，C 从同一 SHA 继续。该交接只改变本地工作分支，不 push/merge，
也不移动 `develop`、远端 refs、Provider pins 或冻结 refs。后续 18/C01b 仅在 C 实施。

**cmd-0001-attempt-02 报告勘误**：同目录 JSON 的 `final_commit` 和远端 ref 核验均为 `b3f8dc4381708b76c5003dde5da138d90518aefa`；
Markdown“远端同步”段写作 `1fb3a55…` 属记录笔误，详见 02 阶段文档的 B.11。原报告不可变，不回写历史记录。

## 10. 序号 18／C01b 动态 Admission（2026-10-20）

从 B 收口 SHA `006801074052c51db9845ccf64be1d21fc08609c` 创建本地 `codex/phase-ii-c` 后，完成序号 18/C01b
有界 admission slice。现有 `RuntimeSession.materialize()` 已用 TaskArtifact 的真实 requirement set 对所选 Provider 的
build-bound manifest 做 admission；本轮新增定向测试验证真实 PickCube/NutAssembly v0 Artifact 对当前 GeoPhys/MuJoCo
manifest 的正向交集，以及 caller-manifest 扩权、requirements 缺失、backend mismatch、unsupported renderer 的拒绝点。
legacy C01a config/plan、selected-reference construction 和 consumers 回归也通过，合计 **59 passed**。实现与证据范围见
[C 阶段 C01b 记录](03_Phase_C_Execution_Lifecycle.md#c01b-bounded-dynamic-admission-receipt2026-10-20)及本地 run metadata。

C01b 沿用现有 Artifact、RuntimeSession 和 Provider identity owners，不增加 production abstraction；通用 `BaseTaskEnv`
静态计划仍是 C01a 的 GeoPhys-only route，selected legacy routes 未迁移或重写。测试只 monkeypatch 既有 native
materializer 来检查 admission 前置边界，故本切片不声称 v1 Artifact 的 provider materialization 或任何新的 physics
qualification。后续序号 19/D01b 未启动。

在 C01b 完成时，`codex/phase-ii-b` 本地固定在 B 收口 SHA `006801074052c51db9845ccf64be1d21fc08609c`，本地
`develop` 与远端 `develop`/`codex/phase-ii-b` 指向 `b3f8dc4381708b76c5003dde5da138d90518aefa`。随后维护者明确要求
同步 C01b 提交链；远端 `develop` 和 `codex/phase-ii-b` 因此都前进到 `132eb0999ea9114cf89ffdd36751d4c45fe79ffb`，本地
`codex/phase-ii-b` 仍为 `0068010`。D01b 在本地 C 分支完成并提交后，经维护者明确要求，将该提交快进同步到远端
`develop` 与 `codex/phase-ii-b`，两者保持同一提交；本地 B 分支指针不变。

## 11. 序号 19／D01b vNext 双 Provider 有界验收（2026-10-20）

D01b 从 C01b 提交 `132eb0999ea9114cf89ffdd36751d4c45fe79ffb` 继续，仅在 `codex/phase-ii-c` 工作。它扩展现有
`TaskArtifactV1`、`TaskSourceV1`、`EpisodeResetPlanV1`、`RuntimeSession.materialize()` 与 provider adapters：v1
Artifact 必须精确绑定 Scene v3；Role/Reset 校验 TaskSource/Scene identity；reset source names 必须逐项对应 canonical
Frame/Joint；MuJoCo 通过公共 `MjModel.from_xml_string(xml, assets=...)` 消费 Scene-v3 scalar-axis projection，检查
runtime Frame、Joint 端点/类型/axis 与构造后的 public model。GeoPhys 继续复用既有 composer/importer；provider-neutral
MJCF projection 位于 RuntimeSource owner，GeoPhys 原模块保留 re-export 兼容路径。

以 A05 Panda + procedural square peg source 为限，在 GeoPhys `4436787e9cb85ce519506a2a9af86d1eeec9de2d` CPU 与
MuJoCo `3.8.1` CPU 运行 v1 Artifact 构建、固定拓扑 Role/Reset、同一 ResetSample 的 rollout 前 measured-state
gate 与各一条 physics step。基准 Scene/变体 Scene 的 `link1` canonical axis 改变后，实测 pose delta 分别约
`0.2462261`；同一 Scene 下跨 Provider pose delta 不超过 `6.42e-9`。不同 Scene identity 产生不同 v1 Artifact hash，
故各用自身 hash-bound sample；同一 sample 在每一 Scene/Artifact 下跨两个 Provider 原样复用。最大 reset joint error
为 GeoPhys `5.96e-9`、MuJoCo `0`；ResetSample 没有 free-body pose target，因此 pose error 的 `0` 只是空目标集合结果，
不作为 pose reset 证据。settle 为 `0`。

`test_phase_ii_d01b_vnext_materialization.py` 有 **6 项**；与 D01a、B02、B04b、C01b、D02b、A04、A05 组合为
**40 passed**。
receipt：`workspace/maintenance/phase_ii_d01b_20261020/d01b_vnext_materialization_receipt.json`（本机 ignored evidence）。
负例覆盖 Scene identity 错配、缺 Frame/Joint 映射、缺 mesh、source root 无界、非零 settle。当前不能据此推及多 Robot、
自由体 pose reset、controller/gripper action、contact、task success、rendering 或 qualification；Canonical 未声明的
geometry/inertia/contact/constraint/transmission 仍不得误标为已执行的 portable semantics。

本轮在 `codex/phase-ii-c` 完成本地提交，并将同一提交快进推送到远端 `develop` 与 `codex/phase-ii-b`；本地
`codex/phase-ii-b` 指针保持 `0068010`。本记录不包含序号 20 的实施。

## 12. C02b 恢复规划与第一轮进展（2026-10-21）

Recovery Review 原始文档修订授权与 C02b-P 审阅结论见
[C02b Recovery Architecture Review](C02b_Recovery_Architecture_Review.md)。维护者随后授权 E；当前完成 Position candidate 的 S1、双 Provider S2、Generic H5 v3 真写读与 fault evidence。执行顺序仍仅由 §3 的表定义；验收见
[C02b-E S1 Acceptance](C02b_E_Position_Profile_S1_Acceptance.md) 与 [C02b-E S2/H5 Acceptance](C02b_E_Position_Profile_S2_Acceptance.md)。

- **RA-01 Profile 分流**：为新位置 Profile 生成独立 writer/config/source/binding identity，只要求实际算法消费的
  Joint/Frame state；保留 R1 raw-force required 与 plan-bound admission 拒绝测试。之后的 C02b-R1 receipt 已关闭 PickCube legacy GeoPhys reset stale-force 前置，不改变该 required contract。位置 servo 的 physical force cap
  是 command，不是 query；position-only 不等价于 R1。
- **RA-02 P/E 检查点与双 Entity 子项**：C02b-P/E 已完成单 Panda Position candidate 的 identity/state mapping、force-free dispatch、双 Provider native actuation/ack、C03a fault evidence 与 H5 磁盘 state readback。2026-10-22 增加 exact `panda-main`/`panda-secondary` 独立 Position writers，同 RuntimeSession、16 个隔离 actuator resources、Entity-qualified target/ack/state 与 reset/record readback；GeoPhys CPU、MuJoCo CPU 双 Provider S2 和 S1 fault evidence 通过。这只关闭 P00/P99 最小双 Entity position-only 子项，不开放通用多 writer/Assembly/production capability，也不等于完成 C02b。记录见 [Position-based Profile Review](C02b_P_Position_Based_Profile_Review.md)、[S1 Acceptance](C02b_E_Position_Profile_S1_Acceptance.md)、[S2/H5 Acceptance](C02b_E_Position_Profile_S2_Acceptance.md) 与 [Dual Entity Acceptance](C02b_Dual_Entity_Position_Acceptance.md)。
- **RA-03 反馈/存储接口**：旧 selected R1 consumer 和 canonical BoundaryRecord 仍依赖 force/readiness；Position candidate 复用 typed state projection，现已接既有 Generic H5 v3 真写读。GeoPhys Position 路径不调用旧 force feedback；MuJoCo 按 plan policy 在 reset/step 不复制 force cache，legacy force-aware 默认行为保持。PickCube R1 reset freshness 前置现有 GeoPhys CPU bounded receipt；plan-bound raw-force typed publication/manifest admission 仍 BLOCKED。
- **RA-04 依赖同步**：采用 P00 的 33 切片表、C05a evidence crosswalk、C02c←C02b/C03b/C05a2。
  C03b 已完成 bounded scalar Stop/Outcome 路线且无 C02b 硬依赖；C05b/C05c 的实际 Solution/Guard 保真不能由位置 Profile 或本次 Stop 证据代替。
- **RA-05 Assembly 后置**：Logical members/preset 与 Physical Attachment 分开；本轮诊断 Scene 中两个 articulated roots 仍独立且无 attachment。跨 Entity fixed-joint 装配另审版本与 Provider S2，不改变现行 Scene v3 或历史收据，不成为 C02b 新前置；不把它与已通过的最小独立施控子项混为一谈。
- **RA-06 发布边界**：D05b 后、本轮 C02b 双 Entity 前的本地检查点为 `477ff8054fb57356e8d03414f2356dd0f18ea043`；本轮源码与报告保持未提交，未推送/合并。PickCube legacy force-aware reset freshness 有界关闭；C02b 仍受 typed/public admission、其他 required intersection 与 Qualification 阻塞，C02c、通用 Panda TaskEnv
  Stage 1 composition 缺口均未关闭；没有 Assembly 或 Phase II qualification。
