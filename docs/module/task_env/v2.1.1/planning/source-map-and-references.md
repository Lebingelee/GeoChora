# 当前 owner、缺口与参考

只读定位日期：2026-11-03，G01/1a 输入 Core `ba874c2d57dc9cd5e3cb710d87d3405808393967`、GeoPhys `67da1165149486d3ae3e779c13ce31af49e17d50`。这是本次审计 HEAD；编排中的原始规划 baseline `fd03817c…` 保持不变。CodeGraph 用于定位；源码、调用者与原始证据优先于索引摘要和旧计划。

## 优先复用的 owner

| Concern | 源码入口 | 当前基础／待补齐 |
| --- | --- | --- |
| 公共构造／配置 | [registry](../../../../../task_env/registry.py)、[configuration](../../../../../task_env/environment/configuration.py)、[声明](../../../../../task_env/environment/task_definition.py)、[source](../../../../../task_env/environment/task_source.py)、[assembly compiler](../../../../../task_env/assembly/compiler.py) | 已有 make_env 和配置优先级；公共 TaskDefinition 仍有兼容路径，需沿真实 caller 迁移 |
| 唯一 selected 生命周期 | [reference_env](../../../../../task_env/tasks/reference_env.py) | 当前 selected reset／step／record／close；非任意 reset 配置切换 |
| physics admission／session | [api](../../../../../task_env/runtime/sessions/api.py)、[control](../../../../../task_env/runtime/sessions/control.py)、[contracts](../../../../../task_env/runtime/contracts.py) | RuntimeSession、manifest、受限准入；阶段 profile 特判不能直接删除 |
| 三后端原生翻译 | [MuJoCo](../../../../../task_env/runtime/sessions/mujoco.py)、[GeoPhys](../../../../../task_env/runtime/sessions/geophys.py)、[native session](../../../../../task_env/runtime/sessions/native_io.py)、[Isaac IO](../../../../../task_env/runtime/sessions/isaac_native_io.py) | CPU 两路线及精确 Isaac CUDA／PhysX 路线；不能外推任意资产 |
| 当前控制器 | [canonical contracts](../../../../../task_env/controllers/canonical/contracts.py)、[R3](../../../../../task_env/controllers/canonical/production_r3.py)、[位置 profile](../../../../../task_env/controllers/canonical/position_profile.py) | R3 输出 q_ref，native servo 仍施控；具名 mixed 通道已有基础，非普遍 effort |
| benchmark 控制与模型 | [LIBERO OSC](../../../../../bench_deploy/libero/controllers/osc.py)、[参考动力学](../../../../../bench_deploy/libero/controllers/source_gravity.py) | 有 arm torque＋finger position；参考模型依赖 MuJoCo，未推进第二套物理；不整体搬入 Core |
| render／camera | [backend registry](../../../../../task_env/render/tools/backend_registry.py)、[single provider](../../../../../task_env/render/providers/single.py)、[camera API](../../../../../task_env/render/camera/api.py)、[camera source](../../../../../task_env/render/camera/source.py)、[observation consumer](../../../../../task_env/observations/capture.py) | 通用 UI `human`／`rgb_array` 与任务 observation 分离。Selected PickCube 仍只准 `renderer=none`；Position candidate 有 GeoPhys CPU → MuJoCo OpenGL 的边界绑定 camera observation 路径，不能外推到 PickCube |
| batch | [parallel API](../../../../../task_env/vectorization/parallel.py)、[batch lifecycle](../../../../../task_env/vectorization/task_definition.py)、[merged-scene batch](../../../../../task_env/runtime/providers/merged_scene.py)、[GeoPhys BRS adapter](../../../../../task_env/runtime/providers/geophys/rigid_batch.py) | `make_parallel_env` 只注册 Pendulum／TwoWheelBalance；native batch 为 GeoPhys merged rigid solver。CPU/CUDA 是同一 provider 的设备 backend，不构成两个 physics provider |
| 记录与读回 | [recorders](../../../../../task_env/recorders/contracts.py)、[canonical H5](../../../../../task_env/trajectory/canonical/h5.py) | 保持已有 schema、单一 Recorder；episode 配置与新数据身份要接通 |
| 任务和 Solution | [PickCube](../../../../../task_env/tasks/pick_cube/solution.py)、[PickCube specialization](../../../../../task_env/tasks/pick_cube/specialization.py)、[NutAssembly](../../../../../task_env/tasks/nut_assembly/solution.py) | 任务策略留在原 owner；成功参考未证明，不以控制器命名推断根因 |

provider 实现公开能力的 owner 仍在其项目内。Core 不访问 solver／renderer 私有 field；不为统一接口另外维护第二套状态或循环。

## 当前事实和待决定项

历史结果查 [v2.1.0 matrix](../../v2.1.0/capabilities/capability-matrix.json)。有界接收、原生驱动例外、0/9 task-success、A123 限定偏差与未测量项全部保持。版本文档含原候选状态文字；本轮只纠正当前导航和可核实来源，不重写历史记录。

| 编号 | 待冻结问题 | 负责子阶段 | 当前建议／约束 |
| --- | --- | --- | --- |
| D01 | 首批三个物理路线的精确 renderer、资产和版本 | 1a、1d | Physics 候选为 MuJoCo CPU、GeoPhys CPU、Isaac Sim 6.2/PhysX/CUDA:0。GeoPhys→MuJoCo OpenGL 仅有 scalar-joint Position camera 路径；PickCube free cube 不兼容。逐后端 native window／RGB／同步 observation 仍须 1d/5a–5c 接通与核验。 |
| D02 | 统一表示映射到哪些现有 schema，保留哪些兼容输入 | 1b | 本轮建议 Task Artifact/TaskDefinition 持有语义、现有 Scene/Asset 持有实体与来源；Scene-v4 在同一 owner 内补 typed 物理模型/表示映射，ExecutionSpec-v2 分层 provider/host/engine/solver/coupler。v0/v1 与 Scene-v1–v3 精确 codec/hash 保留，不建平行 TaskIR；当前已确认演进边界见[1b设计摘要](../maintenance/reviews/20261103_1b_representation_design.md)和[权威协议](../contracts/unified-task-representation.md)。 |
| D03 | 夹爪 effort、传动、mimic／tendon 和现有 native 兼容路由 | 1c、4a | 逐通道声明；不能把 arm torque＋finger position 称为全 effort，不重开 F05 严格等价研究 |
| D04 | 模型服务的库依赖、反馈频率和缺失能力 | 1c、4a | Controller只依赖Core公共state/model接口，不绑定live SDK或provider分支；可替换参考模型依赖需显式记录 |
| D05 | batch 的具体两个以上后端、auto-reset 及图像布局 | 1a、1d、6a | 当前 native batch 是 GeoPhys merged rigid；CPU/CUDA 不算两个 physics provider。Isaac Sim/PhysX/CUDA 是建议第二 provider 候选，需新增 batch adapter；现有 remote vector 是 same-step，图像布局尚未接通 |
| D06 | 数值准入和跨后端容差 | 1a、1c | 锚定 Panda source closure 与 PickCube cube/tendon/接触参数；用公开模型读回和 task source 定义各量 oracle。跨 provider 容差须由具体指标来源批准，审计不外推万能阈值 |
| D07 | 具体 API 签名、action-space 变更和旧 wrapper 兼容 | 1c、1d、4c | obs 固定；动作规格变化显式报告，不承诺旧 Agent／learner 无缝继续 |

