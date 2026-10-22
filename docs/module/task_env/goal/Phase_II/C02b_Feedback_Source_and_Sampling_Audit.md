# C02b Feedback Source & Sampling Audit — 真实 Native Probe

日期：2026-10-21。状态：**C02b 仍为 BLOCKED**。本记录只覆盖源码审计、一个受限 GeoPhys CPU 诊断 Probe、相关 admission 定向检查和执行顺序修订；不实现 structured dispatch，也不增加生产 capability 或 Qualification。

> **后续规划范围说明（同日，非新实验）**：本报告的 PROVIDER CONTRACT GAP 针对已声明 raw-force 的 R1 路线。
> 后续恢复审阅允许另审新身份的位置 Profile；它必须在完整消费链不查询测量力，不能改写本报告或声称 R1 解阻。
> 见 [恢复审阅](C02b_Recovery_Architecture_Review.md)和 Phase C 当前恢复契约。下列 Probe 数据及原始结论保留历史范围。

## 结论

整体结论为 **PROVIDER CONTRACT GAP**。GeoPhys 已有公开、稳定、已文档化的 `RobotArmObservationReader`；本轮用临时诊断 adapter 证明，现有 Provider bootstrap/boundary owner 可以在 100 Hz 外层组合 raw actuator-force snapshot，不需要 Core 穿透 session/boundary 去读 solver 私有状态。该组合尚未成为生产接线。先前“GeoPhys 没有公开 API route”的说法过宽：裸 `read_actuator_force` 未公开，不等于公开 Observation Reader 不存在。

但真实 Probe 证明：在目标 PickCube CPU source 中，产生 `actuator8=-30 N` 后立即 reset 到新的 reset sample，公开 Reader 仍返回旧的 `-30 N`，simulation time 已回到 `0 s`，reset 没有新增 native step。第二次 reset 也继续返回 `-30 N`。Reader 给出的数组不带 freshness、reset identity、native sample index、sample phase 或有效性标志，因此现有 Core owner 虽可组合外层 readback，却无法判定首样是否属于当前 episode。不能把这一数值交给首条 closing compute。

因此，现有 Reader 解决了“从哪里在外层读”的问题，尚未满足“读数属于哪个 reset/native sample、是否有效”的 Provider 合同。必须由 GeoPhys 现有 reset/state 生命周期 owner 与 `control.robot_arm` observation owner 补足 force refresh 和采样有效性合同；Core 保持原始 `actuator_force` required，不清除私有 field、不增加物理步、不填零，也不改 C02a schema。

## 被审计的实际 source 与 consumer

本轮范围限定为单 Panda、arm＋gripper、CPU、100 Hz 外层、每 interval 五个 2 ms native steps。实际 source 通过 [PickCube `build_reference(backend="cpu")`](../../../../../task_env/tasks/pick_cube/task.py) 构造：

| 项目 | 实际值 |
| --- | --- |
| Task Artifact | `pick-cube-v1/p1_6_experimental_100hz`，identity `fd5bc96821ca44adcbe507bfd702bf5288ee6bcb045c584c92df7cd4800a54c4` |
| GeoPhys | CPU，repo pin `4436787e9cb85ce519506a2a9af86d1eeec9de2d`；Taichi 0.6.2，Python 3.12.14，x64 |
| source | `task-env-pick-cube`，XML SHA-256 `bdd119833a5ae3c8176daf1f5ef586c3601870f10f4b4b5f6d7aa730fe5f0fed` |
| 实际 R1 对象 | `ProductionCanonicalPandaController`，identity `76108c78b8159391e448ad9f49050bed42fd7a86e0e00a0520083b4e5efb02e9` |
| R1 gripper config | `experimental_rate_limited`，force limit 30 N，deadband 1 N，opening step 0.002 m，force adjustment step 0.0001 m；opening range 0.08 m，position stiffness 2500 N/m |
| timebase | `physics_dt=0.002 s`，`control_substeps=5`，`control_dt=0.01 s`，zero-order hold，post-control-step observation |
| GeoPhys runtime | `implicitfast` integrator，`dt=0.002 s`，`control_substeps=5` |
| actuator source | XML 顺序 `actuator1..actuator8`，`actuator8` index 7，tendon `split`，`ctrlrange=0..255`，source `forcerange=-5..5`，`gainprm=0.78431372549 0 0`，`biasprm=0 -5000 -120` |

