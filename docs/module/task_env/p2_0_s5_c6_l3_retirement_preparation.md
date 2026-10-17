# P2.0-B S5-C6 — L3 Historical Workspace Retirement Preparation

**RELEASE_CANDIDATE — NOT_PUBLISHED**
**Disposition:** `APPROVAL_PROPOSAL_ONLY`; no workspace file was removed,
moved, copied, rewritten, or reserialized.

## Baseline and decision boundary

The canonical remote was re-read on 2026-10-17. Public `develop` is
`2fb60de7851bf2e5651c2dc99fff7451c16e1a94`; public `main` is
`e4e39883fbe01d4be4b172a53a535ef0095b3d64`; annotated `v1.0.0` tag object
`17c3100d4fabcb061c23569dea49973ebd177d51` peels to
`42787f5e4f658a3f81fdd2140cf7544d6342c783`. The local branch is
`codex/p2-0-b-s4-5-b-workflow-consolidation` at
`28dc2f48a6c16defa9bb3c8037e717a4873ae523`. These S5-C3/C4/C5/C6 governance
changes are local and unpushed. No tag, protected branch, or historical record
was changed.

This report prepares three separate approval units. Each has
`execution_authorized: false`; their `execution_allowlist` fields are empty.
The existing full-workspace backup requirement remains active and
`BACKUP_NOT_VERIFIED`. Neither the maintainer's retention direction nor this
report authorizes cleanup or release publication.

## L1 and L2 preservation check

The exact 22 L2 paths in the [release evidence index](../../releases/v1.1/evidence/README.md)
were re-statted and SHA-256 checked against their recorded values: **22/22
matched**, total **24,563,669 bytes**. The set includes four final-source
manipulation H5s, the canonical recording H5, the SB3 return H5 and checkpoint,
batch/learning results, task worker receipts, and current regression/CLI
receipts. All remain on `/dev/sda`; no copy or restore read exists. Their paths
and inodes are excluded from all three candidate manifests.

Selected identities and acceptance results remain the ones in the current
[capability matrix](capability_matrix_v1_1_0_candidate.json):

| Route | Identity and current-source result |
| --- | --- |
| PickCube / GeoPhys CPU | `pick-cube-v1/p1_6_experimental_100hz`, Artifact SHA `fd5bc968…a54c4`, config SHA `0d6b26b0…e9aa0`; 100 Hz, 151 transitions / 152 boundaries, 755 native substeps, measured success. |
| PickCube / MuJoCo CPU | Same Artifact/config; 470 transitions / 471 boundaries, 2,350 native steps, measured success. |
| NutAssembly / GeoPhys CPU | `nut-assembly-square-v1/p1_8_e/nominal-v1`, Artifact SHA `99e374bd…9b9fe`, config SHA `749c7863…8c531`, Outcome V1; 11 stages, 2,380 transitions / 2,381 boundaries, 11,900 native steps, task/outcome success. The original strict Expert `stable_height_mismatch` at `descend_to_handle` remains a failure observation and an admitted warning; it is not rewritten as a strict Expert PASS. |
| NutAssembly / MuJoCo CPU | Same Artifact/config and policy; 11 stages, 2,373 transitions / 2,374 boundaries, 11,865 native steps, task/outcome success; original Expert completed without a readiness warning. |

The full exact paths, H5 hashes, task/controller/solution identities and
recording results remain in L1/L2. Capability labels remain
`TESTED_BOUNDED`; no Qualification, D0-D2, checkpoint inference, or general
manipulation-learning claim is added. No H5 was substituted with a newer run.

For the current filesystem snapshot, the three candidate path sets were
checked against 911 protected Git/L1/L2 paths/inodes: **zero candidate inode
aliases** were found. The L2 set has 22 paths and all are disjoint from the
candidate paths. At execution time this check must be recomputed; local inode
numbers are not portable identities.

## Exact approval candidates

The full file-level manifests remain in ignored
`workspace/maintenance/p2_0_s5_c5_20261017/`. Their SHA-256 values bind the
candidate path sets and metadata. The three small tracked approval envelopes
link each set to its exact source manifest and keep execution disabled:

