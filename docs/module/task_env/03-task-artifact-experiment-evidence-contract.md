# Task Artifact、Experiment 与 Evidence Contract

> 状态：canonical artifact contract，v0.2
> 日期：2026-10-01

## 1. 三种相互独立的一等对象

Geochora 必须在概念和物理存储上区分这些对象。

### Task Artifact

定义任务是什么，并证明 Stage 1 的有效性/可行性。

### Experiment

定义如何使用一个冻结任务版本来生成数据、学习、rollout 和评估。

### Experiment Evidence

记录发生了什么，并为 Judge、PhysPi 或其他外部经验消费方，以及受审查的 Core 改进 proposal 提供结构化 Evidence。

基数关系：

~~~text
1 个 Task Artifact version -> N 个 Experiment
1 个 Experiment            -> 1 个 canonical Evidence package
~~~

Task Artifact 不得作为一次性副本嵌套在每个 Experiment 中。

## 2. Workspace 布局

Task/Experiment workspace 不提交到 Git。

推荐的 canonical 布局：

~~~text
workspace/
└── tasks/
    └── <task_id>/
        ├── artifacts/
        │   ├── ver_001/
        │   │   ├── manifest.yaml
        │   │   ├── asset.py
        │   │   ├── solution.py
        │   │   ├── task.py
        │   │   ├── local_assets/          # 可选 task-local asset
        │   │   ├── validation/            # Stage-1 validator / feasibility output
        │   │   └── judge_decision.yaml    # Stage-1 decision
        │   └── ver_002/
        │
        └── experiments/
            ├── exp_001/
            │   ├── experiment.yaml
            │   ├── evidence.json
            │   ├── evaluation_report.json
            │   ├── report.md
            │   ├── judge_decision.yaml
            │   ├── videos/
            │   ├── trajectories/
            │   └── refs/
            └── exp_002/
~~~

具体文件名以后可以通过 schema 正式确定，但 artifacts/ 与 experiments/ 的分离属于规范要求。

## 3. Task Artifact 内容

一个 Task Artifact version 包含 Stage 1 所需的任务特定实现。

典型实现文件：

- asset.py：task-local asset 导入与 environment/scene 构造 helper；
- solution.py：expert-route / planning solution 实现或配置；
- task.py：task semantics、observation/action requirement、success/reward/evaluation behavior；
- manifest.yaml：冻结后该版本不可变的 identity/provenance。

需要时可以增加文件，但任务私有实现必须保留在 Task Artifact 内，不得泄漏到 Core。

## 4. Asset 规则

决定任务身份的 asset 属于 Task Artifact，或由它引用。

### 简单的 task-local asset

可以存储在：

~~~text
artifacts/ver_xxx/local_assets/
~~~

例如小型 XML/URDF primitive 或简单生成的 geometry。

### 可复用/复杂 asset

通过 Geochora/asset 解析，Task Artifact 记录稳定的 reference/version/hash。

### Evidence

Experiment Evidence 记录使用的 asset reference/hash，但不会成为 task asset 的 owner。

## 5. Task Artifact 生命周期

最小生命周期：

~~~text
draft -> candidate -> validated -> frozen -> archived
~~~

### draft

Agent、人或 Codex 可以自由编辑。

### candidate

已准备接受 Automatic Validator 与 expert-route validation。

### validated

已产生自动检查和 feasibility Evidence，等待 Judge。

### frozen

Judge 已批准。Stage 2 可以引用，但不得静默修改冻结语义。

### archived

为可复现性/历史保留，但不再是可编辑的活动任务版本。

被拒绝或需要修改的 frozen task 必须产生新版本，不得原地改变 frozen version。

从初始需求到 artifact 获准/冻结的迭代次数，本身也是有价值的 Geochora 系统质量 metric。

## 6. Stage 1 validation contract

### Automatic Validator

检查定义/runtime 有效性，例如：

- schema/config；
- asset/reference；
- provider/runtime capability；
- reset/initial state；
- controller/action compatibility；
- observation sanity。

### Expert Route 与随机化可行性

第一版必须执行 randomized reset probe。

Report 至少必须区分：

- solved；
- invalid execution/state；
- 当前 solver/expert failed 或 unknown。

不得根据当前 expert 失败自动推断任务本身不可行。

### Judge #1

Stage-1 judge_decision.yaml 记录：

- approve / reject；
- 原因；
- 必需修改；
- 可选质量意见；
- judge type（初始为 human；以后可以是 Agent）。

## 7. Domain-randomization contract

