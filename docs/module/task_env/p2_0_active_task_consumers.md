# P2.0-B S2-A：所选任务调用入口

S1/S1.6 已正常快进集成到公开 develop `77e194e2cac1ec82f7a39255a1eef0da9cd95ba8`。
本页描述独立待审阅的 S2-A 调用者迁移；不是 v1.0.1 发布或 S2-B 删除授权。

当前 capability 声明见 [current reference matrix overlay](capability_matrix_current.json)，不修改冻结 v1.0.0 matrix。

## 唯一 active route

| 入口 | task-owned construction | 唯一所选 Artifact / policy |
|---|---|---|
| `make_env('pick-cube-p16-reference-v1', config=...)` / `PickCubeReferenceEnv` | `tasks.pick_cube.reference.build_reference` | 精确 `pick-cube-v1/p1_6_experimental_100hz`，不是 TB-100；原 readiness expert |
| `make_env('nut-assembly-outcome-reference-v1', config=...)` / `NutAssemblyReferenceEnv` | `tasks.nut_assembly.reference.build_reference` | V2/V5/R3，100 Hz，`nutassembly-outcome-oriented-completion-v1` |

高级 API 的模块路径为 `task_env.tasks.{pick_cube,nut_assembly}.reference_env`。
共享 `tasks.reference_env.SelectedReferenceEnv` 只拥有 session/调用协调，不定义第二个 TaskDefinition、TaskArtifact schema 或任务成功谓词。
canonical evaluator、reset sampler、controller、Solution 与所选 construction 是任务语义权威。

配置只接收 `provider='geophys'|'mujoco'`、`backend='cpu'`、整数 `horizon=1..6000`。
默认 GeoPhys CPU、6000 步；无自动 provider/backend fallback。100 Hz 与 force cap 不允许调用者覆盖。
NutAssembly NA-S0 固定 provenance seed19；不同 seed 被拒绝，不伪造随机化。
render_mode、camera、旧 runtime/robot/episode overlay 或其他参数明确拒绝。
这些限制不改变其他任务的通用 make_env 配置合同。

```python
from task_env import make_env

env = make_env('nut-assembly-outcome-reference-v1',
               config={'provider': 'mujoco', 'backend': 'cpu', 'horizon': 6000})
try:
    observation, info = env.reset(seed=19)
    while not env.solution.done and not env.solution.failed:
        observation, reward, terminated, truncated, info = env.step_expert()
        if terminated or truncated:
            break
finally:
    env.close()
```

`step_expert()` 使用 reset 后该 env 实际拥有的 Solution/controller/arm-hold；不使用另一个 factory preview 的 expert。
PickCube 的 `step(action)` 是显式外部 absolute-pose/world/wxyz 8D 动作执行，不推进 expert、不伪造 outcome_complete。
所选 NutAssembly 的 `step(action)` 明确拒绝：只允许 `step_expert()`，避免外部动作绕过 guarded authorization。
同一 episode 禁止混用两种模式。返回值保持 observation/reward/terminated/truncated/info 的边界；不以瞬间 task_success 提前截断专家完整计划。
此适配器不是旧 BaseTaskEnv 或所有 Gym wrapper 的兼容实现。

PickCube 保持原整控制周期 ZOH stepping；不能以逐 native step 累加替代其严格时钟。
NutAssembly 复用 session 的物理率内环；task-owned `ReferenceArmSchedule` 仅生成原 public-ack 插值目标，session 负责步进。
所选 task-owned diagnostic 对照也调用这一 schedule/session 路径；历史与 shadow 分支保持显式历史工具。

实际 old/new 文件与 controller/recipe 身份及逐项不变合同检查见 [source identity migration](p2_0_s2_a_source_identity.json)。

## 调用者图与执行身份

- public facade → registry → task-owned ReferenceEnv → 唯一 reference builder → public scalar CPU control session。
- planning CLIs → selected UID → env-owned `step_expert` → 所选 Solution。
- state-only reporter v1/v2 fixtures → PickCube selected UID → 外部 `step(action)`；未运行 TCP，不代表相机或外部客户端重新验收。
- env single examples → selected UID → PickCube 当前 EE pose/open gripper 外部动作，NutAssembly 使用所选 guarded expert。
- record CLI → selected route → 现有 canonical H5 合同；不新建 TaskArtifact schema。
- selected reexecute CLI → 身份检查 → 同一 selected factory/expert 重新执行并逐 transition/boundary 比较；不注入历史 frozen controls，不宣称 D0。

NutAssembly info 独立记录 `task_success`、`planned_trajectory_completed`、`outcome_complete`、`readiness_warnings`、
`original_expert_lifecycle_status`、`execution_lifecycle_status` 和 selected policy execution complete/failed。
实测 inserted_on_peg AND released_nut、原 capture/authorization/force/budget 限制均由已有 Solution/evaluator 保持。
active path 不导入 DiagnosticShadowCoordinator，不使用通用 shadow override。

