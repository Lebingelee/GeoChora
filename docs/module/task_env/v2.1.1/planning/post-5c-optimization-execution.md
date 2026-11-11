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
| O1 | `registry.make_env`、`configuration.resolve_task_env_config/resolve_execution_plan`、`ResolvedEnvConfig/ResolvedSelectedConfig`、Task binding、Robot recipe | ENTRY-01～03；GOV-01／02；TASK-01／02、SUBJ-01～03、SRC-01／02 的构建部分：一个正式请求及旧 caller 迁移 | NEXT，未实施 |
| O2 | `SelectedReferenceEnv`、`ReferenceTaskBinding`、`selected_materialization`、`state_initialization`、Controller binding／`submit_control_command` | ENV-01～05、CTRL-01～05，TASK-04／SUBJ-01～03：共同 reset／控制／状态／close owner 及能力保全 | 待 O1 |
| O3 | assembly/source composition、provider admission／worker、render registry／camera adapters、observations | SRC-01～04、RUN-01～04、REN-01～08、OBS-01／02；TASK-01～04 剩余职责：实际 source／native／视觉适配归位 | 待相应 O1／O2 输入 |
| O4 | Nut Solution／feedback 支持、Recorder／reader／replay、CLI／examples／vector／LIBERO caller、diagnostics | TASK-03、REC-01～03、CALL-01～04、TEST-01～04；逐个 caller 迁移，通用格式与实验 oracle 分层 | 待相应上游 owner |
| O5 | 最终生产入口和原始记录、独立 reader | V01～V09；按影响复用／最短补测，完整 Solution 与真实任务结果分列 | 待代码稳定及 native 执行包 |
| O6 | 全台账逐项记录、API／指南／能力矩阵／Skills、独立主审 | GOV-01～04、DOC-01／02、V10 代码／文档部分；60 项逐项 PASS 或维护者同意的 NOT_APPLICABLE，代码优化人工接收 | 待 O5 |
| O7 | stage 最终成功证据／核心诊断、生成物、refs／worktrees | PROJ-01～04、BRANCH-01；先独立复算归并包和保全独有成果，再按清单处置 | 待 O6 人工接收且无活动 writer／lease |
| O8 | 最终文档、例子、refs、依赖路径及证据恢复检查 | V10 最终部分；项目优化独立接收，再决定进入 G06 | 待 O7 |

O1～O4 是依赖顺序，不要求每包先耗一轮审计。已有 owner 清楚时，实施、定向验证、必要修复、兼容更新、报告与本地提交同包完成。没有实际缺陷的保全／待核项以 caller 和 diff 核对结案，不制造新抽象。后续完整 Solution 若已覆盖同一路径，复用其结果，避免额外 smoke run。

## 3. O1 首包：正式配置与构建合同

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

维护者在启动提交 `21577d32` 后直接要求本会话实施 E00～E04，并要求文件／代码净变化、统一构建、职责可读性、adapter 对齐及功能保全六类成效。继续同一阶段分支、当前 chat 单 writer，不派发其他 agent；发布、refs／worktree 整理及 E05～E16 不在本轮实现目标内。第 3.4 节原派包准备要求保留为其他执行者接手规范；本次直接实施的输入、纯检查和限定 CPU 实测已单独冻结，不沿用旧 native 窗口。

| 事件 | 当前状态 | 实际变化／剩余条件 |
| --- | --- | --- |
| E00 | 基线与度量已记录 | 输入 `21577d32`，四保护输入、两个 pins、tracked 原始文件／行数快照；原 O0 启动成果保留 |
| E01 | 实施中 | 正式 caller 共用构造、Controller selector 在两 codec 前归一化、registry 不再反射判断工厂；两 codec 与 Position 输入仍待对账，见 6.5～6.8 |
| E02 | 实施中 | 四主体共用 Robot 视图，正式 PickCube／Nut／Pendulum／双轮车共用 TaskDefinition lifecycle；其余主体和 registry 合同仍待审计，见 6.4～6.8 |
| E03 | 实施中 | reset／Solution reset 共用收尾与 close 资源回收，Isaac 正式配置及 MuJoCo／GeoPhys 隔离 worker 已复验；其余 reset／profile／fault 待审计 |
| E04 | 实施中 | 共同提交与 source／state／clock 对齐；正式 Isaac RGB、MuJoCo／GeoPhys 隔离 worker 已定向复验；其余动作／模型／renderer 组合待核，见 6.5～6.6 |

本次先修复 E01／E02 后续迁移会复用的 reset／close／submit 共同 owner，事件接收依赖未改变；不提前关闭 E03／E04 或整个目标。

首批量化结果：生产 Python 3 文件修改，增加 126 行、删除 225 行，净减 99 行；生产文件数不变。`reference_env.py` 从 5,098 行到 4,982 行，close 方法从 190 行到 96 行。4 个测试文件增加 137 行、删除 8 行，净增 129 行；没有新增生产／测试文件。adapter admission 的职责迁移经过重写，不计为原样跨文件搬运；测试／诊断／文档分开统计，后续按累计 diff 更新，不能把这次数字当最终全范围结果。

验证记录：

- 先在原行为下复现 mixed Solution 缺共同分派及未 reset Position 自有 source／Task 未关闭，再完成修复；原行为对照仅通过进程内加载旧方法验证合同，不是旧版本的第二次物理测量。
- 精确选择的 40 项纯合同通过，覆盖两种 reset 入口提交后采图、mixed／canonical Solution 分派、部分失败／主异常保留、资源清理、adapter 选择和旧 Task key 不能越权准入；不把 fake 合同当物理证明。
- 在现行双锁下以 MuJoCo 3.8.1 CPU 实测：正式 PickCube R3、同路线开启既有重力补偿、Pendulum、双轮车，各构造 → reset → 一个非零 step → 二次 reset → 重复 close 通过；装配 Panda `r1_split` 构造后未 reset 即 close 的真实 source 快照已释放。累计观测 60 个原生子步、无 GPU／GUI；单次脚本 180s、累计 native 900s／2,000 子步的预留未用尽，没有历史预算转移。
- 原始结果由独立标准库 reader 核对同次 boundary／clock／计数／关闭一致性；不是第二次物理测量，不代表完整 Solution、任务成功、原生 RGB 或全 provider 矩阵通过。
- GeoPhys／Isaac adapter、控制 lowerer、scene interval、时钟算法和既有 source 字节未改；其旧成果只能按原身份与后续 diff 对账复用，本次不宣称其 native 重跑。

输入、脚本、失败与成功原始结果、[独立读回](../../../../../workspace/maintenance/v211_post5c_e00_e04_20261111_001/cpu-independent-readback.json)及[首批度量](../../../../../workspace/maintenance/v211_post5c_e00_e04_20261111_001/implementation-metrics-001.json)在 ignored `v211_post5c_e00_e04_20261111_001` 包。后续继续 E01／E02 及 E03／E04 剩余职责，完整目标保持未完成。

### 6.1 第二批：正式构造与声明主体

输入 `c4ce6df3`，继续同一实施窗口、同一分支和单 writer。完成以下真实 caller 迁移，尚未完成 E00～E04 全部退出条件：

- 正式 PickCube、NutAssembly、Pendulum、双轮车通过 `make_env → resolve_task_env_config → SelectedReferenceEnv.from_resolved_config → selected_binding → reconstruction.initial → 同一 Env 构造`。PickCube 的重复 Env factory 已删除；两个简单任务的 factory、reset、observation 和录制元数据 override 已删除，任务现在声明 source、采样、具名状态投影和 TaskDefinition。`build_runtime=False` 与 Empty 的组件合同继续走明确的兼容构造，未据此声称 G06 native batch。
- 统一支持 `controller.profile_id`，再解码到保留的配置值类型；旧 `task.controller_profile`／`control.profile_id` 保留，冲突拒绝。已有两种 resolved 配置数据类型、provider kwargs 与 execution overlay 差别尚未归并；Nut 不支持的 profile 仍拒绝。
- `env.robot` 在四条 MuJoCo CPU 主体路线暴露同一 `RobotRuntime` 视图，引用实际已准入 subjects／controllers／root Frames。装配 Panda 保留两个 subject 和两个独立 Controller；不创建新 Controller、Runtime、native 资源或可变状态副本，也不为简单主体制造 gripper／ee。旧组件 Panda 的便利字段继续存在；selected 视图中未声明的便利字段为 None。
- Position compiler 的受控主体保留在现有 `PositionSubjectControlBindingV1`，由原 subject identity 校验，内部两个实际 compiler caller 已迁移至三值结果；旧 binding identity payload 不变。Env 在 reset 重新绑定时更新视图，不保留旧 Controller 副本。
- 两个简单 TaskDefinition 使用现有 `TaskLifecycleAdapter`；Gym 随机流、reset transaction 和结果格式化由 Env 统一拥有。重复 camera lowering 合并到 `CameraGeometry.from_camera_spec`；相机回执读取本次 Runtime publication 的 boundary／clock，reset 提交后和 step 共用 capture，并报告对应 renderer backend。

本批文件／行数口径是 Git tracked Python 文本行，含空行：生产 16 个修改文件，+440／−467，净 -27 行；测试 3 个修改文件，+178／−1，净 +177 行。从 `21577d32` 累计生产 18 个修改文件，+563／−689，净 -126 行。项目 tracked 路径 1,365→1,365（计 submodule gitlink、不递归子模块）；新增／删除／文件迁移均 0，项目文件净变化 0。没有用文件迁移冒充删除；职责归并经过重写，原样保留的 subject identity 字段投影 7 行只在同文件调整位置。生产、测试和文档的逐文件 numstat 分列于 ignored 度量记录。

`reference_env.py` 本批承担共同构造／TaskDefinition 与 capture 编排，因此从 4,982 行增长至5,144 行（比原始 5,098 行多 46 行）；累计项目生产代码仍减少。不能用净行数推断性能提升，也不宣称 Env 已完成全部职责清理。

验证与复用：

- 当前有 124 个不同的定向纯合同节点通过（122 项组合检查，加新增的 foreign Task identity 拒绝与旧 class binding caller 两节点；最后 8 项及 4 项复核覆盖新增身份检查、有效构造和旧入口）。检查 YAML／mapping、旧字段等价和冲突、四主体视图的实际 owner、伪造 subject 拒绝、无 runtime 构造、相机变换与提交后 capture、原 reset／close／Solution 及故障合同。纯检查不证明物理／像素结果。
- 本批五个交集的真实 MuJoCo 3.8.1 CPU 检查通过：Panda R3、重力补偿、装配 Panda R1 split、Pendulum、双轮车，各 reset→非零 step→再次 reset→重复 close；Robot 视图随实际 Controller 重绑。两个简单任务还核对相同 seed 重放、None 继续 RNG，并比较实际 named Runtime state。最终五个成功结果共 65 个 native 子步。
- 原始检查器把 Pendulum 既有 float32 sampler 与 float64 期望值作精确比较，出现约 1.7e−8 差异；失败日志保留，仅将独立期望按原合同转 float32，未改生产 sampler／放宽容差。本批 6 次 CPU run 含此失败，实际 90 子步；连同上一批 5 次／60 子步，当前窗口累计 11 次／150 子步。双锁顺序、180s 单次、900s／2,000 子步累计和无 GPU／GUI限制均保留，已释放资源。
- 后续纯 alias／不可变 subject／Task identity／CameraSpec capture 修复未改变上述无相机旧配置 CPU 输入及推进路径，按实际影响复用同次原始结果；新纯合同覆盖差异。不把本批结果扩大为新 GeoPhys／Isaac factory、真实 RGB 或完整 Solution 验证；未变的 provider 原生执行／提交／状态／clock owner 可引用 G05 原证据，发生变化的完整构造链仍需后续对应复验。

精确证据：本窗口 `implementation-metrics-002.json`、`construction-and-subjects-pure-005.log`、`final-construction-identity-001.log`／`002.log`、`cpu-run-plan-002.json`／`003.json`、`cpu-002-*`／`cpu-003-*` 和 `cpu-independent-readback-002.json`。读回来自同次运行，未冒充第二次 native 测量。

| 事件 | 本批后状态 | 仍需完成 |
| --- | --- | --- |
| E00 | 基线／保护输入／量化口径继续成立 | 最终累计度量随退出包复算 |
| E01 | 正式 Task caller 共用构造 owner，Controller selector 归一化已验证 | 三个高级 candidate UID／factory 仍不是薄输入兼容层；旧 class binding caller 保留严格兼容；execution 与 provider 输入合同待收敛 |
| E02 | 四主体同一公开视图、原资源绑定和简单 TaskDefinition lifecycle 已验证 | Panda／Nut 的 TaskDefinition 与 reference binding 仍需按实际语义接口对账，不能宣称所有 Task 构造已统一 |
| E03 | 普通正式构造与共同 reset／close 增量已验证 | legacy candidate 构造、constructor 反射判断与 reset 中剩余职责待处理 |
| E04 | 首批共同提交／Solution／adapter admission 修复保留 | 对 remaining action／model／clock 特殊路径完成逐项对账；本批未改变求解器、模型与推进语义 |

G05 仍已按原范围接收；代码优化和项目优化尚未接收，E00～E04 目标继续 active，不启动 G06。两任务完整单 seed Solution 属后续 O5／E13，G07 三 seed 最终矩阵另行保留。

