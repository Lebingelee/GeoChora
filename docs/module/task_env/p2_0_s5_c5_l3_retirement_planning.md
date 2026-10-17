# P2.0-B S5-C5 — L3 Historical Evidence Retirement Planning

**RELEASE_CANDIDATE — NOT_PUBLISHED**
**Disposition:** `DRY_RUN_ONLY`; no workspace item was removed, moved, rewritten, or reserialized.

## Baseline and scope

The public `develop` ref was re-read from the canonical `public` remote at
`2fb60de7851bf2e5651c2dc99fff7451c16e1a94`; public `main` remains
`e4e39883fbe01d4be4b172a53a535ef0095b3d64`. The annotated `v1.0.0` tag object
is `17c3100d4fabcb061c23569dea49973ebd177d51`, peeled to
`42787f5e4f658a3f81fdd2140cf7544d6342c783`. The local branch is
`codex/p2-0-b-s4-5-b-workflow-consolidation` at
`28dc2f48a6c16defa9bb3c8037e717a4873ae523`. The S5-C4 tracked documentation
changes were already dirty before this audit; this report and the C5 updates
are additional local changes and have not been pushed.

The audit preserves the C4 no-follow metadata inventory, refreshes exact
candidate file metadata with `lstat`, and hashes only the 22 L2 files, the 17
bytecode-cache candidates, and a few small maintenance receipts whose
classification was resolved by reading them. It did not hash historical
archives or scan their contents. File manifests are in the ignored local
directory `workspace/maintenance/p2_0_s5_c5_20261017/`; their SHA-256 values
are recorded below. These machine-specific manifests are review inputs, not
release metadata and not executable cleanup scripts.

## L1/L2 preservation

The existing L1 inventory and all tracked release, capability, source/recovery,
migration, acceptance, and historical decision metadata remain present. L1
remains local until the existing C4/C5 documentation changes are reviewed and
integrated; public integration was not requested here.

The evidence index lists the complete accepted L2 set: **22 files, 24,563,669
bytes**, including six H5s and the current SB3 checkpoint. Every listed path
was re-statted and SHA-256 checked against the index on 2026-10-17: **22/22
matched**, with no missing or altered files. The six H5 files total 24,333,284
bytes. All 22 files have single-link metadata in this scan. They were not
copied, moved, opened for rewrite, or replaced with newer runs. The raw bytes
remain only on `/dev/sda`; independent backup and restore remain unverified.

The C5 manifests explicitly exclude every L2 path. No new TaskEnv capability
claim or Qualification decision was created. The four selected manipulation
routes remain `TESTED_BOUNDED`; the GeoPhys NutAssembly strict Expert
`stable_height_mismatch` remains distinct from its successful Outcome V1 task
result.

## L3 reclassification and space estimate

Sizes below use allocated file blocks from live `lstat`, deduplicating hardlinks
by `(device, inode)`. Directory blocks are excluded, making the estimates
conservative for fully removed subtrees. Content-identical but separately
allocated copies were not found by hashing; such blocks remain counted
separately. The estimates are conditional upper bounds, not approval or a
promise of free space. **Actual reclaimed space is zero** because no deletion
was performed.

| Class | Inventory | Unique allocated file bytes | Approx. GiB | Meaning |
| --- | ---: | ---: | ---: | --- |
| L3-A — regenerable | 17 files | 311,296 | 0.00029 | Unlinked `.pyc` caches with adjacent sources. Cache meaning is reproducible; byte-identical cache files are not guaranteed. |
| L3-B — superseded/review | 6,795 paths | 3,317,497,856 | 3.08964 | S1.5/S1.6 intermediate receipts, an obsolete P1.1 artifact/design note, small superseded test receipts, and a registered detached checkout. All require separate path-specific approval. |
| L3-C — historical raw review | 66,155 paths | 72,514,465,792 | 67.53436 | Qualification/archive, P1.6 policy-search, diagnostic/demo, and historical P2.0 receipts. Removal can permanently prevent exact re-audit. |
| L3-D — unresolved file rows | 0 | 0 | 0 | No file remained unclassified after reading the small C4 unknown receipts. External-consumer and some historical-source questions remain unresolved at group level, so this does not authorize cleanup. |

