# P99 Readiness Review（2026-10-22，运行缺口关闭后）

## 当前结论

- **两项指定运行 gate 已有真实 PASS_BOUNDED Evidence：** 公开单 Panda Position candidate 在 GeoPhys `a53a8cfe` CPU 上由同一个 `make_env()` 对象完成 reset、64 个连续真实 step、公开 observation、start/append/finalize recording 与同一 Generic H5 v3 磁盘回读；当前 pin 的 GeoPhys CPU × MuJoCo 3.8.1 native OpenGL pairing S1/S2 与资源关闭检查也通过。
- **P99：运行缺口关闭，等待维护者确定最终接受范围及独立二审。** 不自动宣布 P99 全部通过或 Phase II 完成。C02b 原有“声明交集的有界工程退出满足；未准入扩展及 Qualification 单列”结论不变。
- **B04a：单独保持 ACCEPTED-DEFERRED。** 缺少 `geophys-transition-h5/v1`、canonical trajectory outer-v0、canonical-execution-v1 三类历史原始 H5 golden bytes；本轮新 H5 是当前 candidate 实测文件，不替代历史原件或证明其 bytes-level 兼容。维护者仍需决定延期 reader 的最终范围，或另行恢复批准归档原件。
- 未执行发布 freeze、Stage-1 randomized feasibility/Judge 或 Qualification；没有授予 approval。

## 基线、保全与范围

