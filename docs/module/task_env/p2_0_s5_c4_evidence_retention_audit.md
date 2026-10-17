# GeoChora P2.0-B S5-C4 — Current TaskEnv Evidence Retention & Cleanup Audit

**Status: RELEASE_CANDIDATE — NOT_PUBLISHED**

**Retention-policy decision: MAINTAINER_DECISION_REQUIRED**

**Cleanup: DRY_RUN_ONLY — no files deleted, moved, or rewritten**

## Scope and refs

This audit applies the Task Artifact / Experiment / Evidence contract and Core qualification governance. It distinguishes historical formal decisions, current bounded acceptance, raw artifacts, and release metadata. It does not rerun qualification or infer current capability from Phase I experiments.

The local branch is `codex/p2-0-b-s4-5-b-workflow-consolidation`; the S5-C3 HEAD at audit start was `28dc2f48a6c16defa9bb3c8037e717a4873ae523`. Fresh remote readback on 2026-10-17 found public `develop` at `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`, public `main` at `e4e39883fbe01d4be4b172a53a535ef0095b3d64`, and annotated `v1.0.0` tag object `17c3100d4fabcb061c23569dea49973ebd177d51`, peeled to `42787f5e4f658a3f81fdd2140cf7544d6342c783`. No remote ref was changed. At the C4 audit snapshot, its documentation edits were uncommitted; S5-C4/C5/C6 are now prepared together in a local review commit and remain unpushed and absent from public `develop`.

The v1.1.0 candidate has no new formal Qualification decision. The four current manipulation/provider routes remain `TESTED_BOUNDED` and `NOT_QUALIFIED_FOR_CURRENT_SOURCE`. Current `develop` contains the selected task source closure recorded as `929dd8fafe8dca5b0f375341045501c0a8eed9c7`; tested PickCube and NutAssembly run source revisions remain `5b0058010f5416eefb08ce59cec43770602fc336` and `4d6d65c55eca994b4317bcfb80797c69e48452c6`, respectively. The later candidate changes preserve those execution closures; they do not transfer a historical qualification label.

## Current TaskEnv and workflow evidence

The authoritative current identities and bounded status are in the [v1.1.0 candidate capability matrix](capability_matrix_v1_1_0_candidate.json), [PickCube source identity](p2_0_s2_c1_source_identity.json), [NutAssembly source identity](p2_0_s2_c2_source_identity.json), and [release acceptance index](../../releases/v1.1/evidence/README.md).

