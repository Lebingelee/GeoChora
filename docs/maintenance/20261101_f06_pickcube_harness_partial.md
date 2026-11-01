# F06 PickCube Harness multi-backend example — PARTIAL

**Result:** `F06_PICKCUBE_HARNESS_THREE_BACKEND_EXAMPLE_PARTIAL_PENDING_SOL_REVIEW`

- **Date:** 2026-11-01
- **Branch:** `develop-full`
- **Evidence update input HEAD:** `7d9adeaa8256bfad840126d2495f4f5ed773f071`
- **Latest MuJoCo R3 test HEAD:** `7d9adeaa8256bfad840126d2495f4f5ed773f071`; the post-`f0d3273` seed31 revalidation repeated the QACC runtime fault and produced no H5.
**Frozen package:** `sol_f06_001`, input `4a642f71440a76a94a315db1304442dfe6ddcb1f`, prompt SHA-256 `8cb16b3537e1f39677e4ed28a86bb0424311158e7c9f2e84ed40a9a7e1c0ed45`

The versioned `pickcube-harness-example-v1` selects public UID `pick-cube-p16-reference-v1` and reuses the existing PickCube task, reset sampler, readiness solution, R3 controller, Core RuntimeSession and Recorder. The strict `pick-lift-v0` candidate/Oracle/Judge gate remains unchanged. F06 uses `r3_continuous_v1`, seeds 31/32/33, 1000 control ticks and five 0.002 s physics substeps. Task/Expert outcome remains separate from runtime validity.

## Route matrix

| Provider | Seed coverage / tested identity | Runtime/H5/cold read | Task/Expert outcome | F06 disposition |
| --- | --- | --- | --- | --- |
| MuJoCo CPU, `r3_continuous_v1` | Seed31 attempted on source revisions `64a5b61`, `e6e5fb4`, `93efad5`, then current HEAD `7d9adea`; seeds32/33 not run. | Four QACC DOF13 execution faults; 0/3 valid F06 R3 H5. The post-repair run failed at 1.330 s and close/lock cleanup passed. | Execution fault, not a task-only failure. | Retain R3 and report the route failed. The latest single changed-hypothesis verification superseded the earlier no-rerun hold; another MuJoCo attempt now requires maintainer direction. R1 evidence remains separate. |
| GeoPhys CPU, `r3_continuous_v1` | 31/32/33 | 3/3 runtime-valid; planned actions executed; H5 T+1, finite data, independent cold read and close passed. | Seed31 `descend_pose_readiness_timeout`; seeds32/33 `gripper_readiness_timeout`; 0/3 solved. | Route valid; task/Expert failures reported. |
| Isaac Sim 6.2, CUDA `cuda:0`, GPU PhysX, `r3_continuous_v1` | 31/32/33 | 3/3 runtime-valid; planned actions executed; H5 T+1, finite data, independent cold read, close and lock release passed. Controlled workers verified `OMNI_KIT_ACCEPT_EULA=YES` after the maintainer's EULA acceptance. | Seed31 `episode_truncated`; seeds32/33 `gripper_readiness_timeout`; 0/3 solved. | Route valid; task/Expert failures reported. |

The required primary matrix has 9 H5 files. Six current-identity H5 files are valid (GeoPhys 3/3 and Isaac 3/3); the MuJoCo R3 route has 0/3 valid H5 files. Overall task success is 0/6 completed episodes. The example remains **PARTIAL**. A maintainer-authorized seed31 run on the current post-`f0d3273` identity exercised the repaired route and repeated the QACC runtime gate; seeds32/33 remain unrun. Further MuJoCo work is stopped pending maintainer direction. This is not a Qualification result.

## Historical MuJoCo comparison and QACC diagnosis

The prior PickCube × MuJoCo 3.8.1 CPU × seed31 result did pass: the frozen P1.6 Artifact/source and readiness solution completed 470 transitions/471 boundaries, 2,350 native steps, Expert completion, and a 0.1061 m lift. Its controller identity was `76108c78b8159391e448ad9f49050bed42fd7a86e0e00a0520083b4e5efb02e9` (production R1). F06 reused the same Artifact hash (`fd5bc968…`) and initially the same solution identity (`514a5ed3…`), but selected `r3_continuous_v1` with a different R3 controller identity (`12e5e8ed…`, then `44c80a3a…` and `df0e5393…`). The latest safe-approach test retains that R3 controller but has the changed solution identity `a75ed277…`. The earlier successful PickCube result therefore demonstrates that this task and MuJoCo route can work under R1; it does not establish stability for PickCube under R3. The raw historical [PickCube result receipt](../releases/v1.1/evidence/raw/l2/p2_0_part_b_s2_c1_20261016/pickcube_mujoco_v4/result.json) has SHA-256 `96e85d923987ace7fe8980561b00e3df9023d3c6242d347fadacdc191aa7a6fd`; its H5 SHA-256 is `579c676d542f53b1dde8e7488ccff6e1fd01b7e2d6b56e2e975e759d3af69018`. F05 DG01 is a separate derived cube/support Core cell, not the PickCube grasp-and-lift Expert run.

