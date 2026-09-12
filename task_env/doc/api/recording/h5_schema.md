# H5 schema

**Import path**：`task_env.recorders.RecorderConfig`  
**任务域**：Dataset Recording  
**稳定性**：Public API  
**职责**：写出单轨迹 raw H5 v2，并保留 v1 历史文件的 inspect 兼容。
**调用者/消费者**：`TransitionRecorder.save_h5()`、离线读取器。  
**源码**：`recorders/contracts.py`、`h5.py`、`flatten.py`

## `RecorderConfig`

**Kind**：frozen dataclass；**Defined in**：`contracts.py`

默认字段：`schema_id="task-env-h5"`、`schema_version="v2"`、`flatten_observation_paths=()`、`flatten_action=False`、`max_transitions=1000`、`max_buffer_bytes=512*1024*1024`、`h5_compression="gzip"`、`h5_compression_level=4`、`meta_only=False`。v2 只接受 raw tree：禁止 observation/action flatten；RGB 的 HWC/CHW 由 `CameraSpec` 决定。录制器在持有 observation 副本时，将 `rgb` 分支中有限的 `[0,1]` 或 `[0,255]` 图像量化为 `uint8`，以降低缓存与 H5 占用；其他叶子不变。

v2 的 `obs/*` 保存 T+1 帧，`action/*`、`reward`、terminal 与 `info/*` 保存 T 步。`meta/env_cfg` 与 `meta/env_meta` 都是 UTF-8 YAML scalar dataset；历史 JSON `env_meta` 仍可读取。`env_meta` 含 schema、timebase、leaf shape/dtype/order、RGB layout、action protocol 与 replay context。并行 `VectorTransitionRecorder` 还会在每个 slot 文件的 `env_cfg.batch_provenance` 与 `env_meta.batch_provenance` 中写入 slot、exact-B、backend、layout、capability profile 和 capacity policy，避免把不同 batch/layout 的轨迹混淆。兼容模式下 writer 仍可额外写出历史 `episode_meta`；`RecorderConfig(meta_only=True)` 和 grouped collect/replay/merge 只写 `env_cfg`、`env_meta`。

多轨迹采集使用 collection v1 容器：根 H5 只保存容器属性，每条轨迹位于 `traj_000`、`traj_001` 等子组；每个子组保持单轨迹 v2 的完整布局，包括 `obs/*`、`action/*`、`universal_action/*`、`meta/env_cfg` 和 `meta/env_meta`。`universal_action/*` 的组件由 `meta/env_meta.universal_action` 声明：Panda 保持历史 `arm_joint_position/gripper`，non-arm 使用自身 runtime actuator 组件。merge 不再把多条轨迹拼成一条时间序列，而是把兼容的轨迹组打包到同一容器中。

`save_trajectory_h5(trajectory, config, *, path, name, index) -> Path` 写 observation tree 的 leaf path、time-axis 数据和 metadata。具体 leaf 集由实际 observation tree 决定，不能将其简化为未证实的固定 `dict` schema。录制入口是
`python -m task_env.script.trajectory.record`；兼容入口 `task_env/script/recorder.py` 只转发到新实现。

Pendulum/双轮车的 raw tree 分别使用 `obs/state/proprioception` 与 `action/torque`；SB3 的 flatten 只发生在
`SB3FlattenVecWrapper` 边界，不改变 H5 v2 的 raw tree。`VectorTransitionRecorder` 将完成的每个 slot
写成独立 single-file v2，而不是创建未版本化的 batch dataset；slot provenance 随该文件保存。
