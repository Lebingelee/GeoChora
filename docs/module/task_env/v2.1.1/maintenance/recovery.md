# v2.1.1 恢复与当前状态

更新时间：2026-11-05。按[协议确认收据](20261103_protocol_baseline_confirmation.md)、[执行表](../planning/execution-and-acceptance.md)及本页恢复当前状态。

## 3a attempt001 已返包，待 Sol 独立复审

维护者已指定 Terra 执行 `V211_G03_3a_attempt001`，当前状态为 `REPORTED_PENDING_SOL_REVIEW`，不自动进入 3b。预检发现普通 PickCube／Nut 缺可验证的 MJCF 资产闭包回执，当前 reset 会拒绝，兼容性门未通过；不得将离线替身结果当成真实后端运行。详见[执行摘要](reviews/20261105_3a_attempt001_execution.md)及 ignored 输出目录的完整报告。

## 历史：新Sol接手时3a完整包已准备，尚未派发

Sol已完整核对交接及必读资料，实际Core输入与`develop@9d942d43`快照一致，两份保护untracked及子模块pin不变。只读核对未发现新的3a在途包／writer；旧Terra前置窗口已有完整返包和释放声明。已fetch核对public/develop，本地develop领先236、落后0；从完整本地develop建立`codex/v211-stage3`，3a–3c共用当前checkout，新增worktree为0。develop保留原交接HEAD，无reset/rebase或推送。

首份`V211_G03_3a_attempt001`已准备，由维护者指定一个Terra／Luna并手动转发。准确输入HEAD、保护字节和成员摘要在外部包snapshot／manifest冻结；[3a实施安排](../planning/stage3-3a-execution.md)记录当前源码落点、缺口、预算与出口。3a–3c仍PLANNED／attempt0，active_packages为空；未启动实施、native、subagent或后续子阶段。准备不计attempt，不因已有G03等待对话而重复派包。

原[交接检查点](20261105_stage3_sol_handoff.md)保留交接准备时事实。当前动作是等待维护者指定并转发完整3a包，完整报告与writer释放后Sol独立审阅，不自动进入3b或阶段4。下文旧“分支尚未创建”等描述按其历史时点理解。

## 当前决定：前置核心收尾已有限接收