实际 R1 对象由上述 source builder 构造，身份/config 已记录，但**没有**接入诊断 session，也没有调用 `.compute()`；算法见 [ProductionCanonicalPandaController](../../../../../task_env/controllers/canonical/production.py)。C02a [binding fixture](../../../../../task_env/diagnostics/tasks/test_phase_ii_c02a_controller_bindings.py) 的 `panda-main/production-r1` 是静态 `ControllerBindingV1.writer_id`，fixture 声明 `panda-main/actuator8`、raw `actuator_force`、newton、required、`evaluation_boundary`、`actuator_force_query`；它本身不证明此 writer 已连到该 R1 实例或 native dispatch。C02b plan-bound admission 仍会在 Runtime 构造前因缺少 `actuator_force_query` 拒绝。

本轮没有混入 NutAssembly R3、500 Hz inner servo 或 Guard 参数。没有更改 A05 fixture、Scene、GeoPhys pin、冻结分支或 production capability。

## 公开 API 与当前边界

在同一 GeoPhys pin 上，通过官方 API registry 查询：

| 查询 | Registry 结果 |
| --- | --- |
| `read_actuator_force` | `unknown-symbol` |
| `control.robot_arm.RobotArmObservationReader` | exact import route，stable，documented |
| `control.robot_arm.RobotArmObservationConfig` | exact import route，stable，documented |

[`control.robot_arm.RobotArmObservationReader`](../../../../../GeoPhys/src/control/robot_arm_observation.py) 的 `read_cpu_snapshot()` 支持 `actuator_force=True` 并返回数组副本；稳定导出见 [`control.robot_arm`](../../../../../GeoPhys/src/control/robot_arm/__init__.py)。其文档将 CPU snapshot 限定为测试、日志、低频评估或 agent 外层采样；高频路径应使用 device refs/buffer，不应每个 physics substep 调用。本轮在 100 Hz 外层读一次的可组合性得到验证；未得出固定性能门槛，也没有验证 GPU/device-side 路线。

Reader snapshot 目前只有 values，没有 measurement validity、reset/sample identity、clock、native sample index 或 force phase。正式 C02b admission 也没有对应 capability claim：Core [`provider_manifest()`](../../../../../task_env/runtime/sessions/api.py) 和 capability schema 不含 `actuator_force_query`。这是 manifest 缺口与 typed publication 缺口两件独立的事。现有 [`snapshot_v1`](../../../../../task_env/runtime/sessions/common.py) 发布 joint/frame 值，没有发布 required raw actuator force；只加 manifest 名称不够。

## Probe 方法与结果

诊断脚本：[`native_probe.py`](../../../../../workspace/maintenance/c02b_feedback_source_sampling_audit_20261021_001/native_probe.py)。最终完整运行的原始日志：[`native_probe.log`](../../../../../workspace/maintenance/c02b_feedback_source_sampling_audit_20261021_001/native_probe.log)；解析后的结果与 API 查询分别见 [`native_probe.json`](../../../../../workspace/maintenance/c02b_feedback_source_sampling_audit_20261021_001/native_probe.json) 和 [`public_api_queries.json`](../../../../../workspace/maintenance/c02b_feedback_source_sampling_audit_20261021_001/public_api_queries.json)。脚本调试重试及其是否推进过物理时间见 [`probe_attempt_notes.md`](../../../../../workspace/maintenance/c02b_feedback_source_sampling_audit_20261021_001/probe_attempt_notes.md)。

脚本只在 GeoPhys bootstrap/Provider adapter 一侧，把现有 runtime boundary 的 actuator-force readback 接到公开 `RobotArmObservationReader`；Core session 不访问 solver 或 boundary 私有 field。为构造这次诊断 session，脚本调用现有底层 `materialize()`，没有调用 `materialize_control()` 或传入 plan；这是仅用于 native 诊断的实例化步骤，**不绕过/满足/证明 C02b plan-bound admission**。采样期间检查 Provider-measured canonical state、simulation time 和 ctrl；未调用 Controller compute。没有清空 force field、加隐藏物理步、重盖 timestamp、加障碍物或改变冻结 source。

调试中曾有一次单独的 scheduler-wrapper 错误：底层 `Simulator.step(substeps=5)` 已返回，但包装器错误假定它会返回 report，导致 boundary clock 更新与 post-step read 尚未运行便关闭该 session。没有消费 force、reset 或调用 R1；该运行不纳入结果表。脚本调试重试影响详见上述 attempt notes。

