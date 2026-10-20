# Phase A — Core Object Model：架构、实施切片与验收

> **STATUS：A01–A05 静态验收通过。** 证据覆盖当前 Canonical Scene 契约、真实来源映射、旧构造兼容和一个冻结 TaskArtifact 的只读兼容投影；不代表 Provider Runtime、Physics Materialization 或跨 Provider 物理等价。
> 当前分支 `codex/phase-ii-a` 与本地 `develop` 同指 `1f2bb912807aa2abfa9ad9ff98100518127f0aa0`；本轮改动尚未提交。
> 总体边界与 20 Goal 依赖图参见 [`00_Phase_II_AD_Implementation_Blueprint.md`](00_Phase_II_AD_Implementation_Blueprint.md)。

## A.0 阶段目的与非目标

**目的**：使 GeoChora 用户能够使用统一的 Asset、Entity、Robot、Scene、Component 和 Frame 模型描述物理/视觉世界，而不用在 Task 代码中直接创建 MuJoCo Body ID 或 GeoPhys 内部对象。对 B 的 Role/Task、C 的 Controller Binding、D 的双 Materialization 提供可复用身份基础。

**不做**：通用全量 ECS；在 Core 中重写 URDF/MJCF/USD 求解器；自建独立 native physics scene；广泛格式无损互转；Phase III 多环境 Batch；Task Harness/自动生成 Task。

**关键共识（来自 A 部分讨论）**：

1. `Asset Definition`、`Entity Instance`、`Provider Materialization`、`Native Runtime Handle` 是四种不同对象。
2. Entity 在 Scene 内具有稳定语义身份；Robot 为特化 Entity；多个 Entity 可引用同一 Asset。
3. Frame/Link/Joint 是稳定可引用的结构元素，但不强制每个 Link/Joint/Frame 都成为 Scene 顶层 Entity。
4. 用轻量 Typed Components（物理、视觉、关节、Frame、传感器等）表达公共事实，**不**实现通用 ECS Scheduler。
5. Scene 是空间/组织/结构容器；Task 的 Goal、Success、Failure 归 B，不属于 Scene。
6. 资产应遵循 `external format → canonical definition → provider materialization`；Runtime Handle 不泄漏到 B/C/D 的公共对象。
7. Registry UID 表示组件类型，Entity ID 表示实例。保留 `make_agent`；`make_robot` 改名不是本阶段交付前提，无独立价值时不新增 alias。
8. `make_env` 是最终执行 facade，不承担底层资产解析所有权；Scene/Robot 编译不要求启动 Physics。

## A.1 当前实现基线：已有所有者、断裂与边界

| 当前 owner / 路径 | 已知事实（IMPLEMENTED） | A 阶段拟处理的差距（PROPOSED） |
| --- | --- | --- |
| [`task_env/registry.py`](../../../../../task_env/registry.py) | `ComponentRegistry`，`make_agent/make_object/make_scene/make_env` | 按 Entity/Asset/Robot 的稳定身份与对象复用规则扩展；不新造平行 registry |
| [`task_env/environment/protocols.py`](../../../../../task_env/environment/protocols.py) | `AgentComponent`、`TaskObjectComponent`、`SceneBuilderComponent`、`TaskEnvironmentComponent` | 明确 robot/entity/components 继承/组合边界与兼容适配 |
| [`task_env/environment/types.py`](../../../../../task_env/environment/types.py) | `AssetManifest`、`ReferenceSpec`、`TaskCompositionSpec`、`TaskReferences` | 从任务专属声明发展到统一实例/Frame/Reference 规则 |
| [`task_env/assembly/compiler.py`](../../../../../task_env/assembly/compiler.py) | MJCF/任务专用组合，生成 `CompiledTaskScene` | 逐步让组合输入由 Canonical Scene 驱动；不在 A 强制重写 D 的 Physics Materializer |
| [`task_env/assembly/references.py`](../../../../../task_env/assembly/references.py) | 以 name/ID 进行任务引用解析 | 保留功能，升级为 `Entity-qualified` refs；native integer IDs 限制在 adapter |
| [`task_env/robots/`](../../../../../task_env/robots) | Panda、Pendulum 等机器人组件和控制句柄 | 通用 Robot Model/Control Group，不以 Panda 作为唯一 Robot 形状 |
| [`task_env/tasks/worlds/`](../../../../../task_env/tasks/worlds) | 专用 tabletop/classic 场景 | 场景复用、多个机器人/物体实例声明 |
| [`asset/external/mujoco_menagerie`](../../../../../asset/external/mujoco_menagerie) | 仓库中的外部 Gitlink 资产来源 | Asset reference/version/hash；不在 Core 复制第三方大型资产 |

**Codex 必核实**：旧 `make_agent` caller 的实际类型、name→index 映射在 `assembly` 中的生产路径，Scene/XML 构建者是否已经可复用，`asset/` 是否另有外部实际源码。先确定 Owner/CallGraph 再考虑新文件。

### A.1.1 2026-10-20 审阅确认的断点与复用决策

