# E11–E16 U4：60 项逐行对账（实施中）

本表是实施者初步整理，不是独立主审或维护者接收。60 个原编号各有 owner、变化或保留理由、caller、证据与当前结论；E00–E10 的既有有界接收按原时点复用，仍须由本轮独立主审核对。项目和分支条目必须等 U5–U7，保持 OPEN；不因填表视为完成。

证据简称：[E00–E04 主审](20261112_e00_e04_independent_review_76536d2a.md)、[E05–E10 主审](20261113_e05_e10_independent_review_d9dc02c6.md)、[E05–E10 实施与原始入口](../20261113_e05_e10_u7_delivery.md)、[U2 caller](20261113_e11_e16_u2_caller_review.md)、[U3 完整运行](20261113_e11_e16_u3_solution_evidence.md)、[诊断 claim 表](../../../../../../task_env/diagnostics/tasks/v2.1.1/README.md)。

| ID／原关注点 | 当前 owner | 变化／保留理由 | 真实 caller | 证据 | 结论 |
| --- | --- | --- | --- | --- | --- |
| GOV-01 简化任务构建早有明确要求，却未持续约束后续新增能力 | Registry／configuration／builder | 四正式任务共用正式请求，限定于已接受主体 | `make_env` → `from_resolved_config` → `SourceBoundTaskBuilder` | E00–E04 R01–R08；U1 config nodes | 实施自评；待本轮主审 |
| GOV-02 有界路线接收被不当地理解成整体架构接收 | 版本范围／各实际 owner | 分开历史有界接收、后续优化与最终资格 | `maintenance/current-state.md` → 矩阵／各 review | E00–E10 接收；本轮矩阵 | 实施自评；待主审 |
| GOV-03 清理时间在 5c 后与 G07 之间摇摆，欠账不断延期 | 编排／项目整理 | 代码接收后才归并证据及授权清理 | `current-state.md` → 本账本 U4–U7 | 目标依赖和 E00–E10 接收 | 项目部分 OPEN |
| GOV-04 “当前状态”分散且相互冲突，后续执行会选错基线 | 版本摘要／编排 | 唯一恢复入口更新，旧规划保留历史时点 | 版本 README → current-state → API／矩阵／账本 | 本轮文档 validator；矩阵复算 | 实施中，待主审 |
| ENTRY-01 make_env 按类标志选择多种构造协议 | `task_env.registry`／configuration | 正式类使用共同解析，component 路径按原范围保留 | `examples/tasks/pick_cube.py`、`examples/recording/record_expert.py` → `make_env` | E00–E04 R01；U2 caller；U3 五条 | 实施自评；待主审 |
| ENTRY-02 配置的同一概念在 selected 与 component 里有不同形状 | `environment.configuration` | 正式配置由公共 resolver 解析，不把旧 component codec 伪称相同 | `script/env/_common.py` 的 mapping/YAML → `make_env` | E00–E04 R01；U2 YAML 等价检查 | 实施自评；待主审 |
| ENTRY-03 任务 RGB 配置要求调用方先取得内部 Artifact 身份 | registry／camera capability | 支持的任务 RGB 在正式配置声明；renderer 固定至 close | `make_env` → task RGB 配置／camera owner | E00–E10 RGB 证据及 U2 caller | 有界自评；待主审 |
| TASK-01 PickCube 候选文件同时承担任务、控制、后端和渲染装配 | PickCube Task／source adapter／Controller | 旧 candidate UID 退休；任务声明与 source、Controller owner 分开 | 正式 `pick-cube-p16-reference-v1` → builder | E00–E10 主审；U3 PickCube | 实施自评；待主审 |
| TASK-02 PickCube specialization 已成为超出“薄绑定”的第二中心 | PickCube specialization／共同 builder | 保留 readiness 和任务接线，source／controller 创建由对应 owner 消费 | `PickCubeReferenceEnv` → `SourceBoundTaskBuilder` | E00–E04 R03/R04；E05–E10 S27 | 有界自评；Task 并非完全薄化 |
| TASK-03 NutAssembly 内混有通用 native stream／guard 支持 | Nut Solution／公共 feedback | 通用 interval／feedback 归公共 owner，原 guard／Outcome 保留 | `examples/tasks/nut_assembly.py` → caller Solution | E05–E10 S26；U3 Nut 两条 | 实施自评；待主审 |
| TASK-04 Pendulum／双轮车“引用既有主体”与旧 component scene 双入口 | Pendulum／双轮 Robot 与 task | 自身主体声明进入共同 builder；不强造 Panda 字段 | 四正式 UID 的 `make_env`；简单主体短程 | E00–E04 R06/R26；U7 原结果 | 有界自评；batch 留 G06 |
| ENV-01 一个类名下仍有多种构建契约和大量专用状态 | Env／共同 builder | 正式任务共同构建，component 合同按范围保留；大类未声称彻底拆解 | `make_env` → `SourceBoundTaskBuilder` → `SelectedReferenceEnv` | E00–E04 R02/R08；E05–E10 构建链 | 有界自评；待主审 |
| ENV-02 reset／materialization 的 capability owner 与旧 profile 变量并存 | reset lifecycle／materialization | reset 预检、source 和 Runtime owner 保留；不把 profile 名当生命周期 owner | `SelectedReferenceEnv.reset` → reset reconstruction → session | E00–E04 R09–R12；U1 `test_reset_reconstruction.py` | 有界自评；待主审 |
| ENV-03 普通 action、Solution、ExpertAction、序列必须消费共同控制生命周期 | control lifecycle／submission | 普通、兼容 Solution 和已支持 typed 输入汇入共同控制生命周期 | `step`／兼容入口 → `prepare_selected_control_action` → `submit_control_command` | E00–E04 R15–R21；U3 完整 caller | 有界自评；保留各输入准入 |
| ENV-04 Env 内 observation／metadata 仍知道 Panda 和诊断路线 | observation／Robot／Task metadata | Robot 声明主体投影，Task 提供对象事实；特殊兼容字段保留来源 | `observation_projection` → `selected_reference` → declared Robot/Task | E05–E10 S13–S18；U1 observation tests | 有界自评；待主审 |
| ENV-05 资源关闭和故障状态分散，需要按所有权收口 | `EpisodeExecutionState`／session／source | 统一故障与关闭协调，保留首错和资源 owner；重复 close 有界验证 | `SelectedReferenceEnv.close` → session/runtime/source close | E00–E04 R09/R13/R14；E05–E10 S11/S12 | 真实失败注入和 SDK 日志限制保留 |
| SUBJ-01 公共 Robot runtime 外观仍带 Panda 必需字段 | `RobotRuntime` | `gripper`、`ee` 等为可选字段；实际主体和 Controller 可独立提供 | `RobotRuntime.from_selected` → `env.robot` | E00–E04 R06–R08；E05–E10 S13 | 有界自评；非任意 Robot 资格 |
| SUBJ-02 Robot 专用声明合理，但其调用不能把 source materialization 拉回 Robot | Robot 声明／source composer | Robot 给 source intent；provider composer 持有最终映射及 writer | `build_for_request` → `_compose_robot_source` → provider composer | E00–E04 R02/R07；E05–E10 S02/S03 | 有界自评；待主审 |
| SUBJ-03 单层、嵌套及根约束需要统一表达，不按动作类型代替主体类别 | logical assembly／physical subject | 根、嵌套关系和控制资源以声明表达；动作类型不替代主体类型 | `project_logical_assembly_source`、`ControlledSubjectV1` | E00–E04 R07/R26；E05–E10 S03 | 有界自评；不扩大任意拓扑 |
| CTRL-01 Controller 匹配同时涉及语义通道、Scene 资源和 native 映射 | controller binding／provider admission | 语义通道、场景资源和 native 映射分层验证 | `ControllerSelectionMatchV1` → selected materialization → session | E00–E04 R07/R18；E05–E10 S06/S08 | 有界自评；待主审 |
| CTRL-02 统一提交要统一 owner，不能抹去 Position／effort／wrench 的物理区别 | control submission／provider physical port | 共同提交 owner；Position、effort、wrench 的单位和作用方式各自保留 | `prepare_selected_control_action` → `submit_control_command` | E00–E04 R18–R20；E05–E10 S10 | 有界自评；ACK 非测力 |
| CTRL-03 默认恒等 Controller 的能力不能由 facade 名称推断 | `DefaultCanonicalController`／physical controller | 按 binding 和资源声明选择 identity 或 effort，不由 facade 名推断 | `DefaultCanonicalController.bind`／`DirectJointEffortControllerV1` | E00–E04 R15/R18；U1 control lifecycle | 有界自评；未穷举组合 |
| CTRL-04 重力补偿与模型能力要保持解耦，不能再绑定 Task／provider 名称 | dynamic model／controller／provider capability | 默认关闭重力补偿，模型和 provider 能力分离；原严格失败保留 | `dynamic_mass_effort`／`mass_matrix_effort` → MuJoCo model capability | E00–E04 R20；G03 3b 有界接收 | 有界自评；不扩展 provider |
| CTRL-05 外部 interval、Controller tick 与 physics substep 必须区分 | timebase／interval submission／native session | 区分控制 interval、Controller tick、physics substeps；保留 cadence 和时间检查 | `submit_control_command` → session interval → native advances | E00–E04 R20；U3 5 substeps 和 clock 读回 | 有界自评；未知隐式步仍 unknown |
| SRC-01 公共 Assembly compiler 中仍有具体 Task 与 Panda source 处理 | assembly compiler／Task／Robot | compiler 消费声明，Task 物体与 Robot recipe 不再按 Task 名分派 | `TaskBuildRequest` → `SourceBoundTaskBuilder` → source composer | E05–E10 S01/S02/S06 | 有界自评；待主审 |
| SRC-02 provider source composition 仍以 PickCube 专用协议命名和组织 | provider source composition adapters | source intent 与 provider 最终 source/writer binding 分层；保留 MJCF/USD 差异 | `prepare_robot_source_intent` → provider composer | E05–E10 S02/S03/S27 | 有界自评；不声称任意 source |
| SRC-03 固定附件生产模块内包含 R06b 顺序实验配方 | fixed attachment／version diagnostics | 历史 R06 变体生成移到诊断；产品保留识别和合法 profile 校验 | `panda_source_profiles` → fixed attachment；R06 诊断 | E05–E10 S04；U1 claim 表 | 有界自评；历史 oracle 保留 |
| SRC-04 RuntimeSource／UsdRuntimeSource 是表示差异，不是多 Runtime 的借口 | MJCF/USD source／snapshot lease | 不同表示沿各自 closure 和 lease 进入同一 Runtime 协议 | `compile_usd_task_runtime_input`／MJCF source → provider admission | E05–E10 S05/S08；U3 plans | 有界自评；U5 source 闭包 OPEN |
| RUN-01 公共 Runtime API 内集中了大量历史精确准入与诊断 context | Runtime API／provider admission | 共同 API 保留协议分派，精确 USD／fixed 约束归 provider | `assess_selected_request`／`materialize` → provider admission | E05–E10 S07/S08 | 有界自评；准入未弱化 |
| RUN-02 旧 GeoPhys bootstrap／RuntimeBoundary 有活动调用者，迁移必须有范围 | `bootstrap_task_runtime`／GeoPhys provider | 复用固定 pin 的公开初始化；重复初始化沿首次生效语义 | `_GeoPhysSession` → provider bootstrap → public assembly | E05–E10 S09；U1 bootstrap fake | 有界自评；component caller 保留 |
| RUN-03 provider adapter 应承担 SDK 映射，不承担另一套 Task／Controller | MuJoCo／GeoPhys／Isaac session adapters | adapter 持有 native 映射、write、advance、snapshot 和 close，不另造 Task/Controller | 共同 RuntimeSession → 三 provider adapter | E05–E10 S10；U3 同次状态／clock | 有界自评；GeoPhys 隐式步限制保留 |
| RUN-04 进程与资源控制应统一使用既有 worker，不由 Task／诊断复制 | transport／worker／Isaac App owner | 进程、session、source 和 App 分别清理，失败保留首错 | `start_selected_worker` → `serve_session` → owner close | E05–E10 S11/S12；U3 Isaac 记录 | 有界自评；SDK 完整日志未证明 |
| REN-01 普通 render registry 与 task RGB registry 不是同一张能力图 | render capability／factory | UI registry 和 task RGB capability 保持不同用途，后者被实际 factory 消费 | `create_task_rgb_consumer` → admitted renderer factory | E05–E10 S19/S20；U1 renderer tests | 有界自评；非任意配对 |
| REN-02 把 renderer 分支挪到 helper 尚不足以完成可组合适配 | renderer capability／adapter | Env 编排，设备、颜色和 source 适配在 renderer owner | `create_task_rgb_consumer` → renderer adapter | E05–E10 S19/S20；U3 V04/V05 | 有界自评；renderer 固定至 close |
| REN-03 公共状态不应为 RGB 再变成 Position 专属状态路线 | typed state publication／renderer binding | Controller 与 renderer 的视图分开，消费同一 boundary/clock | `_publish_task_rgb_typed_state` → renderer state binding | E05–E10 S15/S25；U1 task RGB source routing | 有界自评；不另推进 physics |
| REN-04 Isaac task sensor 与 observer 共用实现，但不得共用错误身份／生命周期 | Isaac task sensor／observer | 独立请求和局部 fault；解绑及 App 所有权分开 | `bind_task_camera`／`_capture_observer_admitted` | E05–E10 S21；U7 双相机记录 | 有界自评；SDK 退出日志限制 |
| REN-05 MuJoCo renderer-only 与 GeoPhys camera 的 source／光学／灯光边界 | MuJoCo visual-only／GeoPhys camera | 独立 visual source 同步状态；GeoPhys 参数设置后读回 | `MuJoCoDynamicCameraSession`／GeoPhys camera binding | E05–E10 S22/S25；U7 cross RGB | 有界自评；光照限制保留 |
| REN-06 窗口、离屏 RGB、任务图像必须独立，但不必复制三套相机逻辑 | UI provider／camera adapter | 窗口、离屏、任务采图按各自消费及生命周期区分 | `render.providers.single`／task RGB consumer | E05–E10 S23/S25；U7 原始窗口 | 有界自评；不扩展 OS 事件矩阵 |
| REN-07 颜色、设备、ownership 描述不能散落成未经验证的默认事实 | renderer capability／color policy | 设备、颜色与 owner 由对应 adapter 声明；未知或未校准不虚构 | `render.camera.color`／renderer factory | E05–E10 S17/S20；U1 renderer capabilities | 有界自评；颜色未校准 |
| REN-08 通用相机交互数学直接依赖 Taichi 输入常量 | camera 数学／UI adapter | 相机数学不强制顶层 Taichi；UI 输入常量由 UI 层提供 | `render.tools.camera` → `InteractiveCameraController` | E05–E10 S24；U1 import/fake tests | 有界自评；待主审 |
| OBS-01 名为 selected-reference 的公共投影仍以 Panda／PickCube 为默认 | Robot／Task observation projection | Robot 提供主体字段，Task 提供物体字段；不将 Panda 强加简单主体 | `selected_reference` → declared Robot/Task observation | E05–E10 S13/S14；四任务受测 schema | 有界自评；待主审 |
| OBS-02 多种相机配置／schema 需要一处规范化，不凭空宣布全部统一 | CameraSpec／canonical geometry／capture | 复用延迟绑定及 schema 校验；未宣称所有 camera 格式统一 | `CameraSpec` → task RGB capability → capture | E05–E10 S16–S18；U1 metadata tests | 有界自评；sensor/mount 不扩展 |
| REC-01 通用 H5 模块混入精确诊断实验的物理拓扑和样本数 | 通用 H5／legacy codec／版本 Judge | 通用 v3、历史 leaf codec 与严格实验 Judge 分层；历史判据保留 | `load_structured_control_records_h5`／`load_legacy_leaf_control_h5` | E05–E10 S31/S32；U1 offline H5 | 有界自评；U3 T19 completion OPEN |
| REC-02 静态 provenance 复用已有改进，避免每步文件 I/O 回流 | reference provenance／source snapshot | 复用静态 source/provenance 缓存，避免把逐步文件 I/O 重新引入 | `begin_selected_recording` → `selected_source_provenance` | E05–E10 S34；原 Nut 5 次 source 读 | 有界自评；不声称跨 reset 缓存 |
| REC-03 回放／重新执行与正常新运行的身份策略必须区别 | replay inspect／selected re-execution | 离线 inspect 不建 Env；重执行先核 source identity，拒绝不支持 schema | `inspect_selected_replay`／`reexecute_selected` | E05–E10 S35；同源码一步结果 | 有界自评；非 D0、非跨源码重放 |
| CALL-01 CLI／教程／示例仍可能把复杂候选入口教给用户 | CLI／examples／completion projection | 正式配置及 caller-owned Solution；显式 backend 失败不转换为另一交集 | `examples/tasks/pick_cube.py`／`script/env/_common.py` → `make_env` | U2 T08–T10；U3 五条运行 | 实施自评；独立主审待完成 |
| CALL-02 vector／learner／LIBERO 等不能被标量整理顺手破坏 | vectorization／learner adapters | 四正式 UID 提前拒绝未支持 batch；component 保留，space 与 autoreset 按 fake 合同检查 | `make_framework_parallel_spec`／SB3 adapter／learner data | U2 T11/T12；`test_batch_boundaries.py`／`test_learner_boundaries.py` | 实施自评；不声称 native batch 或训练 |
| CALL-03 objects／planners／reporter／utils 按职责保留，不为凑“全面重构”制造抽象 | objects／planners／reporter／utils | 保留有真实 caller 的各自职责；未发现需抽象化的本轮缺陷 | `make_object`、`CanonicalSolutionLifecycle`、`ReporterSession`、`tree_copy` | U2 T14；lifecycle/reporter/vector fake checks | 实施自评；待主审 |
| CALL-04 LIBERO benchmark 的来源语义不能被主任务整理误覆盖 | LIBERO source／OSC／trajectory | 保持原任务和 20 Hz／2 ms ×25 cadence；只核受影响 Core 交接 | `bench_deploy.libero` selected environment → OSC → worker/reader | U2 T13；两个历史 H5 95/96、103/104 | 有界自评；历史 task success 均 false |
| TEST-01 旧测试文件不是纯度／授权范围的可靠边界 | 版本 diagnostics／guard | 精确节点分纯/fake、离线、真实 source 与 native；不把文件名当授权 | `run_pure_checks.py` → 固定 pytest 节点 | U1 claim 表；U3 guarded 223 | 实施自评；guard 非 OS sandbox |
| TEST-02 测试不能把旧候选布局定义为新架构的正确性 | 现行 diagnostics／历史 fixtures | 迁移仍有产品意义的检测器；退役候选不作为产品正确性条件 | `test_solution_compatibility.py`／legacy reader tests | U1 claim/owner 表与旧 oracle 去向 | 实施自评；不复活 candidate |
| TEST-03 生产诊断探针应归位，但正式证据接口不应一起删除 | 诊断 probe／provider admission／codec | 实验 probe 与产品合法准入、readback、历史 codec 分层保留 | `legacy_leaf_judge.py`／`load_legacy_leaf_control_h5`／provider admission | E05–E10 S07/S08/S32；U1 分类 | 有界自评；不机械删除 F05 |
| TEST-04 测试和报告必须能复核，文件数量不代表证据强度 | 版本诊断／最终证据包 owner | 读回与关联明确数据身份；最终五 stage 证据迁移与复算未完成 | `associate_solution_record.py`／U5 独立 reader | U3 同次读回；U5 T29–T34 | 代码证据自评；证据归并 OPEN |
| DOC-01 当前能力、历史决定与拟议方案必须分栏 | capability matrix／current-state | 当前有界证据、历史规划和未测 G06/G07 分开 | 版本 README → current-state → 单一 capability matrix | 本轮矩阵与五条关联复算；docs validator | 实施中；独立主审待完成 |
| DOC-02 开发规范与 Skills 必须反映已经落实的 owner | AGENTS／TaskEnv／版本 Skills | 更新实际 owner、正式入口及历史 candidate 标注；修复 routes 中退休 source 路径与过时 state-only 说法 | `.agents/skills/geochora-task-env`／`task_env/doc/api` | 九份 Skill 静态检查、TaskEnv Skill validator 和 45 项守卫定向测试；U4 记录 | 实施自评；独立行为主审待完成 |
| PROJ-01 大量 attempt／continuation 目录已经妨碍恢复和使用 | stage 证据／maintenance workspace | 按主审 claim 选择必要成功结果，未归并或删除 | U5 final package → 独立 reader | U5 T29–T34；U6 T35–T38 | OPEN；无具体删除授权 |
| PROJ-02 原始证据、可重建缓存和第三方资产必须分开 | source／USD 资产／证据闭包 | 区分原始证据、缓存和第三方 source；闭包和迁移映射待冻结 | U5 source closure／stage reader | U5 T31–T33 | OPEN；无迁移复算 |
| PROJ-03 生成物应继续 ignored，Git 历史清理不能与 workspace 归并混做 | Git ignore／workspace | 生成物保持 ignored，Git 代码提交与证据整理分别核对 | `.gitignore`／`git ls-files`／U5 package | U5 T34；U6 核查 | OPEN；未执行整理 |
| PROJ-04 真实输出目录和运行 cwd 的副产物必须列入清理范围 | 输出目录／cwd 副产物 | 按具体路径测量并排除保护输入、其他项目和 nested worktree | `workspace/maintenance`／`temp_outputs`／保护文件清单 | U6 T35–T38 | OPEN；未授权删除 |
| BRANCH-01 阶段分支、旧 worktree 和证据路径需要一起处置 | Git refs／worktree owner | 确认 ancestry、dirty/ignored、子模块及恢复后按授权处置 | `git worktree list`／refs／U7 恢复验证 | U7 T39–T44 | OPEN；未移除或重写 refs |

