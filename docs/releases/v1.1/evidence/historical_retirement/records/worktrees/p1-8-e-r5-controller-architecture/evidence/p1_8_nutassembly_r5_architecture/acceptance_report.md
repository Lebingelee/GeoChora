# P1.8-E-R5 Materialization Audit Continuation

**Status: `materialization_boundary_localized`**

Generated 2026-10-08 06:16:56 UTC; run wall-clock approximately 36.5 minutes, with physics complete by 05:58:01 UTC (before the minute-55 stop). The static finger-joint-to-pad map matches across GeoPhys and MuJoCo (maximum pad-gap difference 0.107 µm). The unresolved boundary is dynamic: the fixed-object gripper response and finger-equality realization differ, and MuJoCo loses vertical Nut support during verify-lift before the contact patches walk onto the Nut top edge. No correction was applied because the traces do not isolate a safe, causal adapter/shared-source/servo change.

Branch remained `codex/p1.8-e-r5-controller-architecture`; HEAD remained `e8ee54fa16e6537a39b61038d892f2646c0e1ac7`. Persistent-reference R3 and the 6/6 T0 evidence were preserved unchanged. M0/M1/M2 were limited to the requested TB100 probes. No T1, full NutAssembly, D0–D2, SAPIEN, or Genesis.

See [`materialization_audit/materialization_report.md`](materialization_audit/materialization_report.md) for the authored-vs-realized table, M0/M1/M2 measurements, contact timeline, root classification, and correction decision.

---

# P1.8-E-R5 Controller Architecture and Grasp-Retention Record

## Current grasp-retention continuation

**Status: `grasp_retention_unresolved`.** The baseline MuJoCo/TB100 failure is localized to verify-lift slip: bilateral Nut contact exists at fallback authorization and through the first capture-drift violation, then contact and force collapse while the Nut remains near the table. One measured 3 mm shared grasp-z correction preserved GeoPhys/TB100 but prevented MuJoCo from authorizing; no second correction or rate expansion was justified.

### Same-branch provenance and timing

- Branch: `codex/p1.8-e-r5-controller-architecture`; no new branch/worktree.
- Continuation start HEAD: `8d9968f0070852ae707f3f635c946242d432bd59`.
- Ending HEAD: `e8ee54fa16e6537a39b61038d892f2646c0e1ac7` (`test(phase1): localize NutAssembly grasp retention`).
- Persistent-reference controller file unchanged; R1 `production.py` SHA-256 remains `715d78a6339a4b18f6517b2a9a2eee71bc9e2c6cfcf05723d50adae4059754f3`.
- Physics stopped after the MuJoCo/TB100 correction run completed at 2026-10-08 05:12:08 UTC, well before the 55-minute trigger. No physics is pending.
- This run started 2026-10-08 04:55:21 UTC; report generated at 2026-10-08 05:25:03 UTC; total wall-clock through this report: 29.69 minutes. No push or public/main change.

### Baseline TB100

| Field | GeoPhys | MuJoCo |
|---|---:|---:|
| First left/right/bilateral finger-Nut contact | Pair attribution unavailable | 2.572 s |
| Last bilateral contact during close | Pair attribution unavailable | 3.740 s |
| Force-mode entry | 2.690 s | 2.616 s |
| Authorization | controller_close_ready, 0.930 s | stable_grasp_fallback, 1.170 s |
| Opening at authorization | 33.190 mm | 10.633 mm |
| Canonical closing force at authorization | 30.0 N | 26.549 N |
| Native actuator force at authorization | Pair-force diagnostic unavailable | ~-26.55 N |
| Nut contact at authorization | Active per-body Nut aggregate; no finger-pair IDs | Bilateral; 44 finger/Nut contact pairs |
| Verify-lift | PASS | FAIL |
| Corrected capture translation drift | 0.0319 mm | 101.927 mm |
| Corrected capture rotation drift | 0.000927 rad | 0.005164 rad |

At MuJoCo authorization, each finger has about 5.3 mm joint-coordinate distance from its lower limit; finger/table contact is absent and equality force is negligible. In the baseline close trace, all 232 samples with canonical force feedback >=25 N also have bilateral finger/Nut contact. The 25–27 N force is therefore mechanically associated with Nut contact in the sampled MuJoCo baseline; the evidence does not support false force readiness from internal resistance.

