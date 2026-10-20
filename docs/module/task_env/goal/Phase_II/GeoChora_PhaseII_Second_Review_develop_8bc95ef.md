# GeoChora Phase II A–D — Independent Second Architecture Review

> Review date: 2026-10-20<br>
> Target branch: `develop`<br>
> Reviewed HEAD: `8bc95ef4a38b6adbc61166c05b5bb5c2221065a6`<br>
> Implementation baseline: `f292df149f41520b484ff27cf2ff78a584903013` (both subsequent commits are docs-only)<br>
> Disposition: **CONDITIONAL ACCEPT / TARGETED REVISE BEFORE IMPLEMENTATION**. Approve **P00 AUDIT_ONLY** now; do **not** authorize a continuous A01–D05 implementation campaign.<br>
> Method: Read six Phase II documents from remote `develop`, canonical architecture/ownership/runtime/qualification docs and the relevant implementation. No code changes, runtime execution, or qualification claims were made in this second review.

## 1. Integrity and scope

- `a299d8b` adds five original Markdown proposals. The five SHA-256 values recorded in `05` match the five locally available originals byte-for-byte.
- `8bc95ef` modifies those five and adds `05_Architecture_Review_and_Execution_Order.md`, six Markdown planning files total; no production source, tests, Gitlinks, or qualification matrix changed.
- Independently parsed the `05` dependency table: **31 implementation slices + P00 + P99 = 33 entries**; no duplicate IDs or missing/forward references were found. Acyclic ordering is valid as stated.
- The only reported docs validation failure is plausible and directly explained by the existing `validate_docs.py`: it compares current counts with fixed consolidation inventory limits, now exceeded by new plans. We did not rerun this repository-local validator; the first Codex review's receipt is the source of that actual execution claim.

## 2. Positive decisions to retain

1. **Keep 20 parent Goals and the reviewed 31-slice skeleton**, with suffix slices and goal-specific receipts. There is no need to revert to four entirely serial stages.
2. Keep early B04a/D02a/C01a/D05a contract work and D01a real materialization proof before broader Task/Environment migration.
3. Keep a single `task_env` Core owner, no duplicate Runtime/Controller/Recorder/Task Artifact, and precise public/provider source boundaries. Use the pinned public GeoPhys `ImportedScene.ir/capability_report/solver_scene_desc/build_render_scene_desc` before proposing a new importer or IR.
4. Preserve v0 serialized bytes/hash, selected UIDs and v1.1 frozen provenance. New schema versions and explicit legacy readers are required.
5. Keep temporal semantic **read versus commit** separated; especially selected native-rate Guard callbacks must not advance task memory on every diagnostic read.
6. Preserve NutAssembly control and Solution state semantics including controller-held arm target/ramp, native 500 Hz samples, strict failure and Outcome V1; external Solution is not a mechanical relocation of `act()`.
7. Keep D4 property mapping and D5 evidence constraints within D01/D02/D05, rather than opening two new large implementation stages. E remains deferred.
8. Keep genuine runtime S2/S3 and negative-path oracles, not an interface-only or a fake Renderer qualification claim.

## 3. Required clarifications before their affected implementation slices (P0)

### P0-1 — C02b: distinguish action-validation atomicity from native actuation atomicity

**Source:** `03_Phase_C_Execution_Lifecycle.md` C.4, C.5, C02b; `05` §§2–3; actual `task_env/environment/lifecycle.py` step applies control and steps before read/evaluation, and `task_env/runtime/sessions/control.py` currently only has restricted Panda binding.

**Issue:** “atomic group execution” risks implying transactional rollback of all actuators/solver state after one controller or substep fails. That guarantee is not generally available from Physics Provider APIs.

