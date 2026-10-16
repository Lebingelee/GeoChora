# P2.0-B S2-A：所选任务调用入口

S1/S1.6 已正常快进集成到公开 develop `77e194e2cac1ec82f7a39255a1eef0da9cd95ba8`。
本页描述独立待审阅的 S2-A 调用者迁移；不是 v1.0.1 发布或 S2-B 删除授权。

当前 capability 声明见 [current reference matrix overlay](capability_matrix_current.json)，不修改冻结 v1.0.0 matrix。

> 当前实现已叠加本地 S2-C1：PickCube task directory 收敛为四个文件，builder 从本页 S2-A 时点的 `tasks.pick_cube.reference` 移到 `tasks.pick_cube.task`。本页关于 S2-A caller migration 的原始 execution/evidence 记录保留不变；当前 task-authoring、删除路径、source identities 与新增 full-route receipt 见 [S2-C1 authoring receipt](p2_0_s2_c1_pickcube_authoring.md)。S2-C1 尚未推送或合并。

## 唯一 active route

| 入口 | task-owned construction | 唯一所选 Artifact / policy |
|---|---|---|
| `make_env('pick-cube-p16-reference-v1', config=...)` / `PickCubeReferenceEnv` | 当前 S2-C1：`tasks.pick_cube.task.build_reference` | 精确 `pick-cube-v1/p1_6_experimental_100hz`，不是 TB-100；版本化 readiness expert |
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

以上内容描述 S2-A/S1 时点的历史调用状态。S2-C1 后，PickCube 历史 task/candidate/helper/default recipe 模块已从当前 task directory 删除；`diagnostics.historical_tasks.make_historical_env('pick-cube-v1')` 明确拒绝并指向 immutable v1.0.0 source。其他 Phase I campaign/recovery scripts 中仍有旧直接 import；它们属于历史 recovery-only，必须运行于冻结 release 或不可变历史 commit，当前 develop 不提供 silent alias。S2-C1 删除模块、pre-C1 SHA/blob 与 v1.0.0 可用 blob 见 [source identity migration record](p2_0_s2_c1_source_identity.json)。

精确逐文件清单、所有可解析 import caller 和 literal-reference caller 见
[S2-B dependency manifest](p2_0_s2_b_deletion_manifest.json)。这是静态 inventory，动态/外部调用者不能据此被认定不存在。
active inheritance、yaw helper、task spec/constants、source fingerprint、profile 和 assets 的依赖文件均为删除阻塞项，不能整文件删除。
trajectory record CLI 的结果门控已修复并通过 provider-free 回归：失败或不完整轨迹仍会 finalize，但退出码为非零；另有一项单周期合成检查真实写入并重新读取 canonical H5。
历史-only 候选也必须先有逐文件 recovery blob/hash、历史调用者归档/显式保留决定，以及维护者 S2-B 审阅。
不将旧实现复制到另一个 active Core 目录。

Provider-free regression 为 162 passed、6 subtests passed（包括 CLI 成功/失败退出码，以及失败任务后真实 canonical H5 finalize/reload 用例）。从 S2-A task/runtime source `a59840fc31f1da8aa9cbb0f7ce99f31773b91b5d`，通过本页两个新的 public `make_env` UID 串行完成四条完整 100 Hz CPU 功能回归：PickCube GeoPhys/MuJoCo seed31，NutAssembly GeoPhys/MuJoCo NA-S0 seed19。随后 trajectory record CLI 修复提交 `0f27225a6cdc884c6ff8f921351917ac3db47a4d` 未改变 task builder、session、controller、Solution 或四条轨迹逻辑；独立 CLI finalize/reload 测试提交为 `57c98f9063e35d6c15f6f2664e2a1238a1eed885`。额外合成单周期 CLI 检查只验证退出状态与 H5 finalize/reload，不作为 provider physics 证据。每条原生轨迹均验证 T/T+1、provider controls、时钟、终态、录制 finalization 与 H5 roundtrip；NutAssembly 另验证 11 个阶段、retreat endpoint、native application 数及 readiness/outcome 分离。

PickCube GeoPhys 原始 runner 在 H5 finalization 后因 post-run verifier 错误退出 FAIL：它用绝对 `i*0.01` 与单 ULP 比较累计浮点时钟、把 grouped `session.step(substeps=5)` 的 substep 请求与直接 native-step 计数混为一项，并读取不存在的 `stage` 字段。保留该原始 FAIL receipt；独立 canonical H5 `validate()`、逐相邻边界时钟、task/expert 结果与 S1.5 seed31 GeoPhys H5 的全部 transition/boundary 对照均通过，故本报告将这一个功能结果标为 `PASS_RECONCILED`，不把包装器结果改写为 PASS。该比对没有首次 transition 或 boundary divergence。

NutAssembly 两个当前入口的 H5 和 11-stage receipt 均通过。新 GeoPhys 路线重现严格 `stable_height_mismatch`（step362，残差 -0.0002212406621264762m），并单独记录 warning、原 expert failed 状态与 outcome success；MuJoCo 严格 expert 完成且无 warning。两个 provider 的 stage receipts 和选定终端物理指标与对应 S1.6 证据逐项相同。完整数据、源映射、资源监测与比较 receipt 位于 ignored `workspace/maintenance/p2_0_part_b_s2_a_final_20261016/`，详见 [S2-A 最终审阅](p2_0_s2_a_final_review.md)。这是有界功能回归，不是历史 qualification 或新 D0-D2 决策。

`trajectory.record` 的结果门控已在提交 `0f27225a6cdc884c6ff8f921351917ac3db47a4d` 修正：录制仍会保留失败或不完整轨迹，但只有 task success 和所选完成策略均通过才返回退出码0；失败、termination、truncation/horizon stop 返回非零。12 个 provider-free CLI cases 覆盖 PickCube failure/task predicate、NutAssembly planned/outcome/override 条件、termination/truncation、两种退出码，以及失败后真实 H5 finalize/reload；同时确保严格 Expert failure 不会覆盖一个已完成且获准的 NutAssembly outcome。合并前仍需维护者决定显式公共 API 移除的版本与外部迁移策略。

SATA 单盘风险和独立备份不足仍未解决；监测新 ATA/SATA/I/O 错误即停止。
Go2/static physics、通用 Batch/Device/Learner、provider、controller、recorder 和 renderer 合同不在本次 retirement 范围。
