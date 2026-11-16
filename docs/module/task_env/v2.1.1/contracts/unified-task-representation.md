# 统一任务表示协议

状态：`APPROVED_IMPLEMENTATION_BASELINE`，2026-11-03 维护者确认；见[确认收据](../maintenance/20261103_protocol_baseline_confirmation.md)。本文是后续实施的语义基线；新类型名称和字段仍须由所属子阶段工作包映射到现有 owner，不代表生产 schema、API 或运行能力已经实现。

## 1. 结论与边界

沿用 `TaskArtifactDeclarationV1`、`TaskSourceV1`、`SceneDefinition`、`TaskArtifact`、`TaskDefinition`、`ExecutionSpecV1`、`RuntimeSource` 和 typed state 的既有 owner。**不建立顶层 TaskIR、第二套 TaskDefinition、通用 physics manager 或完整物理 DSL。**任务目标、奖励、成功/失败、终止语义和 Solution 继续属于 Task Artifact／TaskDefinition 与任务自己的 Solution。

统一表示由三类值组成，而不是一份会被各层共同修改的对象：

1. **构建描述**：纯值声明，含任务语义、Scene／资产引用、Source 角色和初始条件、静态 execution selection。它用稳定语义 ID、类型化引用、单位和 schema 版本描述要求；不含 native Python object、GPU pointer 或 provider ordinal。
2. **编译绑定**：Core compiler 将描述解析为 Artifact、Scene、Source 和可选 Controller 的不可变组合。当前 `CompiledReferenceTaskV1`／`RuntimeSource` 是 provider materialization 前的绑定值；其 named source binding 可以用于核验来源，但不等于任务语义，也不应把 native index 提升成 task ID。真正的 native handle、索引、分配和实际配置属于 RuntimeSession/provider materialization 与其 receipt。
3. **动态发布**：运行期 state/capture 按 Scene、Source、Execution、scene instance、episode/reset 和 sample boundary 绑定发布。当前 `CanonicalStateViewV1` 以 entity-qualified Joint/Frame 值、boundary 和 clock 表示状态；renderer/camera consumer 另行声明 visual binding 和 capture identity。发布值不能回写或重定义构建描述。

静态类型、compile 成功或外部表示“能表达”都不代表 provider 当前可运行。Admission 应在具体 provider/build、资产 closure、表示、交互、renderer 和环境约束上 fail closed；转换、reset、step、failure receipt、buffer lifetime 与 close 的详细操作协议留给 1c/1d。

## 2. 四类信息的字段与 owner

表内“已有”说明当前实现的真实边界；“扩展”是维护者确认的后续版本设计，不表示生产 schema 已实现。

### 2.1 任务语义

| 字段／约束 | 语义与单位／坐标 | 必需性 | 当前 owner／consumer | 处置 |
| --- | --- | --- | --- | --- |
| `task_id`、Artifact ID、Artifact version | 稳定任务身份和显式版本；不得由 native 名称或对象地址推导 | 必需 | `TaskArtifactDeclarationV1` → `TaskArtifact`／`TaskArtifactV1`；registry、selected task、recording identity | **FIX/COMPOSE**：留在现有 Artifact/compiler；版本变化显式迁移 |
| Entity、Frame、Joint 语义引用 | Entity ID 在 Scene 内唯一；Frame/Joint 使用 entity-qualified `FrameReference`／`JointReference` | 有场景关系时必需 | `TaskSourceV1.roles`、`SceneDefinition`、`TaskArtifactV1` bindings；assembly compiler、task source resolver、runtime source | **COMPOSE**：新边界用类型化引用；旧字符串 binding 仅由现有 bridge 显式映射 |
| 目标、奖励、success/failure、metrics、Solution 与终止策略 | 任务判据及评估采样语义；Solution 行为由任务 owner 决定 | 任务定义所需 | `SemanticDefinition`、`TaskDefinitionBase`／`TaskEvaluation`／`TaskBatchEvaluation`、任务 specialization 与 Solution | **FIX**：扩展原 Task Artifact／TaskDefinition；Execution 不拥有成功判据 |
| Action intent／Controller target | 几何目标与参考系、旋转表示，或具名关节/对象动作；Action 输入和 effort 不是 Joint position 的别名 | 有控制时必需 | `ActionIntent`、Controller contracts、Task-specific control adapter；当前 Panda-box 为 arm joint position + gripper | **COMPOSE**：动作目标与实体/Frame/Joint 类型化绑定；JointEffort／BodyWrench 与 typed load extension 按[控制协议](control-and-feedback.md)具名绑定；嵌套 Robot／组件声明通道与 Controller，维度不硬编码在 Core |
| 初态、reset envelope、随机化、settle、episode policy | SI 世界约定；当前 `PoseWorld` 为 m 与 normalized quaternion `wxyz`，关节值由关节定义确定 | reset 依赖项必需 | `InitializationContract`、`TaskInitializationV1`、reset sampler/plan；selected reset caller | **FIX/COMPOSE**：初始刚体 pose 可复用；自由实体状态不能硬塞入 scalar joint action |
| Observation／state requirements | field、subject、unit、reference frame、sample domain、required/optional；缺值必须标 unavailable + reason | 按 consumer 声明 | `observation_requirements`、`StateRequirements`／`StateFieldRequirement`、`TaskStateView`、`CanonicalStateViewV1`；task、controller、observation、renderer | **COMPOSE**：复用 StateRequirements 与 typed state；维持每个 consumer 独立要求 |
| `Timebase` | physics `dt`、control substeps/`dt`、hold 和采样边界 | 动力学任务必需 | `TaskArtifact`／`TaskArtifactV1.timebase`、runtime config、session 与 identity callers | **FIX**：保留现有字段和历史 hash 语义；改变 timebase 会改变当前 Artifact identity |

