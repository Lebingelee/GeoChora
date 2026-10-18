# v1.1.0 Release Readiness Gates

**Review snapshot: 2026-10-18 — RELEASE_CANDIDATE at the refs recorded below**

This is a dated pre-publication gate review, not a live release-status signal.
Use fresh public ref readback to determine whether later integration or
publication has occurred.

Public `develop` now includes the reviewed S5-C1–C8 documentation chain through
`c679267790726d3e34d080a133535c2c308a7a55`; its normal fast-forward and exact
remote readback completed on 2026-10-18. Public `main` and the immutable
`v1.0.0` tag were not changed. The maintainer accepted Controller Identity
Option B, the current capability matrix within its existing `TESTED_BOUNDED`
limits, the breaking API migration disclosure, the fresh-install and
relocated-regression `NOT_RUN` limitations, and the recorded C8 residuals.
The maintainer has authorized an exact L2 copy to the public GitHub
`v1.1.0` candidate branch, including source files that contain embedded local
absolute paths. The payload commit is
`745efc6a6693a7d10407c6ddd02837a2ae574131`; its 22 blob hashes match. A
representative H5 and result JSON read passed. The branch subsequently advanced
with backup-status receipts; latest public readback on 2026-10-18 is
`v1.1.0=e0e861998711f7ec5e1f10784ca857dc39d7d575`, which retains the payload
commit. The user authorized this L2-only copy (under 100 MB) and approved the
embedded local-path strings. It does not cover the historical full-workspace
bundle or publish the release. On
2026-10-18 the maintainer authorized all four exact C8 batches and accepted
C1/C2 loss.
Assistant deletion stopped before unlinking when the SCSI counter rose; later
repeatable SMART-refresh observations support treating counter-only growth as
an investigation signal, not proof of a new read/write failure. The
maintainer subsequently handled ordinary files manually without per-file
unlink logs. All 65,826 ordinary candidate paths are now absent, while the
registered worktree and all 522 holdouts remain. See [the final C8
report](c8_manual_cleanup_final_report.md), [the storage-monitoring
revision](c8_storage_monitoring_revision.md), and the dated [execution-stop
report](c8_execution_and_phase2_closure.md).

A later documentation-only reconciliation of current refs and L2 backup
status is present on the local release-candidate branch and has not been
integrated remotely. The remote `develop` and `v1.1.0` refs remain the exact
SHAs stated above; the local candidate should be reviewed as a separate delta.