Historical C05c also passed MuJoCo 3.8.1 R3 on NutAssembly (2,377 transitions and 11,885 native samples; see [C Development Record](../module/task_env/goal/Phase_II/C_Development_Record.md#c05c)). That is a different task, scene, and control path; it does not qualify the PickCube × R3 intersection.

In the last failed F06 R3 run, the gripper was still open and the solution remained in `move_above_cube` at the 0.44 s last-completed boundary. The planned TCP hover was `[0.6351, -0.0865, 0.6330]` m while measured TCP was `[0.6201, -0.0834, 0.5703]` m; the cube had moved about 6.9 cm in x and 1.4 cm in z from reset before the next interval raised `Nan, Inf or huge value in QACC at DOF 13` at 0.448 s. This strongly points to an approach-path physical interaction/instability before grasp, rather than a generic inability of MuJoCo to run PickCube. The trace does not retain contact impulses at the fault boundary, so the exact contact mechanism is not proven.

Commit `f0d3273` changed the `move_above_cube` plan to raise vertically, transit laterally at 0.733 m, then descend to the unchanged hover target; its focused route/Harness checks passed (26 tests). The maintainer later explicitly allowed one further verification, so seed31 was run under current HEAD `7d9adeaa` with the same R3 controller and the repaired solution identity. It reached QACC DOF13 at 1.330 s during `descend_vertical`, after 133 complete control intervals. The H5 was not finalized; close and shared-lock release passed.

The new trace narrows the likely cause. At control step 40 (0.400 s), the planned TCP was at z=0.6772 m while public measured TCP was at z=0.5544 m; the cube had just moved 1.21 mm. The solution stage was still `move_above_cube`. By the last completed boundary, cube displacement from reset was 0.1219 m and its orientation had changed substantially. Thus the plan reached a high-clearance target, but the R3 physical tracker lagged by about 12.3 cm vertically while the fixed action sequence continued. This supports a hypothesis that tracking lag leaves the hand/cube at low clearance during planned lateral motion, but the fault-boundary contact impulse was not captured. The run also does not persist the MuJoCo model's DOF-address map, so the physical coordinate represented by DOF13 is not claimed here. The exact QACC/contact mechanism remains unproven.

The run receipt, trace, provider matrix, and post-run MuJoCo log copy are preserved under ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/mujoco_seed31_safe_approach_revalidation_001/`; its compact diagnosis is `diagnosis.json`. The modified repository-level `MUJOCO_LOG.TXT` was restored to its pre-run SHA-256. The changed-hypothesis retry is charged in the Goal ledger; no seed32/33 run followed. Stop further MuJoCo retries pending maintainer direction.

Route identities at source HEAD `00c1029`: GeoPhys recipe `2ce203b0c0025963bc97e3c4b3ab1eccb3fde9f866416a937c086f934b95e642`, solution `a75ed27712884865731747088fc3714c0da5e810836a44c80a4c32415fb10c33`, controller `df0e539399acad854401dbde9986a0338f8fd56909547814edc7566ebd562b25`; Isaac recipe `e9f1b860560455f9f44b6f428127b0ea28eadded9c05e020269609b51c8c5634`, same solution, controller `b37fa47d0fc48df33c8ac28dbef8dbdc3de4a94b8e4ed91894e4f0e3a3f8c027`.

## Current-identity H5 evidence

Each row has a separate run receipt and independent cold-read receipt under the F06 workspace. Hashes below identify the exact files; current identity was cross-checked against each run receipt and reader output.

| Provider / seed | Transitions / planned actions | Reported outcome | H5 SHA-256 | Run receipt SHA-256 | Cold-read SHA-256 |
| --- | ---: | --- | --- | --- | --- |
| GeoPhys / 31 | 228 / 65 | `descend_pose_readiness_timeout` | `d052e60279d97a5e034b4df1fed8a00438a27a2da03ba6c66a1d8ea064d87c57` | `9e4c6d186794f9c40428c67705b93023332dce2a637ed39e0610a1e19726abcb` | `4647f4f155afd9279d63ce5ed3be6244e111d39fd8e855acbbe9c675ceab1a86` |
| GeoPhys / 32 | 966 / 83 | `gripper_readiness_timeout` | `aa95f743e32d35c903836b230282af3d92ba613f6c2f2fab5d06062f28dbc137` | `7b2060003df4a86878e84ef2fff49e3df280f23defc2ef66c3ecc1c61c0461bb` | `a7dda15b90122846384415a522590a5f7bee16e05984b058596d8f13bbb030f5` |
| GeoPhys / 33 | 967 / 81 | `gripper_readiness_timeout` | `00a37f5e79a5c81391c396c462a704c4447d52f391aaac0e93caca693f1ccb9d` | `5a2ec413a8b17f793097b4ea44a3fcbbc7739bd98919cb99ca2e7b3d7a905566` | `ce2535e995286055633126d8ff0add09e2e2a7c43e626d7c2f40f78f3e4f8fb5` |
| Isaac / 31 | 1000 / 79 | `episode_truncated` | `6ba631911a10fe5b48217da1dc725d0e345d4f8465e44c1b98dd3a70fcad921e` | `7a1d4d87052ae55e92f80e4a49ae284200c678053c6a77b16277a2e719cd4c39` | `c5f15484429ae03d3fba365d1f9f46d609b0aec19450cd908bf4e4ca925db698` |
| Isaac / 32 | 966 / 83 | `gripper_readiness_timeout` | `a83b93353e49ee973fdaaec7e68589287a415e67381dcdc4a80d668735001798` | `94005d422bfc6f770e22115d550e5bedbe47949c108b243849bd359f36732127` | `3bb5df6d4b70cd8ec8e3f3a6fcaa9e38c45d1e03d847458de2662c11260f152d` |
| Isaac / 33 | 967 / 81 | `gripper_readiness_timeout` | `f53dca5b6e25e495da2bac94b0c8e707d92011317df6e16b8d3bd0eb4957f051` | `b8ca69336add668b3b094093c59f2f065c390b6d478460fd8e20b7c05882f06a` | `4c266b63d15a4111bee7c4c6e0b440a7cb7949539f59e9792e2ce99a9c5f1913` |

Raw H5 files, run/cold-read receipts, traces, lock receipts, worker logs and provider matrices remain under ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/` (including the Isaac seed31 sibling output directory); raw data was not committed. The refreshed per-file validation receipt is `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/f06_primary_h5_validation.json` (6 available of 9 required). Earlier six H5 files from the prior solution identity remain historical and are not counted as current-identity rows.

## Trajectory and optional backends

The tracked plot generator is [f06_pickcube_trajectory_plot.py](../../task_env/diagnostics/tasks/f06_pickcube_trajectory_plot.py). The refreshed [seed31 trajectory plot](../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f06_001/f06_seed31_trajectory.png) uses current GeoPhys and authorized Isaac post-repair H5 files, plots planned world TCP against public post-step EE pose and measured gripper opening, and labels the task failures. Its MuJoCo panel marks the R3 QACC failure and excludes the separate R1 diagnostic H5. The image was visually inspected after regeneration.

Genesis and SAPIEN import probes report the optional package missing in the configured `geochora` environment. Their CLI preflights persist `NOT_RUN_DEPENDENCY` and start zero workers. No optional engine was installed. Those receipts remain under the ignored F06 workspace.

## Implementation and checks

The existing implementation and six current-identity H5 runs use `develop-full@00c10296255f3a90c6aeb31d0bb0eec5e612cbad`; the post-repair MuJoCo R3 revalidation uses `develop-full@7d9adeaa8256bfad840126d2495f4f5ed773f071`. The local history includes the built-in Harness route, source/reset/identity repairs, the public dynamic EE readback repair, the bounded gripper-opening roundoff fix, and Isaac bootstrap/H5-bound fixes. Isaac seed31's post-repair retry was explicitly authorized; its `[-1e-6, 0)` measured-readback clamp did not change task targets or the physical task contract. All prior same-gate failures and charges remain in the ledger.

Checks recorded for this closeout:

- Refreshed six-file H5 validation receipt and existing independent cold-read checks: PASS for all six available current-identity H5 files; matrix remains 6/9.
- Seed31 trajectory plot regenerated from current H5/run inputs and visually inspected.
- TaskEnv Skill checker, skill-creator `quick_validate.py`, and direct/Harness CLI help: PASS (see the refreshed Skill receipt).
- `git diff --check` and changed relative-link/image existence checks: PASS.
- After staging this evidence update, `validate_docs.py` exited 1 with 285 inventory errors: the frozen document-count limit and 284 cumulative non-documentation changes. It checked 18 immutable URLs and reported no other error classes. This is not recorded as a PASS; the targeted added relative link and `git diff --check` pass.
- The post-repair MuJoCo seed31 revalidation was run under the new safe-approach hypothesis; it failed the QACC gate at 1.330 s. No full pytest suite, F07, training, Oracle/Judge expansion or Qualification was started during this evidence update.

This diagnostic example is pending independent Sol review. No formal provider/task Qualification is claimed.
