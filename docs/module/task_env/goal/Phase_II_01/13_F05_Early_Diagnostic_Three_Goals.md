# 新F05提前诊断实施：三个长期Goal

> **状态：DG01/DG02有界接收、R3对照PARTIAL保持。诊断04 window002的实际物理响应门未通过。维护者已改用无累计额度、同门连续两次失败先询问的规则，并裁定优先研究受支持的Isaac/PhysX公开桥接再实施；window003按新规则准备，正式N2未启动。**
> 本页是该诊断方向的当前编排入口，与[11](11_F05_F07_Multi_Asset_Solver_Recovery_Plan.md)、[12](12_F05_F07_Execution_Playbook.md)及每次冻结执行包共同使用。只更新执行方式，完整required物理语义与最终三cell目标保留。

## 1. 授权、历史与真实起点

2026-10-30维护者决定提前进入诊断模式，要求将整个新F05分成三个长期Goal，由其转述给Luna持续实施；每个Goal结束后Sol根据实际报告调整下一Goal，直到三个全部完成。由此**暂停普通successor三窗口序列**，不派普通003；普通001/002及2/3历史不重置、不删除，也不改成接收。明确指定诊断后的窗口另记，不设固定attempt次数上限；执行时间、native累计资源和输入冻结仍严格有效。

旧F05三轮、OVERALL_PARTIAL、已接受精确cell及失败原件保留。successor001经Sol复核PARTIAL；普通successor002执行时的静态审计与三路线阻断按其原始报告保留。该历史结果不代表后来单独授权的DG01路线。旧r009和GeoPhys/USD限制不因MuJoCo候选通过而改变。

此次不创建第二Runtime；一个CoreRuntime/Controller/Recorder/factory经provideradapter调用各原生宿主。USD/Isaac优先、同源多表示与统一物理语义维持；B同USD三Provider、官方Panda→GeoPhys兼容、Attachment、Newtonsolver仍延期。新F05不包含F06的真实任务20seed/Expert/Oracle/Judge，也不授FormalQualification。

## 2. 三个Goal与完成门

| Goal | 范围与实际交付 | 接收后进入 |
| --- | --- | --- |
| DG01 共同基线＋MuJoCo/MJCF/CPU | 完整源物理参数/任务cube-support/逻辑Joint-Frame-Action-Task基线；真实Core candidate/admission/control/state/record/close；公开native模型与传动力证据；同Env两轮及独立H5 | Sol接收DG01后，重新冻结DG02 |
| DG02 GeoPhys/USD/CPU | 保真USD表示；provider既有scene/constraint/tendon/actuator模型消费；model-bound Core receipt/admission；真实native与独立reader，对照DG01语义 | Sol接收DG02后，重新冻结DG03 |
| DG03 Isaac/USD/GPU PhysX＋联合收口 | 同版Isaac/PhysX公开诊断与现有Core owner接线；当前bounded N1和synthetic S1已完成，正式N2仍要求闭合source equality、fixed-tendon consumer、drive/contact语义 | 闭合required features后按冻结门运行真实Core cell；Sol复核三Goal和矩阵 |

三个Goal均须有implementation及真实route证据；inventoryPASS、固定nextpatchplan或旧syntheticS1不完成Goal。所需code/字段/profile不存在是实施任务，不自动是外部阻塞。无外部约束且scope内可修复时继续工作；阶段检查失败后在同Goal诊断、修复、重跑。真正无法表达的物理语义仍BLOCKED，给原参数、目标API/消费者、最小反例和具体维护者决定，不偷改required/源/阈值。

DG01优先复用现有non-leaf Position candidate/source和MuJoCo session；其sourcecomposition已有freebody路径，旧R02c leaf的no-freebodyshapeguard不是整个Core限制。只有实际选择leaf路径才需版本化扩展该guard，保留旧路线。MJCF→r009差异不能作为MuJoCo原MJCF路线准入阻断。DG02复用provider内部既有约束/传动编译；DG03不得因NewtonMimicAPI名字就认定必须Newtonsolver，也不能由deprecated/draft标签判不可用或已消费。

## 3. 持续Goal与一次执行窗口的关系

长期Goal记录持续目标、完成条件、已完成实现/证据与剩余缺口；一个Goal可经历多个自动turn和经Sol冻结的诊断窗口。若Luna有create_goal工具则明确创建/续同Goal，无tokenbudget；没有时使用goal_progress.json，不伪造工具Goal。工具状态遵守其本身complete/blocked规则。

每窗口只转述一个完整包。维护者人工转述DG01后Luna认领唯一writer，Sol只读观察，不中途追加任务或向别线程发消息。预计每10分钟/重要里程碑更新progress。已完成可以提前收口；未完成只因真实外部依赖/资源门/预算或timebox结束而交checkpoint，不能用“代码尚未实现”在短时间内以patchplan替代持续实施。

Luna释放窗口并返回完整报告后，Sol复核actualdiff、运行命令/原始证据、模型/源/producer身份、gate及退出/资源/保护hash。未达标则调整**同一Goal**的下一诊断窗口；达标才更新下一Goal的真实HEAD、上Goal合同/receipt、source/Task/Controller/reader变化、受影响owner和新预算，再由维护者转述。DG02/DG03今天的基线不得原样执行，避免提前冻结未来HEAD或基于未知结果派包。

Goal1当前预计主动4–10小时，单连续窗口最多12小时含最后1小时收口。DG02/DG03基线估计各8–16小时，可含多个有界窗口；只是估计，不保证成功也不预授额度。长Goal不提供无限native余额，自动turn/新文件夹不能清零累计消耗。预算到限就安全checkpoint，由Sol根据报告冻结追加窗口，Goal仍未完成。

## 4. 三层准入与物理证据

1. **S 静态/host/真实Core S1**：完整source、身份/单位/引用、实际candidate/admission/control/record路径，最低native边界可用显式synthetic；无realmodel的检查不得假称native消费通过。
2. **N0/N1 开发诊断native**：在完整生产路线尚未完成前，允许先冻结hypothesis、同版代码/source、公开API/观测字段、预计steps和失败判据，满足锁与资源门后做真实模型编译/读回或单feature短probe。无需先证明被测feature通过；结果仅diagnostic，不替代Core正run。
3. **N2 正式Core native**：当前route implementation/S1与必要模型/特性证据通过且code/reader/oracle/runplan冻结后，运行同Env两轮，每轮300interval×5×2ms，按route602boundary/observation、600transition、3000acceptedadvances。一个route不等其他route全部ready。

顺序保持环境/reset/state/close→空载hold/点位/return→gripper/freebody/contact→真实Taskpredicate。原粗motion/FK物理门及002新增tracking/stability/非对称耦合门全部保留；不同solver不要求逐点轨迹相同。sourceauthored限制、Canonical请求cap、effectivecap分开，scalarclip→J^T分力不可混为每指独立cap。u=0仍有bias，耦合probe停用actuator必须使用公开能力。单feature派生negativecounterfactual与原正式model分开hash与用途，不改source/r009原字节。

cube/support沿用原recipe：cube .06m/.1kg/reset(1,.5,.9)，supportcenter(1,.5,.45)、全尺寸(.35,.35,.05)、top .475、restcenter .505、gravity9.81；完整材料/惯性/过滤有效值在DG01绑定。Taskpredicate真实读取；初始cube已经高于lift门时rawpredicate如实输出，controlsmoke的非终止策略明确，lifecycle与rawTask成功分开。F05不要求抓取Expert。

