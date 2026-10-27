# Task Artifact、Experiment 与 Evidence

本页保留原 Artifact/Experiment/Evidence 的规范要求；字段与文件名示例是 workspace contract，
不声称已有统一、资格化的 schema loader/Validator/Experiment Engine。当前高级数据对象见
[`task_env/artifacts/contracts.py`](../../../task_env/artifacts/contracts.py)。

## 三个独立对象与工作区

一个 Task Artifact version 定义任务，供多个 Experiment 引用；一个 Experiment 定义如何使用
冻结任务，并产生一个 canonical Evidence package。不得在每个 Experiment 内嵌一次性任务副本。

```text
workspace/tasks/<task_id>/
  artifacts/ver_001/
    manifest.yaml, asset.py, solution.py, task.py
    local_assets/, validation/, judge_decision.yaml
  experiments/exp_001/
    experiment.yaml, evidence.json, evaluation_report.json, report.md
    judge_decision.yaml, videos/, trajectories/, refs/
```

生成 workspace 不提交。world/initialization/semantics 可按内聚性拆分，不强制具体 Python 文件名。
Task-local asset 属于 Artifact，复杂资源通过 `asset/` 引用稳定 version/hash；Evidence 只记录实际使用身份。
大 dataset、checkpoint、cache 放 source tree 外，以稳定 reference/version/hash 引用。
代表性 trajectory/video、plot/report、provenance index 与 machine-readable facts 留 Experiment。

## 任务 contract 与冻结

Artifact 包含 embodiment/world、semantic names、geometry/inertia intent、asset references、
initialization/randomization、timebase、observation/action/controller requirement、success/failure/reward、
evaluation contract 和 solution provenance。provider 选择属 `ExecutionSpec`，不改变任务身份。
Provider-neutral world/semantics 不导入 provider-native API；task adapters 在独立边界实现 materialization。
高级 strict codec 拒绝未知字段/schema、未声明 semantic references、非 finite values 和未知 capability；
TaskArtifact identity 只 hash artifact mapping，不接受 execution field；确定性 JSON/YAML roundtrip 保留原值。

Phase II A01 增加 provider-neutral `AssetDefinition`、`EntityInstance`、`SceneDefinition` 值，位于
`task_env.artifacts`。它们以版本化 ID 和 canonical mapping 表示资产来源与 Scene 内实例关系；
Scene hash 不依赖声明输入顺序，但会随 scene/entity/asset identity 或 source provenance 改变。
source SHA-256 是可选 provenance 字段；声明 hash 不证明 importer 读取了该 bytes。A01 不读取资产、
不执行 importer/materializer，也不将 native handle 写入身份值。原有 `world-v0` 与已冻结
TaskArtifact bytes/hash 不变；vNext Scene 值不自动投影为 TaskArtifact，也不改变发布能力或 qualification。
`AssetManifest`、`TaskCompositionSpec`、`ReferenceSpec` 和 `TaskReferences` 保持各自在 assembly、
注册组合及编译后名称映射中的职责。`AssetManifest` 可选声明稳定 `source_reference` / `source_revision`，
procedural source 还可声明 generator ID/version 与规范化 scalar 参数；这些字段不触发磁盘访问，且不替代本地
`mjcf_sources` / `asset_roots`。A04 的逐次 Evidence 分开记录 `AssetDefinition.identity_hash`（声明身份）、
同一受控输入快照的 Source Closure Digest（文件依赖按逻辑相对路径和精确字节摘要，或 procedural 生成内容摘要）
及 provider/importer-scoped identity。当前 public importer 未导出逐文件消费哈希，因此 Core 侧摘要仅在输入快照被
固定并验证后才能声称绑定到该次导入；GeoPhys 的 source/IR hash 仍是 provider 自有身份，不能替代来源字节摘要。
Phase II A02 的 `scene-definition-v2` 在同一 `SceneDefinition` owner 下补充 entity-qualified authored fixed
frames、runtime body/link anchors 与 Articulation/Joint 静态拓扑；`scene-definition-v1` 的 codec、mapping 与 hash
保持原样。Frame composition 只解析有足够 authored transform 的路径；动态 link pose 留给 D02 canonical state。
Joint 显式保留 parent/child link 内的 joint-frame transforms、joint-frame axis 及独立的位置/速度 coordinate
representations。该静态定义不执行 FK、physics lowering 或 control；closed-chain、transmission、joint limits、
mass/geometry/visual 细节须由后续 importer/materializer 映射、保留为受限来源或拒绝，不能宣称已支持。
Phase II A03 通过 `scene-definition-v3` 在同一 Scene owner 中组合 `RobotInstance`、Entity-owned
`ActuatorResourceDefinition` 与 Entity-qualified `ControlGroup`。Robot 身份直接使用 Entity ID，并引用该 Entity
的 articulation roots；不会另建可能与 Entity 分叉的 Robot ID。`ActuatorReference` 以 `(entity_id, actuator_id)`
结构化解析，ControlGroup 仅声明静态资源归属，并拒绝未知 actuator、跨 Entity membership 和重复静态 writer。
这些值不推导 joint/action 维数，不指定 Controller、提交时序或 native actuator binding。v1/v2 codec、mapping 与
identity hash 保持原样；objects/sensors 仍使用通用 Entity 与 Frame，不引入 Task Role resolver。旧
`TaskCompositionSpec`、assembly `TaskReferences` 和当前 Env 的单 Robot 执行边界未改变；双 Robot 目前仅有静态
composition/reference 证据，真实施控须由后续 D01/C02 路线另行验证。

