# v1.1.0 Release Readiness Gates

**RELEASE_CANDIDATE — NOT_PUBLISHED**

| Gate | Status | Evidence / remaining condition |
| --- | --- | --- |
| Source integrity | **PASS WITH RECORDED LIMITATION** | Exact local ancestry reviewed through `bee498d`; selected task source files are unchanged. A relocated checkout produces a different PickCube controller identity because raw MJCF includes the checkout path; Artifact/config and normalized MJCF match. |
| Git ancestry and protected refs | **PASS** | Freshly fetched public `develop` is `0ff2d846`; local source chain is an ancestor. `main` and annotated `v1.0.0` refs match recorded identities. Re-fetch before any integration or publication. |
| Task/runtime regression | **PASS — TESTED_BOUNDED** | 147 tests plus 6 subtests and accepted task/provider receipts; no new full routes were needed because selected execution closures are unchanged. This is not qualification. |
| Public API compatibility disclosure | **PASS — REVIEW REQUIRED** | Breaking identities and migration/recovery routes are listed. Maintainer must approve the final external-user migration notice before publication. |
| Capability matrix correctness | **PASS — CANDIDATE** | v1.1.0 matrix is the sole current matrix. NutAssembly H5 hashes were reconciled against final-source reports and retained files. Maintainer review remains required. |
| Documentation consistency | **PASS — BOUNDED** | Current target/version policy, active command paths, local links, and nine CLI help invocations were checked. Historical reports remain labeled by their original review time. |
| Clean-checkout reproduction | **PASS — BOUNDED** | Detached `bee498d` worktree, exact two root Gitlinks, and four selected UID/provider construct/reset/close cases passed. No full routes or fresh dependency installation were run. Relocated-root controller identity variation is documented. |
| Fresh dependency installation | **NOT_RUN** | Requirements and source-based installation steps are documented, but pip installation into a clean environment was not tested. |
| Submodule and asset availability | **PASS — EXACT OBJECT FETCH** | Required root Gitlink identities match; exact pinned commits were fetch-dry-run resolved from both declared remotes and initialized in the disposable worktree. |
| Evidence/H5 provenance | **PASS — RECORDED** | Accepted H5 hashes and source/config/Artifact identities are recorded. No new qualification is claimed. |
| Independent backup verification | **BLOCKED — BACKUP_NOT_VERIFIED** | Only `/dev/sda` is available; no independent copy or restore test exists. See [backup manifest](backup_manifest.json). |
| Version policy documentation | **PASS — RC ONLY** | `v1.1.0` is selected; policy explicitly documents breaking changes and does not claim strict SemVer. |
| Maintainer release authorization | **MAINTAINER_DECISION_REQUIRED** | This candidate prep authorizes no merge, push, tag, `main` change, or publication. |

Release publication remains blocked by independent backup/restore verification,
fresh dependency-install decision, final review of compatibility/capability
documents, explicit maintainer authorization, and review of the
checkout-root-sensitive PickCube controller identity policy. `BACKUP_NOT_VERIFIED`
is an open release blocker.
