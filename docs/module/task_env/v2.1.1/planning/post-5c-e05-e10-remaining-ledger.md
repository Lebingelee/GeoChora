# E05～E10 剩余实施账本

更新：2026-11-12。状态：`IMPLEMENTING_U1`。维护者已在本次对话**统一接收 E00～E04**。本账本承接[总台账](post-5c-code-project-optimization-diagnostic-ledger.md)，只细化 E05～E10；[实施 Goal](post-5c-e05-e10-goal.md)引用本页，不复制另一套检查点。实施的实时进度见第 13 节。

## 0. 结论与使用方式

**E05～E10 均已有可复用实现，但尚不能按事件接收。主要欠账在 source／资产配方、provider 准入、状态／相机和 renderer 的职责归位；Task 在接收方生效后减责，Recorder 分开普通格式与历史实验 oracle。无需重做 E00～E04 的共同构建、生命周期和提交链。**

| 事件 | 当前成立的基础 | 还差什么 | 本轮主要单元 |
| --- | --- | --- | --- |
| E05 资产与 source | Robot recipe、Intent／Request／Receipt、具名 source 阶段和 MJCF／USD source 已被正式构造消费；旧 PickCube 专用组合函数名已退休 | compiler 的 Empty／Panda 配方、固定附件实验配方与通用 lowering 分开；Task／Robot／adapter 的数据交接更直接；reference／replace／add 的实际支持边界明确 | U1 |
| E06 physics adapter | 四任务进入共同 Runtime；typed submit、native readback、worker 和 App owner 已存在 | `sessions/api.py` 仍混精确资产准入与通用分派；GeoPhys bootstrap 实际被正式 session 使用，需核对并收敛 provider 边界；worker 的 SDK 启动策略归位 | U2 |
| E07 状态与相机 | 简单任务已有自身观测，binding 已要求显式 space／projection；具名 publication 和 CameraSpec 延迟绑定已有实现 | 公共 reference projection 仍预设 Panda；状态需求／schema／空间的组合分散；Env 枚举 renderer 的 Joint／Frame，旧相机表示的规范化边界需收口 | U3 |
| E08 renderer | 三条首批原生及真实 cross 有有界证据；task RGB consumer、borrowed／independent session 已存在 | UI registry 与 task sampling 能力分散；Env 持有 pairing、RTX／framebuffer／颜色知识；Isaac task／observer 仍耦合 request 与 fault；展示采集和输入接口需整理 | U4 |
| E09 Task 精简 | Position candidate 和两个 PickCube physical UID 已退休；四任务使用共同构建阶段 | PickCube specialization 仍 1,207 行，Nut specialization 567 行；需在接收方生效后去掉 source／native 编排，按内容拆 Nut 通用支持与任务策略 | U1～U4 的迁出，U5 结束 |
| E10 Recorder／replay | 通用 structured reader 已按 T／T+1 校验；源码／XML 已有缓存；same-source reexecution 明确拒绝历史身份替换 | `h5.py` 仍混 R02c／R03c／F06 oracle；metadata／writer 选择与 Env 分支耦合；复核静态 provenance lifetime 与跨源码读取／重执行策略 | U6 |

没有足够依据给出“还剩百分之几”或小时估计。下面是 **7 个大单元、40 个闭合检查点**，其中 **22 项 `改`**为可定位的职责调整，**18 项 `核`**为已有机制的核对及按需补齐；它们不是 40 个新 bug，也不要求 40 轮派包、测试或 native。

- 一次完整推进一个 U 单元，包含实现、直接 caller 迁移、必要修复、定向检查、成效压缩和本地提交。内部 S 格按依赖逐项完成，不逐格返包。
- 单元开始只读本页、其真实源码和必要合同；单元结束再按第 10 节对照总账对应条目。发现不影响当前正确性的范围外问题只记第 11 节，不跳去修另一个小函数。
- 标记最终为 `PASS` 或 `OPEN`，附最终符号／提交／证据。`核` 可原样保留，但须说明 caller、合同与依据。不得以未经维护者同意的 `NOT_APPLICABLE`／延期关闭总账义务。
- 实施者自评、独立主审、维护者接收分列。E00～E04 已接收不等于 E05～E10 自动接收；后续改动若破坏其合同，在当前单元修复回归，不重新审计全部旧事件。

## 1. 规划输入与量度基线

规划核查输入为 `67cb643f24a06dad2056a277110e14ba8d13ff31`，生产代码提交为 `912416e6299558cb2eacb5e94f4e0f8f092dcf16`；分支 `codex/v211-stage5-diagnostic`，tracked clean。四个既有 untracked 输入受保护，包括总台账本身，不纳入本次提交。GeoPhys pin `c1ea3cc9fb99ccbd1d31c36d6fc7b84aa936b3d7`、Menagerie pin `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` 不变。

| 范围 | tracked 文件（排除 gitlink） | Python 文本行 |
| --- | ---: | ---: |
| 全项目／task_env | 1,366／976 | 不用整仓总行数推断本轮效果 |
| assembly | 15 | 4,321 |
| runtime | 52 | 27,166 |
| render | 43 | 7,996 |
| observations | 11 | 2,037 |
| recorders／trajectory | 11／16 | 3,506／3,724 |
| PickCube／Nut 任务目录 | 6／5 | 2,553／2,395 |
| environment | 15 | 12,372 |
| 版本诊断 v2.1.1 | 18 | 4,802 |

目录按现有路径计量，含 `__init__`；Python 行含空行和注释，不能相加当成有效代码行。重要文件为 compiler 518、fixed_attachment 479、Runtime API 1,202、reference_env 4,393、selected_reference 207、Isaac native I/O 3,473、H5 1,823、Nut Solution 1,652 行。**这些是定位阅读负担的输入，不能设任意删行或文件数指标。**

