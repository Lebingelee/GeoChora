# GeoChora P2.0-B S5-A — Release Preflight

Date: 2026-10-17

Status: **preflight prepared; maintainer decisions and stage integrations remain pending**

- Public `develop` at fresh fetch: `0ff2d846a36c7014d2b40a530f52d99e64266ff9`
- Local S4.5-A review head: `59105726c6ec28f467b637b7124f667a6fdd6b52`
- Local S4.5-B implementation: `929dd8fafe8dca5b0f375341045501c0a8eed9c7`
- Local S4.5-B documentation receipt: `fc12780dcaebcb12f9740ae7f3f28224a47c3bbf`
- Local S5-A converter-CLI fix: `bee498d1d784015f034c5b4af34320fdffa61411`

This record prepares a release-candidate review. It neither integrates the
local workflow candidates nor publishes a release. Frozen v1.0.0 and its
Evidence remain unchanged.

## Ref and source review

| Gate | Result |
| --- | --- |
| Fetched `public/develop` | `0ff2d846a36c7014d2b40a530f52d99e64266ff9`; matches last observed S4 baseline. |
| Local chain | `0ff2d846 → 5d57272 → 5910572 → 929dd8f → fc12780 → bee498d`; all five parent/ancestor gates pass. |
| Current branch | `codex/p2-0-b-s4-5-b-workflow-consolidation`. Worktree was clean before this S5-A documentation draft; no implementation changes were made. |
| `public/main` | `e4e39883fbe01d4be4b172a53a535ef0095b3d64`; unchanged from the S4.5-B receipt. |
| Annotated `v1.0.0` | tag object `17c3100d4fabcb061c23569dea49973ebd177d51`, peeled commit `42787f5e4f658a3f81fdd2140cf7544d6342c783`; unchanged. |
| Frozen release paths | No S4.5-A/B changes under `docs/releases/v1.0/`; historical Evidence files and decisions were not edited. |
| Task source identity | S4.5-A/B do not modify selected task code. PickCube and NutAssembly task trees remain the accepted S2-C1/S2-C2 trees; source/config identities are in the [release inventory](p2_0_s5_a_release_inventory.md). |
| Generic contracts | Runtime/provider, task Artifact, recorder/H5, renderer, learner, Batch/Device/Vectorization sources were not changed by S4.5-B. Their unchanged paths are recorded in the S4.5-B source-recovery manifest. |
| Runtime workspace configuration | Selected task builders load their checked-in task configuration. No ignored `workspace/` configuration is required to construct or execute either selected route. |
| Submodules | No dirty or unexpected submodule change. `GeoPhys` is at `c665ce5`; the root Menagerie submodule is at `b846dd1`. Two optional nested GeoPhys externals (`dexjoco`, nested Menagerie) are not initialized; no update or initialization was attempted. |

Recovery manifests were rechecked against Git objects and SHA-256: S3 Go2
source **54/54**, S4 static-solver source **25/25**, S4.5-A prior source
**10/10**, and S4.5-B retired script/helper source **5/5**. The ten S4.5-B
implementation source migrations match their recorded current blobs and
hashes. All 13 source-closure paths listed by the S4.5-B manifest are unchanged
between the A review and B implementation commits.

The S4.5-A and S4.5-B reviews found no duplicate TaskArtifact, RuntimeSession,
Recorder/H5, Batch, Learner, or Renderer contracts. Historical callers that
remain as stubs fail explicitly and point to source-recovery manifests; the
removed private camera helper had no surviving active importer. The task-owned
selected routes still use guarded NutAssembly `step_expert()` and preserve
separate task outcome and Expert lifecycle reporting.

## Separate integration recommendations

**S4.5-A:** the task examples, canonical recorder, result gating, and historical
retirement review are otherwise sound. The original A/B stack has one
integration blocker: its retained `trajectory convert` dispatcher passed an
argument list to a converter `main()` that did not accept one. The fresh
`convert --help` probe reproduced a `TypeError`. A small S5-A follow-up changes
the existing parser to accept forwarded `argv`; it does not alter conversion
semantics. The fix and new regression test pass. Therefore **do not integrate
the original A head by itself**; require review of the follow-up commit below.

