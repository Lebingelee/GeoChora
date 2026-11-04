# 阶段3前环境代码重构方案

日期：2026-11-04。状态：**维护要求已补入规划，尚未实施**。初次源码审计基线为 `develop@2fb903aa35a80a42aef34a10cfe4dbca63dd2d83`；新手入口和并行边界补充核对基线为 `develop@3dd27bd1ece06294efcd3f85f0d6c9673b6b4def`。本轮只更新文档，未修改生产代码、运行pytest或启动native；两个既有保护untracked保留。

维护者提出：整理tasks、隔离诊断、统一BaseTaskEnv与SelectedReferenceEnv，减少冗余诊断和SHA开销，并补齐新手安装、路径复用、启动脚本及基于example的二次开发指引。本次先完成单环境规范路线，Pendulum并行适配延期至G06。本项作为阶段3前的独立维护工作，不修改七阶段／22子阶段编号，不重开已接收的阶段2，也不表示阶段3已经启动。实施要求和验收以本仓库开发文档为准，GPT工作文档只作交接入口。

## 一、已经查明的现状

| 位置 | 当前事实 | 重构含义 |
| --- | --- | --- |
| `task_env/tasks/` | 28个Python文件，共13,630行；已有PickCube／Nut分包，但通用环境和候选输入也混在tasks中 | 按职责移动共享代码，保留任务定义／策略，不按目录或文件长短机械拆分 |
| `tasks/reference_env.py` | 4,123行，SelectedReferenceEnv有54个方法；`_reset`425行、`_position_record_metadata`460行、`__init__`264行 | 生命周期、候选路线、观测、记录和身份组装集中在同一类；需要减少其实际职责 |
| SelectedReferenceEnv构造 | 混入Nut专用gripper诊断入口、F04/F05/F06具名路线、leaf／mixed候选分支；默认8维Panda动作和若干Panda观测shape | 通用环境类不应硬编码任务／实验名称或Panda维数；任务和动作／观测组件应声明这些事实 |
| `environment/env.py` | 923行的BaseTaskEnv仍是独立实现，持有SingleTaskLifecycleAdapter和RuntimeBoundary | 不是一个旧别名；直接改名会损失原构造和生命周期能力 |
| 旧类生产消费者 | EmptyTaskEnv、PendulumEnv、TwoWheelBalanceEnv；另有测试子类 | 先迁移三个活动环境的单环境构造与调用者，再建立同对象alias；旧并行消费者的适配缺口单列，留待G06 |
| `vectorization/factory.py` | 用 `environment_type(config=..., build_runtime=False)`及scene／task扩展点构建并行环境 | 保留纯组装不启动runtime的边界及可复用owner；旧factory／注册不代表新统一路线已完成并行适配 |
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
4. 原SelectedReferenceEnv导入路径继续可用；保留factory配置优先级、单环境合法参数和`build_runtime=False`的纯组装边界。迁移单环境调用者、导出和测试在同一修改单元完成；不要求本次接通并行消费者。
5. 保留classic-control单环境的扭矩动作、reward／success／horizon、Gym reset seed语义及已有有效render/RGB行为。Pendulum本次仅按单环境验收；未适配的并行请求须明确拒绝或标明延期，不静默把N个环境降为1个。selected任务原本不支持的render／后端组合继续明确拒绝，不能借合并扩大能力。
6. 若遇到需要新增provider能力／阶段3–6协议才能实现的交集，列明具体缺口；除维护者已明确延期的并行适配外，保留既有有效行为，不把额外能力工程塞进本次重构。旧并行owner与历史证据保留，不以`num_env=1`、串行循环或现存注册宣称统一路线并行可用。G06原有目标不因此降低。

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

## 六、新手指引、路径配置与启动入口

新手交付是本次阶段3前维护的组成部分，不能只留在GPT工作文档，也不能把全部指引推迟到阶段7。详细清单见[指南交付要求](../guides/README.md)。文档和轻量脚本随实际重构结果一起交付；当前只登记要求，不把现有命令写成已验证的新quickstart。