核查先用 CodeGraph；其 drift 文件再读磁盘源码、AST 和实际 caller。未导入生产模块、加载任务资产、运行 pytest／native／GPU／GUI。本页只对所列边界作静态判断，不声称已复现运行故障。[输入快照](../../../../../workspace/maintenance/v211_e05_e10_replan_20261112_001/input-snapshot.json)保存状态、pins、保护文件字节摘要和统计；[静态源码清单](../../../../../workspace/maintenance/v211_e05_e10_replan_20261112_001/static-source-inventory.json)保存符号定位。实施时以实际新 HEAD／dirty 冻结，不把此规划 HEAD 当执行身份。

## 2. 已有成果与真实调用链

| 已有链／机制 | 当前生产 owner 与实际关系 | 后续保全要求 |
| --- | --- | --- |
| 正式构建 | `make_env → from_resolved_config → ReferenceTaskBinding.build_for_request → SourceBoundTaskBuilder → compile_source / source_composer / Controller factory / compile_control → Env` | 继续使用这些阶段及 `CompiledReferenceTaskV1`、具名 context；不新增 UnifiedEnv／BuildManager |
| source 组合 | `declared_robot_source_composer → prepare_robot_source_intent → resolve_robot_source_adapter → compose_robot_source / compose_reference_robot_source`；简单主体使用已有 source 意图与声明 | 不是原总账所述 `_PICKCUBE_SOURCE_ADAPTERS` 状态。改动重点在真实输入、资产限制与最终映射，不再为改名重写一遍 |
| provider 执行 | `build_selected_runtime → sessions.api.materialize → provider session / CoreRuntimeSession → submit / advance / snapshot / close`；GeoPhys `_GeoPhysSession → bootstrap_task_runtime → GeoPhysRuntimeBoundary` | GeoPhys boundary 是正式链的实际组成，不是可直接删除的旧 caller；一个 interval 仍只有一个推进 owner |
| state／RGB | `observation → _capture_task_rgb_boundary → snapshot_v1 → TaskRgbObservationConsumerV1`；GeoPhys／Isaac 借用 session，相应 MuJoCo 独立视觉模型 | renderer publication 已与 Controller publication 分开；保留同一 boundary／clock 和 source linkage，不让视觉模型推进物理 |
| 相机声明 | `CameraSpec → CameraGeometry.from_camera_spec(artifact hash) → consumer / adapter` 已在 Env 构建后延迟绑定 | 普通用户已经可以不提供 hash；E07 结束重复规则和高级旧表示边界，不再造同功能转换层 |
| 记录 | `start_recording → begin_structured_recording / CanonicalRecorder / ExecutionRecorder → save + independent readback`；structured reader 检查 T／T+1 | 已有通用格式不是固定 64 步；真正问题是严格实验 oracle 与通用模块混放、选择及 metadata owner 分散 |
| replay | `reexecute_selected → current make_env → caller Solution → env.step`；旧格式由 `_historical.make_replay_env` 明确处理 | 保留 same-source 限制、结构化格式拒绝及历史身份，不补回退休 Env 维持旧 import |

四个正式任务仍是 PickCube、NutAssembly、Pendulum、双轮车；主体覆盖一体 Panda、装配 Panda 和两个简单主体。`empty-v1`／Empty+Panda 仅作为 compiler 迁移的现有 caller，核对兼容和必要最短构造，**不增为第五个完整任务成功矩阵**。源表示、provider、Position／effort／wrench 的合法差异保留。

### 2.1 迁移接收位置（实施者不再从目录名猜owner）

| 当前责任 | 优先接收位置及交接值 | 处置方式 |
| --- | --- | --- |
| compiler中桌面与Panda补位 | `tasks/worlds/tabletop.py:TabletopSceneBuilder`承担桌面声明；`robots/panda.py`及`robots/source_recipe.py`给Frame/源recipe；`sessions/mujoco_composition.py`消费recipe进行XML lowering | 扩展现有owner；Robot类不解析native XML。Task自己的物体/scene声明不迁出 |
| R06顺序生成/strict oracle | 版本诊断中的source变体构建与Judge；产品历史recipe识别仍由`assembly/panda_fixed_source.py`等版本化资产声明与provider admission消费 | 抽实验动作，保留兼容codec/约束；不让通用fixed lowerer按实验名识别权限 |
| F06/G05精确USD准入、fixed MJCF准入 | provider域的纯admission函数；优先复用`isaac_g05.py`及`panda_fixed_source.py`的已有声明。若需独立模块，允许在现有sessions域增加小型`isaac_admission.py`/`mujoco_admission.py`，由`api.materialize/assess_selected_request`调用 | 这是已识别缺失的纯provider准入责任，不新建Runtime/注册框架；不塞入现有`runtime/admission.py`（它拥有host/device Runtime Port准入） |
| GeoPhys SDK/bootstrap、worker App启动 | `runtime/providers/geophys`/`provider_bootstrap.py`与`_GeoPhysSession`保留实际boundary；Isaac既有native App owner提供启动能力，`worker`只调用该能力 | 复用公共provider边界；不从Task或runner复制启动过程 |
| typed state需求/观测组合 | `sessions/source.py`提供具名binding事实；现有`observations`组合Task/Robot显式projection、`StateRequirements`与`ObservationSchema`；Env持协调/失效状态 | 不另立state缓存owner；publication和generation仍由Runtime持有 |
| task RGB能力、颜色、visual source和factory | `render/base/backend.py`及`render/camera/api.py`关联能力；`camera/{mujoco,geophys}`和Isaac现有native camera owner实现；`task_rgb.py`调用选定adapter结果 | 显示和sampling的能力条目可以不同；不复制一套RenderManager |
| Nut native interval通用支持 | `controllers/canonical/feedback.py`、runtime interval/recorder owner；连续时间窗复用`planners/completion.py`；Nut sample扩展保留task字段 | 若提取会反向依赖Nut则划界未成功；仅Nut使用的策略保持任务内 |
| H5历史codec、实验oracle与metadata | `recorders/h5.py`保留通用I/O/分派；需要独立codec时放同一recorders域，严格实验Judge归版本诊断；metadata继续扩展`reference_provenance/position_metadata/physical_metadata` | 不新造统一Recorder；旧公共reader可薄导出codec，有效严格判据由外部Judge组合 |

