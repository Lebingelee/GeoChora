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

P1.1 Human Review 修正：ActionIntent.reference 按 Core ActionModeSpec 表达 absolute_joint=None、absolute_pose=world/base、delta_pose=world/base/ee；strict codec 支持 nullable union，mapping 的 null 保持 roundtrip。PickCube candidate 显式记录 Panda initial_state_spec 的九个 semantic joint positions；initialization policy 指定 named joint/entity velocities 为零、arm target 等于初始 joints、gripper open，均为 canonical intent，不使用 legacy storage vocabulary。该 policy 尚未由 provider runtime apply。

Quaternion representation：未来 canonical provider adapter 在输出前 normalize wxyz quaternion；contract 保留 norm-squared sanity validation，abs(norm_sq - 1) <= 8 * 2^-23（约 9.54e-7），覆盖 float32 normalization/四分量 rounding。Contract 不静默 normalize，保持 deterministic roundtrip；zero/non-finite/明显非单位 quaternion 仍拒绝。这是 representation bound，不是 physics qualification tolerance；P1.1 没有新增 adapter。

## 15. P1.2 bounded runtime review route

新增 opt-in `task_env.runtime.sessions.materialize(artifact, execution, source=...)`
入口，admission 在 native materialization 前执行。`source` 为 task-local Phase-I
MJCF migration bridge：TaskSceneSource 与 semantic-to-source-name bindings；
MJCF representation 不决定 physics provider，也不进入 Artifact identity。
PickCube source conversion 位于 GeoPhys adapter；原 scalar compiler 兼容入口保留。
该路由当前仅实现 default PickCube、CPU、render=none、zero-settle intersection，
不替换生产 RuntimeSnapshot / TaskStateView 或现有 batch layout/profile factory。

`task_env.artifacts.execution.ResetSample` 是 immutable execution value，具有
self-excluding SHA256 sample identity 和 strict JSON/YAML mapping。
`task_env.tasks.pick_cube.reset.sample_reset` 使用 versioned NumPy PCG64 sampler，
从 Artifact ±0.10 m XY distribution 生成一次请求；九个 Panda joints、fixed Z、
identity wxyz 与 zero velocity/open gripper policy 保留。Provider 不采样或修改请求。
会话公开 reset / snapshot / step / close，仅返回 measured RealizedInitialState 与
semantic CanonicalStateView。Native IDs、地址与数组仅存在于 private adapters。

Adapters normalize measured wxyz rotation，然后进行 representation validation。
P1.2 reset smoke bounds 为 joint / cube position / quaternion component max_abs
各 1e-5（position 单位 m），不用于 physics qualification。MuJoCo 读 data.time；
GeoPhys 没有 native simulation-time API，读现有 boundary 的 completed-step clock，
并校验 source timestep。GeoPhys close 依赖 Taichi process-global ownership：
reusable detector 以 isolated subprocess 执行各 provider，close 后退出回收资源。

`python -m task_env.diagnostics.phase1.p1_2_runtime --output <report.json>` 检查
seed 31/73 的 same serialized reset、重复 reset、requested/measured state、canonical
semantics wiring 和一步时间，以及 admission negative/fresh provider-free import。
Manifest 仅声明 implemented；测试结论与 provenance 位于 P1.2 Evidence。
该 review route 不产生 qualification、physics/contact/controller equivalence
或 PickCube success parity claim，P1.3+ 保持 deferred，Human Judge decision 尚未创建。

## 16. P1.3 oracle-locked diagnostic route

`task_env.diagnostics.phase1.p1_3_conformance` 是 opt-in diagnostic microprobe
入口，包含 Asset/Frame、Free-fall、Joint-tracking、fixed Camera/Depth、Contact。
Fixture 复用 provider-neutral TaskSceneSource/MJCF representation；recipe hash
覆盖 source bytes、semantic bindings、timebase、gravity、geometry/inertial、
actuator/camera/contact facts。Oracle YAML 与 fixture hashes 在 native execution
前 SHA256-lock，之后不修改 tolerance。每个 provider/probe 独立运行、保留 raw
measured series，并分别对 analytical/behavioral oracle 判定；pairwise difference
仅用于诊断，不把 MuJoCo 当作 truth oracle。

Runtime manifest provider version 由实际 import source / checkout revision 或
installed package metadata 机械推导，不再由代码固定 GeoPhys SHA。Repository
revision、package version、dirty build fingerprint、manifest value 在 Evidence
中分别记录；没有可解析 build identity 时拒绝声明。该变更不改变 P1.2 API、
ResetSample、Task Artifact identity 或 task semantics。

