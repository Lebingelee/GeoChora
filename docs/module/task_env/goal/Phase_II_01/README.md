# Phase II-01 修订规划交付包

**当前恢复入口（2026-10-28）**：R03c attempt004 已经Sol复核，状态为 `ACCEPTED_BOUNDED_S2_S3`：唯一MuJoCo 3.8.1 CPU启动与同run独立H5读回通过，4个H5各64/65，reader读取256 transitions/260 observations并拒绝48/48 tamper。结果仅限Panda Arm+Hand 双source、两个Position writer、MuJoCo 3.8.1 CPU、seed31、2ms×5、E1–E4四配置。详情见 [07 检查点恢复](07_Execution_Order_and_Acceptance.md#r03c-checkpoint-recovery) 与 [R03](03_R03_Physical_Attachment.md)；后续方向见 [10](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md)。
维护者于2026-10-28纠正顺序：F00 attempt001仅完成整合/完成事实修复与S1，20/20 seeds 因 `gripper_readiness_timeout` 失败；随后要求完整验收F00后才准备/执行F01。attempt002已在 `develop-full` 完成公开 A/B 归因、合成输入修复、20-seed campaign、Oracle/H5独立回读及pending Judge包，完整出口及有限复核修正已获Sol **`ACCEPTED_BOUNDED_F00`**。历史attempt001失败原件保留；详见 [10 F00 Sol接收](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md#f00-sol-acceptance)。
当前F01 attempt001在 `develop-full` 冻结输入 `b0b26e95ddfd7b5128401261f05541bb19586372` 上完成隔离 Python 3.12 环境及 Torch 2.11.0+cu128 安装；国内镜像对可镜像依赖达到 21–55 MiB/s 且哈希与上游一致。官方 6.2 扩展缓存 wheel（5.498 GB）在 NVIDIA 源与官方 Akamai 边缘实测约 0.22 MB/s，USTC/阿里/清华/上交均无该专有 wheel；故本次为 `INSTALL_PARTIAL / NATIVE_NOT_RUN_INSTALL_BLOCKED`，IsaacSim 未安装、App 启动数为0。所有部分下载与失败日志保留在 ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f01_001/`，详见 [07 当前入口](07_Execution_Order_and_Acceptance.md) 及该目录 `report.md`。F01尚未完成，F02及后继不启动；Human Judge仍pending、Qualification未评估。
已确认的一个 Core Runtime、多 provider adapter、已验证 USD 输入、Isaac/GeoPhys 与真实 Harness 补丁
集中在 [10 补丁计划](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md)。
原 7/22 与 P99 保留；新增 F00–F07 是独立补丁计划行，不自动改变原 DAG 或授权实现/native。
以下 2026-10-23 记录及历史外部参考保留签署时点含义，不代表所有切片至今未启动。

2026-10-23规划快照：REVISED_DRAFT / AWAITING_MAINTAINER_GOAL_DAG_APPROVAL。独立R07与候选7父Goal/22切片已在develop@535ce251加入（前轮输入234da21b），本地259f27f完成规划复核。该签署时点维护者随后单独授权P00基线核查和工作包准备；当前逐slice执行状态见 [07](07_Execution_Order_and_Acceptance.md) 与 [manifest](planning_manifest.json)。总体定位见 [00](00_Phase_II_01_Blueprint.md)，原规划检查保留在 [validation receipt](validation_receipt.json)，P00核查另记manifest的 `P00_audit` 与 `revision_history`。

## 文档入口与责任

| 文档 | 修订后的责任 |
| --- | --- |
| [00 总蓝图](00_Phase_II_01_Blueprint.md) | 基线/范围/owner/相互独立与批准顺序 |
| [R01](01_R01_Logical_Robot_Assembly.md) | typed logical membership与hash DAG；R01a/R01b/R01c均已获Sol接收静态出口；R01c为声明级source投影/S1 |
| [R02](02_R02_Composite_Control_Profiles.md) | 独立leaf控制与binding/admission/fault |
| [R03](03_R03_Physical_Attachment.md) | 真实source、MuJoCo首条装配候选、GeoPhys拒绝与策略；R03c attempt004精确Panda/MuJoCo CPU public Env S2/S3已获Sol有界接收；不扩展通用Attachment/Provider或Qualification |
| [R04](04_R04_Dynamic_Camera_Consumer.md) | public observation/capture/storage消费边界；attempt002绑定修复已获Sol接收ACCEPTED_S1_BOUNDED |
| [R05](05_R05_Native_Rate_Feedback.md) | 正式Provider sample/cadence合同 |
| [R06](06_R06_Compatibility_and_Regression.md) | 顺序/机械/历史/兼容与证据治理 |
| [07 执行表](07_Execution_Order_and_Acceptance.md) | 7/22 DAG、required envelope与停止条件 |
| [08 审阅交接](08_Codex_Phase_II_01_Planning_Prompt.md) | 下一轮独立审阅/维护者审批指令 |
| [R07部署/Agent成本](09_R07_Benchmark_Deployment_and_Agent_Cost.md) | 固定五LIBERO审计/部署与成本协议、RoboCasa feasibility；不隶属R06 |
| [10 检查点后补丁](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md) | USD/source、free-body/state/control、Isaac/GeoPhys、真实 Harness 的 owner/方法、F00–F07 与调用链门禁；原目标保留 |
| [planning manifest](planning_manifest.json) | 机器可读DAG、source/probe出处与文档hash；非实施receipt |

## 当前开发流程（维护者2026-10-25补充）

本阶段预先规划**1个开发分支、0个新增worktree**，复用`codex/phase-ii-01-p00-20261023`承载多个子阶段/Goal，不按每份Prompt建分支。默认依[07执行顺序及Sol/Luna闭环](07_Execution_Order_and_Acceptance.md#sol-luna-workflow)：Sol发单slice完整Prompt→Luna执行/验证/本地提交并交报告→Sol核diff/Evidence、记账后发下一包；失败则同分支单包返工。

每个有界产出与相关本地提交对应；audit-only的ignored原件由Sol以既有文档摘要/索引提交关联，raw logs/H5不追踪进Git。只有恢复或独立方案比较/整合等实际需要才评估额外branch/worktree。具体分支计划与步骤由07及manifest记录；这些流程要求已明确，不等于具体功能范围、Provider合同或Qualification批准，push/merge/tag/Release仍另行授权。

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
| CTL-1 P0 | canonical Position Profile / plan / Env | R02c005 Hand50 case已获有界S2/S3接收；R03c004固定Panda/MuJoCo 3.8.1 CPU public Env/Recorder/reader S2/S3已获有界接收；更广provider/native mapping尚未接通 | 07记录精确接收边界；10后续方向保持独立，保留Force-aware拒绝与唯一writer保护 |
| MAT-1 P0 | RuntimeSource/materialization/typed state | R03b已为精确Menagerie Panda Arm+Hand双source增加fixed-tree plan与Core S2；更广source/provider路径仍未建立 | R03b及R03c精确Panda/MuJoCo路径已获有界接收 |
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

原 ZIP、解压草案与前次审阅文件未覆盖；初版保全在 ignored `workspace/maintenance/phase_ii_01_plan_revision_20261023_001/`，其中 `prior_review/` 保存前次原始 probe 副本。首版 R07 审计在 `workspace/maintenance/phase_ii_01_r07_plan_revision_20261023_001/`；本轮复核与修订前 tar 在 `workspace/maintenance/phase_ii_01_r07_recheck_20261023_002/`。各文件 hash/逻辑 path 见 [manifest](planning_manifest.json)。前轮 source-bound 收据可从固定 `535ce2516e61ecd538d5ff6dccf7493a1cfe2cac` 恢复，不能把旧收据的“尚未提交”快照解释为本轮状态。未把这些本地原始探针作为可随Git获取的新运行Evidence；新clone如无原件，应标“indexed but raw unavailable”，不能凭摘要重做成功证明。

本轮实际检查与既有测试/compile探针严格分栏，见 [validation_receipt](validation_receipt.json)。没有重跑Assembly NativeS2/S3、CameraEGL、Native-rate实验、完整A–D、NutAssembly矩阵、485区间R1或Qualification。当前工作仅文档，不需要修改Skill/API能力说明；TaskEnv Skill做静态检查，原说明仍描述当前实现。

待维护者批准：最终7/22/依赖；MuJoCo CPU首个装配required与GeoPhys第二Provider状态；独立Position leaf最低接口；R04 required Camera消费范围；R05双backend正式host合同范围；历史原件恢复/退休/继续延期的独立处置。原规划收据的P00 NOT_STARTED保留签署时点含义；后续单独授权仅允许P00核查与准入准备，不开始R01–R07或自动发布v2.0.1。

## P00首轮核查与手工Luna交接（2026-10-23）

本轮输入Core为`259f27f13e0b96067c5f58406271a3339edc0023`；实际fetch/readback的`public/develop`仍为`535ce251…`。保留本地领先提交，并从该HEAD建立`codex/phase-ii-01-p00-20261023`；未push/merge。两个gitlink和v2.0.0冻结refs不变。仅做源码/文档/结构与存储核查，未运行S2/S3/S4，也不把既有Evidence计作新实验。

本地事实报告、精确待决表、原始日志及首份自包含`AUDIT_ONLY` Luna Prompt保存在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_p00_001/`，由manifest引用；这些本地bytes不随Git分发，缺少它们的clone必须报告raw unavailable。P00技术核查与实施准入分开：最终Goal/DAG、Required Envelope、Provider owner合同、运行预算及独立Human决定均未代签。首包仅审计attached-pair source/admission的现有owner与缺口，不执行R03a或任何功能实现。08与原validation receipt仍为规划修订时点的输入，不覆盖本轮明确授权。

2026-10-25，Sol已复核P00-L01有界审计的输出/source hashes及关键源码guard；结果与既有Core准入边界一致，无需返工本次静态审计。原件及复核事实在同一ignored交接根目录的`luna_p00_l01_001/`和`sol_review_l01_20261025_001/`，由manifest引用；未运行S1/S2/S3/S4、未授予Attachment支持或实施准入。后继建议为先冻结MuJoCo CPU的R03a source/物理可行性probe合同；GeoPhys importer/normalization策略只约束其对应Provider路线，不是MuJoCo-only可行性核查的隐藏前置。Scene-v4仍是待比较方案，不能视为已批准或必需。

2026-10-25，Sol复核P00-L02 attempt001：最新包已依据显式amendment核对Sol的`dd02da4…`七文件文档提交，旧HEAD/hash差异关闭，原历史快照保留。source闭包与raw完整性核对通过；候选草稿存在载荷前快照实际取自末态、积分末态与派生位姿缓存混采、失败时partial progress未及时保留等静态缺陷，须以attempt002返工候选合同/脚本。复核入口为同一ignored根目录的`sol_review_l02_20261025_001/`，由manifest引用。没有运行或批准native probe，R03a仍NOT_STARTED / NOT_READY_SCOPE_ORACLE_BUDGET_PENDING；按[交接规则](07_Execution_Order_and_Acceptance.md#sol-luna-workflow)在Luna执行窗口冻结HEAD和保护输入，Sol摘要提交后再发下一包。

2026-10-26，Sol接收P00-L02 attempt002的F01–F08静态返工，直接修正候选实施副本中的integrator精确值/native版本字段等一致性小项，保留Luna原件。外载oracle采用同状态的公开mass/Jacobian与qacc_smooth平衡检查并记录真实轨迹；数值合并准则在首次执行前明确冻结。准备工作收口，下一步为R03a具体实施包的一次维护者授权决定，不再默认第三轮准备。复核与最终候选在同一ignored交接根目录的`sol_review_l02_20261026_002/`和`sol_r03a_001/`，由manifest引用；尚未运行native probe，也未批准Core Attachment准入。

2026-10-26，维护者明确授权PHASE-II-01-R03A attempt001的一次独立MuJoCo 3.8.1 CPU probe及范围内摘要提交。静态准备检查通过；native MjSpec attach/compile与模型身份、维度和ordered mapping通过，但 trial 1 Arm interval 3 触发 Hand finger joint 原生range overrun（`0.040001041818975604 m` > `0.04 m`），15次 `mj_step` 后停止，结果为 **FAIL**。Hand开合、外载与第二trial未执行；这不是Core S2/S3、Attachment admission或Qualification。R03b/c仍受既有依赖阻塞。一次S1修正仅修复了探针静态checker取错XML equality元素的缺陷；冻结数值oracle与native结果未重试或调宽。报告及raw evidence保存在本机ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r03a_001/`，由Sol复核。

2026-10-26，Sol已复核R03a attempt001的实际提交与15-step raw trace，接收冻结限位门触发的FAIL。后继为一个有界实施修复包：在源行程内将Hand reset/open和close目标各内缩2 mm，保留1e-6 m越界容限与全部运动/负载门，另行授权一次attempt002；不重开准备审计，不覆盖旧FAIL，不外推原端点或全行程支持。复核入口为同一ignored交接根目录下`sol_review_r03a_001/`；原native证据及GeoPhys历史拒绝保持。

2026-10-26，维护者明确授权R03a attempt002 `INTERIOR_HAND_COMMANDS` 的有限代码修正、stdlib-only S1和一个MuJoCo 3.8.1 CPU native进程。S1与新case全部冻结数值门通过：两trial各192个outer intervals、`mj_step=1920`、`mj_forward=389`；reset完全重复，Arm/Hand motion、range、mount、finite/warning/clock与1 N同状态load balance oracle均通过。结果仅适用于close `0.002 m / ctrl 12.75`、open/reset `0.038 m / ctrl 242.25`；native joint range仍`[0,0.04] m`、ctrlrange仍`[0,255]`。attempt001端点FAIL保持，未证明0/255端点、全行程、Core Attachment admission、Core public Env/H5、R03b/c或Qualification。报告与raw Evidence保存在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r03a_002/`，由manifest引用；Sol复核结论见下。

2026-10-26，Sol复核接收R03a attempt002为`ACCEPTED_BOUNDED`：实际六文件diff、44项交付与5项native哈希、1,920行step trace、386个状态样本及冻结oracle核对通过，未运行新的native实验。attempt001端点FAIL保留；该精确内缩case满足R03a有界工程出口。随后R01a attempt001在输入`2229ad857c0c711d0c3894c97b05994896c31016`上实现独立`logical-assembly-v1` strict codec及非自指hash，并完成provider-free S1与旧Scene/Artifact兼容检查；结果为`IMPLEMENTED_S1_PASS_PENDING_SOL_REVIEW`，报告在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r01a_001/report.md`。R01b/c仍未执行；R03b仍等待R01c，Core Attachment/公有Env/H5、全行程与Qualification结论不扩展。

2026-10-26，Sol复核接收R01a attempt001为`ACCEPTED_S1_BOUNDED`：实际11文件diff、36项输出哈希、五份旧Scene/Artifact mapping/hash核对通过；Luna完整目标S1为60 passed，Sol定向新合同S1为31 passed，另核对14项严格拒绝与四类typed subref别名隔离。未运行native；R01b/c与物理Assembly仍未实现。R05a的Provider正式native-rate合同存在preflight阻塞，维护者选择在此期间先推进无依赖边的R04a，未更改DAG/P99 required。

2026-10-26，R04a在同一Position candidate/SelectedReferenceEnv/Generic H5 v3 owners中加入显式双相机三模态消费配置、typed capture metadata reader、缓存与close/fault接线及64/128 MiB容量门。provider-free S1覆盖合成数组/H5、capacity、state-only兼容、cache、partial construction cleanup、post-step capture故障latch与mask digest拒绝；真实 MuJoCo/OpenGL/EGL、public Env reset/step和camera H5 readback均NOT_RUN，结果待Sol复核。R05a仍`BLOCKED_PROVIDER_CONTRACT`；R04b/c、DAG与P99 required不变。详见 [R04](04_R04_Dynamic_Camera_Consumer.md) 与 Phase II-01 manifest。

2026-10-26，Sol复核R04a attempt001为`CHANGES_REQUESTED`：原23项S1复跑通过，但独立纯S1反例发现consumer未把返回capture绑定到实际请求的mount/source合同，H5 camera reader未与真实state digest/finalized episode交叉核对。下一包只做R04a attempt002定向修复、相关S1与本地提交，不运行native、不扩展DAG或P99；原证据及未保留早期迭代日志的限制照实保留。复核入口为ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r04a_001/`。

2026-10-26，R04a attempt002在同一camera observation、Generic H5 v3与typed control/outcome owners中完成请求身份/calibration校验，以及sidecar对真实state digest、reset/transition clock、reference profile和finalized control/outcome的交叉核验；定向provider-free S1为33 passed，等待Sol复核。H5 v3根ABI不变，缺失/未知绑定版本fail closed；无native/Env S2/H5 S3声称，R04b/c仍未启动，DAG、R05a blocker与P99 required不变。详见 [R04](04_R04_Dynamic_Camera_Consumer.md) 和 ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r04a_002/report.md`。

2026-10-26，Sol已复核接收R04a attempt002为`ACCEPTED_S1_BOUNDED`，F01/F02关闭；复用33项S1日志并独立检查13个小型H5读回正负例，通过。原attempt001与失败日志保留；无native/S2/S3/Qualification。下一行R06a按一次完整审计/ledger/静态校验/本地提交推进，原件缺失时保留独立compatibility decision gate，不自动批准退休/继续延期。复核见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r04a_002/`。

2026-10-26，R06a attempt001的四类缺失原件审计、ledger与 legacy matrix S1（6 passed）已获Sol接收为`ACCEPTED_AUDIT_S1_BOUNDED`。三类B04a H5原始bytes仍缺，eb870f6f原路径现存JSON为被覆盖后的文件；本阶段恢复/reader退休/继续延期均未批准，compatibility gate保持BLOCKED。逐格式调用者、影响和待审批选项见[R06 ledger](06_R06_Compatibility_and_Regression.md#r06a-legacy-original-audit)与[manifest](planning_manifest.json)；DAG/Required Envelope/R05a与P99状态不变，R01b未启动。

2026-10-27，R01b attempt001实现递归owning/reference-only静态解析与有界typed-leaf结果；最终required provider-free四文件定向集合81 passed，含新resolver、R01a strict codec/hash、Scene composition和legacy matrix。source/compiler投影、native与Core Attachment仍未实现/未运行。当前Luna出口等待Sol复核，不是R01b acceptance。R06兼容性处置继续未批准且gate仍blocked；DAG/Required Envelope/P99/R05a不变。按执行表下一个slice为R02a；R01c未启动。报告与Evidence位于ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r01b_001/`。

## 本轮R07修订与Scope Risks

- [09 R07](09_R07_Benchmark_Deployment_and_Agent_Cost.md)包含五Task逐项source/native语义/init/asset审计、ownership、真实部署门槛、Agent成本/独立review与RoboCasa feasibility；native source code读到了不等于Core已支持。
- R06b新增R03b前置；P99改为R06c+R07d；旧18slice保留目的，其余依赖不变。五Task所选初版R02/R03/R04条件前置各为none；新recipe必须显式加入exact条件边，不能隐含required依赖或全局强加Camera/force。
- R04澄清现有CHW uint8录制与public HWC float32的量化/转置差异，不改变Recorder；成本协议不以float RGB存储为必要。
- 本轮基线已fetch：develop/public develop=535ce251…；冻结PhaseII与gitlinks未动。首版R07以234da21b为输入、source审计收据已随535ce251保存；本轮receipt只记录本轮检查，并单列16文件重新抓取与63份本地source hash复核，不将前次14tests、init下载或compile probes重记为新执行。
- 成本实验起点须在R07a另锁真实源码/复用版本；R07引发的Core Extension成本入账，已有R01–R06基础及未计成本边界分栏，避免把规划提交当成测量起点或作因果成本结论。

| 风险 | 状态 / 影响 | 待审议处置 |
| --- | --- | --- |
| arbitrary BDDL source/reset/admission、contact/site/fixture-joint/evaluator缺口 | 五LIBERO部署当前NOT_RUN，已有BLOCKED_CORE风险；语义不匹配可NOT_REPRESENTABLE | 原task/source/runtime/observation owner扩展review，不能换简单task/用旧UID冒认 |
| native MountedPanda torque-motor/双finger position actuator/OSC/20Hz与Core候选不同 | 机器人/源/控制身份不能迁移，依赖版本未验证 | 锁actualassets/build/Action/frame/cadence和boundedsmoke，不保证控制器算法等价 |
| per-asset许可与完整source closure | 检查XML/tree refs≠完整网格bytes/许可验证 | R07b verified manifest gate；外部安装与可分发来源分开 |
| RoboCasa移动base/复杂fixture/大资产与rolling robosuite依赖 | 仅固定源码feasibility，无五Task执行承诺 | 单独go/no-go建议/版本lock，额外执行另批 |
| Agent usage/billing/active time缺失、self-score或native成本对照缺位 | 不能估算成测量或宣称因果成本下降 | null/reason、session/log/hash、独立human评审；controlled研究另定预算 |

R07a中protocol、functional motion/semantic oracle/tolerance、预算与任务顺序须部署前冻结；R07c指定五Task之一被阻塞或不可表示，P99保持阻塞，等待维护者精确scope decision。全部七Goal仍candidate；本轮建议审阅结果 **REVISE_PLAN**，理由是许可/依赖/Core语义与构造扩展/成本instrumentation及最终7/22范围尚需维护者批准，不构成新的acceptance decision。

2026-10-27，Sol接收R01b为`ACCEPTED_S1_BOUNDED`：审阅10文件diff与原81项S1，直接补递归入口32层门及1100层反例，最终四文件S1为82 passed。无需再开返工包；R01a/Scene旧identity与R06 ledger保持，native/source projection/Qualification未建立。下一表行为R02a静态leaf合同，不自行跳到R01c。复核入口为ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r01b_001/`。

2026-10-27，R02a attempt001在现有 canonical Controller owner 增加版本化 Arm-only/Hand-only Position Action/Target/Ack/Required State、严格静态 binding/Scene/Assembly selector 核验，以及独立 Hand Force-aware 依赖/拒绝目录。Hand 开度是总 opening `q1+q2`，与一个 actuator8、0.5/0.5 tendon、finger equality 和候选 `ctrl=3187.5*opening_m` source mapping 分开记录；Position state 不要求力。定向 provider-free S1 与相关旧 Controller binding 检查完成，输出等待Sol复核；无R02b adapter、native/S2/S3、Recorder接入或Qualification。R01c/R02b/c仍未启动，R06 compatibility gate、R05a blocker、原DAG/Required Envelope/P99不变。详见 [R02](02_R02_Composite_Control_Profiles.md) 和 ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02a_001/report.md`。

2026-10-27，Sol接收R02a静态合同出口为`ACCEPTED_S1_BOUNDED`：原30项S1保留，Required State可降级/跨leaf字段的拒绝缺口已由Sol小范围修正，最终37 passed。catalog/Force-aware仍NOT_ADMITTED，native/plan/adapter/H5/Qualification未建立。下一表行为R01c只读source投影，R06兼容性决定与R05a/DAG/Required Envelope/P99不变；复核见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r02a_001/`。

2026-10-27，R01c attempt001在既有 `task_env.assembly` source/compiler owner完成逻辑Assembly到现有Scene源声明的只读投影，provider-free S1覆盖A05完整Panda视图与独立Menagerie Arm/Hand Entity source declarations，并核验identity/provenance、typed refs、不可变snapshot及fail-closed resolver边界。状态为`IMPLEMENTED_S1_PASS_PENDING_SOL_REVIEW`，尚未获得Sol acceptance。没有lower/attach XML、Provider/native构造、Runtime/S2/S3/S4、Core Attachment admission或Qualification；R06兼容性gate、R05a blocker、原DAG/Required Envelope/P99保持。R02b仍未开始；报告及Evidence保存在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r01c_001/`。

2026-10-27，Sol接收R01c attempt001的声明级source投影与18项provider-free S1为 `ACCEPTED_S1_BOUNDED`；无需返工。下一表行为R02b，一包完成effective plan、leaf adapter/preflight实现、定向S1及本地提交。原S2/S3/S4、Attachment/runtime/Qualification边界和R06/R05a/DAG/Required Envelope/P99保持不变。复核见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r01c_001/`。

2026-10-27，R02b attempt001在既有canonical与RuntimeSession control owners内实现严格parent preset、完整section override、effective Arm/Hand Position plan、共享旧算法的真实leaf adapters、明确canonical/native mapping receipt及全请求preflight/typed dispatch与partial-apply fault progress。新增provider-free S1 13 passed；受影响的R02a/R01b/R01c/C02a/C03a静态回归101 passed，C02b纯action guard 1 passed；三项真实native测试被有意排除。分离Arm/Hand Entity交集只以`synthetic_fixture`完成，Provider materialization、SelectedReferenceEnv、Recorder/H5与真实native尚未接入。交付状态`IMPLEMENTED_S1_PASS_PENDING_SOL_REVIEW`，等待Sol复核，不构成Runtime/admission、Qualification或R02c/R03b完成。R06 compatibility gate、R05a blocker、DAG/Required Envelope/P99均保持；详见[R02](02_R02_Composite_Control_Profiles.md)和ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02b_001/report.md`。

2026-10-27，Sol接收R02b attempt001为 `ACCEPTED_S1_BOUNDED`：4项局部兼容与拒绝门缺口已直接修正，R02b最终18项S1通过；101项既有owner与1项C02b pure guard通过，54个旧源码数值/身份对照一致。下一行R02c，由现有完整Panda两个ControlGroup引用运行真正独立的Arm/Hand Position writer并接入既有Env/H5；不以两个完整Panda替代leaf证据，不增加R03b隐藏前置。Sol本轮未运行native、R02c/R03b或S2/S3/S4，原gate与Qualification边界保持。复核见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r02b_001/`。

2026-10-27，R02c attempt001在既有Task Source、RuntimeSession、SelectedReferenceEnv与Generic H5 v3 owners内完成独立Arm/Hand Position leaf candidate、MuJoCo adapter和严格leaf H5 reader；provider-free定向S1为53 passed。唯一获准probe进程在MuJoCo import前因合同静态校验字段名错误退出，native compile/reset/forward/step与S2/S3均未发生。脚本已静态修正但未重启；Provider admission、Qualification和R03b均未启动。报告及失败原始日志位于ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02c_001/`；当前状态等待Sol复核，原DAG、R06/R05a blocker、Required Envelope和P99不变。

2026-10-28，R03b attempt001完成精确Arm/Hand双source fixed Attachment candidate、Core RuntimeSession S2与定向S1。19项S1负例与80项旧owner回归通过；两个独立3.8.1 CPU trial各128 intervals/640 step，mount、Arm/Hand运动、limits、时钟、warnings及close均通过。首次pre-step source-timestep拒绝和唯一允许修正均单独保留；修正后第二且最后native进程通过，合计预算仍在冻结上限。出口等待Sol复核，仅覆盖该source/seed31/2ms×5；未建立通用Attachment、public Env/Recorder/H5 S3或Qualification。R03c **NOT_RUN / 未启动**，等待R03b复核。完整事实与Evidence入口见 [R03](03_R03_Physical_Attachment.md) 和 ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r03b_001/report.md`。

2026-10-27，Sol复核R02c attempt001为 **CHANGES_REQUESTED_S2_S3_NOT_RUN**：保留53项S1，但reader导入/codec、Target写入前boundary校验及clock比较存在可复现缺陷，另须关闭admission失败清理与probe旧窗口接线。原失败和两进程额度耗尽事实保留；Sol未运行native。下一包attempt002合并修复、provider-free回归、实际静态预检及获授权的有界S2/S3；R02c出口尚未接收，R03b未启动。复核见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r02c_001/`；原DAG、R06/R05a、Required Envelope/P99及Qualification边界不变。

2026-10-27，R02c attempt002在既有leaf-control、MuJoCo RuntimeSession、SelectedReferenceEnv与Generic H5 v3 owners内完成五类返工；provider-free定向S1为28 passed，合法静态合同/source预检通过，四类合同负例均被结构化拒绝。唯一获授权的MuJoCo 3.8.1 CPU进程在compile前的运行时版本/API身份检查被标记`BLOCKED_PROVIDER`，native compile/materialize/reset/forward/step均为0；没有实际episode/H5，S2/S3为`NOT_RUN`，未重试或换Provider。状态待Sol复核，Provider admission/Qualification未建立；R03b不启动。实现提交为`b845bfadf518f57981b3556f65e3eb211dab1996`，报告与Evidence位于ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02c_002/`。R06 gate、R05a blocker、DAG/Required Envelope/P99及旧版本身份保持不变。

2026-10-27，Sol复核R02c attempt002五项修复并直接修复版本检查器错误：MuJoCo3.8.1 API预期应为3008001，原30801错误；原raw未保存actual版本，不能确认Provider不匹配。Sol当前rework S1 19 passed、无native，R02c为S1_REVIEWED_NATIVE_PENDING。下一包attempt003一个native进程补齐S2真实motion/isolation与S3同Env/H5集成，原预算/source/oracle保持，002/003合计启动≤2；R03b未开始。复核及next prompt在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r02c_002/`。

2026-10-27，R02c attempt003按固定合同完成一次MuJoCo 3.8.1 CPU进程：静态source预检通过，实际provider身份匹配，编译及9/9/8 materialization、E1 reset成功；首个interval五个`mj_step`后Core因leaf state requirements以tuple而非`StateRequirements`传入typed projection而失败。H5 event记录物理clock到step 1/0.01s、transition incomplete；probe未序列化逐writer progress/Ack。close产生Generic H5 v3失败artifact（T=0/T+1=1），R02c strict reader按64/65拒绝，Recorder错误原样保留；不算S3。原required S2/S3未通过，Provider admission/Qualification不成立。随后修复既有dispatch owner；provider-free rework S1 19 passed，修复未native验证，未重试。状态`FAIL_CORE / S2_S3_INCOMPLETE_PENDING_SOL_REVIEW`，R03b未启动，R06/R05a、DAG/Required Envelope/P99/source/oracle/冻结refs不变。报告与Evidence见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02c_003/`。

2026-10-27，Sol复核R02c003并收口相邻接口：Provider/source/compile/receipt/E1 reset和5步进展事实有效，Core tuple→StateRequirements错误导致S2/S3未完成，失败H5 T0/1仍拒绝。Sol强化真实publication/projection回归、预先校验要求，修正probe S3剩余导入并保存逐writer fault receipt；38项provider-free S1通过，无新native。当前S1_REVIEWED_NATIVE_PENDING；三条滞后Markdown hash直接同步。下一包004新授权一个native进程执行同source/oracle四episode，不重复准备；R03b/R06/R05a/DAG/required/P99不变。复核在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r02c_003/`。

2026-10-27，R02c attempt004按当前用户指令在新窗口运行一次MuJoCo 3.8.1 CPU native进程。S0保护输入/语义gate匹配，真实static preflight验证未变source closure和67 assets，加载身份`3.8.1/3.8.1/3008001`及固定path/hash通过。E1 Arm-only 64 intervals/320步，Arm motion/home oracle、完整H5 T64/T+1 65、独立reader和9类tamper拒绝通过。E2 Hand-only 64 intervals/320步，但opening最小0.0687899 m、excursion0.00721014 m未达冻结门；关闭时留下的H5为T64/T+1 65，离线typed reader通过。E3/E4未运行，因此R02c required S2/S3未完成。native真实计数为materialize2/reset2/step640；`mj_forward`和RSS未从失败收尾中保存，记未知。主E2 assertion后，NumPy标量JSON序列化错误令原raw summary误报FAIL_PRE_STEP/零计数；JSONL事件保留了准确失败与进度。诊断序列化修正及provider-free模块回归21 passed，没有第二次native，也未改source、物理算法、oracle、阈值或预算。最终状态`FAIL_PHYSICAL_ORACLE / S2_S3_INCOMPLETE_PENDING_SOL_REVIEW`，Provider admission/Qualification未授予，R03b未启动；R06/R05a/DAG/Required Envelope/P99/source/oracle/冻结refs不变。attempt004 report/Evidence在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02c_004/`；attempt001–003失败原件不变。

2026-10-28，R02c004 Sol复核接收E1 arm-only motion/H5有界证据，E2 Hand物理门失败保留，E3/E4未运行；42项收尾修复S1通过，无新native。当前BLOCKED_HAND_CONFIGURATION_DECISION。静态可行的SOURCE_CALIBRATED_HAND_50_V1提案使用现有Hand完整section override，保留2500默认/旧FAIL并按source的50N/m坐标标定新配置，原算法/source/oracle/预算不变；待维护者明确采用，不自行tune重跑。复核及提案在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r02c_004/`；R06/R05a/DAG/required/P99保持。

2026-10-28，R02c005 SOURCE_CALIBRATED_HAND_50_V1已接收ACCEPTED_BOUNDED_S2_S3：现有candidate builder通过完整Hand override显式选50，默认2500/旧plan和004 FAIL保留；56项provider-free S1，单次MuJoCo3.8.1 CPU的四episode motion/隔离及四份真实H5独立回读通过。没有改source/算法/物理门/预算。当前按07转入R03b工作包准备，尚无独立Attachment admission或Qualification。报告在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r02c_005/report.md`。

2026-10-28，Sol已接收R03b attempt001为`ACCEPTED_BOUNDED_S1_S2`：实际双Entity固定装配、两个RuntimeSession trial及256个运动边界/两份reset经离线复核通过。接收时直接补齐source与canonical Joint/Asset声明的一致性拒绝门，99项provider-free回归及原19负例静态检查通过；正确case身份及原S2证据不变，没有新增native。原Luna报告保持签署时状态，当前决定见ignored `sol_review_r03b_001/sol_review.md`。R03c public Env/Recorder/H5及S3/S4仍NOT_RUN、未启动；R06/R05a、DAG/Required Envelope/P99与冻结refs不变。

2026-10-28，R03c001经Sol静态复核后为`S1_REVIEWED_NATIVE_PENDING`：真实Core准入至public reset/step的native-IO替身检查、reader一致篡改拒绝与冻结门、共享执行preflight补齐，当前90项S1通过；没有追加native，原S2/S3仍不完整。GeoPhys继续保留Phase II已验证完整Panda路线；新leaf/Attachment尚有source与Core adapter适配缺口，不能概括成GeoPhys不支持Phase II-01。详细复核在ignored `sol_review_r03c_001/`，原失败raw不改。

2026-10-28，R03c attempt002使用单次授权MuJoCo 3.8.1 CPU native窗口后，在E1 public reset后的 `snapshot_v1()` typed Joint绑定处失败：runner传入 `JointReference` 而Core要求canonical Scene中的 `JointDefinition`。计数为1 start/materialization/reset/forward、0 step/outer，未完成episode/H5，独立H5 reader未运行，RSS无样本。失败后runner从固定Scene选择typed Joint definitions并通过新增1项provider-free S1；无native重试，修正仍待native验证。仅记录此attempt的S2/S3不完整与失败，不改变通用Provider/Attachment能力。原始attempt001与attempt002 bytes、freeze和账本由Phase II-01 manifest分别指向`r03c_001/`与`r03c_002/`；Sol复核前不推进其他slice。

2026-10-28，R03c attempt004在冻结输入HEAD `4ac7284a4cf770f28a1c5d1f9c81337a6b39c66d`完成一次MuJoCo 3.8.1 CPU启动，实际package/runtime/API为3.8.1/3.8.1/3008001，runner exit 0并发布正式receipt/progress。E1–E4各64 transitions/65 observations，合计4 materialization/reset、260 forward、1280 step、256 outer、2.56 simulated seconds；S2活动控制/复位/装配门及E3/E4配置隔离通过。另一provider-free进程对同run四份H5回读256 transitions/260 observations，provider imports为0，48/48 tamper拒绝通过，S3通过。状态为`BOUNDED_ATTACHED_LEAF_PUBLIC_ENV_S2_S3_PASS_PENDING_SOL_REVIEW`；范围仅本包精确source、双Position writer、seed31、2ms×5和MuJoCo CPU，不是Qualification或通用Attachment/Provider准入。S1复用33项已复核结果；attempt001–003原件保留，当前仅待Sol复核，不启动其他slice。raw evidence在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r03c_004/`。

2026-10-28，Sol复核R03c attempt004，接收 `ACCEPTED_BOUNDED_S2_S3`。实际启动exit 0、正式receipt及complete progress存在；50项原始文件hash、16项冻结源码hash、1280 step trace、四份H5与独立readback的hash及冻结门一致，48/48 tamper拒绝。接收仅限Panda Arm+Hand 双source、两个Position writer、MuJoCo 3.8.1 CPU、seed31、2ms×5、E1–E4四配置；RSS为边界采样，非interval内硬峰值。复用33项provider-free S1，没有新增native或软件测试。复核报告：ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r03c_004/sol_review.md`。
