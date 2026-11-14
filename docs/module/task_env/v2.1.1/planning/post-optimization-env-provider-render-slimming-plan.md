# Env、physics adapter 与 renderer 后续精简计划

2026-11-14。状态：`C1_C2_IMPLEMENTED_C3_C5_PENDING`。C1 与 C2 的有界结果分别见[发布记录](../maintenance/reviews/20261114_post_optimization_c1_publication.md)和[共同 interval 记录](../maintenance/reviews/20261114_post_optimization_c2_shared_interval.md)；完整计划和最终复验仍未完成。源码盘点输入为 `d0902adc`；本轮 E14 收尾仅修改文档、Skill、示例 caller 和对应诊断，以下 Core 文件未改。原 E00～E16 的有界接收与[60项结案](../maintenance/reviews/20261114_e14_current_state_alignment_closeout.md)继续有效；本计划不新增 E17，不自动启动 Goal、native 窗口或 G06。

## 1. 要减少什么

按[原始总账](post-5c-code-project-optimization-diagnostic-ledger.md)的 GOV-01、ENV-01～05、RUN-01～04、REN-01～08、REC-01～03、TEST-01～04 和 CALL-01，优先减少重复的发布、结果组装和诊断信息收集；让读者能从正式入口追到一个生命周期 owner。源文件变短、把函数搬家、三种 provider 被迫继承同一个大基类，都不能单独证明成功。

现有统一已经发生在生产调用链：正式配置 → `make_env` → Task/Robot/source/Controller 构建 → Env → `EpisodeExecutionState` → 控制提交 → Runtime session → native adapter。后续应在这条链内精简，不能另造一套更短的 Env 或为四个任务分别接线。

本轮使用 CodeGraph 定位后读取当前磁盘源码及 AST。抽样的17个文件合计17,935行；没有发现去文档字符串后、至少8行的完整函数 AST 完全重复组。这个检测只覆盖整函数的精确重复，**不能排除语句块或职责重复**，也不能支持预先承诺删除一半代码。

| 当前范围 | 文件／行数 | 已确认的阅读负担与处理方向 |
| --- | --- | --- |
| Env及直接协作者 | `reference_env.py` 4,277；`lifecycle.py` 1,467；`reference_binding.py` 632；共6,376行 | reset准备592行，三条step准备分别322／301／184行；先合并发布及提交后样板，不重新实现共同生命周期 |
| session及物理端口 | `api.py` 880；`selected_materialization.py` 210；`mujoco.py` 2,498；`geophys.py` 1,600；`isaac_native_io.py` 3,513；三个`*_physical.py`共939；合计9,640行 | 共同身份／进度封装有合并候选；原生地址、drive、gear、tendon、buffer、时钟和关闭语义仍应由各adapter负责 |
| camera、呈现及观测采集 | camera `api.py` 343、`task_rgb.py` 116、`mujoco.py` 823、`geophys.py` 48；provider `single.py` 308；`observations/capture.py` 281；合计1,919行 | 小型且职责单一的模块原样保留；主要精简候选实际在Isaac session中的相机完成证明与详细诊断混合处 |

上述是选定文件的物理行数，包含注释和空行，不是整个 Core 或 adapter 家族总量。基线与函数位置见[AST盘点](../../../../../workspace/maintenance/v211_e14_alignment_and_core_slimming_plan_20261114_001/source-structure.json)。实施时须另列所有受影响接收文件，避免只报告被拆短文件的下降。

## 2. 不需要重构的部分

以下机制已成立，后续只有发现具体重复或失败才改：

- `EpisodeExecutionState.execute_reset/execute_interval`、共同dispatcher和`submit_control_command`；不加另一个LifecycleManager或Stepper。
- provider准入、source lease、资源归属、命令generation、单位、冲突、clock及独立native读回；不为了删行移除这些拒绝。
- Task/Robot声明、具体source lowerer和provider native映射的合法差异；不以“代码不同”推断构造合同未统一。
- renderer注册／实际factory、`task_rgb.py`、48行GeoPhys camera adapter及固定renderer选择；不为文件对称拆小模块。
- Isaac现有`IsaacSimAppOwnerV1`及唯一物理session；相机整理不能新增App、第二个推进者或另一套可变状态镜像。
- 普通Recorder、历史codec和严格oracle的分层，冻结H5和旧日志；新代码不能改写旧run身份或补造completion字段。

