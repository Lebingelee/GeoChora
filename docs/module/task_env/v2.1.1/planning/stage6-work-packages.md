# G06a～c 工作分解与第一个实施包

日期：2026-11-15。设计输入：`41a09c87a7599f13adce9fb50501eb6378c2a17e`。本文是派发准备，不代表已经启动 agent、安装依赖或完成 native 验收。

以[现行实施方案](stage6-parallel-execution-plan.md)和[G06 Goal](../goals/06-parallel.md)为共同依据；维护者最近决定优先于早期交接的“至少两后端”“不做规模测试”等旧规划。canonical 主包覆盖三后端×两任务；R3 后端名单另定、独立接收。

## 1. 三个子阶段各自交付什么

| 子阶段 | 必须构建的工作 | 真实出口与下一阶段依赖 |
| --- | --- | --- |
| 6a：共同构建与设备合同 | 主环境／provider profile；依赖精确版本解析；复用注册、TaskBuildRequest、Scene／Robot／Controller 声明；batch layout、具名行映射；Dict action／B 轴 obs；episode／clock／RNG；CUDA publication／借用期限；same-step autoreset 与终止数据合同；必要 worker／IPC；Rasterizer 前置门 | 正常 `make_parallel_env` caller 到共同 builder、Controller、native batch 的真实链，不只是 schema。至少一条 Pendulum CUDA 链先贯通；6a 收口前完成代表性跨环境数据链与 Rasterizer 的两物理来源验证，并明确 GeoPhys 缺口及可实施上游落位。所有未完成交集仍拒绝，不宣称六格已通过 |
| 6b：canonical 六格与实际负载 | Isaac／MJWarp／GeoPhys native batch；Pendulum／PickCube 共同 TaskDefinition tensor 运算、reset 分布、batch Robot 信息；canonical source-bound effort；GeoPhys 必需公开 device／接触能力；Rasterizer 公共状态输入、多相机 CUDA uint8、窗口独立；普通 caller／记录读回；性能矩阵 | 三后端两任务 construct→reset→非零 step→state／task obs→可选图像→close；真实物理、行隔离、传动和相机身份。B=3 检查正确性，性能从 16 开始按 10 Hz 条件推进 256、4096，未达到扩容条件不伪造未测结果 |
| 6c：部分 reset 与整批重建 | 全 false／单行／多行 mask；错开 episode 的 same-step autoreset；旧 episode 终止图与新首帧；未选行状态／RNG／Controller 不变；同一 vector Env 内固定 Rasterizer 的 Isaac→MJWarp→Isaac；generation、旧命令／view 失效；半构建／失败／重复 close／资源释放 | 三后端部分 reset 真实验收；两个任务各自 A→B→A；独立读回状态／图像／episode 对应，worker／IPC／App 清理有结果。通过后接收 canonical G06abc；不得把 R3 或 G07 的完整 Solution 矩阵加入主包阻断门 |

6a 建立可执行的生命周期语义，6b 将其落到六格 native 能力，6c 在这些能力上做严格 reset／切换集成；不是把同一套 autoreset 分别实现三次。renderer 前置门在 6a 做，六格图像完成在 6b，跨 generation 行为在 6c。

## 2. 执行窗口

| 窗口 | 工作重点 | 预期活动时间／上限 | 必须返包的内容 |
| --- | --- | --- | --- |
| 6a attempt001（本次首包） | profile／接口实际接线＋MJWarp Pendulum 最短 CUDA native 链＋Rasterizer R0 的可执行验证；只补这些所需的共同能力 | 4～6 小时／6 小时；下载和锁等待另记，上限 90 分钟 | 代码、普通 caller、native 状态证据、R0 已验证边界／具体缺口、最小回归、规范自审、本地提交 |
| 6a attempt002 | 独立主审反馈；补跨解释器／第二物理来源／相机合同等未闭合项，冻结版本和 R0；不是再做一次完整调研 | 依据001返包再定 | 6a 每项出口与6b唯一输入；若 GeoPhys 上游必须修改，先冻结对应公开 API／代码落位包 |
| 6b attempt001 | 六格 canonical native 集成、batch Robot／Task 运算、相机与窗口四组合、B=16 性能基线 | 派发前按6a证据估时 | 六格实际状态与缺口，不把未完成 GeoPhys 改为可选 |
| 6b attempt002 | 按影响修复、独立物理／图像读回、满足条件的256／4096容量测量 | 同上 | 六格与性能矩阵完整报告；某渲染配置资源不足单列，不假装全部成功 |
| 6c attempt001 | mask／错开终止／A→B→A／失效及故障清理 | 同上 | 同次 transition、图像、episode 和资源证据 |
| 6c attempt002 | 独立复核、必要修复、canonical 总接收与交接 | 同上 | 对照原出口的有界接收；R3 待指定包单列 |

attempt 是实现＋修复＋验证＋返包的完整窗口，不等于一次测试或一次 native run。每子阶段最多三个普通窗口；第三次前重新评估实际 blocker，不能换名字重置计数。先审阅上一窗口的 diff 和证据，再生成下一包，不提前下发六份静态 prompt。当前不创建新线程或 worktree。

首包允许真实实现和必要兼容修复，但不是“做完整个G06”。MJWarp Pendulum 已指定为第一条闭环，不让实施者挑一条旧 host demo 冒充。Rasterizer 若依赖缺失的 GeoPhys 公开 API，报告最小上游改动表；此时首包可如实返部分完成，6a不能接收，后续不能跳过R0直接堆6b适配。

## 3. 性能与接收不混淆

- PickCube：传感器开／关 × 窗口开／关共四项；传感器开为 base＋hand 离屏观测，窗口关仍采图。
- Pendulum：没有传感器，仅窗口开／关两项。
- 各 task×provider 从16开始；当前档纯状态无窗口稳态整批控制频率达到10 Hz以上、运行正确且预算允许，才乘16。分别记录 control Hz、env transitions/s、sensor Hz、window FPS、峰值RAM／VRAM和限帧条件。
- 首包的B=3语义验证不是性能验收，不运行256／4096。6b性能结果使用真实 public step，包含承诺的任务计算和观测；不把孤立 physics kernel 吞吐当作用户频率。
- 同一仿真状态/相机配置下比较窗口开关；固定物理dt和substeps，不能关碰撞、简化资产、降低精度或偷偷减少展示实例获得PASS。

## 4. 派发入口

第一包正文：[G06a attempt001 goal prompt](../maintenance/work-packages/20261115_g06a_attempt001_goal.md)。用户可以将全文转交实施 agent；本会话仅生成文件，不自动派发。实际派发HEAD和prompt SHA保存在同次 ignored package index；如派发前HEAD变化，只允许确认本文的文档提交后继，生产变更必须重新核对，禁止reset工作区。

代码约束以该prompt中的“账本约束→代码归属→审查证据”表执行。总账的历史欠账不重开；但任何新实现重新引入同类问题，均不能通过本包代码接收。

## 5. attempt001 后的现行派发状态

生产输入 `3a277e03` 经[独立复核](../maintenance/reviews/20261115_g06a_attempt001_review.md)保持PARTIAL。首包不是仅缺文档：终止B轴／info、reset提交边界、正式pose publication、Rasterizer CUDA图像、第二来源与device Recorder仍需实现。[attempt002完整prompt](../maintenance/work-packages/20261115_g06a_attempt002_goal.md)已准备，包含有限GeoPhys公开render接口扩展的明确增量范围，须维护者整体派发后生效；本次未启动实施。预计活动6～10小时，上限10小时。
