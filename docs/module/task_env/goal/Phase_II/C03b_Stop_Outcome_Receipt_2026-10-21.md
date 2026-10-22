# C03b Stop / EpisodeOutcome receipt (2026-10-21)

## Scope and starting state

Implemented sequence 27 / C03b after the local C02b checkpoint `d99941c` on branch `codex/phase-ii-c03b`.
The checkpoint contains the preceding Position S1/S2/H5 work. C03b changes in this receipt remain uncommitted and
unpushed. No frozen branch, GeoPhys pin, C02b Artifact, or release reference was moved.

The implementation reuses `SingleTaskLifecycleAdapter`, `BaseTaskEnv`, the explicit
`SelectedReferenceEnv` Position candidate, `TransitionRecorder`, `TransitionRecordWrapper`, and Generic H5 v3.
It adds no lifecycle manager, Environment/Recorder/Provider framework, or new control system.

## Contract implemented

- `EpisodeTerminationPolicyV1` is an optional `TaskDefinitionBase` hook. The default keeps success/failure terminal,
  external Stop and horizon truncated with bootstrap allowed, and terminal outcomes non-bootstrapable. Existing
  Gymnasium step flags are preserved, including the existing simultaneous `terminated=True, truncated=True` case.
  The final Outcome prioritizes task terminal in that case without changing the returned tuple.
- `env.stop(reason)` returns `EpisodeEndV1`: one ordered `episode_ended` BoundaryEvent plus one final
  `EpisodeOutcomeV1` at the last complete public boundary. Stop makes no Controller call, control application, or
  physics step. Repeated Stop returns the cached result. Stop before reset and Stop after close reject.
- Generic reset first finalizes an active prior episode as `external_stop` with requested reason `reset`, then returns
  that prior result in new reset info as `previous_episode_end_v1`. Close finalizes an active lifecycle before
  Runtime teardown. An execution fault yields an `execution_fault` outcome, truncated without bootstrap.
- If BaseTaskEnv result formatting fails after physics advanced, its lifecycle boundary is revoked before fault
  closure. The fault receipt retains the actual after-clock; Stop uses the preceding boundary because the failed
  public call returned no transition. The Position candidate uses its last completely returned/recorded boundary
  for the same distinction.
- Position success remains observable without ending Position control. Old selected `production-r1` behavior,
  identity, and required force feedback are unchanged; its Stop route explicitly reports unavailable.
- Recorder finalization validates Event/Outcome identity, final boundary, reason, flags, sequence, and T/T+1 before
  freezing. It runs once. The wrapper preserves v2 behavior but rejects Stop/close during active v2 recording because
  v2 cannot persist its event/outcome/bootstrap. V3 requires a declared structured-control environment and one typed
  control per real step. V3 manual `end_record`, active reset, vector Stop, and unsupported environments fail closed.
- `load_structured_training_episode_h5()` composes exact single-writer action projection with raw per-transition
  Gymnasium flags, final EpisodeOutcome, and final bootstrap policy. It never rewrites already-returned flags.

## S1 checks

Final focused command:

```text
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=GeoPhys/src:. \
  /home/lly/miniconda3/envs/geochora/bin/python -m pytest -q -p no:cacheprovider \
  task_env/diagnostics/tasks/test_phase_ii_c03b_stop_outcome.py \
  task_env/diagnostics/tasks/test_phase_ii_c05a_structured_recording.py \
  task_env/diagnostics/tasks/test_phase_ii_c03a_fault_lifecycle.py \
  task_env/diagnostics/tasks/test_phase_ii_c02b_position_execution_h5.py \
  task_env/diagnostics/tasks/test_selected_consumers.py
```

Result: **78 passed**, one upstream Taichi `locale.getdefaultlocale` deprecation warning. It covers T=0 and repeated
Stop, reset-before-Stop, generic and Position close finalization exactly once, terminal/horizon outcome distinctions, legacy flag
preservation, reset finalization, fault Stop, v2 wrapper mutation-free rejection, v3 declared-control checks,
Event/Outcome finalization and training reader behavior. The real Pendulum C03a regression and current selected
consumers were included.

