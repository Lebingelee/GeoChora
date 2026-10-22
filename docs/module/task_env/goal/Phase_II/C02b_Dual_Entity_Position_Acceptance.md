# C02b 最小双 Entity Position 隔离施控验收

日期：2026-10-22
状态：**PASS_BOUNDED_DUAL_ENTITY_POSITION_S2**（GeoPhys CPU、MuJoCo CPU）；C02b 整体仍 **BLOCKED**。
实现基线：D05b 本地检查点 `477ff8054fb57356e8d03414f2356dd0f18ea043`；本轮实现和本文尚未提交、未推送。GeoPhys gitlink 保持原 pin `4436787e9cb85ce519506a2a9af86d1eeec9de2d`。

## 1. 范围与候选来源

本轮完成 P00/P99 要求的最小独立双 Entity position-only 执行子项。复用了 `SceneDefinition`、`ControlBindingPlanV1`、`PandaPositionServoProfileV1`、`RuntimeSession`、`SelectedReferenceEnv` lifecycle、C03a fault latch 与 Generic H5 v3。没有实现通用 multi-writer arbitration、Assembly、attachment 或跨 Entity IK。

诊断 candidate 在冻结 A05 Panda source closure 上增加第二个独立 Panda articulated root，并建立新的 Scene/Artifact/source closure：

- Scene ID：`phase-ii-c02b-dual-entity-position-v1`
- Entity/writer：`panda-main` / `panda-main/position-servo-v1`；`panda-secondary` / `panda-secondary/position-servo-v1`
- secondary 的 Frame、Joint、Actuator native name 加 `secondary_` 前缀；world root 平移 `(-1.6, 0, 0) m`
- 两个 articulation 是同一 Scene、同一 native world/session 中的独立根，没有 attachment 或 Assembly
- 每个 Entity 有 arm（7 个 actuator）和 gripper（1 个 actuator）两组，共 16 个唯一资源
- 两个实例复用同一个 `CanonicalPandaController` 算法，但有独立的 Profile/Controller instance、writer identity、target namespace 和 memory
- Reset seed `31`；100 Hz outer、每区间 5 个 2 ms native steps，30 个控制 interval；双 Entity Position 要求均为 evaluation-boundary 上的 9 个 scalar Joint position 与 hand Frame pose，共 10 个字段
- measured actuator force 不读取。S2 将 `RuntimeSession.control_feedback()` 替换为立即失败 sentinel。

新的 source closure 与 Scene/Artifact identity 不等于冻结 A05 identity，也没有改写 A05 fixture。跨 Provider 共享的关键 identity：

| 身份 | 值 |
| --- | --- |
| TaskArtifact | `e02cc46b7810a481680c1b93951632745393e6769c6b9eb3c7ca77fcaa4be7b7` |
| TaskSource | `fada245721df38f723142a7546f724d85209906c2b7b99035861fdc8c16fc56e` |
| Scene | `3c14e4b41c4659388e2e005d836d8477cf1eb5f7a120ba46050bc40a50d18bed` |
| source closure | `34f8d34252556961de0770f66014e692e90b6a8af3e9c1362888298fd044a23c` |
| ControlBindingPlanV1 | `0a96506693985e9a1d6d271ab1562ba3a261bbce72647cd04411577489a27410` |
| ResetPlan | `fc3fe2fb24a2ac45d014fd90f5ad0e8828864dc066b626e66582aba7721ef60e` |
| ResetSample | `reset-982fff488f59446e1ea92deef8048f7948102f2670ba4b7c309e7699743fad02` |

Controller identities：`panda-main` = `11099c060c2d3a4ed738c9992ea4fd443eb644dc033b8128220f23ef6317f39f`；`panda-secondary` = `59689313cc483d6c3190ea4a132e455971fad4d4934e3c64d6054256f5dc2c63`。MuJoCo provider 为 3.8.1 / CPU；GeoPhys 使用仓库 pin，Taichi 0.6.2 x64 CPU。Python 3.12.14。

## 2. 接入边界

