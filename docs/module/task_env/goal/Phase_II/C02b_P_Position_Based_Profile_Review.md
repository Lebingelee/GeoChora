# C02b-P Position-based Controller Profile 源码审阅

日期：2026-10-21。基线：干净的 develop，HEAD e0d235c；GeoPhys gitlink 4436787e9cb85ce519506a2a9af86d1eeec9de2d。审阅依据：[执行顺序](05_Architecture_Review_and_Execution_Order.md)、[Phase C lifecycle](03_Phase_C_Execution_Lifecycle.md)、[Recovery Architecture Review](C02b_Recovery_Architecture_Review.md)。

## C02b-E 第一轮勘误与状态更新（2026-10-21）

本报告主体是实施前的 C02b-P 审阅记录。C02b-E 第一轮现已完成 Position Profile/source-state 接线与 S1；**本节修订优先于下方历史基线中的“尚未实现”表述**。原始审阅签发时 C02b 为 **BLOCKED**；后续有界工程退出状态见 [P99 readiness review](P99_Readiness_Review_2026-10-22.md)。验收事实、candidate identity、定向检查及未执行项见 [C02b-E S1 Acceptance](C02b_E_Position_Profile_S1_Acceptance.md)。

- **A05 TCP 勘误**：A05 Panda `hand` 下不存在 `nutassembly_ee_site`。历史段落关于该 site 的假设不正确。代码采用版本化 `panda-tcp-profile-v1 / panda-main/hand-origin-tcp-v1` identity transform；typed Controller pose 与 FK/Jacobian tip 都使用实际 projected MJCF source 的 `hand` body origin。A05 fixture 和 Panda source closure 未修改。若未来改变 source 几何/TCP，需为新 closure/Artifact/Profile 生成新 identity。
- **分阶段退出**：此前 sentinel、双 Provider S2、Generic H5 v3 真写读被列在“进入 C02b-E”的准则中，这个先后关系已修正。S1 实现/拒绝边界已通过；双 Provider native S2、Generic H5 v3 控制及 state-leaf 磁盘回读属于后续 C02b-E 退出层，当前未运行。它们不再是启动 E 或实施第一层的前置条件。
- **现状**：新 writer 为 `panda-main/position-servo-v1`，显式 Required State 为 9 个 joint positions + `panda-main/hand` Frame。实例 identity 绑定 candidate Artifact/Scene/source closure、projected MJCF hash、TCP、resolved ActionConfig、action schema、source bindings、timebase、DLS algorithm identity 与 gripper semantic。SelectedReferenceEnv 的既有 lifecycle 有显式 Position profile 分支，但没有 task registry/default factory 选择该 candidate；不新增 production capability。
- **分层范围**：本轮只做 S1。S1 sentinel 与拒绝边界已完成；双 Provider S2、Generic H5 v3 真写读以及 raw state-leaf 磁盘回读属于后续 E 退出层，未运行且不是 E 的开工前置。

## 结论

分类为 **COMPOSE_EXISTING / EXTEND_EXISTING**。已有 DLS 位置控制、位置 gripper correction、ControlBindingPlanV1、RuntimeSession reset/state/apply/step，以及 Generic H5 v3 structured writer/reader。第一轮已补独立 position Profile 实例、source/state 适配、受限 plan-bound 执行 owner 和 MuJoCo force-cache 策略；双 Provider native S2 与 H5 v3 真写读仍待做。

本报告原始审阅仅完成 C02b-P，不启动 C02b-E；当时状态由后续实施收据更新。该历史记录没有新增 registered capability 或 qualification。

## 实际路径与候选范围

### 当前 production Controller

当前 PickCube selected reference 的实际构造链为：

**PickCubeReferenceEnv → ReferenceTaskBinding.build → task.build_reference → ProductionCanonicalPandaController.from_source → SelectedReferenceEnv.reset/_step → materialize_control → RuntimeSession。**

task factory 当前只构造 R1；reset 与每个 outer step 都调用 RuntimeSession.control_feedback()，再调用 R1 的 reset/compute/readiness。R1 identity 由源码、ActionConfig 和 RobotConfig.gripper 构造；上一份 source audit 记录的实际实例 identity 为 76108c78b8159391e448ad9f49050bed42fd7a86e0e00a0520083b4e5efb02e9。R1 消费 closing_force_N；当前 PickCube resolved gripper config 为 experimental_rate_limited，force limit 30 N、opening step 0.002 m、force deadband 1 N、force adjust step 0.0001 m。此 identity、行为、required raw actuator_force 和旧调用均保持原样。

