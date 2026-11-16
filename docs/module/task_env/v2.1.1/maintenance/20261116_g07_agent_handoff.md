# v2.1.1 G07 Agent handoff：任务复用、最终验收与文档收口

交接日期：2026-11-16。维护者已要求逐步进入G07，本轮交付上下文与实施起点，**没有启动7a/7b/7c执行Goal、native或新的工作包**。G01～G06的有界结论保持；G07三个子阶段均为PLANNED／attempt0。接手后先准备一个完整的7a工作包，再按7a→7b→7c推进，不将全部最终矩阵塞进首次调研窗口。

## 1. 真实输入与恢复入口

| 项目 | 本轮核实的交接输入 |
| --- | --- |
| 仓库与分支 | `/home/lly/Program_Files/Geochora`；`codex/v211-stage6-parallel` |
| G06最终交付Core | `0c4fb5ded6fc2bf0e79eae246269096545d4ec8d`；当前生产代码结案`4332844f0ede0c8f56f75a27c773bd2cf7bd67f5` |
| 本交接提交 | 上述Core的文档后继；实际交接时记录`git rev-parse HEAD`，不checkout旧生产提交丢掉结案材料 |
| GeoPhys HEAD/gitlink | `198d30ac64ce873a1467f55d2adfc471db18fbc5`；本地分支`codex/v211-stage6-render-device` |
| Menagerie | `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`，未变 |
| 工作树与保护 | 编写前tracked clean；唯一预存untracked为`MUJOCO_LOG.TXT`，SHA256 `3b08b858f62dcbaa6521802455c76126f9876a3d6727c7586db90c94296ed6a8` |
| 设备与依赖 | 当前约8GiB VRAM／16GiB RAM；主环境MuJoCo3.8.1、Torch2.14.0+cu130、Forge0.7.0；MJWarp4.0.1/Warp1.18.0与Isaac6.2按既有profile隔离 |
| Git同步事实 | Core曾同步/push develop至`120281a1`，最终G06/6c及收尾仍是本地后继；GeoPhys已合入当时上游main，但阶段成果未反向合并上游；本交接不push/merge/tag |

阅读顺序：仓库`AGENTS.md`及适用Skills → [当前摘要](current-state.md) → [G07原Goal](../goals/07-integration.md) → [G06实施总结](g06/implementation-summary.md)及[证据索引](g06/evidence-index.json) → [原优化账本](../planning/post-5c-code-project-optimization-diagnostic-ledger.md)及其历史结案 → 下列7a附加用例与现有caller。不要先重读所有旧attempt或按旧文档“NOT_RUN”从头实现已存在能力。

G06的461份主要证据及核验副本位于`workspace/maintenance/v211_stage_closeout/stage06/`；原始目录保留。副本不是完整可移植native环境，所需source、delivery、SDK及profile仍按冻结身份恢复。不得清理这些证据、原source、保留stash、锁或第三方资产。

## 2. 已完成能力与不能外推的地方

G05已完成共同Task／Robot／Controller／source构建及E00～E16代码/项目整理；G06进一步接通三后端×Pendulum/PickCube CUDA native batch，canonical action、device Task/state、具名base/hand相机、same-step终止图像、部分reset和固定Rasterizer整批重建。公共入口为标量`make_env(uid, config=...)`、设备批量`make_parallel_env(uid, env_config=..., execution='device', backend='cuda')`；配置与生命周期共享原owner。

G06实际支持的跨provider整批边为Isaac↔MJWarp，两个任务都有同一Env的A→B→A；GeoPhys部分reset成立但跨provider切换未准入。GeoPhys PickCube batch仅显式discrete/contact32/coupled32已验证配置；continuous mesh＋约束、默认预算的旧大穿透异常并未因此解决。shared scene相机可能看到其他行几何，不承诺视觉隔离。旧scalar SHA回执迁移、AOT及上游反向合并等原暂缓事项保持，不自动变成G07额外前置。

**R3范围要分清：**尚未开展的是G06新增CUDA batch的R3／模型／重力补偿独立包；它不阻断canonical G06，也不自动纳入G07。7a原有的单环境Controller/Solution复用、装配机器人自身模型与补偿用例仍须按原要求完成，不能借“R3另包”删掉这些既有任务。