## 5. DG01当前资源与保护

DG01只授权MuJoCo3.8.1CPU。当前窗口native累计≤48000steps/7200s，其中probe≤12000steps；每probe≤500steps/600s，模型编译/参数读回worker≤300s，formalworker≤6000steps/1800s。dt .002，含bootstrap/失败/ablation/诊断；不设置一次launch限制。启动MemAvailable≥6GiB，PG采样RSS≤4GiB，MemAvailable<1GiB中止，采样≤.25s、最多4CPUthreads、单重进程/sharednativeflock直到PG结束。Evidence≤1GiB、log≤128MiB、cache≤1GiB，零资产/依赖下载安装。完整更小约束见冻结budget。

DG01不启动GeoPhyssolver、IsaacApp、GPU、renderer或Newton；隔离provider只读host/source复用。DG02/03分别在前Goal接收后才冻结其CPU/GPU独立预算。不能将诊断模式解释为取消内存/显存/step/time门。

复用develop-full和现有隔离providerworktree，零新分支/worktree；不修改develop/camera、主providercheckout/gitlink、原始资产/旧H5/报告或无关untracked。只提交自己的implementation/docs/Skill，不push/merge/tag。每窗口冻结实际HEAD、prompt/snapshotSHA、保护bytes与runtime，受影响旧Evidence正确标失效或复用。

## 6. 当前工作包与最终接收

完整ignored编排包位于`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_f05_diagnostic_goals_20261030_001/`；三个prompt分别在goal_01、goal_02_baseline、goal_03_baseline。DG01准确INPUT_HEAD和prompt/保护hash由其snapshot及send_to_luna1文本给出；本页不持有自引用HEAD。输出依Goal/window/run分开，保留错误原件，关闭后独立reader复算而非复用producer被测判断，parent/worker/plan/code/source/model/H5/持久化文件与exit0/PGgone/锁收据同run绑定。

候选标签分别为`F05_DG01_MUJOCO_CORE_CELL_PASS_PENDING_SOL_REVIEW`、`F05_DG02_GEOPHYS_USD_CORE_CELL_PASS_PENDING_SOL_REVIEW`、`F05_DG03_ISAAC_AND_THREE_ROUTE_CLOSURE_PASS_PENDING_SOL_REVIEW`。只有Sol独立复核三个Goal及最终一致性矩阵后才能登记`ACCEPTED_BOUNDED_F05_SUCCESSOR_A_THREE_CELL`。这保留旧F05partial，不授通用格式/资产/solver支持或Qualification。

## 7. DG01 Goal01 实际执行结果（2026-10-30；候选通过，待Sol复核）

维护者转述的完整DG01包已在冻结的同一持续Goal/window内执行。输入`develop-full@6d4e222866474b0ce4399183a35c337f58303349`，原prompt/snapshot及5,906项保护输入按冻结快照核验。实现通过现有non-leaf Position candidate、TaskSource/Artifact/ResetPlan、SelectedReferenceEnv、MuJoCo RuntimeSession、typed state和Recorder路径接通Menagerie Panda MJCF与派生cube/support任务scene；不把旧r009 USD或旧GeoPhys/S1证据当作本路线证据。实现commit为`e410f97d90e1e88806318d11c47dc54d013dad5c`，其后的规划/Skill与收口commit列在DG01输出报告。

N0公开模型编译读取到`nq=16, nv=15, nu=8, njnt=10, neq=1, ntendon=1`；N1以非对称q/dq、标量力限幅、tendon wrap消融及equality正/负对照验证原源传动关系，并通过一个实际Core控制区间。N2冻结计划SHA为`e48dae904bf757f9b864eebf129619990638f174d00fe4f1fbdc53e701c60c32`：同一SelectedReferenceEnv两段各300 interval、5×2ms，合计3,000 accepted physics steps；两个H5各含301 observations、300 transitions。worker exit=0、环境关闭、进程组退出且共享锁释放；进程组峰值RSS 498,450,432 bytes，最低MemAvailable 6,796,738,560 bytes，采样最大间隔0.2001s。冷读器在绑定新Reader代码的RUN009内通过两个episode和14/14类负例。RUN008事后冷读仅为诊断证据，不代替RUN009。

reader按H5 v3直接存放的`boundary_events_v1_json`校验`episode_ended`事件，区分raw Task predicate与未评估的lifecycle success；物理门、Task门和14类内层篡改门未降低。目标定向provider-free测试20/20通过。DG01所需source/task recipe、logical-to-native映射、公开model/consumer receipt、完整运行计划、H5、冷读器、资源和失败尝试均保存在`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f05_diagnostic_goal01/window_001/`。

结果标签为`F05_DG01_MUJOCO_CORE_CELL_PASS_PENDING_SOL_REVIEW`，只覆盖这个固定Menagerie revision、派生任务scene、Task/Action合同、Core路由、MuJoCo 3.8.1 CPU profile和有界控制cell。Sol复核前不登记接收；旧`F05_OVERALL_PARTIAL`、GeoPhys/USD缺口和普通successor001/002记录不变。DG02/DG03、F06/F07及Qualification均未启动/授予。DG01 Goal保留为待Sol独立复核状态；完成本窗口不自动推进后续Goal。


## 8. DG01 Sol独立接收与DG02冻结准备（2026-10-30）

**决定：`ACCEPTED_BOUNDED_F05_DG01_MUJOCO_CORE`。** Sol核对DG01实际生产diff、488/488输出、5906/5906保护输入、12/12 runtime与2852/2852隔离provider基线，复算N1 scalarforce→clip→Jᵀ分力与equality正负对照，复核原RUN009同run退出/资源/plan绑定。原producer/H5/冻结plan均保留，不追加native。

复核发现原reader未核实际obs数值叶：重绑外层SHA后的joint observation变异仍被接受。Sol在既有reader owner修复五个观测叶的shape/dtype/finite、float32量化逐值与typed-state对应及boundary digest；增加八类观测负例，并独立复算力投影、加强parent-plan绑定。修复提交`cb8c3541d99d762c177fdade93eef42985aa07cd`。对原两H5冷读通过602实际obs、600transitions、3000advances和22/22负例。原14/14与候选签署保留其历史含义；本节是后续独立接收，不回写原runplan的reader/producer身份。未重跑pytest或native；仅闭合H5冷读、语义变异和已保存数值复算。

接收限同一Menagerie revision、DG01派生Task scene、Action/controller合同、MuJoCo3.8.1CPU精确路线及有界环境/控制/Task读出/录制单元。raw Task predicate不等于抓取成功或lifecycle-valid success；不声明跨引擎摩擦/接触等价、通用MJCF/USD、Expert或Qualification。旧F05 overall partial、普通successor001/002及其零native/阻断历史不变。

独立审阅目录：`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_f05_dg01_001/`，含Sol报告、hash/semantic audit、22类冷读结果和原reader反例。最终收据另绑定本轮review/docs提交与新reader hash，不改原producer签名。

### DG02 window001完整实施包