源码入口：[PickCube task factory](../../../../../task_env/tasks/pick_cube/task.py)、[selected lifecycle](../../../../../task_env/tasks/reference_env.py)、[R1 controller](../../../../../task_env/controllers/canonical/production.py)。

### C02b 首条候选

候选边界仍为一个 Panda RobotInstance，Entity 为 panda-main，同一个 writer 覆盖 arm 与 gripper 两个 ControlGroup，CPU，100 Hz outer、每次 5 个真实 2 ms native steps。C02a 的 A05 Scene-v3 fixture 可复用；其静态 group 声明把 panda-main/arm 指向 actuator1–7，把 panda-main/gripper 指向 actuator8。

现有 C02a writer 是 panda-main/production-r1；其 required feedback 明确含 panda-main/actuator8 的 actuator_force、unit newton、evaluation_boundary、capability actuator_force_query。新 position writer 使用独立 ID 与 StateRequirements，不替换、删减或 optional 化这条 R1 requirement。

D01b 当前 microprobe 可复用 A05 source closure、Scene-v3、TaskSourceV1/TaskArtifactV1 编译、hash-bound ResetPlan 和两个 Provider 的 materialization 路线；但现有 TaskArtifact 时间基是 1×2 ms，测试 RuntimeSource 的 joint_targets 为空、open_actuators 为空，不能直接施控。C02b-E 应用同一 frozen Scene/source 内容生成独立的 100 Hz、5×2 ms candidate TaskArtifact 与 ResetSample，并在现有 RuntimeSource/source owner 内补齐精确 actuator target binding；不得改写 frozen A05 Scene/Artifact、旧 PickCube Artifact 或 GeoPhys pin。

候选构造顺序：

1. 从同一 Scene-v3/A05 source closure 编译新 TaskSourceV1 与 100 Hz TaskArtifactV1，并生成仅对该 Artifact 有效的 ResetPlan/ResetSample。
2. 在现有 canonical Controller owner 中按 Artifact、RuntimeSource、profile 参数构造 position Profile 实例。
3. 为新 writer 编译 ControlBindingPlanV1；用 plan-bound materialize_control() 做实际 Provider manifest/admission。
4. RuntimeSession.reset_plan() 成功后读取 typed state publication；Controller reset/compute 仅消费该 boundary state，不请求 force feedback。
5. 每个 outer boundary 完整预检两组 action，只 compute 一次、apply 一次、RuntimeSession.step() 一次；之后发布新 boundary state。

此处是实施前基线。当前 diagnostic candidate builder 构造独立 100 Hz TaskArtifact/ResetPlan，并给 RuntimeSource 增加精确 actuator mapping；`PandaPositionServoProfileV1.from_source()` 构造实际 Controller instance，已有 `SelectedReferenceEnv` lifecycle branch 可消费 binding builder 返回的 profile/plan/reset-plan/source。当前没有 production task factory/default registration 选择它；本轮不增加此注册，也不新增第二个 Env、Runtime 或 Provider abstraction。

## 新 Profile 的最小 identity、参数与 state

| 项目 | C02b-P 建议合同 | 当前状态 |
| --- | --- | --- |
| 稳定 writer/profile ID | panda-main/position-servo-v1 | 已实现，candidate-only |
| Profile schema | 独立 position-servo-v1、target position-control-target-v1、TCP panda-tcp-profile-v1 | 已实现，未登记为 production capability |
| 实例 Controller identity | 绑定 Artifact/Scene/source closure、projected MJCF hash、TCP、resolved ActionConfig、action schema、source bindings、timebase、DLS algorithm、gripper semantic/Required State | 已实现；identity 摘要见 Acceptance |
| action | 复用 C02a ActionModeSpec：absolute_pose / world / quaternion_wxyz；8 个有序分量 x,y,z,qw,qx,qy,qz,gripper | 已实现 typed group projection 与 pure all-groups preflight |
| gripper semantic | 同一 Entity 的 panda-main/gripper，并与 actuator8/0.08 m opening range 一致 | 已实现显式 adapter；只执行现有一次 position correction |
| Required State | evaluation_boundary：9 个 joint_position（arm 7 + finger 2，Scene Joint unit）和 panda-main/hand frame_pose_world | 已实现，capability 为 joint_state_query/frame_pose_query，不含 actuator_force |

