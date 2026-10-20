# TaskEnv 公共 API

以当前 source 与[唯一发布矩阵](capability_matrix_v1_1_0_candidate.json)为准。
Root facade 的声明见 [`task_env/__init__.py`](../../../task_env/__init__.py)，
组件创建见 [`registry.py`](../../../task_env/registry.py)。未知 UID 抛 `KeyError`；
重复注册默认失败。注册只保存 class，不应在 import 时构造 physics runtime。

## 两类 scalar 构造

| 类型 | 公共入口与配置 | 当前语义 |
| --- | --- | --- |
| 通用 scalar | `make_env("pendulum-v1", config={"runtime": {"backend": "cpu"}})` | `BaseTaskEnv` 的 Gymnasium 生命周期；另有 `two-wheel-balance-v1` |
| PickCube selected reference | `make_env("pick-cube-p16-reference-v1", config={"provider": "mujoco", "backend": "cpu", "horizon": 6000})` | lift-only task predicate，保留 selected P1.6 Artifact |
| NutAssembly selected reference | `make_env("nut-assembly-outcome-reference-v1", config={"provider": "geophys", "backend": "cpu", "horizon": 6000})` | Outcome Completion V1；只允许 `step_expert()` |

两条 selected route 只接受 `provider`、`backend`、`horizon`：provider 仅
`geophys`/`mujoco`，backend 仅 `cpu`，horizon 为 `[1,6000]` 内整数；render_mode、extra kwargs、
legacy overlays 会失败。不要把通用 `runtime` section 传入 selected reference。
每个 selected task 由 task-owned `task.py`、`solution.py`、`config.yaml` 与 `__init__.py` 所有。
UID 与序列化 Artifact ID 不同；精确 Artifact/config hashes 只引用发布矩阵，避免重复维护。

## 生命周期与 evaluation

`reset(seed=...) -> (observation, info)` 在首次 step 前调用；
`step(action) -> (observation, reward, terminated, truncated, info)`。
终端后需 reset，不能继续 step；使用 `try/finally: env.close()` 关闭资源。
通用 `BaseTaskEnv` 组合 task definition、reset sampler、runtime、action、observation 和 rendering。
`TaskEvaluation` 提供 reward、success、failure、metrics、reward_terms；reward 与
`info["is_success"]` 不能替代 Judge。通用 `ignore_done=False` 时 success/failure 可终止 episode，
horizon 产生 truncation；selected expert 的 stop/completion policy 必须单独读取。
Selected reference 同一 episode 不可混用 expert 和 external action；NutAssembly external action 明确拒绝。

通用构造先解析 task-owned YAML defaults，再深合并调用方 mapping/YAML（调用方字段优先），最后只允许
覆盖公开 environment sections；task topology/semantics 不接受 overlay。传入现成 `ResolvedEnvConfig`
时它本身是权威 resolved 值，不再叠加默认 YAML。`BaseTaskEnv.execution_plan` 暴露
`execution-plan-v0` 静态投影：包含 resolved configuration identity、timebase、当前 controller selection、
renderer selection 与 resource owner identities。计划在 GeoPhys bootstrap 前生成；它不代表实际 Provider
manifest admission、native materialization 或 reset realization。Selected-reference 的窄配置及 factory
分支继续作为兼容入口，暂未投影为同一个 normalized config schema。

## Facade、扩展与 advanced contracts

