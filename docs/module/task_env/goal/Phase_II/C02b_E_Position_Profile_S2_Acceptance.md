# C02b-E Position Profile：双 Provider S2 与 Generic H5 v3 验收

日期：2026-10-21。结论：**PASS_BOUNDED_POSITION_PROFILE_S2；C02b 仍 BLOCKED**。本报告承接 [S1 验收](C02b_E_Position_Profile_S1_Acceptance.md)，不重开架构审阅，也不把单 Panda Position 候选扩写为 R1、NutAssembly Guard 或 Phase II 验收。

## 范围与身份

GeoPhys CPU 与 MuJoCo CPU 分别在独立 Python 进程运行相同显式 candidate builder、A05 Scene 和固定 ResetPlan。候选沿用 `SelectedReferenceEnv.from_position_candidate(ReferenceTaskBinding, ...)`、`ControlBindingPlanV1`、既有 `RuntimeSession`、C03a fault latch、`TransitionRecorder` 与 Generic H5 v3 reader/writer；未增加默认 task registry。candidate 使用 100 Hz 外层、5×2 ms native interval，无 renderer、无 measured actuator-force requirement。

本次两进程确认一致的输入与实际 writer identity：

| 身份 | 值 |
|---|---|
| Scene-v3 | `047661ff68e18dffa10a8bfe9cabef4e72f397b5280c1da7c7669ebf9e419e6e` |
| TaskArtifactV1 | `a56b6cbac66bc570c43d38b8eb5a7e3098873cc196015242d3e46df76dd0364c` |
| EpisodeResetPlanV1 | `7965ae3292f96c82e99a442754b36172c885e049204ffb1b1bcb58a4d4a2d53d` |
| ResetSample | `reset-76ee97d76770106cfe04d84dbad39081683493cde7440ba5d5f03edadb733345`，task seed 31 |
| Panda + peg source closure | `aa4ca97bbe3c61b30752ba0dedc6c88a24394f03fe1b53519052d460ff9abc47` |
| Panda Menagerie dependency closure | `a59a66d0b176cb6b2634d54cd20744752742b425e5524db1b865dda0eb3adf2a`，68 files |
| Profile / Controller identity | `panda-main/position-servo-v1` / `3c8fae3e65515f4a62a0c2ba9c5b09d11e8b67ff724642948371b2539050836e` |
| ControlBindingPlanV1 | `e050d41a0d0f3eca8e4c2472b88ab94fd6a1bf12a2d1a28abc97fcc8876d143e` |

The writer owns `panda-main` arm and gripper groups. RuntimeSource/reset/action binding uses the exact `panda-main/joint1…7 → actuator1…7` mapping and `actuator8` for the gripper. The reused legacy DLS algorithm still calculates with its `panda-v1/joint*` keys; Position Profile explicitly maps its outputs back to the candidate’s entity-qualified source Joint keys before the existing RuntimeSession applies them. This aligns ResetSample, source Joint identities and Provider targets without changing old controller behavior.

The actual Controller uses the source ActionConfig: absolute world pose with `quaternion_wxyz`; DLS position gain 0.9, rotation gain 0.65, damping 0.02, one gripper correction of `5 N / 2500 N·m⁻¹ = 0.002 m` per control action, 0.08 m opening range, 5 N position-servo force cap. The force cap is a command parameter; this profile does not read force. A05 Panda XML still has no `nutassembly_ee_site`; the versioned `panda-main/hand-origin-tcp-v1` has identity hand→TCP transform and leaves the frozen source unchanged.

## Native reset, kinematics, action and clock evidence

The public ResetPlan realization gate passed on both Providers. Reset returned control step 0 and simulation time 0.0; typed state had exactly nine entity-qualified Panda Joint positions, the `panda-main/hand` Frame, matching Scene/ResetSample identity, and an `evaluation_boundary` clock at sample index 0. The first recorded observation is that actual reset publication. Three additional public typed snapshots retained the same boundary identity and did not advance control or simulation clocks.

Before executing actions, the S2 probe fixed these kinematic tolerances: FK position ≤ `1e-6 m`; sign-invariant quaternion L2 ≤ `1e-6`; central-difference Jacobian maximum absolute error ≤ `5e-5` using `1e-6 rad` perturbations. The measured results were:

| Provider | FK position error | Quaternion error | Jacobian finite-difference error |
|---|---:|---:|---:|
| GeoPhys CPU | `4.51e-9 m` | `7.02e-9` | `1.01e-10` |
| MuJoCo CPU | `8.36e-17 m` | `2.22e-16` | `1.01e-10` |

In both runs the typed Controller input was the measured hand Frame, the FK output was the hand-origin TCP, and the Jacobian was numerically verified at that same TCP. No `nutassembly_ee_site` was assumed.

Each process issued 64 structured controls: 20 open commands at the initial pose, 12 open commands while moving the hand target +0.02 m in world X, 20 closing commands, then 12 reopening commands. Every action contained both `panda-main/arm` and `panda-main/gripper` groups and passed complete-plan preflight. Each outer action called the actual profile compute once, the single writer apply once, received the matching applied target hash, then returned from `RuntimeSession.step()` once. Measured arm/gripper motion was nonzero:

| Provider | Max arm Joint change | Gripper open peak | After close | Final reopen |
|---|---:|---:|---:|---:|
| GeoPhys CPU | `0.1678 rad` | `0.004882 m` | `0.002225 m` | `0.003593 m` |
| MuJoCo CPU | `0.2090 rad` | `0.004877 m` | `0.002220 m` | `0.003588 m` |

All 64 public outer clocks advanced by one control step and `0.010 s`; the probe records five requested native steps and an inferred count of five from the `0.010 s / 0.002 s` public native-time delta. The RuntimeSession API does not expose a separate provider-neutral completed-native-step counter, so the receipt does not describe that inferred count as a direct counter reading. Target requests and returned step/clock evidence remain separate fields.

This source has no inserted obstruction. Thus open, arm motion, close and reopen are covered; obstructed closure and R1 force hold are not part of this force-free profile probe.

## Generic H5 v3 write and disk readback

Existing `start_recording(path)` starts the existing `TransitionRecorder` at the real reset observation. The 64 completed controls produced 65 state boundaries. `finish_recording("horizon")` wrote Generic H5 v3 and read its structured controls/outcome back. The typed structured reader and single-writer training projection both returned 64 rows. Direct HDF5 reads compared the complete on-disk arrays against live observations and passed:

| Leaf | Stored shape per Provider | Result |
|---|---:|---|
| `obs/state/joint_position` | `(65, 9)` | exact float32 readback |
| `obs/state/hand_pose` | `(65, 7)` | exact float32 readback |
| `obs/state/boundary_identity_sha256` | `(65, 32)` | exact boundary identity digest readback |

Each structured control contained exactly one writer, both action groups, the actual Controller target and matching Provider acknowledgement. The explicit training projection exactly matched the issued eight-component request vectors. H5 outcome is `truncated=true`, `terminated=false`, `final_boundary=64`, `task_success=false`; this is a bounded horizon stop, not a task-success claim.

The per-process H5 files are `workspace/maintenance/c02b_position_s2_20261021/geophys_final/geophys-position-s2.h5` and `workspace/maintenance/c02b_position_s2_20261021/mujoco_final/mujoco-position-s2.h5`. Machine-readable receipts and stdout logs are next to them in the same ignored maintenance directory.

## Lifecycle and failure probes

- Step before reset was rejected before materialization or dispatch. Calling `reset()` without a seed used the bound ResetPlan seed 31; an explicit mismatched seed was rejected both before initial materialization and while a live session existed, without closing/changing that session.
- The post-horizon action and post-close action were rejected without another compute, apply, RuntimeSession step or transition. A wrong-source/incomplete typed preflight remains mutation-free under the existing S1 tests.
- The rollout instrumented `control_feedback()` to raise if called. It was never called. S1 actuator-force copy/query sentinels remain passing; neither provider route requests the measured force field.
- Injected apply failure latched C03a with `physical_progress=not_advanced` and no transition. Injected failure immediately after a real step returned `physical_progress=advanced`, `interval_completed=true`, and no transition. Injected recorder failure after a real completed interval likewise latched the fault and reported `transition_status=rejected`; atomic append left the recorder at 0 transitions / 1 reset observation.
- Repeated reset retained the same ResetSample identity, generated a new episode identity, and returned to control step/time zero.

## Code, tests, and bounded conclusion

This round adds an explicit `SelectedReferenceEnv.from_position_candidate()` entrypoint that accepts the existing `ReferenceTaskBinding`; it does not register a default production task. Fixed ResetPlan seed checks occur before changing a live Position session. Position lifecycle refuses pre-reset, stopped/horizon, faulted and closed calls before compute/apply/step/record. H5 v3 uses `TransitionRecorder` and makes aligned transition append atomic under capacity/copy errors. Legacy selected reset/recording and `panda-main/production-r1` contracts remain unchanged; a regression caught and preserved the legacy reset reconstruction-before-seed-validation behavior.

The native evidence closes only the Position candidate’s declared single-Panda GeoPhys/MuJoCo CPU intersection and its H5 v3 disk route. It does not close the force-aware `production-r1` raw-force requirement or GeoPhys reset-force freshness gap. No R1 execution, PickCube force-aware behavior, NutAssembly R3 500 Hz Guard, obstructed-force hold, C02c, Assembly, multi-Entity dispatch, full Expert route or Phase II qualification was run. **C02b remains BLOCKED.**

Final focused regression command covered eight affected groups: Position profile/execution/H5, C02b admission, C02a controller bindings, C03a fault lifecycle, C05a structured recording, D02b typed runtime state and selected consumers. Result: **92 passed**, one upstream `taichi_forge` `locale.getdefaultlocale` deprecation warning; no failures. `git diff --check` also passed. Broad repository regression was not run. The S2 scripts/logs/H5 files remain ignored under `workspace/maintenance/c02b_position_s2_20261021/`; no source artifact, GeoPhys pin, frozen branch or frozen fixture was changed.
