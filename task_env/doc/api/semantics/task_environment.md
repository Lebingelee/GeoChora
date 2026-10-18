# Task environment

**Import path**：`task_env.BaseTaskEnv`、`task_env.tasks.BaseTaskEnv`  
**任务域**：Task Semantics  
**稳定性**：Public API（使用）/ Extension API（子类 hooks）  
**职责**：组合组件、维护 Gym reset/step 生命周期。  
**调用者/消费者**：用户、wrapper、内置 task。  
**源码**：`task_env/environment/env.py`

## `task_env.tasks.BaseTaskEnv`

**Kind**：class；**Defined in**：`environment/env.py`（`tasks/base.py` re-export）

### Signature

`BaseTaskEnv(config: ResolvedEnvConfig | None = None, *, build_runtime: bool = True)`

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
`env.binding` AttributeError，详见[故障说明](../../../../docs/module/task_env/troubleshooting.md#已复现的-cli-缺陷)。完整参数矩阵见
[`doc/api/examples/index.md`](../examples/index.md)。当前 manipulation UIDs 与
expert/recording 入口见仓库根目录 `examples/README.md`；历史 `pick-cube-v1`
不会映射到新的 selected task。