接收位置是本次规划决定，拟新增模块尚不存在；不以文件名绑定最终实现。若实际源码证明已有更合适owner，在本单元说明替换理由并消除旧责任，不再开一轮全局架构评估。

## 3. U1：资产、Task intent 与 source lowering 闭合

对应 E05，迁出 E09 的 source 责任。依赖已接收的共同构建阶段。复用 [compiler](../../../../../task_env/assembly/compiler.py)、[source composition 合同](../../../../../task_env/assembly/source_composition.py)、[adapter](../../../../../task_env/runtime/sessions/source_composition_adapters.py)、[MJCF lowerer](../../../../../task_env/runtime/sessions/mujoco_composition.py)、[fixed attachment](../../../../../task_env/assembly/fixed_attachment.py)。

| ID／类型 | 当前定位 | 顺序动作、接收方及结束证据 |
| --- | --- | --- |
| S01 改 | compiler `_source_for_task`、`_empty_tabletop_with_panda_xml`、`_ensure_panda_ee_site`、`_initial_state` 含 Empty／Panda／nutassembly site 知识 | 将场景桌面默认交既有 Scene／world builder，Panda Frame／资产 recipe 交 Robot 声明及对应 source adapter；compiler 只消费明确声明。迁移 Empty caller，保留受控 source 字节／身份或解释其变化；证明另一主体声明无需新增 compiler UID 分支 |
| S02 改 | Task specialization 的场景／USD 构造与组合参数；adapter 已收共同 intent，但 MuJoCo 实现仍直接消费 Panda fixed declaration 和 link0～7 等布局 | Task 给物体、保留／替换根、site 转移、reset 语义；Robot 给结构／Frame／actuation recipe；现有 provider lowerer 消费二者。把 Panda 特定布局作为显式受限 recipe／adapter 能力，通用调度不反推 Task 名。先接真实 PickCube／Nut caller，再删旧编排；不把整个 specialization 搬入 adapter |
| S03 核 | Intent 在解析前冻结；最终 source／position binding 的部分组合依赖已编译 Controller writers | 保全“先声明意图，后以实际 Controller 完成资源绑定”的合法顺序，别强制所有物化早于 Controller。核对 reference／replace／add 三模式和 existing 引用，列已实现、静态拒绝及实际使用格；两简单主体不重复导入，不要求实现任意装配树 |
| S04 改 | fixed_attachment 的 `derive_r06b_order_sources`、反转顺序配方、精确版本表与通用 attachment 校验同文件；api 还识别精确 R03／R06 recipe | 顺序实验生成／oracle 归版本诊断；产品确需的冻结资产变体与 decoder 归现有资产／provider admission owner并说明 caller。通用 lowerer消费显式 attachment／recipe，不根据实验名赋权。保留连接约束、namespace、license、hash、原生名称和历史严格解释；不得让 Core 反向 import diagnostics |
| S05 核 | RuntimeSource／UsdRuntimeSource、UsdSnapshotLease、execution_source_receipt、`.xml` 兼容 provenance | 分清原始字节／closure、canonical Scene、provider representation、visual source 和 snapshot owner；MJCF／USD 各到相应 adapter。逐个限定 `.xml` caller，禁止 USD 被当 MJCF 解析；核对 stale／错来源、半构造清理和共享 lease，原资产不修改 |
| S06 改 | 相近的 source prepare／bind／snapshot／task-root 处理仍在任务和组合 helper 间接力 | 在现有 intent／request／compiled result 中只传必要数据，消掉已被接收方替代的重复 prepare、转换和转发。交付四主体+Nut实际构造对照，标出 source、recipe、Controller writers、最终 native mapping。用受影响真实编译／最短纵切及一个错映射拒绝结束本单元 |

**U1 可见成效：**compiler 中具体任务配方退出；每个配方有实际 receiver；Task/source 重复构造被删除；正式 source identity／自由物体／arm-hand映射和 lease 能逐层对应。允许必要的受限 Panda lowerer，不能仅统一函数名字。输出 before/after caller 表和本单元文件／代码变化，最终 E05 仍待 U7 核对。

## 4. U2：provider 准入、物化与 worker 边界闭合

对应 E06。依赖 U1 最终 source 合同。主 owner：[Runtime API](../../../../../task_env/runtime/sessions/api.py)、现有 `sessions/{mujoco,geophys,isaac_native_io,isaac_g05,native_io,physical_control}.py`、`provider_bootstrap.py`、`sessions/{provenance,transport,worker}.py`。