During verify-lift, relative slip first exceeds 1 mm at 3.992 s while force remains 26.52 N and bilateral contact persists. Nut height rises only about 1.02 mm. Relative translation first exceeds the 8 mm capture bound at 4.204 s while bilateral contact remains, force has fallen to 14.01 N, and opening is 6.81 mm. Force falls below 1 N at 4.358 s; bilateral contact is lost at 4.372 s. Canonical `grasped_nut` remains true for 229 sampled intervals after native bilateral contact is gone. The corrected maximum capture drift is 101.927 mm. Primary classification: **verify_lift_slip**.

### Why authorization opening differs by provider

At readiness, GeoPhys reports about 16.60 mm per finger joint (33.19 mm combined opening) and controller-ready force of 30 N. MuJoCo reports about 5.316 mm per finger joint (10.63 mm combined opening) and authorizes only its 25 N fallback at 26.55 N. This is a measured provider gripper/contact materialization difference. GeoPhys lacks public finger-pair contact attribution, so this run cannot determine whether the difference originates in contact proxy realization, actuator mapping, or both.

### Shared correction 01

The single correction profile (`2a2bd8ade2ae30ab5d43ec75a8329fd0d7116cee8563b0c756806f4b714696b2`) changed only shared `grasp_offset.z` from 0.050 m to 0.047 m, based on the measured upward migration of MuJoCo’s force-weighted contact centroid: 2.879 mm above Nut COM at authorization to 7.952 mm at the first capture-drift violation.

- GeoPhys/TB100 still passes at 0.930 s, 30 N and 33.138 mm opening; verify-lift passes with 0.0444 mm translation drift.
- MuJoCo/TB100 does not authorize. It reaches a transient 27.55 N at 3.720 s with 11.19 mm opening and bilateral contact, but does not hold the fallback stability window. At close timeout (11.490 s) it is still bilateral, but force is 11.80 N and opening is 4.72 mm. Verify-lift does not run.
- The candidate did not repair retention and was not promoted. Correction 02 was not used because correction 01 did not improve the MuJoCo hard gate.

### Final G0 evidence

The previous R5 rate matrix remains historical evidence. TB500/TB50 were not rerun in this continuation. Their prior verify-lift failures still fail G0; their old capture-drift numbers used the incorrect inverse-quaternion diagnostic and are invalid. Current corrected TB100 results are shown in the next section.

| Rate | Provider | Baseline G0 evidence | Correction 01 |
|---|---|---|---|
| TB500 | GeoPhys | Prior R5 PASS; 0.932 s, 30 N, 33.337 mm; capture drift not revalidated here | Not run |
| TB100 | GeoPhys | Current baseline PASS; 0.930 s, 30 N, 33.190 mm, 0.0319 mm drift | PASS; 0.930 s, 30 N, 33.138 mm |
| TB50 | GeoPhys | Prior R5 PASS; 0.920 s, 30 N, 33.630 mm; capture drift not revalidated here | Not run |
| TB500 | MuJoCo | Prior R5 authorization; verify-lift FAIL; earlier drift value invalid | Not run |
| TB100 | MuJoCo | Current baseline fallback at 1.170 s, 26.549 N, 10.633 mm; verify-lift FAIL; 101.927 mm corrected drift | Close authorization FAIL; transient peak 27.547 N, no verify-lift |
| TB50 | MuJoCo | Prior R5 authorization; verify-lift FAIL; earlier drift value invalid | Not run |

Rate expansion was not run because corrected-profile TB100 did not pass on both providers. No T1, full NutAssembly, D0–D2, SAPIEN, or Genesis was run.

### Integrity and recommendation

- Persistent-reference R3 and planner: unchanged.
- R1/PickCube and legacy `session.step()`: unchanged.
- Nut mass/inertia, asset, friction, task semantics, timeouts, 30 N target, 1 N deadband, 25 N fallback, fallback window and capture bounds: unchanged.
- Provider-specific behavior and broad tuning sweep: none.
- Diagnostic-only correction: fixed inverse-quaternion transform in the read-only capture-drift analyzer; earlier 0.3057 m MuJoCo drift was superseded by the valid 0.101927 m TB100 result. A no-authorization analyzer edge case was also handled; it did not alter runtime behavior.
- Recommendation: keep persistent-reference R3 as the supported free-space development candidate, but leave MuJoCo grasp retention unresolved. Human review should decide whether to investigate provider gripper/contact materialization before any T1 or full-task qualification.

Detailed artifacts: `grasp_retention/contact_timeline.md`, `grasp_retention/retention_comparison.md`, `grasp_retention/retention_decision.json`.

## Prior R5 architecture status

**persistent_reference_supported** — the persistent-reference arm passed the first segment, full GeoPhys/TB500 T0, and the six-cell T0 matrix. This is development Evidence only, not Phase-I qualification. Fixed-rate gripper G0 is separately partial: GeoPhys passed 3/3; MuJoCo failed all three complete G0 gates.