| Batch | Tracked proposal | Exact source manifest | Candidate scope and current limit |
| --- | --- | --- | --- |
| A | [L3-A candidate](../../releases/v1.1/evidence/retirement/l3_a_approval_candidate.json) | `safe_regenerable_cleanup.json`, SHA `033b4e63…a3e14` | 17 exact `.pyc` files; 311,296 allocated bytes; all sources exist. |
| B | [L3-B candidate](../../releases/v1.1/evidence/retirement/l3_b_approval_candidate.json) | `superseded_experiment_cleanup.json`, SHA `cf02a17b…d61f7` | 6,795 exact rows; 3,317,497,856 allocated bytes including a registered detached worktree. Receipt and ownership exceptions remain. |
| C | [L3-C candidate](../../releases/v1.1/evidence/retirement/l3_c_approval_candidate.json) | `historical_raw_retirement_review.json`, SHA `8359315e…57eed` | 66,155 rows, including 66,153 regular files and two symlinks; 72,514,465,792 unique allocated file bytes. Irreversible-loss and external-consumer review is still required. |

The machine-specific source manifests record path, file type, size, allocated
blocks, device/inode/link count, source/recovery status and dependencies.
Historical raw files were not bulk hashed. Before any later execution, verify
the full source-manifest hash again and compare every live path/type/size/link
identity with its recorded row. A mismatch stops the whole batch.

## Batch A — regenerable caches

All 17 candidates are `.pyc` files with a corresponding source file present.
The cache and source SHA-256 values, paths, sizes, allocated blocks, device,
inode, link count, Python tag and bytecode header are in the exact L3-A
candidate. The current interpreter is Python 3.14.7:

- 9 Python 3.14 caches have a timestamp/size header matching the current
  source.
- 6 Python 3.12 caches have a different bytecode magic and are not current
  interpreter caches.
- 2 Python 3.14 caches have stale source timestamp/size headers.

All remain regenerable because their corresponding source files exist. None is
a symlink or hardlink; no protected inode alias was found. **Batch A proposed
recovery is at most 311,296 bytes (0.00029 GiB); actual recovery is zero.** A
future action must unlink only the 17 exact approved file paths, after a new
manifest and inode check. No directory deletion is appropriate.

## Batch B — superseded experiments and detached checkout

The 6,795-row set divides into 6,619 rows under the registered detached
checkout and 176 rows elsewhere. The non-worktree rows comprise 168 S1.5/S1.6
acceptance artifacts, three old P1.1 candidate artifact files, and five small
review-only files: three repeated/supplementary receipts, one failed default
Python selection receipt, and `workspace/qualification/draft.md`. The current
selected task and public runtime do not consume these files; S1.5/S1.6 records
still explain the historical selection, and the old P1.1 candidate's ownership
is not established. The failed environment-selection receipt and three P1.1
files remain explicit holds. The repeated receipts and design note also
require path-specific review; no group-level deletion is authorized.

The 168 S1.5/S1.6 rows allocate 1,327,337,472 bytes. The three P1.1 files and
the failed environment-selection receipt allocate 20,480 bytes and are explicit
holds. The other three repeated receipts plus the design note allocate another
20,480 bytes and remain review-only. These categories sum to the exact
1,327,378,432-byte non-worktree allocation; no subtotal is an approval.

The registered worktree is
`workspace/maintenance/p2_0_v1_1_clean_checkout_20261017`, at
`bee498d1d784015f034c5b4af34320fdffa61411`. It is clean, detached, and its
superproject commit is an ancestor of both the current local HEAD and public
`develop`. It has no unique superproject commit. GeoPhys and MuJoCo Menagerie
Gitlinks match the current root submodules and their commits are locally
readable. The `.git` administration and shared object stores are outside the
workspace; they are not part of the reclaim estimate and must not be deleted.

Four nested S5-B receipts are explicitly held out of worktree retirement until
their exact bytes have an approved preservation location and their hashes are
verified: `clean_checkout_source_identity.json`,
`provider_free_final.log` (the 139 PASS / 8 FAIL exploratory receipt),
`clean_checkout_smoke.log`, and `clean_checkout_smoke.json`. The full paths,
sizes, and SHA-256 values are in the Batch B envelope. Current L1 documents
cite three of these receipts. The four receipt paths are among the 6,619
worktree rows and are not an exact worktree-retirement allowlist until their
bytes have been preserved and revalidated. No copy or relocation was made.

