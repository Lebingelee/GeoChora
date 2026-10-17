# S5-C8 retention and cleanup preflight

**Release:** GeoChora v1.1.0
**State:** `RELEASE_CANDIDATE — NOT_PUBLISHED`
**Preflight:** complete for the exact manifests listed below; **no deletion executed**.

## Retention baseline

The retained historical-decision package was committed locally at `10dd76712204225592cef9b37d8889dbbcfde2e6`; it contains 37 exact original records (366,744 bytes) plus its README and copy index. The C8 documentation and compact bundle-closure receipt are recorded as current L1 metadata. L1 contains 83 files: 40 prior release metadata files, the 39-file historical decision package, and 4 C8 records. L2 has 22/22 current files at their recorded sizes and SHA-256 values (24,563,669 bytes). The accepted GeoPhys NutAssembly physical outcome and its original strict Expert failure remain distinct. No L1/L2 path or inode overlaps a cleanup candidate.

The original archive manifest and its live filesystem snapshot remain separate. The 3,576-record archive manifest and 3,383-file live inventory reconcile to 3,298 exact common entries, 278 absent historical entries, and 85 live-only entries. The 37 selected P1.8 decision/provenance records have exact Git copies; the private-path file manifest and selected small metadata copies are held outside the P1.8 target on the same disk.

## Exact batch candidates

The machine-readable file allowlists, protected-inode inventory, lstat records, source-manifest identities, hardlink accounting, and post-operation checks are in the ignored local directory `workspace/maintenance/p2_0_s5_c8_20261017/`:

| Batch | Scope | Conditional unique reclaimable allocation | Exceptions |
|---|---|---:|---|
| A | 17 L3-A regenerable cache files | 311,296 bytes | None after current path/hash verification |
| B | 6,792 exact approved L3-B file paths (6,795 total reviewed entries including 3 holds), including a registered detached checkout handled only by non-forced Git worktree operations | 3,317,481,472 bytes | Three P1.1 candidate files remain held. The checkout includes 573 ignored/untracked files and 3 Git administrative pointers; copied S5-B receipts are outside the worktree. |
| C1 | P1.8 live archive, exact files only | 10,978,766,848 bytes | `p1_8_source.bundle` remains held (18,571,359 logical bytes); no directory-recursive removal. |
| C2 | Remaining L3-C historical raw files | 61,120,978,944 bytes | 516 C6 unresolved paths and 2 symlinks remain held/not followed. Hardlinked storage is deduplicated by inode. |

The figures are conditional upper bounds based on current allocated blocks, not guaranteed disk-space recovery. The aggregate candidate set is 75,417,538,560 bytes (about 70.24 GiB) if every proposed batch is approved and storage behavior matches the current lstat snapshot. Batch B must use proper submodule/root `git worktree remove` operations; shared Git object stores are not part of its file allowlist.

The exact approval hashes are in `workspace/maintenance/p2_0_s5_c8_20261017/final_preflight_summary.json` and the `.sha256` sidecars for each batch manifest. They are generated from the exact current protected metadata. Any path, inode, source, or manifest change invalidates the affected approval hash.

## Proposed policy and current gate

Proposed retention policy: `L1_METADATA_REQUIRED`, `L2_CURRENT_RAW_EVIDENCE_REQUIRED`, `L3_REVIEWED_RETIREMENT_ALLOWED`. This proposal does not waive the previous backup requirement. Current recorded states are:

- L1 metadata: locally present and versioned; C8 additions are not pushed.
- L2 raw evidence: local size/SHA-256 integrity verified.
- L2 independent backup: `NOT_VERIFIED`.
- L3 retirement: manifests prepared; approval and execution pending.
- Historical recovery loss: explicit, if any batch is approved.
- Storage health: `OPEN`; single-disk `/dev/sda` and prior ata5 BadCRC remain disclosed.

Public `develop` remains `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`; `main` and annotated `v1.0.0` remain unchanged. No tag, push, release publication, or qualification decision was made in this preflight.

## Approval boundary

Each batch requires explicit maintainer authorization naming its batch and exact manifest SHA-256. Earlier agreement with the L1/L2/L3 direction or with P1.8 retirement does not authorize deletion. Approving one batch does not approve another. On approval, the batch must be revalidated against its exact lstat/inode manifest immediately before execution; any mismatch stops that batch.
