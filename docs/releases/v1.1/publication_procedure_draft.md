# v1.1.0 Publication Procedure Draft

**RELEASE_CANDIDATE — NOT_PUBLISHED**

The functional unit and S5-B release-candidate documents have been integrated
to public `develop` at
`2fb60de7851bf2e5651c2dc99fff7451c16e1a94`. The S5-C1 documentation commit
`2f8555a4c86470fb63cd2386a6e88729d4795a23` and S5-C2 report updates remain
local and are not part of public `develop`. These integrations do not publish
v1.1.0.

Future release procedure:

1. Complete review of the local S5-C1/S5-C2 release-gate documents. After
   maintainer approval and a separate documentation commit, fetch `public`,
   verify `public/develop` is the expected ancestor, and use a normal
   fast-forward only. Read back the exact public SHA. Do not push the local
   S5-C1 commit by itself or silently include unreviewed changes.
2. Obtain explicit maintainer acceptance of controller identity Option B, or
   stop for a separately scoped identity-stabilization proposal. Preserve all
   historic H5/controller hashes.
3. Record the maintainer's decision on fresh-install and full relocated-suite
   scope. Do not convert either `NOT_RUN` into `PASS` without execution.
4. Complete the independent backup using the source set in
   [`backup_manifest.json`](backup_manifest.json). Require a verified
   independent destination, capacity, hashes, bundle/object validation, exact
   submodule recovery, and representative restore reads. `BACKUP_NOT_VERIFIED`
   is a stop condition.
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

The release is currently **PUBLICATION_BLOCKED** by the independent backup
gate. See the [S5-C3 publication checklist](s5_c3_publication_checklist_draft.md)
and [S5-C2 integration receipt](../../module/task_env/p2_0_s5_c2_public_integration_readiness.md).