Gross Batch B allocation is 3,317,497,856 bytes (about 3.08964 GiB):
1,327,378,432 bytes outside the worktree and 1,990,119,424 bytes in the
registered checkout. If the four held receipts are copied to retained storage,
the checkout could be retired only through a separately approved,
non-forced `git worktree remove` operation after verification. Do not use
recursive deletion, `--force`, or `git clean`. Excluding only the four explicit
non-worktree holds (the three P1.1 paths and failed environment-selection
receipt) leaves 172 paths / 1,327,357,952 allocated bytes as a numerical ceiling
for further path-by-path review, not as an authorized deletion list; the three
repeated receipts and design note also need explicit disposition. **Actual
recovery is zero.**

## Batch C — historical raw Evidence and irreversible loss

The C manifest contains 66,153 regular files and two symlinks. The two link
targets are recorded in the candidate and were never followed:

- `.../recording_history_refs_live_v2/run_cwd/task_env` points to the frozen
  v1.0.0 worktree's `task_env` directory.
- The corresponding `run_cwd/workspace` link points back to the active
  `workspace/` directory.

These structural links remain excluded from any raw-file allowlist pending a
separate link-boundary decision. The inventory has 516 rows marked
`Historical or unresolved; see group-level review notes`; their exact paths
are in the C envelope and must not be auto-deleted. The proposed release of
those 516 rows is zero until individually resolved. External PhysPi/Skill
consumers have not been exhaustively inventoried, which blocks execution for
the entire batch until that boundary is checked. The C inventory also has 206
hardlinked inode families. Their aliases are within the reviewed C set and no
protected/external aliases were observed; a future operation must still
process each alias family as a unit and verify link-count decrements.

Historical recovery is materially incomplete:

- **P1.6 archive:** the immutable release manifest records a 205,486,080-byte,
  441-member tar with SHA-256
  `d31b64570e951b1cd694afe105f554dd44199d3f43aba689dac5c62c804d3d93`. It was
  not found in the C4 workspace scan; its location and any independent copy
  remain unknown. It is not a known deletion path. Tracked closure metadata
  cannot reconstruct the missing tar.
- **P1.8 archive:** 3,383 files, 10,989,629,850 logical bytes, and
  10,997,342,208 allocated path bytes exist at
  `workspace/qualification/phase1/archives/p2_0_part_a/legacy_evidence_archive/p1_8_integration_20261012/`.
  The archive has no verified independent copy. Its historical GeoPhys bundle
  lacks a parent object, so 796 local GeoPhys source-snapshot files (about
  1,875,220,444 logical bytes) are not completely recoverable from Git.
- **Human/Judge decisions:** tracked historical phase decisions and the
  immutable v1.0.0 release records remain available. They preserve their
  recorded status and must not be rewritten; the publication receipt records
  seven historical Human decision files verified in the tracked mainline
  decision set. The P1.6 policy-search handoff records a 1/6 fixed-cohort
  result and requests Human Review. Deleting the raw
  P1.6/P1.8 evidence would remove the exact runs, checkpoints, traces,
  diagnostics, source snapshots, and decision-support data behind those
  summaries. Some decision records also exist only in workspace paths; their
  exact bytes are not independently backed up.
- **Failures and external use:** historical failures and unselected outcomes
  are part of the audit history. The exact original failure states will no
  longer be re-openable from raw data after deletion. The repository does not
  provide a complete consumer list for PhysPi/Skills, so any potentially
  referenced group remains a hold until reviewed.

Immutable Git-tracked decisions and source blobs remain recoverable through
`v1.0.0` and recorded commits; raw H5s, checkpoints, logs, videos, and local
source snapshots do not. A SHA-256 value is only an identifier and cannot
restore lost bytes. C5 allocates 72,514,465,792 unique file bytes (about
67.53436 GiB) across the C set; after excluding the 516 unresolved rows and two
symlinks, the conditional regular-file ceiling is 72,118,321,152 bytes (about
67.16542 GiB). The external-consumer hold means no C deletion is currently
executable. **Actual recovery is zero.**