## 3. 大单元及依赖

顺序为 **C1 → C2 → C3 → C4 → C5**。C编号仅用于本独立计划，不改变原事件编号。每次完整实施一个大单元：核对输入 → 修改及必要修复 → 最短验证 → 汇总实际成效 → 提交。随后只翻总账对应条目一次；禁止每发现一个小格就重启全账审计、单独派包或启动一次SDK。

### C1：Env发布与reset结果收敛

对应 ENV-01／02／04／05、OBS-01、REC-02。优先级最高，先用这一单元确认实际净收益。

| 步骤 | 当前符号／事实 | 实施与接收owner | 退出依据 |
| --- | --- | --- | --- |
| C1.1 | `SelectedReferenceEnv`的`_published_position_*`在构造、reset退休、reset发布、physical step、position step重复写入；`physical_sequence.py`也写同组字段 | 列出全部真实读写caller、字段语义及publication时点。复用已有reset/step结果类型；在现有Env/lifecycle owner内形成一次发布及一次清空的实现 | 普通step和序列都实际调用该实现；不只在Env外再包一层；单独deferred RGB更新有明确说明 |
| C1.2 | `_prepare_reference_reset`中`observe`生成info，任务身份和成功信息有多处fallback | Task事实在现有TaskDefinition/binding/metadata阶段确定；Env消费确定结果并继续调用schema/info验证。清除已无正式caller需要的重复推断 | 四任务的Task身份、space/schema、reset info及记录元数据一致；不能把Task名或Panda布局移进Runtime |
| C1.3 | reset准备同时交接Runtime、Controller、source lease和发布结果 | 保留共同事务顺序，明确prepare／commit／失败回滚及旧Runtime保留；只合并重复结果装配，不整段搬走592行函数 | preflight拒绝不改变RNG；构造／reset失败后旧owner可清理；新旧source lease及重复close仍正确 |
| C1.4 | reset发布后可能追加RGB | 保留物理commit与图像完成边界；发布info继续按需要拷贝，不让新旧结果共享可变字典 | 渲染失败不重新推进，不返回旧generation图像；fault和已提交状态的可见性不改变 |

预期成效是同一组publication不再由多处各自维护。若必须引入一个私有值对象，应替代现有字段组，而非让两套状态长期并存。所有兼容访问器必须有真实caller；仅服务旧fixture的私有字段不自动成为兼容合同。

### C2：动作提交后的共同生命周期样板

对应 ENV-03、CTRL-02／04／05、RUN-03、REC-01。依赖C1已经给出唯一发布入口。

| 步骤 | 当前符号／事实 | 实施与接收owner | 退出依据 |
| --- | --- | --- | --- |
| C2.1 | `_prepare_physical_control`、`_prepare_position_profile`、`_prepare_reference_step`均进入共同interval，但各自装配状态、评价、观测、记录和发布 | 逐阶段比较实际副作用，列出共同后处理和合法typed差异；接收方仍是`EpisodeExecutionState`及现有Env hooks | 有明确前后调用表；Controller计算、native提交和结果提交分别只有既定owner |
| C2.2 | 三条路径重复提交后结果组装 | 合并相同的read／evaluate／observe／record／publish样板；不同控制计算与lowering继续传递明确类型，避免多层布尔参数选择一种大函数 | 三种路径消费同一个共同后处理实现，减少维护位置和重复字段；不改变reward、终止、horizon和info |
| C2.3 | reference路径的`submit_position_target`还组装writer/resource/scene command | 判断哪些属于既有`control_submission.py`／`control_lifecycle.py`合同；仅将可复用命令装配归入该owner | Command身份、writer、冲突及source generation检查保留；Position、effort、wrench不混为同一种控制语义 |
| C2.4 | `apply_control`与`advance`的原生推进责任并非在所有路径完全相同 | 按实际session合同保留唯一推进；保持Solution只调用一次act及副作用失败的fault规则 | fake计数证明无双提交／双推进；native interval采样和Nut的2ms任务策略保持；record append失败不伪装为未发生物理推进 |

不能仅把三段代码挪到三个新类后称已完成。退出应展示共同阶段的实际调用者，而不是仅比较函数名称。

