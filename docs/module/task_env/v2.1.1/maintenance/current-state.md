# v2.1.1 当前状态

更新时间：2026-11-12。本文是版本的人工可读当前摘要；工作包、attempt 和历史记录由[编排索引](orchestration.json)维护，逐项优化范围由[优化台账](../planning/post-5c-code-project-optimization-diagnostic-ledger.md)维护。

## 当前停门

**G01～G05 已按各自范围有界接收，5c 诊断单元 1～9 收口；维护者已确认进入 5c 后代码与项目优化。G06／G07 尚未开始，v2.1.1 尚未完成。** 单元 1～9 是 5c 内部工作单元，版本仍为七阶段、二十二子阶段。

[单元 9 综合主审](reviews/20261111_unit009_sol_5c_bounded_acceptance_b23fb3cc.md)的 `SOL_ACCEPTED_BOUNDED_5C` 已由维护者在本次启动对话确认；原主审中的“维护者待确认”描述保留其审查时点。优化实施安排见[执行计划](../planning/post-5c-optimization-execution.md)。顺序为：G05 功能接收 → 代码优化、定向复验及人工接收 → 项目证据和 refs／worktree 整理及接收 → 决定进入 G06。G07 继续承担 G06 新增调用者及最终版本收口，7b 三 provider × 三 seed 门保留。

## 启动输入与工作归属

| 项目 | 2026-11-11 启动核对 |
| --- | --- |
| 分支 | `codex/v211-stage5-diagnostic`；优化复用，不新增分支／worktree |
| 输入 Core HEAD | `1f1359eef9bfff73cf7688a8270c5f06471dc614`；是启动输入，不是随文档提交滚动的最新 HEAD |
| 5c 接收生产基线 | `a53bf19d2526c6c336dd5d0d7108eb0f643f80bd`；输入 `task_env` tree 为 `c4460cd6bcc96a16067d3f61556a66e52da23bbc` |
| GeoPhys／Menagerie | `c1ea3cc9fb99ccbd1d31c36d6fc7b84aa936b3d7`／`b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` |
| 工作树 | 启动时 tracked clean；四个既有 untracked 输入原样保护，含优化台账 |
| 执行窗口 | 单元 9 已有返包及释放记录；启动观察未见本仓库 native worker，前序协调 chat 为 idle；启动时当前 chat 仅写 O0 文档；后续直接实施 E00～E04 的资源使用按其运行计划及释放记录核对 |
| 当前改动 | 启动文档之后维护者已直接授权 E00～E04；实施状态及首批代码／CPU 证据见执行计划第 6 节。其余优化与最终接收尚未完成，不沿用启动表充当实时锁 |

保护输入为 `MUJOCO_LOG.TXT`、2026-10-30 runtime route handoff、stage3 gravity proposal 和用户优化台账。精确大小／SHA-256 与原工作树状态在 ignored [输入快照](../../../../../workspace/maintenance/v211_post5c_optimization_o0_20261111_001/input-snapshot.json)。没有将它们加入本轮提交，也没有清理原始输出、改动 pins、merge／push／tag。

## 已接收的能力与边界

- G01 协议基线；G02 MuJoCo PickCube 成功参考及 Nut 回归；G03 路由、真实执行与 reset 重建；G04 typed 控制／贡献／反馈／Controller reset，分别按原主审范围保留。
- 一体 Panda、装配 Panda、Pendulum、双轮车有共同主体／Assembly／Controller／场景 interval 的受测链；不声称四主体都在最终生产 HEAD 重新运行。
- Pendulum／双轮车的 MuJoCo CPU、GeoPhys CPU 和 Isaac PhysX CUDA 短程路线限各自受测资产。三条首批原生窗口／离屏与 task RGB 按主审及影响复用。
- 最新 Isaac task RGB 已覆盖 reset、非零 step、二次 reset 及 close；GeoPhys CPU physics × MuJoCo renderer-only 已有真实状态映射和零额外物理推进证据。依据见[单元 7／8 主审](reviews/20261111_unit007_008_sol_review_a53bf19d.md)与单元 9 综合主审。
- renderer 创建时选定并保持到 close；通用动态切换、任意装配树、任意组合、通用闭环及完整 batch 能力仍不属于已接收结论。颜色／挂载／source 限制继续适用。

COM 原严格判据失败、维护者有界采纳、原 N08 FAIL、R05c `NOT_REQUALIFIED`、Isaac 6.1 close 限制及历史执行偏差保留；不借本次状态更新转移资格或重开 5c。

## 正式入口及下一交付

