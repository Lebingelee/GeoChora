# Skill and repository instruction audit

## Tracked skill set

The repository contains five skills, each with a `SKILL.md` and `agents/openai.yaml`:

- `geochora`
- `geochora-doc-governance`
- `geochora-architecture-refactor`
- `geochora-public-api-governance`
- `geochora-test-governance`

Their metadata files were reviewed and parsed. The `interface` fields identify
the display name, short description, and default prompt for the matching
skill. No missing tracked skill package was found.

## Reference correction

The general workflow skill named `task-env-experiment-evidence` as an
additional skill, but that package is not present in the tracked repository or
the active skill catalog. The reference now points to the canonical
Task Artifact / Experiment / Evidence contract at
`docs/module/task_env/03-task-artifact-experiment-evidence-contract.md`.
Specialized workflow references now match the five skills that actually exist.

## Root instructions

Added `AGENTS.md` with repository ownership boundaries, evidence language,
workspace exceptions, package-installation reality, and `develop` publication
policy. It links to all five skill files and the release's canonical scope and
evidence pages. It does not duplicate the specialized skill procedures.

## Validation

All five skill YAML metadata files and the v1.0 release/P1.8 JSON and YAML
records were parsed. Relative links in the nine new or modified Markdown
files were checked (49 links); the GeoPhys README link was resolved against
the pinned submodule gitlink because that submodule is not initialized in this
worktree. See `validation_results.json` for machine-readable results.
