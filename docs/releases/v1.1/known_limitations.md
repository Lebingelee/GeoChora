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
- **S5-C8 retirement authorized and manually completed with accepted evidence limits:** On 2026-10-18 the maintainer approved the four exact A/B/C1/C2 manifests and accepted possible permanent C1/C2 historical raw-data/source-snapshot loss. Assistant deletion stopped before its first unlink after `/dev/sda` SCSI `ioerr_cnt` rose from 2000 to 2005. The maintainer later reported two successful SMART refreshes, each correlated with a fixed +5 counter increment, with cached reads steady; individual low-level commands were not captured, so this does not explain every historical increment. After manual handling, 65,826 approved ordinary paths were observed absent; no per-file user unlink receipts exist. Current reports found no matching new ATA/READ error, and the observed CRC and bad-sector attributes did not increase. Counter-only growth is now an investigation signal; stop on actual ATA/block/filesystem errors, read/write failures, CRC or bad-sector growth, or integrity anomalies. The historical SATA/BadCRC risk remains OPEN, and SMART status does not establish device reliability. Original L1 and all 22 L2 files (24,563,669 bytes) were verified intact. The full-workspace backup requirement was explicitly not waived. See [the final C8 report](c8_manual_cleanup_final_report.md) and [monitoring revision](c8_storage_monitoring_revision.md).
- **Historical recovery-location gap:** the v1.0.0 archive manifest records a
  205,486,080-byte, 441-member P1.6 recovery tar, but the S5-C4 workspace
  metadata scan did not locate a matching path or size. Its availability is
  `UNKNOWN_REVIEW_REQUIRED`; the tracked P1.6 closure metadata is not a
  replacement for the raw tar. The original P1.8 integration archive is no
  longer present at its pre-retirement path: 3,382 approved ordinary paths are
  absent and the held source bundle remains. The historical GeoPhys bundle is
  incomplete for full source reconstruction. Neither historical archive has
  a verified independent backup.
- **Worktree and holdout limits:** Exact batch approvals persist. All 65,826 ordinary candidate paths are absent; 6,619 registered worktree entries and the 522 original holdouts remain. Storage safety remains unresolved. The three P1.1 holds, P1.8 source bundle, 516 unresolved C2 files and two symlinks remain excluded. B's inner GeoPhys is a primary repository rather than a removable linked worktree; the described non-forced removal cannot apply. No force, deinit or manual worktree deletion was performed. The existing S5-B receipt copies remain on the same disk and are not independent backup.
- External users and deployments may rely on removed APIs that repository
  scans cannot discover. The compatibility inventory is the migration record;
  no silent aliases are supplied.

- **C8 停止判据更正（2026-10-18）：** 维护者两次 SMART 刷新均令 SCSI 计数增加 5，而缓存读取不增加。当前将单独计数增量作为调查信号；实际 I/O、内核存储错误、CRC/坏扇区增长或哈希异常才触发相应停止。历史 SATA 风险与独立备份门槛仍保留，详见[监测修订](c8_storage_monitoring_revision.md)。
