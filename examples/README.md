# GeoChora developer workflows

These commands use the current TaskEnv APIs and selected task routes. Some examples apply Linux-oriented per-process bounds; the scalar launcher, existing TaskEnv CLIs and interactive probes do not all apply those bounds. All results here are smoke checks, not new provider, task, learner, or renderer qualifications. Run them from the repository root in the GeoChora environment; the repository has no editable-install metadata, so set `PYTHONPATH` explicitly.

For the guided sequence (install → state-only → rendering → device batch → authoring → controllers → API), start at the [v2.1.1 learning guides](../docs/module/task_env/v2.1.1/guides/README.md). For a scalar first step with explicit Python and GeoPhys paths, see the [installation and launch guide](../docs/module/task_env/v2.1.1/guides/installation-and-start.md) and `examples/start.py`. Its argument routing has been checked offline; the launcher has not been validated with a new native run in this maintenance.

```bash
PYTHONPATH=GeoPhys/src:. python examples/tasks/pick_cube.py --provider mujoco --execution direct --seed 31
PYTHONPATH=GeoPhys/src:. python examples/tasks/pick_cube.py --provider geophys --execution direct --seed 31
OMNI_KIT_ACCEPT_EULA=YES ISAAC_SIM_PYTHON=/path/to/isaac-python PYTHONPATH=GeoPhys/src:. python examples/tasks/pick_cube.py --provider isaacsim --seed 31
PYTHONPATH=GeoPhys/src:. python examples/tasks/pick_cube.py --provider mujoco --execution harness --seed 31 --horizon 1000 --controller-profile r3_continuous_v1 --harness-output-dir workspace/examples/pick_cube/harness-mujoco-seed31-run01
PYTHONPATH=GeoPhys/src:. python examples/tasks/pick_cube.py --provider geophys --execution harness --seed 31 --horizon 1000 --controller-profile r3_continuous_v1 --harness-output-dir workspace/examples/pick_cube/harness-geophys-seed31-run01
OMNI_KIT_ACCEPT_EULA=YES PYTHONPATH=GeoPhys/src:. python examples/tasks/pick_cube.py --provider isaacsim --execution harness --seed 31 --horizon 1000 --controller-profile r3_continuous_v1 --source-delivery-manifest workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/isaac_usd_v2/delivery_manifest.json --harness-output-dir workspace/examples/pick_cube/harness-isaac-seed31-run01
PYTHONPATH=GeoPhys/src:. python examples/tasks/pick_cube.py --provider genesis --execution harness --seed 31 --horizon 1000 --controller-profile r3_continuous_v1 --harness-output-dir workspace/examples/pick_cube/harness-genesis-seed31-run01
PYTHONPATH=GeoPhys/src:. python examples/tasks/pick_cube.py --provider sapien --execution harness --seed 31 --horizon 1000 --controller-profile r3_continuous_v1 --harness-output-dir workspace/examples/pick_cube/harness-sapien-seed31-run01
PYTHONPATH=GeoPhys/src:. python examples/tasks/nut_assembly.py --provider geophys --seed 19
```

PickCube selects `pick-cube-p16-reference-v1`. `--execution direct` calls the
public `make_env` example; `--execution harness` uses the versioned built-in
Harness contract and the same Core task owner. The direct Isaac route uses the
installed USD asset, CUDA PhysX and the selected Isaac interpreter; the
versioned F06 Harness remains a separate route requiring its frozen manifest.
The direct Isaac example does not set an address-space or CPU-time limit;
use external process-tree resource supervision when one is required. Genesis/SAPIEN Harness
commands write `NOT_RUN_DEPENDENCY` without starting a worker when their engine
module is absent, and report `UNSUPPORTED_CAPABILITY` when the Core provider
manifest is unavailable. Use fresh output directories. NutAssembly selects
`nut-assembly-outcome-reference-v1`; this example owns the Solution and calls
`act()`, `env.step(action)`, then `observe()`. The action carries the required
source boundary and controller request; arbitrary arrays are not admitted. Both examples report task success separately from expert completion.
NutAssembly must complete its planned stages and retreat to return success; a
short horizon is an incomplete run and exits nonzero.

