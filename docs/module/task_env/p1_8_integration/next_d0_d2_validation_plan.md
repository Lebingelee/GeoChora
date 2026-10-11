# Next GeoPhys/MuJoCo validation plan — NOT EXECUTED

## Ordered prerequisites

Human Review of integration and residual auxiliary-pad penetration first. Freeze source hashes, profile, artifact/ResetSample/recipe identities, environment packages and explicit equal-rate realization. Canonical main remains public/main.

1. GeoPhys 10N closed-loop G0 at 500/100/50; rerun MuJoCo same cells. Old GeoPhys 30N results are not 10N evidence. Existing integration entry accepts --provider geophys. Fail any cell: stop expansion, preserve first violated predicate; do not retune to force a qualification pass.
2. Loaded T1 and full NutAssembly expert for both providers x three rates, under separately authorized campaign. Current candidate has only close + verify competence; no full-task claim or ready golden exists.
3. Only successful full experts may become six frozen goldens. Then D0 6, symmetric D1 12, symmetric D2 12. Boundary providers are a later independent campaign, not implied passes.

G0 oracle: actual preclose stability exact current definition; close_ready >= target-deadband with contiguous 0.1s, <=1.5s authorization; force cap10N; post-authorization regulated hold0.1s; lift actual authorization Z+100mm; capture translation <=8mm and rotation <=0.15rad with original baseline; no forced lift or fallback. T1 endpoints <=7mm/0.06rad continuous0.1s, original capture bounds. Full task must reach original canonical task_success, including insertion/release. Timeouts, task semantics, mass, thresholds frozen.

## History and ownership

| Data | Owner | Current recording | Needed for exact replay |
|---|---|---|---|
| actual joints/poses/control_step/time | CanonicalStateView | ordinary boundaries | retain as contract |
| opening/closing force | ControlFeedback | ordinary and inner trace | retain feedback with boundary alignment |
| force mode/commanded opening | ControllerMemory | existing memory() | full initialization/restore or reconstruct from reset prefix |
| q_ref/previous requested rotation/position/expected step | R3 | persistent_state_mapping diagnostics | versioned owner snapshot+restore, or reset-prefix sequential reconstruction |
| locked arm target/last target | hold adapter | arm diagnostics | serialize lock state/target and update ordering |
| equal-rate inner cadence | cadence owner | counters + inner diagnostic rows | last outer step, held gripper target, effective dt, update ordering |
| stability history/start | EE window | events + extracted to_mapping | full sample history and exact boundary sampling |
| close-ready ticks/deadline/postclose hold | coordinator | events/stage diagnostics | stage/index/emitted/holds/stable ticks, gate start, hold ticks |
| capture baseline | task coordinator | lift trace/plan state | persist pre-hold Nut/EE relative baseline; never replace after hold |
| actions + all hold transitions | CanonicalTrajectory | R5 JSON only currently | recorder adapter with T+1/T and explicit hold provenance |
| inner canonical actuator targets | interval realization | diagnostic substep trace | complete provider-neutral CanonicalControlTarget/Applied stream with substep dt |

## Current gap and minimal proposed change

Existing BoundaryRecord has no controller/coordinator snapshot and TransitionRecord records one target per boundary. D1 cannot reproduce an adaptive inner servo merely by holding the final interval target. The R5 worker currently writes JSON diagnostics; it is not a new replay-qualified recorder. CanonicalTrajectory's interval clock check is one-ULP, while step_control_interval uses cumulative binary64 additions with an audited accumulated-roundoff bound. This needs a contract-consistent representation before recording these goldens.

Propose an additive versioned episode execution recipe plus per-transition canonical interval target stream (substep count, physics dt, ordered canonical targets/applied acknowledgments). Keep v0 readers/legacy step unchanged. For checkpoint replay add versioned controller+coordinator owner snapshots at boundaries; for reset-to-end D0/D2 reconstruct history sequentially from reset/actions/feedback and explicit hold/stage metadata. Test snapshot restore equivalence before any resumed replay claim. No native contacts/solver state enter these fields. Contact logs remain diagnostic sidecars.

Do not implement an unreviewed state contract in this consolidation. D0–D2 runner migration is a prerequisite deliverable of the next campaign, not a promised ready CLI today. Existing nominal worker routes remain historical and must not be used to bypass the stable coordinator.

## Oracles and tolerances

D0: exact action interpretation, canonical targets, readiness and memory sequence from canonical recorded history; source/provenance identities exact. Any first divergence fails, not final success only.
D1: exact input target stream identity and T+1/T/native-substep/timebase execution validity; task validity separately canonical success. Provider responses need not match numerically across engines.
D2: same frozen controller/cadence/coordinator semantics from public actions and live canonical state/feedback, no replanning. Execution identity/ordering exact; independently task-valid. Capture/pose thresholds are original physical limits, not a new cross-engine state-distance tolerance.
Clock bounds must be mathematically derived binary64 representation bounds, recorded explicitly; do not use a broad numerical tolerance to mask skipped control steps. Any non-bitwise reorganization requires first divergence plus bound before acceptance.

## Evidence and failure handling

Fresh workspace/qualification/phase1/p1_8_integration_d0_d2/{provenance,g0,t1,expert,golden,d0,d1,d2,precision,controller_state,acceptance}. Store manifest/source lock and package versions before physics. Preserve unsuccessful trajectories; first failure includes boundary, stage, expected/actual predicate, target/state/memory difference and native diagnostics separately. No behavioral fixes after lock; invalidate and repeat prerequisites if behavior changes.

SAPIEN/Genesis: retain provider-neutral API, pin exact packages, establish separate G0/T1/expert/replay evidence after primary acceptance. Phase I is not closed and P1.6/P1.7 remain unwaived.
