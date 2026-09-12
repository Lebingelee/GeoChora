# Trajectory contract

**Import path**：`task_env.recorders.FrozenTrajectory`  
**任务域**：Dataset Recording  
**稳定性**：Public API  
**职责**：定义不可变内存轨迹的长度不变量。  
**调用者/消费者**：`TransitionRecorder`、H5 writer。  
**源码**：`recorders/trajectory.py`、`recorder.py`

## `FrozenTrajectory`

**Kind**：frozen dataclass；**Defined in**：`trajectory.py`

字段包括 `observations`、`actions`、`universal_actions`、`rewards`、`successes`、`terminated`、`truncated`、`infos`、`reset_info`、`record_metadata`、`stop_reason`。`transition_count` 是 `len(actions)`；`validate()` 要求 observations 为 **T+1**，其余 transition 字段为 **T**，否则抛 `ValueError`。`universal_actions` 始终表示经过 controller/native adapter 的 canonical runtime-facing action；其维度和组件由 `universal_action_schema` 声明，不把 non-arm 强行填充为 Panda 八维。

## `TransitionRecorder`

**Kind**：class；**Stability**：Public API；**Defined in**：`recorder.py`

`begin_episode(initial_obs, reset_info, record_metadata)`、`append_transition(...)`、`end_episode(reason)` 维护冻结轨迹。未 begin 即 append/end 抛 `RuntimeError`；超过 `max_transitions` 抛 `OverflowError`，超过 `max_buffer_bytes` 抛 `MemoryError`。录制器按 `universal_action_schema.dimension` 校验 canonical action；Panda v1 仍必须为 `(8,)`，non-arm 使用自身 schema 维度。
