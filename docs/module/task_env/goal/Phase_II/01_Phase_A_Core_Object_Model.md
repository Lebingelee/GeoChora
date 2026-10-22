# Phase A — Core Object Model：架构与 Goal 契约

> 文档整合：2026-10-22。本文保留父 Goal 的目标、所有权与验收要求；逐项当前状态以 [05 总审阅表](05_Architecture_Review_and_Execution_Order.md) 为准，开发与验收核心事实集中在 [A 开发记录](A_Development_Record.md)。
> 下文“规划起点”、设计示例和 PROPOSED API 是原始设计语境，不代表当前支持清单。实际 capability 仍由源码、精确来源的 Evidence 及 [qualification](../../qualification.md) 约束。
> 当前工程基线为 GeoPhys `a53a8cfed7c9d6464274b5c96fca601271dc4ee4`；旧 pin 的历史收据保持原身份。当前范围是有界工程交付待二审，尚未发布 v2.0.0。

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

## A.1 规划起点与复用 owner（2026-10-20）

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

Control Group **只声明“可控制哪些资源”**，不在 A 固定 `cartesian_pose`、`joint_position` 等控制算法。当前 Scene-v3 拒绝同一 actuator 的重复 Group writer，C 的完整 plan 也要求唯一有效 writer；不能据原始设计中的“重叠组”提议推断已有仲裁能力。Controller 默认配置归 C 的实例化执行配置。

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

### A02 — Component Model / Articulation / Frame Graph

- **依赖**：A01。
- **实现边界修订**：继续扩展唯一的 `task_env.artifacts.SceneDefinition`，以 `scene-definition-v2` 增加静态 Frame/Articulation 结构；保留 v1 identity mapping/hash，不另建 ECS、Robot model、Frame resolver 或 Runtime。暂不添加无消费者的通用 Physical/Visual/Actuation component；Asset 物理/视觉内容归 A04 source importer 与 D01 materialization，控制资源归 C02 binding。
- **Frame contract**：`FrameReference(entity_id, frame_id)` 消除跨 Robot 同名歧义。`authored_fixed` frame 带相对 parent 的 `PoseWorld`；无 parent 表示直接相对 world。`runtime` frame 是无静态 pose 的动态锚点，可对应 free body 或 articulation link，pose 留给后续 D02 state。只允许在完全 authored-fixed 的路径上解析 world pose；以 runtime frame 为 ancestor 时可求 link-local transform，world 结果明确失败。
- **Articulation / Joint contract**：一个 entity 可有多个互不重叠的 articulation tree；每棵包含 root link 与无环连通 joint tree，每个 link frame 恰属一个 articulation。Joint 的 parent/child 是 entity-qualified link frame，joint frame 在 parent/child link 内的两组固定变换完整保留；axis 表达于 joint frame。Joint ID 在 entity 内唯一，不同 entity 可以同名。暂支持 fixed/revolute/continuous/prismatic/spherical/floating 六种常见坐标布局；位置/速度 representation 与数组宽度分别声明（例如 spherical 4/3、floating 7/6），不能把宽度当相等的 DOF 数。
- **产出**：严格 v2 mapping、只读静态 Frame composition、Articulation tree 校验、v1 兼容证明、SOURCE limitations。
- **验收**：World→Base→Hand→Camera Mount 的旋转/平移符合独立 analytical oracle；Frame parent 缺失/成环/跨实体引用、joint topology 错误及未知 schema/字段拒绝；同名 joint 在两个 Robot 实例可共存；joint origin 变化进入 Scene hash；Free/spherical coordinate 宽度按声明校验；runtime link 不冒充 authored pose；不导入 Provider、不做 FK/physics lowering。
- **Source limitation**：A02 不表达闭环约束、transmission/tendon/equality、joint limits 或 actuator control；A04 importer 必须逐项映射、显式保留受限 source reference 或 fail closed，不能静默丢弃。D02a 后续定义动态 link state/timebase/lifetime，本 Goal 的 `PoseWorld` 只描述 authored fixed geometry 与 joint frame geometry。

### A03 — Robot / Control Group / Scene Composition

- **依赖**：A02。
- **任务**：Robot Instance + ControlGroup 资源声明；Scene 独立组合多个 Robot/Objects/Sensors；保留固定 Frame/可视结构。
- **产出**：单 Panda、双 Panda、arm+hand（可以仅用结构 fixture）三种示例；Entity-qualified references。
- **边界**：双 Robot 的结构与实际 reference resolver 都要测试；首个基线仅承诺其静态契约。后续 C02b 若请求真实双 Robot，须先有 D01b binding 和 S2；没有该证据则明确 unsupported/deferred，不可沿用单 Panda 动力学结论。
- **验收**：两相同 Asset 实例名称隔离、关节资源集合可解析；ControlGroup 指向未知 actuator 失败；同一 Scene 重新解析产生相同 Canonical Identity；静态组合不得触发 native step；**不声称多 Robot 物理执行已支持**。
- **Codex AUDIT Goal**：区分 Scene Entity、Articulation Link、Task Role 的所有权，不复制 B 的 role resolver。

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

### A05 — A 阶段集成与保护性迁移

