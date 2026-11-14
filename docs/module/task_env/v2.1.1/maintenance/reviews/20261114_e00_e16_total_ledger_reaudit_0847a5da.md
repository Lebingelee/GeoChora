# E00～E16 总账逐项复审

2026-11-14，审查输入 `0847a5dad3d1c154f8380ccc5118631a4e56d1a0`，分支 `codex/v211-stage5-diagnostic`。依据[原始60项总账](../../planning/post-5c-code-project-optimization-diagnostic-ledger.md)，结合当前磁盘源码、调用关系、变更影响、现行检查及清理后的原始对象复审。原始总账是受保护的 untracked 输入，本次没有修改或加入 Git。

**结论：生产构建、控制、adapter、记录及本轮批准的项目清理可以维持既有有界接收；“60项全部无余项关闭”目前不准确。57项满足原约定的有界出口，3项（GOV-04、DOC-01、DOC-02）存在同一组当前状态／Skill同步欠账。没有发现必须重开底层重构或重跑完整 native 矩阵的新阻断。** 这些资料欠账应集中结束；本报告不撤销维护者已经作出的接收，也不代替新的维护者决定。

本次没有修改生产代码、旧证据、refs、worktree、保护输入或 pins，没有启动 SDK/native。独立复审仍复用原审查与受测身份，未声称重新逐行证明全部引擎实现或所有历史运行。方法沿用 `evidence-driven-delivery`：将实现、证据覆盖和批准例外分开。

## 1. 需要结束的具体缺口

### F1：机器编排入口仍向接手者派发已经完成的工作（P2）

[orchestration.json](../orchestration.json)第4行顶层 `status` 为 `POST_5C_E11_E16_IMPLEMENTATION_IN_PROGRESS`，第25行 `next_action` 仍要求完成 stage／snapshot 补集分类清理、取得项目接收，并遵循 `e3f13d72` 旧主审 R1～R4。可是同文件 `post_5c_optimization.status` 已为 `E00_E16_MAINTAINER_ACCEPTED_BOUNDED`，`next_step` 已说本轮关闭、G06另行启动；[维护者接收记录](20261114_e11_e16_maintainer_project_acceptance.md)也明确接收 `86921c62`。

这不是带日期的历史 attempt 字段，而是现行顶层状态和下一行动。读取顶层的恢复者仍可能重开已清理范围。因此 GOV-04、DOC-01 尚有资料出口欠账。修复仅需统一顶层状态、下一行动及其有效接收引用；保留各历史 attempt 的原结论，不将 v2.1.1 整体或 G06/G07写成完成。

### F2：可发现 Skill 的现行操作指令落后于项目接收（P2）

[TaskEnv Skill](../../../../../../.agents/skills/geochora-task-env/SKILL.md)第18行仍要求 “Proceed with U5 evidence preservation and independent recomputation”，并把 separate project acceptance 当成后续动作。第12行虽有11月13日 checkpoint 日期，但这是当前可发现 Skill 内的操作指令，没有标成已被11月14日接收取代的历史提示。[诊断索引](../../../../../../task_env/diagnostics/tasks/v2.1.1/README.md)第3行也仍称 “in-progress U1 inventory”。当前源码和批准清理已走到 U7，新的接手者不应依赖自行推断来消除这些指令冲突。

DOC-02 尚需同步：Skill 当前检查点转到维护者接收记录；旧 U5/U6/U7 说明明确为历史流程；诊断索引表述为当前选点／输入分类，不再冒称 U1 正在实施。Skill 中早期 capability plan 的 `NOT_RUN` 说明应明确指历史规划字段，与当前 `current_support` 分开。此处不要求修改历史 F06、A123或资格记录。

### 一次资料收尾的建议范围

1. 对齐 `orchestration.json` 顶层和优化节点，保留“G06需另行启动”。
2. 同步 TaskEnv Skill 与诊断索引的当前状态，保留历史命令的版本和限制；引用最终接收／归并入口。
3. 定向核对三入口的状态与链接，运行现有文档／Skill检查；压缩一份结果并本地提交。无需 native，也无需重新清理任何目录。validator 的既有保护文件期望差异及历史链接问题继续披露，不改保护原件求全绿。

本次只交付复审，不执行上述修订。F1/F2是两个具体资料问题，映射到三个原账目，不能解释成三个新运行 bug。

## 2. 当前生产调用关系与可读性

