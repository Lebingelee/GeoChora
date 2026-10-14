# GeoChora v1.0.0 — Scoped Phase I Core Baseline

Snapshot date: 2026-10-14.

GeoChora v1.0.0 packages the currently substantiated Phase I Core baseline. The accepted release scope is limited to historical bounded approvals and the Core/runtime behavior recorded in the evidence index. It does not declare the original Phase I blueprint complete and it does not grant new subphase, task, provider, or policy qualifications.

## Read this release package

- [Scope and release decision](release_scope_decision.yaml)
- [P1.0–P1.8 progress summary](phase1_progress_summary.md)
- [Provider and lifecycle capability matrix](capability_matrix.json)
- [Source and preflight manifest](source_manifest.json)
- [Evidence index](evidence_index.json)
- [Archive and restore manifest](archive_manifest.json)
- [Validation report](validation_report.md)
- [Known limitations](known_limitations.md)
- [Phase I follow-up tracks](../../roadmap/phase1_followups.md)
- [Phase II handoff plan](../../roadmap/phase2_plan.md)
- [Human-readable handoff](phase1_v1_release_handoff.md)

## Scope boundaries

P1.0–P1.6 retain only their original APPROVED_BOUNDED decisions. P1.7 visuomotor remains DEFERRED. P1.8 lifecycle, timebase, guarded transition, and streaming recorder infrastructure is implemented and covered by bounded tests; NutAssembly FULL and replay outcomes remain development or diagnostic evidence until their stated review and provider gates are met.

Publication of this source does not change task success semantics, Human decisions, frozen checkpoints, evidence identities, or provider ownership. In particular, diagnostic shadow completion and diagnostic D2 replay are not formal qualification.

## Release ref receipt

The release commit does not embed its own SHA or mutable remote readback. Exact main, tag object and peeled commit, develop, remaining branch refs, archive verification, and publication time belong in the local/off-repository publication receipt created after remote readback. The source manifests record the verified starting refs and immutable evidence identities.
