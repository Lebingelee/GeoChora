# Runtime、Provider 与控制生命周期

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
同一 episode 不能混用；NutAssembly external action 拒绝，必须用 `step_expert()`。
Selected reset 重建 controller/solution owner 状态，不推进物理，录制需先 finalize 再 reset。

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
