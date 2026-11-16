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

<a id="7b"></a>
## 7b：稳定输入下的最终矩阵

- **输入／依赖：**7a，冻结的最终 Core／provider／source／Controller／Solution／renderer／device／seed／horizon／预算和 oracle。
- **工作：**执行 PickCube 三后端×三 seed（初始 31/32/33），目标 9/9 task-success；收口阶段 3–6 已冻结的同一Env切换、Controller／7＋2／BodyWrench与贡献组合、图像与并行代表性交集。
- **检查：**runtime validity、原任务 predicates、生命周期有效成功、Solution completion、图像同步、独立同运行 H5 读回及 close／进程清理分别报告。对受影响输入才重跑；可以复用仍精确匹配的更强证据。
- **交付／出口：**九格成功与其他独立门都有可审核证据；失败／NOT_RUN／未测项如实保留，不能用 runtime-valid 或不同 run 的部分结果拼接成通过。

最终九格不等于每个 backend×renderer×Controller×batch 都跑三 seed；组合覆盖在阶段 1 冻结，各维度有最小真实代表例。不同 solver 不要求轨迹或像素逐点相同。若九格有失败则本门未完成；范围改变须维护者决定，保留原门和失败历史。

<a id="7c"></a>
## 7c：版本文档与能力记录

- **输入／依赖：**7b 结果、各阶段实际 commits／报告／原始 Evidence；失败也需收据，但不能以文档完毕代替版本全部验收。
- **工作：**保持已确认设计与已实现／已验证能力分列，更新本版协议状态、公共 API／配置／迁移和示例、单一矩阵、当前导航、恢复页及相关 Skills。复核文档校验器覆盖；检查旧候选状态／基线文字的时点，不重写历史接受决定。
- **检查：**文档结构／链接／JSON、公开例子与真实 caller、能力语言和证据身份、dirty／gitlink／refs；Skills 按源码和调用者刷新，不只做文字同步。记录检查运行与未运行项。
- **交付／出口：**版本文档准确描述实现与未支持组合，7 个 Goal 的摘要和编排索引可恢复，原始日志／图片／H5 不入库。必要本地提交与审阅意见完整。

## 发布边界

当前文档与阶段接收不自动授权发布操作。2026-11-17维护者仅授权上述冻结开发分支合入G07的本地merge；不授权合并回develop/main、push／tag／GitHub Release，也不自动选许可证。第三方资产来源／分发未决项保持原状态，不因技术接通被改为获准分发。若维护者后续要求发布，单独冻结发布范围、许可和版本材料。
