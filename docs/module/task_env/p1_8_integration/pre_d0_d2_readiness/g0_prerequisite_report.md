# 10 N G0 prerequisite audit

NA-S0, mass0.1kg, physics dt0.002s, equal-rate canonical gripper. Frozen candidate; no tuning.

| Provider | Hz | authorization s | verify-lift | drift mm/rad | result / first failure |
|---|---:|---:|---|---|---|
| geophys | 500 | NOT REACHED | NOT RUN | NOT MEASURED | nutassembly_solution/stable_height_mismatch |
| geophys | 100 | NOT REACHED | NOT RUN | NOT MEASURED | nutassembly_solution/stable_height_mismatch |
| geophys | 50 | NOT REACHED | NOT RUN | NOT MEASURED | nutassembly_solution/stable_height_mismatch |
| mujoco | 500 | 0.9319999999998978 | True | 5.339208/0.037374 | PASS |
| mujoco | 100 | 0.9300000000000002 | True | 5.337382/0.037341 | PASS |
| mujoco | 50 | 0.9199999999999999 | True | 5.35548/0.037208 | PASS |

GeoPhys passes sampled motion-stability but fails the subsequent stable-height gate before close. Errors: TB500 -0.646013mm, TB100 -0.654835mm, TB50 -0.639039mm. Threshold remains0.1mm. No claim about GeoPhys10N retention is possible. MuJoCo controller-only authorization/readiness0.1s, extra force-regulated hold0.1s, cap10N, original capture baseline and native-count checks pass. Native contact data remain sidecars. Full predicate data: g0_predicate_audit.json. Report fallback_* fields are old diagnostic summaries, not enabled authorization routes. No fallback branch was used.