Potential L3-A + L3-B + L3-C file-block recovery is **75,832,274,944 bytes**
(about **70.6243 GiB**) before any directory blocks; this is not an approved
target. The exact category arithmetic is in
`workspace/maintenance/p2_0_s5_c5_20261017/reclassification_summary.json`.

Major L3 groups:

| Group | Purpose and source/recovery status | Current relevance | Allocated file blocks (unique) |
| --- | --- | --- | ---: |
| `workspace/qualification/` | Phase-I qualification, raw runs, recovery trees, and nested Git/submodule data. Historical v1.0.0 decisions and manifests are tracked, but most raw files are not in Git. The P1.8 local archive has 3,383 files, 10,989,629,850 logical bytes, and 10,997,342,208 file-block bytes in the C4 inventory; its directory-inclusive `du` observation was 11,001,884,672 bytes. Its historical GeoPhys Git bundle has a missing parent object; exact source-tree snapshots are present only in this local archive. | Historical qualification and source recovery. Some Phase-I diagnostic tools still consume files in this tree. No current selected task route or current release example uses it. | 65,489,723,392 |
| `workspace/experiments/p1_6_policy_search/` | P1.6 Flow policy search. The V2a provenance records Artifact SHA `fd5bc968…`, source baseline `df6bd560…`, CUDA execution, and `qualification_claim=false`. The tracked handoff records only 1/6 fixed-cohort 100 Hz checkpoint successes and explicitly requests Human Review. | Not a current manipulation checkpoint capability. Historical diagnostic/training scripts and profiles still read/write this directory; deleting it without retiring those routes would break them. Preserve its failures and Human Review context. | 5,839,798,272 |
| `workspace/diagnostics/` | Historical provider, Go2, renderer, contact, solver, and task diagnostics. Many per-file source revisions remain unknown; the file manifest does not claim exact Git recovery. | Not a selected-task production input. Historical diagnostic outputs and result distinctions remain review evidence. | 255,115,264 |
| `workspace/demos/v1_0_0_group_meeting_20261015/` | v1.0.0 cross-provider demonstration. Its report records GeoPhys source revision `c665ce50…`, historical Artifact identity, eight D1/D2 provider/mode results, task failures as well as successes, and `formal_qualified=false`; the directory includes source H5s and rendered videos. | Historical demonstration evidence only; it must not be presented as current interoperability qualification. No independent copy was verified. | 533,684,224 |
| `workspace/maintenance/p2_0_part_b_s1_5_20261016/` and `...s1_6.../` | Earlier S1.5/S1.6 bounded implementation and acceptance results. The S1.5 receipt records six native cases and no integration; S1.6 receipts include a GeoPhys 100 Hz NA-S0 seed-19 task-owned run at source `0dde256a…`, Artifact SHA `99e374bd…`, and explicit solution/controller/recipe/policy identities. Other stage entries have per-file source revisions in the manifest or `UNKNOWN`. Exact raw bytes are ignored and have no verified independent copy. | Later S2-C2 final-source L2 supports the current release claims, but these records explain how the selected task route and Outcome V1 decision were reached. Cleanup would lose exact historical run-level audit. | 846,471,168 + 480,866,304 |
| `workspace/maintenance/p2_0_v1_1_clean_checkout_20261017/` | Registered detached worktree at `bee498d1…`, which is an ancestor of current public `develop`; tracked status is clean. Gitlinks are GeoPhys `c665ce50…` and Menagerie `b846dd12…`. Nested workspace includes detached-checkout receipts, including the exploratory 139 PASS / 8 FAIL log. | Not an active runtime. The checkout can be reconstructed from recorded source/Gitlinks subject to object availability, but local receipts cannot be recreated byte-for-byte. It is registered: any later retirement must use an explicitly approved Git worktree operation, never recursive removal. | 1,990,119,424 |

