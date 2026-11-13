# E05～E10 独立主审与小项收尾

日期：2026-11-13。结论：`REVIEWED_BOUNDED_ACCEPTANCE_RECOMMENDED`。审查输入 `d9dc02c65a54e51a9bd18548af6601941d39c49e`，此前最终生产 `91ebc9d6`；本次小修生产提交 `7a098423`。分支保持 `codex/v211-stage5-diagnostic`。维护者已接收 E00～E04；本报告建议接收 E05～E10 的既定实施范围，**最终维护者决定仍待确认**，不接收整个优化总账或 v2.1.1。

## 1. 独立结论

**六事件的主要职责迁移已进入生产调用链，S01～S40 在其约定范围完成实施与主审核对。没有发现需要再开底层架构重构的阻塞项。** 本次发现并结束一个生产 metadata 小缺口和现行状态索引滞后：通用 physical Recorder 不再把任何 `state.ee_pose` 覆盖为 PickCube 语义；专用账本、Goal、编排索引、当前状态及 Skill 区分历史规划、实施、自评、独立主审与维护者接收。

这不是“所有代码已彻底精简”的判断。相对于 `67cb643f`，compiler 518→420 行、Runtime API 1202→880、PickCube specialization 1207→600、Nut specialization 567→504、Nut Solution 1652→1407、H5 1823→1374；同时 source adapter 447→724，公共 Env 4393→4277。职责更可追踪，但参数较多的 adapter 阶段函数和较大的 Env 仍有阅读成本。它们目前承担有真实 caller 的受限构造与协调，未据此发现第二 Runtime 或推进 owner，不把文件长度本身再设为门。

| 事件 | 主审判断 | 实际依据与保留边界 |
| --- | --- | --- |
| E05 | 可有界接收 | compiler 消费 Scene/Robot 声明；Task物体与Robot recipe进入intent和实际source adapter；通用attachment与冻结资产profile分开。MJCF/USD合法分派、受限reference/replace保留，add未实现且没有冒称支持。 |
| E06 | 可有界接收 | USD/G05/fixed MJCF准入回provider owner；GeoPhys调用已有公开初始化/assembly；worker调用provider App能力。Runtime保留共同状态/clock/提交及唯一推进，精确资格不放宽；batch留G06。 |
| E07 | 可有界接收 | Robot主体投影、Task物体/兼容投影、共同space/schema校验真实接通；renderer需求在adapter，Env协调独立publication；CameraSpec已有延迟绑定继续使用。未扩展sensor/mount。 |
| E08 | 可有界接收 | capability被实际factory消费，Env不再维护RTX/颜色/pairing表；Isaac独立task request/fault，借用与独立视觉路线有原生证据。显示与sampling接口可不同；world RGB、颜色未校准及固定renderer边界保留。 |
| E09 | 可有界接收 | PickCube声明/准备任务事实，source adapter执行编译、Controller绑定与交付；Nut公共guard/interval回公共owner，严格任务guard保留；candidate未恢复。完整Nut Solution的跨事件要求留E13。 |
| E10 | 小修后可有界接收 | 普通v3、历史codec和严格Judge分层；非Panda短记录/同次RGB已读回；replay不替换历史身份。修复了通用metadata覆盖任务语义。单Controller/group、无图像独立内容摘要及structured重执行拒绝均保留原范围。 |

## 2. 方法、实际调用与证据身份

先用CodeGraph定位；其索引drift文件再读实际源码、AST、caller和diff。对照[总账](../../planning/post-5c-code-project-optimization-diagnostic-ledger.md)、[专用账本](../../planning/post-5c-e05-e10-remaining-ledger.md)和[实施结果](../20261113_e05_e10_u7_delivery.md)，审查实际生产链和原始收据，不以实施者的“已实施”字符串签收。输入状态、保护SHA、pins、源码清单、独立量度与检查在[本次输出](../../../../../../workspace/maintenance/v211_e05_e10_independent_review_20261113_001/input-snapshot.json)。