新包：`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_f05_dg02_001/`。以其input_snapshot记录的实际post-review/docs HEAD为输入；替代旧goal_02_baseline，不创建新branch/worktree。复用develop-full和现有隔离GeoPhys分支（输入`41f8b517c5f92cd6e59907394dc42714b78702a7`），主gitlink不动。维护者人工转述完整prompt后，Luna创建/继续DG02长期Goal；Sol未代其启动Goal或native。

实施重点：新保真USD/source closure→现有GeoPhys semanticIR/constraint/tendon/affine-actuator模型→public runtime消费者→精确Core receipt/admission/candidate/control/state/Task/record/close。九scalarDOF对应八source actuator，joint_targets不是ctrl槽列表；tendon标量限力必须先clip再Jᵀ，保留equality solref/solimp、有效material/collision与freebody/support消费。缺parser/profile/receipt属于本Goal实现；允许完整生产路线未ready前冻结N0/N1短probe，验证实际消费者后再接通N2。不得用MJCFfallback、private数组、poststep投影或审计报告代替USD真实路线。

DG01 recipe/Task/Action语义保持；source8驱动gain/bias/caps与Canonical100N默认、2500N/m servo增量配置分开；旧r009只读，新表示独立版本/hash。N2保持同Env两轮300interval×5×2ms，602真实obs、600transition、3000advance、原物理/控制阈值及独立负例。DG02 reader必须继承本轮实际观测验证，不再只验typed-state/行数。

预计主动8–16小时，可跨经Sol重冻的窗口；本window最多12小时且预留末1小时收口。总native≤72000steps/10800s，其中GeoPhys≤66000/10200s，可选MuJoCo仅source-export零step编译或受影响DG01回归≤6000steps/600s；probe累计≤18000steps，每probe≤500steps。native启动MemAvailable≥6GiB，PG采样RSS≤4GiB，低于1GiB中止，采样≤.25s、4CPUthreads、共享单native锁，新增Evidence≤1.5GiB。精确分项/timeout见budget；无launch次数限制，失败可在同Goal修复，自动turn不重置预算。

DG02只有完成G0–G8、真实public USD/consumer与Core cell、独立reader/退出/保护/owncommits后才可报`F05_DG02_GEOPHYS_USD_CORE_CELL_PASS_PENDING_SOL_REVIEW`。Sol独立接收后才调整/冻结DG03；本次不启动DG03、Isaac、GPU、F06/F07或依赖/资产下载，不保证一个窗口内通过。


本轮收口：Module Skill静态检查、规划文档hash与局部链接、diff检查通过。全局docs validator仍失败：223项＝原216项＋DG01既有七个新增源码/recipe路径的scope诊断；没有把该失败报告为PASS。Sol本轮没有pytest/native，reader修复由原H5冷读与内层负例直接验证。完整validator输出及差分保留在独立复核目录。

<a id="f05-dg02-window001-geophys-usd-in-progress"></a>

## 9. DG02 window001 当前结果（2026-10-31）

本Goal仍为 `F05_EARLY_DIAGNOSTIC_DG02_GEOPHYS_USD_WINDOW001`，Core分支为`develop-full`，provider使用隔离分支`codex/phase-ii-01-f05-geophys`。GeoPhys保真USD表示已通过source closure、几何/frame/mass/contact审计及public USD→既有IR→public model消费；模型为13 bodies、83 shapes、12 joints、8 actuators、8 transmissions、3 constraints、1 tendon、1 equality。N1标量drive/tendon/equality探针及G4耦合正负对照通过。Core已有source/model-bound V2 receipt、admission、Controller、RuntimeSession、Recorder与close路径；同一`SelectedReferenceEnv`的S1通过两轮短流程。

N2正式run `DG02_G5_FORMAL_ACTUAL_CORE_SELECTED_REFERENCE_N2_019`使用已提交Core HEAD `e865834f4c0519e23b37f6100959b5a82ade0f2d` 与provider HEAD `f4d3b3bb21882bac5ca007e657f5d6709a6189b8`。worker exit 0，1次native启动，2集共3,000/3,000 advance，process group先于锁释放退出；每集有301 obs/300 transition，H5已持久化。独立reader冷读两份H5共602实际obs、600 transitions和3,000 advances；source-FK最大残差为`1.66e-7 m`/`4.12e-7 rad`，接触/readback通过，DG01继承22类加DG02负例共23/23拒绝。

冷读同时发现真实控制门失败：home hold通过，但point、return、gripper-close、gripper-open和final-hold在两集都超过冻结tracking阈值。五阶段晚段joint target误差最大值依次为`0.107`、`0.236`、`0.320`、`0.209`、`0.400 rad`；峰值速度为`6.31`、`6.49`、`6.73`、`3.87`、`6.73 rad/s`，明显高于冻结的`0.025 rad` target误差、`0.005 rad`峰峰值和`0.1 rad/s`速度门。两集数值完全重复；因此N2 worker完成不等于控制cell通过，DG02整体保持PARTIAL，不能赋予DG02候选PASS。

为补齐G7，reader后来在独立host supervisor下重跑：parent记录600秒上限、0.25秒采样、约603 MB峰值RSS、15.85 CPU秒、单进程、exit 1、process group清空、共享锁前后空闲；reader结果仍为tracking gate失败。这是有界reader完成证据，不改变G6失败结论。此前无OpenUSD路径的冷读尝试在导入期因缺少`pxr`失败、未生成receipt；按冻结runtime路径重跑后得到上述结果。

DG02目标/阈值未放宽。N2_019失败后，在同一source-bound Core/GeoPhys/USD route上执行了两个500-step定向probe。probe001使用`achieved_state_dls_v1`、reset-posture nullspace gain 1.0，home hold通过、point hold失败：晚段目标误差`0.10227 rad`、峰值速度`5.48838 rad/s`、峰峰值抖动`0.05219 rad`。probe002只将DG02专属nullspace gain改为0.0，home hold通过、point hold仍失败：`0.06816 rad`、`4.30769 rad/s`、`0.10461 rad`；前两项改善但抖动恶化。两个worker均完成500/500，但都不是formal N2或通过的Core cell。probe001 reader发现阈值schema读取缺陷后作了冷读修复，receipt同时记录冻结reader hash和read-time hash；probe002计划绑定修正后的reader hash并通过独立冷读。

累计probe计数现为`17,940 attempted / 17,920 completed / 18,000 max`，只剩60步。原正式两集N2仍需3,000步，因此本冻结预算不能完成正式复验，也不能把bounded probe写成PASS。下一步必须先以新的冻结预算继续定位/修复实际Core point tracking，再按原阈值完成正式N2与冷读。当前Core实现commit为`78ea8cdb06d17792f2c774fbcca52bfd373cbff0`；GeoPhys隔离provider仍为`f4d3b3bb21882bac5ca007e657f5d6709a6189b8`。source仍为`local-validated`且`source_verified=false`；不推断通用GeoPhys/USD、Isaac/USD或跨solver接触/材料等价。不启动DG03、F06/F07或Qualification。旧F05三轮/PARTIAL、接受的DG01、r009及历史输出均不改。


## 10. DG02 window001 Sol复核与window002（2026-10-31）

