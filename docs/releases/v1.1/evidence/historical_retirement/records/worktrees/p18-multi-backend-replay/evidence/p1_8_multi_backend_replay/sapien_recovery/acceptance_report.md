# P1.8 SAPIEN recovery acceptance

**ready_for_human_review**, bounded replay slice only. Human review approval is not created by this package.

## Authority and immutable Evidence

Starting source is 6922a471fdc5ac706ab45ef025e2e5d83597c489. Human explicitly authorizes representation-aware exactness. Existing GeoPhys/MuJoCo/Genesis, golden H5, public-action arrays, source traces, locks and original strict SAPIEN reports are preserved byte-for-byte (historical_inventory.json). Original P1.6 dirty tree remains untouched. No Flow/D3/policy/P1.7/NutAssembly/render qualification.

## Representation versus physics

Independent public timestep calibration uses 0.1, 0.1+2^-30 and 1/73 roundtrips and uniquely discriminates binary32 from binary64, failing closed on unknown/ambiguous representation. requested_dt=.002, native_dt=0.0020000000949949026, expected_native_dt=float32(.002)=same raw readback. Exact equality passes. Wrong native timestep remains rejected. No authored value is substituted into raw facts. Original strict P1.3 evaluator still reports native_dt=false, independently retained inside every new report; all other approved physical/geometric gates pass unchanged for Asset/Frame, Free-fall, Joint-tracking and Contact. Physical tolerances/oracle are untouched.

Canonical time is completed integer control boundaries * TaskArtifact.control_dt, with native substep-count alignment and native timestep admission verified. Every replay boundary matches canonical step*.002 exactly. Raw provider elapsed can be reconstructed from completed substeps and raw native_dt, intentionally separate from canonical time. This follows Human authorization rather than silently recategorizing old P1.3 time semantics.

## Source/runtime boundary

Generic provider adapter compiles unchanged shared MJCF authoring defaults using MuJoCo public source compiler, not MuJoCo runtime/state truth. SAPIEN public actor/articulation APIs consume body/joint/site transforms, collision geometry, mass/inertia, semantic names, limits, armature and actuator source facts. Geometry cooking loss rejects; source geometry is not reauthored in task code. No task-ID branches, native ID public values, rendering or hidden settle. Native joint equality maps through disclosed public mimic tendon default (approximate constraint translation).

Reset/repeat/joint velocity/semantic-state/one-step checks pass. Joint reset max_abs=5.241394052113435e-08, cube position=6.637928096075996e-09m, quaternion=0 within existing reset bounds. Measured opening and public accepted closing-direction generalized actuator force are projected at the same canonical boundary; no force inferred from cube motion. Negative admission rejects all providers before construction.

## Preserved implementation failures and bounded correction

P0 attempt0 found tendon length was incorrectly used as canonical opening (tendon coefficient .5). Adapter projection fix1 uses summed named finger joint positions; production controller is untouched. Failed report and exact adapter bytes are preserved.

First replay uses explicit sampled source PD force for arm and tendon. All four cells execute validly; seed73 succeeds, seed31 D1/D2 lifts .079116/.092621m. Stage-wise evidence shows pre-contact arm tracking divergence and final EE height deficit. One localized provider actuator correction maps arm source PD gains and force bounds to public implicit PhysX joint drives, with source gains unchanged. Fixed tendon retains measured public generalized force application/readback. No controller gain/contact/solver/tolerance/trajectory/action/seed change. Initial failed traces and source bytes are retained. Separate actuator_fix1 spec/source lock documents changed implementation while evaluation inputs remain identical; original locks are not modified.

## Final governed replay

D1 directly accepts all 716/445 stored targets, exact hashes unchanged. D2 uses the same frozen public absolute_joint sequence and fresh unchanged production controller/current canonical state+feedback, with no expert/planner/policy. All four SAPIEN cells execution-valid/task-valid, reached >=.10m and final state remains successful. Final/max lifts: D1 seed31 .104410875, seed73 .104381967; D2 seed31 .104692388, seed73 .104701627. Current source matches actuator_fix1 lock, first execution occurs after lock. The combined matrix includes preserved twelve lower-provider passing cells, for sixteen PASS cells total.

## Regression and claim boundary

Bounded GeoPhys/MuJoCo/Genesis lifecycle/reset/repeat/time/open-close spot-checks pass. P1.1 30 checks, fresh provider-free import and missing-control-capability rejection pass. Frozen lower-phase source hashes, all prior Evidence hashes and golden hashes remain unchanged. No full lower-phase replay/render campaign is rerun. See integrity_checks.json and replay_matrix.md.

Allowed claim only: SAPIEN joins GeoPhys, MuJoCo, and Genesis in the bounded P1.8 PickCube D1/D2 replay matrix for seeds31/73. This does not close full P1.8 canonical scope, Phase I, or waive P1.6/P1.7. Approximate native constraint/contact mapping and source/dependency packaging remain residual risks. No provider-wide qualification or physics equivalence is claimed.
