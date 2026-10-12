# Evidence cleanup report

Infrastructure gate: REPLAY_INFRASTRUCTURE_GO before deletion. Explicit manifest precheck passed; deletion completed.

- Deleted files: 559.
- Last-link allocated bytes released: 32590393344.
- Measured filesystem free-space increase at unlink: 32590274560 bytes (32.590 GB decimal).
- Archive original logical bytes: 27011368180.
- Archive remaining logical bytes: 10989626950.
- Cold-compressed reports: 39; expanded SHA256 verified before deletion.

The measured release includes verified duplicate historical worktree copies as well as archive files. It is not solely archive shrinkage. Compression consumes separate storage; the unlink measurement does not claim an off-host backup.

Lossy scope: nonselected historical dense trajectories, inner-step streams and optional/derived wrist videos listed individually in evidence_cleanup_manifest.json. Deleted detail cannot be recovered from checksums. Source bundles, patches, source assets, selected experiment references, representative failure evidence, current six-cell +1mm baselines, all current live H5 trajectories and native checkpoint sidecars were preserved. Historical failure conclusions were not changed.

Archive is local-only: /home/lly/Geochora_Evidence_Archive/p1_8_integration_20261012. No off-host backup verified. The original file_manifest/complete marker describes the historical full archive; minimal_reproducibility_complete.json supersedes its retention scope after pruning.


## Storage accounting details

- Selected ten experiment evidence references (unique path union, logical bytes): 2630153728 bytes (2.630 GB). This includes shared phase evidence and is not ten disjoint per-experiment totals.
- Current replay closure Evidence in the worktree, including H5 trajectories, native sidecars, logs and reports: 4069079038 bytes (4.069 GB).
- Archived R5 evidence subtree remaining after pruning: 2143649649 logical bytes (selected and protected R5 evidence; includes broader evidence than the selected experiment alone).
- Retained source submodule snapshots: 1954211840 bytes (1.954 GB; GeoPhys and Menagerie source tar files).
- Lossless cold reports: 39 files, 2937880998 original bytes to 272781821 compressed bytes; source hashes of expanded files verified before replacing.
- Verified duplicate-path logical bytes removed (identical copies and matched worktree duplicates): 16282769518 bytes.
- Remaining archive total: 10989626950 logical bytes / 10997338112 allocated bytes.
- Archive source and retained evidence remain on the same host. There is no verified off-host copy.


## Exact historical detail discarded

| Removed category | File count | Historical capability no longer available |
|---|---:|---|
| Superseded dense trace / inner-step streams | 170 | Cannot replot every old nonselected boundary/contact sample or reassess an unrecorded transient from those raw streams. Selected experiments remain rerunnable from pinned source/config/dependencies; their deleted raw realization is not byte-reconstructable. |
| Optional or derived historical videos | 226 | No frame-level reinspection of those nonselected runs; representative videos for protected/selected evidence remain. |
| Losslessly cold-compressed JSON reports | 78 original and duplicate-path entries | No information loss; the exact expanded content hash was verified. |
| SHA-identical redundant regression copy | 3 | No unique content lost; retained identical source was checked. |

The evidence manifest lists every path, original size/hash and reason. Hashes document identity but cannot recover deleted bytes. Old source/configuration and compact outcomes remain available for all ten selected experiments. The cleanup does not claim byte-for-byte reconstruction of unselected historical runs.
