# E00～E04 剩余实施账本

日期：2026-11-12。核查输入：`b94e86250140bffebc27bf92b2e8aec60688b7e4`，分支 `codex/v211-stage5-diagnostic`。状态：`REPLAN_ONLY_IMPLEMENTATION_NOT_RESUMED`。

本账本是[总台账](post-5c-code-project-optimization-diagnostic-ledger.md)在 E00～E04 范围的实施视图。它承接维护者最新的四任务、退休入口及版本诊断要求；不替代总台账，不重置原执行历史、attempt 或资源账，不启动暂停中的 Goal。可替换旧提示的[调整后 Goal](post-5c-e00-e04-goal.md)与本文配套。

## 0. 使用方法与剩余工作量

后续按 **U1 共同构建闭环 → U2 生命周期／资源闭环 → U3 动作／提交闭环 → U4 调用者与诊断收口 → U5 定向复验与事件接收** 推进。每个大单元包含实现、必要修复、适量验证、记录压缩和本地提交；不把每个小格变成一次新派包、审计窗口或 native 运行。

本文列出 **30 个闭合检查点：6 个已确认需要调整实现职责的项目，24 个有既有实现或证据、需核实并按需补齐的项目**。它们不是 30 个已复现 bug，也不是还剩某个百分比。主要新增架构工作集中 U1；U2／U3 以已有公共机制的收敛、重复逻辑整理和缺项修复为主。U4／U5 负责结束这些事件，而非再开一次全仓审计。

标记：`改`＝当前源码能定位的职责／流程调整；`核`＝已有机制的闭合核查，证据充分时原样保全，不要求必改代码。初始均未由本次审查签收；实施者将状态更新为 `PASS`、`IN_PROGRESS` 或明确的 `OPEN`，并填最终符号／提交／证据。最终 `NOT_APPLICABLE` 仍须维护者同意。不能把待核项直接升级成缺陷或强制新增测试。

单元内只读本账本、本单元实际代码及必要规范；完成大单元后，再对照第 9 节列出的总台账条目一次。发现范围外问题集中进入第 8 节，不据此跳到另一个小补丁。只有会破坏当前单元正确性的真实依赖或故障才立即处理。

## 1. 冻结现状与需要保留的成果

### 1.1 输入、统计与可信边界