| 阶段 | reset identity / clock | native steps | `actuator8` raw force | 观察 |
| --- | --- | ---: | ---: | --- |
| 初次 reset 后首样 | seed 31；control step 0；0 s | 0 | 0 N | 读到 0，但 API 无 validity 元数据，故数值的来源/有效性尚无合同保证 |
| 生成非零力 | ctrl 从 255 设为 0；boundary 对 actuator8 设 ±30 N；control step 1；0.010 s | 正好 5 | −30 N | 本次仅开环诊断，不消费反馈；不是故意加阻挡物后的接触力证据 |
| reset 后 | seed 73；control step 0；0 s | reset 增量 0 | −30 N | 与上一 episode 的 force 完全相同，确定复现 stale sample |
| 重复 reset | seed 31；control step 0；0 s | reset 增量 0 | −30 N | 新 reset identity 下仍是同一旧值，重复 reset 串样 |

最终 Reader-backed boundary 计数为 17 次 Reader 读取。单个 interval 经 GeoPhys `Simulator.step(substeps=5)` 正常返回，Provider boundary time 从 0 到 0.010 s；当前 `Simulator` uncaptured 执行路径按 `range(substeps)` 逐一调用 solver binding。Reader 测量的 13 次连续读取期间，Provider-measured canonical state/time 和 actuator ctrl 完全一致；native substep 增量为 0，R1 compute 为 0。Reader 只保存 solver/config，不持有 Controller；没有调用任何 R1 方法，因此读取路径没有 Controller memory transition。结果来自真实 GeoPhys CPU runtime，不是 mock/synthetic force。

### 单位、符号、R1 风险

本次 actuator8 读数为 raw **signed actuator scalar**；该绑定按 C02a requirement 使用 newton。Probe 中真实开环 closing ctrl=0 产生 −30 N；正向 opening 符号来自现有 source/controller binding（高 ctrl=255 对应张开）及 Core 投影代码，本轮未在 freshness gate 失败后再运行正向 opening 物理动作。[`feedback_value()`](../../../../../task_env/runtime/sessions/control.py) 对该特定绑定执行 `closing_force_N = max(0, -signed_actuator_force)`，所以本次代数投影为 +30 N；GeoPhys 当前 [`control_feedback()`](../../../../../task_env/runtime/sessions/geophys.py) 通过现有 Boundary snapshot 读取 raw force 后调用该投影。该 canonical 值是闭合方向幅值，丢失符号；它不是无损 raw force、每指接触力或关节广义力。

R1 当前代码的 force-mode 激活阈值是 `max(0.5, 0.1 * force_limit_N)`；本 profile 为 3 N。若 stale −30 N 被首条 closing compute 消费，投影 +30 N 会超过此阈值。**这是依照当前代码的风险推断；本轮没有调用 R1 compute，因此没有声称实际误激活已被行为探测。**

### 采样相位

GeoPhys [rigid native step](../../../../../GeoPhys/src/solvers/rigid/execution/solver_mixin.py) 在积分之前计算 actuator force。完成五个 native steps 后，字段代表第五步积分前最近一次 force 计算；它不是 integration 后重算值，也不是五个子步平均值。Probe 的 wrapper 能证明一个 10 ms boundary 内向真实 GeoPhys `Simulator` 提交五步且调用正常返回，但 Reader 返回值不包含 native sample index/time/phase；将其关联到第 5 个样本只能从这条受控调用路径推断，当前 Provider 数据没有自行证明这一身份。actuator force 的 gain/bias/limit 计算见 [rigid generalized dynamics](../../../../../GeoPhys/src/solvers/rigid/articulation/generalized_dynamics.py)。

静态对照：[MuJoCo adapter](../../../../../task_env/runtime/sessions/mujoco.py) 在 reset 时走 `mj_forward()` 并缓存 actuator force，native step 后更新完成步缓存。但由于 GeoPhys freshness gate 已失败，本轮**未运行** MuJoCo native reset comparison，也未主张双 Provider Probe 通过。相同语义不要求两 solver 轨迹或力值逐点相等。

### CPU Reader readback 成本

两次完整 Probe 测量均在 materialization/reset 后：

| 运行 | 第一次计时读取 | steady mean | steady median | steady p95（nearest rank） |
| --- | ---: | ---: | ---: | ---: |
| 首次完成运行 | 139,546 ns | 100,883 ns | 99,574 ns | 109,095 ns |
| 最终 file-backed 复跑 | 359,075 ns | 269,257 ns | 267,091 ns | 285,784 ns |