### C3：provider重复值封装与原生读回减负

对应 RUN-01～04、SRC-04、TEST-03。只改有具体收益的重复；不要求三个adapter拥有相同内部布局。

| 步骤 | 当前符号／事实 | 实施与接收owner | 退出依据 |
| --- | --- | --- | --- |
| C3.1 | MuJoCo／GeoPhys的`runtime_progress_receipt`重复schema、materialization、episode、reset、control step、revision及source身份装配 | 先对齐字段和调用频率；若有净收益，在现有`common.py`／provenance owner复用纯值封装，native时间和扩展项由adapter显式提供 | GeoPhys仍用自己的snapshot时钟；MuJoCo仍保留preprocess/forward/monitor事实；缺失不伪填0，不使用统一四舍五入 |
| C3.2 | MuJoCo `_initialize_mixed_actuator`、`compiled_model_physics_fingerprint_v1`有较长enum、option、size和hash读回 | 静态映射及重复序列化可表驱动；保留原生模型读取、独立声明核对和缓存边界。没有重复就原样保留 | native值及拒绝行为相同；不将formal读回误删为实验探针，不把SDK查询放进纯source admission |
| C3.3 | 三个`*_physical.py`承担gear、地址、drive、buffer等原生差异；已有`_SessionValues`处理共同状态 | 删除确证重复的值操作；继续复用已有共同状态owner。无具体重复的native代码保持各自实现 | 状态单位、执行interval、控制写入及资源close合同不变；不增加第二组counter或capability猜测 |
| C3.4 | Isaac `_open_public_runtime`754行，包含App/stage/context/view/reset和准入阶段 | 默认保留其完整资源事务。只有能指出独立的纯声明／读回阶段及真实重复时才按现有owner整理；不为LOC拆成一串转发 | 不把754行当作可删除量；App及异常清理仍可从一个owner追踪；只搬家须按迁移单列并解释收益 |

本单元允许“核实后保留”的结论；这不是遗漏目标。若仅C3.1抽helper反而增加总量和阅读跳转，应放弃该抽取并记录理由，不引入新的公共provider基类凑统一。

### C4：renderer正式完成证明与详细诊断分离

对应 REN-02～07、RUN-04、TEST-01／03。主要候选是`isaac_native_io.py::_capture_observer_admitted`，不是重新搭建renderer registry。

| 步骤 | 当前符号／事实 | 实施与接收owner | 退出依据 |
| --- | --- | --- | --- |
| C4.1 | 412行采集中嵌有95行`log_task_scheduler_snapshot`，同时服务日志和正式完成判断 | 列出每个字段的生产消费者，先区分正式witness、原生控制状态和纯诊断。Fabric时间/stage id、dispatcher freshness及reference计数确被完成逻辑消费，必须保留 | 字段→消费者表闭合；不能整段删日志函数导致完成证明丢失 |
| C4.2 | `G05_TASK_RGB_RENDER_DIAG`／`G05_TASK_RGB_SYNC_CAPTURE`收集大量viewport、stage、settings、replicator状态 | 正式capture只生成必要、版本明确的完成事实；无生产消费者的详细实验输出退出常规路径。仍需要的扩展取证在版本diagnostics经公开readback／SDK接口完成 | 不新增公共debug分支或私有solver探针；冻结旧日志及其历史decoder仍可读；记录字段变更必须按实际reader兼容处理 |
| C4.3 | `render_once`必须协调pause、Fabric、sensor和Replicator，不能推进physics | 保留零`delta_time`、前后时间不变、settings恢复、frame新鲜性、reference与physics时间一致、异常清理 | 同一物理边界重复render的native推进增量为0；reset→step→reset期间frame、generation与相机身份正确 |
| C4.4 | Isaac camera实现在session中较大，App和physics又由同一session拥有 | 仅在职责能形成稳定窄边界时，交给现有camera adapter目录的Isaac私有实现；session持有并关闭资源。模块拆分是迁移，不算删除 | task sensor、observer、wrist mount各自资源不串用；无第二App、第二physics、两份相机状态或Task启动SDK；异常及重复close可追踪 |
| C4.5 | MuJoCo visual-only及GeoPhys raster已有专用owner | 仅按C4实际接口影响调整，保留FOV/near/far、颜色、尺寸和原生读回；不统一掉borrowed与独立visual资源差异 | MuJoCo renderer-only不调用`mj_step`；GeoPhys保存／恢复相机参数的行为不变；实际factory与声明能力一致 |

