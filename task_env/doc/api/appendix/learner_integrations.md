# Learner integrations

`task_env.alg` 是可选 learner boundary，不参与 TaskEnv 核心构造。Generic RL、vectorization、Batch、Device 与 Learner contracts 在 P2.0-B S3 中保留。

## SB3

`task_env.alg.sb3.runner` 负责把已登记的 homogeneous TaskEnv 映射到 SB3。结构化 observation/action 的 flatten 由 `task_env.utils.SB3FlattenVecWrapper` 完成；并行生命周期和本地/远程 transport 仍由 `task_env.vectorization` 所有。

## RSL-RL

`task_env.alg.rsl_rl.adapter.TaskEnvRslVecAdapter` 将 raw homogeneous vector contract 映射为 RSL-RL `VecEnv` 所需的 `get_observations()` 与 `step()`。`terminated | truncated` 是 RSL `dones`；只有 `truncated & ~terminated` 进入 `extras["time_outs"]`。动作变换仍由通用 `RslActionTransformSpec` 处理，未声明 task profile 时回退到环境公开 action bounds。

统一入口 `task_env.script.rl.rsl_ppo` 要求调用者显式传入 `--env-id`。目标必须有 active task 注册、homogeneous parallel capability 和匹配的 learner action/observation contract。入口不自动挑选或替换训练任务；当前 PickCube 与 NutAssembly reference routes 是单环境路线，不因 S3 被隐式作为 PPO 目标。通用 `--render`、`--hard-render` 路径及 RSL/SB3 adapter 保留。

`RemoteBatchVecEnv` 的 `host_numpy` transport 与 runtime 明确支持时的 `device` transition 仍遵循原 capability checks。缺少 task/runtime/action device hooks 时不会隐式把每个 physics substep 转为 NumPy，也不会通过读取 provider-private state 补齐 capability。

## Go2 retirement status

P2.0-B S3 从当前 develop 移除了 Go2 task/robot registration、RSL profiles、Go2 checkpoint conversion/evaluation、Isaac/MuJoCo Go2 diagnostics 与 Go2-specific Flora wrappers。旧 Go2 task/agent UIDs 显式报 retired，不映射到其他任务；Go2 CLI/module imports 已移除。v1.0.0 是历史源代码和原始 Evidence 的恢复点。该 retirement 没有修改、重标或扩展历史 qualification。

Generic RSL-RL/SB3/vectorization contracts 仍可供未来明确注册且通过 action/observation contract review 的 task 使用。Go2 CUDA/static/RSL 的旧回归结果仅代表其历史 source/config/provider intersection，不证明当前 develop 仍有 Go2 runtime capability。S4 已从 public `develop` 退休 GeoChora-owned static-template route，同时保留通用 learner/vectorization contracts、GeoPhys-owned Rigid Batch adapter 和 renderer 实现。该集成没有为这些保留项增加新的 capability qualification。
