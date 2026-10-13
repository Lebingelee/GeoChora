# P1.6 100Hz + GPU Flow result

## Decision

The temporal/runtime path is executable, but the learned policy did not show reliable source-domain competence on the fixed six-seed cohort. The 100Hz best-validation checkpoint succeeded on seed 1000 and failed on the other five seeds (1/6). Preserve this experiment for Human Review before starting the deferred qvel, horizon, or policy-family changes.

The historical 500Hz final h16/a8 checkpoint failed all six matched seed numbers (0/6). The new 100Hz result is directionally better on seed 1000, but it is not a clean single-variable causal comparison: the 100Hz model uses a newly collected corpus, 1360 optimizer updates instead of 6480, a best-validation checkpoint instead of the old final checkpoint, and CUDA physics/inference instead of the prior CPU inference route.

## Frozen timebase and execution

- Historical Artifact: `461d2f08fc08685583d4e7a9ff0cf8401a223e6b719c9ecc32e4f32476f3c25e`, `physics_dt=0.002`, `control_substeps=1`, `control_dt=0.002` (500 Hz control).
- Experimental Artifact: `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4`, `physics_dt=0.002`, `control_substeps=5`, `control_dt=0.010` (500 Hz physics, 100 Hz control).
- GeoPhys collection/execution used the diagnostic CUDA route; training and policy inference also used CUDA. The route is not a provider qualification. The production GeoPhys manifest remains CPU-only.
- G0 passed: a session step completed exactly five native substeps, incremented control step once, advanced simulation time by 0.010 s, and returned finite state.

## Expert and replay gates

| Gate | Result | Evidence
|---|---|---|
| Seed 1000 expert | PASS, task success, max lift 0.10554 m, T=103, duration=1.03 s | `seed1000_expert_cuda/report.json`, `trajectory_metrics.json` |
| D0 teacher-forced public absolute-joint target equivalence | PASS; 103/103 target hashes match; all arm/gripper target errors are zero | `d0_teacher_forced/report.json` |
| D1 exact target replay | PASS; task success, max lift 0.10554 m; zero reported arm/EE/cube state divergence | `d1_exact_target_replay_cuda/report.json` |
| D2 transformed absolute-joint replay | PASS; task success, max lift 0.10554 m; zero target/state divergence; no clipping | `d2_absolute_joint_replay_cuda/report.json` |
| Expert reliability pilot | PASS threshold, 18/20 (90%); failures 1060 and 1065, both `above_pose_readiness_timeout` | `pilot_report.json` |

Seed 1000 stage timing (frames / physical duration):

| Stage | 500 Hz historical | 100 Hz experimental |
|---|---:|---:|
| move above cube | 100 / 0.200 s | 23 / 0.230 s |
| descend vertical | 64 / 0.128 s | 15 / 0.150 s |
| close gripper | 217 / 0.434 s | 20 / 0.200 s |
| lift | 94 / 0.188 s | 45 / 0.450 s |
| total | 475 / 0.950 s | 103 / 1.030 s |

The new policy timebase preserves successful expert/replay behavior for seed 1000 while substantially changing stage durations. This is expected because the per-boundary planner, controller, gripper, and readiness values were intentionally not rescaled.

## Corpus temporal comparison

The 500 Hz historical and 100 Hz new corpora each contain 100 successful demonstrations, but their seed sets are disjoint; compare these as distribution summaries, not paired trajectories.

| Metric | 500 Hz corpus | 100 Hz corpus |
|---|---:|---:|
| mean control frames | 519.10 | 112.94 |
| median control frames | 486.50 | 108.00 |
| p95 control frames | 682.25 | 141.05 |
| mean simulated duration | 1.0382 s | 1.1294 s |
| median simulated duration | 0.9730 s | 1.0800 s |
| p95 simulated duration | 1.3645 s | 1.4105 s |
| readiness-hold fraction | 76.88% | 13.20% |

Mean control frames fell to 21.76% of the historical count, while mean simulated duration increased by 8.78%. The 100 Hz per-boundary arm-position state deltas reached 0.03751 rad versus 0.01030 rad at 500 Hz; max per-boundary arm target-action delta reached 0.07612 versus 0.06446 (component-wise extrema in the locked report). Per-dimension min/max/mean/median/p95/std are retained in `temporal_comparison_report.json`. The decrease in frame count therefore does not mean a shorter physical task or smaller individual control changes.

## Flow training contract and result

