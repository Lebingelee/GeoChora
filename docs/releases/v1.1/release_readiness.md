# v1.1.0 Release Readiness Gates

**Review snapshot: 2026-10-18 — RELEASE_CANDIDATE at the refs recorded below**

This is a dated pre-publication gate review, not a live release-status signal.
Use fresh public ref readback to determine whether later integration or
publication has occurred.

Public `develop` includes the S4.5 functional unit, converter fix, and S5-B
candidate documents through `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`.
The local S5-C1 through S5-C8 review chain is being prepared for a normal
fast-forward. The maintainer has accepted Controller Identity Option B, the
current capability matrix within its existing `TESTED_BOUNDED` limits, the
breaking API migration disclosure, the fresh-install and relocated-regression
`NOT_RUN` limitations, and the recorded C8 residuals. A pre-push consistency
check found that this document still contained the earlier pending-decision
wording; the authorized commit `501c5e55e290870d8ac712ef82c7c33f6956c011`
therefore has not been pushed. This local update records the accepted
decisions; its resulting commit requires a fresh exact-SHA integration review.
Publication remains **BLOCKED** by the unverified independent L2 backup. The
maintainer requested that the L2 backup proceed despite the historical disk
warning; no independent destination is currently mounted. On 2026-10-18 the
maintainer authorized all four exact C8 batches and accepted C1/C2 loss.
Assistant deletion stopped before unlinking when the SCSI counter rose; later
repeatable SMART-refresh observations support treating counter-only growth as
an investigation signal, not proof of a new read/write failure. The
maintainer subsequently handled ordinary files manually without per-file
unlink logs. All 65,826 ordinary candidate paths are now absent, while the
registered worktree and all 522 holdouts remain. See [the final C8
report](c8_manual_cleanup_final_report.md), [the storage-monitoring
revision](c8_storage_monitoring_revision.md), and the dated [execution-stop
report](c8_execution_and_phase2_closure.md).

| Gate | Status | Evidence / remaining condition |
| --- | --- | --- |
| Functional integration | **PASS** | Normal fast-forward from `0ff2d846` to `bee498d1d784015f034c5b4af34320fdffa61411`; public readback matched. |
| Release-document integration | **PASS** | Normal fast-forward from `bee498d1` to `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`; public readback matched. S5-C1 documentation commit `2f8555a4c86470fb63cd2386a6e88729d4795a23` and S5-C2 report updates remain local. |
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
| Historical L3 retention | **MAINTAINER_ACCEPTED — RETIREMENT WITH RECORDED EXCEPTIONS** | C8 retirement and residual loss are accepted as recorded. This does not claim an archive backup and does not substitute for preserving or independently backing up L2. |
| Release metadata preservation | **PASS — LOCAL_GIT_ONLY** | All 91 entries in the post-C8 L1 manifest are present and tracked. Fourteen files have later versioned documentation updates; each previous SHA is recoverable from Git history. The 37 exact historical records and original bytes remain available. Remote preservation awaits the corrected candidate integration. |
| Current TaskEnv raw evidence | **PASS — L2_RAW_EVIDENCE_LOCALLY_VERIFIED** | 22 selected files, 24,563,669 bytes, including six H5 files and bounded SB3/batch raw receipts; local sizes/hashes are verified. This is not an independent backup. |
| Raw evidence backup | **BLOCKED — L2_INDEPENDENT_BACKUP_NOT_VERIFIED** | No independent copy or restore read exists; hashes cannot restore missing files. The exact L2 list is in [the evidence index](evidence/README.md). |
| Historical workspace backup | **NOT_VERIFIED — HISTORICAL LOSS ACCEPTED** | 65,826 approved ordinary paths are absent after maintainer manual handling; exact independent recovery is not verified and historical raw/source bytes may be permanently lost. Workspace allocation observed 2,815,557,632 bytes after cleanup, down 68.317 GiB from the recorded baseline. This is aggregate observation, not exact unlink-attributable recovery. The v1.0.0 P1.6 recovery archive remains unresolved. This is a disclosed accepted retention risk, not a backup PASS. |
| Scoped retention policy and residual-risk acceptance | **MAINTAINER_ACCEPTED — C8 SCOPE ONLY** | L1/L2 preservation and exact A/B/C1/C2 retirement authorized on 2026-10-18, including C1/C2 permanent historical loss. C8 acceptance does not waive the independent L2 backup gate. |
| Approved C8 execution | **C8_CLOSURE_ACCEPTED_WITH_EXCEPTIONS** | All 65,826 approved ordinary paths are absent; no user per-file unlink receipts exist. B worktree remains held (6,619 entries); all 522 pre-existing holdouts remain. Assistant deletion stayed storage-latched. Maintainer explicitly accepted retained worktree/holds and missing per-file operator logs for final C8 closure. |
| P1.8 archive retirement | **PARTIAL — 3,382 PATHS ABSENT** | The held source bundle remains. C1 permanent-loss acceptance is recorded; raw trajectories/source carriers at the retired paths are no longer locally available there. Hashes do not restore them. |
| Remote evidence preservation | **BLOCKED — PRE-PUSH DOCUMENT CONSISTENCY** | The authorized `501c5e5` candidate still states several now-accepted decisions as pending. This local correction is a new commit; do not push it until the exact resulting SHA is reviewed and authorized. |
| Storage monitoring | **OPEN_RISK — BOUNDED BACKUP MAY PROCEED** | Counter-only growth is an investigation signal after the repeated SMART-refresh correlation. Stop on actual I/O failure, new ATA/block/filesystem errors, CRC/bad-sector growth or integrity anomalies. Historic SATA risk remains OPEN; the requested L2 copy still requires an independent destination. |
| Publication authorization | **NOT AUTHORIZED IN THIS INSTRUCTION** | No v1.1.0 tag, `main` change, or GitHub Release is authorized or created; a separate final Publication GO is required. |
| L3 retention and cleanup review | **PARTIAL; RESIDUAL HOLDS PRESERVED** | Ordinary paths handled manually; 522 holdouts and the registered worktree remain. No force/deinit/manual worktree fallback was attempted. |

