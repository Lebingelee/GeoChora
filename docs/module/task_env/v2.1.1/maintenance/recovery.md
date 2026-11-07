# v2.1.1 恢复与当前状态

## 当前：G05 5b attempt002 独立主审，需返工

[5b attempt002 主审](reviews/20261107_5b_attempt002_sol_review.md)决定 `REWORK_REQUIRED_5B`，普通 count=2。MuJoCo、Isaac 真实窗口／RGB 有界进展保留，图像及颜色证明未完全闭合；GeoPhys 公开裁剪/生产路线阻塞。[第三次前重评](../planning/stage5-5b-attempt003-reassessment.md)及[Sol 前置工作](../planning/stage5-5b-attempt003-prework.md)已完成；维护者已同意所提 provider/gitlink 与预算范围，包须由其手动转发，第三次尚未执行。5c PLANNED，不自动进入阶段6。

## 历史：G05 5b attempt001 独立主审，需返工

[5b attempt001 主审](reviews/20261107_5b_attempt001_sol_review.md)决定 `REWORK_REQUIRED_5B`，count=1。MuJoCo 窗口和 RGB 的独立图像/颜色证据未闭合；GeoPhys 所测 camera clipping/生产路线未闭合；Isaac renderer-facing 状态与公开 physics state 不一致，window/RGB 被拒。真实失败、部分证据和先前 5a 有界接收保留；5c 仍 PLANNED。准备返工包不消耗 attempt，不自动派发或进入阶段6。

## 历史：G05 5a 经独立主审有界接收

[5a attempt002 主审](reviews/20261107_5a_attempt002_sol_review.md)决定 `ACCEPTED_BOUNDED_5A_RENDER_BINDING`，普通 count=2。真实范围为单 Env PickCube、MuJoCo CPU 与 renderer-only 模型，001 的返工历史和原始证据保留；窗口/RGB、同步 observation、renderer 切换、GeoPhys/Isaac native 与 cross 均未验证。5b/5c 为 PLANNED、count=0，后续工作包需明确授权并由维护者手动转发；不自动进入阶段6或发布。

## 历史：G05 5a attempt001 已主审，需有界返工

5a attempt001 的 MuJoCo CPU PickCube renderer-only 代表绑定与独立双状态证据保留；Sol 发现渲染更新及恢复均失败时不可信 visual pose 仍可读取，决定 [REWORK_REQUIRED_5A](reviews/20261106_5a_attempt001_sol_review.md)，普通 count=1。5b/5c 仍 PLANNED、count=0；后续另备一次完整返工包，未派发，不自动启动。前包 writer 和 native 已释放；保护输入、两 pin 不变。阶段5继续复用 `codex/v211-stage5` checkout。

## 历史：G04 三子阶段分别有界接收

G03 与 G04/4a、4b 原有界接收不变。4c attempt001 经 [Sol 独立主审](reviews/20261106_4c_attempt001_sol_review.md)按 MuJoCo CPU 单 Env Controller reset 切换和迁移后 PickCube seed31 成功作 `ACCEPTED_BOUNDED_4C_RESET_PICKCUBE`，count=1。任务运行时夹爪 cap ±10 N 与 source 编写值 ±5 N 的差别、外力切换及跨后端未覆盖项均见审查；4b 中 GeoPhys A05 joint2 方向诊断在首次超时后已通过重跑；Sol 此前误称未完成，已在主审记录更正。不得自动进入阶段5、push 或 merge。

## 历史：3c001有界接收，G03限定范围收尾

3c经[Sol独立复审](reviews/20261106_3c_attempt001_sol_review.md)接收为ACCEPTED_BOUNDED_3C_RESET_REBUILD，count=1，不需002。五段同一Env链、固定观测／Core流、旧输入拒绝、故障恢复和逐episode H5均满足冻结出口；仅覆盖显式PickCube profile及四条声明边。3a、[3b](reviews/20261106_3b_attempt003_sol_review.md)及3c各自有界接收，G03限定范围收尾，原N08 FAIL保留。6.1辅助App启动／版本成立但close超时，完整兼容未通过。active_packages=[]；等待维护者后续安排，不自动进入阶段4或push／merge／tag。

