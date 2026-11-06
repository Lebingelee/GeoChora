# G04：统一物理命令与 Controller reset 切换

规划标识：`V211_G04_CONTROL`。3 个子阶段，依据[控制协议](../contracts/control-and-feedback.md)及[已确认基线](../maintenance/20261103_protocol_baseline_confirmation.md)，扩展既有 Robot／Scene／ControlGroup、canonical contracts、ControlBinding、R3 和 session。2c 成功参考不自动成为迁移后成功。

2026-11-06维护者补充：[装配Panda与Solution复用](../planning/stage4-assembled-panda.md)纳入4a–4c，当前均PLANNED／attempt0。验收看新机器人在任务可行域内的空载TCP跟踪精度、现有夹爪控制复用及两任务原Solution成功；不要求复刻原一体Panda的装配、质量／惯量、摩擦、驱动数值或初始关节角。新类放在`task_env/robots/`并由两个正式任务的配置构建路径实际消费，公共控制／模型owner继续复用。G03接收不重开，本页不启动实施。

<a id="4a"></a>
## 4a：控制主体、typed 命令、公共反馈与模型

- **输入／依赖：**1c、2c、3c；当前协议取代历史7＋1 closure-effort提案。
- **工作：**在既有owner内落地嵌套Robot／组件的具名受控通道和Controller binding、JointEffort与BodyWrench版本值／capability／回执、TypedLoadExtension槽、显式贡献组合和单一提交入口。Core不固定Panda维度；Panda profile明确定义8维输入→7臂力矩＋2手指关节力。
- **映射：**记录axis/sign/unit、原生actuator/gear/tendon/mimic、可实现力域、约束与限幅。Closure可在Controller内部存在；双指独立控制不从两路输出推定，不能移除原生约束。BodyWrench明确body/frame/point/moment reference/duration；普通物体与Robot body均可声明。
- **检查：**结构化[控制案例](../planning/control-command-cases.json)、source映射、stale/duplicate、未协调覆盖与重复PD拒绝；声明sum允许叠加，同一wrench与J^T投影不重复；hold/reapply不错误累加。ACK、估算与实测分开。
- **模型：**Controller只依赖Core公共state/model接口；FK/J/M/bias库可替换，依赖版本/source/clock/cadence/freshness明确。无live SDK分支或第二physics step；required缺反馈拒绝。
- **装配机器人：**增加新的Panda描述类，接通两任务的机器人配置选择、夹爪中心TCP、实际关节／夹爪映射及自身模型；显式选择本体补偿连通子段。复用Controller和夹爪控制算法，允许机器人专属配置。执行前冻结可行域、任务所需跟踪精度及测量口径，物性只绑定本机来源，不与旧Panda逐项比较。
- **交付／出口：**命令、嵌套主体及公开模型边界落地；三后端7＋2 effort实际验证计划和BodyWrench最小真实样例的目标／路线／frame／作用点／oracle／预算冻结。BodyWrench不能整体延后，也不自动增加全矩阵。

<a id="4b"></a>
## 4b：Controller 组合、直接 effort 与外力执行

- **输入／依赖：**4a，三后端原生施控公开能力和冻结BodyWrench子集。
- **工作：**复用R3参考与共享effort伺服、关节参考和direct effort输入；由Controller输出同一typed命令。真实完成三后端Panda7＋2语义及源约束映射；实现4a冻结的物体／Robot body外力样例。
- **检查：**末端／关节参考、direct joint effort、BodyWrench坐标／偏置力矩、joint effort＋外力有意组合、持续载荷clear/reapply、饱和／采样／cadence及重复PD拒绝。Controller实现不依赖provider；不要求不同输入产生同数值轨迹，也不将native implicit drive当显式PD等价。
- **装配机器人：**用实际装配模型完成4a冻结的空载保持／点位／代表任务路径跟踪和现有夹爪开闭／抓放检查；本体重力作为显式贡献组合并核对实际应用。首个代表路线MuJoCo CPU，不增设旧／新机器人动力学等价门。
- **交付／出口：**三后端共同effort主路线与最小外力代表例有真实证据；position compatibility单列。源约束不支持的任意独立双指力如实拒绝，不能代替应完成的成对力profile。

<a id="4c"></a>
## 4c：reset 更换 Controller 与 Solution 复核

- **输入／依赖：**4b、2c，Recorder和调用方动作规格边界。
- **工作：**同一Env在reset选择Controller／参数／input spec，按realized state重置；action spec／space／generation可查可记。清空嵌套各binding的q_ref、积分器、滤波、pending contribution、force latch和反馈历史。同批action布局共同。
- **检查：**至少两种input spec往返切换、同一物理命令协议、旧命令／载荷拒绝、obs固定、episode内切换拒绝；fixed-space wrapper明确拒绝不兼容变更。独立读回与PickCube成功复核，不沿用迁移前成功。
- **装配机器人：**PickCube和Nut各用同一任务Solution算法／策略参数，在原Panda与新装配配置下完成代表成功及独立记录读回；只改机器人配置，机器人参数差异留Robot／Controller配置。四个完整闭环不由短程精度检查替代，也不追加同一Env reset替换本体门。
- **交付／出口：**切换无旧episode控制残留，调用者可识别新action要求；保留迁移差异、真实成功和未支持项。

## Owner 与失败处理

公共控制／模型留在既有Core owner；task-specific gains／Solution和LIBERO benchmark配置留任务目录。Provider扩展须正式公开接口和冻结范围。夹爪路线无法表达请求则报告具体blocker，不把position重命名为effort，不重开F05严格源柔顺／传力研究。

阶段4做相关检查和代表成功；最终三seed九格在7b，非刚体载荷只保留typed接口。