| ID／类型 | 当前定位 | 顺序动作、接收方及结束证据 |
| --- | --- | --- |
| S07 改 | api `RuntimeSession`、`materialize`、`assess_selected_request` 与 F06 USD policy／manifest、G05 source校验、fixed attachment 精确预检并置 | 按公共协议、provider／representation 正式准入、实验专用注入三类拆责任；扩展已有 admission／provider owner。公共 facade负责选择与共同交接，不持具体 Task policy、Panda sceneID或实验 authority；不能整文件搬到新 admission.py。保留外部实际使用的薄导出，登记去向 |
| S08 核 | `_validate_f06_pickcube_isaac_input`、`_validate_g05_isaac_effort_source`、exact binding、manifest及 source policy | 为每个精确 hash／profile注明资产约束、历史兼容或实验用途；前两类仍严格验证，实验注入由外部 wrapper/scoped injection承担。错 delivery、source、horizon、Controller在 native前拒绝；正常新资产使用真实能力声明，不能冒用 F06 资格，也不能删除所有 hash来“泛化” |
| S09 改 | `_GeoPhysSession`正式调用 bootstrap；bootstrap/provider_bootstrap仍使用 `geophys.demo_runtime/test_runtime`，还服务 component | 核对已存在的 provider公开构建接口和 GeoPhysSourceComposer／Boundary数据流；将 Core bootstrap中的 SDK／solver参数准备收敛至既有 GeoPhys provider owner，保持唯一 boundary。若 provider公开能力缺失，给具体缺口与最小方案，禁止改用 private solver补洞。Empty/component/pure-build/batch/replay按实际 caller保留或明确拒绝；不实施 G06 |
| S10 核 | 三家原生 load／name map／reset／typed write／advance／snapshot／close | 为受影响 adapter给实际调用链和一次 interval所有权；验证单位、方向、传动、requested/applied与measured区别、clock 和实际 advance。已有修复按diff保全，provider轨迹不逐点比较；boot implicit step unknown保持unknown，不篡改计数 |
| S11 改 | worker按 provider提前 open Isaac App，transport/provenance负责解释器／源身份，Task外 runner曾复制准备 | 把 SDK／App launch细节收敛到既有 provider启动能力；worker继续负责进程、请求和清理，transport不变成Task builder。Task不启动App；runner只预算、锁、监控取证。保全父子环境／source重建校验、owned进程timeout及cleanup确认后的exit；不重造worker |
| S12 核 | 共同 factory／进程协议／关闭已受测 | 按影响复验精确预检无副作用、半物化释放、RemoteSession失败与重复close；每家实际正式caller映射旧证据或最短补测。输出协议／准入／执行／进程四列owner表，限制不因拆文件扩大。源码拆分影响identity时记录新源清单，不替换历史SHA |

**U2 可见成效：**新增资产／provider能力不再修改Task和公共API的实验分支；公共API可读到协议与共同分派；provider只管native映射，worker只管进程合同。原生实现可以不同；不把 GeoPhys boundary 的存在本身当作多 Runtime。

## 5. U3：状态需求、观测投影与相机声明闭合

对应 E07／ENV-04／REN-03。依赖 U1／U2 的 source/state 合同；renderer实现留 U4。复用 `StateRequirements`、`snapshot_v1/v2`、`TaskDefinition`、`ReferenceTaskBinding`已有显式 projection／space、`ObservationSchema`与canonical camera，**不新建第二套观测框架**。

| ID／类型 | 当前定位 | 顺序动作、接收方及结束证据 |
| --- | --- | --- |
| S13 改 | `observations/selected_reference.py`在公共文件内构造9关节／ee／hand和PickCube switch别名；PickCube／Nut显式使用它，简单任务已有自己的投影 | Robot拥有主体字段／布局投影，Task拥有物体／特权状态和兼容schema选择；公共observation owner组合这些显式声明。保留现有binding要求，不能把简单主体说成当前已伪造Panda；迁移公共文件的任务知识，兼容alias不静默改义 |
| S14 改 | observation_space、实际projection、`selected_reference_observation_schema`和metadata分处不同函数 | 用已有字段声明生成／核对空间、schema与实际数组，固定路径／shape／dtype／unit／frame；Env只引用结果。Task success／failure、Solution completion、runtime validity各由原owner表达。用四任务实际输出和Nut正式info消费检查，不靠手补metadata过门 |
| S15 改 | Env `_prepare_task_rgb_state_binding`自行枚举Joint／Frame、组renderer requirements；`_publish_task_rgb_typed_state`另取snapshot | 状态owner按source提供具名状态能力，Controller／Task／renderer各声明需求；renderer准备自己的visual projection。Env仅协调发布／采集，保留独立typed view和同boundary／clock关系，不覆盖控制publication；抽取真实责任而非搬同样的if到helper |
| S16 核 | CameraSpec→CameraGeometry.from_camera_spec已支持无hash声明，另有legacy camera／CameraObservationConfig／canonical contracts | 列普通声明→一次规范化→绑定Artifact/source/episode→adapter读回的路径；高级绑定对象保留严格身份／stale检查。尽量复用既有lower_legacy_camera和geometry，消除重复内参／外参算法；统一声明不意味着删掉所有历史表示或重写五section配置 |
| S17 核 | 当前world挂载、RGB HWC float32、task/observer distinct identities及不支持depth/mount的拒绝 | 在所属声明／adapter边界保留限制；核对空间、实际像素数组与geometry／capture binding一致，错source、旧episode、错shape不进入有效输出。不得自动加入手部动态挂载、深度或任意sensor支持 |
| S18 改 | schema构造和Panda兼容metadata仍有散落caller | 迁移本单元触及的Controller／Task／renderer／Recorder消费者，删除重复schema拼接。交付四任务+支持RGB的非Position代表路线的字段来源表；用独立状态读回及控制publication／物理时钟前后对照结束，真实图像若由U4最终运行覆盖则不重复跑 |

**U3 可见成效：**公共观测组合不预设Panda，兼容Panda投影明确选择；同一声明决定space／schema／数组；普通相机继续无需内部hash；renderer状态需求不由Env按控制类型拼造。不同typed view允许存在，不强制所有消费者一份大状态。

## 6. U4：renderer能力、采集、显示与资源闭合

对应 E08。依赖 U3 的状态／相机结果。复用 `render/base/backend.py` registry、`RenderBuildRequest/RenderProcessor`、`camera/api.py`、`TaskRgbObservationConsumerV1`及现有camera/provider实现。**显示backend（raytracer/rasterizer/flora）与native renderer不是同一层枚举，不把名字强行压成一张支持矩阵。**

