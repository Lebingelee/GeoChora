# R03 — Physical Attachment

状态：REVISED_DRAFT；R03a attempt001 的 ENDPOINT_HAND_COMMANDS **FAIL** 原样保留；attempt002 的 INTERIOR_HAND_COMMANDS 在获批范围内通过独立 MuJoCo source/dynamics probe，Sol 已接收该有界工程出口。R03b attempt001 已由 Sol 接收为 `ACCEPTED_BOUNDED_S1_S2`。R03c attempt001–003 的失败原件继续保留。attempt004 在冻结 HEAD `4ac7284` 上使用一次 MuJoCo 3.8.1 CPU native start 完成 E1–E4，并发布正式 native receipt；独立 provider-free reader 从同 run 四份闭合 H5 读回256 transitions/260 observations并拒绝48/48 tamper。native 与 reader 门均通过，当前状态为 `BOUNDED_ATTACHED_LEAF_PUBLIC_ENV_S2_S3_PASS_PENDING_SOL_REVIEW`。该结果只限本包固定 Panda Arm+Hand source、seed31、2ms×5、四配置和两个 Position writer；不授予通用 Provider/Attachment 支持或 Qualification。

2026-10-28 当前恢复入口见 [07 检查点恢复合同](07_Execution_Order_and_Acceptance.md#r03c-checkpoint-recovery)：attempt004唯一启动额度已耗尽，当前只等待Sol复核；不得追加native启动或推进其他slice。
GeoPhys importer/双 source lowering/leaf adapter 与新 Isaac/已验证 USD 路线的补丁 owner 见
[10](10_Checkpoint_Recovery_and_Provider_Asset_Harness_Plan.md#3-按层级定位补丁)。
旧完整 Panda GeoPhys 证据不代新装配；单 Panda USD 可以独立接入，不因本页 split Attachment 成为隐藏前置。

## 已知事实与精确 Provider 路线

Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` 的 [panda_nohand.xml](../../../../../asset/external/mujoco_menagerie/franka_emika_panda/panda_nohand.xml) + [hand.xml](../../../../../asset/external/mujoco_menagerie/franka_emika_panda/hand.xml)，许可 [Apache-2.0](../../../../../asset/external/mujoco_menagerie/franka_emika_panda/LICENSE)，是两个独立资产来源，不能用完整 Panda 替代。

| 先前审阅观察 | 结果 | 不构成的证明 |
| --- | --- | --- |
| MuJoCo 3.8.1 分别加载未修改资产 | 编译成功：arm nq/nv/nu=7/7/7，hand=2/2/1、neq=1、ntendon=1 | 不证明 Core admission 或手的真实运动 |
| 公开 MjSpec.attach，以 prefix 把 Hand 挂到 Arm link7 frame 后编译 | 成功：nq=9、nu=8、neq=1、ntendon=1 | 无 solver/reset/step/Controller/H5；没有该独立装配的 Native S2/S3 |
| 同一导出 MJCF 经 GeoPhys a53 公开 SceneSource/import_scene_source | 拒绝：`geometry.articulation.site_config.invalid`，`site size: exactly 1 real, non-bool values required` | 只阻塞这份 source dialect；不证明所有 GeoPhys Attachment 不可能，也不改变 Phase II 旧路线结果 |

该导出 sphere site 带三分量 size；[MJCF parser](../../../../../GeoPhys/src/geometry/mjcf_loader.py) 将它交给 [SiteConfig](../../../../../GeoPhys/src/geometry/articulation.py)，其 [site_size](../../../../../GeoPhys/src/geometry/site_volume.py) 校验精确形状宽度。原导出 XML/JSON/失败日志仅保全并记录 hash，见 [planning manifest](planning_manifest.json) 和 [README](README.md#provenance)；本轮未重跑或修复它。

本轮以 **MuJoCo 3.8.1 CPU** 完成了一个精确 source/mount 与 INTERIOR_HAND_COMMANDS 的独立 native source/dynamics case；这只说明该固定候选在已执行的操作范围内通过相应oracle，不是 Core 运行支持。GeoPhys a53 对这份导出 source 仍为 NOT_ADMITTED/BLOCKED，未修复、未重跑，也不是该 MuJoCo-only case 的前置。第二 Provider required 范围须另行批准。GeoPhys没有整体退出Phase II-01：同pin的Phase II完整Panda旧Position/R1路线仍有真实运行证据；当前新leaf与fixed Attachment入口在Core中明确仅准入MuJoCo，GeoPhys adapter尚未接通对应新合同。历史site错误只证明精确导出source的import兼容缺口，不证明GeoPhys动力学无法执行Arm+Hand。source兼容修正、既有GeoPhys adapter扩展与新路线S2/S3是独立待规划工作，本次不更改现有DAG或新开Provider运行。

## R03a 提前 Gate 与可审计策略

前置改为 **P00**，不等待 R01a codec。先做 source feasibility，再投入大规模 lowering；可使用已审议的 mount/identity 草案，不以逻辑 Assembly 已实现为前提。

必须盘点：source dialect/版本与实际消费闭包（XML、mesh、default/include、纹理、license、prefix/name remap）；两个来源各自 root 与 mount；inertial frames/质量/单位；joint axes/limits；Equality、Tendon、mimic/驱动资源；碰撞几何与 exclusions；canonical→native body/joint/actuator 的顺序和逆映射；keyframe/reset、固定-base/child root 处置。信息存在于 source 不等于目标 solver 消费了它；逐项 CANONICAL_REPRESENTED / SOURCE_RETAINED / NOT_ADMITTED，必需语义缺失就停止。

GeoPhys owner 的候选策略：① 在其既有 MJCF importer 明确支持合法的 padded site dimensions 并验证有效维度/冗余值；或 ② 现有 Core source owner 采用带版本的、保持语义的 source normalization，保留原始 bytes、变换规则和新 closure，并经独立审查。两者均只是方案，未授权实施、未选择、未获得 Provider 批准；不得删 site、丢 equality/tendon 或放宽所有维度校验求通过。若需新 Provider pin，另行批准并记录新 Evidence，不移动冻结 pin/旧收据。

## 物理 lowering 与 Oracle

Attachment intent 独立版本化：stable Assembly ID + logical content hash、parent/child Entity 与 typed mount refs、kind=fixed、`T_parent_mount_from_child_mount`、碰撞白/黑名单、root 处置、source/closure。Attachment hash 不参与 logical hash 的反向自指；materialization receipt 绑定本次 Provider/build/backend/native topology 与映射。

首版为静态无环固定连接树，child 仅一个物理父级。MuJoCo 允许通过 jointless child body 的固定树表达约束，不要求创建不存在的 native fixed DOF；必须记录 canonical Fixed Attachment→native 固定关系的 lowering。独立 Hand 不保留第二个 world root，不能受两个 Runtime 推进。两个 canonical Entity 可映射同一 native articulation 的不同 link 集，但身份不融合；现有 single-Robot/dual-independent-root admission 不可直接冒充 attached-pair admission。

Oracle：`T_WC ≈ T_WP · T_PC`，米、弧度、wxyz，明确变换从 child mount 到 parent mount；分别检查位置范数/旋转测地误差。R03a 基于 source 精度/analytical FK 预先冻结 tolerance 与接触/自由运动片段，不事后调宽。必须在重复 reset、连续 Arm 运动、Hand 开合及受控接触/负载中测量刚性相对位姿、真实 q/pose 变化、coupling、有限性/稳定性与 collision filtering；看起来贴合、compile/FK 一致均不能替代动力学证据。

## R03a attempt001 独立 source/dynamics 结果（2026-10-26）

在维护者一次性授权的 MuJoCo 3.8.1 CPU 单进程运行中，实际加载的 Python package、binding extension 与 `libmujoco.so.3.8.1` 均匹配合同 hash；无 Renderer、CUDA 或 EGL。公开 `MjSpec.attach`、固定 mount compensation 和 compile 成功。模型维度为 `nq/nv/nu=9/9/8`、`neq=1`、`ntendon=1`，并保留 9 joints、1 keyframe、12 个非 world bodies、1 site、67 meshes、81 geoms、3 excludes；canonical/native 名称和顺序检查通过。

reset 与前两个 Arm interval 的 mount 误差均为 `0 m`，旋转误差低于 `8.4e-17 rad`。运行在 trial 1 的 Arm interval 3 失败：`probe_hand_finger_joint1=0.040001041818975604 m`，超出原生 `[0, 0.04] m` joint range，探针按冻结的 limit gate 以 `CandidateCheckFailed` 停止。累计成功 `mj_step=15`、`mj_forward=4`、native clock `0.03 s`；该门之后的 Hand 开合、load、第二 trial 与数值 dynamics oracle 均未运行，不能报告 PASS。观测到的有限性/warning 与已完成样本未触发错误，不替代未执行片段。

这是该精确 source、mount、reset、command 和 MuJoCo build 的独立 probe **FAIL**，说明 frozen Arm 动作与 Hand range/equality 的实际交集未通过既定限位门；不是编译失败，也不能外推成所有固定 Attachment 不可表达。不得调宽限位门、改变 oracle 或借此自动推进 R03b/c。完整批准合同、运行证据与 partial trace 留在本地 ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r03a_001/`，由该包的 `report.md` 引用；Git 中只记录摘要，不携带 raw evidence。

GeoPhys `a53a8cf` 对同一导出 source 的精确错误仍是历史 raw：`geometry.articulation.site_config.invalid` / `site size: exactly 1 real, non-bool values required`，原日志 hash `593befa15952ba86bd466b7c4bd2a7fd9c380cc141abd114a0bb5d9ea163c37a`；R03a 没有重跑 GeoPhys。

### Sol复核与后继输入提案（2026-10-26）

Sol复核接收attempt001的EXECUTED_FAIL：15行实际step trace及hash匹配；第3区间已积分但限位验证失败，不能计作3个已通过区间。该边界超出1e-6 m限值约4.18e-8 m，有限性/warning/mount在短片段内未失败，尚不能证明完整稳定性或装配动力学通过。原reset/open target位于0.04 m上限；后继提议保持原越界门及全部实测运动门，将Hand命令两端各内缩源行程的5%：close=0.002 m、open/reset=0.038 m，对应单actuator ctrl=12.75/242.25。源joint range 0..0.04 m和native ctrlrange 0..255不变。

维护者已另行授权INTERIOR_HAND_COMMANDS attempt002；本次输入目标为每finger close `0.002 m / ctrl 12.75`、open/reset `0.038 m / ctrl 242.25`。原生 joint range `[0,0.04] m`、ctrlrange `[0,255]`、source、mount、solver、equality/tendon、Provider pin及1e-6越界容限均未变。

## R03a attempt002：INTERIOR_HAND_COMMANDS（2026-10-26）

独立 MuJoCo 3.8.1 CPU进程正常结束，结果为 `COMPLETED_CANDIDATE_SOURCE_DYNAMICS_PROBE`。该结果是此attempt的单一bounded case结果；attempt001的端点FAIL、0/255端点行为和全行程均未被重新测试或改记。

模型按既有 `MjSpec.attach` mount 编译，维度 `nq/nv/nu=9/9/8`、`neq=1`、`ntendon=1`，canonical/native ordered mapping通过。两trial各完成192个outer intervals；reset状态逐项完全相同。Arm peak `0.09146 rad`、return error `0.00865 rad`、Hand-root旋转 `0.09314 rad`；每trial Hand opening最小 `0.01227 m`、最大 `0.06802 m`、excursion `0.05576 m`、equality mismatch最大 `3.91e-7 m`，每finger Hand-relative位移均超过 `0.03249 m`。两trial所有386个reset/outer-boundary samples的joint range overrun均为0；mount位置误差最大0 m、旋转误差最大`3.61e-16 rad`，无非有限样本或warning增量。

Trial 2同一pre-load state上的1 N world +X Hand-root-COM外载平衡oracle通过：hinge residual最大`5.56e-17 N*m`、slide residual最大`2.23e-18 N`、Arm投影`0.25465 N*m`；wrench清除后state与clock不变。两trial合计调用`mj_step=1920`、`mj_forward=389`，一组`mj_fullM`/`mj_jacBodyCom`；wall约`46.01 s`，峰值RSS约`257 MB`，证据目录约`5.81 MB`，均在预算内。该probe未产生接触，`ncon=0`；这不是contact response测试。负载轨迹差只记录为观测值，没有最小位移门。

报告与raw evidence保存在本机ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r03a_002/`，由manifest引用；Sol已复核实际六文件diff、1,920行step trace与386个样本，接收该case为`ACCEPTED_BOUNDED`。结果不证明 Core public Env/H5、Core S2/S3、固定Attachment admission、0/255端点或全行程支持；不授予Provider owner合同、Human Judge、R03b/c或Qualification。R03b/c仍未启动且保留现有DAG依赖。

Sol复核收据位于同一ignored交接根目录的`sol_review_r03a_002/`。复核未重跑native；原报告中“identity hand-root pose”的措辞应为保留源wxyz `(0,0,0,1)`（绕Z的π旋转），raw的RUNNING/PENDING_COMMIT残留标签不覆盖实际completed结果及提交。下一项按07进入R01a，不追加未批准的contact/端点/全行程验收。

## R03b attempt001：Core 固定 Arm+Hand Attachment（2026-10-28）

在冻结输入 HEAD `48bc7e023929df7aa843a2097014481cd6c3c806` 上，本包在现有 `task_env.artifacts`、`task_env.assembly`、`RuntimeSession` 与 task-owned candidate owners 中增加版本化 `FixedAttachmentPlanV1`、双 source closure/lowering、严格 `materialize()` opt-in 与 model-bound receipt。两个 canonical Entity、Scene-v3、既有 LogicalAssembly 和 TaskArtifact schema/fixture 保持独立与不变；native 只由一个 MuJoCo RuntimeSession 持有。该实现仅绑定本节列出的 Panda Arm/Hand source 与 fixed-tree route。

Provider-free S1 的19个source、Scene/Assembly pin、mount方向、root、映射、资源、碰撞和时间步负例均在 native 前拒绝；生产 `materialize()` admission 的正例通过。受影响旧 owner 回归集合为80 passed。首个native进程因源 MJCF 省略显式 `timestep` 而在native import/reset/forward/step前被 Core 的旧时间步门拒绝；保留该原始失败。包内仅用一次允许的pre-step普通接线修正，将2 ms默认只允许于显式 fixed-Attachment plan，并保留真实compiled model timestep核对；修复后的S1仍19项通过，旧回归仍80 passed。第二次且最后一次授权 MuJoCo 3.8.1 CPU 进程通过两个独立 materialization/reset trials。

两trial各完成128 outer intervals、640 `mj_step`、129 `mj_forward` 和1.28 s仿真。compiled model为 `nq/nv/nu=9/9/8`、9 joints、13 bodies（含world）、1 site、67 meshes、81 geoms、1 equality、1 tendon、3 excludes；物理树只有 `link0` 一个world child root。两次reset的Joint、Velocity、ctrl和time逐项相同。每trial Arm joint1 peak `0.09146 rad`、return error `0.008651 rad`、Hand-root rotation `0.09314 rad`；Hand opening最小 `0.012269 m`、最大 `0.068024 m`、excursion `0.055755 m`，finger-equality mismatch最大 `2.536e-6 m`，两finger相对Hand位移各 `0.032494 m`。实际compiled-state mount最大位置误差 `0 m`、旋转误差 `2.9803e-8 rad`；时钟误差为0，无限值或warning增量。两次close都确认model/data释放。

MuJoCo package、binding、实际mapped CPU library与公开header的路径、版本/API和SHA-256均匹配冻结输入。跨两个进程累计计数为materialization3（含保留的首次pre-step失败尝试）、reset2、forward258、outer256、step1280、模拟2.56 s；峰值观测RSS为336,027,648 bytes，闭包34,318,679 bytes，均在包内上限内。review产物与逐次账本保存在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r03b_001/`，以 `report.md` 与 `native_run_002/s2_evidence.json` 为证据入口。

Sol已复核实现提交 `ee5ed6c298bbdab206968873c61944ac35c66dbf`、两个model-bound receipt、256个运动样本和两份reset，并接收本精确case为 `ACCEPTED_BOUNDED_S1_S2`。复核中发现，错误的Scene Joint轴/拓扑/局部pose或Asset provenance在同步重绑hash后可能通过原静态门；Sol在既有Assembly/source与admission owners中补上source语义核对。19项新定向回归加80项旧owner检查为99 passed，原19负例静态包仍通过。修补只增加native前拒绝检查，正确candidate的Scene/Assembly/Attachment/Artifact/source身份不变；S2依据仍是Luna提交上的原始运行，Sol没有再次native执行。首次fixture/测试选择问题与修正日志均保留在ignored `sol_review_r03b_001/`。该接收不授予Provider通用合同或Qualification。S2只覆盖该源、seed31、2 ms×5、reset与冻结Arm/Hand motion片段；R03b未运行外载或接触测试。R03c 的 public candidate→Env→Recorder→reader S2/S3、H5与所有未列出的source/provider/backend均 **NOT_RUN**，R03c 保持未启动。R06 gate、R05a blocker、DAG、Required Envelope、P99与冻结refs不变。

## R03c attempt001 — candidate/S1完成，native预算耗尽

本包在既有Task/RuntimeSession/SelectedReferenceEnv/Recorder owners中加入显式opt-in的双Entity Position leaf candidate、typed dispatch和provider-free关闭文件reader路径。所选五文件定向S1最终为83 passed，其中包括两个writer与Entity绑定、固定Attachment source key到Hand leaf tendon identity的映射、既有R02b/R02c/R03b回归，以及不导入MuJoCo/Taichi的合成离线reader正负例。固定Scene、Assembly、Attachment、Menagerie source闭包及R02c原配置身份未改；该candidate没有注册为一般`make_env()`能力。

本包第一次MuJoCo 3.8.1 CPU进程核实了package/runtime/API与mapped CPU library/header身份，随后在public Env reset的leaf admission中发现Hand tendon映射把固定Attachment receipt的Entity key `panda-hand/split` 与leaf profile逻辑身份 `hand.xml/tendon/split` 混为一谈。进程在任何`mj_forward`或`mj_step`前失败；traceback证明一次materialization进入Core owner、一次reset尝试。修正后重冻代码和合同，并保留了首轮失败原件。

第二个、也是最后一个授权native start在MuJoCo导入前失败：runner仍按“账本只含首轮一行”校验，但其启动账本已按要求先追加了第二行。原stdout/stderr及prelaunch invocation均保留。随后的provider-free修正使retry counter从append-only账本首行重建，并以最终83项S1和无Provider import的定向counter reconstruction验证；**未再次启动native进程**。累计为native starts 2/2、materialization attempts 1、reset attempts 1、`mj_forward` 0、`mj_step` 0、outer intervals 0、模拟时长0。没有完整episode或真实H5，所以真实S2、关闭文件S3、tamper回读均未运行；不得把候选实现或S1通过写成S2/S3通过。原始输入、冻结合同、两次启动记录与失败日志见ignored [R03c attempt001报告](../../../../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r03c_001/report.md)。

### Sol复核：静态修补与待执行窗口

Sol复核结果为`S1_REVIEWED_NATIVE_PENDING`，尚不接收R03c S2/S3。原两次启动及83项S1是attempt001的历史事实；Sol补查发现原S1跳过真实attached-leaf admission，直接补上现有Core admission→public Env reset/step链，只有native model/data/I/O替身，不作为动力学证据。另修正reader对一致伪造Ack target、重哈希槽位互换的拒绝，并移除物理门中的1e-6额外放宽；零四元数也拒绝。90项provider-free S1通过。freezer支持显式新输出/snapshot/prompt的一次新窗口，runner提供与实际导入前同路径的`--preflight-only`，同时验证预追加启动记录，避免再次因账本形状消耗native。原native窗口2/2耗尽，Sol没有追加Provider导入或native；下一份attempt002仅是待维护者转交授权的一个新启动窗口，不是attempt001的第三次启动。

## R03c attempt002 — 一次native失败，S3未运行

2026-10-28，维护者授权在固定输入HEAD `b39bba45c1d39685bc1bd4869a61a2ca3c360208` 的现有阶段分支运行一次MuJoCo 3.8.1 CPU public Env窗口。S0快照、submodule/gitlink、v2.0.0 tag与保护输入哈希通过，attempt001完整SHA manifest仍有效；90项已复核S1按包复用，启动器provider-free `--check`通过。新窗口唯一子进程实际加载package/runtime 3.8.1、API 3008001及冻结CPU library/header身份，执行1次materialization、1次reset和1次`mj_forward`；在首次typed state snapshot处，`snapshot_v1()`拒绝`JointReference`而要求Scene `JointDefinition`。原始错误为`TypeError: typed Joint binding 'panda-arm/joint1' must be a JointDefinition`。native `mj_step=0`、outer=0、模拟时间0、无完成episode及H5；RSS没有样本，记null。`native_progress.json`的活动phase字段保留为`runtime_materialization`，而traceback显示失败发生在public reset之后的`env.session.snapshot_v1()`；保留二者原样并以traceback定位故障。

失败后按既有owner修正runner的`_candidate_bindings()`：从candidate固定Scene的Articulation中取`JointDefinition`，将leaf `JointReference`仅用于选择，不再把Reference冒充Definition。新增provider-free回归定向检查，关闭pytest插件自动加载后`1 passed`；首次pytest自动加载在受限sandbox中因插件开socket而`PermissionError`退出，该原件也保留。该修正确认不改source、物理门、配置或预算，且没有第二次native启动；因此修正尚未native验证。没有H5可供独立reader读取，S3为`NOT_RUN`，本attempt的S2/S3均不接收。报告、freeze、startup ledger、runtime identity、失败raw与命令记录见ignored [R03c attempt002 report](../../../../../workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r03c_002/report.md)。R06、R05a、DAG、Required Envelope、P99及冻结refs不变，未启动其他slice。

### Sol复核 attempt002

Sol核对提交`dfee52777069c1261334032e4924e8c136d08361`、attempt002的47项与attempt001的77项证据hash及冻结输入，接收失败归因和Scene JointDefinition修正的静态部分，状态为`S1_REVIEWED_NATIVE_PENDING`，不接收S2/S3。原预检只覆盖冻结身份与启动账本，没有覆盖runner在public reset后额外调用的typed snapshot；原Env S1也未执行该诊断调用。这是验证覆盖缺口，不是新的Hand动力学失败。Sol在现有S1补上四个episode配置的真实Core reset→runner bindings/requirements→snapshot/check-reset→public step→snapshot/check-outer，只有native I/O和几何数据替身；旧JointReference输入由真实snapshot接口拒绝。当前R03c定向模块20 passed，不作为native运动或H5证据。原raw/progress字段不重写，RSS仍null，native额度不追加；既有90项中的未变邻接检查继续复用。复核收据见ignored `sol_review_r03c_002/sol_review.md`。

## 切片

| ID | 前置 | 工作与交付 | 必需 Evidence / Stop Condition |
| --- | --- | --- | --- |
| R03a | P00 | MuJoCo CPU source/closure/机械语义的早期真实可行性与 GeoPhys 精确拒绝审计 | attempt001端点case FAIL保留；attempt002 INTERIOR_HAND_COMMANDS bounded case通过冻结source/dynamics oracle，Sol已接收该有界工程出口。不是Core S2/S3或Attachment admission；不证明端点/全行程；该R03a接收时R03b/c未启动，当前状态见下行 |
| R03b | R01c,R03a | **attempt001 已接收 `ACCEPTED_BOUNDED_S1_S2`**。精确两-source Panda fixed tree、source closure、model-bound mapping/topology、ResetPlan与真实相对位姿 | Luna原19项S1及Sol补充后的99项provider-free回归通过；两trial各128区间，冻结motion/mount/range/clock/warning/close门全通过。只限本包source/provider/seed/horizon，非Qualification |
| R03c | R03b,R02c | **attempt004 `BOUNDED_ATTACHED_LEAF_PUBLIC_ENV_S2_S3_PASS_PENDING_SOL_REVIEW`**。两个独立Entity的Position leaf接入既有 public Env→Recorder→reader owners | attempt001–003失败原件保留；attempt004在输入HEAD `4ac7284`上消耗唯一启动，正式receipt与完成progress存在，4个64/65 H5经独立reader核验，256 transitions/260 observations、48/48 tamper拒绝。精确范围和证据见本页末尾及ignored attempt004包；不扩展为通用Provider/Attachment或Qualification。

S3 必须沿现有 factory/SelectedReferenceEnv 或已明确批准的公共 candidate 入口，在原 RuntimeSession/Recorder owners 扩展；public path 不导入 test_*。失败保留原日志、partial apply/fault receipt、资源关闭检查；不伪装 rollback。R03 不依赖 Camera 或 R05 force-only 路线；不引入动态 attach/detach/闭环约束拓扑、USD ABI 或第二 Runtime。外部装配语义参考固定 [Isaac Sim 6.1.0](README.md#references)。


2026-10-28，R03c attempt003在输入HEAD `3b71683d5890c4ca1701037d59bce7b17de50a30`通过S0快照审计和provider-free launcher `--check`后消耗唯一native start。MuJoCo身份为package/runtime 3.8.1、API 3008001。E1–E4各64 outer、320 step、65 forward，合计4 materialization、4 reset、260 forward、1280 step、256 outer、2.56s；每份episode JSON均记录64 transitions、65 observations、close reader PASS、warning为0，RSS采样峰值440,950,784 bytes。四个原始H5仍保留。runner在E4完成后打包总资源数时因`native_log_bytes`未赋值而`UnboundLocalError`退出，未写`native_result.json`。独立reader新进程未导入provider，读出4 episode/256 transitions/260 observations，48个tamper全拒绝，但因正式native result缺失输出`OFFLINE_READBACK_INCOMPLETE_OR_FAILED`。因此该attempt的S2/S3均为INCOMPLETE；不能将H5数据门通过写成总体出口通过。之后仅把resource byte计数提前初始化，并使合成fresh-window测试按当前受保护文件bytes重建fixture；R03c模块20项provider-free测试通过。该修正发生在唯一native结束后，不代表原run代码通过或已native验证。报告及完整raw/commands在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r03c_003/`；原attempt001/002不变，不启动其他slice，等待Sol复核。

2026-10-28，Sol已复核R03c attempt003的两笔提交和53项签署hash：四份真实H5各64/65、1280次step trace、260 forward、四reset与四materialization、48/48离线tamper拒绝事实接收；native最终receipt缺失且exit 1，S2/S3仍INCOMPLETE。post-run计数修正保留。Sol在现有runner提取可独立检查的收尾方法，并在预算/进度写入完成后才发布正式receipt；新增13项成功出口、计数/缺episode、预算与写入/非有限值失败检查，模块33项provider-free S1通过。没有新native，下一包为同source/oracle/预算的attempt004一次启动收口；其结果仍待实际执行和Sol复核，不推进其他slice。复核见ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_review_r03c_003/sol_review.md`。

2026-10-28，R03c attempt004在输入HEAD `4ac7284a4cf770f28a1c5d1f9c81337a6b39c66d`通过S0冻结输入审计及provider-free launcher `--check`，随后仅启动一次MuJoCo 3.8.1 CPU进程，package/runtime/API身份为3.8.1/3.8.1/3008001，renderer未初始化。runner exit 0并生成正式`native_result.json`；progress为complete，无native failure或cleanup error。E1–E4各64 outer、320 `mj_step`、65 `mj_forward`、64 transitions/65 observations；总计4次materialization/reset、260 forward、1280 step、256 outer、2.56 simulated seconds。Arm活动episode joint1峰值约0.09999 rad、return-home误差不超过0.00188 rad、Hand root随动超过0.1003 rad；Hand活动episode闭合最小开口约0.01227 m、最终开口至少0.06802 m、行程约0.06489 m、手指不一致不超过6.4e-6 m。mount/reset、warnings、E3/E4 Arm配置变化与Hand命令不变均通过。采样RSS峰值459,276,288 bytes（每个返回的outer boundary采样，未覆盖interval内峰值）；写入期native/log与整包计数字段分别为8,377,716与8,403,108 bytes。

新provider-free进程对attempt004的四份已关闭H5独立回读，provider imports为0；逐文件SHA-256与native receipt一致，读取256 transitions/260 observations，四份各64/65，并完成48/48 copy-only tamper拒绝。状态为`BOUNDED_ATTACHED_LEAF_PUBLIC_ENV_S2_S3_PASS_PENDING_SOL_REVIEW`。复用此前经Sol复核的33项provider-free S1，没有因本次无代码变更而重跑。报告和全部运行原件在ignored `workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/r03c_004/`；attempt001–003原件不变。仅此精确MuJoCo CPU/source/seed/timebase/config交集进入Sol复核，不代表task success、一般Attachment/Provider admission或Qualification；当前不启动其他slice。
