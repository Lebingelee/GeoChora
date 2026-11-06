# G04/4b attempt001：实施与验证规划

状态：准备中，尚未启动或接收。原始出口以 [G04/4b](../goals/04-control.md#4b) 为准；继承 [4a 有界主审](../maintenance/reviews/20261106_4a_attempt003_sol_review.md)及其条件性 4b 方案。该方案的 GPU、模型接口、阈值与预算均为候选，4a 主审明确没有批准其实际运行。本规划在不降低原出口的前提下，冻结本次可执行选择；历史方案和证据不修改。

## 出口与当前缺口

三后端都要经生产入口真实完成 Panda 七臂加受源约束的成对手指 effort，共享 Controller、末端／关节参考、direct effort、限幅／cadence 与重复 PD 拒绝。普通自由体和 Robot body 至少各有一条真实 BodyWrench 代表路线，并验证组合、持续、清除／重施、坐标和偏置力矩；原目标不要求将两种外力样例乘以三个后端。4c 的 Controller 输入规格往返和迁移后 PickCube 成功留待 4c。已确认的装配 Panda 附加例在主能力稳定后另行安排，不是本次新增门。

实际 4a 物理端口仅有 A05、MuJoCo CPU、implicitfast 的代表接线和 ACK；历史运行不构成独立响应、PickCube 接线、GeoPhys 或 Isaac effort 证据。旧的 3a/3b/3c 有界接收、N08 失败、6.1 关闭超时及未实现通用装配重力补偿均保留。

| 路线 | 目标与主要 owner | 本次必须查明并实施 |
| --- | --- | --- |
| M | MuJoCo 3.8.1 CPU；Core 的 `task_env/runtime/sessions/mujoco.py`、`mujoco_physical.py` 与相应 Task Artifact | 将真实 7＋2 和所选自由体／hand 样例接入现有工厂及 session；核对每子步 frame、作用点、参考矩和清除，保留 source 约束。 |
| G | GeoPhys native rigid CPU；GeoPhys 公共 runtime owner 与 Core 的 `task_env/runtime/sessions/geophys.py` | 使用或补齐正式公开的关节 effort、身份／映射与读回能力，再接统一物理命令；不把 `TORQUE` 标签或 position actuator `ctrl` 当作力。必要时修改 GeoPhys 并以本地提交更新 Core gitlink。 |
| I | Isaac Sim 6.2 PhysX CUDA；现有 USD/session 与 `task_env/runtime/sessions/isaac_native_io.py` | 核验本机公开 API、F06 joint/mimic/drive 及生命周期；真实接通 effort 和读回，不把 drive target 或提交 ACK 当测得力。公开 Omni Physics 107 文档仅为候选，不证明本机扩展版本。 |

M/G 参考 PickCube MJCF closure `02f12b11e8215af606d9eed7f22c411dc5bbd74f7d956331b74400b5a1e6963d`；I 参考 F06 USD closure `dc2a87a74963e0ec10f3cf98b3e33cc87226350dde78aeddbc88244a0fbdafc6`；hand 候选 A05 closure `aa4ca97bbe3c61b30752ba0dedc6c88a24394f03fe1b53519052d460ff9abc47`。每次以实际 source/build receipt 核验，不能把先前 receipt 冒充本次；不更改源关节、tendon、equality 或 mimic 以制造通过。不同 source 的夹爪传动及可实现域分别核实，八维输入的末项是受约束的成对贡献，不保证任意独立双指力。

## 验证策略

原条件计划的模型和数值门未经运行验证；它们可在前提真实满足时使用，但不把三后端公开 M/Jc、软约束 forward 副本或某个未验证的 `1e-5` 数值当作原 4b 本身的必备接口。执行者在任何判定性物理 run 前冻结所用 source、步骤、独立 oracle、读回精度、容差依据和无效条件；预检发现计划不可用时，在已有窗口内选择下述预设替代并重新冻结，保留旧结果，不得事后按通过与否调阈值。

每个后端逐一核对七臂及成对夹爪的名字、轴／单位、传动／限幅和 write receipt；每个独立输入至少进行同源同初态的 baseline 与正／负加载对照，且用公开状态或真实测量建立该输入的可观测响应。若使用方向性差分，提前记录基向量 `u`、正负输入及各自由度单位，分别计算两路速度差的广义功率 `uᵀ(v+−v−)`，按 readback 精度和独立重复 baseline 的噪声上界预先设置信噪下限，并检查 source 约束、接触与 drive 状态；不满足可观测前提为 INCONCLUSIVE，不把写入或 ACK 当物理通过。该方向门不声称逐关节实测力或精确动力学；若其假设不成立，使用同源公开质量／约束模型或可校准的独立实际读回，并说明有效性。受影响后端的 joint-reference、end-effector-reference、direct effort 及合批需真实生产入口证据；不要求不同输入轨迹数值相同。

普通自由体优先沿 4a 计划的无接触各向同性 fixture，在现有 Task Artifact/Scene/registry 下注册，显式冻结 source bytes、质量、惯量、时钟与实际积分条件。以同初态零输入为对照，用 `F Δt/m` 与 `(r×F) Δt/I` 预测线／角速度增量，检查持续和清除／重施；阈值在判定 run 前依据参数误差、精度与预检重复误差记录，数据无法支撑即 INCONCLUSIVE。Robot hand 优先 A05，采用 world force、body-local 偏置点、点处零矩的明确 profile，核对 hand 当前构型、参考点与世界 frame，以独立 pose/Jacobian 和 baseline/load 物理响应为依据，覆盖姿态变化后的力方向及清除。仅 writer 内部同一计算、首帧 ACK 或 fake 不能证明真实响应；原 origin-reference profile 的旧结果不能冒充该场景。joint effort 与 body wrench 要证明一次有意合批且物理响应未重复累加；已有 position drive 的贡献与 direct effort 分开表述。

当正常真实配置初态有接触或约束使 oracle 失效时，按 Task Artifact 的正式构造／注册流程提供独立、可追溯的无接触验证 fixture 和新的 source identity；不得篡改原任务成功语义或偷偷关闭原 source 约束。可使用不推进的 public forward/model 读回，不能绕过生产生命周期另造 Runtime，也不能由 Core 读取 GeoPhys 私有 solver 状态。

## 执行治理

复用同一阶段分支与 checkout，采用一个完整实现窗口；预检、接口补齐、针对性修复、受影响测试与原生重试均在包内，不把单次失败记为新 attempt。冻结授权、双锁、资源和输出快照，以实际版本及显存预检后执行。现有候选要求 ≥10 GiB 空闲显存，但本机显卡总量约 8 GiB，故不可原样作为本窗口门；新资源预算由完整派发包和维护者授权确定。验证全程记录 source/build、每次输入、贡献、ACK、独立读回、时钟、误差、清理、失败和步骤预算；受影响证据才重跑。输出技术完成不等于 Sol 接收，不进入 4c、阶段 5、合并或推送。
