# TaskEnv API Reference

本文记录 TaskEnv 的稳定公开入口和数据契约。快速运行请看 [README Quickstart](../../README.md)；训练、采集、任务和资产开发入口见 [文档入口](../index.md)。

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

## 最短入口

| 领域 | 入口 | 说明 |
| --- | --- | --- |
| 单环境 | task_env.make_env | 创建 Gymnasium 风格环境 |
| 并行环境 | task_env.make_parallel_env | 创建同构 local/remote batch 环境 |
| 单环境 registry | task_env.ENV_REGISTRY | 查询 UID 和 component |
| 并行 registry | task_env.PARALLEL_ENV_REGISTRY | 查询已声明的并行能力 |
| 配置 | task_env.resolve_env_config | 校验并冻结 public config |
| 记录 | task_env.script.trajectory.record / TransitionRecordWrapper | 保存公开 transition/H5 |
| SB3 | task_env.utils.SB3FlattenVecWrapper | 在 learner 边界 flatten tree |
| RSL-RL | task_env.script.rl.rsl_ppo | 统一 PPO 训练 CLI |

## 任务组合与语义

- [Composition index](composition/index.md)：world、passive object、active agent/controller 的组合。
- [Semantics index](semantics/index.md)：BaseTaskEnv、TaskDefinition、episode reset 和 built-in tasks。
- [Planning index](planning/index.md)：public motion primitives 和 task-owned solution。
- [Recording index](recording/index.md)：wrapper、trajectory lifecycle 和 H5 schema。

单环境路径从 make_env 进入 BaseTaskEnv；并行路径从 PARALLEL_ENV_REGISTRY 进入 task-owned parallel capability，再由 vectorization 负责 batch lifecycle、masked reset、local/remote 和 SB3 protocol。并行不会静默退化为多个单环境。

## 内置任务

当前常用 UID：

~~~text
empty-v1
go2-walk-v1
go2-walk-deploy-v1
go2-walk-deploy-height-v1
go2-walk-codex
nut-assembly-square-v1
pendulum-v1
pick-cube-v1
two-wheel-balance-v1
~~~

其中 Pendulum、TwoWheel 和 Go2 任务已声明并行能力；PickCube、NutAssembly 等没有 parallel capability 的任务继续通过单环境入口使用。

## Appendix

- [Environment creation](appendix/environment_creation.md)
- [Configuration](appendix/configuration.md)
- [Public contracts](appendix/public_contracts.md)
- [Runtime boundary](appendix/runtime_boundary.md)
- [Observation and rendering](appendix/observation_and_rendering.md)
- [Learner integrations](appendix/learner_integrations.md)
- [Migration](appendix/migration.md)
- [Runnable examples](examples/index.md)
