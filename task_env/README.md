# Geochora TaskEnv

TaskEnv 为 Geochora 提供单环境、同构并行环境、相机/渲染、强化学习和轨迹采集入口。所有示例均从 Geochora 仓库根目录执行。

## 项目结构

~~~text
task_env/
├── __init__.py              # public exports、make_env、make_parallel_env
├── registry.py              # environment / agent / object / scene registry
├── environment/             # config、Gym lifecycle、state/observation contracts
├── assembly/                # world/robot/object 编译和稳定 references
├── robots/                  # robot/agent asset 与 controller contract
├── objects/                 # object asset 与 reference contract
├── controllers/             # public action 到 control command
├── observations/            # observation 与 camera sensor projection
├── tasks/                   # task composition、reset、reward、success、failure（含 tasks/worlds/）
├── runtime/                 # physics runtime、batch layout、reset/step lifecycle
├── vectorization/           # local/remote parallel、SB3 adapter、masked reset
├── render/                  # rasterizer、raytracer、Flora 和 parallel render provider
├── planners/                # public motion primitive 与 task-owned solution
├── recorders/               # public transition 与 H5 recorder
├── trajectory/              # trajectory schema、processing、replay
├── alg/                    # SB3 / RSL-RL learner boundary
├── script/                  # 可直接执行的 env/camera/rl/trajectory CLI
├── diagnostics/             # 诊断、对照和专项 smoke，不是日常使用入口
└── doc/                     # Quickstart 以外的使用、开发和 API 文档
~~~

常用的调用关系如下：

~~~text
task_env.make_env(...)
    → scene assembly → task lifecycle → observation/reward/info

task_env.make_parallel_env(...)
    → parallel capability → batch runtime → local/remote vector lifecycle

task_env.script.*
    → 调用上述 public API，不直接替代 task、runtime 或 solver
~~~

## 安装

~~~bash
python -m pip install -e .
python -m pip install -r task_env/requirements.txt

# 并行环境、SB3 或 PPO 需要
python -m pip install -r task_env/requirements-rl.txt

export PYTHONPATH=GeoPhys/src:.
~~~

CPU 可以运行基础环境和 smoke；CUDA 训练与大规模并行需要可用的 NVIDIA 驱动。推荐使用仓库已有的 geophys Python 环境。

查看当前注册环境：

~~~bash
PYTHONPATH=GeoPhys/src:. python - <<'PY'
import task_env

print("single:", task_env.ENV_REGISTRY.uids())
print("parallel:", task_env.PARALLEL_ENV_REGISTRY.uids())
PY
~~~

## Quickstart

### env：创建、配置和运行环境

#### Python public API

~~~python
from task_env import make_env

env = make_env(
    "pendulum-v1",
    config={"runtime": {"backend": "cpu"}},
)
try:
    observation, info = env.reset(seed=73)
    for _ in range(100):
        observation, reward, terminated, truncated, info = env.step(
            env.action_space.sample()
        )
        if terminated or truncated:
            observation, info = env.reset()
finally:
    env.close()
~~~

单环境遵循 Gymnasium 五元组接口：reset 返回 observation/info，step 返回 observation/reward/terminated/truncated/info。动作和观测的结构、shape、dtype 以 action_space 和 observation_space 为准。

#### script/env 入口

| 入口 | 作用 | 常用参数 |
| --- | --- | --- |
| task_env.script.env.single_inline | 内联配置创建单环境并短步进 | --env-id、--backend、--steps、--horizon、--seed |
| task_env.script.env.single_from_file | 从公共 YAML 创建单环境 | --env-id、--env-config、--backend、--steps、--horizon |
| task_env.script.env.parallel_inline | 创建 remote 同构并行环境并短步进 | --env-id、--backend、--num-env、--steps、--seed |
| task_env.script.env.parallel_from_file | 从公共 YAML 创建 remote 并行环境 | --env-id、--env-config、--backend、--num-env、--steps |

~~~bash
# 单环境：默认示例为 PickCube，也可以替换为 pendulum-v1
PYTHONPATH=GeoPhys/src:. python -m task_env.script.env.single_inline \
  --env-id pendulum-v1 --backend cpu --steps 3 --horizon 10

# 单环境 YAML
PYTHONPATH=GeoPhys/src:. python -m task_env.script.env.single_from_file \
  --env-id pendulum-v1 \
  --env-config task_env/doc/api/examples/pendulum_cpu.yaml \
  --backend cpu --steps 3 --horizon 10

# 并行环境：默认使用 remote worker
PYTHONPATH=GeoPhys/src:. python -m task_env.script.env.parallel_inline \
  --env-id pendulum-v1 --backend cpu --num-env 4 --steps 3

# 并行环境 YAML
PYTHONPATH=GeoPhys/src:. python -m task_env.script.env.parallel_from_file \
  --env-id pendulum-v1 \
  --env-config task_env/doc/api/examples/pendulum_cpu.yaml \
  --backend cpu --num-env 4 --steps 3
~~~

