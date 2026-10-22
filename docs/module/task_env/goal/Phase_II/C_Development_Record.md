# Phase C 开发记录 — Execution、Lifecycle、Solution 与 Recording

> **2026-10-23 范围决定**：本记录声明的交集按 [维护者决定](../../../../maintenance/phase_ii_scope_freeze_20261023/maintainer_scope_decision.yaml) 获有界工程接受；历史 S0/S1/S2/S3、失败、原 pin 与缺失原件记录保持原义。本次范围冻结不产生新 Task freeze、发布或 Qualification。

日期：2026-10-22。当前状态：C02b **声明交集的有界工程出口满足**；C02c 通用切换、C05c 常规 native-rate Reader 合同及未准入组合单列。
旧 BLOCKED 报告属于逐步解阻过程，不作为当前结论；P99 两项有界运行出口已由维护者接受；v2.0.0 发布仍须独立 Release Gate。
目标契约见 [03_Phase_C_Execution_Lifecycle.md](03_Phase_C_Execution_Lifecycle.md)；唯一状态/依赖入口为 [05](05_Architecture_Review_and_Execution_Order.md)。

## C01

C01a 复用 configuration normalize owner 固定配置优先级和静态 Execution Plan；C01b 使用实际 Task requirements/Provider manifest 做动态 admission。
静态 plan、注册和 import 不授予能力；错 source/backend/device/profile/manifest 在 materialization 前拒绝，构造失败回收已分配资源。
旧 no-plan/config/selected 路线保留，不向所有 Provider 共用 manifest 添加 force capability。
原 C01b receipt 和命令保存在 [整合前 Phase C](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/03_Phase_C_Execution_Lifecycle.md)；定向 detector 为 `test_phase_ii_c01a_execution_plan.py` 与 `test_phase_ii_c01b_dynamic_admission.py`。

## C02a

`ControlBindingPlanV1` 在同一 Scene-v3 Entity×Group owner 编译 action/Controller/resource/required-state 身份。
structured request 必须完整通过全部 Group 预检，资源唯一 writer；错 group/schema/source/plan/Controller/boundary 在 compute/apply 前拒绝。
writer 名称本身不证明真实 Controller 已绑定；真实 identity 包含算法/配置、source、TCP 与实际实例契约。
历史交叉回归 87 passed；此切片只提供 binding/preflight，不冒称真实 dispatch。

## C02b

已批准必需出口逐项有证据：单 Entity Position、最小双 Entity Position、旧 PickCube reset freshness、双 Provider 精确 typed-force admission、单 Panda structured R1 连续执行及同文件 H5 回读。
无依据追加 dual-Entity R1、CUDA R1、Assembly 或 Qualification 为本切片必需条件；这些未准入扩展不机械维持 BLOCKED。

### 解阻过程与位置 Profile

最初缺口不是“GeoPhys 没有公开 Reader”，而是其旧版本 force reset freshness、样本 phase/validity，以及 Core typed publication/admission 不足。
旧 pin 的真实 probe 在产生 −30 N 后连续 reset、0 s、无新物理步仍读到 −30 N；按现有转换会成为 +30 N，但该审计没有调用 R1 compute。
审计证据：`workspace/maintenance/c02b_feedback_source_sampling_audit_20261021_001/`。后续修复 pin 的证据不能抹去这个历史结果。

C02b-P 审阅为 COMPOSE_EXISTING / EXTEND_EXISTING，复用 CanonicalPandaController 的 DLS/位置算法与 gripper 限幅，不另写控制算法。
独立 `panda-main/position-servo-v1` 只要求 Joint/hand Frame；hand-origin TCP 有版本/source identity，不借用 legacy `panda-v1/ee` 或不存在的 `nutassembly_ee_site`。
Position 路径不查询 measured actuator force，physical force-limit command 不等于 force query；旧 production-r1 required force 保持。
S1 初轮 12 passed + C02a 11 passed；后续 candidate 构造、SelectedReferenceEnv lifecycle、recording 联合 92 passed。
GeoPhys CPU/MuJoCo CPU 独立进程均完成 64 interval/65 boundaries 的 S2/H5：100 Hz、每 interval 五个 2 ms steps，FK/Jacobian 与 arm/gripper 运动、seed/reset/horizon/close/fault guard 通过。
native 完成步最初由公开 clock 增量推断，未声称独立完成计数器。
Evidence：`workspace/maintenance/c02b_position_s2_20261021/`。

