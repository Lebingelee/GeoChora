# 录制、回放、Learning 与 Rendering

## 复用现有录制 owner

通用环境使用 `task_env.recorders`：`TransitionRecordWrapper`、`TransitionRecorder`、
`RecorderConfig`、`FrozenTrajectory` 和 `VectorTransitionRecorder`。
Selected reference examples 通过 env 的 `start_recording(path)`/`finish_recording(reason)`
复用 `task_env/trajectory/canonical/` 的 CanonicalRecorder/ExecutionRecorder，不能另造 schema 或混为通用 H5 v2。

当前 selected 录制 starts exactly once at reset boundary，已有 path 抛 FileExistsError；
未完成 interval 不可 finalize 为有效轨迹。保存 TaskArtifact、ResetSample/realized state、ExecutionSpec、
timebase、Core/provider/controller/solution/source/config identities。PickCube canonical-v0 为 outer boundaries；
NutAssembly execution stream 另保留 native application receipts。两者保留各自格式。
Selected owner snapshots 明确 `d0_reconstructible=False`，只是 observation receipt；没有完整
controller/expert restoration。对 source identity 的限制见[known limitations](../../releases/v1.1/known-limitations.md)。

## T/T+1、raw H5 与 wrappers

T 个 transitions 必须有 T+1 个 observations/boundaries；action/reward/success/terminated/truncated/info
均对齐 T。request/canonical action、target、applied control 分别保留。冻结轨迹校验长度、shape、finite 值与 metadata。
通用 v2 (`schema_id="task-env-h5"`) 保存 raw tree，禁止 `flatten_observation_paths`/`flatten_action`；
SB3 flatten 不改变存储 contract。RGB 可按既有规则量化为 uint8，其他 leaves 不改变。
具体 layout/shape 由实际 observation schema 和 universal_action_schema 声明，不能给 non-arm 填 Panda 八维。

Phase II C05a 添加通用 H5 v3：通过原 `TransitionRecorder` 的 `structured_control` 扩展槽保存 typed
`StructuredControlTransitionV1`，并在同一格式 owner 保存版本化 `BoundaryEventV1` 和必须显式提供的
`EpisodeOutcomeV1`。T 条控制记录对齐 T transitions，事件只引用 0..T 的现有 boundary；T=0 可以只有初始
observation、事件和 outcome，不生成伪 action。v3 仍保存 raw action/universal-action datasets；
`load_structured_control_records_h5()` 读取并校验结构化记录，
`load_structured_training_actions_h5()` 只允许单一 writer、完全相同的 action schema id/component order，
并逐值核对训练向量与已落盘 action dataset。多 writer 或投影不一致均拒绝；不能自动 flatten action tree。
旧 task-env-h5/v2 与 geophys-transition-h5/v1 的写入、读取和 fixture 不变；现有 Stage 11 transcode 明确拒绝
v3，Collection v1 仍只包装完整 v2 episode。

Selected canonical outer 也保留既有 `canonical-trajectory-v0`，新增 `canonical-trajectory-v1`，在相同
`CanonicalRecorder`/H5 owner 中版本化结构化控制、事件和 outcome；v1 的单 writer action/target/applied 必须与
现有 Panda `TransitionRecord` 完全一致。`canonical.h5.load()` 负责 v0/v1 精确 dispatch；
`canonical.h5.training_actions()` 仅执行声明 schema/component order 的无损单 writer 投影。
Execution stream 从 v1/v2 保留原 schema，新增 v3：现有 `ExecutionRecorder` 接收每个有效 interval 的结构化控制，
并在真实 boundary 记录事件、在 freeze 时要求 outcome；resident 与 streaming reader 都做版本、T/T+1、完整
substep、目标/施控链接、事件顺序和 outcome 校验。partial interval 不能 freeze。

`EpisodeOutcomeV1` 不回写最后一个 transition 的 `terminated/truncated`。`terminated` 必须关闭 bootstrap；
`truncated` 的 bootstrap 必须显式声明，不能由最后一条 transition flag 推断；两个 flags 都为 false 表示记录终止
不等同 episode 终止，并保留显式 bootstrap 决策。H5/JSON roundtrip 只证明存储完整性，不证明物理 replay、D0
恢复或 qualification。当前 selected replay 路线明确不消费 canonical outer v1 的新控制/事件/outcome。