每次 steady 计 12 次。两组数据都用 `perf_counter_ns` 计同一 CPU `read_cpu_snapshot()` 路径，包含 qpos/qvel/ctrl/actuator_force CPU snapshot/copy；数值存在运行间差异，不设通过阈值。最终运行日志显示 Taichi kernel cache 已 warm（2,436 kernels，约 1.07 GiB）；这不是冷启动或首次 kernel compile 测量。完整计时记录见 [`reader_cost_runs.json`](../../../../../workspace/maintenance/c02b_feedback_source_sampling_audit_20261021_001/reader_cost_runs.json)。该读取成本与 fixed-step 语义分开报告，不据此声称所有机器上 100 Hz 性能合格。

## 源码所有者与精确 Provider 合同缺口

当前 Core reset path 在 [GeoPhysRuntimeBoundary.apply_reset_state](../../../../../task_env/runtime/boundary.py) 中 restore baseline、重放 force-limit override、写入 qpos/qvel/qacc/ctrl/act、同步运动学并把 simulation time 置零；它不触发 actuator-force refresh。GeoPhys [runtime snapshot/restore owner](../../../../../GeoPhys/src/solvers/rigid/state/snapshot.py) 保存/恢复的 runtime state 未包含 actuator-force field，也没有在 restore 后重算。公开 Reader 合法读到了这个 field，却无法区分它是新样本还是旧 episode 残值。

应由 GeoPhys 现有 **rigid state/reset lifecycle owner** 与 **`control.robot_arm` observation owner** 补足同一条合同：

1. reset 完成后，对当前 qpos/qvel/actuator state/ctrl 产生有效的 actuator-force 样本，且不得推进 native physics；若该 Provider 不能在 reset 时刷新，则必须明确返回 invalid，并禁止其被当作当前 reset 的 required feedback。
2. 每个值提供稳定 actuator identity/ordering、signed raw force 与 unit、有效 force limit 配置，以及 validity/freshness 标记。
3. 样本携带 reset/materialization identity、evaluation boundary identity、native sample index/time 与计算 phase。区分 `reset_forward` 初值与 `native_step_pre_integration` 样本；post-control boundary 可引用最近一个 native sample，但不得伪称 post-integration 重算或 interval average。
4. reset 更换 reset identity 后，旧 episode 样本必须失效；Reader 不能仅把当前 clock/timestamp 更新成新值而保留旧数值。

建议沿现有 GeoPhys reset/snapshot 生命周期和 ObservationReader 扩展，不新建 Provider/Recorder/Runtime 抽象，也不让 Core 清私有 field。MuJoCo 的 `mj_forward`/完成步缓存可帮助对齐语义，但不是要求 GeoPhys 复制 MuJoCo 算法。

## Core 内最小接入

Provider freshness contract 生效之后，Core 可在现有 Provider bootstrap/runtime-boundary owner 中组合公开 Reader，继续由既有 `ControlledRuntimeSession.control_feedback()` 与 `feedback_value()` 产出 canonical feedback；不在每个 2 ms 子步调用 CPU Reader。本轮结论是“**outer sampling 可 COMPOSE_EXISTING；完整目标暂为 PROVIDER CONTRACT GAP**”，不能把可读性等同于准入。

若 C02a 的 raw `actuator_force` typed requirement 保持不变，现有 `snapshot_v1` typed-state owner 需要一个版本化扩展：发布实际 raw signed scalar，并绑定 actuator/entity identity、unit、boundary/reset identity、native sample index/time/phase、validity 及 `StateViewLifetime`。不能原地改变 `snapshot_v1` 语义、用 canonical closing magnitude 冒充 raw force、只加 capability 名称或填 0。Core manifest 仅在真实 Provider publication 和 admission 测试闭合后，按具体 provider/backend/profile 受限声明 `actuator_force_query`。

## 本轮未运行项目

因为 reset freshness 前置门失败，下列内容全部标为 blocked/not run，未用替代值补齐：

- 向 R1 首次/后续 `.compute()` 传入 force feedback；打开、闭合、受阻闭合、force hold、重新打开行为；
- R1 state/memory 受反馈读取影响、诊断开关与 required feedback 分离的完整双消费者检查；
- MuJoCo native reset/Reader 对照；GeoPhys/MuJoCo 双 Provider 有效反馈 Probe；
- sustained 100 Hz 回路的性能/反馈采样有效性；每个 boundary 样本的 Provider 原生时钟、sample index 和 fresh flag；
- C02b structured dispatch、真实 `panda-main/production-r1` binding、applied acknowledgement、atomic multi-group execution、Recorder 读回、真实 arm+hand S2。

