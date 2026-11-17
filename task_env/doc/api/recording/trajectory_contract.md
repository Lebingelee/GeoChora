# Trajectory contract

**Import path**：`task_env.recorders.FrozenTrajectory`  
**任务域**：Dataset Recording  
**稳定性**：Public API  
**职责**：定义不可变内存轨迹的长度不变量。  
**调用者/消费者**：`TransitionRecorder`、H5 writer。  
**源码**：`recorders/trajectory.py`、`recorder.py`

## `FrozenTrajectory`

**Kind**：frozen dataclass；**Defined in**：`trajectory.py`

字段包括 `observations`、`actions`、`universal_actions`、`rewards`、`successes`、`terminated`、`truncated`、`infos`、`reset_info`、`record_metadata`、`stop_reason`，以及可选的 `structured_controls`、`boundary_events`、`outcome`。`transition_count` 是 `len(actions)`；`validate()` 要求 observations 为 **T+1**，各 transition 字段为 **T**，存在的 structured control 数量也为 **T**，并校验 outcome 与 boundary events，否则抛 `ValueError`。`universal_actions` 表示经过 controller/native adapter 的 canonical runtime-facing action；其维度和组件由 `universal_action_schema` 声明，不把 non-arm 强行填充为 Panda 八维。

## `TransitionRecorder`

**Kind**：class；**Stability**：Public API；**Defined in**：`recorder.py`

`begin_episode(initial_obs, reset_info, record_metadata)`、`append_transition(...)`、`end_episode(reason)` 维护冻结轨迹。未 begin 即 append/end 抛 `RuntimeError`；超过 `max_transitions` 抛 `OverflowError`，超过 `max_buffer_bytes` 抛 `MemoryError`。录制器按 `universal_action_schema.dimension` 校验 canonical action；Panda v1 仍必须为 `(8,)`，non-arm 使用自身 schema 维度。

## Selected 轨迹与独立读回

selected 的 canonical outer、native execution stream 和 structured v3 使用各自 schema，不是上面的 `FrozenTrajectory` 的文件别名。共同的不变量是 reset boundary 在前、每条完成的 transition 对应一个后续 boundary；每个边界要与 source、episode 和 clock 对齐。native stream 还要求每个 interval 内应用记录数量、顺序与 timebase 匹配。streaming writer 用有界编码缓冲保存现有语义，不代表丢弃状态或获得 D0 可重建能力；processing/export 属于轨迹工具，不修改环境。

```python
from pathlib import Path
from examples._common import load_recording_summary

summary = load_recording_summary(Path('episode.h5'))
assert summary['t_plus_one_valid']
print(summary['schema'], summary['transitions'], summary['boundaries'])
if 'action_origins' in summary:
    print(summary['expert_identity_role'], summary['action_origins'])
```

对本轮 selected canonical 路线，`action_origin_v1` 是每条已提交 transition 的来源；metadata 的声明 identity 或旧 `planned_action` 不能单独证明 Solution 完成。旧文件缺来源字段时显示未知，缺失/损坏字段或不匹配的时间序列由 reader 拒绝。此 reader 只检查落盘事实，Task success、caller 的 Solution done/failed 和环境 close 需与同次运行关联；[H5 schema](h5_schema.md)和[CLI](trajectory_cli.md)说明格式及适用范围。

[Trajectory implementations](../../../trajectory) own trajectory representations; [recorders](../../../recorders) own recording lifecycle.