### 最小双 Entity Position

同一 world/RuntimeSession 两个 Panda 独立根，两个 Position writer、四个 Group、16 个资源；没有 attachment。
新 Scene/Artifact/closure 独立于 A05 frozen fixture：Scene `3c14e4b41c4659388e2e005d836d8477cf1eb5f7a120ba46050bc40a50d18bed`，
Artifact `e02cc46b7810a481680c1b93951632745393e6769c6b9eb3c7ca77fcaa4be7b7`。
历史 GeoPhys `4436787e` CPU 与 MuJoCo CPU 各 30 interval/31 boundaries；完整 request/两 target/两 ack/state 数值 H5 回读和重复 reset 通过。
first-writer 已 apply、second-writer 失败时，物理未推进但控制已部分提交，C03a 闭锁；不声称原生原子回滚。
17 项 Position tests、83 项相邻回归通过。Evidence：`workspace/maintenance/c02b_dual_entity_20261022/s2-final-geophys-r2/` 与 `s2-final-mujoco-r2/`。
这是原 pin 的有界证据，不伪装成 a53 当前 pin 重跑；维护者已接受其原 pin 的精确工程范围，不外推为 a53 双 Entity 重跑。

### Reset freshness 与 typed raw-force

修复基线先为 `eb870f6f`，后对齐并复验 GeoPhys `a53a8cfed7c9d6464274b5c96fca601271dc4ee4`，未仅替换 SHA 常量。
Provider 现有 reset/state/observation owner 在最终 ResetSample 写入后提供不推进物理的 reset-forward 样本；Core boundary/adapter 绑定 episode/reset/evaluation identity。
legacy PickCube seed 31 的重复 reset freshness/首次 closing 通过；它与 Scene-v3 candidate 的 +4 N reset 样本是不同 source/config，不要求 reset force 一律为 0。

现有 typed-state owner 增加 `CanonicalStateViewV2` / `snapshot_v2()`，保留 v0/v1 mapping/hash，v1 和 Position 路径不变。
raw signed force 含 Entity/Actuator、单位、input、validity、sample sequence、state/config revision、phase/native index/time、Scene/source、materialization、episode/reset/boundary。
required 缺测、非有限、错单位/phase/identity/sequence 拒绝；read 不推进物理或重新计算样本。
`control_feedback()` 仍唯一转换 `closing_force_N = max(0, -signed_force)`；N 只对受审计 Panda tendon/source 使用，不泛化到旋转 transmission 或每指接触力。

精确准入绑定 Scene-v3 R1 candidate 的 Artifact `97e0f33d06bc58831a946e3a0cdf277f3f52efe5b2bcf801192a965631c90efd`、
source closure `aa4ca97bbe3c61b30752ba0dedc6c88a24394f03fe1b53519052d460ff9abc47`、实际 R1/hand-origin TCP 和 plan。
GeoPhys 仅 a53 CPU；MuJoCo 仅 3.8.1 CPU 的精确 Python/native build digests，均不扩展 shared capability manifest。
MuJoCo binding SHA `9067239d3126392729430d12d077ab4b298c61d2ea1209c9333823be410359e3`，core library SHA
`8969010a8325d32b9b154159862ffe3b112277cc993983a0168f7dbe2efe0592`；完整 identity 见历史 typed-force 原文和 receipts。
两路 reset→typed publication→真实 R1 compute/apply→五 native steps→下一 publication 均通过。
reset 样本约 +4 N；GeoPhys 后续 −0.038249 N、MuJoCo −0.000466946 N；后者 sample time 8 ms、evaluation time 10 ms。
phase 是最后完成 native step 所用 pre-integration force，不是 post-integration 重算值或五步平均。
S1 35 passed（S1-only 命令另 deselect 1 native），两 Provider 各 S2 1 passed。
Evidence：`workspace/maintenance/c02b_r1_geophys_a53a8cf_20261022/`、`c02b_r1_mujoco_typed_force_20261022/`。
历史早期 eb870 GeoPhys `s2_probe.json` 曾被默认测试路径覆盖，原始 bytes 不可恢复；独立 a53 副本与旧日志保留，未重造丢失原件。

