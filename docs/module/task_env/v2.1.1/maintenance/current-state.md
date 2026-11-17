# v2.1.1 当前状态

更新时间：2026-11-17。本文是版本的人工可读当前摘要；工作包、attempt 和历史记录由[编排索引](orchestration.json)维护，逐项优化范围由[优化台账](../planning/post-5c-code-project-optimization-diagnostic-ledger.md)维护。

## 当前停门

G07／7a已按[attempt002独立主审](reviews/20261117_g07a_attempt002_acceptance.md)有界收尾，普通attempt数2，生产HEAD `0a6213c040e06e6385b6d1f5509af34a8d5b8372`，旧资产冻结来支本地merge `94e865e3`，分支`codex/v211-stage7-integration`。此前维护者[部分接收](reviews/20261117_g07a_attempt001_partial_acceptance.md)的原/装配Panda四个MuJoCo完整交集及空载/本体补偿继续保留；当前GeoPhys源码未按限定重跑，Nut释放MuJoCo1mm/GeoPhys8mm不变。LIBERO默认七轴真实effort/ACK/reset与同run H5/关闭、显式pose空载相对同保持输入历史OSC四项不退步已复核；64步正式caller仍task_success=false、Solution completion未评估。主审仅新增1600子步历史参考补证，未改生产源码，不重开原attempt002窗口。

[7b attempt001工作包与Goal提示](work-packages/20261117_g07b_attempt001_goal.md)已执行并部分返包，attempt_count=1，指定 PR #3 冻结 head 已本地合入。冻结生产输入 `78349184d0600e2fb804e6461930c475bfcc67c1` 的原 Panda PickCube 三 provider × seeds31/32/33 任务成功及同运行 Solution、独立 H5 和关闭均已验证；其他独立门须分别核验，特别是当前 BodyWrench 组合选择被 guard 拒绝，不可用九格替代。维护者已授权显式子步预算重置为200000，历史消耗保留；其他资源边界不变。[实施返包与证据边界](reviews/20261117_g07b_attempt001_execution.md)待独立主审。7c仍PLANNED/0，实时状态见[编排索引](orchestration.json)和[Goal约束](../goals/07-integration.md#g07-code-constraints)。

