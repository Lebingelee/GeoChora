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
| R01 PASS | `registry.make_env`、`SelectedReferenceEnv.from_resolved_config`、四 Task 的 `selected_binding` 已有共同入口；旧 flags／codec 仍服务其他 caller | 冻结四任务实际 UID、配置字段与默认值表，保留当前规范。核对入口解析一次、预解析值身份重验、mapping／YAML 等价及正式类拒绝旧 component 构造。只处理实际进入四任务的分流 | 四 caller 的实际方法链和现有配置诊断对应；没有把范围外 component 全删作为门 |
| R02 PASS（实施者自评） | `TaskBuildRequest` 统一回调签名，但 `ReferenceTaskBinding.build` 仍接受由 Task 自行编排的大构造过程；`_StandardResetReconstruction._compose` 另有后置组合 | 在 `ReferenceTaskBinding/SourceBoundTaskBuilder` 及现有 runtime source／Controller owner 中落实共同构建阶段和明确输入／输出。Task 交声明、Task hook 和参数；公共构建 owner 调用 source、主体、Controller 的能力实现。接通四正式 caller，移除被取代的任务级编排，不只加另一层封装 | 一张阶段 owner 表；四条真实构造链实际执行同一阶段合同；`artifact/source/controller/physical_execution/reset_plan` 等现有结果字段有明确供给者，不能交未被调用的新 schema |
| R03 PASS（实施者自评） | PickCube `specialization._compile_mjcf_effort_source/build_reference` 仍准备 source、选择 Position／effort 工厂并包装 Controller 身份；`make_reference_binding.build` 再选路线 | 保留 Task 的 cube／table 声明、reset／Solution 参数；将 MJCF source／主体构造编排归 source owner，Controller 构造／执行 cadence 和身份包装归 Controller owner，通过 R02 调用。原命名映射作为显式 Task／Robot 数据传入，不让 adapter 反推 PickCube | PickCube Position、直接 effort、可切换 effort 进入共同阶段；Task 不再直接完成这三套 source＋Controller 构造；被替代代码同批删除 |
| R04 PASS（实施者自评） | PickCube `build_isaac_reference/build_pickcube_isaac_runtime_input_v1` 仍在 Task 内装配 USD runtime input、Position subjects 或 effort Controller；有效 USD byte reuse 已存在 | Task 保留场景物体、语义及必要命名声明；将 USD delivery 消费、runtime input 和原生 source 映射归现有 USD／Isaac source adapter，Position／effort Controller 建造归各 Controller capability，接 R02。保留 F06 精确准入与 source freshness，不要求 MJCF／USD 合并表示 | Task 不再亲自组织 USD native 构造；Isaac Position／effort 同一构建合同；必要 source／kinematics/readiness 输入仍可追踪。资产预装要求明确，不新增自动下载门 |
| R05 PASS（实施者自评） | Nut `specialization._build_reference/build_runtime_source/_binding` 仍组织 source、Controller execution wrapper 和带 Solution 信息的 Controller identity | 将本体 source／Controller 执行准备接入 R02 的相同阶段。Nut 保留抓取／接触／reset、Solution 和严格反馈语义；接触参数可以由 Task 声明，由 adapter 应用。无需在本单元重写全部 Nut guard／stream 类型 | Nut 不再是一条另有 source＋Controller 编排的构造主线；当前 guarded ExpertAction 仍有效；两任务共用机制，任务策略分别保留 |
| R06 PASS | 简单主体的 `task_binding` 已很薄；`ExistingSubjectEffortTask.bind` 仍有 source→主体→physical execution 的内部构造流程 | 让这条流程消费 R02 相同阶段；该类可以保留为声明适配，不能持有另一套运行／reset 生命周期。保留各自 MJCF、USD 及传动 lowering，不为“统一”套 Panda source 方案 | Pendulum／双轮车和 Panda 在构建阶段使用相同请求、主体／Controller 编译合同及结果交接；差异限声明和有职责的 adapter／capability |
| R07 PASS（实施者自评） | `compile_position_subjects`、`build_declared_effort_execution`、`bind_selected_controller` 已有真实主体匹配；`_compose` 可能在 Task Controller 创建后才组合 source | 对一体／装配 Panda、简单主体列出 Controller 通道 → Scene writer 资源 → native Joint/DOF/actuator/transmission 三层映射。确认组合／替换 source 后 Controller 与最终 source 同源；若存在先算后绑，说明其合法依赖并最终重验 | 原始声明、编译结果和实际 source 映射能对应；不靠相同字符串或事后 RobotRuntime 证明完成；保留耦合手指和双 writer 约束 |
| R08 PASS（实施者自评） | 四 Task 已有 `task_definition_factory/task_state_projection`，RobotRuntime 只是视图 | 对共同构造和 reset 证明 TaskDefinition、空间、任务状态、Robot declaration 和 live Controller 来自 R02～R07 的实际结果。TaskDefinition 可有不同子类和语义 hook，不要求同一个类或完全相同参数 | 四任务构造对照及装配 Panda 子例；简单主体无虚假 gripper／ee；实际对象和状态来源匹配，非仅视图一致 |