第二批收尾：changed Python AST／JSON、whitespace、四保护输入及两个 submodule pins 核对通过；双锁无 holder。文档 validator 仍仅报既有 `protected local input changed: MUJOCO_LOG.TXT`，历史链接问题 96 项，与启动结果一致，未改原件或 validator 基准。

### 6.2 第三批：正式物理配置、旧 MJCF UID 与模型能力

输入 `038eb10f`，上一轮属于有提交和真实证据的 progress；本轮继续原 E00～E04 目标，没有改成局部完成。以下是本批完成的实际迁移：

- 正式 `pick-cube-p16-reference-v1` 可通过 `controller.profile_id` 选择原有五种 MJCF 物理配置：`panda-direct-effort-v1`、`panda-joint-effort-reference-v1`、`panda-r3-effort-reference-v1`、`panda-joint-mass-effort-v1`、`panda-r3-mass-effort-v1`。Robot 的 `native_drive`、Controller `parameters`、episode seed 及高级 source workspace 分别进入原配置 owner，未知项／无效组合／未消费的 Task 参数在构建前拒绝。新字段不扩大 provider／source／模型资格。
- 旧 `pickcube-physical-candidate-v1` 的 factory 从 111 行变为 30 行，只翻译旧输入并转正式 factory；返回 `PickCubeReferenceEnv`，`env.uid` 为正式 UID。原 Artifact／scene／source closure、Controller 算法与行为边界保留，内部 historical construction_id 未被改写成新资格。旧 caller 的显式 source 目录继续保留。
- `_build_candidate` 不再创建 Env／配置相机；改为提交实际 binding。source 快照复制和 Scene 投影由既有 Runtime source adapter `bind_reference_scene_source` 负责。正常路径复用自有 receipt 快照，不要求用户给临时目录，也不进行第二次 copytree；绑定退休或构造失败时释放自有快照。高级 caller 的持久副本不作为 Env 自有文件删除。
- 相机输入的纯检查归入 renderer contract；普通 CameraSpec 在 Artifact 编译后绑定，advanced Geometry 仍验证 Artifact，observer／task camera 身份、输出和 pair 检查保留。Task compatibility factory 不再自行执行 RGB／observer 编排；真实渲染尚未在本批补测。
- 部署预检现在按真实声明分别验证 Position constructor owner 和 physical port，保留 source、plan、反馈、Controller identity 与物理端口检查。显式 mixed action 的许可仍由原 `position_physical_mixed` 合同控制，没有因构造复合能力而开启混合命令。
- R3 wrapper 只在底层 servo 实际具有 source-model binding 时暴露 `bind_model`；固定模型不再被错误要求注入动态模型，动态模型仍执行原 source 检查。Env constructor 不再以 `from_reference_config` 是否覆盖来推断组件构造；显式 config／既有组件兼容能力和 Base 默认构造保留。未声明 binding/config 的自定义子类须走显式构造或正常 registry，不能隐式落成空组件 Runtime。

量化口径：生产 11 个修改文件，+449／−295，净 **增加 154 行**；测试 1 个文件 +124 行；本批补齐正式字段、共享校验与保全路径的代码多于删掉的旧入口代码，不能报告为净减。从 `21577d32` 累计生产 +1,006／−978，净 **增加 28 行**。文件新增／删除／迁移均 0，tracked 路径 1,365→1,365。Task factory 111→30 行、source lowering 的职责归位与重复编排消除是具体成效；最终行数是否下降须等其余 legacy 迁移后重算。source block 经过重写，binding body 有 ExitStack 作用域引起的缩进变化，不把这些删除行当作删除了功能；没有把整份文件搬走领取优化成效。测试、诊断、文档逐文件统计见 `implementation-metrics-003.json`。

验证：

- 本批 163 个不同的定向纯合同节点通过：组合检查 161 项，另有显式 constructor capability 与未消费 Task 参数拒绝两项；最后 7 项复核覆盖新增拒绝和五种有效解析。覆盖五 profile 的 YAML／mapping／resolved 回环、实际 subject/Controller owner、source 生命周期和构造失败清理、旧 UID 进入正式 factory、缺物理绑定仍拒绝、模型能力与 source 校验、原有 reset／close／Solution／相机和部署合同。
- 在既有双锁和本窗口预算下，五种正式 profile、reset-scoped Controller 切换及旧 UID direct／joint 共八条最终 MuJoCo 3.8.1 CPU 检查通过。均有非零 action、实际公共 clock/boundary 与外部 mj_step 计数；切换路线另验证 generation、旧动作拒绝、故障锁存和显式 reset 后恢复。最终八条成功运行共 45 子步，单 interval 的 native 计数与 dt／substeps 一致，没有据此声称力测量或完整任务成功。
- 原始失败保留：joint 首次被部署 assessment 拒绝，修复对既有 constructor/port 组合的声明检查后通过；nominal R3 wrapper 的 bind_model 误声明在 reset 时失败，修复后 nominal／dynamic 路线通过；检查器在故意提交 stale action 后未按既有故障合同先 reset，纠正检查器后恢复通过，未修改生产 fault 策略。本批 11 次 native run／50 子步，含上述三次失败。整个 E00～E04 窗口累计 22 次／200 子步，仍小于原 900s／2,000 子步累计上界，单次 180s、双线程、8GiB 地址空间、无 GPU／GUI范围保留。
- 后续 constructor 反射删除和不支持的 Task 参数静态拒绝未改变本批显式 binding／空 Task 参数的受测有效路线；以针对性纯检查覆盖该差异，复用同次 native 结果。ISAAC factory、Position diagnostic compatibility、GeoPhys 新正式入口和真实 RGB 本批未实测，不从共同类名继承新的能力声明；既有 provider 执行、typed 命令和渲染 adapter 未变部分仍按原身份与影响复用。

本窗口证据为 `formal-physical-combined-001.log`、`constructor-capability-001.log`、`formal-physical-static-final-001.log`、`formal-physical-assessment-001.log`、`formal-physical-models-001.log`，以及 `cpu-run-plan-004.json`～`007.json`、对应 source diff／probe／run 原件和 `cpu-independent-readback-003.json`。reader 是对同次原件的独立一致性读回，不是第二次物理运行。

E01 仍缺 Isaac candidate 与 Position advanced 输入的共同声明／构造迁移、两种配置 codec 的收敛；E02 仍缺 Panda／Nut TaskDefinition 语义接口对账；E03 仍需完成其余 legacy 构造及 reset 职责；E04 仍需完成其余 action/model/clock 路径审计。下一步按这些实际 owner 继续，目标保持 active，不签收全部代码优化、不启动 G06。

第三批收尾：最终纯构造另与同次 native 原件逐一比对五种 profile 的 Artifact／source／Controller identity，并核对旧 UID 与正式 UID 的 direct／joint 声明相等，见 `final-source-equivalence-003.json`；该检查没有启动第二次 native。文档 validator 仍只有既有 `protected local input changed: MUJOCO_LOG.TXT` 与 96 项历史链接问题；保护输入及 pins 未变，双锁已释放，当前输出约 70 MB，低于预留 2 GiB。tracked 非测试诊断代码本批 0 变化；ignored probe 和维护脚本单独列于度量 JSON，不混入生产代码、测试或 tracked 文件净变化。

### 6.3 第四批：共同声明构造、Isaac 输入翻译与 Position 语义合同

输入 `a382cf96`，仍为同一 E00～E04 窗口、阶段分支和当前 chat 单 writer。本批交付是 progress，完整目标继续 active。

- 普通 resolved 配置和 Position advanced 输入经 `from_task_binding → reconstruction.initial → 同一 Env constructor`。任务编译器保留 source／Controller／Artifact 声明，构造与失败资源回收由 Env 负责；编译失败与 constructor 失败分别只有一个清理 owner，后者也覆盖 horizon／相机／execution 等初始化前拒绝。保留 source 清理失败为主异常 note，不再重复调用同一个 Task cleanup。初次 seeded 编译消费配置 seed，未配置时仍为原 31；reset 算法未改。
- 旧 `pickcube-isaac-physical-candidate-v1` factory 从 147 行缩至 26 行，只校验／翻译原输入到正式 PickCube 配置并返回正式 Env／UID。五种已有 physical profile 共用 Controller selector；原 delivery、隔离 drive、冻结 seed、horizon≤1000、in-process 及不支持 reset selection／MJCF workspace 的限制保留。binding 返回物理执行声明，reset 后的 Controller 引用来自本次重建值。Isaac App 的 renderer source 准备和失败回收从 Task 移入既有 Runtime owner，成功后仍由既有 Runtime leases 管理生命周期，不引入第二个 App／Runtime。
- 两个 Position source 编译器改为返回 binding 和原事实；旧 `build_position_candidate`／`build_versioned_position_candidate` 保留结果 bundle，经共同构造 owner 返回 Env。中性 Task 及 F04／F05 typed 输入保留原 Artifact、source、UID、动作单位与准入，未被改名成 PickCube。中性 Position 与双主体诊断的临时 evaluation 对象改为已有 `TaskEvaluation`，补齐原公共 reset 所需的空 `reward_terms`；原零 reward／未成功与 DG02 原 raw lift 判据不变。

量化（tracked Python 文本行，包含空行）：本批生产 9 个文件，+390／−386，净 **增加 4 行**；测试 2 个文件 +95 行；非测试诊断 1 个文件 +2／−1，净 +1。从 `21577d32` 累计生产 26 个文件 +1,294／−1,262，净 **增加 32 行**。tracked 路径 1,365→1,365，新增／删除／迁移均 0，项目文件净变化 0。不能将 factory 缩短当作项目代码净减。App 准备职责由原 Task 17 行逻辑重写为 Runtime 24 行 context；原样跨文件搬运行数为 0。Position 的同文件声明拆分和 constructor 的缩进也计入 Git numstat，未冒充删除功能。测试、诊断、文档和 ignored 执行代码分列于 `implementation-metrics-004.json`。

验证及实际限制：

- 127 个不同定向纯／fake-IO 节点通过：120 项 common construction／reset policy／observer／selected 配置合同，5 项 F04 fake-IO Env／Recorder／动作归一化，以及新增的 2 项旧 Isaac 严格 seed 拒绝。最后 7 项复核旧 UID 翻译与 seed 限制，未重复计数。验证了配置回环、五 profile selector、单次失败回收、App 仅回收本次自开实例及主异常保留；fake-IO 的 Recorder 不能称为实际 PhysX 证明。首轮 F04 检查缺少其要求的 `F04_S1_OUTPUT`；设置本包独立输出目录后 5 项通过，原失败日志保留。reset-policy fixture 补齐上一批新增的可选 `build_sampled=None` 字段，不改变生产准入。
- 本批四个双锁内 MuJoCo 3.8.1 CPU run 通过：正式 direct、单主体 Position、双主体 Position，以及最后 failure-owner 重构后的双主体复核。每条均 reset→一个非零 interval→再次 reset→重复 close，核对公共 boundary／clock、实际 mj_step 计数及自有／caller-owned source 生命周期，共 20 个子步。最终三个不同交集均有真实证据；最后 exception-only／旧输入拒绝改动不改变其有效 source／Controller／推进路径，复用相应运行，未重复整张历史矩阵。
- 执行偏差明确保留：一次 pytest 命令误纳入 3 个真实 MuJoCo reset 节点，未先获取双锁；三项均在缺少 `reward_terms` 处失败，未成为通过证据。该次没有外部 mj_step 计数，不能报告为测得零子步；按每项 50、合计 150 子步保守计入本窗口预算。之后使用锁内 probe 完成受影响的双主体 reset／step 复验。另一次首轮命令缺少 `GeoPhys/src` 的 PYTHONPATH；历史文件布局／identity 断言未用于本批通过结论。原始 `shared-binding-004.log` 等失败记录保留，不覆盖成成功结果。
- 当前累计 26 个受监督 CPU run、220 个可观测子步；加上述 150 保守计费为 370／2,000。受监督 run 的原始 wall_s 合计约 45.18 秒，另计未锁 pytest 9.91 秒，仍低于 900 秒窗口上界。受监督 run 均沿原单次 180 秒、双线程、8GiB 地址空间、无 GPU／GUI约束。失败的 pytest 命令不冒充受同一 supervisor 约束的运行。独立标准库 reader 读取同次原件，见 `cpu-independent-readback-004.json`；不是第二次物理测量。
- 本批未启动 Isaac／GeoPhys 新原生路线或真实 RGB。旧执行／提交／clock／renderer 算法未改部分可按原身份与影响复用；共同 factory、App 准备和重建 Controller 的新链仍需 Isaac 定向复验，不能从翻译层测试继承新的 native 结论。Isaac binding 仍有首次声明编译与 seeded initial 编译的重复 source 准备，后续应沿现有 binding owner 收敛，不能称该路线已经消除所有重复构建。

证据位于本窗口 `declared-construction-004-final.log`、`typed-position-004b.log`、`legacy-isaac-final-004.log`、`cpu-run-plan-008.json`／`009.json`、`cpu-008-*`／`cpu-009-*` 原件及上述度量／独立 reader。四个保护输入与两个 pins 未变，未新增 branch／worktree、未 merge／push／发布。文档 validator 继续保留既有 MUJOCO_LOG 基准差异及历史链接问题，不改原件来换取全绿。

