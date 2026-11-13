# E05～E10 实施 Goal

规划日期：2026-11-12；状态更新：2026-11-13，`INDEPENDENT_REVIEWED_BOUNDED_PENDING_MAINTAINER`。本 Goal 已实施并完成[独立主审](../maintenance/reviews/20261113_e05_e10_independent_review_d9dc02c6.md)，实施性余项已结束，待维护者接收；以下保留原执行提示，不应再次启动同一 Goal。本次规划输入 `67cb643f`，生产 `912416e6`；执行者开始时冻结实际HEAD和dirty，不将规划身份冒充执行输入。

## 可直接交付的提示

请依据[优化总台账](post-5c-code-project-optimization-diagnostic-ledger.md)及[E05～E10专用账本](post-5c-e05-e10-remaining-ledger.md)，实施 **E05资产与source组合归位、E06 physics adapter、E07状态与相机、E08 renderer adapter、E09 Task精简、E10 Recorder与replay**。维护者已经统一接收E00～E04；保留其共同配置、TaskBuildRequest、SourceBoundTaskBuilder、具名阶段context、公共生命周期和共同submit成果，不从历史描述重开这些事件。

### 1. 范围与实施原则

正式任务限定最新版PickCube、NutAssembly、Pendulum、双轮车；主体包含一体Panda、装配Panda和两个简单主体。四任务继续通过正式 `make_env`、共同配置／构建阶段与唯一Runtime运行。允许资产、结构、能力、provider与源表示不同；不要求简单主体伪造gripper/ee，也不要求MJCF/USD或Position/effort/wrench使用同一native算法。

Task/TaskDefinition负责声明、物体映射、默认选择、reset/奖励/评价/Solution语义；Robot负责主体、Frame/Joint/传动及recipe；Controller负责控制语义和绑定；source/provider adapter负责原生解析、准入、映射与资源；renderer adapter消费公开状态和visual source并报告采集／输出／资源能力；Env负责编排；Recorder拥有记录metadata与版本格式。对旧实现做必要的修复、扩展与组合，不再新增平行Runtime、Env、Recorder、Manager或factory。

Empty/Empty+Panda只因compiler中现有caller受影响而迁移和核对，不增完整任务矩阵。旧Position candidate、两个PickCube physical UID及其独立构造已经退休，不恢复别名、旧输入或fixture专用产品分支。保留仍有正式caller的资产和能力，先接收再删旧实现；不将千行specialization整体换目录。

### 2. 按完整大单元推进

检查点S01～S40的当前定位、顺序动作、接收方和退出证据以专用账本为准，不另造第二套逐项清单。

| 顺序 | 实施单元 | 必须交付的实际变化 |
| --- | --- | --- |
| U1／S01～S06 | 资产／Task intent／source lowering | compiler退出Empty/Panda配方；source组合实际消费Task+Robot声明；实验顺序配方、正式资产变体、通用attachment分层；source表示/lease/最终映射保全 |
| U2／S07～S12 | provider准入／Runtime／worker | 公共Runtime API退出Task资产policy和实验调度；正式精确准入回provider owner；GeoPhys正式bootstrap及worker SDK启动策略归位；唯一物理推进与关闭合同保全 |
| U3／S13～S18 | 状态／观测／相机 | 公共组合不预设Panda；显式Robot/Task/sensor声明对齐space/schema/实际数组；renderer状态需求退出Env；保留已有CameraSpec无hash延迟绑定及高级对象检查 |
| U4／S19～S25 | renderer能力／采集／展示 | 能力来源与真实factory对齐；Env退出RTX/颜色/配对知识；Isaac task与observer身份和fault按资源边界处理；展示/采集/输入职责明确，borrowed与independent消费同一Runtime物理边界 |
| U5／S26～S30 | Task目录／Nut公共支持 | 接收方已工作后删除Task残余native/source接线；按真实公共合同抽取Nut反馈/interval支持，保留任务策略和严格guard；四任务结构、调用层数和迁移量可对比 |
| U6／S31～S36 | Recorder／旧格式／replay | 普通schema完整性、兼容codec、精确实验Judge分层；metadata归原Recorder owner；静态provenance按实际lifetime复用；正常短记录独立读回，旧严格oracle与replay身份不放宽 |
| U7／S37～S40 | 定向复验／成效／事件结案 | 用最终diff映射受影响证据，补尚未覆盖的最短生产路线；压缩记录，逐一给六事件的实施结果和待接收边界 |

一次推进完整U单元：实现、直接caller迁移、必要修复、定向验证、成效记录和本地提交同包完成。S格不是单独派包或native启动次数。单元内部依照专用账本连续推进；**只在大单元结束时回看总台账对应部分**，不反复扫描60项然后只补一个局部函数。

发现同单元正确性问题就修复、补受影响检查；发现不影响本单元的范围外问题集中写账本第11节。既有机制符合目标可以保全并给依据，不为了让每格有diff制造抽象。只有真实外部能力、权限或资源边界阻止继续时才暂停相应依赖，具体说明缺口；一般测试失败不切出一轮新规划。

### 3. 必须保全的合同

