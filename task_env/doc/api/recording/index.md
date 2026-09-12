# Dataset Recording

**Import path**：`task_env.recorders`  
**任务域**：Dataset Recording  
**稳定性**：Public API  
**职责**：记录公开 Gym transition 并导出 H5。  
**调用者/消费者**：rollout 脚本、离线数据使用者。  
**源码**：`task_env/recorders/`

recorder 仅依赖 `reset()`、`step()`、metadata 与 `get_record_metadata()`；不访问 solver、runtime、controller private state 或 task private state。

- [Wrapper lifecycle](wrapper_lifecycle.md)
- [Trajectory contract](trajectory_contract.md)
- [H5 schema](h5_schema.md)
