# 阶段3收尾与阶段4 Sol交接

2026-11-06，Sol。维护者采纳最新G04／附加用例编排，并要求新开Sol对话接手阶段4。本轮聚焦核查结论：**G03冻结范围内未发现未闭合required项，可以有界收尾；G04仍PLANNED／attempt0，无已派4a包。** 本次不实现、不运行native、不创建或消息执行对话，不合并到develop／main。

完整人工交接包位于维护者工作区 `handoffs/V211_G04_sol_handoff/`，含README、可直接转发的prompt、准确最终input-snapshot、成员manifest和只读校验脚本。新Sol先读该README全文，再按分层必读清单进入；**不要用旧G03交接README恢复当前状态**。精确交接HEAD在该包snapshot冻结，不在本页预造自引用SHA。

## 已接收成果与当前源码

| 子阶段 | 最终执行交付 | 独立接收及范围 |
| --- | --- | --- |
| 3a | `6b11123e3293743e01c90ed0ce94e0be450e3833` | [ACCEPTED_3A_ROUTING_ADMISSION](reviews/20261105_3a_diagnostic_attempt001_sol_review.md)：配置／消费级依赖准入、已有声明与具名构建检查、同请求回执；普通3次＋维护者指定诊断1次分记 |
| 3b | `305b1fa5f99e3430b8e71ee6d0ed61586f6556af` | [ACCEPTED_BOUNDED_3B_NATIVE_EXECUTION](reviews/20261106_3b_attempt003_sol_review.md)：冻结三路线真实执行、模型／reset读回、同次记录及有界Panda MuJoCo CPU补偿；普通3次 |
| 3c | `29855741e4e0075336854a9f7708c67d78a8a0aa`，实际运行代码`af6638684c071749c6ecb19f990b13afdb742cee` | [ACCEPTED_BOUNDED_3C_RESET_REBUILD](reviews/20261106_3c_attempt001_sol_review.md)：显式PickCube state-only profile，MJC→GP→MJC→Isaac6.2→MJC，固定obs／随机流／旧输入拒绝／故障处置／逐episode记录与关闭；普通1次 |

当前Core checkout仍为 `/home/lly/.codex/worktrees/v210-integration/Geochora`，分支`codex/v211-stage3`。核查输入`a884e357f874ed7c4a71dda7ed963638c98f06fe`相对3c最终交付的`task_env/`、GeoPhys gitlink及asset无差异；后续Sol提交只更新独立审阅、当前导航和规划。因此复用已有接收和定向检查，不重跑native／历史矩阵／全部raw摘要。

GeoPhys为`dc2685e28c6c916fb6403a2342c04e0d2520aef7`，其本地`codex/v2.1-integration`与gitlink一致且clean；Menagerie为`b846dd12bc459d776cccb3dee0b1d02acbf7a9c7`且clean。provider变更只增加实际有效模型公共读回相关内容，不是MuJoCo依赖升级或solver数值修复。

核查时tracked/index clean，三份保护untracked仍在：`MUJOCO_LOG.TXT`、`docs/maintenance/20261030_runtime_route_diagnostic_handoff.md`、`planning/stage3-gravity-compensation-proposal.md`（最后一项相对此版本目录）。不得stage／删除。当前实施者对话最后turn completed、idle；3b／3c原收据writer/native均RELEASED，编排active_packages为空，读取两把指定native锁的inode未见持有者。该观察只描述交接时点，不承诺未来机器空闲。

## 本轮补齐的交接遗漏

README底部、capabilities末段仍写补偿“待独立复审”，TaskEnv Skill routes仍写后续维护待审；已按实际接收修正导航，不重写旧执行报告。维护者已采纳的附加用例排期从待审提案更新为已确认规划，实施仍NOT_RUN。原G04的14条主线工作／检查／出口和12个控制协议案例保留，附加用例另表维护。