| 交付位置 | 本次要求 |
| --- | --- |
| 根README与`task_env/README.md` | 给出新手短导航：准备依赖／引用已有安装→启动一个单环境→阅读并修改example；标明当前支持面与未完成项 |
| `task_env/doc/index.md`及新手／自定义任务指南 | 面向使用者说明安装、显式路径、启动和二次开发；更新仍以独立BaseTaskEnv为模板的内容，引用重构后的规范Env；资产指南链接现有owner |
| 本版`guides/` | 保存本版安装／复用、启动、开发步骤与限制的一份权威说明；其他入口链接它，不重复维护安装命令 |
| 既有script／examples owner | 提供轻量启动脚本（可复用现有CLI），转调公开factory／现有example；路径、解释器、provider／backend、可选renderer和资产manifest显式选择，不建第二套runtime |
| 本版`planning/`与恢复页 | 维护实施范围、尚缺交付及验收边界；完成后记录实际入口和验证结果，不靠聊天摘要判定完成 |

必须区分两条路线：**新克隆后安装**和**复用已安装仿真器／渲染器**。说明Python解释器、SDK／renderer根目录、资产／delivery manifest、当前Core与GeoPhys源码路径及兼容版本；已有安装可以在checkout外，不默认复制ignored工作树目录，不把维护者机器绝对路径写成默认。state-only不以安装renderer为前提，只安装所选路线需要的组件。

补充审计发现的具体缺口纳入实施清单：

- `task_env/script/agent/builtin_example_validation.py`将Isaac Python固定在当前checkout的`workspace/environments/isaacsim-6.2.0/bin/python`；应复用／补齐既有配置入口，让外部安装可显式引用，并在启动前指出缺失项。
- Flora已有`FLORA_ROOT`／`runtime_root`配置，启动和文档应复用它，而非另建路径发现器或核心诊断探针。
- Core声明`mujoco>=3.8.1,<3.9.0`，当前GeoPhys声明`mujoco>=3.15.0`，无交集。安装说明必须说明现有依赖冲突和已核实的准备方式；不能承诺两组依赖直接混装。修改公共依赖／pin仍归明确的依赖实施范围，不能借写指南任意升级。
- 仓库没有root packaging metadata，不写`pip install -e .`。SDK和资产缺失时给出配置方法，不自动下载、修改依赖、切换旧源码或静默换provider。

二次开发按“选一个已有闭环example→理解task声明／组装／reset／评价／Solution→修改自己的task→经公开Env验证”展开；优先引用`examples/tasks/declared_marker.py`等实际入口。排查说明指向专用diagnostics工作区，禁止把为一次排查增加Core探针作为开发教程。并行章节明确尚未适配，Pendulum新手路线默认单环境。

## 七、实施顺序与验证边界

建议在一个完整维护目标中按以下修改单元推进，每单元可有本地提交，不额外拆成多轮准备／诊断窗口：

1. **收回职责。** 将共享Env移到environment owner，归整观测／记录／候选输入和诊断入口，保留原入口及真正被消费的能力。
2. **迁移调用者。** 三个旧任务及其单环境factory／调用者迁入规范路线，完成BaseTaskEnv同对象alias，删除旧独立生命周期实现；并行适配缺口交G06。
3. **优化并验证。** 消除静态摘要重复读取／序列化，保留动态身份校验，完成受影响契约和代表性运行。
4. **交付新手路线。** 同步README、`task_env/doc`和本版指南，提供显式路径启动入口及example二次开发步骤；检查命令与重构后实现一致。

选择最小的缺陷敏感验证：

- import／registry／alias和三种旧任务构造；action／observation shape、dtype、默认值、seed/reset序列、reward、terminated／truncated、故障阶段和close次数前后对应。
- factory纯组装不启动runtime；检查已有单环境render接口和未适配并行请求的明确边界。本次不要求并行native、训练或吞吐验证，不代替阶段3–6新组合验收。
- 新手文档覆盖新安装／外部安装两条路线；启动入口的路径传递、缺失项提示和转调目标可检查。仅对已有支持路线安排最小代表启动，不把安装全部simulator／renderer或恢复并行设为本次门槛。
- 控制substeps／applied ack／部分推进故障、Recorder T+1与独立读回、兼容schema和历史replay拒绝检测，优先复用现有测试。
- 不可变输入语义hash一致；动态输入变化、错误回执、篡改和过期边界仍被拒绝。用诊断侧调用次数／文件读取统计证明减少重复计算，不先许诺吞吐百分比。
- 在实施包另行冻结预算后，保留必要的MuJoCo PickCube31和Nut19代表回归，以及迁移旧任务的短检查；不重复根因研究、不跑三后端九格，不追修seed32或GPU驱动。

当前只形成方案，尚未派发重构执行包；native和测试预算为0。实施前再冻结实际HEAD、允许路径、必要运行预算和回归基线，继续维护者手动转发／Sol主审流程。阶段3仍未开始。
