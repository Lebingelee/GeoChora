# 5c 后代码与项目优化：现状诊断、迁移要求与逐项验收台账

编写日期：2026-11-11。状态：`DIAGNOSTIC_BASELINE_AND_MAINTAINER_DECISIONS`。

本文用于 5c 功能接收后的强制优化，不是新的 native 执行授权，不是已经完成优化的报告，也不改变正在执行的单元 7／8 Goal。本次只增加本文；没有修改生产代码、运行引擎、清理 workspace、切换／删除分支、修改 gitlink 或提交其他写入者的改动。

## 0. 接手者先读：究竟要交付什么

GeoChora v2.1.1 的目的，是让任务开发者以清楚的声明与配置组合 Task、Robot、Controller、physics provider、renderer，构建环境，施加动作，取得状态和图像。它不应要求开发者为每个 backend／renderer 复制一种任务环境，或了解 F06、某轮 candidate UID、内部 receipt 哈希和临时 source 目录，才能执行普通任务。

当前已经有大量真实成果：共同主体与 Controller 绑定、场景 interval、唯一 RuntimeSession、三家 provider 的部分真实路线、原生和跨组合图像。但是，“这些具体路线分别运行过”和“普通用户能通过统一且易懂的生产链使用这些能力”仍是两个结论。本文要收口后一个问题，同时保住前一个问题的有效成果。

**必须完成的顺序：**5c 的实际功能及单元 9 综合验收 → 本文规定的代码／入口／项目优化 → 定向复验及人工接收 → G06。不能再以“G07 会清理”为理由跳过本次优化。G07 仍处理其原有最终集成范围；本文不把整个 G07 矩阵提前搬进来。

给非代码读者的判断方法：

1. 换 renderer 时，如果要换另一个 PickCube 环境类、给任务文件增加构建函数，而不是改变配置和相应 adapter，这条优化尚未完成。
2. 换 Robot 时，如果公共 Env 必须知道 Panda 的七关节、夹爪或特定 profile 才能 reset／发布图像，职责仍未收敛。
3. 报告只写“若干测试通过”，却没有指出普通用户入口和实际运行 owner，不能签收。
4. 把旧代码完整搬到一个新文件、再包一层共同类，不能作为消除重复 owner 的证据。
5. 删除必要的身份、单位、时钟、冲突或故障检查，也不是代码简化。

### 0.1 本台账的使用方式

- 按编号逐项处理。每项给出位置、当前事实、问题机制、目标职责、实施动作和退出证据。
- `确认`表示本次静态源码或文件内容可直接支持该事实；不代表已复现 native 故障。
- `待核`表示存在具体迁移／兼容风险，必须完成指定的调用者或运行核对；不能直接写成产品缺陷。
- `保全`表示已有正确机制应保留。完成方式可以是核对后原样保留，不要求为了“有改动”再次实现。
- 每项最终只能是 `PASS`，或经维护者明确同意、说明理由的 `NOT_APPLICABLE`。未经同意的 `DEFERRED`、`BLOCKED`、`NOT_RUN` 不能用于宣布本文范围全部完成。
- “全部完成”指本文冻结的职责和受支持能力范围已逐项对账，不表示全仓库所有文件无 bug，也不要求实现所有 provider 的任意组合。新发现的实质问题加入台账，不用无限扩矩阵代替定位。

严重性标记描述对本次目标的影响：`P0` 为共同生产架构／基本正确性必须闭合，`P1` 为实际使用、兼容或项目恢复的必做整理，`P2` 为有明确边界的维护核对。它们不是宣称发现了相同数量的新运行 bug；合法能力和已经修复的行为也有保全项。

## 1. 维护者已明确的决定

本节来自本次侧边讨论中的直接答复，优先于与之冲突的旧工作包。**决定了工作方向，不等于已经执行删除或清理。**

| 议题 | 已确定要求 | 实施时的含义 |
| --- | --- | --- |
| 代码职责 | Task 仅保留任务声明／语义／配置／Solution 与薄绑定；Robot、Controller、provider、renderer 各自拥有实现 | 禁止复制生命周期、公共层任务名特判、仅为旧测试存在的产品分支；保留真实能力分派和必要薄兼容导出 |
| 基础验收 | 正式 `make_env`，四主体共同构建／Controller／reset／step／close；三条原生和一个跨组合 RGB 按影响复用或最短补测 | 不重跑整张历史矩阵，不用合成测试代替真实路线 |
| 完整 Solution | 单 seed，多个 provider 各跑一次 Solution；至少 MuJoCo 的 Solution 要任务成功 | 以 PickCube、NutAssembly 已有正式 Solution 为对象，按两任务各自公开支持的 provider 执行；具体 seed 在执行包冻结。其他 provider 的任务结果分别报告，不能把“运行完但未成功”改成 task-success |
| 历史证据 | “仅保留最终成功结果及核心诊断”；一个 stage 多 attempt 归并为一份最终交付，诊断也只保留核心 | 不要求保存所有旧 attempt 和失败输出。最终保留集必须仍能支持其成功结论；依赖的 source、原始结果和必要核心诊断不能被误删 |
| 分支 | 复用当前阶段主题分支；优化验收后清理旧 worktree／分支 | 保留 `main`、`develop`、版本分支与一个当前分支；不因一次 Goal 再建分支 |
| 版本分支白名单 | `v1.1.0`、`v2.0.0`、`v2.1.0`，以及届时确定的 `v2.1.1`；release tag 保留 | 不能为了匹配名单自动创建／移动版本 ref；冻结 tag 不改写；清理前先保全独有提交和本地文件 |

### 1.1 Solution 验收与旧最终矩阵的边界

维护者此次要求的是优化后的完整调用验证，不能退化为只执行一次 `step_with_solution`。每条被选中的正式路线从构造、reset、完整 Solution、任务评价、记录读回到 close 都要走完，并报告 runtime validity、任务成功、Solution completion 和清理结果。

MuJoCo 至少要成功；其他已支持 provider 各运行一次，不以跨 solver 轨迹逐点相同为门。若其他 provider 未完成，须区分“任务运行合法但该次 Solution 未成功”和“公共构建／控制／时钟／生命周期有缺陷”。后者仍属于优化必须解决的问题，不能借“只要求 MuJoCo 成功”放过。

