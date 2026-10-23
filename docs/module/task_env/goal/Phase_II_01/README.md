# Phase II-01 修订规划交付包

2026-10-23；REVISED_DRAFT / AWAITING_MAINTAINER_GOAL_DAG_APPROVAL。本轮加入独立R07，候选7父Goal/22切片；输入为前版develop@234da21b的规划及本次R07指令。仅文档，尚未批准最终 Goal/DAG，未开始 P00。唯一建议执行表为 [07](07_Execution_Order_and_Acceptance.md)；总体定位见 [00](00_Phase_II_01_Blueprint.md)，本轮结果见 [validation receipt](validation_receipt.json)。

## 文档入口与责任

| 文档 | 修订后的责任 |
| --- | --- |
| [00 总蓝图](00_Phase_II_01_Blueprint.md) | 基线/范围/owner/相互独立与批准顺序 |
| [R01](01_R01_Logical_Robot_Assembly.md) | typed logical membership与hash DAG |
| [R02](02_R02_Composite_Control_Profiles.md) | 独立leaf控制与binding/admission/fault |
| [R03](03_R03_Physical_Attachment.md) | 真实source、MuJoCo首条装配候选、GeoPhys拒绝与策略 |
| [R04](04_R04_Dynamic_Camera_Consumer.md) | public observation/capture/storage消费边界 |
| [R05](05_R05_Native_Rate_Feedback.md) | 正式Provider sample/cadence合同 |
| [R06](06_R06_Compatibility_and_Regression.md) | 顺序/机械/历史/兼容与证据治理 |
| [07 执行表](07_Execution_Order_and_Acceptance.md) | 7/22 DAG、required envelope与停止条件 |
| [08 审阅交接](08_Codex_Phase_II_01_Planning_Prompt.md) | 下一轮独立审阅/维护者审批指令 |
| [R07部署/Agent成本](09_R07_Benchmark_Deployment_and_Agent_Cost.md) | 固定五LIBERO审计/部署与成本协议、RoboCasa feasibility；不隶属R06 |
| [planning manifest](planning_manifest.json) | 机器可读DAG、source/probe出处与文档hash；非实施receipt |

<a id="references"></a>

## 固定外部参考与采用原则

访问日期统一为 2026-10-23；固定版本URL而非滚动latest/develop。Isaac Lab官方Release在2026-10-20发布v3.0.0，页面显示commit短ID e3f7d9f；本包不把未解析的完整commit编造为已核验。文档页面版本为v3.0.0，内容可在发布后维护，不冒称所有页面字节均来自Release commit。Isaac Sim参考独立固定6.1.0，不推定它与Lab3.0.0是本项目依赖组合。

