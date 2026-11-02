---
name: geochora-task-env
description: Use GeoChora TaskEnv public construction, task/provider execution, recording, and evaluation routes; locate the current owner before proposing a change.
---

# TaskEnv Module Skill

Read repository [`AGENTS.md`](../../../AGENTS.md), the [TaskEnv version index](../../../docs/module/task_env/README.md), and the [v2.1.0 candidate overview](../../../docs/module/task_env/v2.1.0/README.md). `task_env/` is the sole GeoChora Core owner. Use its public APIs and the exact versioned capability matrix; plans and imports do not establish runtime support.

## Current construction route

`task_env.make_env(uid, config=...)` is the public registered single-environment factory. The selected references are `pick-cube-p16-reference-v1` and `nut-assembly-outcome-reference-v1`; retired selected UIDs fail explicitly. `TaskArtifactDeclarationV1` declares task semantics and `ReferenceTaskDeclarationV1` binds source references and an optional pure Controller. Compilation does not start a provider. The selected mutable lifecycle has one `SelectedReferenceEnv → RuntimeSession → provider adapter` route.

Task-specific source/reset/evaluation/Solution behavior stays with its Task Artifact or benchmark owner. Reuse `task_env` owners; do not add another factory, Runtime, Recorder, Controller, or provider abstraction. Keep LIBERO benchmark behavior under `bench_deploy/libero`.

## Selected configuration

Selected configuration uses nested `execution`, `episode`, and `task` sections. Precedence is Core → task class → task YAML → caller. Legacy `recipe`/`environment` values and supported flat aliases normalize once; unknown fields, conflicting aliases, task-identity mismatch, and unsupported provider/backend/device or render pairing fail closed. The full renderer contract is `RendererSelectionV1`; selected tasks currently admit only state-only (`renderer-selection-v1`, provider `none`, backend `cpu`, profile `none`, device `null`). Non-`none` selected rendering is rejected, not silently downgraded.

PickCube defaults to `r3_continuous_v1`; `r1` is explicit. The bounded selected provider envelope is GeoPhys CPU and MuJoCo CPU, plus the exact PickCube Isaac Sim 6.2/CUDA PhysX source route recorded in the [matrix](../../../docs/module/task_env/v2.1.0/capabilities/capability-matrix.json). Do not generalize to other tasks/assets or a renderer matrix. The resolved configuration, including renderer selection, flows into construction and record metadata. Missing Controller identity is represented as `null` during pure compilation; this is not execution admission.

## Recording, Expert, and evaluation

Use the [recording/learning contract](../../../docs/module/task_env/v2.1.0/contracts/recording-and-learning.md) and independent H5 inspection route. T transitions and T+1 boundaries, source identity, resolved config, close outcome, task success, Expert completion, replay validity, and Judge decisions are separate facts. Expert/Solution execution is explicit and task-owned; a constructor or one rollout does not establish task success.

For Artifact, Experiment, Evidence, and Judge packaging, also use the existing [`task-env-experiment-evidence` Skill](../../../task_env/.agents/skills/task-env-experiment-evidence/SKILL.md). For CLI-owned task candidates, follow the existing [Task Harness Skill](../geochora-task-harness/SKILL.md); do not confuse candidate feasibility with an accepted task.

## Source and advanced interfaces

Use [USD delivery and source identity](../../../docs/module/task_env/v2.1.0/contracts/task-artifact.md) and [runtime/provider boundaries](../../../docs/module/task_env/v2.1.0/contracts/runtime-and-providers.md) for explicit asset intake, representation, admission, and optional readback. Diagnostic readbacks are optional interfaces; they do not expand provider capability or authorize access to private solver state. Historical APIs and receipts remain under the versioned `history/` and `maintenance/` directories.

## Capability and evidence boundary

The v2.1.0 matrix is the single current TaskEnv table. F06 has 9/9 runtime-valid runs but 0/9 task success. A123's six exact replay runs ended `external_stop` with task success false; task2 GeoPhys's accepted exception remains scoped. Task1 GeoPhys fluid projection is `NOT_MEASURED`; GP07 reuses historical renderer evidence and is not a current-P renderer run. Natural Kit destruction is not claimed fixed; strict DG03 remains unresolved. None of this grants Qualification.

Use [troubleshooting](../../../docs/module/task_env/v2.1.0/guides/troubleshooting.md) to stop at the earliest failure boundary. Do not weaken an oracle, use mock evidence as a native pass, or infer support from registration.

## Development and migration

Before proposing behavior, identify the public facade, owner, callers, tests, and limitation; classify work as fix/extend/compose/new. Use CodeGraph when the index is current. Run only the smallest affected offline/API or bounded route checks authorized by the task. The repository has no root packaging metadata; use `task_env/requirements.txt` and explicit `PYTHONPATH`, not `pip install -e .`.

The next approved migration is not included in this candidate: complete public TaskDefinition migration for PickCube and NutAssembly, share common public construction with LIBERO while keeping benchmark semantics in `bench_deploy/libero`, and compatibility-check other lightweight tasks. See [current scope](../../../docs/module/task_env/v2.1.0/planning/current-scope.md) and [API handoff](../../../docs/module/task_env/v2.1.0/maintenance/reviews/integration/20261102_v210_integration_baseline.md).