| Current route | Identity and bounded result | Evidence boundary |
| --- | --- | --- |
| PickCube / GeoPhys CPU | `pick-cube-p16-reference-v1`; Artifact `pick-cube-v1/p1_6_experimental_100hz`, SHA-256 `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4`; config SHA-256 `0d6b26b08affd68c95a4f3209111f7c4ee2ce62088b664370f7c11b6045e9aa0`; controller `76108c78b8159391e448ad9f49050bed42fd7a86e0e00a0520083b4e5efb02e9`; solution `514a5ed3bc0d289761ef88a00b1e7c11df2795133506ab148db9ab8e98e55241`. Seed 31, 100 Hz; 151 transitions / 152 boundaries, 755 native steps; four expert stages and measured lift success. | `TESTED_BOUNDED`; no checkpoint inference, D0-D2, or qualification inheritance. H5 row and checksum are in L2 below. |
| PickCube / MuJoCo CPU | Same TaskArtifact/config/controller/solution identity. Seed 31, 100 Hz; 470 / 471 transitions/boundaries, 2,350 native steps; four expert stages and measured lift success. | `TESTED_BOUNDED`; same limits as above. Cross-checkout controller-hash equality is not guaranteed because generated MJCF contains an absolute mesh path. |
| NutAssembly / GeoPhys CPU | `nut-assembly-outcome-reference-v1`; Artifact `nut-assembly-square-v1/p1_8_e/nominal-v1`, SHA-256 `99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe`; config SHA-256 `749c78638a1e5c5e59374ceccd846767bacce5af969c2c50370482d2a288c531`; solution `cba7a4932f4b36b01a855417833509d301746325ba93e85cd4cfed23a802a9b4`; Outcome V1 `a940c6cfc4b9dbe64ae55b615e7bdbd9a210dc7495c6337b08cff688c52694ee`; guard `065af38f034f896d3003d8f63cfb2ea9acac3adcefe078b678bd7596d57a0674`. GeoPhys controller `094bbf739793610750e45c1dfd8442d1c680f7b1da4a5b8c537abcb08a92b759`; recipe `7d1b20f30008383d9936355848b39abcb0af3d8780ee588a05c885529ced3286`. NA-S0 seed 19, 100 Hz; 11 planned stages, 2,380 / 2,381 boundaries, 11,900 native steps, measured insertion/release, `task_success=true`, `outcome_complete=true`. | Keep physical task outcome and Outcome V1 separate from original strict lifecycle. The original strict Expert failed at step 362 on `descend_to_handle/stable_height_mismatch`; one admitted readiness warning is recorded. That failure is preserved, not rewritten as PASS. Not P1.8 FULL or D0-D2. |
| NutAssembly / MuJoCo CPU | Same Artifact/config/solution/Outcome/guard identities. MuJoCo controller `3c455279a7d54214fdb6a8d808df8a575d8938b17e92fd7df7d517bca2b492ec`; recipe `9f5ce3206807557d1780e7de8d8abf6009dc237e11a799ac37878d8c2de3f767`. NA-S0 seed 19, 100 Hz; 11 stages, 2,373 / 2,374 boundaries, 11,865 native steps, measured insertion/release, task and outcome success; strict Expert completed without warning. | `TESTED_BOUNDED`; not P1.8 FULL or D0-D2. |
| Canonical recording / H5 inspection | PickCube MuJoCo CPU, seed 31; canonical trajectory schema, 470 / 471 boundaries, `T+1=true`, logical mapping roundtrip exact. | Storage/read validation only; not D0 reconstruction. Incomplete run finalizes readable H5 and exits nonzero. |
| TaskEnv provider-free regression and retired-route checks | S5-C2 source target public `develop` `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`: 147 tests and 6 subtests passed; focused converter/failure-gating receipt has 3 passing checks. | Provider-free API/import/contract regression; not native qualification. Retired routes fail explicitly under the recorded tests. |
| Pendulum `merged_scene` CPU batch | GeoPhys CPU, two worlds, reset and one zero-action step; finite observations/rewards; one accepted result JSON. | Not GeoPhys Rigid Batch native validation. |
| SB3 Pendulum bounded workflow | GeoPhys CPU `merged_scene`; two environments, one update/four timesteps, seed 73 requested and worker seed 75; summary, return H5, checkpoint finalized. | One-update smoke only; no convergence or general RL qualification. The CPU run's stderr contains a PyTorch CUDA initialization warning and is retained. |
| Pendulum scalar/batch rasterizer RGB | GeoPhys CPU, bounded 32×24 float32 RGB reset/step examples. | Frames were in memory, with no saved raw image. Not Native Flora, manipulation rendering, or Physics × Renderer qualification. |
| Generic RSL-RL and GeoPhys Rigid Batch | Adapter imports and fail-closed admission are covered by provider-free tests. | No native RSL training or GeoPhys Rigid Batch validation. |

The six current L2 H5 files and their SHA-256 values, together with supporting current results, are listed in [the evidence index](../../releases/v1.1/evidence/README.md). The original GeoPhys NutAssembly strict Expert failure remains an independent retained observation alongside the successful physical outcome.

## L1 — Required release metadata

L1 is the Git-tracked source of current release metadata and audit decisions. At the C4 snapshot, the [backup manifest proposal](../../releases/v1.1/backup_manifest.json) included a 34-path L1 inventory. S5-C5/C6 subsequently expanded the current inventory to 40 paths, adding the retention reports, retirement proposals, and deletion receipt template. It includes the v1.1.0 scope/version policy, installation and migration guidance, public API/task inventory, capability matrix, task/source identity records, S3/S4 recovery manifests, S4.5 workflows, S5-A/B/C1/C2/C3 reports, the release evidence summaries, known limitations, test summary, and release readiness. C4/C5/C6 remain local review documentation and are not integrated into public `develop`.

Git preserves exact tracked bytes only while the relevant objects remain available. It cannot restore ignored H5, checkpoint, archive, or experiment files. No independent L1 copy was made.

## L2 — Current TaskEnv raw acceptance Evidence

The minimum sufficient L2 proposal contains **22 files / 24,563,669 bytes**, including **six H5 files / 24,333,284 bytes**. The five original selected-task/recording H5s total 24,301,972 bytes; the current SB3 return H5 adds 31,312 bytes. Exact relative paths, byte counts, SHA-256, and roles are tabulated in [the evidence index](../../releases/v1.1/evidence/README.md) and included in the proposed scope in `backup_manifest.json`.

The list consists of the four accepted manipulation full-route H5s and their result/worker receipts, the canonical recording H5, current SB3 summary/example result/stdout/stderr/return H5/checkpoint, the accepted merged-scene batch receipt, the final 147-test provider-free log, and converter/failure-gating log. The old “five H5 plus ten supporting files” S5-C3 tally remains preserved in the dated S5-C3 report; the current evidence index adds seven S4.5-B raw acceptance files.

