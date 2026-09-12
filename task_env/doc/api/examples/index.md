# TaskEnv API examples

这些示例是 TaskEnv 的可运行入口索引。脚本只负责配置解析、调用顺序、contract 检查和结果摘要；任务语义、
batch runtime、SB3 协议转换与 H5 schema 仍由 `task_env/` 的公共模块负责。

## 运行约定

在仓库根目录、GeoPhys 环境中运行：

```bash
PYTHONPATH=GeoPhys/src:. python -m task_env.script.env.single_inline --backend cpu
```

脚本默认将摘要、相机帧、轨迹和 checkpoint 写入
`temp_outputs/task_env/`。`--backend auto`/`cuda` 会先尝试 CUDA；失败后才切换 CPU，并在 logger 中
记录 `runtime.backend_fallback`。脚本不会把 CPU fallback 伪装成 CUDA 成功。

## 命令矩阵

| 示例 | 命令 | 公开边界 | 默认产物 |
| --- | --- | --- | --- |
| 单环境 inline | `python -m task_env.script.env.single_inline` | `make_env`、Gym reset/step | `env/single_inline/summary.json` |
| 单环境 YAML | `python -m task_env.script.env.single_from_file --env-id pendulum-v1 --env-config task_env/doc/api/examples/pendulum_cpu.yaml --backend cpu` | YAML + resolved config | `env/single_from_file/summary.json` |
| 并行 inline | `python -m task_env.script.env.parallel_inline --num-env 4` | `make_parallel_env(..., execution="remote")` | `env/parallel_inline/summary.json` |
| 并行 YAML | `python -m task_env.script.env.parallel_from_file --num-env 4 --env-config task_env/doc/api/examples/pendulum_cpu.yaml --backend cpu` | 公共 env config + batch tree | `env/parallel_from_file/summary.json` |
| 静态相机 | `python -m task_env.script.camera.static` | `CameraSpec(frame="world")` + RGB observation | `camera/static.*` |
| 绑定相机 | `python -m task_env.script.camera.bound` | `CameraSpec(frame="site", parent=...)` | `camera/bound.*` |
| PickCube 规划 | `python -m task_env.script.trajectory.planning.pick_cube` | `PickCubeSolution` + `env.step` | logger summary |
| NutAssembly 规划 | `python -m task_env.script.trajectory.planning.nut_assembly` | `NutAssemblySolution` + `env.step` | logger summary |
| 轨迹录制 | `python -m task_env.script.trajectory.record --env-id pick-cube-v1` | `TransitionRecordWrapper` + H5 v2 | `trajectories/<env_id>/*.h5` |
| Panda 转换 | `python -m task_env.script.trajectory.convert --input source.h5 --output converted.h5` | offline Panda action schema | 显式 `--output` |
| Panda 重播 | `python -m task_env.script.trajectory.replay --trajectory converted.h5` | observation/reward/universal action | `trajectories/replay.json` |
| Pendulum PPO | `python -m task_env.script.rl.pendulum_ppo --num-env 8 --rollout-steps 5 --updates 3000 --save-log` | raw vector tree → SB3 flatten + H5 return curve | `temp_outputs/task_env/rl/pendulum_ppo/*` |

`convert`、`replay` 只面向 Panda/controller action schema；Pendulum、双轮车的 non-arm trajectory 不会被脚本
默认转码。旧的 `environment.py`、`planner.py`、`recorder.py` 和 `trajectory` module 命令继续作为兼容入口。

## 单环境 public API

```python
from task_env import make_env

env = make_env("pendulum-v1", config={"runtime": {"backend": "cpu"}})
try:
    observation, info = env.reset(seed=73)
    action = env.action_space.sample()
    observation, reward, terminated, truncated, info = env.step(action)
finally:
    env.close()
```

Pendulum 的 raw tree 是 `observation["state"]["proprioception"]` 和
`action["torque"]`；不应在单环境示例中强行转成 Panda 的 8 维 action。

## 并行与 SB3 public API

```python
from task_env import make_parallel_env
from task_env.utils import SB3FlattenVecWrapper

raw_env = make_parallel_env(
    "pendulum-v1",
    {"base_seed": 73},
    num_env=4,
    backend="cpu",
    execution="remote",
)
try:
    raw_observation = raw_env.reset()
    # raw_observation["state"]["proprioception"].shape == (4, 3)
finally:
    raw_env.close()

sb3_env = SB3FlattenVecWrapper(
    make_parallel_env(
        "pendulum-v1", {"base_seed": 73}, num_env=4, backend="cpu", execution="remote"
    )
)
try:
    observation = sb3_env.reset()  # shape == (4, 3), only at learner boundary
finally:
    sb3_env.close()
```

raw vector runtime 使用 multiprocessing `spawn` 和独立 Pipe；它不导入或复用 `task_env.reporter` 的 TCP/JSON
协议。raw recorder 应放在 flatten wrapper 之下，保证 H5 仍保存 `obs/*`、`action/*` 和
`universal_action/*` 的结构树。

## 明确保留为 planned

- vector H5 聚合容器、异构 batch 和 multi-agent batch；
- non-arm trajectory conversion；
- RGB policy、`MultiInputPolicy` 训练和 reporter 联调；
- 通用任务的 GPU device-resident observation/action 以及超出当前 contract smoke 的吞吐优化；只有显式声明
  device hooks 的 private Go2 static bridge 已有固定 tick/autoreset smoke。

这些能力不能从现有脚本命令的“可运行”推断为已实现。
