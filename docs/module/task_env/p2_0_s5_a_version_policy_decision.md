# P2.0-B S5-A — Release Version Policy Decision

Status: **DECISION_REQUIRED**. No release tag or version was created.

The planned label is `v1.0.1`, but the consolidated candidate removes public
task UIDs, Python imports, runtime types/configuration, and historical CLI
routes. These are incompatible public API changes relative to `v1.0.0`.

## Maintainer decision

**A — Keep `v1.0.1` under a project-specific policy.** The project would
explicitly document that the P2.0-B consolidation is a one-time exception to
strict SemVer patch compatibility. The release notes and migration guide must
identify every removed UID/import/configuration/CLI route, state that no
behavior-changing aliases are provided, and direct historical users to the
exact recovery refs. Callers should treat this release as a migration boundary
even though its label is `1.0.1`.

**B — Follow strict SemVer.** Since `v1.0.0` is already a stable `1.0.0`
release and P2.0-B contains backward-incompatible public removals, the next
stable release should use **`v2.0.0`** (with an optional `2.0.0-rc.N`
pre-release sequence if the project uses release candidates). This communicates
the compatibility break without an exception.

Neither option is selected by this preflight. The compatibility details are in
[`p2_0_s5_a_compatibility_inventory.json`](p2_0_s5_a_compatibility_inventory.json).
The published [`v1.0.0 release package`](../../releases/v1.0/README.md) remains
unchanged.

## Required maintainer response

Choose **A** or **B** before release documentation and tag names are frozen.
If A is chosen, approve the explicit project-specific compatibility statement.
If B is chosen, approve `v2.0.0` as the stable target and the treatment of any
pre-release tags. This document records the pending choice; it does not create
a tag or publish a release.
