# v2.1.1 恢复与当前状态

更新时间：2026-11-04。按[协议确认收据](20261103_protocol_baseline_confirmation.md)、[执行表](../planning/execution-and-acceptance.md)及本页恢复当前状态。

## 状态

- G01/1a–1d 和 G02/2a 的既有 Sol 决定保留。
- G02/2b attempt_count仍为2。attempt002在原验收包中为G2 FAIL、G3 PARTIAL；维护者于完整报告/manifest提交前暂停，G5为`INCOMPLETE_USER_PAUSED`。2c整理不能倒填或改写这些历史。
- Sol现以 `ACCEPTED_BOUNDED_STAGE2_REFERENCE` 接收2a归因、2b MuJoCo代表实现与2c成功参考冻结，阶段2收尾。此决定不把旧2b扩展包改为全通过。详见[阶段2主审](reviews/20261104_2c_sol_review.md)、[2b中止记录](reviews/20261104_2b_closeout.md)和[2c参考](reviews/20261104_2c_reference_freeze.md)。
- 本窗口`V211_G02_2c_attempt001`只封存现有文档和成功参考，未启动native、pytest、reader、GPU probe或provider import。当前2c状态为 `ACCEPTED_BOUNDED_2C_REFERENCE_FREEZE`；阶段3未开始。

## 证据边界

PickCube seed31 MuJoCo CPU主参考为960 transitions成功、lift 0.10518958081676949 m、task门限0.10 m，独立reader通过。NutAssembly seed19两次独立运行均2377 transitions成功。PickCube seed32在固定horizon1000以0.08261901333725602 m lift失败；保留HDF5与reader，不增大horizon、不放宽oracle。GeoPhys PickCube失败于Solution stale-execution-time guard，control_step=3，具体两侧时刻和完整HDF5缺失。Isaac冻结delivery校验通过，但未有App/native运行。

完整人工阶段2时间线存于主工作区 `/home/lly/Documents/ChatGPT/GeoChora v2.1.1/execution-output/V211_manual_analysis_stage2_summary_001/report.md`；用户暂停时的进度报告为 `/home/lly/Documents/ChatGPT/GeoChora v2.1.1/execution-output/V211_stage2_progress_report_20261104.md`。这些是工作区外于Core checkout的文件，特以原路径列出。attempt002原始H5、trace、失败记录与helper留在ignored `workspace/maintenance/v211_g02_2b_attempt002/`；不恢复、搬迁或覆盖旧运行。

## 阶段3前维护检查点

attempt001 在维护者确认已人工转交后续作，状态仍为 `REPORTED_PENDING_REVIEW`。已落实 Marker 公共创建入口、两个任务目录四文件收敛及相关 guard／Solution／USD 来源接线；本轮只有 provider-free 合成验证，Isaac 投影完整构建和当前源码完整物理回归未验证。classic 单环境统一仍未完成，G1 仍未通过；详见[交付与待复审](reviews/pre-stage3-refactor-attempt001.md)。此记录不改变阶段2决定或授权阶段3。

## 阶段3前待办

[维护方案](../planning/pre-stage3-environment-refactor.md)涵盖环境归整、诊断隔离、Env统一、静态SHA优化，以及新手安装／已有路径复用／启动脚本／example二次开发指引。交付位置包括README、`task_env/doc`和本版[指南](../guides/README.md)，不能只更新GPT工作文档。已有部分代码与启动入口检查点；完整重构、新安装及启动入口的 native 验证尚未完成。

Pendulum本次先完成单环境规范路线；统一Env并行尚未适配，交G06后续实施。旧并行注册／脚本及历史证据不改写，不因此要求本次追加并行native或训练检查。阶段3–7状态保持不变。

## 保护项和停止点

- `MUJOCO_LOG.TXT` SHA-256 `dfb37ada202855d609f9e210cf79b287de78f2ded70e704ceeb544d17bf7ad4b`。
- `docs/maintenance/20261030_runtime_route_diagnostic_handoff.md` SHA-256 `18cc56c7f0ffbcb947db4bd8725279489171efbee8f08b28603b79c47f509d61`。
- 两项保持untracked；不stage、不删锁文件、不清理raw。
- 阶段2窗口已释放；阶段3前维护 attempt001 以 `REPORTED_PENDING_REVIEW` 收束，具体 writer/native 释放和其他用户占锁状态以[交付记录](reviews/pre-stage3-refactor-attempt001.md)及工作报告为准。本项不授权新的三后端九格、2b attempt3或阶段3。
