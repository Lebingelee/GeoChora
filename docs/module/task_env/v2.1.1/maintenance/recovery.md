# v2.1.1 恢复页

更新时间：2026-11-03。压缩或交接后先读本页，再读[总路线](../planning/roadmap.md)、[执行表](../planning/execution-and-acceptance.md)和当前子阶段 Goal。

- **当前阶段：**7 阶段／22 子阶段路线有效；G01/1a 和 1b 已由 Sol 有界接收，五份协议仍为待维护者审阅的草案。
- **执行状态：**1a `ACCEPTED_BOUNDED_1A_AUDIT`、attempt 1；1b `ACCEPTED_BOUNDED_1B_DESIGN`、attempt 1。1c `REPORTED_PENDING_REVIEW`、attempt 1，协议设计结果 PASS 但五份协议仍为 `DRAFT_FOR_DISCUSSION`；详见 [1c 设计摘要](reviews/20261103_1c_physics_protocol_design.md) 与本次外部 raw report。1d 及其余 19 项仍 `PLANNED`。当前无 active package／写入或 native window。
- **来源基线：**Core `develop@fd03817c9f6ef8ce9fd68c1db30125efda68e1c8`；GeoPhys `67da1165149486d3ae3e779c13ce31af49e17d50`。
- **工作树／分支：**继续维护者指定的现有 develop；不恢复 F/R 线，不增加分支或工作树。每包前重新核实当前 HEAD 和 dirty paths。
- **最近有效事实：**1a 核实了三条 physics 候选、selected PickCube state-only 边界、Position candidate 的 boundary-bound camera consumer、free-joint cross-render 限制、GeoPhys-only batch 及当前 provider registrations。未产生新任务成功或 renderer／batch/native evidence。
- **未解决：**D01/D05/D06 的候选与明确缺口、D02–D04/D07 的后续 owner 见[源码与决定表](../planning/source-map-and-references.md)。Core 与 GeoPhys 的 MuJoCo 声明版本区间冲突，需在后续执行环境／依赖决策中处理；不在本审计改依赖。
- **保护项：**已有未跟踪 `MUJOCO_LOG.TXT` 和顶层 diagnostic handoff；ignored 资产／Evidence、子模块和历史 refs 均保留。原始 hash 由本轮文档收据记录。
- **下一动作：**由维护者／Sol 复核 1c attempt001 的设计与门禁；仅复核接受后再由维护者决定是否准备 1d 单阶段包。本轮不自动进入 1d。
- **范围提醒：**Flora、完整 F07、RL／IL demo、agent_factory、新后端完整接入和非刚体样例属于后续 v2.1.x；本版没有自动发布／Qualification。

1c attempt001 使用 Core input `b0024c71614f2d2ede8d9eb1db594cfcde3e9278`、GeoPhys pin `67da1165149486d3ae3e779c13ce31af49e17d50`；raw output、实际 output HEAD 与提交/hash 见外部报告。该窗口已释放，无原生启动或 implementation test。实时子阶段、attempt、包 hash、证据和审核决定更新[编排索引](orchestration.json)。本页只保存恢复所需摘要；不复制原始失败日志，不把完成文档当成完成实现。
