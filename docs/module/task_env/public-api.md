# TaskEnv 公共 API

Phase II 有界工程范围已由 [维护者决定](../../maintenance/phase_ii_scope_freeze_20261023/maintainer_scope_decision.yaml) 接受并冻结；API 交集限制、candidate 状态与 Formal Qualification 分开。

以当前 source 与[唯一发布矩阵](capability_matrix_v1_1_0_candidate.json)为准。
Root facade 的声明见 [`task_env/__init__.py`](../../../task_env/__init__.py)，
组件创建见 [`registry.py`](../../../task_env/registry.py)。未知 UID 抛 `KeyError`；
重复注册默认失败。注册只保存 class，不应在 import 时构造 physics runtime。

## 两类 scalar 构造

| 类型 | 公共入口与配置 | 当前语义 |
| --- | --- | --- |
| 通用 scalar | `make_env("pendulum-v1", config={"runtime": {"backend": "cpu"}})` | `BaseTaskEnv` 的 Gymnasium 生命周期；另有 `two-wheel-balance-v1` |
| PickCube selected reference | `make_env("pick-cube-p16-reference-v1", config={"provider": "mujoco", "backend": "cpu", "horizon": 6000})` | lift-only task predicate，保留 selected P1.6 Artifact |
| NutAssembly selected reference | `make_env("nut-assembly-outcome-reference-v1", config={"provider": "mujoco", "backend": "cpu", "horizon": 6000})` | legacy `step_expert()` retained; exact MuJoCo 3.8.1 CPU external Solution and GeoPhys `a53a8cf` CPU/CUDA cadence S2/S3 are bounded diagnostic results; the GeoPhys matrix deliberately uses host snapshot at every native step and does not expand generic support |
| Explicit Position candidate | `make_env("panda-position-servo-candidate-v1", config={"provider":"geophys", "backend":"cpu", "horizon":64})` | single Panda Scene-v3, fixed seed 31, 100 Hz / five 2 ms steps; state-only by default; opt-in R04a camera consumer checks capture identity against the actual request and typed Frame, while the H5 reader binds sidecars to stored state digests, clocks, typed controls and episode outcome; targeted provider-free S1 accepted by Sol as ACCEPTED_S1_BOUNDED, real renderer/Env/H5 S2/S3 not run; candidate without freeze/Judge/Qualification |

PickCube/NutAssembly 两条 selected reference 只接受 `provider`、`backend`、`horizon`：provider 仅
`geophys`/`mujoco`，backend 仅 `cpu`，horizon 为 `[1,6000]` 内整数；render_mode、extra kwargs、
legacy overlays 会失败。不要把通用 `runtime` section 传入 selected reference。
每个 selected task 由 task-owned `task.py`、`solution.py`、`config.yaml` 与 `__init__.py` 所有。
UID 与序列化 Artifact ID 不同；精确 Artifact/config hashes 只引用发布矩阵，避免重复维护。

## 生命周期与 evaluation

`reset(seed=...) -> (observation, info)` 在首次 step 前调用；
`step(action) -> (observation, reward, terminated, truncated, info)`。
终端后需 reset，不能继续 step；使用 `try/finally: env.close()` 关闭资源。
通用 scalar lifecycle 另提供 `env.stop(reason="external_stop") -> EpisodeEndV1`：Stop 只在最后一个完整公开边界结束 episode，不调用 Controller、不施控、不推进 Runtime，也不伪造 Gym transition。默认 external Stop 是 `truncated=True, bootstrap_allowed=True`；horizon 是可 bootstrap 的截断；task terminal 是 `terminated=True, bootstrap_allowed=False`；execution fault 是不可 bootstrap 的 fault outcome。现有 step flags 保持原值；同时发生 task terminal 与 horizon 时，EpisodeOutcome 以 task terminal 为最终结果，但不回写已返回的五元组。
对成功 reset 后尚未结束的 episode 调用 reset，会先在旧边界生成 Stop，并在新 reset info 的 `previous_episode_end_v1` 返回旧结果；close 也会在 teardown 前结束活动 lifecycle。reset 前 Stop、Stop/step 在 close 后均拒绝；同一 episode 重复 Stop 返回缓存的同一 `EpisodeEndV1`。execution fault 后 Stop 记录 fault 且停在最后完整边界，不把已推进但未完成公开 transition 的间隔补成 transition。
`SelectedReferenceEnv` 仅对显式 PositionServoV1 candidate 实现此 Stop；旧 selected production-R1 路径的 Stop 明确拒绝，旧 Controller identity、反馈要求与执行行为保持原样。
通用 `BaseTaskEnv` 组合 task definition、reset sampler、runtime、action、observation 和 rendering。
`TaskEvaluation` 提供 reward、success、failure、metrics、reward_terms；reward 与
`info["is_success"]` 不能替代 Judge。通用 `ignore_done=False` 时 success/failure 可终止 episode，
horizon 产生 truncation；selected expert 的 stop/completion policy 必须单独读取。
Selected reference 同一 episode 不可混用 expert 和 external action；NutAssembly raw external actions 明确拒绝。

PickCube selected `production-r1` 另有一个有界 C05b public Solution 调用序列：
`from task_env.tasks.pick_cube import build_readiness_solution` 构造 task-owned Solution，
`env.reset_for_solution(solution, seed=31)` 在现有 Artifact/source/controller/readiness identity 下 reset 并初始化该实例，
然后每个控制区间调用 `env.step_with_solution(solution)`。外部 caller 保留 Solution 对象作为唯一 stage-state owner；不读取
`env.value`、`env.solution`，也不调用私有 `_execution_info()`。reset/step 的 `info` 无条件包含
`expert_execution_info_v1`、`control_readiness_v1` 与 `expert_execution_boundary_v1`；边界身份注明 Core episode ID、
Artifact、legacy source ID/XML hash、实际 Controller/Solution、ResetSample 与 control step/time。reset 没有
`control_application_v1`。完成真实 step 后，step info 才发布带 requested/canonical action、真实 target 与 applied ack、
request/evaluation boundary、target/applied hash 的 `control_application_v1`。