| 边界 | 当前实际调用和归属 | 审查判断 |
| --- | --- | --- |
| 正式入口 | `registry.make_env → SelectedReferenceEnv.from_resolved_config → resolve_task_env_config → _build_selected_binding → ReferenceTaskBinding.build_for_request` | 四正式任务都声明 `uses_selected_public_config`，进入共同入口；选中配置在resolver解析。保留的范围外component/legacy factory不定义这四任务的构造协议。 |
| 共同构造 | `TaskBuildRequest → SourceBoundTaskBuilder.__call__`，依次消费 `compile_source / source_composer / controller_factory / compile_control / reset_plan` | 真实调用共同阶段，超过共同类名或运行后视图。Task context不被塞入Runtime结果；Runtime／Task字段冲突会拒绝并清理source。 |
| 四类主体 | PickCube通过`build_panda_reference_stages`；Nut通过`_reference_builder`；Pendulum、双轮通过`ExistingSubjectEffortTask.bind`；均实例化同一builder | Panda与简单主体允许不同lowerer；简单主体recipe明确引用既有实体，不伪造gripper或ee。 |
| source与adapter | `ReferenceTaskDeclarationV1`声明语义映射；`prepare_robot_source_intent`冻结请求；MJCFcomposer／USD admission交付source与映射 | compiler不再按PickCube／Panda UID拼源；具体Panda资产配方留资产owner。实验变体生成退出通用fixed attachment；冻结变体的逆向语义校验仍是合法准入。 |
| reset／故障／close | Env协调reset事务；binding reconstruction、RuntimeBuilder、typed initializer及session各执行自身阶段；`EpisodeExecutionState`协调故障和关闭 | 保留预检失败的RNG回滚、失败Runtime owner保留、source lease清理和首错／次错。borrowed camera不取得第二物理owner。 |
| 动作与推进 | `step / step_with_solution / step_expert → prepare_selected_control_action → submit_control_command → typed lowerer / session interval` | Position、effort、wrench保留不同单位和lowering；场景interval统一提交。兼容Solution共用`_prepare_solution_action`；标准caller继续`act → env.step → observe`。 |
| observation／相机 | Robot提供主体projection，Task提供物体及任务metadata；共同schema校验；camera adapter声明需求并消费同一boundary | `CameraSpec`在Artifact编译后绑定。Env不再配置RTX／推断颜色；Isaac task与observer的请求及局部fault分开。 |
| Recorder／回放 | 普通v3按T/T+1和记录合同；历史leaf codec解码；精确Judge在版本diagnostics；inspect与重执行分开 | 当前公开reader可读五条完整记录；completion缺字段的已批准联合证据不伪装成H5自含。历史重执行仍严格检查源码身份。 |
| worker／锁 | 正式监督器隔离cwd和依赖，传递flock FD；isolated transport继承锁及父死亡处理；App在USD编译前准备 | 最终生产树与`3e77f6e0`的相关源码无差异；三条已受测短程可按原身份复用，不能替代完整Solution或保证所有不可见进程。 |

源码已减轻公共层和Task负担，但还存在明确阅读成本：Env 4,277行，`_prepare_reference_reset` 592行、`_prepare_reference_step` 322行，`build_panda_reference_stages` 213行且参数较多，阶段交接仍使用部分mapping和固定位置tuple。这些不是本次新增的功能缺陷，也没有证据要求另建Manager或全面拆类；后续能力扩展应沿现有owner处理具体问题，不能将本次接收宣传为“彻底精简”。

## 3. 60项逐项结案核对

`PASS_BOUNDED`仅表示原账目在既定任务／能力／证据范围内成立，保留本报告第6节中的已批准例外；`PARTIAL_DOC`表示生产或操作成果成立，但现行资料出口未齐。没有将任何条目自行改成N/A。A/B/C及P分别指第4节的纯合同、真实路线、完整运行和项目取证。

