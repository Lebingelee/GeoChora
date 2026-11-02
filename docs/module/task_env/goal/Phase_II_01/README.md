# Phase II-01 当前入口

> **当前本地候选准备（2026-11-02）**：[v2.1.0 发布准备](16_V210_Release_Preparation_Goal.md)。范围为两项API收口、版本化文档/Skill、发布材料和Core本地分支整理；不push/tag/Release，不启动native。完整迁移和分支方案已由维护者确认，待执行与Sol复核。


> **当前 v2.1.0 重构入口（2026-11-02）**：[公共任务 API 收敛](15_V210_Public_Task_API_Refactor.md)。F/R 集成基线已由 Sol 有界接收；下一轮优先实现统一配置、公共构造与任务迁移，只做最小受影响验证。此规划不声称重构已完成，不改变历史接受或发布授权。


> **当前F线入口（2026-11-01）**：新F05原生适配三路线主线已由Sol有界接收（DG04证据Core `fb4c3836`、文档HEAD `740a74a9`），旧F05 PARTIAL、严格DG03及R3未决保留。F06按维护者新裁定组织[PickCube × Harness × 三主要后端example](14_F06_PickCube_Harness_Multi_Backend_Goal.md)，每后端3 seed、任务成功与runtime有效性分开；包已准备待人工转述，尚未执行。下方日期较早的状态为历史。

