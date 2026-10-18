# v1.1.0 Public API Migration

v1.1.0 已发布，包含 breaking changes。完整旧 identities/symbols/flags/config、替代路线、
等价性分类与 recovery refs 保留在
[冻结 compatibility inventory](https://github.com/Lebingelee/GeoChora/blob/v1.1.0/docs/module/task_env/p2_0_s5_a_compatibility_inventory.json)。

| v1.0/历史入口 | v1.1.0 入口 | 迁移限制 |
| --- | --- | --- |
| `pick-cube-v1` | `make_env("pick-cube-p16-reference-v1", config={"provider":"mujoco","backend":"cpu"})` | breaking identity；非同义 alias，检查 selected P1.6 Artifact |
| `nut-assembly-square-v1` | `make_env("nut-assembly-outcome-reference-v1", config={"provider":"geophys","backend":"cpu"})` | guarded `step_expert()`，不接受任意 external action |
| direct legacy constructors/package helpers | `from task_env import make_env` | PickCube/NutAssembly helper exports 不对称，不假造 root builder |
| Go2 UID/robot/modules/profiles/defaults | 无 replacement | 当前 retired，历史在 v1.0.0 |
| StaticTemplate imports/runtime/layout/config | 仅已 admission 的 merged_scene | fail closed，不静默 redirect；generic contracts 不代表 native batch qualification |
| Stage11/grouped collect/旧 task recorder | selected root examples、`task_env.script.trajectory.record` | 使用现有 recorder，历史 source 需原 ref |
| historical camera/render scripts/private helper | 两条 Pendulum rasterizer examples | 只覆盖具名 scalar/batch CPU RGB，无通用替代 |
| RSL CLI 隐式 task | 显式 `--env-id` | 仍须 homogeneous 与 learner admission，无 Go2 替换 |

Selected 配置只接受 provider/backend/horizon；通用 Pendulum 使用 nested runtime config，两者不能混传。
参考[当前 public API](../../module/task_env/public-api.md)和[examples](../../../examples/README.md)。

原路径保留的[workflow A recovery](../../module/task_env/p2_0_s4_5_a_source_recovery.json)和
[workflow B recovery](../../module/task_env/p2_0_s4_5_b_source_recovery.json)继续供退役 CLI 错误提示读取。
[Go2 recovery](https://github.com/Lebingelee/GeoChora/blob/v1.1.0/docs/module/task_env/p2_0_s3_go2_retirement_manifest.json)
与[static recovery](https://github.com/Lebingelee/GeoChora/blob/v1.1.0/docs/module/task_env/p2_0_s4_static_solver_retirement_manifest.json)
给出逐文件 source hashes/refs。历史执行应在独立 checkout 恢复指定 immutable source，不把旧实现复制回 Core。

Post-release 文档路径改用 semantic names；完整旧文档 → current canonical/tag mapping 见
[inventory](../../maintenance/consolidation-inventory.json)。所有 v1.0.0/v1.1.0 frozen records 不变。
