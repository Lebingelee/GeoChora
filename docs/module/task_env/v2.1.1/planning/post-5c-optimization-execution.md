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

### 6.42 Robot 提供 Task Artifact 主体声明

输入 `73d47118`。四个正式任务的 Artifact 主体声明现在消费 `RobotComponent.artifact_entity`：Panda 由注册的 Panda Robot 提供其固定资产、frame 和关节声明；Pendulum／双轮车由共同 Robot 合同从其自身 Scene 投影主体，并核对关节及资产。PickCube 的主体初态也改由注册 Robot 提供；NutAssembly 按任务声明的 Robot UID 获取主体。公共 Assembly compiler 中硬编码的 `panda_entity_declaration` 已移除。该变化发生在实际 Artifact 编译过程；tabletop 的 source、Controller 构建与两个简单任务仍未完全合流，装配 Panda 仍在后续 source 替换中形成实际嵌套主体，不据此声称 E02 完成。

生产修改 6 文件 +44／−34，净增 10 行；其中既有主体声明及验证职责重写迁到 Robot 合同，非整文件迁移；版本诊断修改 1 文件 +30／−0；本文和当前状态文档修改 2 文件。没有文件新增、删除或整文件迁移，项目 tracked 文件数保持 1364。provider／renderer 的 source、native 映射、clock 和提交接口未更改。四个 Task Artifact 的完整 mapping 与 identity 在相同输入下均与输入版本相同；代码来源身份发生变化，不能仅凭 Artifact 一致扩大旧运行证据。

45 项版本纯合同最终通过，包含四任务主体合同及 Robot／Scene 关节不匹配拒绝。新增测试首版将简单任务的 TaskArtifactV1 当成旧版 Artifact 读取，导致 2 项 AttributeError；改为检查 V1 的 Scene identity、关节绑定和初始化后通过。MuJoCo CPU 的 PickCube、NutAssembly、Pendulum、双轮车及装配 Panda 完成真实短程，共观测 65 子步。GeoPhys CPU 的 PickCube、NutAssembly 和 Pendulum 也完成短程，内部子步未观测，按每条 50 保守预留。Isaac、renderer 和完整 Solution 未重跑；历史有界结果只按具体代码与来源影响参考。计划、冻结 diff、前后 Artifact 对照及运行结果在 ignored `workspace/maintenance/v211_robot_artifact_20261112_001/`；E01～E04 仍未接收。

### 6.43 Runtime 直接消费 physical execution 声明

输入 `3f7ba60b`。移除 `ReferenceTaskBinding.physical_control_profile` 及 PickCube MJCF／USD、简单主体各自提供的取值回调；Env 从已编译 `physical_execution` 或 reset 已提交选择获取同一个对象，Runtime materialization、reset preflight、physical／sequence 提交及混合控制检查均消费这一声明。source、Controller、资源及 native 映射的既有准入检查保留；延迟获得动作合同的 binding 必须在编译后提供真实 `PhysicalControlExecutionV1`。构造 horizon 不再为旧物理回调例外放开超过 6000 的内部入口；四个正式配置在本次之前已限制为至多 6000。旧诊断直接传入该回调不再作为兼容目标。

生产修改 8 文件 +64／−73，净减 9 行；其中控制生命周期分支去除一层缩进，属于代码改写，不计为文件迁移。版本诊断修改 2 文件 +29／−1；本文与当前状态文档修改 2 文件。无新增、删除或整文件迁移，项目 tracked 文件数保持 1364。Task 少三处 physical execution 接线，Runtime 统一读取声明；未修改 provider 原生映射、renderer、clock 或实际物理推进算法，Position 与 physical 不同的控制语义保留。

46 项版本纯合同通过，包括缺失／伪造 physical execution 的编译拒绝。MuJoCo CPU 的四任务，以及固定 joint、direct effort 和 reset-scoped joint／r3 切换均完成短程，后者含 H5 记录读回；另外两次 direct effort 序列验证均推进 5 子步，最终检查生命周期 dispatch、一个已确认提交和 Controller 身份。累计 MuJoCo 实测 90 子步。GeoPhys CPU 的 Panda joint effort 与 Pendulum 短程通过，内部子步未观测，各按 50 保守预留。Isaac USD source、已编译动作合同和 Position 状态绑定完成静态检查，未启动 SDK；第一次检查因调用环境缺少 GeoPhys `scene` 模块路径而失败，补足 PYTHONPATH 后通过。Isaac／renderer 真实运行及完整 Solution 本批未复验。计划、冻结 diff 和结果位于 ignored `workspace/maintenance/v211_physical_execution_declaration_20261112_001/`；E01～E04 仍未接收。

### 6.44 tabletop Artifact 与 RuntimeSource 使用同一个 Robot 实例

输入 `2330f1c5`。PickCube 与 NutAssembly 的实际 reference 构建不再为 Artifact 的 Robot 声明和 RuntimeSource 分别从 registry 创建不同对象：构建时选择一次 Robot，该实例先提供 Artifact 主体声明，再进入 source 组件组合。共同 source compiler 能逐项接收已有组件并解析缺少的组件，部分提供时核对身份与 Task composition；完整提供的 benchmark 组件仍使用其原合同。简单主体的构建此前已将同一个 Robot 传给 Artifact 和 source 编译，此处没有宣称 tabletop 的 source／Controller 算法已与简单主体完全相同；装配 Panda 仍在 source 组合阶段替换默认 Panda。

生产修改 3 文件 +38／−21，净增 17 行，主要是共同 source 编译的部分组件解析与身份校验，以及在 tabletop 构建中传递同一实例；无整文件迁移。版本诊断新增 1 文件 +38／−0；本文与当前状态文档修改 2 文件。项目 tracked 文件数 1364 → 1365，净增 1，无文件删除。source 编译接口改变，provider 原生映射、clock、控制提交与 renderer 未改。

49 项版本检查通过，其中新增 3 项会读取真实 tabletop source 资产，核对 Artifact 声明使用的 Robot 与 RuntimeSource 的 Robot 为同一对象，并拒绝 foreign Robot；其余 46 项为既有版本合同。MuJoCo CPU 四任务、装配 Panda 和 PickCube direct effort 均完成短程，共观测 70 子步；与 6.42 同 seed 比较，主体、reset、可用 Artifact／Scene／source 身份及单步奖励相同，Nut Controller 身份按其源码绑定合同变化，其他比较路线 Controller 身份相同。GeoPhys CPU 的 PickCube／NutAssembly 短程通过，内部子步未观测，各保守预留 50。Isaac、renderer、完整 Solution 本批未重跑；计划、冻结 diff、身份对照及结果在 ignored `workspace/maintenance/v211_robot_source_instance_20261112_001/`。E01～E04 仍未接收。

### 6.45 R3 Controller 构造归控制 owner

输入 `aa471f3e`。PickCube 和 NutAssembly 不再在各自 Task 文件中重复创建 R3 控制器、配置 gripper 上限、创建 hold 和组装节拍；Controller owner 接收实际 Artifact／source、profile、force limit、速度限制和 gripper rate，完成原有对象组合。两个 Task 仍提供各自的任务语义、Solution 与来源身份；共同 owner 不启动 provider 或物理推进，也没有把 Position、effort 或其他 Controller 变成 R3。Task 中仍存在历史来源身份的单独处理，四任务 Controller／Robot 的完整绑定并未由本批收口。

生产修改 3 文件 +24／−26，净减 2 行；版本诊断修改 1 文件 +20／−0；本文与当前状态文档修改 2 文件。无文件新增、删除或整文件迁移，项目 tracked 文件数保持 1365。两份 Task 文件减少重复控制构造，实际 R3、hold 和 gripper 依旧由同一个 Controller 组合 owner 管理。provider／renderer adapter、source 映射、clock 和实际提交未更改。

51 项版本检查通过，其中 5 项读取真实 tabletop source；新增检查确认两个任务的 R3、hold、gripper 指向同一个基础 Controller，保持 500 Hz、10 N 和 Artifact 控制周期。MuJoCo CPU 的 PickCube、NutAssembly 与 PickCube reset-scoped joint／r3 各完成短程，切换路线含 H5 读回；初版及将 Controller 选项改为显式参数后的最终版各 20 子步，合计观测 40 子步。最终版与上批比较，Artifact、source、reset、主体和单步奖励一致；Controller 源码身份变化，历史身份不替换。GeoPhys CPU 的两个 tabletop 短程通过，内部子步未观测，各保守预留 50。Isaac USD source 与 physical 动作合同完成静态检查，未启动 SDK；renderer 和完整 Solution 本批未复验。计划、冻结 diff、身份对照及结果位于 ignored `workspace/maintenance/v211_r3_controller_owner_20261112_001/`；E01～E04 仍未接收。

### 6.46 退休旧 component physical 构建分支

输入 `ffaea599`。四个正式任务的配置解析已统一返回正式 resolved 配置；旧 `ResolvedEnvConfig` 直接进入这些任务时会在解析边界被拒绝。公共 Env 原先仍保留一条将旧 component 配置转为 physical task binding 的分支及其独立 provider、timebase、camera 等检查；该分支对于正式配置不可达，现已移除。独立 component 环境仍有自己的构造路径；正式 source、设备、渲染和控制能力检查继续由既有正式配置及 Runtime owner 执行。

生产修改 1 文件 +41／−78，净减 37 行，删除一条重复物理构建分支及其校验；无整文件迁移。版本诊断修改 1 文件 +13／−0；本文与当前状态文档修改 2 文件。无文件新增或删除，tracked 文件数保持 1365。四任务实际公共构造无需根据旧 component 结果再选择 physical builder；组件-only 配置解析以及真实 Position／effort 控制能力仍在，不能据此宣称整个 E01～E04 已完成。provider／renderer adapter、clock 和提交实现未改。

55 项版本检查通过，包含四任务拒绝旧 component resolved 输入；单独以不启动物理的方式检查背景 component 构造与关闭。MuJoCo CPU 四任务、装配 Panda 和 PickCube reset-scoped joint／r3 切换短程通过，后者含 H5 读回，共观测 75 子步；同 seed 对照的 Robot／Controller、reset、可用 Artifact／Scene／source 身份和单步奖励一致。GeoPhys CPU 的 PickCube 和 Pendulum 通过短程，内部子步未观测，各保守预留 50。Isaac、renderer 和完整 Solution 本批未重跑；计划、冻结 diff、对照与结果位于 ignored `workspace/maintenance/v211_retire_component_physical_20261112_001/`。E01～E04 仍未接收。

### 6.47 退休 tabletop 类级共享 binding

输入 `983aa8e2`。PickCube／NutAssembly 不再在导入 Env 类时预先创建一份类级 Task binding；正式 `make_env` 依据规范配置为每个环境创建 binding。两个 Task 类中与基类完全重复的配置入口也已删除，调用共同入口。Nut 的已有 native-feedback 显式构造在被调用时创建自身 binding，不再读取类级单例；其能力没有因本批重获资格。旧的无配置直接 Env 构造不再作为正式入口，调用者应使用 `task_env.make_env` 及正式配置。

生产修改 2 文件 +1／−16，净减 15 行；版本诊断修改 1 文件 +26／−0；本文和当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1365。减少类加载时无关的 Task 构造及两份重复解析入口；每个 Env 的 binding、Controller 和 source 各自持有。provider／renderer adapter、source 映射、clock 和控制提交未改；共同四主体构建仍未完成。

57 项版本检查通过，新增检查分别构造同一 tabletop 任务的两个 Env，确认 binding、Controller、source 独立，关闭第一个后第二个 source 仍存在；检查读取资产但不启动物理。MuJoCo CPU 的 PickCube、NutAssembly、装配 Panda 和 PickCube reset-scoped joint／r3 切换短程通过，切换含 H5 读回，共观测 25 子步；对照中主体、reset、可用 Artifact／Scene／source 身份和单步奖励一致，Nut Controller 因 Task 来源源码身份变化。GeoPhys CPU 的 NutAssembly 通过短程，内部子步未观测，保守预留 50。Isaac、renderer、显式 native-feedback 路线及完整 Solution 本批未重跑；计划、冻结 diff、对照与结果位于 ignored `workspace/maintenance/v211_task_binding_instance_20261112_001/`。E01～E04 仍未接收。

### 6.48 单主体 effort execution 共同构造

输入 `46c9b52b`。Panda direct effort 与 Pendulum／双轮车在共同 Assembly 编译之后，原先分别创建状态需求、physical execution 并验证 source；现在这些实际步骤由 Runtime 的同一个声明式构造入口完成。Robot 继续提供主体、传动及各自的 Controller 构造；Panda tendon 耦合、简单主体的关节控制和 provider 原生映射保持各自语义。状态关节独立于受控关节声明，以保留双轮车未被直接驱动的俯仰状态。装配 Panda 的多主体 effort、Position 和 USD 专用 effort 仍未进入此入口，不能据此称四主体构建已完全统一。

生产修改 2 文件 +53／−48，净增 5 行；Panda 中的状态需求和 execution 收尾职责重写归 Runtime，非整文件迁移。版本诊断修改 1 文件 +18／−0，覆盖双轮车被动关节；本文和当前状态文档修改 2 文件。无文件新增、删除或整文件迁移，项目 tracked 文件数保持 1365。provider／renderer 的原生映射、clock 和提交算法未改，source／绑定身份和单位校验继续执行。

58 项版本检查通过。首版错误地要求全部状态关节等于受控关节，双轮车在物理启动前拒绝（0 子步）；修正为独立状态关节后通过，新增检查保留该差异。对同一实际 source，分别以输入提交的原构造函数与新构造函数构建，Panda、Pendulum 和双轮车的主体身份、physical binding、状态需求、Controller 身份及 joint／frame 映射一致；Panda 的动作 schema 也一致，简单主体使用其已声明的任务动作合同。比较脚本首版误对不提供 `action_shape` 的简单 Controller 调用通用 schema，失败于无物理运行的对照；修正后通过。

MuJoCo CPU 的 Panda direct effort、reset-scoped joint／r3 切换、Pendulum 和双轮车 direct／velocity-damped 均完成短程；另复验 Panda physical sequence 的共同提交。首轮成功路线 40 子步、修正后六条路线 115 子步、序列 5 子步，共观测 160；切换路线含 H5 写入读回。GeoPhys CPU 的 Panda joint effort 和双轮车通过短程，内部子步未观测，各保守预留 50。Isaac、renderer 和完整 Solution 本批未重跑；计划、冻结 diff、合同对照与结果位于 ignored `workspace/maintenance/v211_shared_effort_execution_20261112_001/`。E01～E04 仍未接收。

### 6.49 清除装配 Panda 的无调用 leaf 诊断探针

输入 `b57df4ab`。删除 Robot 模块中无仓库调用者的 `panda_assembly_leaf_bindings` 及只供该函数使用的旧 leaf／实验配置导入；它依赖历史 candidate 对象和固定实验布局，不参与四任务的正式构建。装配 Panda 的 source recipe、Position 主体绑定及现有 effort 声明仍保留；本批不将这些未统一的构造宣称完成。

生产修改 1 文件 +1／−70，净减 69 行；版本诊断修改 1 文件 +8／−0，为真实双 Controller interval 增加收据核对；本文和当前状态文档修改 2 文件。无文件新增、删除或整文件迁移，tracked 文件数保持 1365。旧诊断专用数据生成逻辑退出 Robot 模块，provider／renderer、clock 与实际提交逻辑未改。

58 项版本检查通过。MuJoCo CPU 的正式 PickCube 装配 Panda `r1_split` 与一体 Panda R3 短程通过，共观测 10 子步；装配路线实际确认一次 `position-target` 提交，arm 与 hand 两个 writer 的资源分别为七个 arm actuator 与一个 hand actuator，收据为 acknowledged，两个运行 Controller 身份与各自产出一致。与上次同 seed 对照的主体、Controller、Artifact、source、reset 和单步奖励一致。GeoPhys、Isaac、renderer 和完整 Solution 未在本批重跑；计划、冻结 diff、对照和提交收据位于 ignored `workspace/maintenance/v211_retire_assembly_leaf_probe_20261112_001/`。E01～E04 仍未接收。

### 6.50 正式公共配置只解析一次

输入 `8925a27a`。`make_env` 与继承的配置入口现在把原始 mapping／YAML／已解析对象直接交给共同 Env 构造边界，由该边界调用一次正式解析器；不再先解析后把结果交给 Env 再重解码一次。外部传入的 `ResolvedSelectedConfig` 仍经过原有字段、任务身份及重建一致性检查，篡改的时间步不会成为构建请求。component-only 环境仍由其既有 codec 解析，不将其当成四任务正式路径。

生产修改 2 文件 +6／−13，净减 7 行；版本诊断修改 2 文件 +47／−3；本文和当前状态文档修改 2 文件。无文件新增、删除或整文件迁移，tracked 文件数保持 1365。普通正式调用去掉一次配置重解码，四任务继续使用同一字段语义与构建边界；实际 source、provider／renderer、clock 与提交实现未改。不同内部任务和能力的构建仍未完全合流，E01～E04 不在此批接收。

63 项版本检查通过，直接计数四任务 `make_env` 各调用一次解析器，检查伪造已解析时间步被拒绝；既有四任务 YAML／mapping 解析等价检查通过。MuJoCo CPU 下，PickCube／Pendulum 使用 YAML，NutAssembly／双轮车、装配 Panda 和 PickCube reset-scoped 物理切换使用 mapping，均完成短程，共观测 75 子步；切换包含 H5 读回。两个 tabletop MuJoCo 隔离 worker 也完成 reset／单 interval／二次 reset／close，内部子步未观测，各保守预留 50。GeoPhys CPU 的 YAML PickCube 与 mapping 双轮车通过短程，内部子步未观测，各保守预留 50；单独以不启动物理的方式检查 component-only 环境构造与关闭。同 seed 对照的主体、reset、可用 Artifact／Scene／source 与单步奖励一致；Nut Controller 与最近一次 Task binding 变更后的身份一致。Isaac、renderer 和完整 Solution 本批未重跑。计划、冻结 diff、对照与结果位于 ignored `workspace/maintenance/v211_single_public_resolution_20261112_001/`。

### 6.51 Panda 参考 effort Controller 组合归控制 owner

输入 `658e6fdb`。MuJoCo／GeoPhys MJCF 与 Isaac USD 两条 PickCube source 路线原先分别创建 R3 参考并分流到普通、动态或质量矩阵 effort Controller；现在两者将 source 对应的模型、配置与边界交给同一个 Panda Controller 构造入口。Task 仍负责声明末端 frame、TCP、R3 参数及受限 nominal mass 模型的 source／字节校验；provider 的 native drive、状态和推进实现未变。这消除了重复的 Controller 组合分支，并非四任务 Robot 构造已经统一。

生产修改 4 文件 +58／−42，净增 16 行；版本诊断新增 1 文件 +30／−0；本文和当前状态文档修改 2 文件。无生产文件新增、删除或整文件迁移，项目 tracked 文件数由 1365 增至 1366。新增生产行是 Controller owner 中对普通、动态和质量矩阵组合的统一及不匹配检查；质量模型内容和 source 约束未放宽。renderer、clock、状态传输与物理提交没有改动。

67 项版本检查通过；新增检查覆盖四种正式 Panda 参考 effort 配置的 source closure、Controller 类型、动作空间及 pose 所需状态。首次新增检查误读动作 schema 的 `dimension` 字段而失败，修正为检查真实 action space 后全部通过。MuJoCo CPU 实际完成 joint 到 R3 的 reset 切换、推进、非法 reset 后保全、H5 读回及重复 close，观测 10 个 native 子步。Isaac 的四种参考 effort 配置对真实 USD source 完成 Controller 和 binding 构造检查，没有启动 Isaac SDK 或推进物理；GeoPhys、renderer 及完整 Solution 未在本批重跑。冻结 diff、计划、MuJoCo 结果和 Isaac source 检查位于 ignored `workspace/maintenance/v211_panda_effort_owner_20261112_001/`。E01～E04 仍未接收。

### 6.52 USD Panda effort 使用共同主体构建

输入 `9032fb38`。原 USD effort 路线在 PickCube Task 内重复创建 LogicalAssembly、物理通道、Controller 与状态需求，且没有 ControlledSubject；现在 USD source 保留已校验的 closure、drive／mimic transmission、Frame 和 native range 声明，交给 Panda 与 Runtime 同一主体声明、Assembly 编译和 physical execution 构建机制，与 MJCF 路线共同构造。source-specific transmission／动作模型身份作为数据传入，不放宽其 native admission。构造对照覆盖五种 Controller 的真实 MJCF／USD source：绑定、Controller action schema、状态需求及 joint／frame 映射逐项一致，USD 额外获得 `panda-v1` subject。

首次真实 Isaac 检查发现既有正式入口错误：USD physical binding 仍带 Position scalar 标记，导致实际 `make_env` 误选 Position source composer 并拒绝 effort profile。已清除此标记，新增检查覆盖该边界；同一次失败的 Isaac 清理还发生 SDK 菜单异常和退出时段错误，原始日志与收据保留。第二次实际运行正常完成两次 reset、非零 step、三帧同步 RGB、独立帧读回、重复 Env close 和 App close；观测 41 次 callback，订阅之前的启动推进未知。首次失败未能观测推进，按预留 59 次保守计入；两次累计记账 100 次。

生产修改 3 文件 +64／−88，净减 24 行；版本诊断修改 2 文件 +21／−0；本文和当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1366。69 项版本检查通过；MuJoCo direct effort 与 joint→R3 reset 切换、记录读回和 close 短程通过，共观测 15 个 native 子步。GeoPhys 与完整 Solution 本批未重跑，原 evidence 的复用限于未受影响行为；Isaac 的本次结果仅覆盖指定 USD、joint effort、CUDA 和同步 RGB 组合。计划、两次冻结 diff、实际前后 source 对照和全部运行收据位于 ignored `workspace/maintenance/v211_usd_robot_owner_20261112_001/`。E01～E04 仍未接收。

### 6.53 Panda effort 声明与构造共享 Robot 实例

输入 `26cce90b`。Panda direct effort 的原模块函数改为 Robot 实例方法；PickCube MJCF 路线通过注册表取得一个 Panda 实例，并把该实例同时用于 Scene 声明和后续真实 subject／Controller execution 构造。USD source 路线同样取得注册的 Panda 实例来构造 execution。方法仍调用共同 Runtime 编译，source admission 与 Controller 算法不变；这消除了实际构建时绕过 Robot 实例的路径，不意味着全部 Task 的 source 组合已统一。

