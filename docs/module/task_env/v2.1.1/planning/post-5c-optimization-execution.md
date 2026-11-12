# 5c 后代码与项目优化：执行安排

日期：2026-11-12。E00～E04 已完成实施、独立主审及后续余项修复，维护者已在本次对话统一接收。当前效果见第 6 节及[专用账本](post-5c-e00-e04-remaining-ledger.md)。第 1～5 节保留 2026-11-11 的历史启动安排，不作为新的剩余工作或实时状态。

## 1. 启动边界

复用 `codex/v211-stage5-diagnostic`，输入 HEAD `1f1359eef9bfff73cf7688a8270c5f06471dc614`、生产 `a53bf19d`，两个 pins 不变。启动 tracked clean；四个既有 untracked 输入按[输入快照](../../../../../workspace/maintenance/v211_post5c_optimization_o0_20261111_001/input-snapshot.json)保护。最新单元 9 已返包并释放，本轮未派发实施 agent、未运行 native／GPU／GUI／任务资产解析，尚未消耗 O1 实施 attempt。

O0 启动窗口交付是基线与导航纠偏：记录维护者功能接收和优化启动、统一当前状态入口、校正旧现行说明、定位首个代码包。代码优化与项目优化的接收仍为 PENDING。原台账 60 项包含问题、待核和保全项，不按“60 个 bug”实施。

## 2. 依赖及逐项归属

以下顺序沿用台账 O0～O8，不增加版本阶段或第 23 个子阶段。跨包条目在最后一项所需证据到齐后结案；静态实现完成不能提前替代 native／完整 Solution 结论。

| 顺序 | 具体 owner／落点 | 台账归属与交付 | 状态 |
| --- | --- | --- | --- |
| O0 | 当前摘要、现行导航、orchestration | GOV-03／04、DOC-01／02 的启动部分；接收范围、输入与后续依赖清楚 | 基线已记录；全条目未结案 |
| O1 | `registry.make_env`、`configuration.resolve_task_env_config/resolve_execution_plan`、`ResolvedEnvConfig/ResolvedSelectedConfig`、Task binding、Robot recipe | ENTRY-01～03；GOV-01／02；TASK-01／02、SUBJ-01～03、SRC-01／02 的构建部分：一个正式请求及旧 caller 迁移 | 实施中；见第 6 节及当前摘要 |
| O2 | `SelectedReferenceEnv`、`ReferenceTaskBinding`、`selected_materialization`、`state_initialization`、Controller binding／`submit_control_command` | ENV-01～05、CTRL-01～05，TASK-04／SUBJ-01～03：共同 reset／控制／状态／close owner 及能力保全 | 实施中；见第 6 节及当前摘要 |
| O3 | assembly/source composition、provider admission／worker、render registry／camera adapters、observations | SRC-01～04、RUN-01～04、REN-01～08、OBS-01／02；TASK-01～04 剩余职责：实际 source／native／视觉适配归位 | 待相应 O1／O2 输入 |
| O4 | Nut Solution／feedback 支持、Recorder／reader／replay、CLI／examples／vector／LIBERO caller、diagnostics | TASK-03、REC-01～03、CALL-01～04、TEST-01～04；逐个 caller 迁移，通用格式与实验 oracle 分层 | 待相应上游 owner |
| O5 | 最终生产入口和原始记录、独立 reader | V01～V09；按影响复用／最短补测，完整 Solution 与真实任务结果分列 | 待代码稳定及 native 执行包 |
| O6 | 全台账逐项记录、API／指南／能力矩阵／Skills、独立主审 | GOV-01～04、DOC-01／02、V10 代码／文档部分；60 项逐项 PASS 或维护者同意的 NOT_APPLICABLE，代码优化人工接收 | 待 O5 |
| O7 | stage 最终成功证据／核心诊断、生成物、refs／worktrees | PROJ-01～04、BRANCH-01；先独立复算归并包和保全独有成果，再按清单处置 | 待 O6 人工接收且无活动 writer／lease |
| O8 | 最终文档、例子、refs、依赖路径及证据恢复检查 | V10 最终部分；项目优化独立接收，再决定进入 G06 | 待 O7 |

