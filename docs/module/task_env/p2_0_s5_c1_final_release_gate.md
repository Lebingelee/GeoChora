# GeoChora P2.0-B S5-C1 — v1.1.0 Final Release Gate Resolution

**Status: RELEASE_BLOCKED — RELEASE_CANDIDATE, NOT_PUBLISHED**  
**Target:** GeoChora v1.1.0. Version selection is closed and is not reopened.

## Current refs and integration review

Fresh fetch/readback on 2026-10-17:

| Ref | Exact identity |
| --- | --- |
| Public `develop` | `0ff2d846a36c7014d2b40a530f52d99e64266ff9` |
| Public `main` | `e4e39883fbe01d4be4b172a53a535ef0095b3d64` |
| Public annotated `v1.0.0` tag object | `17c3100d4fabcb061c23569dea49973ebd177d51` |
| Public `v1.0.0` peeled commit | `42787f5e4f658a3f81fdd2140cf7544d6342c783` |
| Local functional candidate | `bee498d1d784015f034c5b4af34320fdffa61411` |
| Local S5-A documentation | `e0e4dbcbc3dc9d17d0dec58142be5cfb20937e73` |
| Local S5-B documentation | `2fb60de7851bf2e5651c2dc99fff7451c16e1a94` |

The tested S5-B base commit `2fb60de` had a clean tracked worktree before this
S5-C1 review documentation was added. The S5-C1 documentation is a separate
local review package and is not part of either integration candidate below.
Commit parents form the expected chain:

```text
0ff2d846 -> 5d57272d -> 59105726 -> 929dd8fa -> fc12780
         -> bee498d1 -> e0e4dbc -> 2fb60de
```

The required root Gitlinks are unchanged and checked out at GeoPhys
`c665ce5028a12bb4d2afe49f05e015fa9b684a39` and MuJoCo Menagerie
`b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`. Frozen `docs/releases/v1.0/`
matches both public `develop` and the v1.0.0 tag tree. No main, tag, or public
ref was changed.

`fc12780` was inspected independently. Its exact four-file scope is the
current capability overlay, S4.5-B source-recovery manifest, S4.5-B review, and
two migration-guide lines; it contains no executable implementation change.
`bee498d` changes only `task_env/script/trajectory/convert.py` argv forwarding
and its focused regression. It does not alter conversion calculations,
trajectory schema, or action meanings. The result gate still returns nonzero
for failed/incomplete task outcomes even when H5 finalization succeeds.

The S4.5-A/B functional unit through `bee498d` is **recommended for
maintainer-approved normal fast-forward integration**. The candidate release
documents through `2fb60de` are a separate integration approval. Neither has
been authorized or pushed. Exact commands are in the [integration procedure](../../releases/v1.1/publication_procedure_draft.md).

## Source recovery and evidence

The recorded retirement manifests were checked against immutable Git objects:

| Recovery group | Checked | Result |
| --- | ---: | --- |
| S3 Go2 source blobs | 54 | 54 blob IDs and SHA-256 values match |
| S4 Static Template source blobs | 25 | 25 blob IDs and SHA-256 values match |
| S4.5-A retired source blobs | 10 | 10 blob IDs and SHA-256 values match |
| S4.5-B retired source blobs | 5 | 5 blob IDs and SHA-256 values match |
| S4.5-B current source migrations | 10 | 10 current blob IDs and SHA-256 values match |

All eight H5/checkpoint/result files currently enumerated as important ignored
evidence match their recorded SHA-256 values. This checks the files in the
current single-disk workspace; it does not verify a backup or restore.
Selected task execution-source closures remain unchanged through the functional
candidate. The S5-B test-helper correction is provider-free test code only.

## PickCube controller identity portability

The discrepancy is caused by an absolute `compiler meshdir` in generated
PickCube MJCF and identity construction hashing the complete raw XML bytes.
`PandaKinematics.source_sha256` hashes `xml.encode()`; the task's Panda asset
composer sets `meshdir` to the resolved absolute Menagerie assets directory.

| Observation | Original checkout | Detached checkout |
| --- | --- | --- |
| Source revision | `2fb60de7851bf2e5651c2dc99fff7451c16e1a94` | `bee498d1d784015f034c5b4af34320fdffa61411` |
| Controller identity | `76108c78b8159391e448ad9f49050bed42fd7a86e0e00a0520083b4e5efb02e9` | `a8ef891961d020721a35a032ea2093e8da61f36747babfe4bc4ff0e12195cbde` |
| Raw generated MJCF SHA-256 | `bdd119833a5ae3c8176daf1f5ef586c3601870f10f4b4b5f6d7aa730fe5f0fed` | `c5a845a7824fd6810d10d3f461ca248d71448a84de3b29c5453cdcda7022915e` |
| Absolute `meshdir` | `/home/lly/Program_Files/Geochora/asset/external/mujoco_menagerie/franka_emika_panda/assets` | `/home/lly/Program_Files/Geochora/workspace/maintenance/p2_0_v1_1_clean_checkout_20261017/asset/external/mujoco_menagerie/franka_emika_panda/assets` |
| XML SHA after replacing checkout root with `${REPO_ROOT}` | `017b3fb8ae4ad46bd382b43d4462c067d9d6ceafbbfea0a43880bcf0fed6f1ba` | same |