Conformance native readback 仅存在于 diagnostics 的 private adapters，不进入
CanonicalStateView。Fixed camera 使用 native projection/rendered metric depth，
不修改生产 CameraSensor/capture contract。Contact 只 gate basic support behavior，
不 equalize native impulses 或调节 solver 参数。全 route 结果属于 bounded review
Evidence；没有 provider-wide qualification 或 P1.4/P1.5 capability claim。

## 17. P1.4 additive camera geometry boundary

`task_env.observations.canonical_camera` 提供 advanced camera-observation-v0 linked contract，引用 TaskArtifact hash，具有独立 identity；task-artifact-v0 与 approved PickCube serialization 不变。Legacy CameraSpec quaternion 继续表示 +X forward、+Z up mount/view frame；显式 lowering 需要调用者提供 semantic parent binding。Optical +X right、+Y down、+Z forward，固定旋转分别映射到 legacy mount -Y、-Z、+X。Resolved metadata 使用 `T_world_from_mount`、`T_world_from_camera`、`T_camera_from_world`，legacy extrinsic 不作为新 contract 的权威。

Geochora 根据 vertical FOV 和 resolution 构造 K：fx=fy=H/2/tan(fov_y/2)，cx=W/2、cy=H/2。Image-edge pixel index center 为 (u+0.5,v+0.5)。Canonical depth 是 HxW float32、meter optical-Z；有效值 positive，0 表示 invalid/background/clipped。RGB honor HWC/CHW、float32 [0,1] 或 uint8 [0,255]。Metadata 的 capture step/time 直接来自解析 semantic parent 的同一 CanonicalStateView；同步 post-control-step。

`task_env.render.camera.create_camera_session` 是 additive headless render route；独立 render admission 比较 ExecutionSpec.render_provider，当前只实现 CPU native GeoPhys/GeoPhys、MuJoCo/MuJoCo pairings，不 fallback。Source bridge 明确限于 provider-neutral static closed triangle meshes；camera attachment 可动态，scene geometry/material/texture migration 尚未覆盖。GeoPhys adapter 在已初始化的 native runtime 上拥有公开 RayCamera/FrameBuffer/MeshPipeline/RayTraceEngine，转换 ray-distance depth，不依赖 visualizer._camera；MuJoCo adapter 使用公开 Renderer。Render close 释放 session references；GeoPhys native fields 的 process-global ownership 需要 worker exit 完成 teardown。

该 bounded geometry Evidence 不宣称 RGB photometric equivalence、完整任务 visuomotor portability、GPU 或 provider-wide qualification。P1.1–P1.3 detector 不因新 route 改变。

## 18. P1.5 additive canonical control review route

Advanced opt-in `task_env.controllers.canonical` 定义 RequestedAction、CanonicalAction、CanonicalControlTarget 和 AppliedCanonicalControl。Canonical action 保留原始 mode/reference/rotation 与 interpreted values、clipped、resolved world pose；target 区分七个 semantic arm desired positions 与 corrected servo positions，gripper 区分 opening_m、force_limit_N 与 servo_opening_m。Native actuator IDs/ctrl arrays 留在 adapter 内。

CanonicalPandaController 从 Geochora-owned Panda source chain 计算 FK/Jacobian/DLS，不接收 provider、solver、native model 或地址。当前 bounded profile 为 stateless achieved-state one-increment DLS，显式保留 shared config 与 controller identity；不宣称复现 legacy stateful target accumulation 或 experimental gripper force-feedback mode。默认 signed gripper scalar 对应 0–0.08m，legacy physical profile 为 5N、2500N/m opening correction。Delta world/base/ee composition 有 provider-free checks。

`task_env.runtime.sessions.control.materialize_control` 在 native materialization 前执行 control capability admission。ControlledRuntimeSession 添加 apply_control(target) -> AppliedCanonicalControl，step 沿用 P1.2 ZOH/control-substeps 路径；legacy controllers、RuntimeSnapshot、TaskStateView、no-control session 和 approved task-artifact-v0 均保留。

Reusable `task_env.diagnostics.phase1.p1_5_control_expert` 消费锁定的 evaluation oracle。C1 使用一次生成的 semantic targets；C2 compatibility view 只来自 CanonicalStateView、canonical task evaluation 与 action metadata，调用 unchanged PickCubeSolution。该 route 目前是部分实现的 review candidate：C1-A 通过；锁定 gripper close duration 内未满足 close bound，C1-B 未满足 final tracking bound。依据 operator Goal 的 low-cost prerequisite gate，C2 未执行。没有 expert success、provider-wide qualification、P1.6 trajectory 或 policy portability claim；详细数值/provenance 属于 P1.5 Evidence 和后续 Human Review。