预期首先减少常规capture中的详细诊断装配和阅读负担。若C4.4只造成多个文件相互访问私有字段，保持现有文件，只完成C4.1～3的精简。

### C5：集中复验、度量和交付

对应 V01～V09、GOV-04、DOC-01／02；不新增workspace清理或refs处置。

1. 固定最终HEAD/dirty patch、四保护输入与pins。复查四个正式caller、全部被改的内部caller及现有接收owner；按大单元压缩记录，只保留最终结构、实测结果及仍有效限制。
2. 先跑受影响的纯／fake精确检查；可复用本轮242项guarded入口。新增检查只针对改动可能破坏的状态、资源、推进或公开caller，不为每格新增测试。
3. 若实施C1/C2，重点验证失败reset、RNG、source lease、发布generation、序列入口、唯一提交／推进、recording fault和Solution一次提案。最终共同控制链改变时，集中跑PickCube、Nut的MuJoCo完整Solution单seed及读回，覆盖两种实际任务语义；不在每个小步重复完整Solution。
4. C3只对实际修改的provider补最短native读回／interval路线，未改路线按调用链影响复用旧证据。C4若改Isaac采集，补reset采图、非零step、二次reset、重复render零推进、close；若改共同状态或camera合同，再补受影响的原生／cross路线。运行前另行冻结资源窗口、App启动数、显式子步、超时、输出及现行共享锁，不能沿用历史资源授权。
5. 当前reader读回受影响的新H5，分列runtime validity、task success、Solution completion、图像完成和close。不得把纯检查、fake pixels或短程成功写成完整Solution；不改旧H5以求自含completion。
6. 对每个大单元报告下面的成效表，最后独立复核实际diff和关键证据。没有真实收益的抽取回退／停止，已有接收范围及历史证据按原结论保留。

## 4. 成效表与停止条件

| 必须报告 | 口径与出口 |
| --- | --- |
| 文件 | 受影响家族及全项目tracked文件前后值；新增、删除、迁移分别列出；不把文件拆分称为文件量减少 |
| 代码 | 生产／示例／诊断／文档分别列`+/-/net`；迁移行单列。源文件变短但接收方增长必须计入同一范围 |
| 共同实现 | publication和提交后样板原有维护位置、最终位置、实际caller；不能用新增共同外观替代真实收敛 |
| 可读性 | 核心函数跨度、职责、理解一个reset/step/capture所需跳转及状态owner；AST分支数只作辅助，新增参数开关与私有字段穿透也要披露 |
| adapter | 必要native差异、formal witness及拒绝检查保留情况；哪些实验详细输出退出常规路径，哪些读回仍有生产消费者 |
| 功能与证据 | 精确输入、受影响路线、实际命令及结果、证据复用理由；失败和未测边界单列 |

不先设任意百分比指标。C1/C2应能证明重复维护位置减少；C3/C4只有出现真实封装／诊断净删或清楚的职责收益才实施抽取。单纯移动、通用参数开关增多、增加第二状态owner、删必要拒绝、为旧测试恢复产品分支，均不作为可接收成果。

## 5. 后续实施提示（尚未启动）

后续被明确要求实施时，可使用以下Goal文本；本文件本身不激活Goal：

> 按本计划在当前阶段分支依次完成C1～C5，首先核对真实HEAD和diff，不重开已接收E00～E16。每次完整推进一个大单元，包括实现、必要修复、按影响验证、度量、记录压缩和本地提交，再回看原总账对应项。优先消除重复发布与提交后样板；provider与renderer只合并已证明可复用的职责。复用现有生命周期、控制提交、source、camera、App及provenance owner；不得以迁移行数冒充删除，不引入第二状态或推进owner，不删正式身份／单位／clock／冲突／fault检查。native按当次执行计划与窗口开展，未变路线复用证据，不扩为全历史矩阵。诊断集中在版本diagnostics，Task不启动SDK，旧结果不改写。四保护输入、pins、冻结archive及接收例外继续保留，不清理更多目录或refs，不merge/push/tag/发布，不自动进入G06。
