# S5-C8 存储监测判据修订 — 2026-10-18

**GeoChora v1.1.0 — RELEASE_CANDIDATE — NOT_PUBLISHED**

维护者提供了两次可重复、非破坏性 SMART 刷新观察：`0x802→0x807`、`0x807→0x80c`，各增加 5，查询均成功；随后缓存读取不增加。该结果支持近期固定增量与 SMART 查询有关，不能将这些增量等同于相同次数的文件读写故障。本次没有逐条捕获底层命令，也不能据此解释所有历史增量。

上游 [SCSI completion 源码](https://github.com/torvalds/linux/blob/v7.0/drivers/scsi/scsi_lib.c)在 `cmd->result` 非零时增加 `ioerr_cnt`；[libata pass-through 源码](https://github.com/torvalds/linux/blob/master/drivers/ata/libata-scsi.c)明确处理无硬件错误时为返回 ATA 状态产生的 CHECK CONDITION。这支持将该计数视为较广的命令结果观测，不能独自证明本机发生了新读写故障。上游源码说明不是本机逐命令追踪证据。

## 已采用的策略

| 观测 | 当前处理 |
|---|---|
| 单独 `ioerr_cnt` 增长 | INVESTIGATE；记录数值、时间和缓存 SMART 更新时间，不机械停止低 I/O 工作，也不自动认定全部无害 |
| 新 ATA/块设备/文件系统错误，或实际读写失败 | STOP affected operation，保留日志 |
| CRC、重映射、待处理或不可校正指标增长；SMART failing | STOP，并保留原值和新值 |
| 保护文件哈希、路径身份或清单不匹配 | STOP affected operation，禁止替换或扩展路径 |
| 日志/SMART 可见性不足 | 明确记录 UNKNOWN/visibility limits，不冒称磁盘健康，不作为进一步高 I/O/破坏性操作的自动放行 |

文档、Phase 2.0 回顾、readiness 和有界只读核验可以继续。高 I/O 或进一步破坏性操作仍需适用的资源/安全与精确授权条件；本次修订不是新增删除授权。

历史 10 月 15 日 BadCRC、链路重置及 READ I/O error 事实不变。当前 SMART 正常不证明设备或 SATA 链路完全可靠；数据线、接口、供电和设备侧根因未被本次确定。独立备份及恢复验证仍 NOT_VERIFIED，发布仍 BLOCKED。

## 工具与实际验证

C8 本地 `storage_observation.py` 只读取 sysfs、可读 kernel log 和 UDisks 缓存属性/SmartGetAttributes，不调用 SmartUpdate。新版只读 `monitor.py` 使用当前单独的 L1 快照验证文档迁移，同时保留原批准清单和原保护快照不变。删除工具及旧 `STOP_STORAGE` 未解除、未被执行；它们作为早期执行/停止记录保留，不是新版通用停止判据的实现。

分类器 10 项 unittest 通过，含单独计数变化、CRC 和三个扇区指标增长、实际 EIO、哈希异常、kernel error、SMART failing、可见性不足和计数不可读。它们验证监测判据逻辑，不是硬盘可靠性资格。

本轮缓存读取：`ioerr_cnt=0x80c`、CRC=37、reallocated/pending/uncorrectable=0、SmartFailing=false；可读当日日志没有匹配的新同类存储错误。完整 kernel ring 不可见，未声称已排除全部错误。本轮未重复 SMART 刷新实验；重复性的来源为维护者报告，缓存状态为助手独立读取。原始错误判读与停止收据保留，当前判断由本修订补充。

## C8 与发布交接

[最终交付](c8_manual_cleanup_final_report.md)、[逐项完成审计](c8_goal_completion_audit.md)和[当前 readiness](release_readiness.md)必须区分“历史风险 OPEN”与“正在发生、足以停止所有低 I/O 工作的已证实新故障”。前者保留，后者未被计数单独证明。B worktree 和 522 个 holdout 仍保留；用户未保存逐文件日志仍是不可追溯的证据限制，不能伪造补齐。无额外删除、push、main、tag 或正式发布。