生产修改 3 文件 +75／−74，净增 1 行；其中 Panda 文件约 60 行为函数移动到类内及缩进，不是新增算法。版本诊断修改 1 文件 +32／−0；本文和当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1366。版本检查直接确认正式 MJCF Scene 和 execution 收到同一个 Robot 对象。

70 项版本检查通过。MuJoCo direct effort、joint→R3 reset 切换、H5 读回和 close 短程通过，共观测 15 个 native 子步；五种 Controller 的 MJCF／USD 真实 source 前后对照显示主体、绑定、Controller action schema、状态需求及 joint／frame 映射均未改变。Isaac 和 GeoPhys 本批没有重跑；上一批 Isaac 原生验证仅可作为输入相同的历史证据，不能代替本批原生复验。renderer 和完整 Solution 未受本批验证。冻结 diff、构造对照及 MuJoCo 结果位于 ignored `workspace/maintenance/v211_panda_instance_owner_20261112_001/`。E01～E04 仍未接收。

### 6.54 简单主体的 effort Controller 归控制 owner

输入 `b587dca2`。Runtime 的 `ControlledSubjectV1` 只保留主体、source、通道、writer 和能力声明；直接力矩和速度阻尼 Controller 的构造与选择转到 Controller 模块。两种模式现在共用严格的主体 source、writer、单位和有序通道校验；速度阻尼此前未核对主体 source，本批补足。默认 Controller owner 也消费同一直接力矩构造，并保留它的已绑定身份。Panda 与简单主体仍有各自控制语义；本批没有宣称所有 Controller 的算法已合并。

生产修改 3 文件 +81／−91，净减 10 行；其中约 75 行是把既有 Controller 选择算法移入控制模块并收敛重复校验。版本诊断修改 1 文件 +27／−0；本文和当前状态文档修改 2 文件。无文件新增、删除或整文件迁移，tracked 文件数保持 1366。provider／renderer 的 native 适配、clock、提交及 source 构造未改。

72 项版本检查通过，覆盖两个 profile 对异源主体的拒绝及默认直接 Controller 的身份。MuJoCo 的 Pendulum／双轮车各用 direct 与 velocity-damped 完成 reset、非零 step 和 close，合计观测 100 个 native 子步；direct 路线与既有同 seed 证据的 Robot／Controller、奖励及时间一致。GeoPhys Pendulum direct 短程通过，内部子步未观测、保守预留 50；尝试的 GeoPhys velocity-damped 在静态配置准入被拒绝，未启动物理，保持该能力限制。Isaac、renderer 和完整 Solution 本批未重跑。冻结 diff、补充说明和运行收据位于 ignored `workspace/maintenance/v211_subject_controller_owner_20261112_001/`。E01～E04 仍未接收。

### 6.55 从共同 Env 退休旧诊断 profile

输入 `045ef0e8`。四个正式任务均不声明旧 `diagnostic_profile`，共同 Task binding 和 Env 仍以它绕过普通 provider 准入、改变 worker 预检并向 materialization 传参。本批移除该诊断专属字段和 Env 分支；provider 层原有 native 准入及其可独立调用的诊断 API 没有改变。混合控制与 native-feedback 的互斥约束保留；不将这些后续范围宣称完成。

生产修改 3 文件 +4／−14，净减 10 行；诊断、测试代码无变更；本文和当前状态文档修改 2 文件。无文件新增、删除或迁移，tracked 文件数保持 1366。普通 Env 的构造、reset 与物理提交不再有该诊断条件，renderer 和时钟实现未改。

72 项版本检查通过。MuJoCo 四任务短程通过，观测 60 个 native 子步；两个 tabletop MuJoCo 隔离 worker 通过 reset、step、二次 reset 和 close，内部子步未观测、各保守预留 50。GeoPhys PickCube R3 短程通过，内部子步未观测、保守预留 50。四任务同 seed 的 Robot／Controller 视图和单步奖励与先前证据一致。计划原列 GeoPhys Pendulum，实际选择受影响的 tabletop scalar materialization 路线，已在证据补充记录中更正；Isaac、renderer 和完整 Solution 本批未重跑。冻结 diff、计划、补充说明及运行收据位于 ignored `workspace/maintenance/v211_retire_diagnostic_env_20261112_001/`。E01～E04 仍未接收。

### 6.56 退休 C05c 历史 Runtime 准入

输入 `ddb653ae`。上一批已移除正式 Env 对 `diagnostic_profile` 的分流；本批进一步删除只针对历史 NutAssembly／GeoPhys CUDA cadence 实验的临时 capability manifest、两个 materialization 参数及相关互斥分支。普通 provider manifest、native-feedback 与混合控制的既有准入和互斥检查仍保留；历史 C05c 证据不改变其原有结论，也不再作为正式入口的兼容目标。

生产修改 2 文件 +15／−77，净减 62 行；诊断／测试代码无变更；本文和当前状态文档修改 2 文件。无文件新增、删除或整文件迁移，tracked 文件数保持 1366。正式 Runtime 的 source、clock、提交和 renderer 数据路径未改；清除的是诊断专属 admission authority。

72 项版本检查通过。四任务 MuJoCo 短程通过，观测 60 个 native 子步。Isaac PickCube joint effort／CUDA／同步 RGB 实际完成两次 reset、一次非零 step、三帧独立读回及 Env／App 关闭，观测 41 次 physics callback，订阅前启动推进未知。GeoPhys PickCube R3 短程通过，内部子步未观测、保守预留 50。CPU 原计划仅列四个 MuJoCo case，后补 GeoPhys 一次并记录；按原每次 50 的全部保守预留合计为 250，高于计划中原列的 200，实际四个已观测 MuJoCo 子步加 GeoPhys 保守预留为 110。完整 Solution 本批未重跑。冻结 diff、计划、补充说明、独立读回及收据位于 ignored `workspace/maintenance/v211_retire_c05c_admission_20261112_001/`。E01～E04 仍未接收。

### 6.57 退休旧 Position 输入的 observation 和录像 writer

输入 `0a53d8a8`。旧 Position candidate 输入和 classifier 已无正式生产者，但共同 observation 及录像 writer 仍包含 F04／F05 专属分支和 200 余行 metadata。移除这些历史输入专属的实时分流、classifier 和 writer；F06 正式 Isaac Position 的公开状态、native Position 写入确认、逐 substep 推进收据与 provenance 校验保留。历史录像读取器未改；这不代表 E10 的全部 recorder 整理已经完成。

生产修改 3 文件 +11／−276，净减 265 行；测试／诊断代码无修改；本文和当前状态文档修改 2 文件。无文件新增、删除或迁移，tracked 文件数保持 1366。正式构建路径不再检查无生产者的旧 Position 输入；Runtime clock、物理提交、adapter 和 renderer 未改。

72 项版本检查通过。MuJoCo 装配 Panda Position 的双 writer 录像完成逻辑读回、physical joint→R3 切换录像完成 H5 读回，共观测 15 个 native 子步。Isaac 正式 R3 Position／同步 RGB 完成两次 reset、step、三帧独立读回及 Env／App 关闭；H5 独立读回包含一条 structured transition、native Position Ack、5 个 native 推进收据、两个 typed-state 样本，观测 41 次 callback，订阅前启动推进未知。首次 Isaac 运行因测试相机仍绑定旧 physical Artifact，被身份检查拒绝并在退出 SDK 时异常；第二次用当前 Position Artifact 绑定相机后通过。首次未观测推进按 59 次保守计入，累计记账 100 次。GeoPhys 和完整 Solution 本批未重跑。冻结 diff、计划、两次运行、H5 检查及收据位于 ignored `workspace/maintenance/v211_retire_position_input_writer_20261112_001/`。E01～E04 仍未接收。

### 6.58 退休 F05 旧 Position Session 入口

输入 `89e31e56`。F05 native、DG02 和 DG04 输入只由已退休诊断入口生产；共同 Runtime 仍维护三套材料化、专属 capability manifest、验证、S1 测试注入及 receipt 分流。本批从 Session 输入分类、选路和材料化中移除这些分支，并撤销它们的旧执行路线准入。正式 F06 Isaac Position 输入仍要求精确类型、schema、source、Artifact、provider 及 native receipt；普通 G05 effort 与其他正式 provider 的准入保持。F05 底层历史类型及仅由历史诊断引用的 adapter 代码仍在，尚待后续辨别和清理；不因此声明 E01～E04 完成。

生产修改 2 文件 +5／−487，净减 482 行；版本诊断修改 1 文件 +14／−0；本文和当前状态文档修改 2 文件。无文件新增、删除或迁移，tracked 文件数保持 1366。Env 不再能经旧 F05 类型进入这些独立 Session 构建路径；Runtime 的正式 source、clock、提交和 renderer 合同未改变。

73 项版本检查通过，新增检查覆盖正式 USD 输入类型／schema 及未知输入拒绝。MuJoCo 四任务短程通过，共观测 60 个 native 子步；GeoPhys PickCube R3 短程通过，内部子步未观测、保守预留 50。Isaac Position 与 joint effort 两条 CUDA／同步 RGB 路线分别完成两次 reset、step、三帧独立读回和关闭，各观测 41 次 physics callback，订阅前启动推进未知；Position 的 H5 独立核对保留 native Ack、5 条推进收据与两个 typed-state 样本。完整 Solution 本批未重跑。冻结 diff、计划、两条 Isaac 运行、GeoPhys 收据及 H5 检查位于 ignored `workspace/maintenance/v211_retire_f05_session_20261112_001/`。

### 6.59 清除 F05 孤立 native 输入与 GeoPhys adapter

输入 `cd77d708`。F05 的三个 Session 准入在 6.58 已退休；进一步检查四个正式任务、Runtime、benchmark 和 examples 的生产引用后，`position_admission.py` 的旧 F05 类型与 `geophys_native_io.py` 的 F05 专属 USD adapter 均无剩余生产调用者，遂删除这两个文件。正式 GeoPhys 的 MJCF adapter、F06 Isaac 的 native 实现及共享控制／状态合同没有删除；历史诊断对旧路径的引用不再作为兼容目标。Isaac adapter 内的其他历史专用条件仍待后续核对。

生产删除 2 文件、1084 行，新增和迁移均为 0；测试／诊断代码无修改；本文和当前状态文档修改 2 文件。项目 tracked 文件数由 1366 减至 1364。正式 Runtime 构建、source、clock、提交与 renderer 路径未改；删除的是已无法由正式入口到达的旧 native 实现。

73 项版本检查通过；MuJoCo PickCube R3 短程观测 5 个 native 子步，GeoPhys 同任务短程通过、内部子步未观测并保守预留 50。Isaac Position／effort、四任务及 H5 受影响行为可复用 6.58 已有证据：本批删除的两文件没有出现在正式生产导入链中，本批未重跑 Isaac 或完整 Solution。冻结 diff、计划和 CPU 收据位于 ignored `workspace/maintenance/v211_retire_f05_native_files_20261112_001/`。E01～E04 仍未接收。

### 6.60 退休孤立 Position candidate 资产

输入 `837379c7`。旧 Position candidate 的实现与 Session 准入已退休，资产目录仍保留六个仅由历史诊断使用的 scene、recipe、receipt 和 fixture。经检查正式任务、Runtime、benchmark、examples 的生产引用后删除这六个文件；正式 Panda、PickCube、NutAssembly 和简单主体实际使用的 source 不在其中。历史 planning manifest 对其中一次旧变更的文字记录保留，六个文件的 Git blob 与 SHA-256 已记入本批证据，可从输入提交恢复。Isaac adapter 内的 DG04／F06 共用 mimic 路径尚未清理，需分辨后继续。

删除 6 个历史资产文件、24022 字节、869 个文本行；无生产 Python 代码、测试或诊断代码变化，无新增或迁移。本文和当前状态文档修改 2 文件；tracked 文件数由 1364 减至 1358。正式构建、provider／renderer、clock 和提交路径未改变。

73 项版本检查通过；MuJoCo 正式 PickCube reference 与 physical joint→R3 reset 切换、H5 读回和 close 短程通过，共观测 15 个 native 子步。Isaac 与 GeoPhys 本批未重跑，6.58／6.59 的正式路线证据可在本批删除文件不属于其 source 输入或生产调用链的范围内复用；完整 Solution 未重跑。文件身份、冻结 diff、计划及运行收据位于 ignored `workspace/maintenance/v211_retire_position_legacy_assets_20261112_001/`。E01～E04 仍未接收。

### 6.61 退休 Isaac adapter 的 DG04 专用分支

输入 `5f3c714b`。DG04 的正式输入与 Session 准入已退休，但 Isaac native adapter 仍保留其特定 scene、contact witness、DriveAPI 改写、receipt 和 route 选择。本批移除这些专属实现，保留仍由正式 F06 使用的 Panda mimic 关系、source 检查、5 N leader drive、原生状态和 actuation／projected force 的分离读回，以及 G05 effort 路线。此项只收敛已不可达的 DG04 分支，并不代表 renderer 或全部 provider adapter 整理已完成。

生产修改 1 文件 +63／−460，净减 397 行；测试／诊断代码无修改；本文和当前状态文档修改 2 文件。无文件新增、删除或迁移，tracked 文件数保持 1358。Runtime 对正式 source、clock、提交和 native feedback 的合同保持；旧 DG04 输入不再是 native adapter 的构造选项。

73 项版本检查通过。Isaac PickCube Position 与 joint effort 的 CUDA／同步 RGB 路线均完成两次 reset、非零 step、三帧独立读回、重复 Env close 和 App close，各观测 41 次 physics callback；订阅前启动推进未知。Position H5 独立检查确认 native Ack、5 个推进收据、两个 typed-state 样本以及各收据的 F06 mimic／5 N actuation 语义。两次关闭日志均有 Isaac 菜单扩展访问已关闭 USD context 的异常，但应用与进程关闭收据均成功；该日志不当作物理故障或被忽略。简单主体 Isaac、MuJoCo、GeoPhys 和完整 Solution 本批未重跑；其他 provider 代码未变，先前证据按原范围保留。冻结 diff、计划、两次 native 收据与 H5 检查位于 ignored `workspace/maintenance/v211_retire_dg04_isaac_20261112_001/`。E01～E04 仍未接收。

### 6.62 Panda 零偏置 effort Controller 归控制 owner

输入 `a1789db2`。一体与装配 Panda 原先分别创建同一类零偏置模型、Controller requirement 和线性 effort profile；现在 Controller 自己从已编译 source-bound 通道构造该模型，Robot 只提供自身通道、writer 和动作映射。新增统一的 writer／通道校验；一体 Panda 的 MJCF／USD 五种 profile 前后对照中，subject、binding、Controller identity、状态需求和动作合同均一致。装配 Panda 的 effort 构造也调用同一 owner，但目前没有正式 task caller，本批未对其宣称原生验证。

生产修改 3 文件 +33／−26，净增 7 行；控制模型创建逻辑集中到 Controller，新增行包含统一通道检查。版本诊断修改 1 文件 +21／−0；本文和当前状态文档修改 2 文件。无文件新增、删除或迁移，tracked 文件数保持 1358。provider／renderer、clock 与 native 提交路径未改。

74 项版本检查通过，新增错误 writer 拒绝检查。MuJoCo Panda direct effort 与 joint→R3 reset 切换／H5 读回通过，共观测 15 个 native 子步。Isaac PickCube joint effort／CUDA／同步 RGB 完成两次 reset、step、三帧独立读回及 Env／App 关闭，观测 41 次 physics callback，订阅前启动推进未知。GeoPhys、装配 Panda effort 和完整 Solution 本批未重跑；其他 provider 路径保持原有限定。冻结 diff、计划、十组 source 对照及运行收据位于 ignored `workspace/maintenance/v211_panda_controller_factory_20261112_001/`。E01～E04 仍未接收。

### 6.63 Panda effort profile 语义归控制与 Robot owner

输入 `13322cae`。Panda 的五种 effort profile 与输入 kind 原由 PickCube candidate 文件定义；现在 Controller owner 提供不可变语义表，Panda Robot 声明该表，PickCube 配置和构建消费同一对象。Task 的 source、provider 和 fixture 准入仍保持原有限定；这一移动没有扩大能力范围，也没有消除该 Task 内所有 source／profile 材料化分支。

生产修改 4 文件 +27／−16，净增 11 行；五项原有 profile 映射从 Task 移至控制 owner，新增 Panda 声明与不可变约束。版本诊断修改 1 文件 +12／−0；本文和当前状态文档修改 2 文件。无文件新增、删除或整文件迁移，tracked 文件数保持 1358。provider／renderer、native clock、提交和状态路径未改。

75 项版本检查通过，新增检查验证 Task、Robot 和 Controller 消费同一不可变语义表。五种 profile 的 MJCF／USD 十组真实 source 前后对照中，subject、binding、Controller identity、状态需求和动作合同一致。MuJoCo direct effort、joint→R3 reset 切换与 H5 读回通过，观测 15 个 native 子步；Isaac joint effort／CUDA／同步 RGB 完成两次 reset、step、三帧独立读回及 Env／App 关闭，观测 41 次 callback，订阅前启动推进未知。GeoPhys 与完整 Solution 本批未重跑；旧证据按未受影响的已验证范围保留。冻结 diff、计划、source 对照及运行收据位于 ignored `workspace/maintenance/v211_panda_profile_owner_20261112_001/`。E01～E04 仍未接收。

### 6.64 收敛 Panda effort 参考参数的重复准备

输入 `cb815e06`。PickCube 的 MJCF 与 USD 两条 source 原先各自选择 R3 参数、速度限制和质量模型；现由 Task 的一份参考参数准备逻辑执行这些选择与 source-bound 模型准入，再交给共同 Controller owner 组合。MJCF 与 USD 仍分别提供各自的 kinematics 和 frame，模型身份、source closure 和 cadence 检查保留。这减少重复决定，但 PickCube 的 source 专属构建仍存在，四任务共同构造链尚未完成。

生产修改 2 文件并重命名 1 文件，+34／−34，净变化 0；原质量模型文件的既有内容随重命名迁移，新增参数准备逻辑并删除两处重复逻辑。无生产文件新增或删除，tracked 文件数保持 1358；测试／诊断代码无修改，本文及当前状态文档修改 2 文件。provider／renderer 的 source、状态、clock、提交和资源合同未改变，不能将本批视为 adapter 全部对齐。

75 项版本检查通过。MJCF／USD 五种 profile 共十组真实 source 的 subject、binding、Controller identity、状态需求及动作合同与输入版本一致。MuJoCo joint→R3 reset 切换和 H5 读回通过，观测 10 个 native 子步。Isaac joint effort／CUDA／同步 RGB 完成两次 reset、一次 step、三帧独立读回及 Env／App 关闭；采图阶段无额外物理推进，订阅前启动推进未知。渲染 warmup 日志有一次推进错误后继续取得图像；SDK 关闭日志仍有菜单扩展访问已关闭 USD context 的异常，关闭收据及进程退出成功。GeoPhys、完整 Solution 和其余 profile 的原生执行本批未重跑，先前证据按实际代码影响和原限定使用。冻结 diff、计划、source 对照及运行收据位于 ignored `workspace/maintenance/v211_panda_reference_inputs_20261112_001/`。E01～E04 仍未接收。

### 6.65 USD Panda 声明与 effort 构造共享 Robot

输入 `21cdac15`。PickCube USD 路线原先由 Scene 声明和 effort 构造分别创建 Panda；现在复用 Task source 已声明的同一 Robot 实例，将它传入 USD Scene 编译与 effort 绑定。直接调用独立 USD source compiler 时仍可自行创建默认 Panda。源闭包、Artifact、Scene 及 native drive 的准入保持；这消除一次独立实例化，不代表已经统一所有 Task 的 source 构造。

生产修改 3 文件 +13／−12，净增 1 行；版本诊断修改 1 文件 +18／−0，覆盖 Scene 使用传入 Robot；本文及当前状态文档修改 2 文件。无文件新增、删除或整文件迁移，tracked 文件数保持 1358。provider／renderer 的 source、状态、clock、提交和资源合同未改变。

76 项版本检查通过。真实 MJCF／USD source 的五种 profile 共十组合同与输入版本一致，USD 的场景声明与 effort 构造实测收到同一 Robot 实例。Isaac joint effort／CUDA／同步 RGB 实际完成两次 reset、一次 step、三帧独立读回、重复 Env close 与 App close，观测 41 次 physics callback，采图期间无额外推进，订阅前启动推进未知。渲染 warmup 日志出现推进错误后取得图像；只读环境的 stage template 权限日志与 SDK 关闭时菜单扩展异常保留，进程和读回均成功。MuJoCo、GeoPhys 及完整 Solution 本批未重跑，静态 source 对照不等于原生执行。证据位于 ignored `workspace/maintenance/v211_usd_robot_owner_20261112_001/`，本次 native 运行是 `isaac/runs/isaac-003`，目录中更早的 `001`／`002` 属于历史运行，不能混用。E01～E04 仍未接收。

### 6.66 简单主体复用 source 校验过的传动声明

输入 `4726e235`。Pendulum 和双轮车的共同 source compiler 与 Controller 构造此前分别调用 Robot 的主体声明，存在两份独立生成的传动数据。现在 source compiler 检查电机数、关节、名称、传动比、限幅之后，把同一份关节声明交给共同 Assembly／Controller 路径；若 source adapter 改变 source 身份，则将主体绑定到最终 source，后续编译仍核对 source identity 与 closure。删除两份 Task 文件中不再使用的 source compiler 导入。

生产修改 5 文件 +11／−15，净减 4 行；版本诊断修改 1 文件 +32／−2，覆盖 USD source 身份绑定及两个正式任务实际只生成一次声明；本文及当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1358。provider／renderer 的推进、clock、状态及资源合同未改；这项收敛只覆盖简单主体，Panda 和完整 adapter 整理仍需继续。

78 项版本检查通过；MuJoCo Pendulum 和双轮车各完成 reset、step 和关闭，分别观测 25 个 native 子步。GeoPhys 两任务短程均通过，内部物理子步未观测、按每次 50 保守预留。Isaac 的最终 source 身份绑定通过无 SDK 合同检查，本批未进行 Isaac 原生运行；完整 Solution 未重跑。冻结 diff、计划和 CPU 收据位于 ignored `workspace/maintenance/v211_checked_subject_20261112_6l8UzF/`。E01～E04 仍未接收。