`step_with_solution()` 会先校验当前公开 readiness/boundary，再调用 Solution `act()`、复用现有 Controller/RuntimeSession，
在 Recorder append 前调用 `Solution.observe()`。observer 或 Recorder 异常使用现有 C03a execution-fault latch；该区间不允许
续步，fault receipt 描述已发生的物理进度，不承诺 Provider/Controller 回滚。S1 对比 internal `step_expert()`，并覆盖缺失/过期
readiness、错误边界、observer 与 append 失败。此调用面仍使用冻结 PickCube legacy Artifact、`task-env-pick-cube` source、
`panda-v1/ee` TCP、required R1 feedback 和 canonical-trajectory-v0；不会借用新 Scene-v3 A05 candidate/plan identity，
不修改旧 Stop 拒绝、Task success/Expert completion 区分或历史录制语义。S1 公共生命周期已通过；之后的真实 external Expert S2
与 canonical-v0 磁盘读回 S3 又在 GeoPhys `a53a8cf` CPU 和 MuJoCo 3.8.1 CPU 分进程通过，同一 seed-31 ResetSample 下
分别记录 148/149 与 470/471 个 transition/boundary，并核对状态数值、身份和 action→target→ack。详见
[C05b S2/S3 acceptance](goal/Phase_II/C_Development_Record.md#c05b)。
该 legacy PickCube 有界结果不建立 Scene-v3 plan 身份、legacy R1 Stop/Event/Outcome、NutAssembly Guard、完整 C02b 或 Qualification；MuJoCo typed-force 另有新 Scene-v3 candidate 的精确 CPU build/source/Controller/plan 路线，不能转移到该 legacy Artifact/source。

NutAssembly 的 C05c 另有一个 task-owned `OutcomeSolutionV1` 路线：
`from task_env.tasks.nut_assembly import build_outcome_solution`，然后调用
`env.reset_for_solution(solution, seed=19)` 和 `env.step_with_solution(solution)`。
它保留内部 `step_expert()`，不允许任意 raw action。MuJoCo 3.8.1 CPU 的 seed-19 full external Expert、close Guard 授权与同一 execution H5 的 S2/S3 已在所记录 source/Profile 上 bounded passed。之后 GeoPhys `a53a8cf` CPU/CUDA × gripper 100/500 Hz 四格也完成指定诊断 S2/S3，真实测得更新/保持计数并通过 same-file H5 回读。该矩阵为本次授权诊断而在每个 native step 调用公开 `RobotArmObservationReader.read_cpu_snapshot()`，尽管其通常使用指导限定为低频；不改变 Provider 的一般 native-rate 使用合同。若要将 host-servo 的 native-rate Reader 用途转为常规支持，仍需由现有 Provider observation owner 明确 value/phase/freshness 合同，再由 Core RuntimeSession 绑定 materialization、episode/reset/evaluation boundary identity 并验证。结果不扩展到其他 Provider/backend、R1 typed-force、完整 C05c、C02b 或 Qualification。详见
[C05c receipt](goal/Phase_II/C_Development_Record.md#c05c)。

用于本次诊断矩阵的显式入口是 `NutAssemblyReferenceEnv.for_gripper_cadence_diagnostic(backend, gripper_control_hz)` 与 task-owned `build_gripper_cadence_diagnostic_solution(...)`。该入口只接受 GeoPhys CPU/CUDA 与 100/500 Hz，并复用同一 Artifact/source/Outcome/Guard/Recorder owners；默认 `make_env()` 与通用 selected admission 仍不接受 CUDA。四格 S2/S3 为授权诊断性证据：每个 2 ms native step 调用公开 `read_cpu_snapshot()`，不改变其通常低频使用合同，不增加全局 capability，也不证明 device-resident Controller。完整配置、结果与 H5 哈希见 [cadence comparison](goal/Phase_II/C_Development_Record.md#c05c)。

通用 `BaseTaskEnv` 的 `metadata["observation_schema"]` 公布 observation 每个 leaf 的路径、shape、dtype、
unit、frame、采样边界和 requiredness；`state` 是 public observation，`privileged_state` 是 task-defined
privileged/evaluation data。`private_state` 保留既有独立语义与路径（例如
`private_state.robot_base_pose_world`），不能当作 `privileged_state` 的别名。当前 builder 中声明的 leaf
均为必需字段；缺少 RuntimeSnapshot 所需来源时明确失败，不以零值补齐。

`metadata["info_schema"]` 描述 reset/step 的 execution facts、required feedback 和 optional diagnostics。
reset/step `info["simulation_time_s"]` 必须来自对应 RuntimeSnapshot 的有限公开 simulation clock；缺失或无效时
结果构造失败，并由现有 lifecycle fault 闭锁。`ObservationConfig.include_diagnostics` 默认 `True` 以保留旧输出；设为
`False` 只省略 action/ctrl clipping 诊断标记，不省略 requested/external action、controller target、requested/applied
control、universal action、task evaluation 或 clock，也不影响施控路径。TaskEnv info 的 camera capture 引用（若存在）
位于可选 `camera_capture`，来源为 `SensorObservation.camera_metadata`，并标注对应的 elapsed step 与 simulation time；
通用 `BaseTaskEnv` 的 policy RGB/Depth 仍走既有 `CameraObservationProvider` 与 `StateObservationBuilder`。
D05b dynamic CameraSession 的 RGB/Depth/Entity mask 目前由受限 pairing diagnostic 直接消费，尚未接入该 policy
observation 路径或 `TransitionRecorder`；capture 文件回读不代表 observation/Recorder 集成。

失败的 reset/step 在各自 lifecycle owner 中 fail-closed：需要成功 reset 才能再次 step，环境不会假设 provider 物理状态
可以回滚。`BaseTaskEnv` 与 selected reference 的 `execution_fault` 提供当前故障 receipt；构造期间失败时原异常对象
附带 `execution_fault`。`ExecutionFaultV1.physical_progress` 只描述当前控制区间的可观测进展
（`not_advanced`、`partially_advanced`、`advanced`、`unknown`），依据可信 public 前后 simulation clock 与预期
control dt；区间返回状态和 `control_step` 只用于交叉验证，不替代时钟。Native interval receipt 分开记录
`observer_confirmed_substeps`、`recorder_confirmed_substeps` 和 `native_substeps_expected`，回调/Recorder 数量不是
精确物理完成数。时钟缺失、执行证据冲突或信息不足时必须保留 `unknown`。`transition_status` 独立说明当前 owner
是否评估了 transition（`not_assessed`）、没有录制（`not_recorded`）、录制未完成、append 被拒绝或 transition
已确认有效；物理区间已完整推进也不能使不完整 Recorder evidence 成为有效 transition。
selected execution Recorder 的 pending interval 继续由既有 `freeze()` 拒绝。该诊断不承诺故障后的物理恢复。
若未完成的 selected recording 阻止 reset，当前 route 要求关闭并重建环境；C03a 没有新增丢弃 recording 的 API。

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
| `BaseTaskEnv`, `TaskEvaluation`, `RuntimeBoundary`, `ResolvedEnvConfig`, `ExecutionPlan`, `ExecutionFaultV1` | `task_env.environment` | environment/config 生命周期；ExecutionPlan 仅记录静态准入阶段；fault receipt 不创建第二套 Runtime 或恢复接口 |
| `EpisodeTerminationPolicyV1`, `SingleTaskLifecycleAdapter`, `EpisodeEndV1` | `task_env.environment` / `task_env.trajectory.canonical`（分别导入） | task-owned success/failure、horizon 与 external Stop policy；`EpisodeEndV1` 配对有序 `BoundaryEventV1` 与最终 `EpisodeOutcomeV1`。通用默认与 Position candidate 有界支持；legacy selected R1 与 vector Stop 明确不支持 |
| `resolve_env_config` | `task_env` | 解析并冻结公共配置；task-specific overlay 走 factory 分支 |
| `AssetManifest` | `task_env.environment` | assembly 资产声明；保留本地 source/root 与版本字段，可选稳定 source reference/revision 和 procedural generator 元数据；构造时不读文件，也不证明 importer 消费了对应 bytes |
| `make_parallel_env`, `register_parallel_env` | `task_env` | optional homogeneous factory，与 scalar 无互相 fallback |
| `TaskArtifact`, `TaskArtifactV1`, `decode_task_artifact`, `ExecutionSpec`, `CanonicalStateView`, `admit_capabilities` | `task_env.artifacts` | advanced data/admission contracts；TaskArtifact dispatcher 按精确 discriminator 解码，不自动升级；不从 root 假造导出 |
| `TaskSourceV1`, `TaskRoleDeclarationV1`, `TaskHookDeclarationV1`, `load_task_source` | `task_env.environment` | B01 strict authoring-input envelope；只含 identity/Scene reference/explicit Entity-ID role candidates/hook declarations，不执行 hooks，也不接收 execution config |
| `compile_task_artifact_v1` | `task_env.environment` | B04b bounded compiler；组合已验证 Source、结构化 A Scene 与现有 v0 semantic bridge，旧 Frame/Joint 别名只能通过显式类型化绑定解析，输出引用 Scene identity 的 TaskArtifact v1 candidate；D01b 仅在单 Robot、Scene v3、scalar reset/state 的 GeoPhys/MuJoCo CPU 交集中消费，不代表通用 Runtime/qualification 支持 |
| `TaskInitializationV1`, `resolve_role_binding`, `sample_episode_reset_plan` | `task_env.environment` | B02 原 route 使用 TaskArtifact v0；D01b 扩展为接受精确 Scene-bound TaskArtifact v1。两者仍产生既有 provider-facing `ResetSample-v0`，边界由 `UniformDimension` 持有 |
| `RoleBindingV1`, `EpisodeResetPlanV1`, `ResetSample` | `task_env.artifacts.execution` | `EpisodeResetPlanV1` 仅包装 Role/Scene provenance 和现有 `ResetSample` v0；`to_provider_sample()` 原样返回同一 v0 对象，不改冻结 Artifact/sample schema |
| `TaskEvaluationContextV1`, `TaskPredicateEvaluationV1`, `TaskPredicateResultV1`, `TemporalPredicateRuleV1`, `TaskLifecycleAdapter.evaluate_predicates`, `TaskLifecycleAdapter.commit_temporal_predicates` | `task_env.environment` | B03a 只读 predicate 与 B03b 显式 temporal commit；action/AppliedControl、声明 Timebase、实测 NativeIntervalEvidence、boundary/clock 均引用既有类型；step/observation 不自动调用。当前 temporal commit 限 scalar evaluation boundaries |
| `adapt_legacy_recipe_task_source` | `task_env.environment` | 只读兼容投影：从旧 `recipe`/`environment` mapping 提取 task identity、Scene 与固定 agent/object role；environment 仍由既有 `ResolvedEnvConfig` 路径解析，不改 TaskArtifact v0 |
| `ExecutionSpecV1`, `RendererSelectionV1`, `CameraRendererOverrideV1`, `decode_execution_spec` | `task_env.artifacts` | D05a 的显式版本化静态选择；保留旧 `ExecutionSpec` 无版本映射，v1 不自动降为 v0，也不表示已 admission/materialization |
| `CanonicalStateViewV1`, `CanonicalStatePublicationV1`, `TypedJointStateValue`, `TypedFrameStateValue`, `StateRequirements`, `NativeIntervalEvidence`, `StateViewLifetime` | `task_env.artifacts` | D02a contracts；D02b publication 原子绑定 boundary/lifetime。当前只有 GeoPhys/MuJoCo CPU `RuntimeSession.snapshot_v1()` 有界支持 scalar/free-base readback；不增加 contact manifest 能力或 H5 state format |
| `CanonicalStateViewV2`, `CanonicalStatePublicationV2`, `TypedActuatorForceStateValue` | `task_env.artifacts` | Additive D02 typed raw-force publication: exact decoder version, signed value, explicit unit, source closure/materialization, Provider sample revisions/phase/native clock, episode/reset and evaluation-boundary identity. `snapshot_v2()` composes existing Joint/Frame projection with typed force; v0/v1 mappings and hashes remain unchanged. Required missing/invalid/wrong-unit/stale-identity/unsupported-phase values reject. Publication is bounded to the exact Scene-v3 Panda R1 candidate on GeoPhys `a53a8cf` CPU and MuJoCo 3.8.1 CPU with the admitted native binary digests; no generic actuator-force capability |
| `ProductionCanonicalPandaController.source_artifact_hash`, `.source_xml_sha256`, `.tcp_profile_identity`, `.source_kinematics_identity`, `.expected_control_step` | `task_env.controllers.canonical.production` | Read-only actual-instance identity and evaluation-cursor view used by source-bound admission; adding these properties does not alter legacy R1 identity or compute/reset behavior |
| `ActuatorForceMeasurementV1`, `RuntimeSnapshot.actuator_force_measurement` | `task_env.environment` | Core Provider-adapter value contract for signed raw actuator-force provenance: source generation, sample/config/state revisions, native sample index/phase, validity, and selected-session episode/reset/evaluation boundary. Used by GeoPhys legacy force-aware and MuJoCo session-cache routes; wrapped by typed state v2 only for the exact admitted Scene-v3 R1 candidate. It does not grant generic actuator units or shared Provider capability |
| `AssetDefinition`, `EntityInstance`, `SceneDefinition` | `task_env.artifacts` | Phase II A01 identity/provenance、A02 frames/articulations、A03 `scene-definition-v3` static composition；strict codec only，不构造 Provider/runtime |
| `LogicalAssemblyV1`, `LogicalAssemblyScenePinV1`, `LogicalAssemblyEntityMemberV1`, `LogicalAssemblySubcomponentReferenceV1`, `LogicalAssemblyNestedMemberV1`, `LogicalAssemblyControlGroupReferenceV1`, `decode_logical_assembly` | `task_env.artifacts` | R01a provider-neutral `logical-assembly-v1` 静态值；Scene identity pin、typed Entity/reference/nested member 与非自指 content hash。strict codec 不解析、不 lowering、不代表 Attachment admission 或 physical support |
| `resolve_logical_assembly`, `ResolvedLogicalAssemblyV1`, `ResolvedLogicalAssemblyLeafV1` | `task_env.artifacts` | R01b bounded provider-free static resolver：对一个精确 Scene 和显式 child catalog 校验可达 closure，返回不可变 typed leaves/path/provenance；最大32层/1024 leaves。不投影 source、不创建 native mapping/Entity/writer或 Runtime |
| `project_logical_assembly_source`, `LogicalAssemblySourceProjectionV1`, `ProjectedEntitySourceV1`, `ProjectedLeafSourceV1` | `task_env.assembly` | R01c advanced provider-free projection：每次重验当前 Assembly/Scene/child closure，关联被引用的现有 Entity、Asset声明及精确 typed Frame/Joint/Actuator/ControlGroup定义；保留来源Assembly/path与声明级证据。receipt只核对声明身份，不重新验证bytes/closure；不lower XML、不创建物理Entity/native映射或Runtime |
| `LeafProfileBindingV1`, `LeafJointActuatorBindingV1`, `ArmPositionActionV1`, `ArmPositionTargetV1`, `HandPositionActionV1`, `HandPositionTargetV1`, `LeafApplicationAckV1`, `LeafRequiredStateV1`, `HandForceAwareDependencyV1`, `leaf_profile_catalog_v1` | `task_env.controllers.canonical` | R02a advanced provider-free leaf contracts. Strict values pin Scene/Assembly/member/Entity/Asset/source/profile/config/Provider/backend/timebase identities, explicit TCP transform direction, and ordered Joint/Actuator refs. The finite Force-aware catalog remains `CONTRACT_ONLY / NOT_ADMITTED / NOT_RUN`; R02b adds a separate compiled Position leaf plan and synthetic-IO adapter path, but does not alter the catalog or admit a Provider |
| `LeafProfileSectionV1`, `LeafControlPresetV1`, `LeafProfileOverrideV1`, `EffectiveLeafPlanV1`, `compile_effective_leaf_plan` | `task_env.controllers.canonical` | R02b advanced provider-free owner. Re-resolves current R01b/R01c inputs, requires complete Scene ControlGroup/ActuatorResource coverage, compiles exact immutable Arm/Hand Position sections, and derives `preset` / `partially_overridden` / `custom` from effective configuration differences. This is not a public factory or runtime admission |
| `LeafMaterializationReceiptV1`, `LeafNativeJointMappingV1`, `LeafNativeActuatorMappingV1`, `LeafNativeFrameMappingV1`, `LeafNativeTendonMappingV1`, `prepare_leaf_command`, `preflight_leaf_control_interval`, `dispatch_leaf_control_interval` | `task_env.runtime.sessions` (advanced opt-in) | R02b provider-neutral typed boundary and production preflight/dispatch owners. R02b S1 consumes explicitly `synthetic_fixture` mappings only; real Provider execution is attempted only by the R02c SelectedReferenceEnv integration below, whose native gate remains unverified. `LeafControlRuntime` extends the existing RuntimeSession owner, not a second runtime |
| `FrameReference`, `FrameDefinition`, `ArticulationDefinition`, `JointDefinition` | `task_env.artifacts` | entity-qualified frame、固定变换、runtime anchors 与多 articulation topology；不执行 FK 或 provider lowering |
| `RobotInstance`, `ActuatorResourceDefinition`, `ActuatorReference`, `ControlGroup` | `task_env.artifacts` | Entity-qualified 的静态 Robot/actuator/group identity；`SceneDefinition.resolve_*` 仅解析静态声明，不定义 Controller、动作维数、native binding 或多 Robot 执行 |
| `RuntimeSession`, `RuntimeSession.snapshot_v1`, `RuntimeSession.snapshot_v2`, `RuntimeSession.reset_plan`, `materialize`, `provider_manifest` | `task_env.runtime.sessions` | advanced bounded session route；需合法 artifact/source/profile。直接 `materialize()` 的 v1 route 仍只支持精确 Scene-v3、一个 RobotInstance、scalar reset/state、bounded source root 的 GeoPhys/MuJoCo CPU 路线；现有 `materialize_control()` owner 另有精确 Position candidate 和双 Position Entity admission，以及单个 source/Controller/plan-bound R1 typed-force admission：GeoPhys clean revision `a53a8cfe...` CPU 或实测 MuJoCo 3.8.1 CPU Python/native binary digest。两者都严格绑定新 Artifact、Scene/source closure、实际 Controller/TCP、`actuator8` 和精确 plan；不扩展 generic provider manifests 或其他 backend/transmission。`reset_plan()` 校验 Artifact/TaskSource/Scene identity，原样执行 ResetSample v0，并在 measured-state tolerance gate 通过前阻断 snapshot/step。`snapshot_v1()` 保持不发布 actuator force；`snapshot_v2()` 只在上述精确 routes 发布 required typed force，其他 RuntimeSession 对 required force 明确不可用。contact/native-interval 不由此支持 |
| `CameraCaptureIdentityV1`, `CameraRenderSource.capture_identity` | `task_env.render.camera` | 绑定 camera/source、ExecutionSpec v1、准确 manifest mapping、state boundary/clock 与 modalities 的静态 capture-request identity；不代表实际 capture 或 renderer pairing 已运行 |
| `CanonicalCameraObservation.capture_identity` | `task_env.observations.canonical_camera` | Dynamic camera 成功返回图像时附带现有 `CameraCaptureIdentityV1`；buffer、metadata step/time 与 identity boundary/clock/modalities 必须相符。该组合标识已返回的 capture 数据；identity value 单独仍不是运行证据 |
| `DynamicCameraRenderSourceV1`, `project_render_state_v1`, `create_dynamic_camera_session`, D03/D04 manifests and profiles | `task_env.render.camera` | D03 RGB、D04 RGB/Depth、受限 D04 Entity-instance-mask 是独立 versioned profiles；D05b 历史收据在 GeoPhys gitlink `4436787e…` × MuJoCo native OpenGL 上对单 Panda Position/Scene-v3 scalar-joint source 验证 default/override、双相机 materialization/sync/capture/close S1/S2。当前 `a53a8cfe…` pin 已另行完成真实 NVIDIA EGL pairing S1/S2 与资源关闭复验，见 [P99 运行收据](goal/Phase_II/C_Development_Record.md#public-candidate)；旧 `4436787e` 收据独立保留。segmentation requires RGB+Depth in the same capture and maps native geoms through canonical Frame→Entity bindings. `CanonicalEntityInstanceSegmentationV1` is H×W uint32 (0 background); `CanonicalEntityLabelMapV1` maps positive dense labels to canonical Entity IDs and binds source, SceneInstance, episode/reset, boundary, camera and capture identity. Native geometry IDs stay private. Other provider/backend pairs, free-joints, semantic classes, Environment policy observation/TransitionRecorder integration and general D05b qualification remain unsupported or unverified |
| `RecorderConfig`, `TransitionRecorder`, `TransitionRecordWrapper` | `task_env.recorders` | 既有录制 contract；selected examples 使用 selected env 自有录制入口 |
| `TransitionRecordWrapper.stop`, `load_structured_training_episode_h5` | `task_env.recorders` | v3 wrapper 仅接受显式声明 typed structured controls 的 Env；Stop 写入已有 Event/Outcome，训练读取返回原始 transition flags 与 final end/bootstrap 分离字段。v2 活跃记录 Stop/close、vector Stop、没有 structured action 的普通 TaskEnv v3 wrapper 明确拒绝 |

### Static Logical Assembly value (R01a)

```python
from task_env.artifacts import (
    AssetDefinition,
    EntityInstance,
    LogicalAssemblyEntityMemberV1,
    LogicalAssemblyScenePinV1,
    LogicalAssemblyV1,
    SceneDefinition,
    decode_logical_assembly,
)

asset = AssetDefinition("asset-definition-v1", "robot/panda", "v1", "procedural://example/panda")
entity = EntityInstance("entity-instance-v1", "arm", "robot/panda", "v1")
scene = SceneDefinition("scene-definition-v1", "example-scene", (asset,), (entity,))
assembly = LogicalAssemblyV1(
    "logical-assembly-v1",
    "robot-assembly",
    "r1",
    LogicalAssemblyScenePinV1(
        "logical-assembly-scene-pin-v1",
        scene.scene_id,
        scene.schema_version,
        scene.identity_hash,
    ),
    (LogicalAssemblyEntityMemberV1("entity_member", ("arm",), "arm", "robot/panda", "v1"),),
)
assert decode_logical_assembly(assembly.to_mapping()) == assembly
```

This example builds only a static value and round-trips its strict codec. It does not construct an environment, resolve a member, load a source, or create physical attachment.

### Bounded Logical Assembly resolution (R01b)

```python
from task_env.artifacts import (
    AssetDefinition,
    EntityInstance,
    LogicalAssemblyEntityMemberV1,
    LogicalAssemblyNestedMemberV1,
    LogicalAssemblyScenePinV1,
    LogicalAssemblyV1,
    SceneDefinition,
    resolve_logical_assembly,
)

asset = AssetDefinition("asset-definition-v1", "robot/panda", "v1", "procedural://example/panda")
entity = EntityInstance("entity-instance-v1", "arm", "robot/panda", "v1")
scene = SceneDefinition("scene-definition-v1", "example-scene", (asset,), (entity,))
pin = LogicalAssemblyScenePinV1(
    "logical-assembly-scene-pin-v1", scene.scene_id, scene.schema_version, scene.identity_hash
)
child = LogicalAssemblyV1(
    "logical-assembly-v1", "arm-leaf", "r1", pin,
    (LogicalAssemblyEntityMemberV1("entity_member", ("arm",), "arm", "robot/panda", "v1"),),
)
root = LogicalAssemblyV1(
    "logical-assembly-v1", "robot-root", "r1", pin,
    (LogicalAssemblyNestedMemberV1(
        "nested_assembly", ("robot",), child.assembly_id, child.revision,
        child.logical_content_sha256,
    ),),
)
resolved = resolve_logical_assembly(root, scene, {(child.assembly_id, child.revision): child})
assert resolved.leaves[0].full_path == ("robot", "arm")
```

The resolver checks exact Scene pins, child IDs/revisions/content hashes, Entity/assets and entity-qualified typed
Frame/Joint/Actuator/ControlGroup references. It rejects containment cycles, repeated owning Entities, repeated typed
targets and expanded path collisions. Reference-only leaves do not create another Entity owner or writer. Scene v1
permits Entity-only leaves; Frame/Joint require v2/v3 and Actuator/ControlGroup require v3. Result leaves preserve
their source Assembly and local path as well as the canonical expanded path; returned tuples and referenced values
are immutable. The limits are fixed at 32 Assembly levels (root depth 1) and 1024 expanded leaves. Resolution is
stateless and provider-free: it does not request runtime Frame poses, project a Task Source, assign native indices,
construct a RuntimeSession, or prove physical attachment.

### Logical Assembly source declaration projection (R01c)

<!-- R01C_EXECUTABLE_EXAMPLE_BEGIN -->
```python
from task_env.artifacts import (
    AssetDefinition, EntityInstance, LogicalAssemblyEntityMemberV1,
    LogicalAssemblyScenePinV1, LogicalAssemblyV1, SceneDefinition,
)
from task_env.assembly import project_logical_assembly_source

asset = AssetDefinition("asset-definition-v1", "robot/panda", "v1", "procedural://example/panda")
entity = EntityInstance("entity-instance-v1", "arm", "robot/panda", "v1")
scene = SceneDefinition("scene-definition-v1", "example-scene", (asset,), (entity,))
pin = LogicalAssemblyScenePinV1(
    "logical-assembly-scene-pin-v1", scene.scene_id, scene.schema_version, scene.identity_hash
)
assembly = LogicalAssemblyV1(
    "logical-assembly-v1", "robot-assembly", "r1", pin,
    (LogicalAssemblyEntityMemberV1("entity_member", ("arm",), "arm", "robot/panda", "v1"),),
)
projection = project_logical_assembly_source(assembly, scene, {})
assert projection.entities[0].asset.source_content_sha256 is None
assert projection.identity_sha256  # independent projection identity; not embedded in its payload
```
<!-- R01C_EXECUTABLE_EXAMPLE_END -->

`project_logical_assembly_source(root, scene, child_assemblies, source_receipts=None)` first calls the R01b resolver on
the current inputs, then joins each leaf to one existing Scene Entity and its exact Asset declaration. It preserves
distinct Entity instances even when they share an Asset, and keeps reference-only leaves separate from owning members.
Frame, Joint and Actuator leaves retain their exact typed definitions; a ControlGroup leaf includes that Group and the
Actuator definitions selected by its declared references. Runtime Frames remain identity-only anchors. Result tuples
and contract values are immutable; `to_mapping()` returns a detached JSON snapshot, and `identity_sha256` hashes the
versioned snapshot without embedding that digest. Asset declaration identity, optional source-content hash and any
historical receipt digest remain distinct identities. A receipt match is labelled as historical declaration
provenance, not as a new byte/closure check. This source projection does not load source bytes, lower or attach assets,
assign native names/indices, construct a Runtime, or admit Core materialization/physical attachment.

### Position leaf contract values (R02a)

R02a adds versioned, provider-free values in the existing advanced canonical Controller owner. `ArmPositionActionV1`
is exactly seven ordered Panda Joint positions in radians, with the declared Panda joint limits held by its
`LeafProfileBindingV1`. `HandPositionActionV1` is one aggregate `opening_m` in `[0, 0.08]`; its explicit legacy
adapter uses `opening_m = 0.04 * (u + 1)` for `u ∈ [-1, 1]`. The Hand binding keeps the two finger Joints in
canonical order, their `[0, 0.04] m` limits, `opening_m = finger_joint1_q_m + finger_joint2_q_m`, the fixed
0.5/0.5 tendon, the finger equality, and one `actuator8` resource with the declared `ctrl = 3187.5 * opening_m`
mapping and `[0, 255]` native ctrlrange. These values describe the candidate source contract; they do not add a
runtime adapter or prove that a Core Provider consumed the mapping.

Both Position targets bind exact ordered resources, profile/action schema, writer, binding/source/Scene hashes,
typed source boundary and evaluation clock. `LeafApplicationAckV1` cross-checks the exact Target hash, source
identity, resources and explicit application boundary/clock. It is a receipt-shaped static value, not evidence
that native control was applied or that the state reached its target. Required State uses existing typed
`StateRequirements` for each Joint position/velocity and an Entity-qualified TCP parent Frame; Position leaves do
not require or synthesize force. All v1 leaf state fields remain mandatory and exactly match the bound profile
resources and TCP; optional downgrades and extra cross-leaf requirements are rejected. `HandForceAwareDependencyV1` has its own action/profile identity and force-state
requirements, but remains `NOT_ADMITTED`; source/transmission sign and phase are explicitly unaudited. Its absence
does not block either Position contract.

The strict decoders reject unknown fields/versions and cross-kind payloads. `validate_leaf_binding()` checks a
Scene-v3 static binding and, when given a `ResolvedLogicalAssemblyV1`, verifies the exact member selector. A whole
Panda may use two reference-only ControlGroup selectors; those views do not own Entities or create writers. A
two-Entity static fixture uses the existing Entity owners. R02a alone does not project Task Source, assign native
indices, build a plan, call `make_env()`, or admit an executable capability. The R02a Force-aware catalog remains
`CONTRACT_ONLY / NOT_ADMITTED / NOT_RUN`.

### Effective Position leaf plan and synthetic dispatch (R02b)

R02b adds strict versioned `LeafProfileSectionV1`, `LeafControlPresetV1` and complete-section
`LeafProfileOverrideV1` values. `compile_effective_leaf_plan()` re-resolves the current root/Scene/children and
reprojects current source declarations before checking the R02a bindings, source identity, provider/build/timebase,
unique writer/resource coverage and exact preset paths. Its immutable `EffectiveLeafPlanV1` retains the base preset,
ordered overrides, effective config values/identities, leaf bindings and resource writers. Status is computed from
which effective leaf sections differ from base; a no-op override does not change status or effective plan identity.

`prepare_leaf_command()` is the shared stateless Arm/Hand Position adapter. Arm reuses the legacy absolute-joint
limit/correction calculation; Hand reuses the existing gripper opening servo and affine command conversion. A Hand
command keeps requested opening in metres, servo opening in metres and native ctrl as separate values. Explicit
native mapping receipt values bind canonical refs to names/IDs/addresses/slots and source/Provider/config identity;
they must validate exact resource coverage, Arm transmission to the mapped native Joint name, Hand logical-tendon to
native-tendon name, equality and alias-free slots. The receipt must cover all `nu` native actuator IDs and ctrl slots,
including rejection of undeclared extra actuators. Writer IDs use the same Entity-qualified semantic names as R02a. R02b S1 uses only `synthetic_fixture` provenance.

`dispatch_leaf_control_interval()` validates the complete action/state/request and every writer before preparing
commands or consuming the boundary; it then applies each exact typed patch, validates the returned apply Ack,
requests one outer interval, and validates the next typed publication. A failure after boundary consumption latches
the existing `ExecutionFaultV1` with leaf attempted/applied/unknown/acknowledged progress, preserved prepared Targets/command patches,
and every typed apply result returned before the failure. This provider-neutral
path has provider-free S1 evidence only: it is not wired to any real RuntimeSession Provider, selected Env or H5
Recorder and does not establish native leaf admission. R02c remains the required real independent leaf/runtime/
recording gate; S2/S3/S4 and Qualification remain unrun.

```python
from task_env.controllers.canonical import (
    HAND_POSITION_ACTION_SCHEMA,
    HandPositionActionV1,
    leaf_profile_catalog_v1,
)

action = HandPositionActionV1(HAND_POSITION_ACTION_SCHEMA, opening_m=0.038)
assert action.opening_m == 0.038
assert all(entry.admission_status == "NOT_ADMITTED" for entry in leaf_profile_catalog_v1())
```

This example constructs static contract values only; it does not instantiate a leaf Controller or execute a Provider.

### R02c leaf Position integration status (2026-10-27)

The task-owned `build_leaf_position_candidate()` and advanced
`SelectedReferenceEnv.from_leaf_position_candidate()` path compose the existing A05 source, `ReferenceTaskBinding`,
RuntimeSession, lifecycle and Generic H5 v3 owners. One full-Panda Entity exposes two existing ControlGroup references
to separate Arm-only and Hand-only Position writers; this is not two complete Panda Controllers and does not represent
the independent Arm+Hand Attachment route. `load_leaf_control_records_h5()` adds a strict leaf semantic reader over the
existing Generic H5 v3 envelope. It does not introduce a new recorder format or public `make_env()` UID.

Provider-free targeted S1 passed 53 tests. The one bounded MuJoCo 3.8.1 CPU probe process exited during static contract
validation with `KeyError: 'provider_static_files'`, before importing MuJoCo or compiling/materializing/resetting/stepping.
The script was corrected in a later unexecuted contract revision; the fixed process budget did not permit another start.
Therefore no R02c S2/S3, native H5 readback, or Provider admission is established. Keep this path at
`IMPLEMENTED_S1_PASS_PENDING_SOL_REVIEW`; do not describe it as an executable supported candidate or Qualification.
The attempt report and raw logs are local ignored Evidence under
`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02c_001/`.

## C02b Position Profile candidate status (2026-10-22)

The C02b-E first-round candidate adds an internal, opt-in
`PandaPositionServoProfileV1` (`task_env.controllers.canonical.position_profile`) path. It reuses
`CanonicalPandaController`, `ControlBindingPlanV1`, `RuntimeSession` and the existing selected lifecycle;
`materialize_control(..., controller_binding_plan=plan, controller_profile=profile)` admits its exact
force-free typed Joint/hand requirements on GeoPhys/MuJoCo CPU only. Its versioned target binds the actual
Profile identity, source closure, plan and state boundary. The current A05 candidate uses the explicit
`panda-main/hand-origin-tcp-v1` transform and 100 Hz / five 2 ms steps. This is not a default task-factory
selection, registered production capability or qualification. The 2026-10-22 bounded dual candidate composes two
instances of the same existing profile algorithm for exact Entity IDs `panda-main` and `panda-secondary`, with
Entity-qualified Joint/hand state, disjoint arm/gripper resources (16 actuators total), one complete
`ControlBindingPlanV1`, and one shared selected RuntimeSession/world. All groups are preflighted before either
Controller computes; target and applied acknowledgement retain writer, Entity, resource, episode, and source-boundary
identity. This exact diagnostic admission is not general multi-writer arbitration, arbitrary N-Entity support, Assembly,
or a registered capability. The explicit `SelectedReferenceEnv.from_position_candidate()` constructor uses an existing
`ReferenceTaskBinding`, and its bounded selected-lifecycle route writes Generic H5 v3. GeoPhys CPU and MuJoCo CPU S2
plus H5 v3 request/target/ack and Entity-specific state/boundary disk readback passed for both single- and dual-Panda
candidates. The dual S1 rejects wrong Entity, missing Group, overlapping writers/resources, wrong binding identity,
stale target, and materialization-boundary mismatch before compute/apply/step.
The independent `panda-main/production-r1` contract remains required-force and continues to reject before
Runtime materialization when `actuator_force_query` is unavailable. See the
[C02b-E S1 acceptance](goal/Phase_II/C_Development_Record.md#c02b),
[S2/H5 acceptance](goal/Phase_II/C_Development_Record.md#c02b), and
[Dual Entity acceptance](goal/Phase_II/C_Development_Record.md#c02b).

**C02b-R1 reset freshness and typed admission (2026-10-22):** the existing PickCube
legacy route has a bounded GeoPhys reset-forward freshness receipt. Separately,
a new Scene-v3 candidate has a passing `CanonicalStateViewV2` raw-force
publication and exact plan-bound `actuator_force_query` admission on GeoPhys CPU
revision `a53a8cfe...`, followed by a fresh real 100 Hz R1 interval on that exact
Provider pin. Raw signed force is preserved, and existing `control_feedback()`
remains the only canonical closing-force projection. This claim does not transfer
to the old selected PickCube Artifact/source, MuJoCo typed force, other
transmissions, or generic Provider manifests. It was later exercised through the single-Panda Scene-v3 structured R1
sequence on the same exact GeoPhys CPU and MuJoCo 3.8.1 CPU/native-build intersections, with same-file Generic H5 v3
readback. Both final runs passed the predeclared force-mode, arm-pose, dispatch and recording checks. The current C02b
disposition is that declared-intersection bounded engineering exits are satisfied; unadmitted extensions and Qualification
are separate. P00/P99's minimum dual-Entity requirement is covered by Position-only S2;
dual-Entity R1 has no approved basis as a required gate. See the [freshness receipt](goal/Phase_II/C_Development_Record.md#c02b),
[typed-force receipt](goal/Phase_II/C_Development_Record.md#c02b), and
[structured R1 S2/S3 receipt](goal/Phase_II/C_Development_Record.md#c02b).

**Scene-v3 candidate construction boundary:** the single Position candidate now has the explicit public UID
`panda-position-servo-candidate-v1`. `make_env()` reuses the task-owned construction in
`task_env/tasks/position_candidate/`, existing `ReferenceTaskBinding`, `SelectedReferenceEnv`, RuntimeSession,
public reset/step observation and Generic H5 v3 Recorder. The same public environment passed 64 real continuous
intervals and same-file disk readback. Structured R1 and dual-Entity candidates remain diagnostic routes.

Public candidate config admits `provider` (only `geophys`, default), `backend` (only `cpu`, default), `horizon`
(integer 1–6000, default 6000), and optional `source_workspace` (fresh/empty source snapshot directory).
Without a path it allocates a fresh directory under ignored `workspace/tasks/phase-ii-c02b-position-servo/candidate-sources/`.
It rejects render mode, extra kwargs, legacy overlays, alternate provider/backend/profile and nonmatching reset seed
before runtime materialization. Omitted reset seed resolves to the bound seed 31; this is not a randomizable task.
Use `StructuredActionRequestV1` with exact Scene/plan IDs and both `panda-main` arm/gripper groups; observation is
returned from `reset()`/`step()` with boundary/time info. `start_recording(path)` at reset, step, then
`finish_recording(reason)` uses the existing Generic H5 v3 owner; read the same path with
`load_structured_control_records_h5()` / `load_structured_training_actions_h5()` from `task_env.recorders`.
Always close in `finally`. No Expert/task-success or freeze approval is implied. See
[P99 readiness](goal/Phase_II/05_Architecture_Review_and_Execution_Order.md#p99) and the
[implementation/run receipt](goal/Phase_II/C_Development_Record.md#public-candidate).

### R04a opt-in camera observation on the Position candidate (2026-10-26)

The same UID now accepts an optional `camera_observation` mapping decoded as
`CameraObservationConfigV1`. It is limited to the single Panda Position candidate, GeoPhys CPU physics,
the existing D04 profile and two explicitly authored mounts in canonical fixed-then-hand order. Each
mount requires its parent Frame and `T_parent_from_mount`; the public config does not guess or replace
asset mount transforms, and the camera opt-in requires horizon at most 16. Production geometry is 321×241 with RGB HWC float32 `[0,1]`, optical-Z depth
H×W float32 in metres (`0` invalid), and canonical Entity mask H×W uint32 (`0` background). Validation
and capacity checks happen before source workspace creation. Omitting the mapping retains the state-only
default and does not initialize a renderer during import/construction.

After reset/step has published the typed state boundary, the existing SelectedReferenceEnv lazily owns
the two existing CameraSessions and publishes their arrays under `rgb`, `depth`, and `entity_mask`; repeated
reads of one boundary reuse the cache. `info["camera_observation_v1"]` carries the capture/calibration/
label-map identity. Camera close/failure follows the existing Env lifecycle and C03a fault latch. When
recording is enabled, Generic H5 v3 keeps its numeric tree and adds versioned camera metadata sidecars;
read with `load_camera_observations_h5()` alongside the existing structured-control reader. RGB keeps
the existing CHW uint8 quantization rule; depth/mask retain float32/uint32. This R04a S1 is provider-free
and synthetic: native MuJoCo/OpenGL/EGL pairing, real public reset/step capture, and same-file R04c
camera readback remain NOT_RUN. It is not camera qualification or P99 gate completion.

Sol review (2026-10-26): R04a is **CHANGES_REQUESTED**. The existing 23 S1 cases pass, but reviewer counterexamples show missing binding to the requested mount/source and missing camera-sidecar checks against the stored state boundary and episode outcome. These checks require targeted repair before R04a acceptance; native Camera/Env/H5 S2/S3 remain NOT_RUN.

For this explicit selected candidate, `env.position_plan` after reset is the read-only typed action contract
used by the existing dispatch owner. Do not mutate it. Gripper input is normalized in [-1,1] (+1 open / -1 close);
arm pose uses the world hand-origin TCP, metres and wxyz quaternion. A minimal recording example:

```python
from pathlib import Path
from task_env import make_env
from task_env.controllers.canonical.contracts import (
    ControlGroupActionV1, StructuredActionRequestV1,
)
from task_env.recorders import load_structured_control_records_h5

# Use a fresh output directory for every run.
path = Path('workspace/maintenance/p99_candidate_example/episode.h5')
if path.parent.exists():
    raise ValueError('example output directory must be fresh')
path.parent.mkdir(parents=True)
env = make_env('panda-position-servo-candidate-v1', config={'horizon': 4})
try:
    obs, info = env.reset(seed=31)
    plan = env.position_plan  # selected candidate's read-only, typed action contract
    schema_id = plan.controller_bindings[0].action_schema.schema_id
    # World hand-origin pose: x,y,z,qw,qx,qy,qz. Gripper: +1 open, -1 close.
    hand = tuple(float(x) for x in obs['state']['hand_pose'])
    request = StructuredActionRequestV1(
        'structured-action-request-v1', plan.scene_identity_hash, plan.identity_hash,
        (
            ControlGroupActionV1('control-group-action-v1', 'panda-main', 'arm', schema_id, hand),
            ControlGroupActionV1('control-group-action-v1', 'panda-main', 'gripper', schema_id, (1.0,)),
        ),
    )
    env.start_recording(path)
    for _ in range(4):
        obs, reward, terminated, truncated, info = env.step(request)
    result = env.finish_recording('horizon')
    loaded = load_structured_control_records_h5(result['path'])
    assert loaded['transition_count'] == 4 and loaded['observation_count'] == 5
finally:
    env.close()
```

`finish_recording()` must agree with the latched outcome: after horizon use `"horizon"` or `"horizon_reached"`.
For an early intentional end, use `env.stop("external_stop")` and `env.finish_recording("external_stop")`.
Mismatching reasons fail. The structured reader returns controls/events/outcome; observation arrays remain in the
same H5 under `obs/state/{joint_position,hand_pose,boundary_identity_sha256}`.


**C02c bounded Position instance switch (2026-10-22):** the explicit
`SelectedReferenceEnv.from_position_candidate()` route also exposes
`switch_position_controller(candidate)` for a single `panda-main` Position candidate. It requires an active Generic H5 v3
recording and the last complete, live evaluation boundary. The fresh replacement Profile must have a distinct identity and
ActionConfig while retaining the exact action schema, Frame/TCP, unit, timebase, required state, source closure and actuator
ownership. Preparation is side-effect-free; the final RuntimeSession commit initializes its cursor at the live control step
without calling `reset()` (which remains step-0-only). The current Position algorithm is stateless; the Profile carries only
plan/episode/reset/next-step/activation-boundary cursor memory. The switch records a BoundaryEventV1 at T and does not compute, apply,
step physics or append a transition. The first ordinary T→T+1 step carries the new identity target and matching applied ack;
old-identity targets are refused. A second switch is refused until the first replacement has one complete target/ack transition;
that transition carries the switch ID. Ending the episode first records effective/not-applied in its end event. A postcommit
event-write failure trips the existing C03a latch and preserves a failure receipt. This is episode-scoped and limited to the
verified single-Panda Position GeoPhys CPU/MuJoCo CPU intersection; reset
reconstructs the candidate builder's original profile. Dual-Entity switching, production-R1/force-aware switching,
NutAssembly, Assembly, Camera integration, other providers and generic arbitration remain unsupported. This closes only the declared
Position-switch slice; general C02c switching remains deferred. C02b's declared engineering exits are recorded separately;
Phase II scoped engineering acceptance is recorded by the maintainer; release and Formal Qualification remain separate gates. See the [C02c bounded acceptance receipt](goal/Phase_II/C_Development_Record.md#c02c).

D05a 的执行选择只新增在 advanced Artifact/Camera owners 下。`RuntimeSession.materialize()` 和当前
`create_camera_session()` 仍走旧 `ExecutionSpec` 与实际同名 physics/render admission；D05a 没有改变
`admit_render`、Provider manifest capability claims 或 native construction，也不允许 UI `render_mode` 冒充
Camera Sensor selection。现有 provider-capability-v0 mapping 原样保留；其 `identity_hash` 只绑定精确 mapping。
D03/D04 在同一 Camera owner 复用 `create_dynamic_camera_session(camera, execution, source=..., initial_state=..., manifest=None)`；
选择 D03 profile 时只准 RGB，D04 profile `D04_DYNAMIC_PROFILE` 配合 `dynamic_rgbd_render_manifest()` 准入同步 RGB/Depth；
`D04_ENTITY_SEGMENTATION_PROFILE` 配合 `dynamic_entity_instance_segmentation_manifest()` 另行准入同 capture RGB/Depth/Entity mask。
它们只 admission GeoPhys CPU Scene-v3 scalar-joint Position source 与 MuJoCo `native-opengl`，使用现有 `RuntimeSource`
lowering、`CanonicalStateViewV1`、CameraGeometry/metadata 与 Renderer session；挂载相机 parent Frame 必须能唯一解析。
Depth 为光学 +Z 米制 float32，invalid/clipped/background 为 0；Entity mask 为 `canonical-entity-instance-segmentation-v1` 的
H×W uint32、背景 0，label map 使用 `canonical-entity-label-map-v1`，正标签稠密、按 canonical Entity ID 确定性排序，并与同 capture
identity/source/boundary/SceneInstance 绑定。Native geom ID 不得成为公开标签；缺失、歧义或非 geom 映射均拒绝。capture identity
声明 RGB、Depth、Entity-instance-segmentation 三个共采模态。capture/sync 不调用 Controller 或推进物理。该 route 不让旧
`create_camera_session()` 接受 ExecutionSpec v1，也不构成语义分割、free-joint、完整 D04/D05b pairings 或 Qualification。MuJoCo 未公开 Renderer context handle；current GL device query 仅为
capture 后的诊断观察，不参与设备准入或 pinning。

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
B02 初始路线的 `resolve_role_binding()` 使用匹配的 TaskArtifact v0；D01b 增加 TaskArtifact v1 路径，要求 Artifact
精确引用给定 Scene、TaskSource snapshot identity 匹配，并由对应的 RuntimeSource 映射所有必需 Frame/Joint。
两条路线都只接受显式 ID 候选，按排序候选和 per-role RNG domain
生成 immutable binding；v0 路线核对全部 Artifact Entity 与声明的 Frame/Joint 子拓扑，v1 路线核对其显式 legacy Frame/Joint
bindings 和 Scene/TaskSource identity。Scene 可含 v0 未表达的额外结构。
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
