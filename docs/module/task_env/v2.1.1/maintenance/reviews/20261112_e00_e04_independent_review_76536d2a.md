# E00～E04 独立主审：共同构建与生命周期有界接收建议

日期：2026-11-12。审查输入 `codex/v211-stage5-diagnostic@3b5023e8e8674b74535e2e20ec7952bab9b55edd`，生产实现 `76536d2a0625aa79ff85fce0f1777d98ea0a3689`。结论：`BOUNDED_ACCEPTANCE_RECOMMENDED_WITH_NOTES`；维护者最终接收尚未作出。本报告只审 E00～E04，不接收全部优化台账、E05～E16、G06 或整个版本。

依据：[优化总台账](../../planning/post-5c-code-project-optimization-diagnostic-ledger.md)、[R01～R30 专用账本](../../planning/post-5c-e00-e04-remaining-ledger.md)、[既定 Goal](../../planning/post-5c-e00-e04-goal.md)。实施者自评作为待核输入；本次读取当前源码、调用关系、Git diff、冻结 patch、原始结果和诊断实现后独立判断。

## 1. 接收判断

**E00～E04 的本轮代码目标可以有界接收。未发现需要重开 U1～U5 的生产阻塞项；但 R25/R30 的资料收口尚未完全结束，不能将 30 格写成无余项全部关闭。** 六项确定的实现职责调整已经落到被四正式任务消费的 owner；主要改进发生在真实构造过程，并非只增加 RobotRuntime 外观或共同 receipt。余下可读性和文档问题见第 5 节，不另造一轮底层重构或全矩阵门。

| 事件 | 独立判断 | 依据及边界 |
| --- | --- | --- |
| E00 | 基线与本轮度量可接收，当前记录有勘误项 | 核对实际 HEAD、工作树、pins、变更统计和证据身份。四个 untracked 保护输入与规划快照逐字节一致；dirty 执行记录与较早规划快照不同，见第 5 节，不能笼统写成跨全部时点均未变化 |
| E01 | 四任务范围可接收 | 四类共同使用 `make_env → from_resolved_config → resolve_task_env_config → TaskBuildRequest`；规范 section、mapping/YAML、默认 Robot、Controller 与 execution 的单一来源成立。范围外 component codec 的存在不推翻此结论 |
| E02 | 共同构建阶段及受测主体绑定可接收 | source、Controller、reset plan 由已有 builder 调用各 owner；Panda Position/effort、USD 与简单主体保留合法 typed 差异。Task 尚非全部薄绑定，不接收任意资产/主体组合或完整 source 治理 |
| E03 | 受影响生命周期与资源合同可接收 | 共同 reset/step/close owner 保留，新增 RNG 回滚与失败 Runtime owner 可达性修复有纯/fake 检查；最终 MuJoCo 成功路径有原始证据。真实 Isaac/camera 失败注入未做，不冒充已测 |
| E04 | 当前支持动作链可接收 | 普通 action、已支持 ExpertAction、兼容 Solution 和 typed 控制汇入共同 dispatcher/submission；兼容提案重复处理已收敛。完整 Solution 与其余 mixed/COM/sequence 交集不由本轮短程外推 |

“可接收”是独立审查建议；不是代替维护者接受，也不是重新 Qualification。G05/5c 的既有有界接收、COM 历史失败和 R05c 限制均保留。

## 2. 真实构造与执行链

共同入口在 [registry.py](../../../../../../task_env/registry.py) 和 [configuration.py](../../../../../../task_env/environment/configuration.py)。四正式类均声明 `uses_selected_public_config`；`make_env` 将原配置交 `from_resolved_config`，后者调用共同 resolver，再选择一次 Robot。预解析配置会重验身份；正式类不接受旧 component 构造。账本中将 resolver 写在 `from_resolved_config` 之前是简写，准确顺序以上述源码为准。

[SourceBoundTaskBuilder](../../../../../../task_env/environment/reference_binding.py) 实际执行 source 编译/缓存校验、可选 source composition、Controller factory、Task 语义/身份绑定和 reset plan；`ReferenceTaskBinding.build_for_request` 提供共同请求及最终 Robot source 组合，`from_task_binding` 只消费结果。它没有统一所有 native 算法，也没有新增第二个 Runtime。

