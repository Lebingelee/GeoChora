# v1.1.0 Release Readiness Gates

**RELEASE_CANDIDATE — NOT_PUBLISHED**

Public `develop` includes the S4.5 functional unit, converter fix, and S5-B
candidate documents through `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`.
The local C8 preflight and its final manifest receipts are recorded on the
current maintenance branch; its release-governance updates and exact deletion
manifests have not been integrated remotely. Publication remains **BLOCKED**. The previous
full-workspace backup gate remains active because no waiver was approved. On 2026-10-18 the maintainer authorized all four exact C8 batches and accepted C1/C2 loss, but a new unclassified storage-counter anomaly stopped execution before A. See [the C8 execution report](c8_execution_and_phase2_closure.md).

| Gate | Status | Evidence / remaining condition |
| --- | --- | --- |
| Functional integration | **PASS** | Normal fast-forward from `0ff2d846` to `bee498d1d784015f034c5b4af34320fdffa61411`; public readback matched. |
| Release-document integration | **PASS** | Normal fast-forward from `bee498d1` to `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`; public readback matched. S5-C1 documentation commit `2f8555a4c86470fb63cd2386a6e88729d4795a23` and S5-C2 report updates remain local. |
| Protected refs and ancestry | **PASS** | Public `main` is `e4e39883fbe01d4be4b172a53a535ef0095b3d64`; annotated v1.0.0 tag object `17c3100d4fabcb061c23569dea49973ebd177d51`, peeled commit `42787f5e4f658a3f81fdd2140cf7544d6342c783`; all unchanged after both integrations. |
| Source identity / selected task closure | **PASS — LOCAL CHECK** | Selected task, controller, runtime, provider, and object-owner sources did not change in `bee..2fb`; exact task identities remain listed in the candidate matrix. |
| Bounded functional regression | **PASS — TESTED_BOUNDED** | S5-C2 rerun at `2fb60de`, Python 3.12.14: 147 passed, 6 subtests passed, one upstream warning, 160.07 s. No new native route was run. |
| API migration disclosure | **PASS — DISCLOSURE COMPLETE** | Breaking task UID, imports, runtime options, and CLI changes are documented; release-notice approval remains separate. |
| Controller identity decision | **MAINTAINER_DECISION_REQUIRED** | Recommend Option B: retain current path-sensitive controller identity. Cross-checkout equality is not guaranteed; no relocated native rollout. |
| Existing-environment detached checkout | **PASS — BOUNDED** | Exact Gitlinks and construct/reset/close smokes for both tasks/providers; no full route. |
| Fresh Python dependency installation | **NOT_RUN** | Existing Python 3.12.14 environment used. Decide whether this limitation is acceptable for a source-based release. |
| Full relocated-checkout regression | **NOT_RUN** | Prior exploration was 139 PASS / 8 FAIL; test-helper and path issues were analyzed, but the full suite was not rerun. |
| Submodule/source recovery | **PASS — LOCAL CHECK ONLY** | Required Gitlinks are present; 94/94 retired blobs, 10/10 migrated blobs, and 8/8 enumerated H5/checkpoint hashes matched. No independent restore was performed. |
| v1.1.0 capability matrix approval | **MAINTAINER_DECISION_REQUIRED** | One candidate matrix; four manipulation/provider intersections remain TESTED_BOUNDED, not newly qualified. |
| Previous full-workspace backup gate | **BLOCKED — BACKUP_NOT_VERIFIED** | The earlier requirement to back up the full workspace remains active until scoped retention is explicitly approved. The prior single-disk/no-destination observation is preserved. |
| Release metadata preservation | **PASS — LOCAL_GIT_ONLY** | Original 84-file L1 baseline and 37 exact historical records verified before factual governance updates; original bytes remain in commit `153af68`. Current updates are local documentation migrations, not raw Evidence changes. |
| Current TaskEnv raw evidence | **PASS — L2_RAW_EVIDENCE_LOCALLY_VERIFIED** | 22 selected files, 24,563,669 bytes, including six H5 files and bounded SB3/batch raw receipts; local sizes/hashes are verified. This is not an independent backup. |
| Raw evidence backup | **BLOCKED — L2_INDEPENDENT_BACKUP_NOT_VERIFIED** | No independent copy or restore read exists; hashes cannot restore missing files. The exact L2 list is in [the evidence index](evidence/README.md). |
| Historical workspace backup | **BLOCKED — L3_HISTORICAL_BACKUP_NOT_VERIFIED** | Historical raw data remains local and untouched. C8 estimates 75,417,538,560 bytes (70.24 GiB) of conditional, inode-deduplicated allocation across candidate batches; this is not a verified backup or guaranteed recoverable space. The v1.0.0 P1.6 recovery archive remains unresolved. |
| Scoped retention policy and residual-risk acceptance | **PARTIAL — RETIREMENT APPROVED; BACKUP WAIVER NOT APPROVED** | L1/L2 preservation and exact A/B/C1/C2 retirement authorized on 2026-10-18, including C1/C2 permanent historical loss. Full-workspace and independent L2 backup gates remain active. |
| Approved C8 execution | **BLOCKED — STORAGE_SAFETY_STOP; 0 DELETED** | Exact four hashes are authorized and unchanged; all 72,445 candidate file entries still match. SCSI `ioerr_cnt` rose 2000→2005; causality unresolved. No deletion or worktree removal attempted. |
| P1.8 archive retirement | **APPROVED — NOT_RUN_STORAGE_STOP** | C1 exact loss accepted; all 3,383 live archive files remain. The source bundle is held; actual irreversible loss this execution is none. |
| Remote evidence preservation | **MAINTAINER_DECISION_REQUIRED** | No separate authorization to integrate the S5-C3 evidence commit was given; remote file/hash verification is not run. |
| Publication authorization | **MAINTAINER_DECISION_REQUIRED** | No v1.1.0 tag, `main` change, or GitHub Release is authorized or created. |
| L3 retention and cleanup review | **AUTHORIZATION PASS; EXECUTION BLOCKED** | Existing 522 holdouts remain. B nested GeoPhys is a primary worktree, so the described non-forced nested removal is not executable; no force/deinit/manual fallback was attempted. |

The S5-C1/S5-C2 reports, proposed S5-C3 evidence package, and its review report are linked from the
[release package](README.md). C8 supersedes the earlier cleanup-candidate snapshot with exact local
manifests while preserving the S5-C5/C6 inventories as historical records. The
[C8 preflight report](evidence/retirement/c8_retention_and_cleanup_preflight.md)
records the manifest hashes and approval boundary. The [backup manifest](backup_manifest.json)
retains the previous blocked result. The exact retirement scopes are now approved, but execution is safety-blocked. Backup gates remain unwaived; [the dated C8 receipt](evidence/retirement/c8_execution_receipt_20261018.json) records authorization and actual outcomes.
