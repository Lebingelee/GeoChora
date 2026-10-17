# v1.1.0 Release Readiness Gates

**RELEASE_CANDIDATE — NOT_PUBLISHED**

Public `develop` includes the S4.5 functional unit, converter fix, and S5-B
candidate documents through `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`.
Local S5-C3/C4/C5/C6 records preserve the acceptance package, retention audit,
and exact L3 retirement candidates; these updates are not remotely integrated.
Publication remains **BLOCKED**. The previous full-workspace backup gate stays
active until the maintainer approves a scoped retention proposal.

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
| Release metadata preservation | **PASS — LOCAL_GIT_ONLY; S5-C4/C5/C6 DOCS UNCOMMITTED** | S5-C3 L1 package is in local Git. C4/C5/C6 updates are prepared as a separate documentation commit; no public integration was authorized or performed. |
| Current TaskEnv raw evidence | **PASS — L2_RAW_EVIDENCE_LOCALLY_VERIFIED** | 22 selected files, 24,563,669 bytes, including six H5 files and bounded SB3/batch raw receipts; local sizes/hashes are verified. This is not an independent backup. |
| Raw evidence backup | **BLOCKED — L2_INDEPENDENT_BACKUP_NOT_VERIFIED** | No independent copy or restore read exists; hashes cannot restore missing files. The exact L2 list is in [the evidence index](evidence/README.md). |
| Historical workspace backup | **BLOCKED — L3_HISTORICAL_BACKUP_NOT_VERIFIED** | Qualification and historical records remain local and untouched. The inventory identifies 75,974,623,232 allocated bytes under `workspace/`; the v1.0.0 P1.6 recovery tar location is unresolved in the scanned workspace. The reduced policy would exclude L3 only after approval. |
| Scoped retention policy and residual-risk acceptance | **MAINTAINER_DECISION_REQUIRED** | S5-C6 proposes L1_METADATA_PRESERVED / L2_CURRENT_RAW_EVIDENCE_REQUIRED / L3_HISTORICAL_RAW_RETIREMENT_ALLOWED. It does not replace the active full-workspace gate. Approval and explicit acceptance of unbacked L2/L3 risk are required first. |
| Cleanup proposal | **CLEANUP_PENDING_APPROVAL — NO_EXECUTION_ALLOWLIST** | S5-C6 binds separate A/B/C proposals to the exact S5-C5 manifests. Every approval envelope has `execution_authorized: false`; the worktree receipts, 516 unresolved C rows, two symlinks, and external-consumer review remain holds. No bytes were reclaimed. |
| Remote evidence preservation | **MAINTAINER_DECISION_REQUIRED** | No separate authorization to integrate the S5-C3 evidence commit was given; remote file/hash verification is not run. |
| Publication authorization | **MAINTAINER_DECISION_REQUIRED** | No v1.1.0 tag, `main` change, or GitHub Release is authorized or created. |
| L3 retention and cleanup review | **MAINTAINER_DECISION_REQUIRED** | S5-C6 validated the A/B/C manifest hashes and current path metadata. External consumers are not exhaustively checked; L3-C includes irrecoverable raw data and remains blocked. Actual reclaimed bytes: zero. |

The S5-C1/S5-C2 reports, proposed S5-C3 evidence package, and its review report are linked from the
[release package](README.md). The [S5-C5 plan](../../module/task_env/p2_0_s5_c5_l3_retirement_planning.md)
and [S5-C6 retirement preparation](../../module/task_env/p2_0_s5_c6_l3_retirement_preparation.md)
bind exact L3 inventories to separate, non-executable approval proposals. The
[backup manifest](backup_manifest.json) retains the previous blocked result.
Neither the scope proposal nor cleanup is effective before explicit maintainer
approval.
