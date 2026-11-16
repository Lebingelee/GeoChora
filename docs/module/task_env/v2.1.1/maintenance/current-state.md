# v2.1.1 当前状态

更新时间：2026-11-16。本文是版本的人工可读当前摘要；工作包、attempt 和历史记录由[编排索引](orchestration.json)维护，逐项优化范围由[优化台账](../planning/post-5c-code-project-optimization-diagnostic-ledger.md)维护。

## 当前停门

**G01～G05 与优化账本保持原有接收；G06a attempt002 已经[独立主审](reviews/20261115_g06a_attempt002_acceptance.md)有界接收（SOL_ACCEPTED_BOUNDED_6A）。Core 为 `3bc9e2a7`，GeoPhys pin 为 `a2c85b7f`；无需 attempt003。G06b／6c、完整 canonical 六格、R3 和 G07 尚未接收，v2.1.1 尚未完成。** GeoPhys 主分支合并与 AOT 按维护者决定暂缓，不记通过、不阻断本次接收。G06a 的 Isaac 第二来源证据是 scalar 物理；G06b 新增的 native batch 有界证据及限制见[API](../api/README.md)，仍待独立主审。下方早期启动表及历史记录保留其时点。

[单元 9 综合主审](reviews/20261111_unit009_sol_5c_bounded_acceptance_b23fb3cc.md)的 `SOL_ACCEPTED_BOUNDED_5C` 已由维护者在本次启动对话确认；原主审中的“维护者待确认”描述保留其审查时点。优化实施安排见[执行计划](../planning/post-5c-optimization-execution.md)。顺序为：G05 功能接收 → 代码优化、定向复验及人工接收 → 项目证据和 refs／worktree 整理及接收 → 决定进入 G06。G07 继续承担 G06 新增调用者及最终版本收口，7b 三 provider × 三 seed 门保留。

2026-11-14 总账复审及收尾：`d0902adc` 的[逐项复审](reviews/20261114_e00_e16_total_ledger_reaudit_0847a5da.md)确认57项满足有界出口，GOV-04／DOC-01／DOC-02留有编排和Skill同步欠账；后续已按维护者授权完成[E14资料收尾和60项现行结案表](reviews/20261114_e14_current_state_alignment_closeout.md)。60项及V01～V10均按既定有界范围结案，原复审保留其时点；不改变原运行身份、批准例外或G06/G07未开始状态。

维护者另行提出的[Env／provider／renderer精简计划](../planning/post-optimization-env-provider-render-slimming-plan.md)已完成 C1～C5 的有界实施和[集中复验](reviews/20261114_post_optimization_c5_final.md)，其限制及独立复核见交付记录；不是未关闭的原账目。基于 `7f8796b4` 的[G05→G06复核](reviews/20261114_g05_pre_g06_readiness_7f8796b4.md)未发现须重开G05的功能阻断项，已同步当前说明；可以准备G06的范围和执行包，本次不自动启动G06。

2026-11-15 G06交接准备：[总路线](../planning/roadmap.md)已补充两次G05架构改造及总账持续约束；本地develop已按维护者授权从`9d942d43`正常快进到阶段成果，首轮同步为`23c6c86f`，本交接文档提交亦同步。[G06 Agent handoff](20261115_g06_agent_handoff.md)保留派发前时点；后续 attempt001 已开始实施，main／远端未同步、未发布。

G06b attempt002 在 Core `f8c43d61`／GeoPhys `dd393187` 经[范围重估主审](reviews/20261116_g06b_attempt002_scope_reassessment.md)保持 **PARTIAL_NOT_ACCEPTED**。真实六格主链、GeoPhys显式discrete／32次预算的有界接触及reset、MJWarp B16双传感器与窗口800步已有证据。Sol此前将单次受控轨迹2mm界限扩大为通用门，现重估为不应沿用；scalar mixed缺陷和跨引擎接触力差异不自动阻断batch出口。窗口外观仍由维护者人工验收，AOT等既定暂缓事项保持。

