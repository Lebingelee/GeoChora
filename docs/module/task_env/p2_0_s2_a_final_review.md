# P2.0-B S2-A Final Review and Full-Route Regression

## Review boundary and decision

The current maintainer baseline `77e194e2cac1ec82f7a39255a1eef0da9cd95ba8` matches the freshly fetched canonical GeoChora `public` remote `develop` head and is the direct parent of local S2-A `a59840fc31f1da8aa9cbb0f7ce99f31773b91b5d`. An earlier prompt contained a mistyped SHA (`77e194e2cac1ec82cde927d57d4bf3d67a8783c3`); that value does not resolve and has been corrected in the active maintenance records below. All 35 recorded implementation/source identities matched the bytes exercised by the four native runs. The separate CLI-only fix `0f27225a6cdc884c6ff8f921351917ac3db47a4d` is directly on top of S2-A and changes no task builder, session, controller, solution, or runtime execution source. The four named native cases ran on exact S2-A source `a59840fc…`; provider-free checks now run on the final review commit chain. No merge, push, or change to `main`, `v1.0.0`, or historical Evidence occurred.

The selected public routes passed bounded full-trajectory functional checks. PickCube GeoPhys is classified `PASS_RECONCILED`: its simulator run and finalized H5 passed independent contract and historical comparison checks, while the original post-run wrapper exited `FAIL` due to verifier defects recorded below. That failure receipt is preserved. The trajectory-record CLI result gate has since been corrected and tested. The baseline is confirmed. The reviewed commit chain is ready for maintainer fast-forward approval, subject to the documented public API compatibility/version decision; this review does not merge or push it.

The reviewed 42-file diff contains 35 implementation/test files and 7 documentation, capability, or identity/dependency-manifest files. No historical implementation was deleted.

## S2-A integration gate

The checked code chain is `77e194e2cac1ec82f7a39255a1eef0da9cd95ba8` → `a59840fc31f1da8aa9cbb0f7ce99f31773b91b5d` → `0f27225a6cdc884c6ff8f921351917ac3db47a4d` → `57c98f9063e35d6c15f6f2664e2a1238a1eed885`. The added `57c98f9` commit changes tests only. The final provider-free run passed 162 tests and 6 subtests. A fresh canonical remote lookup still returned the stated baseline SHA; the earlier malformed prompt SHA remains only as audit context in the manifest. No fast-forward or push has been executed.

After explicit maintainer approval, the bounded fast-forward command sequence is:

```bash
git fetch public refs/heads/develop
test "$(git rev-parse FETCH_HEAD)" = 77e194e2cac1ec82f7a39255a1eef0da9cd95ba8
git merge-base --is-ancestor FETCH_HEAD HEAD
git push public HEAD:refs/heads/develop
```

Expected result: public `develop` advances from `77e194e2cac1ec82f7a39255a1eef0da9cd95ba8` to the reviewed local chain head; `main` and `v1.0.0` remain unchanged. If the remote head differs or the ancestry gate fails, stop and re-review. The command sequence is recorded for approval and has not been run.

## Code review

`task_env/registry.py` explicitly registers the two selected UIDs and raises on `pick-cube-v1` and `nut-assembly-square-v1`; it does not silently redirect legacy task identities. The task packages export the named reference adapters. `SelectedReferenceEnv` owns scalar session coordination, public stepping, lifecycle boundaries, and recorder wiring. It creates no new `TaskArtifact` schema, task evaluator, controller semantics, or task-success predicate. The PickCube and NutAssembly builders continue to resolve their task-owned canonical source, artifact, reset, controller, and solution.

PickCube retains the selected Artifact `pick-cube-v1/p1_6_experimental_100hz`. Its reference environment applies one requested action and calls grouped `session.step()` once per control interval; it does not replace the P1.6 ZOH interval with a sequence of externally visible native actions. The exact four recorded stages remain `move_above_cube`, `descend_vertical`, `close_gripper`, and `lift`. Success remains the measured lift predicate; grasp is not a separate required predicate.