**单元退出：**R01～R08 均有确定结果；四正式构造实际消费共同阶段；对应的旧编排已处理；至少完成本单元受影响的正式构造／代表短程与必要错误检查。原生执行在有效授权与资源内进行；最终 U5 可以复用本单元完整覆盖的结果，不能重复增加 smoke。交付本单元净变化及 Task 内还留哪些构造知识、为何合法。

### R01：四任务规范配置核对

四任务由 `make_env → resolve_task_env_config → from_resolved_config → TaskBuildRequest` 构建，规范输入使用 `execution`、`episode`、`task`、`controller`、`robot`。空输入在当前配置下的解析结果如下；调用方可在受支持范围内显式覆盖。

| 正式 UID | 默认 Robot | 默认 Controller | 默认 provider／backend | horizon |
| --- | --- | --- | --- | --- |
| `pick-cube-p16-reference-v1` | `panda-v1` | `r3_continuous_v1` | GeoPhys／CPU | 6000 |
| `nut-assembly-outcome-reference-v1` | `panda-v1` | `r3_continuous_v1` | GeoPhys／CPU | 6000 |
| `pendulum-v1` | `pendulum-v1` | `direct_joint_effort_v1` | GeoPhys／CPU | 200 |
| `two-wheel-balance-v1` | `two-wheel-balance-v1` | `direct_joint_effort_v1` | GeoPhys／CPU | 400 |

`test_formal_configuration.py` 覆盖四任务 resolve-once、等价 mapping／YAML、预解析身份重验和 component 输入拒绝；本批版本诊断 283 项通过。范围外 component caller 仍存在，不以全仓移除为本格条件。

### R02／R06：构建阶段与简单主体

| 阶段 | 当前实际 owner | 差异及边界 |
| --- | --- | --- |
| 输入和选定 Robot | `make_env`、配置 resolver、`TaskBuildRequest`、Robot 声明 | 四任务共用请求；任务提供默认值和语义 |
| source／主体 | `SourceBoundTaskBuilder` 调用各声明和 source adapter；简单主体由 `compile_declared_effort_source` 编译 | MJCF／USD 分别 lower；共同 `scalar_joint_source_bindings` 核对 Scene／Artifact，Robot 声明再次限定状态关节 |
| Controller／绑定 | `compile_declared_effort_source` 与 `build_existing_subject_effort` 交接已验证主体，再经 `bind_selected_controller` | Pendulum 和双轮共用 effort 路线；Panda 的 Position／effort 使用其能力工厂，不伪造相同 native 算法 |
| 语义和 reset | TaskDefinition factory／Task reset hook 由共同 Env 生命周期调用 | Task 保留奖励、状态投影和 reset 分布；缓存只由当前 binding 持有，复用前核验 source |

R06 为实施者自评 PASS：两个简单任务已消费共同请求、分阶段 builder、主体／Controller 编译与结果交接，没有独立 reset／step／close 生命周期；各自传动和 USD／MJCF 映射由相应 adapter 保留。真实路线证据见本节末尾计划。R02 的四任务构建与结果交接见下表；判定依据包括实际调用、受影响 source 负例和相应 native 结果，不以阶段回调名称单独结案。

