# v1.0 post-release documentation and governance cleanup

This record summarizes the bounded post-release cleanup on `develop`. It
clarifies published scope and current NutAssembly diagnostics, repairs the
TaskEnv installation instructions, adds repository-level contributor
instructions, and records skill and branch governance checks. No runtime or
task implementation was changed.

## Audit records

- [Documentation audit](documentation_audit.md)
- [Skill instruction audit](skill_instruction_audit.md)
- [Branch cleanup receipt](branch_cleanup_receipt.md)
- [Validation results](validation_results.json)

## Scope and publication

The public release baseline remains GeoChora v1.0.0 at the annotated `v1.0.0`
tag. This cleanup publishes documentation and repository instructions to
`develop`; it does not amend `main`, the release tag, frozen task semantics,
qualification decisions, provider code, or evidence payloads.

The release package remains the canonical source for accepted scope and
limitations: [v1.0 release README](../../releases/v1.0/README.md), [evidence
index](../../releases/v1.0/evidence_index.json), and [known
limitations](../../releases/v1.0/known_limitations.md).

## Known audit limits

- No project-context page was present in the repository or an open Library
  document session during this audit. No missing context was inferred or
  reconstructed.
- P1.6 branch cleanup is retained because its branch is checked out in the
  primary worktree with uncommitted user changes.
- Historical P1.6 and P1.8 archives remain local-only according to the release
  evidence. Their documented hashes and member checks do not prove an off-host
  backup.
- P1.3's original worktree and its ignored local data were preserved in place;
  they were not copied into an external archive.
