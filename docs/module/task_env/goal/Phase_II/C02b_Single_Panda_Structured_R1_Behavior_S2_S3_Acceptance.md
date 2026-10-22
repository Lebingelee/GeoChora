# C02b：单 Panda structured R1 连续行为与 Generic H5 v3 回读

日期：2026-10-22。状态：**本请求的双 Provider 行为与录制切片 PASS；C02b 仍 PARTIAL / IN PROGRESS**。本收据记录单 Panda Scene-v3 `production-r1` candidate 的真实行为和 Generic H5 v3 磁盘回读；不授予 Qualification，也不把 Phase II 标为完成。

## 范围与身份

两个 Provider 分别在独立进程运行，同一 Artifact、Scene、source、R1 Controller/TCP、`ControlBindingPlanV1`、seed-31 ResetSample、动作时序及几何条件。没有修改冻结 A05 source/Artifact、GeoPhys pin、冻结引用或 Provider 文件；没有加入第二 Panda、CUDA、Assembly、NutAssembly Guard、通用 capability 或新 Qualification campaign。

| 身份 | 值 |
| --- | --- |
| Artifact | `97e0f33d06bc58831a946e3a0cdf277f3f52efe5b2bcf801192a965631c90efd` |
| Scene | `047661ff68e18dffa10a8bfe9cabef4e72f397b5280c1da7c7669ebf9e419e6e` |
| Source closure / XML | `aa4ca97bbe3c61b30752ba0dedc6c88a24394f03fe1b53519052d460ff9abc47` / `2521356a6c925e8756e8d5309d68532aabce497654a7bd410cabac8533312aa3` |
| Controller | `panda-main/production-r1`, `aa97e909925b397968ad1c45716ce6e3f22902d5e676d2a18a1f27b86a814c76` |
| Kinematics / TCP | `6ce5254cd92efaffbf52d72881d96a1ea6a35da0b27aefd0c4ac89f181ca5d14` / `panda-main/hand-origin-tcp-v1`, `b27be18d500ddaa548f7a588d61a3756ae7663679ca66b3272aa268183461ff8` |
| Binding plan | `b4838ab8c954f462066cdb07356e5a90ad3f9c521c9f9b53ce9c933ac2828c80` |
| ResetSample | `reset-dd33666d67361443ff075da44cf01a673b3678c368a3118b3042ba652019ad68` |
| Provider build identity | GeoPhys revision `a53a8cfed7c9d6464274b5c96fca601271dc4ee4`, package-origin SHA-256 `57e772e69d39e79fb21fd23547727d7cc9738970ad307b70cd3ebbf2e0264c9e`, clean build; MuJoCo Python/runtime 3.8.1, package-origin `f8e5b528617004b6215e16cb0c945faf1f8c7b5d798e5b92e3aabce19c838497`, native binding `_functions` `9067239d3126392729430d12d077ab4b298c61d2ea1209c9333823be410359e3`, native `libmujoco.so.3.8.1` `8969010a8325d32b9b154159862ffe3b112277cc993983a0168f7dbe2efe0592` |
| Required force | `panda-main/actuator8`, signed raw N, `evaluation_boundary`, `actuator_force_query` |
| GeoPhys | `a53a8cfed7c9d6464274b5c96fca601271dc4ee4`, CPU, clean build |
| MuJoCo | Python/runtime 3.8.1, CPU; Python package, `_functions` binding and `libmujoco` digests match the exact admission values in the [typed-force receipt](C02b_R1_Typed_Raw_Force_Admission_Acceptance.md) |

Candidate construction reuses `build_r1_force_candidate`, `materialize_control`, the existing `execute_plan_bound_r1_control_interval`, `RuntimeSession.snapshot_v2()` and `control_feedback()`. Actual Controller and plan identities are admitted before materialization. The existing R1 policy is the only force-to-control mapping: `closing_force_N = max(0, -signed_actuator_force)`.

