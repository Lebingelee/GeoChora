# Phase D — Physics / Rendering Independence：架构、代码实施与验收（Codex 草案）

> **PROPOSED / 需 Codex Audit 与维护者确认；不是现有多 Provider/Renderer 资格声明。**  
> 编制基准：2026-10-19，`main` HEAD `f292df149f41520b484ff27cf2ff78a584903013`，发布 v1.1.0。  
> 总体蓝图：[`00_Phase_II_AD_Implementation_Blueprint.md`](00_Phase_II_AD_Implementation_Blueprint.md)；A/B/C 输入见相邻阶段文件。

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
| [`task_env/assembly/compiler.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/assembly/compiler.py)、`assembly/references.py` | 有界源与具名 task scene/source mapping | 仍含明显 MJCF/task-specific 组合，非通用 Canonical Scene materializer |
| [`task_env/runtime/sessions/api.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/runtime/sessions/api.py) | `RuntimeSession`, `provider_manifest`, `materialize`；GeoPhys/MuJoCo/SAPIEN/Genesis adapter | 适配器存在不代表同等支持或 selected-task qualification |
| [`task_env/artifacts/contracts.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/artifacts/contracts.py) | `CanonicalStateView(canonical-state-v0)`、`ExecutionSpec`, Manifest/Admission | v0 标量 joint maps，不代表 floating-base typed state 全支持 |
| [`task_env/observations/canonical_camera/contracts.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/observations/canonical_camera/contracts.py) | `CameraGeometry`, `ResolvedCameraMetadata`，Mount/Optical、Step/time、FOV/K | 当前 `camera-observation-v0` 仅明确 RGB/Depth、post-control-step |
| [`task_env/observations/canonical_camera/images.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/observations/canonical_camera/images.py) | RGB/Depth strict normalize + `CanonicalCameraObservation` | Segmentation 与 async capture meta 未通用实现 |
| [`task_env/render/camera/source.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/render/camera/source.py) | `camera-static-triangles-v0`；World-space 静态 closed triangles | 不可当成动态 Articulation/Deformable 完整 Visual Scene |
| [`task_env/render/camera/api.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/render/camera/api.py) | `CameraRenderSession` 与 `admit_render` | 当前 `physics_provider == render_provider` 且 GeoPhys/MuJoCo CPU/native pairing；不支持任意组合 |
| [`task_env/render/base/`](https://github.com/Lebingelee/GeoChora/tree/main/task_env/render/base) | `RenderBackend` registry 与 `UiRenderProvider` 等独立 contract | UI presentation 与 Camera Sensor 不能混为一体；Flora fake tests 不是 native Flora acceptance |
| [`task_env/runtime/sessions/control.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/runtime/sessions/control.py) | Panda specific controlled session capabilities | 特定 Panda joint/actuator 数量约束，不等于通用 multi-robot control |

**现有文档的硬性 Convention**：SI；right-handed Z-up；Quaternion wxyz；`T_world_from_camera` 与逆；Optical Frame +X right、+Y down、+Z forward；Depth `float32` metre **optical-Z**、0 invalid；RGB HWC/CHW 和 dtype/range 必须声明。先保护，后版本化扩展；不随 Renderer 私有约定改变。

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
    default: {provider: rasterizer, profile: fast}
    cameras:
      wrist: {provider: rasterizer, profile: fast, outputs: [rgb, depth]}
      overview: {provider: other_renderer, profile: quality, outputs: [rgb]}