原 [G07 7b](../goals/07-integration.md#7b) 的 PickCube 三 provider × 三 seed 最终门没有被此次讨论删除；它仍属于 G07。若要修改该门，应另有明确决定，不能由接手者自行解释为本次单 seed 已替代它。

### 1.2 仍须在实际优化包冻结的具体值

这些是执行包参数，不是让实施者重新猜架构：最终输入 HEAD／dirty diff、两任务的单个 seed、每条正式公开支持路线、资源预算、最终交付目录、受影响的精确测试节点、具体待删除路径与 refs。本文已确定职责和验收原则；native 授权、实际删除和分支集成仍须由相应执行包明确覆盖。

## 2. 本次核查基线和可信边界

### 2.1 真实 checkout 与持续变化的工作树

核查 checkout：`/home/lly/Program_Files/Geochora`。2026-11-11 14:20（Asia/Shanghai）观察到：

| 项 | 观察值 |
| --- | --- |
| Core HEAD | `17bde018c5499ce8872f24cc591e358b83c5b821` |
| 当前分支 | `codex/v211-stage5-diagnostic` |
| GeoPhys gitlink | `c1ea3cc9fb99ccbd1d31c36d6fc7b84aa936b3d7` |
| Menagerie gitlink | `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` |
| `workspace/`、`temp_output/` 被跟踪文件 | 本次 `git ls-files` 为 0；根目录 `temp_output/` 当时不存在 |

主线有活动实施者，且存在 13 个 tracked dirty 文件：四个诊断测试，`environment/{lifecycle,reference_env,types}.py`、`observations/selected_reference.py`、`runtime/sessions/{api,control,isaac_native_io,selected_materialization,state_initialization}.py`。本文不拥有这些修改，不替实施者提交或回退。

原有三个 untracked 保护输入：`MUJOCO_LOG.TXT`、`docs/maintenance/20261030_runtime_route_diagnostic_handoff.md`、`docs/module/task_env/v2.1.1/planning/stage3-gravity-compensation-proposal.md`。它们不是本次新建内容，不能作为“无用文件”清除。

抽样文件 SHA-256，仅用于识别本次审计时点，不是新的运行准入锁：

| 文件 | SHA-256 |
| --- | --- |
| `planning/stage5-5c-diagnostic-refactor-roadmap.md` | `24ecf4e33929a28d979f208fd13f4d694e1c8cfdda281943460f137ea7ca52b1` |
| `task_env/environment/reference_env.py` | `b9431e5c772a37e45bb683f848d641d4d1af59fa9e618b23a57f1c4a393b6820` |
| `task_env/runtime/sessions/isaac_native_io.py` | `67c820649172cf3c71fa5804ccb608e3ae3986daa92d64795a6fb17da1e2ce79` |
| `task_env/render/camera/task_rgb.py` | `4aeb6224ecf1c016c9fcde1e4c6b4026f48cd29f45a810603d20dbdc9c114c3d` |
| `task_env/runtime/sessions/control.py` | `7c497166aaa8f2618616669ff3278956657faa059d2c558b1cb94c7fa222992c` |

后续发现行号或代码已变，应以符号、实际 diff 和当前生产 caller 复核，不机械重做已经修好的问题，也不把本文当成当前 worker 的实时状态。

### 2.2 核查方法及没有进行的工作

使用现有 CodeGraph 定位符号和调用者，再核对其提示已 drift 的磁盘源码、Python AST、文档、Git refs 与 workspace 第一层目录。没有刷新 CodeGraph 索引，没有导入 Core／provider SDK，没有解析冻结 MJCF／USD 资产，没有运行 native／GPU／GUI 或新的物理测试。

本次对关键生产路径进行了源码核查；不声称逐行审阅整个 `alg/`、GeoPhys、第三方资产或所有历史脚本。后文对未深审的外部调用者明确列出核查入口，不虚构其存在 bug。主线最新 candidate 的完成状态以其正式返包和独立主审为准。

### 2.3 已有成果怎样保留

- G03、G04、5a、5b 和 5c 单元 1～6 的有界接收按各自身份保留；不因为目录需要优化而全部推翻。
- 单元 4 证明过共同主体、Controller、interval、双 writer 等受测交集，不等于所有任务构建入口或所有 component 调用者都完成迁移。
- Position 控制器、R1／R3、effort、BodyWrench、开环序列各自的物理语义保留。不得把统一理解为全部替换成 torque。
- 单 Env 的 renderer 在构建时固定，运行中切换已延后；本次不重新加入该要求。
- 观察相机可以程序移动，不强制鼠标接线；不重新引入已人工接收图像的任意像素评分门。
- R05c 新候选成功不转移历史 Qualification；旧 COM 严格判据和维护者采纳的有界修订分别记录，不由优化改写。

## 3. 接手时必须对照的文件

这些文件回答不同问题，不允许随手挑一个旧 Goal 当作最新架构。

### 3.1 v2.1.1 规范与版本出口

| 文件 | 本次必须使用的内容 |
| --- | --- |
| [版本入口](../README.md)、[总路线图](roadmap.md)、[执行与验收](execution-and-acceptance.md) | 七阶段、依赖、权威入口及阶段出口 |
| [G01](../goals/01-protocols.md)、[G02](../goals/02-pickcube-solution.md) | 协议冻结与原任务／Solution 语义 |
| [G03](../goals/03-backends.md)、[G04](../goals/04-control.md) | provider、Controller、命令、反馈和 reset 已承诺范围 |
| [G05](../goals/05-rendering.md)、[G06](../goals/06-parallel.md)、[G07](../goals/07-integration.md) | 图像、真实跨组合、后续并行与最终集成的边界 |
| [统一任务表示](../contracts/unified-task-representation.md) | Task／Scene／Asset／Assembly 的职责及身份 |
| [physics](../contracts/physics-provider.md)、[render](../contracts/render-provider.md) | 原生映射、唯一推进、视觉消费及能力拒绝 |
| [控制](../contracts/control-and-feedback.md)、[生命周期／数据](../contracts/lifecycle-and-data.md) | 命令物理意义、外部／内部时间、reset、图像 ownership |
| [公共 API](../api/README.md)、[实施映射](protocol-implementation-map.md)、[指南](../guides/README.md) | 用户实际调用形式、owner 与示例 |

### 3.2 整理规范、5c 诊断和单元 4 重构

| 文件 | 必须解决的关系 |
| --- | --- |
| [阶段 3 前整理方案](pre-stage3-environment-refactor.md) 第 2.1／2.2／2.5 节 | 任务四业务文件、禁止候选文件回流、共同 Env、曾延期的欠账 |
| [诊断与核心边界](../../../../global/diagnostics-and-code-boundaries.md)、[全局架构](../../../../global/architecture.md)、[owner](../../../../global/ownership.md) | 诊断不得反向支配产品；必要验证不能一起删除 |
| [5c 固定 renderer](stage5-5c-fixed-renderer-scope.md) | 同步 RGB、固定 renderer、最少真实跨组合、非 PickCube 特化 |
| [5c 诊断路线](stage5-5c-diagnostic-refactor-roadmap.md) | 单元 0～9 为工作依赖，不是要求重复跑九轮历史矩阵 |
| [诊断基线](stage5-5c-human-diagnosis-baseline.md)、[架构审计](stage5-5c-human-diagnosis-architecture-audit.md)、[Runtime／控制审计](stage5-5c-unified-runtime-control-audit.md) | 为什么 profile／component／renderer 曾互相越权；哪些是历史状态 |
| 外部工作文档 `reviews/V211_G05_5c_unit4_侧边方案主审与实施路线_20261109.md` | 单元 4 统一主体、场景命令、唯一 Runtime、开环／闭环边界的主设计 |
| 外部工作文档 `handoffs/V211_G05_5c_unit4_侧边Sol执行授权与goal-prompt_20261109.md` | 当时的具体门、权限及禁止绕行事项；旧资源窗口不能直接沿用 |
| 外部工作文档 `reviews/V211_G05_5c_unit004_复审更正与有界接收建议_170d544c.md` | 接收范围及撤回过严的 Python Robot token 要求，防止重新加回 |
| 外部工作文档单元 5 `8965eec5`、单元 6 `4c8a0be0` 主审 | 两简单主体三 provider、匹配与四主体能力的真实边界 |
| 外部工作文档 `reviews/V211_G05_unit7_8_Isaac成功路径对照_20261111.md` | 旧成功 task sensor 与当前候选差异，不是复制旧 PASS 的授权 |

“外部工作文档”根为 `/home/lly/Documents/ChatGPT/GeoChora v2.1.1/`。优化收尾时把仍有效的设计和接收摘要归到仓库的规范入口；不要求产品用户依赖此绝对路径，也不搬入全部历史聊天。

## 4. 四个根本问题：不是目录审美问题

### GOV-01：简化任务构建早有明确要求，却未持续约束后续新增能力

**确认／P0。位置：**`planning/pre-stage3-environment-refactor.md:61` 规定 PickCube／Nut 四业务文件；`:72` 明确禁止再增加 task 内 lifecycle／guard／candidate／diagnostic 实现；`:59` 明确不能把全部旧逻辑塞进 specialization。当前 PickCube 又包含 `physical_candidate.py`、`physical_isaac_candidate.py`、`physical_mass_profile.py`、`physical_usd_profile.py`，并从 `tasks/__init__.py` 导出两个 candidate Env。

**具体问题机制：**每一轮受限路线都能以“先跑通”为理由增加入口，但没有同时指定它最终由哪个正式入口调用、哪个 owner 维护、何时消除重复构造。下一轮看到旧 candidate，便把它当作唯一生产模板。最终用户必须先懂历史实验，才能选运行方式。

**必须做：**建立正式任务入口和支持配置清单；让 candidate 的已验证能力由正式入口消费。旧 UID 若需兼容，只允许把旧输入翻译为同一构建请求，不拥有第二套 reset／camera／Controller 编排。额外文件按其实际职责迁移，不按文件名整包删除。

**不能这样交差：**仅删导出导致已支持 caller 失效；仅改 candidate 名称；将 460 行候选实现原样搬进 specialization；以 candidate 有真实 RGB 证明正式入口已统一。

- [ ] 正常用户配置能进入同一实际构建链；新增 renderer 不再新增任务 Env。
- [ ] 每个旧 UID 的正式替代、兼容行为或明确退休决定有记录；必要 caller 迁移完成。
- [ ] Task 目录和公共模块都符合职责要求；不是仅在目录外隐藏同样的重复逻辑。

### GOV-02：有界路线接收被不当地理解成整体架构接收

**确认／P0。位置：**单元 4 有界接收、单元 5／6 报告，与 `registry.make_env` 的多 factory、`PickCubeReferenceEnv.selected_binding`、`SelectedReferenceEnv.__init__`、旧 component bootstrap 同时存在。

**具体问题机制：**一条真实路线证实“该输入下的构造和控制有效”；它没有覆盖所有 UID、所有 factory、所有配置解析和旧调用者。后续却默认“统一已经完成”，因此没有回查正式任务能否表达同一能力。旧入口继续获得修复，新入口仍缺选项，代码形成多个半完成主线。

**必须做：**用三列分别登记“设计要求”“最终实现路径”“证据范围”。只对实际受改动路径补最短验证。架构接收必须看调用者、owner 与数据流，不以 PASS 数量替代；真实运行接收必须看最终输入身份，不用共同类名替代。

- [ ] 四主体及正式 Task 的构建／控制／状态 owner 均能画到具体方法。
- [ ] 接收表明确哪些复用、哪些最终代码重测，哪些仍不支持；没有扩大历史 claim。
- [ ] 对本文所有条目逐项签收后才宣布优化完成，不能再只发局部技术 PASS。

### GOV-03：清理时间在 5c 后与 G07 之间摇摆，欠账不断延期

**确认／P1。位置：**最新 5c 路线与单元 4 讨论把大批清理放在 5c 完整接收后；`goals/07-integration.md#7a` 和全局规范仍把阶段 3～6 诊断耦合集中清理放在 7a；阶段 3 前方案又有多个限时延期记录。

**具体问题机制：**这些安排在各自历史时点有意义，但没有一个当前计划说明“哪些现在必做，哪些仍归 G07”。执行者可以合理地在每轮跳过；接手者也无法判断“不增加重复 task 环境”是当下规则还是以后愿望。

**必须做：**本次维护者决定作为当前停门：5c 后、G06 前完成本文优化；G07 保留对后续 G06 新增调用者和最终版本的收口。更新当前路线、执行与验收、API／恢复入口及相关 Skill 的当前状态；历史延期记录保留时点，不回写成当时已完成。

- [ ] 当前导航只给出一种清楚的优化时机和必达清单。
- [ ] G07 与本次优化无重复无空洞；后续不得再以旧 G07 文字跳过本文。

### GOV-04：“当前状态”分散且相互冲突，后续执行会选错基线

**确认／P1。位置：**`api/README.md:9` 仍写单元 4 开发中尚未接收；`:15` 仍按旧 COM 门说明未通过；`maintenance/recovery.md` 累积多个旧“当前”；`docs/global/architecture.md` 仍有 selected state-only／v2.1.1 规划态描述。最新接收又分布于外部 reviews 和 ignored workspace。

**为什么严重：**同一名新 agent 可以分别从 API、路线或旧 Goal 得出互相冲突的实现要求，并各自找到文本“支持”。它可能重加已撤回的 gate、重做已接收工作，或把临时 candidate 当作正式 API。当前正在发生的“改进 adapter 后仍围绕旧路线补测试”与这种恢复困难有关，但不能只凭文档把全部运行故障归因于它。

**必须做：**一个仓库内当前摘要记录 HEAD／dirty 归属、阶段、正式入口、能力边界、有效主审、下一停门；其他文档引用该摘要或明确历史日期。历史报告不删改其结果；过时现行教程必须改正，不能只补一条链接。

- [ ] 新接手者从版本 README 能找到唯一当前状态、正式示例和优化台账。
- [ ] 不再出现无日期的相反“当前结论”；历史设计与当前能力分列。
- [ ] 对撤回过严保护、COM 有界决定、R05c 非重资格的说明一致。

## 5. 优化后的预期生产链

```text
make_env(正式 task UID, config=公开配置)
  → 一次配置解析：Task / Robot / Controller / physics / renderer / camera
  → Task 提供场景物体、初始化、奖励／终止及任务 observation
  → Robot 提供主体、嵌套 Assembly、根约束、通道、状态／模型能力
  → Controller 依据需求匹配主体，声明 action 与 typed 输出
  → source／Scene／Assembly 绑定；provider adapter 完成格式与 native 映射
  → 一个 RuntimeSession，持有物理与物化资源
  → reset：Task reset 请求 → source-bound reset → Controller 初始化 → 发布状态
  → step：action／Solution action → Controller；组合 Task／caller typed 贡献
         → 一个场景 interval → provider 执行 → 发布 boundary／clock／状态
  → observation：任务／本体状态 + renderer 完成后的同步图像
  → render：观察显示／离屏消费当前状态，不再推进物理
  → close：按所有权释放相机／renderer／session／App lease
```

这张图不要求新增万能 Builder／Manager，不要求合并所有 source 类型或抹平 snapshot v1／v2 编码，也不要求三 provider 共用 native 对象。优先扩展已有 `ReferenceTaskBinding`、`ControlledSubjectV1`、Runtime builder、state initialization、场景提交和 render registry。

| Owner | 应知道什么 | 不应知道什么 |
| --- | --- | --- |
| Task | 桌面／方块／螺母，reset 分布，任务成功和 Solution 语义 | SDK App 启动、RTX sensor 预热、通用控制提交、每家 native DOF 构造 |
| Robot | 本体资产、具名关节／Frame、嵌套、根约束、传动与兼容 Controller 能力 | 任务奖励、临时 workspace、某次候选运行的准入事实 |
| Controller | action、状态／模型需求、typed 输出及自身 reset | live provider SDK、Task 类名、renderer 选择 |
| Env／生命周期 | 组合声明、预检、reset／step／fault／close 顺序和固定 observation | Panda 专用关节数、具体 profile 决定的 native 构建细节 |
| provider adapter | source 格式、native 名称／通道映射、能力准入、唯一物理推进 | 复制 Task 的奖励／Solution 或另一套 Env 状态机 |
| renderer adapter | visual source／状态映射、相机、context／sensor、同步和视觉资源 | Controller 计算、修改 Task 语义、启动第二物理求解器 |
| Recorder／reader | 固定 schema、实际身份、状态／图像／命令记录及独立读回 | 为某个诊断脚本硬编码一份任务物理拓扑 |

### 5.1 可实际开工的 owner 迁移对照

这张表规定改动落点，不要求实施者猜一套新架构。具体签名在对应局部包冻结，不能绕开已有 owner 新建平行框架。

| 当前决策点 | 修改后由谁处理 | 公共层还做什么 |
| --- | --- | --- |
| `registry.make_env` 根据 factory 标志决定何时配置 RGB | `resolve_task_env_config/resolve_execution_plan` 规范化请求；Task binding 提交声明；renderer factory 提供准备能力 | registry 选择正式 Task，统一调用 resolved 构建，并处理构造失败 |
| candidate `_build_candidate`／Isaac `from_reference_config` 同时拼控制和 App | Task 提交物体／默认选择；Robot recipe 与 Controller binding；`build_selected_runtime`／provider 和 renderer owners 执行准备 | candidate 如需保留只翻译旧配置到上述请求 |
| `reference_env._configure_task_rgb` 设置 RTX、pair 和颜色 | 现有 `RenderBackendDescriptor`／camera capability 分派到相应 factory；factory 规范化设备、色彩和借用／自有资源 | Env 组合固定 output space，按生命周期调用采集／close |
| Env `_prepare_task_rgb_state_binding` 挑 source 格式、准备 visual projection | state/source owner 提供具名查询绑定；renderer adapter 声明 requirements 并准备其 visual source | Env 协调同一 boundary 的状态与 image 完成，不实现 native 映射 |
| Env 依据 profile 决定 materialization／Controller 初始化 | 已解析 `SelectedControllerBinding` 提供 RuntimeBuilder、InitialState 和控制能力；provider 负责实际 native 核验 | reset 统一预检、事务和故障处理，调用已绑定 owner |
| H5 reader 按 R03c 固定 64／65、writer 名称判断正常性 | 通用 reader 校验记录声明；精确实验 oracle 放诊断 Judge 或单独兼容 reader | 公共读 API 分派格式，不假装精确旧 oracle 支持任意任务 |
| Task 内提供 source／Controller／相机实际实现 | Task 保留声明及 task-specific semantic mapping；其余归现有 Robot／Controller／assembly／runtime／render | Task specialization 只绑定已有能力，不拥有 native 生命周期 |

### 5.2 目录／模块覆盖索引

本文覆盖的是参与本次 v2.1.1 生产链和项目整理的模块，不假设每个模块都有缺陷。表中未深审部分需要按真实 caller 核对，不能由后续 agent 将“待核”升级成无证据的 bug。

| 模块／目录 | 关键路径及对应条目 |
| --- | --- |
| `task_env/registry.py`、顶层 exports | 正式构造、惰性注册、旧UID：ENTRY、CALL-01／03 |
| `task_env/tasks/` | 声明／reset／评价／Solution、候选入口：TASK-01～04 |
| `task_env/environment/` | config、共同生命周期、状态／info编排：ENTRY-02／03、ENV-01～05 |
| `task_env/robots/` | 本体、recipe、嵌套、默认Controller、runtime facade：SUBJ、CTRL-03 |
| `task_env/controllers/` | 旧ActionAdapter和canonical Controller、typed目标／命令、模型：CTRL-01～05 |
| `task_env/artifacts/` | Scene／Task／Assembly／state／binding编码及identity：SUBJ-03、SRC、REC-02 |
| `task_env/assembly/` | source闭包、资产选择、固定附件、组合／USD delivery：SRC-01～04 |
| `task_env/runtime/` | 旧bootstrap／boundary与选定session：RUN-01～04 |
| `task_env/runtime/sessions/` | 物化、状态、统一控制、provider、worker：ENV-02、CTRL、RUN、REN-04／05 |
| `task_env/render/` | registry、single／parallel、相机、display／capture：REN-01～08 |
| `task_env/observations/` | 固定schema、具名状态、相机与任务RGB：OBS-01／02、REN-03 |
| `task_env/recorders/`、`trajectory/` | 记录、reader、旧格式、重执行：REC-01～03 |
| `task_env/planners/`、`objects/`、`reporter/`、`utils/` | Task物体、目标生成、结果呈现和路径：CALL-03 |
| `task_env/vectorization/`、`alg/` | pure build、space、旧wrapper：CALL-02；不在本次实现完整G06／训练 |
| `task_env/diagnostics/`、测试fixture／外部runner | 纯度、授权、oracle与探针：TEST-01～04 |
| `task_env/script/`、根 `examples/` | 正式调用方式、camera／replay／Solution入口：CALL-01 |
| 根 `bench_deploy/libero/` | benchmark自有任务／Controller与Core公共合同的接合：CALL-04 |
| `GeoPhys/` submodule | Core只用公开runtime／render接口，gitlink与provider能力保全：RUN-03、REN-05；本次不审计全部solver内部 |
| 根 `asset/` | 第三方冻结资产、delivery／source来源：SRC-04、PROJ-02；不是可任意删除的生成物 |
| `docs/`、`task_env/doc/`、`.agents/skills/` | 当前／历史、规范／实现、导航与接手：GOV、DOC |
| `workspace/`、真实存在的 `temp_outputs/` | 最终证据、核心诊断、缓存／日志：PROJ-01～04 |
| Git refs／worktrees／submodules | 提交保全、stage分支、旧checkout：BRANCH-01 |

## 6. 正式入口和 Task：逐路径诊断

### ENTRY-01：`make_env` 按类标志选择多种构造协议

**确认／P0。位置：**`task_env/registry.py:130 make_env`；`:161 factory_owns_rgb`、`:168 finish`、`:186 uses_selected_public_config`、`:191 from_reference_config`、`:203` component fallback。

**现在怎样走：**先判断环境类是否自己准备 task RGB，再判断 selected public config、是否覆盖 reference factory、是否 component；一部分在 factory 末尾调用 Env 私有 `_configure_task_rgb`，另一部分在构造前把参数交回任务类。相同公开函数并不意味着相同构建协议。

**为什么有问题：**任务实现只要增减一个类属性，就会改变何时创建 App、何时验证相机、谁负责失败清理。支持 renderer 的能力看起来像任务类属性，而不是可查询的 adapter 能力。新任务很容易复制最复杂的旧 constructor。

**如何改：**以一次 resolved configuration 和一个任务声明／绑定输入为规范入口；兼容 factory 只做旧输入适配。相机、renderer 的需求进入共同构建请求，adapter 按能力参与准备；factory 不根据具体任务或历史 candidate 决定生命周期。允许保留 component 的 `build_runtime=False` 纯装配能力，但需要作为明确构建能力，不靠反射猜方法是否覆盖。

**验收：**同一正式 Task UID 使用不同已支持配置；四主体入口有实际方法链；纯导入／配置查询不启动 SDK；构建失败只释放自有资源。旧 UID 若保留须转向同一链。无需增加新 `make_pickcube_*` 包装。

- [ ] ENTRY-01：规范构建协议及旧 factory 迁移完成。

### ENTRY-02：配置的同一概念在 selected 与 component 里有不同形状

**确认／P1。位置：**`environment/configuration.py:_resolve_robot_config`、`_resolve_selected_config`、`resolve_task_env_config`、`resolve_execution_plan`；`environment/config.py:ResolvedEnvConfig/ResolvedSelectedConfig`。

component 的 `robot` 主要承载 controller／gripper；selected 的 `robot` 要求恰好 `{uid}`，controller 顶层仅支持 gravity flag，具体 profile 又来自 task。provider／backend 既有 execution 层又有 legacy 参数。继续给每条分支加一个字段，会让用户无法预测配置覆盖顺序和错误来源。

**必须改：**先冻结一份用户配置和已解析结果的字段归属／优先级，保留旧输入的单向规范化。规范层只表达 Task、主体／Controller 选择和执行能力；限定 profile 作为能力实现的参数，不作为另一份用户工厂。配置冲突、未知字段、相机输出不兼容在 native 前拒绝。不能通过删校验“支持全部 kwargs”。

**验收：**一个正式 YAML 与等价 mapping 得到同一有效选择；旧字段兼容或明确拒绝；改变 renderer 不改变 Robot／Controller 语义；effective config 可查询且不泄漏临时路径要求。

- [ ] ENTRY-02：字段、优先级、兼容映射和实际解析一致。

### ENTRY-03：任务 RGB 配置要求调用方先取得内部 Artifact 身份

**确认／P1。位置：**`registry.make_env` 的 `task_rgb_camera/task_renderer`；`reference_env._configure_task_rgb:2596` 检查 `camera.task_artifact_hash == artifact.identity_hash`；candidate factory 又自行处理 camera／observer／manifest。

**问题：**底层 `CameraGeometry` 绑定 Artifact 是必要的一致性保护，但普通用户在 Env 构造前可能还拿不到 Artifact。若只能先调用内部任务 builder 算出 hash，再构造 camera，公开 API 就没有达到简化目标。相机约束、renderer pair、颜色设置也混在 Env。

**必须改：**公开层接受普通相机声明，待声明编译后由既有 camera owner 生成绑定几何；高级调用者可继续传已绑定对象并严格验证。renderer 自己提供输出规格／能力约束，Env 组合固定 observation，不直接配置 Isaac RTX。禁止 fake hash 或取消 Artifact 关联。

**验收：**用户不手写 hash／receipt／lease 即可声明相机；错 Artifact 的高级输入仍拒绝；相机身份、输出规格在构造后可查询；不为 camera 添加任务专用 Env。

- [ ] ENTRY-03：相机用户声明和编译后绑定有清楚分工。

### TASK-01：PickCube 候选文件同时承担任务、控制、后端和渲染装配

**确认／P0。位置：**`tasks/pick_cube/physical_candidate.py:_build_candidate:258`、`_pickcube_mjcf_scene:230`、`_physical_pickcube_observation:40`；`physical_isaac_candidate.py:from_reference_config`；`physical_mass_profile.py`、`physical_usd_profile.py`；`tasks/__init__.py:9`。

**事实和纠正：**两个 PhysicalCandidateEnv 在 2026-11-06 的 `a7181de4` 已存在，不是当前 Isaac 续作新造。它们继承同一 SelectedReferenceEnv，不能说已经有三套完全独立物理 Runtime。但前置构建、控制选择、source workspace、camera／renderer 和 observation 有多套具体代码，仍在注册／导出链上。

**必须拆分的具体内容：**任务 reward／cube pose 和 reset 留 Task；Panda 通道、末端和传动回 Robot／Controller；质量模型 Controller 回 `controllers/canonical/` 和 model capability；F06 source／native drive 校验回 provider admission；renderer camera／App 准备回 renderer／session owner；candidate UID 只保留输入兼容桥或经决定退休。

**验收：**正式 PickCube 的配置能表达已支持的一体／装配、Controller、physics／renderer；各能力只有一个实际维护 owner。不得把四个文件整体搬入 specialization。旧受测 source、动作、夹爪限幅与故障边界按影响保全。

- [ ] TASK-01：文件逐段职责迁移、caller 与 UID 迁移对账完成。

### TASK-02：PickCube specialization 已成为超出“薄绑定”的第二中心

**确认／P1。位置：**`specialization.py` 约 1,046 行；`build_reference:218`、`build_isaac_reference:367`、`selected_binding:690`、`build_pickcube_isaac_scene:819`、`build_pickcube_isaac_runtime_input_v1:965`。

**具体痛点：**同文件连接默认配置、source 编译、R3、Isaac scene、USD runtime 输入和 Robot composition；`selected_binding` 对 MuJoCo 默认补 Panda、选择 source adapter，并携带桌面／方块实体映射。Task 选择自己的物体和默认 Robot 合理，但 native source 的装配与执行不能成为 Task 继续复制的工作。

**必须改：**薄绑定只提交 Task 声明／物体映射、默认选择和 Task-specific reset/evaluation hooks。Robot recipe 给出主体，provider composer 消费组合声明并返回映射。USD scene lowering 和 source 验证使用已有 assembly/provider owner，Task 不创建 native App 或相机。

**退出：**从本文件能直接读懂“任务是什么、默认选什么”，不用穿过 native 分支。保留 task-owned body/site 名称声明，不能为了通用性把 PickCube 的任务语义反塞进 runtime。

- [ ] TASK-02：specialization 减责有明确去向及正式调用证据。

### TASK-03：NutAssembly 内混有通用 native stream／guard 支持

**确认／P1。位置：**`tasks/nut_assembly/specialization.py` 中 `_native_feedback_sample`、`_native_interval_receipt`、gripper cadence diagnostic builders；`solution.py:GuardedTransitionEvaluator`、`NutAssemblyNativeFeedbackSampleV1`、`NutAssemblyNativeIntervalReceiptV1`。

**问题边界：**Nut 的阶段名、抓取判据、Solution 完成语义属于任务，不应为了四文件目标拆成任意碎片。反之，连续样本时间窗、stream receipt 解析、通用 replay／fault 验证和诊断 cadence 选择不应迫使其他任务 import Nut。

**必须改：**只抽取确有其他调用者或公共合同责任的通用部分到既有 completion／feedback／runtime／recorder owner；诊断入口移外部；Nut 阈值和策略留 config／solution。当前生产还在使用的严格 guard 窗口不得删除。

**验收：**完整 Nut Solution 在正式入口运行；修改公共反馈不要求改变 Nut 私有构造类；原任务成功、Solution completion、raw predicate、guard validity 分列。不能以只整理 PickCube 宣称整个任务层已优化。

- [ ] TASK-03：Nut 任务语义、公共支持与诊断完成归位。

### TASK-04：Pendulum／双轮车“引用既有主体”与旧 component scene 双入口

**确认＋待核／P1。位置：**`tasks/pendulum.py:PendulumEnv.from_reference_config:688`、`_PendulumSceneComposer:659`，双轮对应 `:594/:565`；`tasks/pendulum_physical.py`、`two_wheel_physical.py`；各自 `robots/` 模块。

**具体路径：**正常 selected factory 走 physical builder；`build_runtime=False` 仍回 component 配置与 SceneComposer。SceneComposer 直接拒绝额外 agents，因为原 MJCF 已拥有主体。保留“不再导入一份主体”是正确的，但现有 API 让“控制主体声明”和“agents 参数”像两套不同概念。

**必须改：**以 Robot 的 `references_existing` 等声明表达引用原主体；同一 assembly/resolver 识别原有实体与新装入实体，避免重复。旧 component 纯构建／batch caller 保留兼容桥，不能粗暴移除；Torque adapter 不能再成为绕过共同 Controller 的另一条施力链。任务自有 MJCF 可以保留，不要求为了统一复制 Panda source 方案。

**验收：**两任务 selected 与必要 component caller 的映射清楚；±2 N·m、双轮通道顺序／±1.5 N·m、reset／奖励和子步数不变；单层是同一主体机制的简单情况，不是按任务名临时分支。

- [ ] TASK-04：声明、实际物理实体和控制 writer 一一对应。

## 7. 公共 Env 和生命周期：逐路径诊断

### ENV-01：一个类名下仍有多种构建契约和大量专用状态

**确认／P0。位置：**`environment/reference_env.py:SelectedReferenceEnv` 约 5,098 行；`__init__:1345`、`_initialize_components`、`from_resolved_config:799`；`reference_binding.py`。

**事实：**`BaseTaskEnv` 已成为共同类的兼容名字，这项成果不能否定；但 `__init__` 按 `_uses_component_assembly`、绑定存在与类方法覆盖决定路径，仍有 `_leaf_position_candidate`、`_fixed_attachment_leaf_position_candidate`、`_mixed_control_candidate` 等参数。`from_resolved_config` 当时仍拒绝非空 kwargs 和 render_mode，candidate 则提供相应渲染。

**问题机制：**类名统一后，构造约定、状态成员和失败阶段没有全部统一。只读类名看不出某属性何时有效；加图像功能时又需要防御性 `getattr` 和特判。代码行数本身不是缺陷，但这里多职责和隐式状态组合可直接定位。

**必须改：**共同 Env 只接收已解析 binding／execution capabilities；构建请求明确需要哪些 owner，不靠 candidate bool 暗中增加能力。把 owner 实现归现有模块，Env 保持编排；不得新造第二个 UnifiedEnv 或把整个大类拆成同样越权的 mixin。

**验收：**构造契约、状态机和资源归属能用一张表解释；正式入口支持已接收能力；旧兼容路径不复制 reset／step。

- [ ] ENV-01：共同门面真实减责，不只是共同继承。

### ENV-02：reset／materialization 的 capability owner 与旧 profile 变量并存

**确认＋保全／P0。位置：**`reference_binding.resolve_reset_execution/prepare_selected_reset`、`selected_materialization.py` 的五种 RuntimeBuilder、`state_initialization.py` 四种 InitialState、`reference_env.reset/_reset`。

**现状：**单元 4 之后已经有真实 Runtime builder、state initialization 和能力式分派；不能再把“有 PositionInitialState”直接判为错误。但是 Env 仍持有 position／leaf／physical 等标志和多组 published state，必须逐分支确认谁作决定、谁执行 native、谁清理。

**必须逐项追踪：**Task reset sample 和 seed → target execution 预检 → 旧 episode 处理 → materialization → source-bound reset → 状态 publication → Controller reset → RGB 首帧 → 发布 observation。对每阶段写清失败前是否可保留旧 episode、失败后谁 fault／close。

**必须改的边界：**Panda profile 不能在公共 Env 决定 source/native 构造策略；绑定能力可以选择合法 typed initializer。保留 position／effort 不同需求与 state projection，不强行合并 v1／v2。reset backend／Controller 若与固定 renderer 不兼容，作用发生前拒绝。

**验收：**四主体最终代码最短 reset／非零 step／二次 reset／close；受影响失败边界一到两项；不以把 `if position_profile` 搬入新大类算完成。

- [ ] ENV-02：reset 每阶段实际 owner 和失败处理闭合。

### ENV-03：普通 action、Solution、ExpertAction、序列必须消费共同控制生命周期

**确认历史缺口＋待核最终实现／P0。位置：**`reference_env.step/step_with_solution/step_expert/_prepare_position_profile`；`control_lifecycle.prepare_selected_control_action`；`control_submission.submit_control_command`。

**为何列为必核：**此前已多次真实发现 Solution 入口绕共同提交、双叶只写入而未消费 lifecycle、Solution.act 副作用后转换异常不 fault，并做过修复。本文不把它们都重标为当前未修；优化迁移时必须保住它们的修复，并确认正式入口没有再保留旁路。

**必须做：**列所有受支持入口的动作来源、转换／预检副作用、lifecycle 创建、场景 interval、唯一提交与 feedback 回传。Solution 由调用方拥有，兼容 `step_with_solution` 不得创建第二调度器；副作用后失败须按既有机制 fault 并要求 reset，保留原异常及 cleanup 次错误。

**验收：**一项真正无副作用的拒绝和一项转换副作用后失败；普通 action 与完整 Solution 产生同一 owner 的真实提交记录。不得为验收创建只有 fake receipt 的公共路径。

- [ ] ENV-03：所有支持动作入口有共同 owner，无副作用失败语义明确。

### ENV-04：Env 内 observation／metadata 仍知道 Panda 和诊断路线

**确认／P1。位置：**`reference_env` 的 observation、metadata、expert info、physical action spec、recording hooks；`environment/metadata.py`；`observations/selected_reference.py`。

**问题：**公共 Env 为不同 profile 组装不同 Task／Robot 状态与 info，并直接维护多种图像元数据。普通环境开发者需要了解这些条件才能产生自洽 observation；同一 dict 的 shape、schema、实际数组可能来自不同 owner。近期 cross 重试记录中出现 schema key／task_uid／observation_builder 缺失，说明这不是单纯排版问题；不据此断言所有正式路线失败。

**必须改：**Robot／Controller／Task 声明各自状态需求和空间；observation owner 组合并固定 schema；Recorder 构造记录 metadata；Env 引用结果。Panda 的兼容观测投影可以保留，但必须由显式 Robot／Task projection 选择，不是通用默认。

- [ ] ENV-04：schema、space、实际 observation 和文档从同一声明对齐；不靠手工补 metadata 过门。

### ENV-05：资源关闭和故障状态分散，需要按所有权收口

**待核＋保全／P1。位置：**`reference_env.close`、`environment/lifecycle.py:EpisodeExecutionState/TaskLifecycleAdapter/SingleTaskLifecycleAdapter`、camera consumers、provider close receipts。

**问题边界：**多个类并不自动是多套生命周期，部分是共同协调器的不同适配。必须查清的是同一资源是否被多个 owner close、失败后是否仍返回旧帧、App 共享引用是否被单 Env 误释放、半构建资源由谁处理。

**必须做：**一张资源所有权表覆盖 session、native worker、App lease、task sensor、observer、窗口、独立 visual model、source snapshot、Recorder。borrowed 与 owned 明确；关闭失败标 unknown，不伪造 released。保留原生引擎进程级限制，不要求所有资源假装每 Env 独立。

- [ ] ENV-05：正常／重复 close、半构建失败和相机失败的受影响最小验证完成；无第二物理 owner。

## 8. Robot、Controller 与场景命令：逐路径诊断

### SUBJ-01：公共 Robot runtime 外观仍带 Panda 必需字段

**确认／P1。位置：**`robots/runtime.py:RobotRuntime:75` 要求 `gripper: PandaGripperController`、`base/ee/world`；`RobotFrameReference` 只允许 world/base/ee；`robots/base.py` 只是 `AgentComponent` 别名；`environment/protocols.py:AgentComponent` 与 `runtime/sessions/physical_control.py:ControlledSubjectV1` 并存。

**为什么需要处理：**Pendulum、双轮车是受控主体，但不天然有 Panda gripper 或末端。如果公共 runtime 外观只能表达机械臂，其他主体要么伪造字段，要么另走隐藏通道。单元 4 的 ControlledSubject 已解决许多真实绑定问题，优化应让公共使用面实际消费它，而不是再造一个 RobotV2。

**必须做：**以现有主体、具名 Frame／Joint、状态与能力作为基础外观；Panda 的 gripper／TCP 作为其有名能力和兼容投影。明确 Agent 描述、编译后的 ControlledSubject、live Robot handle 三者关系及持有者。支持只引用任务 MJCF 中已有主体，不自动导入第二份资产。

**验收：**四主体都有可理解的公开 Robot／Controller 查询；没有为了构造 Pendulum 生成虚假 ee／gripper；旧 Panda caller 仍能使用已承诺的属性或有明确兼容映射。

- [ ] SUBJ-01：公共主体外观不强制 Panda 部件，旧 facade 已处置。

### SUBJ-02：Robot 专用声明合理，但其调用不能把 source materialization 拉回 Robot

**确认＋保全／P0。位置：**`robots/panda.py:source_recipe/physical_subject_declaration`；`robots/assembled_panda.py:source_recipe/source_recipe_for_profile/physical_subject_declaration`；`robots/panda_position_binding.py`；`robots/source_recipe.py`。

**现状：**单元 4 已把 Robot source 声明与 MuJoCo 解析拆开，应保留。Panda 内出现 7＋2、手指 tendon 比例、固定 Menagerie 版本、arm／hand 结构是正确归属，不能搜索到 Panda 就删除。需要确认的是这些声明是否成为所有正式入口的唯一来源，及 Robot 是否仍间接参与 native source 解析。

**必须做：**明确 Robot 只给版本化 recipe、实体／Frame／Joint／传动与 Controller 能力；Task 给独立物体和组合意图；provider composer 解析 source 并返回实际映射。引用、替换、独立装入、空 Task 场景的组合合同继续有效。native body／actuator 的实际对应由 provider readback 校验，不能只对声明自身做相等比较。

**验收：**一体和装配 Panda 正式配置均走同一组合请求；自由 cube 保留且 reset 正确；arm／hand 不重复导入、绑定或施力；支持范围不外推任意装配树。

- [ ] SUBJ-02：Robot recipe、Task intent、provider materialization 的边界和实际 caller 对齐。

### SUBJ-03：单层、嵌套及根约束需要统一表达，不按动作类型代替主体类别

**保全＋待核／P1。位置：**`artifacts/logical_assembly.py`、`assembly/logical_source.py:project_logical_assembly_source`、`runtime/sessions/physical_control.py:ControlledSubjectV1`、Robot declarations。

**需要避免的误区：**“Position 环境”和“非 Position 环境”只是历史控制路径称呼，不应成为环境种类。主体根可固定、自由或受约束；Controller 输出可位置／速度／effort；这两个维度独立。单层 Pendulum 是没有嵌套的同一机制，装配 Panda 是嵌套，不应为它们各写另一种环境建造规则。

**必须核对：**主体／叶子路径、root Frame、parent、fixed attachment、资源 writer 与真实 source 实体一一对应；不把 logical nesting 自动解释为已 materialize 的物理约束。当前未支持的自由主体 reset 等边界明确保留，不借优化宣称全能力。

- [ ] SUBJ-03：共同主体表达支持本次四种声明；合法限制、未实现交集与错误映射分别说明。

### CTRL-01：Controller 匹配同时涉及语义通道、Scene 资源和 native 映射

**确认／P0。位置：**`runtime/sessions/control.py:SelectedControllerBinding/ControllerSelectionMatchV1/_match_position_profiles/_match_physical_execution`；`selected_materialization.py:PositionRuntimeBuilder`；`isaac_physical.py`。

**实际出过的问题：**F06 的 native DOF `joint1…joint7` 曾被拿来与 Scene actuator `actuator1…actuator8` 比较，reset 在采图前失败。当前 dirty 修改已按 Scene control group 生成 writer 资源，不能把旧失败继续当作未修事实，但需要保住不同命名空间的分工。

**必须做：**明确三层映射：Controller 输入／输出具名通道 → Scene 资源所有权 → provider native Joint／DOF／actuator／tendon。共同匹配比较同一命名空间，native 映射由 adapter 核验。Panda 两指耦合不能假定两个独立 motor。`_match_physical_execution` 当前每 subject 一个 Controller、Position admission 的数量限制均须写清实际能力，不能从装配 Position 双 writer 外推任意多 writer。

**退出：**用小型纯合同覆盖 native joint 名与 Scene actuator 名不同的合法例，以及错误 native 映射／资源重叠拒绝；一条受影响真实路线。不能通过两边都读同一声明，宣称 native drive 已独立验证。

- [ ] CTRL-01：三层映射和能力限制清楚；不会靠放宽 gate 通过。

### CTRL-02：统一提交要统一 owner，不能抹去 Position／effort／wrench 的物理区别

**保全＋待核／P0。位置：**`controllers/canonical/{contracts,physical_commands,position_sequence,physical_sequence}.py`；`runtime/sessions/control_submission.py:SceneCommandContributionV1/SceneCommandIntervalV1/V2/submit_control_command`；`physical_control.py`；`leaf_control.py`。

**现状痛点：**同时存在普通 Position、双叶、physical batch、mixed、Task／caller COM 与序列等入口。已实现的场景 interval 是应保留的共同 owner，但各入口生成、预检、写入、步进和记录仍需按实际调用核对。仅有共同 receipt 名称不证明共同提交；独立 standalone leaf 兼容也不能机械删除。

**必须改／保留：**所有新正式 Env 入口消费同一场景提交 owner；typed lowerer 保留位置目标、广义力、BodyWrench 等单位和持续时间；资源互斥／显式求和、partial write fault、effect 去重保留。standalone leaf 先列真实 caller，作为兼容能力明确归属或迁移，不能悄悄加入另一套生产 Env 调度。

**验收：**最短单 writer、已支持双 writer、真实混合贡献按改动影响选择；一项冲突拒绝和一项部分失败锁存即可覆盖关键机制，不重跑所有历史片段排列。

- [ ] CTRL-02：实际提交与物理推进唯一；旧 typed 合同和兼容承诺保全。

### CTRL-03：默认恒等 Controller 的能力不能由 facade 名称推断

**确认＋保全／P1。位置：**`environment/protocols.py:DefaultCanonicalControllerMixin`；`controllers/canonical/default_identity.py:DefaultCanonicalController.bind/bind_many`；`physical_controller.py:DirectJointEffortControllerV1`；主体 `default_effort_controller`。

**现状：**默认对象初始未绑定，绑定已编译 source／writer／单位后复用 direct effort；嵌套返回多个 writer 交给 existing compositor。这是已经实现的有界能力，不应再次要求 Controller 校验某个 Python Robot 实例 token。它也不表示所有 native ctrl 都是 SI effort，或所有 Panda 手指都能任意独立施力。

**必须收口：**公开说明 canonical 通道、单位、限幅和传动约束；Robot 创建提供稳定默认对象，实际运行在 source binding 后可用。Task 显式 R1／R3 不被默认替换；恒等映射不等于零动作保持静止。禁止另加专门为了旧测试的“安全保护”而改变正常 action 语义。

- [ ] CTRL-03：四主体默认能力、绑定前后行为及真实受支持范围可查询；无重复过严 token 检查。

### CTRL-04：重力补偿与模型能力要保持解耦，不能再绑定 Task／provider 名称

**确认边界＋待核／P1。位置：**`controllers/canonical/{model,physical_controller,dynamic_mass_effort,mass_matrix_effort}.py`、`position_profile.py`；`runtime/sessions/{mujoco,mujoco_dynamics}.py`；重力补偿配置和指南。

**问题边界：**现有重力补偿并非没做；默认关闭，已有 MuJoCo CPU 一体 Panda 的限定能力。模型／单位／source 约束是必要的；如果 Controller 算法直接 import live SDK 或公共 Env 根据 Panda profile 决定补偿算法，则职责有问题。冻结初态质量矩阵的候选不应冒充任意构型通用模型。

**必须做：**Controller 声明 model requirement，Robot 提供本体信息，runtime adapter 提供与 source 绑定的实际模型能力；匹配成功才启用。补偿作为明确贡献参与同一次组合／限幅，不重复添加；关闭态原行为保留。仅在修改影响已有开启态时补最短真实验证，不把全 provider／装配树补偿开发新增为本次门。

- [ ] CTRL-04：模型需求与供给匹配清楚；默认关闭、已支持开启和不支持拒绝均保留。

### CTRL-05：外部 interval、Controller tick 与 physics substep 必须区分

**保全＋待核／P0。位置：**`control_submission.py`、`runtime/sessions/physical_sequence.py`、`controllers/canonical/{position_sequence,physical_sequence}.py`、provider interval 方法。

**风险机制：**同一末端增量 action 若每个子步重新接收，会把一次动作重复累计；持续外力若每子步叠加而非替换自有贡献，会重复施力；为容许 tick 更新直接移除 replay guard，又会接受旧 episode 命令。

**必须做：**文档和代码保持外部 step 接收 action 一次、Controller 按既有声明调度、provider 唯一推进。开环片段和 native implicit drive 不冒充通用闭环；依赖新状态的真正闭环必须有新鲜 publication。当前未纳入的通用闭环继续留后续，不为优化另建调度框架。

- [ ] CTRL-05：当前已支持调度的时间、保持／替换、幂等与故障语义没有被清理破坏。

## 9. Scene、source、Assembly 与 provider：逐路径诊断

### SRC-01：公共 Assembly compiler 中仍有具体 Task 与 Panda source 处理

**确认／P1。位置：**`assembly/compiler.py:_ensure_panda_ee_site:233`、`_empty_tabletop_with_panda_xml:292`、`_source_for_task:317`、`panda_entity_declaration:423`。

**具体事实：**公共 compiler 对 `empty-v1` 分支，按 `agent.uid == 'panda-v1'` 取 MJCF、设置 meshdir、补 ee site；另有冻结 Panda source 声明。这里既有合法资产 recipe，也有通用组装里对具体 UID 的知识。

**必须改：**把 Panda MJCF 补位／canonical Frame recipe 放 Robot 资产适配，空桌面声明放 scene builder；公共 compiler 只消费显式 source／attachment／mapping。不能为了没有字符串而用 UID 数字或反射隐藏同一分支；也不能把 XML 解析放回 Robot native constructor。

**验收：**Empty+Panda 原 caller 保持或迁移；其他单层主体无需改 compiler 即可声明；Frame／source 身份和原始 source 字节保持受控。

- [ ] SRC-01：公共编译职责与资产 recipe 分开，正式 caller 已迁。

### SRC-02：provider source composition 仍以 PickCube 专用协议命名和组织

**确认／P0。位置：**`runtime/sessions/source_composition_adapters.py` 的 `_PICKCUBE_SOURCE_ADAPTERS`、`compose_pickcube_robot_source`、`resolve_pickcube_robot_source_adapter`；`mujoco_composition.py:compose_pickcube_robot_source:432`；Task `selected_binding`。

**为什么不是简单改名：**即使实现位于 runtime，若其输入仍要求某任务的既定 Robot 替换／实体布局，公共组装能力仍不能由别的 Task 直接消费。单元 4 曾按明确任务交集提供适配是有效成果；优化现在需要把“通用 source 组合请求”和“PickCube 提供的任务映射”拆开，而不是宣称旧函数已经任意通用。

**必须做：**复用 `assembly/source_composition.py` 的 Intent／Request／Receipt：Task 提供自身实体及需引用／替换的子树，Robot 给 recipe，provider composer 处理相应 source 格式。注册按表示／provider／能力，不按任务名；固定 Panda recipe 可以仍是受限实现，但限制由 recipe／能力声明表达。不能删 source closure／最终模型映射检查。

**验收：**PickCube 自由方块、空 Task／无独立物体声明和现有 Robot 选择都能进入同一请求合同；已支持的真实路线能物化；不具备 adapter 的格子在作用发生前明确拒绝。

- [ ] SRC-02：共用组合合同被真实调用，Task 专用值不由 provider 反推。

### SRC-03：固定附件生产模块内包含 R06b 顺序实验配方

**确认／P1。位置：**`assembly/fixed_attachment.py:_reverse_recipe_children/_apply_r06b_order_recipe/derive_r06b_order_sources/validate_r06b_order_sources`，及 `runtime/sessions/api.py` 固定 Panda source 预检。

**问题边界：**固定连接的真实约束、原生名称校验属于生产能力；“为了证明 source 顺序差异而翻转某两个冻结源”的配方属于实验。当前两者在同一主模块，需要按真实 caller 拆开，不是删掉所有 attachment 校验。

**必须做：**实验变体生成由 diagnostics 外部驱动；生产 lowerer 消费已声明的 attachment／source recipe。若某冻结 recipe 已成为正式支持资产变体，则改由版本化资产 recipe 拥有并解释其产品用途，不再靠实验名获取隐藏权力。

- [ ] SRC-03：每个 R／F 实验 helper 有实际归属；固定连接的真实验证和旧 codec 保全。

### SRC-04：RuntimeSource／UsdRuntimeSource 是表示差异，不是多 Runtime 的借口

**确认＋保全／P0。位置：**`runtime/sessions/source.py:RuntimeSource/UsdRuntimeSourceV1/UsdRuntimeInputV1`；`assembly/source.py:UsdTaskSceneSourceV1/UsdSnapshotLeaseV1`；`assembly/usd_delivery.py`。

**已出现的问题：**曾把 MuJoCo renderer-only 对 RuntimeSource 的约束加到所有 task RGB，导致 USD 原生相机被拒绝。不同 source 类型本身合理；错误在公共状态层擅自用某个 renderer 的格式限制其他 adapter。

**必须做：**source owner 负责不可变原始输入、closure、representation、Scene 和 Artifact 关联；provider／renderer 各自声明可消费格式及实际转换。公共 Runtime 不应要求 USD 假装 MJCF。兼容 `.xml` 属性若只为旧 provenance 提供原始文本，限定 caller 和含义，不能把它当作 USD live 表示或重复解析授权。

**验收：**MJCF 与 USD 两种受支持输入能到正确 adapter；错／过期来源仍拒绝；source snapshot 自有、关闭可追踪，原资产不修改。

- [ ] SRC-04：source 表示分层和不可变来源保证未被“统一”抹平。

### RUN-01：公共 Runtime API 内集中了大量历史精确准入与诊断 context

**确认／P0。位置：**`runtime/sessions/api.py` 约 1,759 行；F04／F05／DG02／DG04／F06 常量和 `_validate_*`；`_F05Dg04S1NativeIOContext`；materialization factories。

**具体问题：**公共协议、通用 factory、冻结某家 Panda 资产的 manifest／checker SHA、source variants、试验 context 和 native factory 分派集中在一起。新增资产需修改共享 API，读者难以区分“这家 adapter 的真实能力限制”和“这轮实验的许可”。

**必须分三类处理：**① RuntimeSession 公共操作与 optional capability 留协议；② 正式 provider／representation 准入归其 adapter admission owner，并保留精确约束；③ 注入诊断 factory／实验 authority 归外部 wrapper 或 scoped test injection。不能把所有 hash 删除，也不能把整个 api.py 搬成一个名叫 admission 的大文件就交差。

**验收：**公共 facade 无具体实验调度；旧 F06／历史资格仍严格按其 profile 验证；新资产通过正常 provider 能力接入，不冒用历史资格。

- [ ] RUN-01：协议、正式准入和实验注入逐段归位，实际运行仍走唯一 Runtime。

### RUN-02：旧 GeoPhys bootstrap／RuntimeBoundary 有活动调用者，迁移必须有范围

**确认／P1。位置：**`runtime/bootstrap.py:bootstrap_task_runtime` 直接使用 `geophys.demo_runtime/test_runtime`；`runtime/boundary.py:GeoPhysRuntimeBoundary`；component Env 与 `vectorization/factory.py`。

**为什么不能只删：**两简单任务的 selected 共同链已接三 provider，不代表 component／batch 构建调用者已接同一 native capability。旧 boundary 是有实际用途的适配，不能因为名字不同否定所有历史成果。反之，也不能让它继续拥有与新 selected 并行的隐式任务／Controller 语义。

**必须做：**列 caller：正式 scalar、`build_runtime=False`、旧组件示例、batch、回放。正式标量优先共同契约，旧 boundary 作为已有 provider adapter／兼容能力保留，明确不支持选项。G06 批量实现仍归 G06，但优化不能破坏其纯构建入口或假称 batch 已迁移。

- [ ] RUN-02：caller 清单、公共合同映射和迁移／兼容界限完成，无隐藏 fallback。

### RUN-03：provider adapter 应承担 SDK 映射，不承担另一套 Task／Controller

**确认结构＋待核细节／P0。位置：**`sessions/{mujoco,geophys,isaac_native_io,isaac_physical,native_io}.py`；`runtime/sessions/physical_control.py`；原生 source readback。

**必须核查的实际动作：**load source → native 名称／关节／actuator 映射 → reset → 写入 typed target／effort → 物理 interval → snapshot → close。provider 可以有不同 API 和 native implicit drive，但不能在 adapter 内再计算 Task 奖励、运行第二 Controller 或修改外部 control_dt。

**既有经验：**单元 5 曾记录 Isaac setter/sync/manager 计数边界差异；启动前 unknown 与显式子步必须分开。不能为数值对齐直接把计数除二或修改公开时间。现有已解的适配问题按最终影响保全，不以本文重新展开全部 native 排查。

**验收：**每家至少一个实际正式 caller；公开状态、单位、方向、有效时间与唯一推进有可信证据。多 provider 无需轨迹逐点相等；`requested_ctrl`／`applied_ctrl` 不称为实测力。

- [ ] RUN-03：provider 只实现其边界职责，旧时钟／力语义不被优化削弱。

### RUN-04：进程与资源控制应统一使用既有 worker，不由 Task／诊断复制

**确认＋保全／P1。位置：**`sessions/transport.py:start_selected_worker/RemoteSession`、`worker.py:main/_exit_after_isaac_cleanup`、`provenance.py`；各轮 workspace runner。

**问题：**历史 runner 各自复制环境变量、解释器、缓存、锁、timeout 和 shutdown 逻辑，容易出现与生产 worker 不同的行为。Task candidate 又可能提前 open App，native worker 内再次取得 owner。不同 cwd／只读缓存／进程 namespace 曾干扰 Isaac 对照；这不是证明唯一根因。

**必须做：**Task 只声明执行需求；环境准备、native SDK 加载和 App lease 由既有 runtime／worker owner。外部 runner 只负责授权预算、监控和取证，不复制物理／渲染操作。保留 `_exit_after_isaac_cleanup` 仅在清理确认后的隔离进程退出含义，不能以强制退出冒充 App 正常 close。

**验收：**解释器、路径、cwd、cache、资源 scope 与生产调用一致或明确记录差异；主进程不因配置查询初始化 SDK；关闭／超时只处理自有进程和锁。

- [ ] RUN-04：生产 worker 和诊断 runner 分工明确；没有为单个任务再造 worker。

## 10. renderer、相机与 observation：逐路径诊断

### REN-01：普通 render registry 与 task RGB registry 不是同一张能力图

**确认／P0。位置：**`render/base/backend.py:_BACKEND_REGISTRATIONS`、`render/tools/backend_registry.py`、`render/providers/single.py`、`render/camera/api.py`、`render/camera/task_rgb.py`、Env 的 `_TASK_RGB_PAIRS`。

**具体痛点：**窗口／普通 render 走 backend registry；task RGB 又按 renderer 字符串和固定 profile 创建 borrowed 或独立 session；Env 持有 pair 白名单、颜色描述和 App 设置。相同名称在不同 API 的支持范围并不相同。仅给 `available_render_backends()` 加一个名称不会接通 task image，反过来 task RGB 成功也不证明 human 窗口。

**必须改：**在现有 renderer registry／capability owner 建立可查询的显示、离屏、task sampling、source／state、设备与输出能力，并给出构建 factory。可以保留不同产品接口，但能力来源和实际 adapter 不重复维护。绑定能力未知时明确拒绝，不创建全新 RenderManager 或静默切 renderer。

- [ ] REN-01：用户能查询实际合法组合；增加 adapter 主要修改其 owner，不修改每个 Task／Env。

### REN-02：把 renderer 分支挪到 helper 尚不足以完成可组合适配

**确认／P0。位置：**`render/camera/task_rgb.py:create_task_rgb_consumer`；`camera/api.py:prepare_task_rgb_render_source`；`reference_env._configure_task_rgb`。

**现在代码：**GeoPhys／Isaac 选择 borrowed RuntimeSession camera，MuJoCo 创建独立 visual session；helper 中直接识别三种名字并拼 `RendererSelectionV1` 和 physics profile；Env 仍识别 Isaac 设置、GeoPhys framebuffer 限制及颜色说明。

**为何是未完项：**borrowed 与 independent 两种实现方式合理；未收敛的是注册／能力／构造知识仍散在多处，公共入口仍知道每家限制。只移动同样的 if 没有减少要同步修改的位置。

**必须改：**相应 adapter 提供状态需求、visual source 准备、session／camera 创建、输出描述、借用所有权及失败清理。公共 Env 只按结果组合 observation 和生命周期。复用既有 camera session 和 provider，不建立一套平行渲染框架。

**验收：**一条 borrowed native 与一条 independent cross 真实纵切；错格式在对应 adapter 拒绝；公共 Env 无具体 RTX／rasterizer 设置。其余按影响复用。

- [ ] REN-02：适配知识由单一 renderer owner 提供，helper 不只是隐藏旧分支。

### REN-03：公共状态不应为 RGB 再变成 Position 专属状态路线

**确认＋保全／P0。位置：**`reference_env._prepare_task_rgb_state_binding:1579`、`_publish_task_rgb_typed_state:1628`、`_capture_task_rgb_boundary:2590`；`runtime/sessions/source.py` 的具名绑定函数；`observations/capture.py`。

**现状：**近期已把 renderer 独立 projection 与 Controller publication 分离，避免覆盖控制状态，属于应保全修复。但 Env 仍从 source 枚举 Joint／Frame 并持有 renderer requirements，函数沿用 position 命名；是否真实依赖 Position 需要看内容和 caller，不能单凭名称否决。

**必须做：**公共状态 owner 发布同一 session boundary／clock 下可供消费者查询的具名状态；Controller、Task、renderer 分别声明需求。renderer-specific visual projection 由 adapter；公共层不得为 MuJoCo visual source 限制 Isaac USD，也不得为渲染偷偷推进物理。允许不同 typed view，但需有明确关系和 lifetime。

**验收：**非 Position 受支持主体能获得 task RGB；渲染前后控制 publication、物理时钟与 episode 不变；错／旧状态拒绝。不能仅以图像 shape 相同或 boundary dict 相等替代实际采集绑定。

- [ ] REN-03：状态 owner、需求和 projection 分工闭合，RGB 无控制类型依赖。

### REN-04：Isaac task sensor 与 observer 共用实现，但不得共用错误身份／生命周期

**确认＋运行问题待最终主审／P0。位置：**`isaac_native_io.py:bind_task_camera:2952`、`task_camera_binding:2992`、`capture_task_camera:3053`、`_capture_observer_admitted:3093`、`_close_task_camera_sensor`、App owner。

**已经可定位的复杂性：**task camera 有独立 prim、光学读回和 sensor 路线，但采集函数复用 observer 采集主体，依赖 `_observer_render_request`，部分失败共用 `_observer_faulted`。共用底层工具合理；“task camera 必须假装存在 observer 才能采图”不是合理的用户合同。

**旧成功对照能说明什么：**旧 `isaac-motion-002` 曾用公开 Env、独立 task sensor、同步预热／采样取得图像。旧物理时间 0.036s 与 Timeline 约 0.033333s 不完全相等却取得 reference 0.036s；因此不能把 timeline 数值严格相等自行新增为唯一门。新的 `isaac-020` 对齐 timeline 后无图，也不能宣称旧方案已证伪。sensor、camera prim、render product、dispatcher reference、App profile、可写缓存和更新顺序需要在 adapter 内分别对齐。

**必须做：**task 与 observer 各有可追踪身份／资源，复用 App lease 和采集工具；headless task RGB 不要求可见 observer 窗口。同步等待以当前物理状态和采集完成证明为依据，warmup 有界且不推进任务物理。失败清理只释放自有对象，不能返回旧 completion。

**验收：**最终身份公开 reset 首帧、最短非零 step 图像、再次 reset 旧帧失效、close；实际 camera／reference／clock 与物理无额外推进。不得重新设任意图像评分门，也不要求重跑历史 2,140 次 dispatcher 作为固定配方。

- [ ] REN-04：真实 Isaac task RGB 及其正确 adapter 生命周期通过；仅“gate 全 true”不足以签收。

### REN-05：MuJoCo renderer-only 与 GeoPhys camera 的 source／光学／灯光边界

**确认＋保全／P1。位置：**`render/camera/mujoco.py:MuJoCoDynamicCameraSession`、`camera/source.py` 的 DynamicCameraRenderSourceV1/V2 与 project_render_state；`sessions/geophys.py:_observer_mjcf_light_declaration/bind_task_camera`；`observations/capture.py:CameraObservationProvider._bind_and_read_task_camera`。

**必须保住的问题修复：**独立 MuJoCo visual model 只消费公开状态、同步运动学，不 step 第二物理；GeoPhys 曾漏设 FOV／near／far，曾把 PickCube 特定 top/headlight 结构当所有任务前置，后续有受测修复。原始图像存在并不证明声明的光学／灯光生效。

**必须做：**由 source 声明 visual／灯光表示，adapter 处理其可支持子集；native camera 参数实际设置并可读回；不支持 authored/default lighting 的情形明确拒绝，不能静默用太阳光。原 source 资产不因优化修改。修复范围以最终代码对照，不重新研发光照完整系统。

**验收：**受影响相机光学一项真实读回；cross 独立状态映射及无额外物理；已有灯位微小误差的有界认可保留，不提升为任意灯光支持。

- [ ] REN-05：真实光学／visual 映射和支持限制由 adapter 负责，旧修复保全。

### REN-06：窗口、离屏 RGB、任务图像必须独立，但不必复制三套相机逻辑

**确认＋待核／P1。位置：**`reference_env._capture_selected_observer/bind_visual_state`；`render/providers/single.py` frame-capture 路线和 visualizer 路线；`render/tools/camera.py:InteractiveCameraController`。

**具体痛点：**provider 包装有公开 API，也直接访问 visualizer 的 `_initial_camera_pose`、`_refresh_render_snapshot`、`_render_frame_to_buffer` 等内部方法；task camera／observer 又在其他模块各自组装姿态和输出。这里是 Core 内部接口稳定性问题，不能不经核对就称为偷读 provider-private solver。

**必须做：**把相机运动、状态消费、帧采集、窗口呈现分开为已存在 owner 的清楚接口；观察相机 A→B 不改变 task camera。真实关窗后按既有合同继续采集或发布 typed fault，不能误关 physics App。未实现的 Pendulum／双轮 human 窗口原有明确拒绝保留，不擅自新增必达窗口矩阵。

- [ ] REN-06：展示与采集分工明确；受影响窗口关闭／独立性有最小证据，无鼠标强制门。

### REN-07：颜色、设备、ownership 描述不能散落成未经验证的默认事实

**确认／P1。位置：**`reference_env._configure_task_rgb` 的 color 字符串和 Isaac 设置；`render/camera/color.py`；`canonical_camera/images.py`；renderer completion／metadata。

**问题：**同一 RGB float32 的数值范围不等于相同色域／传递函数；native 只限某配置的颜色验证不能被用户端一般化。不同位置维护文字描述和真正检查，容易出现“元数据声称 A、设置实际 B”。

**必须做：**adapter 返回与实际设置绑定的输出规格：layout／dtype／range、transfer function、未校准限制、CPU copy／device、owned／borrowed lifetime。公共 observation 只组合，不自行推断颜色语义。保留已披露原色／素材色域未校准限制，不为优化扩成色彩科学项目。

- [ ] REN-07：输出契约来自实际 adapter；旧正确限制和已返回帧的 ownership 保持。

### REN-08：通用相机交互数学直接依赖 Taichi 输入常量

**确认／P2。位置：**`render/tools/camera.py:20` 顶层 `import taichi as ti`；`InteractiveCameraController` 内直接使用 `ti.ui.CTRL/RMB/LMB`。

**具体问题：**相机 yaw／pitch／pan／pose 运算是可复用的；具体窗口输入常量属于某个输入适配。当前工具把两者绑定，其他 renderer 使用相机运动逻辑时也会带入 Taichi 依赖。这里只确认 import 依赖，不宣称 import 就初始化了 GPU。

**必须做：**复用现有相机运动类，把具体按键／窗口事件翻译留给对应 UI/input adapter；通用运动接受明确事件或数值，不为每家引擎复制数学。若现有惰性边界足够且无跨renderer调用，可按真实caller解释保留；不能为了清掉import再造一层无用途的事件总线。

- [ ] REN-08：通用运动与具体输入依赖有明确分工，纯相机配置不必加载无关SDK。

### OBS-01：名为 selected-reference 的公共投影仍以 Panda／PickCube 为默认

**确认／P0。位置：**`observations/selected_reference.py:selected_reference_observation_spaces:25` 默认 ee_pose、9 关节和 hand_pose；装配分支硬编码 `panda-arm/panda-hand`；`build_selected_observation` 有 F04／F05／F06、`pickcube-state-only-switch-v1` 和 cube key。

**问题机制：**这些作为特定 reference task 的兼容 projection 有真实用途；作为通用 observation 工厂就会要求非机械臂补 Panda 字段，并使 renderer 跟随 Position 分支。新任务只想添加状态和相机，却必须理解整个参考任务历史。

**必须改：**公共组合器消费 Robot／Task／sensor 的空间与构造函数；Panda／PickCube reference projection 作为显式被选中的实现，归相应 owner；旧 schema／alias 不悄悄改变。task success／Solution completion／runtime validity 分开，不在通用层按诊断 profile 判断语义。

- [ ] OBS-01：通用组合不预设 Panda；兼容投影明示且 caller 受控。

### OBS-02：多种相机配置／schema 需要一处规范化，不凭空宣布全部统一

**确认／P1。位置：**`environment/config.py:CameraSpec`、`observations/canonical_camera/{geometry,consumer,contracts}.py`、`observations/capture.py` 三类 consumer、`observations/camera.py`。

**具体风险：**历史 component CameraSpec、canonical CameraGeometry、CameraObservationConfig 与 task RGB 参数形状不同；metadata 按声明计算而 native 未实际设置的问题已经发生过。近期重构的 schema key 修复说明 space／schema／实际输出必须共同核对。

**必须做：**普通声明统一规范化到既有相机合同；高级旧对象保留 decoder／兼容适配。单一 owner 决定相机分辨率、内外参、mount、输出字段和输出空间；不同消费者共享结果，不能各算一套。保留现阶段世界挂载限制，不把手部动态挂载自动写为已通过。

**验收：**一个正式声明走到底；实际 observation 被固定 schema 正确验证；native 读回和返回 geometry 一致；其他旧表示明确迁移／支持边界。

- [ ] OBS-02：相机声明、实际绑定、schema 和返回值闭合。

## 11. Recorder、轨迹和外部调用者：逐路径诊断

### REC-01：通用 H5 模块混入精确诊断实验的物理拓扑和样本数

**确认／P1。位置：**`recorders/h5.py:_validate_f06_typed_state_witness`、`_f05_typed_state_extension`、`_load_attached_leaf_control_records_h5:1307`；`recorders/position_metadata.py`。

**具体可见问题：**attached-leaf reader 要求恰好 64 transitions、65 observations、特定 E1～E4、MuJoCo 3.8.1／固定 timebase、固定 `panda-arm`／`panda-hand` writer 和 native 名称；F06 witness 要求九关节和 ee。历史实验 reader 严格限定自己读哪种数据是合理的；把这些限制直接当通用记录能力就会阻碍正常任意 horizon／Robot／writer。

**必须做：**通用 Recorder／reader 按 versioned schema 和数据携带的 source／binding／timebase 验证完整性；精确 R03c／F06 实验 oracle 作为外部 Judge 或专门兼容 reader 注册，明确它只解释旧格式。不删除旧格式解码，也不让普通任务必须伪装成这些固定样本。

**验收：**新正常记录的边界数量、状态、动作、图像与同次实际运行一致；一份仍需支持的旧格式可读或给出明确保留入口；旧实验严格 reader 不被放宽成伪通过。完整 Solution 使用正常 Recorder，不能用 receipt 适配掩盖生产快照问题。

- [ ] REC-01：通用格式与历史 oracle 分层，普通运行不受固定实验样本数支配。

### REC-02：静态 provenance 复用已有改进，避免每步文件 I/O 回流

**确认已有改进＋待核热点／P2。位置：**`recorders/reference_provenance.py:selected_source_provenance/callable_source_snapshots/coordinator_receipt`；`reference_env._owners:4893/_source_xml_sha256:2488`；`artifacts/contracts.py:identity_hash`。

**重要更正：**旧阶段 3 前审计说 `_owners` 每步读源码、边界每步 hash XML；当前代码已经有 episode provenance 准备和 XML snapshot cache。不能复制旧报告，要求重新修已经改好的问题。部分 Artifact identity 也已用 `_artifact_identity`；其他 hash property 仍可能序列化，但未测量开销，不能直接宣称它们是性能瓶颈。

**必须做：**不变源码／source closure／recipe 摘要在正确 owner 和 lifetime 准备一次；动态 boundary／命令／状态 identity 仍随实际数据生成。仅在当前调用链确有重复时优化；不得跨 source 修改、reset、Controller generation 盲目缓存，也不得为了速度移除身份。

- [ ] REC-02：已修热点不回退；确有新热点才作最小测量与修复，无无依据性能重构。

### REC-03：回放／重新执行与正常新运行的身份策略必须区别

**确认＋保全／P1。位置：**`trajectory/reference_replay.py:reexecute_selected`；`trajectory/replay.py`；`environment/_historical.py`。

**现状：**selected re-execution 明确只支持两任务及特定记录 schema，严格比较 source／adapter／coordinator 身份；v1／v3 structured execution 某些路径明确拒绝。原旧审计提到的 Core 反向 import diagnostics，当前所查 replay 路径不应无依据继续标作现存事实。

**问题：**正常新运行若复用旧 replay 资格，就会因源码变化被卡；反过来，优化后删 identity 比较又会让历史数据被错误解释成新能力。新的路径迁移也可能使硬编码 factory/import 失效。

**必须做：**正常构建使用当前声明和真实能力；历史 replay 按记录版本解释旧身份，不替换旧 SHA。保留 thin compatibility factory／明确迁移，或明确标“不支持跨源码重执行”；不能为读旧文件启动不同 physics owner。只读 H5 inspect 与重新执行分开，后者有 native 授权才运行。

- [ ] REC-03：旧记录读取、历史重执行和当前任务运行不混为同一资格。

### CALL-01：CLI／教程／示例仍可能把复杂候选入口教给用户

**待核／P1。位置：**`task_env/script/env/_common.py:public_config/run_single/run_parallel`、`script/environment.py`、camera／trajectory 脚本、`task_env/doc/`、仓库 `examples/` 及 benchmark caller。

**必须逐条核对：**用户如何选择 Task UID、Robot、Controller、physics、renderer；有没有要求手工调用 Task 内 builder、准备 hash 或设置 workspace；CLI 是否继续使用过时同名配置；示例 import 是否会初始化 SDK；render／Solution 操作是否真的走正式 make_env。

**必须改：**主教程给一个真实可运行的正式配置；修改配置即可选择已支持组合；高级候选／诊断示例放专门入口并显式标识。删除无用包装，保留真实兼容 export；不能增加第二套简化 SDK。

- [ ] CALL-01：普通用户示例和正式代码一致，不把实验驱动当 API 入门。

### CALL-02：vector／learner／LIBERO 等不能被标量整理顺手破坏

**确认有边界＋待核调用者／P1。位置：**`vectorization/factory.py:make_framework_parallel_spec` 用 `build_runtime=False`；`homogeneous.py`、`parallel.py`、`task_definition.py:BatchTaskLifecycleAdapter`；`alg/agent_factory.py` 等 observation／action consumers；仓库 benchmark／LIBERO 接线。

**问题边界：**G06 尚未完成，本轮不实现 batch physics 或训练，也不声称 144 个算法文件都存在缺陷。必须保住的是纯构建、固定 action／obs space、自动 reset、terminal observation 和 renderer ownership 的已有合同。若优化把所有构建都强制立即启动单环境 Runtime，会破坏旧并行 factory。

**必须做：**列直接 caller 及它消费的 config、space、snapshot、env/row/episode 信息；迁移正式标量 API 时给清楚适配。未迁 batch 保留路径且明确限制；不通过 batch 入口偷偷回退单环境或 CPU。未来 G06 的并行契约按共同主体／命令／状态边界扩展。

- [ ] CALL-02：最小 import／构建／space 兼容核查通过，未实现并行如实标注；无需完整训练回归。

### CALL-03：objects／planners／reporter／utils 按职责保留，不为凑“全面重构”制造抽象

**待核／P2。位置：**`objects/` 的 TaskObject 声明；`planners/{contracts,references,cartesian,joint,completion}.py`；`reporter/`；`utils/_paths.py` 和配置辅助；`task_env/__init__.py`。

**核查边界：**普通物体无需伪装为 Robot；Task 外力应通过共同 typed 贡献作用。Planner 负责目标／Solution 支持，不直接拥有 physics step。Reporter 负责结果呈现，不重定义 success。路径配置可以解析真实依赖根，不能默认要求某个临时 run 目录。

**必须做：**只处理实际反向依赖、重复 policy 或旧入口调用，若不存在则以调用者核对结案；不拆分每个短 helper，也不把 Robot 的私有细节变成公共 utils。公开 import 保持惰性，无关 learner import 不加载 native。

- [ ] CALL-03：这些模块有明确检查结果；不存在问题时原样保留并说明，无凭空新增 owner。

### CALL-04：LIBERO benchmark 的来源语义不能被主任务整理误覆盖

**待核／P1。位置：**`bench_deploy/libero/environment/selected_reference.py`、`controllers/{osc,source_gravity}.py`、`trajectory/{worker,reader}.py`、`asset/benchmarks/libero/` source bundle。

**问题边界：**LIBERO 有自己的任务谓词、原始源、OSC／gripper cadence 和回放语义，不应该为了“全部统一”改成 PickCube R1 或Panda默认控制。相反，其对Core的构造／Runtime／Recorder依赖若受本轮改动，不能不查caller就声称兼容。

**必须做：**列直接消费的Core符号，确认source、Control／Frame单位、controller cadence和结果读取未受破坏；共享的真正Core机制通过同一合同，benchmark专有语义保留在bench owner。未受影响时用调用／diff核对结案，不重跑全部A123和外部资产流程。

- [ ] CALL-04：代表caller的兼容边界明确，未把benchmark特定语义搬入公共TaskEnv。

## 12. 诊断、测试与证据组织：逐路径诊断

### TEST-01：旧测试文件不是纯度／授权范围的可靠边界

**确认／P0。位置：**`diagnostics/tasks/test_phase_ii_c02b_position_profile.py` 的 `_candidate`／fixture 和多个合同测试；`test_v211_task_rgb.py`、`test_v211_task_rgb_source_routing.py`；历史未预约物理和误选 RGB 测试记录。

**具体问题：**同一个“合同测试模块”可能既有纯合成，也会通过 fixture 解析真实 source、构建物理或启动相机。只运行整个文件、只按测试名判断零步，曾导致未预约子步或未授权路径。结果是开发者为了测试基础修复又启动昂贵矩阵。

**必须做：**将纯合同、真实 source 检查、native CPU、Isaac/GPU、窗口实验在既有 diagnostics 下明确分类／标记；为本次改动冻结具体 test node。纯检查有 SDK／资产访问守卫；native 检查事前估算物理和输出。测试组织改动不等于要补一套巨大新框架。

**验收：**常用快速检查能直接运行且不碰引擎／资产；native 路线必须显式选择。旧模块可保留兼容收集或拆分，但不再被工作包当成“全部纯测试”。

- [ ] TEST-01：测试分层、最小命令与授权边界明确，无意外矩阵运行。

### TEST-02：测试不能把旧候选布局定义为新架构的正确性

**确认机制／P0。位置：**各 `test_phase_ii_*`、冻结候选 driver、手工构造 Env／profile 的 fixtures，以及新的 task RGB／Controller tests。

**问题机制：**旧测试可以证明旧 schema／映射／故障语义。但若它要求特定私有字段、固定 method patch、特殊 Task UID，实施者为让测试通过把它们重新加回公共代码，架构就被测试反向绑架。也不能反过来把所有旧测试删掉，使真实功能退化不可见。

**必须做：**逐项写测试的真实 claim：用户行为、公共合同、旧格式兼容、实验 oracle、实现细节。前四类按实际需要保留／迁移；无产品意义的实现细节测试改为当前 owner 的行为检查。禁止为了 fixture 缺字段把测试专用 fallback 加生产；真实必要字段就修 fixture 或正式兼容 decoder。

- [ ] TEST-02：每个本次保留的核心测试有 claim／owner；没有“旧模块全绿所以新架构完成”的结论。

### TEST-03：生产诊断探针应归位，但正式证据接口不应一起删除

**确认＋待核／P1。位置：**`runtime/sessions/api.py` 诊断 context；`assembly/fixed_attachment.py` 顺序配方；`sessions/mujoco.py:apply_fixed_attachment_diagnostic_control`；`recorders/h5.py` 精确 oracle；各 `_g05_*`、`_f05_*`、`_diagnostic_*` helper 的真实 caller。

**必须分类，不能搜索替换：**

| 类别 | 去向 |
| --- | --- |
| 只为某次实验注入 factory、反转 source、包装计数、输出比对 | diagnostics／外部 runner／scoped test injection |
| 可正式查询的模型 readback、source／时间／fault／ownership | 保留在其真实生产 capability owner |
| 受限但正式支持的 profile admission | provider／source admission，明确限制 |
| 历史入口仍有 caller | 薄兼容入口或有明确迁移的受控实现 |

**验收：**每个本次触及的探针有分类、caller 和去向；Core 不 import diagnostics／tests，不按实验名改变默认行为；删除后仍能通过公开结果定位真实错误。

- [ ] TEST-03：实际越权实现完成迁移，不只留一张未来清理清单。

### TEST-04：测试和报告必须能复核，文件数量不代表证据强度

**确认历史问题／P1。位置：**旧包被覆盖 10 文件、未保留原始输出的 119 passed／38 failed、各轮 manifest／receipt 适配与 worker JSON、当前新输出目录。

**问题：**清单校验 5,674 文件只说明这些字节存在，不证明采样／task-success 正确；同次 worker JSON 的“独立 reader”是独立算法读取，不是第二次独立物理测量。源码提交后若公共 reset 又变，更早运行不能自动标为最终 HEAD 实测。

**必须做：**最终证据最少包含真实输入身份、命令、原始日志／H5／图像中支持 claim 的部分、独立读回、有效计数及 close；说明哪些是直接观测、推算上界或 unknown。每次运行新目录，writer 不覆盖已引用包。不复制大量无关文件来放大 manifest 数量。

**验收：**另一人从最终一份 stage 包能直接复算主要结论，不必猜哪个 attempt 才有效；保留集按第 15 节裁剪，不强制保留所有历史失败。

- [ ] TEST-04：证据最小充分、可独立复核，报告与最终实际身份一致。

## 13. 文档、导航与规范治理：逐路径诊断

### DOC-01：当前能力、历史决定与拟议方案必须分栏

**确认／P1。位置：**第 4 节 GOV-03／04 所列文档，加 `capabilities/README.md`、`planning/protocol-implementation-map.md`、`maintenance/recovery.md`。

**必须更新的具体内容：**正式 Task UID／配置；四主体共同链；单元 4／5／6 精确接收范围；单元 7／8／9 实际进度；固定 renderer；当前支持 source／provider／camera；默认 Controller 限制；COM 旧失败与有界采纳；R05c NOT_REQUALIFIED；优化新停门。

**不能这样做：**仅在旧“尚未接收”段落后再加一个“目前已完成”；把所有历史页都改成最新时态；把设计表全部改写成已支持；把 protected 文件 hash 问题修成“校验通过”。

- [ ] DOC-01：版本 README → 当前摘要 → API／能力／本台账可单向恢复，且与源码一致。

### DOC-02：开发规范与 Skills 必须反映已经落实的 owner

**确认需要同步／P1。位置：**根 `AGENTS.md`、`.agents/skills/geochora*`、`task_env/.agents/skills/`；全局 ownership／architecture；`task_env/doc/` 和用户工作文档入口。

**问题：**根 AGENTS 仍将更广诊断收口指向 v2.1.1 integration；旧目标和新停门不同。Skill 若只重复旧 candidate 路线，会让下一 agent 再次恢复旧布局。反之，只改 Skill 而代码未迁，也不能宣称能力完成。

**必须做：**代码稳定后核对真实 owner、公共 API、调用者、失败语义及测试命令，更新可发现 Skill 和导航。把“任务目录不复制生命周期”“新 backend 不新建 Task Env”“一阶段一主题分支”“最小受影响测试”写成可执行约束。文档层目录瘦身与删除历史内容分开处理。

- [ ] DOC-02：Skills／AGENTS／示例与最终源码一致，链接和文档检查有实际结果。

## 14. 核心测试与最终验收：不用矩阵定义架构

### 14.1 三层证据各回答一个问题

| 层 | 核心检查 | 不能宣称的结论 |
| --- | --- | --- |
| A. 静态调用与纯合同 | 正式配置、owner、单位／资源映射、状态／错误边界、兼容解码 | 不能代表引擎／真实图像已通过 |
| B. 最短生产纵切 | 正式 make_env → reset → 非零 step → state/clock → 二次 reset → close；必要同步 RGB | 不能代表完整任务成功或任意支持矩阵 |
| C. 完整 Solution | 正式任务从头运行到完成／终止、任务成功／completion 分列、同次记录读回 | 不转移历史 Qualification，不等于原 G07 最终九格已完成 |

### 14.2 受影响才执行的核心清单

| 编号 | 必须证明的能力 | 最小选择与复用规则 |
| --- | --- | --- |
| V01 | 一个真正正式的 Task 配置入口 | 一个 YAML 和等价 mapping；所支持 physics／renderer 是配置选择，不更换 Task 业务类 |
| V02 | 四主体共同生产链 | 一体 Panda、装配 Panda、Pendulum、双轮车各最短纵切；若仅改某 adapter，未受影响主体可用精确旧证据与调用链关联 |
| V03 | Controller／资源组合 | 已支持 Position／effort 区别；装配双 writer；若改共同提交，最短混合贡献和一个冲突／fault 例；不遍历全部组合 |
| V04 | renderer 无控制类型依赖 | borrowed 原生与 independent cross；覆盖真实相机、公开状态、boundary／clock；非 Position 已支持路线按影响补最短例 |
| V05 | G05 首批原生与至少一个 cross | MuJoCo、明确命名的 GeoPhys、Isaac 及 GeoPhys physics × MuJoCo renderer 的证据逐项对应；5b 窗口旧证据不因无关整理全部重跑 |
| V06 | 同步 task RGB 生命周期 | reset 首帧、一个新状态、二次 reset／旧帧无效、重复 render 不 step、close；重点检查本次变化的 owner |
| V07 | 关键错误与旧入口 | 错来源／资源冲突／副作用后失败取与变更对应的少量例；旧 UID／旧 import 有明确结果 |
| V08 | 完整 Solution | PickCube、NutAssembly 各自对公开支持的多个 provider 单 seed 各一次；至少 MuJoCo 任务成功，其他结果如实分列 |
| V09 | Recorder／reader | 对完整运行的同次原始记录做独立读取，核对实际命令、状态／时钟、success／completion、有关图像；不要求再模拟一次 |
| V10 | 文档／示例／项目收尾 | 正式例子、链接、能力表、stage 证据归并、refs/worktree 处置与保护文件核对 |

执行包必须把 V01～V10 映射到实际 test node／用户命令和复用证据，不允许只写“跑 relevant tests”。这份映射应足够短，能看出每个命令为什么要跑、会不会启动 native、最多产生什么输出。

**完整 Solution 具体口径：**

- 两任务采用已接收 seed 或维护者指定单 seed，例如 PickCube 既有 31、Nut 既有 19，仅是冻结时可参考值，不是本文新设资格。
- 每家 provider 一次完整尝试，不要求为追赶其他 solver 数值而反复调参；普通适配缺陷在同一授权窗口修复复验。
- 非 MuJoCo 的任务未成功若是 solver／任务策略差异，给真实结果和合理边界；若是构建、施控、clock、采集／close 故障，仍必须修复或由维护者明确调整范围。
- 不具备该任务正式资产／能力的 provider，先给具体能力边界及修复方案，不能用 candidate、mock 或静默 fallback 填 PASS；是否接受该例外由维护者决定。
- 无完整 Solution 的简单主体不因此强造一套任务策略；其动作链通过 V02，完整任务验证针对已有正式 Solution。

### 14.3 不应再新增的“验收门”

不要求不同 provider 轨迹／像素逐点相同；不重设旧 5b 像素阈值；不要求全部 backend×renderer×Controller×Robot×seed 的笛卡尔积；不要求通用动态 renderer 切换；不把所有启动阶段 unknown 强行补造成零；不要求为每个安全检查新增镜像单测；不通过测试数量、manifest 文件数或删行数评价架构。

保留必要边界：真实状态与图像同一已发布物理边界；单位／传动／资源映射正确；物理唯一推进；旧 episode／stale 拒绝；失效资源不继续使用；实际支持范围诚实。这些是包装器基本正确性，不能与冗余测试一起丢掉。

### 14.4 复用证据的具体规则

对每条被保留的结论记：claim、旧代码／source／配置、当前相关 diff、涉及 owner、为何不受影响或最小补测路径。代码 HEAD 不同不自动让所有证据失效；共同 reset／state／submit 被改也不能自动继承所有旧实测。

允许不同独立 gate 用不同受测运行证明，例如原窗口、后续 task RGB、source 读回分别成立；不允许把同一任务成功所需的 state／图像／receipt 从不同 run 拼成一个不存在的成功运行。

若 V08 的最终完整运行覆盖了 V02 的同一任务／Robot／控制／provider 路径，可以直接覆盖该最短纵切，不再重复构造一个 smoke run。

## 15. stage1～stage5 workspace 归并和清理

### PROJ-01：大量 attempt／continuation 目录已经妨碍恢复和使用

**确认／P1。观察范围：**主 checkout 的 `workspace/maintenance/` 当时第一层约 230 项；仅按目录名粗分，G01 4、G02 3、G03 12、G04 12、G05 77，其余包括旧版本及其他工作。数字不是完整证据数量／字节统计，也不是各 stage 全部内容的最终分类。另有 `workspace/evidence_import_v211_stage5_20261108/`、旧 v210-integration checkout 中的阶段证据。

**用户痛点：**接手者看到多个 attempt、rework、Sol side、continuation，不知道最终哪个有效；成功包又引用旧 snapshot／H5／图片，目录名不能说明依赖。保留全部重复缓存与资产副本既耗盘，也让最有价值结果埋没。

**维护者决定：**每 stage 归并一份最终成功交付；有诊断时另归并核心诊断；不保留所有历史 attempt／失败输出。不要求新建庞大的历史问题数据库或永久归档全部旧目录。

**必须如何实施：**

1. 在 stage 已接收、无活动 writer 后，确定各子阶段最终接收的 claim 和证据来源。不能按目录名最大编号选“最新”。G05 尚未最终接收的活动目录不清理。
2. 创建一个最终 stage 包，按该 stage 的子阶段／claim 组织；一个 stage 内可以有多个不同源码身份的有效子结果，不伪造一次全 stage 单运行。
3. 复制最终成功原始结果与它确实依赖的输入身份／source delivery／配置／reader，去重资产副本和可重建缓存。核心诊断只保留能解释最终架构／限制／重要修复的材料。
4. 从新最终包独立复算验收结论，检查没有引用待删除目录。只写 report 链接而丢了它读的 H5／图像／source，不能算归并完成。
5. 生成新清单和旧→新路径对应。旧文件内容不可被改写来假装清单仍完整；明确新包是归并交付，不冒称旧 manifest 的原目录从未变化。
6. 列出最终删除候选和不属于本 stage 的保留项，确认保护输入、活跃缓存、source 原件、第三方资产和 frozen worktree 不被误列。按实际清理包执行，最后再检查最终包与引用。

**阶段完成条件：**

- [ ] 每个 G01～G05 各有唯一最终成功包入口，所需子阶段成果齐全。
- [ ] 核心诊断独立、精简、确实支持当前限制；没有保留整套失败矩阵充数。
- [ ] 归并后可直接复算成功结论，所有保留输入可定位。
- [ ] 旧重复 attempt／cache／副本按清单清理，未接收或活动工作不误删。

### 15.1 推荐的最终包结构

以下是内容组织建议，不是必须新造固定 schema；优先复用项目已有 manifest／receipt 格式。

```text
workspace/maintenance/v211_stage_closeout/
  stage01/ ... stage05/
    report.md                  # 最终已接收能力、限制、对应 commits
    evidence/                  # 支持成功结论的原始结果，按子阶段/claim组织
    inputs/                    # 必要配置/身份/实际依赖的受控输入引用
    readers/                   # 能复算这些结论的最少读取方法
    manifest.*                 # 新包自己的清单
    core-diagnosis/            # 本stage确实需要保留时才有
```

`inputs/` 不意味着复制整个 Menagerie／provider 仓库；可以用冻结 ref、asset identity 和独立保全的必要闭包。若原成功只在临时派生 USD 上成立，就必须保留其必要 delivery 与来源关系，不能只留一个失效绝对路径。

### 15.2 各 stage 的实际归并起点

| Stage | 已发现目录族 | 归并时必须回答的问题 |
| --- | --- | --- |
| G01 | `v211_g01_1a/1b/1c/1d_attempt001` | 协议／capability／资产决定哪些已经进入正式文档，哪些仍需要原始取证？重复草稿不用保留 |
| G02 | `v211_g02_2a_attempt001`、`2b_attempt001/002` | 完整 Solution 最终成功来自哪一份同次记录？哪份是过程失败，不应继续占最终入口？ |
| G03 | `3a_attempt001/002/003`、`3a_diagnostic_attempt001`、`3b_*`、`3c_attempt001` | 三 provider 与 reset 的最终接受证据分别在哪？哪些旧 controller/source 锁仍被当前能力引用？ |
| G04 | `4a_*continuation/recovery/reassessment`、`4b_attempt001/002`、`4c_attempt001` | effort、BodyWrench、Controller reset 哪份是真实最终证据？不把 ACK 写成测力；核心 source/单位诊断保留哪些？ |
| G05 | `5a_*`、`5b_*diagnostic*`、`5c_attempt*`、`unit004*`、`unit005*`、`unit006*`、`unit007_008*` | 5a／5b 与重构后5c分层，不把历史 candidate 成功当最终架构；完整5c接收后才做最终归并 |

单元 5 `continuation_003…014`、多个 Isaac 续作和单元 4 R05c 等目录不是新 stage。最终要按能力归并，不要求用户记住每一轮号。旧 source 预算超额、unknown 或曾有覆盖事故，如仍影响最终结论，应在最终报告限制或核心诊断说明；不需要为了保留历史把所有无关日志留下。

### PROJ-02：原始证据、可重建缓存和第三方资产必须分开

**确认／P1。位置：**各 run 内 cache／snapshot／mesh 副本、`workspace/evidence_import_*`、SDK Kit／Taichi／Python cache、provider workspace、保护输入。

**正确处理：**最终成功的 H5／原始 RGB／必要 receipt 与读回结果保留；核心诊断保留必要样本。可重建 cache、重复网格、失败临时 snapshot 通常可清理，但先确定没有 live lease 和最终包依赖。全局 SDK cache、第三方 source 原件和其他项目文件不属于“stage重复输出”，不能顺带删。

**事故预防：**若去重使用共同资产库，最终 manifest 要能绑定实际字节和引用，不能清除重复 mesh 后继续宣称旧 manifest 全部可核验。恢复路径和哈希是线索，不等于恢复完成。

- [ ] PROJ-02：文件分类、依赖与实际处置一致；无悬空最终证据或越界清理。

### PROJ-03：生成物应继续 ignored，Git 历史清理不能与 workspace 归并混做

**确认已有修复＋保全／P1。位置：**根 `.gitignore`、历史 5c 强制跟踪 workspace 的记录、当前 `git ls-files workspace temp_output`。

当前相关 tracked 文件数为 0，不应继续报告“目前还有 72.9 MB 被跟踪”。旧误提交和已做的历史调整有其记录；本次不为了目录清理再改写 Git 历史。最终 stage 包也仍为 ignored，仓库跟踪的是简洁接收摘要／索引，不是原始 H5、图片、source snapshot。

- [ ] PROJ-03：最终工作树无误加生成物／资产，已有保护文件未改；历史提交身份没有被无意改写。

### PROJ-04：真实输出目录和运行 cwd 的副产物必须列入清理范围

**确认／P1。位置：**根实际存在的是 `temp_outputs/`（复数，核查时仅一层 `logs/`）；`temp_output/`（单数）不存在。另有根 `MUJOCO_LOG.TXT`、`__pycache__`、SDK cache和各worker工作目录。

**具体风险：**只清理某个工作包内的文件会漏掉cwd产生的日志／字节码；按猜测拼目录名又可能清错路径。曾有包外pytest临时输出、缓存及MUJOCO日志追加偏差，说明“文件都在包内”的假设不成立。

**必须做：**先列实际写入位置及owner，将最终成功需要的输出归并；其余按第15节分类。新worker使用独立cwd和显式输出／cache位置，保持普通库代码不硬编码某次run路径。保护原件不因名字像日志就删除，第三方／全局cache不顺带清理。

- [ ] PROJ-04：真实输出位置已对账，清理后无漏存的最终证据或被误删的保护文件。

## 16. 分支与 worktree 收敛

### BRANCH-01：阶段分支、旧 worktree 和证据路径需要一起处置

**确认／P1。本次观察的本地分支：**

| 分支 | 核查时 HEAD | 当前处置要求 |
| --- | --- | --- |
| `codex/v211-stage5-diagnostic` | `17bde018` | 当前主题分支，复用；不因优化 Goal 新建分支 |
| `codex/v211-stage5` | `f3674a0b` | 旧 v210-integration checkout；核对独有提交／未跟踪证据后再清理 |
| `codex/v211-stage4` | `3ca161c4` | 历史阶段分支，接收与证据保全后清理 |
| `codex/v211-stage3` | `842e1efd` | 同上 |
| `develop` | `9d942d43` | 保留；当时相对 `public/develop` 显示 ahead 236，不能默认等于当前阶段成果已合入 |
| `main` | `fd03817c` | 保留，不擅自 merge／push |
| `v1.1.0`／`v2.0.0`／`v2.1.0` | `f292df14`／`3759f917`／`fd03817c` | 版本分支保留；冻结 tag 保留 |

**本次观察的 worktree：**

| 路径／用途 | 核查时身份 | 清理注意点 |
| --- | --- | --- |
| 主 checkout `/home/lly/Program_Files/Geochora` | 当前分支 | 保留当前工作位置 |
| `~/.codex/worktrees/v210-integration/Geochora` | `codex/v211-stage5` | 含大量早期stage证据；先归并并移除绝对路径依赖 |
| `~/.codex/worktrees/phase-ii-01-camera/Geochora` | detached `2cba22d9` | 核对独有文件、活动锁路径和历史引用 |
| `~/.codex/worktrees/archive_v1_0_0` | detached `42787f5e`，locked | 历史 frozen reference；tag／必要本地字节先保全，不能把 locked 当可强删标志 |
| `workspace/maintenance/geophys_upstream_reset_20261022_001/core-baseline` | detached `60b3ecac` | 先识别其 provider 对照／未合入提交；不要用递归删 workspace 误删 Git worktree |
| `workspace/maintenance/p2_0_v1_1_clean_checkout_20261017` | detached `bee498d1` | 同上，核对原始版本依据 |

这些是观察时点，不是最终删除命令清单。主线可能继续变动，实施者须重新列举。

### 16.1 清理顺序与完成标准

1. 优化代码及功能已人工接收；没有活动 writer／worker／source lease；当前 dirty 的归属已经处理。
2. 保存 refs、worktree、独有 commits 和本地文件清单；检查 ancestry／未合入提交，不能仅看分支名称或“看起来很旧”。
3. 最终 stage 证据完成第 15 节归并；所有指向旧 worktree 的必要资产／脚本／锁路径有实际替代。双锁协议若改路径，需要后续执行包明确更新，不能先删锁再解释。
4. 独有实现提交必须保全到适当保留分支／正式集成结果；需要 merge 的操作按维护者的实际集成授权执行，不把“清理”解释成自动把阶段合入 main。
5. 有 submodule 的 checkout 按 Git／管理工具的实际能力安全移除；不使用递归删除跳过 worktree 管理，不删除其他会话拥有的 checkout。
6. 删除不在白名单的阶段／诊断分支与旧 worktree；保留 main、develop、确定的版本分支及一个当前分支。冻结 release tags 不动，不自动新建 v2.1.1。
7. 重新核对 refs、submodule、保护输入、正式构建路径和证据索引；证明没有独有成果丢失和绝对路径断裂。

- [ ] BRANCH-01：分支／worktree 按白名单收敛，独有实现和最终证据已保全，无未经授权的 merge／push／tag。

## 17. 实施顺序：按职责迁移，不再按历史失败逐个补丁

以下是一个实际优化计划的依赖顺序，不机械等于新的 attempt 数量。每段都必须在生产调用链完成，不交空 schema；普通失败在获批窗口内定位修复。

| 顺序 | 动工范围 | 必须产出的具体结果 | 停止条件 |
| --- | --- | --- | --- |
| O0 | 当前 G05／5c 与活动现场 | 单元9综合接收、当前HEAD/dirty owner和支持范围明确；冻结本文执行包 | 5c未接收或其他writer未释放时，不并发大重构 |
| O1 | registry、configuration、Task bindings、Robot recipes | 一份正式构建输入；candidate 到正式入口的迁移表；source／Robot／Task所有权清楚 | 不允许先复制一套新UnifiedEnv再改caller |
| O2 | Env/reset、runtime builders／initializers、Controller／interval | 公共Env按声明／能力编排；同一个物理owner和提交；旧兼容caller明确 | 不以移动同等profile分支假装减责 |
| O3 | source composition、provider admission、renderer／camera／observation | Task专用值留Task；native解析留adapter；统一状态消费和同步图像；必要探针归位 | 不把source限制或renderer差异重新渗入公共Task |
| O4 | Recorder／replay、CLI／示例、相关测试 | 正式用户配置可读；同次记录可复核；旧接口与实验oracle分层 | 不用receipt适配替代真实生产行为 |
| O5 | 最小真实回归与完整Solution | 第14节映射表完成；正式多provider单seed运行；MuJoCo任务成功 | 实质运行缺陷修复后补受影响项，不扩成历史矩阵 |
| O6 | 当前文档／Skills／独立主审 | 全台账逐项结案，规范与源码一致，代码优化人工接收 | 未逐项对账不得用一个测试总数宣布结束 |
| O7 | stage证据、旧worktree和分支 | 最终成功与核心诊断归并；白名单收敛；清理后路径复核 | 最终证据或独有提交未保全时不删除 |
| O8 | 项目优化最终接收 | 文件／refs／证据／示例全部复核，再决定进入G06 | 不自动启动G06，不自动merge／发布 |

### 17.1 每个局部修复包必须写清楚的内容

不要再给实施者一句“收敛到共同 owner”就让其自己猜。每包至少给出：

1. 具体生产入口和调用路径，涉及的文件／类／方法；
2. 哪段决定迁移给哪个已有 owner，输入／输出怎样改变；
3. 哪些合法能力分派、旧接口和安全检查必须保留；
4. 旧 caller 如何迁移，临时兼容桥何时移除；
5. 几个具体纯检查节点、最短真实命令和旧证据复用理由；
6. 独立主审看什么，失败到哪个实际边界才返包；
7. 最终提交、输出、释放与唯一交付入口。

若明确不知道某模块的合法职责，先提出待讨论的问题，不默认存在一个“正确方案”交给实施者无限猜。当前台账已经回答架构方向；具体未决点应在该局部包中显式列出。

## 18. 最终逐项对账与签收

### 18.1 逐项记录模板

每项不必另造一个报告；在最终接收文档中使用下表即可。`证据`优先链接最终归并包内必要部分，不复印大量旧日志。

| ID | 原问题是否仍存在 | 最终代码owner／符号 | 实际变更／原样保留理由 | 正式caller／验证命令／复用依据 | 结论与主审 |
| --- | --- | --- | --- | --- | --- |
| 例如 ENTRY-01 | 是／否／部分 | 真实路径 | 不写“已优化”，写具体分派与输入怎样收敛 | 对应V01及实际输出 | PASS／待办；人工确认 |

`原样保留`必须解释它为什么是合法能力／兼容／安全职责，不是“历史测试需要”。`NOT_APPLICABLE`要维护者确认；未经批准不能把难做项改成以后再说。

### 18.2 总验收清单

- [ ] GOV-01～04：四个根因已处理，当前规则和实际代码一致。
- [ ] ENTRY-01～03：正式入口、配置、相机声明可直接使用。
- [ ] TASK-01～04：任务目录符合职责；没有重复候选生命周期；两简单主体没有旁路施力。
- [ ] ENV-01～05：构造／reset／状态／Solution／close 的实际owner收敛。
- [ ] SUBJ-01～03、CTRL-01～05：四主体、嵌套、Controller匹配和typed命令语义保全且可组合。
- [ ] SRC-01～04、RUN-01～04：资产recipe、Task、source、正式准入和provider执行分层。
- [ ] REN-01～08、OBS-01～02：renderer能力、公共状态、真实采图、窗口与任务相机独立及固定obs闭合。
- [ ] REC-01～03、CALL-01～04：记录、回放、CLI／示例和必要旧caller明确。
- [ ] TEST-01～04：核心测试有claim、范围与授权；无测试反向塑造生产架构。
- [ ] DOC-01～02：当前文档／Skills准确，过时“当前”文字已处理。
- [ ] V01～V10：按影响完成；完整多provider单seedSolution已运行，至少MuJoCo成功；不同结果没有混写。
- [ ] PROJ-01～04：stage1～5仅保留最终成功与核心诊断，归并后可复核，生成物继续ignored。
- [ ] BRANCH-01：优化接收后完成旧worktree和分支清理，保留白名单与必要tag。
- [ ] 清理后正式示例／依赖路径和最终证据入口可恢复；无活动资源／保护输入变更。
- [ ] 实施者交付、独立主审和维护者最终接收三者分列；G06没有自动启动。

### 18.3 必须分别回答的三个结论

1. **5c／G05 功能是否接收？**由单元9对原5c出口和新增统一主体要求作综合判断；不是把九个单元的PASS字符串相加。5a／5b有效成果按实际影响复用。
2. **代码优化是否接收？**由正式用户入口、职责owner、可组合性、最小回归与完整Solution，以及本文全部代码条目决定。目录少、if少、测试多都不是充分条件。
3. **项目优化是否接收？**由最终stage证据归并、当前文档、分支／worktree白名单和清理后可恢复性决定。不能在代码优化通过时，顺便把尚未做的项目清理也标成完成。

只有这三个结论按实际范围明确成立，才达到本次维护者要求的“5c后完成优化再进入G06”的停门。本文没有预先作出其中任何一个通过判断。

## 19. 本文自身的检查记录

本次仅新增此文档，未修改主线13个dirty文件、三个保护输入、refs、worktree或gitlink；未运行生产代码、native或矩阵。

- 逐项台账为60项，含确认问题、待核边界与保全项，不等于60个已复现运行bug。
- 本文相对文件链接已逐一检查目标存在；编号无重复，代码块闭合；`git diff --check` 无输出。
- 仓库现行文档检查器实际运行：`python -B .agents/skills/geochora-doc-governance/scripts/validate_docs.py --mode current`。结果有1项错误：`protected local input changed: MUJOCO_LOG.TXT`；这是检查器对既有保护输入基准的报告，本文未修改该文件，不为使检查全绿而改原件或基准。另报告96项历史链接问题，不能说整个文档库已无错误。
- 当前广泛文档检查不等于上述所有代码／项目条目通过；本文台账仍待后续实施和独立接收。
