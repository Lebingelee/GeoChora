# Phase II Architecture Review — 决策、切片顺序与验收

> 状态：PROPOSED / READY FOR SECOND REVIEW；2026-10-20。
> 维护者授权本次规划修订、两次提交并推送 develop，随后由网页 GPT 二审；没有启动代码实施。
> 源码审阅基准：develop@f292df149f41520b484ff27cf2ff78a584903013。
> 原始五份草案由提交 [a299d8b](https://github.com/Lebingelee/GeoChora/commit/a299d8b) 按原字节保存。
> 本文是本组规划的决策/执行顺序入口；`01–04` 是各父 Goal 的详细契约。都不是新的能力矩阵或 Qualification Decision。

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
| Camera | v0 RGB/Depth、static triangles、同名 provider admission | 动态 visual、segmentation、独立 pairing 尚属提案 |
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
| Multi-robot | 双 Robot 静态命名/引用必测；真实主线先单 Robot/arm+hand | 双 Robot 动力学需独立 D01b/C02b S2，否则准确标 unsupported/deferred |
| Scalar | 先统一公共行为，经已有 ports/adapter 适配 | 不要求立即同一具体 Env 类，不新造 UniversalRuntime |
| Semantics | TaskDefinition 适配 evaluation context，一 sample 一次提交 | native Guard 只读判据、observation、render/diagnostics 不改 Task memory |
| Action/record | structured request 与 target/applied 分层；C05a 前移 | 不把 NumPy vector writer 当 tree writer，不合并三类旧格式 |
| Stop | 独立 Boundary Event/EpisodeOutcome；不追加伪 transition、不回写已返回 flags | loader 以显式 final outcome/policy 决定 end/bootstrap；T=0/重复/terminal 后行为必须测试 |
| Controller switch | 同 schema/资源/单位/时序才允许 safepoint 替换 | schema 改变需要新 Env/wrapper/learner；默认拒绝 multi-writer，不建设通用 arbitration |
| NutAssembly | measured interval feedback + Controller-owned hold/ramp 受限请求 | Solution 不共享可变 hold，不跨边界读私有 stage；保留 500 Hz 和 strict failure/warning |
| Camera | pinhole、同步、RGB/optical-Z Depth；受限 segmentation 单独准入 | 任意 K、fisheye、真实 async/deformable 不因字段存在而支持 |
| Pairing 目标 | GeoPhys CPU physics × MuJoCo native renderer × rigid calibration RGB/Depth | 当前会被 admission 拒绝；需真实动态同步；segmentation 单独证明 |
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
| 16 | B04b | B04a、B03b | Source→vNext Artifact compiler/codec/hash；嵌套读写/拒绝矩阵 |
| 17 | B05 | B04b | 旧 samples/traces 语义差分与 legacy route；新版本无 freeze 自动继承 |
| 18 | C01b | B05、D02b | 实际 Task requirements/actual manifests、动态 admission；兼容配置分支 |
| 19 | D01b | D01a、B04b、C01b | vNext 与两 provider 固定拓扑 materialization/reset/realization |
| 20 | C02a | A03、C01b、D02b | Entity×Group bindings、完整 action/feedback schema、唯一 writer |
| 21 | C05a | C02a、C01b、D05a | 三类格式各自扩展 action/events/outcome；reader/loader 与 legacy fixtures |
| 22 | C03a | C02a、D01b、C05a | 现有 ports 的 scalar reset/step/fault；单 controller 兼容执行 |
| 23 | C04 | C03a、D02b | 固定 public/privileged/private schemas、必要反馈/诊断分离、capture 引用 |
| 24 | C02b | C02a、C03a、C04、C05a、D01b | 原子 group 执行，真实 arm+hand S2；缺 group/局部失败不留未知施控 |
| 25 | C03b | C03a、C04、C05a | termination/Stop/EpisodeOutcome；T/T+1、bootstrap 和 fault/terminal guards |
| 26 | C05b | C02b、C03b、C04 | PickCube 外置 Solution 的实际 step/record 路线，两 provider 回归 |
| 27 | C05c | C05b、D02b | NutAssembly feedback/hold/ramp 契约及迁移；500 Hz/Guard/Outcome/strict status |
| 28 | C02c | C02b、C05b、C05c | 同 schema switch 的 memory initialization、ack/events、原子失败与真实控制检查 |
| 29 | D03 | D01b、D02b、D05a | public visual lowering + rigid/articulation sync；像素运动、same-step、双 consumer |
| 30 | D04 | D03、C04、C05a | RGB/Depth 兼容→segmentation；mounted camera/depth Oracle、reset freshness |
| 31 | D05b | D05a、D04、C01b | 独立动态 pairing、first realization、依赖/资源失败测试；精确支持范围 |
| 32 | P99 | A05、B05、C02c、C05c、D05b | 所有必需切片及其传递依赖 receipt；真实新主线、Stage-1、docs/Skills/回归复审 |

D03 不以 C05c 为硬依赖；表中排在其后是建议主干，不要求 Renderer 等待全部 expert campaign。
相反，C05c 不等待高保真 Renderer。C05a 提前定义 events/outcome 存储，C03b 实现相应生命周期，
避免用后写的存储格式补救已开放的新 action/stop API。

B05 可以完成 legacy semantics 适配，但 vNext 全链执行要到 D01b/P99 验证；
D01a 只证明有限新 Scene bridge，不冒充完整 D01。父目标 implemented 必须覆盖其全部必需切片。
P00/P99 是 gate，不增设新的 Framework/Harness；当前提交不执行表中代码实施。

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

## 6. 原稿保存、文档验证与二审交接

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
