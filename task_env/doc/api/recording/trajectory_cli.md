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
Selected reexecution uses the caller-owned Solution through
`act → env.step(action) → observe` and checks recorded binding source
identities when present. When a task source inventory is recorded, its paths
and hashes must match the currently constructed task inventory exactly.
Legacy Nut recordings made through `step_expert()`
have a different diagnostic contract and are rejected by this reexecution
route; their original files remain historical evidence.

## Ownership and limits

Run these commands from the repository root with the existing Core interpreter,
matching `GeoPhys/src`, installed assets, and a fresh output path. `record`
owns the explicit caller loop and the output file; `inspect` is offline and
does not contact a provider. Exit status and the printed task outcome, Solution
completion and storage result must be read separately. Parameters above are
the actual CLI options; provider support is limited to its declared route.

D0 asks whether the full state can be reconstructed, D1 replays frozen native
controls, and D2 replays requested actions while recomputing control. A valid H5
or an ordinary `inspect` is none of those by itself. The selected source-bound
reexecution checks identities and runs a current caller; it does not silently
upgrade historical evidence. Unsupported/retired inputs remain errors rather
than aliases to a new task. See [trajectory contract](trajectory_contract.md)
and [H5 schema](h5_schema.md) before choosing an output or reader.

[Trajectory command modules](../../../script/trajectory) provide these CLI entry points; the [trajectory package](../../../trajectory) owns their data contracts.