这些 C05a schema 是存储契约，不开放 structured action 的 Runtime dispatch，也不实现 C03b Stop；三个既有 Recorder
仍是各自格式的唯一 owner。

通用 wrapper states：UNRESET、ARMED、READY、RECORDING、STOPPED_TERMINAL、STOPPED_MANUAL。
reset 前 start 为 ARMED；READY start 包含当前 observation；terminal recording 需 reset 后 restart；
重复开始、未 begin append/end 或非法状态抛 RuntimeError；capacity 溢出分别为 OverflowError/MemoryError。
vector 每 slot 独立 trajectory，用 terminal_observation 结束后才接 autoreset observation，保存
slot/batch size/backend/layout/profile/exact-capacity provenance；不把 batch 拼成单条时间轴。

`meta/env_cfg`、`meta/env_meta` 为 YAML scalar，历史 JSON metadata 可读取；
`RecorderConfig(meta_only=True)` 不写历史 episode_meta。Collection v1 以 traj_NNN groups 包装
各自完整 v2 轨迹；merge 不串接时间序列。新增 field 须版本化，旧 Evidence 保持可读或有显式 migration。
细节见[H5 reference](../../../task_env/doc/api/recording/h5_schema.md)和
[wrapper reference](../../../task_env/doc/api/recording/wrapper_lifecycle.md)。

## 回放与离线验证

当前 root examples/recording 和 `task_env.script.trajectory.record` 使用 selected public UID；
`inspect_h5.py` 自动读取 canonical outer/execution 格式并检查 integrity/T+1，不执行 physics。其 `storage_roundtrip` 字段不代表执行了新的 save/load roundtrip。
`task_env.trajectory` 提供 inspect/validate、merge、transcode 和 replay verification；
`task_env.script.trajectory.convert` 是 Panda/controller action offline 转换。
`task_env.script.trajectory.replay` 的 legacy H5 路线要求显式 `--historical`，不是 selected-source 恢复承诺。

- D0：从 recorded state/feedback 与 versioned owners 重构 controller/Solution 行为和 targets。
- D1：直接执行 frozen native control/target stream，不重算 adaptive controller。
- D2：同一 frozen ResetSample 下，用 frozen RequestedAction 与 live state/feedback 重算 control。
- D3：固定 checkpoint/features/normalization/action contract 与 paired samples 的 learned-policy portability；
  software load/contract portability 与 task outcome 分别报告。

D1 的 native control 与 canonical-target 具体层次必须由 campaign manifest 指明。
H5 save/load equality、roundtrip 或完成 expert 均不证明 D0/D1/D2、跨 provider qualification 或 Judge approval。
Diagnostic shadow continuation 不得称 golden。历史各 campaign 原始 source/dirty facts 不改写。

## Learning 与 Rendering

Generic SB3/RSL-RL adapters IMPLEMENTED；当前有界学习是 Pendulum × GeoPhys CPU ×
merged_scene × 2 env × 4 timesteps 的单次 PPO update，属于 wiring，无 convergence/一般训练 qualification。
RSL CLI 要求显式 `--env-id`、homogeneous registration 和 learner-contract admission；
provider-free checks 不等于 native RSL training。PickCube/NutAssembly 不是默认 PPO targets。
历史 manipulation state-policy bounded approvals 只适用于其 frozen source/checkpoint/sample envelope；
没有当前 manipulation checkpoint inference 或一般 PPO 声明。复用 learner 算法，不在 Core 复制 agent_factory。

当前 native rasterizer RGB smoke 只覆盖 Pendulum × GeoPhys CPU × scalar TaskEnv，以及
Pendulum × GeoPhys CPU × merged_scene batch。Renderer Registry、Camera、Flora contracts 保留；
fake Flora endpoint tests 不授予 native Flora 或 manipulation × Flora，亦无通用 Physics × Renderer 资格。
render.single/camera historical CLIs 明确退休，替代的 Pendulum examples 不构成一般 replacement。

有界示例与资源选项只维护在[examples README](../../../examples/README.md)；
任务/Experiment/Evidence/Judge 操作复用[已有 Skill](../../../task_env/.agents/skills/task-env-experiment-evidence/SKILL.md)。