| API | Owner/import | 用途/限制 |
| --- | --- | --- |
| `make_env`, `make_agent`, `make_object`, `make_scene` | `task_env` | 注册组件构造，不证明执行能力 |
| `ENV_REGISTRY`, `AGENT_REGISTRY`, `OBJECT_REGISTRY`, `SCENE_REGISTRY` | `task_env` | 用 `uids()` 查询；扩展注册见 `task_env.registry` |
| `BaseTaskEnv`, `TaskEvaluation`, `RuntimeBoundary`, `ResolvedEnvConfig`, `ExecutionPlan` | `task_env.environment` | environment/config 生命周期；ExecutionPlan 仅记录静态准入阶段 |
| `resolve_env_config` | `task_env` | 解析并冻结公共配置；task-specific overlay 走 factory 分支 |
| `AssetManifest` | `task_env.environment` | assembly 资产声明；保留本地 source/root 与版本字段，可选稳定 source reference/revision 和 procedural generator 元数据；构造时不读文件，也不证明 importer 消费了对应 bytes |
| `make_parallel_env`, `register_parallel_env` | `task_env` | optional homogeneous factory，与 scalar 无互相 fallback |
| `TaskArtifact`, `TaskArtifactV1`, `decode_task_artifact`, `ExecutionSpec`, `CanonicalStateView`, `admit_capabilities` | `task_env.artifacts` | advanced data/admission contracts；TaskArtifact dispatcher 按精确 discriminator 解码，不自动升级；不从 root 假造导出 |
| `TaskSourceV1`, `TaskRoleDeclarationV1`, `TaskHookDeclarationV1`, `load_task_source` | `task_env.environment` | B01 strict authoring-input envelope；只含 identity/Scene reference/explicit Entity-ID role candidates/hook declarations，不执行 hooks，也不接收 execution config |
| `compile_task_artifact_v1` | `task_env.environment` | B04b bounded compiler；组合已验证 Source、结构化 A Scene 与现有 v0 semantic bridge，旧 Frame/Joint 别名只能通过显式类型化绑定解析，输出引用 Scene identity 的 TaskArtifact v1 candidate；不创建 Runtime，也不代表 D01b/qualification 支持 |
| `TaskInitializationV1`, `resolve_role_binding`, `sample_episode_reset_plan` | `task_env.environment` | B02 在现有 Task Source owner 中增加可选初始化声明及确定性 Role selection；采样必须使用结构化 A Scene 与对应 TaskArtifact v0，边界由 `UniformDimension` 持有 |
| `RoleBindingV1`, `EpisodeResetPlanV1`, `ResetSample` | `task_env.artifacts.execution` | `EpisodeResetPlanV1` 仅包装 Role/Scene provenance 和现有 `ResetSample` v0；`to_provider_sample()` 原样返回同一 v0 对象，不改冻结 Artifact/sample schema |
| `TaskEvaluationContextV1`, `TaskPredicateEvaluationV1`, `TaskPredicateResultV1`, `TemporalPredicateRuleV1`, `TaskLifecycleAdapter.evaluate_predicates`, `TaskLifecycleAdapter.commit_temporal_predicates` | `task_env.environment` | B03a 只读 predicate 与 B03b 显式 temporal commit；action/AppliedControl、声明 Timebase、实测 NativeIntervalEvidence、boundary/clock 均引用既有类型；step/observation 不自动调用。当前 temporal commit 限 scalar evaluation boundaries |
| `adapt_legacy_recipe_task_source` | `task_env.environment` | 只读兼容投影：从旧 `recipe`/`environment` mapping 提取 task identity、Scene 与固定 agent/object role；environment 仍由既有 `ResolvedEnvConfig` 路径解析，不改 TaskArtifact v0 |
| `ExecutionSpecV1`, `RendererSelectionV1`, `CameraRendererOverrideV1`, `decode_execution_spec` | `task_env.artifacts` | D05a 的显式版本化静态选择；保留旧 `ExecutionSpec` 无版本映射，v1 不自动降为 v0，也不表示已 admission/materialization |
| `CanonicalStateViewV1`, `CanonicalStatePublicationV1`, `TypedJointStateValue`, `TypedFrameStateValue`, `StateRequirements`, `NativeIntervalEvidence`, `StateViewLifetime` | `task_env.artifacts` | D02a contracts；D02b publication 原子绑定 boundary/lifetime。当前只有 GeoPhys/MuJoCo CPU `RuntimeSession.snapshot_v1()` 有界支持 scalar/free-base readback；不增加 contact manifest 能力或 H5 state format |
| `AssetDefinition`, `EntityInstance`, `SceneDefinition` | `task_env.artifacts` | Phase II A01 identity/provenance、A02 frames/articulations、A03 `scene-definition-v3` static composition；strict codec only，不构造 Provider/runtime |
| `FrameReference`, `FrameDefinition`, `ArticulationDefinition`, `JointDefinition` | `task_env.artifacts` | entity-qualified frame、固定变换、runtime anchors 与多 articulation topology；不执行 FK 或 provider lowering |
| `RobotInstance`, `ActuatorResourceDefinition`, `ActuatorReference`, `ControlGroup` | `task_env.artifacts` | Entity-qualified 的静态 Robot/actuator/group identity；`SceneDefinition.resolve_*` 仅解析静态声明，不定义 Controller、动作维数、native binding 或多 Robot 执行 |
| `RuntimeSession`, `RuntimeSession.snapshot_v1`, `RuntimeSession.reset_plan`, `materialize`, `provider_manifest` | `task_env.runtime.sessions` | advanced bounded session route；需合法 artifact/source/profile。`reset_plan()` 校验 materialized Scene hash，原样执行 ResetSample v0，并在 measured-state tolerance gate 通过前阻断 snapshot/step；GeoPhys/MuJoCo CPU 有界验证通过。`snapshot_v1()` 另要求精确 Scene identity、Joint/Frame bindings 与 StateRequirements；contact/native-interval 不由此支持 |
| `CameraCaptureIdentityV1`, `CameraRenderSource.capture_identity` | `task_env.render.camera` | 绑定 camera/source、ExecutionSpec v1、准确 manifest mapping、state boundary/clock 与 modalities 的静态 capture-request identity；不代表实际 capture 或 renderer pairing 已运行 |
| `RecorderConfig`, `TransitionRecorder`, `TransitionRecordWrapper` | `task_env.recorders` | 既有录制 contract；selected examples 使用 selected env 自有录制入口 |

