# integration 快照最终清理结果

维护者批准[精确清单](20261114_e11_e16_final_snapshot_decision.md)后，执行器在共享锁内重核候选、保留对象、活动、挂载与保护输入，于 2026-11-14 逐项移除 **21,929 条清单内普通文件**，涉及 **1,784 个父目录**。未删除其他清单对象。执行日志记录的清单 SHA-256 为 `ebd4bc4b3149de129869335363823788fea74a2a849de49faf88327fc76a4113`；[执行收据](../../../../../../workspace/maintenance/v211_e11_e16_final_snapshot_cleanup_20261114_001/result.json) 与[只读逐项对账](../../../../../../workspace/maintenance/v211_e11_e16_final_snapshot_cleanup_20261114_001/reconcile.json)显示全部路径删除完成且不存在、所有父目录 CLOSED、冲突 0。事件日志 SHA-256 `dde1454aef22c58cac45aed6432b72f4eda55fb5a9a5efe745010eaede35603e`。独立主审重新对账；[独立复核](../../../../../../workspace/maintenance/v211_e11_e16_independent_review_0506ae26/u7-final-snapshot-execution-review.md)不扩展为完整历史环境恢复。

删除后在锁内重算 561 个对应 U5 内容对象，计 343,110,889 逻辑字节，SHA 均通过；四保护输入和两 pins 一致，见[收据](../../../../../../workspace/maintenance/v211_e11_e16_final_snapshot_cleanup_20261114_001/retained_objects_postcheck.json)。之前的全量候选恢复和拼合抽样仍按原范围复用，本次未重建整份副本；原 integration Git 管理元数据损失不能补回。可见进程扫描有 1,036 次权限拒绝，不能排除不可见或非合作进程；快照内保留的符号链接和原目录不保证完整可运行。

固定顺序 `du -sx -B1`：快照加 U5 删除前 **16,198,696,960 B**，删除后 **6,927,147,008 B**，毛下降 **9,271,549,952 B**；其中快照保留 **6,114,316,288 B**，U5 **812,830,720 B**。本轮执行输出及对账 **15,679,488 B**，预检工具 **180,224 B**，三路线短程证据 **11,894,784 B**；从上述毛下降扣除这三项后为 **9,243,795,456 B**。这是本次明示范围的保守算术，并非全项目或 E00～E16 历史累计净节省；其他既有保全和准备占用未完整计入，硬链接归因随 `du` 顺序而异。历史累计精确净额 **UNKNOWN**。此前三工作树的 9,752,719,360 B 为另一测量区间，不与本结果直接相加。

三 provider 短程 worker 与 H5 读回按其各自冻结运行身份复用，见[项目接收入口](20261114_e11_e16_u7_project_acceptance_entry.md)。未因此重跑完整 Solution、改变 U4/U5 接收或自行宣布项目接收。