2026-11-16 补充交接已[独立复核](reviews/20261116_g06b_attempt002_supplement_review.md)。[attempt003](work-packages/20261116_g06b_attempt003_goal.md)已执行，普通 attempt 计数为3；执行证据见[交接报告](../../../../../workspace/maintenance/v211_g06b_attempt003/report.md)。GeoPhys B1/B3 指定完整状态、Task及reset时钟对照、同源 Pendulum 无接触 scalar/B1 对照、诊断清理，以及 GeoPhys/MJWarp 七项受影响性能补测已完成。维护者已批准仅 Isaac PickCube 三个 B16 渲染组合的资源例外，B3 正确性不豁免；本次安全内存复核不足以启动 Isaac，Pendulum B16 窗口补测及最终 renderer 下 Isaac PickCube B3 的直接运行未闭合。G06b 仍为 **PARTIAL_NOT_ACCEPTED**，等待独立主审；没有宣布维护者接收。

## 启动输入与工作归属

| 项目 | 2026-11-11 启动核对 |
| --- | --- |
| 分支 | `codex/v211-stage5-diagnostic`；优化复用，不新增分支／worktree |
| 输入 Core HEAD | `1f1359eef9bfff73cf7688a8270c5f06471dc614`；是启动输入，不是随文档提交滚动的最新 HEAD |
| 5c 接收生产基线 | `a53bf19d2526c6c336dd5d0d7108eb0f643f80bd`；输入 `task_env` tree 为 `c4460cd6bcc96a16067d3f61556a66e52da23bbc` |
| GeoPhys／Menagerie | `c1ea3cc9fb99ccbd1d31c36d6fc7b84aa936b3d7`／`b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` |
| 工作树 | 启动时 tracked clean；四个既有 untracked 输入原样保护，含优化台账 |
| 执行窗口 | 单元 9 已有返包及释放记录；启动观察未见本仓库 native worker，前序协调 chat 为 idle；启动时当前 chat 仅写 O0 文档；后续直接实施 E00～E04 的资源使用按其运行计划及释放记录核对 |
| 当前改动 | E00～E04 已完成实施、基线独立主审及主审余项修复，并于 2026-11-12 获维护者统一接收。E00～E04 接收生产 `912416e6`，精确验证输入及限制见执行计划第 6 节；不沿用启动表充当实时锁 |

上表启动时的保护输入为 `MUJOCO_LOG.TXT`、2026-10-30 runtime route handoff、stage3 gravity proposal 和用户优化台账。精确大小／SHA-256 与原工作树状态在 ignored [输入快照](../../../../../workspace/maintenance/v211_post5c_optimization_o0_20261111_001/input-snapshot.json)，启动轮没有提交这些输入。维护者此次明确授权后，三份Markdown已在`0722341b`原样纳入Git，字节及原历史结论未改；目前仅`MUJOCO_LOG.TXT`仍为保护untracked。两个pins不变，没有清理原始输出、push或改tag；本地develop快进见上方交接记录。

## 已接收的能力与边界

- G01 协议基线；G02 MuJoCo PickCube 成功参考及 Nut 回归；G03 路由、真实执行与 reset 重建；G04 typed 控制／贡献／反馈／Controller reset，分别按原主审范围保留。
- 一体 Panda、装配 Panda、Pendulum、双轮车有共同主体／Assembly／Controller／场景 interval 的受测链；不声称四主体都在最终生产 HEAD 重新运行。
- Pendulum／双轮车的 MuJoCo CPU、GeoPhys CPU 和 Isaac PhysX CUDA 短程路线限各自受测资产。三条首批原生窗口／离屏与 task RGB 按主审及影响复用。
- 最新 Isaac task RGB 已覆盖 reset、非零 step、二次 reset 及 close；GeoPhys CPU physics × MuJoCo renderer-only 已有真实状态映射和零额外物理推进证据。依据见[单元 7／8 主审](reviews/20261111_unit007_008_sol_review_a53bf19d.md)与单元 9 综合主审。
- renderer 创建时选定并保持到 close；通用动态切换、任意装配树、任意组合、通用闭环及完整 batch 能力仍不属于已接收结论。颜色／挂载／source 限制继续适用。

COM 原严格判据失败、维护者有界采纳、原 N08 FAIL、R05c `NOT_REQUALIFIED`、Isaac 6.1 close 限制及历史执行偏差保留；不借本次状态更新转移资格或重开 5c。