O1～O4 是依赖顺序，不要求每包先耗一轮审计。已有 owner 清楚时，实施、定向验证、必要修复、兼容更新、报告与本地提交同包完成。没有实际缺陷的保全／待核项以 caller 和 diff 核对结案，不制造新抽象。后续完整 Solution 若已覆盖同一路径，复用其结果，避免额外 smoke run。

## 3. O1 首包：正式配置与构建合同（启动时记录）

### 3.1 已核实的当前调用链

启动时先查询现有 CodeGraph；它对 configuration／Task binding 等文件报告索引 drift，因此本次直接核对了这些文件的磁盘源码，没有刷新索引。

| 入口／方法 | 当前事实 | 修改接收方和目标 |
| --- | --- | --- |
| `registry.make_env` | `uses_selected_public_config`、`from_reference_config` 覆盖反射、component fallback 三种构建协议；`factory_owns_rgb` 决定 camera 准备时机 | registry 只选择任务并提交一次已解析构建请求；旧 factory 的输入转换显式登记，不复制状态机 |
| `_resolve_selected_config`／`ResolvedSelectedConfig.__post_init__` | 正式 selected 配置仍严格限定 state-only renderer；`robot` 仅 `{uid}`，`controller` 仅 gravity flag，profile 位于 task；component robot 是另一种形状 | 原 configuration/config owner 规范化字段、优先级和旧输入；renderer 能力约束交既有 adapter，不能只删拒绝条件 |
| `PickCubeReferenceEnv.from_resolved_config` | 再次解析已解析值，拒绝 render_mode／kwargs；Isaac 初始化仍在 Task 内调用 builder | 正式 Task 薄绑定提交任务声明／默认选择；共同构造 owner 消费 resolved 值，原能力预检与失败清理保留 |
| `PickCubePhysicalCandidateEnv.from_reference_config/_build_candidate` | 独立解析 provider／drive／controller／workspace／camera 并编排构建 | 按段迁往现有 Robot、Controller、source／runtime、renderer owner；旧 UID 最终只适配输入或经明确决定退休 |
| `PickCubeIsaacPhysicalCandidateEnv.from_reference_config` | Task factory 直接开 App，再设置 physical binding／相机与清理 | App lease、launch profile 和相机准备交 session／renderer owner；F06 source admission 保留精确边界 |
| `PendulumEnv/TwoWheelBalanceEnv.from_reference_config` | selected physical 与 `build_runtime=False` component 纯构建并存，provider／backend 参数与 resolved runtime 分别传递 | 共同请求明确 live／pure build 能力；保留纯构建及 batch caller，避免强制启动标量 Runtime |
| `PickCubeReferenceEnv.selected_binding` | 已消费 Robot recipe 和 source composition intent，但还按任务组织 adapter 请求 | Task 保留 cube／table 映射，Robot 保留本体 recipe，provider composer 消费共同 request；和 O3 配套完成，不整体搬 specialization |

### 3.2 实施内容与边界

首包按 `EXTEND_EXISTING + COMPOSE_EXISTING` 处理，主 owner 为 `environment/configuration.py`、`environment/config.py` 和现有 registry／binding；不新建 UnifiedEnv、Manager 或平行 factory。准确签名由实施者在这些 owner 内落实并在报告列出，字段语义和迁移要求如下：

1. 将 Task 参数、Robot／Controller 选择、physics 执行、renderer／camera 声明各归其 owner；覆盖顺序保持 Core → Task class → Task YAML → caller。同义旧字段单向规范化，冲突／未知字段继续拒绝；旧身份格式不被静默重解释。
2. mapping／YAML 在正式 `make_env` 得到同一有效选择；预解析配置保留身份、任务匹配和篡改检查。Task 不再通过加类标志改变 native／camera 准备时机。
3. 形成明确的构建请求及正式 caller 链：Task 声明／Robot recipe／Controller capability → 既有 Runtime builder 和 renderer factory。renderer 更换通过配置和 adapter 完成；实际 source／设备限制仍由相应能力拒绝。
4. 相机普通声明在 Artifact 编译后由既有 camera owner 绑定，用户无需先提供内部 hash；高级已绑定 `CameraGeometry` 的 Artifact／source／episode 校验保留。O3 接通实际相机前不能把声明解析通过说成 RGB 已通过。
5. 为两个 PickCube candidate UID、selected 正式 UID、两个简单主体的 `from_reference_config`、component `build_runtime=False` 登记逐个迁移结果。先迁真实 caller，再删重复实现；禁止兼容桥拥有第二套 reset／step／close，也不能仅把原文件搬到新目录。
6. 本包覆盖的实际正式构造必须消费新解析结果；若某条依赖后续 O2／O3，明确留在原能力合同并列出剩余接线，不用未调用 schema 领取整条 ENTRY／TASK 的 PASS。