The S5-C1/S5-C2 reports, proposed S5-C3 evidence package, and its review report are linked from the
[release package](README.md). C8 supersedes the earlier cleanup-candidate snapshot with exact local
manifests while preserving the S5-C5/C6 inventories as historical records. The
[C8 preflight report](evidence/retirement/c8_retention_and_cleanup_preflight.md)
records the manifest hashes and approval boundary. The [backup manifest](backup_manifest.json)
retains the previous blocked result. The exact retirement scopes are approved. [The manual post-observation receipt](evidence/retirement/c8_manual_cleanup_observation_20261018.json) supersedes current cleanup status; the earlier execution-stop receipt remains historical. Backup gates remain unwaived. Post-cleanup current-source checks passed 9 tests (7 in 1.51 s; 2 in 0.81 s), with no native rerun. Recent fixed counter increments have a reproducible maintainer-reported SMART explanation. Counter-only growth is an investigation signal, not proof of new read/write failure. Bounded low-I/O work may continue under [revised criteria](c8_storage_monitoring_revision.md); historical SATA and backup risks remain open. No additional deletion or high-load execution is authorized by this correction.

## C8 final closure acceptance

On 2026-10-18 the maintainer explicitly accepted the retained B worktree/holdouts and the absence of per-file operator deletion logs, using verified path absence, protected hashes and aggregate space observations to close C8. This closes the maintenance Goal under disclosed exceptions; it grants no backup waiver, remote integration or publication authorization. See the [original-goal audit and exact acceptance](c8_goal_completion_audit.md). Publication remains BLOCKED.

## Final v1.1.0 Go/No-Go review

This is the current decision snapshot for the v1.1.0 release candidate. The
release version is already selected; it is a Core consolidation release with
documented breaking API changes under GeoChora's project-specific policy.
Current source and L1 release metadata are local to this review branch and
must be integrated before release publication.