| 固定官方资料 | 使用范围与本项目的推论 |
| --- | --- |
| [Isaac Lab v3.0.0 Release](https://github.com/isaac-sim/IsaacLab/releases/tag/v3.0.0) | 多backend方向是参考；GeoChora能力仍只看自身source/Evidence，不迁移第三方支持声明 |
| [v3.0.0 Backends and Presets / Factory Dispatch](https://isaac-sim.github.io/IsaacLab/v3.0.0/source/concepts/backends_and_presets.html) | 显式配置选择、构造时lazy dispatch、physics/render独立准入；R02采用完整profile选择后校验的编译原则，复用本项目现有factory |
| [v3.0.0 SceneDataBackend / SceneDataProvider API](https://isaac-sim.github.io/IsaacLab/v3.0.0/source/api/lab/isaaclab.scene_data.html) | producer刷新native数据，consumer显式remap/lifetime；R01/R04/R06复用现有typed publication，不引入Warp数据ABI/第二state store |
| [v3.0.0 Asset Preparation for Newton/MJWarp](https://isaac-sim.github.io/IsaacLab/v3.0.0/source/how-to/prepare_asset_for_newton.html) | 分离common/solver-specific语义、核对root/inertia/contact/drive实际消费；R03必须逐项验证source，不把导入成功视作执行等价 |
| [v3.0.0 Policy Interface Compatibility](https://isaac-sim.github.io/IsaacLab/v3.0.0/source/how-to/transfer_policies_between_physx_and_newton.html) | 有序action/obs、时序/hold、reset/机制一致性要独立审计；R06加入mapping/coupling对照；本阶段不承诺policy transfer |
| [Isaac Sim6.1.0 Robot Assembler](https://docs.isaacsim.omniverse.nvidia.com/6.1.0/py/source/extensions/isaacsim.robot_setup.assembler/docs/index.html) | Mount Frame对齐、Fixed Joint、child Root Joint处置与Collision Filtering分开验证；R03用自身versioned intent与native lowering，不采用USD/Kit ABI |

以上各项为工程设计推论，不是要求复刻外部架构或安装依赖。外部页面访问失败的探索URL不作为已读取支持来源；最终使用上表可定位版本页，SceneData API内容经官方搜索结果可读，完整页面抓取有间歇失败，未声称做过逐行源码审计。

## Source / Provider / Controller 风险与影响矩阵

| ID / 优先级 | source / owner / 范围 | 已知风险与状态 | 受影响后继 / stop或处理 |
| --- | --- | --- | --- |
| SRC-1 P0 | 独立Arm+Hand→MjSpec导出→GeoPhys a53 importer | site-size dialect真实拒绝，NOT_ADMITTED/BLOCKED；非所有GeoPhys Attachment结论 | GeoPhys该路线停止；Provider importer修复或versioned source normalization均须单独审查，MuJoCo候选可独立推进 |
| CTL-1 P0 | canonical Position Profile / plan / Env | 当前整Panda writer不能直接拆成Arm-only/Hand-only | R02b/c与R03c；leaf contract/adapters与真实隔离S2/S3，不删唯一writer保护 |
| MAT-1 P0 | RuntimeSource/materialization/typed state | 当前single Robot/dual independent roots准入不等于attached pair；native tree可能跨两个canonical Entity | R03b/c；显式新identity/mapping/admission，错root/源/资源拒绝 |
| ID-1 P1 | artifacts/Assembly refs | 同Entity子组件与Entity owning混淆、alias冲突/循环hash | R01→R02/R03；typed refs、hash有向分域、严格版本派发 |
| MAP-1 P1 | importer→canonical→native slots→Controller/Recorder | joint/body/actuator顺序或Hand equality/tendon误解释，重复驱动 | R02/R03/R06；逆映射/置换负例/独立资源运动与H5 |
| CAM-1 P1 | CameraSession→Observation→H5 | state-only与generic passthrough断点；identity/calibration/labels/缓存与峰值内存 | R04b/c/P99；strict reader/同边界/预算/fault/teardown |
| FDB-1 P1 | GeoPhys public Reader/native sample | a53常规host500Hz未建立；CPU/CUDA同步成本/phase/freshness | R05b/c/P99；owner合同gate；不阻塞Position子链 |
| HIST-1 P1 | B04a/eb870/Reader governance | 缺原bytes，历史兼容未证明，自动retire或延期不允许 | R06c/P99；恢复/退休/继续延期新决定，否则blocked |
| VER-1 P1 | Scene/Artifact/H5/Profile/pin/UID | 静默改旧schema或把旧pin证据移到新source | 每slice/P99；独立version/受影响回归/原日志保留 |
| DOC-1 P2 | 旧consolidation validator | 文档计数与全历史非文档scope已有失败 | 原样记录，不提高阈值；新文档link/anchor与本次docs-only另做精确校验 |

## REVISE_PLAN 逐项修订对照

“已修订”仅表示文档问题有对应文本；不表示实现/Provider批准或审阅结论自动变为ACCEPT_PLAN。

| 前次审阅项 | 修订定位 | 文档处置 / 仍待决定 |
| --- | --- | --- |
| P0-1 GeoPhys source路线未成立 | R03事实表/策略、07第二Provider | MuJoCo CPU first-required候选；保留site-size拒绝，无新S2/S3；Provider策略未选择/未实施 |
| P0-2 独立leaf执行合同缺失 | R02 Leaf表/预检、R03b/c | Arm-only/Hand-only Action/Target/Ack/Required State/TCP/资源；原算法复用，不能双完整Panda充证 |
| P1-1 embedded子组件/Entity/hash歧义 | R01两类成员/非自指/mapping责任 | owning/ref-only分开、typed目标、深度与稳定路径；schema/API名字仍需P00设计审议 |
| P1-2 early R03a滞后 | R03切片、07、manifest | R03a依赖P00；R01a/R05a/R04a/R06a可并列，18切片数不变 |
| P1-3 Camera两条Observation与H5消费 | R04合同/资源、07 | public Env/strict metadata reader/calibration/labels/identity/T/T+1/fault明确；未实现 |
| P1-4 正式Reader与required envelope | R05、07 | 保持CPU/CUDA×100/500Hz为建议required；owner先批准，不降格diagnostic，失败需scope change |
| P1-5 恢复/退休不能自动消除延期 | R06原件与gate、07 | 保留B04a/eb870；新阶段恢复/退休/继续延期均需独立决定，未决blocked |
| P2 版本引用状态 | 00、manifest | v2.0.0分支/Tag已另经授权推送并回读；无main promotion/Release；冻结PhaseII不回写 |
| P2 dual builder依赖test helpers | 00/R03 publicS3边界 | 未来在现有task/source owner提取，不复制Runtime/Recorder；本轮不改代码 |
| P2 每slice执行合同不足 | 07逐slice表/通用Gate、R01–R06 | 每slice有前置/owner/证据/Stop；具体run预算和tolerance要在授权P00/开工前冻结，不能伪造已实测 |
| P2 外部引用滚动版本 | 本页固定参考表 | Lab3.0.0/Sim6.1.0；只借鉴原则 |
| 本轮新增顺序与mechanism保护 | R06映射表、R02/R03 | permutation/逆映射、Equality/Tendon/真实actuator、policy interface分域，未实施 |

<a id="provenance"></a>

## 输入保全、验证与待批准项

原 ZIP、解压草案与前次审阅文件未覆盖；本机保全与本轮校验在 ignored `workspace/maintenance/phase_ii_01_plan_revision_20261023_001/`。前次原始probe副本在该目录 `prior_review/`，文件hash/逻辑path见 [manifest](planning_manifest.json)。未把这些本地原始探针作为可随Git获取的新运行Evidence；新clone如无原件，应标“indexed but raw unavailable”，不能凭摘要重做成功证明。

本轮实际检查与既有测试/compile探针严格分栏，见 [validation_receipt](validation_receipt.json)。没有重跑Assembly NativeS2/S3、CameraEGL、Native-rate实验、完整A–D、NutAssembly矩阵、485区间R1或Qualification。当前工作仅文档，不需要修改Skill/API能力说明；TaskEnv Skill做静态检查，原说明仍描述当前实现。

待维护者批准：最终7/22/依赖；MuJoCo CPU首个装配required与GeoPhys第二Provider状态；独立Position leaf最低接口；R04 required Camera消费范围；R05双backend正式host合同范围；历史原件恢复/退休/继续延期的独立处置。未批准前P00 NOT_STARTED，不开始R01–R07或自动发布v2.0.1。

## 本轮R07修订与Scope Risks

- [09 R07](09_R07_Benchmark_Deployment_and_Agent_Cost.md)包含五Task逐项source/native语义/init/asset审计、ownership、真实部署门槛、Agent成本/独立review与RoboCasa feasibility；native source code读到了不等于Core已支持。
- R06b新增R03b前置；P99改为R06c+R07d；旧18slice保留目的，其余依赖不变。五Task所选初版R02/R03/R04条件前置各为none；新recipe必须显式加入exact条件边，不能隐含required依赖或全局强加Camera/force。
- R04澄清现有CHW uint8录制与public HWC float32的量化/转置差异，不改变Recorder；成本协议不以float RGB存储为必要。
- 本轮基线已fetch：develop/public develop=234da21b…；冻结PhaseII与gitlinks未动。前版validation_receipt由该固定Git提交及本地tar恢复，本轮receipt仅记录本轮检查，不将前次14tests或compile probes重记为新执行。

| 风险 | 状态 / 影响 | 待审议处置 |
| --- | --- | --- |
| arbitrary BDDL source/reset/admission、contact/site/fixture-joint/evaluator缺口 | 五LIBERO部署当前NOT_RUN，已有BLOCKED_CORE风险；语义不匹配可NOT_REPRESENTABLE | 原task/source/runtime/observation owner扩展review，不能换简单task/用旧UID冒认 |
| native MountedPanda torque-motor/双finger position actuator/OSC/20Hz与Core候选不同 | 机器人/源/控制身份不能迁移，依赖版本未验证 | 锁actualassets/build/Action/frame/cadence和boundedsmoke，不保证控制器算法等价 |
| per-asset许可与完整source closure | 检查XML/tree refs≠完整网格bytes/许可验证 | R07b verified manifest gate；外部安装与可分发来源分开 |
| RoboCasa移动base/复杂fixture/大资产与rolling robosuite依赖 | 仅固定源码feasibility，无五Task执行承诺 | 单独go/no-go建议/版本lock，额外执行另批 |
| Agent usage/billing/active time缺失、self-score或native成本对照缺位 | 不能估算成测量或宣称因果成本下降 | null/reason、session/log/hash、独立human评审；controlled研究另定预算 |

R07a中protocol、functional motion/semantic oracle/tolerance、预算与任务顺序须部署前冻结；R07c指定五Task之一被阻塞或不可表示，P99保持阻塞，等待维护者精确scope decision。全部七Goal仍candidate；本轮建议审阅结果 **REVISE_PLAN**，理由是许可/依赖/Core语义与构造扩展/成本instrumentation及最终7/22范围尚需维护者批准，不构成新的acceptance decision。