### 6.67 PickCube direct effort 统一物理状态路径

输入 `247319d8`。PickCube direct effort 的 MuJoCo 路线原已直接使用物理 Controller 和 V2 状态，GeoPhys 同一控制模式却额外创建 Position Controller、编译 Position binding 并使用 V1 状态。现在两者按控制能力选择相同路径：无 reset 切换的 direct effort 使用自身 Controller 和 V2 状态；Position 及 reset 切换路线保留自己的语义与 source 检查。仅影响 MJCF direct effort，不扩大 Isaac 准入。

生产修改 1 文件 +2／−3，净减 1 行；版本诊断修改 1 文件 +26／−0，检查 MuJoCo 和 GeoPhys 的 direct effort 构造不再调用 Position Controller；本文及当前状态文档修改 2 文件。没有新增、删除或整文件迁移，tracked 文件数保持 1358。GeoPhys 现在通过 physical Runtime 的 source、V2 状态、同一个控制提交和 clock；renderer 未改。

80 项版本检查通过。GeoPhys direct effort 实际完成 reset、step、二次 reset 和重复关闭，观测到一次控制 interval 对应 0.01 秒；native 内部子步未观测、按 50 保守预留。补充的 GeoPhys 录像尝试在开始写入前因 direct effort 构造未提供 Solution identity 被记录器拒绝，未完成 H5 读回；该 identity 在本批输入版本也只由 reset 切换路线提供，记录器整理仍待处理。MuJoCo direct 的生产分支未变，其先前运行证据按原范围保留；Isaac 和完整 Solution 本批未重跑。冻结生产 diff、最终 diff、计划与两次运行收据位于 ignored `workspace/maintenance/v211_direct_effort_state_20261112_xkZyFZ/`。E01～E04 仍未接收。

### 6.68 固定 Panda effort 不再依赖 Position 观测

输入 `3106e834`。MJCF 上非切换的 joint、R3 和质量模型 effort 原先仍构造 Position Controller，以取得 action 配置和 V1 观测；现直接从已绑定 source 取得 action 配置，使用 effort Controller 与 V2 状态。MuJoCo 与 GeoPhys 共用此构建决定。reset 切换路线仍需要其 Position 观测和 Solution 接线；USD 仅将同一 action 配置显式传给 effort 组合器，仍使用原 Position 观测。

生产修改 3 文件 +7／−6，净增 1 行；版本诊断修改 2 文件 +9／−5，扩展五种固定 profile 的双 CPU provider 构造检查与 R3 短程探针；本文及当前状态文档修改 2 文件。没有新增、删除或整文件迁移，tracked 文件数保持 1358。固定 effort 不再为状态发布构造 Position Controller；Runtime source、control interval、clock 和 renderer 所有权未改。

88 项版本检查通过，五种固定 profile 均验证 MuJoCo／GeoPhys 构造不调用 Position Controller。五种 MJCF／USD profile 的十组 source／Controller 合同与输入基线对照一致。MuJoCo 和 GeoPhys 的 joint／R3 effort 均完成 reset、step、二次 reset 和关闭；MuJoCo 两次各观测 5 个 native 子步，GeoPhys 内部子步未观测、两次各保守预留 50。质量模型 profile 此批只有构造检查，USD 只有 source 合同对照，Isaac 原生和完整 Solution 未重跑。冻结 production diff、最终 diff、计划与运行收据位于 ignored `workspace/maintenance/v211_fixed_effort_state_20261112_nrUXR7/`；R3 探针更新的身份另记于 `r3-plan.json`。E01～E04 仍未接收。

### 6.69 MJCF Panda source 与物理构造共享 Robot

输入 `c9760c17`。PickCube MJCF effort 原先为已有 Task source 新建另一个 Panda，再用于 Scene 和 Controller 构造；现在沿用该 source 已声明的 Robot，同一实例贯穿 Task source、Scene 声明和 effort 绑定。USD 已在 6.65 采用同一原则。实际 source 身份、资产闭包和传动校验不变；这尚未消除全部 Task 专属 source 构建。

生产修改 1 文件 +1／−2，净减 1 行；版本诊断修改 1 文件 +40／−0，检查三个构建环节实际使用同一 Robot；本文及当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1358。provider／renderer 的 source 合同、状态、clock、提交和资源未改。

89 项版本检查通过；MJCF／USD 五种 profile 共十组 source／Controller 合同对照与输入基线一致。MuJoCo direct effort 与 joint→R3 reset 切换、H5 读回和关闭通过，共观测 15 个 native 子步。GeoPhys、Isaac 原生及完整 Solution 本批未重跑；旧证据按未受影响的路线和 source 身份范围保留。冻结 diff、对照、计划及收据位于 ignored `workspace/maintenance/v211_mjcf_robot_owner_20261112_p5iHyo/`。

本批另尝试让 reset 切换直接使用物理 V2 状态：首次在静态准入因缺少声明被拒，调整后 reset 通过，但录像开始时依赖 Position 专属边界和元数据而失败。该尝试已从生产 diff 撤回，失败收据保留于 ignored `workspace/maintenance/v211_switch_physical_state_20261112_J4EKMr/`；后续需要先迁移录像和 Solution 生命周期，不能仅删除 Position 对象。E01～E04 仍未接收。

### 6.70 物理控制录像元数据归实际执行 owner

输入 `ce1ca466`。reset 可切换 effort 的录像原先先调用 Position Controller 的元数据构造，再覆盖为物理 profile，导致物理录像依赖不参与 effort 的 Position controller、scene 和 binding 来源。现在直接从已提交的物理 execution、实际观测 schema、Task Artifact、source 与 reset plan 生成录像元数据；Position 录像仍由原 Position owner 生成。移除物理录像中无关的 Position binding provenance，保留物理 binding、Controller、source closure、scene、reset 和执行选择身份。

生产修改 2 文件 +55／−33，净增 22 行；版本诊断修改 1 文件 +30／−0，验证 physical 录像不调用 Position 元数据并绑定实际身份；本文和当前状态文档修改 2 文件。无文件新增、删除或整文件迁移，tracked 文件数保持 1358。本批只改变录像元数据构造，provider／renderer 的 source、状态、clock、控制提交与资源没有改变；reset 切换执行仍需 Position 观测，尚未消除。

90 项版本检查通过。MuJoCo joint→R3 reset 切换的 physical H5 写入、结构化读回与关闭通过，观测 10 个 native 子步；独立 h5py／YAML 读回核对物理 binding、scene 和 Controller 身份，确认不含 Position binding provenance。装配 Panda Position 双 Controller 录像及结构化读回通过，观测 5 个 native 子步。GeoPhys、Isaac 和完整 Solution 本批未重跑，先前执行证据按未受影响范围保留。冻结 diff、计划、两次运行和独立检查位于 ignored `workspace/maintenance/v211_physical_record_metadata_20261112_1794433545/`。这只完成录像依赖的一部分，不表示 E10 或 E01～E04 接收。

### 6.71 reset 切换使用实际物理状态与 Controller

输入 `157e3758`。PickCube MJCF 的 reset 切换此前仅为 V1 状态和录像构造 Position Controller；现在声明物理 execution，由共同 Runtime 以当前提交的物理 Controller 物化、初始化并发布 V2 状态。reset 保存动作规格和任务执行信息，停止与结构化录像读取实际活动 Controller 身份；Position Controller 和专用观测投影从该路线移除。选择准备、generation、source／Artifact preflight、故障与失败清理检查保留。USD effort 仍有 Position 状态依赖，本批未处理。

生产修改 3 文件 +48／−45，净增 3 行；版本诊断修改 2 文件 +35／−2，覆盖 R3 Solution 单步／录像和切换 Controller 身份；本文及当前状态文档修改 2 文件。没有新增、删除或整文件迁移，tracked 文件数保持 1358。构建消除一个非执行 Position Controller，物理提交、V2 状态、clock 和 source 由同一 Runtime 执行合同承载；renderer 未改，其他任务仍走各自已声明的能力路径。

91 项版本检查通过，包括 R3 Solution reset、一次真实提交、录像读回和停止；这不是完整 Solution 成功结论。四个正式任务 MuJoCo 短程及 joint→R3 切换／H5 读回通过，最终五次运行共观测 70 个 native 子步；随后装配 Position 录像和切换录像再次通过，分别观测 5 和 10 个子步。本批第一次切换探针完成 10 个子步后，因探针把初始声明误作活动 Controller 而失败；修正探针后通过，失败与重试收据保留。GeoPhys、Isaac 原生和完整 Solution 本批未重跑。冻结各轮 diff、计划与收据位于 ignored `workspace/maintenance/v211_switch_physical_final_20261112_9qFC7G/`；E01～E04 仍未接收。

### 6.72 USD effort 使用物理状态与 source 准入

输入 `417a15d7`。PickCube USD effort 原先选择 Position Controller 物化 Runtime 并发布 V1 观测；现在运行时选择实际 physical execution，任务观测消费其 V2 状态，renderer 继续独立消费同一边界的 source-bound 状态。USD 的 hand_pose 沿用该 source 声明的 ee frame 语义；resolved Controller identity 改为实际物理 Controller。共同 Runtime 将已有 versioned source 准入输入传给物化层，F06 的 Core 生成清单仍按 Artifact 核对。构建阶段仍临时创建 Position 对象以取得配置和运动学模型，尚待移除，不能将本批视为完整统一。

生产修改 4 文件 +18／−8，净增 10 行；测试／诊断代码无修改；本文及当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1358。物理 Controller 的 V2 观测与 task RGB renderer 的 V1 状态分别核对 Runtime 边界，renderer 本身、clock 和物理提交 owner 未改变。

91 项版本检查通过；MJCF／USD 五种 profile 共十组 source 和 physical Controller 合同对照一致。Isaac joint effort／CUDA／同步 RGB 完成两次 reset、一次 step、三帧独立读回及 Env／App 关闭，观测 41 次 physics callback，采图期间无额外推进，订阅前启动推进未知。首次运行因物理构造未传入 F06 准入输入被拒，未观测物理推进、按 59 次保守预留；第二次修正后通过，窗口累计按 100 次记账。SDK 日志仍有只读目录提示、渲染预热错误及关闭时菜单扩展异常；callback 取消订阅接口也报告 AttributeError，进程和独立读回成功。MuJoCo joint→R3 切换／H5 读回通过、观测 10 个 native 子步；GeoPhys 和完整 Solution 本批未重跑。冻结各轮 diff、计划、对照及收据位于 ignored `workspace/maintenance/v211_usd_physical_state_20261112_VUQQP8/`。E01～E04 仍未接收。

### 6.73 USD effort 直接构造物理 Controller

输入 `d75109f2`。PickCube USD effort 原先先构造 PositionServo，再借其 action config 和运动学模型构造物理 Controller；现在共同 USD source 构造将已验证的 source、动作配置和模型文本交给选定的 Controller 构造者，effort 直接创建物理执行，需要 R3 时才创建运动学模型。正式 Position 仍使用自身 PositionServo。effort 的来源身份不再包含未使用的 PositionServo 文件；准确的物理 Controller 身份在首次构造时写入 resolved configuration。共同参考 source 准备仍创建参考 Controller，本批没有消除该剩余依赖。

生产修改 2 文件 +44／−36，净增 8 行；测试／诊断代码无修改；本文和当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1358。F06 source、Artifact、ExecutionSpec、source closure 和 native 准入仍由已有 Runtime 检查；renderer、物理提交和 clock 未改变。

91 项版本检查通过。禁用 USD PositionServo 构造后，五种 effort profile 的真实 source 构建通过，MJCF／USD 十组 physical Controller 合同与输入版本一致；最终静态检查确认 effort 的实际 Controller 身份和来源记录。Isaac effort 与正式 Position 分别完成两次 reset、一次 step、三帧独立读回和 Env／App 关闭，各观测 41 次 physics callback，采图期间无额外推进，订阅前启动推进未知；Position H5 有一条 transition 和两个 observation。两次 SDK 日志均有只读目录及渲染预热错误，读回和进程退出成功。原生运行之后只调整 PositionServo 的延迟导入及 effort 来源记录，最终代码已用静态 source 检查和版本检查复核，未再次重跑 GPU。GeoPhys、MuJoCo 和完整 Solution 本批未重跑。冻结各轮 diff、计划、对照和收据位于 ignored `workspace/maintenance/v211_usd_no_position_20261112_N3k8lC/`；E01～E04 仍未接收。

### 6.74 Task source 准备不再创建参考 Controller

输入 `f4ea172f`。PickCube 的 Task source 编译、reset readiness 和参考 Controller 原由同一函数一并构造，导致 MJCF／USD effort 即使不使用参考 Controller 也要创建它。现在共同 source 准备返回具名的 Task、source、配置与 readiness 结果；正式参考路线再构造自己的 Controller，两个 effort source 路线直接构造物理 Controller。Task、Robot、source 与 Controller 的实际构造关系得到分离；现有 source closure 和 Runtime 准入未放宽。

生产修改 2 文件 +60／−14，净增 46 行，主要是具名准备结果和 USD effort 的真实身份／配置组合；版本诊断修改 1 文件 +8／−3，验证 MJCF source、Scene 和 Controller 复用 Robot 且不创建参考 Controller；本文及当前状态文档修改 2 文件。没有新增、删除或整文件迁移，tracked 文件数保持 1358。provider／renderer、clock 和控制提交 owner 未改变；Task 的其余 source 专属构造仍待收敛。

91 项版本检查通过。禁止参考 Controller 与 USD PositionServo 构造后，五种 MJCF／USD effort 的十组真实 source／Controller 合同对照一致。最终代码的 MuJoCo 参考 R3 短程与 joint→R3 切换／H5 读回通过，共观测 15 个 native 子步。Isaac joint effort／同步 RGB 在具名结果整理之前完成两次 reset、step、三帧独立读回和关闭，观测 41 次 physics callback，采图期间无额外推进、订阅前启动推进未知；最终具名化结果已做十组静态合同和版本检查，未再次重跑 GPU。Isaac 日志有只读目录、渲染预热及 callback 取消订阅异常，进程和读回成功。GeoPhys 与完整 Solution 本批未重跑。各轮 diff、计划、对照及收据位于 ignored `workspace/maintenance/v211_task_source_without_controller_20261112_eALPcy/`；E01～E04 仍未接收。

### 6.75 USD 构造释放临时 Task source 快照

输入 `d2c88d65`。USD 构造借用 MJCF 快照准备 Task／readiness，返回的 Runtime 却拥有独立 USD source，原临时快照在成功返回及后续构造异常时均无 owner 清理。现在 USD 构造结束时关闭借用快照；失败时先保留原异常，再记录可能发生的清理异常。Runtime 的 USD source 和其资源由原有 owner 管理。此保护从 Task source 已成功返回后开始；source 准备内部更早失败的清理仍待单独检查。

生产修改 1 文件 +116／−104，净增 12 行，其中原有 USD 构造主体约 104 行仅缩进迁移以纳入失败清理范围；版本诊断修改 1 文件 +51／−0，覆盖 Position／effort 构造失败及清理异常；本文及当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1358。构建入口与 provider／renderer 的 source、状态、clock 和提交合同未改，减少的是失去 owner 的临时目录。

修改前的实际 USD effort 构造留下一个仍存在的快照；修改后实际 effort、Position 和缺失 manifest 三次构造各自的快照均在返回或抛错后消失。94 项版本检查通过。Isaac effort／Position 的 CUDA／同步 RGB 各完成两次 reset、step、三帧独立读回与 Env／App 关闭，各观测 41 个 physics callback，采图期间无额外推进，订阅前启动推进未知；Position H5 读回含一条 transition。两次 callback 取消订阅均报告 AttributeError，SDK 日志中的预热和关闭信息保留，进程及读回成功。MuJoCo、GeoPhys 与完整 Solution 本批未重跑，旧证据按不受临时 USD 准备快照生命周期影响的范围保留。前后快照检查、冻结 diff、计划和运行收据位于 ignored `workspace/maintenance/v211_usd_source_lease_20261112_oUDbRb/`；E01～E04 仍未接收。

### 6.76 Task source 失败前后资源归属

输入 `57b3b7ca`。PickCube 在创建快照之前先计算 readiness，失败时不再产生待回收的临时目录。共同 source 失败清理机制覆盖 PickCube 和 NutAssembly 参考 Controller 构造、USD source 身份准备以及 PickCube physical 早期构造；成功时资源继续交给原 owner，失败时释放已取得的 source，清理也失败时保留原异常并附加说明。既有物理绑定之后的资源归属保持原合同；这不代表全部生命周期问题均已解决。

生产修改 4 文件 +226／−201，净增 25 行，其中约 200 行增删来自将现有构造主体缩进到资源保护范围；版本诊断修改 1 文件 +114／−0，本文及当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1358。本批没有消除新的配置或任务构建分流；Runtime source 取得失败时的资源清理归于共同机制，provider／renderer 的状态、clock 和提交合同未改变。

100 项版本检查通过，新增检查覆盖 readiness、两个 tabletop Controller、USD 身份准备、physical 早期构造及清理异常。MJCF／USD 五种 profile 共十组 source 和 Controller 合同对照一致。PickCube 参考、NutAssembly 及 PickCube physical reset 切换／H5 读回的 MuJoCo 短程通过，共观测 20 个 native 子步；参考 Solution 仅验证单步。Isaac 和 GeoPhys 本批未重跑：6.75 的 Isaac 原生证据可说明当时代码的行为，但不能视为当前代码已完成 GPU 复验。完整 Solution 未运行。冻结 diff、合同对照及运行收据位于 ignored `workspace/maintenance/v211_task_source_failure_20261112_8RhmP8/`；E01～E04 仍未接收。

### 6.77 物理控制使用请求的 reset seed

输入 `a2764cbe`。PickCube MJCF／USD 物理 Controller 原先把 reset seed 限制在构造时的值，沿用了诊断用固定执行条件。MJCF 现在按请求 seed 编译 EpisodeResetPlan；USD 构造也接收实际 reset seed 和 horizon。外部 Solution 的共同重建流程在任务提供 seeded builder 时使用它，避免丢失请求的 seed；没有 seeded builder 的任务继续使用原外部 Solution builder。Runtime 仍核对 reset plan、Artifact 和 source 身份，物理提交、clock 与 renderer 未修改。

生产修改 3 文件 +14／−16，净减 2 行；版本诊断修改 2 文件 +63／−0，本文和当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1358。本批消除物理路线的固定 seed 限制，未消除其余任务构造分流。

104 项版本检查通过。MuJoCo joint 与可切换 R3 两种物理配置各完成不同 seed 的 reset 和 step、重复 seed 的采样一致性检查；R3 另完成使用新 seed 的外部 Solution reset。Isaac seeded builder 与共同 Solution 重建只做调用合同检查，本批未运行 Isaac 或 GeoPhys 原生路线，也未运行完整 Solution。首次测试错误地从动作空间随机采样，分别触发真实力限与动作代际检查；改用合法声明动作后通过。E01～E04 仍未接收。

### 6.78 reset profile 准入归任务声明

输入 `5d72d8d7`。共同配置类型只校验 reset profile 的字符串形式，配置解析器依据任务声明的 profile 集合准入；PickCube 自己检查该 profile 与 R3 Controller、重力补偿的组合。共同 Env 的控制请求错误信息也不再指定 NutAssembly。现有 profile 的任务特定 observation／reset 实现仍在，尚需继续整理或决定退出，本批不将它描述为通用能力。

生产修改 4 文件 +14／−8，净增 6 行；版本诊断修改 1 文件 +23／−0，本文及当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1358。共同配置与 Env 减少具体任务名称，四任务仍使用既有正式构建入口；provider／renderer 的 source、状态、clock、提交和资源合同未改变。

109 项版本检查通过，覆盖受声明约束的任务 reset profile、PickCube 不支持的组合以及既有配置等价检查。四个正式任务的 MuJoCo 短程各完成 reset、step、再次 reset 和关闭，分别观察 PickCube 5、NutAssembly 5、Pendulum 25、双轮车 25 个 native 子步；其中 NutAssembly 为 Solution 单步，不代表完整成功。GeoPhys、Isaac 及完整 Solution 本批未重跑；历史证据只证明当时代码和具体路线。冻结 diff、计划与运行收据位于 ignored `workspace/maintenance/v211_formal_config_20261112_fv3hdj96/`；E01～E04 仍未接收。

### 6.79 Robot 声明位置驱动重力补偿能力

输入 `9f5bf4b3`。共同配置此前允许 Pendulum、双轮车或装配 Panda 选择只适用于已支持一体 Panda 位置驱动路线的重力补偿，并在原生物化后才可能失败。现在一体 Panda 声明该控制能力，统一配置根据实际 Robot 选择在构建前核对；现有 MuJoCo CPU／进程和 Controller 组合约束不变。Robot 的能力声明不代替 provider 对 source、驱动和 native 物化的检查，也不表示所有 Panda source 都已支持。

生产修改 2 文件 +11／−0；版本诊断修改 2 文件 +27／−1，其中 probe 增加正式配置选项；本文及当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1358。四任务继续使用共同配置解析，减少的是不支持 Robot 的无效构建；renderer、状态、clock 和控制提交合同未改。

114 项版本检查通过，包含不支持 Robot 的静态拒绝和两个 tabletop 的能力准入。MuJoCo 下 PickCube 与 NutAssembly 均以重力补偿完成 reset、step、再次 reset 和关闭，各观察 5 个 native 子步；NutAssembly 的 Solution 只验证单步。GeoPhys、Isaac、完整 Solution 本批未重跑，历史证据仅证明当时代码和具体路线。冻结 diff、计划及运行收据位于 ignored `workspace/maintenance/v211_robot_gravity_20261112_h1qsas2z/`；E01～E04 仍未接收。

### 6.80 退出 NutAssembly 历史诊断构建分支

输入 `328a3dde`。删除只服务 R05b／gripper cadence 历史诊断的任务构造、专属 source 快照、Solution 入口和公共 Env 的专属 reset 策略；同时删除仅供旧 R05b／R05c 诊断调用的 Runtime 固定身份准入及诊断常量文件。正式 NutAssembly 的 Controller、native feedback 样本、ExpertAction、共同控制提交、source 和 capability 准入保持。R05c 资格限制及已有历史证据不因删除入口而改变；当前能力以正式路线的实际证据为准。