| ID／类型 | 当前定位 | 顺序动作、接收方及结束证据 |
| --- | --- | --- |
| S19 改 | backend registrations、camera manifest/profile、`TASK_RGB_PAIRINGS`与Env检查分散 | 在现有render capability/registry owner关联显示、离屏、task sampling、source/state格式、physics配对、设备和输出能力及真实factory。接口可以不同，能力事实只有一个owner；query不得加载SDK。注册存在与实测支持分列，别把hidden mujoco_reference descriptor当RGB已接通 |
| S20 改 | Env `_configure_task_rgb/_configure_selected_observer/_capture_task_rgb_boundary`仍设置RTX、GeoPhys同extent规则、backend名和color字符串；task_rgb helper再按名字拼profile | 相应adapter返回状态需求、visual source准备、session/consumer factory、输出规格和owned/borrowed说明；公共Env消费结果，只编排生命周期与observation。由真实工厂消费注册结果，同包删除重复pairing／设置／描述，不只把分支移到新helper |
| S21 改 | Isaac `capture_task_camera`仍要求 `_observer_render_request`、复用 `_observer_faulted`，失败同时关闭task与observer；独立task prim/sensor已存在 | 保留成功的RTX采样工具、App lease和有界warmup，分清task sampling需求与可见observer需求。按资源表决定单相机fault和共享App级fault传播；可共用工具，不能因headless task采集伪造observer身份。reset/新状态/再reset/close及零额外物理以真实受影响运行证明；不是重开已接收5c |
| S22 核 | MuJoCo独立visual model、GeoPhys borrowed camera、光学／灯光设置已有修复 | 保全独立visual模型只同步公开state、不step；核对受影响FOV/near/far实际读回和authored/default lighting限制。USD由其adapter接收，不被MJCF限制拦截。旧灯位有界误差继续保留，不研发新光照系统 |
| S23 改 | `render/providers/single.py`直接调用visualizer `_initial_camera_pose/_refresh_render_snapshot/_render_frame_to_buffer`；task/observer/window各有处理 | 在现有backend/provider接口明确pose更新、状态消费、capture和presentation，消除跨owner私有方法依赖及重复姿态处理；允许自有实现内部私有方法。observer A→B不动task camera，关窗按原合同继续采集或typed fault，不关闭physics/App；不新增所有任务human窗口 |
| S24 改 | `render/tools/camera.py`通用相机数学顶层import Taichi并读ti.ui输入常量，声明却称backend-neutral | 将具体窗口输入翻译留UI adapter，复用同一相机数学／pose sink；普通pose/config使用不加载无关SDK。可按实际caller采用最小依赖拆分，不建事件总线或为每家复制数学。adapter输出layout/dtype/range/transfer/device/copy/lifetime，删除Env重复颜色推断 |
| S25 核 | consumer已有owned帧、foreign/stale拒绝和close；原生/cross旧证据已成立 | 用U7影响表覆盖borrowed native与independent cross、非Position、reset首帧/step/再reset、重复render物理增量0、返回帧保留性、task/observer独立及受影响close。逐条标重测或旧证据复用；Isaac改了capture/request/fault就不能只拿旧冻结结果当最终代码实测 |

**U4 可见成效：**Env不再了解RTX／引擎颜色／配对表；增adapter主要改其owner；source/state/camera/resource由adapter真实对齐Runtime；显示和task sampling可分别查询。输出规格与设置相符，原色／素材未校准限制保留；固定renderer不变，不增动态切换或像素评分门。

## 7. U5：Task目录及Nut公共支持收口

对应 E09。依赖 U1～U4 的接收方已工作；不能提前整体搬走Task文件。主定位为 PickCube／Nut specialization、Nut solution、简单任务physical binding及 `controllers/canonical/feedback.py`、`planners/completion.py`。

| ID／类型 | 当前定位 | 顺序动作、接收方及结束证据 |
| --- | --- | --- |
| S26 核 | 两个candidate文件和旧UID已退休；当前PickCube目录6文件、Nut5文件，含配置／资产 | 对照迁出清单确认旧实现确实退出，无新别名／重导入／第二生命周期。保留仍被正式任务使用的质量资产配置和任务语义；不是继续删candidate，也不以“四文件”数量裁剪有效Solution或资产 |
| S27 改 | PickCube specialization仍持MJCF/USD/native source接线；Nut build_runtime_source同时处理provider选项和snapshot | 将U1～U4已接收能力接回薄Task binding，删除旧builder、重复编排及多余转发；Task留下声明、默认选择、对象映射、reset/reward/evaluation/Solution。给逐段去向和真实caller，不允许新建一个千行“通用specialization”藏原逻辑 |
| S28 改 | Nut `_native_feedback_sample/_native_interval_receipt`、sample/receipt类、GuardedTransitionEvaluator混有通用身份／时间窗／stream校验和Nut抓取语义 | 先按内容划界：通用native反馈／interval身份和时钟复用现有feedback/runtime/recorder；guard通用连续窗口复用completion。仅在公共合同责任或真实复用成立时抽取，单个任务的策略可原样保留并说明。Nut阶段／grasped_nut／阈值／2ms×5正式要求仍由Nut配置和Solution约束；不放宽原严格guard，也不制造无caller的通用库 |
| S29 核 | 两简单Task已有共同source/subject/Controller链，Nut外部Solution消费正式info已修复 | 核对本轮没有把source物化、native force写入、App启动或observer配置拉回任务。Guard有效性、raw predicate、task success与Solution completion分列；短程sample／receipt证明合同，完整Nut成功仍归E13，不为目录精简新增完整运行门 |
| S30 核 | 代码迁移会改变source inventory、历史imports、诊断fixture | 迁移直接caller与有价值行为检查到版本诊断，删除只服务退休路径的fixture要求；必要薄兼容仅forward/decoder，不带owner。交付四任务构造和目录职责对照、Task与全项目净变化、每段迁移量；E11/E12全库治理不在本单元 |

**U5 可见成效：**打开Task能读出“任务是什么、默认怎么选、如何评价”，无需穿过SDK/renderer接线；公共反馈使用者无需import Nut；确属Nut的策略仍完整可读。可读性以责任、调用层数、重复构造和关键函数结构说明，不能只报行数。

## 8. U6：普通记录、历史解码与replay闭合

对应 E10。消费稳定后的source/state/action/output合同，可先处理与上游无关的离线reader，但不同时启动另一个writer。主owner为 [H5](../../../../../task_env/recorders/h5.py)、`recorder.py`、`reference_provenance.py`、`position_metadata.py/physical_metadata.py`、`trajectory/canonical/*`、[reference replay](../../../../../task_env/trajectory/reference_replay.py)和 `_historical.py`。

