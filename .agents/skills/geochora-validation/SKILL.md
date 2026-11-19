---
name: geochora-validation
description: Use GeoChora's independent validation module for source-bound numeric measurements and terminal review of existing experiment evidence; locate its adapters, contracts and offline tests.
---

# Independent Validation Module

Read [AGENTS](../../../AGENTS.md), the [module entry](../../../validation/README.md) and
[validation contract](../../../docs/module/validation/contracts.md). The root `validation/`
owns offline validation. TaskEnv owns task construction, runtime, recording/replay and
lifecycle predicates. Complete trajectory validation remains future work.

## Route the request

- Task records: use [`inputs.validate_task`, `load_task` and `load_task_source`](../../../validation/inputs.py).
  The [pinned schemas](../../../validation/schemas/README.md) cover `low-detail-task/1.1.0` and
  `low-detail-task/1.2.0`;
  reject unknown versions explicitly and preserve original requirements. The lower-level source
  review protocol accepts arbitrary source JSON and does not replace this task-contract check.
  Follow the [external input example](../../../examples/validation/README.md) for real run evidence.
- Existing normalized world/m/s/WXYZ poses: use
  [`recorded.read_recorded_poses` or `adapt_recorded_poses`](../../../validation/adapters/recorded.py).
  Supply explicit source-byte identities and independent completion facts. Missing observations stay missing.
- Existing public native records: use [`physpi`](../../../validation/adapters/physpi.py),
  [`contacts`](../../../validation/adapters/contacts.py) and
  [`assets`](../../../validation/adapters/assets.py). Native queries require an explicitly selected
  runtime executable; parsing existing recorded evidence requires neither TaskEnv nor a physics runtime.
- Explicit numeric conditions: use [`numeric.measure_source_requests`](../../../validation/terminal/numeric.py).
  Preserve the 16 method contracts, source pointers, units, reference bindings and sample grids.
  Source pointers establish provenance; the original-task review checks method/threshold meaning.
- Original requirements: use [`reviews.prepare_source_review`](../../../validation/terminal/reviews.py),
  then [`source_run.prepare_source_run` and `execute_source_run`](../../../validation/terminal/source_run.py).
  Default `full` differs from explicit `adaptive`, which permits at most one requested evidence expansion.
  A boolean candidate is released only after independent confirmation; valid unknown normally stops.
  Execution errors remain errors. Use the caller's file host, actual image bytes, budgets and distinct contexts.

Generic validation consumes explicit data and imports no TaskEnv runtime. Keep task-specific source
requirements in the Task Artifact; adapt inputs rather than adding per-task reviewers or another recorder.
The [TableCraft deployment](../../../bench_deploy/tablecraft/README.md) owns its original task requirements
and calls validation explicitly; it is a benchmark consumer, not a TaskEnv built-in environment.
Use [tests](../../../validation/tests/README.md) to select numeric/protocol/adapter counterexamples.
The standalone independence test runs recorded measurement and paired review with runtime imports blocked.

## Evidence identity

Preserve original evidence bytes, hashes, clocks and producer identities. New outputs identify the new
source paths and actual hashes; existing run plans still bind their original source implementation.
Endpoint catalogue roundoff uses the existing clock comparison tolerance; preserve raw observation clocks
and reject genuinely future ranges. The adaptive tests protect both cases.
The [2026-11-15 native evidence](../../../docs/module/task_env/v2.1.0/maintenance/reviews/terminal-validation-20261115.md)
remains historical and bounded. Offline synthetic checks are not native accuracy or formal Qualification.
Old specification/multi-route/benchmark experiments stay in the ignored workspace frozen archive;
current validation never imports it. Reuse the existing [TaskEnv Experiment/Evidence Skill](../../../task_env/.agents/skills/task-env-experiment-evidence/SKILL.md)
when the caller specifically needs that packaging contract.