生产范围 8 文件：修改 7、删除 1，+29／−476，净减 447 行；无整文件迁移。版本诊断代码未修改；任务 API 文档修改 2 文件 +4／−12，本文及当前状态文档另修改 2 文件。项目 tracked 文件从 1358 减至 1357。本批移除了正式 Env 构造中一条历史诊断分流；四任务现有构建入口、provider／renderer 的 source、状态、clock 和提交合同未因此扩展。

114 项版本检查通过。最终代码的四个正式任务 MuJoCo 短程完成 reset、step、再次 reset 和关闭，分别观察 5、5、25、25 个 native 子步；NutAssembly GeoPhys CPU 同样完成上述生命周期，控制时间从 0 推进至 0.01 秒，native 子步未在此探针计数。NutAssembly 只验证 Solution 单步，完整 Solution 及 Isaac 未重跑。冻结 diff、计划及运行收据位于 ignored `workspace/maintenance/v211_retire_nut_final_20261112_q4fcwqw_/`；E01～E04 仍未接收。

### 6.81 USD Position 使用 Panda 主体和实际 Controller plan

输入 `5346ccd9`。Isaac Position 路线原有 source-bound Controller，但没有通过 Panda 共同机制编译主体，`env.robot` 无主体。现在 Panda 对实际 USD Scene、source、Artifact 和 Controller 编译同一 Assembly／主体及 Controller plan；共同 Runtime 物化使用该 plan，RobotRuntime 暴露已编译的主体与实际 Controller。source 自身仍没有与 MJCF 相同的 position subject binding，native Position 适配与剩余 source 组合尚待继续收敛。

生产修改 4 文件 +25／−2，净增 23 行；版本诊断修改 1 文件 +26／−0，本文及当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1357。新 plan 在构造与物化时核对 Scene、Artifact、source、writer 和资源；provider 的原有 native 映射及 renderer、clock、提交机制未改。

115 项版本检查通过，包括本机已验证 USD delivery 的实际主体／Controller／物化 plan 合同；未提供该 delivery 时对应检查跳过。Isaac CUDA Position／同步 RGB 完成两次 reset、一次非零 step、三帧独立读回、Env／App 关闭；主体 writer 和 plan 与实际 Controller 一致，匹配检查全部通过。观察到 41 次 physics callback，订阅前启动推进未知；callback 取消订阅报告 AttributeError，SDK 日志保留渲染预热和只读目录错误，进程及独立读回成功。MuJoCo 一体 Panda、装配 Panda 和 NutAssembly 短程均通过，各观测 5 个 native 子步。GeoPhys 和完整 Solution 本批未重跑。冻结 diff、资源预算及证据位于 ignored `workspace/maintenance/v211_usd_robot_position_20261112_7u90vfp_/` 与 `workspace/maintenance/v211_panda_position_20261112_cmzuogv9/`；E01～E04 仍未接收。

### 6.82 Controller 切换限定于 reset

输入 `86c887f4`。G04 明确要求拒绝 episode 内切换，旧的 `switch_position_controller` 却可在运行中替换实例，并依赖专属的状态迁移、Runtime 提交和录像事件。该入口现在明确拒绝并指向 reset；删除只服务它的 Controller 激活、提交和 pending 录像状态。按 reset 选择 Controller 的正式能力保留，历史录像格式和已接收证据不因此改写。

生产修改 4 文件 +4／−406，净减 402 行；版本诊断修改 1 文件 +7／−0，本文及当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1357。共同生命周期不再容纳与 G04 相悖的 episode 内替换旁路；Runtime 的正常 source／状态／clock／提交和 renderer 合同未改。

115 项版本检查通过，包括真实 reset 后拒绝 episode 内更换且保持 Controller 与状态边界、随后可正常 step。MuJoCo 下 joint→R3 reset 切换和 H5 读回通过，观察 10 个 native 子步；参考 Position 录像短程另观察 5 个子步。Isaac CUDA Position／同步 RGB 完成两次 reset、一次非零 step、三帧独立读回和关闭，观察 41 次 physics callback，订阅前启动推进未知；callback 取消订阅报告 AttributeError，SDK 关闭日志有异常但进程和独立读回成功。GeoPhys、完整 Solution 本批未重跑。冻结 diff、预算与收据位于 ignored `workspace/maintenance/v211_position_reset_only_20261112_18r1w8rp/` 和 `workspace/maintenance/v211_reset_only_cpu_20261112_cnchvs06/`；E01～E04 仍未接收。

### 6.83 USD Position 主体和 plan 由 source 持有

输入 `f6010606`。上批 USD Position 将主体及编译 plan 放在 Task 构造结果的单独字段；现在 USD RuntimeSource 持有带身份的主体／Controller plan，RobotRuntime 与 Position 物化从同一个 source 读取，Task 结果不再另存这两份信息。source 校验 plan 与 Scene、Artifact、source closure、主体身份一致，Runtime 拒绝与 source 不一致的 plan。MJCF source 通过同一主体 plan 接口暴露已有绑定；USD 的两个手指 native 目标和 MJCF 单 actuator 映射仍由各自 adapter 负责，不伪造相同映射。

生产修改 4 文件 +52／−5，净增 47 行；版本诊断修改 1 文件 +12／−4，本文及当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1357。新增类型承载实际编译 plan 和受控主体的身份，并参与 Runtime 物化；并非另建 Env。其他任务构造分流仍需处理；renderer、clock 和物理提交 owner 未改。

115 项版本检查通过，包括真实 USD source 的主体／Controller plan 同源，以及外来 source 主体拒绝。Isaac CUDA Position／同步 RGB 完成两次 reset、一次非零 step、三帧独立读回和关闭，Scene、Artifact、source、writer 与资源匹配检查全部通过；观察 41 次 physics callback，订阅前启动推进未知。callback 取消订阅报告 AttributeError，SDK 日志仍有只读目录、渲染预热及关闭异常，进程和独立读回成功。MuJoCo 一体 Panda、装配 Panda、NutAssembly、Pendulum 和双轮车短程均通过，分别观察 5、5、5、25、25 个 native 子步。GeoPhys 和完整 Solution 本批未重跑。冻结 diff、预算及收据位于 ignored `workspace/maintenance/v211_usd_source_subject_20261112_1t8_kquu/` 和 `workspace/maintenance/v211_source_subject_cpu_20261112_8e7_3qjc/`；E01～E04 仍未接收。

### 6.84 Position Controller 匹配实际主体

输入 `39ff2a48`。Position Controller 选择此前以 profile 名称充当主体 ID，即使 source 已持有编译主体也没有核对。现在选择阶段必须消费 source 的主体／Controller plan，以实际 subject ID 形成匹配结果，检查每个 writer、Controller binding 和资源的完整归属；物化再次核对所用主体。缺少主体或主体 writer 与资源不一致时拒绝，不再回退到虚构主体。provider 的 native 映射、renderer、clock 与实际提交 owner 未改。

生产修改 3 文件 +21／−1，净增 20 行；版本诊断修改 1 文件 +7／−0，本文及当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1357。此修改使 Position 选择使用真实已编译主体，未完成四任务全部构造分流的收敛。

115 项版本检查通过，覆盖实际 subject ID、缺少 source 主体及错误 writer 的拒绝。Isaac CUDA Position／同步 RGB 最终代码完成两次 reset、一次非零 step、三帧独立读回和关闭，实际主体、writer、资源匹配通过；观察 41 次 physics callback，订阅前启动推进未知。此前宽松回退版本也做过一次原生运行并观察 41 次 callback，两个独立窗口的证据均保留；最终结论以严格版本的运行结果为准。两次 callback 取消订阅均报告 AttributeError，SDK 日志有只读目录、渲染预热及关闭异常，进程和读回成功。MuJoCo 一体 Panda、装配 Panda、NutAssembly、Pendulum 和双轮车短程均通过，分别观察 5、5、5、25、25 个 native 子步。GeoPhys 与完整 Solution 本批未重跑。冻结 diff、预算和收据位于 ignored `workspace/maintenance/v211_position_subject_match_20261112_a65b6cr0/`、`workspace/maintenance/v211_position_match_final_20261112_c85jc66z/` 和 `workspace/maintenance/v211_position_match_final_cpu_20261112_f8hx6xgr/`；E01～E04 仍未接收。

### 6.85 退出历史 C02b R1 typed-force 旁路

输入 `e7207128`。共同 Runtime 中仍有只接受历史 C02b 专属 TaskArtifact、固定源码和特定 Controller 身份的 typed actuator-force 准入及独立 interval 执行；四个正式任务没有调用它。删除该旁路及只供其使用的 MuJoCo／GeoPhys typed force 注入与投影分支。未准入的 typed actuator-force 请求继续明确返回 unavailable；正式任务使用的 native force 采样、有效性／边界检查、反馈及共同控制提交保留。此处不声称任意 source 的 typed actuator-force 发布已支持，历史 C02b 证据不改写。

生产修改 3 文件 +18／−582，净减 564 行；版本诊断修改 1 文件 +1／−0，用于选择正式 PickCube Controller；本文及当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1357。删除的是独立的旧诊断准入和施控分支，不改变正式任务的构建协议、renderer、clock 或推进 owner。

115 项版本检查通过。MuJoCo 下 PickCube R1、R3、装配 Panda、NutAssembly、Pendulum 与双轮车短程均通过，共观察 70 个 native 子步；PickCube R1 和 NutAssembly 的 H5 读回通过。NutAssembly GeoPhys CPU 完成 reset、Solution 单步、再次 reset 和关闭，控制时间从 0 推进至 0.01 秒，native 子步未计数。完整 Solution 和 Isaac 本批未重跑；旧 Isaac 证据只证明当时源码，F06 Position 的正式 source／Controller 物化路径未因本批旧 R1 分支删除而改变。冻结 diff、计划及运行收据位于 ignored `workspace/maintenance/v211_retire_c02b_r1_20261112_dtv9qnzj/`；E01～E04 仍未接收。

### 6.86 退出旧 leaf 专属物化与 actuator 旁路

输入 `1f2fc8a1`。共同 Runtime 曾为旧 leaf 诊断单独物化 plan、维护 interval／writer 状态并直接写 MuJoCo actuator；另有固定装配诊断直接写入口。四个正式任务没有使用这些入口，装配 Panda 的实际双 Controller 使用 source-owned 主体绑定与共同提交。现删除旧 leaf 的物化参数、专属 Provider 执行与直接写入，并简化 Position 物化合同；保留固定装配 source、原生映射及身份校验。历史 leaf codec／录像读回与其余历史辅助代码尚未在本批整理，不把历史证据转换成当前能力。

生产修改 5 文件 +25／−697，净减 672 行，其中 Position 物化去掉旧分支后约 20 行为缩进迁移；版本诊断修改 1 文件 +1／−1，本文及当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1357。删去两条不经正式任务共同控制链的旧诊断入口；provider 的正式 source、状态、clock、资源身份和控制提交不因此放宽，renderer 未改。

115 项版本检查通过。Isaac CUDA Position／同步 RGB 完成两次 reset、一次非零 step、三帧独立读回和关闭，观察 41 次 physics callback，订阅前启动推进未知；callback 取消订阅报告 AttributeError，SDK 日志有只读目录、渲染预热及关闭异常，进程和读回成功。MuJoCo 的四个正式任务及装配 Panda 短程均通过，分别观察一体 Panda 5、装配 Panda 5、NutAssembly 5、Pendulum 25、双轮车 25 个 native 子步；装配 Panda 的两个实际 writer 均出现在同一 acknowledged 提交。GeoPhys 与完整 Solution 本批未重跑。冻结 diff、预算与收据位于 ignored `workspace/maintenance/v211_retire_leaf_isaac_20261112_h66im01g/` 和 `workspace/maintenance/v211_retire_leaf_cpu_20261112_j4st0en4/`；E01～E04 仍未接收。

### 6.87 退出旧 leaf 控制提交与 dispatcher

输入 `734a7ee9`。旧 leaf dispatcher 及其预检、命令准备和专属 scene interval 已没有正式任务 caller，现从 Runtime 移除；共同提交不再接受由该入口外部注入的 interval、plan 和物化结果。正式 Position、effort 与序列仍由共同提交按实际 source、主体、Controller 和时钟生成 interval，并保留资源、身份、单位、冲突和故障检查。历史 H5 解码所需数据类型，以及 Isaac／GeoPhys 正式原生 Position 物化仍使用的类型保留；不为旧诊断恢复执行入口。

生产修改 3 文件 +51／−728，净减 677 行，其中共同提交约 48 行主要为移除旧分支后的缩进迁移；版本诊断未修改，本文与当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1357。此次删去一条旧诊断提交链，四任务构建入口与 renderer 没有改变；不能据此声称 E01～E04 已完成。

115 项版本检查通过。MuJoCo 下四个正式任务和装配 Panda 均完成短程，依次观察一体 Panda 5、装配 Panda 5、NutAssembly 5、Pendulum 25、双轮车 25 个 native 子步；装配 Panda 两个 writer 在同一提交中均被确认。另以 PickCube 物理 Controller 完成 reset 切换及 H5 读回，观察 10 个子步。两份已有历史 H5 通过现有 reader 读回，验证解码而非恢复旧运行路径。Isaac CUDA Position／同步 RGB 完成两次 reset、一次非零 step、三帧独立读回与关闭；观察 41 次 physics callback，订阅前启动推进未知。callback 取消订阅仍报告 AttributeError，SDK 日志有只读目录、渲染预热与关闭异常，但进程和独立读回成功。GeoPhys 和完整 Solution 本批未重跑；历史证据仅证明其具体受测代码与路线。冻结 diff、预算及收据位于 ignored `workspace/maintenance/v211_retire_leaf_dispatch_20261112_589tdcfx/` 和 `workspace/maintenance/v211_retire_leaf_dispatch_cpu_20261112_gyk_7vmw/`。

### 6.88 退出旧 mixed-actuator candidate 的 Env 生命周期

输入 `0840e833`。历史 mixed-actuator candidate 是一套只由旧诊断构建的独立 Env／Controller 绑定，四个正式任务没有声明其构建或控制 hooks。删除该入口，以及其专属 reset 重建、观察、施控、录像、Stop／close、worker 准入和 selected Runtime 物化分支；正式任务继续使用共同 reset 与控制提交，身份、单位、时钟、资源和故障检查不随该入口放宽。与之不同的 Position／physical 组合提交代码保留；本批未实际验证该组合，不能据此声明它受支持。provider 内仍有历史 mixed-actuator 原语，未在本批完整清理。

生产修改 10 文件 +58／−779，净减 721 行；其中部分新增为去除条件分支后的代码缩进迁移，无整文件迁移。版本诊断未修改，本文与当前状态文档修改 2 文件；无新增或删除文件，tracked 文件数保持 1357。本批消除的是旧诊断的专属 Env 生命周期，未改变四个任务的配置入口，也未完成 E01～E04 的全部构造收敛。

115 项版本检查通过。MuJoCo 的四个正式任务及装配 Panda 完成短程，一体 Panda、装配 Panda、NutAssembly、Pendulum、双轮车分别观察 5、5、5、25、25 个 native 子步；装配两个 writer 在同一提交中均获确认。PickCube 物理 Controller 的 reset 切换及 H5 读回通过，观察 10 个子步。NutAssembly GeoPhys CPU 完成 reset、Solution 单步、再次 reset 和重复关闭，控制时间从 0 推进至 0.01 秒；native 子步未计数，导入日志含 MJCF 语义诊断。Isaac CUDA Position／同步 RGB 完成两次 reset、一次非零 step、三帧独立读回和关闭，观察 41 次 physics callback，订阅前启动推进未知；callback 取消订阅仍报告 AttributeError，SDK 日志有只读目录、渲染预热及关闭异常，进程和读回成功。本批未执行完整 Solution。冻结 diff、预算及收据分别位于 ignored `workspace/maintenance/v211_retire_mixed_cpu_20261112_9fmd71fa/`、`workspace/maintenance/v211_retire_mixed_geophys_20261112_kmd1habf/` 和 `workspace/maintenance/v211_retire_mixed_isaac_20261112_17i725j0/`；E01～E04 仍未接收。

### 6.89 USD Position 直接准备 Task source

输入 `a813e684`。PickCube 的 Isaac Position 原来先通过 MJCF 参考构造创建 Controller，再丢弃它并创建实际使用的 USD Position Controller。现在 USD Position 与 USD effort 均从不创建 Controller 的共同 Task source／readiness 准备开始，随后各自按已选控制语义构造实际 Controller。source 身份、真实主体／Controller plan 准入和失败清理保留；当前准备仍借用并关闭临时 MJCF Task 快照，尚未完成所有 source 构造职责归位。

生产修改 1 文件 +12／−16，净减 4 行，其中既有 effort 分支的大部分代码迁到共同准备路径；版本诊断修改 1 文件 +5／−1，本文与当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1357。减少一次不参与执行的 Controller 构造；四任务的共同配置入口、Runtime 控制提交和 renderer 合同未改变，不将此局部变化视作 E02 完成。

115 项版本检查通过，其中 USD Position 的真实 source 构造明确禁止创建旧 MJCF 参考 Controller，同时核对实际 Robot、source 和 Controller plan。Isaac CUDA Position／同步 RGB 完成两次 reset、一次非零 step、三帧独立读回和关闭；观察 41 次 physics callback，订阅前启动推进未知。callback 取消订阅仍报告 AttributeError，SDK 日志有只读目录、渲染预热及关闭异常，进程和独立读回成功。MuJoCo、GeoPhys、Isaac effort 和完整 Solution 本批未重跑，其旧证据只证明具体受测版本与路线。冻结 diff、预算及收据位于 ignored `workspace/maintenance/v211_usd_position_task_source_20261112_vncixp28/`；E01～E04 仍未接收。

### 6.90 native Position 按 Controller 声明核对关节

输入 `02c508df`。共同控制物化此前在已完成 USD source 准入后，又在 F06 分支写死 PickCube 的九个 Joint／native 名称；F04 则有另一套覆盖检查。现在两条 native Position 物化共用检查：按实际 Controller 声明核对完整 Joint 集合、唯一 native target 及延迟 drive receipt。F06 原有 source 准入仍校验带固定身份的完整绑定表、Artifact、Scene、交付和执行身份；此次没有放宽该准入或将 F06 提升为通用 USD 支持。

生产修改 1 文件 +9／−15，净减 6 行；版本诊断修改 1 文件 +8／−0，本文与当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1357。共同控制物化减少具体任务关节名称和重复分支，任务专属 USD 准入仍在 Runtime 的既有位置，尚需继续归位；renderer、clock 和提交 owner 未改。

115 项版本检查通过，包含对篡改的 USD native target 映射在 source 准入处的拒绝。Isaac CUDA PickCube Position／同步 RGB 完成两次 reset、一次非零 step、三帧独立读回和关闭；观察 41 次 physics callback，订阅前启动推进未知。callback 取消订阅仍报告 AttributeError，SDK 日志有只读目录、渲染预热及关闭异常，进程和独立读回成功。F04、MuJoCo、GeoPhys 和完整 Solution 本批未重跑；不能将 F06 的结果扩展到这些路线。冻结 diff、预算及收据位于 ignored `workspace/maintenance/v211_native_position_binding_20261112_yh9ip87m/`；E01～E04 仍未接收。

### 6.91 native feedback 只消费 source-owned 主体绑定

输入 `e14d4135`。共同 Runtime 曾在 native-feedback 控制缺少 source 主体绑定时，额外创建旧 source／Controller 绑定，使用独立 boundary scope 和 scene interval；普通及隔离 worker 都维护该旁路。现在 native-feedback 控制要求 source 已持有编译主体绑定，缺失时在物化前拒绝；boundary、提交和 worker 均消费同一 source 及其主体绑定。删除旧绑定、重复 interval 和相关 fallback，保留主体路径的身份、资源、时钟及单次提交检查。USD Position 自有的 source／Controller plan 路径继续使用其对应的物化合同。

生产范围 8 文件：修改 7、删除 1，+7／−203，净减 196 行，无整文件迁移；版本诊断修改 1 文件 +9／−0，本文与当前状态文档修改 2 文件。项目 tracked 文件由 1357 减至 1356。本批移除旧诊断旁路而使正式 native feedback 依赖真实主体，不表示全部任务构造和 adapter 的职责已经收敛。

116 项版本检查通过，包括缺少 source 主体时在物化前拒绝。MuJoCo 四任务与装配 Panda 的进程内短程通过，一体 Panda、装配 Panda、NutAssembly、Pendulum、双轮车分别观察 5、5、5、25、25 个 native 子步；PickCube 物理 Controller reset 切换与 H5 读回通过，观察 10 个子步。PickCube 与 NutAssembly 的 MuJoCo 隔离 worker 均完成 reset、step、再次 reset 和关闭；worker native 子步未直接计数，每次按 50 保守预算记账。NutAssembly GeoPhys CPU 完成同类生命周期和 Solution 单步，控制时间从 0 推进至 0.01 秒，native 子步未计数，MJCF 导入有语义诊断。Isaac CUDA Position／同步 RGB 完成两次 reset、一次非零 step、三帧独立读回和关闭；观察 41 次 physics callback，订阅前启动推进未知。callback 取消订阅仍报告 AttributeError，SDK 日志有只读目录、渲染预热及关闭异常，进程和读回成功。本批未执行完整 Solution。冻结 diff、预算及收据位于 ignored `workspace/maintenance/v211_native_subject_only_20261112_yhysmfg5/` 和 `workspace/maintenance/v211_native_subject_isaac_20261112_krix37zp/`；E01～E04 仍未接收。

### 6.92 正式构造要求真实 Robot 主体

输入 `eb76c1e2`。共同构造此前允许 Controller 选择后没有已编译主体的结果进入 Env，直到访问 Robot 或执行控制时才暴露问题。现在共同 Env 构造要求 source／物理执行提供实际 Robot 主体，缺失时立即失败，并沿既有构造失败路径释放 source；该检查覆盖 grouped 和 native 控制，不创建虚构主体或额外 Controller。

