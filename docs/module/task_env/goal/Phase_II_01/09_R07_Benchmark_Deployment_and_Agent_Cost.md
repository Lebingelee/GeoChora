# R07 — Benchmark Deployment & Agent Cost Evaluation

<a id="r07-current-scope-20261030"></a>

## 当前范围决定：三个任务、部署切换与分层成功验收（2026-10-30）

维护者在本诊断对话明确批准保留原任务 #1/#2/#3，并纠正“三任务×三后端都必须 Solution 成功”的建议。**本节是当前 R07 范围真源，覆盖下文历史“五任务 required”及“任务/Expert 成功非必需”的表述；旧报告、attempt、收据与原始审计不追溯修改。** 原 #4 叠碗、#5 炉子与摩卡壶移为 DEFERRED_OUT_OF_CURRENT_R07_SCOPE；其未实施或未成功不再阻塞当前 R07/P99。它们不是已通过，也不自动进入下一阶段。

| 保留编号 | Suite / 精确任务名 | 必须保留的任务成功语义 |
| --- | --- | --- |
| 1 | libero_spatial / `pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate` | 原生 On(black bowl, plate)：原接触、XY 与高度条件 |
| 2 | libero_goal / `open_the_middle_drawer_of_the_cabinet` | 原生 Open(middle drawer)：正确关联 joint，严格 qpos < −0.14 m |
| 3 | libero_goal / `push_the_plate_to_the_front_of_the_stove` | 原生 On(plate, stove-front region)：原 site/region 分支；不另造 Push 动作历史谓词 |

### R07c 的三个独立门

| 门 | 当前必需范围 | 完成条件 |
| --- | --- | --- |
| 部署与后端切换 | 三个任务均可在 MuJoCo、GeoPhys、Isaac Sim 配置中选择并实际运行 | 九个 task/provider 组合均完成 source/admission、真实 construction、重复 reset、有意义的 public control/step、状态/语义检查、Recorder、独立读回与 close；仅注册/编译/参数存在不算可切换 |
| MuJoCo Solution 成功 | #1、#2、#3 全部 | 每任务均有真实有效的完整成功 episode，原任务 predicate 与 Solution 完成同时成立，失败/非法 lifecycle/cleanup 不冒充成功 |
| 其他后端 Solution 成功 | GeoPhys 至少一个保留任务；Isaac Sim 至少一个保留任务 | 两个后端分别有至少一个任务满足同等完成证据；可以选择相同或不同任务。其余组合的 Solution 成功是 STRETCH，不阻塞本成功门 |

因此最低 Solution 成功覆盖是 **MuJoCo 3/3 + GeoPhys ≥1/3 + Isaac Sim ≥1/3**，不是九格全部成功。某个 optional-success 格出现普通任务失败且可安全运行，不阻塞成功覆盖；但 construction/admission/控制/记录不可用或 runtime fault 仍阻塞该格的部署切换门。报告分别列 deployment、task_success、solution_completed、lifecycle、reader/close 和失败原因，不能用一列 PASS 混合这些含义。

“原生 MuJoCo”指统一 Core 路线实际使用 MuJoCo solver，并保留固定上游 LIBERO/robosuite 任务、机器人、资产、reset 和 predicate 语义；不能拿另一个 Panda/简化 lift 替代。上游独立 native comparator 继续核对语义；只在未修改的上游环境跑成功，不能代替 GeoChora 部署后的 Solution 成功。原始三任务的来源/许可/闭包准入仍须完成。

每个 required-success 格至少交付一份同 run 的完整有效成功 episode 和独立可核查记录。工作包执行前固定 source、build、初始化集合/seed、horizon、重复次数、控制配方、容差和资源预算；旧有重复 reset/物理门不得用单次成功删掉。全量尝试和失败均入账，不事后删失败、换简单初态、放宽谓词或直接写入成功状态。该最低门不声称所有初态成功、统计成功率达标或跨后端轨迹逐值相同；更高成功率/seed 门只能在对应新范围明确约定，不在完成复核时临时追加。

后端切换按运行前 Execution/provider 配置选择理解，保持同一 task identity、逻辑 Solution 和公开 state/control 合同；允许有身份、经审阅的 provider 资源表示、映射与控制参数差异。采用 `SelectedReferenceEnv → RuntimeSession → provider adapter`，不回退 BaseTaskEnv 双路线、不在公共 Core 加 LIBERO 特判、不由 Solution 调 native step 或读取 provider-private state。运行中迁移同一 native 状态、任意 backend/device、render/video、逐值动力学等价均未纳入本次切换门。

### 与 develop-harness / Task Harness 的接入边界

已对照远端 `develop-harness` 提交 `9d0b3e524d67105e67ddb98e6dec903f19eb4255`（2026-10-30 ls-remote 回读一致）及本 camera 分支的后续 Harness 修复。该分支只实现 synthetic `pick-lift-v0` / MuJoCo 候选工作流，尚不表达本三任务的 On/region/Open。以下是接入约束，**不是已实现 LIBERO Harness 的声明**。

| Owner | 保留职责 / 后续接线 |
| --- | --- |
| `asset/benchmarks/libero/` | 原始 bytes/revision、逐资产许可、manifest、安装/验证和依赖闭包；Harness 只引用同一来源身份，不复制另一份资产真源 |
| `bench_deploy/libero/` | 三任务配方、source/reset/语义 binding、task-owned evaluator 与 Solution；输出供既有构造入口消费的声明，不另建 Runtime、Recorder、候选审批或任务工厂 |
| `task_env` Core / provider adapters | 统一构造、准入、生命周期、公开 state/control/contact、native lowering/step、记录及 close；benchmark 语义不下沉为公共任务白名单 |
| `task_env/script/agent/` Task Harness | 扩展既有 catalog/spec/compiler/semantic/feasibility/ledger/Oracle/Judge 工具，消费上述相同配方和 Core 路线；不复制 compiler/runtime 体系或把 LIBERO 改成 mock lift |
| Artifact / Experiment / Evidence / Human Judge | 保持来源、候选、运行事实与批准分离；Judge 包先 pending，技术成功不自动 approve/freeze 或取得 Qualification |

后续接入按 COMPOSE_EXISTING + 必要的 EXTEND_EXISTING 评估现有 owner，保持一个 canonical task/Artifact/reset/semantic/Solution 来源；允许版本化适配到 Harness spec，但不得悄悄改目标、fixture、机器人或初始化分布。真实 LIBERO 资源仍标真实 provenance，不能伪造 `synthetic: true` 以通过旧 mock schema；旧 synthetic fixture 也不得改标为真实。MJCF 与 USD/其他派生表示分别绑定转换 recipe、loss/验证报告和 provider source identity，不要求为了接 Harness 先把所有输入变成 USD，也不降低 F05 自己的 USD 出口。

复用 camera 已有 `completion_facts.py` / `harness-feasibility-completion-v1` 的 task、expert、lifecycle、fault、cleanup 原始事实与独立分类；对旧 develop-harness 必须携带相应完成事实/reader 修复，不能在合并时退回旧 solved 判定。不同 H5 版本保留对应 codec/reader，做显式版本适配，不重标历史 H5。

**R07c 完成不要求 F06/Harness 候选通过。** 实际宣称某个 LIBERO task/provider 已通过 Harness/F06 时，仍须该声明交集的四报告、至少 20 个不同声明 seeds 全部 solved、Oracle/H5、ledger 与 pending Stage-1 包；不能把本次“每 required-success 格至少一个有效 episode”冒称 Harness 20-seed 通过。也不强制将所有九格都声明为 Harness 可行。Harness/F06 完成和 Human Judge 审批单独记账；若对应实现正是 R07 路线必需的依赖，只据实际依赖记录阻塞，不能把整个 F06/F07 静默追加为 R07c 前置。

### 当前事实、结束条件与授权

当前仅 #1 的 MuJoCo3.8.1 CPU D01 部署交集有 `ACCEPTED_BOUNDED_R07C_D01_PILOT_S2_S3`；原结果 `task_success=false`、`solution_completed=null`。三项 Solution 全成功、九格部署切换、GeoPhys/Isaac 各一任务成功及 LIBERO Harness 接入均尚未证明；本次范围决定不升级旧证据。

R07a/b 对当前三个 required tasks 补齐审计/来源准入；R07c 三门全部经 Sol 独立复核才可记当前范围完成。R07d 的 session-bound 成本和独立 Human code-quality review、R01–R06 既有门及 P99 的其他条件保留，22 slices / 18 accepted 不因缩减任务数自动变化。训练、全初态鲁棒性、九格 Solution 全成功、#4/#5、F06 完成、正式 Qualification 不属于当前 R07c 必需出口，不得据此重开已完成状态。确需增加条件应另记维护者范围决定。

本次只修改文档/机器范围与 Skill 导航，复用 camera 分支，无新分支、实现/native、自动派发、merge/push 或 F 线写入授权。后续工作包按本节冻结具体 scope/资源与 source；F 线主 checkout 继续由其 owner 管理，整合时保留其当前 F 状态和已修复 Harness 合同。

## 历史决策与原范围记录

以下按原签署时点保留；当前任务范围、Solution 成功要求和后端出口以本页首节为准。

当前Sol决定（2026-10-30）：D01 diagnostic attempt002接收为 **`ACCEPTED_BOUNDED_R07C_D01_PILOT_S2_S3`**。公共Core去LIBERO特化、原三项运行缺陷及native004/H5/每步限位/warning证据已独立复核；Sol直接收紧三个异常输入拒绝门并新增8项检测，最终143项受影响S1通过，零新增native。原生事实仍绑定 `47d38ac4`，修复提交 `d0c89b57` 只有S1/离线验证。详见[Sol接收记录](../../../../maintenance/20261030_r07c_diagnostic_d01_attempt002_sol_review.md)。下文Luna待审标签保留历史时点含义；五任务、18/22、P99、Qualification及F线集成不变。

