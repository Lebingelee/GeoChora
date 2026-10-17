# P1.8 historical retirement metadata (release-candidate proposal)

**RELEASE_CANDIDATE — NOT_PUBLISHED**

This folder preserves selected small P1.8 archive metadata byte-for-byte before any retirement decision. The records describe development experiments, engineering decisions, partial acceptance, source identities, and failure outcomes. They do not create a Human/Judge approval or a new qualification. The frozen v1.0.0 status remains authoritative: formal P1.8 NutAssembly/cross-provider qualification is not approved.

`copy_index.json` lists the source-relative paths, exact hashes, copied locations, and exclusions. It preserves 37 source records (366,744 original bytes). Selected acceptance-report links are kept with their small local support documents. Three reports remain only in the local archive: two link to path-bearing records intentionally not published, and one contains original trailing whitespace that must not be normalized.

The original 3,576-entry archive-time `file_manifest.json` is **not copied here** because it embeds private machine paths. Its SHA-256 and exclusion reason are recorded in `copy_index.json`; the exact original remains in the local P1.8 archive and is a deletion hold. It does not match the current 3,383-file workspace directory: 278 manifest paths are absent and 85 current paths are unlisted. It is historical metadata, not a deletion allowlist.

No H5 dataset, checkpoint, or full source snapshot is copied here. Some path-bearing archive manifests and one oversized acceptance record remain local holdouts. Hash metadata cannot restore raw bytes. No workspace source file has been removed, moved, or rewritten. The archive remains `DRY_RUN_ONLY`; separate maintainer approval is required before any deletion.
