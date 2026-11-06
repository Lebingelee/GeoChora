# v2.1.1 API 与迁移入口

历史记录：3b attempt001 已通过公开 factory 在三条指定路线完成 seed31 的10步与独立读回，整体仍为 PARTIAL、待 Sol 复审：三路线短窗正向位移均未过冻结门。PickCube F06 的 `env.step` 接受既有8维绝对世界位姿与开口动作，并复用已绑定 Controller 的结构化投影；其 Recorder 保存该运行的请求、模型和原生确认。其他 Position 路线仍按各自声明要求 typed action。详见[3b attempt001执行摘要](../maintenance/reviews/20261105_3b_attempt001_execution.md)。

当前状态：阶段3前限定核心收尾及G03的3a–3c均已按各自范围接收，详见[3c独立主审及阶段收尾](../maintenance/reviews/20261106_3c_attempt001_sol_review.md)；生命周期R1已获[Sol有限接收](../maintenance/reviews/20261105_lifecycle_unification_sol_review.md)。当前可调用入口以 [TaskEnv 当前 API](../../../../../task_env/doc/api/index.md)和源码为准；selected 环境实现已迁至 `task_env.environment.reference_env`，旧导入保留兼容。`BaseTaskEnv` 已是 `SelectedReferenceEnv` 同对象兼容出口，三个组件任务使用共同 episode owner；源码与无引擎契约已复核，后续的[CPU 代表回归](../maintenance/reviews/20261105_pre_stage3_resumed_physical_checks.md)按实际源码提交和路线记录，不扩展到其他组合。本页下表是阶段3–6的设计目标，并非当前能力；已有行为及证据不因本页或导入成功而扩展。

Phase C 的标准方向是外部 Solution 读取 observation 并产生 action，由调用方交给 `env.step(action)`；现存 `step_expert()` 是受限兼容，不是新标准 Env API。部分 `step_with_solution()` 路线由 Env 调用调用方持有的 Solution，属于受限过渡；NutAssembly 现支持调用方直接传入含来源边界和控制请求的 `ExpertAction`，并在 `observe` 校验五个 native 样本；裸数组仍拒绝。PickCube seed31 与 NutAssembly seed19 已在 MuJoCo CPU 上完成有界物理回归和独立读回，证据及源码身份见[验证记录](../maintenance/reviews/20261105_pre_stage3_resumed_physical_checks.md)。详见[当前 Solution 说明](../../../../../task_env/doc/api/planning/task_owned_solutions.md)。

## PickCube state-only reset 切换（有界接收）

显式选择 `execution.reset_profile="pickcube-state-only-switch-v1"` 后，同一个 PickCube Env 支持在 `reset(options={"execution": target})` 中切换 MuJoCo CPU 与 GeoPhys CPU，或 MuJoCo CPU 与 Isaac 6.2 CUDA；目标配置从该 provider 的默认路由重新解析。此 profile 固定 state／cube 观测，`hand_pose` 是 `panda-v1/ee` 的兼容别名；九关节速度在 info 与记录中保留。每 episode 的 Recorder 必须在切换前 finish。显式 seed 重置 Core 随机流，None 继续已初始化的流，首次 None 初始化新流。预检失败保留旧 episode；开始替换后失败会 fault 并报告已知关闭及未知写入结果。

本包只验证了指定四条边、state-only、单环境、R3 且重力补偿关闭；GeoPhys↔Isaac、其他任务及通用 controller／renderer 切换不在本次范围。已获[Sol独立有界接收](../maintenance/reviews/20261106_3c_attempt001_sol_review.md)，不需attempt002；实际用法及故障边界按本节，不外推全任务能力。

## 需形成的公共体验

4a 开发中的 Position candidate 提供 `panda-direct-effort-v1`、`panda-split-direct-effort-v1`、`panda-direct-effort-wrench-v1` 与 `panda-direct-effort-object-wrench-v1` 物理控制声明；前两项分别由单个或两个 Controller 以 8 个具名输入产生 7 个臂力矩与 tendon 声明分配的两路 finger 力，后两项分别另声明 hand 或静态 peg 的外力输入。模型的零偏置只定义直接力输入，并非 Panda 动力学；静态 peg 的声明不证明自由物体的受力运动。versioned candidate 也可显式携带 `physical_execution`；预检核对 Scene、Artifact、source closure 和状态名称。

未接收的 002 recovery 增加了该候选的 MuJoCo 3.8.1 CPU physical profile 路线；物化前检查依赖版本与 source 身份。相同 session 在 native build 后核对名称、轴、actuator 力限／gear、tendon 和 equality，将已准入关节贡献与 hand wrench 合并写入广义力缓冲；position drive 保留，显式完整 PD 与未协调 position drive 仍拒绝。source actuator 力域用于约束声明的 direct contribution；保留的 position drive 可叠加，二者总和不受该 direct contribution 界限保证。2026-11-06 在 source closure `aa4ca97bbe3c61b30752ba0dedc6c88a24394f03fe1b53519052d460ff9abc47` 完成单 Controller effort、双 Controller effort 和 effort 加 hand wrench 的各一次 5 子步短运行，确认提交与写入回执；ACK 不是力测量，尚未完成 4b 物理效果验证。其他 provider 的 physical reset 仍拒绝；合成映射不能授权真实写入，旧 position 路线保持原身份。