这些是协议／执行准备工作，不要求维护者提前指定类名、库实现或全部数值。需要产品语义判断时在该项讨论中集中提出，不能静默替维护者改变范围。

## G01/1a 当前源码核实（attempt001）

| 路径／owner | 当前事实与边界 | 后续 owner |
| --- | --- | --- |
| `task_env.registry.make_env` → `configuration._resolve_selected_config` → task factory | `make_env` 是单环境公开入口；显式 task config 按配置优先级解析后调用选中 task 的 `from_resolved_config`／`from_reference_config`。Selected PickCube 使用 P1.6 路线，默认 R3／GeoPhys CPU，仍允许显式 R1；renderer 仅接受 none。 | 1b/1c：统一表示和 admission；3a/3b：精确配置及 route |
| `SelectedReferenceEnv._reset`／`step`／`close` | reset 关闭旧 camera consumer／RuntimeSession，再按绑定的 provider/backend 重建；没有 episode 内切换或旧状态迁移。Position observation 使用公开 `CanonicalStateViewV1` 与同一 boundary/clock，consumer 校验 capture identity。close 依次尽力关闭 consumer、session、runtime owner、source receipt 和 task resources。 | 1d、3c、5c |
| `task_env.render.providers.single.TaskEnvRenderProvider` | `human` 窗口和 `rgb_array` 是 UI renderer 的独立调用；`rgb_array` 是显式 readback，不参与 task observation。Generic visualizer 可从既有 RenderSource 构造；不要把窗口画面当作同步相机 observation。 | 1d、5a/5b |
| `PositionCandidateEnv` → `DynamicCameraObservationConsumerV1` | Position candidate 限 GeoPhys scalar CPU，允许 opt-in `camera_observation`。consumer 只接收 `CanonicalStateViewV1`，要求两个 camera 的 RGB、optical-Z depth、Entity mask 与 state boundary/clock 一致；reset/step 调用时捕获。此为 Position candidate 路径，不是 PickCube P1.6 配置。 | 1d、5b/5c |
| `task_env.render.camera.api`／`DynamicCameraRenderSourceV1` | 当前跨渲染 admission 为 GeoPhys CPU Scene-v3 → MuJoCo native OpenGL、`best_effort`；D04 Entity-mask profile 需要 RGB+Depth+segmentation。动态 render source 拒绝 `source.free_joints`，当前只接受 scalar joints。PickCube 的 `cube-v1` 是 floating/free joint，故此实现不能作为 PickCube cross renderer 的可实施证明。 | 1d、5a/5c；PickCube 资产映射归 3b |
| `make_parallel_env` → `RemoteBatchVecEnv`／`SceneBatchRuntime` | local 执行走 device transfer；remote 默认 spawn，也接受 forkserver，拒绝 fork 并通过 host NumPy IPC。注册 task 只有 `pendulum-v1`、`two-wheel-balance-v1`。batch 使用一个 GeoPhys merged rigid solver、批量 masked reset；remote step 在 done 的同一调用中 reset，并提供 `terminal_observation`／`reset_info`。未发现 MuJoCo 或 Isaac batch adapter。 | 1d、6a–6c |

### 首批路线建议与实际缺口

- **Physics 候选**维持 MuJoCo CPU、GeoPhys CPU、Isaac Sim 6.2.0.0 + PhysX CUDA `cuda:0`。这是源／既有矩阵中的明确交集，不是本次运行结果。v2.1.0 F06 记录为 MuJoCo 3.8.1、GeoPhys CPU、Isaac Sim 6.2.0.0 的历史有界 lifecycle/readback；三条均 `task_success=false`，无 Qualification。当前实现和本次审计均没有重新运行。
- **依赖限制**：`task_env/requirements.txt` 声明 `mujoco>=3.8.1,<3.9.0`，GeoPhys 当前 `pyproject.toml` 声明 `mujoco>=3.15.0`。同一 Python 环境无法同时满足这两个声明；历史 GeoPhys × MuJoCo renderer 证据使用的 GeoPhys pin 是 `a53a8cf…`，本次 gitlink 已为 `67da1165…`。在环境/依赖 owner 解决声明或隔离前，不把旧跨渲染 receipt 迁移为当前 pin 的可复现支持。
- **Renderer 候选**：通用 UI 的 `human` 和 `rgb_array` 由 `TaskEnvRenderProvider` 提供，且不形成 task observation；同 provider 静态 camera profile 为 `p1_4_native_camera_cpu_v0`。已实现动态跨路线名为 `d03_mujoco_native_dynamic_opengl_v1`，扩展 RGB-D／Entity mask 的 D04 profiles 也存在。Selected PickCube 目前 renderer none，Isaac F06 也没有所核实的 selected-task 同步 camera observation owner。5a–5c 需冻结每后端 native window、离屏 RGB 和同步 observation 的各自 API/资源 owner。
- **Batch 候选**：当前唯一 provider 是 GeoPhys native merged rigid batch；CPU/CUDA 是设备配置，不计为两个 physics provider。建议保留 GeoPhys native batch，再将 Isaac Sim + PhysX CUDA 作为第二 provider batch 候选进入 6a 设计；当前没有 Isaac batch adapter，也未将其标为 implemented。`RemoteBatchVecEnv` 的同步 autoreset 可作为 Same-Step 候选，但向量 metadata 尚需公开语义；merged-scene runtime 禁用 render source，故 batch image layout/render 尚无已接通实现。
- **PickCube D06 锚点**：P1.6 使用 2 ms physics tick × 5 substeps = 10 ms control tick（100 Hz），horizon 6000；世界位置为 m、旋转 quaternion wxyz，Panda 关节以 rad/rad·s⁻¹，重力 z=-9.81 m·s⁻²。Cube half-size 0.025 m、mass 0.08 kg、声明对角惯量 `(3.5e-5, 3.5e-5, 3.5e-5) kg·m²`、free-joint damping 0.8、armature 0.01、contact margin 0.001 m；模型还声明 table/cube/gripper friction、7 arm joints、2 finger joints、8 actuators（7 arm generalized actuators + 1 tendon gripper route）。固体均匀 0.05 m 立方体按声明质量的解析对角惯量为 `3.333…e-5 kg·m²`，与现有数值约差 5%；将既有数值保留为 source oracle，先由资产 owner 确认模型意图，不在本审计改写。跨 provider 需比较变换、单位、质量/惯量、joint 顺序/限制、tendon/transmission、驱动/限幅、接触、reset 与稳定性；仅当 source oracle/公开模型读回提供依据时才定容差。