保全重点：Panda R1／R3／Position 与 effort 的差异、±2 N·m Pendulum／±1.5 N·m 双轮通道、两指传动、现有 source closure／admission、固定 renderer、纯导入和纯构建、静态拒绝无 native 副作用。未扩展已支持 provider／source 的交集。

### 3.3 检查选择与证据

先迁实际生产链，再选以下已存在的精确纯检查节点；实施者核对 fixture／导入守卫并冻结实际命令，不能运行整个旧模块冒充纯检查：

```text
task_env/diagnostics/tasks/test_selected_api_configuration_and_identity.py::test_selected_execution_defaults_follow_core_class_yaml_and_caller_order
task_env/diagnostics/tasks/test_selected_api_configuration_and_identity.py::test_selected_execution_is_strict_and_rejects_inherited_device_conflicts
task_env/diagnostics/tasks/test_selected_api_configuration_and_identity.py::test_selected_task_yaml_uses_duplicate_key_rejecting_loader
task_env/diagnostics/tasks/test_selected_api_configuration_and_identity.py::test_layered_selected_route_resolves_without_native_build
task_env/diagnostics/tasks/test_selected_api_configuration_and_identity.py::test_public_factory_consumes_same_layered_selected_resolution
task_env/diagnostics/tasks/test_selected_api_configuration_and_identity.py::test_public_static_rejection_has_stable_json_receipt_and_no_binding
```

它们分别保护覆盖顺序、冲突、YAML、无 native 解析、公开 factory 实际消费和静态失败回执；不能证明真实物理或 RGB。补充检查只针对迁移新增的实质风险：YAML/mapping 同义、旧 UID 到同链、纯构建、相机延迟绑定与错 Artifact 拒绝；保留旧格式严格 oracle，迁移仅依赖旧私有布局的测试。

真实检查与复用映射按 V01～V10：V02 四主体；V03 typed 命令／资源组合；V04～V06 原生 borrowed、cross independent、三原生及图像生命周期；V07 受影响错误／旧入口；V08 两任务完整 Solution；V09 同次记录独立读回；V10 文档和最终项目恢复。哪些旧运行不受影响须列原身份、相关 diff 与 owner，不能仅以 HEAD 不同全盘作废或以共同类名自动继承。

### 3.4 派发前必须冻结

本页是已定位 owner 的首包安排，**尚未派发，也不是新的 native／删除／集成授权**。按仓库单 writer、单包工作流，由实际指定的实施者取得完整包后执行，不自动创建或消息其他 chat。派发前记录：

- 本次启动文档提交后的真实 HEAD／dirty owner、保护输入与 prompt／snapshot SHA、实施者及唯一输出目录；不预造输出 HEAD。
- 具体允许修改文件／方法和上述检查节点，公共字段表及旧 UID 迁移表；允许包内必要修复与本地提交。
- 实施、验证、修复和返包合计的主动时间、硬墙时、RAM／VRAM／磁盘及独占资源预算；不能拿旧 stage 窗口直接复用。
- native 若纳入本包，须逐条冻结正式命令、source delivery、physics／renderer、seed／horizon／dt、物理步及采集上界、现行双锁和失败清理；若仅纯代码包，native 为 0，物理结论留 O5。
- 完整 Solution 优先使用已有成功参考 PickCube seed31、Nut seed19；O5 包固定每任务单 seed 及各自公开支持路线。Nut 当前正式 selected 明确不支持 Isaac，不用 candidate／mock 填表，也不擅自把未支持格增为本次必达。

完整返包和 writer／native 释放后审查实际 diff、caller、原始结果与独立 reader。实施者自评、独立主审和维护者接收分列。第一包可以在原窗口内修复并重测，不按单次测试／启动次数消耗 attempt。

## 4. 最终退出

