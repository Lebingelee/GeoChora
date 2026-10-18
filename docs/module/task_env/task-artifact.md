# Task Artifact、Experiment 与 Evidence

本页保留原 Artifact/Experiment/Evidence 的规范要求；字段与文件名示例是 workspace contract，
不声称已有统一、资格化的 schema loader/Validator/Experiment Engine。当前高级数据对象见
[`task_env/artifacts/contracts.py`](../../../task_env/artifacts/contracts.py)。

## 三个独立对象与工作区

一个 Task Artifact version 定义任务，供多个 Experiment 引用；一个 Experiment 定义如何使用
冻结任务，并产生一个 canonical Evidence package。不得在每个 Experiment 内嵌一次性任务副本。

```text
workspace/tasks/<task_id>/
  artifacts/ver_001/
    manifest.yaml, asset.py, solution.py, task.py
    local_assets/, validation/, judge_decision.yaml
  experiments/exp_001/
    experiment.yaml, evidence.json, evaluation_report.json, report.md
    judge_decision.yaml, videos/, trajectories/, refs/
```

生成 workspace 不提交。world/initialization/semantics 可按内聚性拆分，不强制具体 Python 文件名。
Task-local asset 属于 Artifact，复杂资源通过 `asset/` 引用稳定 version/hash；Evidence 只记录实际使用身份。
大 dataset、checkpoint、cache 放 source tree 外，以稳定 reference/version/hash 引用。
代表性 trajectory/video、plot/report、provenance index 与 machine-readable facts 留 Experiment。

## 任务 contract 与冻结

Artifact 包含 embodiment/world、semantic names、geometry/inertia intent、asset references、
initialization/randomization、timebase、observation/action/controller requirement、success/failure/reward、
evaluation contract 和 solution provenance。provider 选择属 `ExecutionSpec`，不改变任务身份。
Provider-neutral world/semantics 不导入 provider-native API；task adapters 在独立边界实现 materialization。
高级 strict codec 拒绝未知字段/schema、未声明 semantic references、非 finite values 和未知 capability；
TaskArtifact identity 只 hash artifact mapping，不接受 execution field；确定性 JSON/YAML roundtrip 保留原值。

生命周期为 `draft -> candidate -> validated -> frozen -> archived`。
validated 表示产生检查/feasibility Evidence、等待 Judge；frozen 必须有明确批准。
拒绝或修改 frozen 任务必须新建版本，不得原地改变语义。
从初始需求到获准冻结的迭代次数应作为系统质量 metric 记录。

Stage 1 必须分别记录：

- Automatic Validator：config/schema、asset/reference、capability、reset/realized state、controller/action、
  observation finite/sanity checks；当前这些校验分散实现，统一 Validator 仍有缺口。
- Expert/randomized feasibility：首个 Stage-1 release 必须有 randomized reset probe，分别报告
  solved、invalid execution/state、expert failed/unknown；expert 失败不等于任务不可行。
- Human Judge #1：`judge_decision.yaml` 显式 `approve`/`reject`、judge type、原因、required_changes、
  可选质量意见。Agent 不得根据报告 prose 猜测批准。

Task Success、Expert Completion、episode terminated/truncated 分别属于语义、Solution、runtime；
存在成功后动作时必须声明不可变 completion policy、terminal stage、readiness/timeouts/budget 和
record/replay 状态，见[runtime contract](runtime-and-providers.md#expert-lifecycle)。

## Randomization 所有权

Stage 1 定义随机化 quantity/schema、hard bounds/allowed envelope、nominal train range、
feasibility distribution、frozen evaluation distribution、reset semantics 和可选 declared settle。
Core sampler 通过 task_seed 产生 `ResetSample`；provider_seed 与 determinism 独立，provider 不重新采样任务参数。
记录 requested sample 与 `RealizedInitialState`；超出声明的 reset tolerance 必须在 rollout 前失败。
正式 paired comparison 使用同一个 frozen EvaluationSampleSet，不以相同整数 seed 假设不同 provider 初态相同。

Stage 2 仅可在 envelope 内调整 training range、curriculum/schedule、sampling weights。
改变随机化维度、hard bounds、frozen evaluation distribution、success/failure 或 nominal task
必须走新 Artifact → Stage-1 validation → Judge → freeze，不能为了性能降低 benchmark 难度。

## Experiment provenance 与报告

`experiment.yaml` 至少保留 experiment/task IDs、Artifact version/hash、Core commit/version、
physics provider/capability/profile、render provider、expert/data config、learner/policy config、
training randomization、seeds、budget/resource limits、evaluation reference、external dataset/checkpoint refs。
事实报告包含 task/policy metrics、rollout stats、ID/OOD、oracle-state/visuomotor 区别、failure cases、
dataset statistics 及可获得的 budget/cost。事实写 `evaluation_report.json` 和 `report.md`；
Stage-2 acceptance 写独立 `judge_decision.yaml`，Human review 不被 metric 自动替代。

`evidence.json` 索引 Artifact/Experiment/Core/provider identities、validation、dataset/training/evaluation
summaries、video/trajectory refs、report、Judge 和可获得的 Agent/tool/simulation resource usage。
它不授予 Core patch 权限，不直接创建可信 PhysPi Skill。PhysPi 决定经验保留/提炼/验证，
Core promotion 由 Geochora maintainer 单独治理。

## Retention

保留 frozen/approved final Artifact、有诊断价值的失败版本、被提升知识/Skill/Core change 所依赖的 Evidence。
冗余 drafts/cache 仅按 retention policy 清理；跨系统引用不能只依赖易失相对路径，至少绑定
`task_id`、Artifact version/hash、`experiment_id`、Core version，并保护被引用 bytes 或复制到持久 store。
不要把 metadata/hash 当作丢失 raw Evidence 的替代。操作步骤复用
[已有 Experiment/Evidence Skill](../../../task_env/.agents/skills/task-env-experiment-evidence/SKILL.md)，
不再创建同义 Skill 或 schema。
