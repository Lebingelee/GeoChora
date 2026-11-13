# E11～E16 调整后的实施 Goal

日期：2026-11-13。状态：`PLANNED_NOT_STARTED`。本文件是供维护者后续启动的完整实施提示，本次保存不创建/恢复执行Goal，不授权native或删除。E00～E10已获维护者按各自范围接收。

---

请依据[总台账](post-5c-code-project-optimization-diagnostic-ledger.md)和[E11～E16专用账本](post-5c-e11-e16-remaining-ledger.md)，实施E11～E16。以专用账本的7个大单元、T01～T44为日常执行依据；每完成一个U，包含实现、必要修复、定向验证、记录压缩和本地提交，再核对总账对应条目。不要每读总账发现一处就修一个小函数，不把44点拆成44次派包或native测试。

## 已接收范围与基线

G01～G05有界接收、5c单元1～9收口，E00～E10维护者接收。保全共同正式配置/构建/主体/Controller/生命周期/唯一提交链，以及source、provider、状态/相机、renderer、Task和Recorder的既有owner。不得重新展开底层普遍重构；后续发现真实回归在当前单元修复。

规划输入`a6b107ac43bed77565a643612372c6c76e641511`，最新生产小修`7a098423`；执行开始核对实际HEAD和diff，复用`codex/v211-stage5-diagnostic`。不新建主题分支/worktree、不重置已有改动。四保护untracked输入保持字节及归属，总台账本身也不编辑/提交；GeoPhys/Menagerie pins按专用账本冻结。若其他writer/窗口未释放，先明确归属，不叠加执行。

## 按单元实施

1. **U1／T01～T07，诊断与测试。** 复用`task_env/diagnostics/tasks/v2.1.1/`现有检查，分类纯/fake、离线记录、真实资产/source、CPU native、GPU/App、窗口；给可直接运行的最小命令及守卫。逐项处理旧candidate/reader引用和fixture：有价值行为迁入本版本，历史oracle显式保留，无产品意义的实现细节退出。不能恢复旧产品分支换测试通过，也不能删除身份/单位/资源/clock/stale/fault检测器。保留合法provider准入、readback、历史codec，不因F05或probe字样机械删除。输出单份claim/owner/去向表。
2. **U2／T08～T14，caller与外围兼容。** 普通CLI/教程/示例使用正式配置和make_env，无需内部receipt/临时manifest；高级Harness保持明确范围。核对广泛backend fallback和多处completion报告，显式请求失败不伪装另一个交集成功。检查vector纯构建、space、autoreset、terminal observation、renderer owner和learner import；保全尚有caller的component batch路径，未支持正式batch明确拒绝，不实施G06或训练。LIBERO保留原任务/source/OSC/gripper cadence，只适配受影响Core接口。objects/planners/reporter/utils有问题才改，无问题写保留依据。
3. **U3／T15～T21，完整Solution与全程记录。** 在实际执行窗口冻结精确命令和资源计划，运行专用账本五条交集：PickCube MuJoCo CPU、GeoPhys CPU、Isaac PhysX CUDA各单seed31正式R3；Nut MuJoCo/GeoPhys CPU各单seed19正式Outcome。seed/horizon以正式参考和实际准入冻结；Nut Isaac目前不支持，不补新路线。两任务各自MuJoCo必须任务成功并完整完成原Solution/Outcome；其他solver任务失败如实分列，执行/adapter故障必须修复或留下待维护者决定的明确例外。每条记录同次H5，独立读取命令/状态/clock/T/T+1/任务和completion/有关图像，并记录close/App结果。不要以短程、step_with_solution一次或reader通过冒充完整成功，不拼不同run，不重跑仿真代替读回。
4. **U4／T22～T28，文档与代码优化接收。** 更新单一能力矩阵、API/指南/当前摘要/Skills与真实示例，原目标、当前支持、未测范围和历史决定分开。原60项逐行给owner/变化或保留理由/真实caller/证据/结论；V01～V10另列映射。复用E00～E10接收而不重复审计。独立主审实际代码/调用链和完整Solution，修普通余项，提交代码优化范围的接收结果；E15/E16项目项仍单列OPEN，维护者接收不得由实施者自封。
5. **U5／T29～T34，最终证据包。** 按最终主审claim而非最大attempt选G01～G05原始成功证据，每stage一个最终入口及必要核心诊断；同时保全优化结果的必要证据。复制/去重必要H5/RGB/source/USD/receipt/reader，冻结必要资产闭包与旧→新映射，从新包独立复算，不改原始历史结果或冒称单次全stage运行。只保留最终成功和解释当前限制的重要材料，不全量永久归档失败。交确切保留/删除路径、owner、bytes、引用和恢复清单，U5不删除原件。
6. **U6／T35～T38，实际输出整理。** 先处理当前Harness共享锁仍在历史大目录、旧H5测试路径及必要当前引用。无活动锁owner时统一所有运行端路径，不能unlink活跃锁形成双锁。确认具体清单已授权、原件已保全且新包可复核，再清理冗余attempt/cache/副本；排除嵌套worktree、其他版本/项目、第三方source、全局SDKcache、保护原件和必要输入。测目录/文件/逻辑/分配字节及归并新增量，证明实际净下降；生成物仍ignored，Git不收原始数据。
7. **U7／T39～T44，refs/worktree与项目接收。** 重新核对实际owner/refs/ancestry/dirty/ignored/子模块类型；保全所有独有提交及本地字节并实际恢复验证。按Git/App支持的流程处置，不能强删绕过locked/submodule/活动或归属问题。白名单保留main/develop/v1.1.0/v2.0.0/v2.1.0、一个当前阶段分支及冻结tags，不自动建v2.1.1。当前观察预计heads9→6、worktrees6→1，以安全/授权成立为前提；未处理对象明确OPEN。清理后复查正式配置/import/space/示例路径、五stage包和优化汇总、保护SHA及pins，提交独立项目主审与维护者接收入口。