| 事件 | 本批成效 | 仍需完成 |
| --- | --- | --- |
| E00 | 基线、累计度量及偏差计费继续维护 | 最终退出时按最终 diff 重算 |
| E01 | 两个旧物理 UID 进入正式配置；普通与 Position advanced 共用 Env 构造 | execution／两种 codec、Position 旧输入／source 管理继续收敛；Isaac 首次重复准备及新 factory native 复验 |
| E02 | Position 使用正式 evaluation，四主体已有共同视图保留 | Panda／Nut TaskDefinition 实际语义接口及真实 caller 迁移 |
| E03 | 编译与 constructor 失败清理 owner 分明；App 准备归 Runtime | 其余 reset／profile／故障职责逐项对账 |
| E04 | 新 Position 构造保留共同 interval、双 Controller 与 clock | 其余 action／model／clock 分流审计及 adapter 对账 |

G05 功能接收保持；代码优化和项目优化尚未接收，E00～E04 未完成，不启动 G06。

### 6.4 第五批：正式 TaskDefinition、Solution info 与普通 native interval

输入 `4b0a413a`，继续原目标与单 writer。本批推进 E02 语义构造，并修复实测暴露的 E03／E04 接线；不是将 E00～E04 缩为 TaskDefinition 一项。

- 正式 PickCube（含五种物理配置）、NutAssembly、Pendulum、双轮车都通过现有 `ReferenceTaskBinding.task_definition_factory(artifact)`，在同一 Env 构造 TaskDefinition，观察调用 `TaskLifecycleAdapter`。reset 重建后按当前 binding／Artifact 重新绑定，避免保留旧语义对象。两个简单任务的实际 factory 已迁移一参合同。record metadata 改以真实 external action contract 选择格式，不再以“存在 TaskDefinition”误判成简单任务。
- 现有 `as_task_state_view` 增加 `CanonicalTaskStateView`，直接引用具名 canonical state；不生成虚构 qpos／body／site 索引，不复制物理状态。数组 consumer 保留原投影。PickCube 的 legacy component 仍使用原 compiled references／scalar admission；canonical 模式由 Artifact 声明，Nut 也继承已有 TaskDefinitionBase。未开启 named batch 或 G06。原 evaluator 兼容函数与新 TaskDefinition 共用同一 `_evaluate_bound`／数值函数；保留 Python tuple／scalar 顺序。
- 公共 Gym info 中的 `ObservationSchema`／只读 mappings 会被原 Nut Solution 的有限性检查拒绝。已有 metadata owner 现在将它们投影为 callback 值 payload，覆盖 reset／act／observe 的 10 个实际调用点；Gym info 仍保留原类型，字段和数值不删改。Solution guard 未改，NaN 仍被拒绝。
- 普通已准入 native Source 过去没有安装 live scene interval binding，Nut 因而在施控前被共同提交 owner 拒绝。现在 ScalarRuntimeBuilder 提交实际 native Controller，既有 Runtime adapter 在原 admission 之后安装同一个 legacy source／Controller binding；source 的已声明 closure 必须匹配实际 receipt。安装处不再依据单个 R05c profile 名称分流。原 R05c／R05b exact admission block 按源字节核对未变，source、Artifact、writer、资源、Controller、时钟及重放验证保留；没有删除“缺 live interval 拒绝”的检查，也没有制造 SceneDefinition 或第二个 Runtime。

本批 tracked 变更范围 25 个既有文件，25→25；生产 Python 18 个文件 +204／−82，净 **增加 122 行**；测试 1 个文件 +90；tracked 非测试诊断 0。本窗口累计生产 37 个修改文件 +1,484／−1,330，净 **增加 154 行**。项目 tracked 路径仍 1,365→1,365，新增／删除／迁移均 0。原样跨文件迁移 0 行；同文件抽取 4 行 canonical 输入／评价操作供两个接口共用，不能当作项目行数减少。新增状态适配和两个真实接线修复有成本，不报告性能提升或代码净减。文档与 ignored probe／维护脚本单列于 `implementation-metrics-005.json`。

验证与证据：

- 152 个不同的纯合同节点通过：`task-definition-005-complete.log` 组合通过 152 项，其中 148 项覆盖构造／旧输入／predicate／temporal／shared submission／lifecycle，另有 4 项 source／Task 构造失败清理；最后 `task-definition-005-oracle-final.log` 的 7 项复核包含这些 4 项和已计数的 3 项新语义 oracle，不重复计数。3 条正式构造下的 21 个 canonical 状态逐个比较 reward 浮点位、success／failure、metrics、reward terms，与原 evaluator 一致；正式 observation 的旧 evaluate callback 注入拒绝，证明实际进入新 lifecycle。旧数组 predicate／temporal 检查保持。
- 五个真实 MuJoCo 3.8.1 CPU 交集通过：Panda R3、装配 Panda R1 split、Pendulum、双轮车、NutAssembly。各 reset→一个非零 interval→第二次 reset→重复 close，核对实际 TaskDefinition owner、重绑、原 record metadata、公共 boundary／clock 与 mj_step 计数。Nut 使用正式 `reset_for_solution`／`step_with_solution`，只执行一个 interval。最终五格共 65 子步，不声称完整 Solution、任务成功或力测量。
- 本批 10 次锁内 CPU run，含 4 次失败：`cpu-010-nut` typed info 拒绝；`cpu-011-nut` 同问题的字段／身份读回；`cpu-012-nut` 在施控前缺 live scene interval；`cpu-013-nut` 编辑缩进导致 import 失败，观测零子步。修复后 `cpu-014-nut` 通过；`cpu-015-nut` 进一步验证 step 后 Solution failed=False、原 strict receipt 的 requested／completed／samples 均为 5，通过，所有原始失败保留，未关闭原 guard。probe 的私有 `_validate(raw Gym info)` 诊断仍会报告 typed 字段不受旧 Solution 接受；它不是框架 callback，最终 callback 已使用值 payload，raw 中 failed=False／done=False 并完成实际 interval，reader 明确区分。
- 一个旧 GeoPhys fake-consumer 节点因未配置隔离 interpreter，在 materialization 前失败，未列入通过结论；四个同次 cleanup 节点通过并已复核。该旧 fixture 的配置入口迁移仍需后续处理，不用 fake 结果代替真实 GeoPhys。现有 R05c exact admission block 的输入／当前 SHA 相等由 reader 核对，不据此声称该路线新 native 复跑。
- 累计受监督 CPU 36 次、290 个可观测子步，含 8 次已保留失败；加前批未锁 pytest 的 150 保守计费为 440／2,000。受监督 native wall_s 合计约 57.97 秒，另计前批 pytest 9.91 秒，小于 900 秒。单次 180 秒、双锁、双线程、8GiB 地址空间、无 GPU／GUI限制不变。没有新 GeoPhys／Isaac、RGB 或完整 Solution 实测。

原始计划 `cpu-run-plan-010.json`～`015.json`、对应 `cpu-010-*`～`cpu-015-*`、最终纯日志、`native-inputs-005-final.json`、`cpu-independent-readback-005.json` 及度量均在同一 ignored 包。reader 只读同次结果，并保存 checkpoint 对应的 36 个输入，不将后续新 run 混入旧统计；不是第二次物理测量。最后共享 canonical 函数抽取／Protocol annotation 不改变受测数值和有效运行路径，按 source diff 与 21 状态 oracle 复用上述运行。

| 事件 | 本批具体成效 | 剩余工作 |
| --- | --- | --- |
| E00 | 累计行数、文件数、成功与失败、独立读回继续维护 | 最终完整退出审计与度量 |
| E01 | 保留共同构造与两个旧 UID 翻译成果 | execution／codec、Isaac 首次重复准备及新 factory native、剩余 Position 输入与 source 管理 |
| E02 | 正式四类 Task 共用 TaskDefinition 构造／语义 lifecycle，实际 caller 已迁移 | 其余主体／Controller／registry 构建合同逐项对账；advanced diagnostics 不冒充完成 |
| E03 | reset 语义重绑，typed Gym info 与 Solution payload 职责分明 | 其余 reset／profile／fault／close 审计 |
| E04 | 普通已准入 native 的真实 source／Controller interval 已接通 | 其余 action／model／clock／部署与 worker adapter 对账，含受影响 GeoPhys／Isaac 范围 |

G05 功能接收保持；优化和 E00～E04 整体仍未接收，不启动 G06，不 merge／push／发布。

### 6.5 第六批：编译后的 Controller 合同与 Isaac 正式入口复验

输入 `f45ac387`。正式 Isaac 物理配置过去在创建 binding 时先编译一次 source，而共同构造又按 seed 编译一次；现在 binding 只声明能力，实际 source 由共同构造／reset 的现有编译入口生成。动作 schema 和空间取自该次实际 `PhysicalControlExecutionV1`，不再由 Task 提前复制 Controller 列表；已有物理 schema 的扩展字段保留，显式非物理及 mixed action 合同仍归原 owner。三个原先重复的 schema 生成点调用同一物理执行 owner；reset 后也从新执行对象重绑，seed／horizon、身份、source、Controller 和故障检查未放宽。

Isaac 正式入口首次真实复验在 reset 前被部署预检拒绝；原始结果和失败保留。对照实际组合后，预检补认已有资格内的 Isaac CUDA 位置观测 owner 与独立 physical port，继续执行原有 exact F06 USD 来源检查、不同 Controller 身份和 compiled binding／feedback 检查。后续真实复验通过；不据此扩大 Isaac 资产或 provider 资格。构造后 source 编译计数从原先代码路径的两次降到实测一次；第一次／第二次 reset 后累计分别为 2／3 次，表示每次重建各编译一次，未省略 reset 的重建。

量化：本批 7 个生产文件 +50／−22，净**增加 28 行**；1 个测试文件 +54／−0。累计生产 37 个文件 +1,522／−1,340，净**增加 182 行**；累计测试 +677／−8，非测试诊断 +2／−1；tracked 路径 1,365→1,365，新增／删除／迁移均 0。三个重复 schema 表达式收归一个已有执行对象方法；没有跨文件原样搬迁，也不把代码净增加描述成减少。文档与维护脚本单列，最终度量随退出重新计算。

验证与边界：

- 124 个定向纯合同节点通过；最终修改后另有 94 项合同复核通过（两组有重叠，不相加）。覆盖共同编译、实际执行对象、schema 扩展、seed 拒绝和旧输入；纯合同不代表 native 物理表现。
- 真实 MuJoCo CPU direct 与 reset 选择各完成 reset→非零 step→第二次 reset→close；后一条还检查重建代次、旧 action 拒绝及恢复。本批两个成功运行 15 个 native 子步，原 CPU 窗口累计受监督 38 次／305 个可观测子步，加历史未锁运行的 150 保守计费为 455／2,000。
- 独立 Isaac CUDA／RTX headless 窗口使用正式 UID、原 F06 USD delivery、固定 seed 31／horizon 8，完成 reset、一个非零控制 interval、第二次 reset 和三次同步 RGB；独立 reader 检查 source／state boundary／clock、capture 期间无物理回调、图像所有权和关闭。实际首次构造／两次 reset 的编译次数为 1／2／3。应用 close receipt 为 completed；SDK 回调退订接口不可用的诊断仍保留，进程随后退出。启动观察器安装前的隐式物理推进未知，不声称像素逐位一致或任务成功。
- Isaac 两次运行包括首次拒绝及复验成功；未观测到首次运行物理回调，按预留保守计费 59，成功运行观测 41，累计计费 100／120，native wall 约 240.22 秒；资源违规 0，锁已释放。原始计划／失败／成功／资源和 reader 分别保存在 ignored `isaac-006/plan.json`、`plan-v2.json`、`runs/isaac-001/`、`runs/isaac-002/` 与 `budget-ledger.jsonl`。本批仅在 Isaac 路线变化前后冻结各自 source diff，Position schema 去重发生在 native 复验后，属于等价合同输出，未虚称这些最终字节在同次 GPU 中运行。

| 事件 | 本批具体成效 | 仍需完成 |
| --- | --- | --- |
| E00 | 失败与成功、各自输入、资源和实际计数分别记录 | 最终逐项审计与累计度量 |
| E01 | Isaac 正式配置去除首次重复编译，实际 source／Controller 构造及 reset 可见 | execution／codec、Position 旧输入与 source 管理及其余入口继续对账 |
| E02 | 三处动作 schema 使用实际 Controller execution owner | 剩余主体／Controller／registry 构建合同审计 |
| E03 | 编译后的 binding 在构造及 reset 重建后重绑；首次失败仍保留 | 其余 reset／profile／fault／close 审计 |
| E04 | 已接收范围内 Isaac 真实提交、状态边界、clock 和 RGB 复验 | GeoPhys 受影响路线及 action／model／worker adapter 对账 |

G05 保持原有界接收；本批不是 E00～E04 总接收，不进入 G06。

### 6.6 第七批：隔离 worker 的状态边界与控制归属

输入 `cdb1ded1`。正式 PickCube 隔离 worker 原可 reset，但实际 step 在共同控制 lifecycle 请求 `state_boundary_identity()` 时失败：transport 没有暴露这项已有 Runtime 合同。现在 transport 只传递已登记的 canonical／legacy boundary 值；parent 的 RemoteSession 保留实际 source／Artifact，父进程和 worker 各用现有 position subject／legacy native-feedback scope 校验当前 boundary、Controller 与资源，然后才进入原 Runtime 提交。worker 独立重建、source／Artifact／Controller 对账、episode／sequence 身份和原生 layout admission 都保留。GeoPhys 布局事实中的 NumPy 数值在 transport 变为普通有限 JSON 标量，数组、句柄和非有限值继续拒绝。非 Isaac worker 的有限操作超时从 30 秒调整为 120 秒，覆盖本机首次 GeoPhys interval 的实际耗时；外层单次运行仍限 180 秒。

