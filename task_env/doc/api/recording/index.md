# Dataset Recording

**Import path**：`task_env.recorders`  
**任务域**：Dataset Recording  
**稳定性**：Public API  
**职责**：按相应环境的记录入口记录 transition 并导出 H5。
**调用者/消费者**：rollout 脚本、离线数据使用者。  
**源码**：`task_env/recorders/`

classic Gym wrapper 与 selected 环境内的 canonical recorder 是不同入口：前者使用公开 reset/step 和 `get_record_metadata()`；selected 的 `start_recording`、`finish_recording` 与独立 reader 见 [Expert 录制示例](../../../../examples/recording/record_expert.py)。不要将 v2 wrapper 的字段与 selected 的 canonical 记录 schema 混为一谈。

对于记录 native 子步的 execution trajectory，记录器会在追加 transition 前检查实际记录的子步数量、顺序与时间基准；不完整 interval 会被拒绝，不会作为有效 transition 提交。若环境因此进入 execution fault，调用方须按环境的故障语义重置，不能把这段记录视为完整 episode。

Position 与 mixed 的 v3 录制在结束时核对终止原因、最后完整边界和 T/T+1 读回；mixed 录制初始化失败时不会保留半初始化的活动 recorder，修正问题后可在同一 reset 边界重试。

- [Wrapper lifecycle](wrapper_lifecycle.md)
- [Trajectory contract](trajectory_contract.md)
- [H5 schema](h5_schema.md)