本节是规范要求，必须谨慎实现和记录。

### 7.1 Stage 1 / Task Artifact 定义

- 可随机化的 parameter；
- randomization schema；
- hard bound / allowed envelope；
- 默认/nominal training range；
- feasibility-probe distribution；
- frozen evaluation distribution；
- 相关 reset semantics。

概念示例：

~~~yaml
randomization:
  object_position:
    enabled: true
    hard_bound: [-0.20, 0.20]
    default_train_range: [-0.10, 0.10]
    feasibility_range: [-0.15, 0.15]
    evaluation_range: [-0.15, 0.15]
~~~

### 7.2 Stage 2 / Experiment 可以调整

- hard bound 内的 training range；
- allowed envelope 内的 curriculum/schedule；
- 不改变 task semantics 的 sampling weight/parameter。

### 7.3 Stage 2 不得静默改变

- 哪些 quantity 被随机化；
- hard bound；
- frozen evaluation distribution；
- success/failure semantics；
- nominal task definition。

这些变更要求：

~~~text
新 Task Artifact version -> Stage-1 validation -> Judge approval -> freeze
~~~

这样可以防止 Stage 2 为提高表面 policy performance 而降低 benchmark 难度。

## 8. Experiment contract

Experiment 是引用 frozen Task Artifact 的独立一等对象。

experiment.yaml 的最小 identity/provenance 应包含：

~~~text
experiment_id
task_id
task_artifact_version
task_artifact_hash
core_version / commit
physics_provider + capability/profile snapshot
render_provider
expert/data-generation config
learner/policy config
training randomization parameters
seeds
budget/resource limits
evaluation contract reference
external dataset/checkpoint references
~~~

具体 schema 可以演进，但 provenance field 必须可检查。

## 9. 大型 artifact 存储规则

### 存储在 Task/Experiment Git source tree 之外

- 大型 dataset；
- model checkpoint；
- 大型 cache。

Experiment 保存稳定的 reference、identifier、version，并在可行时保存 hash。

### 存储在 Experiment workspace 内

- evaluation video；
- 代表性 trajectory；
- 小型 plot/report；
- machine-readable evaluation/Evidence；
- Judge decision；
- provenance index。

Task Artifact 与 Experiment workspace 不提交到 Git。

PhysPi experience 和 Skill 文档遵循 PhysPi 自己的仓库与 retention policy，不由 Geochora Experiment workspace 管理。

## 10. Evaluation report 与 Judge decision

两者必须保持分离。

### Evaluation report

记录事实：

- task/policy metric；
- rollout statistic；
- ID/OOD result；
- oracle-state / visuomotor result；
- failure case；
- dataset statistic；
- 可获得时的 budget/cost information。

文件：

~~~text
evaluation_report.json
report.md
~~~

### Judge decision

记录权威决策：

~~~yaml
decision: approve   # 或 reject
judge:
  type: human
reason:
  - ...
required_changes:
  - ...
~~~

Agent/Codex 必须消费这个显式 decision，不能从 prose 中推断是否接受。

## 11. Experiment Evidence

evidence.json 是 machine-readable Evidence index/package manifest。

它引用：

- Task Artifact identity/version/hash；
- Experiment identity；
- Core/provider version；
- validation output；
- dataset generation summary；
- training/evaluation summary；
- video/trajectory reference；
- report path；
- Judge decision；
- 可获得时的 Agent/tool/simulation resource usage。

Experiment 产生 Evidence，但不会直接创建经过验证的 PhysPi Skill，也不会授权 Core change。

PhysPi 决定如何保留、提炼、验证 Evidence，并将其提升为经验或 Skills。Geochora maintainer 单独治理 Core change。

## 12. Retention、cleanup 与持久引用

Task Artifact 是 task-local 对象，可以定期 cleanup/archive。

建议的 retention：

- 保留获准/frozen final artifact；
- 当 rejected/failure version 提供有用 Evidence 时，保留关键版本；
- 在 policy 规定的 retention window 后删除冗余临时 draft/cache；
- 保留被提升的 PhysPi knowledge/Skills 或已接受 Core change 所需的 Experiment Evidence。

PhysPi 或其他外部方引用历史 Evidence 时，不能只依赖脆弱的相对路径。至少应保留：

~~~text
task_id
artifact_version
artifact_hash
experiment_id
core_version
~~~

如果 PhysPi 基于特定 Evidence 提升 Skill，则必须保护该 Evidence 不被清理，或将其复制到持久 Evidence store。