量化：本批 5 个生产文件 +55／−9，净**增加 46 行**；1 个测试文件 +15／−0。累计生产 40 个文件 +1,577／−1,349，净**增加 228 行**；测试 +692／−8；非测试诊断 +2／−1。tracked 文件 1,365→1,365；新增、删除和迁移均 0；没有把 source scope 或 transport 编码移动计算成行数减少。文档和 ignored 验证脚本不计生产代码。

验证与保留失败：

- 正式 UID 的真实 MuJoCo CPU 隔离 worker 完成 reset→非零 action→第二次 reset→重复 close，状态边界 control step 为 0→1，时间 0→0.01 秒，第二次 reset 产生新 episode。结果为 `cpu-020-worker/result.json`；后续 GeoPhys 专用数值表达和有限 timeout 的修改未改变此 MuJoCo 输入／控制逻辑，本条按 diff 复用，不声称是最终字节的第二次实测。
- 正式 UID 的真实 GeoPhys CPU 隔离 worker 在最终代码下完成同一短程序列，边界为 0→1、时间 0→0.01 秒，并产生新 episode；`cpu-023-geophys-worker/result.json` 耗时约 55.65 秒。这证明受测配置的真实 source、worker state／clock 和控制提交接线，不是完整 Solution、成功任务或新 provider 资格。
- `cpu-017-worker` 是检查器误调用未暴露方法；`cpu-018-worker` 显示生产 step 缺 boundary；`cpu-019-worker` 显示后续 subject scope 缺 reset 合同；`cpu-021-geophys-worker` 是布局中 NumPy 标量被 transport 拒绝；`cpu-022-geophys-worker` reset 成功后首 interval 超过原 30 秒期限。原始失败、各自冻结 diff／计划和修复后结果均保留；不将失败写成通过。
- 9 个逐项核对的无 native transport 合同节点通过，覆盖 boundary 值跨进程、有限标量／非值／NaN 拒绝、callback、episode／sequence 和关闭。误运行整个旧 transport 测试文件时，3 个 fixture 节点失败：两个被 native import guard 阻止或 launcher 路径不匹配，一个同样在 guard 处停止；日志 `worker-020-pure.log` 保留。这次无锁运行触发资产解析，未将其作为纯证据；物理子步无法观测，另保守计费 150。
- 本批 7 次双锁监督运行各为未观测子进程物理计数预留并计费 50；累计监督 45 次，其中旧已观测 305 子步、此次 worker 内部子步未知。加两次无锁旧 pytest 的各 150 保守计费，累计预算计费 **955／2,000**。锁已释放；RLIMIT_AS 为子进程继承的每进程上限，并非本批全部进程的 aggregate cgroup 读数。

| 事件 | 本批具体成效 | 仍需完成 |
| --- | --- | --- |
| E00 | 真实通过、5 次失败、误运行及保守计费分列 | 最终累计度量和逐项退出对账 |
| E01／E02 | worker 复用现有 source／Artifact／Controller，不创建平行 Runtime | 配置 codec、Position 输入及主体／registry 构造对账 |
| E03 | 两个受测 provider 的隔离 worker reset／close 已复验 | 其余 fault／profile 和未受测模式 |
| E04 | source-bound boundary、clock 和提交跨 parent／worker 对齐，GeoPhys 标量编码问题修复 | 其余 action／model／renderer 及 worker 组合按影响核对 |

G05 继续有界接收，E00～E04 和项目优化尚未整体接收；不进入 G06。

### 6.7 第八批：共同 Controller selector 的配置入口

输入 `dd1538f3`。`controller.profile_id` 现在在共同配置入口统一归一化为 `control.profile_id`，不再由这一层根据 Task class 标志选择不同字段。PickCube 的既有 selected codec 在兼容边界读取相同的 `control.profile_id`，继续识别旧 `task.controller_profile`，冲突拒绝；Pendulum／双轮车沿已有 ControlConfig 消费它。三种任务的 mapping／YAML 与旧写法解析结果相等，原已解析身份和任务允许的 profile 范围保持；NutAssembly 仍拒绝未支持 profile。实际公开 factory 继续消费相同已解析合同，不因此宣称两种底层 resolved codec 已合并。

15 项按节点选择的配置纯合同和 1 项公开 factory 消费合同通过；不运行物理，也不把解析测试写成 native 证据。`config-controller-008.log`、`config-factory-008.log` 留存。PickCube 与两个简单任务的既有真实构造使用同一解析结果，本次复用相关 native 证据；后续其他 codec／输入仍需对账。

本批 1 个生产文件 +14／−7、净增 7 行，1 个测试文件 +1 行；累计生产 +1,585／−1,350，净增 235 行，累计测试 +693／−8；无文件新增、删除或迁移。逐文件和文档度量见 `implementation-metrics-008.json`。E01 的共同输入归一化进一步收敛，E00～E04 仍未整体完成，G05 保持原有界接收。

### 6.8 第九批：registry 不再反射判断构造方法覆盖

输入 `05d6e075`。`registry.make_env` 不再比较 `from_reference_config.__func__` 是否等于基类实现来猜测构造协议，而是调用类实际提供的工厂。既有基类工厂在无 class binding 时，负责解析组件配置、检查单环境 batch layout 并构造组件；有 class binding 的旧 scalar caller 及显式覆盖工厂继续按原合同执行。已经迁移的正式 selected／component factory 仍走原共同 `from_resolved_config`；没有扩大旧候选资产／renderer 能力。

本批生产 2 个文件 +11／−9，净增 2 行；未新增测试代码或文件，没有文件迁移。自 `21577d32` 累计生产 +1,595／−1,358，净增 237 行；不能将本批抽取解释为项目净删除。逐文件度量见 `implementation-metrics-009.json`。4 项已有 caller 合同在双锁下通过：未带 marker 的自定义组件、无声明子类纯构造、旧 class binding 以及正式 factory 消费解析结果。检查未 reset／step，也不声明 native 结果；`registry-009-pure.log` 保留。正式生产任务在 registry 前置共同工厂分支未变，本批旧组件与 binding caller 的影响已由对应检查覆盖。

E01 仍需对剩余配置 codec／Position 输入对账；E02～E04 的剩余审计和整体接收尚未完成，G05 保持原有界接收。

### 6.9 E03 资源归属与失败边界核对

以下是当前代码的所有权对账，不是对未运行组合的新增 PASS：

| 资源或阶段 | 实际 owner 与关闭顺序 | 已有证据／待核边界 |
| --- | --- | --- |
| Task 编译、source 快照 | `from_task_binding` 在编译后失败时调用 `_release_failed_task_construction`；已构造 Env 的 `_close_reference_resources` 关闭 source receipt，再关闭 binding 声明的 Task 自有资源。`ExecutionSourceReceiptV1.close` 只清理其临时 owner；显式 caller source copy 不转为 Env 所有 | 既有编译／构造失败与旧 caller 拷贝检查；第三方自定义 receipt 的实现仍须按其合同验证 |
| RuntimeSession 与 worker | Env 的 `_close_reference_resources` 委托 `close_session_and_runtime_owner`，分别关闭 session、读取需要的 close receipt、关闭实际 runtime owner；失败 reset 保留的不同 session 按对象身份去重关闭。`RemoteSession` 拥有 worker 和 socket，超时／协议错误终止其 worker | MuJoCo／GeoPhys worker 的 reset／step／reset／重复 close 已实测；不同 worker 方法和故障注入仍按各自影响检查 |
| Isaac App 与 scene lease | Isaac Runtime 的进程 App owner 持有 App，scene 由实际 session 租用；进程 lifetime hold 存在时 close 请求延后。close receipt 区分 attempted／completed／failure；不可据 Env 已关闭推断 App 已完成关闭 | 第六批在受测 Isaac 路线取得 App close completed；SDK callback 退订诊断保留；不扩展到其他 SDK 版本 |
| Task RGB、observer、独立 visual model | Env `_close_camera_consumer` 先脱离引用，再分别 close task consumer、observer consumer、visual session，保留首个异常并附加后续异常；visual 最后 close 状态和 fault 状态单列。GeoPhys／Isaac 摄像机借用现有 Runtime，MuJoCo renderer-only 使用独立 visual model | 第六批 Isaac 三帧及关闭；旧 5b／5c 和跨组合证据限原范围。失败后不能以旧帧视为当前有效帧 |
| Recorder／episode | `EpisodeExecutionState.execute_close` 统一协调；reference 路线在健康时按实际发布和 recorder 状态 finalize，再释放相机与 session；component 路线由 lifecycle 关闭 runtime，lifecycle 尚未建立时由 Env 关闭已返回的 runtime | 既有 close／fault 合同及受测重复 close；不同记录格式与完整 Solution 属后续验证 |

reset 的共同阶段由 `EpisodeExecutionState.execute_reset` 顺序调用 prepare、materialize、reset、read state、observe、publish；异常传给实际失败阶段的 `on_failure`。source／target 的预检拒绝可在旧 session 关闭前发生；替换及物理写入后的故障则不能把旧 publication 冒充新状态。具体历史故障测试和真实路线的边界见本节前述批次；未据此宣称所有 provider／renderer 组合已覆盖。此表为静态 owner 审计和既有证据索引，不是新的一轮 native 测量。

### 6.10 E04 动作入口及未调用旁路

静态追踪当前实际 caller，删除 `SelectedReferenceEnv._step_leaf_position`：移除前 Core 中非 ignored Python 搜索只有其定义，没有调用者；未将历史 ignored 探针当作当前调用链；该私有包装直接调用 `_prepare_leaf_position`，缺少共同 `prepare_selected_control_action` 所建立的 dispatch。保留 `_prepare_leaf_position` 作为现有 lifecycle 的 leaf 实现，`dispatch_leaf_control_interval` 仍调用共同 `submit_control_command`；没有删改 typed Action、资源、边界或 clock 校验。同样移除没有当前非 ignored Python 调用者、只转发 `_step` 的 `_step_mixed_control`。两处合计删除 7 行生产代码，不新增／删除文件，不把未调用代码当作真实运行性能提升。

| 动作入口 | 实际动作准备与提交 | 证据边界 |
| --- | --- | --- |
| 普通 selected `step`、caller `ExpertAction` | `_prepare_selected_step` → `prepare_selected_control_action`；按实际 physical／Position／leaf／mixed capability 准备，再经对应 Runtime submission | 现有 CPU 主体与正式 Isaac RGB、MuJoCo／GeoPhys worker 短程证据；只覆盖各受测组合 |
| 调用方 `step_with_solution` | 验证 reset 时接受的同一 Solution；`act` 后 Position 经 `_step_position_profile`、其他路线经 `_step`，两者均调用 `prepare_selected_control_action`，由同一 episode coordinator 执行 | Nut MuJoCo 单 interval 和既有合同；完整 Solution 不在本项宣称 |
| Env-owned `step_expert` | `prepare_expert`／`act` 后走同一个 `_step_position_profile` 或 `_step`；act 后验证失败保留故障 latch | 既有提案失败合同；具体 Solution 完整运行仍待 O5 |
| 组件与 leaf | 组件先由 `TaskLifecycleAdapter.prepare_step` 交 episode coordinator；leaf 通过上述共同 selected dispatch 进入 `_prepare_leaf_position`／`dispatch_leaf_control_interval` | 既有主体和 leaf 合同；不把不同 typed 动作表示合并，也不声称所有组合实测 |

本次无受影响实际 caller，复用既有 native 证据；仅做 Python AST、调用者搜索和差异检查。逐项故障与所有支持模式的完整对账仍未结束，不提前宣布 E04 接收。

### 6.11 Panda MJCF source 检查归属

输入 `6d556a4d`。Panda MJCF 的 fixed tendon／equality、actuator 映射、gain／bias 及有限有符号 force range 检查，现在由既有 MuJoCo source adapter `panda_effort_source_limits` 完成；Position candidate 的 Controller 声明读取 adapter 返回的限值。原 source closure、九个具名 joint、任务特有的 gripper cap、wrench 目标及后续 native admission 均保留。该改动按格式责任归位，**不是**新增 Panda 通用资格；Task 仍有其他待迁的 Robot／Controller 编译职责。

生产 2 个文件 +37／−30，净增 7 行；其中 29 行检查逻辑原样跨文件迁移、另移动 1 条 import，单列而不冒充删除；无文件新增／删除。8 个双锁下的真实 source 编译／fake terminal 合同通过，包含 tendon 篡改、source closure 和实际 Controller 输出；fake terminal 不证明 native。最终改动下正式 PickCube direct effort 走真实 MuJoCo CPU reset→非零 step→第二次 reset→重复 close，通过且观测到 5 个 native 子步。累计监督 46 次，已有可观测 310 子步；7 次 worker 的实际子步未知；加既有保守预留及无锁检查器偏差，累计计费 960／2,000。计划、冻结 diff、结果、纯合同日志位于 ignored `cpu-run-plan-024.json`、`cpu-source-024.diff`、`cpu-024-direct/`、`panda-source-010-pure.log`；不宣称完整 Solution 或其他 source 的资格。