Phase II-01 R01a 在同一 `task_env.artifacts` owner 增加独立 `logical-assembly-v1` strict codec：`LogicalAssemblyV1` 锁定作者给定的 assembly ID/revision、现有 Scene v1/v2/v3 的精确身份 pin 与规范排序成员。Entity member 保存现有 Entity/asset identity；reference-only subcomponent member 复用 `FrameReference`、`JointReference`、`ActuatorReference`，并用 `LogicalAssemblyControlGroupReferenceV1` 表示 typed ControlGroup 引用；nested member 只固定 child ID/revision/content SHA-256。computed logical hash 不写回自身 mapping，codec 输入被复制为 frozen 值，`to_mapping()` 返回独立 JSON snapshot。该合同不验证 Scene 成员存在性或 child digest，不做递归/投影/source closure/native materialization，也不授予物理连接或 Controller 写权；R01b/R01c/R03 仍负责其各自准入与消费。

R01b 在同一 artifacts owner 增加 advanced `resolve_logical_assembly(root, scene, child_assemblies)` 静态入口。它只读取一个严格复制的 Scene v1/v2/v3 值和显式 `(assembly_id, revision)` child catalog，先对可达 containment key 图做环/深度核验，再校验所有可达 Scene pin、child content hash、Entity/Asset 与 Entity-qualified typed references。结果 `ResolvedLogicalAssemblyV1` 由 immutable leaf tuple 组成；每个 leaf 保留 member 类型、完整路径、源 Assembly 身份/hash 与 local path。跨层重复 Entity owning、重复 typed target、路径碰撞、悬空/错版本 child 与越界闭包会拒绝；reference-only view 不分配第二个 Entity owner 或 writer。上界固定为32层与1024个展开 leaf；局部 memo 只复用同一调用内的静态展开结果，错误不污染输入或后续调用。此解析不求 runtime Frame pose、不产生 source/native mapping、Provider/Runtime资源或 Attachment admission；R01c增加后续静态source声明投影，物理lowering/执行能力须由各自Gate另行验证。