NutAssembly uses the selected nominal V2/V5/R3 lineage and `nutassembly-outcome-oriented-completion-v1`. Guard authorization, force cap, capture limits, strict readiness observations, action budget, and runtime terminal behavior remain in the task-owned Solution/session path. The reference adapter gathers actual applied native substeps and passes them to the selected solution. `DiagnosticShadowCoordinator` is not promoted, shadow mode is disabled, and the original strict Expert lifecycle result is recorded independently from outcome completion. The only GeoPhys continuation is the allowlisted `descend_to_handle/stable_height_mismatch`; other failures remain fail-closed.

Resolved configurations use tracked task profiles and source files; the builders do not resolve ignored workspace configuration at runtime. All four launch records point to the exact S2-A HEAD and carry the recorded source-file map. Full resolved source/configuration maps remain in the ignored test receipt directory.

The review found that `task_env/script/trajectory/record.py` finalized failed or incomplete routes and returned exit code 0. Commit `0f27225a6cdc884c6ff8f921351917ac3db47a4d` fixes this: the CLI still finalizes the H5, records a failure reason, and returns nonzero unless the selected policy and task outcome complete. For NutAssembly it requires full planned trajectory, outcome completion, task success, and no unapproved override while keeping original strict Expert status separate. Twelve CLI cases now exercise success/failure exit codes, H5 finalization after a failed/truncated task, expert/task failure, outcome incompletion, override rejection, termination, horizon stop, and successful outcome completion with the historical strict lifecycle failed. The final provider-free suite passed 162 tests and 6 subtests. A one-interval synthetic PickCube CLI run finalized and reloaded a real canonical H5, returned exit code 1, and preserved the horizon failure reason. Its H5 and receipt are under `workspace/maintenance/p2_0_part_b_s2_a_final_20261016/cli_failure_smoke/`; the synthetic session is recorder/CLI evidence, not provider physics evidence.

Public compatibility changes are explicit but breaking. The old UIDs are rejected; root/package convenience exports for `PickCubeEnv` and `NutAssemblyEnv` were replaced by the named reference adapters; legacy camera/runtime overlays and the old grouped collect/replay defaults are not transparent aliases. The migration guide identifies these changes, but external consumer reachability cannot be proven by the repository scan. A maintainer must decide whether this belongs in the planned v1.0.1 compatibility window and approve the migration notice before integration/release.

## Current-source full-route regression

All four runs were serial CPU-only executions through the requested public `make_env` entry points. Each used source HEAD `a59840fc31f1da8aa9cbb0f7ce99f31773b91b5d`; source identity checks matched. All recordings were written to fresh ignored directories, finalized, and checked for T transitions and T+1 boundaries. No checkpoint inference, training, GPU workload, or D0-D2 campaign ran.

| Public route | Result | T / boundaries | Task and lifecycle result | H5 SHA-256 |
|---|---:|---:|---|---|
| PickCube GeoPhys, seed31, 100 Hz | PASS_RECONCILED | 151 / 152 | Task success; valid expert completion; no termination/truncation; cube lift 0.1081811 m; `grasped_cube=false` is consistent with lift-only success | `1d172bfc76ad89e082259b4949f698e027e0d138c921b7c489527b22d70124f9` |
| PickCube MuJoCo, seed31, 100 Hz | PASS | 470 / 471 | Task success; valid expert completion; no termination/truncation; cube lift 0.1060650 m | `c652dc7be2e4fdfae7a24a5e100702739026b39fa5a439f30e775e99a8bedbc3` |
| NutAssembly GeoPhys, NA-S0 seed19, 100 Hz | PASS | 2380 / 2381 | All 11 stages and retreat endpoint complete; `inserted_on_peg`, `released_nut`, `task_success`, `planned_trajectory_completed`, and `outcome_complete` true; original strict Expert result remains failed at step362 | `6eba60e3cc3a298da809bd7b6fef16ce0ff2a023f49df7a5db4acc274aeb3a18` |
| NutAssembly MuJoCo, NA-S0 seed19, 100 Hz | PASS | 2373 / 2374 | All 11 stages and retreat endpoint complete; task/outcome predicates true; original strict Expert complete, with no readiness warning | `2acec0802a48eca99319d2238c324bf8e373c3de5a69563eff3ef3b61115f627` |