### 6.12 质量模型 Controller 归位

输入 `296f1fe8`。PickCube 任务仍验证允许的 fixture ID、质量模型文件 SHA、schema 和 source closure，并选择其已受限的模型参数；实际 `MassMatrixEffortControllerV1`、已有 R3 reference wrapper、状态需求和新 physical execution 的组合移入现有 Controller 模块。源资产资格、R3 类型、帧、时间和模型适用范围均保留；没有声称模型适用于其他 Robot 或 source。

本批生产 2 个文件 +35／−23，净增 12 行。跨文件匹配到 14 行连续原样 Controller 组装代码，其余包括参数接口重写；迁移单列、不计作删除整个功能或性能提升。没有新增／删除文件或新测试文件。双锁下 10 个 Controller／正式配置合同通过；MuJoCo CPU 正式 joint-mass、R3-mass 各完成 reset→非零 step→二次 reset→close，各观测 5 个 native 子步；与本窗口先前同 seed 短程记录相比，Artifact、source closure、Controller identity、动作、reward 和 clock 均相同，见 `mass-owner-011-identity-comparison.json`。累计监督 48 次，320 个已观测子步，另 7 次 worker 的内部子步未知；含历史保守计费共 970／2,000。`mass-owner-011-pure.log`、`cpu-run-plan-025.json`、`cpu-source-025.diff` 和 `cpu-025-mass-*` 记录输入与结果；不是完整 Solution 或跨 provider 资格；受影响的 Isaac 质量模型配置未在本批重新实跑。

### 6.13 组件静态计划使用 Robot 控制能力

输入 `76a05cbe`。`resolve_execution_plan` 不再按 `panda-v1` 名称决定是否检查 Controller；它读取 Robot 声明的 `component_controller_kinds`，再将已有 `robot.controller` 的 kind／reference 记入计划。Panda 的公开 `supported_controller_kinds()` 与静态声明共用同一组值；没有此组件能力的 Robot 保持原空选择。只有 UID 时可从已登记的 Robot 类型读取静态声明，无需实例化 Robot 或启动 provider；未知 UID 仍留给正常 registry 构造边界。实际 agent iterable 只消费一次。此机制让其他 Robot 可以声明相同的组件合同，但不扩大其 native、source 或多主体资格。

本批生产 3 个文件 +27／−10，测试 1 个文件 +24；不新增／删除／迁移文件。4 项纯静态合同通过，覆盖另一名称的能力声明、不同 kind 拒绝、Panda 缺配置拒绝和多 agent 边界。另用真实 `PandaAgent` 声明与修改前执行计划作完整 mapping／identity 比较，结果相等；没有运行物理；独立 import guard 阻止 MuJoCo、Taichi、Isaac、USD 与 Warp 相关模块后，Panda UID 静态解析仍通过。证据为 `component-capability-012-pure.log`、`component-capability-012-comparison.json` 和 `component-capability-012-import-guard.log`。其余主体的实际 Runtime 构建和 native 能力仍按已有范围对账；E02／E04 未据此整体接收。

### 6.14 reset 重建能力归属

输入 `7143c476`。PickCube 在已有 reset profile 的任务 binding 中声明 `prepare_reset_switch`；共同 Env 依据此能力调用原 `prepare_switch_reset`，不再用 PickCube profile 字符串选择 reset 路径。该策略仍自行验证精确 profile、受限 provider 边和 seed；预检、固定 renderer 检查、候选 source 失败清理及 commit／fault 顺序保持。两类包含 PickCube 特定 schema／seed algorithm 的 receipt 构造归到现有 `reset_switch` owner，字段与值保持；不把不同 Task 的 reset 算法强行统一。

本批生产 4 个文件 +45／−22，净增 23 行；测试 1 个文件 +3；无文件新增、删除或整文件迁移。receipt 字段经过缩进／接口重写归位，不作为生产净删除。17 个双锁下的 profile、RNG、source 清理和失败阶段合同通过；真实 MuJoCo CPU 正式 reset-switch 配置完成 reset→非零 step→第二次 reset→close，观测 5 个子步，公开 reset／execution receipt 的 seed 31、代次 1→2 和 topology generation 保留。目标 provider 边的纯准备检查通过，但本批没有跨 provider native 重跑。累计监督 49 次，325 个可观测子步、7 个 worker 的内部子步未知；含原保守计费为 975／2,000。证据为 `reset-capability-013-pure.log`、`cpu-run-plan-026.json`、`cpu-source-026.diff` 与 `cpu-026-reset-switch/result.json`；E03 仍须完成其他 profile／故障组合的影响对账。

### 6.15 位置无关的受限 Panda source 身份

输入 `5394232c`。旧任务代码为了验证同一 Panda source，将某个历史 checkout 的绝对 asset 路径写死并还原后比较旧 hash。现在 source receipt owner 的 `matches_relocated_source_closure` 先验证实际 receipt／snapshot，再仅把 canonical XML 中唯一声明的 asset 根替换为固定标记，对包括全部资产在内的 closure 与固定摘要比较；不改实际 source、snapshot、receipt 或公开 identity。新固定摘要 `cbb7c0a3…` 是在原历史摘要检查通过后，对该同一 69 文件 closure 做上述投影得到，并保留原始推导记录 `panda-normalized-014-final.log`。Task 仅持有其受限 source 的固定规范化摘要，不再包含旧 checkout 绝对路径。资产变化、foreign receipt、缺失／重复根路径继续拒绝；这不是允许任意 Panda 模型。

本批最终生产 2 个文件 +30／−29，净增 1 行；其中 Task 文件 +10／−29、净减 19 行，source owner 新增 20 行；测试文件变更另计 +14／−13。旧验证逻辑按 source owner 重写，不能按整文件删除或原样迁移领取成效；项目文件无新增、删除、迁移。8 个双锁构造／篡改／失败清理合同通过；正式与旧 UID 的真实 MuJoCo CPU direct 各完成 reset→非零 step→第二次 reset→close，各观测 5 子步。与修改前各自短程记录对照，Artifact、source ID／closure、Controller identity 及 source copy 所有权相同；显式旧 caller 目录仍归 caller，普通自有快照关闭后释放。`panda-normalized-014-pure.log`、`panda-normalized-014-comparison.json`、`cpu-run-plan-027.json`、`cpu-source-027.diff` 和 `cpu-027-*` 留存；同一原始测量的读回不是第二次物理运行。最后移除重复的本地 import，仅复用该模块已有的相同函数引用，并复核篡改拒绝；此无语义变化发生在 native 冻结输入之后。

累计监督 51 次，335 个可观测子步；7 次 worker 内部子步未知，按预留与历史无锁偏差累计计费 985／2,000。这里只覆盖受测原 source 和 direct 交集；不将规范化摘要用作其他资产的资格或改写历史原始 hash。

### 6.16 Position 自动 source 工作目录的所有权

输入 `e1ee58d8`。Position 旧入口未指定 `source_workspace` 时，原实现以 `mkdtemp` 在项目 workspace 创建目录，却未将其交给关闭 owner。现在由现有 source owner 分配自动临时目录，声明构建将其 cleanup 接入 `ReferenceTaskBinding.close_task_resources`：Env 关闭、半构造失败均回收该 Env 自有目录；若已有任务资源关闭器，保留其返回 receipt；若它失败，保留原错误并继续尝试清理。显式 `source_workspace` 仍归调用方，Env 不删除。该调整不改变 Position source、Controller 或 provider 准入，也没有把已存在历史目录批量清理。

本批最终生产 3 个文件 +45／−14，净增 31 行；测试 1 个文件 +74；项目文件无新增、删除或迁移。10 个双锁合同通过，覆盖自动目录正常／重复 close、构造失败回收、显式 caller 目录及原 source／动作合同。第一次测试 `position-owned-source-016-pure.log` 误将固定 Menagerie 资产目录当自动目录而失败，未修改资产；纠正检查器后 `position-owned-source-016-pure-v2.log` 的 10 项通过，原失败保留。随后 3 项与前组部分重叠的合同检查验证已有关闭 receipt 和原始错误保留，见 `position-owned-source-016-close-contract.log`。

真实 MuJoCo CPU Position direct 路线两次分别完成 reset→非零 step→第二次 reset→重复 close，各观测 5 子步，最后一次使用最终通用临时目录前缀，确认实际自有目录和 source snapshot 随关闭消失。后续仅补已有关闭器的返回值保留；本次 native 路径没有该已有关闭器，由最终纯合同验证新增分支。显式目录继续保留由上述合同和未改语义的旧 native 路线复用；无新 GeoPhys native 或其他 Position 组合声明。冻结计划、diff 和结果为 `cpu-run-plan-028.json`／`029.json`、`cpu-source-028.diff`／`029.diff`、`cpu-028-owned-position/`／`cpu-029-owned-position/`。累计监督 53 次，345 个可观测子步，7 次 worker 内部子步未知；含历史保守计费共 995／2,000。

### 6.17 维护者纠偏：退休旧 Position 注册

2026-11-12 重新启动目标，输入 `54be99e1`。维护者指定四个正式任务统一构建，过时诊断不再要求兼容，本版本诊断进入 `task_env/diagnostics/tasks/v2.1.1/`。本批移除 `panda-position-servo-candidate-v1` 的注册、旧输入解析和仅供该入口使用的自动 source workspace 分配；直接引用旧实现的历史诊断不再作为当前产品兼容目标。未删除 `physical_profile.py`：正式 PickCube 仍调用其中 Panda effort 构建，后续须迁到真实 owner，不能假称退出 candidate 依赖。早前 6.16 是当时的资源修复记录，不代表旧入口继续受支持。

本批生产 3 文件 +1／−115，净减 114 行；无新增、删除或迁移文件，无测试代码变更。当前记录和本页文档另计，不把文档当作生产代码。使用 `geochora` 环境 Python 做无 native 纯导入核对：四个正式 UID 均登记、旧 UID 从 registry 消失且 `make_env` 明确拒绝、PickCube 当前所需的 effort 实现仍可导入。此检查不运行构造／reset／step 或物理，既有真实运行证据的其他边界不变。

构建协议仍有 selected／component 分流；Robot 仍未统一从声明构建；Position 旧 builder／公共 Env 的候选专用方法仍待按正式 caller 清理。本批没有修改 provider／renderer adapter、时钟或提交，没有完成 E01～E04。历史诊断的旧 UID 检查不作为本次验收；不执行历史测试矩阵。

### 6.18 Panda effort 正式能力迁移与旧诊断退休

输入 `04bb926b`。正式 PickCube 不再从旧 Position candidate 目录导入控制实现：MuJoCo source adapter 负责重新计算 source 闭包并核验 Panda MJCF 传动，Panda Robot 负责已声明通道与直接 effort 控制绑定；PickCube 保留其 10 N 夹爪策略的受限条件。仅迁出正式调用的单主体 direct effort 逻辑，旧的 wrench fixture／split fixture 接线不复制进正式构造。删除旧 Position 诊断构建包的 8 个 Python 文件，其历史资产原样保留；共同 Position、effort 和 wrench 命令及 Runtime 实现没有因该退休删除。旧目录内源码可通过 Git 历史定位，不声称其诊断入口仍可运行。

本批生产 3 个文件修改、8 个 Python 文件删除，+105／−2479 行，净减 2374 行；Panda effort 相关代码经职责拆分和重写迁移，非整文件搬迁。新版本诊断增加 1 个测试文件，验证 Panda 力范围和手指传动篡改拒绝；2 份状态／实施文档修改。除以上变化，tracked 文件不变。构建协议中的两套解析和其余候选接线仍在，E01～E04 未完成；renderer、Runtime 时钟与推进实现本批未改。

双锁下正式 PickCube MuJoCo CPU direct 和 reset-selection 分别完成 reset／step／重置／close，旧包删除后 direct 再次通过；共 20 个可观测物理子步。direct 的 Artifact、source closure、主体与 Controller identity 均与此前同 seed 记录相同。首次运行未设置 GeoPhys source 的 Python 搜索路径，在物理启动前失败、0 子步；修正环境后复验，失败记录保留。新版本纯合同 `test_panda_effort_source.py` 为 1 passed；检查只覆盖声明传动，不代表真实物理效果。计划、冻结 diff 和各次结果位于 ignored `workspace/maintenance/v211_e00_e04_direction_reset_20261112_001/`，不把本轮结果外推到其他 provider、完整 Solution 或 renderer。

### 6.19 四正式任务配置解析收敛与 NutAssembly 主体缺口

输入 `0fad2f83`。四个正式 Task 的普通 mapping／YAML 现在均由同一配置解析器生成 `ResolvedSelectedConfig`，并将 Controller profile、episode horizon／seed／ignore_done 写入共同环境配置；Pendulum 与双轮车的 binding 消费同一构建请求。通用能力检查按声明限制 velocity-damped Controller 的 provider，Runtime preflight 在实际 typed effort 与 source 校验通过后识别 torque 能力。为保全简单主体既有 Isaac USD 路线，将原 materialization 中的 G05 source 准入检查提取为同一检查，供 preflight 和 materialization 共用；没有运行 Isaac 或扩大该 source 资格。纯 component／batch 构造仍存在，且不属于四任务普通配置统一的完成证明。简单主体原通过 `make_env` 顶层 provider／backend kwargs 的用法应迁移到 `config.execution`；没有为旧诊断调用保留专用转换。