All 22 files were found and SHA-256 checked on the current source disk against the recorded baseline where one existed. This is `L2_RAW_EVIDENCE_LOCALLY_VERIFIED`; it is not an independent backup or restore verification. The raw bytes remain exposed to the known `/dev/sda` / `ata5` risk. Hashes identify loss; they do not recover data.

## L3 — Historical and intermediate workspace

L3 includes historical qualification campaigns, Human/Judge decisions and failure records, archived provider/source snapshots, earlier task candidates, Go2 and static-template development runs, policy searches, diagnostics, demos, and unselected maintenance experiments. No directory is deemed disposable solely because it is old, failed, or stored under a historical-looking path.

The immutable v1.0.0 tag was read from the canonical remote. Its tracked tree includes P1.6 closure metadata under `workspace/qualification/phase1/p1_6_closure/`. The v1.0.0 release archive manifest additionally identifies a local-only P1.6 recovery tar (205,486,080 bytes; 441 members) and P1.8 integration evidence archive (10,989,629,850 bytes); it records no verified off-host backup. The P1.8 archive is present at `workspace/qualification/phase1/archives/p2_0_part_a/legacy_evidence_archive/p1_8_integration_20261012/`; its apparent-size metadata is 10,989,629,850 bytes, matching the release manifest. The archive notes that its historical GeoPhys Git bundle cannot be reconstructed from Git history because a parent object is missing, while exact source-tree snapshots are retained. By contrast, the current workspace metadata scan did not locate a file matching the recorded P1.6 recovery tar path or 205,486,080-byte size. Its actual location and availability remain **UNKNOWN_REVIEW_REQUIRED**; do not infer it is recoverable from the tracked P1.6 closure metadata. The release evidence index also points to local P1.8 final-integration and cross-provider development results, including failures. These are protected dependencies, not cleanup candidates. Historical Human decisions and raw failures must remain unchanged.

Other historical dependencies include records consumed by PhysPi/Skills or external users that repository scans cannot discover. Unknown or unreferenced workspace files therefore remain `UNKNOWN_REVIEW_REQUIRED`; public Git metadata is not assumed to restore them.

## File inventory, worktrees, and cleanup allowlist

A metadata-only `os.scandir` walk recorded **85,467 entries** (72,987 files, 12,478 directories, 2 symlinks). It did not follow symlinks and did not hash the full workspace. Hashes were computed only for the selected 22 L2 files and 17 exact cache candidates. The full [JSONL inventory](../../../workspace/maintenance/p2_0_s5_c4_20261017/workspace_file_inventory.jsonl), [summary](../../../workspace/maintenance/p2_0_s5_c4_20261017/inventory_summary.json), and [exact SHA-256-bearing cleanup allowlist](../../../workspace/maintenance/p2_0_s5_c4_20261017/proposed_cleanup_allowlist.json) are in ignored `workspace/maintenance/p2_0_s5_c4_20261017/`.

| Classification | Entries | Path-summed bytes / meaning |
| --- | ---: | --- |
| `KEEP_CURRENT` | 22 | 24,563,669 bytes of current L2 raw acceptance files. |
| `KEEP_HISTORICAL_PROTECTED` | 75,314 | 84,083,421,492 path-summed bytes, including all of `workspace/qualification/` and files under report/recovery references. Hardlinks mean this is not a unique storage estimate. |
| `KEEP_UNTIL_BACKUP` | 7,381 | 1,975,571,044 bytes in the registered detached clean-checkout/source-reproduction tree and its receipts. |
| `REGENERABLE` | 8 | Cache-directory entries only; not in the deletion allowlist. |
| `CLEANUP_CANDIDATE` | 17 | 273,905 logical bytes / 311,296 allocated file-block bytes in standalone `.pyc` caches with adjacent sources. |
| `UNKNOWN_REVIEW_REQUIRED` | 2,725 | 6,480,100,469 bytes: experiments (5,693,980,990), demos (533,395,431), diagnostics (252,717,929), and a small number of maintenance entries. Not safe to delete. |

For the whole workspace, `du -x -s -B1` reported 75,974,623,232 bytes; `du --apparent-size -s -B1` reported 75,732,668,547 bytes. The metadata path-sum is larger because it counts hardlinked paths repeatedly. The qualification subtree occupies 65,536,290,816 allocated bytes. These are local observations, not backup-transfer size guarantees.

The registered nested detached checkout `workspace/maintenance/p2_0_v1_1_clean_checkout_20261017` is at `bee498d1d784015f034c5b4af34320fdffa61411`; its tracked working tree is clean and its GeoPhys/Menagerie Gitlinks match the recorded pins. Its `.git` marker and submodule `.git` files were inventoried but not followed. It remains `KEEP_UNTIL_BACKUP` because it contains clean-checkout reproduction/path-identity receipts. The separately registered frozen v1.0.0 archive worktree was not changed. The inventory found a symlink to that archive worktree and another symlink back to `workspace/`; neither was followed. There are 750 hardlinked file-path entries, including archived Git objects and historical result files; no allowlisted cache file is hardlinked. These findings rule out recursive path cleanup and directory-based deletion.

