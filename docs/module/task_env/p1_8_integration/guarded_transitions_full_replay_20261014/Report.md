# P1.8 Guarded Transitions and FULL Replay Development Report

**Status: candidate-scoped MuJoCo development evidence; not formal qualification.**

The P1.8 task-local Canonical Solution now separates task success from the
Expert terminal sequence, records close-transition evidence on the native
physics clock, and preserves distinct primary and alternative authorization
branches. The current NoSlip2 candidate completes NutAssembly FULL at all four
supported outer control rates and passes same-provider D0/D1/D2 replay. These
results do not establish the historical primary-only 9 N gate at every rate,
sub-millimeter grasp drift, GeoPhys FULL competence, or formal P1.8 acceptance.

## Scope and preserved configuration

The source implementation audited here is commit
`ac38e1e16340fcf8416f3a540a0280e30e6f78bc` on
`codex/p1.8-frequency-robust-grasp`, based on the public mainline commit
`9988cf700ac1b5f7ae9ba0a284deda4fa2141917`.

The FULL candidate is
`nutassembly-r5-v5-clearance-primary-readiness-alternative-8n-guarded-v2`.
It uses MuJoCo with `physics_dt=0.002 s`, NoSlip2, R3 arm control and gains,
native-step arm ramping, fixed 500 Hz gripper feedback, and a 10 N gripper
force target and cap. Its task-local path uses a 24 mm outboard handle grasp
and a shared 0.1605 mm downward descent command correction. Collision geometry,
solver settings, capture bounds, task success semantics, stage readiness,
action budget, and deadlines remain unchanged.

The primary `controller_close_ready` predicate remains the historical R3 route.
With the current 10 N limit and 1 N force deadband, it requires measured force
at least 9 N continuously for 100 ms. A separately identified, opt-in
`alternative_force_8n` guard requires measured force at least 8 N plus active
and initialized force mode, a grasped Nut, and a ready EE pose for the same
100 ms dwell. This alternative changes Solution authorization only; it does
not change R3 force regulation or retroactively satisfy the primary-only
contract. See the [guarded-transition contract](../../canonical-solution-guarded-transitions.md)
and [lifecycle contract](../../canonical-solution-lifecycle-contract.md).

## Nominal FULL matrix

All four cells used the same serialized physical reset-state fingerprint and
the alternative guard. Each completed the eleven Expert stages, reached task
success, released the Nut, passed the original capture and endpoint gates, and
completed approximately 100.5 mm of vertical retreat. Native contact scans
found no Hand/Peg contacts in these nominal episodes.

| Outer rate | FULL | Authorization branch (measured N) | Max Nut/EE translation drift | Max rotation drift | Task success / Expert completion | Retreat endpoint error |
|---:|---|---|---:|---:|---:|---:|
| 20 Hz | PASS | alternative 8 N (9.050) | 1.663 mm | 0.009154 rad | 20.200 / 23.800 s | 0.813 mm / 0.000201 rad |
| 50 Hz | PASS | alternative 8 N (9.018) | 1.733 mm | 0.008643 rad | 20.120 / 23.760 s | 0.892 mm / 0.000144 rad |
| 100 Hz | PASS | alternative 8 N (9.001) | 1.760 mm | 0.008891 rad | 20.090 / 23.730 s | 0.915 mm / 0.000126 rad |
| 500 Hz | PASS | alternative 8 N (9.017) | 1.757 mm | 0.008755 rad | 20.088 / 23.736 s | 0.895 mm / 0.000112 rad |

The separate 0.5 mm drift research target is not met. The maximum nominal
translation drift is 1.760 mm.

Two predefined held-out Nut pose perturbations also completed FULL at 20, 50,
100, and 500 Hz (eight of eight cells). Their maximum translation drift was
2.074 mm. One cell, `offset_a` at 20 Hz, recorded a brief 39-sample
knuckle/peg contact during lowering, peaking at 0.197 N; it cleared before
retreat and passed the original retreat gate. This is limited held-out
coverage, not all-reset robustness.