R01c 在既有 `task_env.assembly` source/compiler owner 增加 `project_logical_assembly_source(root, scene, child_assemblies, source_receipts=None)`。入口从当前输入重跑 R01b resolver，再将每个解析 leaf 关联到唯一的现有 Scene Entity、对应 Asset 声明及准确 typed Frame/Joint/Actuator/ControlGroup 定义；ControlGroup 输出沿用声明的 Actuator references。结果是独立版本化、不可变且可脱离调用者持有的 source projection，保留 root/Scene身份、完整segment路径、源Assembly身份/path及Asset声明身份。receipt 仅在 Scene/Asset/source字段相符时记录为 `MATCHED_DECLARATION_NOT_REVALIDATED`；无receipt或声明中的 `source_content_sha256` 均不代表本轮读取了bytes，默认状态是 `DECLARED_ONLY_NOT_BYTE_VERIFIED`。原Asset的可选null保持不变。该入口不调用旧 `compile_task_scene()`、Provider、XML lowering或Runtime，不创建物理Entity、writer、native名称/indices，不构成materialization或Attachment admission。完整Panda的arm/gripper视图共享 `panda-main`；独立Arm/Hand fixture保留两个Scene Entity及两个Menagerie来源声明，两者都只覆盖静态source关联。

Phase II-01 R02a 在既有 `task_env.controllers.canonical` owner 增加 advanced、provider-free 的 Arm-only 与
Hand-only Position leaf 值合同，以及独立的 Hand Force-aware 依赖/拒绝描述。`LeafProfileBindingV1` 固定 Scene、
Assembly revision/content hash、canonical member path/selector、Entity/Asset、source closure、profile/action schema、
algorithm/config、Provider/build/backend、100 Hz cadence、ordered Joint/Actuator、ControlGroup、Entity-qualified TCP
parent Frame、`T_parent_from_tcp` transform direction 和 Required State identity。Whole-Panda 的两个 Existing-Entity Subcomponent Reference 可分别选两个 ControlGroup；它们仍是只读引用，不
创建 Entity owner 或 Controller writer。两个独立 Entity 的静态 fixture 则仍由现有 Scene Entity owner 表示。
Arm binding 显式保存 ordered `joint1→actuator1` 至 `joint7→actuator7` 配对；TCP pose 按 `T_parent_from_tcp` 解释，值采用 m 与 wxyz。

Arm Action 是严格有序的七关节 rad 位置向量并按绑定限位核验。Hand Action 是总开度 `opening_m ∈ [0, 0.08]`；
指关节各为 `[0, 0.04] m`，测量开度定义为 `q1+q2`，两个手指通过 0.5/0.5 fixed tendon 和 joint equality 耦合，
只引用一个 `actuator8`。显式的旧 normalized adapter 为 `opening_m=0.04*(u+1)`；native mapping 声明
`ctrl=3187.5*opening_m`、`ctrlrange=[0,255]`、`gainprm=(0.01568627451,0,0)` 和 `biasprm=(0,-100,-10)`。
这只是候选合同中的来源映射，不表示已有 Core consumer 实际读取它。
Target/Ack 分别绑定 ordered resources、writer、source/binding/Scene、typed boundary 和 clock；Ack 是静态施用收据
形状，不证明 native apply、到位或任务成功。Position Required State 不需要 force；Force-aware 使用独立 identity、
显式 raw signed N / canonical closing N 分离及 phase/sequence/revision/freshness 等依赖字段，目前保持
`NOT_ADMITTED`，sign/transmission/phase 尚未审计。Force-aware 拒绝不应使 Position 需要力反馈。

R02a strict codecs 和 Scene/Assembly selector 检查只建立静态合同边界，不修改 TaskArtifact v0/v1 identity、旧
`RequestedAction`/`CanonicalControlTarget`/Ack 或 Runtime/Provider manifests，也不创建计划、执行 adapter 或 H5
格式。其 provider-free S1 不等于 Scene source projection、Runtime admission、native S2/S3 或 Qualification。

