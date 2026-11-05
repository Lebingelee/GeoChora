# G03：新Sol接手检查点

2026-11-05，状态`READY_FOR_MANUAL_HANDOFF`。本次只准备阶段3的编排／主审交接，不派发实现、不运行native、不创建分支或对话。核对输入为`develop@7bfe53828762d2eda1d7a566caa82d74dcc00d42`；交接文档提交后的准确HEAD由外部包`V211_G03_sol_handoff/input-snapshot.json`冻结，新增内容仅文档／编排元数据。

## 前置与当前状态

| 项 | 接手结论 |
| --- | --- |
| G01 | 1a–1d已获有界审阅，五协议为[APPROVED_IMPLEMENTATION_BASELINE](20261103_protocol_baseline_confirmation.md)；设计确认不代表新协议已全部实现 |
| G02 | [ACCEPTED_BOUNDED_STAGE2_REFERENCE](reviews/20261104_2c_sol_review.md)：PickCube MuJoCo31成功实现、受影响Nut回归及2c参考冻结。seed32失败、GeoPhys时间guard及Isaac未运行边界保留；不重开2b |
| 生命周期 | `48401525`实现、[Sol有限接收](reviews/20261105_lifecycle_unification_sol_review.md)：三个旧单环境使用SelectedReferenceEnv，共同episode owner，BaseTaskEnv四出口同对象 |
| 前置核心收尾 | `99de88ab`返包、`3c0c73ee`[Sol接收](reviews/20261105_pre_stage3_closeout_120min_sol_review.md)：C1核心职责、C2当前文档、V受影响验证已收口。runtime不再依赖具体Nut Solution；未完成广泛整理不倒填为通过 |
| 新诊断规范 | `7bfe5382`落库：[全局规范](../../../../global/diagnostics-and-code-boundaries.md)、AGENTS及TaskEnv文档已接入。现存耦合登记，当前不全面解耦，7a集成前集中处理 |
| G03 | 3a／3b／3c均PLANNED、attempt0，没有准备或派发的3a实现包。实时表见[编排索引](orchestration.json) |

环境类仍有3420行、多种正式执行路线与诊断遗留；有限接收不表示其已成为纯组合薄类。后续不得新增实验／测试识别分支；既存问题按[第2.6节](../planning/pre-stage3-environment-refactor.md#diagnostic-policy-and-final-cleanup)处理，不把本次交接变成另一轮前置重构。

## 阶段3路线与分支

以[Goal03](../goals/03-backends.md)及[执行表](../planning/execution-and-acceptance.md)为准：3a配置／能力求交与拒绝回执；3b三后端真实场景翻译、公开反馈与最小运行；3c同一个public Env通过reset重建切换、随机流和旧数据失效。先审3a，再准备3b、3c；不以关闭并新建Env冒充3c。

维护者已改为从develop建立一个阶段3主题分支，3a–3c共用，建议名`codex/v211-stage3`，尚未创建。默认复用当前checkout、新worktree计划为0；现无并行writer的执行授权。若将来需要同时写develop与阶段3，先安排独立目录／scope，不在同一checkout并行写入。保留本地已接收提交和历史refs；按阶段政策检查远端差异，但不reset到旧remote-tracking develop。本次未fetch或查询远端。

## 新Sol首轮必读与动作

1. 仓库AGENTS、[诊断规范](../../../../global/diagnostics-and-code-boundaries.md)、本页及[恢复页](recovery.md)。旧报告中的待复审、PARTIAL和停止阶段2只属于其历史检查点。
2. [协议确认收据](20261103_protocol_baseline_confirmation.md)、当前五份contracts及Goal03，特别是physics／统一表示／lifecycle。公共类型和schema版本实施前核对源码，不按旧1c的7＋1 closure提案实施。
3. 当前[Env](../../../../../task_env/doc/api/semantics/task_environment.md)、[Solution](../../../../../task_env/doc/api/planning/task_owned_solutions.md)、[安装／路径](../guides/installation-and-start.md)说明，以及上表三份接收记录。源码映射的旧日期表只能用于导航，使用CodeGraph后按当前源码和真实消费者确认owner。
4. 核对实际HEAD、dirty paths和是否已经有执行包／writer；不要重复派包。确认阶段3分支安排，准备一份完整3a包，由维护者转发Terra或Luna；Sol不直接消息实施者、不自动启动native／subagent。

每包冻结具体owner、修改与拒绝边界、合理总窗口、必要验证、输出和停止条件；实现、相关验证、修复、文档、提交、报告在同一包内。旧维护的两小时、300000物理步及资源账本不是G03新预算。避免无关全库审计、逐helper提交／宽回归、重建资源平台；按真实变化复用证据，保留原运行身份。

## 技术与证据限制

- 首批必须接通MuJoCo CPU、GeoPhys CPU、Isaac Sim＋PhysX CUDA的冻结交集。当前R3主要是位置参考路线，不是阶段4的通用JointEffort／BodyWrench已完成；selected普通渲染仍state-only，统一并行留G06。
- Core与GeoPhys的MuJoCo依赖声明区间不相交，3a须给出可实施隔离／路由方案；新worktree不会自动包含ignored SDK／资产。先核对显式解释器、源码与资产路径，不以缺少pip发行包或checkout内SDK推断新安装，也不执行旧Core替代当前源码。
- `cf425acc`的Nut MuJoCo19成功2377 transitions，2378 boundaries，11885 native substeps及同run reader通过。其后R05b专用变更不重标普通MuJoCo运行。PickCube复用`5a04140a`的MuJoCo31成功960 transitions和reader；原身份和差异依据见核心收尾Sol记录。
- R05b两档新caller只做无引擎契约验证，真实GeoPhys provider未验证；Isaac／GPU／全新安装／矩阵不得假称已通过。GPU、路径或锁的历史错误不是当前实时状态，真正执行时按该包需要核实。
- 模型质量／惯量、单位／Frame、native mapping／readback及reset数值分别验收；required未测不能填PASS，约5%的cube惯量差不自动修正。Controller／planner／任务阈值不因后端失败随意改变。
- 3c保持同一public Env，内部可重建session／worker／App；明确seed重置／None延续、preflight拒绝不消费当前随机流、代次与旧view／command失效、失败后禁止step及资源唯一收尾。

旧H5、报告和ignored输出留原路径；不为接手复制／重新hash所有raw。仅当准备实际native包时使用现有双锁与必要运行约束，不以旧窗口释放推断整台机器资源空闲。推送、合并、tag、Release和Qualification均不在本交接授权中。
