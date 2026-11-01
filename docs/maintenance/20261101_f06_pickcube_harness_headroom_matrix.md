# F06 PickCube Harness: final headroom identity 3×3 matrix

**Disposition:** `F06_PICKCUBE_HARNESS_THREE_BACKEND_EXAMPLE_PASS_PENDING_SOL_REVIEW`\
**Execution date:** 2026-11-01\
**Tested source:** `develop-full@017392e86eb754749fc692263e08a1b33c3c5543`\
**Shared solution identity:** `27d31d85ad0aae83a72c8d3fcb901fa37678d39dae5394ca1395eb5ce6c2cd67`

## Result

The final shared R3 headroom identity was exercised on MuJoCo CPU, GeoPhys CPU,
and Isaac Sim 6.2 CUDA PhysX, each with seeds 31, 32, and 33. All **9/9 runs
were runtime-valid**: each executed planned solution actions, finalized an H5
episode, passed an independent cold read with source/artifact/controller/provider
identity and T+1 checks, closed successfully, ended its worker process group,
and released the shared native lock. There were no execution faults.

Task and Expert outcomes remain separate: **0/9 tasks solved**. All three
seed31 runs stopped at
`measured_tcp_clearance_timeout:over_cube_before_descent`; all six seed32/33
runs reached the 1000-tick horizon and ended as `episode_truncated`. This is a
runtime/example result, not task success or Qualification.

| Provider | Seed | Transitions / observations | Planned actions | Expert outcome | Run receipt | Episode H5 |
|---|---:|---:|---:|---|---|---|
| MuJoCo CPU | 31 | 227 / 228 | 36 | clearance timeout | [run.json](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/headroom_identity_017392e8_matrix_002/results/mujoco_seed31/seed_31/run.json) | [episode.h5](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/headroom_identity_017392e8_matrix_002/results/mujoco_seed31/seed_31/episode.h5) |
| MuJoCo CPU | 32 | 1000 / 1001 | 89 | episode truncated | [run.json](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/headroom_identity_017392e8_matrix_002/results/mujoco_seed32/seed_32/run.json) | [episode.h5](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/headroom_identity_017392e8_matrix_002/results/mujoco_seed32/seed_32/episode.h5) |
| MuJoCo CPU | 33 | 1000 / 1001 | 87 | episode truncated | [run.json](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/headroom_identity_017392e8_matrix_002/results/mujoco_seed33/seed_33/run.json) | [episode.h5](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/headroom_identity_017392e8_matrix_002/results/mujoco_seed33/seed_33/episode.h5) |
| GeoPhys CPU | 31 | 226 / 227 | 36 | clearance timeout | [run.json](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/headroom_identity_017392e8_matrix_002/results/geophys_seed31/seed_31/run.json) | [episode.h5](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/headroom_identity_017392e8_matrix_002/results/geophys_seed31/seed_31/episode.h5) |
| GeoPhys CPU | 32 | 1000 / 1001 | 89 | episode truncated | [run.json](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/headroom_identity_017392e8_matrix_002/results/geophys_seed32/seed_32/run.json) | [episode.h5](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/headroom_identity_017392e8_matrix_002/results/geophys_seed32/seed_32/episode.h5) |
| GeoPhys CPU | 33 | 1000 / 1001 | 87 | episode truncated | [run.json](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/headroom_identity_017392e8_matrix_002/results/geophys_seed33/seed_33/run.json) | [episode.h5](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/headroom_identity_017392e8_matrix_002/results/geophys_seed33/seed_33/episode.h5) |
| Isaac Sim 6.2 CUDA PhysX | 31 | 227 / 228 | 36 | clearance timeout | [run.json](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/headroom_identity_017392e8_matrix_002/results/isaacsim_seed31_eula_retry001/seed_31/run.json) | [episode.h5](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/headroom_identity_017392e8_matrix_002/results/isaacsim_seed31_eula_retry001/seed_31/episode.h5) |
| Isaac Sim 6.2 CUDA PhysX | 32 | 1000 / 1001 | 89 | episode truncated | [run.json](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/headroom_identity_017392e8_matrix_002/results/isaacsim_seed32_eula_retry001/seed_32/run.json) | [episode.h5](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/headroom_identity_017392e8_matrix_002/results/isaacsim_seed32_eula_retry001/seed_32/episode.h5) |
| Isaac Sim 6.2 CUDA PhysX | 33 | 1000 / 1001 | 87 | episode truncated | [run.json](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/headroom_identity_017392e8_matrix_002/results/isaacsim_seed33_eula_retry001/seed_33/run.json) | [episode.h5](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/headroom_identity_017392e8_matrix_002/results/isaacsim_seed33_eula_retry001/seed_33/episode.h5) |