本批生产 5 文件修改，+106／−41 行，净增 65 行；source 准入检查归位涉及重写迁移，未按整段删除计算。新增 3 个版本诊断文件（183 行）：正式 CPU 短程检查、四任务配置等价与能力拒绝检查、Isaac source 准入边界检查。无生产文件新增／删除；2 个实施状态文档更新。生产检查不再按 Task 判断选哪个配置 codec，但旧 component 工厂及其他未迁 caller 仍存在；Robot／Controller 真实构建链仍未统一，E01～E04 不关闭。

版本诊断纯检查 8 passed。MuJoCo CPU 下 Pendulum、双轮车、PickCube 分别通过正式配置构造、reset、非零 step、二次 reset 与重复 close；最终源码对应运行共 55 个可观测子步。此前 Pendulum 首次两次 preflight 因共同 Runtime 能力表漏列已验证的 torque 绑定而拒绝，均为 0 子步；修复后复验通过，失败保留。NutAssembly 正式配置可解析、环境可构造，但短程检查在调用 `env.robot` 时发现现有 source 没有 Position subject binding，故在物理推进前失败、0 子步；不能将它记作四主体共同构建通过。需迁移 NutAssembly 实际 Robot 声明及控制绑定，而非为测试伪造 RobotRuntime。总计本批观察 110 个物理子步，全部锁释放；source/控制变动的 GeoPhys、Isaac 和 renderer 尚未复验，Isaac 仅纯准入边界检查。记录、失败回执、冻结 diff 和各次原始结果位于 ignored `workspace/maintenance/v211_formal_config_20261112_001/`。

### 6.20 NutAssembly 进入共同 Robot source 编译

输入 `e521c5de`。将 PickCube 原有 Robot source 组合流程从任务专有接线移到共同声明、source composer 和 reconstruction owner；NutAssembly 声明自己的桌面／nut／peg 实体及 Panda 默认选择，MuJoCo CPU 通过同一个 composer 编译真实 Panda subject、Controller 绑定和 resource writers。构造、普通 reset、执行切换重建及隔离 worker 使用同一组合入口；失败时释放新 source receipt。PickCube 原任务中的组合闭包和重复身份写入已删除。MuJoCo source adapter 的名称和分派不再依赖 PickCube，但替换装配仍保留其当前受支持能力范围。

本批生产 7 文件修改，+117／−105 行，净增 12 行；原 PickCube 组合逻辑按职责重写迁移，非整文件搬运。版本诊断修改 1 文件（+17／−3），新增 1 个隔离 worker 诊断文件（45 行）；2 个状态／实施文档修改，无生产文件新增或删除。NutAssembly 的 MuJoCo source 实际带 Position subject binding，Env Robot 和 Runtime source 使用同一绑定；不是仅补 facade。当前仅 MuJoCo CPU 有此 source 组合 adapter，GeoPhys／Isaac 的对应主体声明和四任务完整共同构造仍待实现；renderer 未改，E01～E04 不提前结案。

MuJoCo CPU 下 NutAssembly 单个 caller-owned Solution interval、PickCube R3、一体及装配主体、二次 reset 和 close 均通过；检查验证 Env Robot 的 subject 与 Runtime source binding 相同。NutAssembly 首轮在已推进 5 子步后，由检查脚本错误传入 seed 31 导致第二次 reset 拒绝；改为该任务固定 seed 19 后通过，失败和原始输出保留。总计本批进程内观察 30 个物理子步；PickCube 和 NutAssembly 隔离 worker 各完成 reset／一个 interval／二次 reset／close，worker 内部子步未直接观测，各保守预留 50，所有锁释放。新版本纯检查 8 passed。此结果不是完整 Solution 成功，也不外推 GeoPhys／Isaac／renderer。冻结 diff、计划和原始结果在 ignored `workspace/maintenance/v211_robot_composition_20261112_001/`。

### 6.21 GeoPhys 与 MuJoCo 共享已有 Robot 引用声明

输入 `987afe84`。将一体 Panda 的已有 source 引用组合从 MuJoCo 专属 composer 拆到共享 source 组合 owner；Robot 自己编译 Panda subject 与 Controller binding，MuJoCo 及 GeoPhys 共同校验 source、recipe 和 intent。GeoPhys adapter 基于实际已解析的关节／actuator 映射核对资源归属并发布 source reference build receipt；不将合成声明当作 native 映射证据。装配 Panda 的 source 替换仍只在已支持的 MuJoCo adapter，Isaac source 仍待迁移；E01～E04 未接收。

生产 5 文件修改，+156／−76 行，净增 80 行；部分代码从 MuJoCo composer 重写迁至共享 source 和 Robot owner，迁移单列，不按整体删除计算。版本诊断 1 文件 +7／−1，2 个状态／实施文档修改；无文件新增、删除。adapter 不再因 GeoPhys CPU 缺少一体 Robot composer 退回无主体路线，但其他未支持组合没有扩大。

最终源码下，PickCube 与 NutAssembly 在 GeoPhys CPU 和 MuJoCo CPU 的隔离 worker 各完成 reset、一个控制 interval、第二次 reset 和 close，NutAssembly 使用 caller-owned Solution；四条受测路线均有 Robot subject binding，所有锁释放。另有先前一轮相同四条成功，以及首个 GeoPhys 构建后因缺少 reference receipt 而在 reset 阶段失败；worker 内部物理子步均未直接观测，9 次运行每次保守计费 50 子步，不以计费值冒充观测。第一次 MuJoCo 对照误沿用了标注 GeoPhys 的计划文件；其输入身份和实际 provider 见独立结果，后续已按 MuJoCo 专用计划及最终计划重跑。版本纯检查 8 passed；没有运行完整 Solution、Isaac 或 renderer。冻结 diff、计划及原始结果在 ignored `workspace/maintenance/v211_geophys_subject_20261112_001/`。

### 6.22 简单主体共享 effort 构建

输入 `7c143ae9`。Pendulum、双轮车各自的 Robot 声明自身源内根、受控关节、writer、通道和完整状态关节顺序；共同 physical control owner 从声明和 Scene 编译 Assembly、选择 Controller、绑定状态要求并生成 `PhysicalControlExecutionV1`。两个任务的 source 构建不再各自重复创建 Assembly、Controller 和执行对象，Task 不再传入关节路径／writer 进行特定接线。关节力范围、左／右顺序、Controller 物理语义及 source／Artifact 身份检查保留。两任务仍各自构造 Scene 和 source，下一步须继续核对其 Robot／provider 职责，不能将本批当成四主体全部统一。

生产 5 文件修改，+76／−77 行，净减 1 行，原有 Assembly／Controller 执行组装按声明重写到共同 owner；无生产文件新增、删除或整文件搬迁。版本诊断 1 文件 +19／−13，2 个状态／实施文档修改。共享构建器不按 Task、provider 或 renderer 名分流；adapter 的原生 source 映射和 renderer 未改。

MuJoCo CPU 下两主体 direct 和 velocity-damped 各完成 reset、非零 step、重复 reset 和 close，4 条运行共实测 100 个物理子步；direct 两条的 Robot subject 与 Controller identity 和上批同配置记录相同。GeoPhys CPU 的两主体 direct 路线也各完成相同行为；其内部物理子步未直接观测，各按 50 子步保守预留。首次 GeoPhys 命令未指定进程内解释器，preflight 拒绝、未启动物理；修正正式配置后复验通过，失败记录保留。版本纯检查 8 passed；所有锁释放。本批未实测 Isaac、renderer 或完整 Solution，保留原有界证据而不外推。计划、冻结 diff、原始结果在 ignored `workspace/maintenance/v211_subject_effort_20261112_001/`。

### 6.23 简单主体 Scene 声明归 Robot

输入 `568d8739`。Pendulum 与双轮车的内联 MJCF、主体 frame／joint／actuator 拓扑和 SceneDefinition 分别归各自 Robot；任务构建使用同一 Robot 实例声明场景并交给已有主体 effort 构建器，移除两个 task physical 文件中的独立 `_scene`。Task 仍负责自身任务 Artifact、reset 和 source 编译；这一步没有消除 provider 分流，也没有证明四主体已走完全一致的 source 构建链。

生产修改 6 个文件，+156／−141，净增 15 行，文件数无增减；两段内联 XML 和 Scene 声明为职责迁移，不能把迁移行当成新功能或精简成果，另有调用与 imports 调整。测试／诊断文件无改动，文档修改两份，项目 tracked 文件数不变。Robot 自身声明仍有不同拓扑，属于主体差异；目前尚没有完整统一的场景组合器。renderer、clock、提交与 provider adapter 本次未修改。

同一进程将旧 `_scene` 与新 Robot 声明分别按无 revision 和指定 revision 比较，四组 SceneDefinition 与 identity hash 均一致；内联 XML 内容亦未改动。第一次在移除旧模块 imports 后重跑比较时检查脚本缺少 `PoseWorld`，未启动物理；向比较命名空间补入原 artifacts 符号后通过。正式 Pendulum／双轮车 MuJoCo CPU 均完成 reset、非零 action、第二次 reset 和 close，各 25 个可观测子步。版本诊断 8 项纯合同通过。计划、冻结 diff、比较结果与运行记录位于 ignored `workspace/maintenance/v211_robot_scene_20261112_001/`。此前 GeoPhys CPU 的对应有界证据仍可作为历史参考，场景与内容身份一致，但本批未重跑 GeoPhys；Isaac 和 renderer 同样未重跑。E01～E04 仍未全部完成，不以本批为四主体统一或 adapter 全面接收。

### 6.24 简单主体按声明共同编译 source

输入 `c1f11e60`。Pendulum／双轮车 Task 不再各自实现 MJCF 电机验证、关节及 body 映射、source closure 和 provider source 分支：新的 Runtime source 编译器读取 Robot 的 XML、Scene articulation 和受控关节声明，验证 actuator 名称、关节、齿轮比及力矩范围，再构造相应 RuntimeSource；Isaac 的既有受限 USD source 准入仍由 Isaac source owner 执行。相同 Robot 实例仍交给共同主体 effort 构建器。Task 继续负责各自的语义、reset 和 Artifact；没有声称两个 tabletop Task 已使用此 source 编译路径，renderer、clock 与控制提交本批未改。

生产新增 1 个共同 source 编译器文件（93 行），修改 4 个文件 +23／−111，合计 +116／−111，净增 5 行；电机验证、provider 映射及闭包构造为重写迁移，不能将搬迁行计算为新增功能。新增 1 个版本诊断文件（45 行），修改 2 份文档；项目 tracked 文件净增 2，未删除或移动文件。共同构建去掉两个任务中的相同决策，但完整四任务 source 统一和 Panda 路线仍待后续，E01～E04 不因此关闭。

两个任务分别在 MuJoCo CPU、GeoPhys CPU 完成 reset、非零 action、第二次 reset 和 close；MuJoCo 各观测 25 子步，GeoPhys 内部子步未观测，按计划各保守预留 50。MuJoCo 新旧结果中的 Scene identity、reset sample、Robot／Controller identity 和单步奖励一致。10 项纯合同通过，新增检查覆盖两任务 Isaac body／joint 映射与齿轮篡改拒绝，使用 stub，不代表 Isaac 实际运行；原有 Isaac 有界证据不自动扩展到本批代码。计划、生产冻结 diff 和运行结果在 ignored `workspace/maintenance/v211_declared_source_20261112_001/`；本批未实测 Isaac 或 renderer。

### 6.25 Controller 规范字段直达配置解析

输入 `1e651adb`。四个正式任务的普通配置直接从 `controller.profile_id` 解析 Controller 选择，不再先转换到 `control.profile_id`、再塞入 `task.controller_profile`。明确拒绝这两个旧位置及顶层 `controller_profile`；其他 Controller 参数仍由原有能力检查约束。Resolved 配置复解析和 PickCube reset 切换也使用同一规范字段。PickCube 示例和本版本装配 Panda 诊断已迁移；外部旧调用应把选择改写为 `controller: {profile_id: ...}`。component-only 构建仍有自己的内部 codec，其存在不能作为四任务完整构建统一的证据。

生产配置与 reset 修改 2 文件 +12／−22，净减 10 行；示例 1 文件 +1／−1；版本诊断 2 文件 +45／−1；本记录及当前状态文档 2 文件修改。无文件新增、删除或迁移，tracked 文件净变化为 0。provider、renderer、时钟、提交与 source 不因本批改变；历史 controller 输入及其诊断不再作为兼容目标。

四正式任务以及 PickCube 装配 Panda 在 MuJoCo CPU 完成构建、reset、非零动作／Nut 单个 Solution interval、再次 reset 和 close，依次观测 5、5、5、25、25 子步（合计 65）；其中装配 Panda 以 `controller.profile_id=r1_split` 指定选择。18 项版本纯合同通过，覆盖四任务 mapping／YAML／Resolved 配置一致、显式 profile、旧位置拒绝和 reset 切换候选；并非完整 Solution 验证。计划、冻结 diff 和结果在 ignored `workspace/maintenance/v211_controller_config_20261112_001/`。其他 provider、renderer 本批未重跑。E01 的其他旧别名与 component 结构仍须对账，E00～E04 均不以本批声明完成。

### 6.26 正式执行配置和直接 caller 迁移