The policy contract stayed at Flow_Vanilla / ConditionalUnet1D, 19,512,264 parameters, full 33D state including qvel, 8D absolute-joint action, horizons 2/16/8, 10 inference steps, train-only observation z-score and per-dimension q01–q99 action mapping. Training used float32 CUDA, batch 512, AdamW (`lr=1e-4`, `weight_decay=1e-6`), 80 epoch-equivalents. The new loader has 17 steps/epoch, so the frozen budget is 1,360 updates. Prediction duration is 0.160 s; open-loop execution is 0.080 s; replanning frequency is 12.5 Hz.

- Best-validation checkpoint SHA256: `563f37221c20e031bd20be095a8ff34dfcc279622181a4678371ad1c53a7ea37` (step 1360).
- Final checkpoint SHA256: `6639a4d650dbfc7f35c87ffbaa4aee845d09de381a7dbef91f197ca519193e6f` (step 1360).
- 100 Hz config SHA256: `77da445c4393d8dea26f88f37f8b506199eef63f63d05bb7315fc37f30b4df8d`.
- 100 Hz dataset manifest SHA256: `0e13517ce9f179daf7d4c525a6fb7d33629d3bb6fdd7683b4f06ac9492cf10dd`.
- Frozen training spec SHA256: `daa11ce98eff98b31c4677a53612287ddb4edb6422fe78a76d04cbcc1776c078`.
- Training completed 1,360 updates in 65.65 s; losses remained finite. The first report finalizer failed after training/checkpoint saves because it referenced a missing helper. The summary was reconstructed from preserved metric/checkpoint files without repeating training. Allocator peak memory values were not retained; a mid-run `nvidia-smi` sample observed 2,057 MiB used.

## Fixed Flow cohort

All six episodes used the best-validation checkpoint, one inference RNG stream `100000 + task_seed`, the same 2500-control-step ceiling, and no expert fallback. Each report verifies synchronous GPU inference with unchanged simulation time during every inference call. No action clipping occurred. Native contact readback was unavailable in the existing diagnostic session.

| Seed | Result | Max lift | Frames | Sim duration | GPU inference p50 / p95 | Max arm target step delta |
|---:|---|---:|---:|---:|---:|---:|
| 1000 | PASS | 0.10294 m | 243 | 2.43 s | 26.54 / 27.21 ms | 0.1233 rad |
| 1010 | FAIL | 0.00100 m | 2500 | 25.00 s | 25.78 / 26.58 ms | 0.1047 rad |
| 1020 | FAIL | 0.00688 m | 2500 | 25.00 s | 26.35 / 27.16 ms | 0.1755 rad |
| 1040 | FAIL | 0.01205 m | 2500 | 25.00 s | 26.40 / 27.23 ms | 0.1261 rad |
| 1050 | FAIL | 0.00100 m | 2500 | 25.00 s | 26.06 / 27.03 ms | 0.0742 rad |
| 1100 | FAIL | 0.00100 m | 2500 | 25.00 s | 26.71 / 27.82 ms | 0.1274 rad |

The historical 500 Hz q99/z-score final checkpoint (`dc5f8a2852c715dc51f20a2afd051559a5920638f3f2f06623a2efda0c0363df`) failed the same seed numbers 0/6, with max lifts respectively 0.00100, 0.00100, 0.01637, 0.00681, 0.07675, and 0.00100 m. The seed 1000 success is a real per-run difference, but the five failed 100 Hz episodes show no cohort-level competence.

The aggregate `rollout_cohort_report.json` and the six per-seed reports agree on 1/6 successes. The derived summary stores the row-level values and references the raw per-seed reports for episode-level audit.

## Interpretation and scope

The runtime/timebase and expert-to-action replay gates pass. The measured rollout result fits interpretation B only in the limited sense that this temporal profile, with a newly sampled dataset and GPU execution, is not sufficient to produce reliable Flow competence. It does not isolate timebase as the sole cause because corpus, optimizer update count, selected checkpoint, and device route also changed. The next action should be Human Review of these preserved results; do not infer that a future ablation or larger horizon will fix the failure.

No qvel ablation, longer horizon, ACT, cross-provider learned-policy rollout, or P1.8 work was performed. Production provider qualification and default PickCube identity were not changed. The separate P1.8 worktree was clean at final audit (`codex/p1.8-d-multirate-timebase`, `60b51e38ff3460da62296f73bbb93138f9d41b7f`); this task did not modify it.
