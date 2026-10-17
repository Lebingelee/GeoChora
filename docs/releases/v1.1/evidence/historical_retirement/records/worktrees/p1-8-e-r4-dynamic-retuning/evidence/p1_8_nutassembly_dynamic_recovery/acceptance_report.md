# P1.8-E-R4 Acceptance Status — through C11

**partial_with_localized_failure**

## Decision

C11 establishes T0 endpoint readiness on both primary providers at all three rates (6/6). G0 passes on GeoPhys at all rates and fails on MuJoCo at all rates (3/6 overall). T1 was not run because the ordered G0 gate did not pass. No dynamic profile lock, primary acceptance lock, full NutAssembly expert, D0–D2, regression, or boundary-provider qualification was produced.

The current failure boundary is **shared gripper force acquisition/retention across provider/rate realizations**. The most localized failure is MuJoCo/TB50: closing force plateaus at approximately 2.42 N after the target reaches zero opening, leaving the force-readiness predicate false. MuJoCo/TB500 and TB100 pass verify-lift but miss the 1.0 s close target; TB100 additionally exceeds the capture translation bound by 0.226 mm.

The T0 gate is endpoint-based and passes all five endpoints in each cell. However, TB500 path-wide tracking peaks at 43.4 mm and 0.283 rad, while its maximum stable-window endpoint errors are 6.922 mm and 0.05956 rad. This transient tracking result should be addressed before claiming rate-equivalent trajectory tracking.

## Locks and profiles

- `dynamic_profile.yaml` is a copy of candidate C11 for reproducibility. It is **provisional and unlocked**.
- `dynamic_profile_lock.json` was not created.
- `primary_dynamic_acceptance_lock.json` was not created.
- The Nut asset remains 0.1 kg with the original inertia and frozen contact profile.
- Force target 30 N, deadband 1 N, fallback 25 N, 0.5 mm opening-span limit, 0.1 s fallback window, mandatory verify-lift, and readiness timeouts were unchanged.
- R1 source hash remains `715d78a6339a4b18f6517b2a9a2eee71bc9e2c6cfcf05723d50adae4059754f3`; R2 was added at source hash `22c3e0d2a2d0ec3f0fc89fd0fabe215d195a59d7ade0091b68bfd6244b7e8a93`.

## Qualification matrix

| Gate | Required | Result |
|---|---:|---|
| T0 unloaded | 6 | 6 PASS |
| G0 closure + verify-lift | 6 | 3 PASS / 3 FAIL |
| T1 loaded | 6 | NOT RUN |
| Full expert | 6 | NOT RUN |
| D0 | 6 | NOT RUN |
| D1 | 12 | NOT RUN |
| D2 | 12 | NOT RUN |
| SAPIEN / Genesis tracking and expert | — | NOT ENTERED |

No primary-provider nominal NutAssembly approval is claimed. P1.6/P1.7 are not waived and Phase I is not closed.
