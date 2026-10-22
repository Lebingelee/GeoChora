# Phase D — Physics / Rendering Independence：架构、实施切片与验收

> **ACTIVE bounded implementation record；Phase D remains incomplete and carries no new Qualification.**
> 修订于 2026-10-22；源码审阅基准仍为规划期 `develop@f292df149f41520b484ff27cf2ff78a584903013`，发布 v1.1.0。
> 总体蓝图：[`00_Phase_II_AD_Implementation_Blueprint.md`](00_Phase_II_AD_Implementation_Blueprint.md)；A/B/C 输入见相邻阶段文件。
> **当前状态（2026-10-22）**：D01b/D02b 保持原有 bounded evidence；序号 31／D03 的 GeoPhys CPU × MuJoCo native OpenGL RGB 动态同步首个交集已通过；序号 32／D04 的 RGB/Optical-Z Depth 与固定/hand-mounted camera 已通过 S1/S2，Entity Instance Segmentation 也完成受限首个交集 S1/S2；序号 33／D05b 已完成该 exact 交集的 selection→admission→materialization→sync→capture→close S1/S2。完整 D04/D05b、Env policy/Recorder consumer 接线、广泛 Renderer/Scene 支持及 Phase II 均未完成。

## D.0 讨论结论与范围

用户已确认将 D 的本轮架构开发收束在 **D1–D3**：

- **D1 — Canonical Scene Materialization**：Physics 与 Renderer 从**同一份** Canonical Scene Definition 分别生成各自原生 Scene，使用共同的 Entity/Frame Identity；Visual Geometry 可与 Collision Geometry 不同。
- **D2 — Canonical Runtime State**：以现有 `CanonicalStateView` 演进为 Named Typed State + Capability Extensions + Explicit Time Semantics；Provider 为 native physical state 唯一 Owner，向不同 Consumer 提供 Entity-oriented Read Views。
- **D3.1 — Scene Synchronization**：Render State Projection；Transform/Geometry Sync 分离；状态发布版本独立于物理步数；按需渲染。
- **D3.2 — Camera & Sensor Contract**：Camera Independent Definition/Frame/Intrinsics、RGB/Optical-Z Depth、Segmentation Canonical IDs、Capture Timestamp；默认同步，预留异步。
- **D3.3 — Physics × Renderer Composition**：独立选择与配置、按 Camera 覆盖、明确 Pairing Capability/Runtime Resources/Admitted Envelope；在线 Camera 与离线 Re-render 可共享定义但生命周期不同。

**原先的 D4 Provider Feature Mapping、D5 Cross-provider Qualification 不再作为单独的概念开发阶段。** 但 Exact/Approximate/Unsupported 的参数映射约束必须进入 D01/D02；必要的 Pairing S1/S2/S3 Evidence 必须进入 D05。完整任务/Provider Qualification Governance 沿用现有规范，广泛 Task Harness/自动 campaign 属未来 E。

**不做**：新的 Canonical OpenUSD 全量系统、全类 soft/cloth/fluid/particle visual pipeline、全 Physics×Renderer pair 正式资格、render 进程分布式集群、Phase III Batch Render 全面改造、Solver Kernel 改写。

## D.1 当前仓库可复用能力与明确缺口

| owner | IMPLEMENTED | 必须保留的限制 |
| --- | --- | --- |
| [`task_env/assembly/compiler.py`](../../../../../task_env/assembly/compiler.py)、`assembly/references.py` | 有界源与具名 task scene/source mapping | 仍含明显 MJCF/task-specific 组合，非通用 Canonical Scene materializer |
| [`task_env/runtime/sessions/api.py`](../../../../../task_env/runtime/sessions/api.py) | `RuntimeSession`, `provider_manifest`, `materialize`；GeoPhys/MuJoCo/SAPIEN/Genesis adapter | 适配器存在不代表同等支持或 selected-task qualification |
| [`task_env/artifacts/contracts.py`](../../../../../task_env/artifacts/contracts.py) | `CanonicalStateView(canonical-state-v0)`、`ExecutionSpec`, Manifest/Admission | v0 标量 joint maps，不代表 floating-base typed state 全支持 |
| [`task_env/observations/canonical_camera/contracts.py`](../../../../../task_env/observations/canonical_camera/contracts.py) | `CameraGeometry`, `ResolvedCameraMetadata`，Mount/Optical、Step/time、FOV/K | 当前 `camera-observation-v0` 仅明确 RGB/Depth、post-control-step |
| [`task_env/observations/canonical_camera/images.py`](../../../../../task_env/observations/canonical_camera/images.py) | RGB/Depth strict normalize + `CanonicalCameraObservation`；D04 增加 versioned Entity-instance mask/label-map values | Segmentation 仅限已准入的 exact profile；Semantic labels、Link IDs 与 async capture meta 未通用实现 |
| [`task_env/render/camera/source.py`](../../../../../task_env/render/camera/source.py) | 保留 `camera-static-triangles-v0`；另有 D03 `camera-dynamic-source-v1` 的 Scene-v3 scalar Joint/Frame binding 与 typed state projection | 动态源只接受确切 Scene/source closure 与一一映射；不支持 free-joint、变形体或通用 Visual Scene |
| [`task_env/render/camera/api.py`](../../../../../task_env/render/camera/api.py) | 旧 `create_camera_session()` 与 `admit_render()` 不变；dynamic route 有独立 D03 RGB、D04 RGB-Depth、D04 Entity-instance profile，均 admission GeoPhys CPU → MuJoCo native OpenGL | 仅限 Scene-v3 scalar-joint Position source 与同步 pinhole；不是通用 D05b pairing admission，不支持 semantic segmentation/free-joint |
| [`task_env/render/base/`](../../../../../task_env/render/base) | `RenderBackend` registry 与 `UiRenderProvider` 等独立 contract | UI presentation 与 Camera Sensor 不能混为一体；Flora fake tests 不是 native Flora acceptance |
| [`task_env/runtime/sessions/control.py`](../../../../../task_env/runtime/sessions/control.py) | Panda specific controlled session capabilities | 特定 Panda joint/actuator 数量约束，不等于通用 multi-robot control |

**现有文档的硬性 Convention**：SI；right-handed Z-up；Quaternion wxyz；`T_world_from_camera` 与逆；Optical Frame +X right、+Y down、+Z forward；Depth `float32` metre **optical-Z**、0 invalid；RGB HWC/CHW 和 dtype/range 必须声明。先保护，后版本化扩展；不随 Renderer 私有约定改变。

### D.1.1 审阅补充的复用入口与选择维度

