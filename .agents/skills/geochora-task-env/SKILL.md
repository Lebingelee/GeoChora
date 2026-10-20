---
name: geochora-task-env
description: "Use GeoChora TaskEnv public construction, expert execution, recording and evaluation routes, or locate their owners before proposing a change; apply to current task/provider workflows."
---

# TaskEnv Module Skill

Read repository `AGENTS.md` and [module README](../../../docs/module/task_env/README.md).
`task_env/` is the sole Core owner; use its public APIs. No historical chat context is required.
For the source/contract/test map read [routes](references/routes.md) when implementing a workflow or diagnosing a gap.

## Choose the actual construction branch

- Generic scalar: `from task_env import make_env`; e.g. `make_env("pendulum-v1",
  config={"runtime":{"backend":"cpu"}})`. Call reset before step and always close in finally.
- Selected PickCube: UID `pick-cube-p16-reference-v1`, config `{"provider":"mujoco",
  "backend":"cpu","horizon":6000}`; published bounded scope CPU/100 Hz/seed 31, lift-only predicate.
- Selected NutAssembly: UID `nut-assembly-outcome-reference-v1`, same flat config, seed 19/NA-S0.
  Use guarded `step_expert()` only. Do not send arbitrary external actions or use legacy UID/builders.
- Selected config accepts provider/backend/horizon only: geophys/mujoco, scalar CPU, horizon integer 1–6000.
  No render, legacy overlays, SAPIEN/Genesis or implicit batch support. Generic parallel must have explicit
  homogeneous registration and merged_scene layout; no scalar fallback.

Use [examples](../../../examples/README.md) for exact current CLI commands. Preserve fresh output paths,
resource bounds and provenance. Repository has no root packaging metadata: dependencies via requirements,
run from root with `PYTHONPATH=GeoPhys/src:.`; do not recommend editable installation.

## Outcomes, recording and evaluation

Task predicate, Outcome V1 completion, strict Expert lifecycle, termination/truncation, replay validity
and Judge approval are different facts. NutAssembly GeoPhys accepted readiness warning/strict failure
must not be erased by successful outcome. Do not stop a required retreat at first task success.

For selected expert recording use `examples/recording/record_expert.py` or
`task_env.script.trajectory.record`, which reuse the selected env's recorder owner.
`start_recording(path)` is at reset boundary; finalize before another reset. Inspect with
`examples/recording/inspect_h5.py`; T transitions require T+1 boundaries. Generic wrappers use
`task_env.recorders`; selected canonical/execution formats differ from generic raw H5 v2.
The inspector validates loaded storage/T+1; its `storage_roundtrip` field does not mean it
performed a new save/load roundtrip. H5 roundtrip itself is storage integrity, not D0 restoration
or formal replay qualification.

For task construction/freeze, randomized feasibility, Experiments, evaluation report, explicit Human
Judge and Evidence packaging, load the existing
[task-env-experiment-evidence Skill](../../../task_env/.agents/skills/task-env-experiment-evidence/SKILL.md).
It owns that procedure; this Skill does not copy or replace it. Workspace manifests/reports/Judge
files currently require explicit preparation under that contract; no unified Experiment Engine,
validator command or automatic approval is implied. A built-in recipe/Artifact hash is not an
independent Stage-1 Judge approval; verify the referenced approval package, or report its absence
and prepare the required validation/Judge review before claiming a newly frozen task.

## Capability and change boundaries

Use the [single published matrix](../../../docs/module/task_env/capability_matrix_v1_1_0_candidate.json)
with exact source/config/provider/backend/task identity. Candidate wording in its frozen metadata records
review time; v1.1.0 publication is documented separately. Historical report/source paths inside this
byte-preserved matrix may be tag-only: resolve them through
[consolidation inventory](../../../docs/maintenance/consolidation-inventory.json) or
`git show refs/tags/v1.1.0:<original-path>`, not by assuming local files still exist.
IMPLEMENTED != TESTED_BOUNDED != QUALIFIED.
No new P1.8 FULL/D0-D2, manipulation checkpoint/PPO, native Flora/GeoPhys Rigid Batch or general
Physics × Renderer qualification. Pendulum learning/RGB smokes are bounded wiring, not convergence.
The 2026-10-20 GeoPhys development sync has a newer Gitlink than v1.1.0; use the checked-out
revision and the bounded [sync receipt](../../../docs/module/task_env/runtime-and-providers.md#geophys-开发基线同步2026-10-20).
Published v1.1.0 qualification/acceptance does not transfer to this provider revision.

Physics and renderer stay separate. Never read provider-private solver/renderer state. Task semantics
and stages stay task-owned; reuse controller/observation/recording/learner/render contracts.
Go2/static-template and historical camera/task routes are RETIRED, not aliases; use migration/recovery refs.
Unsupported combinations fail closed; locate exact error and first violated invariant before patching.

Before changing behavior, identify owner/public API/existing implementation/production callers/tests,
establish the limitation, and evaluate repair/extension/composition. Use
[module maintainer](../geochora-module-skill-maintainer/SKILL.md) `mode: improve` and classify the proposal;
never add duplicate Runtime/Recorder/Controller/factory/provider/Skill. Documentation requests do not
authorize implementation changes. Review Skill drift after API/registry/ownership/workflow/status/bugfix/
retirement/test/failure changes, using the maintainer refresh procedure and bounded validation.