当前Sol决定（2026-10-30）：D01 attempt001为 **`R07C_DIAG_D01_PROGRESS_RETAINED_REWORK_REQUIRED`**。统一Selected/RuntimeSession路线、129项S1复跑和三H5/4800 step事实保留；生产contact漏revision校验、reset schema/profile拒绝发生在写入之后、实测手指超出源range而reader未检测，以及Core反向依赖benchmark语义需集中修复。详见[Sol复核与attempt002范围](../../../../maintenance/20261030_r07c_diagnostic_d01_attempt001_sol_review.md)。原Luna标签和下方执行记录保留为候选报告，不代表Sol接收。五任务、18/22、P99、Qualification和F线集成不变。

维护者追加：attempt002必须清除D01新增公共Core中的LIBERO专用入口、任务/布局/控制/初始化白名单和专用记录schema，沿既有owner转为source-bound typed contract；以非LIBERO、不同命名/通道数量的同链路synthetic fixture验证，不能仅改名。benchmark语义、来源规则与策略仍归bench_deploy。此项与已有返工合为一个完整窗口，未派发前冻结实际HEAD与预算。

当前诊断接续（2026-10-30）：维护者授权的 D01 diagnostic attempt002 已完成并等待 Sol 复核，目标仍为原五任务 R07c。公共 Core 已改为 generic source-bound typed mixed-control admission；最终 provider-free S1 为19 passed。MuJoCo 3.8.1/API3008001 CPU run004完成三回合、4,800 native steps、五次 reset、三份同run H5；独立 provider-free reader与五类实际bundle篡改拒绝通过，标签为 `R07C_DIAG_D01_ATTEMPT002_BOUNDED_S2_S3_PASS_PENDING_SOL_REVIEW`，完整事实见[D01 attempt002 execution result](#r07c-diagnostic-d01-attempt002-execution-result-2026-10-30)。attempt001 review状态和旧普通 attempt003 的 partial/失败不追溯升级；本次不宣称历史 fixture-to-row parity、task success 或 Expert completion。五任务、18/22、P99 与 Qualification 均不变。下文 2026-10-29 状态和原报告保留历史时点含义。

状态（2026-10-29）：R07a成本协议/S1及来源审计已有有界部分接收；R07b首pilot来源安装、部署配方及provider-free S1已获Sol有界接收；R07c pilot attempt003已交回PARTIAL/BLOCKED待Sol复核。新source composer恢复了上游 movable-object free-joint与命名规则；原`.pruned_init`安全解码成功，但其不含每行fixture pose或采样seed，不能完成原始reset映射。真正MuJoCo RuntimeSession mixed-control/contact consumer与同路线S1未完成，因此G1/G2未过、zero native。公开LIBERO `make_env` admission关闭；真实部署成本完整性仍缺失。原五任务整体仍未完成，首pilot固定spatial bowl→plate；历史记录保持其签署时点含义，原五任务最终目标不缩减。

2026-10-28 规划接续：本页五任务/原生语义/成本目标保留；新增真实 USD 与 Task Harness 接入由
[10](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md) 承接。
上游按已验证 USD 处理，Core 负责接收与 provider 执行绑定；其来源/验证成功不自动证明 benchmark 语义对应。
Harness 当前 mock `pick-lift-v0` 不能替代本页 On/In/region/Open/TurnOn/native-init 的任务映射。
F06 的 Expert/≥20-seed/Oracle 是新增 Harness 出口，不回写为本页五任务部署的新必需项；
本页任务完成/Expert/训练非必需的边界保持，R07 当前仍未执行。

## 1. 范围、来源和实际审计边界

首个 required Benchmark 候选为 LIBERO 下列五任务；RoboCasa 仅第二阶段 feasibility/scope recommendation。R07 不要求 Expert Solution、任务成功率、策略训练或机器人完整完成任务；但必须真实构造、重复 reset、语义对照和有意义的公开 Controller/Planner 物理交互，不能以静态编译、fake/random actions 或视觉相似充证。

LIBERO 固定 inspected candidate：`8f1084e3132a39270c3a13ebe37270a43ece2a01`，仓库 [Lifelong-Robot-Learning/LIBERO](https://github.com/Lifelong-Robot-Learning/LIBERO/tree/8f1084e3132a39270c3a13ebe37270a43ece2a01)。提交存在、未截断树与下载文件 Git blob bytes 已核对；这不是 dependency/runtime compatibility 已通过。共读取/核 hash 46 个 LIBERO 文件，包括 5 BDDL、8 init/pruned_init 文件、native evaluator/object/site/robot/source XML；raw files 留 ignored workspace，摘要在 [manifest](planning_manifest.json)。

审计时点：上述 46 个 LIBERO + 9 个 RoboCasa + 8 个 robosuite 文件的获取/审计来自 `535ce251…` 保存的前轮收据。本轮在该提交基线上重新确认 LIBERO commit，并重新抓取 16 个固定版本文本文件（含五 BDDL、loader、object/site/predicate、依赖和 robot/gripper XML），逐字节摘要与原 Git blob 一致；本地另复核全部 63 个既存源文件摘要。8 份 init 二进制本轮未重新下载或反序列化；完整 mesh/逐资产许可/依赖运行兼容核验及所有 native 语义/部署实验仍未执行。详见 [validation receipt](validation_receipt.json)，不能把重新读取源码写成 R07a 已验收。

[benchmark loader](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/benchmark/__init__.py) 实际为每个 Task 选择 `.pruned_init` 并调用 torch.load。五份对应文件都存在；libero_goal 两任务在此树中没有同名 `.init`，其他三任务另有 `.init`，不能互换。前轮初始化审计只检查 ZIP/pickle opcode 元数据与 bytes/hash，未调用 torch.load/unpickle、上游 import 或 native env；本轮复核保全文件摘要。元数据中的二维尺寸如下；其坐标含义、MuJoCo flat-state 顺序与实际 reset realization 尚未验证。

| # | Suite | Native filename（无扩展名） | 原 BDDL goal（原表达，不推断行为顺序） | pruned_init 编码 shape |
| --- | --- | --- | --- | --- |
| 1 | libero_spatial | `pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate` | `['And', ['On', 'akita_black_bowl_1', 'plate_1']]` | [50, 92] |
| 2 | libero_goal | `open_the_middle_drawer_of_the_cabinet` | `['And', ['Open', 'wooden_cabinet_1_middle_region']]` | [50, 79] |
| 3 | libero_goal | `push_the_plate_to_the_front_of_the_stove` | `['And', ['On', 'plate_1', 'main_table_stove_front_region']]` | [50, 79] |
| 4 | libero_90 | `KITCHEN_SCENE2_stack_the_black_bowl_at_the_front_on_the_black_bowl_in_the_middle` | `['And', ['On', 'akita_black_bowl_1', 'akita_black_bowl_2']]` | [50, 77] |
| 5 | libero_10 | `KITCHEN_SCENE3_turn_on_the_stove_and_put_the_moka_pot_on_it` | `['And', ['Turnon', 'flat_stove_1'], ['On', 'moka_pot_1', 'flat_stove_1_cook_region']]` | [50, 47] |

每任务精确 [BDDL / init SHA-256、init 条件、fixtures/objects 与条件前置](planning_manifest.json) 是机器审阅入口；任务名来自维护者指定集合，不允许替换难任务。language、BDDL `:init`、serialized native init、BDDL `:goal`、原生 Python predicate 是五种输入：language 不是动作约束，`:init` 不是对 serialized state 已实现的证明。

前轮审计读取 11 个真实资产 XML，42 个 file references 均能按路径在同提交树定位；检查了 mesh scales、joint/range、site、inertial 声明，本轮保留这些 source-bound 结果并复核文件摘要。外部 mesh/texture 原 bytes、完整 robot/scene transitive closure、逐资产许可和 runtime importer 消费尚未验证，不能称 verified asset manifest。LIBERO [root LICENSE](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/LICENSE) 为 MIT，不能据此自动批准 Google Scanned / HOPE / Turbosquid 等来源网格的再分发。

## 2. Native predicate 审计与不能简化的语义

固定来源：[dispatch](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/predicates/__init__.py)、[predicate functions](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/predicates/base_predicates.py)、[ObjectState/SiteObjectState](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/object_states/base_object_states.py)、[SiteObject](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/objects/site_object.py)、[Tabletop evaluator](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/problems/libero_tabletop_manipulation.py)、[Kitchen evaluator](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/problems/libero_kitchen_tabletop_manipulation.py)、[articulated objects](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/objects/articulated_objects.py)。以下是源码解释，未执行 semantic fixtures。

| Native 调用链 | 确认的语义 | GeoChora 映射风险 / 必需负例 |
| --- | --- | --- |
| On(a,b)→b.check_ontop(a)，b 为 object | b 的 body 高度≤a，真实 geom-group contact，XY body-centre 距离严格小于0.03m | bowl→plate/stack 均走此路；不是 bounding-box overlap，也不是 `Stack` predicate；测试无contact、0.03m两侧、上下关系/同高度 |
| b 为 site / region | 调用 SiteObject.under：`delta = site_mat @ (object_pos-site_pos)`；严格 XY half-size 界，Z 位于 size_z−0.005 与 size_z+0.10m 之间；有 parent object 时还要求 parent contact，找不到parent时仅under；无under分支可返回True | 保留矩阵方向与native条件分支，不能擅自改成“更正确”的逆矩阵或接触条件；table TargetZone/site与真实fixture分开解析 |
| SiteObjectState.check_contact | site 本身没有动力学，该方法直接True；这不取消 check_ontop 的 parent contact 分支 | 不能把全部site On当作真实contact，也不能删parent接触；逐状态对应parent身份 |
| SiteObject.in_box / In | world bounds采用abs(mat @ size)、严格边界、Z下界额外−0.01m；In=contact且contain | 不是本五任务所有goal都使用，但init/region解析与未来扩展需区分；不得混用On/contain |
| Open(cabinet middle site) | SiteObjectState 读取该site关联joint；交给其parent WoodenCabinet.is_open；任一关联joint qpos < −0.14m 为True（源码strict比较） | 查询middle_level而非任意drawer；−0.14边界/错误drawer/旧reset必须负例；不是文本“打开一点” |
| TurnOn(flat_stove) | ObjectState 遍历真实关联joint，FlatStove.turn_on 在qpos≥0.5rad返回True；同时更新burner视觉标记 | 分开纯semantic bool与native visual side effect；不能以图片颜色或force代替关节；若视觉副作用列required则另走renderer owner，不偷改只读Evaluator |
| Goal And | 两类problem的_check_success遍历当前goal列表作conjunction | stove/moka需要当前TurnOn且On，没有“先打开再放置”的temporal sequence；push任务仅On目标region，没有Push动作历史约束 |

真实接触对照继续追踪到 robosuite v1.4.0 的 [MujocoEnv.check_contact](https://github.com/ARISE-Initiative/robosuite/blob/fbee5844ff5632f5b5698e204ec5357ca50be0df/robosuite/environments/base.py)：按两个 geom groups 在当次 native contact list 中任一方向匹配。该 native 私有数据访问只用于独立原生对照进程；GeoChora 部署必须经 Provider public/canonical contact publication，不能把 `env.sim.data` 穿进 Core/benchmark adapter。

现有 [TaskDefinition/lifecycle](../../../../../task_env/environment/task_definition.py) 支持显式 predicate evaluator 和 unavailable/no_evaluator，但没有任意 BDDL 自动 compiler。当前 [TaskArtifact bridge](../../../../../task_env/environment/task_definition.py) 的冻结语义字段和 selected task predicate 也不自动承载这些 generic On/site/contact/fixture-joint 语义。是否能以 task-owned evaluator + Provider public state 精确表达，需要 R07a 逐谓词输出需求表。contact/site/fixture joint 无公开可用值时 **BLOCKED_CORE/BLOCKED_PROVIDER**；在批准合同内无法表达时 **NOT_REPRESENTABLE**，不能填False/静默简化或增加未经要求的temporal gate。

## 3. 机器人、依赖与资产准备

LIBERO [requirements](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/requirements.txt) 固定 robosuite1.4.0、bddl1.0.1、numpy1.22.4 等；[README](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/README.md) 建议Python3.8.13/Torch1.11.0。与既有 GeoChora Python3.12/MuJoCo3.8.1 不同，本轮不安装或声称兼容。robosuite v1.4.0 已解析到 `fbee5844ff5632f5b5698e204ec5357ca50be0df`；其他依赖需R07a/b锁定完整版本、wheel/native build/hash与隔离环境，不能直接升级Core依赖。

[ControlEnv](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/env_wrapper.py) 默认Panda/OSC_POSE、20Hz、camera_obs；实际tabletop classes将其改成 [MountedPanda](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/envs/robots/mounted_panda.py)：robosuite Panda XML、RethinkMount、PandaGripper与特定关节damping/base offset。已直接读取robosuite v1.4.0的 [Panda robot XML](https://github.com/ARISE-Initiative/robosuite/blob/fbee5844ff5632f5b5698e204ec5357ca50be0df/robosuite/models/assets/robots/panda/robot.xml)、[PandaGripper XML](https://github.com/ARISE-Initiative/robosuite/blob/fbee5844ff5632f5b5698e204ec5357ca50be0df/robosuite/models/assets/grippers/panda_gripper.xml) 与RethinkMount：Arm为7个torque motors；Hand为两个position actuators（finger1 [0,0.04]m，finger2 [−0.04,0]m），不是Menagerie single-tendon actuator8。当前受准入Position candidate的drive/feedback/target/apply契约不能直接套用，**BLOCKED_CORE controller/actuation mapping**需原Controller/runtime owner审议；不能未获批准就把torque motors改为position actuators并声称原生部署。不能直接以Menagerie完整Panda、旧hand-originTCP或已有100Hz selected recipe冒充原生实例。native OSC与Core Position adapter的Action/frame/hold/frequency差异要显式审议，保留物理资产，不承诺native controller算法等价；首版不要求复刻OSC或训练policy。

### 仅规划的两个 repository 区域

```text
asset/benchmarks/libero/  → source manifests / allowed source references / install+verify recipe
asset/benchmarks/robocasa/→ version/license/dependency feasibility references
bench_deploy/libero/
  task/ robot/ controller/ planner/ observation/ assembly/ evaluation/
```

本轮不创建上述可执行目录。asset owner 管来源、许可、版本化refs、允许分发的source与可复现安装/校验；不可再分发/尚未审查的资源只引用外部安装位置与hash，不批量复制upstream。bench_deploy仅拥有benchmark-specific Task Artifact/recipe、config、mapping与最小adapter，按现有Core职责组织，不拥有第二TaskEnv/Runtime/Recorder/Planner/Controller框架/registry。可复用通用能力不足须提交既有Core owner Extension review与精确admission；不得累积私有benchmark补丁。

R07b 的 verified asset source manifest 必须包含 URI/upstream repo+revision、per-file content hash、license/attribution/redistribution disposition、实际消费闭包和安装验证、geometry scales/单位/轴/wxyz、body/joint/actuator定义及顺序逆映射、mass/inertia/COM、limits/damping/friction/contact filters、Equality/Tendon/mimic与真实drive resources、scene/robot/fixture来源。必须包括distractors：spatial的两bowl/plate/ramekin/cookies/cabinet/stove；goal两任务的bowl/plate/cream-cheese/wine-bottle/cabinet/stove/wine-rack；stack的三bowl/plate/cabinet；stove的moka/frypan/stove及各table/scene。obj_of_interest不是完整资产清单。

## 4. R07c 的公开执行路线与条件前置

当前 [make_env/ENV_REGISTRY](../../../../../task_env/registry.py) 先加载注册模块、查精确UID，再分generic或selected construction；未知UID拒绝。selected PickCube/NutAssembly只有固定provider/backend/horizon，公开Position candidate只GeoPhys CPU、state-only、固定seed31/Scene/profile；不能给旧UID传任意BDDL/source就宣称可运行。候选部署须复用既有factory、TaskDefinition、assembly/source、RuntimeSession、Observation/Recorder owners，经显式review扩展source/admission与Task-local registration。native benchmark env只作独立语义/成本对照，不包装后冒称Core已经实现新的TaskEnv/provider能力。

首版五任务均建议 **authentic native preintegrated MountedPanda + 固定base + state-only + 待准入MuJoCo CPU**。五项一一声明：无全局R02/R03/R04/R05前置。若某项经审议配方确实改用split leaf→该任务依赖R02c；独立资产Attachment→R03c；dynamic public camera观察→R04c。必须在该Task manifest锁定chosen recipe与依赖、运行前检查并重算DAG闭包；不允许Required Task含未解析的条件或忽略其chosen dependency。native reference camera默认值不是本阶段自动required Camera训练接口。

| Required Task | 首版conditional R02/R03/R04 prereqs | 仍需先解决的Owner Gate |
| --- | --- | --- |
| spatial bowl→plate | none；明确使用原生预集成robot/state-only | native motor/gripper drive准入 + scene/free-body/reset + object On/contact evaluator |
| goal middle drawer | none；同上 | native drive准入 + cabinet middle site↔joint identity/strict Open/native reset |
| goal plate→stove-front | none；同上 | native drive准入 + TargetZone frame/strict under/parent分支；不要求Push动作方法 |
| 90 front bowl→middle bowl | none；同上 | native drive准入 + 两bowl object/contact/XY阈值，三bowl身份不能错配 |
| 10 stove+moka | none；同上 | native drive准入 + stove joint TurnOn与site On/parent-contact/conjunction、visual副作用分界 |

[CartesianPosePlanner](../../../../../task_env/planners/cartesian.py) 只做pose waypoint与速度/加速度限幅，源码明确不调用IK、不step；[JointPositionPlanner](../../../../../task_env/planners/joint.py) 生成7关节+gripper的8D平滑动作。均未证明通用IK、碰撞感知路径搜索或benchmark新robot的自动适配。必须实际通过其公开输出schema与Controller/Env消费链；需要generic IK/collision planner时BLOCKED_CORE并审原owner，禁止内部native ctrl直写或随机动作充Planner证据。

### 五任务共同的拟议最低部署验收

- 每Task固定source/init索引，至少3次reset，各至少64个合法真实outer steps；固定frequency/dt/hold，不假设native20Hz=Core100Hz。预先审议不同init rows、时间/设备/内存/磁盘预算并记录requested/realized状态。此数为规划proposal，未运行。
- 通过公开Controller/Planner完成限定workspace轨迹：实际joint与TCP有可测变化、gripper真实开合；建议事前门槛为TCP≥0.02m、至少一arm joint≥0.05rad、opening变化≥0.005m（依据资产范围在R07a批准，不能事后放宽），检查tracking/limits/finite/collision/contact日志和step时钟。轨迹应接近该task的对象/fixture并有受控接触/接触负例，不要求成功操纵到goal或自动完成整个任务。
- 同一公共env返回合法observation，使用既有Recorder写短episode并同文件reader核对T/T+1、Action/Target/Applied Ack/state/clock/identities与资源关闭。数组存储转换按R04原合同，state-only无需RGB；有RGB时CHW uint8，绝不强制float32 RGB H5。
- 每predicate至少一positive、一negative、一个threshold/boundary family；object On分contact有/无与XY/高度，site On分region strict bounds/parent branch，Open分middle/错drawer与−0.14m两侧，TurnOn分0.5rad两侧，conjunction分四个truth组合。固定fixture ID、source/native-order mapping与units，数值容差/边界epsilon在运行前冻结；bool对应state须一致，边界不确定带不能删除或默认PASS。
- 两组fixture provenance严格分开：`injected_semantic_fixture`（只用于可复现positive/negative/boundary对照）与`action_reached_state`（实际robot action生成，证明真实motion/state）。不得将注入成功状态当作机器人完成任务。native与GeoChora评估必须针对显式对应物理state/关节/site/接触事实，比对差异而非只比图片；本轮对照全部NOT_RUN。

失败分类：**BLOCKED_CORE**（factory/source/evaluator/Controller/Planner/public-state缺口）、**BLOCKED_PROVIDER**（公开物理/接触/构造能力不足）、**NOT_REPRESENTABLE**（批准contract无法准确表达必要语义）、**FAIL**（已执行但违反Oracle）、**NOT_RUN**（未执行/资源未准入）。每项保留原因/source/task/session/evidence，不自动PASS/DEFERRED，不换任务/简化predicate。budget timeout保留独立timeout fact，验收不通过。五任务之一阻塞即P99阻塞，直至维护者显式scope decision。

## 5. R07a 冻结的 Agent 成本协议（执行前批准）

所有生成的Agent日志、H5、视频、benchmark/evaluation outputs必须在既有workspace/Experiment/Evidence治理路径，不能写入asset/benchmarks或bench_deploy的可部署源码目录；source manifest只引用它们的稳定身份/路径/hash。

成本来自未来真实Agent Sessions，当前不填虚构数值。建议任务顺序按上表1→5，部署前与冷/热cache处置一起冻结。协议、任务顺序、functional acceptance、工具/模型/预算、比较设计须在任何R07b部署工作前冻结。复用Experiment/Evidence事实记录，不新建Agent runtime；PhysPi仍为外部消费方。

| 分域 | 拟议必需字段 / 计算与缺失规则 |
| --- | --- |
| binding | protocol ID/version/hash；Agent session/subsession IDs、Task IDs、Core/benchmark/dependency commits、source/recipe hashes、command/tool/log hashes、start/end、machine/provider/build。缺session来源不可作为实测成本 |
| code delta | baseline→final git diff；effective added LOC=新增手写production code非空/非注释行（排除generated/vendor/data，单列moved/copied）；减去删除行另报net，不以删除旧码降低added LOC。raw/net/effective/deduplicated views及过滤/AST工具版本都保留 |
| ownership与新增结构 | 分asset/bench_deploy/Core/provider/tests/docs；new adapters/classes/utilities、Core changes及理由、重复clone组/复用库、public API calls与private API violations逐项定位。通用修复不能藏在recipe |
| 七类复用 | Robot Asset、Robot Assembly、Controller、Planner、Task Semantics、Observation、Recorder分别记录existing owner/public API/source revision、reused/extended/new adapter/duplicated/blocked与Evidence；不能给一个综合“复用率”掩盖未消费能力 |
| time | total wall-clock起止；active development、installation/test/debugging/等待时间；用真实session/操作计时，不能凭日志间隔猜active。重叠并行session同时报interval union与worker-sum，分类避免双计 |
| tokens/money | input/output/cached-input分别取实际usage记录；说明input是否含cached避免双计。tool calls/retries/failures/human interventions及原因/人工时单列；金额仅在账单或真实usage+当次可核费率/币种存在时报告，缺失一律null+reason，不能以估算当测量 |
| first-time vs incremental | 首次环境安装/资产审计/共享adapter和Core extension单列setup；固定任务顺序，每任务独有incremental成本、共享改动按预先归属表记录；累计C(k)=setup+前k项incremental，边际ΔC(k)=C(k)−C(k−1)。失败探索/重试也计入；不把全部R01–R06历史开发成本任意分摊进R07 |
| maintainability | 固定静态检查配置/版本（LOC、复杂度/重复、public/private usage、测试/owner边界）+独立human readability review；保存reviewer身份/资格冲突、rubric、原始意见。部署Agent自评仅附录，不足以独立结论 |

静态比较需同一工具/过滤集合，新增classes数量/LOC本身不是越少越好；binary/data与installation量分别统计。记录缺失instrumentation、工具失败、未计入的外部服务和人工支持；不将“未读取到”当零。R07d必须给出可审计session-bound报告，即使部分tokens/billing确实不可得也写null/reason；若连主要session/time/source/log来源不可追溯，成本gate不能PASS。本轮真实部署成本均未测，未读取私人账单或以对话长度估算tokens。

R07a 还须固定真实部署的 `measurement_baseline_commit`、可复用模块版本与 setup 起点；本轮规划审阅提交不是未来成本实验的默认源码起点。R07 引发的通用 Core Extension 成本必须进入 setup/shared 或对应任务增量，并与已有 R01–R06 基础分栏；后者列来源与未纳入成本的边界，不能当作本次新开发、免费实现或降低成本的因果证据。所有口径与原始计数一起冻结，失败和人工帮助不能在汇总时被排除。

### Native-reference 成本对照与因果边界

拟议reference为同固定LIBERO/robosuite/native assets与同五任务、等价构造/3reset/真实运动/语义fixtures/记录/close验收的原生部署Agent流程。两侧一致任务顺序、初始cache、硬件、模型/effort/tool permissions、人类帮助、预算、日志与代码排除规则；native recording以等价字段验收，不强迫移植Core Recorder。记录差异/confounds，明确native既有env可用带来的setup差异。

**P99必需：描述性GeoChora实际Agent成本报告+独立代码质量审阅。完整native-reference Agent成本实验为额外研究证据，非当前P99必需**；native semantic comparator本身仍是R07c必需，不可与可选成本baseline混淆。没有批准的controlled design/样本量/预算与实际baseline runs，不声称“统计证明GeoChora降低成本”，不得从五任务边际趋势作因果推断。若要升级因果目标，需新维护者设计/预算批准，不能偷加到release gate。

## 6. RoboCasa 第二阶段可行性建议

固定审阅 `2ce1aecdd76e29b52d32fdb160436c5a3e230b07`，源码setup版本1.0.1：[repository](https://github.com/robocasa/robocasa/tree/2ce1aecdd76e29b52d32fdb160436c5a3e230b07)、[setup](https://github.com/robocasa/robocasa/blob/2ce1aecdd76e29b52d32fdb160436c5a3e230b07/setup.py)、[installation](https://github.com/robocasa/robocasa/blob/2ce1aecdd76e29b52d32fdb160436c5a3e230b07/docs/introduction/installation.md)、[Kitchen](https://github.com/robocasa/robocasa/blob/2ce1aecdd76e29b52d32fdb160436c5a3e230b07/robocasa/environments/kitchen/kitchen.py)、[download recipe](https://github.com/robocasa/robocasa/blob/2ce1aecdd76e29b52d32fdb160436c5a3e230b07/robocasa/scripts/download_kitchen_assets.py)。main仅是此次发现入口，后续审计按SHA，不按移动分支。

| 维度 | 源码观察 / 未验证事项 | 建议 |
| --- | --- | --- |
| 依赖 | setup pin MuJoCo3.3.1/numpy2.2.5等；安装文档建议Python3.11和移动robosuite master；与LIBERO1.4.0、Core3.8.1不同 | 独立lock/environment；未锁robosuite transitives即不承诺compatibility |
| license与资产 | [LICENSE](https://github.com/robocasa/robocasa/blob/2ce1aecdd76e29b52d32fdb160436c5a3e230b07/LICENSE) Code MIT并含Apache notice；[README](https://github.com/robocasa/robocasa/blob/2ce1aecdd76e29b52d32fdb160436c5a3e230b07/README.md)声明资产/数据CC BY4.0；下载recipe分fixtures、textures、Objaverse/aigen/lightwheel等集合，文档提示约10GB | 逐collection/实际文件核原许可/attribution/hash，不批量复制，不把总README声明当全部第三方授权证明 |
| embodiment/base | Kitchen处理PandaMobile→PandaOmron重命名、single robot、base/torso/arm/controller configs；不同robot/layout并非固定桌面Panda同义 | 逐选定robot锁base mobility/actuator/whole-body与控制模式；现有Position子链不授予移动底座能力 |
| fixture/scene | kitchen layout/style、cabinet/stove/sink等大量articulated fixtures、对象采样与collision/inertia开销 | 先选一受限scene审source规模、内存/资产/接触；不能承诺任意scene或五task支持 |
| Controller/Planner | composite config与base/torso依赖；Core只有受限Panda与waypoint helper，无通用移动base/全身IK/碰撞规划承诺 | 需要时BLOCKED_CORE，交原Controller/Planner owner review；不复制framework |

R07a交付source/asset/license/embodiment/fixture/资源/缺口与go/no-go recommendation即满足RoboCasa规划gate；native执行、五任务集、实测大资产预算均NOT_RUN，不纳入首个release envelope。只有维护者明确授权新执行范围后才扩展。

## 7. 四切片、P99 与待决定事项

| ID | 前置 | 交付 | 必需 Evidence / Stop Condition |
| --- | --- | --- | --- |
| R07a | P00 | 5任务source/predicate/init/asset/dependency审计、RoboCasa feasibility、成本测量协议冻结 | 审计/S1方案；protocol/许可/required semantic gap未决则不进入部署；本轮source inspection不是slice完成 |
| R07b | R07a | asset/benchmarks与bench_deploy责任划分、verified manifests/install、最小配方与Core extension清单 | S1来源/闭包/license/units/映射/admission；任何必需资产或owner缺口保持BLOCKED |
| R07c | R07b | 固定5任务真实construction/reset/motion/public control/Planner/state/recording + native semantic equivalence | 每Task S1/S2/S3；chosen conditional deps逐项检查；FAIL/BLOCKED/NOT_REPRESENTABLE/NOT_RUN不能过gate |
| R07d | R07c | 真实Agent Sessions成本/LOC/复用/失败报告、独立human code quality评审；可选reference研究分栏 | session/source/log/hash可追溯；缺required task或无独立审阅则阻塞；不能以self-score或虚构usage代替 |

建议阶段依赖 **P99 ← R06c, R07d**，保留R01–R06原required gates；R06b修正为依赖R06a/R01c/R02c/R03b。[07](07_Execution_Order_and_Acceptance.md)为统一执行表。七Goal/22切片仍是candidate，所有implementation NOT_STARTED。

维护者待决：7/22/DAG最终范围、5Task的初版state-only/robot/controller/frequency/安全trajectory与tolerance/预算、generic source/reset/contact/evaluator缺口的原owner扩展范围、逐资产许可与依赖兼容、RoboCasa仅feasibility边界、成本instrumentation与独立human reviewer/可选reference实验设计。任一Required Task无法表示或准入须显式scope decision，不能换题/放宽predicate/自动延期。Release、Scoped Engineering Acceptance、测试、Formal Qualification独立；本轮不签maintainer决定。

<a id="r07b-pilot-attempt001-plan"></a>

## R07b pilot attempt001：来源安装与部署配方实施定位（2026-10-29）

前置：R06c已接收；R07a004的Sol审阅已准许首pilot的来源级推进。首任务固定 `libero_spatial/pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate`，reserve stack任务本包不实施。原五任务保留，R07a不重开attempt005。只消费首pilot所需且已核验的源文件；93条已审计mesh/texture路径是起点，不自动等于包含BDDL/XML/init及所有依赖的完整安装闭包。安装原件留ignored版本化目录，tracked roots保留manifest/refs/notice/recipe/工具，不提交模型二进制。

| 层与真实owner | 本包允许实现/必须消除的缺口 | 本包验收 |
| --- | --- | --- |
| `asset/benchmarks/libero/`（拟建benchmark源交付区）；现`assembly/assets.py` closure helper | 可复现的显式revision/per-file hash来源manifest；从已验证cache安装到独立目标，verify仅消费manifest；解析XML include/file及upstream路径解析约定，缺依赖明确报出；原cache只读 | 真安装/再验证，独立目标重建；坏hash、重复/漏文件、越界路径、错revision/错任务、缺notice/未准入asset族拒绝；不import native |
| `bench_deploy/libero/`（拟建配方区）；现`assembly/source.py::TaskSceneSource`、`environment/task_source.py` | task/robot/controller/planner/observation/assembly/evaluation同一pilot配方与入口、source/init引用、成本协议绑定；TaskSceneSource只是xml/base_dir/source_id，不代表完整原生benchmark composer或任意BDDL compiler | CLI实际读安装receipt并生成有身份的声明配方；跨文件字段接线/错误输入S1，缺Core能力显式未准入 |
| `registry.py::make_env`、`TaskDefinitionBase`、`RuntimeSource/ExecutionSourceReceiptV1` | 明确未来公开构造入口、source消费与不可变receipt接线；本包不注册一个实际不能执行的UID、不私造TaskArtifact字段 | owner/方法/输入输出/错误/最小扩展清单；fake IO验证已有可调用接缝，不能冒称native admission |
| 现controller/action adapters、`planners/joint.py`、`planners/cartesian.py` | MountedPanda七torque motor+双finger position与Menagerie tendon Position不同；原20Hz/physics dt/hold/关节符号/TCP逐项声明；Cartesian planner不带IK | 维度/单位/frame/drive语义S1；缺motor控制或IK必须列准确Core门，不改actuator类型/机器人求绿 |
| `artifacts/contracts.py` reset/state与`TaskDefinitionBase.evaluate_predicates` | free-body/native init row布局、site/object/contact语义不能猜；On保留contact、XY严格阈值及高度，不换lift_height；pickle/init只当bytes核hash | 固定版本原输入与待扩展合同，available/false/unavailable分开；无torch.load/unpickle/native semantic等价声明 |
| Recorder/readers、public observation/clock | 沿当前Core记录/回读owner规划后续T/T+1与identity链，不建立benchmark Recorder/Runtime | R07c具体运行配方、oracle、成本与预算提案；本包不写真实轨迹/不运行R07c |

本包分类为COMPOSE_EXISTING来源/工具与benchmark-specific配方；没有现成完整安装器时只新增benchmark交付胶水，禁止第二Core框架。当前共用Core/Provider合同扩展先写明确最小补丁位置，留下一包在原owner内实现。未知输入导致的schema/字段/调用差错应在本包真实CLI与S1处理，不拖到native。

成本协议采用R07a003经Sol冻结v2.1候选与其精确hash；测量baseline为0309d73bb5b60f9989907c3eede8c0cd2893f29f，warm cache盘点；R07触发的通用改动计setup/shared。真实模型usage不可得填null+原因，不能用synthetic成本冒充本次会话。独立Human质量评审在R07d，不阻塞本包源安装。

预计主动90–150分钟，上限180分钟。provider-free S1/本地install+verify可多次修正重跑；每进程180秒/采样RSS2GiB，输出128MiB，独立安装目标256MiB；额外缺失固定文本来源最多32MiB，不下载未审计模型/不装上游运行环境。零native/零共享锁，原因是R07b的源/配方S1交付；不把attempt视为一次测试额度。

目标交付为`R07B_PILOT_SOURCE_RECIPE_S1_PASS_PENDING_SOL_REVIEW`或准确PARTIAL/BLOCKED，必须区分source_install_ready与core_native_admission_ready。所有本包源/配方S1通过也不等于R07b原五任务整体完成，不增加18/22、不表示R07c/P99/Qualification通过。下一包由Sol审阅完整报告后准备、维护者发送。


<a id="r07b-attempt001-execution-result-2026-10-29"></a>

## R07b pilot attempt001 执行结果（2026-10-29）

在 camera 输入 `21ea2965a1660a60d9f236793eb01f02e05ee7b6` 上完成有界来源包与单pilot声明式配方；实现提交为 `b1d5c8719f2289b6ee9fb20a5d0a22a8486d6c93`。最终来源manifest固定 LIBERO `8f1084e3132a39270c3a13ebe37270a43ece2a01` 与 robosuite `fbee5844ff5632f5b5698e204ec5357ca50be0df`，manifest SHA-256 为 `4ad168e4710f3153d0f1f470389a506df27588e4d5ce1eaec450289807d30a75`。manifest 含 103 个文本/来源载荷条目；选定场景闭包为89个文件、76,512,539 bytes（10个XML、92条XML文件边），不把未选中的robosuite默认arena纹理并入场景。安装到两个全新目录并分别独立verify；第二目录完成验证与篡改负例后清理。二进制资产只在ignored安装目录，不进Git。

provider-free CLI 成功串联 install→verify→recipe。最终 focused S1 为50 passed，tripwire未观察到MuJoCo、GeoPhys、Taichi、Isaac、Genesis、Warp、Torch、LIBERO或robosuite导入。`source_install_ready=true`、`recipe_s1_ready=true`；`core_native_admission_ready=false`。未启动native worker、未取共享锁。

recipe保留原任务 `On(akita_black_bowl_1, plate_1)` 及严格XY `<0.03 m`、contact和竖直次序需求；公开contact、free-body init realization、Core frame映射、MountedPanda 7 torque motor+双finger position对接、OSC_POSE 20 Hz至Core 100 Hz时钟/drive与planner映射仍未建立。native物理dt未由编译模型确认，init仅按原bytes/hash核验，没有反序列化或reset。`owner_gap_matrix.json` 和 `r07c_minimal_patch_checklist.json` 指向原owner的最小后续工作；本结果不代表任务执行或语义等价。

输出和逐命令原件位于ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r07b_pilot_001/`，安装树位于对应 `_install/`。成本事实按R07a003 v2.1原口径记录；该协议固定测量基线 `0309d73bb5b60f9989907c3eede8c0cd2893f29f` 不在本camera输入 `21ea2965a1660a60d9f236793eb01f02e05ee7b6` 的祖先链中，因此协议校验结果如实保留为 INVALID，不更改基线或声称有效LOC/Agent成本测量。token usage与货币费用不可用；活动时间未连续计量，保留null及原因。

状态为 `R07B_PILOT_SOURCE_RECIPE_S1_PASS_PENDING_SOL_REVIEW`。这只是单pilot来源/配方S1出口，原五任务总目标、18/22接收数、R07c、P99与Qualification均保持未关闭。详见本包 `report.md`、`evidence.json` 与 `commands.json`。


## R07b pilot attempt001 Sol接收（2026-10-29）

2026-10-29 Sol接收单pilot来源安装/verify/recipe S1为`ACCEPTED_BOUNDED_R07B_PILOT_SOURCE_RECIPE_S1`。135项包哈希、109项保护输入及45项冻结源码核对通过；Sol新进程独立verify保留目标的103个payload并重建recipe通过，50项S1按原日志复用。两个独立目标的原安装/verify收据保留，Sol未重新创建第二目标。Core native admission仍false，R07b原五任务整体未通过、接收计数仍18/22。成本协议仍INVALID：0309d73不是camera输入21ea2965祖先，另有asset/benchmarks Python被旧工具归为data的LOC缺口；原结果不改写，后续须先修订跨分支成本协议/代码归属规则。token/费用/连续活动时间未知仍null。初期3次构建缺资源采样如实保留；未重跑native或pytest。Sol同时更正后继owner符号并移除未获要求的全任务完成/通用碰撞规划门；R07c仍须原重复reset、有意义公开控制、原生语义及同H5验收。

独立复核入口：ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r07b_pilot_001/`。旧v2.1协议及INVALID记录保持；不得替换原baseline后把本轮改记有效成本。未来方案保留0309d73作为历史测量参考，另明确camera实际session输入/输出提交、共同祖先与跨分支继承成本账本，并修正asset/benchmarks Python工具的代码分类，经审阅后采用新协议版本；本次没有追溯批准新协议或启动R07c。

<a id="r07c-pilot-attempt001-core-s1-plan"></a>

## R07c pilot attempt001：现有Core接线与跨分支成本协议修正

R07b首pilot来源安装/metadata recipe S1已获Sol接收，native admission仍false。attempt001在同camera分支做实际原owner扩展及provider-free集成，不仅重复六缺口报告；预计主动150–210分钟、上限240分钟。attempt002理想用于复查和有界native验收，需Sol另发完整执行合同，本包零native、不取得共享锁，不依赖F线未合入代码。

| 改动面 | 实施位置与复用要求 | 本包出口 |
| --- | --- | --- |
| 成本协议 | 原R07a003 v2.1工具/reader保留；在`bench_deploy/libero/`就近建立版本化接续，保留历史0309d73 reference，新增实际camera session start/final anchors与merge-base/继承成本表；执行start→final仍须祖先链，历史reference不被冒充实际开始点。先于asset/data规则分类asset/benchmarks Python；不将测试/数据/通用Core改动免费排除 | 同祖先与跨分支正例、假commit/错误blob/跨run/重复成本/缺来源负例；本次真实记录缺usage仍null、缺继承计量保持partial；旧INVALID不改写，不声称有效总成本或成本下降 |
| 原生source与构造 | `TaskSceneSource`/`RuntimeSource`、`assembly/references.py`、现task factory及RuntimeSession边界；benchmark composer只拥有固定task assembly。核对source真实Python合并/命名前缀/style/关节/body/site/actuator；不能把散XML直接叫compiled scene | 真实安装→source composition/身份→原Core构造接缝→fake native IO集成，XML依赖/资源mapping/时钟先验通过；无真实compile/reset/step |
| 混合actuator与controller | `AbsoluteJointPositionActionAdapter`/`JointPositionServoBackend`仅支持position ctrl，不能把rad写进torque motor。复用既有公开Controller契约，在原controller owner最小扩展source-bound joint-target→bounded torque与双finger位置转换；保留旧默认类/行为 | 明确动作schema、torque N*m/finger m、name→slot、qpos/dof映射、finite/limit/clock/ack及fault负例；调用真实Core adapter和运行边界、只替换native IO，不造bench私有solver控制 |
| init/public状态/evaluator | `.pruned_init`仍不unpickle；先完成准确的decode/flat-state→版本化reset需求与安全显式输入接口。free-body/pose/contact复用当前公开Snapshot/TaskState/Evaluation owners，版本化缺项不回写旧v0 | 能实现的有界合同与S1先落地；不能用当前输入证明的mapping/接触/初始化保持unavailable/NOT_ADMITTED，不填零或把native-init换随机reset冒充等价。未闭合项必须给明确所需输入/下一最小补丁 |
| 后继验收 | 复用现有Recorder/public state/Clock/planners；不要求复刻OSC、完整task/Expert成功、通用collision planner | 记录3reset×至少64outer、原On语义正负/阈值、meaningful motion、同H5读回的精确后继合同草案；若native init/contact/worker无法provider-free贯通则明确NOT_READY，不启动native |

原生20Hz控制周期与physics timestep应从已锁robosuite源码查证；允许获取固定revision的小型macros/controller/config文本，source-declared dt与compiled dt分开。不得为填unknown拒绝读取已可核实常量，也不得把常量读到当编译模型验证。Core可采用显式审议的joint-space servo而非相同OSC算法，保持原torque actuator与物理source，记录控制算法差异。

本包目标为`R07C_PILOT_CORE_WIRING_S1_READY_PENDING_SOL_REVIEW`；仅当source/控制/原Core成功与故障路径S1真实贯通可用READY；其余必要init/contact/source问题仍有缺口时PARTIAL并报告，不因成本schema修好而声称全部就绪。原R07五任务出口、18/22与P99/Qualification不变。Sol复核真实diff和证据后才准备下一窗口，不要求Luna自行规划所有后继子阶段或重复旧audit。

<a id="r07c-pilot-attempt002-execution-result-2026-10-29"></a>

## R07c pilot attempt002 执行结果（2026-10-29）

输入为 camera branch `codex/phase-ii-01-camera` HEAD `fa1dc08f7b8ae7c23109f1157b0c964f563198a1`；GeoPhys pin `c6df840bef8d36b1150150167df08e29dc3f664c`、Menagerie pin `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。独立成本reader已从冻结输入、协议、只读Git对象和快照blob关系重算lineage/identity/measurement completeness；原合法自哈希伪造commit、nonancestor、wrong merge-base、snapshot/blob不匹配与partial→measured变体均进入对应拒绝门。测试只证明结构/拒绝逻辑；usage、token、费用、连续活动时间和历史继承金额仍未知。

同一 `BaseTaskEnv` candidate经过实际Core构造、`reset()`、`step()`、fault latch/recovery、现有Recorder和H5 v3 readers、`close()` finalizer。source composer由锁定的LIBERO/robosuite字节输出确定性107,165-byte MJCF，SHA-256 `22d6aa38dde89bf60309434dbd93155b7e740b3ea80df5e757801f5247e0cf16`；source/resource/name收据见本窗口ignored evidence。最后provider-free S1为成本reader 15 passed、source/Core Env及candidate worker/report consumer 29 passed、兼容owner 43 passed、3个真实provider节点deselected。最终三组process-wide import tripwire无命中。早期一次兼容回归尝试真实Pendulum并命中GeoPhys的日志保留，未计作pass。合成H5仅用于S1，不是物理轨迹；无native、无模型compile、未取得共享锁。

结果状态 `R07C_PILOT_PARTIAL_PENDING_SOL_REVIEW`，未满足 `CORE_WIRING_S1_READY`。`.pruned_init`原bytes没有解码或映射到flat-state；LIBERO BDDL/site/runtime placement没有重放；声明semantic names仍不是compiled IDs；当前GeoPhys没有实现可选typed `read_contact_summary()` peer方法，生产contact保持unavailable。native模型、compiled references、公开object pose/contact freshness、真实reset/运动与On语义等价都未验证，`core_native_admission_ready=false`。成本v2.2 candidate不升格为实际总成本，旧v2.1 `INVALID`保持。接收数18/22、原五任务目标、P99、Qualification、Human Judge不变；完整报告及机器收据位于ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r07c_pilot_002/`，等待Sol按diff复核，不自动开启attempt003。

<a id="r07c-pilot-attempt001-execution-result-2026-10-29"></a>

## R07c pilot attempt001 执行结果（2026-10-29）

输入为camera branch `codex/phase-ii-01-camera` HEAD `e07e7929105ad70b524f31b63c2b72025bc24c85`；实现和文档收尾分别提交，最终HEAD与证据/报告列于ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r07c_pilot_001/`。GeoPhys和Menagerie pins未变。该窗口零native、零shared lock，不导入真实模拟引擎、不compile/load/reset/step。

**Core source/control接线：部分完成。** `MountedPandaMixedActuatorAdapter`使用TaskDefinition扩展hook与真实`resolve_task_references`，保留7个torque arm槽和两个signed position finger槽、显式unqualified PD增益及source 20Hz / 2ms×25候选时钟。真实BaseTaskEnv action conversion与RuntimeBoundary调用到fake native IO，验证首条AppliedControl和write/close故障传播。版本化`ContactSummary`区分available-empty和unavailable；当前boundary不提供entity-pair query，候选On predicate对此返回unavailable。

`bench_deploy.libero.assembly.build_source_composition_plan`重读既有103载荷安装树并验证manifest、独立verify receipt、全体payload bytes及32项固定source-text references；8个对象/fixture semantic names确定且计划hash可复现。它只产出**composition declaration**：上游Libero/robosuite Python模型合并未执行，compiled body/joint/actuator映射和MJCF均为空。Core `make_env`尚无LIBERO source composer / Scene-v3 RuntimeSource consumer / candidate factory，`.pruned_init`行与Core reset state对应未知，故没有可native admission的路径。

最终provider-free candidate S1为25 passed；受影响predicate/fault-lifecycle/observation节点为39 passed，另2个真实provider节点按零engine边界deselected；成本协议v2.2 synthetic S1为8 passed。source installation/verify receipt按原冻结回执复用并交叉校验；旧v2.1 INVALID原结果不改。v2.2 lineage/LOC structural result绑定session start、final commit、历史reference `0309d73bb5b60f9989907c3eede8c0cd2893f29f`、实际common ancestor `b0b26e95ddfd7b5128401261f05541bb19586372` 与copy-bound prior sources。缺实际token usage、收费来源、连续开发时间、历史继承成本，均为null并注明原因；结构S1不能声称完整实测或累计R07成本。

状态为`R07C_PILOT_PARTIAL_PENDING_SOL_REVIEW`，不满足原计划的`CORE_WIRING_S1_READY`或native readiness。固定source composition、TaskEnv construction/admission、`.pruned_init`安全解释和reset、public object-pose/contact route、同Env Recorder/H5/independent-reader/worker-finalizer仍需后续冻结合同解决。原五任务目标、18/22、P99、Formal Qualification与Human Judge均未改变；没有自动授权下一attempt。


2026-10-29 Sol复核R07c pilot attempt001：`PARTIAL_WORK_RETAINED_REWORK_REQUIRED`，保留mixed control/contact合同与25/39/8项S1原结果，source仍声明计划、完整Env调用链未贯通。独立成本reader接受合法自哈希的伪造commit及partial→measured变体，v2.2不予技术冻结，必须补拒绝门。下一包须实际source composition与原Core构造/reset/step/fault/recording的provider-free完整链，仅native叶IO可fake；未授权native，不改变18/22/五任务/P99/Qualification。复核原件位于ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r07c_pilot_001/`。

<a id="r07c-pilot-attempt002-rework-plan"></a>

## R07c pilot attempt002：完整source与Core调用链返工

Sol复核attempt001为PARTIAL_WORK_RETAINED_REWORK_REQUIRED，保留controller/contact合同与25/39/8项S1，成本v2.2未冻结。下一窗口在同camera分支完成两类已复现缺口：①独立reader核验Git lineage、identity/快照/blob及真实缺项，不接受重签hash后的假commit/假MEASURED；②输出真实确定性组合MJCF，进入原Core构造/reset/step/fault/Recorder完整路径，只有native叶IO替换为显式fake。不再以declaration plan、SimpleNamespace._convert_action、手工boundary.apply和另一个对象close拼接当集成通过。

真实实现位置沿bench_deploy/libero/assembly.py（固定上游组合胶水）、task.py/evaluation.py、task_env/assembly/compiler.py::compile_task_scene及source/reference owners、environment/env.py::BaseTaskEnv.__init__/reset/step/close、runtime boundary/provider peer、现Recorder/H5 readers；先查已有source composer/控制/状态owner，最小扩展、不新建Runtime或TaskEnv。选定MuJoCo CPU后继，fake IO须在该实际运行路径的同一叶边界替换，不用另一个Provider的单方法测试冒充该路线。

init decoder/原行flat-state mapping、public对象pose/contact、ControlMap实际source绑定及typed故障记录能在纯S1内完成的本轮落地；源名字/声明布局与compiled native IDs分别记录，不能伪造编译。缺必需源事实时列具体输入和阻塞，不换随机reset、不把缺contact填False。零native/零compile/不import上游env；允许基于已锁source编写有界确定性XML组合及无pickle hooks的纯数据解码，未支持opcode明确拒绝。

预计主动180–240分钟、timebox300分钟；窗口内多轮修复测试。目标R07C_PILOT_CORE_WIRING_S1_READY_PENDING_SOL_REVIEW（不是R07c物理通过）；源组合/真实Env成功与故障/同H5读回没有完成则准确PARTIAL。现源码变化后重新跑受影响S1和原拒绝门，避免降低旧gate。上次native draft保持历史，生成新draft及明确ready blockers。若本次仍核心未解，第三attempt前必须重新梳理实际阻碍、官方/开源可复用方案和原门可行性；本包不自动第三轮或新native。


2026-10-29 Sol复核R07c pilot attempt002：`PARTIAL_WORK_RETAINED_REWORK_REQUIRED`。139项包哈希、32项保护输入、122项输入Git blob通过；15/29/43项S1与3个native deselect按原日志保留。实际组合XML的free joint为0，可动物体被固定，缺上游object实例化/free joint语义；同Env S1仍走GeoPhys consumer，未证明约定MuJoCo路线。init/placement、生产contact与freshness、native验证仍缺。planning manifest中07/09的旧hash不匹配，Sol当前修复，原报告不改。接收数18/22不变；第三attempt前须完成这些具体owner/方法方案及上游复用可行性判断，未授权native或下一attempt。复核原件：ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r07c_pilot_002/`。


<a id="r07c-pilot-attempt003-final-repair-plan"></a>

## R07c pilot attempt003：最后一次修复与有条件原生验收

前两轮root cause已明确：散XML模板拼接遗漏上游object实例化（实际产物free joint=0）；BaseTaskEnv旧bootstrap硬接GeoPhys，不能代表MuJoCo路线。成本reader拒绝门和同Env生命周期S1保留，不重做平台。attempt003为最后一次自主窗口，预计主动240–360分钟、总timebox420分钟，多次修复/测试/native运行按run记录，不另算attempt。

已核锁定上游可复用实现：robosuite `models/objects/objects.py::MujocoXMLObject.__init__/_get_object_subtree`（object子树、free joint、geom处理）、`utils/binding_utils.py::MjSimState.from_flattened/flatten`（time+qpos+qvel，na=0）、LIBERO `envs/env_wrapper.py::ControlEnv.regenerate_obs_from_state`与`bddl_base_domain.py::_reset_internal`（原状态回放与fixture变换）。源版本、notice沿已接受manifest，不安装上游框架；复用其纯数据/XML语义，不调用上游环境或不安全unpickle。检索发现旧`simulation/binding_utils.py`路径不存在，正确owner为utils，已更正。`.pruned_init`静态检查为ZIP两成员archive/data.pkl、archive/version，protocol2 NumPy f8数组、shape50×92；GLOBAL/REDUCE只能按已知格式符号解释，不能执行对象构造。未知opcode/shape/布局拒绝。

| 面 | 实施位置与选择 | 验收门 |
| --- | --- | --- |
| 动态source | bench_deploy/libero/assembly.py::_compose_mjcf；沿锁定object/fixture/robot/mount/arena代码还原实例化、顺序/前缀/变换/options | 可动物体free joint与fixture joints精确匹配上游；依赖、引用、物理属性、稳定bytes及篡改门 |
| init/reset | bench_deploy/libero就近纯数据decoder/semantic reset配方；Core现ResetSample/EpisodeResetPlan与runtime reset owners | 50×92原数据有hash；按上游joint遍历顺序证明nq/nv/layout与semantic映射，不能仅凭长度猜；原qvel不能静默清零；fixture静态pose先于state restore |
| MuJoCo消费 | task_env/runtime/sessions/source.py/api.py/control.py/mujoco.py、tasks/reference_env.py现binding seam及controllers owner；版本化内部candidate opt-in，不扩大旧position/tendon gate | 现RuntimeSession负责compile/reset/step/close，mixed torque与signed finger在原peer最小扩展；原Env入口消费，无benchmark Runtime。BaseTaskEnv GeoPhys假接线不能代替 |
| public状态 | MuJoCo peer把原生public API转为typed pose/contact，现TaskState/evaluation owners消费 | source/materialization/episode/boundary/query覆盖绑定；未知/过期与false分开；同一public状态On严格阈值比较 |
| 原生收口 | 同route完整fake-native叶S1、worker/finalizer/reader通过后，冻结本run源码/source/动作/增益/映射/预算 | 同一Env三次原始init reset各64outer、25×2ms/outer；公开motion/contact与原On，闭合H5 T/T+1独立读回。单pilot通过仍不是五任务R07c整体、P99或Qualification |

可行性判断：固定source、50×92数据和上游恢复布局均可取得，存在沿现RuntimeSession/Env扩展的实现路线，无需新框架或资产授权决定；风险是mixed-control admission与原joint order/fixture placement精确对应，必须在native前做provider-free证据。只有证明布局/source/consumer而非猜测才可进入物理门。允许在本attempt内通过完整前置门后做MuJoCo3.8.1 CPU有界验证，不再为普通字段/finalizer问题另开attempt。若布局或现owner不可支持，在门前如实BLOCKED并给维护者决策，不降低验收或自行第四轮。

包规定每native进程600秒、采样RSS2GiB、硬RSS3GiB，累计native墙钟3600秒、20000物理substeps、30次reset，输出1GiB；共享锁独占worker全部生命周期，无锁不导入native。S1每进程180秒/2GiB，多次修复重跑。源码/输入/增益/阈值在每run启动前冻结，变更另建run并留旧件；禁止用不同run片段拼PASS。详细资源、物理判据和断路门由同一冻结prompt约束。下一prompt由维护者转发，无自动派发。

<a id="r07c-pilot-attempt003-execution-result"></a>

## R07c pilot attempt003 执行结果（2026-10-29）

状态：`R07C_PILOT_PARTIAL_G1_G2_BLOCKED_PENDING_SOL_REVIEW`。输入HEAD为`3fcfb0c0b78c3659751c0918e02b0aea8d2e65d3`，source manifest SHA-256为`4ad168e4710f3153d0f1f470389a506df27588e4d5ce1eaec450289807d30a75`。G0冻结输入/单writer/资源预检通过。上游source适配输出确定性MJCF，静态审计见到五个movable free joints、fixture内部关节、源顺序及named resources；合法`.pruned_init`由不执行pickle构造器的固定格式decoder读取，50×92原始行hash保留。source-derived nq/nv布局仍未由compiled MuJoCo model验证。

G1被原始reset信息缺失阻断：92个值覆盖time/qpos/qvel，不含`wooden_cabinet_1`与`flat_stove_1`的每行placement；上游将其作为reset采样后的`model.body_pos/body_quat`写入，固定输入也没有配套seed。禁止用XML默认pose或新采样补值，故无法证明rows0/1/2的原始场景。G2同样未通过：本轮只修复了mixed adapter对`robot0_` arm与`gripper0_` finger前缀的名称校验；当前LIBERO候选依然走`BaseTaskEnv → GeoPhys`，没有接入MuJoCo `_MuJoCoSession` mixed torque/position、原reset、fresh contact与SelectedReferenceEnv/Recorder同路线。旧fake-leaf S1不代表G2。contact freshness仍无producer及公开episode/materialization/boundary绑定。

provider-free修复S1：安全decoder/source-control 32 passed；旧BaseTaskEnv synthetic fake-leaf/worker/H5回归2 passed，保留5个synthetic H5。曾有前缀/旧fixture字段失败，已在本attempt修复并重跑；失败原因记录于attempt输出。G3未冻结MuJoCo run；G4/G5未执行。MuJoCo 3.8.1 CPU未导入、未编译、未reset/step；native starts=0，reset=0，mj_step=0，共享锁未占用。无MuJoCo native H5、无contact正例。实现提交和报告见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r07c_pilot_003/`；本结果不增加18/22，不关闭五任务/P99/Qualification/Human Judge/R07d，不自动授权第四attempt。


2026-10-29 Sol复核R07c pilot attempt003：`PARTIAL_G1_G2_BLOCKED_CONFIRMED`，三次常规窗口已用完。82项包哈希/14项保护输入/136项Git blob匹配，5个free roots及原row hashes独立静态通过。G1缺历史fixture精确sample；G2 MuJoCo mixed/reset/contact/Env仍未实施。32+2项S1沿原记录保留；早期三次失败缺原始stdout。planning manifest中07/09旧hash再次过期，Sol当前修复，原证据不改。18/22不变，无native/第四轮授权。维护者可提供精确历史fixture记录，或明确批准按原BDDL语义新生成并冻结fixture realization的合同修正续接；后者不宣称历史等价、不重置attempt。复核入口：ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r07c_pilot_003/sol_review.md`。

<a id="r07c-diagnostic-d01-attempt001-execution-result-2026-10-30"></a>

## R07c diagnostic D01 attempt001 execution result (2026-10-30)

Final status: `R07C_DIAG_D01_PILOT_BOUNDED_S2_S3_PASS_PENDING_SOL_REVIEW`.
The package input was camera HEAD `06e289aaedc5d9e540beb56807e8cb898bf57c99`;
the native freeze bound implementation HEAD `4eaa76ba2b35a2d984559980bbf98f46bd4d333d`.
Final provider-free S1 run111 passed 129 focused cases in 29.14 s with maximum
sampled process-group RSS 787,726,336 bytes. It exercised the same
`SelectedReferenceEnv → RuntimeSession → MuJoCo adapter → existing H5 v3`
route with only bottom MuJoCo public model/data IO replaced; it is not native
evidence. The implementation correction computes Panda aggregate finger
aperture as `q1 - q2` because the source's second finger joint is negative;
the independent reader cross-checks this summary against H5 observations and
enforces the episode motion thresholds. The first locked run (run108) completed
but its old signed-sum summary was not accepted; run110's initial rerun exposed
one test-order assertion mismatch, fixed before run111. Both raw runs remain
preserved and are excluded from the final S1/native result.

The final native plan was frozen in run112 (SHA-256
`b3876b5558c6070d05d948490c63e3c4ee5aaff601fe6afd6f2de9b779327c32`) for a
fresh CPU run on MuJoCo 3.8.1/API3008001, with renderer disabled. It binds:
LIBERO `8f1084e3132a39270c3a13ebe37270a43ece2a01`, robosuite
`fbee5844ff5632f5b5698e204ec5357ca50be0df`, seed 19, rows 0/1/2, 64 public
outer intervals each, 20 Hz, 2 ms × 25, 4,800 expected `mj_step` calls, and two
separately counted public contact endpoints. Gains are explicit unqualified
joint-space PD `Kp=20`, `Kd=4`; this is not upstream OSC_POSE equivalence or a
controller qualification. The deterministic current fixture realization is
source-derived and recorded; historical per-row fixture parity is not claimed.

Locked run113 exited 0 in 4.83 s with maximum sampled RSS 1,402,273,792 bytes;
its process group exited and released the shared lock. The same Env produced
three 64-transition/65-observation H5s (192 transitions, 195 observations),
4,800 native steps and five resets, including the separate diagnostic endpoints.
Each episode exceeded the arm and TCP gates (0.713–0.760 rad and 0.380–0.404 m)
and the corrected aggregate finger-aperture gate (0.04067 m). The negative and
positive contact endpoints agreed between the Core predicate and source oracle
with 0 and 56 bowl/plate contact pairs. Run114 independently verified all three
H5s, worker/result and parent exit/lock receipts; it returned `verified_complete`.
Worker outcomes are horizon-truncated, `task_success=false`, and
`solution_completed=null`; no task completion or Expert success is claimed.

Cumulative attempt native use is four locked starts, 9,600 `mj_step`, ten
resets, and 11.3139 native wall seconds. Two earlier starts failed before reset
and contributed zero steps/resets; run108 completed its own 4,800-step trace but
is excluded because its worker summary used the wrong signed finger formula.
Run113 alone supplies the accepted same-run native/H5 result. No broader
five-task, 18/22, P99, Human Judge, D0/D1/D2, develop-full integration or
Qualification claim follows. Full run receipts, exact gate status, resources,
source snapshots and package manifest are in ignored
`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r07c_diag_d01_001/`.

<a id="r07c-diagnostic-d01-attempt002-execution-result-2026-10-30"></a>

## R07c diagnostic D01 attempt002 execution result (2026-10-30)

Status: `R07C_DIAG_D01_ATTEMPT002_BOUNDED_S2_S3_PASS_PENDING_SOL_REVIEW`.
This is a bounded result for the frozen LIBERO spatial bowl-to-plate source,
MuJoCo 3.8.1/API3008001 CPU, seed 19, rows 0/1/2, task-owned controller and
source-derived reset realization. It is not acceptance, Qualification, task
success, or closure of the original five-task R07 goal.

The package input was camera HEAD
`566ed511252d0afca5c247ba1ea8eac0c2b2a11b` on `codex/phase-ii-01-camera`,
with GeoPhys pin `c6df840bef8d36b1150150167df08e29dc3f664c` and Menagerie pin
`b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`. The implementation commits are
`73e573fa20ae0656cc6bef193fe233bc96d3df5b` (generic mixed-control selected
runtime ownership), `b2108d55052995a4639f4340fb29044279798df3` (safe 16 mm
aggregate aperture target), and `47d38ac40a3aa1a54107582cd4db75403dc6e0e5`
(evidence-driven unqualified PD gains `Kp=100`, `Kd=20`). The Core now admits
source-bound typed mixed actuator channels without LIBERO-specific task,
layout, or channel-count branches. A different-name/channel-count synthetic
fixture exercised the same SelectedReferenceEnv/RuntimeSession/adapter path.

Final provider-free S1 run `s1_full_pd100_001` passed 19 focused cases in
12.5791 s; maximum sampled process-group RSS was 669,437,952 bytes. It covered
generic shared-route fixture, contact revision, reset-before-mutation,
fault/cleanup, recording/reader semantics, monitor behavior, and tamper
negatives. The S1 substitutes only bottom public MuJoCo model/data primitives;
it does not count as native evidence.

The first two locked native runs exposed real source-limit failures and remain
preserved: `native_001` exited 2 at step 262 when `finger_joint2` exceeded its
upper limit by about 0.0000816 m; after fixing the task planner aperture target,
`native_002` exited 2 at step 304 when `flat_stove_1.button` exceeded its lower
limit by about 0.0000621 m, while the second arm joint had drifted substantially
under `Kp=20/Kd=4`. Both close receipts report zero MuJoCo warnings and successful
resource release. Their failed-worker budget charges conservatively reserve
4,928 steps and five resets each, instead of using their measured 262/1 and
304/1 close counts. `native_003` was rejected by the start-memory guard at
6,358,085,632 bytes, below the 6 GiB minimum; it acquired no lock and started
no native worker.

The final frozen plan `native/native_004/frozen_plan.json` binds the clean
implementation HEAD `47d38ac40a3aa1a54107582cd4db75403dc6e0e5`, exact source and
closure digests, controller/action/plan identities, MuJoCo package/binding/
library/header hashes, launcher hash, and remaining budget. Locked run004
started with 6,689,480,704 bytes MemAvailable, completed in 6.0084 s with
maximum sampled process-group RSS 1,546,661,888 bytes, and wrote 4,559,549
bytes. It exited 0, confirmed its process group had exited, and released the
shared lock. The same selected Env produced three 64-transition/65-observation
H5 v3 episodes (192 transitions, 195 observations), 4,800 `mj_step` calls and
five resets. Each episode passed arm/TCP and aggregate finger-opening motion
gates. The per-step monitor covered 13 limited scalar joints, reported zero
maximum excursion and all-zero warning counters. The negative/positive public
contact endpoints matched the source oracle (0 and 56 bowl/plate contacts).
Each episode ended at its 64-step horizon with `terminated=false`,
`truncated=true`, `task_success=false`, and `solution_completed=null`.

Independent reader run `reader_native_004` returned `verified_complete` for the
three H5s and verified 192 transitions, 195 observations, 4,800 native steps,
five resets, both endpoints, and parent exit/lock receipts. Its import tripwire
confirmed no provider/native runtime modules loaded. Five copied bundles made
from native run004 were rejected: stale result digest, re-sealed H5 interior
limit excursion, nonzero warning counter, missing warning counters, and wrong
compiled-model monitor identity. The actual native bundle and H5 files remain
unchanged.

The attempt's locked native budget ledger records three worker starts, 9.3652
seconds, 14,656 conservatively charged `mj_step` calls, and 15 resets. The
14,656 step total includes the two failed-run worst-case reserves; measured
close receipts for those failures were 262 and 304 steps. `native_003` did not
acquire the lock and is not a native start. Resource peaks are launcher samples,
not hard maxima. Token usage, cost, and continuous active time were not
available and remain unknown. The full report, gate receipt, commands, source
and run evidence, tamper matrix, documentation/Skill receipts, and manifests
are in ignored
`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r07c_diag_d01_002/`.

The fixed diagnostic is still not registered in `make_env()`. No task success,
Expert completion, historical per-row fixture parity, general Provider route,
other LIBERO task, five-task R07 completion, 18/22 count change, P99, Human
Judge, Formal Qualification, F05 integration, merge, or push follows. Attempt001
review and all failed run receipts remain unchanged; this result awaits Sol's
independent diff/evidence review.