- 使用既有SourceCompositionIntent/Request/Receipt、CompiledReferenceTaskV1、RuntimeSource/UsdRuntimeSource及snapshot lease。意图可先声明，最终source/writer绑定可以依赖实际Controller；不制造第二物理owner，也不为相机把USD当成MJCF。
- 继续严格检查source/Artifact、closure、版本化资产准入、Controller generation、单位/传动、资源冲突、state boundary/clock、stale与fault。把检查放正确owner，不能整批删除hash或放宽F06/R03历史准入。
- 一个场景interval只有一个提交和advance owner；requested/applied不当作实测力；外部step、Controller tick、physics substep分别报告；启动隐式advance unknown不伪造零。
- Controller、Task、renderer可有不同typed view，但必须属于同一已发布边界和明确lifetime；保全renderer publication不覆盖控制publication的修复。renderer固定至close，不实现运行中切换。
- task camera、observer、窗口、独立visual模型、App lease各有身份与资源owner；borrowed consumer不关闭physics；关闭失败不伪报released。Isaac共享底层采集工具合理，headless task sampling不能依赖伪造可见observer。
- 普通相机已经支持CameraSpec延迟绑定，无需重建；普通structured H5 reader已经按T/T+1校验，无需另造格式。迁出历史oracle时保留显式旧reader/codec和严格Judge，Core不依赖diagnostics。
- 正常新运行使用当前能力，历史读取按记录版本；same-source reexecution不替换SHA，未支持格式／跨源码重执行明确拒绝；只读inspect不启动SDK，不擅自实现D0。
- Nut的阶段、阈值、grasped_nut、2ms×5要求和完成策略属于任务；通用时间窗/身份/stream校验按公共责任复用既有feedback/runtime/completion。没有真实复用或公共职责的任务逻辑可以保持完整，不强造通用guard库。

### 4. 验证与执行窗口

实施开始记录实际HEAD、dirty归属、四保护输入字节、两个pins、唯一输出目录及计划；复用当前阶段分支、单writer。按专用账本第12节冻结**精确node/命令**、fixture纯度、interpreter/provider/source/renderer、seed/horizon/dt、显式步数与capture上界、内存/墙时/磁盘和锁/cleanup。已有probe优先复用；只按影响增补检查，不反复重测已覆盖同一路径。

纯检查、fake、真实离线source/USD构造、native短程、真实RGB和完整Solution分别记录。纯配置查询不加载SDK；OpenUSD离线资产构造不能冒充纯检查，也不能因误禁pxr把它当native故障。不得运行整个历史模块来凑通过数，必要行为迁入 `task_env/diagnostics/tasks/v2.1.1/`，退休fixture不反向要求产品兼容。

对受影响路线完成 `make_env → reset → 非零interval → state/clock → 二次reset → 重复close`；覆盖四主体的共同合同，以及本轮实际改动provider/renderer的代表交集。三首批原生和GeoPhys physics×MuJoCo renderer-only逐项给复用或补测依据，不增全任务×provider×renderer矩阵。

RGB检查reset首帧、新状态、再reset旧帧失效、重复render物理推进增量0、task/observer独立及owned帧lifetime；受影响光学参数给真实readback，不重新设像素评分门。S21若改变Isaac真实采集链，必须有受影响最终输入的有界采集结果或保留OPEN；不能拿旧冻结证据声称新行为已测。资源未就绪时写具体阻塞，不用fake填native PASS。

Recorder用同次正常短记录独立读回状态、动作、clock、T/T+1、图像和episode结果；包含不等于64的短horizon与非Panda声明，并保全一个仍需支持的旧格式和关键篡改拒绝。普通记录验证不用完整任务成功代替，历史H5读取不用重模拟。静态provenance先测实际read/hash调用再决定是否优化；无热点可原样保全。

**本Goal不扩展E13。** 两任务按各自正式支持provider单seed完整Solution、至少MuJoCo任务成功及同次完整记录V09仍归E13。若某次受授权运行恰已覆盖后续同一claim，按身份复用；不能把短程改称完整成功。COM原严格FAIL、R05c NOT_REQUALIFIED及历史执行偏差保留，不重开5c。

### 5. 每单元成效与记录压缩

每个U单元结束提供：

1. 输入/输出HEAD、diff、相关提交和证据；S格最终owner及PASS/OPEN，原样保留有caller依据。
2. 同口径文件数前后、增删和迁移路径及项目净变化；生产代码+/−/净量、迁移量，诊断/测试/文档分桶。相对本轮实际输入与相对stage5基线分列，不冒领E00～E04删行。
3. 哪些重复构造、转换、特殊分流、私有跨owner调用被消除；四正式caller的实际调用图和各模块最终职责。保留的合法adapter差异说明理由。
4. provider/renderer如何消费Runtime source、state、clock、submit与资源合同；支持边界、未触及部分及身份变化说明。
5. 实际验证、独立读回、失败/修复、旧证据复用依据和限制；runtime validity、task success、Solution completion、close各自结果。

执行过程日志和原始失败保留ignored输出；当前执行记录按模块及时压缩，只保留最终效果/边界和证据入口。专用账本第13节是唯一进度更新区，详细40行结果表可链接一份摘要，不新增40份报告。总台账每个U结束只核对相关项；跨事件条目全部责任与证据到齐才最终关闭。

### 6. 最终交付与边界

分别报告E05～E10六事件的完成状态、实际owner、可见效果、剩余项与证据；实施者自评、独立主审、维护者最终接收分列。同步直接涉及的API/Skill/当前状态/导航，保持历史证据时点。不得用文件数、净删行、测试数量或一个共同类名代替架构接收。

E11全诊断治理、E12全caller迁移只处理本轮直接依赖；E14整体文档/优化接收、E15输出归并、E16分支/worktree清理以及G06/G07不提前宣布完成。不删除旧证据或保护输入，不改子模块pin、不merge/push/tag/发布、不自动创建或消息其他chat。完成本轮后交付可review结果，后续阶段由维护者决定。
