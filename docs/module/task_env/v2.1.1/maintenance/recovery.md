# v2.1.1 恢复页

更新时间：2026-11-03。压缩或交接后先读本页，再读[总路线](../planning/roadmap.md)、[执行表](../planning/execution-and-acceptance.md)和当前子阶段 Goal。

- **当前阶段：**7 阶段／22 子阶段路线有效；G01/1a、1b、1c 已由 Sol 有界接收；1d attempt001 已完成设计文档并 `REPORTED_PENDING_REVIEW`，五份协议仍为草案。
- **执行状态：**1a `ACCEPTED_BOUNDED_1A_AUDIT`、1b `ACCEPTED_BOUNDED_1B_DESIGN`、1c `ACCEPTED_BOUNDED_1C_DESIGN`，均 attempt 1。1d attempt001 为 `REPORTED_PENDING_REVIEW`；设计摘要见 [1d review](reviews/20261103_1d_render_protocol_design.md)，权威条款见 render/lifecycle/physics contracts 与实施映射。五份协议仍 `DRAFT_FOR_DISCUSSION`。2a 与其余后续子阶段保持 `PLANNED`；本窗口已结束，不运行 native。
- **来源基线：**Core `develop@fd03817c9f6ef8ce9fd68c1db30125efda68e1c8`；GeoPhys `67da1165149486d3ae3e779c13ce31af49e17d50`。
- **工作树／分支：**继续维护者指定的现有 develop；不恢复 F/R 线，不增加分支或工作树。每包前重新核实当前 HEAD 和 dirty paths。
- **最近有效事实：**1a 核实了三条 physics 候选、selected PickCube state-only 边界、Position candidate 的 boundary-bound camera consumer、free-joint cross-render 限制、GeoPhys-only batch 及当前 provider registrations。未产生新任务成功或 renderer／batch/native evidence。
- **未解决：**D01/D05/D06 的候选与明确缺口、D02–D04/D07 的后续 owner 见[源码与决定表](../planning/source-map-and-references.md)。Core 与 GeoPhys 的 MuJoCo 声明版本区间冲突，需在后续执行环境／依赖决策中处理；不在本审计改依赖。
- **保护项：**已有未跟踪 `MUJOCO_LOG.TXT` 和顶层 diagnostic handoff；ignored 资产／Evidence、子模块和历史 refs 均保留。原始 hash 由本轮文档收据记录。
- **下一动作：**由维护者/Sol 手动审阅 1d attempt001；确认前不冻结协议、不派发 2a。报告与下一包仍由维护者手动转发。
- **范围提醒：**Flora、完整 F07、RL／IL demo、agent_factory、新后端完整接入和非刚体样例属于后续 v2.1.x；本版没有自动发布／Qualification。

1c attempt001 使用 Core input `b0024c71614f2d2ede8d9eb1db594cfcde3e9278`、GeoPhys pin `67da1165149486d3ae3e779c13ce31af49e17d50`；执行 output `4c3894df74f1946417b360e76fe3440b0551805d`；raw output 与 hash 见外部报告，原始输出保持。该窗口已释放，无原生启动或 implementation test。实时子阶段、attempt、包 hash、证据和审核决定更新[编排索引](orchestration.json)。本页只保存恢复所需摘要；不复制原始失败日志，不把完成文档当成完成实现。


1d attempt001 输入 `8e70ee581602016932c99a257faad7aa6e5f91ea`、GeoPhys `67da1165149486d3ae3e779c13ce31af49e17d50`；输出 commit 与原始报告/hash 见 `workspace/maintenance/v211_g01_1d_attempt001/`。只提交 allowlisted docs；其余历史保护与旧 raw 保持。静态文档验证完成后本地窗口释放；没有 subagent、native、window、physics/GPU 或 implementation tests。核心未决建议：reset capture phase 新值、Canonical RGB dtype/range、owned-copy 默认、window/App fault policy，由维护者审阅 1d review 表；实施 owner 分派到 3a、5a–5c、6c。当前不进入 2a。
