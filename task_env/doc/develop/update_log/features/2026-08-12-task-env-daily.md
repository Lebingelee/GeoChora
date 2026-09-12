# TaskEnv Daily — 2026-08-12

## 范围

收口 fixed active-slot f32 pipeline、Go2 PPO 性能门禁、release worktree 投影、评估脚本目录和并行生命周期边界。

## 核心数据

- B4096 清理后 3 seed median：P0 **89.131/91.992 ms**、P1 **87.159/88.935 ms**、P12 **49.812/50.362 ms**（p50/p95）。
- P12 相对 P0 的 p50/p95 改善约 **44.1%/45.3%**，最低 control Hz **20.05**。
- B8192、100 iterations：P0 约 **304 s**，P12 约 **277 s**；无 OOM、NaN、Graph fallback，checkpoint/resume 通过。

## 结论与边界

P1 是固定 topology 的 1-DOF child Schur，P12 在此基础上增加有界 root 6×6 factor；旧 `articulated_mass_response_triton_v1` 不进入 production。Go2 YAML 默认 P12、Taichi FK、f32 contact、CUDA Graph，runtime 细节不再从 PPO CLI 传入。

`origin/main` 当日已推送 `d1582717` 与 `5a6b21d2`；本地同步和合并留待用户确认。CUDA render 退出阶段的 native teardown、full `test/small` 的 TensorDict 崩溃和 ignored `temp_outputs` 仍单独记录，不能写成性能结论。
