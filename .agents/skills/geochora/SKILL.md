---
name: geochora
description: "Apply the Geochora repository workflow when changing Core, providers, task contracts, experiment infrastructure, or cross-boundary documentation; use a task-local workflow for changes confined to one Task Artifact."
---

# Geochora Repository Workflow

Use this skill for repository-wide Geochora work. It establishes ownership,
scope, evidence, and qualification boundaries; it does not replace the more
specific architecture, documentation, public-API, test, or TaskEnv evidence
skills.

## Authority

Before making a material change, inspect the current branch, HEAD, dirty paths,
and the real implementation path. Treat sources in this order:

1. current implementation and production callers;
2. canonical contracts in `docs/global/` and the relevant module documents;
3. executable tests and qualification evidence;
4. plans or historical records only when the task needs their rationale.

When the repository has a current CodeGraph index, use `codegraph status` and
`codegraph explore` to locate code and trace relationships before broad text
search. Do not initialize or rebuild an index as part of an unrelated task.

Read these pages when the task crosses their concerns:

- `docs/global/architecture.md`
- `docs/global/ownership.md`
- `docs/module/task_env/public-api.md`
- `docs/module/task_env/task-artifact.md`
- `docs/module/task_env/qualification.md`

## Classify the change first

Choose one primary owner before editing:

- **Task-local**: the change belongs in a Task Artifact and does not alter
  shared Core behavior.
- **Reusable Agent experience or Skill**: the change belongs to PhysPi (or
  another external Agent consumer) and must not be implemented by importing
  that consumer's internals into Core.
- **Core capability**: the change alters reusable task/environment behavior,
  contracts, providers, recording, learning, evaluation, or qualification and
  requires Core review and regression evidence.

Do not keep a second actively maintained canonical copy of `task_env` in
GeoPhys. The dependency direction is:

```text
Geochora/task_env -> GeoPhys public/runtime-facing API
GeoPhys             -X-> Geochora/task_env
```

## Required workflow

1. Declare what this change includes and excludes.
2. Identify the current owner, consumers, state/lifecycle transitions, and
   provider boundary. Use real callers rather than filenames alone.
3. Make one bounded change unit. Keep adjacent gaps as follow-up items unless
   they are required for the declared contract.
4. Validate the smallest relevant contract and golden path. State exactly
   which solver/provider, backend, asset, and representation were exercised.
5. Update the canonical document when the supported contract changed, and
   report changed files, checks, unsupported intersections, and remaining risk.

## Phase branches and handoffs

Follow the maintainer's [phase branch and Sol/Luna policy](../../../AGENTS.md#phase-branch-workflow): plan branches/worktrees per phase or stage, reuse the current phase branch across Goal prompts, and associate each bounded output with its relevant local commit(s). For Phase II-01, the [execution table](../../../docs/module/task_env/goal/Phase_II_01/07_Execution_Order_and_Acceptance.md#sol-luna-workflow) owns its concrete branch plan, sequential Sol → Luna → Sol review loop and audit-summary commit route. Preserve old receipts and check the actual committed HEAD before the next handoff; this workflow does not grant implementation, publishing or Qualification approval.

### One complete prompt per Luna execution window

- Before dispatch, freeze one self-contained package: slice/attempt ID, target
  thread, checkout/branch/input HEAD, prompt path and SHA-256, protected inputs,
  allowed changes, acceptance gates, execution budgets, output directory and
  required final report. Keep this index with the package so review can match
  the response to the exact prompt. Include implementation, in-scope repairs,
  validation and evidence/report/commit cleanup in the original package.
- Assign an expected duration based on scope and known dependencies. Useful
  planning ranges are 15–30 minutes for a bounded audit/document edit,
  30–90 minutes for a known-owner implementation with targeted checks, and
  90–180 minutes for integration with native execution and independent readers.
  Adjust for actual difficulty and prior attempts; do not split work merely to
  fit these examples. Estimate downloads separately from active development.
  Expected duration is not a timeout, success criterion, retry allowance or
  permission to extend the package's hard native/resource limits.
- Keep at most one unfinished package per Luna thread. While Luna executes,
  collect new findings and proposed next steps in Sol's own review notes;
  do not send supplemental prompts, review requests, reminders or new tasks
  into that thread. Inspect progress through read-only status tools. Passing
  the expected duration alone does not justify interruption or another prompt.
- Wait for a complete final response to the original package, including actual
  outcome (PASS/FAIL/BLOCKED), input/output HEAD, permitted local commits,
  validation and evidence paths, remaining blockers and explicit release of
  the writing/native window. A progress update, tool result, interrupted turn,
  capacity error or idle UI alone is not a completed handoff. A failed gate
  can still have a complete handoff; implementation success is not required
  before Sol may review it.
- After the final response, review the actual diff and evidence against that
  frozen package. Then send one consolidated rework/continuation or the next
  authorized package. If the report is incomplete, address its missing items
  in that one continuation rather than layering more messages onto execution.
  After interruption, first confirm the worker has stopped and ownership is
  clear, then issue one recovery package with the preserved progress.
- An explicit maintainer redirection or an immediate safety/resource issue
  may require stopping early. Record the reason, stop and confirm the current
  execution/window has ended, preserve its prompt/snapshot/progress, then
  dispatch one replacement package with an explicit supersedes reference and
  changed scope/HEAD/hashes. Do not silently append requirements. If Luna
  explicitly pauses for a required clarification, answer only that question;
  a scope change follows the same replacement procedure.
- Parallel Luna threads may each hold one package only under the existing
  independent-checkout/scope and shared native-lock rules. One thread's early
  return does not authorize injecting work into another active thread.

### Goals spanning multiple substages

For a maintainer-authorized goal covering multiple substages, follow the
[goal orchestration procedure](references/goal-orchestration.md): locate each
substage's implementation details in its planning document, aim for research
and implementation in attempt 1 and review/acceptance in attempt 2, and cap
each substage at three attempts. Before attempt 3, reassess the actual blockers,
research relevant open-source implementations and decide whether the original
acceptance remains achievable. Track Luna through periodic read-only checks;
prepare future work privately during report cleanup, then independently verify
the completed handoff before dispatch. This procedure does not itself create a
goal or start/message additional agents.

## Non-negotiable boundaries

- Core must not repair a provider through private solver or renderer state.
- Registration, importability, or a single demo is not proof of end-to-end
  support.
- Fail closed when a requested capability is outside verified evidence.
- Keep Task Artifact, Experiment, and Experiment Evidence distinct.
- Do not silently change a frozen task/evaluation contract during Stage 2.
- Preserve unrelated dirty files, generated outputs, submodules, and worktrees.

Use the specialized skills when their trigger applies:
`geochora-architecture-refactor`, `geochora-doc-governance`,
`geochora-public-api-governance`, and `geochora-test-governance`. When work
concerns Task Artifact, Experiment, or Evidence, also read the canonical
contract at
`docs/module/task_env/task-artifact.md`.
