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
| D02 | 统一表示映射到哪些现有 schema，保留哪些兼容输入 | 1b | 优先扩展现有 owner，不凭讨论新建完整物理语言 |
| D03 | 夹爪 effort、传动、mimic／tendon 和现有 native 兼容路由 | 1c、4a | 逐通道声明；不能把 arm torque＋finger position 称为全 effort，不重开 F05 严格等价研究 |
| D04 | 模型服务的库依赖、反馈频率和缺失能力 | 1c、4a | Controller 不依赖 live provider 私有状态；可替换参考模型依赖需显式记录 |
| D05 | batch 的具体两个以上后端、auto-reset 及图像布局 | 1a、1d、6a | 当前 native batch 是 GeoPhys merged rigid；CPU/CUDA 不算两个 physics provider。Isaac Sim/PhysX/CUDA 是建议第二 provider 候选，需新增 batch adapter；现有 remote vector 是 same-step，图像布局尚未接通 |
| D06 | 数值准入和跨后端容差 | 1a、1c | 锚定 Panda source closure 与 PickCube cube/tendon/接触参数；用公开模型读回和 task source 定义各量 oracle。跨 provider 容差须由具体指标来源批准，审计不外推万能阈值 |
| D07 | 具体 API 签名、action-space 变更和旧 wrapper 兼容 | 1c、1d、4c | obs 固定；动作规格变化显式报告，不承诺旧 Agent／learner 无缝继续 |

这些是协议／执行准备工作，不要求维护者提前指定类名、库实现或全部数值。需要产品语义判断时在该项讨论中集中提出，不能静默替维护者改变范围。

## G01/1a 当前源码核实（attempt001）

| 路径／owner | 当前事实与边界 | 后续 owner |
| --- | --- | --- |
| `task_env.registry.make_env` → `configuration._resolve_selected_config` → task factory | `make_env` 是单环境公开入口；显式 task config 按配置优先级解析后调用选中 task 的 `from_resolved_config`／`from_reference_config`。Selected PickCube 固定 P1.6、R3、GeoPhys CPU 默认；renderer 仅接受 none。 | 1b/1c：统一表示和 admission；3a/3b：精确配置及 route |
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
