# E00～E04 调整后 Goal

日期：2026-11-12。用途：维护者恢复原实施会话时替换原宽泛 Goal 的提示文本。**本文件的编写不恢复已暂停 Goal，不授予本次规划会话生产修改／native 权限，也不创建或消息其他 chat。**

执行主账本：[E00～E04 剩余实施账本](post-5c-e00-e04-remaining-ledger.md)。范围依据：[优化总台账](post-5c-code-project-optimization-diagnostic-ledger.md)及维护者对四任务、退休入口和版本诊断目录的最新要求。既有进度与原始证据索引：[执行记录](post-5c-optimization-execution.md)。以下正文可直接用于恢复实施。

---

请继续完成 GeoChora v2.1.1 的 E00～E04，以本次专用账本 R01～R30 为逐项实施和接收清单。当前已经有大量有效成果，先保全账本 K1～K7，再按 U1→U5 结束剩余闭环。不要把目标重新变成逐次翻阅总台账、发现一个局部问题、修一处、跑一轮短测的无限循环。

## 一、输入和范围

1. 重评输入为 `codex/v211-stage5-diagnostic@b94e86250140bffebc27bf92b2e8aec60688b7e4`。规划文档可能随后有本地提交；恢复时以实际 HEAD、diff 和现有 writer 状态核对，不硬要求回退 b94。
2. 保全分支已有符合目标的实现、原始证据、两个 submodule pins、四个 untracked 输入及执行记录的既有 dirty 追加。只提交本单元拥有的路径。不得 reset、改写历史、清理证据或新建阶段分支来重新开始。
3. 正式任务范围为最新版 PickCube、NutAssembly、Pendulum、双轮车；一体／装配 Panda 是这些任务构建机制的主体子例，不新增第五个任务或任意装配树要求。
4. 四任务已经进入共同正式配置链；保留这一成果。旧 component 路径若仅服务范围外 caller，明确边界即可，不把全仓删除 component 当作 E01 门。
5. Position candidate、两个旧 PickCube physical UID 及其专用旧输入已经退休，不恢复。Position Controller、typed 命令和仍被正式任务使用的能力继续由真实 owner 提供。

## 二、固定工作顺序与结束单位

按[专用账本](post-5c-e00-e04-remaining-ledger.md)实施以下五个大单元：

| 顺序 | 必须结束的工作 | 检查点 |
| --- | --- | --- |
| U1 | 把四任务共同配置后的 source、主体、Controller、TaskDefinition 建造阶段实际接通；Task 内的构造编排归现有 owner，合法 source／控制差异由能力处理 | R01～R08 |
| U2 | 沿共同构造结果收口 reset 事务、source lease/cache、publication、fault、worker／App／camera 的资源交接 | R09～R14 |
| U3 | 收口 action／ExpertAction／Solution／已支持序列的入口支持表、重复提案转换、失败副作用和唯一提交／推进 | R15～R21 |
| U4 | 迁移本次直接影响的 caller 和版本诊断，移除只因旧 fixture 存在的复杂度，压缩当前效果记录 | R22～R25 |
| U5 | 根据实际改动复用或补最短真实路径，核对总账对应部分，分别完成 E00～E04 结果和接收材料 | R26～R30 |

一个大单元包含实现、必要修复、验证和报告，可以包含多个本地提交和多次运行。小格不是一次派包、一次 attempt 或一个必须单独运行的测试。保留原 attempt／时间／资源历史，不借 U 编号重置已有计数；如触及真实既有停止条件，按原规则向维护者报告。

在每个大单元内：

1. 读账本的本单元及实际相关 diff／源码，确定本单元输入、接收方和退出证据。
2. 连续完成该单元各格，遇到可独立修复的普通错误就在本单元处理，不为一次失败提前返包。
3. 对共同 owner 的改动稳定后，运行精确受影响检查及最短必要 native 路线；不为每个 helper／每个提交重复宽测试。
4. 单元整体完成后，对照账本第 9 节指定的总台账部分一次；处理遗漏，然后更新本单元的最终结果并提交。
5. 若已有授权和依赖均满足，推进下一单元；原始 Goal 的暂停状态由维护者恢复。本提示不自动恢复暂停或派发执行者。需要交接时，完成报告和资源释放后再切换 writer。

## 三、共同架构的硬边界

