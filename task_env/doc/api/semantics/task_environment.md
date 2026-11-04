# Task environment

**Import path**：`task_env.BaseTaskEnv`、`task_env.tasks.BaseTaskEnv`
**任务域**：Task Semantics
**稳定性**：旧 classic 路线及兼容入口；统一迁移尚未完成。
**职责**：本文先描述旧 classic 生命周期；selected 路线见下文。
**调用者/消费者**：用户、wrapper、内置 task。
**源码**：`task_env/environment/env.py`

## `task_env.tasks.BaseTaskEnv`

**Kind**：class；**Defined in**：`environment/env.py`（`tasks/base.py` re-export）

### Signature

`BaseTaskEnv(config: ResolvedEnvConfig | None = None, *, render_mode=None, build_runtime: bool = True)`

`reset(*, seed: int | None = None, options: dict[str, Any] | None = None)` 返回 `(observation, info)`；会应用初态、归零 elapsed steps、reset action/render/task definition。`step(action)` 返回 Gym 五元组 `(observation, reward, terminated, truncated, info)`：terminal 后再次 step 在 reset 前抛 `RuntimeError`。

### Lifecycle and extension hooks

`default_config()` 是 classmethod；`placement_notes()`、`create_scene_composer()`、`create_reset_sampler()`、`create_task_definition(compiled_scene)` 是供子类覆写的 Extension API。`composition_spec`、`get_env_metadata()`、`task_references` 是读取入口；未构造 runtime 时访问 runtime 相关成员抛 `StageUnavailableError`。`get_record_metadata()` 返回 recorder 使用的 JSON-compatible public projection。

### Example

```python
from task_env import make_env

env = make_env("pendulum-v1", config={"runtime": {"backend": "cpu"}})
try:
    obs, info = env.reset(seed=73)
    obs, reward, terminated, truncated, info = env.step(env.action_space.sample())
finally:
    env.close()
```

公共 reset/step 示例可直接执行；v1.1.0 的 `single_inline` Pendulum step 有已复现的
`env.binding` AttributeError，详见[故障说明](../../../../docs/module/task_env/v2.0.0/guides/troubleshooting.md#已复现的-cli-缺陷)。完整参数矩阵见
[`doc/api/examples/index.md`](../examples/index.md)。当前 manipulation UIDs 与
expert/recording 入口见仓库根目录 `examples/README.md`；历史 `pick-cube-v1`
不会映射到新的 selected task。

## 当前 selected 路线

`task_env.environment.reference_env.SelectedReferenceEnv` 是 selected 环境的当前实现 owner；`task_env.tasks.reference_env.SelectedReferenceEnv` 为兼容导入。PickCube 和 Nut 由 `make_env` 根据其 task class 与 selected 配置构造，并非上述 `BaseTaskEnv` 类对象。普通 selected `reset()` 不传 seed 时使用 19；显式 `seed=None` 与省略并不等价。Position 候选的 seed 受固定 reset plan 约束，mixed 候选有独立明确的 reset-plan 检查。普通 selected 非空 options 不支持。

规范 Env 的方向是外部 Solution 根据 observation 产生 action，调用方使用 `step(action)`；`step_expert()` 不是标准 Env API。selected 保留的 `step_expert()` 是受限兼容入口，`reset_for_solution()` / `step_with_solution()` 也仍由 Env 调用 Solution。NutAssembly 已支持调用方 `act → step(action) → observe`：action 包含来源边界与控制请求，Env 返回五样本 native receipt；裸数组仍拒绝。新路径完整物理成功尚未验证；各执行模式不能在同一 episode 混用。相关 step 调用返回 observation、reward、terminated、truncated、info。执行 fault 后必须 reset；`close()` 释放环境持有的 session，重复 close 幂等。selected 普通 public 配置当前 state-only，不接受 `render_mode`。Action/observation、termination 与 success 以实际任务和其 spaces、metadata、评估为准；不将 Panda 的输入维数套到 classic-control。统一生命周期和 `BaseTaskEnv` 同对象 alias 尚未完成，见[维护检查点](../../../../docs/module/task_env/v2.1.1/maintenance/reviews/pre-stage3-refactor-attempt001.md)。
