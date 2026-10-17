# v1.1.0 Release Readiness Gates

**RELEASE_CANDIDATE — NOT_PUBLISHED**

Public `develop` includes the S4.5 functional unit, converter fix, and S5-B
candidate documents through `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`.
The local C8 preflight and its final manifest receipts are recorded on the
current maintenance branch; its release-governance updates and exact deletion
manifests have not been integrated remotely. Publication remains **BLOCKED**. The previous
full-workspace backup gate remains active because no scoped-retention waiver or
deletion batch has been approved.

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
| Release metadata preservation | **PASS — LOCAL_GIT_ONLY; C8 DOCS NOT PUBLIC** | C8 rechecked 84 tracked L1 files (1,042,038 bytes) against path, size, inode/link-count, and SHA-256 identities. The C8 documents are committed locally; no public integration was authorized or performed. |
| Current TaskEnv raw evidence | **PASS — L2_RAW_EVIDENCE_LOCALLY_VERIFIED** | 22 selected files, 24,563,669 bytes, including six H5 files and bounded SB3/batch raw receipts; local sizes/hashes are verified. This is not an independent backup. |
| Raw evidence backup | **BLOCKED — L2_INDEPENDENT_BACKUP_NOT_VERIFIED** | No independent copy or restore read exists; hashes cannot restore missing files. The exact L2 list is in [the evidence index](evidence/README.md). |
| Historical workspace backup | **BLOCKED — L3_HISTORICAL_BACKUP_NOT_VERIFIED** | Historical raw data remains local and untouched. C8 estimates 75,417,538,560 bytes (70.24 GiB) of conditional, inode-deduplicated allocation across candidate batches; this is not a verified backup or guaranteed recoverable space. The v1.0.0 P1.6 recovery archive remains unresolved. |
| Scoped retention policy and residual-risk acceptance | **MAINTAINER_DECISION_REQUIRED** | C8 proposes `L1_METADATA_REQUIRED` / `L2_CURRENT_RAW_EVIDENCE_REQUIRED` / `L3_REVIEWED_RETIREMENT_ALLOWED`. This proposal has not replaced the full-workspace backup gate. The maintainer must explicitly approve the policy change and accept unbacked raw-data/storage risk before any waiver is recorded. |
| Cleanup proposal | **CLEANUP_PENDING_APPROVAL — EXACT LOCAL MANIFESTS; NO DELETION** | C8 final allowlists are in ignored `workspace/maintenance/p2_0_s5_c8_20261017/`. A: 17 files / 311,296 allocated bytes; B: 6,792 approved paths / 3,317,481,472 bytes plus 3 holds; C1: 3,382 P1.8 files / 10,978,766,848 bytes plus the source-bundle holdout; C2: 62,254 paths / 61,120,978,944 bytes plus 518 holds. No batch has exact-hash authorization; actual reclaimed bytes are zero. |
| P1.8 archive retirement | **MAINTAINER_DECISION_REQUIRED — IRREVERSIBLE LOSS REVIEWED** | The live archive reconciles to 3,298 exact common entries, 278 manifest-listed files already absent, and 85 live-only entries. The P1.8 source bundle remains held; retiring the approved portion permanently removes unbacked raw experiment data and some historical records. See the C8 loss assessment and exact C1 manifest before authorizing. |
| Remote evidence preservation | **MAINTAINER_DECISION_REQUIRED** | No separate authorization to integrate the S5-C3 evidence commit was given; remote file/hash verification is not run. |
| Publication authorization | **MAINTAINER_DECISION_REQUIRED** | No v1.1.0 tag, `main` change, or GitHub Release is authorized or created. |
| L3 retention and cleanup review | **MAINTAINER_DECISION_REQUIRED** | C8 revalidated exact A/B/C1/C2 path manifests. No known active repository TaskEnv consumer was found, but external PhysPi/Skill usage has not been exhaustively checked; historical raw recovery loss remains a maintainer risk decision. Actual reclaimed bytes: zero. |

The S5-C1/S5-C2 reports, proposed S5-C3 evidence package, and its review report are linked from the
[release package](README.md). C8 supersedes the earlier cleanup-candidate snapshot with exact local
manifests while preserving the S5-C5/C6 inventories as historical records. The
[C8 preflight report](evidence/retirement/c8_retention_and_cleanup_preflight.md)
records the manifest hashes and approval boundary. The [backup manifest](backup_manifest.json)
retains the previous blocked result. Neither the scoped-retention proposal nor cleanup is effective
before explicit maintainer approval.
