---
name: geochora-architecture-refactor
description: "Audit or implement Geochora ownership and lifecycle refactors when Core modules, provider boundaries, state ownership, or orchestration edges change; do not use for ordinary cleanup that preserves ownership."
---

# Geochora Architecture Refactor

Use this skill when a change may move ownership, split or consolidate a
module, alter lifecycle state, change dependency direction, or add an adapter
boundary. The goal is a smaller and clearer ownership graph with preserved
public behavior and evidence-backed capability claims.

## Authority

Start from the current branch, dirty state, real production callers, runtime
and provider provenance, and the canonical Geochora documents:

- `docs/global/00-system-architecture-anchor.md`
- `docs/global/01-repository-ownership-and-boundaries.md`
- `docs/module/task_env/02-core-api-and-capability-scope.md`
- `docs/module/task_env/04-core-qualification-and-governance.md`

Use CodeGraph when its index is current to trace symbols and call paths. A
filename or line count is not evidence of an ownership seam.

## Invariants

1. One owner must hold mutable state, lifecycle transitions, queues, caches,
   workers, resources, and teardown. A facade may re-export but must not mirror
   process state.
2. Trace construction, steady-state execution, failure paths, teardown,
   recording/replay, and provider calls before moving an owner.
3. Keep `task_env` as the canonical Core owner. Core uses GeoPhys through its
   public/runtime-facing boundary and never through private solver or renderer
   internals.
4. Do not introduce a manager, service, protocol, or wrapper only to shorten a
   file. Add an abstraction only when it has independent ownership, lifecycle,
   substitution, or a stable value contract.
5. Preserve signatures, defaults, ordering, result schemas, synchronization,
   resource lifetime, and exactly-once teardown unless the user explicitly
   requests a behavior change.
6. Keep support claims limited to the verified provider × capability ×
   backend/runtime × representation intersection.
7. `accepted-deferred` is a valid result when no safe seam can be proved.

## Workflow

1. Record HEAD, branch, dirty paths, current owner, consumers, and user scope.
2. Map the state and call graph, including provider boundary, data movement,
   readback/upload, failure, and teardown paths.
3. Write a boundary table with current owner, state written, lifecycle,
   synchronization, public exposure, tests, and proposed disposition.
4. Choose `EXTRACT`, `CONSOLIDATE`, `KEEP COHESIVE`, or
   `ACCEPTED-DEFERRED`; identify the receiving owner before editing.
5. Implement one ownership change at a time and remove obsolete forwarding or
   duplicate state in the same change.
6. Run the smallest defect-sensitive API, golden-path, and provider checks
   required by the affected boundary. Do not turn a refactor into an unrelated
   physics or performance campaign.
7. Hand off completed and deferred boundaries, exact checks, and unsupported
   envelopes. Use `geochora-public-api-governance` or
   `geochora-test-governance` when their triggers apply.