## 3. G07三个子阶段的工作与出口

| 子阶段 | 本阶段工作 | 完成判据 |
| --- | --- | --- |
| 7a 任务/Robot复用与caller | 先按实际消费者收口阶段3–6新增诊断耦合，再接Nut已支持路线、原/装配Panda两任务用例、BaseTaskEnv兼容名、examples、LIBERO与learner/vector边界 | 代表性真实复用；装配用例逐项结论；调用者支持/拒绝/未迁清楚；源码在进入7b前稳定 |
| 7b 稳定输入最终验收 | 冻结Core/provider/source/Robot/Controller/Solution/renderer/device/seed/horizon/预算/oracle，执行原PickCube三后端×三seed及其他最小代表门 | 九格9/9 task-success，runtime、predicates、lifecycle成功、Solution完成、图像、同运行H5读回及close各自成立 |
| 7c 版本资料收口 | 按7b实际结果更新协议/API/配置/指南/示例、单一矩阵、当前导航、恢复入口及Skills，复核dirty/gitlink/refs与证据 | 文档准确可恢复；未支持/未测明确；失败有收据但不能用资料完备代替7b成功 |

7c不承接大规模源码改造；7a完成应有的归位后再冻7b输入。复用未受影响的更强证据，不重跑G06的18项性能或全部历史A123。不同solver不要求力值、轨迹或像素逐点相同；若出现明显物理、控制或生命周期异常，按具体owner修复，不用“引擎不同”解释掉。

## 4. 7a的实际起点：装配Panda已经存在

正式任务为`pick-cube-p16-reference-v1`与`nut-assembly-outcome-reference-v1`。原Panda UID为`panda-v1`；[AssembledPandaAgent](../../../../../task_env/robots/assembled_panda.py) UID为`panda-arm-hand-v1`，已有arm＋hand recipe、具名组件及`r1/r1_split`。**不能再按旧规划新建第二套装配Panda、Controller或source框架。**

当前PickCube允许选择装配UID，但该Robot recipe尚不能由此宣布支持所有profile；Nut目前仅允许原Panda与`r3_continuous_v1`，已支持MuJoCo/GeoPhys scalar CPU，明确不支持Isaac。7a沿既有Robot recipe、共同source composition和Task binding补实际缺口，不新增Nut Isaac、Nut native batch或全部后端装配矩阵作为默认门。

| 附加用例交集 | 可复用的现状 | 7a仍需做什么 |
| --- | --- | --- |
| 原Panda × PickCube | 4c及G05 C5有MuJoCo完整成功；GeoPhys/Isaac亦有各自旧输入的单seed成功 | 核对与最终7a输入的影响，匹配可复用，失配补最短必要运行 |
| 原Panda × Nut | G05已有MuJoCo/GeoPhys seed19完整成功及同运行读回 | 同上，不因“复用Nut”盲目新跑所有组合 |
| 装配Panda × PickCube | G05 U7有正式配置的短程reset→step→reset→close | 补原Solution完整任务成功及独立同运行记录 |
| 装配Panda × Nut | Robot/source已有共同基础，尚无查到的完整成功交集 | 在原owner补Task配置和Controller能力接线，再完整复用原Nut Solution |

[装配用例说明](../planning/stage4-assembled-panda.md)与[用例JSON](../planning/assembled-panda-use-case.json)还要求自身可行域内的空载夹爪中心TCP跟踪、适用的本体补偿、现有夹爪开闭/代表抓放。5个子步的构造短测不能替代这些结果。原/新机器人无需质量、惯量、摩擦、初始q或轨迹逐点等价；各任务原Solution算法/策略与成功判据保持，不复制一套“装配专属Solution”过关，不自动补偿抓持物载荷。

用例JSON的初建`implementation_started=false/AP NOT_RUN`已在本交接中按“已有类/短测、完整用例未接收”校正；历史初建值仍保留，不把部分成果升为AP整项PASS。附加用例不乘进7b原九格。

## 5. 既有成功参考与证据复用