#### `a5483e63` 构建结果实际交接核对

| 路线 | 共同阶段实际调用 | 结果与仍留 Task 的职责 |
| --- | --- | --- |
| PickCube MJCF Position | `SourceBoundTaskBuilder` 调用 `compose_declared_reference_source` 后调用 `build_reference_position_controller`；`ReferenceTaskBinding.build_for_request` 完成声明的 Robot source 组合 | Artifact／source 来自声明与 source adapter，Controller 来自能力工厂；Task 提供桌面、方块、readiness 和身份参数。装配 Panda 的组合仍需 Controller writer，故在 Controller 创建后完成，并由 `bind_selected_controller` 验证最终结果 |
| PickCube MJCF effort | 同一 builder 调用 source 组合和 `compile_panda_effort_selection`；该能力调用 `prepare_panda_source_effort_factory`，核对 intent、source 和 writer | `physical_execution` 与 Controller 来自相同编译结果，reset plan 由共同 builder 按 episode seed 产生；直接 effort 与 reset 可切换的差异属于能力和 Task Solution 参数 |
| PickCube USD | 同一 builder 将已准入 USD Artifact／source 交 `build_usd_panda_control`；Runtime 的 `compile_usd_task_runtime_input` 产生 source、execution 和 reset 输入 | Position／effort 分别由已有能力编译，USD 原生 readback／admission 归 Runtime；Task 留物体与语义映射、readiness、Solution 和经声明的 F06 参数 |
| Nut | 同一 builder 将 `ReferenceTaskDeclarationV1.compile_source` 的结果交 `build_reference_position_controller`；`ReferenceExecutionController` 组合 cadence／hold 并绑定 Task 提供的 provenance | Task 留 Nut／peg 场景及接触参数、guard／Solution 与 provenance；MuJoCo option lowering 调用 provider adapter，Task 不启动 native session |
| Pendulum／双轮车 | `ExistingSubjectEffortTask.bind` 使用同一 builder；`compile_declared_effort_source` 与 `build_existing_subject_effort` 分别编译 source／主体和 Controller | 任务声明 reset、评价与投影；typed effort execution 和 source 校验归公共 owner，无 Panda 字段要求 |

上述是构建时的 owner 与受测路径，不是任意 Robot／资产组合的支持声明。`ReferenceTaskBinding.build_for_request` 的后置 source 组合只用于需要已构造 Controller writer 的路线；最终绑定及原生映射还需按下表和 R07 的限定核对。`_bind_selected_task_definition` 在初构及 reset 重建后均从当次 Artifact 创建 TaskDefinition 并绑定 TaskLifecycle；该静态调用关系和短程结果不单独扩大 observation 或完整 Solution 的结论。

U1 逐格结论为实施者自评，独立主审和维护者接收另行记录。与重评输入 `b94e8625` 比，当前 `task_env` 生产代码涉及 13 个修改文件，+903／−600 行；版本诊断涉及 6 个修改文件，+301／−22 行（含当前 probe）。这些包含迁移到共同 owner 的代码，不能把逐行移动当作净删除。该范围没有新增／删除／重命名文件；原 `1f1359ee` 至重评输入的净减与本段统计分别报告，不相加冒充本段效果。文档仅提交本账本变更，原有执行记录 dirty 与四个保护输入不纳入本段提交。

### R07／R08：主体到执行的当前对照

`a5483e63` 下的[剩余任务 MuJoCo 短程计划](../../../../../workspace/maintenance/v211_u1_remaining_tasks_native_20261112_001/plan.json)补充了 Nut、Pendulum、双轮车的正式构造、reset、非零 interval、第二次 reset 与重复 close：分别推进 5、25、25 个显式子步，双锁已释放。Nut 使用其受约束 Solution 单 interval；不作为完整 Solution 成功。该运行核对重建后 Robot／Controller 和简单主体 action space 的交接，不能单凭运行结果替代下面的 native 映射逐项核对。

