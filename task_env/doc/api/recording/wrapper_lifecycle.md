# Wrapper lifecycle

**Import path**：`task_env.recorders.TransitionRecordWrapper`  
**任务域**：Dataset Recording  
**稳定性**：Public API  
**职责**：以 Gym wrapper 截获公开 transition。  
**调用者/消费者**：采集脚本。  
**源码**：`recorders/wrapper.py`、`contracts.py`

## `TransitionRecordWrapper`

**Kind**：class；**Defined in**：`wrapper.py`

构造签名：`TransitionRecordWrapper(env, config: RecorderConfig | None = None)`。`start_record()` 在 reset 前将状态设为 `ARMED`，在 reset 后立即开始；在 `READY` 状态开始会写入当前 observation。`end_record() -> FrozenTrajectory` 仅在 recording 时可调用；`save_h5(path=None, name=None) -> Path` 转交 core recorder。

`RecordState`：`UNRESET`、`ARMED`、`READY`、`RECORDING`、`STOPPED_TERMINAL`、`STOPPED_MANUAL`。terminal recording 必须 reset 后才能 restart；重复开始或错误状态会抛 `RuntimeError`。wrapper 对 observation/action 可按 config flatten，但向底层 env 解码后仍调用公开 `env.step()`。

## `VectorTransitionRecorder`

**Kind**：class；**Defined in**：`recorders/vector.py`

构造签名为 `VectorTransitionRecorder(venv, path=None, name_prefix="trajectory", config=None)`。它使用
`make_parallel_env` 已有的 `reset`/`step_async`/`step_wait` 协议，不导入 Stable-Baselines3；兼容旧调用名
`VectorTransitionRecordWrapper` 仍作为别名保留。它通常包在
raw `HomogeneousVectorTaskEnv`/`RemoteBatchVecEnv` 之上、SB3 flatten wrapper 之下。每个 vector slot 独立维护
`TransitionRecorder`；slot 的 `done` 到达时，以 `terminal_observation` 结束并立即写出一个 single-file H5 v2，
然后只用该 slot 的 autoreset observation 开启下一条录制。`saved_paths` 返回已经保存的文件；文件不把整个
batch 拼成一条 trajectory，仍满足 observation `T+1`、transition `T`。每个文件的
`meta/env_cfg.batch_provenance` 与 `meta/env_meta.batch_provenance` 标识 slot、batch size、backend、physics
layout、capability profile 和 exact-capacity policy。