| 来源 | 保存的真实结果 | 复用边界 |
| --- | --- | --- |
| [4c主审](reviews/20261106_4c_attempt001_sol_review.md) | MuJoCo PickCube seed31成功，993 transitions/994 boundaries；同Env Controller/input规格reset | 旧输入下的原Panda参考，不自动替代当前九格 |
| [G05 C5](reviews/20261114_post_optimization_c5_final.md) | MuJoCo PickCube31为960/961；Nut19为2377/2378，完整成功与独立读回 | 精确输入与影响匹配才复用 |
| [U4同运行联合证据](reviews/20261113_e11_e16_u4_joint_completion.md) | 原Panda GeoPhys PickCube31为951/952、Nut19为2442/2443；Isaac PickCube31后修复`solution-002`为951/952 | 五条正式完整运行均state-only，分别保留原source/pin；早期Isaac失败不覆盖后来成功 |
| [U7装配路线](20261113_e05_e10_u7_delivery.md) | MuJoCo装配Robot短程构造/控制/reset/关闭 | 只证明相应短程，不能声称AP-C2/C3或完整Solution通过 |
| [G06总结](g06/implementation-summary.md) | canonical六格、设备/相机/记录、部分reset、固定renderer切换与故障清理 | 不替代Nut完整Solution或装配Robot用例；不将batch接触成功移植为scalar任务成功 |

旧H5的Solution completion可能不存在或为null；既有接收依据是**同运行caller完成事实＋H5独立读回＋身份/监督/关闭关联**，不能改写成H5单独证明完成，也不能从`stop_reason=pass`反推Solution完成。新7a/7b记录优先沿用正式Recorder的可用字段；存在必要记录缺口时在原owner修复，不为历史文件填假字段。

GeoPhys旧scalar完整成功与后来记录的scalar mixed局部缺陷都保留，G06 batch是另一条路径。7b应按最终选定路线的真实任务行为定位问题，不自动开展通用mixed/软接触/Schur研究，也不要求接触力追平MuJoCo。

## 6. 首个7a工作包的代码落位与兼容边界

| 关注点 | 现有owner/入口 | 接手原则 |
| --- | --- | --- |
| 共同构造 | `registry.make_env`、`environment/configuration.py`、`environment/reference_binding.py`、`SelectedReferenceEnv` | 复用TaskBuildRequest/SourceBoundTaskBuilder，不另建factory或Runtime |
| Nut语义 | `tasks/nut_assembly/{specialization,task,solution}.py`，`NutAssemblyOutcomeSolutionV1` | Task差异与严格成功/完成语义留Nut，不塞进公共Env |
| Robot/source | `robots/{panda,assembled_panda}.py`、`runtime/sessions/source_composition_adapters.py`、`assembly/{panda_fixed_source,panda_source_profiles,nut_assembly}.py` | 具名组件/TCP/profile匹配与source lowerer各归原owner，公共层不写Panda维度或任务名特判 |
| 正式caller | `examples/tasks/nut_assembly.py`、`examples/recording/record_expert.py`、`examples/_common.py::run_caller_solution` | 按reset→act→step→observe驱动原Solution，不从诊断包借私有接口 |
| 旧import名 | `environment/env.py`的BaseTaskEnv薄alias及`tasks/base.py`导出 | 保留2.x兼容名，不重建旧基类生命周期 |
| learner/vector | `vectorization/{sb3,sb3_remote}.py`、`alg/rsl_rl/{adapter,action_transform,training}.py` | 明确fixed-space与autoreset所有权；不把旧wrapper合同通过当新CUDA Env训练通过 |
| LIBERO | `bench_deploy/libero/environment/selected_reference.py`、其controllers/trajectory | 只验受影响代表caller，保留benchmark source/谓词/OSC/gripper cadence，不换成PickCube、不全量A123 |

特别注意：旧SB3 host路线有自己的masked autoreset，不能直接包G06 same-step CUDA Env再次reset。RSL现有device adapter消费`step_device()` named transition，而G06正式device Env要求`step()`并拒绝`step_device()`；接手先判断支持/明确拒绝/必要适配，不能从类名推断兼容。7a要求有效边界或受影响适配，不增设完整训练门。