R02b 在现有 canonical Controller 与 RuntimeSession control owners 内新增严格版本化的 parent preset、whole-section
leaf override、effective plan、Arm/Hand Position adapters，以及显式 canonical/native mapping receipt 和整请求
preflight/dispatch。plan compiler 从当前输入重跑R01b解析及R01c source declaration projection，并验证完整唯一
Scene ControlGroup/ActuatorResource覆盖；实际 adapter 复用既有绝对关节 Position 与 Hand gripper opening 算法。
合成 receipt 明确标为 `synthetic_fixture`，只用于provider-free S1，不代表真实materialization。整体preflight通过后
才准备所有命令、consume边界、逐writer apply/Ack并请求单次外层step；部分apply、step或后续publication失败时，
使用既有 `ExecutionFaultV1` 记录真实进度并闭锁；`LeafDispatchProgressV1` 保留已准备的 Target/command patch
及失败前返回的每个 typed apply result，不回滚、不生成伪transition。当前没有真实Provider、SelectedReferenceEnv
或Recorder/H5接线；R02b经Sol局部兼容/拒绝门修正后获接收为ACCEPTED_S1_BOUNDED。R02c attempt001已在相同既有owners中实现
candidate、MuJoCo RuntimeSession leaf dispatch、typed state与Generic H5 v3 reader，provider-free定向S1为53 passed；其
MuJoCo probe在import前因合同字段名错误退出，故真实materialization、motion、H5 native readback及S2/S3均未运行，Provider admission仍未建立。
修正后的probe脚本未重跑。Sol复核进一步发现H5导入/解码、写入前Target boundary及clock校验缺口，状态为CHANGES_REQUESTED_S2_S3_NOT_RUN；合并修复与有界验证的返工包尚待执行。R01c继续独立负责静态source投影。R02c未改变R02a Force-aware `NOT_ADMITTED`、旧TaskArtifact/Scene/Reset/Profile/
Target/Ack/H5身份、R06兼容性gate、R05a blocker、DAG、Required Envelope或Qualification。

### R02c attempt002修复与Provider阻塞（2026-10-27）

attempt002在既有leaf-control、MuJoCo RuntimeSession、Generic H5 v3和SelectedReferenceEnv owners内修复严格command解码、stale Target写入前拒绝、`1e-12 s`物理clock比较、admission异常时单次close，以及probe合同/窗口预检。新增生产Recorder写入后关文件、独立H5读回及9类篡改拒绝的provider-free S1；定向集合28 passed。真实静态预检核对完整source closure、67个lowered assets与MuJoCo静态安装文件，合法合同通过；缺字段、source hash、脚本hash和冻结HEAD四种合同负例均被结构化拒绝，native计数为0。

获授权的唯一attempt002 native进程成功导入阶段开始，但运行时 MuJoCo 版本/API 检查返回 `BLOCKED_PROVIDER: loaded MuJoCo version/API differs from 3.8.1`，发生在compile、materialize、reset、forward和step之前；本次各native调用计数均为0，未产生physics/H5 episode，S2/S3为NOT_RUN。失败未被当作可重试的普通预步进程序错误，未启动第二进程或更换Provider。细节与原始日志保存在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02c_002/`；R02c仍待Sol复核，Provider admission与Qualification均未建立，R03b未启动。R06兼容性gate、R05a blocker、DAG、Required Envelope、P99及旧身份保持不变。

### R02c attempt003 Core publication failure (2026-10-27)

唯一获授权进程核验到MuJoCo package/runtime/API `3.8.1 / 3.8.1 / 3008001`及冻结的package/binding/library路径和哈希，编译未变的Panda closure，生成model-bound `nq/nv/nu=9/9/8` receipt并成功reset E1。首个控制interval完成五次`mj_step`后，typed state publication失败：leaf dispatcher把state fields作为tuple传给既有`RuntimeSession.snapshot_v1()`，而该owner要求typed `StateRequirements`。本轮未发布完整boundary或transition；关闭不完整Recorder时保留其`64 transitions / 65 observations`错误，未生成完整episode H5。S2/S3未通过；此为Core接线失败，不是Provider身份失败。

保留原native失败后，现有leaf dispatch owner改为构造controller-owned typed aggregate requirements；定向provider-free rework模块19 passed。该修正发生在native进程后，本attempt没有也不会重跑native，故修正后的S2/S3仍未验证。报告状态为`FAIL_CORE / S2_S3_INCOMPLETE_PENDING_SOL_REVIEW`；Provider admission、Qualification和R03b均未建立。原件位于ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02c_003/`。

