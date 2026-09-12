---
name: task-env-experiment-evidence
description: "Create and operate TaskEnv Task Artifacts, Experiments, evaluation reports, Judge decisions, and canonical Evidence packages without mixing task definitions with run outputs."
---

# TaskEnv Experiment and Evidence

Use this skill when an Agent, human, or Codex constructs a task, validates an
expert route, collects data, trains/evaluates a policy, or packages results for
reproduction. This is an operational skill for using Core; it is not Part B's
experience distillation or Skill-promotion implementation.

## Authority

Follow:

- `docs/module/task_env/02-core-api-and-capability-scope.md`
- `docs/module/task_env/03-task-artifact-experiment-evidence-contract.md`
- `docs/module/task_env/04-core-qualification-and-governance.md`
- `task_env/README.md`

If the current implementation does not yet provide a formal schema or command,
keep the prescribed identity and provenance visible, label the gap, and do not
invent an unsupported success claim.

## Three separate objects

Keep these physically and conceptually distinct:

```text
Task Artifact version -> defines what the task is
Experiment            -> defines how one frozen task is used
Experiment Evidence   -> records what actually happened
```

The cardinality is one frozen Task Artifact version to many Experiments, and
one canonical Evidence package per Experiment. An Experiment must reference a
frozen Task Artifact; it must not contain a disposable copied task definition.

## Workspace contract

Task and experiment workspaces are local and are not committed to Git:

```text
workspace/tasks/<task_id>/
├── artifacts/ver_001/
│   ├── manifest.yaml
│   ├── asset.py
│   ├── solution.py
│   ├── task.py
│   ├── local_assets/          # optional
│   ├── validation/
│   └── judge_decision.yaml
└── experiments/exp_001/
    ├── experiment.yaml
    ├── evidence.json
    ├── evaluation_report.json
    ├── report.md
    ├── judge_decision.yaml
    ├── videos/
    ├── trajectories/
    └── refs/
```

Large datasets, checkpoints, and caches stay outside the source tree. Store
stable external identifiers, versions, and hashes in `experiment.yaml` and
`evidence.json`. Keep representative videos, trajectories, reports, and
machine-readable evidence in the Experiment workspace.

## Task Artifact lifecycle

Use the lifecycle:

```text
draft -> candidate -> validated -> frozen -> archived
```

A version includes the embodiment, task-local or referenced assets, scene,
task semantics, observation/action requirements, controller/action mode,
reset and domain-randomization contract, evaluation contract, and validated
expert-route provenance. A rejected or changed frozen task creates a new
version; never edit a frozen version in place.

Stage 1 has three distinct decisions:

- **Automatic Validator**: checks config/schema, asset/reference, provider
  capability, reset/initial state, controller/action compatibility, and
  observation sanity.
- **Expert Route / randomized feasibility**: reports whether the current
  executable route solved, encountered invalid execution/state, or failed/is
  unknown. Solver failure is not intrinsic task infeasibility.
- **Judge #1**: records explicit `approve` or `reject`, reasons, and required
  changes in the artifact's `judge_decision.yaml`.

A randomized reset probe is required for the first Stage-1 release.

## Experiment procedure

1. Start from a `frozen` Task Artifact and record its ID, version, hash, and
   validation/Judge references.
2. Create a separate Experiment with Core commit/version, provider and
   capability snapshot, expert/data-generation config, learner/policy config,
   seeds, budgets, randomization parameters, and external dataset/checkpoint
   references.
3. Generate expert data from the validated route. Run recorder/replay and
   lightweight observation/action/coverage checks before learning.
4. Run the declared learner and closed-loop evaluation. Keep oracle-state and
   visuomotor routes distinguishable, and report ID/OOD, success/failure,
   robustness, and failure cases where applicable.
5. Write `evaluation_report.json` and `report.md` as facts and metrics only.
6. Write the separate Stage-2 `judge_decision.yaml` with explicit
   `approve`/`reject`, reasons, judge type, and required changes.
7. Finalize `evidence.json` with artifact/experiment identity, versions,
   validation, dataset, training, evaluation, report, video/trajectory, Judge,
   and resource references.

## Domain-randomization ownership

Stage 1 / Task Artifact owns the randomizable quantities, schema, hard bounds,
nominal training range, feasibility distribution, evaluation distribution,
and reset semantics. Stage 2 may tune training ranges and schedules only
inside that envelope. Changing dimensions, hard bounds, evaluation
distribution, or success semantics requires a new Task Artifact version,
Stage-1 validation, Judge approval, and freeze.

## Retention and promotion

Keep approved/frozen artifacts and evidence needed by promoted knowledge or
Skills. Remove redundant drafts or caches only under the retention policy, and
protect historical evidence through stable IDs such as task ID, artifact
version/hash, experiment ID, and Core version. Producing Evidence does not
automatically create or validate a Part B Skill; Part B owns retention,
distillation, validation, and promotion.