## 正式入口及当前实施

E00～E04 接收生产为 `912416e6`；四个正式任务使用 `task_env.make_env`：`pick-cube-p16-reference-v1`、`nut-assembly-outcome-reference-v1`、`pendulum-v1`、`two-wheel-balance-v1`。mapping 与 YAML 进入共同配置解析及构建请求；具体支持的 Robot、Controller 和 provider 组合以配置准入及相应证据为准。基线生产 `76536d2a` 已有[独立主审建议](reviews/20261112_e00_e04_independent_review_76536d2a.md)，后续主审余项在 `912416e6` 修复并自检；维护者于本次对话统一接收 E00～E04。后续自检与原独立主审仍按各自时点保留。

| 事件 | 当前状态 | 实际进展和剩余边界 |
| --- | --- | --- |
| E00 基线与度量 | 维护者已接收 | 输入/证据/保护/统计已核对；旧 dirty 已完整保全，再恢复执行记录角色及有效索引。 |
| E01 入口与配置 | 维护者已接收 | 四任务共用正式解析与请求；Position candidate 和两个旧 PickCube physical UID 已退休；范围外 component 不进入这四条正式链。 |
| E02 模块与主体 | 维护者已接收 | 共同 builder 消费 source、主体和 Controller 阶段；复用 CompiledReferenceTaskV1 与具名 context，去除 20 种阶段临时字典键；合法 typed lowerer 差异保留。 |
| E03 Env 生命周期 | 维护者已接收 | 共同 reset/fault/close、source lease/cache、worker/App/camera owner 已按受影响范围核对；保留真实失败注入未测边界。 |
| E04 控制与推进 | 维护者已接收 | 当前支持输入进入共同 dispatcher/submission；兼容提案以显式投影和类型策略决定行为，错误阶段不再决定控制路径。 |

