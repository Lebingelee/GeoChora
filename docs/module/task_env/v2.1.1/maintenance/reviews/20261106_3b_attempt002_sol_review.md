# G03/3b attempt002：Sol独立复审

2026-11-06。整体决定 **REWORK_REQUIRED_3B**；保留执行者的 THREE_B_TECHNICAL_PARTIAL 和原 N08 FAIL。**有界接收已完成的根因对照、launcher／F06记录修复及 Panda MuJoCo CPU 重力补偿的计算与最终短程行为**，不将其扩展为最终补偿全验收或整个3b通过。普通 attempt_count=2、active_packages=[]；003尚未准备或派发，3c未启动。3a既有接收不变。

输入 `470c3ef90bf2179916733f0049444bedefe07e3d`，实现 `be88c5cd4ac823c997040d3166f7ea14e069b610`，返包 `5a3d6c7d4a5dc306ad2de4612694ea86259ea12e`；复用 codex/v211-stage3。[执行摘要](20261105_3b_attempt002_execution.md)与 ignored `workspace/maintenance/v211_g03_3b_attempt002/` 原件保持不变。

## TCP问题的当前结论

维护者已在执行对话明确“通过审阅并同意实施”，并给出默认关闭、本体范围、基座旋转、重复补偿和限幅要求；这是原002包之外的有效追加授权。Sol只读核对了该人类消息及装配树建议，没有向执行对话发送消息。

Sol独立从原始11边界轨迹重算：0192旧基线与002输入在同一 MuJoCo source、实际 ResetSample、R3、动作和时间基准下，q、qdot、TCP、time最大差均为0。两者原 N08 都下降1.229934 mm；hold-only下降1.636992 mm，上移动作相对hold产生+0.407058 mm效果。因此本次已测下沉是此前就存在的行为，不能继续列为“3b新引入TCP偏移”。结论仅覆盖该配对交集。

维护者的 Nut19 首子步诊断显示：位置目标初始接近实测q、qdot为0，驱动力矩近零；joint4零速bias约+21.506 N·m，反馈随后建立相应支撑。与新增补偿计算、首子步输出和保持实验结合，足以支持并接收**所测固定基座 Panda 位置伺服缺少初始重力前馈的定位与修复**。不把该诊断推广为所有provider、接触或载荷漂移的唯一根因。

最终代码的开启补偿短程日志，已由Sol独立按边界和来源重算：

| 公开入口／样本 | 前5步保持的Z变化 | 后5步上移的Z变化 | 最终回执与限幅 |
| --- | --- | --- | --- |
| PickCube31，MuJoCo CPU | +6.04e-10 m | +0.406886 mm | 50次贡献／50次力采样，手指字段齐全，目标／力限幅均0 |
| Nut19，MuJoCo CPU | +6.21e-10 m | +0.416924 mm | 同上 |

两例各10个控制步、0.1 s并正常close；q／qdot／TCP有限。它们是新增开启配置的行为证据，**不覆盖默认关闭的三条历史 N08 FAIL**。长时 Nut19 350步实验的最大高度偏差1.42037e-8 m、首子步最大力矩差5.95632e-6 N·m可保留为有效机制证据，但运行早于最终保护和手指回执细化；最终短程没有同次H5，不与较早H5拼接成最终记录验收。

## 实现与可保留成果

1. 重力计算复用 PandaKinematics，读取来源绑定的七臂连杆、hand和两指质量／COM、连接及当前q；世界重力按实际基座旋转变换，外物不纳入。源与编译模型检查在MuJoCo adapter内完成。位置贡献按已核实仿射执行器换算，保留原动作、计算贡献、调整目标和执行器输出的区别；不能冒称通用JointEffort或力传感接口。
2. 开关默认关闭，仅 selected Panda、MuJoCo CPU、in_process；混合执行器、固定附件、GeoPhys、Isaac、worker开启均不受支持。已检查的数学、关闭配置、外物排除、不可表达手指合力和限幅测试可接收；实际多姿态长期稳定性仍未验证。
3. launcher修复沿 production metadata probe、worker bootstrap 和 worker环境核对保留 python.sh 的路径上下文，Core／GeoPhys优先级及SDK来源核对继续存在。真实consumer fixture覆盖空格路径等相关情况；不需要重做全SDK组合巡检。
4. F06真实九关节速度、ee Frame和边界身份已沿既有 typed state→Recorder→H5贯通。Sol在SDK导入隔离下通过公共reader独立读回最终三路线：每条10 transitions／11 boundaries，Isaac额外11×9实测速度有限，source/request/materialization检查通过；F05兼容证据保留。

## 仍须闭合的3b工作