D05a 的执行选择只新增在 advanced Artifact/Camera owners 下。`RuntimeSession.materialize()` 和当前
`create_camera_session()` 仍走旧 `ExecutionSpec` 与实际同名 physics/render admission；D05a 没有改变
`admit_render`、Provider manifest capability claims 或 native construction，也不允许 UI `render_mode` 冒充
Camera Sensor selection。现有 provider-capability-v0 mapping 原样保留；其 `identity_hash` 只绑定精确 mapping。

`TaskDefinition` 只消费公开 snapshot/state，不访问 solver。
`BaseTaskEnv` 的 scene/reset/task-definition hooks 是 Extension API，不是第二套 task factory。
配置公共 sections 包含 asset、scene、agents、objects、runtime、robot、action、observation、render、task、episode。
通用 action mode 包括 `absolute_pose`、`delta_pose`、`absolute_joint`；以每个 task/robot 的
`ExternalActionContract` 和 observation schema 为准，不能给 non-arm 强加 Panda 维度。

`load_yaml_mapping()` 继续由 `environment.configuration` 所有，并使用 PyYAML SafeLoader 拒绝重复 mapping
keys。B01 `TaskSourceV1` 是 task authoring input，不是 `ResolvedEnvConfig` 或自行完成的 `TaskArtifact`；B04b
只能通过显式 `compile_task_artifact_v1()` 与现有 v0 semantic bridge 编译。其当前角色候选仅使用 explicit Entity IDs，
因为 A 的 canonical `EntityInstance` 尚无 tags/selector metadata owner。
未知 source/environment 混用字段会失败，hook
引用不会触发 Python import 或执行。当前 PickCube `recipe`/`environment` 兼容适配仅投影 identity、Scene 与
固定 entity roles；执行配置仍沿旧 resolver，legacy TaskArtifact v0 bytes/hash 不变。

