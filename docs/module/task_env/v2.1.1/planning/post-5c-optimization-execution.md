# 5c 后代码与项目优化：执行安排

日期：2026-11-11。状态：`E00_E04_IMPLEMENTING`。维护者已直接要求本会话实施 E00～E04。当前事实见[唯一当前摘要](../maintenance/current-state.md)，范围与退出证据以[60 项优化台账](post-5c-code-project-optimization-diagnostic-ledger.md)为准；本文负责依赖、具体改动落点和实施包安排。

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

## 6. E00～E04 实施记录

本节按模块维护当前效果、限制和证据入口，不再逐批追加过程日志。此前逐批历史可从提交 `69f4380e` 的本文件第 6 节恢复；原始诊断与运行结果仍保存在对应的 ignored `workspace/maintenance/` 目录。历史证据只证明其自身输入和范围，不合并为当前代码的最终验收。继续逐事件对照[优化台账](post-5c-code-project-optimization-diagnostic-ledger.md)；G06／G07 未开始。

| 事件／模块 | 当前效果 | 尚需完成 |
| --- | --- | --- |
| E00 基线 | 5c 接收与优化输入 `1f1359ee`、保护文件和两个 submodule pin 已记录。 | 按实际 HEAD、工作树和证据继续对账；E00 基线不证明架构已接收。 |
| E01 入口与配置 | 四个正式任务使用 `make_env`、同一规范配置语义及默认值调用；mapping／YAML 对齐。Position candidate、两个 PickCube 旧物理 UID 及只服务历史诊断的 F04 Isaac Position 物化入口已退休；正式 PickCube USD 与普通 Robot effort 准入仍保留。 | 旧 component 路径仍有其他 caller；PickCube 正式物理构建仍调用 candidate 文件。Isaac 资产必须预装，自动生成／发行尚未完成。 |
| E02 Task／Robot／Controller | 四任务的已选 Robot 进入声明、source、Controller 和 live 绑定；一体／装配 Panda 与两个普通 Robot 的主体能力保留。普通 Robot 动作空间来自已编译 Controller；PickCube 的 MJCF Position／effort 共用 Task／Robot 场景编译和 source 绑定；Isaac Position／effort 使用同一 Task binding 工厂并分别绑定 Controller；MJCF／USD Panda effort 共用 source／Controller 组合，reset 增益及可切换类型由 Controller 校验和声明；普通 Robot 的 MJCF 传动检查和 USD 层级映射分别由 source 导入层与 Isaac adapter 负责。 | Panda 与普通 Robot 的 source 物化仍有不同路径；不能仅凭共同运行视图认定统一构造完成。Task 内剩余候选构建与具体 source 接线需按 owner 迁移。 |
| E03 Env／生命周期 | TaskDefinition 生命周期、reset 重建、部分故障处理和 source／Env 关闭已收敛到共同 owner；隔离 worker 在构造失败和关闭时也按同一顺序释放 session、Runtime owner、source 与 Task 资源，并在关闭响应中传递失败；Isaac App 在共同构造边界按 provider 准备，不依赖 Task UID 或由普通 Robot source 再次启动。 | 继续核对各受影响路径的构造失败、reset、fault、共享 App／renderer 及 close 所有权。 |
| E04 控制／推进 | 已受测的 action、Solution 单步和 Position／effort 均进入共同场景提交；保留 typed 命令、writer 资源、单位、boundary 和 clock。 | 按实际 caller 完成已支持 ExpertAction／序列及失败语义核对；完整 Solution、所有 provider／renderer 及任意组合均不能由短程结果推断。 |

### 6.1 累计文件与代码变化

以 `1f1359ee` 为比较基线、当前冻结代码输入为范围，`git diff --no-renames` 中 `task_env` 跟踪文件由 980 减至 979；整个项目跟踪文件由 1363 增至 1364。生产 Python 涉及 107 个文件，+4,887／−14,297，净减 9,410 行，其中新增 3、删除 15、修改 89；诊断新增 17 个文件，+3,826／−0；其他 `task_env` 文本（含文档及资产）修改 8、删除 6 个文件，+28／−917。按 Git 整文件重命名检测无整文件迁移，按职责拆分的代码不伪装为原样迁移。旧目录中本阶段的 12 个诊断文件修改已撤回到优化启动基线；仍有效的 adapter 准入检查在 v2.1.1 目录维护，旧诊断不再作为兼容目标。

这些是累计文本 diff，不是对实现质量或最终接收的证明；历史台账、原始输出、四个未跟踪保护输入和其他用户修改不计入新增／删除。项目其他目录的跟踪文件变化包含文档和示例。每个事件最终接收时仍需按目标表提供该事件的精确对账及 diff。

### 6.2 受影响路线和证据