The Linux-oriented time/address-space options apply these scopes:
`--time-limit-s` sets a per-process CPU-time limit and a real-time alarm in the
coordinating process; `--address-space-limit-mb` applies per-process
`RLIMIT_AS`. The older `--memory-limit-mb` spelling remains an alias.
For direct Isaac, `--memory-limit-mb` is rejected and neither `RLIMIT_AS` nor
`RLIMIT_CPU` is set by the example; the real-time alarm still applies to the
coordinator, and any limits inherited from the caller remain in force. On the CPU routes, `RLIMIT_AS` limits virtual address space; it is not an RSS or aggregate
process-tree memory cap. Native BLAS/OpenMP thread counts are set to one before
runtime imports.

The current public entry points are:

| Task or workflow | Entry | Scope |
| --- | --- | --- |
| PickCube | `examples/tasks/pick_cube.py --provider mujoco` | Caller-owned R3 Solution via `make_env`; Isaac CUDA uses the direct route shown above. |
| NutAssembly | `examples/tasks/nut_assembly.py --provider mujoco` | Caller-owned Outcome Solution via `make_env`. |
| Pendulum | `examples/tasks/scalar_step.py --uid pendulum-v1` | One scalar GeoPhys CPU transition via `make_env`. |
| Two-wheel balance | `examples/tasks/scalar_step.py --uid two-wheel-balance-v1` | One scalar GeoPhys CPU transition via `make_env`. |
| Inline or YAML scalar config | `python -m task_env.script.env.single_inline` or `single_from_file` | Formal configuration and `make_env`; mapping/YAML equivalence is shown in the installation guide. |
| Recording and trajectory | `examples/recording/record_expert.py` and `task_env.script.trajectory.planning` | Selected task Solution and recorder; successful storage and task completion are separate. |
| Scalar camera/render example | `examples/rendering/pendulum_single_rgb.py` | Existing bounded Pendulum rasterizer example; retired `task_env.script.camera.static` and `.bound` are historical and report retirement. |
| Device batch, Pendulum | `examples/parallel/pendulum_device.py` | G06 canonical CUDA device route for `pendulum-v1` with `--provider mujoco_warp\|geophys\|isaacsim`; see the [device guide](../docs/module/task_env/v2.1.1/guides/quickstart-device-batch.md). |
| Device batch, PickCube | `examples/parallel/pick_cube_device.py` | G06 canonical CUDA device route with explicit `panda-direct-effort-v1`; GeoPhys requires `--geophys-contact-mode discrete --geophys-contact-iterations 32`. |
| Device whole-batch switch | `examples/parallel/reconfigure_device.py` | Accepted representative edge Isaac ↔ MuJoCo Warp for both tasks; GeoPhys cross-provider switching is not admitted. |

For a small new-task declaration, see [`declared_marker.py`](tasks/declared_marker.py).
It declares the Panda Robot and R1 profile, a source snapshot and named task
bodies, then uses the common composition and Controller binding. In 7c002,
MuJoCo CPU marker-005 completed reset, a nonzero step, recording, another reset
and close; the same H5 was independently read as 1 transition and 2 boundaries.
This bounded execution awaits independent review and does not imply other
providers or arbitrary assets are supported. See the [authoring guide](../docs/module/task_env/v2.1.1/guides/authoring-scenes-assets-robots.md).

## Workflow matrix