后续规划重评（维护者已采纳本规划）：[装配Panda](../planning/stage4-assembled-panda.md)是本版附加集成用例，原G04完整主线／出口恢复；建议4b稳定后早检查、7a两任务Solution完整收口，原G04接收不以该用例四交集齐全为前置。新类在robot目录、配置选择、空载精度和现有夹爪／Solution复用、不做物性等价的需求均保留。上述计划采纳当时的 4a–4c 为 PLANNED／attempt0；当前进展以本页顶部和编排索引为准。当前代码仍未实现新Robot或通用子树补偿。

人工交接入口：[阶段3收尾与G04 Sol交接](20261106_stage3_closeout_stage4_sol_handoff.md)。准确HEAD、保护输入、必读Skill和故障处理经验在维护者工作区handoffs/V211_G04_sol_handoff；新Sol先读其README全文，不重开旧前置或G02。

## 历史：3b003与条件3c001准备时

维护者要求一次将两个Goal包交Terra顺序实施；[连续安排](../planning/stage3-3b003-3c001-sequential-execution.md)明确仅在3b全部required技术通过、提交／报告冻结及资源释放后，绑定其实际HEAD开始3c；Sol最后分别独立复审，中间不伪记3b已接收。3b count仍2／REWORK_REQUIRED_3B，3c count0／PLANNED，active_packages=[]，准备不计次数。最后普通[3b003重评](../planning/stage3-3b-attempt003-reassessment.md)已完成；[3c首包](../planning/stage3-3c-attempt001.md)固定公开reset入口、opt-in observation、随机流、四条实际切换边及fault恢复。外部包入口在维护者工作区handoffs/V211_G03_3b003_3c001_bundle，精确3b输入见其snapshot，3c未来SHA不预造。

3b未过则不启动3c，第三次后人工诊断，不普通004或改名续作。两包分别120–180分钟主动、240分钟硬墙时，不能互借；不自动消息／对话／subagent或阶段4。原3a及002有界接收、原N08 FAIL保留；新N08-v2方向／保持案例在本包执行前显式冻结。准备时Sol无native或SDK launcher。

## 历史：3b attempt002独立复审时

Sol已作[002独立复审](reviews/20261106_3b_attempt002_sol_review.md)：整体REWORK_REQUIRED_3B，普通count=2，active_packages=[]。已确认所测MuJoCo下沉在3b前就存在；维护者授权的默认关闭Panda补偿在最终PickCube31／Nut19短程中已消除初始下沉并产生正向上移。launcher及F06同次九关节速度记录修复有界接收。长时实验早于最终细化，最终补偿H5／稳态、required物性公共读回、部分reset／约束及缺项拒绝仍须闭合；原默认关闭三路线N08 FAIL不改。通用装配树选择是维护者确认的设计方向，未实现，不追加为原3b阻塞。第三次前先重评上游公共接口依赖和新案例，不自动003或3c；不再重复旧HEAD因果对照。

更新时间：2026-11-06。3a接收、原attempt历史和原始包均不变。当前精确状态见[编排索引](orchestration.json)。

## 历史：3b attempt002准备时

3a接收决定不变。Sol对3b attempt001决定[REWORK_REQUIRED_3B](reviews/20261105_3b_attempt001_sol_review.md)，原技术结果THREE_B_TECHNICAL_PARTIAL保留；普通attempt_count=1，不进入3c。三条指定路线各完成公开10步及独立读回，但短窗正向位移门三者均失败；部分模型／记录要求尚未充分验证。6.2 pip路线真实启动并关闭，维护者另装6.1但本轮未运行。独立FK与R3重构表明两CPU目标方向／TCP映射一致，下沉在hold段已开始，尚不能归为新代码回归；launcher路径上下文丢失已离线复现。按[聚焦返工分析](../planning/stage3-3b-rework-analysis.md)完成[002完整包](../planning/stage3-3b-attempt002.md)准备，count仍1、active_packages为空，等待维护者手动转发。首组三组CPU因果控制采用双锁内临时detached旧基线并恢复当前主题分支，不新建branch/worktree；先在ignored登记start，恢复后才改tracked编排。原N08不改，6.1辅助仅主线完成且明确有余时；Sol无native/SDK launcher/自动消息。详见[执行摘要](reviews/20261105_3b_attempt001_execution.md)及ignored原始返包。

