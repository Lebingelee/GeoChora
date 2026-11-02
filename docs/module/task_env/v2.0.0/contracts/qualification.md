# 能力、测试与资格治理

Phase II 已于 2026-10-23 获 [Scoped Engineering Acceptance](../../maintenance/phase_ii_scope_freeze_20261023/maintainer_scope_decision.yaml)。该维护者范围决定不改本页的 Qualification 层级、不修改唯一发布矩阵、不伪装成独立 Human Judge 签名；S4/新 Formal Qualification 未执行、未授予，Release Promotion 仍须独立 Gate。

## 唯一发布基线

[v1.1.0 capability matrix](capability_matrix_v1_1_0_candidate.json) 保留已发布原始 bytes、schema、
status definitions、source/config/task hashes 与 Evidence linkage。文件名/status 中的 candidate 表示
发布前记录时点；不代表 v1.1.0 现在未发布。[Release](../../releases/v1.1/README.md)记录 tag identity。
不再维护第二份 current capability matrix。

状态语义直接复用该矩阵：IMPLEMENTED 为有源码；TESTED_BOUNDED 为精确交集已执行；
QUALIFIED 须独立 decision 与足够 Evidence。PLANNED、NOT_IMPLEMENTED、RETIRED、HISTORICAL_ONLY
均不构成当前可用/获准能力。缺 source/provider provenance 不得补造 identity 或宣称 current-HEAD qualification。

| 已发布有界执行交集 | 结果与限制 |
| --- | --- |
| PickCube × GeoPhys CPU × 100 Hz × seed 31 | selected P1.6 Artifact，expert/lift outcome/recording receipts；TESTED_BOUNDED |
| PickCube × MuJoCo CPU × 100 Hz × seed 31 | 同一任务范围；TESTED_BOUNDED |
| NutAssembly × GeoPhys CPU × 100 Hz × NA-S0 seed 19 | 11-stage Outcome V1 与物理 outcome；admitted warning 和原 strict Expert failure 分开保留 |
| NutAssembly × MuJoCo CPU × 100 Hz × NA-S0 seed 19 | 11-stage Outcome V1 与物理 outcome，strict completion 无 readiness warning；TESTED_BOUNDED |
| Pendulum CPU batch/learning/rasterizer | 仅具名 smoke；完整配置/来源看矩阵 |

上述四条 manipulation route 没有新增正式资格，不建立 P1.8 FULL/D0-D2、checkpoint inference、
一般 manipulation PPO、native GeoPhys Rigid Batch、native Flora 或 Physics × Renderer 资格。
SAPIEN/Genesis adapters 存在不准入 selected factory；已安装 package/registry/fake tests 不证明完整路线。

