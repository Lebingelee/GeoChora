# Repository instructions

## Authority and scope

- Check the current branch, HEAD, dirty paths, and implementation owners before
  changing repository files.
- Treat implementation and production callers as current behavior; use
  canonical contracts and qualification records to describe intended or
  accepted behavior. Plans and historical reports explain context but do not
  establish current capability by themselves.
- Keep changes bounded. Preserve unrelated dirty files, ignored evidence,
  submodules, and worktrees.

## CodeGraph

- When `.codegraph/` exists at the repository root, use `codegraph_explore` or
  `codegraph explore` before broad search or file reads to locate code and
  trace callers. If no index exists, skip CodeGraph; do not initialize or
  rebuild one for unrelated work.

## Canonical references

- System and ownership: [architecture](docs/global/architecture.md), [ownership](docs/global/ownership.md).
- Current module entry: [TaskEnv](docs/module/task_env/README.md), [public API](docs/module/task_env/public-api.md),
  [Artifact/Experiment/Evidence](docs/module/task_env/task-artifact.md), [qualification](docs/module/task_env/qualification.md).
- Published baseline: [v1.1.0](docs/releases/v1.1/README.md), its single capability matrix and limitations.
  Historical [v1.0.0](docs/releases/v1.0/README.md) remains scoped to its frozen source.
- Current direction: [post-v1.1.0 roadmap](docs/roadmap/README.md).
- Repository governance: [.agents/skills/geochora/SKILL.md](.agents/skills/geochora/SKILL.md),
  [documentation](.agents/skills/geochora-doc-governance/SKILL.md),
  [architecture](.agents/skills/geochora-architecture-refactor/SKILL.md),
  [public API](.agents/skills/geochora-public-api-governance/SKILL.md),
  [tests](.agents/skills/geochora-test-governance/SKILL.md).

## Module Skill activation

Use ordinary prompt text; this convention is not a native Codex slash command:

```text
$geochora-module-skill-maintainer
module: task_env
mode: learn
request: <concrete task>
```

Modes are `learn | audit | refresh | improve`; choose exactly one. The generic
[Module Skill Maintainer](.agents/skills/geochora-module-skill-maintainer/SKILL.md)
locates any requested module's real owner and existing Skill. The discoverable
[TaskEnv module Skill](.agents/skills/geochora-task-env/SKILL.md) routes current APIs/examples.
Reuse [TaskEnv Experiment/Evidence](task_env/.agents/skills/task-env-experiment-evidence/SKILL.md)
for Artifact freeze, Experiment, facts and Judge packaging.

For improve, establish owner → public APIs → existing implementations → production callers → tests →
reproduced/established limitation → repair/extension/composition assessment. Classify as
FIX_EXISTING, EXTEND_EXISTING, COMPOSE_EXISTING or NEW_IMPLEMENTATION; new implementation
requires explicit reasons existing owners cannot support it. Do not duplicate Runtime, Recorder,
Controller, task factory, provider abstraction or Skill, or use provider-private state.
Documentation-only work does not authorize implementation changes.

Review module Skills after API/registry/ownership/workflow/capability/important bugfix/retirement/
test or failure-behavior changes. Refresh from source and callers, detect drift, update references,
validate examples, run bounded checks, produce a receipt and preserve Human review for
API/qualification-sensitive changes. A source diff alone does not validate a Skill.

## Ownership and boundaries

- `task_env/` is the canonical owner of Geochora Core task and environment
  behavior. Core uses GeoPhys through its public/runtime-facing API; GeoPhys
  must not depend on Geochora internals.
- Task-specific behavior belongs to its Task Artifact unless it is reusable
  Core behavior. Keep Task Artifact, Experiment configuration, observed
  Evidence, and Judge decisions distinct.
- Registration, importability, static checks, synthetic checks, or one demo do
  not prove an end-to-end task/provider capability.
- Do not read provider-private solver or renderer state to compensate for a
  missing public capability.

## Capability and evidence language

- State the exact task, provider, backend, source identity, and exercised
  intersection when making a qualification claim. Preserve bounded approval
  labels and their limits.
- v1.1.0 is the published Core consolidation baseline. Selected PickCube/NutAssembly
  GeoPhys/MuJoCo CPU routes are TESTED_BOUNDED, not new Qualification. v1.0.0
  P1.0–P1.6 retain historical bounded approvals; P1.7 remains deferred.
  P1.8 infrastructure/diagnostic results do not grant formal qualification.
