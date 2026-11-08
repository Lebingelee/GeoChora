# G05 5c 人工诊断：控制主体与三次改动审计

2026-11-08。维护者明确：Pendulum 和双轮车均应以受控主体接入统一构建／Controller 流程，Controller 可以是保持原动作语义的直接 torque 映射；Panda 专用假设应限制在对应 Robot/Controller 内，不应支配环境公共构建和渲染。人工诊断应复盘 5c 三次代码变动及对已有路线的影响，不能只定位 Isaac 一个报错。此文件记录只读诊断、已确认缺陷和拟议设计，不表示已实现或授权 native 运行。

## 范围转译更正

attempt002 工作包 `V211_G05_5c_attempt002/goal-prompt.md` 第 19–43 行将第一层渲染接线设为必做，第二层写成必须分析、在安全范围内可实施；其中把 Agent/Controller 迁移写成优先评估而非必须交付。003 工作包又明确不把完整迁移设为本包门。实施者因而评估并暂缓，而没有实现两个主体的 Controller 流程。按冻结工作包文字，不能把未实施单独说成执行者违令；但 Sol 当时没有将维护者期望转成明确的实现和验收目标，后续又将其简化为“延期”，是 Sol 的范围转译遗漏。维护者本次已明确要求该实际流程：这是当前 5c 未完成事项，不再仅列为远期可选设计。

当前 `PendulumTorqueActionAdapter` 和 `TwoWheelTorqueActionAdapter` 分别已执行动作校验与执行器命令填充，却由各自 TaskDefinition 创建，组件 `SelectedReferenceEnv._convert_action` 优先走 `_action_adapter`，并非通过统一受控主体／Controller owner。`RobotRuntime` 类型及 component Env 的分支还包含 gripper、base/ee 和 `env.robot` 假设。仅把现有 adapter 改名或注册成 agent 不能证明已迁移；重复创建一个 Controller 路径并再次施力也不行。

## 实际 Position 分支含义

`position_profile` 是历史 selected 环境的执行分支，不是“环境固定／可移动”分类，也不是一般的动力学位置类型。`bind_selected_controller()` 根据 `PandaPositionServoProfileV1` 或特定 leaf plan 设置它；该 Panda profile 明确要求七臂关节和两个手指关节。selected Env 又用这个标志分流 Session 准备、typed state、控制和部分 observation；即使 Isaac PickCube 的 physical/direct-effort 路线，也先走 `from_position_candidate` 且 physical-control admission 要求这个标志。因此这里的“非 Position”仅指**没有进入该既有 selected 分支**，并不是没有 position 状态、不是非机器人，也不是主体自由移动的意思；Pendulum/双轮车本身走组件式生命周期，不能等同于 003 受控测试构造的“非 Position selected”任务。

“根部运动约束”和“控制方式”需要正交表达：固定根可以有可转动的铰链和 position 或 torque Controller；有自由根或受约束根的主体也可以使用这些控制器。静态／运动学／动态属性、根和关节的固定／自由／约束拓扑、接触约束、具名控制通道与单位、控制输入/输出模式分别由可表达的 scene、execution 与 controller 声明负责，不将一个固定/自由枚举当作所有仿真能力的充分描述。保留特定 Position Controller 及其真实能力校验是合理的；让公共 renderer/state admission 依赖 Panda position 不是合理的通用抽象。不能直接删除 `position_profile` 而破坏已接受的 controller/physics 路线；应分离职责并按影响逐步迁移。

## 逐次代码变化和实际影响