输入 `fb8f4eec`。正式配置不再接受顶层 `provider`、`backend`、`horizon`、`source_delivery_manifest`，分别使用 `execution` 和 `episode` 下的规范字段；移除对应别名转换。迁移轨迹录制／规划、录制示例、通用环境脚本和简单主体单步示例；移除无调用者且已经失效的旧 PickCube 配置 helper。修复上一批漏查的 Harness：其生成的 `task.controller_profile` 已改为 `controller.profile_id`。通用环境脚本对四个正式 UID 使用同一种配置结构，其他历史 component 环境仍有独立入口。

生产配置及脚本修改 6 文件 +15／−38，净减 23 行；示例 2 文件 +4／−2；版本诊断 1 文件 +41；本记录和当前状态文档 2 文件修改。无文件新增、删除、迁移，tracked 文件数不变。27 项版本纯合同通过，覆盖旧字段拒绝、四任务示例配置以及 Harness 输出交给真实配置解析器；Harness 此处未实际执行完整运行。四任务 MuJoCo CPU 各完成 reset／单 interval／第二次 reset／close，共 60 个观测子步，Nut 为单个 Solution interval；结果、计划和冻结 diff 位于 ignored `workspace/maintenance/v211_formal_callers_20261112_001/`。运行后只对 `_bootstrap.py` 移除一个文件末尾空行，纯合同在最终内容上重跑通过；冻结 diff 保留运行时精确状态。

本批未更改 provider／renderer、时钟或提交，其他 provider 和 renderer 未重跑。Pendulum 的旧 RGB 示例仍传入 component 的 `runtime`／`render` 配置，不能在当前正式配置入口使用；其渲染参数迁移留待渲染配置整理，不将它描述为已迁移。仍需审计其他正式 caller、component 结构和四主体共同构造，E01～E04 未完成。

### 6.27 单层与嵌套已有主体的 effort Assembly 编译

输入 `780a33bf`。Panda direct effort 与 Pendulum／双轮车的已有主体 effort 现在使用同一个 Assembly 编译入口：读取 Robot subject 和关节声明，按声明构造单层或嵌套 logical assembly，再交给共同的主体绑定编译器。Panda 的 tendon 力分配、原有嵌套身份及不同 Controller 语义保留；简单主体仍按各自通道声明处理。移除三个 Robot 上只由历史诊断调用的 `controlled_subject` 旧反向构造方法，正式路径使用先声明再编译。Position 的主体与控制编译没有改为该 effort 路径，四任务的完整主体机制仍未收口。

生产修改 4 文件 +45／−79，净减 34 行；其中 Assembly 重写归并到 Runtime，删除的是重复构建及旧反向方法，不能把迁移行直接当作删除效果。版本诊断修改 1 文件 +4／−2，增加正式 PickCube Panda effort 短程选项；本记录及当前状态 2 文件修改。无文件新增、删除或迁移，tracked 文件数不变。renderer、时钟、Position 提交及 source adapter 未改。

MuJoCo CPU 的 PickCube Panda direct effort、Pendulum、双轮车各完成 reset／非零 action／第二次 reset／close，分别观测 5、25、25 子步；两个简单主体 GeoPhys CPU 同样通过，内部物理子步未观测，按各 50 预留。MuJoCo 新旧运行的两个简单主体 Scene、reset sample、Robot／Controller identity 相同；Panda effort 的 Scene 和 Controller identity 与此前直接路线相同。27 项版本纯合同通过；不声称本批验证了每个绑定 hash、完整 Solution、Isaac、renderer 或 Position 路线。冻结 diff、计划和结果在 ignored `workspace/maintenance/v211_subject_assembly_20261112_001/`；E01～E04 仍未完成。

### 6.28 Position 与 effort 共用已有主体成员声明

输入 `c1ce191e`。Position Panda 和 Panda／简单主体 effort 不再各自从 Scene 实体手工拼接 owner 与关节引用；共同 Assembly resolution owner 从实体及 joint path 声明生成相同成员。单层、嵌套结构仍由各自逻辑 Assembly 组合，Position 的 group／姿态控制合同和 effort 的传动／单位合同保留；这是共同主体构建的一步，不代表两种控制已被错误合并成一个语义，也不代表 E02 已完成。

生产修改 3 文件 +26／−26，净变化 0；成员构建代码经过重写归并，无新增、删除或迁移文件；诊断代码未改，文档修改 2 文件，tracked 文件数不变。provider source、renderer、时钟、动作提交未改。27 项版本纯合同通过；MuJoCo CPU 的 PickCube Panda effort／Position、装配 Panda、NutAssembly、Pendulum、双轮车分别完成 reset、非零 action 或单个 Nut Solution interval、再次 reset 和 close，共 70 个可观测子步。

与先前对应同 seed 路线对照，六种运行的 Robot／Controller identity、reset sample 及各自可用的 Scene 或 Artifact／source identity 一致；三条 Position 路线中记录的 binding identity 和 resource writers 亦包含在 Robot 对照中。首次自动对账错误地假设 Position boundary 包含 `scene_identity_hash`，未启动物理；改为比较其实际提供的 Artifact 和 source 字段后通过。计划、冻结 diff、原始结果和对账在 ignored `workspace/maintenance/v211_common_members_20261112_001/`。GeoPhys、Isaac、renderer 本批未重跑，不外推完整 Solution 或后续事件接收。

### 6.29 退休 Position 诊断构造旁路

输入 `6c3db21d`。公共 Env 移除已无正式调用者的 `from_position_candidate`、`from_leaf_position_candidate`，以及仅由它们使用的 candidate 执行选择解析、临时动态类型和 leaf 构造开关；共同 Task binding 构造去掉只供这些入口使用的参数。Position Controller 与正式 PickCube／NutAssembly 的 Position 路线保留，LIBERO 仍实际调用的 mixed-control 构造也保留。旧 leaf 计划在控制／记录模块中的剩余内部逻辑还需继续审计，本批不声称整体删除。

生产修改 2 文件 +5／−122，净减 117 行；无文件新增、删除或迁移，tracked 文件数不变；版本诊断未改，实施与当前状态 2 文档修改。生命周期更直接地由正式配置和共同 Task binding 进入；provider、renderer、clock 和控制提交代码未改。27 项版本纯合同通过。

第一次冻结版本中，四任务的六条 MuJoCo CPU 短程通过（70 个可观测子步）；随后去掉共同构造上已无用途的两个候选专用参数，并按最终 diff 再次运行同六条路线，全部通过（再 70 个子步）。每条均完成 reset、非零 action 或 Nut 单个 Solution interval、再次 reset 和 close，两个版本合计 140 个观测子步。计划、两个冻结 diff 和各结果在 ignored `workspace/maintenance/v211_retire_position_constructor_20261112_001/`。GeoPhys、Isaac 和 renderer 未在本批复跑，E01～E04 未完成。

### 6.30 退休 leaf 控制分派并修复 worker 配置投影

输入 `ec114139`。四个正式 Task 没有生成旧诊断 leaf plan；移除 selected Controller 的 leaf 准入、leaf Runtime builder、Env 内的 leaf interval／记录入口、lifecycle 分派及对应预检分支。显式传入旧 leaf plan 将被拒绝。装配 Panda 仍使用的主体配置声明和一般 Position／effort 合同保留；记录器、观察与底层 provider 中其他历史 leaf 代码还未整体清理。

本批首次隔离 worker 测试揭示此前规范配置迁移遗漏：记录配置投影仍将 Controller profile 写入已退休的 `task.controller_profile`，worker 在重建解析阶段失败。将该投影改为 `controller.profile_id`，并保留 Robot、Controller 参数与 episode 的正式重建字段；版本纯合同增加投影到实际解析器的往返检查。首次失败及原冻结 diff 保留，不称其通过。

生产修改 8 文件 +34／−223，净减 189 行；版本诊断 1 文件 +21；本记录与当前状态 2 文档修改。无文件新增、删除或迁移，tracked 文件数不变。六条 MuJoCo CPU 进程内路线在首版 diff 下各完成 reset／非零 action 或 Nut 单个 Solution interval／再次 reset／close，合计 70 可观测子步；后续变动仅为记录配置投影及对应测试。最终 diff 下 PickCube 与 NutAssembly MuJoCo 隔离 worker 均通过相同生命周期，worker 内部子步不可观测，各保守计费 50；首次失败也按预留保守计费 50。28 项版本纯合同在最终 diff 下通过。

本批未重跑 GeoPhys、Isaac、renderer 或完整 Solution。leaf 低层代码及非本轮触及的观察／记录分支尚未完成审计；E01～E04 仍未完成。两个冻结 diff、计划、失败与成功结果见 ignored `workspace/maintenance/v211_retire_leaf_dispatch_20261112_001/`。

### 6.31 退休 leaf 观察／记录分支并修复记录投影

输入 `4e0d8e63`。移除已无法被正式控制选择产生的 leaf 专属观察、episode-end、记录及 readback 分流；正式 Position 双主体和装配 Panda 的实体观察仍由各自声明的实际 Controller／subject 生成。历史 leaf H5 读取器不因产品构造入口退休而删除。共同 Env 的 preflight／记录不再携带无生产者的 leaf 状态。首次记录验证发现 typed `ObservationSchema` 无法直接进入协调器 JSON 收据，现复用现有 portable metadata 投影，保留字段后再计算完整性 hash。

生产修改 5 文件 +46／−446，净减 400 行；版本诊断 2 文件 +49／−9；实施和当前状态 2 文档修改。无文件新增、删除或迁移，tracked 文件数不变。任务／Controller 语义及 provider、renderer、clock、提交实现未改。29 项版本纯合同通过，包括 typed schema 收据投影。

MuJoCo CPU 的 PickCube、一体与装配 Panda、NutAssembly、Pendulum 和双轮车短程通过；其中一体与装配 Panda 和 NutAssembly 各完成单 interval 记录写入及读回（前两条 canonical mapping 精确、Nut streaming 字节精确），合计 65 可观测子步。PickCube reset-scoped joint effort 路线另完成 1 interval 的 H5 v3 结构化记录、1 transition／2 observations 读回及第二次 reset（5 子步）。这不是完整 Solution 或整段轨迹资格。纯测试在最后诊断变更后重跑；相关生产代码与前述成功运行相同。

失败按原样保留：首次记录在首步前因 typed schema JSON 投影失败，修复后一次探针错误地对 legacy scalar route 调用不支持的 `stop`（5 子步），调整为正确的 `finish_recording` 后通过；物理记录首次未启用 reset-scoped selection 而被明确拒绝（0 子步），随后启用 selection 又发现 reset 前 `env.robot` 不可用（0 子步）。最终记录验证显式记录该 Robot 缺口，没有将其计作主体统一通过；此缺口属于 E02 后续工作。本批实际观测合计 75 子步。所有计划、冻结 diff、失败及成功结果位于 ignored `workspace/maintenance/v211_retire_leaf_observation_20261112_001/`。GeoPhys、Isaac 和 renderer 本批未重跑，E01～E04 仍未完成。

### 6.32 reset-scoped 物理选择的 Robot 声明与提交

输入 `71547bb2`。reset-scoped 选择 owner 接收已经编译的物理主体声明并暴露已提交选择；RobotRuntime 使用该声明在第一次 reset 前提供真实 subjects，此时 `controller=None`、`controllers=()`，不声称 Controller 已提交。成功 reset 后 Robot 使用实际提交的 physical execution subjects 和 Controller；无效选择在提交前拒绝，已提交 Robot 不变；成功切换后视图指向新提交 Controller。该实现消费原有真实声明和 reset 事务，不启动第二个 Runtime，也不在观察层伪造主体。当前此路线的 `env.controller` 仍是既有 Position 观察／兼容 owner，Robot 对外显示实际 physical Controller；两者职责与进一步收敛仍须 E02／E04 对账。

生产修改 4 文件 +23／−6，净增 17 行；版本诊断修改 1 文件 +38／−15；本记录与当前状态 2 文档修改。无文件新增、删除或迁移，tracked 文件数不变。provider、renderer、source、时钟和提交接口未改；29 项版本纯合同通过。

MuJoCo CPU 的 reset-scoped PickCube 先显示声明而无 committed Controller，第一次 reset 后以实际 joint Controller 非零推进并完成 H5 v3 记录读回；错误 Controller 选择保持原 Robot 和 spec，第二次 reset 切换至 r3-pose 后，新 Robot 指向新 Controller 并实际非零推进。该最终运行观测 10 子步。先前版本完成相同选择／记录但仅对切换后的身份做检查（5 子步）；四正式任务和装配 Panda 的五条普通短程另通过（65 子步），本批共 80 观测子步。计划、冻结 diff 和结果在 ignored `workspace/maintenance/v211_reset_robot_20261112_001/`。GeoPhys、Isaac、renderer 未在本批重跑；E01～E04 仍未完成。

### 6.33 退休 PickCube 物理诊断 UID

输入 `43892ba1`。移除 `pickcube-physical-candidate-v1` 和 `pickcube-isaac-physical-candidate-v1` 的注册、导出及各自旧输入翻译器；不再为旧 `source_workspace`、`drive_mode`、`control_kind` 等诊断配置维护两套构造入口。正式 `pick-cube-p16-reference-v1` 继续使用实际物理 binding、source 和 Controller 能力；实现文件目前仍含候选命名及任务内 source／profile 职责，不能称为已完成 E09 或四主体完整统一。