The Artifact SHA `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4`, task configuration SHA `0d6b26b08affd68c95a4f3209111f7c4ee2ce62088b664370f7c11b6045e9aa0`, resolved runtime config SHA `d187ad45cec5fe7ac8a12a115dcf7a185336e8c1b78524ae5d2a6ed17bac22a1`, solution identity `514a5ed3bc0d289761ef88a00b1e7c11df2795133506ab148db9ab8e98e55241`, and readiness identity `ccc3e93e1d740beaad3b0c52098c87e5830baabfa1f146df6fdbcf647b60c453` match. PickCube task, solution, config, object-owner source hashes also match; the Panda asset-bundle digest is `5c5f93668a16c2861e51cd7be911b7fffb6727db71758ca1a289a666824885ea` in both.

A provider-free controller-compute probe used the same synthetic canonical
reset state and absolute-pose request in both checkouts. FK tip and Jacobian
digests matched; the physical `CanonicalControlTarget` fields had SHA-256
`d39d408fd14cea0037d71058b53b97ccd6ce2a6021578f6c6f472960a8d2f80e` in both.
The controller identity field still differs, so the complete target identity
and provenance identity are not path-independent. No provider applied-control
readback or full relocated trajectory was performed.

Recommendation **B**: retain this as an explicit v1.1.0 limitation. Cross-
checkout controller hash equality is not guaranteed; preserve each run's
actual generated identity. This is a recommendation, not yet a maintainer
decision. Stabilizing the hash would change identity semantics and requires a
separate migration and test plan. Do not rewrite old controller or H5 hashes.

The earlier relocated-checkout provider-free suite remains recorded as
**139 PASS / 8 FAIL**: six failures were `find_spec()` on dotted retired
modules whose parent package was absent (the test helper has since been fixed);
one was a `/workspace/` path guard triggered by the checkout location; one
was the path-dependent controller identity. It was not rerun after analysis.
Do not call relocated-checkout full regression PASS.

## Reproduction levels

| Level | Status | Scope |
| --- | --- | --- |
| Existing-environment detached checkout | **PASS — BOUNDED** | Exact source `bee498d`, exact two root Gitlinks, PickCube and NutAssembly `make_env` construct/reset/close on GeoPhys CPU and MuJoCo CPU. No full route. |
| Fresh Python dependency installation | **NOT_RUN** | Existing validated Python 3.12.14 environment was reused. The source-based install commands are documented; a clean dependency solve/install was not independently verified. |
| Full relocated-checkout regression | **NOT_RUN** | Initial exploratory run is 139 PASS / 8 FAIL as explained above; no successful full relocation regression is claimed. |

The detached smoke confirms current source and asset availability for its bounded
construct/reset/close scope. It does not prove a fresh install or full execution
reproducibility.

## Final bounded verification

Command:

```bash
python -m pytest -q task_env/diagnostics/tasks task_env/diagnostics/render/test_backend_registry.py
```

Result on 2026-10-17: **147 passed, 6 subtests passed, 1 upstream Taichi
`locale.getdefaultlocale` deprecation warning, 160.51 s**. Receipt:
`workspace/maintenance/p2_0_s5_c1_20261017/provider_free_final.log`.
The suite covers selected IDs and Artifact/semantics, construction/controller,
recording and CLI result gates, retired APIs/runtimes, generic batch and learner
boundaries, renderer contracts, and documentation-support imports. Existing
accepted full-route H5 receipts were hash-checked and were not rerun.

## Gate table

| Gate | Status | Resolution |
| --- | --- | --- |
| Functional integration authorization | **MAINTAINER_DECISION_REQUIRED** | Recommend FF through `bee498d`; no push/merge performed. |
| Release-document integration authorization | **MAINTAINER_DECISION_REQUIRED** | Review and approve candidate docs through `2fb60de` separately. |
| Source and Git ancestry | **PASS** | Exact parent chain, clean tracked worktree, protected refs read back; no unexpected root Gitlink changes. |
| Task/runtime regression | **PASS — TESTED_BOUNDED** | 147 tests + 6 subtests; accepted four full-route intersections remain unchanged. |
| API compatibility disclosure | **PASS — DISCLOSURE COMPLETE** | Breaking routes and migration/recovery refs are documented; final external notice needs review. |
| Controller portability decision | **MAINTAINER_DECISION_REQUIRED** | Recommend B; cross-checkout equality is not guaranteed. |
| Detached-checkout reproduction | **PASS — BOUNDED** | Existing Python environment, construct/reset/close only. |
| Fresh-install validation | **NOT_RUN** | No fresh dependency environment or install test. |
| Git submodule availability | **PASS** | Exact root Gitlinks initialized and fetch-dry-run resolved from declared remotes. |
| Evidence/source recovery integrity | **PASS — LOCAL CHECK ONLY** | 94/94 retired blobs, 10/10 migrated blobs, and 8/8 listed ignored artifacts match; independent backup not implied. |
| Independent backup verification | **BLOCKED — BACKUP_NOT_VERIFIED** | Only `/dev/sda` is available; no authorized independent destination or restore test. |
| v1.1.0 capability matrix approval | **MAINTAINER_DECISION_REQUIRED** | Matrix is consistent and bounded; final approval remains open. |
| Maintainer publication authorization | **MAINTAINER_DECISION_REQUIRED** | Publication is prohibited in S5-C1 and remains BLOCKED by backup. |

Publication is not READY while the independent backup gate is blocked. See the
[release readiness table](../../releases/v1.1/release_readiness.md),
[backup manifest](../../releases/v1.1/backup_manifest.json), and [S5-C2
procedure draft](../../releases/v1.1/publication_procedure_draft.md).