Phase II D02a 在既有 `task_env.artifacts` owner 增加 `canonical-state-v1`、Entity-qualified joint/frame
values、consumer-owned `StateRequirements`、evaluation/native interval clocks、boundary revision identity、
explicit unavailable values 与 provider-view lifetime contract。`canonical-state-v0` class/codec/mapping 不变，
TaskArtifact v0 不新增 state fields，State 不进入 TaskArtifact identity。v0→v1 projection 必须调用者显式提供
`scene-definition-v2/v3`、legacy-name→Joint/Frame bindings、episode/sample/boundary identities；只可精确映射
标量 joint，不从字符串猜 Entity/Frame，也不把旧 scalar 值扩成 spherical/free-base state。缺少 required contact
必须 admission/read failure，optional 缺失则记录 unavailable，不能写成零。Provider-native view alias 由其
materialization/generation 和失效事件限定；Recorder 跨步保留数据须使用 owned snapshot/copy。此切片只有
provider-free S1 contract evidence；真实 provider projection、moving free/spherical state 与 alias invalidation
仍属于 D02b，不构成 runtime capability 或 qualification。`StateFieldRequirement.required_capability` 是消费方
的需求名称；它不会向 ProviderCapabilityManifest v0 添加新声明，当前 manifest 未知的需求必须被 admission 拒绝。

Phase II D05a 在同一 Artifact owner 增加 `ExecutionSpecV1`、完整 `RendererSelectionV1` 和
`CameraRendererOverrideV1`。旧 `ExecutionSpec` 继续使用没有 `schema_version` 的既有 mapping；
`decode_execution_spec()` 仅将缺失版本精确路由至旧 codec、将 `execution-spec-v1` 路由至新 codec，未知版本拒绝。
v1 的每相机 override 替换整组 provider/backend/profile/device，未覆盖相机才继承显式 default；绑定已知相机集合时
拒绝重复或悬空 camera ID。静态选择值可记录不同 Physics 与 Renderer provider，但不准入该组合，也不投影到旧
`RuntimeSession.materialize()`。现有 `provider-capability-v0` mapping 未增加字段，新增 `identity_hash` 是该 mapping
的 SHA-256，不是更高 capability 或 Evidence 等级。

D05a 在现有 Camera Source owner 新增 `CameraCaptureIdentityV1`，其 `capture_identity()` 将确切 CameraGeometry、
静态 RenderSource、ExecutionSpecV1、Renderer selection、Provider manifest mapping、canonical state boundary/clock
和输出 modality 绑定为一个稳定 identity。它表示 planned capture request，不证明已构造 renderer、执行 capture 或
生成图像；旧 camera/source mapping 和 `create_camera_session()` 行为不变。实际 pairing、device/runtime identity
解析、capture receipt、资源共享和 teardown 留给 D05b/D03。

