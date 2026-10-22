# C05c NutAssembly Public Native S1 Acceptance

**Date:** 2026-10-22  
**Current status (2026-10-22 continuation):** the contract-level S1 and defect-sensitive sampling regressions pass. The one-interval GeoPhys CPU evidence is **diagnostic-only** because its public CPU snapshot API explicitly disallows a read at every simulation substep. The exact MuJoCo 3.8.1 CPU route passed full external Expert S2 and canonical execution H5 S3. GeoPhys full S2/S3 remains blocked on a Provider-owned native-rate host sampling contract; C05c is not closed across Providers.

## Preserved baseline and scope

The earlier C05b external PickCube S2/S3 implementation, tests, reports and documentation were preserved in local checkpoint `0255d83` (`checkpoint: preserve C05b external S2 and S3`). Before this continuation, the C05c S1 implementation, tests, docs and receipt were preserved in local checkpoint `389951c` (`checkpoint: preserve C05c native S1 implementation`). The working branch is `codex/phase-ii-c03b`; neither checkpoint was pushed. Ignored Evidence and unrelated files were retained. GeoPhys remains pinned to `a53a8cfed7c9d6464274b5c96fca601271dc4ee4`.

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

The selected route uses one Panda, the existing NutAssembly Outcome V1 recipe, R3 Controller and gripper force law, CPU Provider, 100 Hz outer control and five 2 ms native updates. The public RuntimeSession sample wraps the exact `ActuatorForceMeasurementV1` used by existing `control_feedback()`; it carries Provider/materialization, source, episode/reset, actuator, signed value/unit, source sequence/index, phase and sample/evaluation time. The task Guard sample adds the actual Solution/controller/evaluation-boundary identity, current target and applied acknowledgement. The MuJoCo route below exercises this contract at every substep. GeoPhys's current `read_cpu_snapshot()` route can supply the same values for low-frequency observation, but it is not accepted for every-substep 500 Hz host-servo reads.

The accepted Panda mapping is `actuator8`, force unit `N`, and existing `closing_force_N = max(0, -signed_actuator_force)`. Sampling is native-rate through the selected adapter/RuntimeSession contract; no repeated outer observation is substituted and no solver-private state is read. At the first interval, the first sample is `reset_forward` at time 0; the following samples are completed-step pre-integration samples. For one 10 ms interval the evaluation times are 0, 0.002, 0.004, 0.006 and 0.008 s, while their force sample times are 0, 0, 0.002, 0.004 and 0.006 s. This preserves the real pre-integration phase: the second sample has advanced native identity but still reports the t=0 force evaluation. It is not a post-integration force recomputation or interval average.

Reset identity is now shared explicitly: the NutAssembly Environment boundary uses the public RuntimeSession episode identity. Reset Sample identity remains unchanged. Other selected-task bindings retain their existing Environment episode identity behavior.

## Bounded native Probe evidence

Each Provider was run in an independent process on the same Artifact, ResetSample seed 19, 100 Hz / 5 × 2 ms route. Both external probes performed `reset → one external Solution step → Solution observe → execution Recorder finish → disk reader`. These GeoPhys values remain diagnostic evidence only; the earlier statement that the Probe established a supported GeoPhys native-rate route was too broad. The retained files are under ignored `workspace/maintenance/c05c_nutassembly_native_s1_20261022/rerun_03/`.

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

The focused S1 invocation passed **15 tests** across NutAssembly outcomes and selected consumers. It covered existing close Guard authorization not being bypassed by readiness warnings, Controller-owned hold/ramp requiring and using actual acknowledgement values, reset rebuilding the Controller and clearing hold state, external sample receipt completeness/staleness, wrong reset identity, missing sample, partial native interval, Solution observer failure and Recorder append failure. Faulted intervals did not become complete transitions or exportable recordings; no physical rollback is claimed. The MuJoCo one-interval Probe verifies the RuntimeSession native sequence and H5 readback; GeoPhys's corresponding run is diagnostic-only under its published CPU snapshot limitation.

