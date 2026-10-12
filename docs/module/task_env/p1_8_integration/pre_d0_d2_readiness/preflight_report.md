# P1.8 Pre-D0–D2 readiness

## Decision: NO-GO

Infrastructure: NO-GO. Campaign: BLOCKED. This is preparation, not D0–D2 or full-task qualification.

Start ff46c7822708d43f682e983b2b0ab30589545ef7; source prototype commit dd2258622f6c0ebd46774109730029e2f4aea8d3; same codex/p1.8-integration. Clean start. main remains f977528b9b9866c50afcf8ea9b5f5deadce60892; public/integration remains ff46c7822708d43f682e983b2b0ab30589545ef7; no push.

## Passed

- 30 provider-free contract checks
- MuJoCo G0 3/3
- Fresh 4550-boundary physical exact regression against independent archive
- R1/R3/planner/runtime/profile source preservation
- PickCube archived v0 H5 exact roundtrip 1091/1092
- Opt-in canonical owner checkpoint synthetic tests
- All real interval canonical targets reconstructed exactly
- Native substep counts and derived clock bounds validated
- Nine synthetic negative cases reject
- 3576 original archive hashes verified
- 10 selected historical experiment entries source/CLI restored

## Blocking

- GeoPhys G0 3/3 stable_height_mismatch before closing
- Raw GeoPhys TB100/TB50 boundary clocks rejected by existing v0 one-ULP invariant
- No live R5 CanonicalTrajectory recorder incorporating owner checkpoints and interval recipe

## Not exercised

- Real boundary-checkpoint restore-next-target across complete live coordinator lifecycle
- T1 loaded tracking
- Full NutAssembly experts
- Six successful source goldens
- Formal D0/D1/D2
- SAPIEN/Genesis current candidate
- Recovered video pixel decoding (container integrity only)

Only two diagnostic modules added, no production arm/gripper/planner/geometry/physics change. Four provider source implementations preserved; SAPIEN/Genesis packages unavailable here and not installed for this audit. Fail-closed admission contract tests retained. Auxiliary-pad penetration1.7–2.0mm, single reset envelope and local-only archive remain explicit risks. Source/lock JSON is a prequalification candidate freeze, not qualification approval. Human decisions and ordered next actions: readiness_decision.json.
