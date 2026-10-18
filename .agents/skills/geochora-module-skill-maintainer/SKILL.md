---
name: geochora-module-skill-maintainer
description: "Learn, audit, refresh or improve a GeoChora module Skill from current public APIs, callers and evidence; use module and mode to select the owner and workflow."
---

# Module Skill Maintainer

Activate in ordinary prompt text (not a native slash command):

```text
$geochora-module-skill-maintainer
module: task_env
mode: learn | audit | refresh | improve
request: <concrete outcome>
```

Choose one mode, not the literal list. Apply to future modules by locating their actual owner/API/Skill;
do not silently substitute task_env or invent missing module implementations.

## Start from authority

Read repository `AGENTS.md`; inspect branch/HEAD/dirty paths and current module owner. With a CodeGraph
index, explore the module/API/callers before broad searches. Implementations and production callers
establish behavior, canonical docs establish contracts, tests and published Evidence bound claims.
Plans do not prove support. Resolve stale docs without rewriting historical decisions.

- **learn**: route the concrete request through current public API and module Skill; explain supported
  intersections, workflow, outputs and likely failure behavior. Do not implement a replacement.
- **audit**: compare Skill routes/claims with source, callers, docs, tests and capability evidence;
  report drift with paths/lines and impact; do not edit merely because an audit was requested.
- **refresh**: update the existing module Skill/references after verified drift; follow the
  [refresh procedure](references/refresh.md), validate examples, and produce a receipt.
- **improve**: use the mandatory reuse gate below before proposing or changing behavior. Improvement
  mode does not itself authorize implementation changes, external publishing or qualification promotion.

TaskEnv's module Skill is [geochora-task-env](../geochora-task-env/SKILL.md). Reuse the existing
[Experiment/Evidence Skill](../../../task_env/.agents/skills/task-env-experiment-evidence/SKILL.md)
when that contract is involved; do not create a duplicate Skill.

## Mandatory reuse-before-reimplementation gate

Before any new implementation: identify canonical owner; inspect current public APIs; search current
implementations; trace production callers; inspect existing tests; reproduce or establish the limitation;
then evaluate repair/extension/composition. Record concrete evidence for all seven steps.

Classify the proposal as `FIX_EXISTING`, `EXTEND_EXISTING`, `COMPOSE_EXISTING`, or `NEW_IMPLEMENTATION`.
The last requires explicit justification why existing owners cannot support the requested behavior.
Do not duplicate Runtime, Recorder, Controller, task factory, provider abstraction or Skill; never
bypass public APIs through provider-private internals or create another canonical TaskEnv.

During a documentation-only request, write the proposal/limitation and stop before implementation
unless separately authorized. API/qualification-sensitive updates retain Human review; source change
alone is not proof that a Skill update is correct. Do not modify frozen Evidence, tags or Judge decisions.
