# GeoChora developer workflows

These commands use the current TaskEnv APIs and selected task routes. The
repository-root examples apply Linux-oriented per-process bounds; existing
TaskEnv CLIs and interactive probes do not all apply those bounds themselves.
All results here are smoke checks, not new provider, task, learner, or renderer
qualifications. Run them from the repository root in the GeoChora environment;
the repository has no editable-install metadata, so set `PYTHONPATH` explicitly.

```bash
PYTHONPATH=GeoPhys/src:. python examples/tasks/pick_cube.py --provider mujoco --seed 31
PYTHONPATH=GeoPhys/src:. python examples/tasks/nut_assembly.py --provider geophys --seed 19
```

The task examples require an explicit `geophys` or `mujoco` provider and use
CPU. PickCube selects `pick-cube-p16-reference-v1`; NutAssembly selects
`nut-assembly-outcome-reference-v1` and advances only through guarded
`step_expert()`. Both report task success separately from expert completion.
NutAssembly must complete its planned stages and retreat to return success; a
short horizon is an incomplete run and exits nonzero.

The Linux-oriented time/address-space options apply these scopes:
`--time-limit-s` sets a per-process CPU-time limit and a real-time alarm in the
coordinating process; `--address-space-limit-mb` applies per-process
`RLIMIT_AS`. The older `--memory-limit-mb` spelling remains an alias.
`RLIMIT_AS` limits virtual address space; it is not an RSS or aggregate
process-tree memory cap. Native BLAS/OpenMP thread counts are set to one before
runtime imports.

## Workflow matrix

| Workflow | Command | Current scope and result |
| --- | --- | --- |
| Scalar task construction and expert rollout | `PYTHONPATH=GeoPhys/src:. python examples/tasks/pick_cube.py --provider mujoco --seed 31` | Selected PickCube P1.6 expert, scalar CPU; bounded MuJoCo example completed successfully. |
| Guarded task rollout | `PYTHONPATH=GeoPhys/src:. python examples/tasks/nut_assembly.py --provider geophys --seed 19` | This CLI uses the retained `step_expert()` path; incomplete route exits nonzero. Separately, the task-owned external Solution has bounded MuJoCo CPU S2/S3 and a diagnostic GeoPhys CPU/CUDA × 100/500 Hz S2/S3 comparison. The GeoPhys matrix deliberately reads the public host snapshot each native step and does not grant general capability; see the [C05c comparison](../docs/module/task_env/goal/Phase_II/C05c_GeoPhys_Gripper_Cadence_Comparison_2026-10-22.md). |
| Canonical expert recording | `PYTHONPATH=GeoPhys/src:. python examples/recording/record_expert.py --env-id pick-cube-p16-reference-v1 --provider mujoco --seed 31 --output workspace/examples/pickcube-mujoco.h5` | Requires a fresh output path; finalizes the existing canonical H5 recorder and checks transitions, T+1 boundaries, provenance, and storage roundtrip. |
| Offline H5 inspection | `PYTHONPATH=GeoPhys/src:. python examples/recording/inspect_h5.py --input workspace/examples/pickcube-mujoco.h5` | Reads the existing canonical schema and validates logical/numeric integrity and T+1 boundaries. It does not replay the task or claim D0. |
| Generic batch environment smoke | `PYTHONPATH=GeoPhys/src:. python -m task_env.script.env.parallel_inline --env-id pendulum-v1 --backend cpu --num-env 2 --steps 1` | Existing generic `make_parallel_env` Pendulum path; not a task or learner qualification. |
| SB3 learning smoke | `PYTHONPATH=GeoPhys/src:. python examples/learning/pendulum_sb3.py --output-dir workspace/maintenance/pendulum-sb3-run-01` | One CPU PPO update on Pendulum/`merged_scene`, delegating to the existing SB3 runner. Pick a fresh output directory. This is a wiring smoke, not training qualification or convergence evidence. |
| Current native rendering smoke | `PYTHONPATH=GeoPhys/src:. python examples/rendering/pendulum_parallel_rgb.py` | One Pendulum batch step and RGB frame on GeoPhys CPU/`merged_scene`/rasterizer. This does not exercise Flora or Physics × Renderer interoperability. |
| Current scalar rendering smoke | `PYTHONPATH=GeoPhys/src:. python examples/rendering/pendulum_single_rgb.py` | One Pendulum scalar TaskEnv step and RGB frame on GeoPhys CPU/rasterizer. This does not exercise Flora or Physics × Renderer interoperability. |
| Advanced current parallel render CLI | `PYTHONPATH=GeoPhys/src:. python -m task_env.script.render_parallel --env-id pendulum-v1 --num-env 1 --parallel-render-num 1 --mode rgb_array --backend cpu --render-backend rasterizer --width 64 --height 48 --steps 1 --sleep 0` | Same narrow GeoPhys/Pendulum route; human display and other provider/renderer combinations are unverified. |
| Standalone window-input probe | `PYTHONPATH=GeoPhys/src:. python -m task_env.script.render_input_probe --arch cpu` | Taichi Forge keyboard/window probe only; it does not construct a TaskEnv or test a physics-renderer intersection. |
| Generic RSL-RL entry point | `PYTHONPATH=GeoPhys/src:. python -m task_env.script.rl.rsl_ppo --help` | `--env-id` is required. Admission also requires a registered homogeneous task and compatible learner contracts; no Go2 replacement is selected. |

H5 storage validation and a successful expert lifecycle are separate facts.
H5 equality or roundtrip does not establish D0 reconstruction, historical
qualification, or a Judge decision. The recording command preserves task,
controller, solution, provider, source, and resolved-configuration provenance
through the existing recorder.

The current executable renderer intersections are intentionally narrow:
Pendulum × GeoPhys CPU × scalar TaskEnv × rasterizer RGB and Pendulum × GeoPhys
CPU × merged-scene batch × rasterizer RGB. Both have a bounded single-frame
smoke. The Renderer Registry, Flora, Camera, and rasterizer contracts remain
available within their declared boundaries. No selected manipulation task ×
Flora route has been established. The historical `render_single` CLI and
PickCube camera-observation/lighting probes fail explicitly; the scalar
Pendulum example uses current public `make_env`. See the [migration note](../task_env/doc/api/appendix/migration.md).

Generic trajectory conversion, explicit historical replay, selected-source
reexecution, parallel environment, SB3, and RSL-RL APIs remain separate routes.
Do not map retired task IDs to current task behavior. The S4.5-B source-recovery
manifest records retired script identities and their exact recovery blobs.