**决定：`DG02_WINDOW001_REVIEWED_PARTIAL_REWORK_REQUIRED`。** 已核820/820输出、277份JSON、6475/6475保护输入和12/12 runtime。独立直接读取原N2_019 H5重算12行phase tracking，与签署reader一致：最大target error0.400356rad、p2p0.364800rad、速度6.730178rad/s，22项失败真实存在。现有生产USD/public consumer/Core接线和source语义探针是工程增量，不接收完整DG02，不推进DG03/F06/F07/Qualification。

复核返工点：R1同source/dt/hold窗口下以公开固定native目标→Core absolute_joint→Core absolute_pose三层受控对照定位首个失稳层，停止以nullspace gain扫参/重复整轮替代归因；R2现有reader漏读实际H5 cube target_body_pose叶，负例仅改typedframe，须补真实存储叶校验；R3原bundle已有task_predicate错误，negative仅以同错误码存在计PASS不能证明Task变异检测，须有独立检查ID/差分；R4共享默认Controller identity由v0变v1，须核旧默认兼容及实际caller/回归；R5保留两次无监督compile和一次默认CUDA初始化事件，后续所有会触发compile/init的检查必须正确CPU failclosed且受既有supervisor约束。

**预算纠正：** 原Goal冻结probe18000、GeoPhys总66000steps分别约束；逐run实际formal16325＋其余所有步骤保守算probe1675＝18000attempted（17980completed）。原账把formal也写入probe，不能据此称全部native余额0。所有失败/formal仍计入GeoPhys/总native，不退款、不抹历史。两条native test wall缺失先各保守预扣900s，待原日志核实。startedUTC至最后更新约15h11m，与原active230min/externalwait0须对账，不能伪造暂停区间。原window释放后仍须新冻结，不直接沿旧文件续跑。

完整复核：`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_f05_dg02_001/`。旧report/manifest/H5/plan原件保留签署含义；本次Sol只做diff/哈希/原H5独立数值核验，零pytest/native/GPU。

**window002续同DG02 Goal：** 完整包`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_f05_dg02_002/`，以input_snapshot的post-review/docs HEAD为准；provider输入f4d3b3bb21882bac5ca007e657f5d6709a6189b8。复用原phase分支/隔离worktree，零新branch/worktree，人工转述后执行。不能重建Goal或清零计数；工具blocked与JSONactive字段须诚实说明并按宿主规则恢复。

原Goal总native资源上限不增加；新window从剩余额度划出GeoPhys≤18000steps（probe≤12000、formal≤6000）/3600s；可选受影响DG01 MuJoCo回归≤3000steps/300s；合计≤21000steps/3900s，与原各bucket剩余额度取较小值。未知旧wall已先保守预扣1800s。每probe≤500steps，至少预留完整3000step formal；短对照稳定、受影响S1与reader修复通过、implementation提交并准确冻结plan后才formal。预计主动4–8h，window上限8h、末45min收口；MemAvailable≥6GiB/PG RSS≤4GiB/低于1GiB中止/.25s采样/4CPUthreads/单重进程与共享锁保持。新Evidence≤1GiB，无依赖/资产下载，不启动Isaac/GPU/Newton。

N2仍须原同Env两轮300interval×5×2ms、全部物理/control/Task/storage/退出门，不改变source gain/物性/Task Action配置/阈值换PASS。成功只报待Sol复核候选；DG03需本Goal完整接收后再冻结。无法在原语义下实现时给最小反例和外部决定，不扩大solver算法范围。


本轮Sol收口静态检查：Module Skill元数据/本地链接/源码路径、规划15份文档hash与局部链接、diff检查通过。全局docs validator实际退出1、247条（246个non-documentation scope诊断＋1个count limit）；相较Luna收口245条，增加的是其随后已提交的两个tracking-probe plan/reader源码路径，未新增本轮文档链接/内容诊断。全局仍不记PASS；原245签署输出保留。完整差分见Sol复核目录。


## 11. DG02返工方向修订：PickCube R3对照（2026-10-31）

维护者明确批准PickCube通过既有公共构造/配置显式使用NutAssembly的R3持续笛卡尔反馈，作为DG02对照。原R1默认、冻结历史身份/证据保留；复用已有`ProductionCanonicalPandaControllerR3`及必要共享臂/Position适配，不复制控制器，不搬NutAssembly任务补偿、10N抓手配方、Expert或Outcome。此前PickCube R1任务成功是功能证据；NutAssembly2026-10-20局部continuous/locked精度报告是独立诊断参考，均不自动证明当前PickCube R3或USD精度。

新的唯一待转述执行包为`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_f05_dg02_002_pickcube_r3_001/`，继续同DG02/window002，不增加已执行窗口计数。它替代未执行的`sol_f05_dg02_002` prompt/scope，不叠加派发。准确post-preparation HEAD与保护hash由新input_snapshot给出；复用develop-full与既有隔离GeoPhys@f4d3b3bb，不新开branch/worktree。Sol准备阶段仅文档/包/静态哈希核对，零implementation、pytest/native。

实施顺序：PickCube/MJCF/R3在MuJoCo和GeoPhys的当前连续反馈对照→对齐physical TCP、q0/dq0、目标轨迹、限速/加速度、reset记忆/保持/度量窗口→同一GeoPhys中对DG02同物理配方的MJCF/R3与USD/R3作可归因比较→修复既有Core/provider消费/控制适配并完成原3000step formal。PickCube加强配方（含臂限力±250）与DG02原source限力/物性差异必须记录，不把它们当只换文件格式；handorigin与offset TCP正确变换，不当作已证实误差。R3新方法/实际派生参数以独立profile和真实identity冻结，Canonical请求含义、source gains/caps/物性/Task及原验收门不改。reader实际cube叶、负例归因、旧默认identity兼容、CPU监督及预算分桶修复一并收口。

原Goal总step/wall上限不增加；MuJoCo本window授权由旧DG01回归限定明确扩为PickCube R3对照及受影响回归≤3000steps/300s。GeoPhys新增≤18000steps（nonformal≤12000/formal≤6000）/3600s，总新增≤21000steps/3900s；所有nonformal（含baseline/MuJoCo）保守记原probe桶，旧1675＋新≤15000仍≤18000。baseline regression可≤3000steps/run以保留完整轨迹/hold；feature microprobe≤500steps，不能截短协议冒充同门。8h窗口/末45min收口，原资源门/锁/零GPU/下载保持。所有额度与原累计剩余取较小值。

成功仍只交DG02待Sol复核候选；DG03/F06/F07/Qualification不启动。原source/recipe/oracles、旧窗口/失败/H5/plan及原partial均保留。

## 12. DG02 window002复核及window003（2026-10-31）

**决定：`REVIEWED_PARTIAL_CURRENT_IDENTITY_N2_REQUIRED`。** Core输出`f9198d4fdb2e1a28c341d8934caec4c3020fe09b`，隔离GeoPhys输出`a9e4c4850bd225f5929e74831ac282b18ff517ce`。PickCube已显式接入既有R3共享臂控制；GeoPhys USD importer已补源关节damping/armature。Sol逐项核对7,367保护输入、12 runtime，离线复算旧通过run的H5观测及12行tracking稳定性；零pytest/native。

window002 N2 #002的3,000步及reader通过绑定旧provider f4d3b3bb；window001 N2 #019的22项失败仍是不同证据。补passive后的S1 #003通过80步，完整N2 #008却因短S1 horizon12被传入而仅完成55/attempted60步。当前Core已修formal horizon300，但未有当前完整结果。不能用旧H5接收，也不能把passive遗漏称为原tracking失败唯一根因：R3在旧provider下已通过，passive修复解决的是另一个由counterfactual确认的源消费差异。