| ID | 当前owner／生产符号 | 实现、实际caller与保留理由 | 证据／本次判断 |
| --- | --- | --- | --- |
| GOV-01 | `registry.make_env`、configuration、`SourceBoundTaskBuilder` | 四正式UID使用共同请求；candidate退休，能力由正式owner消费；无新增任务Env。 | A配置、B/C正式caller；PASS_BOUNDED |
| GOV-02 | current-state、任务binding、各adapter | 构造／控制／状态可追到方法；设计、受测交集和资格分开，未以测试数量替代架构。 | 本报告调用表、B/C身份关联；PASS_BOUNDED |
| GOV-03 | roadmap、current-state、总账与分事件账本 | 本次停门位于5c后／G06前；G07保留后续批量与最终版本收口，不借旧延期跳过优化。 | 当前导航及维护者接收；PASS_BOUNDED |
| GOV-04 | current-state／orchestration | README能恢复到当前摘要，但编排顶层与优化节点冲突；不能称唯一现行状态已全同步。 | F1；PARTIAL_DOC |
| ENTRY-01 | `make_env → from_resolved_config` | 四正式类同协议；惰性注册无SDK启动；范围外component合同显式保留，构造失败清理自有资源。 | A配置、B正式纵切、C五路线；PASS_BOUNDED |
| ENTRY-02 | `resolve_task_env_config / _resolve_selected_config` | mapping/YAML同语义；字段优先级、未知字段与冲突拒绝保留；旧component codec不再冒充四任务协议。 | A配置、原真实source构建节点及关联；PASS_BOUNDED |
| ENTRY-03 | `CameraSpec → CameraGeometry.from_camera_spec` | 编译后绑定Artifact，用户不手写hash；高级外来Artifact仍拒绝。 | A相机／foreign identity、B真实RGB；PASS_BOUNDED |
| TASK-01 | PickCube Task、Robot、Controller、source／render owner | 两旧physical candidate及Position旧入口退休；正式PickCube消费原有效能力，不是整体改名搬家。 | A旧入口与B/C正式PickCube；PASS_BOUNDED |
| TASK-02 | PickCube `make_reference_binding`及任务回调 | Task准备物体、readiness、reset／评价；source编译和Controller交付在adapter／共同builder。 | 调用表、原S27身份检查、C；PASS_BOUNDED |
| TASK-03 | Nut Solution、`planners.completion`、canonical feedback | 通用guard／interval解析归公共owner；Nut阶段、2ms cadence及严格策略保留。 | A任务owner及guard；C Nut两路线；PASS_BOUNDED |
| TASK-04 | 简单Task、Robot recipe、`ExistingSubjectEffortTask.bind` | `references_existing`进入共同source／受控主体合同；任务奖励和reset保留；未支持的正式batch提前拒绝。 | A主体／batch、B两简单主体；PASS_BOUNDED |
| ENV-01 | `SelectedReferenceEnv`、binding、lifecycle | 正式构建消费已解析binding；旧候选bool接线退出，不再复制第二生命周期；component按其旧范围保留。 | A构造／lifecycle、B/C；PASS_BOUNDED |
| ENV-02 | reset reconstruction、materialization、initial state | source-bound reset、publication、Controller初始化和RGB按阶段协调；Panda/native决定归相应owner。 | A reset失败、B二次reset及C；PASS_BOUNDED |
| ENV-03 | `prepare_selected_control_action / submit_control_command` | 普通action、ExpertAction和受支持兼容Solution汇入共同提交；拒绝与副作用后fault有区分。 | A无副作用／fault、C外部Solution；PASS_BOUNDED |
| ENV-04 | `observations.selected_reference`、Robot／Task projection | space、schema、数组相互校验；Panda字段由显式Robot提供，metadata不再被通用Recorder改成PickCube。 | A observation/metadata、当前H5读回；PASS_BOUNDED |
| ENV-05 | `EpisodeExecutionState`、session/App/source/camera owner | 重复close、半构建和失败reset资源按owner释放，保留首错及cleanup次错；App日志限制未抹除。 | A资源失败、B/C关闭收据；PASS_BOUNDED |
| SUBJ-01 | `RobotRuntime.from_selected`、`ControlledSubjectV1` | gripper/ee为可选能力；实际主体和Controller可查询，Pendulum无需Panda假字段。旧Frame facade限名不等于通用主体只支持三Frame。 | A四主体声明、B正式构建；PASS_BOUNDED |
| SUBJ-02 | Robot source recipe、composition intent、provider composer | recipe给本体／传动，Task给物体和替换意图；provider核验最终映射和writer，Robot不加载SDK物化。 | B一体／装配Panda及C；PASS_BOUNDED |
| SUBJ-03 | logical assembly、source projection、physical subject | 根、嵌套、父子与writer独立于控制动作种类；不把logical nesting冒充native约束。 | A主体映射；B装配／简单主体；PASS_BOUNDED |
| CTRL-01 | controller matching、Scene resource、provider admission | 语义通道→Scene资源→native DOF／actuator分层；保留tendon与重叠拒绝。 | A映射、资源冲突及B真实路线；PASS_BOUNDED |
| CTRL-02 | scene interval、`submit_control_command` | 单提交／推进owner；Position、effort、BodyWrench不同lowering，显式求和、去重和partial-write fault保留。 | A物理合同；B原混合／双writer；PASS_BOUNDED |
| CTRL-03 | `DefaultCanonicalController.bind / bind_many` | 默认对象绑定source和单位后工作；Task显式R1/R3不被替换，不要求Python Robot token。 | A声明／单位、B四主体；PASS_BOUNDED |
| CTRL-04 | model requirement、动态模型、MuJoCo capability | 补偿默认关闭；受限开启态依赖实际模型匹配，不推广到任意provider或冻结质量模型。 | 原受测开启态按diff复用、A拒绝；PASS_BOUNDED |
| CTRL-05 | timebase、typed sequence、session interval | 外部action一次接收，tick／physics substep分开；开环序列不冒充通用闭环，stale及generation保护保留。 | A序列／clock、B/C原始计数；PASS_BOUNDED |
| SRC-01 | assembly compiler、TabletopSceneBuilder、Robot资产适配 | compiler消费显式scene composer，不含按empty/Panda UID补场景的旧分支。 | 实际源码与原构建节点关联；PASS_BOUNDED |
| SRC-02 | `SourceCompositionIntentV1 / RequestV2`及source adapters | Task提交物体映射，注册不按PickCube命名；reference/replace按能力工作，未实现add不伪报支持。 | A请求合同、B正式source、C；PASS_BOUNDED |
| SRC-03 | 通用fixed attachment、`panda_source_profiles`、版本diagnostics | 实验变体生成外置；冻结历史变体SHA和逆向语义校验留资产准入是合法职责，不能因函数含R06就删除。 | source caller及实验／准入分类；PASS_BOUNDED |
| SRC-04 | `RuntimeSource / UsdRuntimeSourceV1`、snapshot lease | MJCF/USD表示分开，closure／Artifact／Scene身份与资源lifetime保留，不让USD假装MJCF。 | A stale/lease、B两表示、P source对象；PASS_BOUNDED |
| RUN-01 | Runtime API、USD／MJCF admission owner | 公共协议／分派与冻结资产准入分开，实验context退出；精确manifest/profile限制保留。 | 源码与A精确输入准入、B；PASS_BOUNDED |
| RUN-02 | `runtime.provider_bootstrap`、旧component boundary | GeoPhys走公开init/assembly，旧component／纯构建caller范围明确；四正式batch并未假装完成G06。 | A bootstrap/batch、B/C GeoPhys；PASS_BOUNDED |
| RUN-03 | MuJoCo／GeoPhys／Isaac session adapters | adapter拥有native load、映射、reset、typed write、advance、snapshot、close，不计算Task奖励或第二Controller。 | B/C三个provider，计数及ACK边界；PASS_BOUNDED |
| RUN-04 | transport、worker、App owner、正式Harness | Task不复制worker；cwd、依赖和App准备回真实owner；锁FD跨隔离worker保留，不以强退冒充正常close。 | A 52项定向检查；B最终三短程；PASS_BOUNDED |
| REN-01 | render registry、`TaskRgbCapability`与实际factory | 显示与task sampling接口可不同，task能力被实际factory消费；合法pair可查询，无静默替换。 | A能力／factory与B RGB；PASS_BOUNDED |
| REN-02 | `render.camera.task_rgb`及native／visual adapters | borrowed与independent资源分工实际生效；Env只编排，不再设置RTX、颜色、设备细节。 | A factory／资源；B native/cross；PASS_BOUNDED |
| REN-03 | renderer state requirements、typed publication | renderer与Controller视图分开、同boundary/clock；格式限制留对应adapter，不为RGB另推进物理。 | A stale／publication隔离、B非Position及cross；PASS_BOUNDED |
| REN-04 | Isaac task sensor、observer、App lease | task request／fault局部独立，共用采集工具而不依赖伪造observer；headless、二次reset与关闭按原证据保全。 | A fake隔离、B原Isaac RGB及腕部对照；PASS_BOUNDED |
| REN-05 | MuJoCo visual session、GeoPhys camera | renderer-only消费公开状态；GeoPhys设置且读回FOV/near/far，灯光支持范围显式保留。 | 源码无第二mj_step；B光学读回／cross；PASS_BOUNDED |
| REN-06 | UI provider、camera capture／presentation | 窗口、离屏、task camera分开；借用窗口关闭不取得physics所有权；只复用受支持交集。 | A fake窗口独立；B历史5b及受影响UI；PASS_BOUNDED |
| REN-07 | renderer capability、color policy、completion | dtype/layout/range、transfer限制、CPU copy和owned/borrowed由adapter给出，未校准项不虚构。 | A输出／ownership与B原帧；PASS_BOUNDED |
| REN-08 | `InteractiveCameraController`及UI输入adapter | 通用相机数学不顶层import Taichi；具体输入常量由UI调用时提供。 | 当前源码及A纯import／输入检查；PASS_BOUNDED |
| OBS-01 | Robot observation、Task object projection | 公共selected投影不默认九关节／Panda arm-hand路径；兼容alias由显式owner选择。 | A schema／空间；B四任务；PASS_BOUNDED |
| OBS-02 | CameraSpec、canonical geometry、capture | 普通声明延迟绑定，space/schema/实际值闭合；新增腕部挂载仅限已测Isaac，不扩大其他renderer。 | A几何／schema，B原光学和Isaac腕部；PASS_BOUNDED |
| REC-01 | normal v3、legacy codec、外部严格Judge | 普通T/T+1不受64/65实验限制；旧leaf解码与原严格oracle分层；不放宽旧Judge。 | A离线25＋8；C当前reader五条、T19边界；PASS_BOUNDED |
| REC-02 | reference provenance、source snapshot cache | 既有episode静态缓存保留，动态边界仍生成身份；未凭无测量热点新增跨reset缓存。 | 原source读取计数按相关diff复用；PASS_BOUNDED |
| REC-03 | `inspect_selected_replay / reexecute_selected` | inspect不构造Env；重执行严格核source/adapter身份，拒绝不支持版本；不替换旧SHA。 | A拒绝／原同源码短重执行；C仅只读；PASS_BOUNDED |
| CALL-01 | examples、CLI、caller-owned Solution | 用户正式配置→make_env；退休builder不再是入门路径；显式backend失败不重试为别的能力。 | A caller/backend/completion、C五完整路线；PASS_BOUNDED |
| CALL-02 | vector factory、SB3／learner、batch lifecycle | 四正式UID未支持batch在worker前拒绝；旧component纯构建、space/autoreset/terminal语义保留。 | A batch/learner检查；不称native并行或训练通过；PASS_BOUNDED |
| CALL-03 | objects、planners、reporter、utils | 物体不伪装Robot；Planner／Reporter不推进physics或重定义任务成功；惰性导入保留，无需新抽象。 | 当前caller核对及A reporter/lifecycle；PASS_BOUNDED |
| CALL-04 | LIBERO benchmark owner与Core公共合同 | benchmark保留自己的OSC、gripper、谓词和replay语义，不改成PickCube；受影响共享接口按合同验证。 | A LIBERO合成／fake检查和diff；不称全A123 native重跑；PASS_BOUNDED |
| TEST-01 | 版本diagnostics索引、`run_pure_checks.py`及guard | 固定精确选点；纯合同、真实source、CPU/GPU/window显式分层。guard限制资产／SDK，非OS sandbox。 | 本次240项正式守卫命令；PASS_BOUNDED |
| TEST-02 | claim表／各行为owner测试 | 新架构不恢复旧fixture需要的candidate；旧API漂移已有边界，当前核心行为用新合同检查。 | A固定集＋52精确选点；不宣称旧整模块全绿；PASS_BOUNDED |
| TEST-03 | diagnostics／asset admission／公开readback | 实验注入、变体生成、严格Judge外置；source/clock/fault/readback及正式受限准入保留。 | 当前466个生产Python AST无diagnostics/tests静态反向import；caller核对；PASS_BOUNDED |
| TEST-04 | 各原run、U5包与独立reader | 原输入、命令、SHA、raw、计数、close及限制可定位；不同run未拼成同一次成功。 | 本次1,021对象、七项包复算、C同次联合；PASS_BOUNDED |
| DOC-01 | README→current-state→API／能力／编排 | 人工当前摘要及接收入口正确；机器编排顶层尚未同步，现行导航还不能全部一致。 | F1及文档检查；PARTIAL_DOC |
| DOC-02 | AGENTS、Skills、诊断／用户导航 | owner及正式API已有同步，TaskEnv Skill仍向U5派工，诊断索引仍称U1实施中。 | F2；PARTIAL_DOC |
| PROJ-01 | U5 stage01～05／optimization、最终选择与reader | 五stage唯一入口、必要核心诊断已归并；批准的旧attempt／副本已处置，103个根锚点保留不代表内容未清理。 | P 76,334路径与日志、七项读回；PASS_BOUNDED |
| PROJ-02 | selected object／source／资产索引、精确处置清单 | 必要H5/RGB/source与缓存分类；当前fixture有效；两项明确原位例外按维护者决定保留。 | P 14索引／1,021对象／4链接，无越界删除证据；PASS_BOUNDED |
| PROJ-03 | `.gitignore`、tracked inventory／保护输入 | workspace/temp输出无误跟踪，Git历史未重写，保护原件和pins保持。 | P git清单、前后SHA；PASS_BOUNDED |
| PROJ-04 | 正式worker cwd、输出／cache范围与处置owner | 新worker独立cwd；真实输出列入清理；不按日志文件名删除保护输入，不顺带清全局SDK缓存。 | A隔离cwd、B短程及P精确范围；PASS_BOUNDED |
| BRANCH-01 | Git refs／worktree、保全／恢复记录 | 保留主checkout＋指定冻结archive、6 heads/4 tags；旧stage分支和指定worktree已处置。integration Git管理元数据损失是批准接受的不可逆例外。 | P现状与原恢复记录；不是完整恢复认证；PASS_BOUNDED |

