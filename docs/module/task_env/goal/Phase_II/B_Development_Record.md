# Phase B 开发记录 — Task Source、Reset、Semantics 与 Artifact

日期：2026-10-22。B01–B05 的有界工程记录齐备；B04a 三类历史 H5 golden 为 **ACCEPTED-DEFERRED**，不能写成全部历史 bytes 兼容已通过。
目标契约见 [02_Phase_B_Task_Semantics.md](02_Phase_B_Task_Semantics.md)；统一状态见 [05](05_Architecture_Review_and_Execution_Order.md)。

## B01

在既有 environment owner 实现 provider-free `TaskSourceV1`、strict YAML loader 与 Hook metadata。
允许 identity、Scene ref、显式 Entity 候选 Role 和受限 Hook declaration；重复 YAML key、未知字段/version/type/cardinality/placement 拒绝。
保留 YAML merge-key 的本地覆盖语义。首版 Role 为 `exactly_one`，不建立 tags registry。
Hook 记录 kind/ID/version/code hash、输入、依赖、determinism/phase/pure-stateful，不动态 import 或执行任意 Hook。
专项 6 passed，与 legacy/config/reference 合计 35 passed；隔离 import 未加载 native Provider。

## B02

扩展现有 artifacts/execution 为 `TaskInitializationV1`、`RoleBindingV1`、`EpisodeResetPlanV1`。
固定 topology；按规范化 Entity 候选和 per-role SHA-256→PCG64 domain 选择。相同 seed/version/Scene 可复现，独立 Role 不干扰。
`pcg64-v0` 保留旧顺序，`pcg64-domain-v1` 为每 dimension 独立 RNG，`frozen-authored-v0` 只接受空随机化集。
位置 x/y/z 与已声明 semantic/role joint position 有界支持；未知 dimension 不猜映射。
`to_provider_sample()` 返回原 ResetSample v0；`RuntimeSession.reset_plan()` 先检查精确 Scene/source identity，再复用 requested/measured realization tolerance gate。
非法 topology、overlap、类型、bounds、Scene hash 或 realization 拒绝后不能 rollout。
历史 B01/B02 专项 13 passed，B01/B02/D01a/D02b 联合 20 passed，既有兼容 29 passed。
GeoPhys/MuJoCo CPU 三自由刚体 reset 与 A05 source 路线的声明证据分开；candidate 不获 freeze。

## B03a

既有 `TaskDefinitionBase` / `TaskLifecycleAdapter` 增加只读 `TaskEvaluationContextV1` 与 predicate 入口。
context 区分 requested action、AppliedControl、前后状态、Timebase 和可选 NativeIntervalEvidence；配置频率不伪装成实测 interval。
`available/False`、`unavailable`、`no_evaluator` 分开。重复读取不提交 memory。
PickCube 保持 lift-only；Pendulum torque cost、scalar/batch 五步窗口不变；Expert Guard 仍归 task Solution。
历史联合 50 passed；依赖集 25 passed。

## B03b

temporal rules 支持 rising-edge、evaluation-boundary sample dwell 和 ordered rising-edge sequence。
可变状态归同一 lifecycle adapter，`commit_temporal_predicates()` 是唯一提交点；reset 清除。
完全相同 boundary/input 重复提交幂等；同 boundary 冲突或乱序拒绝，gap/missing 清连续进度。
dwell 样本数不等于物理秒或 native substep 数；native callback 不提交 Task memory。
专项 15 passed，含 B03a/reference/selected 合计 65 passed；仅 scalar commit，batch temporal commit 未准入。

## B04a

保护矩阵覆盖 TaskArtifact/Scene/Reset/RealizedState/Execution/Timebase/Capability/Camera 与三类独立 trajectory codecs。
旧 mapping/hash、原始文件 bytes 与新版本 identity 分开；未知 discriminator/字段拒绝，不猜 key 自动升级。
两份 TaskArtifact v0 fixtures pin 原文件 SHA、解码 mapping/hash 和现有 builder；这不是三类历史 H5 的替代。