| 之前确认的六项调整 | 当前落点及实际数据流 | 独立判断 |
| --- | --- | --- |
| R02 共同阶段 | `SourceBoundTaskBuilder.__call__ → source_composer/controller_factory/compile_control`；`build_for_request → _compose_robot_source`；`from_task_binding → bind_compiled_control` | 被真实 caller 使用；不是一个不被消费的新 schema |
| R03 PickCube MJCF | `_position_reference_builder`、effort builder 分别提供任务声明和参数；`compose_declared_reference_source`、`bind_reference_scene_source` 处理 source，`build_reference_position_controller` / `compile_panda_effort_selection` 创建 Controller | Task 不再直接实现 Position/effort Controller 算法和 source lowerer；readiness、任务参数及 provenance 留 Task |
| R04 PickCube USD | `_isaac_reference_builder` 将 source/Artifact 交 `build_usd_panda_control`；`compile_usd_task_runtime_input`、`build_usd_runtime_source`、provider admission 持有 USD 输入及准入；主体路径由 articulation 声明推导 | 精确 F06 准入及 freshness 保留；Task 的物体/语义映射和 readiness 仍属合法输入；不要求自动安装资产 |
| R05 Nut 构造 | `_reference_builder` 调同一 builder 和 Position factory；Controller owner 提供 hold/cadence 与身份绑定，Task 提供接触参数、Solution/provenance 和 guard | 不再由旧 `_build_reference` 一段独立完成 Controller 构造；未抽取全部 Nut guard/stream，后者仍属后续范围 |
| R06 简单主体 | `ExistingSubjectEffortTask.bind` 的 source/control 两阶段进入同一 builder；`compile_declared_effort_source` 与 `build_existing_subject_effort` 交接主体、传动和 Controller | 两任务无独立 step/reset/close；无需伪造 Panda gripper/ee，也无需使用相同的 Panda lowerer |
| R16 兼容提案 | `step_with_solution` / `step_expert → _prepare_solution_action → _step → prepare_selected_control_action` | 共享 act、提案检查和投影；标准 caller-owned `act → env.step → observe` 不由 Env 额外调用 act/observe |

装配 Panda 仍有 Controller 创建后的 source composition。这不自动构成未统一：composition 消费实际 writer，最终 `bind_selected_controller` 核验 source-owned binding 与实际 Controller；原始短程保存了两 writer、不相交的 arm/hand 资源及实际完成 writer。复合 Controller 的提交 identity 与 Robot 暴露的两个叶 Controller identity 属不同层级，不能要求它们逐项相等。

主体→Scene writer→native 映射并非只比对同一份字符串。MuJoCo 原始 `native_layout` 保存了模型关节地址、DOF、actuator 等；一体 Panda、装配 Panda、Nut 各为 9 个状态关节及 8 个 actuator，Pendulum 为 1/1，双轮为 3/2。最终绑定及 TaskDefinition/observation-space 的重建也有检查。它不证明任意新模型可直接接入。

执行链为 `prepare_selected_control_action → submit_control_command → RuntimeSession`。submission 对 dispatcher 的 source、Artifact、episode、boundary、Controller generation/identity 进行消费核验，提交成功/失败更新 stage，并关联场景贡献及 writer；不是只记录一个不参与执行的 PASS 字段。Position、effort、wrench 保留各自单位与物理意义。完整 source、renderer registry、Recorder/replay 整理不在本轮宣布完成。

## 3. R01～R30 独立核对

下表的“满足”限定于本轮规定范围；未重跑的证据不写成新实测。原始读取和独立检查见第 4 节。