The independent audit verifies the full receipt/H5 SHA-256 values and the
following for every row: planned actions executed, no execution fault, exact
provider/seed/source/solution/recipe match, H5 hash and T+1 match, independent
cold-read PASS, close PASS, lock release, and no timeout/resource violation.
It records `case_count=9`, `runtime_valid_count=9`,
`cold_read_pass_count=9`, `close_pass_count=9`, and `task_solved_count=0`.

## Frozen identities and execution bounds

- MuJoCo and GeoPhys recipe: `7b3bdd32b2ae5462ea412594f018820f52d6f5e8f8b5a9ece5975366e2199697`.
- Isaac recipe: `02a91827ae24f16ce68b71cb72768e3caa1ff8d4fd9c3cc11052912d05214abe`.
- MuJoCo/GeoPhys controller: `df0e539399acad854401dbde9986a0338f8fd56909547814edc7566ebd562b25`.
- Isaac controller: `b37fa47d0fc48df33c8ac28dbef8dbdc3de4a94b8e4ed91894e4f0e3a3f8c027`.
- CPU per-run bound: 5000 native steps and a 420-second watchdog. Isaac per-run bound: 5018 steps including 18 bootstrap steps, and a 1200-second watchdog. Runs were serialized under the shared native lock.
- One Isaac seed31 startup attempt omitted the already accepted EULA environment variable and exited before physics/H5 creation. That attempt and its charge remain in the ledger. The retry set `OMNI_KIT_ACCEPT_EULA=YES`; all three final Isaac rows passed runtime and evidence checks.
- Genesis and SAPIEN remain `NOT_RUN_DEPENDENCY` from earlier optional probes. No F07, training, or Qualification was started.

## Evidence and cumulative charges

Raw outputs are local ignored workspace evidence and must remain with this
checkout for cold reinspection:

- Matrix root: `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/headroom_identity_017392e8_matrix_002/`.
- Frozen matrix plan: [`matrix_plan.json`](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/headroom_identity_017392e8_matrix_002/matrix_plan.json), SHA-256 `0ff1348ca0b0ed633ddd5c8b80c34a510eb3f9373ca56d78ffa84b3a2e11c8a9`.
- Independent nine-case audit with full evidence paths and hashes: [`matrix_audit.json`](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/headroom_identity_017392e8_matrix_002/matrix_audit.json), SHA-256 `0e968d21844a4de13d712dbb6678c96970568a2c4fa42d159aa25dcddde2de6f`.
- Seed31 public TCP/gripper trajectory comparison:

  ![Final headroom identity seed31 trajectory](/home/lly/Program_Files/Geochora/workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/headroom_identity_017392e8_matrix_002/f06_final_headroom_seed31_trajectory.png)

  Plot SHA-256: `4d10206f97417f2072b979e80b20d12c1b9ea41ef16485471af353693aa840d8`.
- Append-only run ledger and resumable execution state: `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/run_ledger.json`, `goal_progress.json`, and `RESUME.md`.
- This follow-up charged 10 worker starts (nine matrix cases plus the zero-step Isaac EULA startup failure), 50,072 upper-bound native steps, 33,454 measured steps including 54 bootstrap steps, and 1,529.612618 worker seconds. Cumulative Goal totals are 41 starts, 177,527 upper-bound steps, 87,572 measured steps including 234 bootstrap steps, and 5,108.202755 worker seconds. Earlier failed attempts remain charged in the ledger.

The previous 6/9 PARTIAL snapshot and all earlier failures belong to earlier
solution identities and remain historical evidence; this matrix is the final
shared headroom identity's complete 3×3 runtime revalidation. Independent Sol
review remains pending.