Phase II-01 R04a 在现有 Observation、SelectedReferenceEnv 与 Generic H5 v3 owners 上增加 opt-in
`CameraObservationConfigV1`/`DynamicCameraObservationConsumerV1`，仅接入既有单 Panda Position candidate：明确 fixed/world 与 hand parent Frame/mount、双相机 canonical 顺序、RGB HWC float32、optical-Z depth 与 canonical Entity mask。未选择时保持 state-only 默认；typed boundary 后延迟 capture，相同边界复用缓存，Env lifecycle 负责 reset/fault/close 清理。Consumer 将返回 capture 的请求身份和 calibration 与实例实际 config/source/execution/manifest 及同一 typed parent Frame 交叉核对。H5 v3 保持根 ABI 并追加版本化 metadata sidecars；camera recording binding 锚点来自实际 state boundary digest、reset/transition clock、reference profile 与 finalized typed outcome/control，`load_camera_observations_h5()` 对这些独立记录 fail closed，同时校验 T+1、capture/calibration/label-map 与既有量化布局。attempt001原23项provider-free synthetic S1通过；Sol复核发现请求mount/capture绑定与H5独立state/episode锚点缺口。attempt002已完成定向修复，目标 provider-free S1 为33 passed，Sol复核已接收为ACCEPTED_S1_BOUNDED，原请求绑定及独立记录锚点缺口关闭。真实 MuJoCo/OpenGL/EGL、真实 Env S2 与同文件图像 S3 尚未执行，不能表述为 native camera capability、R04b/c 完成或 Qualification。

Phase II B04b 在同一 `task_env.artifacts` owner 增加 `TaskArtifactV1` 与 `decode_task_artifact()`。旧
`TaskArtifact.from_mapping()` 仍是严格的 `task-artifact-v0` codec；dispatcher 只按精确 `schema_version`
解码 v0/v1，未知或缺失版本拒绝，绝不自动迁移。`compile_task_artifact_v1()` 由现有 Task Source owner 显式组合
已验证的 `TaskSourceV1`、结构化 A Scene 和现有 v0 semantic bridge。Entity 名称必须精确存在于 Scene；Frame/Joint
引用精确匹配或由调用方显式提供类型化的 `FrameReference`/`JointReference` 绑定，不按名称猜测别名。解析结果参与
v1 identity。编译器不复制第二份 Scene/World；v0 的 Action、初始化、SemanticDefinition、Observation
要求、Timebase 和 RequiredCapabilitySet 由原有 typed contracts 表达。旧 World Entity 中尚不能由 Scene 精确表达的
`kind`、`asset_reference`、`geometry`、`collision_intent`、`parameters_si` 以 source v0 Artifact identity 及逐字段
`source_retained_v0_fields` 指针显式保留，不能静默删除。v1 identity 绑定 Task Source snapshot、Scene identity、这些
保留字段的来源 Artifact identity 和已表达语义；ExecutionSpec/Provider 不在其中。Timebase 的 native
`physics_dt × control_substeps == control_dt` gate 原样保留。

该 v1 仍是有界 candidate，不是新的任务发布/freeze 路径。D01b 已通过现有 `RuntimeSession.materialize()` 和
`EpisodeResetPlanV1` 接入一个受限 S2 路线：精确 Scene-v3、一个固定拓扑 RobotInstance、scalar reset/state、bounded
source root，且仅验证 GeoPhys/MuJoCo CPU。`TaskArtifactV1.validate_scene()` 核对 Scene 与显式 Frame/Joint bindings；
Role/Reset 使用同一个 hash-bound `ResetSample-v0` 在两 Provider 上分别执行 rollout 前 measured-state gate。
该接入不扩展到 Recorder、Camera、通用 free-body reset 或新的任务发布路径。它目前只桥接既有 v0 semantic fields；
B03b temporal-rule declaration 尚未序列化到 TaskArtifact。`ResetSample-v0`、
`CanonicalStateView-v0/v1`、CapabilityManifest-v0、CameraGeometry-v0 与三类 trajectory/H5 版本域均保持原 owner
和 reader；B04b 没有改写这些存储格式。`geophys-transition-h5/v1`、`canonical-trajectory-v0` outer H5 和真正的
canonical execution v1 bytes 仍缺历史 golden fixture，因此相关 reader compatibility 继续 deferred，不能用合成
数据宣称旧文件兼容。B04b 的 S1 codec/编译测试不构成 Stage-1、freeze、Provider qualification 或历史存储完整验收。

生命周期为 `draft -> candidate -> validated -> frozen -> archived`。
validated 表示产生检查/feasibility Evidence、等待 Judge；frozen 必须有明确批准。
拒绝或修改 frozen 任务必须新建版本，不得原地改变语义。
从初始需求到获准冻结的迭代次数应作为系统质量 metric 记录。