Position profile 的扩展只在现有 owners 内完成：Profile 显式绑定 Entity-local Joint/Frame/native prefix/Actuator prefix，并把 typed state 映射到既有 Panda controller 输入。单 Entity `from_source()` 和旧 `panda-main/production-r1` 行为与身份保持；旧 R1 的 required raw-force requirement 没有降级。

直接 `materialize()` 对双 Robot Scene 仍拒绝。精确双 Entity 路线只经现有 `materialize_control()` 做完整 Profile/Artifact/Scene/Source/plan/resource/provider 校验后，以内部专用 authority 进入双根 construction；这不是通用 Runtime materialization 开放。candidate 通过现有 `SelectedReferenceEnv.from_position_candidate()` 与既有 `ReferenceTaskBinding` 构造，没有默认 registry。

一次 structured action 必须有两个 Entity 各自的 arm/gripper Group。Core 先校验全部四组、Entity/Group/action schema、plan/source identity、target boundary、writer 与实际 resource binding；通过后才 compute 两个 target，再按 writer apply/ack，最后只推进一次共享 RuntimeSession interval 并发布联合 typed state。Controller target、AppliedControl ack 与 state 都含 Entity/source boundary/episode 绑定。任一提交前校验失败，两个 Controller 均不 compute，RuntimeSession 不 apply/step，Recorder 不追加 transition。

## 3. S1：冲突与失败边界

新增 [`test_phase_ii_c02b_dual_entity_position.py`](../../../../../task_env/diagnostics/tasks/test_phase_ii_c02b_dual_entity_position.py) 覆盖：

- 两个 writer、四个 group、16 个 Entity-qualified actuator resource 完整且唯一；直接 `materialize()` 双根拒绝。
- 计划层资源/Group 重叠与缺失 Group 拒绝；改变 arm action component 投影但保持 schema 分区合法的 compiled plan，也会因 Profile↔Controller/action/group contract 不一致而拒绝。
- live recording 已开启时，未知 Entity、缺失 action Group、错误 binding identity 均在 compute/apply/step 前拒绝；计数仍为 `(0,0,0)`，H5 transition/observation 仍为 `0/1`。
- 自洽但 provider-materialization identity 错误、或来自上一 episode 的 target，在 `RuntimeSession.apply_control()` 前拒绝。
- 只 compute main Profile 时，main memory 前进一个 control step，secondary memory 保持为零；reset 构造两份新 Profile instance，双方 memory 各自归零，旧 target 不得跨 episode。

提交中失败单独于 preflight rejection 实测。在第一个 writer apply+ack 成功后，注入第二 writer apply 入口失败；记录为 `compute=2, apply_attempt=2, acknowledged_apply=1, native_step=0`。区间请求 5 个 native steps、实际完成 0，公开 clock 未变，C03a 记录 `physical_progress=not_advanced` 并闭锁后续 step。Recorder 保持 `(T,T+1)=(0,1)`，只 finalize 一个 `execution_fault` Outcome，不生成 pseudo-transition。第一 writer 的控制值已提交给 Provider；本证据**不声称跨 Entity 原生物理回滚**，也不把这个无 step 故障等价成物理状态已回滚。

## 4. S2：双 Provider 同世界实跑

GeoPhys 与 MuJoCo 分别在独立进程使用相同 candidate、sample、timebase 与 ControlBindingPlan。两个阶段各 15 个 interval：一个 Entity 收到 hand-origin TCP 的 `+0.025 m` x 位移目标，另一 Entity 的目标保持其当前测量位姿；随后交换目标 Entity 并使用 `-0.025 m`。每 interval 两个 writer 都有完整 Groups、独立 compute/apply/ack；30 个 interval 总计 60 次 compute、60 次 apply/ack、30 次 `RuntimeSession.step()`。

事前容差：FK 位置 `1e-6 m`、符号不变 quaternion L2 `1e-6`、Jacobian 中心差分最大绝对误差 `5e-5`（`epsilon=1e-6 rad`）。结果：

