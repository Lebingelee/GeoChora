# 新F05提前诊断实施：三个长期Goal

> **状态：DG01精确单元已接收；DG02 window002经Sol复核仍为PARTIAL，当前身份完整N2未完成。window003收口包准备待人工转述，继续同一Goal；DG03等待DG02接收。**
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
| DG03 Isaac/USD/GPU PhysX＋联合收口 | 查同版真实schema消费者并实施；原nativeIO/Appowner/control/state与退出收据；真实cell及三路线requiredfeature/Action/Task矩阵、受影响回归 | Sol独立复核三Goal和矩阵，登记新F05有界技术接收 |

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
