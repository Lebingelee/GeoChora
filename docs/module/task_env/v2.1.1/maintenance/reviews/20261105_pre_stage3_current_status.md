# 阶段3前维护：当前证据与待复审项

2026-11-05；核心源码检查点 `b6ce23727f1b2cd21da15758785b59448eb9ceb0`。本轮具体结论及限制见[120分钟收尾报告](20261105_pre_stage3_closeout_120min_001.md)。整体维护仍为 **PARTIAL、待 Sol 复审**，阶段 3 未开始。本页汇总现状；逐次结果、失败和资源记录保留在[续作证据历史](20261105_pre_stage3_renewed_evidence_history.md)及[物理验证记录](20261105_pre_stage3_resumed_physical_checks.md)，不能将其重标到其他源码。

| 门 | 当前状态 | 证据与剩余边界 |
| --- | --- | --- |
| G0 输入与资源 | **PARTIAL** | 两项保护文件和 GeoPhys／Menagerie pin 与原快照一致。物理步保守预留 **287107／300000**；新离线墙时累计 **481.391／3000 秒**（含本轮 64.109 秒 pytest supervisor 墙时），原可见约 1464 秒保留历史、不计新预算。两个维护目录当前表观总量约 **1.31 GiB／2 GiB**，见物理验证记录；历史总写入量未重新估算。 |
| G1 代码职责 | **PARTIAL，待复审** | 三个旧任务经公共 factory 构造统一 scalar Env，`BaseTaskEnv` 为同对象兼容出口；PickCube／Nut 各四个业务文件。外部 Solution 使用 `act → env.step(action) → observe`，`step_expert()` 仅受限兼容。控制器准入、部分 reset 和录制逻辑已归现有 owner；`SelectedReferenceEnv` 在核对基线仍有 3419 行及多路线编排，[剩余职责清单](20261105_reference_env_remaining_owners.md)列出具体缺口。R05b runtime 物化不要求 Nut Solution 实例，普通 reset 无内部 Solution，外部 caller 动作已有无引擎测试；精确类型、配置及来源匹配由 Nut task binding 检查。旧 Env-driven Solution 仅按需创建，作为受限兼容。 |
| G2 功能与身份 | **PARTIAL** | `5a04140a` 的 PickCube／Nut MuJoCo CPU 代表运行及同次独立 reader 均通过，分别 960／2377 transitions；本轮仅 Nut 身份与代码受影响，`cf425acc` 的 Nut 代表运行及同次独立 reader 再次通过 2377 transitions；其后源码变动仅在 R05b 专用构造与按需兼容分支及测试，不改变本次 MuJoCo 普通执行路径，运行身份不重标。`59fba768` 无引擎组合 270 passed、4 deselected，`32162885` R05b 无引擎检查 20 passed、1 deselected；[证据历史](20261105_pre_stage3_renewed_evidence_history.md)包含实际源码身份。三个 classic 的 `8b3c8d93` CPU 单步结果保留原身份；未启动 Isaac／GPU，未证明其他 provider、D0 或 Qualification。 |
| G3 文档与启动 | **PARTIAL** | [安装与启动指南](../../guides/installation-and-start.md)和[任务开发指南](../../../../../../task_env/doc/自定义任务构建指南.md)描述公共入口；显式路径启动器的 classic CPU 单步已运行。`0b3e2a53` 及本次状态页整理工作树的完整文档检查均为 0 errors、0 stale paths、96 条历史链接问题，原始记录位于 ignored `renewed-doc-audit-0b3e2a53/` 和 `renewed-doc-audit-current-summary/`。全新安装及所有适用入口尚未验证。 |
| G4 证据与清理 | **PARTIAL** | 同次 H5、独立 reader、失败和锁收据保留；核对 SHA 后删除已复制的测试资产，Position 测试现共享一份验证快照并自动清理。旧 FULL 诊断缺失的任务实现已明确拒绝；其余历史诊断引用仍需逐项判定，不能把旧证据重标。 |
| G5 交付 | **PARTIAL** | 本地提交与资源账本已保存；完成剩余职责整理和必要检查后固定 HEAD、释放 writer，由维护者按既有流程转交 Sol。不得预填 Sol 决定或更改阶段 3 的 PLANNED 状态。 |

本轮按规划第2.5节完成有界收尾并交 Sol 复审；保留 R05b Env 兼容生命周期和其他明确未验证路线的实际边界，不把历史诊断或所有环境分支整理视为本轮已完成。
