# v2.1.1 API 与迁移入口

历史记录：3b attempt001 已通过公开 factory 在三条指定路线完成 seed31 的10步与独立读回，整体仍为 PARTIAL、待 Sol 复审：三路线短窗正向位移均未过冻结门。PickCube F06 的 `env.step` 接受既有8维绝对世界位姿与开口动作，并复用已绑定 Controller 的结构化投影；其 Recorder 保存该运行的请求、模型和原生确认。其他 Position 路线仍按各自声明要求 typed action。详见[3b attempt001执行摘要](../maintenance/reviews/20261105_3b_attempt001_execution.md)。

当前状态：阶段3前限定核心收尾及G03的3a–3c均已按各自范围接收，详见[3c独立主审及阶段收尾](../maintenance/reviews/20261106_3c_attempt001_sol_review.md)；生命周期R1已获[Sol有限接收](../maintenance/reviews/20261105_lifecycle_unification_sol_review.md)。当前可调用入口以 [TaskEnv 当前 API](../../../../../task_env/doc/api/index.md)和源码为准；selected 环境实现已迁至 `task_env.environment.reference_env`，旧导入保留兼容。`BaseTaskEnv` 已是 `SelectedReferenceEnv` 同对象兼容出口，三个组件任务使用共同 episode owner；源码与无引擎契约已复核，后续的[CPU 代表回归](../maintenance/reviews/20261105_pre_stage3_resumed_physical_checks.md)按实际源码提交和路线记录，不扩展到其他组合。本页下表是阶段3–6的设计目标，并非当前能力；已有行为及证据不因本页或导入成功而扩展。

Phase C 的标准方向是外部 Solution 读取 observation 并产生 action，由调用方交给 `env.step(action)`；现存 `step_expert()` 是受限兼容，不是新标准 Env API。部分 `step_with_solution()` 路线由 Env 调用调用方持有的 Solution，属于受限过渡；NutAssembly 现支持调用方直接传入含来源边界和控制请求的 `ExpertAction`，并在 `observe` 校验五个 native 样本；裸数组仍拒绝。PickCube seed31 与 NutAssembly seed19 已在 MuJoCo CPU 上完成有界物理回归和独立读回，证据及源码身份见[验证记录](../maintenance/reviews/20261105_pre_stage3_resumed_physical_checks.md)。详见[当前 Solution 说明](../../../../../task_env/doc/api/planning/task_owned_solutions.md)。

## PickCube state-only reset 切换（有界接收）

显式选择 `execution.reset_profile="pickcube-state-only-switch-v1"` 后，同一个 PickCube Env 支持在 `reset(options={"execution": target})` 中切换 MuJoCo CPU 与 GeoPhys CPU，或 MuJoCo CPU 与 Isaac 6.2 CUDA；目标配置从该 provider 的默认路由重新解析。此 profile 固定 state／cube 观测，`hand_pose` 是 `panda-v1/ee` 的兼容别名；九关节速度在 info 与记录中保留。每 episode 的 Recorder 必须在切换前 finish。显式 seed 重置 Core 随机流，None 继续已初始化的流，首次 None 初始化新流。预检失败保留旧 episode；开始替换后失败会 fault 并报告已知关闭及未知写入结果。

本包只验证了指定四条边、state-only、单环境、R3 且重力补偿关闭；GeoPhys↔Isaac、其他任务及通用 controller／renderer 切换不在本次范围。已获[Sol独立有界接收](../maintenance/reviews/20261106_3c_attempt001_sol_review.md)，不需attempt002；实际用法及故障边界按本节，不外推全任务能力。

## 需形成的公共体验

4a 开发中的 Position candidate 提供 `panda-direct-effort-v1`、`panda-split-direct-effort-v1`、`panda-direct-effort-wrench-v1` 与 `panda-direct-effort-object-wrench-v1` 物理控制声明；前两项分别由单个或两个 Controller 以 8 个具名输入产生 7 个臂力矩与 tendon 声明分配的两路 finger 力，后两项分别另声明 hand 或静态 peg 的外力输入。模型的零偏置只定义直接力输入，并非 Panda 动力学；静态 peg 的声明不证明自由物体的受力运动。versioned candidate 也可显式携带 `physical_execution`；预检核对 Scene、Artifact、source closure 和状态名称。