**Change:** Specify two guarantees separately: (1) **preflight action-schema/ownership/target validation is atomic with respect to controller and physics mutations**; (2) native commands are submitted at one declared control boundary when the actual provider supports it, but any partial application must result in **FAULTED + a partial-application receipt**, not rollback or a valid synthetic transition. Declare ordering/substep synchronization and no hidden hold-last defaults. Do not claim all-or-nothing physical application without S2 evidence.

**Gate:** invalid group key/shape/NaN/overlap never calls provider; failed native commit records last known completed boundary and blocks subsequent step; a normal two-group action has a single defined sample/hold interval.

### P0-2 — C05a/C03b: `env.stop()` must traverse wrappers and terminate record/read/learner semantics coherently

**Source:** `03` C.5.3/C05a, `05` §2/§5; actual `task_env/recorders/wrapper.py` only overrides `reset`, `step`, `end_record` and auto-closes on `terminated/truncated` returned by `step`. Generic H5 v2 and canonical/execution streams have distinct terminal formats.

**Issue:** Independent `env.stop()` is **outside standard Gymnasium `step`**. A call to a wrapped environment can bypass `TransitionRecordWrapper`'s end handling; old last-transition flags cannot be changed after return. Generic third-party Gym wrappers/learners cannot be assumed to understand a stop event.

**Change:** Before C05a schema work, freeze a **wrapper-visible lifecycle command / outcome contract**: who receives stop, which layer finalizes exactly once, how consumers inspect `EpisodeOutcome`, what `truncated/terminated` means without another step, and how each old/new file reader and learner derives `end/bootstrap`. Explain explicitly that this is a GeoChora extension, **not automatically compatible with arbitrary Gymnasium wrappers**. Zero-transition stop, repeated stop, stop after failure, and recorder active/inactive must be specified.

**Gate:** wrapped `env.stop()` produces exactly one outcome/event and an inspectable terminal recording with T/T+1 unchanged; no stale episode stays recording; training conversion tests `bootstrap` versus `terminated` for task-defined stop, external truncation, and horizon; old readers reject unrecognized new schema rather than silently misdecode.

### P0-3 — D05a/P00: front-load the native cross-renderer feasibility spike

**Source:** `04` D05b/P99; actual `task_env/render/camera/api.py` explicitly rejects cross-name provider pairing, and `task_env/render/camera/mujoco.py` builds a separate static mesh-only `MjModel/MjData/Renderer` and uses `mj_forward` to update camera pose. This currently does not implement dynamic body visual synchronization.

**Issue:** The first real `GeoPhys CPU physics × MuJoCo native renderer` outcome is placed at D05b after most A–D work. An unverified rendering dependency (headless GL/EGL/OSMesa/graphics context, model mesh binding and transform update route) could block P99 very late.

**Change:** Add to **P00 technical feasibility audit** or **D05a** an independent *bounded* native probe: instantiate MuJoCo offscreen Renderer on target machine, test controlled geometry transform updates at a fixed canonical boundary, and confirm `mj_forward` does not advance the GeoPhys authoritative step/time. Check ownership/close and headless resources. This does **not** remove the formal D05b scene/Camera Admission and qualification gate, and does not count as Phase II cross-pairing implementation. If infeasible, select an explicit alternative cross-renderer route and approve its support envelope before coding D03/D04.

**Gate:** truthful PASS/FAIL/TIMEOUT/NOT_RUN and actionable root cause; no removing `physics_provider == render_provider` merely to obtain PASS.

### P0-4 — C05a: choose a canonical *new* event/action data contract before changing three existing formats

**Source:** `03` C05a, `05` §§2–3; actual `task_env/recorders/recorder.py` casts actions to flat floats, `recorders/h5.py` stacks fixed-width components, `trajectory/canonical/contracts.py` enforces its own T/T+1 layout, and `trajectory/canonical/execution.py` with `streaming.py` uses a separate strict schema and readers.

**Issue:** C05a intends to extend action tree, stop/switch/capture events, final outcome and training conversion across all three formats within a single “one bounded slice”. This risks violating the plan's own one-contract/one-owner change principle and entangling incompatible readers.