window002 formal已用3,060/6,000步，余额2,940不足完整3,000，释放并停下正确。Sol复算Goal累计GeoPhys25,745 attempted、MuJoCo3,000；全部nonformal保守probe9,360，累计native wall含旧未知项1,800秒reserve为7,426.902秒。原总72,000步/10,800秒等Goal上限未耗尽，不能称总预算为零。

唯一下一包为`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_f05_dg02_003_formal_closeout_001/`。复用原phase分支/隔离provider及同一DG02，window另计，不重建Goal或重置历史；post-review HEAD以新snapshot为准。预计主动1–3小时、窗口最多4小时含末30分钟收口。从原Goal剩余划出GeoPhys最多6,500步（formal6,000、必要nonformal500）/1,800秒，零新增MuJoCo。单正式run仍同Env两轮各300interval×5×2ms＝3,000步；不缩短、不放宽门。允许预算内必要修复重跑，完整3000步预留是每次formal启动条件。新增Evidence最多512MiB且受原Goal累计上限约束；原6GiB启动、4GiB PG RSS、1GiB中止、CPU4线程、共享锁及零GPU/下载保持。

收口前须按真实消费者解释50个host descriptor差异（材料fallback/有效geom材料、网格顶点/几何、惯性数值/场景表示），不能由短probe名称宣称等价。PickCube strict f64对照未过的原结果保留；按已冻结normalization核每值dtype/量化，不一律套f32或另改阈值。formal预检明确实际candidate/Env horizon300、timebase、两轮、run/output/sidecar和完整源码闭包，避免继续消耗native在接线错误上。复用未变S1/模型/reader证据；受影响部分才重验，所有model compile/init仍受native监督。G8补当前公开选择的文档、Skill及受影响回归记录，保留旧时间账本未决项。

完整复核及离线审计在`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_f05_dg02_002/`。成功只交`F05_DG02_GEOPHYS_USD_CORE_CELL_PASS_PENDING_SOL_REVIEW`，DG02是否接收由Sol复核全部原门；本次不推进DG03/F06/F07或Qualification，不push/merge。

本轮Sol静态收口：TaskEnv Skill checker、规划15份文档hash及diff检查通过。全局docs validator退出1：258条（257条non-documentation scope＋1条count limit），相较上次247条增加11条既有实现路径scope诊断；无新增具体文档内容/链接错误。全局仍为失败，原输出保留于Sol复核目录。


<a id="f05-dg02-window003-current-identity-candidate"></a>

## 13. DG02 window003当前身份正式Core N2与收口（2026-10-31；Sol有界接收）

**Sol决定：`ACCEPTED_BOUNDED_F05_DG02_GEOPHYS_USD_CORE`。** 接收范围是本次冻结的Menagerie source、Task/Action合同、Core source-bound候选及runtime路径、隔离GeoPhys CPU profile和下述N2证据；不扩展为任意USD、全部GeoPhys资产或跨solver等价声明。

窗口003使用冻结包`DG02_WINDOW003_CURRENT_IDENTITY_FORMAL_AND_CLOSEOUT`，输入Core `develop-full@491f89a28e98badd3147fec968854e70717571a7`、隔离GeoPhys分支`codex/phase-ii-01-f05-geophys@a9e4c4850bd225f5929e74831ac282b18ff517ce`。冻结prompt、snapshot、manifest SHA分别为`53651b07b024b9adbb080359e319a025d89ce761b644f011db6bce8213655e8c`、`1be83ca3b7356dcccd07817670fd1034bfabef025079093b495a5c699c23b22c`、`b7f7f86d3932751d1a5d8fa22760c6489c1bc1e43cfb4afed7db7da114d2bf23`。当前Core实现HEAD为`589fb956cd691460d93a77db8ff7475e9431940c`；window003新增Reader修复已由`589fb956`提交。唯一无关未跟踪文件`docs/maintenance/20261030_runtime_route_diagnostic_handoff.md`受保护且未纳入提交。

此前已授权的窄MuJoCo enum→`int`规范化及回归位于祖先提交`bc1bc170`，本窗口未再改production MuJoCo代码。当前窗口Reader修复确保H5实际cube pose quaternion为有限且单位范数，非单位变异由既有`obs_cube_pose`负例拒绝；相关reader测试与MuJoCo enum回归共11项通过。窗口003代码改动仅限TaskEnv诊断reader和窄回归。

当前Core身份的静态候选用受监督零步public model build通过，模型包含16 qpos、15 dof、8 actuators、1 tendon、1 equality和25 geoms。正式N2使用计划SHA `5f0d098c40ba99fc0c025717975e2f3b8514523baf19f5a85f72840b3b83412d`，run `DG02_G5_FORMAL_ACTUAL_CORE_SELECTED_REFERENCE_N2_001`：同一`SelectedReferenceEnv`两集、每集300 intervals×5×2 ms，合计3,000/3,000 physics advances；602 observations、600 transitions，两份H5均关闭持久化。受监督worker exit 0、峰值process-group RSS 1,682,337,792 bytes，进程组在共享native锁释放前退出。独立冷读计划SHA `4286dbffbec159f058ebd030be8bc4f0e75a84656d96ebb137cab15d34ee0bc6`，reader与supervisor exit 0，baseline error 0，source-FK最大位置/方向残差`1.864644006e-7 m` / `4.887944301e-7 rad`；所有tracking phase、rest contact与实际cube pose校验通过。保存的structured negative suite报告23/23（DG01继承22类＋DG02新增1类）。冷读顶层历史status文字仍写“22 negatives”，这里保留原件并按嵌套结构化的23 required/23 passed计数；未篡改冻结receipt。

源几何审计记录11个Panda body frames、23个绑定USD PhysicsMaterial的collision shapes、10个匹配box及71个匹配mesh geometry；13个collision mesh的匹配坐标最大差约`1.49e-8 m`。USD authored材料值均为static/dynamic friction 1.0、restitution 0.0，宿主descriptor和有效contact/friction law仍有表示差异，不声明跨solver接触/摩擦等价。逐值R3 normalization审计也没有解除原strict f64 comparison：arm position 1,064/4,214、velocity 2,482/4,214、target position 4,048/4,200仍超适用逐值容差；float32只解释部分差异，R3跨provider结果继续为`PARTIAL_REALIZED_STATE_OR_TARGET_MISMATCH`，不得称其通过。DG02被冻结的control oracle明确声明`not_trajectory_equivalence=true`，DG02的本路线验收要求实际源语义消费、Core tracking/物理门及其独立记录，不要求不同solver逐点重现轨迹。因此该R3差异作为最终三路线矩阵中的未决诊断保留，不阻止本次有界GeoPhys/USD cell接收，也不被掩盖。

本窗口native仅有1次零步GeoPhys public model build与1次3,000步formal GeoPhys N2；没有新增MuJoCo启动。窗口003 GeoPhys共3,000 attempted/completed正式步，累计GeoPhys为28,745 attempted / 28,720 completed；累计正式步22,385 / 22,365，保守nonformal probe仍9,360，MuJoCo历史3,000步保持不变。窗口新增native wall约570.607秒；Goal累计GeoPhys native wall保守7,973.055秒，all-native wall含window001未知项1,800秒reserve为7,997.509秒。所有值仍在冻结Goal/window限额内。未启动DG03、F06/F07，未授Qualification，也未改变旧F05三轮/PARTIAL、旧r009或历史输出。