当前正式公开工厂为 `task_env.make_env`。PickCube／Nut 正式 UID 为 `pick-cube-p16-reference-v1`／`nut-assembly-outcome-reference-v1`；两简单主体使用各自注册 UID。它们当前的配置与构建协议尚未全部归并：candidate 仍是部分受测能力的入口，不能把优化目标写成已实现的新 API。

下一实施范围是 O1：配置字段归属／覆盖顺序、正式构建请求、旧 UID／factory 的迁移表；随后按 O2～O4 归位生命周期、source／renderer／observation 和 Recorder／caller。O5 必须完成两任务各自公开支持 provider 的单 seed 完整 Solution 与同次记录读回，至少 MuJoCo 任务成功；O6 逐项主审后才进入 O7 的项目清理。详见执行计划及原台账。

规划 [capability-matrix.json](../capabilities/capability-matrix.json) 尚待按实际证据逐格对账，旧 `NOT_RUN` 目标不能替代最新主审判断，也不能仅凭阶段接收批量改成 PASS。当前本地成果尚未合入 develop／main，未发布。

## E00～E04 当前实施

维护者已调整实施方向：四个正式任务统一配置和 Robot 构建链，不再兼容过时诊断；本版本诊断归 `task_env/diagnostics/tasks/v2.1.1/`。旧 `panda-position-servo-candidate-v1` 注册及其专属自动目录管理已退出正式入口；PickCube 使用的 Panda effort 绑定已从旧目录迁至 Robot，source 校验归 MuJoCo source adapter，旧 Position 诊断构建代码已退休。原 Position 历史证据保留，旧入口退休不等于 Position 控制能力退休。四个正式 Task 的 mapping／YAML 现进入同一种解析结果；Pendulum 和双轮车的普通构造已改用同一配置路径，旧 component 纯构建与其他未迁 caller 仍在。MuJoCo CPU 与 GeoPhys CPU 的 NutAssembly、PickCube 一体 Panda 路线已使用共同 Robot source 编译及控制绑定并各完成一个短程 interval；Isaac 对应主体路径及四任务完整共同构造仍待收敛，E00～E04 未接收；此前批次是历史执行记录。

Pendulum 和双轮车现由各自 Robot 声明受控关节、writer 和 source 中的根，复用同一个已有主体 effort 构建器完成 Assembly、Controller 及执行绑定；MuJoCo CPU 的 direct／velocity-damped 和 GeoPhys CPU 的 direct 短程已复验。Task 对各自 Scene／source 的部分构建仍待归位，Isaac 本批未实测，不能据此宣布四任务主体机制全部统一。