维护者最新安排：先落实[诊断与代码边界规范](../../../../global/diagnostics-and-code-boundaries.md)，本轮不再全面解耦。后续环境、Controller、provider和renderer开发从外部诊断，不向核心新增实验／测试分支；现存已确认耦合登记在[规划第2.6节](../planning/pre-stage3-environment-refactor.md#diagnostic-policy-and-final-cleanup)，在版本准备进入7a集成时集中处理，并在稳定源码上验证。有限接收不表示诊断完全隔离，规则更新也不表示代码已整改。规范已落地；目前G03只完成分支与首包准备，尚未启动实施。

`V211_PRE_STAGE3_CLOSEOUT_120MIN_001`返包`99de88abd6d3f464de0d5c9c98362813f52252c9`经[Sol复审](reviews/20261105_pre_stage3_closeout_120min_sol_review.md)，决定 **ACCEPTED_BOUNDED_PRE_STAGE3_CORE_CLOSEOUT**：C1核心职责、C2当前文档、V受影响行为在限定范围通过，本次前置核心收尾结束，不再追加持续拆分窗口。runtime不依赖具体Nut Solution，任务侧保留检查；R05b普通reset不持有Solution，兼容Expert按需创建。Sol独立R05b检查25 passed／1 deselected，核对执行者182 passed／1 deselected及Nut物理／同次reader结果，并接受有调用链差异依据的PickCube和Nut证据复用。详见[原返包](reviews/20261105_pre_stage3_closeout_120min_001.md)。

真实R05b provider、新安装及其他未验证能力继续保留限制，环境类更广整理不等于已完成；它们不重开本次限定收尾。阶段3分支和首份3a包现已另行准备，见本页顶部；尚未派发实施。以下派包计划与旧记录保留当时身份，不覆盖本段接收决定及顶部的新接手状态。

## 本次收尾的派包记录（历史）

维护者要求回到原环境重构与开发指引目标，最多再用两小时。最新源码检查点为`develop@dba855e1ad9575d21604304dc04e9f7fc036ad7e`，tracked clean，两个保护untracked保留；整体维护待Sol复审，G03未开始。最后窗口以[规划第2.5节](../planning/pre-stage3-environment-refactor.md#pre-stage3-closeout-120min)为当前执行范围：C1任务／Solution与Env/runtime职责、诊断隔离；C2当前`task_env/doc`和真实example；V只验证实际受影响行为。已接受生命周期不重做，不再逐helper拆分或逐提交重建全套证据。

`5a04140a`的PickCube31／Nut19 MuJoCo成功和独立reader已有记录；至`dba855e1`仅五个文档文件变化，允许按原运行身份引用并注明运行代码未变。旧任务短检查按其各自来源和调用链另判，不将新文档HEAD视为全部证据自动失效，也不冒充新run。证据入口见[当前状态](reviews/20261105_pre_stage3_current_status.md)。下文各次NOT_RUN／PARTIAL与预算待答复描述均保留所属历史检查点，不能覆盖本段当前入口。

两小时包含实现、必要验证、文档、提交与返包，到时无条件停止新工作并释放窗口；核心未过门就列具体阻塞，不自行延期，不自动接收或进入阶段3。包由维护者手动转发，Sol本次仅准备规划与prompt，未启动执行。

## 状态

- G01/1a–1d 和 G02/2a 的既有 Sol 决定保留。
- G02/2b attempt_count仍为2。attempt002在原验收包中为G2 FAIL、G3 PARTIAL；维护者于完整报告/manifest提交前暂停，G5为`INCOMPLETE_USER_PAUSED`。2c整理不能倒填或改写这些历史。
- Sol现以 `ACCEPTED_BOUNDED_STAGE2_REFERENCE` 接收2a归因、2b MuJoCo代表实现与2c成功参考冻结，阶段2收尾。此决定不把旧2b扩展包改为全通过。详见[阶段2主审](reviews/20261104_2c_sol_review.md)、[2b中止记录](reviews/20261104_2b_closeout.md)和[2c参考](reviews/20261104_2c_reference_freeze.md)。
- 本窗口`V211_G02_2c_attempt001`只封存现有文档和成功参考，未启动native、pytest、reader、GPU probe或provider import。当前2c状态为 `ACCEPTED_BOUNDED_2C_REFERENCE_FREEZE`；阶段3未开始。

## 证据边界

PickCube seed31 MuJoCo CPU主参考为960 transitions成功、lift 0.10518958081676949 m、task门限0.10 m，独立reader通过。NutAssembly seed19两次独立运行均2377 transitions成功。PickCube seed32在固定horizon1000以0.08261901333725602 m lift失败；保留HDF5与reader，不增大horizon、不放宽oracle。GeoPhys PickCube失败于Solution stale-execution-time guard，control_step=3，具体两侧时刻和完整HDF5缺失。Isaac冻结delivery校验通过，但未有App/native运行。

完整人工阶段2时间线存于主工作区 `/home/lly/Documents/ChatGPT/GeoChora v2.1.1/execution-output/V211_manual_analysis_stage2_summary_001/report.md`；用户暂停时的进度报告为 `/home/lly/Documents/ChatGPT/GeoChora v2.1.1/execution-output/V211_stage2_progress_report_20261104.md`。这些是工作区外于Core checkout的文件，特以原路径列出。attempt002原始H5、trace、失败记录与helper留在ignored `workspace/maintenance/v211_g02_2b_attempt002/`；不恢复、搬迁或覆盖旧运行。

## 阶段3前维护检查点

attempt001及维护者授权续作已返包，最终执行HEAD为`656ef136`。Sol独立复审决定`REWORK_REQUIRED_PRE_STAGE3`：保留部分实现作为后继基线，G1 FAIL、G2–G4 PARTIAL，整体未接受。目录四文件及原字节manifest迁移已核对；三个classic任务真实统一、Marker通用构造回收及F06任务／runtime职责分离仍待整改。最终源码物理与独立reader未验证。见[Sol复审](reviews/20261104_pre_stage3_attempt001_sol_review.md)和[执行者交付](reviews/pre-stage3-refactor-attempt001.md)。不改变阶段2决定或启动阶段3。

attempt002 的 30 分钟 R1 返工已记录在[返工交付](reviews/pre-stage3-refactor-attempt002.md)：scalar episode 部分状态与准入已共用，classic／selected 的完整生命周期和 Env 类仍未统一，RW1 为 FAIL；原生验证未运行，仍待 Sol 复审。

### 2026-11-05 生命周期续作

后续职责去向、原功能调用者及当前文档处置见[职责与文档清单](reviews/20261105_pre_stage3_owner_and_document_map.md)；该清单是待复审检查点，不表示整体维护已接受。

维护者授权更长的三个单环境修复，提交为 `4840152530e55fb8a3e77517c3b187e99647b5b7`。Sol 已作[独立复审](reviews/20261105_lifecycle_unification_sol_review.md)，决定 `ACCEPTED_BOUNDED_LIFECYCLE_UNIFICATION`：R1 的真实源码迁移与无引擎契约有限接收。四个 `BaseTaskEnv` 出口与 `SelectedReferenceEnv` 为同一类对象，三个组件任务及 selected 路线通过共同 episode owner 执行 reset、step、stop 和 close；组件 RuntimeBoundary 和 selected RuntimeSession 保持各自物理接口。Sol 独立复跑171 passed／3 deselected和12 passed；真实 provider、物理和独立物理 reader 未运行。整体维护仍为 PARTIAL，R2/R3等后续项和阶段3均未获本次整体验收。原[Terra 交付记录](reviews/20261105_lifecycle_unification_terra.md)及历史30分钟结果保留。

2026-11-05后续goal在上述复审之后继续实施，至 `f37dec92` 的源码与文档检查点均待Sol复审：Marker公共组装、F06受信声明、部分task／recorder职责、Nut cadence诊断隔离和R05b源码身份准入均有实现。PickCube普通CPU、Position/F06、内建与通用candidate的调用方动作接线已迁移；Position/F06新路线仅有合成证据，真实Isaac未运行。通用candidate合成oracle预检因两份保护untracked触发clean-check，尚未通过。完整记录及失败边界见[续作检查点](reviews/20261105_pre_stage3_continuation.md)。

当前待处理状态、资源上限违规及待维护者决定事项汇总在[待复审检查点](reviews/20261105_pre_stage3_pending_handoff.md)；该页不是最终返包或验收。

其后续作至 `8416ef49` 的源码与文档仍待Sol复审；当前逐门证据与未完成项见[验收门核对草稿](reviews/20261105_pre_stage3_gate_audit.md)。该草稿不是最终交付或Sol决定，后续源码变化须重新核对适用范围。

已有受限物理证据：`fa885280` 的Empty／Pendulum／TwoWheel GeoPhys CPU各单步与close；`f9cb51fd` 的PickCube MuJoCo CPU seed31调用方驱动回归及同H5独立reader。结果只对应各自源码，后续源码不自动继承这些物理结论。Nut完整物理回归与独立物理reader仍为NOT_RUN；原生步数预算问题已向维护者提出，尚待答复。整体维护仍为PARTIAL，阶段3未开始。

维护者计划后续从 develop 建立阶段3分支；目前尚未创建新分支或 worktree，也未启动3a。正式执行前固定起点提交、独立工作目录及与后续维护的接口边界；旧编排中的零新增分支方案届时按维护者新安排更新。

## 阶段3前待办

[维护方案](../planning/pre-stage3-environment-refactor.md)涵盖环境归整、诊断隔离、Env统一、静态SHA优化，以及新手安装／已有路径复用／启动脚本／example二次开发指引。交付位置包括README、`task_env/doc`和本版[指南](../guides/README.md)，不能只更新GPT工作文档。已有部分代码与启动入口检查点；完整重构、新安装及启动入口的 native 验证尚未完成。

Pendulum本次先完成单环境规范路线；统一Env并行尚未适配，交G06后续实施。旧并行注册／脚本及历史证据不改写，不因此要求本次追加并行native或训练检查。阶段3–7状态保持不变。

## 历史返工范围：30分钟

维护者已指定30分钟硬窗口。本轮只优先修复生命周期统一R1；Marker简化、F06职责整理及不受影响的文档诊断优化延期，不因这些事项继续延长窗口。见[规划优先级](../planning/pre-stage3-environment-refactor.md#24-维护者指定的30分钟返工优先级)。本轮无native／GPU／完整物理reader预算，现有物理证据边界不变；新包为`V211_PRE_STAGE3_REFACTOR_attempt002`，准备后由维护者转发，不自动启动或进入阶段3。

## 保护项和停止点

- `MUJOCO_LOG.TXT` SHA-256 `dfb37ada202855d609f9e210cf79b287de78f2ded70e704ceeb544d17bf7ad4b`。
- `docs/maintenance/20261030_runtime_route_diagnostic_handoff.md` SHA-256 `18cc56c7f0ffbcb947db4bd8725279489171efbee8f08b28603b79c47f509d61`。
- 两项保持untracked；不stage、不删锁文件、不清理raw。
- attempt001和attempt002窗口已释放；2026-11-05较长续作的实际完成和窗口释放以本次报告为准。不得干扰其他用户的原生运行。本项不授权新的三后端九格、2b attempt3、Isaac native或阶段3。
