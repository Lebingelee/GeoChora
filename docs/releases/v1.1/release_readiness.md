# v1.1.0 Release Readiness Gates

**RELEASE_CANDIDATE — NOT_PUBLISHED**

Public `develop` now includes the S4.5 functional unit, converter fix, and S5-B
candidate documents through `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`.
Publication remains **BLOCKED**.

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
| Independent backup verification | **BLOCKED — BACKUP_NOT_VERIFIED** | No authorized independent destination found. No copy or restore test was attempted. |
| Publication authorization | **MAINTAINER_DECISION_REQUIRED** | No v1.1.0 tag, `main` change, or GitHub Release is authorized or created. |

The S5-C1 report and current S5-C2 integration/backup receipt are linked from
the [release package](README.md). The [backup manifest](backup_manifest.json)
records the required set and the reason publication remains blocked.
