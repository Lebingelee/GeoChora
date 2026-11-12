# E05～E10 U5 Task 与公共 guard 实施记录

状态：`IMPLEMENTED`（实施者自评），输入 `1ce601fa`。E09 的整体接收与完整 Solution 成功仍待 U7/E13 和独立主审；不把本次短程当作任务成功。[输入快照、精确计划、原始结果与日志](../../../../../workspace/maintenance/v211_e05_e10_u5_20261113_001/)保留。

| 检查点 | 实际结果与范围 |
| --- | --- |
| S26 | 当前 PickCube/Nut 正式目录分别为 7／5 个 tracked 文件；旧 Position/physical candidate UID 和对应独立 Task 入口未恢复。质量配置、任务 Solution 与实际资产声明继续保留。 |
| S27 | PickCube binding 构建时确定 source strategy，MJCF Position、effort 与 USD 都经既有 `SourceBoundTaskBuilder` 和同一个 `TaskBuildRequest`；Task 保留 cube/table、frame 和 reset 声明，场景声明移至 Task 文件。F06 delivery 校验、资产变体、native USD 路径绑定及严格 admission 由 Isaac adapter 负责。Nut 的声明到 MJCF 物化归现有 assembly owner，provider source 选项仍由 adapter 处理，删除一个只转发的 builder。PickCube specialization 从 1,207 减至 1,008 行，仍含必要的构建交接和较多 provenance/config 映射，**尚不能称全部 Task 文件已经很薄**；Recorder metadata 的共性继续由 U6 处理。 |
| S28 | 通用连续时间 guard、优先级、缺样本恢复和状态恢复移入已有 `planners/completion.py`；通用 interval 边界身份、时钟验证归 `controllers/canonical/feedback.py`。共享 native feedback 不再硬编码 Panda actuator8 或 2 ms × 5；Nut 自己严格检查 actuator8、2 ms、5 个样本、cadence、抓取条件、ack 与身份。通用层仍检查测量单位、有效期及边界，不因此声称其他 Robot/provider 已经通过 native guard。 |
| S29 | Pendulum／双轮车继续使用 Robot 的 existing-subject 共同编译链，不把 SDK、observer 配置或额外推进搬回 Task；本单元未修改其正式实现，U3/U4 的受测证据依代码影响保留。Nut task success、raw predicate、guard validity 与 Solution completion 保持独立；本次只运行一个 Solution interval。 |
| S30 | 两个正式 Task 的直接 caller 保留；`build_outcome_solution` 不再泄漏其临时 source snapshot，真实 source 检查和外部 Solution 与 Env 身份匹配均通过。历史 source/code SHA 不替换；本单元没有扩展 E11/E12 全库治理。 |

## 调用与职责

PickCube：`make_env → selected_binding → 一次 source strategy 选择 → SourceBoundTaskBuilder(TaskBuildRequest) → Task 场景/Robot 声明 → MJCF 或受限 F06 source adapter → Controller → Runtime`。两种原生 source 的 lowering 可以不同，不形成第二 Env 或推进 owner。Task 仍选择自己的 cube/table、语义 frame、任务参数和 Solution；F06 固定交付与路径只由 provider 校验。

Nut：`make_env → SourceBoundTaskBuilder → Task 声明 + Robot → assembly 的声明式 MJCF → provider source options → Controller → Runtime`。Solution 的通用 guard 调用 completion owner，真实 force sample 的身份/单位来自 feedback owner，Nut 自己施加 task-specific 时间、actuator、抓取与终态判据。Pendulum/双轮车继续 `Task 声明 → ExistingSubjectEffortTask → Robot → source/Controller → Runtime`，不伪造 Panda。旧诊断测试不为这些链增产品分支。

## 实际验证

- [定向检查](../../../../../workspace/maintenance/v211_e05_e10_u5_20261113_001/contracts-scenes/result.json)：22 项通过，含正式四任务共同请求、Robot 绑定、MJCF/USD 资产真实离线构建、F06 错交付拒绝、guard 连续性/快照、Nut 原严格条件、Solution 临时 source 实际释放；离线 USD 读取不称 native。
- [Nut MuJoCo/GeoPhys](../../../../../workspace/maintenance/v211_e05_e10_u5_20261113_001/nut-feedback-phase/native-results.json)：正式构造、reset、一个 Solution interval、再 reset 和重复 close；MuJoCo 显式 5 子步，GeoPhys 子步未独立计数。[外部 Solution](../../../../../workspace/maintenance/v211_e05_e10_u5_20261113_001/external-nut/native-results.json) 在释放独立准备 source 后与正式 Env 身份一致并运行一个 MuJoCo interval，5 个显式子步。以上早于仅影响 PickCube 的场景声明迁移；Nut source 与 guard 没有随该迁移改变。
- [PickCube CPU 路线](../../../../../workspace/maintenance/v211_e05_e10_u5_20261113_001/pickcube-routes/native-results.json)：MuJoCo Position/effort/装配 Panda、GeoPhys effort、MuJoCo→GeoPhys reset 切换均通过，MuJoCo 共 20 个显式子步，GeoPhys 未独立计数。其后 Task 场景声明迁移，[最终 MuJoCo Position/effort](../../../../../workspace/maintenance/v211_e05_e10_u5_20261113_001/pickcube-scenes-final/native-results.json) 再各测 5 子步；装配与 reset 的先前收据保留原源码身份，最后一次迁移只改变声明位置及 F06 资产 owner，最终影响由 U7 再核对。
- [最终 F06 Isaac](../../../../../workspace/maintenance/v211_e05_e10_u5_20261113_001/isaac-scene-final/isaac-position/result.json)：正式构造、reset、5 个显式子步、再 reset、重复 close 与 App close 完成；启动隐式推进未知，未重跑 RGB 或完整 Solution。U4 的 G05 双相机证据不冒称最终 F06 运行。
- 一次诊断误把 source receipt 当作有 `closed` 字段，已改为核对实际 snapshot 路径删除；首错与重试保留。未放宽历史 COM、R05c 或 SDK 日志限制。

## 总账与成效

已对照 TASK-01～04：旧 candidate 接线未恢复，通用 guard/反馈与任务策略按实际职责分开，existing-subject 简单任务按 U1～U4 证据保留。TASK-02 的整体可读性、跨 provider 组合及 Recorder metadata 仍需 U6/U7 与独立主审核对；不因 specialization 行数下降单独关闭总账项。

以 `1ce601fa` 为输入，tracked blob 项目 **1,381 → 1,383**、`task_env` **985 → 986**；新增版本诊断及本记录各一份，无整文件删除或重命名。生产代码 **+627／−584，净 +43 行**，诊断／测试 **+115／−2，净 +113 行**；文档以提交 diff 为准。通用 guard 约 260 行从 Nut Solution 接入 completion，约 145 行 PickCube 场景声明转至同任务声明 owner，二者为职责迁移而非项目删码。source adapter 和严格 Task guard 增量用于明确 ownership 与保全规则。

相对 5c 输入 `1f1359ee`，累计 tracked blob 项目 **1,361 → 1,383**、`task_env` **977 → 986**；生产代码 **+7,427／−15,739**，诊断／测试 **+5,738／−0**，文档和其他内容见提交 diff。累计包含此前所有事件，不能归功于 U5。