## Primary 9 N dwell and continuation diagnostic

A common evaluator audit of the four nominal and eight held-out traces found
that only held-out `offset_b` at 100 and 500 Hz met the primary 100 ms dwell.
The nominal primary-ready continuous windows were 26, 26, 32, and 32 ms at
20/50/100/500 Hz. In a fresh 500 Hz primary-only run with the 8 N alternative
disabled, Nut grasp, EE pose, force-mode active/initialized, and the 8 N force
condition were all true for all 333 post-close native samples. The 9 N primary
readiness bit was true for 317 samples; measured force ranged from 8.99682 to
9.05759 N, with a 54 ms maximum continuous run and a 30 ms run at the original
1.5 s deadline. The underlying reason the realized contact force settles near
9 N instead of 10 N is not isolated.

The explicitly diagnostic runner continued after the primary authorization
expired. It was a fresh FULL execution, not trajectory replay. The robot
entered all eleven stages, reached task success, inserted and released the
Nut, completed the terminal retreat, and emitted
`expert_sequence_completed` at 24.318 s. Maximum Nut/EE drift was 1.994 mm
and 0.015985 rad; Nut lift was 191.1 mm; retreat displacement was 100.496 mm
vertically with a 0.895 mm / 0.000112 rad endpoint error. No Hand/Peg contacts
were recorded.

This is physical completion after bypassing the failed authorization, **not**
a FULL pass: `close_authorization_gate_pass=false`, `close_sequence_pass=false`,
and the runner status is `FULL_EXPERT_FAILED`. The diagnostic preserves rather
than relaxes the historical primary gate. An earlier 9 N-labeled attempt had
the alternative guard enabled and selected it early; it is excluded from the
primary-only conclusion.

## Candidate-scoped D0/D1/D2 and regression

| Replay | 20 Hz | 50 Hz | 100 Hz | 500 Hz |
|---|---|---|---|---|
| D0: full Canonical Solution/controller owner reconstruction | PASS | PASS | PASS | PASS |
| D1: ordered native applied-control replay | PASS | PASS | PASS | PASS |
| D2: fresh live controller/coordinator execution | PASS | PASS | PASS | PASS |

The tested FULL sources had no first divergence. D0 matched all expected
transitions and T+1 boundaries, D1 matched the native target stream and task
state, and D2 produced exact H5 SHA-256 and logical-hash matches at every rate.
These are same-provider, same-candidate development results only.

Current-HEAD tests: **60 passed** across guarded transitions, lifecycle,
streaming recording, native math, and offline event windows. The bounded
MuJoCo PickCube regressions for seeds 31 and 73 also passed in the preserved
regression run at this same source HEAD.

The primary-only 500 Hz continuation episode wrote 12,159 transitions and
12,160 boundaries. Its H5 roundtrip was byte-exact (899,456,779 logical bytes;
189,516,102 physical bytes). Full validation/replay remains memory-intensive;
peak RSS in the run was about 3.7 GiB. The [Recorder I/O optimization report](../recording_io_optimization_20261014/Report.md)
describes the bounded streaming changes and their limits. A later read-only
semantic audit of the archived 11,868-transition source used about 116 MiB RSS;
see the [follow-up audit report](../recording_io_followup_20261014/Report.md).

## Evidence and acceptance boundary

Machine-readable summary and source hashes are in [results.json](results.json).
Raw H5, native streams, contact sidecars, and detailed per-boundary traces
remain in the local development Evidence tree at
`workspace/qualification/phase1/p1_8_guarded_transitions_20261014/`; they are
not committed to Git. The local Evidence SHA-256 manifest covers those files.

The alternative-authorization candidate has development FULL and replay passes.
The strict primary-only 9 N route has not passed the nominal 500 Hz dwell, and
primary-only 20/50/100 Hz FULL cells remain unrun. Formal D0/D1/D2 remains
blocked pending Human Review, eligible full-task source-golden status, and
symmetric GeoPhys FULL evidence. The current candidate is not a production
default and does not establish formal cross-provider qualification.
