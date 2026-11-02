# F06：PickCube × Task Harness × 多后端稳定示例

> 2026-11-01维护者范围裁定；状态`GOAL_PACKAGE_PREPARED_NOT_DISPATCHED`。本页是F06当前实施合同。新F05主线已由Sol按原生适配范围有界接收；F06尚未执行，F07/Qualification不启动。此前文档将F06限定为真实外部资产、20-seed全solved、成功Oracle与Judge包的要求，在本轮example范围由本页替代；原Harness严格合同继续保留。

## 1. 目标与验收边界

以`task_env/tasks/pick_cube/`为任务owner，接通现有Task Harness，形成一个公开example，使用同一Core Runtime显式选择Isaac Sim、MuJoCo、GeoPhys，并通过现有solution展示规划与执行。Genesis、SAPIEN为可选后端。优先可调用、可观测、可记录；允许抓取/抬升或Expert阶段失败，不允许接口故障、silent fallback、崩溃或记录损坏冒充有效任务失败。

维护者明确要求三个主要后端均验证，每后端三个固定seed，且不强求所有仿真器完成任务。固定seed为31/32/33；保持现有PickCube任务谓词、XY随机分布及timebase。每行独立报告runtime有效性、规划事实、Expert、Task、终止/截断与存储结果；不把“跑完3 seed”说成“3/3 solved”。本页不新增所有seed或任一指定Provider必须solved的门；保留现有MuJoCo成功路径作为回归参考，实际退化须解释，不能以新标准掩盖故障。

## 2. 当前行为与具体缺口（审查740a74a9）

| owner / 当前方法 | 实际缺口 | 实施方向 |
| --- | --- | --- |
| `task_env/tasks/pick_cube/task.py` 的 `build_reference`、`make_reference_binding`、`PickCubeReferenceEnv.from_reference_config`；公开`make_env` | 目前构造绑定MJCF RuntimeSource，binding忽略provider并固定CPU；公开selected config只接provider/backend/horizon/controller_profile | 在原任务owner内组合现有能力，扩展明确的provider/device/profile选择；保留旧默认和现有UID，不从Harness调用诊断worker来绕过Core。 |
| `task_env/objects/pick_cube.py`、`task_env/tasks/worlds/tabletop.py`及PickCube composer | 现有任务方块50mm/0.08kg，桌面z=.462，TCP在hand上偏移.0584m；F05诊断为60mm/0.1kg、空中初态、不同语义ID | 各后端使用PickCube实际recipe、几何、reset、Task含义。Isaac单独版本化桌面表示与映射，不能仅改F05标签/放宽guard。碰撞proxy、驱动等派生差异明确记录。 |
| `position_candidate/builder.py`、`runtime/sessions/{api,control,leaf_control,native_io,isaac_native_io}.py` | 已接收DG04公开I/O与native mimic，但精确candidate/scene/profile锁定F05诊断；不能直接接PickCube Expert | 复用适配算法与Session/Recorder，扩展任务绑定与model-bound准入。旧F05 exact-profile保护不删除；F06新输入绑定实际桌面source/Task/reset/controller。无需完整软约束/传力等价研究。 |
| `pick_cube/solution.py` 的`PickCubeReadinessConfig.from_source`、`PickCubeReadinessSolution` | 读取`source.config`和public observation中的`cube_v1_body_pose`，EEF、gripper schema/反馈与现有名称绑定；USD输入并非相同结构 | 在原任务/公开投影owner对齐输入、状态、TCP、Action与反馈；复用solution/AbsolutePosePlanner和现有R3连续反馈，不复制另一个Expert或读取私有native状态。 |
| `script/agent/harness_compiler.py` 的`compile_candidate`/`CompiledTask.env_class`、catalog/spec/asset检查 | compiler自组Artifact/reset/evaluate_lift，默认CPU；catalog普通provider_manifest尚不含Isaac exact-cell | 增加小范围、版本化内置PickCube example配置，委托Core原构造入口。catalog的资产已准备、安装可用和实际运行通过分开；支持精确Isaac/profile，不能向generic manifest无证据放行。 |
| `feasibility_probe.py`、`completion_facts.py`、`oracle_candidate.py`、ledger/Judge | 现有流程以至少20 seed全solved/Oracle成功为准；后端CPU写死，打包强制mock bundle | 独立`example-validation`模式，3 seed分别报告runtime与Task。复用原始事实/record/inspect；失败也留普通rollout H5。不全局降低严格合同，不伪造mock bundle或通过Judge。 |
| `examples/tasks/pick_cube.py` | 仅MuJoCo/GeoPhys CLI，使用CPU及虚拟地址空间限额 | 扩展同一公开示例的provider选择；Isaac用已有专用Python/受控App worker，避免把CPU的8GB RLIMIT_AS误用于GPU App。 |

改动分类为`EXTEND_EXISTING + COMPOSE_EXISTING`；不建设新Runtime/Recorder/Controller/provider抽象或通用场景编辑器。允许在这些owner内拆小文件，但不把能力留在ignored工作目录。

## 3. 实施顺序：同一Goal内连续完成

1. **A Core与Harness先接MuJoCo。** 固定内置PickCube recipe和R3 controller选择；内置来源有明确version/hash，不伪造外部任务/资产。example模式从catalog/spec经现有Core构造和solution跑通一集，立即检查记录/结果分类。保留原recipe reset分布及Task谓词；不为PASS缩采样范围。
2. **B 扩展GeoPhys与Isaac。** GeoPhys优先复用现有PickCube MJCF CPU路线及主仓gitlink；实际导入build与路径必须记录，不能把DG02隔离USD证据套给它。Isaac复用DG04适配机制，生成F06桌面表示，补齐source/role/reset/TCP/Action/observation/Expert反馈。允许原生驱动与约束适配，但差异不能静默。三后端同seed应消费同一任务reset值；无跨solver轨迹逐点相同要求。
3. **C 正式三seed与示例收口。** 冻结稳定commit/config，对三个主要后端分别运行31/32/33。前面符合完全相同身份的合格预检可计入对应seed，不为报告重复运行。保存9份实际episode记录，分别读回；生成主矩阵和一条可复现示例命令/后端。每后端选择seed31展示计划TCP与实测TCP、抓手开合曲线或等价离线轨迹图；标注阶段失败/提前结束，不做渲染器/视频项目。