未接收的 002 recovery 增加了该候选的 MuJoCo 3.8.1 CPU physical profile 路线；物化前检查依赖版本与 source 身份。相同 session 在 native build 后核对名称、轴、actuator 力限／gear、tendon 和 equality，将已准入关节贡献与 hand wrench 合并写入广义力缓冲；position drive 保留，显式完整 PD 与未协调 position drive 仍拒绝。source actuator 力域用于约束声明的 direct contribution；保留的 position drive 可叠加，二者总和不受该 direct contribution 界限保证。2026-11-06 在 source closure `aa4ca97bbe3c61b30752ba0dedc6c88a24394f03fe1b53519052d460ff9abc47` 完成单 Controller effort、双 Controller effort 和 effort 加 hand wrench 的各一次 5 子步短运行，确认提交与写入回执；ACK 不是力测量，该次 4a 运行当时尚未完成 4b 物理效果验证。该 002 历史 A05 Position candidate 的其他 provider physical reset 当时仍拒绝；这一时点结论不覆盖后续 PickCube physical candidate。合成映射不能授权真实写入，旧 position 路线保持原身份。

Sol 已按 [attempt003 独立主审](../maintenance/reviews/20261106_4a_attempt003_sol_review.md)有界接收原 4a 控制契约和条件性 4b 方案；4b 后续有界接收三后端 effort 和 MuJoCo 代表外力；独立测力未证明。

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

## 4b 有界物理控制路线

版本化 `pickcube-physical-candidate-v1`（MuJoCo／GeoPhys CPU）和 `pickcube-isaac-physical-candidate-v1`（Isaac Sim 6.2／CUDA、F06）通过既有 factory、SelectedReferenceEnv 和 RuntimeSession 提供 Panda 七臂及受源约束的成对双指 effort；直接贡献的限幅不代表与保留的原生 position drive 叠加后的总力。每个 interval 的贡献由 session 持有并清理；MuJoCo／Isaac 逐子步重施各自的有效写入，GeoPhys 保持本 interval 的公开广义力并在结束时清零，其独立 `hold_reapply` 声明当前拒绝。重复贡献、无效映射和未经协调的完整 PD 与活动 drive 组合被拒绝。原 source 的 tendon、equality 和 mimic 不变，不能由此推断两根手指可独立任意施力。

同一共享 Controller 可使用具名关节参考或 R3 末端参考。质量矩阵版本采用各 source 在指定初态公开读回的固定降维矩阵，限定 0.15 rad／0.019 m 状态邻域，并只在声明的 cadence 和原生 drive 已禁用的有界 fixture 中使用；它不是通用动力学模型或力传感器。MuJoCo／GeoPhys 使用公开 actuator 隔离，Isaac 使用公开增益接口，原始 source 未改写。直接 effort 路线仍允许按声明与 source drive 共存。

MuJoCo 的独立版本化自由体和 Robot hand fixture 分别验证实际外力响应与 world force、body-local 偏置点和点参考矩的语义；手部旋转后逐子步更新 frame 和 Jacobian。自由体与手部证据不代表其他 provider 的 BodyWrench 物理验证。所有物理响应为运动观察，ACK、计算力矩及公开模型读回不作为独立测力。

各次直接 effort 和外力实验的中间版本证据已按实际受影响路径作有界关联；最终版本的参考 Controller 对照不代替逐输入实验。具体接受范围及原失败见[002 独立主审](../maintenance/reviews/20261106_4b_attempt002_sol_review.md)。

## 4c 有界 reset 控制路线

MuJoCo CPU 的 `pickcube-physical-candidate-v1` 可显式设置 `reset_switch=True`，在 `reset(options={'controller': 'r3-pose'})` 或 `'joint'` 时选择控制器；需要调节参数时可用 `{'controller': {'kind': 'joint', 'parameters': {'kp': 120.0}}}`。`physical_action_spec()` 返回当前输入语义、参数、身份和 generation；用 `bind_physical_action(values)` 生成该 episode 的输入并交给 `step`。旧 episode 的输入即使 shape 相同也会拒绝。`action_space_policy='fixed_semantic'` 在破坏已有 session 前拒绝不同语义；这个候选是单环境标量接口，不承诺原生 batch。

