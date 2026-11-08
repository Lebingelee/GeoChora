# G05 5c 人工诊断：统一主体、嵌套控制、Runtime 与 renderer 边界

2026-11-08。维护者明确：统一控制主体、环境搭建和任务语义应覆盖既有多层嵌套 Robot，Pendulum／双轮车是同一机制的单层情形；渲染是 5c 主线，公共 runtime/state 不依赖任一 renderer，renderer 专属适配放在 renderer 边界。下述为 Sol 静态审计及诊断方向，不表示改造或新 native 验证已经完成。既有控制、render 和任务行为的有界接收保留，必须按实际改动验证兼容。

## 1. 多层嵌套是否已经保证？

**设计和部分代码具备基础，当前统一生产链尚不能保证。** [控制协议](../contracts/control-and-feedback.md)要求嵌套主体与组件具名通道、可有多个 Controller、显式聚合与唯一提交；不引入第二个 Robot runtime。已有 `task_env.artifacts.logical_assembly.LogicalAssemblyV1` 通过 entity member、subcomponent ref 和 nested member 表达路径和引用；`resolve_logical_assembly` 对具体版本限制为最多 32 层、1024 个 leaf，并验证 Scene pin、子装配 identity、环、别名与路径冲突。`compile_physical_control_binding` 将完整 component path 解析到 Scene joint；`PhysicalControlExecutionV1` 与 typed command batch 支持多个具名 Controller、显式冲突／组合及一个控制区间。4a 的接收是有界合同和代表构造/提交证据；4b 三后端是特定 Panda effort 配置，不证明任意嵌套结构或 provider 全部可运行。

Sol 在禁止 SDK/provider 导入与任务 XML/MJCF/USD/URDF 读取的守卫下独立运行多层引用解析、32 层边界、嵌套命令贡献/过期拒绝、两个不相交 Controller 的同区间合成四项测试：4 passed。它们使用合成声明，只证明合同处理，不证明 Pendulum、双轮车、嵌套实际 native 或渲染已统一。

当前 Pendulum/双轮车通过 component `TaskDefinition.create_action_adapter` 直接生成旧 `ControlCommand`；selected 的 physical execution 又受 `position_profile` 准入。即便可以把单层主体在逻辑上看成单节点 Assembly，目前也**没有证据表明现有两任务的构建、控制、state 和 render 已接入那条 Assembly/physical binding 生产链**。不能以两种各自独立实现声称支持嵌套，也不能把另建的特例 Controller wrapper 当作统一。

后续实现应复用已存在的 Scene/LogicalAssembly/控制 binding 与一个 Env 生命周期 owner，而非再造一套独立图和第二物理 runtime：单层使用根 Assembly 及其叶，嵌套使用同一解析器和全路径；每个 Controller 的 state、输入、命令和资源指向解析后的具名实体/通道；多个贡献经同一命令编译/聚合提交；保留 source 与 Scene identity、所有权和冲突拒绝。是否可无损复用现有具体类/API，必须实作与验证后确定；`PhysicalJointChannelV1` 当前只覆盖其声明的 revolute/prismatic 力矩/力，不能据此承诺任意 DOF、传动或 provider。

验收至少包含：两个任务各自真实 public 构建→主体与 Controller binding→reset→固定 action step→单次命令提交和状态/时钟；Panda 与既有多层嵌套代表同一解析/binding/提交语义的受影响回归；单层/嵌套路径、主体重名、重复引用、控制通道冲突、多个 Controller、正确目标及无重复物理实体/施力的测试。对未修改的原 4a/4b 证据按身份复用；如迁移改变它们的生产链，则补有界真实代表回归，不预设全 provider/任务矩阵。渲染作为同一状态消费的代表端到端结果继续验证。

## 2. 两个 source 类型与实际 Runtime

`RuntimeSource` 和 `UsdRuntimeSourceV1` 是**构建/物化输入声明**，记录 Task/Scene、资产表示/来源 closure、joint/body/frame/actuator 名称映射等；它们本身不是在 step 的仿真 Runtime，也不会因存在两个 source 值而运行两套物理。Git 历史显示 USD 类型由此前 F03 source/state 契约提交 `ed951129` 引入，早于本次 5c；003 引入的是把仅接受另一 source 类型的 renderer-only 绑定无条件放进共同 reset 的回归。`UsdRuntimeSourceV1` 绑定已验证 USD delivery、representation、TaskArtifact 和 Scene identity；不只用于资产浏览，也给后续 provider materialization 提供来源与映射。它并非 Isaac 专属类型：源码中也有受限 GeoPhys/USD 路线。