- 输入 HEAD、两个 pins 与维护者提供的状态一致；tracked dirty 仅为[执行记录](post-5c-optimization-execution.md)末尾的既有追加。该 dirty 文本及四个 untracked 输入均按原字节保护，本次不整理或提交它们。
- GeoPhys：`c1ea3cc9fb99ccbd1d31c36d6fc7b84aa936b3d7`；Menagerie：`b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。
- 本次采用 CodeGraph 定位，再核对其标记 drift 的实际磁盘源码、AST、Git diff 和既有运行计划。没有导入生产模块、解析 MJCF／USD 资产或运行 pytest／native／GPU／GUI。
- 与 `1f1359ee` 比，生产 Python 的 `git diff --no-renames` 涉及 109 文件，+5,343／−14,441，净减 9,098 行；版本诊断新增 17 文件、4,270 行。项目 tracked 文件为 1363→1363。数字独立复算一致，不等于事件接收。
- `reference_env.py` 为 4397 行，PickCube `specialization.py` 为 1196 行（启动时 1046），Nut specialization 为 537 行，`reference_binding.py` 为 575 行。PickCube 候选文件虽已删除，其 Task 内仍有 source／Controller 构造编排；不能只按删行或 candidate 目录是否消失结案。
- 基线到输入共有 198 个提交，包含文档提交；不能以提交数推断耗时原因。但当前记录没有给出一个可逐格结束的剩余闭环，继续逐函数发现、修补和短测容易重复触及同一调用链。

原始冻结信息、dirty patch、保护输入及已读源码摘要见[本次输入快照](../../../../../workspace/maintenance/v211_e00_e04_replan_20261112_001/input-snapshot.json)。文档提交后的 HEAD 不冒充上述生产输入。

### 1.2 事件判断

| 事件 | 当前判断 | 保留内容 | 真正剩余 |
| --- | --- | --- | --- |
| E00 | 启动基线成立，后续持续对账 | 输入、保护、pins、统计和既有证据身份 | 在单元边界更新实际输入／输出及证据，不另开“再审一遍基线”的实施循环 |
| E01 | 四任务共同配置与入口已有实质实现，待收口签收 | 五个规范 section、共同 resolver／resolved 类型、Robot 默认选择、旧 UID 退休 | 核实四正式 caller 不回退 component，迁移触及的现行例子；无需再重写一套配置系统 |
| E02 | 声明、绑定与共同请求已有成果；主要架构欠账仍在构建内部 | Robot recipe／主体、Controller 匹配、TaskBuildRequest、运行视图 | U1：Task 内还选择、组装 source 和 Controller；共同请求之后仍由任务执行较大构造流程，需把阶段编排交现有公共 owner |
| E03 | 共同生命周期及多项关闭修复已实现；完整阶段／资源对账尚缺 | EpisodeExecutionState、统一 reset reconstruction、source／worker cleanup | U2：跨构造失败、reset 事务、publication、worker／App／相机资源的闭合；没有依据判定每条当前都故障 |
| E04 | 共同 dispatcher／submission 已真实接通；入口及失败语义需收口 | typed 命令、interval、source-bound Controller、调用方 Solution 及部分拒绝检查 | U3：动作入口支持表、兼容提案转换重复、失败副作用、序列／混合能力的实际支持范围和最终证据 |

### 1.3 已有实现，禁止反复重做

| 编号 | 当前事实与定位 | 后续处置 |
| --- | --- | --- |
| K1 | [registry.make_env](../../../../../task_env/registry.py) 对四正式类进入共同 `from_resolved_config`；四类已声明 `uses_selected_public_config` | 保留。`_resolve_task_env_config_impl` 的 component codec 仍有范围外 caller，其存在本身不再阻塞 E01 |
| K2 | [configuration._resolve_selected_config](../../../../../task_env/environment/configuration.py) 对四任务使用 `execution/episode/task/controller/robot`；Controller profile 和 execution 已有单一 resolved 来源 | 保留严格冲突／unknown／身份检查，不恢复已退休的顶层别名或旧输入 |
| K3 | [ReferenceTaskBinding.build_for_request](../../../../../task_env/environment/reference_binding.py) 使用同一 `TaskBuildRequest`；`_StandardResetReconstruction` 统一初构与重建；`SourceBoundTaskBuilder` 已负责复用／重建策略 | 扩展和实际消费这些 owner，不新建另一套 UnifiedBuilder 或 Runtime |
| K4 | [RobotRuntime.from_selected](../../../../../task_env/robots/runtime.py) 已以可选 Panda 便利字段暴露真实主体与 Controller，声明对象被构建与 reset 复用 | 不再把简单主体缺少 gripper／ee 当成未完成；仍须用构建过程证明声明生效，不能只看运行视图 |
| K5 | [build_selected_runtime](../../../../../task_env/runtime/sessions/selected_materialization.py) 已按已绑定能力选择 RuntimeBuilder，Position／effort initializer 合法分开 | 不以多个 builder／typed state 类为重复 Runtime 的证据，不强迫所有 Controller 改为 torque |
| K6 | [control_lifecycle.prepare_selected_control_action](../../../../../task_env/runtime/sessions/control_lifecycle.py) 及 [submit_control_command](../../../../../task_env/runtime/sessions/control_submission.py) 已是共同控制／提交 owner | 保留 Position、effort、native-feedback 不同 lowering；检查实际 caller 的汇入和消费，不只再加共同 receipt |
| K7 | 既有 source、worker 清理，stale 拒绝和 Solution 副作用失败已有定向诊断；多份短程原生结果已保存 | 按本次改动影响复用。281 项通过是实施记录的既有结论，本次没有重跑；旧结果不自动等于最终代码实测 |

## 2. U1：完成四任务的共同构建闭环

**对应：E01／E02，必要的 E03 构造边界。依赖：现状 K1～K5。** 分类为 `EXTEND_EXISTING + COMPOSE_EXISTING`。这是最大的剩余实现单元，应一次冻结完整阶段和接收方，再连续完成，不再每发现一个 Task helper 就单独返包。

目标流程为：规范配置 → Task 声明／默认选择 → 选定 Robot 声明和 source 组合意图 → 已准入表示的 source 编译／最终主体绑定 → Controller 构造与绑定 → TaskDefinition／空间／reset 声明 → 同一构建结果进入 Env／Runtime。source 解析和 Controller 计算可有合法的双向需求解析，但执行绑定必须指向最终实际 source，不能以两边比较同一份声明替代 native 映射核验。

| ID／类别 | 当前定位与事实 | 依序实施／核查动作 | 本格完成证据 |
| --- | --- | --- | --- |
| R01 核 | `registry.make_env`、`SelectedReferenceEnv.from_resolved_config`、四 Task 的 `selected_binding` 已有共同入口；旧 flags／codec 仍服务其他 caller | 冻结四任务实际 UID、配置字段与默认值表，保留当前规范。核对入口解析一次、预解析值身份重验、mapping／YAML 等价及正式类拒绝旧 component 构造。只处理实际进入四任务的分流 | 四 caller 的实际方法链和现有配置诊断对应；没有把范围外 component 全删作为门 |
| R02 改 | `TaskBuildRequest` 统一回调签名，但 `ReferenceTaskBinding.build` 仍接受由 Task 自行编排的大构造过程；`_StandardResetReconstruction._compose` 另有后置组合 | 在 `ReferenceTaskBinding/SourceBoundTaskBuilder` 及现有 runtime source／Controller owner 中落实共同构建阶段和明确输入／输出。Task 交声明、Task hook 和参数；公共构建 owner 调用 source、主体、Controller 的能力实现。接通四正式 caller，移除被取代的任务级编排，不只加另一层封装 | 一张阶段 owner 表；四条真实构造链实际执行同一阶段合同；`artifact/source/controller/physical_execution/reset_plan` 等现有结果字段有明确供给者，不能交未被调用的新 schema |
| R03 改 | PickCube `specialization._compile_mjcf_effort_source/build_reference` 仍准备 source、选择 Position／effort 工厂并包装 Controller 身份；`make_reference_binding.build` 再选路线 | 保留 Task 的 cube／table 声明、reset／Solution 参数；将 MJCF source／主体构造编排归 source owner，Controller 构造／执行 cadence 和身份包装归 Controller owner，通过 R02 调用。原命名映射作为显式 Task／Robot 数据传入，不让 adapter 反推 PickCube | PickCube Position、直接 effort、可切换 effort 进入共同阶段；Task 不再直接完成这三套 source＋Controller 构造；被替代代码同批删除 |
| R04 改 | PickCube `build_isaac_reference/build_pickcube_isaac_runtime_input_v1` 仍在 Task 内装配 USD runtime input、Position subjects 或 effort Controller；有效 USD byte reuse 已存在 | Task 保留场景物体、语义及必要命名声明；将 USD delivery 消费、runtime input 和原生 source 映射归现有 USD／Isaac source adapter，Position／effort Controller 建造归各 Controller capability，接 R02。保留 F06 精确准入与 source freshness，不要求 MJCF／USD 合并表示 | Task 不再亲自组织 USD native 构造；Isaac Position／effort 同一构建合同；必要 source／kinematics/readiness 输入仍可追踪。资产预装要求明确，不新增自动下载门 |
| R05 改 | Nut `specialization._build_reference/build_runtime_source/_binding` 仍组织 source、Controller execution wrapper 和带 Solution 信息的 Controller identity | 将本体 source／Controller 执行准备接入 R02 的相同阶段。Nut 保留抓取／接触／reset、Solution 和严格反馈语义；接触参数可以由 Task 声明，由 adapter 应用。无需在本单元重写全部 Nut guard／stream 类型 | Nut 不再是一条另有 source＋Controller 编排的构造主线；当前 guarded ExpertAction 仍有效；两任务共用机制，任务策略分别保留 |
| R06 改 | 简单主体的 `task_binding` 已很薄；`ExistingSubjectEffortTask.bind` 仍有 source→主体→physical execution 的内部构造流程 | 让这条流程消费 R02 相同阶段；该类可以保留为声明适配，不能持有另一套运行／reset 生命周期。保留各自 MJCF、USD 及传动 lowering，不为“统一”套 Panda source 方案 | Pendulum／双轮车和 Panda 在构建阶段使用相同请求、主体／Controller 编译合同及结果交接；差异限声明和有职责的 adapter／capability |
| R07 核 | `compile_position_subjects`、`build_declared_effort_execution`、`bind_selected_controller` 已有真实主体匹配；`_compose` 可能在 Task Controller 创建后才组合 source | 对一体／装配 Panda、简单主体列出 Controller 通道 → Scene writer 资源 → native Joint/DOF/actuator/transmission 三层映射。确认组合／替换 source 后 Controller 与最终 source 同源；若存在先算后绑，说明其合法依赖并最终重验 | 原始声明、编译结果和实际 source 映射能对应；不靠相同字符串或事后 RobotRuntime 证明完成；保留耦合手指和双 writer 约束 |
| R08 核 | 四 Task 已有 `task_definition_factory/task_state_projection`，RobotRuntime 只是视图 | 对共同构造和 reset 证明 TaskDefinition、空间、任务状态、Robot declaration 和 live Controller 来自 R02～R07 的实际结果。TaskDefinition 可有不同子类和语义 hook，不要求同一个类或完全相同参数 | 四任务构造对照及装配 Panda 子例；简单主体无虚假 gripper／ee；实际对象和状态来源匹配，非仅视图一致 |

**单元退出：**R01～R08 均有确定结果；四正式构造实际消费共同阶段；对应的旧编排已处理；至少完成本单元受影响的正式构造／代表短程与必要错误检查。原生执行在有效授权与资源内进行；最终 U5 可以复用本单元完整覆盖的结果，不能重复增加 smoke。交付本单元净变化及 Task 内还留哪些构造知识、为何合法。

### 2.1 六项实现调整的接收方

以下限定落点及输入／输出，避免实施者再从目录名猜架构；可以在这些既有 owner 内调整私有签名，但须同批迁 caller。不能把下面的描述当成已经存在的新公开 API。

| 检查点 | 主要接收方／现有符号 | 要迁入的决定与要留下的内容 |
| --- | --- | --- |
| R02 | `environment/reference_binding.py:SourceBoundTaskBuilder.__call__/ReferenceTaskBinding.build_for_request/bind_compiled_control`；`reference_env.from_task_binding` 只接结果 | 共同 owner 执行声明→source/subject→Controller→binding 的阶段，接已有 source／Controller 工厂；source cache 的寿命属于本次 Env/binding。Task 可以提供声明 hook，不能把旧整段构造函数作为唯一 hook 原样塞入。`_StandardResetReconstruction` 保留 episode 重建／lease 交接，不再另复制一次构造策略 |
| R03 | `runtime/sessions/source.py:bind_reference_scene_source`、`source_composition_adapters.prepare_panda_source_effort_factory`、`mujoco_composition`；`controllers/canonical/execution.build_reference_position_controller`、`r3_effort.PandaEffortProfileFactory` | source 负责最终受控实体／传动／资源绑定，Controller 负责执行 wrapper、参考算法和参数。PickCube 的 `compile_pickcube_mjcf_task` 可保留 Task Scene/Artifact 声明，但不再由 `_compile_mjcf_effort_source/build_reference` 复制编排。Task 的 cube／table／TCP 语义选择作为显式输入 |
| R04 | `assembly/usd_delivery`、`runtime/sessions/source.py:UsdRuntimeInputV1`、`isaac_g05` 的既有 source 构建、`position_subject_binding.compile_position_subjects`、`isaac_physical`；Controller owner 同 R03 | 将 Task 中 USD runtime input 的通用构造和 readback/admission 交这些 owner。`build_pickcube_isaac_scene` 等可以继续产生 Task 声明；不将一个仍硬编码 PickCube 布局的大函数改名后整包搬到 Core |
| R05 | `assembly/compiler.py:compile_reference_source` 及 source owner；`controllers/canonical/execution.build_reference_position_controller` 和 `execution` 的已有执行类型 | Nut 的 Task objects/reset/Solution/guard 参数留下，source、cadence/Controller 构造与执行身份归对应 owner。Controller 不 import Nut Solution；任务与策略 provenance 由现有构造／记录合同携带，不以删身份消除耦合 |
| R06 | `reference_binding.ExistingSubjectEffortTask.bind` 接 R02；`declared_effort_source.compile_declared_effort_source`、`physical_control.build_existing_subject_effort/build_declared_effort_execution` | 简单主体声明继续留任务和 Robot；source/physical 编译归现有实现。相同的请求、阶段和结果可有不同 typed lowerer；不要求简单主体转用 Panda 函数 |
| R16 | `planners/contracts.py:validate_caller_solution_action`、`control_lifecycle.prepare_selected_control_action/project_position_action`，Env 的 `_step` 与必要的一处兼容提案准备 | 纯提案身份校验、动作投影和生命周期失败分别回既有 owner；两个兼容入口委托相同实现，调用方标准路径不新增 act/observe。若需一个私有提案准备函数，说明其三个入口的复用和实际删除的重复段，不扩成新调度器 |

U1 首个可操作顺序为 R01 确认已有输入 → R02 定阶段及字段交接 → R03 先接 MJCF PickCube → R05 接 Nut → R06 接简单主体 → R04 接 USD/Panda → R07/R08 验证最终 source／主体／TaskDefinition。R02 的阶段改动与至少一个真实 caller 同批落地；不单独交空框架。U3 内再完成 R16，不把它混入 U1 任意小修。

## 3. U2：结束生命周期与资源所有权的对账

**对应：E03。依赖：U1 接收的构造交接。** 已有 `EpisodeExecutionState` 和 `_StandardResetReconstruction` 不重写；按下面的实际风险补缺口，避免再造一套 reset manager。

| ID／类别 | 当前定位 | 依序实施／核查动作 | 本格完成证据 |
| --- | --- | --- | --- |
| R09 核 | `from_task_binding/__init__/_release_failed_task_construction` 与 `close_source_and_task_resources` | 按构造阶段列出已取得资源及失败清理接收方，覆盖 Task source 准备后、主体／Controller 绑定后、Env 尚未返回的异常。U1 移动实现时同时迁移清理责任 | 一张资源表：取得、借用／自有、交接、释放、失败状态；原异常保留，cleanup 次错误附注；无重复 owner |
| R10 核 | `SourceBoundTaskBuilder._cached`、`_StandardResetReconstruction.reconstruct`、snapshot receipt | 核对 source 复用／重建、路由变化、freshness、构造失败、替换失败、Env close 后失效。保持新 source 验证成功前保全旧 lease 的既有语义 | 缓存属于当前 Env／binding 的有效 lifetime；旧／新 receipt 不误关；已关闭或 stale source 不复用。现有检查充分则原样保全 |
| R11 核 | `_prepare_reference_reset`、`prepare_selected_reset`、Controller reset capability、`reset_switch` | 整理预检→准备替换→破坏旧 episode→物化→reset→publication→Controller commit 的阶段表；把纯拒绝与有副作用后失败分开。核对 seed=None 连续、显式 seed、旧 generation 和固定 renderer 不兼容拒绝 | 无副作用拒绝保留原 episode／RNG／Controller；替换后失败按原合同 fault；成功 reset 后旧动作／帧失效。无需重跑全部 3c 边矩阵 |
| R12 核 | `build_selected_runtime`、initializers、`_bind_selected_task_definition`、状态／RGB publication | 检查 materialization、source-bound reset、初态 readback、Controller reset、TaskDefinition 初始化、首帧及 observation 发布顺序；允许 Position／effort typed initializer 差异 | 初态同 episode／boundary／clock；空间固定且实际输出匹配；失效 publication 不外泄。完整 observation 架构重构留 E07 |
| R13 核 | `worker._materialize_selected`、`transport.serve_session`、Env close | 保全已有 worker 清理修复，核对构造失败／session 物化后失败／close 响应／重复 close 对 source、session、Runtime owner、Task 资源的交接 | 原异常及 cleanup error 可跨 worker 识别；释放状态真实。当前不支持的 physical isolated worker 明确拒绝，不新增实现为本门 |
| R14 核 | `prepare_isaac_source`、App lease、camera consumer、`_close_reference_resources` | 对 U1/U2 触及的 App／borrowed renderer／独立 visual/source 资源画出所有权；必要时核对 Isaac 菜单 AttributeError 与本次 owner 的关系。属于契约缺陷则修复；仅外部 SDK 日志且生命周期合同成立时保留证据和限制，需接受例外交维护者 | 半构造失败和正常／重复 close 的结果、借用资源不误释放、App close 收据与日志分别报告。不给 SDK 全局“无任何错误日志”新增门，也不只凭 receipt 宣称完全无异常 |

**单元退出：**R09～R14 的资源／阶段表与真实 owner 对齐；现有强诊断优先复用，少量正负例覆盖改变的失败边界。只有确有共同 owner 缺口才改生产；不因 `reference_env.py` 仍大就继续拆 helper。

## 4. U3：结束动作来源、提案和唯一提交的收口

**对应：E04。依赖：U1 的 Controller 绑定和 U2 的 episode 生命周期。** 当前共同 submit 已存在。本单元整理真实入口及失败语义，不重新设计调度框架。

| ID／类别 | 当前定位 | 依序实施／核查动作 | 本格完成证据 |
| --- | --- | --- | --- |
| R15 核 | `step/_prepare_selected_step/step_with_solution/step_expert`，typed sequence exports | 固定“输入→声明能力→转换→lifecycle→提交→推进→反馈／observe”表。区分 Position 数组／typed request、简单主体 torque、Panda effort、caller-owned ExpertAction、compat Solution、已支持 Position／effort sequence／mixed／COM | 每种现行支持输入有正式 caller 或明确能力边界；不支持格明确拒绝。Nut 裸数组不因“统一”被开放；不新增任意组合 |
| R16 改 | `step_with_solution` 和 `step_expert` 重复 `act`、提案检查、Position／reset-selected 转换和 fault 包装；普通 ExpertAction 另有投影 | 复用现有 `planners.contracts`、`control_lifecycle` 和 Controller action projector，把重复提案准入／转换及副作用失败处理收敛到实际 owner。标准调用仍为外部 `act → env.step → observe`；有真实 caller 的兼容入口只薄委托，不再维持各自一套调度 | 标准路径不由 Env 多调一次 act／observe；兼容路径只做其声明的动作；重复实现实际减少；LIBERO 当前 `step_with_solution` caller 可用，未擅改 benchmark 语义 |
| R17 核 | stale action、Controller compute、Env 内 act／转换、Task load 与 partial write | 核对四种失败：无副作用输入拒绝、Env 已调用有状态 Solution.act 后提案失败、Controller／Task 计算后失败、部分 native 写入／推进后失败。保留最初异常及附注 | 至少对应已有行为检查或少量补充：可纠正输入不误 fault；副作用后锁存故障并要求 reset；不通过删 guard 放行 |
| R18 核 | `prepare_selected_control_action`、`_preflight_control_command/submit_control_command`、`EpisodeExecutionState.execute_interval` | 跟踪 dispatch 的生成与消费、typed batch／resource writer、admission、一次提交及唯一 advance。核对 preflight 后到提交的数据／generation 不能换掉，不能只新增 receipt 字段 | 实际命令、session、source、episode、boundary 与推进计数可关联；单／双 writer 和受影响冲突／部分失败覆盖即可，不遍历历史排列 |
| R19 核 | `PositionActionSequenceV1/PhysicalActionSequenceV1/PositionPhysicalActionV1` 与当前正式 probe | 区分已经在正式入口支持的序列与仅剩导出／旧诊断的交集。现行支持的保护片段覆盖、持有／替换和 replay guard；退休 fixture 不作为兼容目标；不能把该核查改为给四任务普遍新增序列／mixed 能力 | 一份短支持表及实际 caller／检查。无有效实现或明确限制时如实列出，需改变承诺范围的交维护者，不用旧 candidate 复活填 PASS |
| R20 核 | typed effort／Position／wrench、gravity/model capability、interval／tick／substep | 保全物理类型、SI／传动、组合限幅、唯一补偿贡献和默认关闭；核对每外部 action 接收一次、Controller tick 与 native 子步的声明调度 | 重力及模型已支持范围、不支持拒绝、子步保持／替换均不退化；不用跨 solver 轨迹相同或通用闭环作门 |
| R21 核 | readback→Task evaluation→obs→Solution.observe→Recorder append | 核对同一真实 interval 的 publication 和反馈，Task 评价只由既有 TaskDefinition/lifecycle 负责；兼容与 caller-owned observe 次数清楚 | 任务成功、raw predicate、Solution completion、runtime validity 分列；state/clock 同一边界；不为 E04 重写 Recorder／replay 格式 |

**单元退出：**R15 支持表中的每条现行路径都有去向，R16 的重复处理已实际收敛，R17～R21 有与风险匹配的证据。现有 Unit4/G04 物理语义保留；一项通过不升级全表。

## 5. U4：只收口本范围的 caller 与版本诊断

**对应：E01～E04 的受影响兼容、测试和记录。依赖：U1～U3。** 不是提前执行完整 E11/E12。

| ID／类别 | 具体步骤 | 本格完成证据 |
| --- | --- | --- |
| R22 核 | 对当前 `diagnostics/tasks/v2.1.1` 按真实动作分类：纯配置／fake 合同、真实 source 检查、native CPU、Isaac/GPU、图像。`test_formal_tasks_construct_from_common_request` 会调用真正 `make_env`，不能因模块写 provider-free 就自动当作完全纯检查 | 每大单元有精确 node/命令及成本；纯检查有 import／asset 守卫；不新造测试平台、不默认跑整个 281 集合 |
| R23 核 | 将本次依赖旧 method patch／私有布局的核心检查迁到四正式任务或实际公共 owner；保留能独立发现单位、身份、冲突、clock、故障错误的行为检查 | 不为 fixture 把退休分支补回生产；不以删除 detector 获得全绿；新的测试针对一项实际风险，不逐 helper 镜像 |
| R24 核 | 更新被 U1～U3 改动直接影响的 examples、CLI、worker、记录入口与 LIBERO Core caller。范围外 component／batch／learner 只做受影响 import／pure build／space 核查 | 本次四任务不再从旧 candidate 构造；必要薄兼容有真实 caller；不扩展为完整训练／batch／LIBERO A123 回归 |
| R25 核 | 每单元结束覆盖更新本账本第 10 节当前效果；执行过程放原始 ignored 证据，最终记录按模块压缩。保全现有执行记录 dirty，不自动吞入提交或清掉历史证据 | 一个当前摘要表、每单元一个结论入口；没有每批追加同类进度的长叙事，也没有只有“281 passed”的结果 |

## 6. U5：用最短实际证据结束 E00～E04

**依赖：U1～U4。** 复用同一最终 owner 已覆盖的结果，不在结尾机械重跑。以下是已有要求的映射，不新增全矩阵、像素门或完整 Solution。

| ID／类别 | 具体步骤 | 本格完成证据 |
| --- | --- | --- |
| R26 核 | 对四正式任务和装配 Panda 子例完成/关联正式构造→reset→非零合法 interval→state/clock→第二次 reset→close；Position、effort、Nut guarded action 与 caller-owned Solution 取实际支持的代表路径 | 优先复用现有 `formal_cpu_probe.py`：`panda-r3/assembled-live/nut/pendulum/two-wheel`，effort 另选已改变的 `panda-effort/panda-joint`；同路径已有最终证据就不重复。Nut 单 interval 不写完整 Solution 成功 |
| R27 核 | 对 source／Controller／worker／App 变更做 provider 影响表。相同实现的简单主体可以由一条 native 代表配另一条 source／caller 检查；不同实现受影响时分别补；未改变交集用旧身份和 diff 关联 | 准确列 MuJoCo CPU、GeoPhys CPU、Isaac CUDA 的受影响路线和复用理由；没有默认四任务×三家全跑，亦没有修改共同 owner 后全部盲继承 |
| R28 核 | 判断本次是否改变 renderer 消费的 source、publication、reset 或 App lease：若有，补一条最相关的原生 borrowed 或 independent cross 同步图像／关闭检查；两类都被不同代码改动影响时分别处理；若无，用实际 diff 说明复用 | renderer 仍消费同一 Runtime boundary/clock，render 不推进物理。只验证受影响合同，完整 registry／光学／颜色整理仍归 E07/E08；不重开 5c 图像接收 |
| R29 核 | 按事件给出最终 owner／调用链、输入输出 HEAD、文件新增删除迁移、生产＋诊断＋文档 diff、复用／新证据与限制；区分阶段内移动和项目净减少 | 统计与结果可复算；净减 9098 行只作为本次输入基线，后续新增有职责说明；不规定任意删行／文件下降比例，不用全文件搬迁冒充 owner 收敛 |
| R30 核 | 对本账本 30 格及第 9 节总账映射一次收口，分别判断 E00、E01、E02、E03、E04；将 E05 以后未完成内容明确保留 | 实施者结论、独立主审、维护者接收分列；无未解释的 in-scope OPEN 才提请该事件接收。完成 E00～E04 不等于全部代码／项目优化接收，也不自动进入 E05 或 G06 |

### 6.1 验证复用和命令选择

| 大单元 | 可优先复用的现有检查／取证入口 | 结论边界 |
| --- | --- | --- |
| U1 | `test_formal_configuration.py` 的 resolve-once、mapping/YAML、Robot/default/profile、正式类拒绝 component；`test_declared_effort_source.py`、`test_tabletop_robot_source.py` 的真实声明／source 行为；`formal_cpu_probe.py` | 区分配置、source 编译和 native。测试名和目录不决定纯度 |
| U2 | `test_reset_reconstruction.py` 的四个现有 source／selection 检查；`test_worker_resources.py`；`test_episode_import.py`；已有 worker probe 与 U1 的正常路径 | fault 注入证明对应阶段，fake close 不升级为真实 SDK 全部关闭 |
| U3 | `test_control_lifecycle.py`、`test_panda_effort_profiles.py` 的 stale/proposal/selection 检查、`test_position_outputs.py`；正式 probe 的 `--solution`、`--record --solution-after-switch` 或 `--sequence` 按实际支持选择 | 单步 Solution、序列、记录分别报告；不由同一个 PASS 外推其他输入 |
| U4／U5 | 仅所改 doc／CLI caller 的静态或纯构建检查，最终影响表和 native 原始结果 | 代码 HEAD 不同不自动废弃旧证据；同一任务成功需要的材料不从不同 run 拼接 |

已保存的 `v211_common_task_build_request_20261112`、`v211_robot_position_layout_final_20261112`、`v211_preparse_robot_intent_20261112` 和 `v211_simple_robot_source_intent_20261112` 等 plan/log 可从[执行记录](post-5c-optimization-execution.md)定位。本次核对其计划与输入存在，没有把各旧 HEAD 的结果改称 b94 最终代码实测。

每个实际执行单元开始时冻结真实 HEAD／dirty、probe 字节、case、seed、horizon／dt、显式子步、内存／墙时／输出和现行锁。参考 probe 自身已有双锁／计数能力，但旧 plan 的资源窗口不直接沿用。有效授权内的普通修复可连续进行，不按一次失败切包。启动隐式推进 unknown 保持 unknown，不伪造零。

## 7. 架构分歧的明确处理规则

1. **统一合同和阶段，不统一所有 native 算法。** MJCF／USD、Position／effort／wrench、单层／嵌套的能力分派合法，归对应 owner；不能再按 Task UID、候选历史或测试名字决定公共生命周期。
2. **TaskDefinition 可以不同。** 各任务奖励、reset 分布、谓词、Solution 和显式状态投影保留 Task owner；共同生命周期调用这些声明，而非把策略抽进公共 Runtime。
3. **公共旧 component 代码不是本轮的删除目标。** 它不进入四正式任务就以 caller 及边界结案；只有隐藏回流、复制实际 owner 或受本次改动破坏时才处理。
4. **现有 builder 是扩展落点。** `ReferenceTaskBinding`、`SourceBoundTaskBuilder`、RuntimeBuilder 和 Controller capability 允许调整；禁止另建平行 factory／Runtime，或原样迁一个千行 Task specialization 再包共同类。
5. **真实性高于文本指标。** 减少一层 Task-owned native 编排比改几个名称有意义；为合理 adapter 增文件可接受，必要身份／单位／资源检查不得作为冗余删除。

## 8. 明确留给后续事件的事项

| 后续范围 | 本轮边界 |
| --- | --- |
| E05／E06 完整 source／provider 体系整理 | U1 只迁移实现四任务共同构建所必需的编排和接线；任意资产 recipe、全部准入历史、通用 source 注册体系不成为 E00～E04 新门 |
| E07／E08 观测／renderer 完整整理 | 保住受影响 publication、首帧、固定 renderer、App／camera ownership；不提前实现完整 registry、颜色校准或动态 renderer 切换 |
| E09～E12 全面 Task／Recorder／诊断／caller 整理 | 本轮只收敛四任务构建与控制的直接依赖；完整 Nut 通用 guard 抽取、H5 oracle 分层、历史 replay、全部教程／benchmark 清理继续留后续 |
| E13 完整 Solution | 本轮是构造／短程／单 interval／失败语义；不要求 MuJoCo 全任务成功或重复完整多 provider Solution 作为 E00～E04 新停门 |
| E14～E16 文档总体接收、证据／refs／worktree 清理 | 本轮仅同步直接变化的 owner／API／执行记录；不删证据、不整理旧分支／worktree，不自动 merge／push／tag／发布 |

新发现问题只在此表追加“问题／owner／为何不阻塞当前单元”，保持短摘要；影响当前正确性的真实依赖必须回到对应 R 格处理，而不是借后续事件延期。

## 9. 大单元结束后的总账核对范围

| 大单元 | 只核对这些相关总账项 | 不据此宣布的结果 |
| --- | --- | --- |
| U1 | ENTRY-01／02、TASK-01～04 的构造部分、SUBJ-01～03、CTRL-01／03、SRC-01／02 的必要接口 | 不表示 Task／source／adapter 全台账完成 |
| U2 | ENV-01／02／05、RUN-04 的受影响 worker、REN-04 的 App／资源接口 | 不表示全部 renderer、SDK 或 batch 已支持 |
| U3 | ENV-03、CTRL-02／04／05、RUN-03 的命令／clock 接口 | 不表示任意输入／序列／provider 全组合成立 |
| U4 | TEST-01～03、CALL-01～04、DOC 的本次直接变化部分 | 不表示整个诊断库、文档库和 benchmark 已治理完成 |
| U5 | GOV-01／02、TEST-04、V01～V07 和 V09／V10 的本次实际覆盖；E00～E04 原事件出口 | V08 完整 Solution 留 E13，项目清理及 G06 未启动 |

## 10. 后续实施时覆盖更新的当前效果表

| 单元 | 当前结果 | 最终 owner／提交／证据 | 剩余格 |
| --- | --- | --- | --- |
| U1 | IN_PROGRESS：四任务部分路径已接入 source／Controller 构建阶段；Robot source 组合移至构建请求，R3 身份和 USD 主体绑定归各自 owner | 当前冻结输入及 [CPU／Isaac 计划](../../../../../workspace/maintenance/v211_u1_common_build_20261112_001/plan.json)，版本诊断 282 项通过；受影响路线按原始结果分别判断 | R01～R08 尚未逐格收口；Task 内剩余编排和 USD 整体构建仍需继续迁移，不能以阶段回调视为统一完成 |
| U2 | 既有机制保全，待单元收口 | 现有 reset／worker 诊断及执行记录，尚未作最终继承判断 | R09～R14 |
| U3 | 共同提交保全，重复入口和支持表待收口 | 当前 control lifecycle／submission 与既有短程证据 | R15～R21 |
| U4 | 尚未执行本轮 caller／诊断收口 | 本次只静态定位相关检查 | R22～R25 |
| U5 | 尚未执行最终事件接收 | 没有新 native 或完整 Solution 结果 | R26～R30 |

本批冻结输入的 MuJoCo 七条受影响短程均完成第二次 reset 与重复 close；Isaac Position／effort 各完成 5 个显式子步及 Env／App close 收据，重跑日志未见 traceback。首次 Isaac Position 运行的结果路径误指目录，5 个显式子步后最终收据写入失败；原始日志、修正重跑及预算见 [Isaac 计划](../../../../../workspace/maintenance/v211_u1_common_build_20261112_001/gpu-plan.json)，隐式启动推进数未知。Nut CPU 使用受限 Solution 单步。

每格完成只写最终行为、真实 owner／提交／证据和残余限制；过程及失败日志保存在各单元原始输出，不在此逐次追加。目标是让下一次恢复直接读本表及当前单元，而非重走全仓发现流程。
