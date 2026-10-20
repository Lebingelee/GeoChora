# Phase A — Core Object Model：架构、代码实施与验收（Codex 草案）

> **PROPOSED / 需 Codex Audit 与维护者确认。** 本文是 Phase II A 阶段代码开发目标，不声称当前仓库已有全部类型/API。  
> 基准：2026-10-19，`main` HEAD `f292df149f41520b484ff27cf2ff78a584903013`，发布 v1.1.0。  
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
7. 注册和构造 API 扩展当前 `task_env.registry`；`make_agent` 为历史机器人构造术语，未来希望用 `make_robot` 避免与 RL Agent 混淆，但需分阶段迁移。
8. `make_env` 是最终执行 facade，不承担底层资产解析所有权；Scene/Robot 编译不要求启动 Physics。

## A.1 当前实现基线：已有所有者、断裂与边界

| 当前 owner / 路径 | 已知事实（IMPLEMENTED） | A 阶段拟处理的差距（PROPOSED） |
| --- | --- | --- |
| [`task_env/registry.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/registry.py) | `ComponentRegistry`，`make_agent/make_object/make_scene/make_env` | 按 Entity/Asset/Robot 的稳定身份与对象复用规则扩展；不新造平行 registry |
| [`task_env/environment/protocols.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/environment/protocols.py) | `AgentComponent`、`TaskObjectComponent`、`SceneBuilderComponent`、`TaskEnvironmentComponent` | 明确 robot/entity/components 继承/组合边界与兼容适配 |
| [`task_env/environment/types.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/environment/types.py) | `AssetManifest`、`ReferenceSpec`、`TaskCompositionSpec`、`TaskReferences` | 从任务专属声明发展到统一实例/Frame/Reference 规则 |
| [`task_env/assembly/compiler.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/assembly/compiler.py) | MJCF/任务专用组合，生成 `CompiledTaskScene` | 逐步让组合输入由 Canonical Scene 驱动；不在 A 强制重写 D 的 Physics Materializer |
| [`task_env/assembly/references.py`](https://github.com/Lebingelee/GeoChora/blob/main/task_env/assembly/references.py) | 以 name/ID 进行任务引用解析 | 保留功能，升级为 `Entity-qualified` refs；native integer IDs 限制在 adapter |
| [`task_env/robots/`](https://github.com/Lebingelee/GeoChora/tree/main/task_env/robots) | Panda、Pendulum 等机器人组件和控制句柄 | 通用 Robot Model/Control Group，不以 Panda 作为唯一 Robot 形状 |
| [`task_env/tasks/worlds/`](https://github.com/Lebingelee/GeoChora/tree/main/task_env/tasks/worlds) | 专用 tabletop/classic 场景 | 场景复用、多个机器人/物体实例声明 |
| [`asset/external/mujoco_menagerie`](https://github.com/Lebingelee/GeoChora/tree/main/asset/external/mujoco_menagerie) | 仓库中的外部 Gitlink 资产来源 | Asset reference/version/hash；不在 Core 复制第三方大型资产 |

**Codex 必核实**：旧 `make_agent` caller 的实际类型、name→index 映射在 `assembly` 中的生产路径，Scene/XML 构建者是否已经可复用，`asset/` 是否另有外部实际源码。先确定 Owner/CallGraph 再考虑新文件。

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

**静态定义不能持有 native mutable state**；对同一 Asset 重复实例化要不共享实例状态；Runtime Handle 的构造/释放属 D Owner，不应放在 AssetDefinition 的 `__del__` 中。

## A.5 分 Goal 实施路线与验收

### A01 — Asset Definition / Entity Instance / Identity

- **依赖**：P00 Baseline。
- **任务**：调查现有 AssetManifest/ReferenceSpec/Registry，确定 source provenance、definition id、instance id、hash/version；实现可扩展的最小声明与严格 codec；明示 native handle 不属于定义。
- **产出**：最小 typed data contract；source/instance 映射规则；Schema/Compatibility Notes；Unit Fixtures。
- **验收**：同 Asset→两 Entity IDs；重复实例 ID/缺失资产/非法单位拒绝；定义与实例独立 serialize/deserialize；不发生 Physics import/native construction；旧 `make_agent`/`make_object` 可正常导入。
- **终止条件**：如需重写 `asset/` 外部 Gitlink 或不能保持现有 Reference ID，先 `REVISE`。
- **Codex AUDIT Goal**：列出 AssetManifest、EntityDefinition、Asset Reference 的现有重叠数据，决定扩展的**唯一** owner 和迁移层。

### A02 — Component Model / Articulation / Frame Graph

- **依赖**：A01。
- **任务**：最小 Physical/Visual/Joint/Frame/Actuation component contract；Frame Parent 静态关系和 transform composition；无环校验，约束 Joint types 与 DOF 语义。
- **产出**：可验证的 Frame/Articulation structure、只读结构访问路径、strict failures。
- **验收**：World→Base→Hand→Camera Mount 的矩阵乘积符合 analytical oracle；循环/不存在 parent/不一致 frame 拒绝；同名 joint 在不同 Robot 中可共存；Free-base position/velocity 维度不能隐式要求相等；不实现 FK Solver。
- **Codex AUDIT Goal**：对照 `task_env/assembly/references.py` 与已有 Frame 代码，优先复用。

### A03 — Robot / Control Group / Scene Composition

- **依赖**：A02。
- **任务**：Robot Instance + ControlGroup 资源声明；Scene 独立组合多个 Robot/Objects/Sensors；保留固定 Frame/可视结构。
- **产出**：单 Panda、双 Panda、arm+hand（可以仅用结构 fixture）三种示例；Entity-qualified references。
- **验收**：两相同 Asset 实例名称隔离、关节资源集合可解析；ControlGroup 指向未知 actuator 失败；同一 Scene 重新解析产生相同 Canonical Identity；静态组合不得触发 native step；**不声称多 Robot 物理执行已支持**。
- **Codex AUDIT Goal**：区分 Scene Entity、Articulation Link、Task Role 的所有权，不复制 B 的 role resolver。

### A04 — Asset Import / Registry / Factory Migration

- **依赖**：A01–A03。
- **任务**：在现有 Registry 上新增/适配 Asset/Robot 构造；受限支持当前真实用到的 MJCF/URDF/source reference；列明无法无损转换的字段与变换。
- **产出**：统一的 Canonical Construction Path、旧 API 迁移/弃用报告、受限资产导入样例。
- **验收**：unknown/duplicate UID fail-closed；旧 `make_scene/make_object/make_agent` 保留兼容；构造 Panda/Cube 与已有任务 Recipe 语义一致；导入期间不访问 provider private solver；Asset source/content identity 能写入元数据。
- **Codex AUDIT Goal**：判断哪些资产解析应当归外部 `asset/` owner，哪些只能放 Core Assembly；禁止重新造通用 Asset Framework。

### A05 — A 阶段集成与保护性迁移

- **依赖**：A01–A04。
- **任务**：审阅前四 Goal 的 schema/owner 一致性；迁移至少一个现有 Scene Declaration；固定 Static Representation Test；准备供 B/D 消费的稳定入口。
- **产出**：A 阶段 Contract/Compatibility Receipt、正负测试集、残余 Unsupported List。
- **验收**：Pendulum 及受限 Panda/PickCube Scene 描述不退化；旧 selected reference Asset/ID 解析不丢；单/双机器人静态例子；测试真实命令/来源清楚。需要 Runtime 验证的能力不能用静态构造标成 verified runtime。
- **Codex AUDIT Goal**：判断是否已经具有可让 B 编译 Task 的最小 SceneContract；如果物理转换仍待 D，明确 deferred boundary。

## A.6 阶段 Gate：推荐最低证据

| 测试 | Oracle | 级别 |
| --- | --- | --- |
| Asset/Entity deterministic identity | 相同 Canonical Mapping 的 hash、实例唯一性 | S1 |
| Frame compose / inverse / parent cycle | 解析矩阵与严格异常 | S1 |
| Scene Role-agnostic composition | 静态 Reference 集合完整性 | S1 |
| Registry compatibility | public UIDs/callers + duplicate/unknown | S0/S1 |
| Panda/Cube/Pendulum affected construction | 当前受限真实 route（能运行时） | S2，记录不能运行原因 |
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
5. `asset/` gitlink 的维护/依赖许可是否影响新 Asset Registry 的职责？
6. 多 Robot 静态场景是否存在生产路径能验证，不允许把构造成功错误提升为 multi-robot physics qualification。

**A 阶段出口**：`Canonical Asset/Entity/Scene/Frame` 能作为 B 的任务声明和 D 的 Materialization 输入，但 A 本身不宣称物理仿真器之间的动力学等价。