| ID／类型 | 当前定位 | 顺序动作、接收方及结束证据 |
| --- | --- | --- |
| S31 核 | Env按Position/physical reset selection/canonical mode选已有Recorder；多种H5 outer schema与typed payload并存 | 先列“实际writer→schema→reader→生产caller→身份/clock来源”。普通structured reader已有T/T+1，不宣称所有记录被64/65限制；不同真实数据格式可保留版本codec。明确同次状态/动作/图像/结果由谁写，读回不重模拟 |
| S32 改 | h5 `_validate_f06_typed_state_witness/_f05_typed_state_extension/load_leaf_control_records_h5/_load_attached_leaf_control_records_h5`含9关节、64/65、固定writer/timebase/native版本和任务运动判据 | 通用H5保留schema/完整性/计数/source/clock/typed records验证；旧格式解码归显式兼容reader/codec，精确物理实验oracle归版本诊断Judge。保留现有公开旧reader必要薄导出或明确迁移入口；不得通过放宽固定oracle让旧实验伪PASS。Core不import diagnostics，严格旧validator由外部Judge组合codec |
| S33 改 | Env recording metadata分支与position/physical/reference模块重复组source/owner/output描述 | 由既有Recorder metadata owner消费构建结果、控制合同、U3 schema和U4 output规格；Env只传当前边界和提交事实。合并确有重复的字段转换，保留各schema需要的历史字段和action语义。正常任意短horizon、不同主体/writer不必伪装R03c/F06 |
| S34 核 | `selected_source_provenance`在start_recording准备；`_owners`不再读文件，XML已有cache；construction也会取source摘要 | 先计数当前真实路径的read/hash调用及lifetime再决定是否改。source/recipe/代码不变的摘要在正确owner准备一次；source/reset/Controller generation变化要失效或重建；boundary/command/state动态identity继续生成。无重复热点即保全，不声称已测性能提升、不加跨路径盲缓存 |
| S35 改 | reexecute_selected只限两任务、旧canonical-v0/execution-stream格式并严格比source；structured-v1/v3明确拒绝；_historical处理旧UID | 将只读inspect/历史codec与会make_env的重执行入口清楚分层，迁移本轮变动的factory/import/source inventory caller。same-source比较不替换旧SHA；跨源码或不支持格式给明确边界，不自动实现D0或所有新格式重执行。普通新构建不依赖旧replay资格 |
| S36 改 | 当前reader验证、例子、Nut receipt与camera记录分散 | 用正式入口短记录→正常save→独立reader检验T/T+1、实际命令/typed状态/clock/图像/终止；取一个不等于64的短horizon及非Panda声明，避免只对固定Panda样本自测。另保全一份实际仍需支持的旧格式读取与篡改拒绝；有资产的旧H5只读即可，不为读取启动SDK。补适量版本诊断并删除被替代的重复检查 |

**U6 可见成效：**正常记录的验证由数据schema决定，旧实验有明确入口和严格判据；Env不拼多套provenance；读旧文件不启动物理，新运行不借旧资格；缓存成效用实际调用计数说明，完整Solution记录读回仍在E13完成。

## 9. U7：定向复验、成效归并及逐事件结束

对应 E05～E10 的交付结束，不是提前做E13～E16。前六单元各自检查可复用，不要求最后重跑一遍全部测试。

| ID／类型 | 动作及退出条件 |
| --- | --- |
| S37 核 | 对最终diff形成claim→实际owner/source/config→旧证据输入→为何可复用/补哪条的影响表；对四任务、四主体、三原生与一cross分别说明，不自动跑笛卡尔积。影响公共source/state/submit/renderer的格子不能只因“共同类没变”继承旧证据 |
| S38 核 | 将第12节映射到真实精确node／正式命令及资源上界，执行尚未覆盖的最短纵切、必要RGB/optics及短记录读回。纯／fake、离线资产构造、native／图像、完整Solution分别报告；未测的不改名PASS；普通故障在本单元修复复验 |
| S39 核 | 汇总每单元及累计diff/commit、文件新增/删除/迁移、生产+/−/净量、迁移量、诊断/测试/文档分桶；四任务构造图、owner表、adapter source/state/clock/submit/resources和限制。压缩当前记录，只保留按模块最终效果，失败原件留ignored证据 |
| S40 核 | 按第10节回对总账，分别给E05/E06/E07/E08/E09/E10的实施结论、独立主审及维护者待接收项。直接同步API/Skill/当前状态与导航；不得顺便标整个60项、V08/V09全程、E11～E16、G06/G07完成或清理旧输出/refs |

### 9.1 每个单元固定的成效记录

| 观察项 | 必须交付 |
| --- | --- |
| 文件 | 本单元输入/输出在相同tracked-blob口径下的本范围与项目文件数；新增/删除/迁移路径；迁移的原/目标对应；生成物不混入生产统计 |
| 代码 | 生产Python+/−/净量；移动代码单列，不把原样迁移计作删除成果；测试/诊断/文档及其他文件分桶。本轮相对67cb643f和累计相对1f1359ee分开，历史已实现成果不冒领 |
| 构建/职责 | 删除哪些重复构造、转换、注册、旁路；四正式caller实际进入哪个合同；每段移出代码由哪个owner消费。列保留的合法能力分派及必要兼容 |
| 可读性 | 关键函数/模块前后职责、调用层数与重复片段；任务/资产知识是否退出公共层。必要新代码解释目的；不追求统一文件行数 |
| adapter | 分别说明physics/renderer如何消费source、状态、clock、提交和资源；borrowed/owned、implicit unknown和未受影响范围明确 |
| 功能 | 精确命令/输入身份/原始结果/失败和修复；旧证据复用依据；runtime validity、task success、completion、close分列，不能用短程推断完整Solution |

## 10. 单元依赖与总账覆盖