| Gate | Status | Evidence / remaining condition |
| --- | --- | --- |
| Functional integration | **PASS** | Normal fast-forward from `0ff2d846` to `bee498d1d784015f034c5b4af34320fdffa61411`; public readback matched. |
| Release-document integration | **PASS** | Normal fast-forward from `2fb60de7851bf2e5651c2dc99fff7451c16e1a94` to `c679267790726d3e34d080a133535c2c308a7a55`; exact public readback matched. |
| Protected refs and ancestry | **PASS** | Public `main` is `e4e39883fbe01d4be4b172a53a535ef0095b3d64`; annotated v1.0.0 tag object `17c3100d4fabcb061c23569dea49973ebd177d51`, peeled commit `42787f5e4f658a3f81fdd2140cf7544d6342c783`; all unchanged after both integrations. |
| Source identity / selected task closure | **PASS — LOCAL CHECK** | Selected task, controller, runtime, provider, and object-owner sources did not change in `bee..2fb`; exact task identities remain listed in the candidate matrix. |
| Bounded functional regression | **PASS — TESTED_BOUNDED** | S5-C2 rerun at `2fb60de`, Python 3.12.14: 147 passed, 6 subtests passed, one upstream warning, 160.07 s. No new native route was run. |
| API migration disclosure | **MAINTAINER_ACCEPTED — DISCLOSURE COMPLETE** | The maintainer accepted the documented breaking task UID, imports, runtime options, and CLI changes under the project-specific v1.1.0 policy. |
| Controller identity decision | **MAINTAINER_ACCEPTED — OPTION B** | Retain the current path-sensitive controller identity. Cross-checkout equality is not guaranteed; no relocated native rollout is claimed. Historical identities and H5 hashes remain unchanged. |
| Existing-environment detached checkout | **PASS — BOUNDED** | Exact Gitlinks and construct/reset/close smokes for both tasks/providers; no full route. |
| Fresh Python dependency installation | **NOT_RUN — LIMITATION ACCEPTED** | Existing Python 3.12.14 environment used. No clean dependency-install or packaging claim is made. |
| Full relocated-checkout regression | **NOT_RUN — LIMITATION ACCEPTED** | Prior exploration was 139 PASS / 8 FAIL; test-helper and path issues were analyzed, but the full suite was not rerun. No relocated full-route pass is claimed. |
| Submodule/source recovery | **PASS — LOCAL CHECK ONLY** | Required Gitlinks are present; 94/94 retired blobs, 10/10 migrated blobs, and 8/8 enumerated H5/checkpoint hashes matched. No independent restore was performed. |
| v1.1.0 capability matrix approval | **MAINTAINER_ACCEPTED — BOUNDED CLAIMS ONLY** | The current candidate matrix is approved in principle; four manipulation/provider intersections remain `TESTED_BOUNDED`, not newly qualified. |
| Historical L3 retention | **MAINTAINER_ACCEPTED — RETIREMENT WITH RECORDED EXCEPTIONS** | C8 retirement and residual loss are accepted as recorded. Missing historical raw data has not been restored. |
| Release metadata preservation | **PASS — PUBLIC_GIT** | All 91 L1 entries are tracked in the integrated source. Fourteen differ from the older C8 snapshot after documented updates; each older exact blob is recoverable from Git history. The 37 exact historical records and original bytes remain available. |
| Current release-document reconciliation | **PASS — LOCAL CANDIDATE ONLY** | The current-ref, L2 status, retention, and retrospective edits are committed on the local release-candidate branch. They are not yet in public Git; publishing this delta requires explicit remote-integration authorization. |
| Current TaskEnv raw evidence | **PASS — L2_LOCAL_AND_REMOTE_HASH_VERIFIED** | 22 selected files, 24,563,669 bytes, including six H5 files and bounded SB3/batch raw receipts; local and remote sizes/hashes match. |
| Raw evidence backup | **PASS — SCOPED L2 REMOTE COPY** | Public `v1.1.0` branch `745efc6a6693a7d10407c6ddd02837a2ae574131` contains 22/22 files with matching sizes/SHA-256; a NutAssembly H5 opened and a PickCube result JSON parsed from fetched remote Git objects. Twelve originals contain approved local path strings. The copy is off-host but in the same GitHub repository/account; it is not the full-workspace or separately administered backup. |
| Proposed backup-scope exception | **MAINTAINER_DECISION_REQUIRED — NOT ACCEPTED** | Proposal: keep L1 and all 22 L2 bytes, accept the verified GitHub copy against local-disk loss, and waive only a second separately administered L2 destination/full-workspace bundle. Accept the same-repository/account common-mode risk, open SATA/BadCRC risk, and accepted C8 L3 loss. See [the exact proposal](publication_procedure_draft.md). |
| Historical workspace backup | **NOT_VERIFIED — HISTORICAL LOSS ACCEPTED** | 65,826 approved ordinary paths are absent after maintainer manual handling; exact independent recovery is not verified and historical raw/source bytes may be permanently lost. Workspace allocation observed 2,815,557,632 bytes after cleanup, down 68.317 GiB from the recorded baseline. This is aggregate observation, not exact unlink-attributable recovery. The v1.0.0 P1.6 recovery archive remains unresolved. This is a disclosed accepted retention risk, not a backup PASS. |
| Scoped retention policy and residual-risk acceptance | **MAINTAINER_ACCEPTED — C8 SCOPE ONLY** | L1/L2 preservation and exact A/B/C1/C2 retirement authorized on 2026-10-18, including C1/C2 permanent historical loss. The current L2 GitHub copy is recorded separately; it does not restore retired L3 data. |
| Approved C8 execution | **C8_CLOSURE_ACCEPTED_WITH_EXCEPTIONS** | All 65,826 approved ordinary paths are absent; no user per-file unlink receipts exist. B worktree remains held (6,619 entries); all 522 pre-existing holdouts remain. Assistant deletion stayed storage-latched. Maintainer explicitly accepted retained worktree/holds and missing per-file operator logs for final C8 closure. |
| P1.8 archive retirement | **PARTIAL — 3,382 PATHS ABSENT** | The held source bundle remains. C1 permanent-loss acceptance is recorded; raw trajectories/source carriers at the retired paths are no longer locally available there. Hashes do not restore them. |
| Remote evidence preservation | **PASS — PUBLIC L1 BASELINE AND L2 COPY** | The integrated L1 baseline is on public `develop` at `c679267`; latest release-document reconciliation remains local. The L2 payload commit `745efc6a` is retained on public `v1.1.0`, whose latest readback is `e0e8619`. Readback hashes and representative H5/JSON reads passed. |
| Storage monitoring | **OPEN_RISK — HISTORICAL SATA ISSUE** | Counter-only growth is an investigation signal after the repeated SMART-refresh correlation. Stop on actual I/O failure, new ATA/block/filesystem errors, CRC/bad-sector growth or integrity anomalies. The exact L2 copy is remotely verified; the historical SATA risk remains OPEN. |
| Publication authorization | **NOT AUTHORIZED IN THIS INSTRUCTION** | No v1.1.0 tag, `main` change, or GitHub Release is authorized or created; a separate final Publication GO is required. |
| L3 retention and cleanup review | **PARTIAL; RESIDUAL HOLDS PRESERVED** | Ordinary paths handled manually; 522 holdouts and the registered worktree remain. No force/deinit/manual worktree fallback was attempted. |

