# P2.0 retrospective — v1.1.0 release candidate

**Status:** `RELEASE_CANDIDATE — NOT_PUBLISHED`
**Reviewed source baseline:** public `develop` `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`
**Local historical-metadata preservation commit:** `10dd76712204225592cef9b37d8889dbbcfde2e6`

This retrospective compares the original P2.0-A workspace/evidence objective and P2.0-B Core-consolidation objective with the implementation now on public `develop`. It distinguishes implementation, bounded regression, qualification, documentation, and work still awaiting approval. It does not grant new Qualification or represent completion of Phase II.

## Original goals and disposition

| Original goal | Implemented source/API and evidence | Status | Remaining boundary |
|---|---|---|---|
| P2.0-A: establish workspace Evidence ownership, preserve immutable v1.0.0 decisions, and make cleanup provenance-driven | `docs/maintenance/p2_0_part_a.md`; frozen v1.0.0 tree and tracked Phase-I decisions; S5-C3–C8 inventories | `PARTIALLY_COMPLETED` | L1/L2 integrity is verified locally. Historical workspace cleanup has not run; the independent backup and single-disk storage risks remain open. |
| P2.0-A: reconcile local branches, worktrees, and historical source recovery | Local Git/worktree inventories, source-recovery manifests, C8 registered-worktree inventory | `PARTIALLY_COMPLETED` | The S5-B detached checkout and historical bundle are still present. Worktree removal and historical-data retirement require exact batch approval. |
| P2.0-A: remove redundant development outputs while preserving decision records | 37 byte-identical P1.8 decision/provenance records are now tracked under `docs/releases/v1.1/evidence/historical_retirement/`; other exact candidates are listed in C8 manifests | `BLOCKED` | No deletion has been authorized or executed. The historical P1.8 source bundle remains a holdout. |
| P2.0-B: keep one small, task-owned active authoring route for each selected task | PickCube and NutAssembly each use `task.py`, `solution.py`, `config.yaml`, and `__init__.py`; current UIDs are `pick-cube-p16-reference-v1` and `nut-assembly-outcome-reference-v1` | `COMPLETED` | Historical recovery remains in immutable refs and Evidence; no old task identity is silently redirected. |
| P2.0-B: move task semantics, reset, scene composition, selected solution, and artifact construction into concise task-owned implementations while reusing Core contracts | S2-C1/S2-C2 authoring slices; selected TaskArtifact identities, provider-neutral bindings, and the four-file task directories | `COMPLETED` for selected routes | This does not introduce a second task schema or new runtime/physics abstractions. |
| P2.0-B: reduce multi-version task branches and clarify reusable asset ownership | Selected PickCube P1.6 and NutAssembly Outcome V1 remain active; reusable geometry/assets stay with existing object and assembly owners | `COMPLETED` for selected active paths | Historical candidates and raw evidence remain subject to the separate C8 retirement decision. |
| P2.0-B: preserve task semantics, Artifact identity, and selected expert behavior while simplifying construction | S1 task-owned builders (`d01cc3b`, `0dde256`); S2 construction/consolidation (`a59840f`, `8ff33b3`, `13063f8`, `38f18f3`, `5b00580`, `ce1cd78`, `4d6d65c`) | `COMPLETED` | Four selected manipulation/provider intersections are `TESTED_BOUNDED`; they are not new formal qualifications. |
| P2.0-B: retire obsolete active task paths and Go2-specific implementation while preserving generic RL/Core contracts | S2-B2 and S3 retirement; S3 implementation `9c6548d69cbddb63c63727b7210814c1881c5180`; integration record `5b8c901` | `COMPLETED` for approved active scope | Generic RL and vectorization interfaces remain; retired Go2 tasks are not a currently qualified route. External historical consumers were not exhaustively inventoried. |
| P2.0-B: retire GeoChora-owned static-template physics without removing generic batch contracts | S4 implementation `0ff2d846a36c7014d2b40a530f52d99e64266ff9`; static-template requests fail closed; merged-scene and GeoPhys adapter paths remain | `COMPLETED` for GeoChora-owned solver retirement | No native GeoPhys rigid-batch qualification was added. Generic parallel physics and provider capability were not expanded. |
| P2.0-B: consolidate current developer workflows and clarify Renderer ownership | S4.5-A `5d57272`, S4.5-B `929dd8f`, CLI forwarding fix `bee498d`; examples use public `make_env` and existing Recorder/Renderer contracts | `PARTIALLY_COMPLETED` | Bounded Pendulum and rasterizer smokes exist. No new native Flora qualification or Physics × Renderer interoperability was established. |
| P2.0-B: produce a stable v1.1.0 Core release baseline | Candidate package under `docs/releases/v1.1/`; current public `develop` includes S2–S4.5 and S5-A/B candidate documents | `PARTIALLY_COMPLETED` | v1.1.0 is not published. Breaking changes are documented under project-specific versioning. Backup, final retention approval, capability-matrix approval, and publication authorization remain open. |