The changed GeoPhys sample validator also received the focused C02b R1 typed-force/admission and Position/H5 regression: **10 passed**. That run exposed an overly strict comparison which required each two outer-boundary reads to advance exactly one native step, although the R1 legacy outer `RuntimeSession.step()` completes five 2 ms steps. The validator now derives the expected native-index and sample-sequence advance from the elapsed evaluation-boundary time and physics dt, and still rejects a missing/skipped sample, a phase/index mismatch, or any sample identity change within one evaluation state. The C05c native interval tests and fresh probes were rerun after this correction; see the final run record below.

The external API examples and status have been refreshed in TaskEnv public docs and Skill. The TaskEnv Skill refresh was checked against current factories, binding, RuntimeSession, Recorder, callers and tests; the check result is recorded in the Phase C execution log. It is knowledge maintenance, not qualification.

## C02b remaining exit items

C02b remains **BLOCKED** for specific reasons:

1. The new Scene-v3 Panda candidate has GeoPhys CPU typed raw-force publication, exact plan admission and one real R1 interval. It still needs the required structured R1 execution evidence across the intended open/close/obstructed-close/force-hold/reopen behavior and complete request/target/applied/state recording.
2. MuJoCo does not yet publish/admit the required typed raw actuator-force state for the exact plan-bound R1 route; the NutAssembly MuJoCo native sample in this receipt is not that C02b publication contract.
3. The dual-Entity Position S2/H5 result is force-free and cannot close the R1 required-force route. Full C02b qualification has not been issued.

The legacy PickCube `production-r1` route's C05b public lifecycle S1, real external Expert S2 and canonical-v0 S3 did pass on the specified GeoPhys/MuJoCo CPU routes. That completed legacy route is not a missing C05b prerequisite and must not be force-migrated to the unrelated Scene-v3 candidate to close C02b.

## S1-era scope at the time this receipt was first issued

Not run: full NutAssembly external Expert or full `step_expert()` rollout, close Guard activation/authorization under real contact, outcome/task-success completion, long recording S3, warning/strict-failure full campaign, other source/profile/provider/backend intersections, qualification, C02c, Assembly or camera observation integration.

This paragraph records the boundary before the continuation below. The MuJoCo S2/S3 work has since run; the GeoPhys contract gap remains.

## Final verification after the GeoPhys sample-gap correction

The corrected adapter was revalidated with the focused C02b regression (**10 passed**) and C05c/selected-consumer regression (**90 passed in 179.22 s**). `py_compile` for the changed runtime/controller/task/recorder modules, `git diff --check`, and the TaskEnv Skill checker all passed. The real one-interval external and retained `step_expert()` probes were rerun for each Provider in separate processes. All four probe JSON files reported execution/readback success; both external runs wrote and read one transition, two boundaries and five native substeps/samples. This is an execution fact, not a GeoPhys every-substep support claim: `RobotArmObservationReader.read_cpu_snapshot()` explicitly says not to call it on every simulation substep. The updated evidence is under ignored `workspace/maintenance/c05c_nutassembly_native_s1_20261022/rerun_04/`; the original `rerun_03` bytes remain preserved. GeoPhys remains `a53a8cfed7c9d6464274b5c96fca601271dc4ee4`; MuJoCo remains 3.8.1.

## C05c continuation: sampling contract and MuJoCo S2/S3 (2026-10-22)

### GeoPhys sampling route and Provider contract gap

The current Core call path is `step_control_interval()` → per-substep `control_feedback()` → `_GeoPhysSession._capture_actuator_force()` → `RuntimeBoundary.read_snapshot()` → GeoPhys `RobotArmObservationReader.read_cpu_snapshot()`. That Reader materializes `RigidWorldCache`, copies qpos/qvel/ctrl and actuator force to CPU, and brackets the read with sample-status checks. Its public documentation says it is intended for low-frequency observation and says not to call it on every simulation substep. The current C05c 500 Hz host-servo call path does so five times per outer interval. The public `RobotArmDeviceObservationBuffer.pack()` avoids CPU readback but exposes a packed device buffer without the required host value plus atomic phase/freshness/reset identity contract; the existing `device_observation_refs()` similarly does not publish a host sample receipt. Core cannot use either as a substitute for the missing contract.