The PickCube GeoPhys original wrapper reported `clock_100hz=false` because it compared cumulative floating-point time against `i * 0.01` with a one-ULP tolerance, and reported `recorded_native_interval_count=false` because it compared direct native-step calls to `5*T` on the grouped-step route. It then raised `KeyError('stage')` after H5 finalization because canonical transitions expose `expert_stage`. The same receipt records task success, expert completion, T/T+1, provider-applied controls, grouped substep instrumentation, and storage roundtrip as true. Independent `CanonicalTrajectory.validate()` and adjacent-boundary 100 Hz checks pass. The new PickCube GeoPhys H5 has exact transition and boundary object equality with the S1.5 seed31 GeoPhys record. The runner's grouped-request instrumentation check matched the expected 755 substeps across 151 control intervals; the failed JSON retained the check result but not its aggregate counter, and these native substeps are not embedded in the PickCube canonical-v0 H5. The original wrapper FAIL remains unchanged in the receipt.

PickCube MuJoCo reports 2,350 public adapter `mj_step` calls across 470 transitions. Its canonical H5 transition and boundary records are exactly equal to the S1.5 seed31 MuJoCo H5. Both providers preserve the exact selected Artifact, controller, readiness solution, reset identity, and resolved configuration identity; no checkpoint inference was run.

NutAssembly GeoPhys records 11,900 applied native substeps; MuJoCo records 11,865. Both use 2 ms physics steps and five substeps per 10 ms control action. H5 execution-v2 streaming byte-roundtrip verification passed. GeoPhys records exactly one readiness warning: `stable_height_mismatch`, `descend_to_handle`, step362, strict residual `-0.0002212406621264762 m`, against the unchanged strict tolerance `0.0001 m` and the selected admission bound `0.0003 m`. Its original strict lifecycle is `expert_complete=false`, `expert_failed=true`; the successful task outcome is separately recorded. MuJoCo has no warning and the strict Expert completes.

For each NutAssembly provider, current S2-A stage receipts and selected final physical metrics match the corresponding S1.6 records exactly. GeoPhys remains T=2380 with the same stage endpoints and measured release/insertion; MuJoCo remains T=2373 with the same stage endpoints and physical result. The task Artifact, Outcome policy, and Solution identities are unchanged. Controller and recipe identities intentionally differ because selected execution construction and arm-schedule support moved into the task-owned route: GeoPhys controller `9940cc4b…` → `0d5d3e05…`, recipe `48c7f4da…` → `97a71033…`; MuJoCo controller `5535d3a5…` → `2867280b…`, recipe `9f338b1e…` → `d829233d…`. The new source does not inherit historical qualification.

The four complete resolved configuration and source identity receipts, raw runner results, resource samples, supervisor logs, H5 files, and offline reconciliation are preserved under ignored `workspace/maintenance/p2_0_part_b_s2_a_final_20261016/`. The concise machine-readable comparison is `final_route_reconciliation.json`. A preliminary invocation with the base system Python was `NOT_RUN` because that interpreter lacked pytest; the suite then passed using the configured `geochora` environment. The separately committed CLI fix changes `record.py` from SHA-256 `0eb221ab…` to `55d9e3e2…`; its new test file SHA-256 is `4481f794…`.

Each run stayed within its 2 GiB process-tree RSS and time limit. Peak sampled RSS was approximately 627 MiB / 289 MiB / 775 MiB / 409 MiB for PickCube GeoPhys / PickCube MuJoCo / NutAssembly GeoPhys / NutAssembly MuJoCo. NutAssembly GeoPhys took 305 s against its 420 s limit. Memory and I/O PSI remained below stop thresholds; no new kernel SATA/ATA/read-write error was observed. The one-disk SATA risk and independent-backup limitation remain open.

## S2-B dependency and deletion preparation

The exact manifest remains 42 entries with status `REVIEW_REQUIRED_NO_DELETION_AUTHORIZED`: 39 `KEEP_ACTIVE_DEPENDENCY`, two `S2_B_CANDIDATE_REVIEW_REQUIRED`, and one `KEEP_CURRENT_DOCUMENTATION`. No file was deleted.

