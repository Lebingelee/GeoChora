# v2.1.1 恢复页

更新时间：2026-11-03。压缩或交接后先读本页，再读[总路线](../planning/roadmap.md)、[执行表](../planning/execution-and-acceptance.md)和当前子阶段 Goal。

- **当前阶段：**已确认 7 阶段／22 子阶段路线，文档已建立并完成静态检查；五份协议为待讨论草案。
- **执行状态：**22 项均 PLANNED，attempt 0；没有 active package，没有新增实现 Goal／代理派发。
- **来源基线：**Core `develop@fd03817c9f6ef8ce9fd68c1db30125efda68e1c8`；GeoPhys `67da1165149486d3ae3e779c13ce31af49e17d50`。
- **工作树／分支：**继续维护者指定的现有 develop；不恢复 F/R 线，不增加分支或工作树。每包前重新核实当前 HEAD 和 dirty paths。
- **最近有效事实：**已有 v2.1.0 source baseline 与有界证据；本轮只做源码／文档只读核实及文档编辑，没有新任务成功或渲染／并行证据。
- **未解决：**D01–D07 见[源码与决定表](../planning/source-map-and-references.md)，尤其首批 renderer／batch 名单、夹爪 effort、模型服务与数值准入。
- **保护项：**已有未跟踪 `MUJOCO_LOG.TXT` 和顶层 diagnostic handoff；ignored 资产／Evidence、子模块和历史 refs 均保留。原始 hash 由本轮文档收据记录。
- **下一动作：**维护者审阅文档，再进入 1a/1b 的范围核实和统一表示讨论；协议定稿与完整工作包准备完成后才进入实施。
- **范围提醒：**Flora、完整 F07、RL／IL demo、agent_factory、新后端完整接入和非刚体样例属于后续 v2.1.x；本版没有自动发布／Qualification。

实时子阶段、attempt、包 hash、实际输入／输出 HEAD、证据和审核决定更新[编排索引](orchestration.json)。本页只保存恢复所需摘要；不复制原始失败日志，不把完成文档当成完成实现。