生产修改 1 文件 +2／−0；版本诊断修改 1 文件 +25／−0，本文与当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1356。四任务继续使用现有共同配置入口及各自已编译主体；新增准入不改变 provider／renderer 的 source、clock、状态或提交合同。该约束不能单独证明四任务的全部构造职责已经统一。

118 项版本检查通过，其中两个 tabletop 在移除主体绑定时均于正式构造失败并释放已准备的 source。四个正式任务及装配 Panda 的 MuJoCo 短程通过，一体 Panda、装配 Panda、NutAssembly、Pendulum、双轮车分别观察 5、5、5、25、25 个 native 子步；PickCube 物理 Controller reset 切换与 H5 读回通过，观察 10 个子步。此前 Isaac 原生短程明确记录了实际 Robot 主体、Controller 和 source plan，本批仅新增非空构造准入且 USD 构造合同检查通过，但未按本批源码重跑 Isaac；GeoPhys、worker 与完整 Solution 同样未重跑。冻结 diff、预算及收据位于 ignored `workspace/maintenance/v211_require_constructed_robot_20261112_bzvetg39/`；E01～E04 仍未接收。

### 6.93 Controller 选择核对主体计划中的实际 owner

输入 `ea73fc89`。MJCF source 已持有编译后的主体和 Controller plan，但选择 Controller 时此前没有核对 plan 中的身份是否仍与实际对象一致。现在选择阶段对一体 Controller 核对身份，对多 owner Controller 同时核对每个 writer 和身份，并要求计划提供身份；不匹配时在构造／重建阶段拒绝。检查位于共同 Controller 选择，而 RobotRuntime 继续只暴露已绑定结果。物理 Controller 的既有 source 匹配和 USD typed Position 的独立匹配未改。

生产修改 1 文件 +13／−0；版本诊断修改 1 文件 +24／−0，本文与当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1356。新增代码核对实际主体 plan 与 Controller owner，不能单独证明 E02 全部构造职责已经统一；provider／renderer 的状态、clock、提交和资源生命周期未改。

120 项版本检查通过，包含一体与装配 Panda 的 Controller 被替换后拒绝。四个正式任务和装配 Panda 的 MuJoCo 进程内短程通过，一体 Panda、装配 Panda、NutAssembly、Pendulum、双轮车分别观察 5、5、5、25、25 个 native 子步；PickCube 物理 Controller reset 切换与 H5 读回通过，观察 10 个子步。PickCube、NutAssembly 的 MuJoCo 隔离 worker 完成 reset、step、再次 reset 和关闭；worker native 子步未直接计数，每次按 50 保守预算记账。NutAssembly GeoPhys CPU 完成相同生命周期和 Solution 单步，控制时间从 0 推进至 0.01 秒，native 子步未计数，MJCF 导入有语义诊断。Isaac 和完整 Solution 本批未重跑，不能以这些短程结果替代完整成功证据。冻结 diff、预算及收据位于 ignored `workspace/maintenance/v211_controller_source_match_final_20261112_idjnahua/`；E01～E04 仍未接收。

### 6.94 默认 Robot 在共同配置中确定

输入 `e9b2a1bd`。四个正式任务此前在配置解析后仍由任务 binding 或 source composer 各自补默认 Robot，`robot_uid=None` 同时表示尚未填默认值。现在共同解析器根据任务声明选择并注册校验实际 Robot UID，默认与显式选择相同 Robot 得到同一个已解析配置；Pendulum、双轮车和 source composer 直接消费该 UID。reset 配置切换保留已选择的 Robot。PickCube split 控制的 Robot／profile 适配继续由实际 Robot recipe 准入，不再要求用户仅为消除空值而重复显式选择。Isaac 的默认 Panda 使用其实际 USD 主体路线；不因此扩展其他 Robot 的 provider 能力。

生产修改 7 文件 +19／−23，净减 4 行；版本诊断修改 1 文件 +16／−0，本文与当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1356。本批删除多个默认 Robot 回退点，使四任务配置结果直接携带实际选择；构建链中的其他任务／source 分流仍需处理。provider／renderer 的状态、clock、提交和资源合同未改。

124 项版本检查通过，包括四任务默认与显式 Robot 的配置等价和已解析配置重建。四个正式任务及装配 Panda 的 MuJoCo 进程内短程通过，一体 Panda、装配 Panda、NutAssembly、Pendulum、双轮车分别观察 5、5、5、25、25 个 native 子步；PickCube 物理 Controller reset 切换与 H5 读回通过，观察 10 个子步。PickCube、NutAssembly 的 MuJoCo 隔离 worker 完成 reset、step、再次 reset 和关闭；worker native 子步未直接计数，每次按 50 保守预算记账。NutAssembly GeoPhys CPU 完成同类生命周期和 Solution 单步，控制时间从 0 推进至 0.01 秒，native 子步未计数，MJCF 导入有语义诊断。Isaac CUDA 默认 Panda Position／同步 RGB 完成两次 reset、一次非零 step、三帧独立读回和关闭，观察 41 次 physics callback，订阅前启动推进未知；callback 取消订阅仍报告 AttributeError，SDK 日志有只读目录、渲染预热及关闭异常，进程和读回成功。本批未执行完整 Solution。冻结 diff、预算及收据位于 ignored `workspace/maintenance/v211_resolved_robot_uid_20261112_ri21v2z_/` 和 `workspace/maintenance/v211_resolved_robot_uid_isaac_20261112_pta2301d/`；E01～E04 仍未接收。

### 6.95 Controller profile 在共同配置中确定

输入 `0f916410`。NutAssembly 的配置此前记录空 Controller profile，实际构造却固定使用 R3；Pendulum 与双轮车的共同 effort builder 也会在解析后再次补默认 profile。现在 NutAssembly 声明其实际使用的 `r3_continuous_v1`，四任务的共同解析均要求已声明的非空 profile，共同 effort builder 直接消费解析结果。NutAssembly 仍使用其既有 R3 参数和 native-feedback 控制语义，此变化不表示支持其他 Controller 或 provider 组合。

生产修改 3 文件 +5／−5，净变化 0；版本诊断修改 1 文件 +11／−1，本文与当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1356。本批使四任务已解析配置表达实际 Controller 选择，消除两个普通任务构造时的默认回退；其他任务构造职责尚未收敛。provider／renderer 的 source、状态、clock、提交和资源合同未改变。

128 项版本检查通过，包括四任务空 profile 拒绝及 NutAssembly R3 的 YAML／mapping／已解析配置往返。四任务及装配 Panda 的 MuJoCo 进程内短程通过，一体 Panda、装配 Panda、NutAssembly、Pendulum、双轮车分别观察 5、5、5、25、25 个 native 子步；PickCube 物理 Controller reset 切换与 H5 读回通过，观察 10 个子步。PickCube、NutAssembly 的 MuJoCo 隔离 worker 完成 reset、step、再次 reset 和关闭；worker native 子步未直接计数，每次按 50 保守预算记账。NutAssembly GeoPhys CPU 完成相同生命周期和 Solution 单步，控制时间从 0 推进至 0.01 秒，native 子步未计数，MJCF 导入有语义诊断。Isaac 的既有默认 R3 选择未改，本批未重跑 Isaac 或完整 Solution；旧证据仍只证明各自受测源码和路线。冻结 diff、预算及收据位于 ignored `workspace/maintenance/v211_resolved_controller_profile_20261112_g4vcow4m/`；E01～E04 仍未接收。

### 6.96 tabletop 参考 Controller 构造归共同 owner

输入 `5969bc83`。PickCube 原来在任务文件中按 R1、split 和 R3 分别创建具体 Controller，NutAssembly 另行直接创建 R3。现在这些参考 Position profile 的实际选择和构造由 Controller 模块的共同入口负责；两个任务提供已选 profile、source 和各自的控制参数，继续负责自身 Solution 与执行元数据。PickCube 的 profile 集合也改为消费同一 Controller 声明，装配 Panda 的两个实际 Controller 仍由该入口构造并由原主体 plan 绑定。此变化针对 MJCF 参考控制，不声称 USD Position、effort 和普通任务已合成同一实现。

生产修改 3 文件 +41／−28，净增 13 行；其中 profile 分支和声明由任务移至 Controller owner，属代码职责迁移而非新增一条任务构建路径。版本诊断修改 1 文件 +14／−5，本文与当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1356。四任务配置入口不变，provider／renderer 的 source、状态、clock、提交和资源合同未改变；其他任务构造及 source 分流仍需收敛。

128 项版本检查通过，包含两个 tabletop 实际消费共同 Controller 构造结果。MuJoCo 下 PickCube R1、R3、装配 Panda、NutAssembly、Pendulum、双轮车及 PickCube 物理 Controller 短程通过，分别观察 5、5、5、5、25、25、10 个 native 子步；R1 和物理 Controller 的 H5 读回通过。PickCube、NutAssembly 的 MuJoCo 隔离 worker 完成 reset、step、再次 reset 和关闭；worker native 子步未直接计数，每次按 50 保守预算记账。NutAssembly GeoPhys CPU 完成同类生命周期和 Solution 单步，控制时间从 0 推进至 0.01 秒，native 子步未计数，MJCF 导入有语义诊断。Isaac Position 未调用该 MJCF Controller 入口，本批未重跑 Isaac 或完整 Solution；旧证据仍只证明各自受测源码和路线。冻结 diff、预算及收据位于 ignored `workspace/maintenance/v211_reference_controller_owner_20261112_w7w93e81/`；E01～E04 仍未接收。

### 6.97 Solution 诊断别名退出 Controller 配置

输入 `bfab5aab`。历史 `r3_continuous_v1_pose_path_x20` 只切换 PickCube Solution 的姿态绕行，历史对照中 Controller 身份与普通 R3 相同；它不应作为另一种 Robot／Controller profile。现在该别名从共同 Controller 声明、Panda source recipe 和正式任务选择退出，普通 R3 仍使用原有 Solution 默认路径。Solution 类中的可选绕行实现尚在，本批未删除或验证它；历史对照证据保留。

生产修改 3 文件 +3／−8，净减 5 行；版本诊断修改 1 文件 +8／−0，本文与当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1356。正式配置消除一个把 Solution 选择伪装为 Controller 的分流；provider／renderer 的 source、状态、clock、提交和资源合同未改，Panda recipe 身份随声明变化。

129 项版本检查通过，包含旧别名从正式 Controller 配置拒绝。四任务及装配 Panda 的 MuJoCo 进程内短程通过，一体 Panda、装配 Panda、NutAssembly、Pendulum、双轮车分别观察 5、5、5、25、25 个 native 子步；PickCube 物理 Controller reset 切换与 H5 读回通过，观察 10 个子步。PickCube、NutAssembly 的 MuJoCo 隔离 worker 完成 reset、step、再次 reset 和关闭；worker native 子步未直接计数，每次按 50 保守预算记账。NutAssembly GeoPhys CPU 完成同类生命周期和 Solution 单步，控制时间从 0 推进至 0.01 秒，native 子步未计数，MJCF 导入有语义诊断。Isaac CUDA 默认 R3 Position／同步 RGB 完成两次 reset、一次非零 step、三帧独立读回和关闭，观察 41 次 physics callback，订阅前启动推进未知；callback 取消订阅仍报告 AttributeError，SDK 日志有只读目录、渲染预热及关闭异常，进程和读回成功。本批未执行完整 Solution。冻结 diff、预算及收据位于 ignored `workspace/maintenance/v211_retire_planner_alias_20261112_gmxd_5rp/` 和 `workspace/maintenance/v211_retire_planner_alias_isaac_20261112_7z_9i7kd/`；E01～E04 仍未接收。

### 6.98 清除退休姿态绕行的 Solution 分支

输入 `f592e8bb`。旧 20° 姿态绕行原只由已退休的诊断 Controller 别名选择，正式 R3 始终采用原始路径。删除该可选路径、专属配置和四元数辅助函数，正常路径直接连接垂直、横向和下降段；保留原有 7 次规划预算作为余量，不缩短正常 Solution 的动作时限。配置／元数据变化使 Solution 身份变化；历史对照和原有接收结论保留，但不能把历史身份当成本版新证据。

生产修改 2 文件 +6／−65，净减 59 行；版本诊断修改 1 文件 +7／−5，增加正式 PickCube Solution 单步探针；本文与当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1356。移除的是退休诊断的 Task／Solution 分流，Robot／Controller、provider／renderer 的 source、状态、clock、提交和资源合同未变。

129 项版本检查通过。四个正式任务及装配 Panda 的 MuJoCo 进程内短程通过，一体 Panda、装配 Panda、NutAssembly、Pendulum、双轮车分别观察 5、5、5、25、25 个 native 子步；PickCube 物理 Controller reset 切换与 H5 读回通过，观察 10 个子步。PickCube 正式 R3 Solution 在 MuJoCo 完成 reset、一个 Solution step、H5 逻辑读回及再次 reset，观察 5 个子步；GeoPhys 同一 Solution 完成 reset、单步和再次 reset，控制时间从 0 推进至 0.01 秒，native 子步未计数，MJCF 导入有语义诊断。PickCube MuJoCo 隔离 worker 完成 reset、step、再次 reset 和关闭；worker native 子步未直接计数，按 50 保守预算记账。Isaac CUDA 默认 R3 Position／同步 RGB 完成两次 reset、一次非零外部 action、三帧独立读回和关闭，观察 41 次 physics callback，订阅前启动推进未知；callback 取消订阅仍报告 AttributeError，SDK 日志有只读目录、渲染预热及关闭异常，进程和读回成功。上述 Solution 证据均为单步，本批未执行完整 Solution。冻结 diff、预算及收据位于 ignored `workspace/maintenance/v211_retire_posture_detour_20261112_8wuqh_ao/` 和 `workspace/maintenance/v211_retire_posture_detour_isaac_20261112_al0n6izh/`；E01～E04 仍未接收。

### 6.99 Controller profile 只有一个配置 owner

输入 `ff99e9ea`。`ResolvedSelectedConfig` 此前同时保存外层 `controller_profile` 和 `environment.control.profile_id`，解析时需要维护两份值。现在实际值只存于已解析 control 配置，外层同名读取属性直接返回它；构造器不再接受第二份 Controller profile。直接使用 dataclass 序列化时外层不再产生重复字段，正式记录配置仍从该属性写入规范 `controller.profile_id`。

生产修改 2 文件 +5／−2，净增 3 行；版本诊断修改 1 文件 +13／−0，本文与当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1356。四任务及 reset／worker 均消费相同的 Controller 选择；这消除一个重复配置权威，不表示其余配置类型或构建链已经全部合并。provider／renderer 的 source、状态、clock、提交和资源合同未改。

130 项版本检查通过，包括 Controller profile 的单一存储、替换后的读取和已解析配置重建。四任务及装配 Panda 的 MuJoCo 进程内短程通过，一体 Panda、装配 Panda、NutAssembly、Pendulum、双轮车分别观察 5、5、5、25、25 个 native 子步；PickCube 物理 Controller reset 切换与 H5 读回通过，观察 10 个子步。PickCube、NutAssembly 的 MuJoCo 隔离 worker 完成 reset、step、再次 reset 和关闭；worker native 子步未直接计数，每次按 50 保守预算记账。NutAssembly GeoPhys CPU 完成相同生命周期及 Solution 单步，控制时间从 0 推进至 0.01 秒，native 子步未计数，MJCF 导入有语义诊断。Isaac 和完整 Solution 本批未重跑；旧证据仍只证明原受测源码和路线。冻结 diff、预算及收据位于 ignored `workspace/maintenance/v211_single_controller_config_20261112_x65s60e1/`；E01～E04 仍未接收。

### 6.100 执行选择由同一请求持有

输入 `c596cfc1`。正式已解析配置此前重复保存 provider、设备和默认 renderer，另有可为空的 `ExecutionSpecV2` 及缺失时补建旧分支。现在这三项只由必需的执行请求持有，外层属性直接读取；环境后端与请求后端必须一致。直接 dataclass 序列化时外层重复字段退出，已解析配置仍通过规范执行字段往返。请求中的默认 renderer 仍为 state-only，创建 Env 时另外声明的固定任务 RGB renderer 保持既有合同，并未归并或扩展。

生产修改 2 文件 +25／−21，净增 4 行，其中部分是移除旧条件后的缩进迁移；版本诊断修改 1 文件 +14／−0，本文与当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1356。四任务和 worker 现在读取同一执行选择，删除旧的无执行请求补建分流；环境配置与执行请求仍为不同职责的数据结构，其他构建分流尚未收敛。provider／renderer 的实际 source、状态、clock、提交和资源合同未改。

131 项版本检查通过，包括单一执行选择存储及缺少执行请求的拒绝。四任务及装配 Panda 的 MuJoCo 进程内短程通过，一体 Panda、装配 Panda、NutAssembly、Pendulum、双轮车分别观察 5、5、5、25、25 个 native 子步；PickCube 物理 Controller reset 切换与 H5 读回通过，观察 10 个子步。PickCube、NutAssembly 的 MuJoCo 隔离 worker 完成 reset、step、再次 reset 和关闭；worker native 子步未直接计数，每次按 50 保守预算记账。NutAssembly GeoPhys CPU 完成同类生命周期和 Solution 单步，控制时间从 0 推进至 0.01 秒，native 子步未计数，MJCF 导入有语义诊断。Isaac CUDA 默认 Position／固定任务 RGB 完成两次 reset、一次非零外部 action、三帧独立读回和关闭，观察 41 次 physics callback，订阅前启动推进未知；callback 取消订阅仍报告 AttributeError，SDK 日志有只读目录、渲染预热及关闭异常，进程和读回成功。本批未执行完整 Solution。冻结 diff、预算及收据位于 ignored `workspace/maintenance/v211_single_execution_config_20261112_xivc3c1e/` 和 `workspace/maintenance/v211_single_execution_config_isaac_20261112_wobwghqv/`；E01～E04 仍未接收。

### 6.101 正式任务不再直接进入 component 构造

输入 `d999fbff`。Pendulum 和双轮车虽然经 `make_env` 使用共同正式配置与 Task binding，类本身仍声明旧 component 构造；四个正式类也可通过直接实例化绕过统一入口。移除两个旧标志，并让四个正式类在缺少正式 Task binding 的直接实例化时明确拒绝；`make_env`／正式解析和共同 Task binding 继续是普通构建链。非本次四任务的 component 代码没有借此删除。旧 parallel factory 仍依赖早期 component 装配，未作为 G06 可用能力接收，后续并行工作需要接入新的共同合同。

生产修改 3 文件 +2／−2，净变化 0；版本诊断修改 1 文件 +15／−0，本文与当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1356。消除四个正式类直接调用旧构造的分流，未宣称所有历史组件代码或四任务的主体构造已收敛；provider／renderer 的 source、状态、clock、提交和资源合同未改。

135 项版本检查通过，包括四个正式类拒绝直接旧构造及正式工厂配置。四任务及装配 Panda 的 MuJoCo 进程内短程通过，一体 Panda、装配 Panda、NutAssembly、Pendulum、双轮车分别观察 5、5、5、25、25 个 native 子步；PickCube 物理 Controller reset 切换与 H5 读回通过，观察 10 个子步。PickCube、NutAssembly 的 MuJoCo 隔离 worker 完成 reset、step、再次 reset 和关闭；worker native 子步未直接计数，每次按 50 保守预算记账。NutAssembly GeoPhys CPU 完成同类生命周期和 Solution 单步，控制时间从 0 推进至 0.01 秒，native 子步未计数，MJCF 导入有语义诊断。Isaac 和完整 Solution 本批未重跑；旧证据仍只证明原受测源码和路线。冻结 diff、预算及收据位于 ignored `workspace/maintenance/v211_formal_construction_only_20261112_fwrdgypq/`；E01～E04 仍未接收。

### 6.102 共用 arm hold 与 ramp 请求合同

输入 `fce3a6ba`。两个 tabletop Solution 使用同一种 Controller hold／ramp 语义，但公共 Controller 硬编码两个任务专属请求标识，默认状态也写死 NutAssembly 名称。现在由 Controller 定义一个共同请求 profile，两条 Solution 及 PickCube Controller 身份元数据均引用它；保留请求 schema、三种模式、真实 applied acknowledgement、资源和有限数值检查。旧任务专属 profile 不再作为新请求兼容入口；历史记录仍按原身份解释。本次修改 Controller 源码及 PickCube 的身份元数据，不能将此前记录的 Controller 身份直接当作新源码身份。

生产修改 4 文件 +11／−13，净减 2 行；版本诊断修改 1 文件 +37／−0，本文和当前状态文档修改 2 文件；没有新增、删除或整文件迁移，tracked 文件数仍为 1356。共同请求删除了 Controller 对任务名称的依赖，但没有改变配置构建入口，也没有证明四任务 Robot 构造已经统一；tabletop source 编译与组合分别创建 Robot 的问题仍待处理。provider／renderer 的 source、状态、clock、资源合同未变；两条 Solution 的 arm 请求仍进入已有 Controller 校验和共同提交链。

137 项版本检查通过，包括两个 tabletop 的 hold、五个线性 ramp 子步、gripper 保持及先有反馈检查。PickCube、NutAssembly 的 MuJoCo 各完成一次 Solution 提交、5 个 native 子步、第二次 reset 和关闭；NutAssembly GeoPhys 完成同类生命周期及 Solution 单步，native 子步未直接计数。MJCF 导入有语义诊断。Isaac 和完整 Solution 本批未重跑，旧证据仍限定原源码身份；冻结 diff、预算和收据位于 ignored `workspace/maintenance/v211_shared_arm_request_20261112_q4uu7p3b/`。E01～E04 未因此整体接收。

### 6.103 source 组合复用已声明的 Robot

输入 `1516b404`。此前两个 tabletop 默认 Panda 路线由任务编译 Artifact 和 source 时创建一个 Robot，source composer 又按 UID 创建另一个 Robot 并交给 adapter。现在 composer 在每次 source 构建后查找身份匹配的已声明 Robot，将同一个实例交给 adapter；当选中的主体不在任务 source 中时，才按注册选择创建替换主体。重复身份仍被拒绝，Controller profile、source intent 和资源检查继续执行；profile 准入发生在 source 编译之后、adapter 组合之前，失败由现有 source 清理路径处理。

