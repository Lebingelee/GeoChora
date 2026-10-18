# P2.0 retrospective — v1.1.0 release candidate

**Status:** `RELEASE_CANDIDATE — NOT_PUBLISHED`
**Historical S5-B source baseline:** public `develop` `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`
**Current C8 execution:** [Ordinary candidate paths absent after manual handling; residual holds retained](c8_manual_cleanup_final_report.md). Exact batch approval is no longer pending.

**Local historical-metadata preservation commit:** `10dd76712204225592cef9b37d8889dbbcfde2e6`

This retrospective compares the original P2.0-A workspace/evidence objective and P2.0-B Core-consolidation objective with the implementation now on public `develop`. It distinguishes implementation, bounded regression, qualification, documentation, and work still awaiting approval. It does not grant new Qualification or represent completion of Phase II.

## Current release-candidate readback

The final-review readback on 2026-10-18 found public `main` at
`e4e39883fbe01d4be4b172a53a535ef0095b3d64`, public `develop` at
`c679267790726d3e34d080a133535c2c308a7a55`, and the public `v1.1.0` branch at
`e0e861998711f7ec5e1f10784ca857dc39d7d575`. The verified 22-file L2 payload
commit `745efc6a6693a7d10407c6ddd02837a2ae574131` remains on that branch; all
22 sizes and SHA-256 values match the manifest, with representative H5 and
result JSON reads. This is a same-public-repository/account off-host copy, not a
separately administered backup. The full workspace and separate submodule
bundles remain unverified. Controller Option B is accepted, the capability
matrix is accepted only within its existing `TESTED_BOUNDED` claims, and no
new Qualification is granted. No `v1.1.0` tag, `main` update, or GitHub Release
exists; publication is not authorized. Fresh dependency installation and full
relocated-checkout regression remain `NOT_RUN`.

## Original goals and disposition

| Original intent | Current implementation and public source/API | Source commits and bounded evidence | Status and remaining limitations |
|---|---|---|---|
| P2.0-A: consolidate repository/workspace state, branches, and worktrees | Read-only branch, worktree, submodule, and L3 inventories; the frozen v1.0.0 worktree remains separately protected | C8 manifests record exact worktree state and source pins; all 65,826 ordinary candidate paths are absent after manual handling | `PARTIALLY_COMPLETED` — ordinary cleanup post-observation complete; B registered worktree and all original holdouts remain. Storage safety remains open. |
| P2.0-A: govern Evidence ownership, preserve source recovery, and protect v1.0.0 decisions | `docs/maintenance/p2_0_part_a.md`, immutable v1.0.0 records, source recovery manifests, and L1/L2 inventory | Local C8 commits include `10dd767`, `61a786a`, `8c4da3a`, and `413fc48`; the pre-execution L1 baseline has 84 files and L2 has 22/22 files (24,563,669 bytes), rechecked against the C8 manifest; subsequent factual documentation changes are versioned L1 migrations | `PARTIALLY_COMPLETED` — L1 is public; L2 is remotely hash-verified on the same GitHub repository/account, but not separately administered. Full-workspace recovery remains unverified and `/dev/sda` risk is open. |
| P2.0-A: remove redundant development outputs while retaining decision provenance | 37 exact P1.8 decision/provenance records are versioned under `docs/releases/v1.1/evidence/historical_retirement/`; A/B/C1/C2 allowlists are local | Historical record hashes were byte-compared; the final batch manifests pass sidecar and protected-inode checks | `PARTIALLY_COMPLETED` — assistant execution stopped on the storage counter; maintainer manual handling left all ordinary candidate paths absent. No per-file user unlink receipts exist. C1 bundle, three P1.1 artifacts, 516 C6 paths, and two symlinks are held. |
| P2.0-B: provide minimal, parameterized authoring, task-local semantics, and a clear public construction API | Four-file `task_env/tasks/pick_cube/` and `task_env/tasks/nut_assembly/`; `task_env.make_env` exposes `pick-cube-p16-reference-v1` and `nut-assembly-outcome-reference-v1` | S2-C1/C2 commits include `13063f8`, `38f18f3`, `5b00580`, `ce1cd78`, `4d6d65c`; provider-free and four provider/task full-route receipts are preserved as bounded evidence | `COMPLETED` for the selected routes; not a new formal Qualification. |
| P2.0-B: preserve Artifact identity and task behavior while reducing historical task versions and clarifying reusable asset ownership | Selected PickCube P1.6 and NutAssembly Outcome V1 implementations own task semantics/reset/scene choices; reusable assets remain with object/assembly owners | S1/S1.6 commits `d01cc3b`, `0dde256`; S2 authoring commits above; current L2 stores final accepted routes | `COMPLETED` for active construction. Historical source and raw replay data remain subject to C8 decisions. |
| P2.0-B: retire obsolete task/runtime routes and GeoChora-owned GeoPhys-coupled implementations while preserving generic Core contracts | Go2-specific implementation retired in S3; GeoChora static-template solver retired in S4; generic RL, Batch/Device/Vectorization, merged-scene, GeoPhys adapter and Renderer contracts remain | S3 `9c6548d` / receipt `5b8c901`; S4 `0ff2d846`; focused provider-free regression and migration records | `COMPLETED` for the approved retirement scope. No native GeoPhys Rigid Batch qualification; external PhysPi/Skill dependency review is incomplete. |
| P2.0-B: consolidate developer workflows and define the Renderer ownership/public-interface boundary | S4.5 examples use `make_env`, canonical Recorder, existing learning adapters, and current Renderer/Camera APIs | S4.5-A `5d57272` / review `5910572`; S4.5-B `929dd8f` / review `fc12780`; CLI fix `bee498d`; 129-test and 146-test provider-free receipts plus bounded smokes | `PARTIALLY_COMPLETED` — no new Native Flora qualification, Physics × Renderer interoperability, broad training, or manipulation PPO capability. |
| P2.0-B: establish a stable Core release baseline | v1.1.0 candidate package, migration guide, capability matrix, and release evidence index under `docs/releases/v1.1/` | S5-A/B `e0e4dbc`, `2fb60de`; candidate capability claims remain `TESTED_BOUNDED` where applicable; L2 copy is verified on the public candidate branch | `PARTIALLY_COMPLETED` — capability matrix and migration disclosure are accepted within bounded claims. Full-workspace/separate-admin backup and storage risk remain open; release publication is not authorized. |

