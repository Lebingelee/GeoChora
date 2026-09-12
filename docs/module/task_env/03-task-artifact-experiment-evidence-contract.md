# Task Artifact, Experiment, and Evidence Contract

> Status: canonical artifact contract, v0.1  
> Date: 2026-09-12

## 1. Three distinct first-class objects

Geochora must keep these objects conceptually and physically distinct.

### Task Artifact

Defines **what the task is** and proves Stage 1 validity/feasibility.

### Experiment

Defines **how a frozen task version is used for data generation, learning, rollout, and evaluation**.

### Experiment Evidence

Records **what happened** and provides structured evidence for Judge, Part B, and Core improvement proposals.

Cardinality:

```text
1 Task Artifact version -> N Experiments
1 Experiment            -> 1 canonical Evidence package
```

Task Artifact must not be nested as a disposable copy inside each Experiment.

## 2. Workspace layout

Task/experiment workspaces are not committed to Git.

Recommended canonical layout:

```text
workspace/
└── tasks/
    └── <task_id>/
        ├── artifacts/
        │   ├── ver_001/
        │   │   ├── manifest.yaml
        │   │   ├── asset.py
        │   │   ├── solution.py
        │   │   ├── task.py
        │   │   ├── local_assets/          # optional task-local assets
        │   │   ├── validation/            # Stage-1 validator / feasibility outputs
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
```

The exact filenames may later be formalized as schemas, but the separation between `artifacts/` and `experiments/` is normative.

## 3. Task Artifact contents

A Task Artifact version contains the task-specific implementation required for Stage 1.

Typical implementation files:

- `asset.py`: task-local asset import and environment/scene construction helpers;
- `solution.py`: expert-route / planning solution implementation or configuration;
- `task.py`: task semantics, observation/action requirements, success/reward/evaluation behavior;
- `manifest.yaml`: immutable identity/provenance for this version after freeze.

Additional files are allowed when needed, but task-private implementation must remain inside the Task Artifact rather than leaking into Core.

## 4. Asset rule

Assets that determine task identity belong to the Task Artifact or are referenced by it.

### Simple task-local asset

May be stored under:

```text
artifacts/ver_xxx/local_assets/
```

Examples: a small XML/URDF primitive or simple generated geometry.

### Reusable/complex asset

Resolved through `Geochora/asset`, with the Task Artifact recording a stable reference/version/hash.

### Evidence

Experiment Evidence records the asset references/hashes used, but does not become the owner of task assets.

## 5. Task Artifact lifecycle

Minimum lifecycle:

```text
draft -> candidate -> validated -> frozen -> archived
```

### `draft`

Agent/human/Codex may freely edit.

### `candidate`

Ready for Automatic Validator and expert-route validation.

### `validated`

Automatic checks and feasibility evidence have been produced; awaiting Judge.

### `frozen`

Judge approved. Stage 2 may reference it but may not silently change frozen semantics.

### `archived`

Retained for reproducibility/history but not an active editable task version.

A rejected or modified frozen task must produce a new version. Do not mutate a frozen version in place.

Iteration count from initial requirement to approved/frozen artifact is itself a useful Geochora system-quality metric.

## 6. Stage 1 validation contract

### Automatic Validator

Checks definition/runtime validity, such as:

- schema/config;
- asset/reference;
- provider/runtime capability;
- reset/initial state;
- controller/action compatibility;
- observation sanity.

### Expert Route & randomized feasibility

A randomized reset probe is mandatory in the first release.

The report must distinguish at least:

- solved;
- invalid execution/state;
- current solver/expert failed or unknown.

Do not automatically infer intrinsic task infeasibility from current expert failure.

### Judge #1

Stage-1 `judge_decision.yaml` records:

- `approve` / `reject`;
- reasons;
- required changes;
- optional quality comments;
- judge type (`human` initially; agent possible later).

## 7. Domain-randomization contract

This section is normative and must be implemented/documented carefully.

### 7.1 Stage 1 / Task Artifact defines

- randomizable parameters;
- randomization schema;
- hard bounds / allowed envelope;
- default/nominal training range;
- feasibility-probe distribution;
- frozen evaluation distribution;
- relevant reset semantics.

Conceptual example:

```yaml
randomization:
  object_position:
    enabled: true
    hard_bound: [-0.20, 0.20]
    default_train_range: [-0.10, 0.10]
    feasibility_range: [-0.15, 0.15]
    evaluation_range: [-0.15, 0.15]
```

### 7.2 Stage 2 / Experiment may tune

- training range inside the hard bound;
- curriculum/schedule inside the allowed envelope;
- sampling weights/parameters that do not change task semantics.

### 7.3 Stage 2 may not silently change

- which quantities are randomized;
- hard bounds;
- frozen evaluation distribution;
- success/failure semantics;
- nominal task definition.

Such changes require:

```text
new Task Artifact version -> Stage-1 validation -> Judge approval -> freeze
```

This prevents Stage 2 from making the benchmark easier in order to improve apparent policy performance.

## 8. Experiment contract

An Experiment is a separate first-class object referencing a frozen Task Artifact.

Minimum `experiment.yaml` identity/provenance should include:

```text
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
```

Exact schema may evolve, but provenance fields must remain inspectable.

## 9. Large artifact storage rule

### Stored outside the Task/Experiment Git source tree

- large datasets;
- model checkpoints;
- large caches.

The Experiment stores stable references, identifiers, versions, and hashes where practical.

### Stored inside the Experiment workspace

- evaluation videos;
- representative trajectories;
- small plots/reports;
- machine-readable evaluation/evidence;
- Judge decision;
- provenance index.

Task Artifacts and Experiment workspaces are not committed to Git.

Part B memory/skill documents may be committed to Git according to the Part B team's policy.

## 10. Evaluation report vs Judge decision

These must remain separate.

### Evaluation report

Records facts:

- task/policy metrics;
- rollout statistics;
- ID/OOD results;
- oracle-state / visuomotor results;
- failure cases;
- dataset statistics;
- budget/cost information where available.

Files:

```text
evaluation_report.json
report.md
```

### Judge decision

Records authority decision:

```yaml
decision: approve   # or reject
judge:
  type: human
reason:
  - ...
required_changes:
  - ...
```

Agent/Codex must consume this explicit decision and must not infer acceptance from prose.

## 11. Experiment Evidence

`evidence.json` is the machine-readable evidence index/package manifest.

It references:

- Task Artifact identity/version/hash;
- Experiment identity;
- Core/provider versions;
- validation outputs;
- dataset generation summary;
- training/evaluation summaries;
- videos/trajectory references;
- report paths;
- Judge decision;
- agent/tool/simulation resource usage when available.

Experiment produces Evidence. Experiment does **not** directly create a validated Part B Skill.

Part B decides how Evidence is retained, distilled, validated, and promoted.

## 12. Retention, cleanup, and durable references

Part A is task-local and may be periodically cleaned/archived.

Recommended retention:

- keep approved/frozen final artifacts;
- keep key rejected/failure versions when they provide useful evidence;
- delete redundant temporary drafts/caches after policy-defined retention windows;
- keep Experiment Evidence required by promoted Part B knowledge/skills.

Part B references to historical evidence must not rely only on fragile relative paths. At minimum retain identifiers such as:

```text
task_id
artifact_version
artifact_hash
experiment_id
core_version
```

If Part B promotes a skill based on specific evidence, that evidence must be protected from cleanup or copied to a durable evidence store.