| 边界 | 实际调用／owner |
| --- | --- |
| 入口和构建 | `make_env → from_resolved_config → ReferenceTaskBinding.build_for_request → SourceBoundTaskBuilder`；TaskBuildRequest仍是共同交接。PickCube `make_reference_binding → build_panda_reference_stages`真实调用compile/compose/controller/finish阶段，Task回调只交任务事实，冲突的Runtime字段被拒绝并清理source。 |
| source | `TabletopSceneBuilder.build_scene_source`声明桌面；Robot提供component Frame和initial-control；compiler不按Task UID或Panda构造。`prepare_robot_source_intent → provider composer → final source/writers`保留先意图后最终绑定；`PandaReferenceSourcePlan`携任务事实进入既有builder，不是另一套Runtime。 |
| provider | `api.materialize/assess_selected_request`消费provider准入；`isaac_usd_admission`、`isaac_g05`、`mujoco_attachment_admission`保留精确限制。`_GeoPhysSession → bootstrap_task_runtime → provider_bootstrap → simulation公开assembly → GeoPhysRuntimeBoundary`，worker/App仍各有owner。 |
| 状态／图像 | `selected_reference`消费`binding.robot.reference_observation_*`与Task物体；renderer adapter声明具名Joint/Frame需求。Env的独立`_publish_task_rgb_typed_state`不覆盖Controller publication。consumer使用登记的camera capability，MuJoCo独立视觉模型只同步公开状态，GeoPhys/Isaac借用session。 |
| 控制 | 既有`control_lifecycle → control_submission → selected RuntimeSession`仍是一条提交/推进链。未把Position、effort、wrench变成相同物理命令。Nut的actuator8、2ms×5与guard有效性留Task，公共feedback校验单位/身份/时钟。 |
| 记录／replay | `Env.start_recording → begin_selected_recording → 既有writer → 版本H5/reader`。`load_legacy_leaf_control_h5`只解码，严格R02c/R03c Judge在版本诊断；`inspect_selected_replay`不make_env，重执行才检查源身份并进入当前正式make_env。 |

`build_panda_reference_stages`明确是Panda受限source adapter，不是声称任意Robot都用Panda配方；其MJCF/USD和Position/effort分派有不同资产及控制语义。简单主体已使用共同existing-subject机制，不要求伪造Panda字段。Empty只核对迁移影响，不新增完整任务矩阵。

## 3. S01～S40 逐项主审核对

`PASS_BOUNDED`指本账本约定的职责及受测范围足以结束实施；不等于任意组合或最终人工接收。跨事件完整任务成功要求仍按原E13保留。

