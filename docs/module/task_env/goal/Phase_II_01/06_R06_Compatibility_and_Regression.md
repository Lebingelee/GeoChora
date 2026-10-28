# R06 — Compatibility / Mapping / Regression Governance

状态：REVISED_DRAFT；R06a Audit/S1交付已获Sol接收（ACCEPTED_AUDIT_S1_BOUNDED），compatibility decision gate仍BLOCKED；R06b/c PLANNED / NOT_STARTED。本 Goal 管理新支持交集与历史局限，不改 Phase II 接受决定。

## 映射与机械语义保护

| 检查对象 | 必需验证与失败边界 |
| --- | --- |
| Body/Joint/Actuator order | canonical typed name→native name/index/coordinate slice→逆映射，绑定 closure/Provider build/materialization；声明顺序、import order 与 native slot 不能假设一致 |
| Permutation detector | 刻意打乱 body/joint/actuator 列表，以可区分单资源输入验证目标、真实响应、state readback 与 H5 路径；错映射/alias/遗漏/重复在 apply 前拒绝 |
| Coordinate layout | qpos/qvel 各自 width/单位/offset；不把 nq=nv 作为通用合同，fixed relation 不伪造 DOF |
| Hand coupling | 两 finger 与一个 tendon actuator、Equality/mimic 的符号/比例、约束误差/限位、真实 driven resource；每个 finger joint 不一定有独立 actuator；禁止重复 writer |
| Inertia/contact/root | source 有声明≠solver消费；固定 child/root 处置、mass/inertia frame、collision filtering、接触/负载行为与 warning 要单列 receipt |
| Policy interface compatibility | 有序 action/observation、scale/offset/clipping/units/frames、clock/hold、reset/termination/语义保持；shape 相同不证明机制或 policy transfer 等价 |

复用 existing Scene/artifacts、source/import、ControlBindingPlan、typed state、Recorder/readers 和其测试 owners；不建立跨 Provider storage ABI，不访问 Provider 私有数组补 mapping。

## 版本、原件与 source-bound Evidence

保持 Scene v1/v2/v3 strict decode/mapping/hash、旧 Artifact/Entity identities、ResetSample/timebase、Position/R1 source-bound targets/acks、Recorder fault/T/T+1、旧 Provider capability manifest 与 UID/defaults。新 Assembly/Profile/Camera metadata 采用明确版本，未知字段/版本拒绝，不能用 global skip/删断言获得兼容 PASS。

