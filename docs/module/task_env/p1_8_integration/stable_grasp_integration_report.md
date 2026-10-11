# 10 N stable grasp integration

## Scope and disposition

Preserved opt-in development candidate. MuJoCo 3.8.1, NA-S0 seed 19, 0.1 kg Nut, equal outer/gripper rates only. No formal NutAssembly qualification decision changes.

`stable_grasp_reference.py` is the byte-preserved reference from checkpoint 8e914da. `stable_grasp_candidate.py` composes extracted canonical boundary owners. Legacy nominal solutions and PickCube routes are unchanged.

## Preserved sequence

1. Original cubic/SLERP move to task-local grasp offset Z = 44.895 mm.
2. Hold achieved arm servo target; wait at least 0.5 s. Last 0.2 s uses samples at t >= now - 0.2 - 1e-8, minimum ceil(window/dt - 1e-10) samples. Per-axis position `ptp` <= 0.1 mm; every adjacent-position Euclidean speed <= 2 mm/s. No replacement by vector-span norm or joint velocity.
3. Close reference is actual stable canonical EE pose; same arm desired/servo target is held. R3 persistent q_ref is preserved, not reset; integrated provisional arm target is discarded while held.
4. Only controller_close_ready plus existing pose/canonical grasp gate continuously for 0.1 s authorizes. Canonical grasped_nut remains a weak geometric proxy; it is not bilateral contact evidence. No fallback/bypass.
5. Hold arm + force-regulated gripper for another 0.1 s, distinct from readiness window.
6. Resume persistent R3 tracking. Verify goal actual authorization EE Z + 100 mm. Capture baseline is established at original verify-plan entry before extra hold, not rebased after holding.

Force target and native actuator cap 10 N; deadband 1 N. Gripper cadence equals outer rate. Force regulation still executes during grasp hold. Historical fixed-500Hz inner mode remains separate and unqualified at 10 N.

## Explicit deadline correction

The old worker checked 1.5 s only post hoc, while task-local execution retained max_close_hold_s=8 s. Integration adds 1.5 s fail-closed authorization deadline to the candidate, including before close-plan exhaustion. At the deadline an already completed readiness window can authorize; absent readiness fails closed. This is the requested execution bound, not a fixed-time lift or increased timeout. Legacy timeout/config sources are unchanged. Synthetic negative probe proves no lift at expired deadline.

## Regression

| outer/gripper Hz | authorization s | force N | opening mm | max capture translation mm | max rotation rad | G0 |
|---|---:|---:|---:|---:|---:|---|
| 500/500 | 0.932 | 9.034263 | 28.588315 | 5.339208 | 0.037373682 | PASS |
| 100/100 | 0.930 | 9.038163 | 28.586530 | 5.337382 | 0.037341481 | PASS |
| 50/50 | 0.920 | 9.073366 | 28.568785 | 5.355480 | 0.037207937 | PASS |

Frozen vs integrated physical equality: 3500/3500, 700/700, 350/350 recorded boundaries exactly equal for RequestedAction, arm desired/servo targets, joint achieved state, actual EE, feedback, readiness, R3/gripper memories, simulation time and task metrics. AppliedControl equals after removing target_hash; its actuator cap remains 10 N. New source-based identities differ starting boundary 0; no physical first divergence. This is three development G0 reproductions, not D0/D1/D2 qualification.

## Limitations

Auxiliary-pad penetration approximately 1.7–2.0 mm remains an explicit residual risk. No GeoPhys 10N G0 claim, other reset/pose/object claim, loaded transport/full task/replay/boundary provider claim. No force/mass/friction/geometry tuning in integration.
