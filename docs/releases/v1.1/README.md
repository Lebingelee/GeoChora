# GeoChora v1.1.0 Release Candidate

**RELEASE_CANDIDATE — NOT_PUBLISHED**
Target version: **v1.1.0**
Code candidate: `bee498d1d784015f034c5b4af34320fdffa61411`
Candidate base: public `develop` `0ff2d846a36c7014d2b40a530f52d99e64266ff9`

GeoChora v1.1.0 is a Core consolidation release with documented breaking API
changes under the project-specific GeoChora versioning policy. It is not
claimed to follow strict Semantic Versioning. The target is approved for
release-candidate preparation only. No release tag or GitHub Release exists;
`main`, `v1.0.0`, and frozen Evidence remain unchanged.

## Candidate package

- [Scope and version policy](release_scope_and_version_policy.md)
- [Installation and clean-checkout reproduction](installation.md)
- [Public API and task identities](public_api_and_tasks.md)
- [Capability matrix and tested intersections](capability_matrix.md)
- [Learning and rendering limits](learning_and_rendering_limits.md)
- [Breaking-change migration guide](migration.md)
- [Known limitations](known_limitations.md)
- [Source, evidence, and recovery manifest](source_recovery_manifest.json)
- [Test and acceptance summary](test_acceptance_summary.md)
- [Backup manifest](backup_manifest.json)
- [Release readiness gates](release_readiness.md)

The only current candidate capability matrix is
[`capability_matrix_v1_1_0_candidate.json`](../../module/task_env/capability_matrix_v1_1_0_candidate.json).
It uses the existing capability-matrix schema; this package does not define a
second provenance or capability schema.
