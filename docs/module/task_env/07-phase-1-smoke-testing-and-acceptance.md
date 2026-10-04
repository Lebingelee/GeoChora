# Geochora Phase I Smoke Testing 与验收

> 状态：active Phase-I test/qualification plan，v0.2
> 日期：2026-10-04
> 范围：定义 Phase I 的成本感知 smoke 选择、smoke record、子阶段 acceptance Evidence 与昂贵 qualification gate。
> 相关文档：05-phase-1-multi-simulator-blueprint.md、06-phase-1-contracts-and-provider-boundaries.md
> 权威关系：作为 Phase-I 实施计划采纳，从属于 [系统架构基准](../../global/00-system-architecture-anchor.md)、[仓库所有权](../../global/01-repository-ownership-and-boundaries.md) 与 canonical TaskEnv contract。active 表示文档用于指导实施，不表示 capability 已实现、测试通过、qualified 或任何子阶段已获准。

## 1. 测试目标

Phase I 测试必须最大化单位运行和工程成本对应的缺陷敏感度。

默认规则：

~~~text
每次修改：
  运行能够直接执行被修改 contract 的最小测试；

子阶段结束前：
  运行必需的 golden-path 与 provider qualification gate；

不要：
  每次局部修改后都重跑所有昂贵 simulator/task/policy campaign。
~~~

如果修改的代码控制 reset semantics、state mapping、controller conversion、camera geometry、recorder layout 或 provider admission，廉价 import-only test 不能替代针对性测试。

## 2. Evidence 层级

必须区分以下层级。

