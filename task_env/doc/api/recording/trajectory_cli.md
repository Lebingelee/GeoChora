# Trajectory CLI

The grouped historical collector was retired. The current selected expert
recorder uses the explicit task UID, provider, and a fresh output path:

```bash
PYTHONPATH=GeoPhys/src:. python -m task_env.script.trajectory.record \
  --env-id pick-cube-p16-reference-v1 --provider mujoco --seed 31 \
  --output workspace/examples/pickcube-mujoco.h5
```

For NutAssembly, select `nut-assembly-outcome-reference-v1` and seed 19. The
CLI advances through the selected expert route and returns nonzero unless the
required task and expert completion gates pass. It finalizes the existing
canonical recorder even when execution fails or truncates.

Inspect a finalized canonical H5 file offline with:

```bash
PYTHONPATH=GeoPhys/src:. python examples/recording/inspect_h5.py \
  --input workspace/examples/pickcube-mujoco.h5
```

The inspector validates the current canonical schema, H5 payload integrity,
provenance summary, and T+1 boundary count. It does not reexecute the task or
claim D0 reconstruction. Storage validity and task completion are separate
results.

The existing Panda/controller offline utilities remain:

```bash
PYTHONPATH=GeoPhys/src:. python -m task_env.script.trajectory.convert \
  --input source.h5 --output converted.h5 \
  --target-mode absolute_pose --target-reference world

PYTHONPATH=GeoPhys/src:. python -m task_env.script.trajectory.replay \
  --trajectory legacy.h5 --historical
```

Legacy replay requires the explicit `--historical` flag. Current-source
reexecution is a separate `--selected-reexecute` operation and requires a
fresh output path; neither route is the same as offline H5 validation.
