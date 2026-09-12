# TaskEnv Daily — 2026-08-09

## 范围

复核 Taichi/Torch backend、reset lifecycle、CUDA Graph scope、Go2 action profile、render input 和源码路径迁移。

## 核心发现

- Taichi FK 与 Torch/CUDA external view、pointer、device、stream 边界稳定；部分大 batch 有收益，但不能据此宣称完整 Taichi solver。
- Torch-FK ground-contact Graph 有 parity/invalidation 证据；Taichi-FK 加完整接触 Graph 继续受 capability gate 约束。
- Go2 的 Unitree native 12D PD action、48D observation/action clip 和 YAML profile 已固定；legacy RSL-RL 入口隔离在 diagnostics。
- masked reset、selected-world buffer 和 device constants 已稳定，避免随 iteration 增长的 shape/allocation 风险；headed 相机输入改为鼠标语义。
- P2-S19 路径迁移完成 canonical `task_env/`、import/bootstrap/package-data 和 smoke 收口，后续只维护根目录实现。

## 结论与边界

保留 Graph/eager 两条 capability-guarded 路径，不把旧 CLI 或未完成接触 Graph 写入生产。backend 排序会受 batch、warmup、cache 和 GPU 负载影响，正式性能门禁必须使用固定空载口径；renderer teardown 与 physics frequency 分开记录。
