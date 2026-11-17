# Trajectory recording, H5 inspection, and Camera boundaries

Record one current expert route with a fresh path:

```bash
PYTHONPATH=GeoPhys/src:. python examples/recording/record_expert.py \
  --env-id pick-cube-p16-reference-v1 --provider mujoco --seed 31 \
  --output workspace/examples/pickcube-mujoco.h5
```

The command resets through public `make_env`, starts the canonical recorder at
the reset boundary, drives the selected Solution through caller-owned
`act → step(action) → observe`, finalizes H5,
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

## One recorded interval and a UI frame

This complete scalar example associates a frame captured after the step with
that returned boundary. It writes a fresh H5 path and closes before the offline
reader; it does not claim task or Solution completion.

```python
from pathlib import Path
import numpy as np
from task_env import make_env
from task_env.environment.config import CameraSpec
from examples._common import load_recording_summary

path = Path('pick-frame.h5')
env = make_env('pick-cube-p16-reference-v1', config={
    'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu', 'deployment': 'in_process'},
    'episode': {'horizon': 10},
    'render': {'backend': 'mujoco_reference', 'width': 128, 'height': 96},
}, render_mode='rgb_array', observer_camera=CameraSpec(
    'observer', width=128, height=96, position=(.5545, 0., 2.),
    quaternion_wxyz=(2**-.5, 0., 2**-.5, 0.)))
try:
    obs, info = env.reset(seed=31)
    pose = env.state.pose_world['panda-v1/ee']
    action = np.asarray([*pose.position, *pose.quaternion_wxyz, 1.], dtype=np.float64)
    action[0] += .001
    env.start_recording(path)
    obs, reward, terminated, truncated, info = env.step(action)
    boundary = (env.state.control_step, env.state.simulation_time)
    frame = env.render()
    assert frame.shape == (96, 128, 3) and frame.dtype == np.uint8
    assert boundary == (env.state.control_step, env.state.simulation_time)
    env.finish_recording('external_stop')
finally:
    env.close()
summary = load_recording_summary(path)
assert summary['t_plus_one_valid']
print(boundary, frame.shape, summary['action_origins'])
```

This particular block is statically checked, not rerun in 7c002. The earlier
7b MuJoCo PickCube seed31 image evidence remains under its original source
identity; a fresh observer requires compatible rendering dependencies. Never
substitute that image for a different Nut or provider run.

## Camera and renderer support

`CameraSpec` and camera observation contracts remain available for Task
Artifacts that declare camera observations. UI rendering remains a separate
`UiRenderProvider` contract. The old
`task_env.script.camera.static`/`bound` scripts were tied to historical
`pick-cube-v1` construction and now fail explicitly. Selected manipulation camera acceptance is bounded by the actual source, provider, renderer and task in the current capability matrix; it is not a blanket claim. The initial 7c002 GeoPhys Nut Rasterizer attempt failed before its first frame because the canonical Scene was absent. A subsequent original Panda, GeoPhys CPU isolated-worker 128×96 observer run passed reset, one step, reset and close with the new Scene-bound Artifact; it does not qualify other cameras or visual geometry accuracy.

Historical bounded native renderer examples covered one scalar Pendulum frame through
public `make_env` and one Pendulum batch frame through `merged_scene`, both on
GeoPhys CPU with the GeoPhys rasterizer; this maintenance attempt has not rerun those render examples. The historical
`task_env.script.render_single` CLI fails explicitly and points to the current
scalar and batch examples. Renderer Registry and Flora contracts remain, but
these examples do not establish a selected manipulation × Flora intersection
or any Physics × Renderer interoperability.

`task_env.script.render_input_probe` is a standalone Taichi Forge keyboard
probe; it does not construct a TaskEnv or test physics or camera rendering.
For exact current commands and capability limits, see the
[developer workflow guide](../../../../examples/README.md).