Isaac Lab Scene Data Provider／Actuator 页面当前为其最新文档版本，不能当成本仓库 `isaacsim==6.2.0.0` 的可直接调用 API；它们只支持公开数据 freshness、资源 owner 和 explicit/implicit drive 语义的协议讨论。详见下表官方链接。

## G01/1b 表示设计的源码映射

本节只映射当前实现及建议 owner，不表示示例 JSON 是 public schema，也不把未迁移调用方写成已迁移。

| 设计内容 | 当前声明／schema owner | 已核实 caller／消费边界 | 决定 |
| --- | --- | --- | --- |
| Task semantics/build description | `TaskArtifactDeclarationV1`；`TaskSourceV1` identity/roles/init/hooks；`TaskArtifact` v0、`TaskArtifactV1`；`TaskDefinitionBase`／`TaskEvaluation` | `compile_declared_artifact` 纯值编译；`compile_task_artifact_v1` 连接 source、Scene 与 v0 semantic bridge；`ReferenceTaskDeclarationV1.compile` 返回 artifact/source/可选纯 controller，不 materialize provider | 复用 task-owned Artifact、TaskDefinition 和 Core compiler；奖励/success/Solution 不搬入 execution |
| Scene/physical topology/state | `EntityInstance`、`FrameDefinition`、`ArticulationDefinition`、`JointDefinition`、`SceneDefinition` v1–v3；`StateRequirements`、`TypedJointStateValue`、`CanonicalStateViewV1` | Scene codec 按版本拒绝未知字段；v3 有结构/robot/control group；typed state 已支持 floating 7-position/6-velocity，但 TaskArtifact-v1 `validate_scene` 仅允许 scalar required Joint | 旧 schema 不补字段；需 physics/material/collider/visual mapping 时同 Scene owner 新增显式版本及小型 typed refs |
| Asset/source/representation | `AssetDefinition`、USD delivery closure、`ProviderRepresentationSelectionV1`、`TaskSourceV1`／`TaskSceneSource` | selection 只记录 source/format/recipe 决定且 `runtime_admitted=false`；`RenderVisualInstanceBindingV1` 是 camera-specific source binding，不是通用机械/碰撞/视觉映射 | 同一 Entity 可多表示，但 mapping、frame、单位、源/output identity 和拓扑代次须显式；asset harness 派生与无损 native importer lowering 分开 |
| Execution route | `ExecutionSpecV1`、`ResolvedEnvConfig`、Provider manifest/admission、RuntimeSource | v1 有 provider/backend/profile/seed/determinism/renderer selection；`reference_task_identity_fields` 另含 resolved config、source XML hash、controller ID 与具名 source bindings。当前字段不能区分 host/engine/solver/coupler/precision/environment | 建议同 owner 的严格 `ExecutionSpecV2`；Newton standalone 与 Isaac-hosted Newton 为不同可表达 route，均不代表 GeoChora adapter |
| Free-body 与 camera | `RuntimeSource.free_joints`、Scene floating Joint、`InitializationContract.poses_world`、`TypedJointStateValue`／`TypedFrameStateValue`、`DynamicCameraRenderSourceV1` | `panda_box._panda_box_reference_declaration` 将 cube 绑定到 `PickCube_joint`；dynamic camera `from_runtime_source` 拒绝非空 `free_joints`；camera visual binding 需要 entity/frame/native-body/geometry 名映射 | 被动 free cube 以 Entity/Frame pose 表达，不要求 joint action；camera admission 要有对应 floating-state publisher 和 visual mapping，现有 selected PickCube 保持 renderer none |
| Batch/instance identity | `StateBoundaryIdentity`、`TaskStateView`／`BatchTaskStateView`、`SceneBatchRuntime`、`RemoteBatchVecEnv` | State boundary 有 episode/reset sample/Scene instance/materialization/step/revision；物理布局与进程部署可组合，当前 RemoteBatchVecEnv 的一个 worker 承载 GeoPhys merged native batch。`make_parallel_env` 目前只注册 Pendulum/TwoWheelBalance | 一个 template 对应多个带 env/scene-instance/episode ID 的实例；未来 batch publication 明示 leading env axis、env→worker→local row mapping，保持一份语义和统一 execution config |

主要 caller 入口包括 `task_env/assembly/panda_box.py::_panda_box_reference_declaration`／`compile_panda_box_task`、`task_env/tasks/pick_cube/specialization.py`、`task_env/tasks/nut_assembly/specialization.py` 和 `bench_deploy/libero/environment/selected_reference.py`。LIBERO 可复用 declaration/compiler，但公共通用构造迁移仍未完成，benchmark semantics 继续留在 `bench_deploy/libero`。设计示例与逐项拒绝理由在[representation-cases.json](representation-cases.json)。

### 1b 新增核对的官方参考

以下页面于 2026-11-03 核对。固定版 Isaac Sim 6.2 仅用来核对 host/backend/solver 路由真实存在与其 dependency boundary；`latest`／`release` 页面只用于一般概念，实施前仍需按确切安装重查。