诊断耦合从[登记清单](../planning/pre-stage3-environment-refactor.md#diagnostic-policy-and-final-cleanup)开始逐项核对；其中旧`diagnostic_profile`、`_record_leaf_position_transition`、`_diagnostic_manifest`样例在当前对应生产路径已经退出，记录已迁/已退，不能照旧名单恢复它们。正式来源准入、feedback、fault、stale检查及有效trace/reader保留，不按F06/R06/diagnostics名称删功能，不以文件长短机械拆分。规则以[全局边界规范](../../../../global/diagnostics-and-code-boundaries.md)和[优化账本](../planning/post-5c-code-project-optimization-diagnostic-ledger.md)为准。

首包先用真实caller列“已具备/未接通/需验证/不支持”，确定最小补齐owner，再同时包含实现、普通示例、定向验证、原始证据和收尾。7a成果稳定后再进入7b；不要每发现一个小问题就返包或重开已接收G05/G06。

## 7. 7b冻结九格时不能误改的门

[能力矩阵](../capabilities/capability-matrix.json)的`final_pickcube_cells`目前九格仍全部NOT_RUN、`input_identity=null`：

| 原规划路线 | seeds | 当前最终状态 |
| --- | --- | --- |
| `mujoco_cpu` | 31/32/33 | NOT_RUN，最终7b输入未冻结 |
| `geophys_cpu` | 31/32/33 | 同上 |
| `isaac_sim_physx_cuda` | 31/32/33 | 同上 |

保留原9/9 task-success门。**G06新增MJWarp不自动替换MuJoCo CPU九格，原/装配Robot用例也不乘进九格。** 若维护者要调整路线/seed/成功要求，须显式更新范围并保留原门与失败历史，不能由执行者自行改变。

正式7b包至少冻结：最终Core/pins、实际provider部署/版本、Task/Robot/source/TCP/Controller/Solution身份、seed/horizon、dt/substeps、gravity/驱动/控制配置、固定renderer和代表图像覆盖、RAM/VRAM/子步/墙时/输出预算、独立oracle和同运行关联。原成功判据不放宽，不用runtime-valid、不同run部分结果、SDK ack或截图拼成成功。

其他门采用阶段1及阶段3–6已冻结的最小代表例：同Env切换、Controller输入规格、7＋2、BodyWrench/贡献、同步图像、并行生命周期。先对输入与源码影响分类，仍匹配的强证据复用；不是所有backend×renderer×Controller×batch×seed笛卡尔积。只有九格和其他独立门均有证据，7b才完成；若有失败，如实记录并在包内修复，不以7c文档完成掩盖。

## 8. 工作区、资源与交接流程

- 本轮保持阶段6分支不变。准备7a包时按仓库phase workflow从本交接的文档后继规划G07分支，例如`codex/v211-stage7-integration`；核实dirty及共享writer，不从旧develop/main或旧G05 pin开工，不自动同步分支。
- 开始代码定位先CodeGraph；索引漂移时读实际符号与caller，不为接手重建索引。阶段3～5登记的旧缺口必须先与后续已完成优化对账。
- 每个完整执行包冻结实际HEAD、允许改动、目标入口、验收门、预算、输出目录/证据/提交及释放要求。每子阶段最多三个普通attempt；一次失败run不等于一次attempt，第三次前做有根因的重估。只写交接不消耗attempt。
- 继续使用现有共享native锁和监督器，所有可能初始化CUDA的pytest也纳入。新阶段重新冻结预算，不能把G06的剩余分钟当作G07授权，也不能默认九条完整Solution适合沿用短程预算。
- 运行cwd与输出隔离，优先少量B/短程定位后跑正式完整任务；不杀用户进程、不改swap、不unlink锁、不擅自升级profile。释放旧scene/worker后再启下一条，进程树RSS含共享页，不能直接等同净新增内存。
- 原始H5/图片/日志继续ignored。结果、源码、Task/Solution完成、原始读回及清理收据应能关联，测试计数不重叠累加。保护日志的文档基准错误已知且实际SHA未变，不为文档绿灯修改它。
- 每次完整返包后独立主审，再准备下一包；执行中不向同一agent叠加新要求。原始失败/中断/时序偏差保留，不能事后补造。

7c按上述原Goal逐项更新文档、指南、API/迁移、单一能力矩阵、Goal摘要/编排和Skills，并检查实际caller；不只同步文字。完整九格、附加用例和未支持组合分别记录，版本接收与发布另有边界。当前交接不授权push、merge、tag、Release、第三方资产分发或选择许可证。