生产修改 1 文件 +9／−6，净增 3 行，其中 profile 检查随共同组合调用迁移；版本诊断修改 1 文件 +30／−0，本文和当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1356。新增版本检查直接证明 PickCube 与 NutAssembly 的 Artifact／source Robot 和 MuJoCo source adapter 使用同一实例；不等于任务声明、装配 Panda 的替换 source 和其他主体已统一构造。provider 仍通过既有 source recipe、intent 和 adapter 合同组合，状态、clock、控制提交和 renderer 资源合同未改。

139 项版本检查通过。PickCube、NutAssembly 与装配 Panda 的 MuJoCo 短程分别完成 5 个 native 子步、第二次 reset 和关闭；两个 tabletop 的隔离 MuJoCo worker 完成 reset、step、再次 reset 和关闭，worker native 子步未直接计数。NutAssembly GeoPhys 完成同类生命周期和 Solution 单步，native 子步未直接计数；MJCF 导入有语义诊断。Isaac source 没有注册本次更改涉及的 composer，未重跑；完整 Solution 未重跑。冻结 diff、预算和收据位于 ignored `workspace/maintenance/v211_source_robot_owner_20261112_oy7kp_rd/`。E01～E04 未因此整体接收。

### 6.104 PickCube effort 消费已解析配置

输入 `95ed3490`。PickCube 的正式 Position 路线使用解析时冻结的任务配置和环境配置，effort 路线却重新读取默认任务配置并丢弃已解析环境配置。现在 MJCF 与 Isaac effort 的绑定都接收正式解析所得的任务配置及环境配置，MJCF 构建不再二次读取任务配置；Isaac seeded 重建也沿同一 binding 传递它们。这样正式配置与执行实际消费的配置保持一致，旧配置重读路径退出；source、Controller 身份可能随实际配置变化，历史证据仍只对应原输入。

生产修改 2 文件 +17／−10，净增 7 行；版本诊断修改 2 文件 +30／−2，本文和当前状态文档修改 2 文件；无新增、删除或整文件迁移，tracked 文件数保持 1356。版本检查验证 MJCF effort 不会重载任务配置，并保留实际 profile 与 horizon；Isaac 纯合同检查验证 seeded builder 传入同一任务与环境配置。此次只收敛 PickCube effort 的配置所有权，没有取消其任务专属物理构建路径，也没有完成四任务统一构造。provider adapter 的 source 合同按输入的实际配置构建，状态、clock、提交与 renderer 合同未改。

140 项版本检查通过。MuJoCo 直接 effort 完成 5 个 native 子步和第二次 reset，MuJoCo joint effort 的 Controller reset 与 H5 读回完成 10 个子步；GeoPhys joint effort 完成 reset、step、第二次 reset 和关闭，native 子步未直接计数。MJCF 导入有语义诊断。受影响的 Isaac effort 本轮仅检查配置传递，未做真实 CUDA 复验；完整 Solution 未运行。冻结 diff、预算和收据位于 ignored `workspace/maintenance/v211_effort_config_owner_20261112_1qrzc718/`。

复核还发现：`make_reference_binding` 调用 USD builder 时未传 `lift_height_m`，USD Artifact 按默认值构造。这里更正本条初写的判断：正式解析器当时明确拒绝 Isaac 的所有任务参数，因此正式入口不会静默忽略该值；实际问题是 Isaac 不支持此覆盖，且内部 builder 没有贯通该值。后续处理见 6.105。E01～E04 未整体接收。

### 6.105 PickCube lift 参数贯通 position 与 effort

输入 `c4a5195e`。将 `lift_height_m` 从正式任务配置传至 Position 和 effort 的 MJCF／USD 任务声明、Artifact、reset 与任务评价；移除共同配置层对 Isaac 所有任务参数的笼统拒绝，PickCube 仍明确拒绝其 Isaac source 不支持的 Task force。旧 Isaac 入口对 lift 的拒绝和 builder 对参数的遗漏得到纠正，不扩大 provider 原生能力或任务范围。

生产修改 4 文件 +25／−19，净增 6 行；版本诊断修改 2 文件 +61／−0，本文和当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1356。145 项版本检查通过，包括两个控制模式在 MJCF 与 USD Artifact 的非默认任务语义，以及 USD reset 对同一 Artifact 的身份绑定。MuJoCo Position Solution 单步和直接 effort 分别完成 5 个 native 子步及再次 reset。Isaac Position 以 0.17 米 lift 完成 reset、非零 action、第二次 reset、同步 RGB 和独立三帧读回，观察 41 次 physics callback，订阅前启动推进未知；Runtime 和 reader 退出码均为 0，日志有只读目录、USD 包、渲染预热警告。首次 Isaac 尝试因诊断脚本在 SimulationApp 启动前加载 USD 引起扩展初始化冲突并退出 139，未进入物理推进；重试将 Artifact 身份移到独立进程计算，完整失败及预算记录保留。Isaac effort 本轮仅完成 USD Artifact／reset 合同检查，真实 CUDA effort 和完整 Solution 尚未复验。冻结 diff、预算和收据分别位于 ignored `workspace/maintenance/v211_lift_config_cpu_20261112_u4on4_61/` 与 `workspace/maintenance/v211_isaac_lift_20261112_svcug385/`。E01～E04 未整体接收。

### 6.106 PickCube TaskDefinition 退出旧索引诊断

输入 `a265736c`。`PickCubeTaskDefinition` 此前同时保留 Artifact 绑定的具名状态和只由旧诊断调用的 `TaskReferences` 索引式评价，后者再区分单行／批量并从本地默认 recipe 获取语义。删除旧 references、索引和批量 predicate 分支后，正式 TaskDefinition 直接消费同一个 Artifact 的语义及具名 Runtime 状态；保留已知成功判据、缺失状态和非有限值检查，不再为构造定义重复读取 recipe。G06 尚未实现，此处不声称具名批量状态已交付。

生产修改 1 文件 +23／−78，净减 55 行；版本诊断修改 1 文件 +25／−0，本文和当前状态文档修改 2 文件；无新增、删除或整文件迁移，tracked 文件数保持 1356。新增检查以冻结的 Artifact 验证非默认 lift 的 reset、评价和 predicate，且禁止构造时重载 recipe。此项只消除任务语义的旧诊断分流；Robot／Controller 的所有构造尚未统一。provider adapter 仍向相同 Runtime 状态及时间边界发布，renderer 合同未改。

146 项版本检查通过。当前源码下 MuJoCo Position 的 Solution 单步与直接 effort 各完成 5 个 native 子步及第二次 reset；GeoPhys joint effort 完成 reset、step、第二次 reset 和关闭，native 子步未直接计数。Isaac Position 非默认 lift 完成相同生命周期、RGB 及独立读回，观察 41 次 physics callback，订阅前启动推进未知；SDK 日志保留只读目录、USD 包和渲染预热警告。本项之前的 `a265736c` 还真实验证了 Isaac 直接 effort 在 0.17 米 lift 下的非零力矩、第二次 reset、RGB 和独立读回，观察 41 次 callback；该证据只对应 `a265736c`，当前 TaskDefinition 改动后没有再次重跑 Isaac effort。完整 Solution 未运行。

Isaac effort 验证中的两次提前退出也保留：首次是验证脚本误用 Position 专属断言；第二次暴露真实 recorder 限制——`selected_recording_metadata` 调用的 `provider_build_identity` 不接受 `isaacsim`，`start_recording` 因而报 `ValueError('unknown provider')`。去掉录制后 effort 控制路线通过；不能把它当作录制能力通过，录制修复留待 E10。冻结 diff、预算及收据位于 ignored `workspace/maintenance/v211_pickcube_named_final_20261112_tzr8tscd/`、`workspace/maintenance/v211_named_pickcube_isaac_20261112_rchuh6qq/`、`workspace/maintenance/v211_isaac_effort_lift_20261112_u8rdr1rn/` 和 `workspace/maintenance/v211_isaac_effort_state_20261112_wzke9iah/`。E01～E04 未整体接收。

### 6.107 退休两个普通任务的旧 component 与并行接线

输入 `34b0365c`。Pendulum 和双轮车正式单环境已通过声明的 Robot、Controller 和共同执行链构建，但 Task 文件仍分别维护旧 component scene composer、native 索引 reset sampler、旧 Task factory 和专用 torque action adapter；两个旧 scene composer 还拒绝 Robot。旧 parallel registry 继续宣称这两个类有框架并行能力。修改前直接调用该并行 factory，两个任务均在 `ResolvedSelectedConfig` 上访问不存在的 `runtime` 而失败；G06 本来就尚未接收。

删除两个不可达的旧 scene／reset／Task factory 和旧单独 torque adapter，撤销两个失效的 parallel 注册及相应旧 adapter 导出；正式 Robot 主体声明、共享 physical Controller、力矩单位及 reset 分布保留。G06 需以正式构建合同重新实现并行能力，不能再将历史 parallel 示例当作当前可用能力。同步修正内建任务、示例和迁移文档。生产修改 5 文件 +4／−395，净减 391 行；版本诊断修改 1 文件 +8／−0；API 文档修改 3 文件 +14／−32，本文与当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1356。

148 项版本检查通过。Pendulum 和双轮车各自在 MuJoCo CPU 以正式 `make_env` 完成 reset、非零力矩 step、第二次 reset、关闭及 25 个实际 native 子步；两者在 GeoPhys CPU 完成同样生命周期，native 子步未直接计数。MJCF 导入有语义诊断。两任务的真实主体和 Controller 仍由共同的 source、Assembly 和 Runtime 控制合同消费；provider 的状态、clock、提交及 renderer 接口未变。Isaac 本轮未重跑，旧证据仍只对应原源码；本次删除的 adapter 和 component 工厂不参与正式 Isaac 调用链。冻结生产／诊断 diff、预算与收据位于 ignored `workspace/maintenance/v211_remove_legacy_actuation_20261112_n6ty3ks4/`。此项不宣称四任务主体构建完全统一，E01～E04 未整体接收。

### 6.108 effort 构建不再准备未使用的 Solution

输入 `7d64fbff`。PickCube 的 MJCF 直接及 joint effort 即使不提供 Solution，也会先加载 R3 动力学、生成 Solution readiness 和身份。现在 Task source 编译可按实际需要准备 readiness；未启用 Solution 的 effort 路线不再加载这些数据。需要 Solution 的 reset 选择仍准备 readiness，R3 effort 所需的动力学仍由该 Controller 的真实构建路径加载，source snapshot 和身份检查保留。这消除了普通 effort 对无关 Solution 准备的运行依赖；它仍使用 PickCube 现有 physical binding，尚未完成四任务共同构造。

生产修改 2 文件 +38／−34，净增 4 行；其中多数变更是将 readiness 准备置于条件内的缩进迁移，不计作独立能力；版本诊断修改 1 文件 +23／−0，本文和当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1356。150 项版本检查通过，包括在禁止 R3 动力学和 readiness 读取时构建直接／joint effort。MuJoCo 直接 effort、R3 effort 和 Position Solution 各完成 5 个 native 子步；joint effort 的 Controller reset 切换与 H5 读回完成 10 个子步。GeoPhys joint effort 完成 reset、step、再次 reset 和关闭，native 子步未直接计数。MJCF 导入有语义诊断。Position 和 Isaac 的 readiness 默认路径未关闭；Isaac 本轮未重跑，旧证据仍只对应原源码。完整 Solution 未运行。provider 的 source、状态、clock、提交和 renderer 合同未改；冻结 diff、预算和收据位于 ignored `workspace/maintenance/v211_effort_without_solution_20261112_kd8ubpcj/` 与 `workspace/maintenance/v211_effort_solution_retained_20261112_bsoz5a92/`。E01～E04 未整体接收。

### 6.109 Isaac effort source 准入归 Runtime adapter

输入 `6cb5f27e`。PickCube 任务目录中的 `physical_usd_profile.py` 原先承担 Isaac 专用的 USD source、Panda mimic 和 native range 准入，虽然同一 provider 的 physical port 已在 Runtime adapter 中。将这些 source 事实归入现有 Isaac physical adapter，删除旧文件；Task binding 传入已解析的 native drive，adapter 校验它与 Artifact 一致，再交给 Robot 的共同 effort 构建。主体身份改为读取所选 Robot；保留 source closure、Artifact、Scene 和 native drive 一致性检查，并将实际 adapter 与 Controller builder 源码纳入 source provenance。仍只接收现有受测 Isaac USD／Panda source，不据此宣称支持任意 Robot 或 source。

生产修改 3 文件并删除 1 文件：+36／−33，净增 3 行，其中约 29 行为从任务目录归入现有 Runtime adapter 的迁移，非新增第二套实现；版本诊断修改 1 文件 +11／−1，本文和当前状态文档修改 2 文件。无新文件，tracked 文件数由 1356 降为 1355。151 项版本检查通过，覆盖 position／disabled 两种 native drive 的绑定与交叉拒绝、source provenance 和非默认 lift。Isaac CUDA 直接 effort 以 0.17 米 lift 完成 reset、非零力矩 step、第二次 reset、RGB 和独立三帧读回；观察 41 次 physics callback，订阅前启动推进未知，worker 和 reader 退出码均为 0。SDK 日志仍有只读目录、USD 包和渲染预热警告；录制未启用，6.106 所述 recorder 限制仍存在。disabled drive 本轮只做 source／Controller 合同检查，完整 Solution 未运行；MuJoCo／GeoPhys 和 renderer 实现未改。冻结运行时生产 diff、预算和收据位于 ignored `workspace/maintenance/v211_isaac_physical_owner_20261112_skge4l7e/`；随后只扩充了版本诊断的 disabled-drive 断言。E01～E04 未整体接收。

### 6.110 native drive 模式由控制 binding 声明

输入 `288a4cfd`。MuJoCo 和 GeoPhys physical adapter 原先按 PickCube 专属 Artifact 名称推断原生驱动是否关闭，简单 Robot 的 motor 又走另一条特判。现在两者消费共同 physical binding 中各 channel 的 `native_drive`；混合或未受支持的模式在 provider 写入前拒绝。无 joint channel 的 body-only binding 延续原来的 position 默认，不关闭原生驱动。MuJoCo 的驱动关闭是全局操作，新增所有 native actuator 必须属于 binding 的检查，防止关闭其他主体的驱动；GeoPhys 继续只隔离声明的 actuator。保留源 transmission、单位、身份和原生映射检查。MuJoCo 为 PickCube reset 选择设置 gripper cap 的历史专属分支仍存在，尚未借此宣称完全消除 Task 特例。

生产修改 3 文件 +17／−10，净增 7 行；版本诊断修改 1 文件 +27／−0，本文和当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1355。153 项版本检查通过，包括真实 Panda binding 的 position／disabled 模式及混合模式拒绝。MuJoCo 直接 effort、Controller reset 切换、Pendulum 分别完成 5、10、25 个 native 子步；GeoPhys Panda joint effort 与双轮车完成 reset、非零 action、再次 reset 和关闭，native 子步未直接计数。GeoPhys 检查使用最终 MuJoCo 全局覆盖检查之前的 diff，该最后一行只影响 MuJoCo adapter。MJCF 导入有语义诊断；Isaac 和完整 Solution 本轮未重跑。renderer 未改，物理推进仍由原 Runtime session 执行。冻结 diff、预算和收据位于 ignored `workspace/maintenance/v211_binding_drive_owner_20261112_byprqs0a/` 与 `workspace/maintenance/v211_native_drive_coverage_20261112_kkjit98b/`。E01～E04 未整体接收。

### 6.111 gripper force cap 由 Robot 声明并由 adapter 核对

输入 `4b00097f`。PickCube 的 Controller reset 路线先前在 Task 中按 Panda 的第八个 native range 硬编码 ±10 N，MuJoCo adapter 又按 PickCube Artifact 名称把 source 原有 ±5 N 调成 ±10 N。现在 Task 只传递该路线实际使用的 gripper 配置，Panda Robot 负责将正的力限绑定到其声明的通道；MuJoCo adapter 检查所需范围与 source 的 gripper 配置一致、通道为受声明的双 prismatic 传动且驱动已隔离，然后记录并应用运行时 force cap。保留有限数值、source 身份与 transmission 核验，不再靠 Task Artifact 名称或 Task 写入 Panda 通道索引决定此映射。reset 选择仍决定何时请求该配置，Task 的 physical binding 尚待进一步收敛。

生产修改 3 文件 +28／−18，净增 10 行；版本诊断修改 2 文件 +15／−0，本文和当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1355。156 项版本检查通过，包含 Robot 对非正、非有限或未隔离驱动 force 请求的拒绝。MuJoCo reset 选择完成 Controller 切换、H5 读回及 10 个 native 子步；真实 receipt 记录 source 范围 ±5 N、配置范围 ±10 N，source MJCF 未修改。直接 effort 完成 reset、非零 step、再次 reset、关闭及 5 个 native 子步。MJCF 导入有语义诊断。GeoPhys、Isaac、renderer 和完整 Solution 本轮未重跑，旧证据仍限原源码。冻结 diff、预算和收据位于 ignored `workspace/maintenance/v211_robot_gripper_cap_20261112_2cjq7bwf/`；E01～E04 未整体接收。

### 6.112 删除 effort 路线的诊断手指初值

输入 `a97602fd`。PickCube 的 MJCF 非 reset-switch effort 和 Isaac effort 原先为了 force-observation fixture，把正式 Task 声明的两只手指初始位置从 0.04 m 私自改为 0.02 m，并替换 reset validity。删除这些初始化改写后，Position／effort 的 Artifact 消费相同 Task 初始化；当前用于 provider 准入和 Controller 模型身份的 physical Artifact ID 暂时保留，不能据此宣称完整构建链已经统一。source、Controller effort／Position 语义和驱动准入不变，实际任务初始状态恢复为正式声明。

生产修改 2 文件 +2／−20，净减 18 行；版本诊断修改 3 文件 +10／−2，本文和当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1355。156 项版本检查通过，比较 MJCF／USD 的 Position 和 effort Artifact 与同一 Task 声明。MuJoCo 直接 effort 与 Controller reset 切换实际 reset 时两手指均为 0.04 m，分别完成 5／10 个 native 子步；GeoPhys joint effort 实际值约 0.04 m，完成 reset、非零 step、再次 reset 和关闭，native 子步未直接计数。Isaac CUDA 直接 effort 在 0.17 m lift 下实际 reset 到 0.04 m，完成非零力矩、第二次 reset、RGB 和独立读回，观察 41 次 physics callback，订阅前启动推进未知；worker 和 reader 退出码均为 0。MJCF／SDK 日志有既有导入与渲染诊断，Isaac recorder 限制仍在，完整 Solution 未运行。Artifact 身份改变，旧证据仍只对应原身份。冻结 diff、预算和收据位于 ignored `workspace/maintenance/v211_task_initial_cpu_20261112_8m9rnycr/` 与 `workspace/maintenance/v211_task_initial_isaac_20261112_jn7fsiy6/`；Isaac 运行后只为 CPU 诊断补充了实际手指初值断言。E01～E04 未整体接收。

**后续纠正：**6.112 未验证固定质量矩阵 Controller。其历史校准只覆盖手指名义 0.02 m ±0.019 m，正式 0.04 m 初态在范围外；6.112 的初始化收敛因此使这两条质量矩阵 profile 无法执行，详见 6.113。不能将当时直接／joint effort 的通过扩大到质量矩阵能力。

### 6.113 MJCF effort 使用正式 Task ID，并显式暴露质量模型缺口

输入 `f83c7b2a`。MuJoCo／GeoPhys adapter 已按控制 binding 的 native drive 选择行为，MJCF effort 不再需要生成控制专属 Artifact ID；现在直接沿用正式 Task ID。固定质量模型选择从 Artifact 名称改为核对物理 binding 的 Artifact、source、闭包和驱动隔离，并匹配模型文件内经哈希固定的 source closure。Task Artifact v0／v1 仍是不同表示，不能把 ID 一致说成完整构建链已合一。

实际复验暴露了 6.112 的遗漏：质量模型以手指 0.02 m 为名义、容差 0.019 m，正式初态为 0.04 m。MuJoCo mass effort 原先能构建，但第一次 step 因状态超出模型范围而拒绝，观察到 0 个 native 子步；这是一项实际能力缺口，不是成功。现在将同一范围检查从首次计算提前到构建阶段，明确报告模型不覆盖声明的初态；未扩大或修改模型校准范围，也未恢复诊断专用初态。两种固定质量矩阵 profile 目前不可用于正式初态，需要后续取得真实 source 模型能力或重新校准，E04 因此仍未完成。

生产修改 2 文件 +22／−16，净增 6 行；版本诊断修改 1 文件 +56／−3，本文和当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件数保持 1355。155 项版本检查通过，包含 Task ID 一致、错误 Artifact／source 拒绝和两个质量模型 profile 对正式初态的明确拒绝；这不代表质量模型可运行。MuJoCo 直接 effort 和 Controller reset 切换分别完成 5／10 个 native 子步，GeoPhys joint effort 完成 reset、step、再次 reset 和关闭，native 子步未直接计数。Isaac 和完整 Solution 本轮未重跑。失败证据在 ignored `workspace/maintenance/v211_task_artifact_effort_20261112_k54h6618/`；修正后的冻结 diff、预算及其他路线收据在 ignored `workspace/maintenance/v211_formal_artifact_mass_boundary_20261112_yt31_3u_/`。该 CPU 窗口后仅添加了错误 Artifact／source 的版本合同检查。


### 6.114 质量矩阵控制使用 provider 的实时 source 模型

输入 `49fb6f3d`。6.113 指出的固定校准模型不覆盖正式初态；此处移除 PickCube 任务内固定模型加载和相关专属校验，质量矩阵 Controller 在 MuJoCo 使用当前 source、episode 和状态绑定的 provider dynamics。它在独立 scratch 状态计算矩阵，不推进现场物理；保持 `M × PD`、成对手指投影和超限拒绝，不加入动力学 bias。矩阵现在随状态更新，和旧固定名义矩阵不保证数值相同，因此这是明确的控制行为变化，不是旧模型数值等价的证明。保留 source closure、Artifact／状态边界和矩阵正定性检查。历史校准文件暂留作证据，不再用于正式构建。

