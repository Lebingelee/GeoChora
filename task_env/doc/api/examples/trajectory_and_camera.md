# Trajectory recording, H5 inspection, and Camera boundaries

Record one current expert route with a fresh path:

```bash
PYTHONPATH=GeoPhys/src:. python examples/recording/record_expert.py \
  --env-id pick-cube-p16-reference-v1 --provider mujoco --seed 31 \
  --output workspace/examples/pickcube-mujoco.h5
```

The command resets through public `make_env`, starts the canonical recorder at
the reset boundary, steps only the selected task-owned expert, finalizes H5,
and checks the logical/numeric storage representation and `T`/`T+1` counts.
It returns nonzero if the task or expert is incomplete or the recording check
fails. Task outcome, expert lifecycle, and recording validity are reported as
separate fields.

Inspect the completed H5 offline without constructing a provider:

```bash
PYTHONPATH=GeoPhys/src:. python examples/recording/inspect_h5.py \
  --input workspace/examples/pickcube-mujoco.h5
```

This uses the existing canonical reader and does not define another H5
schema. It validates the stored representation and T+1 boundary count; it
does not reexecute the task, reconstruct D0, or award task qualification.

The generic Panda/controller `task_env.script.trajectory.convert` path remains
available for supported action conversion. `trajectory.replay` requires
explicit `--historical` for legacy H5 replay. The separate
`--selected-reexecute` route requires a fresh output and is not D0 reconstruction.

## Camera and renderer support

`CameraSpec` and camera observation contracts remain available for Task
Artifacts that declare camera observations. UI rendering remains a separate
`UiRenderProvider` contract. The old
`task_env.script.camera.static`/`bound` scripts were tied to historical
`pick-cube-v1` construction and now fail explicitly. The selected manipulation
routes have no camera acceptance claim.

The bounded native renderer examples cover one scalar Pendulum frame through
public `make_env` and one Pendulum batch frame through `merged_scene`, both on
GeoPhys CPU with the GeoPhys rasterizer. The historical
`task_env.script.render_single` CLI fails explicitly and points to the current
scalar and batch examples. Renderer Registry and Flora contracts remain, but
these examples do not establish a selected manipulation × Flora intersection
or any Physics × Renderer interoperability.

`task_env.script.render_input_probe` is a standalone Taichi Forge keyboard
probe; it does not construct a TaskEnv or test physics or camera rendering.
For exact current commands and capability limits, see the
[developer workflow guide](../../../../examples/README.md).
