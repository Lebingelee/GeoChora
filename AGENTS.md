# Repository instructions

## Authority and scope

- Check the current branch, HEAD, dirty paths, and implementation owners before
  changing repository files.
- Treat implementation and production callers as current behavior; use
  canonical contracts and qualification records to describe intended or
  accepted behavior. Plans and historical reports explain context but do not
  establish current capability by themselves.
- Keep changes bounded. Preserve unrelated dirty files, ignored evidence,
  submodules, and worktrees.

## CodeGraph

- When `.codegraph/` exists at the repository root, use `codegraph_explore` or
  `codegraph explore` before broad search or file reads to locate code and
  trace callers. If no index exists, skip CodeGraph; do not initialize or
  rebuild one for unrelated work.

## Canonical references

- System and ownership: `docs/global/00-system-architecture-anchor.md` and
  `docs/global/01-repository-ownership-and-boundaries.md`.
- Core scope and qualification: `docs/module/task_env/02-core-api-and-capability-scope.md`
  and `docs/module/task_env/04-core-qualification-and-governance.md`.
- Task Artifact, Experiment, Evidence: `docs/module/task_env/03-task-artifact-experiment-evidence-contract.md`.
- Published baseline and open limits: `docs/releases/v1.0/README.md`, its
  evidence index and known limitations, and `docs/roadmap/phase1_followups.md`.
- Repository workflow skills: [geochora](.agents/skills/geochora/SKILL.md),
  [documentation governance](.agents/skills/geochora-doc-governance/SKILL.md),
  [architecture refactor](.agents/skills/geochora-architecture-refactor/SKILL.md),
  [public API governance](.agents/skills/geochora-public-api-governance/SKILL.md),
  and [test governance](.agents/skills/geochora-test-governance/SKILL.md).

## Ownership and boundaries

- `task_env/` is the canonical owner of Geochora Core task and environment
  behavior. Core uses GeoPhys through its public/runtime-facing API; GeoPhys
  must not depend on Geochora internals.
- Task-specific behavior belongs to its Task Artifact unless it is reusable
  Core behavior. Keep Task Artifact, Experiment configuration, observed
  Evidence, and Judge decisions distinct.
- Registration, importability, static checks, synthetic checks, or one demo do
  not prove an end-to-end task/provider capability.
- Do not read provider-private solver or renderer state to compensate for a
  missing public capability.

## Capability and evidence language

- State the exact task, provider, backend, source identity, and exercised
  intersection when making a qualification claim. Preserve bounded approval
  labels and their limits.
- v1.0.0 is a scoped Phase I Core baseline. P1.0–P1.6 retain their historical
  bounded approvals; P1.7 remains deferred. P1.8 infrastructure tests do not
  grant NutAssembly or cross-provider qualification.
- Keep raw physical task predicates separate from lifecycle-valid task
  success, Expert completion, replay validity, and formal qualification.
- Keep diagnostic shadow execution, D1 frozen native controls, D2 frozen
  RequestedAction with live control recomputation, and D0 reconstruction claims
  separate. Never call diagnostic execution a golden or formal approval.
- Update canonical documentation when the supported contract changes. Date
  and identify evidence; do not rewrite frozen historical decisions.

## Repository hygiene and publishing

- `workspace/` is ignored for generated local data by default, but tracked
  historical P1.6 closure documents are governed exceptions. Inspect Git state
  before moving or removing anything there.
- The repository currently has no root `pyproject.toml`, `setup.py`, or
  `setup.cfg`; document dependency installation and `PYTHONPATH`, not editable
  installation, unless packaging metadata is added deliberately.
- Keep `main` and the annotated `v1.0.0` tag immutable during follow-up work.
  Publish approved documentation/governance updates to `develop` with a normal
  fast-forward push after fetching and checking the target.
- Run checks appropriate to the changed files and report what ran, what did
  not run, and any open limitation. Do not claim unperformed validation.
