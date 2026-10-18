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
