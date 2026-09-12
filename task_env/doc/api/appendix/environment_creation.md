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

`make_env(uid: str, config=None) -> TaskEnvironmentComponent`，`make_agent`、`make_object`、`make_scene` 分别创建对应组件。`ENV_REGISTRY`、`AGENT_REGISTRY`、`OBJECT_REGISTRY`、`SCENE_REGISTRY` 是公开 registry 实例。未知 UID 的行为以 `ComponentRegistry.get()` 的 `KeyError` 为准。

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
它只为通过 `@register_parallel_env()` 显式登记 framework batch capability 的任务创建同构 batch；没有 batch backend 的
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

`env_config["runtime"]["batch_physics_layout"]` 是并行物理布局选择，默认 `"merged_scene"`，因此省略该字段时
行为与既有 `SceneBatchRuntime` 相同。`"static_template"` 当前开放
`hinge_or_slide_no_contact_v1`、`articulated_fused_no_contact_v1` 与
`articulated_fused_ground_contact_v1` profiles：它们采用共享 immutable model 与 exact-B per-world state，
CPU/CUDA smoke 已通过；fused ground profile 只提供 analytic local ground rows。能力检查失败会明确抛出，不会悄悄切回
`merged_scene`。该字段不改变
`execution="local"|"remote"` 的进程语义，也不属于 single `make_env()` 的创建入口。

`import task_env`、`from task_env import make_parallel_env` 不会提前加载 SB3、Torch、Taichi 或 Pendulum batch
runtime；具体依赖在真正选择 local/remote parallel execution 后才导入。

可直接运行的单环境、并行、相机、轨迹和 PPO 命令见 [API examples](../examples/index.md)。