The S5-C1/S5-C2 reports, proposed S5-C3 evidence package, and its review report are linked from the
[release package](README.md). C8 supersedes the earlier cleanup-candidate snapshot with exact local
manifests while preserving the S5-C5/C6 inventories as historical records. The
[C8 preflight report](evidence/retirement/c8_retention_and_cleanup_preflight.md)
records the manifest hashes and approval boundary. The [backup manifest](backup_manifest.json)
retains the historical full-scope blocked observation and tracks the newly
authorized scoped L2 copy separately. The exact retirement scopes are approved. [The manual post-observation receipt](evidence/retirement/c8_manual_cleanup_observation_20261018.json) supersedes current cleanup status; the earlier execution-stop receipt remains historical. Post-cleanup current-source checks passed 9 tests (7 in 1.51 s; 2 in 0.81 s), with no native rerun. Recent fixed counter increments have a reproducible maintainer-reported SMART explanation. Counter-only growth is an investigation signal, not proof of new read/write failure. Bounded low-I/O work may continue under [revised criteria](c8_storage_monitoring_revision.md); historical SATA risk remains open. No additional deletion or high-load execution is authorized by this correction.

## C8 final closure acceptance

On 2026-10-18 the maintainer explicitly accepted the retained B worktree/holdouts and the absence of per-file operator deletion logs, using verified path absence, protected hashes and aggregate space observations to close C8. This closes the maintenance Goal under disclosed exceptions; it grants no publication authorization. See the [original-goal audit and exact acceptance](c8_goal_completion_audit.md). Publication remains BLOCKED.

## Final v1.1.0 Go/No-Go review

This is the current decision snapshot for the v1.1.0 release candidate. The
release version is already selected; it is a Core consolidation release with
documented breaking API changes under GeoChora's project-specific policy.
The reviewed source and L1 release metadata are present on public `develop` at
`c679267`; the separate `v1.1.0` branch is being used only for the authorized
L2 evidence copy. Neither branch integration nor evidence backup publishes the
release.

| Decision | Review result | Required maintainer action before publication |
| --- | --- | --- |
| A. Controller identity portability | **ACCEPTED — OPTION B** | Retain the path-sensitive identity. Cross-checkout hash equality is not guaranteed. Preserve current identities and historical H5 hashes. No relocated full native rollout was run. |
| B. Capability matrix | **ACCEPTED — EXISTING TESTED_BOUNDED ONLY** | The current candidate matrix is approved in principle; it grants no new formal qualification. |
| C. API migration disclosure | **ACCEPTED** | The documented breaking task UID, Python import, runtime configuration, and CLI removals are accepted under the v1.1.0 project policy. |
| D. Fresh-install validation | **NOT_RUN — LIMITATION ACCEPTED** | The source-checkout/Python 3.12.14 validation scope is accepted; no fresh installation or packaging claim is made. |
| E. Full relocated-checkout regression | **NOT_RUN — LIMITATION ACCEPTED** | Preserve the exploratory 139 PASS / 8 FAIL result and its explained path/test-helper causes; no full rerun or relocated native rollout is claimed. |
| F. L1 remote preservation | **PASS — PUBLIC GIT** | Candidate `c679267` is present on public `develop`; remote SHA readback matched, and protected refs are unchanged. |
| G. L2 integrity and backup | **PASS — SCOPED REMOTE COPY; FULL BACKUP NOT VERIFIED** | All 22 local originals, branch copies, and fetched remote Git blobs match (24,563,669 bytes). A representative NutAssembly H5 opened and a PickCube result JSON parsed from fetched objects. Payload commit `745efc6a` is retained on the current public branch HEAD `e0e8619`. The same-repository copy is off-host but not separately administered; the full-workspace bundle remains unverified. |
| H. Historical L3 retirement | **C8_CLOSURE_ACCEPTED_WITH_EXCEPTIONS** | The exact C8 loss is accepted while the registered worktree and all 522 holdouts remain. Unknown/external consumers remain a disclosed limit; no further deletion is authorized. |
| I. `/dev/sda` storage risk | **OPEN — BACKUP WORK AUTHORIZED** | The maintainer directed that the L2 backup proceed despite the warning. Counter-only `ioerr_cnt` growth is an investigation signal; actual I/O failures, new storage errors, integrity failures, or CRC/bad-sector growth remain stop conditions. |
| J. Publication and repository changes | **NOT AUTHORIZED IN THIS INSTRUCTION** | The maintainer separately authorized the `v1.1.0` branch for this exact L2 backup only. `main`, release tag, GitHub Release, and further cleanup remain subject to separate explicit approval. |