GeoPhys 和 Isaac 当前没有 provider-owned source dynamics，故质量矩阵 profile 在其 physical preflight 明确拒绝；Isaac 的 preflight 不保证早于 App 启动。其他 effort profile 保持各自语义。此项没有恢复 GeoPhys／Isaac 的质量矩阵能力，也没有完成四任务统一构建；renderer 未改，source、状态、clock、提交及物理推进仍由各自 Runtime session 管理。

生产代码修改 6 文件 +43／−57，净减 14 行；版本诊断修改 1 文件 +12／−22；无新增、删除或整文件迁移，tracked 文件数保持 1355。本文和当前状态文档各修改 1 文件。156 项版本检查通过，包含两个正式 mass profile、foreign source 拒绝和 GeoPhys preflight 拒绝。MuJoCo CPU 两个 mass profile 各完成正式 0.04 m 初态 reset、一次控制 step、第二次 reset、关闭与 5 个 native 子步；原动态控制器 reset 切换与记录完成 10 个子步。MJCF 导入有语义诊断。GeoPhys／Isaac 的 mass profile 未进行原生运行；Isaac preflight 的同类拒绝由代码检查支持，完整 Solution 未运行。冻结 diff、预算和原始收据位于 ignored `workspace/maintenance/v211_live_mass_ovikmdb1/`。E01～E04 尚未整体接收。


### 6.115 reference effort 共享绑定合同直接构建 Controller

输入 `795b679b`。实时质量矩阵和动态 effort Controller 先前调用普通 reference effort builder，完整创建 affine PD model、profile 和 Controller 后立即丢弃，只借用其绑定验证与状态需求。现在三种 reference effort 路线共同校验已有 physical binding 并声明 pose 状态需求，各自直接构造实际选用的 Controller；保留驱动隔离、主体和 writer 校验、状态需求与命令语义。此项减少不参与执行的对象构造，但尚未消除 PickCube 的任务专属 physical binding，也不表明 E02／E04 已完成。provider／renderer adapter、source、clock 和提交接口未修改。

生产修改 1 文件 +33／−26，净增 7 行；原有绑定校验及 pose 需求代码移至同文件内共同函数，非新的一套控制路径。版本诊断修改 1 文件 +20／−0；本文与当前状态文档修改 2 文件；无新增、删除或整文件迁移，tracked 文件数保持 1355。158 项版本检查通过，包括禁止构造未使用 PD servo 时仍能构造两种 mass profile。MuJoCo CPU 的 joint／R3 普通 reference 以及 joint／R3 mass 各完成 reset、step、第二次 reset、close 与 5 个 native 子步；动态 reset 选择及记录完成 10 个子步。MJCF 导入有语义诊断。GeoPhys／Isaac 和完整 Solution 本轮未运行，先前证据仍只对应原源码；renderer 未改。冻结 diff、预算和原始收据位于 ignored `workspace/maintenance/v211_effort_contract_vz7nh1hu/`。E01～E04 尚未整体接收。


### 6.116 退休旧 Position 诊断相机入口

输入 `144b1b54`。正式四任务的 `make_env`／`from_task_binding` 不传入旧 `camera_observation_config`；该入口服务已退休的 Position 诊断，额外在公共 Env、观测、关闭与记录元数据中维护 RGB／depth／mask 双相机 consumer。删除此诊断入口及专用 consumer、观测拼接和写入分支；5c 正式 `task_rgb_camera` 及其同步采集和关闭保留。历史相机合同和 H5 读取代码保留以读取既有证据。此项不宣称统一所有 renderer 或完成 E03／E04。

生产代码修改 4 文件 +5／−330，净减 325 行；版本诊断修改 probe 1 文件 +27／−3，并新增 1 文件 158 行，将正式 task RGB 合同检查从旧诊断中摘录至版本目录并补充关闭检查；旧文件未删除，不能计作整文件迁移。本文和当前状态文档修改 2 文件；tracked 文件数 1355→1356。158 项既有版本检查及 9 项 RGB 合同检查通过。MuJoCo CPU 的正式 joint effort／CameraGeometry／native RGB 完成 reset、step、第二次 reset、关闭和 5 个 native 子步；正式 R3 Position 记录完成 reset、step、第二次 reset、关闭与 5 个子步。MJCF 导入有语义诊断。

本轮还发现两个独立于旧诊断入口的正式相机问题，均在首次 step 前退出，尚未归因或修复：R3 Position／RGB 在 reset 的 source 检查处缺少 Scene 声明；joint effort 使用公开 `CameraSpec` 时实际采集后尝试调用 MuJoCo session 不提供的 `task_camera_binding`。上述 CameraGeometry 通过不能代表 CameraSpec 或 Position／RGB 已通过。GeoPhys／Isaac、完整 Solution 及历史 H5 独立读回本轮未复验。预算、冻结输入和失败／成功收据位于 ignored `workspace/maintenance/v211_retire_position_camera_ch77m4u5/`。E01～E04 尚未整体接收。


### 6.117 task RGB 相机几何由 renderer 采集结果提供

输入 `05419455`。6.116 的 `CameraSpec` 失败源于 Env 在 renderer 已完成采集后，额外向物理 session 请求 `task_camera_binding`；MuJoCo 物理 session 没有该接口，独立 renderer 场景也不应要求物理 session 充当相机 owner。现由 RGB consumer 从实际捕获结果发布 `resolved_camera` 几何及边界元数据，Env 保留用户请求和 renderer 信息，不再请求物理 session。`resolved_camera` 是与该帧关联的解析几何，不声称是原生设备实测标定；先前 CameraSpec 回执中的 `realized_camera` 字段不再提供。source／状态／clock 身份和同步采集检查保留。

生产修改 2 文件 +2／−2；版本诊断修改 2 文件 +13／−11；本文和当前状态文档修改 2 文件。无新增、删除或整文件迁移，tracked 文件保持 1356。167 项版本检查通过，包含物理 session 没有相机方法时由 renderer 结果提供边界几何的检查。MuJoCo CPU joint effort 分别使用公开 CameraSpec 和 CameraGeometry，均完成 reset、step、再次 reset、关闭与 5 个 native 子步，RGB 的解析几何分别对应 reset／step 边界；MJCF 导入有语义诊断。此项没有改动物理推进。GeoPhys／Isaac 和完整 Solution 本轮未运行。

R3 Position／RGB 的另一个失败仍在：当前 MJCF reference Task source 不提供完整 `SceneDefinition`，其 Artifact 仍为旧表示；renderer 的 source 合同要求完整 Scene 和 `TaskArtifactV1`，不能以 Panda 局部 Scene 伪装整场景。需将正式 Position Task、Robot 与 source 构建汇入同一完整合同后复验。失败记录继续保留于 6.116；本项未接收 E01～E04。冻结 diff、预算及收据位于 ignored `workspace/maintenance/v211_rgb_camera_owner_upcla9eh/`。


### 6.118 PickCube 跨 source 共用 Task Artifact 编译

输入 `8ed86886`。MJCF effort binding 和 USD source 原先各自将 PickCube 任务配置、旧语义、Scene 和帧别名编译为 `TaskArtifactV1`，造成任务编译藏在两条不同控制／source 路径。将同一 Task Source、Artifact 编译、cube 身份绑定及 Scene 验证归到 PickCube Task 的共同编译函数；MJCF 和 USD 只提供各自真实 Scene 与帧声明。MJCF Scene 组合也从 physical candidate 私有函数归到 Task 声明处，消费所选 Robot 的真实主体。此项是接入共同 Task 声明的中间步骤：MJCF Position 仍使用旧 Artifact 与 source，Position／RGB 缺口没有解决；四任务 Robot／Controller 构造未整体统一。provider 和 renderer 执行合同未改。

生产修改 2 文件 +41／−40，净增 1 行；其中 MJCF Scene 声明从 candidate 移至现有 Task 文件，属于代码段迁移，不是整文件迁移。版本诊断修改 1 文件 +25／−0，比较 MJCF／USD 的 Task Source、初始化、时间和任务语义及各自完整 Scene 帧。本文和当前状态文档各修改 1 文件；无新增、删除或整文件迁移，tracked 文件保持 1356。168 项版本检查通过；受影响 USD source／Artifact 的静态检查通过，未进行本次 Isaac 原生复验。MuJoCo effort／CameraSpec／RGB 完成 reset、step、第二次 reset、关闭与 5 个子步；GeoPhys effort 完成同样生命周期，native 子步未计数；MuJoCo R3 Position Solution 完成单步与 5 个子步，非完整 Solution。MuJoCo effort 与前次验证的 Scene、reset 样本和 Controller 身份一致，MJCF 导入有语义诊断。冻结 diff、预算及收据位于 ignored `workspace/maintenance/v211_pickcube_shared_artifact_xsz4wlmz/`。E01～E04 尚未整体接收。


### 6.119 Panda effort 运动学模型归 Controller 构造

输入 `26c13acc`。MJCF 和 USD 的 PickCube physical binding 原先各自检查 R3 profile 并构造 Panda 运动学模型；现在它们传递各自已核验的 source XML 和 Task 指定的 TCP，公共 Controller 构造只在所选 pose reference 实际需要时创建模型。joint／direct profile 不构造该模型。Task reference 参数仍由 Task 声明，Panda source、传动范围、Controller 身份和 source 闭包检查保留。删除 Task helper 中已不使用的 source 参数及重复 direct 分支；这减少两条任务接线的 Controller 决策，但 Position 和 effort 仍未汇入同一完整构造。

生产修改 4 文件 +15／−19，净减 4 行；版本诊断修改 1 文件 +30／−0，检查 joint 不创建运动学模型、R3 从实际绑定的 MJCF source 创建。本文和当前状态文档各修改 1 文件；无新增、删除或整文件迁移，tracked 文件保持 1356。171 项版本检查通过，包括 USD source 构造的静态检查；未进行本次 Isaac 原生复验。MuJoCo 的 R3 effort、R3 mass 各完成 reset、step、第二次 reset、关闭和 5 个子步；动态 reset 切换与记录完成 10 个子步；GeoPhys R3 effort 完成相同短程生命周期，native 子步未计数。MuJoCo 两个 R3 Controller 身份与此前相同；MJCF 导入有语义诊断。renderer 及完整 Solution 本轮未复验。冻结 diff、预算及收据位于 ignored `workspace/maintenance/v211_effort_model_owner_77375rld/`。

MJCF Position／RGB 的 source lease 目前与旧 Artifact、控制计划和闭包绑定；要切入完整 Scene／Artifact，需让共同 source 构建与生命周期拥有同一受验证资源，不能只为 renderer 添加投影。此项仍未解决，E01～E04 尚未整体接收。


### 6.120 规范 MJCF source 接入引用式 Robot 组合

输入 `a34eec23`。引用式 Robot 组合以前只接受旧 `ExecutionSourceReceiptV1`，因此已包含完整 Scene 和 source 闭包的规范 MJCF source 无法被相同 Position Robot／Controller 组合消费。现在共同 source 组合 adapter 对规范 source 重新投影 Scene 并根据实际 XML／资产计算闭包，与声明的 source 身份一致才继续；旧快照仍检查 receipt，替换式 Robot 组合仍要求受管快照。由实际 PickCube 规范 source 构建 R3 Position Controller 后，MuJoCo 和 GeoPhys 的共同组合均能产生与 Artifact、source 闭包绑定的 Robot／Controller 计划；更改重力声明会被闭包校验拒绝。

生产修改 1 文件 +14／−3；版本诊断修改 1 文件 +43／−0；本文和当前状态文档各修改 1 文件。无新增、删除或整文件迁移，tracked 文件保持 1356。173 项版本检查通过。MuJoCo 原 Position Solution 单步和装配 Panda 替换式路线各完成 5 个 native 子步，GeoPhys 原 Position 完成 reset、step、再次 reset 和关闭，native 子步未计数。规范 source／Position 组合本轮仅验证到纯构造合同，没有进行真实 materialize／step；旧 Position 普通构建尚未切换到该规范 source，Position／RGB 仍未修复。Isaac、renderer 和完整 Solution 本轮未复验。冻结生产输入、测试最终 diff、预算及收据位于 ignored `workspace/maintenance/v211_canonical_robot_reference_rxv171sd/`。E01～E04 尚未整体接收。


### 6.121 规范 Scene source 校验归共同 Runtime owner

输入 `5d43bd90`。引用式 Robot 组合、Panda effort source 限值读取以及 MuJoCo 物化此前各自执行 Scene 投影和 XML／资产闭包校验；将共同部分归入 Runtime source，三个调用处消费同一投影和校验。MuJoCo 特有的 freejoint 和 keyframe lowering 仍由物理 adapter 入口完成；source ID、闭包及资产路径检查未放宽。此项减少重复校验实现，但 Position 普通构建仍未切换到规范 source，Position／RGB 未修复。

生产修改 3 文件 +14／−23，净减 9 行；版本诊断修改 1 文件 +1／−1，适配统一的闭包错误；本文和当前状态文档各修改 1 文件。无新增、删除或整文件迁移，tracked 文件保持 1356。173 项版本检查通过，包括规范 source 字节篡改拒绝。MuJoCo effort／CameraSpec／RGB 和 Position Solution 单步各完成 5 个 native 子步；GeoPhys effort 完成 reset、step、第二次 reset 和关闭，native 子步未计数。MJCF 导入有语义诊断。Isaac 和完整 Solution 未复验；规范 source／Position 原生执行仍未验证。冻结 diff、预算及收据位于 ignored `workspace/maintenance/v211_scene_source_verification_okbgfwoy/`。E01～E04 尚未整体接收。


### 6.122 规范 source 快照纳入共同生命周期

输入 `cb9b91fd`。MJCF 规范 source 的 XML 和资产存放在受验证的原始快照内，但此前快照只由 PickCube physical binding 保存，公共 Env 无法从规范 source 识别其资源。现在 source 显式携带该快照，并在构造时核对输入 XML 和目录；共同 Env 的构造失败、Robot 组合失败、reset 和 close 使用同一资源识别方式。规范投影身份仍由 Scene 和投影闭包独立校验，原始快照 receipt 不冒充投影闭包；既有 task binding 的资源关闭仍保留，直至正式构建进一步统一。

生产修改 4 文件 +32／−9，净增 23 行；版本诊断修改 2 文件 +53／−1，新增 1 个 103 行版本化 Runtime probe；无删除或整文件迁移，tracked 文件 1356→1357。175 项版本检查通过，包含篡改输入拒绝及组合失败释放快照。MuJoCo 和 GeoPhys 分别使用实际规范 source、相同 TaskArtifact／Scene／Position 计划完成 Runtime materialize、reset 和一个受控 interval；MuJoCo 实测 5 子步，GeoPhys 未计数 native 子步。该验证直接调用共同 Runtime 合同，尚非正式 Position make_env 路线。MuJoCo effort／CameraSpec／RGB 和动态 Controller reset／记录，以及 GeoPhys effort 的重复 reset 和关闭通过；MJCF 导入有语义诊断。Isaac、Position／RGB 和完整 Solution 未复验。普通 Position 入口仍未接入规范 source，E01～E04 尚未整体接收。预算、冻结生产输入及收据位于 ignored `workspace/maintenance/v211_canonical_source_lifetime_i8h4nbr_/`。


### 6.123 正式 Position 路线消费共同 Task Scene

输入 `ba1eb932`；实施前复核优化台账 GOV-01／02、ENTRY-01／02、TASK-01／02、ENV-01～03、SUBJ 和 CTRL 条目。PickCube 的一体 Panda 正式 Position 和 effort 构建现使用同一 MJCF Task Scene 与 TaskArtifact 编译，规范 source 将快照交给共同 Env 生命周期；Robot Position 绑定消费实际 source Scene，而非另造不同身份的 Scene。控制提交仍核验 Scene、Artifact、闭包和 Controller 身份。首次真实 Position 提交因不同 Scene 身份被拒绝、未推进，随后修正并保留该失败收据。装配 Panda 的替换式 source 暂仍使用旧构建，Isaac 路线另有适配；本批没有完成四主体统一，也没有关闭 E01～E04。

生产修改 3 文件 +44／−27，版本诊断修改 3 文件 +20／−14，本文新增记录；无新增、删除或整文件迁移，tracked 文件数保持 1357。代码段从 physical candidate 收敛到 Task 共同编译，不按整文件迁移计算。175 项版本合同检查通过。正式 `make_env` 在 MuJoCo CPU 完成一体 Position、任务 RGB、一体 Position Solution 单步及装配 Panda 各一次 reset／控制推进／再次 reset／close，各观测 5 个 native 子步；Solution 非完整执行。GeoPhys CPU 一体 Position 完成同一短程生命周期，native 子步未观测，按 50 预留。GeoPhys 日志报告 Taichi 四线程，即使探针限制了 BLAS／OMP 线程，不能称为两线程运行。MJCF 导入保留语义诊断。Isaac、完整 Solution 和其他未受影响路线本批未复验。输入冻结、失败与成功收据位于 ignored `workspace/maintenance/v211_position_formal_wdu7jxv_/`。


### 6.124 共享 MJCF Scene 投影与 source 闭包

输入 `d018abaf`；实施前复核台账 GOV-01／02、ENTRY-01／02、ENV-01～03、SUBJ-01～03、CTRL-01／02 及 source owner 边界。正式 PickCube Position 和 effort 的共同 MJCF Scene 绑定此前从 MuJoCo composition 模块取得，即使实际 provider 是 GeoPhys；简单主体 effort source 又独立计算相同的投影与资产闭包。将 Scene 投影、资产读取和闭包计算归入共同 Runtime source，PickCube 的快照绑定、简单主体的 source 编译以及 adapter 的闭包复核实际调用同一实现。MuJoCo 特有物化仍由 MuJoCo adapter 执行；Scene、source 闭包、受管快照和 native 校验均未删减。

生产修改 5 文件 +37／−47，净减 10 行；共同绑定函数从 MuJoCo composition 迁入既有 Runtime source，属于代码段迁移，无整文件迁移。版本诊断和测试本批无源码变化；本文新增记录，无新增或删除文件，tracked 文件数保持 1357。最终代码下 175 项版本合同检查通过。MuJoCo 正式 PickCube Position 和 Pendulum 分别完成构建、reset、一次非零控制、第二次 reset、关闭，观测 5 和 25 个 native 子步；PickCube MJCF 导入保留语义诊断。本批未复跑 GeoPhys、Isaac、renderer 或完整 Solution；此前对应证据保留其原代码和范围。冻结输入、双锁预算及收据位于 ignored `workspace/maintenance/v211_shared_mjcf_source_3jk6quiw/`。装配 Panda 的替换式 source 及四任务共同构建仍待收敛，E01～E04 未整体接收。


### 6.125 Solution 重建使用共同 builder

输入 `a961ae5d`；实施前复核优化台账 GOV-01／02、ENTRY-01／02、ENV-01～03、SUBJ 和 CTRL-01／02。PickCube、NutAssembly 及 PickCube 物理切换的 caller-owned Solution 原先分别声明 `build_external`，其实际 builder 与普通构建相同；共同 reset 现在在有 seeded 能力时调用 seeded builder，否则调用同一个普通 builder。删除多余 binding 字段和两任务的重复声明；外部 Solution 是否受支持仍由任务提供的验证函数决定，旧 source 验证、seed、失败清理及唯一提交路径保留。LIBERO caller 中对该字段的重复声明同步移除；该 caller 还含已有未迁移 binding 字段，本次未验证或宣称 LIBERO 路线可运行。

生产修改 6 文件 +4／−23，净减 19 行；版本诊断修改 1 文件 +10／−1，覆盖有 seed 和无 seed 的 Solution 采用共同 builder。本文新增记录，无新增、删除或整文件迁移，tracked 文件数保持 1357。176 项版本合同检查通过；正式 MuJoCo PickCube 与 NutAssembly 各以 caller-owned Solution 完成 reset、单次控制推进、再次 reset 和关闭，各观测 5 个 native 子步，非完整 Solution。MJCF 导入保留语义诊断。GeoPhys、Isaac、renderer 和其他任务本批未复验；既有证据保留原范围。冻结输入、预算和收据位于 ignored `workspace/maintenance/v211_shared_solution_build_xsrk4d3b/`。装配 Panda source、四主体统一与完整控制验收仍未完成，E01～E04 未整体接收。


### 6.126 PickCube 任务力声明脱离 Position binding

输入 `681a1b0d`；实施前重新审阅 GOV-01／02、ENTRY、TASK-01／02、ENV-01～03、SUBJ、CTRL 和 source 边界。PickCube effort 路线为了取得任务 COM 力，原先额外构造 Position `ReferenceTaskBinding` 再从中提取 callback。现在 Task 直接声明同一个可选力贡献；Position 与 effort 两条真实构建链直接消费，力、单位、资源、interval 子步范围与共同提交不变。effort 不再构造 Position binding。此项只消除该依赖，不代表两个路线的 Robot/source 构建已经完全统一。

生产修改 3 文件 +20／−14，净增 6 行；原力贡献实现从 Position specialization 迁到现有 Task 语义，属代码段迁移，无整文件迁移。版本诊断修改 2 文件 +34／−0，检查两路线声明一致及 effort 不再构造 Position binding，并支持正式短程输入；本文新增记录。无新增或删除文件，tracked 文件数保持 1357。最终代码 177 项版本合同检查通过。MuJoCo 正式 R1 Position 和 direct effort 分别以 1.5 N 的任务力完成 reset、一次控制、再次 reset、关闭，各观测 5 个 native 子步；此检查不替代或重开原 COM 历史判据。MJCF 导入保留语义诊断。GeoPhys、Isaac、renderer、完整 Solution 本批未复验。冻结输入、双锁预算与收据位于 ignored `workspace/maintenance/v211_task_force_owner_xom0_foa/`。E01～E04 仍未整体接收。


### 6.127 PickCube 控制路线共享 Task 语义

输入 `c559b4e6`；实施前复核台账 GOV-01／02、ENTRY、TASK-01／02、ENV-01～03、SUBJ、CTRL 及 source 边界。PickCube Position 与 MJCF effort binding 之前各自写任务评估、TaskDefinition、状态投影、对象和任务力接线；现在这些实际字段由 PickCube Task 一处声明，两条正式绑定均消费。物理路线继续提供 source-bound reset sampler，控制、source 与资源 owner 不变；Isaac physical 路线通过已有正式 Task binding 消费相同任务声明。删除 specialization 中不再使用的重复导入。此项统一任务语义，不声称 Position／effort 或装配 Panda 的主体构建已统一。

