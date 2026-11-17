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

`TransitionRecorder.begin_episode()` 会先复制并检查初始观测及元数据；若复制或容量检查失败，先前已冻结的轨迹仍可读取，修正输入后可重试。

selected scalar 录制在开始时记录实际动作和观测绑定函数的源码文件摘要；绑定函数若无法追溯到文件，录制启动会拒绝，修正后可在该 reset 边界重试。摘要反映录制开始时的文件字节，不单独证明 provider 运行或任务成功。

- [Wrapper lifecycle](wrapper_lifecycle.md)
- [Trajectory contract](trajectory_contract.md)
- [H5 schema](h5_schema.md)

## 如何选择记录路线

单环境 selected 的 `start_recording` 在 reset 边界开始，`finish_recording` 完成后再 close；canonical outer 保存 T 次 transition/T+1 次 boundary，execution stream 还保存已完成的 native 子步。structured v3 和 device recorder 有自己的 typed 控制、事件与边界，旧 Gym wrapper 则使用 generic H5；先看 schema 和来源，不能按文件名猜格式。

Recorder 接收环境已经提交的事实，不是控制或推进 owner。读取时核 T/T+1、时钟、source、实际 action/ACK 和同运行 close；metadata 中的声明 Solution identity、实际 transition 来源、Task outcome 和 Solution completion 分开解释。旧数据没有字段就保留未知，不补造。依次阅读 [wrapper 生命周期](wrapper_lifecycle.md)、[轨迹合同](trajectory_contract.md) 和 [H5 格式](h5_schema.md)；独立 reader 不等于重放或物理成功。