B02 的 `TaskInitializationV1` 对 B01 YAML 为可选字段；缺省保持旧 B01 输入可读，但 reset-plan 构造要求显式声明。
`resolve_role_binding()` 要求显式传入匹配的 TaskArtifact v0，只接受显式 ID 候选，按排序候选和 per-role RNG domain
生成 immutable binding；全部 Artifact Entity 与声明的 Frame/Joint 子拓扑都必须在 A Scene 中，Scene 可含 v0 未表达的额外结构。
AssetDeclaration identity 与旧 Artifact `asset_reference` 分属各自 owner，不由 B02 合并比较。`RuntimeSession.reset_plan()`
继续使用现有 `ResetSample` v0，并在 Scene identity 和 requested/realized tolerance gate 成功后才允许后续 snapshot/step；
原 `reset(sample)` 兼容入口仍保留。B02 证据为 GeoPhys/MuJoCo CPU 三刚体 synthetic reset probe，加 PickCube PCG64-v0 与
NutAssembly NA-S0 的逐字段 ResetSample 相等检查；另以 A05 `scene-definition-v3` 和真实 source closure 在 GeoPhys
验证了固定 authored reset-plan 集成。随机化三刚体 probe 使用 bounded direct MJCF/Scene-v2，不代表 A04 importer
已覆盖通用 free-body topology；不声称 TaskArtifact freeze、完整任务 rollout 或 SAPIEN/Genesis qualification。

B03a 的谓词结果把已计算的 bool（包括 `False`）、缺测/未生成的 `unavailable` 和无 evaluator 的
`no_evaluator` 明确区分。`TaskEvaluationContextV1` 复制冻结 requested-action payload；`AppliedControl`
仍表示现有 runtime 控制结果。`Timebase.control_dt` 仅为声明 cadence，`measured_control_interval_s`
只有输入现有 `NativeIntervalEvidence` 时才有值。当前 PickCube `cube_lifted` 复用其 lift-only reward oracle；
Pendulum 暴露瞬时 `upright`，纯谓词读取不会推断依赖窗口的 `task_success`。谓词读取是 lifecycle 的显式调用，
不会替代或改变旧 `TaskDefinition.evaluate()`、reward、Pendulum scalar/batch 窗口或 selected-reference native callbacks。

B03b 的 `TemporalPredicateRuleV1` 只声明 rising-edge、连续 evaluation-boundary sample dwell 和按 rising-edge 匹配的 sequence；
progress 由现有 `TaskLifecycleAdapter` 持有，并在 `reset_task()` 清除。调用 `commit_temporal_predicates()` 才会提交一个
`StateBoundaryIdentity` + `StateSampleClock`；精确重复输入幂等返回，不同输入/乱序拒绝，boundary gap 或 unavailable source
清除相应连续进度。dwell 的 `required_samples` 是外层 evaluation sample 数，不是物理秒或 native substep 数；NativeIntervalEvidence
仍只为该 outer boundary 提供时间/来源证据，不把其内部 native samples 当作多次 task commit。当前为 scalar-only S1 contract，
Temporal rule 不进入冻结 TaskArtifact v0，也不建立持续时间 Guard 或自动接入 observation/native callback。

## Parallel、退休和缺失路线

`make_parallel_env` 要求显式 homogeneous registration。`execution="local"|"remote"`
控制进程边界，`runtime.batch_physics_layout="merged_scene"` 控制物理布局，两者独立。
Remote 使用 spawn，并在 child 重建 registry。未支持的任务不退化成 N 个 single env。
当前学习/渲染有界样例是 Pendulum CPU；不能据此宣称 manipulation batch 支持。

Go2 task/robot/profile/RSL 专用路线、GeoChora-owned static-template physics、旧 PickCube/NutAssembly
construction routes 和部分 camera/render CLIs 已退休，不能静默 alias。显式
`runtime.static_template.*` 及 `static_template` layout fail closed；默认 legacy config 对象残留
仅为保持无关 resolved identity，不代表 active implementation。
通用 RL/Batch/Device/Vectorization contracts 保留，GeoPhys-owned `GeoPhysRigidBatchRuntime`
不是已注册的 TaskEnv batch factory。详见[迁移](../../releases/v1.1/migration.md)。

统一 Validator、通用 `Runner(env, policy).run()`、完整 Task/Policy Harness 不作为当前 API。
现有 `task_env/alg/runner.py` 的 PPO dispatch 与各脚本 rollout loop 不能冒称统一 Runner。
符号级细节见 [API reference](../../../task_env/doc/api/index.md)。
