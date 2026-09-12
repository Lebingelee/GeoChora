# Camera, planning and trajectory examples

The examples below intentionally use different public boundaries:

| Goal | Public object | Command |
| --- | --- | --- |
| fixed camera observation | `CameraSpec(frame="world")` | `python -m task_env.script.camera.static` |
| object-bound camera observation | `CameraSpec(frame="site", parent=...)` | `python -m task_env.script.camera.bound` |
| task planning | `PickCubeSolution` / `NutAssemblySolution` | `python -m task_env.script.trajectory.planning.pick_cube` |
| one H5 trajectory | `TransitionRecordWrapper` | `python -m task_env.script.trajectory.record --env-id pick-cube-v1` |
| offline Panda conversion | `task_env.trajectory.processing` | `python -m task_env.script.trajectory.convert ...` |
| replay verification | `task_env.trajectory` public replay API | `python -m task_env.script.trajectory.replay ...` |

Planning scripts only call `solution.reset()`, `solution.act()`, `env.step(proposal.action)` and
`solution.observe(...)`. They do not read solver fields or reconstruct task solutions in the script.

Recording preserves the raw public observation/action tree and the H5 v2 length contract:

```text
obs/*                  T + 1
action/*               T
universal_action/*     T
reward/terminal/info   T
meta/env_cfg           resolved public config
meta/env_meta          schema, action and task metadata
```

`VectorTransitionRecorder` writes one independent single-file H5 trajectory per completed slot. It is not a
versioned aggregate batch container; aggregate vector H5 remains planned.