参数使用该 A05 candidate RuntimeSource 的 resolved `ActionConfig`；不从 PickCube R1 或 NutAssembly R3 的 force-aware `GripperConfig` 借参数。当前值：DLS damping 0.02、position gain 0.9、rotation gain 0.65、rotation row weight 0.22、max joint delta 0.10 rad/outer tick、position/rotation deadband 0.006 m/0.035 rad、Cartesian max step 0.025 m/0.20 rad、joint correction gain 2.5；gripper opening range 0.08 m、servo force cap 5 N、position stiffness 2500 N/m、close/open ctrl 0/255。这里的 5 N 是 position servo 的目标/物理 force limit command，不是 measured actuator force，也不等价于 R1 的 force-aware close/readiness。

CanonicalPandaController 的现有 DLS 与 gripper position target 由 joint position/state pose 计算，不读 measured actuator force。位置 Profile 只调用它现有一次 gripper correction；不会再调用第二次位置 servo correction。结构化 RuntimeSession.apply_control() 继续映射 `CanonicalControlTarget.gripper.servo_opening_m` 到 Provider。

source/state 不能靠字符串 alias：

- A05 v3 的 Typed Joint 是 (panda-main, joint1…joint7, finger_joint1, finger_joint2)；CanonicalPandaController 的 v0 输入使用 panda-v1/joint1…joint7 与两个 panda-v1/finger_joint* 名称。
- **勘误**：A05 Panda XML 不含 `nutassembly_ee_site`；不能把该旧 PickCube/NutAssembly source site 套用到 A05。版本化 `panda-main/hand-origin-tcp-v1` 明确声明 hand-local identity transform。typed `panda-main/hand` pose 是 controller 输入，FK/Jacobian 同一 projected XML 的 `hand` body origin 是 tip；两者一致并纳入 Profile identity。没有创建或假称独立 `ee` Frame。
- typed `panda-main` 的 9 个 Joint 已精确投影到 Controller canonical inputs；candidate RuntimeSource 把 arm target 精确映射到 actuator1–7、gripper 映射到 actuator8。plan-bound `materialize_control()` 对 Position candidate 校验这些实际 source bindings 与 Scene plan 的资源映射。

### Reset / Compute / Step 接口

| 阶段 | C02b-E 的最小调用合同 | 当前能力 |
| --- | --- | --- |
| 实例构造 | `PandaPositionServoProfileV1.from_source(artifact, source)` → 独立 writer_id 与 Controller identity | 已实现 candidate instance；无 default production factory selection |
| reset | `profile.reset(publication, plan)`；selected branch 先 `RuntimeSession.reset_plan()`、再 `snapshot_v1()`；不读取力、不推进物理 | 已实现；只由 typed state fixture/S1 验证，未执行 native Provider reset |
| compute | `profile.compute(publication, requested, plan)` → canonical action + source-bound versioned target；无 feedback | 已实现 typed adapter、episode/reset/boundary/clock 顺序校验；S1 测试 |
| step | 既有 execution owner 做一次 `apply_control(target)`，再调用 `RuntimeSession.step()`；目标 interval 为 5×2 ms | 已实现 dispatch 接线与 session-probe 断言；真实五步 Provider actuation 留给 S2 |

`profile.reset/compute` 的 typed input 包含同一 state publication 的 boundary/reset identity。CanonicalStatePublicationV1 提供这些标识；调用现有 CanonicalPandaController 前使用显式 canonical-name 与 hand-origin TCP adapter。位置路线没有 GripperReadiness/force-hold 输出，不伪造 R1 readiness。

## Lifecycle/API 审计与 force-free 条件

