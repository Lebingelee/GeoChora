# Phase II-01 当前入口

Phase II-01 同时记录 R 路线的 Core 工作与 F 路线的多资产后继计划。两条路线的 owner、状态和证据相互独立；本页只负责当前导航，不改写历史接受、冻结输入或发布决定。

## 当前状态

截至 2026-11-01，R 路线的 LIBERO A123 技术交集为 `ACCEPTED_BOUNDED_R07_A123_TECHNICAL`：固定上游来源、task 1–3、MuJoCo/GeoPhys CPU、冻结 A 阶段环境和上游控制流程。它不表示整个 R00–R07/P99、任务成功、Qualification 或发布已完成。

task2 GeoPhys 的接触前偏差按维护者接受的限定例外处理，仅对应这次冻结的来源、controller 和 action sequence。首次上游手指碰柜体发生在 action 82；其 TCP 对上游的位置 P95/最大值为 33.143/37.916 mm，姿态为 229.074/259.412 mrad。该决定不建立一般 provider parity。资产 `wine_bottle` 与 `wine_rack` 的具体文件许可和署名记录仍未解决；B/C、高精度控制器改进和自主 Solution 是可选后续，Isaac Sim 延期。

完整状态与接受边界见 [07 执行与接受矩阵](07_Execution_Order_and_Acceptance.md) 和 [Sol A123 接受记录](../../../../maintenance/20261101_r07_a123_sol_acceptance.md)。原始 A123 返工报告保留于忽略跟踪的 [`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/libero_a123_review_rework_20261101_001/`](../../../../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/libero_a123_review_rework_20261101_001/)；接受决定不改写该报告或 raw evidence。

## 文档入口与责任

| 文档 | 当前用途 |
| --- | --- |
| [00 总蓝图](00_Phase_II_01_Blueprint.md) | Phase 基线、历史目标和 owner 总览 |
| [07 执行与接受矩阵](07_Execution_Order_and_Acceptance.md) | R 阶段依赖、当前接受状态、范围与停止条件 |
| [A123 Sol 接受记录](../../../../maintenance/20261101_r07_a123_sol_acceptance.md) | 最新有界技术决定、task2 例外和未决限制 |
| [R 路线档案索引](../../../../archive/phase_ii_01_r_routes/README.md) | R01–R07 旧规划原文、路径映射与 SHA-256 |
| [planning manifest](planning_manifest.json) | 冻结的机器可读计划；作为历史收据只读 |
| [validation receipt](validation_receipt.json) | 原规划验证快照；不以本轮改写 |
| [10 检查点恢复与 Harness 计划](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md) | F 后继计划的输入、owner 与限制 |
| [11 多资产 solver 恢复计划](11_F05_F07_Multi_Asset_Solver_Recovery_Plan.md) | F05–F07 的恢复范围 |
| [12 F05–F07 执行手册](12_F05_F07_Execution_Playbook.md) | F 路线执行流程；F owner 状态由其 checkout 决定 |

R01–R06 和 R07 的详细旧规划已逐字节保存在 [`docs/archive/phase_ii_01_r_routes/`](../../../../archive/phase_ii_01_r_routes/README.md)。原文件路径保留短导航页及旧标题锚点。需要恢复历史实现时，以路线记录所列的固定 Git commit 和 hash 为准；活动源码不保留一套旧版本实现。

## 当前开发流程（维护者 2026-10-25 补充）

沿用现有 phase branch 和逐包 Sol/Luna review 流程。每份实现报告关联输入/输出 HEAD、提交、检查和证据；Sol 独立检查 diff 与 Evidence 后再接受或派后继工作。讨论或本地整理不代表 merge；push、merge、tag 和 Release 按仓库治理要求另行授权。

<a id="references"></a>

## 固定外部参考与采用原则

下列资料用于工程设计参考，不自动证明 GeoChora 对应 provider、资产或能力已支持。历史访问日期与完整讨论保留在 [00 总蓝图](00_Phase_II_01_Blueprint.md) 的固定来源记录和归档原文中。

| 参考资料 | 使用边界 |
| --- | --- |
| [Isaac Lab v3.0.0 Release](https://github.com/isaac-sim/IsaacLab/releases/tag/v3.0.0) | 只作为多 backend 方向参考 |
| [Isaac Lab v3.0.0 backend 与 preset 文档](https://isaac-sim.github.io/IsaacLab/v3.0.0/source/concepts/backends_and_presets.html) | 配置选择和准入设计参考 |
| [Isaac Lab v3.0.0 SceneData API](https://isaac-sim.github.io/IsaacLab/v3.0.0/source/api/lab/isaaclab.scene_data.html) | 数据 producer/consumer 生命周期参考 |
| [Isaac Sim 6.1.0 Robot Assembler](https://docs.isaacsim.omniverse.nvidia.com/6.1.0/py/source/extensions/isaacsim.robot_setup.assembler/docs/index.html) | 装配意图与 native lowering 的边界参考 |

<a id="provenance"></a>

## Provenance 与保全

R 路线原文的文件名、字节数和 SHA-256 在 [档案索引](../../../../archive/phase_ii_01_r_routes/README.md)。`planning_manifest.json`、`validation_receipt.json`、F-owned 10–12 文档、冻结 release/tag 和忽略跟踪的 workspace evidence 均按原职责保留；本页和档案不把 unresolved 状态变成已接受能力，也不为历史计划补造执行结果。