## S2 provider evidence

The probe was run in two independent CPU processes with the same fixed Position candidate/sample:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=GeoPhys/src:. python -m task_env.diagnostics.tasks.c03b_stop_s2_probe \
  --provider geophys --workspace workspace/maintenance/c03b_stop_20261021/final_run
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=GeoPhys/src:. python -m task_env.diagnostics.tasks.c03b_stop_s2_probe \
  --provider mujoco --workspace workspace/maintenance/c03b_stop_20261021/final_run
```

Both returned `PASS_BOUNDED_STOP_OUTCOME_S2` for the Position candidate. Profile identity was
`panda-main/position-servo-v1`; Controller identity was
`3c8fae3e65515f4a62a0c2ba9c5b09d11e8b67ff724642948371b2539050836e`; source closure digest was
`aa4ca97bbe3c61b30752ba0dedc6c88a24394f03fe1b53519052d460ff9abc47`.

| Probe | GeoPhys CPU | MuJoCo CPU |
| --- | --- | --- |
| T=0 Stop | clock unchanged; T=0/T+1=0/1; Event/Outcome disk readback passed | same |
| One returned Position step, then external Stop | clock unchanged across Stop; T/T+1=1/2; step flags remain false/false; final Outcome truncates and permits bootstrap; task success remains true | same |
| Stop / post-Stop refusal control calls | compute/apply/step all zero | compute/apply/step all zero |
| Injected append fault after a real physical step | fault reports advanced 1/0.01 s; Stop stays at published boundary 0; v3 disk readback T/T+1=0/1; bootstrap false | same |
| Generic scalar Pendulum | tested on GeoPhys CPU, below | `NOT_ADMITTED` |

The fault case intentionally separates a completed physical interval from an uncommitted transition: physical clock
was control step 1 / 10 ms, but H5 contains only the reset observation and no transition. The Event carries both the
last published boundary clock and the fault's observed Runtime clock.

Generic Pendulum was tested only on its current GeoPhys CPU `BaseTaskEnv` route. T=0 and T=1 Stop left control and
simulation clocks unchanged, reset returned the preceding EpisodeEnd, repeated Stop was idempotent, and step after
Stop rejected. Its existing Gym v2 recording wrapper rejected active Stop before forwarding it. Current generic
`ExecutionPlan` only admits GeoPhys, so MuJoCo Pendulum was not run and is explicitly `NOT_ADMITTED`.

V3 wrapper success was checked with a typed contract fixture; no real generic TaskEnv currently declares
`supports_structured_control_recording=True`. Position's real v3 evidence uses its existing direct recorder. V2
active Stop/close and vector Stop remain unsupported and explicit.

The S2 receipts and H5 files are ignored local evidence in
`workspace/maintenance/c03b_stop_20261021/final_run/{geophys,mujoco}/`. Earlier harness attempts that passed
provider/backend as forbidden generic TaskEnv overlays, reused an existing output path, or sampled an out-of-space
wrapper action were corrected; none is counted as a pass or a supported route.

## Not run and status

Not run at this receipt's issuance: vectorized Stop semantics, every learner/algorithm integration, a real generic v3 wrapper provider,
MuJoCo generic Pendulum, NutAssembly R3 Guard, dual Entity/Robot Assembly, R1 force refresh, complete C02b, and
Phase II qualification. C02b was **BLOCKED** then; its current declared-intersection bounded exit is recorded in the [P99 readiness review](P99_Readiness_Review_2026-10-22.md). This bounded C03b receipt does not mark Phase II complete.

The TaskEnv module Skill static checker and `git diff --check` pass for this update. C03b changes remain uncommitted;
no push or merge was performed.
