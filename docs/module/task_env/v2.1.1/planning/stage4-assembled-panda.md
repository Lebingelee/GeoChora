# v2.1.1附加用例：装配Panda、空载跟踪与Solution复用

2026-11-16交接校正：装配Robot类`panda-arm-hand-v1`及G05短程路线已经存在；完整AP用例仍待7a。当前分项状态以[用例JSON](assembled-panda-use-case.json)和[G07交接](../maintenance/20261116_g07_agent_handoff.md)为准，下文“未实施”等为原规划时点，不作为再次创建Robot的依据。

2026-11-06维护者已采纳重新编排并要求交接阶段4。需求与排期状态为 **MAINTAINER_CONFIRMED_PLANNING**。此项是整个v2.1.1的附加集成用例，不能重新定义[G04](../goals/04-control.md)或替代其原门。当前未实施、未派包，4a–4c仍PLANNED／attempt0；G03接收不重开。文件沿用现有路径作为唯一用例说明，具体检查清单在[用例JSON](assembled-panda-use-case.json)，与原控制协议案例分开。

2026-11-08维护者进一步要求：装配 Panda 作为统一主体/Controller 的实际构建与受影响代表检查提前纳入[5c 诊断重构路线](stage5-5c-diagnostic-refactor-roadmap.md)；本文件的原排期是既有基线，完整两任务 Solution／任务成功等附加用例仍由7a收口，不改写已接收G04或声称此用例已完成。

## 先保留原G04主线

| 子阶段 | 原本必须完成的工作 |
| --- | --- |
| 4a | 嵌套Robot／组件通道和Controller binding；JointEffort、BodyWrench、TypedLoadExtension槽；公共state/model、来源／时序；显式贡献组合和唯一提交契约；冻结三后端effort与最小BodyWrench实际验证方案 |
| 4b | 复用R3与共享effort伺服，末端／关节参考及direct effort进入同一命令；三后端Panda7臂力矩＋2手指力的实际约束映射；物体／Robot body的最小真实BodyWrench、组合、clear/reapply和驱动冲突检查 |
| 4c | 同一Env在reset更换Controller／参数／输入规格，至少两种输入往返；清理控制历史，旧命令／载荷拒绝，固定obs与wrapper兼容；迁移后的PickCube完整成功及独立读回 |

这些出口均不因附加用例减免，也不被“新Panda能跟踪／任务成功”替代。重力补偿不能代替BodyWrench真实外力样例；配置选择新Robot不能代替Controller reset输入切换。上一版把新Robot类、两任务迁移和四个完整交集全部写成4a–4c必达，现撤回这种排期，不撤回用例需求。

## 用例要证明什么

同一个PickCube或Nut任务，通过配置选择原Panda或“Panda裸臂＋独立夹爪”的新Robot。新机器人在声明的任务可行域内空载跟踪夹爪中心TCP，复用现有夹爪控制；各任务原Solution算法和策略参数保持，物体／路径可行时完成任务。空载包含机器人自己的手掌／手指重量，不包括额外抓持物载荷补偿。

装配位置、质量／质心／惯量、摩擦、驱动参数、初始关节角可以不同于原一体Panda。验收看自身模型下的实际控制和任务结果，不做一比一物理复刻或轨迹等价。夹爪中心是公开TCP；自身坐标／末端方向由Robot和Controller解释，原Solution若输出位姿则继续执行既有动作语义，不强制复制原生原点或+58.4 mm旧安装偏移。

## 推荐放置：4b后早验证，7a完整收口

| 时点 | 附加用例安排 | 与主线接收的关系 |
| --- | --- | --- |
| 阶段3收尾后／4a | 用本用例审阅嵌套binding、TCP、公共模型及贡献组合能否表达需求；冻结一个最小代表路线的精度／可行域测量计划 | 不在旧位置控制链另建装配补偿；不把新类及两任务适配列为4a完成条件 |
| 4b主能力稳定后 | 若原完整4b包已包含该附加范围和独立预算，建立新Panda类／最小正式消费者，做MuJoCo CPU空载点位／路径跟踪、夹爪开闭／代表抓放及自身模型补偿检查 | 原三后端effort和BodyWrench先完成。附加项单列结果；没有预先纳入或未完成的用例工作交7a，不临时追加提示或延长窗口 |
| 4c | 完成原Controller reset门和迁移后PickCube成功；可复用为本用例的原Panda参考。有已接通新Robot时，可在预先冻结的附加预算内先跑一个PickCube闭环 | 不以两任务四交集齐全作为4c新门；共享能力缺陷若影响原门，仍由G04修复 |
| 7a集成 | 补足新Robot的两任务正式配置接线，完成原／新两机器人在PickCube、Nut上的四种交集；各任务复用原Solution并独立读回 | 作为本版附加用例完整出口单列接收，不能因“附加”而静默删除；未完成／失败如实保留并交维护者决定 |
| 7b稳定输入 | 只对7a之后受影响的用例输入定向复核，仍匹配的更强证据直接复用 | 不把新增机器人乘进原三后端×三seed九格，不为凑四个run重复已有有效参考 |