**S4.5-B:** the renderer/learning wrappers, documentation and bounded results
are independently reviewable and do not change the selected task/core
implementation closures. The B commit inherits the same dispatcher issue, so
do not publish B without the S5-A fix. Treat A and B as separate maintainer
decisions, but integrate only after both decisions and the small compatibility
fix are approved. This avoids exposing an intermediate public `develop` with a
known broken supported conversion command.

The exact safe normal fast-forward target is the converter-fix commit
`bee498d1d784015f034c5b4af34320fdffa61411`. It contains the reviewed A/B
chain and the nonbreaking dispatcher correction. Integration prerequisites
remain:
fresh `public/develop` must equal `0ff2d846a36c7014d2b40a530f52d99e64266ff9`,
the ancestry check must pass, and all three decisions (A, B, and the fix) must
be explicit. Then use:

```bash
git fetch public
test "$(git rev-parse public/develop)" = 0ff2d846a36c7014d2b40a530f52d99e64266ff9
git merge-base --is-ancestor public/develop bee498d1d784015f034c5b4af34320fdffa61411
git push public bee498d1d784015f034c5b4af34320fdffa61411:refs/heads/develop
git ls-remote public refs/heads/develop
```

Expected readback is `bee498d1d784015f034c5b4af34320fdffa61411`. Any new
remote head, branch divergence, failed gate, or source mismatch cancels this
command pending renewed review. No push was performed. S5-A draft documents
remain a separate release-preflight record.

## Release candidate and compatibility decisions

The detailed inventories are:

- [Source and capability inventory](p2_0_s5_a_release_inventory.md)
- [Candidate capability matrix](capability_matrix_v1_0_1_candidate.json)
- [Breaking compatibility inventory](p2_0_s5_a_compatibility_inventory.json)
- [Version-policy decision](p2_0_s5_a_version_policy_decision.md)

The release name is unresolved. The maintainer must choose **A** (`v1.0.1`
under an explicit project-specific breaking-change policy) or **B** (`v2.0.0`
to follow strict SemVer after incompatible removals). No tag was created.

The present-tense documentation audit found and corrected these stale claims:

- Root `README.md` described Go2 as a current regression route and summarized
  pre-S4.5 status. It now points to the selected task UIDs and accurately marks
  S4.5 examples as local candidates.
- `docs/global/00-system-architecture-anchor.md` described generic Static
  Physics contracts as retained; it now distinguishes the retired
  GeoChora-owned solver from generic batch contracts and the GeoPhys-owned
  adapter.
- `docs/global/01-repository-ownership-and-boundaries.md` had the same
  static-solver ambiguity and is corrected.
- `docs/module/task_env/04-core-qualification-and-governance.md` now records
  S4.5-A/B as local candidates and does not imply qualification.
- `docs/module/task_env/02-core-api-and-capability-scope.md` now distinguishes
  integrated S3/S4 from the unintegrated S4.5/S5-A local review chain.
- `task_env/doc/api/semantics/built_in_tasks.md` described obsolete
  PickCube/NutAssembly task-definition classes; it now documents the current
  reference routes, Artifact identities, and lifecycle boundaries.
- `docs/module/task_env/canonical-solution-guarded-transitions.md` now labels
  its P1.8 candidate classes/profiles as historical development context and
  points to the active flattened NutAssembly solution. The S4 retirement
  receipt distinguishes its review-time local status from its later public
  integration. The migration guide presents the unresolved version choice
  instead of treating `v1.0.1` as already selected.

Historical P1.8, Phase I, source-lock, qualification, and frozen release
reports intentionally retain their original-time claims. They are not current
user guidance and are not rewritten by this preflight.

The remaining search matches in current docs are explicitly historical: the
`NutAssemblySquare` heading in qualification-policy section 3.2 describes the
prior qualification scope, and the P1.0 status paragraph in
`02-core-api-and-capability-scope.md` describes its named baseline; the
guarded-transition design note is explicitly historical. Other occurrences of
retired Go2/static-template identities are migration/recovery tables or
explicit negative-admission guidance. No present-tense current route claims
use the retired UIDs, Go2, static-template solver, or obsolete NutAssembly
Candidate imports.

## Validation and resource record

Existing accepted bounded receipts, not repeated here:

