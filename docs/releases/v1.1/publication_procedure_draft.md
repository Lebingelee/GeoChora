# v1.1.0 Publication Procedure Draft

**RELEASE_CANDIDATE — NOT_PUBLISHED**

This is a future procedure only. It does not authorize integration, a release
tag, a GitHub Release, or a `main` update. Do not execute the publication steps
until every blocking gate is resolved and the maintainer gives explicit
authorization.

1. Obtain separate maintainer authorization for the functional integration unit and the release-candidate documents. After authorization, the exact fast-forward sequence is:

   ```bash
   git fetch public
   test "$(git rev-parse public/develop)" = "0ff2d846a36c7014d2b40a530f52d99e64266ff9"
   test "$(git rev-parse public/main)" = "e4e39883fbe01d4be4b172a53a535ef0095b3d64"
   test "$(git rev-parse v1.0.0)" = "17c3100d4fabcb061c23569dea49973ebd177d51"
   test "$(git rev-parse 'v1.0.0^{}')" = "42787f5e4f658a3f81fdd2140cf7544d6342c783"
   git merge-base --is-ancestor public/develop bee498d1d784015f034c5b4af34320fdffa61411
   git push public bee498d1d784015f034c5b4af34320fdffa61411:refs/heads/develop
   test "$(git ls-remote public refs/heads/develop | cut -f1)" = "bee498d1d784015f034c5b4af34320fdffa61411"

   git fetch public
   test "$(git rev-parse public/develop)" = "bee498d1d784015f034c5b4af34320fdffa61411"
   test "$(git rev-parse public/main)" = "e4e39883fbe01d4be4b172a53a535ef0095b3d64"
   test "$(git rev-parse v1.0.0)" = "17c3100d4fabcb061c23569dea49973ebd177d51"
   test "$(git rev-parse 'v1.0.0^{}')" = "42787f5e4f658a3f81fdd2140cf7544d6342c783"
   git merge-base --is-ancestor public/develop 2fb60de7851bf2e5651c2dc99fff7451c16e1a94
   git push public 2fb60de7851bf2e5651c2dc99fff7451c16e1a94:refs/heads/develop
   test "$(git ls-remote public refs/heads/develop | cut -f1)" = "2fb60de7851bf2e5651c2dc99fff7451c16e1a94"
   ```

   Stop without pushing if either expected `develop` SHA differs, ancestry fails, or the target moves during the sequence. Readback verifies integration only; it does not publish v1.1.0. Neither command has been run.
2. Resolve the controller-identity portability decision. The current recommendation is to retain per-checkout identity and document that controller hash equality across checkout paths is not guaranteed. Do not rewrite prior provenance or H5 records.
3. Complete clean-environment installation validation if the maintainer requires it. Otherwise record the approved limitation: existing-environment detached construction smoke only; fresh installation remains NOT_RUN.
4. Copy the exact candidate source, all refs and Git objects, required submodules, recovery manifests, v1.0.0 Evidence, enumerated H5/checkpoints, release documents and test receipts to authorized independent physical or controlled external storage. From the repository root, create a Git bundle with `git bundle create geochora-v1.1.0-rc.bundle --all`; create separate `--all` bundles inside `GeoPhys/` and `asset/external/mujoco_menagerie/`. Verify each bundle with `git bundle verify`, compare all Gitlink SHAs, and hash copied files. Restore representative H5 and v1.0.0 Evidence from the destination and read them. Update the backup manifest only from observed results. Do not treat another path on `/dev/sda` as independent storage.
5. Re-fetch public refs. Verify the approved candidate tree, clean tracked worktree, exact Gitlinks, current capability matrix, migration inventory, protected `main` and immutable v1.0.0 tag/Evidence. Run the final bounded provider-free suite; repeat native runs only if task execution source changed or an uncovered specific risk requires them.
6. Obtain explicit maintainer approval for the release notes, compatibility notice, capability matrix, remaining limitations, and publication. At this point require the independent backup gate to be PASS; `BACKUP_NOT_VERIFIED` means stop.
7. Only after those approvals, tag the specifically approved develop commit as `v1.1.0` by annotated tag and verify the remote tag object plus peeled commit. Publish the release notes and candidate artifacts; do not create a tag from a moving or unreviewed branch.
8. Record the exact release commit, tag object, peeled commit, backup manifest hash, submodule Gitlinks, final test receipts, and publication timestamp in the release receipt. Keep v1.0.0 and its Evidence unchanged.

The target version remains **v1.1.0** under the GeoChora project-specific
versioning policy. This policy does not claim strict SemVer compatibility and
does not imply new capability qualification.
