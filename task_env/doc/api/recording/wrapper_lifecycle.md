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

## Selected scalar：环境自己的记录入口

selected 环境不需要额外包这一 classic wrapper。先成功 reset，调用 `start_recording(path)` 保存初始边界；每次 `step` 只有在物理间隔和记录 append 都完成后形成 transition。调用 `finish_recording(reason)` 冻结并写文件，`close()` 释放 session。文件已存在会拒绝覆盖；不完整的 native interval 或 fault 不能作为完整轨迹结束。结束时即使没有任务成功，也可以如实使用 `external_stop`，不能由停止原因推断 Solution 完成。

```python
from pathlib import Path
import numpy as np
from task_env import make_env
from examples._common import load_recording_summary

path = Path('one-step.h5')
env = make_env('nut-assembly-outcome-reference-v1', config={
    'execution': {'physics_provider': 'mujoco', 'physics_backend': 'cpu', 'deployment': 'in_process'},
    'episode': {'horizon': 10},
})
try:
    obs, info = env.reset(seed=19)
    pose = env.state.pose_world['panda-v1/ee']
    action = np.asarray([*pose.position, *pose.quaternion_wxyz, 1.], dtype=np.float64)
    action[0] += .001
    env.start_recording(path)
    obs, reward, terminated, truncated, info = env.step(action)
    env.finish_recording('external_stop')
finally:
    env.close()
summary = load_recording_summary(path)
assert summary['boundaries'] == summary['transitions'] + 1
print(summary['action_origins'])
```

本例的普通动作没有实际 Solution identity，完成保持未评估；metadata 仍携带声明身份以兼容旧 canonical schema，应读取 transition 来源判断实际执行。7c002 中同类 MuJoCo 操作有真实记录和独立读回；此代码块本身为静态核对。由 `start_recording` 到 `finish_recording` 期间如要 reset，先按该路线结束当前录制，不把新 episode 的首帧拼入旧轨迹。

## `VectorTransitionRecorder`

**Kind**：class；**Defined in**：`recorders/vector.py`

构造签名为 `VectorTransitionRecorder(venv, *, path=None, name_prefix="trajectory", config=None, record=True, env_ids=None, observation_paths=None)`。其中选择性 `env_ids` / `observation_paths` 限 device batch；它使用
`make_parallel_env` 已有的 `reset`/`step_async`/`step_wait` 协议，不导入 Stable-Baselines3；兼容旧调用名
`VectorTransitionRecordWrapper` 仍作为别名保留。它通常包在
raw `HomogeneousVectorTaskEnv`/`RemoteBatchVecEnv` 之上、SB3 flatten wrapper 之下。每个 vector slot 独立维护
`TransitionRecorder`；slot 的 `done` 到达时，以 `terminal_observation` 结束并立即写出一个 single-file H5 v2，
然后只用该 slot 的 autoreset observation 开启下一条录制。`saved_paths` 返回已经保存的文件；文件不把整个
batch 拼成一条 trajectory，仍满足 observation `T+1`、transition `T`。每个文件的
`meta/env_cfg.batch_provenance` 与 `meta/env_meta.batch_provenance` 标识 slot、batch size、backend、physics
layout、capability profile 和 exact-capacity policy。

该 wrapper 的 legacy host autoreset 语义不等于 G06 coordinated device same-step。设备批量应使用其显式记录入口：terminal boundary 与随后选中行的 reset boundary 分开记录；partial reset 不应改写其他 slot，也不能在 same-step 已自动重置后再用旧 wrapper 重置。具体受测范围见[学习器边界](../appendix/learner_integrations.md)和[版本能力矩阵](../../../../docs/module/task_env/v2.1.1/capabilities/capability-matrix.json)。
