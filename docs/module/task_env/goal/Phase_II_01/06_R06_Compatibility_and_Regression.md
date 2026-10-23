# R06 — Compatibility / Mapping / Regression Governance

状态：REVISED_DRAFT；R06a/b/c 均 PLANNED / NOT_STARTED。本 Goal 管理新支持交集与历史局限，不改 Phase II 接受决定。

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

## 与独立R07的分界

R06b新增R03b前置，以便对真实lowering/root与native顺序映射做回归；原R01–R06目的/required gates保持。Benchmark部署/Agent成本由独立[R07](09_R07_Benchmark_Deployment_and_Agent_Cost.md)所有，不并入R06c。R06仍保护旧Scene/Artifact/Recorder/Provider合同；P99同时依赖R06c和R07d，R07不是回写PhaseII兼容结论的理由。
