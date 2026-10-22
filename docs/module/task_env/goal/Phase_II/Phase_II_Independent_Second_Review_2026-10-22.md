# Phase II 独立二审交付包（2026-10-22）

## 交付结论与阅读入口

**工程实现与现有有界证据可提交独立二审；P99 最终接受范围、延期处置和 Phase II 完成决定尚未作出。**
本文件是下列源码点的交付快照，不是新的 capability matrix、Judge approval 或持续维护的第二份执行表。
当前执行顺序及处置仍由 [05 执行表](05_Architecture_Review_and_Execution_Order.md) 维护。

建议二审顺序：本包的源码/范围 → 20 父 Goal 和 33 切片索引 → [Public API](../../public-api.md) →
[P99 readiness](P99_Readiness_Review_2026-10-22.md) 与 [P99 实测收据](P99_Runtime_Closure_2026-10-22.md) →
C02b/C05c 专项收据 → 待维护者决定的范围。历史规划中的授权、READY、BLOCKED、未运行等措辞均按各自签发时点解释，
不代表本轮二审批准，也不能以当前实测替换历史 source identity。

## 源码、检查点与相对 develop 的范围

| 项目 | 固定值 / 解释 |
| --- | --- |
| 分支 | `codex/phase-ii-c03b`，本地 topic branch；未推送/合并 |
| 本轮开始 HEAD | `1e3b558d38de746e3290246171b8e578d7323603` 加上一轮 candidate/pairing/docs 工作树 |
| 先保全的检查点 | `517c44a0dcff52c9a33bd436851ceaf06390c5f4`，包含公开 candidate、pairing 复验入口、测试和全部当时报告 |
| **受审源码点** | **`52c61dc3079d852b9144d66de5d7b2fe2695ee8f`**；相对上一个检查点只调整现有 D01a 测试，无 runtime/功能变化 |
| 本交付文档 | 后续仅文档/Skill 提交；最终 HEAD、tree、bundle ref 和校验值见包内 `delivery_manifest.json`，避免文档自引用自己的 commit hash |
| fetch 到的 develop | `339878ed3134e8f6ddb612c50e33ef0f6cd0a18a`；本轮 `git fetch --no-tags public develop` 成功；FETCH_HEAD、本地 develop、public/develop 一致 |
| merge-base / 提交关系 | merge-base 同为 `339878e…`；源码点相对 develop **ahead 4 / behind 0** |
| GeoPhys gitlink / checkout | **`a53a8cfed7c9d6464274b5c96fca601271dc4ee4`**，无本轮修改；与上述 develop 也相同 |
| Menagerie gitlink / checkout | `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`，保持原值 |
| Phase II 历史规划基准 | `f292df149f41520b484ff27cf2ff78a584903013`；A/B/C/D 既有大量实施已在 develop，不能将本次增量 diff 冒称全部 Phase II 源码 |

源码比较固定使用 `git diff 339878e… 52c61dc…`，**53 files，+4729 / -612**。完整路径/状态、diffstat、
提交列表与 binary patch 位于本地交付目录；本轮最后的文档增量另由 final bundle/manifest 覆盖。

| 相对 develop 的改动组 | owner 与二审重点 |
| --- | --- |
| 公开单 Position candidate | `tasks/position_candidate/`、`tasks/__init__.py`；一个显式 UID、受限 config、task-owned source/builder；旧 diagnostic/test helpers 转用同一实现，源输入 bytes 与身份不变 |
| 单 Panda R1 / typed force | `runtime/sessions/{api,control,mujoco}.py`、R1 candidate/diagnostics/tests；精确 source/Controller/TCP/plan/build admission、signed force provenance、reset/step cache、旧 routes 与 Position force-free 边界 |
| C05c cadence comparison | `tasks/nut_assembly/{task,solution}.py`、`tasks/reference_env.py`、`controllers/canonical/gripper_execution.py` 与诊断/tests；native sample identity、100 Hz update/hold 与 500 Hz update、Guard/H5；Reader 使用仍是 diagnostic exception |
| P99/pairing 验证与 D01a 适用性 | `c02b_position_s2_probe`、`d05b_pairing_s2_probe`、public candidate tests、D01a/D01b helper 提取；实际上下文 provenance、防输出覆盖、历史 pin admission |
| 文档、示例入口和原 Skill | Public API、runtime docs、阶段收据、README/examples 导航与既有 TaskEnv Skill；准确分层 candidate/diagnostic/current-pin/historical/deferred |

