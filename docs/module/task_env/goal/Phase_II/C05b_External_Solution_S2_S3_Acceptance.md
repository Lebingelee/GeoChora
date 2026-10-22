# C05b Legacy PickCube External Solution S2/S3 Acceptance

**Date:** 2026-10-22  
**Status:** The specified legacy PickCube S2 and canonical-v0 S3 passed independently on GeoPhys CPU and MuJoCo CPU. This is a bounded task/provider result; C02b remains **BLOCKED**, and Phase II is not complete.

## Scope and preserved baseline

This receipt uses the existing `pick-cube-p16-reference-v1` legacy Artifact and `task-env-pick-cube` RuntimeSource. It does not borrow the A05 Scene-v3 candidate or its plan identity, change the frozen Artifact, or change the legacy Controller/feedback contract. The local Core checkpoint is `b3fc42e` (`checkpoint: preserve C05b public lifecycle S1 and GeoPhys pin`), on `codex/phase-ii-c03b`. GeoPhys is pinned and checked out at `a53a8cfed7c9d6464274b5c96fca601271dc4ee4`; no Provider files, branch references, or remote refs were changed. Ignored run evidence is preserved under `workspace/maintenance/c05b_external_s2_s3_20261022/`.

The actual path was the task-owned `build_readiness_solution()`, `SelectedReferenceEnv.reset_for_solution(seed=31)`, and repeated `step_with_solution()` calls using a real RuntimeSession, `ProductionCanonicalPandaController`, R1 required feedback, and the existing canonical-trajectory-v0 Recorder. Each Provider ran in a separate process. One run per Provider also recorded the canonical H5, which was then read back from the same disk file.

| Identity / contract | Exercised value |
| --- | --- |
| UID / Artifact | `pick-cube-p16-reference-v1` / `pick-cube-v1/p1_6_experimental_100hz` |
| Artifact hash | `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4` |
| RuntimeSource | `task-env-pick-cube`; composed XML SHA-256 `bdd119833a5ae3c8176daf1f5ef586c3601870f10f4b4b5f6d7aa730fe5f0fed`; this legacy source has no Scene closure identity, so none was invented |
| Controller / TCP | `ProductionCanonicalPandaController`, `panda-production-control-r1`, `panda-v1/ee`; identity `76108c78b8159391e448ad9f49050bed42fd7a86e0e00a0520083b4e5efb02e9` |
| External Solution | `PickCubeReadinessSolution`, `pick-cube-p16-readiness-expert-v2`; identity `514a5ed3bc0d289761ef88a00b1e7c11df2795133506ab148db9ab8e98e55241` |
| Reset | seed `31`; identical `reset-ee9644c1af42c7897f79a0cece21e5fc4bd5323ae40eba7b7259d34d681a5fb6` ResetSample on both Providers |
| Timebase | 100 Hz outer; 0.010 s control interval; five 0.002 s native steps; post-control-step observation and semantic sampling |
| Required feedback / recording | Existing R1 `actuator8` feedback remains required; existing canonical-trajectory-v0 Recorder; no Event/Outcome or typed-force plan migration |

## S2: real external Expert execution

Both runs reset to the same named Panda joint values and cube pose recorded in the ResetSample. Reset boundary identity named the actual Artifact, RuntimeSource ID and XML hash, Controller, external Solution, Core episode, and ResetSample; it started at control step 0 and time 0. The reset feedback and R1 memory were valid: GeoPhys reported `closing_force_N=0 N`, MuJoCo `4.999378688808065e-11 N`; both reported `close_ready=false`, `force_mode_active=false`, and `force_mode_initialized=false`. These values are the legacy R1 canonical closing-force projection in `CanonicalControlFeedback`, not a new raw signed-force publication claim.

The first close request was made at boundary 73 and evaluated at boundary 74 on both Providers. The actual pre-compute feedback was boundary-matched and finite: GeoPhys `closing_force_N=0.0001983642578125 N`; MuJoCo `0.000488337955090401 N`. On that first closing interval the actual R1 Controller still had force mode inactive; the continued real feedback later activated the existing force mode. From the recorded post-compute Controller memory, GeoPhys force mode was active on rows 89–148 (60 rows); readiness reported `close_ready=true` on 50 rows between 91 and 148. MuJoCo force mode was active on rows 93–470 (378 rows); readiness reported `close_ready=true` on 13 rows between 421 and 434. Force-mode state and readiness are reported separately; neither is inferred from Task success or Expert completion.

The Solution stage sequence on both runs was `move_above_cube` → `descend_vertical` → `close_gripper` → `lift`. The recorded first lift-stage row was 94 for GeoPhys and 422 for MuJoCo. Every completed step recorded a fresh request/evaluation boundary pair, target and actual applied acknowledgement; target and acknowledgement hashes matched. Instrumented calls confirmed `Solution.observe()` completed before the corresponding Recorder append on every transition (148/148 and 470/470 respectively).

| Provider/backend | Completed external intervals | Clock | Task success | Expert completion | Final result |
| --- | ---: | --- | --- | --- | --- |
| GeoPhys `a53a8cfe` / CPU | 148 | step 0 / 0 s → step 148 / 1.480000000000001 s | first true at step 147; lift `0.10764365243911739 m` | done at step 148; endpoint `>=0.105 m` | success; neither terminated nor truncated |
| MuJoCo `3.8.1` / CPU | 470 | step 0 / 0 s → step 470 / 4.7 s | first true at step 469; lift `0.10606502570351223 m` | done at step 470; endpoint `>=0.105 m` | success; neither terminated nor truncated |