| 数据域 | 已有验证与边界 |
| --- | --- |
| task-artifact-v0 / world-v0 | frozen mapping/hash fixtures 与 strict decode/roundtrip |
| Scene v1/v2/v3 | 各自字段集合与 identity；不是 world-v0 的自动升级 |
| TaskArtifact v1 / typed state / execution selection | 各 owner 版本化；旧未带 discriminator 的 ExecutionSpec/Timebase mapping 保持合法 |
| Generic H5 / canonical outer / execution stream | 各自 version routing、malformed input 与 bounded 新格式回读；不合并格式域 |
| 三类历史 H5 golden | `geophys-transition-h5/v1`、canonical outer-v0、canonical execution-v1 原始 bytes 缺失，ACCEPTED-DEFERRED |

source-bound 重建：Core `f9543b8725d2990966743f49cebf9d68493b6b06` / GeoPhys `4436787e`，6 passed；
`workspace/phase_ii_coordination/evidence/cmd-0001/worker/run_metadata.json` SHA
`7dd71a134e4878ee891d245f7bcb32464eb15e5cef213c279e14fe7f5fd4d788`。
不得将改 schema 的 v2 synthetic 文件称作原始 v1 golden。
D04 曾报告的两个 reader failure 后证实是测试将支持的 v3/v1 当未知版本；修正为 v99 后拒绝检查通过，见 [D04 勘误](D_Development_Record.md#d04)。

## B04b

`TaskArtifactV1`、`decode_task_artifact()` 与 `compile_task_artifact_v1()` 复用现有 artifacts/Task Source owners。
显式接收 TaskSource、精确 Scene 与旧 v0 semantic bridge；Frame/Joint 别名须类型化显式绑定，解析结果进入新 identity。
Scene 以 schema/scene_id/hash 引用，不复制世界；v0 尚无法表示的 geometry/contact/parameters 等留 source-retained 字段指针。
ActionIntent、world convention、Observation requirements、Initialization、Semantics、精确 Timebase 与 RequiredCapabilitySet 保留。
TaskSource 尚非完整独立 reward/predicate DSL；B03b temporal rules 未因此自动序列化，Hook 闭包也未获得任意执行能力。
历史 codec/legacy 12 passed，相关联合 97 passed；新增 v1 是 candidate，旧 selected routes 不自动切换 Artifact。

## B05

PickCube/NutAssembly 通过现有 evaluator 和明确结构映射比较相同 deterministic state fixture 下的 reward/success/metrics。
PickCube lift 标准、NutAssembly Task success 与 Outcome/Expert completion 分离；原 ResetSample、Artifact 和 selected 路线保持。
专项 2 passed，相关 legacy/outcome/selected 80 passed。这是语义桥接，不是新 v1 实际执行/replay/Stage-1 feasibility。

## B 工程出口

Core `b3f8dc4381708b76c5003dde5da138d90518aefa` / GeoPhys `4436787e` 上，B01–B05、D02b 与 C01a 联合 **56 passed**，22.22 s。
Evidence：`workspace/maintenance/phase_ii_closure_20261020_001/run_metadata.json`，stdout SHA
`4b09b9fa2d1913cffd199073b868d240adebc31891ac00a2375c1de627af47bc`。
早期协调 report.md 把远端 SHA 写为 `1fb3a55…` 属笔误，以同目录 report.json 与当时核对的 `b3f8dc4…` 为准。
当时 frozen `codex/phase-ii-b` 指针是历史协作记录；维护者本轮授权在备份后清理中间分支，不改变这些 Evidence 的 source identity。
本轮只整合文档，没有重跑这些历史组合。

原始完整契约/命令/收据：[整合前 B 文档](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/02_Phase_B_Task_Semantics.md)。兼容延期的最终接受范围与恢复/退休决定仍待二审。