相对该 develop **未修改 GeoPhys/Menagerie gitlinks、发布 qualification matrix 或 frozen refs**。
已有 Evidence 的 bytes 不因本地提交纳入 Git。原 P99 manifest 中 **385 个文件**在本轮开始逐一校验 SHA-256 一致；
历史目录与冻结输入原地保留。检查点与后续核对信息在 ignored
`workspace/maintenance/phase_ii_second_review_20261022_001/`。

## 20 个父 Goal：本轮交付时的工程处置

以下是现有源码与已有收据的索引整合，**不是重新执行 A–D 全量审计**。每个通过结论只继承原收据的 source/provider/backend/representation
交集，不把旧 pin 的 native Evidence 自动转移为当前 pin 全量通过。局部通过、未准入扩展、明确延期和独立 Qualification 分开列示。

| 父 Goal | 对应切片 | 最终工程结果与边界 | 证据入口 |
| --- | --- | --- | --- |
| A01 | A01 | static identity/codec gate 通过；不授予 runtime 能力 | [A01 收据](01_Phase_A_Core_Object_Model.md#a01-验收收据2026-10-20) |
| A02 | A02 | Frame/Articulation 静态 contract 通过；非树/闭环/transmission 等保留边界 | [A02 收据](01_Phase_A_Core_Object_Model.md#a02-验收收据2026-10-20) |
| A03 | A03 | 单/双 Robot 静态 composition/resource/reference 隔离通过；不是任意多 Robot dynamics | [A03 收据](01_Phase_A_Core_Object_Model.md#a03-实施收敛与验收收据2026-10-20) |
| A04 | A04 | pinned Panda/peg source closure、映射、source-retained 与旧 factory 兼容通过；不是完整 importer lowering | [A04 收据](01_Phase_A_Core_Object_Model.md#a04-实施记录来源闭包映射与旧-factory-兼容2026-10-20) |
| A05 | A05 | 静态集成/legacy 只读 projection gate 通过；Source identity 保持 | [A05 收据](01_Phase_A_Core_Object_Model.md#a05-实施记录2026-10-20) |
| B01 | B01 | strict TaskSource/Hook declaration 通过；不执行任意 Hook | [B01 收据](02_Phase_B_Task_Semantics.md#b01-bounded-source-and-hook-declaration-slice-2026-10-20) |
| B02 | B02 | 固定拓扑 role/reset plan、原 ResetSample、realization gate 有界通过；不等于动态拓扑 | [B02 收据](02_Phase_B_Task_Semantics.md#b02-bounded-rolereset-plan-slice-2026-10-20) |
| B03 | B03a/B03b | 只读谓词与显式 exactly-once temporal commit 通过；temporal rules 未自动写入新 Artifact | [B03 收据](02_Phase_B_Task_Semantics.md#b03a--只读-predicate-与-actioninterval-context2026-10-20) |
| B04 | B04a/B04b | 严格 codec/compiler/版本与 source-retained 有界通过；三类历史 H5 golden **ACCEPTED-DEFERRED** | [B04a](02_Phase_B_Task_Semantics.md#b04a--source-bound-evidence-重建2026-10-20cmd-0001)、[B04b](02_Phase_B_Task_Semantics.md#b04b-taskartifact-v1) |
| B05 | B05 | 旧任务同状态语义适配/回归通过；不等于新 freeze/trajectory replay | [B05 收据](02_Phase_B_Task_Semantics.md#b05-bounded-execution-receipt-2026-10-20) |
| C01 | C01a/C01b | config precedence/static plan 与 actual-manifest admission 有界通过；static plan 不是 runtime 支持 | [C01](03_Phase_C_Execution_Lifecycle.md#c01--resolved-execution-config--admission-planab) |
| C02 | C02a/C02b/C02c | C02b 声明交集有界工程出口满足、最小双 Entity Position 已覆盖；C02c 只通过单 Position 实例切换，通用切换 deferred | [C02b 当前结论](P99_Readiness_Review_2026-10-22.md#c02b-必需退出项映射)、[C02c](03_Phase_C_Execution_Lifecycle.md#c02c-bounded-single-panda-position-receipt2026-10-22) |
| C03 | C03a/C03b | fault/record fence 与 generic/Position Stop/Outcome 有界通过；旧 selected R1/vector Stop 明确未支持 | [C03a](03_Phase_C_Execution_Lifecycle.md#c03a-bounded-scalar-lifecycle-and-fault-receipt2026-10-21)、[C03b](C03b_Stop_Outcome_Receipt_2026-10-21.md) |
| C04 | C04 | observation/info schema、必要反馈/可选 diagnostics 有界通过；generic Panda scene construction 缺口不由 builder test 遮盖 | [C04 收据](03_Phase_C_Execution_Lifecycle.md#c04-bounded-observation-and-info-receipt-2026-10-21) |
| C05 | C05a1/a2/a3/b/c | 三 recorder owner 的 opt-in storage、PickCube legacy external Solution 有界通过；C05c 指定矩阵 diagnostic pass，常规 Reader/native-rate 合同延期 | [C05a 映射](05_Architecture_Review_and_Execution_Order.md#32-c05a-既有证据与三切片映射)、[C05b](C05b_External_Solution_S2_S3_Acceptance.md)、[C05c](C05c_GeoPhys_Gripper_Cadence_Comparison_2026-10-22.md) |
| D01 | D01a/D01b | 旧 4436787e D01a 及双 Provider vNext bounded receipts 保留；当前 pin A05/reset/step 与 P99 public candidate 已有对应入口/Evidence，不宣称通用 lowering | [D01a](04_Phase_D_Physics_Rendering.md#d01a-bounded-execution-receipt-2026-10-20)、[D01b](04_Phase_D_Physics_Rendering.md#d01b-bounded-vnext-two-provider-receipt-2026-10-20)、[本轮适用性](#d01a-历史基线与当前验证入口) |
| D02 | D02a/D02b | typed requirements/evaluation-boundary owned projection 有界通过；raw-force v2 只准入精确 R1 交集；通用 contact/native interval/spherical/alias 未支持 | [D02 收据](04_Phase_D_Physics_Rendering.md#d02b-bounded-typed-publication-slice-2026-10-20)、[raw force](C02b_R1_Typed_Raw_Force_Admission_Acceptance.md) |
| D03 | D03 | 首个受限 source 的 visual sync/consumer versions 有 S1/S2；不外推任意 Scene/Renderer | [D03 收据](04_Phase_D_Physics_Rendering.md#d03-first-bounded-intersection-receipt-2026-10-21) |
| D04 | D04 | fixed/mounted RGB/Depth/Entity-mask 与 capture identity/回读有界通过；semantic classes、完整 D04 与 consumers 仍未完成 | [D04 收据](04_Phase_D_Physics_Rendering.md#d04-bounded-entity-instance-segmentation-receipt-2026-10-22) |
| D05 | D05a/D05b | 静态 selection 与当前 pin 的精确 native pairing S1/S2/teardown 通过；完整 pairing matrix/Qualification 未授予 | [D05a](04_Phase_D_Physics_Rendering.md#d05a-static-contract-delivery-2026-10-20)、[当前 D05b](04_Phase_D_Physics_Rendering.md#d05b-current-pin-revalidation-2026-10-22) |

## 33 个切片与原始证据索引

顺序/编号复用 05，不把 C02b-P/E、R1 各内部 checkpoint 增算为新切片。以下链接进入各收据，再按其中 source hashes、
raw paths、commands 和 limits 追溯 Evidence。A/B 等历史文件在原路径保留；本轮只重新运行 D01a 受影响最小集合。

| 顺序 | 切片 | 工程结果 / 未完成边界 | Evidence / detector 入口 |
| ---: | --- | --- | --- |
| 01 | A01 | static identity PASS | [A01](01_Phase_A_Core_Object_Model.md#a01-验收收据2026-10-20) |
| 02 | A02 | static Frame/Joint PASS | [A02](01_Phase_A_Core_Object_Model.md#a02-验收收据2026-10-20) |
| 03 | B04a | S1 source-bound 检查通过；三类历史 H5 ACCEPTED-DEFERRED | [B04a](02_Phase_B_Task_Semantics.md#b04a--source-bound-evidence-重建2026-10-20cmd-0001) |
| 04 | D02a | provider-free typed-state contract PASS | [D02a](04_Phase_D_Physics_Rendering.md#d02a-contract-slice-2026-10-20) |
| 05 | C01a | normalize/static plan contract bounded PASS，无 runtime admission 推论 | [静态 detector](../../../../../task_env/diagnostics/tasks/test_phase_ii_c01a_execution_plan.py)、[B closure/C01a 回归](02_Phase_B_Task_Semantics.md#b11-b-阶段有界工程收口2026-10-20) |
| 06 | D05a | provider/renderer selection + planned capture identity PASS | [D05a](04_Phase_D_Physics_Rendering.md#d05a-static-contract-delivery-2026-10-20) |
| 07 | A03 | static single/dual composition PASS | [A03](01_Phase_A_Core_Object_Model.md#a03-实施收敛与验收收据2026-10-20) |
| 08 | A04 | bounded public import/source mapping PASS | [A04](01_Phase_A_Core_Object_Model.md#a04-实施记录来源闭包映射与旧-factory-兼容2026-10-20) |
| 09 | A05 | static integration/projection PASS | [A05](01_Phase_A_Core_Object_Model.md#a05-实施记录2026-10-20) |
| 10 | D01a | original pin microprobe PASS_HISTORICAL；当前 pin 精确分流见下；未知 pin 拒绝 | [原收据](04_Phase_D_Physics_Rendering.md#d01a-bounded-execution-receipt-2026-10-20)、[当前测试](../../../../../task_env/diagnostics/tasks/test_phase_ii_d01a_scene_materialization.py) |
| 11 | D02b | GeoPhys/MuJoCo CPU scalar/free-base owned publication bounded PASS | [D02b](04_Phase_D_Physics_Rendering.md#d02b-bounded-typed-publication-slice-2026-10-20) |
| 12 | B01 | strict source/hook declaration bounded PASS | [B01](02_Phase_B_Task_Semantics.md#b01-bounded-source-and-hook-declaration-slice-2026-10-20) |
| 13 | B02 | fixed role/reset/realization bounded PASS | [B02](02_Phase_B_Task_Semantics.md#b02-bounded-rolereset-plan-slice-2026-10-20) |
| 14 | B03a | read-only predicate/action context bounded PASS | [B03a](02_Phase_B_Task_Semantics.md#b03a--只读-predicate-与-actioninterval-context2026-10-20) |
| 15 | B03b | explicit temporal commit/missing/reset/duplicate bounded PASS | [B03b](02_Phase_B_Task_Semantics.md#b03b--有界-temporal-memory-与显式边界提交2026-10-20) |
| 16 | B04b | TaskArtifactV1 compiler/strict dispatch bounded PASS，仍为 candidate | [B04b](02_Phase_B_Task_Semantics.md#b04b-taskartifact-v1) |
| 17 | B05 | legacy semantic fixture equivalence bounded PASS | [B05](02_Phase_B_Task_Semantics.md#b05-bounded-execution-receipt-2026-10-20) |
| 18 | C01b | actual-manifest/source/backend dynamic admission bounded PASS | [C01b](03_Phase_C_Execution_Lifecycle.md#c01b-bounded-dynamic-admission-receipt2026-10-20) |
| 19 | D01b | exact Scene-v3/reset plan、GeoPhys/MuJoCo CPU bounded PASS，历史 receipt pin 不改 | [D01b](04_Phase_D_Physics_Rendering.md#d01b-bounded-vnext-two-provider-receipt-2026-10-20) |
| 20 | C02a | Entity×Group bindings/preflight bounded PASS | [C02a](03_Phase_C_Execution_Lifecycle.md#c02a-bounded-implementation-receipt2026-10-21) |
| 21 | C05a1 | value/version/finalizer/End Event evidence mapped，非全 consumer 迁移 | [C05a 映射](05_Architecture_Review_and_Execution_Order.md#32-c05a-既有证据与三切片映射) |
| 22 | C05a2 | Generic H5 v3、T/T+1、single-writer projection/bootstrap bounded PASS | [C05a 映射](05_Architecture_Review_and_Execution_Order.md#32-c05a-既有证据与三切片映射) |
| 23 | C05a3 | canonical/execution storage + malformed input rejection bounded PASS；不是 D0 restore/replay qualification | [C05a3 补证](05_Architecture_Review_and_Execution_Order.md#33-c05a3-targeted-supplement-与-29c05b-pickcube-consumer-audit2026-10-22) |
| 24 | C03a | execution fault/progress/Recorder completeness & atomic append fence bounded PASS | [C03a](03_Phase_C_Execution_Lifecycle.md#c03a-bounded-scalar-lifecycle-and-fault-receipt2026-10-21) 及其后续 correction/fence receipts |
| 25 | C04 | state/privileged/private/info/diagnostics bounded PASS | [C04](03_Phase_C_Execution_Lifecycle.md#c04-bounded-observation-and-info-receipt-2026-10-21) |
| 26 | C02b | 声明交集有界工程出口满足；Position、最小双 Entity、legacy freshness、typed raw-force、single R1 closed loop | [退出映射](P99_Readiness_Review_2026-10-22.md#c02b-必需退出项映射)、[R1 S2/S3](C02b_Single_Panda_Structured_R1_Behavior_S2_S3_Acceptance.md) |
| 27 | C03b | generic/Position Stop/Outcome/H5 bounded PASS；旧 R1/vector 明确未支持 | [C03b](C03b_Stop_Outcome_Receipt_2026-10-21.md) |
| 28 | C02c | single Position instance switch bounded PASS；general switching ACCEPTED-DEFERRED | [C02c](03_Phase_C_Execution_Lifecycle.md#c02c-bounded-single-panda-position-receipt2026-10-22) |
| 29 | C05b | legacy PickCube external Solution + canonical-v0 S1/S2/S3 bounded PASS | [C05b](C05b_External_Solution_S2_S3_Acceptance.md) |
| 30 | C05c | specified MuJoCo route / GeoPhys four-cell diagnostic S2/S3 PASS；normal Reader contract deferred | [C05c](C05c_NutAssembly_Public_Native_S1_Acceptance.md)、[four-cell report](C05c_GeoPhys_Gripper_Cadence_Comparison_2026-10-22.md) |
| 31 | D03 | first bounded sync/reset/same-step/read-only consumers PASS，历史身份保留 | [D03](04_Phase_D_Physics_Rendering.md#d03-first-bounded-intersection-receipt-2026-10-21) |
| 32 | D04 | RGB/Depth/Entity-mask slices bounded PASS；semantic segmentation/full scope 未完成 | [D04](04_Phase_D_Physics_Rendering.md#d04-bounded-entity-instance-segmentation-receipt-2026-10-22) |
| 33 | D05b | a53a8cfe CPU × MuJoCo native OpenGL current-pin S1/S2/close PASS_BOUNDED | [当前 pairing](04_Phase_D_Physics_Rendering.md#d05b-current-pin-revalidation-2026-10-22) |

**P00/P99 是额外 gate，不计入上述 33 切片或 20 父 Goal。** P00 的 frozen identity/旧 routes/最小双 Entity 保护保留；
P99 两项指定运行缺口已通过同一公开环境主线及当前 pin pairing 的真实 Evidence 关闭；其最终接受仍待独立 review/维护者。

## Public API、兼容性与失败行为

本轮只调整测试与交付文档，没有新增功能。二审需覆盖整个相对 develop 的候选源码，而非只看最后一次测试提交。

| 项目 | 准确范围与失败语义 |
| --- | --- |
| 新 candidate UID | `panda-position-servo-candidate-v1`；GeoPhys CPU、scalar、state-only、固定 seed 31、horizon 整数 1–6000、100 Hz/五个 2 ms steps；可选 source_workspace 必须 fresh/empty；默认路径在 ignored workspace |
| action/observation/record | reset 后 read-only `env.position_plan` 提供 Scene/plan/schema IDs；完整 arm+gripper StructuredActionRequest；世界 hand-origin pose 与 normalized gripper；reset/step public observation；existing Generic H5 v3 start/append/finalize，T/T+1 同文件 readback |
| candidate Evidence | 同一 make_env 对象连续 64 steps / 65 observations；request/target/ack/state/clock/identity 与 H5 精确回读；实测关节/gripper 运动，不是几条独立 diagnostics 拼接 |
| candidate 拒绝 | unsupported provider/backend/render、旧 overlay/extra kwargs、错 reset seed/source/request/plan identity、复用非空 source 目录；preflight 前拒绝不推进 physics；录制失败复用 C03a 闭锁，不造成功 transition/不声称 rollback |
| import/bootstrap | 只注册 class；public import/registry 不导入 test modules 或初始化 native runtime；构造与 runtime 复用既有 owners |
| 旧路线 | PickCube/NutAssembly selected UID、默认路径及 frozen v0 Artifact 保持；Position/R1 profile 身份分离，R1 required force 不被 force-free Position 替代 |
| storage/version | Scene v1/v2/v3、TaskArtifact v0/v1、state v0/v1/v2、ExecutionSpec 与三类 H5 版本域分别 strict dispatch；未知版本/字段/身份/时序错配拒绝；new recording 不证明历史 bytes 或 D0 reconstruction |
| finalization | horizon 用 horizon/horizon_reached；提前 Stop 必须匹配 outcome reason；中间 pending/不完整 interval 不可伪造有效 finalize；task predicate、Expert completion、flags、replay validity、Qualification 分开 |
| candidate 状态 | 仍为 candidate，Task success 不由运动证明；无发布 freeze、randomized feasibility/Human Judge approval；R1/dual-Entity candidate 仍是诊断路线 |

详情与可执行四步录制示例见 [Public API](../../public-api.md#c02b-position-profile-candidate-status-2026-10-22)，
所有制与复用 gate 见 [P99 收据](P99_Runtime_Closure_2026-10-22.md#复用-gate-与边界)。

## D01a 历史基线与当前验证入口

变更仅位于原 `test_phase_ii_d01a_scene_materialization.py` 测试 owner。分类为测试适用性修正，不改变 materialization 行为。

| 条件/入口 | 处置与保护 |
| --- | --- |
| 原 axis-change test 遇到 4436787e | 运行原 materialization/reset/axis-change detector；末尾精确 pin 断言仍保留；历史 receipt 含 provider_revision |
| 原 axis-change test 遇到已知 a53a8cfe | 在 native materialization 前以 pytest 单项 skip 明确输出 **HISTORICAL_NOT_APPLICABLE**，列出两 SHA 与当前测试/probe 入口；不把 skip 计作 pass |
| 原 test 遇到其他 pin | **失败**；不将任意 pin 当成历史不适用；pin rejection 有 provider-free 正/反例 |
| 当前 pin 入口 | `test_b02_plan_consumes_the_exact_a05_v3_scene_identity` 明确要求 a53a8cfe，不走历史 skip；真实 source→materialize→reset_plan→realization gate→snapshot→step→close |
| 当前错误身份 | 同文件 missing Frame/Joint、source closure/geometry、reset tolerance、malformed build 等 tests 继续执行；未删断言或放宽容差 |
| receipt writer | 要求 report 的精确历史 pin，只向 pytest tmp_path 用 exclusive create 写入；拒绝错 pin/覆盖；不再向既有历史 Evidence 固定目录写入 |
| public/H5 与 pairing | 当前 pin 的专门入口继续为 `test_p99_public_position_candidate.py`、`c02b_position_s2_probe --public-factory`、`test_phase_ii_d05b_pairing_integration.py` / `d05b_pairing_s2_probe`；上轮实测保留，本轮不重跑 |

本轮最小命令（已有 GeoChora Python 环境，repo root）：

```bash
PYTHONPATH=GeoPhys/src:. python -m pytest -q -rs -p no:cacheprovider \
  task_env/diagnostics/tasks/test_phase_ii_d01a_scene_materialization.py
```

**12 passed、1 skipped/HISTORICAL_NOT_APPLICABLE、0 failed**，50.03 s，一条已有 Taichi `locale.getdefaultlocale` deprecation warning。
8 个 pin/适用性/receipt 案例与 4 个当前 native/身份/realization tests 通过。旧 pin 的原 axis-change campaign 本轮未重跑。
日志 `workspace/maintenance/phase_ii_second_review_20261022_001/d01a_regression.log`。上一轮原始
`35 passed、1 historical-pin failure` 日志保持原样；本轮分流结果不回写旧事实。

## 必须单列的延期、诊断例外与未准入项

**B04a ACCEPTED-DEFERRED**：三类历史原件仍缺：`geophys-transition-h5/v1`、canonical trajectory outer-v0 H5、
canonical-execution-v1 H5。TaskArtifact v0 mapping/hash fixtures 与 codec tests 不是这三类历史文件的 bytes-level 证据。
新 candidate H5、将 v2 schema 字段改为 v1、重造 synthetic H5 都不能替代原件。二审必须分别记录这些 reader 的延期/退休/恢复范围；
本包不改变既有延期，不擅自将其升为兼容 PASS 或 retirement。

**C05c Reader diagnostic exception**：GeoPhys 四格 CPU/CUDA × gripper 100/500 Hz 的原实验实际逐 native step 调用
公开 `RobotArmObservationReader.read_cpu_snapshot()`，尽管通常指导限于低频 host read。这次实测 Probe/full Expert/Guard/H5 pass
不构成一般 per-substep Provider API 合同、不改 manifest、不是 GPU device-resident Controller。常规支持仍需 Provider owner
明确 value/phase/freshness/cadence/invalidations，再由 Core RuntimeSession 绑定 episode/reset/boundary。原 accepted MuJoCo 3.8.1 CPU
external route 与其 2,377 transitions 的 Evidence 独立保留；四格矩阵本轮未重跑。

**Camera consumer 未接入**：当前 pin pairing 是直接 dynamic CameraSession 的真实复验，固定/hand-mounted RGB/Depth/Entity-mask、
sync/capture/state identity、两 consumer/失败/close 均有 Evidence；其 actual context 是 NVIDIA EGL / RTX 5060 / OpenGL 4.6 driver 595.84。
Camera capture 不调用 Controller 或推进 physics；尚未接入 policy observation/TransitionRecorder，不能称作 visuomotor 或录制相机数据集。
旧 `4436787e` pairing 收据保留历史身份，当前 pin 有自己的一轮 S1/S2，二者不混用。

**未准入扩展**：dual-Entity R1、CUDA R1、任意 source/profile/transmission/MuJoCo build、通用 C02c 切换、全 renderer pairing matrix、
free-joint/semantic segmentation、Assembly/attachments/topology hot swap、Task Harness、通用学习/Batch/Policy Runner 等不因本包获得支持。
最小双 Entity Position 已满足 P00/P99 相应 gate；不得反向将 dual-Entity R1 添为已批准必需项。

**独立 Qualification**：工程有界测试、任务物理 predicate、Expert/Outcome completion、H5 storage integrity、replay/reconstruction 与
Qualification 是不同结果；本包未执行/授予新的 Qualification，没有修改唯一 v1.1.0 qualification matrix 或历史 Decision。
新 Task freeze 前 Stage-1 validator、randomized feasibility 与独立 Human Judge 保持前置，candidate 不例外升级。

## 需要维护者接受的范围及未作决定

| 待决事项 | 本包建议供审范围 / 尚未发生的动作 |
| --- | --- |
| 受审源码与工程边界 | 独立审查 52c61dc 的实现及相对 develop 的 53 个文件增量；接受、要求修订或拆分均由维护者决定；本轮未签署 acceptance |
| P99 两项运行关闭 | 审查公开 Position 同一环境 64/65 H5 与当前 pin pairing S1/S2/close；决定是否满足 P99 对应受限运行 gate，不外推父阶段 complete |
| B04a 三类 H5 | 明确继续接受延期的精确 reader 范围/约束，或另行授权从批准归档恢复原件；retirement 未获批准 |
| C05c 工程范围 | 确认 diagnostic-only 四格与常规 Provider Reader 合同延期的分界；是否接受其作为本阶段范围缩减，不能由测试数量代替决定 |
| C02c/Camera/D04/D05 广度 | 明确剩余通用切换、consumer 接线与广泛渲染支持的 deferred/unimplemented disposition；没有自动扩大或补做 |
| 新 Task 发布 / Qualification | 是否另排 Stage-1/Judge/freeze、Qualification campaign；目前无新任务 freeze/qualification 决定 |
| 独立二审与集成 | 由维护者安排 reviewer，审后另行授权 fetch/check 与 develop/main 正常集成；未 push/merge、未移动 frozen refs |
| Phase II 完成声明 | 待所有必需范围与明确延期 disposition 经独立审阅；**本包不宣布 Phase II 完成** |

## 交付文件、复现与 NOT_RUN

本地包根：`workspace/maintenance/phase_ii_second_review_20261022_001/`。

- 本文及 canonical docs/receipts：从 Git checkout 阅读；`SOURCE_REVIEW.md` 是本文的交付副本。
- `source-review.bundle`：develop 为 prerequisite 的本地 Git bundle；`delivery_manifest.json` 固定 source/delivery commit、tree、SHA-256 与包内容。
- `source-vs-develop.patch`、`changed-files.tsv`、`diffstat.txt`、`commits.txt`：固定源码点对 develop 的审查增量；最终文档增量在 bundle 中另见。
- `goal_slice_index.json`：本次 20 父 Goal / 33 切片、P00/P99 独立 gate 的只读导航快照；不取代 canonical 执行表。
- `evidence_inventory.json`：从各收据索引原始文件及 hashes；大量 ignored Evidence 原地保留，不默认进入 Git。portable archive 仅复制选定关键日志/receipts/current H5/图像及已有原始 R1/C05c 结果；其余明确 external/preserved，不伪造、恢复或重新运行缺失的历史 golden。
- `d01a_regression.log`、`static_checks.log`、`preservation_check.json`：本轮命令/结果、静态检查和保护核对。

取 bundle 前需要上述 develop commit；先 `git bundle verify source-review.bundle`，在独立 checkout 检查其 manifest 所列 ref。
`PYTHONPATH=GeoPhys/src:.` 与现有 GeoChora 环境；无 root packaging metadata，不使用 editable installation。
历史 expensive probes 不作为默认二审执行命令；如 reviewer 发现新的明确受影响问题，应先确定有界复验范围。

本轮 NOT_RUN：完整 A–D、NutAssembly 四格、485 interval R1、公开 64-step/native pairing S2 重跑（无新 runtime 改动）、
旧 4436787e axis-change campaign、历史 D01b 双 Provider campaign、B04a 历史 golden 恢复、新功能、Camera consumer 接线、
Stage-1/Judge/freeze、Qualification、push/merge。现有 source-bound receipts 与本轮 D01a 验证分开报告。

本轮静态检查通过：变更 D01a 文件 `py_compile`、`git diff --check`、module Skill metadata/links/source paths、
系统 `quick_validate.py`；**248 个本地链接/锚点、20 父 Goal 与 33 切片计数/顺序**均已核对。
完整 consolidation-inventory validator 未运行：它面向历史 docs-only consolidation，本次候选源码包含 runtime/tests，
其 docs-only scope/count gates 不适用；本轮使用其既有 anchor parser 做 touched-link 检查，并单独核对 frozen refs/受保护 bytes。
Skill 的只读冷启动导航已复核，无阻断缺口；这不是维护者安排的独立二审，没有授予接受结论。
最终静态/Skill 检查与包完整性见 `delivery_manifest.json`；独立二审尚未执行。本轮完成交付后停止，等待维护者安排。
