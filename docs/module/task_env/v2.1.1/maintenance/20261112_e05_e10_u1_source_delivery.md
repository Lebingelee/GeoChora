# E05～E10 U1 source 实施记录

状态：`IMPLEMENTED`（实施者自评）；实施输入 `5dd3d29a`。本页记录本单元的模块关系和证据入口；独立主审及维护者接收待后续整体工作。总台账和 E05 的其余职责尚未结案。

## 组合范围与实际调用

四任务仍使用 `make_env → ReferenceTaskBinding → SourceBoundTaskBuilder → Env`。下表中的 source 和 native 映射描述实际受测路径，不代表任意资产组合已支持。

| 正式任务／主体 | source、主体及 Controller 交接 | 受测 native 映射 |
| --- | --- | --- |
| PickCube／一体 Panda，MJCF Position | Task 物体声明及 Panda recipe → source 意图与 scene projection → Controller → reference source binding | `panda-v1/joint1..7` 对应 `joint1..7`；cube free joint 为 `PickCube_joint` |
| PickCube／装配 Panda，MJCF Position | 同一构建阶段；Robot 声明 arm/hand 和固定 edge，MuJoCo lowerer 核对 Panda 资产 profile、任务保留根和实际 writer | arm 的 `actuator1..7` 与 hand 的 `actuator8` 分属两个 writer；hand 原生关节使用 `probe_hand_` 命名空间 |
| PickCube／一体 Panda，USD | USD delivery 使用自身 snapshot；source adapter 组合 Task 对象和 Robot articulation 路径，Controller 绑定后交 native session | USD 映射由 `bind_declared_usd_paths` 和真实 delivery 校验；不把 USD source 作为 MJCF 场景解析 |
| NutAssembly／一体 Panda | Task 声明 Nut、peg、reset 和资产参数，Robot 提供 MJCF 与 actuation；provider 物化 contact 选项，共同 compiler 拥有 snapshot | `square-nut-v1 → SquareNut_joint`，Panda 关节与 actuator 使用实际 source 名称 |
| Pendulum | `ExistingSubjectEffortTask` 使用 Robot source 和 Task 声明编译 artifact／source，校验 intent 与实际 effort writer | `pendulum_hinge → pendulum_torque` |
| 双轮车 | 同一 existing-subject effort 构建阶段；Task 给平衡状态与 reset，Robot 给主体、两个轮驱动与 source | 左右 wheel hinge 分别映射 `left_wheel_torque`、`right_wheel_torque` |

统一的是声明、source 和 Controller 的交接合同；MJCF 与 USD 的物化，以及一体与装配主体的 native lowering 有不同实现。PickCube 在 source 物化前冻结输入意图；scene projection 后的 source 及 Controller writer 再形成绑定请求。两次身份对应不同的 source 边界，不能把原始 source hash 当作 projection hash。简单主体的意图在共同 effort 构建过程中校验，不因此声称每条路线都生成同一种 V2 receipt。

| 模式 | 当前支持与拒绝边界 |
| --- | --- |
| reference | MJCF 的一体 Panda 引用任务内已有 Robot；GeoPhys 只注册此类 source composition。简单主体使用 existing-subject effort 路线。 |
| replace | MuJoCo 支持受限装配 Panda 替换已有任务主体；保留 Task 物体与自由关节，并校验 Robot edge、资源 writer、source closure 和名称映射。GeoPhys 的 reference adapter 不接受替换。 |
| add | intent/request 类型能表达没有既有 Robot 的添加，但当前正式 adapter 和四任务入口没有实现该路线；不能因为数据类型存在而声称支持。 |

`TaskSceneSource` 的 MJCF 字节、source closure 与 execution snapshot 是不同层次；provider 使用已验证的 snapshot 及具名映射，close／失败路径释放其 lease。USD 使用 `UsdRuntimeSourceV1` 和 USD snapshot，仍有用于控制运动学的明确 MJCF 字节；这一兼容字段不表示 USD 被按 MJCF 加载。renderer 消费 source／state 的完整调整留 U4，本单元未改变 renderer 生命周期。

## 定向证据与边界