## 下一步与解除 C02b 的进入准则

下一步最小目标应限于 GeoPhys 现有 reset/state owner 和公开 ObservationReader owner 的合同扩展与诊断测试：reset 后刷新或显式判 invalid；在快照中给出 measurement identity/clock/phase/validity；对产生非零 force 后的两次 reset 验证旧样本不再可消费。然后用 GeoPhys/MuJoCo 对照同一 source semantics 验证有效 reset sample 和最近完成 native sample。此步骤不等于 C02b 实施。

C02b 后续进入完整实施前须同时满足：

1. **反馈可信**：目标 profile 下 actuator identity、unit、sign、采样相位和 reset 首样有效性有真实证据，首条 closing 不会消费旧样本。
2. **接入闭合**：raw required value 有真实 typed publication/manifest/admission 路线，canonical 转换复用现有 `control_feedback()`，不需私有穿透或降低 required。

在此之前保留 `BLOCKED` 与现有 plan-bound fail-closed admission；本审计不自动进入任何实施或后续 Goal。

## 定向验证

- 真实 GeoPhys CPU 公开 Reader reset/stale Probe：完成；结果和运行日志见 `workspace/maintenance/c02b_feedback_source_sampling_audit_20261021_001/`。
- 公开 API registry：bare symbol unknown；Reader 与 Config exact/stable/documented。
- 定向 C02a/C02b admission 测试：**14 passed**，1 个 Taichi 上游 `locale.getdefaultlocale` deprecation warning；日志见 ignored `targeted_admission_tests.log`。这些测试只验证既有静态绑定与 fail-closed admission，不验收 C02b。
- 未运行完整 Phase II 回归、双 Provider physics suite、完整 R1 反馈行为、structured dispatch 或 Qualification。

## 恢复审阅补充：证据边界（2026-10-21，未复跑）

此次公开 Reader 的 reset 残留读数是受限真实诊断事实；R1 误激活仍是源码推断。
脚本的 wrapper counter 在调用前累加请求步数，reset 的增量字段为诊断填入的 0，并不是独立的 Provider
完成步计数器。当前五步/无 reset 步进判断结合正常返回、公开 boundary clock 和已审阅执行路径，
不应扩张为每个 native tick 均有独立 completion receipt。后续执行验收须提供完成证据，并在不可判定时保留 unknown。

ResetSample.sample_id 是输入内容身份；重复使用同一样本不会产生新的 sample ID，不等于新的 episode generation。
后续 freshness gate 应在 Core 绑定 episode/materialization generation，由 Provider 提供原生测量有效性/相位/状态版本，
不要求 GeoPhys 引入 GeoChora 的 Scene/ResetSample/Controller 类型。仅返回 invalid 可防止误用，
但在 R1 首次 compute 需要 required feedback 时并不能单独解除阻塞；仍须有合法的初始测量路线。

## 后续修正：C02b-R1 reset-force freshness（2026-10-22）

上文结论准确描述了 2026-10-21 pin 和当时源码状态，保留作历史证据。之后的受限 C02b-R1 修复在同一 GeoPhys gitlink 上实现了 public Reader sample receipt、输入失效和无步 reset-forward 重算，并在 PickCube seed 31 的 GeoPhys CPU 路线上完成同-session 非零力→重复 reset→R1 首次 closing compute 的 S1/S2。MuJoCo CPU 只作语义对照。复现数据、law oracle、样本相位和运行范围见 [C02b-R1 acceptance](C02b_R1_Reset_Force_Freshness_Acceptance.md)；原始结果另存于 ignored `workspace/maintenance/c02b_r1_reset_force_freshness_20261022/`。

因此，`PROVIDER CONTRACT GAP` 中关于 reset freshness 的部分已在该受限 legacy route 上关闭；“公开 Reader 只能给无 provenance 数组”的描述也仅适用于旧合同，现由 `RobotArmActuatorForceSampleV1` 增加版本化 provenance。**C02b 整体仍 BLOCKED**：计划绑定的 manifest 尚未公开 `actuator_force_query`，`snapshot_v1()` typed publication 也未发布 required signed raw force，因此正式 plan-bound admission 仍失败。没有通过改 optional、零填充或伪造 capability 处理该缺口。
