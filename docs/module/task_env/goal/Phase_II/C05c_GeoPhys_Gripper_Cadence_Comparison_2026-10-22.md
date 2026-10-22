# C05c GeoPhys NutAssembly Gripper Cadence Comparison

**Date:** 2026-10-22
**Result:** all four specified GeoPhys S2/S3 diagnostic cells passed. This is a bounded experiment, not a general Provider capability or Qualification.

## Scope and fixed identities

The experiment uses the task-owned NutAssembly external Solution and existing R3 Controller/Guard/Outcome route. Each group ran in its own process against GeoPhys `a53a8cfed7c9d6464274b5c96fca601271dc4ee4`; no GeoPhys source or parent gitlink was changed. The fixed task identity is `nut-assembly-square-v1/p1_8_e/nominal-v1`, TaskArtifact hash `99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe`, source `nut-assembly-square-v1/canonical-source-nutassembly-nominal-v1`, and source XML SHA-256 `909759def6bbaa4c5644a100a36625400464cd571dcab1222f807efaaf1c225d`. Every group used seed 19 and the same NA-S0 ResetSample `reset-767d56397dec41243aec445232d8d726b0891e7eeb49f655b789a86b23b5f4a2`.

The configuration held R3, the existing action trajectory, 10 N force target/cap, 8 N / 0.1 s Guard policy, 50 consecutive native Guard samples, 100 Hz outer control, 2 ms physics dt, five native steps per interval, arm hold/ramp, Outcome, horizon and strict/warning behavior constant. Only GeoPhys backend and gripper-law cadence varied. Runtime configuration comparison found no difference beyond `runtime.backend` for CUDA. The 100/500 Hz cadence is represented by the task-owned Controller identity/configuration, not by mutating the frozen TaskArtifact or source.

The already accepted MuJoCo CPU external Expert is the reference: seed 19, 2,377 transitions, 2,378 boundaries, 11,885 native samples, task/Outcome/strict Expert completion and real close Guard authorization. It was not rerun for this comparison, and cross-Provider force values are not expected to match.

## Minimal native Probe and full-route results

Each final group first recorded two complete external Solution intervals, then reset to the same ResetSample, recorded the full external Expert once, finalized the existing execution Recorder, and read that same H5 with the existing reader. Every persisted 2 ms force sample passed validity, signed-N value, phase, native index/sequence/time, reset/evaluation-boundary identity, canonical `max(0, -signed_force)` conversion, target/applied-ack identity and clock checks. Probe update counts were exactly 2/8 for 100 Hz and 10/0 for 500 Hz (updates/holds).

| GeoPhys backend | Gripper law | S2 transitions / boundaries | Native samples | Updates / holds | First task success | Task / Outcome / strict Expert | Guard authorization |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| CPU (`x64`) | 100 Hz | 2,443 / 2,444 | 12,215 | 2,443 / 9,772 | step 2,078 (20.78 s) | pass / pass / pass; no warnings | 5.17 s; consumed 5.18 s; 50 samples; closing force 9.7561 N; raw −9.7561 N |
| CPU (`x64`) | 500 Hz | 2,442 / 2,443 | 12,210 | 12,210 / 0 | step 2,078 (20.78 s) | pass / pass / pass; no warnings | 5.17 s; consumed 5.18 s; 50 samples; closing force 10.0000 N; raw −10.0000 N |
| CUDA (`cuda`) | 100 Hz | 2,443 / 2,444 | 12,215 | 2,443 / 9,772 | step 2,078 (20.78 s) | pass / pass / pass; no warnings | 5.17 s; consumed 5.18 s; 50 samples; closing force 9.7588 N; raw −9.7588 N |
| CUDA (`cuda`) | 500 Hz | 2,442 / 2,443 | 12,210 | 12,210 / 0 | step 2,078 (20.78 s) | pass / pass / pass; no warnings | 5.17 s; consumed 5.18 s; 50 samples; closing force 10.0000 N; raw −10.0000 N |

All four Solutions completed the 11 planned stages and original strict Expert assessment with `expert_complete=true`, `expert_failed=false`; each reported task success and Outcome completion, with no readiness warnings, runtime fault, termination or truncation. Their complete simulated times were 24.42–24.43 s. The one or two transition difference between cadence groups is the measured execution result; no seed, trajectory, tolerance, threshold, contact, or solver setting was changed.

The common Guard identity is `primary_controller_close_ready` under policy identity `065af38f034f896d3003d8f63cfb2ea9acac3adcefe078b678bd7596d57a0674`. Each H5 contains all 50 consecutive close-stage force samples, reports 0.1 s observed stable dwell, shows force mode active/initialized, grasped nut and pose readiness, and records authorization at 5.17 s before consumption at the 5.18 s outer boundary. Hold/ramp rows were read from disk and checked against their actual applied arm acknowledgements. Each route contains 518 `track` intervals, 10 `hold_last_applied` intervals and 1,914–1,915 `ramp_from_last_applied` intervals.

