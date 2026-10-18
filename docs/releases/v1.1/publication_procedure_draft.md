# v1.1.0 Publication Procedure Draft

**RELEASE_CANDIDATE — NOT_PUBLISHED**

The functional unit and S5-B release-candidate documents are integrated into
public `develop` at `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`. The local
S5-C1 through S5-C8 release-review documents are on the current maintenance
branch and have not been integrated remotely. These local commits do not
publish v1.1.0.

Future release procedure:

1. Complete review of the local S5-C1 through S5-C8 release-gate, evidence,
   and cleanup records. After separate maintainer authorization for the exact
   release commit, fetch `public`, verify `public/develop` is its expected
   ancestor, and use a normal fast-forward only. Read back the exact public
   SHA; verify the remote L1 hashes and reject unexpected binaries, secrets,
   or host-local paths. Do not push unreviewed local documentation.
2. Obtain explicit maintainer acceptance of controller identity Option B, or
   stop for a separately scoped identity-stabilization proposal. Preserve all
   historic H5/controller hashes. The current recommendation and its bounded
   evidence are listed in [release readiness](release_readiness.md).
3. Record the maintainer's decision on fresh-install and full relocated-suite
   scope. Do not convert either `NOT_RUN` into `PASS` without execution.
4. Resolve the retention-policy proposal in
   [`backup_manifest.json`](backup_manifest.json). The existing full-workspace
   gate remains active unless the maintainer explicitly approves the scoped
   L1/L2/L3 policy and accepts the remaining risks. L1 hashes do not restore
   missing L2 files. If the reduced policy is approved, retain L1 in Git,
   preserve L2 on disk, and record `RAW_EVIDENCE_BACKUP_NOT_VERIFIED` and
   `HISTORICAL_WORKSPACE_BACKUP_NOT_VERIFIED` without promoting either to PASS.
   The specific proposed release exception is recorded in
   [release readiness](release_readiness.md); it is not approved by this draft.
   Obtain explicit risk acceptance before publication review.
5. Re-fetch public refs and verify the exact approved source tree, protected
   `main`, immutable v1.0.0 tag/Evidence, submodule Gitlinks, API migration
   inventory, capability matrix, and final provider-free regression. Repeat
   native runs only for a changed selected execution source or a specific
   unresolved risk.
6. Obtain maintainer approval for the release notes, migration notice,
   capability claims, limitations, final commit, and publication. The target
   remains v1.1.0 under GeoChora's project-specific versioning policy; no new
   qualification is implied.
7. Only after all gates pass and explicit authorization is given, create an
   annotated `v1.1.0` tag on the specifically approved commit. Read back both
   tag object and peeled commit. Publish the GitHub Release only after tag
   verification; treat tag creation and publication as separate authorized
   actions.
8. Record the release commit, tag object, peeled commit, backup manifest hash,
   submodule Gitlinks, final test receipts, and publication timestamp. Do not
   modify `main` or v1.0.0 without separate authorization.

The release remains **PUBLICATION_BLOCKED**. C8's exact retirement scopes
were approved and the maintainer accepted closure after observing ordinary
candidate path absence; the registered worktree and holdouts remain, and no
per-file deletion logs were saved. No scoped-backup replacement or waiver was
approved, so the independent backup gate remains active. See the [release
evidence index](evidence/README.md), [S5-C3 publication
checklist](s5_c3_publication_checklist_draft.md), and [S5-C2 integration
receipt](../../module/task_env/p2_0_s5_c2_public_integration_readiness.md).
