# S5-C8 execution and Phase 2.0 closure status — 2026-10-18

**GeoChora v1.1.0 — RELEASE_CANDIDATE — NOT_PUBLISHED**

The maintainer explicitly authorized the four exact C8 manifest hashes on 2026-10-18 and accepted permanent C1/C2 historical raw Evidence and source-snapshot loss. Authorization is complete. Execution stopped before the first deletion because the observed `/dev/sda` SCSI `ioerr_cnt` increased from `0x7d0` (2000) at 02:23:06 UTC to `0x7d5` (2005) by 02:25:17 UTC. No manifest was regenerated after approval. No candidate, worktree, L1/L2 file, or original historical record was deleted or moved.

## Authorization and actual outcomes

| Batch | Approved SHA-256 | Approved paths | Execution | Conditional allocated upper bound |
|---|---|---:|---|---:|
| A | `a39734b52f69b11492d1d3e7b9ee5bfc2c4da938fc47bcf44607a04999822f75` | 17 | NOT_RUN — storage safety stop | 311,296 B |
| B | `500012d5e2a6e0e998cd58bcc245bac885f1b88f0e1a140fac48b9e6802186b9` | 6,792 | NOT_RUN — storage safety stop; worktree method also held | 3,317,481,472 B |
| C1 | `ff1c3e8e2db976293fd9da1f6f22a0ac3ffabb9a823f3a8d49e00b7f3f333281` | 3,382 | NOT_RUN — storage safety stop | 10,978,766,848 B |
| C2 | `f3bf52ee69e91515755f7b238d854bacf232bc98d08041bd0c50e489acd578de` | 62,254 | NOT_RUN — storage safety stop | 61,120,978,944 B |

**Actual deletion: 0 files; actual worktree removal: 0; attributable recovered space: 0 GiB; actual irreversible historical loss this execution: none.** The 75,417,538,560-byte (70.24 GiB) total is a conditional upper bound, not achieved recovery. A non-destructive `du -sx --block-size=1 workspace` observed 76,170,403,840 allocated bytes remaining. `df` observed 109,596,819,456 used and 527,471,026,176 available bytes on the filesystem; background activity and receipts prevent interpreting their variation as cleanup recovery.

## Storage stop and worktree exception

The readable current kernel log contained no new ATA/SATA/READ/WRITE storage-error line for this interval. Kernel-ring access was denied; an empty `journalctl -k` query is not clearance. Cached UDisks SMART state was updated at 02:24:10 UTC and reported no failing/bad-sector condition. That timestamp correlates with the counter increase but does not prove its cause. The receipt therefore records an **unclassified SCSI error-counter anomaly**, not a confirmed new ATA read/write failure. It cannot be dismissed or rebased to a later counter. The execution helper is latched with `STOP_STORAGE`.

A separate B prerequisite was found without attempting removal: the nested GeoPhys checkout uses its own primary repository in the parent worktree's administration area. Its git-dir equals its git-common-dir; it is not a linked-worktree registration that can be removed by the proposed nested `git worktree remove`. The installed Git manual says a primary worktree cannot be removed; worktrees with submodules require force. Force, deinit and manual recursive removal are outside the approved procedure. This worktree remains held. No failed removal was claimed or attempted. Ordinary B files remain authorized but were also untouched because the storage stop precedes A.

## Integrity and evidence

Before any governance-document update, all 84 original L1 entries (1,042,337 bytes), all 22 L2 files (24,563,669 bytes), all 72,445 candidate file entries, and all 522 pre-existing holdouts passed their expected integrity/identity checks. The approved manifests retained their exact hashes. No L1/L2 path or inode was admitted for deletion. All 37 byte-identical historical metadata records remain in Git. The P1.8 reconciliation remains 3,298 exact common, 278 already absent historical, and 85 live-only entries; all 3,383 live P1.8 files remain present, including the held bundle.

The five S5-B reproduction receipts remain copied outside the disposable checkout; they are same-disk copies, not independent backup. The 3 P1.1 holds, 516 unresolved C2 paths and 2 C2 symlinks remain untouched. No newly known active TaskEnv consumer was found; accessible local process inspection is incomplete and external PhysPi/Skill status is still not exhaustively established.

Current-source bounded checks used Python 3.12 with single-thread settings, 2-GiB address-space and CPU/time ceilings. Seven artifact/reset/semantics/retired-UID/import checks passed in 1.25 s; two additional workspace-isolation/task-binding checks passed in 0.78 s. These are **9 provider-free checks**, not native physics or Qualification. No native full route or learning campaign was rerun. The selected TaskEnv tree and submodule Gitlinks have no diff from public develop. The recovery verifier confirmed 115 explicit Git object/reference specifications. Its initial parser incorrectly treated 10 prose fields as revspecs; that failed receipt is retained alongside the corrected result.

Detailed commands, logs, authorization and safety-stop records remain under ignored `workspace/maintenance/p2_0_s5_c8_20261018_execution/`; hashes and source identities are in the [compact execution receipt](evidence/retirement/c8_execution_receipt_20261018.json). The immutable approved preflight manifests remain under the original C8 directory. Current documentation status updates are versioned migrations of L1, not replacements of raw Evidence; the original baseline bytes remain in commit `153af68e51140b0cc1b79b3db493a7648b8da3eb`.

## C8 acceptance checklist

