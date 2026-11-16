# G06 开发实施总结与 canonical 有界结案

日期：2026-11-16。状态：**CLOSED_BOUNDED_CANONICAL_G06**。维护者在6c独立主审后要求收尾；本次依已审范围结案，不代替v2.1.1版本接收或发布。G06a两次、6b三次、6c一次普通执行窗口已经结束；原补证/接续不另算attempt，不再准备6c attempt002。R3／模型／重力补偿是独立后续包，G07保留原最终集成门。

后继维护说明：本总结记录canonical结案时点。维护者随后在G07前要求补齐scalar/batch render断线，当前行为、后继代码与真实检查见[渲染收尾记录](../20261116_scalar_render_followup.md)。不回写为原六格已覆盖全部scalar默认组合；下表旧结案SHA仍是历史输入。

## 1. 源码、当前入口和结案依据

| 项目 | 精确身份 |
| --- | --- |
| G06规划/实施前Core | `41a09c87a7599f13adce9fb50501eb6378c2a17e`；首包前文档`fb8a8c17`的GeoPhys pin相同 |
| 6a接收 | Core `3bc9e2a70daea2dda1004352c54ba1d1ada46b54`／GeoPhys `a2c85b7fb87e821b1e3b211c97ed2b695db8b3c1` |
| 6b接收 | Core `8d0fd75615c707d1f461c0c0fae5e86ebd3da700`／GeoPhys `198d30ac64ce873a1467f55d2adfc471db18fbc5` |
| 6c执行与主审小修 | 执行`a824b7df3ddbcafc9f886a4f476959cdbe6b60a7`；清理重试修复`a4d9eb26de0a32b1cb515433f42a4304272d939c` |
| 当前生产代码结案 | `4332844f0ede0c8f56f75a27c773bd2cf7bd67f5`，删除冗余状态；其后结案提交仅文档/索引 |
| 阶段分支 | `codex/v211-stage6-parallel`；统一入口`make_parallel_env(..., execution='device', backend='cuda')` |
| 当前submodules | GeoPhys `198d30ac64ce873a1467f55d2adfc471db18fbc5`；Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` |

独立接收依据：[6a主审](../reviews/20261115_g06a_attempt002_acceptance.md)、[6b主审](../reviews/20261116_g06b_attempt003_acceptance.md)、[6c主审](../reviews/20261116_g06c_attempt001_acceptance.md)。结构要求以原[优化账本](../../planning/post-5c-code-project-optimization-diagnostic-ledger.md)为准，分解要求见[stage6-work-packages](../../planning/stage6-work-packages.md)。当前调用合同只在[API](../../api/README.md)维护；本总结记录已实现成果、受测范围与来源，不另定义接口。

受测依赖组合是主环境MuJoCo3.8.1/Torch2.14.0+cu130、隔离MuJoCo/MJWarp4.0.1+Warp1.18.0、Isaac6.2配套环境、Forge/Forge runtime0.7.0。MJWarp精确worker依赖文件及profile说明见[dependencies](../../../../../../task_env/dependencies/README.md)。不是将三个SDK强装进同一个解释器，也没有安装Isaac Lab、ManiSkill、mjlab整套运行依赖。

## 2. 基本要求对账及abc成果

| 子阶段/要求 | 已实现与接线 | 验收出口 |
| --- | --- | --- |
| 6a 入口与共享构建 | device入口与旧host/SB3入口明确区分；仍共享Task注册、配置、binding、source/Scene/Robot/Controller构建；按provider解释器物化 | 普通caller真实进入native batch，未增加一套并行Task注册/生命周期 |
| 6a 设备合同 | Dict动作叶子带B轴、obs树前置B；reward/done设备tensor；逐行episode/RNG、共享native clock的真实语义；same-step保留旧终止state/RGB与新首帧 | B3非零控制、mask/reset、owned/borrowed身份和受影响兼容性 |
| 6a renderer/记录前置 | 公开设备pose→固定Rasterizer；CUDA uint8多相机；显式device Recorder复用原H5 writer | MJWarp真实batch和Isaac scalar第二来源前置验证；后者当时不冒认Isaac batch |
| 6b canonical六格 | Isaac/MJWarp/GeoPhys × Pendulum/PickCube全部native CUDA batch；batch Robot提供具名关节/frame；Task tensor与标量公式共享语义 | 异行动作、真实Panda/双指/自由cube/table、行隔离、局部reset、相机/记录/close |
| 6b设备/接触补齐 | GeoPhys沿用Rigid batch，补公开state/effort/reset和有限mesh/condim4等缺口；预算显式透传；MJWarp PickCube传动/接触，Isaac真实多世界与过滤 | GeoPhys限discrete/contact32/coupled32已验证配置，未靠默认大穿透样本通过 |
| 6b性能 | PickCube传感器×窗口四项、Pendulum窗口两项，共18项B16；纯状态按条件推进256/4096 | 18项齐全（11项最终新测、7项历史复用），未使用批准的三项Isaac B16资源例外 |
| 6c部分reset | 三后端两任务全false/单行/非相邻两行mask；post-step/pre-reset比较；未选状态、响应、RNG和Task计数保持 | 六格通过；不把共享buffer失效误认为未选行物理改变 |
| 6c错开终止 | 错开horizon、same-step、owned终止图像继续步进后保持；reward/done属于旧episode | 三后端真实H5逐边界读回 |
| 6c整批切换 | 同一Env、固定Rasterizer配置，两任务各Isaac→MJWarp→Isaac；旧scene资源释放，新scene重建 | B/action/obs合同固定，materialization/generation区分A1/B/A2；旧view/command/selection/render绑定拒绝 |
| 6c故障关闭 | 预验证拒绝保留旧Env；破坏阶段失败faulted；worker/IPC/GPU按owner释放；失败close可重试 | 真实目标已建立后注入首次reset失败，独立检查退出/句柄/引用；主审补构造+清理复合故障重试 |

上述基本要求没有尚待实施或未闭合的必需证据。6a前置、6b六格、6c跨generation集成是递进成果，不能互相外推，也不是一次在最终HEAD重跑了所有历史样本。

### 六格最终支持表

| 任务 | MJWarp CUDA | Isaac PhysX CUDA | GeoPhys CUDA |
| --- | --- | --- | --- |
| Pendulum | native batch、canonical torque、state/Task、部分reset、窗口、记录 | 同左 | 同左；不需要传感器相机 |
| PickCube | native batch、source-bound effort、手指传动/接触、双相机/窗口独立、记录 | 同左；真实collision filtering负对照 | 同左的有界交集；必须显式discrete/32配置 |
| 固定renderer整批切换 | 两任务Isaac↔MJWarp | 两任务Isaac↔MJWarp | 跨provider未准入，不由部分reset成功外推 |

## 3. 测试与独立读回

计数按套件/时点列示，存在重叠，**不能加总成一个测试通过总数**。当前closeout没有重新运行仿真、GPU、窗口或18项性能。

| 阶段/时点 | 保存的验证 | 结果/解释 |
| --- | --- | --- |
| 6a主审 | device semantics29；transport/recording/render-fault合计29；六份离线读回 | 58项定向检查通过、六份读回通过；真实native沿用执行证据 |
| 6b最终 | budget/lifecycle/Task/preflight/DLPack；framebuffer与监督pose-copy | 67项定向检查通过；设备专项分别有监督结果，不编造合计 |
| 6b B1核对 | GeoPhys B1/B3指定状态/obs/Task/clock/reset35组字段；同状态scalar/tensor Task | 对应字段差0；reward误差5.09e-8；另有同源Pendulum无接触scalar/B1误差3.58e-7rad、1.91e-6rad/s |
| 6b几何/物理 | GeoPhys32配置三组冻结轨迹、独立几何、真实双指冲量 | 最大桌面重叠1.715mm；双指正冲量/接触102子步。2mm仅该冻结回归，不是跨引擎统一精度门 |
| 6c最终回归 | 最后定向87；较广105/8skip；scalar定向2 | 分别保留，不相加；跳过不记为通过 |
| 6c C2 | 三后端21份H5、81个边界、162帧；各69项staggered检查 | 公共state/action/reward/done/context与保存记录逐值一致 |
| 6c C3 | 两任务18份H5，三代三行；PickCube72帧 | A1/B/A2 provider、materialization/generation及obs/action/reward/done一致 |
| 6c主审修复 | reconfiguration文件23项纯测试，含三项清理重试新例 | 通过；没有新增native |
| 本次代码精简 | 同一reconfiguration文件，隐藏CUDA、关闭bytecode/cache及自动pytest插件 | 23 passed in1.97s；只CPU纯/fake检查 |
| Submodule专项 | mesh CUDA4项、预算requested/resolved37/37、FREE armature CPU10/1skip及CUDA Graph3、framebuffer2 | 各自原记录通过；Graph与armature不外推连续模式/通用mixed求解 |

### B16性能矩阵

单位为整批control steps/s，包含公共step及实际present开销；transitions/s为该配置下B×控制频率。无传感器/无窗口的历史测量与当前补测分列；GPU列是整卡峰值MiB，旧样本缺该读回时明确留空，不补造。模式off为无传感器无窗口，sensor为仅传感器，window为仅窗口，sensor-window为双开。传感器为base/hand各128×128，窗口640×480。相机逐行渲染和copy开销包括在实际结果中，低于10Hz的渲染结果不判失败。

| 任务/后端 | 模式 | control Hz | transitions/s | 进程树RSS GiB | 整卡GPU MiB | 来源 | 原始结果 |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| MJWarp Pendulum | off | 11.908 | 190.5 | 1.52 | 未独立记录 | 历史复用 | [证据](../../../../../../workspace/maintenance/v211_g06b_attempt001/mjwarp-pendulum-b16-off-002) |
| MJWarp Pendulum | window | 12.209 | 195.3 | 2.24 | 1753 | 本轮实测 | [证据](../../../../../../workspace/maintenance/v211_g06b_attempt003/performance-pendulum-window-001) |
| GeoPhys Pendulum | off | 121.225 | 1939.6 | 2.31 | 未独立记录 | 历史复用 | [证据](../../../../../../workspace/maintenance/v211_g06b_attempt001/geophys-pendulum-b16-off-001) |
| GeoPhys Pendulum | window | 91.598 | 1465.6 | 3.01 | 1793 | 本轮实测 | [证据](../../../../../../workspace/maintenance/v211_g06b_attempt003/performance-geophys-window-001) |
| Isaac Pendulum | off | 14.505 | 232.1 | 6.81 | 未独立记录 | 历史复用 | [证据](../../../../../../workspace/maintenance/v211_g06b_attempt001/isaac-pendulum-b16-off-001) |
| Isaac Pendulum | window | 18.330 | 293.3 | 6.79 | 2653 | 本轮实测 | [证据](../../../../../../workspace/maintenance/v211_g06b_attempt003/performance-isaac-window-retry-001) |
| MJWarp PickCube | off | 26.185 | 419.0 | 1.97 | 1579 | 历史复用 | [证据](../../../../../../workspace/maintenance/v211_g06b_attempt001/mjwarp-pickcube-b16-off-final-001) |
| MJWarp PickCube | sensor | 8.541 | 136.7 | 2.54 | 2192 | 本轮实测 | [证据](../../../../../../workspace/maintenance/v211_g06b_attempt003/performance-pickcube-mujoco_warp-sensor-001) |
| MJWarp PickCube | window | 24.955 | 399.3 | 2.88 | 2453 | 本轮实测 | [证据](../../../../../../workspace/maintenance/v211_g06b_attempt003/performance-pickcube-mujoco_warp-window-001) |
| MJWarp PickCube | sensor+window | 8.382 | 134.1 | 2.84 | 2643 | 历史复用 | [证据](../../../../../../workspace/maintenance/v211_g06b_attempt002/performance-mjwarp-sensor-window-scoped-b16-001) |
| GeoPhys PickCube | off | 10.893 | 174.3 | 2.86 | 1768 | 历史复用 | [证据](../../../../../../workspace/maintenance/v211_g06b_attempt002/performance-geophys-off-32-001) |
| GeoPhys PickCube | sensor | 5.763 | 92.2 | 3.27 | 2387 | 本轮实测 | [证据](../../../../../../workspace/maintenance/v211_g06b_attempt003/performance-pickcube-geophys-sensor-001) |
| GeoPhys PickCube | window | 10.429 | 166.9 | 3.55 | 2599 | 本轮实测 | [证据](../../../../../../workspace/maintenance/v211_g06b_attempt003/performance-pickcube-geophys-window-001) |
| GeoPhys PickCube | sensor+window | 5.551 | 88.8 | 3.62 | 2605 | 本轮实测 | [证据](../../../../../../workspace/maintenance/v211_g06b_attempt003/performance-pickcube-geophys-sensor-window-001) |
| Isaac PickCube | off | 18.259 | 292.1 | 7.47 | 2983 | 历史复用 | [证据](../../../../../../workspace/maintenance/v211_g06b_attempt001/isaac-pickcube-b16-off-003) |
| Isaac PickCube | sensor | 7.828 | 125.3 | 7.98 | 3457 | 本轮实测 | [证据](../../../../../../workspace/maintenance/v211_g06b_attempt003/performance-pickcube-isaacsim-sensor-retry-001) |
| Isaac PickCube | window | 22.193 | 355.1 | 8.43 | 3756 | 本轮实测 | [证据](../../../../../../workspace/maintenance/v211_g06b_attempt003/performance-pickcube-isaacsim-window-retry-001) |
| Isaac PickCube | sensor+window | 7.160 | 114.6 | 7.90 | 3744 | 本轮实测 | [证据](../../../../../../workspace/maintenance/v211_g06b_attempt003/performance-pickcube-isaacsim-sensor-window-retry-001) |

### 纯状态规模

| 任务/后端 | B16 Hz | B256 Hz | B4096 Hz/状态 |
| --- | ---: | ---: | --- |
| MJWarp Pendulum | 11.908 | 11.530 | 11.397 |
| GeoPhys Pendulum | 121.225 | 119.116 | 115.542 |
| Isaac Pendulum | 14.505 | 7.798 | CONDITION_NOT_MET |
| MJWarp PickCube | 26.185 | 21.399 | 7.028 |
| GeoPhys PickCube | 10.893 | 6.696 | CONDITION_NOT_MET |
| Isaac PickCube | 18.259 | RESOURCE_LIMIT | CONDITION_NOT_MET |

只有当前档纯状态>10Hz、行为正确且资源允许才继续扩大。Isaac Pendulum与GeoPhys PickCube在256档停止；MJWarp PickCube4096已测但约7.028Hz，不伪称达到10Hz。Isaac PickCube256当时为主机内存准入估计RESOURCE_LIMIT，未实际分配；本次不把后续B16渲染能运行推成B256也能运行。GeoPhys4096约37.6GiB只是逻辑载荷估算，不是一次运行结果。详尽数值、测量长度、显存口径和停止原因在[evidence-index.json](evidence-index.json)及原performance-index中。

## 4. 结构账本复核与处理

本次按`41a09c87..9c13febe`实际Core增量、调用者和后续小修复核；不是复审整个仓库所有历史路径。未发现G06新增公共Task/Panda特判、复制Task生命周期、生产import diagnostics或逐step SHA。

| 原账本条目 | 当前职责/本次处理 | 判定 |
| --- | --- | --- |
| ENTRY/TASK/SRC/RUN | 公共入口共享binding和factory；Task只声明语义，provider只做source/SDK/行映射；三session继承同一DevicePhysicalBatchSession | 保留，不建立第二套Env/Runtime/注册 |
| ENV-05 | 6c主审发现构造失败后清理失败的owner丢失，已于a4d9eb26保留失败close并允许重试 | 已解决，纯测试验证 |
| GOV-01/ENV/REC | 本次4332844f删除从未读取的render_signature及签名helper、PreparedReconfiguration冗余provider/execution、adapter.device_generation重复动态字段；实际renderer校验仍由固定合同比较负责 | 净减30行，23项纯测试通过 |
| CTRL/OBS/REC | source-bound动作映射、Task公式、相机schema、VectorTransitionRecorder/H5 writer各有明确owner；device不每步重算hash | 保留真实单位/shape/身份/故障检查 |
| TEST-03 | 无成果interleave候选、Core mixed研究入口、scalar隐式trace已退出；有效接触trace/reader仅在diagnostics/development，产品不依赖 | 已清理且保全有效证据producer |
| TEST-03/04 | 约3500行runner是历史诊断/监督兼容入口；各分支仍有有效运行或核心诊断消费者，实际生产路径不导入它 | 不以行数制造新重构门；保留，后续新增诊断遵循独立功能owner |
| RUN/REN | 两种IPC publisher对应Warp/Torch的实际设备/stream owner，共用consumer；provider能力guard针对真实物理交集 | 不为删差异强行合并，不把准入视为无用防御 |
| GOV-04/DOC-01/02 | 修复README/恢复/路线/依赖/API/能力/Skill当前态；旧审批稿转历史定位，撤回邻居不可见和R3误作canonical门的残留措辞 | 本次完成 |
| PROJ/TEST-04 | 原运行不改不删；原位461份主要证据已核验并作最终副本，hash/输入/来源统一索引 | 可恢复、可对账；不冒称完整可移植native环境 |

此前旧scalar每步SHA回执迁移仍是独立公共语义工作，不能因G06 device没有热路径SHA就写成旧scalar已修复。大规模Env/Robot精简未纳本包；本次只处理确认无消费者的状态，不换名搬运整套旧实现。

## 5. Submodule变更及来源

GeoPhys由`c1ea3cc9fb99ccbd1d31c36d6fc7b84aa936b3d7`推进到`198d30ac64ce873a1467f55d2adfc471db18fbc5`；Menagerie整个G06保持`b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`，资产未修改。完整14次Core gitlink变化、24个本地GeoPhys提交见JSON索引。

必须区分：旧pin已经有homogeneous刚体batch、primitive/mixed contact、joint/tendon、部分reset和selected-world渲染；G06复用这些基础。`e38c6bad8fbf66c3d5322851c0ea2981e55d6a25`把当时上游main `2110d359a90f3fbcea89d35d7756a523ebd91cde`合入阶段分支，导入1129个对旧pin不可达提交，净差1939文件/+379721/-41995；这不算G06新写的batch算法。其后24个阶段提交净差56文件/+3499/-137。

| 模块 | 本阶段能力/修复及范围 | GeoPhys关键提交 |
| --- | --- | --- |
| G06前已有基础 | homogeneous free/articulated rigid batch；Row/EFC有限路线；sphere/box/mixed contact；joint/tendon；host/K-shaped部分reset；selected-world raster。G06复用并接到TaskEnv，不应表述为新造native batch。 | 原有/未变 |
| 上游同步 | 将2110d359合入旧pin c1ea3cc9；1129个上游提交，1939文件+379721/-41995。与24个G06本地提交分计。 | `e38c6bad` |
| 设备渲染接口 | 具名多task-camera、CUDA pose、caller-owned RGB8、observer设备frame/present、公开RenderScene source；compute finite clipping准入；active framebuffer height；DLPack scoped lifetime。JIT CUDA有界，AOT未通过。 | `05f2e2d3`、`a2c85b7f`、`9ef7768b`、`f47c0cd4` |
| Rigid batch设备端口 | owned CUDA world-major qpos/qvel/body pose；CUDA applied generalized effort；masked CUDA reset；direct step clock；FREE passive damping；native actuator disable isolation。沿用BatchedRigidSolver owner。 | `ef5c8de8`、`570f4b2f`、`fe8ebb90`、`9793a8b5`、`d267fad6`、`42c30c6b` |
| contact planning与有限几何 | 仅排除已证明fixed-root pair；保留全部源contact candidates；condim4扭转row；bounded full convex hull geometry/owned scratch/fault latch。mesh CCD/boundary/sphere/softEFC/Graph不在资格范围。 | `ed3bb32b`、`7a10d5e8`、`3e5991ca`、`81d87f8b` |
| 预算与诊断 | 实际contact/coupled预算public readback及development trace/independent witnesses；Core ae96d52e透传既有runtime预算。最终198d仅删development interleave实验switch21行，未改src，默认预算异常不记修复。 | `ce594de8`、`335da22f`、`cbd9ca86`、`9548b12b`、`6606865c`、`64c506fc`、`a436f2a9`、`198d30ac` |
| Forge Graph兼容 | 当builder缺private_scalar时用template-specialized sort pass；保留已有API路径。 | `d5b33f0e` |
| FREE armature修复 | 显式discrete/CCD-off纯FREE joint armature保留generalized质量响应，并用完整质量响应对角项。限已测CPU direct/CUDA Graph；default/continuous、未准入TGS、mixed任务并非全面修复。 | `dd393187` |
| Menagerie | b846dd12始终未变；detached HEAD且干净。 | 原有/未变 |

“把上游main合入阶段分支”已完成；“把阶段分支成果反向合并到上游main”仍按维护者决定暂缓。这两个方向不能混写成从未合并。AOT缺少taichi.aot.Component、既有治理/package admission问题也保留暂缓，不记PASS。

本地ref/reflog显示Core develop及public/develop已到`120281a1ed787bcb351840bf9f5f6622ec89152c`，曾有fast-forward和update-by-push；所以不能写整个G06从未push。该点之后的6c/主审/本次代码精简仍为本地后继提交，本次不push或合并develop/main。Core main/public/main仍`fd03817c`；GeoPhys本地阶段分支最终pin未被当前已知remote ref包含，上游origin/main仍`2110d359`。这些是本地refs观察，未重新fetch远端。合并前备份stash`51bc6d46a16f6148dda04a22b8526fb951a1d3d2`保留不动。

## 6. 尚未完成的可选、暂缓与不支持项

| 项目 | 分类与后续条件 |
| --- | --- |
| batch R3/模型/本体重力补偿 | 独立后续包；provider名单尚未指定，不阻断canonical结案 |
| 更大范围Env/Robot代码精简 | 后续按明确owner另立范围；本次已解决确认的无用状态和清理问题 |
| GeoPhys continuous mesh+约束、默认预算异常、通用稳定抓取 | 未支持/未解决；不能从discrete/32短程成功外推，不承诺各引擎接触轨迹/力值相同 |
| GeoPhys跨provider、任意后端两两切换 | 未准入；本包代表边Isaac↔MJWarp已满足原要求 |
| 逐slot换后端、异构任意资产、每行不同维度、多GPU、全部autoreset模式 | 原范围外；不得因schema存在声明已支持 |
| 相机跨行视觉隔离 | 当前共享平铺scene可能看到其他行；物理/身份隔离通过，需视觉隔离时另做公开visibility/FOV/布局方案 |
| MJWarp renderer备选、RayTracer/Flora共同device相机 | 未作为本包路线构建/验收；Rasterizer已满足所选目标，不要求额外补三套renderer |
| 独立static provider、软体batch | 本次canonical未准入；刚体场景中的静态桌面/地面几何已在真实任务覆盖 |
| Isaac PickCube B256/4096等未测规模 | RESOURCE_LIMIT/条件未满足；按表保留未运行状态，不为收尾重跑 |
| 窗口视觉外观 | 保留维护者人工验收角色；技术窗口/相机/时钟检查已通过，本轮不新增外观开发 |
| 旧scalar SHA、AOT、上游反向合并/治理 | 独立迁移或明确暂缓；既不冒记通过，也不扩大为G06必需返工 |
| G07三provider×三seed与版本发布 | 仍未完成；G06短程canonical并行不替代完整Solution/最终集成 |

以上未覆盖项均有明确状态；不是将必需失败改成可选。原G06确定的六格、设备/生命周期、所选renderer、代表切换边和条件规模测试已完成。

## 7. 证据保全与过程记录

[evidence-index.json](evidence-index.json)登记原始run roots、461份主要文件的大小/SHA-256、冻结提交、性能与submodule来源。最终检索包位于`workspace/maintenance/v211_stage_closeout/stage06/`，其中`evidence/`按原仓库相对路径保存经过hash核验的副本，主要文件共10,043,543字节。原目录保留，未删除旧attempt/cache，也未把缓存及全部SDK/生成delivery冒充可移植安装包；需要native复跑时仍须恢复冻结代码/profile及原必要source。后续若清理原目录，须按索引迁移被引用输入与reader，不能只保留报告删掉H5/NPZ。

部分历史样本只保存执行窗口的输入/输出提交范围，未独立记录每次run的精确pin；索引保留原说明和按影响复用依据，不把结案code_head当成所有样本的执行HEAD。

本次唯一执行检查是上述23项CPU纯测试和文档/JSON/链接/身份校验；没有新native、GPU、窗口或性能测量。原6b首次未监督CUDA及后续监督复验、6c未找到事前调用链落盘记录/API补写较晚均保留；不补造时间戳、执行历史或跨版本复跑身份。6c63次监督累计114.99/120分钟无限额违例不改变。

受保护untracked `MUJOCO_LOG.TXT` SHA仍为`3b08b858f62dcbaa6521802455c76126f9876a3d6727c7586db90c94296ed6a8`。文档校验已知保护基准差异不能改成PASS，本轮不改保护日志或基准来消除提示。精简代码已本地提交；结案文档后继提交仅更新入口/状态/证据索引。没有push、merge、tag、删除分支或改submodule pin。