`reset_for_solution` / `step_with_solution` 可将既有 PickCube Solution 的绝对位姿送入 R3 reference 和具名关节 effort。该路线使用对应 MuJoCo source 的状态相关质量矩阵与 bias、禁用原生 position drive，并复用 Generic H5 v3 Recorder；记录的 ACK 和 admitted effort 不等于独立测力。seed 31 原任务成功和 A→B→A 证据经[独立主审](../maintenance/reviews/20261106_4c_attempt001_sol_review.md)有界接收，不扩展为其他 seed、source 或后端资格。任务 profile 将 MJCF actuator8 编写的 ±5 N 运行时配置为 ±10 N，与原 2c 任务配置一致；该成功不证明 ±5 N 条件。详情见 [4c 计划](../planning/stage4-4c-attempt001.md)和该 attempt 的 ignored 原始证据。

<a id="visual-state-binding"></a>
## 5a 显式 visual-state 绑定（有界接收）

`pickcube-physical-candidate-v1` 的 MuJoCo CPU Position 路线成功 reset 后，可将 `CameraGeometry` 交给 `env.bind_visual_state(camera)`，再用 `env.sync_visual_state()` 消费最新已发布的 typed boundary。`env.visual_model_info()` 返回 source closure、具名几何／材质／相机／灯光、renderer-only 所有权和限制；`env.visual_body_pose(entity_id, frame_id)` 返回拥有的 body-origin world pose 副本。这个显式入口属于已有 Env 和 camera owner，独立 visual model 只复制 CPU 状态并运行同步 kinematics，不调用 physics step 或 Controller。reset／close 清理自有 renderer；不转移 physics 所有权。

此候选要求同一 Scene／Artifact／source closure 的具名 scalar Joint、floating Joint 和 Frame；floating body 使用米、右手系、world body origin、wxyz，四元数正负等价。重复、缺失、错来源、stale 或不支持的变形表示拒绝。该接口是 binding-only：构造用的 camera geometry 不构成 RGB 请求；对该 profile 的 capture 明确拒绝，RGB 能力为 unknown。普通旧 camera 路径、state-only 默认和旧 codec 保持原语义。seed 31、MuJoCo 3.8.1 CPU、同一 PickCube source、单 Env 的两次边界已由 [Sol 有界接收](../maintenance/reviews/20261107_5a_attempt002_sol_review.md)；此结果不证明窗口、正式离屏 RGB、同步 observation、renderer 切换或 GeoPhys／Isaac／cross 支持。runtime finger cap ±10 N 与 source ±5 N 的既有边界不变。

视觉更新或其结果验证失败时，renderer binding 进入 fault 并尝试关闭自有资源；即便回滚后的 Frame poses 可核对，也须重建 binding，因为这不能证明所有 renderer 派生字段均已恢复。故障后不再提供 pose、sync、capture 或旧 receipt 作为当前结果；已返回给调用者的旧 receipt 只表示它原来的历史边界。`env.visual_binding_status()` 报告 fault 与 renderer close 的实际状态，close 失败时释放结果为 unknown；physics Env 不因该 renderer 故障被关闭。reset 后可重新 bind，已有其他 owner 不受此绑定清理影响。

<a id="observer-candidate"></a>
## 5b observer 路线（有界接收）

MuJoCo CPU 的 PickCube 候选及 Isaac 6.2 的 F06 候选可在构造时传入 `render_mode='human'` 或 `'rgb_array'` 和显式 `observer_camera`。`render()` 使用已发布边界；RGB 为拥有的 HWC float32 数组，窗口与任务 observation 分离。MuJoCo 的 RGB 路线检查 offscreen GL 附件为 `GL_LINEAR` 且禁用 framebuffer sRGB 写转换；无法核实时拒绝该帧并使 renderer fault。receipt 所述为未经色彩校准的 framebuffer RGB，不能推断标准 sRGB、已知原色或输入纹理色域。Isaac 候选将公开 PhysX body 位姿同步到 renderer-facing Fabric，再核对全部发布 body 和具名 frame；变换或时钟不一致时拒绝帧。其 RGB 声明为 RTX tone mapping 后的 sRGB 传递函数；采集前后核验指定 RTX 设置和 OCIO 文件摘要，未通过时拒绝该帧。该声明不校准原色或源素材色域。该候选依赖实际 F06 source／App，并不证明任意 Isaac 场景。

