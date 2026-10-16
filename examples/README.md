# Developer examples

These examples use the selected public task routes through `task_env.make_env`.
They are bounded developer workflows, not new provider qualifications. The
current route intersection is state-only scalar CPU execution on GeoPhys or
MuJoCo; the scripts do not enable rendering, checkpoint inference, PPO
training, or Physics × Renderer interoperability. NutAssembly advances only
through its guarded `step_expert()` route.

From the repository root, use the repository GeoPhys source path and an
environment that has the project dependencies installed. The repository does
not provide editable-install metadata:

```bash
PYTHONPATH=GeoPhys/src:. python examples/tasks/pick_cube.py --provider mujoco --seed 31
PYTHONPATH=GeoPhys/src:. python examples/tasks/nut_assembly.py --provider geophys --seed 19 --horizon 16
```

Both examples require an explicit provider, use CPU, cap the horizon at 6000
control intervals, default to a 420-second wall/CPU budget and an 8192 MiB
address-space limit, and constrain native numerical libraries to one thread.
Use `--time-limit-s` and `--memory-limit-mb` to lower those limits. The short
NutAssembly command is only a guarded construction/step smoke; unless it
finishes the full route, it reports failure and exits nonzero.

Record one selected expert route to a new H5 path:

```bash
PYTHONPATH=GeoPhys/src:. python examples/recording/record_expert.py \
  --env-id pick-cube-p16-reference-v1 --provider mujoco --seed 31 \
  --output workspace/examples/pick-cube-mujoco.h5
```

For NutAssembly, select `nut-assembly-outcome-reference-v1` and seed 19. The
recorder starts immediately after reset, records the reset boundary, executes
the task-owned expert, finalizes the canonical task recorder, checks the
stored H5 through the current reader, and verifies `T` transitions against
`T+1` boundaries. Existing provenance captures Artifact, resolved
configuration, controller/solution, provider, and source-revision identities.
The command returns nonzero when task completion, trajectory completion,
recording roundtrip, or boundary validation fails. Storage roundtrip is not a
D0 exact-replay claim.

Current supported commands are:

| Workflow | Entry point | Status |
| --- | --- | --- |
| Selected PickCube plan | `python -m task_env.script.planner --provider <geophys\|mujoco>` | Current selected P1.6 task-owned expert |
| Selected NutAssembly plan | `python -m task_env.script.trajectory.planning.nut_assembly --provider <geophys\|mujoco>` | Guarded `step_expert()` only |
| Record an expert | `python -m task_env.script.trajectory.record ...` | Current selected routes |
| Offline action conversion | `python -m task_env.script.trajectory.convert ...` | Generic H5 utility retained |
| H5 replay/inspection | `python -m task_env.script.trajectory.replay ...` | Historical replay requires explicit `--historical`; selected reexecution remains distinct |
| Merge current H5 collections | `python -m task_env.script.trajectory merge ...` | Offline utility retained |

`task_env.script.stage11`, `task_env.script.stage11_socket`, and the legacy
grouped trajectory collector are retired. Their historical source is
recoverable from the immutable refs listed in
`docs/module/task_env/p2_0_s4_5_a_source_recovery.json`; restore it in a separate
historical checkout rather than mapping an old Task UID onto a selected task.

Generic parallel/vectorization and learner adapters remain separate APIs.
These examples do not make PickCube or NutAssembly generic PPO targets. Flora
and the Renderer Registry remain within their existing declared contracts;
no physics-provider × renderer intersection was tested here. Broader learning
and rendering workflows are S4.5-B work.