## 19. P1.5-R1 recovery ownership and evaluation version

`ProductionCanonicalPandaController.from_source` 是 additive opt-in canonical route；gripper profile authority 为 resolved `source.config.robot.gripper`，identity 包含其所有字段。ActionConfig 仅提供既有 opening range/stiffness 和 arm parameters，不再以 fallback force 定义 production gripper profile。Controller 显式 reset，然后每个 measured control boundary compute 一次，拥有 persistent commanded opening、rate limit、force activation、首次 initialization 与 deadband adjustment。冻结的 `CanonicalPandaController` v0 仍只用于旧 oracle/replay compatibility；两者没有替换 legacy production controllers。

独立 `CanonicalControlFeedback` 使用 semantic gripper opening 与非负 closing-direction force magnitude，并要求 step/time/opening 与同一 CanonicalStateView 一致。Force 表示最近完成的 native actuation interval；reset 时使用初始化后的 native force。Native force sign/index 只在 adapters 内转换，MuJoCo 在既有 post-forward refresh 前保存 completed-interval force。当前实现仅支持已审计的 positive-open Panda tendon binding，以及 deadband 小于 force limit 的 experimental profile；不声明通用 force-sensor/control support。canonical-state-v0、TaskArtifact v0、P1.2 no-control behavior 保持不变。

`task_env.diagnostics.phase1.p1_5_r1_recovery` 只执行 provider-free state machine、resolved-profile free-space gripper、旧 C1-A 和 versioned settled C1-B prerequisites。R1 使用独立 oracle/lock；C1-B 完整旧 40 targets（包括其 archival 5N open gripper 和 controller identity）保持不变，最后完整 target 再 hold 1 秒。该 arm replay 不是由 R1 controller 重新生成的 expert sequence；new gripper 的 contact/expert integration 尚未测试。旧 moving-end failure、旧 160-tick gripper failure 与 R0 diagnostics 均保留。R1 不运行 C2、不创建 qualification decision；结果由 Human Review 判断。

## 20. P1.5-R4 versioned stage readiness

Advanced `PickCubeReadinessSolution` / `PickCubeReadinessConfig` (`pick-cube-readiness-v1`)
are additive public expert clients. Historical `PickCubeSolution` remains unchanged.
The versioned route reuses its geometric/planner primitives and separates plan
exhaustion, physical readiness, and task outcome. `StageCompletionPolicy` supports
pose_ready, gripper_ready, task_outcome; exhausted plans repeat the exact final
public action, and traces mark readiness holds.

Pose thresholds come from resolved ActionConfig controller deadbands, with a
1-second timeout mechanically converted through Artifact control_dt. Read-only
`ProductionCanonicalPandaController.readiness(state, feedback)` produces
`CanonicalControlReadiness`: same-boundary semantic close readiness and physical
force/error. Expert consumers receive only `ExpertExecutionInfo`, separately
from task metrics; they never inspect controller memory or native force signs.
The controller compute profile and identity are unchanged.

Experimental close horizon follows R1: max(full opening range/opening step,
full range/force adjustment step), rounded up, plus common 0.2-second dynamics
margin. The 20 transition actions count within that total horizon. Planned budget
120 excludes readiness holds; deterministic global cap sums planned budget and
all stage hold budgets. Identity includes planner, resolved profile/thresholds,
timebase, policies and derivation. Lift completes immediately at measured task
success plus the unchanged 0.105m collection endpoint, even before plan exhaustion;
final EE pose readiness is diagnostic only. If exhausted, final lift action may
hold for at most 1 second, then explicit lift_outcome_timeout.

`p1_5_readiness` is a locked production readiness smoke, not final P1.5 C2
qualification. No task-artifact-v0, task-success, controller behavior, native
physics, prior expert identity or older Evidence is revised.

## 19. P1.6 additive canonical trajectory / state-policy route

Advanced `task_env.trajectory.canonical` 提供 `canonical-trajectory-v0` 和独立 `task-env-canonical-trajectory-v0` H5 route；不修改 historical task-env-h5/v2。Recorder 拥有 reset boundary、每个 transition 的 post-step boundary 和 freeze，验证 T+1/T、timebase、requested/canonical/target/applied linkage、target hash、semantic names 与 metadata identities。Boundary 包含 CanonicalStateView、Feedback、Readiness 和 task outcome；planned/readiness-hold 都是完整 transitions。H5 保存 exact logical mappings 与 float64/int64/bool numeric projections，load 校验 shapes/dtypes/content；logical hash 不依赖 HDF5 container bytes。Heterogeneous expert diagnostic values losslessly encode 为每个 key 的 JSON string，不作为 learner feature。

