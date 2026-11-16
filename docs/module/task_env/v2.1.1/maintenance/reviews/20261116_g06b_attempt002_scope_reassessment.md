# G06b attempt002 主审与 attempt003 前范围重估

日期：2026-11-16。状态：**PARTIAL_NOT_ACCEPTED；实施按维护者要求暂停；attempt003 未派发。** 本文纠正主审派发中扩大的验收要求，并按原始 G06b 出口重估剩余工作，不授予完整六格或通用求解器资格。

## 1. 复核基线与责任

Core `f8c43d61163e6774b3869875842337b427781fe4`；GeoPhys `dd393187983798abac0e8d99c2426d64d4a8aa5e`；Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。两仓 tracked clean；保护的 untracked `MUJOCO_LOG.TXT` 摘要独立核对为 `3b08b858f62dcbaa6521802455c76126f9876a3d6727c7586db90c94296ed6a8`。本次仅审查源码、提交差异和落盘证据，离线核对数组与摘要，没有启动物理、窗口或 GPU，没有恢复暂停的 goal。

原始依据是 [G06b 出口](../../goals/06-parallel.md#6b)和 [attempt001 工作包](../work-packages/20261115_g06b_attempt001_goal.md)。它们要求真实六格、逐行动作与状态、接触、隔离、图像、记录和性能；明确允许短程手指接触见证，不要求完整抓取 Solution、R3 或不同引擎逐点一致。

身份核对：仓内attempt002原稿SHA为`3438b9fc1a4466beaee39c6bf455d991ea49ea8daba495b2176087550c7852a5`；[执行窗口保存的转发文本](../../../../../../workspace/maintenance/v211_g06b_attempt002/prompt.md)含Markdown转义，SHA为`36b8f5217b17ee66860e737a7d3479453a86a6c00ae58e5a1eb128aabf28aab1`。两者字节不同，编排的package字段记录仓内原稿，执行证据保留其实际文本身份。

Sol 在 [attempt002 工作包](../work-packages/20261116_g06b_attempt002_goal.md)中有三项设计问题，应承担派发责任：

1. 把一次受控轨迹的 2 mm 实验界限提升为三组输入、逐子步的统一硬门，没有先论证它对不同接触模型和动作载荷的适用性。
2. “反作用力、残差、速度／能量合理”没有明确可结束的判定方式，给接触力真值研究留下无限扩张空间。
3. 将 scalar 对照作为定位工具，却没有明确 scalar 已有缺陷何时退出 G06b 阻断清单；允许最小共有修复不等于必须重构 scalar mixed 求解。

发现 10 mm 级异常并修复配置透传是必要工作；问题在于修复后没有及时回到阶段出口。不能把全部责任推给执行者。403 份 supervisor 记录、约 6431 秒监督运行及 2755 行技术笔记反映调查分支很多，但不能据此计算实际额度消耗，也不能直接宣称违反 native 时间预算。

## 2. 三个争议的结论

### 2.1 2 mm 从哪里来

[attempt001 的冻结说明](../../../../../../workspace/maintenance/v211_g06b_attempt001/geophys-controlled-contact-frozen.md)只对 B3、指定 seed、60 步受控动作规定 2 mm，并明确不是通用 solver／CCD 保证。随后 Sol 在 attempt002 §2.3 和 A02-P2 中将其扩大到三组动作。它不是维护者最初给出的统一物理标准。

现有证据还说明：GeoPhys discrete、32 次预算的三组 B3 数据最大重叠 **1.715 mm**，已经满足被扩大后的这项几何条件。MuJoCo 的另一个 seed 参考轨迹约 6 mm、MJWarp 约 5 mm，提示统一标准本身不成立；这不应成为继续阻断已满足该几何条件的 GeoPhys 的理由。

attempt003 的范围建议：保留历史阈值和所有测量，撤销其“所有后端／动作通用标准”的地位。当前 32 次配置及原输入可保留为有界回归，不事后把它放宽到 10 mm，也不新增一个没有依据的通用数值。新的物理异常须关联实际任务失效、源映射错误或自身动力学矛盾，再确定针对性的测试。

### 2.2 接触力差异是不是阻断

不是单凭差值就阻断。MuJoCo 的[接触模型说明](https://mujoco.readthedocs.io/en/3.3.7/computation/index.html#soft-contact-model)把软接触和硬接触模型视为不同近似；因此这里不把软接触瞬时力乘 dt 当作 GeoPhys 硬接触离散冲量的真值。它仍可以帮助发现单位、方向、映射错误。

本仓当前 `batch/contact.py::_solve_contact_sweep_world`采用目标速度、有效质量和累计冲量的法向更新，与源软接触配置不是同一求解模型。两者应保留各自声明；不能声称 solref／solimp 完全等价，也无需为 G06b 新实现一套软 EFC 来追平力值。

仍要保留真正的正确性要求：真实几何接触、合法方向和输入、有限状态、未丢失控制或状态、世界隔离，以及所声明范围内没有持续穿过桌面或数值爆炸。只有出现具体反例，才追查质量响应、冲量或约束。不要求每个观测冲量有外部真值，不要求接触点数和每点力相同。

已有力学检查不应被“不是完整力真值”一句话全部否定。例如同初态首次桌面接触的冲量力矩重建与角速度差误差约 `5.50e-9 rad/s`，是有效的局部自洽证据，虽不证明所有时刻。[读回](../../../../../../workspace/maintenance/v211_g06b_attempt002/first-contact-budget-torque-001/readback.json)

### 2.3 mixed 是否必须改进

**不作为本轮无条件必修项。** 当前正式 batch 路线为：

`GeoPhysDeviceBatchSession → GeoPhysNativeBatch → GeoPhysRigidBatchRuntime → materialize_rigid(homogeneous_batch) → BatchedRigidSolver → _solve_constraint_rows_world`。

`batch/constraints.py`在每个 world 内循环 contact、limit、equality、tendon 后提交 warmstart。这里已经有共同迭代 owner。报告中的 scalar 路线则先解 generalized contact，再经 `contact/freebody_route.py`解 free/static 等 rows；两条路径不同。

scalar mixed 的阶段性法向速度破坏有真实证据，应保留为上游缺陷。它说明 scalar 不能无条件充当 batch 的数值真值，而不是证明 batch 缺少耦合求解。只有新证据说明该缺陷进入当前 G06b 生产调用链或本轮修改造成必须修复的兼容回归，才重新列为阻断。

同理，已提交的 pure FREE armature 修复是实际修复，但不是当前 PickCube batch 接触问题的总修复。不要继续借此把所有坐标路线、Schur 原型或通用 mixed 重构加入 attempt003。

## 3. 当前实现与证据应怎样判定

| 项目 | 本次判断 | 对下一包的影响 |
| --- | --- | --- |
| 六格 B3 正式 native 链 | attempt001 已有实现和有界证据，未发现需要重建的依据 | 复用；只补受本轮影响的路径 |
| 迭代预算透传 | 已修复 request → native config，并报告 resolved budget | 冻结显式配置，不隐藏在任务专属分支 |
| GeoPhys B3 三组轨迹 | 32 次预算最大桌面重叠 1.715 mm；当前 pin 记录与原读回输入一致 | 几何改善有可复核依据，停止重复寻找跨引擎一致 |
| 真实双指接触 | 下移组 row0 有 102 个子步同时具备双指正物理法向冲量及独立源几何接触，91 个同时有桌面反力 | 足以支撑该短程接触已发生；不是“尚无双指接触” |
| 非相邻 reset | 当前 pin 两组读回通过，未选 row 随后一步 qpos/qvel 与无 reset 对照误差为零 | 已有有界证据；6c 的完整压力覆盖不要提前全搬过来 |
| B16 渲染停滞 | DLPack 显式租约修复已落地；当前 pin MJWarp 双传感器＋窗口 800 public steps 及关窗后采图通过 | 原停滞有修复证据，不再重复定位同一问题 |
| 完整渲染／记录出口 | 最终 renderer 下各 provider 接线和性能索引尚未收口 | 这是实际余项，按影响补最短代表回归和缺项 |
| scalar SHA | 旧控制回执欠账，非当前 device 热路径缺口 | 延续另包，不借本次迁移全部回执 |

证据入口：[最新摘要](../../../../../../workspace/maintenance/v211_g06b_attempt002/brief-for-sol.md)、[几何读回](../../../../../../workspace/maintenance/v211_g06b_attempt002/contact-trace-b3-32-full-001/independent-substep.json)、[双指同阶段读回](../../../../../../workspace/maintenance/v211_g06b_attempt002/geophys-batch-solve-fingers-readback-001/solve-stage-fingers-readback.json)、[当前 reset](../../../../../../workspace/maintenance/v211_g06b_attempt002/reset-geophys-b3-32-current-pin-001/independent-reset-current-pin.json)、[接触边界 reset](../../../../../../workspace/maintenance/v211_g06b_attempt002/geophys-contact-reset-current-pin-readback-001/independent-contact-reset.json)、[800 步监督记录](../../../../../../workspace/maintenance/v211_g06b_attempt002/render-live-b16-current-pins-800-001/supervisor.json)。

本次独立离线核对：当前与原三组 control 轨迹及完整 contact trace 共四对 NPZ 文件 SHA 均相同；500 子步 B3 的 qpos/qvel/body pose 和所存接触数组均有限。这里使用 hash 是离线复核，不进入 step。既有几何／接触 reader 的结论据此可用于这些相同输入，不等于本次重新运行了 native。

仍有数值局限应如实记录：32 次预算下桌面法向速度残差峰值约 0.440 m/s、p95 约 0.0203 m/s，不能声称硬约束精确收敛。但单个残差不是原 G06b 自动失败条件，更不能据此无限增加求解器研发。若要升级为阻断，需要给出它导致本轮所需任务行为失效的证据。已有数据足以先判短程接触和稳定性范围，无需等待通用力真值。

## 4. 性能和资源才是尚需具体收口的部分

[现有18项索引](../../../../../../workspace/maintenance/v211_g06b_attempt002/performance-b16-after-scoped-views.json)为：6项沿用状态样本、8项旧 renderer 未复验、1项修复后实测、3项 Isaac 渲染 RESOURCE_LIMIT。这个分类不是当前完整门状态，不能原样复制为最终结果。

尤其索引的 GeoPhys PickCube 纯状态项仍指向旧样本，而 attempt002 实际已保存显式32次预算性能：B16 **10.894 Hz**，B256 **6.697 Hz**，样本均满足原统计长度。它们在当前 pin 之前，batch 数值源码未因 pure FREE scalar 修复改变；应审查并记录可复用关系，不直接采用旧默认预算的较高 Hz，也不无理由重跑。日志分别在 `performance-geophys-off-32-001` 和 `performance-geophys-b256-off-32-001`。

按维护者的纯状态 >10 Hz 扩容规则，32 次配置在 B256 停止，B4096 为 **CONDITION_NOT_MET**，无需尝试分配或继续优化以强过10 Hz。既有37.6 GiB容量估计可保留为另一项信息。MJWarp修复后的双传感器＋窗口样本 public step约8.77 Hz不是失败；10 Hz只用于无传感器无窗口的扩容。

Isaac B16 三个渲染组合的预检是当时主机 MemAvailable 不足，不能被改写成该机器永久不支持，也不能当作通过。下一包先在串行释放本包资源后复核可用量与估算。若仍无法运行，保留小B正确性与 RESOURCE_LIMIT，完整B16门是否允许资源例外需维护者决定；不杀其他进程、不加swap、不调低相机规格冒充同一配置。[预检](../../../../../../workspace/maintenance/v211_g06b_attempt002/isaac-b16-render-preflight.md)

修复后的 renderer 回归应覆盖 GeoPhys 与 Isaac 的实际 pose／camera 接入以及记录读回；可以将相机、窗口、reset、H5 核验合在少量普通 caller 运行中。旧 H5 文件、旧测试结果不会因 pin 字符串不同自动失效；先看输入和实际受影响代码。8项旧渲染不等于8种新故障，也不授权重复全部历史矩阵。

## 5. 接线与代码规范复核

本次抽查公共 GeoPhys device provider、rigid batch bridge、batch constraints 和 renderer 新增模块，未发现以 PickCube／Panda／任务名判定的生产分支。关节／free joint／传动系数由 source layout 和 binding 解析，canonical 动作写入同一 native batch；渲染接收设备 pose，不替代物理状态。

新增 `render/rasterizer/pose_transfer.py` 有明确生产调用，负责设备 pose 复制与租约寿命，不是探针框架。初始化时的 shape／source／传动／能力校验和 close 的错误聚合有实际边界责任，不应为“简洁”删除。现有同步设备复制有成本，但没有理由在本轮承诺零同步或扩成跨SDK零复制工程。

应控制的膨胀主要在诊断面：g06 runner 已3530行，技术笔记2755行；长度不是单独缺陷，但不能继续把每个假设变成永久CLI分支。attempt003 新增代码只落实际故障owner；复用少量 reader／runner，禁止把实验开关、私有反射补洞、资产名、每步SHA或通用字典层加入公共区。不借收尾之名重新展开整仓Env／Robot／诊断重构。遵循[优化账本](../../planning/post-5c-code-project-optimization-diagnostic-ledger.md)。

## 6. attempt003 的可行范围与结束条件

建议将下一包定为“canonical 六格验收收口”，不定为“接触求解器继续研发”。先完成以下四个工作单元：

1. **证据与配置冻结**：以当前 pins、显式 discrete／32 配置及源输入建立最终证据映射；将已有几何、真实双指、reset与原六格结果逐项归位。标清 source物理数据和 native接触模型的差异，不承诺软硬接触等价。
2. **受影响链路最小回归**：补最终 renderer 下 GeoPhys／Isaac 的普通 B3 状态—双相机—记录—关闭；已有MJWarp800步不重复作为耗时压力门。只有出现当前生产缺陷才最小修复，改动后复验相关链。
3. **性能表补齐**：复用可追溯、同配置、影响可解释的样本，只测缺项；处理Isaac现实资源限制；纯状态逐档规则保持。B16重复三行可证明容量和隔离交集，不追加任意随机初态泛化门。
4. **规范与交付**：精确pins、正式示例、设备数据路径、H5与关闭结果、18项状态和扩容决定一致，随后交独立主审。6c的整批切换、R3和完整抓取仍另包。

退出研究支线的规则：对每项新实验写清它要决定哪个原门及可能导致的代码动作；如果不同结果都不会改变G06b接收或修复决策，就不运行。跨引擎力值不一致、scalar mixed反例、未实现soft EFC、接触点数不同，不单独启动新原型。发现确切且可达的生产缺陷，可以修复；需要通用新算法则返独立技术议题，不在本包循环尝试。

第三次尝试前的开源参考复核：[MuJoCo接触模型](https://mujoco.readthedocs.io/en/3.3.7/computation/index.html#soft-contact-model)支持区分接触建模；[MuJoCo Warp solver源码](https://github.com/google-deepmind/mujoco_warp/blob/main/mujoco_warp/_src/solver.py)以world轴组织状态和求解临时量，适合借鉴批量隔离，不支持把不同引擎的力值当作统一真值。该上游main阅读仅作设计参考，不替换已冻结本地4.0.1依赖，也不引入新运行库。本项目已有batch共同迭代，无需复制上游求解器才能完成原门。

**可行性判断：当前主链足以进入有界验收收口；没有证据要求先完成通用mixed或软接触求解器。尚未接收的实际理由是最终证据／性能矩阵与资源处置未闭合，不能再笼统写成“接触力差异未解释完”。** 本文不是attempt003 goal prompt；维护者确认范围后再冻结完整包，不恢复暂停执行。

文档检查：`git diff --check`通过；current文档校验仅报既知的保护日志基准差异，实际日志摘要与派发保护值一致。没有为消除该提示修改日志。本次同步current-state与orchestration中的attempt计数、当前pins及阻断描述；历史prompt和报告保留原文。
