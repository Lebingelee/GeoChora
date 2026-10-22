# C02b-E 第一轮：Position Profile 与 force-free 接线验收

日期：2026-10-21。实现基线：`develop@e0d235c54b33dda195269714214338dbad970548`；GeoPhys gitlink 保持 `4436787e9cb85ce519506a2a9af86d1eeec9de2d`。依据：[C02b-P 源码审阅](C02b_P_Position_Based_Profile_Review.md)、[Recovery Architecture Review](C02b_Recovery_Architecture_Review.md)、[Phase C lifecycle](03_Phase_C_Execution_Lifecycle.md) 与[执行顺序](05_Architecture_Review_and_Execution_Order.md)。

**阶段性历史记录说明**：本报告记录 S1 完成时的范围与状态；其中“S2/H5 未运行”是该阶段的准确历史事实。后续 GeoPhys/MuJoCo CPU S2、Generic H5 v3 真写读和数值回读已完成，见 [S2/H5 Acceptance](C02b_E_Position_Profile_S2_Acceptance.md)。实际运行前发现的 entity-qualified target mapping 修正也已计入后续 probe 的 Profile identity；本报告中的旧 S1 identity 仅用于追溯第一阶段收据，不代表后续实例 identity。

## 结论与退出层级

第一轮完成 Position Profile、Typed State/source adapter、plan-bound force-free dispatch 与缺陷敏感 S1。分类为 **COMPOSE_EXISTING / EXTEND_EXISTING**：DLS 和位置 gripper 计算继续由现有 `CanonicalPandaController` 完成；执行仍走 `ControlBindingPlanV1`、`RuntimeSession` 和 `SelectedReferenceEnv` owner。未增加 Runtime、TaskEnv、Provider、Recorder 或 Controller manager。

**签发时 C02b 仍为 BLOCKED。** 本轮 S1 是 C02b-E 的第一层退出证据，不是完整 Goal 验收。此轮没有执行 GeoPhys/MuJoCo 双 Provider native S2，没有生成并回读 Generic H5 v3 真文件，也没有打开新 production registration/capability 或授予 qualification。后续 Position/R1 收据与当前有界出口见 [P99 readiness review](P99_Readiness_Review_2026-10-22.md)。

C02b-E 分层退出标准如下，后续工作可以从当前 S1 基础继续，不以尚未实现的后层实验作为开工前置：

1. **S1 / 实现合同**：Profile、candidate Artifact/ResetPlan、exact source mapping、identity/boundary preflight 与 force-query/copy sentinel 定向检查通过。本轮已完成。
2. **S2 / 双 Provider native**：GeoPhys CPU、MuJoCo CPU 分别用同一 hash-bound candidate/sample 验证 reset、真实 arm/gripper actuation、每区间五个 native step、只读 publication、applied acknowledgement 和 boundary identity。本轮未运行。
3. **H5 v3 / 真写读**：使用现有 Generic H5 v3 writer/reader 记录 reset observation、T→T+1 boundary、single-writer structured transition、target/hash/ack 与 outcome；从磁盘读回控制记录和实际 state leaves 并按 identity/numeric 值比对。本轮未运行。
4. **完整 C02b**：按 Recovery Review 要求完成其余必需交集、生命周期和记录验收；不能由单 Panda Position Profile 的 S1/S2 单独替代。

## Candidate、source 与 TCP 修正

冻结 A05 Scene-v3 与 Panda asset bytes 未修改。冻结 Panda source receipt closure 为 `a59a66d0b176cb6b2634d54cd20744752742b425e5524db1b865dda0eb3adf2a`，Menagerie Panda dependency closure 含 68 个 asset files。**A05 的 Panda `hand` body 下没有 `nutassembly_ee_site`**；C02b-P 原文关于该 site 存在的描述为勘误前错误，不能沿用。此 candidate 不更改 MJCF，也不把 hand 隐式命名为一个源文件中不存在的 site。