Sol 已按 [attempt003 独立主审](../maintenance/reviews/20261106_4a_attempt003_sol_review.md)有界接收原 4a 控制契约和条件性 4b 方案；真实三后端物理施力与实测力仍未验收。

attempt003 修正持续 BodyWrench：Controller 在 outer boundary 提交一次原始 typed 命令，MuJoCo session 在每个 physics substep 用当前构型刷新运动学和 Jacobian，将各声明的表达 frame、作用点与力矩参考重新解析后，与 joint effort 合并并替换自有缓冲；正常 interval、异常、reset 与 close 清理可辨认的自有贡献。该路线对 BodyWrench 目前只准入 source-bound `implicitfast` 积分器；其他积分器写入前拒绝。非空或被外部修改的力缓冲拒绝，未提供与 UI/其他 writer 并发叠加能力；冲突时不覆盖被改写的槽位，其混合归属和剩余力不能推断，须结束该故障 session。`torque_Nm` 是关于声明的 `moment_reference` 的总力矩：力矩参考为作用点且为零时，偏置力在 body 原点有 `r×F` 力矩；参考为 body 原点且总矩为零时，不再额外加该项。上述 002 的实际候选使用 body frame 和 body origin 参考，不能当作 world force、作用点零矩的 4b 案例。新逐子步语义有定向 fake 和 A05/implicitfast 有界 session 证据，未证明其他 provider、其他 source／积分器的物理效果。

| 操作 | v2.1.1 目标 | 责任与边界 |
| --- | --- | --- |
| make_env／配置 | 查询并选择合法 physics／solver／renderer／Controller／batch 组合 | 复用 registry 和配置解析，Core→任务类→YAML→调用方 |
| reset | 新 episode 按初始化规则选择允许的执行组合／Controller | 同一public Env内部重建，不迁移旧物理状态；Core sampler按seed规则保持；固定 obs；原生 batch 按批次切换 |
| step | 运行已确定的组合，返回当前边界状态／图像和评价 | 不在步进中替换 provider 或 renderer；Controller 依赖公共反馈 |
| render | 可配置相机的 human／RGB 可视化 | 与相机 observation 协调，额外调用不推进任务物理时间 |
| 查询 | 实际生效配置、能力／拒绝原因、action spec／space | 输入规格可随 reset 更换 Controller 改变，调用方负责匹配 |
| close | 清理自有资源并使借用数据失效 | 原生共享资源和进程级 runtime 不假装每 env 独立销毁 |

用户只配置backend／renderer／controller／camera等，不需构造receipt hash、lease ID或generation。

权威语义见[协议索引](../README.md)；语义按已确认五协议，生产字段／方法在所属后续包冻结，阶段 3–6 随实现补齐 API 页面。`ExecutionSpec` 等现有类型与兼容解码须显式处置，不因本表新增平行 facade。

## 兼容和迁移记录要求

- 当前 selected state-only 输入继续有明确行为；新 renderer 不能通过无条件放开 admission 接入。
- 旧 position／mixed 命令和新 JointEffort／BodyWrench 主路线区分身份与准入；Robot／嵌套组件声明通道，Panda8维输入→7＋2输出，贡献显式组合，不改变旧证据含义。
- observation 构建后固定；动作输入变化须更新 schema／space，fixed-space consumer 不支持时明确拒绝。
- `BaseTaskEnv` 等保留名字按既有 2.x 约束处理，先迁生产 caller，不能创建第二套 reset／step。
- PickCube、NutAssembly 迁移按真实实现和 caller 收口，LIBERO 保留 benchmark 语义；不宣布全部任务已统一。
- 记录格式变化沿用已有 Recorder 和独立 reader；episode 配置、旧版本读取及失败行为有检查。

完成 3／4／5／6 阶段时更新对应 API 与迁移说明，7c 汇总。新示例只能使用已实现并验证的公共入口，不能以概念示例冒充已运行代码。

## Panda 重力选项（有界接收）

selected 构造的 `controller.gravity_compensation` 是可选布尔值，默认关闭；当前开启仅支持 MuJoCo CPU 进程内的 PickCube／NutAssembly 位置驱动，其他选择拒绝。详细来源、实际执行回执和限幅语义见[重力补偿指南](../guides/panda-gravity-compensation.md)。

MuJoCo／GeoPhys 旧 selected CPU RuntimeSession 的 `snapshot_free_joint_native_v1()` 返回当前边界具名自由关节位置与速度的拥有值副本，含 sample、materialization、时间、单位和速度坐标约定；它不推进物理。该接口不提供力传感数据；基于 USD 的 body-COM 原生读回使用既有 `snapshot_v1` 投影。

GeoPhys 的 `GeoPhysRuntimeBoundary.read_model_snapshot()` 委托 provider 的 `RigidSolver.read_model_snapshot()`，从该次物化的有效字段复制 body、joint、actuator、equality 和 tendon 值；session build facts 将 provider ID 绑定到同一来源名称。该快照不推进物理，缺失字段明确标注 unavailable。Isaac F06 另保存同一 bootstrap 边界的公开 Jacobian 和 tensor 连杆姿态，供轴方向与来源独立比较；读取前后物理计数必须一致。这些只读事实不构成跨 provider 功能认证。
