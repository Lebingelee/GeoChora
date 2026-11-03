# v2.1.1 恢复页

更新时间：2026-11-03。压缩或交接后先读本页，再读[总路线](../planning/roadmap.md)、[执行表](../planning/execution-and-acceptance.md)和当前子阶段 Goal。

- **当前阶段：**7 阶段／22 子阶段路线有效，五份协议仍为待讨论草案；G01/1a 已经 Sol 有界接收，1b attempt001 设计报告已提交待审。
- **执行状态：**1a `ACCEPTED_BOUNDED_1A_AUDIT`、attempt 1，执行 output `eb64b89f1dbceb6c7dbd10bef400846f8ab91ec9`；1b attempt001 `PASS`（设计交付）/`REPORTED_PENDING_REVIEW`，维护者审核前不视为 accepted；其余 20 项仍 `PLANNED`。当前无 active package／写入或 native window。
- **来源基线：**Core `develop@fd03817c9f6ef8ce9fd68c1db30125efda68e1c8`；GeoPhys `67da1165149486d3ae3e779c13ce31af49e17d50`。
- **工作树／分支：**继续维护者指定的现有 develop；不恢复 F/R 线，不增加分支或工作树。每包前重新核实当前 HEAD 和 dirty paths。
- **最近有效事实：**1a 核实了三条 physics 候选、selected PickCube state-only 边界、Position candidate 的 boundary-bound camera consumer、free-joint cross-render 限制、GeoPhys-only batch 及当前 provider registrations。未产生新任务成功或 renderer／batch/native evidence。
- **未解决：**D01/D05/D06 的候选与明确缺口、D02–D04/D07 的后续 owner 见[源码与决定表](../planning/source-map-and-references.md)。Core 与 GeoPhys 的 MuJoCo 声明版本区间冲突，需在后续执行环境／依赖决策中处理；不在本审计改依赖。
- **保护项：**已有未跟踪 `MUJOCO_LOG.TXT` 和顶层 diagnostic handoff；ignored 资产／Evidence、子模块和历史 refs 均保留。原始 hash 由本轮文档收据记录。
- **下一动作：**由维护者手动转发 [1b 设计报告](reviews/20261103_1b_representation_design.md)给 Sol 独立审阅；在新的完整包获授权前，不自动进入 1c。权威协议保持 `DRAFT_FOR_DISCUSSION`。
- **范围提醒：**Flora、完整 F07、RL／IL demo、agent_factory、新后端完整接入和非刚体样例属于后续 v2.1.x；本版没有自动发布／Qualification。

实时子阶段、attempt、包 hash、实际输入／输出 HEAD、证据和审核决定更新[编排索引](orchestration.json)。本页只保存恢复所需摘要；不复制原始失败日志，不把完成文档当成完成实现。