## Wall-clock and readback cost

The initial Probe interval includes backend initialization/JIT; the second is the measured steady candidate interval. The Reader timer includes the public host snapshot copy/synchronization. CUDA native-step timing is mainly device submission and may be asynchronous, so the counters below must not be added as if they were disjoint.

| Group | First Probe interval | Second Probe interval | Full Expert loop | Full route + Recorder + H5 readback | Reader calls; mean / total |
| --- | ---: | ---: | ---: | ---: | ---: |
| CPU 100 Hz | 36.95 s | 0.049 s | 250.23 s | Not captured by the first runner after its S3 checker assertion; the standalone same-file readback took 10.30 s | 14,658; 0.294 ms / 4.303 s |
| CPU 500 Hz | 36.94 s | 0.056 s | 249.05 s | 318.10 s | 14,652; 0.294 ms / 4.308 s |
| CUDA 100 Hz | 39.94 s | 0.038 s | 165.38 s | 239.88 s | 14,658; 0.304 ms / 4.461 s |
| CUDA 500 Hz | 20.50 s | 0.037 s | 148.66 s | 200.30 s | 14,652; 0.298 ms / 4.365 s |

The measured simulated speeds were 0.098×, 0.098×, 0.148× and 0.164× respectively; no real-time pass threshold was set. The gripper-law compute, apply, feedback and native-step call distributions are retained in `comparison.json` for each group. CPU initialized on Taichi `x64`. CUDA initialized on Taichi `cuda` and used NVIDIA GeForce RTX 5060, UUID `GPU-c526e691-239f-a5ad-dc68-2305beb29a56`, driver `595.84`, 8,151 MiB. This is CUDA physics evidence, not GPU rendering. The CUDA paths use host `read_cpu_snapshot()` for force and state; they are not device-resident Controller routes.

## Same-file H5 evidence

The existing execution reader verified `T/T+1`, every native row, state/time values, stage receipts, R3 request, five substep target/applied acknowledgements, force samples and the final Outcome. Full H5 identities and hashes are:

| Group | Transitions / boundaries / samples | H5 SHA-256 |
| --- | --- | --- |
| CPU 100 Hz | 2,443 / 2,444 / 12,215 | `2f127e625a593f63954c15bcd48a8f7b23b85e988fed5a60eaf806a4135109d2` |
| CPU 500 Hz | 2,442 / 2,443 / 12,210 | `93d2817135ecc27f477dcfd779c1cdfdadae5f3589f7863cbdaa1285d9314176` |
| CUDA 100 Hz | 2,443 / 2,444 / 12,215 | `b03106d0e503a79519538371fd713566eb12861441e0d21cefeb76430a9778ac` |
| CUDA 500 Hz | 2,442 / 2,443 / 12,210 | `187ab241ef03d9bd28935116695d6619732ecf69961fe505780a7c0badeab3dc` |

Each full H5, Probe H5, process log and raw result is preserved in ignored `workspace/maintenance/nutassembly_gripper_cadence_geophys_20261022/`. The consolidated structured result is `comparison.json`. CPU 100 Hz S2 is in `cpu-100hz-corrected-03/result.json`; the original runner stopped after a checker-only assertion, then the same full H5 passed a separately timed **10.30 s** corrected readback in `cpu-100hz-corrected-03/s3-readback-followup.json`.

## Diagnostic corrections and limits

Four early CPU 100 Hz attempts were preserved, not erased. The first exposed a Core sample validator that hardcoded “update every sample at 500 Hz”; it now accepts the exact 100 Hz first-substep-update/four-holds pattern while keeping native force reads at 500 Hz. The next run exposed a one-ULP control-boundary comparison too strict for five accumulated 2 ms increments; the boundary check now budgets only their binary64 roundoff. A later check incorrectly required the whole arm-plus-gripper target hash to remain fixed while the arm target evolved; the interval validator now checks that only the gripper command and applied opening remain held. The first S3 checker also used `1e-9 rad` for float32 applied-arm ramp acknowledgements and expected threshold fields absent from the stored Guard receipt; the final check keeps exact ramp target validation, permits the observed float32 applied error up to `2e-7 rad`, and verifies the 50 serialized samples themselves all exceed 8 N. These were validation defects; no physical parameter or policy was relaxed.

For this expressly authorized diagnostic, the existing GeoPhys `RobotArmObservationReader.read_cpu_snapshot()` was invoked for every native substep on CPU and CUDA. Its general API guidance still discourages that cadence; the measurements do not expand the Provider's normal support contract, any capability manifest, CUDA device-resident support, or any production profile. No solver-private state was read. The 10 N force target, 8 N Guard threshold/dwell, samples, reset identity and failure checks remained active.

**Bounded exit:** the four requested backend × gripper-cadence cells have Probe, full S2 and same-file S3 evidence. C05c's general Provider/API status remains bounded and diagnostic-only; no generic capability, Qualification, complete C05c approval, complete C02b, Assembly or Phase II status follows from this comparison.