- 统一的是正式配置、Task／Robot／Controller 声明与编译合同、构建阶段、状态／命令／生命周期交接；允许 MJCF／USD、Position／effort／wrench、单层／嵌套的合法 capability 和 adapter 实现不同。
- Task／TaskDefinition 保留物体、命名语义映射、reset 分布、奖励、谓词、Solution 和默认参数。公共 owner 不能反向知道 PickCube 的任务名或奖励，也不能让 Task 组织 native／Controller 运行主线。
- 优先扩展 `ReferenceTaskBinding`、`TaskBuildRequest`、`SourceBoundTaskBuilder`、现有 source adapters、Controller capabilities、RuntimeBuilder 和 `EpisodeExecutionState`。不得新建另一套统一门面／Manager／Runtime，也不得整体搬 Task specialization 后包一层共同类。
- 共同构建必须有实际 caller，Controller 绑定必须对应最终 source、主体与 writer；RobotRuntime 事后视图相同不代替构造统一，声明与自身比较不代替 native 映射核验。
- 标准 Solution 调用为调用方持有实例，执行 `act → env.step → observe`。当前有真实 caller 的 `step_with_solution`／`step_expert` 仅为薄兼容；不因为历史测试继续保留重复调度，也不擅自破坏 LIBERO 真实 caller。
- 一个 interval 只有一个共同提交和物理推进 owner。保留 typed 单位、传动、限幅、重力默认关闭及模型限制、state/source/episode/generation/clock、冲突和部分失败检查。

## 四、验证方式

1. 首先按账本 R15 固定支持／拒绝范围，不给四任务普遍扩展所有输入。Nut guarded ExpertAction 的要求、当前不支持的 physical worker／序列组合继续明确表达。
2. 现有 `v2.1.1` 诊断优先复用；测试模块名为 provider-free 不表示它不会真实构造 source。按实际 fixture／调用选择纯配置、真实 source、native CPU、Isaac/GPU 和图像检查，使用精确 node 和守卫。
3. 真实短程覆盖正式构造、reset、非零 interval、state/clock、第二次 reset 和 close。四任务、装配 Panda、Position／effort 及 caller-owned Solution 的代表路径按账本 R26～R28 映射；旧证据未受影响时不重复跑，改变共同 owner 后不得盲继承所有旧结果。
4. 在维护者已授权且仍有效的 native 范围内，自行冻结本单元实际 HEAD／dirty、source、probe、seed、horizon/dt、显式子步和资源计划，使用现行锁与独立输出 cwd；正常修复与受影响重测属于原窗口。旧运行计划的预算不是新窗口授权；真正缺少授权、资源或外部输入时报告具体边界。
5. SDK App close receipt、真实日志、已知／unknown 启动推进分别报告；不自行加跨 solver 轨迹一致、像素阈值、启动零步或全矩阵门。
6. 完整 Solution 单 seed 和同次完整记录仍留 E13。本轮短程、单 interval、source 编译、fake 合同各自只证明其范围；不能以完整 Solution 未跑为理由无限延长 E00～E04。

## 五、范围控制与记录压缩

范围外问题记入专用账本第 8 节：问题、真实 owner、为何不阻塞当前单元，保持简短。完整 source registry／任意资产、完整 renderer／观测重构、全 H5／replay 整理、全部 benchmark、证据／分支／worktree 清理和 G06 均不提前实施或宣称完成。为本单元正确性必须修复的真实依赖不得借后续事件延期。

每完成一大单元，覆盖更新专用账本第 10 节及各 R 格的最终 owner／状态／证据；执行记录只保留模块最终效果和必要限制，不再逐批追加相似进度。过程和失败输出留 ignored 原始包，保留必要身份；不在本轮删除旧证据。

每单元报告必须能直接回答：

- 哪条实际构建／控制链收敛了，哪段 Task-owned native／Controller 编排或重复提案逻辑消失了；合法差异留在哪里。
- 生产、诊断、文档分别新增／删除多少；迁移与项目净变化分列。需要新增实现时说明职责，不设任意删行比例。
- 实际跑了什么、复用什么及其 diff 依据；未触及的 provider／renderer 和仍不支持交集是什么。
- 本单元 R 格是否全部有结果，下一单元依赖是否就绪，有无真正阻塞。

最终分别给出 E00、E01、E02、E03、E04 的结果和对应证据。实施者自评、独立主审与维护者接收分列；全部本范围退出满足后结束本 Goal，不再无界寻找新的“还不够统一”。本 Goal 完成不等于整个优化台账、v2.1.1 或 G06 已完成。