**Change:** Before implementation identify: (a) authoritative vNext action/event/outcome **value semantics**, (b) primary new storage route, (c) explicit adaptation/legacy route for each other writer/reader, (d) required vs deferred training loaders. Preserve all v0/v2 readers and tests. Codex should **SPLIT C05a into 2–3 small sub-slices if the actual caller map shows independent storage owners**; this would change the count from 31 while preserving 20 parents. Do not force all historical formats to acquire the same binary schema.

**Gate:** two complete fixture sets (old and new), version/reader matrix, T=0/T+1/terminal checks, and typed structured actions where explicitly supported. Legacy frozen recordings remain unchanged.

## 4. Scope decision requiring maintainer approval (P0-design)

### Multi-robot implementation scope is narrower than the earlier A–C vision

**Source:** `00` §1, `01` A03, `03` C02b, `05` §2: two Robot entities and identity/reference handling will be tested structurally, while an arm+hand **single Robot** is the planned real multi-group path; two-Robot real dynamics may be deferred.

This is a reasonable complexity reduction, **but it must be explicitly authorized** rather than silently labeled “multi-robot execution supported.” Given the motivating examples (two manipulators, manipulator + quadruped), recommend a **minimal two-Entity, two independently actuated groups S2 probe**, potentially far simpler than two Pandas, before claiming the Phase II action model works across robots. If even that is too expensive, adopt the precise exit status **multi-robot static binding only; multi-robot physical stepping NOT IMPLEMENTED**, and reserve capability at C02b/D01b. This is a product scope decision, not a contradiction in the document.

## 5. Important optimizations (P1)

| Area | Recommendation | Why |
| --- | --- | --- |
| **C02c critical path** | Consider making same-schema switch depend on C02b, C03b and a small real single-group switch case rather than *full* C05c NutAssembly migration. Retain task-specific prohibition for unqualified paths. | Prevents a difficult native Guard migration from blocking independent safe-switch capability; still require targeted regression for affected routes. |
| **B04a versus later schemas** | Treat B04a as a **version/discriminator/migration-rule baseline**; leave final Camera/Renderer/action event field shapes to D05a/C05a. Revalidate nested version tables before B04b. | Avoids prematurely freezing fields of a subsystem whose runtime requirement has not been confirmed. |
| **P99 exit envelope** | Separate **Phase II contractual completeness** from **specific physical/rendering qualification**. State required and allowed deferred outcomes, particularly D05b and multi-robot, and forbid an unqualified “A–D complete” claim. | Current P99 both requires D05b and permits accepted-deferred slices, which can be read inconsistently. |
| **Docs governance** | Ask maintainer for a *documented scope-specific exception or a governance policy update* to the historical consolidation count ceiling (58 → actual 64), without weakening frozen hashes/URL/doc-scope checks. | `validate_docs.py` compares root tracked docs count to a fixed consolidation-inventory limit; this is a policy issue, not a source regression. |
| **Resource budgets** | Pin expected runtime, hardware, graphics support, seed/timeouts for each S2/S3; capture worker/process-local allocator limitations. | Python `close()` may not free GeoPhys process-global resources; test timeout cannot equal PASS. |
| **Release roadmap** | After authorization, document the priority choice A–D-before-LIBERO while preserving canonical research history. | Current `docs/roadmap/README.md` prioritizes bounded LIBERO benchmark research; planning docs are not yet an approved roadmap revision. |

## 6. Review of stages

