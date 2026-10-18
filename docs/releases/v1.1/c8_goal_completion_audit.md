# S5-C8 原 Goal 完成审计 — 2026-10-18

**RELEASE_CANDIDATE — NOT_PUBLISHED**

本审计对应原 Goal《Final Workspace Retirement, Evidence Preservation & Phase 2.0 Closure Review》，保持原范围，不新设 C9。维护者于 2026-10-18 明确接受下述残余项与证据限制，并要求完成 C8 收尾。闭环状态为 MAINTAINER_ACCEPTED_WITH_RETAINED_EXCEPTIONS，不等于所有 L3 字节都已删除或 release READY。

## 按原章节检查

| 原章节 | 结论与权威证据 |
|---|---|
| 0–1 Mission / canonical baseline | 同一 C8 工作流；本轮 `git fetch public --prune` 成功。public/develop 仍为 `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`。没有远端写入。 |
| 2 L1/L2 baseline | 原始保护清单、后续版本化 L1 和当前 L2 22/22 保留；本轮大小/SHA-256 通过，L2 24,563,669 字节。L1 文档变更为有 Git diff 的状态同步，不覆盖旧 baseline。 |
| 3 governance preservation | C3–C8 元数据、本地提交、原始批准清单与后续观察收据已保留。部分精确文件级清单仍在 ignored workspace；独立/远端保留未验证，不冒称已公开。 |
| 4 P1.8 variance | C8 LIVE 清单与 C7 差异报告保留；3,298 common、278 原缺失、85 live-only 分开记录。未重写原 archive manifest；C1 3,382 条普通路径现已消失，1 bundle 保留。 |
| 5 historical records | `evidence/historical_retirement/copy_index.json` 中 37 份、366,744 字节原记录 SHA-256 本轮通过；没有新的 Human/Judge/FULL 决策。 |
| 6 irreversible loss | [最终报告](c8_manual_cleanup_final_report.md)及原 C8 loss assessment 保留源载体、原始数据与恢复限制；不将 796 GeoPhys-named 文件误称为 796 个源码快照。独立副本未验证，哈希不能恢复缺失字节。 |
| 7 dependencies | 已知当前 TaskEnv/L1/L2 交集受保护；external PhysPi/Skill consumer 调查仍非穷尽。522 原有 unresolved/protected holdout 保留，未将未知自动视为无依赖。 |
| 8–10 reuse / worktrees / exact manifests | 复用 A/B/C1/C2 原清单、保持批准 SHA-256；分开普通路径、worktree、holdout。B 内层 primary submodule 无适用的原非强制移除方法，6,619 条仍保留，未手工递归删除。 |
| 11 authorization | 四份精确批准哈希与 C1/C2 永久历史损失接受已记录；不重复请求既有批准，不推导额外删除或备份豁免。 |
| 12–13 execution / receipts | **执行覆盖部分完成；残余范围与证据限制已由维护者接受收尾**。助手执行在首次 unlink 前停止。维护者后来手工处理，监测证实 65,826 普通路径全部消失；没有用户逐项 unlink 日志，不能补造原要求的每次尝试/结果收据，也无法追溯证明所有手工删除即时安全条件。 |
| 14 L1/L2 after cleanup | PASS_LOCAL_INTEGRITY。当前文档有意迁移、旧内容保留 Git；L2 22/22 原字节未更换。Capability Matrix SHA-256 不变。 |
| 15 cleanup result | 路径缺失、保留项、worktree 注册和 du/df 前后观测记录齐备。Workspace 观测减少 68.317 GiB，但非逐项精确归因。缺少用户执行/转移记录，不能证明每个文件字节均已销毁或每个 block 均因该次 unlink 释放。 |
| 16 final source validation | 清理后 9 项轻量 provider-free 检查通过（7 in 1.51s，2 in 0.81s）；本轮复核 Gitlink 对象、执行源码无 diff、115 个恢复引用与 55 个当前文档链接。未重复 native campaigns。 |
| 17 retention policy | L1/L2 保留、精确 L3 已批准退休范围有效；仅这些范围，非通用授权。full-workspace backup 与独立 L2 backup 均未获豁免或满足。 |
| 18 RC consistency | README、readiness、known limitations、version policy、evidence index、retrospective、backup manifest 已同步手工清理观察。早期执行停止 JSON 与 C5/C6 子节明确为历史状态。 |
| 19–21 original goals / future direction | [回顾矩阵](p2_0_retrospective.md)与[最终报告](c8_manual_cleanup_final_report.md)区分 P2.0-A/B、S0–S5、实现/有界测试/资格/未来方向，不声称完成全部 Phase II。 |
| 22 A–K acceptance | A–F/I/J 的元数据与审计证据具备；G 的 B worktree 保留和逐项日志缺失属维护者明确接受的收尾例外，未被伪标为完整删除 PASS；H 的保护核验通过，空间仅按观测陈述；K 的 readiness 报告完成，不等于发布 READY。 |
| 23 final deliverables | 原要求 17 项交付有报告/清单/引用映射；实际 deletion receipts 仅有助手停止收据及用户操作后的观察，必须保留该不足，不能把它替换为伪造成功收据。 |