selected 路线现有一个概念上的 `RuntimeSession` Protocol，提供 reset、step、snapshot 等接口，`materialize` 按 source、execution 和 capability 创建 MuJoCo/GeoPhys/`UsdCoreRuntimeSession` 等不同实现；底层 provider/进程/设备不同不等于公共层应有不同语义或多个并行物理 Runtime。**但组件任务当前确有另一套实际运行入口**：`bootstrap_task_runtime` 直接构造 GeoPhys runtime/`GeoPhysRuntimeBoundary`，消费 `RuntimeSnapshot`；selected 使用 `RuntimeSession`、source-bound state 等。两者都由同一个 `SelectedReferenceEnv` 类型承载，并不意味着已经统一到同一个生命周期接口。这是需要正视的兼容／收敛工作，不能只改两个 source 类型名。

目标应是每个环境拥有一个统一的**公共运行时契约和生命周期 owner**，对具体 source 表示和 provider 通过 adapter/typed representation 降低；独立 Env 可以各有实例，batch 可有共享的底层 runtime，独立 renderer-only visual model 不构成第二物理 solver。不同文件格式/资产 closure 可以是不同的 versioned payload，不必损失 USD／MJCF 语义或伪造为同一格式；不允许公共状态/任务/控制逻辑因 source Python 具体类或 renderer 的需要改写共同语义。现有使用 `type(...)` 的 admission、source/hash、历史 receipt 和 renderer ownership 都须有兼容迁移，不能靠更改继承或绕过 provenance 消除报错。最终具体共用接口需根据现有 RuntimeSession、RuntimeBoundary、状态与 capability 审查后确定，不主张预先新造第二 runtime manager。

## 3. Panda 与 Position 假设分布（按位置，不代表每项都是无效代码）

| 代码位置 | 可核对的现状 | 诊断归类和要求 |
|---|---|---|
| `controllers/canonical/position_profile.py::PandaPositionServoProfileV1` | 要求 7 个 arm、2 个 finger，含 hand/TCP/gripper/源映射 | Panda 专属 profile 内的有效假设；保留其准确能力和既有行为，不推广给所有主体。 |
| `runtime/sessions/control.py::bind_selected_controller` / `is_admitted_position_profile_set` | 按 Panda profile 或 leaf plan 设置 selected 的 `position_profile`；相关 materialization 有具体 Panda/双实体 source 映射与限界 | 历史有界控制准入不等于通用控制类型；抽离通用 controller binding 的同时保留受限分支和安全检查，不能仅删 allowlist。 |
| `environment/reference_env.py::_initialize_selected_value`、`_prepare_reference_reset`、`_prepare_reference_step` | 以 `position_profile` 分流控制准备、typed state 和 observation；physical-control admission 也要求该标志，Isaac direct-effort 因而仍依附 Position 候选 | 控制行为、state 发布及物理 admission 发生耦合，不能以位置模式决定通用 runtime 或 renderer 接入；需拆职责、维护既有 control switch/reset 语义。 |
| `environment/reference_env.py::_build_runtime_with_rollback`、`_reset_episode_components`、`_convert_action`；`robots/runtime.py::RobotRuntime` | component 分 `env.robot.controller` 与 task action adapter；`RobotRuntime` 含 PandaGripperController、base、ee；Env 直接查看 gripper、robot 来决定部分 snapshot 请求 | 通用主体/Controller owner 不应要求 end-effector/夹爪；对应能力由机器人或具体 consumer 声明，必要采样按实际需求协商。 |
| `environment/configuration.py::resolve_execution_plan`、`environment/config.py::RobotConfig` | component 静态计划至多一个 agent，显式识别 `panda-v1` 的 controller 种类；RobotConfig 有默认 GripperConfig | 单 agent 与多层逻辑组件不是同一概念；当前组件公共流程有真实限制。配置解耦需保留旧 Panda API 默认行为和配置 identity。 |
| `assembly/references.py::AgentReferences`、`assembly/compiler.py` | ref 既有通用 joint/actuator 列表，也有 arm/gripper/ee 必需字段及 Panda 专门分支；compiler 含 empty tabletop/Panda 特定 source 和初始夹爪处理 | 将 Panda 兼容映射局限到其 scene/agent adapter；通用引用不能强制无夹爪主体合成假 gripper。任务专属 compiler 本身并非错误，错误是将其变成所有任务构建前提。 |
| `observations/selected_reference.py`、`environment/metadata.py` | selected 参考投影含 ee、Panda 9 关节和 7+2 叶；metadata 有 8 维 Panda universal-action fallback | 作为明确的 PickCube/Panda 投影或兼容输出可保留；公共任务语义与 observation/action spec 必须来自声明，不能让默认值伪装成其他主体能力。 |
| `render/camera/source.py::DynamicCameraRenderSourceV2` 和 `reference_env.py::_prepare_task_rgb_state_binding` / `bind_visual_state` | V2 是 source/scene/映射受限的独立 renderer 绑定，003 将其提前用于所有 selected RGB；旧 visual binding 亦限定 MuJoCo CPU Position publication | 已确认 Isaac USD 回归；公共发布不依赖某 renderer/source 具体类；旧有限接口保留兼容且不冒称通用。 |
| `runtime/bootstrap.py`／`runtime/boundary.py` 与 `runtime/sessions/*` | component bootstrap 直接依赖 GeoPhys；selected 则经 RuntimeSession 和 provider materialization | 不是仅 Panda 名称问题，说明统一运行时消费和任务生命周期尚未完全实现。重构按受影响范围有边界推进。 |