这样既能在阶段4发现真实Controller／模型接口问题，又把两任务的完整接线和Solution复用放在原本就负责Nut与调用者复用的7a。全部放在阶段3会重复旧控制适配；全部等到7a才首次检查跟踪则容易过晚发现共享控制缺口。推荐的早检查是用例安排，不是原G04新的接收前置。

## 用例需要的适配实现

在 `task_env/robots/` 创建独立Panda描述类，拟议 `panda_assembled.py::AssembledPandaAgent`，UID与配置字段在承接它的完整包冻结。复用BaseAgent／AgentComponent及已有注册、arm Controller和实际任务夹爪算法；允许适用的增益、模型、限幅及开口映射。现有PandaAgent保留，不复制Controller、Solution、Runtime或Recorder。

新类提供来源／装配、具名关节与夹爪、中心TCP、初始状态及控制绑定。用例必须实际经过任务配置→同一make_env→现有PickCube／Nut selected_binding与source构建→所选Robot→公共state/model与控制绑定→原session／Recorder。只注册类、仍使用硬编码旧来源不能证明用例；两个任务共同消费一个Robot定义，正常代码不按实验名分支。

可复用 `robots/panda.py`、`robots/gripper.py`、canonical R3／gripper servo、`FixedAttachmentPlanV1`及现有裸臂＋Hand候选。候选中的固定seed、测试前缀和专用诊断行为不转为正式Robot契约。新Robot描述及任务配置接线是“用例适配实现”；命令、模型与贡献的公共能力仍由原G04 owner实现，两者分别列工作和结果。

## 补偿、精度与任务证据

本体补偿按显式选择的根连通刚体集合，以新装配自身质量／质心、关节状态和安装变换计算；夹爪分支可纳入，桌面、任务物体和接触负载不自动纳入。通过阶段4公共贡献组合统一施加并记录实际应用／限幅。沿用已声明真实驱动约束，不把3b位置目标偏置重命名为通用effort，也不增加任意灵巧手／移动基座矩阵。更广方向见[装配树提案](gravity-compensation-assembly-tree.md)。

用例首次精度运行前，按任务需求冻结位置误差，原动作需要时冻结姿态误差，以及任务路径／可行域、速度、控制和观测cadence。只用必要的保持和代表路径检查实际跟踪，不以3b极小保持误差反推新门，不要求原／新物性相等。若无法满足精度，先区分公共控制缺陷和该Robot的模型／参数适配，归对应owner；不得因用例标签而掩盖原主线缺陷。

首个代表路线建议MuJoCo CPU、固定基座、一套新装配；PickCube31、Nut19是候选，须确认物体和任务路径在所选机器人的可行域。其他provider的新Robot覆盖单独声明，不从MuJoCo结果外推。G04原有三后端控制门继续使用各自已声明资产交集。

7a要收口的是两任务×两机器人四种交集的有效证据，不是必须新启动四次native。4c原Panda／PickCube成功等仍精确匹配的证据可复用；迁移后未验证或代码受影响的交集才补跑。各任务保持同一Solution算法和策略参数，不加Robot UID策略分支；Robot／Controller配置可不同，绑定和运行身份自动更新。奖励、成功门和任务业务逻辑不随机器人选择改写。完整任务成功、Solution完成、记录读回和close分别报告，短程step不代替任务成功。

## 状态与执行边界

用例独立状态为PLANNED，检查点不是新子阶段或新增attempt序列；实际工作并入承接阶段的一个完整工作包并遵守其计时／attempt规则。G04接收看原门，用例最终接收在7a；用例未通过不等于可直接宣称版本全部完成。该排期已由维护者采纳，具体实施仍须完整包。

当前无实施、native、自动派发或新执行对话。七阶段／22子阶段不变；阶段4执行分支与准确输入在正式包准备时确定并继承已接收G03。本次仅在现有主题分支更新规划，不自行merge或创建执行分支。
