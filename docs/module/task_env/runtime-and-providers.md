# Runtime、Provider 与控制生命周期

## 当前开发基线与有界证据（2026-10-22）

本地 `codex/phase-ii-c03b` 的保全检查点为 `b3fc42e`，包含 Provider pin 迁移与 C05b public lifecycle S1；当前工作区有
C05b S2/S3 probe、必要的 canonical-recording fault guard、测试及报告改动。GeoPhys Gitlink 与实际检出固定在
`a53a8cfed7c9d6464274b5c96fca601271dc4ee4`。此前 `ec2dd24`/`eb870f6f` 内容描述的是迁移前状态；2026-10-20 的
`54f40fbf` 同步范围和测试数字仍保留为历史 Evidence，不作为当前 topic 分支 Provider pin 或全链能力声明。

当前有界证据包括：旧 selected PickCube GeoPhys CPU reset-force freshness；新的 Scene-v3 Panda R1 candidate 在 GeoPhys
`a53a8cf` CPU 上的 `snapshot_v2()` typed raw-force publication、精确 admission 与一个真实 100 Hz interval；以及旧
PickCube legacy external Solution 在 GeoPhys CPU 与 MuJoCo 3.8.1 CPU 的真实 S2、canonical-v0 磁盘 S3。三者使用不同的
Artifact/source/Controller 路线，不能互相转移 plan identity。最后一项只证明指定 legacy PickCube consumer 路线；不授予
MuJoCo typed-force、通用 `actuator_force_query`、完整 C02b、其他任务或 Qualification。见
[freshness 收据](goal/Phase_II/C02b_R1_Reset_Force_Freshness_Acceptance.md)、
[typed-force 收据](goal/Phase_II/C02b_R1_Typed_Raw_Force_Admission_Acceptance.md)和
[C05b S2/S3 收据](goal/Phase_II/C05b_External_Solution_S2_S3_Acceptance.md)。

## GeoPhys 开发基线同步（2026-10-20）

本次将三个 Phase II 开发分支与 develop 的 GeoPhys 从
`c665ce5028a12bb4d2afe49f05e015fa9b684a39` 同步到
`54f40fbfffd945967525aa85801087e7da0b491e`。目标是已发布的 GeoPhys integration branch
`codex/geochora-main-sync-20261020`，包含上游 main
`4436787e` 的全部历史（相对共同基线新增 1,542 个 main 提交）和原有静态接触修复。
原有 Core main、v1.1.0 分支/tag、冻结 worktree 和 Menagerie Gitlink 不在更新范围。

GeoPhys 合并在 `solver_setup.py` 有一处内容冲突：保留混合场景中固定子树的零逆质量/逆惯量，
同时保留上游全固定树的处理与 armature 更新。新增三项数组级回归覆盖混合树、无 joint-range
的全固定树和旧移动树调用；solver 继续在 armature 更新后消除固定体接触 mobility。
Core selected bridge 改为通过 `ImportedScene.build_rigid_scene_model(use_imported_meshes=True)`
解析公开 mesh 表。旧的 False 路线在新 Provider 下会将 canonical asset ID 当作文件路径，
PickCube/NutAssembly reset 因 `mesh_required` 失败；没有采用忽略 mesh、替换 box 或私有状态补救。

本次实际验证范围如下，不转移 v1.1.0 的历史 acceptance/Qualification：

| 验证 | 结果与边界 |
| --- | --- |
| A01–A03、reference construction、selected consumers | 86 passed，7.39 s；包含旧 Artifact hash、schema 与 synthetic consumer 回归 |
| NutAssembly Outcome | 32 passed，146.69 s；现有纯语义/生命周期 detector |
| Render backend registry | 9 passed、6 subtests passed，4.66 s；native endpoints 替代测试 |
| GeoPhys 静态接触初始化 | 3 passed；数组级 oracle，不等同完整接触演化验收 |
| Pendulum × GeoPhys CPU | 真实 construct/reset/2 steps/close 通过，28.90 s |
| PickCube × GeoPhys CPU，seed 31 | 真实 reset/3 expert intervals/record/read/close 通过，63.07 s |
| NutAssembly × GeoPhys CPU，seed 19 | 同上，66.63 s；包含 native-rate interval 路线，未完成整段 Expert |
| PickCube / NutAssembly × MuJoCo CPU | 各 3 intervals 与录制读取通过，约 0.54 / 0.77 s |
| Camera geometry/admission | 26 个 pure checks 与正/负 admission 通过；跨 Provider pairing 仍拒绝 |
| GeoPhys CPU native static camera | 32×24 RGB/depth capture 通过，中心 optical-Z=2.0 m，4.93 s |