三类历史 H5 原件：`geophys-transition-h5/v1`、canonical trajectory outer-v0、canonical-execution-v1，继续 **ACCEPTED-DEFERRED / MISSING_RAW_EVIDENCE / bytes compatibility NOT_PROVEN**。早期 GeoPhys eb870f6f typed-force JSON 被覆盖的原 bytes 仍 MISSING_RAW_EVIDENCE；同路径现存文件不是丢失原件，a53 新收据不能恢复它。历史 [B04a](../Phase_II/B_Development_Record.md#b04a) 与 [C02b](../Phase_II/C_Development_Record.md#c02b) 不回写。

只可从批准备份恢复原 bytes 并核 hash；synthetic、新格式 H5、摘要 hash 或相同任务重跑都不是恢复。Reader retirement/支持范围缩减必须另获维护者批准，并列精确 reader/格式/迁移影响，不自动执行。若不能恢复又没有 retirement/继续延期的本阶段独立决定，R06 compatibility decision gate 保持 BLOCKED；不能把 Phase II 旧延期当作 Phase II-01 自动豁免。

Evidence 分三栏：① 原 Phase II 固定 source/pin 收据；② 本轮仅文档/静态校验；③ 未来新 source/profile/Provider 交集的 S1/S2/S3。GeoPhys dual Position `4436787e` 不能改写为 a53 重跑；当前 a53 单 Panda/Camera pairing 不转移为 split-leaf Assembly 支持。未来 Provider pin 变化必须独立准入与新证据，旧 pin/原日志/原 hash 不移动。

## 分层回归与 Stop Conditions

每个 R01–R05 slice 在自己的提交前运行受影响旧路/negative detectors；R06b 是汇总 gate，不允许把兼容问题拖到 R06c。现有静态回归定位包括 [Scene composition](../../../../../task_env/diagnostics/tasks/test_phase_ii_scene_composition.py)、[legacy matrix](../../../../../task_env/diagnostics/tasks/test_phase_ii_b04a_legacy_matrix.py)、[Position profile](../../../../../task_env/diagnostics/tasks/test_phase_ii_c02b_position_profile.py)、[public candidate](../../../../../task_env/diagnostics/tasks/test_p99_public_position_candidate.py)、[pairing](../../../../../task_env/diagnostics/tasks/test_phase_ii_d05b_pairing_integration.py)。测试存在不等于本轮运行或新交集通过。

| ID | 前置 | 工作与交付 | 必需 Evidence / Stop Condition |
| --- | --- | --- | --- |
| R06a | P00 | 原件/备份可恢复性、版本/缺口 ledger、恢复/退休/继续延期待审批方案 | Audit/S1：缺失不改 PASS；没有本阶段精确决定则 compatibility gate 未关闭 |
| R06b | R06a,R01c,R02c,R03b | 新/旧 Schema、source、profile、native 顺序/coupling、UID/default/admission 正负回归 | S1/S2：错顺序、联动/资源/identity、版本误派发会失败；旧范围不退化 |
| R06c | R06b,R03c,R04c,R05c | 汇总所有 required 源码/Provider/backend/camera/reader交集，交付 P99 包 | S1/S2/S3 原始 receipts+checksums，FAIL/NOT_RUN/BLOCKED 分列；缺 required gate 不产生阶段 PASS |

P99 包应有 `acceptance_report.md`、`acceptance.json`、独立 `phase_decision.yaml`；记录 Core/tree、gitlinks/native build、source/closure/Scene/Assembly/profile/mapping identities、seed/reset/horizon、commands/预算、oracle/tolerance、T/T+1/H5/hash、failed/NOT_RUN/unsupported。事实由 evaluator 记录，维护者/Judge 独立决定；本轮不生成该未来 decision。

<a id="r06a-legacy-original-audit"></a>

## R06a 历史原件审计（2026-10-26）

审计边界仅复用 `evidence_index.json`、P00 `missing_originals.json`、所列 v1.1 备份/恢复索引和已知工作目录；未全盘扫描、未访问云端或其他机器。v1.1 L2 本地归档含22项有界证据副本，无一命中这四项历史域/路径，且不是完整工作区备份。source-recovery索引列出的7个manifest路径中，2个可读且未含目标域，5个在当前checkout中不存在。恢复清单没有列出以下四项原件。前三项的原件路径与原始文件 SHA-256 均为 `UNKNOWN`，索引无逐文件 bytes identity。B04a source-bound reconstruction 的 Core `f9543b8725d2990966743f49cebf9d68493b6b06` / GeoPhys `4436787e` 是重建来源事实，不能绑定为每个丢失文件的原始身份。

| 缺失原件 | 当前严格格式/读取路径与真实影响 | 原件/现存候选及历史身份 | 本阶段决定 |
| --- | --- | --- | --- |
| `geophys-transition-h5/v1` H5 | `RecorderConfig` 仍接受该 id/version；`TransitionRecorder.save_h5()` 可按 v1 写入。`inspect_trajectory_h5()` 可读容器摘要及 `meta/layout_json`，不重建完整语义轨迹；未找到独立完整 v1 loader 或 Core production replay caller。移除会影响旧格式写入/检查与兼容 fixture。 | 原路径/hash `UNKNOWN`；没有可信候选。历史 B04a 仅记录该 golden 缺失。 | 历史 `ACCEPTED-DEFERRED`；本阶段恢复/退休/延期均 `PENDING`。 |
| canonical trajectory outer-v0 H5 | `task_env.trajectory.canonical.h5.load()` 严格解析 v0 mapping、identity hash 与 numeric projection；`reference_replay.reexecute_selected()` 对 v0 调用该 loader 并走当前选定重执行。退休会移除该读取/selected replay 入口及对应 legacy matrix。 | 原路径/hash `UNKNOWN`；没有可信候选。B04a 重建 pin 仅作上下文，不是该 H5 的逐文件 source binding。 | 历史 `ACCEPTED-DEFERRED`；本阶段恢复/退休/延期均 `PENDING`。 |
| canonical-execution-v1 H5 | `execution.load()` 与 `streaming.load_streaming()` 接受 legacy v1 外层/逻辑 schema并校验hash/projection；`reference_replay.reexecute_selected()` 将非 outer-v0 路由至 streaming reader。`ExecutionRecorder` 构造器只创建 v2/v3，但模块级 `validate/save/load` 仍接受 v1 mapping。退休会影响读取、selected replay、legacy serialization及历史回归。 | 原路径/hash `UNKNOWN`；没有可信候选。历史 B04a 重建 pin 不等同于该 H5 的 bytes identity。 | 历史 `ACCEPTED-DEFERRED`；本阶段恢复/退休/延期均 `PENDING`。 |
| 早期 GeoPhys `eb870f6f` typed-force `s2_probe.json` 原 bytes | `test_phase_ii_c02b_r1_typed_force.py` 的诊断 probe writer 输出 JSON；未发现生产 codec/reader 或需要迁移的 production caller，因此不适用机械 reader retirement。 | 丢失原路径 `workspace/maintenance/c02b_r1_typed_force_20261022/s2_probe.json`；原 hash/Core pin `UNKNOWN`，GeoPhys 早期 pin 仅知短值 `eb870f6f`。同路径现有文件是后续 `c02b-r1-typed-force-probe-v1` 内容（7,664 bytes，SHA-256 `3c23764e877c067cd26d6af75f45127bbe5234c575dea5d69eb5118a0ac3bec7`），不是原件。 | `MISSING_RAW_EVIDENCE`；本阶段保留/排除该历史证据项的决定 `PENDING`。 |

当前没有批准归档成员或原始 hash 可供恢复；旧日志、mapping/identity hash、摘要、当前同路径 JSON 或新 a53 收据均不能代替文件 bytes。恢复选项需提供已批准来源、原件及可核验 SHA-256/来源链。若无法恢复，维护者可逐格式批准准确的 reader retirement/支持收缩（须接受上述调用者影响），或明确批准本阶段继续延期并规定该缺口对 R06c/P99 的后果；诊断 JSON 应按历史 Evidence 保留边界单独决定，不套用 reader retirement。所有选项的 `decision`、`approved_by`、`reference` 当前均为 `null`/未批准，Phase II 旧延期不自动沿用。

R06a 本轮定向 `test_phase_ii_b04a_legacy_matrix.py` 为 6 passed；它覆盖当前 codec/version route 与负例，不读取缺失历史 bytes，不证明 byte compatibility。Audit/S1 可交付但 compatibility decision gate 仍为 `BLOCKED_MISSING_RAW_OR_PHASE_DECISION`；R06b/c 与 P99 不得把它记作关闭。本轮没有改 reader、格式、source pin、DAG、Required Envelope 或 Skill。

## Sol复核（2026-10-26）

Sol审阅提交 `56f689570a0fbaf29aea4ea26a073d38b5e6afd6` 的四份文档差异、四项ledger及当前reader/caller边界，接收R06a为 **ACCEPTED_AUDIT_S1_BOUNDED**，无必需返工。20项输出、9项owner源码、13项审计输入、8项保护输入与11份phase文档摘要核验通过，复用6 passed日志；22项L2成员和7项恢复清单路径核对支持本包限定检索结论。四项原件仍未恢复，处置批准均为空，compatibility gate保持 `BLOCKED_MISSING_RAW_OR_PHASE_DECISION`。下一行R01b不增加原件恢复前置；R06b/c/P99 gate不因此关闭。复核入口为ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r06a_001/`。

## 与独立R07的分界

R06b新增R03b前置，以便对真实lowering/root与native顺序映射做回归；原R01–R06目的/required gates保持。Benchmark部署/Agent成本由独立[R07](09_R07_Benchmark_Deployment_and_Agent_Cost.md)所有，不并入R06c。R06仍保护旧Scene/Artifact/Recorder/Provider合同；P99同时依赖R06c和R07d，R07不是回写PhaseII兼容结论的理由。

## 与 USD / Harness 后继计划的分界（2026-10-28）

[10 补丁计划](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md) 规定新增 source/receipt/recording profile
版本化并保留现有 R02c/R03c exact reader；不能为接 Isaac 删除 MuJoCo3.8.1/64/65 的旧交集校验。
Harness 的 canonical H5 与 leaf Generic H5 各沿现有 owner 扩展，storage roundtrip 不代正式 replay。
新三 provider 运行保留精确 execution/source/build 身份，不回写旧 pin 的证据。
本页四项 missing raw/处置决定与 R06c/P99 阻塞保持，不以新资产验证报告或新 H5 自动填补历史 bytes。
