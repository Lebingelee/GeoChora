# G07：任务复用、最终验收与文档收口

规划标识：`V211_G07_INTEGRATION`。3 个子阶段；只收口已冻结范围，不恢复旧 P99／F05 研究门。最终能力仍是精确交集的有界工程结果，不自动授予 Qualification。

<a id="g07-code-constraints"></a>
## G07收尾期间的代码约束

2026-11-16维护者revision003：G07以真实案例驱动的集成收尾和代码复审为主，尽量避免新增功能；保留原7a必要接线和验收。执行中持续对照[post-5c优化总账](../planning/post-5c-code-project-optimization-diagnostic-ledger.md)及其E00～E16/G06后续结案。总账的旧未勾选文字不重新变成开发任务，不重开已接收阶段，也不以功能通过替代owner与阅读成本的审查。

- 沿原/装配Panda的PickCube、Nut和受影响caller核对实际构造、控制、状态、模型、记录与关闭。已有owner组合满足的直接复用；只修复由真实调用或运行证实、原门必需的缺口。owner定位表不要求每项产生diff。
- 将“案例、实际问题/消费者、原owner、复用或最小修改、总账条目、验证”记在同一份包内结案表。执行中发现有产品意义的边界结论时，及时更新本节及该表；不另建审计schema、validator、能力注册或证据平台。
- Task保留任务语义与薄binding；Robot/source拥有recipe、TCP/具名通道/传动；Controller拥有选择、状态与计算；session/provider/render/Recorder保留各自唯一owner。复用现有source composition、shared worker装配/物理端口/模型代理，不新增第二Env/Runtime/factory/调度器、通用RPC、profile分派或仅为缩短文件的Manager/mixin/helper层。
- 装配本体模型/补偿仅作原用例中这一套recipe与代表路线所需适配，不扩大为任意Robot/装配树/provider动力学。原R3已正确包含的贡献用证据证明，不再重复施加。任务成功与严格完成语义保持；维护者 2026-11-16 针对 Nut 夹爪触桌明确授权调整 Solution 的释放高度，须保留同运行完成、读回和 close 的验证，不将该例外扩大为其他策略修改。
- 装配替换的R3模型须来自同一source组合及实际装配后的具名本体，并与session核对来源；位置驱动重力补偿须核对实际施加与ACK。任务原有驱动参数须随具名执行器保留，不能仅开放profile就声称装配行为等同。
- 既有装配`r1_split`的MuJoCo CPU进程内控制可用；隔离worker首个提交会因远端缺少同一存活Controller的分路输出而拒绝。保留该边界，不以本包装配接线声称多Position writer的worker支持。
- 原／装配Robot的正式Task必须沿共同构建、source和Controller绑定；默认Controller只在已声明的canonical通道、writer、单位和传动下绑定，Task显式选择不得被替换。普通reset验证选择、参数、绑定和状态重建；显式切换仍遵循已有能力范围，不由此扩充装配切换矩阵。
- 保留正式source/provider能力、单位/三层映射、组合/冲突、generation/stale、partial-write fault、ACK与close检查。不为fixture恢复私有兼容桥、宽泛kwargs、getattr兜底链、吞异常、重复状态/hash或过严token保护；临时诊断与故障注入留外部。
- 配置和普通caller只补案例实际需要的入口；现有入口足够则不新增CLI或SDK层。SB3/RSL保留固定空间与autoreset边界；LIBERO保留原source、Task predicate与reset语义。2026-11-17维护者revision002改为canonical action／默认恒等Controller真实链优先，再配置合适Controller；允许复用、扩展或必要新Controller，不要求新路线完整复刻OSC或旧500Hz/gripper cadence，但须声明新算法/profile/时钟并以可信可比OSC参考证明空载精度不退步，不能冒称旧OSC/A123等价。共享算法/模型/servo/记录归TaskEnv对应模块，bench仅留来源、任务语义、配置/薄binding及任务oracle。无受影响缺口可按调用/diff与匹配证据结案。
- LIBERO已确认含七个扭矩电机及两个独立位置夹爪执行器：source声明、单位与native映射须分别核验，静态保持不等于夹爪writer或其ACK。迁入共同Scene时须保留原初始化行的自由物体位姿、速度与fixture语义，并使Artifact和source的关节身份一致；非零原生reset时刻与episode相对时钟不可混用。接触查询须经真实source和provider准入，不能删掉Task要求来促成构造。
- LIBERO task1 的 MuJoCo CPU 代表路线已在正式 CLI／公共 builder 中实测默认七轴 effort 和显式 world-TCP pose Controller；后者的 source 模型要求、TCP 状态和 typed effort ACK 须绑定同一实际 source 与边界，scratch 模型计算不得推进物理。64/65 空载轨迹在冻结窗口内相对历史 500Hz OSC 的位置及姿态最大误差不退步；该证据不证明任务成功、任意模型、其他 provider、独立夹爪writer或切换矩阵。旧 mixed 记录继续可读，未迁移的 LIBERO 路线明确拒绝而不恢复退休生命周期。
- 复用仍匹配的强证据，只跑会揭示实际错误的受影响检查。完整案例覆盖的smoke/开闭/抓放不重复运行，不加完整训练、全A123/G06矩阵、性能门或额外笛卡尔积。不按行数、文件数、删行数、PASS数或搬到新大文件评价架构。
- 普通owner/可读性问题在同一窗口修正，不留给7c、不为每个小问题重新派包。超出原门的能力只登记，不自动开发；若原门确需超出最小适配的新能力，保全具体阻断供维护者决定，不自行删门或扩大范围。
- 2026-11-17维护者确认BodyWrench方向：公共typed表达与场景提交统一，`joint_efforts`和`body_wrenches`保留不同物理语义，由adapter分别降低至合法actuation／外载接口；joint effort不强制走native `ctrl`。一个正常动作Controller与独立Task/caller场景载荷共同准入、提交、记录及清理，不将普通物体伪装Robot、将wrench伪装joint channel或通过清空subject/selection绕过检查。保留producer/body/source权限、frame/作用点/矩参考、单位、显式sum/effect去重、逐子步持续语义和唯一推进。原post-5c总账CTRL-01/02/05、SRC、RUN、REC约束继续适用。
- attempt002实施中：独立producer经source/body声明和共同interval准入，scalar worker与MJWarp设备路径各保留原有唯一推进和记录owner；设备world COM代表仅限B=1。MuJoCo原PickCube source的implicitfast FREE角运动出现原生数值失稳；带角向armature的显式FREE body力矩／非body原点矩参考在写入前拒绝，单独零阻尼／零armature诊断source的物理通过不覆盖该原source，也不改变pin。新的真实运行须记录source、作用点／Frame、时钟、独立oracle、同run H5和close，完成与接收仍按工作包逐门判定。