## 4. V01～V10、验证与复用边界

[本次取证目录](../../../../../../workspace/maintenance/v211_e00_e16_final_audit_0847a5da_20261114_001/baseline.json)保存输入身份、保护SHA、refs/worktree、原始命令输出及派生收据。CodeGraph先定位，索引drift文件读取磁盘当前源码，不重建索引。

| 证据层 | 本次实际执行或核对 | 结论及边界 |
| --- | --- | --- |
| A1 | `run_pure_checks.py` | **240 passed**；纯／fake合同，不能证明native或像素。 |
| A2 | 正式守卫 `run_pure_checks.py --offline-h5` 和显式fixture的 `--offline-physical` | **25＋8 passed**；读取保留旧H5及短物理记录，无SDK。 |
| A3 | `test_builtin_example_mode.py`精确当前节点＋`test_native_locks.py` | **52 passed**；节点表记录在本次输出。排除两个已登记旧API节点 `test_pickcube_r3_profile_is_task_versioned_and_records_rate_bound`、`test_isaac_interpreter_selection_without_launch`，本次未重跑它们，不声称整文件通过。含合成进程／信号，不启动native。 |
| B | 原四主体／三provider／原生及cross RGB；最终worker三路线 | 相关源码调用及diff复核；`3e77f6e0 → 0847a5da` 在task_env/examples/bench_deploy/Skills/AGENTS无文件差异。三短程仍仅构建/reset/非零step/close/H5，PARTIAL，不改称完整Solution。 |
| C1 | 当前公开 `examples/recording/inspect_h5.py --input <选中对象>` 对五完整H5读回 | **5/5 PASS**，T/T+1依次960/961、951/952、2377/2378、2442/2443、951/952。这是当前schema/storage reader兼容，不单独证明completion或新任务成功。 |
| C2 | U5包内 `recompute_packaged_joint_completion.py` | 五路同次caller、监督、计划、H5及源码身份关联成立。四CPU completion字段不存在，Isaac为null；caller done=true/failed=false，沿用维护者已批准的联合解释。部分动作／任务事实复算复用包内既有isolated-reader结果，不伪报本次全部重新测量。 |
| P1 | 14个固定索引、选定3,056条stage记录及13 supporting source索引的内容并集 | **1,021不同对象／572,124,256逻辑字节**逐个SHA/大小通过；四fixture链接有效。不是全部历史manifest可原样重放证明。 |
| P2 | 清理清单、执行日志、当前路径／权限事件 | **76,334**候选均不存在；intent和unlinked事件逐一匹配，无重复／额外候选；24,554个rmdir完成且与当前缺失目录一致，剩107目录身份/mode无漂移；38,794对权限事件闭合。两例外inode/大小/mode仍一致，未读私人输入内容。 |
| P3 | 包内七项有界检查，派生结果重定向本次目录 | **7/7 PASS**。G05一项仍为`PASS_REFERENCE_INTEGRITY_ONLY`，不等于重跑所有原renderer reader或物理；U4仍是联合证据。没有覆盖原U5收据。 |
| D | 当前文档validator | 退出1：既有`protected local input changed: MUJOCO_LOG.TXT`；79项历史链接问题，当前stale-path 0。F1/F2属语义漂移，链接检查通过也发现不了。 |

