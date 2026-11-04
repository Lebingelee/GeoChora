# 阶段3前环境代码重构方案

日期：2026-11-04。状态：**讨论稿，尚未实施**。本轮只做源码／调用关系审计，未修改生产代码、运行pytest或启动native。基线为 `develop@2fb903aa35a80a42aef34a10cfe4dbca63dd2d83`，两个既有保护untracked保留。

维护者提出：整理tasks、隔离诊断、统一BaseTaskEnv与SelectedReferenceEnv，并在保持功能的前提下减少冗余诊断和SHA开销。本项作为阶段3前的独立维护工作，不修改七阶段／22子阶段编号，不重开已接收的阶段2，也不表示阶段3已经启动。

## 一、已经查明的现状

| 位置 | 当前事实 | 重构含义 |
| --- | --- | --- |
| `task_env/tasks/` | 28个Python文件，共13,630行；已有PickCube／Nut分包，但通用环境和候选输入也混在tasks中 | 按职责移动共享代码，保留任务定义／策略，不按目录或文件长短机械拆分 |
| `tasks/reference_env.py` | 4,123行，SelectedReferenceEnv有54个方法；`_reset`425行、`_position_record_metadata`460行、`__init__`264行 | 生命周期、候选路线、观测、记录和身份组装集中在同一类；需要减少其实际职责 |
| SelectedReferenceEnv构造 | 混入Nut专用gripper诊断入口、F04/F05/F06具名路线、leaf／mixed候选分支；默认8维Panda动作和若干Panda观测shape | 通用环境类不应硬编码任务／实验名称或Panda维数；任务和动作／观测组件应声明这些事实 |
| `environment/env.py` | 923行的BaseTaskEnv仍是独立实现，持有SingleTaskLifecycleAdapter和RuntimeBoundary | 不是一个旧别名；直接改名会损失原构造和生命周期能力 |
| 旧类生产消费者 | EmptyTaskEnv、PendulumEnv、TwoWheelBalanceEnv；另有测试子类 | 三个活动环境及其factory／并行消费者全部迁移后，才能删除旧实现并建立同对象alias |
| `vectorization/factory.py` | 用 `environment_type(config=..., build_runtime=False)`及scene／task扩展点构建并行环境 | 迁移必须保留这种纯组装用途，不可无意启动单环境runtime或破坏已有classic-control并行能力 |
| `trajectory/replay.py` | 在两处从 `task_env.diagnostics.historical_tasks` 导入构造函数 | 已有Core功能反向依赖diagnostics；历史兼容和诊断入口需要分开归属 |
| `_execution_boundary()` | 每次调用都hash相同scene XML，并读取TaskArtifact.identity_hash | 把不变输入摘要准备一次；每个真实边界仍生成动态身份 |
| `_owners()` | execution recorder逐transition调用；每次读取环境类源码文件并hash | 静态源码provenance不应每步读磁盘，记录owner负责引用已准备的摘要 |
| `TaskArtifact.identity_hash` | 每次访问都to_mapping、JSON序列化和SHA；定义为frozen contract | 可审查深层不可变性并复用摘要，不能把动态／可变数据也一概缓存 |

上述为静态调用和实现事实，尚未测量整体加速比。CodeGraph存在但若干文件已drift；按其提示检查了当前源码，未重建索引。

## 二、目标结构与职责

唯一环境实现以SelectedReferenceEnv为准，规范owner放在 `task_env/environment/`。原 `tasks/reference_env.py` 只保留必要的兼容导出，不继续拥有生命周期。优先复用现有owner，不新增平行Runtime、Recorder、Manager或另一套Task协议。

| Owner | 应保留的职责 | 从环境类移出的内容 |
| --- | --- | --- |
| `tasks/<task>/` | task声明、物理／reset语义、评价、Solution；task自身动作／观测声明 | 通用Env、记录序列化、全局实验分支 |
| `environment/` | 规范Env门面、配置和组件装配；复用现有lifecycle owner管理episode／fault／close | 特定任务探针、历史实验名称、长篇记录metadata构造 |
| `runtime/`及sessions | 现有能力准入、control application、唯一物理推进和provider资源 | Env自行分支推进、为诊断复制的runtime路径 |
| `observations/`与task观测组件 | observation schema／shape／构造及既有传感器接入 | 通用Env硬编码Panda的8／9维、finger／site细节 |
| `recorders/`与既有trajectory owner | 记录格式、metadata投影、静态provenance引用、同run完整性 | Env内数百行按F/R版本拼接metadata的逻辑 |
| `diagnostics/` | 明确opt-in的实验入口、方法包装、对照分析、说明文档 | 只为某轮排查新增的构造参数／任务名字判断／特殊探针 |

`position_candidate`不能整包当作诊断删除：当前RuntimeSession、CLI和benchmark仍消费其中的输入与构建逻辑。应按实际消费者分成共享表示／正式运行能力／实验入口，分别归入已有artifacts、runtime及diagnostics owner，并保留必要旧导出。不能把runtime对tasks的依赖简单替换成对diagnostics的依赖。

## 三、统一环境类的完成标准

当前两条路线的差异不止类名：BaseTaskEnv经bootstrap构建RuntimeBoundary，SelectedReferenceEnv经materialize构建RuntimeSession；两者的action／observation、seed、done、故障和close语义也不能假定相同。