原台账每项使用其 18.1 表格结案，记录原问题现状、最终 owner／符号、变更或保全理由、真实 caller／命令／复用依据、结论与主审。不得用本页 O0 文档同步关闭 GOV／DOC 全项。

最终分别回答 G05 功能是否接收、代码优化是否接收、项目优化是否接收。O7 必须先保全独有提交、最终原始证据和必要 source 闭包，从归并包复算并解除旧 worktree 路径依赖，再按明确清单处置；保护输入、frozen tags 和无关资产／全局缓存不变。未完成项目接收不启动 G06；本次不自动 merge／push／发布。

## 5. 本次启动检查

本轮按仓库 `geochora`、架构／公共 API／测试治理及文档治理 Skill 核对实际 caller、规划和当前导航；启动修改限文档／JSON／Skill，不改变生产 Python、资产、pins 或历史主审结果。

- 维护者提供的启动 HEAD、分支、两个 pins、tracked clean 及四个 untracked 输入已与实际 Git／字节核对，快照在本页第 1 节。
- 文档检查器在修改前后分别运行 `python -B .agents/skills/geochora-doc-governance/scripts/validate_docs.py --mode current`。两次均仅报原有 `protected local input changed: MUJOCO_LOG.TXT`，96 项历史链接问题一致；不改保护原件或检查器基准，不报告全库检查全绿。
- 版本 JSON 可解析，七阶段仍为 22 个唯一子阶段；原普通 attempt 记录保留，G06／G07 均为 PLANNED／attempt0，5c 旧阻塞及预算移入明确的历史字段。
- 台账仍为 60 个唯一条目；四个保护输入的 SHA-256 与启动快照一致，生成数据继续 ignored。
- 本轮没有运行 pytest、native、GPU、GUI、任务 source 解析或完整 Solution；没有据此新增物理能力结论。O1 实施包与 O5 native 范围仍需按第 3.4 节冻结。

检查日志和[摘要](../../../../../workspace/maintenance/v211_post5c_optimization_o0_20261111_001/validation-summary.json)保存在本轮 ignored 输出目录；本地提交按当前阶段分支归属，仅包含本轮文档。后续实施前重新核对其实际输出 HEAD 与 dirty 归属。

<a id="6-e00e04-实施记录"></a>
## 6. E00～E04 实施记录

当前以[专用账本](post-5c-e00-e04-remaining-ledger.md)和[独立主审](../maintenance/reviews/20261112_e00_e04_independent_review_76536d2a.md)对照；后者审查生产 `76536d2a`，建议有界接收并指出四项代码/资料余项。本轮维护者授权这些余项的一轮实施测试，现已完成，生产提交 `912416e6`，详见[实施返包](../maintenance/20261112_e00_e04_review_fix_delivery_912416e6.md)。维护者现已统一接收 E00～E04；原主审及后续自检的身份/证据边界保留。E05～E10 仅完成专用规划，G06 未启动。

| 事件 | 最终效果及本轮补充 | 仍保留的边界 |
| --- | --- | --- |
| E00 基线与度量 | 实际输入 `e25f37c5`、原 dirty、四保护输入和 pins 冻结；生产、诊断、文档分开计量 | 代码身份、原始证据和文档提交身份分别记录；不以行数推导质量 |
| E01 正式入口与配置 | 四任务共用 `make_env`、规范配置、Robot 选择和 `TaskBuildRequest`；旧 Position candidate 和 PickCube physical UID 已退休 | 范围外 component 有独立 caller；Isaac 需要预装资产 |
| E02 构造与主体 | 共同 builder 复用 `CompiledReferenceTaskV1`，各任务使用不可变具名 context；source composition 返回具名结果，Controller 选择单独传给最终绑定，不再在 Runtime value 填充/弹出临时键 | 保留 MJCF/USD、Position/effort、单层/嵌套的合法差异；不承诺任意组合 |
| E03 生命周期 | 共同 reset、source cache/lease、publication、worker/App/camera 清理保全；RNG 预检回滚和失败 Runtime owner 保留的修复继续有效 | fake 失败检查不升级为真实 SDK 失败注入；资源/关闭日志限制保留 |
| E04 控制与推进 | 标准外部 `act → env.step → observe` 保留；兼容 helper 由显式投影与类型策略决定行为，错误阶段只负责 fault 标签，进入原共同提交和推进 owner | typed 单位/资源/clock/generation 检查不弱化；完整 Solution 留 E13 |