The exact dry-run allowlist is [proposed_cleanup_allowlist.json](../../../workspace/maintenance/p2_0_s5_c4_20261017/proposed_cleanup_allowlist.json), SHA-256 `f79eb22b47bd4e1a7db8645cf0755ad336607b4d026174f41cf094daf59f25d7`. It names 17 `.pyc` files under the S2 harness, demo camera-retake tools, and a diagnostics imageio-ffmpeg cache. Each has `nlink=1`, no symlink, an adjacent `.py` source, and both cache/source hashes. Their exact byte identities are **not** guaranteed reproducible; only the cache semantics are. The allowlist excludes the registered checkout, qualification evidence, all H5/checkpoint/log/source files, and every directory. It estimates at most **311,296 bytes (about 304 KiB)** of file blocks, excluding directory metadata. No deletion occurred. No large workspace cleanup is justified by this allowlist.

The inventory classification is conservative:

- All `workspace/qualification/` content is `KEEP_HISTORICAL_PROTECTED` until individual qualification, Human/Judge, archive, external-consumer, and raw-data dependencies are reviewed.
- Referenced historical maintenance outputs are protected; the detached clean checkout is held; other maintenance/experiment/diagnostic/demo files that lack verified ownership or dependency mapping are `UNKNOWN_REVIEW_REQUIRED`.
- `CLEANUP_CANDIDATE` applies only to the 17 exact cache file paths in the allowlist. It is not approval to remove them.

## Proposed v1.1.0 retention policy and backup gate

The proposed statuses are tracked independently:

| Status | Audit result |
| --- | --- |
| `L1_METADATA_PRESERVED` | Present in the local repository; C4/C5/C6 review documentation is not integrated into public `develop`. |
| `L2_RAW_EVIDENCE_LOCALLY_VERIFIED` | PASS for 22 files / 24,563,669 bytes on the local disk. |
| `L2_INDEPENDENT_BACKUP_NOT_VERIFIED` | Open; no independent destination, copy, or restore read. |
| `L3_HISTORICAL_BACKUP_NOT_VERIFIED` | Open; historical workspace remains on the same disk. |
| `CLEANUP_PENDING_APPROVAL` | DRY_RUN_ONLY; 17 cache paths, no deletion. |
| `MAINTAINER_RISK_ACCEPTANCE_REQUIRED` | Required for raw L2 and proposed L3 scope under the known storage condition. |

Proposed policy: retain L1 permanently in release source history; retain the exact L2 raw acceptance set in place and require an independent copy only if a destination is later authorized; keep historical v1.0.0 source/Evidence immutable; and exclude L3 from the v1.1.0 mandatory off-host preservation scope only after the maintainer explicitly approves the scope change and accepts the residual risks. This does **not** mark an independent backup PASS and does **not** make SHA-256 references substitutes for raw data.

The prior full-workspace backup requirement remains active and `BACKUP_NOT_VERIFIED` remains the release gate until approval. No cleanup, backup copy, restore read, remote integration, tag, or publication was performed. The known single-disk `/dev/sda` / `ata5` BadCRC and READ I/O history remains an open risk; a clean recent kernel query would not close it.

## Checks and decisions required

- Verified public `develop`, `main`, and v1.0.0 tag refs by fresh remote readback; no ref changed.
- Checked the immutable v1.0.0 release tree, evidence index, archive manifest, and known limitations. No v1.0.0 file was changed.
- Reused accepted functional/test receipts; no native route or qualification campaign was rerun because no task/provider source changed.
- Rehashed the 22 L2 paths and 17 allowlisted cache/source pairs. The complete inventory itself is metadata-only; whole-workspace hashing was deliberately not run.
- Confirmed current S5-C4 JSON parses, Markdown has no whitespace errors, and relative links resolve before handoff.

Maintainer decisions before cleanup or changing the release gate:

1. Approve or reject the reduced L1/L2/L3 retention policy; until then the full-workspace gate remains active.
2. If approving, explicitly accept that L2 and L3 lack verified independent copies and that raw data remains exposed to the known disk risk.
3. Separately authorize any future removal of the exact 17 cache paths. No broader cleanup is proposed as safe; unknown files require their own review.
4. Separately authorize integrating these local release-documentation updates into public `develop`.
5. Retain the other v1.1.0 release decisions and publication blockers in the readiness matrix; this audit grants no release approval.

**Handoff:** stop for maintainer review. Do not delete workspace files or publish v1.1.0.
