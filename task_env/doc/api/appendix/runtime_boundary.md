# Runtime boundary

**Import path**：`task_env.RuntimeBoundary`、`task_env.runtime`  
**任务域**：Appendix  
**稳定性**：Advanced boundary  
**职责**：限定 TaskEnv 与 GeoPhys runtime 的唯一物理边界。  
**调用者/消费者**：`BaseTaskEnv`、runtime bootstrap。
**源码**：`environment/protocols.py`、`runtime/`

## `RuntimeBoundary`

**Kind**：Protocol；**Defined in**：`environment/protocols.py`

成员为 `apply_reset_state(state)`、`apply_control(command)`、`step(*, substeps)`、`read_snapshot(request)`、`snapshot_state()`、`restore_state(state)`、`prewarm(profile="interactive")`。这是 framework integration contract，而不是用户控制入口。

`GeoPhysRuntimeBoundary`、`TaskRuntimeBootstrap`、`bootstrap_task_runtime` 是 advanced runtime API；不将 solver 内部布局、Taichi field、private runtime 方法、`ctrl` 或 `qpos` 写成 planner/recorder 可访问路径。
