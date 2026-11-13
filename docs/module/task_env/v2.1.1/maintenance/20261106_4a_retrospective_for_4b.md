# G04 4a 复盘及 4b 准备经验

> U6 整理说明：本文中的旧目录路径保留为历史记录；该目录已按维护者授权退休。所选证据的旧路径、SHA 和现存位置见 [G04 有界证据入口](../../../../../workspace/maintenance/v211_e11_e16_u5_20261113_001/stage04/README.md)，旧目录及其完整 manifest 不保证可恢复。

2026-11-06，维护者要求在建立 4b prompt 前复盘 4a，并把可执行经验用于后续开发。此页是对既有记录的分析和 4b **准备建议**，不构成 4b 执行包、native/GPU 授权或新验收门；当前 4a 已按[独立主审](reviews/20261106_4a_attempt003_sol_review.md)有界接收，4b／4c 仍 PLANNED、attempt0。阶段目标以[原 G04](../goals/04-control.md)为准；状态以[编排索引](orchestration.json)为准。

## 时间线与计时口径

| 窗口 | 已观察事实 | 对应教训 |
| --- | --- | --- |
| 001 | 12:52 启动后，跨 provider 宽泛搜索误输出私有 solver 片段，首次窗口提前释放。第一次续作误选含真实 `make_env/reset` 的测试，至少两次 source 解析违反当时 source=0，提前返包；第二次续作积累 fake／纯契约，但 source 和真实 session 不能完成。三段仍是**一次普通 attempt**。 | 定点 public owner 和完整测试副作用审查；先弄清正常构造的必要动作，再冻结可执行权限。保留事件，不将本包限制作原规划要求。 |
| 002 | 14:06–14:57，允许 source 解析后，真实 registry/config/source 构造和 fake 终端有增量，提交 `0e229a72`；真实 physical session reset 仍 fail-closed，4b 计划待处理。 | 必须核对实现路径最早阻塞；纯 source、fake terminal 和 native build／write 不可互相替代。 |
| 002 授权续作 | 约 15:26–16:03，维护者授权最小 native 后，A05／MuJoCo 真实接入、7 次短跑及 ACK；主审发现持续 BodyWrench 在各 substep 使用初次投影。其后又识别候选与 4b 案例的 frame／参考点不一致。 | 不能只测固定状态和首次写入；同时冻结运动、持续、坐标、参考点及缺陷敏感测试。 |
| 003 | 17:06:44–17:31:13，构型变化的 fake 先在旧实现失败，之后逐 substep 更新，错误积分器拒绝，真公开入口短跑；17:37:57 Sol 提交有界接收。 | 保留失败证据，在一个授权窗口里修、测、重试并交付；主审仍区分 fake、ACK 与真实物理测量。 |

从 001 首次启动 12:52:27 到 Sol 接收记录 17:37:57 约 **4 小时 45 分 30 秒墙钟**，包含手动转发、间隔、讨论和主审；各段主动／等待未可靠分离，不能把它当作实现者持续编码时间或算力用时。002 实际墙钟约 50.9 分钟，003 约 24.5 分钟；原 002 预算 360 分钟未耗尽。此口径不能从个别 Goal 耗时倒推。

## 为什么反复卡住

1. **权限与真实调用链矛盾，是 Sol 的编排失误。** 001 把 source 解析定为 0，正常任务构造却需要 source snapshot／XML；002 放开 source，仍禁止 native，却同时需要依赖真实 build/compiled 状态才能证明的事项。执行者遇到外部授权边界时返包是按冻结条件行事；不能把窗口未用满归为执行者消极。001 确有不应发生的私有路径误输出和 source 限制越界，也不能因为限制制定不合理而抹掉。
2. **4a 契约／计划与 4b 真实物理验证曾被混在一起。** 4a 必须完成类型、生产消费、可信 capability／拒绝和 4b 路线计划；4b 需三后端真实 7＋2 及最小物体／Robot body 外力。Sol 的 002 包禁止 native 的同时对 4b 方案要求实际读回才可闭合，造成“先运行才能规划、又不能运行”的矛盾。后续还需我澄清：不应把全部后端外力实测变成 4a 门；已开放却错误声称支持的 capability 又不能忽略。[002 重评](reviews/20261106_4a_attempt002_sol_reassessment.md)、[续作主审及补充](reviews/20261106_4a_attempt002_recovery_sol_review.md)保留责任与结论。
3. **用静态／写入证据覆盖时间相关语义，导致真实实现缺陷晚发现。** 002 续作的真实 session 和 ACK 证明了构造及提交，但初始广义力固定用于多个子步；静态 frame、单次 ACK 和 fake build 不能证明移动 body 上持续力正确。003 的多构型测试能在旧实现上失败，才证明测试能发现该缺陷。真实路线目前仍仅有 A05／MuJoCo 3.8.1 CPU／implicitfast 构造、写入、刷新与 ACK 的有界证据，并无独立物理力测量。
4. **测试目标／参考点容易“看似相同”。** A05 候选的 body-frame 力和 origin-reference 零总矩，不等于 4b 计划的 world-force、偏置作用点处零矩；在单位姿态、1 N、1 cm 的示例中原点矩分别为 0 与 −0.01 N·m。两种语义可合法存在，但不能把一种的短跑当另一种结果。A05 source closure `aa4ca97b…`、PickCube `02f12b11…` 与 Isaac F06 `dc2a87a7…` 亦不同，证据只能在真实同源、同条件时复用。
5. **工程边界与交接的摩擦放大了普通问题。** 整文件测试比选定 node 有额外 fixture／source 效果；CodeGraph 索引漂移及宽泛检索曾输出无关 private solver。代码／草稿、报告、Goal 状态和 writer／锁是不同事实；Goal active 或 complete 本身不表示 writer 占用、技术通过或 Sol 接收。外部决定必要时才交回；普通失败在同一授权窗口内继续修复。