| Workflow | Command | Current scope and result |
| --- | --- | --- |
| Scalar task construction and expert rollout | `PYTHONPATH=GeoPhys/src:. python examples/tasks/pick_cube.py --provider mujoco --execution direct --seed 31` | Direct public `make_env` example; the F06 Harness route is a separately versioned mode below. |
| Direct PickCube on Isaac Sim | `OMNI_KIT_ACCEPT_EULA=YES ISAAC_SIM_PYTHON=/path/to/isaac-python PYTHONPATH=GeoPhys/src:. python examples/tasks/pick_cube.py --provider isaacsim --seed 31` | Uses the installed USD asset via public configuration. The changed route has offline routing checks only; native validation remains open. |
| F06 built-in Harness, MuJoCo CPU | `PYTHONPATH=GeoPhys/src:. python examples/tasks/pick_cube.py --provider mujoco --execution harness --seed 31 --horizon 1000 --controller-profile r3_continuous_v1 --harness-output-dir workspace/examples/pick_cube/harness-mujoco-seed31-run01` | Compiles the versioned built-in PickCube example and calls the same public Core task owner; runtime validity and task outcome are separate. |
| F06 built-in Harness, GeoPhys CPU | `PYTHONPATH=GeoPhys/src:. python examples/tasks/pick_cube.py --provider geophys --execution harness --seed 31 --horizon 1000 --controller-profile r3_continuous_v1 --harness-output-dir workspace/examples/pick_cube/harness-geophys-seed31-run01` | Same Core task owner and R3 profile; runtime validity and task outcome are reported separately. |
| F06 PickCube on Isaac Sim | `OMNI_KIT_ACCEPT_EULA=YES PYTHONPATH=GeoPhys/src:. python examples/tasks/pick_cube.py --provider isaacsim --execution harness --seed 31 --horizon 1000 --controller-profile r3_continuous_v1 --source-delivery-manifest workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/isaac_usd_v2/delivery_manifest.json --harness-output-dir workspace/examples/pick_cube/harness-isaac-seed31-run01` | After accepting the NVIDIA Omniverse EULA, passes the non-interactive acceptance setting to the supervised CUDA PhysX worker; task outcome remains separate from runtime evidence. |
| Optional Genesis/SAPIEN preflight | Same command with `--provider genesis` or `--provider sapien` and `--execution harness` | Optional only. Missing engine dependency is recorded as `NOT_RUN_DEPENDENCY` without a worker; provider manifest gaps are `UNSUPPORTED_CAPABILITY`. |
| Guarded task rollout | `PYTHONPATH=GeoPhys/src:. python examples/tasks/nut_assembly.py --provider geophys --seed 19` | Caller-owned `act → step(action) → observe`; incomplete route exits nonzero. Nut MuJoCo/GeoPhys seed19 complete runs have [bounded same-run evidence](../docs/module/task_env/v2.1.1/maintenance/reviews/20261113_e11_e16_u4_joint_completion.md), each at its frozen source/configuration; this is not a full run at every later HEAD or general provider qualification. |
| Canonical expert recording | `PYTHONPATH=GeoPhys/src:. python examples/recording/record_expert.py --env-id pick-cube-p16-reference-v1 --provider mujoco --seed 31 --output workspace/examples/pickcube-mujoco.h5` | Requires a fresh output path; finalizes the existing canonical H5 recorder and checks transitions, T+1 boundaries, provenance, and storage roundtrip. |
| Offline H5 inspection | `PYTHONPATH=GeoPhys/src:. python examples/recording/inspect_h5.py --input workspace/examples/pickcube-mujoco.h5` | Reads the existing canonical schema and validates logical/numeric integrity and T+1 boundaries. It does not replay the task or claim D0. |
| Generic batch environment | `task_env.make_parallel_env(..., execution='device')` | G06 has bounded acceptance for Pendulum/PickCube × `mujoco_warp`/`geophys`/`isaacsim`; the generic SB3 `remote`/`local` wrappers are a different contract. Nut batch, R3 batch, heterogeneous rows and arbitrary sources are not admitted. |
| SB3 learning example | `examples/learning/pendulum_sb3.py` | Its historical Pendulum batch dependency is not the accepted device contract. This does not establish training support. |
| Parallel rendering example | `examples/rendering/pendulum_parallel_rgb.py` | Historical batch-render smoke; current device windows/cameras are shown by the `examples/parallel/*_device.py` `--window`/`--sensor` flags. No general batch-render qualification follows. |
| Scalar observer example | `PYTHONPATH=GeoPhys/src:. python examples/rendering/pendulum_single_rgb.py` | Declares GeoPhys CPU and an observer CameraSpec through the formal scalar factory. The migrated caller has guarded configuration/fake-loop checks; native RGB was not rerun for this migration. Running the command requests one real frame and step; no Flora or cross-renderer claim follows. |
| Advanced parallel render CLI | `python -m task_env.script.render_parallel --help` | Component-batch render CLI; it is not the accepted G06 device route. Use the `examples/parallel/*_device.py` flags for the tested device windows/cameras. |
| Standalone window-input probe | `PYTHONPATH=GeoPhys/src:. python -m task_env.script.render_input_probe --arch cpu` | Taichi Forge keyboard/window probe only; it does not construct a TaskEnv or test a physics-renderer intersection. |
| Generic RSL-RL entry point | `PYTHONPATH=GeoPhys/src:. python -m task_env.script.rl.rsl_ppo --help` | `--env-id` is required. Admission also requires a registered homogeneous task and compatible learner contracts; no Go2 replacement is selected. |