<a id="7a"></a>
## 7a：NutAssembly 复用与调用者兼容

- **输入／依赖：**4c、5c、6c，阶段 1 的任务／配置兼容决定。
- **诊断耦合收口：**先按[代码与诊断规范](../../../../global/diagnostics-and-code-boundaries.md)及[登记清单](../planning/pre-stage3-environment-refactor.md#diagnostic-policy-and-final-cleanup)分类阶段3–6涉及的核心边界，将实验选择／探针／测试专用兼容归外部驱动、包装／子类或真实功能owner。保留正式准入、feedback、fault和唯一生命周期，不按行数机械拆分；该工作纳入本包，不新增阶段。完成代码归位后再进行代表回归和7b稳定输入冻结，不到7c才大幅修改源码。未完成边界如实交付，不以文档规则代替解耦结果。
- **工作：**在 NutAssembly 已支持后端复用公共构造、配置、施控、reset、render、obs 和记录；核对受影响 TaskDefinition／旧 BaseTaskEnv alias／examples／LIBERO 代表 caller 及 learner／vector wrapper 边界。
- **检查：**无 PickCube 名称／Panda维度硬编码泄漏；具名通道与Robot组件binding复用，任务差异留 task；fixed-space consumer 对 action 变更有明确处理，未迁 caller 有保留路径。选最小相关检查，不要求完整训练和全部 A123 重跑。
- **交付／出口：**代表性真实复用、受影响兼容结果和明确未迁列表；不宣布所有任务已统一，也不移除 2.x 承诺保留的 import 名称。

附加用例收口安排（2026-11-06，维护者已采纳）：[装配Panda版本用例](../planning/stage4-assembled-panda.md)在4b主能力稳定后先做空载／夹爪／补偿代表检查，完整的新Robot两任务配置接线与Solution复用在本7a同包收口。原／新机器人×PickCube／Nut四种交集分别留有效成功和独立读回；精确匹配的4c参考直接复用，不固定重跑四次。该用例不替代G04三后端effort／BodyWrench／Controller reset，也不替代本节原有诊断耦合和调用者兼容工作；独立状态见[用例清单](../planning/assembled-panda-use-case.json)。

<a id="g07a-attempt002"></a>
### 2026-11-17维护者部分接收与attempt002

[A3之前的有界交付已由维护者接收](../maintenance/reviews/20261117_g07a_attempt001_partial_acceptance.md)，保留当前源码GeoPhys未按限定重跑、worker R1-split、默认effort未native验证等限制；不据此宣布全部7a或7b通过。A3与A4进入[attempt002](../maintenance/work-packages/20261117_g07a_attempt002_goal.md)，准备不消耗attempt，实际启动才由1变2。

本窗口另包含维护者指定的`public/v2.1.1-asset-skills`冻结`3da60b74fa8918f996d5abc4a3f93780c67b5d5f`向G07分支的本地整合。该来支含资产Skill/服务、TaskHarness及旧PickCube修补，须逐语义保全当前owner/已接收行为；不恢复退役Env/Isaac Task路径。外部资产工作流编排与TaskEnv物理Runtime须按真实状态/推进/关闭owner区分，不按名称批量删改。只整合适用源码与定向验证，不自动下载模型、安装/注册MCP、部署服务、追未来PR或合并其他未指定分支。合并/修复影响已有证据时才定向复验，不能整树选旧实现或机械重跑所有AP。

A3默认Controller必须按声明通道真实绑定并执行非零canonical action，旧pose/gripper不能当effort透传；所选Controller经公共配置、typed提交和唯一Runtime推进。旧`controller_tracking_002`已恢复为joint-space PD-v6而非OSC，其12mm门不能作为新精度不退步标准；先恢复可信OSC身份/同输入oracle，必要最短参考也计入本窗口。A4按真实新payload保全正式Recorder/reader及当前门/身份/关闭关联。

总连续wall硬上限240分钟，包含实现、合并、验证、实际阻塞问答/等待、报告及提交；不因subagent/换线程重置。维护者明确允许实施者/subagent就实际阻塞点向规划线程提问，规划者可在原范围回应，仍保持单writer、原共享锁和native累计预算；该授权取代旧“一律不发送执行中补充”的绝对限制，不允许无问叠加新任务或超范围默示批准。7b/7c与原9/9门不变，本窗口不自动启动后续阶段。

<a id="g07a-closeout"></a>
### 2026-11-17独立主审与7a关闭

生产 `0a6213c040e06e6385b6d1f5509af34a8d5b8372`、旧资产来支本地merge `94e865e3cd272f5c8c5b8ca8892799270457cc84` 已按[独立主审](../maintenance/reviews/20261117_g07a_attempt002_acceptance.md)有界收尾，7a普通attempt数2。默认七轴effort、typed ACK、reset、同运行记录/关闭成立；显式pose空载在补齐同手指保持输入的历史OSC参考后，四项冻结指标均未退步。64步LIBERO正式caller仍task_success=false、Solution completion未评估，不扩张为任务成功、独立夹爪或其他provider/切换能力。原四个MuJoCo完整交集和GeoPhys当前源码未重跑等限制继续保留。

主审外部补证新增1600子步/21.094秒，单独事前冻结并计账；不重开原执行窗口或普通attempt。原attempt002重置后16460子步不变。7b工作包仅准备，不能从此节推断九格已运行。

<a id="7b"></a>
## 7b：稳定输入下的最终矩阵

- **输入／依赖：**已关闭的7a；先完成本节新增PR整合和验收必需的最小适配，再冻结最终 Core／provider／source／Robot／TCP／Controller／Solution／renderer／device／seed／horizon／预算和 oracle。
- **工作：**执行 PickCube 三后端×三 seed（初始 31/32/33），目标 9/9 task-success；收口阶段 3–6 已冻结的同一Env切换、Controller／7＋2／BodyWrench与贡献组合、图像与并行代表性交集。
- **检查：**runtime validity、原任务 predicates、生命周期有效成功、Solution completion、图像同步、独立同运行 H5 读回及 close／进程清理分别报告。对受影响输入才重跑；可以复用仍精确匹配的更强证据。
- **交付／出口：**九格成功与其他独立门都有可审核证据；失败／NOT_RUN／未测项如实保留，不能用 runtime-valid 或不同 run 的部分结果拼接成通过。

2026-11-17维护者新增：将[PR #3](https://github.com/Lebingelee/GeoChora/pull/3)冻结head `23387a9cffd82fe02fb69fb5d2993141fdd54ae9`（`v2.1.1-asset-skills-develop`）本地合入当前G07阶段分支，此项归7b，不倒写为7a成果。逐语义裁决实际12处冲突，保留当前共享锁继承/进程清理、正式PickCube/Robot/source与桌面＋asset-object准入owner；来支setup/doctor不自动部署、下载或改用户MCP。其作者运行证据不替代本版最终九格。合并/必要修复与图像/独立reader薄驱动稳定后才冻结矩阵输入。

[7b attempt001完整包与Goal提示](../maintenance/work-packages/20261117_g07b_attempt001_goal.md)最初准备时为 READY_FOR_MANUAL_FORWARD_NOT_STARTED／attempt0，现已启动，见下方实施状态。原总连续wall硬上限240分钟，含PR合并、问答等待、验证和收尾；native累计≤120分钟、显式子步≤100000，单run/内存/GPU/输出/原锁监督见包。三provider各seed31在同次完整Solution中保留reset、首个非零step和最终返回边界图像；其余seed可state-only。H5、caller严格完成与各provider实际schema的close分别关联，不新增跨provider记录平台。原三条路线为MuJoCo CPU、GeoPhys CPU、Isaac PhysX CUDA；seeds31/32/33，MJWarp不替换MuJoCo，附加Robot不乘进九格。准备本身不创建Goal/native或实际merge；后续启动与本地合并见下方实施状态。

最终九格不等于每个 backend×renderer×Controller×batch 都跑三 seed；组合覆盖在阶段 1 冻结，各维度有最小真实代表例。不同 solver 不要求轨迹或像素逐点相同。若九格有失败则本门未完成；范围改变须维护者决定，保留原门和失败历史。

### 7b attempt001实施状态（2026-11-17）

已在本地合入指定 PR #3 冻结 head；最终生产输入 `78349184d0600e2fb804e6461930c475bfcc67c1`。维护者明确允许在原 PickCube Solution 内压缩前段固定等待，保留实际 TCP gate、下降／闭合／抬升、原任务与完成判据及 1000 步上限；这是一项特定时序授权，不扩展到改变其他任务策略。最终三 provider × 三 seed 均有同运行任务成功、原事件驱动 Solution 完成、独立记录读回和关闭；计划轨迹完成字段为 null，不补造。原失败与截断记录仍保留。

7b实施返包为 PARTIAL，待独立主审：其他独立门必须单独核验，不能从九格成功推定全部通过。当前 BodyWrench 真实 source 下的组合选择被一致性 guard 拒绝，当前链路尚未验证；历史 4b 与当前 COM 力证据不能替代。维护者随后授权将显式子步预算重新设为 200000，以新周期计数并保留此前实际消耗；其他预算不变。7c仍为 PLANNED／0。

<a id="g07b-attempt002"></a>
### 7b attempt002准备：公共贡献与provider分别适配（2026-11-17）

维护者已停止attempt001并要求准备[attempt002完整工作包与Goal提示](../maintenance/work-packages/20261117_g07b_attempt002_goal.md)，状态为READY_FOR_MANUAL_FORWARD_NOT_STARTED；本次准备不启动Goal/native、不增加计数，7b普通attempt仍为1，7c为PLANNED／0。attempt001的PARTIAL及原始失败/拒绝继续保留，不视为7b已接收。

维护者明确选择公共链＋MuJoCo、Isaac、MJWarp的BodyWrench代表接通，GeoPhys按冻结公共API可达范围处理；这是本次新增明确授权，不倒写成历史4b的三后端要求。MuJoCo保留hand／自由体、偏置矩、effort组合和hold/reapply/clear原门；Isaac6.2 scalar隔离worker接通真实body/link载荷与传输；MJWarp4.0.1走正式device B1／step及原same-step生命周期；GeoPhys限具名显式FREE的公开qfrc交集，任意link/device与无DOF body不足的能力明确拒绝，默认不改pin。SDK接口存在、typed类型存在和ACK均不代替本机物理响应、同运行独立H5读回及关闭证据。

已通过的九格及其他代表矩阵不要求重跑。按`78349184`族的`freeze-final.json`、`results-final.json`及原H5复用，保留输入身份、PickCube事件驱动完成/null字段及旧限制，只补实际受影响的最短定向检查。attempt002负责最终diff影响表和7b完整独立主审输入；不自动开始7c。240分钟新执行窗口仍受7b原native累计余额约3249秒和新子步周期余额约198825约束，本包另收紧新增显式子步至20000，不重置历史消耗；精确资源与状态见完整包。

<a id="g07b-priority-disposition"></a>
### 2026-11-17维护者优先级调整与主线补证

attempt002生产返包`81d1138d`保持原PARTIAL。维护者要求只优先处理直接影响当前主线的部分，仿真器本身问题留专门后续，退休入口不强制恢复/迁移。按[裁决与补证](../maintenance/reviews/20261117_g07b_attempt002_priority_review.md)，修正当前Robot配置测试并通过7项现有合同/清理检查；MJWarp无producer补齐非零动作、reset、两份同运行H5独立读回与close，新增10子步，未改生产代码或重跑九格。两项退休PickCube注入入口的原失败保留，当前共同构建已有清理覆盖，不因此恢复旧factory。

MuJoCo3.8.1 FREE角向armature／implicitfast的原生数值边界保留写入前拒绝，问题G07B-MJC-FREE-ARMATURE移交专门后续，不要求G07修引擎、换source/积分器或升级依赖。独立预声明的零阻尼/零armature夹具证据限其自身source，可证明公共载荷响应，不证明原组合修复；原失败与原B2-2状态保留。当前重点缺口已补证，7b进入最终独立主审，不以退休suite未全绿或上游数值研究自动开启attempt003；ordinary attempt_count仍2，版本接收另作判断。

<a id="g07b-final-acceptance"></a>
### 2026-11-17 最终独立主审与7b收尾

维护者同意仅处理直接影响主线的部分，并授权检查通过后接收及主 agent 小修。按[最终独立主审](../maintenance/reviews/20261117_g07b_final_acceptance.md)，生产`81d1138d`及测试／文档后继`c392b259`已 **ACCEPTED_BOUNDED_7B**，普通attempt数2，不新开attempt003。九格在原`78349184`输入9／9任务成功、同运行Solution完成、图像／记录／关闭分别成立；本轮重新离线读回九份H5并核对图像及原caller，未重跑native矩阵。B2-1～B2-6在实际source/body/provider范围接收；MuJoCo原生数值交集保留guard并交后续专题，旧退休入口与原115／3等失败保留，不声明原失败全绿。

[单一能力矩阵](../capabilities/capability-matrix.json)现登记实际九格及原冻结身份，初始NOT_RUN规划快照另存。原两次PARTIAL返包与主线优先审阅仍按原时点保留；本次最终审阅新增0子步、不改生产代码。7c最终总结可消费本页接收结论，独立文档工作树仍以其自身状态为准，本轮未启动7c attempt002，也不授权发布或回合develop/main。

<a id="7c"></a>
## 7c：版本文档与能力记录

- **输入／依赖：**7b 结果、各阶段实际 commits／报告／原始 Evidence；失败也需收据，但不能以文档完毕代替版本全部验收。
- **工作：**保持已确认设计与已实现／已验证能力分列，更新本版协议状态、公共 API／配置／迁移和示例、单一矩阵、当前导航、恢复页及相关 Skills。复核文档校验器覆盖；检查旧候选状态／基线文字的时点，不重写历史接受决定。
- **检查：**文档结构／链接／JSON、公开例子与真实 caller、能力语言和证据身份、dirty／gitlink／refs；Skills 按源码和调用者刷新，不只做文字同步。记录检查运行与未运行项。
- **交付／出口：**版本文档准确描述实现与未支持组合，7 个 Goal 的摘要和编排索引可恢复，原始日志／图片／H5 不入库。必要本地提交与审阅意见完整。

<a id="g07c-split-doc-worktree"></a>
### 2026-11-17维护者调整：独立工作树提前完善文档

维护者明确允许在7b尚待接收时，先完成与其最终结果无关的文档工作；这是本节依赖的**有界提前执行例外**，不取消7c整体收口对7b接收的依赖。
7c attempt001使用独立`codex/v211-stage7-docs`工作树，源码基线`4fdf9379482af6bb913eb1a6587316e64b6a0fed`，不复制主实施树正在变化的7b源码。准备为READY_FOR_MANUAL_FORWARD_NOT_STARTED／普通attempt0，实际启动才增1；不创建执行Goal/native或自动派发。

- **attempt001现在完成：**安装、scalar无渲染、GeoPhys Rasterizer优先的有头相机、device并行三provider、环境/资产/Robot、独立Controller章节及API详细教程；归并当前文档与导航，按真实caller修正文档漂移及相关现有Skills。逐节内容、命令/字段、输出/排错与验收见[详细填充蓝图](../planning/stage7-7c-tutorial-blueprint.md)和[完整包索引](../maintenance/work-packages/20261117_g07c_attempt001_goal.md)。不交付只有目录、链接或TODO的教程。
- **attempt002等待7b：**以独立主审实际接收的7b HEAD重新对账，更新BodyWrench新公共调用/准入/IPC/记录、最终九格与其他门的单一能力矩阵、7Goal/22子阶段摘要、恢复身份和Skills，处理两分支文档冲突后完成7c。不能提前写7b已接收或7c已完成。
- **源码约束：**7c以说明、归并和普通示例为主，不改运行代码/算法、依赖、source/provider、Recorder或tests来让教程通过；继续遵守[post-5c总账](../planning/post-5c-code-project-optimization-diagnostic-ledger.md)与唯一owner，不增加API/factory/validator或诊断耦合。新BodyWrench公共typed方向可解释，未稳定签名标WAIT_7B_ACCEPTANCE。
- **实际缺口：**准备输入的Nut仅准入source-bound ExpertAction，普通随机数组被明确拒绝；保留维护者要求的随机动作章节、预期拒绝例子和T-NUT-RANDOM未满足项，不伪造Solution身份或放松guard。最终仍无普通随机能力时交维护者裁定必要task-local接线，不以负例充作随机控制成功。
- **隔离与验证：**两个活跃G07 checkout及原locked历史worktree保留；7b writer与其原证据/共享锁不受本包改写。attempt001不启动native/安装/下载，只做源码/caller、教学语义、AST/JSON/链接核对并准确引用既有运行。没有新运行则不称教程已native验证；不为文档绿灯复制保护日志或修改旧证据。

本工作树中的7b状态是分叉输入快照；其实时结果由主实施树维护。7c最终正常整合须等待7b返包/接收并作diff影响复核，不在其活跃窗口合并或覆盖其orchestration。

<a id="g07c-attempt002"></a>
### 2026-11-17 attempt002 范围更新

维护者已接收attempt001文档，实际docs HEAD为`1e9081c4`；7b也已按[最终主审](../maintenance/reviews/20261117_g07b_final_acceptance.md)接收。现正常[整合docs树及保全](../maintenance/reviews/20261117_g07c_attempt001_integration.md)，使用阶段7主分支准备002，普通attempt仍1，实际执行002才增2。此前“7c不改源码”和Nut仅留负例是001的边界；维护者本次明确授权002修复Nut普通随机动作拒绝，以及直接影响教程的declared-marker示例漂移。

002沿Nut Task binding／既有动作Controller和共同生命周期最小接通普通action，仍保留原ExpertAction的source／Solution身份、native反馈、reset／混用／fault检查；不复制Solution或Runtime，不放宽原Task成功/完成门。只补实际受影响代表运行，原7b九格与其他已通过矩阵按身份复用。完整包须包含实现、正式随机教程、定向负例、同运行H5独立读回和关闭，不能以设置一个flag或AST通过作为能力接收。

同时收口7b BodyWrench最终公共API／provider准入／记录与组合规则、7Goal/22子阶段摘要、单一矩阵、恢复入口、指南／API／Skills、版本变更／限制和发布准备。维护者补充：`task_env/doc`必须作为更细致的模块教程，按原`api/composition`、`semantics`、`planning`、`recording`、`appendix`及中文指南结构，逐页深化34篇current文档，覆盖21顶层目录及facade的实际职责、上下游、接口/输入输出/异常、生命周期/资源和完整核心例子；8篇历史更新日志原字节保留。不准只加导航或笼统“补全文档”，逐页owner/要求见完整包module-doc-map。维护者授权在002独立验收后将**本地develop**快进到最终阶段7 HEAD；不得覆盖非祖先develop、同步main或操作远端，源码身份变化按影响复核，不机械重跑完整历史矩阵。详见[002完整工作包与Goal提示](../maintenance/work-packages/20261117_g07c_attempt002_goal.md)。准备为READY_FOR_MANUAL_FORWARD_NOT_STARTED，计数仍1。

## 发布边界

当前文档与阶段接收不自动授权发布操作。2026-11-17维护者授权上述旧资产冻结分支及7b指定PR #3冻结head合入G07的本地merge；此前不授权回合develop/main；本次002验收后本地develop快进以本节新增授权为准，仍不授权main同步、push／tag／GitHub Release，也不自动选许可证。第三方资产来源／分发未决项保持原状态，不因技术接通被改为获准分发。若维护者后续要求发布，单独冻结发布范围、许可和版本材料。
