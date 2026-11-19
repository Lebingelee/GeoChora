# TaskEnv route and owner map

Use the [v2.1.1 current state](../../../../docs/module/task_env/v2.1.1/maintenance/current-state.md), [API](../../../../docs/module/task_env/v2.1.1/api/README.md), and [capability matrix](../../../../docs/module/task_env/v2.1.1/capabilities/capability-matrix.json) for current behavior and evidence. Earlier v2.1.0 and pre-stage3 references describe their own historical inputs; they do not define the current route.

## Public construction and lifecycle

- `task_env/__init__.py` and `task_env/registry.py` expose `make_env`. The four formal UIDs resolve mapping/YAML through `task_env/environment/configuration.py`, then a `TaskBuildRequest` and `SourceBoundTaskBuilder`. Legacy component paths retain their separately supported scope.
- PickCube and NutAssembly each own task semantics and Solution under `task_env/tasks/`; Pendulum and TwoWheel provide their own Robot/task declarations. Source compilation, Controller binding and provider materialization remain with their respective owners.
- `task_env/environment/reference_env.py` owns the selected lifecycle and coordinates `task_env/runtime/sessions/control_lifecycle.py` and `task_env/runtime/sessions/control_submission.py`. Position, effort and wrench keep distinct physical semantics; provider adapters own native mapping and session/App resources.
- Opted-in Pendulum and TwoWheel direct-effort feedback is an acknowledged generalized-effort command projection, not motor-control readback or a force measurement; preserve the [bounded feedback semantics](../../../../docs/module/task_env/v2.1.1/maintenance/20261108_direct_effort_feedback.md).
- External Solutions use `act → env.step(action) → observe`; `step_expert` and `step_with_solution` are limited compatibility routes. Nut actions remain source-bound and are not arbitrary arrays. The [U3 results](../../../../docs/module/task_env/v2.1.1/maintenance/reviews/20261113_e11_e16_u3_solution_evidence.md) distinguish task success, Solution completion, readback and close. Isaac CUDA runtime was valid but its task and Solution failed; its v3 H5 completion field is absent.
- `task_env/recorders/reference_provenance.py`, `task_env/recorders/position_metadata.py` and `task_env/recorders/h5.py` own provenance and current record formats; `task_env/trajectory/reference_replay.py` separates read-only inspection from source-checked re-execution. The versioned diagnostics distinguish legacy codec and strict historical Judge.
- `task_env/runtime/sessions/isaac_usd_admission.py` owns the precise F06 USD admission; provider-specific source and control restrictions remain in their adapters. The old Position candidate builder and its admission file are retired; do not recreate them to satisfy old diagnostics.
- `task_env/observations/selected_reference.py` consumes Robot and Task observation declarations. Task RGB uses renderer capability and the published typed boundary; borrowed and renderer-only sources retain distinct resource ownership. The renderer is fixed until close.
- LIBERO remains under `bench_deploy/libero/`; preserve its original source, task, OSC, gripper cadence and reader semantics rather than promoting it to a generic Core UID.

## Independent validation

For offline terminal measurements, original-task review and independent verification,
use the [validation module Skill](../../geochora-validation/SKILL.md) and
[contract](../../../../docs/module/validation/contracts.md). TableCraft owns its original
requirements in `bench_deploy/tablecraft/` and calls validation from `evaluation.py`
and `cli.py`. TaskEnv owns runtime, recording and replay.

## Current examples and checks

- Ordinary scalar construction and recording: `examples/README.md`, `examples/tasks/pick_cube.py`, `examples/tasks/nut_assembly.py`, and `examples/recording/record_expert.py`. Isaac requires the selected interpreter and installed delivery; the advanced Harness has separate manifest requirements.
- The exact pure/fake and offline entry points are in `task_env/diagnostics/tasks/v2.1.1/README.md`. The guard excludes declared SDK/asset paths but is not an OS sandbox. Native, GPU/App and window runs require their own frozen plan and shared locks.
- Formal batch adapters for the four current task UIDs are not implemented and reject before resource allocation. Existing component batch paths remain within their original scope; G06 and G07 are not complete.
- Current versioned API, installation and examples live in `docs/module/task_env/v2.1.1/api/`, `docs/module/task_env/v2.1.1/guides/`, and `task_env/doc/api/`.

Historical COM strict FAIL/bounded acceptance, original N08 FAIL, R05c NOT_REQUALIFIED, F06 and LIBERO A123 task-result limitations, SDK shutdown-log limitations, and the three-provider-by-three-seed final gate remain unchanged. Do not infer arbitrary provider/source/renderer support or Qualification from a single accepted route.
