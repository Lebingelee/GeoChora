# Dataset Recording

**Import path**：`task_env.recorders`  
**任务域**：Dataset Recording  
**稳定性**：Public API  
**职责**：按相应环境的记录入口记录 transition 并导出 H5。
**调用者/消费者**：rollout 脚本、离线数据使用者。  
**源码**：`task_env/recorders/`

classic Gym wrapper 与 selected 环境内的 canonical recorder 是不同入口：前者使用公开 reset/step 和 `get_record_metadata()`；selected 的 `start_recording`、`finish_recording` 与独立 reader 见 [Expert 录制示例](../../../../examples/recording/record_expert.py)。不要将 v2 wrapper 的字段与 selected 的 canonical 记录 schema 混为一谈。

- [Wrapper lifecycle](wrapper_lifecycle.md)
- [Trajectory contract](trajectory_contract.md)
- [H5 schema](h5_schema.md)