## 验证和执行边界

- 先查实际代码/调用者/fixture，遵守CodeGraph优先；精确node启动，不把整个历史模块称为纯测试。fresh-process守卫SDK和安装资产；离线H5与真实source构造分列。已有强检测器优先，不按测试数量、文件数或删除行数定义成功。
- native开工前登记interpreter/provider/source/controller/renderer/seed/horizon/timebase、唯一目录、cwd/cache、显式子步与采图/App上界、墙时/内存/磁盘及现有锁。预算给普通定位修复和定向重试余量，失败run不自动等于新attempt；不擅自扩大物理矩阵。构造/reset可能重建App，不能照抄“最多一次App”；未知隐式推进写unknown。
- V01～V07按owner diff选择最短补测或旧证据复用；完整运行已覆盖同claim就不另跑smoke。G05三原生/cross/taskRGB/窗口旧证据按原输入和实际影响复用，不改称本轮HEAD重跑。没有改renderer不为完整Solution强加五条RGB。独立reader读取同次关闭记录，工作JSON不是第二次物理测量。
- 保留Position/effort/wrench各自物理语义、身份/单位/资源/clock/fault和唯一advance owner。COM原严格FAIL/有界采纳、N08原FAIL、R05c NOT_REQUALIFIED、SDK关闭日志及执行偏差仍保留；不重开5c或改历史资格。renderer固定至close，G07三provider×三seed继续保留。
- 文档检查按现行validator，基线2 errors/96历史链接问题逐项归属；不改保护原件/随意expected hash、不恢复退休文件换全绿。处理当前断链与历史source-ref，剩余问题给准确结果/决定，不称全部通过。
- 后续正式实施授权内，可逆代码/测试/文档/保全准备自主完成。删除执行须有已准备的具体清单、保全和相应维护者授权；已授权不重复问。缺授权或对象owner/活动状态未明时，完成可审查结果后在实际操作边界集中提出一次具体问题，说明依据和待批准对象；时间经过不算批准。不能仅因执行提示包含U6/U7就推断任意历史目录/他人checkout均获准强删。
- 不改pins、不merge/push/tag/发布、不自动创建或消息其他chat，不自动启动G06/G07。可以提前只读准备后续清单，执行按U4代码接收→U5复算→U6具体清理→U7项目接收依赖推进。

## 每个大单元的成效与记录压缩

在专用账本第11节更新一次结果，详细事实可链接一份精简表。报告输入/输出HEAD、diff/提交/证据、T项PASS/OPEN及最终owner；文件前后/增删迁移、生产+/−/净量与迁移量、诊断/测试/文档分桶。本轮相对a6b107ac与累计相对1f1359ee分开，不冒领前轮成果。说明实际消除的分流/依赖、可读性与职责变化、adapter对Runtime合同的变化/保全及未涉及部分。无生产变化记0。

运行结果分runtime validity、task success、Solution completion、record/readback、close；项目单元追加目录/文件/空间/refs/worktree前后和可恢复性。过程日志留ignored原始目录，当前执行记录按模块压缩，只保留最终效果、边界和证据入口，不持续堆追加日记。

最终分别报告E11～E16状态、44点结果、总账60项和V01～V10对应证据，以及实现自评/独立主审/维护者接收。U4单独回答代码优化是否接收；U7单独回答项目优化是否接收。未完成项、未经批准的N/A/延期和未执行删除不能包装成Goal整体完成。只有实际完成相应工作及接收后，才提出由维护者决定进入G06；这仍不是v2.1.1版本完成。
