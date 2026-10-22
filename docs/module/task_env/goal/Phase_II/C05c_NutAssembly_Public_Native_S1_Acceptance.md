# C05c NutAssembly Public Native S1 Acceptance

**Date:** 2026-10-22  
**Status:** bounded S1 and one-native-interval Probe passed on the specified GeoPhys CPU and MuJoCo CPU routes. Full external Expert S2/S3 remains open.

## Preserved baseline and scope

The earlier C05b external PickCube S2/S3 implementation, tests, reports and documentation were preserved in local checkpoint `0255d83` (`checkpoint: preserve C05b external S2 and S3`). The working branch is `codex/phase-ii-c03b`. The checkpoint was not pushed; ignored Evidence and unrelated files were retained. GeoPhys remains pinned to `a53a8cfed7c9d6464274b5c96fca601271dc4ee4`.

This slice adds a source-bound NutAssembly external Solution lifecycle using the existing task, Controller, RuntimeSession, selected Environment and execution Recorder owners. It keeps the existing `step_expert()` path. It does not run a full external Expert, enter a complete close/Guard transition, evaluate full task success or Outcome completion, or claim C05c S2/S3.

## Existing owners and call order

| Owner | State and responsibility |
| --- | --- |
| `NutAssemblyOutcomeSolutionV1` | Owns stage, authored action plan, close-authorization Guard state, observation history, warning/strict-failure and completion state. `act()` emits a versioned arm execution request; it does not hand the Environment a mutable hold/ramp object. |
| `ReferenceExecutionController` / existing canonical Controller | Owns the existing R3 Controller, 500 Hz `NativeRateGripperServo`, and acknowledged arm hold/ramp state. `hold_last_applied` and `ramp_from_last_applied` require a prior applied acknowledgement. |
| `RuntimeSession` | Owns materialization, reset identity, Provider sample validity/phase/sequence/time, canonical force projection, application and native stepping. The new public `episode_id` and existing materialization identity let Environment boundary receipts match the actual session. |
| `SelectedReferenceEnv` | Validates the task-owned Solution against the selected source and Controller, publishes reset/step boundaries, orders compute → per-native apply/step/sample → Solution observe → Recorder append, and applies the existing fault latch. Raw external actions remain rejected for NutAssembly. |
| `ExecutionRecorder` | Owns pending/complete native intervals. It now preserves the optional serialized native sample already supplied with each applied substep; an incomplete interval remains pending and cannot be frozen as a complete episode. |

The external call is `build_outcome_solution(provider=...)`, `env.reset_for_solution(solution, seed=19)`, then `env.step_with_solution(solution)` once per outer interval. The active Solution is the caller's object. The Environment does not use `env.solution`, private Solution stage, or a mutable hold/ramp reference on this route.

## Native feedback contract

The bounded selected route uses one Panda, the existing NutAssembly Outcome V1 recipe, R3 Controller and gripper force law, CPU Provider, 100 Hz outer control and five 2 ms native updates. The public RuntimeSession sample wraps the exact `ActuatorForceMeasurementV1` used by existing `control_feedback()`; it carries Provider/materialization, source, episode/reset, actuator, signed value/unit, source sequence/index, phase and sample/evaluation time. The task Guard sample adds the actual Solution/controller/evaluation-boundary identity, current target and applied acknowledgement.

The accepted Panda mapping is `actuator8`, force unit `N`, and existing `closing_force_N = max(0, -signed_actuator_force)`. Sampling is native-rate through the selected adapter/RuntimeSession contract; no repeated outer observation is substituted and no solver-private state is read. At the first interval, the first sample is `reset_forward` at time 0; the following samples are completed-step pre-integration samples. For one 10 ms interval the evaluation times are 0, 0.002, 0.004, 0.006 and 0.008 s, while their force sample times are 0, 0, 0.002, 0.004 and 0.006 s. This preserves the real pre-integration phase: the second sample has advanced native identity but still reports the t=0 force evaluation. It is not a post-integration force recomputation or interval average.

Reset identity is now shared explicitly: the NutAssembly Environment boundary uses the public RuntimeSession episode identity. Reset Sample identity remains unchanged. Other selected-task bindings retain their existing Environment episode identity behavior.

## Bounded native Probe evidence

Each Provider was run in an independent process on the same Artifact, ResetSample seed 19, 100 Hz / 5 × 2 ms route. Both external probes performed `reset → one external Solution step → Solution observe → execution Recorder finish → disk reader`. The retained files are under ignored `workspace/maintenance/c05c_nutassembly_native_s1_20261022/rerun_03/`.

| Item | GeoPhys CPU | MuJoCo CPU |
| --- | --- | --- |
| Provider build | GeoPhys `a53a8cfed7c9d6464274b5c96fca601271dc4ee4` | MuJoCo `3.8.1` |
| TaskArtifact identity | `99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe` | same |
| Source ID | `nut-assembly-square-v1/canonical-source-nutassembly-nominal-v1` | same |
| Projected source XML SHA-256 | `909759def6bbaa4c5644a100a36625400464cd571dcab1222f807efaaf1c225d` | `29d06cc1296411c9bfa8b8d251e915291f47629f058afd3c125a2f02f1f2217a` |
| Controller identity | `0b11b4be4c9dfa60535f5f7d32128e01c8012558dea33ec9bdc2d23925844928` | `b1b9a017e312767d3415fe54f10d4f548cf0d8f37c525878fa8c40c41135de2c` |
| Requested/completed native steps | 5 / 5 | 5 / 5 |
| Reset/evaluation clock | 0 → 0.010 s | 0 → 0.010 s |
| H5 readback | 1 transition, 2 boundaries, 5 substeps, 5 typed Guard samples | same |