### Structured R1 行为与同文件 H5

GeoPhys a53 CPU 与精确 MuJoCo 3.8.1 CPU/build 各 485 interval/486 boundaries，open→close→obstructed-close→force-hold→reopen。
R1 实际消费 GeoPhys −3.0923 N / MuJoCo −3.0658 N 并进入 force mode，10 个 hold interval 保持，再 reopen 清除；readiness 两路均 false，单列保留。
最终 source-FK pose 满足事前 6 mm / 0.035 rad；没有调整 force 阈值或 pose 容差。这里不证明 task success/Expert completion 或稳定 30 N 接触夹力。
Generic H5 v3 同文件逐值读回 request、feedback、target、ack、state、时钟与身份；native sample/index 增量和外层 clock 佐证每 interval 五步，没有 RuntimeSession 独立子步完成计数器。
GeoPhys H5 SHA `cb8554628a5780682e01d2befe4171ed0d6dad8432492ef1d87e016be5c5c109`；MuJoCo
`372a3fb9a1c3abb432e53fc6924bf98f42222bdddbb28d2a607a20c0bc23d8b7`。
69 项定向、2 项 stale/reapply 与 2 项 Evidence 防覆盖回归通过；原失败探索保留。
Evidence：`workspace/maintenance/c02b_r1_structured_r1_closure_20261022/geophys_cpu_run_018/`、`mujoco_cpu_run_005/`。

## C02c