```text
E00～E04（已维护者接收）
 → U1 source／recipe → U2 provider／worker → U3 state／camera
 → U4 renderer → U5 Task收尾 → U6 Recorder／replay → U7定向复验／接收对账
```

source迁出Task在U1实施，renderer迁出Env在U4实施；U5清除已被替代的残余接线。U6离线codec可在相应输入已明确时处理，但保持单writer。既有代码可直接按正确owner保全，不为维持顺序搬两次。

| 大单元 | 完成后只核对这些总账项 | 不能提前关闭的范围 |
| --- | --- | --- |
| U1 | SRC-01～04、SUBJ-02、TASK-01/02/04的source部分 | 任意Robot/source/provider组合；E06/E08完整退出 |
| U2 | RUN-01～04，SRC-04的provider准入接口 | G06真实batch、所有旧component caller全面迁移、全部SDK异常清零 |
| U3 | ENV-04、OBS-01/02、ENTRY-03、REN-03 | 不支持sensor/mount、完整renderer注册与原生采集 |
| U4 | REN-01/02/04～08，REN-03最终采集对应、ENV-05受影响资源 | 动态renderer切换、任意像素/灯光支持、所有任务human矩阵 |
| U5 | TASK-01～04，GOV-01/02本轮职责部分 | E11全诊断库、E12全部CLI/vector/learner/LIBERO、E13完整Solution |
| U6 | REC-01～03、ENV-04的record metadata接口 | 新D0/跨源码精确重执行、E13完整任务同次记录V09 |
| U7 | 上列条目逐项结果；V01～V07及V09/V10实际触及部分 | E14全部代码/文档接收、E15证据整理、E16 refs/worktree项目接收 |

总账TASK-03含完整Nut Solution要求，该部分明确交给原事件E13，不以S29短测代替其最终PASS。ENV-04等跨事件条目只有全部关联责任和证据到齐才最终结束。维护者已接收的E00～E04保持原边界；本页不通过重复计账撤销或扩大它们。

## 11. 范围外与待决事项

| 范围 | 本轮处理 |
| --- | --- |
| E11/E12 | 迁移本轮直接破坏的caller/行为测试；不展开全部历史布局、benchmark或learner治理 |
| E13 | 两正式Solution各自公开支持provider单seed完整运行、至少MuJoCo任务成功及同次H5读回保留原门；本轮短纵切不能替代 |
| E14～E16／G06／G07 | 只同步直接变化的文档/Skill；不清证据、旧refs/worktree或缓存，不merge/push/tag/发布；后续阶段不自动开始 |
| GeoPhys公开构建接口 | S09需在实施时核对实际provider公开能力；当前只确认demo/test bootstrap使用，不预设缺陷或擅自改子模块pin |
| Isaac采样／资源迁移 | 现有成功证据保留；若S21改了运行链，需要明确预算下的受影响真实采集，不得以冻结旧运行替代新行为 |
| U2 isolated Isaac 启动预算偏差 | 第二次 reset 重建 worker，实际顺序启动两次 App，超过该次计划的单次启动上限；两次未并发。保留[计划与原始日志](../../../../../workspace/maintenance/v211_e05_e10_u2_20261112_001/isaac-isolated-worker-retry2/)，今后按 reset 重建次数冻结 App 启动上限；该事实不改写既有 5c 结论。 |

本表仅登记新增的范围外问题、owner和为何不阻塞本单元；本单元合同被破坏时回到对应S格修复，不能随意延期或增加全矩阵。

## 12. 验证入口与复用规则

以下为**已有入口与计划选择**，本次未运行。诊断目录下测试可能加载资产／SDK，不能仅凭名字叫contract判定纯度；实施窗口先检查fixture/参数化，冻结精确node，避免整个旧模块执行。保留有意义行为；只服务过时私有布局的旧测试不强制兼容。

| 验证组 | 已有精确入口／正式路径 | 证明和边界 |
| --- | --- | --- |
| A source/config | `v2.1.1/test_formal_configuration.py::test_make_env_resolves_public_config_once`；`test_tabletop_robot_source.py::test_source_composition_failure_releases_source_before_controller`、`::test_assembled_composition_uses_the_robot_selected_by_the_common_entry`、`::test_tabletop_source_uses_selected_robot_actuation_declaration` | 配置/实际Robot/source交接与失败释放；部分参数需要真实资产，冻结时分类，不称全部纯 |
| B admission/worker | `test_isaac_effort_admission.py::test_f06_delivery_admission_rejects_foreign_identity`、`::test_isaac_position_input_dispatch_requires_exact_formal_type_and_schema`；`test_worker_resources.py::test_worker_initial_build_failure_releases_binding_and_keeps_primary_error`、`::test_worker_close_response_includes_source_and_task_cleanup` | exact admission、无native拒绝和fake资源合同；不代表实际SDK关闭 |
| C camera/state | `test_task_rgb.py::test_camera_spec_lowering_preserves_pose_and_artifact_link`、`::test_task_rgb_produces_owned_contiguous_reset_and_step_frames`、`::test_task_rgb_rejects_foreign_or_stale_capture`、`::test_environment_closes_rgb_and_visual_resources_once` | 声明、ownership、stale、fake关闭；真实采图仍需D组 |
| D production短纵切 | `formal_cpu_probe.py --case panda-r3 / assembled-live / nut / pendulum / two-wheel`及受影响`panda-effort`；`--task-rgb --camera-spec`走无需预构建hash的正式声明；MuJoCo/GeoPhys以实际case/provider选择；Isaac复用既有原生worker/runner并冻结最短命令 | 正式make_env→reset→非零interval→状态/clock→二次reset→重复close；RGB覆盖变化边界，重复render不额外推进。每条参数/plan/预算执行前固定，不启动此表所有组合 |
| E provenance/replay | 旧`test_selected_consumers.py::test_callable_source_snapshot_rechecks_bytes_without_path_cache`、`::test_nutassembly_feedback_xml_cache_tracks_source_changes`、`::test_reexecution_rejects_changed_binding_source`；将仍有效行为移入v2.1.1对应检查 | 身份/lifetime/篡改拒绝；fake重执行不算native或D0。测试数不作为新增门 |
| F H5/Nut | 旧`test_phase_ii_01_r03c_attached_leaf.py::test_attached_generic_h5_closes_and_independently_reads_back_without_native`；guard相关有效检查；U6正式短记录+独立reader；旧冻结H5只读 | 区分通用T/T+1、历史strict oracle、guard语义；旧fixture若依赖退休入口，改针对当前合同，不补回产品分支。完整Nut Solution仍在E13 |

