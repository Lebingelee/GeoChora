# E11～E16：E15 剩余整理当前状态

**E15 OPEN，未提出整体项目接收。** 以 `932a98dc` 为分类输入，按[独立项目复核 R1～R4](20261114_e11_e16_final_project_review_e3f13d72.md)继续；E11～E14 既有有界接收及 U4／U5 不重开，E16 的 refs／worktree 收敛按此前范围保留。已批准清理的既有结果不变，本轮没有执行新增删除或 native／完整 Solution。

## 已完成的分类与保全

- 对 102 个 G01～G05 历史根和 integration 快照做不跟随链接的清点，共 69,542 个普通文件及 6,637 条链接，扫描错误 0。[目录清单](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/directory-classification.csv)与[逐文件事实](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/files.jsonl)保留来源。先前 16 类 E11～E16 产物也已[按职责分类](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/e11-e16-output-ownership.json)。
- 复用 U5 冻结对象、Git blob 和必要归位副本，形成[候选交叉表 v13](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/preliminary-candidate-overlap-audit-v13.json)：56,583 个不同非目录路径，另有 1,428 个缓存目录条目。它汇总精确路径、来源清单及各清单 SHA，**不是最终删除清单或授权**；部分同字节日志不能证明同次运行，路径／调用身份仍须判断。
- 已保全此前未被完整覆盖的 G04 关键诊断与主审引用、G05 human／窗口／RGB 原始材料、两份不同 R05c 原始记录和旧 G03 partial Recorder 证据；原始来源、SHA 及恢复边界见[详细证据记录](20261114_e11_e16_e15_classification_details.md)。保全的两份 R05c 均在新位置通过各自原候选 reader，均为 2,443 transition／12,215 样本，历史资格仍 `NOT_REQUALIFIED`。human 和旧返工材料依各自原状态保留，不扩大接收。
- 对原 G05 Isaac loader 历史报告的 001／005 混写建立[独立更正](20261114_g05_isaac_loader_history_correction.md)，保留原报告及同次收据；001 的 226,129,691 字节独有事件流作为核心诊断原地保留，已从所有候选排除。未将未知隐式物理推进写成零。
- 快照 36 项独立主审图片／脚本及 F04 原路径 provenance 已归位；[快照逐项草稿 v3](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/snapshot-file-disposition-draft-summary-v3.json)覆盖其 23,069 个普通文件与 6,328 条链接。257 条历史 Isaac／Python overlay 链接单列保留，私人本地输入保留且内容未读取；任何链接候选只涉及链接自身，绝不跟随目标。
- 独立主审已对各类关键保全和已列候选做逐项身份／哈希核对或注明的抽样；67 项快照／stage／保留副本的最新三方 SHA 核验通过。复核范围与各清单的限制保留在详细记录中，不能当成对未列材料或完整历史环境的保证。

## 仍需处理

1. [Stage 逐文件草稿 v7](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/stage-file-disposition-draft-summary-v7.json)仍有 7,122 条其他历史、1,605 条根级上下文、1,041 条同次上下文及 2,738 条核心诊断组待判；155 条锁文件单列，不能仅凭名称清理。草稿尚未计入最近新增的所有保全，须重新归并。
2. 快照尚有 5,772 项与 stage 文件同内容，但依赖后者的最终去向；不得将两份仅凭相互重复同时删除。历史 overlay 链接目标未被访问，不能保证其现存或可用。需完成剩余必要性分类和恢复映射，明确不可原样重放的旧过程。
3. 形成一份可执行的最终路径清单：消除类别和保留来源冲突，复核 F04 的单对象 manifest、固定 Git blob、相对路径映射及所有例外；执行前检查实际持锁者／运行进程、挂载、权限和逐项身份，保证保留对象及 in-place 核心原件不在候选中。已批准过的事项不重复询问；**新增删除仍须按原目标获得针对具体清单的维护者授权**。
4. 授权执行后按同口径统计净变化，复核必要 reader、保全输入及受影响调用，再做独立最终项目复核，提交维护者决定 U7 项目接收。历史累计精确净额缺基线，保持 UNKNOWN；不自动进入 G06，不改 pins、merge、push、tag 或发布。

## 测量与验证边界

[同序测量](../../../../../../workspace/maintenance/v211_e11_e16_e15_final_classification_20261114_001/interim-space-measurement-v2.json)中，102 根加快照仍为 **29,222,801,408 分配字节**，与本轮基线相同；随后计算本轮新增分类／保全目录为 **474,955,776 字节**，合计 **29,697,757,184 字节**。本轮没有新增删除，因此没有实际净下降；这些数字不代表 E00～E16 历史累计净节省。新增目录包含此前多复制的 147 个 U5 内容重复项，已按 SHA 单列候选，未删除。

本轮文档校验在最近一次运行时退出 1：唯一错误是旧期望中的 `MUJOCO_LOG.TXT` 差异，历史链接问题 79、当前 stale 引用 0；与清理前记录一致。四份实际保护输入 SHA 与独立主审基线一致，两个子模块 pins 保持原值。后续最终收尾需在最终文档状态重跑校验，不能将该既有错误称为通过。

详细的中间发现、原始清单、修正过的错误候选及审查记录保留在[分类详情](20261114_e11_e16_e15_classification_details.md)和忽略目录内；旧版或被纠正的候选不得用于执行。