- **依赖**：A01–A04。
- **任务**：审阅 A01–A04 schema/owner 一致性，并把 A04 的真实 Panda MJCF 与 Procedural Asset 映射接入一个 `scene-definition-v3` Canonical Scene integration fixture；沿用 A03 的单/双 Robot 静态 oracle，不重复定义其验收。A05 只建立静态集成与向 D01a 的兼容 Projection，不构造 Provider Runtime 或执行 Physics。
- **Projection / Evidence 产出**：提供从 Canonical Scene 到 D01a microprobe input 的明确、可测试 Projection。维护者已批准 `scene-definition-v3` mapping 原样复制作为输入契约。逐字段列出 Asset/Entity/Frame/Joint/Actuator 的 canonical identity、目标字段/legacy reference、默认与拒绝规则、未投影字段及其语义处置；附 `SceneDefinition.identity_hash`、Asset Declaration Identity、Source Closure Digest、Provider Import/Cache Identity、映射/语义 receipt 引用、正负测试及 Unsupported List。它是 compatibility contract/receipt，不新增 SceneManager、Runtime 或第二份 Scene owner；不得把 legacy `world-v0` TaskArtifact 声称为 D01a payload。
- **验收**：真实 Panda MJCF 与现有 Procedural Asset 经各自 A04 Evidence 进入同一个 Canonical Scene contract 并稳定 roundtrip/hash；Projection 对必需 canonical fields 无隐式丢弃、错误默认或未声明近似；证明一个既有冻结任务场景可通过只读兼容投影描述，同时保留 `world-v0` mapping/hash、selected reference Asset/ID 与 legacy references。Evidence 可由后续 D01a 直接消费并追溯到实际 source/import/mapping；A05 只证明静态 contract/projection，D01a 仍负责以 S2 Evidence 证明 Provider 实际消费新输入、真实 materialization 与 realization tolerance。
- **Codex AUDIT Goal**：判断是否已经具有可让 B 编译 Task 的最小 SceneContract；如果物理转换仍待 D，明确 deferred boundary。
- **顺序决议（按 05 的依赖图修正实际路线）**：A03–A05 的初次实现早于 B04a、D02a、C01a、D05a；因此首次验收不能满足推荐拓扑顺序。现已依次完成 B04a → D02a → C01a → D05a，再按本文件 A03 → A04 → A05 重新运行静态 Gate。A05 的 `scene-definition-v3` 原样 mapping 仍是已批准的 D01a microprobe input contract。D01a 还需消费 A05、B04a、C01a 的结果并证明新 Scene 表示真实进入 Provider materialization；D02b 等待 D02a 与 D01a，B01 等待 A05、B04a、D01a、D02b。A 阶段不替代 D 的真实 Physics Materialization。

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

## A.9 Logical Robot Assembly 扩展候选（2026-10-21，仅规划）

本次只补未来扩展方向，不重开 A01–A05、不更改已验收 Scene v1/v2/v3 mapping/hash。
现有 `RobotInstance(entity_id, articulation_roots)`、Joint endpoints 和 ControlGroup actuator refs 仍受同 Entity 边界约束。
跨 Entity Joint 不能塞入现行 v3。当前恢复主线先维持一个 Panda Entity 的 arm/gripper Groups，见
[C02b 恢复契约](C_Development_Record.md#c02b)。

**Logical Assembly**：未来可在现有 Scene/artifacts owner 中审阅轻量版本化 member relation，引用独立 Entity 或
已有 Entity 内的逻辑 control subpart；集成 Panda 的 hand link 不因此变成第二个 Entity。
资产定义可以多次实例化，物理 Entity 实例和可写 actuator 不得因嵌套/alias 被重复占有。递归仅作为未来候选，
必须拒绝 cycle、悬挂引用、歧义路径和重复有效 writer；不立即实现通用 Robot Framework。

**Physical Attachment**：与逻辑成员分开声明 parent/child Entity、mount Frame、明确方向的相对 SE(3)、
fixed attachment、collision-filter intent 和 articulation-root 处理。初期物理 attachment 采用无环、唯一物理父级的结构；
independent roots 不隐式生成“自由连接”。mount Frame 必须解析到有效物理 link/anchor，不能仅改 parent Frame
就声称 fixed-joint 动力学成立。dynamic attach/detach、闭环装配、runtime topology hot swap 暂缓。

**控制配置**：Robot preset + 声明的 leaf overrides 展开到唯一带 identity 的 Effective ControlBindingPlan；
父级 preset 不是 writer，不拥有第二份 native state。preset/partially_overridden/custom 由配置差分推导。
具体 Controller implementation、required feedback 和 source/config hash 归 C，不把实例/函数指针存入 Asset。

**Provider-neutral 边界**：Canonical Entity/Joint/Frame/Actuator 身份保持稳定，单或多个 native articulations
只能在 Provider 支持、物理约束和 reset/state mapping 经验证时选择。多 Entity 装配须另审 Scene 版本及 A03/D01 扩展，
当前仅 DEFERRED 候选，不进入 C02b 前置。最小双 Entity 独立施控仍按 P00/P99 验收，与此扩展无依赖关系。

参考：[Isaac Sim Robot Assembler API](https://docs.isaacsim.omniverse.nvidia.com/latest/py/source/extensions/isaacsim.robot_setup.assembler/docs/index.html)、
[6.2 装配教程](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/robot_setup/assemble_robots.html)。仅借鉴 mount alignment、
fixed joint、root handling、collision filtering/variant；不将 USD/Kit/PhysX 作为 Core ABI，当前 API 细节以引用版本为限。