**GeoPhys result: diagnostic-only; full S2/S3 not run.** No Provider pin or Provider source was changed. A bounded full Expert run was not attempted on this route because the public Reader contract conflicts with its five-per-interval use. The one-interval bytes in the S1 evidence directory remain historical diagnostic evidence and do not qualify this 500 Hz route.

The minimum Provider-owner extension is to the existing `RobotArmObservationReader` / observation-state owner, with the provider boundary exposing that existing owner to Core. It must offer a native-rate CPU host-servo sample that returns the selected actuator's real signed force without copying a full `RigidWorldCache` snapshot, atomically paired with: provider source generation; sample sequence; state and actuator-configuration revisions; native step index; sample phase and native sample time; and validity. The contract must define which completed/pre-integration state produced the value, invalidate it after state/configuration writes and reset, state that reading does not integrate or advance activation, and explicitly permit one CPU host read per 2 ms native update. The existing Core RuntimeSession adapter can then bind that immutable Provider sample to its materialization, episode/reset and evaluation-boundary identity before Controller consumption. The generic device pack is not sufficient unless it also provides the same host-accessible value and freshness receipt. Until GeoPhys supplies and validates this API, Core must not claim a supported GeoPhys 500 Hz Guard/servo route or read private solver state.

### Direct sampling regressions

Added direct Core adapter regressions for continuous native reads, consecutive outer-boundary reads separated by five 2 ms steps, same-evaluation sample mutation, sample sequence/index jumps, provider-clock mismatch, evaluation-boundary mismatch and reset-sample contamination. The focused file `test_phase_ii_c02b_r1_force_freshness.py` passed **17 tests**. In the MuJoCo H5 S3 below, all native sample, Guard, target and acknowledgement rows are present across all consecutive intervals; the reader verifies a continuous sample sequence and all five rows per transition.

### MuJoCo CPU full external Expert S2 and H5 S3

Ran the task-owned `build_outcome_solution(provider="mujoco")` route with `reset_for_solution(seed=19)` and `step_with_solution()` in a real MuJoCo CPU process (horizon 6,000; package `mujoco==3.8.1`). It used the frozen `nut-assembly-outcome-reference-v1` Artifact identity `99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe`, source `nut-assembly-square-v1/canonical-source-nutassembly-nominal-v1` (XML SHA-256 `29d06cc1296411c9bfa8b8d251e915291f47629f058afd3c125a2f02f1f2217a`), the existing R3 Controller identity `1b46eba3cd21b66b7b59cca64bd779c9992259bcaa3950da9de27ad4bb3ef7d2`, Solution identity `6a7fb5eae1b4caa0bd4f18a62fa37ccbd1af6192c961e2e223965acb81056612`, 100 Hz outer control and five 2 ms steps per interval. The actual episode/reset/materialization identities were `episode-4ca12727ce524fd78c8d8357c1bad0ca`, `reset-767d56397dec41243aec445232d8d726b0891e7eeb49f655b789a86b23b5f4a2`, and `mujoco-materialization-477ebbe974b1411dafe780380a084b7e`. The same H5 was closed and read through the existing canonical execution reader.

S2 passed with **2,377 completed transitions / 23.77 s**, all 11 authored stages complete. Task success first became true at control step 2,013 (20.13 s); task success was true at the final boundary. Separately, the planned trajectory and Outcome completed, and the original strict Expert lifecycle reported `expert_complete=true`, `expert_failed=false`, with no readiness warnings. The Environment did not report terminated or truncated; H5 stop reason is `nutassembly-external-expert-complete`. No warning or strict-failure campaign was run.

The actual close Guard selected `alternative_force_8n` under the unchanged Guard policy identity `065af38f034f896d3003d8f63cfb2ea9acac3adcefe078b678bd7596d57a0674` and 8 N / 0.1 s threshold/dwell. Its evidence records 50 continuous native samples over 0.1 s, measured closing force `9.003612594570654 N` from signed actuator force `−9.003612594570654 N`, active and initialized force mode, grasped nut and ready pose. Authorization occurred at 4.56 s and was consumed at the 4.57 s outer boundary. The authorization receipt carries the same episode, reset sample, provider materialization and evaluation boundary as the recorded native samples. The strict Expert assessment used its original `original-guarded-v2-v5-strict-gates` policy.