新增版本化 TCP 合同 `panda-tcp-profile-v1 / panda-main/hand-origin-tcp-v1`：frame `hand`，局部平移 `(0,0,0) m`、旋转单位四元数 `(1,0,0,0)`。Position Profile 从实际 Scene-v3 projected MJCF 构造 `PandaKinematics`，FK/Jacobian tip 为 `transform(hand) @ TCP(hand-origin)`；typed Controller 输入取同一个 `panda-main/hand` Frame publication。测试确认无 `nutassembly_ee_site`、profile 与测试用 actual materialized projection 的 source XML hash 相同，且 FK/Jacobian 在该模型上可调用。因此 hand→TCP、Controller pose 与运动学模型处于同一 source boundary。

candidate 只改任务级 identity/timebase/source bindings，不修改冻结 fixture：100 Hz outer，`physics_dt=0.002 s`、`control_substeps=5`、`control_dt=0.01 s`；7 个 arm target 使用 source Joint identity `panda-main/joint1…7 → actuator1…7`，gripper opening actuator `actuator8`。旧位置算法内部仍使用 `panda-v1/joint1…7`，Profile 显式适配其输出回 source Joint identity；ResetSample、RuntimeSource 和 Provider target map 因而使用同一 `panda-main` identity。A05 Scene group identity 与 candidate Artifact/ResetPlan 各自保留版本化 hash。若将来修改 Panda XML/TCP 几何或 source closure，必须新增 closure/identity 并重新绑定 Artifact/Profile；不得借此修改或重写冻结 A05 fixture。

本轮 probe fixture 重建得到的 identity 摘要（用于可复核的 candidate input；不是冻结 Artifact）：

| Identity | 值 |
| --- | --- |
| Scene-v3 | `047661ff68e18dffa10a8bfe9cabef4e72f397b5280c1da7c7669ebf9e419e6e` |
| TaskSourceV1 | `e57fcc60788cab2c3c0d06648740f10c14d4ee12f3061fb91ed014f18cd6403e` |
| Candidate TaskArtifactV1 | `a56b6cbac66bc570c43d38b8eb5a7e3098873cc196015242d3e46df76dd0364c` |
| ResetPlan | `7965ae3292f96c82e99a442754b36172c885e049204ffb1b1bcb58a4d4a2d53d` |
| ResetSample | `reset-76ee97d76770106cfe04d84dbad39081683493cde7440ba5d5f03edadb733345` |
| Composite RuntimeSource closure | `aa4ca97bbe3c61b30752ba0dedc6c88a24394f03fe1b53519052d460ff9abc47` |
| Projected materialized MJCF XML SHA-256 | `f911356aee95d9b002ef3ea28eafae76c13d02d5f16c5a96325c0fd41eb48a7c` |
| TCP profile SHA-256 | `b27be18d500ddaa548f7a588d61a3756ae7663679ca66b3272aa268183461ff8` |
| Position Controller instance identity | `06b4fe0c709b952eabf51930c44bf3f1c8eafc3ef51474e2de7816819efccbd7` |
| ControlBindingPlanV1 identity | `e050d41a0d0f3eca8e4c2472b88ab94fd6a1bf12a2d1a28abc97fcc8876d143e` |

The composite closure includes the Panda and square-peg source used by this candidate. It is separate from the frozen Panda-only receipt above. Neither provider was materialized by the new S1 test; these hashes identify inputs only.

## 实际 Controller profile 与构造路径