This matrix distinguishes implementation, bounded tests, documentation, and Qualification. `TESTED_BOUNDED` does not mean `QUALIFIED`; source or recovery metadata does not make missing raw data replayable.

## Implementation stages

| Stage | Current source / record | Evidence boundary and outcome |
|---|---|---|
| S1 / S1.6 | `d01cc3b` task-owned reference construction; `0dde256` NutAssembly Outcome Completion V1 | Bounded construction and two-provider execution receipts. NutAssembly physical outcome and original strict Expert lifecycle status remain separately recorded. |
| S2 | PickCube authoring commits `13063f8`, `38f18f3`, `5b00580`; NutAssembly `ce1cd78`, `4d6d65c`; integration records `a637209`, `8b950e9` | Minimal selected routes and updated API/migration documentation. No duplicated TaskArtifact schema. |
| S3 | `9c6548d`; S3 receipt `5b8c901` | Go2-specific paths retired; generic RL/Batch/Device/Learner and Renderer contracts retained. |
| S4 | `0ff2d84` | GeoChora static-template solver retired; generic batch and supported provider adapters retained. |
| S4.5 | `5d57272`, `5910572`, `929dd8f`, `fc12780`, `bee498d` | Examples, recording/inspection and learning/rendering workflows consolidated; trajectory CLI forwarding fixed. Smoke tests do not establish general training or renderer interoperability. |
| S5-A/B | `e0e4dbc`, `2fb60de` | v1.1.0 inventory and candidate release docs; capability labels remain bounded and historical decisions remain unchanged. |
| S5-C1–C8 | C1–C6 records in current docs; C7/C8 exact inventories and C8 local outputs | Exact four-batch retirement authorized on 2026-10-18; assistant storage-stop followed by manual ordinary cleanup; all ordinary paths absent, 9 post-cleanup checks passed, L1/L2 verified intact. Registered worktree and 522 holdouts remain; no backup waiver, tag or publication. |

## What P2.0 enables next

P2.0 leaves a smaller TaskEnv Core surface, two selected task routes, explicit provider/runtime admission, current source-based examples, and a bounded release-evidence baseline. That makes it possible to choose one benchmark family and compare its native workflow with a canonical TaskEnv/Harness workflow.

The future Phase II direction remains research and engineering work: benchmark-to-TaskArtifact adaptation, provider reuse, task/controller/observation mapping, bidirectional trajectory conversion and validation, a stronger evidence-grounded Harness, and governed PhysPi integration. LIBERO, RoboCasa, RoboTwin, and RoboDojo remain candidates; none is represented here as generally interoperable. Autonomous RSI, full PhysPi integration, complete provider interoperability, and Phase II completion are not claimed.

## Qualification and release boundary

The four PickCube/NutAssembly × GeoPhys/MuJoCo full routes remain `TESTED_BOUNDED` at their recorded source/configuration identities. H5 storage validation is not D0 replay. The GeoPhys NutAssembly accepted physical outcome does not erase the original strict Expert failure. No new P1.8 FULL, D0–D2, manipulation-checkpoint, general manipulation PPO, native GeoPhys Rigid Batch, or native Flora qualification is granted by this retrospective.
