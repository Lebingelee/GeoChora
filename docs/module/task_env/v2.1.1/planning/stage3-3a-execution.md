# G03/3a：接手核对与首包实施安排

2026-11-05，Sol。历史准备状态：`PREPARED_NOT_DISPATCHED`。当前attempt003整体未获Sol接收、已到三次上限，须维护者人工诊断；002核心恢复保留。首包与返工安排均保留为历史，实时结论见末节独立复审。原执行摘要见[执行摘要](../maintenance/reviews/20261105_3a_attempt001_execution.md)。本页记录3a实施落点与首包准备历史；阶段出口仍以[Goal03](../goals/03-backends.md#3a)、[执行表](execution-and-acceptance.md)及已确认五协议为准。attempt001已实施且需返工，没有3a接收结论。

## 接手与分支

已完整阅读外部交接README，并按其必读清单核对当前文件和input-snapshot：Core为`develop@9d942d43a1cf3210d5bccca0f703c1be4ba45654`，tracked clean，仅两个原保护untracked，内容摘要及GeoPhys／Menagerie gitlink和checkout均一致。已只读核对现有G03对话仅收到等待指令、旧前置Terra最终返包明确释放writer与native窗口；没有新的3a包、活动writer或G03结果。对话状态只是辅助，未来开工仍重验输入与writer。

按阶段分支策略已fetch public/develop，得到`fd03817c9f6ef8ce9fd68c1db30125efda68e1c8`；本地develop领先236、落后0。保留所有本地进展，从9d942d43建立`codex/v211-stage3`，3a–3c共用当前checkout；新增分支1、worktree0。未reset/rebase、未推送或合并。develop停留原交接HEAD。本次仅写接手／规划文档，准确派包输入HEAD在外部包snapshot于本次文档提交后冻结，不循环修改当前索引来填入自身commit。

前置边界保持：G02为[ACCEPTED_BOUNDED_STAGE2_REFERENCE](../maintenance/reviews/20261104_2c_sol_review.md)，生命周期R1及限定C1/C2/V[核心收尾](../maintenance/reviews/20261105_pre_stage3_closeout_120min_sol_review.md)已接收。不重开2b、seed32或旧前置维护。已有PickCube／Nut成功按原source/run身份引用；真实R05b新caller、Isaac、新安装、RGB、并行、D0及Qualification未因接手通过。

## 当前源码与实施单元

已按AGENTS先用CodeGraph；索引对config、contracts、session API等漂移，随后只读当前源码，不重建索引。现有public factory确实调用共同配置owner，但尚无完整分层selection/assessment与依赖隔离：

| 单元 | 当前owner／实际调用点 | 3a修改方向 |
| --- | --- | --- |
| 配置解析 | `registry.make_env` → `environment.configuration.resolve_task_env_config`，selected由`_resolve_selected_config`归一；generic由`resolve_execution_plan`产生v0计划 | 同一配置owner归一host/engine/solver/coupler/device/renderer/batch，保留旧alias与优先级，拒绝未知层级／冲突；不复制parser |
| 值与codec | `environment.config`的ResolvedEnvConfig／ResolvedSelectedConfig／ExecutionPlan；`artifacts.contracts`的ExecutionSpec/v1、decode_execution_spec、RequiredCapabilitySet、ProviderCapabilityManifest/admit_capabilities | 原owner最小版本化扩展；旧v0/v1、Scene/Artifact/Timebase exact codec/hash不改；新assessment分provider API、adapter、依赖、证据 |
| 准入与构造 | `SelectedReferenceEnv.from_resolved_config/_prepare_reference_reset`，`reference_binding.resolve_reset_execution/prepare_selected_reset`；任务specialization形成binding；`runtime.sessions.api.materialize/_materialize_admitted`和`control.materialize_control/compile_control_binding_plan`消费 | 需求求交接入正常factory/materialize链；静态拒绝在close/write前；保留source、Controller、feedback及精确Isaac准入，不借清特判扩权 |
| 环境与来源 | `runtime.sessions.provenance.provider_build_identity/provider_module_origins`；现有路径、launcher与bootstrap；`vectorization.parallel._remote_worker`只是同构batch worker | 约束解析、指定解释器元数据／origin核验、正常runtime的薄环境路由；如需transport仍转发原session。现有batch wrapper不能替代跨解释器scalar session |
| 配置和拒绝回执 | `recorders.reference_provenance.recorded_execution_configuration`、Env现有info/get_record_metadata与Recorder | 同一resolved/assessment值可查询和序列化读回；requested/resolved与尚未知的native-effective分清，不另建Recorder |

分类为EXTEND_EXISTING／COMPOSE_EXISTING。task/source/Controller、state/model、嵌套具名通道、typed命令与render/batch需求须按实际声明求交；尚未实现的effort、嵌套新表示、RGB或batch明确拒绝／标缺口，不在3a提前实施阶段4–6。Controller不绑定live SDK、不增加第二physics step。

首批仍是MuJoCo CPU、GeoPhys CPU、Isaac Sim＋PhysX CUDA的冻结交集；其他host/solver可表达不等于实现。当前selected普通路线state-only，R3为位置compatibility；Panda8输入→7臂torque＋2指力及JointEffort/BodyWrench在阶段4实现，不能照旧7＋1 closure提案施工。

## 依赖、时间与证据分期

Core要求MuJoCo >=3.8.1,<3.9.0，GeoPhys要求>=3.15.0，没有同环境交集。本包须有被正常runtime消费的环境选择／隔离接线，不能只有纸面worker方案；默认评估Core/MuJoCo、GeoPhys、Isaac独立解释器／SDK，复用现有路径和清理约定。缺真实依赖如实unavailable，允许在无native测试中验证metadata/dispatch/transport契约；实际构建与读回留3b。缺pip geophys distribution不否认当前pin源码，旧checkout源码不能用于验证当前Core。

不安装、下载或升级依赖，不改requirements或provider pins。metadata只查指定解释器和当前源码origin，不import/init native。可静态拒绝的required项先拒绝；只有准确adapter与build oracle存在时才pending_native_build，不能把pending当ready或将用户manifest当扩权凭据。

PickCube/Nut现有task physics_dt=0.002s、control_substeps=5、control/obs cadence=0.01s保持；不同native dt请求若无版本化映射就拒绝，不静默改旧身份。本包不实施完整3c sampler/generation/A→B→A，也不把preflight哨兵测试当作3c接收。

## 完整包与验收组织

外部人工交接包为`V211_G03_3a_attempt001`，位于主工作区handoffs。包含完整prompt、输入snapshot、manifest/sidecar、20项planning acceptance cases、只读verify脚本和既有offline guard副本。snapshot冻结本次文档提交后的实际HEAD、保护字节／pins、必读资料和直接相关源码；manifest冻结全部成员。维护者尚未指定Terra／Luna执行对话；不自动发送包或启动subagent。

完整门按Goal03/3a细化为：A配置与旧codec/hash兼容；B多维能力交集及拒绝；C依赖隔离/实际路由；D查询和既有记录回执；E无副作用及受影响回归；F文档、提交与完整返包。具体输入/oracle在包内cases，不另造阶段标准。

复用`test_selected_api_configuration_and_identity.py`、C01a execution_plan、C01b dynamic_admission、D05a execution_contracts及受影响时的R05b无引擎node。新测试针对生产consumer和真实缺口，使用外部fixture/guard；不镜像实现自证，不跑宽矩阵。依赖metadata/transport fake只算离线契约，不算physics。文档validator和diff-check必须通过；旧历史链接问题单列。

预估主动120–150分钟，180分钟总墙时硬上限，含等待、文档、提交和返包；145分钟收敛、165分钟后不启新实现。单测试组15分钟，测试/metadata累计60分钟；单进程树及并发总RSS8GiB，输出256MiB、单日志16MiB；同一时间一个测试组，metadata单次30秒。native/physics/GPU/render/window/训练均0，不获取或探测native双锁。不能继承旧维护两小时、300000步或旧Isaac预算。到时返包，不用补报告/资源账本作加时理由。

输出复用ignored `workspace/maintenance/v211_g03_3a_attempt001/`，一份report及commands/results/output-manifest；跟踪一份短执行摘要。只提交本包路径，保护untracked和旧raw不动。attempt开始才记3a attempt1；本次准备仍attempt0。一次失败测试可在窗口内修复，不自动另算attempt；普通子阶段上限3，第三次前按原规则重新评估。

## 诊断与推进边界

遵循[诊断规范](../../../../global/diagnostics-and-code-boundaries.md)：诊断从外部消费核心，核心不感知实验／测试case；正式feedback、source、fault、stale/tamper、target/applied与close继续保留。既存耦合按[维护规划2.6](pre-stage3-environment-refactor.md#diagnostic-policy-and-final-cleanup)登记，7a开始时集中合理解耦，随后稳定源码验证，不现在重开全面整理。

本次Sol接手仅做文档和包一致性检查：未运行implementation tests、provider import、native、reader、GPU/resource probe。3a未派发，3b/3c未准备；完整报告与writer释放后Sol独立核对diff和证据，接收后才准备下一包。阶段3最终汇总三项独立接收与真实覆盖，等待维护者安排，不自动进入阶段4。

<a id="attempt002-runtime-first"></a>
## attempt002 revision 2：真实运行优先

维护者于2026-11-05明确要求先解决核心矛盾、舍弃大量无用安全／边界核查及旧路线重复验收。未派发revision 1已封存；本revision替换其native=0及全20case重验要求，仍为attempt002，当前attempt_count=1，不自动派发。

首要硬门：明确允许读取PickCube／Nut实际MJCF引用的mesh、texture及其他依赖，修现有source→reset/preflight→materialize/importer接线。执行者经make_env分别以PickCube31、Nut19在真实MuJoCo CPU上创建、reset、连续10个公开control step、读取有限state/obs/reward并close，记录时间与control_step推进。不能用fake、绕过闭包或拒绝负例数量抵消失败。必要时删除／合并重复预检，沿原消费owner处理真实映射／文件错误，不强制新快照／能力注册表或通用oracle框架。

优先R1及合法路线实际涉及的R2/R3映射；R4只修已复现的错误回复与回收。20case只是阶段需求追踪，旧证据未受影响直接REUSED，不重跑108项、旧维护组、codec oracle或全能力／消息边界矩阵；历史合同／报告不重读。原3a尚未覆盖项如实报告给Sol，不把本次核心恢复冒充整阶段接收，也不让其挤掉核心修改与真实运行。G02及前置有限接收不重开。

预计主动90–120分钟、总墙时180分钟；先核对直接输入，最迟第60分钟开始第一次真实构建尝试并在窗口内修复。仅执行者在维护者手动转发后可运行MuJoCo CPU，原生累计30分钟／2000物理步（含失败／reset／settle），全部验证累计60分钟、单组15分钟；RSS8GiB、输出256MiB。仅原生期间沿既有双锁串行，GPU/render/App/GeoPhys原生0，禁止下载／安装。Sol准备中native仍0。三后端完整验证与Isaac6.1/6.2兼容仍在3b，未启动3b。

原revision 1完整包保留于主工作区handoffs/archive/V211_G03_3a_attempt002_r1_20261105；当前根目录prompt、snapshot和manifest冻结本revision的输入及预算。一个writer、本地明确路径提交、报告真实运行结果与剩余项后释放，维护者手动交Sol复审。准备不增加attempt计数。

## attempt002独立复审后：只收口剩余3a

本轮实现42dfcda5经[Sol复审](../maintenance/reviews/20261105_3a_attempt002_sol_review.md)有界接收为ACCEPTED_BOUNDED_3A_CORE_RUNTIME_RECOVERY。两任务真实MuJoCo CPU公开创建/reset/10步/close已通过；Sol仅独立5项相关离线检查，不再启动原生。上节runtime-first为已完成窗口的安排，不能继续派发原attempt002。

3a整体仍PARTIAL_CORE_RUNTIME_RECOVERED、已执行2次。剩余按实际声明求交和已有adapter的具体构建检查点做有界评估，先复用原owner／已过证据，不造oracle框架、不铺开全对象边界矩阵；最后003完整包准备见末节，尚未执行。第三次前遵循既定根因／可行性重评，只研究实际未决问题。GeoPhys/Isaac原生、物性及完整三路线验证交3b，不倒加为3a提前运行门。已接收的MuJoCo核心恢复在代码未受影响时直接引用。旧G02／前置维护不重开。

## attempt003前重评与最后窗口

维护者再次明确三次上限：003是最后一次普通窗口，若整体3a未接收则必须停止普通执行并进行人工诊断，不自动第四次。已完成[本次重评与调度](stage3-3a-attempt003-reassessment.md)：比较两次实际窗口、原协议和当前生产owner，记录官方／开源对照，选择实际需求汇总→准确adapter构建检查→同一回执的一次整体收口。不将已解决reset重做，也不在3a提前实施4a或3b物理矩阵。

003完整包现已按重评固定，见下节；尚未指定执行者／派发，attempt_count保持2。准确输入在本次准备文档提交后的外部snapshot冻结；本页准备不授权Sol运行native。


<a id="attempt003-complete-package"></a>
## attempt003完整包：最后窗口，准备完成待维护者转发

完整包为主工作区handoffs/V211_G03_3a_attempt003；当前PREPARED_NOT_DISPATCHED，一个执行者待维护者指定，active_packages为空，3a仍PARTIAL_CORE_RUNTIME_RECOVERED／attempt_count=2。沿当前阶段分支与checkout，不创建分支／worktree。实际实现基线42dfcda5；准确input HEAD在本次Sol文档提交后的外部snapshot冻结，不回退到实现提交。input verifier一次核对后，实际开工才登记第三次。

固定的实现单元是：api.assess_selected_request汇总实际Artifact/source、ControllerBindingV1.feedback_requirements／ControlBindingPlan、已有Scene具名通道及StateRequirements，复用logical assembly resolver；CapabilityAssessment原owner替换通用constructor名字放行逻辑；MuJoCo实际model映射、GeoPhys公开boundary映射、Isaac原USD／DOF检查由各adapter构建消费；同一request关联的静态assessment及后续有界检查事实经原环境查询/info和Recorder metadata读回。静态能判定直接判定，需要原生的项有准确检查才pending，无检查则拒绝；不因layout匹配升级物性或Qualification。不设计新框架或新typed/nested语言。

原20case全部追踪，实际验证只补六组：现有声明正负consumer、具体build helper真实消费、三route共同selection/admission及准确unavailable、同一metadata JSON/H5读回、受影响MuJoCo主路回归、完整3a返包。GeoPhys依赖冲突和Isaac SDK缺失如实拒绝，SDK终端fixture只证明离线接线，不能绕过source/assessment/helper。已有F06身份／证据直接引用，真实三后端运行和物性仍是3b，typed执行仍是4a/4b。旧codec／worker／历史大组不受影响就复用。

预计主动90–120分钟、总墙时180分钟含等待／文档／提交／返包；0–10分钟一次核对和方法阅读，10–70分钟核心接线，70–120分钟聚焦验证与必要CPU回归，120–150分钟实际失败修复，150–180分钟终验及交付。验证累计60分钟，单组15分钟；仅受影响MuJoCo CPU累计30分钟／2000原生substeps，含reset/settle/失败重试，同窗口允许多次修复。RSS8GiB、输出256MiB／单日志16MiB；不安装下载，GPU/Isaac App/GeoPhys native/render均0。CPU仅实际运行期间按既有双锁串行，Sol准备native0。

若改变MuJoCo构建/reset/admission（预计如此），稳定源码上以公开factory、原Solution和真实MuJoCo3.8.1 CPU对PickCube31／Nut19各reset+10step+close，有限值与0.10秒推进；否则按真实调用链理由复用002，不重跑完整task-success或物理reader。结果按整个3a出口交Sol独立审阅，不再以局部CORE_PASS作为完成。

003是最后一次普通attempt，窗口结束未完成就停止；若Sol复审后整体仍未接收，必须维护者主导人工诊断，无attempt004、换名续包、关闭后续003或自动诊断对话。技术结果保持REPORTED_PENDING_SOL_REVIEW；通过也只解锁3b下一包准备。输出为新ignored目录workspace/maintenance/v211_g03_3a_attempt003及一份短执行摘要，保留旧证据原字节、保护untracked和子模块pins，不推送／合并。


## attempt003复审后：停止普通执行，等待人工诊断

执行输出3d10b357经[Sol独立复审](../maintenance/reviews/20261105_3a_attempt003_sol_review.md)决定NOT_ACCEPTED_3A_HUMAN_DIAGNOSIS_REQUIRED。两任务及worker的真实MuJoCo短程与metadata事实保留，Sol独立5项离线通过；主要未决仅F06真实来源预检边界、versioned/nested完整selected生产consumer证据。当前3a状态HUMAN_DIAGNOSIS_REQUIRED／attempt_count=3，active_packages为空，无普通候选；上节完整包准备和预算是已结束的冻结历史，不继续派发。维护者主导人工诊断并决定后续授权前，不再实施、补验证或自动第四次；3b/3c仍PLANNED。
