# F05–F07 后继重规划：多格式资产、统一物理语义与多求解器闭环（规划方向已采纳；执行待冻结）

> **状态**：`PLANNING_DIRECTION_ADOPTED / ATTEMPT001_REVIEWED_PARTIAL_REWORK_REQUIRED / NO_NATIVE`。规划与合同背景保留其签署时点；2026-10-30首个successor包已按维护者给出的冻结输入完成S0静态执行，tracked诊断与文档/本地提交已产出，Sol复核结果为PARTIAL、需补齐原包静态门；来源/原始字段采集事实有效，完整S0 PASS未接收。旧F05 attempt001–003、原同USD门和全部Evidence保留，不命名为attempt004；本结果不授予S1 native或Qualification。
>
> 原网页稿SHA-256：`94506530bb4d3751a6abed2c43b0ade32768e144b00b667599221edb65665519`；仓库补充解释见[第9节](#repository-adoption)。F线规划owner为`develop-full`；其他分支同步本文不表示已经集成该分支的实现或native结果。

## 0. 事实来源和状态边界

- 审查 HEAD：`develop-full@b24a1ac84bbfb32f91864ddc8121ea8af23a6c31`，`develop@41cbf537fd3d5a6d3ad07136bf2c868e0d149d62`。真正派包时必须重新 fetch/检查 HEAD、dirty、gitlinks 与现有 writer 状态。
- F00/F01/F02：各自 `ACCEPTED_BOUNDED_*`；F03：`ACCEPTED_BOUNDED_F03_S1`；F04：`ACCEPTED_BOUNDED_F04`；F05：`ACCEPTED_BOUNDED_F05_SOURCE_CONTROL_S1` 与 `ACCEPTED_BOUNDED_F05_MENAGERIE_GEOPHYS_CPU_NATIVE`，总体仍 `F05_OVERALL_PARTIAL`；F06/F07 尚未启动。
- F05 原合同仍要求**同一声明 USD 交付**在 Isaac/GeoPhys/MuJoCo 三 Provider 的真实 Core 闭环，另有 split Attachment 单元。此要求未被本提案静默替换。
- F05 原三个普通 attempt 已耗尽；任何新增原生运行或重定 F05 验收都要求维护者的新 Scope Decision 和有界工作包。历史 attempt001–003 与 F04 的原始失败和已接收证据均原样保留。
- 现存已知阻塞：官方 Panda USD `maxDepenetrationVelocity=+inf`／PhysX mimic 的 GeoPhys 消费，固定 MuJoCo 3.8.1 build 缺 USD decoder，split Attachment；F02 clean catalog、F04 ignored fixture/cold-checkout 限制；该列表不是全部软件缺陷的证明。

权威索引：[07 Execution Order](07_Execution_Order_and_Acceptance.md)、[10 historical F log](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md)、[08 Codex handoff](08_Codex_Phase_II_01_Planning_Prompt.md)。上游背景：Menagerie Panda `franka_emika_panda/panda.xml` 与 README；Isaac Lab 3.0 多后端资产导入；MuJoCo OpenUSD decoder（实验性，须单独构建）。

## 1. 原则和目标

**目标**：同一物理资产源（和可追溯的派生表示）在多个物理求解器中具有统一身份、可比较的物理结构、兼容的 Canonical State/Control，以及稳定的 Task 评价语义；**不要求不同 Solver 的数值轨迹相同**。

**不要求**：所有 Provider 必须原生解析同一文件后缀；所有源扩展必须无损映射；所有 Solver 都必须支持所有物理特性；GeoChora 建第二套 Scene/Runtime/Recorder/Controller；v2.1.0 立即实现完整 HPG 或真实机器人接口。

**硬性边界**：支持的源格式（USD、MJCF、URDF，后续可扩展）只是 serialization；物理能力（rigid body、articulation、mimic、tendon、joint drive、materials 等）才决定执行兼容性。`file parsed != semantic complete != model lowered != native consumed != task accepted`。

## 2. 共享 Panda 的选择与资格

**首选共同来源**：Google DeepMind MuJoCo Menagerie 的 `franka_emika_panda`，按仓库固定 gitlink（当前 Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`）及完整文件闭包冻结；优先复用 F04/F05 的 `local_menagerie_panda_r009` 派生 USD，与原 MJCF 建立 source→recipe→derived 的追溯关系。Menagerie README 描述 finger equality、tendon、position actuators，不能在转换时把它们默默丢失。

| 执行路径 | 现有范围或预期 | 身份与资格限制 |
|---|---|---|
| Menagerie 固定源 MJCF → MuJoCo | 上游原生模型可用；GeoChora 既有 MJCF selected/bounded 路径作为可能复用基础 | **尚未**证明同一 r009 的 Source/Task/Core 全合同闭环；不得充作 USD 三 Provider 原门。 |
| Menagerie → 本地验证 USD r009 → Isaac Sim PhysX | F04 冻结两 Panda 的 exact native cell 有界接收 | 不代表任意 Menagerie revision、转换配方或更多任务通过。 |
| Menagerie → 本地验证 USD r009 → GeoPhys CPU | F05 attempt003 exact native cell 有界接收 | 只对应隔离 GeoPhys candidate、零 COM free cube/support、特定 solver/build、两 episode。 |
| Menagerie USD → MuJoCo USD decoder | 现有固定 wheel/build 阻塞 | 仅在明确批准 USD-enabled build / 精确 decoder、导入能力与执行验证后才可能通过。 |
| Menagerie 表示 → Newton / MJWarp | 后续候选 | 目前**没有 GeoChora native accepted cell**，不纳入 F05 自动必选。 |

**资格策略**：以 `Panda Source Family` 为统一 source identity，但每个 representation 具有独立 SHA/recipe/validation identity；不得以共同名称等同所有字节和动力学。检查 source/model 的 link/joint/control/frame 映射、左右 finger 与 TCP、关节位置/速度方向、root/free joint、collision、质量/COM/惯性、mimic/equality/tendon、drive mode/gains/limit，以及物理交互必要关系。来源改动使相关证据失效。

**保留官方 Panda**：官方 Isaac Panda USD 不删除、不篡改、不改写旧 F05 失败。将其标为 *secondary compatibility / regression case*：将 `+inf`、PhysX mimic 视作解释与 solver 消费问题，需独立具体的 feature mapping 或 fail-closed；不再阻塞经明确批准的 Menagerie 共同基线。是否改变它在原 F05 required envelope 中的身份，由维护者另行批准。

## 3. 资产处理的最小设计：复用现有 owner

处理链路：

```text
Source Asset + exact closure / license / revision
    → format-aware reader (USD / MJCF / URDF)
    → semantic feature inventory + entity-qualified references
    → existing AssetDefinition / SceneDefinition / Assembly / Task bindings
    → provider-specific representation selection + feature coverage
    → provider-owned lowering / public model readback
    → Core Canonical State / Canonical Control / Task Lifecycle
    → Recorder / independent oracle / Judge
```

**不引入通用新 Runtime 或独立 Scene IR**。所谓 `Canonical Physical View` 仅为现有资产、Scene、Joint、Frame、Actuator 及报告组合成的**逻辑语义视图**；其版本化合同是否需要扩展，应由缺口审查决定。USD 是一等来源和交换格式，MJCF/URDF 保留原生路径；适合时通过声明的派生配方导向 USD，不强制所有来源无条件转换为 USD。

应复用的 owner：`asset/` 原始资产引用与 identity；`task_env/assembly/` 的 Source/Delivery、闭包与组合；`task_env/artifacts/` 的类型化 Scene/State/Receipt；`task_env/runtime/sessions/` 的 admission/native state mapping 与 provider-owned lowering；`task_env/controllers/` 的 Canonical Target/leaf mapping；`task_env/environment/` 的 Task Semantics；Recorder/Evidence 不改成第二套。

### 3.1 Physical Feature Inventory（候选附加审核视图）

以**对象级精确引用**记录 `source_format, source_revision, source_sha, feature_path, kind, source_semantics, normalized_semantics, units/frame, mapping_method, status, provenance`。起步仅覆盖 F05 Panda 需要的：rigid body、mass/inertia/COM、collision、fixed/free/joint、joint axis/limit、actuator/drive、mimic/equality/tendon、frame/TCP、source extension；不为完整软体/流体等预设字段。

状态必须区分：`recognized`、`normalized_verified`、`native_consumed_verified`、`unsupported`、`unknown`、`not_required_for_this_cell`。`retained_in_file` 不等于 `host consumed`；`selected` 不等于 `runtime admitted`。不能只列出字段名字不验证效果；不应使用不可靠的字符串驱动更改原 Source。

### 3.2 Compatibility Matrix（用户视图与机器证据分离）

每个单元取决于 `(Asset source SHA, representation SHA, recipe SHA, provider build, solver/backend/device, intended Task/feature set)`，不只是文件扩展名。用户矩阵保留 `PASS_BOUNDED`、`CONVERTIBLE_UNVERIFIED`、`BLOCKED_FEATURE`、`BLOCKED_BUILD`、`UNKNOWN` 等态；原始证据单独绑定。对相同源的不同格式，每格分 `parse / normalize / lower / native state-control / task` 五门。

### 3.3 State 和 Control 的必保语义

同一 Joint/Frame 的 Entity-qualified ID、维度、SI 单位、关节顺序与方向、姿态四元数顺序、COM/Link Frame 和控制模式必须一致。Native mapping 为 `canonical → native` 的明确双向适配（init/write 与 readback），不要求 solver 数值演化相同。Source/State/Control/Task 必须回读与独立证据验证，缺失状态 fail closed 或 `unavailable`，禁止造零补洞。

## 4. F05 后继的两条门槛：不得静默降低

**A — 后继规划主线“同源多表示”互操作门**（执行合同与预算待首包冻结）：固定 Menagerie Panda Source Family，在 MuJoCo MJCF、Isaac USD、GeoPhys USD 走各自有证据的 Representation；复用一个 Canonical Identity/Joint/Frame/Task 定义，至少验证统一 joint/FK、gripper response、free-body/reset/state/control、T+1/H5/close。该门面向架构目标；**不是原 F05 同一 USD 总门的替代凭据**。

**B — 原 F05 “同一 USD 三 Provider”门**：保持 `HELD`，直到具有 USD-enabled MuJoCo 的固定 build/decoder、相同 USD delivery 和相同生产 Core 路线的 native/reader/物理证据；当前固定 MuJoCo build 不满足。官方 Panda `+inf`/PhysX mimic、split Attachment 作为原门独立遗留事实持续列示。若维护者选择以 A 替代 B 为新的 F05 出口，必须先签署明确的 **Scope Decision**，写清旧门如何归档（DEFERRED/NOT_QUALIFIED）、新验收交集与后继依赖，不能将旧门记 PASS。

**本轮规划裁定**：按A组织后继路线，B在后继计划中显式延期；原B合同及旧F05总体仍保持未通过/HELD，不回填PASS。首个successor工作包之前再冻结具体Scope Decision、A的完整required feature集、B与官方兼容/split单元的延期处置和F06对应依赖。不是F05 attempt004，不追溯改变历史 `F05_OVERALL_PARTIAL`；原B的三次普通窗口仍记满，后继范围独立建账。

## 5. 候选后继路线（不是原 F00–F07 已批准 DAG 的变更）

| 候选包 | 内容与最小出口 | 前置/阻塞 |
|---|---|---|
| F05-S0 semantic inventory（静态） | 冻结 Menagerie MJCF/r009 USD、官方 Panda USD、相关 closure/recipe；给出结构/属性/损失与控制映射对照，识别 blockers | 文档和已验证文件可访问；不启动 solver；若 ignored 本地 r009 bytes 不可恢复，记 `SOURCE_UNAVAILABLE` |
| F05-S1 shared Panda route（受控实现/验证） | 精确完成 Menagerie MJCF→MuJoCo 与 r009 USD→Isaac/GeoPhys 的语义/状态/控制/读回对照；复用已接收 native evidence，只对**未覆盖输入**运行所授权的验证 | 维护者批准新范围、每 run 真实启动预算；不得用 raw upstream MuJoCo 代替 Core cell |
| F05-S2 optional USD-decoder/official compatibility（独立） | 固定 USD-enabled MuJoCo build 实际入口测试，或单独研究官方 Panda `+inf`/mimic 的 GeoPhys 等价消费；成果按 cell 记 | 不作为 F05-S1 自动依赖；不能无限期延展 attempt |
| F06 task harness | 在明确获准的 ready intersection 实施真实任务 20-seed、Expert/Oracle/H5、四报告/pending Judge；On/In/region 独立任务谓词 | F00 接受+对应 provider/asset/task native 已达门；保留 F06 原要求，**不能用 F05-S1 语义 smoke 代替** |
| F07 mixed-asset/provider extension | 组合不同来源的机器人/物体/fixture（如 MJCF robot + USD fixture），检验闭包、Assembly、Task/State、Provider matrix；Newton 单独候选精确 solver profile | 通过实际 ready cells 后才排期，不自动要求全部 LIBERO，R07 原预算/门另计 |

## 6. F06/F07 不变项与扩展项

F06 仍要求受控真实来源、可复现 Expert、至少 20 seeds、四报告、独立 task/Expert/lifecycle/storage/Oracle 校验与 pending Judge；不可用/失败 seed 如实记录。物理资产一致性的检查是新增*前置验证建议*，不替换其原本 Gate。F07 的更复杂场景按单元扩展：先一机器人＋刚体/fixture，再 mixed-format scene，再 articulated cabinet，最后 Newton/其他 solver 的具体 build；相关能力保留 `UNKNOWN` 直到实际验证。

## 7. 工程/治理条件

- 先检现有 owner、production caller、negative tests、文件格式与上游公开 API；对每项变化标注 `FIX_EXISTING / EXTEND_EXISTING / COMPOSE_EXISTING / NEW_IMPLEMENTATION`。
- 保留历史签署 Evidence、旧 V1 Hash、已接收 TaskArtifact/Scene 与 Reader，新增合同用版本化 additive path；旧源保留 byte/hash。
- 不破坏与 `develop` 的 R04c/R05a 等独立写入线；先确认单 writer、后冻结真实 HEAD/保护清单。本次文档调整**不授权** native、安装、push、merge、Qualification。
- 本轮同步 [07]、[08]、README、manifest和Skill中的规划入口/状态，不预填任何执行PASS；历史`validation_receipt.json`保持原字节。原R线DAG/P99不因本次F线重规划变化。

## 8. 已选方向与执行前待冻结项

本轮文档采用Menagerie共同基线和A同源多表示主线，将B同USD三Provider列为后继延期单元；官方Panda→GeoPhys兼容独立排期，split Attachment列为F07候选且旧F05相应门仍未通过。F06可在后继合同明确批准的ready asset/provider/task intersection推进，不继承全部Provider通过，也不能绕过本cell的required feature。

首个执行包必须形成明确的Scope Decision与真实输入：新required/deferred表、每cell源码/来源/build/profile、Task与控制器门、可复用证据及失效项、累计资源/timebox/重试、writer窗口、exact acceptance。具体数值未冻结则不启动；本文件不替代该包。Newton只保留F07候选，不自动要求新增Runtime或安装。

<a id="repository-adoption"></a>

## 9. 仓库接入时的约束澄清

1. **共享基线与资产策略分开**。Menagerie是这一轮跨Provider校准的共同来源；USD及Isaac系列资产仍是一等输入。官方资产走Isaac原生路线的优先级不被取消，官方→GeoPhys的secondary身份只限定兼容单元，不能泛化为拒绝官方资产。
2. **r009不能直接判等价**。固定原MJCF含双指equality、`split` tendon与8个actuator；现有r009有界路线使用9个驱动通道。旧native证明原门下的动作/FK/落体，不证明这些结构和控制语义完整等价。S0必须逐特性核对机器人及cube/support的几何、质量/COM/惯性、接触材料、控制和耦合。关键关系丢失或未知时S1阻塞；必要的新派生配方另定版本、声明变化，不覆盖r009，不按共同Panda名称认定等价。
3. **逻辑身份与精确hash分开**。共享entity-qualified Joint/Frame及Task/Action含义；不同representation/recipe/build保留独立identity。现有Scene/Artifact如包含格式/表示信息，可有不同精确hash，须有显式对应及等价证据，不伪造同一hash。logical view仅为既有owner与报告的组合，不预设新的通用Scene IR。
4. **先环境、后控制、再任务**。先核construct/reset/native public state/close及模型合理性，再验证空载hold/点位追踪和gripper/free-body，最后进入Task与Solution。FK读回一致不等于目标追踪稳定；Ack不等于位置达到。位置/方向误差、漂移、稳定时间等oracle与阈值在执行包中确定，不能从旧粗粒度motion/FK门自动继承为控制器合格。
5. **S0是前置语义门，不是固定准备轮**。只为影响实现选择的未知拆包；已知owner的实现、定向验证与收口可在一个完整successor窗口内安排。S0未通过时不进入依赖它的native。stage编号与S0/S1验证成本层级分开记录；attempt按完整窗口计，run/修复次数另记。
6. **证据与运行预算**。复用旧证据仅限source/recipe/模型/控制/接口/任务/阈值等受影响输入未变且覆盖新门的交集。每Provider在完整包中冻结累计wall/steps/RAM/VRAM/磁盘/锁预算及允许修复重跑，不默认一次launch，也不要求每次已授权的包内重跑重新问许可。失败原件和每run的新代码/输入freeze保留。
7. **跨分支与可恢复性**。F线owner为`develop-full`，`develop`只同步规划，camera/R07保持独立scope和writer。ignored r009/fixture、隔离GeoPhys候选及未集成gitlink是复现限制，先核可恢复交付与实际producer；不能用文档同步冒充实现合入。camera窗口未释放时只备补丁，不更改该worktree或HEAD。

2026-10-30早先规划同步阶段的签署状态为后继stage PLANNED/NOT_EXECUTED；旧F05 partial、旧Required门与Evidence原件保持签署时事实。该planning-only状态由后续首包执行记录（第10节）更新。当前路由以本文件与[12执行指南](12_F05_F07_Execution_Playbook.md)为准，[10历史记录](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md)保留旧门与执行历史，[07执行表](07_Execution_Order_and_Acceptance.md)给出后继依赖选择。

<a id="successor-attempt001-contract"></a>

## 10. 新路线三窗口与首包合同（2026-10-30）

维护者随后明确要求按新路线重新规划F05，仍设三个attempt，并准备首包供其转述。新账为 **F05 successor，最多三个完整执行窗口，总额度跨S0/S1共享**；不是每个stage另给三轮，也不是旧F05 attempt004。旧三轮及`F05_OVERALL_PARTIAL`、同USD三Provider原门未通过、已接收精确cell和失败Evidence均保留。后继范围采用A同源多表示；B同USD门及官方Panda→GeoPhys兼容延期，split Attachment后移为F07候选，均不回填PASS。USD／Isaac资产优先策略与一个Core Runtime保持。

新A required集合暂按完整物理语义冻结：机器人link/joint/frame/axis/limit、质量/COM/惯性、碰撞与接触材料、equality/mimic、tendon及传动、drive law/gain/damping/ctrl与force limits、free-body/support、canonical state/control/Task含义；不同表示保留独立精确hash。S0可以完整识别loss/unknown并被接收为审计成果，但关键loss/unknown仍阻止S1 native准入；不能将“已登记差异”改写为“已等价”。必要的新派生recipe必须单独版本化，不能默默将r009作为完整等价源。

首包 **`F05_SUCCESSOR_ATTEMPT001_SOURCE_SEMANTICS`**，执行S0语义盘点、可重复的tracked诊断工具与10类定向负例、后续真实补丁/迁移图、文档及本地提交。原MJCF的8-actuator/equality/tendon与r0099-drive及重标定参数为已知重点；来源、有效默认值、变换/单位、消费者和旧Evidence覆盖逐特性绑定。静态检查不能证明solver消费。输出必须同时给`inventory_status`和`cross_representation_readiness`，允许前者PASS、后者BLOCKED_BY_FEATURE。

执行窗口预计150–240分钟，timebox300分钟，最后30分钟收口；每静态child wall≤300s、采样PG RSS≤3GiB、启动MemAvailable≥4GiB、低于1GiB中止、采样≤0.25s、单重进程、最多4CPU线程；本窗口child累计wall≤3600s，新Evidence≤256MiB，官方资料网络≤25MiB。零solver/physics/App/GPU/renderer、零依赖/资产下载或安装、零实际格式转换。允许OpenUSD只读组成及明确无engine-init的公开GeoPhys source/host检查；不compile/load MuJoCo模型。Scope Decision仅授权转述后的首包静态实施；后续native预算和准确cell仍须新包冻结，不能从本三轮额度推定授权。

尝试目标：001完成语义审计与可实施修复方案；002依据Sol复核完成已批准的表示/控制接线及环境→空载控制证据；003仅在复评后作有界修复与收口。后两窗口为规划，不预授native。若S0证明关键语义无法等价，先交具体owner/缺失能力及需维护者裁定的来源变更，不能消耗后两轮重复审计或降低门。

复用`develop-full`及现有隔离GeoPhys worktree；零新branch/worktree，不切换或修改develop/camera，不更新gitlink。完整包在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_f05_successor_001/`；输出f05_successor_001/。该段是执行前冻结合同。实际输入HEAD及保护hash由首包snapshot绑定。

### attempt001 S0 执行记录（2026-10-30；窗口1/3，待Sol复核）

冻结输入为develop-full@ca5b9bb3c39fc23fc5b7ee69e94600e035c3fb79；Menagerie源修订b846dd12bc459d776cccb3dee0b1d02acbf7a9c7，只读GeoPhys候选41f8b517c5f92cd6e59907394dc42714b78702a7。诊断实现提交9634491a6438f1fcbe3eab367a8070abe678be33。最终run f05_s0_source_family_011退出0：原MJCF来源闭包68文件、r009 USD 130 prim；来源字节闭包核验通过，交付保持local-validated且source_verified=false。结果分层为inventory_status=PASS、cross_representation_readiness=BLOCKED_BY_FEATURE，阻塞joint identity、frame/COM绑定、equality/mimic、tendon传动、drive gain/damping/force、collision/contact material及派生free-body/support。

审计保留有限发现：源MJCF与r009 authored mimic关系和固定split tendon路径/0.5权重存在局部对应，但目标约束参数或消费合同未确立；8个源actuator对应drive的原始数值有漂移，不能由相似字段证明等价；cube/support是派生任务场景，不是源MJCF组成。10类定向负例均在预期校验点被拒绝。后续修补图和证据复用矩阵列在本包JSON结果中。

目标测试为5/5；最终受监督静态child 10.603秒，PG峰值RSS 354033664 bytes，4核亲和/并发上限，tripwire通过；child/进程组已退出，native lock未获取。run001–005的失败/中止回执保留，run006–011记录于ignored输出；所有run均零native、solver、physics、App、GPU或renderer启动。结果不证明solver消费、物理等价或Qualification；S1不得据此启动，F06/F07尚未开始。旧F05三轮、PARTIAL、旧门与Evidence保持不变。

完整报告、命令、资源回执、负例、源/目标inventory、patch计划与输出hash见ignored输出workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/f05_successor_001/。当前successor窗口计数为1/3，工作窗口已释放，等待Sol独立复核；后续窗口/范围/native预算仍须明确新授权。

<a id="successor-attempt001-sol-review"></a>

## 11. successor attempt001 Sol复核（2026-10-30）

决定 **`F05_SUCCESSOR_ATTEMPT001_REVIEWED_PARTIAL_REWORK_REQUIRED`**；Sol inventory_status=PARTIAL，cross_representation_readiness=BLOCKED_BY_FEATURE。上述Luna候选PASS记录及ignored原件保持签署时状态。完整S0审计可在物理差异未解时被接收；此次未接收是冻结包要求的静态检查、报告完整性与缺陷检测未完成，并非要求S0执行native或消除所有真实差异。

Sol核验输出142/142、保护输入5,401/5,401、原包14/14、runtime12/12、provider748/748匹配；实际CLI在独立输出目录复跑exit0（10.611s）、PG结束、tripwire通过，无native。独立反例确认：authored apiSchemas的未注册token在99个prim上未被记录；语义validator仅被negative_cases调用，真实比较路径调用数0；compiler angle缺省被误按radian。当前Panda显式radian源未因此改变，但parser/测试不足。九个Joint存在唯一同名path双射，序列化遍历顺序不同本身不是identity缺失。

返工须在原owner内完成：同时记录authored与registered schema；把10类负例接到实际loader/normalizer/report-validator；补齐单位/axis/frame/惯性与tendon length/Jacobian/两指非对称受力/limit的独立host核验；unknown须区分实际消费缺口与未做的静态映射。当前原始数字对照不能替代这些检查。下一补丁图需覆盖真实MuJoCo/MJCF及Isaac/GeoPhys路线、实际方法/字段/调用者和语义取舍；LeafNativeTendonMapping的身份字符串不代表机械耦合实现。Panda＋cube/support为A/S1 required，不能整体移到F07；复杂mixed资产/Attachment才属后者。

窗口计数仍1/3，剩余2；下包应有界补齐上述原包缺口并形成可实施决策，不重复全量来源采集。此复核不是第二包，也不授权S1 native或F06/F07。旧F05 PARTIAL及接收/失败Evidence不变；不需维护者在泛化unknown上盲选新配方。完整报告与反例在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_f05_successor_001/`，本次未改诊断实现或Luna输出。
