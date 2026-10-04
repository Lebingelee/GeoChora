# Geochora Core 资格验证与治理

> 状态：canonical Core validation policy，v0.3
> 日期：2026-10-04

## 1. 目的

每次 Geochora Core 更新都必须保留已有的资格化能力，并以明确方式增加新能力。

资格验证以 Evidence 为基础。注册了 task、provider 可以 import 或 class 已存在，都不能单独证明端到端能力已受支持。

参考任务是多仿真器、多渲染器中枢的资格验证载体，不定义完整产品范围。

## 2. 资格验证层级

### Layer A — API / contract test

验证公共行为与 invariant：

- environment/task API；
- Runtime Port/provider boundary；
- reset/step semantics；
- observation/action schema；
- controller/action conversion；
- artifact/experiment schema handling；
- report/Judge contract；
- fail-closed capability admission。

### Layer B — Golden-path task qualification

运行真实可执行的 task workflow，而不是只做 construction test。

Golden path 按适用情况包括：

~~~text
construct
-> reset
-> step/rollout
-> record
-> replay
-> evaluate
-> report
~~~

Stage-1 manipulation golden path 还必须包含 randomized feasibility。

### Layer C — Provider/system regression

验证默认端到端集成范围：

- runtime smoke；
- default render smoke；
- render/UI presentation-contract smoke；
- recorder/replay smoke；
- learning smoke；
- runner closed-loop smoke；
- provider capability snapshot/report。

### Phase-I qualification ladder 与 smoke 映射

Phase I 按以下关系积累并审查 Evidence：

~~~text
API/contract
 -> conformance microprobe
 -> golden path
 -> provider/system regression
 -> phase qualification
~~~

