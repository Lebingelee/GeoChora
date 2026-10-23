# R07 — Benchmark Deployment & Agent Cost Evaluation

状态：**REVISED_DRAFT / PLANNED / NOT_STARTED**。本轮仅源码审计与规划修订，不启动 P00/R07a，不把审阅检查计为部署验收。独立父 Goal；不归入 R06 Compatibility。全阶段候选为 **7 父 Goal / 22 切片**，尚待维护者批准。

## 1. 范围、来源和实际审计边界

首个 required Benchmark 候选为 LIBERO 下列五任务；RoboCasa 仅第二阶段 feasibility/scope recommendation。R07 不要求 Expert Solution、任务成功率、策略训练或机器人完整完成任务；但必须真实构造、重复 reset、语义对照和有意义的公开 Controller/Planner 物理交互，不能以静态编译、fake/random actions 或视觉相似充证。

LIBERO 固定 inspected candidate：`8f1084e3132a39270c3a13ebe37270a43ece2a01`，仓库 [Lifelong-Robot-Learning/LIBERO](https://github.com/Lifelong-Robot-Learning/LIBERO/tree/8f1084e3132a39270c3a13ebe37270a43ece2a01)。提交存在、未截断树与下载文件 Git blob bytes 已核对；这不是 dependency/runtime compatibility 已通过。共读取/核 hash 46 个 LIBERO 文件，包括 5 BDDL、8 init/pruned_init 文件、native evaluator/object/site/robot/source XML；raw files 留 ignored workspace，摘要在 [manifest](planning_manifest.json)。

[benchmark loader](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/libero/libero/benchmark/__init__.py) 实际为每个 Task 选择 `.pruned_init` 并调用 torch.load。五份对应文件都存在；libero_goal 两任务在此树中没有同名 `.init`，其他三任务另有 `.init`，不能互换。初始化本轮只检查 ZIP/pickle opcode 元数据与 bytes/hash，未调用 torch.load/unpickle、上游 import 或 native env。元数据中的二维尺寸如下；其坐标含义、MuJoCo flat-state 顺序与实际 reset realization 尚未验证。

| # | Suite | Native filename（无扩展名） | 原 BDDL goal（原表达，不推断行为顺序） | pruned_init 编码 shape |
| --- | --- | --- | --- | --- |
| 1 | libero_spatial | `pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate` | `['And', ['On', 'akita_black_bowl_1', 'plate_1']]` | [50, 92] |
| 2 | libero_goal | `open_the_middle_drawer_of_the_cabinet` | `['And', ['Open', 'wooden_cabinet_1_middle_region']]` | [50, 79] |
| 3 | libero_goal | `push_the_plate_to_the_front_of_the_stove` | `['And', ['On', 'plate_1', 'main_table_stove_front_region']]` | [50, 79] |
| 4 | libero_90 | `KITCHEN_SCENE2_stack_the_black_bowl_at_the_front_on_the_black_bowl_in_the_middle` | `['And', ['On', 'akita_black_bowl_1', 'akita_black_bowl_2']]` | [50, 77] |
| 5 | libero_10 | `KITCHEN_SCENE3_turn_on_the_stove_and_put_the_moka_pot_on_it` | `['And', ['Turnon', 'flat_stove_1'], ['On', 'moka_pot_1', 'flat_stove_1_cook_region']]` | [50, 47] |

每任务精确 [BDDL / init SHA-256、init 条件、fixtures/objects 与条件前置](planning_manifest.json) 是机器审阅入口；任务名来自维护者指定集合，不允许替换难任务。language、BDDL `:init`、serialized native init、BDDL `:goal`、原生 Python predicate 是五种输入：language 不是动作约束，`:init` 不是对 serialized state 已实现的证明。

本轮读取 11 个真实资产 XML，42 个 file references 均能按路径在同提交树定位；检查了 mesh scales、joint/range、site、inertial 声明。外部 mesh/texture 原 bytes、完整 robot/scene transitive closure、逐资产许可和 runtime importer 消费尚未验证，不能称 verified asset manifest。LIBERO [root LICENSE](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/8f1084e3132a39270c3a13ebe37270a43ece2a01/LICENSE) 为 MIT，不能据此自动批准 Google Scanned / HOPE / Turbosquid 等来源网格的再分发。

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

现有 [TaskDefinition/lifecycle](../../../../../task_env/environment/task_definition.py) 支持显式 predicate evaluator 和 unavailable/no_evaluator，但没有任意 BDDL 自动 compiler。当前 [TaskArtifact bridge](../../../../../task_env/environment) 的冻结语义字段和 selected task predicate 也不自动承载这些 generic On/site/contact/fixture-joint 语义。是否能以 task-owned evaluator + Provider public state 精确表达，需要 R07a 逐谓词输出需求表。contact/site/fixture joint 无公开可用值时 **BLOCKED_CORE/BLOCKED_PROVIDER**；在批准合同内无法表达时 **NOT_REPRESENTABLE**，不能填False/静默简化或增加未经要求的temporal gate。

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