### 2.2 物理模型

| 字段／约束 | 语义与单位／坐标 | 必需性 | 当前 owner／consumer | 处置 |
| --- | --- | --- | --- | --- |
| Entity、Frame、Articulation、Joint topology | Scene-local 稳定 ID；父/子 Frame 及 parent/child joint pose 明确；世界约定为 SI、右手、Z-up、quaternion `wxyz` | 物理场景必需 | `SceneDefinition` v1–v3、`EntityInstance`、`FrameDefinition`、`ArticulationDefinition`、`JointDefinition`; Scene-v3 compiler/lowerer、typed state | **FIX**：保留这些 canonical owner 和 exact versioned codec |
| Joint coordinate layout | `fixed 0/0`；`revolute/continuous 1 rad / 1 rad·s⁻¹`；`prismatic 1 m / 1 m·s⁻¹`；`spherical 4 quaternion / 3 angular`；`floating 7 xyz+m+quat / 6 linear+angular`。`qpos`、`qvel`、effort/control 维数各由各自 contract 定义，不能互推 | 对已声明 Joint 必需 | `JointDefinition` 和 `TypedJointStateValue`; `CanonicalStateViewV1.validate_against_scene`; runtime adapters | **FIX**：按既有 `position_size`／`velocity_size` 精确描述；effort 是 Actuator/action contract |
| Free rigid Entity | Entity 可以由根 floating/free Joint 驱动，也可以只按实体/Frame pose 发布；给出 world pose、速度表达 Frame 和 twist reference point | task/reset/state 消费时条件必需 | `RuntimeSource.free_joints`、Scene floating Joint、`InitializationContract.poses_world`、runtime Frame state；PickCube cube source | **COMPOSE**：被动 free cube 是物理状态，不自动成为可控 Joint；其自由运动靠 gravity/contact |
| 质量、COM、惯量、接触/碰撞近似、摩擦、阻尼、约束、actuation/transmission | 具名 SI 量、适用 entity/frame、约束对象和来源；惯量必须声明表达 Frame/参考点；material 参数保留 provider-neutral 的量纲/值或可验证引用 | 只在模型/任务需要时必需；缺少任务所需项不得 admission | legacy `EntityDefinition.parameters_si`／`collision_intent` 只在 TaskArtifact-v0；Scene-v3 没有统一 first-class physics/material/collider schema；Scene actuator resource/control group 仅覆盖其声明范围 | **EXTEND**：同一 `SceneDefinition` owner 中新增有版本的 typed model/reference；不把旧自由字典冒充跨 provider physics model |
| 相互作用和 capability requirement | 明确相互作用类型、实体/区域/Frame 端点、requiredness、观测/时序和必须支持的能力 | 任务需要相互作用时必需 | `RequiredCapabilitySet`、`StateRequirements`、admission manifest；当前 manifest/adapter 有界能力检查 | **EXTEND/COMPOSE**：补充 typed interaction reference；“能声明”不等于“provider 支持”；coupling 缺证必须拒绝 |
| 软体、绳索、粒子、体积、拓扑变化 | typed model/reference、state component layout（名称/shape/dtype/unit/frame）、representation/topology generation 和拓扑变更边界 | 仅非刚体任务必需 | 当前 Scene/TaskArtifact 无通用离散状态/拓扑 owner；Vector `TaskStateView` 现为 named numeric arrays | **EXTEND**：保留类型化 payload/reference 和 generation；不在本版定义完整材料词典、求解器 DSL 或定长 CPU state |