与 canonical Layer A/B/C 的范围映射见 [04 qualification ladder](04-core-qualification-and-governance.md#phase-i-qualification-ladder-与-smoke-映射)。S0–S3 smoke 不等价于 qualification；S4 才是正式 subphase qualification evidence，且 qualified 仍须满足已声明 acceptance route、足够 Evidence/provenance 和独立 decision。

### S0 — Static/import/schema smoke

典型成本：数秒。

用于：

- import；
- dataclass/schema validation；
- serialization；
- CLI/help；
- 文档引用；
- 纯 semantic fixture。

S0 只证明基本 wiring。

### S1 — Contract-boundary smoke

典型成本：数十秒到数分钟。

用于：

- capability admission；
- ResetSample generation；
- canonical state adaptation；
- action/controller conversion；
- camera transform math；
- trajectory schema；
- report/Evidence schema。

S1 应直接命中 patch 修改的公共 contract。

### S2 — Provider microprobe

典型成本：数分钟。

用一个最小物理场景执行：

- provider construction；
- reset；
- step；
- joint tracking；
- free fall；
- contact；
- camera capture/depth；
- deterministic replay。

调试 provider 边界时，应优先使用 S2，而不是启动完整 PickCube campaign。

### S3 — Golden-path short smoke

典型成本：数分钟到数十分钟，取决于 backend。

用于：

- 短 PickCube expert rollout；
- record/save/load/replay；
- 短 Runner rollout；
- 一次/少量 learner update；
- 同一 checkpoint 在另一 provider 的加载/执行。

S3 证明集成路线可以运行，不证明 convergence 或完整 qualification。

### S4 — Subphase qualification

可能很昂贵，只在显式 gate 使用：

- 完整 conformance probe matrix；
- randomized feasibility set；
- paired EvaluationSampleSet；
- policy transfer matrix；
- visuomotor evaluation；
- NutAssembly regression；
- 最终 provider capability matrix。

S4 产生 acceptance Evidence。

## 3. 风险导向 smoke 选择

根据修改的边界选择 smoke：

| 修改面 | 必须立即执行的 smoke | 验收前升级项 |
|---|---|---|
| Task Artifact/schema | S0 load/reject/roundtrip | candidate artifact validator |
| capability admission | S1 positive + negative admission | provider capability snapshot matrix |
| ResetSample/randomization | S1 deterministic sampler + S2 reset realization | 跨 provider paired reset set |
| provider materialization | S2 construct/reset/step | conformance probe |
| CanonicalState mapping | S1 semantic-name mapping + finite/shape | provider-paired state probe |
| timebase/scheduler | S1 exact control time increment | 短 trajectory timing comparison |
| controller/action | S1 conversion + S2 free-space joint tracking | C1 open-loop + C2 expert |
| camera/frame | S1 transform math + S2 projection/depth | 完整 camera geometry gate |
| recorder/H5 | S1 synthetic T/T+1 + roundtrip | 真实 PickCube record/replay |
| semantics | S1 state/history fixture | closed-loop task rollout |
| learner adapter | 一个 minibatch/update | state-policy transfer matrix |
| Runner/policy | 短 closed-loop rollout | paired EvaluationSampleSet |
| report/Evidence | schema/reference integrity | subphase acceptance package |

此表是默认选择。跨越多个边界的 change 应运行相关 targeted smoke 的并集，而不是整个仓库。

## 4. Critical-path smoke 规则

以下 Phase-I surface 是关键路径；修改它们时，handoff 前必须运行 defect-sensitive S1 或 S2：

~~~text
Task Artifact load/validation
provider capability admission
ResetSample generation/application
CanonicalState conversion
timebase/control scheduling
controller -> canonical target conversion
camera/frame transform
trajectory T/T+1 与 metadata
provider materialization
task success/failure semantics
~~~

Formatting、optional logging、CLI text 和非语义 report presentation 可以使用较低成本 smoke，除非它们改变 machine-readable Evidence。

## 5. Smoke run record

每次作为 Evidence 使用的实质 smoke 都应有紧凑的 machine-readable record。

推荐位置：

~~~text
workspace/qualification/phase1/<subphase>/smoke/<smoke_id>/
├── smoke_plan.yaml
├── smoke_report.json
├── command.txt
├── stdout.log
├── stderr.log
└── artifacts/
~~~

### 5.1 smoke_plan.yaml

建议 field：

~~~yaml
smoke_id: p1_3_joint_tracking_mujoco_001
repository_commit: ...
change_scope:
  - task_env/runtime/...
protected_risk:
  - canonical joint target is interpreted with correct joint order
provider:
  name: mujoco
  version: ...
task_or_probe: joint_tracking_probe
oracle:
  type: declared_tolerance
  metric: max_joint_position_error
  threshold: ...
expected_cost:
  wall_time_s: 60
~~~

### 5.2 smoke_report.json

建议 field：

~~~text
smoke_id
start/end timestamp
repository commit
provider/adapter/backend version
command
result: pass/fail/error/timeout
measured metric
oracle/tolerance
failure category
retained artifact reference
wall time
适用时的 resource summary
~~~

Timeout 不能算 pass。

## 6. Smoke record 与源码中的 test

可复用 regression 或 conformance detector 的测试实现属于仓库。

运行记录属于 workspace/qualification/...，默认不提交。

One-off diagnostic script 不能仅因为曾有帮助就提升为公共 regression；只有在保护重复出现或 contract-level 风险时才提升。

## 7. 子阶段 acceptance package

P1.0–P1.8 的每个 Phase-I 子阶段都必须在自己的 workspace/qualification/phase1/<subphase>/ 下产生以下 acceptance package，不仅是 p1_8_closure：

~~~text
acceptance_report.md
acceptance.json
phase_decision.yaml
~~~

### 7.1 acceptance_report.md

只记录事实，必需 section：

~~~text
1. 范围
2. repository/provider provenance
3. 接受验收的 contract 或 capability
4. 修改的实现路径
5. 执行的 smoke run
6. 执行的 qualification run
7. oracle 与 tolerance
8. 结果
9. failure 与 deviation
10. unsupported intersection
11. resource/cost note
12. residual risk
13. Evidence reference
~~~

不能仅因为可见 metric 都良好就在此写 approved。

### 7.2 acceptance.json

Machine-readable summary，建议最小内容：

~~~text
subphase_id
repository_commit
provider_versions
task_artifact_refs
experiment_refs
smoke_refs
qualification_refs
passed_checks
failed_checks
untested_envelopes
unsupported_intersections
known_risks
~~~

### 7.3 phase_decision.yaml

与 evaluation fact 分离的 authority decision：

~~~yaml
phase: p1_5_expert
decision: approve
judge:
  type: human
basis:
  - ...
required_changes:
  - ...
~~~

只有当剩余条件不可能推翻已接受 contract 时，conditional 才可以允许进入下一个隔离子阶段；不能用它隐藏 failing hard gate。

## 8. 各阶段 smoke budget

### P1.0 baseline

低成本：

- import/bootstrap；
- 现有 governed contract test。

昂贵项：

- 只运行建立 baseline 所需的最小历史 regression route，并重新确认其 current-HEAD 状态；不运行完整训练或 qualification campaign。

历史 Evidence 缺少完整 commit/provider provenance 时不能自动升级为 current-HEAD qualification。缺失的既有 contract subset/detector、baseline failure 与未测试 envelope 必须保留；文档采纳不产生全绿结果。Operator workflow 为 audit → documentation adoption → baseline smoke → evidence freeze；这些是 P1.0 内执行 checkpoint，不是新 architecture subphase。

### P1.1 contracts

优先：

- schema；
- provider-free task import；
- negative capability admission；
- semantic fixture。

不要为每次 schema edit 启动 manipulation physics。

### P1.2 runtime

优先：

- construct/reset/one-step；
- deterministic reset；
- canonical-state snapshot；
- timebase。

这里 one-step runtime smoke 比长 task rollout 更有信息量。

### P1.3 conformance

独立运行每个 microprobe，避免难以归因的单体 all-physics test。

### P1.4 camera

在 PickCube RGB 前使用小型 calibration scene 与 fixed landmark。

### P1.5 expert

先测试一个 semantic segment，再测试短 C1/C2，最后测试 randomized feasibility。

### P1.6 state policy

先运行：

- dataset roundtrip；
- 一个 minibatch/update；
- 一次短 policy rollout。

之后再运行完整 transfer matrix。

### P1.7 visuomotor

Smoke 使用仍能执行真实 observation path 的最小 image resolution 与最短 train/rollout。完整配置 resolution 属于 qualification。

### P1.8 closure

在 frozen commit、frozen provider version 和 frozen EvaluationSampleSet 上运行一次声明的最终 matrix。

## 9. Oracle 层级

按以下顺序优先选择：

1. analytical invariant；
2. 显式 Task Artifact contract；
3. provider-independent semantic/behavioral metric；
4. 有合理 tolerance 的 pairwise comparison；
5. 仅在明确作为诊断参考时使用 provider reference behavior。

MuJoCo 不自动成为所有 Phase-I 检查的 ground truth。

## 10. Tolerance 治理

每个 qualification numerical tolerance 都必须说明：

~~~text
比较的 quantity
unit
tolerance 为什么有意义
覆盖哪个 lifecycle segment
contact 是否激活
tolerance 是 exact、numerical 还是 behavioral
~~~

不得通过以下方式让失败测试变绿：

- 没有新 Evidence 就放宽有效 tolerance；
- 删除 assertion；
- 吞掉 exception；
- 改用敏感度更低的 metric；
- 静默跳过失败的 provider/task。

Tolerance change 需要在子阶段 failure/acceptance record 中写简短 Evidence note。

## 11. Smoke 升级策略

出现以下情况时，从 S0/S1 升级到 S2/S3：

- 修改进入 provider runtime；
- failure 取决于 physical state evolution；
- state/control/camera 静态值正确但 step 后发散；
- recorder 或 semantic bug 只在真实 rollout lifecycle 出现；
- 新增 provider-specific branch。

只有以下情况升级到 S4：

- 子阶段已准备验收；
- fix 可能影响声明的 qualification envelope；
- 正在重新验证此前 S4 failure。

## 12. Codex handoff 要求

Codex 声明有界 Phase-I change 完成前，必须说明：

~~~text
修改的文件
保护的 contract
smoke command
执行的 provider/backend/task/probe
结果
未测试 envelope
是否运行 subphase qualification
剩余风险
~~~

只说“测试通过”而不说明执行的 provider/task/representation，是不充分的。