| 阶段 | 实际变化 | 正确增量与问题 |
|---|---|---|
| 5c 前 | selected Env 已按 Position、mixed 和 legacy scalar 控制分支装配；组件 Env 另有 agent robot 或 task action adapter 分支 | `position_profile` 与 Panda 类型耦合不是 5c 才产生；通用环境需要兼容既有能力，不能全盘归咎新 RGB 代码 |
| 001 | `make_env` 和 `_configure_task_rgb` 新增 `position_profile` 准入；共享的 `observation()` 读取该分支的 typed_state。`_new_task_rgb_consumer` 对 GeoPhys/Isaac 借用 session，对 MuJoCo 才构造独立 `DynamicCameraRenderSourceV2` | PickCube 四路线包括 Isaac 真机通过；入口人为排除其他 selected 控制方式，renderer 依赖 Position 是需求不符。任务 RGB 与固定选择、receipt 等增量仍有价值 |
| 002 | 放开公共入口，给 component lifecycle 加 observation transform 和 RGB；GeoPhys 灯光按实际 source 处理 | component 的通用接缝方向可取；但放开入口未补 non-Position selected typed_state，组件相机未将声明光学值传给 renderer，造成两个真实缺口；Agent/Controller 未实施 |
| 003 | 增加 `_prepare_task_rgb_state_binding` 与非 Position reset/step publication，MuJoCo renderer 用具名绑定；组件实际 bind/update/read task camera 并验证光学 | non-Position 受控链、Pendulum 真机相机是进展；但把 `DynamicCameraRenderSourceV2.from_runtime_source` 放进所有 RGB selected reset，强加仅 `RuntimeSource`／MJCF 适配给所有 renderer。Isaac 使用 `UsdRuntimeSourceV1`，故在 materialization 边界拒绝；GeoPhys 借用 session 也被迫满足本不属于该 renderer 的约束。003 测试未覆盖 USD 受影响分支，这是可确认的覆盖缺口，不把其余路线一概判失败 |

`DynamicCameraRenderSourceV2` 还约束完整具名 joint/frame、Scene-v3 与对应 source；这些约束可用于其已准入的独立 renderer-only 路线，但不可未经能力分析提升为所有 native renderer 的普遍准入。当前 5b 接收、001 真机 Isaac 历史、003 三条 CPU/跨组合及 Pendulum 真机成果均保留，并按后续变动影响判断复用。

## 统一建构与控制目标：方案约束，不预设唯一类结构

1. **实体与 source 单一所有权：**任务声明场景；受控主体可拥有 source，也可绑定已编译的具名实体和 actuator，二者各自有明确身份和唯一装配方式，不把相同 pendulum/车体加入两次；被动对象零个或多个。现有任务 assets/MJCF 不随意改写。
2. **Controller 真正参与生产链：**公共构建解析受控主体及命名控制通道，选择匹配 Controller；reset 时初始化，step 时从 action 与必要状态生成一次语义明确的控制命令，沿现有唯一 Runtime/provider 提交；不创建重复物理进程或重复施力。控制模块可复用或迁移现有 adapter 的功能，但必须能在可审查的生产入口看到主体→Controller→命令→provider 的调用链，而不是仅多一个标签。
3. **保留现有动作含义：**Pendulum 单关节直接 torque，原范围 ±2 N·m；双轮车左右轮 torque 按原顺序、每路 ±1.5 N·m，现有 action tree/schema、有限值和越界拒绝、25×0.002 s 节奏、reward/termination、单位/轴和传动映射保持。恒等/直通 controller 为优先可验证基线；若未来使用平滑，必须显式选择、说明状态和 reset，不能默认改变物理/动作语义。Panda 自身 profile 的 7+2、末端和夹爪要求留在其实现及确有需要的 adapter。
4. **感知与渲染独立控制类型：**统一 state boundary/clock 和 consumer requirements，基于 source 表示与 renderer capability 选择适当 provenance/binding；USD native shared-scene 不因非 MJCF 被强迫构建 MuJoCo renderer-only source。不能为某任务名/关节数/控制类型开通专用公共渲染旁路，不能取消真实 source identity、安全准入或旧状态拒绝。
5. **验证与迁移：**先做公开构建及两个控制主体、controller identity、单次 command、旧新 action 等价、reset、异常、缺失/冲突通道拒绝及 Panda 回归的受控检查；按可用 source/授权实测 Pendulum、双轮车各自 public reset/固定 action step 和命令/状态，并结合已支持相机至少验证代表同步 RGB。对 Isaac、MuJoCo、GeoPhys、跨组合按代码影响选最小真实复验；保留历史证据，不要求全矩阵和额外图像分数。要如实记录不支持的 source/硬件/控制交集，不能仅用 fake 或属性接线宣布实现完成。

## 状态与下一步

5c 有两个并行维度的未完成事项：Isaac 当前 RGB 回归；维护者明确要求的 Pendulum/双轮车受控主体 + Controller 生产流程。此前观察到的其他边界（source closure、灯光、相机挂载、颜色等）按需影响分析，不自动扩大为所有能力必须实现。Sol 继续静态分析并准备可审核诊断方案；实施、source 解析、native/GPU/GUI 和资源须由维护者另定窗口授权，实施者由维护者指定并手动转发。无自动第四普通 attempt、无阶段 6 或发布。