P1.6 raw recovery remains an unresolved loss risk. The immutable v1.0.0
`archive_manifest.json` records a 205,486,080-byte, 441-member tar with SHA-256
`d31b64570e951b1cd694afe105f554dd44199d3f43aba689dac5c62c804d3d93`; the C4
workspace scan found no matching path or size. No recovery location or
independent copy is verified. Tracked P1.6 closure metadata cannot restore
that tar.

Historical Human/Judge decisions, failed runs, and v1.0.0 records remain
unchanged. The v1.0.0 tag/tree are a source recovery point for tracked blobs,
not a backup of ignored raw H5, checkpoints, logs, or all historical submodule
objects. Current repository documentation identifies PhysPi/Skills as an
external consumer boundary, but no cross-repository consumer inventory was
available here. That uncertainty blocks automatic retirement of any evidence
group with possible external references.

## Dependency analysis

| Dependency | Finding |
| --- | --- |
| Current selected TaskEnv production routes/public API | No selected PickCube or NutAssembly builder, `make_env`, RuntimeSession, or current example reads L3 at construction/runtime. The public capability matrix points to the exact L2 runs and tracked L1 identities. |
| Historical TaskEnv diagnostic/source callers | Present. Phase-I scripts and profiles reference `workspace/qualification/...` and `workspace/experiments/p1_6_policy_search/...`, including `task_env/diagnostics/phase1/policy_search/{flow100_rollout.py,flow_variants.py,flow100_train.py,flow100_data.py}`, `task_env/alg/agent_factory/config/profiles/geochora_flow.yaml`, and historical NutAssembly campaign modules. These are not selected production routes, but a cleanup would retire or break those historical command paths unless they are explicitly migrated. |
| Current test execution | The accepted S5-C2 provider-free result is 147 passed plus 6 subtests at `2fb60de`; it is in L2. No test suite was rerun for this documentation-only audit. Historical Phase-I diagnostics/tests may use L3 fixtures; the full 147-test command-to-fixture graph was not re-executed or exhaustively traced in C5. |
| Current developer examples | Examples use current public routes and repository assets; no example requires historical L3 input. Output directories named `workspace/` are generated outputs, not a read dependency on existing evidence. |
| Submodules/assets | Active selected providers/assets are pinned by the repository Gitlinks, outside `workspace/`. Copies and nested repositories under historical archives are recovery data, not active provider inputs. |
| L1/L2 evidence | L2 paths are separately protected and excluded from manifests. L1 documents cite historical decisions and archive manifests; those metadata do not restore raw files. |
| Git/source recovery | v1.0.0 immutable source and tags recover tracked code/metadata; the P1.8 GeoPhys parent gap and P1.6 missing tar show that Git recovery is incomplete for some historical raw/source snapshots. |
| External consumers / PhysPi Skills | Not exhaustively verified. No file/group with a plausible external relationship may be automatically approved while this remains unresolved. |

## Exact manifests and link accounting

The three manifests contain file-level path, logical size, allocated bytes and
512-byte blocks, device/inode/link count, symlink/hardlink status, owner/source
revision, current/historical dependency fields, recovery status, and proposed
action. No L1 or L2 path appears in any manifest.

| Manifest | SHA-256 | State |
| --- | --- | --- |
| `workspace/maintenance/p2_0_s5_c5_20261017/safe_regenerable_cleanup.json` | `033b4e63b1965ea293a11d02cc9d39985ff0cd75b8435149928ce99b496a3e14` | 17 exact `.pyc` paths; dry-run only |
| `workspace/maintenance/p2_0_s5_c5_20261017/superseded_experiment_cleanup.json` | `cf02a17bd96cc6e793fa4f640541b2d401c5ceb545d42895cdab8899533d61f7` | 6,795 exact paths; review only, includes registered worktree receipts and sources |
| `workspace/maintenance/p2_0_s5_c5_20261017/historical_raw_retirement_review.json` | `8359315ea46b0442a8c8bc0ed5c8834aa5d6b236a13e5319ff87038897557eed` | 66,155 exact historical paths (including two symlinks not followed) plus unresolved recovery note; no bulk raw hashes |

