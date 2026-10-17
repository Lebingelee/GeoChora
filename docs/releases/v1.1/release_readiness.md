# v1.1.0 Release Readiness Gates

**RELEASE_CANDIDATE — NOT_PUBLISHED**

| Gate | Status | Evidence / remaining condition |
| --- | --- | --- |
| Functional integration authorization | **MAINTAINER_DECISION_REQUIRED** | Recommend the S4.5-A/B + CLI unit through `bee498d1`; no push or merge occurred. |
| Release-document integration authorization | **MAINTAINER_DECISION_REQUIRED** | Review the S5-A/S5-B candidate docs through `2fb60de` separately. |
| Source integrity and ancestry | **PASS** | Exact parent chain checked through `2fb60de`; the tested S5-B base had a clean tracked worktree before S5-C1 review docs were added. S5-C1 documents are maintained as a separate local review package and are not part of either integration candidate. Public `develop`, `main`, and v1.0.0 tag identities were read back. |
| Task/runtime regression | **PASS — TESTED_BOUNDED** | 147 tests + 6 subtests; four accepted task/provider full-route receipts remain bound to their recorded source. No new routes were needed. |
| Public API compatibility disclosure | **PASS — DISCLOSURE COMPLETE** | Breaking identities and recovery routes are in the inventory; final external migration notice still needs maintainer review. |
| Controller portability decision | **MAINTAINER_DECISION_REQUIRED** | Recommend retaining path-sensitive identity; controller hash equality across checkout roots is not guaranteed. No controller code changed. |
| Detached-checkout reproduction | **PASS — BOUNDED** | Existing validated environment; exact Gitlinks; four construct/reset/close cases. No full relocated regression. |
| Fresh dependency installation | **NOT_RUN** | No clean Python environment install. Source-based commands are documented; repository packaging metadata is absent. |
| Git submodule and asset availability | **PASS** | Exact root Gitlinks are initialized and exact commits were remotely resolvable. Panda asset bundle hashes match across tested checkouts. |
| Evidence and source recovery | **PASS — LOCAL CHECK ONLY** | 94/94 retired source blobs, 10/10 migrated blobs, and 8/8 listed ignored H5/checkpoint files match hashes. No independent copy is implied. |
| v1.1.0 capability matrix approval | **MAINTAINER_DECISION_REQUIRED** | One current candidate matrix; bounded results and non-claims are explicit. |
| Independent backup verification | **BLOCKED — BACKUP_NOT_VERIFIED** | Only `/dev/sda` is available; no authorized external destination or restore verification. |
| Maintainer publication authorization | **MAINTAINER_DECISION_REQUIRED** | No tag, `main` update, or GitHub Release is authorized here. |

**Publication status: BLOCKED.** Independent backup and restore verification
is the primary blocker. The [S5-C1 receipt](../../module/task_env/p2_0_s5_c1_final_release_gate.md)
contains the exact refs, portability analysis, test results, and open decisions.
See the [backup manifest](backup_manifest.json) and [S5-C2 procedure draft](publication_procedure_draft.md).