| V编号 | 对应实现／证据及本次复核 | 当前结论 |
| --- | --- | --- |
| V01 | 四正式配置／共同builder，A1配置，原YAML/mapping与source证据 | PASS_BOUNDED |
| V02 | 一体／装配Panda、两简单主体共同声明与绑定，原B及C覆盖相应路线 | PASS_BOUNDED；不外推任意主体 |
| V03 | typed Position/effort/wrench、双writer与冲突/fault；A1及原受影响B | PASS_BOUNDED |
| V04 | borrowed原生与independent cross、非Position RGB；A1及原B | PASS_BOUNDED；Isaac腕部挂载不推广其他provider |
| V05 | 原三native与GeoPhys physics×MuJoCo renderer；按各自身份复用，P对象保全 | PASS_BOUNDED；窗口不因无关改动全部重跑 |
| V06 | camera reset/step/二次reset/stale/close与无额外推进，A1及原B | PASS_BOUNDED；renderer固定到close |
| V07 | wrong source、资源冲突、副作用后fault、退休UID；A1/A3及原精确节点 | PASS_BOUNDED |
| V08 | PickCube MuJoCo／GeoPhys／Isaac，Nut MuJoCo／GeoPhys五完整运行，各自单seed且任务成功 | PASS_BOUNDED；不是最终HEAD完整重跑或G07三seed矩阵 |
| V09 | 当前公开reader五记录，包内同次联合completion及原独立动作/状态/clock读回 | PASS_BOUNDED；H5单文件不自含completion |
| V10 | 证据、清理、refs、pins和保护项核对成立；F1/F2状态／Skill仍待同步 | PARTIAL_DOC |