**新F05 successor（2026-10-30；attempt001经Sol复核需返工）**：`F05_SUCCESSOR_ATTEMPT001_REVIEWED_PARTIAL_REWORK_REQUIRED`；来源字节/原始字段采集有效，完整S0 PASS未接收。inventory=PARTIAL、readiness=BLOCKED_BY_FEATURE。authored schema、真实语义负例接线、归一化/传动核验与具体补丁图需补齐；零native，窗口1/3。旧F05三轮/PARTIAL保留，S1 native及F06/F07未启动。见[Sol复核](11_F05_F07_Multi_Asset_Solver_Recovery_Plan.md#successor-attempt001-sol-review)。

<a id="f05-successor-replan-20261030"></a>

**2026-10-30 F05后继规划入口**：维护者要求按网页审阅重新组织F05。当前规划采用同源多表示主线（Menagerie MJCF/MuJoCo、USD/Isaac、USD/GeoPhys），原同USD三Provider门列为后继延期单元，旧F05仍PARTIAL且原门未通过。官方Panda→GeoPhys兼容独立排期；USD/Isaac资产优先输入策略保留。见[11路线与语义约束](11_F05_F07_Multi_Asset_Solver_Recovery_Plan.md)及[12执行指南](12_F05_F07_Execution_Playbook.md)。本轮只调整文档，Scope Decision/实际工作包/预算待冻结，所有successor stage为PLANNED/NOT_EXECUTED；不启动F06/F07或原F05 attempt004。F线owner为`develop-full`，本分支文档同步不证明已合入其实现；R线范围/进度及旧接收/失败保留。下文未更新的旧时点路线由11/12管理其后继，不能据旧默认入口派包。

**当前恢复入口（2026-10-28）**：R03c attempt004 已经Sol复核，状态为 `ACCEPTED_BOUNDED_S2_S3`：唯一MuJoCo 3.8.1 CPU启动与同run独立H5读回通过，4个H5各64/65，reader读取256 transitions/260 observations并拒绝48/48 tamper。结果仅限Panda Arm+Hand 双source、两个Position writer、MuJoCo 3.8.1 CPU、seed31、2ms×5、E1–E4四配置。详情见 [07 检查点恢复](07_Execution_Order_and_Acceptance.md#r03c-checkpoint-recovery) 与 [R03](03_R03_Physical_Attachment.md)；后续方向见 [10](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md)。
**当前F线恢复入口（2026-10-30）**：F00/F01/F02已获各自有界接收；F03 attempt003获`ACCEPTED_BOUNDED_F03_S1`。F04 attempt004获`ACCEPTED_BOUNDED_F04`，限冻结双Panda/Isaac 6.2.0.0/CUDA GPU PhysX/受控worker路线。F05 attempt003的Menagerie USD + GeoPhys candidate CPU exact cell已获`ACCEPTED_BOUNDED_F05_MENAGERIE_GEOPHYS_CPU_NATIVE`：同一Env两episode共1,000步、两份H5、原物理门、202/202独立T+1读回、36/36 H5与6/6 bundle篡改拒绝、父观察exit0/PG结束/锁释放；F05总体仍PARTIAL，official Panda +inf/mimic、MuJoCo USD decoder和split Attachment仍HELD。F06/F07未启动，不授予Qualification。详见[10 F05 attempt003](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md#f05-attempt003-menagerie-geophys-cpu-native-result)。
维护者于2026-10-28纠正顺序：F00 attempt001仅完成整合/完成事实修复与S1，20/20 seeds 因 `gripper_readiness_timeout` 失败；随后要求完整验收F00后才准备/执行F01。attempt002已在 `develop-full` 完成公开 A/B 归因、合成输入修复、20-seed campaign、Oracle/H5独立回读及pending Judge包，完整出口及有限复核修正已获Sol **`ACCEPTED_BOUNDED_F00`**。历史attempt001失败原件保留；详见 [10 F00 Sol接收](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md#f00-sol-acceptance)。
历史F01 attempt001记录：当时在 `develop-full` 冻结输入 `b0b26e95ddfd7b5128401261f05541bb19586372` 上完成隔离 Python 3.12 环境及 Torch 2.11.0+cu128 安装；国内镜像对可镜像依赖达到 21–55 MiB/s 且哈希与上游一致。官方 6.2 扩展缓存 wheel（5.498 GB）在 NVIDIA 源与官方 Akamai 边缘实测约 0.22 MB/s，USTC/阿里/清华/上交均无该专有 wheel；故该attempt为 `INSTALL_PARTIAL / NATIVE_NOT_RUN_INSTALL_BLOCKED`，IsaacSim 未安装、App 启动数为0。所有部分下载与失败日志保留在 ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f01_001/`，详见 [07 当前入口](07_Execution_Order_and_Acceptance.md) 及该目录 `report.md`。该时点F01尚未完成，后续接收见本页当前F线入口；Human Judge仍pending、Qualification未评估。
已确认的一个 Core Runtime、多 provider adapter、已验证 USD 输入、Isaac/GeoPhys 与真实 Harness 补丁
集中在 [10 补丁计划](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md)。
原 7/22 与 P99 保留；新增 F00–F07 是独立补丁计划行，不自动改变原 DAG 或授权实现/native。
以下 2026-10-23 记录及历史外部参考保留签署时点含义，不代表所有切片至今未启动。

Phase II-01 同时记录 R 路线的 Core 工作与 F 路线的多资产后继计划。两条路线的 owner、状态和证据相互独立；本页只负责当前导航，不改写历史接受、冻结输入或发布决定。


## 当前状态

截至 2026-11-01，R 路线的 LIBERO A123 技术交集为 `ACCEPTED_BOUNDED_R07_A123_TECHNICAL`：固定上游来源、task 1–3、MuJoCo/GeoPhys CPU、冻结 A 阶段环境和上游控制流程。它不表示整个 R00–R07/P99、任务成功、Qualification 或发布已完成。

task2 GeoPhys 的接触前偏差按维护者接受的限定例外处理，仅对应这次冻结的来源、controller 和 action sequence。首次上游手指碰柜体发生在 action 82；其 TCP 对上游的位置 P95/最大值为 33.143/37.916 mm，姿态为 229.074/259.412 mrad。该决定不建立一般 provider parity。资产 `wine_bottle` 与 `wine_rack` 的具体文件许可和署名记录仍未解决；B/C、高精度控制器改进和自主 Solution 是可选后续，Isaac Sim 延期。

完整状态与接受边界见 [07 执行与接受矩阵](07_Execution_Order_and_Acceptance.md) 和 [Sol A123 接受记录](../../../../maintenance/20261101_r07_a123_sol_acceptance.md)。原始 A123 返工报告保留于忽略跟踪的 [`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/libero_a123_review_rework_20261101_001/`](../../../../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/libero_a123_review_rework_20261101_001/)；接受决定不改写该报告或 raw evidence。

## 文档入口与责任

| 文档 | 当前用途 |
| --- | --- |
| [00 总蓝图](00_Phase_II_01_Blueprint.md) | Phase 基线、历史目标和 owner 总览 |
| [07 执行与接受矩阵](07_Execution_Order_and_Acceptance.md) | R 阶段依赖、当前接受状态、范围与停止条件 |
| [A123 Sol 接受记录](../../../../maintenance/20261101_r07_a123_sol_acceptance.md) | 最新有界技术决定、task2 例外和未决限制 |
| [R 路线档案索引](../../../../archive/phase_ii_01_r_routes/README.md) | R01–R07 旧规划原文、路径映射与 SHA-256 |
| [planning manifest](planning_manifest.json) | 冻结的机器可读计划；作为历史收据只读 |
| [validation receipt](validation_receipt.json) | 原规划验证快照；不以本轮改写 |
| [10 检查点恢复与 Harness 计划](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md) | F 后继计划的输入、owner 与限制 |
| [11 多资产 solver 恢复计划](11_F05_F07_Multi_Asset_Solver_Recovery_Plan.md) | F05–F07 的恢复范围 |
| [12 F05–F07 执行手册](12_F05_F07_Execution_Playbook.md) | F 路线执行流程；F owner 状态由其 checkout 决定 |

R01–R06 和 R07 的详细旧规划已逐字节保存在 [`docs/archive/phase_ii_01_r_routes/`](../../../../archive/phase_ii_01_r_routes/README.md)。原文件路径保留短导航页及旧标题锚点。需要恢复历史实现时，以路线记录所列的固定 Git commit 和 hash 为准；活动源码不保留一套旧版本实现。

## 当前开发流程（维护者 2026-10-25 补充）

沿用现有 phase branch 和逐包 Sol/Luna review 流程。每份实现报告关联输入/输出 HEAD、提交、检查和证据；Sol 独立检查 diff 与 Evidence 后再接受或派后继工作。讨论或本地整理不代表 merge；push、merge、tag 和 Release 按仓库治理要求另行授权。

<a id="references"></a>

## 固定外部参考与采用原则

下列资料用于工程设计参考，不自动证明 GeoChora 对应 provider、资产或能力已支持。历史访问日期与完整讨论保留在 [00 总蓝图](00_Phase_II_01_Blueprint.md) 的固定来源记录和归档原文中。

| 参考资料 | 使用边界 |
| --- | --- |
| [Isaac Lab v3.0.0 Release](https://github.com/isaac-sim/IsaacLab/releases/tag/v3.0.0) | 只作为多 backend 方向参考 |
| [Isaac Lab v3.0.0 backend 与 preset 文档](https://isaac-sim.github.io/IsaacLab/v3.0.0/source/concepts/backends_and_presets.html) | 配置选择和准入设计参考 |
| [Isaac Lab v3.0.0 SceneData API](https://isaac-sim.github.io/IsaacLab/v3.0.0/source/api/lab/isaaclab.scene_data.html) | 数据 producer/consumer 生命周期参考 |
| [Isaac Sim 6.1.0 Robot Assembler](https://docs.isaacsim.omniverse.nvidia.com/6.1.0/py/source/extensions/isaacsim.robot_setup.assembler/docs/index.html) | 装配意图与 native lowering 的边界参考 |

<a id="provenance"></a>

## Provenance 与保全

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

2026-10-28 当前并行安排：维护者手动下载Isaac依赖，F01仍安装未完成、无native；Luna1推进R07a的非native审计/S1，Luna2在独立camera工作树完成R04b attempt002返工。R04b attempt001的24项S1可复核，完整S2未通过，旧失败与新修正分开记账。新包冻结具体HEAD/保护输入，原7/22/P99门及F02–F07后继不改。


2026-10-30，Sol有界接收F05 source/control/S1修复，状态`ACCEPTED_BOUNDED_F05_SOURCE_CONTROL_S1`，F05整体仍PARTIAL；reader降级合同遗漏由Sol直接补齐并通过新S1。官方GeoPhys source/mimic、native及MuJoCo USD仍未接收；F06不启动。详见[接收记录](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md#f05-attempt002-sol-acceptance)。


### F05 successor attempt002 执行结果（2026-10-30）

冻结工作包`F05_SUCCESSOR_ATTEMPT002_SEMANTIC_REPAIR_AND_CORE_CELLS`已完成；静态审计输出位于ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f05_successor_002/`。原完整prompt/snapshot/hash、G0–G8和当时readiness见[执行快照](11_F05_F07_Multi_Asset_Solver_Recovery_Plan.md#successor-attempt002-execution)。2026-11-01有界续行已补当前HEAD DG03 synthetic Core S1及两个N1关系诊断；正式Isaac Core cell仍`BLOCKED_BY_FEATURE`，未获得三cell候选通过。保留旧attempt002快照，并以[续行记录](11_F05_F07_Multi_Asset_Solver_Recovery_Plan.md#successor-attempt002-continuation-20261101)为当前事实入口；旧F05/PARTIAL不改，F06/F07未启动。


<a id="f05-early-diagnostic-three-goals"></a>

### 2026-10-30维护者指定提前诊断：三个长期Goal

当前执行入口改为[13提前诊断Goal编排](13_F05_Early_Diagnostic_Three_Goals.md)：DG01共同基线＋MuJoCo/MJCF、DG02 GeoPhys/USD、DG03 Isaac/USD＋三路线收口。普通successor001/002与2/3历史保留，普通003不派发；明确指定的诊断窗口另记，无固定attempt上限，资源预算仍严格。每Goal必须持续实现和取得真实Core/native/reader证据；缺profile/receipt是工作项，不自行结束为BLOCKED。允许完整route未就绪前的有界N0/N1模型/特性探针，最终N2生产门不降低。DG01/DG02已分别获有界Sol接收；DG03已有synthetic S1与N1诊断但仍partial、长期Goal active，后续窗口须按Sol复核后的HEAD与剩余语义缺口重新冻结。F06/F07未启动，旧F05partial及required物理语义不变。

R 路线原文的文件名、字节数和 SHA-256 在 [档案索引](../../../../archive/phase_ii_01_r_routes/README.md)。`planning_manifest.json`、`validation_receipt.json`、F-owned 10–12 文档、冻结 release/tag 和忽略跟踪的 workspace evidence 均按原职责保留；本页和档案不把 unresolved 状态变成已接受能力，也不为历史计划补造执行结果。