| 验证 | 当前证据与结论 |
| --- | --- |
| V01 | U3 映射：正式配置及 mapping/YAML 等价；不外推任意组合。 |
| V02 | U3 映射：四主体与装配按各自原生输入或本轮完整运行关联；旧输入不冒称本轮重跑。 |
| V03 | U3 映射：Position／effort、双 writer 和 fault 按受影响范围复用；不扩大所有控制组合。 |
| V04 | U3 映射：borrowed／独立 renderer 和非 Position 按原输入复用；没有新像素资格。 |
| V05 | U3 映射：三原生和 GeoPhys physics × MuJoCo renderer 的原始去向及各自限制。 |
| V06 | U3 映射：reset、step、再次 reset、采图和 close 的有界原始结果；本轮 fake 另列。 |
| V07 | U3 映射：source／资源／stale／fault 及旧入口按精确节点与历史 oracle 复用。 |
| V08 | U3 五条单 seed 完整尝试；两项 MuJoCo 均成功，Isaac 任务／Solution 失败。 |
| V09 | U3 同次 H5 的独立读回及 caller 报告关联；Isaac v3 completion 缺失仍为 T19 OPEN。 |
| V10 | 当前文档／示例和能力矩阵正在更新；原 2 项基线错误中的退休源码引用已改为精确历史 Git 来源。历史源码行号误报修复后，docs validator 现有 1 项保护文件 hash 错误及 79 个历史链接问题；逐项归属见 U4 实施记录。五 stage 归并、项目清理、恢复与维护者接收尚 OPEN。 |

V01–V09 的命令、输入、证据入口与限制见 U3；每项仍需独立主审。`OPEN` 不构成 N/A、延期或维护者同意。