The frozen Task threshold remains `0.10 m`; the existing Expert completion endpoint remains `0.105 m`. Both were met without changing the seed, tolerance, feedback, or readiness. On GeoPhys the final Task metrics reported `grasped_cube=false` while `lifted_cube=true`; the lift Task predicate and Expert completion still independently passed. The stored `expert_completed` stop reason is the canonical Recorder finalization reason, not a C03b `EpisodeOutcome` or a newly supported R1 Stop API.

The selected step path requests five substeps from the existing RuntimeSession on each interval. MuJoCo's existing session executes five `mj_step` calls and advances its native-step counter per interval. For GeoPhys this legacy path submits `substeps=5` to the existing boundary and advances the observed clock by 0.010 s; the route does not expose a separate public completed-native-step counter, so this receipt treats five-step completion as supported by the configured call and boundary clock, not as a directly read counter.

## S3: canonical-v0 disk readback

The existing canonical reader loaded each exact H5 path after recording. It validated the canonical trajectory and compared every serialized boundary and transition with the same-run runtime ledger, including numeric state leaves, clock, feedback/readiness, Task metrics and flags, requested action → canonical action → target → applied acknowledgement, stage, reward, and termination flags. It also checked source/Artifact/Controller/Solution/ResetSample identities, Provider, seed, T/T+1, and `stop_reason=expert_completed`. The legacy source closure stayed absent in the file metadata.

| Provider | H5 and schema | Readback | SHA-256 |
| --- | --- | --- | --- |
| GeoPhys CPU | `geophys_retry01/pickcube_external_expert.h5`, canonical-trajectory-v0 | 148 transitions / 149 boundaries; all 149 numeric state boundaries and 148 request-to-ack transitions compared; logical identity `af504faaafae585a533b5a925ae7aa47c272afca8555c2ed8dda225410eda233` | `fd948fa1fd1eb87b6b6dca4a6f09bd9fb74049b44fba8fd6af7df2d950d89257` |
| MuJoCo CPU | `mujoco/pickcube_external_expert.h5`, canonical-trajectory-v0 | 470 transitions / 471 boundaries; all 471 numeric state boundaries and 470 request-to-ack transitions compared; logical identity `a5a532adc5d2324cabab9802687d3b4e3e38f4060c3d6cad38603d7ba2fa3be8` | `a941cb23375b71b4a3bbb44ccc3ce82c5daf8cf7a7b4b19d5e3ce2c7a2489383` |

GeoPhys's first candidate run stopped on a diagnostic interval comparator at step 8; it is retained separately. The subsequent full run reached Expert completion and wrote the H5, but its in-process post-write checker then used the nonexistent `BoundaryRecord.success` attribute. The diagnostic was corrected to use the actual reader contract and independently read the same saved file; the corrected receipt reports `S2_PASS_S3_PASS`. This was a probe/readback bug, not a Provider failure. Both failed raw receipts and the final same-file readback are retained.

## Failure boundary and checks

`finish_recording()` now refuses to freeze a faulted selected canonical recording as a complete trajectory. The existing C03a fault latch is reused. A targeted observer-failure and Recorder-append-failure test confirms that each injected error occurs after the test session has advanced to boundary 1, produces no transition, makes finalization reject, creates no H5 file, and does not claim physics rollback. A follow-up step remains fault-closed. This failure test is lifecycle evidence, not a native failure injected into either completed S2 run.

Final targeted regression:

```text
PYTHONPATH=GeoPhys/src:. python -m pytest -q \
  task_env/diagnostics/tasks/test_selected_consumers.py \
  task_env/diagnostics/tasks/test_phase_ii_c03a_fault_lifecycle.py \
  task_env/diagnostics/tasks/test_phase_ii_c05a_structured_recording.py
72 passed, 1 upstream Taichi locale deprecation warning
```

The two parametrized fault cases are `test_c05b_faulted_canonical_recording_cannot_be_exported`. Focused C05b tests also passed 9 cases. `py_compile` and `git diff --check` are recorded after the final documentation edits. Raw command output and receipts are under the ignored Evidence directory named above.

## Result boundary

This closes the requested legacy PickCube external Solution S2 and canonical-v0 S3 for **GeoPhys `a53a8cf` CPU and MuJoCo 3.8.1 CPU only**, using the exact old Artifact/source/R1/TCP route and seed-31 sample. It does not grant a plan-bound identity to that legacy source, extend typed-force admission to it, or claim MuJoCo typed-force publication. Selected legacy R1 Stop/Outcome remains unsupported; canonical-v0 has no Event/Outcome/native-substep stream. NutAssembly 500 Hz Guard, Assembly, full Expert coverage beyond this PickCube Solution, Qualification, and Phase II completion were not run or granted. C02b remains **BLOCKED** on its independent remaining exits.

### Evidence paths

- GeoPhys full run: `workspace/maintenance/c05b_external_s2_s3_20261022/geophys_retry01/geophys_run.json`
- GeoPhys final independent readback: `workspace/maintenance/c05b_external_s2_s3_20261022/geophys_retry01/s3_readback_final.json`
- GeoPhys H5: `workspace/maintenance/c05b_external_s2_s3_20261022/geophys_retry01/pickcube_external_expert.h5`
- MuJoCo run and H5 readback: `workspace/maintenance/c05b_external_s2_s3_20261022/mujoco/mujoco_run.json`
- MuJoCo H5: `workspace/maintenance/c05b_external_s2_s3_20261022/mujoco/pickcube_external_expert.h5`
- Final regression: `workspace/maintenance/c05b_external_s2_s3_20261022/checks/c05b_c03a_c05a_pytest_final.log`
- Initial GeoPhys diagnostic failures: `geophys/geophys_run.json` and `geophys_retry01/geophys_run.json` in the same Evidence directory