此外 `api.py`、`control.py` 和 provider adapters 中存在 F06/F05 等明确限定 source、asset、物理映射、build 和能力的 admission；其中很多是历史证据支持的安全边界，不因搜索到 Panda 字符串就应删除。需要将“特定候选的合法约束”和“进入公共路径的默认假设”分开，保证 refactor 不放宽原约束或转移错误的 qualification。

## 4. 公共状态与 renderer 的边界

统一任务/场景、受控主体/Controller、runtime 公开状态、boundary 和 clock 的语义独立于 renderer；启用 task camera 时，采样协调器在同一已发布 boundary 上请求 render，等待真实完成，再输出帧/receipt。renderer 可以声明受限的 state、visual representation、设备和 source provenance requirements，但它的 source payload、model、context、native 映射和转换在自己的 adapter／capability admission 中处理；不把某一个 renderer 的具体类、资产格式或 topology 硬塞入所有 Env 的 public source/state 类型。可由公共层对 capability 缺口作有依据的 fail-closed；这不表示应取消安全/identity 校验，也不允许 renderer 写回 physics/Controller 或推进第二求解器。

Isaac USD 类型回归先按该边界修复并作受影响闭环；GeoPhys native、MuJoCo native 和 GeoPhys→MuJoCo 的既有成果按改动实际影响复用或做最小回归。不要用一个仅适合 Pendulum 的新适配器取代已证明的嵌套能力，或以单个 DTO 统一名称但保留多个互不一致的运行时语义。

## 5. 诊断顺序与边界

(1) 梳理 public Env→task/scene/subject/assembly→Controller→provider 与 state→task/renderer 的现有两条路径和 source identity；明确能复用的 owner、协议与特定限制；(2) 设计兼容单层和多层的真实 binding 路径及一个公共 runtime 生命周期/状态契约，对现有 selected 和 component 采用可验证迁移，不改变任务 reward/reset/action；(3) 在 renderer adapter 边界解决 USD/MJCF 接口假设，保留 identity 和同步；(4) 按能力与代码影响实施和进行上述分层验证；(5) 整理仍不能支持的 source/physics/renderer 交集。两个优先缺口——统一控制主体/Controller 与 Isaac 受影响 RGB——均不以空 schema、假通过或历史 hash 替代真实链。

当前为维护者主导人工诊断；本审计本身不启动新实施窗口、source 解析、native/SDK/GPU/GUI，或自动派包、阶段 6、merge/push/tag/发布。后续实施需要可审阅的具体工作包、资源预算与维护者授权，并由维护者手动转发。
