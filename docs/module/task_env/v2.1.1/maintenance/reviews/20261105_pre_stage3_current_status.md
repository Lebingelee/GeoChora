# 阶段3前维护：当前证据与待复审项

2026-11-05；核对基线 `0b3e2a53d3c458c21fd7b58da9dd8427c16c135f`。整体维护仍为 **PARTIAL、待 Sol 复审**，阶段 3 未开始。本页汇总现状；逐次结果、失败和资源记录保留在[续作证据历史](20261105_pre_stage3_renewed_evidence_history.md)及[物理验证记录](20261105_pre_stage3_resumed_physical_checks.md)，不能将其重标到其他源码。

| 门 | 当前状态 | 证据与剩余边界 |
| --- | --- | --- |
| G0 输入与资源 | **PARTIAL** | 两项保护文件和 GeoPhys／Menagerie pin 与原快照一致。物理步保守预留 **257107／300000**；新离线墙时累计 **417.282／3000 秒**，原可见约 1464 秒保留历史、不计新预算。两个维护目录当前表观总量约 **1.31 GiB／2 GiB**，见物理验证记录；历史总写入量未重新估算。 |
| G1 代码职责 | **PARTIAL，待复审** | 三个旧任务经公共 factory 构造统一 scalar Env，`BaseTaskEnv` 为同对象兼容出口；PickCube／Nut 各四个业务文件。外部 Solution 使用 `act → env.step(action) → observe`，`step_expert()` 仅受限兼容。控制器准入、部分 reset 和录制逻辑已归现有 owner；`SelectedReferenceEnv` 在核对基线仍有 3419 行及多路线编排，[剩余职责清单](20261105_reference_env_remaining_owners.md)列出具体缺口。R05b 原生反馈物化仍依赖 Nut Solution 精确类型和身份，不能宣称所有路线解耦。 |
| G2 功能与身份 | **PARTIAL** | `5a04140a` 的 PickCube／Nut MuJoCo CPU 代表运行及同次独立 reader 均通过，分别 960／2377 transitions；其后至核对基线仅文档变更。`59fba768` 无引擎组合 270 passed、4 deselected，`32162885` R05b 无引擎检查 20 passed、1 deselected；[证据历史](20261105_pre_stage3_renewed_evidence_history.md)包含实际源码身份。三个 classic 的 `8b3c8d93` CPU 单步结果保留原身份；未启动 Isaac／GPU，未证明其他 provider、D0 或 Qualification。 |
| G3 文档与启动 | **PARTIAL** | [安装与启动指南](../../guides/installation-and-start.md)和[任务开发指南](../../../../../../task_env/doc/自定义任务构建指南.md)描述公共入口；显式路径启动器的 classic CPU 单步已运行。`0b3e2a53` 及本次状态页整理工作树的完整文档检查均为 0 errors、0 stale paths、96 条历史链接问题，原始记录位于 ignored `renewed-doc-audit-0b3e2a53/` 和 `renewed-doc-audit-current-summary/`。全新安装及所有适用入口尚未验证。 |
| G4 证据与清理 | **PARTIAL** | 同次 H5、独立 reader、失败和锁收据保留；核对 SHA 后删除已复制的测试资产，Position 测试现共享一份验证快照并自动清理。旧 FULL 诊断缺失的任务实现已明确拒绝；其余历史诊断引用仍需逐项判定，不能把旧证据重标。 |
| G5 交付 | **PARTIAL** | 本地提交与资源账本已保存；完成剩余职责整理和必要检查后固定 HEAD、释放 writer，由维护者按既有流程转交 Sol。不得预填 Sol 决定或更改阶段 3 的 PLANNED 状态。 |

后续继续处理 R05b 的冻结准入与外部 Solution 职责、环境类剩余路线接线、历史诊断和新手入口；保持来源、控制反馈与故障拒绝边界。最终提交后再次核对文档、保护项、版本 pin 和资源释放，并将实际源码与验证交 Sol 独立复审。
