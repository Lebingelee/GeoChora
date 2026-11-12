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

## 正式入口及当前实施

截至实施输入 `f691d32e`，四个正式任务使用 `task_env.make_env`：`pick-cube-p16-reference-v1`、`nut-assembly-outcome-reference-v1`、`pendulum-v1`、`two-wheel-balance-v1`。mapping 与 YAML 进入共同配置解析及构建请求；当前具体支持的 Robot、Controller 和 provider 组合以配置准入及相应证据为准。Git 当前 HEAD 以实际工作树为准，不把此输入当作实时 HEAD。

| 事件 | 当前状态 | 实际进展和剩余边界 |
| --- | --- | --- |
| E00 基线与度量 | 基线已记录；持续对账 | 输入身份、保护文件和项目统计有记录；当前摘要及实施记录需随变化维护。 |
| E01 入口与配置 | 实施中 | 四任务共同解析、选择 Robot 和构建；历史 Position candidate UID、输入与专属构建已退休。旧 component 纯构建属于其他保留 caller，不能由此称所有入口均已统一；PickCube 的有效物理能力仍有任务内 candidate 文件待归位。 |
| E02 模块与主体 | 实施中 | 正式入口选一次 Robot，Task、source 与 Controller 使用该声明；四主体已有受测的主体与绑定链。装配／一体 source 的不同物化路径和 Task 内部分构造职责仍需收敛，不能将共同运行视图当作完整统一。 |
| E03 Env 生命周期 | 实施中 | reset、资源清理和 source 快照已部分归共同 owner；构造、故障及剩余专用状态仍需逐路径核对。 |
| E04 控制与推进 | 实施中 | 正式受测动作进入共同场景提交；Panda effort 已接入主体／通道匹配，Position 投影由 Controller 提供。其他已支持序列、故障、模型及 provider／renderer 受影响路径仍需按实际代码和证据核对。 |

本版本诊断放在 `task_env/diagnostics/tasks/v2.1.1/`。最近一次代码输入下，210 项版本诊断通过；PickCube 物理任务绑定收敛及受影响短程证据见[实施记录 6.150](../planning/post-5c-optimization-execution.md#6150-pickcube-物理任务绑定收敛)，此前 PickCube effort 职责归位及受影响短程证据见[实施记录 6.149](../planning/post-5c-optimization-execution.md#6149-pickcube-effort-控制与任务语义归位)，此前共同 reset 重建的受影响短程证据见[实施记录 6.148](../planning/post-5c-optimization-execution.md#6148-共同-reset-重建与选择身份)，此前两个普通 Robot 的 source 身份和受影响短程证据见[实施记录 6.147](../planning/post-5c-optimization-execution.md#6147-普通-robot-source-身份与当前状态对账)，此前四任务、一体／装配主体及 GeoPhys PickCube R1 的受影响短程提交证据见[实施记录 6.146](../planning/post-5c-optimization-execution.md#6146-移除-selected-控制提交旁路)。该记录中的 Solution 只验证单步；Isaac 原生、renderer 和完整 Solution 不能由此推断通过。各批输入、限制和历史失败保留在[执行记录](../planning/post-5c-optimization-execution.md#6-e00e04-实施记录)及对应原始证据中，不能把不同输入的结果合并为最终生产验收。

O5 仍需完成两任务各自公开支持 provider 的单 seed 完整 Solution 与同次记录读回，至少 MuJoCo 任务成功；O6 完成逐项主审和代码优化接收后才进入 O7 项目清理。规划 [capability-matrix.json](../capabilities/capability-matrix.json) 仍须按实际证据逐格对账；本地成果尚未合入 develop／main，未发布。
