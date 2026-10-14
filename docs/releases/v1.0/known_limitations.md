# Known limitations

## Phase I qualification

- The original Phase I blueprint is not complete. This v1.0 scope is a Core baseline release, not Phase I closure.
- P1.7 remains DEFERRED. No camera-policy full route or visuomotor qualification is claimed.
- P1.8 has no formal NutAssembly FULL or cross-provider D0/D1/D2 qualification. The candidate acceptance contract still records Human review as pending.
- MuJoCo 20/50/100/500 Hz FULL and same-provider D0/D1/D2 results are development evidence tied to their recorded source identities.
- GeoPhys FULL attempts at 50/100/500 Hz retain the stable_height_mismatch failure. Later shadow success predicates do not make the original expert lifecycle valid.
- GeoPhys D0 at 50 Hz is partial/invalid for exact reconstruction: first divergence is transition 157. GeoPhys D0 at 100/500 Hz was not run. The 500 Hz source has a recorded reporting-source provenance limitation.
- GeoPhys-source D1/D2 outcomes are diagnostic. Diagnostic D2 is not formal Canonical Solution D2. Cross-provider physical equality is not claimed.
- 20 Hz is outside the final loaded-episode GeoPhys diagnostic replay runner admission. Historical MuJoCo 20 Hz development evidence is a separate source record.
- SAPIEN and Genesis adapter/development evidence is limited to recorded intersections. No provider-wide support is claimed; those packages were not installed in the current geochora environment used for the release regression.

## Historical boundaries

- P1.6 remains the bounded PickCube V2a result described in the progress summary. It is not a universal policy or provider approval.
- The P1.6 recovery tar and P1.8 archive are local-only. Their hashes and restore checks are recorded, but off-host backup was not verified.
- GeoPhys native contact-checkpoint resume is not claimed bitwise.
- Historical source profiles, failures, and archive anomalies remain preserved as dated evidence; their presence does not qualify the current candidate.

## Current PickCube smoke

The current-HEAD physical PickCube smoke completed with task_success true after 93 transitions on GeoPhys Taichi CPU. The MJCF import retained one extension.light semantic with a warning and rejected none. This smoke did not exercise camera rendering, and no rendering support claim follows from it.
