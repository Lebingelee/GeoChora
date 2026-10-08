# P1.8-E-R5 Persistent-Reference Continuation

Status: `persistent_reference_supported` for the experimental arm architecture.
The result is development Evidence, not Phase-I qualification.

## Provenance

- Branch: `codex/p1.8-e-r5-controller-architecture` (no new branch/worktree).
- Rejected achieved-state prototype checkpoint: `7e8c1e042d5156ef87bcdba20ad141426747ce14`.
- Persistent-reference implementation: `9332fbe`.
- Controller: `canonical-panda-production-r3-persistent-reference-v1`.
- Controller source SHA-256: `8805f0f3b6e5497871269888d876216baef96bfa7e5fabc8f3e0eef93e1152b5`.
- R1 source SHA-256 remains `715d78a6339a4b18f6517b2a9a2eee71bc9e2c6cfcf05723d50adae4059754f3`.

## Results

- The first GeoPhys/TB500 vertical segment passed endpoint readiness at 3.344 s. At plan exhaustion, position/rotation errors were 0.766 mm / 0.000064 rad.
- First-segment position RMS was 17.127 mm for C11, 134.443 mm for rejected achieved-state R3, and 1.546 mm for persistent-reference R3. Persistent R3's maximum reference lead was 0.03223 rad, with no lead clamp or actuator saturation.
- Full GeoPhys/TB500 T0 passed all five endpoints. Six-cell T0 passed 6/6 across GeoPhys/MuJoCo and TB500/TB100/TB50.
- Fixed-rate gripper G0 passed 3/6: GeoPhys passed all three rates; MuJoCo reached stable fallback at all rates but exceeded the 1.0 s close limit and failed verify-lift with approximately 0.306 m capture drift.
- MuJoCo/TB50 classification is `contact_acquired_then_lost`. Native finger/Nut contacts persisted through the close authorization sample. The zero-opening command saturated after load was present; force later fell below 1 N during verify-lift, and the Nut remained at table height. Native contacts were not sampled during lift, so the exact loss instant is unavailable.

## Limits

One audit-only correction widened the cumulative binary64 interval-time bound after a TB100 audit false positive; simulation/controller behavior was unchanged. No gain sweep, planner tuning, gripper-rate tuning, threshold change, provider-specific tuning, T1, full task, D0-D2, SAPIEN, or Genesis run occurred. R4 Evidence was not modified.

The detailed reports and traces remain in the repository's ignored Experiment workspace:
`workspace/qualification/phase1/p1_8_nutassembly_r5_architecture/`.
See its `acceptance_report.md`, `architecture_comparison.md`, and
`evidence_index.json` for the complete tables and artifact paths.
