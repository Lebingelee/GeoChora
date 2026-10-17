# GeoChora P2.0-B S5-C3 — Minimal v1.1.0 Release Evidence Preservation

**Status: RELEASE_CANDIDATE — NOT_PUBLISHED**
**Current public develop last observed:** `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`
**Preservation policy decision:** pending maintainer approval.

## Evidence classes

- **Formal Qualification Evidence:** v1.1.0 makes no new formal Qualification
  decision. Historical v1.0.0 qualification labels and records remain bound to
  their immutable source and Evidence.
- **Bounded Functional Acceptance Evidence:** four selected manipulation
  task/provider CPU routes. They remain `TESTED_BOUNDED` and are summarized in
  the [evidence index](../../releases/v1.1/evidence/README.md) and candidate
  [capability matrix](capability_matrix_v1_1_0_candidate.json).
- **Historical Experiment Evidence:** older qualification campaigns,
  candidate branches, and exploratory runs. These remain untouched in the
  ignored workspace and are classified L3 for the proposed reduced off-host
  scope.
- **Raw H5/checkpoint artifacts:** the four full-route H5 files and a
  representative canonical recording H5 are L2. They remain local. Their
  hashes identify bytes but cannot restore missing files.
- **Release metadata and provenance:** current reports, identities, recovery
  refs, and capability claims are L1 Git files. They do not replace raw H5
  contents or create a qualification decision.

## Proposed L1/L2/L3 retention set

L1 consists of the three files under
[`docs/releases/v1.1/evidence/`](../../releases/v1.1/evidence/), this report,
and the existing capability/source-recovery records they reference. The L1
metadata is preserved in a local Git commit; it is not in public `develop`,
because no S5-C3 remote integration authorization was given.

L2 contains five H5 files totaling **24,301,972 bytes** and ten supporting
result/log files. The complete 15-file inventory, per-file byte sizes, and
SHA-256 values are in the [evidence index](../../releases/v1.1/evidence/README.md).
The combined listed L2 set is **24,390,405 bytes**. All listed files exist and
their current local hashes match the manifest; no transfer or restore was
attempted. Preserve every file in place.

L3 is the prior historical workspace, estimated at about 71 GB. The proposal
places L3 outside the mandatory v1.1.0 off-host preservation set only after
explicit maintainer approval and risk acceptance. L3 and frozen v1.0.0 records
were not deleted, rewritten, or copied. The earlier full-workspace estimate
and failed independent-destination observation remain in
[`backup_manifest.json`](../../releases/v1.1/backup_manifest.json).

## Scope-policy decision and separate statuses

The reduced policy is a proposal, not an adopted waiver. Until it is approved,
the prior full-workspace gate remains active and `BACKUP_NOT_VERIFIED` remains
the current gate result.

| Required status | Current observation |
| --- | --- |
| `RELEASE_METADATA_PRESERVED` | Local Git only; public remote integration has not been authorized or performed. |
| `RAW_EVIDENCE_BACKUP_NOT_VERIFIED` | L2 exists and is locally hash-checked; no independent copy or restore read. |
| `HISTORICAL_WORKSPACE_BACKUP_NOT_VERIFIED` | L3 remains on the single local disk; excluded from the proposed mandatory off-host set only if approved. |
| `MAINTAINER_RISK_ACCEPTANCE_REQUIRED` | Pending for unbacked L2/L3 and the known `/dev/sda`/`ata5` storage history. |

No full-backup PASS is claimed. A hash list is an integrity reference, not a
backup. The previous observation—one physical `/dev/sda`, no authorized
independent destination, no copy, and no restore verification—is preserved.

## Verification performed

- Re-read the canonical Evidence and Qualification governance documents,
  current release package, candidate matrix, source/recovery manifest, and
  S5-C1/S5-C2 reports.
- Verified the five H5 files against their recorded SHA-256 values and verified
  the listed result/log file sizes and hashes on the local disk.
- Confirmed the candidate matrix continues to label the four manipulation
  intersections `TESTED_BOUNDED` and `NOT_QUALIFIED_FOR_CURRENT_SOURCE`.
- Reused the S5-C2 provider-free receipt: 147 tests and 6 subtests passed on
  `2fb60de`; no new native task route or qualification campaign was run.
- Remote evidence-file verification is **NOT_RUN**. No remote integration
  authorization was provided.

## Decisions and blockers

1. Approve or reject the reduced L1/L2/L3 preservation policy. Until decided,
   the previous full-workspace gate remains active.
2. If approving the reduced policy, explicitly accept that L2 raw files and
   L3 historical data have no verified independent copy, and accept the known
   storage risk. This is not a backup PASS.
3. Separately authorize any normal fast-forward integration of the L1 files.
   After authorization, verify public ancestry, remote file contents/hashes,
   absence of accidental binaries/secrets, and read back the exact SHA.
4. Resolve the existing controller Option B acceptance, capability-matrix
   approval, fresh-install/full-relocation scope, and final publication
   authorization as listed in the release readiness table.

The target remains v1.1.0 under the project-specific version policy. No tag,
main change, GitHub Release, or new qualification is created by this work.