生产修改 3 文件 +26／−21，净增 5 行；任务语义字段由两处收敛到既有 Task 文件，是代码段迁移，无整文件迁移。版本诊断修改 1 文件 +3／−0，检查两路线 TaskDefinition、状态投影和对象映射一致；本文新增记录。无新增或删除文件，tracked 文件数保持 1357。最终代码 177 项版本合同检查通过。正式 MuJoCo 的 Position caller-owned Solution 单步和 direct effort 携任务力单步分别完成 reset、控制推进、再次 reset 和关闭，各观测 5 个 native 子步；非完整 Solution，原 COM 历史判据不变。MJCF 导入保留语义诊断；GeoPhys、Isaac 和 renderer 未作本批原生复验。冻结输入、双锁预算及收据位于 ignored `workspace/maintenance/v211_pickcube_task_binding_u_i36rl5/`。E01～E04 尚未整体接收。


### 6.128 四任务使用同一构建请求

输入 `7e801ecf`；实施前重新审阅 GOV、ENTRY、TASK、ENV-01～03、SUBJ、CTRL 与 source 边界。共同 reset 之前在 `build`、`build_seeded`、`build_sampled` 三种字段之间分支，任务各自拼装不同 builder。现在正式任务接收同一组 provider、backend、seed、horizon 和可选采样结果：普通初始化、reset、caller-owned Solution 和配置切换均通过同一构建入口；Pendulum／双轮车仍由自己的任务采样器提供结果，PickCube 的 source-bound reset 按 seed 编译。移除不再需要的多个 builder 字段及物理 binding 创建时重复的 provider／seed／horizon 参数；Isaac 实际构建请求仍校验 provider、backend 和 horizon。Harness 和 LIBERO 的相关 caller 字段同步迁移；LIBERO 尚有其他既有未迁移能力，不据此声称其运行。

生产修改 7 文件 +42／−62，净减 20 行；版本诊断修改 5 文件 +30／−34，适配统一请求并检查普通采样与 Solution 请求；本文新增记录。无新增、删除或整文件迁移，tracked 文件数保持 1357。最终生产代码 176 项版本合同检查通过；随后增加的 Isaac horizon 拒绝断言在 11 项针对性检查中通过。最终物理 binding 输入下，MuJoCo reset-scoped Controller 切换／记录完成 10 个 native 子步。此前冻结的同批输入下，MuJoCo 四任务和装配 Panda 均完成 reset、控制、再次 reset、关闭，分别观测 PickCube／Nut／Pendulum／双轮／装配为 5／5／25／25／5 个子步；其中两个桌面任务为 Solution 单步，非完整 Solution。GeoPhys Pendulum 同批短程通过，native 子步未观测，按 50 预留，日志显示 Taichi 四线程；MJCF 导入保留语义诊断。上述先前输入与最终物理 binding 的差异仅为该 binding 删除已无用途的创建参数及 Isaac horizon 检查，证据身份分别保存在冻结 patch 中。Isaac、renderer 及完整 Solution 本批未作原生复验。预算、输入差异与收据位于 ignored `workspace/maintenance/v211_single_build_request__0go9q00/`。此项统一构建请求，不等于四主体 source 和构造机制已全部统一；E01～E04 仍未整体接收。


### 6.129 引用式 PickCube 构建复用所选 Robot

输入 `b21ae9d0`；实施前复核台账 GOV、ENTRY、TASK、ENV、SUBJ、CTRL 和 source 边界。PickCube Position 正式构建之前创建所选 Robot 来判断 source recipe，却由 Panda box 编译器另造一个默认 Robot；引用式路线现在将同一所选实例交给 Task Artifact／source 编译及后续 Scene 声明，source 组合继续复用该实例。装配 Panda 仍需要原 Task 中的参考 source 供替换式 composer 使用，保留其现有路径和身份校验；这不是四主体完整统一。

生产修改 2 文件 +12／−12，净变化 0；版本诊断修改 1 文件 +19／−0，检查所选 Robot 与实际 source 实例相同；本文新增记录。无新增、删除或整文件迁移，tracked 文件数保持 1357。最终代码 177 项版本合同检查通过。MuJoCo 正式一体 Panda Solution 单步及装配 Panda 短程均完成 reset、控制、再次 reset 和关闭，各观测 5 个 native 子步；非完整 Solution。MJCF 导入保留语义诊断。GeoPhys、Isaac、renderer 本批未复验；先前证据保持原输入和范围。冻结输入、双锁预算及收据位于 ignored `workspace/maintenance/v211_selected_robot_identity_btzsoime/`。E01～E04 尚未整体接收。


### 6.130 装配 Robot 声明关节与 actuator 所有权

输入 `372eed00`；实施前重新核对 GOV、ENTRY、TASK、ENV、SUBJ-02／03、CTRL-01／02 和 source 组合边界。MuJoCo composer 原先直接枚举装配 Panda 的臂关节、手指和 actuator，并自行指定打开 actuator；现在装配 Robot 一处声明这些部件关系，Robot 主体编译和 provider composer 同时消费。composer 按该声明将 Task source 关节映射到实际 native 名称，并核验每个关节以及打开 actuator；固定附件、source 闭包、writer 和实际 native 模型校验仍由原 owner 负责。这个变化减少 adapter 对特定 Robot 通道的硬编码，替换式 source 与一体 source 的其余差异仍未消除。

生产修改 2 文件 +27／−13，净增 14 行；Robot 关节／actuator 声明从 adapter 收敛到 Robot，属于代码段迁移，无整文件迁移。版本诊断修改 1 文件 +23／−0，验证错误 Task 关节映射在 native 之前拒绝并释放 source；本文新增记录。无新增或删除文件，tracked 文件数保持 1357。最终代码 178 项版本合同检查通过。正式 MuJoCo 装配 Panda 完成 reset、双 writer 控制、第二次 reset 和关闭，观测 5 个 native 子步；provider 的原生名称、固定连接和资源核对仍有效。本批未复验其他 provider、renderer 或完整 Solution。冻结输入、双锁预算与收据位于 ignored `workspace/maintenance/v211_robot_joint_ownership_h_1kc72h/`。E01～E04 尚未整体接收。


### 6.131 装配 source 消费 Robot 资产声明

输入 `1a1292f1`；实施前复核 GOV、ENTRY、TASK、ENV、SUBJ-02／03、CTRL 与 SRC-02／04。装配 Panda 的 provider composer 原先忽略所选 Robot 的资产路径，固定从仓库目录读取 arm／hand；现在它消费 Robot 的 `AssetManifest` 中两个 MJCF 和资产根目录，核对 manifest owner 与 recipe revision，原受支持 source 字节、license、资产闭包和 native 映射检查保留。实际声明的根目录贯穿固定附件编译与 provider 物化；从该生产构造移除仅服务旧顺序诊断的可选分支，不清除其他仍有调用的历史检查。

生产修改 2 文件 +36／−35，净增 1 行；版本诊断修改 2 文件 +74／−0，验证重定位资产根和 foreign owner 拒绝，并支持真实运行输入；本文新增记录。无新增、删除或整文件迁移，tracked 文件数保持 1357。最终代码 180 项版本合同检查通过。正式 MuJoCo 使用复制到独立目录、由 Robot 明确声明的资产完成装配 Panda reset、双 writer 控制、第二次 reset 和关闭，观测 5 个 native 子步；这验证已支持的两源资产，不扩大为任意 Robot 组合。GeoPhys、Isaac、renderer 和完整 Solution 本批未复验。冻结输入、双锁预算与收据位于 ignored `workspace/maintenance/v211_declared_robot_source_61gx1xn_/`。替换式与引用式 source 的共同构造及四主体统一仍未完成，E01～E04 尚未整体接收。


### 6.132 共同入口选择 Robot 并贯穿构建

输入 `d41b09fb`；实施前重新审阅台账 GOV、ENTRY、TASK、ENV、SUBJ、CTRL 与 SRC，核对四正式任务当前构造。共同入口选择一次 Robot，向 Task binding、编译、source 组合及 worker 传递同一声明；reset 切换若 Robot UID 不变则复用声明，运行时 Controller／物化仍按 episode 重新绑定。Pendulum 和双轮车 source 显式携带同一 Robot。装配 source 的参考主体与最终装配主体仍有替换边界，不能据此宣称 source 已统一。共同 GeoPhys 场景编译根据 Robot 是否声明资产／引用合同区分需要解析的组件和已包含在 source 的主体，不新增任务名分流；资产、引用、身份检查继续由各自合同负责。示例 caller 适配新 binding 参数，但未做其真实运行验收。

本批生产修改 15 文件 +83／−57，净增 26 行；版本诊断修改 1 文件 +39／−0，检查四任务绑定所选 Robot 身份及装配调用；本文新增记录。无新增、删除或整文件迁移；tracked 项目文件数保持 1357。代码段跨文件传递与调整未单独计为整文件迁移，本批未实现净精简。以 `1f1359ee` 为起点的 task_env 工作树差异为 134 文件（新增 12、删除 20、修改 102）及 +7669／−14659，净减 6990 行；其中包含历史目录退休和诊断搬迁，不能将全部减少归因于本批。

最终代码版本诊断 185 项通过。正式 GeoPhys Pendulum 与双轮车分别完成 reset、一次控制推进、再次 reset 和重复 close；native 子步未观测，双锁和每项 50 子步预留记录在 `workspace/maintenance/v211_robot_source_bridge_20261112/`。本批较早冻结输入下，MuJoCo PickCube、NutAssembly、Pendulum、双轮及装配 Panda 分别观测 5／5／25／25／5 子步并完成短程 reset、控制、再 reset、关闭；前两项为 Solution 单步而非完整 Solution；隔离 worker PickCube 短程通过但 native 子步未观测。较早输入及其锁、预算和收据在 `workspace/maintenance/v211_common_robot_owner_k0dsflgd/`；最终输入额外增加共同 GeoPhys 编译边界和示例 caller 签名，MuJoCo 未按最终字节重跑，证据按输入区别引用。先前 GeoPhys Pendulum 因既有主体错误进入外部资产解析而失败，修正后重新运行通过。MJCF 导入保留语义诊断；Isaac、renderer 与完整 Solution 本批未复验。E01～E04 仍未整体接收。


### 6.133 普通任务消费实际共同构建请求

输入 `fceb727f`；实施前再次对照台账 GOV、ENTRY、TASK、ENV-01～03、SUBJ 和 CTRL，并复核当前正式构建链。Pendulum／双轮车的共同 effort binding 原先忽略构建请求中的 provider，改用绑定时闭包保存的 provider；两个任务还各自保留 Robot 未传入时重新从 registry 创建的分支。现在 source 编译直接消费每次共同请求的 provider，backend 与已解析配置不一致时在资源物化前拒绝；Robot 由共同入口提供并用于 composition，不再在任务侧重复选择。episode horizon 仍归 Env 生命周期，当前 source 编译不消费它。此项不声称其他 Task 构造、source 组合或 renderer 已全部统一。

生产修改 5 文件 +13／−21，净减 8 行；版本诊断修改 1 文件 +32／−0，检查两任务按请求消费 provider、使用所选 Robot 并拒绝不一致 backend；本文新增记录。无新增、删除或整文件迁移；tracked 项目文件数保持 1357。相对 `1f1359ee` 的 task_env 工作树差异为 134 文件（新增 12、删除 20、修改 102），+7693／−14659，净减 6966 行；包含较早历史目录退休与诊断搬迁，不能将其归因于本批。

最终输入下版本诊断 187 项通过；MuJoCo Pendulum、双轮车均完成 reset、一次控制推进、再次 reset 和重复 close，各观测 25 个 native 子步。GeoPhys Pendulum 完成同样短程，native 子步未观测，按 50 预留；GeoPhys 双轮车在上一输入 `fceb727f` 已短程通过，本批两任务使用共同 builder，当前差异将请求中相同 provider 直接传入原有 source 编译并核对 backend，但未按最终输入重复运行该路线。Isaac、renderer、两个桌面任务与完整 Solution 本批未复验。冻结输入、双锁、预算与收据在 ignored `workspace/maintenance/v211_effort_request_20261112/`。E01～E04 仍未整体接收。


### 6.134 Solution 与普通动作共享 interval 作用域

输入 `90225da0`；实施前复核 GOV、ENV-03／05、SUBJ、CTRL-01／02／05 及四任务当前执行链。普通 action 已经经过共同 interval 作用域，但 position Solution 与可切换 physical Solution 分支直接准备并执行 interval，绕过该作用域；它们虽然使用同一提交器，任务力等 interval 资源仍可能被漏掉。现在这两条 Solution 分支在完成各自必要的动作转换后调用共同 `_step`，与其他 Solution 共享任务／caller 力作用域、控制准备、故障锁存和 interval 执行；删除仅供旧分支使用的 `_step_position_profile`。Solution 已执行 `act` 后失败仍 fault，typed position／effort 及提交 owner 不变。本项未消除所有 Position／physical 的合法能力分派。

生产修改 1 文件 +3／−12，净减 9 行；版本诊断修改 1 文件 +13／−1，实测可切换 effort Solution 进入共同作用域、提交与录制；本文新增记录。无新增、删除或整文件迁移；项目 tracked 文件数保持 1357。相对 `1f1359ee` 的 task_env 差异为 134 文件（新增 12、删除 20、修改 102），+7708／−14671，净减 6963 行，含此前历史目录退休与诊断迁移，不代表本批贡献。

最终输入版本诊断 187 项通过；其中的 MuJoCo 可切换 R3 effort Solution 验证了该路径一个真实 interval 和 recorder，未单独统计 native 子步。双锁冻结探针中，MuJoCo PickCube R3 与 NutAssembly 各完成一次正式 Solution 推进、再次 reset、close，分别观测 5 个 native 子步，均非完整 Solution。附加任务力探针误填 `panda` case，脚本实际选择普通任务并在调用不存在的任务力工厂前失败，native 推进 0，不是产品失败也不作为有效功能证据；输入与记录位于 `workspace/maintenance/v211_solution_interval_20261112/`。Isaac position Solution、GeoPhys、renderer、完整 Solution 本批未复验；其原有证据保留原输入和范围。E01～E04 仍未整体接收。


### 6.135 普通 Robot 拥有其 source 根目录

输入 `894d2725`；实施前重新核对台账 GOV、TASK-04、ENV、SUBJ-02／03、CTRL 和 source 所有权。Pendulum 与双轮车的 MJCF 字节已经由各自 Robot 声明，但相对资产根目录仍由对应 Task 物理文件提供；这使 source 解释依赖 Task 文件位置。现由 Robot 声明 source 根目录，共同 effort source 编译器直接消费，Task binding 不再传递 source 路径。两个现有 inline source 不含外部资源；该变更说明路径归属，不证明任意外部资产或 Robot 可组合。source 字节、闭包／身份、传动与 provider 校验保持。

生产修改 6 文件 +9／−10，净减 1 行；版本诊断修改 1 文件 +18／−2，检查两种 Robot 声明的替代目录确实传入 Runtime source；本文新增记录。无新增、删除或整文件迁移，tracked 项目文件数保持 1357。相对 `1f1359ee` 的 task_env 差异为 134 文件（新增 12、删除 20、修改 102），+7726／−14674，净减 6948 行，其中包括此前历史路径退休及诊断迁移，不能归因于本批。

最终输入版本诊断 189 项通过。MuJoCo Pendulum、双轮车均完成 reset、一次控制推进、再次 reset、重复 close，各观测 25 native 子步；GeoPhys Pendulum 完成同样短程，native 子步未观测，按 50 预留。GeoPhys 双轮车在此前 `fceb727f` 路线已短程通过，当前路径根目录变化后未重跑；由于 source 路径变化，不将旧结果当作最终输入复验。Isaac、renderer、桌面任务及完整 Solution 本批未复验。冻结输入、双锁、预算和收据位于 ignored `workspace/maintenance/v211_robot_source_root_20261112/`。装配／引用 source 和控制构造仍有未收敛边界，E01～E04 未整体接收。


### 6.136 PickCube effort 记录实际 source 身份

输入 `53a5777d`；实施前重读台账 GOV、ENTRY、TASK-01／02、ENV、SUBJ、CTRL 与 source 边界并核对当前调用链。正式 PickCube effort 构建先前将一次历史 source closure 的固定哈希写入本次 `source_sha256` 和 resolved configuration；本地验证发现它与真实 snapshot receipt 不同，不能准确标识本次 source。现在两个字段均来自本次已验证的 source closure。原有标准化闭包与 snapshot 字节检查继续保留；其资产路径改从所选 Robot 的 manifest 和实际 MJCF 声明取得，并检查 manifest owner、单个资产根及 mesh 目录归属，避免在该调用处重新硬编码仓库全局路径。Robot manifest 及现有 source 快照仍限制受支持资产；候选文件内历史标准化摘要和共同 source 机制尚待进一步迁移，本项不宣称候选职责已收口。

生产修改 1 文件 +15／−5，净增 10 行；版本诊断修改 1 文件 +4／−1，检查两个输出摘要均与本次 snapshot 一致；本文新增记录。无新增、删除或整文件迁移；项目 tracked 文件数保持 1357。相对 `1f1359ee` 的 task_env 差异 134 文件（新增 12、删除 20、修改 102），+7739／−14674，净减 6935 行，包含先前退休旧路径和诊断迁移，不归因于本批。

最终输入版本诊断 189 项通过。MuJoCo PickCube direct effort（含 1.5 N 任务力）与 joint effort 各完成 reset、一次控制推进、再次 reset 和重复 close，各观测 5 个 native 子步；GeoPhys direct effort 同样完成短程，native 子步未观测，按 50 预留。此项不重开旧 COM 历史判据。Isaac、renderer、Nut、两个普通任务及完整 Solution 本批未复验。冻结输入、双锁和收据位于 ignored `workspace/maintenance/v211_actual_closure_20261112/`。E01～E04 未整体接收。


### 6.137 移除历史整场景摘要准入

输入 `c5de70fc`；实施前再次核对 GOV、ENTRY、TASK-01／02、ENV、SUBJ、CTRL 和 source 边界。正式 PickCube effort 构建原来以历史运行的标准化 SHA-256 限定整个 Task／Robot MJCF 闭包，而非只检查 Robot 资产。将任务桌面半宽从 0.28 改为 0.29 时，原输入在主体／传动检查之前被该旧摘要拒绝。现移除此固定整场景资格和只服务它的闭包归一化 helper；保留本次 source 与 receipt 的闭包一致、snapshot 字节、所选 Robot manifest owner／资产根和 MJCF mesh 目录归属检查，以及后续 Robot 通道、native 传动、Scene／Artifact 映射检查。实际 source 闭包继续进入运行身份。此变化不再保证整份场景与某次历史字节完全一致，也不宣称支持任意修改过的 Robot 资产；历史精确资格及原结论不迁移到新 source。

生产修改 2 文件 +3／−31，净减 28 行；版本诊断修改 2 文件 +36／−0，验证替换 Task 桌面声明仍生成 source、实际 snapshot 身份和 Controller，并为真实探针提供同一声明；本文新增记录。无新增、删除或整文件迁移；tracked 项目文件数保持 1357。相对 `1f1359ee` 的 task_env 差异 134 文件（新增 12、删除 20、修改 102），+7749／−14676，净减 6927 行；包含此前旧路径退休与诊断迁移，不归因于本批。

最终输入版本诊断 190 项通过；其中保留 source 变化／snapshot 不一致拒绝与错误 tendon 传动拒绝。使用内部 Task 声明将桌面半宽改为 0.29 的正式 PickCube direct effort，在 MuJoCo 和 GeoPhys 上分别完成 reset、控制推进、再次 reset 和重复 close；MuJoCo 观测 5 native 子步，GeoPhys 未观测，按 50 预留。默认 MuJoCo joint effort 也完成短程并观测 5 子步。声明通过诊断注入，并非宣称新公开配置字段；不扩大任意资产或组件组合支持。Isaac、renderer、其他任务及完整 Solution 本批未复验；历史证据按原 source 身份保留。冻结输入、双锁、预算和收据在 ignored `workspace/maintenance/v211_task_scene_declaration_20261112/`。E01～E04 尚未整体接收。


### 6.138 桌面 source 消费 Robot 资产声明

输入 `bece0df4`；实施前重审台账 GOV、ENTRY、TASK、ENV、SUBJ-02／03、CTRL 和 SRC。PickCube／Nut 的 source builder 此前固定读取仓库 Panda 路径，MJCF 快照器也只接受同一个固定 assets 路径，即使所选 Robot manifest 声明了不同根目录。现在 Agent 的单 MJCF source 从其 manifest 解析并核对 owner／源文件与根目录，两个桌面 Task composer 接受这个实际源；快照器按 source 中组件的 manifest 收集允许根目录，解析相对路径并拒绝越界、路径逃逸、缺失与冲突，继续以真实字节建立快照和 closure。装配 Panda 的参考替换边界仍存在；本项不声称任意 Robot、任意外部 MJCF 或 source 组合都受支持。

生产修改 6 文件 +36／−19，净增 17 行；版本诊断修改 2 文件 +56／−7，检查两任务重定位 Robot source、快照完整性、未声明根目录拒绝及真实探针；本文新增记录。无新增、删除或整文件迁移；tracked 项目文件数保持 1357。相对 `1f1359ee` 的 task_env 差异 136 文件（新增 12、删除 20、修改 104），+7832／−14693，净减 6861 行；包含先前旧路径退休及诊断迁移，不归因于本批。

最终生产输入版本诊断 193 项通过；随后仅修正探针输出变量，不影响 pytest 覆盖的生产代码。MuJoCo PickCube 和 Nut 分别使用实际复制到独立目录、由所选 Robot 声明的 Panda MJCF／资产完成 Solution 单步、再次 reset 和重复 close，各观测 5 个 native 子步，非完整 Solution；MuJoCo 装配 Panda 短程完成并观测 5 子步。GeoPhys PickCube Solution 短程通过，native 子步未观测，按 50 预留。首次重定位探针在成功构造后因诊断变量未定义而失败，native 推进 0；修正后使用单独目录重跑通过，保留初次输入和结果。Isaac、renderer、普通任务和完整 Solution 本批未复验。冻结输入、双锁和收据在 ignored `workspace/maintenance/v211_declared_tabletop_source_20261112/`。E01～E04 未整体接收。
