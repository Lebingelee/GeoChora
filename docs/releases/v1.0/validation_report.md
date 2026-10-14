# v1.0 release validation

Snapshot date: 2026-10-14. Validation is bound to the source manifest and the exact candidate tests below. These checks provide release integrity and bounded smoke evidence; they do not create a new Human qualification decision.

## Completed checks

| Check | Result | Boundary |
|---|---|---|
| P1.1 provider-free Task Artifact contract detector | PASS, 30 checks | Contract/readiness shape only |
| Synthetic readiness contract | PASS, 12,204 positive checks | Synthetic only; no formal D0/D1/D2, provider checkpoint restore, or mechanical competence claim |
| P1.8 focused regression | PASS, 66 tests | Lifecycle, guarded transition, diagnostic isolation, replay contracts, and streaming recorder; exact historical result is hash-indexed |
| GeoPhys Taichi CPU PickCube expert smoke | PASS, task_success true after 93 transitions; cube lift 0.106213 m | Seed 31, horizon 220; no camera render; one retained MJCF `extension.light` semantic emitted a warning and zero semantics were rejected |
| Additional `checkpoint_validation.py` replay attempts | NOT PASSED | The selected GeoPhys FULL/diagnostic H5 inputs did not contain the required `verify_lift` stage. The selected MuJoCo guarded-candidate H5 input diverged at boundary 447 with `owner update`. These were exploratory infrastructure checks and are not qualification evidence. |
| P1.6 archive recovery | PASS, 441/441 member hashes | Local archive only; off-host backup not verified |
| P1.8 evidence archive inspection | PASS for recorded manifest and sampled restore checks | Local archive only; Git bundle history has a missing historical parent object; exact source-tree snapshots retained |
| Historical Human decision copies | PASS, seven indexed SHA-256 matches | Original bounded decisions only |

## Commands

Run from the repository root with the declared geochora environment and `PYTHONPATH=GeoPhys/src:.`:

```bash
python -m task_env.diagnostics.phase1.p1_1_contracts --output <fresh-output-directory>
python -m task_env.diagnostics.phase1.integration.readiness_synthetic --output <fresh-output-directory>
python -m pytest \
  task_env/diagnostics/phase1/integration/test_diagnostic_shadow.py \
  task_env/diagnostics/phase1/integration/test_diagnostic_cross_provider_replay.py \
  task_env/diagnostics/phase1/integration/test_solution_lifecycle.py \
  task_env/diagnostics/phase1/integration/test_guarded_transition.py \
  task_env/diagnostics/phase1/integration/test_recording_streaming.py \
  task_env/diagnostics/phase1/integration/test_cross_provider_full_context.py -q
python -m task_env.script.trajectory.planning.pick_cube --backend cpu --horizon 220 --seed 31
```

The focused P1.8 suite was rerun on this candidate and returned 66 passed. The P1.1 detector and synthetic readiness check were run on this candidate as well. The PickCube smoke completed on GeoPhys Taichi CPU and printed the retained `extension.light` warning described above.

## Release publication gates

Publication readiness requires this release package to pass JSON/YAML parsing, local Markdown link checks, diff whitespace and sensitive/large-file review; then normal publication must make `main` point to the release commit, the annotated `v1.0.0` tag peel to that commit, and `develop` start at that same commit. Exact remote readback and any cleanup exceptions are written to the local/off-repository publication receipt after publication.

The checkpoint-validation attempts used local-only 100 Hz NutAssembly recordings from the 2026-10-14 final diagnostic and guarded-transition workspaces. The script requires its `verify_lift` checkpoint stage; the GeoPhys records lacked that stage and the MuJoCo record reached the owner-update mismatch at boundary 447. No positive checkpoint-validation claim is made. These attempts do not change the diagnostic and development classifications in the capability matrix.
