# v1.1.0 Publication Procedure Draft

**RELEASE_CANDIDATE — NOT_PUBLISHED**

The reviewed S5-C1–C8 release-review chain is integrated into public
`develop` at `c679267790726d3e34d080a133535c2c308a7a55`. The maintainer
authorized using the `v1.1.0` candidate branch as a public L2 evidence backup.
The exact 22-file L2 copy is present and verified at
`745efc6a6693a7d10407c6ddd02837a2ae574131`; this does not publish v1.1.0 or
grant qualification. The latest public `v1.1.0` branch readback is
`e0e861998711f7ec5e1f10784ca857dc39d7d575`, which retains that payload.

Current review decisions and remaining procedure:

1. The maintainer accepted controller identity Option B, the current
   capability matrix within its existing `TESTED_BOUNDED` scope, breaking API
   migration disclosure, and the `NOT_RUN` fresh-install/relocated-regression
   limitations. Preserve the current controller algorithm, historic H5
   hashes, and all qualification labels. These decisions do not grant new
   qualification.
2. The maintainer authorized the exact candidate `c679267790726d3e34d080a133535c2c308a7a55`
   for normal fast-forward integration. Public `develop` now reads back that
   exact SHA; public `main` and the immutable `v1.0.0` tag are unchanged.
3. Preserve L1 metadata in Git and retain all 22 L2 files (24,563,669 bytes).
   The maintainer explicitly approved publishing the exact L2 originals,
   including embedded local absolute paths, to the public `v1.1.0` candidate
   branch. Remote readback verified all 22 blob sizes and SHA-256 values; a
   representative NutAssembly H5 opened and a PickCube result JSON parsed from
   fetched Git objects. This is an L2-only off-host copy in the same public
   GitHub repository, not a separately administered backup or full-workspace
   backup. The former full-scope backup remains unverified; no missing historical
   raw data is restored by this copy.
4. Keep the fresh-install check and full relocated-checkout regression as
   `NOT_RUN`; their limitations are accepted for this review. The historical
   exploratory 139 PASS / 8 FAIL result remains disclosed; do not report a
   relocated full-suite or native-route pass.
5. L2 remote readback is complete at `745efc6a6693a7d10407c6ddd02837a2ae574131`.
   Before any publication, perform a fresh source/ref/evidence readback.
   Repeat native runs only if the selected execution source changes or a
   specific unresolved risk warrants one.
6. Publication is a separate step and is not authorized here. Before it,
   present the exact RELEASE_COMMIT, `main`/`develop`/release-branch/tag
   operations, L2 backup receipt, bounded capability claims, breaking API
   notice, and accepted limitations. Wait for an explicit Publication GO.
7. Only after that GO may the approved procedure update `main`, finalize the
   `v1.1.0` branch as the frozen release source, create its annotated tag, and
   publish a GitHub Release if explicitly included. Read back every remote
   ref; never move v1.0.0.
8. Branch/worktree cleanup requires a separate exact-name approval after
   publication. Preserve the frozen v1.0.0 worktree, the retained C8 worktree
   and holdouts, all unique logs, and unrelated refs.

The release remains **RELEASE_CANDIDATE — NOT_PUBLISHED**. The scoped L2 copy is
verified, while the full-workspace backup remains unverified; this L2 copy does
not cover all submodules or local-only historical refs. C8 closure is
accepted with its retained worktree, holdouts and missing per-file deletion
receipts. No `main` update, release tag, or GitHub Release is authorized by
this backup operation.
See the [release readiness](release_readiness.md), [release evidence
index](evidence/README.md), and [S5-C3 publication
checklist](s5_c3_publication_checklist_draft.md).

## Proposed backup-scope exception — NOT ACCEPTED

The exact L2 copy is 22 files / 24,563,669 bytes and is verified off-host on
the public GitHub `v1.1.0` branch. It protects against loss of the local
`/dev/sda` copy, but the source and backup share one public repository and
account. A separately administered destination, a full-workspace bundle, and
separate submodule bundles are not verified.

Proposed exception for v1.1.0 only: retain L1 release metadata in the final
Git history and retain all 22 L2 raw files; accept the verified GitHub branch
copy as the L2 preservation copy; waive only the requirement for a second,
separately administered L2 destination and a full historical workspace
bundle. Explicitly accept the same-repository/account common-mode risk, the
open historical SATA/BadCRC risk, and the already accepted C8 L3 retirement
loss. This proposal does not claim a full backup PASS, restore the retired L3
bytes, close the storage risk, grant qualification, or authorize publication.
The exception takes effect only if the maintainer explicitly accepts it in the
final Publication GO. Until then, the independent-backup gate remains
`BACKUP_NOT_VERIFIED` and publication remains `PUBLICATION_BLOCKED`.