更新时间：2026-11-05。按[协议确认收据](20261103_protocol_baseline_confirmation.md)、[执行表](../planning/execution-and-acceptance.md)及本页恢复当前状态。

## 历史：3b完整包准备时

3a接收和原attempt历史保持。维护者要求开始下一步；Sol已准备[3b attempt001完整安排](../planning/stage3-3b-execution.md)，覆盖消费级依赖修复、Isaac6.1/6.2共同部署与身份，以及三后端真实物性/readback闭环。维护者澄清GeoPhys原生solver不消费其MuJoCo求解路线依赖，本包修正准入范围，不改pin或升级环境。3b仍PLANNED／attempt0、active_packages为空；准确输入与预算在外部snapshot冻结，等待维护者手动转交单一Terra／Luna。Sol无native、source解析或自动消息，不启动3c。

## 3a已由Sol接收，诊断001关闭

诊断001输出6b11123e经[Sol独立复审](reviews/20261105_3a_diagnostic_attempt001_sol_review.md)决定 **ACCEPTED_3A_ROUTING_ADMISSION**，3a整体在配置／环境准入／已有声明与具体构建检查接线／同请求回执范围通过。真实Position和leaf生产来源consumer、required缺Frame拒绝、H5 metadata及最终PickCube31／Nut19 MuJoCo CPU短程均有证据；F06真实目标依赖不满足时已在加载USD前准确拒绝，source未评估明确保留。Sol核对215输出／10提交文件hash，独立5项guard离线通过，未解析来源或运行native。

普通attempt_count=3、diagnostic_attempt_count=1，原三次失败／局部接收记录不改写，诊断D1/D2关闭、active_packages为空。当时3b仍PLANNED／attempt0；其后已执行，结果以本页顶部为准。进程树RSS未测及首次source命令cwd偏差已保留说明，不为补账本重跑。

## 历史：诊断001由维护者指定并准备

维护者在本会话完成阶段范围／矩阵与SHA／时间讨论，明确要求诊断attempt工作包并指定Terra手动转交。[诊断001完整安排](../planning/stage3-3a-diagnostic-001.md)现为PREPARED_NOT_DISPATCHED，普通attempt_count=3、diagnostic_attempt_count=0，active_packages为空；当前准确输入在准备文档提交后的外部snapshot冻结。已定位真实F06和现有代表输入，无Sol native／自动派发。手动转发后按120分钟窗口诊断、最小修复和聚焦验证，原三次结果不改写，报告后Sol独立复审，不自动普通004或3b。

## 历史：3a第三次未接收与人工诊断停止点

Sol对attempt003／3d10b357作出 **NOT_ACCEPTED_3A_HUMAN_DIAGNOSIS_REQUIRED**，详见[独立复审](reviews/20261105_3a_attempt003_sol_review.md)。最终PickCube31／Nut19真实MuJoCo CPU、隔离worker PickCube和同请求H5 metadata事实保留；Sol核对110输出／20提交文件hash、最终日志并独立5项离线通过，native为0。

整体3a仍未通过：F06真实factory在pxr guard处先于selected preflight停止，不能认定SDK或资产缺失；versioned Controller／StateRequirements／nested完整selected生产source消费证据不足。attempt_count=3，active_packages为空、无普通候选包；第三次已关闭，不因180分钟未用满而续时。等待维护者主导人工诊断及后续明确授权，不自动attempt004、改名续作、创建／消息诊断对话或进入3b。原包与旧证据不改写，002核心恢复不重开。