Genesis/SAPIEN只复用已有adapter。安装/能力/场景已准备则可做小范围执行；否则明确`NOT_RUN_DEPENDENCY`或`UNSUPPORTED_CAPABILITY`和具体原因，不装新引擎、不展开新适配工程、不阻塞三主要后端。

## 4. 核心出口与最小测试

- 三个主要后端须真实经Harness→公开任务构造→SelectedReferenceEnv→RuntimeSession→adapter，完成build/reset、实际solution调用、公开action控制/physics时间推进、状态/Task回读、H5持久化与close。每后端须有真实规划动作进入执行的证据，不能仅reset或无动作空转后称example通过。
- 每seed可在真实Task/Expert结果出现或horizon结束时停止；Task未成功、正常Expert失败、正常horizon截断如实记录且不自动否定runtime有效性。运行时异常、execution_fault、丢失观测/动作、错误shape/unit、worker异常退出、close失败归runtime失败。调用链正常与规划可行/任务成功分别汇总。
- 固定horizon1000 control intervals、physics_dt=.002、substeps5；只有原solution计算的必要上界/实际运行成本证明需要调整时，先记录理由并在正式活动前冻结，不靠无限延长horizon获取成功。reset正常Task约定保持，初始化步骤单列，时间和T+1自洽。
- 只做一个受影响Core/Harness联调测试集：provider/config派发、同seed reset/TCP/单位与schema、mock vs builtin来源、runtime与任务失败分类、3seed example不能冒充20seed候选/Judge、H5/finalize/close。具体共享代码变化再加对应窄回归。无需全任务/全部provider矩阵、历史tamper全集或F05三路线重跑。
- 9份episode数据沿用现有Recorder与reader/inspector，检查T+1、实际时间/动作/状态有限性、provider/source/controller/solution身份；至少每主要后端一份独立cold read，另外两份使用同一已验证检查路径。计划轨迹与实测轨迹明确区分。普通失败rollout不命名成功Oracle。
- 新example结果使用独立状态，例如`EXAMPLE_RUNTIME_VALID_TASK_OUTCOME_REPORTED`。原20seed全solved的`candidate_ready`、成功Oracle及Judge prepare/verify保持严格。不为本Goal新增成功Oracle或pending Judge的强制门，也不把3seed示例包送入原严格通道。

## 5. 资源、恢复和协作

复用develop-full，不增branch/worktree。Sol准备一个完整包，由维护者转述后Luna实施、定向验证、本地提交并交Sol复核。本轮预计主动4–8小时；window001规划时间盒8小时，最后约30分钟收口，外部等待单列。Goal可跨有明确进展的续包；普通attempt按仓库规则最多3个窗口，本轮不是重置旧F05诊断计数。时间盒结束须交精确进度，不为了包格式拖延；不设置额外累计native步数/启动数硬限，每run有有限horizon/bootstrap/timeout。

复用现有native supervisor/共享锁/受控退出；worker在合适环境启动，Isaac OpenUSD必须来自冻结Isaac Python。RAM/VRAM启动与实际资源保护保持；一次只运行一个native worker。监督持锁至进程组退出。孤立采样抖动记为监控信息，实际资源越界/持续丢监控才中止；CPU限制是最多4个可运行affinity槽位，不以引擎后台线程数判物理失败。

每门连续两次实际失败后提具体问题并等待，不能原样第三次尝试；一次后也要有新证据/假设。禁止因backend任务不成功开展无止境控制调参或C++/solver研究。遇到确需改变Task/资产物理属性、引擎安装或公开能力不足，给具体方案询问。

当前状态保持一页RESUME：总目标/当前阶段/最后结果/下一动作/待答问题/worker状态。压缩后读新包+当前状态，历史按需引用；不重读巨大Skill和历史快照，不嵌套旧ledger。交接核对HEAD/dirty及少量相关source/code身份；记录无关untracked文件并保护，不藏文件或把repo_dirty谎报false。严格旧Harness仍拒dirty；本example可显式采用冻结的tracked-clean/expected-untracked证据范围，新字段如实记录，不放宽旧默认、不开任意allow-dirty。

稳定后更新公开example/API/provider支持说明及相关TaskEnv/Harness Skill的当前路由一次，生成短refresh收据；不逐run堆历史。全局docs validator已知范围/数量诊断单列，不作为runtime阻断。结束提交本地commits、报告三后端各seed结果及可选状态，释放writer/native窗口；不push/merge/tag、不发其他线程消息、不spawn agent，不启动F07/训练/Qualification。

## 6. 本轮工作包与复核

window001包：`workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/sol_f06_001/`；输出：同根`f06_001/`。精确输入HEAD、prompt SHA与运行政策由包冻结。准备本页未执行F06，也未恢复/消息任何线程。

完成候选为`F06_PICKCUBE_HARNESS_THREE_BACKEND_EXAMPLE_PASS_PENDING_SOL_REVIEW`，须三主要后端runtime门及三seed报告齐备；任务结果按事实记录。若一条主要路线仍构造/执行失败，整体为PARTIAL，已通过路线可保留为有界增量。由Sol依据真实diff与关键证据决定接收，不由Luna自动授予正式Qualification。