E00～E04最终生产912416e6、217受影响source/caller检查、76纯/fake检查及115显式MuJoCo子步的身份见[修复返包](../maintenance/20261112_e00_e04_review_fix_delivery_912416e6.md)，数字有重叠，不相加。Isaac/RGB沿原冻结输入与影响复用；若改变其真实owner/输入，补受影响最短路线。不同run可证明不同独立claim，不能拼成一次不存在的完整任务成功。

本次规划文档检查与保护核对存于上述replan目录；只报告静态文档结论，不新增能力声明。实施后的当前效果填下一节，原过程日志保留ignored，不把本页扩成逐次命令日记。

## 13. 当前实施结果（唯一更新区）

| 单元 | 状态 | 最终效果／提交／证据／未完成项 |
| --- | --- | --- |
| U1／S01～S06 | IMPLEMENTED | 输入 `5dd3d29a`，提交 `1a2bc947`；[实施结果、四任务调用、模式边界和证据](../maintenance/20261112_e05_e10_u1_source_delivery.md)。Scene、Robot 和 MJCF adapter 分别接收桌面、主体声明及物化；USD 路径按声明绑定；source snapshot 的创建与失败释放归编译 owner；两实体 attachment 与受限 Panda 资产 profile 分开，严格准入保留。三原生代表路线及 GeoPhys × MuJoCo RGB 按实际影响复验，具体范围见记录；本结果为实施者自评，E05 与整个优化尚未接收。 |
| U2／S07～S12 | PARTIAL | 输入 `1a2bc947`，提交 `73eebf37`；[实施结果、实际调用、证据和限制](../maintenance/20261112_e05_e10_u2_provider_delivery.md)。精确 USD／Panda 准入归相应 provider owner，GeoPhys solver 配置归 provider bootstrap，isolated Isaac App 由 worker/provider 管理；最终隔离短程、GeoPhys 和 MuJoCo 代表路线及定向故障检查已覆盖受影响边界。GeoPhys 初始化 facade 的 provider 缺口、旧 SDK 日志及第 11 节所记启动预算偏差保留；本结果为实施者自评，E06 和整个优化尚未接收。 |
| U3／S13～S18 | IMPLEMENTED | 输入 `73eebf37`，提交 `ff5309d0`；[实施结果、字段来源、证据与限制](../maintenance/20261112_e05_e10_u3_observation_delivery.md)。Robot 与 Task 拥有各自投影，renderer 在 adapter 声明状态需求；四任务 schema、非 Position RGB 和跨 provider reset 已定向复验。光学 readback、重复 render、Isaac 采集与 Recorder metadata 分别留 U4/U6/U7；结果为实施者自评，E07/E08 尚未接收。 |
| U4／S19～S25 | IMPLEMENTED | 输入 `ff5309d0`，提交 `1ce601fa`；[实施结果、真实采集与窗口证据](../maintenance/20261112_e05_e10_u4_renderer_delivery.md)。renderer capability 与 factory 对齐，Isaac task/observer 请求和故障分离，展示与相机输入走公开合同；三家原生及 cross 路线分别按影响复验。U3 简单任务附加 RGB schema 遗漏已修复，设备限制及先前失败保留；结果为实施者自评，E08 尚未接收。 |
| U5／S26～S30 | PARTIAL | 输入 `1ce601fa`，提交 `5cb0d470`；[实施结果、调用链与真实证据](../maintenance/20261113_e05_e10_u5_task_delivery.md)。PickCube 一次选择 source strategy，Task 场景声明与 F06 provider 资产分离；Nut 通用 guard/interval 归 completion/feedback，严格任务条件保留并修复 Solution 临时 source 泄漏。共同构造来源清单、USD 身份投影、F06 source inventory 与 MJCF backend 处理已进一步归位；USD readiness 不再额外物化临时 MJCF source，F06 原生路径、Nut MJCF 物化与 PickCube MJCF 场景映射分别归 Isaac admission 和 assembly，见[后续结果和证据](../maintenance/20261113_e05_e10_u7_delivery.md#s27去除-usd-readiness-的重复-mjcf-source2026-11-13)。specialization 仍承担分 provider 编译协调和部分配置映射，S27 未闭合，E09 尚未接收；本结果为实施者自评。 |
| U6／S31～S36 | IMPLEMENTED | 输入 `5cb0d470`，提交 `f83c0601`；[实施结果与证据](../maintenance/20261113_e05_e10_u6_recording_delivery.md)。旧 Judge 与 codec 分层、只读 inspect；Pendulum 和双轮车进入 v3 物理记录，Pendulum 同次状态／动作／clock／RGB／outcome 已独立读回。图片字节没有独立摘要；GeoPhys／Isaac 受影响路线与最终对账留 U7。本结果为实施者自评。 |
| U7／S37～S40 | PARTIAL | 已完成影响对账与定向复验，[六事件结果、证据与限制](../maintenance/20261113_e05_e10_u7_delivery.md)。GeoPhys 正式 backend 初始化 facade 不在当前固定子模块中，S09 与 E06 保留开放，S27 与 E09 仍有明确实现欠账；其余结果为实施者自评，独立主审与维护者接收待完成。 |

每行最终结果可链接一份按模块压缩的实现摘要及机器可复核证据；S格的最终owner/判断可放同一摘要的40行表，不另建40份报告。没有对应最终调用与证据的格子仍为OPEN。