v1.0 P1.0–P1.6 bounded approvals 保留原 task/source/profile 范围；P1.7 deferred；P1.8 infrastructure
测试不升级为正式 acceptance。原 decisions 见
[冻结历史 decisions](https://github.com/Lebingelee/GeoChora/tree/v1.1.0/docs/module/task_env/phase1_mainline_integration/historical_decisions)
及[v1.0 release](../../releases/v1.0/README.md)。历史 Go2 资格不转移到新任务。

## 验证层级与成本

Layer A 保护 API/contract（reset、state/action、admission、schema、report）；Layer B 是真实 golden path
（construct/reset/rollout/record/replay/evaluate/report，适用时 randomized feasibility）；Layer C
是 provider/system regression（runtime/render/recorder/learner/runner/provenance）。

S0 static/import/schema 仅 wiring；S1 contract-boundary；S2 最小真实 provider microprobe；
S3 短集成/expert/record/learner smoke；S4 显式声明的 qualification campaign。
Layer A/B/C 描述范围，S0–S4 描述成本/gate，不一一对应。S0–S3 不等于 qualification；
S4 也须通过 declared route、完整 provenance、独立 Human Judge/maintainer decision 才可 QUALIFIED。

每次执行最小 defect-sensitive check，跨边界取相关 targeted checks 并集：

| 变更 | 必需 targeted evidence |
| --- | --- |
| Artifact/schema/report | load/reject/roundtrip/reference integrity |
| admission | positive/negative capability checks |
| reset/randomization | deterministic sampling + realized-state probe |
| state/timebase | semantic-name/finite/shape + exact control timing |
| controller | conversion + free-space tracking；验收前 C1/C2 |
| camera | transform math + projection/depth |
| recorder | T/T+1 synthetic + roundtrip；验收前真实 task collection/replay |
| semantics/provider | fixture + construct/reset/step/physical microprobe |
| learner/Runner | minibatch/update、短闭环；验收前 frozen paired policy evaluation |

Critical reset/admission/state/timebase/control/camera/trajectory/materialization/semantics 修改不能用
import-only 代替 S1/S2。物理演化相关失败、新 provider branch 或真实 rollout 才出现的 bug
升级 S2/S3；仅 declared acceptance、qualification envelope 受影响或复验 S4 failure 才运行 S4。
文档/格式变化不重跑昂贵 native campaigns。

## Oracle、tolerance 与 acceptance

Oracle 优先顺序：analytical invariant → Artifact contract → provider-independent semantic metric →
有依据 tolerance 的 paired comparison → 明确标注诊断的 provider reference。MuJoCo 不天然为 ground truth。
每个 tolerance 说明 quantity/unit、物理/数值依据、lifecycle segment、contact 是否激活、exact/numerical/behavioral 类别。
不得删断言、吞异常、降低 metric 敏感度、跳过失败 provider 或无 Evidence 放宽 tolerance。
变更 tolerance 需 fixed-sample error/scale/analytical evidence，并写 failure/acceptance note。

正式 run 必须记录时间、Core/provider/adapter/backend/task/Artifact/config/source identity、command、
oracle/tolerance、pass/fail/error/timeout、metrics、failure category、artifacts、wall time/resource；timeout 不算 pass。
可复用 detector 属 source，run outputs 属 ignored workspace。acceptance package 保留
`acceptance_report.md`、`acceptance.json`、独立 `phase_decision.yaml`，包括 scope/provenance、
contract、changed owners、smoke/qualification runs、oracle、results/deviations、unsupported/untested
intersection、cost/risks/refs。conditional 仅在剩余条件不可能推翻已接受 contract 时有效，不能掩盖 hard gate。

Evaluator 产事实，Judge 显式 approve/reject、judge type、basis、required changes；
初始权威为 Human Judge。保留 task feasibility 与 solver failure、Task Success 与 Expert Completion、
replay validity 与 qualification、有限 seed 结果与统计稳健性的区别。

## Core promotion 与交付

Evidence proposal → candidate patch → contract tests → reference/system regression → Human review →
reject/rollback 或 promote。重复任务问题、provider integration 或真实 regression 可触发 Core proposal；
单任务便利性、Agent 经验不得自动提升 Core。Provider 团队拥有 solver/kernel/native cache，
Core 定义公共行为、admission/error、conformance 与 provenance；不可用私有 workaround 绕 gate。

交付报告必须列出修改文件、保护 contract、实际 command/provider/backend/task/representation、结果、
未测 envelope、是否运行 qualification 和 residual risk。Skill/API/qualification 敏感改变保留 Human review。
更多退役/恢复与[调试](troubleshooting.md)和[发布限制](../../releases/v1.1/known-limitations.md)互相约束。

## 未完成的历史验收要求

[原蓝图](https://github.com/Lebingelee/GeoChora/blob/v1.1.0/docs/module/task_env/05-phase-1-multi-simulator-blueprint.md)
的完整 Phase I completion gate 仍未通过，不因本文档整合消失：primary GeoPhys/MuJoCo
需 frozen task admission/materialization、state/frame/time/reset/camera conformance、control realization、
C1/C2、dataset record/load/replay、同 checkpoint state-policy paired evaluation、camera-ready visuomotor
与完整 Experiment/phase decision；boundary SAPIEN/Genesis 需 admission/materialization/reset/state/time/
camera/control/conformance/PickCube C2，不强制完整 training。NutAssembly 还需相同 frozen contract
的 expert/trajectory semantic acceptance，不能只依赖 PickCube。
这些是保留的验收目标，不是当前 capability 或本次工作新增的 execution gate。当前后续工程优先级
由 post-v1.1 roadmap 决定；未完成的 visuomotor/正式 P1.8 资格不会由 benchmark 研究或工程 closure 豁免。