- Writer/Profile ID：`panda-main/position-servo-v1`。
- Controller instance identity：a profile digest binding candidate Artifact/Scene, RuntimeSource closure and projected XML hash, TCP profile, exact Joint/Frame/actuator source bindings, action schema, timebase, resolved ActionConfig, reused DLS algorithm identity, gripper semantic, required state and `force_feedback=not-consumed-v1`. The Profile snapshots RuntimeSource mapping dictionaries at construction and rejects mapping drift at materialization/reset/compute.
- Construction: existing candidate builder produces `TaskArtifactV1`, `EpisodeResetPlanV1` and bounded `RuntimeSource`; call `PandaPositionServoProfileV1.from_source(artifact, source)`, then compile `ControlBindingPlanV1` from `profile.controller_binding()`. Existing selected lifecycle branch accepts that actual profile instance from its existing `ReferenceTaskBinding.build` result. No registered task factory currently selects this candidate by default; this round does not add production registration.
- Selected lifecycle input values remain the existing binding’s source, Artifact, solution slot (`None` for this external-only profile), Controller slot, reset plan and optional precompiled plan. A test/probe caller can exercise construction and interval owners without changing PickCube or NutAssembly factories.
- Reset: `profile.reset(CanonicalStatePublicationV1, plan)` validates exact typed requirements, Scene, initial evaluation boundary (`step=0`, time `0`), and binds episode/reset sample/plan. Existing selected path calls `RuntimeSession.reset_plan()` first, then `snapshot_v1()` and profile reset. It does not call `control_feedback()` or advance physics.
- Compute: `profile.compute(publication, RequestedAction, plan)` returns the existing canonical action and canonical position target inside `PositionControlTargetV1`; envelope binds writer, profile identity, plan hash, source closure, typed `StateBoundaryIdentity`, and `StateSampleClock`. Outer step preflights all bound groups, resolves the one writer, computes once, validates/applies once, then calls existing `RuntimeSession.step()` once and publishes next typed state.
- Step: the 100 Hz RuntimeSession interval uses the candidate Artifact’s five native 2 ms steps. The S1 session probe asserts the owner calls apply once and step once and advances a five-step probe counter; this is not evidence that a real Provider performed five native steps.

Required State is exactly 9 `joint_position` values—arm joints `joint1…joint7`, fingers `finger_joint1/2`—and one `frame_pose_world` for `panda-main/hand`, all `required` at `evaluation_boundary`. Joint units and coordinates are checked against the Scene Joint definitions: radian revolute arm values and meter prismatic finger values. Capabilities are `joint_state_query` and `frame_pose_query`; no `actuator_force` field or `actuator_force_query` requirement is present.

The resolved ActionConfig values bound by this run include DLS damping `0.02`, position/rotation gains `0.9/0.65`, rotation row weight `0.22`, max joint delta `0.10 rad`, position/rotation deadbands `0.006 m/0.035 rad`, Cartesian max steps `0.025 m/0.20 rad`, joint correction gain `2.5`, gripper opening `0.08 m`, command force cap `5 N`, stiffness `2500 N/m`, close/open ctrl `0/255`, and the remaining configured velocity-brake/error-growth fields in the identity. `5 N` is the existing position servo command/actuator cap; no measured force is read or treated as R1 feedback. The reused `CanonicalPandaController.compute()` performs its existing gripper correction once; the adapter only assigns the independent `panda-main/gripper` semantic and profile identity. It does not run a second Gripper Servo correction.

## S1 已验证事实与未验证范围

新增测试 `task_env/diagnostics/tasks/test_phase_ii_c02b_position_profile.py` 覆盖：

- 从未修改 A05 Scene/source closure 生成独立的 100 Hz candidate Artifact/ResetPlan 与精确 source target mapping；验证 profile 使用的是实际 projected XML hash 与版本化 hand-origin TCP。
- Typed 9 Joint + hand Frame 到 `CanonicalPandaController` 现有输入语义的显式转换；position target 写入同一 profile identity、gripper semantic、plan hash、source boundary 与 evaluation clock。
- 用 GeoPhys/MuJoCo 各自实际 Provider manifest 做 plan-bound 静态 admission，检查 profile identity/plan/hash 与 force policy；native `materialize()` 在测试中替换为 probe，因此不算实际 Provider materialization。candidate source Joint 或 actuator mapping 被改动时，在 native construction 前拒绝。
- arm/gripper 两组完整 request 预检、单 writer apply、target/source/plan/Controller identity 检查；缺组、错误 plan/writer、过期 boundary、同 boundary 重复 apply 在额外 provider write 前拒绝。SelectedReferenceEnv 对 Position profile 收到旧 8-float action 时在 episode-mode mutation 前拒绝。直接绕过 source-bound target gate 的 `validate_target()` 被拒绝。
- MuJoCo `actuator_force` copy sentinel：position plan reset/五步 step 未复制；position `control_feedback()` fail-closed。切回旧 force-aware policy 后 cache copy 仍工作。GeoPhys feedback sentinel 确认未发 force snapshot query。
- SelectedReferenceEnv 位置 interval 异常复用既有 execution fault latch。