## 交付入口

- [最终交付、空间观测、损失说明与后续 P2.x](c8_manual_cleanup_final_report.md)
- [当前 release gate matrix](release_readiness.md)
- [当前保留/备份状态及历史快照](backup_manifest.json)
- [L2 精确列表与历史元数据入口](evidence/README.md)
- [原始助手停止收据](evidence/retirement/c8_execution_receipt_20261018.json)
- [手工处理后机器可读观察](evidence/retirement/c8_manual_cleanup_observation_20261018.json)
- [原 P2.0 goal-to-implementation 矩阵](p2_0_retrospective.md)

详细本轮核验结果位于本地 ignored `workspace/maintenance/p2_0_s5_c8_manual_cleanup/final_goal_integrity.json`；9 项 post-cleanup 测试原日志在 `workspace/maintenance/p2_0_s5_c8_20261018_execution/post_manual_cleanup_tests*.log` 和 JSON。它们是本地证据，不是独立备份。

## 剩余外部条件

1. 存储历史风险未解除；维护者后续 SMART 刷新实验证明近期固定增量有可重复查询来源。单独计数增长不再作为低 I/O 阻塞，当前策略见 [修订判据](c8_storage_monitoring_revision.md)。新真实错误仍触发停止。
2. B worktree 的原非强制操作不可执行；若仍要求退休，需要另行确认合规方法及范围，禁止擅自 force/deinit/递归删除。
3. 维护者已于 2026-10-18 明确确认没有保存逐文件日志；该项收据缺口已确认，缺失的过去事件无法通过后验扫描恢复。
4. 备份、controller Option B 风险接受、capability matrix、L1 远端集成与正式发布各有独立门槛。C8 不授权自动满足它们。

这些条件不再触发新一轮常规清理审查。维护者明确接受保留 worktree/holdout，以路径缺失、L1/L2 哈希和空间观测作为手工清理结果，并接受逐文件日志未保存的限制；按该已批准验收边界完成 C8。原始不足继续如实披露。正式发布、main、tag 与远端 push 均未执行。

## 原要求 17 项最终交付入口与缺口