| ID | 独立判断 | 最终实现／核对依据 |
| --- | --- | --- |
| S01 | PASS_BOUNDED | compiler无Empty/Panda配方分派；world/Tabletop声明、Robot Frame/初始控制和source adapter接收。新第三主体声明/外来控制拒绝纯检查通过，Empty旧source字节证据复用U1。 |
| S02 | PASS_BOUNDED | Task给物体/根/site等意图；Robot给recipe；Panda source adapter实际消费编译计划，provider负责原生表示。最终九条构造稳定身份与原始对照关联，不只改函数名。 |
| S03 | PASS_BOUNDED | reference/replace受限支持，add未实现且明确拒绝；最终writers可依赖Controller，未强行把全部构造放到Controller之前。 |
| S04 | PASS_BOUNDED | R06变体生成在版本诊断，产品历史recipe识别/inverse语义校验在panda_source_profiles；通用attachment消费显式source_profile。保留历史codec与严格检查，不将有界资产泛化。 |
| S05 | PASS_BOUNDED | MJCF/ USD snapshot、closure、lease和必要MJCF运动学文本分层；source类型/foreign/stale及失败释放均保留。Renderer不要求USD变MJCF。 |
| S06 | PASS_BOUNDED | SourceBoundTaskBuilder消费编译与Controller结果；source owner清理失败资源；四任务/装配映射见原始构造与native结果，源码清单实际对齐。 |
| S07 | PASS_BOUNDED | API协议/共同分派保留，精确USD/fixed资产验证分别由provider模块调用；不是整文件搬家，也没有新增Runtime。 |
| S08 | PASS_BOUNDED | F06 delivery/hash/policy/设备/profile仍严格；G05和fixed历史准入未删除。fake错交付/类型/drive拒绝独立检查通过。 |
| S09 | PASS_BOUNDED | provider_bootstrap调用固定pin公开`geophys.init_taichi`和`simulation`assembly；S09真实CPU短程和本次参数转发/未知backend拒绝检查成立。重复初始化仅沿既有首次生效语义。 |
| S10 | PASS_BOUNDED | provider只做source/native映射、reset、write、advance、snapshot、close；状态/clock和显式步数分别有代表路线。GeoPhys子步未独立计数，启动隐式推进unknown保留。 |
| S11 | PASS_BOUNDED | worker/provider App接口和父进程in-process/isolated分工真实；U2最终isolated证据及本次fake启动/失败清理通过；先前启动预算偏差如实保留。 |
| S12 | PASS_BOUNDED | transport/worker source及session失败清理、重复close独立检查通过，实际原生close收据复用；不升级为SDK所有退出无警告。 |
| S13 | PASS_BOUNDED | Robot拥有Panda投影、PickCube拥有switch alias，公共组合接受非Panda Robot；本次fake非Panda检查通过，简单任务保持自身观测。 |
| S14 | PASS_BOUNDED | space/schema/数组校验与Robot/Task字段metadata真实关联；嵌套schema、dtype/shape、unknown含义处理检查通过，不虚构单位。 |
| S15 | PASS_BOUNDED | renderer state binding在camera adapter；Controller和renderer view分开、同boundary/clock。独立publication/stale拒绝检查通过。 |
| S16 | PASS_BOUNDED | CameraSpec延迟绑定、canonical geometry复用；普通caller无需hash；高级身份检查保留。没有新增同功能配置系统。 |
| S17 | PASS_BOUNDED | world、RGB HWC float32、身份/episode和格式限制仍生效；错误capture和schema检查通过，未扩展mount/depth。 |
| S18 | PASS_BOUNDED | 四任务字段/边界证据及非Position RGB关联；本次metadata小修使Recorder继续尊重声明，未手工补字段绕过schema。 |
| S19 | PASS_BOUNDED | task capability和observer capability关联实际consumer/factory；Robot声明source family和Controller能力。不是只在registry加名称；纯查询/未准入/foreign descriptor检查通过。 |
| S20 | PASS_BOUNDED | native setup/颜色/共享extent在render owner；Env引用capability并编排。小量按provider调用session的委派保留，未形成另一个adapter实现。 |
| S21 | PASS_BOUNDED | Isaac独立task请求与局部fault、共享clock fault、detach失败owner保全有fake检查；U4headless和S19双相机真实采集/close证据成立。 |
| S22 | PASS_BOUNDED | MuJoCo visual-only不step；GeoPhys binding设置并读回FOV/near/far，不符即拒绝，原生borrowed结果沿该路径通过。既有光照限制保全。 |
| S23 | PASS_BOUNDED | 单环境UI改用public source camera/set_camera_pose/read_frame；无跨owner旧私有方法调用。公开UI原生呈现证据和本次frame/presentation检查对应，不扩展全部OS事件。 |
| S24 | PASS_BOUNDED | 通用相机数学无Taichi顶层依赖，UI提供输入常量；纯导入、键盘/中键检查通过。输出spec来自adapter，未声称颜色科学或性能提升。 |
| S25 | PASS_BOUNDED | borrowed/cross、非Position、reset/step/再reset、重复render零时钟增量和frame保留有受影响原始证据；本次camera stale/close检查通过，不要求最终HEAD重跑所有格子。 |
| S26 | PASS_BOUNDED | candidate/旧UID未恢复；配置、质量资产和Solution保留。新增观测文件有明确Task责任，不按“四文件”机械删业务。 |
| S27 | PASS_BOUNDED | Task准备source事实，adapter实际compile/compose/controller/finish；无千行新特化文件平移。两类Task越权结果拒绝/释放的原JUnit通过，31个冻结源码hash与当前一致，可精准复用。 |
| S28 | PASS_BOUNDED | completion拥有通用guard，feedback拥有通用interval；Nut本地仍严格actuator8、2ms×5、cadence和抓取策略。独立guard连续性/恢复/优先级及错误测量检查通过。 |
| S29 | PASS_BOUNDED | 简单任务无新native/相机旁路；Nut短程不改称完整成功，completion/raw predicate/runtime各自表述保留。 |
| S30 | PASS_BOUNDED | 直接harness/record/replay及有价值行为已迁；历史私有helper不成为产品兼容目标；全库diagnostics/caller治理明确留E11/E12。 |
| S31 | PASS_BOUNDED | writer/schema/reader调用链实查；canonical与physical v3不混为自动保存RGB。普通v3按T/T+1，非固定64样本。 |
| S32 | PASS_BOUNDED | H5通用I/O、legacy_typed_witness/leaf codec、严格Judge分层；两份真实旧H5及篡改拒绝独立通过。严格函数AST与迁出前一致，没有Core反向import诊断。 |
| S33 | PASS_BOUNDED | Recorder metadata消费真实控制/source/schema；本次删除3行PickCube语义覆盖，三种声明语义经metadata与H5投影保留；两简单主体真实记录读回通过。 |
| S34 | PASS_BOUNDED | 已有XML/provenance缓存保留；U6实际Nut开始5次/5文件、interval后仍5次。只承认该scope，无新热点依据故不新增跨reset缓存。 |
| S35 | PASS_BOUNDED | 离线format inspect和有副作用重执行分开；foreign source先于make_env拒绝。最终记录/重执行的transitions和boundaries独立逐项相等，未支持structured/cross-source仍拒绝。 |
| S36 | PASS_BOUNDED | MuJoCo非Panda及旧Judge篡改测试本次通过；另读回GeoPhys/Isaac同次T=1、T+1=2、clock 0→0.05、两帧RGB和outcome。未宣称图像有独立内容hash。 |
| S37 | PASS_BOUNDED | 最终source31哈希、九条构造对照、受影响原生/RGB/记录逐claim关联；不同输入时点保留，没有拼成完整任务成功。 |
| S38 | PASS_BOUNDED | 原始plans/results/JUnit、精确守卫与独立离线读回已核；本次无新native/SDK/安装资产读取。资产节点被守卫拦下后以精确原证据复用，未谎称整个检查进程通过。 |
| S39 | PASS_BOUNDED | 本报告复算NUL路径统计和分桶增删；迁移单列，Task减行不冒称项目净删码。早期中文路径漏计更正有解释和旧快照保全。 |
| S40 | PASS_BOUNDED | 逐事件、40行主审、当前入口/Goal/编排/Skill同步齐备；维护者接收仍pending。E11～E16、G06/G07和整个优化未提前关闭。 |

