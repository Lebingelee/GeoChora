# H5 schema

**Import path**：`task_env.recorders.RecorderConfig`  
**任务域**：Dataset Recording  
**稳定性**：Public API  
**职责**：区分 generic raw、selected canonical 与 structured/device 记录及其读回合同。
**调用者/消费者**：`TransitionRecorder.save_h5()`、离线读取器。  
**源码**：`recorders/contracts.py`、`h5.py`、`flatten.py`

本页的 v2 和 collection 描述适用于以下 generic wrapper/recorder；selected 的 canonical H5 入口及独立读回见 [录制示例](../../../../examples/recording/record_expert.py) 和 [检查示例](../../../../examples/recording/inspect_h5.py)，不要把这两种记录路径当成同一 schema。

## Selected 记录与动作来源

selected 路线先 reset，再调用 `start_recording(path)`，在同一环境上 step，最后 `finish_recording(reason)` 并在 `finally` 中 close。canonical outer 记录 T 条 transition 和 T+1 个边界；execution stream 另外保存原生子步应用；structured/device 记录有自己的 typed control、边界事件和 episode end。具体入口与格式由实际 binding 选择，不能把 generic v2 的 dataset 结构套到所有 H5。加载器检查 schema、时间和关联；提交 ACK 不是独立力测量，单个 H5 也不替代同运行 caller 的完成与 close 事实。

旧 canonical metadata 的 `expert_identity` 是构建时声明的 Solution 身份，格式仍要求 SHA-256；录制开始时尚无动作，因此这个字段不能证明专家曾执行。新 transition 的 `expert_diagnostics.action_origin_v1` 以 JSON 字符串记录成功提交后的来源：`ordinary` 的实际 Solution identity 为 null、完成未评估；已校验 proposal 为 `solution_proposal` 并记录匹配身份；若 proposal 无法确认来源则标记 `solution_proposal_unverified` 而不宣称身份。旧文件没有该字段时来源是未知，不应反推。`planned_action` 是旧记录的 planned/hold 分类，不能单独证明专家计划轨迹完成；任务成功、Solution 完成和计划轨迹完成需分别依据实际字段和同运行 caller。

读取当前仓库示例产生的单条文件，可使用下列离线 reader（不启动环境）：

```python
from pathlib import Path
from examples._common import load_recording_summary

summary = load_recording_summary(Path('episode.h5'))
print(summary['schema'], summary['transitions'], summary['boundaries'])
print(summary['expert_identity_role'], summary['action_origins'])
assert summary['t_plus_one_valid']
```

此 reader 对旧 canonical 文件的缺失来源返回 `None`，不补造历史事实；v3 有独立字段合同，按具体 reader 使用。文件不存在、schema 或内容不匹配时读取会抛出异常。上面的来源字段已在 7c002 同运行 reader 中验证，独立主审前不作为全 provider 的接收声明。

## 结构化数据位置与核验

canonical execution v2 使用一维 `logical_json_utf8` 的 `uint8` 字节流，以及 T+1 长的 `control_step`、`native_step_index` 整数索引；它并非按每个字段建立独立 H5 dataset。使用 `task_env.trajectory.canonical.execution.load` 解码后，`transitions[i].record.applied_control` 是控制提交，`interval.substeps[j].applied` 与 `native_feedback_sample_v1` 是各原生子步的应用和反馈。不要把 ACK 解释成独立力传感。

structured v3 的 `meta/structured_controls_v1_json`、`meta/boundary_events_v1_json`、`meta/episode_outcome_v1_json` 是 UTF-8 JSON scalar：首项解码为 T 个 typed control，事件和结果分别遵循自己的合同。它们不是固定宽度的 float 数组；joint effort 和 body wrench 的资源、writer、单位、frame 与 6 分量值按记录的 schema 解释。device scene 的 boundary context 若存在，其 `scene_physical_v1` 中记录 producer、body key、binding、6 个有限数值和 `native_ack`；它只表明指定 worker 接收并完成对应推进。通用数值轨迹中的 `reward` 是 `(T,) float32`，success/terminated/truncated 为 `(T,) bool`；observation/action 的 shape 与 dtype 以各自 metadata 为准。

writer 对缺失 structured control、缺 EpisodeOutcome 或边界不一致抛 `ValueError`；`load_structured_control_records_h5` 检查 structured 结构、T/T+1、事件与 outcome；对具备相应 physical 记录的文件，`load_physical_recording_h5` 另行核验 source/boundary、资源绑定和 scene native ACK。RGB 字节没有独立内容 digest；不能把这些检查概括为对任意 H5 内容的完整防篡改。v2 generic、canonical execution 和 v3 的字段不得互相套用。

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
