# GeoChora roadmap

## Current state

v1.1.0 is the published release. v2.0.0 is preserved as a frozen source tag, with no publication or acceptance date added here. The v2.1.0 F/R integration and selected TaskEnv API closeout are recorded as a **local draft candidate**, not a published release or a general capability expansion. Follow the [v2.1.0 scope](../module/task_env/v2.1.0/planning/current-scope.md) and [capability matrix](../module/task_env/v2.1.0/capabilities/capability-matrix.json) for exact evidence.

## Next API work

The approved follow-on API scope is:

1. Complete public TaskDefinition migration for PickCube and NutAssembly.
2. Reuse shared Core construction for LIBERO while keeping benchmark-specific task/source/action behavior under `bench_deploy/libero`.
3. Compatibility-check other lightweight tasks against the settled public contract.

The current owners and boundaries are recorded in the [API handoff](../module/task_env/v2.1.0/maintenance/reviews/integration/20261102_v210_integration_baseline.md) and [follow-up plan](../module/task_env/v2.1.0/planning/v2.1.x-followups.md). This roadmap does not authorize a new provider abstraction, a parallel runtime, or broader migration without source/caller/test evidence.

## Deferred v2.1.x work

R07/F06 solution behavior review and optimization, F07, and unresolved strict DG03/source-actuation work remain separate follow-ups. A runtime-valid episode is not task success. The F06 final shared R3 identity had 9/9 runtime-valid runs but 0/9 task successes; preserve that result and its source identity.

Longer-term benchmark, asset, policy, and learning harnesses must build on current Core owners. Documentation pages for these harnesses describe scope and status, not implemented products. New provider/backend combinations, renderers, simulator equivalence, and formal Qualification each need their own bounded evidence and maintainer decision.