本版本诊断集中在 `task_env/diagnostics/tasks/v2.1.1/`。E00～E04 主审余项修复轮的 217 项受影响 source/caller 检查通过，另有 76 项纯/fake 精确检查通过（与前者有重叠，不相加）；六项 USD 检查为真实 delivery 的离线构造，不启动 Isaac App。MuJoCo 七条短程共 75 个显式子步，GeoPhys effort/Pendulum 两条短程通过；加上测试中的 40 个，本轮共 115 个显式 MuJoCo 子步。冻结输入为 `e25f37c5` 加保存的生产 patch，与 `912416e6` 对应生产字节相同，运行的 source_revision 仍为 e25，不改称提交后重跑。详情见[按模块压缩的实施记录](../planning/post-5c-optimization-execution.md#6-e00e04-实施记录)。renderer 未重跑，完整 Solution 仍留 E13；旧逐批记录从历史提交和原始输出恢复。

O5 对应的五条完整运行与同次读回及其开放边界见下方 E11～E16；O6 独立主审与维护者代码接收及 O7 项目清理和有界接收均已完成。[capability-matrix.json](../capabilities/capability-matrix.json)分列当前有界证据与历史目标；本地develop已按本次授权同步G05及优化成果，main／远端未同步，未发布。

## E05～E10：维护者已接收

E05资产/source、E06 physics adapter、E07状态/相机、E08 renderer、E09 Task精简和E10 Recorder/replay已按[专用账本](../planning/post-5c-e05-e10-remaining-ledger.md)完成，[实施Goal](../planning/post-5c-e05-e10-goal.md)保留为历史提示，不再作为下一执行包。[结果和证据](20261113_e05_e10_u7_delivery.md)及[独立主审](reviews/20261113_e05_e10_independent_review_d9dc02c6.md)覆盖S01～S40，生产小修 `7a098423` 删除physical Recorder的PickCube语义覆盖并验证声明保全；维护者于2026-11-13明确接收。后续完整Solution已按E11～E16的U3/U4有界核对，项目整理与最终接收见下。


## E11～E16：维护者有界接收

以[E11～E16细化账本](../planning/post-5c-e11-e16-remaining-ledger.md)及[实施Goal](../planning/post-5c-e11-e16-goal.md)记录七个大单元、44个检查点及其证据；维护者已按[接收记录](reviews/20261114_e11_e16_maintainer_project_acceptance.md)对 `86921c62` 及明确限制作有界项目接收。

规划时输入`a6b107ac`，tracked clean，四保护输入和pins不变；规划轮仅作静态及只读盘点。随后 U1（`d0c25ae4`）和 U2（`1ff617d0`）完成实施自评；U3 检查点 `5742e956` 记录五条完整运行、同次读回和受影响修复。四保护输入及两 pins 在 U3 后仍一致。规划时主 maintenance 约84.46GB、旧 integration 的 workspace 约13.79GB 均为混合总量，不是可删空间承诺；9 个本地 heads、6 个 worktree 须在处置时重新核对，当时 Harness 共享锁位于历史大目录；后续锁已按现行合同收敛。

E13 的四条 CPU 完整运行与后续 Isaac `solution-002` 均已记录任务成功及同次 caller Solution 完成；原 Isaac 失败保留在[U3实施结果](reviews/20261113_e11_e16_u3_solution_evidence.md)。维护者同意的[同次联合证据](reviews/20261113_e11_e16_u4_joint_completion.md)已完成离线核对，四条 canonical H5 completion 字段不存在，新 Isaac 字段为 null；H5 单文件不自含完整 completion，独立复审已支持该有界结论。E14 文档与代码范围已按维护者本次条件授权[有界接收](reviews/20261113_e11_e16_u4_independent_acceptance.md)；该段为 U4 接收时点；其后 E15/E16 按具体清单保全、归并、安全清理和恢复，项目优化现已由维护者有界接收；不自动 merge/push/tag/发布或进入 G06。详细检查点、接收 owner 和操作边界均在专用账本。

2026-11-14项目整理进展：U5有界证据归并已完成；integration此前Git移除部分失败，现按维护者续授权完成残留及旧stage5分支清理，当时6个本地heads、5个注册worktree。删除前剩余文件逐项与快照／Git对象核验，删除后240项纯/fake、25＋8项离线H5和七项包检查通过，四保护SHA及pins未变。约15.4 GB临时快照仍保留；其精简、当时其他worktree处置、历史累计净空间及U6/U7项目接收在该时点仍未完成。[当前处置与收尾证据](reviews/20261113_e11_e16_u6_directory_disposition.md)记录了前次Git管理元数据未完整保全的限制，不将本次清理写成完整恢复或整轮项目接收。

2026-11-13 Isaac 夹爪专项返工补充：原 U3 的失败结论按原冻结输入保留。[后续物理对照与修复](reviews/20261113_isaac_gripper_rework_ef10e348.md)确认空载可近零闭合、碰撞方块50 mm，约53.6 mm夹持下可以抬起并保持；原45 mm就绪门阻止了Solution试举。Task现在输出v2稳定关闭读回，Solution连续稳定50 ms后尝试抬升，100 mm成功判据和物理参数不变。相同seed31／1000 horizon的正式Isaac Solution已于951步完成、lift105.254 mm，H5独立读回4755个显式子步及关闭回执成立；腕部RGB有单独430步／431帧控制对照。H5 completion仍为null，U4接收依据独立复审及同次联合证据，而非该专项自行替代主审。

2026-11-14阶段性记录：维护者批准三处停用工作树的[集中清单及具体例外](reviews/20261114_e11_e16_three_worktree_decision.md)，完成 camera、core-baseline 和旧版 clean checkout 的 Git 移除；保留主checkout与冻结archive。该时点尚待T35收敛和快照处置，后续状态见下；各次测量及恢复限制保留在[原执行结果](reviews/20261114_e11_e16_three_worktree_execution.md)。

E15 项目停门时：[E15 最终清理与独立复核](reviews/20261114_e15_final_disposition_execution.md)已完成维护者批准清单；同序含 U5 和分类日志的范围下降 29,109,616,640 B，保留两项原位例外。U4/U5 不重开；维护者已接收 [项目接收入口](reviews/20261114_e11_e16_u7_project_acceptance_entry.md)所列边界及交付 `86921c62`。旧 Git 管理元数据损失、历史精确净额 UNKNOWN、同次 completion 及不可见进程限制保留；其时 G06 尚未启动。