The existing Scene contains `square-peg-instance`; no geometry or source hash was changed. Exploratory runs with earlier approach targets did not meet the auxiliary pose comparison; those result files remain intact and are not presented as passing evidence. Before each final process was materialized, the probe configuration declared a source-FK-consistent arm target. Its offline constrained posture places the existing peg center at hand-local `(0, +0.0105, +0.1285) m`, within the unchanged source peg cross-section, and uses the corresponding hand-origin pose as the arm action target. This changes only the diagnostic action target: source, Artifact, plan, geometry, controller configuration, force/opening thresholds, and failure criteria are unchanged. The final target and its provenance are recorded in each final `predeclared_probe.json`; no threshold was adjusted after a run.

## Predeclared sequence and thresholds

Both providers used 100 Hz outer control, five 2 ms native steps per interval, 30 N R1 force limit, 1 N deadband, 0.0001 m force adjustment, 3 N force-mode activation (`max(0.5 N, 10% of limit)`), and a 10-interval / 0.10 s force-hold phase. The sequence was:

| Stage | Intervals | Request |
| --- | ---: | --- |
| open at reset pose | 65 | gripper open |
| close in free space | 65 | gripper close |
| open and approach existing peg | 240 | open, source-derived ramp then settle |
| obstructed close | 40 | close |
| force hold | 10 | keep close request |
| reopen | 65 | open |

Open endpoints had to reach at least 0.078 m, free-space close at most 0.002 m with force mode inactive, obstructed close had to reach the existing 3 N activation condition, force mode had to remain active throughout the 0.10 s hold, and reopen had to clear force mode and reach 0.078 m. Missing or stale force, incomplete Group coverage, wrong boundaries, mismatched target/ack, non-five-step intervals, or incomplete H5 readback were failures. No force threshold or source geometry was changed after a run.

The final configurations have the same reset sample, action schedule, source, geometry, controller parameters and failure limits. A structured diff of the two final `predeclared_probe.json` files found only `provider` and `execution.physics_provider` changed. The predeclared probe also records the auxiliary arm-pose deadband comparison using the existing 6 mm position and 0.035 rad orientation values. Exploratory targets did not meet those limits; the final source-FK target did, as recorded below. No failure threshold was changed after a run.

## S2: continuous behavior

Both final runs executed 485 real control intervals and produced 486 boundaries, ending at 4.85 s. Each interval had a five-sample sequence/native-index increment and a 10 ms evaluation-clock increment. Neither RuntimeSession exposes an independent completed-substep counter here; the five native steps are evidenced by the Provider's monotonic native sample sequence/index deltas plus the 10 ms outer clock, not claimed from a separate counter. The initial reset-forward sample was valid, episode/reset/materialization-bound and read without advancing the clock. The reset sample was `+4 N` on GeoPhys and `+4.00000000005 N` on MuJoCo; the existing canonical mapping correctly produced zero closing force from this opening-direction sign.

| Observation | GeoPhys CPU | MuJoCo 3.8.1 CPU |
| --- | ---: | ---: |
| Reset raw signed force | `+4.0 N` | `+4.00000000005 N` |
| First obstructed-close force entering R1 | `−3.0922515392 N` | `−3.0658391239 N` |
| Canonical closing force | `3.0922515392 N` | `3.0658391239 N` |
| R1 force-mode servo target / applied ack | `0.05157403269 / 0.05157403275 m` | `0.06697947278 / 0.06697947278 m` |
| Force-mode intervals in obstructed-close | 3 of 40 | 9 of 40 |
| Force-mode intervals in 0.10 s hold | 10 of 10 | 10 of 10 |
| Hold closing-force range | `0.4205–0.9942 N` | `0.7183–0.7641 N` |
| Reopen | mode cleared; `0.079932 m` | mode cleared; `0.079991 m` |
| Approach endpoint position error | `0.002671 m` | `0.003391 m` |
| Approach endpoint orientation error | `0.030374 rad` | `0.030208 rad` |