单 Panda Position Profile 在完整非终止边界、active Generic H5 v3 下，同 schema/source/TCP/资源/required state/timebase 更换实例。
switch 本身不 reset、compute、apply、step 或追加 transition；既有 BoundaryEvent 记录请求/生效，下一真实 step 才产生新 target/ack。
旧 identity target 在 dispatch 前拒绝；事件写入失败沿用 C03a 闭锁，不声称物理回滚。
GeoPhys/MuJoCo CPU 两路 bounded S2/H5 与 16 项 S1 通过。
通用 arbitration、R1/Guard、dual-Entity switching、schema 改变与 Assembly 切换为未准入/延期范围。
完整命令/Evidence 路径见 [历史 C02c 收据](https://github.com/Lebingelee/GeoChora/blob/a5ba5376e90804a3681d4e9535128bcd705457d3/docs/module/task_env/goal/Phase_II/03_Phase_C_Execution_Lifecycle.md#c02c-bounded-single-panda-position-receipt2026-10-22)。

## C03a

复用 `SingleTaskLifecycleAdapter`、`BaseTaskEnv`、`SelectedReferenceEnv`；保留 Gymnasium 5-tuple、clock、horizon、terminal guard 和 success 后继续完成 Expert。
Fault receipt 分开记录公开时钟判断的物理进度、observer 确认子步、Recorder 确认子步与 transition 状态。
边界不可读/证据冲突为 unknown；物理完整推进不代表 Recorder 完整，缺 receipt 的 pending 区间不生成有效 transition，闭锁后不能续步。
不清除 pending、不新增 recovery Runtime、不假装物理回滚；受录制 pending 阻止 reset 时关闭并重建。
后续 append copy/capacity failure 保持原子；最终子步后抛错、中途推进、clock 冲突、缺 final Recorder receipt、append 提交失败均有独立负例。
历史 correction 定向 70 passed；后续 fence/atomicity 回归与日志见整合前 Phase C 原文。

## C03b

独立 Stop 在最后一个完整公开边界结束 episode，不调用 Controller/apply/physics，不追加伪 transition，不回写已经返回的 terminated/truncated。
`EpisodeEndV1`、`EpisodeTerminationPolicyV1` 与 H5 v3 training reader 区分 external Stop、task terminal、horizon、execution fault 和 bootstrap policy。
Position 继续 success 后执行；旧 R1 拒绝新 Stop，v2 active recording/vector/未声明 typed control 的 v3 wrapper 也明确拒绝。
S1 78 passed；双 Provider Position T=0/T=1 Stop/H5 S2 通过；Pendulum scalar 仅 GeoPhys CPU，MuJoCo 因 ExecutionPlan NOT_ADMITTED。
close T=0/T+1=1、重复 close 仅 finalize 一次；真实 step 后 Recorder fault 不生成伪 transition。
Evidence：`workspace/maintenance/c03b_stop_20261021/final_run/`。

## C04

既有 ObservationBuilder/ObservationSchema 与 info_schema 明确 leaf shape/dtype/unit/frame/time/visibility，state、privileged_state 与 legacy private_state 各保留语义。
必需 feedback/clock 缺失失败，不能填零；diagnostics off 只省可选 clipping facts，不删除 required control/readiness/metrics。
Pendulum GeoPhys CPU 有真实 reset/step schema/time 证据；generic Panda 曾因 Stage-1 scene composition 未完成而拒绝，不能以 Position candidate 通过改写该路线历史状态。
Camera capture metadata reference 不等于相机 buffer 已进入 policy observation/Recorder。

## C05a

C05a1 为值/版本/finalizer/Event/Outcome；C05a2 为 Generic H5 v3、T/T+1 与最小 training reader；C05a3 为 canonical outer/execution stream 的独立版本域和负例。
复用既有 Recorder，不把 NumPy writer 冒充 action-tree writer。
`load_structured_control_records_h5()` 回读结构化控制；training actions/episode 要求显式单 writer schema/order、numeric projection 和 end/bootstrap policy 一致。
raw numeric observation 另从同一 H5 dataset 逐值核对，不能以 control reader 成功代替 state readback。
未知 outer/logical version、错 request/target/ack/boundary/Event/Outcome 均拒绝；storage roundtrip 不证明 D0 reconstruction/replay qualification。
旧 generic v1/v2、canonical-v0 和 execution v1/v2 的分离语义不变；缺历史原件仍见 [B04a](B_Development_Record.md#b04a)。

## C05b

task-owned `build_readiness_solution()` → `reset_for_solution(solution, seed=31)` → `step_with_solution(solution)`；同一 external Solution 独占阶段 memory。
公开带边界 identity 的 readiness/target/applied ack；`Solution.observe()` 在 Recorder append 前执行。
readiness/observer/append failure 沿用 C03a latch，不能 finalize 为完整 canonical 轨迹。S1 FakeSession 只证明 lifecycle，后续真实 S2/S3 单列。

| legacy PickCube × CPU | intervals / boundaries | Task success / Expert completion | 最终 lift |
| --- | --- | --- | --- |
| GeoPhys a53 | 148 / 149 | step 147 / 148 | 0.10764 m |
| MuJoCo 3.8.1 | 470 / 471 | step 469 / 470 | 0.10607 m |

两路相同 frozen Artifact/source、生产 R1、`panda-v1/ee` 与 seed-31 ResetSample；100 Hz、五个 2 ms steps。
Task 0.10 m、Expert 0.105 m 标准未改；canonical-v0 同文件 state/identity/action→target→ack 数值读回通过。
首次 GeoPhys run 后 checker 属性名错误，保留失败并由修正的独立 reader 对同一 H5 通过，不归因为 Provider 执行失败。
定向 72 passed。Evidence：`workspace/maintenance/c05b_external_s2_s3_20261022/`。
不强制 legacy Artifact 迁移成 Scene-v3 plan，也不把它当成 Scene-v3 R1 candidate 的证据。

## C05c

复用 task-owned NutAssembly external Solution、R3、native interval/Guard 与 execution Recorder。
100 Hz outer、2 ms physics、五 steps；R3 10 N target/cap、Guard 8 N/0.1 s/50 连续样本不变，arm hold/ramp、Outcome/strict failure 分开保留。
MuJoCo 3.8.1 CPU：2,377 transitions/2,378 boundaries/11,885 native samples；Task success step 2,013，Guard 4.56 s 授权/4.57 s 消费，closing 9.0036 N；同文件 execution H5 S3 通过。
Evidence：`workspace/maintenance/c05c_native_s2_s3_20261022/`；H5 SHA
`645bc41015e022b95b342abd403e433cae7bde8a8bfe300676114f3cf7ef78e5`。

GeoPhys a53 四组独立进程，seed 19 / NA-S0/source/轨迹/阈值/物理参数固定，仅 backend 与 gripper-law cadence 变化：

| Physics / gripper | T / native samples | update / hold | Guard closing | 完整 H5 SHA-256 |
| --- | --- | --- | --- | --- |
| CPU / 100 Hz | 2443 / 12215 | 2443 / 9772 | 9.7561 N | `2f127e625a593f63954c15bcd48a8f7b23b85e988fed5a60eaf806a4135109d2` |
| CPU / 500 Hz | 2442 / 12210 | 12210 / 0 | 10.0000 N | `93d2817135ecc27f477dcfd779c1cdfdadae5f3589f7863cbdaa1285d9314176` |
| CUDA / 100 Hz | 2443 / 12215 | 2443 / 9772 | 9.7588 N | `b03106d0e503a79519538371fd713566eb12861441e0d21cefeb76430a9778ac` |
| CUDA / 500 Hz | 2442 / 12210 | 12210 / 0 | 10.0000 N | `187ab241ef03d9bd28935116695d6619732ecf69961fe505780a7c0badeab3dc` |

四组 task/Outcome/原 strict Expert completion 无 warning/fault；Guard 5.17 s 授权/5.18 s 消费，50 个连续样本。
100 Hz 只是 gripper law 每 interval 一次更新加四次 hold，Guard/force sampling 仍逐 2 ms；不能称作 Reader 降为 100 Hz。
CUDA 确实是 Taichi CUDA/RTX 5060 physics，Controller/force readback 仍在 CPU host，不是 device-resident。
Reader 均值约 0.294–0.304 ms，速度约 0.098×–0.164×，没有实时门槛。
这是维护者授权的逐 native step `read_cpu_snapshot()` **诊断例外**；通常低频 host Reader 合同未因此扩展，不授予常规 native-rate capability/Qualification。
常规支持需 Provider owner 明确 phase/freshness/sequence/config-state revisions/invalidations/cadence，再由 Core 绑定 episode/reset/evaluation。
Evidence：`workspace/maintenance/nutassembly_gripper_cadence_geophys_20261022/comparison.json` 及四组完整 H5。
早期 cadence、浮点时钟、held gripper ack、float32 回读 checker 修正有失败日志，不改变物理阈值；CPU100 首次 checker 停止后由同文件独立 S3 通过。
四组 H5 不含 RGB，总计 84.84 MB；它们外置于轻量包，轻量收据本身不足以重做所有逐值 S3。

## Public candidate

新公开 UID `panda-position-servo-candidate-v1` 经现有 `make_env()` 与同一 SelectedReferenceEnv owner 构造。
GeoPhys a53 CPU、scalar/state-only、固定 seed 31、horizon 1–6000、100 Hz/五个 2 ms；不接受其他 provider/backend/render 或隐式 extra kwargs。
reset 后 `env.position_plan` 只读暴露 plan/schema IDs；完整 structured arm/gripper action，通过既有 start/finish recording。
同一个 env 64 steps/65 observations，实际 arm/gripper 运动、request/target/ack/state/clock/identity 与 Generic H5 v3 同文件逐值回读通过。
缺/错 source/plan/seed/action 与非空 source workspace 拒绝，import 不初始化 native runtime；录制失败沿用 C03a。
它仍是无 Task success/freeze 的 candidate，不把真实运动称作新任务成功。
Evidence：`workspace/maintenance/p99_runtime_closure_20261022/public_s2/`；当前 pin renderer closure 见 [D05](D_Development_Record.md#d05)。

## 历史原文与当前范围

原始 C 记录及各专题报告保存在 Git `a5ba537`，[历史原文导航和文件迁移表](05_Architecture_Review_and_Execution_Order.md#history) 逐一对应。
本轮为文档整合，未重跑上述 S1/S2/S3 或 Qualification。通用 Stop/vector/学习 consumer、一般 Controller switching、常规 GeoPhys native-rate 合同、CUDA R1、Assembly 与新 Task freeze 不由本记录获得支持。
