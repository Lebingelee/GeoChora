# v2.1.1 恢复页

更新时间：2026-11-03。压缩或交接后先读本页，再读[总路线](../planning/roadmap.md)、[执行表](../planning/execution-and-acceptance.md)和当前子阶段 Goal。

- **当前阶段：**7 阶段／22 子阶段路线有效，五份协议仍为待讨论草案；G01/1a attempt001 已完成审计和文档提交，等待维护者／Sol review。
- **执行状态：**1a `REPORTED_PENDING_REVIEW`、attempt 1；其余 21 项仍 `PLANNED`。无 active package／native window；1b 未开始。
- **来源基线：**Core `develop@fd03817c9f6ef8ce9fd68c1db30125efda68e1c8`；GeoPhys `67da1165149486d3ae3e779c13ce31af49e17d50`。
- **工作树／分支：**继续维护者指定的现有 develop；不恢复 F/R 线，不增加分支或工作树。每包前重新核实当前 HEAD 和 dirty paths。
- **最近有效事实：**1a 核实了三条 physics 候选、selected PickCube state-only 边界、Position candidate 的 boundary-bound camera consumer、free-joint cross-render 限制、GeoPhys-only batch 及当前 provider registrations。未产生新任务成功或 renderer／batch/native evidence。
- **未解决：**D01/D05/D06 的候选与明确缺口、D02–D04/D07 的后续 owner 见[源码与决定表](../planning/source-map-and-references.md)。Core 与 GeoPhys 的 MuJoCo 声明版本区间冲突，需在后续执行环境／依赖决策中处理；不在本审计改依赖。
- **保护项：**已有未跟踪 `MUJOCO_LOG.TXT` 和顶层 diagnostic handoff；ignored 资产／Evidence、子模块和历史 refs 均保留。原始 hash 由本轮文档收据记录。
- **下一动作：**维护者／Sol 审阅 [1a 审计摘要](reviews/20261103_1a_scope_audit.md)和原始报告；接收后由维护者另行派发完整 1b 包。不得自动进入 1b，也不以本审计批准协议或实现。
- **范围提醒：**Flora、完整 F07、RL／IL demo、agent_factory、新后端完整接入和非刚体样例属于后续 v2.1.x；本版没有自动发布／Qualification。

实时子阶段、attempt、包 hash、实际输入／输出 HEAD、证据和审核决定更新[编排索引](orchestration.json)。本页只保存恢复所需摘要；不复制原始失败日志，不把完成文档当成完成实现。
