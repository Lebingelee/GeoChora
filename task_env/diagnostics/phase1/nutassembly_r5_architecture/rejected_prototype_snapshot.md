# Preserved R5 rejected achieved-state prototype

This note records the R5 prototype immediately before the same-branch persistent-reference continuation. Source is preserved in commit `0f2290c9b25e590da04be82a74b0aea8b005735a`'s parent plus the current checkpoint commit; the previous run's full evidence remains under the ignored-but-preserved workspace path below.

- Branch: `codex/p1.8-e-r5-controller-architecture`
- Pre-checkpoint HEAD: `0f2290c9b25e590da04be82a74b0aea8b005735a`
- Status: `architecture_candidate_rejected`
- Controller: `ProductionCanonicalPandaControllerR3`, achieved-state rebase law `q_ref = q_actual + qdot * control_dt`
- Controller source SHA-256: `8babb8ed0bcb829e46a17eedec827f3c9aab8dd4284b7908c7590c17ff857dec`
- R1 source SHA-256: `715d78a6339a4b18f6517b2a9a2eee71bc9e2c6cfcf05723d50adae4059754f3`
- C11 profile SHA-256: `5bbac0ad315c07a1ced354ccee845acf92ae50ab1a125255d6af486c83d4c266`
- Failed cell: GeoPhys/TB500, first T0 vertical endpoint; planned 3.244 s plus 3.0 s readiness hold; endpoint position miss about 193.9 mm.
- Like-for-like first 1,622 planned-boundary comparison is in the prior `architecture_comparison.md` and `r4_c11_reference.json`.
- Prior report, trace, audit, and handoff: `workspace/qualification/phase1/p1_8_nutassembly_r5_architecture/`.
- R4 Evidence root was not modified. No G0, T1, full task, replay, or boundary-provider test was run.

This snapshot is diagnostic provenance only. It is not a qualification claim. The persistent-reference continuation changes only R3 reference state and adds its diagnostics; this baseline remains available in git history.