| 检查点 | 主审结论 | 对应事实/限制 |
| --- | --- | --- |
| R01 | 满足 | 四正式类、规范配置及拒绝边界；独立 mapping/YAML/default/identity 检查通过；resolve-once 实际 caller 源码成立 |
| R02 | 满足 | 共同 builder 实际控制 source/Controller 阶段，最终 result 被 Env 消费 |
| R03 | 满足 | MJCF source/composition 与 Position/effort factory 已回 owner；Task 保留 readiness/声明 |
| R04 | 满足 | USD input、路径推导、admission 和 Controller capability 有实际交接；冻结 Isaac 输入可复原 |
| R05 | 满足 | Nut 使用共同 builder/factory；Controller 不为创建自身而 import Nut Solution |
| R06 | 满足 | 两简单主体的 source/control 阶段使用共同请求与 builder，无独立生命周期 |
| R07 | 满足 | 最终 source/Controller matching、MuJoCo native mapping、装配双 writer；不扩大为全 provider 映射矩阵 |
| R08 | 满足 | TaskDefinition 按当前 Artifact 绑定并在 reset 后重绑，空间及实际 Controller 来源可对应 |
| R09 | 满足 | 新 source/Controller 失败、Env 半构造的清理 owner 可追踪；原异常及 cleanup note 保留 |
| R10 | 满足 | cache 复用前校验 receipt/USD freshness；验证新 source 后才退休不同旧 lease，失败新 lease 清理有检查 |
| R11 | 满足 | 预检、破坏旧 episode、重建及 fault 边界明确；无副作用拒绝回滚 RNG；显式 seed 与连续 seed=None 有对应检查 |
| R12 | 满足 | materialize/reset/readback/Controller 初始化/TaskDefinition/observation/publication 在共同事务下执行；RGB 失败可 latch fault |
| R13 | 满足 | worker source/session/runtime/task 清理与跨进程 error notes 有 fake 检查；既有 worker 路径未在本轮新增实现 |
| R14 | 满足，有界 | camera/visual 与 Runtime/App 资源 owner 分明；fake 失败和真实正常 close 分列。Isaac 关闭日志不是“全部 SDK 无异常” |
| R15 | 满足 | Position、effort、ExpertAction、兼容 Solution、sequence/mixed 有明确支持/拒绝边界；Nut 裸数组仍拒绝 |
| R16 | 满足 | 两兼容入口的提案准备收敛；错误阶段字符串参与行为的可读性余项见第 5 节 |
| R17 | 满足，有界 | stale 无副作用拒绝与 act 后失败有真实短程，partial write 为 fake 合同证据，未写成真实注入 |
| R18 | 满足 | dispatcher 被实际提交核验；命令/场景资源/推进关联有源码与原始 interval 支持；不把 ACK 单独当物理证明 |
| R19 | 满足，有界 | typed sequence/mixed 限制明确，effort sequence 有本轮短程；未新增四任务任意组合，也未复活退休 fixture |
| R20 | 满足，有界 | typed 单位、限幅、gravity capability/default-off、outer interval 与 native substep 调度保全；不要求跨 solver 同轨迹 |
| R21 | 满足 | readback、评价、observation、Solution observe 和记录沿同 interval 生命周期；caller-owned observe 由 caller 完成 |
| R22 | 满足 | 配置/source/native 检查已区分；本次独立选择精确纯/fake 节点并启用 SDK/资产守卫 |
| R23 | 满足 | 所改测试针对真实 owner/行为，无为退休入口补回产品分支；不以测试总数作为架构接收 |
| R24 | 满足，有界 | 示例动作改用控制能力；Nut Solution 接受正式 schema 并拒绝非有限值；LIBERO 兼容 caller 保留。未声明完整训练/benchmark 回归 |
| R25 | 资料尚未完全收口 | 账本有按模块效果表和证据，但顶部规划状态及三个失效的实施记录索引须勘误，见第 5 节；不据此重开生产重构 |
| R26 | 满足 | 最终 MuJoCo 四任务、装配及 effort 六条原始路线，70 显式子步，二次 reset 与重复 close |
| R27 | 满足，有界 | 最终 GeoPhys effort/Pendulum 及 U1 Isaac 冻结证据按 diff 关联；未计数 native 子步/启动推进仍为 unknown |
| R28 | 满足，有界 | MuJoCo borrowed RGB 与 GeoPhys×MuJoCo RGB 的 reset/step/二次 reset 状态边界逐项相等；不推断 renderer 全交集 |
| R29 | 满足 | 文件与代码量可按既定分类复算；本次补完阶段生产净增 309 行，不虚报成本轮又净删数千行 |
| R30 | 独立主审完成，最终收口待文档修正及维护者 | 本报告补足代码/证据的独立判断；不能将 R25 的资料余项写成已完成，E05 以后及完整 Solution 留后续 |

## 4. 独立验证与证据边界