The execution recorder round-tripped the real H5 byte stream (`byte_exact=true`, logical hash `92a618cbd4fe5c535ca5027150fea53a9f0e2a31ad89ce500b59ec79f4ef1bec`). The existing reader then read the same 20,133,807-byte file from disk (SHA-256 `645bc41015e022b95b342abd403e433cae7bde8a8bfe300676114f3cf7ef78e5`) and verified **T/T+1 = 2,377/2,378**, 11,885 native feedback samples, 475 samples in close-stage intervals, and five samples with continuous sample sequence in every interval. It checked each request mode, substep target and applied acknowledgement; all 10 `hold_last_applied` intervals equal the preceding actual applied arm acknowledgement, and all 1,910 ramp intervals match the Controller-owned linear ramp and per-substep acknowledgement. It also checked all numeric state leaves are finite and that each substep/boundary state clock and native index agrees with the 2 ms/10 ms timeline. Disk state shows a maximum Panda joint displacement of `0.3441948364 rad` and `0.1400020589 m` square-nut displacement from reset to final boundary. The guard authorization is read back from the boundary owner snapshot and equals the runtime receipt. The final response and stop reason are checked separately from task success and strict Expert completion.

The initial full-run process wrote the complete H5 and its Recorder finish succeeded, but its first readback checker stopped on a checker-only lookup of serialized `identity_hash` (the identity is derived from the persisted target mapping). We preserved that raw process JSON and reran only the existing-reader readback against the same H5 with the corrected checker. The same disk file passed. The final evidence is under ignored `workspace/maintenance/c05c_native_s2_s3_20261022/`: `mujoco_external_expert_s2_s3.stdout.log`, `mujoco-nutassembly-external-expert-s2-s3.json` (raw first process receipt), `mujoco-nutassembly-external-expert-s2-s3.h5`, `mujoco-nutassembly-external-expert-s2-s3-readback.json`, and `mujoco-nutassembly-external-expert-s2-s3-final-receipt.json`.

The defect-sensitive S1 command covering full authored Guard policy, native sample receipt, faulted external interval, and incomplete freeze refusal passed **7 tests**. The direct sampling regression file passed **17 tests**. No MuJoCo typed-force C02b plan admission or R1 behavior is claimed by this NutAssembly result.

Final targeted verification reran the combined command for those paths: **24 passed**. Python compilation for the changed Core/task/test modules, `git diff --check`, the TaskEnv Skill checker, and the new C05c report-anchor check passed. The repository-wide `validate_docs.py` was also attempted; it reports the existing Phase A link to an absent C02b anchor, the checked-in documentation inventory count limit, and a documentation-only scope mismatch: it compares against an older inventory baseline and therefore rejects this authorized Core/test work plus other implementation changes already on the branch. No new C05c receipt link failed the targeted anchor check. No broad repository regression or Qualification run was performed.

### Provider-split exit status

| Provider/backend | C05c native sample contract | External NutAssembly Expert S2 | H5 S3 | Result |
| --- | --- | --- | --- | --- |
| GeoPhys `a53a8cf` / CPU | Existing public CPU snapshot provides values at low frequency; it explicitly forbids every-substep use | Not run | Not run | **Blocked; one-interval evidence diagnostic-only** pending the Provider contract above |
| MuJoCo 3.8.1 / CPU | Per-substep signed sample, phase and identity exercised by the existing RuntimeSession path | Passed, seed 19; task success and strict Expert completion both separately recorded | Passed on the same file with state/time, identity, target/ack, full native stream, T/T+1, outcome and guard authorization readback | **Passed for this exact bounded intersection** |

No GeoPhys code or pin, frozen Artifact, old `step_expert()` route, Guard threshold or Outcome policy changed. Full C05c across both Providers, Assembly, C02b and Qualification remain open.