| Criterion | Result | Actual evidence |
|---|---|---|
| A — L1 preserved/versioned | PASS | Original 84-file baseline verified; factual governance migrations retained in Git; current L1 snapshot recorded separately without editing approved manifests |
| B — L2 intact | PASS | 22/22 SHA-256, 24,563,669 bytes; no replacements or reserialization |
| C — historical metadata | PASS | 37 original records / 366,744 bytes preserved and indexed |
| D — P1.8 live reconciliation | PASS | Original/live identities remain separate; 278 absent and 85 live-only records explicit |
| E — loss acknowledgment | PASS | Maintainer accepted exact C1/C2 losses; actual loss in this execution is zero |
| F — exact batch approvals | PASS | All four supplied SHA-256 values match immutable local manifests |
| G — approved cleanup | BLOCKED | Storage stop before first unlink; worktree method also held |
| H — post-deletion checks/recovery | NOT_RUN | No deletion; post-stop baseline and raw integrity checks passed; recovered space 0 GiB |
| I — refs/source protection | PASS | Public develop/main/tag read back unchanged; selected execution tree and Gitlinks unchanged |
| J — original-goal retrospective | PASS (documented) | Goal/stage matrix completed; it does not claim all P2.0 objectives achieved |
| K — release readiness report | PASS (reported) | Publication remains BLOCKED; mandatory backup gate unwaived |

The pre-existing P1.6 205,486,080-byte recovery archive remains unlocated; this is not a new loss caused by C8. All currently live P1.8 source carriers remain, including the 49,971,200-byte GeoPhys tar, 12,139,954-byte GeoPhys bundle, 1,904,240,640-byte Menagerie tar, 604,164,075-byte Menagerie bundle, and held 18,571,359-byte root source bundle. The earlier incomplete-history/source-loss assessment remains relevant if deletion later proceeds. Hash metadata is not restoration capability.

## Phase 2.0 original goals and stage assessment

The [goal-to-implementation retrospective](p2_0_retrospective.md) compares the original [P2.0-A ownership work](../../maintenance/p2_0_part_a.md), [Phase II handoff plan](../../roadmap/phase2_plan.md), canonical architecture and implementation history. Its current assessment is:

| Stage / original goal | Implementation and evidence | Status |
|---|---|---|
| P2.0-A repository/worktree consolidation | Ownership rules and exact inventories exist; frozen v1.0.0 worktree is protected; approved cleanup has not run | PARTIALLY_COMPLETED; storage-blocked cleanup |
| P2.0-A Evidence ownership, recovery and redundant artifacts | L1 versioned; L2 locally verified; 37 historical records preserved; loss accepted for exact C1/C2 lists; no independent backup | PARTIALLY_COMPLETED |
| S0 Renderer Registry M1 | `08e9a912`; Registry and provider-free contracts integrated; native render behavior not newly qualified | COMPLETED for M1 only |
| S1/S1.6 selected construction and NutAssembly Outcome V1 | `d01cc3b` through `77e194e`; strict lifecycle remains distinct from physical outcome and accepted warning | COMPLETED for selected bounded scope |
| S2 minimal task authoring | Four task-local files per selected task; PickCube `5b00580`, NutAssembly `4d6d65c`; `make_env` public UIDs and accepted two-provider routes | COMPLETED for selected tasks |
| S3 Go2-specific retirement | `9c6548d`; generic RL/Batch/Device/Learner retained | COMPLETED for approved scope |
| S4 GeoChora static solver retirement | `0ff2d846`; merged_scene and GeoPhys adapter boundary retained | COMPLETED for approved scope; native GeoPhys Rigid Batch not validated |
| S4.5 current task/expert/recording/learning/rendering workflows | `5d57272`, `929dd8f`, `fc12780`, `bee498d`; developer examples and bounded smokes | COMPLETED for approved workflows; broader interoperability DEFERRED |
| S5-A/B v1.1.0 candidate | `e0e4dbc`, `2fb60de`; inventory, migration and candidate capability matrix | COMPLETED for candidate preparation; publication BLOCKED |
| S5-C1–C8 governance and workspace retirement | Exact authorization now present; safety stop prevents execution; preserved metadata and current-source checks complete | PARTIALLY_COMPLETED; no cleanup completion claim |

The selected routes remain `TESTED_BOUNDED`, not newly `QUALIFIED`. P2.0 implementation work enabled a smaller Core and explicit task/provider boundaries. It did not complete all Phase II research or establish general Physics × Renderer interoperability.

## Release readiness and next Phase II direction

The [current release gates](release_readiness.md) retain the independent/full-workspace backup blocker: the maintainer explicitly **did not waive** it. L1 remote integration, controller identity Option B acceptance, capability-matrix approval and final publication authorization remain separate decisions. Fresh-install validation and full relocated-checkout regression remain NOT_RUN; the historical 139 PASS / 8 FAIL exploratory receipt is preserved. No new P1.8 FULL, D0–D2, manipulation checkpoint/PPO, native Flora or native GeoPhys Rigid Batch qualification is implied. GeoPhys NutAssembly's original strict Expert failure remains separate from accepted Outcome V1 success.

Future P2.x work should choose one benchmark (LIBERO, RoboCasa, RoboTwin or RoboDojo) and compare its native execution with a canonical TaskArtifact/TaskEnv workflow. Required research includes provider and controller/observation mapping, bidirectional trajectory conversion/validation/replay, an evidence-grounded Task Harness, and later governed PhysPi consumption. General benchmark interoperability, autonomous RSI and complete PhysPi integration remain NOT_IMPLEMENTED; none was implemented in C8.

Continue only this C8 when storage classification/resolution permits it, revalidating the unchanged approved hashes and exact file identities. Preserve the B worktree unless a compliant non-forced Git procedure is established. The existing exact batch approvals persist; no repeated blanket cleanup review or C9 is requested. No push, main update, tag or release publication is authorized.