维护者现已停止attempt001，并确认公共typed贡献统一、joint effort／body wrench分别由adapter接入合法原生接口；已选择MuJoCo／Isaac／MJWarp代表接通及GeoPhys公开可达交集，见[attempt002工作包](work-packages/20261117_g07b_attempt002_goal.md)与[新增Goal范围](../goals/07-integration.md#g07b-attempt002)。该包READY待维护者转发，未启动Goal/native，7b计数仍1。九格及已通过矩阵按最终冻结身份和实际diff影响复用，不机械重跑；新载荷的独立物理/记录/关闭门仍待实施。7b整体保持PARTIAL待独立主审，7c未启动。

**G01～G06 canonical范围及G07／7a有界关闭；7b部分返包待独立主审，7c与版本收口待实施。** G06[开发实施总结](g06/implementation-summary.md)和[证据索引](g06/evidence-index.json)保留基本要求、abc成果、测试/性能、submodule及未覆盖项；G06生产结案`4332844f`，GeoPhys pin`198d30ac`，Menagerie`b846dd12`。其后scalar/batch render授权修复见[渲染收尾](20261116_scalar_render_followup.md)，不把旧生产pin当最新HEAD，不自动纳入新R3独立包。

6a、6b、6c独立主审分别为[6a](reviews/20261115_g06a_attempt002_acceptance.md)、[6b](reviews/20261116_g06b_attempt003_acceptance.md)、[6c](reviews/20261116_g06c_attempt001_acceptance.md)，普通attempt计数2/3/1。三后端×两任务CUDA native batch、canonical action、设备Task/state、相机/窗口独立、same-step终止帧、部分reset及两个任务固定Rasterizer的Isaac→MJWarp→Isaac已成立。GeoPhys限显式discrete/contact32/coupled32配置，跨provider未准入；shared scene不承诺视觉隔离。R3、旧scalar SHA迁移、AOT/上游反向合并等后续或暂缓边界不记通过。

结构复核保留真实provider/IPC差异和必要identity检查，清除无消费者重复状态；相关23项CPU纯测试通过。本次保全461份主要证据副本，原运行目录不改不删。6b未监督CUDA及6c两项时序偏差继续记录，不补造历史。窗口外观人工验收、COM/N08原失败和R05c NOT_REQUALIFIED保持原范围。文档校验仍仅有既知保护日志基准问题，实际SHA不变。

G05及E00～E16优化的原有接收见[项目接收入口](reviews/20261114_e11_e16_u7_project_acceptance_entry.md)；本次不重开。Core此前已同步并push develop至`120281a1`，最终6c与收尾仍在阶段分支，本次不合并/推送。下列G05启动输入和旧进展均为历史记录，不覆盖上方当前结论。

## 启动输入与工作归属

| 项目 | 2026-11-11 启动核对 |
| --- | --- |
| 分支 | `codex/v211-stage5-diagnostic`；优化复用，不新增分支／worktree |
| 输入 Core HEAD | `1f1359eef9bfff73cf7688a8270c5f06471dc614`；是启动输入，不是随文档提交滚动的最新 HEAD |
| 5c 接收生产基线 | `a53bf19d2526c6c336dd5d0d7108eb0f643f80bd`；输入 `task_env` tree 为 `c4460cd6bcc96a16067d3f61556a66e52da23bbc` |
| GeoPhys／Menagerie | `c1ea3cc9fb99ccbd1d31c36d6fc7b84aa936b3d7`／`b846dd12bc459d776cccb3dee0b1d02acbf7a9c7` |
| 工作树 | 启动时 tracked clean；四个既有 untracked 输入原样保护，含优化台账 |
| 执行窗口 | 单元 9 已有返包及释放记录；启动观察未见本仓库 native worker，前序协调 chat 为 idle；启动时当前 chat 仅写 O0 文档；后续直接实施 E00～E04 的资源使用按其运行计划及释放记录核对 |
| 当前改动 | E00～E04 已完成实施、基线独立主审及主审余项修复，并于 2026-11-12 获维护者统一接收。E00～E04 接收生产 `912416e6`，精确验证输入及限制见执行计划第 6 节；不沿用启动表充当实时锁 |

上表启动时的保护输入为 `MUJOCO_LOG.TXT`、2026-10-30 runtime route handoff、stage3 gravity proposal 和用户优化台账。精确大小／SHA-256 与原工作树状态在 ignored [输入快照](../../../../../workspace/maintenance/v211_post5c_optimization_o0_20261111_001/input-snapshot.json)，启动轮没有提交这些输入。维护者此次明确授权后，三份Markdown已在`0722341b`原样纳入Git，字节及原历史结论未改；目前仅`MUJOCO_LOG.TXT`仍为保护untracked。两个pins不变，没有清理原始输出、push或改tag；本地develop快进见上方交接记录。

## 已接收的能力与边界

- G01 协议基线；G02 MuJoCo PickCube 成功参考及 Nut 回归；G03 路由、真实执行与 reset 重建；G04 typed 控制／贡献／反馈／Controller reset，分别按原主审范围保留。
- 一体 Panda、装配 Panda、Pendulum、双轮车有共同主体／Assembly／Controller／场景 interval 的受测链；不声称四主体都在最终生产 HEAD 重新运行。
- Pendulum／双轮车的 MuJoCo CPU、GeoPhys CPU 和 Isaac PhysX CUDA 短程路线限各自受测资产。三条首批原生窗口／离屏与 task RGB 按主审及影响复用。
- 最新 Isaac task RGB 已覆盖 reset、非零 step、二次 reset 及 close；GeoPhys CPU physics × MuJoCo renderer-only 已有真实状态映射和零额外物理推进证据。依据见[单元 7／8 主审](reviews/20261111_unit007_008_sol_review_a53bf19d.md)与单元 9 综合主审。
- renderer 创建时选定并保持到 close；通用动态切换、任意装配树、任意组合、通用闭环及完整 batch 能力仍不属于已接收结论。颜色／挂载／source 限制继续适用。

COM 原严格判据失败、维护者有界采纳、原 N08 FAIL、R05c `NOT_REQUALIFIED`、Isaac 6.1 close 限制及历史执行偏差保留；不借本次状态更新转移资格或重开 5c。

## 正式入口及当前实施

E00～E04 接收生产为 `912416e6`；四个正式任务使用 `task_env.make_env`：`pick-cube-p16-reference-v1`、`nut-assembly-outcome-reference-v1`、`pendulum-v1`、`two-wheel-balance-v1`。mapping 与 YAML 进入共同配置解析及构建请求；具体支持的 Robot、Controller 和 provider 组合以配置准入及相应证据为准。基线生产 `76536d2a` 已有[独立主审建议](reviews/20261112_e00_e04_independent_review_76536d2a.md)，后续主审余项在 `912416e6` 修复并自检；维护者于本次对话统一接收 E00～E04。后续自检与原独立主审仍按各自时点保留。

| 事件 | 当前状态 | 实际进展和剩余边界 |
| --- | --- | --- |
| E00 基线与度量 | 维护者已接收 | 输入/证据/保护/统计已核对；旧 dirty 已完整保全，再恢复执行记录角色及有效索引。 |
| E01 入口与配置 | 维护者已接收 | 四任务共用正式解析与请求；Position candidate 和两个旧 PickCube physical UID 已退休；范围外 component 不进入这四条正式链。 |
| E02 模块与主体 | 维护者已接收 | 共同 builder 消费 source、主体和 Controller 阶段；复用 CompiledReferenceTaskV1 与具名 context，去除 20 种阶段临时字典键；合法 typed lowerer 差异保留。 |
| E03 Env 生命周期 | 维护者已接收 | 共同 reset/fault/close、source lease/cache、worker/App/camera owner 已按受影响范围核对；保留真实失败注入未测边界。 |
| E04 控制与推进 | 维护者已接收 | 当前支持输入进入共同 dispatcher/submission；兼容提案以显式投影和类型策略决定行为，错误阶段不再决定控制路径。 |

本版本诊断集中在 `task_env/diagnostics/tasks/v2.1.1/`。E00～E04 主审余项修复轮的 217 项受影响 source/caller 检查通过，另有 76 项纯/fake 精确检查通过（与前者有重叠，不相加）；六项 USD 检查为真实 delivery 的离线构造，不启动 Isaac App。MuJoCo 七条短程共 75 个显式子步，GeoPhys effort/Pendulum 两条短程通过；加上测试中的 40 个，本轮共 115 个显式 MuJoCo 子步。冻结输入为 `e25f37c5` 加保存的生产 patch，与 `912416e6` 对应生产字节相同，运行的 source_revision 仍为 e25，不改称提交后重跑。详情见[按模块压缩的实施记录](../planning/post-5c-optimization-execution.md#6-e00e04-实施记录)。renderer 未重跑，完整 Solution 仍留 E13；旧逐批记录从历史提交和原始输出恢复。

O5 对应的五条完整运行与同次读回及其开放边界见下方 E11～E16；O6 独立主审与维护者代码接收及 O7 项目清理和有界接收均已完成。[capability-matrix.json](../capabilities/capability-matrix.json)分列当前有界证据与历史目标；本地develop已按本次授权同步G05及优化成果，main／远端未同步，未发布。

## E05～E10：维护者已接收

E05资产/source、E06 physics adapter、E07状态/相机、E08 renderer、E09 Task精简和E10 Recorder/replay已按[专用账本](../planning/post-5c-e05-e10-remaining-ledger.md)完成，[实施Goal](../planning/post-5c-e05-e10-goal.md)保留为历史提示，不再作为下一执行包。[结果和证据](20261113_e05_e10_u7_delivery.md)及[独立主审](reviews/20261113_e05_e10_independent_review_d9dc02c6.md)覆盖S01～S40，生产小修 `7a098423` 删除physical Recorder的PickCube语义覆盖并验证声明保全；维护者于2026-11-13明确接收。后续完整Solution已按E11～E16的U3/U4有界核对，项目整理与最终接收见下。


## E11～E16：维护者有界接收

以[E11～E16细化账本](../planning/post-5c-e11-e16-remaining-ledger.md)及[实施Goal](../planning/post-5c-e11-e16-goal.md)记录七个大单元、44个检查点及其证据；维护者已按[接收记录](reviews/20261114_e11_e16_maintainer_project_acceptance.md)对 `86921c62` 及明确限制作有界项目接收。

规划时输入`a6b107ac`，tracked clean，四保护输入和pins不变；规划轮仅作静态及只读盘点。随后 U1（`d0c25ae4`）和 U2（`1ff617d0`）完成实施自评；U3 检查点 `5742e956` 记录五条完整运行、同次读回和受影响修复。四保护输入及两 pins 在 U3 后仍一致。规划时主 maintenance 约84.46GB、旧 integration 的 workspace 约13.79GB 均为混合总量，不是可删空间承诺；9 个本地 heads、6 个 worktree 须在处置时重新核对，当时 Harness 共享锁位于历史大目录；后续锁已按现行合同收敛。

E13 的四条 CPU 完整运行与后续 Isaac `solution-002` 均已记录任务成功及同次 caller Solution 完成；原 Isaac 失败保留在[U3实施结果](reviews/20261113_e11_e16_u3_solution_evidence.md)。维护者同意的[同次联合证据](reviews/20261113_e11_e16_u4_joint_completion.md)已完成离线核对，四条 canonical H5 completion 字段不存在，新 Isaac 字段为 null；H5 单文件不自含完整 completion，独立复审已支持该有界结论。E14 文档与代码范围已按维护者本次条件授权[有界接收](reviews/20261113_e11_e16_u4_independent_acceptance.md)；该段为 U4 接收时点；其后 E15/E16 按具体清单保全、归并、安全清理和恢复，项目优化现已由维护者有界接收；不自动 merge/push/tag/发布或进入 G06。详细检查点、接收 owner 和操作边界均在专用账本。

2026-11-14项目整理进展：U5有界证据归并已完成；integration此前Git移除部分失败，现按维护者续授权完成残留及旧stage5分支清理，当时6个本地heads、5个注册worktree。删除前剩余文件逐项与快照／Git对象核验，删除后240项纯/fake、25＋8项离线H5和七项包检查通过，四保护SHA及pins未变。约15.4 GB临时快照仍保留；其精简、当时其他worktree处置、历史累计净空间及U6/U7项目接收在该时点仍未完成。[当前处置与收尾证据](reviews/20261113_e11_e16_u6_directory_disposition.md)记录了前次Git管理元数据未完整保全的限制，不将本次清理写成完整恢复或整轮项目接收。

2026-11-13 Isaac 夹爪专项返工补充：原 U3 的失败结论按原冻结输入保留。[后续物理对照与修复](reviews/20261113_isaac_gripper_rework_ef10e348.md)确认空载可近零闭合、碰撞方块50 mm，约53.6 mm夹持下可以抬起并保持；原45 mm就绪门阻止了Solution试举。Task现在输出v2稳定关闭读回，Solution连续稳定50 ms后尝试抬升，100 mm成功判据和物理参数不变。相同seed31／1000 horizon的正式Isaac Solution已于951步完成、lift105.254 mm，H5独立读回4755个显式子步及关闭回执成立；腕部RGB有单独430步／431帧控制对照。H5 completion仍为null，U4接收依据独立复审及同次联合证据，而非该专项自行替代主审。

2026-11-14阶段性记录：维护者批准三处停用工作树的[集中清单及具体例外](reviews/20261114_e11_e16_three_worktree_decision.md)，完成 camera、core-baseline 和旧版 clean checkout 的 Git 移除；保留主checkout与冻结archive。该时点尚待T35收敛和快照处置，后续状态见下；各次测量及恢复限制保留在[原执行结果](reviews/20261114_e11_e16_three_worktree_execution.md)。

E15 项目停门时：[E15 最终清理与独立复核](reviews/20261114_e15_final_disposition_execution.md)已完成维护者批准清单；同序含 U5 和分类日志的范围下降 29,109,616,640 B，保留两项原位例外。U4/U5 不重开；维护者已接收 [项目接收入口](reviews/20261114_e11_e16_u7_project_acceptance_entry.md)所列边界及交付 `86921c62`。旧 Git 管理元数据损失、历史精确净额 UNKNOWN、同次 completion 及不可见进程限制保留；其时 G06 尚未启动。

2026-11-16后续公共控制修复：默认GeoPhys canonical worker、共享物理端口和MuJoCo受约束source dynamics／physical reset切换已完成定向实施与验证，见[worker记录](20261116_worker_physical_followup.md)。本项不启动G07，不改变原G06 abc接收范围。
