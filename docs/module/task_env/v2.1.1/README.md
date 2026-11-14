# TaskEnv v2.1.1 — 协议与实施

更新时间：2026-11-14。**G01～G05 已按各自范围有界接收，5c 诊断单元 1～9 收口；当前仍在代码与项目优化，G06／G07 尚未开始。**

从[唯一当前摘要](maintenance/current-state.md)恢复接收范围、启动输入、正式入口及下一停门；工作包状态在[编排索引](maintenance/orchestration.json)，实施顺序见[优化执行安排](planning/post-5c-optimization-execution.md)及[60 项台账](planning/post-5c-code-project-optimization-diagnostic-ledger.md)。[单元 9 综合主审](maintenance/reviews/20261111_unit009_sol_5c_bounded_acceptance_b23fb3cc.md)保留原 5a／5b、四主体、同步 RGB 及跨组合的受测边界，维护者已确认功能接收。E00～E10已获维护者按各自范围接收；当前使用[E11～E16细化账本](planning/post-5c-e11-e16-remaining-ledger.md)。U4代码范围与U5有界证据归并已接收，五条完整运行采用同次联合completion口径；H5单文件不自含完整completion，旧Isaac失败保留。已批准的旧工作树／快照清单已执行，但[最新独立复核](maintenance/reviews/20261114_e11_e16_final_project_review_e3f13d72.md)确认E15剩余历史输出及快照补集尚缺最终分类和处置，整体项目接收仍OPEN；不把清单执行成功写成E11～E16全部完成。

优化及人工接收完成后才决定进入 G06；G07 的最终三 provider × 三 seed 门保留。renderer 创建时固定至 close；COM 原判据 FAIL、原 N08 FAIL、R05c NOT_REQUALIFIED、6.1 close 及历史执行偏差不改写。完整两任务 Solution 在本次优化按各自支持 provider 单 seed 验证，G07 仍保留其最终集成范围。

## 版本目标

以统一任务表示为中枢，明确 Core、physics provider adapter、render adapter 之间的协议，实际接通 MuJoCo、GeoPhys、Isaac Sim＋PhysX 的首批路线。后端和 Controller 的已准入切换可在 reset 时选择；renderer 在构建时选择并保持到 close，同一 Env 的 renderer 切换另行排期。reset 重新初始化下一轮，不迁移上一轮物理状态；不兼容固定 renderer 的 reset 组合须明确拒绝。

控制器统一、PickCube Solution 修复、窗口与同步 RGB、并行执行都服务于上述协议的真实落地。接口注册、静态通过或窗口截图不代表整条路线完成。

## 阅读入口

- [范围与七阶段路线](planning/roadmap.md)：7 个阶段、22 个 a/b/c/d 子阶段及延期事项。
- [执行顺序与验收](planning/execution-and-acceptance.md)：依赖、阶段出口、工作包、证据及分支约束。
- [阶段3前维护方案](planning/pre-stage3-environment-refactor.md)：生命周期R1与限定的核心代码／开发文档收尾已获[Sol有限接收](maintenance/reviews/20261105_pre_stage3_closeout_120min_sol_review.md)，该前置核心窗口结束；更广整理和未验证能力保留边界。Pendulum并行适配留阶段6。
- [源码 owner 与外部参考](planning/source-map-and-references.md)：当前基础、缺口、待讨论事项和官方项目链接。
- 协议实施基线：[统一任务表示](contracts/unified-task-representation.md)、[physics provider](contracts/physics-provider.md)、[render provider](contracts/render-provider.md)、[控制与反馈](contracts/control-and-feedback.md)、[生命周期与数据](contracts/lifecycle-and-data.md)。
- 阶段 Goal：[01 协议](goals/01-protocols.md)、[02 Solution](goals/02-pickcube-solution.md)、[03 后端](goals/03-backends.md)、[04 控制](goals/04-control.md)、[05 渲染](goals/05-rendering.md)、[06 并行](goals/06-parallel.md)、[07 集成](goals/07-integration.md)。
- [API 迁移入口](api/README.md)、[指南交付要求](guides/README.md)、[单一能力矩阵](capabilities/README.md)。
- [当前摘要](maintenance/current-state.md)、[恢复页及历史](maintenance/recovery.md)、[编排索引](maintenance/orchestration.json)、[规划初建收据](maintenance/20261103_documentation_receipt.md)。

## 规划来源及历史能力

规划输入 Core：`develop@fd03817c9f6ef8ce9fd68c1db30125efda68e1c8`；GeoPhys pin：`67da1165149486d3ae3e779c13ce31af49e17d50`。本地 `refs/tags/v2.1.0` 指向该 Core；本轮未查询远端或 GitHub Release，不能从旧候选措辞推断当前发布状态。

规划初建时的实现与证据按 [v2.1.0 API](../v2.1.0/api/public-api.md)和[有界能力矩阵](../v2.1.0/capabilities/capability-matrix.json)理解。selected 渲染仍只准入 state-only；R3 主要输出位置参考；LIBERO 有限定的力矩＋位置混合控制。G02/2a 与 2b 有当前 MuJoCo 原生证据；PickCube seed32 有效运行但任务失败。阶段2接收范围为seed31成功实现、受影响Nut回归及可复现参考，不将原2b扩展包的未过门改为PASS。该段记述旧规划时点，其余阶段实际状态以编排索引及恢复页为准。

F06 历史 9/9 runtime-valid、0/9 task-success，R07 A123 的有界接收与例外、F05 未决研究门均保留。不将 v2.1.1 的目标或后续结果改写进冻结证据。

## G02 历史成功参考

MuJoCo PickCube seed31 和 NutAssembly seed19 的任务、Solution、runtime 与独立 HDF5 读回均通过；PickCube seed32 的 runtime/记录有效，但在 horizon 1000 时任务与 Solution 失败。GeoPhys PickCube 在执行边界时间 guard 抛出 stale execution time；Isaac delivery 文件校验通过，但 GPU admission 不稳定，本包未启动 Isaac App。详见 [2b 收尾报告](maintenance/reviews/20261104_2b_closeout.md) 与 [恢复页](maintenance/recovery.md)。2c文档封存已由Sol有界接收，该阶段2收尾记录的时点早于阶段3执行。

## 文档边界

本目录拥有 v2.1.1 的规划及已确认语义协议；v2.1.0 保留来源版本行为。每项协议只在对应 `contracts/` 页面维护，Goal 引用它并记录具体实施与验收。实现后再更新 API、指南和矩阵，不能把设计基线当成现有可调用 API。系统归属仍服从[架构](../../../global/architecture.md)与[ownership](../../../global/ownership.md)。

## 本体重力补偿（有界接收）

维护者已授权实施默认关闭的 [Panda 本体重力补偿](guides/panda-gravity-compensation.md)。当前仅 MuJoCo CPU 进程内 selected PickCube／Nut 路线有界实现；原 3b 默认关闭的 N08 历史失败保留，其他 provider 的开启请求不支持。