[TaskDefinition 重建检查](../../../../../workspace/maintenance/v211_u1_definition_rebind_20261112_001/plan.json)在同一生产源码、扩充后的版本 probe 下，检查四任务及装配 Panda 两次 reset 后的 TaskLifecycle 对象和 observation space，五条 MuJoCo 短程通过。桌面 Task 额外核对 Artifact semantics，Nut 还核对 Artifact hash；简单主体的 TaskDefinition 不暴露这两个字段，结果没有虚报相应核验。此结果不证明任意资产或其他 provider 的 TaskDefinition 映射。

[MuJoCo native 映射检查](../../../../../workspace/maintenance/v211_u1_native_mapping_20261112_001/plan.json)读取实际 `RuntimeSession.build_layout_facts`，核验 materialization/source closure 后保留每个 semantic 对应的 native 名称、关节地址和 actuator 传动结果。一体 Panda Position／effort、装配 Panda 与 Nut 各读回 9 个关节和 8 个 actuator；Pendulum 为 1／1，双轮车为 3／2。六条均完成其受测短程并释放双锁；具体 writer、source 和逐项地址见各 `result.json`，该证据限 MuJoCo CPU，不替代 Isaac 的公开 DOF 检查。

| 主体／任务 | Controller 通道与 Scene writer | source／原生映射及 TaskDefinition |
| --- | --- | --- |
| 一体 Panda／PickCube、Nut | 七个 arm Joint 与两个 finger Joint；Scene 中七个 arm actuator 和一个耦合 gripper actuator | Robot recipe 和 position／effort compiler 给出主体；MuJoCo 的 `check_mujoco_named_layout` 核对模型 Joint、actuator 和 tendon；Isaac 的 `check_isaac_named_layout` 核对公开 DOF／state view。任务各自从实际 Artifact 创建定义 |
| 装配 Panda／PickCube 子例 | arm 与 hand 作为嵌套主体，`r1_split` 使用各自 writer | source composition 校验 arm／hand 资源及 attachment；Position 编译后的主体与 Controller 在 Runtime 绑定。仅覆盖现有受支持装配 |
| Pendulum | hinge 经 `pendulum_torque`，一个 effort writer，限幅 ±2 N·m | Robot 声明引用已有主体，source adapter 校验传动；TaskDefinition 使用该任务状态投影 |
| 双轮车 | 左右轮 Joint 分别经各自 actuator，单个 effort writer，每轴限幅 ±1.5 N·m；chassis pitch 为状态轴 | 与 Pendulum 共同消费声明式 effort 编译和绑定，保留不同 MJCF／USD lowering；TaskDefinition 使用该任务状态投影 |

`bind_selected_controller` 对最终 Artifact／source／Controller 匹配，Position source 组合后重编译或核验主体绑定；物理执行通过 `validate_source` 再核验。MuJoCo／Isaac 的实际 readback 和短程结果按各自计划判断，不能把声明相等扩大为任意模型支持。四任务的构造诊断已检查 `RobotRuntime` 引用选中的声明、主体与 Controller，并检查 TaskLifecycle 使用实际创建的 TaskDefinition；二次 reset 的覆盖仍依赖各真实运行收据，最终按当前代码身份对账。

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

### U2 资源交接与 reset 阶段核对

