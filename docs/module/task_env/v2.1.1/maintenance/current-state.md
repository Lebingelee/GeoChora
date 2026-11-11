# v2.1.1 当前状态

更新时间：2026-11-11。本文是版本的人工可读当前摘要；工作包、attempt 和历史记录由[编排索引](orchestration.json)维护，逐项优化范围由[优化台账](../planning/post-5c-code-project-optimization-diagnostic-ledger.md)维护。

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

## 正式入口及下一交付

当前正式公开工厂为 `task_env.make_env`。PickCube／Nut 正式 UID 为 `pick-cube-p16-reference-v1`／`nut-assembly-outcome-reference-v1`；两简单主体使用各自注册 UID。它们当前的配置与构建协议尚未全部归并：candidate 仍是部分受测能力的入口，不能把优化目标写成已实现的新 API。

下一实施范围是 O1：配置字段归属／覆盖顺序、正式构建请求、旧 UID／factory 的迁移表；随后按 O2～O4 归位生命周期、source／renderer／observation 和 Recorder／caller。O5 必须完成两任务各自公开支持 provider 的单 seed 完整 Solution 与同次记录读回，至少 MuJoCo 任务成功；O6 逐项主审后才进入 O7 的项目清理。详见执行计划及原台账。

规划 [capability-matrix.json](../capabilities/capability-matrix.json) 尚待按实际证据逐格对账，旧 `NOT_RUN` 目标不能替代最新主审判断，也不能仅凭阶段接收批量改成 PASS。当前本地成果尚未合入 develop／main，未发布。

## E00～E04 当前实施

维护者已直接要求本会话实施 E00～E04，输入 `21577d32`，当前 chat 单 writer。共同构造和旧物理 UID 翻译之后，正式 PickCube（含物理配置）／NutAssembly／Pendulum／双轮车已从本次 Artifact 构造 TaskDefinition，观察调用共同语义 lifecycle，reset 后重新绑定。数组与具名 canonical state 各保留真实表示；Gym typed info 保留，Solution callbacks 使用公共 metadata 值投影。已准入的普通 native 路线安装现有 live source／Controller interval binding，移除安装处的单一 R05c profile 名称分流，原严格准入仍保留。本批生产代码净增 122 行，累计净增 154 行；tracked 文件数不变。152 个不同纯合同节点及五条 MuJoCo CPU 交集通过；累计受监督 36 次／290 个可观测子步，加前序 150 保守计费为 440。四次本批失败和原始拒绝均保留，未称完整 Solution 成功。配置 codec、剩余主体／registry／reset／action／clock／部署审计继续；E00～E04 未完成。详细证据与限制见[实施记录第 6 节](../planning/post-5c-optimization-execution.md#6-e00e04-实施记录)，不提前签收或启动 G06。

第六批将 Isaac source 首次重复编译收敛到共同构造，并让实际 physical execution 提供动作合同；Isaac 正式配置完成两次 reset／非零 step／三次 RGB 与独立读回。首次预检失败及受限修复、资源账和 SDK 退订诊断均保留。生产累计净增 182 行，文件数不变；其余 E00～E04 仍待逐项完成，细节见[第六批记录](../planning/post-5c-optimization-execution.md#65-第六批编译后的-controller-合同与-isaac-正式入口复验)。

第七批修复隔离 worker 的 source-bound 控制提交：正式 PickCube 在 MuJoCo CPU 和 GeoPhys CPU 两条受测路线均完成 reset／单 interval／第二次 reset／close。失败、未观测子步的保守计费和一次无锁资产解析的偏差保留；累计生产净增 228 行、tracked 文件数不变。见[第七批记录](../planning/post-5c-optimization-execution.md#66-第七批隔离-worker-的状态边界与控制归属)。
