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
| 当前改动 | E00～E04 已完成实施、基线独立主审及主审余项修复，并于 2026-11-12 获维护者统一接收。当前生产 `912416e6`，精确验证输入及限制见执行计划第 6 节；不沿用启动表充当实时锁 |

保护输入为 `MUJOCO_LOG.TXT`、2026-10-30 runtime route handoff、stage3 gravity proposal 和用户优化台账。精确大小／SHA-256 与原工作树状态在 ignored [输入快照](../../../../../workspace/maintenance/v211_post5c_optimization_o0_20261111_001/input-snapshot.json)。没有将它们加入本轮提交，也没有清理原始输出、改动 pins、merge／push／tag。

## 已接收的能力与边界

- G01 协议基线；G02 MuJoCo PickCube 成功参考及 Nut 回归；G03 路由、真实执行与 reset 重建；G04 typed 控制／贡献／反馈／Controller reset，分别按原主审范围保留。
- 一体 Panda、装配 Panda、Pendulum、双轮车有共同主体／Assembly／Controller／场景 interval 的受测链；不声称四主体都在最终生产 HEAD 重新运行。
- Pendulum／双轮车的 MuJoCo CPU、GeoPhys CPU 和 Isaac PhysX CUDA 短程路线限各自受测资产。三条首批原生窗口／离屏与 task RGB 按主审及影响复用。
- 最新 Isaac task RGB 已覆盖 reset、非零 step、二次 reset 及 close；GeoPhys CPU physics × MuJoCo renderer-only 已有真实状态映射和零额外物理推进证据。依据见[单元 7／8 主审](reviews/20261111_unit007_008_sol_review_a53bf19d.md)与单元 9 综合主审。
- renderer 创建时选定并保持到 close；通用动态切换、任意装配树、任意组合、通用闭环及完整 batch 能力仍不属于已接收结论。颜色／挂载／source 限制继续适用。

COM 原严格判据失败、维护者有界采纳、原 N08 FAIL、R05c `NOT_REQUALIFIED`、Isaac 6.1 close 限制及历史执行偏差保留；不借本次状态更新转移资格或重开 5c。

## 正式入口及当前实施

当前生产为 `912416e6`；四个正式任务使用 `task_env.make_env`：`pick-cube-p16-reference-v1`、`nut-assembly-outcome-reference-v1`、`pendulum-v1`、`two-wheel-balance-v1`。mapping 与 YAML 进入共同配置解析及构建请求；具体支持的 Robot、Controller 和 provider 组合以配置准入及相应证据为准。基线生产 `76536d2a` 已有[独立主审建议](reviews/20261112_e00_e04_independent_review_76536d2a.md)，后续主审余项在 `912416e6` 修复并自检；维护者于本次对话统一接收 E00～E04。后续自检与原独立主审仍按各自时点保留。

| 事件 | 当前状态 | 实际进展和剩余边界 |
| --- | --- | --- |
| E00 基线与度量 | 维护者已接收 | 输入/证据/保护/统计已核对；旧 dirty 已完整保全，再恢复执行记录角色及有效索引。 |
| E01 入口与配置 | 维护者已接收 | 四任务共用正式解析与请求；Position candidate 和两个旧 PickCube physical UID 已退休；范围外 component 不进入这四条正式链。 |
| E02 模块与主体 | 维护者已接收 | 共同 builder 消费 source、主体和 Controller 阶段；复用 CompiledReferenceTaskV1 与具名 context，去除 20 种阶段临时字典键；合法 typed lowerer 差异保留。 |
| E03 Env 生命周期 | 维护者已接收 | 共同 reset/fault/close、source lease/cache、worker/App/camera owner 已按受影响范围核对；保留真实失败注入未测边界。 |
| E04 控制与推进 | 维护者已接收 | 当前支持输入进入共同 dispatcher/submission；兼容提案以显式投影和类型策略决定行为，错误阶段不再决定控制路径。 |

本版本诊断集中在 `task_env/diagnostics/tasks/v2.1.1/`。E00～E04 主审余项修复轮的 217 项受影响 source/caller 检查通过，另有 76 项纯/fake 精确检查通过（与前者有重叠，不相加）；六项 USD 检查为真实 delivery 的离线构造，不启动 Isaac App。MuJoCo 七条短程共 75 个显式子步，GeoPhys effort/Pendulum 两条短程通过；加上测试中的 40 个，本轮共 115 个显式 MuJoCo 子步。冻结输入为 `e25f37c5` 加保存的生产 patch，与 `912416e6` 对应生产字节相同，运行的 source_revision 仍为 e25，不改称提交后重跑。详情见[按模块压缩的实施记录](../planning/post-5c-optimization-execution.md#6-e00e04-实施记录)。renderer 未重跑，完整 Solution 仍留 E13；旧逐批记录从历史提交和原始输出恢复。

O5 仍需完成两任务各自公开支持 provider 的单 seed 完整 Solution 与同次记录读回，至少 MuJoCo 任务成功；O6 完成逐项主审和代码优化接收后才进入 O7 项目清理。规划 [capability-matrix.json](../capabilities/capability-matrix.json) 仍须按实际证据逐格对账；本地成果尚未合入 develop／main，未发布。

## 当前实施范围：E05～E10（U1～U2 已实施）

维护者已决定准备 E05 资产/source、E06 physics adapter、E07 状态/相机、E08 renderer、E09 Task 精简和 E10 Recorder/replay。当前以[专用剩余账本](../planning/post-5c-e05-e10-remaining-ledger.md)和[实施 Goal](../planning/post-5c-e05-e10-goal.md)作为后续执行入口：六个实施单元及一个集中复验/对账单元，共 40 个闭合检查点。E00～E04 不再重开；U1～U2 已实施，结果及边界见专用账本第 13 节，U3 待实施。完整 Solution 继续归 E13，整体代码/项目优化尚未接收。
