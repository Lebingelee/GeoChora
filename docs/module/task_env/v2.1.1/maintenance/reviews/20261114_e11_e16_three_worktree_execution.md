# E11～E16 三处停用工作树清理结果

维护者确认[集中清单](20261114_e11_e16_three_worktree_decision.md)及其中的两项例外后，于 2026-11-14 执行。三处均已移除，冻结 archive 保留；不由本记录宣布 U7 项目接收。

| 候选 | 实际操作 | 结果 |
| --- | --- | --- |
| `/home/lly/.codex/worktrees/phase-ii-01-camera/Geochora` | 对清单中身份核验通过的 61 个用户自有只读目录补写权限；一次 `git worktree remove --force` | Git 退出 0；工作树及对应 Git 管理目录均已不存在。60 个目录位于获明确例外的第三方 source 快照。 |
| `/home/lly/Program_Files/Geochora/workspace/maintenance/geophys_upstream_reset_20261022_001/core-baseline` | 不跟随两条外链，移除链接项并建立未初始化 gitlink 空目录；一次普通 `git worktree remove` | Git 退出 0；工作树及管理目录均已不存在，两外部目标根设备／inode 与之前一致。 |
| `/home/lly/Program_Files/Geochora/workspace/maintenance/p2_0_v1_1_clean_checkout_20261017` | 一次 `git worktree remove --force` | Git 退出 0；工作树及对应 Git 管理目录均已不存在。 |

操作期间持有同一共享锁，变更前复核注册、HEAD、活动、挂载、受保护文件、pins、U5 对象、保留副本和路径身份。可见进程扫描未见目标命中；`/proc` 有权限拒绝，不能证明不可见或非合作进程均不存在。未运行 `submodule deinit`，未跟随外部符号链接清理目标。camera 的外部硬链接保留路径、设备／inode／大小及 SHA 未变，链接数由 2 减至 1；可预期的 ctime 变化不作为内容变化。

[core 执行日志](../../../../../../workspace/maintenance/v211_three_worktree_cleanup_20261114_001/core-events.jsonl)与[其余两处执行日志](../../../../../../workspace/maintenance/v211_three_worktree_cleanup_20261114_001/remaining-events.jsonl)记录意图、结果、操作后核查和锁释放；[独立复核](../../../../../../workspace/maintenance/v211_e11_e16_independent_review_0506ae26/u7-three-worktree-removal-execution-review.md)核对 61 次权限变更、三次 Git 命令及日志无未闭合意图。原 integration 的 Git 管理元数据此前部分损失的限制仍保留，本次成功不使该历史缺口恢复。

删除后仅余主 checkout 与原锁定 archive 两个注册工作树，六个本地 heads 和四个 tags 仍在；共享 Git config 的 SHA、四保护输入 SHA 和 GeoPhys／Menagerie pins 与执行前一致。U5 的 1,370 个内容对象、六份冻结索引及引用在操作前持锁重算；操作后受守卫的 [240 项纯／fake](../../../../../../workspace/maintenance/v211_three_worktree_cleanup_20261114_001/post-cleanup-pure-result.json)和[七项包内离线检查](../../../../../../workspace/maintenance/v211_three_worktree_cleanup_20261114_001/post-cleanup-core-offline-checks.json)通过。包内检查有界于既定入口，包含引用或已保存读回的检查，不是新的物理运行。

[同一固定顺序空间核算](../../../../../../workspace/maintenance/v211_three_worktree_cleanup_20261114_001/space-after.json)：删除前 **26,922,106,880** 字节、删除后 **17,169,387,520** 字节，减少 **9,752,719,360** 字节；两次均包含原 integration 快照和保留证据，新增清理目录当时约 180,224 字节另计。该范围的 `du` 差额不等于文件系统独占块释放量，也不是 E00～E16 历史累计净节省。

U4/U5 的既有有界接收不变；历史锁路径依赖（T35）、原 integration 快照进一步处置及历史累计空间结论仍按原账本 OPEN。[U7 项目接收入口](20261114_e11_e16_u7_project_acceptance_entry.md)明确列出尚未闭合项，最终接收仍由维护者决定；不自动进入 G06，不 merge、push、tag 或发布。