| 阶段 | 持有与交接 | 失败或关闭 |
| --- | --- | --- |
| Task source 构造／Controller 编译 | `SourceBoundTaskBuilder` 持有新 source receipt；复用时先验证 snapshot／USD freshness | 首次构造的 source 或 Controller 阶段失败由 builder 关闭 receipt，并在 cleanup 失败时保留原异常与附注；缓存不提交失败结果 |
| Env 尚未返回 | `from_task_binding` 和 `SelectedReferenceEnv.__init__` 将初始 value 与 binding 交接 | 失败由 `_release_failed_task_construction → close_source_and_task_resources` 清理 source 与 Task 自有资源，异常及清理附注保留 |
| reset 重建 | `_StandardResetReconstruction` 持有旧与候选 source receipt，先检查新 source、Artifact 和外部 Solution | 新 source 验证失败仅关闭新 receipt；通过后再关闭不同的旧 receipt，避免丢失原恢复路径 |
| worker | `_materialize_selected` 重建并独立核验 binding/source；`serve_session` 管理 session 与关闭响应 | worker 清理顺序为 session、Runtime owner、source、Task；多个 cleanup 失败以附注保留，重复 cleanup 不再执行 |
| episode 与 Runtime owner | 预检后旧 episode 的 publication 失效，旧 session 关闭；进程级 owner 可跨成功 reset 复用 | 若替代 session 未建成即失败，旧 owner 保持可达，Env close 时释放；失败的新 session owner 同样保留。close 失败保留首个异常与次级附注 |
| camera／visual | RGB consumer 负责其 camera session；独立 visual session 持有自己的 renderer 资源，borrowed 模型的物理资源仍归 Runtime | reset 与 Env close 调用 consumer 清理；即使 camera close 失败，仍尝试关闭 visual。关闭状态以实际 receipt／异常为准 |
| Recorder／Task | Recorder 由当前 Env episode 管理，未完成记录拒绝 reset；Task 自有资源由 binding 关闭 | 先结束可正常结束的 episode，再关闭 camera、session／Runtime owner、source／Task；fault 时不伪造正常 episode 结束 |

| 阶段 | 实际职责与失败边界 |
| --- | --- |
| 预检／采样 | Task sampler 与 reset capability 准备 seed、Controller 和 source；固定 renderer 不兼容、无效选择等在破坏前拒绝。采样后的预检拒绝恢复 RNG，`seed=None` 与显式 seed 均覆盖 |
| 破坏／重建 | `EpisodeExecutionState` 停止旧 episode；Env 清除 publication、关闭旧 camera／session；reconstruction 验证 source、重绑 Controller／TaskDefinition，再由 RuntimeBuilder 物化。此后失败 latch fault，清理异常附注到原异常 |
| 初态／发布 | initializer 执行 reset，session 读回状态，Task 生成 observation；publication 成功才完成 episode commit。RGB 延后采集时校验同一 boundary／clock，失败仍 latch fault；Controller 的 reset selection 在旧 session 关闭后提交 |

R09～R14 实施者核对完成，独立主审及维护者接收待定。版本化纯合同检查 30 项通过，覆盖 source、worker、相机和 RNG；不将 fake 当作真实 App。最终代码的 [MuJoCo 冻结计划](../../../../../workspace/maintenance/v211_u2_lifecycle_20261112_003/plan.json)覆盖四任务及 Panda effort／装配，每条完成构造、reset、一个非零 interval、第二次 reset 和重复 close；Pendulum／双轮车额外核对连续 RNG。前一轮等价实现的 002 也通过；001 因缺少 `scene` 模块在物理推进前失败，锁已释放。另一次误将含真实 source 构造的配置测试模块作为纯测运行，未按 native／source 窗口冻结或持锁，且桌面用例因缺少 `scene` 模块失败；不作为验证证据，详见[偏差记录](../../../../../workspace/maintenance/v211_u2_lifecycle_20261112_003/verification-notes.md)。

Isaac 成功 reset 与 App close 参考 U1 的冻结运行：U2 改动仅影响失败后 owner 保留和有 Task sampler 的预检拒绝，未改其 provider／renderer 实现；U2 未重跑 Isaac 失败路径。U1 的 Position 关闭日志曾含 SDK 菜单回调警告，App receipt 和日志分别保留，无法仅凭 receipt 断言 SDK 无异常。GeoPhys、真实 camera 失败与跨 renderer 不扩大为本单元已复验范围。

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

### U3 动作输入与当前处理边界

