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
