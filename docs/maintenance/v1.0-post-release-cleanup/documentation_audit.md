# Documentation audit

## Changes made

- `README.md` now opens with the v1.0 scoped Core baseline, names the bounded
  P1.0–P1.6 decisions, marks P1.7 deferred, and limits P1.8 to tested
  infrastructure plus separate development/diagnostic evidence. It links the
  release evidence index, follow-up plan, and Phase II roadmap.
- The capability description preserves P1.5's bounded PickCube expert result
  and P1.6's bounded PickCube V2a policy/D3 result. It does not generalize
  either result to all tasks, learners, providers, or randomized conditions.
- NutAssembly language distinguishes MuJoCo R5 G0 development evidence, the
  GeoPhys original Expert gate failure, shadow physical predicates, lifecycle
  validity, D0 reconstruction, D1 frozen native controls, and D2 frozen
  RequestedAction with live controller recomputation. It also distinguishes
  cross-provider trajectory differences from same-provider D2 drift.
- The root README clarifies that generated `workspace/` evidence is ignored by
  default while tracked P1.6 closure documents are governed legacy exceptions.
- `task_env/README.md` removes the invalid editable-install instruction,
  documents submodule initialization, requirements files, and `PYTHONPATH`.
  No package metadata was added.
- `task_env/tasks/nut_assembly/README.md` appends a v1.0 status section and
  preserves the existing R5 section verbatim.
- Root `AGENTS.md` adds a short contributor workflow pointing to canonical
  contracts, release scope, and the five tracked repository skills.

The root public API quickstart and the TaskEnv CPU single-environment CLI
quickstart both passed a three-step Pendulum smoke in the `geochora` Python
environment. The documented PPO and trajectory collection CLI options appear
in their respective `--help` output; no training or trajectory data was
generated.

## Evidence basis

The status statements above follow the v1.0 release crosswalk, evidence index,
known limitations, and the tracked P1.8 final diagnostic report. In
particular:

- GeoPhys FULL attempts at 50/100/500 Hz preserve the original
  `stable_height_mismatch` Expert gate failure.
- Raw insertion/release/task-success predicates after shadow continuation are
  not lifecycle-valid task success or canonical Expert completion.
- GeoPhys-source D1 and frozen-action D2 executions are diagnostic. D0 was
  partial/invalid at 50 Hz and was not run at 100/500 Hz.
- P1.8 Human review and formal NutAssembly/cross-provider qualification remain
  pending.

## Context availability

The file `docs/Geochora Project Context.md` was absent, and no open Library
document session was available. This is recorded as a missing context source;
the audit does not substitute an inferred context page.
