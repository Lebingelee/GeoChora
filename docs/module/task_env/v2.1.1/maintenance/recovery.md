# v2.1.1 恢复与当前状态

更新时间：2026-11-05。按[协议确认收据](20261103_protocol_baseline_confirmation.md)、[执行表](../planning/execution-and-acceptance.md)及本页恢复当前状态。

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

维护者授权更长的三个单环境修复，提交为 `4840152530e55fb8a3e77517c3b187e99647b5b7`。Sol 已作[独立复审](reviews/20261105_lifecycle_unification_sol_review.md)，决定 `ACCEPTED_BOUNDED_LIFECYCLE_UNIFICATION`：R1 的真实源码迁移与无引擎契约有限接收。四个 `BaseTaskEnv` 出口与 `SelectedReferenceEnv` 为同一类对象，三个组件任务及 selected 路线通过共同 episode owner 执行 reset、step、stop 和 close；组件 RuntimeBoundary 和 selected RuntimeSession 保持各自物理接口。Sol 独立复跑171 passed／3 deselected和12 passed；真实 provider、物理和独立物理 reader 未运行。整体维护仍为 PARTIAL，R2/R3等后续项和阶段3均未获本次整体验收。原[Terra 交付记录](reviews/20261105_lifecycle_unification_terra.md)及历史30分钟结果保留。

2026-11-05后续goal在上述复审提交后继续实施，当前检查点至 `eaebe344`：Marker公共组装、F06受信声明及部分task/recorder职责调整均待Sol复审；Nut cadence诊断接线迁至diagnostics。R05b旧源码身份准入失配已针对当前源码刷新，并保留精确字段及来源检查；真实源码路径核验加合成会话为14 passed／1 deselected，不是物理或GPU成功。其中 `fa885280` 已通过Empty／Pendulum／TwoWheel的GeoPhys CPU单步与close，受限于该源码和场景；完整记录及失败边界见[续作检查点](reviews/20261105_pre_stage3_continuation.md)。整体维护继续PARTIAL，`f9cb51fd`的PickCube MuJoCo seed31调用方驱动物理回归及同H5独立reader通过；Nut必要完整物理回归与独立物理reader仍为NOT_RUN；阶段3未开始。 后续 `a1971ebb` 已为PickCube Position/F06和内建Harness接入调用方动作，仅有合成证据，实际Isaac未运行；该源码的生命周期离线回归176 passed／3 deselected，R05b来源与synthetic组14 passed／1 deselected。

维护者计划后续从 develop 建立阶段3分支；本次仅完成复审，尚未创建新分支或 worktree，也未启动3a。正式执行前固定起点提交、独立工作目录及与后续维护的接口边界；旧编排中的零新增分支方案届时按维护者新安排更新。

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