| owner/API | 当前实现 | C02b-E 所需行为或缺口 |
| --- | --- | --- |
| CanonicalPandaController | compute(state, requested)；shared-dls-v0 algorithm identity；无 reset；输入为 v0 semantic maps | Profile 复用算法，并由 versioned Profile 提供 identity/reset/typed adapter；每个 evaluation boundary compute 一次 |
| ProductionCanonicalPandaController (R1) | reset(state, feedback) / compute(state, feedback, requested) / readiness(state, feedback)；内部 GripperMemory | 旧 R1 全部保留，不传给 position writer |
| SelectedReferenceEnv | production R1 route 仍读 control_feedback 并走 R1 reset/compute/readiness | 既有 owner 增加显式 Position branch；Position route 不请求 feedback，也不生成零力 readiness |
| ControlBindingPlanV1 | 校验 Scene group/action partition、writer 的 StateRequirements、resource ownership；prepare_structured_action() 是纯预检 | Position plan 一个 writer 覆盖两个 group，Required State 不含 actuator_force；正向 native admission 尚未运行 |
| materialize_control() | 先检查 provider manifest，再按 plan required capabilities 做 fail-closed admission；无 plan legacy route 保持兼容 | Position contract path 增加 source/Artifact/Scene/profile 与 exact actuator-map 校验；R1 `actuator_force_query` 仍在 Runtime 前拒绝；正向双 Provider materialization 留给 S2 |
| validate_target()/apply_control() | existing canonical target checks Artifact hash、arm key set、gripper semantic | Position target envelope 增加 writer/Controller/plan/source closure/StateBoundaryIdentity/sample clock；执行 owner 对 fresh RuntimeSession publication 做核验后才允许 apply |
| RuntimeSession.snapshot_v1() | exact Scene/Joint/Frame bindings 下发布 Typed State、StateBoundaryIdentity、ResetSample ID、Provider materialization ID、evaluation clock；不发布 actuator_force | 可作为 position Profile 的有类型 reset/step measurement；使用现有 state/要求，不增第二套 state |
| RuntimeSession.step() | GeoPhys 按 control_substeps 执行；MuJoCo 每子步调用 mj_step，最后返回 outer state | 既有 `step()` 用于 100 Hz/5×2 ms；S1 只断言 session probe 的调用数，真实 native interval 留给 S2 |
| RuntimeSession.step_control_interval() | Common owner 每个 native substep 调用 control_feedback(state)，并驱动 inner gripper servo | 不能用于本 Profile；会引入力反馈，内层 R1/500 Hz 语义不属于本候选 |

**C02b-P 基线的完整链不能被称作 force-free；当前 Position candidate 的 Core 接线不查询 measured force。**

GeoPhys 的明确 raw-force query 在 GeoPhysRuntimeSession.control_feedback()，它通过公开 boundary snapshot 请求 actuator_force；普通 snapshot/step 不在 Core 侧读取力。plan-bound session 现在按 Required State 设置 force policy；MuJoCo Position route 的 reset/step 不复制 `_data.actuator_force`，required-force R1 plan 仍保留该 cache 行为。Provider 内物理 solver 计算力属于模拟，Core/adapter 读取或复制测量缓存属于本 Profile 禁止的读取。

当前 plan-bound Core owner 按 Required State 决定是否缓存测量 force：R1 required-force plan 仍 fail-closed；Position profile 无 force requirement，GeoPhys 不调用 `control_feedback()`，MuJoCo reset/step 不复制 force cache。`control_feedback()` 在此 Profile 下 fail-closed。S1 force read/copy sentinel 通过；未运行 Provider native S2。诊断开关不参与 required feedback 是否存在。

## Generic H5 v3 最小真实写读合同

已有通用 writer/reader 足够存储 Position Profile，不需要新增 Recorder，也不把 force/readiness 填进旧 BoundaryRecord：

