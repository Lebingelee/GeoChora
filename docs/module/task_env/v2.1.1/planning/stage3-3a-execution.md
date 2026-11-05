# G03/3a：接手核对与首包实施安排

2026-11-05，Sol。历史准备状态：`PREPARED_NOT_DISPATCHED`。当前 attempt001 已执行并待 Sol 独立复审，见[执行摘要](../maintenance/reviews/20261105_3a_attempt001_execution.md)。本页记录3a实施落点与首包准备历史；阶段出口仍以[Goal03](../goals/03-backends.md#3a)、[执行表](execution-and-acceptance.md)及已确认五协议为准。attempt001已实施且需返工，没有3a接收结论。

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

## attempt001独立复审与attempt002安排

当前以[Sol复审](../maintenance/reviews/20261105_3a_attempt001_sol_review.md)及[编排索引](../maintenance/orchestration.json)为准：3a为REWORK_REQUIRED_3A／attempt1；上文未派发／attempt0文字保留为首包准备历史。输出32397283继续作为实现基线，先提交此次复审／规划文档，再冻结attempt002准确输入HEAD。

attempt002只修R1普通source闭包／reset回归、R2逐能力准确build oracle、R3嵌套具名／typed评估、R4worker错误回复清理，并补齐原20项门。定向枚举真实source引用、读取摘要及必要的小型快照属于闭包实施，不属于禁止的全库扫描；沿现有source receipt和importer消费者接线，不移植另一个资产平台。保留严格拒绝且恢复合法ordinary caller；成功路径不得绕过闭包。metadata unavailable必须如实报告，缺GeoPhys环境或Isaac SDK不要求本包安装或运行native。

同一分支，预计主动120–150分钟／墙时180分钟，其他资源限额同首包；一个writer、一个测试组，原始失败不可覆盖。新包含全部输入、方法、正负例、预算、报告和释放要求，由维护者指定后人工转发；准备不增加attempt计数。3a接收后才准备3b；新增Isaac兼容范围按[独立规划](isaac-deployment-compatibility.md)接入3b完整包，不倒加本次原门，不在返工窗口提前实施。
