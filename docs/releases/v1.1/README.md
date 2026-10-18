# GeoChora v1.1.0 Release Content

Target version: **v1.1.0**

This directory contains the proposed v1.1.0 release content and review
receipts. Publication status is determined by the public Git refs and any
GitHub Release, not by this document. Verify `refs/heads/v1.1.0` and
`refs/tags/v1.1.0` before describing the release as published.

## Provenance snapshot

At the start of final release review, the functional implementation candidate
was `bee498d1d784015f034c5b4af34320fdffa61411`, and the public integration
base was `develop` at `2fb60de7851bf2e5651c2dc99fff7451c16e1a94`. S5-C1 through
S5-C8 release-review documents were local and unintegrated. The final reviewed
release commit, if approved, is recorded by the Git release refs.

GeoChora v1.1.0 is a Core consolidation release with documented breaking API
changes under the project-specific GeoChora versioning policy. It is not
claimed to follow strict Semantic Versioning. The maintainer selected v1.1.0
as the target version; publication remains a separate, ref-verified action.
At the start of this review no v1.1.0 tag or GitHub Release existed, and
`main`, `v1.0.0`, and frozen Evidence were unchanged.

## Candidate package

- [Scope and version policy](release_scope_and_version_policy.md)
- [Installation and clean-checkout reproduction](installation.md)
- [Public API and task identities](public_api_and_tasks.md)
- [Capability matrix and tested intersections](capability_matrix.md)
- [Learning and rendering limits](learning_and_rendering_limits.md)
- [Breaking-change migration guide](migration.md)
- [Known limitations](known_limitations.md)
- [Source, evidence, and recovery manifest](source_recovery_manifest.json)
- [Release acceptance evidence index](evidence/README.md)
- [S5-C3 minimal evidence and retention report](../../module/task_env/p2_0_s5_c3_minimal_release_evidence.md)
- [Test and acceptance summary](test_acceptance_summary.md)
- [Backup manifest](backup_manifest.json)
- [Release readiness gates](release_readiness.md)
- [S5-C8 final report — maintainer-accepted closure with retained exceptions](c8_manual_cleanup_final_report.md)
- [S5-C8 original-goal requirement-by-requirement completion audit](c8_goal_completion_audit.md)
- [S5-C8 revised storage monitoring criteria and SMART interpretation](c8_storage_monitoring_revision.md)
- [S5-C8 earlier authorized execution and safety-stop receipt](c8_execution_and_phase2_closure.md)
- [S5-C1 final gate receipt](../../module/task_env/p2_0_s5_c1_final_release_gate.md)
- [S5-C2 integration and backup gate receipt](../../module/task_env/p2_0_s5_c2_public_integration_readiness.md)
- [S5-C3 publication checklist draft](s5_c3_publication_checklist_draft.md)
- [Publication procedure draft](publication_procedure_draft.md)

The only current candidate capability matrix is
[`capability_matrix_v1_1_0_candidate.json`](../../module/task_env/capability_matrix_v1_1_0_candidate.json).
It uses the existing capability-matrix schema; this package does not define a
second provenance or capability schema.
