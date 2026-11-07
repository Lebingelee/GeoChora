# G05 5c attempt002 — 通用任务接线返工准备

状态：待维护者批准，准备本身不启动 attempt；5c 已执行一次且仍未接收。继承 attempt001 的四条 PickCube 有界证据和独立主审；不得仅凭本计划声明能力通过。

返工面向不依赖 Panda Position profile 的公开任务 RGB 接线、声明驱动的 GeoPhys 灯光及实际不支持能力的清楚拒绝。Env 创建时选择 renderer 并保持至 close；同步 observation 和 GeoPhys physics × MuJoCo renderer 仍是原定目标，同一 Env 切换 renderer 已延期。不得为 PickCube、Pendulum 或双轮车特设渲染路径，不重复完整历史矩阵。

`PendulumEnv` 与 `TwoWheelBalanceEnv` 的单环境类均通过 `BaseTaskEnv = SelectedReferenceEnv` 构造；它们采用组件生命周期，并不意味着已有 5c task RGB 支持。优先尝试 Pendulum 的真实有界验证，遇具体限制可尝试双轮车；不因可选第二任务未跑成而自动否定满足原范围的通用证据。真实运行与旧的独立观察图像分开报告。

组件路线使用 runtime assembly、snapshot 和各自 observation builder，现有 task RGB 实现绑定 selected Position 路线；接线需真实覆盖公开构造、reset、step 及 observation，而非仅改变类型检查。保留原 state-only API、现有物理和 Controller 准入；按受影响范围验证，清楚报告实际支持的 renderer 和 source。

维护者允许保留 attempt001 的预算预约和临时目录执行偏差及其未知项，不追加不可恢复的历史调查；见 [Sol 独立主审](../maintenance/reviews/20261108_5c_attempt001_sol_review.md)。执行包、具体预算和必要的 provider 改动均待本次单独批准；用户手工转交，Sol 独立主审。

## 维护者补充：统一 Env 与通用构建模型（2026-11-08）

本包按两层推进：一是在 `SelectedReferenceEnv` 的实际构造、reset、step、close 上接入 renderer，以真实发布状态与相机为输入，覆盖 selected 与组件式调用链；二是分析并在本包所需接缝内推进“受控主体＋场景中的客观实体”的通用声明、编译绑定和生命周期消费，避免 Panda 作为公共渲染或通用生命周期的特殊条件。明确给出两条链的映射、公共 owner、保留差异、可行性和迁移路径；本次所需统一接线须落地，大范围迁移须以实际能力为据，不用纯设计替代 5c 交付。

现有 Pendulum 和 TwoWheelBalance 的组件 scene composer 不接受 robot agents，受控关节经 task action adapter 驱动；受控主体不等同于现有 Robot/Agent 类型，可以是有具名控制通道的机械机构，也可以无可复用 Controller。客观实体可以为空，或是 cube、桌面等被动对象；不为满足命名强造机器人、物体或控制器。PickCube 的任务语义和 Panda 控制器仍可专有，其 renderer 与通用接线不得依赖该专有 profile。不得以统一表面类名宣称构建、发布和资源生命周期已统一。

维护者批准此前提议的执行范围和预算，并要求上述两层细化；完整可执行范围以重新冻结的 attempt002 包为准。仍由维护者人工转发；第三次普通 attempt 前须重评。

### Agent／Controller 候选（维护者后续问题）

优先分析将 Pendulum 和双轮车声明为现有 `AgentComponent`，将直接转矩 action adapter 纳入 Controller 边界。现有 `AgentReferences` 已包含非机械臂的关节、执行器等通用字段，`ActionAdapter` 与 `Controller` 协议均提供 `action_space`、`reset`、`convert`，所以有可复用基础；当前两任务尚未注册为 Agent，原 scene composer 拒绝 robot agents，不能称为现成功能。`RobotRuntime` 当前还有 Panda gripper/base/ee 等假设。须核查 inline source 复用避免模型重复、通用运行 handle 和配置、controller 与 provider 适配边界以及原直接转矩动作语义。可按真实能力做所需最小适配和兼容验证；若全量迁移超出本包资源或无法保持语义，保留具体差距并交 Sol 决定，不影响用户要求的 renderer 主线。
