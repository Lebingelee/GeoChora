# GeoChora roadmap

## Current state

v1.1.0 is the published consolidation baseline. v2.0.0 is preserved as a frozen source tag. The v2.1.0 F/R integration and selected API closeout form the source baseline for v2.1.1; the locally verified v2.1.0 tag resolves to `fd03817c9f6ef8ce9fd68c1db30125efda68e1c8`. Its [scope](../module/task_env/v2.1.0/planning/current-scope.md) and [capability matrix](../module/task_env/v2.1.0/capabilities/capability-matrix.json) retain the original candidate context and exact bounded evidence. Remote refs and GitHub Release publication were not rechecked during this planning work.

## v2.1.1 agreed route

The maintainer confirmed [seven stages / twenty-two substages](../module/task_env/v2.1.1/planning/roadmap.md): Core/physics/render protocols first, a PickCube success reference, backend translation and reset rebuilding, common effort and Controller switching, native rendering with synchronized RGB, multiple parallel backends, then task reuse and final acceptance. The [execution table](../module/task_env/v2.1.1/planning/execution-and-acceptance.md) owns dependencies and gates.

The [v2.1.1 contracts](../module/task_env/v2.1.1/README.md) are discussion drafts. Creating these documents starts no implementation Goal or native execution. Selected rendering remains state-only in the source baseline until its real implementation and evidence exist.

## API migration within the agreed route

The approved follow-on API scope is:

1. Complete public TaskDefinition migration for PickCube and NutAssembly.
2. Reuse shared Core construction for LIBERO while keeping benchmark-specific task/source/action behavior under `bench_deploy/libero`.
3. Compatibility-check other lightweight tasks against the settled public contract.

The current owners and boundaries are recorded in the [API handoff](../module/task_env/v2.1.0/maintenance/reviews/integration/20261102_v210_integration_baseline.md) and [follow-up plan](../module/task_env/v2.1.0/planning/v2.1.x-followups.md). This roadmap does not authorize a new provider abstraction, a parallel runtime, or broader migration without source/caller/test evidence.

## Deferred v2.1.x work

F06 PickCube Solution is now part of the agreed v2.1.1 route. R07 autonomous Solution expansion, Flora, full F07, asset-harness automation, non-rigid examples, RL/IL demos, agent_factory improvements and complete new-backend integrations remain later v2.1.x work. Strict DG03/source-equivalence research stays separately scoped. A runtime-valid episode is not task success. The F06 final shared R3 identity had 9/9 runtime-valid runs but 0/9 task successes; preserve that result and its source identity.

Longer-term benchmark, asset, policy, and learning harnesses must build on current Core owners. Documentation pages for these harnesses describe scope and status, not implemented products. New provider/backend combinations, renderers, simulator equivalence, and formal Qualification each need their own bounded evidence and maintainer decision.
