# Phase I progress summary and v1.0 scope crosswalk

Snapshot date: 2026-10-14. This is a dated v1.0 crosswalk. The original Phase I blueprint and its dated reports remain unchanged as historical plans and results.

| Phase | Core implementation and owner | Verified intersection and evidence | Qualification status |
|---|---|---|---|
| P1.0 | Repository provenance, architecture baseline, and evidence governance; Geochora repository/Core | Historical baseline decision and provenance records; see the evidence index | APPROVED_BOUNDED; not a universal runtime claim |
| P1.1 | Task Artifact v0, task contracts, and capability admission in task_env | Provider-free contract detector and the original bounded P1.1 decision | APPROVED_BOUNDED |
| P1.2 | Single-environment runtime construction, reset, and step lifecycle in task_env | GeoPhys and MuJoCo CPU bounded PickCube reset/step route; original decision preserved | APPROVED_BOUNDED |
| P1.3 | Provider conformance probes in task_env diagnostics | Five declared primary-provider probes; the result does not cover every provider capability | APPROVED_BOUNDED |
| P1.4 | Canonical camera geometry and sensor metadata in task_env | Declared GeoPhys/MuJoCo camera geometry, depth, and timestamp contract | APPROVED_BOUNDED |
| P1.5 | PickCube R1 control, replay, and expert route in task_env | Frozen seeds 31 and 73 and the historical PickCube acceptance package | APPROVED_BOUNDED; not every task or provider |
| P1.6 | Flow state-policy training, frozen V2a checkpoint, and D3 evaluation in task_env | PickCube, 100 Hz, Flow_Vanilla/ConditionalUnet1D V2a FINAL step 15000, 26D state, h50/a36; GeoPhys and MuJoCo D3 each 20/20. Checkpoint, selected dataset manifest, resolved config, and all 441 recovery-archive members were hash-verified on the local host. | APPROVED_BOUNDED; no universal learner or provider approval |
| P1.7 | Camera observation exists in Core, but the complete visual-observation-to-policy route is not qualified | No current-HEAD camera-policy full route and no accepted visuomotor evaluation set | DEFERRED |
| P1.8 infrastructure | Integer/native timebase, owner snapshots, R3 controller integration, canonical solution lifecycle, guarded transitions, v0/v2 recorder, streaming H5, and replay preparation in task_env | Current candidate contract/replay test suite: 66/66 passed. The declared tests cover lifecycle, guards, diagnostic isolation, replay contracts, and streaming recorder behavior. | IMPLEMENTED_AND_TESTED_IN_DECLARED_SCOPE; no P1.8 formal qualification |
| P1.8 MuJoCo NutAssembly | V5 guarded candidate, NoSlip2 profile, 0.002 s physics step and 500 Hz gripper feedback | Historical same-provider FULL Expert and D0/D1/D2 development results at 20/50/100/500 Hz; evidence is tied to recorded candidate/source identities and is not a new current-HEAD qualification | DEVELOPMENT_ONLY; formal review pending |
| P1.8 GeoPhys NutAssembly | Same declared task family and guarded candidate path | FULL attempts at 50/100/500 Hz fail the original stable-height gate. A separate shadow-executed authored trajectory reaches raw insertion/release/task-success predicates, but lifecycle FULL completion is invalid. GeoPhys-source diagnostic D1/D2 execution is valid; representative D0 at 50 Hz first diverges at transition 157. | PARTIAL / FAILED_EXACT_RECONSTRUCTION; formal qualification not granted |
| P1.8 cross-provider replay | Diagnostic replay runner in task_env | GeoPhys-source D1 and frozen-action diagnostic D2 were exercised on GeoPhys and MuJoCo at the declared 50/100/500 Hz source rates. Execution validity, task predicates, and expert completion remain separate outputs. | DIAGNOSTIC_ONLY; not formal cross-provider D1/D2 |

## P1.8 contract details

The versioned alternative close guard is 8 N; the physical force target and cap remain 10 N. The 2 mm Nut-to-EE drift value is a research target. The 8 mm capture limit is the hard physical bound. The older frozen task/controller/solver semantics are not retroactively changed by this release.

In the GeoPhys shadow run, the original Expert route records stable_height_mismatch. The raw insertion and release predicates becoming true later do not repair that failure: task_success, expert_complete, terminated, truncated, stream_execution_valid, and formal_qualified are distinct facts. The diagnostic shadow stays opt-in.

## Scope decision

The release accepts the scoped Phase I Core baseline. P1.7, formal P1.8 GeoPhys FULL/D0, symmetric cross-provider formal replay, and bounded provider gaps move to non-blocking follow-up tracks. The original Phase I blueprint remains incomplete.