- [Core compiler](../../../../../task_env/assembly/compiler.py#L236-L269) 已调用公开 import_scene_source；
  [ImportedScene](https://github.com/SCAILab-USTC/GeoPhys/blob/c665ce5028a12bb4d2afe49f05e015fa9b684a39/src/scene/scene_import.py#L296-L363) 已提供 ir/capability_report
  和独立 solver/render lowering。D01/D03 先评估这些 owner，不能默认从 static triangle bridge 重写全 pipeline。
- Core Scene 身份和 Provider Scene IR 不是两个可写物理世界：前者定义任务结构意图，
  adapter 映射到后者公开 lowering；不把 GeoPhys IR/array storage 规定为所有 Provider 的 ABI。
- 旧 [ExecutionSpec](../../../../../task_env/artifacts/contracts.py#L935-L949) 的 render_provider 为 scalar；D05a
  在同一 Artifact owner 增加带版本的静态选择值，但不接入旧 materialize/camera session。
  [Camera admission](../../../../../task_env/render/camera/api.py#L17-L45) 当前仍用 geophys/mujoco 且强制同名，
  [UI backend](../../../../../task_env/render/base/contracts.py#L19-L25) 则用 raytracer/rasterizer/flora。
  Provider、backend、profile、device/runtime identity 必须分层；rasterizer 不能冒充 provider 名。
- EXACT/APPROXIMATE/UNSUPPORTED 是属性映射保真度，IMPLEMENTED/TESTED_BOUNDED/QUALIFIED 是实现/证据状态，
  两者不能互换。必要 source semantics 不允许因为 canonical schema 暂无字段而静默丢弃。

## D.2 整体推荐架构：一份 Scene，两类 Materialization

```text
            A: Canonical Asset / Scene Definitions
                           │
               ┌───────────┴─────────────┐
               │                         │
               ▼                         ▼
        Physics Materializer      Visual Materializer
               │                         │
               ▼                         ▼
         Physics Native Scene       Renderer Visual Scene
               │                         ▲
               │ authoritative native    │ engine-owned GPU/cache
               ▼                         │
        Canonical State / Frame           │
               │                         │
               ▼                         │
        Render State Projection          │
               │ ┌─ Transform updates   │
               │ ├─ Geometry updates    │
               │ ├─ State versions      │
               │ └─ Mapping/capability  │
               ▼                         │
        Renderer Synchronization ────────┘
               │
        Camera Capture / Metadata
               │
       C Observation Builder → env.step result
```

- Provider Adapter 不拥有新的 Task Semantics/Controller Solver；Provider-native solver 继续由原 Provider 管理。
- Render Scene Mapping 是 `Entity/Frame ID → Native Renderer Node` 的只读/受限绑定；不要让 Renderer 从 Physics native body index 自己重建任务语义。
- Render State Projection **仅是按 Consumer 需要映射/缓存的只读状态投影**，不拥有第二份随物理独立演化的 state。
- UI Presentation 与 Camera Observation 是两个 contract。Renderer 可以共用底层引擎，但其 capture、metadata、输出资格分别判断。

## D.3 D1 实施细化：Materialization & Mapping

### D.3.1 两种 Materialization 输入不同、身份一致

**Physical View**：Rigid/Articulation/Mass/Inertia/Joint/Collision/Actuation 等声明。**Visual View**：Mesh/Material/Texture/Light/Camera/Visibility/Frame/Scene Hierarchy 等声明。共享稳定的 Entity/Link/Frame 身份，不要求物理碰撞网格与精细视觉 Mesh 相同。

```text
Canonical Entity: cube_01
  ├─ Physical: box collision, mass, inertia
  ├─ Visual: beveled textured mesh
  └─ Shared Frame: cube_01/base
```

转换报告每种必要属性的 `EXACT / APPROXIMATE / UNSUPPORTED`。必要 Exact 项不允许静默降级；未知 geometry/actuation/camera capabilities 必须在 admission 或 materialization 失败。对于 friction/damping/compliance 等不完全等价参数，声明 approximation mapping 与 tolerances，不能冒充 native 参数一一相等。

### D.3.2 Scene Variant 与 Reset

- **结构不变的 ResetSample**：尽量复用已 Materialized Scene，只执行 provider reset/realization check 与 render transform invalidation。
- **拓扑变化的 Scene Variant**：验证合法性、计划局部 rebuild 或新 scene instance；不强迫所有任务的每次 reset 都重建 GPU scene。
- Reset 之后 **Camera Pending Frames、Renderer temporal cache、State Versions** 必须对齐新 Episode；不能返回上一 Episode 图片。
- `ProviderMaterializationID` / `SceneInstanceID` / Canonical identity 有不同生命周期，不得混淆。

### D.3.3 资源所有权与关闭

- Physics Session 负责 native model/state、controls、teardown；Renderer Session 负责 Visual Scene、Camera render objects/buffers、GPU caches；GeoChora facade 负责协调且保证 exactly-once close。
- 失败中途构造要 rollback 已成功的 owner；进程级 GPU/GeoPhys 全局分配器可能不能由 Python `close()` 真正释放，需要 worker isolation，不能隐瞒这一点。
- 编译/Materialization 不等于 Runtime validated；同样不等于正式 Qualification。

## D.4 D2 实施细化：Typed Canonical State

### D.4.1 基础状态与 Extensions

```text
Canonical State Boundary
 ├─ identity: episode/scene-instance/materialization/boundary
 ├─ clock: control_step, simulation_time
 ├─ joints: entity-qualified typed position/velocity
 ├─ frames: world pose (and validity/provenance)
 └─ capabilities (optional): dynamics/contact/kinematics/sensors
```

- Revolute/Prismatic joint 有标量 position/velocity；Spherical/Free-base 不能被 `Mapping[str,float]` 强制等长。Free-base pose 应允许采用 SE(3)，velocity 用声明 frame 的 6D Twist。
- `state.joints["robot_left/joint1"]` 与按 Entity 的 `state.entities["robot_left"].joints["joint1"]` 是**同一只读数据视图的两个投影**，不能双写/复制出两个权威值。
- 未支持 Contact Force ≠ 真实 Contact Force 为 0；强制 Required/Optional 分开，缺失明确 unavailable。
- Quaternion 位置参数、角速度所在 frame、Twist 的参考点与表达 frame 必须明确；free joint 的 position/velocity
  不同维数需要真实 adapter 测量，不能只验证类型构造。零拷贝 view 不能被 Recorder 跨步持有后随 native buffer 改写。
- Task、Controller、Observation、Renderer 分别声明 State Requirements（field/frame/units/sampling/capability）；Environment/Runtime 汇总需求，在同一 Boundary 生成一致的 Canonical Projection，避免每个消费者各自读出不同时刻的状态。
- 真实 Runtime State 与可恢复 Checkpoint 不同；没有包含 controller/semantic/solution/RNG/renderer memory 的证据就不能称为完整 restore。

### D.4.2 时间、只读与原生高频

- `control_step` 与 `simulation_time` 明确；同一 outer boundary 内不同消费者读取相同“物理事实”。
- 每次可见状态改变（包括 same-step reset/manual pose write/geometry update）需要增量版本，不能仅靠 physics step number 作为 dirty flag。
- Native-rate Guard/Force Evidence 必须是真实采样区间，保留该区间 `[t,t+dt)`；Outer interpolation 不能变成 500Hz 接触采样。
- Provider 原生只读 Array 允许在 Lifetime/aliasing 有效范围内零拷贝；若跨 GPU stream/重置失效，则由 Adapter 进行缓存/复制并标明 Lifetime，不强制 Python 对每个 Step 全量 copy。

## D.5 D3.1 实施细化：Render State Projection

参考 [Isaac Lab `SceneDataProvider`](https://github.com/isaac-sim/IsaacLab/blob/develop/docs/source/concepts/scene_data_providers.rst) 的高价值原则：Producer publication version、consumer read-only remapping、同版本避免重复转换；但不引入 Warp 数组作为 GeoChora 的唯一 ABI。

候选同步数据：

```text
RenderStateFrame
 ├─ scene_instance_id / state_boundary_id
 ├─ transform_version (even if control_step unchanged)
 ├─ geometry_version
 ├─ optional visual_material_version
 ├─ transform bindings: frame_id → renderer visual node
 └─ geometry bindings: visual_id → mutable vertices/points (optional)
```

Phase II 必须完成 **Rigid / Articulation Transform Sync**；Deformable/Particle 可在 Type/Capability 上预留，但实际完全实现仍 DEFERRED。多个 Renderer 各自记录 `last_seen_transform_version`；不能由一个 Renderer 消费后清除全局 dirty flag，使另一个遗漏更新。Renderer 仅按 Camera/Visual Demand 同步，不强制无 Camera 的 RL 每步渲染。

D03 的真实 Oracle 必须看到运动物体/link 的像素投影改变，而不只是 metadata version 增长；
same-step pose write、reset、两个 consumer 的消费顺序都要覆盖。先评估公开 render description/transform
接口；没有公开动态上传能力时，报告 Provider gap 并走 owner-reviewed 扩展，不能私读 renderer cache。

## D.6 D3.2 实施细化：Camera/Sensor & Modalities

### D.6.1 Camera Definition 和 Observation 分离

**Camera Definition**：Camera ID、Parent Frame、T_parent_from_mount、T_mount_from_camera、K/Projection、width/height、near/far、Sampling Period/Phase、Required Modalities、Capture Identity requirements。

**Camera Runtime Binding**：Scene/Frame/Renderer refs、capture scheduler、output normalization、resource lifetime。

**Camera Observation**：图像 Buffer + 原子关联的 capture metadata（Camera Pose、K、采集时刻、Episode/State Boundary、renderer/profile identity）。

- RGB：保留当前 HWC/CHW、uint8[0,255]/float32[0,1]；补充 sRGB/linear/HDR 等 Color Encoding 的显式元数据。**不能**仅凭 `[0,1]` 推断 Gamma。
- Depth：统一 `H×W float32` **optical-Z in meters**，0 invalid/clipped/background；Ray Distance 与 Optical-Z 必须声明转换；回投影必须使用同次 capture K/Pose。
- Segmentation：Semantic Category ID 与 Entity/Link Instance ID 分离；输出整数 mask + canonical label mapping，background/unknown ID 明确；Renderer 原生 indices 不外泄。Colorized Mask 仅用于 UI/诊断。
- Camera Parent Frame：Fixed World、Wrist、Robot Head、Dynamic Attach 均走 D2 Frame Graph；不让 Renderer 独立 FK。
- 默认同步 Capture；低频 Camera 可声明 hold-last 并带真实 capture step/time；异步预留 capture time ≠ return time，重置后旧 pending frame 必须失效。
- 首个实现限定 pinhole、同步 capture、既有 RGB/optical-Z Depth，并增加受限 segmentation。
  任意 K/skew、distortion/fisheye、真实 async scheduling 不由字段存在推断支持，未实现时明确拒绝。
- 缺失 required modality/时间新鲜度时 Admission 拒绝或合法执行失败，不能删除字段、填零并假称有效。

### D.6.2 Obs/public 组织继续归 C

规范化 RGB/Depth/Segmentation 必须能由 C Observation Builder 返回 `obs`；元数据可以作为单独只读 capture object 或 `info` 引用，**必须与具体 Buffer 的 Capture Identity 原子绑定**；不得用当前机器人 Pose 解释旧图像。UI Viewer 的 `rgb_array` 与 Policy Camera Observation 不相互替代。

## D.7 D3.3 实施细化：Physics × Renderer Composition

### D.7.1 配置：Environment default + per-Camera override（示意）

```yaml
# PROPOSED; not available as current public schema
execution:
  physics: {provider: geophys, backend: cpu, profile: declared_v1}
  renderer:
    default: {provider: geophys, backend: rasterizer, profile: fast}
    cameras:
      wrist: {provider: geophys, backend: rasterizer, profile: fast, outputs: [rgb, depth]}
      overview: {provider: mujoco, backend: native, profile: declared_rgb, outputs: [rgb]}
```

一套 Scene，不是多个 Physics；多个 Camera 可选择不同 Renderer。此 YAML 仍是**未接入运行时的示意配置**；
示例 backend/profile 不表示当前 registered/admitted。D05a 已在既有 Artifact/Camera owners 下交付旧 scalar
`ExecutionSpec` v0 原样保留、显式 v1 decoder、完整 per-camera selection 与静态 identity。它复用现有
ProviderCapabilityManifest，不另建 Provider 框架。只有 distinct resolved selection 才需新
Renderer Session；同配置共享 Scene/cache 时，Camera calibration/buffer/schedule 和 refcount/close 仍独立。

### D.7.2 Admission 不是一个布尔值

推荐四个 Gate（复用 C3 与现有 manifests，不新建 Qualification 体系）：

1. **Static Requirements**：Task/Scene/Controller/Camera 声明所需几何、Frame、time、output capabilities。
2. **Pairing Capability**：Physics × Renderer × Backend/Device/Runtime × Scene Geometry × Camera outputs；检查互斥依赖（例如 Kit/非 Kit）；显式 manifest/version/known unsupported。
3. **Materialization Validation**：真实链接 frame/render nodes、材料/纹理/geometry、camera intrinsics；只可声明近似的字段记录 approximation report，必须项失败。
4. **First Runtime Realization**：reset→同 State Boundary→sync→capture，验证 Shape/Dtype/K/Pose/Depth/Segmentation ID 和“不推进 Physics”；标记已实现/有界测试/资格三种独立事实。

能力不应只用 `GeoPhys+RendererA=True` 声称；至少声明具体 `Task/Geometry/Modalities/Timing/Profile`。**当前 `CameraRenderSession` 严格同名 physics/render provider，不可因本路线而误报已解耦。**

**本轮首选工程目标**：GeoPhys CPU physics × MuJoCo native renderer × rigid calibration scene，
先验证 RGB/Depth、动态 transform、mounted camera 与 capture 不推进 physics。该 cross pairing 当前会被拒绝，
需要真实 adapter/materialization/sync Evidence，不能只删除同名 gate。Segmentation 单独按 capability 准入。
异名样例有助于验证 portability，但 independence 的判据是共同 Scene 身份、独立实例化、canonical state
输入及正确时间同步；字符串相同/不同本身都不是充分证明。首选不成立时明确 blocker，替代目标需重新声明范围。

### D.7.3 Resource sharing 与异步

相同 Renderer 实例配置可以共享 Render Scene 和 Renderer-native caches，不同 Camera 仍有独立 Calibration、Capture Schedule、Buffers、Pending Events。不同 Renderers 可能各自复制 Visual Scene/GPU data；允许 Renderer Cache 重复，禁止 Physics Authority 重复。没有独立 GPU/多线程 lifetime Evidence，不强制在 Phase II 同时运行所有 Renderer。

在线 Environment Camera 与离线 Trajectory Re-render 共享 Scene/Camera/State 的语义，但独立生命周期；后者可以使用 C 已记录 Canonical State Sequence，不能假装它运行了真实 Physics Step。完整离线数据生产 Harness 归 E。

## D.8 五个 Implementation Goals

### D01 — Physics Scene Materialization / Binding（a/b）

- **D01a**：依赖 A05/B04a/C01a，用 v0 schema 的新 candidate microfixture 或经证明等价的只读 projection，
  保持旧 frozen Artifact/hash 不变；使用既有 ExecutionSpec 和受限 compatibility bridge，
  提前跑一个新 Scene 表示真实到 Provider 的 microprobe；source、state 和 mapping 必须消费新输入，
  不能仅执行旧 hardcoded recipe。不等待完整 B/C。
- **D01b**：依赖 D01a/B04b/C01b，完成 vNext、固定拓扑 Role/Reset/realization 接入和
  GeoPhys/MuJoCo 两 provider 验证。沿用 TaskArtifact/TaskSource、`RuntimeSession.materialize()`、
  `EpisodeResetPlanV1` 与现有 provider adapters；TaskArtifact v1 必须引用精确 Scene identity，
  Role/Reset 产生的同一个 provider-facing ResetSample 在两个 Provider 上分别过 rollout 前测量 gate。
  当前有界交集是单 RobotInstance、固定拓扑、scalar revolute/prismatic joints；多 Robot、拓扑 variant
  和 free-body pose reset 不进入本切片。
- **验收**：命名 Entity/Frame 在 GeoPhys/MuJoCo 支持的限定任务中都能解析；缺必需 Joint/Frame/Geometry fail-closed；同一 hash-bound ResetSample 在 rollout 前执行 realized-state tolerance gate；无隐式重新采样或 private solver 访问；S2 真实 microprobe。
- **补充 Gate**：realization tolerance 是 rollout 前实际执行的 gate，不只是写入 RealizedInitialState；
  场景改变一个可测属性应改变 provider realization，证明新 Source 真正生效。映射报告包括当前资产必需
  transmission/constraints/inertial-frame/contact 语义，不能将保留但未执行误标 EXACT supported。
- **Codex AUDIT**：确定现有 MJCF-centered `assembly/compiler.py` 能复用的构造边界，以及哪些 conversions 必须 deferred；不得以“架构完整”名义重写 solver。

#### D01a bounded execution receipt (2026-10-20)

按 [执行顺序](05_Architecture_Review_and_Execution_Order.md#3-切片依赖与推荐执行顺序)，A05、B04a、C01a
完成后进入 D01a。维护者批准将 `scene-definition-v3` 原样 mapping 作为该 microprobe 的输入契约；本切片仍是
EXTEND_EXISTING/COMPOSE_EXISTING 的 GeoPhys 有界桥接，不是新的通用 Scene importer 或第二套 Runtime。

实现沿用 `RuntimeSource`、现有 GeoPhys session/composer、GeoPhys public `SceneSource`/`ImportedScene`
与 `build_rigid_scene_model()`。candidate `TaskArtifact` 和 `ResetSample` 使用既有 v0 类型；新 Scene identity、
source-closure digest 和 Provider import identity 分别记录。v3 scalar joint axis 被投影到 MJCF 后由 public importer
实际导入；Frame、Joint endpoint/transform/axis 与 actuator resource 映射须逐项吻合，否则 materialization 失败。
Reset realization tolerance 在 reset 返回后、首个 rollout step 前执行。

真实 microprobe 使用 A05 v3 Scene mapping、Panda Menagerie MJCF source closure 和既有 procedural square-peg
source，在 GeoPhys `main` `4436787e9cb85ce519506a2a9af86d1eeec9de2d` CPU 上运行。通过同一个 candidate Artifact 和
同一个 ResetSample，将 `panda-main/joint1` 的 canonical axis 改变后重建 Scene，reset readback 仍满足 tolerance，
`panda-main/link1` 的实测姿态变化 `0.246226`；因此新 Scene 输入确实影响 Provider realization。Panda 的独立 source closure
记录了 68 个依赖文件；procedural peg 的生成 source bytes 和 closure digest 单独记录，并将其生成的 body 投影进组合
MJCF root。public importer 返回 12 bodies、83 shapes、9 joints、8 actuators、
8 transmissions、3 constraints；public rigid model 建立 24 个 collision geometries、8 actuators、9 qpos/DOF。

Canonical v3 当前没有几何、惯量、接触、约束或 transmission 字段，因此这些属性在 Canonical mapping 中仍标为
`SOURCE_RETAINED`。其中 MJCF 几何/惯量/约束/transmission source bytes 被当前 public importer 读取并进入公开 IR 或
solver description；这不等于它们已经成为可移植的 Canonical contract。接触响应没有被本 probe 验证。映射报告按
`CANONICAL_REPRESENTED`、`SOURCE_RETAINED`、`APPROXIMATE`、`UNSUPPORTED` 分列，不把 Source Retained 冒充语义执行。

有界验收与负例位于 `task_env/diagnostics/tasks/test_phase_ii_d01a_scene_materialization.py`：5 passed，覆盖
真实 GeoPhys main reset/首步、同 ResetSample 的 axis variant、缺 Frame/Joint/Geometry、source-closure 不匹配、
超容差和 malformed source。Evidence receipt 保存在被忽略的
`workspace/maintenance/phase_ii_d01a_main_20261020/d01a_microprobe_receipt.json`。该结果不声明 MuJoCo/第二 Provider、
Controller/action、contact behavior、Task success、D01b、Task Harness 或 Qualification 已通过。

#### D01b bounded vNext two-Provider receipt (2026-10-20)

D01b 在 `codex/phase-ii-c` 的 C01b 后续实现中完成有界接线，没有改写冻结的 TaskArtifact v0 identity/codec，也没有
新增 Runtime、TaskEnv、Provider 或 Scene manager。`TaskArtifactV1.validate_scene()` 校验精确 Scene schema/id/hash 与
显式 legacy Frame/Joint bindings；既有 `sample_episode_reset_plan()` 接受 v0/v1 Artifact，但仍只产出现有
`EpisodeResetPlanV1` 和 provider-facing `ResetSample-v0`。`RuntimeSession.materialize()` 对 v1 进一步核对 Scene、Role
Task Source identity、单 RobotInstance、scalar reset/state 字段和 native source names；`reset_plan()` 在执行 provider
reset 前核对 Artifact/TaskSource/Scene identity，继续使用既有 measured-state tolerance gate。

MJCF scalar-axis projection 从 GeoPhys bridge 移至现有 provider-neutral `RuntimeSource` owner，并由 GeoPhys 旧导入路径
重导出以保留兼容。MuJoCo 现在将相同 canonical Scene 投影应用到其 XML string，按 XML 中明确引用的 asset 文件构造
有界 VFS bytes，并在 native build 前重算/核对 canonical source-closure digest，再走 `MjModel.from_xml_string()`；构造后核对
runtime Frame、Joint parent/child body、Joint kind 和 axis。
不使用 Provider 私有状态做验收。MuJoCo native import/cache key 不公开，因此 Evidence 记录包版本、canonical source closure
和实测状态，不伪造 cache identity。

真实范围固定为 A05 `scene-definition-v3` Panda RobotInstance + procedural static square peg，在 GeoPhys
`4436787e9cb85ce519506a2a9af86d1eeec9de2d` CPU 与 MuJoCo `3.8.1` CPU、`p1_2_scalar_cpu_v0` profile 上。
每一个确切 v1 Artifact/Scene 只生成一个 Role/Reset plan，并将同一 ResetSample 交给两 Provider；两者均在首个 step
之前通过 joint readback gate。GeoPhys 最大关节误差为 `5.96e-9`，MuJoCo 为 `0`；ResetSample 没有 free-body pose target，
所以 pose error 的 `0` 是空目标集合结果，不作为 pose reset 证据。actual settle steps 为 `0`；每条路线实际 step 一次。
改变 `panda-main/joint1` canonical axis 后，两 Provider 都由同一 Scene 的
v1 Artifact 生成对应 ResetSample，`panda-main/link1` 姿态变化分别为 `0.2462260806`（GeoPhys）和 `0.2462260895`
（MuJoCo）；相同 Scene 上两 Provider 的 link1 姿态差不超过 `6.42e-9`。Scene 改变会改变 TaskArtifact v1 identity，
所以不同 Scene 变体必须使用各自 hash-bound sample；“同一 sample”指同一 Scene/Artifact 下跨 Provider 复用。

负例覆盖两 Provider 上缺少必需 Frame/Joint source map、缺失 Panda mesh、Scene identity 错配、无界 source root 和非零
settle 拒绝。Task Source 使用恰好一个 Panda 与 square-peg role selector；本 probe 不运行 Controller/gripper action，
不评价接触、任务成功、multi-Robot、Renderer、Qualification，也不把 candidate TaskArtifact v1 宣称为 frozen。
Asset declaration identity、68-file Panda source closure、canonical Scene identity、materialized source-closure digest
和 Provider import/cache identity 分别记录。GeoPhys evidence 有 public importer's source-graph/IR hashes；MuJoCo 记录
engine/package version 与 closure digest，但 native cache key 不公开。当前 Canonical Scene 未声明的几何/惯量/约束/transmission
仍保持 `SOURCE_RETAINED`，不是可移植执行语义。

定向实现为 `task_env/diagnostics/tasks/test_phase_ii_d01b_vnext_materialization.py` 的 **6 项**；D01b、D01a、B02、
B04b、C01b、D02b、A04、A05 组合回归为 **40 passed, 0 failed, 0 errors**。本机原始 receipt 位于被忽略的
`workspace/maintenance/phase_ii_d01b_20261020/d01b_vnext_materialization_receipt.json`。这只关闭执行表序号 19 的
有界 S2 microprobe gate，不构成通用 Scene/Asset import、控制、接触、Task Harness 或 Qualification 通过。

### D02 — Typed Canonical State / Requirements / Owner Views（a/b）

- **D02a**：依赖 A02，提前规定 requirements、state type/frame、clock/sample/boundary identity、
  native interval evidence、validity/alias lifetime 和 v0 projections，供 B04a/C01a 使用。
- **D02b**：依赖 D02a/D01a，在既有 runtime/artifacts owner 实现受限 typed projections，
  供 B02/B03/C04/C05c 消费，不反过来等待 C04 才设计必需状态。
- **任务**：在既有 `CanonicalStateView` 上版本化支持 Typed Joint/Frame、Entity-oriented read views、State Requirements、Sampling/Time/Validity；保留旧 scalar state decode。
- **验收**：v0 roundtrip 不变；joint scalar/free-base type 结构测试，frame SI/wxyz/Z-up；同 boundary consumer state 一致；缺失 required contact 不返回零；相同 data 不双写；真实 provider read/release 生命周期测试。
- **真实 Gate**：至少一个 moving free-body 或 spherical-joint probe，检验不同 qpos/qvel 维数、Twist/frame
  与时间。S1 覆盖数学 oracle；S2 证明 adapter 真正执行。跨 step/reset 后 view 失效行为和 Recorder 自有存储可测。
- **Codex AUDIT**：与通用 `RuntimeSnapshot/TaskStateView` 做 owner 对照，不要求两种 session 共享内存 ABI。

#### D02a contract slice (2026-10-20)

在 `task_env.artifacts` owner 中保留 `CanonicalStateView(canonical-state-v0)` 原样，并新增
`CanonicalStateViewV1(canonical-state-v1)`、`TypedJointStateValue`、`TypedFrameStateValue`、
`StateRequirements`/`StateFieldRequirement`、`StateSampleClock`、`StateBoundaryIdentity`、
`NativeIntervalEvidence` 与 `StateViewLifetime`。精确 schema dispatch 由 `decode_canonical_state_view()` 执行；
`project_canonical_state_v0()` 只接受 Scene v2/v3 和调用者明确提供的 legacy name bindings。v0 的 scalar maps
只能转成声明为 scalar 的 JointDefinition；multi-DOF 值、缺少 identity 或未声明 Frame 必须拒绝。

每个可见状态 publication 由 `state_revision` 区分，即使 `control_step` 不变；evaluation clock 必须与该
boundary 对齐。Native evidence 固定每个物理 interval 的 `[t,t+physics_dt)` 起止和 native index，不允许
interpolation 补采样；native 起始 index 是显式 provider clock 值，不从 `control_step × substeps` 推算，以容纳
reset settle 与 native clock offset；interval evidence 另带完整 raw evidence reference。Required/Optional 仅改变缺失处置：
required unavailable 失败，optional unavailable 必须有原因记录，不能把未支持 contact 编成零。typed values
在 canonical view 中只存一次，`joints_for_entity()`/`frames_for_entity()` 返回同一不可变值的只读投影。
`required_capability` 是消费方的 requirement ID，不是 Provider manifest claim；例如当前 v0 manifest 不认识
`actuator_force_query`，所以对应需求在 admission 时必须失败，不能借 D02a 的新字符串扩权旧 manifest。

此切片是 provider-free S1 contract，不改变 `RuntimeSession`、`RuntimeSnapshot`、Provider manifest、Recorder
格式或 native state owner。`StateViewLifetime` 冻结 owned snapshot 可保留、provider alias 必须绑定
materialization/generation 并在 mutation/reset/close 失效的声明；实际失效检查和真实 free/spherical probe 留在
D02b。定向验证位于 `task_env/diagnostics/tasks/test_phase_ii_d02a_state_contracts.py`。

#### D02b bounded typed publication slice (2026-10-20)

在现有 `RuntimeSession`/`_SessionValues` owner 增加 `snapshot_v1()`，并以
`CanonicalStatePublicationV1` 将一个 `CanonicalStateViewV1` 与匹配的 `StateViewLifetime` 绑定；旧
`snapshot()`、`RealizedInitialState` 与 TaskArtifact v0 均保持原样。调用方必须提供与
`RuntimeSource.scene_source.source_id` 完全一致的 Scene identity、显式 Joint/Frame bindings 和
`StateRequirements`。标量值组合 `project_canonical_state_v0()`；GeoPhys/MuJoCo CPU 的真实 free-body
探针通过现有 provider session readback 发布 7D pose/6D twist，明确把线速度变换到 child frame，并验证
跨 provider 的时间、frame、reset episode/state revision 和 step readback。所有输出均为 owned tuple
snapshot；不开放 provider alias，不把 contact 填零，required contact 与 native interval request 失败关闭。

定向证据：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 OMP_NUM_THREADS=1 \\
  OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=GeoPhys/src:. \\
  python -m pytest -q -p no:cacheprovider \\
  task_env/diagnostics/tasks/test_phase_ii_d02b_typed_runtime_state.py
```

在已配置的 TaskEnv Python 3.12 环境中，GeoPhys 与 MuJoCo 两项 S2 free-body projection 均通过；测试另验证
同一 boundary 的重复 consumer read 一致、legacy v0 snapshot、reset 后新 episode identity、close 后 owned view
仍有效，以及现有 `TransitionRecorder` 的内存 observation copy 不受输入 mapping 后续变更影响。该 Recorder
检查不扩展 H5/v1/v2 schema，也不声称 typed state 已持久化。当前明确范围仅限 GeoPhys/MuJoCo CPU scalar/free-base
evaluation-boundary projection；SAPIEN/Genesis、native interval evidence、contact readback、spherical native state
及跨 provider qualification 仍未实现。D02a state-contracts、当前 D01a/B02 integration 与 D02b typed-publication
三个定向文件合计 **14 passed**；GeoPhys Taichi 依赖报告一条上游 `locale.getdefaultlocale` deprecation warning。

### D03 — Visual Materialization / Sync Versioning

- **依赖**：D02b、D01b、D05a；不硬性依赖 selected Solution 的 C05c 迁移。
- **任务**：复用现有 `render` abstraction，构造 Visual Instance refs 与 Render State Projection；Transform/Geometry 更新分别版本化；Renderer 只按需消费。
- **验收**：相同 Canvas 的多个 renderer-consumer 不相互清 dirty；physics step 不变的 pose write 也可触发更新；静态物体不重复重建 mesh；camera capture 不推进 physics；unsupported deformable 明确拒绝。
- **Codex AUDIT**：是否可以在 `CameraRenderSource` 的 static mesh bridge 上**增量扩展**，还是确需受限新 visual binding？不能新建第二个 authoritative scene。
- **复用 Gate**：对照 GeoPhys public ImportedScene/render lowering、Core UI 和 canonical camera 三条路径，
  说明选择现有桥接/组合/新增受限 binding 的原因；不从内部 renderer arrays 取状态补缺口。

#### D03 first bounded intersection receipt (2026-10-21)

本次选择 **EXTEND_EXISTING / COMPOSE_EXISTING**：保留静态三角形 source 和旧 `create_camera_session()`；在现有
Camera source/API 与 MuJoCo adapter 内增加一条精确受限的动态 visual consumer。physics 唯一 authority 仍是
GeoPhys RuntimeSession 的公开 `CanonicalStateViewV1`。新 renderer model 只从现有 `RuntimeSource` 的
Scene-v3 `TaskSceneSource`、source closure 和 entity-qualified binding lowering 构造一次；每次同步只将公开
scalar Joint positions 写到 renderer-owned MuJoCo data，再用 `mj_kinematics`/`mj_camlight` 计算视觉变换，
不执行 `mj_step`、`mj_forward`、Controller 或 Provider state access。MuJoCo renderer 是视觉 consumer，不是第二个物理 authority。

实际 S2 使用 C02b `phase-ii-c02b-position-servo-v1` candidate：GeoPhys CPU（Taichi 0.6.2 x64 CPU），
`panda-main/position-servo-v1` Controller；TaskArtifact `a56b6cbac66bc570c43d38b8eb5a7e3098873cc196015242d3e46df76dd0364c`，
Canonical Scene `047661ff68e18dffa10a8bfe9cabef4e72f397b5280c1da7c7669ebf9e419e6e`，source closure
`aa4ca97bbe3c61b30752ba0dedc6c88a24394f03fe1b53519052d460ff9abc47`。Renderer 是 MuJoCo 3.8.1 native
OpenGL Renderer；实际 context 报告 NVIDIA Corporation、NVIDIA GeForce RTX 5060/PCIe/SSE2、OpenGL 4.6.0
NVIDIA 595.84。GeoPhys physics backend 的 `cpu` 与 Renderer selection 的 `native-opengl` 分开记录；此结果不是软件渲染。
诊断相机复用既有 `CameraGeometry`/RGB contract，固定 world camera、160×120 RGB；peg 在该 Position source 中是静态对象，
本次真实运动证据来自 Panda arm，不声称 peg/object movement。

`DynamicCameraRenderSourceV1` 把每个 Canonical Entity/Joint 映射到 source MJCF Joint 名称，每个 Entity/Frame 映射到
source body，并由已编译 renderer model 枚举到相应 geometry instance names。Source identity hash 同时绑定
TaskArtifact、Scene identity、source identity/closure 与 Joint/Frame names。版本分开记录：

- `geometry_version` 固定绑定 canonical Scene-v3 source closure 和 renderer lowering；本次每个 consumer 的静态几何 build count 为 1，12 个外层区间未重建。
- `publication_version` 使用 `StateBoundaryIdentity.boundary_id`，包括 reset identity、control step 和 state revision。
- `transform_version` 对实体化的 scalar joint positions 与其 Entity-qualified Frame poses 计算 digest；同一步新 revision 可消费同一步的新变换。
- 每个 Camera session 自己保存最后消费的 publication/transform 版本。两个 MuJoCo consumer 的 S1 顺序测试证明 A 消费不会清掉 B 的更新；reset 后两者各自消费新 episode publication。

Frame 对照阈值在运行前固定为位置 5e-4 m、四元数符号不变 L2 1e-3。S2 初始最大误差分别为约
4.94e-8 m 与 2.53e-8；12 个 10 ms outer intervals 由公开 clock 对应 60 个完成的 2 ms native steps。
hand-origin 移动 0.08044 m；以单通道差异大于 1/255 计，RGB 有 327 个变化像素（最小观测阈值 8）。
捕获前后均为 `(control_step=12, simulation_time=0.12 s)`；capture 时 Controller compute、GeoPhys step、
MuJoCo `mj_step`、MuJoCo `mj_forward` 调用数都是 0。Provider step API 被调用 12 次（每个 outer interval 一次）；
native 完成数来自公开 simulation clock 对照，而非把 API 调用数冒充子步数。

定向证据：`test_phase_ii_d03_visual_sync.py` **2 passed**（版本/身份、缺 Frame 映射 admission 前拒绝、同一步变换 publication、
双 consumer、reset、只读 capture/sync、close 隔离）；`d03_visual_sync_s2_probe.py` **D03_S2_BOUNDED_PASS**。
完整 JSON、RGB PNG 与原始日志保存在 ignored `workspace/maintenance/d03_visual_sync_20261021/s2_geophys_mujoco/`。
同一步变换 S1 使用同一 source MJCF 生成并 frame-pose 一致性校验的 canonical-state-v1 fixture；它证明合法新 revision/transform
不会被版本游标吞掉，但不声称 GeoPhys 提供了同一步手工 pose-write publisher。GeoPhys 实际外层控制运动由 S2 验证。

TaskEnv module Skill refresh receipt：mode=`refresh`，更新现有 `geochora-task-env` 的 camera routes，未新建 Skill。
复核了 `task_env.render.camera` 的实现、公开 exports、D03 S1/S2、D01b/D02b/D05a callers/tests 与
[`public-api.md`](../../public-api.md)；分类为 EXTEND_EXISTING/COMPOSE_EXISTING。Skill checker 与
system `quick_validate.py` 均通过；冷启动 route 从 Skill 的 Learner/render owner 表到新 admission 入口，明确写出
GeoPhys CPU × MuJoCo native OpenGL RGB、Scene-v3 scalar-joint 与不支持范围。API/qualification-sensitive 变更仍待维护者 review；
上述检查不构成 D04/D05b 或 Formal Qualification。

本 bounded route 只准入 GeoPhys CPU、Scene-v3 scalar-joint Position source 与 MuJoCo native OpenGL RGB；不允许 free-joint、
缺失/重复 canonical binding 或 closure mismatch。没有扩展 `camera-static-triangles-v0`，没有开启 Depth/Segmentation、
camera attachment/async scheduling、deformable visuals、其它 renderer/physics pairs、双 Entity、完整 D05b resource/pairing admission，
也没有正式 Qualification。D03 本轮首个刚性 articulation 交集可复核；完整 D03/D04/D05b 与 Phase II 保持未完成。

### D04 — Camera Contract / RGB/Depth/Segmentation

- **依赖**：D03、C04、C05a2；沿用 D05a 的 selection/capture identity 版本契约。C05a 的旧证据逐项映射，不重做已有实现。
- **任务**：扩展既有 Canonical Camera Schema、同步 capture、RGB/Depth/Segmentation normalization、metadata/camera frame/quality、低频/async future contract。
- **验收**：landmark projection、depth backprojection、fixed/mounted moving camera same-state-time；sRGB/linear 声明分离；Seg IDs 指向 canonical names；旧 v0 RGB/Depth 兼容；缺 output fail-closed，reset pending frame 不串 Episode。
- **切片策略**：先 RGB/Depth 兼容和动态 capture，再受限 segmentation；同 capture 的 mask/label map、
  scene-instance identity 必须一起保存。仅 metadata 正确而物体像素不动不得过关；未完成 segmentation 不标完整 D04。
- **Codex AUDIT**：优先增量扩展 `CameraGeometry`、`ResolvedCameraMetadata`、`CanonicalCameraObservation`，新 schema version 和数据复用路径有明确证据。

#### D04 first bounded RGB/Depth receipt (2026-10-22)

本切片 **EXTEND_EXISTING**：复用 `CameraGeometry`、`ResolvedCameraMetadata`、`CanonicalCameraObservation`、
`DynamicCameraRenderSourceV1` 和 `MuJoCoDynamicCameraSession`。旧 `camera-observation-v0` mapping/hash、旧
`create_camera_session()` 与 D03 RGB profile 不变；新增精确的
`d04_mujoco_native_dynamic_opengl_rgbd_v1` admission/manifest，仍只准入 GeoPhys CPU、Scene-v3 scalar-joint
Position source 与 MuJoCo native OpenGL。没有改冻结 A05 source/fixture，也没有改写 MuJoCo Renderer depth branch。

实际 S2 继续使用 D03/C02b `phase-ii-c02b-position-servo-v1` candidate、同一 TaskArtifact
`a56b6cbac66bc570c43d38b8eb5a7e3098873cc196015242d3e46df76dd0364c`、Scene
`047661ff68e18dffa10a8bfe9cabef4e72f397b5280c1da7c7669ebf9e419e6e`、source closure
`aa4ca97bbe3c61b30752ba0dedc6c88a24394f03fe1b53519052d460ff9abc47`，Controller
`panda-main/position-servo-v1`。Render source 与实际 graphics 仍分别记录：GeoPhys/Taichi 0.6.2 x64 CPU physics；
MuJoCo 3.8.1 native OpenGL Renderer，实测 current GL context 为 NVIDIA Corporation / GeForce RTX 5060 / OpenGL
4.6.0 NVIDIA 595.84。MuJoCo 没有公开 Renderer context handle，因此此设备值只在成功 capture 后从当前 GL context
即时读取并作为诊断事实；不读取 `_gl_context`，不把它当作 device pinning 或 admission 证据。

相机与影像 contract 沿用现有值：optical frame 为 `+X right, +Y down, +Z forward`；
`T_world_from_camera = T_world_from_parent @ T_parent_from_mount @ T_mount_from_camera`；居中 pinhole `K` 由
321×241 resolution 与 vertical FOV 90° 推导，实际矩阵为
`[[120.5,0,160.5],[0,120.5,120.5],[0,0,1]]`；像素坐标采用 image-edge convention、pixel center 为
`(column+0.5,row+0.5)`。S2 的 RGB 是 HWC float32 `[0,1]`；Depth 是 H×W float32、单位 m、沿 optical `+Z`。
MuJoCo 3.8.1 `Renderer.render()` 的 depth 分支已反投影为米制 view-Z；adapter 按 `model.stat.extent` 设置 near/far，
并将 near-clipped、far plane 及 background 归一为 `0.0` invalid。D04 profile 采用 exclusive far plane；旧
`optical_z_m` / `ray_distance_m` 的 inclusive far-plane normalization 保持原样。

两个真实相机均从同一个 Canonical State boundary 构造 capture：fixed world camera `d04-fixed-square-peg-calibration-v1`，
以及父 Frame 明确解析为 `panda-main/hand` 的 `d04-panda-hand-mounted-camera-v1`。Observation 携带现有
`CameraCaptureIdentityV1`，identity 的 boundary/clock/modalities 必须与已渲染 buffer、metadata step/time 一致；它
只作为成功返回 Observation 的数据关联，不单独声称 identity 类型可证明渲染。同步、render、device readback 都没有调用
Controller、GeoPhys step、MuJoCo `mj_step` 或 `mj_forward`。S1 覆盖缺 Frame admission 前拒绝、depth sentinel、RGB/Depth
shape/dtype、挂载位姿、reset 后旧 episode state 拒绝、capture failure 与 sibling consumer/资源隔离；双 consumer 版本游标
另由 D03 S1 复测。

独立几何 oracle 使用**未修改**的 A05 square-peg box（半尺寸 `(0.016, 0.016, 0.06) m`），不用 Renderer geometry buffer
反推预测值。固定相机的 peg-center 投影正好是主点 `(160.5,120.5)`；analytic front-surface Z `1.484000 m`，实测
`1.48399997 m`，backprojection 误差 `3.3e-8 m`。mounted 相机的初始/运动后深度误差分别约 `1.413 mm` / `1.348 mm`，
backprojection 误差分别约 `1.413 mm` / `1.351 mm`；运行前界定的阈值为 depth `2 mm`、backprojection `3 mm`。12 个
10 ms outer intervals 的 public clock 给出 60 个完成的 2 ms native steps。手部移动 `0.08044 m`，fixed/mounted RGB 分别有
1183 / 1165 个变化像素，Depth 分别有 1187 / 15843 个变化像素。父 Frame 外参误差为 0；mounted camera 平移 `0.07990 m`，
fixed camera 外参不变。每个 capture 前后物理 clock 不变。reset 后两路 RGB 与 Depth 均逐元素重现 reset 初帧，同时新 episode
capture identity 改变；旧 episode state 被拒绝。

S1：`test_phase_ii_d04_rgbd_camera.py` **2 passed**；随后 D03 S1、D04 S1、camera/capability legacy pin 与
D05a execution contracts 定向回归 **12 passed**（1 Taichi deprecation warning）；真实 S2：
`d04_rgbd_camera_s2_probe.py` **D04_RGBD_FIXED_MOUNTED_S2_BOUNDED_PASS**。当时的 B04a sweep 有两个测试失败，
但后续兼容性审阅确认是测试把已支持的版本误标为未知：TaskEnv H5/v3 已有 Recorder/structured reader 路径；
canonical trajectory/v1 也已支持，原 case 的 `{}` logical payload 才引发 `TypeError`。未建立生产 reader 缺陷。
测试更正与真 unsupported-version 拒绝证据见下方 D04 compatibility erratum。Skill 刷新已核对 Camera API、dynamic
source/session、公开调用路径、相关 S1/S2 与当前限制；模块 Skill checker 与 `quick_validate.py` 均通过。
cold-start 独立新 Agent 演练未运行，API/Qualification 语义保留 Human review。

receipt、PNG、Depth `.npy` 和原始日志位于 ignored
`workspace/maintenance/d04_rgbd_camera_20261022/`。定向 pytest 日志在 `verification/`，真实 S2 receipt 在
`s2_geophys_mujoco/d04_rgbd_s2_receipt.json`。该 RGB/Depth 首个有界 receipt 当时没有实施或验证 Segmentation；
后续受限 Entity-instance slice 见下方 receipt。该次仍未覆盖 free-joint、Assembly、其它 provider/backend、async
capture、完整 D05b pairing 或 Formal Qualification。

#### D04 compatibility erratum (2026-10-22)

Follow-up inspection corrected the prior B04a failure attribution. The stale TaskEnv H5 test used `v3` as an
unknown version even though `RecorderConfig` accepts `task-env-h5/v3`; the stale canonical trajectory case used
the supported `task-env-canonical-trajectory-v1` file schema with malformed `{}` logical content, so the reader
reported a payload `TypeError` after recognizing the schema. The corrected matrix uses `v99` and checks refusal at
the actual `load_structured_control_records_h5()` typed-reader boundary plus `load_canonical_trajectory()`; the
generic `inspect_trajectory_h5()` remains metadata-only and may report an arbitrary version without decoding it.
Corrected focused result: `test_phase_ii_b04a_legacy_matrix.py` **2 passed**. No production H5 or trajectory reader
defect was confirmed; the earlier diagnostic logs remain as historical evidence and must not be interpreted as
reader failures.

#### D04 bounded Entity Instance Segmentation receipt (2026-10-22)

This slice is **EXTEND_EXISTING**: it adds an exact `D04_ENTITY_SEGMENTATION_PROFILE` and
`dynamic_entity_instance_segmentation_manifest()` to the existing Camera admission/session owner, and versioned
values to `CanonicalCameraObservation`. It uses MuJoCo's public segmentation-rendering methods and native
`Renderer.render()` output; Core maps native geom IDs internally through the existing dynamic source
Frame→renderer Body binding and the source's declared canonical Entity IDs. A non-world geom without exactly one
Entity owner, a non-world Entity bound to MuJoCo world Body 0, an ambiguous body owner, an unsupported native
object type, malformed background, or an unknown geom ID fails closed. Native geometry IDs do not cross the
canonical observation boundary. World-body geometry maps to background.

The output contracts are `canonical-entity-instance-segmentation-v1` and
`canonical-entity-label-map-v1`. The mask is immutable H×W `uint32`; 0 is background and dense positive labels are
assigned deterministically by sorted canonical Entity ID. The label map binds the TaskArtifact and Scene/source
hashes, camera, provider materialization, SceneInstance, episode/reset, exact state boundary/revision/control step/
simulation time, and the exact capture-identity hash. The camera identity declares RGB, Depth, and
`entity_instance_segmentation` together. `CanonicalCameraObservation` rejects a map from another camera,
SceneInstance, Episode, boundary, clock, source, or capture identity. The old RGB/Depth profile remains a separate
route and returns `segmentation=None`; its existing output and identity contract is protected by the D04
compatibility test.

S1: `test_phase_ii_d04_rgbd_camera.py` covers missing/ambiguous body mapping, illegal label 0, mask labels absent
from the map, non-world→world-body mapping, mismatched label-map publication, stale previous-Episode capture,
segmentation admission requiring the co-captured RGB and Depth channels, and old RGB/Depth behavior. The corrected
B04a sweep verifies `task-env-h5/v3` is accepted by the existing recorder contract, a truly unsupported v99 is
rejected at the typed structured H5 reader, canonical v1 remains a recognized schema, and v99 is rejected by the
actual canonical reader. `inspect_trajectory_h5()` is intentionally only a metadata summary. The targeted
D03/D04/B04a/D05a regression was **18 passed**, followed by a final D04 S1 rerun after hardening the world-Body
mapping rule (**3 passed**) and the final segmentation contract case (**1 passed**); each D04 run had one Taichi
`locale.getdefaultlocale` deprecation warning. Existing C05a supported-version read/write cases for generic H5 v3
and canonical v1 also passed (**2 passed**).

Real S2 used the unchanged Position candidate and existing source closure: TaskArtifact
`a56b6cbac66bc570c43d38b8eb5a7e3098873cc196015242d3e46df76dd0364c`, Scene
`047661ff68e18dffa10a8bfe9cabef4e72f397b5280c1da7c7669ebf9e419e6e`, closure
`aa4ca97bbe3c61b30752ba0dedc6c88a24394f03fe1b53519052d460ff9abc47`, source identity
`ed51c2470eb4d1b9dacc60a2a373bf9b75ae8ae32b57089867646df7f23ab41b`, and controller profile
`panda-main/position-servo-v1` (identity `3c8fae3e65515f4a62a0c2ba9c5b09d11e8b67ff724642948371b2539050836e`).
Physics was GeoPhys / Taichi 0.6.2 x64 CPU. Rendering was MuJoCo 3.8.1 native OpenGL; the successful-capture GL
query observed NVIDIA GeForce RTX 5060, OpenGL 4.6.0 NVIDIA 595.84. Device strings are post-capture diagnostics,
not device pinning or admission evidence. GeoPhys gitlink remains `4436787e9cb85ce519506a2a9af86d1eeec9de2d`.
The fixed camera is the versioned diagnostic source
`d04-entity-seg-fixed-occlusion-v1`; the mounted camera is `d04-panda-hand-mounted-camera-v1`, parented to the
declared `panda-main/hand` Frame. No frozen A05 fixture or source closure was modified.

The 100 Hz outer route completed 12 intervals, each with five actual 2 ms native steps (60 total); hand-origin
displacement was `0.08666 m`. Fixed and mounted captures changed RGB/Depth/mask by respectively 2251/2154/913 and
1171/15010/754 pixels. The fixed camera pose stayed constant; the mounted pose followed its parent by `0.08652 m`.
An independent ray/OBB calculation for the existing square peg found 12 pixels whose label changed from
`square-peg-instance` to nearer `panda-main`; analytic peg surface optical-Z was `1.464745 m`, while captured
foreground Depth was `0.827117 m`. This is visual occlusion evidence, not a contact-force or task-success claim.
Capture instrumentation observed zero Controller compute, Provider step, `mj_step`, or `mj_forward` calls.

For fixed and mounted cameras, reset reproduced the initial uint32 mask element-for-element while producing a new
Episode/SceneInstance and capture identity; stale pre-reset state was rejected. The mask `.npy`, label-map JSON,
and capture-identity JSON were written and read back for both cameras at initial, moved, and reset boundaries
(six captures); disk dtype, values, mask checksum, label-map identity and publication hashes matched. Receipt,
masks, maps, RGB/Depth diagnostic files and S1 logs are in ignored
`workspace/maintenance/d04_entity_segmentation_20261022/`.

This passes only the bounded Entity **instance** mask slice for this Position source/provider/backend/camera
intersection. Semantic categories, links, free-joints, Assembly, other provider/backend pairs, async capture,
resource/device qualification, full D04/D05b, and Phase II remain unsupported or unverified. No production reader
defect was found; no D05b work was started.

### D05 — Renderer Selection / Pairing Integration（a/b）

- **D05a**：依赖 C01a/A02，提前交付 provider/backend/profile/device selection、
  per-camera overrides、manifest/capture identity 和 ExecutionSpec 版本策略，供 C05a/D03 使用。
- **D05b**：依赖 D05a/D04/C01b，执行实际 Pairing admission/materialization/sync/capture、
  native dependency 和资源失败检查；完整 task/provider/renderer/geometry/outputs/time/source 明确。
- **验收**：非法组合/缺 NativeDeps/输出模态、临时资源泄漏均被检测；至少确定一个**已实现的真实在线 Camera 交集**并给出完整 task/provider/renderer/geometry/outputs/time/source/evidence；如果目标是证明跨独立 Provider 组合，应包含 `physics_provider != renderer_provider` 的真实 route，否则只能标记为 interface-ready/accepted-deferred，不能称 complete independence。
- **Codex AUDIT**：列出当前 GeoPhys/MuJoCo/rasterizer/Flora/CameraSource 的真实组合状态和资源/许可依赖，建议先完成**最小的异名 Physics×Renderer 组合**；不把 fake Flora 测试算作 Native Qualification。
- **退出规则**：首选 cross pairing 无真实 Evidence 时 D05b 为 blocked/accepted-deferred，不能将整个父目标
  或完整 independence 标完成。接口可读、同名 native capture 通过和独立动态 pairing 通过分别报告。
  唯一切片顺序见 [执行表](05_Architecture_Review_and_Execution_Order.md#3-切片依赖与推荐执行顺序)。
  单一真实 cross-provider pairing 可关闭其有界交集 gate；不要求本轮扩展到完整 Env policy observation、Recorder、任意 provider/backend 或 Qualification。

#### D05a static contract delivery (2026-10-20)

`task_env.artifacts` 现在有 `ExecutionSpecV1`、`RendererSelectionV1`、`CameraRendererOverrideV1` 与
`decode_execution_spec()`。没有 `schema_version` 的 mapping 仍交给原 `ExecutionSpec` strict codec；只有
`execution-spec-v1` 才进入新 codec，未知版本/字段拒绝。v1 区分 Physics provider/backend/profile/device 与
Renderer provider/backend/profile/device；每 camera override 是完整选择，未覆盖 camera 才用显式 default，绑定
Scene camera ID 集合时 duplicate/dangling ID 失败。旧 provider-capability-v0 mapping 不变，仅增加其 exact mapping
`identity_hash`。新静态选择可表达独立 Physics × Renderer，但没有给组合 admission。

既有 `CameraRenderSource.capture_identity()` 生成 `CameraCaptureIdentityV1`，绑定 TaskArtifact hash、
CameraGeometry/source identities、ExecutionSpec/renderer selection、实际传入的 Provider manifest exact identity、
canonical state boundary 与 evaluation clock、capture modalities。该值是 planned request identity，不是 capture
receipt；v0 manifest 没有 device/runtime identity 字段，设备解析仍是 D05b admission/materialization 工作。
`RuntimeSession.materialize()`、`render_manifest()`、`admit_render()`、`create_camera_session()` 与其
strict same-provider gate 未改变。D05a 只通过 provider-free S1 contract 验证；不声称 native cross pairing、真实
device realization、共享 session 生命周期或 camera pixels 已验证。

定向证据：`task_env/diagnostics/tasks/test_phase_ii_d05a_execution_contracts.py` 与
`test_phase_ii_b04a_legacy_matrix.py`，运行于 TaskEnv Python、`PYTHONPATH=GeoPhys/src:.`；13 passed。
其中显式断言 v1 selection 不能进入当前 `admit_render()`/`create_camera_session()`，legacy 同 Provider
准入仍成功、异名 Physics×Renderer 仍在 native construction 前拒绝。

#### D05b bounded cross-provider pairing receipt (2026-10-22)

**Bounded result: S1/S2 passed for one exact online Camera pairing; the D05b parent Goal remains partial.**
This is `COMPOSE_EXISTING`: no production Runtime, TaskEnv, Provider, Camera, Renderer, or Recorder owner changed.
The diagnostic path builds the existing `phase-ii-c02b-position-servo-v1` candidate through
`SelectedReferenceEnv.from_position_candidate()` on GeoPhys CPU; its normal selected lifecycle materializes the
existing controlled `RuntimeSession`. It converts that actual `RuntimeSource` to `DynamicCameraRenderSourceV1`,
then calls `create_dynamic_camera_session()`, whose existing owner performs `admit_dynamic_camera()`, projects the
reset `CanonicalStateViewV1`, lowers the existing Scene/source closure, creates one MuJoCo renderer-only model per
camera, consumes typed state via `sync_state()`, captures `CanonicalCameraObservation`, and releases resources through
each session's `close()`.

Exact identities: TaskArtifact `a56b6cbac66bc570c43d38b8eb5a7e3098873cc196015242d3e46df76dd0364c`; Scene
`047661ff68e18dffa10a8bfe9cabef4e72f397b5280c1da7c7669ebf9e419e6e`; source closure
`aa4ca97bbe3c61b30752ba0dedc6c88a24394f03fe1b53519052d460ff9abc47`; dynamic source identity
`ed51c2470eb4d1b9dacc60a2a373bf9b75ae8ae32b57089867646df7f23ab41b`; Controller
`panda-main/position-servo-v1`, identity `3c8fae3e65515f4a62a0c2ba9c5b09d11e8b67ff724642948371b2539050836e`.
Physics is GeoPhys/Taichi 0.6.2 x64 CPU. Renderer is MuJoCo 3.8.1 native OpenGL, with an observed post-capture
NVIDIA GeForce RTX 5060 and OpenGL 4.6.0 NVIDIA 595.84. The GL strings are diagnostic observations, not device
pinning or admission criteria. The GeoPhys gitlink remains `4436787e9cb85ce519506a2a9af86d1eeec9de2d`.

`ExecutionSpecV1` identity is `1662901cdfc8ad75277a0d0a8bf539ab7b165bb394efa118a1535b8347f0c530`.
The fixed world camera `d04-entity-seg-fixed-occlusion-v1` resolves the declared renderer default; the mounted
camera `d04-panda-hand-mounted-camera-v1` resolves its explicit per-camera override. Both capture identities report
the same exact admitted selection (`mujoco` / `native-opengl` /
`d04_mujoco_native_dynamic_opengl_entity_instance_segmentation_v1`, selection hash
`6a3dd18fc407f29111406780f2677b327a102faf5afc58f33aaf98e606133723`) because it is the only selection currently
admitted for this intersection. The actual Renderer manifest identity in the returned capture identity is
`678a853e1b3bc70eef9558a63f90ec71a8fd12d0d6553c4accdf9f9199ce9682`. The override origin and effective selection
were both recorded. Its parent selector `hand` resolves uniquely to the existing canonical Frame
`panda-main/hand` and native source body `hand`.

The real run completed 12 × 10 ms outer intervals, each with five 2 ms native steps (60 completed steps from the
public clock). The hand moved `0.08666 m`. Fixed/mounted RGB, Depth and mask changed respectively 2251/1171,
2154/15010 and 913/754 pixels. Six successful initial/moved/reset captures were written and read back; every
capture identity matched its own sync publication, evaluation boundary, SceneInstance and GeoPhys materialization.
The reset created a new episode/materialization identity and reproduced the same reset outputs; old-episode state
was rejected. Capture instrumentation recorded zero Controller compute, GeoPhys provider step, `mj_step`, or
`mj_forward` calls. Two independent camera consumers each built static geometry once and each called native
`Renderer.close()` once. S1 also injected wrong selection/provider/backend/device, missing RGB/Depth requirements,
wrong source/Frame/publication, absent MuJoCo package, post-allocation constructor failure, sync failure and capture
failure. Invalid requests produced no CameraObservation and no physical/Controller advancement; a failed consumer
did not prevent its sibling from capturing, and repeated session close did not repeat its Renderer close. The
receipt intentionally does not require process-wide GL allocator memory to reach zero.

Targeted command results: `test_phase_ii_d05b_pairing_integration.py` **3 passed**; combined D05b/D05a/D04/D03/B04a
regression **21 passed**, one Taichi `locale.getdefaultlocale` deprecation warning. The final real receipt records
Core `ab73f78af39601ce55fc21f85160fffcbc209520`, GeoPhys
`4436787e9cb85ce519506a2a9af86d1eeec9de2d`, Python 3.12.14, Taichi Forge 0.6.2 and MuJoCo 3.8.1. The receipt,
raw capture files and probe stdout are under ignored
`workspace/maintenance/d05b_pairing_20261022/s2_geophys_mujoco_final2/` and
`workspace/maintenance/d05b_pairing_20261022/s2_d05b_probe_stdout.log`; the final S1 log is
`workspace/maintenance/d05b_pairing_20261022/s1_d05b_pytest_final.log`.

**Consumer boundary:** these captured `CanonicalCameraObservation` values are currently consumed directly by the
diagnostic probe. Generic `BaseTaskEnv` can publish configured RGB/Depth leaves through its separate existing
`CameraObservationProvider` and `StateObservationBuilder`, but that route does not instantiate these D05b dynamic
sessions or provide Entity masks. The Position candidate's dynamic camera buffers are not connected to its policy
observation or `TransitionRecorder`; diagnostic file readback is not Environment observation or trajectory recording
evidence. This does not block the bounded pairing S1/S2 gate, but it blocks any end-to-end visuomotor/recorded-data
claim. The minimal follow-up is to connect existing admitted CameraSession outputs through the existing observation
owner with same-boundary RGB/Depth/mask and capture identity fields, then exercise existing TransitionRecorder on
those observation leaves. No parallel renderer or recorder owner is indicated.

This receipt closes only the first bounded GeoPhys CPU × MuJoCo native OpenGL Position/Scene-v3 pairing. It does not
close the full D05b matrix, full D04, Environment policy/Recorder integration, other pairings, D05 qualification or
Phase II.

## D.9 验收矩阵：先确保语义正确，再验证组合性能

| 分层 | 示例 fixture/oracle | 不可误认 |
| --- | --- | --- |
| Structural | Entity/Frame/Joint/Visual ID 对应、必要实体数与 geometry | 不等于物理轨迹一致 |
| Canonical State | wxyz、SI、Typed DOF、时间与只读 view | 不等于 native solver storage 相同 |
| Camera Geometry | analytic landmark projection、depth backprojection、动手眼 Mount | 不要求跨 Renderer RGB pixel-perfect |
| Render Sync | same-step dirty versions、renderer A/B independent last-seen | 不等于完整异步多传感器已实现 |
| Image Buffer | RGB dtype/layout/color encoding；Depth optical-Z；Seg labels | Seg native ID 不可当 canonical ID |
| Pairing | exact provider/backend/geometry/camera/profile 的 admitted sample | 一个 RGB smoke 不构成全部 pairing QUALIFIED |
| Physics Behavior | frozen sample/control stream、可声明的物理等价容差 | 不要求不同 solver 接触轨迹逐点一致 |
| Failure/teardown | wrong mesh/Frame/profile/camera mode 拒绝；close/lifetime | `close()` 不一定释放 process-global allocator |

**测试执行**：S0/S1 契约每 Goal；D01/D02/D03/D04 涉及状态/相机关键更改时 S2；D05 至少 S2，适用的真实 task route 需要 S3；正式 S4 资格需要单独 Human Judge 和完整 Evidence，此阶段不会自动获得。

## D.10 保留但不单独实施的 D4/D5 约束

| 保留编号 | 内容 | 落点 |
| --- | --- | --- |
| D-F1 | Exact/Approximate/Unsupported 的 Feature Mapping、必要精确参数不静默降级 | D01/D02 的 adapter admission/conversion report |
| D-F2 | State/Geometry/Contact/Camera/Controller/Renderer required capability 缺失即拒绝 | C01/D01/D02/D04/D05 |
| D-F3 | 同 Frozen Artifact + 同 ResetSample/paired samples；物理一致性优先 independent oracle/tolerances | D05 的 bounded test；以后 E 扩展 campaign |
| D-F4 | IMPLEMENTED、TESTED_BOUNDED、QUALIFIED 不可混用；Human Judge 才做正式批准 | 既有 Qualification docs / D05 Evidence / 后续 E |

特殊复杂碰撞模型、Friction Cones、Tendon、软体参数按具体 Provider Feature Goal 再设计，不把所有未来物理特性预装进 A–D 的核心接口。

## D.11 可借鉴项目与技术建议

| 项目 | 影响力/活跃程度（定性） | 参考的实际机制 | 不照搬 |
| --- | --- | --- | --- |
| [Isaac Lab `develop`](https://github.com/isaac-sim/IsaacLab/tree/develop) | 大型活跃机器人学习框架；多 Backend 仍持续演进 | [`SceneDataProvider`](https://github.com/isaac-sim/IsaacLab/blob/develop/docs/source/concepts/scene_data_providers.rst)：versions、consumer remap、只读 cache、render output contracts，`BaseRenderer` | Warp GPU array layout、Kit/OVRTX 依赖、实验性类签名 |
| [Gazebo Sim](https://github.com/gazebosim/gz-sim) / [`gz-rendering`](https://github.com/gazebosim/gz-rendering) | 长期机器人系统工程生态；小型渲染子仓库 star 数不能代表实际采用 | Renderer plugins、SceneManager、Camera/depth/segmentation sensors | 整个 C++ ECS/transport/message pipeline |
| [Genesis](https://github.com/Genesis-Embodied-AI/genesis-world) | 高活跃通用具身仿真；多 renderer path 变化频繁 | Transform/Deformable/Particle sync 分离、Rasterizer/Nyx camera pathways | 将未充分资格化的 Nyx 视作稳定所有组合可用 |
| [ManiSkill](https://github.com/mani-skill/ManiSkill)/[SAPIEN](https://github.com/haosulab/SAPIEN) | 广泛用于机器人操作 Benchmark | Camera mounting、shader pack 的 native→rgb/depth/seg normalization | 把 shader variants 当成独立 Renderer Provider |
| [robosuite](https://github.com/ARISE-Initiative/robosuite) + [MuJoCo](https://github.com/google-deepmind/mujoco) | 成熟机器人操作路线 | USD/Omniverse 离线重渲染与在线任务分离、轨迹 provenance | 假设离线 re-render 自动支持闭环 policy camera |

**技术路线推荐**：以 Isaac Lab 的 Scene Data Provider 作为状态同步参考，Gazebo 的 Render Engine 映射作为生命周期参考，Genesis 的复杂几何同步做扩展设计；用 ManiSkill 的 Camera Buffer Normalize 和 robosuite 的独立 re-render workflow 约束数据语义。不“选一个框架照搬所有模块”。

## D.12 Codex 审阅重点与阶段出口

1. `CameraRenderSource` 是静态 world-space triangles：如何升级 Dynamic Link Visuals 又不新建独立 Physics State？
2. 对原生 Provider 的 transform/geometry 读取应优先使用公开 API；如果需要更高效可选 native view，是否存在允许的 public buffer+Lifetime contract？
3. `CanonicalStateView` vNext 如何最小版本迁移；老 `RuntimeSnapshot`/`TaskStateView` 是否无需强制同 ABI？
4. Render State Projection 同步版本号的 Owner 是 Producer 还是 Consumer？同一 control step 中状态变化如何传播？
5. 各 Renderer 需要 GPU/Kit/进程级 allocator 时，Resource ownership/teardown/worker isolation 是否明确？
6. Semantic/Instance/Link Segmentation 的 canonical ID map 在 Scene Variant 重新 Materialize 后如何更新？
7. `ExecutionSpec.render_provider` 当前是 scalar：默认 renderer + per-camera override 如何版本化，不重建无必要的多个 Session？
8. 能否交付一个**受限真实异名 Provider Pairing**，无法交付时精确写出 Blocker，而不是把严格的旧 `physics_provider == render_provider` gate 删除后视为完成？
9. 当前 UI `render_mode`、Camera Obs、Offline Re-render 是否真正分离？

**D 阶段出口**：Canonically authored Scene 可以经有界 Physics Materialization 获取统一 State，并由独立 Camera/Renderer 消费正确身份、几何与时间；Pairing Capability 会明确拒绝不支持的组合，并提供**范围准确的**真实验证。**不要求**实现 D4/D5 的全量算法/资格 campaign，也不在没有 Evidence 时声称任意 Provider 可自由互换。

## D.13 Physical Attachment 与 C02b 恢复边界（2026-10-21，规划）

本次恢复不重开 D01a/D01b/D02b/D05a，不更改其 source closure、Scene identity、reset sample 或历史证据。
C02b 的新位置 Profile 优先复用现有 position actuation 和 Joint/Frame publication，完整消费链无测量力查询时，
不要求先新增 GeoPhys raw-force API。旧 force-aware Profile 的 freshness/initial-force 缺陷继续保留，
不能因新 Profile 通过而追加 `actuator_force_query` 能力声明。

未来 Physical Attachment 消费 [A.9 logical members/attachment intent](01_Phase_A_Core_Object_Model.md#a9-logical-robot-assembly-扩展候选2026-10-21仅规划)，
由现有 D01 Provider materialization owner 处理 mount 对齐、fixed joint、root joint/root articulation 和 collision filter 映射。
必要的 Canonical Joint/Frame/Actuator 均需明确 native mapping；不能让 Renderer、Assembly 或 Controller 复制物理 authority。
不支持的 Provider/组合明确拒绝，不用 Frame parenting 冒充物理连接，也不把多个 independent roots 自动变成 free joints。

该扩展未来至少需要：mount-transform Oracle、根约束无冲突、装配约束稳定性、明确的 self/external collision
过滤范围、reset realization 和 source/mapping identity。一个或多个 native articulations 是受验证的实现选择，
不能因 Isaac Sim 的某个模式存在就假设 GeoPhys/MuJoCo 都支持。拓扑变化需按新 Scene/Env 生命周期审阅，
不得在现行 v3 上原地添加跨 Entity joint、动态 attach/detach 或热切换 topology。

真实多 Entity attachment 当前 DEFERRED，不是 C02b、D03/D04/D05b 的新增硬前置。
P00/P99 的最小双 Entity position-only 隔离施控已有独立的 GeoPhys/MuJoCo CPU bounded evidence，见
[C02b 双 Entity Position receipt](C02b_Dual_Entity_Position_Acceptance.md)。该证据不包含 attachment、跨 Entity joint 或
更广泛的多 Robot 支持；不得以 attachment 后置为由删除 Assembly 与独立施控之间的边界。
如将来正式实施装配，再明确新版本和额外 gate，不追溯授予旧 A03/D01b 收据新能力。

参考：[Isaac Sim Robot Assembler](https://docs.isaacsim.omniverse.nvidia.com/latest/py/source/extensions/isaacsim.robot_setup.assembler/docs/index.html)。
该资料只解释设计借鉴，不证明本仓库任何新的物理或渲染支持范围。