## 给 4b 准备的具体做法

这些是下一个完整包的设计输入，不直接成为额外验收条件；若与维护者指示或原目标冲突，先按权威目标和明确授权调整。

1. **先映射原目标和阶段，不追加交叉矩阵。** 按原 4b 明确三后端真实 7＋2、共享 Controller／direct effort、源约束、至少普通物体与 Robot body 的有界真实外力及组合／清除。4c 的 reset 切换、迁移后成功留 4c；不把最终 7b 三 seed 九格、新装配 Robot 或每个 wrench case 的三后端全交叉擅自追加为本轮前置。附加装配 Panda 只在主能力稳定、包内已有预算时按维护者采纳安排早验证，完整两任务留 7a。
2. **每个目标先画生产路径和最早能力边界。** 对实际 `registry → config → source/Artifact → selected binding → session → provider public API → step/readback`，区分 MuJoCo A05 与 PickCube、GeoPhys native rigid 与 actuator/control 标签、Isaac 6.2 PhysX 与其实际 extension；逐项列已实现、仅候选、待扩展 owner、不能通过即需的最小动作。GeoPhys 的 UI 弹簧点力、Isaac 文档接口都不是已有通用 typed wrench 的 4b 实证；不能通过读取私有 solver 补接线。
3. **先建立“要求—动作—证据—权限—预算”的一致映射。** 每个必需 gate 指出确切 source、provider/device、实际命令、允许的 source 解析／构造／reset／step／读回、锁、观察点和预期；让计划与授权不自相矛盾。仅可从 build／运行确定的质量、接触、M/Jc、API 或设备状态，以确定的 preflight 与失败处置处理，不伪造静态事实；不能让 4b 全部真实运行被无关的前置问题长期卡住，也不能跳过原 required gate。
4. **先冻结能检出缺陷的最小对照。** 对 7＋2 分别检查真实 source/order/axis/sign/units、tendon/mimic 可实现子空间、驱动叠加和单通道漏写。对 body wrench 预先明确 force 与 torque 的单位、表达 frame、point、moment reference、保持时间和清除；覆盖至少一次姿态变化与有偏置／非零矩的解析对照，再测试所要求的真实执行。不要仅用首子步或 ACK 证明持续外力；不要把驱动 contribution 或估算当 measured force。
5. **Oracle 和预算在运行前完成可行性审查。** 现有 [003 的 4b 候选计划](../../../../../workspace/maintenance/v211_g04_4a_attempt003/4b-plan.md)可复用，不是运行批准；其 41 次 build、600 总步、180 分钟与固定阈值仍是候选。核对三路线实际可用 public 模型／观测、软约束和精度，给缺数据的可执行预检与负责 owner；优先符合原 gate 的最小独立数值对照，不把非必要的特定矩阵 API、每个假设都已实测或未经评估的极严阈值变成新门。结果出现后不为变绿放宽阈值；如设计前提不成立，记录原因并按原规则获得方案调整，而不是无限期重采样。
6. **按实际资源定义一个有修复空间的窗口。** 将 source／native build／bootstrap／每个物理步、三后端 reader/close、锁等待、CPU/GPU／进程树内存、磁盘和报告所需时间纳入估算；逐次与累计分别记账，未测为 unknown。历史 3b 全程约 6 小时 23 分、source/native 约 17.4 分钟但主动／等待未知，不能把 Goal 时长当 native 或用作 4b 的可靠耗时预测。双锁和使用者已授权的资源约束继续执行；不默认一次失败就消耗一次 attempt。
7. **只复用同一身份且未受改动影响的证据。** 源闭包、运行代码、provider/version/device、命令、frame、积分器和 cadence 不同就单列；只重跑变更影响的检查和原 4b 必需实验。对纯逻辑测试事先逐 node 追踪 import/fixture/factory 与 source／SDK 副作用；CodeGraph 若索引过期，只针对已知 Core 或 public provider 路径，误匹配即停止并防止输出私有内容，不重建全库、不跨私有路径搜索。
8. **一次完整返包再独立主审。** 同一 attempt 允许预算内定位、修复、受影响重试和记录失败；按最早失败层排查，相同 signature 两次局部修复仍失败或三次尝试无新证据时，按现有 troubleshooting 写三个可区分假设和最小实验。确需新权限、外部输入、锁协调或预算上限才如实停；记录实际 HEAD、源码、run 与输出 hash、未测、writer／双锁／进程释放。维护者继续指定并手动转发，Sol 不自动消息、创建对话或运行 native。

## 下一步

在维护者允许建立 4b prompt 时，先基于当前真实 HEAD 和此回顾复核上述现有候选计划、接口可行性、真实预算及必要授权，形成覆盖原 4b 全部出口的一份完整包，再由维护者手动转发。不得预设新的 source、GPU 可用性、实测力或模型一致性；也不要因仍未实测而重开已按范围接收的 4a。