- [MuJoCo 六条短程](../../../../../workspace/maintenance/v211_e05_e10_u1_20261112_001/native-final/native-results.json)：共同构造、reset、一个非零 interval、状态／clock、再 reset 和重复 close，共 70 个显式子步。后续仅影响固定附件 profile 的更改通过[装配 Panda 复测](../../../../../workspace/maintenance/v211_e05_e10_u1_20261112_001/attachment-owner-native/native-results.json)，5 个显式子步。
- [GeoPhys Panda effort 与 Pendulum](../../../../../workspace/maintenance/v211_e05_e10_u1_20261112_001/geophys-final/native-results.json)：相同短程边界通过；native 子步未独立计数。后续 Panda 固定附件专用变更未触及这两条 reference source 路线。
- [附件／构建检查](../../../../../workspace/maintenance/v211_e05_e10_u1_20261112_001/attachment-owner-check/result.json)：24 项通过，包含真实资产读取、不同声明的通用结构与 Panda 专用 tendon 拒绝、资源所有权和失败清理；不全是纯检查。[USD 离线检查](../../../../../workspace/maintenance/v211_e05_e10_u1_20261112_001/usd-final/usd-final-result.json)7 项通过，包含实际 delivery 与 stale 拒绝。
- [Isaac Position 受影响原生短程](../../../../../workspace/maintenance/v211_e05_e10_u1_20261112_001/isaac-source-final/isaac-position/result.json)：正式构造、reset、非零 interval、第二次 reset、重复 Env close 和 App close 成立，显式推进 5 子步；启动隐式推进未知。本次未重测 Isaac RGB；完整 Solution、任务成功及最终记录仍在 E13。
- [MuJoCo 原生与 GeoPhys physics × MuJoCo renderer-only RGB](../../../../../workspace/maintenance/v211_e05_e10_u1_20261112_001/source-rgb-final/native-results.json)：两条 source 受影响路线通过 reset、step、第二次 reset 的 task RGB 边界和 close；MuJoCo 显式推进 5 子步，GeoPhys native 子步未独立计数。此短测不替代 U4 的 renderer 职责、重复采集及资源合同核查。

旧 R03b/R06b 诊断 worker 引用已经退休的 `position_candidate`，不是正式 caller；有价值的固定源与篡改拒绝已迁入版本诊断。历史结果按原时间与身份保留，不以旧 fixture 继续要求产品兼容。

## 本单元与总账对应

| 检查点 | 当前 owner 与结果 |
| --- | --- |
| S01 | `TabletopScene` 拥有桌面，Robot 声明 Frame/初始通道，MJCF adapter 物化；compiler 不再识别 Empty/Panda。Empty 与 Empty+Panda 实际 source 编译已测，旧 Panda XML 与 base 离线字节对照一致。 |
| S02 | Task 声明物体与组合参数，Robot 提供 source recipe 和 attachment edge；MuJoCo adapter 物化受限 Panda 组合，USD adapter 组合声明路径，Nut contact 选项由 provider lowering。Task 内其他 source 接线待 U5。 |
| S03 | reference／replace／add 的实际边界和先意图、后 writer 的时序见上表；无 adapter 的模式不宣称支持。 |
| S04 | generic 两实体固定连接与 Panda 精确资产 profile 分离；生产保留 hash、版本、license、传动和 native 名称检查；实验生成迁至版本诊断。 |
| S05 | MJCF/ USD source、原始 source、snapshot lease 和关闭边界分列；过期、外来 source 与 Controller 失败清理有定向检查。 |
| S06 | source snapshot 的创建集中于编译 owner，按实际 Robot/provider 计入 source provenance；四任务调用和不同 source 身份见上表。 |

本单元结束对照总账的 SRC-01～04、SUBJ-02 和 TASK-01/02/04：source 子项已有上述实现和证据；TASK 目录精简、provider 完整准入、renderer 格式消费及跨事件整体退出仍分别由 U2、U4、U5、U7 处理，不能据此直接关闭整项或整个 E05。旧导出和完整 Solution 的历史边界保持不变。

## 文件和代码变化

统计基线为本单元输入 `5dd3d29a`；仅计 Git tracked 文件及本单元新增文件，排除 gitlink、保护输入与 ignored 证据。相对 stage 5 基线的累计数在 U7 和各事件最终交付时单独统计，不把旧成果计成本单元优化。

本单元新增 4 个文件：Panda source profile、版本诊断的顺序配方与合同检查、本文；无整文件删除或重命名。预计 tracked blob：项目 1,368 → 1,372，`task_env` 976 → 979。固定附件代码按职责拆分到上述 profile 和诊断配方；以有序完全相同行粗略匹配，分别有 145 行和 24 行来自旧固定附件文件，这不是实际净删除。其他旧代码以函数粒度调整，不标作整文件迁移。

按最终文本 diff 分桶：生产 Python **+470／−377，净 +93 行**；诊断／测试 **+313／−1，净 +312 行**；文档 **+64／−5，净 +59 行**。新增和删除中包含上段迁移的相同行，不能把它们当作独立新增或删除成果。

生产新增代码承担 Robot 声明、source profile 和 provider 映射检查。原四个未跟踪保护输入的摘要及 GeoPhys、Menagerie pins 均与输入快照一致。

相对 5c 接收点 `1f1359ee` 至 U1 提交 `1a2bc947` 的累计 tracked blob：项目 **1,361 → 1,372**，`task_env` **977 → 979**；按文件路径分桶的 Python/C/C++ 等生产代码 **+5,985／−14,671**，诊断／测试 **+5,114／−0**，文档 **+1,456／−94**，其他文本 **+125／−945**。累计数包含 E00～E04 和历史迁移，仅用于对账，不视为 U1 的新增成效。