本次没有新运行物理、GPU、GUI 或任务资产解析；没有恢复/创建实施 Goal。使用 CodeGraph 定位，索引提示 drift 后读取实际磁盘源码。独立运行 **73 项纯/fake 检查，全通过**；SDK 导入与安装资产读取守卫的拦截数为 0，已加载 native 模块为空。这些检查支持合同逻辑，不冒充真实物理。

审查原始运行结果的独立脚本还核验：同一 episode 非零 interval、control_step 增一、二次 reset 新 episode、重复 close、source snapshot 释放、提交身份以及 RGB 与 physics 的同一 boundary。最终四份 U5 计划中声明的 source/probe/config 哈希均与当前文件一致；不能据此声称计划未列文件也由哈希覆盖。

| 原始证据 | 本次独立核对结果 |
| --- | --- |
| [最终 MuJoCo](../../../../../../workspace/maintenance/v211_u5_final_mujoco_20261112_001/plan.json) | 生产 `76536d2a`；Position、effort、装配、Nut 各 5 子步，Pendulum/双轮各 25，共 70；桌面 dt=0.01s，简单主体 dt=0.05s；六条正常闭环成立 |
| [GeoPhys](../../../../../../workspace/maintenance/v211_u5_geophys_20261112_001/plan.json) | 同生产 HEAD；Panda effort 和 Pendulum 各一个 interval，dt 分别 0.01s/0.05s；native 子步未独立计数 |
| [borrowed RGB](../../../../../../workspace/maintenance/v211_u5_renderer_20261112_001/plan.json)、[跨组合 RGB](../../../../../../workspace/maintenance/v211_u5_cross_rgb_20261112_001/plan.json) | reset/step/二次 reset 的 capture boundary 与 physics boundary 相等；前者 5 显式 MuJoCo 子步，后者 GeoPhys 子步 unknown；不据 unknown 宣称测得额外推进为零 |
| [U1 Isaac](../../../../../../workspace/maintenance/v211_u1_usd_shared_native_20261112_002/plan.json) | HEAD `253e1efe` 加冻结 dirty patch，非仅裸 HEAD；重算 patch/probe SHA，并在内存复原 patch，五个相关改动文件与后来 `a5483e63`/最终文件一致；Position/effort 各 5 显式 advances、二次 reset、重复 Env close、App close receipt |
| U2/U3 定向检查 | 源码核对 RNG/失败 owner 修复；读取 stale/action-failure/expert/typed 控制计划与 runner。真实部分写入、真实 camera/Isaac 失败注入未运行，仍按 fake 或未测报告 |

Isaac 冻结输入后，生产改动集中于共同 Env 的 RNG 预检失败回滚、失败 session owner 保留、兼容 Solution helper，以及示例/Nut schema。U1 Isaac 普通 Position/effort 成功路径未进入这些新增失败/兼容分支；USD/source/provider 实现相同，故成功路径可复用。它不能证明最终代码的 Isaac 失败处理已经真实注入。启动隐式推进 unknown 和历史 SDK shutdown 日志限制保留。

本次精确节点、守卫、Junit、原始结果复算及输入快照在 [独立审查输出](../../../../../../workspace/maintenance/v211_e00_e04_independent_review_20261112_001/input-snapshot.json)。首次审查 runner 的 `open` 包装参数与 Python 关键字冲突，在测试开始前退出，已修正并保留原日志；这不是生产失败。第一次原始结果复算误将复合 Controller identity 等同两个叶 identity，修正为按实际复合/叶层级、writer 和资源核对，未改运行结果或产品检查。

## 5. 可读性、度量和应保留的余项

**职责收敛成立，整体可读性是局部改善，不能写成 Task 层已经彻底精简。** 相对本次重评输入 `b94e8625`：

| 文件/范围 | 输入→最终 | 解释 |
| --- | --- | --- |
| PickCube specialization | 1196→1177 行；最大函数 156→128 行 | 大构造拆成 source、factory 参数、Task 结果绑定；仍有大量 provenance/readiness 及 profile/provider 配置接线 |
| Nut specialization | 537→561 行；最大函数 96→84 行 | 共用 Controller factory/执行包装，但元数据、Solution、guard 接线仍占较大篇幅；不能只凭函数变短声称总复杂度消失 |
| reference_binding | 575→608 行 | 共同 owner 新增阶段职责；有合理增量，也增加了阶段 callback 及私有字典字段的阅读成本 |
| reference_env | 4397→4391 行；reset 约 590 行 | 兼容提案去重和错误恢复修复成立；本轮不是大类整体拆分，也不以文件仍大作为自动返工依据 |
| 本次生产/诊断 | 生产 +996/−687，净 +309；诊断 +529/−23，净 +506 | 本轮是补闭环及验证；未再净删 9000 行 |