- S4.5-A: 129 provider-free tests; PickCube/MuJoCo/CPU/seed31 full example;
  canonical H5 recording and roundtrip; NutAssembly/MuJoCo/CPU/seed19/horizon2
  expected-incomplete smoke with nonzero exit.
- S4.5-B: 146 tests and 6 subtests; Pendulum GeoPhys CPU scalar/batch RGB
  rasterizer one-step smokes; one-update SB3 Pendulum smoke; H5 inspection;
  negative retired CLI checks. These are bounded tests, not qualifications.
- Selected-task native routes were not repeated because their task source
  closures and accepted configurations are unchanged; exact source revision
  and receipts are recorded in the candidate matrix.

S5-A preflight check record: the 147-test run executed at parent `fc12780` with
the exact two-file converter-dispatch patch later committed as
`bee498d1d784015f034c5b4af34320fdffa61411`; no code changed after the run.
Release-preflight documents remain a separate draft:

| Check | Result |
| --- | --- |
| Provider-free selected tasks, lifecycle, recording, retirement, renderer registry | **PASS** — 147 tests, 6 subtests, one upstream Taichi locale deprecation warning; 155.10 s. Exact log: `workspace/maintenance/p2_0_s5_a_20261017/provider_free_final.log`. |
| Public task imports/configuration and Artifact identity | **PASS** — task builders returned PickCube SHA-256 `fd5bc968…` and NutAssembly `99e374bd…`; task config YAML hashes matched the candidate records. No native provider was constructed by this identity check. |
| RSL/SB3, Batch/Device/Vectorization and renderer registry contracts | **PASS_BOUNDED_PROVIDER_FREE** within the same 147-test suite. Fake renderer endpoints are contract tests only. |
| Example CLI syntax | **PASS** — nine `--help` commands: selected task examples, recording, H5 inspection, SB3, scalar/batch rendering, generic RSL, and trajectory converter dispatch; all exit 0. |
| Python compilation and docs links | **PASS** — `compileall` over `examples` and `task_env/script`; 12 reviewed Markdown files, zero missing local links. |
| Candidate/recovery JSON and whitespace | **PASS** — candidate matrix and compatibility inventory parse; S3/S4/S4.5 manifests parse; `git diff --check` passes. Recovery blobs/hashes verified: S3 54/54, S4 25/25, S4.5-A 10/10, S4.5-B 5/5; ten current migration hashes and 13 protected closure paths verified. |
| Native full task reruns | **NOT_RUN** — selected task trees and accepted scalar execution identities remain unchanged; S4 changes were confined to static-template/batch admission and scalar resolved configuration identity was checked in its receipt. |
| Broad RL, GPU, Native Flora, native GeoPhys Rigid Batch | **NOT_RUN** — outside this bounded preflight. |

The final provider-free run log is preserved in
`workspace/maintenance/p2_0_s5_a_20261017/provider_free_final.log`; it records
147 passed tests and 6 passing subtests in 155.10 seconds. A separate
`convert --help` run and the focused 9-test workflow file passed after the fix.
Ignored H5, checkpoints and historical Evidence were not modified or deleted.

## Storage, recovery, and release gates

The single-disk `/dev/sda` / `ata5` BadCRC risk and lack of a verified
independent backup remain **OPEN**. A recent journal query returned no matching
ATA/SATA/read/write error lines, but journal access/result absence is not proof
of device integrity and does not close the risk. Before the final suite,
observations were approximately 4.2 GB available memory, 22.8 GB free swap, and
low PSI. Immediately after it, approximately 3.6 GB remained available with
elevated short-window PSI (about 9–13%); no further native or resource-intensive
tests were started. No disk health guarantee is made.

Before release publication, require an independent backup on a separate
physical device or controlled external storage; include the repository refs,
release package, immutable Evidence, H5/checkpoint records, and manifests;
verify every backup hash; perform a restore/read test from that independent
copy; and record the location, timestamp, verification result, and responsible
maintainer. The repository and its same-disk clones do not satisfy this
requirement.

Release publication remains blocked pending: separate S4.5-A/B maintainer
integration decisions; a version-policy choice; public API migration approval;
final capability matrix review; final source/ref readback after integration;
and verified independent backup. This document authorizes none of those
external actions.