- 最新冻结代码输入的版本诊断为 258 项通过，涵盖正式配置、Robot／Controller 绑定、资源故障边界和已验证 USD source 字节；它不等于原生运行或任务成功。
- 四任务及装配 Panda 的 MuJoCo CPU 短程路线曾在 [共同配置默认值输入](../../../../../workspace/maintenance/v211_task_defaults_20261112/plan.json)下完成 reset、非零 action 或 Nut 单个 Solution interval、共同提交、再次 reset 和重复关闭；代码身份不同于本批，按改动影响参考。
- PickCube 的 MuJoCo 直接 effort、关节参考和 R3 参考以及 Isaac CUDA 关节参考曾在 [共同 source／Controller 组合输入](../../../../../workspace/maintenance/v211_shared_effort_builder_20261112/plan.json)下完成短程运行。每条观测 5 个显式子步；这不是完整 Solution 或全部 provider 的结论。
- 此前冻结输入的 PickCube Position 与关节 effort 的 Isaac CUDA 运行、预算和原始结果见 [USD source 验证计划](../../../../../workspace/maintenance/v211_pickcube_usd_source_20261112/plan.json)。两次均完成 reset、5 个显式子步、再次 reset、重复 Env close 和 App close 收据；关节 effort 路线的 SDK 关闭日志另有 Isaac 菜单回调访问空 USD context 的 `AttributeError`，因此不能称整个 SDK 关闭过程无异常。App 隐式启动推进数未知。
- Pendulum／双轮车的 MJCF 传动检查及 USD 层级映射归位后，MuJoCo CPU 与 Isaac CUDA 的正式短程验证分别见 [CPU 计划](../../../../../workspace/maintenance/v211_effort_source_lowering_20261112/plan.json)和 [Isaac 计划](../../../../../workspace/maintenance/v211_effort_source_lowering_20261112/isaac-plan.json)。四条路线各完成 25 个显式子步、再次 reset 和重复 Env close，Isaac App close 收据均完成；Pendulum 的 SDK 关闭日志另有菜单回调空 USD context `AttributeError`，不能据收据称整个关闭过程无异常。各项不扩展为完整任务成功。
- PickCube 与 NutAssembly 在 MuJoCo CPU 隔离 worker 下完成 reset、单个控制 interval、再次 reset 和重复关闭，见 [worker 资源验证](../../../../../workspace/maintenance/v211_worker_resource_lifecycle_20261112/plan.json)。Nut 为一个 Solution interval；worker 子步没有独立实测，按每条 50 子步保守计费。故障注入另核对构造失败、session 已物化后失败和关闭响应中的资源释放，并验证原异常及清理失败附注跨 worker 传递；原生短程输入之后仅增加错误序列化代码及其诊断，正常运行路径未变。
- Isaac App 统一准备后，Pendulum 和双轮车的进程内 CUDA 路线复验见 [App owner 计划](../../../../../workspace/maintenance/v211_isaac_app_owner_20261112/plan.json)；两条路线各完成 25 个显式子步、再次 reset、重复 Env close 和 App close；本次日志未出现此前记录的菜单回调异常。worker 在不同 Task 选择下的启动及失败清理由版本诊断覆盖，未作 Isaac 隔离 worker 原生复验；不表示 physical execution 已支持隔离 worker。
- 退休 F04 独立准入后，PickCube 的 MuJoCo、Isaac Position／effort 和 Pendulum 的 Isaac effort 复验见 [CPU 计划](../../../../../workspace/maintenance/v211_retire_f04_route_20261112/cpu-plan.json)与 [Isaac 计划](../../../../../workspace/maintenance/v211_retire_f04_route_20261112/isaac-plan.json)。三条 PickCube 路线各完成 5 个显式子步，Pendulum 完成 25 个；三条 Isaac 路线均完成第二次 reset、重复 Env close 和 App close，日志未见 traceback 或 `[Error]`，隐式启动推进数未知。F04 历史结果仍按原时点保留，不转化为现行能力。
- MJCF Task／Robot 场景合并后的 PickCube R3 Position、直接 effort 与关节 effort 见[本批 MuJoCo 计划](../../../../../workspace/maintenance/v211_shared_pickcube_task_scene_20261112/plan.json)：均完成 reset、5 个显式子步、第二次 reset 和重复 close；正式构建检查另确认 Position／effort 的 Task Artifact、场景与实体映射一致。本批未重跑 Isaac 或 GeoPhys；改变的共享场景步骤仅用于 MJCF 输入。
- Isaac 共同 Task binding 改动后的 Position 与关节 effort 实际路线见[本批计划](../../../../../workspace/maintenance/v211_shared_usd_task_binding_20261112/plan.json)：均完成 reset、5 个显式子步、再次 reset、重复 Env close 和 App close；Position 的 SDK 关闭日志出现两次菜单回调访问空 USD context 的 `AttributeError`，effort 日志未见 traceback 或 `[Error]`。App 隐式启动推进数未知。
- Panda effort 的 reset 增益校验与可切换类型归 Controller owner 后，[本批 MuJoCo 验证](../../../../../workspace/maintenance/v211_controller_reset_owner_20261112/plan.json)以 `kp=80` 重置关节 effort、记录并执行一个 interval，再切换 R3 effort 并执行一个 interval，共 10 个显式子步；直接 effort 另完成 5 个。无效增益的拒绝和不提交选择由版本诊断检查。
- 5c 已接收的原生渲染及跨组合证据保留原有有界结论；本次未重新验证 renderer。完整 Solution 的单 seed 和记录读回留待 E13，G07 三 seed 矩阵不属于本次实现范围。

### 6.3 USD source 与资产边界

PickCube 的 USD 构造使用已验证的 `UsdTaskSceneSourceV1` 原始 source 字节，不再重复加载交付并自行从路径读取 MJCF；source owner 在 Controller 绑定前仍检查所有受验证字节的新鲜度。诊断验证三种 Controller 配置共用同一加载结果，并在原始 source 变更后拒绝。先前新增的本地 USD 缓存仍需预装，未变为资产发行方案。各项运行证据按其实际代码输入分别标记。