生产修改 3 文件 +1／−85，净减 84 行；版本诊断 1 文件 +7，实施和当前状态 2 文档修改。无文件新增、删除或迁移，tracked 文件数不变。31 项版本纯合同通过，确认旧 UID 不再注册；MuJoCo CPU 正式 PickCube 的 Position、direct effort 和 reset-scoped joint／r3 切换路线通过短程，合计 20 个观测子步；后者包括 H5 v3 单 interval 写入读回与切换后实际推进。正式 Isaac 物理 binding 工厂仅做纯导入检查，未启动 Isaac；本批未改 provider／renderer、clock 或提交，不外推其他 provider 或完整 Solution。计划和结果在 ignored `workspace/maintenance/v211_retire_pickcube_uid_20261112_001/`。`env.controller` 与实际 reset-scoped physical Controller 的职责仍待继续收敛，E01～E04 未完成。

### 6.34 PickCube 任务场景直接组合 Robot 声明

输入 `c98f35c5`。PickCube MJCF 物理路径不再先构造 Isaac 专用场景、再通过映射和硬编码资产 ID 替换 Robot 与 frame；共同任务场景组合接收已声明的 Robot 场景、资产及 source frame／joint 名称，直接形成任务物体和主体组合。Isaac 路线继续传入原有特定 USD 资产声明，MJCF 路线传入自己的 Robot 声明。公共组合函数不选择 provider 或固定 Robot UID；具体 source 名称仍由调用方给出，完整 source lowering 和 adapter 整理属于后续工作。

生产修改 2 文件 +30／−41，净减 11 行；无文件新增、删除或迁移，tracked 文件数不变；版本诊断未改，实施和当前状态文档 2 文件修改。共享任务实体组装被重写复用，迁移行不作为删除成果；provider／renderer、clock 和控制提交代码未改。

实际解析的 MJCF 与 Isaac 两种 Scene，新旧完整 mapping 和 identity 均一致；此项没有启动物理 SDK，但读取并解析了 Panda 源资产。MuJoCo CPU 的 direct effort 和 reset-scoped joint／r3 切换各完成真实短程，后者包含 H5 v3 单 interval 记录读回及切换后的实际推进；首版和仅调整共享函数 Robot 参数命名后的最终版各 15 子步，合计 30 个可观测子步。31 项版本纯合同在最终代码通过。Isaac 只核对 Scene 声明，未重跑其物理或 renderer，也不声称 source／adapter 全面统一。计划、diff、场景对照和结果在 ignored `workspace/maintenance/v211_pickcube_scene_20261112_001/`；E01～E04 仍未完成。

### 6.35 简单主体 Task Artifact 共同编译

输入 `484deadd`。Pendulum 与双轮车不再各自复制 Entity、初始化、joint-effort action 和 Artifact 编译接线；Task 提供自身身份、成功语义和 timebase，共同 Task Source 编译器从 Robot／Scene 读取真实实体、资产、frame 和 joint 顺序，并在编译前拒绝 Robot 与 Scene 的关节不一致。两任务仍各自负责 reset 和奖励语义；新入口目前覆盖这两种已有主体的 joint-effort 声明，不宣称 tabletop Task 已使用同一专用入口。顺带移除任务文件中不再使用的 Isaac source imports，实际 provider source 仍由 Runtime source owner 处理。

生产修改 3 文件 +45／−42，净增 3 行；版本诊断修改 1 文件 +9／−1；实施和当前状态文档 2 文件修改。无文件新增、删除或迁移，tracked 文件数不变。32 项版本纯合同通过，包括 Robot／Scene 关节不一致拒绝。无 revision 和指定 revision 两种情况下，两任务的 Task Source identity、Artifact identity 和完整 mapping 与输入版本相同。

两任务 MuJoCo CPU 均完成 reset、非零 action、第二次 reset 和 close，各观测 25 子步；与上轮同 seed 的 Robot、Scene、reset sample 身份及单步奖励一致。GeoPhys、Isaac、renderer 本批未重跑；两种 revision 的静态身份一致可作为评估旧有界证据的依据，不能替代本批 native 复验。计划、冻结 diff 和对照位于 ignored `workspace/maintenance/v211_simple_task_declaration_20261112_001/`。E01～E04 仍未完成。

### 6.36 简单主体 joint-effort reset 合同归并

输入 `0607109d`。Pendulum／双轮车继续各自定义采样分布和 joint 值，Task Source owner 统一将这些值编译为 source-bound joint-effort ResetSample／ResetPlan，包括随机样本 identity、初始化顺序和物理控制策略。两个 Task 文件不再分别复制相同 reset 合同；该入口明确限定 joint-effort，不声称已经替代 tabletop 的 reset 语义或全部 Env 生命周期。

生产修改 3 文件 +28／−33，净减 5 行；版本诊断无改动，实施和当前状态文档 2 文件修改；无新增、删除或迁移文件，tracked 文件数不变。相同显式采样输入下，两任务的完整 reset plan mapping 与 identity 均与输入版本一致。MuJoCo CPU 两任务均完成 reset、非零 action、重复同 seed reset、无 seed RNG 续采和 close，各观测 25 子步；样本 identity、RNG 序列、Robot identity 和单步奖励与前次相同。32 项版本纯合同通过。

native 验证后只将共同函数及两个调用点改名，明确其 effort 范围；最终代码重新通过纯合同及两任务 reset plan 完整 mapping／identity 对照，未重复物理运行。GeoPhys、Isaac 和 renderer 本批未重跑；provider source、clock 和提交未改。计划、运行时冻结 diff 和对照在 ignored `workspace/maintenance/v211_joint_reset_20261112_001/`；E01～E04 仍未完成。

### 6.37 简单主体共同 Task／Robot 构建编排

输入 `f3b01851`。Pendulum 和双轮车的 Task 文件不再分别编排 Robot 实例、Scene、Artifact、source、Controller、physical execution 和 ReferenceTaskBinding；二者提供 Task 身份／语义、Robot factory、reset 采样和动作合同，由共同 binding owner 按相同顺序构建。动作 schema 与空间从各自现有动作合同生成，source 原始 hash 来自 Robot 声明；任务的奖励、观测和采样不合并。两个任务的共同化已经发生在实际构建步骤，不仅是运行后 Robot 视图；tabletop 仍有不同的 Position／source 构建路径，不能因此宣称四任务已统一。

生产修改 3 文件 +110／−130，净减 20 行；共同编排涉及职责重写迁移，非整文件搬迁；版本诊断未改，实施和当前状态文档 2 文件修改。无新增、删除或迁移文件，tracked 文件数不变。source／provider 的原有校验和 Runtime 物化仍由已有 adapter 执行，renderer、clock 和动作提交代码未改。

MuJoCo CPU 下两任务 direct 和 velocity-damped Controller 各完成 reset、非零 action、同 seed 重置、无 seed RNG 续采和 close，共 100 个可观测子步；同 seed 原路线的 Robot／Controller、reset sample、RNG 序列和单步奖励一致。GeoPhys CPU 两任务 direct 路线同样完成短程并与前次对应身份及结果一致，内部子步未观测，各保守预留 50。32 项版本纯合同通过。Isaac 和 renderer 本批未重跑；计划、冻结 diff 和对照在 ignored `workspace/maintenance/v211_shared_effort_build_20261112_001/`。E01～E04 仍未完成。

### 6.38 四任务 Robot 身份与实例创建入口

输入 `1e1f7b81`。引入只要求主体身份及实际声明能力的共同 `RobotComponent`，原有 AgentComponent 保留其旧 source-component 能力合同；Pendulum 与双轮车注册进现有 Robot／agent registry。两个简单任务不再持有并直接调用具体 Robot class factory，而是按 `robot.uid` 使用与 Panda 相同的 registry 创建实际 Robot。正式配置允许各简单任务显式选择自己的 Robot UID，并按 Task 声明拒绝不同主体；默认选择保持原有行为。简单主体无需伪造 Panda 的 asset manifest、gripper 或末端接口。

生产修改 9 文件 +30／−19，净增 11 行；版本诊断修改 2 文件 +26／−1；实施和当前状态文档 2 文件修改。无文件新增、删除或迁移，tracked 文件数不变。入口统一发生在实际 Robot 实例创建；Position 与 effort 的 source 编译和 Controller 绑定仍各有能力合同，不据此声称四任务构建全部统一。provider／renderer adapter、clock、提交和 native 映射未修改。

37 项版本纯合同通过，覆盖四任务显式 Robot UID、registry 创建、配置重解析及跨任务主体拒绝。四任务及装配 Panda 均以显式 `robot.uid` 在 MuJoCo CPU 完成构造、reset、非零 action 或 Nut 单个 Solution interval、第二次 reset 和 close，共 65 个可观测子步；同 seed 与此前默认选择的主体／Controller、reset、可用的 Scene 或 Artifact／source identity 及单步奖励一致。GeoPhys、Isaac 和 renderer 本批未重跑，旧有界证据不扩大；计划、冻结 diff 和对照在 ignored `workspace/maintenance/v211_robot_registry_20261112_001/`。E01～E04 仍未完成。

### 6.39 公开 Controller 与实际提交者对齐

输入 `533655f0`。对于 reset 时选择物理 Controller 的正式路径，`env.controller` 现在与 `env.robot.controller` 指向实际已提交的 physical Controller；首次 reset 前两者均为 `None`。无效选择不改变已提交对象，成功切换后两者同时指向新对象。用于 Position 状态投影、构造及历史记录格式的内部对象由内部选择和 `position_profiles` 明确引用，不再冒充公开的动作提交 Controller；本批未删除这些仍在用的投影能力。公开属性只读，避免外部赋值造成伪状态。

生产代码修改 5 文件 +51／−42，净增 9 行；版本诊断修改 1 文件 +5／−5；本记录和当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1364；代码改写中的引用迁移不计为文件删除或代码精简。配置解析、provider／renderer adapter、source、clock 与实际提交实现未改，四任务完整共同构造和内部 Position 投影进一步归位仍未完成。

37 项版本纯合同通过。MuJoCo CPU 的四任务短程以及装配 Panda 通过；可切换 PickCube 在最终代码上完成实际 joint 动作、H5 写入读回、无效选择拒绝、切换至 r3-pose 后再次推进，确认 Env／Robot／已提交执行为同一 Controller。首轮四任务及可切换路线观测 70 子步；只移除可写 setter 后最终代码另观测 15 子步，合计 85。GeoPhys、Isaac 和 renderer 未在本批重跑，不外推完整 Solution 或其他 provider。运行计划、冻结 diff 与结果位于 ignored `workspace/maintenance/v211_controller_owner_20261112_001/`。E01～E04 仍未接收。

### 6.40 退休诊断 source_workspace 输入

输入 `0916cc99`。四个正式任务共同的配置解析不再接受历史诊断的 `execution.source_workspace`；PickCube 物理路径不再通过公开配置指定、复制或保留外部 source 目录。MuJoCo source lowering 直接消费现有受管快照，正式 binding 保持快照所有权直至关闭；配置对象、记录重建投影和 provider adapter 中为旧输入服务的字段及复制分支一并移除。该变更不移除真实 source 资产、校验或快照生命周期，也不改变 Isaac 的 delivery manifest 合同。

生产修改 5 文件 +11／−42，净减 31 行；版本诊断修改 2 文件 +18／−0；本文和当前状态文档修改 2 文件。无新增、删除或整文件迁移，项目 tracked 文件数保持 1364；删除的复制分支不涉及整文件搬迁。移除一项正式配置特殊输入和一个 source adapter 分支，未改变 Runtime 物理推进、时钟、renderer 或通用构造协议。

41 项版本纯合同通过，四个正式任务均拒绝旧字段。MuJoCo CPU 的 PickCube reset-scoped joint／r3 切换及 H5 记录读回、direct effort、普通 Position、Nut Solution 单 interval 均通过，共观测 25 物理子步；物理 source 在构造后存在、关闭后移除，重复关闭成功。GeoPhys、Isaac、renderer 和完整 Solution 本批未重跑，已有证据按具体影响保留；计划、冻结 diff 及结果在 ignored `workspace/maintenance/v211_retire_source_workspace_20261112_001/`。E01～E04 仍未接收。

### 6.41 固定 physical Controller 的公开归属

输入 `cc2526df`。上批对齐的是 reset-scoped 物理选择；再次审计发现固定物理 Controller 与 Position 投影并存时也会产生同样的公开身份偏差。现在 RobotRuntime 和 `env.controller` 对任何已声明 physical execution 均公开该 execution 的实际 Controller，Position 只保留内部状态投影角色；Position 单独控制路径仍公开原 Controller。此项修正已有实际 owner 的投影，不更换执行、clock 或控制提交机制。

生产修改 2 文件 +5／−0；版本诊断修改 1 文件 +8／−2；实施和当前状态文档 2 文件修改。无文件新增、删除或整文件迁移，tracked 文件数保持 1364。41 项版本纯合同通过；MuJoCo CPU 的固定 joint effort、可切换 joint／r3（含 H5 记录读回）、direct effort、Pendulum、双轮车完成真实短程，断言 Env、Robot 和实际 physical execution 的 Controller 对象一致，累计观测 70 子步。普通 Position、Nut 和装配 Panda 本批未改其 Controller 语义，使用本轮 6.39／6.40 对应受测证据；GeoPhys、Isaac、renderer 和完整 Solution 本批未重跑。计划及冻结 diff 位于 ignored `workspace/maintenance/v211_fixed_physical_owner_20261112_001/`。E01～E04 仍未接收。