## 4. 本次修复、独立检查与复用

生产小修仅在[physical_metadata](../../../../../../task_env/recorders/physical_metadata.py)删除把`state.ee_pose`写为`source-bound PickCube...`的3行；字段语义、单位、frame、time reference继续来自已有ObservationSchema。没有改source、Controller、state/clock、renderer、reader或advance。因此原始受限native/RGB证据可按其原输入保留，不需要为一个metadata字符串重新启动三家引擎。

[定向回归](../../../../../../task_env/diagnostics/tasks/v2.1.1/test_recording_observation_metadata.py)以不同声明语义复现3次失败，修复后3次通过，并检查metadata进入v3 H5投影后仍保持声明。它保护真实的跨owner语义保全，不是仅检查代码里有没有PickCube字符串。本修复由主审者实施，验证属于本次小修自检；原93文件实施的审查仍独立于实施者，不能声称小修又经过另一个独立审者。

- [独立检查进程](../../../../../../workspace/maintenance/v211_e05_e10_independent_review_20261113_001/contracts-offline.json)中 **87项纯/fake/离线检查通过**，包括真实MuJoCo三份短H5、metadata H5、旧R02c/R03c读取与篡改、schema四类篡改、capability/factory、worker失败清理、guard和replay拒绝。没有skip充数。该进程另有2个真实source构造节点被零资产守卫拒绝，整体退出1，不称全进程通过；实际没有读取安装资产或导入SDK。
- 被拦下的2个source节点在前序final3 JUnit均通过；[31项输入SHA对照](../../../../../../workspace/maintenance/v211_e05_e10_independent_review_20261113_001/source-evidence-hash-comparison.json)全部相同，[精准复用收据](../../../../../../workspace/maintenance/v211_e05_e10_independent_review_20261113_001/asset-check-reuse.json)记录节点和依据。本次metadata文件不在这些构造路径内，不为凑新通过数重复构造资产。
- [额外独立读回](../../../../../../workspace/maintenance/v211_e05_e10_independent_review_20261113_001/independent-readback.json)核对GeoPhys/Isaac真实同次physical v3和最终Isaac Position记录，以及PickCube同源码一步重执行。重执行的transition/boundary逐项相同；整文件metadata中的requested默认值展开、materialization/request身份及stop标签有合理差异，不称整文件字节或全metadata相同。初次过宽全映射比较及更正日志保留，未放宽生产replay或改原数据。
- MuJoCo六条四任务/四主体、后续source/Position/effort及same-source路线；GeoPhys正式初始化/非Position/cross；Isaacheadless/双相机/source更新和App close分别有原生结果。原生仍以[U7影响表](../20261113_e05_e10_u7_delivery.md)及具体冻结patch为身份，**本次没有重新运行native或宣称全部最终HEAD重跑**。
- GeoPhys子步未独立计数、Isaac启动隐式步unknown、SDK日志限制、U2单次启动计划不足的旧偏差均保留；最终正确预算下isolated运行有收据。完整任务成功、Solution completion和E13完整记录读回不由这些短测替代。

