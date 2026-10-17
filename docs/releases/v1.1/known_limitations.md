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
- External users and deployments may rely on removed APIs that repository
  scans cannot discover. The compatibility inventory is the migration record;
  no silent aliases are supplied.
