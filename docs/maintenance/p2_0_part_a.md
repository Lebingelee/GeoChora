# P2.0-A workspace evidence ownership

The active development branch is `develop`. Generated Task Artifact,
Experiment, qualification, diagnostic, archive, and maintenance workspace
contents remain Git-ignored. Filesystem retention is governed by provenance
and evidence value independently of Git tracking.

## Historical P1.6 closure metadata

The 21 P1.6 closure files formerly tracked under
`workspace/qualification/phase1/p1_6_closure/` are historical qualification
decisions, specifications, manifests, and reports. Their authoritative bytes
remain in the immutable [v1.0.0 release tree](https://github.com/Lebingelee/GeoChora/tree/v1.0.0/workspace/qualification/phase1/p1_6_closure).
They were removed from the active `develop` index while local copies were
preserved. They were not relocated into `docs/` or rewritten.

The [release evidence index](../releases/v1.0/evidence_index.json),
[archive manifest](../releases/v1.0/archive_manifest.json), and
[historical Human decisions](../module/task_env/phase1_mainline_integration/historical_decisions/)
retain their original identities and bounded scopes. Historical relative
`workspace/` paths in frozen release manifests resolve against their recorded
source identity, including v1.0.0, rather than the current `develop` tree.
Use the original SHA256 to compare any local or archived copy.

## Local consolidation and deletion gate

Keep phase, task, provider, experiment, and qualification identities. Record
the original and retained paths and verify complete readable copies before
deleting originals. Preserve failed, partial, deferred, and diagnostic
evidence needed to explain historical boundaries. Never substitute rerun
results for original evidence.

Hardlinks and multiple directories on one disk do not provide independent
failure isolation. Unverified backups, storage errors, active processes, or
unresolved local changes block the affected destructive operation. Other safe
maintenance may continue with its own evidence recorded.

The detailed per-machine inventory, relocation mapping, removal manifest,
resource review, checks, and blockers are local maintenance outputs under
`workspace/maintenance/p2_0_part_a/`. They are intentionally outside Git
tracking. Publishing this ownership rule does not claim that every local
worktree cleanup is complete or grant any new Phase I qualification.
