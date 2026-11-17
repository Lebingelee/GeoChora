# Environment creation

**Import path**：`task_env.make_env`、`task_env.make_parallel_env`、`task_env.registry`
**任务域**：Appendix  
**稳定性**：Public API / Extension API  
**职责**：按 UID 创建注册组件、single environment 或可选的并行环境。
**调用者/消费者**：用户脚本、内置注册模块。  
**源码**：`task_env/registry.py`、`task_env/vectorization/registry.py`、`task_env/vectorization/parallel.py`

### 源码职责边界

- `task_env/registry.py` 只保存 component class，并实现 `make_env()`、`make_agent()`、`make_object()` 和 `make_scene()`。
- `task_env/vectorization/registry.py` 只登记 task 是否显式具备 homogeneous parallel capability；不创建 runtime，也不保存 batch/CUDA 对象。
- `task_env/vectorization/parallel.py` 实现 `make_parallel_env()` 的 local/remote、SB3 adapter、进程隔离、seed/masked reset 和 autoreset 生命周期。
- `task_env/__init__.py` 只提供懒加载 public facade；`make_env()` 与 `make_parallel_env()` 不互相 fallback。

因此，`registry.py` 与 `vectorization/parallel.py` 的分工是有意的：前者是单环境/组件的登记与构造边界，后者是并行环境的运行时生命周期边界。

## `make_env` and registries

**Kind**：function / registry object；**Stability**：Public API；**Defined in**：`registry.py`

`make_env(uid: str, *, config=None, render_mode=None, **kwargs) -> TaskEnvironmentComponent`；`make_agent`、`make_object`、`make_scene` 分别创建对应组件。`ENV_REGISTRY`、`AGENT_REGISTRY`、`OBJECT_REGISTRY`、`SCENE_REGISTRY` 是 registry 实例。未知 UID 抛 `KeyError`；已退休的 PickCube、NutAssembly 和 Go2 旧 UID 抛带迁移提示的 `ValueError`。selected 与 classic-control 的 Task binding 不同，但使用共同环境 owner；详见 [API 入口](../index.md)。

最小用户调用顺序如下；配置只使用声明的公共 section，task topology 与 task-owned reward 不从脚本侧重写：

```python
from task_env import make_env

env = make_env("pendulum-v1", config={"runtime": {"backend": "cpu"}})
try:
    observation, info = env.reset(seed=73)
    observation, reward, terminated, truncated, info = env.step(
        env.action_space.sample()
    )
finally:
    env.close()
```

`ComponentRegistry(kind, expected_base)` 与其 `register(...)`、`decorator(uid, override=False)` 是 **Extension API**：注册会改变 registry 状态，`override=False` 时重复注册会失败。已注册 UID 应从 `registry.uids()` 获取，避免在文档中写死清单。

## Optional homogeneous parallel factory

`from task_env import make_parallel_env` 的 `make_parallel_env(uid, env_config=None, num_env=1, backend="cuda", execution="remote")` 是可选的并行入口。
`execution='device'` 是 G06 有界接收的正式设备 batch 路线：Pendulum/PickCube × `mujoco_warp`/`geophys`/`isaacsim`，使用 `step()`、same-step autoreset、部分 reset 和具名相机；见 [device 教程](../../../../docs/module/task_env/v2.1.1/guides/quickstart-device-batch.md)。`remote`/`local` 是旧 SB3 并行路线；登记本身不是当前多环境运行证据。组件并行入口只为通过 `@register_parallel_env()` 显式登记 framework batch capability 的任务创建同构 batch；没有 batch backend 的
task 会明确抛出 `task uid has no homogeneous parallel backend`，不会退化为 `num_env` 个 single env。

`execution="local"` 返回同进程 raw vector/SB3 adapter，适合契约 smoke；`execution="remote"` 使用
`multiprocessing` `spawn`，simulator child 只接收 UID、resolved config、batch size、backend 和 compile mode，
并在 child 内重新解析 parallel registry。该 IPC 不导入 `task_env.reporter`，也不使用 reporter 的 TCP/JSON 协议。

raw vector 只负责 batch 首维、seed、masked reset 和 terminal guard；任务的 observation、reward、termination、
reset profile、action schema 与 metadata 由 task definition 和 reset sampler 所有，公共物理批运行时由
`SceneBatchRuntime` 提供。`environment.TaskLifecycleAdapter` 负责 scalar/batch 共同的任务语义生命周期，
batch wrapper 只补充 batch runtime、seed/masked reset 与 slot info；任务只提供统一的 `TaskStateView` 语义，
不再实现 Pendulum-specific batch definition。SB3 flatten 和 autoreset 只发生在
learner/adapter 边界。

`env_config["runtime"]["batch_physics_layout"]` 与 `execution="local"|"remote"` 相互独立；当前只支持
`"merged_scene"`。自 public `develop` 集成 S4 后，显式请求已退休的 `"static_template"` 会 fail closed 并提示使用
`merged_scene`，不会静默切换布局。这里的 `local`/`remote` 控制旧并行路线；单环境物理部署使用配置中的 `execution.deployment`。`make_env(..., execution="device")` 则是明确的 B=1 设备入口，与上述选项不同。

`import task_env`、`from task_env import make_parallel_env` 不会提前加载 SB3、Torch、Taichi 或 Pendulum batch
runtime；具体依赖在真正选择 local/remote parallel execution 后才导入。

### Selected task-owned reference routes

The current selected manipulation UIDs are `pick-cube-p16-reference-v1` and
`nut-assembly-outcome-reference-v1`. Construct both through
`from task_env import make_env` with an explicit `provider`, `backend="cpu"`,
and bounded `horizon`, using the selected `execution` and `episode` configuration sections. They admit the current scalar CPU GeoPhys/MuJoCo
intersection. The NutAssembly example uses caller-owned `act → step(action) → observe`;
Solution proposals include the required source boundary and control request; legal ordinary world-pose arrays are admitted separately in 7c002. The root [developer examples](../../../../examples/README.md)
show task execution and canonical H5 recording without introducing another
environment or recording API.

The examples do not establish a new qualification, checkpoint result, or
Physics × Renderer capability. Generic parallel APIs remain independent of
these selected scalar task routes.

## 已验证的声明式 marker

先 import 示例模块注册 UID，再调用同一个 `make_env`；Task 声明 Robot、R1 与 source body，builder 负责 closure、composition 和绑定。注册成功本身不证明资源可用。

```python
import numpy as np
import examples.tasks.declared_marker
from task_env import make_env

env = make_env('marker-height-example-v1', config={
    'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu', 'deployment': 'in_process'},
    'episode': {'horizon': 10},
})
try:
    obs, info = env.reset(seed=19)
    pose = env.state.pose_world['panda-v1/ee']
    action = np.asarray([*pose.position, *pose.quaternion_wxyz, 1.], dtype=np.float64)
    action[0] += .001
    obs, reward, terminated, truncated, info = env.step(action)
    print(info['task_metrics']['marker_height_m'])
    obs, info = env.reset(seed=19)
finally:
    env.close()
```

7c002 marker-005 在 MuJoCo CPU 完成该生命周期并独立读回同运行 H5，等待独立主审；不存在的 UID、冲突配置或不匹配的 Robot/source 会拒绝。无此依赖的离线声明例不证明 native 创建成功。