The first negative signed force crossed the unchanged 3 N threshold during the obstructed-close interval. Its canonical value changed the actual R1 servo target according to the existing configuration-derived R1 law, and the Provider acknowledgement named that target. The measured force during hold fell below the 30 N limit; R1 readiness therefore remained false. Readiness, force-mode memory, force values and physical finger/hand state were recorded separately. This probe did not assert task success or Expert completion; its finalized diagnostic outcome is `external_stop` with `task_success=null` and `solution_completed=null`.

All requested dispatch/behavior checks passed on both final runs: both `panda-main/arm` and `panda-main/gripper` were present on every request; target hash equaled applied-ack hash; the next state boundary followed the source publication; five native samples completed per interval; open/free-close/obstructed-close/force-hold/reopen behavior matched the predeclared force and opening criteria. The two providers' force values and trajectories are evidence for their own implementations, not cross-provider equality claims.

The final endpoint residuals satisfy the unchanged auxiliary 6 mm / 0.035 rad comparison on both providers. This is evidence for the declared source-FK target and exact candidate; it does not establish general R1 tracking accuracy for other poses, sources, providers, or builds. Earlier exploratory runs and their target residual failures remain preserved as failures.

## S3: same-file Generic H5 v3 write/read

Each run used the existing `TransitionRecorder` and Generic H5 v3 owner, then read the same H5 file through `load_structured_control_records_h5()` and `load_structured_training_actions_h5()`. Both files contain T=485 structured control transitions and T+1=486 observations. The structured reader validated the finalized `external_stop` EpisodeOutcome and BoundaryEvent; the action reader validated the one-writer projection. The runner additionally read the stored joint positions, hand pose, signed raw force, canonical closing force, opening/force feedback, native force clock, evaluation boundary clock and boundary/static/episode/reset/materialization identities from disk and compared them to the in-memory publications. Both same-file comparisons passed.

| Provider | Evidence directory / identities | H5 SHA-256 | Result JSON SHA-256 | Predeclared config SHA-256 | Readback |
| --- | --- | --- | --- | --- | --- |
| GeoPhys CPU | `workspace/maintenance/c02b_r1_structured_r1_closure_20261022/geophys_cpu_run_018/`; episode `episode-afa298c92f2a48218bfa29777ae1007a`; materialization `geophys-materialization-cd179aec3ca4473d8cb4e7c3c7c1ec12` | `cb8554628a5780682e01d2befe4171ed0d6dad8432492ef1d87e016be5c5c109` (3,201,849 bytes) | `2ff740ace528e7c02b0ac73b67a536539090628c8beff55e07ef0c9c8d0fa94c` | `b0f0b1a1b374bf03a1bab0a6fc572228ed720b2ae1d63b4f0edb7d1982251be2` | PASS: structured controls, action projection, numeric state, identities, clock and T/T+1 |
| MuJoCo 3.8.1 CPU | `workspace/maintenance/c02b_r1_structured_r1_closure_20261022/mujoco_cpu_run_005/`; episode `episode-df97cef28efe4dccb80eadeb0d07b6bc`; materialization `mujoco-materialization-0abbec3fe22748448ae61f706c447f15` | `372a3fb9a1c3abb432e53fc6924bf98f42222bdddbb28d2a607a20c0bc23d8b7` (3,213,924 bytes) | `37d1b9cefe5998dc49605729c49ba27d3c448b04129dd3e93eb1cbb18a80499d` | `73440e51411abf1fa752ef0f2483dd42ae5fde6d0919d43b0db6adee54b8ac52` | PASS: structured controls, action projection, numeric state, identities, clock and T/T+1 |