此前 Isaac 原生 viewport 的关闭会使共享 App 的物理时钟和运行态失效。当前选定候选使用 headless App 和 GeoChora 自有窗口；正常关闭窗口与 App 崩溃是不同情形，适用证据及限制见[诊断主审](../maintenance/reviews/20261107_5b_diagnostic_attempt002_sol_review.md)。

F06 候选可在 `make_env` 构造时另外提供 `task_camera=CameraGeometry(...)`，当前仅支持一个 world 挂载、与 observer 使用不同 camera ID 的相机，且需与同一 TaskArtifact 关联。每次 reset 的现有 Isaac 场景 owner 会创建该 USD camera；`env.task_camera_binding()` 从当前原生场景核验并读取几何、source、相机路径与状态边界。它是几何绑定，不自动采集 task RGB、depth 或 segmentation；reset 替换场景并重新绑定，close 释放场景。它不表示通用挂载或同步 task observation 已实现。真实场景观察相机运动和读回已在 F06 具体配置下有界接收。

PickCube physical candidate 的 MuJoCo CPU observer 与 GeoPhys CPU rasterizer observer 也可在构造时声明一个 world-mounted `task_camera`。任务相机与 observer 的 ID 必须不同；MuJoCo 当前还要求两者的 clip 和分辨率相同。`task_camera_binding()` 读取各自 renderer owner 的实际 camera；它不创建自动 observation。这两条 CPU 路线的真实窗口、相机隔离和 RGB 证据已按各自限定范围独立接收。

5c 实施候选提供单相机同步 RGB：在 `make_env` 同时传入 `task_rgb_camera=CameraGeometry(...)` 和固定的 `task_renderer`（`mujoco`、`geophys` 或 `isaacsim`）。`reset` 和正常 `step` 的 observation 自动包含 `task_rgb`（HWC、float32、0–1 的 owned host copy），`info['task_rgb_v1']` 包含相机、状态边界、采集阶段及 renderer 身份；无需调用 `.render()`。`env.metadata['task_rgb_v1']` 记录色彩语义，三种 renderer 的颜色并非跨设备标定。相机须为所支持的 world-mounted 几何，实际 provider/backend 与 renderer 必须满足准入；renderer 在创建时固定，reset 不接受更换 renderer。旧 `task_camera` 只声明几何，不与新 `task_rgb_camera` 同时使用。

当前实现交集为 MuJoCo CPU × MuJoCo、GeoPhys CPU × rasterizer、Isaac Sim 6.2 PhysX × RTX，以及 GeoPhys CPU × MuJoCo renderer-only；实际交付证据和未闭合项以 5c 报告及独立主审为准。该机制面向符合已支持 source/state/control 契约的 selected Position 环境，其他任务的真实 native 场景尚未经本次代表用例验证。task 相机不提供 depth、分割、动态挂载或多相机承诺。


PickCube 的 GeoPhys CPU joint-effort 候选也可请求 observer，使用具名的 GeoPhys `rasterizer` compute 路线。它检查材质和灯光资源报告，缺失必需特性或使用默认太阳光时拒绝采集；PickCube 的 authored `top` trackcom 聚光灯和默认头灯使用同一公开状态边界更新；源零位质量中心由编译模型计算，实时质量中心由公开 body pose 和质量计算。投影能力未覆盖或其他 authored 灯光设置未准入时拒绝采集。相机有限 near/far 使用光轴距离，当前只准入无粒子、TAA、overlay 和 native graphics 的 CPU mesh／analytic 组合。若材质和灯光检查通过，RGB 从 renderer 的 ACES 后 gamma 2.2 值转换到 sRGB 传递函数；原色及源素材色域未校准。此前使用默认灯光的 CPU 离屏试验仅为探索证据；后续使用源灯光的所选 rasterizer 真实窗口/RGB 和 5b 相机隔离已按限定范围接收，这不代表同步 task observation 已接通。

5b attempt001 的未接收历史见 [Sol 主审](../maintenance/reviews/20261107_5b_attempt001_sol_review.md)；三路线 5b 当前接收范围与限制见[最终主审](../maintenance/reviews/20261107_5b_diagnostic_attempt003_sol_review.md)。同步 task observation、renderer 切换和 cross 组合仍属 5c，尚未完成。