四条 selected 录制均为 3 transitions/4 boundaries、约 0.03 s；两任务 `world-v0` Artifact hash 保持
原值。这里的有界 horizon 不表示 task success 或 Expert completion，storage read 不表示 D0 replay。
没有运行完整 manipulation rollout、randomized feasibility、训练、CUDA、native Flora、一般 batch
或新的跨 Provider renderer qualification。首次合并套件在 120 s、拆分后的含 Outcome 套件在 90 s
预算下 TIMEOUT；按 detector 拆分并给 Outcome 240 s 后，上表各项通过，没有删除断言或放宽 tolerance。
CPU native probes 使用 180 s 墙钟预算，相机 120 s；native peak RSS 仅来自单进程统计，不是进程树上限。

可复现 pytest 路径为 `task_env/diagnostics/tasks/test_phase_ii_{artifact_identity,scene_structure,scene_composition}.py`、
`test_reference_construction.py`、`test_selected_consumers.py`、`test_nutassembly_outcome.py`（均在同一 tasks 目录）
及 `task_env/diagnostics/render/test_backend_registry.py`。使用现有 GeoChora Python、
`PYTHONPATH=GeoPhys/src:.`、`PYTHONDONTWRITEBYTECODE=1`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`，
执行 `python -m pytest -q -p no:cacheprovider <paths>`；无需新增安装方式。
Provider regression 位于 `GeoPhys/test/verification/rigid/test_static_contact_mobility.py`。
上述完整收据产生于 Core `a248c9f` 加本次同步补丁；两个较早的规划分支只移植依赖同步和兼容补丁，
不引入 A01–A03 实现。文档治理检查的链接、锚点和冻结 bytes 未报错；仍报告既有 docs66/task_env22
数量上限，以及相对 consolidation 基线的七项非文档路径。该检查要求 documentation-only，不能记作全绿。
原始诊断脚本、初次 mesh 失败、成功录制和各运行日志保留在 ignored
`workspace/maintenance/geophys_main_sync_20261020/`，不作为发布 Evidence/Judge approval。

模块 Skill 的 public construction、recording 和不支持交集经上述 routes 复核，API 未增加；Skill 只新增
当前依赖与历史资格区分的路由说明。旧 P00/A04 来源图、跨 checkout 和 dependency evidence 结论绑定
旧 GeoPhys commit，下一次 A04 审查必须在新 pin 重核；本次同步不启动 A04 实施。

## 执行边界

稳定路径为 Artifact → ExecutionSpec → capability admission → ResetSample → provider
materialization → CanonicalStateView → controller/semantics → trajectory。
`task_env.runtime.sessions.RuntimeSession` 的高级协议为 reset、snapshot、step、close；
selected manipulation 通过 `task_env.runtime.sessions.control.materialize_control` 建立 control session。
不要绕开公开 factory 在任务脚本中创建第二个 runtime。

通用 environment 的 `task_env.RuntimeBoundary` 另提供 apply_reset_state、apply_control、
`step(substeps=...)`、read_snapshot、snapshot_state/restore_state、prewarm。
这是 framework integration boundary，不是 planner/recorder 访问 native `qpos`/`ctrl` 的授权。
当前 production callers 包括 `task_env/registry.py`、`task_env/tasks/reference_env.py`、
`task_env/environment/env.py` 和 root examples；具体 source owner 见[ownership](../../global/ownership.md)。

通用 `BaseTaskEnv` 在调用 `bootstrap_task_runtime` 前生成只读的
`execution-plan-v0`（`env.execution_plan`）。其身份覆盖 normalized config、精确 timebase、当前单 Agent
Controller 选择、RenderConfig 选择和资源 owner identities。已知不支持的多 Agent 与缺失 Panda Controller
会在 native bootstrap 前拒绝。此 Plan 只证明静态配置通过；没有读取 Provider manifest、实例化 solver、
验证 Renderer backend 可用性或执行 reset realization。C01b 才连接 Artifact/task requirements 与实际
manifest admission，后续 D/B 切片分别验证 materialization 和 realization。

当前通用资源归属为：`BaseTaskEnv` 管理 CameraObservationProvider 与懒创建的 UI TaskEnvRenderProvider；
`SingleTaskLifecycleAdapter` 是 `RuntimeBoundary` 的唯一 close 调用者；`GeoPhysRuntimeBoundary` 持有
GeoPhys runtime-facing 对象。BaseTaskEnv 构造在 bootstrap 返回后失败时会关闭已创建的 Core wrappers，
重复 `env.close()` 不会再次关闭它们。当前 GeoPhys boundary 的 `close()` 是空操作，因为 Taichi runtime
为进程级资源；这条路径不声称每个 Env 都释放/销毁一个独立 native solver。Selected reference 自己拥有并关闭
其 advanced `RuntimeSession`，没有被该静态资源表改写。

## Admission、Reset 与 state

Provider manifest 绑定 provider/version、adapter、backend、physics/render profile、determinism、
capability statuses、known unsupported 与 Evidence reference。请求须被实际 provider manifest
覆盖；用户 manifest 可收紧但不能扩权；未知 pairing/profile/backend/capability 在 rollout 前失败。
`provider_manifest` 有 GeoPhys、MuJoCo、SAPIEN、Genesis adapters；这不是 provider-wide qualification。
Selected reference factory 只准入 GeoPhys/MuJoCo scalar CPU、state-only，不能外推 SAPIEN/Genesis。

Task randomness 属 Core sampler，provider randomness 独立。Provider 应用同一个 ResetSample，
记录 realized state；不得 hidden settle 或重新采样。reset realization gate 在执行前检查声明 tolerance。
Canonical state 用稳定 semantic names、SI、明确 right-handed frame、quaternion wxyz、finite values，
不使用 provider integer IDs。当前 world convention 为 right-handed Z-up；adapter 在输出前 normalize wxyz，
contract 仅验证 `abs(norm_sq - 1) <= 8 * 2^-23`，不静默 normalize，以保留 deterministic roundtrip。
zero/non-finite/明显非单位 quaternion 拒绝；这是 representation bound，不是 physics tolerance。
control step/simulation time、joint position/velocity、body/frame poses
按 contract 提供；contact/camera/privileged fields 必须各自准入，不以私有 contact arrays 代替。
`RuntimeSnapshot`、`TaskStateView` 和 `CanonicalStateView` 是既有不同投影，不能假定 storage ABI 相同。

Phase II D01b 在现有 `RuntimeSession.materialize()` 上增加受限 TaskArtifact v1 admission：必须绑定精确
`scene-definition-v3`、单一 RobotInstance、固定拓扑 scalar reset/state 与 bounded source root；当前只允许 GeoPhys/MuJoCo
CPU。v1 reset plan 继续传递原有 `ResetSample-v0`，并在 rollout 前核对 TaskArtifact、TaskSource、Scene identity 和
requested/realized tolerance。MuJoCo 使用 MJCF string 的 `assets` VFS 消费 canonical scalar-axis projection，native build 前
重算并校验 source-closure digest，并在构造后检查 runtime Frame、Joint parent/child body、kind 和 axis。该路径不支持
free-body pose reset、拓扑变化或其他 Provider。

2026-10-20 的 TESTED_BOUNDED S2 microprobe 使用 A05 Panda + procedural square peg；同一 Artifact/Scene 的 sample 在两
Provider 上复用，GeoPhys 最大 reset joint error `5.96e-9`、MuJoCo `0`，均实际 step 一次。改变 canonical `joint1` axis
后两边 `link1` pose delta 约 `0.246226`，同 Scene 跨 Provider pose delta 不超过 `6.42e-9`。这不证明 Controller/action、
contact、Task success、Renderer pairing、通用 Scene import 或 Qualification。详细 receipt 在
[Phase D D01b 记录](goal/Phase_II/04_Phase_D_Physics_Rendering.md#d01b-bounded-vnext-two-provider-receipt-2026-10-20)。

Phase II D02a 在 `task_env.artifacts` 增加 provider-neutral `CanonicalStateViewV1`、typed Joint/Frame、
consumer `StateRequirements`、sample/boundary clocks、native interval evidence 与 bounded view lifetime
contracts。现有 `RuntimeSession.snapshot()/step()` 仍返回 `canonical-state-v0`；D02a 不提供 provider
projection、native contact readback 或 alias invalidation。v0→v1 仅通过显式 Scene/legacy-name bindings 投影，
真实 adapter projection 与跨 step/reset lifetime enforcement 留在 D02b。

Phase II D05a 在既有 Artifact 与 Camera Source owners 下提供 `ExecutionSpecV1`、每相机完整
RendererSelection override、精确旧 v0/v1 decoder，以及将 source/camera/execution/manifest/state boundary/clock
组合成 planned capture identity 的 contract。该静态 API 不改变 `RuntimeSession.materialize()`、
`provider_manifest()` 或 `create_camera_session()` 的旧 `ExecutionSpec` 路由；当前 camera admission 仍限制
GeoPhys/MuJoCo CPU 且要求 physics/render provider 同名。Manifest v0 identity 只 hash 原 mapping；设备选择目前
没有 provider manifest 对应字段，因而 capture identity 绑定的是声明设备，实际解析设备与 pairing 留给 D05b。
CameraCaptureIdentityV1 是请求身份，不是 capture receipt，也不表示输出能力已准入。

`control_dt = physics_dt * control_substeps`；当前 selected 100 Hz 配方以 0.002 s native step、
5 substeps 构成一个 outer boundary。decimal/JSON timebase representation 仅允许一个 ULP 差异；action hold、观测与语义采样必须保持显式。
通用配置允许值不证明某任务/backend 已支持；同步 control-boundary contract 也不证明异步多传感器。

## Controller 与 observation

Requested action → canonical/public action → canonical controller target → provider-applied control
是四个独立层次。Panda pose action 在 provider 前经公共 controller/IK 解析，adapter 最后映射 actuator；
requested action、target、applied control 必须分别记录。
ProductionCanonicalPandaController 从 Geochora-owned source chain 计算 FK/Jacobian/DLS，
gripper profile authority 为 resolved source.config.robot.gripper，identity 包含全部字段。
它在 reset 后每 measured control boundary compute 一次，拥有 commanded opening、rate limit、
force activation/initialization/deadband state；不是旧 stateless controller 的隐式 alias。
CanonicalControlFeedback 的 opening、step/time 要与同一 state 对齐；非负 closing-force 为完成的
native actuation interval measurement，sign/index 转换留 adapter；不宣称通用 force-sensor 支持。任务实际 observation_space/schema 和 metadata
决定 state/privileged_state/camera 内容，不固定所有任务为 Panda 八维。通用 SB3 flatten 在 learner 边界。

Selected reference 使用 finite 8D world absolute pose request；PickCube 可用 external action 或 expert，
同一 episode 不能混用；NutAssembly raw external action 拒绝，并保留 `step_expert()`。NutAssembly
另有有界 task-owned external Solution native S1：GeoPhys `a53a8cf` CPU 与 MuJoCo 3.8.1 CPU 单 interval
Probe 已通过，完整 external Expert 和录制 S2/S3 未通过；详见 C05c S1 receipt。
Selected reset 重建 controller/solution owner 状态，不推进物理，录制需先 finalize 再 reset。

### C02b Position Profile candidate (2026-10-21)

`PandaPositionServoProfileV1` is an internal candidate composed in the existing canonical controller,
plan-bound session and selected lifecycle owners. It consumes typed Panda Joint positions and the A05
`panda-main/hand` frame through the versioned hand-origin TCP profile. Its Required State omits measured
actuator force, so plan-bound GeoPhys execution does not call `control_feedback()` and the MuJoCo session
does not copy its force cache during reset/step. A required-force R1 plan still fails admission when the
actual provider manifest lacks `actuator_force_query`; legacy no-plan behavior remains compatible.

This candidate has no registered default task selection. Its explicit diagnostic constructor reuses the existing
`SelectedReferenceEnv` lifecycle and `ReferenceTaskBinding`; the bounded route uses existing Generic H5 v3 recording.
GeoPhys CPU and MuJoCo CPU native S2 passed for one Panda candidate, including motion, clock/boundary evidence,
force-free reads, structured control readers and direct H5 joint/hand/identity state-leaf readback. This is not a
production capability or qualification, and it does not close R1 reset-force freshness. See the
[C02b-E S1 acceptance](goal/Phase_II/C02b_E_Position_Profile_S1_Acceptance.md) and
[S2/H5 acceptance](goal/Phase_II/C02b_E_Position_Profile_S2_Acceptance.md).

### C02b-R1 reset-force freshness (2026-10-22)

The existing PickCube `production-r1` legacy selected route now asks the
GeoPhys runtime adapter to refresh reset force after restoring and explicitly
writing the final reset qpos/qvel/ctrl/activation. The adapter uses the public
`control.robot_arm.RobotArmObservationReader`; its versioned sample receipt
distinguishes reset-forward force from the last completed native-step
pre-integration force. A reset-forward refresh evaluates the current actuator
law and does not integrate or advance the native clock. State/config writes
invalidate the prior receipt, and required consumers fail closed on invalid,
wrong-source, wrong-actuator, stale-boundary or non-finite samples.

The bounded real probe passed for the selected PickCube source on GeoPhys CPU,
seed 31, at 100 Hz / five 2 ms native steps, including a nonzero force sample,
two same-session resets, source-law comparison and the first actual R1 closing
compute. MuJoCo CPU supplied a separate reset/step sampling-semantics comparison;
force values are not compared across providers. This closes only the R1 reset
freshness prerequisite for this legacy route. At that receipt's checkpoint,
plan-bound typed raw-force admission was still missing. The later
[`snapshot_v2()` candidate receipt](goal/Phase_II/C02b_R1_Typed_Raw_Force_Admission_Acceptance.md)
adds one source/Controller/plan-bound GeoPhys CPU route on `a53a8cf`; it does not
rebind the old selected PickCube source or enable MuJoCo typed force. The shared
`provider_manifest()` still makes no generic `actuator_force_query` claim, and
`snapshot_v1()` remains force-free. C02b remains BLOCKED. The later bounded C05b
legacy external Expert S2 and canonical-v0 S3 use the old selected route and do
not migrate the candidate plan identity or add typed-force capability to MuJoCo.
See the
[freshness receipt](goal/Phase_II/C02b_R1_Reset_Force_Freshness_Acceptance.md).

### NutAssembly selected Solution B

NutAssembly Outcome Solution v3 的抓取下降命令偏置与高度验收补偿相同，TaskArtifact v0 mapping/hash 不变。
末端到达下降终点后，Solution 保持固定 world absolute-pose 请求，由现有 Controller 在每个 100 Hz control
boundary 重新计算目标；只有 20 个样本、0.2 s 窗口内的欧氏位置 RMSE 严格低于 0.1 mm，且原有等待、位置稳定、
高度和姿态门槛通过后才开始闭合。未在原 `max_pose_hold_s` 内达到跟踪误差门槛会以
`preclose_motion_stability_timeout` 失败并停止抓取。闭合期间继续笛卡尔反馈，不锁定关节目标；现有 500 Hz
gripper Guard、10 N 力目标/上限和后续 11-stage Expert 生命周期保持原 owner。

该 B 路线已在 NutAssembly seed 19、GeoPhys main `4436787e`、CPU 上完成一次全 Expert 轨迹及 recorder round-trip；
单次执行证据仅适用于该交集。它没有升级 v1.1.0 capability matrix 或授予 Qualification，也没有验证 root Gitlink
`54f40fbf`、其他 seed/provider、D0 replay 或动态相机。Selected NutAssembly 仍是 state-only；当前 native camera
source 只覆盖静态 triangle scene，不能作为这条轨迹的动态相机验收。

Camera mount frame 与 optical frame 分离，显式记录 `T_world_from_camera`/逆变换、K/FOV、near/far、
尺寸、RGB layout/dtype、depth unit/convention、timestamp。几何验证检查 landmark projection、
dynamic parent 与 depth back-projection，不要求 pixel-perfect photometric equality。
当前 advanced camera 的 legacy mount 为 +X forward/+Z up，optical 为 +X right/+Y down/+Z forward；
vertical FOV 构造 `fx=fy=H/2/tan(fov_y/2)`、`cx=W/2, cy=H/2`，pixel center 为 `(u+0.5,v+0.5)`。
Canonical depth 为 H×W float32 metre optical-Z，positive 为有效，0 为 invalid/background/clipped；
RGB 为 HWC/CHW、float32 [0,1] 或 uint8 [0,255]。metadata 来自解析 parent 的同一 state step/time。
高级 headless native camera route 只声明 CPU native pairing 与 static closed-triangle source bridge，
不外推 scene/material/texture migration、GPU 或 visuomotor；GeoPhys process-global fields 的 teardown
需 worker exit，不能把 close session references 当作 native allocator 全释放。
Camera observation 与 UI frame/presentation 是不同 contract，physics 与 renderer 分别 admission。
当前 rasterizer native RGB 范围见[recording-and-learning](recording-and-learning.md#learning-与-rendering)。

## Expert lifecycle

Task semantics 拥有物理 success/failure；Solution 拥有 stage/readiness/timeout/action budget；
environment/runtime 拥有 terminated/truncated；Recorder 记录事实，Judge 决定接受。
controller readiness 是 Solution 的输入，不自动等于成功或 Expert completion。

内部 `task_env/tasks/canonical_solution_lifecycle.py` 的不可变 policy 区分 `ON_TASK_SUCCESS`
与 `ON_EXPERT_TERMINAL_STAGE`，不从 root facade 导出。后者必须同时满足 terminal readiness、
曾观察成功、当前 final success；仅早先 success 不足。记录 first/current success、step/time、
environment flags、complete/failed（互斥）、原因与有序 events。终态后不能再 action/observe，reset
清 rollout state；提前 environment termination、truncation、readiness timeout、budget overrun 或
final success 丢失不可隐瞒。`TASK_SUCCESS_EXPERT_INCOMPLETE` 不是 Expert 完成。

新/修改 Solution 必须版本化 policy、成功谓词、post-success work、terminal stage/readiness、
timeout/budget、stop 条件及影响行为的 owner state；行为变更要求新 identity，不能迁移历史 H5 假装同源。
可恢复状态含 policy、first/current success、terminal state/reason/boundary、environment flags、events；
restore 在修改新 owner 前校验 identity/version/policy/clocks/consistency。
Selected 录制的 observation receipt 不是完整 controller/expert restoration checkpoint，不能因此宣称 D0。

当前 NutAssembly `solution.py` 为 task-owned Outcome Completion V1：完成 11 个 planned stages、
open gripper 与 release retreat，最终 task outcome 单独判断。GeoPhys 的 admitted
`stable_height_mismatch` warning 与原 strict Expert failure 必须独立保留；Outcome completion
不把 strict failure 改写为 pass。PickCube 保留 expert collection margin，不等同于无条件 success-stop。

## Guard 与物理时间

内部 `task_env/tasks/guarded_transition.py` 是 provider-neutral deterministic evaluator，输出
WAIT/AUTHORIZED/RECOVERY_REQUIRED/FAILED；task 映射 canonical evidence 为 conditions。
每个观测为 `[t,t+dt)` measured interval；所有 condition 存在且 true、采样连续才累计 dwell。
false/缺采样/clock gap 重置连续性，不插值、不平均、不多数投票；完整 dwell 须在 deadline 内结束。
同采样多个 guard eligible 时按显式 priority；early alternative 是否允许由版本化 policy 决定。
outer-frequency 更新不创造 native samples；缺 substep evidence 的 adapter 不能宣称 native-rate equivalence。

历史 8 N alternative 与 500 Hz candidate 是版本特定开发机制，不能当作当前 universal threshold、
controller target 或 qualification。guard authorization 不修改 task predicates，后续真实 hold 动作也不得
用 timeout warning 代替。guard continuity、selected authorization 与 lifecycle 纳入版本化 owner snapshot，
缺失/identity mismatch restore 必须失败。历史设计与 Evidence 在
[冻结设计记录](https://github.com/Lebingelee/GeoChora/blob/v1.1.0/docs/module/task_env/canonical-solution-guarded-transitions.md)。

## 物理等价与资格边界

unit、gravity、mass/inertia、geometry、joint limits、timebase 属 exact semantic parameters；
friction、damping、gain/compliance 可能需近似映射；iteration/stabilization/kernel 为 provider-native。
验证声明 tolerance 下 provider-independent outputs，不能假设 native 参数一一对应。
C1 open-loop 固定 Artifact/ResetSample/control stream/timebase；C2 closed-loop expert 固定
Artifact/sample/algorithm/config 但读取 live state；两者独立 gate，contact-rich 长时轨迹不要求逐点相等。
不同 replay 语义及未测试交集见[qualification](qualification.md)和[recording](recording-and-learning.md)。
