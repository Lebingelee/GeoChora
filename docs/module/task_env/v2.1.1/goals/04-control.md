# G04：统一施控和 Controller reset 切换

规划标识：`V211_G04_CONTROL`。3 个子阶段，依据[控制与反馈协议](../contracts/control-and-feedback.md)，复用 canonical contracts、ControlBinding、R3 和现有 session。2c 的成功参考是比较输入，迁移后不自动继承成功。

<a id="4a"></a>
## 4a：底层 effort 与公共反馈／模型能力

- **输入／依赖：**1c、2c、3c，尤其 D03/D04 的夹爪／模型服务决定。
- **工作：**扩展具名物理命令和映射，覆盖 torque N·m／force N、控制区间、范围、唯一 writer 和回执。明确公共 q／qdot／FK／Jacobian 等能力及 Controller 依赖，按需提供模型计算。
- **检查：**joint／DOF 轴向、量纲、原生 gear／传动／约束、身份／过期／重复 writer、缺反馈拒绝；submitted command 和 measured effort 分开。
- **交付／出口：**原生 `ctrl` 与 canonical effort 的映射可解释；arm／gripper 逐通道语义确定。模型库来源、软件依赖和 live provider 依赖分别记录。

<a id="4b"></a>
## 4b：复用 R3 参考与共享 effort 伺服

- **输入／依赖：**4a，三后端原生施控的公开能力。
- **工作：**组合 R3 q_ref 与已有／扩展的共享伺服；增加或复用关节参考输入及 direct effort 校验路径。原生 drive 与完整显式 PD 互斥，明确被动项、限幅、反馈采样和 hold／子步重算。
- **检查：**三后端真实执行共同命令语义；覆盖位置／末端参考和 direct effort 的代表输入、夹爪映射及饱和。数值依据按输入／执行频率重新冻结，不能把隐式 PD 当成显式 PD 等价。
- **交付／出口：**主路线支持多种 Controller 输入进入共同物理命令；保留的 native position 兼容路线单列，不计为全 effort 已完成。

<a id="4c"></a>
## 4c：reset 更换 Controller 与 Solution 复核

- **输入／依赖：**4b、2c，Recorder／调用方动作规格边界。
- **工作：**reset 选择 Controller 实现／参数／输入规格，按 realized state 清空历史；action spec／space／identity 更新可查询和记录。Fixed-space wrapper 明确拒绝不兼容改变；同批动作规格保持一致。
- **检查：**至少两种输入规格的 reset 切换、相同底层命令、旧 command 拒绝、obs 不变、episode 内切换拒绝；独立记录读回及 PickCube 成功复核。
- **交付／出口：**切换不会遗留 q_ref／积分器等状态，调用方知道新输入要求；保留迁移前后差异和有效成功，不声称旧 Agent 自动兼容。

## Owner 与失败处理

公共模型／控制功能留在既有 Core owner，task-specific gains／Solution 及 LIBERO benchmark 配置留在任务目录。若公共 feedback 需要 provider 扩展，通过正式公开接口完成。夹爪某路线不可实现时报告具体 blocker，不能把 position 通道改标签为 effort，也不自动重开 F05 严格源柔顺研究。

阶段 4 只做与修复相关的检查及代表成功；完整三 seed 验收在 7b，不因每次调 gain 重跑九格。
