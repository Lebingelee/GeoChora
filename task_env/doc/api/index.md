# TaskEnv API Reference

当前模块使用与能力治理入口：[TaskEnv canonical docs](../../../docs/module/task_env/README.md)。符号级细节继续在 API reference 维护。

本文导航当前调用入口；可 import 或登记并不单独构成稳定 API 或端到端能力承诺。快速运行请看 [README Quickstart](../../README.md)；训练、采集、任务和资产开发入口见 [文档入口](../index.md)。

## 公开数据流

~~~
environment UID/config
        ↓
make_env / make_parallel_env
        ↓
scene assembly + stable references
        ↓
task lifecycle: reset → action/controller → runtime step
        ↓
observation + reward + terminated/truncated + info
        ↓
optional SB3/RSL-RL learner or H5 recorder
~~~

用户通过 public environment、Gymnasium spaces 和 metadata 访问数据；runtime、solver、Taichi field、contact workspace、actuator ctrl 和 qpos private layout 不属于通用用户契约。

标准交互方向是外部 Solution 从 observation 推理 action，再由调用方交给 `env.step(action)`；`step_expert()` 仅作为受限兼容保留，不是标准 Env API。当前示例及轨迹脚本使用调用方驱动路线；PickCube 与 NutAssembly 的差异见[Solution 接口](planning/task_owned_solutions.md)。

## 最短入口

| 领域 | 入口 | 说明 |
| --- | --- | --- |
| 单环境 | task_env.make_env | 创建 Gymnasium 风格环境 |
| 旧并行环境 | task_env.make_parallel_env | 旧 SB3 local/remote 的独立入口；显式 `execution='device'` 是 G06 有界接收的正式 device 路线，旧 wrapper 不能由登记推断兼容 |
| 单环境 registry | task_env.ENV_REGISTRY | 查询 UID 和 component |
| 并行 registry | task_env.PARALLEL_ENV_REGISTRY | 查询已声明的并行能力；登记不等于任意 batch 能力 |
| 配置构造 | task_env.resolve_env_config | 使用 task_uid、scene_uid 等关键字构造配置；并非任意配置字典的统一解析器 |
| 记录 | task_env.script.trajectory.record / TransitionRecordWrapper | 保存公开 transition/H5 |
| SB3 | task_env.utils.SB3FlattenVecWrapper | 在 learner 边界 flatten tree |
| RSL-RL | task_env.script.rl.rsl_ppo | 统一 PPO 训练 CLI |

## 任务组合与语义

- [Composition index](composition/index.md)：world、passive object、active agent/controller 的组合。
- [Semantics index](semantics/index.md)：BaseTaskEnv、TaskDefinition、episode reset 和 built-in tasks。
- [Planning index](planning/index.md)：public motion primitives 和 task-owned solution。
- [Recording index](recording/index.md)：wrapper、trajectory lifecycle 和 H5 schema。

单环境通过 `make_env(uid, *, config=None, render_mode=None, **kwargs)` 创建。Empty、Pendulum、TwoWheel、PickCube 和 NutAssembly 的单环境由 `task_env.environment.reference_env.SelectedReferenceEnv` 拥有；`BaseTaskEnv` 和 `task_env.tasks.reference_env` 为兼容导出。四个正式任务使用共同配置解析、Task binding 与 RuntimeSession 构建链；保留的 Empty component 路线使用 RuntimeBoundary。动作、观测和支持的 render 以实际任务及 provider 能力为准。生命周期源码和无引擎契约已获 [Sol 有限接收](../../../docs/module/task_env/v2.1.1/maintenance/reviews/20261105_lifecycle_unification_sol_review.md)；后续三个旧任务与 PickCube 有按提交限定的 [CPU 运行记录](../../../docs/module/task_env/v2.1.1/maintenance/reviews/20261105_pre_stage3_continuation.md)，不能代替当前源码的完整物理验证。旧并行入口和 registry 保留；G06 的 device batch 是独立的、经独立主审接收的 `make_parallel_env(..., execution='device')` 路线，见 [device 教程](../../../docs/module/task_env/v2.1.1/guides/quickstart-device-batch.md)；登记、历史 SB3/RSL 运行或单 slot 示例不证明旧 wrapper 兼容。

## 内置任务

当前常用 UID：

~~~text
empty-v1
nut-assembly-outcome-reference-v1
pendulum-v1
pick-cube-p16-reference-v1
two-wheel-balance-v1
~~~

Pendulum 和 TwoWheel 的旧并行能力有登记；G06 已独立接收 Pendulum/PickCube × MuJoCo Warp/GeoPhys/Isaac 的 canonical device batch 交集，但 Nut batch、R3 batch、任意异构组合和旧 SB3/RSL wrapper 兼容仍是未支持/独立项。四个正式任务使用同一单环境构建入口；旧 `pick-cube-v1`、`nut-assembly-square-v1` 及 Go2 UID 在当前 factory 明确退休，不映射到其他 task。

## Appendix

- [Environment creation](appendix/environment_creation.md)
- [Configuration](appendix/configuration.md)
- [Public contracts](appendix/public_contracts.md)
- [Runtime boundary](appendix/runtime_boundary.md)
- [Observation and rendering](appendix/observation_and_rendering.md)
- [Learner integrations](appendix/learner_integrations.md)
- [Migration](appendix/migration.md)
- [Runnable examples](examples/index.md)
