# Historical archive storage audit

Full streaming SHA256 audit of the independent archive (storage_inventory.json). Original3576 files/21,798,465,898bytes all verified. Current archive includes integration snapshots/bundles/regression: 3624 files, 27011368180 logical bytes, 27019628544 allocated bytes.

| Category | files | logical bytes | allocated bytes |
|---|---:|---:|---:|
| json | 1770 | 4101231258 | 4105564160 |
| source_archive | 17 | 2612403922 | 2612457472 |
| trace | 379 | 18650013486 | 18650861568 |
| other | 1074 | 168729442 | 170946560 |
| H5 | 68 | 522265836 | 522416128 |
| contact | 121 | 915162384 | 915410944 |
| video | 170 | 38705432 | 39059456 |
| image | 25 | 2856420 | 2912256 |

Inventory records exact paths, hashes, file type, stat device/inode/nlink, readonly mode, provenance family, dependencies and same-hash locations. 234 hash-identical groups detected; they remain in place. TierA source snapshots/patches/bundles/final10N/regression and tierB causal historical failures retained. Slow-motion videos/keyframes are not assigned deletable C because regeneration from frozen inputs has not been independently verified. Exact duplicate content is a D candidate only after reference/recovery review; no deletion authorized by this classification alone.

Archive and worktree are on the same /home device, local-only/no off-host backup. Free capacity approximately 492.15GiB; no urgent pressure. Hard-link duplicates are not double-counted as reclaimable space. No compression experiment: already-compressed H5/video uncertain benefit and sole source recovery safety takes priority. GeoPhys historical bundle is incomplete; exact verified source tar snapshots, not that bundle, support reconstruction. Source archives remain read-only. No other worktree was modified.