## Implementation stages

| Stage | Current source / record | Evidence boundary and outcome |
|---|---|---|
| S1 / S1.6 | `d01cc3b` task-owned reference construction; `0dde256` NutAssembly Outcome Completion V1 | Bounded construction and two-provider execution receipts. NutAssembly physical outcome and original strict Expert lifecycle status remain separately recorded. |
| S2 | PickCube authoring commits `13063f8`, `38f18f3`, `5b00580`; NutAssembly `ce1cd78`, `4d6d65c`; integration records `a637209`, `8b950e9` | Minimal selected routes and updated API/migration documentation. No duplicated TaskArtifact schema. |
| S3 | `9c6548d`; S3 receipt `5b8c901` | Go2-specific paths retired; generic RL/Batch/Device/Learner and Renderer contracts retained. |
| S4 | `0ff2d84` | GeoChora static-template solver retired; generic batch and supported provider adapters retained. |
| S4.5 | `5d57272`, `5910572`, `929dd8f`, `fc12780`, `bee498d` | Examples, recording/inspection and learning/rendering workflows consolidated; trajectory CLI forwarding fixed. Smoke tests do not establish general training or renderer interoperability. |
| S5-A/B | `e0e4dbc`, `2fb60de` | v1.1.0 inventory and candidate release docs; capability labels remain bounded and historical decisions remain unchanged. |
| S5-C1–C8 | C1–C6 records in current docs; C7/C8 exact inventories and C8 local outputs | Evidence retention and historical retirement preflight only. No deletion, backup waiver, tag, or publication has occurred. |

## What P2.0 enables next

P2.0 leaves a smaller TaskEnv Core surface, two selected task routes, explicit provider/runtime admission, current source-based examples, and a bounded release-evidence baseline. That makes it possible to choose one benchmark family and compare its native workflow with a canonical TaskEnv/Harness workflow.

The future Phase II direction remains research and engineering work: benchmark-to-TaskArtifact adaptation, provider reuse, task/controller/observation mapping, bidirectional trajectory conversion and validation, a stronger evidence-grounded Harness, and governed PhysPi integration. LIBERO, RoboCasa, RoboTwin, and RoboDojo remain candidates; none is represented here as generally interoperable. Autonomous RSI, full PhysPi integration, complete provider interoperability, and Phase II completion are not claimed.

## Qualification and release boundary

The four PickCube/NutAssembly × GeoPhys/MuJoCo full routes remain `TESTED_BOUNDED` at their recorded source/configuration identities. H5 storage validation is not D0 replay. The GeoPhys NutAssembly accepted physical outcome does not erase the original strict Expert failure. No new P1.8 FULL, D0–D2, manipulation-checkpoint, general manipulation PPO, native GeoPhys Rigid Batch, or native Flora qualification is granted by this retrospective.
