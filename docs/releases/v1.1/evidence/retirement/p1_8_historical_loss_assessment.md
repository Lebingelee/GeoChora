# P1.8 historical loss assessment — retirement proposal

**Status:** `RELEASE_CANDIDATE — NOT_PUBLISHED`; proposal only.
**No deletion has been authorized or performed.**
**Target:** local P1.8 integration archive under `workspace/qualification/phase1/archives/p2_0_part_a/legacy_evidence_archive/p1_8_integration_20261012/`.

## Historical and live inventories

The original archive file manifest contains 3,576 records and has SHA-256 `0eb01f44b3b3409b11c4874e5bccc06c56d35af4104e21448a5f46819532f943`. The current no-follow live snapshot contains 3,383 regular files: 10,989,629,850 logical bytes and 10,997,342,208 path-allocated bytes. All 3,298 common entries match the original manifest's size and SHA-256. The original manifest has 278 entries absent from the live archive (16,294,516,785 recorded logical bytes); 85 live entries are not in that manifest. These are retained as separate inventories. No absent entry is reconstructed or treated as a deletion target.

C8 hashed each of the 3,383 live files once using bounded streaming; all lstat identities still matched the C5 snapshot. The archive contains no symlinks or hardlinked files. The protected L1/L2 path and inode intersection is zero. The C8 candidate allows 3,382 files (10,978,766,848 allocated bytes) for maintainer review and holds `p1_8_source.bundle` pending the recovery-reference issue below. The manifest is exact-file based; the archive directory itself is never an executable deletion target.

## Historical decisions and retained metadata

A Git-tracked package at `docs/releases/v1.1/evidence/historical_retirement/` preserves 37 byte-identical original decision/provenance records (366,744 original bytes), including the recorded acceptance, partial, diagnostic, and failure context. The package does not rewrite or promote the original results. No completed P1.8 formal FULL qualification or completed Human/Judge approval was found. Frozen v1.0.0 decisions and reports remain unchanged.

The original 1,752,569-byte `file_manifest.json` has SHA-256 `0eb01f44b3b3409b11c4874e5bccc06c56d35af4104e21448a5f46819532f943`. Its exact bytes were copied outside the target to the ignored C8 preservation directory and verified; the copy is on the same `/dev/sda` device and is not an independent backup. Other small live-only private-path records are likewise held locally where listed in the copy receipts. They were not published into Git.

## Source carriers and recovery limits

| Carrier | Size | SHA-256 | Current recovery assessment |
|---|---:|---|---|
| `source_snapshots/geophys-c665ce5028a12bb4d2afe49f05e015fa9b684a39.tar` | 49,971,200 | `21aeab5c1d3c80033860105e8653b95530ad4c19b70f42b8a3a884a70c914e89` | GeoPhys commit `c665ce5028a12bb4d2afe49f05e015fa9b684a39` remains the current public Gitlink and its source/object closure is present locally. The exact tar serialization will not be recoverable from the Gitlink. |
| `geophys_source.bundle` | 12,139,954 | `2285308e07c61b597a4284b3bc54fe4f9747431fe85bf43fab1b6b0f0067eb5b` | The current GeoPhys repository and public Gitlink contain the selected source tree. The frozen v1.0.0 archive record described a missing historical parent during bundle reconstruction; that historical limitation is not rewritten. Exact original bundle bytes are not guaranteed reproducible. |
| `source_snapshots/menagerie-b846dd12bc459d776cccb3dee0b1d02acbf7a9c7.tar` | 1,904,240,640 | `2b9a17be324b1518181d2be26c5302c89bf3abc3fa20d5bb9d623934435004ba` | Menagerie commit `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` remains the current Gitlink and its source assets are present. The exact tar serialization is not recoverable from a Gitlink. |
| `menagerie_source.bundle` | 604,164,075 | `3c9f399e5848c904e8f37dee85efcb07a766e1d8b9bcbdfc01ce13db728107df` | Current Menagerie object set corresponds to the selected Gitlink; exact bundle serialization is not guaranteed reproducible. |
| `integration_final_source.bundle` | 1,999,101 | `bc2f3f234bcf62a1ec6ca8d232c875d52536835a463a1adb60d917718d9c5f8f` | Root repository source objects are available; exact archive bundle bytes are not retained elsewhere. |
| `integration_report_staging.bundle` | 19,292,050 | `7dc1aae163d08e47cd9f6e01fd14b63006cfc597749bcb43ef7527ed5f8d52e2` | Root repository source objects are available; exact archive bundle bytes are not retained elsewhere. |
| `integration_source.bundle` | 1,995,357 | `5f414f2e3642a689aa68c12d46d6e10ec5762c9563c3e1aea7bda7846d00a720` | Root repository source objects are available; exact archive bundle bytes are not retained elsewhere. |
| `p1_8_source.bundle` | 18,571,359 | `e6c6067ada628c2207017051a510f921ac6bac57f903abe0ac2e13507efa0737` | `git bundle verify` succeeds; all 7,610 packed objects are currently present in the root object database. Of those, 7,592 are reachable from current local refs; 18 objects (all trees) are not, including the six direct tree-ref targets. The bundle names 66 commit refs and 6 tree refs; 29 of 72 exact ref name+OID pairs match local refs, and none match a current public ref. Keep this bundle as a C1 hold until the six tree refs and their 18-tree closure are pinned or separately preserved. The tracked compact reachability summary is beside this report; the full local ref mapping remains in ignored C8 output. |

The 796 paths previously described as GeoPhys snapshots are not 796 source archives: only the GeoPhys tar and bundle above are actual source carriers. Other GeoPhys-named files are experiment/diagnostic outputs. For the C1 allowlist, exact raw experiment/report bytes and the exact original bundle/tar serializations may become permanently unavailable. Hashes identify those bytes but cannot restore them. The held `p1_8_source.bundle` remains locally available and protects 18 currently unreferenced tree objects until its refs are pinned or separately preserved. The previously inventoried P1.6 recovery archive (205,486,080 bytes) is absent from the current workspace inventory; its bytes are not established as recoverable by this preflight.

## Consumers, qualification, and residual risk

No active current TaskEnv caller was identified for the P1.8 raw archive. Repository search is not an exhaustive PhysPi/Skill consumer audit, so external status remains `EXTERNAL_STATUS_UNKNOWN`. The exact C1 batch approval must acknowledge this uncertainty and permanent raw-data loss. The source recovery and qualification documents in Git remain historical records; they do not make missing raw trajectories replayable.

The current v1.1.0 four manipulation/provider intersections remain `TESTED_BOUNDED`. P1.8 raw data retirement does not grant a new Qualification or change any historical Judge/Human decision. L2 independent backup remains unverified; `/dev/sda` storage health remains an open risk.
