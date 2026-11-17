# GeoChora roadmap

## Current state

v2.1.1 is [published](../releases/v2.1.1/README.md) at `15f85f35`; all seven Goals / twenty-two substages have bounded acceptance. See the [remaining-work register](../releases/v2.1.1/remaining-work.md) before selecting v2.1.2 scope. v1.1.0 remains a historical published consolidation baseline. v2.0.0 is preserved as a frozen source tag. The v2.1.0 F/R integration and selected API closeout form the source baseline for v2.1.1; the locally verified v2.1.0 tag resolves to `fd03817c9f6ef8ce9fd68c1db30125efda68e1c8`. Its [scope](../module/task_env/v2.1.0/planning/current-scope.md) and [capability matrix](../module/task_env/v2.1.0/capabilities/capability-matrix.json) retain the original candidate context and exact bounded evidence. Remote refs and GitHub Release publication were not rechecked during this planning work.

## v2.1.1 agreed route

The maintainer confirmed [seven stages / twenty-two substages](../module/task_env/v2.1.1/planning/roadmap.md): Core/physics/render protocols first, a PickCube success reference, backend translation and reset rebuilding, common effort and Controller switching, native rendering with synchronized RGB, multiple parallel backends, then task reuse and final acceptance. The [execution table](../module/task_env/v2.1.1/planning/execution-and-acceptance.md) owns dependencies and gates.

The [v2.1.1 contracts](../module/task_env/v2.1.1/README.md) are maintainer-approved semantic baselines with bounded implementation evidence. Rendering, native CUDA batch and the final PickCube nine-cell matrix have been accepted at their recorded inputs; this is not arbitrary provider support or a rerun at the release HEAD.

## API migration within the agreed route

The v2.1.1 integration disposition is:

1. PickCube and NutAssembly public TaskDefinition migration is complete within the accepted routes.
2. LIBERO task1 has bounded shared-Core integration; other tasks, independent gripper control and full Solution execution remain uncompleted. Benchmark-specific source/task behavior stays under `bench_deploy/libero`.
3. Affected lightweight tasks and learner/vector boundaries were checked; coordinated CUDA learner training remains unsupported.

The current owners and boundaries are recorded in the [API handoff](../module/task_env/v2.1.0/maintenance/reviews/integration/20261102_v210_integration_baseline.md) and [follow-up plan](../module/task_env/v2.1.0/planning/v2.1.x-followups.md). This roadmap does not authorize a new provider abstraction, a parallel runtime, or broader migration without source/caller/test evidence.

## Deferred v2.1.x work

F06 PickCube Solution is now part of the agreed v2.1.1 route. R07 autonomous Solution expansion, Flora, full F07, asset-harness automation, non-rigid examples, RL/IL demos, agent_factory improvements and complete new-backend integrations remain later v2.1.x work. Strict DG03/source-equivalence research stays separately scoped. A runtime-valid episode is not task success. The F06 final shared R3 identity had 9/9 runtime-valid runs but 0/9 task successes; preserve that result and its source identity.

Longer-term benchmark, asset, policy, and learning harnesses must build on current Core owners. Documentation pages for these harnesses describe scope and status, not implemented products. New provider/backend combinations, renderers, simulator equivalence, and formal Qualification each need their own bounded evidence and maintainer decision.