对E00～E04的原[独立主审](20261112_e00_e04_independent_review_76536d2a.md)及后续收尾、E05～E10的[独立主审](20261113_e05_e10_independent_review_d9dc02c6.md)，按当前方法链与后续相关diff复用；E11以后涉及caller、batch、PickCube readiness/相机和worker的变化另由U4专项、当前A及B/C核对。`0506ae26`之后的生产变更集中在transport／监督／worker／Harness编译，不能冒称五完整运行在这些新进程路径下全部重跑；最终三provider短程用于其受影响运行边界。当前审查未发现需新增完整Solution或全矩阵的具体失效证据。

## 5. 可实测的优化成效与口径

以 `1f1359ee → 0847a5da` 的Git路径和文本比较，不计ignored证据和四个保护untracked。文件数下表排除两gitlink、按tracked blob统计，避免把submodule当源码文件；原始取证中包含gitlink的计数也保留。

| 指标 | stage5输入 | 当前 | 实际变化 |
| --- | ---: | ---: | ---: |
| 项目tracked blob | 1,361 | 1,450 | +89 |
| task_env tracked文件 | 980 | 1,020 | +40 |
| PickCube specialization行数 | 1,046 | 600 | −446 |
| Nut specialization行数 | 702 | 504 | −198 |
| 公共Env行数 | 5,098 | 4,277 | −821 |
| Runtime API行数 | 1,759 | 880 | −879 |
| Assembly compiler行数 | 513 | 420 | −93 |
| H5模块行数 | 1,823 | 1,374 | −449 |