```

一套 Scene，不是多个 Physics；多个 Camera 可选择不同 Renderer。但 Phase II 实际可用 pairing 由 manifest/admission 逐一决定，不能由配置解析成功推断支持。`other_renderer` 是示意，不代表当前注册。

### D.7.2 Admission 不是一个布尔值

推荐四个 Gate（复用 C3 与现有 manifests，不新建 Qualification 体系）：

1. **Static Requirements**：Task/Scene/Controller/Camera 声明所需几何、Frame、time、output capabilities。
2. **Pairing Capability**：Physics × Renderer × Backend/Device/Runtime × Scene Geometry × Camera outputs；检查互斥依赖（例如 Kit/非 Kit）；显式 manifest/version/known unsupported。
3. **Materialization Validation**：真实链接 frame/render nodes、材料/纹理/geometry、camera intrinsics；只可声明近似的字段记录 approximation report，必须项失败。
4. **First Runtime Realization**：reset→同 State Boundary→sync→capture，验证 Shape/Dtype/K/Pose/Depth/Segmentation ID 和“不推进 Physics”；标记已实现/有界测试/资格三种独立事实。

能力不应只用 `GeoPhys+RendererA=True` 声称；至少声明具体 `Task/Geometry/Modalities/Timing/Profile`。**当前 `CameraRenderSession` 严格同名 physics/render provider，不可因本路线而误报已解耦。**

### D.7.3 Resource sharing 与异步

相同 Renderer 实例配置可以共享 Render Scene 和 Renderer-native caches，不同 Camera 仍有独立 Calibration、Capture Schedule、Buffers、Pending Events。不同 Renderers 可能各自复制 Visual Scene/GPU data；允许 Renderer Cache 重复，禁止 Physics Authority 重复。没有独立 GPU/多线程 lifetime Evidence，不强制在 Phase II 同时运行所有 Renderer。

在线 Environment Camera 与离线 Trajectory Re-render 共享 Scene/Camera/State 的语义，但独立生命周期；后者可以使用 C 已记录 Canonical State Sequence，不能假装它运行了真实 Physics Step。完整离线数据生产 Harness 归 E。

## D.8 五个 Implementation Goals

### D01 — Physics Scene Materialization / Binding

- **依赖**：A05、B04、C01。
- **任务**：现有 `assembly`/`RuntimeSession` 上建立 Canonical Scene→Provider Source/Native Handle 的有界路径；单/双 Entity 可分辨，Exact/Approximate/Unsupported mapping reports；支持 Scene Instance/Reset Variant 生命周期。
- **验收**：命名 Entity/Frame 在 GeoPhys/MuJoCo 支持的限定任务中都能解析；缺必需 Joint/Frame/Geometry fail-closed；相同 Frozen ResetSample realized-state tolerance 检查；无隐式重新采样或 private solver 访问；S2 真实 microprobe。
- **Codex AUDIT**：确定现有 MJCF-centered `assembly/compiler.py` 能复用的构造边界，以及哪些 conversions 必须 deferred；不得以“架构完整”名义重写 solver。

### D02 — Typed Canonical State / Requirements / Owner Views

- **依赖**：D01 与 C04 的现有 view 兼容规划。
- **任务**：在既有 `CanonicalStateView` 上版本化支持 Typed Joint/Frame、Entity-oriented read views、State Requirements、Sampling/Time/Validity；保留旧 scalar state decode。
- **验收**：v0 roundtrip 不变；joint scalar/free-base type 结构测试，frame SI/wxyz/Z-up；同 boundary consumer state 一致；缺失 required contact 不返回零；相同 data 不双写；真实 provider read/release 生命周期测试。
- **Codex AUDIT**：与通用 `RuntimeSnapshot/TaskStateView` 做 owner 对照，不要求两种 session 共享内存 ABI。

### D03 — Visual Materialization / Sync Versioning

- **依赖**：D02。
- **任务**：复用现有 `render` abstraction，构造 Visual Instance refs 与 Render State Projection；Transform/Geometry 更新分别版本化；Renderer 只按需消费。
- **验收**：相同 Canvas 的多个 renderer-consumer 不相互清 dirty；physics step 不变的 pose write 也可触发更新；静态物体不重复重建 mesh；camera capture 不推进 physics；unsupported deformable 明确拒绝。
- **Codex AUDIT**：是否可以在 `CameraRenderSource` 的 static mesh bridge 上**增量扩展**，还是确需受限新 visual binding？不能新建第二个 authoritative scene。

### D04 — Camera Contract / RGB/Depth/Segmentation

- **依赖**：D03。
- **任务**：扩展既有 Canonical Camera Schema、同步 capture、RGB/Depth/Segmentation normalization、metadata/camera frame/quality、低频/async future contract。
- **验收**：landmark projection、depth backprojection、fixed/mounted moving camera same-state-time；sRGB/linear 声明分离；Seg IDs 指向 canonical names；旧 v0 RGB/Depth 兼容；缺 output fail-closed，reset pending frame 不串 Episode。
- **Codex AUDIT**：优先增量扩展 `CameraGeometry`、`ResolvedCameraMetadata`、`CanonicalCameraObservation`，新 schema version 和数据复用路径有明确证据。

### D05 — Pairing Config / Capability / Bounded Integration Gate

- **依赖**：D03–D04、C01。
- **任务**：Environment default Renderer + per Camera overrides 配置解析；Provider/Renderer Pairing admission；物理/视觉 Scene Binding 验证；有界真实运行与失败报告。
- **验收**：非法组合/缺 NativeDeps/输出模态、临时资源泄漏均被检测；至少确定一个**已实现的真实在线 Camera 交集**并给出完整 task/provider/renderer/geometry/outputs/time/source/evidence；如果目标是证明跨独立 Provider 组合，应包含 `physics_provider != renderer_provider` 的真实 route，否则只能标记为 interface-ready/accepted-deferred，不能称 complete independence。
- **Codex AUDIT**：列出当前 GeoPhys/MuJoCo/rasterizer/Flora/CameraSource 的真实组合状态和资源/许可依赖，建议先完成**最小的异名 Physics×Renderer 组合**；不把 fake Flora 测试算作 Native Qualification。

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