针对性检查结果：

- `PYTHONPATH=.:GeoPhys/src /home/lly/miniconda3/envs/geochora/bin/python -m pytest -q task_env/diagnostics/tasks/test_phase_ii_c02b_position_profile.py task_env/diagnostics/tasks/test_phase_ii_c02b_admission.py`：**12 passed**，包括 S1 与既有 R1 required-force admission / no-plan legacy compatibility。
- `PYTHONPATH=.:GeoPhys/src /home/lly/miniconda3/envs/geochora/bin/python -m pytest -q task_env/diagnostics/tasks/test_phase_ii_c02a_controller_bindings.py`：**11 passed**；一条 Taichi 上游 `locale.getdefaultlocale` 弃用告警，无失败。
- changed source `py_compile`、`git diff --check` 与本轮更新文档的本地相对链接检查通过。
- 本轮未运行完整回归。S1 使用 contract/state fixtures、session probe 和 method sentinel；不包含 native provider actuation。

## Generic H5 v3 真写读最小合同

后续沿用现有 `TransitionRecorder` + `RecorderConfig(schema_version="v3")` 和 `load_structured_control_records_h5()` / `load_structured_training_actions_h5()`。每个 outer transition 至少要把 reset boundary 与后继 boundary（T+1）、两组原始 structured action、唯一 writer 的 canonical action、versioned target/profile identity/hash、Provider applied payload/target hash ack 和 outcome 写入同一个现有格式；`env_meta`/`action_schema` 等既有 metadata 保存 Artifact/Scene/source closure、ResetSample/episode、Provider/backend、Profile/ActionConfig、映射和 0.002×5 timebase。load 后检查 finalized、T/T+1、transition/ack/hash/outcome，并直接读取 observation state leaves，比对 joint/frame 数值、`StateBoundaryIdentity`、reset identity 和 sample clock。

当前既有 structured reader 会校验控制记录与 action projection，但不会返回或核对 raw observation leaves。因此只读 structured transition record 不足以宣称 state storage 回读通过。实现时先试现有 generic H5 v3；若字段无法表达本合同，再在既有 Recorder owner 中提出最小版本化扩展。本轮没有写 H5 文件、没有从磁盘回读任何状态，也没有改 H5 schema/Recorder。

## 建议的后续最小实施边界

第一轮代码落在 [position profile](../../../../../task_env/controllers/canonical/position_profile.py)、[Controller target contract](../../../../../task_env/controllers/canonical/contracts.py)、[existing control/session owner](../../../../../task_env/runtime/sessions/control.py)、[MuJoCo/GeoPhys session policies](../../../../../task_env/runtime/sessions/mujoco.py) 与 [selected lifecycle](../../../../../task_env/tasks/reference_env.py)。Candidate Artifact/ResetPlan 与 exact RuntimeSource adapter 暂由诊断构造器构建，不开放 task registry/default factory。R1 Controller、C02a required force fixture、A05 fixture、GeoPhys pin 和冻结分支均未修改。

下一层只需在当前 owners 上补真实双 Provider S2 与 Generic H5 v3 producer/readback：分别实际 materialize candidate；核验 reset 后首个 typed sample、开/闭/受阻位置命令、真实五步区间、Provider applied ack、read-only snapshot 和磁盘 state leaves；接入现有 recorder，不添加第二套状态或 Recorder。继续保持 R1 required-force gate。C02c、Assembly、GeoPhys force refresh 和跨 Entity actuation 不在本轮或下一层最小工作范围。