完整差额按 `git diff --no-renames --numstat` 分桶：生产及其他Python **+8,990／−17,050，净−8,060**；测试／diagnostics **+11,895／−1,334，净+10,561**；文档／Markdown **+4,016／−252，净+3,764**；配置及其他文本 **+0／−869，净−869**；全项目文本合计 **净+5,396行**。新增115路径、删除26路径、修改184路径；不考虑rename检测时，搬迁计为增删，不能把新增量全称为新逻辑。检测到的迁移另存原始summary，本表不声称逐函数精确区分搬迁与新写代码。

因此，确有Task/公共API减责和生产Python减少，**没有项目文件数或全项目文本净减少**。诊断和进程/资源检查等增加有实际职责，不以数量上升判定失败，也不再用早期累计净删除来掩盖它。

最终批准清理的同一有序范围（含U5和本轮分类/保全/日志）原分配量 **30,579,863,552→1,470,246,912 B**，点时下降 **29,109,616,640 B**。本次重新测同一范围为 **1,470,308,352 B**，较原后测增加61,440 B，符合之后收据增长；它仍远小于清理前。此范围不包含本次新复审目录，不能据此计算整个项目的当前净占用。历史E00～E16累计精确净额仍为 **UNKNOWN**，不能相加不同批次空间差额。