| Decision | Review result | Required maintainer action before publication |
| --- | --- | --- |
| A. Controller identity portability | **ACCEPTED — OPTION B** | Retain the path-sensitive identity. Cross-checkout hash equality is not guaranteed. Preserve current identities and historical H5 hashes. No relocated full native rollout was run. |
| B. Capability matrix | **ACCEPTED — EXISTING TESTED_BOUNDED ONLY** | The current candidate matrix is approved in principle; it grants no new formal qualification. |
| C. API migration disclosure | **ACCEPTED** | The documented breaking task UID, Python import, runtime configuration, and CLI removals are accepted under the v1.1.0 project policy. |
| D. Fresh-install validation | **NOT_RUN — LIMITATION ACCEPTED** | The source-checkout/Python 3.12.14 validation scope is accepted; no fresh installation or packaging claim is made. |
| E. Full relocated-checkout regression | **NOT_RUN — LIMITATION ACCEPTED** | Preserve the exploratory 139 PASS / 8 FAIL result and its explained path/test-helper causes; no full rerun or relocated native rollout is claimed. |
| F. L1 remote preservation | **NOT_RUN — LOCAL_GIT_ONLY** | The previously authorized candidate was stopped before push due to stale decision wording. The corrected candidate requires exact-SHA integration review and remote hash readback. |
| G. L2 integrity and backup | **L2_RAW_EVIDENCE_LOCALLY_VERIFIED; INDEPENDENT_BACKUP_BLOCKED** | All 22 local files match. No separate destination is mounted; do not mark backup `PASS` or treat hashes as restore capability. |
| H. Historical L3 retirement | **C8_CLOSURE_ACCEPTED_WITH_EXCEPTIONS** | The exact C8 loss is accepted while the registered worktree and all 522 holdouts remain. Unknown/external consumers remain a disclosed limit; no further deletion is authorized. |
| I. `/dev/sda` storage risk | **OPEN — BACKUP WORK AUTHORIZED** | The maintainer directed that the L2 backup proceed despite the warning. Counter-only `ioerr_cnt` growth is an investigation signal; actual I/O failures, new storage errors, integrity failures, or CRC/bad-sector growth remain stop conditions. |
| J. Publication and repository changes | **NOT AUTHORIZED IN THIS INSTRUCTION** | This instruction authorizes only the reviewed develop integration. `main`, v1.1.0 branch/tag, GitHub Release, and cleanup remain subject to separate explicit approval. |

### Specific backup-policy exception proposed — not approved

The current maintainer direction is to create and verify an independent copy
of all 22 L2 files (24,563,669 bytes) before publication. No independent disk
or network target is mounted in the current environment, so the gate remains
**BLOCKED**. No backup waiver has been requested or granted. If no authorized
independent destination can be provided, publication remains blocked unless a
separate explicit maintainer decision approves a narrowly scoped exception.
Any exception must preserve L1 in Git, retain all L2 bytes locally, disclose
`L2_INDEPENDENT_BACKUP_NOT_VERIFIED` and `STORAGE_HEALTH_RISK_OPEN`, and must
not claim that hashes restore missing raw data. C8's L3 loss acceptance does
not satisfy or waive the L2 backup gate.

At this review snapshot the release remains **RELEASE_CANDIDATE —
NOT_PUBLISHED**. Later publication status must be determined from fresh remote
ref readback, not inferred from this dated report.

## Final review checks on the local candidate

- **PASS:** current public ref readback still matches the recorded pre-release
  base: `main=e4e39883fbe01d4be4b172a53a535ef0095b3d64`,
  `develop=2fb60de7851bf2e5651c2dc99fff7451c16e1a94`, annotated `v1.0.0` tag
  object `17c3100d4fabcb061c23569dea49973ebd177d51` peeling to
  `42787f5e4f658a3f81fdd2140cf7544d6342c783`; no remote `v1.1.0` branch/tag
  was observed at review start. The candidate is a descendant of `main`,
  `develop`, and the frozen release commit.
- **PASS:** the release package's 40 JSON files parse; all 40 paths in the
  current L1 release inventory are tracked and present; 126 local Markdown
  links resolve. The changed-file scan found no credential patterns or
  host-local absolute paths.
- **PASS — LOCAL INTEGRITY ONLY:** all 22 L2 paths match their recorded sizes
  and SHA-256 values (24,563,669 bytes; six H5 files). No independent copy or
  restore read is implied.
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
- **PASS — SCOPE:** current local changes are documentation/governance only;
  selected task/provider/runtime sources and Gitlinks are unchanged. No
  release binary or H5 file was added to Git.