inline/file 示例会写出环境摘要，默认输出位于 temp_outputs/task_env 下。需要在当前进程调试时，直接使用 make_parallel_env(..., execution="local")；需要隔离 learner 和 simulator 时，使用 execution="remote"。task_env.script.environment 是 single_inline 的兼容入口。

### camera：相机 observation 与 UI render

TaskEnv 中有两种相机用途：

- camera/static.py、camera/bound.py 采集 public camera observation，分别对应 world-fixed camera 和 site-bound camera；
- render_single.py、render_parallel.py 展示 UI frame，分别对应单环境和选定并行 world，不改变 physics 或 task observation 语义。

#### camera observation

这两个脚本默认使用 PickCube、raytracer 和 32×24 相机，并把 RGB/summary 写入 temp_outputs/task_env：

~~~bash
PYTHONPATH=GeoPhys/src:. python -m task_env.script.camera.static --backend cpu
PYTHONPATH=GeoPhys/src:. python -m task_env.script.camera.bound --backend cpu
~~~

static 用固定 world frame 相机；bound 用 site-bound 相机，并在 reset 后推进一步验证 parent pose 与图像变化。无 CUDA 时可以显式使用 cpu。

#### UI render

~~~bash
# 单环境 RGB/offscreen
PYTHONPATH=GeoPhys/src:. python -m task_env.script.render_single \
  --env-id pendulum-v1 --mode rgb_array \
  --backend cpu --render-backend rasterizer --steps 3

# 单环境 headed window
PYTHONPATH=GeoPhys/src:. python -m task_env.script.render_single \
  --env-id pendulum-v1 --mode human \
  --backend cuda --render-backend rasterizer

# 并行 selected-world 网格
PYTHONPATH=GeoPhys/src:. python -m task_env.script.render_parallel \
  --env-id pendulum-v1 --num-env 4 --parallel-render-num 4 \
  --mode human --backend cuda --render-backend rasterizer
~~~

render_parallel 还支持 width、height、columns、cell-width、cell-depth、padding、steps、seed 和 sleep。无显示服务器时将 mode 改为 rgb_array；human 模式需要图形会话。

#### camera/render 专项脚本

| 入口 | 用途 | 关键参数 |
| --- | --- | --- |
| task_env.script.camera_lighting_probe | 对比当前/legacy lighting 配置 | --mode current/legacy、--backend、--output |
| task_env.script.render_input_probe | 检查 render input 和窗口输入 | --arch、--width、--height、--fps-limit |
| task_env.script.flora_go2_single_smoke | Flora Go2 单资产 smoke | --module-dir、--width、--height、--force |

camera observation 与 UI render 的结果不要混用：前者进入 observation tree，后者只产生展示帧。

### rl：PPO、checkpoint 和评估

#### Pendulum native SB3 PPO

pendulum_ppo.py 使用 remote homogeneous batch 和 SB3 PPO，适合验证并行环境、rollout 和 return curve。关键参数为 num-env、backend、batch-physics-layout、static-template-profile、integrator、updates、rollout-steps、seed、output-dir、save-log 和 verify-batches。

~~~bash
PYTHONPATH=GeoPhys/src:. python -m task_env.script.rl.pendulum_ppo \
  --num-env 8 --backend cpu \
  --batch-physics-layout merged_scene \
  --integrator implicitfast \
  --updates 3 --rollout-steps 5 \
  --output-dir temp_outputs/task_env/pendulum_ppo_quickstart \
  --save-log
~~~

如果需要测试当前 src/solvers/rigid/batch 的 Pendulum 路径，使用与该 profile 匹配的显式配置：

~~~bash
PYTHONPATH=GeoPhys/src:. python -m task_env.script.rl.pendulum_ppo \
  --num-env 256 --backend cuda \
  --batch-physics-layout static_template \
  --static-template-profile rigid_batch_v1 \
  --integrator euler \
  --updates 3 --rollout-steps 5 \
  --output-dir temp_outputs/task_env/pendulum_rigid_batch
~~~

#### 统一 RSL-RL PPO

rsl_ppo.py 是 Go2 和其他已声明 RSL profile 任务的统一训练入口：

~~~bash
PYTHONPATH=GeoPhys/src:. python -m task_env.script.rl.rsl_ppo \
  --env-id go2-walk-v1 \
  --num-env 256 \
  --iterations 10 \
  --rollout-steps 24 \
  --sim-device cuda \
  --rl-device cuda:0 \
  --output-dir temp_outputs/task_env/go2_ppo_quickstart \
  --save-interval 5
~~~

常用参数包括 env-id、num-env、iterations、rollout-steps、seed、sim-device、rl-device、env-config、output-dir、log-dir、save-interval、checkpoint-out 和 resume。render 与 hard-render 互斥：

~~~bash
# 使用任务 YAML overlay
PYTHONPATH=GeoPhys/src:. python -m task_env.script.rl.rsl_ppo \
  --env-id go2-walk-deploy-height-v1 \
  --env-config task_env/tasks/go2_walk_deploy/domain_randomization_curriculum.yaml \
  --num-env 256 --iterations 10 --rollout-steps 24 \
  --sim-device cuda --rl-device cuda:0 \
  --output-dir temp_outputs/task_env/go2_height_quickstart

