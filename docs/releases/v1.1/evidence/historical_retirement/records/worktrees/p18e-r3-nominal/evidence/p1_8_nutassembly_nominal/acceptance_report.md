# P1.8-E-R3 Nominal NutAssembly Acceptance Report

## P1.8-E-R3 status: PARTIAL / NOT APPROVED

Phase A stopped at its first failing mandatory expert cell, GeoPhys / NA-TB500. The failure boundary is `closed_loop_expert/lower_nut_to_table`; the observed failure was `lower_nut_to_table_readiness_timeout`. Per the gated order, no other NutAssembly expert or replay cells were run and Phase B was not entered. This is not a successful nominal NutAssembly qualification.

## Provenance and frozen nominal profile

- Qualification branch/base: `codex/p1.8-e-r3-nutassembly-nominal` / `6160ba0a8b494f0cc3989d464b5ef61d83219b10`; working tracked tree was clean at lock and remains clean.
- Human follow-up source lock `eb533e675c0f05e0a85f9e52e2d011c5237ad306cec65ef4af87aacb027b4585` is bound to the preserved R2 worktree inventory and reports. Its normalized 0.1 kg source overlay is byte-identical to the reconstructed profile source after only absolute Panda meshdir normalization.
- Nominal spec lock: SHA256 `e765fcfb4dcba0325d9936b2775d2f8b3ee56cfb481740461beb7e5c2b80fa30`; created before any native provider session. All 52 locked source hashes still match after execution.
- Nut mass/inertia: 0.1 kg / `[7.5e-05, 7.5e-05, 0.000125]` kg·m². The exact asset, collision, friction, Panda, gripper, controller, solution, timebase, and reset definitions are retained in `nominal_spec.yaml`.
- Controller target/deadband: 30 N / 1 N, unchanged. The 25 N value is only the solution fallback. Stable fallback: 0.1 s, opening span ≤0.5 mm, grasped throughout; computed tick counts are 50/10/5 for TB500/TB100/TB50. `verify_lift` is mandatory.
- GeoPhys gitlink/checkout: `c665ce5028a12bb4d2afe49f05e015fa9b684a39` / `c665ce5028a12bb4d2afe49f05e015fa9b684a39`, clean. MuJoCo 3.8.1. SAPIEN and Genesis were absent in the environment; no installation attempted. These absences did not cause the Phase-A stop.

## Declared goal and implemented qualification substrate

The frozen nominal profile and additive rate-specific TaskArtifact identities were prepared for TB500, TB100, and TB50 under the unchanged NA-S0 reset. The qualification harness performs A0, then the ordered expert gate; it does not bypass verify_lift, alter task semantics, or proceed to D0/D1/D2 until all six expert source runs pass.

## A0 reset/source/timebase precheck

All six primary provider × rate prechecks passed: GeoPhys and MuJoCo at 500, 100, and 50 Hz. They verified the same physical reset request and source geometry, requested zero settle, finite canonical state, time alignment, native substep count, repeat reset, and ZOH target identity. Details are under `phase_a/precheck/`.

## A1 full closed-loop expert

Only GeoPhys / TB500 was attempted. The run closed the gripper under `controller_close_ready` at 4.368 s, maintained the frozen force/opening/grasp conditions, and passed mandatory verify_lift: 0.100256 m Nut lift and `lifted_nut=true`. It reached hover at 15.374 s. The first failed stage was lowering the Nut to the table: readiness timed out at 28.740 s with peg Z error 0.080915 m, while XY error was 0.001092 m and yaw error 0.009261 rad. The Nut remained grasped; insertion/release/task success were false. This evidence names the failed stage and measured state but does not infer the underlying cause.

Expert count: 0/6 full-task PASS; 1 attempted and failed, 5 not run. The exact trace, contacts, native audit, H5, stdout/stderr, and command are retained under `phase_a/expert/tb500/geophys/`.

## CanonicalTrajectory, D0, D1, and D2

No successful NutAssembly trajectory exists in this acceptance run. Therefore no NutAssembly goldens were frozen, no primary acceptance lock was created, and NutAssembly D0 (0/6), D1 (0/12), and D2 (0/12) were not run. The placeholders under `phase_a/{golden,d0,d1,d2}` explicitly record this gated disposition.

## Independent regressions

PickCube D0 was rerun from the unchanged seed31/seed73 goldens: 716/716 and 445/445 exact target reconstruction. GeoPhys and MuJoCo D1 and D2 spot checks passed for both seeds (8/8 task-valid cells). Existing goldens/action sequences were reused; no PickCube goldens were regenerated. D2 recomputes targets online, so its stored-target exact-match count is diagnostic, not the D2 pass criterion.

CanonicalTrajectory strict H5 load-save-load passed on the preserved unsuccessful NutAssembly run: 14,370 transitions, 14,371 boundaries, exact logical mapping and identity retained. P1.1 contract diagnostic passed all 30 checks. The P1.2 detector initially stopped at provenance because the clean R3 worktree did not carry its local decision file. The original P1.1 and P1.2 Human decisions were then found in the approved P1.3 worktree, SHA-verified against the user-directory workspace, copied unchanged into this worktree Evidence, and P1.2 rerun: provider-free guard, GeoPhys, MuJoCo, same-input/source checks, negative admission, and close lifecycle all passed. The first provenance stop remains preserved under `regression/p1_2_initial_block/`.

## Flow / learner, P1.7, and P1.8 roadmap

No Flow learner, policy training, D3, P1.7, or learner tuning was run. P1.6 remains PARTIAL / NOT APPROVED; P1.7 remains deferred. This nominal task acceptance does not waive either phase and does not close Phase I.

## Failed / unqualified intersections and Phase B

Primary nominal qualification: **NOT APPROVED**. Five primary expert cells and all NutAssembly D0/D1/D2 cells are untested because the first mandatory expert cell failed. Phase B (SAPIEN / Genesis, all rates/routes) is **NOT RUN** because Phase A did not pass; no Phase-B qualification claim is made.

## Heavy-load profile

The separate 1.0 kg stress profile and all prior evidence remain unchanged. Its historical GeoPhys/MuJoCo results are stress diagnostics only and are not nominal hard gates.

## Evidence

- Nominal spec/lock: `nominal_spec.yaml`, `nominal_spec_lock.json`.
- Source/provenance: `provenance/source_freeze.json`, `provenance/prior_followup_reference.json`, `provenance/heavy_load_stress_reference.json`, `provenance/qualification_snapshot.json`.
- Phase-A matrix and first failure: `phase_a/replay_matrix.md`, `phase_a/expert/tb500/geophys/`.
- Precision/timing: `precision_report.md`, `timing_report.md`.
- Regression records: `regression/pickcube/`, `regression/canonical_trajectory_roundtrip.json`, `regression/p1_1/report.json`, `regression/p1_2/report.json`.
- Machine acceptance and indexed file hashes: `acceptance.json`, `evidence_index.json`.