H5 storage validation and a successful expert lifecycle are separate facts.
H5 equality or roundtrip does not establish D0 reconstruction, historical
qualification, or a Judge decision. The recording command preserves task,
controller, solution, provider, source, and resolved-configuration provenance
through the existing recorder.

The scalar observer example requests Pendulum × GeoPhys CPU × scalar TaskEnv
× rasterizer RGB. Its current caller/configuration checks do not establish new
pixel evidence. The historical Pendulum batch-render smoke predates the
formal task migration and does not establish the G06 device render result;
current device windows/cameras are exercised by `examples/parallel/*_device.py`.
The Renderer Registry, Flora, Camera, and rasterizer contracts remain
available within their declared boundaries. No selected manipulation task ×
Flora route has been established. The historical `render_single` CLI and
PickCube camera-observation/lighting probes fail explicitly; the scalar
Pendulum example uses current public `make_env`. See the [migration note](../task_env/doc/api/appendix/migration.md).

Generic trajectory conversion, explicit historical replay, selected-source
reexecution, parallel environment, SB3, and RSL-RL APIs remain separate routes.
Do not map retired task IDs to current task behavior. The S4.5-B source-recovery
manifest records retired script identities and their exact recovery blobs.

**Historical F06 result (2026-11-01; runtime portion partially accepted):** This section records the frozen 2026-11-01 F06 run and is not the current capability summary. Later Phase C/7b PickCube runs with their own source identities are recorded in the [current state](../docs/module/task_env/v2.1.1/maintenance/current-state.md) and [G06 summary](../docs/module/task_env/v2.1.1/maintenance/g06/implementation-summary.md); they do not rewrite this failure.
MuJoCo CPU, GeoPhys CPU and Isaac Sim 6.2 CUDA PhysX each completed seeds31/32/33
at source `017392e86eb754749fc692263e08a1b33c3c5543`. All 9/9 runs are
runtime-valid with planned actions, finite recorded numeric data, H5 T+1 and
identity checks, independent cold reads, successful close, ended worker groups,
released locks and no execution faults. Task success is 0/9: all three seed31
runs report `measured_tcp_clearance_timeout:over_cube_before_descent`; all six
seed32/33 runs reach the 1000-tick horizon and report `episode_truncated`.
The maintainer partially accepts these nine runtime/example executions; task
effectiveness remains unresolved and solution behavior review is deferred.
The earlier QACC attempts and 6/9 PARTIAL remain historical evidence for older
solution identities. An initial zero-step Isaac EULA startup failure remains
charged; the accepted EULA environment was supplied on retry. Genesis and
SAPIEN remain `NOT_RUN_DEPENDENCY`. See the [final 3×3 matrix and raw evidence
index](../docs/module/task_env/v2.1.0/maintenance/validation/f_route/20261101_f06_pickcube_harness_headroom_matrix.md),
the [recording/action/reset integrity audit](../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/headroom_identity_017392e8_matrix_002/recording_integrity_audit.json),
and the [historical PARTIAL snapshot](../docs/module/task_env/v2.1.0/maintenance/validation/f_route/20261101_f06_pickcube_harness_partial.md).
This partial acceptance is not task success or Qualification and starts no F07 work.
