# Source change summary

Source checkpoints: 39479aa (live recorder), d6016e1 (versioned clock), 78eba97 (checkpoint diagnostics and strict restore validation). All on codex/p1.8-integration; no new branch/worktree or automatic push.

| Source | Reason and behavior | Compatibility | Evidence |
|---|---|---|---|
| task_env/runtime/sessions/common.py | Optional completed-application observer receives actual per-substep events | None by default; existing step() unchanged | Six independent physical trace comparisons |
| task_env/diagnostics/phase1/nutassembly_r5_architecture/tracking_worker.py | Opt-in recording lifecycle at reset, compute, substeps, post-observe and finish | Original execution unchanged without factory | Six G0 exact baseline comparisons |
| task_env/diagnostics/phase1/integration/live_recording.py | Task-local adapter supplies recipe, typed boundaries, owner snapshots and actual interval data | Advanced opt-in diagnostic module | Six live H5 roundtrips |
| task_env/trajectory/canonical/execution.py | Additive executed-interval v1/v2 H5 representation | Original CanonicalTrajectory v0 readers/contracts untouched; v1 readable | v0 fixture, six v1/v2 roundtrips, H5 negatives |
| task_env/trajectory/canonical/clock.py | Explicit integer-step and derived binary64 native-clock validation | Only v2; original one-ULP v0 remains unchanged | Six real clocks and short/long sums, fail-closed negatives |
| task_env/diagnostics/phase1/integration/replay_preparation.py | Lossless NumPy scalar codec v2; fresh-owner restoration; pre-mutation field/lifecycle validation | Experimental snapshot ABI explicitly versioned; no numerical controller change | Real P0–P8 restore and negative fixtures |
| task_env/diagnostics/phase1/integration/checkpoint_validation.py | Exact canonical replay from real captured boundaries into independent fresh owners | Infrastructure check, not formal D0/D2 campaign | Six cells, lifecycle-transition coverage |
| task_env/diagnostics/phase1/integration/native_checkpoint.py | Public provider snapshot sidecars, independent native restore and bounded comparison | Diagnostic only; no native data enters canonical policy | Native P0–P8 results and explicit limitations |

R1/PickCube, persistent R3 law/gains/caps, planner, task/asset semantics, gripper force law, thresholds and physics/provider source are unchanged. Source snapshots and proof hashes are included in the final acceptance package. No 25 N fallback, forced lift, seating or reference reset was introduced. Current shared +1 mm grasp offset remains an explicit diagnostic recipe; original registered default remains preserved.

Final diagnostic corrections: historical experiment recovery uses the final immutable bundle and verifies every selected source hash; native restore-only uses sidecar-recorded boundary index; synthetic report wording reflects live wiring. No controller/physics/profile behavior changed.


## Final recovery and audit fixes (code commit cf5f941)

| Source | Reason and old/new behavior | Compatibility | Evidence |
|---|---|---|---|
| task_env/diagnostics/phase1/integration/experiments.py | Removed the R5 selected-experiment shortcut that bypassed frozen source verification; all selected experiments now restore from the final immutable source bundle and validate their recorded source hash. | Experiment tooling only; no controller/task behavior. | Ten post-cleanup prepare-only entries pass source/config/reference checks and CLI validation. |
| task_env/diagnostics/phase1/integration/native_checkpoint.py | Restore-only now reads the actual captured control-step index from each native sidecar rather than recomputing it using a newer checkpoint selector. | Diagnostic restore selection only; native state/controller unchanged. | Existing native checkpoint restore evidence at all rates; source index association follows each captured NPZ. |
| task_env/diagnostics/phase1/integration/readiness_synthetic.py | Corrected the synthetic report limitation to say that the synthetic test itself does not validate live recorder/native restore, which have separate live evidence. | Report wording only. | `synthetic_final/validation.json` PASS; 12,204 positive and 9 negative checks. |