Stage 1 必须分别记录：

- Automatic Validator：config/schema、asset/reference、capability、reset/realized state、controller/action、
  observation finite/sanity checks；当前这些校验分散实现，统一 Validator 仍有缺口。
- Expert/randomized feasibility：首个 Stage-1 release 必须有 randomized reset probe，分别报告
  solved、invalid execution/state、expert failed/unknown；expert 失败不等于任务不可行。
- Human Judge #1：`judge_decision.yaml` 显式 `approve`/`reject`、judge type、原因、required_changes、
  可选质量意见。Agent 不得根据报告 prose 猜测批准。

Task Success、Expert Completion、episode terminated/truncated 分别属于语义、Solution、runtime；
存在成功后动作时必须声明不可变 completion policy、terminal stage、readiness/timeouts/budget 和
record/replay 状态，见[runtime contract](runtime-and-providers.md#expert-lifecycle)。

## Randomization 所有权

Stage 1 定义随机化 quantity/schema、hard bounds/allowed envelope、nominal train range、
feasibility distribution、frozen evaluation distribution、reset semantics 和可选 declared settle。
Core sampler 通过 task_seed 产生 `ResetSample`；provider_seed 与 determinism 独立，provider 不重新采样任务参数。
记录 requested sample 与 `RealizedInitialState`；超出声明的 reset tolerance 必须在 rollout 前失败。
正式 paired comparison 使用同一个 frozen EvaluationSampleSet，不以相同整数 seed 假设不同 provider 初态相同。

Stage 2 仅可在 envelope 内调整 training range、curriculum/schedule、sampling weights。
改变随机化维度、hard bounds、frozen evaluation distribution、success/failure 或 nominal task
必须走新 Artifact → Stage-1 validation → Judge → freeze，不能为了性能降低 benchmark 难度。

## Experiment provenance 与报告

`experiment.yaml` 至少保留 experiment/task IDs、Artifact version/hash、Core commit/version、
physics provider/capability/profile、render provider、expert/data config、learner/policy config、
training randomization、seeds、budget/resource limits、evaluation reference、external dataset/checkpoint refs。
事实报告包含 task/policy metrics、rollout stats、ID/OOD、oracle-state/visuomotor 区别、failure cases、
dataset statistics 及可获得的 budget/cost。事实写 `evaluation_report.json` 和 `report.md`；
Stage-2 acceptance 写独立 `judge_decision.yaml`，Human review 不被 metric 自动替代。

`evidence.json` 索引 Artifact/Experiment/Core/provider identities、validation、dataset/training/evaluation
summaries、video/trajectory refs、report、Judge 和可获得的 Agent/tool/simulation resource usage。
它不授予 Core patch 权限，不直接创建可信 PhysPi Skill。PhysPi 决定经验保留/提炼/验证，
Core promotion 由 Geochora maintainer 单独治理。

## Retention

保留 frozen/approved final Artifact、有诊断价值的失败版本、被提升知识/Skill/Core change 所依赖的 Evidence。
冗余 drafts/cache 仅按 retention policy 清理；跨系统引用不能只依赖易失相对路径，至少绑定
`task_id`、Artifact version/hash、`experiment_id`、Core version，并保护被引用 bytes 或复制到持久 store。
不要把 metadata/hash 当作丢失 raw Evidence 的替代。操作步骤复用
[已有 Experiment/Evidence Skill](../../../task_env/.agents/skills/task-env-experiment-evidence/SKILL.md)，
不再创建同义 Skill 或 schema。

R02c Sol review (2026-10-27): attempt002 command/H5, pre-write boundary and cleanup repairs are reviewed with bounded S1. The native stop exposed a probe API-version constant error (30801 instead of MuJoCo3.8.1 header value 3008001); Sol fixed it with strict identity regressions and pre-rejection observation capture. Original runtime values remain unavailable. S2 requires actual native motion/isolation; S3 requires those real Env transitions in the closed H5 and independent readback. Synthetic S1 is distinct; R02c remains S1_REVIEWED_NATIVE_PENDING, and R06/R05a/DAG/Required Envelope/P99 are unchanged.

R02c attempt003 update (2026-10-27): the single native process verified the fixed MuJoCo identity, compiled/materialized/reset E1, then failed after five `mj_step` calls when leaf dispatch passed an untyped tuple to `snapshot_v1()` instead of `StateRequirements`. No complete boundary, transition or H5 episode resulted; incomplete Recorder close diagnostics were preserved. A post-failure Core fix constructs typed aggregate requirements and passes 19 provider-free tests; it has no native verification in this attempt. Required S2/S3 remain incomplete and pending Sol review; there is no Provider admission, Qualification or R03b start. Evidence is in ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02c_003/`.

R02c attempt003 review: aggregate leaf publication uses typed StateRequirements, now validated before boundary consume and physics. Provider-free regression exercises the actual MuJoCo publisher, shared typed projection, production transition writer and independent H5/control comparison over synthetic IO. Native003 advanced5 steps before the old tuple error and stored only T0/T+1=1; a finalized failure artifact is not a complete64-step R02c episode. Original raw is immutable; future probe failures preserve public per-writer command/Ack/fault progress before Session teardown. S2/S3 remain incomplete pending a separately authorized004 execution.

R02c attempt004 update (2026-10-27): the authorized single MuJoCo 3.8.1 CPU process passed static source verification and runtime identity, then completed E1 arm-only and E2 hand-only at 64 outer intervals each. E1 passed its joint-1 motion/home oracle, closed a Generic H5 v3 file at T=64/T+1=65, passed independent leaf readback, and rejected all nine tamper cases. E2's requested Hand curve and recorded leaf controls were present, and its closed H5 passed independent T/T+1 readback, but the fixed physical oracle failed: opening minimum 0.068789857 m and excursion 0.007210143 m did not meet ≤0.02 m and ≥0.04 m. E3/E4 did not run; S2/S3 remain incomplete. The probe's `native_evidence.json` was secondarily damaged by `numpy.float32` JSON serialization during failure finalization; its immutable JSONL `probe_failure` event records the primary assertion and 2 materializations, 2 resets, and 640 `mj_step` calls. Exact `mj_forward` and RSS counters were not retained and are not inferred. A serialization-only probe fix plus regression passed 21 provider-free tests after the native run; there was no retry or change to physics, targets, oracle, or budget. Preserve attempt004 raw outputs at ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02c_004/` and all prior attempt failures. No Provider admission, Qualification, or R03b start is claimed.

R02c004 evidence review distinguishes immutable misleading raw counters from JSONL/H5 reconstruction: actual640 mj_step, two materializations/resets, E1 motion pass and E2 motion fail. Both64/65 H5 files are structurally readable; that does not turn E2 into physical acceptance. Forward/RSS remain unknown. A proposed source-calibrated50N/m Hand section override is a new experiment configuration over the existing versioned plan mechanism; the original2500 configuration/failure and numeric oracles remain frozen. It is not approved by Sol or by the existence of this proposal.

R02c005 selects a complete Hand section override through the existing effective
plan mechanism. SOURCE_CALIBRATED_HAND_50_V1 retains the parent preset and frozen
Task Artifact/source while giving the resolved experiment configuration and plan
new identities. Native Evidence contains four independently reset64-transition
H5 episodes, their actual requested/servo/native commands and matching typed
Target/Ack/state/source/plan/config identities. Independent post-close readback
also passes without loading a physics Provider. Sol accepted this exact case as
bounded S2/S3; old2500/default and004 failure evidence remain separate. Generic
outcome task_success=false reflects this control diagnostic, not failed motion;
physical gate results and horizon completion are recorded separately. No Human
Judge or Qualification decision is inferred.