| 输入／调用 | 准入和转换 | 提交与限制 |
| --- | --- | --- |
| 普通 Position／typed request | 声明 Position capability 的 Controller 投影；typed request 先验绑定 | `prepare_selected_control_action` → Position interval → `submit_control_command`；装配 Panda 使用已声明双 writer |
| 简单主体 torque／Panda effort | 对已绑定 physical execution，Controller 生成有单位和 source／generation 身份的命令 | 同一 submit owner 后推进 Runtime；reset-scoped 选择要求当前 action identity，stale 输入预检拒绝 |
| 调用方 `ExpertAction` | Task 声明允许时校验 Solution identity 和已发布 boundary；Position 再投影 | `env.step` 进入相同 lifecycle；调用方自行 `observe`。Nut 不开放普通裸数组 |
| `step_with_solution`／`step_expert` | 受限兼容入口调用同一提案处理，按当前 Controller 能力投影；前者要求 reset 接受的同一实例 | 两者委托 `_step`；`act` 已发生后失败锁存 fault。标准调用仍是调用方持有 Solution 并 `act → env.step → observe` |
| Position／physical sequence | 现有 typed 片段必须覆盖完整 interval，不得重叠；不为四任务扩展全部组合 | Position 单 Controller 且不接 Recorder／Solution／task RGB；physical sequence 不支持 reset-scoped Controller 切换 |
| mixed／COM wrench | 仅已声明的 binding、writer、资源和 SI 单位；COM 外力受 MuJoCo CPU 与生命周期约束 | mixed 不支持 reset-scoped 切换或 Solution；writer／effect 冲突和 replay guard 保留，不宣称任意组合 |

R15～R21 实施者核对：兼容入口共用提案检查／投影及已有 `_step`，caller-owned 标准调用不额外调用 `act` 或 `observe`；native 检查中 caller-owned 在一次提交后由调用方 observe 一次。[兼容 Solution 与 caller-owned 路线](../../../../../workspace/maintenance/v211_u3_solution_20261112_001/plan.json)、[Position expert](../../../../../workspace/maintenance/v211_u3_expert_20261112_001/plan.json)、[可切换 R3 expert](../../../../../workspace/maintenance/v211_u3_expert_20261112_002/plan.json)均为单 interval，不能当作任务成功或完整 Solution。expert 首次可切换探针在完成 5 子步后误要求相同 R3 profile 的 Controller identity 改变，导致断言失败；已在第二次按实际前提修正，失败结果及锁释放记录保留。

[真实失败边界](../../../../../workspace/maintenance/v211_u3_failure_native_20261112_001/plan.json)验证 stale action 不改变 boundary、不 fault，Solution.act 后无效提案 latch fault，以及可切换 R3 expert 提交；三项合计 10 显式子步。[typed 控制短程](../../../../../workspace/maintenance/v211_u3_typed_control_20261112_001/plan.json)覆盖一条 effort sequence 和一条 Position gravity；12 项纯合同检查覆盖提案、Position sequence 准入、资源冲突及部分写入后跳过推进。具体推进由 session 完成，dispatch／submission 校验 source、boundary、generation 和实际 Controller identity；测试不推断 solver 间轨迹等价。Position sequence、mixed／COM 的其余组合及真实部分写入失败没有在本轮复验，保留现有能力限制及历史证据，不扩大结论。

## 5. U4：只收口本范围的 caller 与版本诊断

**对应：E01～E04 的受影响兼容、测试和记录。依赖：U1～U3。** 不是提前执行完整 E11/E12。

| ID／类别 | 具体步骤 | 本格完成证据 |
| --- | --- | --- |
| R22 核 | 对当前 `diagnostics/tasks/v2.1.1` 按真实动作分类：纯配置／fake 合同、真实 source 检查、native CPU、Isaac/GPU、图像。`test_formal_tasks_construct_from_common_request` 会调用真正 `make_env`，不能因模块写 provider-free 就自动当作完全纯检查 | 每大单元有精确 node/命令及成本；纯检查有 import／asset 守卫；不新造测试平台、不默认跑整个 281 集合 |
| R23 核 | 将本次依赖旧 method patch／私有布局的核心检查迁到四正式任务或实际公共 owner；保留能独立发现单位、身份、冲突、clock、故障错误的行为检查 | 不为 fixture 把退休分支补回生产；不以删除 detector 获得全绿；新的测试针对一项实际风险，不逐 helper 镜像 |
| R24 核 | 更新被 U1～U3 改动直接影响的 examples、CLI、worker、记录入口与 LIBERO Core caller。范围外 component／batch／learner 只做受影响 import／pure build／space 核查 | 本次四任务不再从旧 candidate 构造；必要薄兼容有真实 caller；不扩展为完整训练／batch／LIBERO A123 回归 |
| R25 核 | 每单元结束覆盖更新本账本第 10 节当前效果；执行过程放原始 ignored 证据，最终记录按模块压缩。保全现有执行记录 dirty，不自动吞入提交或清掉历史证据 | 一个当前摘要表、每单元一个结论入口；没有每批追加同类进度的长叙事，也没有只有“281 passed”的结果 |

