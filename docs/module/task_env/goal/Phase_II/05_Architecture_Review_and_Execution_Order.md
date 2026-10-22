# Phase II Architecture Review — 当前状态、验收范围与二审入口

日期：2026-10-22。本文是 **20 个父 Goal、33 个实施切片及 P00/P99** 的唯一当前处置表。
本轮以 2.18 MB 轻量二审包为审阅入口，对照整合前源码 `a5ba537`（其中受审功能源码 `52c61dc`）、canonical docs 和原始收据，整理文档与分支；没有新增实现或重新授予 Qualification。
**结论：全部 Goal 已逐项处置，但并非原规划所有广度都已实现。声明交集的工程出口与两项 P99 运行 gate 已有有界证据；延期/诊断例外的最终接受以及 v2.0.0 发布仍待网页独立二审与维护者决定。**

<a id="scope"></a>

## 1. 文档、范围与事实优先级

Phase II 目录固定为九份文件：01–04 为 A/B/C/D 目标契约，05 为当前状态/审阅入口，A/B/C/D_Development_Record.md 为开发与验收核心记录。
旧 00 蓝图、06 P00 和中间专题报告的核心事实已归并；完整旧文由不可变 Git commit/本地备份恢复，不保留第二套当前状态。

依赖方向为 `task_env Core → Provider public/runtime-facing API`。复用现有 Scene/Artifact、Registry、TaskDefinition、RuntimeSession、Controller、Environment、Recorder、Camera owners；不新增第二套 Runtime/TaskEnv/Provider。
Native physics state 只有 Provider 一个演化 owner，Renderer 只消费只读 publication；Task、Solution、Experiment、Evidence 与 Judge 分开。
实施范围为 A–D；Task Harness/Agent Workflow、通用 Batch/Policy Runner、Assembly/attachments/topology hot swap 为后续范围。

事实优先级：当前源码/生产调用者 → canonical contracts → source-bound tests/Evidence → 规划/历史讨论。
canonical 入口：[architecture](../../../../global/architecture.md)、[ownership](../../../../global/ownership.md)、[Public API](../../public-api.md)、[Artifact/Evidence](../../task-artifact.md)、[qualification](../../qualification.md)。
发布资格基线仍是 v1.1.0 的唯一 capability matrix，本轮不改其 bytes、冻结 tags、历史 decisions 或新 Task freeze 要求。

<a id="status"></a>

## 2. 20 个父 Goal 的当前处置

“有界出口满足”表示对应精确交集的工程证据齐备，不代表原设计所有可扩展方向均实现，也不是 QUALIFIED。
ACCEPTED-DEFERRED 是已有工程延期处置，发布是否接受该范围仍待维护者；没有把缺失证据改写为 PASS。

