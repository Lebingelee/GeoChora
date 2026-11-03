# 控制、effort 与反馈协议草案

状态：`DRAFT_FOR_DISCUSSION`；1c 冻结语义，4a 落实既有契约与实现。统一的是底层物理命令；不同 Controller 可以接受不同输入。

## 控制分层

```text
Controller 的输入 action
        ↓ 公共状态／运动学／动力学模型
参考生成与控制／执行器计算
        ↓ 具名 canonical 物理命令
RuntimeSession → adapter → 原生施控与物理推进
```

Core 调度控制和时间，adapter 执行公开物理接口。Controller 不 step／reset 原生场景，不读取 provider 私有状态；反馈必须声明需求。现有 R3 的 q_ref 生成可与共享 effort 伺服组合，direct effort 可由显式 passthrough Controller 校验后进入同一路线。

## Canonical 物理语义

- 转动 DOF 为 torque，单位 N·m；平动 DOF 为 force，单位 N。通道绑定语义 joint／DOF、顺序、轴向、正负、作用区间和来源。
- 区分广义驱动力、原生执行器输入和外部 body wrench。传动、gear、mimic／tendon、限幅及被动项必须在映射中说明，原生 `ctrl` 数组不天然等于 effort。
- 每个受控资源在一个作用区间有唯一命令 writer；多种输入 Controller 不得同时重复施控。External wrench 需要对象、坐标系、作用点和叠加规则。
- 接受、裁剪和实际写入回执与实测关节／接触力分开。不可测项说明缺失，不填零冒充测量。
- 为节点／粒子／分布力等保留类型化扩展，不要求全部物理对象都使用 joint torque。

现有 `CanonicalAction`／`CanonicalControlTarget` 含位置语义；`MixedActuatorPlanV1`／Command 有具名通道、单位与身份基础，但其准入仍受 source、provider、设备、标量和 state-only 限定。迁移必须显式兼容，不能改名后宣称全部统一。

## Controller 的公共依赖

每个 Controller 声明输入规格、输出通道、关节／实体需求、q／qdot／pose 等反馈、更新频率及可选 FK／Jacobian／质量矩阵／重力偏置等模型能力。缺少必需能力时拒绝该组合。

模型计算可以依赖显式声明且可替换的机器人模型库。LIBERO 当前在 GeoPhys 执行时也可使用 MuJoCo 参考动力学且不执行其物理 step；这不等于没有 MuJoCo 软件依赖。模型／惯性来源、约定、时刻与 live state 映射须可追溯，不读取当前 provider 的私有 solver 对象。

## 显式 effort 迁移

位置参考可通过公共 PD／前馈计算转为 effort：`tau = Kp*(q_ref-q) + Kd*(qd_ref-qd) + tau_ff`。具体增益、限幅、补偿和离散时间在工作包中冻结，不在协议里指定一套通用数值。

原生隐式 PD 与显式 effort 不保证相同响应。输出完整控制 effort 时，native drive 必须处于已声明且不会重复 PD 的状态；被动阻尼、摩擦、重力及约束处理分别记录。控制更新与 sample-hold／每物理子步重算要明确。

夹爪按真实 DOF、传动和力／开度控制需求逐通道处理。1c/4a 冻结首批映射与数值依据；保留原生位置兼容路线时必须单列，不能计作全 effort 主路线完成。若本版必达 effort 在某后端确实不可实现，应上报协议／范围问题，不能偷偷换成 position。已有 F05 原生约束适配例外不自动变为严格传力等价门。

## Reset 切换

Controller 实现、参数及输入规格允许在 reset 改变，episode 内保持确定。reset 清空积分器、滤波、轨迹和 q_ref 等历史；初值由本轮实际初始化状态产生。

动作维度、单位、含义或边界变化时更新并公布新 action spec／space 与身份。旧 Agent、Gymnasium wrapper 或 learner 未必兼容；固定空间消费者必须显式拒绝或重建匹配绑定。不能仅因底层 effort 相同就宣称它们可无缝继续。

Observation 仍服从[固定契约](lifecycle-and-data.md)。同一原生批次保持可批处理的动作规格；本版不承诺批内每个环境自由选择不同维度的 Controller。Recorder 按 episode 保存输入与底层命令身份，直接力输入同样适用。

## 验证边界

4b 至少覆盖 R3 参考组合、关节参考和 direct effort 的代表输入；检查传动、限幅、唯一 writer 与原生驱动互斥。4c 检查 reset 切换、反馈缺失拒绝和 Solution 复核。控制层统一不自动证明 R3 失败已修复，迁移前后证据不得互相替代。
