# TaskEnv Daily — 2026-08-11

## 范围

完成 Go2 B4096 PPO collection 的 active-slot response、Triton row-PGS、Taichi FK、CUDA Graph 和 device lifecycle 优化验证。

## 核心数据

- B4096、3 seed、15 个稳态 PPO collection 窗口：最低 **14.531 Hz**，平均 **14.816 Hz**。
- collection-only 吞吐约 **60,686 env-steps/s**；该指标不与包含 learner 的 RSL total FPS 混用。
- B4096 相比 B32 的聚合 env-step 吞吐约 **44.33×**，但 control-Hz 不线性扩展。

## 结论与边界

response 只组装和求解每个 world 的 active contact slots，固定 capacity 保持 Graph storage/pointer 稳定；Triton 仅在当前 stream qualification 通过时启用，并把 selected/effective/fallback/failed-closed 写入 provenance。显存峰值、Nsight occupancy、长时收敛和 render 开关影响未在本日完整量化。
