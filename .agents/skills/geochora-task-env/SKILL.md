---
name: geochora-task-env
description: "Use GeoChora TaskEnv public construction, expert execution, recording and evaluation routes, or locate their owners before proposing a change; apply to current task/provider workflows."
---

# TaskEnv Module Skill

Read repository `AGENTS.md` and [module README](../../../docs/module/task_env/README.md).
`task_env/` is the sole Core owner; use its public APIs. No historical chat context is required.
For the source/contract/test map read [routes](references/routes.md) when implementing a workflow or diagnosing a gap.

## Choose the actual construction branch

- Generic scalar: `from task_env import make_env`; e.g. `make_env("pendulum-v1",
  config={"runtime":{"backend":"cpu"}})`. Call reset before step and always close in finally.
  Task defaults are deep-merged with caller mapping/YAML before public-section overlay; an existing
  `ResolvedEnvConfig` is authoritative. `env.execution_plan` is a provider-free `execution-plan-v0`
  static projection only: it does not establish actual manifest support, runtime materialization, or reset realization.
- Selected PickCube: UID `pick-cube-p16-reference-v1`, config `{"provider":"mujoco",
  "backend":"cpu","horizon":6000}`; published bounded scope CPU/100 Hz/seed 31, lift-only predicate.
- Selected NutAssembly: UID `nut-assembly-outcome-reference-v1`, same flat config, seed 19/NA-S0.
  Use guarded `step_expert()` only. Do not send arbitrary external actions or use legacy UID/builders.
- Selected config accepts provider/backend/horizon only: geophys/mujoco, scalar CPU, horizon integer 1–6000.
  No render, legacy overlays, SAPIEN/Genesis or implicit batch support. Generic parallel must have explicit
  homogeneous registration and merged_scene layout; no scalar fallback.

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
[D01b bounded receipt](../../../docs/module/task_env/goal/Phase_II/04_Phase_D_Physics_Rendering.md#d01b-bounded-vnext-two-provider-receipt-2026-10-20).
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
bind the same ExecutionSpec and each camera's sync publication. Targeted S1 and real S2 passed for this single
Scene-v3 scalar-joint candidate. See the [D05b receipt](../../../docs/module/task_env/goal/Phase_II/04_Phase_D_Physics_Rendering.md#d05b-bounded-cross-provider-pairing-receipt-2026-10-22).

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
has a separate, exact call-specific claim bound to its source/Controller/plan and clean GeoPhys `a53a8cfe` CPU build;
it does not make the original binding or a generic manifest supported. Omitting the optional plan preserves the legacy
route. Admission alone is not Group dispatch, an applied acknowledgement, or real execution evidence.

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
has a separate GeoPhys CPU receipt; one new candidate now has exact plan-bound GeoPhys CPU raw-force admission and a
single real interval, but the legacy selected Artifact/source is not rebound by that evidence. NutAssembly Guard and full
C02b remain blocked. See [single-profile S1](../../../docs/module/task_env/goal/Phase_II/C02b_E_Position_Profile_S1_Acceptance.md),
[single-profile S2/H5](../../../docs/module/task_env/goal/Phase_II/C02b_E_Position_Profile_S2_Acceptance.md), and
[dual-Entity acceptance](../../../docs/module/task_env/goal/Phase_II/C02b_Dual_Entity_Position_Acceptance.md).

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

**C02b-R1 typed raw-force admission (2026-10-22):** `CanonicalStateViewV2` /
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
This does not transfer to the old PickCube selected Artifact/source, MuJoCo
typed-force support, other transmissions, full C02b, or C05b. See the
[freshness receipt](../../../docs/module/task_env/goal/Phase_II/C02b_R1_Reset_Force_Freshness_Acceptance.md)
and [typed-force receipt](../../../docs/module/task_env/goal/Phase_II/C02b_R1_Typed_Raw_Force_Admission_Acceptance.md).

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
plan identities from [typed-force receipt](../../../docs/module/task_env/goal/Phase_II/C02b_R1_Typed_Raw_Force_Admission_Acceptance.md),
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
existing stop/recording semantics remain distinct. See the [public lifecycle S1 receipt](../../../docs/module/task_env/goal/Phase_II/C05b_Public_Lifecycle_S1_Acceptance.md).

**C05b legacy external Solution S2/S3 (2026-10-22):** for the fixed `pick-cube-p16-reference-v1` legacy Artifact/source,
construct the task-owned Solution with `build_readiness_solution()`, call `reset_for_solution(solution, seed=31)`, then
`step_with_solution(solution)` at each 100 Hz control boundary. Keep the exact actual Controller, source ID/XML hash, Core
episode, Solution and ResetSample identities; this source has no Scene closure or plan identity. The bounded external Expert
and canonical-v0 disk readback passed in separate processes on GeoPhys `a53a8cf` CPU and MuJoCo 3.8.1 CPU, using five 2 ms
steps per interval. Each route has its own T/T+1, feedback/readiness, stage, Task success, Expert completion, action→target→ack,
flags and H5 readback evidence in [the S2/S3 receipt](../../../docs/module/task_env/goal/Phase_II/C05b_External_Solution_S2_S3_Acceptance.md).
Observer/append failures reuse the C03a fault latch and cannot finalize an incomplete canonical recording. This does not create
legacy R1 Stop/Event/Outcome, migrate candidate plan-bound typed force, enable MuJoCo typed force, close C02b, or grant
Qualification.

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
does not complete C02b/C02c. See the [C02c acceptance receipt](../../../docs/module/task_env/goal/Phase_II/03_Phase_C_Execution_Lifecycle.md#c02c-bounded-single-panda-position-receipt2026-10-22).

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
do not report this receipt as real Panda Controller/physics qualification. See the [C04 receipt](../../../docs/module/task_env/goal/Phase_II/03_Phase_C_Execution_Lifecycle.md#c04-bounded-observation-and-info-receipt-2026-10-21).