## Wall-clock

- Continuation start: `2026-10-08 04:12:39 UTC`
- Physics stopped: `2026-10-08 04:33:03 UTC` (last G0 trace write; no physics runs followed)
- Report generated at: `2026-10-08 04:42:22 UTC`
- Total wall-clock through report: **29.72 minutes** (within the 60-minute budget).
- Physics stopped by minute 55: **yes**
- No pending physics run remained.

## Same-branch provenance

- Branch: `codex/p1.8-e-r5-controller-architecture`
- Starting HEAD: `7e8c1e042d5156ef87bcdba20ad141426747ce14`
- Checkpoint commit preserving rejected R3: `7e8c1e042d5156ef87bcdba20ad141426747ce14`
- Controller implementation commit: `9332fbe`
- Ending HEAD: `8d9968f0070852ae707f3f635c946242d432bd59`
- New branch created: **no**
- Rejected achieved-state R3 source/Evidence preserved: **yes** (`rejected_achieved_state/` and checkpoint commit).
- R4 Evidence modified: **no**
- R1 source unchanged: **yes**, SHA-256 `715d78a6339a4b18f6517b2a9a2eee71bc9e2c6cfcf05723d50adae4059754f3`.

## Persistent-reference law

- Reset: `q_ref = canonical q_actual` at controller reset; previous requested pose starts unset.
- Normal update: `q_ref_next = q_ref_previous + qdot_cmd * control_dt`.
- Safety bound: per-joint reference lead clipped to ±0.15 rad after joint-limit projection; the persistent state is retained within that bounded lead.
- First-segment lead: maximum 0.03223 rad, mean absolute 0.00576 rad, nonzero for the full 3.344 s; zero lead-clamp activations and zero velocity clips.
- Reset events: one explicit reset per run; no unexpected q_ref resets. No twist-history reset occurred in the six T0 routes.
- Arm actuator saturation: 0% in all six T0 cells. First-segment maximum absolute force was 22.78 N against a 250 N limit.
- Profile: `canonical-panda-production-r3-persistent-reference-v1`; source SHA-256 `8805f0f3b6e5497871269888d876216baef96bfa7e5fabc8f3e0eef93e1152b5`.
- Shared arm profile: feedforward 1.0; position/rotation feedback 4 s⁻¹; DLS damping 0.02; rotation row weight 0.22; joint velocity cap 2 rad/s; lead bound 0.15 rad. Planner and gripper rates stayed frozen.

## First-segment causal test

Same GeoPhys/TB500 vertical waypoint and first 1,622 planned boundaries. Plan-exhaustion errors are listed; persistent R3 then passed the separate 0.1 s endpoint readiness window.

| Metric | C11 | Rejected R3 (achieved-state rebase) | Persistent R3 |
|---|---:|---:|---:|
| Position RMS (m) | 0.01712732 | 0.1344428 | 0.001545539 |
| Position p95 (m) | 0.02764152 | 0.1931128 | 0.003492152 |
| Position peak (m) | 0.02779951 | 0.1931509 | 0.003773435 |
| Rotation RMS (rad) | 0.003026229 | 0.155543 | 0.002271261 |
| Rotation p95 (rad) | 0.004206436 | 0.2112064 | 0.006300169 |
| Rotation peak (rad) | 0.004857812 | 0.2137368 | 0.007291585 |
| Plan-exhaustion position error (m) | 0.006534176 | 0.1931509 | 0.0007660621 |
| Plan-exhaustion rotation error (rad) | 0.002767903 | 0.2137368 | 6.423689e-05 |
| Maximum reference/target-to-achieved joint error (rad) | not recorded | 0.00328 | 0.03222667 |
| Actuator saturation fraction | not recorded | not recorded | 0 |

**Causal hypothesis: supported.** Persistent R3 remained ahead of achieved arm state, with a 0.03223 rad maximum lead versus the rejected R3 target/achieved discrepancy of about 0.00328 rad. The plan-exhaustion miss fell from 193.15 mm / 0.21374 rad to 0.766 mm / 0.000064 rad. The endpoint gate passed.

## Full TB500 T0

GeoPhys/TB500 passed all five endpoint gates. Path-wide position RMS/p95/peak: 1.435 / 2.547 / 3.773 mm. Rotation RMS/p95/peak: 0.01490 / 0.008277 / 0.12617 rad. Rotation peak is a transient; the declared hard gate is endpoint readiness.

## Six-cell T0