- Keep raw physical task predicates separate from lifecycle-valid task
  success, Expert completion, replay validity, and formal qualification.
- Keep diagnostic shadow execution, D1 frozen native controls, D2 frozen
  RequestedAction with live control recomputation, and D0 reconstruction claims
  separate. Never call diagnostic execution a golden or formal approval.
- Update canonical documentation when the supported contract changes. Date
  and identify evidence; do not rewrite frozen historical decisions.

## Repository hygiene and publishing

<a id="phase-branch-workflow"></a>

### Phase branches, commits and Sol/Luna handoff

- Follow the maintainer's explicit workflow preferences over conflicting older
  plans or prompts. Plan the total development branches and worktrees at the
  phase/stage level before execution; normally reuse one topic branch per
  planned stage for multiple sub-stages, Goals and slices. A new Goal prompt
  is not a reason to create another branch or worktree.
- Reuse a suitable existing phase branch. Consider an additional branch or
  worktree for recovery, a separately retained alternative, or an isolated
  comparison/integration after independent or web-GPT review; first record its
  reason, scope, base, expected branch count and reintegration/disposition.
  Discussion alone does not require a new checkout. Preserve historical refs
  and worktrees; do not rename or remove them just to match a naming preference.
- Pair each bounded output with its relevant local commit(s) on that phase
  branch. Reports identify the input/output HEAD, slice/attempt, commits,
  validation and Evidence references. Raw generated workspace data stays
  ignored; an audit-only output can be paired with a tracked summary/index
  commit by its designated owner instead of committing raw logs or creating an
  empty commit. Do not stage another writer's pending files.
- For Sol/Luna work, follow the phase execution table by default: Sol prepares
  one self-contained, authorized, ready work package; Luna executes that slice,
  validates and makes its permitted local commit(s), then returns its report;
  Sol reviews the actual diff and available Evidence before sending the next
  slice. Luna's reported PASS is input to that review, not automatic acceptance.
  Keep one writer at a time and use the same phase branch across handoffs.
- Size packages to the change. A basic change with known owners normally
  combines implementation, targeted validation, necessary in-scope fixes and
  local commit(s) in one package. Separate preparation only for unknowns that
  affect the implementation decision; do not impose fixed preparation rounds.
  Reuse unchanged evidence and repeat checks only for an affected input,
  new change, failure or unresolved concern. Sol may fix minor review issues
  directly or include them in the implementation package; additional
  preparation requires a concrete mandatory blocker, not report formatting
  or an unapproved extension of the original completion criteria.
- Freeze HEAD and protected input bytes for each Luna execution window,
  including ignored-output-only audits. Sol lands review/summary/document
  commits after Luna returns and before issuing the next package. If urgent
  maintainer steering changes an in-flight baseline, explicitly interrupt or
  amend that package with the exact commit/diff/hashes; preserve the old
  snapshot and require readback before resuming.
- If a gate fails, Sol issues one bounded rework package. If the next table row
  is blocked, record the blocker and any explicit decision to advance an
  independent ready row; do not silently reorder work or add dependencies.
  Scope approval remains separate from this development workflow, and
  push/merge/tag/Release still require their existing authorization.

- Keep generated `workspace/` data untracked. Historical P1.6 closure metadata
  remains in immutable v1.0.0. Preserve local bytes, decisions, hashes and
  relocation mappings before cleanup. Protect current L2 originals and frozen decisions;
  historical source recovery uses annotated tags and the consolidation inventory.
- The repository currently has no root `pyproject.toml`, `setup.py`, or
  `setup.cfg`; document dependency installation and `PYTHONPATH`, not editable
  installation, unless packaging metadata is added deliberately.
- Keep annotated v1.0.0/v1.1.0 tags and the v1.1.0 release branch immutable.
  At a new phase/stage boundary, prepare its planned topic branch from fetched
  current develop, preserving intentional local commits. Reuse that phase
  branch for subsequent Goal prompts; do not reset or recreate it per slice.
  Do not push or merge before maintainer review authorization. After approval,
  fetch/check and integrate normally into develop, then main; never rewrite frozen refs.
- Run checks appropriate to the changed files and report what ran, what did
  not run, and any open limitation. Do not claim unperformed validation.
