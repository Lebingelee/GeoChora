# Geochora Phase I Contract 与 Provider 边界

> 状态：active Phase-I contract specification，v0.2
> 日期：2026-10-04
> 范围：定义 Phase I 多仿真器实施蓝图所需的最小 provider-neutral contract。
> 相关文档：05-phase-1-multi-simulator-blueprint.md
> 权威关系：作为 Phase-I 实施计划采纳，从属于 [系统架构基准](../../global/00-system-architecture-anchor.md)、[仓库所有权](../../global/01-repository-ownership-and-boundaries.md) 与 canonical TaskEnv contract。active 表示文档用于指导实施，不表示 capability 已实现、测试通过、qualified 或任何子阶段已获准。

## 1. 设计原则

Phase I 不得创建 UniversalSolver，也不要求所有 simulator internal 共享同一 storage ABI。

稳定边界是：

~~~text
Task Artifact
   -> ExecutionSpec
   -> capability admission
   -> ResetSample
   -> provider materialization
   -> CanonicalStateView
   -> Geochora controller / semantics
   -> CanonicalTrajectory
~~~

Provider-specific storage、solver object、scene handle、cache 与 kernel 必须留在 provider adapter 后方。

## 2. Task Artifact v0

Phase-I Task Artifact 冻结的是任务是什么，而不是由哪个 provider 运行。

Artifact 包含三个概念部分及跨部分 contract。

### 2.1 WorldDefinition

声明 provider-neutral world content：

- scene/environment entity；
- passive/static asset；
- movable object；
- controllable embodiment；
- semantic entity/frame name；
- geometry/collision intent；
- mass/inertia 与具有物理意义的 parameter；
- joint/actuator declaration；
- observation requirement；
- public action/controller selection；
- randomization dimension 与 allowed envelope。

这一层的 task code 不得导入或调用 GeoPhys、MuJoCo、SAPIEN、Genesis API。

推荐 task-local 组织：

~~~text
artifacts/ver_xxx/
├── manifest.yaml
├── world.py
├── initialization.py
├── semantics.py
├── solution.py
├── local_assets/
├── validation/
└── judge_decision.yaml
~~~

使用 asset.py / task.py 的现有 artifact 可以逐步迁移。概念所有权是规范要求，具体文件名可以演进。

### 2.2 InitializationContract

声明：

- canonical initial-state requirement；
- randomizable quantity；
- hard bound；
- nominal training distribution；
- feasibility distribution；
- frozen evaluation distribution；
- reset validity predicate；
- 可选显式 settle policy；
- 实现 reset 所需的 provider capability。

InitializationContract 声明 distribution，不要求 simulator 采样 task randomness。

### 2.3 SemanticDefinition

只消费 canonical state/history 与 semantic reference。

可以产生：

~~~text
step metric
predicate
event
task reward
success
failure
termination/truncation input
trajectory-level metric
trajectory quality
safety/collision semantics
~~~

禁止输入 provider-native body ID、scene handle、contact array 或 solver storage。

### 2.4 Timebase

Phase I 使用一个显式 control-boundary timeline。

最小 field：

~~~yaml
timebase:
  physics_dt: 0.002
  control_substeps: 10
  control_dt: 0.020
  action_hold: zero_order_hold
  observation_sampling: post_control_step
  semantic_sampling: post_control_step
~~~

除非未来 contract 显式引入其他 scheduler，否则 control_dt 必须等于 physics_dt * control_substeps。

Phase I 不要求 asynchronous multi-rate sensor。

### 2.5 RequiredCapabilitySet

Task Artifact 推导或声明最小 capability set，例如：

~~~text
rigid_body
free_body
articulated_robot
joint_position_actuation
body_pose_query
frame_pose_query
rgb_camera
depth_camera
contact_detection
contact_impulse
~~~

Admission 规则：

~~~text
RequiredCapabilitySet ⊆ ProviderCapabilityManifest
~~~

否则必须在 rollout 前让 materialization 失败。

## 3. ExecutionSpec

Provider 选择不属于 Task Artifact identity。

示例：

~~~yaml
execution:
  physics_provider: mujoco
  physics_profile: default_cpu
  render_provider: mujoco_native
  backend: cpu
  provider_seed: 1007
  determinism_mode: strict
~~~

另一个 execution 可以引用同一 Task Artifact：

~~~yaml
execution:
  physics_provider: geophys
  physics_profile: rigid_manipulation_v1
  render_provider: geophys_raytracer
  backend: cuda
  provider_seed: 1007
  determinism_mode: strict
~~~

即使 Phase I 使用 native pairing，physics 与 render provider 仍是不同维度。