| Rate | GeoPhys | MuJoCo |
|---|---|---|
| TB500 | 5/5 PASS | 5/5 PASS |
| TB100 | 5/5 PASS | 5/5 PASS |
| TB50 | 5/5 PASS | 5/5 PASS |

All six cells passed. Per-cell path-wide metrics, mean position-error proxy, lead, actuator force, and saturation fraction are in `persistent_reference/six_cell_t0/matrix.json`. Temporal lag was not separately inferred from pose-error norms. TB500 position tracking is comparable to TB100/TB50; its rotation peak is 0.126 rad versus 0.117/0.107 rad.

## Fixed-rate gripper

The shared inner servo ran at 500 Hz for all outer rates. The initial R5 G0 matrix recorded GeoPhys as passing all three cells and MuJoCo as passing close acquisition but failing verify-lift at all three rates. The older MuJoCo capture-drift values (~0.306 m) are invalid because they used an incorrect inverse-quaternion diagnostic; the corrected TB100 baseline in the current continuation measures 0.101927 m. TB500/TB50 were not rerun after that diagnostic correction.

| Rate | Provider | Prior authorization | Verify-lift | Current corrected capture evidence |
|---|---|---|---|---|
| TB500 | GeoPhys | controller_close_ready, 0.932 s / 30 N / 33.337 mm | PASS | Not revalidated in this continuation |
| TB500 | MuJoCo | stable_grasp_fallback, 1.182 s / 26.539 N / 10.627 mm | FAIL | Old drift invalid; not rerun |
| TB100 | GeoPhys | controller_close_ready, 0.930 s / 30 N / 33.190 mm | PASS | 0.0319 mm translation / 0.000927 rad rotation |
| TB100 | MuJoCo | stable_grasp_fallback, 1.170 s / 26.549 N / 10.633 mm | FAIL | 101.927 mm translation / 0.005164 rad rotation |
| TB50 | GeoPhys | controller_close_ready, 0.920 s / 30 N / 33.630 mm | PASS | Not revalidated in this continuation |
| TB50 | MuJoCo | stable_grasp_fallback, 1.140 s / 26.583 N / 10.654 mm | FAIL | Old drift invalid; not rerun |

### Grasp-retention diagnosis and correction

The baseline MuJoCo/TB100 failure is **verify_lift_slip**, not false force readiness: all 232 samples at or above 25 N have bilateral finger/Nut contact; at authorization the actuator and contact diagnostics show a mechanically loaded bilateral grasp. Relative drift first exceeds 8 mm at 4.204 s while contact remains bilateral and force has fallen to 14.01 N. Bilateral contact is lost at 4.372 s; canonical `grasped_nut` remains true for 229 sampled intervals afterward.

One measured shared correction lowered `grasp_offset.z` from 0.050 m to 0.047 m. GeoPhys/TB100 still passed. MuJoCo/TB100 did not authorize: force peaked transiently at 27.55 N, then fell to 11.80 N by close timeout while bilateral contact remained. No second correction or rate expansion was run. The provider opening difference is measured (33.19 mm GeoPhys vs 10.63 mm MuJoCo at authorization); its exact materialization source is unresolved. See `grasp_retention/contact_timeline.md` and `grasp_retention/retention_comparison.md`.

## Prior arm-spike one-fix rule and tuning audit

- Implementation correction count: **1** — cumulative binary64 native-interval audit bound after GeoPhys/TB100 attempt 01 failed the timebase audit from accumulated float rounding. This changed audit tolerance only; simulation/controller behavior was unchanged. Only TB100 was rerun, and it passed.
- Arm gain sweep: **no**
- Planner tuning: **no**
- Gripper-rate tuning: **no**
- Threshold or geometry tuning: **no**
- Provider-specific controller behavior: **no**
- Behavioral parameter candidates after first run: **0**

## Backward compatibility (architecture spike, previous continuation)

- R1 source SHA unchanged. The default `ProductionCanonicalPandaController` was not modified.
- PickCube files/routes were not migrated or edited.
- Existing `session.step()` path is unchanged from the R5 checkpoint; fixed-rate servo execution is opt-in through `step_control_interval`.
- Public action schema remains absolute pose / world / quaternion_wxyz.
- Planner, task semantics, mass, friction, geometry, thresholds, and physics solver configuration were unchanged.

## Not run

T1, full NutAssembly, D0–D2, SAPIEN, and Genesis were **not run**. No dynamic profile lock or Phase-I acceptance claim was created.

## Current recommendation

