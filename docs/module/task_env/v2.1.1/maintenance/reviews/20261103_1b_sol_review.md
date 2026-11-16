# G01/1b attempt001：Sol 独立审核

日期：2026-11-03。结论：`ACCEPTED_BOUNDED_1B_DESIGN`，包含下述主审有界文档修正。接收的是统一表示设计交付；五份协议仍为 `DRAFT_FOR_DISCUSSION`，Scene-v4／ExecutionSpecV2 未实现、未获维护者最终批准，1c 未启动。

## 输入、提交和输出核对

- 执行 input：`498f03b55b3f557af962f98d2f7b5c9f543262c2`；output／commit：`f28a48a7c5747fc9448e93f3b1654d12b435ba0e`，为直接父子。
- 包 `V211_G01_1b_attempt001` 的 manifest 为 `ff6156eb22ce5ace2f29030c7e2bcc867be82670fab880c42cafbf98aa8789ab`；prompt 为 `067c572094d6e16ba2dfa5c76cdff37f84a46c7d3e39aff6b6f4dea9ad69568c`。
- 独立核对 report SHA-256 `96ca998b050c79d159d1a06ee63e9ad1043ac84471220b803c0ec9ddf651bbb5`、output manifest `c2ba266378908d6b4222e327ceec69dfc9c131410772ddf95766ce7e34d34a09`；清单内 7 文件大小／hash 全部匹配，共 71589 bytes。
- 原执行提交恰为允许的 7 个文档／JSON；GeoPhys pin `67da1165…`、两项保护文件、1a 原始输出保持。无生产代码、依赖、测试、provider 或 schema 实现变化。
- 审核使用实际 diff、协议正文、9 个案例、只读源码与官方资料。执行报告声明 native／physics／GPU／implementation tests 为 0；本审核也未运行这些项目。

## G0–G5 审核结果

| Gate | 主审处置 | 依据与限制 |
| --- | --- | --- |
| G0 | 接收 | 提交关系、允许路径、包／报告／输出 hash 与保护输入一致 |
| G1 | 接收 | 四类字段、owner／caller、现有 schema 与扩展建议具体；未新增顶层 TaskIR 或平行状态 owner |
| G2 | 修正后接收 | JointDefinition 的 7/6 等布局、required scalar bridge 和被动 free cube 有源码依据；修正进程部署／物理布局与 partial reset 描述 |
| G3 | 接收 | timebase 位于现有 Artifact hash，旧 decoder 精确版本保留；未来版本拆分不作为本版前置；扩展槽规则收紧 |
| G4 | 修正后接收 | P1–P4/N1–N5 仍是 planning-only；补 P3 context、P4 Scene 引用和 reset 区别；原 checker 只查 case ID／顶层复用，不能宣称验证了所有语义引用 |
| G5 | 接收 | 原始报告／命令／快照／hash、本地提交和窗口释放声明完整；主审修正另记提交，不改原 manifest |

## 主审修正及原因

1. **两个并行维度。**`RemoteBatchVecEnv` 创建一个 worker，worker 通过 `make_homogeneous_env` 持有 GeoPhys native merged batch；它不是每 env 一个 scalar session。物理实例布局与进程部署可组合，公开数据要保留 env→worker→local row 映射。源码为 `vectorization/parallel.py` 的 worker／constructor 及 merged-scene owner。
2. **正例不留悬空引用。**P3 的 rope/table interaction 原来没有桌面 context；补为只复用 P1 静态桌面，不继承 PickCube action／success／camera 能力。P4 原 Scene identity 指向 asset representation；P1 增加显式 Scene template 引用，P4 改为引用该 identity。
3. **Partial reset 与重建分开。**同配置 partial reset 只初始化选中 row，其他环境状态／时钟／Controller／episode 代次保持；更换执行配置才整批重建且无旧状态迁移。统一协议与 P4 均澄清，不改变既定需求。
4. **扩展不能绕过旧 codec。**仅新版本显式 extension 槽可定义 optional opaque payload 策略，旧精确 decoder 不因新草案而接受未知字段；必需或影响物理的未知项仍拒绝。
5. **不制造产品前置。**当前 Timebase／历史 hash 保留已是明确建议，未来重组不需要本版先决策。直接施力的类型化扩展与既有讨论一致，具体协议归 1c/4a；被动 cube 不自动成为 action target。惯量模型意图归后续资产验证，不因约 5% 差异阻塞协议。

原执行报告、findings、validation script 与 manifest 保持原字节；以上是审核修正，不能把原 checker 的范围追溯扩大。后续包使用修正后的 tracked 文档，并保护原始交接。

## 对版本演进建议的处置

同一 Scene owner 内有版本地增加 typed model／representation／mapping，以及在既有 execution owner 内显式分层，方向可进入 1c 联合设计。`Scene-v4`／`ExecutionSpecV2` 仍为建议编号；实现前要按消费者所需字段给出最小 schema、映射与兼容方案，不因文档使用名字就必须构建大型类型系统。

官方 [Isaac Sim 6.2 release notes](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/overview/release_notes.html)与 [Newton backend](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/physics/newton_physics.html)支持执行层级和发行依赖组合的设计依据；本审核查阅确认其版本条目。它们不是本机实际安装身份或 GeoChora runtime 支持证明。

## 后继与校验

1b 真实 output HEAD／commit 与本审核写入编排；其余 20 子阶段仍 PLANNED，13 实现目标／9 最终 cell 维持未启动／未运行。修正文档后复核文档治理 current、JSON、案例上下文／引用、DAG、draft 状态、空白和保护项；原有 96 条历史来源链接问题保持单列。

可准备仅覆盖 1c 的完整包：physics provider 双向协议、能力准入／原生翻译、最小状态／模型反馈、effort／夹爪／传动、reset／advance／失败回执和公开数据有效期。1d 保留 renderer 的完整动态更新／输出设计。协议最终接受仍由维护者审阅，后继由维护者手动转发，不自动执行。

原始 [1b 报告](../../../../../../workspace/maintenance/v211_g01_1b_attempt001/report.md)、[交付摘要](20261103_1b_representation_design.md)保留。