**必要版本演进依据：**Scene-v1/v2/v3 codec 按显式 `schema_version` 选择允许字段并拒绝未知键。v3 当前包含 assets/entities/frames/articulations/robots/actuator resources/control groups，但没有可校验的物理模型、分离的 collision/visual representation 和它们之间的 typed mapping。legacy `parameters_si` 与 `collision_intent` 不具备实体引用、单位维度、拓扑或来源映射约束。若实现这些内容，建议在现有 `task_env.artifacts`／Scene owner 增加 Scene-v4 及最小 typed model/reference、representation 和 mapping 值；不能向旧 v1–v3 codec 偷加字段。具体类名和材料词典留待真实 consumers 出现后冻结。

### 2.3 资产表示

| 字段／约束 | 语义 | 必需性 | 当前 owner／consumer | 处置 |
| --- | --- | --- | --- | --- |
| Asset identity／来源 closure | asset ID/version、稳定 source URI/revision/content hash、license、完整依赖闭包的相对 POSIX path/size/hash | 对输入资产必需 | `AssetDefinition`、USD delivery/validation/closure contracts、`TaskSceneSource`／`UsdTaskSceneSourceV1`；source verifier、provider importer | **FIX/COMPOSE**：继续复用稳定 URI 和内容 hash；不写机器绝对路径 |
| Entity → representation binding | 同一语义 Entity 可关联 mechanical、collision、visual、sensor 等具名表示；每个绑定声明 format/content ref、entity-local Frame、`T_entity_from_representation`、单位/坐标约定及用途 | task/provider/renderer 实际消费到该表示时必需 | `AssetDefinition` 与 `EntityInstance` 只提供资产来源/版本；`ProviderRepresentationSelectionV1` 记录一次 provider 的格式/recipe 决策但明确不 runtime-admit；camera visual binding 现有 bounded caller | **EXTEND**：Scene-v4 以 Entity/Frame/representation ID 显式引用；选择结果不可代替 Scene identity 或 runtime admission |
| 表示间 mapping | source/target representation IDs、转换 kind、坐标变换、实体/Frame correspondence；非刚体还需 source/target topology generation 和映射数据身份 | 多表示有关联或 task 消费需要它时必需 | `RenderVisualInstanceBindingV1` 只覆盖当前 camera native body/geometry binding；一般 mechanical↔collision↔visual correspondence 缺失 | **EXTEND**：同 Scene owner 保存 typed mapping；悬空、重复、跨 entity 错绑或 stale topology 均拒绝 |
| 原生 importer lowering | 将所选、已声明输入映射到 provider representation/native build；需报告采用表示、已知转换和丢失语义 | 每次 materialization | RuntimeSession/provider adapter 和 source receipt | **COMPOSE**：是执行/构建记录，不悄悄改写逻辑 asset identity；未知/有损变换不能静默接受 |
| asset harness 派生 | decimation、重建 collider、重做物理离散或改材料等会改变 representation/模型的输出 | 仅显式派生任务 | 未来 asset harness owner；当前不在 Core importer 中 | **EXTEND**：源/recipe/tool-version/options/output hash/validation report 组成独立派生 representation identity；不得与原生 lowering receipt 混写 |