| 项 | 交付物与实际状态 |
|---|---|
| 1 执行与批准收据 | [原始授权/停止收据](evidence/retirement/c8_execution_receipt_20261018.json) + [后验观察](evidence/retirement/c8_manual_cleanup_observation_20261018.json)。不将后者称为用户逐次 unlink 收据。 |
| 2 L1/L2 preservation manifest | `workspace/maintenance/p2_0_s5_c8_manual_cleanup/final_current_l1_l2_manifest.json`；历史 baseline、后续迁移与 Git 提交共同保留，L2 精确列表见 [Evidence index](evidence/README.md)。本地 ignored 清单，尚非远端保存。 |
| 3 P1.8 live reconciliation | C8 原目录 `p1_8_manifest_reconciliation.json`、`p1_8_live_filesystem_manifest.json` 与其 SHA-256 sidecar；[历史元数据 index](evidence/historical_retirement/copy_index.json)保留原载体身份。 |
| 4 历史决策 metadata index | [37 条 exact-copy index](evidence/historical_retirement/copy_index.json)，本轮逐条 SHA-256 核验。 |
| 5 不可恢复损失报告 | [最终报告](c8_manual_cleanup_final_report.md) + 原 C8 C1/C2 清单 `loss_summary` / 风险字段；源码载体和历史结果不可恢复风险已确认。 |
| 6 A/B/C1/C2 精确清单 | `workspace/maintenance/p2_0_s5_c8_20261017/batch_{a_l3a,b_l3b,c1_p1_8,c2_l3c}_final.json`（花括号仅说明四个原文件名，不是执行命令）；四个 SHA-256 绑定于 [原批准收据](evidence/retirement/c8_execution_receipt_20261018.json)。 |
| 7 各批批准身份 | 同上收据引用维护者对四个哈希的明确批准及 C1/C2 损失接受；不包含额外删除/备份豁免/发布授权。 |
| 8 实际删除收据 | **缺口确认**：维护者明确没有保存逐文件日志。仅保留助手停止记录、监测 `events.jsonl` 和最终 path-absence 观察；不得伪造历史执行过程。 |
| 9 清理后 L1/L2 | 最终 snapshot + 本轮 `final_goal_integrity.json`；旧 snapshot 不因文档迁移而改写。L2 22/22 原哈希通过。 |
| 10 GiB / 残余 Workspace | [观察收据](evidence/retirement/c8_manual_cleanup_observation_20261018.json)：前后 Workspace allocation 差 68.317 GiB，残余观测 2,815,557,632 字节；非逐项 unlink 精确归因。 |
| 11 repository/worktree | [最终报告](c8_manual_cleanup_final_report.md)记录 protected refs；注册 worktree 未移除、522 holds 保留，未执行 force/deinit/共享对象删除。 |
| 12 retention/readiness | [readiness](release_readiness.md)、[backup manifest](backup_manifest.json)、[policy](release_scope_and_version_policy.md)；当前状态已同步，历史 snapshot 明确标识。 |
| 13 P2.0-A 完成度 | [goal-to-implementation 矩阵](p2_0_retrospective.md)：部分完成，worktree、恢复与存储/备份限制保留。 |
| 14 P2.0-B 完成度 | 同矩阵：选定 Core consolidation 批准范围实现完成，release 尚未发布，不冒称全部 Phase II。 |
| 15 原 Goal 实现映射 | [retrospective](p2_0_retrospective.md) + 本文逐章检查，含原目标、实现、提交、测试和限制。 |
| 16 后续 Phase II/P2.x | [最终报告](c8_manual_cleanup_final_report.md)和 retrospective 的 benchmark/native-vs-TaskEnv/Harness、轨迹与 PhysPi 边界研究交接；未在 C8 实现。 |
| 17 v1.1.0 publication blockers | [release readiness](release_readiness.md)：独立备份、存储、controller 风险接受、能力矩阵、L1 远端保留和正式授权分别保留。 |

2026-10-18 补充发现与修复：当前 source recovery manifest 的三个测试/help 收据原路径已经消失。它们并未作为字节丢失处理，因为预先保留的同盘副本分别按原保存记录验证 SHA-256 一致。当前 lookup 已迁移到原 C8 preserved 路径，原路径/哈希/大小另行留档；没有重新生成测试结果。该修复不构成独立备份。

## 最终维护者验收 — 2026-10-18

维护者原回复：**“接受上述残余项和证据限制，完成 C8 收尾”**。该回复对应的完整具体条件是：

- 保留 B 注册 worktree 及全部 holdout，不执行额外删除。
- 65,826 个批准普通路径缺失、L1/L2 哈希和空间观测作为手工清理结果；逐文件日志未保存，删除过程无法追溯验证。
- 该验收不豁免独立备份，不授权 push、main 修改、tag 或发布。

因此 C8 Goal 在这项明确批准的最终验收边界下可以完成；不能描述为“原全部 L3 清理无例外成功”，也不能把日志缺口变成虚构的删除记录。所有尚未获授权的 release 动作继续独立受阻。本轮与原 Goal 一致交付最终残余风险报告，不创建 C9。