1. 用 TransitionRecorder + RecorderConfig(schema_version=v3) 保存 T+1 个实际边界 observations、T 个 outer actions 和 T 个 StructuredControlTransitionV1。每条控制记录包含两个 groups、唯一 writer、完整 request/canonical action、带 Controller identity 的 target/hash、Provider applied payload/target_hash ack。
2. env_meta/action_schema/reference_profile/env_cfg 写入 Artifact/Scene/source-closure、ResetSample/episode、Provider/backend、profile/config digest、source frame/joint/actuator mapping 与 0.002 s × 5 timebase。每条 observation 或 boundary event 保留 control_step、simulation_time、state boundary/reset identity，使 reset 与 T→T+1 sampling 可从磁盘核验。
3. 正常 finalize 后写 EpisodeOutcomeV1；按需写 BoundaryEventV1。用 load_structured_control_records_h5() 检查 schema v3、finalized 标志、T/T+1 counts、StructuredControlTransition target hash/ack、events/outcome 与 end_reason；用 load_structured_training_actions_h5() 读单 writer numeric action projection，并与源 request 数值核对。
4. Generic H5 v3 保存 raw observation leaves，但 load_structured_control_records_h5() 不返回这些叶子，也不验证其中数值。C02b-E 真写读检查须再从文件读回 state observation dataset 并比对 reset、step、joint/frame values；这是针对既有格式的窄检查，不需要新通用 Reader。

当前 H5 v3 的 structured 写入、控制/event/outcome 读取、target hash/ack 检查和单 writer 数值投影已经存在；本轮没有 Position Profile transition producer 或真实文件/state-leaf 回读。structured reader 不验证 raw observation leaves。旧 canonical BoundaryRecord 强制 force/readiness；Position 路线不消费或放松它。真写读是 C02b-E 后续退出层，不是启动 E 的前置。

## C02b-E 最小实施边界与当前完成状态

| 现有 owner | 最小扩展 |
| --- | --- |
| `task_env/controllers/canonical/` | **完成第一层**：`PandaPositionServoProfileV1` identity/from_source/reset/compute、typed joint/hand adapter、一次既有 DLS/position gripper correction；新增 source-bound `PositionControlTargetV1` 与 hand-origin TCP profile |
| `task_env/runtime/sessions/control.py` | **完成第一层**：校验 writer/Controller/plan/source/target boundary；all-groups preflight 后单 writer apply；现有 `RuntimeSession.step()` 后 snapshot next typed boundary |
| `task_env/runtime/sessions/{geophys,mujoco,common}.py` | **完成第一层**：按 admitted required state 设置 force policy；GeoPhys 禁止 Position feedback query；MuJoCo reset/step 不复制 force cache；legacy force-aware cache 路径保留 |
| `task_env/tasks/reference_env.py` | **完成接线**：在既有 SelectedReferenceEnv 生命周期内增加显式 Profile branch 并复用 C03a fault latch；Position candidate 暂不具备 Generic H5 v3 录制入口，现有任务 factory 默认不选择它 |
| A05/D01b candidate source | **诊断构造器完成**：独立 candidate Artifact/ResetPlan、5×2 ms timebase、7 arm target + actuator8；不改 A05 fixture。尚未做真实 Provider materialization S2 |
| `task_env/diagnostics/tasks/` | **S1 完成**：profile/dispatch/sentinel/拒绝边界；既有 C02a 与 C02b admission 测试复跑。Generic H5 v3 真写读与双 Provider S2 未运行 |
| Phase C / execution table / public API / TaskEnv Skill | 本轮更新为 S1 bounded status 与分层退出标准；不开放 registry/capability，不代表 qualification |

不预期修改 Generic H5 v3 schema/Recorder owner，除非真实读写证明字段无法表达；届时只在现有 owner 内追加版本化字段。不修改 C02a 旧 R1 required state、冻结 Artifact、GeoPhys pin 或跨 Entity Scene/Robot Assembly。

## 测试与双 Provider S2 方案

### 已完成的 S1 定向检查

- 新 position binding 精确要求 9 个 Panda Joint position 与 hand Frame pose，action groups 覆盖全部 arm/gripper 组件，resources 与 actuator1–8 一一匹配；不含 actuator_force。
- R1 required-force case 仍因 `actuator_force_query` 在 Runtime 前拒绝；no-plan legacy call 保持原语义。Position profile 通过真实 Provider manifest 的静态 plan admission，但 native materialization 尚未运行。
- 本 Profile 测试覆盖缺 group、错误 plan/writer、stale/duplicate target；共享 `prepare_structured_action()` 的 extra/unknown/non-finite/identity 拒绝由 C02a 专项测试覆盖。每个 boundary 至多一次 compute/apply/ack。
- Position session probe 的 force read/copy sentinel、完整 target/boundary preflight 与五步 interval call-count 通过；C02a legacy R1 required force admission 与 no-plan compatibility 独立通过。
- Selected lifecycle 注入 interval failure 后复用 C03a fault latch 的定向断言通过。
- Sentinel 只覆盖 S1 可调用的 Core/session methods；不等价于双 Provider native S2，也没有 H5 writer/readback。

