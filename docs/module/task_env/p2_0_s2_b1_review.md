# P2.0-B S2-B1 Final Review and Regression Receipt

## Decision and review boundary

S2-A is integrated into the canonical public `develop` branch at `32bdde9573cc20f8d8b2aafa975422834df2585b`. S2-B1 consists of implementation `8ff33b310bd15c8f5fa5e5f8bfae5f0873b64006`, dependency-manifest refresh `60fafb689efe89312d4d79b0431c61ebc98642d8`, and final review receipt `961ff67489cf6ed1fd3665fc77db2e3f389796e9`. The latter is the tested and integrated final S2-B1 HEAD; the exact task source HEAD used for the four native runs is `60fafb…`, and the intervening `961ff…` commit is documentation-only. S2-B1 has been fast-forwarded into public `develop`.

The review covers selected task-construction ownership, source identities, callers, current-source provider-free tests, and four serial CPU full-route runs. It does not delete historical implementations, retire Go2 or custom static physics, start Renderer interoperability, alter frozen Evidence, or publish v1.0.1. The existing deletion manifest remains `REVIEW_REQUIRED_NO_DELETION_AUTHORIZED`.

## S2-B1 integration receipt

Before integration, canonical `public/develop` was fetched and verified at `32bdde9573cc20f8d8b2aafa975422834df2585b`, the exact S2-B1 baseline. The implementation commit is descended from that baseline through S2-A integration metadata; `60fafb…` is parented by `8ff33b3…`, and `961ff…` is parented by `60fafb…`. The working tree was clean. All 18 recorded S2-B1 task-source file hashes and all four current-source full-route receipts matched the tested `60fafb…` source; the provider-free suite passed 157 tests. `git diff 60fafb… 961ff…` contains only the current capability matrix, this review receipt, and the S2-B deletion manifest.

The normal fast-forward push was:

```bash
git fetch public refs/heads/develop
test "$(git rev-parse FETCH_HEAD)" = 32bdde9573cc20f8d8b2aafa975422834df2585b
git merge-base --is-ancestor FETCH_HEAD 961ff67489cf6ed1fd3665fc77db2e3f389796e9
git push public 961ff67489cf6ed1fd3665fc77db2e3f389796e9:refs/heads/develop
```

The push advanced public `develop` from `32bdde9573cc20f8d8b2aafa975422834df2585b` to `961ff67489cf6ed1fd3665fc77db2e3f389796e9`; `git ls-remote` confirmed that exact ref. The same readback confirmed public `main=e4e39883fbe01d4be4b172a53a535ef0095b3d64`, annotated `v1.0.0` tag object `17c3100d4fabcb061c23569dea49973ebd177d51`, and peeled release commit `42787f5e4f658a3f81fdd2140cf7544d6342c783` were unchanged.

## S2-A integration receipt

The S2-A chain from public baseline is `77e194e2cac1ec82f7a39255a1eef0da9cd95ba8` → `a59840fc31f1da8aa9cbb0f7ce99f31773b91b5d` → CLI result-gate fix `0f27225a6cdc884c6ff8f921351917ac3db47a4d` → CLI regression tests `57c98f9063e35d6c15f6f2664e2a1238a1eed885` → integration receipt `32bdde9573cc20f8d8b2aafa975422834df2585b`. The approved push was a fast-forward. The S2-A review recorded 162 provider-free tests plus 6 subtests and verified unchanged `main`, annotated `v1.0.0`, and frozen Evidence. The exact receipt and public integration commands are in [`p2_0_s2_a_final_review.md`](p2_0_s2_a_final_review.md).

The earlier trajectory-record CLI issue is closed: failed or incomplete execution still finalizes its H5 and now exits nonzero, with the failure reason retained. Twelve CLI cases cover successful and failed outcome paths, including H5 finalization after task failure/truncation. S2-B1 does not change this CLI. (The three initial S2-B1 native-runner failures described below were separate post-run verifier defects; their original receipts remain preserved.)

## Code review and dependency migration

The implementation commit changes 21 files (task modules, tests, and source-identity record); it adds seven small task-owned support modules and deletes no task implementation. The only public make_env routes remain `pick-cube-p16-reference-v1` and `nut-assembly-outcome-reference-v1`.