PickCube 录制使用既有 `task-env-canonical-trajectory-v0`，记录 outer ZOH target/ack 和 T+1 边界；不伪造逐子步观测。
NutAssembly 使用既有 canonical execution v2，记录每个实际 applied native substep、T+1 边界以及 outcome/warning 观察收据。
后者 observation owner receipt 明确不含完整 controller/expert restoration，不具备 D0 重建资格。
两者记录实际 adapter、construction、controller、Solution、配置与 provider 身份，保持不同录制格式的验真边界。

```bash
PYTHONPATH=.:GeoPhys/src python -m task_env.script.trajectory.record \
  --env-id nut-assembly-outcome-reference-v1 --provider mujoco \
  --seed 19 --output workspace/new-run/selected.h5
PYTHONPATH=.:GeoPhys/src python -m task_env.script.trajectory.replay \
  --trajectory workspace/new-run/selected.h5 --selected-reexecute \
  --output workspace/new-run/reexecution.h5
```

新 H5 路径必须不存在；录制 finalization 拒绝未完成 interval。此命令示例不是本次已运行完整轨迹的声明。
重执行要求匹配 source/config/controller/Solution/reset 身份；不把不同版本证据组合为一份验证。

## v1.0.1 迁移与兼容性审阅

| 旧入口 / symbol | 迁移与不兼容性 |
|---|---|
| `make_env('pick-cube-v1')` | 明确拒绝；调用者显式选择 P1.6 reference UID，不能默默替换旧控制频率/config |
| `make_env('nut-assembly-square-v1')` | 明确拒绝；新 UID 使用 measured release 与 Outcome V1，不能继承旧命令开夹捷径 |
| root/tasks `PickCubeEnv`, `NutAssemblyEnv` exports | 替换为具名 `PickCubeReferenceEnv`, `NutAssemblyReferenceEnv`；旧类仍在原 task.py，未删除 |
| task package old Solution/Config/ResetSampler/TaskDefinition/constants convenience exports | active construction 为 package `build_reference`；历史工具必须使用精确旧模块路径，不能把旧名 alias 到新语义 |
| PickCubeReadinessSolution/Config | 保留原 selected expert exports |
| trajectory record 的旧 env ID、camera、30N overlay 参数与旧 H5 v2 默认格式 | 明确不兼容；新 CLI 固定所选控制配置，使用现有 canonical 格式 |
| grouped collect/replay/merge | 默认 collect/replay 转到所选 canonical 单回合入口；旧 grouped H5 工具仅显式 `--historical-grouped` 恢复，不静默转换格式 |
| legacy trajectory replay | `--historical` 显式恢复旧语义；`--selected-reexecute` 为另一个具名执行模式，不是旧 H5 的透明升级 |
| reporter camera fixtures | 当前入口是 selected state-only；原 camera qualification 在冻结记录中保留，未宣称新 renderer 支持 |

这些是实际 public API 不兼容移除，**不能按普通 patch 兼容性宣称冻结 v1.0.1**。
维护者须在发布前审阅版本策略、外部调用者迁移和 release migration notice；本次不改变版本号。

## 历史与 S2-B 边界

旧 task.py、solution.py、candidate/helper、默认 YAML 等仍完整保留（仅移除旧 env registration）。
`diagnostics.historical_tasks.make_historical_env` 是明确 recovery-only 构造；不是第二个 active route。
旧相机/lighting/render/stage11_socket 与旧 H5 replay 使用此隔离入口；它们不建立当前 reference capability。
其他 Phase I campaigns、qualification/recovery tests 保留原显式源码路径和原 frozen source hash 检查。
当前旧模块发生 registration 源码身份变化，不能冒充 v1.0.0 的逐字节历史源码；严格恢复应 checkout 冻结 tag/commit。

精确逐文件清单、所有可解析 import caller 和 literal-reference caller 见
[S2-B dependency manifest](p2_0_s2_b_deletion_manifest.json)。这是静态 inventory，动态/外部调用者不能据此被认定不存在。
active inheritance、yaw helper、task spec/constants、source fingerprint、profile 和 assets 的依赖文件均为删除阻塞项，不能整文件删除。
历史-only 候选也必须先有逐文件 recovery blob/hash、历史调用者归档/显式保留决定，以及维护者 S2-B 审阅。
不将旧实现复制到另一个 active Core 目录。

Provider-free 150 tests / 6 subtests 与四个具名 8 步 CPU smoke 只覆盖新入口的有界行为，不等于完整轨迹验收。

S2-A 的完整新入口轨迹验收仍是 S2-B 前置条件：最小建议为两个任务 × 两个 provider，各一条具名 100Hz CPU 轨迹，
PickCube 使用 S1.5 seed31/reference 合同并对照其实测 Expert/task outcome，NutAssembly 使用 NA-S0 seed19 并要求 full plan/retreat、task_success/outcome_complete。
逐项比较 controller/requested action、物理终态、warnings、strict lifecycle 和 H5 finalization；不重复整个历史矩阵、不把旧失败改 PASS。
NutAssembly 每次可从 420 秒/2 GiB 监测预算开始，先检查可用资源；实际预算不足必须 TIMEOUT，不能推定通过。

SATA 单盘风险和独立备份不足仍未解决；监测新 ATA/SATA/I/O 错误即停止。
Go2/static physics、通用 Batch/Device/Learner、provider、controller、recorder 和 renderer 合同不在本次 retirement 范围。
