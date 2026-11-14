# E15 最终清理与复核结果

维护者批准了 [最终处置方案](20261114_e15_final_disposition_proposal.md)的精确清单及 586 个目录的按需临时权限调整。执行输入 HEAD `fed05753`，无生产代码修改、无 native 或完整 Solution 重跑；U4／U5 既有接收不重开。

执行器锁内重检清单、历史锁、活动、工作树／挂载、保护输入、pins、14 个固定 U5 索引和 1,021 个选中对象后，删除 **76,177** 条范围内普通文件／链接及 **157** 条分类副本／旧草稿，按清单移除 **24,554** 个已空内部目录。链接仅处理自身，外部目标未跟随。锁释放后日志有结束与释放记录；[执行日志](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/final-execution-journal.jsonl) SHA-256 `c5a01ca8172272d1572a0563698ea10f71198ae99e69de674671f849198d5a70`。

独立只读复核：76,334 个候选的意图／完成事件与固定清单一一对应、无重复或额外路径，当前均不存在；24,554 个目录删除事件及 38,794 对父目录权限意图／恢复事件均配对。原 24,661 个范围目录剩 **107** 个，为 103 个根锚点及两项例外祖先，身份和模式保持；快照私人输入和 loader 001 事件流原件保留，未读取私人内容。共享锁两个路径同 inode，四项保护输入、两 pins、U5 14 个索引及 1,021 个对象 SHA／大小通过；四个当前 physical／metadata fixture 链接有效。日志记录 `/proc` 访问拒绝 1,045 次，无法证明不可见或不遵守协议的进程不存在。

从 U5 包执行的 [七项有界离线读回](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/post-cleanup-readback/summary.json)全部通过，派生输出写入独立目录，未覆盖原 U5 收据；其 G05 仍仅为引用完整性，U4 completion 仍为有界联合证据。首次使用新包装器时因 cwd 导致 G03 导入主工作树而被隔离守卫拒绝；该 [失败收据](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/post-cleanup-readback/initial-wrapper-failure.json)保留，修正 cwd 后全部通过。当前正式纯守卫入口下，[历史 H5 **25 passed**](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/post-cleanup-guarded-h5.log)，[physical fixture **8 passed**](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/post-cleanup-guarded-physical.log)。首次直接调用 32 项虽通过，但启动时缺 guard 环境变量，不能作为受守卫结果；随后使用正式入口重跑。

文档 validator 退出码 1，唯一 error 为旧期望中的 `MUJOCO_LOG.TXT` 差异；历史链接问题 79、当前 stale 引用 0，与既有记录一致。四项实际保护输入 SHA 与独立基线一致，未修改保护原件或校验期望。[校验日志](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/post-cleanup-doc-validator.log)保留。

同一有序 `du -s -x -B1` 范围包括 102 个 stage 根、快照、U5 包和本轮分类／保全目录，硬链接仅计一次：[执行前](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/approved-execution-space-before.json) **30,579,863,552 B**，[清理后](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/approved-execution-space-after.json) **1,470,246,912 B**，实测下降 **29,109,616,640 B**（约 29.11 GB）。后值含 U5 **812,830,720 B**、分类／保全及执行日志 **430,714,880 B**、保留的 stage 例外等 **226,648,064 B**和快照 **53,248 B**；随之后收据增长可能略变。按相同范围点时清点，目录 **25,813→1,260**，普通文件 **76,816→7,131**，链接 **6,641→4**；路径逻辑字节 **31,808,834,715→2,976,397,934 B**，去重 inode 逻辑字节 **30,287,093,972→1,454,657,191 B**。后测包含新读回目录，故目录净变化与删除计数不完全相同。历史累计精确净额仍为 UNKNOWN，不能把不同起点的节省相加。

旧 attempt／overlay 的原布局和未选历史记录不再保证可运行或可重放；原路径到 U5 的映射及清单保留。COM、N08、R05c、T19、SDK 关闭和 integration Git 管理元数据损失等边界沿用。项目最终接收仍由维护者决定，不自动进入 G06／G07。