| 官方来源 | 核对内容 | 本设计采用边界 |
| --- | --- | --- |
| [Isaac Sim 6.2 Newton backend](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/physics/newton_physics.html) | Isaac Sim 可选 PhysX/Newton backend；Newton 有 XPBD、MuJoCo、Featherstone、SemiImplicit solver families；host 内 engine 和 solver 可分层 | 证明 execution vocabulary 有具体对应；GeoChora 无 Isaac-Newton adapter 的证据，不宣称实现 |
| [Isaac Sim 6.2 release notes](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/overview/release_notes.html) | 6.2 捆绑 Newton 1.6.1、MuJoCo/MuJoCo Warp 3.12.0 与 Warp 1.17.0 | 每条路线须 bind exact environment/dependency identity；不能与 Core/GeoPhys 声明的 MuJoCo 区间冲突混为一谈 |
| [MuJoCo XML reference](https://mujoco.readthedocs.io/en/latest/XMLreference.html) | 文档将 runtime `qpos` 和 `qvel` 分开描述；free Joint 对 body topology 有单独限制 | 作为 position/velocity 不可互推的旁证；Canonical size 仍由本仓库 `JointDefinition` 决定 |
| [OpenUSD UsdPhysics schemas](https://openusd.org/release/api/usd_physics_page_front.html) 与 [MassAPI](https://openusd.org/release/api/class_usd_physics_mass_a_p_i.html) | collision approximation 与图形网格可分开定义，mass API 与 collider/rigid body 分离 | 支持把 mechanical/collision/visual representations 分离建模；OpenUSD 字段不是 GeoChora schema |

主审已接收该有界审计，见 [1a Sol 审核](../maintenance/reviews/20261103_1a_sol_review.md)。其中澄清：v2.1.0 矩阵已有当前 GeoPhys pin 的短程 state-only F06 证据；旧 pin 限制针对特定 cross-render receipt，不能混淆。上述 horizon 6000 是当前 YAML 默认，历史或调用方覆盖的运行按各自 identity／配置解释。

## 官方参考与采用边界

以下页面于 2026-11-03 查阅。`main`／`latest` 为可变来源，派实施包时必须核对本机版本、具体 API、依赖与许可证；参考项目能力不是 GeoChora 验收证据。

| 项目／来源 | 借鉴点 | 本版采用边界 |
| --- | --- | --- |
| [Newton ModelBuilder](https://newton-physics.github.io/newton/latest/api/_generated/newton.ModelBuilder.html) | 构建、Model、State、Control 和 world 布局的分离 | 支持路由和状态协议设计；不承诺接通 Newton |
| [Genesis Engine](https://genesis-world.readthedocs.io/en/latest/api_reference/engine/index.html) | 场景内 solver、材料和 coupler 的归属 | 能力需表达相互作用；不由两种材料存在推断耦合可用 |
| [Isaac Lab Scene Data Provider](https://docs.nvidia.com/isaaclab/concepts/scene-data-provider) | 公开几何／变换、重排、数据格式与消费者需求 | 复用现有公开数据 owner，避免 task／renderer 读取 physics 私有存储 |
| [Isaac Lab Actuators](https://isaac-sim.github.io/IsaacLab/main/source/concepts/actuators.html) | 显式／隐式 PD、effort 计算和限幅区别 | 迁移需重新验证，增益相同不保证响应相同 |
| [Gymnasium Env](https://gymnasium.farama.org/api/env/) | render_mode、metadata、human／rgb_array 与 close | 保持熟悉调用习惯；本项目 reset 换配置属于显式扩展，不能冒称完全兼容所有 wrapper |
| [Farama Vector Autoreset](https://farama.org/Vector-Autoreset-Mode) | 终止观测与 reset 首帧的语义区别 | 选择并公布支持方式，保护 Recorder 和 learner 边界 |
| [SOFA Mapping](https://sofa-framework.github.io/doc/simulation-principles/multi-model-representation/mapping/) | 机械、碰撞和视觉表示之间的映射 | 只准备资产表示边界，不实施 SOFA 后端或非刚体自动适配 |

实施记录须保存实际采用／拒绝方案与理由；不能把外部通用架构直接复制成重复 Runtime、manager 或大型抽象层。

## G01/1c 双向 physics 协议核实（attempt001）

本次只读输入 Core `develop@b0024c71614f2d2ede8d9eb1db594cfcde3e9278`、GeoPhys `67da1165149486d3ae3e779c13ce31af49e17d50`。CodeGraph 索引存在待同步文件，以下 owner/caller 事实以 on-disk 文件为准；未同步或重建索引。

| Concern／owner | 当前源码和 caller | 当前契约与精确缺口 | 1c 决定／后续 owner |
| --- | --- | --- | --- |
| query/admission | `runtime/sessions/api.py::provider_manifest/admit_capabilities/materialize`；`runtime/sessions/control.py::materialize_control`；SelectedReferenceEnv._reset | RuntimeSession 没有通用 request-specific query；静态 provider manifest 不是 source/build-bound report，generic capability claims 不能证明 task intersection；profile-specific admission 才绑定精确输入 | query 在现有 admission owner 扩展，逐项记录 provider API、adapter、dependency、evidence 与检查阶段。3a/3b 实施；未知 required 不准入 |
| build receipt／映射 | `RuntimeSession`、`NativeRuntimeIOMetadataV1`、各 `materialize` profile 与 `_materialize_admitted` | metadata 已绑定 source/closure/scene/Artifact/Execution/provider/build/backend/device/timebase/具名 scalar DOFs；但普通 materialize 无统一 receipt，也未一般化 host/engine/solver/coupler、转换损失和 required interaction 清单 | 在同一 session/admission owner 中 additive `ProviderMaterializationReceiptV1`；复用 ExecutionSourceReceipt、metadata、readback 和已存在的编译指纹；不得另建 manager |
| reset／状态 identity | `api.py::RuntimeSession.reset_plan/snapshot_v1/v2`；`native_io.py::NativeResetWriteReceiptV1/NativeRuntimeReadbackV1`；`artifacts/state.py::StateBoundaryIdentity/StateSampleClock/StateRequirements/CanonicalStatePublicationV1/V2/StateViewLifetime` | 已有 ResetPlan、exact source/sample validation、named readback、typed clock/requirements/lifetime；RuntimeSession 没统一 row mask。SelectedReferenceEnv.reset 会关闭旧 session 再建新 session；GeoPhys merged batch partial reset 是不同 owner | static reset preflight 放到 destructive close 之前；after-first-effect fault 不 rollback；batch mask 仅对明确支持的 native route 开放。1c 区分两个现状，3c/6a 落地 |
| command／feedback | `controllers/canonical/contracts.py::MixedActuatorPlanV1/MixedActuatorCommandV1/AppliedMixedActuatorCommandV1`；`RuntimeSession.apply_control/apply_mixed_actuator_command/step_mixed_actuator_interval` | name/unit/boundary/ACK 已在受限 source profile；ACK 不是 generalized-force measurement。Position target 仍是 R3/PickCube 主路线，native ctrl 不能天然解释为 effort | submitted/accepted/applied/measured 四阶段；Panda七臂joint torque＋两手指joint force为设计主路线；Robot嵌套／Controller binding、BodyWrench与贡献组合见当前控制协议；现有 position/mimic 另列 compatibility。4a/4b 实施与验证 |
| 模型与 feedback owner | `controllers/canonical/production_r3.py::from_source/compute`；`bench_deploy/libero/controllers/source_gravity.py::MujocoSourceGravityBiasV1`；`osc.py::_SourceOSCController` | R3 从 source MJCF 建 kinematics 并生成 q_ref；LIBERO model 以 ExecutionSourceReceipt 绑 source，提供 FK/J/M/qfrc_bias，`mj_step_call_count=0`，仍是 bench owner/MuJoCo 依赖 | 在现有 ControlBindingPlan 描述 model dependency、source identity、输入/输出/frame、cadence、age、pure computation 和 close owner。不把 LIBERO controller搬入Core |
| advance/state/fault | `NativeAdvanceReceiptV1`；`NativeIntervalEvidence`；`ExecutionFaultV1`；SelectedReferenceEnv mixed step caller | 当前 NativeAdvance 一次同步步进；RuntimeSession.step 按固定 substeps；可选 mixed physics-rate route逐步重算；ExecutionFault 可分 not/partial/advanced/unknown；没有通用 async ticket | sync completion fence 与有界 partial interval必需；只对精确支持的未来 route 声明 async ticket，不能返回正常 transition |
| resource close | `SelectedReferenceEnv.close`、`_close_failed_native_materialization`、`IsaacSimAppOwnerV1`、adapter `close_receipt` | Env 顺序收集清理错误；session 通用 close 返回 None；Isaac app/process owner 与 NativeIO/session分离，支持 lifetime hold；source/task resources另有 owner | 对各已有 owner 返回最小 close receipt；shared App 按 lease 释放，session 不直接关共享 App；1d 才定义 renderer sharing细节 |
| scalar/batch/worker | `vectorization/parallel.py::RemoteBatchVecEnv`、`runtime/providers/merged_scene.py::SceneBatchRuntime`；SelectedReferenceEnv | Remote batch 一个 worker可承载GeoPhys merged batch，不是每 env一进程；现无 Isaac batch adapter；physics route换配整批重建目标不同于 selected scalar route | 一个 batch identity绑定 route/device/layout与env→worker→row；partial reset须mask receipt；6a/6c实施 |

### 1c 双向操作／公开 owner 对照

query/build/reset/command/advance/publish/close 的字段、回执、副作用和失败见[physics-provider 协议](../contracts/physics-provider.md)。输入 owner 分别为 Artifact/Scene/source closure、ControlBindingPlan/Controller requirements、StateRequirements、reset sample/mask 和 execution route；adapter不得补造缺失的 task semantics。renderer 仅能作 query 前置需求，image/render 细节归 1d。状态 identity复用现有 StateBoundaryIdentity 和 StateSampleClock；命令复用 source-bound MixedActuator value。没有 general build receipt、request-specific capability result、async ticket与通用 close receipt的地方明确列为后续扩展，不写成已实现。

### D03/D04/D06/D07 的 1c 收敛

- **D03 夹爪 effort／传动：**维护者确认Panda一类8维Controller输入输出七个臂关节力矩N·m和两路手指关节力N；closure可作Controller内部目标。Scene/ControlGroup/Robot binding以具名通道声明，adapter验证tendon/mimic约束下可实现力域，不默认任意独立双指力。BodyWrench与JointEffort是独立类别，显式贡献组合后单一提交；finger position/mimic仍为compatibility。
- **D04 模型／反馈：**Controller 仅声明自身必须的 q/qdot/FK/J/M/bias/contact/force fields；在现有 ControlBindingPlan 绑定库依赖、source/model hash、semantic joint order、frame、cadence、max age 与纯计算/no-physics-step。LIBERO source MJCF model 是可参考实现，不是 Core ModelService；缺 required measure 不得填零。
- **D06 数值准入：**用 source closure、单位/坐标、质量/全惯量、axis/order/limits、actuator/transmission/coupler、reset readback和 task-required contact等模型项作为具名检查表；以具体 source oracle与指标定义容差。Panda cube约5%惯量差保留待确认，不引入跨 provider万能容差；optional未可读项带原因标NOT_MEASURED；required未测不能通过，3b补输入合法性、native mapping及reset/短程数值行为三层检查。
- **D07 command/action schema：**现有 mixed value绑定 Artifact/source closure/materialization/episode/reset/control step/revision/time，可作为 extension槽；位置 target继续兼容。physical command增加具名广义力/effort坐标映射、writer、interval与mapping receipt；action spec只在reset切换，batch保持共同布局；具体 codec/versioned value待4a。

### 1c 核对的官方资料

以下页面于 2026-11-03 查阅。它们支持协议术语和分层，不证明当前 Geochora adapter 或本机安装能力。

| 官方来源 | 对协议的影响 | 本仓库适用边界 |
| --- | --- | --- |
| [Isaac Sim 6.2 Newton backend](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/physics/newton_physics.html) | Isaac Sim host 可选择 PhysX 或 Newton；Newton engine/SDK 的 solver family 与宿主插件实际暴露的 solver 必须分开核实 | ExecutionSpec层级应区分host/engine/solver；Geochora没有Newton adapter，不得claim已接入 |
| [MuJoCo API functions](https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html) | `mj_step`推进仿真一个dt，`mj_forward`仅执行forward dynamics | 支持区分physics advance与参考模型计算；不证明当前model package版本/适配 |
| [Isaac Lab actuator concepts](https://isaac-sim.github.io/IsaacLab/main/source/concepts/actuators.html) | implicit drive由solver执行PD，explicit模型计算并提交effort；输出与limit owner不同 | 作为drive ownership和重复PD风险的概念旁证；latest页面可变，不当本仓库Isaac 6.2 API |
| [MuJoCo Python API](https://mujoco.readthedocs.io/en/stable/python.html) | `mj_step(nstep=...)`与循环多个`mj_step`等价；切片可能是native-buffer零拷贝view | 支持批量advance/borrowed data要声明完成和有效期；本仓库具体view以本地typed contract为准 |


### 1c 主审补充：复杂路线与实施责任

独立 Newton、Isaac 内 Newton、Isaac＋PhysX、Genesis 多 solver 和 SAPIEN 的表达边界见 [physics 协议](../contracts/physics-provider.md)；P2 改为 rigid＋FEM 及 required coupling 的明确设计例。仅表达扩展，不增加本版运行后端。参考 [Genesis v1.4.5 coupling](https://genesis-world.readthedocs.io/en/v1.4.5/user_guide/theory/coupling/index.html) 的 scene/solver/coupler 分工，不能将该官方能力当成本仓库能力。

夹爪力映射遵守明确 Jacobian 方向的虚功关系；参考 [MuJoCo actuation/transmission](https://mujoco.readthedocs.io/en/stable/computation/index.html#actuation-model)。若 q_native=f(s)，共轭关系为 F_s=(df/ds)^T*tau_native，不能据此唯一反解 native effort。当前 `control.py::feedback_value` 将 native force 投影为 closing magnitude，位置只决定 opening；不能把已存在的受限力读回写成位置估算。这些来源于 2026-11-03 核对，只用于设计及源码事实。

| 协议要求 | 现有代码 owner／需要修改 | 实施／验证位置 |
| --- | --- | --- |
| 分层 execution、能力结果及旧配置兼容 | `environment/configuration.py`、`artifacts/contracts.py` execution codec、`runtime/admission.py`／sessions admission | 3a：新值与旧 decoder 兼容、层级冲突／缺依赖／未实现拒绝；最终字段先经维护者冻结 |
| Scene 物理/资产表示、映射与兼容 codec | 既有 Scene/Asset contracts、declaration/assembly compiler、source owner；版本号仍为建议 | 3b：首批刚体必要字段、旧 Scene 解码/hash 和 native translation/readback；非刚体保留有类型扩展位置 |
| build/reset/advance/public state/close receipt | RuntimeSession、各 provider adapter、typed state owner | 3b/3c：真实 lifecycle、partial failure、旧状态失效、清理与重建 |
| Panda effort／传动与模型/反馈值 | canonical contracts、ControlBindingPlan、公开 provider 控制与 model binding | 4a/4b：验证符号／传动／力分配、反馈 provenance 和唯一 writer；Isaac position compatibility 不能充当 effort 完成 |
| Controller/action spec reset 切换 | Controller binding、SelectedReferenceEnv、wrapper/caller | 4c：action identity 更新、旧动作拒绝、obs 固定、Solution 复核 |
| 公开 scene/render 绑定、采样及数据生命周期 | render/camera owner、RuntimeSession 公开数据和 Env 调度 | 1d 设计；5a–5c 实施窗口/RGB/同步 obs／跨组合，不能另建 physics runtime |
| batch row/mask/整批配置重建 | vectorization、merged_scene 与各 batch adapter | 6a–6c：两个以上 physics provider，单独记录原生 batch/进程部署 |
| GeoPhys/MuJoCo 声明依赖冲突 | 现有环境/依赖配置 owner，admission 记录 readiness | 3a 明确方案，任何受影响的提前 native 执行前先处理；不预定隔离进程、不擅改 pin/依赖，既有环境与安装声明分开判断 |

该表是实施归属，不授权现在编码；1d 应加入完整 renderer／三方条款后形成阶段 1 最终追踪表。


## G01/1d Core↔renderer 与三方生命周期核实（attempt001）

本节限定于输入 Core `develop@8e70ee581602016932c99a257faad7aa6e5f91ea`、GeoPhys `67da1165149486d3ae3e779c13ce31af49e17d50` 的当前磁盘源码。CodeGraph 索引有待同步变更，符号定位后按 on-disk 文件核实；没有 sync/rebuild。该记录是设计依据，不升级任何 native/camera/batch 目标证据。

| Concern / owner | 当前源码与 caller | 当前事实 / 缺口 | 1d 决定 / 后继 owner |
| --- | --- | --- | --- |
| Generic UI render | `task_env/environment/env.py::BaseTaskEnv`、`TaskEnvRenderProvider` | `render_mode` 构建时固定；metadata 含 human/rgb_array；human lazily builds window、pump events、render+present，不推进 physics；rgb_array 读取 UI visualizer frame。与 task camera observation 分离 | 保持现有 UI owner；UI `.render()` 返回不作为 task RGB；5b 对三 mode 与 close/window behavior 接 oracle |
| Static camera sessions | `task_env/render/camera/api.py::CameraRenderSession/create_camera_session`、`mujoco.py::MuJoCoCameraSession`、`geophys.py::GeoPhysCameraSession` | legacy `ExecutionSpec`/same-provider profile `p1_4_native_camera_cpu_v0`；MuJoCo 从 static mesh 建独立 model+Renderer；GeoPhys 用 RayCamera/FrameBuffer/EnvironmentPipeline/LightingSystem/MeshPipeline/RayTraceEngine/TonemapPass 与 CPU Taichi；不证明 selected PickCube动态同步 | 准确名称写 capability matrix；5a/5c 从 public typed state 建绑定/更新，不把静态 session 写成同步 route |
| Selected task observation | `task_env/tasks/reference_env.py::SelectedReferenceEnv._reset/observation/step/close`、`task_env/observations/capture.py::DynamicCameraObservationConsumerV1` | reset 先 close/rebuild consumer，state reset/readback 后 observation capture；step 后 capture；Position 与 mixed step 错误会 close consumer并 fault；输出当前 HWC float32 `[0,1]` | 复用 consumer/Env observation owner；5c 加 phase 与完整 identity、cache invalidation、RGB frame receipt 和错误 receipt |
| Capture identity phase | `observations/canonical_camera/` geometry/identity/metadata 与 `capture.py` | config 的 `CameraGeometry.capture_phase` 固定 `post_control_step`；reset-first observation 也走同 consumer；validate 当前只收此 phase，不能辨认 reset 初帧 | 明确当前语义 gap；5c request/call-time phase=`reset_initial` vs `post_control_step`，为新 identity version 增 oracle；不修现有历史 evidence |
| Dynamic cross renderer | `render/camera/source.py::DynamicCameraRenderSourceV1.from_runtime_source`、`mujoco.py::MuJoCoDynamicCameraSession` | ExecutionSpec admission 是 GeoPhys CPU→MuJoCo native OpenGL/best_effort/Scene-v3 scalar joints；free_joints 拒绝。render-only MuJoCo session 更新 scalar qpos/time、kinematics/camera/light/update/render，不调用 `mj_step`/`mj_forward`，不执行 Controller；无 PickCube free cube binding | 保留 cross target；5a typed world-frame free body visual mapping + transform update，明确 no second physics; 5c state-bound RGB。旧 D05 evidence 使用不同 GeoPhys pin |
| Isaac app/camera | `runtime/providers/*`、`runtime/sessions/isaac_native_io.py::IsaacSimAppOwnerV1`、`UsdCoreRuntimeSession.close` | per-process/headless Isaac Sim 6.2 owner；F06 launch receipt `enable_cameras=False`；session close delegates NativeIO close/release lease，App owner最后关闭；无 selected task camera consumer | 5a/5b/5c 再定 exact 6.2 camera API、camera-enabled profile、render-only/pause update、per-worker App lease；不启动 App |
| State / image storage | `artifacts/state.py` `StateBoundaryIdentity/StateSampleClock/StateViewLifetime`、camera sessions `copy()`、canonical observations | state owner 已定义 typed identity/lifetime；native camera 输出 copies，但无通用跨 provider buffer/fence/lifetime contract | 复用 typed identity；5c image owned by default，borrowed 明示 owner/lease/layout/device/fence/expiry，必要时 copy/retain |
| Batch/terminal/render | `vectorization/parallel.py::_step_and_autoreset`、`vectorization/sb3.py::TaskEnvSB3VecAdapter.step_wait`、`vectorization/parallel.py::RemoteBatchVecEnv`、`runtime/providers/merged_scene.py::SceneBatchRuntime` | same-step done row 保存 `terminal_observation` 后 mask reset、附 `reset_info` 并返回新 reset observation；GeoPhys merged reset(mask) 另有 row semantics；Remote `get_images()` 将单 worker image list复制给每 env slot；当前 parallel tasks 只有 Pendulum/TwoWheelBalance，Isaac batch adapter absent | 6a–6c 明确 `env→worker→row→camera→image`；旧 repeated image 不冒充真实 per-row obs；done row terminal frame 需在 reset 前 copy/retain，env-0 lineage不变 |
| Observed shared resources | RuntimeSession, task/env, renderer consumer, `IsaacSimAppOwnerV1` | RuntimeSession 是 physics boundary；Env 协调 lifecycle；Isaac per-worker App owner支撑 process lifetime/lease；renderer native shared-scene adapter当前不一般化 | 复用现有 owners，以版本化 limited binding/lease连接；没有第二 ResourceManager/Recorder；close receipt由资源原 owner发出 |

### D01、D05、D07 的 1d 收敛

- **D01 构建前需求：**将 renderer/camera/window/App/device/context/worker/batch 的 required/optional 需求合并进现有 admission owner，与 physics、Controller、state 一起 query；unknown required 只有明确 adapter/build check 才能 provisional build。Core/GeoPhys MuJoCo 声明区间冲突仍归 3a dependency resolution，不在此包换依赖。
- **D05 render 组合：**保留三条物理路线及三种 render 完成目标。MuJoCo CPU、GeoPhys CPU、Isaac Sim 6.2.0.0 + PhysX/CUDA:0 的准确 camera/renderer 名称和 current gaps 见 [capability matrix](../capabilities/capability-matrix.json) 与 [render protocol](../contracts/render-provider.md)。跨组合候选仍是 GeoPhys CPU physics × MuJoCo native OpenGL renderer；现有 dynamic source free_joints rejection 与旧 pin evidence 不能算 PickCube 支持，也不减少必达 cross target。
- **D07 frame/state identity：**state field 仍由既有 StateBoundaryIdentity/Clock owner定义；render frame 组合 env/worker/row/camera/state revision/config/topology generation/capture phase 与 device completion/lifetime。reset-initial capture phase 当前未表达；交由 5c 增版本值，不修改旧 state codec/hash。

### 五协议联合设计审阅边界

本包只读了 unified representation 与 control-and-feedback 正文；不修改它们。建议维护者接受统一术语：具名 entity/frame/asset visual mapping 属 representation owner；Renderer 消费 physics 已发布 boundary，不获得第二 physics authority；image/frame lease 隶属生命周期 owner；对旧 schema 只 additive/versioned 扩展。首要待确认项是 reset capture phase 新值/迁移，以及 task RGB 必需失败后 fault receipt 与现有 Env error接口如何汇总；完整条款→owner→5a–6c oracle 见 [protocol implementation map](protocol-implementation-map.md)。协议维持 draft。

### 1d 核对的官方资料

以下官方页面于 2026-11-03 查阅。它们只佐证外部 API/术语概念，不能证明当前 checkout 的适配器、精确依赖或运行能力；`stable/latest` 页面可能晚于本包要求的版本，实际 implementation package 必须按目标安装重核版本。

| 官方来源 | 仅采用的概念 | 限制 |
| --- | --- | --- |
| [Gymnasium Env API](https://gymnasium.farama.org/api/env/) | 构建时 `render_mode`、metadata、human/rgb_array 与 close 的调用习惯 | 不代表 reset rebind、task observation 或任意 wrapper 兼容 |
| [Gymnasium Vector Autoreset API](https://gymnasium.farama.org/main/api/vector/autoreset/) | same-step 模式中终止 observation 与 reset observation 是不同边界 | 本仓库具体 key 是 `terminal_observation`/`reset_info`，wrapper-specific |
| [MuJoCo Python API](https://mujoco.readthedocs.io/en/stable/python.html) | renderer/model/data lifecycle 与 Python binding 概念 | stable 页面版本不等于 3.8.1；不宣称精确 API match |
| [MuJoCo rendering](https://mujoco.readthedocs.io/en/latest/programming/rendering.html) | OpenGL/Filament 渲染路径、同步/readback completion 要单独处理 | latest 可能比 3.8.1 新；仅作为 completion 概念参考 |
| [Isaac Sim 6.2 camera sensors](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/sensors/isaacsim_sensors_camera.html), [camera migration](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/migration_guides/isaac_sim_6_0/sensors_camera_to_experimental_rtx.html) | 6.2 camera sensor、tiled camera、annotator device 与实验性 RTX API 迁移 | 文档能力不等于 GeoChora adapter；未来需按 exact build 审阅 experimental API |
| [Isaac Sim 6.2 Replicator workflow](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/replicator_tutorials/tutorial_replicator_sdg_workflows.html) | explicit render wait、frame correspondence、physics 与 capture update 可分离讨论 | 不代表当前 F06 camera-enabled，也不作为 runtime evidence |
| [Isaac Sim 6.2 core API migration](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/migration_guides/isaac_sim_6_0/core_api_to_core_experimental.html) | SimulationManager stepping 与 RenderingManager/Replicator render owner 区分 | API迁移与精确 package generation 必须未来核验；没有导入/启动 Isaac |

官方说明正文及 source facts 的分工见 [render-provider](../contracts/render-provider.md)、[lifecycle-and-data](../contracts/lifecycle-and-data.md)、[physics-provider](../contracts/physics-provider.md)。

## G02/2a PickCube 失败归因（attempt001；交付与主审）

输入 Core `develop@fcf0700a5ddaff85e7beb190f018d9f71d94100b`、GeoPhys `67da1165149486d3ae3e779c13ce31af49e17d50`。本记录基于当前源码、旧 F06 原始公开轨迹和一条当前 MuJoCo CPU seed31 运行；旧原件只读。完整逐样本映射、执行资源和 hash 见[诊断报告](../../../../../workspace/maintenance/v211_g02_2a_attempt001/report.md)与[历史对齐表](../../../../../workspace/maintenance/v211_g02_2a_attempt001/historical_time_alignment.json)。

| 链路位置 | 当前事实／本次样本 | 归因边界与 owner |
| --- | --- | --- |
| Task action → R3 | `SelectedReferenceEnv.step_expert` 将 task-owned Solution 的 8D world absolute pose/quaternion-wxyz 请求传给 `controller.compute`；R3 生成 `q_ref` 与 position-servo target，速度上限 4 rad/s。 | 这是当前 R3 位置兼容路径；不是已批准的 7+2 effort 实现。任务策略留在 PickCube owner。 |
| R3/adapter → public state | seed31 attempt 227 请求 TCP `(0.635134,-0.086464,0.753000) m`；控制器诊断 position error 为 `(+0.034243,-0.004555,+0.036945) m`。末样本 `q_ref_next` 与实测 arm q 的最大绝对分量差约 `0.00821 rad`，实测 qdot 已接近零，但公开 EE site 仍在 `(0.600891,-0.081910,0.716055) m`。 | 末样本不支持“只因关节速度还高、仍在快速追赶”的解释；仍未区分目标/reference/TCP site、IK/ref dynamics 与 native servo 的贡献。不得把关节 q_ref 接近误写为 TCP 到位。 |
| Public state → measured gate | cube center `(0.635134,-0.086464,0.487628) m`，顶面 z=`0.512628 m`；末样本 TCP 高于顶面 `0.203427 m`（需 `0.215 m`）且 XY 误差 `0.034545 m`（需 `≤0.010 m`）。100 个连续 gate-hold 样本全未通过；高度样本范围约 `0.194860–0.210789 m`，XY 误差范围约 `0.025405–0.067145 m`。 | `PickCubeReadinessSolution` 在 `over_cube_before_descent` 等待上游 measured state，hold 到 100 tick 后失败。0.215 m 来自当前 `0.12+0.10−0.005 m` waypoint/headroom 几何；XY 门限来自当前任务 gate。 |
| Gate → Expert/task result | attempt 227、仿真 `2.26→2.27 s`，报 `measured_tcp_clearance_timeout:over_cube_before_descent`；未进入下降/关爪。Cube lift `0.000628 m`、opening `0.0799995 m`、grasp/lift/task-success/Expert-complete 均 false；runtime、记录、close 成功。 | **近端失败机制**是本 seed 的 measured-TCP gate 未满足导致 Solution timeout。夹爪 grouped interval 对 `inner_gripper_step` 的静态缺口是后续风险，但本次失败发生在它相关的关爪阶段之前，不能作为本次根因。 |

本次 run 的 trace SHA-256 `7d1b30b1ae51f05dbedfd8e87c06d89323a4af17c8b14e350ddaa755b5ba9325` 与 F06 MuJoCo seed31 trace 字节级相同；artifact 相同，但源码身份不同：当前/F06 `solution.py` SHA 分别为 `4543df1cdc6f89ca99c300923a90e360ae19e4cab4762702b98e9f86eb1b1266` / `9d7e8d24961a2253585a2eb3b995f21183f34c64a7d65da2666d64f22e8e61c1`，`production_r3.py` 为 `e14532c684dd14488d8f040cbd9188acc7cd1cd754eeb55f27c5aced30022c72` / `8364b5424419946f778e12255d2519ab966e1fe7f9091ec54035090c2d30bc56`，`task.py` 为 `80cccad2944401d13bbffbdcf5284ac68fad60b1371a155f29c020b068cc08aa` / `35e7b4f592b81314e966623230a9155252aa6c11862da53700a11f86431a3902`。因此它支持 seed31 失败机制在当前输入上的重现，不能证明旧新实现完全相同，也不把 R3 版本相关性当因果。F06 seed33 在 attempt 192→193 通过 clearance gate，是对“所有 seed 均无法过 gate”的反证；seed32/33 后续未抓取发生在不同的 close/horizon 阶段。

2b 最小候选归属 `task_env/tasks/pick_cube`：对 requested world TCP、R3 reference、`panda-v1/ee` 公开 site 和 cube-frame 的逐控制边界差值作定向比对；据结果仅改必要的任务 hover/侧移 waypoint 或推进时序，保持 measured gate、lift oracle、碰撞、reset/source 和 public lifecycle。代表 seed 固定31；当且仅当 gate 推进到关爪，才单独检验 `servo_opening_m`、finger q/qd、readiness 与每个 2 ms 子步内环调用。此为 2b 方案，不授权本次实施。


### 2a 独立主审补充（2026-11-04）

决定 `ACCEPTED_BOUNDED_2A_DIAGNOSIS`，依据[Sol复审](../maintenance/reviews/20261104_2a_sol_review.md)中的原包与维护者追加诊断，不单独以gate失败重述当上游根因。当前纯模型FK在原227个pre-step边界与public TCP位置最大差6.96e-16 m；同run内部诊断的q_actual/H5对齐、J/SVD/DLS独立重算一致。当前权重0.22、阻尼0.02下，末段修正twist几乎完全沿最弱左奇异方向，qdot仅约0.00020 rad/s；速度干预另证明点列速率是动态误差放大项。4 rad/s内部诊断与2 rad/s `_002` 不拼为同run；后者关闭碰撞、外部重放，未证明任务gate或完整成功。2b首选Solution姿态路径单因素干预与任务级修复，沿既有specialization对齐Controller/planner；若到达close后证实内环缺失，复用 `RuntimeSession.step_control_interval` 和原binding修复，禁止第二physics step。共享R3算法、原生源/约束与阶段4协议不提前改写。

### 1d 主审核对与建议

- `TaskEnvRenderProvider.render` 当前 human 返回 None、rgb_array 返回 HWC float32 `[0,1]` 数组；`CameraGeometry` 和 `normalize_rgb` 已可构建选择 float32/uint8、HWC/CHW。不把 adapter receipt/leased frame 直接作为公共 `.render()` 返回，不将改默认 dtype 作为本版无理由迁移。
- `parallel.py::_step_and_autoreset` 与 `TaskEnvSB3VecAdapter.step_wait` 是两个 caller；`utils/tree.py::tree_index` 当前对 NumPy 叶子 `.copy()`，终止快照在 reset 前保留已有依据。未来 GPU/borrowed image 扩展仍须在覆写前 copy/retain，不能据现有 NumPy 行为推断全部 device route。
- Generic UI owner 当前仍调用 visualizer `_refresh_render_snapshot`、`_render_frame_to_buffer`、`_synchronize_taichi_runtime` 等下划线方法；这是现有适配的边界欠账，不能当成目标 public renderer binding 已具备的证明。5a/5b 须通过正式公开/runtime-facing renderer 操作收敛，不继续扩散私有访问；若需改 provider API/pin，按包单独冻结。
- 同一 batched step 中未 done row 会正常推进；“保持未选 row 不变”仅指其后的 mask reset，不是整个 step。P4 的 terminal retain 必须位于覆盖缓冲区的 reset 前。
- P5 改为固定 GeoPhys CPU physics 下 renderer A→B→A，独立检验 render选择；后端+renderer联合切换另列后续3c/5c集成条件。当前两个动态 renderer 仍未实现，不新增任何能力证据。

主审建议使用版本化 actual capture phase（reset_initial/post_control_step）、沿用现有 RGB 默认并允许构建显式选择、公共 observation/Recorder 独立存储而 device lease显式选择、独立 window close只停展示而 required capture fault。详见 [主审记录](../maintenance/reviews/20261103_1d_sol_review.md)，最终协议冻结由维护者决定。

## G02/2b attempt002：R3 对齐后复测（2026-11-04）

九份人工源输入已整合至提交 8fba7f8ff0d47f7de8e5ced53f2ecdeb21869238。PickCube seed31 成功 960 transitions，seed32 在 1000 tick horizon 失败；NutAssembly seed19 成功 2377 transitions。四份 MuJoCo HDF5 均独立读回通过，task 成功与 runtime 有效性分开记账。

PickCube/NutAssembly 使用共享 R3 arm/execution wrapper 与 planner profile；两者仍有 task Artifact/source/scene/reset/Recorder identity 差异。GeoPhys 当前实跑在 PickCube Solution 的边界时间 guard 抛出 stale execution time；原始 run 没记录当前/期望 simulation_time，因此 provider 级根因未定。Isaac delivery 的 77 个文件 hash 匹配，但 GPU admission 不稳定而未启动 native worker。详见[中止记录](../maintenance/reviews/20261104_2b_closeout.md)和[成功参考冻结页](../maintenance/reviews/20261104_2c_reference_freeze.md)；同run原始H5、readback、trace、worker_result与supervisor保存在 `/home/lly/.codex/worktrees/v210-integration/Geochora/workspace/maintenance/v211_g02_2b_attempt002/`。

旧2b在维护者中止时G2 FAIL、G3 PARTIAL、G5 INCOMPLETE_USER_PAUSED。Sol在保留旧包结果的前提下，现已按原G02出口有界接收代表实现及2c参考冻结，见[阶段2主审](../maintenance/reviews/20261104_2c_sol_review.md)。阶段2收尾，阶段3未开始。

## 当前协议基线与后继实施

维护者于2026-11-03确认五协议，详见[确认收据](../maintenance/20261103_protocol_baseline_confirmation.md)。历史1b–1d建议与当前冲突时，以权威正文的7＋2、BodyWrench、嵌套主体、贡献组合、公共可替换模型、同一Env切换、Core随机流和timebase规则为准；原始报告不改。新增[控制命令案例](control-command-cases.json)仍为planning-only。