实施应复用既有TaskDefinition、配置归一化、编译回执和lifecycle扩展点，在现有runtime owner中适配已经具备的能力，保持唯一推进authority。允许必要的接口转接，不保留两份episode状态机，不新写物理积分或私有SDK状态通道。

最终必须同时成立：

1. Empty、Pendulum、TwoWheelBalance均通过SelectedReferenceEnv的规范构造和生命周期；非Panda任务无需伪造Panda控制器、TCP或8维动作。
2. PickCube、NutAssembly、声明式PandaBox、Position候选和LIBERO保留现有有效行为及明确拒绝边界。
3. 原BaseTaskEnv相关导出均直接引用规范SelectedReferenceEnv类对象，包括 `task_env.BaseTaskEnv`、`task_env.tasks.BaseTaskEnv`、`tasks.base`及原environment出口；不是再套一层继承壳或藏起原实现。
4. 原SelectedReferenceEnv导入路径继续可用；factory配置优先级、旧合法参数、`build_runtime=False`和并行组装扩展点不丢失。迁移调用者、导出和测试在同一修改单元完成。
5. 保留classic-control的扭矩动作、reward／success／horizon、Gym reset seed语义、已有render/RGB和并行入口。selected任务原本不支持的render／后端组合继续明确拒绝；不能借合并扩大能力，也不能通过统一到state-only删除旧功能。
6. 若遇到需要新增provider能力／阶段3–6协议才能实现的交集，列明具体缺口，保留旧有效行为；不把额外能力工程塞进本次重构。

## 四、诊断隔离规则

维护性诊断程序和说明集中在 `task_env/diagnostics/<topic>/`；具体run、临时脚本、原始数据和分析输出留在ignored workspace的独立目录。每个实验说明记录问题、参考闭环、控制变量、调用模块／方法、命令、观测及结论边界。

诊断应引用被检查模块／方法，通过正常输入输出、公开state、现有Recorder／reader或局部诊断包装采集数据。Core不能为一次实验新增专用参数／case分支／probe；不读取provider私有solver状态。确有共享可观测性缺口时，独立说明公共能力需求，不以临时探针冒充正式接口。

并非所有名为diagnostics的字段都能删除。正式control feedback、applied ack、fault、时钟／状态过期检查及既有记录schema中的字段有运行语义，按原合同保留。一次性统计、绘图、内部量采样和实验metadata迁出默认执行路径。

`trajectory/replay.py`的历史构造功能应迁到明确兼容owner或隔离的历史入口，再解除Core→diagnostics依赖。保留既有拒绝／退役语义，不承诺恢复已删除任务，不产生第二个活动环境factory。

## 五、SHA优化规则

| 类别 | 处理方式 | 必须保留的保证 |
| --- | --- | --- |
| 不变的TaskArtifact／Scene／配置摘要 | 在已证明不可变的对象或一次构造快照上计算并复用 | canonical编码、字段排序、数值表示和原语义hash不变 |
| 场景XML／资产closure／源码provenance | 在构造／准入／记录开始等明确边界准备一次；输入替换后失效 | 不永久按路径缓存，不漏掉新内容、配置或reset重建 |
| 当前control boundary／target／applied ack | 继续按真实输入和边界校验；可共享同一边界内的计算结果 | 不跨step、episode或state revision复用，不漏检stale／tamper／错来源 |
| 纯实验统计与展示用摘要 | 交diagnostics按需处理 | 不进入默认step／reset开销，不破坏既有正式记录格式 |

重构会改变源码文件及provenance SHA，这是正确的版本变化；建立旧／新来源映射，不伪造旧source identity。任务语义／物理spec未变时应保留相应语义hash。阶段2冻结commit、H5、manifest和历史结论保持原件，不将旧run重标为新实现的成功证据。

## 六、实施顺序与验证边界

建议在一个完整重构目标中按三个有依赖的修改单元推进，每单元可有本地提交，不额外拆成多轮准备／诊断窗口：

1. **收回职责。** 将共享Env移到environment owner，归整观测／记录／候选输入和诊断入口，保留原入口及真正被消费的能力。
2. **迁移调用者。** 三个旧任务及其factory／并行消费者迁入规范路线，完成BaseTaskEnv同对象alias，删除旧独立生命周期实现。
3. **优化并验证。** 消除静态摘要重复读取／序列化，保留动态身份校验，完成受影响契约和代表性运行。

选择最小的缺陷敏感验证：

- import／registry／alias和三种旧任务构造；action／observation shape、dtype、默认值、seed/reset序列、reward、terminated／truncated、故障阶段和close次数前后对应。
- factory纯组装不启动runtime；已有classic-control并行组装和render接口保留。重构不代替尚未执行的阶段3–6新组合验收。
- 控制substeps／applied ack／部分推进故障、Recorder T+1与独立读回、兼容schema和历史replay拒绝检测，优先复用现有测试。
- 不可变输入语义hash一致；动态输入变化、错误回执、篡改和过期边界仍被拒绝。用诊断侧调用次数／文件读取统计证明减少重复计算，不先许诺吞吐百分比。
- 在实施包另行冻结预算后，保留必要的MuJoCo PickCube31和Nut19代表回归，以及迁移旧任务的短检查；不重复根因研究、不跑三后端九格，不追修seed32或GPU驱动。

当前只形成方案，尚未派发重构执行包；native和测试预算为0。实施前再冻结实际HEAD、允许路径、必要运行预算和回归基线，继续维护者手动转发／Sol主审流程。阶段3仍未开始。