Sol的离线复核重新计算两份H5的观测值和12个tracking行，H5 SHA与worker witness一致；验证输出清单39/39、冻结保护输入7,626/7,626、runtime 12/12和provider source 2,859/2,859。复核未运行pytest或native。复核报告及机器可读审计位于`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_f05_dg02_003/`。Luna报告的tracked tree clean，Core在`e13a02acef64642bd8f3ce3b3735303c80c671a7`，隔离GeoPhys在`a9e4c4850bd225f5929e74831ac282b18ff517ce`；原有无关untracked文档保持未改。当前有界接收标签为`ACCEPTED_BOUNDED_F05_DG02_GEOPHYS_USD_CORE`。

DG03现在可以进入新包准备，但不得重用今日的baseline直接执行；须以当前已复核HEAD重冻实际Isaac/PhysX消费者、DG01/DG02合同输入、保护哈希、资源与验证范围。DG03、F06、F07仍未启动，本次没有授予F05整体接收或Qualification。

G8文档与静态收口：Module Skill checker通过；4份受影响文档的本地链接/锚点检查通过；`git diff --check`通过。系统quick-validate脚本不可用。staged consolidation docs validator退出1，258项错误＝257条non-documentation scope路径＋1条count limit；没有报告本次编辑文档的链接或内容错误。不得将全局validator写为PASS。完整checker/validator结果与输出hash清单留在忽略window003目录。

<a id="dg03-window001-current-implementation-status"></a>

## 14. DG03 window001 当前实施状态（2026-10-31；formal N2 blocked）

本窗口基于`develop-full@ea5611eb06cb22648c43b1656ba3353e7983a805`实施；包输入HEAD由DG03冻结plan绑定，旧F05 successor002历史报告及其`03ec5ef`输入要求不回写。DG03代码增量扩展既有Position candidate、SelectedReferenceEnv、Core RuntimeSession/native-I/O与Recorder链，增加版本化source-tendon receipt和每substep公开状态/力投影核验。`materialize()`对生产DG03明确fail closed：来源只有局部验证，且原source equality compliance、PhysX fixed-tendon消费者、drive/contact映射尚未证明；仅私有synthetic S1 context可替换Native I/O，不会启动Isaac App。

DG03 S1 provider-free Core回归通过：同一source-bound candidate录制两段synthetic episode，每段8 transitions、9 observations、40条synthetic advance；独立Core Python进程用现有typed-H5 reader cold-read两份v3 H5。12种source-tendon receipt tamper被拒绝。证据`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f05_successor_002/s1_isaac_core_s1_003/`将`source_verified=false`、`runtime_admitted=false`、`native_starts=0`和`physics_steps=0`明确记为synthetic；H5 cold-read只证明持久化可读，不是PhysX消费、独立native reader或物理通过证据。

DG03此前保存的N0 worker通过公开GPU PhysX model compile（18 bootstrap steps）；随后N1 attempt006在exact locally validated USD上启动一次Isaac Sim 6.2、worker exit 0、78 physics steps、进程组退出及shared lock释放。N1以代码显式author的`PhysxMimicJointAPI`验证了finger coupling，并通过公开`Articulation.set_dof_efforts`人工计算`J^T` source-like effort，观测到有限运动及+100 N clamp。它**没有**证明转换USD中的source `MjcEquality`/`MjcTendon`被PhysX消费者读取，也没有证明Core生产materialization、安全驱动映射或材料/接触等价；这些feature仍属于G4阻断项。EULA启动授权记在窗口ledger；此处无追加/重放native。

因此DG03正式N2/Core native cell尚未启动；这次状态是`DG03_PARTIAL_SYNTHETIC_S1_AND_N1_DIAGNOSTIC_PENDING_SOURCE_CONSUMER_PROOF`，不是三路线F05通过。source-specific补丁/代码、收据与当前回归由Sol独立复核；在feature gate闭合、正式runplan与独立reader冻结之前，不启动DG03 formal N2、F06/F07或Qualification。`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f05_diagnostic_goal03/window_001/`保留N0/N1计划、worker/supervisor原收据和失败attempt；不覆盖旧结果。

<a id="f05-successor-attempt002-continuation-2026-11-01-partial-pending-sol"></a>

## 15. F05 successor attempt002 continuation (2026-11-01; PARTIAL; Sol reviewed)

本节记录维护者在 attempt002 执行后继续推进同一 goal 的有界续行；原 attempt002 的 `report.md`、freeze、失败原件和时间点不回写。续行基于 `develop-full@681a3361f33d52799a61ac5d43edbf6caabfe33e`，完整事实与 raw receipt 索引见 ignored 输出 `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f05_successor_002/continuation_closeout_20261101.md`。Prompt 和 snapshot 仍分别绑定 `3343335567569fc88201a95975131cf8e94369fcb806ede690fb4b79e1e5b90e` 与 `a45d44fd5937c0db12a42d93dab8a43f83794f0feb0f803aae0b28c470188270`。

DG01 原 MJCF/MuJoCo CPU 和 DG02 USD/GeoPhys CPU 各自已有精确有界 Sol 接收；这些结果保留各自 source/Task/Action/profile 范围，不单独构成 successor 三路线整体通过。DG02 的 PickCube R3 跨路线状态/目标结果仍为 `PARTIAL_REALIZED_STATE_OR_TARGET_MISMATCH`。attempt002 当前 HEAD 上另完成 DG03 source-bound synthetic Core S1：两段 synthetic H5 各 8 transitions/9 observations，native/physics/renderer starts 均为0；直接 HDF5 独立冷读通过，`source_verified=false`、`runtime_admitted=false`。

DG03 另有两个有界 N1 Isaac 6.2 GPU PhysX 诊断探针：source-bound mimic positive 78步，非对称手指差从约0.016m降至约1.85e-6m；完整移除三种 equality/mimic schema 与八项关系属性的 counterfactual 48步，差异由约0.016m增至约0.040m。两者 reader 均为 `PASS_DIAGNOSTIC_ONLY`，只说明该诊断舞台上的关系消费对照有缺陷敏感性，不证明 production importer/Core 对 source `solimp` 或固定 tendon 的消费，也不证明drive/contact/材料等价。维护者明确接受并授权本包所需的 `OMNI_KIT_ACCEPT_EULA=YES`；该授权不放宽 feature 门。

DG03 的正式 Core N2 cell 未启动，状态 `BLOCKED_BY_FEATURE`：源 equality authored compliance（`solimp=0.95 0.99 0.001`）没有已证明的 PhysX/Core 等义消费者；source fixed-tendon actuator law 与 public consumer 的完整接线及 source-to-PhysX drive/contact 映射也未闭合。不得以显式 authoring 的 mimic 探针或 synthetic S1 填补这些缺口。当前 attempt002 的三cell候选仍为 `F05_SUCCESSOR_PARTIAL_PENDING_SOL_REVIEW`；旧 F05 `F05_OVERALL_PARTIAL`、r009 和历史 Evidence不变，F06/F07及Qualification未启动/授予。此前 attempt002 原收口所述“native starts=0”针对当时三个正式cell；续行之后确实启动了单独账本中的 DG03 N1 诊断，不应把诊断运行混称为正式cell。