## 5. 文件、代码与可读性成效

使用`git ls-tree -r -z`按blob统计，排除gitlink/保护untracked/ignored。此前默认转义中文路径导致部分按前缀统计少3项，不能说成文件删除；原始快照保留。当前专用账本的规划量度校正为下表。

| 身份 | 项目tracked blob | task_env tracked blob |
| --- | ---: | ---: |
| 5c输入 `1f1359ee` | 1361 | 980 |
| 规划输入 `67cb643f` | 1366 | 979 |
| 规划交付 `5dd3d29a` | 1368 | 979 |
| 实施自评 `d9dc02c6` | 1393 | 997 |
| 本次生产小修 `7a098423` | 1393 | 997 |

E05～E10自评相对规划交付新增25文件、无整文件删除/重命名；若以更早67cb计则新增27，包含2份规划文档。生产Python **+3247/−2985，净+262**，诊断 **+2371/−121，净+2250**；相对67cb文档 **+815/−61**、Skill **+5/−1**。本次小修另为生产 **+0/−3**、诊断 **+33/−0**，无生产文件增删。主审报告及索引的文档变化另按最终提交统计，不冒称删码收益。

迁移包括约230行provider准入、约260行公共guard、约110行legacy witness及约480行严格Judge；这些是责任迁移，不是项目消失的代码。新adapter/声明/检查有真实职责，文件与总文本上升；主要收益是Task/公共API负担下降、实际数据交接和字段owner更明确，不能用E00～E04累计净删除粉饰本轮净增。

保留的阅读成本包括：`build_panda_reference_stages`参数和三个能力分支较多；Env依旧较大；source binding仍有固定位置tuple和兼容dict。已有具名context、严格键冲突拒绝和各owner的真实消费足以支持当前范围。未来若caller/能力扩展产生具体问题，再按相应事件处理；不为本次接收新增纯审美重构或任意删行指标。

## 6. 接收边界与交接

本轮六事件已具备有界接收条件，实施性余项结束；维护者可基于本报告作最终接收。E00～E04原接收不变。S40的接收状态交付已完成，不代表维护者已经批准；本次只把当前状态从“规划/实施中”改为“独立主审完成、待维护者接收”。

总账TASK-03完整Nut Solution、V08及完整同次V09仍归E13；E11诊断全库、E12全caller、E14整体代码/文档接收、E15输出归并、E16 refs/worktree和G06/G07按原矩阵保留。原COM FAIL、R05c NOT_REQUALIFIED等历史结论不改写。

四个保护输入SHA、两个pins及七阶段/attempt历史保全；不清证据、不操作refs/worktree、不merge/push/tag。文档检查按本次before/final日志对照，既有两项错误和96项历史链接问题不为全绿而修改保护原件或恢复退休代码。