- `TaskCompositionSpec` 拒绝重复 agent/object UID，`resolve_task_references()` 按组件 UID 存储，
  Panda 分支读取全局 `joint1/hand/actuator1`。实例化需贯穿 composition→命名空间→reference map；
  不能只在 YAML 增加 entity_id。依据：
  [types](../../../../../task_env/environment/types.py#L103-L127)、
  [references](../../../../../task_env/assembly/references.py#L190-L273)。
- 已有 [EntityDefinition/WorldDefinition](../../../../../task_env/artifacts/contracts.py#L130-L203)。
  本轮选择 Core artifacts owner 下的不可变 Scene/Entity value contract 作为 vNext 唯一结构权威，
  文件布局由 A01 audit 决定；v0 保留 codec/projection，不维持两套独立可写世界。
  AssetManifest 是来源描述，TaskReferences 是编译后映射，二者不取得 Scene 定义权威。
- [GeoPhys ImportedScene](https://github.com/SCAILab-USTC/GeoPhys/blob/c665ce5028a12bb4d2afe49f05e015fa9b684a39/src/scene/scene_import.py#L296-L363) 已公开 ir、
  capability_report、solver/render lowering；A04 必须先比较组合公开 importer 与新写 parser 的必要性。
  Core 不复制 parser，也不要求其他 Provider 使用 GeoPhys IR ABI。
- 受版本控制的 `asset/` 当前只含 Menagerie Gitlink；`asset/` 本身不是外部 Gitlink，
  不假设那里已有通用 Asset Framework。来源责任见 [Gitlinks](../../../../../.gitmodules)。
- Parser 映射必须保留当前资产所需的 transmission/tendon/equality、惯性参考 frame、contact exclusions
  等语义；不要求全部跨格式支持，但未知必要语义必须拒绝或显式保留为受限 source reference。
  不得用基础 Rigid/Joint 的构造成功掩盖信息丢失。

## A.2 推荐概念模型

```text
AssetDefinition (immutable, versioned, provider-neutral intent)
  ├─ geometry / collisions / inertial description
  ├─ kinematic structure / joints / frames
  ├─ visual geometry / materials
  └─ reference to original source (URI/version/hash/license)
           │ instantiate
           ▼
EntityInstance (unique within one SceneInstance)
  ├─ entity_id, asset_ref, placement
  ├─ components: Physical, Visual, Sensor, Metadata ...
  ├─ Robot specialization: articulation + control_group declarations
  └─ nested link/joint/frame identity graph
           │ composition
           ▼
CanonicalSceneDefinition (entities, frames, lights, cameras, authored relations)
           │
           ├─ B: Task role selection, initialization, semantics
           ├─ C: Controller bindings and Action/Observation planning
           └─ D: Physics/Render materialization
                    ├─ Physics native handles
                    └─ Renderer native handles
```

### A.2.1 Identity 与稳定性

- `asset_id`: 可复用资产**定义**身份，可包括来源 URI、content hash、版本，不因 Scene 中实例数量而改变。
- `entity_id`: 在一个 Scene Definition/Scene Instance 命名域唯一；例如 `robot_left`、`robot_right`、`cube_01`。同一个 Asset 创建两次必须有两个不同 `entity_id`。
- `joint_ref/frame_ref`: 使用 Entity-qualified 路径，如 `robot_left/arm_joint1` 或 `robot_right/hand/grasp_frame`；**不得只以 `joint1` 在 Scene 全局查找**。
- `semantic_role`: 归 B：例如 `grasp_target` 由 Reset Role Binding 解析到某个 Entity，不改变 Entity Identity。
- `native_handle`: 如 MuJoCo `body_id` 或 GeoPhys 内部索引，属于 D Provider Adapter 的生命周期及 mapping，不属于 Task Artifact 身份。
- 更换 Provider 不应更换 Task 定义中的 Canonical Entity/Frame 名字；若 Scene Variant 在 Episode 间改变实体集合，须由 B 的 Variant/Role 机制记录。

### A.2.2 Component 最小集合

| 组件族 | 核心内容 | 边界 |
| --- | --- | --- |
| `Transform/Frame` | Parent frame、固定局部变换、world/root 约定 | 静态 parent 关系，动态状态由 D Physics 提供 |
| `RigidBody/Inertial` | Mass、Inertia、Kinematic/Dynamic intent | 真实 solver 参数映射属 D |
| `Collision` | shape/geometry、enabled、contact material reference | 不能把 native contact kernel 暴露到 Core |
| `Visual` | mesh/material/visibility、renderer-independent reference | 独立于 Collision Geometry，可简化碰撞网格 |
| `Joint/Articulation` | joint type、limits、parent/child link、DOF | Free/Spherical 不强迫标量 qpos/qvel 同维 |
| `Actuation` | controlled joint/actuator scope 与要求 | Action mode 与具体 Controller 归 C |
| `Sensor/Camera mount` | Camera attachment frame/固定相对位姿 | Camera 观测契约在 D3 |
| `Provider Extension` | 显式能力与 namespace 的实现特性 | 非标准字段不得静默注入 frozen Task |

**避免过度抽象**：没有第二套 ECS Query/Update 系统；不创建重复的 Entity Cache owner；`Component` 不承诺任意插件组件都可跨 Provider Materialize。

### A.2.3 Robot 与 Control Group

Robot 是有 Articulation/Actuation 语义的 Entity，而非 `Agent Policy`。

```text
RobotInstance: mobile_manipulator
 ├─ body/link/frame hierarchy
 ├─ ControlGroup: locomotion = {leg joints / relevant actuators}
 ├─ ControlGroup: arm        = {arm joints}
 ├─ ControlGroup: gripper    = {finger joints}
 └─ Sensor Mounts: front_cam, wrist_cam
```

Control Group **只声明“可控制哪些资源”**，不在 A 固定 `cartesian_pose`、`joint_position` 等控制算法；默认 Controller Bindings 在 C 的实例化执行配置 YAML。重叠组可以作为结构定义存在，但 C 的同时启用控制需要唯一 Owner 或显式协调/仲裁。

### A.2.4 Scene 组合

- Scene 具名包含 Entity Instances、World Frames、Light/Camera Definitions 和必要静态参数。
- Scene 中的 `table`, `panda_01`, `cube_01` 不包含“必须先抓取再放置”等 Task Success/Goals。
- 一份 Scene 可复用于多个 Task；Task 的 Role Binding 用 Entity ID 选择对象。
- `Scene Definition` 与每个 Episode 的 `Scene Instance/Resolved Bindings` 要区分：资产配置可固定、Episode 实体选择可变化。
- D1 确定 Physics/Visual 由同一个 Scene Definition 分别 Materialize；A 不实现 Renderer Sync。

### A.2.5 资产导入与导出边界

```text
URDF/MJCF/source assets (owned externally)
       │ Parse/Validate/Normalize
       ▼
Canonical Asset Definition + Source Provenance
       │ Instantiate/Compose (A)
       ▼
Canonical Scene Definition
       │
       └── D: capability admission + provider materialization
```

必须报告：解析失败/未知 Joint/Frame/材质、单位不一致、mass/inertia 缺失或不可确定、unsupported geometry。资产 importer 不假设 MJCF/URDF 必然无损互换；OpenUSD 可作为未来 Adapter/Interchange，不是 Phase II 唯一 canonical 格式。

## A.3 API 与 YAML 体验（**示意**，不冻结类名）

```yaml
# PROPOSED: 单场景多个可控制 Robot；实际 Schema 待 A/B/C Goal 批准
scene:
  id: dual_arm_tabletop
  entities:
    - id: robot_left
      asset: assets/panda@sha256:...
      pose: {frame: world, xyz_m: [0, -0.4, 0]}
    - id: robot_right
      asset: assets/panda@sha256:...
      pose: {frame: world, xyz_m: [0, 0.4, 0]}
    - id: block_a
      asset: assets/block@v2
      pose: {frame: world, xyz_m: [0.5, 0, 0.5]}
```

推荐**公共便利接口**最终具有相同归一化构造路径（并不要求 A 阶段全部一次实现）：

```python
asset = resolve_asset("panda")           # 候选，不是当前 root API
robot = make_robot("panda", entity_id="robot_left")  # 候选；旧 make_agent 先保留
scene = make_scene("dual_arm_tabletop", entities=[robot, ...])
# B Task、C make_env 在后续阶段消耗 scene
```

Codex 必须比较使用当前 `ComponentRegistry` 扩展/适配与引入新 Asset Registry 的收益；原则是**一个 Canonical Owner**。没有充分理由时，不新增公开的 `resolve_asset()` 或同义管理器。

## A.4 代码职责建议（非强制文件布局）

| 当前仓库区域 | 目标职责 | 推荐动作 |
| --- | --- | --- |
| `task_env/environment/types.py`, `protocols.py` | Core 公开身份、组件与 Scene/Robot 语义边界 | `EXTEND_EXISTING` 或按 owner 内聚提取；不要无意义拆类 |
| `task_env/robots/` | Robot 特化、Control Group、Frame refs | 扩展现有 Panda/Robot 组件 |
| `task_env/assembly/` | Asset 规范化、Scene Composition、Canonical refs | 调整产物，不复制 provider materializer |
| `task_env/registry.py` | UID/构造 facade | 保留注册契约，逐步迁移 `make_agent` |
| `asset/` / Menagerie | 资产来源、引用与校验 | 复用 Gitlink/version/hash，遵守外部许可 |
| `task_env/tasks/worlds/` | 已有简单 Scene recipes | 作为兼容参考，后续逐步改以声明式 Scene 构造 |
| `task_env/diagnostics/` 与适合位置的测试 | Reference/Frame/Codec invariants | 复用并补充小粒度测试，不建立 mega-test |

**静态定义不能持有 native mutable state**；同 Asset 多实例不共享实例状态；Runtime Handle 的构造/释放属 D Owner。
逻辑内容 hash 不依赖 checkout 绝对路径；materialized path 留 execution provenance。已有 controller hash
受 absolute meshdir 影响的限制保留，不改历史 identity，见[发布限制](../../../../releases/v1.1/known-limitations.md)。

## A.5 分 Goal 实施路线与验收

### A01 — Asset Definition / Entity Instance / Identity

- **依赖**：P00 Baseline。
- **Owner 决议**：在现有 `task_env.artifacts` strict immutable contract/codec 中增加 `AssetDefinition`、`EntityInstance`、`SceneDefinition`；不新建 Asset Registry、Runtime 或 provider loader。`AssetManifest` 仍提供 assembly 使用的本地 source paths，`ReferenceSpec` 描述编译后 native 名称，`TaskCompositionSpec` 组合注册组件，`TaskReferences` 保存编译后的运行时映射；它们均不拥有此 Scene identity。TaskArtifact `world-v0` 保持原样。
- **A01 schema v1 范围**：asset identity 由 `(asset_id, asset_version)` 表示，附稳定 source URI、可选 source revision/source SHA-256/license；绝对本地路径、`file:` URI 和 parent traversal 拒绝。`EntityInstance.entity_id` 在单一 Scene 内唯一，并引用精确的 asset id/version。Scene 只列出被实体引用的资产，且以 ID 排序后确定序列化/hash。相同 Asset 可由多个 entity 引用；新增/重命名 entity、scene、asset declaration 或 provenance 都会改变 Scene identity hash。该 hash 是声明内容 hash；可选的 source SHA-256 只记录来源摘要，不能证明 importer 实际消费了对应 bytes。
- **边界**：v1 只承载 identity 与 provenance，不含 geometry、pose、components、Frame、Registry 映射或 native handle。没有物理量，因此单位/DOF 校验归 A02。A04 才把本契约与 AssetManifest/source importer 连接，并检查实际来源 bytes；本 Goal 不读磁盘、不导入 Physics、不执行 provider 构造。
- **产出**：typed identity values、严格 mapping codec、独立 Asset/Entity/Scene roundtrip/hash fixtures、与 `world-v0` 的兼容证明。
- **验收**：同 Asset→两个不同 Entity IDs；重复 Entity ID、重复 asset id/version、未声明资产引用、未使用资产、未知字段/版本、非法或机器本地 source reference 拒绝；声明顺序变化不改变 Scene hash；实体/场景/资产身份变化改变相应 hash；后续修改输入 mapping 不改变已构造值；不加载 Physics/provider；旧 `make_agent`/`make_object` 导入通过；现有 PickCube/NutAssembly `world-v0` Artifact hash 不变。
- **终止条件**：如需修改 Menagerie Gitlink、复制 Provider importer 或不能保持已有 Reference ID，先 `REVISE`；不把 `asset/` 本身误作 Gitlink。
- **兼容演进**：A02 若加入 structure/components，必须给新结构明确 schema version 和显式旧值投影；不能在 `world-v0` 增字段、复用其 hash 或让 v1 忽略未知字段。

#### A01 验收收据（2026-10-20）

- **结果**：`PASS — static identity contract`；满足进入 A02 的门槛，不授予 Runtime/provider 能力或 Qualification。
- **实现**：新增 `task_env.artifacts.AssetDefinition`、`EntityInstance`、`SceneDefinition`；仅从 `task_env.artifacts` 导出，没有增加 root facade、Asset Registry 或 loader。
- **验证**：`test_phase_ii_artifact_identity.py` 与既有 `test_reference_construction.py` 合计 **31 passed**。覆盖版本/字段拒绝、身份 hash/排序、资产引用完整性、mapping roundtrip/防输入突变、旧 factory import、provider-free subprocess，以及冻结身份回归。
- **Frozen 回归**：PickCube `world-v0` TaskArtifact hash=`fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4`；NutAssembly=`99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe`，与基线一致。
- **命令**：`PYTHONPATH=GeoPhys/src:. PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider task_env/diagnostics/tasks/test_phase_ii_artifact_identity.py task_env/diagnostics/tasks/test_reference_construction.py`（在 `workspace/maintenance/phase_ii_a_20261020_A01_004/` 有界运行；2.001 s、峰值采样 RSS 约 105 MiB）。
- **原始记录**：`workspace/maintenance/phase_ii_a_20261020_A01_004/{run.json,stdout.log,stderr.log}`；A01 source digest 清单见同目录 `a01_receipt.json`。
- **失败保留**：前序夹具修正过程中的失败 stdout/stderr 保留在 `_002`，后续修正版本结果保留在 `_003`；最终 `_004` 覆盖加入 Scene schema 负例后的代码并全绿。

### A02 — Component Model / Articulation / Frame Graph

- **依赖**：A01。
- **实现边界修订**：继续扩展唯一的 `task_env.artifacts.SceneDefinition`，以 `scene-definition-v2` 增加静态 Frame/Articulation 结构；保留 v1 identity mapping/hash，不另建 ECS、Robot model、Frame resolver 或 Runtime。暂不添加无消费者的通用 Physical/Visual/Actuation component；Asset 物理/视觉内容归 A04 source importer 与 D01 materialization，控制资源归 C02 binding。
- **Frame contract**：`FrameReference(entity_id, frame_id)` 消除跨 Robot 同名歧义。`authored_fixed` frame 带相对 parent 的 `PoseWorld`；无 parent 表示直接相对 world。`runtime` frame 是无静态 pose 的动态锚点，可对应 free body 或 articulation link，pose 留给后续 D02 state。只允许在完全 authored-fixed 的路径上解析 world pose；以 runtime frame 为 ancestor 时可求 link-local transform，world 结果明确失败。
- **Articulation / Joint contract**：一个 entity 可有多个互不重叠的 articulation tree；每棵包含 root link 与无环连通 joint tree，每个 link frame 恰属一个 articulation。Joint 的 parent/child 是 entity-qualified link frame，joint frame 在 parent/child link 内的两组固定变换完整保留；axis 表达于 joint frame。Joint ID 在 entity 内唯一，不同 entity 可以同名。暂支持 fixed/revolute/continuous/prismatic/spherical/floating 六种常见坐标布局；位置/速度 representation 与数组宽度分别声明（例如 spherical 4/3、floating 7/6），不能把宽度当相等的 DOF 数。
- **产出**：严格 v2 mapping、只读静态 Frame composition、Articulation tree 校验、v1 兼容证明、SOURCE limitations。
- **验收**：World→Base→Hand→Camera Mount 的旋转/平移符合独立 analytical oracle；Frame parent 缺失/成环/跨实体引用、joint topology 错误及未知 schema/字段拒绝；同名 joint 在两个 Robot 实例可共存；joint origin 变化进入 Scene hash；Free/spherical coordinate 宽度按声明校验；runtime link 不冒充 authored pose；不导入 Provider、不做 FK/physics lowering。
- **Source limitation**：A02 不表达闭环约束、transmission/tendon/equality、joint limits 或 actuator control；A04 importer 必须逐项映射、显式保留受限 source reference 或 fail closed，不能静默丢弃。D02a 后续定义动态 link state/timebase/lifetime，本 Goal 的 `PoseWorld` 只描述 authored fixed geometry 与 joint frame geometry。

#### A02 验收收据（2026-10-20）

- **结果**：`PASS — static frame/articulation contract`；静态结构 gate 通过，不表示 Provider materialization、FK、physics runtime support 或 Qualification。
- **实现**：`scene-definition-v2` 在同一 `SceneDefinition` owner 下纳入 `FrameDefinition`、`FrameReference`、`ArticulationDefinition`、`JointDefinition`；v1 mapping/hash 继续由版本专属 codec 保持原样。复用 TaskEnv 既有 WXYZ rotation utilities，不复用 camera owner 或 Panda-specific FK。
- **验证**：`test_phase_ii_scene_structure.py`、A01 contract tests、`test_reference_construction.py` 合计 **49 passed**。包括独立 World/Base/Hand/Camera Mount oracle、fixed/runtime frame 分离、free-body anchor、多 articulation、entity-qualified 同名 joint、6 类 position/velocity layout、joint-origin hash、cycle/missing/invalid parent 与 schema 拒绝。
- **旧身份**：PickCube / NutAssembly `world-v0` TaskArtifact hash 仍分别为 `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4` / `99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe`，同一测试集回归通过。
- **命令**：`PYTHONPATH=GeoPhys/src:. PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider task_env/diagnostics/tasks/test_phase_ii_scene_structure.py task_env/diagnostics/tasks/test_phase_ii_artifact_identity.py task_env/diagnostics/tasks/test_reference_construction.py`（在 `workspace/maintenance/phase_ii_a_20261020_A02_004/` 有界运行；2.208 s、峰值采样 RSS 约 106 MiB）。
- **原始记录**：`workspace/maintenance/phase_ii_a_20261020_A02_004/{run.json,stdout.log,stderr.log}`；source digest 清单见同目录 `a02_receipt.json`。
- **保留限制**：非树/闭环、transmission/tendon/equality、limits、真实质量/几何/视觉和控制 binding 均未实现；后续各 owner 必须映射、保留来源或拒绝。初始 `_001` 失败是负向测试错误地要求现有 `task_env` import 不加载 Panda 专用 kinematics module；修订为只断言本静态路径不加载 Provider/native runtime，最终 `_004` 覆盖多 articulation 与 free-body anchor 全集通过。

### A03 — Robot / Control Group / Scene Composition

- **依赖**：A02。
- **任务**：Robot Instance + ControlGroup 资源声明；Scene 独立组合多个 Robot/Objects/Sensors；保留固定 Frame/可视结构。
- **产出**：单 Panda、双 Panda、arm+hand（可以仅用结构 fixture）三种示例；Entity-qualified references。
- **边界**：双 Robot 的结构与实际 reference resolver 都要测试；首个基线仅承诺其静态契约。后续 C02b 若请求真实双 Robot，须先有 D01b binding 和 S2；没有该证据则明确 unsupported/deferred，不可沿用单 Panda 动力学结论。
- **验收**：两相同 Asset 实例名称隔离、关节资源集合可解析；ControlGroup 指向未知 actuator 失败；同一 Scene 重新解析产生相同 Canonical Identity；静态组合不得触发 native step；**不声称多 Robot 物理执行已支持**。
- **Codex AUDIT Goal**：区分 Scene Entity、Articulation Link、Task Role 的所有权，不复制 B 的 role resolver。

#### A03 实施收敛与验收收据（2026-10-20）

- **Owner / 版本**：在 `task_env.artifacts.SceneDefinition` 中新增 `scene-definition-v3`；v1/v2 的严格字段集合、mapping 与 identity hash 保持原样。没有新建 Registry、robot factory、Task Role resolver 或 Runtime。
- **Robot 身份**：`RobotInstance` 以已有 `entity_id` 作为实例身份，不再创建可与 Entity 分叉的第二个 robot ID；它列出该 Entity 全部 articulation roots。一个 Entity 至多标记为一个 RobotInstance；同一个 Asset 可由多个 Entity 独立实例化。
- **Actuator / Group**：`ActuatorResourceDefinition(entity_id, actuator_id)` 是 entity-local 的资源声明；`ActuatorReference` 是二元结构化引用。`ControlGroup(entity_id, group_id, actuator_refs)` 只声明静态资源集合，并拒绝未知资源、跨 Entity 引用及一个 actuator 被多个 Group 声明 writer。Actuator 不暗示一个 joint、DOF、action width、Controller、命令模式或控制时序。
- **静态解析**：`SceneDefinition.resolve_robot()`、`resolve_control_group()`、`resolve_actuator()` 在 v3 中按完整 Entity/resource tuple 查询。`/`、`:` 可出现在合法名称中；不通过拼接字符串生成键。旧 `TaskCompositionSpec` / `resolve_task_references()` 和当前 Env 的单 Robot 执行边界均未改变。
- **Scene 角色与状态**：Objects/Sensors 仍是通用 `EntityInstance`，以既有 Frame 引用关系组合；不新增 B 的 Task Role 或通用 ECS。Scene authored-fixed placement 与 runtime frame 状态分离；A03 不把 B02 reset sample 或 D02 动态 pose 写入 Scene。
- **结果**：`PASS_STATIC_COMPOSITION`。单 Robot 与双同型号 Robot、arm/hand 分组、对象和相机 Entity、同名/分隔符歧义资源解析、未知资源/重复 writer 拒绝、顺序无关 hash、v1/v2 hash/codec 保留以及 provider/native-runtime-free import 均通过。该静态 Gate 已用于后续 A04/A05 集成审查；不代表 A04 importer、actuator lowering、双 Robot Runtime 或 Qualification。
- **兼容 oracle**：固定 v1 Scene fixture hash `283fcf2766ce4b0eb1eaf83d27856d2b37472f8f46c92605dd587f0f2a81b36a`，固定 v2 Scene fixture hash `af5618c3404100c82c5083fbf59466230d7bc1b7db8b8ba30bae99f145f81467`；PickCube/NutAssembly `world-v0` Artifact hash 由联合回归再次核对。
- **验证**：新增 `test_phase_ii_scene_composition.py`；与 A01/A02 静态契约测试和既有 `test_reference_construction.py` 联合 **57 passed**。运行环境 Python 3.12 GeoChora 环境，单进程 CPU/Address Space 分别限 120s/8 GiB，墙钟 120s；pytest 2.31s、supervisor wall 2.467s。采样未覆盖进程树 RSS，不把该结果用作内存性能承诺。
- **原始记录**：`workspace/maintenance/phase_ii_a_20261020_A03_003/{run.json,stdout.log,stderr.log}`；A03 文件摘要见同目录 `a03_receipt.json`。
- **未覆盖**：无来源 importer 消费证明、MJCF/URDF 解析、资源到真实 native actuator 的绑定、Controller/action shape、双 Entity 施控、物理或渲染验证。A04 仍须复用现有公开 importer/Registry，并逐项报告未表达语义；A03 不授权提前实施 A04。
- **审阅报告**：见下方 A03 Review Report；其静态边界已接受用于后续 A04/A05 集成。

#### A03 Review Report: Static Scope Accepted

**审查结论**：A03 在现有 Core artifact owner 内完成了 Robot/ControlGroup/Scene 的静态组合。v1/v2 identity 与
Frame/Articulation mapping 保留；同一个 Entity-qualified 路径隔离相同 Robot asset 的实例名。当前证据足以接受
A03 静态契约，不足以声称资产 importer、native actuator binding、Controller 或多 Robot 物理执行已实现。
维护者随后授权并完成 A04/A05；该后续工作不扩大 A03 的能力声明。

| 关注点 | 本次判断 | 后续边界 |
| --- | --- | --- |
| Core/Provider 所有权 | `SceneDefinition` 是唯一静态 Scene owner；不复制 Registry、assembly、Provider importer 或 Runtime | A04 只连接现有 owners；真实 materialization 留给 D01 |
| Robot identity | Entity ID 是 Robot instance identity；RobotInstance 列举该 Entity 所有 articulation roots | 一 Entity 一个 Robot；不同 Entity 可复用同一 Asset，暂不表示一个 Robot 跨多个 Entity |
| Actuator/ControlGroup | actuator 是 Entity-local identity，ControlGroup 只声明资源集合；unknown、cross-entity 和重复静态 writer 拒绝 | 不推导 joint/action width，不指定 Controller、command mode、timing 或 native mapping |
| Reference semantics | resolver 用 `(entity_id, resource_id)` 两段式 key；同名与含 `/`、`:` 的名称无拼接冲突 | 旧 `TaskCompositionSpec`/`TaskReferences` 仍有原先 UID 与 global native-name 边界 |
| Entity roles / state | object 与 sensor 继续用通用 Entity + Frame；authored placement 与 runtime pose 分离 | 不复制 B 的 Role resolver；reset sample 归 B02，动态 pose 归 D02 |
| Compatibility | v1/v2 strict mapping/hash oracle、`world-v0` Artifact hash 和旧 factory regression 通过 | v3 仅由 `task_env.artifacts` codec 使用；root facade 和旧 Env behavior 未改变 |

**风险与优先级**：

- **P1 — A03 资源身份尚未绑定真实来源**：当前 actuator declaration 只负责静态引用闭合。A04 必须比对实际 importer
  输出并校验完整 source graph；否则 Scene v3 的静态成功不能解释为资产已导入或资源已可控。
- **P1 — 唯一 writer 规则约束重叠分组**：同一 actuator 不能同时加入 arm 子组和 whole-robot 组。若 C02 需要重叠的
  只读分组，应将资源视图与实际 writer binding 分开建模，并另行版本化审查。
- **P2 — Robot 必须列出 Entity 的全部 Articulation roots**：避免部分列举造成含糊，但一个 Robot 跨多个 Entity
  或 Entity 同时承载多个独立 Robot 尚未表达。当前目标限定一 Entity 一个 Robot；需要扩展时先提交真实消费场景。
- **P2 — 当前生产 reference route 保持旧边界**：assembly resolver 仍按组件 UID/global native names 工作；本轮新增的
  Entity-qualified resolver 只供静态 Scene v3 使用。不得据此宣称 selected Env 能执行双 Robot。
- **P3 — 没有 provider/runtime/render 验证**：这是 A03 的静态 scope 选择，不是本轮失败；native construction、双 Entity
  施控与相机/渲染仍须对应后续 Goal 的正向 Evidence。

**Evidence**：联合回归 **57 passed**（A03 composition、A02 structure、A01 identity、既有 reference construction）；
固定 v1/v2 Scene fixture hash 与 PickCube/NutAssembly `world-v0` Artifact hash 均匹配。A03 pytest 用时 2.31s，
supervisor wall 2.467s，单进程 CPU/Address Space 上限 120s/8 GiB；未采样进程树 RSS。原始 stdout/stderr、run metadata
和 9 个审阅文件的 SHA-256 清单保存在 ignored
`workspace/maintenance/phase_ii_a_20261020_A03_003/`。静态 subprocess 断言未导入 MuJoCo、GeoPhys、solver、scene
importer 或 visualization backend。`git diff --check` 通过。

**A04 实施门槛（历史记录）**：该报告确认后，A04 按下节设计复用公开 importer 和现有 `AssetManifest`/Registry/assembly，区分纯
resolution 与 D01 materialization；逐项报告传动、闭环、limits、惯性 frame、contact exclusions 等语义，实际旧 factory 构造与
unknown/duplicate UID 负例也纳入验收。A04 实施结果见下方记录。

### A04 — Asset Source Mapping / Legacy Factory Compatibility

- **依赖**：A01–A03。
- **任务**：组合现有 Registry、assembly 与公开 Provider importer；首个交集覆盖真实 pinned Panda MJCF 和一个当前 Procedural Asset，URDF 仅在独立 fixture/实际需求成立时纳入。GeoChora 继续作为 GeoPhys 下游的通用机器人执行框架，A04 建立 provider-neutral Canonical Entity/Joint/Frame/Actuator 映射，不把 GeoPhys IR 定为跨 Provider ABI。
- **Source→Imported→Canonical 映射证据**：为每个影响目标 Scene 的来源实体、link/frame、joint 和 actuator 记录 `AssetDefinition(asset_id, asset_version)`、source reference/revision 与稳定 source locator、Imported Structure locator，以及 canonical `entity_id` / `FrameReference` / joint `(entity_id, joint_id)` 或现有 `ActuatorReference`；若 Canonical Scene 没有对应字段，记录无目标及其语义处置，不造占位 ID。保留一对多/多对一关系和来源名称；不得用 provider-native ID 充当 Canonical ID。此逐次导入 receipt 是 Evidence，不另建 Registry、Asset Framework 或公共运行时 API。
- **三种身份分离**：分别记录 **Asset Declaration Identity**（现有 `AssetDefinition.identity_hash`，只标识声明）、**Source Closure Digest**（来源闭包内容身份）和 **Provider Import/Cache Identity**（provider/importer-scoped 身份）。Source Closure Digest 对文件来源按 root-relative logical path 与实际输入字节 SHA-256 确定性排序求值，跨 checkout root 稳定；Procedural Asset 记录 generator/version/规范化参数及其生成内容摘要，不伪造文件 URI。它须来自现有 importer 的同一读取快照；若只能在导入后重算，明确标成观察摘要，不满足“实际消费来源”验收。Provider 身份必须记录实际导出的字段及 importer/version；IR semantic hash、source graph hash 和 cache key 不互相替代。不得把 `AssetDefinition.identity_hash`、可选 `source_content_sha256` 或 GeoPhys `source_graph_hash` 互相代替；若 importer 缺少必要的只读依赖证据，只能在现有 public import owner 增加最小证据出口，不读取其私有 cache manifest。
- **语义处置**：A04 对范围内每项来源语义恰好记录一种处置：`CANONICAL_REPRESENTED`（明确映射到 Canonical Scene 字段，仍不代表 Provider 已执行）、`SOURCE_RETAINED`（由来源闭包及稳定 locator 在 Evidence 中可追溯，但不声称其语义已进入 Canonical Scene/Provider）、`APPROXIMATE`（记录变换、误差/适用范围及影响）、`UNSUPPORTED`（不能表示或保留）。Provider CapabilityReport 的 `SUPPORTED/RETAINED` 不自动决定 Core 处置。必需语义若为 SOURCE_RETAINED、APPROXIMATE 或 UNSUPPORTED，必须由后续消费 Gate 显式接受其受限范围，否则 fail closed；任何未分类或静默丢弃均验收失败。
- **验收**：真实 Menagerie Panda MJCF 在 pinned revision 上核对 root/include/mesh/texture 等实际依赖闭包、身份变化和跨 checkout 稳定性，并为会影响 canonical 结构的来源元素输出上述映射/处置；通过现有 `square-peg-v1` 或 `round-peg-v1` Procedural Asset 路线核对 generator/version/parameters 与生成结构映射；实际构造旧 `make_scene/make_object/make_agent` factories 并核对当前公开 UID/default、manifest 与 reference 输出兼容，同时沿用现有 selected `build_reference()` construction regression 守住另一条旧构造路线；unknown 与 duplicate UID 按现有 Registry/Composition 规则 fail closed。测试须从真实 owners 走通，导入阶段不得访问 provider private solver 或启动 Runtime/step。
- **产出**：既有构造路径与 owner 映射、受限 source-resolution bridge、Source→Imported→Canonical mapping receipt、三种身份及逐项语义处置 Evidence、Panda/Procedural fixtures 和 Legacy Factory Compatibility 报告；不要求把 generic Env 与 selected reference session 合并成一个 Runtime constructor。
- **补充 Gate**：same-content source 在不同 checkout root 得到同一 Source Closure Digest，任一被消费依赖变化可检测；Provider Import/Cache Identity 只作 provider/importer scoped provenance，不作跨 Provider Canonical identity。Registry 不存 native 实例，不为改名强制新增公开 factory。
- **参考经验**：[Isaac Lab 的 typed asset 配置与命名 Interactive Scene](https://isaac-sim.github.io/IsaacLab/main/source/api/lab/isaaclab.assets.html) / [scene construction](https://isaac-sim.github.io/IsaacLab/main/source/tutorials/02_scene/create_scene.html)，以及 [Genesis 的 Morph、`Scene.add_entity()` 与显式 `Scene.build()` 生命周期](https://genesis-world.readthedocs.io/en/latest/user_guide/getting_started/hello_genesis.html)，用于借鉴声明式资产描述、具名实例组合和清楚的构造边界；不复制它们的 Scene Runtime/manager、USD/Kit 类型或 Provider handle。真实物理 materialization 仍属于 D。
- **Codex AUDIT Goal**：判断哪些资产解析应当归外部 `asset/` owner，哪些只能放 Core Assembly；禁止重新造通用 Asset Framework。

#### A04 预审：只读来源图与兼容设计（2026-10-20）

**状态**：已完成代码路径审查和一次公开 MJCF importer 的只读解析；没有修改 A04 生产代码，也没有构造 scene model、启动
Provider Runtime 或执行物理 step。预审形成时没有授权 A04 实施；之后维护者明确要求开始 A04，实施记录见下文。

**当前 owner 与调用路径**：

- [`AssetDefinition`](../../../../../task_env/artifacts/contracts.py#L155) 只持有稳定声明身份与来源字段；[`AssetManifest`](../../../../../task_env/environment/types.py#L43)
  持有 assembly 使用的本地 `mjcf_sources`、`asset_roots` 和版本标签，尚无稳定 source URI、revision 或 source graph digest。
  Panda manifest 使用 Menagerie 本地路径和 `mujoco-menagerie-panda` 标签；当前 Gitlink revision 为
  `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。仓库内 Nut XML、程序生成的 peg 和 PickCube 合成 source 又有不同来源，不能用
  一种路径推导规则假定它们共享来源语义。
- [`ComponentRegistry`](../../../../../task_env/registry.py#L76) 保存组件 class，默认重复 UID 注册失败；factory 在构造边界实例化组件。
  [`TaskCompositionSpec`](../../../../../task_env/environment/types.py#L102) 拒绝重复 agent/object UID。它们是当前兼容 owner，不应被
  Asset Registry 替代。
- [`compile_task_scene()`](../../../../../task_env/assembly/compiler.py#L236) 依次检查 manifest 路径、生成 source、调用 GeoPhys importer、
  构造 scene model、解析全局名称引用并生成初态。因此它不是纯 Asset loader；物理 materialization 应继续留给 D01。
  [`resolve_task_references()`](../../../../../task_env/assembly/references.py#L162) 仍把引用按组件 UID/global native name 保存，Panda 分支保留
  `joint1..joint7`、`actuator1..actuator8` 等既有布局。A03 的 Entity-qualified 静态 resolver 没有迁移此 Runtime 路径。
- 当前有两条不同的生产构造路线，A04 必须分别守住兼容边界。通用 Core Env 由
  [`bootstrap_task_runtime()`](../../../../../task_env/runtime/bootstrap.py#L20) 调用 `compile_task_scene()`，再创建 GeoPhys Runtime boundary；
  选定 PickCube/NutAssembly 则由各自 `build_reference()` 构造 TaskArtifact、`RuntimeSource`、Controller 和 Solution，
  [`SelectedReferenceEnv.reset()`](../../../../../task_env/tasks/reference_env.py#L119) 再通过 `materialize_control()` 创建 session。
  后者不经过 `compile_task_scene()`。A04 的目标应是两条路径复用可验证的 source identity/evidence 规则并分别核对 factory、manifest、
  reference，不应为了“统一”重写 `RuntimeSource`、Task Artifact 或 selected session API。
- GeoPhys 对 Core 的公开入口是 [`scene.import_scene_source()`](../../../../../GeoPhys/src/scene/__init__.py#L1)。[`ImportedScene`](../../../../../GeoPhys/src/scene/scene_import.py#L173)
  暴露语义 `source_graph_hash` 和 `dependency_paths`；逐文件 `content_hash` 位于 GeoPhys compilation-cache manifest，未由当前 package-root
  importer 返回给 Core。[`normalized_source_graph_hash()`](../../../../../GeoPhys/src/scene/compilation_cache.py#L282) 对规范化 IR 求摘要，
 不是完整原始文件字节图摘要；对当前 Panda 路线，它也不是跨 checkout 稳定身份。

**当前 Panda source 的只读证据**：在 Menagerie 当前 Gitlink revision 上，用公开 `SceneSource.mjcf_path()` 与
`import_scene_source(cache=False)` 解析 `franka_emika_panda/panda.xml`。返回 68 个依赖路径（根 XML 与 67 个 OBJ/STL 文件）；IR
含 8 actuators、8 transmissions、3 constraints。约束包括 fixed tendon、joint equality 和 contact exclusion；capability report 将这些
条目标为 `SUPPORTED` by `scene_ir.inventory`。同一报告把 `mjcf.light` 标为 `RETAINED`，并提示在 lowering 前注册 typed extension schema。
MJCF parity report 的 `max_abs_error=0` 只说明该 importer 检查的表示与数值 oracle 一致，不证明 TaskEnv canonical contract 或其他 Provider
保留了这些语义。当前 [`SceneDefinition v2/v3`](../../../../../task_env/artifacts/contracts.py#L429) 没有 tendon、transmission、equality、
joint limits、惯性 frame 或 contact-exclusion 字段；A04 必须按 source→TaskEnv contract 的映射再次分类，不能把 GeoPhys IR 的
`SUPPORTED` 直接记作 Core 已支持。导入后观察到的 68 个依赖文件摘要和 probe metadata 保存在 ignored
`workspace/maintenance/phase_ii_a_20261020_A04_REVIEW_001/a04_mjcf_import_probe.json`（SHA-256
`a11c20c4db909937d0086644ab1b0b591720b6c8186c9d0ce7c017f203a0de91`）；该收据明确标注摘要不是 importer 精确读取字节的证明。

**跨 checkout 探针与来源身份设计决议**：将同一 Panda asset tree 复制到两个不同临时根目录后，公开 importer 返回的 68 个依赖集合、
相对逻辑路径与逐文件字节摘要完全一致；基于“相对路径 + SHA-256”构造的观察摘要也相同（`cc018eef53ac8ec6b67682bf447beb8c02a0d0584500297c3578da3a8d51a23a`）。
但 GeoPhys `source_graph_hash` 与 `ir_semantic_hash` 均因根目录变化而改变。对 IR 规范化载荷做只读差异定位后，至少 `assets[*].payload.file`
仍含绝对路径。反过来，仅给根 XML 追加换行会改变观察字节图摘要，而两个 GeoPhys hash 保持不变。这证明当前 `source_graph_hash`
既不能作为跨 checkout 稳定 Asset identity，也不是完整原始字节图摘要。

A04 上述契约将三种身份分别命名为 **Asset Declaration Identity**、**Source Closure Digest** 与 **Provider Import/Cache Identity**：
`AssetDefinition.identity_hash` 只标识声明，GeoPhys hash 保留为当前 importer 的 IR/cache identity，A04 Source Closure Digest 单独标识
稳定来源下的原始依赖闭包。既有 probe 已证明 GeoPhys `source_graph_hash` / `ir_semantic_hash` 会受 checkout 根路径影响，且不等同于
完整原始字节图；本目标新增的验收规则是把 Source Closure Digest 绑定到 importer 实际读取的快照，并将映射和语义处置记入同一
import Evidence。Procedural Asset 使用 generator/version/规范化参数及生成内容摘要表达来源；不把本地临时文件路径包装成稳定 URI。

**测试缺口与实施切片**：现有 [G5 cache test](../../../../../GeoPhys/test/verification/scene/test_scene_compilation_cache_g5.py#L190)
验证根 XML+mesh dependency path 和 mesh 内容变化后的 invalidation，邻近测试检查 texture/heightfield 的 payload content 去重；现有 MJCF
include fixture 检查解析，但未形成跨 checkout 的完整 MJCF 依赖字节身份验收。本轮只读 probe 已实际通过 PickCube 和 MuJoCo NutAssembly
`build_runtime_source()` 路线构造旧 scene/agent/object factories，并核对 `AssetManifest` 与 `ReferenceSpec`；结果显示 Panda 是外部
MJCF，Cube/peg 是 procedural asset，而 Nut 是仓库内 MJCF 副本。未知 agent/object/scene UID 均以 `KeyError` 拒绝；重复
`TaskCompositionSpec` agent UID 以 `ValueError` 拒绝；独立临时 `ComponentRegistry` 的重复 UID 注册以 `KeyError` 拒绝。这些是只读
探针结果，尚不是受版本控制的自动化测试。A04 首轮应限于有真实调用方的 MJCF；补充根 XML/include/mesh/texture 依赖枚举、修改任一
依赖可检测、两个 checkout root 同内容得同逻辑摘要、正式 factory/manifest/reference 测试和 unknown/duplicate UID 负例。
[`test_reference_construction.py`](../../../../../task_env/diagnostics/tasks/test_reference_construction.py#L1) 已经通过选定 Task 的
`build_reference()` 路径构造真实旧 factories，但 Phase II identity test 对单独 `make_agent/make_object` 仅检查导出 callable；A04 应增加
直接 factory/manifest/reference 断言。正式验收应分别覆盖 generic `bootstrap_task_runtime`/assembly 与 selected
`build_reference`/session 路径；只有修改对应生产 compiler 或 session 时，才为受影响路线增加有界 construct/reset/step 回归。
以上是 A04 实施前的缺口记录；下方实施记录给出本轮已补的静态 source/mapping 与兼容验收。

跨 checkout、factory 和 negative UID 探针的原始结果保存在 ignored
`workspace/maintenance/phase_ii_a_20261020_A04_REVIEW_001/a04_portability_factory_probe.json`（SHA-256
`1144f1672f63d40007eb5bc246c77eaedac1f8bdafbe59c01fc04f853ca75310`）。两份 A04 收据均为导入后/构造期观察证据，不是 Runtime、物理或 Qualification 证明。

**边界**：A04 不新建 Asset Registry、Runtime、Provider loader 或第二套 factory；不复制 MJCF parser，不把 GeoPhys IR ABI 强加给其他
Provider，不将多 Robot 静态组合扩张成现有 Env 的多 Robot 执行能力。上文的 A03 验收门槛是预审建议；维护者随后明确授权 A04，故按该指令
开始实施。若来源字节证据不能证明本次 importer 输入快照，或必要语义无法表达/保留，则该交集应 fail closed 或标为受限 source reference。

#### A04 实施记录：来源闭包、映射与旧 factory 兼容（2026-10-20）

**完成范围**：在现有 `AssetManifest` 增加可选稳定来源引用/revision 与 procedural generator/version/规范化参数；不改变旧构造参数和
本地 source/root 语义。assembly 内仅提供私有 `AssetManifest -> AssetDefinition` 与 root-relative source closure 摘要 helper，未扩展公开
factory、Registry、Asset Framework 或 Provider API。测试通过 GeoPhys public `scene.import_scene_source()` 及 A01–A03 已有 strict
`SceneDefinition v3` 构造 Canonical Scene；不创建 Runtime、不构造 physics model、不执行 physics step。

**A04 静态验收结果**：本 Goal 的来源声明、来源闭包、Canonical 映射、逐项来源处置和旧 factory 兼容验收均在静态边界内通过；这不授予
geometry/materialization 或物理执行支持资格。

**实际证据**：pinned Menagerie Panda 公开导入闭包为 68 个文件；canonical receipt 记录 11 个 source body、11 个 frame、9 个 joint、8 个
actuator 及一条 hand 固定连接派生关系，共 40 条 Source→Imported→Canonical 映射；对 298 条 GeoPhys CapabilityReport semantic entry 逐项
给出 Core disposition。该 pinned `panda.xml` 不含 MJCF include 或 texture 元素，实际依赖闭包为根 XML 和 67 个 OBJ/STL 文件。独立的 root XML
结构清单覆盖 230 个节点，其中 28 个映射到 Canonical 字段，202 个 `SOURCE_RETAINED`；闭包中的
67 个 OBJ/STL 文件逐文件以来源字节保留。GeoPhys retained 的 `extension.light` 保持 `SOURCE_RETAINED`；geometry、transmission、
tendon/equality 与 contact-exclusion 等尚无对应 Canonical 字段的语义仍由来源闭包和 locator 追溯，不冒称已进入 Canonical Scene。相同
bytes 在不同 checkout root 得到相同 closure digest；根 XML 和实际 OBJ 依赖字节变化均被检测。Procedural `square-peg-v1` 记录 generator
参数、生成内容摘要，并映射为一个 canonical Entity/Frame；5 个 XML 节点中 1 个进入 Canonical、其余 4 个明确 source-retained，该 fixture
没有 joint/actuator，Evidence 明确记录为空。旧 `make_agent` / `make_object` / `make_scene` UID、Panda reference、selected scene UID、未知 UID
与重复 UID fail-closed 均有 receipt 和断言。

联合回归 **63 passed**（A01–A04 与既有 reference construction）；命令见忽略目录内的
[`run_metadata.json`](../../../../../workspace/maintenance/phase_ii_a_20261020_A04_001/run_metadata.json)。三份 JSON receipt 与源快照、测试
临时输出保存在 `workspace/maintenance/phase_ii_a_20261020_A04_001/pytest_tmp/`，不会进入 Git：Panda receipt SHA-256
`3113cc75eb498497018316ad7b62a46680152daa1b3cd57efb7e2f894ac4d376`，procedural peg receipt SHA-256
`490f7fda76655566249e5eda5dfa4d2862f7e651b104627b02f9ab6287c2c933`，legacy factory receipt SHA-256
`30451191e41fb5159d1a5b128d3fa39a77f26d08890ccfabbfb0c130d843a383`。run metadata 另记录 procedural source XML 与生成 peg subtree 的文件摘要，
并验证它们与 closure digest / generator content hash 一致。`git diff --check` 通过。

**边界与后续 Gate**：当前 GeoPhys public importer 仍未导出逐依赖文件 consumption hash；本证据通过复制闭包到受控快照、将同一快照交给
importer 并在导入后核对字节来限定本次验证，不能外推为对任意并发可变路径的原子读取保证。Canonical Scene 尚不表示 Panda geometry、质量/惯性、
limits、transmission、constraints 或 light。它们逐项保留来源或标注不支持，任何后续消费须显式设 Gate；近似转换目前没有被引入。真实 Provider
materialization、构造误差与 realization tolerance 仍属 D01a，不由本次静态证据验收。

### A05 — A 阶段集成与保护性迁移

- **依赖**：A01–A04。
- **任务**：审阅 A01–A04 schema/owner 一致性，并把 A04 的真实 Panda MJCF 与 Procedural Asset 映射接入一个 `scene-definition-v3` Canonical Scene integration fixture；沿用 A03 的单/双 Robot 静态 oracle，不重复定义其验收。A05 只建立静态集成与向 D01a 的兼容 Projection，不构造 Provider Runtime 或执行 Physics。
- **Projection / Evidence 产出**：提供从 Canonical Scene 到 D01a microprobe input 的明确、可测试 Projection。维护者已批准 `scene-definition-v3` mapping 原样复制作为输入契约。逐字段列出 Asset/Entity/Frame/Joint/Actuator 的 canonical identity、目标字段/legacy reference、默认与拒绝规则、未投影字段及其语义处置；附 `SceneDefinition.identity_hash`、Asset Declaration Identity、Source Closure Digest、Provider Import/Cache Identity、映射/语义 receipt 引用、正负测试及 Unsupported List。它是 compatibility contract/receipt，不新增 SceneManager、Runtime 或第二份 Scene owner；不得把 legacy `world-v0` TaskArtifact 声称为 D01a payload。
- **验收**：真实 Panda MJCF 与现有 Procedural Asset 经各自 A04 Evidence 进入同一个 Canonical Scene contract 并稳定 roundtrip/hash；Projection 对必需 canonical fields 无隐式丢弃、错误默认或未声明近似；证明一个既有冻结任务场景可通过只读兼容投影描述，同时保留 `world-v0` mapping/hash、selected reference Asset/ID 与 legacy references。Evidence 可由后续 D01a 直接消费并追溯到实际 source/import/mapping；A05 只证明静态 contract/projection，D01a 仍负责以 S2 Evidence 证明 Provider 实际消费新输入、真实 materialization 与 realization tolerance。
- **Codex AUDIT Goal**：判断是否已经具有可让 B 编译 Task 的最小 SceneContract；如果物理转换仍待 D，明确 deferred boundary。
- **顺序决议（按 05 的依赖图修正实际路线）**：A03–A05 的初次实现早于 B04a、D02a、C01a、D05a；因此首次验收不能满足推荐拓扑顺序。现已依次完成 B04a → D02a → C01a → D05a，再按本文件 A03 → A04 → A05 重新运行静态 Gate。A05 的 `scene-definition-v3` 原样 mapping 仍是已批准的 D01a microprobe input contract。D01a 还需消费 A05、B04a、C01a 的结果并证明新 Scene 表示真实进入 Provider materialization；D02b 等待 D02a 与 D01a，B01 等待 A05、B04a、D01a、D02b。A 阶段不替代 D 的真实 Physics Materialization。

#### A05 实施记录（2026-10-20）

A04 Panda MJCF 与 Procedural `square-peg-v1` 的完整 `canonical_scene` mapping 现随各自 A04 import receipt 保存，A05 直接从这些 receipt 解码并合并为一个 `scene-definition-v3`，不手写替代来源。集成场景 identity 为
`047661ff68e18dffa10a8bfe9cabef4e72f397b5280c1da7c7669ebf9e419e6e`；roundtrip 保持 mapping 与 hash。A05 记录 34 条 Asset/Entity/Frame/Joint/Actuator identity 字段映射，目的地保持 Canonical Scene 原字段，没有默认值或近似；另外完整携带 Asset Declaration Identity、Source Closure Digest、GeoPhys import identity、A04 Source→Imported→Canonical mapping 和语义 receipt。278 条非 Canonical semantic entry 都明确保留在来源 receipt 中并标记为 provenance-only，不作为 D01a 可执行结构。Panda 的旧 UID、joint/body/actuator references、selected `tabletop-v1` 与 peg 的 `square-peg-v1` / `peg1` 由 legacy receipt 和断言覆盖。A03 单/双 Robot oracle 继续由既有测试验证，本次没有复制一套 oracle。

维护者于 2026-10-20 明确批准 `scene-definition-v3` mapping 原样作为 D01a microprobe input contract；本 Evidence 将该 mapping 原样作为输入，不增加默认、字段改名或近似转换。严格 codec 的缺字段/未知字段负例通过。`world-v0` 不被声明为等价投影：它缺少承载本次完整 Scene/Actuator 结构的字段；已有 frozen Artifact/hash 测试在回归中通过。除此 D01a 输入契约批准外，本轮不执行 Provider materialization，也不声称 D01a 已验证实际消费。

A.6 的现有任务场景兼容要求由冻结的 NutAssembly `world-v0` TaskArtifact 提供独立只读投影：保持原 Artifact mapping 与 identity hash `99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe` 不变，并将其 Entity/Frame/Joint/Actuator 身份投影到同一 `scene-definition-v3` owner。没有 A04 Source Closure/Provider Import receipt 的资产仅标记 manifest 或 TaskArtifact 来源，不纳入 D01a microprobe payload；几何、接触意图、Task lifecycle/evaluation、world convention 等未由 Scene 表示的属性逐字段以 `SOURCE_RETAINED` 保留，不静默丢失。现有 RuntimeSource 中 Panda hand 下的 `nutassembly_ee_site` 只投影为静态 link-local `ee` Frame，不主张 world pose 或动态状态。

最终联合回归 **64 passed, 0 failed**，覆盖 A03 静态场景/结构、Artifact identity、legacy construction、A04 Panda/Procedural source import 与 A05 两种投影；使用 Python 3.12 GeoChora 环境，墙钟 6.85 s。命令、结果和限制记录于忽略目录 [`run_metadata.json`](../../../../../workspace/maintenance/phase_ii_acceptance_20261020/run_metadata.json)。A05 receipt 为 [`a05_static_projection_receipt.json`](../../../../../workspace/maintenance/phase_ii_acceptance_20261020/regression_final_tmp/test_a05_integrates_a04_assets0/a05_static_projection_receipt.json)，SHA-256 `7b08573613bb57067cd856a1d1a36354f3eeacab7dfa9d75d4e7b0517c304492`；集成 Panda+peg Scene identity `047661ff68e18dffa10a8bfe9cabef4e72f397b5280c1da7c7669ebf9e419e6e`，NutAssembly 兼容投影 Scene identity `59b50c4e4745a10736d2ad2113404e9864e5d92614baacd916ecbd4b62d10b85`。`git diff --check` 通过。A05 Evidence 为静态 S1：没有构造 Provider Runtime、运行 Physics 或验证 D01a 的真实消费/realization tolerance。

#### 按执行表 05 的 A03–A05 复验（2026-10-20）

在 B04a、D02a、C01a、D05a 已交付后，重新运行 A03 composition/structure、A01 Artifact identity、reference construction、A04 真实 Panda MJCF/Procedural source + legacy factory、A05 集成与两种静态 projection；并在同一联合回归中验证 B04a、D02a、C01a、D05a：**91 passed, 0 failed**，5.38 s（A 测试子集此前独立运行 **64 passed**）。完整命令与 Python/environment 配置记录于忽略目录 [`run_metadata.json`](../../../../../workspace/maintenance/phase_ii_acceptance_20261020_d05a/run_metadata.json)。新 A05 receipt [`a05_static_projection_receipt.json`](../../../../../workspace/maintenance/phase_ii_acceptance_20261020_d05a/final_tmp/test_a05_integrates_a04_assets0/a05_static_projection_receipt.json) 的 SHA-256 为 `d2ef1a18d4c47a36584c3875a2fde889016a42ba32a71b7246c5af1662f627eb`；Panda+peg canonical Scene identity 仍为 `047661ff68e18dffa10a8bfe9cabef4e72f397b5280c1da7c7669ebf9e419e6e`，frozen NutAssembly `world-v0` mapping/hash 与原只读兼容 projection 保持不变。新证据仍为 provider-free 静态 S1；没有开始 D01a、构造 Provider Runtime 或执行 Physics。

## A.6 阶段 Gate：推荐最低证据

| 测试 | Oracle | 级别 |
| --- | --- | --- |
| Asset/Entity deterministic identity | 相同 Canonical Mapping 的 hash、实例唯一性 | S1 |
| Frame compose / inverse / parent cycle | 解析矩阵与严格异常 | S1 |
| Scene Role-agnostic composition | 静态 Reference 集合完整性 | S1 |
| Registry compatibility | public UIDs/callers + duplicate/unknown | S0/S1 |
| Panda/Cube/Pendulum affected construction | 当前受限真实 route（能运行时） | S2，记录不能运行原因 |
| Existing TaskArtifact compatibility | 保持冻结 `world-v0` mapping/hash；Task/entity fields 全部映射或 SOURCE_RETAINED | S1 |
| Scene/no-task 的静态双 Robot | Identity/ControlGroup/Frame | S1；**不代替多 Robot 动力学验证** |

**阶段通过条件**：提供稳定的 Canonical Scene/Asset/Entity/Frame 表示，并证明至少一个现有任务场景可经兼容层描述；B/C/D 不必知道 provider native IDs。遇到更广 Parser/Asset schema 硬需求，可采用 `ACCEPTED-DEFERRED`，但不得静默丢失 Task 需要的必需属性。

## A.7 参考项目：明确借鉴点与禁止照搬点

| 项目 | 影响/使用与借鉴 | 不照搬 |
| --- | --- | --- |
| [Isaac Lab](https://github.com/isaac-sim/IsaacLab) | 活跃机器人学习框架；Asset/Articulation/Scene 配置与多实例命名空间 | 强制依赖 USD/Kit 或其所有 GPU 克隆布局 |
| [SAPIEN](https://github.com/haosulab/SAPIEN) / [ManiSkill](https://github.com/mani-skill/ManiSkill) | Entity/Component、Actor/Link、机器人相机 Mount 的工程组织 | 将 SAPIEN Runtime Component 指针当 Core 类型 |
| [Gazebo Sim](https://github.com/gazebosim/gz-sim) | Scene Entity ID、Components、Transform Hierarchy 的清晰边界 | 整套 ECS Storage/System Scheduler 与进程通信 |
| [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie) | 高质量 Robot Asset 来源、版本/许可/引用 | 直接把 MJCF 定义成唯一 Canonical Object Model |
| [Genesis](https://github.com/Genesis-Embodied-AI/genesis-world) | Scene/Entity 创建与复合资产的简洁用户体验 | 将 Genesis native object 当成通用 Entity Instance |

参考优先级：**Isaac Lab/SAPIEN 的对象语义 + Menagerie 的资产来源治理 + Gazebo 的稳定身份思想**；不要把多种框架的继承关系叠加成复杂通用 ECS。

## A.8 需 Codex 重点审阅的问题

1. 当前 `AssetManifest`、`EntityDefinition`、`TaskCompositionSpec` 是否有相互重叠但语义不同的 owner？建议如何兼容而非重复？
2. `ComponentRegistry` 的 expected_base 限制应如何迁移到 Robot/Entity？保留 `make_agent` 多久？
3. Frame 用 Entity-qualified 字符串引用是否足够；何种情况需要显式 `FrameId` 类型？避免重命名导致既有记录失效。
4. 现有 MJCF 特化 Assembly 能安全抽出多少共享 Scene 结构？哪些细节必须留给 D materializer？
5. Menagerie source/version/license 如何经现有 registry/assembly 保存；是否仍存在足以证明新 Asset Registry 必要性的缺口？
6. 多 Robot 静态场景是否存在生产路径能验证，不允许把构造成功错误提升为 multi-robot physics qualification。

**A 阶段出口**：`Canonical Asset/Entity/Scene/Frame` 能作为 B 的任务声明和 D 的 Materialization 输入，但 A 本身不宣称物理仿真器之间的动力学等价。