## 历史：3a attempt002核心恢复已由Sol有界接收

Sol决定 `ACCEPTED_BOUNDED_3A_CORE_RUNTIME_RECOVERY`：PickCube31／Nut19真实MuJoCo3.8.1 CPU公开创建、reset、各10步和close的核心恢复通过；各推进0.10秒，实际source闭包及具名映射、已复现worker错误回收得到有界修复。源码／原生日志和manifest已核对，Sol独立5项离线检查通过，没有重跑native或历史大组。详见[独立复审](reviews/20261105_3a_attempt002_sol_review.md)。

3a整体仍 `PARTIAL_CORE_RUNTIME_RECOVERED`／attempt_count=2；剩余只先收口实际声明求交与具体adapter构建检查点，不扩展安全／边界矩阵。已完成[003前重评与最后窗口安排](../planning/stage3-3a-attempt003-reassessment.md)，最后[完整003包](../planning/stage3-3a-execution.md#attempt003-complete-package)现已准备，等待维护者指定单一执行者并手动转发；尚未派发／消耗第三次。第三次整体未接收必须人工诊断，不自动第四次。GeoPhys／Isaac原生仍交3b，Isaac兼容版本安排不变，不重开已接收核心恢复。

## 历史：3a attempt001：Sol已复审，需返工

Sol对 `32397283` 作出 `REWORK_REQUIRED_3A`：普通PickCube／Nut reset闭包回归、逐能力build oracle、嵌套／typed需求及错误worker回复清理未闭合；不可部署，不进入3b。完整证据与安排见[独立复审](reviews/20261105_3a_attempt001_sol_review.md)。attempt_count=1；下一候选为 `V211_G03_3a_attempt002`，准备不计attempt，仍由维护者指定Terra／Luna手动转发。使用同一分支。维护者最新要求已将未派发的attempt002修订为revision 2：先修核心source/reset接线，读取真实资产，让PickCube31和Nut19各在真实MuJoCo CPU上创建、reset、10步及close；只做必要受影响检查、旧证据直接引用。执行者转发后原生累计30分钟／2000物理步，Sol准备不启动引擎。详见[当前runtime-first安排](../planning/stage3-3a-execution.md#attempt002-runtime-first)。

新增Isaac反馈范围已进入[仓库兼容规划](../planning/isaac-deployment-compatibility.md)：v2.1.1实现6.1／6.2共同PhysX路线与部署可移植性，5.1留后续版本。它不追溯增加attempt001门，3a返工后在3b完整包中实施；6.1未安装，native仍NOT_RUN。下文旧状态均属各自历史检查点。

## 历史：新Sol接手时3a完整包已准备，尚未派发

Sol已完整核对交接及必读资料，实际Core输入与`develop@9d942d43`快照一致，两份保护untracked及子模块pin不变。只读核对未发现新的3a在途包／writer；旧Terra前置窗口已有完整返包和释放声明。已fetch核对public/develop，本地develop领先236、落后0；从完整本地develop建立`codex/v211-stage3`，3a–3c共用当前checkout，新增worktree为0。develop保留原交接HEAD，无reset/rebase或推送。

首份`V211_G03_3a_attempt001`已准备，由维护者指定一个Terra／Luna并手动转发。准确输入HEAD、保护字节和成员摘要在外部包snapshot／manifest冻结；[3a实施安排](../planning/stage3-3a-execution.md)记录当前源码落点、缺口、预算与出口。3a–3c仍PLANNED／attempt0，active_packages为空；未启动实施、native、subagent或后续子阶段。准备不计attempt，不因已有G03等待对话而重复派包。

原[交接检查点](20261105_stage3_sol_handoff.md)保留交接准备时事实。当前动作是等待维护者指定并转发完整3a包，完整报告与writer释放后Sol独立审阅，不自动进入3b或阶段4。下文旧“分支尚未创建”等描述按其历史时点理解。

## 当前决定：前置核心收尾已有限接收

维护者最新安排：先落实[诊断与代码边界规范](../../../../global/diagnostics-and-code-boundaries.md)，本轮不再全面解耦。后续环境、Controller、provider和renderer开发从外部诊断，不向核心新增实验／测试分支；现存已确认耦合登记在[规划第2.6节](../planning/pre-stage3-environment-refactor.md#diagnostic-policy-and-final-cleanup)，在版本准备进入7a集成时集中处理，并在稳定源码上验证。有限接收不表示诊断完全隔离，规则更新也不表示代码已整改。规范已落地；目前G03只完成分支与首包准备，尚未启动实施。

`V211_PRE_STAGE3_CLOSEOUT_120MIN_001`返包`99de88abd6d3f464de0d5c9c98362813f52252c9`经[Sol复审](reviews/20261105_pre_stage3_closeout_120min_sol_review.md)，决定 **ACCEPTED_BOUNDED_PRE_STAGE3_CORE_CLOSEOUT**：C1核心职责、C2当前文档、V受影响行为在限定范围通过，本次前置核心收尾结束，不再追加持续拆分窗口。runtime不依赖具体Nut Solution，任务侧保留检查；R05b普通reset不持有Solution，兼容Expert按需创建。Sol独立R05b检查25 passed／1 deselected，核对执行者182 passed／1 deselected及Nut物理／同次reader结果，并接受有调用链差异依据的PickCube和Nut证据复用。详见[原返包](reviews/20261105_pre_stage3_closeout_120min_001.md)。

真实R05b provider、新安装及其他未验证能力继续保留限制，环境类更广整理不等于已完成；它们不重开本次限定收尾。阶段3分支和首份3a包现已另行准备，见本页顶部；尚未派发实施。以下派包计划与旧记录保留当时身份，不覆盖本段接收决定及顶部的新接手状态。

## 本次收尾的派包记录（历史）

维护者要求回到原环境重构与开发指引目标，最多再用两小时。最新源码检查点为`develop@dba855e1ad9575d21604304dc04e9f7fc036ad7e`，tracked clean，两个保护untracked保留；整体维护待Sol复审，G03未开始。最后窗口以[规划第2.5节](../planning/pre-stage3-environment-refactor.md#pre-stage3-closeout-120min)为当前执行范围：C1任务／Solution与Env/runtime职责、诊断隔离；C2当前`task_env/doc`和真实example；V只验证实际受影响行为。已接受生命周期不重做，不再逐helper拆分或逐提交重建全套证据。

`5a04140a`的PickCube31／Nut19 MuJoCo成功和独立reader已有记录；至`dba855e1`仅五个文档文件变化，允许按原运行身份引用并注明运行代码未变。旧任务短检查按其各自来源和调用链另判，不将新文档HEAD视为全部证据自动失效，也不冒充新run。证据入口见[当前状态](reviews/20261105_pre_stage3_current_status.md)。下文各次NOT_RUN／PARTIAL与预算待答复描述均保留所属历史检查点，不能覆盖本段当前入口。

两小时包含实现、必要验证、文档、提交与返包，到时无条件停止新工作并释放窗口；核心未过门就列具体阻塞，不自行延期，不自动接收或进入阶段3。包由维护者手动转发，Sol本次仅准备规划与prompt，未启动执行。

## 状态

- G01/1a–1d 和 G02/2a 的既有 Sol 决定保留。
- G02/2b attempt_count仍为2。attempt002在原验收包中为G2 FAIL、G3 PARTIAL；维护者于完整报告/manifest提交前暂停，G5为`INCOMPLETE_USER_PAUSED`。2c整理不能倒填或改写这些历史。
- Sol现以 `ACCEPTED_BOUNDED_STAGE2_REFERENCE` 接收2a归因、2b MuJoCo代表实现与2c成功参考冻结，阶段2收尾。此决定不把旧2b扩展包改为全通过。详见[阶段2主审](reviews/20261104_2c_sol_review.md)、[2b中止记录](reviews/20261104_2b_closeout.md)和[2c参考](reviews/20261104_2c_reference_freeze.md)。
- 本窗口`V211_G02_2c_attempt001`只封存现有文档和成功参考，未启动native、pytest、reader、GPU probe或provider import。当前2c状态为 `ACCEPTED_BOUNDED_2C_REFERENCE_FREEZE`；阶段3未开始。

## 证据边界

PickCube seed31 MuJoCo CPU主参考为960 transitions成功、lift 0.10518958081676949 m、task门限0.10 m，独立reader通过。NutAssembly seed19两次独立运行均2377 transitions成功。PickCube seed32在固定horizon1000以0.08261901333725602 m lift失败；保留HDF5与reader，不增大horizon、不放宽oracle。GeoPhys PickCube失败于Solution stale-execution-time guard，control_step=3，具体两侧时刻和完整HDF5缺失。Isaac冻结delivery校验通过，但未有App/native运行。

完整人工阶段2时间线存于主工作区 `/home/lly/Documents/ChatGPT/GeoChora v2.1.1/execution-output/V211_manual_analysis_stage2_summary_001/report.md`；用户暂停时的进度报告为 `/home/lly/Documents/ChatGPT/GeoChora v2.1.1/execution-output/V211_stage2_progress_report_20261104.md`。这些是工作区外于Core checkout的文件，特以原路径列出。attempt002原始H5、trace、失败记录与helper留在ignored `workspace/maintenance/v211_g02_2b_attempt002/`；不恢复、搬迁或覆盖旧运行。

## 阶段3前维护检查点

attempt001及维护者授权续作已返包，最终执行HEAD为`656ef136`。Sol独立复审决定`REWORK_REQUIRED_PRE_STAGE3`：保留部分实现作为后继基线，G1 FAIL、G2–G4 PARTIAL，整体未接受。目录四文件及原字节manifest迁移已核对；三个classic任务真实统一、Marker通用构造回收及F06任务／runtime职责分离仍待整改。最终源码物理与独立reader未验证。见[Sol复审](reviews/20261104_pre_stage3_attempt001_sol_review.md)和[执行者交付](reviews/pre-stage3-refactor-attempt001.md)。不改变阶段2决定或启动阶段3。

attempt002 的 30 分钟 R1 返工已记录在[返工交付](reviews/pre-stage3-refactor-attempt002.md)：scalar episode 部分状态与准入已共用，classic／selected 的完整生命周期和 Env 类仍未统一，RW1 为 FAIL；原生验证未运行，仍待 Sol 复审。

### 2026-11-05 生命周期续作

后续职责去向、原功能调用者及当前文档处置见[职责与文档清单](reviews/20261105_pre_stage3_owner_and_document_map.md)；该清单是待复审检查点，不表示整体维护已接受。

维护者授权更长的三个单环境修复，提交为 `4840152530e55fb8a3e77517c3b187e99647b5b7`。Sol 已作[独立复审](reviews/20261105_lifecycle_unification_sol_review.md)，决定 `ACCEPTED_BOUNDED_LIFECYCLE_UNIFICATION`：R1 的真实源码迁移与无引擎契约有限接收。四个 `BaseTaskEnv` 出口与 `SelectedReferenceEnv` 为同一类对象，三个组件任务及 selected 路线通过共同 episode owner 执行 reset、step、stop 和 close；组件 RuntimeBoundary 和 selected RuntimeSession 保持各自物理接口。Sol 独立复跑171 passed／3 deselected和12 passed；真实 provider、物理和独立物理 reader 未运行。整体维护仍为 PARTIAL，R2/R3等后续项和阶段3均未获本次整体验收。原[Terra 交付记录](reviews/20261105_lifecycle_unification_terra.md)及历史30分钟结果保留。

2026-11-05后续goal在上述复审之后继续实施，至 `f37dec92` 的源码与文档检查点均待Sol复审：Marker公共组装、F06受信声明、部分task／recorder职责、Nut cadence诊断隔离和R05b源码身份准入均有实现。PickCube普通CPU、Position/F06、内建与通用candidate的调用方动作接线已迁移；Position/F06新路线仅有合成证据，真实Isaac未运行。通用candidate合成oracle预检因两份保护untracked触发clean-check，尚未通过。完整记录及失败边界见[续作检查点](reviews/20261105_pre_stage3_continuation.md)。

当前待处理状态、资源上限违规及待维护者决定事项汇总在[待复审检查点](reviews/20261105_pre_stage3_pending_handoff.md)；该页不是最终返包或验收。

其后续作至 `8416ef49` 的源码与文档仍待Sol复审；当前逐门证据与未完成项见[验收门核对草稿](reviews/20261105_pre_stage3_gate_audit.md)。该草稿不是最终交付或Sol决定，后续源码变化须重新核对适用范围。

已有受限物理证据：`fa885280` 的Empty／Pendulum／TwoWheel GeoPhys CPU各单步与close；`f9cb51fd` 的PickCube MuJoCo CPU seed31调用方驱动回归及同H5独立reader。结果只对应各自源码，后续源码不自动继承这些物理结论。Nut完整物理回归与独立物理reader仍为NOT_RUN；原生步数预算问题已向维护者提出，尚待答复。整体维护仍为PARTIAL，阶段3未开始。

维护者计划后续从 develop 建立阶段3分支；目前尚未创建新分支或 worktree，也未启动3a。正式执行前固定起点提交、独立工作目录及与后续维护的接口边界；旧编排中的零新增分支方案届时按维护者新安排更新。

## 阶段3前待办

[维护方案](../planning/pre-stage3-environment-refactor.md)涵盖环境归整、诊断隔离、Env统一、静态SHA优化，以及新手安装／已有路径复用／启动脚本／example二次开发指引。交付位置包括README、`task_env/doc`和本版[指南](../guides/README.md)，不能只更新GPT工作文档。已有部分代码与启动入口检查点；完整重构、新安装及启动入口的 native 验证尚未完成。

Pendulum本次先完成单环境规范路线；统一Env并行尚未适配，交G06后续实施。旧并行注册／脚本及历史证据不改写，不因此要求本次追加并行native或训练检查。阶段3–7状态保持不变。

## 历史返工范围：30分钟

维护者已指定30分钟硬窗口。本轮只优先修复生命周期统一R1；Marker简化、F06职责整理及不受影响的文档诊断优化延期，不因这些事项继续延长窗口。见[规划优先级](../planning/pre-stage3-environment-refactor.md#24-维护者指定的30分钟返工优先级)。本轮无native／GPU／完整物理reader预算，现有物理证据边界不变；新包为`V211_PRE_STAGE3_REFACTOR_attempt002`，准备后由维护者转发，不自动启动或进入阶段3。

## 保护项和停止点

- `MUJOCO_LOG.TXT` SHA-256 `dfb37ada202855d609f9e210cf79b287de78f2ded70e704ceeb544d17bf7ad4b`。
- `docs/maintenance/20261030_runtime_route_diagnostic_handoff.md` SHA-256 `18cc56c7f0ffbcb947db4bd8725279489171efbee8f08b28603b79c47f509d61`。
- 两项保持untracked；不stage、不删锁文件、不清理raw。
- attempt001和attempt002窗口已释放；2026-11-05较长续作的实际完成和窗口释放以本次报告为准。不得干扰其他用户的原生运行。本项不授权新的三后端九格、2b attempt3、Isaac native或阶段3。

历史记录（002 返包时）：2026-11-06：3b 普通 attempt002 已返包、writer 已释放，等待 Sol 独立复审；技术结果 PARTIAL，原 N08 FAIL，ORACLE_REVIEW_REQUIRED。不要自动启动 attempt003 或 3c。具体证据、已知偏差与下一步见 [002 执行摘要](reviews/20261105_3b_attempt002_execution.md)。维护者提出的装配树通用重力补偿目前仅为[设计](../planning/gravity-compensation-assembly-tree.md)，不应误认为当前 Panda 有界实现已支持任意夹爪。