本地develop仍为`9d942d43a1cf3210d5bccca0f703c1be4ba45654`，核查输入领先其37提交、落后0；缓存public/develop仍`fd03817c9f6ef8ce9fd68c1db30125efda68e1c8`，本轮未fetch，不称其为远端最新。**不能直接从旧develop开始4a而漏掉G03。** 新Sol先记录阶段4的一个主题分支、0新worktree安排，按AGENTS核对fetch后的develop，并在新主题分支接纳已接收G03历史；若develop仍为祖先，可从develop建新主题分支后快进纳入交接HEAD。4a冻结输入必须含本交接。此过程不修改develop／main，不授权push／merge回主分支；出现分叉先记录最小集成方案，不reset或重建本地历史。当前不创建该分支。

## 保留限制，不能改判或追加旧门

- 原3b默认关闭三后端N08仍FAIL；新N08-v2只证明正向动作效应。有界补偿仅Panda、MuJoCo CPU、in-process、默认关闭；最终350步保持与三份H5已接收。通用子树／外接夹爪／新Robot尚未实现。
- N09按已发布11个控制边界、G01按351边界验收；未记录的外物子步／连续接触遥测不事后追加。其余原本承诺的本体子步贡献仍保留；ACK不能当实测。
- Isaac6.2专用worker完成session／App／source清理和ACK后受控退出0，不代表Python／Kit自然析构已修复。6.1辅助App版本／来源／启动核验成立，但close在300秒未返回；完整Env闭环未测。该兼容限制后续独立处理，不重开G03或当4a隐含前置；5.1仍延期。
- 3c只覆盖声明的PickCube四条边及same-route reset；无provider_alias，借用view失效未实测。故障终端合成检查不等于真实SDK故障注入。未授权RGB／batch／全任务能力或Qualification。
- 原native锁／cwd偏差、丢失测试观察句柄、部分资源／步数未知及3b授权超时收尾均已披露；不删失败，不为补账本再运行。3c独立25项通过、1旧Position来源fixture被Sol SDK guard阻止并保留原执行证据；不能写成该项独立通过。

## 阶段4正确的动工范围

以[G04](../goals/04-control.md)和[控制协议](../contracts/control-and-feedback.md)为主：4a落地嵌套主体、typed JointEffort／BodyWrench／load扩展槽、公共state/model、显式贡献及唯一提交契约；4b完成三后端7＋2 effort、共享Controller／direct effort、最小真实外力与组合；4c完成Controller／输入规格reset往返、清历史、固定obs及迁移后PickCube成功。阶段3R3位置参考和补偿偏置不等于这些能力已经完成。

[装配Panda](../planning/stage4-assembled-panda.md)及[单独用例清单](../planning/assembled-panda-use-case.json)消费这些成果：4a需求审阅；4b主能力稳定且已在完整包冻结范围／预算时做新Robot、空载跟踪／夹爪／补偿早检查；4c有效参考复用；7a完整两任务配置／Solution成功收口，7b只复核受影响输入。不把它升级为G04新增接收门，也不静默删除版本用例。Robot类放`task_env/robots/`、两任务正常构建实际消费，参数可不同，不要求复刻一体Panda物性。

新Sol首轮完成接手核对、在途／writer判断、阶段4分支继承安排和首份完整4a包准备；实施由维护者指定并手动转发Terra／Luna，返包后Sol独立审阅。不自动消息、建执行对话、subagent、native或阶段5。所有故障处理和必读Skill／源码落点详见外部README，避免再从全库审计开始。

## 本轮静态验证

current文档检查零错误、96项既有历史链接问题保留；TaskEnv Skill的引用检查与metadata检查通过，`git diff --check`通过。逐字比对确认原G04的14条主线及原控制案例字节未改。TaskEnv Skill仅更新接收／交接导航，复用已有独立主审和未变化源码；未重跑示例、native、历史矩阵或新agent冷启动，不把静态检查当行为证明。紧凑收据和命令日志在外部交接包`closeout-audit.json`及对应validation日志中。