### U4 受影响入口与诊断分类

| 调用／诊断 | 本次处理与成本 |
| --- | --- |
| `test_formal_configuration.py::test_config_resolution_does_not_open_assets_or_import_native_sdks` | 四任务纯配置解析；禁止常见 native SDK 导入及仓库资产打开。模块中 `test_formal_tasks_construct_from_common_request` 等会构造真实 source，不能整文件当纯测 |
| `test_solution_compatibility.py`、`test_control_lifecycle.py` | fake 合同，覆盖 Solution 提案、公开 schema 数值检查、writer 冲突和部分写入回调；不构造 source 或 native |
| `test_reset_reconstruction.py`、`test_worker_resources.py`、`test_task_rgb.py` | fake／临时 source receipt、socket 和 fake camera；不代表真实 SDK App 或图像采集 |
| `formal_cpu_probe.py`、`test_panda_effort_profiles.py` 的 native node | 真实 source／MuJoCo；需冻结 node、输入、子步、资源和双锁。Isaac 或图像另需对应 GPU／显示资源，不由 CPU 证据外推 |
| `task_env/script/env/_common.py`、四任务示例 | 正式 `make_env` 和共同配置；动作根据已绑定 Position capability 或 action space 生成，不再把 `step_expert` 方法存在与否当作主体类别。Nut Solution 接受 Gym `info` 中的公开 schema，同时仍拒绝非有限值 |
| `bench_deploy/libero/trajectory/worker.py` | 保留真实 caller 的 `reset_for_solution → step_with_solution`，U3 兼容入口仍提供一次 act／observe；静态核对，不宣称完成 LIBERO benchmark 复验 |
| vector／learner 与范围外 component | 不扩大为 G06 或训练实现；正式四任务的旧 parallel factory 拒绝由纯配置节点核对；未运行 batch physics |

