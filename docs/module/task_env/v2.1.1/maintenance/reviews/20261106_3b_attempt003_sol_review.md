# G03/3b attempt003：Sol独立复审与接收

2026-11-06。决定 **ACCEPTED_BOUNDED_3B_NATIVE_EXECUTION**：3b在本包冻结的三条路线、公开构建／reset／控制／state／模型读回／记录／close交集内完成；普通attempt_count=3，本次结束，不需要3b人工诊断或第四次。依据是执行前明确的N08-v2及维护者转达的N09/G01控制边界澄清，**不把旧N08 FAIL改为PASS**。3c虽已按连续安排技术返包，仍待另行独立审阅；本次不接收3c或整个G03，不进入阶段4。

准确输入 `d27c5d6c8e12f0835b8e3fc56040971b6d41166f`；3b实现 `4e392f56`、`076c751f`、`9af222f0`、`071dc540`，交付 `305b1fa5f99e3430b8e71ee6d0ed61586f6556af`；GeoPhys `dc2685e28c6c916fb6403a2342c04e0d2520aef7`。复审时当前HEAD `29855741e4e0075336854a9f7708c67d78a8a0aa`已含3c；不将旧run改标为当前HEAD生成。原[执行摘要](20261106_3b_attempt003_execution.md)、ignored原包report/results/manifest均保持。

## 原缺口是否闭合

| 必需项 | 本次实际完成 | Sol决定 |
| --- | --- | --- |
| B3-01公共有效模型 | GeoPhys既有RigidSolver host IO从实际owned fields复制mass／COM／inertia、joint／actuator／equality／tendon，Core boundary委托，原session映射同次names并记录build facts；有独立provider提交及Core pin | 接收限定公开getter与实际consumer，compiled与effective继续分列，无额外step |
| B3-02物性／初始化／约束 | MJCF 12体／9关节／8执行器的源与实际值比较，Isaac公开tensor质量／COM／inertia及9轴／限位／驱动；六run同次reset读回，N09按11发布边界 | 接收原量纲／容差内的已声明交集，派生COM与authored分列，不要求跨源模型相等 |
| B3-03方向／运行／记录 | 三后端各hold/up与hold-only，六份T10/T+1=11，公共reader、同源／同sample／前缀可比、0.10s时钟 | 新N08-v2通过；默认关闭绝对下沉仍保留 |
| B3-04最终补偿 | 最终Nut19 350步保持＋Nut19/PickCube31各10步方向，同次三份H5及1850条子步贡献、首步实际力与限幅 | 接收有界Panda MuJoCo CPU补偿及本组最终验收，不外推其它provider／任意姿态／载荷 |
| B3-05缺项拒绝 | 真实F06来源进入生产selected preflight／materializer／native IO，以局部SDK终端替换覆盖缺mimic schema、DOF不符和缺get_link_inertias | 接收契约拒绝证据；此项为合成终端，不能作为native运行 |
| B3-06／07部署与兼容 | launcher及版本consumer事实复用，真实F06同次11×9测量速度，受影响回归与关闭配置语义，3c后另有旧默认F06复核 | 接收已测修复与适用性明确的复用；6.1不据此获得真实全闭环支持 |
| B3-08交付／释放 | 最终report/results/commands/numeric/manifest/final-state、提交与pin、writer/native/锁释放，原缺测与过程偏差保留 | 接收技术交付；计量未知与授权超时不抹去 |

## 独立重算的核心数值

Sol读取原始同次H5，经公共reader重算配对方向：

| provider | boundary10的up相对hold | 原绝对上移段Z变化 | 新方向门 |
| --- | --- | --- | --- |
| MuJoCo CPU | +0.407058 mm | −1.229934 mm | PASS |
| GeoPhys原生rigid CPU | +0.407040 mm | −1.230121 mm | PASS |
| Isaac6.2 PhysX CUDA | +0.404316 mm | −1.290584 mm | PASS |

各pair前6个发布TCP边界差0；记录float32分辨率界5.96046e-8 m，冻结方向门max(1µm,10倍前缀差,10倍分辨率)仍为1µm。六run各10步、11边界与0.10s一致。**这些结果证明正向动作效应，不证明关闭补偿时已经消除下沉。**

