# v1.1.0 Candidate Known Limitations

**RELEASE_CANDIDATE — NOT_PUBLISHED**

- The current tested task scope is four bounded scalar CPU intersections:
  selected PickCube and NutAssembly on GeoPhys and MuJoCo. This is not
  provider-wide interoperability or formal qualification.
- GeoPhys NutAssembly completed the physical task and planned Outcome V1 route
  while the original strict Expert lifecycle recorded
  `stable_height_mismatch`; the accepted warning does not rewrite the strict
  failure. MuJoCo's original Expert completed without that warning.
- No new P1.8 FULL, D0, D1, or D2 qualification was performed. H5 storage
  roundtrip is not exact replay.
- No manipulation checkpoint inference, general manipulation PPO, or
  parallel manipulation learner qualification is claimed.
- GeoChora-owned Static Template physics and Go2-specific implementation are
  retired. The generic batch contracts and GeoPhys Rigid Batch adapter remain,
  but no native GeoPhys Rigid Batch validation was performed in S4/S4.5.
- Pendulum SB3, batch, and rasterizer results are bounded CPU smokes only.
  There is no Native Flora qualification or general Physics × Renderer
  interoperability.
- Fresh dependency installation was not executed for this preparation. The
  source checkout/reproduction smoke uses the already validated Python
  3.12.14 environment; see [installation](installation.md).
- PickCube's production controller identity includes the hash of generated
  MJCF bytes that contain the absolute checkout root. The identity therefore
  changes when the same source tree is checked out at a different path; both
  values and normalized XML hash are recorded in the source manifest. A
  provider-free one-action controller probe produced the same physical control
  target fields across the two checkouts, but did not apply that target through
  a provider. Cross-checkout controller hash equality is not guaranteed. The
  provisional recommendation is to retain this limitation; maintainer decision
  remains open. The relocated-checkout full regression is NOT_RUN; preserve the
  exploratory 139 PASS / 8 FAIL result and its explanation in the S5-C1 receipt.
- **OPEN storage risk:** `/dev/sda` / `ata5` has recorded BadCRC and READ I/O
  errors. The workspace resides on one physical disk and an independent backup
  has not been verified. A clean recent kernel scan does not close this risk.
- **Proposed retention scope is not yet approved:** L1 summaries are in local
  Git; S5-C4/C5/C6 documentation is prepared in a local review commit and is
  not public. The exact L2 set has 22 files (six H5 files), totaling
  24,563,669 bytes. All paths,
  sizes, and hashes match on the existing `/dev/sda`; no independent copy or
  restore read exists. SHA-256 metadata cannot restore missing raw data. S5-C5
  reclassified the ignored workspace using allocated file blocks: L3-A 17
  cache files / 311,296 bytes; L3-B 6,795 paths / 3,317,497,856 unique bytes,
  including a registered clean-checkout worktree; and L3-C 66,155 historical
  paths / 72,514,465,792 unique bytes. C6 identified four worktree receipts to
  preserve, three old P1.1 candidate files and one failed environment-selection
  receipt to hold, 516 unresolved L3-C rows, and two symlinks outside any
  proposed file allowlist. L3-D has no remaining C5 file rows, while external
  PhysPi/Skill consumers remain unverified. These are conditional review
  estimates; actual reclaimed space is zero. No approval envelope authorizes
  deletion. The earlier
  full-workspace `BACKUP_NOT_VERIFIED` gate remains active until a maintainer
  explicitly approves a replacement policy and accepts the unbacked L2/L3
  risks. No L2 or L3 files were deleted or rewritten.
- **Historical recovery-location gap:** the v1.0.0 archive manifest records a
  205,486,080-byte, 441-member P1.6 recovery tar, but the S5-C4 workspace
  metadata scan did not locate a matching path or size. Its availability is
  `UNKNOWN_REVIEW_REQUIRED`; the tracked P1.6 closure metadata is not a
  replacement for the raw tar. The P1.8 integration archive is present locally
  at the path recorded in the S5-C4 audit, with apparent size matching the
  v1.0.0 archive manifest. Neither archive has a verified independent backup.
- **Cleanup is not authorized:** exact L3-A/B/C source manifests remain in the
  ignored S5-C5 maintenance directory. The [S5-C6 preparation](../../module/task_env/p2_0_s5_c6_l3_retirement_preparation.md)
  and its three tracked envelopes bind each proposal to those exact hashes;
  every `execution_allowlist` is empty. The registered worktree requires a
  Git-aware, separately approved removal after its four receipts are
  preserved. Historical raw retirement requires separate acceptance of
  irreversible loss and external-consumer review. No cleanup has been
  performed.
- External users and deployments may rely on removed APIs that repository
  scans cannot discover. The compatibility inventory is the migration record;
  no silent aliases are supplied.