### 6.1 本轮验证与影响

精确计划和结果见[本轮冻结输入](../../../../../workspace/maintenance/v211_e00_e04_review_fixes_20261112_001/input-snapshot.json)、[受影响 source/caller 检查](../../../../../workspace/maintenance/v211_e00_e04_review_fixes_20261112_001/source-contract-plan.json)、[USD 离线检查](../../../../../workspace/maintenance/v211_e00_e04_review_fixes_20261112_001/usd-source-plan.json)和[CPU 短程计划](../../../../../workspace/maintenance/v211_e00_e04_review_fixes_20261112_001/native-plan.json)。217 项受影响检查通过，76 项纯/fake 精确检查通过（有重叠，不相加）。MuJoCo 七条短程 75 显式子步，测试另 40，合计 115；GeoPhys 两条短程通过，native 子步未独立计数。首轮六项 USD 因守卫误拦 OpenUSD 失败，放开离线 OpenUSD 后只补六项，全部通过，首轮记录保留。

验证输入为 `e25f37c5` 加保存的生产 patch，逐文件 SHA 与 `912416e6` 生产/诊断字节一致；运行的 source_revision 仍是 e25，不写成提交后裸 HEAD 重跑。本轮修改 5 个生产文件，+208/−143，净 +65；修改 2 个版本诊断文件，+35/−9，净 +26。没有新增/删除/整文件迁移生产文件；具名阶段 context 和显式提案策略是新增代码的职责。文档/Skill 的变更及项目文件数另见返包，不与原累计净减少相加冒充本轮成果。

共同 builder 的内部交接发生变化，需复验四任务、装配 Panda 和受影响 Solution caller。USD 使用真实 delivery 的离线 source/Controller 检查；本轮没有启动 Isaac App/GPU。renderer adapter、状态/RGB publication、physics clock 与资源合同未改；此前 `76536d2a` 的两条 RGB 有界证据按接口及 source 对照复用，不改称本轮重跑。完整 Solution、全部 provider/renderer 交集和真实 SDK 失败注入仍未由本轮证明。

### 6.2 资料保全与恢复

修改前 dirty 文件是与 Goal 相同角色的提示文本，SHA `af50897d…`；本轮先按完整字节保存为[执行记录修改前副本](../../../../../workspace/maintenance/v211_e00_e04_review_fixes_20261112_001/execution-record-before.md)及[原 dirty patch](../../../../../workspace/maintenance/v211_e00_e04_review_fixes_20261112_001/existing-dirty.patch)，再从 Git 中恢复本页执行计划角色并更新第 6 节。独立的 [Goal 文件](post-5c-e00-e04-goal.md)保留。不是将旧 dirty 静默丢弃，也不将跨时点的不同文本写成从未变化。

旧执行摘要可从 `b94e8625`、`3b5023e8` 的相应记录/账本恢复，更早逐批记录见 `69f4380e`。初始 `1f1359ee → 76536d2a` 的累计统计及 U1～U5 原始 native/失败记录保留在专用账本，不与本轮增量混算。COM 历史失败、R05c NOT_REQUALIFIED、Isaac shutdown 日志及未计数启动推进限制保留；本轮没有整理 refs、worktree 或原始证据。

## 7. E05～E10 后续规划

维护者统一接收 E00～E04 后，下一范围为 E05～E10。使用[专用剩余账本](post-5c-e05-e10-remaining-ledger.md)及[实施 Goal](post-5c-e05-e10-goal.md)，按 U1 source → U2 provider → U3 状态/相机 → U4 renderer → U5 Task → U6 Recorder/replay → U7 定向复验与对账推进。一次完整结束大单元后才对照总账相应条目；不再逐函数反复重评全部范围。

本次核查输入 `67cb643f`、生产 `912416e6`，tracked clean、四保护输入和 pins 保全。仅静态核查、规划及直接状态索引同步，E05～E10 尚未实施，未运行 pytest/native/资产解析。完整 Solution 和完整同次记录读回仍归 E13；本次不清理输出、refs/worktree，不启动 G06。