| Stage | Result | Observations |
| --- | --- | --- |
| **A01–A05** | Conditional accept | Canonical immutable Scene/Entity and instance ID logic is appropriate. Keep GeoPhys public importer and source-lowering analysis, strict source semantics, and old UID projections. A static dual-Robot fixture does not prove dynamic control. |
| **B01–B05** | Conditional accept | Stateful evaluator read/commit split is essential. Preserve action-aware Pendulum reward, native Guard vs task memory, Stage-1/Human Judge for new *frozen* tasks, v0 nested codec/hash. B04a scope should remain mainly version strategy. |
| **C01–C05** | Targeted revise | Runtime config and Entity×Group Controller direction is sound, but C02b atomic semantics, C03b wrapper-visible stop, C05a storage blast radius, and C02c dependencies require clarification. Preserve selected old routes until real evidence. |
| **D01–D05** | Conditional accept with early spike | D1–D3 only is good. Typed State/Frame, transform/geometry synchronization, Camera metadata and capability-scoped pairing are coherent. Move a small native Renderer feasibility probe forward. |

## 7. Practical next actions

1. **Approve P00 AUDIT_ONLY** on remote `develop@8bc95ef` as a source/test/resource inventory and impact analysis; do not authorize implementation yet.
2. Ask Codex to issue a **small planning amendment** addressing P0-1 through P0-4, with updated direct-predecessor map and explicit old/new storage selection. Preserve all historical commits; no need to rewrite original five.
3. Ask maintainer to choose the **multi-robot scope** and the preferred D05 cross-renderer fallback if native MuJoCo path is infeasible.
4. Approve A01 AUDIT_ONLY when P00 receipts and protection fixtures are confirmed. Only then consider A01 implementation authorization under the existing repo review process.
5. Repeat source/caller/test audit against the new `develop` after each approved Goal; documents remain **PROPOSED** until formally adopted.

## 8. Key source pointers

- Planning [00](https://github.com/Lebingelee/GeoChora/blob/develop/docs/module/task_env/goal/Phase_II/00_Phase_II_AD_Implementation_Blueprint.md), [A](https://github.com/Lebingelee/GeoChora/blob/develop/docs/module/task_env/goal/Phase_II/01_Phase_A_Core_Object_Model.md), [B](https://github.com/Lebingelee/GeoChora/blob/develop/docs/module/task_env/goal/Phase_II/02_Phase_B_Task_Semantics.md), [C](https://github.com/Lebingelee/GeoChora/blob/develop/docs/module/task_env/goal/Phase_II/03_Phase_C_Execution_Lifecycle.md), [D](https://github.com/Lebingelee/GeoChora/blob/develop/docs/module/task_env/goal/Phase_II/04_Phase_D_Physics_Rendering.md), [05](https://github.com/Lebingelee/GeoChora/blob/develop/docs/module/task_env/goal/Phase_II/05_Architecture_Review_and_Execution_Order.md).
- Canonical [ownership](https://github.com/Lebingelee/GeoChora/blob/develop/docs/global/ownership.md), [runtime](https://github.com/Lebingelee/GeoChora/blob/develop/docs/module/task_env/runtime-and-providers.md), [qualification](https://github.com/Lebingelee/GeoChora/blob/develop/docs/module/task_env/qualification.md).
- Implementation [generic lifecycle](https://github.com/Lebingelee/GeoChora/blob/develop/task_env/environment/lifecycle.py#L468-L512), [recording wrapper](https://github.com/Lebingelee/GeoChora/blob/develop/task_env/recorders/wrapper.py#L40-L75), [generic recorder](https://github.com/Lebingelee/GeoChora/blob/develop/task_env/recorders/recorder.py#L104-L145), [render admission](https://github.com/Lebingelee/GeoChora/blob/develop/task_env/render/camera/api.py#L17-L48), [MuJoCo static camera](https://github.com/Lebingelee/GeoChora/blob/develop/task_env/render/camera/mujoco.py#L15-L53), [NutAssembly hold](https://github.com/Lebingelee/GeoChora/blob/develop/task_env/tasks/nut_assembly/solution.py#L465-L489), [reviewed GeoPhys public importer](https://github.com/SCAILab-USTC/GeoPhys/blob/c665ce5028a12bb4d2afe49f05e015fa9b684a39/src/scene/scene_import.py#L296-L363).