最终Nut19开启补偿，351边界最大高度偏差 **1.42037e-8 m（约0.0000142 mm）**，小于冻结10µm；首子步各臂计算支撑与provider实际执行器广义输出最大差 **5.95632e-6 N·m**，小于1e-4；三份H5的50＋50＋1750条贡献身份／手指字段／目标和力限幅检查通过，无clipping。两任务开启补偿后的10步绝对上移分别约PickCube0.406886 mm、Nut0.416924 mm。执行器内部输出不是外部力传感器，不能宣称通用JointEffort已完成。

Sol另从源数值与返回native值独立重算MJCF全部12体的质量、COM、完整惯量及9轴／限位，均满足原componentwise abs＋relative容差；不只读取预填PASS。Isaac源／实际轴最大误差约2.416e-7 rad小于1e-5；其USD cube COM依单个居中均匀collider条件派生，不能写成显式authored属性。

## N09与G01的采样边界

N09以reset＋10个已发布控制边界检查cube支撑、位移及源声明约束，源collision几何／实测状态及相应重建用于核对无机器人接触前提。六run所列数值符合原阈值。G01按350控制步的351发布边界检查保持。未记录的50子步cube状态、外物子步或连续接触遥测明确未测；它们不是后来追加的必需门。G02首子步、G04承诺的本体子步贡献、N07推进凭据则仍按原要求核对，不由本澄清免除。

本次接收不宣称两个发布边界之间绝无穿透／接触，不把机械臂子步加相邻外物边界的重建冒称同次外物native遥测；也不为这些未承诺量再跑宽矩阵。完整澄清已由维护者转交执行者并纳入原返包。

## 3c后改动与Isaac版本边界

本次检查了3c对shared common、configuration、Env／observation与worker的改动：新reset行为由显式reset_profile启用；GeoPhys getter、MuJoCo模型读回和gravity数学／apply路径未在3c中改动。当前源码上的Sol聚焦guard检查通过，3c返包中的旧默认F06 10步及reader是受影响路径的补证，不把所有3b旧run重标为新HEAD，也不代替3c整体复审。

3b原运行的父进程成功／close调用不能单独证明Kit自然析构正常。最新6.2 worker退出0与App／USD lease完整关闭回执来自3c最终运行；其策略是session、App、source、socket清理与ACK后由专用worker受控退出。仅采纳这部分作为当前共享close边界的定向补证，**不是Python／Kit自然析构已修复**；整个3c仍待审。

6.1是完成主目标后另做的辅助App检查：实际自报 `6.1.0-rc.26+release.49347.2d230af4.gl`，origin在指定独立安装内，证明启动／版本／来源；SimulationApp.close在300秒内未返回，按时限回收，不能记为正常close或完整runtime-valid。该项不是3b冻结的6.2必达门，故不推翻本次3b接收；6.1端到端兼容仍未通过。5.1及通用夹爪／灵巧手／装配树选择不因此完成。

## 计量、过程与审阅记录

3b从02:25:44到08:48:40，墙时 **22976.53 s，约6小时23分**；原06:25:44截止后8576.53 s约2小时23分，依维护者授权仅整理／文档／释放／绑定，不能倒填为240分钟内完成。用户转述的Goal约2小时19分是另一计时口径，不是3b该墙时，也不能当作已独立测得的3b主动时间。native/source已记录1044.454 s约17.4分钟；主动与等待未完整分别计量。

已知owner发起4708子步，失败SDK bootstrap和部分provider启动未知，不能填0或声称全量上界已证。树RSS峰值约6.32 GB、全卡用量约2.95 GB，未测独立进程VRAM／完整PID树；原资源口径保持。一次无双锁源解析、失败fixture／reader、后续3c丢失的测试观察句柄等历史不重写；后者缺结果不计PASS，后续重跑按所属run记录。已披露问题不通过重跑“补账”或删除失败解决。

Sol核对 **354个3b输出，23,711,733 bytes，manifest全匹配**；原三保护untracked和Menagerie pin保持，当前provider pin对应独立提交。独立14项无SDK导入检查通过；六份配对H5＋三份最终补偿H5通过公共reader重新读回与数值重算，native／SDK launcher／physics／GPU／render均0。独立材料在维护者工作区workspace/reviews/V211_G03_3b_attempt003_sol_review，原Terra包未修改。

本次只接收3b限定出口并更新当前编排；不触发自动消息、执行对话、3c实施续作或阶段4。下一项是对已经返包的3c作独立主审，不是重新派3b返工。
