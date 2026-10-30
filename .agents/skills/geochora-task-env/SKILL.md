---
name: geochora-task-env
description: "Use GeoChora TaskEnv public construction, expert execution, recording and evaluation routes, or locate their owners before proposing a change; apply to current task/provider workflows."
---

# TaskEnv Module Skill

Read repository `AGENTS.md` and [module README](../../../docs/module/task_env/README.md).
`task_env/` is the sole Core owner; use its public APIs. No historical chat context is required.
For the source/contract/test map read [routes](references/routes.md) when implementing a workflow or diagnosing a gap.

## Static Logical Assembly values

R01a exposes `LogicalAssemblyV1`, `LogicalAssemblyEntityMemberV1`,
`LogicalAssemblySubcomponentReferenceV1`, `LogicalAssemblyNestedMemberV1`, and
`decode_logical_assembly` from `task_env.artifacts`. Use these values only for
an immutable, versioned logical contract pinned to an existing Scene identity.
Entity members describe logical ownership; subcomponent members are typed
reference-only views; nested members pin an exact child revision and digest.
The codec alone does not check Scene/child existence or recursively resolve
ownership.

R01b adds advanced `resolve_logical_assembly(root, scene, child_assemblies)`
from the same artifacts owner. It validates the exact Scene pin, reachable
child revision/content hashes, Entity/Asset identities, and typed
Frame/Joint/Actuator/ControlGroup targets, then returns immutable
`ResolvedLogicalAssemblyV1` leaves with canonical segment-tuple paths and
source Assembly provenance. Reference-only leaves do not create owners or
writers. The fail-closed limits are root depth 1 / maximum 32 Assembly levels
and 1024 expanded leaves. Resolution is provider-free and stateless; it does
not project Task Source, create native names/indices, attach bodies, or admit a
Runtime. R01c and R03 remain separate gates. See the executable minimal
example in [Public API](../../../docs/module/task_env/public-api.md#bounded-logical-assembly-resolution-r01b).
This static contract does not change selected runtime routes or their supported
capability envelope.

## USD delivery and representation selection (F02)

Use the `task_env.artifacts` strict `UsdAssetDeliveryV1` / `UsdValidationReportV1`
values with `task_env.assembly.load_usd_asset_delivery()` and
`resolve_provider_representation()` for byte-bound USD source intake. Preserve
the original `AssetDefinition`; keep entry bytes, all-authored-branch closure,
delivery mapping, and report hashes distinct. Synthetic fixtures require an
explicit test opt-in and never establish upstream verification. The resolver
separates format matching, verified-source status, representation preparation,
and runtime admission. It does not connect USD to MJCF-only `RuntimeSource` or
admit Isaac, GeoPhys, or MuJoCo execution. Entry layers may be nested below the
delivery root, and authored `../` arcs are valid only when every resolved file
stays inside that root. The inspected MuJoCo 3.8.1 decoder rejection is bound to
its exact library hash; other MuJoCo build identities remain unverified. Isaac
and GeoPhys selection indicates source representation preparation only, not
runtime compatibility for an arbitrary build. F02 attempt002 has Sol acceptance
`ACCEPTED_BOUNDED_F02` for this source-contract/fixture scope; actual validated Panda
delivery and provider runtime admission remain unverified. See the [F02 public API route](../../../docs/module/task_env/public-api.md#usd-delivery-and-provider-representation-selection-f02)
and the detailed [source map](references/routes.md).

## F03 Core source/state/control status (2026-10-29)

The existing Assembly source owner exposes internal `UsdTaskSceneSourceV1` plus
an owned snapshot lease copied from the exact immutable F02 loaded-delivery
bytes. `UsdRuntimeSourceV1` binds the delivery, `TaskArtifactV1`, canonical
Scene/TaskSource identities, reset pose/free Joint maps, body/Frame bindings
and named scalar drive targets. This is a construction declaration, not by
itself Provider admission. Production `RuntimeSession.materialize()` rejects
synthetic or unverified USD. F04 attempt001 initially had only an adapter/source
candidate; attempt002 adds a separate, exact-sample `local-validated` route
described below. A local report does not establish F02 `upstream-validated`
provenance. Do not pass synthetic source onward as runtime evidence.

`legacy_execution_projection()` preserves the exact old `ExecutionSpec`
mapping. It projects `ExecutionSpecV1` only when all choices are representable
by the selected legacy adapter; Isaac/device choices, camera overrides, and
nonlegacy renderer selections fail closed. New typed free-body adapters may
return `PublicRigidBodyReadbackV1`, explicitly naming world velocity and COM
reference. The shared projection converts to body-origin local velocity and
checks agreement with the measured child Frame; the existing MuJoCo-compatible
tuple path remains intact. `IsaacNamedPositionDriveReceiptV1` is marked
`synthetic_fixture`, maps the exact seven Panda Arm and two Finger DOFs by
public names/metadata order, and splits aggregate hand opening in metres
between fingers. The F04 candidate can compile a `native_runtime` receipt only
from actual public articulation names, limits, device and build metadata after
the native view exists. Neither receipt alone admits a Provider or establishes
qualification.

F03 attempt001 is the historical partial contract result. Attempt002 adds an
explicit versioned `make_env()` opt-in and exercised the existing Core reset,
typed state, Position control, public step, Generic H5 v3 Recorder/finalizer,
independent reader and close owners through a private synthetic
`NativeRuntimeIOV1` implementation. Two same-Env episodes each produced a
closed T=4/T+1=5 H5. Its independent reader initially checked only the T
transition-source boundaries while reporting T+1 rows verified.

Attempt003 reproduced acceptance after changing only the final H5 boundary
digest. Generic H5 v3 and the old ABI remain unchanged. Two new synthetic
episodes were recorded through the existing Core chain with a sidecar captured
from public reset/step observation and info returns. The independent F03
reader checks every T+1 typed boundary and observation row, transition source
boundary, episode-end/outcome, final successful advance and publication clock.
It verifies 10/10 rows across two H5 files and rejects the original eight
tamper classes plus seven end-boundary/observation cases. Exact old R02c/R03c
compatibility node IDs pass under Core Python's MuJoCo 3.8.1, with collection
allowlist and zero-native import/launcher tripwires enabled; the old mixed
environment failures remain retained evidence.

Sol reviewed and accepted attempt003 as `ACCEPTED_BOUNDED_F03_S1`, limited to
the synthetic-I/O Core route and final-boundary reader. This remains synthetic
Core S1 evidence only. The private S1 context does not change production
admission: `materialize()` still rejects synthetic or unverified USD. F04
attempt001 adds an adapter candidate, but no validated Panda delivery has
passed source admission. Do not report Isaac provider admission, native
execution, S2/S3 or Qualification. Attempt002's ancillary legacy test run
accidentally executed three public steps on the real CPU Pendulum route,
outside its zero-physics scope; preserve this historical deviation for Sol
review; those steps are not F03 acceptance evidence. Attempt003 itself started
no native runtime or physics. See the [F03
attempt003 closure](../../../docs/module/task_env/goal/Phase_II_01/10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md#f03-attempt003-final-boundary-closure),
[attempt002 result](../../../docs/module/task_env/goal/Phase_II_01/10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md#f03-attempt002-real-core-call-chain),
the [public API boundaries](../../../docs/module/task_env/public-api.md#f03-versioned-usd-source-typed-free-state-and-bounded-admission),
and the [historical attempt001 record](../../../docs/module/task_env/goal/Phase_II_01/10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md#f03-attempt001-contract-implementation-and-s1).

## F04 Isaac Core adapter and bounded two-source evidence (accepted route: 2026-10-30)

F04 attempt001 is a historical source/adapter candidate only; see its dated plan
record. Attempt002 added `UsdLocalValidationReportV1` and
`UsdAssetDeliveryLocalV1` as separate versioned owners for the two fixed derived
Panda samples. These values bind the original source inventory and variants,
derived output closure, recipe/options, checker and report bytes. Their
`local-validated` provenance is distinct from F02 `upstream-validated` and
`synthetic_fixture`; it never sets the upstream `source_verified` bit. Runtime
admission is limited to the exact frozen official-Panda and Menagerie-Panda
sample recipes and execution profile.

The existing Core RuntimeSession, native-I/O seam, Position control, public Env,
Recorder and reader were exercised. Provider-free S1 passed 20/20 exact node IDs
with zero Kit/native starts. The CUDA/GPU PhysX worker ran both sources at Isaac
Sim 6.2.0.0, CUDA `cuda:0`, state-only, `best_effort`, 100 Hz and five 2 ms
substeps. Each source produced two 100-transition/101-observation closed H5s;
each interval advanced five physics steps. The independent diagnostic readback
verified 404/404 boundary/observation rows and rejected 40/40 tamper cases.

Historical attempt002 remains `F04_PARTIAL_PENDING_SOL_REVIEW`: all four episodes missed
the frozen gripper opening-change gate (about 0.00974 m observed vs 0.015 m
required) and source-calibrated FK position/orientation gates (about
0.568–0.611 m and 0.878–0.959 rad error). The free-body drop/settle checks
passed. The original reader also has an exact-float clock comparison that
rejects valid recorded time values; a separate diagnostic reader copy used a
1e-12-second tolerance without editing the original. Do not loosen physical
thresholds or infer a completed qualification from the structural readback.
The worker exited 0, but fast `SimulationApp.close()` shutdown skipped writing
the producer's root aggregate receipt; parent-side reconciliation is separately
labeled and raw receipts remain preserved. No broader Isaac/provider,
Qualification or F05 claim follows. See [F04 attempt002](../../../docs/module/task_env/goal/Phase_II_01/10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md#f04-attempt002-isaac-core-adapter-two-source-native).

F04 attempt003 added the public reset kinematics refresh, worker action-unit
conversion through the existing Core action contract, 1e-12-second reader clock
tolerance, and explicit graceful App-close receipts. Its exact provider-free S1
set passed 29/29. Five combined A/B native runs completed all four episodes but
each parent-observed worker exit was `-11`. The latest run's independent reader
verified all 404 boundary/observation rows, 2,000 substep advances, 40/40
tamper rejections and the frozen physical metrics; because the worker exit was
abnormal, that readback remains diagnostic and is not native acceptance. Current
status is `F04_PARTIAL_NATIVE_WORKER_SIGSEGV_PENDING_SOL_REVIEW`; preserve every
failed run, keep the original thresholds, and do not start F05. Details are in
the [attempt003 closeout](../../../docs/module/task_env/goal/Phase_II_01/10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md#f04-attempt003-execution-candidate).

F04 attempt004's technical gates passed: the exact provider-free list passed 30/30, and one
same-run Isaac Sim 6.2.0.0 CUDA `cuda:0`/GPU PhysX worker exercised the frozen official and
current Menagerie Panda sources through the existing Core route. Four closed H5 files passed
independent T+1 and original physical-gate checks; the same-run parent observed worker exit 0,
process-group completion and lock release. On 2026-10-30 the maintainer supplied the independent
technical review acceptance, and the main window closed G8: the unrelated generic Skill changes
were reviewed/committed separately, a clean tracked HEAD was observed, and the missing forward-copy
was restored byte-for-byte from the intact original package. Status is `ACCEPTED_BOUNDED_F04` for
the exact two deliveries/build/backend/device/profile and controlled-worker exit route. This is
not general Isaac admission or Qualification. See the [final acceptance](../../../docs/module/task_env/goal/Phase_II_01/10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md#f04-sol-acceptance).

The process-scoped App owner calls public `SimulationApp.close()` and records its outcome. Env,
Session and adapter close release their owned resources but never terminate the caller process.
Only the dedicated outer native-worker boundary performs controlled process termination, after
H5/witness/receipt durability, and preserves the actual result code. Do not describe this as
successful natural interpreter/Kit teardown. Preserve attempt003's five `-11` exits and all other
historical failures; at F04 closeout, F05 had not yet started. See the [attempt004 record](../../../docs/module/task_env/goal/Phase_II_01/10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md#f04-attempt004-controlled-exit-two-source-closure).

R01c adds `task_env.assembly.project_logical_assembly_source(root, scene,
child_assemblies, source_receipts=None)`. It always reruns the R01b resolver
from current inputs, then associates each expanded leaf with one existing
Scene Entity, its exact Asset declaration, and the corresponding typed
Frame/Joint/Actuator/ControlGroup definition. ControlGroup actuator resources
come from the Group's declared references. The immutable projection preserves
the source Assembly/path and Scene/Asset declaration identities; source
content hashes and matched historical receipts remain provenance fields, not
fresh byte or closure verification. Use the executable example in [Public
API](../../../docs/module/task_env/public-api.md#logical-assembly-source-declaration-projection-r01c).
This is a static declaration join: it does not lower or attach XML, create
physical entities/native names/indices, call the legacy Provider compiler, or
admit Runtime/materialization/Qualification.

## F05 typed-H5 reader and GeoPhys source boundary (attempt002; pending Sol review)

The tracked F05 diagnostics reader compares every public typed state row with
the stored H5 observation values at the declared float32 storage precision.
Keep its witness sourced from public reset/step results; the independent reader
must not trust producer PASS summaries or fixture-private state. The F05
producer identity distinguishes the requested target build from the actual
GeoPhys checkout/module origin and source bytes. A candidate provider checkout
does not prove the main repository gitlink was executed. The attempt002 result
is partial: official Panda import remains rejected at authored
`maxDepenetrationVelocity=+inf`, and an authored `PhysxMimicJointAPI` retained
in generic source inventory is not evidence of a GeoPhys typed host/solver
consumer. Production USD admission remains fail closed; no physics/native,
S2/S3, Qualification, or F06 follows. Preserve the exact bounded S1 and the
source-consumption limitations in the [F05 result](../../../docs/module/task_env/goal/Phase_II_01/10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md#f05-attempt002-reader-producer-and-source-boundary).

## Static Position leaf contracts (R02a)

`task_env.controllers.canonical` exports advanced provider-free values:
`LeafProfileBindingV1`, `ArmPositionActionV1`/`ArmPositionTargetV1`,
`HandPositionActionV1`/`HandPositionTargetV1`, `LeafApplicationAckV1`,
`LeafRequiredStateV1`, and `HandForceAwareDependencyV1`. Use the exact strict
decoders and `validate_leaf_binding(s)` for typed Scene-v3 and optional resolved
Assembly selector checks. A binding pins Scene/Assembly/member/Entity/Asset,
source closure, profile/action schema, algorithm/config, Provider/build/backend,
timebase, ordered resources, ControlGroup, TCP and Required State; synthetic
fixtures must keep `provenance_kind="synthetic_fixture"`.

Arm Position is seven ordered Panda joint positions in radians. Hand Position
is one aggregate `opening_m` in `[0, 0.08]`; finger positions are measured as
`q1+q2`, with two `[0, 0.04] m` fingers, one fixed 0.5/0.5 tendon, finger
equality, and a single `actuator8`. The legacy normalized adapter is explicit:
`opening_m=0.04*(u+1)` for `u∈[-1,1]`. Its bound candidate mapping is
`ctrl=3187.5*opening_m`, with `[0,255]` ctrlrange; this is static source
metadata, not an executed Core mapping. All v1 leaf state fields remain mandatory
and exactly match the bound profile resources and TCP; optional or extra cross-leaf
requirements are rejected. Position Required State does not ask for force. Force-aware dependencies remain `NOT_ADMITTED`; raw signed force,
canonical closing force, transmission/sign/phase, validity, sequence/revisions,
freshness and Provider/build/backend/cadence are separate required provenance.

Targets and Acks are static contracts. Validate them against the exact binding
and caller-supplied source/application boundary and clock; an Ack is not proof
of native apply, target attainment, or task success. The finite catalog is
`CONTRACT_ONLY / NOT_ADMITTED / NOT_RUN`. The R02a contracts alone do not compile
a plan or create a writer; see the R02b owner below. See the executable value
example in [Public API](../../../docs/module/task_env/public-api.md#position-leaf-contract-values-r02a).

## Effective Position leaf plan and synthetic dispatch (R02b)

The existing canonical Controller owner exports `LeafProfileSectionV1`,
`LeafControlPresetV1`, `LeafProfileOverrideV1`, `EffectiveLeafPlanV1`, and
`compile_effective_leaf_plan()`. A preset stores complete registered Arm/Hand
Position sections by canonical member path. An override replaces one whole
known section; it cannot change profile/action/algorithm or add fields. The
compiler re-resolves current root/Scene/children through R01b and reruns the
R01c source declaration projection before checking the binding, source,
Provider/build/backend/timebase, exact Scene Group/Actuator coverage and
Required State. Effective status is derived from which consumed configurations
differ from base; a no-op override does not change status or effective plan
identity. Force-aware and unknown algorithms remain refused.

The existing RuntimeSession control owner exposes advanced opt-in values and
functions from `task_env.runtime.sessions`: `LeafMaterializationReceiptV1`,
the explicit canonical/native Joint/Actuator/Frame mappings and logical
Tendon-to-native-name mapping,
`prepare_leaf_command()`, `preflight_leaf_control_interval()` and
`dispatch_leaf_control_interval()`. The Arm adapter reuses the legacy absolute
joint limit/correction function. The Hand adapter reuses the existing gripper
opening servo and ctrl conversion, keeping requested metres, servo metres and
native ctrl as separate fields. Never infer native indices from tuple order or
write Hand fingers as two independent actuators.
Receipt validation must cover all `nu` native actuator IDs and ctrl slots; an
extra unowned native actuator is rejected. Writer identities follow the same
Entity-qualified semantic-name rule as R02a. Shared math preserves the legacy
zero-force GripperTarget hold and the canonical controller's final opening
clamp; these do not admit zero physical force limits or Force-aware leaves.

Preflight validates every writer, action, typed state sample, source/config
identity, mapping and evaluation clock before preparing commands or consuming
the source boundary. After all stateless commands are prepared, dispatch applies
each owned patch and verifies its returned Target Ack, steps the outer boundary
once, then validates the next typed publication. Failure after boundary consume
uses the existing `ExecutionFaultV1` latch plus leaf attempted/applied/unknown/
acknowledged progress, the prepared Target/command patches, and every typed apply
result returned before failure; it does not roll back, retry, or publish a transition.
Provider-free S1 uses `synthetic_fixture` receipts only. No real Provider
materialization, SelectedReferenceEnv or Recorder/H5 integration exists in R02b;
do not report split leaves as admitted. R02c is the real execution/recording
gate, and native S2/S3/S4 and Qualification remain separate.

## SelectedReferenceEnv leaf integration (R02c attempts 001–005)

Current bounded route (R02c005, 2026-10-28): explicitly pass
`hand_stiffness_N_per_m=50.0` to the task-owned builder for
SOURCE_CALIBRATED_HAND_50_V1. It composes a complete Hand section override with
Arm gain2.5 or3.0 using the existing effective-plan owner. Omission preserves
legacy2500/preset/plan identities; the original0042500 motion failure remains.
This is the same force-free Position law and source, not force feedback or a
physical5N cap.56 provider-free S1 and actual static preflight passed; one
MuJoCo3.8.1 CPU process completed four64-interval episodes,1280mj_step,
260mj_forward and4reset/materializations. Arm/Hand motion, clock/range/reset,
E3/E4 Arm-only configuration isolation, four real64/65 H5 readbacks and nine
tamper rejections passed. A separate provider-free process reread the four
closed H5 files and recomputed motion/command mappings without modifying bytes.
Sol accepted only this exact full-Panda/two-writer/Hand50/seed31/2ms×5 case as
ACCEPTED_BOUNDED_S2_S3. Independent Attachment, other Providers, force-aware,
endpoints and new Qualification remain outside this result. Next table row is
R03b; no R03b implementation/native has occurred. Evidence is in ignored
`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02c_005/`.
The attempt history below retains original failures and earlier review states.

The task-owned `build_leaf_position_candidate()` composes the existing A05
source/Artifact/reset owners with two separate Arm-only and Hand-only Position
writers on one full-Panda Entity. `SelectedReferenceEnv.from_leaf_position_candidate()`
reuses the existing binding, reset/step/stop/close, typed-state, fault and
Recorder lifecycle; it is an advanced task candidate, not a registered
`make_env()` UID or independent Arm+Hand Attachment route. The MuJoCo adapter
builds a provider-materialization receipt from the compiled model and applies
each writer's owned ctrl slots. `load_leaf_control_records_h5()` is an additive
semantic reader over Generic H5 v3, not a second recording format.

The provider-free targeted S1 passed 53 tests. The authorized bounded MuJoCo
3.8.1 CPU process exited during static contract verification with
`KeyError: 'provider_static_files'` before importing MuJoCo or running native
compile/materialize/reset/forward/step. A script correction was preserved in
contract revision 3 but was not rerun because the fixed process-start budget
was exhausted. Treat R02c native S2/S3 and Provider admission as NOT_RUN; do not
describe the implementation as a supported runtime route or Qualification.
The initial error, corrected script and revisioned contracts are in the local
ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02c_001/`
attempt package.

Sol review (2026-10-27) requested bounded attempt002 fixes after identifying a
wrong prepared-command import, missing nested decoder, stale Target writes
before Ack rejection, exact-float clock comparison, admission cleanup and
old-window preflight gaps. Attempt002 fixed those owners and its provider-free
targeted S1 passed 28 tests, including production Recorder/H5 T=64/T+1=65,
nine tamper cases, adapter no-write rejection and admission cleanup. Static
preflight passed against the frozen source/assets and MuJoCo installation
files; four malformed-contract variants were rejected with structured
zero-native-call evidence. The one authorized MuJoCo 3.8.1 CPU process failed
the loaded runtime version/API check before compile, materialization, reset,
forward or step (`BLOCKED_PROVIDER`). No retry or Provider fallback occurred;
native S2/S3 and Provider admission remain unestablished, and the attempt is
pending Sol review. The earlier attempt001 mixed compatibility process's four
legacy materialize/reset/forward operations remain historical and do not count
toward attempt002. See ignored
`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02c_002/`.

Sol reviewed the attempt002 repairs and synthetic evidence. Current status is
`S1_REVIEWED_NATIVE_PENDING`: the probe incorrectly expected API integer 30801;
MuJoCo3.8.1's official and installed header define 3008001. Sol fixed that guard,
kept strict package/runtime/version/path/hash checks, and records observed
identity before rejection. Original raw logs lack the actual loaded version
values, so neither runtime identity nor a real Provider mismatch is established.
The current rework module passed 19 provider-free tests; Sol ran no native.
The single attempt003 process then verified exact MuJoCo 3.8.1 package/runtime/API,
compiled the unchanged full-Panda closure, created its model-bound 9/9/8 receipt,
and reset E1. The first interval failed after five native substeps: leaf dispatch
passed an untyped tuple to the existing `snapshot_v1()` owner, which requires
`StateRequirements`. No typed interval publication or completed transition
resulted; Generic H5 v3 left a failure artifact with T=0/T+1=1, rejected by the
R02c reader, and the close diagnostic is preserved. The
attempt does not pass S2/S3 or admit the Provider. After retaining its raw
failure, the existing dispatch owner was fixed to construct the typed aggregate
requirements and the rework module passed 19 provider-free tests; this change
was not natively rerun. Treat the attempt as failed and pending Sol review; do
not start R03b. Attempt002 report/logs are in ignored
`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02c_002/`;
attempt003 evidence is in ignored
`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02c_003/`.

Sol review of attempt003 retains actual MuJoCo identity/compile/receipt/reset
and five integration steps, followed by the typed publication failure. The
StateRequirements repair is reviewed and now validates before consume/physics.
The strengthened S1 uses the actual MuJoCo publisher and shared snapshot/projection
with synthetic IO, production Recorder/H5 and the same probe ctrl checker;
38 R02c/R02b tests passed without native load. The remaining probe readback
import and pre-close per-writer fault receipt capture were fixed. The original
T0/T+1=1 failure H5 remains rejected; its finalized attribute does not satisfy
R02c's64/65 requirement.

Attempt004 (2026-10-27) used the new authorized single-process window. Static
preflight verified the unchanged 34,307,550-byte source closure and 67 assets;
the loaded MuJoCo identity matched 3.8.1/3.8.1/3008001 and its pinned file hashes.
E1 arm-only completed 64 intervals, passed the joint-1 motion/home oracle, and
passed same-file H5 T=64/T+1=65 readback plus nine tamper rejections. E2
hand-only completed 64 intervals but failed the frozen hand-motion oracle:
opening minimum 0.068789857 m and excursion 0.007210143 m did not meet ≤0.02 m
and ≥0.04 m. E2's H5 was closed and passed offline typed-reader T/T+1 checks;
E3/E4 did not run. A secondary `numpy.float32` JSON serialization error
obscured the raw summary, but the immutable JSONL event records the actual E2
assertion, 2 materializations, 2 resets, and 640 `mj_step` calls. Exact
`mj_forward` and RSS counts are unavailable. A diagnostic serialization fix
and regression passed 21 provider-free tests after the run; no native retry,
source/algorithm/oracle/threshold/budget change, Provider admission,
Qualification, or R03b start occurred. R02c remains
`FAIL_PHYSICAL_ORACLE / S2_S3_INCOMPLETE_PENDING_SOL_REVIEW`. Evidence is in
ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02c_004/`.

Sol review of R02c004 accepts only the exact E1 arm-only motion/closed-H5
bounded evidence. E2 finished64 intervals but failed Hand motion; E3/E4 did
not run. Actual JSONL/H5 support640 integration steps, while original raw
summary/ledger misleadingly show zero after secondary serialization failure;
keep the raw immutable and reconstruction separate. Forward/RSS remain unknown.
Future probe finalization retains owned live counters, primary/secondary errors
and atomic strict NumPy-safe JSON.42 provider-free checks passed; no Sol native.
The existing5/2500 command-step policy sends at most2mm beyond measured opening.
A source-derived50N/m full Hand section override is proposed as a new Task-owned
configuration; defaults/original failure/source/algorithm/oracle remain unchanged.
It is not a physical5N force cap or Force-aware profile. Current status is
BLOCKED_HAND_CONFIGURATION_DECISION; only explicit maintainer adoption authorizes
the next single-process implementation/validation package. No R03b/Qualification.

## Choose the actual construction branch

- Generic scalar: `from task_env import make_env`; e.g. `make_env("pendulum-v1",
  config={"runtime":{"backend":"cpu"}})`. Call reset before step and always close in finally.
  Task defaults are deep-merged with caller mapping/YAML before public-section overlay; an existing
  `ResolvedEnvConfig` is authoritative. `env.execution_plan` is a provider-free `execution-plan-v0`
  static projection only: it does not establish actual manifest support, runtime materialization, or reset realization.
- Explicit single-Panda Position candidate: `make_env("panda-position-servo-candidate-v1", config={"provider":"geophys",
  "backend":"cpu", "horizon":64})`. Only GeoPhys scalar CPU, fixed reset seed 31, state-only by default, 100 Hz / five 2 ms steps.
  Optional `source_workspace` must be fresh/empty; omission allocates an ignored workspace source snapshot.
  Use exact Scene/plan-bound `StructuredActionRequestV1` with both arm/gripper groups; returned reset/step observations
  carry joint/hand/boundary leaves and info clocks. After reset use the read-only `env.position_plan` for exact Scene/plan IDs and its first binding's action schema;
  hand pose order is x,y,z,qw,qx,qy,qz (world hand-origin TCP), gripper [-1,1] with +1 open/-1 close. At reset call
  `start_recording(path)`, step, then `finish_recording("horizon")` at horizon, or `stop("external_stop")` followed by
  `finish_recording("external_stop")` early. Reasons must match the outcome. Use the same H5 path with the existing
  structured readers; observation arrays are under `obs/state/`. Always close. Constructor imports and an executable
  request example are in [Public API](../../../docs/module/task_env/public-api.md#c02b-position-profile-candidate-status-2026-10-22).
  The task/source owner is `task_env/tasks/position_candidate/`; the old diagnostic builder forwards there.
  No public runtime path imports test modules. The same public environment passed 64 real intervals/65 observations
  and same-file request/target/ack/state readback; task success, freeze/Judge and Qualification are separate.
  R1 and dual-Entity candidates remain diagnostic. See [P99 run receipt](../../../docs/module/task_env/goal/Phase_II/C_Development_Record.md#public-candidate).
- R04a adds an explicit `camera_observation` mapping to that same Position candidate. Decode it with
  `CameraObservationConfigV1` and supply both canonical camera mounts (`world` fixed mount, `hand` mounted camera)
  with authored rigid transforms and use horizon at most 16. It publishes RGB HWC float32, optical-Z depth in metres and canonical Entity mask
  after an existing typed state boundary. The consumer checks capture request identity against its actual config/source/
  execution/manifest and calibration against that same typed parent Frame before publishing leaves. Generic H5 v3
  keeps its root ABI and adds versioned sidecars; the recording-binding sidecar is cross-checked against stored Position
  state-boundary digests, reset/transition clocks, reference-profile metadata and finalized typed outcome/control records.
  Use `load_camera_observations_h5()` for strict semantic checks; missing or unknown binding versions fail closed. Omitting
  the mapping keeps the state-only default. R04a attempt002's targeted provider-free synthetic S1 passed (33 cases),
  accepted by Sol as `ACCEPTED_S1_BOUNDED` after bounded identity/readback review. Real MuJoCo/OpenGL/EGL pairing, public Env camera capture, and same-file camera S3 remain NOT_RUN.
  Do not treat this S1 as R04b/c completion, camera qualification, or P99 gate completion. See
  [R04](../../../docs/module/task_env/goal/Phase_II_01/04_R04_Dynamic_Camera_Consumer.md).
- Selected PickCube: UID `pick-cube-p16-reference-v1`, config `{"provider":"mujoco",
  "backend":"cpu","horizon":6000}`; published bounded scope CPU/100 Hz/seed 31, lift-only predicate.
- Selected NutAssembly: UID `nut-assembly-outcome-reference-v1`, same flat config, seed 19/NA-S0.
  Keep guarded `step_expert()` for the retained internal route. A task-owned external Solution is available
  through `from task_env.tasks.nut_assembly import build_outcome_solution`, `reset_for_solution(solution, seed=19)`,
  and `step_with_solution(solution)`. The bounded full external Expert + execution H5 S2/S3 result is accepted
  only for the exact C05c source/profile in its receipt. The GeoPhys `a53a8cf` CPU/CUDA × 100/500 Hz comparison
  also passed full diagnostic S2/S3, but deliberately called public `read_cpu_snapshot()` on every native step
  despite its general low-frequency guidance. This does not establish a generally supported 500 Hz host-servo
  contract, change a manifest, or establish device-resident control. RuntimeSession binds samples to its
  materialization and episode/reset/evaluation-boundary identity. Neither route admits raw external actions.
- Selected config accepts provider/backend/horizon only: geophys/mujoco, scalar CPU, horizon integer 1–6000.
  No render, legacy overlays, SAPIEN/Genesis or implicit batch support. Generic parallel must have explicit
  homogeneous registration and merged_scene layout; no scalar fallback.

For the bounded NutAssembly external Solution route, caller owns the active Solution instance; the
selected Environment publishes its actual reset/runtime boundary, `step_with_solution()` supplies the
native RuntimeSession sample/ack contract, and the existing execution Recorder persists substep samples.
Keep the Panda `actuator8` signed-force/N mapping, reset-forward versus completed-step pre-integration
phase, and five 2 ms native samples per 100 Hz interval. Do not read `env.solution`, private Solution stage,
or a mutable hold/ramp object. The MuJoCo receipt verifies task success, Expert/Outcome completion,
the original 8 N / 0.1 s close Guard, Controller-owned hold/ramp acknowledgements and same-file H5 readback
for 2,377 intervals. The explicit `NutAssemblyReferenceEnv.for_gripper_cadence_diagnostic(backend, gripper_control_hz)`
and `build_gripper_cadence_diagnostic_solution(...)` reuse those owners for the exact GeoPhys cadence comparison.
They completed CPU/CUDA × 100/500 Hz S2/S3, using host snapshots at each native step as an authorized diagnostic
exception. The default selected constructor remains CPU-only; do not infer generic capability or GPU-resident
control. Update counts, timing and H5 hashes are in the [cadence report](../../../docs/module/task_env/goal/Phase_II/C_Development_Record.md#c05c)
and [C05c receipt](../../../docs/module/task_env/goal/Phase_II/C_Development_Record.md#c05c).

Use [examples](../../../examples/README.md) for exact current CLI commands. Preserve fresh output paths,
resource bounds and provenance. Repository has no root packaging metadata: dependencies via requirements,
run from root with `PYTHONPATH=GeoPhys/src:.`; do not recommend editable installation.

## Outcomes, recording and evaluation

Task predicate, Outcome V1 completion, strict Expert lifecycle, termination/truncation, replay validity
and Judge approval are different facts. NutAssembly GeoPhys accepted readiness warning/strict failure
must not be erased by successful outcome. Do not stop a required retreat at first task success.

The generic scalar lifecycle exposes `env.stop(reason="external_stop") -> EpisodeEndV1`, pairing the existing
`BoundaryEventV1` and `EpisodeOutcomeV1` at the last complete boundary. Stop does not call a Controller, apply
control, advance Runtime, or change flags from an already-returned Gymnasium transition. Defaults: external Stop
and horizon truncate with bootstrap allowed; task terminal terminates without bootstrap; execution fault truncates
without bootstrap and carries the `ExecutionFaultV1`. Terminal takes precedence in the final outcome when a legacy
step returns both flags, while the returned flags remain untouched. Repeated Stop returns its cached result; Stop
before reset and Stop after close fail. Reset of an active generic episode first finalizes Stop(`reset`) and returns
that result in `previous_episode_end_v1`; close ends an active lifecycle before resource teardown. The selected
`production-r1` route explicitly rejects Stop; only the opt-in PositionServoV1 candidate has its own bounded Stop.

After a failed reset/step, inspect the existing Env owner's `execution_fault` (`ExecutionFaultV1`); a
construction exception may carry the same receipt as `exception.execution_fault`. Faulted environments
require a successful reset before another step. `physical_progress` describes only observable progress
of the current control interval and is inferred from trusted public before/after simulation clocks against
the expected control dt, checked against interval-return and control-step boundary evidence. An unreadable
clock, conflict between observer and Recorder count claims, or contradiction between clock and execution
boundary evidence yields `unknown`. The independently reported
`observer_confirmed_substeps` and `recorder_confirmed_substeps` are evidence counts, never exact physical
completion counts. A missing or inconsistent Recorder receipt can leave physical progress clock-confirmed
while making the Recorder count unavailable and the transition incomplete or rejected. `transition_status`
independently reports whether the owner assessed a transition, recording was absent, incomplete, rejected, or
confirmed valid; full physical progress does not make an incomplete transition valid. For selected native
execution, the existing `SelectedReferenceEnv` checks the Recorder's pending control step, timebase, substep
counter and ordered payload rows before append. The counter is accepted only when it agrees with the rows;
missing rows reject append, while an internally conflicting count is reported as unknown. The existing
`ExecutionRecorder` prepares the transition and following boundary before committing either; a boundary
serialization failure leaves the interval pending and does not leave an orphan transition row. The receipt
does not imply physics rollback or recovery, and an incomplete selected execution interval must remain pending
so the existing Recorder refuses to freeze it. If that pending recording blocks reset, close and recreate the
environment; C03a adds no recording-discard API.

For selected expert recording use `examples/recording/record_expert.py` or
`task_env.script.trajectory.record`, which reuse the selected env's recorder owner.
`start_recording(path)` is at reset boundary; finalize before another reset. Inspect with
`examples/recording/inspect_h5.py`; T transitions require T+1 boundaries. Generic wrappers use
`task_env.recorders`; selected canonical/execution formats differ from generic raw H5. Generic default v2,
canonical outer v0, and execution v1/v2 stay readable with their original schemas; Phase II C05a adds
opt-in generic H5 v3, canonical outer v1, and execution stream v3 within those same Recorder owners.
The inspector validates loaded storage/T+1; its `storage_roundtrip` field does not mean it
performed a new save/load roundtrip. H5 roundtrip itself is storage integrity, not D0 restoration
or formal replay qualification.

For generic structured recording, configure `RecorderConfig(schema_version="v3")`, pass one typed
`StructuredControlTransitionV1` per actual transition, record `BoundaryEventV1` only at the current 0..T
boundary, and finalize with explicit `EpisodeOutcomeV1`. A v3 file with T=0 has one initial observation and
may contain boundary events/outcome without a pseudo action. Use `load_structured_control_records_h5()` to
read the typed payload. `load_structured_training_actions_h5()` is a narrow lossless conversion: the recorded
request must have one writer, an exact schema id/component order, and values equal to the stored action dataset.
Multi-writer trees and schema mismatches reject; the existing Stage 11 transcode remains v2-only and rejects v3.
`load_structured_training_episode_h5()` composes the same exact action projection with the stored per-transition
`terminated`/`truncated` arrays and the final EpisodeOutcome/bootstrap policy. It never rewrites transition flags;
the final effective bootstrap decision is returned separately. The v3 `TransitionRecordWrapper` requires an Env
that explicitly declares `supports_structured_control_recording is True` and emits a typed control on every step.
No current generic TaskEnv is so declared: Pendulum remains GeoPhys-only and v2 recording rejects active Stop
before forwarding it. Manual v3 `end_record`, active v2 Stop/close, and vector Stop are explicitly unavailable.
The Position candidate currently uses its existing direct Generic H5 v3 recorder, not the Gym wrapper.
Canonical outer v1 uses `CanonicalRecorder(schema_version="canonical-trajectory-v1")` and
`canonical.h5.load()`; execution stream v3 uses the existing `ExecutionRecorder(..., schema=STRUCTURED_SCHEMA)`
and resident/streaming readers. These are storage contracts only: they do not add Runtime dispatch or prove
physical replay. The current selected reference replay deliberately rejects canonical outer v1.

For task construction/freeze, randomized feasibility, Experiments, evaluation report, explicit Human
Judge and Evidence packaging, load the existing
[task-env-experiment-evidence Skill](../../../task_env/.agents/skills/task-env-experiment-evidence/SKILL.md).
It owns that procedure; this Skill does not copy or replace it. Workspace manifests/reports/Judge
files currently require explicit preparation under that contract; no unified Experiment Engine,
validator command or automatic approval is implied. A built-in recipe/Artifact hash is not an
independent Stage-1 Judge approval; verify the referenced approval package, or report its absence
and prepare the required validation/Judge review before claiming a newly frozen task.

## Capability and change boundaries

Use the [single published matrix](../../../docs/module/task_env/capability_matrix_v1_1_0_candidate.json)
with exact source/config/provider/backend/task identity. Candidate wording in its frozen metadata records
review time; v1.1.0 publication is documented separately. Historical report/source paths inside this
byte-preserved matrix may be tag-only: resolve them through
[consolidation inventory](../../../docs/maintenance/consolidation-inventory.json) or
`git show refs/tags/v1.1.0:<original-path>`, not by assuming local files still exist.
IMPLEMENTED != TESTED_BOUNDED != QUALIFIED.
No new P1.8 FULL/D0-D2, manipulation checkpoint/PPO, native Flora/GeoPhys Rigid Batch or general
Physics × Renderer qualification. Pendulum learning/RGB smokes are bounded wiring, not convergence.
The 2026-10-20 GeoPhys development sync has a newer Gitlink than v1.1.0; use the checked-out
revision and the bounded [sync receipt](../../../docs/module/task_env/runtime-and-providers.md#geophys-开发基线同步2026-10-20).
Published v1.1.0 qualification/acceptance does not transfer to this provider revision.

Physics and renderer stay separate. Never read provider-private solver/renderer state. Task semantics
and stages stay task-owned; reuse controller/observation/recording/learner/render contracts.
Go2/static-template and historical camera/task routes are RETIRED, not aliases; use migration/recovery refs.
Unsupported combinations fail closed; locate exact error and first violated invariant before patching.

Before changing behavior, identify owner/public API/existing implementation/production callers/tests,
establish the limitation, and evaluate repair/extension/composition. Use
[module maintainer](../geochora-module-skill-maintainer/SKILL.md) `mode: improve` and classify the proposal;
never add duplicate Runtime/Recorder/Controller/factory/provider/Skill. Documentation requests do not
authorize implementation changes. Review Skill drift after API/registry/ownership/workflow/status/bugfix/
retirement/test/failure changes, using the maintainer refresh procedure and bounded validation.

For advanced canonical state contracts, use the existing `task_env.artifacts` owner. `CanonicalStateView`
remains the strict scalar `canonical-state-v0` route; D02a added `CanonicalStateViewV1`, typed Joint/Frame,
StateRequirements, sample/boundary clocks, native interval evidence, and view lifetime values. Use
`decode_canonical_state_view()` for exact version dispatch and `project_canonical_state_v0()` only with
explicit Scene plus legacy-name bindings. D02b adds `RuntimeSession.snapshot_v1()` and
`CanonicalStatePublicationV1` on the existing GeoPhys/MuJoCo CPU sessions: the caller supplies the exact
Scene identity, explicit Joint/Frame bindings, and StateRequirements; scalar state is projected from v0,
and the bounded floating-joint path reads 7-position/6-velocity values into an owned snapshot. Legacy
`snapshot()` remains v0. Optional unsupported contact is explicit unavailable; required contact and
native-interval requests fail closed. SAPIEN/Genesis typed projection, spherical native readback, contact
readback, and a versioned H5 state format are not implemented. The existing TransitionRecorder in-memory
copy path has a bounded owned-storage probe; this does not claim typed-state H5 persistence. Requirement
capability IDs describe what a consumer needs and never add claims to a provider manifest.

For Phase II B02 reset selection, use `TaskInitializationV1`, `resolve_role_binding()`, and
`sample_episode_reset_plan()` in `task_env.environment`; keep `RoleBindingV1` and
`EpisodeResetPlanV1` beside the existing `ResetSample` in `task_env.artifacts.execution`. Initialization
is optional when reading the B01 source shape, but required to build a reset plan. Reuse the Artifact's
`UniformDimension` bounds and preserve the exact provider-facing ResetSample v0. `resolve_role_binding()` requires
the matching TaskArtifact v0 on the original B02 route; D01b also admits a TaskArtifactV1 only when its exact
Scene identity and TaskSource snapshot match. The resolver checks explicit candidate IDs, structured Scene
topology coverage, RobotInstance classification, and disjoint role candidates; it does not create tags or an
asset registry. Use `RuntimeSession.reset_plan()`
for a plan-bound reset: it matches the materialized Scene identity, runs the existing requested/realized
state gate, and keeps snapshot/step closed if that gate fails. The legacy `reset(sample)` route remains
available. Current end-to-end B02 evidence covers three free rigid bodies on GeoPhys and MuJoCo CPU plus
exact PickCube PCG64-v0 and NutAssembly NA-S0 ResetSample compatibility; a separate GeoPhys probe consumes
the exact A05 Scene-v3/source-closure input with fixed authored initialization. The randomized three-body
probe uses bounded direct MJCF/Scene-v2 input and does not qualify general A04 free-body import lowering.
Do not infer full task rollout or SAPIEN/Genesis qualification from these probes.

For the Phase II D01b vNext materialization slice, compile the candidate with
`compile_task_artifact_v1()`, build its plan with the matching `TaskSourceV1` and exact Scene-v3 value, then call
the existing `RuntimeSession.materialize()` and `reset_plan()` APIs. This route is TESTED_BOUNDED only for one
fixed-topology Panda RobotInstance plus a static square peg on GeoPhys/MuJoCo CPU; MuJoCo consumes the canonical
MJCF axis projection and bounded VFS assets, and verifies the source-closure digest before native build. It rejects Scene/TaskSource identity drift, missing required
Frame/Joint/assets, unbounded source roots, multiple RobotInstances, free-body pose reset and nonzero settle.
The same hash-bound `ResetSample-v0` must be passed to both Providers for one exact Artifact/Scene; changing the
Scene changes the TaskArtifactV1 identity and therefore needs its own sample. See the
[D01b bounded receipt](../../../docs/module/task_env/goal/Phase_II/D_Development_Record.md#d01).
This does not implement control execution, contact semantics, task success, rendering or qualification.

For Phase II B03a read-only predicates, use `TaskEvaluationContextV1` and call
`TaskLifecycleAdapter.evaluate_predicates()` explicitly. The context separates the task's requested action and
schema from the existing `AppliedControl`; declared `Timebase` cadence is not measured interval evidence, which
must come from `NativeIntervalEvidence`. Resolve predicates through `TaskPredicateEvaluationV1.resolve()`:
`available` with `value=False`, missing/unavailable data, and `no_evaluator` are distinct outcomes. Predicate reads
must be pure and may repeat at one boundary; ordinary step and observation paths do not call them automatically.
Current bounded task projections are PickCube lift-only and Pendulum instantaneous upright. Pendulum's windowed
`task_success` is unavailable on a pure read; B03b exposes it through an explicit temporal commit. Declare only
`TemporalPredicateRuleV1` rising-edge, sample-count dwell, or rising-edge sequence rules on the existing
TaskDefinition. Call `TaskLifecycleAdapter.commit_temporal_predicates()` with the matching
`StateBoundaryIdentity` and evaluation `StateSampleClock`: exact duplicate commits are idempotent, conflicts/order errors
fail closed, and reset/gaps/missing inputs clear progress. Dwell counts outer evaluation samples, never seconds or native
substeps. This route currently commits scalar boundaries only and is S1 contract evidence. Do not replace the existing
reward `evaluate()` contract or reuse the stateful Expert Guard as a general predicate engine.

For generic execution configuration, inspect the normalized `BaseTaskEnv.execution_plan` before assuming
provider support. Known unsupported generic selections (including multi-agent materialization and a Panda
without an explicit Controller) fail before `bootstrap_task_runtime`. The plan's owner identities are static
contracts: BaseTaskEnv closes camera/UI wrappers, `SingleTaskLifecycleAdapter` closes the runtime boundary,
and the current GeoPhys boundary does not destroy Taichi's process-wide runtime. Selected-reference configs
remain on their separate provider/backend/horizon compatibility route.

For D05a execution selections, import the advanced `ExecutionSpecV1`, `RendererSelectionV1`,
`CameraRendererOverrideV1`, and `decode_execution_spec` from `task_env.artifacts`. Missing discriminator
continues to mean the exact legacy `ExecutionSpec` mapping; do not rewrite frozen v0 values. Per-camera
overrides replace the complete renderer selection, while other cameras use the explicit default. These
contracts and `CameraRenderSource.capture_identity()` are static request descriptions only. Current
`RuntimeSession.materialize()` and `create_camera_session()` still consume the legacy selection/admission
route. The separate advanced `create_dynamic_camera_session()` route has three exact profiles over the same
verified `DynamicCameraRenderSourceV1` and initial `CanonicalStateViewV1`: D03 admits GeoPhys CPU Scene-v3
scalar-joint state to MuJoCo native OpenGL RGB; D04 admits the same source intersection for synchronous
RGB/optical-Z Depth; the bounded D04 Entity-instance profile requires RGB+Depth and adds an integer mask in the
same capture. It binds native geometry through unique canonical Frame→Entity ownership; native geom IDs never
become public labels. `CanonicalEntityInstanceSegmentationV1` is H×W uint32 with background label 0, and
`CanonicalEntityLabelMapV1` uses dense deterministic positive labels for canonical Entity IDs. The map binds
TaskArtifact/source, Camera, SceneInstance, provider materialization, episode/reset, exact state boundary and
capture identity. Missing/ambiguous mappings, non-geom objects, stale publications and unknown mask labels fail
closed. D04 Depth is H×W float32 metres along optical +Z with zero for invalid/clipped/background. A successful
`CanonicalCameraObservation` carries the existing `CameraCaptureIdentityV1` for its exact boundary/clock/modalities.
The route rejects free joints and other provider/backend pairs; semantic classes and general D05b admission remain
unsupported. It does not call Controller or advance physics and is not a Qualification. MuJoCo exposes
no public renderer context handle; GL strings observed after capture are diagnostic only and do not pin or admit
a device.

**D05b first bounded pairing (2026-10-22):**
`task_env/diagnostics/tasks/d05b_pairing_s2_probe.py` composes the existing Position candidate's GeoPhys CPU
`RuntimeSession`/`RuntimeSource` with the existing `ExecutionSpecV1` and `create_dynamic_camera_session()` owner.
It exercises the default selection for a fixed camera and a per-camera override for the hand-mounted camera; both
resolve to the one exact admitted MuJoCo native OpenGL Entity-instance profile and their successful capture identities
bind the same ExecutionSpec and each camera's sync publication. The receipt's targeted S1 and real S2 passed for this
single Scene-v3 scalar-joint candidate on GeoPhys gitlink `4436787e…`. A separate current-pin S1/S2 now passes on
`a53a8cfe…` with MuJoCo 3.8.1, real NVIDIA EGL / RTX 5060 / OpenGL 4.6.0 driver 595.84. S1 includes failure/teardown;
S2 includes 12 intervals, six fixed/mounted captures, exact capture/state identities, RGB/Depth/Entity-mask change,
zero capture-time Controller/physics calls and exactly-once native Renderer close. Preserve the old receipt identity. See the [D05b receipt and applicability addendum](../../../docs/module/task_env/goal/Phase_II/D_Development_Record.md#d05).

This bounded pair remains a direct CameraSession diagnostic route. `BaseTaskEnv` policy RGB/Depth currently use the
separate configured `CameraObservationProvider` → `StateObservationBuilder` route; the D05b dynamic session does not
feed those observations or `TransitionRecorder`, and its diagnostic files are not policy/trajectory data. Do not
claim visuomotor observation or recorded-camera integration. A future connection belongs in the existing observation
owner and must bind RGB/Depth/mask plus capture identity to the same runtime boundary before using the existing recorder.

For Phase II B01 authoring input, use `task_env.environment.TaskSourceV1` and `load_task_source()` from the existing
environment owner. The current strict envelope accepts task identity, a Scene reference, typed role selectors,
and hook declarations; loading it does not alter `ResolvedEnvConfig` and never imports or executes a declared hook.
`load_yaml_mapping()` rejects duplicate YAML mapping keys. Keep execution settings in the existing config resolver.
`adapt_legacy_recipe_task_source()` is a compatibility projection for the old `recipe`/`environment` shape; it does
not change PickCube's v0 Artifact identity. Role candidates are explicit Entity IDs because A's canonical
`EntityInstance` has no tag metadata owner; B02 owns reset-time selection.

For Phase II B04b's bounded compile, call `compile_task_artifact_v1()` with a validated Source, structured canonical
Scene, and the existing v0 semantic bridge. It statically checks role candidates and exact legacy Entity references;
legacy Frame/Joint aliases require explicit typed `FrameReference`/`JointReference` bindings and are included in the
candidate identity. Compilation does not draw a reset sample. The resulting `TaskArtifactV1` references Scene schema/id/hash, snapshots
the normalized Task Source mapping, carries the existing typed action/initialization/semantics/timebase/capability
contracts, and identifies unrepresented v0 World fields through `source_retained_v0_fields` plus the source Artifact
identity. Do not embed a second Scene/World copy, infer an approximate mapping, or treat the result as a RuntimeSession,
Recorder, qualification, or freeze route. `TaskArtifact.from_mapping()` remains v0-only; use
`task_env.artifacts.decode_task_artifact()` for exact v0/v1 dispatch. H5/trajectory/state/camera readers retain their
independent version routes until real historical fixtures are available.

## Phase II C02a / C05a bounded routes

`compile_control_binding_plan()` in `task_env.runtime.sessions.control` resolves A03 Scene-v3 ControlGroups to
existing Controller writers, existing `ActionModeSpec`, and existing `StateRequirements`. It is static admission and
`prepare_structured_action()` is a pure all-groups preflight returning existing `RequestedAction` values. These two
functions do not dispatch to Runtime. The separate existing session execution paths have the exact single/dual Position
and single R1 candidate evidence described below; static compilation alone does not grant multi-robot support.

`materialize_control(..., controller_binding_plan=plan)` is the fail-closed admission route for a bound Controller: the
source must carry the plan's exact Scene identity, and every required feedback capability must be supported by both the
actual Provider capability envelope and any caller-supplied restricting manifest before Runtime materialization. The
original C02a A05 required-force binding remains rejected by the generic GeoPhys/MuJoCo manifests. The new R1 candidate
has separate, exact call-specific claims for clean GeoPhys `a53a8cfe` CPU and the audited MuJoCo 3.8.1 CPU/native build,
each bound to source/Controller/TCP/plan; neither makes the original binding or a generic manifest supported. Omitting
the optional plan preserves the legacy route. Admission alone is not Group dispatch, an applied acknowledgement, or real
execution evidence.

**C02b-E Position Profile candidates (2026-10-22):** use
`PandaPositionServoProfileV1.from_source(artifact, source)` only for the explicit A05 candidate, then compile the
existing `ControlBindingPlanV1` from `profile.controller_binding()` and pass both plan and profile to the existing
`materialize_control()` owner. The profile identity binds the candidate Artifact/Scene/source closure, projected MJCF,
hand-origin TCP v1, exact Joint/Frame/actuator mappings, action schema, ActionConfig and 100 Hz / 5×2 ms timebase.
Its Required State is the entity's nine Panda Joint positions plus its hand Frame at evaluation boundaries; it does
not consume measured actuator force. The exact bounded dual candidate composes the same existing Profile for
`panda-main` and `panda-secondary`, 16 entity-local actuator resources and one complete `ControlBindingPlanV1` in one
selected RuntimeSession/world. Every action Group and source/boundary identity is preflighted before either Controller
computes. This does not authorize arbitrary multi-writer arbitration, arbitrary N Entities, Assembly or a default
capability. The explicit diagnostic candidate constructor reuses `SelectedReferenceEnv` and `ReferenceTaskBinding`; the
selected lifecycle writes Generic H5 v3. GeoPhys CPU and MuJoCo CPU S2 and request/target/ack/state/boundary disk
readback passed for both the single- and dual-Panda candidates. Wrong Entity, missing Group, altered Profile/group
contract, overlap, stale target and boundary mismatch are rejected before compute/apply/step; an injected second-writer
apply failure uses the C03a latch and emits no partial transition. Do not substitute this profile into PickCube R1, weaken its required-force contract,
or treat the candidate as a default registered capability. The legacy PickCube R1 reset-force freshness prerequisite
has a separate GeoPhys CPU receipt; one new candidate now has exact plan-bound GeoPhys CPU and MuJoCo CPU raw-force
admission and a single real interval on each route, but the legacy selected Artifact/source is not rebound by that evidence. NutAssembly Guard and full
C02b remained open at this Position receipt's checkpoint. See [single-profile S1](../../../docs/module/task_env/goal/Phase_II/C_Development_Record.md#c02b),
[single-profile S2/H5](../../../docs/module/task_env/goal/Phase_II/C_Development_Record.md#c02b), and
[dual-Entity acceptance](../../../docs/module/task_env/goal/Phase_II/C_Development_Record.md#c02b).

**C02b-R1 reset-force freshness (2026-10-22):** the legacy selected PickCube
`production-r1` GeoPhys adapter consumes the public
`RobotArmObservationReader` sample contract after restore and writes of the
final reset state. Reset-forward force is evaluated from current
qpos/qvel/ctrl/activation/configuration without a physics step; completed-step
force is separately marked pre-integration. State/config writes invalidate the
previous receipt, and the required R1 consumer rejects invalid or mismatched
identity/boundary samples. Core preserves signed raw force until the existing
`control_feedback()` maps the Panda closing direction. Evidence is bounded to
PickCube seed 31 on GeoPhys CPU; MuJoCo CPU is a sampling-semantics comparison.

**C02b-R1 typed raw-force admission, original GeoPhys receipt (2026-10-22):** `CanonicalStateViewV2` /
`CanonicalStatePublicationV2` add typed raw signed force without changing v0/v1
state bytes or hashes. `RuntimeSession.snapshot_v2()` composes the existing
Joint/Frame view with a Provider-owned sample. A call-specific admission claim
is produced only for the new Panda R1 Scene-v3 candidate on clean GeoPhys CPU
revision `a53a8cfed7c9d6464274b5c96fca601271dc4ee4`, exact source closure,
`panda-main/actuator8` tendon, actual `ProductionCanonicalPandaController` /
hand-origin TCP, and exact `ControlBindingPlanV1`. The required value retains
signed force and binds unit, Provider sample revisions/phase/native clock,
source closure, materialization, episode/reset and evaluation boundary.
`snapshot_v1()` remains force-free; legacy no-plan APIs remain compatible;
generic Provider manifests do not claim `actuator_force_query`. One real
100 Hz GeoPhys CPU plan-bound R1 interval and next typed publication passed.
This does not transfer to the old PickCube selected Artifact/source, other
transmissions, full C02b, or C05b. The later MuJoCo build-bound addendum is recorded below. See the
[freshness receipt](../../../docs/module/task_env/goal/Phase_II/C_Development_Record.md#c02b)
and [typed-force receipt](../../../docs/module/task_env/goal/Phase_II/C_Development_Record.md#c02b).

**C02b single-Panda structured R1 behavior (2026-10-22):** the Scene-v3
`production-r1` candidate ran in independent GeoPhys `a53a8cfe` CPU and exact
MuJoCo 3.8.1 CPU/native-build processes. Both completed the predeclared
open/free-close/open-approach/obstructed-close/force-hold/reopen sequence at
100 Hz with five 2 ms native steps, and each Generic H5 v3 file passed same-file
structured-control/action, state, identity, clock and T/T+1 readback. A real
negative signed force crossed the unchanged 3 N trigger on both routes;
`control_feedback()` alone produced canonical closing force, and the real R1
force-mode target matched its applied acknowledgement. Force mode, readiness
and measured state remain separate facts. Both final runner results are
`PASS`; their source-FK arm-pose residuals were 2.671 mm / 0.030374 rad on
GeoPhys and 3.391 mm / 0.030208 rad on MuJoCo, within the unchanged 6 mm /
0.035 rad limits. Earlier exploratory target failures remain preserved and
are not the final runs. The C02b declared-intersection bounded engineering exit
is satisfied; unadmitted extensions and Qualification are separate. The
R1 candidate remains diagnostic. P99's separate single Position candidate now has an explicit public UID and
passing continuous reset→step→observation→record→same-file readback Evidence. The
force publication/admission and behavior claims remain bounded to their exact
intersections.
P00/P99's minimum dual-Entity requirement is already covered by the Position
S2 evidence; no approved basis was found to require dual-Entity R1. CUDA R1,
alternate source/build/transmission and broader capability remain unadmitted;
Qualification is separate and unrun. See [structured R1 S2/S3 receipt](../../../docs/module/task_env/goal/Phase_II/C_Development_Record.md#c02b).

**C02b structured R1 Skill refresh receipt (2026-10-22):** baseline at review start was Core `9280b589685bb80d6c484aea51c99a90f2640cfb` on `codex/phase-ii-c03b`, with the GeoPhys checkout clean at `a53a8cfed7c9d6464274b5c96fca601271dc4ee4`; all current implementation/report changes remain local. The trigger was completing the exact candidate's continuous force-mode/recording probe and finding old Skill text that still described structured execution, MuJoCo typed force, or dual-Entity R1 as current blockers. Inspected owners/callers: `build_r1_force_candidate`, `materialize_control`, `execute_plan_bound_r1_control_interval`, `RuntimeSession.snapshot_v2()` and `control_feedback()`, `TransitionRecorder`/Generic H5 v3 readers, the diagnostic runner, and its S1/C03a tests. Reuse result is `COMPOSE_EXISTING` runtime/Controller/Recorder owners plus a task-local diagnostic runner; no public registry, Runtime, Provider, Controller, or Recorder was added.

The Skill identifies both exact CPU intersections, same-file H5 v3 readback, reset/step force phase semantics, stale-reapply refusal, and the passing final arm-pose comparisons. The current C02b wording is now “declared-intersection bounded engineering exit satisfied”; unadmitted extensions and Qualification are separate. At that historical checkpoint P00's minimum dual-Entity requirement was covered by Position-only evidence and P99 still lacked a candidate `make_env()` mainline; the later P99 run receipt supersedes that route gap. Targeted regressions were 69 passed, then 2 updated native stale-reapply tests passed; the Evidence-overwrite refusal regression and static Skill metadata/local-link/source-path checker also passed. Independent cold-start/Agent review and system `quick_validate.py` were NOT_RUN; Human review remains pending. Full config, raw evidence hashes, exploratory failures and output-preservation declaration are in the [structured R1 receipt](../../../docs/module/task_env/goal/Phase_II/C_Development_Record.md#c02b).

**P99 / C02b current status (2026-10-22):** C02b's approved bounded engineering exits remain satisfied.
The two P99 runtime gaps now have PASS_BOUNDED Evidence: public single Position candidate mainline and current
`a53a8cfe` GeoPhys CPU × MuJoCo native OpenGL pairing. B04a's original `geophys-transition-h5/v1`, canonical outer-v0
and canonical-execution-v1 H5 byte fixtures remain ACCEPTED-DEFERRED separately. The maintainer accepted and froze the Phase II scoped engineering envelope on 2026-10-23; unrestricted breadth, release promotion and Formal Qualification are separate. See
[P99 readiness](../../../docs/module/task_env/goal/Phase_II/05_Architecture_Review_and_Execution_Order.md#p99) and
[run/Skill receipt](../../../docs/module/task_env/goal/Phase_II/C_Development_Record.md#public-candidate).

**Documentation alignment (2026-10-22, task_env / refresh):** on Core `ec2dd24`, corrected the routing text and
`references/routes.md` to distinguish original static admission, exact candidate typed-force admission, and actual
execution. Owners/callers and retained S1/S2 evidence are those in the typed-force refresh receipt below; no implementation,
Provider pin or capability was changed by that documentation-only alignment. It correctly stated that a future `a53a8cfe`
migration required its own verification; the migration and re-verification have since completed as recorded below. C05b
public lifecycle S1 also now has a bounded receipt. Independent Agent cold-start checks from that earlier pass were NOT_RUN.
Validation used the repository's GeoChora Python environment: module Skill checker, system `quick_validate.py`,
documented v1/v2 state/session import checks, and local-link/anchor checks passed. These are documentation/static checks,
not a new native acceptance or capability review; the typed-force claim still retains the Human review boundary below.

**Historical Skill refresh receipt — 2026-10-22, task_env / refresh:** source checkpoint at start was
`ec2dd2438da5c0bd1b79ed58c3900e54bb7433ca` on `codex/phase-ii-c03b`; the listed Core files are local changes,
GeoPhys remains clean at `eb870f6f8812abea9022594b702df0c395d98d48`. The refresh was triggered by new typed state,
RuntimeSession, Controller identity-readout and capability-admission behavior. Owners inspected: `task_env.artifacts.state`,
`RuntimeSession.snapshot_v1/v2`, `materialize_control`, the GeoPhys session adapter, the existing R1 Controller, public
`RobotArmObservationReader`, selected force consumers, State/Admission/Position tests and the targeted native probe.
Reuse classification: `EXTEND_EXISTING` state/session/Controller owners plus `COMPOSE_EXISTING` public observation and
control-feedback route; no parallel Runtime, measurement store or Provider abstraction.

Drift repaired: the earlier Skill entry said typed plan-bound admission did not exist. The actual state is now an additive
v2 publication and one call-specific admission route restricted to the new Panda candidate and repaired GeoPhys CPU revision;
`snapshot_v1`, v0/v1 hashes, legacy no-plan behavior and shared Provider capability lists remain unchanged. S1 regression was
**35 passed, 1 deselected**, including C02a, old R1/Position and dual-Position consumers; S2 was **1 passed** for one native
100 Hz interval. Fresh-interpreter imports, skill link/metadata validation and their outputs are recorded with the acceptance
receipt. Evidence envelope for that historical refresh: candidate Artifact/Scene/source closure, actual R1 Controller/TCP and
plan identities from [typed-force receipt](../../../docs/module/task_env/goal/Phase_II/C_Development_Record.md#c02b),
GeoPhys CPU `eb870f6f...`; raw evidence remains under ignored
`workspace/maintenance/c02b_r1_typed_force_20261022/`. Cold-start route: construct the explicit candidate, compile its
ControllerBindingPlan, call `materialize_control(..., controller_binding_plan=plan, controller_profile=controller)`, reset
with its EpisodeResetPlan, then call `snapshot_v2()` and the bounded plan-bound interval owner. MuJoCo typed force, old selected
PickCube plan identity, other actuators/backends, full C02b, C05b, Guard and qualification were not run or enabled at that
historical checkpoint. Human review of this API/capability-sensitive bounded claim remains pending.

**C05b public lifecycle S1 (2026-10-22):** for the selected PickCube R1 route, a task-owned external Solution can be
constructed with `from task_env.tasks.pick_cube import build_readiness_solution`, then passed to
`env.reset_for_solution(solution, seed=31)`. Keep that instance as the sole owner of its stage/counter/wait state and call
`env.step_with_solution(solution)` once per 100 Hz control boundary. Do not read `env.value`, `env.solution`, or private
`_execution_info()`. Reset and step info carry required `expert_execution_info_v1`, `control_readiness_v1`, and
`expert_execution_boundary_v1` regardless of diagnostics; reset contains no applied acknowledgement. Only a completed control
step carries `control_application_v1` with source/request/evaluation boundary, target and actual applied acknowledgement/hash.
The Environment calls the supplied Solution's `observe()` before its existing canonical-v0 Recorder append. Missing/stale
readiness, boundary mismatch, observer exceptions and Recorder append failure reject/latch before another step; a fault does not
imply physics rollback.

This paragraph records the public lifecycle S1 acceptance at that checkpoint. It used the legacy `task-env-pick-cube` source,
frozen PickCube Artifact, `panda-v1/ee` TCP, required production-r1 feedback and canonical-trajectory-v0; it did not borrow the
separate A05 Scene-v3 `panda-main` plan identity. At that checkpoint S2/S3 had not run; they were subsequently completed for
the bounded GeoPhys/MuJoCo CPU routes below. Legacy selected `stop()` remains unsupported; Task success, Expert completion and
existing stop/recording semantics remain distinct. See the [public lifecycle S1 receipt](../../../docs/module/task_env/goal/Phase_II/C_Development_Record.md#c05b).

**C05b legacy external Solution S2/S3 (2026-10-22):** for the fixed `pick-cube-p16-reference-v1` legacy Artifact/source,
construct the task-owned Solution with `build_readiness_solution()`, call `reset_for_solution(solution, seed=31)`, then
`step_with_solution(solution)` at each 100 Hz control boundary. Keep the exact actual Controller, source ID/XML hash, Core
episode, Solution and ResetSample identities; this source has no Scene closure or plan identity. The bounded external Expert
and canonical-v0 disk readback passed in separate processes on GeoPhys `a53a8cf` CPU and MuJoCo 3.8.1 CPU, using five 2 ms
steps per interval. Each route has its own T/T+1, feedback/readiness, stage, Task success, Expert completion, action→target→ack,
flags and H5 readback evidence in [the S2/S3 receipt](../../../docs/module/task_env/goal/Phase_II/C_Development_Record.md#c05b).
Observer/append failures reuse the C03a fault latch and cannot finalize an incomplete canonical recording. This does not create
legacy R1 Stop/Event/Outcome or migrate the legacy PickCube route to the separate candidate plan-bound typed-force identity,
close C02b, or grant Qualification.

For the latest local route baseline, use GeoPhys `a53a8cfed7c9d6464274b5c96fca601271dc4ee4`; the older `eb870f6f` refresh
receipts below are historical and remain useful only for their original evidence provenance.

**Follow-up Skill refresh receipt — 2026-10-22, task_env / refresh:** Core checkpoint at start was
`1eac5649afaa25b077afdd58de5f480a0a213245` on `codex/phase-ii-c03b`, preserving the uncommitted typed-force work; Core
lifecycle/docs/Skill changes remain working-tree edits. GeoPhys is clean at the requested fixed revision
`a53a8cfed7c9d6464274b5c96fca601271dc4ee4`. Public owners inspected: `SelectedReferenceEnv`, `ReferenceTaskBinding`,
PickCube `build_reference()`/`build_readiness_solution()`, `PickCubeReadinessSolution`, `ExpertExecutionInfo`, the existing
R1 compute/apply path, `CanonicalRecorder`, C03a fault latch, selected-consumer tests, public API and Phase C records.
Drift repaired: Skill statements previously tied typed-force admission to `eb870f6f` and said external Solution wiring was
future work; current source binds force admission to `a53a8cfe`, and exposes the bounded public S1 sequence above. Provider
re-verification evidence is under ignored `workspace/maintenance/c02b_r1_geophys_a53a8cf_20261022/`; C05b lifecycle test
output and provenance are under ignored `workspace/maintenance/c05b_public_lifecycle_s1_20261022/`.
Classification: `EXTEND_EXISTING` task binding and selected lifecycle owners plus `COMPOSE_EXISTING` current Solution,
readiness, Controller, RuntimeSession, Recorder and C03a fault handling. This refresh does not grant broader capability or
qualification. Cold-start walkthrough and qualification-level/full Expert S2/S3 are NOT_RUN; Human review of this public
API/capability-sensitive route remains pending.

**C02b-R1 MuJoCo typed raw-force bounded slice (2026-10-22):** `snapshot_v2()` now projects the existing
`_MuJoCoSession` reset/completed-step cache for the exact Scene-v3 Panda R1 candidate. Admission is call-specific and
requires the exact Artifact/Scene/source closure and XML, actual `ProductionCanonicalPandaController` with hand-origin TCP,
compiled `ControlBindingPlanV1`, `panda-main/actuator8` signed N, strict MuJoCo CPU profile at 100 Hz / five 2 ms steps, and
MuJoCo package/runtime 3.8.1 plus the audited native binding/core SHA-256 values in the [receipt](../../../docs/module/task_env/goal/Phase_II/C_Development_Record.md#c02b).
Reset uses the existing `mj_forward()` over the final reset state; each native step preserves its pre-integration actuator-force
cache. Typed reads do not call `mj_forward()` or advance physics. Existing `control_feedback()` remains the sole signed-to-closing
conversion. Shared provider manifests and `snapshot_v1()` stay force-free; legacy no-plan and Position routes remain compatible.

Typed-force/admission/cache S1 plus targeted Position/H5/C02a compatibility passed **35 tests**; the independent MuJoCo CPU
reset→typed publication→real R1 compute/apply→five native steps→next publication S2 passed **1 test**. Evidence and logs are in
ignored `workspace/maintenance/c02b_r1_mujoco_typed_force_20261022/`. This closed only the MuJoCo typed-force gate for the exact
candidate/build at that receipt's checkpoint. Full structured R1 behavior/recording was not yet run then; its later bounded
result and current declared-intersection engineering-exit disposition are recorded above. P99 subsequently gained the explicit public Position mainline described above; the R1 route remains diagnostic. Dual-Entity R1, CUDA, other MuJoCo builds/transmissions,
legacy PickCube plan migration and Qualification remain unadmitted or unverified; C05c diagnostic evidence remains separate.

## C02c bounded Position instance switch

Only the explicit single-Panda `SelectedReferenceEnv.from_position_candidate()` route has a bounded
`switch_position_controller(candidate)` operation. Start Generic H5 v3 recording at reset, execute to a complete
nonterminal boundary, then pass a fresh `PandaPositionServoProfileV1` built from the same Artifact/source with a distinct
ActionConfig. The switch requires identical Action schema, hand-origin Frame/TCP, Scene/Artifact/source closure, required
state, 100 Hz / five 2 ms timebase and actuator/writer ownership. It validates before mutating the current Profile or its
memory; the current Position algorithm has no accumulated control-law state, and its Profile cursor carries plan,
episode/reset identity, next step and activation boundary. The final RuntimeSession commit seeds that cursor at the current
control step without calling `reset()`.
`reset()` remains restricted to step 0/time 0. Switching itself emits one existing BoundaryEventV1 at T but does not compute,
apply, step physics or append a transition. The next ordinary T→T+1 step is the first new target and applied acknowledgement.
An old-identity target must fail before Provider dispatch. Another switch is refused until the new instance has one complete
target/ack transition; that transition records the switch ID. If the episode ends first, its end event says effective/not-applied.
If event recording fails after the active Profile commit, the existing C03a fault latch blocks more steps and the EpisodeEnd
event carries request/identity/boundary details and a failure receipt; no physical rollback is claimed. The selection lasts for
the active episode; reset rebuilds the candidate builder's configured Profile.

This route requires an active Generic H5 v3 Recorder and a live, aligned public boundary. It is tested only for the explicit
single `panda-main` Position candidate on GeoPhys CPU and MuJoCo CPU. It does not enable dual-Entity switching, R1/force-aware
switching, NutAssembly Guard, Assembly, Camera observation, another Profile/provider/backend or general arbitration, and
does not grant general C02c switching or Qualification; C02b bounded exits are recorded separately. See the [C02c acceptance receipt](../../../docs/module/task_env/goal/Phase_II/C_Development_Record.md#c02c).

**Refresh receipt (2026-10-22):** source checkpoint `5610f8a` on `codex/phase-ii-c03b`; public caller is the explicit
`SelectedReferenceEnv.from_position_candidate()` route; owners inspected are `PandaPositionServoProfileV1`,
`RuntimeSession` control admission, `SelectedReferenceEnv`, and `TransitionRecorder`/Generic H5 v3. Cold-start route verified:
build the existing A05 Position candidate, start v3 recording at reset, switch only at an aligned complete boundary, step once,
then verify event/transition/state with `load_structured_control_records_h5()`. Evidence is bounded to the two recorded CPU
provider intersections; 16 S1 checks and independent GeoPhys/MuJoCo S2 probes pass. Skill metadata/link checker passes; the
system `quick_validate.py` is not installed on this host. Maintainer review remains pending.

C05a versioned storage is opt-in. Generic H5 v3 is read with
`task_env.recorders.load_structured_control_records_h5()`; training projection is accepted only by
`load_structured_training_actions_h5()` after exact one-writer schema/order and stored numeric-value checks.
Canonical outer v1 is decoded by `task_env.trajectory.canonical.load()` and can use its `training_actions()` explicit
projection. Execution stream v3 uses `task_env.trajectory.canonical.execution.load()` or its bounded
`streaming.load_streaming()` reader. The old generic H5, canonical outer, and execution schemas keep separate readers;
do not use storage equality as replay evidence. See the C02a/C05a receipts in the Phase II C and execution-order docs.

## Phase II C04 observation and info contract

Generic `BaseTaskEnv` uses its existing ObservationBuilder and `ObservationSchema`; inspect
`env.metadata["observation_schema"]` for required leaf paths, shape, dtype, unit, frame, boundary-time reference, and
visibility. Exact group membership and order are enforced. `state`, `privileged_state`, and the historical
`private_state` namespace have distinct meanings; preserve `private_state.robot_base_pose_world` and fail when a required
snapshot source is unavailable instead of substituting zeros.
The bounded Panda builder contract also uses `privileged_state.<object>_body_pose` for the object's measured world pose
at the same reset/step boundary; it does not alias or absorb the legacy private robot-base pose. Required `applied_ctrl`
feedback is part of step info and its absence fails validation.

`env.metadata["info_schema"]` declares reset/step facts, required action/control feedback, optional diagnostics, and optional
camera capture references. Reset and step `info["simulation_time_s"]` comes from that boundary's RuntimeSnapshot; an absent or
invalid public clock fails result construction and leaves the existing lifecycle faulted. `ObservationConfig.include_diagnostics`
defaults to `True` for output compatibility. Turning it off omits clipping flags only; task metrics/evaluation, requested and
applied control feedback, controller targets, universal action, physics and clocks remain available and unchanged.
`info["camera_capture"]`, when present, points to `SensorObservation.camera_metadata` and identifies the same elapsed-step/time
boundary. This is a metadata reference only; it does not establish D04 image/depth behavior.

The C04 bounded receipt records real Pendulum GeoPhys CPU reset/step schema, time and diagnostics checks plus Panda builder-level
private-state contract checks. The generic Panda `BaseTaskEnv` route currently fails earlier at missing Stage 1 scene composition;
do not report this receipt as real Panda Controller/physics qualification. See the [C04 receipt](../../../docs/module/task_env/goal/Phase_II/C_Development_Record.md#c04).


## D01a evidence-baseline test routing

The historical A05 axis-change test in `task_env/diagnostics/tasks/test_phase_ii_d01a_scene_materialization.py`
is bound to GeoPhys `4436787e9cb85ce519506a2a9af86d1eeec9de2d`. On the one known current pin `a53a8cfe` it reports
HISTORICAL_NOT_APPLICABLE before materialization, with explicit replacement-entry navigation; unknown pins still fail.
Its exact pin assertion remains, and regression receipts use exclusive creation under pytest tmp_path to preserve old Evidence.
The same owner's `test_b02_plan_consumes_the_exact_a05_v3_scene_identity` now requires `a53a8cfe` and really runs
source/reset/realization/step/close. Existing closure/Frame/Joint/identity/tolerance rejection tests still run.
Public candidate/H5 and dynamic pairing retain their P99/D05b owners above; a historical skip does not prove either route.
The preparation run reports 12 passed / 1 historical-not-applicable; expensive native campaigns were not rerun.
See the [independent-review handoff](../../../docs/module/task_env/goal/Phase_II/05_Architecture_Review_and_Execution_Order.md#evidence)
for source commits, precise commands, limits and pending Human decisions. This is test/document routing maintenance, no new feature.


## Phase II documentation consolidation navigation (2026-10-22)

The maintained Phase II directory now contains 01–05 plus A/B/C/D development records. Goal contracts, current dispositions and historical evidence have separate owners; use [05](../../../docs/module/task_env/goal/Phase_II/05_Architecture_Review_and_Execution_Order.md) for the 20-parent/33-slice status and precise deferred/diagnostic boundaries. Old report links now resolve to the relevant development section; original full reports remain recoverable at Core a5ba537. This refresh changes documentation navigation/status wording only. It reuses the existing public factory, RuntimeSession, typed-state, external Solution, Recorder and Camera owners, introduces no new API or capability, and leaves qualification review to the maintainer. Static Skill/link checks and the consolidation receipt are under ignored workspace/maintenance/phase_ii_docs_consolidation_20261022_001/. No native campaign was rerun for this navigation change.


## Phase II maintainer scope freeze (2026-10-23)

The [scope decision](../../../docs/maintenance/phase_ii_scope_freeze_20261023/maintainer_scope_decision.yaml)
reuses ACCEPTED_SCOPED_CORE for Phase II Scoped Engineering Acceptance at Core 90071ace / GeoPhys a53a8cfe / pinned Menagerie.
The [05 current status entry](../../../docs/module/task_env/goal/Phase_II/05_Architecture_Review_and_Execution_Order.md)
remains canonical for 20 parents/33 slices/P00/P99. Both P99 bounded runtime exits are accepted; the candidate is not a newly frozen Task.
B04a historical H5 originals remain ACCEPTED-DEFERRED/MISSING_RAW_EVIDENCE. C05c native host Reader is an accepted diagnostic exception,
not a normal-frequency contract. Camera policy/TransitionRecorder consumers and general switching/Assembly remain outside the accepted implementation envelope.
Historical refresh receipts saying review was pending retain their signing-time meaning; the current scoped acceptance is the decision above.
Release promotion/main/tag/GitHub Release and new Formal Qualification are not authorized by this freeze.
Six next-stage themes are candidates only in the existing [Roadmap](../../../docs/roadmap/README.md#phase-ii-01-candidate-handoff);
do not create or implement Phase II-01 Goals without separate authorization. This refresh changes status navigation only, no API/example behavior.

## Phase II-01 fixed Attachment candidate (R03b/R03c, 2026-10-28)

`FixedAttachmentPlanV1` is an advanced immutable intent exported by
`task_env.artifacts`; `validate_fixed_attachment_scene()` and
`lower_fixed_attachment_sources()` extend the existing Assembly/source owners.
The bounded candidate binds two separate canonical Scene-v3 Entities to the
unchanged Menagerie Panda Arm and Hand sources, explicit mount transforms,
license/source-closure hashes and complete native-name maps. One existing
MuJoCo RuntimeSession owns the attached native model and its model-bound
receipt.

The current task-owned `build_fixed_attachment_candidate()` path has provider-
free S1 and bounded MuJoCo 3.8.1 CPU S2 evidence for exactly this source pair,
seed 31, ResetPlan and 2 ms × five-step timebase. Its current result is
`ACCEPTED_BOUNDED_S1_S2` after Sol review. Static admission also rejects
coherently rebound Scene Joint topology/type/axis/pose or Asset provenance
that disagrees with the pinned source; 99 provider-free checks and the actual
19-case static gate passed. Sol reused the two original native trials,
independently checked 256 motion boundaries plus both resets, and added no
native execution. This is not a
registered `make_env()` route, a general multi-Entity/Attachment capability,
or Qualification. R03c attempt001 adds an opt-in two-Entity Position-leaf
candidate and passed 83 selected provider-free S1 tests. The first authorized
native start verified the pinned MuJoCo CPU identity but stopped during public
reset admission on the Entity-scoped Attachment tendon key versus the Hand
leaf logical tendon identity, before any forward or step. The second and final
authorized start stopped before provider import because the retry runner did
not accept its already-appended ledger row. A provider-free retry-counter fix
and S1 rerun passed; the native budget is exhausted, with no real episode/H5
or S2/S3 result. Sol reviewed the static implementation and added real Core
admission→public Env reset/step S1 with native IO stand-ins, coherent Ack/slot
tamper checks, strict physical thresholds and a shared pre-import execution
preflight. The current 90 provider-free tests pass; the state is
`S1_REVIEWED_NATIVE_PENDING`, not S2/S3 acceptance. Use the existing
`r03c_freeze` explicit output/snapshot/prompt and `r03c_attached_leaf_probe
--preflight-only` before any separately authorized new native window; never
reuse attempt001's spent two-start budget. Read the current scope and limits in the
[R03 contract](../../../docs/module/task_env/goal/Phase_II_01/03_R03_Physical_Attachment.md)
and the current materialization boundary in [Public API](../../../docs/module/task_env/public-api.md).

R03c attempt002 update (2026-10-28): its one authorized MuJoCo 3.8.1 CPU
native start verified runtime/API identity, reset E1 and called one `mj_forward`,
then failed when the runner passed `JointReference` values to
`RuntimeSession.snapshot_v1()`, which requires `JointDefinition` values from
the canonical Scene. It recorded one materialization/reset, zero `mj_step` or
outer intervals, no episode/H5, and no RSS sample; independent H5 readback did
not run. The task-owned runner mapping was repaired after preserving the raw
failure, and one provider-free S1 regression passed. This repair is not
native-verified and no retry is permitted in that window. Sol reviewed the
source repair and added four actual runner snapshot configurations through real
Core reset/step with synthetic native IO/geometry; the current R03c module has
20 provider-free passing checks. The prior shared preflight checked frozen
identity/ledger, not this runner publication path. Status remains
`S1_REVIEWED_NATIVE_PENDING`, with S2 incomplete/S3 not run; this does not add
Provider admission, general Attachment support or Qualification. Keep
attempt001 bytes and attempt002 failure/freeze/ledger separate at their ignored
workspace Evidence paths.

R03c attempt003 update (2026-10-28): the separately authorized one-start
MuJoCo 3.8.1 CPU window completed four 64-transition/65-observation episodes
and closed four H5 files. The independent provider-free reader read all four,
reported 256 transitions/260 observations, and rejected all 48 copy-only
tamper cases. After E4 close, the runner raised `UnboundLocalError` because
`native_log_bytes` had not been initialized while assembling the final receipt;
no `native_result.json` was written. The aggregate reader therefore returned
`OFFLINE_READBACK_INCOMPLETE_OR_FAILED`, and R03c S2/S3 remain incomplete.
After this consumed native window, the runner's output-byte initialization order
and the synthetic fresh-window test's stale protected-hash fixture were fixed;
the focused provider-free module suite passed 20 cases. Neither correction was
native-verified. Keep the original failure and H5s; do not retry this window,
claim general Attachment/Provider support or Qualification, or start another
slice. Sol review is pending in ignored
`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r03c_003/`.

R03c attempt003 Sol review (2026-10-28): accepts the four-episode execution
facts and post-run correction, while S2/S3 remain incomplete (exit 1, no final
native receipt). The existing probe now delegates its post-episode closeout to
a provider-free helper and publishes the final receipt after budget/progress
writes. The focused suite has 33 passing cases, including 13 closeout checks;
these synthetic closeout facts do not prove dynamics. The next package is
attempt004, same source/oracles and one separate native start. No new native
execution, Qualification or other slice follows from this review. See ignored
`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r03c_003/sol_review.md`.

R03c attempt004 execution (2026-10-28): one bounded MuJoCo 3.8.1 CPU start
on frozen input HEAD `4ac7284a4cf770f28a1c5d1f9c81337a6b39c66d` completed
four same-public-Env Arm/Hand Position episodes and published the formal
native receipt. A separate provider-free process read the four closed H5s,
verified 256 transitions/260 observations and rejected 48/48 copy-only tamper
cases. Current exact-scope status is
`BOUNDED_ATTACHED_LEAF_PUBLIC_ENV_S2_S3_PASS_PENDING_SOL_REVIEW`; the focused
33-case S1 was reused, not rerun. This result is limited to the frozen Panda
Arm+Hand source, MuJoCo 3.8.1 CPU, seed 31, 2 ms × 5 and four configurations.
It does not establish general Attachment/Provider support, task success or
Qualification. Preserve attempt001–003 originals; attempt004's one-start
budget is consumed and no other slice starts before Sol review. Evidence is in
ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r03c_004/`.

R03c attempt004 Sol review (2026-10-28): the exact Panda Arm+Hand, two
Position-writer, MuJoCo 3.8.1 CPU, seed 31 and 2 ms × 5 four-configuration
public Env/Recorder/reader intersection is `ACCEPTED_BOUNDED_S2_S3`. The
50-file attempt manifest, 16 frozen source files, receipt, native trace and
four H5 hashes/readback were reviewed; 33 provider-free S1 checks were reused.
This does not grant general provider/Attachment admission or Qualification.
Evidence and the Sol review remain in ignored workspace maintenance records.

F01 attempt002 execution (2026-10-29): isolated Isaac Sim 6.2.0.0 metadata,
installed public-source/API inventory and 11-case provider-free diagnostic S1
passed. The first bounded Kit process stopped at `app_start` because the
non-interactive NVIDIA Omniverse EULA had not been accepted. After maintainer
confirmation, the one permitted second start failed importing
`isaacsim.robot_motion.examples` before scene/physics; the worker receipt
reports zero steps and a successful `app_closed` flag, while the parent
observed process exit `-11` after 821.487 seconds. Both independent readers
rejected the native gates; the two-start budget is consumed, so F01 has no
native baseline and F02 remains held. This is not a Core Isaac provider,
current Panda import, task-harness asset success or Qualification. See the
[Phase II-01 execution record](../../../docs/module/task_env/goal/Phase_II_01/07_Execution_Order_and_Acceptance.md).

F01 attempt003 Sol acceptance (2026-10-29): the preserved attempt002 failures
remain failed history. The bounded Isaac Sim 6.2.0.0 official Panda + rigid
body run completed two GPU PhysX rounds on `cuda:0`; the worker exited 0,
486 physics steps/4.05 simulated seconds stayed within budget, the independent
reader passed 32/32 gates, and targeted provider-free S1 passed 20/20.
Attempt003's 42-file manifest and attempt002's 53-file original manifest both
verified. Sol replayed the reader against the exact path-bound runtime source
copies and reproduced 32/32; its initial replay from the current checkout
rejected the harness-specific supervisor hash, which differs only in the
attempt, lock, and interpreter paths. The bounded result is
`ACCEPTED_BOUNDED_F01`; it does not establish a Core Isaac provider, current
Panda import, general Isaac capability, or Qualification. F02 remains held and
was not started.

Maintainer preference from 2026-10-29: future Isaac Sim native verification
defaults to CUDA GPU PhysX (`cuda:0`, `gpu_dynamics=true`). Freeze and verify
the device and GPU process evidence in each run package; use a CPU recipe only
when the maintainer explicitly specifies it for that package. See the
[Phase II-01 F01 closeout](../../../docs/module/task_env/goal/Phase_II_01/10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md#f01-attempt003-sol-acceptance).


## F05 attempt001 source/control result (2026-10-30; partial, pending Sol review)

F05 attempt001 added an internal USD source composer and model-bound GeoPhys force-drive receipt in the existing source/control owners. Menagerie local-validated USD passed public import/host lowering using isolated provider candidate commit `41f8b517...`; this is not evidence for the Core checkout's pinned `a53a8cf...` provider. The actual Core Position route, Recorder, independent H5 reader and close owners passed the bounded synthetic S1 with two episodes. Keep `synthetic_fixture`, `runtime_admitted=false`, and `source_verified=false`.

The frozen official Panda source was rejected by public GeoPhys import at `/panda/panda_link0` because authored `maxDepenetrationVelocity` is infinite. Do not remove the source property or treat importer retention as consumption. Production GeoPhys USD materialization remains rejected; no GeoPhys physics, Isaac, MuJoCo USD, S2/S3 or Qualification claim follows. See [F05 execution result](../../../docs/module/task_env/goal/Phase_II_01/10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md#f05-attempt001-execution-result).
