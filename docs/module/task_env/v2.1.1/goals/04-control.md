# G04：统一物理命令与 Controller reset 切换

发布后导航（2026-11-17）：G01～G07／22个子阶段均按各自范围有界接收，v2.1.1已发布。本页早期“当前／未启动”描述保留对应交付时点；最终状态见[当前摘要](../maintenance/current-state.md)，明确后移项见[遗留清单](../../../../releases/v2.1.1/remaining-work.md)。

规划标识：`V211_G04_CONTROL`。3 个子阶段，依据[控制协议](../contracts/control-and-feedback.md)及[已确认基线](../maintenance/20261103_protocol_baseline_confirmation.md)，扩展既有 Robot／Scene／ControlGroup、canonical contracts、ControlBinding、R3 和 session。2c 成功参考不自动成为迁移后成功。

2026-11-06编排修订安排（维护者已采纳）：本Goal继续以原4a／4b／4c主线和出口为准。[装配Panda](../planning/stage4-assembled-panda.md)是v2.1.1附加集成用例，不再逐项追加为4a–4c的接收条件。建议在4b主能力稳定后取得空载／夹爪／补偿的首次代表证据，4c可提供已匹配的PickCube成功参考，两个任务完整复用由7a收口；未完成的附加项单列状态，不掩盖共享控制能力缺陷，也不取代原三后端effort、BodyWrench或Controller reset门。4a已执行两次且未接收；维护者采纳[主审与第三次前重评](../maintenance/reviews/20261106_4a_attempt002_sol_reassessment.md)，要求先进行002授权续作，再视结果决定003。续作已返包，经[独立主审](../maintenance/reviews/20261106_4a_attempt002_recovery_sol_review.md)仍不接收4a。维护者已手动转发最后普通attempt003；其原4a出口经[独立主审](../maintenance/reviews/20261106_4a_attempt003_sol_review.md)有界接收，count=3。4b attempt001/002 的三后端 effort 与 MuJoCo 代表外力经[Sol 独立主审](../maintenance/reviews/20261106_4b_attempt002_sol_review.md)有界接收，普通 count=2；原失败和覆盖范围保留。4c attempt001 经[Sol 独立主审](../maintenance/reviews/20261106_4c_attempt001_sol_review.md)有界接收，count=1；三子阶段的各自边界和未覆盖项保留。

<a id="4a"></a>
## 4a：控制主体、typed 命令、公共反馈与模型

- **输入／依赖：**1c、2c、3c；当前协议取代历史7＋1 closure-effort提案。
- **工作：**在既有owner内落地嵌套Robot／组件的具名受控通道和Controller binding、JointEffort与BodyWrench版本值／capability／回执、TypedLoadExtension槽、显式贡献组合和单一提交入口。Core不固定Panda维度；Panda profile明确定义8维输入→7臂力矩＋2手指关节力。
- **映射：**记录axis/sign/unit、原生actuator/gear/tendon/mimic、可实现力域、约束与限幅。Closure可在Controller内部存在；双指独立控制不从两路输出推定，不能移除原生约束。BodyWrench明确body/frame/point/moment reference/duration；普通物体与Robot body均可声明。
- **检查：**结构化[控制案例](../planning/control-command-cases.json)、source映射、stale/duplicate、未协调覆盖与重复PD拒绝；声明sum允许叠加，同一wrench与J^T投影不重复；hold/reapply不错误累加。ACK、估算与实测分开。
- **模型：**Controller只依赖Core公共state/model接口；FK/J/M/bias库可替换，依赖版本/source/clock/cadence/freshness明确。无live SDK分支或第二physics step；required缺反馈拒绝。
- **交付／出口：**命令、嵌套主体及公开模型边界落地；三后端7＋2 effort实际验证计划和BodyWrench最小真实样例的目标／路线／frame／作用点／oracle／预算冻结。BodyWrench不能整体延后，也不自动增加全矩阵。

<a id="4b"></a>
## 4b：Controller 组合、直接 effort 与外力执行

- **输入／依赖：**4a，三后端原生施控公开能力和冻结BodyWrench子集。
- **工作：**复用R3参考与共享effort伺服、关节参考和direct effort输入；由Controller输出同一typed命令。真实完成三后端Panda7＋2语义及源约束映射；实现4a冻结的物体／Robot body外力样例。
- **检查：**末端／关节参考、direct joint effort、BodyWrench坐标／偏置力矩、joint effort＋外力有意组合、持续载荷clear/reapply、饱和／采样／cadence及重复PD拒绝。Controller实现不依赖provider；不要求不同输入产生同数值轨迹，也不将native implicit drive当显式PD等价。
- **交付／出口：**三后端共同effort主路线与最小外力代表例有真实证据；position compatibility单列。源约束不支持的任意独立双指力如实拒绝，不能代替应完成的成对力profile。

<a id="4c"></a>
## 4c：reset 更换 Controller 与 Solution 复核

- **输入／依赖：**4b、2c，Recorder和调用方动作规格边界。
- **工作：**同一Env在reset选择Controller／参数／input spec，按realized state重置；action spec／space／generation可查可记。清空嵌套各binding的q_ref、积分器、滤波、pending contribution、force latch和反馈历史。同批action布局共同。
- **检查：**至少两种input spec往返切换、同一物理命令协议、旧命令／载荷拒绝、obs固定、episode内切换拒绝；fixed-space wrapper明确拒绝不兼容变更。独立读回与PickCube成功复核，不沿用迁移前成功。
- **交付／出口：**切换无旧episode控制残留，调用者可识别新action要求；保留迁移差异、真实成功和未支持项。

## Owner 与失败处理

公共控制／模型留在既有Core owner；task-specific gains／Solution和LIBERO benchmark配置留任务目录。Provider扩展须正式公开接口和冻结范围。夹爪路线无法表达请求则报告具体blocker，不把position重命名为effort，不重开F05严格源柔顺／传力研究。

阶段4做相关检查和代表成功；最终三seed九格在7b，非刚体载荷只保留typed接口。

## 附加用例如何消费G04成果

| 原主线 | 必须交付的原能力 | 装配Panda用例的作用 |
| --- | --- | --- |
| 4a | 嵌套控制主体与公共模型、JointEffort／BodyWrench／typed-load槽、贡献组合／唯一提交契约 | 用其需求审阅通道／TCP／模型是否足以表达新Robot，不要求此时完成新Robot类或两任务迁移 |
| 4b | 三后端7＋2 effort、共享Controller、direct effort及最小真实BodyWrench与组合执行 | 主能力稳定后，若完整包已冻结该附加范围与预算，建立新Robot消费者并做MuJoCo CPU空载／夹爪／本体补偿代表检查；未纳入或未完成部分转7a用例清单 |
| 4c | 同一Env至少两种Controller输入规格reset往返、状态清理、固定obs和迁移后PickCube成功 | 优先完成原门；已有精确匹配的成功记录供版本用例复用，新装配短例可提前暴露适配问题，不要求两任务四交集全部通过才接收4c |

本版附加用例完整出口建议由[7a](07-integration.md#7a)负责，排期已由维护者采纳，详见[用例计划](../planning/stage4-assembled-panda.md)。附加结果不会把原G04未完成的门变成通过；若附加检查证明缺陷影响共享控制协议或原主线已声明能力，仍须在对应G04 owner修复。