PickCube now has one canonical TaskArtifact factory in `pick_cube/artifact.py`. `build_p16_artifact()` constructs the exact selected P1.6 identity and explicit 2 ms × 5-substep = 100 Hz timebase. Historical P1.1 `candidate.build_candidate()` remains a wrapper around that same factory and retains its old serialized Artifact hash. `definition.py` owns the shared variant identity and lift-success constants; `reset_policy.py` owns the reset center and envelope; `reference_config.py` resolves tracked task defaults. The selected reference builder no longer imports the legacy `task.py` or the P1.1 candidate route. The old Gym adapter remains available to its historical callers, importing shared definitions rather than defining a second task identity.

NutAssembly `definition.py` now owns the shared variant specification and the legacy `task.py` re-exports it. `reference_config.py` resolves the tracked `default.yaml` using the shared task definition. `canonical_source.py` no longer constructs `NutAssemblyEnv` to obtain defaults. `geometry.py` owns the square-yaw correction used by the active canonical solution; legacy `solution.py` re-exports `_square_yaw_correction` for existing imports. The selected active builder continues to use the same Guarded V2/V5/R3 Outcome V1 route, physical task predicates, authorization, warning admission, limits, and original strict lifecycle reporting.

The four active `make_env` routes passed module-isolation checks: selected construction does not import PickCube `task.py`/`candidate.py` or NutAssembly `task.py`/legacy `solution.py`. There is no second TaskArtifact schema, no silent UID alias, and no runtime dependency on ignored workspace configuration. The resolved NutAssembly base source/config hash remains `937aec616f2547181c3b522959a9430a801a3916ee5657b9ad7379365b51b688`; exact active source file hashes and old-to-new source mappings are in [`p2_0_s2_b1_source_identity.json`](p2_0_s2_b1_source_identity.json).

Source bytes changed, so old qualification is not inherited. PickCube preserves Artifact hash `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4`, selected controller `76108c78b8159391e448ad9f49050bed42fd7a86e0e00a0520083b4e5efb02e9`, selected solution `fcef1d3a9c093a1d0adfce394a44099f5bff61edae48b3dce2ff50406118cd61`, and seed-31 reset identity `ee9644c1af42c7897f79a0cece21e5fc4bd5323ae40eba7b7259d34d681a5fb6`. NutAssembly preserves Artifact hash `99e374bd870c70f0dd427e34c47c6e6820aaa7067365133181a001a38239b9fe`, the task policy identity, and physical-source/config lineage. The selected Outcome Solution identity is now `4bf902b9b0bcc84955e9d51177c5811e65e02b2b540678fa14235d13d7cad923`; provider controller identities are GeoPhys `cad9c5d2c1a619bc2ae94e240e7d4fb632b60599a7073e5c5adc616af0311a8f` and MuJoCo `ce29b631ef50e842bbc0d51a5350ac668e9dca431caefc6a57afeedeb2ee05f3`. Provider recipe/resolved-execution identities are GeoPhys `84912989baf66361da3db2f5dbd3f514c0a509ccf1aac479f0639ed567bfa3a5` and MuJoCo `c6747b2634c50f00703df2f09db179eb0e806cd6bfb411e79155d95b7e35ec46`. The Outcome policy identity remains `a940c6cfc4b9dbe64ae55b615e7bdbd9a210dc7495c6337b08cff688c52694ee`.

S2-B1 removes no explicitly declared Core export and does not alter the selected public `make_env` contract. Existing `build_candidate`, task variant-spec exports, and the legacy yaw-helper import remain available. One incidental module binding did disappear: `PickCubeEnv` and `PickCubeResetSampler` had been importable as side effects of `pick_cube.candidate` importing `task.py`; no repository caller uses that path, and the candidate module declared no public export list. Treat external use as unknown and decide whether to preserve or document that incidental import before a later API cleanup. S2-A did introduce breaking behavior that remains a v1.0.1 review item: the old task UIDs are rejected, and old convenience exports/routes were replaced by the explicitly named reference routes. The S2-A migration guide records those changes; external consumers cannot be discovered by repository scans, so release/version compatibility and the migration notice still need maintainer review.

## Provider-free regression

The final current-source provider-free suite passed **157 tests in 15.95 seconds**. It covered task identity and semantics, reset sampling and exact Artifact identity, task-owned import isolation, selected solution lifecycle, outcome/guard behavior, provenance, controller behavior, recorder/streaming, and recording boundaries. `git diff --check` and bytecode compilation also passed before the S2-B1 commits. No checkpoint inference, training, GPU, or historical D0-D2 campaign was run.

Command:

```bash
PYTHONPATH=. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
/home/lly/miniconda3/envs/geochora/bin/python -m pytest -q \
  task_env/diagnostics/tasks \
  task_env/diagnostics/phase1/integration/test_execution_provenance.py \
  task_env/diagnostics/phase1/integration/test_solution_lifecycle.py \
  task_env/diagnostics/phase1/integration/test_recording_streaming.py \
  task_env/diagnostics/phase1/integration/test_guarded_transition.py \
  task_env/diagnostics/phase1/test_flow_horizon_chunks.py
```

## Current-source full-route regression

All four final receipts were produced serially through the public `make_env` routes, on exact source HEAD `60fafb689efe89312d4d79b0431c61ebc98642d8`, with fresh ignored output directories. Each case stayed under a 2 GiB process-tree RSS limit and its wall-time budget. All H5 recordings finalized, passed their recorded storage roundtrip, and have T transitions and T+1 boundaries.

| Case | Result | T / boundaries | Native applications | H5 SHA-256 |
|---|---:|---:|---:|---|
| PickCube GeoPhys, seed 31, 100 Hz | PASS | 151 / 152 | 755 grouped substeps (151 public grouped intervals × 5) | `c4e66723e81d5391751b6b2007d9a82c69a4550738b62933f3a4d48079290415` |
| PickCube MuJoCo, seed 31, 100 Hz | PASS | 470 / 471 | 2,350 public `mj_step` calls | `3d4e8bcabd3cfba2e66df2bb3ae2e0e4f409d39b8026c6d6f60b7f372ebe4e45` |
| NutAssembly GeoPhys, NA-S0 seed 19, 100 Hz | PASS | 2,380 / 2,381 | 11,900 public session physics applications | `495ce4b678494b9c373f30839932dadecc55eafd64f60358edb778c0d9c95cfd` |
| NutAssembly MuJoCo, NA-S0 seed 19, 100 Hz | PASS | 2,373 / 2,374 | 11,865 public `mj_step` calls | `39739dbd6bf7dc1ea819cdeef54c124288e9c1beced792b018e6cdca30e2db74` |

PickCube completed the measured lift-only task and its expert on both providers. Its authored stage path remains exactly `move_above_cube`, `descend_vertical`, `close_gripper`, `lift`; the 10 cm lift predicate remains the success contract. Measured cube lift was 0.1081811 m on GeoPhys and 0.1060650 m on MuJoCo.

NutAssembly completed all eleven authored stages, including a passing `release_retreat` endpoint, on both providers. `inserted_on_peg`, `released_nut`, `task_success`, `planned_trajectory_completed`, and `outcome_complete` were true; diagnostic shadow mode was false; no unapproved override was used. GeoPhys terminal measurements were peg XY error 0.00147766 m, peg Z error -0.00114415 m, yaw error 0.0675844 rad, and gripper opening 0.07999993 m. MuJoCo measurements were 0.00039858 m, -0.00002656 m, 0.00081279 rad, and 0.08000000 m respectively.

The strict lifecycle observation remains separate. On GeoPhys, the original strict gate failed at step 362 with `stable_height_mismatch` in `descend_to_handle`, while Outcome V1 recorded the admissible readiness warning and completed the planned route. Its strict tolerance remains 0.0001 m; measured residual was -0.00022124 m against the unchanged 0.0003 m continuation admission limit, with the original measured readiness values preserved. On MuJoCo, the original strict expert completed with no warning. Both recorded the same policy identity and unchanged force/capture/action/runtime limits. These are bounded current-source task/provider regressions, not historical P1.8 FULL or D0-D2 qualification.

For each provider and task, S2-B1 transitions and boundaries compare exactly to the S2-A H5 after excluding only source/configuration identity metadata. This is an exact per-provider replay comparison: no transition, action, observation, physical state, control clock, or boundary divergence was found. Cross-provider step counts remain different as in the prior baseline. Fresh S2-B1 outcomes and timings are under ignored `workspace/maintenance/p2_0_part_b_s2_b1_20261016/`.

Resource receipts: PickCube GeoPhys ran 44.2 s, peak RSS 653 MB, minimum MemAvailable 3.85 GB; PickCube MuJoCo 6.0 s, 302 MB, 3.81 GB; NutAssembly GeoPhys 313.3 s, 812 MB, 3.64 GB; NutAssembly MuJoCo 102.4 s, 429 MB, 4.06 GB. Supervisor checks recorded no new kernel storage errors; memory and I/O pressure remained below stop thresholds.

### Preserved verifier failures