## Per-batch approval and post-deletion safeguards

Each batch needs its own explicit maintainer approval; approval of one batch
does not authorize another. Batch C approval must explicitly acknowledge
permanent loss of historical re-audit capability and the absence of verified
raw-data recovery. Approval does not waive the backup gate or authorize
publication.

Before any later approved operation:

1. Fetch and record public refs; verify `main` and `v1.0.0` are unchanged.
2. Confirm L1/L2 files and hashes; recompute protected path/inode aliases.
3. Verify the exact approval-envelope hash and its referenced source-manifest
   hash. Re-stat every selected path with no symlink following.
4. Confirm the expected filesystem/device, link counts, worktree registration,
   dirty/untracked state, Gitlinks, and source objects. Stop on any mismatch.
5. For A and file-level B rows, unlink one allowlisted regular file at a time
   through a no-follow implementation. Never pass a directory to a recursive
   remover. For the checkout, use only an approved non-forced Git worktree
   operation after preserving its four receipts. Do not remove shared Git or
   submodule objects.
6. Stop on the first I/O error, path/inode mismatch, or unexpected link. Keep
   a receipt with the before metadata, approved manifest hashes, each removed
   path, exit status, and remaining allowlist. Never retry a mismatched path.
7. Verify every approved target is absent, every holdout and all L1/L2 paths
   still exist and hash correctly, the worktree registration is as expected,
   and the actual `df` change does not exceed the inode-deduplicated estimate.

The [deletion receipt template](../../releases/v1.1/evidence/retirement/deletion_receipt_template.json)
captures authorization, manifest identities, preflight checks, exact removed
files, stop reason, and postflight results. It is marked `NOT_EXECUTED` and
must only be populated after separate batch approval.

This is a procedure proposal only; none of these operations ran.

## Current storage observation

On 2026-10-17, `/dev/sda4` reported 626 GiB total, 102 GiB used, and 492 GiB
available. Memory reported 5.2 GiB available and 11 GiB swap in use; current
memory and I/O PSI averages were 0.00. A last-30-minute kernel journal filter
returned no ATA/SATA/read-I/O matches. These are bounded observations only:
the prior `ata5` BadCRC and `/dev/sda` READ errors, single-disk storage, and
unverified independent backup remain open risks.

## Proposed retention and release gates

Propose `L1_METADATA_PRESERVED`, `L2_CURRENT_RAW_EVIDENCE_REQUIRED`, and
`L3_HISTORICAL_RAW_RETIREMENT_ALLOWED`, with separate open states
`L2_INDEPENDENT_BACKUP_NOT_VERIFIED`, `HISTORICAL_RAW_DATA_LOSS_RISK`,
`STORAGE_HEALTH_RISK_OPEN`, and `MAINTAINER_DELETION_APPROVAL_REQUIRED`. This
does not replace the previous full-workspace backup gate until explicitly
approved. Keep `/dev/sda` / `ata5` BadCRC and READ errors open; a clean recent
kernel query is not proof of device health.

Release remains **`RELEASE_CANDIDATE — NOT_PUBLISHED`**. Four manipulation
provider intersections remain `TESTED_BOUNDED`; no new formal Qualification
is granted. The current S5-C2 provider-free receipt (147 tests plus six
subtests) is an existing record, not a rerun in C6. This documentation and
inventory audit made no task/source changes.

## Checks

- **PASS:** current public refs and immutable tag object readback.
- **PASS:** L2 22/22 size and SHA-256 verification; all C5 file rows still
  match the current `lstat` snapshot; no L1/L2 inode aliases.
- **PASS:** all 17 L3-A cache/source paths exist and were identity checked;
  all three source manifests match their SHA-256 values.
- **PASS:** detached checkout clean, commit ancestry and Gitlink identities
  checked; exact cited receipt hashes recorded.
- **NOT_RUN:** fresh test suite, native tasks, full historical archive hash,
  external PhysPi/Skill consumer inventory, independent backup/restore.
- **NOT_RUN:** all deletion operations. **No files were deleted or moved.**