### Sol复核决定（2026-11-01）

**决定：`F05_SUCCESSOR_PARTIAL_REVIEWED_DG03_CONTINUE_REQUIRED`。** Sol核验36/36输出manifest，并检查当前Core代码差异、synthetic S1/H5冷读收据及两个N1计划、worker收据与独立读回。N1正例和完整关系消融构成exact derived USD/PhysX诊断舞台上的缺陷敏感对照；它们不是生产Core materialization、原source `solimp`柔顺等价、完整source fixed-tendon consumer、drive/contact等价或正式N2证据。DG03生产`materialize()`保持fail closed，正式N2仍`NOT_STARTED_BLOCKED_BY_FEATURE`。protected/runtime/provider/gitlink、受控退出和锁释放按continuation收据核验；本次Sol review未运行pytest或native。

DG01/DG02此前有界接收保持不变，R3对照仍`PARTIAL_REALIZED_STATE_OR_TARGET_MISMATCH`。DG03长期Goal继续active，必须以复核输出HEAD新冻执行窗口，完成剩余source-to-consumer实现和验证后才运行未降低的正式N2及三路线矩阵。旧`F05_OVERALL_PARTIAL`、ordinary successor计数2/3、F06/F07和Qualification状态均不改变。Sol审阅记录见`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_f05_successor002_continuation_20261101/`。

<a id="f05-diagnostic04-dg03-repair-and-closure"></a>

## 16. 诊断04：DG03返工、新F05收口及F06入口（2026-11-01；准备供维护者转述）

维护者要求构建新的持续Goal，明确主要目标、当前状态、分阶段方案和压缩上下文后的恢复方法，并避免在细枝末节上长期停留。诊断04是承接DG03未完成项与联合收口的执行名称；原三个provider目标、普通successor 2/3历史、DG01/DG02有界接收和DG03既有消耗均保留，不增加第四条provider路线。包为`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_f05_diagnostic04_001/`，ID `F05_DIAGNOSTIC04_WINDOW001_DG03_REPAIR_AND_F05_CLOSURE`。实际执行HEAD、prompt/保护字节hash和允许修改范围见该包冻结snapshot/manifest，Luna人工接包后才认领writer。

按A源参数到公开consumer的最小可实施决策→B既有Core owner的实际修复与S1/有界探针→C未降低的3,000步正式Isaac N2与独立冷读→D三路线矩阵及F06入口清单实施。equality柔顺、fixed-tendon law/分力、drive/contact映射是剩余实现主线；没有同版公开能力证明时保留精确阻断与最小反例，不以普通字段错误或静态表格结束持续Goal。F06只列正式交付、Harness真实资产/CPU profile接线、新桌面场景/reset/谓词和Expert对接owner；20-seed/Oracle/Judge留在F06，不新增为F05完成门。

复用`develop-full`与现有只读隔离GeoPhys，零新branch/worktree。原DG03累计上限24,000步/5,400秒，已用486步/1,063.598855582秒；诊断04新增最多23,514步/4,336秒，其中Isaac17,514步/3,436秒，CPU回归6,000步/900秒，各限同时适用。保守取整后native wall总量仍不超过旧上限，非正式Isaac probe剩余8,514步。正式N2前预留6,400 attempted步/2,400秒，覆盖两次完整3,000正式步及每run最多200 bootstrap步；实际bootstrap更大时先重算内部预留。原内存/显存/共享锁/受控worker退出门保持。单窗口主动最多12小时，最后至少60分钟收口；native资源不随压缩/新turn/别名清零。

每阶段或run后维护一页`RESUME.md`和`goal_progress.json`，记录当前门、证据、身份、预算、worker/锁及下一动作；压缩后先读原prompt/短进度/ledger/Git状态，确认监督进程再续，不重跑全量历史。约30–45分钟没有新证据就换最小复现或独立判别方式，同类失败两次先修接口/detector；这要求改变方法，不授权弱化必需语义。报告/计数文字和已有全局docs scope错误不应挤占物理实现主线。

候选通过标签为`F05_DIAGNOSTIC04_CLOSURE_PASS_PENDING_SOL_REVIEW`；未完成则保留PARTIAL并交具体阻断/证据/下一步。新F05 `ACCEPTED_BOUNDED_F05_SUCCESSOR_A_THREE_CELL`仍需Sol独立复核，不授Formal Qualification。本包准备仅文档、Git和hash检查，不运行native或软件测试，不向Luna或其他线程发送消息。

### 16.1 执行续行与预算停点（2026-11-01；PARTIAL_PENDING_SOL_REVIEW）

以下保留执行者当时的停点与判断；其中“非正式预算耗尽/需新增额度”的判断已由16.2的独立复核更正，不能作为当前执行裁定。

DG04在冻结输入`develop-full@9af66009cd0634aec583f96db51ef88e13a824bc`上继续实现了既有Isaac Native-I/O/Core owners：USD v3 angular DriveAPI单位换算；源`solimp`残差曲线到公开mimic属性的候选映射及读回；source fixed-tendon `J^T` effort的公开写入/读回见证；Arm drive/schema/力限/关节类型和手指重复drive检查；F05 cube/support的公开质量、COM、惯性、碰撞和source-scoped滤波见证；以及公开raw contact actor-path到精确support collider的映射。S1增加float32场景值、保留Panda原有`physics:filteredPairs`、拒绝F05 task-scene过滤、compliance及contact收据缺陷的synthetic检查。`materialize()`仍fail closed。

这些实现没有通过DG04所需的完整source-consumer native门。Core S1 attempt013为10/10 PASS_SYNTHETIC_CORE_S1_ONLY（两段synthetic H5、12 tendon/4 equality/3 contact变异拒绝、native starts/physics steps为0、`runtime_admitted=false`）。最后一次N1 attempt007使用单Isaac App；worker返回于Core native adapter construction之后，却在读取bootstrap收据时错误索引不存在的`physics_steps_after`字段，未到达fixed-tendon/equality paired rollout或contact probe，且没有稳定worker receipt。supervisor progress停留在早期App阶段，无法提供可靠精确计数；因此ledger按冻结run最大值保守计32 attempted steps，而不采用supervisor原始0。process group已退出、shared lock已释放。worker字段映射、supervisor stale-stage exactness判断和关闭顺序已离线修复，但这些修复尚未经过新的native run验证。

DG04 formal Isaac N2仍`NOT_STARTED_BLOCKED_BY_REQUIRED_N1`. 当前非正式Isaac headroom已耗尽；完整6,400 attempted-step/2,400秒正式N2预留保持未动。新的N1所需预算需维护者重新授权，不能借用N2预留。attempt007之后的offline修复在本窗口新增了 source-tendon writer 边界验证：先验证有限非布尔数值、非空 actuator 名和小写 SHA-256 target/receipt identity，再保存 target；typed ACK 也拒绝无效 identity。attempt015/016针对性检查均PASS 1/1。完整 Core S1 attempt018为11/11 PASS；使用现有 `geochora` Python 与冻结 Isaac 6.2 OpenUSD Python package 做离线 USD composition，没有启动 Isaac App、native step或admission。attempt017曾因该解释器缺少`pxr`而2项无法完成，attempt018使用匹配OpenUSD读取路径后通过。N1 worker现在通过单一严格解析器核验 `isaac-public-physics-bootstrap-v1`、精确整数计数/公开counter差和timebase；attempt019解析器测试11/11，attempt020合并Core S1和worker合同测试22/22。`py_compile`、`git diff --check`、Module Skill checker和`quick_validate.py`通过，测试/检查日志见窗口`core_s1_attempt015`至`020`及`closeout_static_checks/`。没有安装依赖。provider-free S1/worker合同检查不证明 PhysX 每步source consumer，完整N1仍必须先通过；独立正式H5冷读未运行。