The initial PickCube GeoPhys run was preserved as `FAIL` because an older verifier used an overly strict floating-point clock comparison (first flagged boundary 21: 0.21000000000000005 s versus 0.21 s) and checked the wrong native-step counter for grouped execution. Its task, expert, finalized H5, T/T+1, controls, and recording checks passed. The later fresh run passed with an 8-ULP clock tolerance and provider-appropriate grouped-step counts. An initial PickCube MuJoCo verifier also used the grouped counter expectation on a direct-step provider; its fresh corrected run passed. The first NutAssembly GeoPhys run completed the physical route and finalized H5 but its post-run verifier raised `KeyError('native_interval_count')`; a new fresh run with the corrected ignored verifier passed every check. These original outputs were not overwritten. The verifier edits live only in ignored workspace; task execution source and repository code were unchanged.

## Active caller graph and S2-B2 deletion manifest

The refreshed exact manifest remains [`p2_0_s2_b_deletion_manifest.json`](p2_0_s2_b_deletion_manifest.json): 49 source/documentation entries, 35 active or mixed-support files blocked from whole-file deletion, ten legacy/public-caller files awaiting disposition, two exact S2-B2 deletion candidates, and one profile with caller audit pending. The selected runtime closure now uses the new task-owned routes, but files with historical or mixed callers remain in place.

- PickCube `task.py` is no longer in the selected construction identity; it remains directly used by `diagnostics/historical_tasks.py` and P1.1 contract diagnostics. `candidate.py` is no longer in the selected route but remains the preserved P1.1 `build_candidate()` entry point used by historical P1.1/P1.2/P1.4, policy-search, state-policy, replay and contract diagnostics. `solution.py` remains active selected support because `readiness_solution.py` inherits its planner/config behavior; it is also consumed by `_task_plans.py` and historical diagnostics. These are distinct migration slices, not safe whole-file deletions.
- NutAssembly `task.py` is no longer in the selected source closure; `diagnostics/historical_tasks.py` and `diagnostics/phase1/nutassembly/native.py` still import it. Legacy `solution.py` is no longer selected active source; historical NutAssembly diagnostics and `script/trajectory/_task_plans.py` still import it, while its yaw-helper export remains compatible. The active canonical source and selected Outcome Solution use task-owned definitions/configuration/geometry.
- Exact S2-B2 candidates are `nut_assembly/clearance_candidate_v4.py` (current SHA `10067cbdea578c17c9a1659667e8dbb5edd081ab362b2ad16b1fcdd8a53b3f83`; v1.0.0 recovery blob `6251ac1d861ab41c14379b3fd9af7cd9e82034e3`) and `nut_assembly/stable_grasp_reference.py` (current SHA `b51c054bb997e294d9e3605a28d86eec1dfc253589f3da1578078a64a6908324`; v1.0.0 recovery blob `e8cc8880ddf2e5342c74d8ef63a8acd6696f5bb9`). Their current callers are historical `integration/lifecycle_full.py` and `integration/stable_grasp.py`; frozen P1.8 records also reference these sources. No deletion is authorized.
- `nut_assembly/profiles/mujoco-noslip2-v1.json` has no recorded v1.0.0 blob; its recovery point is immutable baseline commit `77e194e2cac1ec82f7a39255a1eef0da9cd95ba8` blob `d30561416843987bca8aac0fa22ec3ef3898c574`. Resolve its historical/profile use before any removal.

Minimal S2-B2 order: (1) maintainer review S2-B1 and decide the planned v1.0.1 compatibility window and public migration notice for S2-A’s rejected legacy UIDs/exports; (2) map or explicitly retire each diagnostics, replay, reporter, and trajectory-script caller, preserving historical labels and frozen Evidence; (3) extract selected PickCube readiness support from legacy `solution.py` only if a later proposal requires its removal; keep P1.1 construction as an explicit historical route or obtain approval to remove its callers/API; (4) verify the two candidate files and profile recovery identities against immutable refs, then submit an exact separate deletion diff; (5) run import/API/Artifact/semantics/lifecycle/controller/recording/CLI gates and repeat the four full routes if runtime bytes change. Preserve generic Core contracts, Go2/static physics, v1.0.0 and all frozen records.

## Recommendation

S2-B1 is ready for maintainer review as a bounded construction-ownership consolidation with four PASS full-route checks and exact per-provider H5 behavior comparison. Keep it local pending that review. Do not start S2-B2 bulk deletion until the caller disposition and public compatibility decisions above are explicit.