There are two workspace symlinks, both recorded without following them; one
points to the frozen v1.0.0 worktree under `.codex/worktrees/archive_v1_0_0`,
and one points back to `workspace/`. The scan records 750 hardlinked path
entries. The C manifest counts 206 hardlinked inodes once; 16,898,535,424
bytes of path-summed allocated blocks are duplicate hardlink paths rather than
additional disk usage. There are no hardlinks in the A/B candidate sets.
Nested Git packs and shared hardlinks were counted by inode. Content-identical
but independently allocated files were not hash-deduplicated.

The only registered nested worktree under the scanned workspace is the clean
checkout above. It has no unique main-repository commit relative to public
`develop`, but contains local ignored receipts and pinned submodule checkouts.
Its root, GeoPhys, and Menagerie `.git` files point to the parent repository's
shared worktree administration under `/home/lly/Program_Files/Geochora/.git`;
the object stores are outside `workspace/`. The workspace scan found no nested
`.git` directories or object alternates under `workspace/`, and the inspected
shared object stores had no `objects/info/alternates` file. Thus the L3-B
estimate counts only file blocks physically under the checkout. Removing that
registered worktree would not reclaim its shared parent Git objects, and its
submodule Git administration also lives outside the counted subtree. No
worktree removal is included as an executable command.

## Retention proposal and required approvals

Propose this policy for maintainer decision:

- `L1_METADATA_REQUIRED`
- `L2_CURRENT_RAW_EVIDENCE_REQUIRED`
- `L3_REVIEWED_RETIREMENT_ALLOWED`

Track these risks separately:

- `L2_INDEPENDENT_BACKUP_NOT_VERIFIED`
- `L3_HISTORICAL_RECOVERY_LOSS_RISK`
- `MAINTAINER_DELETION_APPROVAL_REQUIRED`

This proposal is **not effective** until explicit maintainer approval. The
previous full-workspace backup gate remains active and `BACKUP_NOT_VERIFIED`;
it is not waived, satisfied, or replaced by this report. SHA-256 metadata
cannot restore missing raw files. The `/dev/sda` / `ata5` BadCRC and READ I/O
history and the unverified independent-backup limitation remain open. The
recent kernel query returned no matching ATA/SATA/read/write error lines, but
that does not establish storage health.

Recommended review sequence:

1. Accept or reject the proposed L1/L2/L3 backup-policy change and explicitly
   acknowledge that L2 and historical L3 have no verified independent copy.
2. Resolve external PhysPi/Skill and Human/Judge references, then review the
   P1.6 missing-tar location and P1.8 archive loss consequences.
3. Approve any L3-A cache removal by exact path as its own small action.
4. Review L3-B individually. Preserve nested clean-checkout receipts first;
   retire the registered worktree only via an approved Git worktree action.
5. Review L3-C group-by-group and explicitly accept the loss of exact
   historical re-audit capability before any raw evidence retirement.
6. Keep L1/L2 and the immutable v1.0.0 tree untouched throughout.

## Checks performed

- **PASS:** L2 path/size/SHA-256 checks, 22/22; no file was modified.
- **PASS:** manifests parse as JSON; all manifest paths are outside L1/L2;
  every L3-B/L3-C file row still exists with refreshed `lstat` metadata.
- **PASS:** `git diff --check` and local release-document link checks (see
  final handoff).
- **NOT_RUN:** full historical raw archive hashing, fresh test suite,
  independent copy/restore, external PhysPi consumer scan, and any cleanup.
- **No cleanup performed.**