Optional `task_env.alg.state_bc` 定义 `pick-cube-state-policy-v0` 33D float32 features：arm position7/velocity7、canonical gripper opening1、EE position3/rotation columns6、cube position3/rotation columns6；rotation 顺序为 column0 然后 column1。8D public absolute_joint target 来自 desired arm positions 和 physical opening 的 inverse signed-scalar mapping，不读取 servo/native ctrl。Dataset 消费 loaded canonical files，保留全部 readiness holds，checkpoint-local normalization 只来自各 source train set。固定 CPU MLP [128,128]/ReLU/Adam route 与 validation checkpoint selection 均属于 versioned Experiment config；provider 仅是 training provenance，不参与 inference branch。

`task_env.diagnostics.phase1.p1_6_state_policy` 执行冻结 spec 下的 collection、loaded-control replay、learner/checkpoint smoke、两-source training、same-checkpoint transfer matrix 与 lower-phase regressions。Learned rollout 始终经 RequestedAction -> accepted ProductionCanonicalPandaController -> provider realization；direct loaded targets 只用于 replay。Time rollback 是 runtime failure，不能作为有效 policy state继续运行。

历史 Evidence 必须按阶段读取：最初 state_bc route 的 EvaluationSampleSet 31/73 task-success matrix 为 1/8，且 G->MuJoCo seed73 有 native warning/time rollback；最初 canonical-trajectory/state-policy acceptance 因此为 `partial_with_localized_failure`。后续 Flow policy-search 保留 V0/V1/V2/V1a/V2a 各自的 config、checkpoint 与结果；最终 V2a 在固定 source-domain cohort 上为 6/6。该工程搜索并非因果消融，不能把收益归因于单一的 horizon 或 qvel 变化。

已批准的 P1.6 bounded closure 使用版本化的 PickCube 100Hz 实验 Artifact（physics dt 0.002 s、5 个 physics substeps、control dt 0.010 s；默认 500Hz Artifact 不变），以及 GeoPhys 训练的 V2a FINAL checkpoint。冻结 D3 配对评估在 train-support 与 validation-support 上均为 GeoPhys 10/10、MuJoCo 10/10；同一 checkpoint、ResetSamples、26D observation contract、normalization 与 public `absolute_joint` / `ProductionCanonicalPandaController` 路线贯穿两 provider。40 个 episode 的 simulator-freeze、finite state/action、零 action clipping 检查通过。这支持在上述有限 PickCube/V2a/100Hz 范围内的 bounded checkpoint/software portability，不支持 statistical robustness、任意 task/policy portability、provider-wide qualification、visuomotor portability 或 Phase-I 完成。Human Judge 已在该限定范围内批准 P1.6；该 bounded approval 不代表 statistical robustness、provider-wide qualification 或 Phase-I 完成。

同一 10 个 validation seeds 的 supplementary local-environment check 为 Genesis 10/10、SAPIEN 9/10（seed 2212 未达到 0.10 m，运行至 2500 control steps）。该结果使用 Genesis 1.4.3、SAPIEN 3.0.3 与 CPU physics，但其 session implementation 来自 closure branch 之外的 P1.8 source snapshot，不能仅由 `codex/p1.6-closure` 重现。因此它只作为 supplementary bounded Evidence，不给 Genesis/SAPIEN provider qualification，也不改变 core GeoPhys/MuJoCo closure result。

可复用的 replay/portability 诊断顺序为：D0 用记录的 state/feedback 检查 public action 转换能否复现 canonical target；D1 对记录的 `CanonicalControlTarget` 做 exact replay；D2 让转换后的 public action 经生产 controller 做 closed-loop provider replay；D3 再运行 frozen learned policy，比较同一 checkpoint 与 canonical contract 在多个 provider 上的任务结果。D0–D2 的 seed1000 PASS 是历史 Evidence，原始 source tree dirty 的事实被保留，未 retroactively rerun。

P1.7 保持 deferred；P1.8 按 Human-authorized roadmap 独立推进。P1.5 behavioral sources、TaskArtifact v0、GeoPhys core、MuJoCo core 与默认 PickCube Artifact 均未被此 closure package 修改。