当前三路线状态见ignored [three_route_matrix.md](../../../../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f05_diagnostic04/window_001/three_route_matrix.md)：DG01 `ACCEPTED_BOUNDED_F05_DG01_MUJOCO_CORE`及DG02 `ACCEPTED_BOUNDED_F05_DG02_GEOPHYS_USD_CORE`仅限各自精确source/Task/Action/Core/build交集；DG03是`F05_DIAGNOSTIC04_PARTIAL_PENDING_SOL_REVIEW`，不授三路线整体接收或Qualification。DG02 PickCube R3跨provider差异保留`PARTIAL_REALIZED_STATE_OR_TARGET_MISMATCH`及原逐值计数，冻结oracle的`not_trajectory_equivalence=true`不变。

F06只准备了ignored [f06_entry_readiness.md](../../../../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f05_diagnostic04/window_001/f06_entry_readiness.md)。它把PickCube/MuJoCo 3.8.1 CPU作为首选scope候选，明确了现有Harness mock/proxy、固定CPU profile和source-bound Core构造缺口，建议新版本的桌面reachable reset/predicate；F05空中cube不复用为抓取初态。DG04未运行F06 Expert、20 seeds、Oracle、四报告、Judge或Qualification。完整run/budget/hash/保护文件状态见窗口`goal_progress.json`、`run_ledger.json`、`RESUME.md`与`source_consumer_decision.md`；未向其他线程发送消息。

<a id="f05-diagnostic04-window001-sol-review-and-window002"></a>

### 16.2 Sol复核与window002纠错续包（2026-11-01）

决定`F05_DIAGNOSTIC04_PARTIAL_REVIEWED_REWORK_REQUIRED`，复核实现/文档HEAD `ebeeea572880f783541e9b88b9ecf22c35f577c4`。保存的22/22是synthetic S1/worker合同证据；Sol未重跑pytest或native。原保护输入8,324/8,324、runtime12/12、隔离provider源2,854/2,854复算均匹配。DG03正式N2和source live门仍未通过，DG01/DG02有界接收和R3未决项保持。

三项返工：其一，Isaac总余额15,400步/约2,965.8秒与非正式子余额6,400步同时适用，保护正式6,400步/2,400秒后仍有N1的6,400步/约565.8秒；不能从非正式子余额再扣正式预留，故无需追加总预算。旧最坏扣账和失败原件保留。其二，当前柔顺齐次映射漏掉源reference里的第二层`d(r)`，应先按固定MuJoCo3.8.1源码和独立oracle核实并修复；这仍不证明完整PhysX等义。其三，paired探针只比较属性读回而没有物理响应的正反判别，不能拒绝“USD属性变化但solver忽略”的坏consumer。具体推导、数值点、代码位置和账本见ignored `sol_review_f05_diagnostic04_001/sol_review.md`及`offline_audit.json`。

新包`sol_f05_diagnostic04_002/`，ID `F05_DIAGNOSTIC04_WINDOW002_REPAIR_SOURCE_ORACLE_AND_LIVE_CONSUMER`。执行HEAD由Sol本次planning/Skill提交后的snapshot冻结，不复用旧输入。先离线修公式/oracle、独立版本USD、实际consumer detector与预算计算，再用原额度内N1最多1,400步/500秒验证；正式预留6,400 attempted步/2,400秒保持。live门成立后才运行完整3,000步正式N2、独立冷读及三路线矩阵。新窗口Isaac总计≤7,800步/2,900秒、必要CPU回归≤6,000步/600秒，全部新增native≤13,800步/3,500秒，且旧累计上限同时生效；不是增加总额度。主动最多8小时，旧window001至少2小时带入原12小时时间盒；压缩、换名和新turn不清账。

F06只准备入口；不执行F06/F07或授Qualification。保持同阶段分支、原只读provider和单writer，维护者人工转述后Luna才继续；本次Sol只进行离线复核和冻结准备，没有发送其他线程消息。

<a id="f05-diagnostic04-window003-policy-and-public-bridge"></a>

### 16.3 window002复核、维护者新执行规则与公开桥接裁定（2026-11-01）

window002输出HEAD `1d71aeab84a6fa576265e0cba33b886b9d83326f`，Sol复核为`F05_DIAGNOSTIC04_WINDOW002_PARTIAL_REVIEWED_PUBLIC_BRIDGE_RESEARCH_NEXT`。源齐次映射已修正，v4及27/27离线检查有记录；attempt004/005均未过实际物理响应门。attempt005读回频率差约1.2861Hz，残差差约2.6077e-8m、相对速度差约4.2409e-5m/s，未达原门，worker `-11`退出。原500秒N1子预算仅余约46.983秒，确实不足约89.123秒的App生命周期，因此原包停点有效。公开API检查仅界定已查安装范围，不证明任何公开桥接均不存在，也不把USD属性变化称为solver消费。

维护者随后明确要求暂不设置Luna累计额度、同一门多次未通过必须询问。该指令在DG04 window003取代旧累计steps/native wall/启动次数/Goal主动工时硬上限；所有历史消耗及旧formal reserve未动的事实保留，新执行不再用旧余额或预留作启动判据。每个run仍须有限steps/timeout计划、资源监控、共享锁及受控退出；正式N2仍是完整3,000步，内存/显存/并发保护和验收阈值保持。

具体提问规则：同一稳定gate连续两次实际验证失败后，必须停止该门后续native，交根因/观测/阈值/已试方案与明确选项并等待维护者或网页GPT裁定；不能靠新window/commit/压缩清零。用户明确选择新方案后，以有引用的decision epoch推进且保留原失败史。重复报告旧失败的自动turn不算新验证，未到达物理门的接口错误单列相应门，避免用不同traceback绕过规则。当前attempt004/005已触发提问，维护者答复为优先查明受支持的Isaac/PhysX公开桥接路径，再实施验证；Luna不重复询问同一决定，不原样重跑旧Set/Get路线。

新包`sol_f05_diagnostic04_003/`，ID `F05_DIAGNOSTIC04_WINDOW003_NO_AGGREGATE_QUOTA_ASK_ON_REPEATED_GATE_FAILURE`，实际输入HEAD由本次review/docs提交后的snapshot冻结。先同版公开bridge研究→原owner实现/S1及有缺陷敏感性的live判别→required门通过后正式N2/冷读→新F05三路线联合收口。若需要额外SDK/依赖安装下载或新语义裁定，先形成具体方案再询问；不放宽原禁止私有solver访问和重复Runtime的边界。F06只入口，F07/Qualification不执行。复核与授权转述记录位于ignored `sol_review_f05_diagnostic04_002/`及新冻结包。
