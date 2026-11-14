# E11～E16 项目接收入口

状态：**维护者已对交付 `86921c62` 及本入口所列限制作 E11～E16 有界项目接收。** 详见[接收记录](20261114_e11_e16_maintainer_project_acceptance.md)。 U4、U5 的既有有界接收不重开。

[本轮 E15 最终清理与独立对账](20261114_e15_final_disposition_execution.md)及[独立项目复核](20261114_e15_final_project_reconciliation.md)覆盖此前独立复核指出的 102 个 stage 根和 integration 快照补集，保留两项明确例外。七项包内离线读回、25 项历史 H5 和 8 项 physical fixture 守卫检查通过；按包含 U5 与本轮分类／日志的同序范围实测下降 29,109,616,640 B。旧未选 attempt 与历史环境不保证原样重放，历史累计净额 UNKNOWN。

| 范围 | 已完成与待办 |
| --- | --- |
| U1～U4 | [U4 独立主审与维护者条件接收](20261113_e11_e16_u4_independent_acceptance.md)保留；五路线 T19 为[同次联合证据](20261113_e11_e16_u4_joint_completion.md)，H5 单文件不自含完整 completion。各路线保留自己的源码与配置身份。 |
| U5 | [五 stage 与优化证据包](20261113_e11_e16_u5_evidence_selection.md)已接收；三处清理后七项包内离线检查通过，不能改称新 native 资格。 |
| U6 T35～T38 | [当前受支持运行端锁收敛](20261114_e11_e16_final_lock_convergence.md)完成有界验证；新旧锁别名仍为同 inode，旧别名保留。三工作树清理的同序含快照范围下降 9,752,719,360 B。快照 [精确候选清单](20261114_e11_e16_final_snapshot_decision.md)经批准已执行并独立复核；[固定范围结果](20261114_e11_e16_final_snapshot_execution.md)扣除本轮三项证据及工具占用后下降 9,243,795,456 B。历史累计精确净额 UNKNOWN。 |
| U7 T39～T44 | [三工作树移除](20261114_e11_e16_three_worktree_execution.md)后保留主 checkout 与维护者要求的 locked archive、六个本地 heads 和四个 tags。三 provider 清理后短程真实 worker 及同次 H5 冷读通过，见下；项目已按本入口边界由维护者有界接收。 |

三条短程运行的生产源码身份均为 `3e77f6e0768ca2896e60d4236c9822a917625887`：MuJoCo、GeoPhys、Isaac 各 seed 31、3 个非零 interval，构造、reset、step、close 及 H5 T=3/T+1=4 冷读通过，关闭后锁可再取得。[独立读回复核](../../../../../../workspace/maintenance/v211_e11_e16_independent_review_0506ae26/u7-final-short-worker-v5-review.md)核对收据与 SHA。三次均为 PARTIAL，solution_failed 和 truncated 为真；不代表任务成功或完整 Solution。Isaac 记录一次 App 启动及关闭，18 bootstrap 与 15 显式子步；其他隐式推进 UNKNOWN。此前 Isaac v4 [监督与中断事故](20261114_e11_e16_harness_worker_incident.md)保留，不能补称正常 close。

**维护者已接受的具体边界：** H5 completion 采用已批准的同次联合证据；历史 integration Git 管理元数据不可补回；历史累计精确净额 UNKNOWN；保留 archive 与旧锁同 inode 别名；可见性不足和非合作进程不属锁协议保证；文档 validator 留有既有基准错误及历史链接问题；强制终止时原生 App 正常关闭不能保证。旧整模块测试有历史 API 漂移失败，R06b 历史 fake 测试因缺旧模块不能收集，不声称全绿。各项原资格与此前失败保持原身份。

[U6/U7 原独立主审](../../../../../../workspace/maintenance/v211_e11_e16_independent_review_0506ae26/u7-final-independent-project-audit.md)和后续短程独立复核分别说明其审查范围；不会将其合并成对所有历史内容的新资格。已批准的快照精确清单及独立复核已完成；本轮批准的快照补集和历史输出已按最终清单处置。维护者已接收上述有界范围；G06 另行启动，不自动 merge、push、tag 或发布。