# 普通并行展示或 Go2 asset 展示
PYTHONPATH=GeoPhys/src:. python -m task_env.script.rl.rsl_ppo \
  --env-id go2-walk-v1 --num-env 256 --iterations 2 \
  --rollout-steps 24 --sim-device cuda --rl-device cuda:0 \
  --render --output-dir temp_outputs/task_env/go2_render_quickstart
~~~

训练输出包括 checkpoint、TensorBoard event 和 train summary；resume 可接收 checkpoint 或运行目录。

#### Go2 held-out evaluator

需要先准备 current-RSL checkpoint：

~~~bash
PYTHONPATH=GeoPhys/src:. python -m task_env.script.rl.go2.go2_ppo_eval \
  --checkpoint temp_outputs/task_env/go2_ppo_quickstart/model_5.pt \
  --env-id go2-walk-v1 --num-env 32 --steps 200 \
  --sim-device cuda --rl-device cuda:0 \
  --output-dir temp_outputs/task_env/go2_eval
~~~

该脚本记录 rollout return、episode length、termination/timeout、device 和 transfer metadata，不负责训练。

#### MuJoCo Go2 evaluator/helper

go2_mujoco_eval.py 使用 checkpoint 做独立 MuJoCo actor rollout，go2_mujoco.py 用于单次 MuJoCo action/viewer smoke：

~~~bash
PYTHONPATH=GeoPhys/src:. python -m task_env.script.rl.go2.go2_mujoco_eval \
  --checkpoint temp_outputs/task_env/go2_ppo_quickstart/model_5.pt \
  --env-id go2-walk-v1 --steps 1000 --device cpu \
  --output-dir temp_outputs/task_env/go2_mujoco_eval

PYTHONPATH=GeoPhys/src:. python -m task_env.script.rl.go2.go2_mujoco \
  --steps 1 --output temp_outputs/task_env/go2_mujoco_one_step.json
~~~

MuJoCo evaluator 的 checkpoint observation contract 必须与 env-id 对应；height-deploy 可以额外传入四维 command。

### trajectory：收集、回放、合并和转换

trajectory package 提供 collect、replay、merge 三个组合命令：

~~~bash
# 收集 PickCube/NutAssembly source trajectories
PYTHONPATH=GeoPhys/src:. python -m task_env.script.trajectory collect \
  --env_id pick-cube-v1 \
  --backend cpu --num-traj 1 --horizon 600 --no-render \
  --output temp_outputs/task_env/trajectories/source.h5

# 回放 trajectory collection
PYTHONPATH=GeoPhys/src:. python -m task_env.script.trajectory replay \
  --trajectory temp_outputs/task_env/trajectories/source.h5 \
  --backend cpu \
  --output temp_outputs/task_env/trajectories/replayed.h5

# 合并目录下的 H5 collection
PYTHONPATH=GeoPhys/src:. python -m task_env.script.trajectory merge \
  --input_dir temp_outputs/task_env/trajectories \
  --output temp_outputs/task_env/trajectories/merged.h5
~~~

collect 还支持 env_config、seed、gripper-force、vis、camera-size 和 max-attempts；replay 支持 replay_config、backend 和 vis。

#### 单条 public solution 记录

record.py 针对 PickCube/NutAssembly 的 public solution 生成 H5 v2：

~~~bash
PYTHONPATH=GeoPhys/src:. python -m task_env.script.trajectory.record \
  --env-id pick-cube-v1 \
  --backend cpu --horizon 600 --no-render \
  --output temp_outputs/task_env/trajectories/pick_cube.h5
~~~

record 只消费 public reset/step/info/metadata，不读取 solver private state。H5 基本长度关系为 len(observation)-1 == len(action) == T。

#### Panda trajectory offline API

~~~bash
# 转换 Panda/controller action schema
PYTHONPATH=GeoPhys/src:. python -m task_env.script.trajectory.convert \
  --input source.h5 --output converted.h5 \
  --target-mode absolute_pose --target-reference world

# 回放并检查 Panda trajectory
PYTHONPATH=GeoPhys/src:. python -m task_env.script.trajectory.replay \
  --trajectory converted.h5 --backend cpu --require-exact
~~~

planning/pick_cube.py 和 planning/nut_assembly.py 是 task-owned solution 示例；planner.py、recorder.py 等根级 script 仍作为兼容入口保留。

## 进一步阅读

- [文档入口](doc/index.md)：按使用者、任务开发者和资产开发者分类。
- [训练与采集](doc/新手使用训练与采集.md)：RL、SB3、RSL-RL 和 H5 细节。
- [自定义任务](doc/自定义任务构建指南.md)：创建新的 TaskEnv task family。
- [资产导入与二次开发](doc/资产导入与二次开发指南.md)：添加 robot、object 和 world。
- [API Reference](doc/api/index.md)：公开 API、配置、并行和数据契约。