### Authorized scoped L2 copy

The maintainer authorized an exact 22-file L2 copy (24,563,669 bytes) on the
public GitHub `v1.1.0` branch, within the 100 MB limit. The original local
files remain unchanged. Remote readback verified 22/22 blob sizes and SHA-256;
a representative NutAssembly H5 opened and a PickCube result JSON parsed from
fetched Git objects. This verifies off-host preservation of the selected L2
bytes; it does not create a separately administered backup, a full
workspace/source bundle, or copies of all submodule objects. The historical
full-scope backup observation remains `BACKUP_NOT_VERIFIED`; C8 acceptance does
not reconstruct deleted historical raw data. No release publication is
authorized by this backup approval.

At this review snapshot the release remains **RELEASE_CANDIDATE —
NOT_PUBLISHED**. Later publication status must be determined from fresh remote
ref readback, not inferred from this dated report.

## Final review checks on the local candidate

- **PASS:** public ref readback after integration is
  `develop=c679267790726d3e34d080a133535c2c308a7a55`,
  `main=e4e39883fbe01d4be4b172a53a535ef0095b3d64`, annotated `v1.0.0` tag
  object `17c3100d4fabcb061c23569dea49973ebd177d51` peeling to
  `42787f5e4f658a3f81fdd2140cf7544d6342c783`. At the time of this update,
  `v1.1.0` payload commit is `745efc6a6693a7d10407c6ddd02837a2ae574131` and
  the latest branch HEAD readback is `e0e861998711f7ec5e1f10784ca857dc39d7d575`;
  no release tag or GitHub Release has been created. The candidate is a descendant of `main`,
  `develop`, and the frozen release commit.
- **PASS:** the release package's JSON files parse; all 91 current L1 paths
  are tracked and present; 126 local Markdown links resolved in the prior
  check. Fourteen current L1 documents differ from the older C8 hash snapshot;
  the exact older blobs remain in Git history. The L2 raw payload contains no
  detected credentials, private keys, or password-like strings; twelve files
  contain local absolute paths, whose public inclusion the maintainer approved.
- **PASS — SCOPED REMOTE COPY:** all 22 L2 source/copy/remote blobs match their
  recorded sizes and SHA-256 values (24,563,669 bytes; six H5 files). A
  representative H5 and result JSON were read from fetched remote Git objects.
- **PASS — EXISTING CODE RECEIPTS:** the 147-test/6-subtest S5-C2 provider-free
  run at `2fb60de` and the nine post-C8 provider-free checks on the unchanged
  selected source are recorded in the linked reports. The exact converter
  `--help` forwarding regression was independently rerun here: 1 passed,
  8 deselected in 0.51 s. No expensive native task route was repeated because
  selected task execution sources are unchanged.
- **PRESERVED HISTORICAL FORMAT EXCEPTION:** `git diff --check` reports one
  blank line at EOF in the P1.8 `materialization_report.md` copy. Its SHA-256
  still matches the byte-identical copy index, so the historical record was
  not normalized. The newly edited release files have no trailing whitespace.
- **PASS — SCOPE:** integrated `develop` through `c679267` changes only
  documentation/governance; selected task/provider/runtime sources and
  Gitlinks are unchanged. The separate local `v1.1.0` backup branch contains
  the exact 22-file L2 payload and verified remote-readback metadata.
