# G07／7a attempt002 独立有界主审与7a收尾

日期：2026-11-17。结论 **ACCEPTED_BOUNDED_7A**。按维护者“收尾7a、准备7b”的指示，规划主审结合独立代码/证据复核接收本包 A3/A4 及指定旧资产分支整合；连同[此前维护者已接收的A3之前范围](20261117_g07a_attempt001_partial_acceptance.md)，7a 有界关闭，普通 attempt 数为2。不是新 Qualification，也不将未测组合改为维护者已接收。7b仅准备，attempt0；7c仍PLANNED/0。

## 身份与审阅依据

审查实际生产 HEAD `0a6213c040e06e6385b6d1f5509af34a8d5b8372`，阶段分支 `codex/v211-stage7-integration`；旧资产来支冻结 `3da60b74fa8918f996d5abc4a3f93780c67b5d5f` 的本地合并为 `94e865e3cd272f5c8c5b8ca8892799270457cc84`。GeoPhys pin `198d30ac64ce873a1467f55d2adfc471db18fbc5`，Menagerie `b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`。主审不修改生产源码。

完整返包：[report.md](../../../../../../workspace/maintenance/v211_g07a_attempt002/report.md)。冻结的原包见[工作包索引](../work-packages/20261117_g07a_attempt002_goal.md)。主审读实际diff/公共caller和原始H5/trace/关闭/资源，而不从执行者PASS自动推导接收；两名独立只读复核分别检查生产调用链和原始证据，另一名核实后续7b/PR边界。定位先CodeGraph，漂移处核实际符号；未重建索引。

## 逐项决定

| 范围 | 独立复核与结果 | 限制 |
| --- | --- | --- |
| 旧资产分支整合 | 当前阶段本地merge及source/监督/TaskHarness冲突裁决保全正式owner，无第二TaskEnv/Runtime | 不含后来PR #3；不部署setup/服务/模型或用户MCP配置 |
| A3 canonical默认链 | `native-033/bundle` 同run七个非零N*m请求、admitted efforts、真实mujoco-qfrc-applied ACK、1/2边界、25子步、H5独立读回和完整close关联；`native-040`另证明同Controller二次reset、新episode、clock归零 | 033与040分别证明各自事实；040未存raw close字段，不能借用033关闭回执 |
| A3空载pose Controller | task1公共builder/正式配置，source绑定的本体模型/世界TCP与typed effort ACK；scratch计算不推进物理。匹配保持输入的历史OSC对照，四项冻结指标均改善，见下 | 20Hz effort hold与历史500Hz重算已明示；不是完整OSC复刻或所有模型/Controller等价 |
| 正式LIBERO caller及A4 | `native-023/bundle` 64/65同run H5及独立读回、正常关闭；`osc-selected-006`也各自在本run关联source/closure/episode/reset/materialization、64/1600/3.2s和释放 | task_success=false，solution_completed=null；不宣称LIBERO任务成功或Solution完成 |
| 7a已接收AP影响 | `native-037/038`分别原/装配Panda共同构建、reset和一次R3 step/close；实际VFS/source改动影响有界检查通过，原四个MuJoCo完整任务交集沿已接收证据 | 短测不替代完整Solution；Nut MuJoCo1mm/GeoPhys8mm不变，GeoPhys当前源码未重跑 |
| 架构/可读性 | bench留来源/任务语义/配置薄绑定；共享模型/控制/scene/session/recording归TaskEnv原owner；保留source freshness、公开状态与ACK/close，未因diagnostics名称删有效能力 | 按[G07约束](../../goals/07-integration.md#g07-code-constraints)与已结案[总账](../../planning/post-5c-code-project-optimization-diagnostic-ledger.md)审查，不要求所有owner产生diff |

默认链033的H5、runtime_progress与raw final_session_close_receipt五项身份逐项匹配，control1/native25/reset1，session/model/data释放为true；040只作为reset补充。selected006和023各自同run关闭身份、control64/native1600/3.2s成立，不拼接不同run闭环。原包针对性检查和失败记录按返包逐项保留，不把重叠测试数相加。

## 主审补证：消除非被测手指保持输入混杂

原参考每子步opening=.04，对应双指±.02m；selected按同一reset保持±.020833m。掌部TCP运动学不直接依赖两指，但质量/阻尼/armature可影响整臂动力学，不能直接假定零影响。主审仅在新的 ignored `review001/` 外部probe中将历史参考opening改为reset两指位置之差；生产源码、历史Controller、source/初态、arm增益、TCP targets、64边界/1600子步、采样窗口和原不退步判据均保持。

这是本次独立审阅的最小补证，不重开已结束的执行Goal、普通attempt或原4h窗口。事前[freeze.json](../../../../../../workspace/maintenance/v211_g07a_attempt002/review001/freeze.json)单独冻结15分钟总审阅补证上限、120秒native和1600子步。第一条supervisor启动缺少外层PYTHONPATH，在child启动前失败，0子步；保留launch001失败后，用显式Core环境执行未变supervisor。

补证实际1600子步、21.094秒监督墙时、进程树峰值RSS 2,483,163,136 B，无强制清退或资源超界，正常close。独立离线重算如下：

| 原冻结指标 | 同保持历史OSC | 原selected006 | 结果 |
| --- | --- | --- | --- |
| 最大位置误差 | 7.899763mm | 7.272765mm | 改善 |
| 最大姿态误差 | 0.01763035rad | 0.01676356rad | 改善 |
| 各段末四步最大位置误差 | 0.104010mm | 0.047846mm | 改善 |
| 各段末四步最大姿态误差 | 0.00046578rad | 0.00011458rad | 改善 |

[独立复算收据](../../../../../../workspace/maintenance/v211_g07a_attempt002/review001/independent-comparison.json) SHA256 `05236221eaaa83a23584a684818dd7ad74740a37cac0d16b69b249cd1c4cb9c3`。目标/时钟/窗口、参考close↔progress及selected close↔H5/context/progress均核对一致。没有扩大到独立夹爪控制/抓放门，原不匹配保持值的比较记录亦完整保留。

## 预算、释放与后续

原attempt002执行窗口约97分钟，授权重置后的显式子步独立合计16,460；native009 supervisor漏记的25由其原child结果补计。52次监督窗口合计223.719秒，峰值树RSS约2.48GB；早期native001监控缺口继续记失败。主审新增1,600单独记账，合计可见18,060，不改写原窗口时长/消耗。释放核验见[release-receipt.json](../../../../../../workspace/maintenance/v211_g07a_attempt002/review001/release-receipt.json)：补证进程已退、canonical共享锁可重新取得并释放。

保护日志仍239 B，SHA256 `3b08b858f62dcbaa6521802455c76126f9876a3d6727c7586db90c94296ed6a8`。文档validator既有保护基准差异单独报告，不能为其修改日志。没有重跑GeoPhys/Nut、原全部AP、G06性能或A123；worker R1-split、learner CUDA/autoreset、LIBERO其他task/provider/独立夹爪/切换等旧边界保留。

维护者新指定[PR #3](https://github.com/Lebingelee/GeoChora/pull/3)冻结 `23387a9cffd82fe02fb69fb5d2993141fdd54ae9` 的本地合并归7b，不能倒写成7a已完成内容。7b先整合/必要修复、再冻最终输入，原三后端×31/32/33九格及独立门不变。参见[7b工作包](../work-packages/20261117_g07b_attempt001_goal.md)，当前准备未启动；不自动进入7c或发布。