坐标映射的推荐方向写为 `T_entity_from_representation`，而状态 Pose 仍用已有 `PoseWorld` 的 world-from-frame 语义。各 provider importer 负责显式转换；不能因视觉 mesh 可读就推定 collider、质量、惯量、材料或接触模型正确。若 OpenUSD 有独立 collider mesh/approximation 和质量来源，那是表示分层的例子，不是 GeoChora 现有能力承诺（[OpenUSD UsdPhysics schema](https://openusd.org/release/api/usd_physics_page_front.html)、[UsdPhysicsMassAPI](https://openusd.org/release/api/class_usd_physics_mass_a_p_i.html)）。

### 2.4 执行配置

| 字段／约束 | 语义 | 必需性 | 当前 owner／consumer | 处置 |
| --- | --- | --- | --- | --- |
| Provider route | Core adapter/provider ID 与 build/version；一个物理 provider 拥有整场景的推进、内部 solver 和所声明的 coupler | 运行必需 | `ExecutionSpecV1.physics_provider/profile/backend/device`、provider manifest、RuntimeSession admission | **FIX/COMPOSE**：保持 provider 为路由边界，不用 CPU/CUDA 伪装成两个 provider |
| Host / engine / solver family + algorithm / coupler | 可区分独立 Newton、Isaac Sim host + PhysX、Isaac Sim host + Newton；只填写该路径实际适用的层级。多个 solver 不自动组成 coupler | 路由需要该区分时条件必需 | 当前 `ExecutionSpecV1` 只有 `physics_provider/profile/backend/device`，把 host/engine/solver 层次压在字符串/外部 config 中；无通用 coupler value | **EXTEND**：建议在原 Artifact/execution owner 中引入严格版本化 `ExecutionSpecV2` 的分层字段；v1 codec 不接受未知字段，不能原地重解释 |
| backend/device/precision/determinism | CPU/CUDA 等设备 backend、明确 device ID、数值精度/浮点模式、确定性要求；不得由 device 字符串推测可用性 | provider 有该维度时必需 | `ExecutionSpecV1`、ResolvedEnvConfig、ProviderCapabilityManifest、runtime identity | **COMPOSE**：保留既有 renderer selection/override；新精度字段缺省须注明 provider default 或 unknown |
| Timebase / workload batch layout | physics `dt`、控制 tick、substeps、batch mode/axis，provider/solver 对这些值的限制 | physics 执行必需 | Task Artifact Timebase、ResolvedEnvConfig、batch adapter | **FIX/EXTEND**：Timebase 暂留 TaskArtifact 以保护旧 hash；执行 receipt 同时绑定实际生效值 |
| dependency/environment constraints | runtime/OS/Python/package lock or environment identity、外部许可/资产资源前置条件 | 路线依赖时必需 | TaskEnv requirements、provider package/environment facts、source map | **COMPOSE**：记录环境 profile/lock identity 与约束，由 3a 冻结隔离／依赖方案；内部可用 worker 隔离，公共 Env 不因依赖冲突被替换 |
| Renderer route | 与 physics provider 分开的 renderer、backend/device/profile；camera-specific override 和 capture modalities | 若任务/observation 要图像时必需 | `RendererSelectionV1`／camera override、render provider/camera source/observation consumer | **FIX/COMPOSE**：继续独立选择并按完整组合 admission；selected PickCube 当前仍只接受 `renderer=none` |

当前 `ExecutionSpecV1.identity_hash` 对其声明的 provider/backend/profile/seed/determinism/renderer selection 计算 identity；`reference_task_identity_fields` 还将 resolved runtime config、source XML hash、Controller identity 和 named Source bindings 放进 route facts。它没有独立表达 host/engine/solver/coupler/precision/environment。建议新版本保留这些旧字段的精确解释，并给可选层次明确区分“not applicable”“unknown”和“required but unsupported”，不可用空字符串或缺键让含义漂移。

独立 Newton 与 Isaac Sim 6.2 host 内 Newton 在 1b 只是可表达的两种 route。Isaac Sim 6.2 官方文档说明其 Newton backend 与 PhysX 是可切换的 physics backend，并给出 Newton solver settings；Isaac 6.2 release notes 记录所捆绑 Newton 1.6.1/MuJoCo 3.12.0。它证明 route vocabulary 有现实对应，不证明 GeoChora 有相应 adapter。Isaac Sim 文档也提醒保持其捆绑 dependency 组合，不能任意升级（[Isaac Sim 6.2 Newton backend](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/physics/newton_physics.html)、[6.2 release notes](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/overview/release_notes.html)）。Core 当前 `mujoco>=3.8.1,<3.9.0` 与 GeoPhys 当前 `mujoco>=3.15.0` 仍无交集；本阶段仅把它作为 execution-environment constraint 记录。

## 3. 关节、状态与动作不可互换

`JointDefinition` 已有规范化布局，`TypedJointStateValue` 已能核对 position/velocity 的表示和维数；MuJoCo 文档也分别称 `qpos` 为 position vector、`qvel` 为 linear/angular velocity vector（[XML reference](https://mujoco.readthedocs.io/en/latest/XMLreference.html)）。实际维数应由 canonical Joint contract 与目标 provider codec 双向核验，不靠 `qpos` 长度猜 actuator 数。

- Scalar revolute/continuous/prismatic：1 个位置和 1 个广义速度；其 effort/control 是否存在由单独 actuator/action binding 决定。
- Spherical：4 个 quaternion 位置分量和 3 个角速度分量，不是 4 个 effort。
- Floating/free：7 个位置分量（xyz 米 + `wxyz` quaternion）和 6 个 twist 分量（线速度 xyz + 角速度 xyz）；typed state 同时给速度表达 Frame 和 twist reference point。free root pose 可通过 Entity 的 runtime Frame 作为 world pose 发布。
- PickCube 的被动物理 cube 需要 source free-joint binding 与 reset pose；这不表示 Controller 对它发 7 个 effort、7 个 velocity 或 7 个动作值。当前 `TaskArtifactV1.validate_scene` 对“required joint” reset/state bridge 明确只接受 scalar joints；Scene-v3/typed-state 支持 floating 布局不能抹掉这个 caller 边界。PickCube pose 可复用 Frame/state owner；若 task/controller/renderer 要求其浮动速度，则需 typed `StateRequirements`、明确 twist frame/point，并在对应 publisher/admission 中核验。
- 本版 BodyWrench 是独立命令类型；显式直接施力的请求必须绑定 Entity、作用 Frame/point、坐标系、力/力矩单位、duration/sample domain 和执行能力；不能把 free-body `qpos` 冒充 joint action。具体 command/reply 按[控制协议](control-and-feedback.md)，4a/4b 落地。

## 4. Scene instance、batch 与动态身份

物理实例布局（scalar／provider-native batch）与进程部署（同进程／独立 worker／多 worker）是两个可组合维度，不能把 remote worker 当成第二种物理批处理算法：

| 形态 | 任务/Scene 描述 | 运行实例和 batch 轴 | 当前事实与限制 |
| --- | --- | --- | --- |
| 单环境 | 一个 Task Artifact + Scene template | 一个 `scene_instance_id`、env ID、episode/reset generation；没有 batch 轴 | selected `make_env` 构造路线；physics provider 负责整场景 |
| native batch | 一份同构 Scene template + 多个带稳定 ID 的 Scene instances | publisher 明确 `batch_axis=env` 并逐行给 `(env_id, scene_instance_id, episode_id, reset_sample_id, state_revision)`；共享一个 provider route/config | 当前 GeoPhys merged rigid batch 是已存在实现，注册 Pendulum/TwoWheelBalance；不代表 PickCube/Isaac batch 已准入 |
| 进程隔离／process vectorization | worker 可持有 scalar session 或 native batch；一份任务模板按实际部署引用实例 | vector wrapper 明确 env→worker→worker-local row、episode/reset 信息；不假定一 env 一进程 | 当前 `RemoteBatchVecEnv` 是一个 child worker 持有 GeoPhys merged batch；不是每 env 独立 session。多 scalar worker 只是未来可声明的部署，当前未据此获得支持 |

建议让 batch envelope 引用唯一 task/Scene template、共同 execution config 和稳定实例列表；不要把 N 份 native state 复制进 Task Artifact，也不要把 N 个同值 Scene hash 当成不同 task semantics。Scene instance identity、env identity、episode/reset generation 和 batch row mapping 是 publication/runtime identity。当前 `StateBoundaryIdentity` 已有 `episode_id`、`scene_identity_hash`、`scene_instance_id`、`provider_materialization_id`、step/revision；未来 batch publication 还需显式 `env_id` 和稳定 batch axis/row mapping。

每批使用统一 provider route/config；不能把 CPU/CUDA 当作两个 physics provider 或把两类 solver 推定为可耦合。不变配置时，支持 partial reset 的路线只重新初始化选中 env，保留其他 env 的状态、时钟、Controller 历史和 episode/generation；这不要求重建整个 batch。更换执行配置时，按原生批次建立新执行实例／materialization，不迁移旧 native state。同一环境契约在 reset 后保持 Observation schema、shape/dtype/unit 与 camera output contract 固定。动作/controller 切换输入的完整契约留 1c/4a。render 图像沿用同一 batch row/environment ID，图像 layout 与 auto-reset detail 留 1d/6a。

## 5. Identity、codec 与兼容

| Identity | 当前形成方式／设计规则 | 不包含或不代表 |
| --- | --- | --- |
| Task/Artifact | `TaskArtifact`／`TaskArtifactV1.identity_hash` 基于 canonical strict JSON；v1 明确保留 v0 source Artifact identity、TaskSource snapshot、Scene identity/bindings、semantic fields 和 Timebase | 不含 provider native pointer/index；不能从不同 backend 得出相同的全部执行身份 |
| Asset | `AssetDefinition.identity_hash` 包含 source reference/revision/content hash/license；delivery closure另有精确 closure/hash | 仅 URI 或 asset label 不代表内容相同 |
| Scene | `SceneDefinition.identity_hash` 包含明确版本及该版字段；Entity/asset/Frame/Articulation/control 引用有序/规范化；Scene-v4 新 representation/model 字段将进入其 identity | native 下标或 importer 临时对象不属于稳定 Scene identity |
| Task Source／logical source | `TaskSourceV1.identity_hash` 覆盖 task/version、Scene ref、roles、initialization 和 hooks；logical Scene/source receipts 再绑定实际 closure 与 projections | role string 或路径不能覆盖缺失的源 closure hash |
| Execution | `ExecutionSpecV1.identity_hash` 覆盖当前显式静态选择；resolved config、task/source/controller/environment 和 provider build 按各自 receipt 一起绑定执行实例 | 仅写 `provider=Isaac` 不说明 host engine、solver、renderer 或 package build |
| Dynamic publication | `StateBoundaryIdentity`、`StateSampleClock`、scene instance、episode/reset/provider materialization、step/revision；Capture Identity 绑定相机/source/execution/provider manifest/modalities/boundary | state/capture generation 不回写 Artifact 或 Scene identity |

`Timebase` 现已位于 `TaskArtifact` 和 `TaskArtifactV1` 的 canonical mapping 中，所以改 physics `dt`/control substeps 会改当前 task artifact hash；backend/renderer 路由则由 `ExecutionSpec` 与 resolved config identity 分开绑定。**1b 保持 v0/v1 hash/codec 原义，不把“改 backend 或 dt 永不改变 task identity”写成规则。**若产品希望未来将 cadence 完全移入 Execution，需要新 Artifact/identity 版本、显式旧身份对应表、codec reader 和历史 evidence 保留；不得重签旧 Artifact 或把旧接收静默转移。

Decoder 只按精确 `schema_version`；unknown core fields/enum 均拒绝。扩展仅能进入该版本显式定义的类型化 extension 槽，至少带 namespace、extension schema version、requiredness、payload/content identity 与 typed references。旧版本若没有 extension 槽，不因新设计而接受未知字段。未来 decoder 仅为保留未知 optional payload 而透传时，执行 admission 仍须确认它不改变语义且不影响本路线；任何 required/physics-affecting extension 未注册、悬空引用、缺少 required representation 或未知相互作用必须在 compile/admission/materialization 的首个可知阶段，以稳定原因拒绝，不丢字段、不降级、不 silent fallback。

### 5.1 Task/Robot source 组合

`SourceCompositionPlanV1` 与其 `source-composition-plan-v1` identity 继续按历史结构解释，不能为加入新组合方式而重签。共享层先从 Task source identity、Task/既有 Robot owner 与 Robot `source_recipe()` 生成 `SourceCompositionIntentV1`；该预解析 identity 固定 pinned source reference/revision、Robot entity、reference/replace/add 模式、组件边、Task site transfer、controlled joints、Controller profile 和 resource writer，不读取 Robot 素材。Provider adapter 消费该 intent 后才校验 source closure、解析 source 并作 native 映射，再生成带 `intent_identity_sha256` 的解析后 `SourceCompositionRequestV2`。V2 可表示空 Task entity 集、Task 已含 Robot 的 reference/replace，以及 Task source 不含 Robot 的 add；它继续携带已验证 source closure、实体 owner、带 closure provenance 的 attachment frame/rule 与 writer/resource 声明。物化回执同时记录 intent/request identity、source closure、native entity 映射及 provider materialization identity。Intent 和 V2 均不含 XML、native handle/index 或 provider type；重复 owner、悬空实体、错误 closure、循环 attachment 和资源双 writer 均应在组合准入时拒绝。旧 V1 identity 和 receipt 仍按其原结构核验。

## 6. 兼容矩阵

| 现有调用路径 | 1b 处置 | 明确限制 |
| --- | --- | --- |
| `TaskArtifact` v0 + `decode_task_artifact` | 原 codec/identity 保持；仅接受其既有字段 | 不按字段形状猜成 v1，不重签历史 |
| `TaskArtifactV1` + `TaskSourceV1` | 按显式 compiler、source/Scene identity 和 Frame/Joint bindings 继续复用 | `validate_scene` 的 required reset/state Joint 仍限 scalar；无通用 free-body joint action |
| `SceneDefinition` v1/v2/v3 | 保留当前精确版本语义和 reader；v3 继续承载当前 robots/actuator groups | 新物理参数、representation map、拓扑字段需显式后继版本；不在旧 codec 放未知字段 |
| selected PickCube | 保持 `TaskArtifactDeclarationV1`／`ReferenceTaskDeclarationV1`、selected `make_env`、P1.6 当前配置和 task-owned Solution | cube 是 floating/free source；selected renderer 仍为 `none`，现有动态 cross-camera 不兼容 free joints；文档不宣称迁移或渲染能力新增 |
| NutAssembly | 保持现有 specialization/Artifact/source/TaskDefinition 和 outcome semantics owner | 复用编译 owner 不表示使用新 Scene-v4 或任意 provider 兼容 |
| LIBERO | 继续在 `bench_deploy/libero` 保留 benchmark source/control/evaluation owner；可以复用 `TaskArtifactDeclarationV1`/compiler | 尚无通用 public LIBERO construction API；不宣称 caller 已迁移、不把 benchmark logic 移入 Core |
| 通用 `TaskDefinition`／旧 wrapper 与 lightweight tasks | 保留当前 public `make_env`/factory 和兼容 caller，各自以精确来源核查 | PickCube/NutAssembly 公共 TaskDefinition migration 尚是后续范围；不做宽兼容 sweep |
| `make_parallel_env`／merged scene | 复用已有 native GeoPhys batch 与独立 remote vector owner | 当前注册 task/provider envelope 保持不变；batch/camera/auto-reset 新契约留 1d/6a |

## 7. 结构化设计案例

[`planning/representation-cases.json`](../planning/representation-cases.json) 是可审阅的 planning JSON，声明本身就是唯一意图：**设计例子，不是生产 codec/API，不导入 runtime，不模拟 capability validator。**它包含 P1–P4 与 N1–N5：刚体/相机+free cube、同任务不同 Newton route、非刚体可表达但 provider 未准入、实例化 batch；以及错误维数、视觉推断物理、身份/映射冲突、忽略未知扩展/假设耦合、reset 后改变固定 observation/camera contract 五类反例。

## 8. 已确认的版本演进与实施边界

Scene 及 Execution 扩展继续归既有 owner；Scene-v4／ExecutionSpecV2 是建议版本名，具体最小类型／字段由 3a/3b 对照真实 caller 冻结。Scene-v1–v3、Artifact-v0/v1、Execution-v1 exact codec 与历史 hash 不改。非刚体只保留 typed representation/state/load 槽；实际 coupling 缺证仍拒绝。

任务控制／观测 cadence 与 native integration dt/substeps 概念分开。v2.1.1 优先沿用当前共享 Timebase 并核对三条路线；不能静默改 dt。若真实路线必须使用不同 native dt，由 3a 明确版本化 execution/identity 映射、逻辑任务对应关系与旧 reader 兼容，不把旧 Artifact identity 重签成相同；无法满足时提出具体依赖决定。

Robot 嵌套、Controller binding、7＋2 Panda profile、JointEffort／BodyWrench 与未来 typed loads 的语义以[控制协议](control-and-feedback.md)为准；不能把九个具名输出解释为九个独立输入。原生约束和可实现力域必须保留。被动 free cube 不会因支持 BodyWrench 而默认受控。

资产准入必须区分输入物理合法性、native mapping/readback 与 reset/短程数值行为，具体 oracle/容差由 3b 冻结；required 未测量不得判为通过。约 5% cube 惯量差仍是待核对模型意图，不是已证明缺陷。

历史 1b 交付／审核见[原审核](../maintenance/reviews/20261103_1b_sol_review.md)；其中 draft 和待维护者措辞是当时状态，本次[确认收据](../maintenance/20261103_protocol_baseline_confirmation.md)确定当前基线。生产 schema 与能力状态仍按真实实现维护。