The persistent-reference arm remains a supported free-space development candidate. MuJoCo grasp retention is unresolved: baseline verify-lift slips, while the single measured shared grasp-offset correction prevents stable close authorization. Keep T1 and full-task qualification stopped for Human Review.

---

# P1.8-E-R5 Engineering Grasp Sanity Audit

**Status: `engineering_boundary_localized`** (engineering Evidence only; not Phase-I qualification). This audit ran on the existing branch `codex/p1.8-e-r5-controller-architecture`, starting and ending at `e8ee54fa16e6537a39b61038d892f2646c0e1ac7`. No production behavior, simulator source, branch, or worktree was changed. Physics execution stopped by the minute-55 limit.

- Authored handle width is 31.75 mm. Principal-pad zero-gap opening is 28.75 mm; auxiliary-pad zero-gap opening is 31.75 mm. The geometric investigation band is about 29–33 mm. The functional GeoPhys/TB100 baseline authorizes at 33.190 mm / 30 N and passes verify-lift, but GeoPhys's body-aggregate contact API does not establish which exact finger geom carries the load.
- The current MuJoCo/TB100 authorization opening is 10.633 mm. Its physical principal-pad gap is 13.633 mm; static reconstruction at the authorization state gives 9.328 mm principal-pad/handle, 10.774 mm auxiliary-pad/handle, and 3.198 mm finger-mesh/handle penetration. This state is deeply interpenetrating and not a geometrically healthy grasp.
- The archived 0.1 kg, 25 N fallback MuJoCo grasp-lift was reproduced in MuJoCo 3.8.1: the Nut rose 97.338 mm and stayed in bilateral contact during the recorded lift. The historical authorization also had a ~10.63 mm opening and deep reconstructed pad/handle overlap. Historical and current grasp outcomes differ despite similar opening and force; controller, gripper rates, planner dynamics, and Nut-in-EE placement also differ.
- The prior ~80 mm fixed-object force event was pad-box contact against Nut outer-frame geom `SquareNut_collision_3`, not the 31.75 mm handle geom `SquareNut_collision_4`.
- The all-five-pad-only diagnostic fixture did not retain the Nut: GeoPhys did not authorize; MuJoCo authorized then failed verify-lift. A principal-pad-only supplement did not authorize on either provider.
- Primary classification is `mixed_engineering_boundary` (medium confidence). High-confidence secondary findings are deep interpenetration at current authorization and unintended outer-frame contact in the ~80 mm probe. There is no evidence justifying simulator-dynamics changes.
- Six auxiliary hand-camera MP4/H.264 recordings are listed with hashes, event times, and camera metadata in `engineering_grasp_audit/media_manifest.json`. Reports embed no media. Human visual review is required.

Detailed text-only report: `engineering_grasp_audit/engineering_grasp_report.md`. T1, full NutAssembly, D0–D2, SAPIEN, and Genesis were **not run**.

# P1.8-E-R5 Engineering Grasp Sanity Audit

**Status: `engineering_boundary_localized`** (development Evidence only; not Phase-I qualification).

- Authored geometry gives 28.75 mm principal-pad zero gap and 31.75 mm auxiliary-pad zero gap for the 31.75 mm handle; a practical geometric band is about 29–33 mm.
- The current MuJoCo 10.63 mm fallback state has deep pad/handle and mesh/handle overlap: 9.328 mm principal-pad, 10.774 mm auxiliary-pad, and 3.198 mm finger-mesh maximum penetration in a static reconstruction.
- The prior ~80 mm M1 load is finger pad boxes contacting Nut outer-frame geom `SquareNut_collision_3`, not the handle `SquareNut_collision_4`.
- The historical 0.1 kg MuJoCo force-25 configuration was reproduced on MuJoCo 3.8.1: stable mechanical fallback at 6.12 s and 97.338 mm Nut lift. Historical and current authorization openings/forces are nearly equal; rates, planner/controller versions, and Nut-to-EE pose differ.
- The all-five-pad-only fixture did not pass retention: GeoPhys did not authorize; MuJoCo authorized at 1.14 s and then failed verify-lift.
- No production, R1/PickCube, persistent R3, planner, task semantics, mass, thresholds, or simulator source was changed. No simulator-dynamics modification is justified.
- Six hand-camera videos are indexed in `engineering_grasp_audit/media_manifest.json`; textual reports contain no media embeddings.

Detailed text-only report: `engineering_grasp_audit/engineering_grasp_report.md`. See `engineering_grasp_audit/engineering_decision.json`, `grasp_geometry.json`, `historical_mujoco/golden_grasp_state.json`, and `old_vs_current.json`. T1, full task, D0–D2, SAPIEN, and Genesis were not run.
