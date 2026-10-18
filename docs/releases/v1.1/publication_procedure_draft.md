# v1.1.0 Publication Procedure Draft

**RELEASE_CANDIDATE — NOT_PUBLISHED**

The functional unit and S5-B release-candidate documents are integrated into
public `develop` at `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`. The local
S5-C1 through S5-C8 release-review documents are on the current maintenance
branch and have not been integrated remotely. These local commits do not
publish v1.1.0.

Current review decisions and remaining procedure:

1. The maintainer accepted controller identity Option B, the current
   capability matrix within its existing `TESTED_BOUNDED` scope, breaking API
   migration disclosure, and the `NOT_RUN` fresh-install/relocated-regression
   limitations. Preserve the current controller algorithm, historic H5
   hashes, and all qualification labels. These decisions do not grant new
   qualification.
2. The exact authorized candidate `501c5e55e290870d8ac712ef82c7c33f6956c011`
   still had stale pending-decision wording in this readiness file. Per the
   maintainer's stop condition, it was not pushed. A local documentation
   correction is being prepared; the resulting exact SHA must be reviewed and
   authorized before normal fast-forward integration. Fetch `public` again
   immediately before that push, verify ancestry and protected refs, then read
   back the exact public SHA. Never force-push.
3. Preserve L1 metadata in Git and retain all 22 L2 files (24,563,669 bytes).
   The maintainer directed that the L2 copy proceed despite the historic disk
   warning. The current host exposes only `/dev/sda`; no independent disk or
   network destination is mounted. Do not copy L2 to another directory on the
   same device and do not claim a backup. The backup gate remains
   `L2_INDEPENDENT_BACKUP_NOT_VERIFIED` until a separately mounted/authorized
   destination is copied, hash-verified, and tested with representative
   restore reads. C8 acceptance of historical L3 loss does not waive L2.
4. Keep the fresh-install check and full relocated-checkout regression as
   `NOT_RUN`; their limitations are accepted for this review. The historical
   exploratory 139 PASS / 8 FAIL result remains disclosed; do not report a
   relocated full-suite or native-route pass.
5. After documentation integration and a verified L2 backup, perform one
   final source/ref/evidence readback. Repeat native runs only if the selected
   execution source changes or a specific unresolved risk warrants one.
6. Publication is a separate step and is not authorized here. Before it,
   present the exact RELEASE_COMMIT, `main`/`develop`/release-branch/tag
   operations, L2 backup receipt, bounded capability claims, breaking API
   notice, and accepted limitations. Wait for an explicit Publication GO.
7. Only after that GO may the approved procedure update `main`, create the
   `v1.1.0` branch and annotated tag, and publish a GitHub Release if it is
   explicitly included. Read back every remote ref; never move v1.0.0.
8. Branch/worktree cleanup requires a separate exact-name approval after
   publication. Preserve the frozen v1.0.0 worktree, the retained C8 worktree
   and holdouts, all unique logs, and unrelated refs.

The release remains **PUBLICATION_BLOCKED** solely on the release gate because
no independent L2 destination is currently available; the reviewed develop
integration is separately paused until the corrected documentation commit's
exact SHA is authorized. No backup waiver is approved. C8 closure is accepted
with its retained worktree, holdouts and missing per-file deletion receipts.
See the [release readiness](release_readiness.md), [release evidence
index](evidence/README.md), and [S5-C3 publication
checklist](s5_c3_publication_checklist_draft.md).
