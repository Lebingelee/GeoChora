# TaskEnv Daily — 2026-08-15

## 范围

收口 Flora/RayTracer 并行资产渲染、共享 asset/selected-world transform、`src/solvers/rigid/batch` 接入，以及 Pendulum 不同并行 runtime 的对比实验。

## 核心数据

### 并行渲染

- Flora 256 实例使用 **16 unique models / 8448 mesh instances**；256 world 共享地板 model，不复制物理 batch。
- Flora 256-world asset smoke 的 native 统计为 **unique_meshes=32、mesh_instances=8450**；TaskEnv CUDA 256 selected worlds 输出 `float32[480,640,3]`，最大 RGB **0.686**。
- RayTracer 256 selected worlds 资源为 **22 unique assets、8448 instances、38,710,504 B geometry、9,780,420 B acceleration**；4096 physical worlds + 256 render worlds 保持相同 render topology，证明物理 batch 没有进入 scene asset import。
- 相关 render small tests 最近一次集合为 **55 passed**，另有 RayTracer instancing 集合 **14 passed**。

### Pendulum 并行 runtime

| num_env | optimization static-template control/s | optimization 默认 merged-scene | src `rigid_batch_v1` |
|---:|---:|---:|---:|
| 1 | 884.653 | 481.333 | 114.466 |
| 8 | 743.673 | 201.388 | 113.004 |
| 32 | 495.771 | 失败（sort-key overflow） | 99.727 |
| 128 | 217.406 | 失败（sort-key overflow） | 72.031 |
| 256 | 120.631 | 失败（sort-key overflow） | 52.930 |

optimization 静态模板实际报告 `hinge_or_slide_no_contact_v1 / fused_device_kernel / zero_copy_substeps=true`；`src` batch 的 `rigid_batch_v1` 当前仍是 `device_transition.available=false` 的 host/NumPy 状态边界。两者使用的积分器和接触能力不同，表格是执行路径性能比较，不是数值等价结论。

## 结论与边界

- 并行渲染已能复用 canonical asset table，并把 selected-world transform 传给各 backend；Flora 当前明确保留 host batch readback，不伪造 zero-copy。
- `BatchedRigidSolver` 已接入 Pendulum 的 static profile，但 device-native `step_device/reset_device` 尚未完成；二轮平衡车接触几何/CCD admission 仍是后续缺口。
- 静态模板路线在本次 Pendulum 测量中明显快于当前 `src` adapter，主要证据是两条路径的 device handoff 能力不同；应继续分别完善 capability 和公平的数值/性能基线。