| 父 Goal | 核心目标 | 当前工程处置 | 关键边界 / Evidence |
| --- | --- | --- | --- |
| A01 | Asset/Entity identity | 声明交集有界出口满足 | 仅本阶段开发记录列明范围，非通用支持/Qualification；[证据](A_Development_Record.md#a01) |
| A02 | Frame/Articulation | 声明交集有界出口满足 | 仅本阶段开发记录列明范围，非通用支持/Qualification；[证据](A_Development_Record.md#a02) |
| A03 | Robot/Group/Scene | 声明交集有界出口满足 | 仅本阶段开发记录列明范围，非通用支持/Qualification；[证据](A_Development_Record.md#a03) |
| A04 | Source/Registry mapping | 声明交集有界出口满足 | 仅本阶段开发记录列明范围，非通用支持/Qualification；[证据](A_Development_Record.md#a04) |
| A05 | 静态集成/兼容投影 | 声明交集有界出口满足 | 仅本阶段开发记录列明范围，非通用支持/Qualification；[证据](A_Development_Record.md#a05) |
| B01 | strict Task Source/Hook metadata | 声明交集有界出口满足 | 仅本阶段开发记录列明范围，非通用支持/Qualification；[证据](B_Development_Record.md#b01) |
| B02 | 固定 topology Role/ResetPlan | 声明交集有界出口满足 | 仅本阶段开发记录列明范围，非通用支持/Qualification；[证据](B_Development_Record.md#b02) |
| B03 | 只读 Predicate/temporal commit | 声明交集有界出口满足 | 仅本阶段开发记录列明范围，非通用支持/Qualification；[证据](B_Development_Record.md#b03a) |
| B04 | Artifact/codec/兼容基线 | 有界实现；ACCEPTED-DEFERRED | 三类历史 H5 原件缺失，bytes-level 兼容未证明；[证据](B_Development_Record.md#b04a) |
| B05 | legacy 语义桥接 | 声明交集有界出口满足 | 仅本阶段开发记录列明范围，非通用支持/Qualification；[证据](B_Development_Record.md#b05) |
| C01 | 静态计划/动态 admission | 声明交集有界出口满足 | 仅本阶段开发记录列明范围，非通用支持/Qualification；[证据](C_Development_Record.md#c01) |
| C02 | binding/dispatch/safe switch | C02a/b 有界出口满足；C02c 有界/延期 | 只支持声明的 Position switch；dual-Entity R1/CUDA R1 非必需扩展；[证据](C_Development_Record.md#c02b) |
| C03 | scalar fault/Stop/Outcome | 声明交集有界出口满足 | 仅本阶段开发记录列明范围，非通用支持/Qualification；[证据](C_Development_Record.md#c03a) |
| C04 | Observation/info/diagnostics | 声明交集有界出口满足 | 仅本阶段开发记录列明范围，非通用支持/Qualification；[证据](C_Development_Record.md#c04) |
| C05 | storage/external Solutions | 存储/PickCube 有界通过；NutAssembly 分层处置 | GeoPhys 四格为诊断例外，常规 native-rate Reader 合同延期；[证据](C_Development_Record.md#c05a) |
| D01 | source materialization/reset | 声明交集有界出口满足 | 仅本阶段开发记录列明范围，非通用支持/Qualification；[证据](D_Development_Record.md#d01) |
| D02 | typed state publication | 声明交集有界出口满足 | scalar/free-base 与精确 raw-force；spherical/contact/native alias 等未准入；[证据](D_Development_Record.md#d02) |
| D03 | dynamic visual sync | 声明交集有界出口满足 | 仅本阶段开发记录列明范围，非通用支持/Qualification；[证据](D_Development_Record.md#d03) |
| D04 | RGB/Depth/Entity mask | 直接 CameraSession 有界通过；consumer/广度延期 | policy/Recorder 未接入；semantic/free-joint/async 未实现；[证据](D_Development_Record.md#d04) |
| D05 | selection/native pairing | 精确当前 pin pairing 通过；广度延期 | 不是全部 pairing matrix 或正式 Qualification；[证据](D_Development_Record.md#d05) |

<a id="slice-order"></a>

## 3. 切片依赖与推荐执行顺序

这是批准规划的 33 切片拓扑与现有结果映射，不是要求重新施工。C02b-P/E、typed-force/freshness 等是内部检查点，不额外计数。
历史序号 18–22 等执行记录保留当时含义；当前查找以切片 ID 为准。

| 顺序 | 切片 | 直接前置 | 当前结果 / 证据 |
| ---: | --- | --- | --- |
| 01 | A01 | P00 | 有界证据齐备；[开发记录](A_Development_Record.md#a01) |
| 02 | A02 | A01 | 有界证据齐备；[开发记录](A_Development_Record.md#a02) |
| 03 | B04a | A02 | 有界通过；历史 golden ACCEPTED-DEFERRED；[开发记录](B_Development_Record.md#b04a) |
| 04 | D02a | A02 | 有界证据齐备；[开发记录](D_Development_Record.md#d02) |
| 05 | C01a | B04a、D02a | 有界证据齐备；[开发记录](C_Development_Record.md#c01) |
| 06 | D05a | C01a、A02 | 有界证据齐备；[开发记录](D_Development_Record.md#d05) |
| 07 | A03 | A02 | 有界证据齐备；[开发记录](A_Development_Record.md#a03) |
| 08 | A04 | A03 | 有界证据齐备；[开发记录](A_Development_Record.md#a04) |
| 09 | A05 | A04 | 有界证据齐备；[开发记录](A_Development_Record.md#a05) |
| 10 | D01a | A05、B04a、C01a | 有界证据齐备；[开发记录](D_Development_Record.md#d01) |
| 11 | D02b | D02a、D01a | 有界证据齐备；[开发记录](D_Development_Record.md#d02) |
| 12 | B01 | A05、B04a、D01a、D02b | 有界证据齐备；[开发记录](B_Development_Record.md#b01) |
| 13 | B02 | B01、D01a、D02b | 有界证据齐备；[开发记录](B_Development_Record.md#b02) |
| 14 | B03a | B02、D02b | 有界证据齐备；[开发记录](B_Development_Record.md#b03a) |
| 15 | B03b | B03a | 有界证据齐备；[开发记录](B_Development_Record.md#b03b) |
| 16 | B04b | B04a、B03b、D05a | 有界证据齐备；[开发记录](B_Development_Record.md#b04b) |
| 17 | B05 | B04b | 有界证据齐备；[开发记录](B_Development_Record.md#b05) |
| 18 | C01b | B05、D02b | 有界证据齐备；[开发记录](C_Development_Record.md#c01) |
| 19 | D01b | D01a、B04b、C01b | 有界证据齐备；[开发记录](D_Development_Record.md#d01) |
| 20 | C02a | A03、C01b、D02b | 有界证据齐备；[开发记录](C_Development_Record.md#c02a) |
| 21 | C05a1 | C02a、C01b、D05a | 有界证据齐备；[开发记录](C_Development_Record.md#c05a) |
| 22 | C05a2 | C05a1 | 有界证据齐备；[开发记录](C_Development_Record.md#c05a) |
| 23 | C05a3 | C05a1、C05a2 | 有界证据齐备；[开发记录](C_Development_Record.md#c05a) |
| 24 | C03a | C02a、D01b、C05a2 | 有界证据齐备；[开发记录](C_Development_Record.md#c03a) |
| 25 | C04 | C03a、D02b | 有界证据齐备；[开发记录](C_Development_Record.md#c04) |
| 26 | C02b | C02a、C03a、C04、C05a2、D01b | 有界证据齐备；[开发记录](C_Development_Record.md#c02b) |
| 27 | C03b | C03a、C04、C05a2 | 有界证据齐备；[开发记录](C_Development_Record.md#c03b) |
| 28 | C02c | C02b、C03b、C05a2 | Position switch 有界通过；通用切换延期；[开发记录](C_Development_Record.md#c02c) |
| 29 | C05b | C02b、C03b、C04、C05a3 | 有界证据齐备；[开发记录](C_Development_Record.md#c05b) |
| 30 | C05c | C05b、D02b | 指定 S2/S3 通过；GeoPhys 为诊断例外；[开发记录](C_Development_Record.md#c05c) |
| 31 | D03 | D01b、D02b、D05a | 有界证据齐备；[开发记录](D_Development_Record.md#d03) |
| 32 | D04 | D03、C04、C05a2 | 直接 CameraSession 有界通过；consumer/广度延期；[开发记录](D_Development_Record.md#d04) |
| 33 | D05b | D05a、D04、C01b | 直接 CameraSession 有界通过；consumer/广度延期；[开发记录](D_Development_Record.md#d05) |

<a id="p00"></a>

## 4. P00、兼容保护与实现路线评估

P00 是额外启动审计，不计入 20/33。它建立 owner/caller、legacy routes、已退役 detector、版本矩阵、真实运行/资源与既知失败清单。
原最小双 Entity gate 由同世界两个独立 Panda Position writer 的 S2/H5 满足，不能扩大成 dual-Entity R1 或 Assembly 的新前置。
旧 samples/hash、strict version dispatch、精确 timebase、task success/Expert completion/episode end 分离、故障闭锁与 Provider-private-state 禁令继续保护。
新 Task Source/Artifact 仍是 candidate；Stage-1 validation/randomized feasibility/独立 Human Judge 是新 freeze 的前置。

架构结论：跨阶段提前确定 typed-state/version/selection 契约，再做最小真实 materialization，降低了纯静态 A→B→C→D 最后联调的风险。
复用现有 owners 的方向一致；位置 Profile 解耦、真实 R1 required force 和高频 native Guard 分别验收，避免因一个 Profile 的需求冻结全部施工。
主要工程风险仍是精确硬编码 admission 的维护成本、同一 API 下 legacy/candidate 多路线、常规 Provider 高频合同与 Camera consumer 接口尚未闭合；应按 owner 小切片扩展，不以新的抽象替代。

<a id="p99"></a>

## 5. P99 与最终接受边界

| Gate | 当前事实 | 最终状态 |
| --- | --- | --- |
| 新 Scene/Task public mainline | 公开 `panda-position-servo-candidate-v1`，同一 make_env 对象完成 reset→64 steps→65 observations→同文件 Generic H5 v3 数值/identity 回读 | PASS_BOUNDED；不是新 Task success/freeze |
| 当前 pin Physics×Renderer | a53 GeoPhys CPU × MuJoCo 3.8.1 native OpenGL/NVIDIA EGL；双 camera、6 captures、S1 3 passed、S2/consumer isolation/close 通过 | PASS_BOUNDED；dynamic CameraSession 直接消费者 |
| 旧格式 compatibility | codec/identity/negative tests 与当前轨迹回读有界通过 | 三类历史 H5 golden 继续 ACCEPTED-DEFERRED |
| 完整原规划广度 | 当前表明确列出范围与未实现/未准入项 | 不标全部 full-complete |
| 独立二审/维护者接受 | 本次提交供网页 reviewer 评估 | PENDING_REVIEW |
| v2.0.0 / Qualification | 尚无 release tag、发布 freeze 或新 qualification decision | 本轮不执行 |

运行缺口已关闭；没有外部 blocker 机械阻止审阅。是否将这些有界交集和显式延期作为 v2.0.0 接受范围，需要二审明确决定。

<a id="risks"></a>

## 6. 风险优先级与维护者决策

| 优先级 | 问题 / 原因与影响 | 二审应作的具体决定 |
| --- | --- | --- |
| P1 | B04a 三类历史原 H5 缺 bytes，现有 synthetic/新 H5 不能证明历史 reader 兼容 | 接受精确 reader 延期、授权恢复批准原件或另审 retirement；不能默认为 PASS |
| P1 | GeoPhys C05c 四格每 2 ms 调用 public CPU snapshot，与通常低频指引不同；实际成功不等于常规合同 | 是否接受 diagnostic-only 阶段范围；常规支持另由现有 Provider owner 补合同和受影响 CPU/CUDA 验证 |
| P1 | dynamic Camera 输出未进 policy observation/TransitionRecorder | 是否把相机任务闭环/录制留作下一阶段；当前只能接受 direct CameraSession pairing |
| P1 | P99 与 release/Qualification 不同 | 审阅确认当前 20/33 的有界范围与延期后，再独立决定 v2.0.0，不能由本次整理自动发布 |
| P2 | typed R1 admission 绑定 source/Controller/TCP/plan/build/pin；其他构建未准入 | 后续变化做精确 delta audit + targeted S1/S2；不只替换 SHA，不扩 shared manifest |
| P2 | dual Position 历史 S2 绑定 4436787e；当前 pin 的替代公开单 Panda/pairing 不等于双 Entity 重跑 | 接受历史精确交集或要求单独 a53 dual probe；不要求无批准依据的 dual R1 |
| P2 | C02c 只实现同 schema 单 Panda Position switch，D04/D05 只覆盖受限 source/modality/pairing | 明确通用切换、semantic/free-joint/async、广泛 pairing 是后续范围 |
| P2 | 一份早期 eb870 JSON 原件已丢失，当前 pin 有独立替代证据 | 接受该历史 provenance 限制；不重造“恢复原件” |

建议二审先审这些范围决定，再审错误 identity/故障/版本拒绝与真实回读链。若要求新增实现，按上述风险分成一至两个 owner 切片，另行授权；本轮停止在整理交付。

### 本轮状态勘误

| 漂移 / 冲突 | 整理后的单一解释 |
| --- | --- |
| 旧 31 切片、历史序号与后来拆分并存 | 当前 20 父 Goal / 33 切片；历史序号只解释原收据 |
| C02b BLOCKED / PARTIAL 与后续真实 R1 回读通过并存 | 声明交集有界工程出口满足；旧阻塞经过保留在历史原文，不作为当前状态 |
| 旧 eb870/443 pin、X11 失败与当前 a53/EGL pass 混用 | 每条 receipt 绑定原 pin；当前 pairing 有独立 S1/S2，dual Position 仍标历史 pin |
| README 仍称本地未提交、未进 develop | 本轮正常集成 develop；独立二审/发布未完成，不与分支同步混为一谈 |
| 设计允许重叠 Group 与 Scene-v3 实际拒绝重复 writer | 当前 v3/compiled plan 按唯一有效 writer；没有通用 arbitration |
| 两项历史 reader failure 被误当生产缺陷 | 实为测试用了已支持版本，改用 v99 后拒绝检查通过，原日志保留 |

模块 Skill 本轮仅刷新这些文档导航与当前状态措辞；复核现有 public factory、typed state、Solution lifecycle 和 Camera owners，静态 checker/quick validation 与源码导航核对分别记录，不据此增加运行能力；未启动独立 Agent 二审或运行新的 native 示例。

<a id="evidence"></a>

## 7. 轻量包、Evidence 组成与验证层级

正式二审入口为 `workspace/maintenance/phase_ii_second_review_compact_20261022_001/Phase_II_Light_Review_2026-10-22.zip`，
2,182,883 bytes，SHA-256 `d8aad09379a0181ec85b3b52b9f367ff856484812627df22a66f184abc8b2d36`。
包含原字节的 67 个文件（9 份小型 H5）、源码 bundle/diff、收据、日志与 manifest；完整包约 85.52 MB 仍保留。
四份 NutAssembly H5 共 84,843,948 bytes，均无 RGB，因完整 native samples/结构化 request-feedback-target-ack-state/身份的 logical JSON 仍大；18 份相机 raw 文件共 3,745,503 bytes。
这 22 份大文件外置并逐项记录 path/size/SHA。轻量包可导航/核对收据，不能独立重做四组逐值 S3 或相机像素级复核。
整合后的九文档/最新 develop 与恢复信息在本轮增补轻量包单独给出，原轻量包和原始 Evidence 不覆盖。

S0 为 static/schema；S1 为 contract/identity/failure；S2 为最小真实 Provider；S3 为 rollout/record/read 集成；S4/Qualification 独立。
测试数量不累加成 Qualification。clock 推断、native sample/index 佐证与独立完成计数器分开报告；不同 Provider 不要求接触力逐值一致。
本轮为文档/分支整理，只运行目录/状态/依赖/链接、Skill 与包保全检查；没有新 native campaign，历史结果以各记录原 source/pin 为准。

<a id="history"></a>

## 8. 中间报告迁移与历史追溯

下表左列固定到整合前 `a5ba537` 的原始文件；右列为当前核心内容。原草案 `a299d8b`、二审 `8bc95ef` 和历史 source/pin 记录继续可恢复。
保留的 01–04 只承担目标契约，不与 A–D 开发记录争夺当前验收状态；旧“尚未提交/未推送/BLOCKED”只在历史原文中解释当时检查点。

| 整合前原文（固定 commit） | 当前核心内容 |
| --- | --- |
| [00_Phase_II_AD_Implementation_Blueprint.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/00_Phase_II_AD_Implementation_Blueprint.md) | [05_Architecture_Review_and_Execution_Order.md](05_Architecture_Review_and_Execution_Order.md) |
| [01_Phase_A_Core_Object_Model.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/01_Phase_A_Core_Object_Model.md) | [01_Phase_A_Core_Object_Model.md](01_Phase_A_Core_Object_Model.md) |
| [02_Phase_B_Task_Semantics.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/02_Phase_B_Task_Semantics.md) | [02_Phase_B_Task_Semantics.md](02_Phase_B_Task_Semantics.md) |
| [03_Phase_C_Execution_Lifecycle.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/03_Phase_C_Execution_Lifecycle.md) | [03_Phase_C_Execution_Lifecycle.md](03_Phase_C_Execution_Lifecycle.md) |
| [04_Phase_D_Physics_Rendering.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/04_Phase_D_Physics_Rendering.md) | [04_Phase_D_Physics_Rendering.md](04_Phase_D_Physics_Rendering.md) |
| [05_Architecture_Review_and_Execution_Order.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/05_Architecture_Review_and_Execution_Order.md) | [05_Architecture_Review_and_Execution_Order.md](05_Architecture_Review_and_Execution_Order.md) |
| [06_P00_Baseline_Caller_Compatibility_and_Feasibility_Audit.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/06_P00_Baseline_Caller_Compatibility_and_Feasibility_Audit.md) | [05_Architecture_Review_and_Execution_Order.md](05_Architecture_Review_and_Execution_Order.md) |
| [C02b_Dual_Entity_Position_Acceptance.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/C02b_Dual_Entity_Position_Acceptance.md) | [C_Development_Record.md](C_Development_Record.md) |
| [C02b_E_Position_Profile_S1_Acceptance.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/C02b_E_Position_Profile_S1_Acceptance.md) | [C_Development_Record.md](C_Development_Record.md) |
| [C02b_E_Position_Profile_S2_Acceptance.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/C02b_E_Position_Profile_S2_Acceptance.md) | [C_Development_Record.md](C_Development_Record.md) |
| [C02b_Feedback_Source_and_Sampling_Audit.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/C02b_Feedback_Source_and_Sampling_Audit.md) | [C_Development_Record.md](C_Development_Record.md) |
| [C02b_P_Position_Based_Profile_Review.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/C02b_P_Position_Based_Profile_Review.md) | [C_Development_Record.md](C_Development_Record.md) |
| [C02b_R1_Reset_Force_Freshness_Acceptance.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/C02b_R1_Reset_Force_Freshness_Acceptance.md) | [C_Development_Record.md](C_Development_Record.md) |
| [C02b_R1_Typed_Raw_Force_Admission_Acceptance.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/C02b_R1_Typed_Raw_Force_Admission_Acceptance.md) | [C_Development_Record.md](C_Development_Record.md) |
| [C02b_Recovery_Architecture_Review.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/C02b_Recovery_Architecture_Review.md) | [C_Development_Record.md](C_Development_Record.md) |
| [C02b_Single_Panda_Structured_R1_Behavior_S2_S3_Acceptance.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/C02b_Single_Panda_Structured_R1_Behavior_S2_S3_Acceptance.md) | [C_Development_Record.md](C_Development_Record.md) |
| [C03b_Stop_Outcome_Receipt_2026-10-21.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/C03b_Stop_Outcome_Receipt_2026-10-21.md) | [C_Development_Record.md](C_Development_Record.md) |
| [C05b_External_Solution_S2_S3_Acceptance.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/C05b_External_Solution_S2_S3_Acceptance.md) | [C_Development_Record.md](C_Development_Record.md) |
| [C05b_Public_Lifecycle_S1_Acceptance.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/C05b_Public_Lifecycle_S1_Acceptance.md) | [C_Development_Record.md](C_Development_Record.md) |
| [C05c_GeoPhys_Gripper_Cadence_Comparison_2026-10-22.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/C05c_GeoPhys_Gripper_Cadence_Comparison_2026-10-22.md) | [C_Development_Record.md](C_Development_Record.md) |
| [C05c_NutAssembly_Public_Native_S1_Acceptance.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/C05c_NutAssembly_Public_Native_S1_Acceptance.md) | [C_Development_Record.md](C_Development_Record.md) |
| [GeoChora_PhaseII_Second_Review_develop_8bc95ef.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/GeoChora_PhaseII_Second_Review_develop_8bc95ef.md) | [05_Architecture_Review_and_Execution_Order.md](05_Architecture_Review_and_Execution_Order.md) |
| [P99_Readiness_Review_2026-10-22.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/P99_Readiness_Review_2026-10-22.md) | [05_Architecture_Review_and_Execution_Order.md](05_Architecture_Review_and_Execution_Order.md) |
| [P99_Runtime_Closure_2026-10-22.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/P99_Runtime_Closure_2026-10-22.md) | [05_Architecture_Review_and_Execution_Order.md](05_Architecture_Review_and_Execution_Order.md) |
| [Phase_II_Independent_Second_Review_2026-10-22.md](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/Phase_II_Independent_Second_Review_2026-10-22.md) | [05_Architecture_Review_and_Execution_Order.md](05_Architecture_Review_and_Execution_Order.md) |

<a id="branches"></a>

## 9. 分支整理与 v2.0.0 审阅安排

维护者已授权将本轮整理后的最新提交正常快进到 develop，并清理中间开发分支；main 与历史 v1 分支/tags 保留原 SHA。
此前 phase-ii-b 冻结指针属于已完成协作的历史约定；本轮新的清理授权以可恢复 bundle 保全其原 SHA，不修改旧提交内容或冻结发布 refs。
父仓库最终只保留 develop、main 和既有 v1.1.0 分支；Provider 子模块的分支、pin 与历史 detached worktrees 不在本轮清理范围。
只使用正常提交/快进与明确分支删除，不重写 develop/main 历史。网页独立二审后再决定 v2.0.0；本轮不打 v2 tag，不把 develop 合入 main。

<a id="preservation"></a>

## 10. 保全与本轮复核

原始 25 份 Markdown bytes、每文件 SHA、所有分支 refs/worktrees 和完整可恢复 Git bundle 保存在 ignored
`workspace/maintenance/phase_ii_docs_consolidation_20261022_001/`：`original_phase_ii_docs.tar.gz`、`preservation_before.json`、`refs_before.txt`、`worktrees_before.txt`、`branches_before.bundle`。
bundle 已验证为完整历史；独立恢复 checkout 可从 bundle 原 refs 恢复，不必保留中间活动分支。
轻量包、大包、原始 H5、失败日志与失落原件说明保留，不重算/改写实验结论；不会把备份 bundle 的体积混入 10 MB 二审 Evidence 预算。
实际文档检查、Skill 导航/检查、分支与远端核验、轻量包增补清单见同目录交付 receipt；commit/ref 的最终值从 Git 与 receipt 读取，不在正文写入自指 SHA。

本轮文档/Goal 静态复核：九文件布局、20 父 Goal/33 切片拓扑、450 个本地链接/锚点及两项 Skill 检查通过；原轻量包 CRC/SHA 与旧文档备份核对通过。
完整 `validate_docs.py` 退出 1，仅报告历史 docs/task_env 数量上限（当前 67/23，历史限制 66/22）及相对旧 consolidation 基线的 139 项既有非文档路径；无链接/锚点/冻结数据错误。
本次相对 `a5ba537` 没有生产 Python、Provider 或 gitlink 差异；不为获得全绿而改写历史 validator/inventory。
