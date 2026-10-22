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
通用 scalar lifecycle 另提供 `env.stop(reason="external_stop") -> EpisodeEndV1`：Stop 只在最后一个完整公开边界结束 episode，不调用 Controller、不施控、不推进 Runtime，也不伪造 Gym transition。默认 external Stop 是 `truncated=True, bootstrap_allowed=True`；horizon 是可 bootstrap 的截断；task terminal 是 `terminated=True, bootstrap_allowed=False`；execution fault 是不可 bootstrap 的 fault outcome。现有 step flags 保持原值；同时发生 task terminal 与 horizon 时，EpisodeOutcome 以 task terminal 为最终结果，但不回写已返回的五元组。
对成功 reset 后尚未结束的 episode 调用 reset，会先在旧边界生成 Stop，并在新 reset info 的 `previous_episode_end_v1` 返回旧结果；close 也会在 teardown 前结束活动 lifecycle。reset 前 Stop、Stop/step 在 close 后均拒绝；同一 episode 重复 Stop 返回缓存的同一 `EpisodeEndV1`。execution fault 后 Stop 记录 fault 且停在最后完整边界，不把已推进但未完成公开 transition 的间隔补成 transition。
`SelectedReferenceEnv` 仅对显式 PositionServoV1 candidate 实现此 Stop；旧 selected production-R1 路径的 Stop 明确拒绝，旧 Controller identity、反馈要求与执行行为保持原样。
通用 `BaseTaskEnv` 组合 task definition、reset sampler、runtime、action、observation 和 rendering。
`TaskEvaluation` 提供 reward、success、failure、metrics、reward_terms；reward 与
`info["is_success"]` 不能替代 Judge。通用 `ignore_done=False` 时 success/failure 可终止 episode，
horizon 产生 truncation；selected expert 的 stop/completion policy 必须单独读取。
Selected reference 同一 episode 不可混用 expert 和 external action；NutAssembly external action 明确拒绝。

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
| `CanonicalStateViewV2`, `CanonicalStatePublicationV2`, `TypedActuatorForceStateValue` | `task_env.artifacts` | Additive D02 typed raw-force publication: exact decoder version, signed value, explicit unit, source closure/materialization, Provider sample revisions/phase/native clock, episode/reset and evaluation-boundary identity. `snapshot_v2()` composes existing Joint/Frame projection with typed force; v0/v1 mappings and hashes remain unchanged. Required missing/invalid/wrong-unit/stale-identity/unsupported-phase values reject. Current publication is bounded to the exact GeoPhys CPU Panda R1 candidate receipt |
| `ProductionCanonicalPandaController.source_artifact_hash`, `.source_xml_sha256`, `.tcp_profile_identity`, `.source_kinematics_identity`, `.expected_control_step` | `task_env.controllers.canonical.production` | Read-only actual-instance identity and evaluation-cursor view used by source-bound admission; adding these properties does not alter legacy R1 identity or compute/reset behavior |
| `ActuatorForceMeasurementV1`, `RuntimeSnapshot.actuator_force_measurement` | `task_env.environment` | Core Provider-adapter value contract for signed raw actuator-force provenance: source generation, sample/config/state revisions, native sample index/phase, validity, and selected-session episode/reset/evaluation boundary. Used by the GeoPhys legacy force-aware adapter and wrapped by typed state v2 only for the admitted candidate; it does not grant generic actuator units or shared Provider capability |
| `AssetDefinition`, `EntityInstance`, `SceneDefinition` | `task_env.artifacts` | Phase II A01 identity/provenance、A02 frames/articulations、A03 `scene-definition-v3` static composition；strict codec only，不构造 Provider/runtime |
| `FrameReference`, `FrameDefinition`, `ArticulationDefinition`, `JointDefinition` | `task_env.artifacts` | entity-qualified frame、固定变换、runtime anchors 与多 articulation topology；不执行 FK 或 provider lowering |
| `RobotInstance`, `ActuatorResourceDefinition`, `ActuatorReference`, `ControlGroup` | `task_env.artifacts` | Entity-qualified 的静态 Robot/actuator/group identity；`SceneDefinition.resolve_*` 仅解析静态声明，不定义 Controller、动作维数、native binding 或多 Robot 执行 |
| `RuntimeSession`, `RuntimeSession.snapshot_v1`, `RuntimeSession.snapshot_v2`, `RuntimeSession.reset_plan`, `materialize`, `provider_manifest` | `task_env.runtime.sessions` | advanced bounded session route；需合法 artifact/source/profile。直接 `materialize()` 的 v1 route 仍只支持精确 Scene-v3、一个 RobotInstance、scalar reset/state、bounded source root 的 GeoPhys/MuJoCo CPU 路线；现有 `materialize_control()` owner 另有精确 Position candidate 和双 Position Entity admission，以及单个 source/Controller/plan-bound GeoPhys CPU R1 typed-force admission。后者严格绑定新 Artifact、Scene/source closure、实际 Controller/TCP、GeoPhys revision `eb870f6f...` 与 `actuator8`；不扩展 generic provider manifests 或其他 backend/transmission。`reset_plan()` 校验 Artifact/TaskSource/Scene identity，原样执行 ResetSample v0，并在 measured-state tolerance gate 通过前阻断 snapshot/step。`snapshot_v1()` 保持不发布 actuator force；`snapshot_v2()` 目前只在上述精确 route 发布 required typed force，其他 RuntimeSession 对 required force 明确不可用。contact/native-interval 不由此支持 |
| `CameraCaptureIdentityV1`, `CameraRenderSource.capture_identity` | `task_env.render.camera` | 绑定 camera/source、ExecutionSpec v1、准确 manifest mapping、state boundary/clock 与 modalities 的静态 capture-request identity；不代表实际 capture 或 renderer pairing 已运行 |
| `CanonicalCameraObservation.capture_identity` | `task_env.observations.canonical_camera` | Dynamic camera 成功返回图像时附带现有 `CameraCaptureIdentityV1`；buffer、metadata step/time 与 identity boundary/clock/modalities 必须相符。该组合标识已返回的 capture 数据；identity value 单独仍不是运行证据 |
| `DynamicCameraRenderSourceV1`, `project_render_state_v1`, `create_dynamic_camera_session`, D03/D04 manifests and profiles | `task_env.render.camera` | D03 RGB、D04 RGB/Depth、受限 D04 Entity-instance-mask 是独立 versioned profiles；D05b 已对单 Panda Position/Scene-v3 scalar-joint source → GeoPhys CPU × MuJoCo native OpenGL 验证 default/override、双相机 materialization/sync/capture/close S1/S2。segmentation requires RGB+Depth in the same capture and maps native geoms through canonical Frame→Entity bindings. `CanonicalEntityInstanceSegmentationV1` is H×W uint32 (0 background); `CanonicalEntityLabelMapV1` maps positive dense labels to canonical Entity IDs and binds source, SceneInstance, episode/reset, boundary, camera and capture identity. Native geometry IDs stay private. This exact pairing is TESTED_BOUNDED only; other provider/backend pairs, free-joints, semantic classes, Environment policy observation/TransitionRecorder integration and general D05b qualification are unsupported or unverified |
| `RecorderConfig`, `TransitionRecorder`, `TransitionRecordWrapper` | `task_env.recorders` | 既有录制 contract；selected examples 使用 selected env 自有录制入口 |
| `TransitionRecordWrapper.stop`, `load_structured_training_episode_h5` | `task_env.recorders` | v3 wrapper 仅接受显式声明 typed structured controls 的 Env；Stop 写入已有 Event/Outcome，训练读取返回原始 transition flags 与 final end/bootstrap 分离字段。v2 活跃记录 Stop/close、vector Stop、没有 structured action 的普通 TaskEnv v3 wrapper 明确拒绝 |

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
[C02b-E S1 acceptance](goal/Phase_II/C02b_E_Position_Profile_S1_Acceptance.md),
[S2/H5 acceptance](goal/Phase_II/C02b_E_Position_Profile_S2_Acceptance.md), and
[Dual Entity acceptance](goal/Phase_II/C02b_Dual_Entity_Position_Acceptance.md).

**C02b-R1 reset freshness and typed admission (2026-10-22):** the existing PickCube
legacy route has a bounded GeoPhys reset-forward freshness receipt. Separately,
a new Scene-v3 candidate has a passing `CanonicalStateViewV2` raw-force
publication and exact plan-bound `actuator_force_query` admission on GeoPhys CPU
revision `eb870f6f...`, followed by one real 100 Hz R1 interval. Raw signed force
is preserved, and existing `control_feedback()` remains the only canonical
closing-force projection. This claim does not transfer to the old selected
PickCube Artifact/source, MuJoCo typed force, other transmissions, or generic
Provider manifests. C02b remains blocked on the other required intersections
and complete execution; C05b has not started. See the [freshness receipt](goal/Phase_II/C02b_R1_Reset_Force_Freshness_Acceptance.md)
and [typed-force receipt](goal/Phase_II/C02b_R1_Typed_Raw_Force_Admission_Acceptance.md).

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
NutAssembly, Assembly, Camera integration, other providers and generic arbitration remain unsupported. This does not complete
C02b, C02c or Phase II. See the [C02c bounded acceptance receipt](goal/Phase_II/03_Phase_C_Execution_Lifecycle.md#c02c-bounded-single-panda-position-receipt2026-10-22).

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
