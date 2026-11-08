# G05 5c attempt003 — 最终普通窗口执行规划

状态：`APPROVED_READY_FOR_MANUAL_FORWARD`。已完成两次普通 attempt 和第三次前的[强制重评](stage5-5c-attempt003-reassessment.md)、[Sol 前置分析](stage5-5c-attempt003-sol-prework.md)。本计划与工作包准备不启动 attempt；维护者已批准本次提出的执行范围和预算，将手工转发，随后由 Sol 独立主审。第三次仍未接收则停止普通派包，进入维护者主导诊断。

目标不变：Env 创建时固定 renderer 至 close、同步任务 RGB、至少一个真实跨组合和通用任务接线；同 Env 的 renderer 切换延期。以已有 [attempt002 主审](../maintenance/reviews/20261108_5c_attempt002_sol_review.md)为起点，优先修复非 Position selected 的 typed state/具名渲染绑定，以及 component task camera 的实际 FOV/near/far 绑定、回读和图像对应。实现应保留原 Controller／physics admission、任务语义和已有 state-only 行为，不得依任务名或 Panda 类型特设通用 renderer。Pendulum／双轮车 Agent 迁移是既定后续候选，不是本次新增绝对门。

以真实构造、真实生命周期及有边界的物理/渲染验证闭环；provider-free 合同可用于隔离缺陷但不冒充 native，旧三原生及跨组合证据按实际代码、输入和适用性复用。不能以新的相机方案重新要求全部 5b 矩阵、所有任务、额外像素精度或任意 provider 组合。前两包偏差和失败保留，不为了重建历史合规而追溯重跑。

实施顺序、逐门证据、权限、提议预算、失败处置和 release 要求以 `V211_G05_5c_attempt003` 冻结工作包为准；此包已获维护者批准，尚未派发或开始执行。stage5 历史清理及原/新身份映射见[收据](../maintenance/20261108_5c_history_cleanup.md)；全部诊断与 source snapshot 文件保留在 workspace，不 force-add 进 Git。