Layer A/B/C 描述保护的 contract/route 范围；[07 的 S0–S4](07-phase-1-smoke-testing-and-acceptance.md#2-evidence-层级) 描述 smoke 成本与 acceptance gate，两者不是一一对应关系。

| 本文范围 | targeted smoke | 正式 qualification |
| --- | --- | --- |
| Layer A：API/contract | S0 基本 wiring；S1 contract boundary | 相关 contract Evidence 纳入 S4 declared gate |
| Provider conformance microprobe | S2 最小 provider execution/probe | S4 验收声明的 probe set 与 tolerance |
| Layer B：golden path | S3 短 expert、record/replay 或 policy route | S4 完整 declared golden path，适用时含 randomized feasibility |
| Layer C：provider/system regression | 按风险选择 S1–S3 | S4 验收 declared integration/regression envelope |
| Phase/subphase acceptance | 引用上述 smoke 与 qualification records | S4 subphase qualification Evidence，加独立 phase decision |

S0–S3 smoke 不等价于 qualification；S4 才是正式 subphase qualification evidence。执行 S4 本身也不自动授予 qualified：必须通过已声明 acceptance route，具备足够 Evidence/provenance，并保留独立 Judge/maintainer decision。资格范围始终是 provider × backend/profile × task × lifecycle，不能从一个 intersection 外推到整个 provider。

## 3. 参考资格验证矩阵

### 3.1 PickCube — 主要 manipulation MVP

目的：

- 首条完整的 manipulation Stage 1 + Stage 2 路线；
- controller/action conversion；
- expert trajectory generation；
- randomized feasibility；
- recording/replay；
- oracle-state IL；
- render/camera 路径就绪后的 RGB visuomotor route。

### 3.2 NutAssemblySquare — 精密 manipulation regression

目的：

- 更高要求的 alignment/contact/task semantics；
- 检验 Core 是否能泛化到 PickCube 之外；
- 为更困难任务验证 artifact/evaluation contract。

### 3.3 Agent 生成的相似未见 manipulation task

目的：

- 验收公共 Core API 和文档是否足以让 Agent 构造任务；
- 应根据文本需求生成，范围与 PickCube/NutAssembly 可比，但不能复制已有任务。

### 3.4 Go2 Walk — locomotion/RL regression

目的：

- 保留历史 Evidence 最强的 Go2 CUDA/static/RSL training/runtime regression route；
- 确保 Core refactor 不破坏 device/RSL capability；
- 作为以后把 locomotion 适配到其他机器人时的参考。

Go2 路线是一项 regression/reference capability，而不是 manipulation 的架构驱动因素。

## 4. 当前状态注意事项

历史 2026-09-07 capability audit 记录：

- Go2 CUDA/static/RSL 是当时最强的 production/qualification 路线；
- Pendulum/TwoWheel 有 host batch Evidence；
- PickCube/NutAssembly 已有 task semantics，但完整 physics execution path 尚未资格化；
- recorder/replay infrastructure 已存在，但仍需逐任务完成 collection/save/load/replay oracle；
- 一个 task/backend 的资格验证不能推广到无关的 task/backend 组合。

P1.0-A（起始 HEAD `9b4a55e8f944daa45a5d4d811ba6a02af4c1cfdc`）已通过人工审查；这是 repository/architecture audit，不是 runtime qualification。当前 PickCube/NutAssembly 没有完整 current-HEAD manipulation qualification；Go2 CUDA/static/RSL 的 current-HEAD qualification 必须在 P1.0 baseline 执行中重新确认。

历史 Evidence 若缺少完整 Core commit、provider revision/version 或执行 profile/task/lifecycle provenance，不能自动视为 current-HEAD qualification。保留其原始通过/失败事实及证据限制，不追补虚构 identity，不把历史运行或已安装 dependency 当作当前验收。

Roadmap claim 必须遵守这些 Evidence 边界，implemented/tested/qualified/planned/unsupported/unknown 使用 [仓库治理定义](../../global/01-repository-ownership-and-boundaries.md#5-capability-与-evidence-治理)。

## 5. Core update gate

Core change 遵循：

~~~text
有 Evidence 支撑的 proposal
        |
        v
Candidate patch
        |
        v
API/contract test
        |
        v
reference task/system regression
        |
        v
Judge / maintainer review
   |             |
reject         promote
   |             |
rollback       Core v(t+1)
~~~

Core 有意保持比 task-local artifact 和 PhysPi experience/Skills 更慢的更新速度。

## 6. Provider 集成治理

针对 GeoPhys、Phase-I planned MuJoCo/SAPIEN/Genesis 以及 Flora 等 render provider change：

### Core 团队定义

- 必需的公共行为；
- capability/admission expectation；
- conformance test；
- error/fail-closed semantics；
- report 中预期的 provider version/capability metadata。

### Provider 团队定义

- numerical/storage/kernel implementation；
- backend-specific cache/graph；
- renderer implementation detail；
- performance engineering。

Core 不得通过增加私有内部 workaround 来让 provider 通过资格验证。

## 7. 默认 smoke suite

首个稳定 Geochora Core 应始终提供默认 smoke command 或受治理的 test group，覆盖：

- import/bootstrap；
- default physics runtime construction；
- reset + 一步/多步；
- 适用时的 default renderer frame/readback；
- trajectory record + replay；
- runner(env, policy) rollout；
- baseline learning smoke；
- report/Evidence generation；
- artifact/experiment provenance。

Smoke suite 不能证明 policy convergence；convergence/performance evaluation 属于另一 Evidence 层级。

P1.0 baseline 应先运行最小 defect-sensitive detector，再考虑昂贵 workflow。缺失的 contract test、失效的历史 detector 或未执行的 envelope 必须记录为 unsupported/unknown 或 coverage gap；不能以 import/demo 替代后宣布全绿。P1.0 operator checkpoint 与 Evidence 布局见 [05](05-phase-1-multi-simulator-blueprint.md#5-实施子阶段) 和 [07](07-phase-1-smoke-testing-and-acceptance.md#7-子阶段-acceptance-package)。

## 8. Judge 与 reporting 治理

Evaluation 与 acceptance 相互独立：

~~~text
Evaluator -> evaluation_report.json + report.md
Judge     -> judge_decision.yaml
~~~

初始阶段由 Human Judge 对 Stage 1 和 Stage 2 验收拥有权威。

未来 Agent Judge 可以使用同一 contract，但必须输出明确的 approve/reject、原因和 requested change。

## 9. Core promotion 来源

Core update 可以来自：

- 系统性/重复出现的 Task Artifact 问题；
- 有 Evidence 支撑的 PhysPi 已验证 Skill 或重复 bottleneck；
- provider/API 集成需求；
- 暴露 Core defect 的 qualification failure。

单个 task-local inconvenience 通常应保留在 Task Artifact 内。可复用 Agent behavior 属于 PhysPi。只有当重复 Evidence 支撑共享可执行能力，且公共 contract、provider 影响和 regression 都经过审查时，才能提升到 Core。

Evidence 可以推动 proposal，但不能自治式 patch Core 或绕过审查。RSI 不是当前 Geochora 的资格验证目标。
