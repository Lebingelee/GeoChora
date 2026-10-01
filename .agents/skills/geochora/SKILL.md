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

- `docs/global/00-system-architecture-anchor.md`
- `docs/global/01-repository-ownership-and-boundaries.md`
- `docs/module/task_env/02-core-api-and-capability-scope.md`
- `docs/module/task_env/03-task-artifact-experiment-evidence-contract.md`
- `docs/module/task_env/04-core-qualification-and-governance.md`

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
`geochora-public-api-governance`, `geochora-test-governance`, and
`task-env-experiment-evidence`.
