# Episode reset

**Import path**：`task_env.environment`  
**任务域**：Task Semantics  
**稳定性**：Public API / Extension API  
**职责**：描述 reset seed、初态及一次 episode 的公开状态。  
**调用者/消费者**：`BaseTaskEnv.reset()`、runtime boundary、task definition。  
**源码**：`environment/env.py`、`types.py`、`tasks/nut_assembly/reset.py`

`reset(seed=..., options=...)` 将 seed 交给 Gym 基类；当前实现丢弃 `options`，且 reset info 的 `reset_parameters` 是空 dict。每次 reset 应在首次 `step()` 前调用。

`InitialStateSpec(joint_positions=(), notes=())` 是命名初态描述，不含 solver 地址。`EpisodePhysicsState(qpos, qvel, qacc, ctrl, act)` 会复制并冻结 1-D float32 数组。`NutAssemblyResetSampler.resolve_initial_state(*, solver, compiled_scene)` 是 task-specific **internal hook**，由 assembly 调用，不是 solution API。