### S1 后续退出层：Generic H5 v3 真写读（未运行）

- 真文件写读确认 reset initial observation、至少一个 T→T+1 transition、Controller target/hash、applied ack、state boundary/time、episode outcome 的数值与 identity。
- 当前 Position candidate 明确拒绝 `start_recording()`；须在现有 SelectedReferenceEnv/Recorder owner 内接通既有 Generic H5 v3 producer，并直接读取 observation raw state leaves，不能只用 structured control reader 代替状态值回读。
- 录制检查通过前，Position Profile 没有 recording capability；本轮未改 H5 schema。

### 两个独立 CPU S2 方案（未运行）

每个 Provider 独立进程运行相同的 versioned candidate、Scene-v3/source closure、100 Hz outer/0.01 s、5×0.002 s native interval 和同一 hash-bound ResetSample。reset 后先核对 hand/joint publication 与 ResetPlan identity；每个 outer action 完整 preflight arm+gripper，一次 compute/apply，再通过 RuntimeSession.step() 得到五个真实 native steps。验证开闭位置命令实际影响 Panda arm/gripper、只读 state 不推进仿真、next state boundary/sample identity 正确，并做 H5 v3 真读回。

GeoPhys CPU 与 MuJoCo CPU 共享 Core identity、action、reset sample、timebase 和 source closure；Provider materialization identity 分开记录。各自 target/applied 按确定性输入和事前容差核对，不要求接触轨迹或力逐值相等。不要调用 step_control_interval，不运行 NutAssembly R3 500 Hz/Guard，不把 S2 结果解释为 task success、R1 equivalence、replay qualification 或完整 C02b。

## 已实现与仍缺失

| 已有且可复用 | 仍未实现/未证明 |
| --- | --- |
| CanonicalPandaController 的 source-bound DLS/no-force position target；A05 Scene-v3 groups 与 C02a pure preflight | Profile 的真实双 Provider materialization 与 Panda physical motion 尚未验证 |
| RuntimeSession.reset_plan/snapshot_v1/apply_control/step 与 plan-bound required-state admission | S2 native 五步执行、Provider ack、reset/step publication 尚未执行 |
| Generic H5 v3 structured writer/reader、outcome/ack 与 action projection | Position candidate 的真实 transition producer、raw state-leaf 磁盘回读尚未接通 |
| 旧 R1 force-aware Controller、required-force admission rejection、legacy no-plan compatibility | S2、H5 v3 磁盘回读及完整 C02b 的其余必需交集 |

## C02b-E 分层退出标准（不是开工前置）

1. **S1 / 接口与拒绝边界**：Profile/source/target identity、exact A05 mapping、typed required state、100 Hz/5×2 ms candidate、全组预检、source boundary freshness 与 force-query/copy sentinel 通过。已完成。
2. **S2 / 真实 Provider 执行**：同一 candidate Artifact/ResetSample 分别在 GeoPhys CPU 和 MuJoCo CPU reset 并运行真实 arm/gripper position actuation，确认有效 typed state、每 outer interval 五个 native steps、ack、只读 snapshot 不推进物理且边界身份正确。未运行。
3. **H5 v3 / 持久化**：既有 Generic H5 v3 producer 写出结构化控制、T/T+1 boundary 与 outcome；reader 核对控制/ack/hash/outcome，并针对 raw state leaves 做数值和 identity 的真磁盘回读。未运行。
4. **完整 C02b**：完成 Recovery Review 要求的其余必需交集与生命周期验收；S1/S2/H5 的单 Panda candidate 结果不自动关闭 C02b、R1 force freshness、多 Entity 或正式资格。

后续实施可从任一未完成退出层继续；不要求先完成 S2/H5 才能开始 E 的下层代码。该段记录的是 C02b-E 开始前的审阅边界。双 Entity isolated actuation、R1 force freshness、C05b/C05c readiness/Guard、通用 Panda TaskEnv Stage 1 composition 与正式 Qualification 保持独立；当前 C02b 出口见本报告首段链接。