The H5 includes the original structured request, canonical action, signed raw-force and canonical feedback observation leaves, target envelope, applied acknowledgement and next-state leaves. The 486 observation rows include reset and final boundaries. No Recorder storage schema change was required. A prior exploratory run found that the training projection is based on the requested action vector; the probe now records that exact vector. The initial probe capacity was also raised from 400 to 500 transitions after the declared 485-step sequence exposed the diagnostic limit.

## S1, compatibility and failure boundaries

The targeted suite completed **69 passed** with one upstream `taichi_forge` `locale.getdefaultlocale` deprecation warning. After adding the final stale-repeat assertion to the GeoPhys and MuJoCo real-interval tests, both modified native tests passed again (**2 passed**, same warning). Coverage includes exact force admission and invalid/stale required values, old state-v1 mapping/hash, old no-plan admission, Position force-free compatibility, missing force capability, wrong Group/identity, stale publication/target and repeated application rejection before another compute/step, and the existing C03a partial-advance/apply/observer/Recorder fault latch behavior.

The new output writer tests refuse to reuse an explicit Evidence directory or JSON path and preserve the original bytes. Default pytest writes to `tmp_path`; retained native evidence uses a unique explicit path. The original loss declaration for the earlier overwritten GeoPhys JSON remains intact; no old JSON was reconstructed or represented as recovered.

Evidence is retained under `workspace/maintenance/c02b_r1_structured_r1_closure_20261022/`: each final run directory contains its `predeclared_probe.json`, `result.json`, and H5; exploratory outputs, the 69-test/stale-repeat logs, and `evidence_overwrite_refusal_001.log` are also preserved. There is no separate stdout log for final `run_018` / `run_005`, so their structured result/config and H5 files are the primary run evidence. Earlier `run_013` / `run_003` and subsequent exploratory runs remain unchanged, including failures. The final H5, result JSON, and predeclared-config hashes are listed above. The runner refuses an existing Evidence root before materialization.

## C02b exit scope

The [P00 baseline audit](06_P00_Baseline_Caller_Compatibility_and_Feasibility_Audit.md) and [Phase II blueprint](00_Phase_II_AD_Implementation_Blueprint.md) require a minimum two-Entity independent-control S2 for the P00/P99 envelope; they do not require two R1 Controllers. The accepted GeoPhys/MuJoCo Position-only dual-Entity evidence already closes that minimum. **No separate approved basis for dual-Entity R1 was found**, so it is not retained as an engineering blocker. Dual-Entity R1, CUDA R1, alternate MuJoCo builds, new source/Artifact profiles and general actuator-force support remain unadmitted extensions.

| Category | Current disposition |
| --- | --- |
| Engineering-required, completed evidence | Position Profile single-Entity S1/S2/H5; minimum dual-Entity Position S1/S2/H5 under the P00/P99 requirement; legacy PickCube reset-force freshness; exact GeoPhys/MuJoCo Scene-v3 typed-force publication/admission and one-interval gates; continuous single-Panda R1 force-mode/open/reopen behavior and Generic H5 v3 readback on both declared CPU intersections. |
| Additional required engineering item within this bounded P00/C02b scope | None identified after both final exact-provider runs passed all predeclared behavior and same-file H5 checks. This is a bounded result for the listed candidate/builds, not a general R1 capability claim. |
| Unadmitted extensions | Dual-Entity R1 (not a P00/P99 requirement), CUDA typed force, other source/Artifact/actuator transmissions, other MuJoCo builds, NutAssembly 500 Hz Guard, Assembly and general Provider capability. |
| Qualification | No Qualification campaign was run or granted. |

The requested single-Panda structured R1 behavior and recording slice is **PASS on both declared provider intersections**. C02b remains **PARTIAL / IN PROGRESS** at the parent-goal level, with no external blocker declared: this evidence closes only the explicit Scene-v3 candidate/build intersections above, while broader profiles stay unadmitted and Qualification is separate and unrun. Dual-Entity R1 has no approved basis as a required item; it is not an outstanding blocker. This receipt does not authorize an automatic transition into C02c or any extension. Phase II remains incomplete.
