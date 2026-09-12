# TaskEnv Daily — 2026-08-08

## 范围

收口公共 `merged_scene` / `static_template` runtime 边界、分层 profiling、persistent workspace，以及 Go2 device 状态和接触数据的生命周期。

## 核心发现

- 并行 layout 由 runtime factory 选择，TaskEnv lifecycle、Gym/SB3 接口和任务语义保持不变。
- profile 已拆分为 construction、prewarm、reset、physics、task bridge 和 learner/PPO 阶段，并区分空载 GPU 与训练占用 GPU。
- `DeviceFieldPlan`、local/remote transfer provenance 和 persistent workspace 已建立；device-native 路径必须同时满足 runtime、task、action adapter 的 capability。
- static runtime 固定 traversal、contact slot、actuator route；Go2 device 常量和 task-owned buffer 缓存不改变 48D/12D/500-tick 契约。

## 结论与边界

fused ground-row 继续保持 local-slot ascending 的 row-PGS/Gauss-Seidel 语义，并只通过 public contact summary 对外提供结果。通用 ABA、CG/Newton、旧 device-mask/workspace opt-in 仍是候选路径，不能作为生产默认。

CPU/CUDA smoke、Stage 15.5/16 contract 和 Go2 device/contact envelope 已有记录；本日候选 profile 数据不与后续正式门禁混用。
