# 阶段3前置重构：120分钟核心收尾返包

状态：**REPORTED_PENDING_REVIEW**。输入 `develop@f3650a7520e96e392758a9605d86d513c819a469`；实现源码 `b6ce23727f1b2cd21da15758785b59448eb9ceb0`；Nut 物理运行源码 `cf425acc6ab44e2180978ab88f7cf68d6168305f`。本报告和当前文档的后续提交只改文档／skill；最终输出 HEAD 为包含本报告的提交，由 Git 日志确定。2026-11-05 12:47:35（Asia/Shanghai）开工，13:00 前编写返包；未超过 120 分钟。已停止本轮 writer，worker 及双锁已释放，由维护者手动转交 Sol；不声明整项维护已接收或启动 G03。

## C1：核心职责

- 已完成 R05b 的直接依赖归位：`materialize_control` 不再导入 Nut Solution 类，也不要求接收 Solution；runtime 保留 R05b 的 source receipt、冻结 source／provider／时间、Controller 实例与配置、100／500 Hz、反馈及能力准入。Nut 既有 binding 在接收外部或兼容内置 Solution 时核对具体类型、冻结配置、时间、来源和 Controller 身份；普通 Nut／PickCube caller 的 `act → env.step(action) → observe` 方向不变。
- 本轮检查的上述核心默认路径没有反向导入 diagnostics；正式 Position／leaf／mixed 没有删除。Controller、任务、资产、reset 分布、任务判据和物理参数未改。Nut specialization 源码变化触发构造来源身份及 Controller 来源绑定身份变化，已按稳定源码重新固定两档 R05b Controller 身份；冻结 source closure、配置和实际 Controller 字段检查没有移除。
- R05b 的普通构造和 reset 不再创建 Env 持有的 Solution，调用方可执行 `act → step → observe`；`prepare_expert` 仍可按需创建并经任务 binding 校验，`reset_for_solution`／`step_with_solution` 保留为受限过渡接口。R05b 新 caller 路线仅做了无引擎验证，实际 provider 运行未验证。环境类仍有多路线编排，未逐 helper 拆分；不将该余项误写为已完成。此前 Sol 有限接收的单 Env 生命周期不重做。

## C2：当前文档和示例

- 更新 `task_env/doc` 的任务开发指南、Solution 与 Env 语义：用真实 Marker 示例逐项定位 UID／注册、声明／资产、reset、评价、动作／观测绑定和 task-owned Solution；继续通过 `task_env.make_env` 构造，不手写摘要或增加任务 factory。现有示例接线正确，未为缩短代码增设模板。
- 安装指南区分新克隆与复用现有解释器／SDK／资产，保留依赖冲突和未实测限制；`task_env/README.md` 补开发导航。更新 TaskEnv skill 对 R05b 的事实描述并通过 skill 快速校验。新克隆完整安装及 provider 安装矩阵未运行。

## V：受影响验证与证据复用

- 无引擎、禁止 native 导入：最终受影响组合 **182 passed、1 deselected**，包括 100／500 Hz 无 Solution 的 runtime 物化正例、任务侧错类型／身份／配置／来源／时间拒绝、错误 Controller、来源、五样本及反馈。excluded 的跨任务真实 provider 测试未运行，以及 caller action、边界、故障和清理。此前受影响组合 **236 passed、2 deselected**；这些较早结果保留各自源码时点，不重标为最终完整套件。
- 实现提交 `cf425acc` 的 Nut MuJoCo CPU seed 19、horizon 6000：**2377 transitions、2378 boundaries、任务成功**；同次独立 reader **PASS**，11885 native substeps、T+1、target／applied 身份通过，H5 SHA-256 `c8985c02448ab935e846c0f0330ff6c8389e4d5ed34ec3fc4703433be59d61e8`；reader 禁止并确认没有加载 native 模块。worker 墙时 58.958 秒，按序获取并释放两把共享锁，进程组退出。两者日志及结构化结果在 ignored `workspace/maintenance/v211_pre_stage3_closeout_120min_001/nut-physical/`。
- Nut 物理运行后 `b6ce2372` 只改 R05b 专用构造／reset、按需兼容及测试，不触及普通 MuJoCo 的 reset／控制／录制路径，但来源文件摘要随源码改变；不将本次物理运行重标到该提交。PickCube 本轮没有更改其 task、控制与实际执行分支；`5a04140a` 的 MuJoCo CPU seed31／960 transitions及独立 reader 证据按原源码身份复用，不重标到新提交。三个 classic 的运行分支未改，旧有证据仍按各自源码身份保留。没有运行 Isaac、GPU、其他新 provider、并行或训练；不因此推断 Qualification、D0 或其他任务成功。
- 物理步本轮保守预留 30000，总计 **287107／300000**；离线 pytest supervisor 本轮合计 64.109 秒，加原新窗口 417.282 秒为 **481.391／3000 秒**。保留旧历史记录，不重算历史输出。新输出仅在本轮目录。
- 当前文档校验及 `git diff --check` 在本报告之后运行一次；结果和原始日志见本轮输出目录，96 条历史链接问题不在本轮修复范围。