The 13 PickCube active files are `__init__.py`, `assets.py`, `candidate.py`, `canonical_semantics.py`, `default.yaml`, `readiness_solution.py`, `reference.py`, `reference_env.py`, `reset.py`, `runtime_source.py`, `solution.py`, `task.py`, and `timebase.py` under `task_env/tasks/pick_cube/`. The 26 NutAssembly active support files are `__init__.py`, `assets.py`, `canonical_artifact.py`, `canonical_initialization.json`, `canonical_reset.py`, `canonical_semantics.py`, `canonical_solution.py`, `canonical_solution_v2.py`, `canonical_source.py`, `clearance_candidate_v3.py`, `clearance_candidate_v5.py`, `default.yaml`, `guarded_authorization_candidate.py`, `guarded_authorization_candidate_v2.py`, `outcome_solution.py`, profiles `mujoco-noslip2-v1.json`, `nutassembly-nominal-v1.json`, `nutassembly-nominal-v2.json`, `nutassembly-r5-stable-grasp-10n-v1.json`, `r5-controller-planner-reference.yaml`, plus `reference.py`, `reference_env.py`, `reference_execution.py`, `solution.py`, `stable_grasp_candidate.py`, and `task.py` under `task_env/tasks/nut_assembly/`. `task_env/tasks/nut_assembly/README.md` remains current documentation.

The two exact whole-file candidates require separate caller disposition before removal:

| Candidate | Current hash; v1.0.0 recovery blob | Historical caller to resolve |
|---|---|---|
| `task_env/tasks/nut_assembly/clearance_candidate_v4.py` | `10067cbdea578c17c9a1659667e8dbb5edd081ab362b2ad16b1fcdd8a53b3f83`; `6251ac1d861ab41c14379b3fd9af7cd9e82034e3` | `task_env/diagnostics/phase1/integration/lifecycle_full.py` direct import and literal path |
| `task_env/tasks/nut_assembly/stable_grasp_reference.py` | `b51c054bb997e294d9e3605a28d86eec1dfc253589f3da1578078a64a6908324`; `e8cc8880ddf2e5342c74d8ef63a8acd6696f5bb9` | `task_env/diagnostics/phase1/integration/stable_grasp.py` direct import; frozen P1.8 reports reference its source |

Current files still mix selected dependencies with legacy symbols: PickCube `task.py` supplies task specification/constants; NutAssembly `task.py` supplies reset/geometry helpers; PickCube `solution.py` supplies plans/config inherited by the selected readiness solution; NutAssembly `solution.py` supplies selected yaw support. `_task_plans.py` retains historical grouped/stage11 factories. `diagnostics.historical_tasks.make_historical_env` remains the explicit recovery route for historical camera/render/replay callers. Do not delete these mixed files whole or copy obsolete implementations into a new active Core directory. Generic Batch/Device/Learner and Go2/static-physics code are outside S2-B.

Order for any future S2-B proposal:

1. Obtain maintainer decisions on the exact public UID/export removals, v1.0.1 compatibility/versioning, and external consumer migration notice. Static repository scans do not settle external use.
2. The trajectory record CLI result-gating prerequisite is satisfied by local commit `0f27225a…`; keep its failure/truncation tests in the S2-B regression set.
3. Extract only the selected task-owned plan/config/spec/yaw support from mixed legacy modules, preserving old/new source mappings and immutable historical identities. Rerun source, API, artifact, semantic, lifecycle, and recording tests; repeat the four full routes if execution bytes change.
4. Resolve and archive the historical-only callers of the two candidates and any recovery callers; verify immutable v1.0.0 blob identities and preserve frozen reports byte-for-byte.
5. Present an exact path/symbol deletion diff as a separate S2-B review. Remove only paths approved by the maintainer; preserve the generic Core contracts and Go2/static implementations. Run independent import/API, artifact, provider-free, full-route, recording, and historical-recovery gates after deletion.

The source-compatible shape of these old APIs is not promised; silently mapping an old UID or symbol to the selected route would alter semantics. No S2-B deletion, S3/S4/S5 work, Renderer interoperability, merge, or push is authorized by this review.
