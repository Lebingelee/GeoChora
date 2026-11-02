# v2.1.0 capability status

The [capability matrix](capability-matrix.json) is the single current table for bounded TaskEnv evidence. Rows identify task, source, provider, backend/runtime, controller or control representation, evidence Core/provider heads, result, and limits.

## Status meanings

- `IMPLEMENTED`: current code owner has the behavior; this is not runtime evidence.
- `TESTED_BOUNDED`: the listed exact intersection passed its stated check.
- `PARTIAL`: some required behavior or route passed while a named gate remains open.
- `NOT_RUN`: no current evidence is claimed for that intersection.
- `DEFERRED`: explicitly moved to a later scope.
- `PASS_REUSED_BOUNDED_EVIDENCE`: evidence was accepted for a historical provider/head and reused only within its stated unchanged boundary; it is not a run on provider P.

Runtime validity, physical task predicate, lifecycle-valid task success, Expert completion, replay validity, and formal Qualification are separate outcomes. The F06 source-bound 3×3 matrix is 9/9 runtime-valid and 0/9 task-success; its solution effectiveness remains open. All six A123 replay episodes ended `external_stop` with `task_success=false`. The accepted task2 GeoPhys contact exception and task3 MuJoCo monitor tolerance stay limited to their frozen profiles.

The integration's required GeoPhys GP01–GP08 checks are summarized in the versioned [integration review](../maintenance/reviews/integration/20261102_v210_integration_baseline.md); the raw per-run ledger and files are local ignored evidence, not part of the source package. GP07 reused historical R04 evidence and is not a current-P native renderer test. Task1 fluid-parameter projection impact remains `NOT_MEASURED`.