维护者已直接要求本会话实施 E00～E04，输入 `21577d32`，当前 chat 单 writer。共同构造和旧物理 UID 翻译之后，正式 PickCube（含物理配置）／NutAssembly／Pendulum／双轮车已从本次 Artifact 构造 TaskDefinition，观察调用共同语义 lifecycle，reset 后重新绑定。数组与具名 canonical state 各保留真实表示；Gym typed info 保留，Solution callbacks 使用公共 metadata 值投影。已准入的普通 native 路线安装现有 live source／Controller interval binding，移除安装处的单一 R05c profile 名称分流，原严格准入仍保留。本批生产代码净增 122 行，累计净增 154 行；tracked 文件数不变。152 个不同纯合同节点及五条 MuJoCo CPU 交集通过；累计受监督 36 次／290 个可观测子步，加前序 150 保守计费为 440。四次本批失败和原始拒绝均保留，未称完整 Solution 成功。配置 codec、剩余主体／registry／reset／action／clock／部署审计继续；E00～E04 未完成。详细证据与限制见[实施记录第 6 节](../planning/post-5c-optimization-execution.md#6-e00e04-实施记录)，不提前签收或启动 G06。

第六批将 Isaac source 首次重复编译收敛到共同构造，并让实际 physical execution 提供动作合同；Isaac 正式配置完成两次 reset／非零 step／三次 RGB 与独立读回。首次预检失败及受限修复、资源账和 SDK 退订诊断均保留。生产累计净增 182 行，文件数不变；其余 E00～E04 仍待逐项完成，细节见[第六批记录](../planning/post-5c-optimization-execution.md#65-第六批编译后的-controller-合同与-isaac-正式入口复验)。

第七批修复隔离 worker 的 source-bound 控制提交：正式 PickCube 在 MuJoCo CPU 和 GeoPhys CPU 两条受测路线均完成 reset／单 interval／第二次 reset／close。失败、未观测子步的保守计费和一次无锁资产解析的偏差保留；累计生产净增 228 行、tracked 文件数不变。见[第七批记录](../planning/post-5c-optimization-execution.md#66-第七批隔离-worker-的状态边界与控制归属)。

第八批将 Controller selector 在两类配置 codec 之前统一归一化；PickCube 也接受 `control.profile_id`，原输入、身份与能力限制保持。累计生产净增 235 行，详细证据见[第八批记录](../planning/post-5c-optimization-execution.md#67-第八批共同-controller-selector-的配置入口)。

第九批移除 registry 对构造方法覆盖的反射判断，基类工厂处理既有组件配置和旧 binding，四个实际 caller 合同通过。累计生产净增 237 行；E00～E04 仍在实施。见[第九批记录](../planning/post-5c-optimization-execution.md#68-第九批registry-不再反射判断构造方法覆盖)。

后续职责整理将 Panda MJCF 传动检查归入 MuJoCo source adapter，将质量模型执行组合归入 Controller owner。MuJoCo direct、joint-mass、R3-mass 真实短程复验通过；Isaac 质量模型未在本批重跑。见[职责整理记录](../planning/post-5c-optimization-execution.md#611-panda-mjcf-source-检查归属)。

此前增量让 reset 策略由任务 binding 声明，并移除 Panda source 检查中的历史 checkout 绝对路径；当时的 Position 旧入口自动目录回收记录见[实施记录](../planning/post-5c-optimization-execution.md#614-reset-重建能力归属)。该入口及其专属目录管理现已退休。

最新简单主体职责整理进一步将 Pendulum／双轮车的内联资产和 Scene 拓扑声明移至 Robot；正式构建用同一个 Robot 实例声明场景及绑定控制。两个 MuJoCo CPU 短程通过、场景身份与原实现一致；GeoPhys、Isaac 和 renderer 未在此批重跑。Task 中的 source 编译及 provider 分流仍待进一步归位，E01～E04 未完成。详见[实施记录 6.23](../planning/post-5c-optimization-execution.md#623-简单主体-scene-声明归-robot)。

Pendulum／双轮车的传动校验与 provider source 映射现由共同 source 编译器从 Robot 和 Scene 声明生成，Task 不再各自接线；MuJoCo CPU 和 GeoPhys CPU 的两任务短程均通过。Isaac 映射仅做不启动 SDK 的合同检查，完整四任务构建统一仍待完成。详见[实施记录 6.24](../planning/post-5c-optimization-execution.md#624-简单主体按声明共同编译-source)。

四个正式任务的 Controller 选择现直接使用 `controller.profile_id`；旧顶层、`task.controller_profile` 和 `control.profile_id` 选择位置已明确拒绝。四任务及装配 Panda 的 MuJoCo CPU 短程已复验，详细范围见[实施记录 6.25](../planning/post-5c-optimization-execution.md#625-controller-规范字段直达配置解析)。

正式执行选择已收敛到 `execution`／`episode`，旧顶层选择字段被拒绝；Harness 和本批识别到的录制、轨迹及环境脚本已迁移。Pendulum 旧 RGB 示例的渲染配置仍待迁移；E01～E04 保持未完成。详见[实施记录 6.26](../planning/post-5c-optimization-execution.md#626-正式执行配置和直接-caller-迁移)。

Panda direct effort 与两个简单主体现在共用已有主体 Assembly 编译，单层和嵌套结构均从声明进入共同绑定；Position 路线仍待进一步共同化。MuJoCo CPU 三条 effort 短程及两个简单主体 GeoPhys CPU 短程已通过，详见[实施记录 6.27](../planning/post-5c-optimization-execution.md#627-单层与嵌套已有主体的-effort-assembly-编译)。

Position 与 effort 的已有实体及关节成员现由共同 Assembly owner 声明，保留各自控制合同；六条 MuJoCo CPU 短程及记录的主体／source 身份对照通过。完整四任务共同构造和 E01～E04 仍未收口，详见[实施记录 6.28](../planning/post-5c-optimization-execution.md#628-position-与-effort-共用已有主体成员声明)。

Env 中无正式调用者的 Position／leaf Position 候选构造入口及其执行选择解析已退休；正式 Position 和仍有实际调用的 mixed-control 路径保留。旧 leaf 内部控制分支仍待审计。六条 MuJoCo CPU 短程在最终构造签名下通过，见[实施记录 6.29](../planning/post-5c-optimization-execution.md#629-退休-position-诊断构造旁路)。

旧 leaf 诊断的 Env／Runtime 控制分派及预检入口已退休；装配 Panda 使用的主体配置声明保留。隔离 worker 测试发现的旧 Controller 配置投影已修复，PickCube／NutAssembly MuJoCo worker 均复验通过。底层 leaf 及观察／记录剩余分支待继续审计，E01～E04 未完成。详见[实施记录 6.30](../planning/post-5c-optimization-execution.md#630-退休-leaf-控制分派并修复-worker-配置投影)。

已退休 leaf 路线的观察与记录分支已移除，历史 H5 reader 保留；实际短记录验证同时修复了 typed observation schema 的 JSON 投影。发现 PickCube reset-scoped 物理选择在 reset 前不暴露 `env.robot`，是 E02 待修复缺口，不能视为四主体构造统一已完成。详见[实施记录 6.31](../planning/post-5c-optimization-execution.md#631-退休-leaf-观察记录分支并修复记录投影)。

PickCube reset-scoped 物理选择现在在 reset 前暴露已编译 Robot subjects、无已提交 Controller；reset 后 Robot 指向实际提交的 physical Controller，错误切换保持原视图，有效切换后的 Controller 已实际推进。该路线的 `env.controller` 仍承担原 Position 兼容职责，完整统一仍待 E02／E04；详见[实施记录 6.32](../planning/post-5c-optimization-execution.md#632-reset-scoped-物理选择的-robot-声明与提交)。

两个 PickCube 物理诊断 UID 和旧输入翻译已退休，正式 PickCube 的物理 binding 保留；MuJoCo CPU 受影响短程通过，Isaac 仅检查 binding 工厂可导入。物理实现仍有任务内 candidate 职责，后续需继续归位。详见[实施记录 6.33](../planning/post-5c-optimization-execution.md#633-退休-pickcube-物理诊断-uid)。

PickCube MJCF 场景现直接将 Robot 声明与任务实体组合，不再先构造并改写 Isaac 场景；两路线的场景 mapping／identity 保持一致，受影响 MuJoCo CPU 物理短程通过。Isaac 仅做声明对照，完整 source 和控制归属仍待整理。详见[实施记录 6.34](../planning/post-5c-optimization-execution.md#634-pickcube-任务场景直接组合-robot-声明)。

Pendulum 与双轮车现在通过共同 Task Source 编译器从 Robot／Scene 声明生成 joint-effort Artifact；两种 source revision 的 Artifact 与先前身份一致，MuJoCo CPU 两条短程通过。tabletop 尚未使用此专用编译入口，四任务完整共同构造仍未收口；见[实施记录 6.35](../planning/post-5c-optimization-execution.md#635-简单主体-task-artifact-共同编译)。

Pendulum／双轮车的 Task 采样结果现在经共同 joint-effort reset 合同编译；两任务 MuJoCo CPU 的 reset、RNG 序列和短程已对照通过。tabletop reset 和完整生命周期仍须继续收敛，见[实施记录 6.36](../planning/post-5c-optimization-execution.md#636-简单主体-joint-effort-reset-合同归并)。

Pendulum／双轮车现在由同一 binding owner 实际编排 Robot、Scene、Artifact、source 和 Controller，Task 只提供各自声明及语义；MuJoCo CPU direct／阻尼和 GeoPhys CPU direct 短程通过。tabletop 的主体构建仍须继续收敛，见[实施记录 6.37](../planning/post-5c-optimization-execution.md#637-简单主体共同-taskrobot-构建编排)。

四个正式任务现在可通过同一 registry 和 `robot.uid` 选择实际 Robot；Pendulum／双轮车不再由 Task 直接实例化具体主体，且不需伪造 Panda 专属能力。显式主体选择的五条 MuJoCo CPU 短程通过；source／Controller 的全部共同构建仍待完成。见[实施记录 6.38](../planning/post-5c-optimization-execution.md#638-四任务-robot-身份与实例创建入口)。

可切换 physical Controller 现在由 `env.controller` 和 `env.robot.controller` 同时公开实际已提交对象，首次 reset 前为 `None`；Position 的状态投影与记录继续使用内部对象。MuJoCo 四任务、装配 Panda 及切换后实际推进已按影响复验；完整统一仍未完成。详见[实施记录 6.39](../planning/post-5c-optimization-execution.md#639-公开-controller-与实际提交者对齐)。

正式配置已退休历史 `execution.source_workspace`，物理 source 快照由内部 owner 管理并在 close 后释放；MuJoCo 受影响路线和记录短程已复验。详见[实施记录 6.40](../planning/post-5c-optimization-execution.md#640-退休诊断-source_workspace-输入)。

固定 physical execution 与 Position 投影并存时，Env／Robot 也公开实际 physical Controller，避免同一动作有两个对外身份；验证及范围见[实施记录 6.41](../planning/post-5c-optimization-execution.md#641-固定-physical-controller-的公开归属)。

四任务的 Artifact 主体现从注册 Robot 的共同声明合同产生；公共 Assembly compiler 不再硬编码 Panda 主体。MuJoCo 四任务／装配 Panda 与 GeoPhys 三条受影响路线短程通过；完整四任务构建链尚未合流。详见[实施记录 6.42](../planning/post-5c-optimization-execution.md#642-robot-提供-task-artifact-主体声明)。

Runtime 现直接消费已声明或 reset 已提交的 physical execution；正式物理任务不再分别提供取回该对象的 binding 回调。MuJoCo 四任务／物理序列与 GeoPhys 两条受影响路线通过短程；Isaac 仅完成静态构建合同检查。详见[实施记录 6.43](../planning/post-5c-optimization-execution.md#643-runtime-直接消费-physical-execution-声明)。

PickCube／NutAssembly 的 Artifact 和 RuntimeSource 现消费构建时同一个 Robot 实例；MuJoCo 四任务／装配 Panda 和 GeoPhys 两个 tabletop 任务短程通过。装配 source 替换及完整构建链仍待收敛，详见[实施记录 6.44](../planning/post-5c-optimization-execution.md#644-tabletop-artifact-与-runtimesource-使用同一个-robot-实例)。

PickCube 与 NutAssembly 的 R3、arm hold 与 gripper cadence 现由共同 Controller owner 从已声明 source 构造；MuJoCo 与 GeoPhys tabletop 短程已复验，完整 Controller 构建统一尚未完成。详见[实施记录 6.45](../planning/post-5c-optimization-execution.md#645-r3-controller-构造归控制-owner)。

公共 Env 中旧 component 配置转 physical task 的不可达分支及重复检查已移除；四个正式任务继续使用同一正式配置路径。MuJoCo 四任务／装配 Panda 与 GeoPhys 两条受影响路线短程通过；详情及限制见[实施记录 6.46](../planning/post-5c-optimization-execution.md#646-退休旧-component-physical-构建分支)。

两个 tabletop Task 类不再预创建共享 binding 或重复配置入口；正式 `make_env` 为各环境建立独立 binding 与 source。受影响 MuJoCo 和 GeoPhys 短程已复验；详见[实施记录 6.47](../planning/post-5c-optimization-execution.md#647-退休-tabletop-类级共享-binding)。

Panda direct effort 与两个简单主体现通过共同 Runtime 入口构建单主体 physical execution；双轮车的被动俯仰状态独立保留。MuJoCo 与 GeoPhys 受影响短程、原构造合同对照通过；多主体和 Position 路线仍待收敛。详见[实施记录 6.48](../planning/post-5c-optimization-execution.md#648-单主体-effort-execution-共同构造)。

装配 Panda 中无调用者的旧 leaf 诊断配置生成逻辑已移除；正式双 Controller 在一次 MuJoCo interval 中的两个 writer 与资源归属已复验。详见[实施记录 6.49](../planning/post-5c-optimization-execution.md#649-清除装配-panda-的无调用-leaf-诊断探针)。

四个正式任务的 mapping／YAML 构造现只调用一次配置解析器，外部已解析对象仍执行一致性检查；MuJoCo、隔离 worker 与 GeoPhys 的受影响短程已复验。详见[实施记录 6.50](../planning/post-5c-optimization-execution.md#650-正式公共配置只解析一次)。

Panda 参考 effort 的普通、动态和质量矩阵 Controller 组合已归共同控制 owner，MJCF／USD 各自保留 source、TCP 和 frame 的声明与校验。MuJoCo reset 切换短程及 USD source 构造检查通过；详见[实施记录 6.51](../planning/post-5c-optimization-execution.md#651-panda-参考-effort-controller-组合归控制-owner)。

USD 与 MJCF 的 Panda effort 现通过同一主体声明及 Runtime 构建；修复 USD 力矩 binding 被误认作 Position source 的错误。指定 Isaac CUDA／同步 RGB 路线及 MuJoCo 受影响短程已复验；首次失败及 SDK 清理异常保留。详见[实施记录 6.52](../planning/post-5c-optimization-execution.md#652-usd-panda-effort-使用共同主体构建)。

Panda effort 的 Scene 声明与物理构造现由同一 Robot 实例承担；MuJoCo 受影响短程和 MJCF／USD source 构造对照通过。详见[实施记录 6.53](../planning/post-5c-optimization-execution.md#653-panda-effort-声明与构造共享-robot-实例)。

简单主体的直接及阻尼 effort Controller 选择已归控制 owner，并共用 source／writer／单位检查；MuJoCo 两任务和 GeoPhys 已支持路线短程复验。详见[实施记录 6.54](../planning/post-5c-optimization-execution.md#654-简单主体的-effort-controller-归控制-owner)。

共同 Env 已退休旧诊断 profile 的构造与 worker 分支；四任务 MuJoCo、tabletop 隔离 worker 和 GeoPhys 受影响短程通过。详见[实施记录 6.55](../planning/post-5c-optimization-execution.md#655-从共同-env-退休旧诊断-profile)。

旧 C05c CUDA cadence 专属 Runtime 准入已退休；正式 MuJoCo 四任务、GeoPhys PickCube 和 Isaac RGB 受影响短程已复验。详见[实施记录 6.56](../planning/post-5c-optimization-execution.md#656-退休-c05c-历史-runtime-准入)。

退休 Position candidate 输入专属的 observation／录像写入分支已移除；MuJoCo 装配 Position 录像及 Isaac 正式 Position／RGB／H5 的 native 收据已复验。详见[实施记录 6.57](../planning/post-5c-optimization-execution.md#657-退休旧-position-输入的-observation-和录像-writer)。

旧 F05 Position 的三条 Session 准入及材料化分支已退休；正式 MuJoCo 四任务、GeoPhys 和 Isaac Position／effort 受影响短程已复验。底层历史类型和相关诊断仍待后续清理。详见[实施记录 6.58](../planning/post-5c-optimization-execution.md#658-退休-f05-旧-position-session-入口)。

F05 孤立输入类型与专属 GeoPhys/USD native adapter 两个无生产调用者的文件已删除；正式 MuJoCo／GeoPhys 短程通过。详见[实施记录 6.59](../planning/post-5c-optimization-execution.md#659-清除-f05-孤立-native-输入与-geophys-adapter)。

旧 Position candidate 六个仅供历史诊断的资产已退休，Git blob 与 SHA-256 已记录；正式 PickCube 两条受影响 MuJoCo 短程通过。详见[实施记录 6.60](../planning/post-5c-optimization-execution.md#660-退休孤立-position-candidate-资产)。

Isaac adapter 已退休旧 DG04 专用构造和 witness，正式 F06 Position／effort、RGB、关闭及 Position H5 native 收据已复验；关闭日志的扩展异常保留。详见[实施记录 6.61](../planning/post-5c-optimization-execution.md#661-退休-isaac-adapter-的-dg04-专用分支)。

一体和装配 Panda 的零偏置 effort Controller 创建已归共同控制 owner；正式一体 Panda 的 MuJoCo／Isaac 路线复验，装配 effort 尚无正式 caller。详见[实施记录 6.62](../planning/post-5c-optimization-execution.md#662-panda-零偏置-effort-controller-归控制-owner)。

Panda effort profile 语义已从 PickCube candidate 归控制与 Robot owner，Task 继续执行 source／provider 准入；受影响 MuJoCo／Isaac 路线已复验。详见[实施记录 6.63](../planning/post-5c-optimization-execution.md#663-panda-effort-profile-语义归控制与-robot-owner)。

MJCF／USD 的 Panda effort 参考参数与质量模型准入已收敛为一份 Task 声明，受影响 MuJoCo reset 切换和 Isaac effort／RGB 已复验；Task 的 source 专属构建仍待收敛。详见[实施记录 6.64](../planning/post-5c-optimization-execution.md#664-收敛-panda-effort-参考参数的重复准备)。

PickCube USD Scene 声明与 effort 构造现使用同一 Panda Robot 实例；真实 source 对照和 Isaac 短程已复验。详见[实施记录 6.65](../planning/post-5c-optimization-execution.md#665-usd-panda-声明与-effort-构造共享-robot)。

Pendulum 与双轮车现将 source 校验过的同一份传动声明用于 Assembly／Controller；MuJoCo 与 GeoPhys 短程通过，Isaac 本批只有无 SDK 合同检查。详见[实施记录 6.66](../planning/post-5c-optimization-execution.md#666-简单主体复用-source-校验过的传动声明)。

PickCube GeoPhys direct effort 已与 MuJoCo 使用相同的物理 Controller／V2 状态路径；真实短程通过，录像因缺少 Solution identity 在写入前被拒绝。详见[实施记录 6.67](../planning/post-5c-optimization-execution.md#667-pickcube-direct-effort-统一物理状态路径)。

PickCube 固定 MJCF effort profile 已直接消费 source action 配置并使用 V2 状态，joint／R3 的 MuJoCo／GeoPhys 短程通过；reset 切换和 USD 的 Position 观测依赖仍待处理。详见[实施记录 6.68](../planning/post-5c-optimization-execution.md#668-固定-panda-effort-不再依赖-position-观测)。

PickCube MJCF effort 的 Task source、Scene 和 Controller 构造现共享同一 Panda；切换到纯物理 V2 的尝试因录像仍依赖 Position 生命周期而撤回。详见[实施记录 6.69](../planning/post-5c-optimization-execution.md#669-mjcf-panda-source-与物理构造共享-robot)。

可切换 effort 的录像元数据现直接来自物理执行和 source，不再套用 Position 元数据；物理及装配 Position 的 MuJoCo H5 已复验。详见[实施记录 6.70](../planning/post-5c-optimization-execution.md#670-物理控制录像元数据归实际执行-owner)。

PickCube MJCF reset 切换已改用活动物理 Controller 与 V2 状态，切换／H5 和 R3 Solution 单步通过；USD 仍待收敛。详见[实施记录 6.71](../planning/post-5c-optimization-execution.md#671-reset-切换使用实际物理状态与-controller)。

PickCube USD effort 已由物理 Runtime 发布 V2 任务状态，Isaac 同步 RGB 与 MuJoCo 切换短程通过；构建时仍临时创建 Position 对象。详见[实施记录 6.72](../planning/post-5c-optimization-execution.md#672-usd-effort-使用物理状态与-source-准入)。

USD effort 已直接构造物理 Controller，不再临时创建 USD PositionServo；参考 source 准备仍创建参考 Controller。Isaac effort／Position 短程均通过，详见[实施记录 6.73](../planning/post-5c-optimization-execution.md#673-usd-effort-直接构造物理-controller)。

PickCube 的 Task source 与 readiness 准备已和参考 Controller 构造分开；MJCF／USD effort 不再创建参考 Controller，详见[实施记录 6.74](../planning/post-5c-optimization-execution.md#674-task-source-准备不再创建参考-controller)。

USD 构造完成或在 source 准备之后失败时，借用的 MJCF Task 快照已由构造者释放；Isaac effort／Position 已复验。详见[实施记录 6.75](../planning/post-5c-optimization-execution.md#675-usd-构造释放临时-task-source-快照)。

两个 tabletop 的 source 准备与 Controller 构造失败清理已进一步收敛；MuJoCo 短程及版本检查通过，GPU 未按本批代码重跑。详见[实施记录 6.76](../planning/post-5c-optimization-execution.md#676-task-source-失败前后资源归属)。

PickCube 物理控制不再将 reset seed 冻结在构造时；MuJoCo 多 seed 短程和 Solution reset 已验证，Isaac 本批只验证重建调用合同。详见[实施记录 6.77](../planning/post-5c-optimization-execution.md#677-物理控制使用请求的-reset-seed)。

共同配置不再写死 PickCube reset profile 的名称和 Controller 条件，由任务声明能力并验证组合；四任务 MuJoCo 短程通过。详见[实施记录 6.78](../planning/post-5c-optimization-execution.md#678-reset-profile-准入归任务声明)。

统一配置按实际 Robot 的声明准入位置驱动重力补偿；两个 tabletop 的 MuJoCo 短程通过。详见[实施记录 6.79](../planning/post-5c-optimization-execution.md#679-robot-声明位置驱动重力补偿能力)。

NutAssembly 的 R05b／R05c 历史诊断专属构造与 Runtime 准入已退出；四任务 MuJoCo 和 NutAssembly GeoPhys 短程通过，历史资格边界保留。详见[实施记录 6.80](../planning/post-5c-optimization-execution.md#680-退出-nutassembly-历史诊断构建分支)。

Isaac Position 已通过 Panda 共同主体编译生成实际 Controller plan，并完成原生短程与三帧读回；USD source 自身的 Position binding 仍待收敛。详见[实施记录 6.81](../planning/post-5c-optimization-execution.md#681-usd-position-使用-panda-主体和实际-controller-plan)。

Controller 变更限定于 reset；旧 episode 内 Position 替换及其专属状态、录像分支已退出，MuJoCo reset 切换和 Isaac 录像短程通过。详见[实施记录 6.82](../planning/post-5c-optimization-execution.md#682-controller-切换限定于-reset)。

USD Position 的主体和 Controller plan 已由 source 持有，Robot 与 Runtime 从同一 source 消费；Isaac 原生短程及四任务 MuJoCo 短程通过。详见[实施记录 6.83](../planning/post-5c-optimization-execution.md#683-usd-position-主体和-plan-由-source-持有)。

Position Controller 选择与物化现在核对 source 持有的真实主体、writer 和资源，不再用 profile 名称冒充主体；Isaac 及四任务 MuJoCo 短程通过。详见[实施记录 6.84](../planning/post-5c-optimization-execution.md#684-position-controller-匹配实际主体)。

历史 C02b R1 typed-force 专属准入与独立施控旁路已退出；正式 native force 反馈保留，MuJoCo 与 NutAssembly GeoPhys 短程通过。详见[实施记录 6.85](../planning/post-5c-optimization-execution.md#685-退出历史-c02b-r1-typed-force-旁路)。

旧 leaf 专属物化和直接 actuator 写入已退出；装配 Panda 的双 writer 共同提交及 Isaac Position 短程通过。详见[实施记录 6.86](../planning/post-5c-optimization-execution.md#686-退出旧-leaf-专属物化与-actuator-旁路)。

旧 leaf dispatcher 和专属提交入口已退出；共同提交、装配双 writer、Isaac Position 及历史 H5 解码分别复验。详见[实施记录 6.87](../planning/post-5c-optimization-execution.md#687-退出旧-leaf-控制提交与-dispatcher)。

旧 mixed-actuator candidate 的 Env 专属生命周期已退出；四任务 MuJoCo、NutAssembly GeoPhys 和 Isaac Position 短程复验通过。详见[实施记录 6.88](../planning/post-5c-optimization-execution.md#688-退出旧-mixed-actuator-candidate-的-env-生命周期)。

Isaac Position 现在直接准备 Task source，不再构造并丢弃 MJCF 参考 Controller；USD 主体／Controller plan 和原生短程已复验。详见[实施记录 6.89](../planning/post-5c-optimization-execution.md#689-usd-position-直接准备-task-source)。

native Position 物化改按 Controller 声明核对 Joint，完整 USD 绑定仍由 source 准入核验；Isaac PickCube 短程及错误映射拒绝已复验。详见[实施记录 6.90](../planning/post-5c-optimization-execution.md#690-native-position-按-controller-声明核对关节)。

旧 native-feedback 专属绑定与提交旁路已退出，native 控制缺少 source 主体时在物化前拒绝；进程内、隔离 worker 和 Isaac 受影响短程已复验。详见[实施记录 6.91](../planning/post-5c-optimization-execution.md#691-native-feedback-只消费-source-owned-主体绑定)。

共同 Env 构造现在要求真实 Robot 主体；缺失绑定时拒绝并清理 source，四任务 MuJoCo 短程通过。详见[实施记录 6.92](../planning/post-5c-optimization-execution.md#692-正式构造要求真实-robot-主体)。

共同 Controller 选择现核对 source 主体 plan 中的一体／多 owner 身份；MuJoCo 进程内及隔离 worker、GeoPhys NutAssembly 短程通过。详见[实施记录 6.93](../planning/post-5c-optimization-execution.md#693-controller-选择核对主体计划中的实际-owner)。

四任务默认 Robot UID 已在共同配置解析阶段确定；MuJoCo、GeoPhys 和 Isaac 受影响短程及两个 MuJoCo worker 已复验。详见[实施记录 6.94](../planning/post-5c-optimization-execution.md#694-默认-robot-在共同配置中确定)。

四任务配置现在明确解析实际 Controller profile；NutAssembly 声明既有 R3，普通 effort 构造不再重复补默认值。详见[实施记录 6.95](../planning/post-5c-optimization-execution.md#695-controller-profile-在共同配置中确定)。

两个 tabletop 的 MJCF 参考 Position Controller 选择与构造已归共同 Controller owner；R1、R3、装配主体及受影响短程已复验。详见[实施记录 6.96](../planning/post-5c-optimization-execution.md#696-tabletop-参考-controller-构造归共同-owner)。

只改变 Solution 姿态绕行的历史别名已退出正式 Controller 选择；正常 R3 的受影响 MuJoCo、GeoPhys 和 Isaac 短程已复验。详见[实施记录 6.97](../planning/post-5c-optimization-execution.md#697-solution-诊断别名退出-controller-配置)。

已退休姿态绕行的 Solution 分支及配置已清除，正常预算保留；PickCube Solution 的 MuJoCo／GeoPhys 单步与 Isaac 外部 action 短程已复验。详见[实施记录 6.98](../planning/post-5c-optimization-execution.md#698-清除退休姿态绕行的-solution-分支)。

已解析 Controller profile 现在由 control 配置单独存储；四任务 MuJoCo、两个 worker 和 GeoPhys NutAssembly 短程通过。详见[实施记录 6.99](../planning/post-5c-optimization-execution.md#699-controller-profile-只有一个配置-owner)。
