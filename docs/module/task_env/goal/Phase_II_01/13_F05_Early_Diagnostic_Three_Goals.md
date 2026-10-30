# 新F05提前诊断实施：三个长期Goal

> **状态：维护者已明确指定提前诊断模式；DG01工作包准备，尚未执行；DG02/DG03为待适配基线。**
> 本页是该诊断方向的当前编排入口，与[11](11_F05_F07_Multi_Asset_Solver_Recovery_Plan.md)、[12](12_F05_F07_Execution_Playbook.md)及每次冻结执行包共同使用。只更新执行方式，完整required物理语义与最终三cell目标保留。

## 1. 授权、历史与真实起点

2026-10-30维护者决定提前进入诊断模式，要求将整个新F05分成三个长期Goal，由其转述给Luna持续实施；每个Goal结束后Sol根据实际报告调整下一Goal，直到三个全部完成。由此**暂停普通successor三窗口序列**，不派普通003；普通001/002及2/3历史不重置、不删除，也不改成接收。明确指定诊断后的窗口另记，不设固定attempt次数上限；执行时间、native累计资源和输入冻结仍严格有效。

旧F05三轮、OVERALL_PARTIAL、已接受精确cell及失败原件保留。successor001经Sol复核PARTIAL；002候选PARTIAL，诊断审计有进展但完整S0尚不在本次规划提交中自动接收。002输出295项清单已核对匹配；本轮源diff仅新增/改进审计与测试和文档，生产Core/provider三路线接线仍未完成、native为0。新诊断不把这些缺口当既成能力。

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

本轮仅创建诊断规划与完整prompt/冻结包，零软件测试、零native，不自动创建Luna工具Goal或向其他线程发消息。文档/Skill/hash与保护核对收据随包保留。