| 剩余项 | 当前事实与最小后续工作 | owner／边界 |
| --- | --- | --- |
| 最终有界补偿记录与稳态 | 最终短程行为通过；补一次最终源码Nut19固定姿态稳态记录与独立H5读回，并按实际改动决定PickCube最小记录回归；保持和首子步分别验收，不重跑完整任务 | 现有MuJoCo session、selected Env、Recorder及外部验收驱动 |
| GeoPhys实际物性公共读回 | 当前compiled输入与公共动态通道不能证明solver-effective质量／COM／惯量／轴／传动／约束。先冻结最小provider公共快照方案及实施归属，再决定是否需要独立GeoPhys提交和pin更新；不能让Core执行者反复搜私有字段 | GeoPhys公开runtime边界输出；Core现有GeoPhys session消费。原包 `geophys-public-model-gap.md` 是提案，不是接口已实现 |
| 原物性、reset及约束缺项 | N01–N06／N09按现有逐量结果补真实缺项，区分source、derived、compiled、native-effective；支撑／接触条件和pre/post-settle分别记录。复用已验字段，不能用一项API缺口把其他缺项全部归零或标过 | source、provider build facts、ResetRealization与外部数值比较 |
| required API/schema/DOF拒绝 | 生产consumer仍缺少部分缺项反例，补真正到达相应边界的最小案例；不重开坏输入矩阵 | 现有Isaac native IO／selected admission |
| 方向响应判据 | 原50ms窗口绝对位移受初始下沉混杂。接受“匹配hold/up与hold-only用于区分方向”的分析方向；相对增益门只能证明动作影响，不能单独证明保持或位置精度。三路线配对及噪声／reset一致性未验证，尚未批准新最终数值门 | Sol与维护者先冻结新案例／版本，再交执行者验证；原记录原判据保留 |

真实6.1 App仍NOT_RUN，符合“主目标完成且明确有余时才辅助”的授权条件；不是为推进3b强加的额外门。6.1/6.2离线消费链也不代替真实6.1能力证据。

维护者确认的[装配树连通子段方向](../../planning/gravity-compensation-assembly-tree.md)保留。自定义子树、跨实体附件、外接夹爪、灵巧手及其各自由度贡献**未实现**，不属于原3b缺陷，也不作为新的3b阻塞。它们应在4a控制贡献与装配合同设计中明确本版范围、provider能力和后续独立包；此安排不自动将其移出v2.1.1，也不授权启动4a。当前有界实现不能提前宣传这些能力。

## 独立检查与证据适用性

Sol核对208个输出，共13,752,201 bytes，manifest全部匹配；最终HEAD／branch、两pin及原两保护文件保持。另保留已有untracked诊断提案 `planning/stage3-gravity-compensation-proposal.md`，不stage、不覆盖。独立材料在维护者工作区 `workspace/reviews/V211_G03_3b_attempt002_sol_review/`，包括audit.py、independent-evidence-audit.json及离线日志，未写回Terra原包。

以原SDK隔离guard复核受影响9组测试：**75 passed，1项被guard阻断**。该项是 `test_pickcube_isaac_projection_preserves_task_semantics_and_binds_runtime_frames`，在Panda来源组装导入`scene`时停止；这不证明产品缺陷，也不计为Sol通过。执行者的76 passed属于其原执行条件，不与Sol结果相加。Sol未放行Scene／OpenUSD／引擎解析，native／App／物理步进均0。独立H5读回与轨迹计算不消耗native预算。

执行窗口8422.37 s（约140.4分钟），已知物理子步下限3909，首次失败reset启动数unknown，无法证明原4000上界；此为既成计量缺口，不为补账重跑。两只读reader约0.1 s重叠、运行中源码修改后稳定重跑、冻结时间手填错误、暂停时writer账面未释放等偏差按执行报告保留。最终writer与自身进程／双锁已有释放收据，不追加整机扫描。

本次文档及当前状态同步经 current 文档检查零错误、96项既有历史链接问题原样保留，git diff --check通过；TaskEnv Skill静态checker通过。Skill只修正复审状态和导航，不新增能力说明；未创建新Agent进行冷启动，不宣称已完成完整Skill刷新验证。相应检查和限制写入独立复审收据。

## 003前的安排

第三次是最后一个普通窗口，先完成重评，不能再派“继续排查TCP”的开放包：根因对照已闭合，无需再次跑旧HEAD；先明确GeoPhys公共接口／pin依赖、新方向案例及最终Panda验证范围，再一次性冻结剩余required门。保持三种可区分风险：实现／接线缺项、上游公共模型合同缺口、oracle瞬态前提；各自已有证据和owner，不再用重复三后端短跑替代修复。

本次只复审并更新当前编排，没有创建003执行包、派发消息、执行native或进入3c。若未来003整体仍未接收，按既定规则转维护者主导人工诊断，不自动004或改名续作。
