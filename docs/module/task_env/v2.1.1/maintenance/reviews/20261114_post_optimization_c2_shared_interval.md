# C2：selected interval 共同后处理

输入 `f686acb0`，本地阶段分支。C1 结论及 E00～E16 有界接收不重开。本单元保留 `EpisodeExecutionState`、Controller、`submit_control_command`、Runtime session 与 Recorder 原有 owner；C3～C5 和最终复验仍未完成。

## 调用关系和实际收敛

| 阶段 | physical | Position profile | reference |
| --- | --- | --- | --- |
| 提交／推进 | typed effort batch 或 sequence 由既有提交 owner 准入；`advance` 调 session.step | Position interval 在 `apply_control` 内完成提交及推进；`advance` 解包 | canonical Position target 通过同一提交 owner；native feedback 或 boundary-hold 各按原合同推进 |
| read／evaluate／observe | V2／可选 V1 读回并核对边界；任务 observation 与 physical receipts | interval 提供 typed state；任务 observation 与 sequence/gravity 信息 | state、feedback、任务 observation 与 readiness/native interval 信息 |
| Solution／record／publish | finish_step 后观察 Solution；active physical Recorder 追加后发布 | finish_step 后观察 Solution；Position／dual Recorder 追加后发布 | Solution 观察后 `finish_step(preserve_stop=True)`；canonical／execution Recorder 保留原记录和相位 |

`execute_selected_interval` 在现有 `EpisodeExecutionState` 中统一从同一个 Env 读取已推进 state 与已评估 obs，再复用原 `execute_interval` 的六阶段、failure handler 和 phase；三类 selected 路线及 physical sequence 均由生产 `step`／`_step` 实际进入，组件路线仍使用其自己的 snapshot hooks。四处 state/obs 回调装配收敛为一处；Evaluation 的 provider 读回与 Recorder 的 typed 数据不同，保留各自实现，没有新推进者或第二状态。

三个 Solution 分支共用 Env 的 `_observe_selected_solution`，只负责一次 observe、按调用方原先策略读取 outcome_report、发布完成／失败事实。physical 在 finish_step 后调用且不读取 report；Position 在 finish_step 后调用并保留原始 info／扩展；reference 在 finish_step 前调用并保留 Solution stopped 状态。每个原始 fault phase、Recorder append 前后顺序不变。

`control_submission._resource_owners_from_rows` 统一原 canonical source 声明和提交侧三个 binding 检查中的同一 writer/resource 纯值投影。source 与已物化 plan 依然独立输入并比较，缺失 writer 和重复资源不会被去重隐藏；身份、clock、generation、scene 资源冲突、replay 与 lowering 检查保留。Position、effort 和 wrench 仍是各自 typed 命令。canonical target 中独有的实际 session clock、source 及 lowering 仍由其原路径装配。

## 验证与边界

- 正式 pure/fake guard：**258 passed**。新增的真实 dispatcher＋fake terminal 检查覆盖 physical 单次写入／推进／Solution observe、重复提交拒绝、observe 与 Recorder append 失败；后两者确认 interval 已完成且 fault 锁存，append 失败为 rejected。Position fake 覆盖 Recorder 失败不发布新边界。selected interval 检查绑定当前 state/obs 和原 evaluation failure phase。fake terminal 不证明 native 读回。
- 提交合同中 materialized plan、writer generation、subject、资源冲突及 replay 的 5 个定向受守卫节点通过。整份历史合同文件 21 passed、1 failed：旧 split fixture 使用不再符合当前组件输出类型，实际较早被类型拒绝，未恢复旧接口。旧 R04a 文件因已退役 candidate builder 无法收集；相应 Position 记录失败的当前 fake 已迁入版本 diagnostics，不声明旧文件通过。
- [锁内 MuJoCo 短程计划](../../../../../../workspace/maintenance/v211_c2_shared_interval_20261114_001/plan.json)：Pendulum、TwoWheel、PickCube、Nut 与 assembled split 各完成 reset、非零 step、再 reset 和重复 close；显式子步依次 25、25、5、5、5。PickCube/Nut 执行一次 Solution 调用，split 核验两个 writer。physical reset-switch 首次跑完两段物理后因诊断脚本误从 step info 读取 reset-only schema 而失败；保留失败收据，修正诊断读取时点后按[新计划](../../../../../../workspace/maintenance/v211_c2_shared_interval_20261114_002/plan.json)重跑 PASS、10 显式子步、一次 caller-owned Solution observe、重复 close 和锁释放。
- [五份新 H5 正式 reader 读回](../../../../../../workspace/maintenance/v211_c2_shared_interval_20261114_001/readback.json)，各一转换、两个边界；physical 记录的是切换前一转换，切换后 Solution 调用由同次 probe 结果另记。Nut execution 读回 5 个 2 ms 子步。短程 external_stop、任务成功、Solution completion、图像和 close 各为独立事实，不能称完整 Solution 成功。后续 C5 要求的 PickCube/Nut MuJoCo 完整 Solution 尚未执行。
- 未重跑 GeoPhys／Isaac 或采图；三条 provider 对应旧证据继续保留原源码身份与原有接收边界。旧 H5 和历史输出未改写。受影响的最终路线及 reader 在 C5 集中复验。

## 度量和原账回看

四个生产文件合计 `+48/-53/net -5`，其中 writer/resource 投影约 7 行由 Env 移到现有提交 owner，属于迁移，不计作删除。Env 4,254→4,244 行；physical、Position、reference 准备函数分别 298→296、180→172、322→310 行；lifecycle 1,467→1,472 行，control_submission 1,218→1,218 行，physical_sequence 228→228 行。新增一个 selected interval 调用跳转和一个 Solution 回调跳转；没有新增状态、Controller、物理 session 或布尔分支树。版本诊断／probe 现有文件 `+177/-5`，是验证和诊断修复，不能计入生产精简；本记录及计划状态为文档变动。

回看原总账 ENV-03、CTRL-02／04／05、RUN-03、REC-01：本次改变共享 state/obs 挂接和 Solution 事实发布位置，以及声明 writer 纯投影；控制计算、native 提交、唯一推进、按路径记录及失败事实仍由原 owner 执行。此前有界结论不因本次重构自动扩展，最终影响复验留 C5。未清理目录／refs、merge、push、tag、发布或启动 G06；冻结 archive 与保护输入保持。