## 4. ProviderCapabilityManifest

每个 provider 在 task materialization 前都必须暴露 machine-readable capability record。

最小 identity：

~~~text
provider_name
provider_version
adapter_version
backend
physics_profile
render_profile（适用时）
determinism_mode
supported capabilities
known unsupported capabilities
qualification ID/Evidence reference
~~~

Capability claim 必须区分：

~~~text
implemented
tested
qualified
planned
unsupported
unknown
~~~

这些词使用 [仓库 Capability 与 Evidence 治理](../../global/01-repository-ownership-and-boundaries.md#5-capability-与-evidence-治理) 的定义。Config enum 或可 import dependency 不能证明 capability 已资格化；安装 MuJoCo package 也不证明统一 provider 已 implemented。

## 5. ResetSample 与 EvaluationSampleSet

### 5.1 Randomness 所有权

Task randomness 由 Geochora 生成：

~~~text
task_seed -> Geochora sampler -> ResetSample
~~~

Provider randomness 独立存在：

~~~text
provider_seed
provider_determinism_mode
~~~

Provider 不得重新采样 Task Artifact randomization parameter。

### 5.2 ResetSample

ResetSample 是完全实例化、provider-neutral 的 episode initialization request。

概念 field：

~~~yaml
reset_sample:
  sample_id: ...
  task_artifact_hash: ...
  sampler_version: ...
  task_seed: ...
  robot:
    joint_position: ...
  entities:
    cube:
      pose_world: ...
      mass: ...
      friction: ...
  sensors:
    camera_front:
      mount_pose: ...
~~~

只需包含与任务相关的 field。

### 5.3 RealizedInitialState

Provider reset 和可选 declared settle 后：

~~~text
ResetSample -> provider apply/reset -> RealizedInitialState
~~~

请求 sample 与实际 state 都要记录。Initialization gate 检查：

~~~text
distance(requested, realized) <= declared reset tolerance
~~~

Reset-realization failure 必须在 trajectory execution 前报告。

### 5.4 EvaluationSampleSet

正式跨 provider evaluation 使用一个 frozen set：

~~~text
EvaluationSampleSet = {ResetSample_1, ..., ResetSample_N}
~~~

所有参与比较的 provider 都消费同一 set，从而支持 paired comparison，以及 provider/Core upgrade 后的长期 regression。

## 6. CanonicalStateView

Phase I 使用最小 semantic state contract，而不是 universal simulator state。

### 6.1 Core field

最小 view 应支持按名称访问：

~~~text
time:
  control_step
  simulation_time

articulations:
  joint_position[semantic_joint_name]
  joint_velocity[semantic_joint_name]

entities / frames:
  pose_world[semantic_id]
  linear_velocity_world[semantic_id]（需要时）
  angular_velocity_world[semantic_id]（需要时）
~~~

可选、由 capability gate 控制的 field：

~~~text
actuator state
contact evidence
camera/sensor state
privileged state
~~~

### 6.2 Convention

Phase I canonical convention：

- SI unit；
- Task Artifact 定义的 right-handed world convention；
- 显式 frame identity；
- quaternion 顺序 wxyz；
- 使用稳定 semantic name，而不是 provider integer ID；
- 在公共边界做 finite-value validation。

Provider adapter 将 native name/index 解析为 semantic reference。

### 6.3 与当前代码兼容

当前 RuntimeSnapshot / TaskStateView 应逐步演进，而不是一次 refactor 中删除。

有效迁移路线：

~~~text
provider-native state
    -> existing runtime snapshot
    -> CanonicalStateView adapter
    -> TaskStateView / semantic evaluator
~~~

资格验证后可以合并重复 representation。

## 7. Camera 与 frame contract

Phase I 区分 camera mount frame 和 camera optical frame。

使用无歧义 transform 名称：

~~~text
T_world_from_camera
T_camera_from_world
~~~

Camera contract 记录：

~~~text
width / height
intrinsic matrix K
fov convention
near / far
mount frame
optical frame convention
T_world_from_camera
RGB layout/dtype
depth unit/convention
timestamp
~~~

资格验证关注 geometry：

- landmark projection；
- dynamic parent transform；
- depth back-projection。

不要求 pixel-perfect photometric equality。

## 8. Action 与 controller contract

Phase I 分离四层：

~~~text
requested action
    -> canonical/public action
    -> canonical controller target
    -> provider-applied actuator control
~~~

对 Panda manipulation，Phase-I 初始最低公共 canonical target 应为 arm joint-position target + gripper target。

Public action 可以继续包括 absolute_joint、absolute_pose、delta_pose。

使用 pose action 时，只要可行，共享 Geochora controller computation 应在 provider boundary 前将其解析为 canonical control target。

Provider adapter 负责从 canonical target 到 native actuator API 的最终转换。

## 9. CanonicalTrajectory v0

保留当前 T/T+1 invariant：

~~~text
observations: T + 1
transitions:  T
~~~

Trajectory 必须能够诊断跨 provider divergence 起源。

推荐逻辑内容：

~~~text
meta/
  Task Artifact identity/hash
  ExecutionSpec
  provider/adapter version
  timebase
  schema
  ResetSample
  RealizedInitialState
  expert/policy provenance

obs/
  canonical state
  proprioception
  配置时的 rgb/depth

camera/
  intrinsic
  T_world_from_camera

action/
  requested
  canonical

control/
  target
  applied

task/
  reward
  success
  failure
  metric
  predicate
  event
  trajectory-quality input

terminal/
  terminated
  truncated
~~~

具体 H5 layout 可以从现有 v2 writer 演进。新 field 必须 versioned；旧 Evidence 必须仍可读取，或存在显式 migration。

## 10. Open-loop 与 closed-loop qualification

### 10.1 C1 Open-loop replay

相同项：

~~~text
Task Artifact
ResetSample
canonical control sequence
timebase
~~~

不同项：provider。

用途：

- differential physics/controller-realization Evidence；
- state 与 event divergence measurement。

Contact-rich manipulation 不要求 long-horizon exact state equality。

### 10.2 C2 Closed-loop expert

相同项：

~~~text
Task Artifact
ResetSample
expert algorithm/config
~~~

Expert 每一步重新观测当前 canonical state。

用途：

- behavioral/task feasibility；
- semantic stage completion；
- success/failure；
- collision/safety；
- trajectory quality。

C1 与 C2 是独立 gate。

## 11. Physics equivalence profile

不能假定每个 provider parameter 都有一对一映射。

### Exact semantic parameter

例如 unit、gravity、mass、inertia、geometry dimension、joint limit、physics/control timebase。

### Approximately mapped parameter

例如 friction、damping、actuator gain，以及存在有意义映射时的 contact compliance。

### Provider-native parameter

例如 solver iteration、ERP/stabilization internal、provider-native contact regularization、backend/kernel setting。

资格验证比较的是声明 tolerance 下 provider-independent 的 physical/behavioral output，而不是 provider-native solver field。

## 12. 主要与边界 provider 资格验证

### 主要：GeoPhys、MuJoCo

必须覆盖 materialization、canonical state/reset/timebase、camera geometry、canonical control、C1 open-loop、C2 closed-loop、dataset/replay、state policy 与 visuomotor policy。

### 边界：SAPIEN、Genesis

必须覆盖 capability admission、materialization、canonical state/reset/timebase、camera geometry、canonical control、conformance probe 与 PickCube C2 closed-loop expert。

Phase I 不要求完整 policy training。

## 13. Provider adapter 规则

Provider adapter 内部可以使用 provider 公共 API。

Task Artifact、task semantics、learner-facing code、recorder contract 与 public runner 不得：

- 导入 provider-private internal；
- 依赖隐藏的 mutable singleton state；
- 仅根据 import 成功推断 capability；
- 为适配 provider 而静默改变 task semantics。

不支持的 capability 必须 fail closed，并提供足够 metadata 供诊断。

## 14. P1.1 additive contract route

`task_env.artifacts` 提供 Phase-I advanced data contract：TaskArtifact v0、WorldDefinition、InitializationContract、SemanticDefinition、Timebase、ExecutionSpec、RequiredCapabilitySet、ProviderCapabilityManifest 与 CanonicalStateView。它们支持 strict mapping validation 和 deterministic roundtrip；TaskArtifact SHA-256 identity 只包含 artifact mapping，不接受 execution field。

Canonical convention 为 SI / right-handed Z-up / wxyz unit quaternion。Timebase 允许至多一个 ULP 的浮点 representation difference。未知字段、schema、capability、非 finite 值和未声明 semantic references 均拒绝。Capability admission 只接受 implemented/tested/qualified claim，planned/unknown/unsupported 或缺失 claim fail closed；该检查本身不授予 qualification。

这些 contract 为 additive skeleton，保留 RuntimeSnapshot / TaskStateView。Production runtime 不会自动输出 CanonicalStateView；provider materialization、ResetSample realization 与 production state conversion 仍属于 P1.2。可复用 S0/S1 detector 入口为 `python -m task_env.diagnostics.phase1.p1_1_contracts --output <workspace-report.json>`；纯 fixture Evidence 不代表 simulator execution 或 provider qualification。