分支 `codex/phase-ii-c03b`，执行前 Core HEAD `1e3b558d38de746e3290246171b8e578d7323603` 加本地变更。
GeoPhys checkout/gitlink 保持 `a53a8cfed7c9d6464274b5c96fca601271dc4ee4`；Menagerie 保持
`b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。未 push、merge、移动冻结引用或修改 Provider。

先保存本审阅旧版和全部既有 tracked dirty diff 到 ignored
`workspace/maintenance/p99_runtime_closure_20261022/checkpoint/`：旧审阅 SHA-256
`ddb5072e39b243a1ebbb9ffffdff7e70a582e70a57684cae921c94b3aac0e675`；既有 patch
`1f9b2e93edb9a044562d44780cb5be8dca38bf69e4b124ae0f5182748e0cf41e`。
原审阅中的 NOT READY / 无 X11 context 结论是该检查点时的事实，由本轮真实运行更新；旧日志与
`4436787e` D05b 收据继续保留为历史 Evidence，不迁移身份。冻结 Artifact、源引用、原始输入和 ignored Evidence 均保留。

范围只含公开 Position candidate 接线和当前 pin D05b pairing；未重跑 A–D 全量审计、NutAssembly 四格矩阵、
485 区间 R1 闭环，未扩展 CUDA/R1/Assembly/Task Harness。详见
[本轮运行与实现收据](P99_Runtime_Closure_2026-10-22.md)。

## P99 gate 对照

| Gate | 当前结果 | 实测交集与剩余边界 |
| --- | --- | --- |
| 新 Scene/Task public mainline | **PASS_BOUNDED** | 新 UID `panda-position-servo-candidate-v1`，GeoPhys CPU；同一个公开环境 64 transitions / 65 observations，实际运动、request/target/ack/state、时钟、身份和同文件 H5 数值回读通过；不是独立 diagnostic 路径拼接 |
| 当前 pin Physics × Renderer pairing | **PASS_BOUNDED** | 原 Position/source，GeoPhys `a53a8cfe` CPU × MuJoCo 3.8.1 native OpenGL；真实 NVIDIA EGL，fixed/hand-mounted RGB/Depth/Entity-mask，S1 3 passed、S2 12 连续区间、6 captures、双 consumer 与 close；Camera policy/Recorder 集成另属未接消费者边界 |
| 兼容/拒绝/身份/录制失败 | 有界通过，历史 bytes 单列延期 | 新 UID admission/import/错误 source/request/录制失败回归，原 selected 路线与 Position/Switch 定向检查；B04a 三类原始 H5 golden 仍 ACCEPTED-DEFERRED |
| A–D 父 Goal/全部切片 | 沿用既有逐项处置 | 未重审全量；C02c 通用切换、C05c 常规 native-rate Reader、完整 D04/D05b 等原有未完成/延期项不能自动改成 complete |
| 新 Task freeze 前置 | 本 candidate 不适用；未来 freeze 必须保留 | 无新 freeze、无 randomized feasibility/Judge；task success 始终 false，真实运动不等于任务成功 |
| Public API/docs/Skill | 本轮已更新，待 Human review | 公开 UID 与内部扩展 hook/旧诊断入口明确分层，精确交集见收据 |
| 独立 review / develop 二审 | **待维护者** | 已保全为本地提交；未推送/合并 |

## C02b 必需退出项映射

| 原批准范围 | 当前实现与 owner | 测试／真实 Evidence | 结果 |
| --- | --- | --- | --- |
| C02a/C02b 的 Entity×Group 绑定、全组预检、唯一 writer、真实 target/applied acknowledgement；Position Profile 不读取 measured force | 既有 `ControlBindingPlanV1`、`CanonicalPandaController`、Position Gripper Servo、`SelectedReferenceEnv`、`RuntimeSession` 与 C03a fault latch；保留独立 `panda-main/position-servo-v1` identity | [Position S1](C02b_E_Position_Profile_S1_Acceptance.md)、[Position S2/H5](C02b_E_Position_Profile_S2_Acceptance.md)；本地定向回归 69 passed，另有两项 stale-repeat native tests passed | 满足声明的 Position 交集 |
| P00/P99 最小双 Entity 同世界隔离施控；不是双 Entity R1 | 两个 Panda Position writers 在同一 RuntimeSession／物理世界，Entity-qualified source、resource、target、ack、state 与 reset identity | [Dual Entity Position 收据](C02b_Dual_Entity_Position_Acceptance.md)，GeoPhys CPU 与 MuJoCo CPU S1/S2/H5；提交中故障使用既有闭锁，无伪 transition | 最小双 Entity 必需项满足；无批准依据要求 dual-Entity R1 |
| 旧 PickCube R1 reset 首样 freshness，不把上一 episode 力值当作有效反馈 | GeoPhys 既有 adapter/Observation Reader 合同在 restore 与最终状态写入后产生不积分的 reset-forward sample；旧 Artifact/source identity 保留 | [reset freshness 收据](C02b_R1_Reset_Force_Freshness_Acceptance.md)：seed 31、GeoPhys a53a8cfe CPU，重复 reset 与首次 closing 检查通过 | 满足该 legacy route 的有界前置 |
| Scene-v3 R1 保留 required raw signed force，并只对实际 source/Controller/TCP/plan/build 精确准入 | typed-state v2、`ActuatorForceMeasurementV1`、`snapshot_v2()`、GeoPhys/MuJoCo 既有 cache 和 call-specific admission；唯一 signed→closing 转换仍为 `control_feedback()` | [typed-force 收据](C02b_R1_Typed_Raw_Force_Admission_Acceptance.md)：两条声明 CPU 路线的 S1 与 plan-bound interval；旧 v0/v1、Position force-free、no-plan compatibility 与拒绝反例 | 满足两条已声明的精确交集；shared manifest 未扩权 |
| R1 连续真实反馈行为与 request→feedback→target→ack→state 的闭环、H5 T/T+1 同文件数值回读 | 单 Panda Scene-v3 `production-r1` candidate，GeoPhys a53a8cfe CPU 与精确 MuJoCo 3.8.1 CPU/native build；100 Hz、每区间五个 2 ms steps | [structured R1 S2/S3 收据](C02b_Single_Panda_Structured_R1_Behavior_S2_S3_Acceptance.md)：485 intervals／486 boundaries，open/close/obstructed-close/force-hold/reopen；同一 Generic H5 v3 文件实际读回；两 provider 预先声明检查通过 | 满足声明的单 Panda CPU 行为/记录交集；任务 success、Expert completion 与 Qualification 未被替代或声称 |
| 缺 group/错 identity/过期 publication/重复 apply/apply-record fault 不得伪成功 | existing preflight 与 C03a latch；Evidence 输出目录重用明确拒绝 | structured R1 receipt 列明 69、2 和防覆盖专项回归；日志在 ignored `workspace/maintenance/c02b_r1_structured_r1_closure_20261022/` | 有界 S1/故障边界满足 |

据以上映射，原 C02b 必需出口已有实现、测试或真实 Evidence；未发现新的必需缺口。旧报告中的 `BLOCKED` 是各自签发时的准确历史结论，应保留历史语境，但当前状态已由最新 structured R1 收据和本报告收敛。候选 Artifact/source/plan 仍只作为有界候选证据，不转移到旧 PickCube Artifact，不改变冻结内容。

**当前 C02b 表述：声明交集的有界工程退出满足；未准入扩展及 Qualification 单列。** 未准入扩展包括 dual-Entity R1、CUDA R1、其他 source/Artifact/transmission/MuJoCo build、NutAssembly Guard 与通用 capability。Qualification 是独立 gate，本轮未进行。

## 独立二审交付

当前源码与 develop 差异、20 父 Goal/33 切片处置、D01a 历史不适用与当前 pin 回归、
延期/诊断例外及待维护者决定范围见 [独立二审包](Phase_II_Independent_Second_Review_2026-10-22.md)。
本包已准备，不表示独立二审通过或 Phase II 完成。

## 剩余决策

1. 维护者审阅公开 candidate 的受限 API、owner 提取和两项运行 Evidence，决定 P99 最终接受范围；按既有流程安排独立 review/develop 二审。
2. 单独确认 B04a 三类历史 H5 reader 的 ACCEPTED-DEFERRED 最终范围，或授权从批准归档恢复原始 bytes。不得以本轮新文件合成替代原件。
3. Camera policy observation/TransitionRecorder、通用切换、常规 native-rate Provider 合同及 Qualification 继续分别排期，不属于本轮待关闭运行项。

## 检查与 Skill refresh

命令、结果、一次历史旧-pin 测试失配、Evidence 路径、冷启动核对与 NOT_RUN 见
[本轮收据](P99_Runtime_Closure_2026-10-22.md)。检查以既有 GeoChora Python 环境进行；静态检查不替代 native Evidence。
完成后停止，等待维护者指令。