The source hashes and full identities, all five raw-force samples, 500 Hz update diagnostics, target/applied receipts, Recorder finish result and H5 SHA-256 are in `geophys-probe.json` / `mujoco-probe.json`. The exact disk files are `geophys-one-native-interval.h5` / `mujoco-one-native-interval.h5`. The probe deserialized all five persisted NutAssembly samples through the existing sample contract and matched them to the in-memory receipt; it independently checked the last substep target hash against its applied acknowledgement.

Raw signed samples for the external interval were:

- GeoPhys: `0, 0, 0, +0.0007781982421875, +0.0002593994140625 N`; the canonical closing magnitude was zero for all five.
- MuJoCo: `+0.000004470298364367409, +0.000004470298364367409, +0.00000118702837426099, +0.00000003720788299688138, -0.0000004892696381375572 N`; the closing magnitude was zero for the first four and `0.0000004892696381375572 N` for the fifth.

These opening-stage values prove source sampling and signed-to-canonical conversion only. They do not exercise the close Guard authorization or claim a force-mode grasp. `legacy_step_expert_probe.py` also ran one internal `step_expert()` interval in an independent process for each Provider; it verified the same five sample phases, target/ack alignment and 0.010 s boundary. It did not run the full legacy Expert.

## S1 and fault coverage

The focused S1 invocation passed **15 tests** across NutAssembly outcomes and selected consumers. It covered existing close Guard authorization not being bypassed by readiness warnings, Controller-owned hold/ramp requiring and using actual acknowledgement values, reset rebuilding the Controller and clearing hold state, external sample receipt completeness/staleness, wrong reset identity, missing sample, partial native interval, Solution observer failure and Recorder append failure. Faulted intervals did not become complete transitions or exportable recordings; no physical rollback is claimed. The one-interval real Probe separately verifies actual RuntimeSession sampling, native sequence and H5 readback on both Providers.

The changed GeoPhys sample validator also received the focused C02b R1 typed-force/admission and Position/H5 regression: **10 passed**. That run exposed an overly strict comparison which required each two outer-boundary reads to advance exactly one native step, although the R1 legacy outer `RuntimeSession.step()` completes five 2 ms steps. The validator now derives the expected native-index and sample-sequence advance from the elapsed evaluation-boundary time and physics dt, and still rejects a missing/skipped sample, a phase/index mismatch, or any sample identity change within one evaluation state. The C05c native interval tests and fresh probes were rerun after this correction; see the final run record below.

The external API examples and status have been refreshed in TaskEnv public docs and Skill. The TaskEnv Skill refresh was checked against current factories, binding, RuntimeSession, Recorder, callers and tests; the check result is recorded in the Phase C execution log. It is knowledge maintenance, not qualification.

## C02b remaining exit items

C02b remains **BLOCKED** for specific reasons:

1. The new Scene-v3 Panda candidate has GeoPhys CPU typed raw-force publication, exact plan admission and one real R1 interval. It still needs the required structured R1 execution evidence across the intended open/close/obstructed-close/force-hold/reopen behavior and complete request/target/applied/state recording.
2. MuJoCo does not yet publish/admit the required typed raw actuator-force state for the exact plan-bound R1 route; the NutAssembly MuJoCo native sample in this receipt is not that C02b publication contract.
3. The dual-Entity Position S2/H5 result is force-free and cannot close the R1 required-force route. Full C02b qualification has not been issued.

The legacy PickCube `production-r1` route's C05b public lifecycle S1, real external Expert S2 and canonical-v0 S3 did pass on the specified GeoPhys/MuJoCo CPU routes. That completed legacy route is not a missing C05b prerequisite and must not be force-migrated to the unrelated Scene-v3 candidate to close C02b.

## Not run and next boundary

Not run: full NutAssembly external Expert or full `step_expert()` rollout, close Guard activation/authorization under real contact, outcome/task-success completion, long recording S3, warning/strict-failure full campaign, other source/profile/provider/backend intersections, qualification, C02c, Assembly or camera observation integration.

The next C05c work may start its separately authorized S2/S3 only after this S1 contract review: run the full task-owned external Solution through its stages on each declared Provider process, retain actual native Guard receipts through the existing Recorder, and read the completed disk episodes back. Keep the warning/strict failure and task-success/Expert-completion distinctions. This report does not declare that work started.

## Final verification after the GeoPhys sample-gap correction

The corrected adapter was revalidated with the focused C02b regression (**10 passed**) and C05c/selected-consumer regression (**90 passed in 179.22 s**). `py_compile` for the changed runtime/controller/task/recorder modules, `git diff --check`, and the TaskEnv Skill checker all passed. The real one-interval external and retained `step_expert()` probes were rerun for each Provider in separate processes. All four probe JSON files report `passed`; both external runs wrote and read one transition, two boundaries and five native substeps/samples. The updated evidence is under ignored `workspace/maintenance/c05c_nutassembly_native_s1_20261022/rerun_04/`; the original `rerun_03` bytes remain preserved. GeoPhys remains `a53a8cfed7c9d6464274b5c96fca601271dc4ee4`; MuJoCo remains 3.8.1. Full NutAssembly external Expert S2/S3 remains unrun.