按实现者既定统计口径，`1f1359ee → 76536d2a`：blob 文件 1361→1364；加上两个 gitlink 则为 1363→1366。生产及其他 +5564/−15220，净 −9656；诊断 +4776/−0；文档 +882/−131，净 +751；合计 **−4129 行**，独立复算一致。分类为 `task_env/diagnostics/`、`docs/` 与 `task_env/doc/`、其余；因此 root README/AGENTS/Skill 计入“生产及其他”，这个桶不等于纯生产 Python。行数用 `git diff -M`，无 rename 的文件新增/删除数另算；一组 Robot binding 迁移不能冒充净删。`f52c158f → 76536d2a` 实际仅新增一个诊断文件，其余两份规划文档在 f52 已新增。

需要记录的余项：

1. **阶段结果依赖私有字典键。** `_robot/_scene/_controller_selection/_legacy` 在 Task、builder、adapter 间流转，部分 hook 使用 `pop`。当前交接与负例可追踪，未发现实际错配；以后触及相应模块时优先减少隐式字段/可变交接，不要求本轮再造一套 Builder 或强制新 schema。
2. **错误阶段字符串参与行为选择。** `_prepare_solution_action` 用 `proposal_phase == 'physical_external_solution_proposal'` 决定 strict type 检查及 action 投影。当前 caller 配对正确且独立检查通过；后续调整该 helper 时应让行为由明确能力/参数决定，错误标签只描述故障。此项为维护性意见，未据此发现当前功能故障。
3. **专用账本的现行状态需勘误。** 顶部仍写 `REPLAN_ONLY_IMPLEMENTATION_NOT_RESUMED`，第 1 节混有 b94 规划时点的“未运行”及事件待办，后文已是实施结果。应将前者明确标为历史输入，把顶部改成实施自评完成/独立主审建议接收/维护者待接收，并链接本报告；不能让恢复者再次把旧剩余当新工作。Skill 的旧 physical UID 翻译、source 编译次数等说法也须在后续文档同步时按当前 owner 校正。
4. **dirty 执行记录不能按一个跨时点的“原样保留”概括。** 本次观察它已是 Goal 文本，SHA `af50897d…`，较早 f52 规划快照中为执行记录且 SHA `d0a389ed…`。至少 U1 shared-source/USD 冻结 patch 已保存当前 Goal 文本，并与本次当前字节一致；现有材料不足以将中间编辑归责实施者或用户。本次不覆盖它、不丢弃旧 dirty patch。当前文档检查器实际报告 API、current-state、TaskEnv Skill 指向该文件 `#6-e00e04-实施记录` 的三处断链；这是恢复入口的真实缺口。接下来做文档收尾时先核对归属，将正式执行摘要和 Goal 的角色恢复清楚。四个 untracked 输入及两 pins 无此差异。

第 3/4 项是资料准确性与恢复入口的收尾，不能继续宣称文档全无余项；它们不否定已独立核对的生产闭环。建议一次完成文档勘误，再由维护者作 E00～E04 最终接收决定。E05/E06 的完整 source/provider、E07/E08 observation/render、E09～E12 全面 Task/Recorder/caller、E13 完整单 seed Solution、E14～E16 全量文档/证据/分支整理仍保留。不得以本报告自动启动后续事件或 G06。

## 6. 本次审查变更与保全

本次仅新增本独立主审文档；原始审查脚本/结果置 ignored workspace。未改生产、原专用账本、Goal、dirty 执行记录、保护输入、submodule pin 或历史证据。文档提交后的 HEAD 不冒充生产验证 HEAD。当前文档检查前后均为 5 项错误、96 项历史链接问题，没有本报告新增错误：其中三个实施记录锚点问题如上，其余是保护的 `MUJOCO_LOG.TXT` 与检查器旧保护哈希不同、历史 review 指向退休 Position 文件。不能为消除这两项而删除保护输入或复活退休实现。最终保护哈希、文档检查差异与提交身份记录在同一审查输出目录。