[四任务示例 MuJoCo 计划](../../../../../workspace/maintenance/v211_u4_cli_20261112_003/plan.json)各运行一个 interval，总计 60 显式子步；Nut caller-owned Solution 的 `act → step → observe` 同次完成。001 使用错误的 Nut seed 31 在其推进前被拒绝；002 使用 seed 19 后发现公开 schema 被 Solution 错误拒绝；两次 PickCube 各推进 5 子步、锁已释放，记录和日志保留。003 修正后通过，不能据此宣称任务成功或完整 Solution。11 项精确纯节点通过。已有执行记录的用户 dirty 内容未纳入本单元提交。

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
| U1 | 实施者自评 PASS，独立主审及维护者接收待完成：`253e1efe` 与 `a5483e63` 将桌面 Position／effort 的 source 和 Controller 能力接入共同阶段；四任务构建结果交接见第 2 节。Task 继续提供任务参数和语义映射 | [MuJoCo 计划](../../../../../workspace/maintenance/v211_u1_shared_source_native_20261112_001/plan.json)：Position、effort、装配 Panda 各 5 个显式子步、二次 reset 和重复 close；[剩余任务计划](../../../../../workspace/maintenance/v211_u1_remaining_tasks_native_20261112_001/plan.json)：Nut、Pendulum、双轮车各完成对应短程。[Isaac 重试计划](../../../../../workspace/maintenance/v211_u1_usd_shared_native_20261112_002/plan.json)：Position、effort 各 5 个显式子步、二次 reset、App close receipt 完成，启动隐式推进 unknown；首次启动失败和早前 MuJoCo 运行偏差分别保留原始日志与[偏差记录](../../../../../workspace/maintenance/v211_u1_continuation_20261112_001/verification-notes.md) | R01～R08 均有实施者结论；U2 可沿现有结果开展生命周期核对。后续事件和全台账未完成 |
| U2 | 实施者自评完成，独立主审及维护者接收待定：修复失败 reset 的旧 Runtime owner 遗失及预检拒绝后的 RNG 变化；保全 source、worker 与 camera 清理合同 | 第 3 节资源／阶段表、30 项纯合同检查与 [MuJoCo 最终冻结计划](../../../../../workspace/maintenance/v211_u2_lifecycle_20261112_003/plan.json)；Isaac 的成功路径沿用 U1 证据并保留日志限制 | R09～R14 均有实施者结论；U3 可继续，真实 Isaac 失败与真实 camera 失败未复验 |
| U3 | 实施者自评完成，独立主审及维护者接收待定：兼容入口共用提案处理，保留调用方持有 Solution 的标准调用、现有 typed 语义和唯一提交 owner | 第 4 节支持表、12 项纯合同检查及 MuJoCo Solution／expert／故障／typed 控制冻结证据；部分 mixed／COM 交集未复验 | R15～R21 均有实施者结论；U4 可继续。完整 Solution 保留 E13 |
| U4 | 实施者自评完成，独立主审及维护者接收待定：示例按控制能力选动作，Nut caller-owned Solution 接受正式 schema，版本诊断标明真实成本并增加配置 import／资产守卫 | 第 5 节分类、11 项精确纯检查及[四任务示例计划](../../../../../workspace/maintenance/v211_u4_cli_20261112_003/plan.json)；LIBERO 静态核对 | R22～R25 均有实施者结论；批处理／训练与完整 benchmark 不在本单元 |
| U5 | 尚未执行最终事件接收 | 没有新 native 或完整 Solution 结果 | R26～R30 |

当前 Controller owner 调整后，119 项受影响诊断通过；[冻结输入](../../../../../workspace/maintenance/v211_u1_position_controller_owner_20261112_002/plan.json)下 MuJoCo PickCube／Nut 和 Isaac Position／effort 各完成 5 个显式子步、二次 reset 与 close，Isaac 日志未见 traceback，隐式启动推进数未知。先前运行期间发生源码输入漂移，两条 Isaac 各消耗 5 个显式子步的结果未作为冻结输入证据；一次锁冲突未推进，均保留原始输出并计入计划。

USD delivery 精确身份及 policy 由 provider admission 持有；[先前 USD 准入验证](../../../../../workspace/maintenance/v211_u1_usd_admission_owner_20261112_001/plan.json)及[Joint／执行合同验证](../../../../../workspace/maintenance/v211_u1_joint_execution_contract_20261112_001/plan.json)按其输入身份参考。后者的 Isaac Position 关闭日志含 SDK 菜单回调空 USD context `AttributeError`。

PickCube 与 NutAssembly 的 arm／gripper actuator 由所选 Panda 声明，[MuJoCo 短程](../../../../../workspace/maintenance/v211_u1_robot_actuation_20261112_001/plan.json)覆盖 Position、两种 effort、装配 Panda 与 Nut 单个受限 Solution interval；[GeoPhys effort](../../../../../workspace/maintenance/v211_u1_mjcf_source_owner_20261112_001/geophys-plan.json)子步未独立计数。旧记录的 source 哈希如在启动后补记，已在对应计划中标明，不能当作启动前冻结。

缓存 source 复用前验证快照或 USD 新鲜度；[缓存验证](../../../../../workspace/maintenance/v211_u1_cached_source_freshness_20261112_001/plan.json)覆盖关节 effort 的 reset 与 close。各短程不代表完整 Solution、所有 provider／renderer 或 U1 最终接收。

每格完成只写最终行为、真实 owner／提交／证据和残余限制；过程及失败日志保存在各单元原始输出，不在此逐次追加。目标是让下一次恢复直接读本表及当前单元，而非重走全仓发现流程。
