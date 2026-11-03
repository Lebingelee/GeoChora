# TaskEnv v2.1.1 — 协议与实施规划

日期：2026-11-03。状态：`PLANNING`。维护者已确认实施路线并授权构建本目录文档；协议具体字段、API 签名和执行包仍待分阶段讨论、冻结。本次没有启动实现 Goal、派发执行任务或运行仿真。

## 版本目标

以统一任务表示为中枢，明确 Core、physics provider adapter、render adapter 之间的协议，实际接通 MuJoCo、GeoPhys、Isaac Sim＋PhysX 的首批路线。支持构建及 reset 时选择后端、renderer 和 Controller；episode 内维持已选执行组合。reset 重新初始化下一轮，不迁移上一轮物理状态。

控制器统一、PickCube Solution 修复、窗口与同步 RGB、并行执行都服务于上述协议的真实落地。接口注册、静态通过或窗口截图不代表整条路线完成。

## 阅读入口

- [范围与七阶段路线](planning/roadmap.md)：7 个阶段、22 个 a/b/c/d 子阶段及延期事项。
- [执行顺序与验收](planning/execution-and-acceptance.md)：依赖、阶段出口、工作包、证据及分支约束。
- [源码 owner 与外部参考](planning/source-map-and-references.md)：当前基础、缺口、待讨论事项和官方项目链接。
- 协议草案：[统一任务表示](contracts/unified-task-representation.md)、[physics provider](contracts/physics-provider.md)、[render provider](contracts/render-provider.md)、[控制与反馈](contracts/control-and-feedback.md)、[生命周期与数据](contracts/lifecycle-and-data.md)。
- 阶段 Goal：[01 协议](goals/01-protocols.md)、[02 Solution](goals/02-pickcube-solution.md)、[03 后端](goals/03-backends.md)、[04 控制](goals/04-control.md)、[05 渲染](goals/05-rendering.md)、[06 并行](goals/06-parallel.md)、[07 集成](goals/07-integration.md)。
- [API 迁移入口](api/README.md)、[指南交付要求](guides/README.md)、[单一能力矩阵](capabilities/README.md)。
- [恢复页](maintenance/recovery.md)、[编排索引](maintenance/orchestration.json)、[本轮文档收据](maintenance/20261103_documentation_receipt.md)。

## 来源和当前能力

规划输入 Core：`develop@fd03817c9f6ef8ce9fd68c1db30125efda68e1c8`；GeoPhys pin：`67da1165149486d3ae3e779c13ce31af49e17d50`。本地 `refs/tags/v2.1.0` 指向该 Core；本轮未查询远端或 GitHub Release，不能从旧候选措辞推断当前发布状态。

当前实现与证据仍按 [v2.1.0 API](../v2.1.0/api/public-api.md)和[有界能力矩阵](../v2.1.0/capabilities/capability-matrix.json)理解。selected 渲染仍只准入 state-only；R3 主要输出位置参考；LIBERO 有限定的力矩＋位置混合控制。本目录所有目标均未取得新的原生运行证据。

F06 历史 9/9 runtime-valid、0/9 task-success，R07 A123 的有界接收与例外、F05 未决研究门均保留。不将 v2.1.1 的目标或后续结果改写进冻结证据。

## 文档边界

本目录拥有 v2.1.1 的规划及待冻结协议；v2.1.0 保留来源版本行为。每项协议只在对应 `contracts/` 页面维护，Goal 引用它并记录具体实施与验收。实现后再更新 API、指南和矩阵，不能把草案当成现有可调用 API。系统归属仍服从[架构](../../../global/architecture.md)与[ownership](../../../global/ownership.md)。
