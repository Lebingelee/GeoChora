---
name: geochora-doc-governance
description: "Create, update, move, or audit Geochora documentation while preserving canonical contracts, ownership boundaries, evidence provenance, and accurate capability language."
---

# Geochora Documentation Governance

Use this skill for `README.md`, `docs/`, `task_env/doc/`, architecture
contracts, capability descriptions, experiment documentation, and navigation.
Do not use it for a code comment that does not change a public or governed
contract.

## Canonical routing

- `docs/global/` contains current system positioning, repository ownership,
  and provider boundaries.
- `docs/module/task_env/` contains current Core API, artifact/evidence, and
  qualification contracts.
- `README.md` is the public project overview and must summarize current facts,
  link to canonical detail, and clearly label unfinished capability.
- Task evolution, run outputs, and experiment evidence belong in the local
  `workspace/` contract rather than in a public architecture page.

If documents, code, and tests disagree, classify the conflict as a regression,
stale documentation, an intentional transition, or an unimplemented plan. Do
not silently edit prose to hide the disagreement.

## Invariants

1. Keep one canonical current page per concern. Do not copy a legacy page and
   leave two apparent authorities.
2. Verify capability claims against current callers, tests, provider/runtime
   provenance, and the supported intersection. A registration, import, or demo
   does not prove end-to-end support.
3. Keep Task Artifact, Experiment, evaluation report, Judge decision, and
   Evidence terminology distinct.
4. Preserve Chinese explanatory prose and established English technical terms
   such as Core, provider, Task Artifact, Experiment, Evidence, and Judge.
5. Do not publish private machine paths, private provider internals, temporary
   timing samples, or task-local implementation details as stable contracts.
6. Preserve relative links, image paths, document history, and navigation.

## Workflow

1. Record branch, HEAD, dirty paths, and the exact documentation scope.
2. Read the relevant canonical page and implementation/test evidence. Use
   CodeGraph for code navigation when the index is current.
3. Decide whether to update the canonical page, extract a current contract,
   record an investigation, or leave an unimplemented plan explicit.
4. Write concise contract language: purpose, scope, defaults, ownership,
   capability boundary, failure behavior, and links to detail.
5. Check all touched relative links and image assets, then run
   `git diff --check`. For a documentation-only change, do not claim runtime
   qualification that was not executed.
6. Hand off the authoritative page, claims verified, conflicts or gaps, and
   exact checks performed.

For changes to public API or governed tests, also use
`geochora-public-api-governance` or `geochora-test-governance` respectively.

## Versioned documents and validation

Current system documents live in `docs/global/` and `docs/roadmap/`. TaskEnv has a version index at `docs/module/task_env/README.md`. v2.1.0 retains implemented source-baseline contracts and bounded evidence; its candidate closeout text is time-scoped, and does not determine current tag/remote Release status. v2.1.1 owns the confirmed seven-stage/twenty-two-substage plan and discussion-draft protocols under `docs/module/task_env/v2.1.1/`. Do not promote those targets to implemented APIs or rewrite v2.1.0 evidence with v2.1.1 behavior. v1.1.0 and v2.0.0 content remains source-versioned; v2.0.0 is a frozen source snapshot.

The migration manifest at `docs/module/task_env/v2.1.0/maintenance/migrations/document-migration-manifest.json` maps each old path to its new path and source ref. For frozen originals, interpret relative links from the original source ref/path and report pre-existing historical breaks separately; do not edit frozen facts to produce a green current-link report.

Run `python .agents/skills/geochora-doc-governance/scripts/validate_docs.py --mode current` for the active versioned structure, links/anchors, JSON, migration manifest, version indexes and active source/Skill references. Use `--mode historical` only for the tag-backed consolidation inventory and its preserved byte/count/doc-only constraints. The [validator](scripts/validate_docs.py) checks static documentation structure only; it does not prove runtime behavior, task success, or Qualification.

Current mode scans new untracked versioned Markdown/JSON as well as tracked files. Its required-path list still describes the v2.1.0 source baseline; a successful run alone does not prove the new v2.1.1 plan is complete. Check the seven Goal documents, twenty-two unique substages, dependencies, draft status and NOT_RUN capability targets separately. Maintain one authoritative contract per concern and one version-scoped capability matrix. A planning document does not start an execution Goal or authorize agent dispatch.