| Provider / backend | main FK 位置误差 | secondary FK 位置误差 | Jacobian 最大误差 | 被命令的 arm Joint delta norm（main / secondary） |
| --- | ---: | ---: | ---: | ---: |
| MuJoCo 3.8.1 / CPU | `8.36e-17 m` | `3.16e-16 m` | `1.01e-10` / `1.01e-10` | `0.24876 rad` / `0.10227 rad` |
| GeoPhys pin / CPU | `4.51e-9 m` | `1.45e-7 m` | `1.01e-10` / `1.01e-10` | `0.12953 rad` / `0.06746 rad` |

每个已完成控制间隔的 public control boundary 增加 1，public simulation clock 增加约 `0.010 s`；按 candidate `physics_dt=0.002 s` 推得每 interval 五个 native steps。这里没有读取 Provider 私有计数器。

没有把未成为当前位移目标的 Entity 状态不变当验收条件。实测它可能因共享物理世界而漂移：MuJoCo 的 secondary 在 main 目标阶段变化 `0.23831 rad`、main 在 secondary 阶段变化 `0.00320 rad`；GeoPhys 对应 `0.07560 rad` 与 `0.05308 rad`。隔离证据来自 writer 的 target actuator key、writer/entity ack identity 和当前受控 Entity 的目标响应；被动状态仍完整记录，不解释为跨 Entity 串写，也不主张零物理耦合。

## 5. Reset 与 Generic H5 v3

每 Provider 录制包含真实 reset observation、30 条 structured controls、31 个 evaluation-boundary observation 与最终 `horizon_reached` Outcome。structured reader 逐条核对请求的四个 Entity-qualified Groups、两个 writer、target hash 与 applied ack hash、episode/boundary identity；直接从 H5 读取双方 `joint_position`、`hand_pose` 与 boundary identity leaves，并与运行中返回的 31 组状态逐值比较。`T=30/T+1=31`，state numeric 与 boundary disk readback 均通过。随后使用同一 ResetSample 再 reset：episode ID 改变、sample ID 保持，两个 Profile instance 均重建且 memory 从 step 0 开始，双方 reset Joint values 匹配 ResetSample。故障 H5 含一条 reset observation、零 transition 和单一 fault Outcome。

Raw ignored Evidence：

- MuJoCo receipt/H5：`workspace/maintenance/c02b_dual_entity_20261022/s2-final-mujoco-r2/mujoco-receipt.json`、`mujoco-dual-entity.h5`、`mujoco-inflight-failure.h5`
- GeoPhys receipt/H5：`workspace/maintenance/c02b_dual_entity_20261022/s2-final-geophys-r2/geophys-receipt.json`、`geophys-dual-entity.h5`、`geophys-inflight-failure.h5`
- 原始 evidence 目录被保留；更早诊断失败目录也未删除，本文只引用最终通过的 `s2-final-*` 收据。

## 6. 定向检查与能力边界

通过的检查：

- 双 Entity 与原 Position profile/execution/H5 tests：**17 passed**。
- C02b admission、C02a controller bindings、C03a fault lifecycle、C05a structured recording、D01b materialization、D02b typed state、selected consumers 定向回归：**83 passed**，一条上游 Taichi `locale.getdefaultlocale` deprecation warning。
- 两个 Provider 的原生 S2 分进程均为 `PASS_BOUNDED_DUAL_ENTITY_POSITION_S2`；报告中每个 Provider 均有 H5 numeric/state/boundary 回读与 partial-apply fault 证据。

本轮未运行完整仓库测试、C02c、R1 force/reset freshness、NutAssembly R3 500 Hz Guard、C05b/C05c、camera policy/Recorder observation 集成、其他 Provider/backend、任意 N writers、跨 Entity attachment/Assembly、whole-body IK 或 Qualification。双 Entity 验收只在本报告的 Scene-v3 candidate × GeoPhys CPU 与 MuJoCo CPU 上成立；不能推及其他 profile/provider 或完整 C02b/P99。

下一步应先由维护者审阅本次窄扩展与 evidence，再决定是否扩展到其他所需 C02b 交集。R1 raw force 和 reset 首样 freshness 是独立 blocker，不应以本次 force-free dual Position 通过替代。C02b、D05b、Qualification 与 Phase II 状态均不因此变更为 complete。