Git现状为主checkout＋维护者指定冻结archive两个worktree、6个本地heads、4个tags。被处置stage3/4/5及camera/core-baseline/clean checkout的六个原commit对象均存在，并且都是当前分支祖先；不依赖已删除分支名才能找到这些提交，但这不能补回integration原Git管理元数据。两submodule实际HEAD与gitlink一致：GeoPhys `c1ea3cc9`、Menagerie `b846dd12`；规范共享锁和保留旧alias同inode，点时可取得。466个task_env生产Python的AST语法检查无错误，未发现静态反向import diagnostics/tests；这不是对动态反射或第三方solver内部的全面证明。

## 6. 已批准边界与事件结论

以下是[维护者接收](20261114_e11_e16_maintainer_project_acceptance.md)已有边界，不重新登记成待修bug：T19同次联合completion；integration原worktree Git管理元数据不可补回；历史累计净空间UNKNOWN；冻结archive及旧锁硬链接保留；私人输入和loader历史事件流两项原位例外；锁的不可见/非合作进程限制；强制中断不保证App正常close；旧未选attempt／overlay不保证原样重放；N08/COM原FAIL、R05c NOT_REQUALIFIED、4b中间源码缺口、SDK及旧测试/validator限制。不能以“全部完成”省略它们。

| 事件 | 本次复审结论 | 保留的实际边界／剩余 |
| --- | --- | --- |
| E00 | 基线与度量成立 | 本次另建现行基线；保护输入及pins保全。 |
| E01 | 正式入口／配置有界成立 | 四正式任务同合同，范围外component不强并。 |
| E02 | 构造／主体绑定有界成立 | 构造阶段真实共享，lowerer可因结构／表示不同。 |
| E03 | 生命周期有界成立 | 失败、RNG及资源owner保全；不声称SDK全部日志无异常。 |
| E04 | 提交／推进链有界成立 | 单owner与typed区别保留，非任意序列组合。 |
| E05 | source／资产归属有界成立 | reference/replace受限；add等未支持能力不升级。 |
| E06 | physics adapter有界成立 | native映射和worker归属明确，batch留G06。 |
| E07 | 状态／观测／相机有界成立 | 明确projection及schema，腕部挂载仅沿用受测交集。 |
| E08 | renderer adapter有界成立 | native/cross有原始证据，固定renderer及颜色限制保留。 |
| E09 | Task减责有界成立 | 无旧candidate复活；Task仍保留有效业务与readiness。 |
| E10 | Recorder／replay分层有界成立 | 旧格式严格解码，T19按已批准联合证据。 |
| E11 | 诊断／测试归位有界成立 | 快速固定入口成立，旧整模块不宣称全绿；索引时态并入E14。 |
| E12 | 直接caller迁移有界成立 | 正式用户入口、learner/batch/LIBERO必要合同成立，非训练或G06验证。 |
| E13 | 完整运行／读回有界成立 | 五路线各自冻结身份、单seed；当前reader可读，不冒称最终HEAD完整重跑。 |
| E14 | 既有代码接收维持；资料收口PARTIAL_DOC | 集中结束F1/F2，对应GOV-04/DOC-01/DOC-02。 |
| E15 | 批准范围已归并／清理／复核 | 1,021对象、批准清单、两例外及范围空间下降成立；非所有历史可恢复。 |
| E16 | 批准白名单及项目有界接收维持 | 2 worktree/6 heads/4 tags，已批准不可恢复例外保留。 |

**三个结论分别是：** G05/5c历史有界功能接收不重开；代码优化的生产成果可维持有界接收，F1/F2资料出口尚需收尾；批准范围的项目归并/清理及维护者接收有真实证据，不因本次资料漂移推翻。结束资料收尾后可更新60项总账结案入口，但不自动启动G06，不merge/push/tag或发布，v2.1.1整体仍未完成。
